CONSISTENCY_SYSTEM = (
    "You are a rigorous peer reviewer performing an internal consistency audit of a research paper. "
    "You compare claims, numbers, and methodology descriptions across sections to detect contradictions."

    "Rules:"
    "- Only flag contradictions you are confident about."
    "- Do not flag vague or ambiguous statements."
    "- Cross-reference specific claims from different pages."
    "Write a thorough evaluation_reasoning that covers every inconsistency found, referencing the exact pages involved and explaining the contradiction in detail."
    "Respond ONLY with valid JSON following the schema."
)

CONSISTENCY_JSON_SCHEMA: dict = {
    "name": "consistency_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "page_nos": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "description": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["HIGH", "MEDIUM", "LOW"],
                        },
                    },
                    "required": ["page_nos", "description", "severity"],
                    "additionalProperties": False,
                },
            },
            "evaluation_reasoning": {"type": "string"},
        },
        "required": ["issues", "evaluation_reasoning"],
        "additionalProperties": False,
    },
}

_PROMPT = """\
You are performing an internal consistency audit of a research paper.

Paper title: {title}

Your job is to detect contradictions or inconsistencies between different sections/pages of this paper.

Look for:
- Same metric reported with different values on different pages
- Methodology described differently in different sections
- Dataset sizes or splits that differ across pages
- Claims in the introduction that are not supported or contradicted by results
- Figures, tables, or numbers that conflict with surrounding text

--- METHODOLOGY PAGES ---
{methodology}
--- END ---

--- RESULTS PAGES ---
{results}
--- END ---

Return ONLY this JSON:
{{
  "issues": [
    {{
      "page_nos": [<page numbers involved>],
      "description": "<what is inconsistent and how>",
      "severity": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "evaluation_reasoning": "<in-depth narrative covering every inconsistency found: for each, reference the exact pages, quote or paraphrase the conflicting claims, and explain why they contradict each other. If no issues found, explain what cross-references were checked and why they are consistent.>"
}}

Severity:
- HIGH: directly contradicts a core result or claim
- MEDIUM: inconsistency that affects interpretation
- LOW: minor wording or formatting inconsistency

If no inconsistencies found, return: {{"issues": [], "evaluation_reasoning": "<explanation of what was cross-checked and why the paper is internally consistent>"}}
"""


def build_consistency_prompt(title: str, methodology_pages: list[dict], results_pages: list[dict]) -> str:
    def _fmt(pages: list[dict]) -> str:
        if not pages:
            return "(not available)"
        return "\n\n".join(
            f"[Page {p['page_num']}]\n{p.get('page_summary', '')}\n{p.get('image_data', '')}"
            for p in pages
        ).strip()

    return _PROMPT.format(
        title=title or "Unknown",
        methodology=_fmt(methodology_pages),
        results=_fmt(results_pages),
    )
