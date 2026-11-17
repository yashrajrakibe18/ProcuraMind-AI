"""Sign-in / registration view. All data access goes through the API client."""

import streamlit as st

from components.ui import safe_page_link, show_error
from services.api_client import ApiError
from state.session import client, logged_in

st.title("ProcureAI")
st.caption("Procurement intelligence and decision support. Analysis assists people; it never awards contracts.")

if logged_in():
    st.success(f"Signed in as {st.session_state['user']['full_name']}.")
    safe_page_link("pages/01_overview.py", "Open the overview")
    st.stop()

left, right = st.columns(2)
with left:
    with st.form("login"):
        st.subheader("Sign in")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            try:
                st.session_state["user"] = client().login(email, password)
                st.rerun()  # the entrypoint rebuilds navigation; Overview is the default page
            except ApiError as exc:
                show_error(exc)
with right:
    with st.form("register"):
        st.subheader("Create an account")
        name = st.text_input("Full name")
        email_r = st.text_input("Email", key="reg_email")
        pw = st.text_input("Password (min. 8 characters)", type="password", key="reg_pw")
        if st.form_submit_button("Register"):
            try:
                client().register(email_r, name, pw)
                st.success("Account created. You can now sign in.")
            except ApiError as exc:
                show_error(exc)
