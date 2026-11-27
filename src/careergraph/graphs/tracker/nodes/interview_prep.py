"""interview_prep

Purpose:      Run the interview_prep subgraph (research -> questions -> STAR stories) for the
              application that moved to "interview".
Reads:        job_id, run_id
Writes:       prep, turn (reset to 0)
Uses LLM?:    via the subgraph
Side effects: none
Config keys:  see subgraph nodes
"""

from __future__ import annotations

from typing import Any

from careergraph.documents.assemble import select_evidence
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.tracker.state import TrackerState
from careergraph.graphs.tracker.subgraph import INTERVIEW_PREP
from careergraph.retrieval.index import HybridIndex


def interview_prep(state: TrackerState, runtime: Ctx) -> dict[str, Any]:
    """Prepare questions and stories; without a stored analysis/profile, prep is skipped."""
    ctx = runtime.context
    job = ctx.repo.cached_analysis_by_posting(state["job_id"])
    profile = ctx.repo.latest_profile()
    if job is None or profile is None:
        return {"error": "no stored analysis or profile for interview prep", "prep": None}
    index = HybridIndex(
        [(e.id, f"{e.text} {' '.join(e.skills)}") for e in profile.evidence], ctx.embedder
    )
    evidence = select_evidence(job, profile, index, k=8)
    out = INTERVIEW_PREP.invoke(
        {"run_id": state["run_id"], "job": job, "evidence": evidence}, context=ctx
    )
    return {"prep": out["prep"], "turn": 0}
