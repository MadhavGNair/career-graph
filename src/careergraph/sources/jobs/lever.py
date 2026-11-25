"""Lever Postings API: GET https://api.lever.co/v0/postings/{site}?mode=json (EU:
api.eu.lever.co). Verified against github.com/lever/postings-api 2026-11-22. `createdAt`
(epoch ms) is not in the README but present in live data, so it is parsed tolerantly."""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import JobPosting, RemoteType
from careergraph.security.fetcher import SafeFetcher
from careergraph.sources.html import html_to_text
from careergraph.sources.jobs.base import build, parse_date, remote_from_text
from careergraph.sources.jobs.ids import lever_id

_WORKPLACE: dict[str, RemoteType] = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite"}


def _salary(item: dict[str, Any]) -> str:
    rng = item.get("salaryRange") or {}
    if rng.get("min") and rng.get("max"):
        return f"{rng.get('currency', '')} {int(rng['min']):,} - {int(rng['max']):,}".strip()
    return item.get("salaryDescriptionPlain") or ""


def parse_lever(payload: list[dict[str, Any]], slug: str, company: str) -> list[JobPosting]:
    """Normalise a Lever postings array."""
    out: list[JobPosting] = []
    for item in payload:
        cats = item.get("categories") or {}
        location = cats.get("location", "")
        body = item.get("descriptionPlain") or "\n".join(
            x for x in (item.get("openingPlain"), item.get("descriptionBodyPlain")) if x
        )
        sections = [
            f"{lst.get('text', '')}:\n{html_to_text(lst.get('content', ''))}"
            for lst in item.get("lists", [])
        ]
        salary = _salary(item)
        text = "\n\n".join(
            x for x in [body, *sections, item.get("additionalPlain", ""), salary] if x
        )
        wp = _WORKPLACE.get(str(item.get("workplaceType", "")).lower(), "unknown")
        out.append(
            build(
                id=lever_id(slug, item["id"]),
                source="lever",
                company=company or slug,
                title=item.get("text", "").strip(),
                location=location,
                remote=wp if wp != "unknown" else remote_from_text(location),
                url=item.get("hostedUrl", ""),
                description=text,
                posted_at=parse_date(item.get("createdAt")),
                salary_text=salary,
            )
        )
    return out


class LeverSource:
    """One Lever site."""

    def __init__(self, fetcher: SafeFetcher, slug: str, company: str, region: str) -> None:
        self.fetcher, self.slug, self.company = fetcher, slug, company
        self.host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
        self.name = f"lever:{slug}"

    def fetch(self) -> list[JobPosting]:
        """Fetch and parse the site's postings."""
        url = f"https://{self.host}/v0/postings/{self.slug}?mode=json"
        return parse_lever(self.fetcher.get(url).json(), self.slug, self.company)
