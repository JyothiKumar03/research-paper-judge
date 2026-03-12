NOVELTY_SYSTEM = (
    "You are an expert research reviewer evaluating the novelty of academic papers. "
    "Your role is to determine whether the paper presents a genuinely new contribution "
    "or mainly repackages existing work.\n\n"
 
    "CRITICAL TEMPORAL RULE:\n"
    "Prior work is ONLY work published STRICTLY BEFORE the paper's own publication date. "
    "Any paper, tool, dataset, blog post, or GitHub project published on or after the "
    "paper's publish_date is NOT prior work and must never appear in similar_papers. "
    "If you cannot verify a publication date, skip that source entirely.\n\n"
 
    "SEARCH QUALITY RULES:\n"
    "- Use Google Search to find prior work that directly overlaps the core METHOD, "
    "not just the application domain or motivation.\n"
    "- Surface only works with a clear, direct technical overlap with the specific "
    "approach described — not works that are merely in the same field.\n"
    "- Separately note whether each similar paper is cited by the authors or was "
    "NOT cited by them. Undisclosed overlap is the meaningful signal.\n"
    "- 3–6 well-chosen comparisons are better than 10 superficial ones.\n\n"
 
    "WHAT NOT TO FLAG AS PRIOR WORK:\n"
    "- GitHub repos, product pages, or commercial tools with no peer-reviewed publication\n"
    "- Post-publication projects even if they use a similar approach\n"
    "- Works that share only motivation or dataset, not the core method\n"
    "- Works the authors already cite — these are expected and not surprising\n\n"
 
    "Return ONLY valid JSON following the provided schema. "
    "Do not include explanations outside the JSON."
)
 

_VALID_INDEXES = "HIGHLY_NOVEL, MODERATELY_NOVEL, INCREMENTAL, POTENTIALLY_DERIVATIVE"

_PROMPT = """\
Evaluate the novelty of the following research paper by searching for and comparing \
prior work published BEFORE this paper's publication date.
 
Paper title: {title}
Paper URL: {paper_url}
Publication date: {publish_date}
 
Abstract:
{abstract}
 
Key sections (introduction / contributions / related work):
{intro}
 
=== YOUR TASK ===
 
Step 1 — ANCHOR YOUR SEARCH TEMPORALLY
All prior work you search for must have been published before: {publish_date}
Do not cite anything published on or after this date as prior work.
 
Step 2 — SEARCH FOR DIRECT METHODOLOGICAL OVERLAP
Search for papers that:
- Use the same or very similar core technique (not just the same domain)
- Address the same specific problem with a comparable approach
- Were published in peer-reviewed venues (conference or journal) before {publish_date}
 
Step 3 — CLASSIFY EACH SIMILAR PAPER
For every similar paper found, determine:
- Is it cited by the authors in this paper? (cited / not cited)
- Does it overlap the core method, or only the domain/motivation?
- What specifically overlaps, and what is genuinely different?
 
Step 4 — ASSESS CONTRIBUTIONS
For each claimed contribution, determine whether it is:
- novel: does not exist in prior literature before {publish_date}
- incremental: meaningfully extends a known approach
- already exists: essentially the same idea exists in prior work
 
Step 5 — ASSIGN NOVELTY INDEX
Use only these levels:
  HIGHLY_NOVEL           → core idea does not exist in pre-{publish_date} literature (score 80–100)
  MODERATELY_NOVEL       → meaningful new contribution over prior work (score 55–79)
  INCREMENTAL            → minor extension of known methods (score 30–54)
  POTENTIALLY_DERIVATIVE → core idea largely exists in prior work (score 0–29)
 
Return ONLY this JSON (no text outside the JSON):
 
{{
  "novelty_index": "<one of: {valid_indexes}>",
  "score": <float 0.0–100.0>,
  "similar_papers": [
    {{
      "title": "<exact paper title>",
      "venue": "<conference or journal name>",
      "year": <publication year as integer>,
      "url": "<URL if found, else null>",
      "cited_by_authors": <true | false>,
      "overlap_summary": "<1–2 sentences: what specifically overlaps and what is different>"
    }}
  ],
  "assessment": "<2–3 sentence summary of the paper's novelty position relative to prior work>",
  "key_contributions_verified": [
    {{
      "contribution": "<exact contribution as stated in the paper>",
      "verdict": "<novel | incremental | already exists>",
      "reasoning": "<1 sentence: what prior work covers this, if any>"
    }}
  ],
  "evaluation_reasoning": "<1-2 sentences max: state the novelty verdict and the single most important prior work overlap (or confirm no overlap found).>"
}}
"""

def build_novelty_prompt(title: str, abstract: str, intro: str, paper_url: str = "", publish_date: str = "") -> str:
    return _PROMPT.format(
        title=title or "Unknown",
        abstract=abstract or "(not available)",
        intro=intro or "(not available)",
        valid_indexes=_VALID_INDEXES,
        paper_url=paper_url or "(not available)",
        publish_date=publish_date or "(not available)",
    )
