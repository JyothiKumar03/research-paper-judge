import time

import asyncpg

from app.constants import AgentName, AgentStatus, FindingSeverity, RiskLevel, TaskType
from app.db import get_pages_by_paper, get_paper, insert_agent_result
from app.prompts.authenticity import AUTHENTICITY_JSON_SCHEMA, AUTHENTICITY_SYSTEM, build_authenticity_prompt
from app.services.llm_service import LLMExhaustedError, build_model_chain, call_llm
from app.types import AgentResult, Finding, TokenUsage
from app.utils.json_parser import parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_RESULTS_TAGS = {"RESULTS", "DISCUSSION", "EXPERIMENTS"}
_METHODOLOGY_TAGS = {"METHODOLOGY", "BACKGROUND"}

_RISK_PENALTY = {"HIGH": 25, "MEDIUM": 15, "LOW": 5}
_RISK_TO_SEVERITY = {
    "HIGH": FindingSeverity.HIGH,
    "MEDIUM": FindingSeverity.MEDIUM,
    "LOW": FindingSeverity.LOW,
}
_OVERALL_RISK_SCORE = {
    RiskLevel.HIGH: 20.0,
    RiskLevel.MEDIUM: 55.0,
    RiskLevel.LOW: 80.0,
    RiskLevel.NONE: 100.0,
}


async def run(pool: asyncpg.Pool, paper_id: str) -> AgentResult:
    t0 = time.perf_counter()
    log.info("authenticity_agent: start paper=%s", paper_id)

    paper = await get_paper(pool, paper_id)
    title = paper["title"] if paper else ""
    pages = await get_pages_by_paper(pool, paper_id)

    results_pages = [p for p in pages if p.get("page_tag") in _RESULTS_TAGS]
    methodology_pages = [p for p in pages if p.get("page_tag") in _METHODOLOGY_TAGS]

    if not results_pages:
        log.warning("authenticity_agent: no results pages for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.AUTHENTICITY,
            score=50.0,
            status=AgentStatus.SKIPPED,
            error_msg="No results pages found",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    models = build_model_chain(TaskType.AUTHENTICITY)
    prompt = build_authenticity_prompt(title, results_pages, methodology_pages)

    try:
        resp = await call_llm(
            prompt, models, system=AUTHENTICITY_SYSTEM, json_schema=AUTHENTICITY_JSON_SCHEMA
        )
        parsed = parse_llm_json(resp.content, fallback={})
        red_flags = parsed.get("red_flags", []) if isinstance(parsed, dict) else []
        overall_risk_str = parsed.get("overall_risk", "NONE") if isinstance(parsed, dict) else "NONE"
    except LLMExhaustedError:
        log.error("authenticity_agent: all models exhausted for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.AUTHENTICITY,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg="All LLM models exhausted",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result
    except Exception as exc:
        log.error("authenticity_agent: error for paper=%s — %s", paper_id, exc)
        result = AgentResult(
            agent_name=AgentName.AUTHENTICITY,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg=str(exc),
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    try:
        overall_risk = RiskLevel(overall_risk_str)
    except ValueError:
        overall_risk = RiskLevel.NONE

    flag_penalty = sum(
        _RISK_PENALTY.get(f.get("risk_level", "LOW"), 5)
        for f in red_flags
        if isinstance(f, dict)
    )
    base_score = _OVERALL_RISK_SCORE[overall_risk]
    score = max(0.0, min(base_score, 100.0 - flag_penalty))

    findings = [
        Finding(
            category=f.get("flag_type", "unknown"),
            location=f"page {f.get('page_no', '?')}",
            description=f.get("description", ""),
            severity=_RISK_TO_SEVERITY.get(f.get("risk_level", "LOW"), FindingSeverity.LOW),
        )
        for f in red_flags
        if isinstance(f, dict)
    ]

    result = AgentResult(
        agent_name=AgentName.AUTHENTICITY,
        score=round(score, 1),
        findings=findings,
        usage=TokenUsage(total_tokens=resp.usage.total_tokens),
        duration_s=round(time.perf_counter() - t0, 2),
        status=AgentStatus.COMPLETED,
        raw_output=str({"overall_risk": overall_risk_str, "red_flags": red_flags}),
    )

    await insert_agent_result(pool, paper_id, result)
    log.info(
        "authenticity_agent: done paper=%s score=%.1f risk=%s flags=%d tokens=%d",
        paper_id, score, overall_risk_str, len(red_flags), resp.usage.total_tokens,
    )
    return result
