import streamlit as st

from components.ui import empty_state, page_setup, project_selector, show_error
from services.api_client import ApiError
from state.session import client

page_setup(
    "Reports",
    "Evidence-based PDF and Excel exports. Reports distinguish source facts, calculated values, model interpretation and unresolved items.",
)
project = project_selector()
if not project:
    st.stop()
pid, api = project["id"], client()
runs = [r for r in api.runs(pid) if r["status"] in ("completed", "awaiting_human_review")]
if not runs:
    empty_state("No finished analysis", "A report needs a finished analysis run. Start one on the Compliance page.")
    st.stop()
run = st.selectbox(
    "Analysis run", runs, format_func=lambda r: f"{r['id'][:8]} - {r['status']} - {str(r['created_at'])[:16]}"
)
if run["status"] == "awaiting_human_review":
    st.warning("This run has unresolved review items. They will be listed as 'Unresolved' in the report.")
c1, c2, _ = st.columns([1, 1, 4])
for col, kind, label in ((c1, "pdf", "Generate PDF"), (c2, "excel", "Generate Excel")):
    if col.button(label, type="primary", key=kind):
        try:
            with st.spinner("Generating..."):
                api.create_report(pid, kind, run["id"])
            st.success("Report generated.")
        except ApiError as exc:
            show_error(exc)
st.subheader("Generated reports")
reports = api.reports(pid)
if not reports:
    st.caption("None yet.")
for r in reports:
    cols = st.columns([4, 1.5, 1.5])
    cols[0].write(r["filename"])
    cols[1].caption(str(r["generated_at"])[:16])
    mime = (
        "application/pdf"
        if r["report_type"] == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    try:
        cols[2].download_button(
            "Download", api.download_report(r["id"]), file_name=r["filename"], mime=mime, key=f"dl_{r['id']}"
        )
    except ApiError as exc:
        cols[2].error(str(exc))
