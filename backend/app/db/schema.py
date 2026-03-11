import asyncpg

from app.utils.logger import get_logger

log = get_logger(__name__)

_CREATE_PAPERS = """
CREATE TABLE IF NOT EXISTS papers (
    id              TEXT PRIMARY KEY,
    title           TEXT        NOT NULL,
    authors         TEXT        NOT NULL,
    abstract        TEXT        NOT NULL,
    submitted_date  TEXT        NOT NULL,
    pdf_url         TEXT        NOT NULL,
    page_count      INTEGER     NOT NULL DEFAULT 0,
    extraction_path TEXT        NOT NULL DEFAULT 'pdf'
        CHECK (extraction_path IN ('pdf', 'latex')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_SECTIONS = """
CREATE TABLE IF NOT EXISTS sections (
    id          BIGSERIAL   PRIMARY KEY,
    paper_id    TEXT        NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    tag         TEXT        NOT NULL
        CHECK (tag IN (
            'TITLE', 'ABSTRACT', 'INTRODUCTION', 'RELATED_WORK', 'BACKGROUND',
            'METHODOLOGY', 'EXPERIMENTS', 'RESULTS', 'DISCUSSION', 'CONCLUSION',
            'REFERENCES', 'APPENDIX', 'ACKNOWLEDGMENTS', 'OTHER'
        )),
    content     TEXT        NOT NULL,
    token_count INTEGER     NOT NULL DEFAULT 0,
    page_start  INTEGER,
    page_end    INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (paper_id, tag)
);
"""

_CREATE_AGENT_RESULTS = """
CREATE TABLE IF NOT EXISTS agent_results (
    id          BIGSERIAL   PRIMARY KEY,
    paper_id    TEXT        NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    agent_name  TEXT        NOT NULL
        CHECK (agent_name IN ('grammar', 'novelty', 'factcheck', 'consistency', 'authenticity')),
    score       REAL,
    findings    TEXT        NOT NULL DEFAULT '[]',
    raw_output  TEXT        NOT NULL DEFAULT '',
    tokens_used INTEGER     NOT NULL DEFAULT 0,
    duration_s  REAL        NOT NULL DEFAULT 0.0,
    status      TEXT        NOT NULL DEFAULT 'completed'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    error_msg   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (paper_id, agent_name)
);
"""

_CREATE_REPORTS = """
CREATE TABLE IF NOT EXISTS reports (
    id                BIGSERIAL   PRIMARY KEY,
    paper_id          TEXT        NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
    overall_score     REAL        NOT NULL,
    verdict           TEXT        NOT NULL CHECK (verdict IN ('PASS', 'FAIL')),
    weights_json      TEXT        NOT NULL DEFAULT '{}',
    scores_json       TEXT        NOT NULL DEFAULT '{}',
    executive_summary TEXT        NOT NULL DEFAULT '',
    markdown_report   TEXT        NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pages_paper ON pages(paper_id);",
    "CREATE INDEX IF NOT EXISTS idx_sections_paper_tag ON sections(paper_id, tag);",
    "CREATE INDEX IF NOT EXISTS idx_agent_results_paper ON agent_results(paper_id);",
    "CREATE INDEX IF NOT EXISTS idx_reports_paper ON reports(paper_id);",
]

_CREATE_PAGES = """
CREATE TABLE IF NOT EXISTS pages (
    id              BIGSERIAL    PRIMARY KEY,
    paper_id        TEXT         NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    page_num        INTEGER      NOT NULL,
    markdown        TEXT         NOT NULL DEFAULT '',
    tables          INTEGER      NOT NULL DEFAULT 0,
    images          INTEGER      NOT NULL DEFAULT 0,
    has_screenshot  BOOLEAN      NOT NULL DEFAULT FALSE,
    screenshot_path TEXT,
    page_tag        TEXT         CHECK (page_tag IS NULL OR page_tag IN (
                        'TITLE', 'ABSTRACT', 'INTRODUCTION', 'RELATED_WORK', 'BACKGROUND',
                        'METHODOLOGY', 'EXPERIMENTS', 'RESULTS', 'DISCUSSION', 'CONCLUSION',
                        'REFERENCES', 'APPENDIX', 'ACKNOWLEDGMENTS', 'OTHER'
                    )),
    page_summary    TEXT         NOT NULL DEFAULT '',
    image_data      TEXT         NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (paper_id, page_num)
);
"""

_ALL_DDL = [_CREATE_PAPERS, _CREATE_PAGES, _CREATE_SECTIONS, _CREATE_AGENT_RESULTS, _CREATE_REPORTS]


_MIGRATIONS = [
    # safe to run on both fresh and existing DBs
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='pages' AND column_name='image_data'
        ) THEN
            ALTER TABLE pages ADD COLUMN image_data TEXT NOT NULL DEFAULT '';
        END IF;
    END $$;
    """,
]


async def init_db(database_url: str) -> asyncpg.Pool:
    log.info("init_db: creating connection pool")
    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)

    async with pool.acquire() as conn:
        for ddl in _ALL_DDL:
            await conn.execute(ddl)
        for idx in _INDEXES:
            await conn.execute(idx)
        for migration in _MIGRATIONS:
            await conn.execute(migration)

    log.info("init_db: schema ready (%d tables, %d indexes)", len(_ALL_DDL), len(_INDEXES))
    return pool
