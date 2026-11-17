import streamlit as st

from components.ui import empty_state, page_setup, project_selector, show_error
from services.api_client import ApiError
from state.session import client

page_setup(
    "AI Assistant",
    "Ask questions about this project's documents. Answers cite document and page, or say evidence is missing.",
)
project = project_selector()
if not project:
    st.stop()
pid = project["id"]
hist_key = f"chat_{pid}"
history = st.session_state.setdefault(hist_key, [])
if not history:
    empty_state("Ask a question", "For example: What warranty does the policy require for IT hardware?")
for turn in history:
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
        a = turn["a"]
        st.write(a["answer"])
        label = {
            "llm": "Model-generated answer, citations verified",
            "extractive": "Extractive summary of retrieved passages (no language model used)",
            "insufficient_evidence": "No supporting evidence found",
        }[a["mode"]]
        st.caption(label)
        for c in a["citations"]:
            with st.expander(f"[{c['marker']}] {c['filename']} - page {c['page']} (relevance {c['score']:.2f})"):
                st.markdown(f"<div class='pa-src'>{c['snippet']}</div>", unsafe_allow_html=True)
q = st.chat_input("Ask about the tender, quotations or policies")
if q:
    try:
        with st.spinner("Searching your documents..."):
            history.append({"q": q, "a": client().ask(pid, q)})
        st.rerun()
    except ApiError as exc:
        show_error(exc)
