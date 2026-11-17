import pandas as pd
import plotly.express as px
import streamlit as st

from components.ui import badge, empty_state, kpi, page_setup, safe_page_link, show_error
from services.api_client import ApiError
from state.session import client

page_setup("Overview", "Live figures from your procurement workspace.")
try:
    with st.spinner("Loading overview..."):
        data = client().overview()
except ApiError as exc:
    show_error(exc)
    st.stop()

k = data["kpis"]
cols = st.columns(6)
for col, (label, key) in zip(
    cols,
    [
        ("Projects", "projects"),
        ("Documents", "documents"),
        ("Vendors", "vendors"),
        ("Analysis runs", "analysis_runs"),
        ("Open reviews", "pending_reviews"),
        ("Runs awaiting review", "runs_awaiting_review"),
    ],
    strict=True,
):
    kpi(label, k[key], col)

if k["projects"] == 0:
    st.write("")
    empty_state("No projects yet", "Create a project to upload a tender and vendor quotations.")
    safe_page_link("pages/02_projects.py", "Create your first project")
    st.stop()

left, right = st.columns([3, 2])
with left:
    st.subheader("Recent projects")
    df = pd.DataFrame(data["recent_projects"])[
        ["title", "status", "document_count", "vendor_count", "latest_run_status", "updated_at"]
    ]
    df.columns = ["Project", "Status", "Documents", "Vendors", "Latest run", "Updated"]
    df["Status"] = df["Status"].str.replace("_", " ")
    df["Latest run"] = df["Latest run"].fillna("-").str.replace("_", " ")
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.subheader("Recent analysis runs")
    if data["recent_runs"]:
        for r in data["recent_runs"]:
            st.markdown(
                f"{badge(r['status'])} &nbsp; `{r['id'][:8]}` &nbsp; <span class='pa-note'>{r['created_at'][:16]}"
                f"{' - ' + r['error'][:90] if r['error'] else ''}</span>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No analysis has been run yet.")
with right:
    st.subheader("Runs by status")
    if data["runs_by_status"]:
        d = pd.DataFrame(
            {
                "Status": [s.replace("_", " ") for s in data["runs_by_status"]],
                "Runs": list(data["runs_by_status"].values()),
            }
        )
        fig = px.bar(d, x="Status", y="Runs", text="Runs")
        fig.update_layout(
            height=260, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Run status", yaxis_title="Number of runs"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Source: analysis runs in this workspace.")
    else:
        st.caption("No runs yet.")
    st.subheader("Recent activity")
    for e in data["recent_activity"]:
        st.markdown(f"<span class='pa-note'>{e['timestamp'][:16]}</span> {e['action']}", unsafe_allow_html=True)
