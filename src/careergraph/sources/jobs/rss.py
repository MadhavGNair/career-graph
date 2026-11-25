"""RSS/Atom job feeds via feedparser (bytes fetched through SafeFetcher, never by feedparser)."""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime
from typing import Any

import feedparser

from careergraph.domain.models import JobPosting
from careergraph.security.fetcher import SafeFetcher
from careergraph.sources.html import html_to_text
from careergraph.sources.jobs.base import build, remote_from_text
from careergraph.sources.jobs.ids import rss_id


def _date(entry: Any) -> date | None:
    parsed: time.struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*parsed[:6], tzinfo=UTC).date() if parsed else None


def parse_rss(body: bytes, feed_url: str, company: str) -> list[JobPosting]:
    """Normalise feed entries."""
    feed = feedparser.parse(body)
    default_company = company or feed.feed.get("title", "")
    out: list[JobPosting] = []
    for entry in feed.entries:
        text = html_to_text(entry.get("summary", "") or entry.get("description", ""))
        loc_match = re.search(r"^Location:\s*(.+)$", text, re.M)
        tags = entry.get("tags") or []
        location = (
            loc_match.group(1).strip() if loc_match else (tags[0].get("term", "") if tags else "")
        )
        guid = entry.get("id") or entry.get("link", "")
        out.append(
            build(
                id=rss_id(feed_url, guid),
                source="rss",
                company=default_company,
                title=entry.get("title", "").strip(),
                location=location,
                remote=remote_from_text(location),
                url=entry.get("link", ""),
                description=text,
                posted_at=_date(entry),
            )
        )
    return out


class RssSource:
    """One feed."""

    def __init__(self, fetcher: SafeFetcher, url: str, company: str) -> None:
        self.fetcher, self.url, self.company = fetcher, url, company
        self.name = f"rss:{url}"

    def fetch(self) -> list[JobPosting]:
        """Fetch and parse the feed."""
        return parse_rss(self.fetcher.get(self.url).body, self.url, self.company)
