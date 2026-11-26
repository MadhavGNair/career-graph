"""research_company (optional; runs once per approved job via Send)

Purpose:      Run the research subgraph for the job's company and store a cited brief.
Reads:        branch payload {run_id, job}
Writes:       research[job_id]
Uses LLM?:    via the subgraph (cheap tier, tools: web_search, fetch_page)
Side effects: HTTP via SafeFetcher (search provider + company pages)
Config keys:  ENABLE_COMPANY_RESEARCH, SEARCH_PROVIDER, RESEARCH_MAX_STEPS, RESEARCH_MAX_TOKENS,
              search.yaml companies.<name>.domain
"""

from __future__ import annotations

from typing import Any

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.research_company import RESEARCH_COMPANY
from careergraph.graphs.job_search.subgraphs.state import DocState


def research_company(branch: DocState, runtime: Ctx) -> dict[str, Any]:
    """Research one company (failures yield an empty, low-confidence brief)."""
    ctx = runtime.context
    job = branch["job"]
    info = ctx.cfg.search.companies.get(job.posting.company)
    domains = [info.domain] if info and info.domain else []
    result = RESEARCH_COMPANY.invoke(
        {
            "messages": [],
            "run_id": branch["run_id"],
            "job_id": job.posting.id,
            "company": job.posting.company,
            "allowed_domains": domains,
            "steps": 0,
            "tokens": 0,
        },
        context=ctx,
    )
    return {"research": {job.posting.id: result["brief"]}}
