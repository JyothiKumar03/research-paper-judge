import ast
import time
from datetime import datetime, timezone

import asyncpg

from app.constants import (
    AGENT_WEIGHTS,
    AgentName,
    NoveltyIndex,
    PASS_THRESHOLD,
    TaskType,
    Verdict,
)
from app.db import get_agent_results, get_paper, insert_report
from app.prompts.evaluator import EVALUATOR_JSON_SCHEMA, EVALUATOR_SYSTEM, build_evaluator_prompt
from app.services.llm_service import LLMExhaustedError, build_model_chain, call_llm
from app.utils.json_parser import parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_NOVELTY_LABEL: dict[str, str] = {
    "HIGHLY_NOVEL":           "Highly Novel — strong original contribution not found in prior literature",
    "MODERATELY_NOVEL":       "Moderately Novel — meaningful advancement over existing work",
    "INCREMENTAL":            "Incremental — minor extension of known methods",
    "POTENTIALLY_DERIVATIVE": "Potentially Derivative — largely overlaps with prior literature",
}

_GRAMMAR_RATING = lambda score: "HIGH" if score >= 80 else ("MEDIUM" if score >= 50 else "LOW")


_TOKEN_LIMIT = 16_000


async def run(
    pool: asyncpg.Pool,
    paper_id: str,
) -> dict:
    t0 = time.perf_counter()
    log.info("evaluator_agent: start paper=%s", paper_id)

    paper = await get_paper(pool, paper_id)
    title = paper["title"] if paper else ""

    # Fetch agent results from DB (source of truth, not in-memory props)
    db_rows = await get_agent_results(pool, paper_id)

    agent_data: dict = {}
    for row in db_rows:
        name = AgentName(row["agent_name"])
        raw: dict = {}
        try:
            if row["raw_output"]:
                raw = ast.literal_eval(row["raw_output"])
        except Exception:
            pass
        agent_data[name] = {
            "score": row["score"] if row["score"] is not None else 50.0,
            "status": row["status"],
            "findings": row["findings"],  # already parsed by get_agent_results
            "evaluation_reasoning": raw.get("evaluation_reasoning", ""),
            "raw": raw,
        }

    # Weighted overall score
    overall_score = round(
        sum(
            AGENT_WEIGHTS.get(name, 0.0) * agent_data.get(name, {}).get("score", 50.0)
            for name in AgentName
        ),
        1,
    )

    # Derived values
    grammar_score = agent_data.get(AgentName.GRAMMAR, {}).get("score", 50.0)
    grammar_rating = _GRAMMAR_RATING(grammar_score)

    novelty_raw = agent_data.get(AgentName.NOVELTY, {}).get("raw", {})
    novelty_index = novelty_raw.get("novelty_index", "INCREMENTAL")
    novelty_label = _NOVELTY_LABEL.get(novelty_index, novelty_index)

    auth_raw = agent_data.get(AgentName.AUTHENTICITY, {}).get("raw", {})
    fabrication_risk_pct = round(
        100.0 - agent_data.get(AgentName.AUTHENTICITY, {}).get("score", 50.0), 1
    )

    # LLM call for verdict, executive summary, and detailed reasoning
    models = build_model_chain(TaskType.EXECUTIVE_SUMMARY)
    prompt = build_evaluator_prompt(
        title, agent_data, overall_score, grammar_rating, novelty_label, fabrication_risk_pct,
        include_grammar_sequences=True,
    )
    # Rough token estimate: ~4 chars per token. If over limit, strip grammar sequences.
    if len(prompt) // 4 > _TOKEN_LIMIT:
        log.warning(
            "evaluator_agent: prompt ~%d tokens exceeds %d limit, stripping grammar sequences for paper=%s",
            len(prompt) // 4, _TOKEN_LIMIT, paper_id,
        )
        prompt = build_evaluator_prompt(
            title, agent_data, overall_score, grammar_rating, novelty_label, fabrication_risk_pct,
            include_grammar_sequences=False,
        )

    executive_summary = ""
    novelty_assessment = ""
    fabrication_risk_level = auth_raw.get("overall_risk", "NONE")
    detailed_reasoning = ""
    verdict_from_llm: str | None = None

    try:
        resp = await call_llm(
            prompt, models, system=EVALUATOR_SYSTEM, json_schema=EVALUATOR_JSON_SCHEMA
        )
        parsed = parse_llm_json(resp.content, fallback={})
        if isinstance(parsed, dict):
            verdict_from_llm = parsed.get("verdict")
            executive_summary = parsed.get("executive_summary", "")
            novelty_assessment = parsed.get("novelty_assessment", "")
            fabrication_risk_level = parsed.get("fabrication_risk_level", fabrication_risk_level)
            detailed_reasoning = parsed.get("detailed_reasoning", "")
    except LLMExhaustedError:
        log.error("evaluator_agent: all models exhausted for paper=%s", paper_id)
    except Exception as exc:
        log.error("evaluator_agent: LLM error for paper=%s — %s", paper_id, exc)

    # Final verdict: trust LLM if valid, else fall back to threshold
    if verdict_from_llm in ("PASS", "FAIL"):
        verdict = Verdict(verdict_from_llm)
    else:
        verdict = Verdict.PASS if overall_score >= PASS_THRESHOLD else Verdict.FAIL

    # Build the markdown report
    factcheck_raw = agent_data.get(AgentName.FACTCHECK, {}).get("raw", {})
    factcheck_verified = factcheck_raw.get("verified_claims", [])

    markdown = _build_markdown(
        paper_id=paper_id,
        title=title,
        overall_score=overall_score,
        verdict=verdict,
        executive_summary=executive_summary,
        agent_data=agent_data,
        grammar_rating=grammar_rating,
        grammar_score=grammar_score,
        novelty_index=novelty_index,
        novelty_label=novelty_label,
        novelty_assessment=novelty_assessment,
        fabrication_risk_pct=fabrication_risk_pct,
        fabrication_risk_level=fabrication_risk_level,
        detailed_reasoning=detailed_reasoning,
        factcheck_verified=factcheck_verified,
    )

    scores_out = {name.value: agent_data.get(name, {}).get("score") for name in AgentName}
    weights_out = {k.value: v for k, v in AGENT_WEIGHTS.items()}

    await insert_report(
        pool,
        paper_id,
        overall_score=overall_score,
        verdict=verdict,
        weights=weights_out,
        scores=scores_out,
        executive_summary=executive_summary,
        markdown_report=markdown,
    )

    duration = round(time.perf_counter() - t0, 2)
    log.info(
        "evaluator_agent: done paper=%s score=%.1f verdict=%s duration=%.2fs",
        paper_id, overall_score, verdict.value, duration,
    )
    return {"overall_score": overall_score, "verdict": verdict.value, "duration_s": duration}


