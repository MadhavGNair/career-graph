"""Job source protocol and shared helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol

from careergraph.domain.models import JobPosting, RemoteType
from careergraph.sources.documents import sha256


class JobSource(Protocol):
    """Anything that can list postings."""

    name: str

    def fetch(self) -> list[JobPosting]:
        """Return all current postings from the source."""
        ...


def parse_date(value: str | int | float | None) -> date | None:
    """ISO string or epoch milliseconds -> date (None if missing/unparseable)."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value / 1000, UTC).date()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, OverflowError, OSError):
        return None


def remote_from_text(*texts: str) -> RemoteType:
    """Infer remote type from location/workplace strings."""
    t = " ".join(texts).lower()
    if "hybrid" in t:
        return "hybrid"
    if "remote" in t:
        return "remote"
    if "on-site" in t or "onsite" in t or "office" in t:
        return "onsite"
    return "unknown"


def content_hash(title: str, location: str, description: str) -> str:
    """Hash of the analysable content; unchanged postings are never re-analysed."""
    return sha256(f"{title}\n{location}\n{description}")


def build(**kw: object) -> JobPosting:
    """Construct a JobPosting and fill its content hash."""
    p = JobPosting.model_validate(kw)
    return p.model_copy(update={"content_hash": content_hash(p.title, p.location, p.description)})
