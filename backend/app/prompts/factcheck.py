FACTCHECK_SYSTEM = (
    "You are an expert scientific fact-checker and peer reviewer specializing in auditing research papers. "
    "You verify claims against established scientific knowledge, mathematical correctness, and internal consistency. "
    "Your job is NOT to summarize the paper, but to audit factual claims — identifying which are correct and which are wrong."

    "You think like a rigorous journal reviewer (e.g., NeurIPS / IEEE reviewer):"
    "- Carefully verify numerical values, formulas, definitions, and scientific claims."
    "- Detect contradictions between different sections or pages."
    "- Flag claims that violate well-known scientific principles."

    "Rules you MUST follow:"
    "- Only report errors when you are highly confident they are incorrect."
    "- Only add a claim to verified_claims when you have actively checked it and confirmed it is correct."
    "- Do NOT add trivial or obvious statements to verified_claims — only non-trivial checkable facts."
    "- Do NOT flag stylistic issues, vague statements, or missing citations."
    "- Do NOT speculate about the author's intent."
    "- If information is incomplete but not provably wrong, ignore it."
    "Write a concise evaluation_reasoning in 1-2 sentences max: state only the most critical error found (page + claim) or confirm no errors were found. No lengthy walk-throughs."

    "Your output MUST be strictly valid JSON that follows the provided schema."
    "Do not include explanations outside the JSON."
)

FACTCHECK_JSON_SCHEMA: dict = {
    "name": "factcheck_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "verified_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "page_no": {"type": "integer"},
                    },
                    "required": ["claim", "page_no"],
                    "additionalProperties": False,
                },
            },
            "errors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "error_type": {
                            "type": "string",
                            "enum": ["mismatch", "false_claim"],
                        },
                        "page_no": {"type": "integer"},
                        "error_description": {"type": "string"},
                    },
                    "required": ["error_type", "page_no", "error_description"],
                    "additionalProperties": False,
                },
            },
            "evaluation_reasoning": {"type": "string"},
        },
        "required": ["verified_claims", "errors", "evaluation_reasoning"],
        "additionalProperties": False,
    },
}

_PROMPT = """\
You are performing a factual audit of a research paper using page-level keypoints and summaries.

Paper title: {title}

Your task is to audit factual claims in the paper — identifying which are verified correct and which are wrong.

Follow this evaluation process:

1. Review each page summary carefully.
2. Identify key non-trivial factual claims (numbers, formulas, scientific principles, benchmark values).
3. For each claim you can actively verify:
   - If it is correct → add to verified_claims
   - If it is clearly wrong → add to errors
4. Skip claims you cannot verify or that are vague/subjective.

Types of errors to detect:

1. false_claim
A statement that is factually incorrect based on well-established science, mathematics, or widely accepted knowledge.

Examples:
- Incorrect formulas
- Impossible statistical results
- Misstated scientific laws
- Wrong historical or benchmark values

2. mismatch
Two pages make contradictory claims about the same concept, result, or definition.

Examples:
- Different model architectures described for the same system
- Conflicting dataset sizes
- Inconsistent performance metrics

DO NOT report:
- Missing information
- Weak explanations
- Speculation
- Opinions
- Writing style issues

--- PAGE DATA ---
{summaries}
--- END ---

Return ONLY this JSON structure:

{{
  "verified_claims": [
    {{
      "claim": "<a non-trivial factual claim you checked and confirmed correct>",
      "page_no": <page number>
    }}
  ],
  "errors": [
    {{
      "error_type": "mismatch" or "false_claim",
      "page_no": <page number>,
      "error_description": "<clear explanation of the incorrect or contradictory claim>"
    }}
  ],
  "evaluation_reasoning": "<1-2 sentences max: state the most critical error found (page + claim) or confirm no factual errors were detected.>"
}}

Rules:
- If no clear errors are found, return errors as [].
- If no claims could be actively verified, return verified_claims as [].
- Do not invent errors or verified claims.
- Be conservative — only report clear facts.
"""

def build_factcheck_prompt(title: str, page_data: list[tuple[int, str, str]]) -> str:
    parts = []
    for page_no, summary, image_data in page_data:
        block = f"[Page {page_no}]"
        if summary.strip():
            block += f"\nSummary: {summary.strip()}"
        if image_data.strip():
            block += f"\nExtracted figures/tables data: {image_data.strip()}"
        parts.append(block)
    return _PROMPT.format(title=title or "Unknown", summaries="\n\n".join(parts))
