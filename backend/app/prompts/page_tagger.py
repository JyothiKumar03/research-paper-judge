from app.constants import SectionTag

_VALID_TAGS = "  " + ", ".join(t.value for t in SectionTag)

PAGE_TAG_SYSTEM = (
    "You are a research paper section classifier. "
    "Respond ONLY with valid JSON — no prose, no markdown fences, no explanation."
)

# JSON schema for structured output — sent as response_format to OpenRouter.
# Models that support it will return guaranteed-valid JSON matching this schema.
# Models that don't support it will ignore it; the JSON parser handles those.
PAGE_TAG_JSON_SCHEMA: dict = {
    "name": "page_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "page_tag":    {"type": "string", "enum": [t.value for t in SectionTag]},
            "page_summary": {"type": "string"},
            "image_data":  {"type": "string"},
        },
        "required": ["page_tag", "page_summary", "image_data"],
        "additionalProperties": False,
    },
}

# --- Vision prompt (page has tables / figures — screenshot sent alongside) ---
_PAGE_TAG_VISION_PROMPT = """\
You are given a screenshot of one page from a research paper, along with its extracted markdown text.

Use BOTH the image and the markdown to classify this page and extract all key data.

--- MARKDOWN TEXT ---
{markdown}
--- END ---

Return ONLY this JSON:
{{
  "page_tag": "<tag>",
  "page_summary": "<summary>",
  "image_data": "<extracted table and figure data>"
}}

Valid tags (choose exactly one):
{valid_tags}

Tag rules:
- TITLE → title, authors, affiliations
- ABSTRACT → abstract section
- INTRODUCTION → motivation, contributions, paper outline
- RELATED_WORK → prior work, literature review
- BACKGROUND → preliminaries, definitions, theory
- METHODOLOGY → model/algorithm design, architecture
- EXPERIMENTS → setup, datasets, hyperparameters, baselines
- RESULTS → performance tables, graphs, quantitative comparisons
- DISCUSSION → analysis, limitations, implications
- CONCLUSION → concluding remarks, future work
- REFERENCES → bibliography, citations
- APPENDIX → supplementary material, proofs
- ACKNOWLEDGMENTS → funding, thanks
- OTHER → none of the above

page_summary: 3-5 sentences covering key ideas, methods, and claims on this page. It should be captured in such a way that if someone sees it, they should get the whole idea!
image_data: Read the image carefully. Extract ALL essential data from tables and figures:
  - Table: column headers, row labels, every numeric cell value
  - Graph/plot: axis labels, axis ranges, legend entries, key data point values or trends
  - Equation/diagram: variable names, relationships described
  If the page has no tables or figures, set image_data to "".
"""

# --- Text prompt (page has no visual content — markdown only) ---
_PAGE_TAG_TEXT_PROMPT = """\
You are given one page from a research paper in markdown format.

Classify this page and summarise its content.

--- PAGE CONTENT ---
{markdown}
--- END ---

Return ONLY this JSON:
{{
  "page_tag": "<tag>",
  "page_summary": "<summary>",
  "image_data": ""
}}

Valid tags (choose exactly one):
{valid_tags}

Tag rules:
- TITLE → title, authors, affiliations
- ABSTRACT → abstract section
- INTRODUCTION → motivation, contributions, paper outline
- RELATED_WORK → prior work, literature review
- BACKGROUND → preliminaries, definitions, theory
- METHODOLOGY → model/algorithm design, architecture
- EXPERIMENTS → setup, datasets, hyperparameters, baselines
- RESULTS → performance tables, graphs, quantitative comparisons
- DISCUSSION → analysis, limitations, implications
- CONCLUSION → concluding remarks, future work
- REFERENCES → bibliography, citations
- APPENDIX → supplementary material, proofs
- ACKNOWLEDGMENTS → funding, thanks
- OTHER → none of the above

page_summary: 3-5 sentences covering key ideas, formulas, numbers, and claims on this specific page.
image_data: always "" for text-only pages.
"""


def build_vision_prompt(markdown: str) -> str:
    return _PAGE_TAG_VISION_PROMPT.format(
        markdown=markdown or "(empty page)",
        valid_tags=_VALID_TAGS,
    )


def build_text_prompt(markdown: str) -> str:
    return _PAGE_TAG_TEXT_PROMPT.format(
        markdown=markdown or "(empty page)",
        valid_tags=_VALID_TAGS,
    )
