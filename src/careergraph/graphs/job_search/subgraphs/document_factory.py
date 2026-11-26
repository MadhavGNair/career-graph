"""document_factory subgraph: draft_documents <-> verify_documents, run once per approved job
via Send. No interrupts here (they live at the top level only).

START --(mode=verify & draft present)--> verify_documents
START --(otherwise)--> draft_documents --> verify_documents
verify_documents --(revise: unsupported claims and revisions left)--> draft_documents
verify_documents --(done)--> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from careergraph.graphs.job_search.nodes.draft_documents import draft_documents
from careergraph.graphs.job_search.nodes.verify_documents import verify_documents
from careergraph.graphs.job_search.subgraphs.state import DocState
from careergraph.service.wiring import Services


def entry_route(state: DocState) -> str:
    """Edited drafts skip drafting and go straight to verification."""
    return "verify" if state.get("mode") == "verify" and state.get("draft") is not None else "draft"


def revise_route(state: DocState) -> str:
    """Loop back while claims are unsupported and MAX_REVISIONS is not reached."""
    return "revise" if state.get("revise") else "done"


def build_document_factory() -> StateGraph[DocState, Services]:
    """The draft/verify loop."""
    g: StateGraph[DocState, Services] = StateGraph(DocState, context_schema=Services)
    g.add_node("draft_documents", draft_documents)
    g.add_node("verify_documents", verify_documents)
    g.add_conditional_edges(
        START, entry_route, {"verify": "verify_documents", "draft": "draft_documents"}
    )
    g.add_edge("draft_documents", "verify_documents")
    g.add_conditional_edges(
        "verify_documents", revise_route, {"revise": "draft_documents", "done": END}
    )
    return g


DOCUMENT_FACTORY = build_document_factory().compile(name="document_factory")
