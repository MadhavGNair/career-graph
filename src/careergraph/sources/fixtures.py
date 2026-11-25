"""Demo-mode HTTP transport: serves data/demo files for the exact URLs live adapters request.

The live adapters, SafeFetcher checks, robots handling and ETag caching all run unchanged;
only the bytes come from disk. No sockets are opened.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import yaml

from careergraph.config import DEMO_DIR

# Fixture hosts are fictional (.example); the demo resolver returns this public address so the
# SSRF address check passes. MockTransport never connects to it.
DEMO_ADDRESS = "93.184.215.14"


def demo_resolver(host: str) -> list[str]:
    """Resolve every host to a fixed public address (demo only)."""
    return [DEMO_ADDRESS]


class FixtureTransport(httpx.MockTransport):
    """httpx transport backed by data/demo."""

    def __init__(self, root: Path = DEMO_DIR) -> None:
        self.root = root
        self.requests: list[str] = []
        super().__init__(self._handle)

    def _file(self, path: Path, request: httpx.Request, ctype: str) -> httpx.Response:
        if not path.is_file():
            return httpx.Response(404, text="not found")
        body = path.read_bytes()
        etag = '"' + hashlib.sha1(body, usedforsecurity=False).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, content=body, headers={"content-type": ctype, "etag": etag})

    def _json(self, data: object) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps(data).encode(), headers={"content-type": "application/json"}
        )

    def _search_hits(self, query: str) -> list[dict[str, str]]:
        index = yaml.safe_load((self.root / "web" / "search_index.yaml").read_text()) or {}
        q = query.lower()
        return [hit for company, hits in index.items() if company.lower() in q for hit in hits]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        host, path = url.hostname or "", url.path
        self.requests.append(f"{request.method} {request.url}")
        if host == "boards-api.greenhouse.io" and (
            m := re.fullmatch(r"/v1/boards/([^/]+)/jobs", path)
        ):
            return self._file(
                self.root / "postings/greenhouse" / f"{m.group(1)}.json",
                request,
                "application/json",
            )
        if host in ("api.lever.co", "api.eu.lever.co") and (
            m := re.fullmatch(r"/v0/postings/([^/]+)", path)
        ):
            return self._file(
                self.root / "postings/lever" / f"{m.group(1)}.json", request, "application/json"
            )
        if host == "api.ashbyhq.com" and (
            m := re.fullmatch(r"/posting-api/job-board/([^/]+)", path)
        ):
            return self._file(
                self.root / "postings/ashby" / f"{m.group(1)}.json", request, "application/json"
            )
        if host == "api.github.com":
            return self._github(path, request)
        if host == "api.tavily.com" and path == "/search":
            query = json.loads(request.content or b"{}").get("query", "")
            hits = self._search_hits(query)
            return self._json(
                {
                    "query": query,
                    "results": [
                        {
                            "title": h["title"],
                            "url": h["url"],
                            "content": h["snippet"],
                            "score": 0.9,
                        }
                        for h in hits
                    ],
                }
            )
        if host == "api.search.brave.com":
            query = parse_qs(url.query).get("q", [""])[0]
            hits = self._search_hits(query)
            return self._json(
                {
                    "web": {
                        "results": [
                            {"title": h["title"], "url": h["url"], "description": h["snippet"]}
                            for h in hits
                        ]
                    }
                }
            )
        if path.endswith((".rss", ".xml")):
            return self._file(
                self.root / "postings/rss" / f"{host}.xml", request, "application/rss+xml"
            )
        if path == "/robots.txt":
            return self._file(self.root / "web" / host / "robots.txt", request, "text/plain")
        page = path.strip("/") or "index"
        return self._file(self.root / "web" / host / f"{page}.html", request, "text/html")

    def _github(self, path: str, request: httpx.Request) -> httpx.Response:
        if path == "/robots.txt":
            return httpx.Response(404)
        m = re.fullmatch(r"/users/([^/]+)/repos", path) or re.fullmatch(
            r"/repos/([^/]+)/([^/]+)/(languages|readme)", path
        )
        if not m:
            return httpx.Response(404)
        fixture = self.root / "github" / f"{m.group(1)}.json"
        if not fixture.is_file():
            return httpx.Response(404)
        data = json.loads(fixture.read_text())
        if m.re.pattern.startswith("/users"):
            return self._json(data["repos"])
        repo, what = m.group(2), m.group(3)
        if what == "languages":
            return self._json(data["languages"].get(repo, {}))
        readme = data["readmes"].get(repo)
        return httpx.Response(200, text=readme) if readme is not None else httpx.Response(404)
