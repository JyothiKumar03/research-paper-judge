import json
import uuid

from fastapi import APIRouter, HTTPException, Request

from app.agents import run_all_agents
from app.constants import AgentName
from app.api.schemas import AgentScoreItem, EvaluateRequest, EvaluateResponse, RunEvalResponse
from app.constants import ExtractionPath
from app.db import get_agent_results, get_pages_by_paper, get_paper, get_report, insert_paper
from app.extraction.arxiv_meta import extract_arxiv_id, fetch_metadata
from app.extraction.pdf_downloader import download_pdf
from app.extraction.pdf_extractor import extract_pages
from app.structuring.section_tagger import tag_all_pages
from app.types import PaperMetadata, PaperRecord
from app.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


_SANITY_AGENTS = {AgentName.GRAMMAR, AgentName.FACTCHECK, AgentName.NOVELTY}

async def _run_eval(pool, paper_id: str) -> tuple[list[AgentScoreItem], dict | None]:
    """Runs both waves + evaluator, returns per-agent summaries and the final report."""
    agent_results = await run_all_agents(pool, paper_id)
    items = [
        AgentScoreItem(
            name=str(name),
            wave="sanity_check" if name in _SANITY_AGENTS else "fraud_check",
            status=res.status.value,
            score=res.score,
            findings_count=len(res.findings),
        )
        for name, res in agent_results.items()
    ]
    report = await get_report(pool, paper_id)
    return items, report


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

    _FALLBACK = "FAILED TO FETCH METADATA"
    try:
        metadata = await fetch_metadata(arxiv_id)
    except Exception as exc:
        log.warning("evaluate_paper: metadata fetch failed for %s — %s, continuing with fallback", arxiv_id, exc)
        metadata = PaperMetadata(
            arxiv_id=arxiv_id,
            title=_FALLBACK,
            authors=[_FALLBACK],
            abstract=_FALLBACK,
            submitted_date=_FALLBACK,
            categories=["unknown"],
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        )

    try:
        pdf_path = await download_pdf(arxiv_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}")

    try:
        pages = extract_pages(pdf_path, arxiv_id)
        log.info("evaluate_paper: extracted %d pages for %s", len(pages), arxiv_id)

        paper_id = str(uuid.uuid4())
        paper = PaperRecord(
            id=paper_id,
            arxiv_id=arxiv_id,
            title=metadata.title,
            authors=metadata.authors,
            abstract=metadata.abstract,
            submitted_date=metadata.submitted_date,
            pdf_url=metadata.pdf_url,
            page_count=len(pages),
            extraction_path=ExtractionPath.PDF,
        )
        await insert_paper(pool, paper)
        log.info("evaluate_paper: paper row inserted id=%s arxiv_id=%s", paper_id, arxiv_id)

        tagged_pages = await tag_all_pages(pool, paper_id, pages)
        log.info("evaluate_paper: %d pages tagged for %s", len(tagged_pages), paper_id)

        agent_items, report = await _run_eval(pool, paper_id)
        log.info("evaluate_paper: all agents complete for %s", paper_id)

        return EvaluateResponse(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            title=metadata.title,
            authors=metadata.authors,
            abstract=metadata.abstract,
            submitted_date=metadata.submitted_date,
            page_count=len(tagged_pages),
            tagged_count=sum(1 for p in tagged_pages if p.page_tag is not None),
            agent_scores={item.name: item.score for item in agent_items},
            overall_score=report["overall_score"] if report else None,
            verdict=report["verdict"] if report else None,
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.error("evaluate_paper: pipeline failed for %s — %s", arxiv_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")
    finally:
        pdf_path.unlink(missing_ok=True)


@router.post("/run-eval/{paper_id}", response_model=RunEvalResponse)
async def run_eval(paper_id: str, request: Request):
    """Re-run (or run for the first time) all evaluation agents on an already-ingested paper."""
    pool = request.app.state.pool

    paper = await get_paper(pool, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found — ingest it first via /evaluate")

    try:
        agent_items, report = await _run_eval(pool, paper_id)
        log.info("run_eval: complete for paper=%s", paper_id)
        return RunEvalResponse(
            paper_id=paper_id,
            agents=agent_items,
            overall_score=report["overall_score"] if report else None,
            verdict=report["verdict"] if report else None,
        )
    except Exception as exc:
        log.error("run_eval: failed for paper=%s — %s", paper_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Eval error: {exc}")


@router.get("/evaluate/{paper_id}/status")
async def evaluation_status(paper_id: str, request: Request):
    pool = request.app.state.pool
    paper = await get_paper(pool, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")
    pages = await get_pages_by_paper(pool, paper_id)
    agent_rows = await get_agent_results(pool, paper_id)
    return {
        "paper_id": paper_id,
        "title": paper["title"],
        "page_count": paper["page_count"],
        "pages_stored": len(pages),
        "agents": [
            {"name": r["agent_name"], "status": r["status"], "score": r["score"]}
            for r in agent_rows
        ],
    }


@router.get("/paper/{paper_id}")
async def get_paper_endpoint(paper_id: str, request: Request):
    """Return paper metadata (title, arxiv_id, authors, etc.)."""
    pool = request.app.state.pool
    paper = await get_paper(pool, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")
    paper["authors"] = json.loads(paper["authors"]) if isinstance(paper["authors"], str) else paper["authors"]
    return paper


@router.get("/agents/{paper_id}")
async def get_agents_endpoint(paper_id: str, request: Request):
    """Return full agent results (score, findings, reasoning) for a paper."""
    pool = request.app.state.pool
    paper = await get_paper(pool, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")
    agent_rows = await get_agent_results(pool, paper_id)
    return {"paper_id": paper_id, "agents": agent_rows}


@router.get("/report/{paper_id}")
async def get_report_endpoint(paper_id: str, request: Request):
    pool = request.app.state.pool
    report = await get_report(pool, paper_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report for {paper_id!r} not found")
    return report
