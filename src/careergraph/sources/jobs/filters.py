"""Deterministic posting filters: title, location/remote, age, near-duplicate removal."""

from __future__ import annotations

import re
from datetime import date

from careergraph.config import SearchConfig
from careergraph.domain.models import JobPosting

NEAR_DUP_JACCARD = 0.85


def title_ok(p: JobPosting, cfg: SearchConfig) -> bool:
    """Include/exclude keywords on the title (case-insensitive substring)."""
    t = p.title.lower()
    if any(x.lower() in t for x in cfg.titles.exclude):
        return False
    return not cfg.titles.include or any(x.lower() in t for x in cfg.titles.include)


def location_ok(p: JobPosting, cfg: SearchConfig) -> bool:
    """Location keywords and remote preference (required/excluded are hard filters)."""
    pref = cfg.locations.remote
    if pref == "required" and p.remote != "remote":
        return False
    if pref == "excluded" and p.remote == "remote":
        return False
    loc = p.location.lower()
    return not cfg.locations.include or any(x.lower() in loc for x in cfg.locations.include)


def age_ok(p: JobPosting, today: date, max_age_days: int) -> bool:
    """Undated postings are kept; dated ones must be recent enough."""
    return p.posted_at is None or (today - p.posted_at).days <= max_age_days


def _shingles(text: str, k: int = 5) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i : i + k]) for i in range(max(len(words) - k + 1, 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    """Set similarity."""
    return len(a & b) / len(a | b) if a or b else 1.0


def dedupe(postings: list[JobPosting]) -> tuple[list[JobPosting], dict[str, str]]:
    """Drop near-duplicates within a company, keeping the newest. Returns (kept, dropped->kept)."""
    ordered = sorted(postings, key=lambda p: p.posted_at or date.min, reverse=True)
    kept: list[tuple[JobPosting, set[str]]] = []
    dropped: dict[str, str] = {}
    for p in ordered:
        sh = _shingles(p.description)
        dup = next(
            (
                k
                for k, ksh in kept
                if k.company.lower() == p.company.lower() and jaccard(sh, ksh) >= NEAR_DUP_JACCARD
            ),
            None,
        )
        if dup is None:
            kept.append((p, sh))
        else:
            dropped[p.id] = dup.id
    return [p for p, _ in kept], dropped
