"""interview_prep subgraph: prep_research (reuses research_company) -> derive_questions ->
build_stories. No interrupts inside."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from careergraph.graphs.tracker.nodes.build_stories import build_stories
from careergraph.graphs.tracker.nodes.derive_questions import derive_questions
from careergraph.graphs.tracker.nodes.prep_research import prep_research
from careergraph.graphs.tracker.state import PrepState
from careergraph.service.wiring import Services


def build_interview_prep() -> StateGraph[PrepState, Services]:
    """Research, questions, stories."""
    g: StateGraph[PrepState, Services] = StateGraph(PrepState, context_schema=Services)
    g.add_node("prep_research", prep_research)
    g.add_node("derive_questions", derive_questions)
    g.add_node("build_stories", build_stories)
    g.add_edge(START, "prep_research")
    g.add_edge("prep_research", "derive_questions")
    g.add_edge("derive_questions", "build_stories")
    g.add_edge("build_stories", END)
    return g


INTERVIEW_PREP = build_interview_prep().compile(name="interview_prep")
