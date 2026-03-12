import time

import asyncpg

from app.constants import AgentName, AgentStatus, FindingSeverity, TaskType
from app.db import get_pages_by_paper, get_paper, insert_agent_result
from app.prompts.factcheck import FACTCHECK_JSON_SCHEMA, FACTCHECK_SYSTEM, build_factcheck_prompt
from app.services.llm_service import LLMExhaustedError, build_model_chain, call_llm
from app.types import AgentResult, Finding, TokenUsage
from app.utils.json_parser import parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_SKIP_TAGS = {"REFERENCES", "ACKNOWLEDGMENTS", "APPENDIX", "TITLE", "OTHER"}


async def run(pool: asyncpg.Pool, paper_id: str) -> AgentResult:
    t0 = time.perf_counter()
    log.info("factcheck_agent: start paper=%s", paper_id)

    paper = await get_paper(pool, paper_id)
    title = paper["title"] if paper else ""
    pages = await get_pages_by_paper(pool, paper_id)

    # Collect (page_no, summary, image_data) for evaluable pages
    page_data = [
        (p["page_num"], p.get("page_summary", ""), p.get("image_data", ""))
        for p in pages
        if p.get("page_tag") not in _SKIP_TAGS
        and (p.get("page_summary", "").strip() or p.get("image_data", "").strip())
    ]

    if not page_data:
        log.warning("factcheck_agent: no page content for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.FACTCHECK,
            score=50.0,
            status=AgentStatus.SKIPPED,
            error_msg="No page summaries or image data available",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    models = build_model_chain(TaskType.FACTCHECK)
    prompt = build_factcheck_prompt(title, page_data)

    try:
        resp = await call_llm(
            prompt, models, system=FACTCHECK_SYSTEM, json_schema=FACTCHECK_JSON_SCHEMA
        )
        parsed = parse_llm_json(resp.content, fallback={})
        errors = parsed.get("errors", []) if isinstance(parsed, dict) else []
        evaluation_reasoning = parsed.get("evaluation_reasoning", "") if isinstance(parsed, dict) else ""
    except LLMExhaustedError:
        log.error("factcheck_agent: all models exhausted for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.FACTCHECK,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg="All LLM models exhausted",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result
    except Exception as exc:
        log.error("factcheck_agent: error for paper=%s — %s", paper_id, exc)
        result = AgentResult(
            agent_name=AgentName.FACTCHECK,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg=str(exc),
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    score = max(0.0, 100.0 - len(errors) * 15.0)

    findings = [
        Finding(
            category=e.get("error_type", "unknown"),
            location=f"page {e.get('page_no', '?')}",
            description=e.get("error_description", ""),
            severity=FindingSeverity.HIGH,
        )
        for e in errors
        if isinstance(e, dict)
    ]

    result = AgentResult(
        agent_name=AgentName.FACTCHECK,
        score=round(score, 1),
        findings=findings,
        usage=TokenUsage(total_tokens=resp.usage.total_tokens),
        duration_s=round(time.perf_counter() - t0, 2),
        status=AgentStatus.COMPLETED,
        raw_output=str({"errors": errors, "evaluation_reasoning": evaluation_reasoning}),
    )

    await insert_agent_result(pool, paper_id, result)
    log.info(
        "factcheck_agent: done paper=%s score=%.1f errors=%d tokens=%d",
        paper_id, score, len(errors), resp.usage.total_tokens,
    )
    return result
