"""Deterministic verification: identity facts must match profile.yaml exactly, cited evidence
must exist, and degrees/years mentioned in claims must be grounded."""

from __future__ import annotations

import re

from careergraph.config import ProfileConfig
from careergraph.documents.assemble import identity_education, identity_roles
from careergraph.documents.claims import iter_claims
from careergraph.domain.models import DocumentDraft, EvidenceItem

_DEGREE = re.compile(r"\b(ph\.?\s?d|doctorate|mba|m\.?sc|b\.?sc|master'?s?|bachelor'?s?)\b", re.I)
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


def _norm_degree(s: str) -> str:
    s = s.lower().replace(".", "").replace(" ", "").replace("'", "")
    return {"doctorate": "phd", "masters": "master", "bachelors": "bachelor"}.get(s, s)


def fact_errors(
    draft: DocumentDraft, profile: ProfileConfig, evidence: dict[str, EvidenceItem]
) -> list[str]:
    """Return human-readable fact errors (empty list = all facts consistent)."""
    errors: list[str] = []
    ident = profile.identity
    cv, letter = draft.cv, draft.letter
    if (cv.name, cv.email, cv.phone) != (
        ident.name,
        ident.email,
        ident.phone,
    ) or letter.name != ident.name:
        errors.append("identity (name/email/phone) differs from profile.yaml")
    expected = [(r.employer, r.title, r.start, r.end) for r in identity_roles(profile)]
    actual = [(r.employer, r.title, r.start, r.end) for r in cv.experience]
    if actual != expected:
        errors.append(f"experience headers differ from profile.yaml: {actual} != {expected}")
    if [e.model_dump() for e in cv.education] != [
        e.model_dump() for e in identity_education(profile)
    ]:
        errors.append("education differs from profile.yaml")
    degrees = {_norm_degree(d.degree) for d in profile.education}
    degrees |= {_norm_degree(m) for d in profile.education for m in _DEGREE.findall(d.degree)}
    profile_years = set(_YEAR.findall(" ".join(f"{r.start} {r.end}" for r in profile.experience)))
    profile_years |= set(_YEAR.findall(" ".join(f"{d.start} {d.end}" for d in profile.education)))
    for claim_id, claim in iter_claims(draft):
        if not claim.evidence_ids:
            errors.append(f"{claim_id}: cites no evidence")
        missing = [i for i in claim.evidence_ids if i not in evidence]
        if missing:
            errors.append(f"{claim_id}: cites unknown evidence {missing}")
        cited = " ".join(
            f"{evidence[i].text} {evidence[i].dates}" for i in claim.evidence_ids if i in evidence
        )
        for deg in _DEGREE.findall(claim.text):
            if _norm_degree(deg) not in degrees and deg.lower() not in cited.lower():
                errors.append(f"{claim_id}: mentions a degree not in profile.yaml: {deg}")
        for year in set(_YEAR.findall(claim.text)) - profile_years - set(_YEAR.findall(cited)):
            errors.append(
                f"{claim_id}: mentions year {year} not found in profile or cited evidence"
            )
    return errors


def build_critique(unsupported: list[tuple[str, str, str]], errors: list[str]) -> str:
    """Critique for the next draft: (claim_id, text, reason) of unsupported claims + fact errors."""
    lines = [f"- UNSUPPORTED {cid}: {text!r} ({reason})" for cid, text, reason in unsupported]
    lines += [f"- FACT ERROR: {e}" for e in errors]
    return "\n".join(lines)
