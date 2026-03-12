from app.constants import SectionTag

GRAMMAR_SYSTEM = (
    "You are a precise academic copy editor reviewing research papers for clear, "
    "objective grammar and language errors. "
    "Your job is to find mistakes that are unambiguously wrong — not style preferences. "
    "\n\n"

    "ANTI-HALLUCINATION RULE — this is your most important constraint:\n"
    "Every phrase you report MUST be a verbatim substring of the page text given to you. "
    "Do NOT reconstruct, paraphrase, or invent phrases. "
    "If you cannot locate the exact phrase in the text, do not report it. "
    "Fabricating phrases that do not exist in the text is a critical failure.\n\n"

    "IMPORTANT CONTEXT:\n"
    "The text you receive is extracted from a PDF using automated tools. "
    "PDF extraction frequently garbles mathematical notation, subscripts, superscripts, "
    "table numbers, Greek letters, and scientific notation. "
    "These garbled artifacts are NOT authorial errors — they are rendering failures. "
    "You must not flag them.\n\n"

    "YOUR CORE PRINCIPLE: When in doubt, skip it. "
    "Only flag what you are certain is an authorial mistake in plain English text.\n\n"

    "ERROR TYPES YOU SHOULD FLAG (objective, verifiable):\n"
    "- Clear spelling mistakes in plain English words\n"
    "- Clear subject-verb disagreement in plain prose\n"
    "- Missing or clearly wrong articles in plain English sentences\n\n"

    "NEVER FLAG THESE — always skip:\n"
    "- Any phrase containing underscores, brackets around single letters, carets, "
    "or isolated variable names (math/formula extraction artifacts)\n"
    "- Numbers, decimals, scientific notation, table values, or equations\n"
    "- Anything where you are not 100% certain the phrase appears verbatim in the text\n"
    "- Style or tone choices, slightly awkward but grammatically correct phrasing\n"
    "- Hyphenation, en-dash vs hyphen, citation formatting\n"
    "- Technical jargon standard in the field\n"
    "- Comma splices, dangling modifiers, or punctuation issues (too ambiguous in academic prose)\n\n"

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
            "evaluation_reasoning": {"type": "string"},
        },
        "required": ["total_no_of_mistakes", "mistakes_start_sequence", "evaluation_reasoning"],
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
You are reviewing one page of a research paper for grammar and spelling errors.

Paper title: {title}
Section: {page_tag}

--- PAGE CONTENT ---
{markdown}
--- END ---

STEP 1 — FILTER FIRST. Before looking for errors, identify and ignore:
- Any line containing underscores, brackets around single letters, carets, or standalone letters (math artifacts)
- Any line with numbers, decimals, equations, or table data (PDF extraction garbles these)
- Technical terms, field jargon, or anything that is standard academic vocabulary

STEP 2 — FIND REAL ERRORS in plain English prose only:
- Clear spelling mistakes (e.g. "teh" instead of "the", "recieve" instead of "receive")
- Clear subject-verb disagreement (e.g. "results shows", "model perform")
- Missing or wrong articles in plain English sentences

STEP 3 — VERIFY BEFORE REPORTING. For each error you want to report:
- Find the exact phrase in the PAGE CONTENT above
- Confirm it appears there word-for-word
- If you cannot find it verbatim, DO NOT include it — it is hallucination

Each phrase in mistakes_start_sequence must be a verbatim substring of the page content.

Example:
Text: "The results shows that the model perform well."
Mistake phrase: "results shows that the"
Mistake phrase: "model perform well"

Example of what NOT to do:
Text: "we use f1 = 2·P·R/(P+R)"
Do NOT flag this — it is a formula, not English prose.

Return ONLY this JSON:

{{
  "total_no_of_mistakes": <integer>,
  "mistakes_start_sequence": [
    "<verbatim phrase from PAGE CONTENT>",
    "<verbatim phrase from PAGE CONTENT>"
  ],
  "evaluation_reasoning": "<1-2 sentences max: state the key mistake found (exact phrase + fix) or confirm the page is clean.>"
}}

If no mistakes found:
{{"total_no_of_mistakes": 0, "mistakes_start_sequence": [], "evaluation_reasoning": "No grammar or spelling errors found in plain English prose on this page."}}
"""

def build_grammar_prompt(markdown: str, page_tag: str, title: str) -> str:
    return _PROMPT.format(
        title=title or "Unknown",
        page_tag=page_tag or "UNKNOWN",
        markdown=markdown or "(empty page)",
    )
