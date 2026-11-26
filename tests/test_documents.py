"""Assembly with identity injection, claim ids/patches, deterministic fact checks, review parsing."""

from __future__ import annotations

from datetime import date

from careergraph.config import DEMO_DIR, ProfileConfig, load_yaml_model
from careergraph.documents.assemble import assemble
from careergraph.documents.claims import apply_patch, iter_claims
from careergraph.documents.review import parse_actions
from careergraph.documents.verify import fact_errors
from careergraph.domain.models import (
    AnalyzedJob,
    Claim,
    CVDraft,
    DocumentDraft,
    DraftOutput,
    EvidenceItem,
    InjectionReport,
    JobAnalysis,
    JobPosting,
    LetterDraft,
    RoleBullets,
)

PROFILE = load_yaml_model(DEMO_DIR / "profile" / "profile.yaml", ProfileConfig)
EV = {"ev-001": EvidenceItem(id="ev-001", kind="experience", text="Built ML platform on Kubernetes in 2022.",
                             skills=["kubernetes"], source_ref="cv")}  # fmt: skip
JOB = AnalyzedJob(
    posting=JobPosting(id="j", source="rss", company="Acme", title="ML Engineer", description="d"),
    analysis=JobAnalysis(summary="s"),
    injection=InjectionReport(flagged=False, score=0),
)


def _draft(*claims: Claim, employer: str = "Quillfeather Analytics GmbH") -> DocumentDraft:
    out = DraftOutput(
        cv=CVDraft(
            summary=list(claims),
            roles=[
                RoleBullets(
                    employer=employer,
                    bullets=[
                        Claim(text="Built ML platform on Kubernetes.", evidence_ids=["ev-001"])
                    ],
                )
            ],
        ),
        letter=LetterDraft(
            paragraphs=[Claim(text="I built an ML platform.", evidence_ids=["ev-001"])]
        ),
    )
    cv, letter, notes = assemble(out, PROFILE, JOB, date(2026, 11, 20))
    return DocumentDraft(job_id="j", cv=cv, letter=letter, notes=notes)


def test_identity_is_injected_verbatim_and_unknown_employer_noted() -> None:
    d = _draft(employer="Google")
    assert d.cv.name == "Sam Demo" and d.cv.experience[0].employer == "Quillfeather Analytics GmbH"
    assert all(not r.bullets for r in d.cv.experience)
    assert d.notes and "Google" in d.notes[0]
    assert d.letter.date == "20 November 2026" and d.letter.company == "Acme"


def test_clean_draft_has_no_fact_errors() -> None:
    assert (
        fact_errors(
            _draft(Claim(text="Built ML platform in 2022.", evidence_ids=["ev-001"])), PROFILE, EV
        )
        == []
    )


def test_fact_checks_catch_tampering_and_ungrounded_details() -> None:
    d = _draft(
        Claim(text="Earned a PhD in 2015.", evidence_ids=["ev-001"]),
        Claim(text="No evidence here."),
        Claim(text="Cites a ghost.", evidence_ids=["ev-999"]),
    )
    d.cv.experience[0].start = "2019-01"
    errors = "\n".join(fact_errors(d, PROFILE, EV))
    assert "experience headers differ" in errors
    assert "degree not in profile.yaml: PhD" in errors
    assert "year 2015" in errors
    assert "cites no evidence" in errors
    assert "unknown evidence ['ev-999']" in errors


def test_claim_ids_and_patch() -> None:
    d = _draft(Claim(text="A.", evidence_ids=["ev-001"]), Claim(text="B.", evidence_ids=["ev-001"]))
    ids = [cid for cid, _ in iter_claims(d)]
    assert ids == [
        "cv.summary.0",
        "cv.summary.1",
        "cv.experience.0.bullets.0",
        "letter.paragraphs.0",
    ]
    patched, unknown = apply_patch(d, {"cv.summary.0": "A2.", "cv.summary.1": "", "nope": "x"})
    assert [c.text for c in patched.cv.summary] == ["A2."] and unknown == ["nope"]
    assert patched.cv.summary[0].evidence_ids == ["ev-001"] and d.cv.summary[0].text == "A."


def test_parse_review_actions() -> None:
    acts = parse_actions(
        {
            "actions": [
                {"job_id": "a", "action": "approve"},
                {"job_id": "b", "action": "fly"},
                {"job_id": "c", "action": "reject"},
            ]
        },
        ["a", "b"],
    )
    assert [(a.job_id, a.action) for a in acts] == [("a", "approve")]
