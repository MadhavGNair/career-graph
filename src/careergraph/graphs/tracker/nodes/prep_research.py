"""prep_research (interview_prep subgraph)

Purpose:      Reuse the research_company subgraph for the interviewing company.
Reads:        job, run_id
Writes:       research
Uses LLM?:    via research_company (cheap tier + tools); skipped when research is disabled
Side effects: HTTP via SafeFetcher
Config keys:  ENABLE_COMPANY_RESEARCH, SEARCH_PROVIDER, RESEARCH_MAX_*
"""

from __future__ import annotations

from typing import Any

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.research_company import RESEARCH_COMPANY
from careergraph.graphs.tracker.state import PrepState


def prep_research(state: PrepState, runtime: Ctx) -> dict[str, Any]:
    """Run the shared research loop (the same subgraph the job_search graph uses)."""
    ctx = runtime.context
    if not ctx.settings.enable_company_research:
        return {"research": None}
    job = state["job"]
    info = ctx.cfg.search.companies.get(job.posting.company)
    result = RESEARCH_COMPANY.invoke(
        {
            "messages": [],
            "run_id": state["run_id"],
            "job_id": job.posting.id,
            "company": job.posting.company,
            "allowed_domains": [info.domain] if info and info.domain else [],
            "steps": 0,
            "tokens": 0,
        },
        context=ctx,
    )
    return {"research": result["brief"]}
