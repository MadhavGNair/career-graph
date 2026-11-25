"""Build job sources from search.yaml. Placeholders and disabled entries are skipped."""

from __future__ import annotations

from urllib.parse import urlparse

from careergraph.config import SearchConfig
from careergraph.security.fetcher import SafeFetcher
from careergraph.sources.jobs.ashby import AshbySource
from careergraph.sources.jobs.base import JobSource
from careergraph.sources.jobs.greenhouse import GreenhouseSource
from careergraph.sources.jobs.lever import LeverSource
from careergraph.sources.jobs.rss import RssSource


def build_sources(cfg: SearchConfig, fetcher: SafeFetcher) -> tuple[list[JobSource], list[str]]:
    """Return (sources, warnings). RSS hosts are added to the fetch allowlist."""
    sources: list[JobSource] = []
    warnings: list[str] = []
    for spec in cfg.sources:
        if not spec.enabled:
            continue
        if spec.is_placeholder:
            warnings.append(f"skipped placeholder source {spec.type}: {spec.slug or spec.url}")
            continue
        if spec.type == "greenhouse":
            sources.append(GreenhouseSource(fetcher, spec.slug, spec.company))
        elif spec.type == "lever":
            sources.append(LeverSource(fetcher, spec.slug, spec.company, spec.region))
        elif spec.type == "ashby":
            sources.append(AshbySource(fetcher, spec.slug, spec.company))
        else:
            host = urlparse(spec.url).hostname
            if host:
                fetcher.allow([host])
            sources.append(RssSource(fetcher, spec.url, spec.company))
    return sources, warnings
