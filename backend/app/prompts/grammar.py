from app.constants import SectionTag

GRAMMAR_SYSTEM = (
    "You are a strict academic copy editor who reviews research papers for grammar and clarity issues. "
    "You detect spelling mistakes, grammar errors, punctuation issues, and awkward phrasing."

    "Your task is to identify the exact location of each mistake in the text."

    "Rules:"
    "- For every mistake, return a SHORT exact phrase from the text (about 3–5 words) that contains the mistake."
    "- The phrase MUST appear verbatim in the text."
    "- The phrase should include the mistake itself so it can be highlighted."
    "- Do not return explanations."

    "Respond ONLY with valid JSON that follows the schema."
)

GRAMMAR_JSON_SCHEMA: dict = {
    "name": "grammar_check",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "total_no_of_mistakes": {"type": "integer"},
            "mistakes_start_sequence": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["total_no_of_mistakes", "mistakes_start_sequence"],
        "additionalProperties": False,
    },
}

_SKIP_TAGS: frozenset[SectionTag] = frozenset({
    SectionTag.REFERENCES,
    SectionTag.ACKNOWLEDGMENTS,
    SectionTag.APPENDIX,
    SectionTag.TITLE,
    SectionTag.OTHER,
})

_PROMPT = """\
You are reviewing one page of a research paper for grammar and writing issues.

Paper title: {title}
Section: {page_tag}

--- PAGE CONTENT ---
{markdown}
--- END ---

Find all issues related to:
- Grammar mistakes
- Spelling errors
- Punctuation mistakes
- Informal wording
- Awkward or unclear phrasing

For each mistake:
- Extract a SHORT phrase (3–5 words) from the text that contains the mistake.
- The phrase must be copied EXACTLY from the page content.
- The mistake should appear inside this phrase.

Example:
Text: "hii, how are u? I'm god, what about you?"
Mistake phrase: "u? I'm god"

Return ONLY this JSON:

{{
  "total_no_of_mistakes": <integer>,
  "mistakes_start_sequence": [
    "<exact phrase containing the mistake>",
    "<exact phrase containing the mistake>"
  ]
}}

Rules:
- Each phrase must appear exactly in the text.
- Each phrase should be short (3–5 words).
- If no mistakes exist, return:
  {{"total_no_of_mistakes": 0, "mistakes_start_sequence": []}}
"""

def build_grammar_prompt(markdown: str, page_tag: str, title: str) -> str:
    return _PROMPT.format(
        title=title or "Unknown",
        page_tag=page_tag or "UNKNOWN",
        markdown=markdown or "(empty page)",
    )
