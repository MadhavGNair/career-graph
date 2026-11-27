"""tracker: the second graph. Table of contents:

update_status --(error or any status but interview)--> wrap_up -> END
update_status --(interview)--> interview_prep -> ask_question (PAUSE) -> score_answer
score_answer --(more turns)--> ask_question ; --(done or /stop)--> wrap_up
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.tracker.nodes.ask_question import ask_question
from careergraph.graphs.tracker.nodes.interview_prep import interview_prep
from careergraph.graphs.tracker.nodes.score_answer import score_answer
from careergraph.graphs.tracker.nodes.update_status import update_status
from careergraph.graphs.tracker.nodes.wrap_up import wrap_up
from careergraph.graphs.tracker.state import TrackerState
from careergraph.service.wiring import Services


def on_status(state: TrackerState) -> str:
    """Router on the status change."""
    if state.get("error"):
        return "done"
    return "interview" if state["new_status"] == "interview" else "done"


def after_prep(state: TrackerState) -> str:
    """Start the mock interview only when prep produced questions."""
    prep = state.get("prep")
    return "ask" if prep is not None and prep.questions and not state.get("error") else "done"


def next_turn(state: TrackerState, runtime: Ctx) -> str:
    """Continue until MOCK_INTERVIEW_TURNS, the question list ends, or the answer is /stop."""
    prep = state.get("prep")
    limit = min(len(prep.questions) if prep else 0, runtime.context.settings.mock_interview_turns)
    stop = state.get("pending_answer", "").strip().lower() == "/stop"
    return "done" if stop or state.get("turn", 0) >= limit else "ask"


def build_tracker_graph() -> StateGraph[TrackerState, Services]:
    """Status changes with a router, interview prep and a mock-interview loop."""
    g: StateGraph[TrackerState, Services] = StateGraph(TrackerState, context_schema=Services)
    g.add_node("update_status", update_status)
    g.add_node("interview_prep", interview_prep)
    g.add_node("ask_question", ask_question)  # PAUSE per turn
    g.add_node("score_answer", score_answer)
    g.add_node("wrap_up", wrap_up)
    g.add_edge(START, "update_status")
    g.add_conditional_edges(
        "update_status", on_status, {"interview": "interview_prep", "done": "wrap_up"}
    )
    g.add_conditional_edges(
        "interview_prep", after_prep, {"ask": "ask_question", "done": "wrap_up"}
    )
    g.add_edge("ask_question", "score_answer")
    g.add_conditional_edges("score_answer", next_turn, {"ask": "ask_question", "done": "wrap_up"})
    g.add_edge("wrap_up", END)
    return g
