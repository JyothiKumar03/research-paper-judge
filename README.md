# Research Validator

A multi-agent AI system that autonomously evaluates arXiv research papers and generates a peer-review-style **Judgement Report** — complete with PASS/FAIL verdict, scored dimensions, and in-depth reasoning.

---

## What it does

Submit any arXiv URL. The system will:

1. Fetch paper metadata from the arXiv API (title, authors, abstract)
2. Download and extract the PDF into structured, page-tagged content
3. Tag each page by section (Abstract, Methodology, Results, etc.)
4. Run **5 specialized AI evaluation agents** in two parallel waves
5. Pass all agent outputs to a **6th Evaluator Agent** that synthesizes a final verdict
6. Generate a full **Markdown Judgement Report** stored in the database

**Example output:**

```
Paper : Attention Is All You Need (1706.03762)
Overall Score  : 84/100  →  ✅ PASS

  Consistency    88/100   (weight 30%)
  Authenticity   82/100   (weight 25%)
  Novelty        91/100   (weight 20%)
  Fact-Check     79/100   (weight 15%)
  Grammar        85/100   (weight 10%)
```

---

## Setup

### Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`
- A [NeonDB](https://neon.tech) PostgreSQL database (free tier works)
- A free [OpenRouter](https://openrouter.ai/keys) API key
- A free [Google Gemini](https://aistudio.google.com/app/apikey) API key (for novelty agent — Google Search grounding)

---

### 1. Clone

```bash
git clone <repo-url>
cd research-validator
```

---

### 2. Backend

```bash
cd backend

# Install dependencies
uv venv && uv pip install -e .

# Configure environment
cp .env.example .env
```

Edit `backend/.env`:

```env
OPENROUTER_API_KEY=sk-or-...
GEMINI_API_KEY=AIza...
DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require

# Optional
HOST=0.0.0.0
PORT=8000
DEBUG=true
ALLOWED_ORIGINS=["http://localhost:8501"]
```

Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 3. Frontend

```bash
cd frontend

uv pip install -e .

# Set backend URL if not default
export BACKEND_URL=http://localhost:8000

streamlit run app.py
```

UI: [http://localhost:8501](http://localhost:8501)

---

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | **Yes** | Free key from openrouter.ai — routes to Gemini and fallback models |
| `GEMINI_API_KEY` | **Yes** | Google AI Studio key — novelty agent uses Google Search grounding |
| `DATABASE_URL` | **Yes** | NeonDB PostgreSQL connection string |
| `HOST` | No | Server host (default `0.0.0.0`) |
| `PORT` | No | Server port (default `8000`) |
| `DEBUG` | No | FastAPI reload mode (default `true`) |
| `ALLOWED_ORIGINS` | No | CORS origins (default includes `localhost:8501`) |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Liveness check |
| `POST` | `/api/v1/evaluate` | Submit arXiv URL — runs the full pipeline |
| `POST` | `/api/v1/run-eval/{paper_id}` | Re-run all agents on an already-ingested paper |
| `GET` | `/api/v1/evaluate/{paper_id}/status` | Per-agent status and scores |
| `GET` | `/api/v1/paper/{paper_id}` | Paper metadata (title, authors, abstract) |
| `GET` | `/api/v1/agents/{paper_id}` | Full agent results (scores, findings, reasoning) |
| `GET` | `/api/v1/report/{paper_id}` | Final Judgement Report (markdown + verdict) |

**POST `/api/v1/evaluate` body:**
```json
{ "arxiv_url": "https://arxiv.org/abs/1706.03762" }
```

**Response includes:** `paper_id` (UUID), `arxiv_id`, `title`, `overall_score`, `verdict`, `agent_scores`

---

## Core Architecture

```
arXiv URL
    │
    ├─ arXiv API ──────────► title, authors, abstract, pdf_url
    │
    ▼
PDF Download
    │
    ▼
Page Extraction  (pymupdf4llm)
→ per page: markdown, table count, image count
    │
    ▼
LLM Section Tagger
→ tags each page:  ABSTRACT | INTRODUCTION | METHODOLOGY |
                   RESULTS  | DISCUSSION   | CONCLUSION  | REFERENCES | ...
    │
    ▼
PostgreSQL  (NeonDB)
→ tables: papers, pages, sections, agent_results, reports
    │
    ├────────── WAVE 1  (all three run in parallel) ──────────────────┐
    │                                                                  │
    ├─ Grammar Agent       ← all content pages                        │
    ├─ Novelty Agent       ← abstract + intro  (Gemini + Google Search)
    └─ Fact-Check Agent    ← all page summaries                       │
                                                                       │
    ├────────── WAVE 2  (both run in parallel) ───────────────────────┘
    │
    ├─ Consistency Agent   ← methodology + results pages
    └─ Authenticity Agent  ← results + methodology pages
                │
                ▼
         Evaluator Agent   ← reads all 5 results from DB
                │
                ▼
    Weighted score  +  PASS / FAIL  +  Markdown Report
    stored in  reports  table
```

**Score weights:**

| Agent | Weight |
|-------|--------|
| Consistency | 30% |
| Authenticity | 25% |
| Novelty | 20% |
| Fact-Check | 15% |
| Grammar | 10% |

**Verdict:** `overall_score >= 60` → **PASS**, else **FAIL**

---

## The 6 Agents

### Wave 1 — Sanity Check

**1. Grammar Agent**
Runs concurrently on every content page (up to 6 pages at a time). Detects spelling mistakes, grammar errors, punctuation issues, and awkward phrasing. Returns the exact verbatim phrases containing each mistake (for UI highlighting), a total mistake count, and a detailed per-page evaluation reasoning.

- Score: `100 − (total_mistakes × 2)`, floor 0
- Rating: HIGH (≥ 80) / MEDIUM (≥ 50) / LOW (< 50)

**2. Novelty Agent**
Uses the **Gemini API directly** with **Google Search grounding** (not OpenRouter) to search for prior work in real-time. Compares the paper's claimed contributions against discovered similar papers and assigns a novelty index.

- Levels: `HIGHLY_NOVEL` → score 90 | `MODERATELY_NOVEL` → 70 | `INCREMENTAL` → 45 | `POTENTIALLY_DERIVATIVE` → 20
- Output: novelty index, list of similar papers, per-contribution verdict, qualitative assessment

**3. Fact-Check Agent**
Acts as a rigorous NeurIPS/IEEE-style reviewer. Verifies factual claims in page-level summaries against established scientific knowledge and flags internal contradictions between pages.

- Error types: `false_claim` (factually wrong) or `mismatch` (contradictions across pages)
- Score: `100 − (errors × 15)`, floor 0

---

### Wave 2 — Fraud Check

**4. Consistency Agent**
Internal consistency audit — cross-references claims, numbers, dataset sizes, and methodology descriptions across sections to detect contradictions.

- Detects: conflicting metrics, different dataset sizes, contradictory claims across sections
- Score: `100 − Σ(severity penalties)` where HIGH=20, MEDIUM=10, LOW=5

**5. Authenticity Agent**
Thinks like a statistical auditor. Detects signs of data fabrication or dishonest reporting by examining results and methodology pages.

- Detects: `too_perfect`, `no_error_bars`, `cherry_picked`, `logical_leap`, `p_hacking`, `no_reproducibility`, `missing_baseline`, and more
- Score: base from overall risk level (NONE/LOW/MEDIUM/HIGH) minus per-flag penalties

---

### Final Stage

**6. Evaluator Agent**
Reads all 5 agent results directly from the DB, computes the weighted overall score, makes one LLM call to produce a synthesis, then builds the full Markdown report programmatically and stores it in the `reports` table.

- LLM generates: `verdict`, `executive_summary`, `novelty_assessment`, `fabrication_risk_level`, `detailed_reasoning`
- Falls back to pure threshold logic (`score >= 60 → PASS`) if the LLM call fails

---

## Final Output — Judgement Report

Retrievable via `GET /api/v1/report/{paper_id}`. The Markdown report contains:

```
# Research Paper Evaluation Report
| Paper ID | Title | Overall Score | Verdict | Generated |

## Executive Summary
3-4 sentence pass/fail recommendation with key rationale.

## Detailed Scores

  1. Consistency        — score, issues list, evaluation reasoning
  2. Grammar            — rating, per-page mistake breakdown
  3. Novelty            — index, similar papers, contributions verified
  4. Fact Check Log     — table: type | page | description | ✅/❌/⚠️
  5. Fabrication Risk   — risk level, risk %, red flags, reasoning

## Final Verdict: ✅ PASS / ❌ FAIL
Full reasoning citing every agent's findings with page references.
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI + Uvicorn |
| Frontend | Streamlit |
| Database | PostgreSQL via NeonDB (asyncpg) |
| PDF extraction | pymupdf4llm + PyMuPDF |
| LLM routing | OpenRouter (Gemini 2.5 Flash primary, free fallbacks) |
| Novelty search | Gemini API + Google Search grounding |
| Config | pydantic-settings + python-dotenv |
| HTTP client | httpx (async) |
| Logging | Rich |

---

## Project Structure

```
research-validator/
├── README.md
├── for-agent.md                    ← codebase map for AI coding agents
├── backend/
│   ├── .env                        ← secrets (gitignored)
│   ├── pyproject.toml
│   └── app/
│       ├── main.py                 ← FastAPI app, lifespan, CORS
│       ├── config.py               ← pydantic-settings (reads backend/.env)
│       ├── constants/
│       │   └── enums.py            ← AgentName, TaskType, AGENT_WEIGHTS, model chains
│       ├── types/
│       │   ├── agent_types.py      ← AgentResult, Finding, TokenUsage
│       │   └── paper_types.py      ← PaperRecord, PageData, PaperMetadata
│       ├── db/
│       │   ├── schema.py           ← DDL, init_db(), migrations
│       │   └── repository.py       ← CRUD for papers, pages, agents, reports
│       ├── extraction/
│       │   ├── arxiv_meta.py
│       │   ├── pdf_downloader.py
│       │   └── pdf_extractor.py
│       ├── structuring/
│       │   └── section_tagger.py
│       ├── services/
│       │   └── llm_service.py      ← OpenRouter client, model chain, retry
│       ├── agents/
│       │   ├── __init__.py         ← orchestration: run_all_agents()
│       │   ├── grammar_agent.py
│       │   ├── novelty_agent.py
│       │   ├── factcheck_agent.py
│       │   ├── consistency_agent.py
│       │   ├── authenticity_agent.py
│       │   └── evaluator_agent.py
│       ├── prompts/
│       │   ├── grammar.py
│       │   ├── novelty.py
│       │   ├── factcheck.py
│       │   ├── consistency.py
│       │   ├── authenticity.py
│       │   ├── evaluator.py
│       │   └── page_tagger.py
│       ├── utils/
│       │   ├── json_parser.py
│       │   ├── logger.py
│       │   └── token_counter.py
│       └── api/
│           ├── routes.py
│           └── schemas.py
└── frontend/
    ├── app.py                      ← Streamlit UI
    └── pyproject.toml
```
