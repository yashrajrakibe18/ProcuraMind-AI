import time

import pandas as pd
import streamlit as st

from components.ui import badge, empty_state, page_setup, project_selector, show_error
from services.api_client import ApiError
from state.session import client

page_setup("Documents", "Upload, review extraction and confirm the data the analysis will use.")
project = project_selector()
if not project:
    st.stop()
pid, api = project["id"], client()
tab_files, tab_req, tab_vendor = st.tabs(["Files", "Tender requirements", "Vendor data"])

with tab_files:
    with st.form("upload", clear_on_submit=True):
        files = st.file_uploader(
            "Tender, quotations, policies, historical purchases (PDF, TXT, CSV, PNG, JPG)", accept_multiple_files=True
        )
        dtype = st.selectbox(
            "Document type",
            ["auto", "tender", "quotation", "policy", "historical", "other"],
            help="'auto' classifies by content; check the result afterwards.",
        )
        if st.form_submit_button("Upload", type="primary") and files:
            for f in files:
                try:
                    api.upload(pid, f.name, f.getvalue(), dtype)
                    st.success(f"Uploaded {f.name}")
                except ApiError as exc:
                    st.error(f"{f.name}: {exc}")
    try:
        docs = api.documents(pid)
    except ApiError as exc:
        show_error(exc)
        st.stop()
    if not docs:
        empty_state("No documents yet", "Upload the tender first, then the vendor quotations.")
    else:
        for d in docs:
            c = st.columns([4, 1.4, 1.4, 1, 1])
            c[0].markdown(
                f"**{d['original_filename']}**  \n<span class='pa-note'>{d['size_bytes'] / 1024:.0f} KB</span>",
                unsafe_allow_html=True,
            )
            c[1].markdown(badge(d["processing_status"]), unsafe_allow_html=True)
            c[2].write(f"{d['document_type']} ({d['classification_confidence']:.0%})")
            c[3].write(f"{d['page_count']} p.")
            if c[4].button("Delete", key=f"del_{d['id']}"):
                api.delete_document(d["id"])
                st.rerun()
            if d["processing_error"]:
                st.warning(f"{d['original_filename']}: {d['processing_error']}")
        if any(d["processing_status"] == "pending" for d in docs):
            st.info("Some documents are still processing...")
            time.sleep(2)
            st.rerun()
        st.divider()
        st.subheader("Preview extracted text")
        done = [d for d in docs if d["processing_status"] == "processed"]
        if done:
            doc = st.selectbox("Document", done, format_func=lambda d: d["original_filename"])
            for pg in api.pages(doc["id"]):
                with st.expander(f"Page {pg['page_number']}" + (" (OCR)" if pg["ocr_used"] else "")):
                    st.text(pg["text"])

