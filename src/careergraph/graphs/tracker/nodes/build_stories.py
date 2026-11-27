"""build_stories (interview_prep subgraph)

Purpose:      STAR stories built only from the evidence most relevant to the job; each cites
              evidence ids (unknown ids are dropped).
Reads:        job, evidence, prep, run_id
Writes:       prep (stories)
Uses LLM?:    cheap tier, structured output
Side effects: none
Config keys:  CHEAP_MODEL
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import StoryDraft
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.tracker.state import PrepState
from careergraph.llm.prompts import STORIES_SYSTEM, stories_prompt


def build_stories(state: PrepState, runtime: Ctx) -> dict[str, Any]:
    """Draft STAR stories from evidence."""
    job, evidence, prep = state["job"], state.get("evidence", []), state.get("prep")
    assert prep is not None
    facts = {
        "title": job.posting.title,
        "company": job.posting.company,
        "must_have": job.analysis.must_have,
    }
    out = runtime.context.models.get_model("cheap").structured(
        task="interview_stories",
        schema=StoryDraft,
        system=STORIES_SYSTEM,
        prompt=stories_prompt(facts, evidence),
        payload={"job": facts, "evidence": [e.model_dump(mode="json") for e in evidence]},
        run_id=state["run_id"],
    )
    known = {e.id for e in evidence}
    stories = [s for s in out.stories if s.evidence_ids and set(s.evidence_ids) <= known]
    return {"prep": prep.model_copy(update={"stories": stories})}
