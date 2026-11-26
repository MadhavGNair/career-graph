"""Typed graph state. Reducers merge results from parallel Send branches by job id."""

from __future__ import annotations

from typing import Annotated, Any, Required, TypedDict

from careergraph.domain.models import (
    AnalyzedJob,
    DocumentDraft,
    EvidenceItem,
    JobPosting,
    MatchResult,
    ProfileDocument,
    ProfileSnapshot,
    RenderResult,
    ResearchBrief,
    ShortlistDecision,
)


def merge_by_key[V](left: dict[str, V] | None, right: dict[str, V] | None) -> dict[str, V]:
    """Reducer: union of dicts; right wins per key (one branch writes one job id)."""
    return {**(left or {}), **(right or {})}


class JobSearchState(TypedDict, total=False):
    """State of one `job_search` thread (one run)."""

    run_id: Required[str]
    force_profile: bool
    # profile
    documents: list[ProfileDocument]
    pinned: list[EvidenceItem]
    profile_key: str
    profile_cached: bool
    profile: ProfileSnapshot
    # jobs
    to_analyse: list[JobPosting]
    analyses: Annotated[dict[str, AnalyzedJob], merge_by_key]
    funnel: dict[str, Any]
    # matching + first pause
    matches: list[MatchResult]
    shortlist: list[str]
    decisions: list[ShortlistDecision]
    approved: list[str]
    # research + documents + second pause
    research: Annotated[dict[str, ResearchBrief], merge_by_key]
    evidence_selection: dict[str, list[str]]
    drafts: Annotated[dict[str, DocumentDraft], merge_by_key]
    redo: dict[str, str]
    review_errors: list[str]
    rendered: Annotated[dict[str, RenderResult], merge_by_key]
    summary: str


class JobBranch(TypedDict):
    """Payload of one extract_jobs Send branch."""

    run_id: str
    posting: JobPosting
