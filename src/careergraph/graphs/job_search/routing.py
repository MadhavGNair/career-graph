"""Conditional-edge functions. Pure functions of state (+ runtime settings): easy to test.

Routers that fan out with Send are only attached to single-run nodes (never to a node that
itself ran in N parallel branches), otherwise every branch would fan out again.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import Send

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState


def profile_route(state: JobSearchState) -> str:
    """Skip extraction when every document hash is unchanged and a cached extraction exists."""
    return "cached" if state.get("profile_cached") else "extract"


def fan_out_postings(state: JobSearchState) -> list[Send] | str:
    """One extract_jobs branch per new posting; straight to matching if none are new."""
    postings = state.get("to_analyse", [])
    if not postings:
        return "match_jobs"
    return [Send("extract_jobs", {"run_id": state["run_id"], "posting": p}) for p in postings]


def after_shortlist(state: JobSearchState, runtime: Ctx) -> list[Send] | str:
    """Nothing approved -> save_results; research enabled -> one research branch per job."""
    approved = state.get("approved", [])
    if not approved:
        return "save_results"
    if not runtime.context.settings.enable_company_research:
        return "select_evidence"
    analyses = state.get("analyses", {})
    return [
        Send("research_company", {"run_id": state["run_id"], "job": analyses[j]}) for j in approved
    ]


def _doc_branch(state: JobSearchState, job_id: str, mode: str) -> dict[str, Any]:
    profile = state.get("profile")
    assert profile is not None
    by_id = profile.by_id()
    selected = state.get("evidence_selection", {}).get(job_id, [])
    existing = state.get("drafts", {}).get(job_id)
    draft = existing if mode == "verify" else None
    critique = existing.critique if existing is not None and mode == "draft" else ""
    return {
        "run_id": state["run_id"],
        "job": state.get("analyses", {})[job_id],
        "evidence": [by_id[i] for i in selected if i in by_id],
        "evidence_pool": profile.evidence,
        "research": state.get("research", {}).get(job_id),
        "draft": draft,
        "critique": critique,
        "mode": mode,
    }


def fan_out_drafts(state: JobSearchState) -> list[Send]:
    """One document_factory branch per approved job."""
    return [
        Send("document_factory", _doc_branch(state, j, "draft")) for j in state.get("approved", [])
    ]


def after_documents(state: JobSearchState, runtime: Ctx) -> str:
    """Review pause unless REQUIRE_DOCUMENT_REVIEW=false (branches dedupe to one target)."""
    return "human_review" if runtime.context.settings.require_document_review else "render_latex"


def after_review(state: JobSearchState) -> list[Send] | str:
    """Edits/regenerations go back through document_factory; undecided drafts loop back to
    review; otherwise render."""
    redo = state.get("redo", {})
    if redo:
        return [Send("document_factory", _doc_branch(state, j, mode)) for j, mode in redo.items()]
    approved = set(state.get("approved", []))
    waiting = [
        d
        for j, d in state.get("drafts", {}).items()
        if j in approved and d.status not in ("approved", "rejected")
    ]
    return "human_review" if waiting else "render_latex"
