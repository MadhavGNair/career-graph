"""research_company subgraph: an explicit ReAct loop (no prebuilt agent).

START -> plan_query --(tool calls)--> tools (ToolNode) -> reflect_or_stop
reflect_or_stop --(continue)--> plan_query ; --(limit hit)--> write_brief
plan_query --(no tool calls)--> write_brief -> END

Hard limits: RESEARCH_MAX_STEPS, RESEARCH_MAX_TOKENS, fetches restricted to company domains.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from careergraph.graphs.job_search.nodes.plan_query import plan_query
from careergraph.graphs.job_search.nodes.reflect_or_stop import reflect_or_stop
from careergraph.graphs.job_search.nodes.write_brief import write_brief
from careergraph.graphs.job_search.subgraphs.research_tools import RESEARCH_TOOLS
from careergraph.graphs.job_search.subgraphs.state import ResearchState
from careergraph.service.wiring import Services


def after_plan(state: ResearchState) -> str:
    """Tool calls -> run tools; otherwise the model is done."""
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "done"


def after_reflect(state: ResearchState) -> str:
    """Continue unless a limit or the page budget was reached."""
    return "done" if state.get("stop_reason") else "continue"


def build_research_company() -> StateGraph[ResearchState, Services]:
    """The research loop."""
    g: StateGraph[ResearchState, Services] = StateGraph(ResearchState, context_schema=Services)
    g.add_node("plan_query", plan_query)
    g.add_node("tools", ToolNode(RESEARCH_TOOLS))
    g.add_node("reflect_or_stop", reflect_or_stop)
    g.add_node("write_brief", write_brief)
    g.add_edge(START, "plan_query")
    g.add_conditional_edges("plan_query", after_plan, {"tools": "tools", "done": "write_brief"})
    g.add_edge("tools", "reflect_or_stop")
    g.add_conditional_edges(
        "reflect_or_stop", after_reflect, {"continue": "plan_query", "done": "write_brief"}
    )
    g.add_edge("write_brief", END)
    return g


RESEARCH_COMPANY = build_research_company().compile(name="research_company")
