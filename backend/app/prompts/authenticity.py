AUTHENTICITY_SYSTEM = (
    "You are a careful, conservative research auditor. Your job is to flag only clear, "
    "unambiguous evidence of data fabrication or dishonest reporting — NOT normal academic "
    "limitations or common experimental practices.\n\n"

    "Core philosophy:\n"
    "- HIGH risk = smoking-gun contradictions only: results that are mathematically impossible, "
    "data explicitly contradicted by the paper's own method, or fabricated-looking digit patterns "
    "(e.g. every result is exactly X.00%). A missing error bar with a stated justification is NOT high risk.\n"
    "- MEDIUM risk = suspicious patterns that could have innocent explanations: selectively reported "
    "metrics, thin ablation coverage, or missing reproducibility details.\n"
    "- LOW risk = minor best-practice omissions that do not threaten result validity.\n\n"

    "Important: Absence of something (error bars, ablation, baseline) is LOW or MEDIUM unless the "
    "paper's own claims REQUIRE it and it is entirely absent with no justification. "
    "A paper that acknowledges a limitation is less suspicious than one that ignores it.\n\n"

    "Be conservative. Err toward NONE or LOW. Reserve HIGH for results that cannot be explained "
    "by honest experimental choices.\n\n"
    "Write evaluation_reasoning in 1-2 sentences max. Respond ONLY with valid JSON."
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
            "evaluation_reasoning": {"type": "string"},
        },
        "required": ["red_flags", "overall_risk", "evaluation_reasoning"],
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

## Flag types and when to use each

| Flag | Use ONLY when... | Do NOT flag if... |
|------|-----------------|-------------------|
| round_numbers | >80% of reported values end in .0 or .00 with no explanation | Some round values appear naturally |
| no_error_bars | Quantitative comparisons lack variance AND the paper gives no justification | Paper explains why (e.g. dominant systematic error, deterministic method) |
| no_ablation | Paper claims a novel design but provides zero component justification | Ablation is partial or informally described |
| cherry_picked | Paper explicitly reports only the single best metric while hiding worse ones | Paper uses standard metrics for the field |
| logical_leap | Claimed result is mathematically impossible given the described method | Result is merely surprising or impressive |
| missing_baseline | No comparison to ANY prior work despite directly claiming SOTA | Baseline exists but may not be the strongest |
| scale_mismatch | A minor change (e.g. 1 hyperparameter) is used to explain a 20%+ jump | Modest improvement from a meaningful change |
| p_hacking | Multiple hypothesis tests with no correction and borderline p-values throughout | Single clean statistical test |
| no_reproducibility | Key hyperparameters, datasets, or code are entirely withheld | Standard details present; minor gaps remain |

## Risk level rules
- HIGH: Only when the finding directly implies the result could not have been obtained honestly.
  Use sparingly — most papers should score MEDIUM or lower.
- MEDIUM: Suspicious but explainable. Warrants scrutiny, not accusation.
- LOW: Minor omission. Does not threaten validity.

## Output
Return ONLY this JSON:
{{
  "red_flags": [
    {{
      "flag_type": "<one of the flag types above>",
      "page_no": <page number where evidence appears>,
      "description": "<specific observation — quote or cite the exact text/number that triggered this flag>",
      "risk_level": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "overall_risk": "HIGH" | "MEDIUM" | "LOW" | "NONE",
  "evaluation_reasoning": "<1-2 sentences: name the single most critical finding (page + observation), or confirm no suspicious patterns detected.>"
}}

overall_risk rules:
- NONE: zero flags
- LOW: only LOW flags
- MEDIUM: at least one MEDIUM flag, no HIGH
- HIGH: at least one HIGH flag AND it is a clear logical impossibility or direct self-contradiction in the paper

If no red flags found: {{"red_flags": [], "overall_risk": "NONE", "evaluation_reasoning": "No authenticity red flags detected."}}
"""


def build_authenticity_prompt(title: str, results_pages: list[dict], methodology_pages: list[dict]) -> str:
    def _fmt(pages: list[dict]) -> str:
        if not pages:
            return "(not available)"
        parts = []
        for p in pages:
            block = f"[Page {p['page_num']}]"
            if p.get("markdown", "").strip():
                block += f"\nPage text:\n{p['markdown'].strip()}"
            if p.get("image_data", "").strip():
                block += f"\nExtracted figures/tables data: {p['image_data'].strip()}"
            parts.append(block)
        return "\n\n".join(parts).strip()

    return _PROMPT.format(
        title=title or "Unknown",
        results=_fmt(results_pages),
        methodology=_fmt(methodology_pages),
    )
