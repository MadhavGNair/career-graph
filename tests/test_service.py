"""Service layer: durable pause/resume, pending list, decisions, budget halt, crash resume."""

from __future__ import annotations

from pathlib import Path

import pytest

from careergraph.domain.models import ReasonTag, ShortlistDecision
from careergraph.graphs.job_search.nodes import match_jobs as match_mod
from tests.helpers import demo_service


def test_run_pauses_at_shortlist_and_resumes_in_new_process(tmp_path: Path) -> None:
    svc = demo_service(tmp_path)
    out = svc.start_run()
    assert out.status == "waiting_shortlist" and out.payload is not None
    items = out.payload["items"]
    assert 1 <= len(items) <= 8 and items[0]["rank"] == 1
    assert "too_junior" in out.payload["reason_tags"]
    tid = out.thread_id
    svc.close()

    svc2 = demo_service(tmp_path)  # "hours later": new process, same durable state
    pending = svc2.list_pending()
    assert [p.thread_id for p in pending] == [tid] and pending[0].waiting_for == "shortlist"
    first, second = items[0]["job_id"], items[1]["job_id"]
    decisions = [
        ShortlistDecision(job_id=first, decision="approve"),
        ShortlistDecision(job_id=second, decision="reject", reason_tags=[ReasonTag.NOT_MY_DOMAIN]),
    ]
    done = svc2.approve_shortlist(tid, decisions)
    assert done.status in ("completed", "waiting_review")
    saved = {d.posting_id: d.decision for d in svc2.repo.all_decisions()}
    assert saved[first] == "approve" and saved[second] == "reject"
    assert len(saved) == len(items)  # unmentioned jobs recorded as defer
    assert svc2.store.search(("preferences", "default"), limit=100)
    svc2.close()


def test_approve_rejects_unknown_jobs_and_wrong_state(tmp_path: Path) -> None:
    with demo_service(tmp_path) as svc:
        tid = svc.start_run().thread_id
        with pytest.raises(ValueError, match="not on the shortlist"):
            svc.approve_shortlist(tid, [ShortlistDecision(job_id="nope", decision="approve")])
        with pytest.raises(ValueError, match="waiting for input"):
            svc.resume(tid, None)
        with pytest.raises(ValueError, match="unknown thread"):
            svc.resume("missing", None)


def test_decided_jobs_are_not_shortlisted_again(tmp_path: Path) -> None:
    with demo_service(tmp_path) as svc:
        out = svc.start_run()
        first = out.payload["items"][0]["job_id"]  # type: ignore[index]
        svc.approve_shortlist(out.thread_id, [ShortlistDecision(job_id=first, decision="reject")])
        again = svc.start_run()
        assert first not in {i["job_id"] for i in again.payload["items"]}  # type: ignore[index]


def test_budget_halt_is_checkpointed_and_resumable(tmp_path: Path) -> None:
    with demo_service(tmp_path, max_tokens_per_run=3000) as svc:
        out = svc.start_run()
        assert out.status == "halted_budget" and "make resume" in out.error
        assert [p.waiting_for for p in svc.list_pending()] == ["resume (halted_budget)"]
        svc.services.settings.max_tokens_per_run = 10**7  # user raises the cap
        resumed = svc.resume(out.thread_id)
        assert resumed.status == "waiting_shortlist"


def test_crash_then_resume_from_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    real = match_mod.match_jobs

    def flaky(state, runtime):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated crash")
        return real(state, runtime)

    monkeypatch.setattr("careergraph.graphs.job_search.graph.match_jobs", flaky)
    with demo_service(tmp_path) as svc:
        out = svc.start_run()
        assert out.status == "failed" and "simulated crash" in out.error
        tokens_before = svc.repo.run_totals(out.thread_id)[0]
        resumed = svc.resume(out.thread_id)
        assert resumed.status == "waiting_shortlist"
        # extraction branches were checkpointed: resuming did not re-run them
        assert svc.repo.run_totals(out.thread_id)[0] - tokens_before < 2000
