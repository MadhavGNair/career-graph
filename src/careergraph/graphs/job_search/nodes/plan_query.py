"""plan_query (research_company subgraph)

Purpose:      One ReAct step: the model decides the next tool call (web_search / fetch_page)
              or that it has enough information.
Reads:        messages, company, allowed_domains, steps, tokens, run_id
Writes:       messages (+1 AIMessage), steps, tokens
Uses LLM?:    cheap tier with tools bound (tool choice left to the model)
Side effects: none (tools run in the ToolNode)
Config keys:  CHEAP_MODEL
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.research_tools import RESEARCH_TOOLS
from careergraph.graphs.job_search.subgraphs.state import ResearchState
from careergraph.llm.port import usage_from_message
from careergraph.llm.prompts import RESEARCH_SYSTEM, research_task_prompt


def plan_query(state: ResearchState, runtime: Ctx) -> dict[str, Any]:
    """Ask the model for the next action."""
    ctx = runtime.context
    messages = list(state.get("messages", []))
    new: list[Any] = []
    if not messages:
        new.append(
            HumanMessage(
                content=research_task_prompt(state["company"], state.get("allowed_domains", []))
            )
        )
    msg = ctx.models.get_model("cheap").tool_step(
        task="research_plan",
        system=RESEARCH_SYSTEM,
        messages=messages + new,
        tools=RESEARCH_TOOLS,
        payload={"company": state["company"], "allowed_domains": state.get("allowed_domains", [])},
        run_id=state["run_id"],
    )
    inp, out, _, _ = usage_from_message(msg)
    return {
        "messages": [*new, msg],
        "steps": state.get("steps", 0) + 1,
        "tokens": state.get("tokens", 0) + inp + out,
    }
