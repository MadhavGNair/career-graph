"""wrap_up

Purpose:      Summarise the status change and, after a mock interview, the average rubric
              scores and the weakest dimension.
Reads:        old_status, new_status, error, transcript, prep
Writes:       summary
Uses LLM?:    deterministic
Side effects: none
Config keys:  none
"""

from __future__ import annotations

from typing import Any

from careergraph.graphs.tracker.state import TrackerState

DIMS = ("structure", "relevance", "specificity", "conciseness")


def wrap_up(state: TrackerState) -> dict[str, Any]:
    """Write the summary."""
    error = state.get("error")
    if error:
        return {"summary": f"No change: {error}"}
    lines = [f"{state['job_id']}: {state.get('old_status')} -> {state['new_status']}"]
    turns = state.get("transcript", [])
    prep = state.get("prep")
    if prep is not None:
        lines.append(f"Prep: {len(prep.questions)} questions, {len(prep.stories)} STAR stories")
    if turns:
        avg = {d: sum(getattr(t.score, d) for t in turns) / len(turns) for d in DIMS}
        overall = sum(avg.values()) / len(DIMS)
        weakest = min(avg, key=lambda d: avg[d])
        lines.append(
            f"Mock interview: {len(turns)} answers, overall {overall:.1f}/5, weakest: {weakest}"
        )
    return {"summary": "\n".join(lines)}
