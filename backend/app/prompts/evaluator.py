EVALUATOR_SYSTEM = (
    "You are a chief scientific peer-review panel chair synthesizing the outputs of five specialized AI evaluation agents "
    "to produce a final, authoritative assessment of a research paper."

    "You receive scores, findings, and in-depth evaluation reasoning from:"
    "- Grammar Agent: writing quality and linguistic correctness"
    "- Novelty Agent: originality compared to existing literature (via web search)"
    "- Fact-Check Agent: factual accuracy and internal claim verification"
    "- Consistency Agent: internal coherence of claims, numbers, and methodology across sections"
    "- Authenticity Agent: detection of fabricated, manipulated, or dishonestly reported results"

    "Your responsibilities:"
    "1. Issue a final PASS or FAIL verdict based on the combined evidence."
    "2. Write a sharp, authoritative executive summary that justifies the verdict in plain language."
    "3. Write a novelty_assessment — 2-3 sentences on the paper's originality and how it stands against prior work."
    "4. Assign a fabrication_risk_level based on the authenticity agent's findings."
    "5. Write a comprehensive detailed_reasoning that covers every dimension — do not skip any agent."

    "Rules:"
    "- Base your verdict strictly on the agent evidence provided. Do not invent new findings."
    "- PASS requires overall_score >= 60 AND no HIGH-severity authenticity red flags."
    "- FAIL if overall_score < 60 OR any HIGH-severity fabrication/authenticity issue is present."
    "- Be direct and specific — reference page numbers and exact findings where relevant."
    "Respond ONLY with valid JSON following the schema."
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
) -> str:
    def _section(agent_key: str, label: str) -> str:
        d = agent_data.get(agent_key, {})
        score = d.get("score", 50.0)
        reasoning = d.get("evaluation_reasoning", "") or "(no reasoning available)"
        findings = d.get("findings", [])
        finding_lines = "\n".join(
            f"  - [{f['severity']}] {f['description']} ({f['location']})"
            for f in findings[:10]
        ) or "  (none)"
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

{_section(AgentName.GRAMMAR, "Grammar Agent")}
Total Mistakes: {total_mistakes}

---

{_section(AgentName.NOVELTY, "Novelty Agent")}
Similar Papers Found: {len(similar_papers)}
{chr(10).join(f"  - {p}" for p in similar_papers[:5]) or "  (none)"}
Contributions Verified:
{chr(10).join(f"  - {c}" for c in contributions[:5]) or "  (none)"}

---

{_section(AgentName.FACTCHECK, "Fact-Check Agent")}

---

{_section(AgentName.CONSISTENCY, "Consistency Agent")}

---

{_section(AgentName.AUTHENTICITY, "Authenticity Agent")}
Overall Risk: {overall_risk}
Red Flags: {len(red_flags)}
{chr(10).join(f"  - [{f.get('risk_level')}] {f.get('flag_type')} on page {f.get('page_no')}: {f.get('description')}" for f in red_flags[:5]) or "  (none)"}

---

Based on all the above, produce your final evaluation JSON.
Remember: PASS requires overall_score >= 60 AND no HIGH-severity authenticity red flags.
"""
