"""Shared UI helpers: one cached service per settings, the password gate, small renderers."""

from __future__ import annotations

import hmac
from typing import Any

import streamlit as st

from careergraph.config import ConfigErrors, Settings, load_app_config, load_settings
from careergraph.service.api import CareerGraphService, RunOutcome


@st.cache_resource(show_spinner=False)
def _service(db_url: str, mode: str) -> CareerGraphService:
    return CareerGraphService(load_app_config(load_settings()))


def get_service() -> CareerGraphService:
    """The process-wide service for the current settings (cached by DB URL and mode)."""
    s = load_settings()
    return _service(s.db_url, s.app_mode)


def page_setup(title: str) -> Settings:
    """Page config, config validation and the password gate. Stops the page when needed."""
    st.set_page_config(page_title=f"CareerGraph · {title}", layout="wide")
    try:
        settings = load_settings()
        load_app_config(settings)
    except ConfigErrors as exc:
        st.error("Configuration problem. Fix it and reload.")
        st.code(exc.render())
        st.stop()
    if settings.app_env == "production" and settings.ui_password is None:
        st.error("APP_ENV=production requires UI_PASSWORD. Set it in .env and restart.")
        st.stop()
    if settings.ui_password is not None and not st.session_state.get("authed"):
        pw = st.text_input("Password", type="password", key="pw")
        if pw and hmac.compare_digest(pw, settings.ui_password.get_secret_value()):
            st.session_state["authed"] = True
            st.rerun()
        st.stop()
    st.title(title)
    if settings.is_demo:
        st.caption(
            "Demo mode: fake LLM, fictional user and companies. Numbers are plumbing checks."
        )
    return settings


def show_outcome(out: RunOutcome) -> None:
    """Explain a run outcome and what to do next."""
    if out.status == "waiting_shortlist":
        st.success(f"Paused for your shortlist: {out.thread_id}")
        st.info("Next: open the Shortlist page in the sidebar.")
    elif out.status == "waiting_review":
        st.success(f"Paused for document review: {out.thread_id}")
        st.info("Next: open the Documents page in the sidebar.")
    elif out.status == "waiting_mock_interview":
        st.info("Next question is ready (Tracker page, Mock interview).")
    elif out.status == "completed":
        st.success(f"Completed {out.thread_id}")
        st.text(out.summary)
    elif out.status == "halted_budget":
        st.warning(f"Halted by budget: {out.error}")
    else:
        st.error(f"Failed: {out.error}. State is checkpointed; resume it from the Run page.")


def pending_of(svc: CareerGraphService, kind: str) -> list[str]:
    """Thread ids waiting for a given pause type."""
    return [p.thread_id for p in svc.list_pending() if p.waiting_for == kind]


def skills_line(rows: list[dict[str, Any]]) -> str:
    """Compact skill list with evidence ids or 'via' info."""
    out = []
    for m in rows:
        extra = f" via {m['via']}" if m.get("via") else ""
        ids = f" [{', '.join(m['evidence_ids'])}]" if m.get("evidence_ids") else ""
        out.append(f"{m['skill']}{extra}{ids}")
    return "; ".join(out) or "none"
