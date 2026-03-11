"""
PDF extraction using pymupdf4llm + PyMuPDF.

extract_pages(pdf_path, pdf_code, images_dir) -> list[PageData]

- Splits PDF page by page into markdown chunks via pymupdf4llm
- Pages that contain tables or images/graphs get a screenshot saved to images_dir
- Screenshot filenames: <pdf_code>_img_<id>.png  (e.g. 1706_03762_img_3.png)
- Returns PageData per page with has_screenshot=True for visual pages
"""

from pathlib import Path

import fitz  # PyMuPDF
import pymupdf4llm

from app.types import PageData
from app.utils.logger import get_logger

log = get_logger(__name__)

# pymupdf4llm: disable layout analysis (fixes Python 3.14+ import error)
pymupdf4llm.use_layout(False)

_DEFAULT_IMAGES_DIR = Path("data/images")


def extract_pages(
    pdf_path: Path,
    pdf_code: str,
    images_dir: Path = _DEFAULT_IMAGES_DIR,
    screenshot_dpi: int = 150,
) -> list[PageData]:
    """
    Extract every page of the PDF as markdown. Pages with visual content
    (tables, images, graphs) are also saved as PNG screenshots.

    Args:
        pdf_path:       Path to the downloaded PDF file.
        pdf_code:       arXiv ID used to name screenshots, e.g. "2301.12345".
                        Dots/slashes are replaced with underscores.
        images_dir:     Directory where screenshots are saved. Created if absent.
        screenshot_dpi: Resolution for screenshot rendering (150 is good enough for LLMs).

    Returns:
        list[PageData] in document order (page 1 first).

    Raises:
        RuntimeError if pymupdf4llm extraction fails completely.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    safe_code = pdf_code.replace("/", "_").replace(".", "_")

    # --- Step 1: extract markdown per page ---
    try:
        chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    except Exception as exc:
        raise RuntimeError(f"extract_pages: pymupdf4llm failed - {exc}") from exc

    # --- Step 2: open PDF for screenshot rendering ---
    doc = fitz.open(str(pdf_path))
    pages: list[PageData] = []
    screenshot_count = 0

    try:
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            page_num = meta.get("page", len(pages)) + 1  # 0-indexed -> 1-indexed
            tables = len(chunk.get("tables", []))
            images = len(chunk.get("images", []))
            has_screenshot = False

            # Take screenshot if the page has any visual content
            if tables > 0 or images > 0:
                screenshot_count += 1
                img_name = f"{safe_code}_img_{screenshot_count}.png"
                img_path = images_dir / img_name

                fitz_page = doc[page_num - 1]
                pixmap = fitz_page.get_pixmap(dpi=screenshot_dpi)
                pixmap.save(str(img_path))
                has_screenshot = True

                log.debug(
                    "screenshot: page %d -> %s (tables=%d, images=%d)",
                    page_num, img_name, tables, images,
                )

            pages.append(
                PageData(
                    page=page_num,
                    markdown=chunk.get("text", "").strip(),
                    tables=tables,
                    images=images,
                    has_screenshot=has_screenshot,
                    screenshot_path=str(img_path) if has_screenshot else None,
                )
            )
    finally:
        doc.close()

    log.info(
        "extract_pages: %d pages | tables=%d | images=%d | screenshots=%d",
        len(pages),
        sum(p.tables for p in pages),
        sum(p.images for p in pages),
        screenshot_count,
    )
    return pages
