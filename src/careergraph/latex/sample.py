"""Sample data for `make render-sample` and the golden-file test (fictional, with every LaTeX
special character so escaping is exercised)."""

from __future__ import annotations

from datetime import date

from careergraph.config import ProfileConfig
from careergraph.documents.assemble import identity_education, identity_roles
from careergraph.domain.models import Claim, CVData, LetterData


def sample_documents(profile: ProfileConfig) -> tuple[CVData, LetterData]:
    """CVData/LetterData built from profile identity plus fixed sample claims."""
    ident = profile.identity
    roles = identity_roles(profile)
    if roles:
        roles[0].bullets = [
            Claim(
                text="Cut costs by 38% & shipped R&D tooling in C# and C++ (budget: $1,000_000).",
                evidence_ids=["ev-001"],
            ),
            Claim(
                text="Handled paths like ~/data/{raw}/x^2 and back\\slashes #safely.",
                evidence_ids=["ev-002"],
            ),
        ]
    cv = CVData(
        name=ident.name,
        headline=ident.headline,
        email=ident.email,
        phone=ident.phone,
        location=ident.location,
        links=dict(ident.links),
        summary=[
            Claim(
                text="Machine learning engineer – production first… €-aware.",
                evidence_ids=["ev-001"],
            )
        ],
        experience=roles,
        projects=[Claim(text="Open-source evaluation kit (100% Python).", evidence_ids=["ev-003"])],
        skills=["python", "c++", "ci/cd"],
        education=identity_education(profile),
        languages=["English (fluent)"],
    )
    letter = LetterData(
        name=ident.name,
        email=ident.email,
        phone=ident.phone,
        location=ident.location,
        date=date(2026, 11, 20).strftime("%d %B %Y"),
        company="Example & Co",
        role="ML Engineer_II",
        paragraphs=[
            Claim(
                text="I build reliable ML systems; 100% of claims cite evidence.",
                evidence_ids=["ev-001"],
            )
        ],
    )
    return cv, letter
