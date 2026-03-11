# Research Validator

A multi-agent system that autonomously evaluates arXiv research papers and generates a peer-review-style **Judgement Report** with scored dimensions.

---

## What it does

Give it any arXiv URL. It will:

1. Download the paper (LaTeX source preferred, PDF fallback)
2. Structure it into sections (Abstract, Methodology, Results, etc.)
3. Run 5 specialized AI agents in two waves
4. Aggregate scores with fixed weights
5. Generate a Judgement Report (Markdown + PDF)

```
Input:  https://arxiv.org/abs/1706.03762

Output:
  Overall Score  : 82/100 — PASS
  Consistency    : 88     (30%)
  Authenticity   : 79     (25%)
  Novelty        : 91     (20%)
  Fact-Check     : 74     (15%)
  Grammar        : 85     (10%)
```

---

## Architecture

```
URL
 │
 ├─ arXiv API ──────────────────► Metadata (title, authors, abstract)
 │
 └─ LaTeX source (preferred)
    PDF fallback
        │
        ▼
   Page extraction (pymupdf4llm)
        │
        ▼
   LLM section tagging ─► ABSTRACT | INTRODUCTION | METHODOLOGY | RESULTS | ...
        │
        ▼
   Stitch sections ──────────────► SQLite
        │
        ├──────────────────────────────────────────┐
        │          WAVE 1 (parallel)               │
        ├─ Grammar Agent      ◄── all sections      │
        ├─ Novelty Agent      ◄── abstract + intro + Semantic Scholar
        └─ Fact-Check Agent   ◄── methodology + results
                │
                ▼
          WAVE 2 (sequential)
        ├─ Consistency Agent  ◄── methodology + results
        └─ Authenticity Agent ◄── results + factcheck flags
                │
                ▼
        Weighted Score (no LLM)
        consistency×0.30 + authenticity×0.25 + novelty×0.20
        + factcheck×0.15 + grammar×0.10
                │
                ▼
        Executive Summary (1 LLM call)
                │
                ▼
        Judgement Report (Markdown + PDF)
```

**Constraints honoured:**
- Max **16K tokens per LLM call** (enforced by `token_counter.py`)
- Free-tier LLMs only via **OpenRouter** (no paid APIs required)
- No embeddings, no vector DB, no RAG — pure tag-based routing

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Agent orchestration | LangGraph |
| PDF extraction | pymupdf4llm + PyMuPDF |
| Token counting | tiktoken (cl100k_base) |
| LLM | OpenRouter (Gemini Flash free tier) |
| External search | Semantic Scholar API (free) |
| Storage | SQLite (raw sqlite3, no ORM) |
| Report export | fpdf2 (pure Python PDF) |
| UI | Streamlit |
| Logging | Rich |

---

## Project Structure

```
research-validator/
├── backend/
│   ├── app/
│   │   ├── config.py              # Settings from .env
│   │   ├── main.py                # FastAPI app + lifespan (DB init)
│   │   ├── constants/             # SECTION_TAGS, AGENT_WEIGHTS, model list
│   │   ├── types/                 # Pydantic models (paper, agent, state)
│   │   ├── db/                    # SQLite schema + CRUD repository
│   │   ├── utils/                 # logger, token_counter, json_parser
│   │   ├── extraction/            # arxiv_meta, pdf_downloader, pdf_extractor, latex_extractor
│   │   ├── services/              # llm_service (OpenRouter client, retry + fallback)
│   │   ├── agents/                # [Phase 2] grammar, novelty, factcheck, consistency, authenticity
│   │   ├── structuring/           # [Phase 2] section_tagger, stitcher, token_manager
│   │   ├── graph/                 # [Phase 2] LangGraph state + nodes + pipeline
│   │   ├── prompts/               # [Phase 2] prompt templates per agent
│   │   ├── api/                   # routes.py (endpoints), schemas.py
│   │   └── templates/             # [Phase 2] report_template.md
│   ├── pyproject.toml
│   └── .env.example
└── frontend/
    ├── app.py                     # [Phase 2] Streamlit UI
    └── pyproject.toml
```

---

## Setup

### 1. Clone

```bash
git clone <repo-url>
cd research-validator
```

### 2. Backend

```bash
cd backend

# Create venv and install deps
uv venv
uv pip install -e .

# Configure environment
cp .env.example .env
# Edit .env — add your OPENROUTER_API_KEY
```

Get a free OpenRouter key at [openrouter.ai/keys](https://openrouter.ai/keys).

### 3. Run backend

```bash
cd backend
python -m app.main
# or
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Frontend (Phase 2)

```bash
cd frontend
uv pip install -e .
streamlit run app.py
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | **Yes** | — | Free key from openrouter.ai |
| `OPENROUTER_MODEL` | No | `google/gemini-2.0-flash-exp:free` | Primary LLM model |
| `SEMANTIC_SCHOLAR_API_KEY` | No | — | Optional — increases rate limits |
| `SQLITE_DB_PATH` | No | `data/research_validator.db` | DB file location |
| `HOST` | No | `0.0.0.0` | Server host |
| `PORT` | No | `8000` | Server port |
| `DEBUG` | No | `true` | Enable FastAPI reload |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Liveness check |
| `POST` | `/api/v1/evaluate` | Submit arXiv URL for evaluation |
| `GET` | `/api/v1/evaluate/{paper_id}/status` | Poll evaluation progress |
| `GET` | `/api/v1/report/{paper_id}` | Fetch completed Markdown report |
| `GET` | `/api/v1/report/{paper_id}/pdf` | Download PDF report |

---

## Scoring

| Agent | Weight | Input sections |
|-------|--------|---------------|
| Consistency | 30% | Methodology + Results |
| Authenticity | 25% | Results + Fact-check flags |
| Novelty | 20% | Abstract + Intro + Semantic Scholar |
| Fact-Check | 15% | Methodology + Results + Intro |
| Grammar | 10% | All sections (map-reduce) |

**Verdict:** `overall_score >= 60` → **PASS**, else **FAIL**

---

## LLM Usage per Paper (15-page estimate)

| Step | LLM Calls | ~Tokens |
|------|-----------|---------|
| Section tagging | 3 | ~10K |
| Grammar (map-reduce) | 4–6 | ~78K |
| Novelty | 2 | ~20K |
| Fact-check | 2–3 | ~39K |
| Consistency | 1–2 | ~26K |
| Authenticity | 1–2 | ~26K |
| Executive summary | 1 | ~4K |
| **Total** | **~18** | **~200K** |

Gemini Flash free via OpenRouter: ~20 RPM → ~60–120 seconds per paper.

---

## Development Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Done | Foundation: config, types, DB, utils, extraction, LLM service |
| Phase 2 | 🔲 Next | Structuring, agents, LangGraph pipeline, API wiring, Streamlit UI |
