from pydantic import BaseModel


class EvaluateRequest(BaseModel):
    arxiv_url: str


class AgentScoreItem(BaseModel):
    name: str
    wave: str  # "sanity_check" or "fraud_check"
    status: str
    score: float | None
    findings_count: int


class RunEvalResponse(BaseModel):
    paper_id: str
    agents: list[AgentScoreItem]
    overall_score: float | None = None
    verdict: str | None = None


class EvaluateResponse(BaseModel):
    paper_id: str   # UUID — unique per submission
    arxiv_id: str   # canonical arXiv ID
    title: str
    authors: list[str]
    abstract: str
    submitted_date: str
    page_count: int
    tagged_count: int
    agent_scores: dict[str, float | None] = {}
    overall_score: float | None = None
    verdict: str | None = None
