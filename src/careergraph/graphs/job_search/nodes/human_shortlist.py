"""human_shortlist (PAUSE)

Purpose:      Show the ranked shortlist and wait for the human: approve / reject / defer each
              job, with optional reason tags and a note. Learn preferences from the tags.
Reads:        matches, shortlist, analyses, run_id
Writes:       decisions, approved
Uses LLM?:    deterministic (tags are a fixed list; notes are stored, never interpreted)
Side effects: interrupt(); writes decisions table; writes preferences to the LangGraph Store
Config keys:  criteria.yaml preference.enabled
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.matching.payload import HELP, parse_decisions, reason_tags, shortlist_items
from careergraph.memory import preferences


def human_shortlist(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Pause for shortlist decisions. Everything before interrupt() re-runs on resume, so it is
    kept deterministic and side-effect free."""
    ctx = runtime.context
    analyses = state.get("analyses", {})
    items = shortlist_items(state.get("matches", []), state.get("shortlist", []), analyses)
    if not items:
        return {"decisions": [], "approved": []}
    raw = interrupt(
        {
            "type": "shortlist",
            "run_id": state["run_id"],
            "items": items,
            "reason_tags": reason_tags(),
            "help": HELP,
        }
    )
    decisions = parse_decisions(raw, [i["job_id"] for i in items])
    scores = {i["job_id"]: i["score"] for i in items}
    meta = {
        d.job_id: {
            "title": analyses[d.job_id].posting.title,
            "company": analyses[d.job_id].posting.company,
            "score": scores[d.job_id],
        }
        for d in decisions
    }
    ctx.repo.save_decisions(state["run_id"], [(d, meta[d.job_id]) for d in decisions])
    if ctx.cfg.criteria.preference.enabled and runtime.store is not None:
        preferences.learn(runtime.store, decisions, analyses)
    return {
        "decisions": decisions,
        "approved": [d.job_id for d in decisions if d.decision == "approve"],
    }
