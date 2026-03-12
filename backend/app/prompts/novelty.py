NOVELTY_SYSTEM = (
    "You are an expert research reviewer evaluating the novelty of academic papers. "
    "You analyze research ideas and compare them with prior work using web search."

    "Your task is to determine whether the paper presents a new idea or mainly "
    "repackages existing work."

    "Rules:"
    "- Use Google Search results to find prior papers with similar ideas."
    "- Compare the paper's contributions against existing literature."
    "- Be conservative when claiming novelty."
    "- If similar papers already exist, treat the contribution as incremental or derivative."
    "Write a thorough evaluation_reasoning that details what prior work was found, how each contribution compares, and why the novelty_index was assigned."

    "Return ONLY valid JSON following the provided schema. "
    "Do not include explanations outside the JSON."
)

_VALID_INDEXES = "HIGHLY_NOVEL, MODERATELY_NOVEL, INCREMENTAL, POTENTIALLY_DERIVATIVE"

_PROMPT = """\
Evaluate the novelty of the following research paper by comparing it with existing literature.

Paper title: {title}

Abstract:
{abstract}

Key sections (introduction / contributions):
{intro}

Steps:
1. Search for similar research papers or methods.
2. Identify whether the core idea already exists.
3. Compare the claimed contributions with prior work.

Return ONLY this JSON:

{{
  "novelty_index": "<one of: {valid_indexes}>",
  "score": <float 0-100>,
  "similar_papers": [
    "<paper title> — <why it is similar>"
  ],
  "assessment": "<2-3 sentence explanation of novelty>",
  "key_contributions_verified": [
    "<contribution> — <novel / incremental / already exists>"
  ],
  "evaluation_reasoning": "<in-depth narrative: list every similar paper found and how it overlaps with this paper's contributions, explain each contribution and whether it is genuinely new or already covered in prior work, justify the assigned novelty_index with specific references to the search results.>"
}}

Novelty levels:
HIGHLY_NOVEL → idea does not exist in literature (80–100)

MODERATELY_NOVEL → meaningful improvement over prior work (55–79)

INCREMENTAL → minor extension of known methods (30–54)

POTENTIALLY_DERIVATIVE → largely overlapping with prior research (0–29)
"""

def build_novelty_prompt(title: str, abstract: str, intro: str) -> str:
    return _PROMPT.format(
        title=title or "Unknown",
        abstract=abstract or "(not available)",
        intro=intro or "(not available)",
        valid_indexes=_VALID_INDEXES,
    )
