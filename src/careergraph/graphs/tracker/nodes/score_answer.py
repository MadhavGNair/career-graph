"""score_answer

Purpose:      Score the answer against the rubric (structure, relevance, specificity,
              conciseness; 1-5 each) with actionable feedback.
Reads:        prep, turn, pending_answer, run_id
Writes:       transcript (+1 turn), turn
Uses LLM?:    cheap tier, structured output (the answer is delimited as untrusted text)
Side effects: none
Config keys:  CHEAP_MODEL
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import AnswerScore, MockTurn
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.tracker.state import TrackerState
from careergraph.llm.prompts import SCORE_SYSTEM, score_prompt


def score_answer(state: TrackerState, runtime: Ctx) -> dict[str, Any]:
    """Score one answer."""
    prep = state.get("prep")
    assert prep is not None
    turn = state.get("turn", 0)
    q, answer = prep.questions[turn], state.get("pending_answer", "")
    score = runtime.context.models.get_model("cheap").structured(
        task="score_answer",
        schema=AnswerScore,
        system=SCORE_SYSTEM,
        prompt=score_prompt(q.text, answer),
        payload={"question": q.text, "answer": answer},
        run_id=state["run_id"],
    )
    clamp = {
        k: max(1, min(5, getattr(score, k)))
        for k in ("structure", "relevance", "specificity", "conciseness")
    }
    score = score.model_copy(update=clamp)
    return {"transcript": [MockTurn(question=q, answer=answer, score=score)], "turn": turn + 1}
