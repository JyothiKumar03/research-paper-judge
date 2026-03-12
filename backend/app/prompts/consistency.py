CONSISTENCY_SYSTEM = (
    "You are a rigorous peer reviewer performing an internal consistency audit of a "
    "research paper. Your job is to detect genuine contradictions between different "
    "sections — claims that cannot both be true simultaneously.\n\n"

    "WHAT COUNTS AS A REAL INCONSISTENCY:\n"
    "- A specific number stated in prose (abstract, intro, conclusion) that directly "
    "contradicts the same number in a results table or another prose section\n"
    "- A dataset size, split ratio, or label count claimed differently in two separate "
    "prose statements\n"
    "- A methodology described in one section that is structurally incompatible with "
    "how it is described in another section\n"
    "- A conclusion that claims X when the results clearly show not-X\n\n"

    "WHAT IS NOT AN INCONSISTENCY — never flag these:\n"
    "- Different rows in an ablation table or architecture search table showing "
    "different performance numbers. These are intentional comparisons.\n"
    "- An intermediate result (e.g. a baseline or early model in a search) that is "
    "lower than the final result. Papers deliberately show this progression.\n"
    "- A number visible in a figure/plot that differs from a prose count, UNLESS "
    "the paper explicitly claims the figure defines that count.\n"
    "- A performance difference the paper's own text already explains. "
    "If the paper reconciles it, it is not a contradiction.\n"
    "- Minor wording differences that do not change meaning\n\n"

    "BEFORE FLAGGING ANYTHING:\n"
    "Read the surrounding context of both conflicting statements. If the paper itself "
    "explains the difference anywhere in the text, do NOT flag it.\n\n"

    "HIGH SEVERITY RULE — only mark HIGH if ALL three are true:\n"
    "1. You can quote the exact conflicting text from BOTH pages verbatim.\n"
    "2. The conflict involves a core claim (final result, central methodology, "
    "primary dataset size) — not a footnote, intermediate step, or minor detail.\n"
    "3. There is NO explanation anywhere in the paper for the difference.\n"
    "If you cannot satisfy all three, use MEDIUM or LOW.\n\n"

    "SEVERITY CALIBRATION:\n"
    "HIGH: Abstract claims weighted F1 of 97%, Results table final row shows 84%, "
    "no explanation given anywhere.\n"
    "MEDIUM: Dataset section says 2,940 pages, experiment section says 3,695 pages, "
    "no explanation.\n"
    "LOW: Introduction says 'more than 10 labels', methodology says exactly 17 — "
    "directionally consistent, minor precision difference.\n\n"

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

Your job is to detect genuine contradictions between different pages.
A contradiction means two statements that cannot both be true simultaneously,
where the paper does not itself explain the difference.

=== GROUND RULES ===

1. PROSE OVER PLOTS: Prose numbers are authoritative. Only flag figure-based
   counts if they directly contradict a prose claim with no explanation.

2. ABLATION / SEARCH TABLES ARE NOT CONTRADICTIONS: Different rows in the
   same table showing different scores are intentional — do NOT flag them.

3. CHECK CONTEXT BEFORE FLAGGING: If the paper explains the difference
   anywhere (different config, metric, split, intermediate result), skip it.

4. HIGH SEVERITY requires ALL THREE:
   - You can quote the exact conflicting text from both pages verbatim
   - The conflict involves a core claim (final result, primary method, main dataset)
   - No explanation exists anywhere in the paper
   If you cannot satisfy all three, use MEDIUM or LOW.

=== PAPER CONTENT (page by page) ===

{pages}

=== END OF PAPER ===

Return ONLY this JSON:
{{
  "issues": [
    {{
      "page_nos": [<both page numbers involved>],
      "description": "<verbatim quote from page A> vs <verbatim quote from page B> — explain why they conflict and confirm no author explanation exists>",
      "severity": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "evaluation_reasoning": "<1-2 sentences max: state the key contradiction found (pages + claim) or confirm the paper is internally consistent.>"
}}

If no inconsistencies found:
{{"issues": [], "evaluation_reasoning": "No internal inconsistencies found."}}
"""


def build_consistency_prompt(title: str, pages: list[dict]) -> str:
    if not pages:
        pages_text = "(no content available)"
    else:
        parts = []
        for p in pages:
            block = f"[Page {p['page_num']} | Section: {p.get('page_tag', 'UNKNOWN')}]"
            if p.get("page_summary", "").strip():
                block += f"\nSummary: {p['page_summary'].strip()}"
            if p.get("image_data", "").strip():
                block += f"\nFigures/tables data: {p['image_data'].strip()}"
            parts.append(block)
        pages_text = "\n\n".join(parts)

    return _PROMPT.format(
        title=title or "Unknown",
        pages=pages_text,
    )
