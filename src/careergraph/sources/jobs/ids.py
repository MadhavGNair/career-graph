"""Stable posting ids: readable, source-prefixed, unique per board."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse


def greenhouse_id(slug: str, native: int | str) -> str:
    """gh-<board>-<numeric id>."""
    return f"gh-{slug}-{native}"


def lever_id(slug: str, native: str) -> str:
    """lv-<site>-<first 8 chars of the posting UUID>."""
    return f"lv-{slug}-{native[:8]}"


def ashby_id(slug: str, native: str) -> str:
    """ab-<board>-<first 8 chars of the job UUID>."""
    return f"ab-{slug}-{native[:8]}"


def rss_id(feed_url: str, guid: str) -> str:
    """rss-<feed host>-<hash of the item guid>."""
    host = (urlparse(feed_url).hostname or "feed").replace(".", "-")
    return f"rss-{host}-{hashlib.sha1(guid.encode(), usedforsecurity=False).hexdigest()[:8]}"
