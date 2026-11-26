"""job_search: the table of contents of CareerGraph. Read top to bottom.

ingest_profile -> extract_profile -> find_jobs -> extract_jobs (Send per posting)
-> match_jobs -> human_shortlist (PAUSE) -> research_company (optional, Send per job)
-> document_factory (Send per job: draft <-> verify loop) -> human_review (PAUSE, optional)
-> render_latex -> save_results
"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from careergraph.graphs.job_search.nodes.document_factory import document_factory
from careergraph.graphs.job_search.nodes.extract_jobs import extract_jobs
from careergraph.graphs.job_search.nodes.extract_profile import extract_profile
from careergraph.graphs.job_search.nodes.find_jobs import find_jobs
from careergraph.graphs.job_search.nodes.human_review import human_review
from careergraph.graphs.job_search.nodes.human_shortlist import human_shortlist
from careergraph.graphs.job_search.nodes.ingest_profile import ingest_profile
from careergraph.graphs.job_search.nodes.match_jobs import match_jobs
from careergraph.graphs.job_search.nodes.render_latex import render_latex
from careergraph.graphs.job_search.nodes.research_company import research_company
from careergraph.graphs.job_search.nodes.save_results import save_results
from careergraph.graphs.job_search.nodes.select_evidence import select_evidence
from careergraph.graphs.job_search.routing import (
    after_documents,
    after_review,
    after_shortlist,
    fan_out_drafts,
    fan_out_postings,
    profile_route,
)
from careergraph.graphs.job_search.state import JobBranch, JobSearchState
from careergraph.graphs.job_search.subgraphs.state import DocState
from careergraph.service.wiring import Services

Graph = StateGraph[JobSearchState, Services]


def _profile_and_jobs(g: Graph, after_match: str) -> None:
    """Nodes 1-5, shared by the full graph and `make jobs`."""
    g.add_node("ingest_profile", ingest_profile)
    g.add_node("extract_profile", extract_profile)
    g.add_node("find_jobs", find_jobs)
    g.add_node("extract_jobs", cast(Any, extract_jobs), input_schema=JobBranch)
    g.add_node("match_jobs", match_jobs)

    g.add_edge(START, "ingest_profile")
    g.add_conditional_edges(
        "ingest_profile", profile_route, {"extract": "extract_profile", "cached": "find_jobs"}
    )
    g.add_edge("extract_profile", "find_jobs")
    g.add_conditional_edges("find_jobs", fan_out_postings, ["extract_jobs", "match_jobs"])
    g.add_edge("extract_jobs", "match_jobs")  # join: runs once after every branch finished
    g.add_edge("match_jobs", after_match)


def build_job_search_graph() -> Graph:
    """The full graph with both human pauses."""
    g: Graph = StateGraph(JobSearchState, context_schema=Services)
    _profile_and_jobs(g, after_match="human_shortlist")
    g.add_node("human_shortlist", human_shortlist)  # PAUSE 1
    g.add_node("research_company", cast(Any, research_company), input_schema=DocState)
    g.add_node("select_evidence", select_evidence)
    g.add_node("document_factory", cast(Any, document_factory), input_schema=DocState)
    g.add_node("human_review", human_review)  # PAUSE 2
    g.add_node("render_latex", render_latex)
    g.add_node("save_results", save_results)

    g.add_conditional_edges(
        "human_shortlist", after_shortlist, ["research_company", "select_evidence", "save_results"]
    )
    g.add_edge("research_company", "select_evidence")  # join after parallel research
    g.add_conditional_edges("select_evidence", fan_out_drafts, ["document_factory"])
    g.add_conditional_edges("document_factory", after_documents, ["human_review", "render_latex"])
    g.add_conditional_edges(
        "human_review", after_review, ["document_factory", "human_review", "render_latex"]
    )
    g.add_edge("render_latex", "save_results")
    g.add_edge("save_results", END)
    return g


def build_jobs_graph() -> Graph:
    """`make jobs`: nodes 1-5, ends with the shortlist in state (no pause)."""
    g: Graph = StateGraph(JobSearchState, context_schema=Services)
    _profile_and_jobs(g, after_match=END)
    return g


def build_profile_graph() -> Graph:
    """`make profile`: nodes 1-2 only."""
    g: Graph = StateGraph(JobSearchState, context_schema=Services)
    g.add_node("ingest_profile", ingest_profile)
    g.add_node("extract_profile", extract_profile)
    g.add_edge(START, "ingest_profile")
    g.add_conditional_edges(
        "ingest_profile", profile_route, {"extract": "extract_profile", "cached": END}
    )
    g.add_edge("extract_profile", END)
    return g
