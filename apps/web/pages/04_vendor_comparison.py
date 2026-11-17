import pandas as pd
import streamlit as st

from components.ui import empty_state, page_setup, project_selector
from state.session import client

page_setup("Vendor Comparison", "Side-by-side commercial terms and offered specifications, with source pages.")
project = project_selector()
if not project:
    st.stop()
vendors = client().vendors(project["id"])
if not vendors:
    empty_state("No vendor data", "Upload quotations and extract them on the Documents page.")
    st.stop()

rows = []
for v in vendors:
    q = max(v["quotations"], key=lambda x: x["id"], default=None)
    if q:
        rows.append(
            {
                "Vendor": v["vendor_name"],
                "Currency": q["currency"],
                "Unit price": q["unit_price"],
                "Quantity": q["quantity"],
                "Tax %": q["tax_percent"],
                "Delivery charge": q["delivery_cost"],
                "Warranty (months)": q["warranty_months"],
                "Delivery (days)": q["delivery_days"],
                "Confirmed": "yes" if q["confirmed"] else "no",
            }
        )
st.subheader("Commercial terms (as quoted)")
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
st.caption(
    "Values are shown in each vendor's own currency. Normalised, comparable totals are on the Price Intelligence page."
)

st.subheader("Offered specifications")
matrix: dict[str, dict[str, str]] = {}
for v in vendors:
    for q in v["quotations"]:
        for s in q["specifications"]:
            matrix.setdefault(s["label"], {})[v["vendor_name"]] = f"{s['value_text']} (p.{s['source_page']})"
st.dataframe(pd.DataFrame(matrix).T.fillna("not found"), use_container_width=True)
st.caption(
    "'not found' means the value could not be located in the quotation; it is not assumed to be zero or non-compliant."
)
