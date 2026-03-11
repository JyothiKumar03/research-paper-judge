AUTHENTICITY_SYSTEM = (
    "You are a fraud detection specialist reviewing research papers for signs of data manipulation, "
    "result fabrication, and reporting dishonesty."

    "You think like a statistical auditor:"
    "- Suspicious patterns in results (too clean, too perfect)"
    "- Missing error bars, confidence intervals, or variance"
    "- No ablation study or controlled comparison"
    "- Cherry-picked baselines or metrics"
    "- Logical gaps between method and claimed results"

    "Be conservative. Only flag clear, specific red flags — not vague concerns."
    "Respond ONLY with valid JSON following the schema."
)

AUTHENTICITY_JSON_SCHEMA: dict = {
    "name": "authenticity_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "red_flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "flag_type": {
                            "type": "string",
                            "enum": [
                                "too_perfect",
                                "round_numbers",
                                "no_error_bars",
                                "no_ablation",
                                "cherry_picked",
                                "logical_leap",
                                "missing_baseline",
                                "scale_mismatch",
                                "p_hacking",
                                "no_reproducibility",
                            ],
                        },
                        "page_no": {"type": "integer"},
                        "description": {"type": "string"},
                        "risk_level": {
                            "type": "string",
                            "enum": ["HIGH", "MEDIUM", "LOW"],
                        },
                    },
                    "required": ["flag_type", "page_no", "description", "risk_level"],
                    "additionalProperties": False,
                },
            },
            "overall_risk": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW", "NONE"],
            },
        },
        "required": ["red_flags", "overall_risk"],
        "additionalProperties": False,
    },
}

_PROMPT = """\
You are auditing a research paper for signs of data fabrication, manipulation, or dishonest reporting.

Paper title: {title}

--- RESULTS PAGES ---
{results}
--- END ---

--- METHODOLOGY PAGES ---
{methodology}
--- END ---

Identify red flags that suggest the results may not be trustworthy:

Flag types:
- too_perfect: results are suspiciously clean, no noise or variance
- round_numbers: all results are suspiciously round (e.g. 90.0%, 50.0%)
- no_error_bars: performance results lack standard deviations or confidence intervals
- no_ablation: no ablation study justifying design choices
- cherry_picked: only favorable metrics shown, unfavorable omitted
- logical_leap: results do not logically follow from the method described
- missing_baseline: no comparison to obvious or standard baselines
- scale_mismatch: claimed improvement does not match scale of described changes
- p_hacking: statistical results that suggest selective hypothesis testing
- no_reproducibility: insufficient detail to reproduce experiments

Return ONLY this JSON:
{{
  "red_flags": [
    {{
      "flag_type": "<one of the flag types above>",
      "page_no": <page number>,
      "description": "<specific observation>",
      "risk_level": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "overall_risk": "HIGH" | "MEDIUM" | "LOW" | "NONE"
}}

If no red flags found, return: {{"red_flags": [], "overall_risk": "NONE"}}
"""


def build_authenticity_prompt(title: str, results_pages: list[dict], methodology_pages: list[dict]) -> str:
    def _fmt(pages: list[dict]) -> str:
        if not pages:
            return "(not available)"
        return "\n\n".join(
            f"[Page {p['page_num']}]\n{p.get('page_summary', '')}\n{p.get('image_data', '')}"
            for p in pages
        ).strip()

    return _PROMPT.format(
        title=title or "Unknown",
        results=_fmt(results_pages),
        methodology=_fmt(methodology_pages),
    )
