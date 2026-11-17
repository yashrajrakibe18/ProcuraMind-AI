import pandas as pd
import streamlit as st

from components.ui import empty_state, page_setup, show_error
from services.api_client import ApiError
from state.session import client

page_setup("Projects", "Each project is one tender with its quotations, policies and analyses.")
with st.expander("Create a project", expanded=False):
    with st.form("new_project", clear_on_submit=True):
        title = st.text_input("Title", max_chars=255)
        desc = st.text_area("Description", max_chars=4000)
        if st.form_submit_button("Create project", type="primary"):
            try:
                p = client().create_project(title, desc)
                st.session_state["project_id"] = p["id"]
                st.success("Project created and selected.")
                st.rerun()
            except ApiError as exc:
                show_error(exc)

show_archived = st.toggle("Show archived", value=False)
try:
    projects = client().projects(show_archived)
except ApiError as exc:
    show_error(exc)
    st.stop()
if not projects:
    empty_state("No projects", "Use 'Create a project' above to begin.")
    st.stop()
df = pd.DataFrame(projects)[
    ["title", "status", "document_count", "requirement_count", "vendor_count", "latest_run_status", "created_at"]
]
df.columns = ["Project", "Status", "Documents", "Requirements", "Vendors", "Latest run", "Created"]
df["Status"] = df["Status"].str.replace("_", " ")
df["Latest run"] = df["Latest run"].fillna("-").str.replace("_", " ")
st.dataframe(df, hide_index=True, use_container_width=True)

chosen = st.selectbox(
    "Open project",
    projects,
    format_func=lambda p: p["title"],
    index=next((i for i, p in enumerate(projects) if p["id"] == st.session_state.get("project_id")), 0),
)
c1, c2, _ = st.columns([1, 1, 4])
if c1.button("Select", type="primary"):
    st.session_state["project_id"] = chosen["id"]
    st.switch_page("pages/03_documents.py")
if c2.button("Archive"):
    try:
        client().archive_project(chosen["id"])
        st.rerun()
    except ApiError as exc:
        show_error(exc)
