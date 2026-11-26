"""Review interrupt payload and resume validation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from careergraph.documents.claims import iter_claims
from careergraph.domain.models import AnalyzedJob, DocumentDraft, ResearchBrief, ReviewAction

HELP = (
    "For each draft choose approve, edit (patch: {claim_id: new text}; edits are re-verified), "
    "regenerate (optional reason) or reject (reason). Drafts still flagged after the maximum "
    "revisions can only be approved with override=true."
)


def review_rows(
    drafts: list[DocumentDraft],
    analyses: dict[str, AnalyzedJob],
    research: dict[str, ResearchBrief],
) -> list[dict[str, Any]]:
    """JSON-safe rows for the UI/CLI."""
    rows = []
    for d in drafts:
        job = analyses[d.job_id]
        labels = {c.claim_id: c for c in d.report.checks}
        brief = research.get(d.job_id)
        rows.append(
            {
                "job_id": d.job_id,
                "title": job.posting.title,
                "company": job.posting.company,
                "status": d.status,
                "flagged": d.flagged,
                "revision_count": d.revision_count,
                "unsupported": len(d.report.unsupported),
                "partial": sum(c.label == "partial" for c in d.report.checks),
                "fact_errors": d.report.fact_errors,
                "critique_log": d.critique_log,
                "claims": [
                    {
                        "claim_id": cid,
                        "text": c.text,
                        "evidence_ids": c.evidence_ids,
                        "label": labels[cid].label if cid in labels else "unchecked",
                        "quote": labels[cid].quote if cid in labels else "",
                        "reason": labels[cid].reason if cid in labels else "",
                    }
                    for cid, c in iter_claims(d)
                ],
                "cv": d.cv.model_dump(mode="json"),
                "letter": d.letter.model_dump(mode="json"),
                "research": brief.model_dump(mode="json") if brief else None,
            }
        )
    return rows


def parse_actions(raw: Any, valid_ids: list[str]) -> list[ReviewAction]:
    """Validate a resume value; unknown ids and malformed items are dropped."""
    items = raw.get("actions", []) if isinstance(raw, dict) else raw or []
    out: dict[str, ReviewAction] = {}
    for item in items:
        try:
            a = item if isinstance(item, ReviewAction) else ReviewAction.model_validate(item)
        except ValidationError:
            continue
        if a.job_id in valid_ids:
            out[a.job_id] = a
    return list(out.values())
