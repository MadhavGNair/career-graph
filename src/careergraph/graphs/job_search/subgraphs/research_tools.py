"""Tools for the research loop. Both go through SafeFetcher; fetch_page is limited to the
company's own domain(s) plus the fetcher allowlist, and flags injected instructions."""

from __future__ import annotations

import json
from typing import cast
from urllib.parse import urlparse

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from careergraph.security.fetcher import FetchError
from careergraph.security.injection import scan
from careergraph.service.wiring import Services
from careergraph.sources.html import html_title, html_to_text

MAX_PAGE_CHARS = 4000


@tool
def web_search(query: str, runtime: ToolRuntime) -> str:
    """Search the web. Returns a JSON list of {title, url, snippet}."""
    try:
        results = cast(Services, runtime.context).search.search(query, k=5)
    except FetchError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps([r.model_dump() for r in results])


@tool
def fetch_page(url: str, runtime: ToolRuntime) -> str:
    """Fetch one page from an allowed company domain. Returns JSON {url, title, text}."""
    host = (urlparse(url).hostname or "").lower()
    allowed = [d.lower() for d in runtime.state.get("allowed_domains", [])]
    if not any(host == d or host.endswith("." + d) for d in allowed):
        return json.dumps({"url": url, "error": f"domain not allowed for research: {host}"})
    try:
        body = cast(Services, runtime.context).fetcher.get(url).text()
    except FetchError as exc:
        return json.dumps({"url": url, "error": str(exc)})
    text = html_to_text(body)[:MAX_PAGE_CHARS]
    report = scan(text)
    return json.dumps(
        {"url": url, "title": html_title(body), "text": text, "injection_flag": report.flagged}
    )


RESEARCH_TOOLS = [web_search, fetch_page]
