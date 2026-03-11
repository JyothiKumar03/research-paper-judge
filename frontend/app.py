"""
Research Validator — Streamlit Frontend

Calls the FastAPI backend at BACKEND_URL (default: http://localhost:8000).
"""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Research Validator",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Research Validator")
st.caption("Powered by LangGraph agents + FastAPI")

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Settings")
    backend_url = st.text_input("Backend URL", value=BACKEND_URL)
    st.divider()
    st.markdown(
        "**How it works**\n"
        "1. **Plan** — agent designs a research plan\n"
        "2. **Search** — agent gathers evidence\n"
        "3. **Validate** — fact-checker reviews findings\n"
        "4. **Summarize** — final report with confidence rating"
    )

    # Health check
    if st.button("Check Backend Health"):
        try:
            r = httpx.get(f"{backend_url}/api/v1/health", timeout=5)
            if r.status_code == 200:
                st.success(f"Backend online ✅  ({r.json()['status']})")
            else:
                st.error(f"Backend returned {r.status_code}")
        except Exception as exc:
            st.error(f"Cannot reach backend: {exc}")

# ---------------------------------------------------------------------------
# Main — query input
# ---------------------------------------------------------------------------

query = st.text_area(
    "Enter your research query",
    placeholder="e.g. What are the latest breakthroughs in quantum computing in 2024?",
    height=120,
)

run_btn = st.button("🚀 Run Research", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Run agent
# ---------------------------------------------------------------------------

if run_btn:
    if not query.strip():
        st.warning("Please enter a research query.")
        st.stop()

    with st.spinner("Running research agent pipeline... this may take a moment."):
        try:
            response = httpx.post(
                f"{backend_url}/api/v1/research",
                json={"query": query.strip()},
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            st.error(f"Backend error: {detail}")
            st.stop()
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            st.stop()

    st.success("Research complete!")
    st.divider()

    # Results layout
    col1, col2 = st.columns([1, 1])

    with col1:
        with st.expander("📋 Research Plan", expanded=True):
            st.markdown(data["plan"])

        with st.expander("🔍 Search Findings", expanded=True):
            for i, finding in enumerate(data["search_results"], 1):
                st.markdown(f"**{i}.** {finding}")

    with col2:
        with st.expander("✅ Validation Notes", expanded=True):
            st.markdown(data["validation"])

        with st.expander("📝 Final Summary", expanded=True):
            st.markdown(data["summary"])

    # Raw JSON toggle
    with st.expander("🔧 Raw JSON response"):
        st.json(data)
