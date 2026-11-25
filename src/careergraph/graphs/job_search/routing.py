"""Conditional-edge functions. Pure functions of state: easy to unit test."""

from __future__ import annotations

from langgraph.types import Send

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
