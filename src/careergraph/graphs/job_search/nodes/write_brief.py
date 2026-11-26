"""write_brief (research_company subgraph)

Purpose:      Turn fetched pages into a ResearchBrief whose facts cite only URLs that were
              actually read (uncited or invented sources are dropped).
Reads:        messages (fetch_page / web_search results), company, steps, tokens, stop_reason
Writes:       brief
Uses LLM?:    cheap tier, structured output (skipped when no page was read)
Side effects: none
Config keys:  CHEAP_MODEL
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from careergraph.domain.models import ResearchBrief
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.state import ResearchState
from careergraph.llm.prompts import RESEARCH_BRIEF_SYSTEM, research_brief_prompt


def _pages(state: ResearchState) -> list[dict[str, str]]:
    pages = []
    for m in state.get("messages", []):
        if isinstance(m, ToolMessage) and m.name == "fetch_page":
            try:
                data = json.loads(str(m.content))
            except json.JSONDecodeError:
                continue
            if data.get("text"):
                pages.append(
                    {
                        "url": data["url"],
                        "title": data.get("title", ""),
                        "text": data["text"],
                        "injection_flag": data.get("injection_flag", False),
                    }
                )
    return pages


def write_brief(state: ResearchState, runtime: Ctx) -> dict[str, Any]:
    """Summarise cited facts."""
    ctx = runtime.context
    company = state["company"]
    pages = _pages(state)
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    reason = state.get("stop_reason") or ("model finished" if isinstance(last, AIMessage) else "")
    if not pages:
        brief = ResearchBrief(
            company=company, summary="No pages could be read.", stopped_reason=reason
        )
    else:
        brief = ctx.models.get_model("cheap").structured(
            task="research_brief",
            schema=ResearchBrief,
            system=RESEARCH_BRIEF_SYSTEM,
            prompt=research_brief_prompt(company, pages),
            payload={"company": company, "pages": pages},
            run_id=state["run_id"],
        )
        read = {p["url"] for p in pages}
        brief = brief.model_copy(
            update={
                "facts": [f for f in brief.facts if f.source_url in read],
                "sources": [s for s in brief.sources if s.url in read],
                "stopped_reason": reason,
            }
        )
    tokens = state.get("tokens", 0)
    return {
        "brief": brief.model_copy(
            update={"steps_used": state.get("steps", 0), "tokens_used": tokens}
        )
    }