with tab_req:
    st.caption(
        "Review what was read from the tender. Edit anything wrong, then confirm: only confirmed requirements are used."
    )
    c1, c2 = st.columns([1, 1])
    if c1.button("Extract requirements from tender", type="primary"):
        try:
            rep = api.extract_requirements(pid)
            st.success(f"{rep['created']} new requirement(s) extracted; {rep['kept_confirmed']} confirmed kept.")
            for w in rep["warnings"]:
                st.warning(w)
        except ApiError as exc:
            show_error(exc)
    reqs = api.requirements(pid)
    if not reqs:
        empty_state("No requirements", "Extract them from the tender, or add them manually below.")
    else:
        if c2.button("Confirm all"):
            api.confirm_requirements(pid)
            st.rerun()
        df = pd.DataFrame(reqs)
        df["rule"] = (
            df["operator"]
            + " "
            + df["required_value"]
            + df["required_value_max"].fillna("").map(lambda v: f"-{v}" if v else "")
            + " "
            + df["unit"].fillna("")
        )
        view = df[["label", "rule", "criticality", "source_page", "confirmed", "source_text"]]
        view.columns = ["Requirement", "Rule", "Criticality", "Source page", "Confirmed", "Source text"]
        st.dataframe(view, hide_index=True, use_container_width=True)
        with st.expander("Edit a requirement"):
            sel = st.selectbox(
                "Requirement", reqs, format_func=lambda r: f"{r['label']} ({r['operator']} {r['required_value']})"
            )
            ops = [">=", "<=", ">", "<", "==", "between", "contains"]
            e1, e2, e3, e4 = st.columns(4)
            op = e1.selectbox("Operator", ops, index=ops.index(sel["operator"]))
            val = e2.text_input("Value", sel["required_value"])
            unit = e3.text_input("Unit", sel["unit"] or "")
            crit = e4.selectbox(
                "Criticality", ["mandatory", "desirable"], index=["mandatory", "desirable"].index(sel["criticality"])
            )
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("Save and confirm"):
                try:
                    api.update_requirement(
                        sel["id"], operator=op, required_value=val, unit=unit or None, criticality=crit, confirmed=True
                    )
                    st.rerun()
                except ApiError as exc:
                    show_error(exc)
            if b2.button("Delete requirement"):
                api.delete_requirement(sel["id"])
                st.rerun()
    with st.expander("Add a requirement manually"):
        with st.form("add_req", clear_on_submit=True):
            a1, a2, a3, a4, a5 = st.columns(5)
            label = a1.text_input("Name")
            op = a2.selectbox("Operator", [">=", "<=", ">", "<", "==", "contains"])
            val = a3.text_input("Value")
            unit = a4.text_input("Unit")
            crit = a5.selectbox("Criticality", ["mandatory", "desirable"])
            if st.form_submit_button("Add") and label and val:
                try:
                    api.add_requirement(
                        pid, label=label, operator=op, required_value=val, unit=unit or None, criticality=crit
                    )
                    st.rerun()
                except ApiError as exc:
                    show_error(exc)

with tab_vendor:
    st.caption("Vendor values are extracted automatically. Correct any value and confirm each quotation.")
    if st.button("Extract vendors from quotations", type="primary"):
        try:
            rep = api.extract_vendors(pid)
            st.success(f"{rep['created']} vendor(s) extracted; {len(rep['skipped'])} already present.")
            for w in rep["warnings"]:
                st.warning(w)
        except ApiError as exc:
            show_error(exc)
    vendors = api.vendors(pid)
    if not vendors:
        empty_state("No vendors", "Upload quotations, then extract.")
    for v in vendors:
        for q in v["quotations"]:
            with st.expander(f"{v['vendor_name']} - {'confirmed' if q['confirmed'] else 'not confirmed'}"):
                for n in q["extraction_notes"]:
                    st.warning(n)
                m = st.columns(5)
                m[0].write(f"Unit price: {q['unit_price']} {q['currency'] or ''}")
                m[1].write(f"Quantity: {q['quantity']}")
                m[2].write(f"Tax: {q['tax_percent']}%")
                m[3].write(f"Delivery: {q['delivery_cost']}")
                m[4].write(f"Page: {q['source_page']}")
                sp = pd.DataFrame(q["specifications"])[
                    ["label", "value_text", "source_page", "confidence", "source_text"]
                ]
                sp.columns = ["Field", "Value", "Page", "Confidence", "Source text"]
                st.dataframe(sp, hide_index=True, use_container_width=True)
                s1, s2, s3 = st.columns([2, 2, 1])
                spec = s1.selectbox(
                    "Correct a value", q["specifications"], key=f"sp_{q['id']}", format_func=lambda s: s["label"]
                )
                new = s2.text_input("New value", spec["value_text"], key=f"nv_{q['id']}")
                if s3.button("Save", key=f"sv_{q['id']}"):
                    api.update_spec(spec["id"], new)
                    st.rerun()
                if not q["confirmed"] and st.button("Confirm this quotation", key=f"cf_{q['id']}"):
                    api.update_quotation(q["id"], confirmed=True)
                    st.rerun()
