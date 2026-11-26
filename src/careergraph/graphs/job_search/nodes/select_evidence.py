"""select_evidence

Purpose:      Join point after the shortlist (and optional research): pick the most relevant
              evidence for every approved job (skill evidence first, then hybrid retrieval).
Reads:        approved, analyses, profile
Writes:       evidence_selection {job_id: [evidence ids]}
Uses LLM?:    deterministic
Side effects: none
Config keys:  EMBEDDING_BACKEND, EMBEDDING_MODEL
"""

from __future__ import annotations

from typing import Any

from careergraph.documents.assemble import select_evidence as pick
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.retrieval.index import HybridIndex


def select_evidence(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Rank evidence per approved job."""
    profile = state.get("profile")
    assert profile is not None, "select_evidence needs a profile"
    docs = [(e.id, f"{e.text} {' '.join(e.skills)}") for e in profile.evidence]
    index = HybridIndex(docs, runtime.context.embedder)
    analyses = state.get("analyses", {})
    selection = {
        jid: [e.id for e in pick(analyses[jid], profile, index)]
        for jid in state.get("approved", [])
    }
    return {"evidence_selection": selection}
