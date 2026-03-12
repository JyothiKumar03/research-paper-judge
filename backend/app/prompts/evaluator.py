EVALUATOR_SYSTEM = (
    "You are the chief scientific peer-review panel chair. "
    "You receive CLEAN, HIGH-QUALITY summaries from five agents. "
    "Your ONLY job: (1) decide PASS/FAIL first, then (2) write a short, sharp report. "

    "You receive:"
    "- Grammar Agent (writing quality)"
    "- Novelty Agent (originality)"
    "- Fact-Check Agent (factual accuracy)"
    "- Consistency Agent (internal coherence)"
    "- Authenticity Agent (fabrication risk)"

    "Workflow (follow exactly):"
    "1. Decide verdict immediately using the rules below."
    "2. Write executive_summary (max 4 sentences)."
    "3. Write novelty_assessment (exactly 2-3 sentences)."
    "4. Set fabrication_risk_level."
    "5. Write detailed_reasoning as ONE short paragraph per agent (max 70 words each), citing only critical issues + page numbers."

    "Rules:"
    "- Base everything strictly on the provided agent data. Never invent findings."
    "- PASS = overall_score >= 60 AND no HIGH-severity authenticity red flags."
    "- FAIL = overall_score < 60 OR any HIGH-severity authenticity issue."
    "- Be direct, specific, and concise. Reference severity/page only when relevant."
    "- Output ONLY valid JSON. No extra text."
)

EVALUATOR_JSON_SCHEMA: dict = {
    "name": "evaluator_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "executive_summary": {"type": "string"},
            "novelty_assessment": {"type": "string"},
            "fabrication_risk_level": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW", "NONE"],
            },
            "detailed_reasoning": {"type": "string"},
        },
        "required": [
            "verdict",
            "executive_summary",
            "novelty_assessment",
            "fabrication_risk_level",
            "detailed_reasoning",
        ],
        "additionalProperties": False,
    },
}


def build_evaluator_prompt(
    title: str,
    agent_data: dict,
    overall_score: float,
    grammar_rating: str,
    novelty_label: str,
    fabrication_risk_pct: float,
    include_grammar_sequences: bool = True,
) -> str:
    def _section(agent_key: str, label: str, strip_sequences: bool = False) -> str:
        d = agent_data.get(agent_key, {})
        score = d.get("score", 50.0)
        reasoning = d.get("evaluation_reasoning", "") or "NO DATA FROM THIS AGENT"
        findings = d.get("findings", [])
        finding_lines_parts = []
        for f in findings[:10]:
            desc = f["description"]
            if strip_sequences and ":" in desc:
                # keep only the part before the sequence list, e.g. "5 mistake(s)"
                desc = desc[: desc.index(":")].strip()
            finding_lines_parts.append(f"  - [{f['severity']}] {desc} ({f['location']})")
        finding_lines = "\n".join(finding_lines_parts) or "  NO DATA FROM THIS AGENT"
        return (
            f"### {label}\n"
            f"Score: {score}/100\n"
            f"Findings:\n{finding_lines}\n"
            f"Evaluation Reasoning:\n{reasoning}"
        )

    from app.constants import AgentName

    grammar_raw = agent_data.get(AgentName.GRAMMAR, {}).get("raw", {})
    total_mistakes = grammar_raw.get("total_mistakes", 0)

    novelty_raw = agent_data.get(AgentName.NOVELTY, {}).get("raw", {})
    novelty_index = novelty_raw.get("novelty_index", "INCREMENTAL")
    similar_papers = novelty_raw.get("similar_papers", [])
    contributions = novelty_raw.get("contributions", [])

    auth_raw = agent_data.get(AgentName.AUTHENTICITY, {}).get("raw", {})
    overall_risk = auth_raw.get("overall_risk", "NONE")
    red_flags = auth_raw.get("red_flags", [])

    return f"""\
You are producing the final evaluation report for the following research paper.

Paper title: {title}
Computed Overall Score (weighted): {overall_score}/100
Grammar Rating (derived): {grammar_rating}
Novelty Index: {novelty_index} — {novelty_label}
Fabrication Risk Estimate: {fabrication_risk_pct}%

---

{_section(AgentName.GRAMMAR, "Grammar Agent", strip_sequences=not include_grammar_sequences)}
Total Mistakes: {total_mistakes}

---

{_section(AgentName.NOVELTY, "Novelty Agent")}
Similar Papers Found: {len(similar_papers)}
{chr(10).join(f"  - {p}" for p in similar_papers[:5]) or "  NO DATA FROM THIS AGENT"}
Contributions Verified:
{chr(10).join(f"  - {c}" for c in contributions[:5]) or "  NO DATA FROM THIS AGENT"}

---

{_section(AgentName.FACTCHECK, "Fact-Check Agent")}

---

{_section(AgentName.CONSISTENCY, "Consistency Agent")}

---

{_section(AgentName.AUTHENTICITY, "Authenticity Agent")}
Overall Risk: {overall_risk}
Red Flags: {len(red_flags)}
{chr(10).join(f"  - [{f.get('risk_level')}] {f.get('flag_type')} on page {f.get('page_no')}: {f.get('description')}" for f in red_flags[:5]) or "  NO DATA FROM THIS AGENT"}

---

Based on all the above, produce your final evaluation JSON.
Remember: PASS requires overall_score >= 60 AND no HIGH-severity authenticity red flags.
"""
