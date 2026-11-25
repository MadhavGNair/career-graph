"""Ashby public job posting API: GET https://api.ashbyhq.com/posting-api/job-board/{name}
?includeCompensation=true (no auth). Verified against developers.ashbyhq.com 2026-11-22;
`id` and per-job `compensation` are present in live data although the docs omit/misplace them."""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import JobPosting, RemoteType
from careergraph.security.fetcher import SafeFetcher
from careergraph.sources.html import html_to_text
from careergraph.sources.jobs.base import build, parse_date, remote_from_text
from careergraph.sources.jobs.ids import ashby_id

_WORKPLACE: dict[str, RemoteType] = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite"}


def _salary(job: dict[str, Any]) -> str:
    comp = job.get("compensation") or {}
    for c in comp.get("summaryComponents") or []:
        if c.get("compensationType") == "Salary" and c.get("minValue") and c.get("maxValue"):
            lo, hi = int(c["minValue"]), int(c["maxValue"])
            return f"{c.get('currencyCode', '')} {lo:,} - {hi:,}".strip()
    return comp.get("compensationTierSummary") or ""


def parse_ashby(payload: dict[str, Any], slug: str, company: str) -> list[JobPosting]:
    """Normalise an Ashby job-board payload."""
    out: list[JobPosting] = []
    for job in payload.get("jobs", []):
        if job.get("isListed") is False:
            continue
        location = job.get("location", "")
        text = job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml") or "")
        salary = _salary(job)
        wp = _WORKPLACE.get(str(job.get("workplaceType", "")).lower(), "unknown")
        native = job.get("id") or job.get("jobUrl", "").rstrip("/").split("/")[-1]
        out.append(
            build(
                id=ashby_id(slug, native),
                source="ashby",
                company=company or slug,
                title=job.get("title", "").strip(),
                location=location,
                remote=wp if wp != "unknown" else remote_from_text(location),
                url=job.get("jobUrl", ""),
                description="\n\n".join(x for x in (text, salary) if x),
                posted_at=parse_date(job.get("publishedAt")),
                salary_text=salary,
            )
        )
    return out


class AshbySource:
    """One Ashby job board."""

    def __init__(self, fetcher: SafeFetcher, slug: str, company: str) -> None:
        self.fetcher, self.slug, self.company = fetcher, slug, company
        self.name = f"ashby:{slug}"

    def fetch(self) -> list[JobPosting]:
        """Fetch and parse the board."""
        url = f"https://api.ashbyhq.com/posting-api/job-board/{self.slug}?includeCompensation=true"
        return parse_ashby(self.fetcher.get(url).json(), self.slug, self.company)
