"""Tracker: applications and validated status changes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from careergraph.domain.status import TRANSITIONS, ApplicationStatus
from common import get_service, page_setup, pending_of, show_outcome

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
            out = svc.change_status(job, new, note)
            if out.status == "waiting_mock_interview":
                st.success("Interview prep ready. Practise below.")
            else:
                show_outcome(out)
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

st.subheader("Mock interview")
threads = pending_of(svc, "mock_interview")
if not threads:
    st.caption('Set an application to "interview" for prep questions, STAR stories and practice.')
else:
    thread = st.selectbox("Interview thread", threads)
    payload = svc.pending_payload(thread) or {}
    q = payload.get("question", {})
    st.write(
        f"**Question {payload.get('turn')}/{payload.get('of')}** ({q.get('kind')}): {q.get('text')}"
    )
    if payload.get("story_hints"):
        st.caption("Your STAR stories: " + "; ".join(payload["story_hints"]))
    with st.form("answer"):
        answer = st.text_area("Your answer (/stop to finish)")
        if st.form_submit_button("Submit answer") and answer:
            show_outcome(svc.answer_mock(thread, answer))
