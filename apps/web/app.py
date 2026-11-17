"""ProcureAI Streamlit entry point: global config, theme and the persistent sidebar navigation.

Run with `streamlit run app.py`. The built-in page list is hidden so the sidebar can be rendered explicitly
(signed-out users see nothing but the sign-in view).
"""

import streamlit as st

from components.ui import CSS, NAV
from state.session import logged_in

st.set_page_config(page_title="ProcureAI", page_icon=None, layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

if logged_in():
    pages = [st.Page(path, title=title, default=(i == 0)) for i, (path, title) in enumerate(NAV)]
else:
    pages = [st.Page("login.py", title="Sign in", default=True)]
navigation = st.navigation(pages, position="hidden")

if logged_in():
    with st.sidebar:
        st.markdown("### ProcureAI")
        for path, title in NAV:
            st.page_link(path, label=title)
navigation.run()
