"""Turn LLM drafts (claims only) into CVData/LetterData with identity facts injected verbatim."""

from __future__ import annotations

from datetime import date

from careergraph.config import ProfileConfig
from careergraph.domain.models import (
    AnalyzedJob,
    CVData,
    DraftOutput,
    EducationEntry,
    EvidenceItem,
    ExperienceEntry,
    LetterData,
    ProfileSnapshot,
)
from careergraph.retrieval.index import HybridIndex

LANG_NAMES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese",
    "pl": "Polish",
}


def select_evidence(
    job: AnalyzedJob, profile: ProfileSnapshot, index: HybridIndex, k: int = 14
) -> list[EvidenceItem]:
    """Evidence most relevant to the posting: every item proving a required skill first, then
    hybrid-retrieval hits, de-duplicated, at most k."""
    by_id = profile.by_id()
    ordered: list[str] = []
    for skill in job.analysis.must_have + job.analysis.nice_to_have:
        ordered += profile.skills.get(skill, [])[:2]
    query = " ".join([job.posting.title, job.analysis.summary, *job.analysis.must_have])
    ordered += [h.doc_id for h in index.search(query, k=k)]
    return [by_id[i] for i in dict.fromkeys(ordered) if i in by_id][:k]


def identity_roles(profile: ProfileConfig) -> list[ExperienceEntry]:
    """Roles exactly as in profile.yaml (never generated)."""
    return [
        ExperienceEntry(
            employer=r.employer, title=r.title, start=r.start, end=r.end, location=r.location
        )
        for r in profile.experience
    ]


def identity_education(profile: ProfileConfig) -> list[EducationEntry]:
    """Degrees exactly as in profile.yaml."""
    return [EducationEntry(**d.model_dump()) for d in profile.education]


def assemble(
    out: DraftOutput, profile: ProfileConfig, job: AnalyzedJob, today: date
) -> tuple[CVData, LetterData, list[str]]:
    """Build template data. Returns notes about draft content that had to be dropped (e.g. bullets
    for an employer not in profile.yaml); the verifier treats those as fact errors."""
    ident = profile.identity
    notes: list[str] = []
    roles = identity_roles(profile)
    by_employer = {r.employer: r for r in roles}
    for rb in out.cv.roles:
        target = by_employer.get(rb.employer)
        if target is None:
            notes.append(f"draft used an employer not in profile.yaml: {rb.employer!r}")
            continue
        target.bullets.extend(rb.bullets)
    cv = CVData(
        name=ident.name,
        headline=ident.headline,
        email=ident.email,
        phone=ident.phone,
        location=ident.location,
        links=dict(ident.links),
        summary=out.cv.summary,
        experience=roles,
        projects=out.cv.projects,
        skills=out.cv.skills,
        education=identity_education(profile),
        languages=[
            f"{LANG_NAMES.get(lang.code, lang.code)} ({lang.level})" for lang in ident.languages
        ],
    )
    letter = LetterData(
        name=ident.name,
        email=ident.email,
        phone=ident.phone,
        location=ident.location,
        date=today.strftime("%d %B %Y"),
        company=job.posting.company,
        role=job.posting.title,
        paragraphs=out.letter.paragraphs,
    )
    return cv, letter, notes
