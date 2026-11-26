"""Headless end-to-end smoke test of the whole demo flow (Definition of Done).

run -> shortlist pause -> resume with approvals -> research -> draft/verify loop revises the
forced fabrication -> review pause -> edit (re-verified, flagged) -> approve without override is
refused -> approve with override -> simulated crash in render -> resume from checkpoint ->
LaTeX rendered -> tracker -> time-travel fork from before the shortlist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from careergraph.domain.models import ReasonTag, ReviewAction, ShortlistDecision
from careergraph.graphs.job_search.nodes import render_latex as render_mod
from careergraph.latex.compile import detect_engine
from tests.helpers import demo_service

pytestmark = pytest.mark.slow


def test_full_demo_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = demo_service(tmp_path, enable_company_research=True)
    events: list[str] = []
    out = svc.start_run(lambda node, _u: events.append(node))
    assert out.status == "waiting_shortlist" and out.payload
    assert (
        events[:3] == ["ingest_profile", "extract_profile", "find_jobs"] and "match_jobs" in events
    )
    tid, items = out.thread_id, out.payload["items"]
    ids = [i["job_id"] for i in items]
    fab = svc.cfg.settings.demo_fabricate_job
    assert fab in ids
    other = next(i for i in ids if i != fab)
    before_shortlist = next(h for h in svc.history(tid) if h.next == ("human_shortlist",))

    # ---- pause 1: approve two jobs, reject one with a tag
    reject = next(i for i in ids if i not in (fab, other))
    out = svc.approve_shortlist(tid, [
        ShortlistDecision(job_id=fab, decision="approve"),
        ShortlistDecision(job_id=other, decision="approve"),
        ShortlistDecision(job_id=reject, decision="reject", reason_tags=[ReasonTag.NOT_MY_DOMAIN]),
    ])  # fmt: skip
    assert out.status == "waiting_review" and out.payload
    drafts = {d["job_id"]: d for d in out.payload["drafts"]}
    assert set(drafts) == {fab, other}
    assert drafts[fab]["revision_count"] >= 1 and "Google" in drafts[fab]["critique_log"][0]
    assert not drafts[fab]["flagged"] and drafts[fab]["research"]["facts"]

    # ---- pause 2: edit introduces an unsupported claim; edits are re-verified, not redrafted
    out = svc.review_documents(tid, [
        ReviewAction(job_id=fab, action="approve"),
        ReviewAction(job_id=other, action="edit", patch={"cv.summary.0": "Won a Nobel prize in 2019."}),
    ])  # fmt: skip
    assert out.status == "waiting_review" and out.payload
    [row] = out.payload["drafts"]
    assert row["job_id"] == other and row["flagged"]
    assert (
        next(c for c in row["claims"] if c["claim_id"] == "cv.summary.0")["label"] == "unsupported"
    )

    out = svc.review_documents(tid, [ReviewAction(job_id=other, action="approve")])
    assert out.status == "waiting_review" and out.payload and "override" in out.payload["errors"][0]

    # ---- simulated crash while rendering, then resume from the checkpoint
    real = render_mod.write_and_compile
    calls = {"n": 0}

    def crash_once(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full (simulated)")
        return real(*a, **k)

    monkeypatch.setattr(render_mod, "write_and_compile", crash_once)
    out = svc.review_documents(tid, [ReviewAction(job_id=other, action="approve", override=True)])
    assert out.status == "failed" and "simulated" in out.error
    assert [p.thread_id for p in svc.list_pending()] == [tid]
    out = svc.resume(tid)
    assert out.status == "completed", out.error
    assert "READY" in out.summary and "plumbing check" in out.summary

    # ---- outputs + tracker
    apps = {a.job_id: a for a in svc.list_applications()}
    assert set(apps) == {fab, other} and all(a.status == "ready" for a in apps.values())
    for a in apps.values():
        d = Path(a.out_dir)
        assert (
            (d / "cv.tex").exists() and (d / "letter.tex").exists() and (d / "report.md").exists()
        )
        assert (d / "cv.pdf").exists() == (detect_engine(svc.cfg.settings.latex_engine) is not None)
    assert "approved with override" in (Path(apps[other].out_dir) / "report.md").read_text()
    assert svc.set_status(fab, "applied").status == "applied"
    assert svc.skills_trend() and svc.usage_by_run()[0]["fake"] is True

    # ---- time travel: fork from before the shortlist with an edited shortlist
    forked = svc.fork(
        tid, before_shortlist.checkpoint_id, {"shortlist": [ids[-1]]}, as_node="match_jobs"
    )
    assert forked.status == "waiting_shortlist" and forked.payload
    assert [i["job_id"] for i in forked.payload["items"]] == [ids[-1]]
    svc.close()


def test_review_can_be_disabled(tmp_path: Path) -> None:
    with demo_service(tmp_path, require_document_review=False) as svc:
        out = svc.start_run()
        first = out.payload["items"][0]["job_id"]  # type: ignore[index]
        done = svc.approve_shortlist(
            out.thread_id, [ShortlistDecision(job_id=first, decision="approve")]
        )
        assert done.status == "completed" and "READY" in done.summary
