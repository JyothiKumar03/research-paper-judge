from typing import Optional, TypedDict

from app.constants import ExtractionPath, PipelineStage, PipelineStatus, Verdict


class PaperEvalState(TypedDict):
    arxiv_url: str
    paper_id: str

    metadata: Optional[dict]
    pages: list[dict]
    extraction_path: ExtractionPath

    tagged_pages: list[dict]
    sections: dict
    section_tokens: dict
    chunks: dict

    grammar_result: Optional[dict]
    novelty_result: Optional[dict]
    factcheck_result: Optional[dict]

    consistency_result: Optional[dict]
    authenticity_result: Optional[dict]

    scores: dict
    overall_score: float
    verdict: Verdict

    executive_summary: str
    markdown_report: str

    current_stage: PipelineStage
    errors: list[str]
    status: PipelineStatus
