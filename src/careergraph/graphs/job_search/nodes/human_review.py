"""human_review (PAUSE; skipped when REQUIRE_DOCUMENT_REVIEW=false)

Purpose:      Show every draft with its verification report; the human approves, edits (patch
              by claim id, re-verified), regenerates or rejects each one. Flagged drafts need
              an explicit override to be approved.
Reads:        drafts, approved, analyses, research, review_errors
Writes:       drafts (status updates / patched drafts), redo {job_id: mode}, review_errors
Uses LLM?:    deterministic
Side effects: interrupt()
Config keys:  REQUIRE_DOCUMENT_REVIEW
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from careergraph.documents.claims import apply_patch
from careergraph.documents.review import HELP, parse_actions, review_rows
from careergraph.domain.models import DocumentDraft
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState

DONE = ("approved", "rejected")


def human_review(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Pause for review decisions; apply them deterministically."""
    drafts = state.get("drafts", {})
    pending = [
        d for jid, d in drafts.items() if jid in state.get("approved", []) and d.status not in DONE
    ]
    if not pending:
        return {"redo": {}, "review_errors": []}
    rows = review_rows(pending, state.get("analyses", {}), state.get("research", {}))
    raw = interrupt(
        {
            "type": "review",
            "run_id": state["run_id"],
            "drafts": rows,
            "errors": state.get("review_errors", []),
            "help": HELP,
        }
    )
    updates: dict[str, DocumentDraft] = {}
    redo: dict[str, str] = {}
    errors: list[str] = []
    for a in parse_actions(raw, [d.job_id for d in pending]):
        d = drafts[a.job_id]
        if a.action == "approve":
            if d.flagged and not a.override:
                errors.append(
                    f"{a.job_id}: still has unsupported claims; approve with override=true"
                )
                continue
            updates[a.job_id] = d.model_copy(update={"status": "approved", "override": d.flagged})
        elif a.action == "reject":
            updates[a.job_id] = d.model_copy(update={"status": "rejected", "critique": a.reason})
        elif a.action == "edit":
            patched, unknown = apply_patch(d, a.patch)
            if unknown:
                errors.append(f"{a.job_id}: unknown claim ids {unknown}")
            updates[a.job_id] = patched.model_copy(update={"status": "drafted"})
            redo[a.job_id] = "verify"
        else:
            updates[a.job_id] = d.model_copy(
                update={"status": "drafted", "critique": a.reason or "Regenerate."}
            )
            redo[a.job_id] = "draft"
    return {"drafts": updates, "redo": redo, "review_errors": errors}
