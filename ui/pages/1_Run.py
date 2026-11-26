"""Run: start a run with live node updates, see pending threads, resume, time travel."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from common import get_service, page_setup, show_outcome

page_setup("Run")
svc = get_service()

if st.button("Start a run", type="primary"):
    with st.status("Running the job_search graph...", expanded=True) as status:

        def on_event(node: str, update: dict[str, Any]) -> None:
            st.write(f"done: `{node}`")

        out = svc.start_run(on_event)
        status.update(
            label=f"Run {out.status}", state="error" if out.status == "failed" else "complete"
        )
    show_outcome(out)

st.subheader("Threads waiting for you")
pending = svc.list_pending()
if not pending:
    st.info("Nothing pending.")
for p in pending:
    cols = st.columns([4, 3, 2])
    cols[0].write(f"`{p.thread_id}`")
    cols[1].write(f"{p.waiting_for} ({p.items} items)")
    if p.waiting_for.startswith("resume") and cols[2].button("Resume", key=f"resume-{p.thread_id}"):
        show_outcome(svc.resume(p.thread_id))

st.subheader("Time travel")
threads = [r.thread_id for r in svc.repo.list_runs() if r.kind == "job_search"]
thread = st.selectbox("Thread", threads, key="tt-thread") if threads else None
if thread:
    history = svc.history(thread)
    st.dataframe(
        [
            {
                "checkpoint": h.checkpoint_id,
                "step": h.step,
                "wrote": ", ".join(h.writes),
                "next": ", ".join(h.next),
            }
            for h in history
        ],
        hide_index=True,
    )
    with st.form("fork"):
        cp = st.selectbox("Fork from checkpoint", [h.checkpoint_id for h in history])
        update = st.text_area("State update (JSON, optional)", '{"shortlist": []}')
        as_node = st.text_input("Apply update as node", "match_jobs")
        if st.form_submit_button("Fork and replay"):
            show_outcome(
                svc.fork(
                    thread, cp, json.loads(update) if update.strip() else None, as_node or None
                )
            )
