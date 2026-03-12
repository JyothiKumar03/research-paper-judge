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

- "page_summary": produce 3–5 concise, content-first sentences (declarative) describing the concepts, methods, numbers or claims on that page. **Do NOT** use navigation/meta phrases like "this page", "the page", "here", "on this page", "the figure shows", "the authors say". Start sentences with concepts or results (e.g. "The Transformer uses...", "Experiments report...").
- Keep "page_summary" mergeable with other summaries — write as if it's a paragraph inside a unified paper summary.
- Include exact numeric values, units, dataset names, metrics and hyperparameters when present.
- "image_data": for pages with figures/tables, extract all table headers, all rows and numeric cells, axis labels and ranges for plots, legend entries and notable data points or trends, and equations/variable relationships. If there are no visuals, set image_data to "".
- For vision prompts, use both the provided markdown and the image to extract information. For text-only prompts do not invent image data — image_data must be "".
- IF THERE ARE TABLES, OR TABULAR DATA, ALWAYS RETURN THEM IN A STRUCTURED MARKDOWN FORMAT!!!
- If uncertain about tag choose "OTHER". Do not invent authors/affiliations unless clearly present in the text.
- The JSON must not contain additional keys and must be parseable by strict JSON validators.
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

- "page_summary": produce 3–5 concise, content-first sentences (declarative) describing the concepts, methods, numbers or claims on that page. **Do NOT** use navigation/meta phrases like "this page", "the page", "here", "on this page", "the figure shows", "the authors say". Start sentences with concepts or results (e.g. "The Transformer uses...", "Experiments report...").
- Keep "page_summary" mergeable with other summaries — write as if it's a paragraph inside a unified paper summary.
- Include exact numeric values, units, dataset names, metrics and hyperparameters when present.
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
