import time

import pandas as pd
import streamlit as st

from components.ui import badge, empty_state, page_setup, project_selector, show_error
from services.api_client import ApiError
from state.session import client

page_setup("Compliance", "Run the analysis, inspect requirement-wise results and evidence, and resolve review items.")
project = project_selector()
if not project:
    st.stop()
pid, api = project["id"], client()

with st.container(border=True):
    st.subheader("Analysis")
    auto = st.checkbox(
        "Confirm extracted requirements and quotations automatically (skips manual review of extraction)", value=False
    )
    if st.button("Start analysis", type="primary"):
        try:
            run = api.start_run(pid, auto)
            st.session_state["run_id"] = run["id"]
        except ApiError as exc:
            show_error(exc)

runs = api.runs(pid)
if not runs:
    empty_state("No analysis yet", "Confirm requirements on the Documents page, then start an analysis.")
    st.stop()
run_id = st.session_state.get("run_id") if st.session_state.get("run_id") in [r["id"] for r in runs] else runs[0]["id"]
run = api.run(run_id)
st.markdown(
    f"**Run `{run['id'][:8]}`** {badge(run['status'])} &nbsp; <span class='pa-note'>started {str(run['created_at'])[:16]}"
    f" - workflow v{run['workflow_version']}</span>",
    unsafe_allow_html=True,
)
if run["status"] == "failed":
    st.error(f"The analysis stopped: {run['error']}")
for n in run["summary"].get("notes", []):
    st.warning(n)
with st.expander("Workflow steps", expanded=run["status"] in ("queued", "running", "failed")):
    if not run["steps"]:
        st.caption("Waiting to start...")
    for s in run["steps"]:
        dur = f"{s['duration_ms']} ms" if s["duration_ms"] is not None else "running"
        st.markdown(
            f"{badge(s['status'])} &nbsp; `{s['name']}` attempt {s['attempt']} - {dur}"
            f"{' - ' + s['error'] if s['error'] else ''}",
            unsafe_allow_html=True,
        )
    mi = run["model_info"]
    st.caption(
        f"Language model: {mi.get('llm_provider')} ({mi.get('llm_role')}). Embeddings: {mi.get('embedding_model')}."
    )
if run["status"] in ("queued", "running"):
    time.sleep(2)
    st.rerun()
if run["status"] == "failed":
    st.stop()

tab_res, tab_rev = st.tabs(["Results", "Human review"])
with tab_res:
    rows = api.compliance(pid, run_id)
    if not rows:
        empty_state("No results")
    else:
        df = pd.DataFrame(rows)
        f1, f2, f3 = st.columns(3)
        vend = f1.multiselect("Vendor", sorted(df["vendor_name"].unique()))
        stat = f2.multiselect("Status", sorted(df["effective_status"].unique()))
        crit = f3.multiselect("Criticality", sorted(df["criticality"].unique()))
        if vend:
            df = df[df["vendor_name"].isin(vend)]
        if stat:
            df = df[df["effective_status"].isin(stat)]
        if crit:
            df = df[df["criticality"].isin(crit)]
        matrix = df.pivot_table(
            index="requirement_label", columns="vendor_name", values="effective_status", aggfunc="first"
        )
        st.dataframe(matrix.fillna("-"), use_container_width=True)
        st.caption(
            "Statuses are shown as text. 'Requires Human Review' and 'Missing Information' are never silently treated as pass or fail."
        )
        st.subheader("Evidence")
        for r in df.to_dict("records"):
            off = (r["evidence"] or {}).get("offered") or {}
            with st.expander(f"{r['requirement_label']} / {r['vendor_name']} - {r['effective_status']}"):
                st.markdown(
                    badge(r["effective_status"])
                    + f" &nbsp; requirement: `{r['requirement_text']}` ({r['criticality']}, {r['category']})",
                    unsafe_allow_html=True,
                )
                st.write(r["explanation"])
                if off:
                    st.markdown(
                        f"<div class='pa-src'>Source fact - page {off.get('page')}: {off.get('text')}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No matching value was found in this vendor's quotation.")
                if r["effective_status"] != r["status"]:
                    st.info(f"Manually decided (system result: {r['status']}). Note: {r['reviewer_note']}")
                if r["used_unconfirmed_input"]:
                    st.caption("Based on quotation data that has not been confirmed by a person.")

with tab_rev:
    items = api.review_items(run_id)
    open_items = [i for i in items if i["status"] == "open"]
    st.write(f"{len(open_items)} open / {len(items)} total review items.")
    for it in items:
        with st.expander(
            f"[{it['status']}] {it['kind']}: {it['reason'][:110]}",
            expanded=it["status"] == "open" and len(open_items) <= 3,
        ):
            st.write(it["reason"])
            if it["status"] == "open":
                decisions = ["acknowledged"] + (
                    ["meets", "fails", "not_applicable"] if it["kind"] == "compliance" else []
                )
                d = st.selectbox("Decision", decisions, key=f"d_{it['id']}")
                note = st.text_input("Justification (required)", key=f"n_{it['id']}")
                if st.button("Resolve", key=f"r_{it['id']}"):
                    try:
                        api.resolve_review(it["id"], note, d)
                        st.rerun()
                    except ApiError as exc:
                        show_error(exc)
            else:
                st.caption(f"Resolved: {it['resolution_note']}")
    if run["status"] == "awaiting_human_review" and not open_items:
        if st.button("Approve analysis", type="primary"):
            try:
                api.approve_run(run_id)
                st.rerun()
            except ApiError as exc:
                show_error(exc)
    elif run["summary"].get("approved_by"):
        st.success("This analysis has been approved by a person.")
    st.caption("Approval records that a person reviewed the results. The system never awards contracts.")
