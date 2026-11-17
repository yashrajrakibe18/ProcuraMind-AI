"""Reusable presentation components and the shared design system (CSS tokens, badges, states)."""

from __future__ import annotations

import html

import streamlit as st

from services.api_client import ApiError
from state.session import client, logged_in, logout

NAV = [
    ("pages/01_overview.py", "Overview"),
    ("pages/02_projects.py", "Projects"),
    ("pages/03_documents.py", "Documents"),
    ("pages/04_vendor_comparison.py", "Vendor Comparison"),
    ("pages/05_compliance.py", "Compliance"),
    ("pages/06_price_intelligence.py", "Price Intelligence"),
    ("pages/07_ai_assistant.py", "AI Assistant"),
    ("pages/08_reports.py", "Reports"),
    ("pages/09_settings.py", "Settings"),
]

CSS = """
<style>
:root{--navy:#0F2A47;--blue:#1F5FBF;--ink:#14213D;--muted:#5B6B7F;--line:#D9E0E8;--card:#FFFFFF;
--ok:#1B7F4B;--warn:#9A6200;--bad:#B3261E;--info:#1F5FBF;}
[data-testid="stSidebar"]{background:var(--navy);} [data-testid="stSidebar"] *{color:#E8EEF5 !important;}
[data-testid="stSidebar"] button,[data-testid="stSidebar"] button *{color:#0F2A47 !important;}
[data-testid="stSidebar"] a[aria-current="page"]{background:rgba(255,255,255,.14);border-radius:6px;}
h1,h2,h3{color:var(--navy);letter-spacing:-.01em;} h1{font-size:1.7rem !important;}
.pa-kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;}
.pa-kpi .v{font-size:1.6rem;font-weight:650;color:var(--navy);line-height:1.1}
.pa-kpi .l{font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.pa-badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.78rem;font-weight:600;border:1px solid}
.pa-ok{color:var(--ok);border-color:var(--ok);background:#EAF6EF}.pa-warn{color:var(--warn);border-color:var(--warn);background:#FFF5E0}
.pa-bad{color:var(--bad);border-color:var(--bad);background:#FDECEA}.pa-info{color:var(--info);border-color:var(--info);background:#E9F0FB}
.pa-neutral{color:var(--muted);border-color:var(--line);background:#F1F4F8}
.pa-note{font-size:.82rem;color:var(--muted)}
.pa-src{font-size:.8rem;background:#F1F4F8;border-left:3px solid var(--blue);padding:6px 10px;border-radius:0 4px 4px 0}
</style>
"""

STATUS_CLASS = {
    "Meets Requirement": "pa-ok",
    "Does Not Meet Requirement": "pa-bad",
    "Missing Information": "pa-warn",
    "Requires Human Review": "pa-warn",
    "Not Applicable": "pa-neutral",
    "completed": "pa-ok",
    "processed": "pa-ok",
    "awaiting_human_review": "pa-warn",
    "running": "pa-info",
    "queued": "pa-info",
    "pending": "pa-info",
    "failed": "pa-bad",
    "succeeded": "pa-ok",
    "open": "pa-warn",
    "resolved": "pa-ok",
}
STATUS_TEXT = {"awaiting_human_review": "Awaiting human review", "pending": "Processing", "queued": "Queued"}


def safe_page_link(path: str, label: str) -> None:
    """Navigation link that degrades to plain text if the page registry is unavailable."""
    try:
        st.page_link(path, label=label)
    except Exception:  # StreamlitPageNotFoundError when a page is run directly
        st.caption(f"Open '{label}' from the sidebar.")


def badge(status: str) -> str:
    label = STATUS_TEXT.get(status, status.replace("_", " ").capitalize() if status.islower() else status)
    return f'<span class="pa-badge {STATUS_CLASS.get(status, "pa-neutral")}">{html.escape(label)}</span>'


def kpi(label: str, value: object, col=None) -> None:
    (col or st).markdown(
        f'<div class="pa-kpi"><div class="l">{html.escape(label)}</div>'
        f'<div class="v">{html.escape(str(value))}</div></div>',
        unsafe_allow_html=True,
    )


def page_setup(title: str, subtitle: str = "", *, require_auth: bool = True) -> None:
    if require_auth and not logged_in():
        st.title(title)
        st.info("Please sign in to continue.")
        st.caption("Use the Sign in page in the sidebar.")
        st.stop()
    if logged_in():
        with st.sidebar:
            u = st.session_state["user"]
            st.markdown(
                f"**{html.escape(u['full_name'])}**  \n<span class='pa-note'>{html.escape(u['role'])}</span>",
                unsafe_allow_html=True,
            )
            if st.button("Sign out", key="signout"):
                logout()
                st.rerun()
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def show_error(exc: Exception) -> None:
    if isinstance(exc, ApiError):
        st.error(f"{exc}")
    else:
        st.error("Something went wrong. Please try again.")


def project_selector() -> dict | None:
    """Sidebar-independent project picker; the choice persists in session state."""
    try:
        projects = client().projects()
    except ApiError as exc:
        show_error(exc)
        return None
    if not projects:
        st.info("You have no projects yet. Create one on the Projects page.")
        safe_page_link("pages/02_projects.py", "Go to Projects")
        return None
    ids = [p["id"] for p in projects]
    current = st.session_state.get("project_id")
    idx = ids.index(current) if current in ids else 0
    chosen = st.selectbox("Project", projects, index=idx, format_func=lambda p: p["title"], key="project_pick")
    st.session_state["project_id"] = chosen["id"]
    return chosen


def empty_state(message: str, hint: str = "") -> None:
    st.markdown(
        f"<div class='pa-kpi' style='text-align:center'><b>{html.escape(message)}</b><br>"
        f"<span class='pa-note'>{html.escape(hint)}</span></div>",
        unsafe_allow_html=True,
    )
