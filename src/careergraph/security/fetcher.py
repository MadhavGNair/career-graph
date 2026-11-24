"""SSRF-safe, polite, cached HTTP client used for every outbound request.

Guarantees for each request (including every redirect hop):
- https only, no credentials in the URL, default port only;
- host must be on the allowlist (exact or subdomain);
- every resolved address must be globally routable (blocks private, loopback, link-local,
  multicast, reserved, CGNAT, documentation ranges and IPv6 equivalents);
- redirects are followed manually (max 5) and each Location is re-validated;
- response size and time are capped;
- robots.txt is respected (RFC 9309: 4xx = allow all, 5xx/unreachable = disallow all);
- at most one request per host per HTTP_MIN_INTERVAL_SECONDS;
- an honest User-Agent; ETag / Last-Modified revalidation from a disk cache.

Residual risk: the address is validated before httpx connects and httpx resolves again, so a
DNS-rebinding attacker controlling an allow-listed domain could race the check. The allowlist
(public APIs and companies you configure) keeps that surface small; see docs/security.md.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import socket
import threading
import time
import urllib.robotparser
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from careergraph import __version__

Resolver = Callable[[str], list[str]]
DEFAULT_ALLOWED = (
    "boards-api.greenhouse.io",
    "api.lever.co",
    "api.eu.lever.co",
    "api.ashbyhq.com",
    "api.github.com",
    "api.tavily.com",
    "api.search.brave.com",
)
MAX_REDIRECTS = 5


class FetchError(RuntimeError):
    """The request failed (network, status, size, robots)."""


class BlockedURL(FetchError):
    """The URL violates the fetch policy (scheme, host, address, allowlist)."""


def system_resolver(host: str) -> list[str]:
    """Resolve a host to its IP addresses using the OS resolver."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"cannot resolve {host}: {exc}") from None
    return sorted({str(info[4][0]) for info in infos})


def is_public_address(ip: str) -> bool:
    """True only for globally routable unicast addresses."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not (addr.is_multicast or addr.is_reserved or addr.is_loopback)


@dataclass
class FetchResponse:
    """A fully read response."""

    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    from_cache: bool = False

    def text(self) -> str:
        """Decode the body as UTF-8 (replacing bad bytes)."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse the body as JSON."""
        return json.loads(self.body)


@dataclass
class FetchPolicy:
    """Limits applied to every request."""

    allowed_domains: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED))
    max_bytes: int = 3_000_000
    timeout: float = 20.0
    min_interval: float = 1.0
    contact: str = ""
    respect_robots: bool = True

    @property
    def user_agent(self) -> str:
        """Honest User-Agent identifying the tool (and optionally a contact)."""
        suffix = f"; +{self.contact}" if self.contact else ""
        return f"CareerGraph/{__version__} (personal job-search tool{suffix})"


