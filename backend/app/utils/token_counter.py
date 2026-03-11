"""
Token counting and text chunking utilities.

Uses tiktoken with cl100k_base encoding (GPT-4 / text-embedding-ada-002).
This is a close-enough approximation for Gemini and other models — exact
counts vary by model but the 16K / 12K budget gates are soft limits.
"""

import tiktoken

from app.utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared encoder — initialised once at import time
# ---------------------------------------------------------------------------
_ENCODING = tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Return approximate token count for *text*."""
    return len(_ENCODING.encode(text))


def fits_in_budget(text: str, max_tokens: int) -> bool:
    """Return True if *text* fits within the token budget."""
    return count_tokens(text) <= max_tokens


def chunk_text(
    text: str,
    max_tokens: int = 12_000,
    overlap_tokens: int = 500,
) -> list[str]:
    """
    Split *text* into chunks of at most *max_tokens* tokens.

    Splits on paragraph boundaries (double newline) to avoid cutting mid-sentence.
    Each chunk except the first includes *overlap_tokens* of context from the
    end of the previous chunk so agents don't lose cross-boundary context.

    Returns a list of strings.  If *text* already fits, returns [text].
    """
    if count_tokens(text) <= max_tokens:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_paras: list[str] = []
    current_tokens = 0
    overlap_buffer: str = ""   # Tail of the last chunk for overlap injection

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # Edge case: single paragraph exceeds budget — hard-split by sentences
        if para_tokens > max_tokens:
            if current_paras:
                chunks.append("\n\n".join(current_paras))
                overlap_buffer = _last_n_tokens(current_paras[-1], overlap_tokens)
                current_paras, current_tokens = [], 0
            for sub in _split_long_paragraph(para, max_tokens, overlap_tokens):
                chunks.append(sub)
            overlap_buffer = _last_n_tokens(para, overlap_tokens)
            continue

        # Would adding this paragraph exceed the budget?
        if current_tokens + para_tokens > max_tokens:
            chunks.append("\n\n".join(current_paras))
            overlap_buffer = _last_n_tokens(current_paras[-1], overlap_tokens)
            # Start new chunk with overlap context
            current_paras = [overlap_buffer, para] if overlap_buffer else [para]
            current_tokens = count_tokens("\n\n".join(current_paras))
        else:
            current_paras.append(para)
            current_tokens += para_tokens

    if current_paras:
        chunks.append("\n\n".join(current_paras))

    log.debug(
        "chunk_text: split into %d chunks (max=%d tokens, overlap=%d)",
        len(chunks),
        max_tokens,
        overlap_tokens,
    )
    return chunks


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _last_n_tokens(text: str, n: int) -> str:
    """Return the last *n* tokens of *text* as a string."""
    tokens = _ENCODING.encode(text)
    return _ENCODING.decode(tokens[-n:]) if len(tokens) > n else text


def _split_long_paragraph(
    para: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """
    Hard-split a paragraph that is itself longer than max_tokens.
    Splits on sentence boundaries (". ") as a best-effort approach.
    """
    sentences = para.replace(". ", ".\n").split("\n")
    return chunk_text("\n".join(sentences), max_tokens, overlap_tokens)
