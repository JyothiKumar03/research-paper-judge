# Codebase Guide for AI Agents

This file is a navigation map for AI coding agents working on this repository.
Read this first before exploring any files.

---

## What this project is

A FastAPI backend + Streamlit frontend that evaluates arXiv research papers using 6 AI agents.
Submit an arXiv URL → get a PASS/FAIL Judgement Report with scored dimensions.

Language: **Python 3.11+**
Package manager: **uv**
DB: **PostgreSQL (NeonDB)** via asyncpg — no ORM
LLM: **OpenRouter** (Gemini 2.5 Flash primary) + **Gemini API** directly (novelty agent only)

---

## Directory Layout

```
research-validator/
├── backend/               ← all server-side code
│   ├── .env               ← secrets (OPENROUTER_API_KEY, GEMINI_API_KEY, DATABASE_URL)
│   ├── pyproject.toml     ← dependencies
│   └── app/               ← Python package root
│       ├── main.py
│       ├── config.py
│       ├── constants/
│       ├── types/
│       ├── db/
│       ├── extraction/
│       ├── structuring/
│       ├── services/
│       ├── agents/
│       ├── prompts/
│       ├── utils/
│       └── api/
└── frontend/
    ├── app.py             ← Streamlit UI
    └── pyproject.toml
```

---

## Key Files — What Each Does

### Entry Points

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app creation, lifespan (DB pool init/close), CORS middleware |
| `frontend/app.py` | Streamlit UI — submits arXiv URL to backend, displays report |

---

### Configuration

| File | Purpose |
|------|---------|
| `backend/app/config.py` | `Settings` class (pydantic-settings). Reads `backend/.env`. Exports singleton `settings`. |
| `backend/app/constants/enums.py` | **The single source of truth for all constants.** Contains: `AgentName`, `TaskType`, `ModelID`, `TASK_MODEL_CHAIN`, `AGENT_WEIGHTS`, `PASS_THRESHOLD`, `Verdict`, `AgentStatus`, `SectionTag`, `NoveltyIndex`, `FindingSeverity`, `RiskLevel`, and more. Always check here before adding new enums or constants. |

---

### Types / Models

| File | Purpose |
|------|---------|
| `backend/app/types/agent_types.py` | `AgentResult`, `Finding`, `TokenUsage`, `LLMResponse` — the core data contracts between agents and DB |
| `backend/app/types/paper_types.py` | `PaperRecord`, `PageData`, `PaperMetadata`, `SectionData` — paper ingestion types |

**`AgentResult` shape** (every agent returns this):
```python
AgentResult(
    agent_name: AgentName,
    score: float,              # 0.0 – 100.0
    findings: list[Finding],   # category, location, description, severity
    usage: TokenUsage,
    duration_s: float,
    status: AgentStatus,       # COMPLETED | FAILED | SKIPPED
    error_msg: str | None,
    raw_output: str,           # str(dict) — contains evaluation_reasoning
)
```

The `raw_output` field is `str(dict)`. Parse it with `ast.literal_eval()` to get the structured dict back. Every agent stores `evaluation_reasoning` inside this dict.

---

### Database

| File | Purpose |
|------|---------|
| `backend/app/db/schema.py` | DDL for all 5 tables + `init_db()` + migration list. Run at startup. |
| `backend/app/db/repository.py` | All DB CRUD. Import these functions directly — no ORM. |
| `backend/app/db/__init__.py` | Re-exports all repository functions for easy import. |

**Tables:**
- `papers` — one row per submitted paper (UUID `id` + `arxiv_id`)
- `pages` — one row per extracted page with `page_tag`, `page_summary`, `markdown`, `image_data`
- `sections` — stitched section content by tag
- `agent_results` — one row per (paper_id, agent_name) — score, findings JSON, raw_output, status
- `reports` — one row per paper — overall_score, verdict, weights_json, scores_json, executive_summary, markdown_report

**Useful DB functions:**
```python
from app.db import (
    get_paper,              # → dict | None
    get_pages_by_paper,     # → list[dict]  (ordered by page_num)
    get_agent_results,      # → list[dict]  (findings already parsed from JSON)
    get_agent_result_by_name,
    insert_agent_result,    # takes AgentResult pydantic model
    insert_report,          # takes raw fields: overall_score, verdict, weights, scores, ...
    get_report,             # → dict | None
)
```

