import asyncio
import time

import httpx
import asyncpg

from app.config import settings
from app.constants import AgentName, AgentStatus, FindingSeverity, NOVELTY_SCORE_MAP, NoveltyIndex, TaskType
from app.db import get_pages_by_paper, get_paper, insert_agent_result
from app.prompts.novelty import NOVELTY_SYSTEM, build_novelty_prompt
from app.services.llm_service import build_model_chain, call_llm
from app.types import AgentResult, Finding, TokenUsage
from app.utils.json_parser import extract_score, parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_INTRO_TAGS = {"ABSTRACT", "INTRODUCTION", "RELATED_WORK", "CONCLUSION"}


async def run(pool: asyncpg.Pool, paper_id: str) -> AgentResult:
    t0 = time.perf_counter()
    log.info("novelty_agent: start paper=%s", paper_id)

    paper = await get_paper(pool, paper_id)
    if not paper:
        result = AgentResult(
            agent_name=AgentName.NOVELTY,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg="Paper not found in DB",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    pages = await get_pages_by_paper(pool, paper_id)
    intro_pages = [
        p for p in pages
        if p.get("page_tag") in _INTRO_TAGS and p.get("markdown", "").strip()
    ]
    intro_text = "\n\n".join(p["markdown"] for p in intro_pages)[:8000]

    prompt = build_novelty_prompt(
        title=paper["title"],
        abstract=paper["abstract"],
        intro=intro_text,
        paper_url=paper.get("pdf_url", ""),
        publish_date=paper.get("submitted_date", ""),
    )

    models = build_model_chain(TaskType.NOVELTY)
    raw_text = None

    for model_cfg in models:
        try:
            if model_cfg.model.startswith("google/"):
                gemini_model = model_cfg.model.removeprefix("google/")
                raw_text = await _call_gemini_with_grounding(prompt, gemini_model)
            else:
                resp = await call_llm(prompt, [model_cfg], system=NOVELTY_SYSTEM)
                raw_text = resp.content
            break
        except Exception as exc:
            log.warning("novelty_agent: model=%s failed — %s", model_cfg.model, exc)
            continue

    if raw_text is None:
        log.error("novelty_agent: all models exhausted for paper=%s", paper_id)
        result = AgentResult(
            agent_name=AgentName.NOVELTY,
            score=50.0,
            status=AgentStatus.FAILED,
            error_msg="All models exhausted",
            duration_s=round(time.perf_counter() - t0, 2),
        )
        await insert_agent_result(pool, paper_id, result)
        return result

    parsed = parse_llm_json(raw_text, fallback={})
    novelty_str = parsed.get("novelty_index", "") if isinstance(parsed, dict) else ""

    try:
        novelty_index = NoveltyIndex(novelty_str)
        score = NOVELTY_SCORE_MAP[novelty_index]
    except (ValueError, KeyError):
        log.warning("novelty_agent: unknown novelty_index %r — using extracted score", novelty_str)
        score = extract_score(raw_text, default=50.0)
        novelty_index = None

    similar_papers = parsed.get("similar_papers", []) if isinstance(parsed, dict) else []
    assessment = parsed.get("assessment", "") if isinstance(parsed, dict) else ""
    contributions = parsed.get("key_contributions_verified", []) if isinstance(parsed, dict) else []
    evaluation_reasoning = parsed.get("evaluation_reasoning", "") if isinstance(parsed, dict) else ""

    findings = []
    if similar_papers:
        findings.append(Finding(
            category="novelty",
            location="paper-level",
            description=f"Similar papers found: {'; '.join(str(p) for p in similar_papers[:5])}",
            severity=FindingSeverity.MEDIUM,
        ))
    if assessment:
        findings.append(Finding(
            category="novelty",
            location="paper-level",
            description=assessment,
            severity=FindingSeverity.LOW if score >= 60 else FindingSeverity.HIGH,
        ))

    result = AgentResult(
        agent_name=AgentName.NOVELTY,
        score=round(float(score), 1),
        findings=findings,
        usage=TokenUsage(),
        duration_s=round(time.perf_counter() - t0, 2),
        status=AgentStatus.COMPLETED,
        raw_output=str({"novelty_index": novelty_str, "similar_papers": similar_papers, "contributions": contributions, "evaluation_reasoning": evaluation_reasoning}),
    )

    await insert_agent_result(pool, paper_id, result)
    log.info(
        "novelty_agent: done paper=%s score=%.1f novelty=%s similar=%d",
        paper_id, score, novelty_str, len(similar_papers),
    )
    return result


_GROUNDING_RETRIES = 5
_GROUNDING_BACKOFF_S = 5


async def _call_gemini_with_grounding(prompt: str, model: str) -> str:
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": NOVELTY_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 5000},
    }
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, _GROUNDING_RETRIES + 1):
        try:
            log.debug("_call_gemini_with_grounding: model=%s attempt=%d/%d", model, attempt, _GROUNDING_RETRIES)
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            log.warning(
                "_call_gemini_with_grounding: model=%s attempt=%d failed (status=%s) — retrying in %ds",
                model, attempt, status, _GROUNDING_BACKOFF_S,
            )
            if attempt < _GROUNDING_RETRIES:
                await asyncio.sleep(_GROUNDING_BACKOFF_S)

    raise last_exc
