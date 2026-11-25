"""job_search: the table of contents of CareerGraph. Read top to bottom.

ingest_profile -> extract_profile -> find_jobs -> extract_jobs (Send per posting)
-> match_jobs -> human_shortlist (PAUSE) -> research_company (optional, Send per job)
-> document_factory (Send per job: draft <-> verify loop) -> human_review (PAUSE, optional)
-> render_latex -> save_results
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from careergraph.graphs.job_search.nodes.extract_profile import extract_profile
from careergraph.graphs.job_search.nodes.ingest_profile import ingest_profile
from careergraph.graphs.job_search.routing import profile_route
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.service.wiring import Services


def build_profile_graph() -> StateGraph[JobSearchState, Services]:
    """`make profile`: nodes 1-2 only."""
    g = StateGraph(JobSearchState, context_schema=Services)
    g.add_node("ingest_profile", ingest_profile)
    g.add_node("extract_profile", extract_profile)
    g.add_edge(START, "ingest_profile")
    g.add_conditional_edges(
        "ingest_profile", profile_route, {"extract": "extract_profile", "cached": END}
    )
    g.add_edge("extract_profile", END)
    return g


__all__ = ["CompiledStateGraph", "build_profile_graph"]
