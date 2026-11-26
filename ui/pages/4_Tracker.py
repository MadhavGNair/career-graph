"""Tracker: applications and validated status changes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from careergraph.domain.status import TRANSITIONS, ApplicationStatus, InvalidTransition
from common import get_service, page_setup

page_setup("Tracker")
svc = get_service()
apps = svc.list_applications()
if not apps:
    st.info("No applications yet. Approve documents in the review pause to create them.")
    st.stop()
st.dataframe(
    [
        {
            "job": a.job_id,
            "company": a.company,
            "role": a.role,
            "status": a.status,
            "updated": a.updated_at,
            "folder": a.out_dir,
        }
        for a in apps
    ],
    hide_index=True,
)
job = st.selectbox("Application", [a.job_id for a in apps])
current = ApplicationStatus(next(a.status for a in apps if a.job_id == job))
allowed = sorted(TRANSITIONS[current])
if allowed:
    with st.form("status"):
        new = st.selectbox("New status", allowed)
        note = st.text_input("Note")
        if st.form_submit_button("Update"):
            try:
                svc.set_status(job, new, note)
                st.success(f"{job}: {current} -> {new}")
            except InvalidTransition as exc:
                st.error(str(exc))
else:
    st.caption(f"{current} is final.")
st.caption("History")
st.dataframe(
    [
        {"at": e.at, "from": e.from_status, "to": e.to_status, "note": e.note}
        for e in svc.repo.application_events(job)
    ],
    hide_index=True,
)
