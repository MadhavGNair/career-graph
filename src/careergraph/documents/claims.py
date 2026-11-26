"""Stable claim ids (cv.summary.0, cv.experience.1.bullets.2, cv.projects.0,
letter.paragraphs.1) used by verification reports, the UI editor and review patches."""

from __future__ import annotations

from collections.abc import Iterator

from careergraph.domain.models import Claim, DocumentDraft


def iter_claims(draft: DocumentDraft) -> Iterator[tuple[str, Claim]]:
    """Every claim in CV and letter with its id."""
    for i, c in enumerate(draft.cv.summary):
        yield f"cv.summary.{i}", c
    for j, role in enumerate(draft.cv.experience):
        for i, c in enumerate(role.bullets):
            yield f"cv.experience.{j}.bullets.{i}", c
    for i, c in enumerate(draft.cv.projects):
        yield f"cv.projects.{i}", c
    for i, c in enumerate(draft.letter.paragraphs):
        yield f"letter.paragraphs.{i}", c


def apply_patch(draft: DocumentDraft, patch: dict[str, str]) -> tuple[DocumentDraft, list[str]]:
    """Replace claim texts by id (evidence ids are kept). An empty text deletes the claim.

    Returns the patched copy and a list of unknown ids.
    """
    new = draft.model_copy(deep=True)
    claims = dict(iter_claims(new))
    unknown = [k for k in patch if k not in claims]
    for claim_id, text in patch.items():
        if claim_id in claims:
            claims[claim_id].text = text.strip()
    new.cv.summary = [c for c in new.cv.summary if c.text]
    new.cv.projects = [c for c in new.cv.projects if c.text]
    for role in new.cv.experience:
        role.bullets = [c for c in role.bullets if c.text]
    new.letter.paragraphs = [c for c in new.letter.paragraphs if c.text]
    return new, unknown
