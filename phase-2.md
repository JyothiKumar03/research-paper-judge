# Phase 2 — Structuring, Agents, Pipeline, UI

Everything in Phase 1 is done and verified. Phase 2 wires it all together into a running end-to-end system.

---

## What Phase 1 gave us (ready to use)

- `config.py` — settings from .env
- `constants/` — section tags, agent weights, model list
- `types/` — Pydantic models for paper, agent results, LangGraph state
- `db/` — SQLite schema + full CRUD repository
- `utils/` — logger, token counter (chunking), JSON parser
- `extraction/` — arXiv ID parser, PDF downloader, pymupdf4llm extractor, LaTeX extractor
- `services/llm_service.py` — `call_llm()` with per-model retry + fallback chain

---

## Phase 2 deliverables

### 1. Structuring (`backend/app/structuring/`)

**`section_tagger.py`**
- `tag_pages(pages, llm_models) -> list[TaggedPage]`
- Sends batches of 5 pages to the LLM asking it to classify each page as `ABSTRACT | INTRODUCTION | METHODOLOGY | ...`
- Returns JSON `[{page, tag}]` per batch
- Validation: check returned tags are in `SECTION_TAG_SET`; retry once on bad JSON; fallback tag = `OTHER`
- Vision mode: pages where `images > 0` and `markdown` is suspiciously short (<200 chars) get a screenshot attached via `take_page_screenshot()`
- Concurrency: run batches with `asyncio.gather`, limit to 3 concurrent (rate limit headroom)
- **Prompt lives in** `prompts/section_tagging.py`

**`stitcher.py`**
- `stitch_sections(tagged_pages) -> dict[str, str]`
- Groups pages by tag, concatenates markdown in page order with `\n\n` separator
- Smoothing pass: if a single page is tagged differently from both its neighbours (same tag before and after), re-tag it to match — catches LLM mis-classifications
- Returns `{TAG: full_text}`

**`token_manager.py`**
*(already have `count_tokens` and `chunk_text` in `utils/` — this module adds section-level orchestration)*
- `prepare_sections(sections_dict, max_tokens) -> (token_counts, chunks_dict)`
- Calls `count_tokens()` per section
- Calls `chunk_text()` for any section > `max_section_tokens`
- Returns both counts and chunks so agents can run map-reduce

---

### 2. Prompt Templates (`backend/app/prompts/`)

One file per agent. Each file exports a `build_prompt(...)` function that returns `(system: str, user: str)`.

**`section_tagging.py`** — classify pages into section tags
**`grammar.py`** — evaluate writing quality, return `{score, issues[]}`
**`novelty.py`** — assess uniqueness vs Semantic Scholar results, return `{score, index, closest_work}`
**`factcheck.py`** — identify claims and flag VERIFIED / SUSPICIOUS / UNVERIFIED
**`consistency.py`** — check if methodology supports the results, return `{score, supported[], unsupported[], gaps[]}`
**`authenticity.py`** — assess fabrication risk from statistical patterns, return `{score, risk_pct, flags[]}`
**`executive_summary.py`** — write 2–3 paragraph human-readable narrative from all agent outputs

All prompts end with explicit JSON output format + calibration examples (70 = competent, 90 = excellent, 40 = major issues).

---

### 3. Semantic Scholar service (`backend/app/services/semantic_scholar.py`)

- `search_papers(query, limit=5) -> list[dict]`
  - Hits `https://api.semanticscholar.org/graph/v1/paper/search`
  - Returns `[{title, abstract_snippet, year, citation_count}]`
- `get_paper_by_title(title) -> Optional[dict]`
- Rate limiting: `asyncio.sleep(SEMANTIC_SCHOLAR_RATE_LIMIT_S)` between calls (1 req/sec free)
- Uses `SEMANTIC_SCHOLAR_API_KEY` from config if set (higher rate limit)
- On failure: log warning, return empty list (novelty agent degrades gracefully)

---

### 4. Evaluation Agents (`backend/app/agents/`)

Each agent is an **independent async function** — no class, no inheritance. Takes a payload, returns `AgentResult`.

#### Pattern (same for all agents)
```python
async def evaluate_<name>(
    sections: dict[str, str],      # {TAG: content}
    chunks: dict[str, list[str]],  # pre-chunked for sections > 12K
    llm_models: list[ModelConfig], # retry/fallback chain
    **kwargs,                      # agent-specific extras
) -> AgentResult:
    t0 = time.perf_counter()
    try:
        # build prompt → call_llm → parse_llm_json → build findings
        return AgentResult(agent_name="...", score=..., findings=..., ...)
    except Exception as exc:
        log.error("evaluate_<name>: failed — %s", exc)
        return AgentResult(agent_name="...", status="failed", error_msg=str(exc))
```

