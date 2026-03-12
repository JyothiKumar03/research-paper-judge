import time

import asyncpg

from app.constants import AgentName, AgentStatus, FindingSeverity, TaskType
from app.db import get_pages_by_paper, get_paper, insert_agent_result
from app.prompts.consistency import CONSISTENCY_JSON_SCHEMA, CONSISTENCY_SYSTEM, build_consistency_prompt
from app.services.llm_service import LLMExhaustedError, build_model_chain, call_llm
from app.types import AgentResult, Finding, TokenUsage
from app.utils.json_parser import parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_SKIP_TAGS = {"REFERENCES", "ACKNOWLEDGMENTS", "TITLE"}

_SEVERITY_PENALTY = {"HIGH": 15, "MEDIUM": 10, "LOW": 5}
_SEVERITY_MAP = {"HIGH": FindingSeverity.HIGH, "MEDIUM": FindingSeverity.MEDIUM, "LOW": FindingSeverity.LOW}


async def run(pool: asyncpg.Pool, paper_id: str) -> AgentResult:
    t0 = time.perf_counter()
    log.info("consistency_agent: start paper=%s", paper_id)

    paper = await get_paper(pool, paper_id)
    title = paper["title"] if paper else ""
    pages = await get_pages_by_paper(pool, paper_id)

    # Send all pages except boilerplate — no tag filtering
    all_pages = [
        p for p in pages
        if p.get("page_tag") not in _SKIP_TAGS
        and (p.get("page_summary", "").strip() or p.get("image_data", "").strip() or p.get("markdown", "").strip())
    ]

    if not all_pages:
        log.warning("consistency_agent: no content pages for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.CONSISTENCY,
            score=50.0,
            status=AgentStatus.SKIPPED,
            error_msg="No content pages found",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    models = build_model_chain(TaskType.CONSISTENCY)
    prompt = build_consistency_prompt(title, all_pages)

    try:
        resp = await call_llm(
            prompt, models, system=CONSISTENCY_SYSTEM, json_schema=CONSISTENCY_JSON_SCHEMA
        )
        parsed = parse_llm_json(resp.content, fallback={})
        issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
        evaluation_reasoning = parsed.get("evaluation_reasoning", "") if isinstance(parsed, dict) else ""
    except LLMExhaustedError:
        log.error("consistency_agent: all models exhausted for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.CONSISTENCY,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg="All LLM models exhausted",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result
    except Exception as exc:
        log.error("consistency_agent: error for paper=%s — %s", paper_id, exc)
        result = AgentResult(
            agent_name=AgentName.CONSISTENCY,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg=str(exc),
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    total_penalty = sum(
        _SEVERITY_PENALTY.get(issue.get("severity", "LOW"), 5)
        for issue in issues
        if isinstance(issue, dict)
    )
    score = max(0.0, 100.0 - total_penalty)

    findings = [
        Finding(
            category="consistency",
            location=f"pages {issue.get('page_nos', [])}",
            description=issue.get("description", ""),
            severity=_SEVERITY_MAP.get(issue.get("severity", "LOW"), FindingSeverity.LOW),
        )
        for issue in issues
        if isinstance(issue, dict)
    ]

    result = AgentResult(
        agent_name=AgentName.CONSISTENCY,
        score=round(score, 1),
        findings=findings,
        usage=TokenUsage(total_tokens=resp.usage.total_tokens),
        duration_s=round(time.perf_counter() - t0, 2),
        status=AgentStatus.COMPLETED,
        raw_output=str({"issues": issues, "evaluation_reasoning": evaluation_reasoning}),
    )

    await insert_agent_result(pool, paper_id, result)
    log.info(
        "consistency_agent: done paper=%s score=%.1f issues=%d tokens=%d",
        paper_id, score, len(issues), resp.usage.total_tokens,
    )
    return result
