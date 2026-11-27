"""update_status

Purpose:      Apply a validated status transition (e.g. ready -> applied -> interview).
Reads:        job_id, new_status, note
Writes:       old_status, error
Uses LLM?:    deterministic
Side effects: applications + application_events tables
Config keys:  none
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.status import ApplicationStatus, InvalidTransition
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.tracker.state import TrackerState


def update_status(state: TrackerState, runtime: Ctx) -> dict[str, Any]:
    """Validate and persist the change; errors end the graph without side effects."""
    repo = runtime.context.repo
    app = repo.get_application(state["job_id"])
    if app is None:
        return {"error": f"no application {state['job_id']}"}
    try:
        new = ApplicationStatus(state["new_status"])
        repo.set_status(state["job_id"], new, state.get("note", ""))
    except (ValueError, InvalidTransition) as exc:
        return {"error": str(exc), "old_status": app.status}
    return {"old_status": app.status, "error": ""}
