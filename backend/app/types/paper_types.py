from typing import Optional

from pydantic import BaseModel

from app.constants import ExtractionPath, SectionTag


class PaperMetadata(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    submitted_date: str
    categories: list[str]
    pdf_url: str


class PageData(BaseModel):
    page: int
    markdown: str
    tables: int = 0
    images: int = 0
    has_screenshot: bool = False
    screenshot_path: Optional[str] = None
    page_tag: Optional[SectionTag] = None
    page_summary: str = ""
    image_data: str = ""   # key values/numbers extracted from tables or graphs on this page


class SectionData(BaseModel):
    tag: SectionTag
    content: str
    token_count: int = 0
    page_start: int = 0
    page_end: int = 0


class PaperRecord(BaseModel):
    id: str
    title: str
    authors: list[str]
    abstract: str
    submitted_date: str
    pdf_url: str
    page_count: int
    extraction_path: ExtractionPath
