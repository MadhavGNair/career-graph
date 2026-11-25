"""Greenhouse Job Board API: GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
(no auth; `content` is entity-escaped HTML; verified against docs.greenhouse.io 2026-11-22)."""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import JobPosting
from careergraph.security.fetcher import SafeFetcher
from careergraph.sources.html import html_to_text
from careergraph.sources.jobs.base import build, parse_date, remote_from_text
from careergraph.sources.jobs.ids import greenhouse_id


def parse_greenhouse(payload: dict[str, Any], slug: str, company: str) -> list[JobPosting]:
    """Normalise a Greenhouse jobs payload."""
    out: list[JobPosting] = []
    for job in payload.get("jobs", []):
        location = (job.get("location") or {}).get("name", "")
        out.append(
            build(
                id=greenhouse_id(slug, job["id"]),
                source="greenhouse",
                company=company or job.get("company_name") or slug,
                title=job.get("title", "").strip(),
                location=location,
                remote=remote_from_text(location),
                url=job.get("absolute_url", ""),
                description=html_to_text(job.get("content") or "", unescape_first=True),
                posted_at=parse_date(job.get("first_published") or job.get("updated_at")),
            )
        )
    return out


class GreenhouseSource:
    """One Greenhouse board."""

    def __init__(self, fetcher: SafeFetcher, slug: str, company: str) -> None:
        self.fetcher, self.slug, self.company = fetcher, slug, company
        self.name = f"greenhouse:{slug}"

    def fetch(self) -> list[JobPosting]:
        """Fetch and parse the board."""
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.slug}/jobs?content=true"
        return parse_greenhouse(self.fetcher.get(url).json(), self.slug, self.company)
