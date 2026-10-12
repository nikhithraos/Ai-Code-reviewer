import difflib
import streamlit as st
from llm import get_provider
from orchestrator import ReviewManager, build_markdown

ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "⚪"}

st.set_page_config(page_title="Agentic Code Reviewer", layout="wide")
st.title("🤖 Agentic AI Code Review & Developer Assistant")

with st.sidebar:
    st.header("Settings")
    model = st.text_input("Ollama model", "qwen2.5-coder:7b")
    parallel = st.checkbox("Run agents in parallel", value=False)
    quick = st.checkbox("Quick verify (skip LLM re-review)", value=True)

code = st.text_area("Paste your Python code", height=300)
upload = st.file_uploader("...or upload a .py file", type=["py"])
if upload:
    code = upload.read().decode("utf-8")

if st.button("▶ Run Review") and code.strip():
    manager = ReviewManager(get_provider("ollama", model=model), parallel=parallel)
    with st.spinner("Agents are reviewing your code..."):
        st.session_state["result"] = manager.run_pipeline(code, quick_verify=quick)
        st.session_state["original"] = code

if "result" in st.session_state:
    r, original = st.session_state["result"], st.session_state["original"]

    cols = st.columns(4)
    for col, sev in zip(cols, ["Critical", "High", "Medium", "Low"]):
        col.metric(f"{ICON[sev]} {sev}", sum(f.severity.value == sev for f in r.initial))

    tab1, tab2, tab3 = st.tabs(["Findings", "Improved Code", "Final Report"])

    with tab1:
        st.caption(f"Detected language: {r.language}")
        for f in r.initial:
            with st.expander(f"{f.id} {ICON[f.severity.value]} {f.title} (line {f.line_start})"):
                st.write(f"**Category:** {f.category.value} · **Source:** {f.source}")
                st.write(f.explanation)
                st.info(f"Suggested fix: {f.suggested_fix}")

    with tab2:
        if r.fix:
            st.code(r.fix.improved_code, language="python")
            diff = "\n".join(difflib.unified_diff(
                original.splitlines(), r.fix.improved_code.splitlines(),
                "original", "improved", lineterm=""))
            st.subheader("Diff")
            st.code(diff or "No changes", language="diff")
            st.subheader("What changed")
            for c in r.fix.changes:
                st.write(f"- {c}")
        else:
            st.info("No fix generated.")

    with tab3:
        if not r.comparison_reliable:
            st.warning("Some agents failed or timed out, so the resolved/new comparison is unreliable. Re-run.")
            st.success(f"Resolved ({len(r.resolved)}): {[f.title for f in r.resolved]}")
            st.warning(f"Remaining ({len(r.remaining)}): {[f.title for f in r.remaining]}")
            st.error(f"Newly introduced ({len(r.introduced)}): {[f.title for f in r.introduced]}")
        for e in r.errors:
            st.caption(f"⚠ {e}")
        st.download_button("Download report (Markdown)", build_markdown(r), "report.md")