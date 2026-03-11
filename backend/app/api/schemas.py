from pydantic import BaseModel, HttpUrl


class EvaluateRequest(BaseModel):
    arxiv_url: str


class EvaluateResponse(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    submitted_date: str
    page_count: int
    tagged_count: int
