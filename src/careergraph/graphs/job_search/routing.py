"""Conditional-edge functions. Pure functions of state: easy to unit test."""

from __future__ import annotations

from careergraph.graphs.job_search.state import JobSearchState


def profile_route(state: JobSearchState) -> str:
    """Skip extraction when every document hash is unchanged and a cached extraction exists."""
    return "cached" if state.get("profile_cached") else "extract"
