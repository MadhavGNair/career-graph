"""Build the shortlist interrupt payload and validate the human's resume value."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from careergraph.domain.models import AnalyzedJob, MatchResult, ReasonTag, ShortlistDecision

HELP = (
    "For each job choose approve, reject or defer. Optional reason_tags explain a rejection "
    "and teach the matcher (stored as preferences). Deferred jobs can reappear next run."
)


def shortlist_items(
    matches: list[MatchResult], shortlist: list[str], analyses: dict[str, AnalyzedJob]
) -> list[dict[str, Any]]:
    """JSON-safe rows for the UI/CLI, in rank order."""
    by_id = {m.job_id: m for m in matches}
    rows: list[dict[str, Any]] = []
    for rank, job_id in enumerate(shortlist, start=1):
        m, job = by_id[job_id], analyses[job_id]
        rows.append(
            {
                "job_id": job_id,
                "rank": rank,
                "title": job.posting.title,
                "company": job.posting.company,
                "location": job.posting.location,
                "remote": job.analysis.remote,
                "url": job.posting.url,
                "posted_at": job.posting.posted_at.isoformat() if job.posting.posted_at else "",
                "score": m.score,
                "breakdown": [c.model_dump() for c in m.breakdown],
                "preference_adjustment": m.preference_adjustment,
                "matched": [s.model_dump() for s in m.skills_with("matched")],
                "partial": [s.model_dump() for s in m.skills_with("partial")],
                "missing": [s.model_dump() for s in m.skills_with("missing")],
                "rationale": m.rationale,
                "summary": job.analysis.summary,
                "red_flags": job.analysis.red_flags,
                "salary": job.analysis.salary.model_dump() if job.analysis.salary else None,
                "injection_flag": job.injection_flag,
                "injection_matches": job.injection.matches,
            }
        )
    return rows


def parse_decisions(raw: Any, valid_ids: list[str]) -> list[ShortlistDecision]:
    """Validate a resume value. Unknown ids and malformed items are dropped; jobs without a
    decision are deferred, so a partial answer never loses data."""
    items = raw.get("decisions", []) if isinstance(raw, dict) else raw or []
    seen: dict[str, ShortlistDecision] = {}
    for item in items:
        try:
            d = (
                item
                if isinstance(item, ShortlistDecision)
                else ShortlistDecision.model_validate(item)
            )
        except ValidationError:
            continue
        if d.job_id in valid_ids:
            seen[d.job_id] = d
    return [seen.get(j) or ShortlistDecision(job_id=j, decision="defer") for j in valid_ids]


def reason_tags() -> list[str]:
    """The fixed list of reason tags."""
    return [t.value for t in ReasonTag]
