"""
Research Validator — Streamlit Frontend

Two entry points:
  1. Submit a new arXiv paper URL → full pipeline evaluation
  2. Load an existing report by paper_id (UUID)

Backend: FastAPI at BACKEND_URL (default http://localhost:8000)
"""

import json
import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 300  # seconds — evaluation pipeline can be slow

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Research Validator",
    page_icon="🔬",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Settings")
    backend_url = st.text_input("Backend URL", value=BACKEND_URL, key="backend_url_input")
    st.divider()

    if st.button("🩺 Check Backend Health", use_container_width=True):
        try:
            r = httpx.get(f"{backend_url}/api/v1/health", timeout=5)
            if r.status_code == 200:
                st.success(f"Backend online ✅")
            else:
                st.error(f"HTTP {r.status_code}")
        except Exception as exc:
            st.error(f"Unreachable: {exc}")

    st.divider()
    st.markdown(
        "**Pipeline**\n"
        "1. Extract PDF pages\n"
        "2. Tag sections (LLM)\n"
        "3. Grammar · Novelty · Fact-check\n"
        "4. Consistency · Authenticity\n"
        "5. Evaluator → final report"
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base() -> str:
    return st.session_state.get("backend_url_input", BACKEND_URL).rstrip("/")


def _get(path: str) -> dict:
    r = httpx.get(f"{_base()}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> dict:
    r = httpx.post(f"{_base()}{path}", json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _verdict_badge(verdict: str | None) -> str:
    if verdict == "PASS":
        return "🟢 **PASS**"
    if verdict == "FAIL":
        return "🔴 **FAIL**"
    return "⚪ _Pending_"


def _score_color(score: float | None) -> str:
    if score is None:
        return "—"
    color = "green" if score >= 70 else ("orange" if score >= 50 else "red")
    return f":{color}[**{score:.1f} / 100**]"


AGENT_ICONS = {
    "grammar":       "✏️",
    "novelty":       "💡",
    "factcheck":     "🔍",
    "consistency":   "🔗",
    "authenticity":  "🛡️",
}

SEVERITY_ICONS = {
    "HIGH":   "🔴",
    "MEDIUM": "🟡",
    "LOW":    "🟢",
}

# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def render_paper_header(paper: dict, report: dict | None) -> None:
    verdict = report.get("verdict") if report else None
    score   = report.get("overall_score") if report else None

    col_title, col_verdict, col_score = st.columns([5, 1, 1])
    with col_title:
        st.subheader(paper.get("title", "—"))
        st.caption(
            f"**arXiv ID:** `{paper.get('arxiv_id', '—')}`  |  "
            f"**Paper ID:** `{paper.get('id', paper.get('paper_id', '—'))}`  |  "
            f"**Pages:** {paper.get('page_count', '—')}  |  "
            f"**Submitted:** {paper.get('submitted_date', '—')}"
        )
        authors = paper.get("authors", [])
        if isinstance(authors, str):
            authors = json.loads(authors)
        if authors:
            st.caption("**Authors:** " + ", ".join(authors))
    with col_verdict:
        st.markdown("**Verdict**")
        st.markdown(_verdict_badge(verdict))
    with col_score:
        st.markdown("**Score**")
        st.markdown(_score_color(score))


def render_report_tab(report: dict) -> None:
    exec_summary = report.get("executive_summary", "")
    if exec_summary:
        st.markdown("### Executive Summary")
        st.info(exec_summary)
        st.divider()

    markdown_report = report.get("markdown_report", "")
    if markdown_report:
        st.markdown("### Full Report")
        st.markdown(markdown_report, unsafe_allow_html=False)
    else:
        st.warning("No markdown report available yet.")


def render_agent_tab(agent: dict) -> None:
    score  = agent.get("score")
    status = agent.get("status", "—")
    name   = agent.get("agent_name", "—")

    col_score, col_status = st.columns([1, 1])
    with col_score:
        st.metric("Score", f"{score:.1f} / 100" if score is not None else "—")
    with col_status:
        st.metric("Status", status.upper())

    # Findings
    findings = agent.get("findings", [])
    if isinstance(findings, str):
        findings = json.loads(findings)

    st.markdown(f"#### Findings ({len(findings)})")
    if findings:
        for f in findings:
            sev   = f.get("severity", "LOW")
            icon  = SEVERITY_ICONS.get(sev, "⚪")
            cat   = f.get("category", "")
            loc   = f.get("location", "")
            desc  = f.get("description", "")
            st.markdown(f"{icon} `{cat}` — {desc} *({loc})*")
    else:
        st.success("No findings — all checks passed.")

    # Raw reasoning
    raw_output = agent.get("raw_output", "")
    if raw_output:
        with st.expander("🔧 Raw agent output"):
            try:
                parsed = json.loads(raw_output) if raw_output.startswith("{") else eval(raw_output)
                reasoning = parsed.get("evaluation_reasoning", "")
                if isinstance(reasoning, dict):
                    st.markdown("**Page-by-page reasoning:**")
                    for page_no, text in reasoning.items():
                        st.markdown(f"**Page {page_no}:** {text}")
                elif reasoning:
                    st.markdown(reasoning)
                else:
                    st.json(parsed)
            except Exception:
                st.text(raw_output[:2000])


def render_full_results(paper: dict, report: dict | None, agents: list[dict]) -> None:
    render_paper_header(paper, report)
    st.divider()

    # Build tab labels
    agent_labels = [
        f"{AGENT_ICONS.get(a['agent_name'], '🤖')} {a['agent_name'].capitalize()}"
        for a in agents
    ]
    tab_labels = ["📄 Report"] + agent_labels
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        if report:
            render_report_tab(report)
        else:
            st.warning("Report not generated yet. Run evaluation first.")

    for i, agent in enumerate(agents, start=1):
        with tabs[i]:
            render_agent_tab(agent)


# ---------------------------------------------------------------------------
# Load by paper_id
# ---------------------------------------------------------------------------

def load_by_paper_id(paper_id: str) -> None:
    paper_id = paper_id.strip()
    if not paper_id:
        st.warning("Enter a paper ID.")
        return

    with st.spinner("Fetching paper data…"):
        try:
            paper = _get(f"/api/v1/paper/{paper_id}")
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            st.error(f"Paper not found: {detail}")
            return
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            return

    report = None
    with st.spinner("Fetching report…"):
        try:
            report = _get(f"/api/v1/report/{paper_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                st.warning(f"Report fetch error: {exc.response.json().get('detail', str(exc))}")
        except Exception as exc:
            st.warning(f"Report fetch failed: {exc}")

    agents = []
    with st.spinner("Fetching agent results…"):
        try:
            data = _get(f"/api/v1/agents/{paper_id}")
            agents = data.get("agents", [])
        except Exception as exc:
            st.warning(f"Agent results fetch failed: {exc}")

    st.session_state["result"] = {"paper": paper, "report": report, "agents": agents}


# ---------------------------------------------------------------------------
# Submit new paper
# ---------------------------------------------------------------------------

def submit_paper(url: str) -> None:
    url = url.strip()
    if not url:
        st.warning("Enter an arXiv URL.")
        return

    with st.spinner("Running full evaluation pipeline… this can take 2-5 minutes ⏳"):
        try:
            data = _post("/api/v1/evaluate", {"arxiv_url": url})
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            st.error(f"Evaluation failed: {detail}")
            return
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            return

    paper_id = data.get("paper_id", "")
    st.success(f"Evaluation complete! Paper ID: `{paper_id}`")

    # Now load the full results using the returned paper_id
    load_by_paper_id(paper_id)


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

st.title("🔬 Research Paper Validator")
st.caption("Submit an arXiv paper for AI-powered peer review, or load an existing report.")

st.divider()

col_submit, col_load = st.columns(2)

with col_submit:
    st.subheader("📥 Submit New Paper")
    arxiv_url = st.text_input(
        "arXiv URL",
        placeholder="https://arxiv.org/abs/1706.03762",
        key="arxiv_url_input",
    )
    if st.button("🚀 Evaluate Paper", type="primary", use_container_width=True, key="submit_btn"):
        submit_paper(arxiv_url)

with col_load:
    st.subheader("🔎 Load Existing Report")
    paper_id_input = st.text_input(
        "Paper ID (UUID)",
        placeholder="e.g. a3f2c1d4-...",
        key="paper_id_input",
    )
    if st.button("📂 Load Report", use_container_width=True, key="load_btn"):
        load_by_paper_id(paper_id_input)

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

if "result" in st.session_state:
    st.divider()
    result = st.session_state["result"]
    render_full_results(
        paper=result["paper"],
        report=result["report"],
        agents=result["agents"],
    )
