"""Pluggable web search for company research.

- site  (no key): returns the company's own pages listed in search.yaml `companies`.
- tavily: POST https://api.tavily.com/search, `Authorization: Bearer <key>`;
  results[].title/url/content.
  Free tier at time of writing: 1,000 credits/month (tavily.com/pricing, checked 2026-11-22).
- brave: GET https://api.search.brave.com/res/v1/web/search?q=..., `X-Subscription-Token`;
  web.results[].title/url/description. No free plan at time of writing ($5 monthly credit,
  card required; brave.com/search/api, checked 2026-11-22).
All requests go through SafeFetcher. Check current pricing before relying on any tier.
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import quote_plus

from careergraph.config import SearchConfig
from careergraph.domain.models import SearchResult
from careergraph.security.fetcher import SafeFetcher


class SearchProvider(Protocol):
    """Returns ranked results for a query."""

    name: str

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Search the web (or a restricted corpus)."""
        ...


class SiteProvider:
    """No-key fallback: only the company's own configured pages."""

    name = "site"

    def __init__(self, cfg: SearchConfig) -> None:
        self.cfg = cfg

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Return configured pages of companies named in the query."""
        q = query.lower()
        hits = [
            SearchResult(title=f"{name}: {url.rsplit('/', 1)[-1] or 'home'}", url=url)
            for name, info in self.cfg.companies.items()
            if name.lower() in q
            for url in info.pages
        ]
        return hits[:k]


class TavilyProvider:
    """Tavily search API (keyed)."""

    name = "tavily"

    def __init__(self, fetcher: SafeFetcher, key: str) -> None:
        self.fetcher, self.key = fetcher, key

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Basic-depth search (1 credit per call at time of writing)."""
        resp = self.fetcher.post_json(
            "https://api.tavily.com/search",
            {"query": query, "max_results": k, "search_depth": "basic"},
            headers={"Authorization": f"Bearer {self.key}"},
        )
        return [
            SearchResult(
                title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", "")
            )
            for r in resp.json().get("results", [])[:k]
        ]


class BraveProvider:
    """Brave Search API (keyed)."""

    name = "brave"

    def __init__(self, fetcher: SafeFetcher, key: str) -> None:
        self.fetcher, self.key = fetcher, key

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Web search, first page."""
        url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={k}"
        resp = self.fetcher.get(url, headers={"X-Subscription-Token": self.key}, use_cache=False)
        results = (resp.json().get("web") or {}).get("results", [])
        return [
            SearchResult(
                title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("description", "")
            )
            for r in results[:k]
        ]
