"""Documents: drafts with verification labels; approve / edit / regenerate / reject; downloads."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from careergraph.domain.models import ReviewAction
from common import get_service, page_setup, pending_of, show_outcome

page_setup("Documents")
svc = get_service()
threads = pending_of(svc, "review")
if threads:
    thread = st.selectbox("Thread waiting for review", threads)
    payload = svc.get_review(thread)
    for err in payload.get("errors", []):
        st.error(err)
    with st.form("review"):
        actions: list[ReviewAction] = []
        for d in payload["drafts"]:
            jid = d["job_id"]
            with st.expander(f"{d['title']} · {d['company']} · {d['status']}", expanded=True):
                if d["flagged"]:
                    st.error(
                        f"Flagged: {d['unsupported']} unsupported claim(s) "
                        f"after {d['revision_count']} revision(s)."
                    )
                for e in d["fact_errors"]:
                    st.warning(e)
                if d["critique_log"]:
                    st.caption("Caught by the verifier and revised:")
                    for c in d["critique_log"]:
                        st.code(c)
                patch: dict[str, str] = {}
                for c in d["claims"]:
                    label = {
                        "supported": "OK",
                        "partial": "PARTIAL",
                        "unsupported": "UNSUPPORTED",
                    }.get(c["label"], "?")
                    new = st.text_area(
                        f"[{label}] {c['claim_id']} · evidence {', '.join(c['evidence_ids'])}",
                        c["text"],
                        key=f"{jid}-{c['claim_id']}",
                    )
                    if c["quote"]:
                        st.caption(f"Evidence: {c['quote']}")
                    if new is not None and new != c["text"]:
                        patch[c["claim_id"]] = new
                if d["research"]:
                    st.caption(
                        f"Research ({d['research']['confidence']}): {d['research']['summary']}"
                    )
                action = st.radio(
                    "Action",
                    ["approve", "edit", "regenerate", "reject"],
                    horizontal=True,
                    key=f"a-{jid}",
                )
                override = st.checkbox(
                    "Override: approve despite unsupported claims",
                    key=f"o-{jid}",
                    disabled=not d["flagged"],
                )
                reason = st.text_input("Reason (regenerate/reject)", key=f"r-{jid}")
                if action == "edit" and not patch:
                    action = "approve"
                actions.append(
                    ReviewAction.model_validate(
                        {
                            "job_id": jid,
                            "action": action,
                            "patch": patch if action == "edit" else {},
                            "reason": reason,
                            "override": override,
                        }
                    )
                )
        if st.form_submit_button("Submit review", type="primary"):
            with st.spinner("Applying decisions..."):
                show_outcome(svc.review_documents(thread, actions))
else:
    st.info("No thread is waiting for document review.")

st.subheader("Rendered applications")
for a in svc.list_applications():
    with st.expander(f"{a.company}: {a.role} ({a.status})"):
        out = Path(a.out_dir)
        for name, mime in [
            ("cv.tex", "text/x-tex"),
            ("letter.tex", "text/x-tex"),
            ("cv.pdf", "application/pdf"),
            ("letter.pdf", "application/pdf"),
            ("report.md", "text/markdown"),
        ]:
            f = out / name
            if f.exists():
                st.download_button(
                    f"Download {name}",
                    f.read_bytes(),
                    file_name=name,
                    mime=mime,
                    key=f"{a.job_id}-{name}",
                )
        if not (out / "cv.pdf").exists():
            st.caption("No PDF: no LaTeX engine was found (set LATEX_ENGINE or install tectonic).")
