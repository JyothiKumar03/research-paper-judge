from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import EvaluateRequest, EvaluateResponse
from app.constants import ExtractionPath
from app.db import get_pages_by_paper, get_paper, get_report, insert_paper
from app.extraction.arxiv_meta import extract_arxiv_id, fetch_metadata
from app.extraction.pdf_downloader import download_pdf
from app.extraction.pdf_extractor import extract_pages
from app.structuring.section_tagger import tag_all_pages
from app.types import PaperRecord
from app.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "research-validator-backend"}


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_paper(body: EvaluateRequest, request: Request):
    pool = request.app.state.pool

    try:
        arxiv_id = extract_arxiv_id(body.arxiv_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        metadata = await fetch_metadata(arxiv_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"arXiv API error: {exc}")

    try:
        pdf_path = await download_pdf(arxiv_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}")

    try:
        pages = extract_pages(pdf_path, arxiv_id)
        log.info("evaluate_paper: extracted %d pages for %s", len(pages), arxiv_id)

        # Insert paper row first — pages FK-reference it and are stored as they complete
        paper = PaperRecord(
            id=arxiv_id,
            title=metadata.title,
            authors=metadata.authors,
            abstract=metadata.abstract,
            submitted_date=metadata.submitted_date,
            pdf_url=metadata.pdf_url,
            page_count=len(pages),
            extraction_path=ExtractionPath.PDF,
        )
        await insert_paper(pool, paper)
        log.info("evaluate_paper: paper row inserted for %s", arxiv_id)

        # Tag all pages concurrently; each page is stored to DB immediately on completion
        tagged_pages = await tag_all_pages(pool, arxiv_id, pages)
        log.info("evaluate_paper: all %d pages tagged and stored for %s", len(tagged_pages), arxiv_id)

        return EvaluateResponse(
            paper_id=arxiv_id,
            title=metadata.title,
            authors=metadata.authors,
            abstract=metadata.abstract,
            submitted_date=metadata.submitted_date,
            page_count=len(tagged_pages),
            tagged_count=sum(1 for p in tagged_pages if p.page_tag not in (None,)),
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.error("evaluate_paper: pipeline failed for %s — %s", arxiv_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")
    finally:
        pdf_path.unlink(missing_ok=True)


@router.get("/evaluate/{paper_id}/status")
async def evaluation_status(paper_id: str, request: Request):
    pool = request.app.state.pool
    paper = await get_paper(pool, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")
    pages = await get_pages_by_paper(pool, paper_id)
    return {
        "paper_id": paper_id,
        "title": paper["title"],
        "page_count": paper["page_count"],
        "pages_stored": len(pages),
    }


@router.get("/report/{paper_id}")
async def get_report_endpoint(paper_id: str, request: Request):
    pool = request.app.state.pool
    report = await get_report(pool, paper_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report for {paper_id!r} not found")
    return report
