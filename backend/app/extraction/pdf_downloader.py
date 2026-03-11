"""
PDF download utility.

Downloads a PDF from a URL (typically https://arxiv.org/pdf/{id}) to a
temporary file and returns its path.  The caller is responsible for deleting
the temp file when done.

Ported from scripts/pdf_to_pages_json.py with async support added.
"""

import tempfile
from pathlib import Path

import httpx

from app.utils.logger import get_logger

log = get_logger(__name__)

_HEADERS = {"User-Agent": "research-validator/0.1 (academic use)"}


async def download_pdf(
    arxiv_id: str,
    timeout: float = 60.0,
) -> Path:
    """
    Download the PDF for *arxiv_id* from arxiv.org to a temporary file.

    Returns the Path to the temp file.  Caller must delete it when done:
        try:
            pdf_path = await download_pdf(arxiv_id)
            pages = extract_pages(pdf_path)
        finally:
            pdf_path.unlink(missing_ok=True)

    Raises httpx.HTTPStatusError on non-200 responses.
    Raises httpx.TimeoutException on timeout.
    """
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    log.info("download_pdf: fetching %s", url)

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf",
        prefix=f"arxiv_{arxiv_id.replace('/', '_')}_",
    )

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                tmp.write(chunk)

    tmp.close()
    pdf_path = Path(tmp.name)
    size_kb = pdf_path.stat().st_size / 1024

    log.info("download_pdf: saved %.0f KB → %s", size_kb, pdf_path.name)
    return pdf_path
