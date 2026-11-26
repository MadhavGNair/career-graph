"""reflect_or_stop (research_company subgraph)

Purpose:      After tools ran, decide whether to continue the loop: stop on the step limit,
              the token limit, or when two pages have been read.
Reads:        steps, tokens, messages
Writes:       stop_reason ("" = continue)
Uses LLM?:    deterministic
Side effects: none
Config keys:  RESEARCH_MAX_STEPS, RESEARCH_MAX_TOKENS
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.state import ResearchState

ENOUGH_PAGES = 3


def reflect_or_stop(state: ResearchState, runtime: Ctx) -> dict[str, Any]:
    """Enforce hard limits after every tool round."""
    s = runtime.context.settings
    pages = [
        m
        for m in state.get("messages", [])
        if isinstance(m, ToolMessage) and m.name == "fetch_page"
    ]
    if state.get("steps", 0) >= s.research_max_steps:
        return {"stop_reason": f"step limit ({s.research_max_steps})"}
    if state.get("tokens", 0) >= s.research_max_tokens:
        return {"stop_reason": f"token limit ({s.research_max_tokens})"}
    if len(pages) >= ENOUGH_PAGES:
        return {"stop_reason": f"read {len(pages)} pages"}
    return {"stop_reason": ""}
