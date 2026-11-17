import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ui import badge, empty_state, page_setup, project_selector
from state.session import client

page_setup("Price Intelligence", "Normalised cost comparison with transparent statistical baselines.")
project = project_selector()
if not project:
    st.stop()
pid, api = project["id"], client()
rows = api.price_analysis(pid)
if not rows:
    empty_state("No price analysis yet", "Run an analysis on the Compliance page.")
    st.stop()
df = pd.DataFrame(rows)
base = df["base_currency"].iloc[0]
st.info(
    "Totals add tax and delivery to the quoted unit price (assuming prices exclude tax) and convert to the base "
    f"currency ({base}) using the configured static FX table. A flag means 'deviates from the baseline - please review'; "
    "it is not a finding of overpricing or misconduct."
)

peer = df[df["baseline_source"] == "peer"].copy()
tbl = peer[
    [
        "vendor_name",
        "currency",
        "subtotal",
        "tax_amount",
        "delivery_cost",
        "normalized_total",
        "normalized_unit_price",
        "baseline",
        "deviation_pct",
        "anomaly_flag",
    ]
].copy()
tbl["anomaly_flag"] = tbl["anomaly_flag"].map({True: "Review", False: "No flag"})
tbl.columns = [
    "Vendor",
    "Quoted currency",
    "Subtotal (quoted)",
    "Tax (quoted)",
    "Delivery (quoted)",
    f"Total ({base})",
    f"All-in unit price ({base})",
    f"Peer baseline ({base})",
    "Deviation %",
    "Flag",
]
st.dataframe(tbl, hide_index=True, use_container_width=True)

st.subheader(f"All-in unit price per vendor ({base})")
chart = peer.dropna(subset=["normalized_unit_price"])
if not chart.empty:
    fig = go.Figure(
        go.Bar(
            x=chart["vendor_name"],
            y=chart["normalized_unit_price"],
            text=chart["normalized_unit_price"].round(0),
            name="Vendor",
        )
    )
    hist = df[df["baseline_source"] == "historical"]["baseline"].dropna()
    if not hist.empty:
        fig.add_hline(y=float(hist.iloc[0]), line_dash="dash", annotation_text=f"Historical median {hist.iloc[0]:,.0f}")
    fig.update_layout(
        height=340,
        xaxis_title="Vendor",
        yaxis_title=f"Unit price incl. tax and delivery ({base})",
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Source: vendor quotations in this project; dashed line = median of matching historical purchases.")

st.subheader("How each figure was derived")
for r in df.to_dict("records"):
    with st.expander(f"{r['vendor_name']} - {r['baseline_source']} baseline"):
        st.markdown(
            badge("Requires Human Review") if r["anomaly_flag"] else badge("Not Applicable"), unsafe_allow_html=True
        )
        st.write(r["explanation"])

hist_rows = api.historical(pid)
if hist_rows:
    st.subheader("Historical purchases")
    h = pd.DataFrame(hist_rows)[["item_category", "unit_price", "currency", "purchased_on", "supplier"]]
    h.columns = ["Item", "Unit price", "Currency", "Date", "Supplier"]
    st.dataframe(h, hide_index=True, use_container_width=True)
else:
    st.caption("No historical purchase file was uploaded, so only peer-quotation baselines are shown.")