def _build_markdown(
    paper_id: str,
    title: str,
    overall_score: float,
    verdict: Verdict,
    executive_summary: str,
    agent_data: dict,
    grammar_rating: str,
    grammar_score: float,
    novelty_index: str,
    novelty_label: str,
    novelty_assessment: str,
    fabrication_risk_pct: float,
    fabrication_risk_level: str,
    detailed_reasoning: str,
    factcheck_verified: list,
) -> str:
    verdict_icon = "✅" if verdict == Verdict.PASS else "❌"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    consistency_score = agent_data.get(AgentName.CONSISTENCY, {}).get("score", 50.0)
    consistency_reasoning = agent_data.get(AgentName.CONSISTENCY, {}).get("evaluation_reasoning", "")
    consistency_findings = agent_data.get(AgentName.CONSISTENCY, {}).get("findings", [])

    grammar_raw = agent_data.get(AgentName.GRAMMAR, {}).get("raw", {})
    grammar_total_mistakes = grammar_raw.get("total_mistakes", 0)
    grammar_page_reasonings = grammar_raw.get("evaluation_reasoning", {})
    grammar_findings = agent_data.get(AgentName.GRAMMAR, {}).get("findings", [])

    novelty_score = agent_data.get(AgentName.NOVELTY, {}).get("score", 50.0)
    novelty_reasoning = agent_data.get(AgentName.NOVELTY, {}).get("evaluation_reasoning", "")
    novelty_raw = agent_data.get(AgentName.NOVELTY, {}).get("raw", {})
    novelty_similar = novelty_raw.get("similar_papers", [])
    novelty_contributions = novelty_raw.get("contributions", [])

    factcheck_score = agent_data.get(AgentName.FACTCHECK, {}).get("score", 50.0)
    factcheck_findings = agent_data.get(AgentName.FACTCHECK, {}).get("findings", [])
    factcheck_reasoning = agent_data.get(AgentName.FACTCHECK, {}).get("evaluation_reasoning", "")
    factcheck_raw = agent_data.get(AgentName.FACTCHECK, {}).get("raw", {})
    factcheck_verified = factcheck_raw.get("verified_claims", [])

    auth_score = agent_data.get(AgentName.AUTHENTICITY, {}).get("score", 50.0)
    auth_findings = agent_data.get(AgentName.AUTHENTICITY, {}).get("findings", [])
    auth_reasoning = agent_data.get(AgentName.AUTHENTICITY, {}).get("evaluation_reasoning", "")

    lines: list[str] = [
        "# Research Paper Evaluation Report",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Paper ID** | `{paper_id}` |",
        f"| **Title** | {title} |",
        f"| **Overall Score** | **{overall_score}/100** |",
        f"| **Verdict** | {verdict_icon} **{verdict.value}** |",
        f"| **Generated** | {timestamp} |",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        executive_summary or "_No executive summary generated._",
        "",
        "---",
        "",
        "## Detailed Scores",
        "",
        "---",
        "",
        "### 1. Consistency",
        "",
        f"**Score:** {consistency_score}/100",
        "",
    ]

    if consistency_findings:
        lines += ["**Issues Found:**", ""]
        for f in consistency_findings:
            lines.append(f"- **[{f['severity']}]** {f['description']} *({f['location']})*")
        lines.append("")
    else:
        lines += ["**Issues Found:** None", ""]

    if consistency_reasoning:
        lines += ["**Evaluation Reasoning:**", "", consistency_reasoning, ""]

    lines += [
        "---",
        "",
        "### 2. Grammar",
        "",
        f"**Rating:** {grammar_rating}",
        f"**Score:** {grammar_score}/100",
        f"**Total Mistakes Detected:** {grammar_total_mistakes}",
        "",
    ]

    if isinstance(grammar_page_reasonings, dict) and grammar_page_reasonings:
        lines += ["**Page-by-Page Evaluation:**", ""]
        for page_no, reasoning in grammar_page_reasonings.items():
            lines += [f"**Page {page_no}:**", reasoning, ""]
    elif isinstance(grammar_page_reasonings, str) and grammar_page_reasonings:
        lines += ["**Evaluation Reasoning:**", "", grammar_page_reasonings, ""]

    if grammar_findings:
        lines += ["**Pages with Issues:**", ""]
        for f in grammar_findings:
            lines.append(f"- **[{f['severity']}]** {f['description']} *({f['location']})*")
        lines.append("")

    lines += [
        "---",
        "",
        "### 3. Novelty",
        "",
        f"**Index:** {novelty_index}",
        f"**Description:** {novelty_label}",
        f"**Score:** {novelty_score}/100",
        "",
    ]

    if novelty_assessment:
        lines += ["**Assessment:**", "", novelty_assessment, ""]

    if novelty_similar:
        lines += ["**Similar Prior Work:**", ""]
        for p in novelty_similar[:5]:
            lines.append(f"- {p}")
        lines.append("")

    if novelty_contributions:
        lines += ["**Contributions Verified:**", ""]
        for c in novelty_contributions:
            lines.append(f"- {c}")
        lines.append("")

    if novelty_reasoning:
        lines += ["**Evaluation Reasoning:**", "", novelty_reasoning, ""]

    lines += [
        "---",
        "",
        "### 4. Fact Check Log",
        "",
        f"**Score:** {factcheck_score}/100",
        "",
    ]

    if factcheck_verified:
        lines += [
            "**Verified Claims:**",
            "",
            "| Page | Claim |",
            "|------|-------|",
        ]
        for vc in factcheck_verified:
            page = vc.get("page_no", "?") if isinstance(vc, dict) else "?"
            claim = vc.get("claim", "") if isinstance(vc, dict) else str(vc)
            lines.append(f"| ✅ page {page} | {claim} |")
        lines.append("")

    if factcheck_findings:
        lines += ["**Unverified / Erroneous Claims:**", ""]
        lines += [
            "| Type | Page | Description |",
            "|------|------|-------------|",
        ]
        for f in factcheck_findings:
            desc = f.get("description", "")[:120]
            location = f.get("location", "")
            category = f.get("category", "")
            lines.append(f"| ❌ {category} | {location} | {desc} |")
        lines.append("")
    elif not factcheck_verified:
        lines += [
            "**Result:** No factual errors detected — all verifiable claims passed inspection.",
            "",
        ]

    if factcheck_reasoning:
        lines += ["**Evaluation Reasoning:**", "", factcheck_reasoning, ""]

    lines += [
        "---",
        "",
        "### 5. Accuracy / Fabrication Risk",
        "",
        f"**Risk Level:** {fabrication_risk_level}",
        f"**Risk Percentage:** {fabrication_risk_pct}%",
        f"**Authenticity Score:** {auth_score}/100",
        "",
    ]

    if auth_findings:
        lines += ["**Red Flags Detected:**", ""]
        for f in auth_findings:
            lines.append(
                f"- **[{f['severity']}]** `{f['category']}` — {f['description']} *({f['location']})*"
            )
        lines.append("")
    else:
        lines += ["**Red Flags:** None detected.", ""]

    if auth_reasoning:
        lines += ["**Evaluation Reasoning:**", "", auth_reasoning, ""]

    lines += [
        "---",
        "",
        f"## Final Verdict: {verdict_icon} {verdict.value}",
        "",
        detailed_reasoning or f"Overall weighted score: {overall_score}/100.",
        "",
        "---",
        "",
        f"*Generated by Research Validator AI · {timestamp}*",
    ]

    return "\n".join(lines)
