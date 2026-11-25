"""SSRF-safe fetcher: scheme, allowlist, address checks, redirects, caps, robots, cache."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from careergraph.security.fetcher import (
    BlockedURL,
    FetchError,
    FetchPolicy,
    SafeFetcher,
    is_public_address,
)

PUBLIC = "93.184.215.14"


def fetcher(
    handler, tmp_path: Path | None = None, resolve: dict[str, str] | None = None, **policy: object
) -> SafeFetcher:
    pol = FetchPolicy(allowed_domains={"good.example", "other.example"}, min_interval=0, **policy)  # type: ignore[arg-type]
    table = resolve or {}
    return SafeFetcher(
        pol, tmp_path, httpx.MockTransport(handler), resolver=lambda h: [table.get(h, PUBLIC)]
    )


def ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, text="hello", headers={"etag": '"v1"'})


@pytest.mark.parametrize(
    "url",
    [
        "http://good.example/x",
        "ftp://good.example/x",
        "https://evil.example/x",
        "https://user:pw@good.example/x",
        "https://good.example:8443/x",
        "https://127.0.0.1/x",
        "https://[::1]/x",
        "https://good.example.evil.example/x",
    ],
)
def test_policy_blocks_bad_urls(url: str) -> None:
    with pytest.raises(BlockedURL):
        fetcher(ok).get(url)


@pytest.mark.parametrize(
    "ip", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1", "100.64.0.1", "::1",
           "fd00::1", "::ffff:127.0.0.1", "224.0.0.1", "0.0.0.0"]
)  # fmt: skip
def test_private_resolution_is_blocked(ip: str) -> None:
    assert not is_public_address(ip)
    f = fetcher(ok, resolve={"good.example": ip})
    with pytest.raises(BlockedURL, match="non-public"):
        f.get("https://good.example/x")


def test_subdomains_allowed_and_ua_is_honest() -> None:
    seen: dict[str, str] = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen["ua"] = req.headers["user-agent"]
        return ok(req)

    f = fetcher(h, contact="me@example.com")
    assert f.get("https://jobs.good.example/x").text() == "hello"
    assert seen["ua"].startswith("CareerGraph/") and "me@example.com" in seen["ua"]


def test_redirect_is_revalidated() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.host == "good.example":
            return httpx.Response(
                302, headers={"location": "https://169.254.169.254/latest/meta-data"}
            )
        return httpx.Response(200, text="secret")

    with pytest.raises(BlockedURL):
        fetcher(h).get("https://good.example/start")


def test_redirect_to_allowed_host_is_followed() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.host == "good.example":
            return httpx.Response(301, headers={"location": "https://other.example/final"})
        return httpx.Response(200, text="final")

    resp = fetcher(h).get("https://good.example/start")
    assert resp.text() == "final" and resp.url == "https://other.example/final"


def test_redirect_loop_is_capped() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(FetchError, match="too many redirects"):
        fetcher(h).get("https://good.example/start")


def test_size_cap_declared_and_streamed() -> None:
    def declared(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"x" * 50, headers={"content-length": "999999"})

    with pytest.raises(FetchError, match="too large"):
        fetcher(declared, max_bytes=20_000).get("https://good.example/a")

    def streamed(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=iter([b"y" * 15_000, b"y" * 15_000]))

    with pytest.raises(FetchError, match="exceeds"):
        fetcher(streamed, max_bytes=20_000).get("https://good.example/b")


def test_robots_disallow_and_5xx() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            if req.url.host == "good.example":
                return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
            return httpx.Response(503)
        return httpx.Response(200, text="page")

    f = fetcher(h)
    assert f.get("https://good.example/public").text() == "page"
    with pytest.raises(FetchError, match="robots"):
        f.get("https://good.example/private/x")
    with pytest.raises(FetchError, match="robots"):
        f.get("https://other.example/anything")


def test_rate_limit_sleeps_between_requests_to_same_host() -> None:
    slept: list[float] = []
    now = [100.0]
    pol = FetchPolicy(allowed_domains={"good.example"}, min_interval=2.0, respect_robots=False)
    f = SafeFetcher(
        pol, None, httpx.MockTransport(ok), lambda h: [PUBLIC], slept.append, lambda: now[0]
    )
    f.get("https://good.example/1")
    f.get("https://good.example/2")
    assert slept == [2.0]


def test_etag_revalidation_uses_cache(tmp_path: Path) -> None:
    calls: list[str | None] = []

    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls.append(req.headers.get("if-none-match"))
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, text="body", headers={"etag": '"v1"'})

    f = fetcher(h, tmp_path)
    first, second = f.get("https://good.example/c"), f.get("https://good.example/c")
    assert (first.from_cache, second.from_cache) == (False, True)
    assert second.text() == "body" and calls == [None, '"v1"']