class SafeFetcher:
    """The only HTTP client in CareerGraph. Thread-safe."""

    def __init__(
        self,
        policy: FetchPolicy,
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._cache_dir = cache_dir / "http" if cache_dir else None
        self._client = httpx.Client(
            transport=transport, timeout=policy.timeout, follow_redirects=False
        )
        self._resolver, self._sleep, self._clock = resolver, sleep, clock
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | bool] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ policy
    def allow(self, domains: Iterable[str]) -> None:
        """Add domains (e.g. configured company sites, RSS hosts) to the allowlist."""
        for d in domains:
            d = d.strip().lower().lstrip(".")
            if d:
                self.policy.allowed_domains.add(d)

    def _host_allowed(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        return any(host == d or host.endswith("." + d) for d in self.policy.allowed_domains)

    def check_url(self, url: str) -> str:
        """Validate a URL against the policy; return its hostname or raise BlockedURL."""
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise BlockedURL(f"only https is allowed: {url}")
        if parsed.username or parsed.password:
            raise BlockedURL("credentials in URLs are not allowed")
        host = parsed.hostname
        if not host:
            raise BlockedURL(f"no host in {url}")
        if parsed.port not in (None, 443):
            raise BlockedURL(f"non-default port in {url}")
        try:
            ipaddress.ip_address(host)
            raise BlockedURL(f"IP-literal hosts are not allowed: {host}")
        except ValueError:
            pass
        if not self._host_allowed(host):
            raise BlockedURL(f"host not on the allowlist: {host}")
        addrs = self._resolver(host)
        if not addrs:
            raise BlockedURL(f"{host} did not resolve")
        bad = [a for a in addrs if not is_public_address(a)]
        if bad:
            raise BlockedURL(f"{host} resolves to non-public address {bad[0]}")
        return host

    # ------------------------------------------------------------------ public API
    def get(
        self, url: str, headers: dict[str, str] | None = None, use_cache: bool = True
    ) -> FetchResponse:
        """GET with policy checks, robots, rate limit, redirects and ETag cache."""
        if self.policy.respect_robots and not self._robots_allowed(url):
            raise FetchError(f"robots.txt disallows {url}")
        cached = self._cache_load(url) if use_cache else None
        hdrs = dict(headers or {})
        if cached:
            if cached.get("etag"):
                hdrs["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                hdrs["If-Modified-Since"] = cached["last_modified"]
        resp = self._request("GET", url, hdrs, None)
        if resp.status == 304 and cached:
            return FetchResponse(
                url, 200, cached["headers"], base64.b64decode(cached["body"]), True
            )
        if resp.status >= 400:
            raise FetchError(f"HTTP {resp.status} for {url}")
        if use_cache:
            self._cache_store(url, resp)
        return resp

    def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> FetchResponse:
        """POST JSON (search APIs). Not cached, no robots check (API endpoints)."""
        resp = self._request("POST", url, dict(headers or {}), payload)
        if resp.status >= 400:
            raise FetchError(f"HTTP {resp.status} for {url}")
        return resp

    # ------------------------------------------------------------------ internals
    def _throttle(self, host: str) -> None:
        with self._lock:
            now = self._clock()
            wait = self._last.get(host, -1e9) + self.policy.min_interval - now
            self._last[host] = now + max(wait, 0)
        if wait > 0:
            self._sleep(wait)

    def _request(
        self, method: str, url: str, headers: dict[str, str], payload: Any
    ) -> FetchResponse:
        headers = {**headers, "User-Agent": self.policy.user_agent}
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host = self.check_url(current)
            self._throttle(host)
            try:
                with self._client.stream(method, current, headers=headers, json=payload) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        location = r.headers.get("location")
                        if not location:
                            raise FetchError(f"redirect without Location from {current}")
                        current = urljoin(current, location)
                        if r.status_code == 303:
                            method, payload = "GET", None
                        continue
                    declared = int(r.headers.get("content-length") or 0)
                    if declared > self.policy.max_bytes:
                        raise FetchError(f"response too large ({declared} bytes) from {current}")
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.policy.max_bytes:
                            raise FetchError(f"response exceeds {self.policy.max_bytes} bytes")
                    return FetchResponse(current, r.status_code, dict(r.headers), bytes(body))
            except httpx.HTTPError as exc:
                raise FetchError(f"{type(exc).__name__} for {current}: {exc}") from None
        raise FetchError(f"too many redirects from {url}")

    def _robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"https://{parsed.hostname}"
        with self._lock:
            known = self._robots.get(root)
        if known is None:
            try:
                resp = self._request("GET", root + "/robots.txt", {}, None)
                if resp.status >= 500:
                    known = False
                elif resp.status >= 400:
                    known = True
                else:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(resp.text().splitlines())
                    known = parser
            except BlockedURL:
                raise
            except FetchError:
                known = False
            with self._lock:
                self._robots[root] = known
        if isinstance(known, bool):
            return known
        return known.can_fetch(self.policy.user_agent, url)

    def _cache_path(self, url: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _cache_load(self, url: str) -> dict[str, Any] | None:
        path = self._cache_path(url)
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _cache_store(self, url: str, resp: FetchResponse) -> None:
        path = self._cache_path(url)
        etag, lm = resp.headers.get("etag"), resp.headers.get("last-modified")
        if path is None or not (etag or lm):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "etag")}
        record = {"etag": etag, "last_modified": lm, "headers": keep,
                  "body": base64.b64encode(resp.body).decode()}  # fmt: skip
        path.write_text(json.dumps(record))