**`grammar_agent.py`** — `evaluate_grammar(sections, chunks, llm_models)`
- Map: call LLM once per chunk of each section (skip REFERENCES / APPENDIX)
- Reduce: average scores, merge findings lists
- Output: `{score: 0-100, findings: [{category, location, severity, description}]}`

**`novelty_agent.py`** — `evaluate_novelty(sections, chunks, llm_models)`
- Step 1: extract claimed contributions from ABSTRACT + INTRODUCTION (1 LLM call)
- Step 2: search Semantic Scholar for each contribution (2–3 queries)
- Step 3: LLM assesses novelty vs search results (1 LLM call)
- Output: `{score, novelty_index: str, closest_work: str}`

**`factcheck_agent.py`** — `evaluate_factcheck(sections, chunks, llm_models)`
- Runs on METHODOLOGY + RESULTS + INTRODUCTION
- Each chunk: LLM extracts claims, classifies as VERIFIED / SUSPICIOUS / UNVERIFIED
- Output: `{score, findings: [{claim, verdict, reason}]}`

**`consistency_agent.py`** — `evaluate_consistency(sections, chunks, llm_models, factcheck_flags)`
- Runs after Wave 1 (needs factcheck output)
- If METHODOLOGY + RESULTS combined > 12K: compress the larger one first (1 extra LLM call)
- Checks: do results match methodology? are all described experiments reported?
- Output: `{score, supported[], unsupported[], gaps[]}`

**`authenticity_agent.py`** — `evaluate_authenticity(sections, chunks, llm_models, factcheck_flags)`
- Runs after Wave 1 (uses fact-check red flags)
- Checks: statistical plausibility, too-good-to-be-true results, suspicious rounding/precision
- Deliberately conservative prompting to avoid false accusations
- Output: `{score, fabrication_risk_pct, anomalies[]}`

**`executive_summary_agent.py`** — `generate_executive_summary(scores, all_results, llm_models)`
- 1 LLM call using all agent scores + top findings
- Returns 2–3 paragraph narrative (not a re-evaluation — just narrative)

---

### 5. LangGraph Pipeline (`backend/app/graph/`)

**`state.py`** — `PaperEvalState` TypedDict (already defined in `types/state_types.py`, re-export here)

**`nodes.py`** — one async function per graph node:

| Node | What it does | Uses |
|------|-------------|------|
| `parse_url_node` | `extract_arxiv_id()`, validate | `extraction.arxiv_meta` |
| `fetch_metadata_node` | arXiv API call | `extraction.arxiv_meta` |
| `extract_content_node` | Try LaTeX → PDF fallback | `extraction.*` |
| `tag_sections_node` | LLM page classification (PDF path only) | `structuring.section_tagger` |
| `stitch_sections_node` | Concatenate pages by tag | `structuring.stitcher` |
| `store_sections_node` | Write to SQLite | `db.repository` |
| `token_budget_node` | Count + chunk sections | `structuring.token_manager` |
| `wave1_node` | `asyncio.gather(grammar, novelty, factcheck)` | `agents.*` |
| `wave2_node` | `consistency` then `authenticity` (sequential) | `agents.*` |
| `aggregate_node` | Weighted score, PASS/FAIL verdict (no LLM) | `constants.weights` |
| `executive_summary_node` | 1 LLM call for narrative | `agents.executive_summary_agent` |
| `generate_report_node` | Fill markdown template, render PDF | `services.report_generator` |
| `store_report_node` | Write report to SQLite | `db.repository` |

Each node pushes a `ProgressEvent` to `app.state.progress_queues[paper_id]` so the frontend can poll progress.

**`pipeline.py`** — build + compile the graph:

```
START
  → parse_url
  → fetch_metadata
  → extract_content
  → (conditional: "latex" → stitch_sections | "pdf" → tag_sections → stitch_sections)
  → store_sections
  → token_budget
  → wave1          (grammar | novelty | factcheck run in parallel inside wave1_node)
  → wave2          (consistency → authenticity sequential inside wave2_node)
  → aggregate
  → executive_summary
  → generate_report
  → store_report
  → END
```

Conditional edges:
- After `extract_content`: if `extraction_path == "latex"` skip `tag_sections`
- After any node: if `status == "failed"` route to END

---

### 6. Report Generator (`backend/app/services/report_generator.py`)

**`generate_markdown_report(paper, agent_results, summary, scores, verdict) -> str`**
- Fills `templates/report_template.md` with f-string substitution
- Renders findings as bullet lists per agent

**`generate_pdf(markdown_text) -> bytes`**
- Uses `fpdf2` to render the markdown as a simple PDF
- Returns raw PDF bytes (caller writes to response or file)

**`templates/report_template.md`**
Markdown template with `{placeholders}` for all dynamic content.

---

### 7. API (`backend/app/api/`)