---

### LLM Service

| File | Purpose |
|------|---------|
| `backend/app/services/llm_service.py` | `call_llm()`, `build_model_chain()`, `LLMExhaustedError`. Handles OpenRouter API calls, retry logic, model fallback chain. |

**How to call the LLM:**
```python
from app.services.llm_service import build_model_chain, call_llm, LLMExhaustedError
from app.constants import TaskType

models = build_model_chain(TaskType.GRAMMAR)  # returns ordered list of ModelIDs for this task
resp = await call_llm(prompt, models, system=SYSTEM_PROMPT, json_schema=MY_SCHEMA)
# resp.content  → str (LLM output)
# resp.usage    → TokenUsage
```

**Model chains** are defined in `TASK_MODEL_CHAIN` in `enums.py`. Each `TaskType` maps to an ordered list of `ModelID`s — the service tries them in order until one succeeds.

**Note:** The **Novelty Agent** calls the Gemini API directly (not via OpenRouter) to use Google Search grounding. See `agents/novelty_agent.py:_call_gemini_with_grounding()`.

---

### Agents

| File | Purpose |
|------|---------|
| `backend/app/agents/__init__.py` | Orchestration: `run_sanity_check()` (wave 1), `run_fraud_check()` (wave 2), `run_all_agents()` (both + evaluator) |
| `backend/app/agents/grammar_agent.py` | Per-page grammar check, runs pages concurrently (semaphore=6) |
| `backend/app/agents/novelty_agent.py` | Originality check via Gemini + Google Search grounding |
| `backend/app/agents/factcheck_agent.py` | Factual accuracy check on page summaries |
| `backend/app/agents/consistency_agent.py` | Internal consistency check across sections |
| `backend/app/agents/authenticity_agent.py` | Fraud/fabrication detection |
| `backend/app/agents/evaluator_agent.py` | Reads all 5 from DB → weighted score → LLM synthesis → markdown report → insert_report() |

**Every agent except evaluator has the same signature:**
```python
async def run(pool: asyncpg.Pool, paper_id: str) -> AgentResult
```

**Evaluator agent signature:**
```python
async def run(pool: asyncpg.Pool, paper_id: str) -> dict
# returns {"overall_score": float, "verdict": str, "duration_s": float}
# side effect: calls insert_report() to store report in DB
```

**Wave execution in `__init__.py`:**
```python
# Wave 1 + Wave 2 run in parallel via asyncio.gather()
# Evaluator runs after both waves complete
# Evaluator fetches agent data from DB (not from in-memory results)
```

---

### Prompts

Every prompt file exports:
- A `*_SYSTEM` string (system prompt)
- A `*_JSON_SCHEMA` dict (OpenAI-style structured output schema, strict mode)
- A `build_*_prompt()` function

| File | Key exports |
|------|-------------|
| `prompts/grammar.py` | `GRAMMAR_SYSTEM`, `GRAMMAR_JSON_SCHEMA`, `build_grammar_prompt(markdown, page_tag, title)`, `_SKIP_TAGS` |
| `prompts/novelty.py` | `NOVELTY_SYSTEM`, `build_novelty_prompt(title, abstract, intro)` — no JSON schema (Gemini direct) |
| `prompts/factcheck.py` | `FACTCHECK_SYSTEM`, `FACTCHECK_JSON_SCHEMA`, `build_factcheck_prompt(title, page_summaries)` |
| `prompts/consistency.py` | `CONSISTENCY_SYSTEM`, `CONSISTENCY_JSON_SCHEMA`, `build_consistency_prompt(title, methodology_pages, results_pages)` |
| `prompts/authenticity.py` | `AUTHENTICITY_SYSTEM`, `AUTHENTICITY_JSON_SCHEMA`, `build_authenticity_prompt(title, results_pages, methodology_pages)` |
| `prompts/evaluator.py` | `EVALUATOR_SYSTEM`, `EVALUATOR_JSON_SCHEMA`, `build_evaluator_prompt(title, agent_data, overall_score, grammar_rating, novelty_label, fabrication_risk_pct)` |
| `prompts/page_tagger.py` | Used by `section_tagger.py` for LLM-based page tagging |

