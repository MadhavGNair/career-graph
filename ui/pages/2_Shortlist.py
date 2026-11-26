"""Shortlist: score breakdowns, skills with evidence ids, injection flags, decisions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from careergraph.domain.models import ReasonTag, ShortlistDecision
from common import get_service, page_setup, pending_of, show_outcome, skills_line

page_setup("Shortlist")
svc = get_service()
threads = pending_of(svc, "shortlist")
if not threads:
    st.info("No thread is waiting for a shortlist. Start a run on the Run page.")
    st.stop()
thread = st.selectbox("Thread", threads)
items = svc.get_shortlist(thread)
tags = [t.value for t in ReasonTag]

with st.form("decisions"):
    decisions: list[ShortlistDecision] = []
    for it in items:
        jid = it["job_id"]
        with st.expander(
            f"#{it['rank']} {it['score']:.0f} · {it['title']} · {it['company']}",
            expanded=it["rank"] <= 3,
        ):
            if it["injection_flag"]:
                st.warning(
                    "Possible prompt injection in this posting: "
                    + "; ".join(it["injection_matches"])
                )
            if it["red_flags"]:
                st.warning("Red flags: " + ", ".join(it["red_flags"]))
            where = f"{it['location']} ({it['remote']}) · posted {it['posted_at']}"
            st.write(f"{where} · [posting]({it['url']})")
            st.write(it["rationale"])
            st.caption(it["summary"])
            st.dataframe(
                [
                    {
                        "criterion": c["name"],
                        "weight": c["weight"],
                        "score": c["score"],
                        "points": c["points"],
                        "detail": c["detail"],
                    }
                    for c in it["breakdown"]
                ],
                hide_index=True,
            )
            st.write("Matched: " + skills_line(it["matched"]))
            st.write("Partial: " + skills_line(it["partial"]))
            st.write("Missing: " + skills_line(it["missing"]))
            choice = st.radio(
                "Decision", ["defer", "approve", "reject"], horizontal=True, key=f"d-{jid}"
            )
            chosen = st.multiselect("Reason tags", tags, key=f"t-{jid}")
            note = st.text_input("Note (stored, never interpreted)", key=f"n-{jid}")
            decisions.append(
                ShortlistDecision.model_validate(
                    {"job_id": jid, "decision": choice, "reason_tags": chosen, "note": note}
                )
            )
    if st.form_submit_button("Submit decisions", type="primary"):
        with st.spinner("Drafting and verifying documents for approved jobs..."):
            show_outcome(svc.approve_shortlist(thread, decisions))
