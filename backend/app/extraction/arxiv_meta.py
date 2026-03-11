"""
arXiv metadata extraction — no LLM needed.

Provides two functions:
  extract_arxiv_id(url) → str      — parse any arXiv URL/ID format
  fetch_metadata(arxiv_id) → PaperMetadata — call the arXiv Atom API
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from app.types import PaperMetadata
from app.utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "http://www.w3.org/2005/Atom"

# Patterns handled (in priority order):
#   1.  https://arxiv.org/abs/1706.03762        new-style abs
#   2.  https://arxiv.org/pdf/1706.03762v7      new-style pdf (with/without version)
#   3.  https://arxiv.org/abs/cs/0609001        old-style category/id
#   4.  https://arxiv.org/src/1706.03762        source URL
#   5.  1706.03762                               bare new-style ID
#   6.  cs/0609001                               bare old-style ID
_PATTERNS: list[re.Pattern] = [
    re.compile(r"arxiv\.org/(?:abs|pdf|src)/([a-z-]+/\d{7}(?:v\d+)?)", re.I),   # old-style
    re.compile(r"arxiv\.org/(?:abs|pdf|src)/(\d{4}\.\d{4,5}(?:v\d+)?)",  re.I),  # new-style
    re.compile(r"^([a-z-]+/\d{7})$",                                       re.I),  # bare old
    re.compile(r"^(\d{4}\.\d{4,5}(?:v\d+)?)$"),                                  # bare new
]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def extract_arxiv_id(url: str) -> str:
    """
    Extract the canonical arXiv paper ID from any of the common URL formats
    or a bare ID string.

    Returns the ID without version suffix (e.g. "1706.03762" not "1706.03762v7")
    so we always fetch the latest version's metadata.

    Raises ValueError if the input cannot be parsed.
    """
    url = url.strip()
    log.debug("extract_arxiv_id: parsing %r", url)

    for pattern in _PATTERNS:
        match = pattern.search(url)
        if match:
            raw_id = match.group(1)
            # Strip version suffix (vN) for canonical ID
            arxiv_id = re.sub(r"v\d+$", "", raw_id)
            log.debug("extract_arxiv_id: found %r -> %r", raw_id, arxiv_id)
            return arxiv_id

    raise ValueError(
        f"Cannot extract arXiv ID from {url!r}. "
        "Expected formats: https://arxiv.org/abs/1706.03762, "
        "https://arxiv.org/pdf/1706.03762, or a bare ID like 1706.03762"
    )


async def fetch_metadata(
    arxiv_id: str,
    timeout: float = 30.0,
) -> PaperMetadata:
    """
    Fetch paper metadata from the arXiv Atom API.

    Returns a PaperMetadata with title, authors, abstract, date, categories.
    Uses the abstract from the API (clean, no LaTeX artifacts).

    Raises httpx.HTTPError on network failure.
    Raises ValueError if the API returns no results.
    """
    log.info("fetch_metadata: fetching arXiv metadata for %s", arxiv_id)

    params = {"id_list": arxiv_id, "max_results": "1"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(_ARXIV_API_URL, params=params)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    entry = root.find(f"{{{_ATOM_NS}}}entry")

    if entry is None:
        raise ValueError(f"fetch_metadata: arXiv API returned no entry for {arxiv_id!r}")

    # --- Parse fields ---
    title = _text(entry, f"{{{_ATOM_NS}}}title")
    abstract = _text(entry, f"{{{_ATOM_NS}}}summary")
    submitted_date = _text(entry, f"{{{_ATOM_NS}}}published")[:10]  # "YYYY-MM-DD"

    authors = [
        _text(author, f"{{{_ATOM_NS}}}name")
        for author in entry.findall(f"{{{_ATOM_NS}}}author")
    ]

    categories = [
        tag.get("term", "")
        for tag in entry.findall("{http://arxiv.org/schemas/atom}primary_category")
        + entry.findall("{http://arxiv.org/schemas/atom}category")
        if tag.get("term")
    ]
    # Deduplicate while preserving order (primary category first)
    seen: set[str] = set()
    categories = [c for c in categories if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    metadata = PaperMetadata(
        arxiv_id=arxiv_id,
        title=title.strip(),
        authors=authors,
        abstract=abstract.strip(),
        submitted_date=submitted_date,
        categories=categories or ["unknown"],
        pdf_url=pdf_url,
    )

    log.info(
        "fetch_metadata: %r — %d authors, date=%s",
        metadata.title[:60],
        len(metadata.authors),
        metadata.submitted_date,
    )
    return metadata


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _text(element: ET.Element, tag: str, default: str = "") -> str:
    """Safe text extraction from an XML element."""
    child = element.find(tag)
    return (child.text or default) if child is not None else default
