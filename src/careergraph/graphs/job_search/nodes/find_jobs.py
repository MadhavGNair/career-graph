"""find_jobs

Purpose:      Collect postings from every configured source, filter them, drop near-duplicates,
              reuse analyses for unchanged content and cap how many new ones get analysed.
Reads:        (config only)
Writes:       to_analyse, analyses (cached ones), funnel
Uses LLM?:    deterministic
Side effects: HTTP to job boards via SafeFetcher (fixtures in demo), robots.txt, ETag cache
Config keys:  search.yaml sources, titles, locations, max_age_days; MAX_JOBS_PER_RUN
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from careergraph.domain.models import AnalyzedJob, JobPosting
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.security.fetcher import FetchError
from careergraph.sources.jobs.factory import build_sources
from careergraph.sources.jobs.filters import age_ok, dedupe, location_ok, title_ok

log = logging.getLogger(__name__)


def find_jobs(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Fetch, filter, dedupe and split postings into cached vs to-analyse."""
    ctx = runtime.context
    cfg = ctx.cfg.search
    sources, warnings = build_sources(cfg, ctx.fetcher)
    fetched: list[JobPosting] = []
    errors: dict[str, str] = {}
    for src in sources:
        try:
            fetched += src.fetch()
        except (FetchError, ValueError, KeyError, TypeError) as exc:
            errors[src.name] = f"{type(exc).__name__}: {exc}"
            log.warning("source failed; continuing", extra={"source": src.name, "error": str(exc)})
    by_title = [p for p in fetched if title_ok(p, cfg)]
    by_location = [p for p in by_title if location_ok(p, cfg)]
    fresh = [p for p in by_location if age_ok(p, ctx.today, cfg.max_age_days)]
    unique, duplicates = dedupe(fresh)
    cached: dict[str, AnalyzedJob] = {}
    new: list[JobPosting] = []
    for p in unique:
        hit = ctx.repo.cached_analysis(p.content_hash)
        if hit is not None:
            cached[p.id] = hit.model_copy(update={"posting": p})
        else:
            new.append(p)
    new.sort(key=lambda p: p.posted_at or date.min, reverse=True)
    cap = ctx.settings.max_jobs_per_run
    funnel = {
        "sources": len(sources),
        "source_errors": errors,
        "warnings": warnings,
        "fetched": len(fetched),
        "after_title": len(by_title),
        "after_location": len(by_location),
        "after_age": len(fresh),
        "duplicates": duplicates,
        "cached": len(cached),
        "new": len(new),
        "skipped_over_cap": max(len(new) - cap, 0),
    }
    log.info("jobs found", extra={k: v for k, v in funnel.items() if isinstance(v, int)})
    return {"to_analyse": new[:cap], "analyses": cached, "funnel": funnel}
