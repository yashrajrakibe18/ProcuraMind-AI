import streamlit as st

from components.ui import page_setup, show_error
from services.api_client import ApiError
from state.session import client

page_setup("Settings", "Account and service status.")
u = st.session_state["user"]
st.subheader("Account")
st.write(f"**{u['full_name']}** - {u['email']} - role: {u['role']}")
st.subheader("Service status")
try:
    r = client().ready()
    st.write(f"Overall: **{r['status']}**")
    for name, ok in r["checks"].items():
        st.write(f"- {name.replace('_', ' ')}: {'available' if ok else 'unavailable'}")
    llm = r["llm"]
    st.write(
        f"- language model: {llm['provider']} ({'configured' if llm['configured'] else 'not configured - deterministic mode'})"
    )
except ApiError as exc:
    if exc.status == 503 and exc.details is not None:
        st.warning("The service reports it is degraded.")
    show_error(exc)
st.caption(f"API endpoint: {client().base_url}")
st.caption(
    "Model and provider settings are configured on the server through environment variables; secrets are never shown here."
)
