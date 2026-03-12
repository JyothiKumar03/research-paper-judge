import asyncio
import time
from typing import Optional

import asyncpg

from app.constants import AgentName, AgentStatus, FindingSeverity, TaskType
from app.db import get_pages_by_paper, get_paper, insert_agent_result
from app.prompts.grammar import GRAMMAR_JSON_SCHEMA, GRAMMAR_SYSTEM, _SKIP_TAGS, build_grammar_prompt
from app.services.llm_service import LLMExhaustedError, build_model_chain, call_llm
from app.types import AgentResult, Finding, TokenUsage
from app.utils.json_parser import parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_CONCURRENCY = 6


async def run(pool: asyncpg.Pool, paper_id: str) -> AgentResult:
    t0 = time.perf_counter()
    log.info("grammar_agent: start paper=%s", paper_id)

    paper = await get_paper(pool, paper_id)
    title = paper["title"] if paper else ""
    pages = await get_pages_by_paper(pool, paper_id)

    eval_pages = [
        p for p in pages
        if p.get("page_tag") and p["page_tag"] not in _SKIP_TAGS
    ]

    if not eval_pages:
        log.warning("grammar_agent: no evaluable pages for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.GRAMMAR,
            score=50.0,
            status=AgentStatus.SKIPPED,
            error_msg="No evaluable pages found",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    models = build_model_chain(TaskType.GRAMMAR)

    async def _check_page(page: dict) -> Optional[dict]:
        async with semaphore:
            prompt = build_grammar_prompt(page["markdown"], page["page_tag"], title)
            try:
                resp = await call_llm(
                    prompt, models, system=GRAMMAR_SYSTEM, json_schema=GRAMMAR_JSON_SCHEMA
                )
                parsed = parse_llm_json(resp.content, fallback={})
                if isinstance(parsed, dict) and "total_no_of_mistakes" in parsed:
                    return {
                        "page_no": page["page_num"],
                        "mistakes": int(parsed.get("total_no_of_mistakes", 0)),
                        "sequences": parsed.get("mistakes_start_sequence", []),
                        "evaluation_reasoning": parsed.get("evaluation_reasoning", ""),
                        "tokens": resp.usage.total_tokens,
                    }
                log.warning("grammar_agent: bad response page=%d", page["page_num"])
            except LLMExhaustedError:
                log.error("grammar_agent: models exhausted page=%d", page["page_num"])
            except Exception as exc:
                log.error("grammar_agent: error page=%d — %s", page["page_num"], exc)
            return None

    page_results = [
        r for r in await asyncio.gather(*[_check_page(p) for p in eval_pages])
        if r is not None
    ]

    total_mistakes = sum(r["mistakes"] for r in page_results)
    all_sequences = [seq for r in page_results for seq in r["sequences"]]
    total_tokens = sum(r["tokens"] for r in page_results)
    page_reasonings = {r["page_no"]: r["evaluation_reasoning"] for r in page_results if r.get("evaluation_reasoning")}
    score = max(0.0, 100.0 - min(100.0, total_mistakes * 2.0))

    findings = [
        Finding(
            category="grammar",
            location=f"page {r['page_no']}",
            description=f"{r['mistakes']} mistake(s): {', '.join(r['sequences'][:5])}",
            severity=FindingSeverity.HIGH if r["mistakes"] > 5 else FindingSeverity.MEDIUM,
        )
        for r in page_results
        if r["mistakes"] > 0
    ]

    result = AgentResult(
        agent_name=AgentName.GRAMMAR,
        score=round(score, 1),
        findings=findings,
        usage=TokenUsage(total_tokens=total_tokens),
        duration_s=round(time.perf_counter() - t0, 2),
        status=AgentStatus.COMPLETED,
        raw_output=str({"total_mistakes": total_mistakes, "sequences": all_sequences[:50], "evaluation_reasoning": page_reasonings}),
    )

    await insert_agent_result(pool, paper_id, result)
    log.info(
        "grammar_agent: done paper=%s score=%.1f mistakes=%d tokens=%d",
        paper_id, score, total_mistakes, total_tokens,
    )
    return result
