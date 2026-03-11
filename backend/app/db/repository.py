import json
from typing import Optional

import asyncpg

from app.constants import AgentName, SectionTag, Verdict
from app.types import AgentResult, PageData, PaperRecord, SectionData
from app.utils.logger import get_logger

log = get_logger(__name__)


async def insert_paper(pool: asyncpg.Pool, paper: PaperRecord) -> None:
    log.debug("insert_paper: %s", paper.id)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO papers (id, title, authors, abstract, submitted_date, pdf_url, page_count, extraction_path)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO UPDATE SET
                title           = EXCLUDED.title,
                authors         = EXCLUDED.authors,
                abstract        = EXCLUDED.abstract,
                submitted_date  = EXCLUDED.submitted_date,
                pdf_url         = EXCLUDED.pdf_url,
                page_count      = EXCLUDED.page_count,
                extraction_path = EXCLUDED.extraction_path
            """,
            paper.id,
            paper.title,
            json.dumps(paper.authors),
            paper.abstract,
            paper.submitted_date,
            paper.pdf_url,
            paper.page_count,
            paper.extraction_path.value,
        )


async def get_paper(pool: asyncpg.Pool, paper_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM papers WHERE id = $1", paper_id)
    if row is None:
        return None
    d = dict(row)
    d["authors"] = json.loads(d["authors"] or "[]")
    return d


async def insert_pages(
    pool: asyncpg.Pool,
    paper_id: str,
    pages: list[PageData],
) -> None:
    log.debug("insert_pages: paper=%s count=%d", paper_id, len(pages))
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM pages WHERE paper_id = $1", paper_id)
        await conn.executemany(
            """
            INSERT INTO pages
                (paper_id, page_num, markdown, tables, images, has_screenshot, screenshot_path, page_tag, page_summary, image_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            [
                (
                    paper_id,
                    p.page,
                    p.markdown,
                    p.tables,
                    p.images,
                    p.has_screenshot,
                    p.screenshot_path,
                    p.page_tag.value if p.page_tag else None,
                    p.page_summary,
                    p.image_data,
                )
                for p in pages
            ],
        )


async def insert_page(pool: asyncpg.Pool, paper_id: str, page: PageData) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pages
                (paper_id, page_num, markdown, tables, images, has_screenshot, screenshot_path, page_tag, page_summary, image_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (paper_id, page_num) DO UPDATE SET
                page_tag        = EXCLUDED.page_tag,
                page_summary    = EXCLUDED.page_summary,
                image_data      = EXCLUDED.image_data
            """,
            paper_id,
            page.page,
            page.markdown,
            page.tables,
            page.images,
            page.has_screenshot,
            page.screenshot_path,
            page.page_tag.value if page.page_tag else None,
            page.page_summary,
            page.image_data,
        )


async def get_pages_by_paper(pool: asyncpg.Pool, paper_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pages WHERE paper_id = $1 ORDER BY page_num",
            paper_id,
        )
    return [dict(row) for row in rows]


async def insert_sections(
    pool: asyncpg.Pool,
    paper_id: str,
    sections: list[SectionData],
) -> None:
    log.debug("insert_sections: paper=%s count=%d", paper_id, len(sections))
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sections WHERE paper_id = $1", paper_id)
        await conn.executemany(
            """
            INSERT INTO sections (paper_id, tag, content, token_count, page_start, page_end)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (paper_id, s.tag.value, s.content, s.token_count, s.page_start, s.page_end)
                for s in sections
            ],
        )


async def get_sections_by_tag(
    pool: asyncpg.Pool,
    paper_id: str,
    tag: SectionTag,
) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT content FROM sections WHERE paper_id = $1 AND tag = $2",
            paper_id, tag.value,
        )
    return row["content"] if row else None


async def get_all_sections(
    pool: asyncpg.Pool,
    paper_id: str,
) -> dict[SectionTag, str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tag, content FROM sections WHERE paper_id = $1 ORDER BY id",
            paper_id,
        )
    return {SectionTag(row["tag"]): row["content"] for row in rows}


async def insert_agent_result(
    pool: asyncpg.Pool,
    paper_id: str,
    result: AgentResult,
) -> None:
    log.debug("insert_agent_result: paper=%s agent=%s score=%s", paper_id, result.agent_name, result.score)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_results
                (paper_id, agent_name, score, findings, raw_output, tokens_used, duration_s, status, error_msg)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (paper_id, agent_name) DO UPDATE SET
                score       = EXCLUDED.score,
                findings    = EXCLUDED.findings,
                raw_output  = EXCLUDED.raw_output,
                tokens_used = EXCLUDED.tokens_used,
                duration_s  = EXCLUDED.duration_s,
                status      = EXCLUDED.status,
                error_msg   = EXCLUDED.error_msg
            """,
            paper_id,
            result.agent_name.value,
            result.score,
            json.dumps([f.model_dump() for f in result.findings]),
            result.raw_output,
            result.usage.total_tokens,
            result.duration_s,
            result.status.value,
            result.error_msg,
        )


async def get_agent_results(pool: asyncpg.Pool, paper_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM agent_results WHERE paper_id = $1 ORDER BY id",
            paper_id,
        )
    results = []
    for row in rows:
        d = dict(row)
        d["findings"] = json.loads(d["findings"] or "[]")
        results.append(d)
    return results


async def get_agent_result_by_name(
    pool: asyncpg.Pool,
    paper_id: str,
    agent_name: AgentName,
) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agent_results WHERE paper_id = $1 AND agent_name = $2",
            paper_id, agent_name.value,
        )
    if row is None:
        return None
    d = dict(row)
    d["findings"] = json.loads(d["findings"] or "[]")
    return d


async def insert_report(
    pool: asyncpg.Pool,
    paper_id: str,
    overall_score: float,
    verdict: Verdict,
    weights: dict,
    scores: dict,
    executive_summary: str,
    markdown_report: str,
) -> None:
    log.debug("insert_report: paper=%s score=%.1f verdict=%s", paper_id, overall_score, verdict.value)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reports
                (paper_id, overall_score, verdict, weights_json, scores_json, executive_summary, markdown_report)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (paper_id) DO UPDATE SET
                overall_score     = EXCLUDED.overall_score,
                verdict           = EXCLUDED.verdict,
                weights_json      = EXCLUDED.weights_json,
                scores_json       = EXCLUDED.scores_json,
                executive_summary = EXCLUDED.executive_summary,
                markdown_report   = EXCLUDED.markdown_report
            """,
            paper_id,
            overall_score,
            verdict.value,
            json.dumps(weights),
            json.dumps(scores),
            executive_summary,
            markdown_report,
        )


async def get_report(pool: asyncpg.Pool, paper_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM reports WHERE paper_id = $1", paper_id)
    if row is None:
        return None
    d = dict(row)
    d["weights"] = json.loads(d["weights_json"] or "{}")
    d["scores"] = json.loads(d["scores_json"] or "{}")
    return d
