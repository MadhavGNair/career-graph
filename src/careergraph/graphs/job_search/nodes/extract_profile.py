"""extract_profile

Purpose:      Turn documents into citable evidence items (ev-001...) with normalised skills;
              merge pinned items from evidence.yaml; cache the result by content hash.
Reads:        documents, pinned, profile_key, run_id
Writes:       profile
Uses LLM?:    cheap tier, structured output (one call per document)
Side effects: writes profile_cache table
Config keys:  CHEAP_MODEL, skills.yaml aliases
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.evidence import build_snapshot
from careergraph.domain.models import EvidenceDraft, ProfileExtraction
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.llm.prompts import EXTRACT_PROFILE_SYSTEM, extract_profile_prompt


def extract_profile(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Extract evidence from every document and build the profile snapshot."""
    ctx = runtime.context
    llm = ctx.models.get_model("cheap")
    known = sorted(ctx.skills.known)
    drafts: list[EvidenceDraft] = []
    for doc in state.get("documents", []):
        out = llm.structured(
            task="extract_profile",
            schema=ProfileExtraction,
            system=EXTRACT_PROFILE_SYSTEM,
            prompt=extract_profile_prompt(doc, known),
            payload={"document": doc.model_dump(mode="json")},
            run_id=state["run_id"],
        )
        drafts.extend(out.items)
    hashes = {d.source_id: d.content_hash for d in state.get("documents", [])}
    snap = build_snapshot(drafts, state.get("pinned", []), ctx.skills, hashes)
    ctx.repo.put_profile(state.get("profile_key", ""), snap)
    return {"profile": snap}
