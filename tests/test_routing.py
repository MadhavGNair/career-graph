"""Routers and the draft/verify loop termination (revision cap)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.types import Send

from careergraph.domain.models import DocumentDraft
from careergraph.graphs.job_search.graph import build_jobs_graph
from careergraph.graphs.job_search.routing import after_review, after_shortlist, profile_route
from careergraph.graphs.job_search.subgraphs.document_factory import (
    DOCUMENT_FACTORY,
    entry_route,
    revise_route,
)
from careergraph.llm import fake as fake_mod
from tests.helpers import demo_services


class _Rt:
    def __init__(self, svc: Any) -> None:
        self.context = svc


def _state(tmp_path: Path, **kw: Any) -> tuple[Any, dict[str, Any]]:
    svc = demo_services(tmp_path, **kw)
    out = build_jobs_graph().compile().invoke({"run_id": "r"}, context=svc)
    return svc, out


def test_simple_routes() -> None:
    assert profile_route({"run_id": "r", "profile_cached": True}) == "cached"
    assert profile_route({"run_id": "r"}) == "extract"
    assert entry_route({"run_id": "r", "mode": "verify", "draft": None}) == "draft"  # type: ignore[typeddict-item]
    assert revise_route({"run_id": "r", "revise": True}) == "revise"  # type: ignore[typeddict-item]


def test_after_shortlist(tmp_path: Path) -> None:
    svc, st = _state(tmp_path)
    assert after_shortlist({**st, "approved": []}, _Rt(svc)) == "save_results"  # type: ignore[arg-type]
    assert after_shortlist({**st, "approved": st["shortlist"][:2]}, _Rt(svc)) == "select_evidence"  # type: ignore[arg-type]
    svc.settings.enable_company_research = True
    sends = after_shortlist({**st, "approved": st["shortlist"][:2]}, _Rt(svc))  # type: ignore[arg-type]
    assert isinstance(sends, list) and all(
        isinstance(s, Send) and s.node == "research_company" for s in sends
    )


def _branch(svc: Any, st: dict[str, Any], job_id: str) -> Any:
    prof = st["profile"]
    return {"run_id": "r", "job": st["analyses"][job_id], "evidence": prof.evidence[:10],
            "evidence_pool": prof.evidence, "research": None, "draft": None, "mode": "draft"}  # fmt: skip


def test_revision_loop_fixes_fabrication(tmp_path: Path) -> None:
    svc, st = _state(tmp_path)
    job = "gh-nimbus-analytics-4001"
    out = DOCUMENT_FACTORY.invoke(_branch(svc, st, job), context=svc)
    d: DocumentDraft = out["draft"]
    assert d.revision_count == 1 and d.status == "verified"
    assert "Google" in d.critique_log[0] and all(c.label != "unsupported" for c in d.report.checks)


def test_revision_loop_terminates_at_cap(tmp_path: Path, monkeypatch: Any) -> None:
    original = fake_mod.fake_draft

    def always_fabricate(payload: dict[str, Any], ids: set[str]) -> Any:
        return original({**payload, "revision": 0, "unsupported": []}, {payload["job_id"]})

    monkeypatch.setattr(fake_mod, "fake_draft", always_fabricate)
    svc, st = _state(tmp_path, max_revisions=2)
    job = st["shortlist"][0]
    d: DocumentDraft = DOCUMENT_FACTORY.invoke(_branch(svc, st, job), context=svc)["draft"]
    assert d.revision_count == 2 and d.status == "flagged" and d.flagged
    assert len(d.critique_log) == 3  # revisions 0, 1, 2 all failed; no fourth draft


def test_after_review_routes(tmp_path: Path) -> None:
    svc, st = _state(tmp_path)
    job = st["shortlist"][0]
    draft = DOCUMENT_FACTORY.invoke(_branch(svc, st, job), context=svc)["draft"]
    base: Any = {**st, "approved": [job], "drafts": {job: draft}, "evidence_selection": {}}
    assert after_review({**base, "redo": {}}) == "human_review"  # type: ignore[arg-type]
    approved = draft.model_copy(update={"status": "approved"})
    assert after_review({**base, "redo": {}, "drafts": {job: approved}}) == "render_latex"  # type: ignore[arg-type]
    sends = after_review({**base, "redo": {job: "verify"}})  # type: ignore[arg-type]
    assert (
        isinstance(sends, list)
        and sends[0].arg["mode"] == "verify"
        and sends[0].arg["draft"] is draft
    )
