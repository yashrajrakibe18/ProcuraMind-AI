"""Streamlit session helpers: presentation state only (token, selected project, filters)."""

from __future__ import annotations

import streamlit as st

from services.api_client import ApiClient

_factory = ApiClient  # tests replace this to route requests to an in-process API


def client() -> ApiClient:
    if "api" not in st.session_state:
        st.session_state["api"] = _factory()
    return st.session_state["api"]


def logged_in() -> bool:
    return bool(st.session_state.get("user")) and bool(client().token)


def logout() -> None:
    for key in ("api", "user", "project_id"):
        st.session_state.pop(key, None)