**All LLM JSON schemas use strict mode** (`"strict": True`, `"additionalProperties": False`).
Every agent's JSON schema now includes an `evaluation_reasoning` field — a detailed narrative the LLM must fill in.

---

### API Layer

| File | Purpose |
|------|---------|
| `backend/app/api/routes.py` | All FastAPI route handlers. Imports `run_all_agents` and DB functions. |
| `backend/app/api/schemas.py` | Pydantic models for API request/response bodies. |

**Current endpoints:**
```
POST /api/v1/evaluate                → EvaluateResponse (paper_id, verdict, overall_score, agent_scores)
POST /api/v1/run-eval/{paper_id}     → RunEvalResponse  (same fields + agents list)
GET  /api/v1/evaluate/{paper_id}/status
GET  /api/v1/paper/{paper_id}
GET  /api/v1/agents/{paper_id}
GET  /api/v1/report/{paper_id}       → full report dict (includes markdown_report)
GET  /api/v1/health
```

---

### Utils

| File | Purpose |
|------|---------|
| `utils/json_parser.py` | `parse_llm_json(text, fallback)` — strips markdown fences, parses JSON. `extract_score(text)` — regex fallback for score extraction. |
| `utils/logger.py` | Rich logger. `get_logger(__name__)` for any module. |
| `utils/token_counter.py` | Token counting utilities. |

---

## Data Flow Summary

```
POST /api/v1/evaluate
    │
    ├─ extract_arxiv_id()           → "1706.03762"
    ├─ fetch_metadata()             → PaperMetadata
    ├─ download_pdf()               → tmp Path
    ├─ extract_pages()              → list[PageData]
    ├─ insert_paper()               → papers table
    ├─ tag_all_pages()              → list[PageData] with page_tag set, pages table updated
    │
    └─ run_all_agents(pool, paper_id)
            │
            ├─ [parallel] grammar_agent.run()       → agent_results table
            ├─ [parallel] factcheck_agent.run()     → agent_results table
            ├─ [parallel] novelty_agent.run()       → agent_results table
            ├─ [parallel] consistency_agent.run()   → agent_results table
            ├─ [parallel] authenticity_agent.run()  → agent_results table
            │
            └─ evaluator_agent.run()
                    │
                    ├─ get_agent_results()           ← reads from agent_results table
                    ├─ compute weighted score
                    ├─ call_llm() → verdict + summary + reasoning
                    ├─ _build_markdown() → full report string
                    └─ insert_report()               → reports table
```

---

## Common Patterns

### Adding a new field to an agent's output

1. Add the field to the agent's `*_JSON_SCHEMA` in `prompts/*.py`
2. Mention it in the prompt text and system prompt
3. Extract it from `parsed` in the agent file
4. Include it in `raw_output=str({...})`

### Adding a new agent

1. Create `agents/my_agent.py` with `async def run(pool, paper_id) -> AgentResult`
2. Create `prompts/my_agent.py` with system prompt + JSON schema + prompt builder
3. Add `AgentName.MY_AGENT = "my_agent"` to `constants/enums.py`
4. Add a `TaskType` and model chain entry to `TASK_MODEL_CHAIN`
5. Add the CHECK constraint in `schema.py` → `agent_name IN (..., 'my_agent')`
6. Wire it into `agents/__init__.py`

### Parsing raw_output from DB

Every agent stores `raw_output` as `str(dict)`. To parse:
```python
import ast
raw = {}
try:
    if row["raw_output"]:
        raw = ast.literal_eval(row["raw_output"])
except Exception:
    pass
reasoning = raw.get("evaluation_reasoning", "")
```

### Checking what models are available

See `ModelID` and `TASK_MODEL_CHAIN` in `backend/app/constants/enums.py`.
Models without JSON schema support are listed in `NO_SCHEMA_MODELS`.

---

## What NOT to touch without reading first

| File | Why |
|------|-----|
| `db/schema.py` | DDL changes require migrations. Always add to `_MIGRATIONS`, never alter `_ALL_DDL` in-place for existing columns. |
| `constants/enums.py` | Every agent, model, and weight lives here. Changes ripple everywhere. |
| `services/llm_service.py` | Retry logic and model fallback is carefully tuned. Don't change call semantics. |
| `agents/__init__.py` | Controls wave parallelism. Changing execution order affects correctness. |
