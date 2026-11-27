"""ask_question (PAUSE, once per mock-interview turn)

Purpose:      Show the next question (and your matching STAR stories as hints) and wait for
              your answer. Answer "/stop" to end early.
Reads:        prep, turn
Writes:       pending_answer
Uses LLM?:    deterministic
Side effects: interrupt()
Config keys:  MOCK_INTERVIEW_TURNS
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.tracker.state import TrackerState


def ask_question(state: TrackerState, runtime: Ctx) -> dict[str, Any]:
    """Interrupt with the current question."""
    prep = state.get("prep")
    assert prep is not None
    turn = state.get("turn", 0)
    q = prep.questions[turn]
    total = min(len(prep.questions), runtime.context.settings.mock_interview_turns)
    hints = [s.title for s in prep.stories if q.skill and q.skill in s.title.lower()] or [
        s.title for s in prep.stories[:2]
    ]
    answer = interrupt(
        {
            "type": "mock_interview",
            "run_id": state["run_id"],
            "turn": turn + 1,
            "of": total,
            "question": q.model_dump(),
            "story_hints": hints,
        }
    )
    return {"pending_answer": str(answer or "")}