**`schemas.py`** — Pydantic request/response models:
```python
class EvaluateRequest(BaseModel):
    arxiv_url: str

class EvaluateResponse(BaseModel):
    paper_id: str
    stream_url: str    # /api/v1/evaluate/{id}/status

class StatusResponse(BaseModel):
    paper_id: str
    status: str        # "running" | "completed" | "failed"
    current_step: str
    progress_pct: int  # 0-100
    result: Optional[dict]   # populated when status == "completed"
```

**`routes.py`** — full implementation:

| Endpoint | Implementation |
|----------|---------------|
| `POST /evaluate` | Extract paper_id, create progress queue, launch graph as `BackgroundTask`, return paper_id |
| `GET /evaluate/{id}/status` | Read from progress queue or SQLite, return `StatusResponse` |
| `GET /report/{id}` | Query SQLite `reports` table, return markdown |
| `GET /report/{id}/pdf` | Generate PDF from stored markdown, stream bytes |

Progress polling (Streamlit-friendly): Streamlit polls `/status` every 2 seconds.
No SSE needed — polling is simpler and more reliable with Streamlit's execution model.

---

### 8. Streamlit Frontend (`frontend/app.py`)

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  Sidebar: backend URL | health check            │
│           past evaluations list                 │
├─────────────────────────────────────────────────┤
│  [arXiv URL input]         [Evaluate button]    │
│                                                 │
│  Progress panel (polling):                      │
│    ✅ Fetched metadata: "Attention Is All..."   │
│    ✅ Extracted 15 pages (LaTeX path)           │
│    ✅ Stitched 7 sections                       │
│    ⏳ Running agents...                         │
│                                                 │
│  Results (after completion):                    │
│  ┌──────────┬──────────────────────────────┐   │
│  │ PASS 82  │ Consistency  88  ████████░░  │   │
│  │          │ Authenticity 79  ███████░░░  │   │
│  │          │ Novelty      91  █████████░  │   │
│  │          │ Fact-Check   74  ███████░░░  │   │
│  │          │ Grammar      85  ████████░░  │   │
│  └──────────┴──────────────────────────────┘   │
│                                                 │
│  Executive Summary (expandable)                 │
│  Detailed Findings per agent (expandable)       │
│  [Download Markdown] [Download PDF]             │
└─────────────────────────────────────────────────┘
```

**`components/progress_tracker.py`** — polls `/status`, updates `st.progress()` + step messages
**`components/report_viewer.py`** — renders scores, findings, download buttons

---

## Build order for Phase 2

```
1. prompts/          (no dependencies — pure strings)
2. structuring/      (uses utils/ + types/ + services/llm_service)
3. services/semantic_scholar.py  (no LLM dependency)
4. agents/           (uses structuring + services + prompts)
5. graph/            (uses agents + db + extraction)
6. services/report_generator.py  (uses types + db)
7. api/schemas.py + api/routes.py  (uses graph + db)
8. frontend/         (calls API)
```

---

## Testing plan for Phase 2

| Test | What to verify |
|------|---------------|
| Section tagger | Feed known pages from "Attention Is All You Need" → check METHODOLOGY and RESULTS are correctly tagged |
| Stitcher smoothing | Inject a mis-tagged page between two same-tag pages → verify it gets corrected |
| Grammar agent | Mock LLM returning known JSON → verify map-reduce averages correctly |
| Novelty agent | Mock Semantic Scholar + LLM → verify findings structure |
| Factcheck agent | Feed a section with a known false claim → verify SUSPICIOUS flag |
| Consistency agent | Feed mismatched methodology/results → verify unsupported claims |
| Authenticity agent | Feed suspicious result numbers → verify HIGH_RISK flag |
| Full pipeline | Run on 1706.03762 with mocked LLM → all 5 agents produce results, report generated |
| API | `POST /evaluate` with real arXiv URL → status polling → `/report` returns markdown |
| Frontend | Input 1706.03762, watch progress update, verify report renders |

---

## Edge cases to handle in Phase 2

| Edge case | Where handled |
|-----------|--------------|
| LaTeX source returns 404 | `latex_extractor.try_latex_extraction()` returns `None` → PDF fallback in `extract_content_node` |
| LLM returns bad JSON | `json_parser.parse_llm_json()` with 3-strategy fallback (already built) |
| Section > 12K tokens | `token_manager.prepare_sections()` → `chunk_text()` → agent map-reduce |
| All Wave 1 agents fail | `aggregate_node` logs error, returns score=0, verdict=FAIL |
| Semantic Scholar timeout | Returns `[]`, novelty agent notes "external search unavailable" in findings |
| Paper has no METHODOLOGY section | Consistency agent uses RELATED_WORK or INTRODUCTION as fallback |
| Very short paper (<5 pages) | All sections likely fit in one chunk — no map-reduce needed |
| Non-English paper | Grammar agent detects language, notes it, does not penalise score |
