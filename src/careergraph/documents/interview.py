"""Deterministic interview-question derivation from a JobAnalysis (and optional research)."""

from __future__ import annotations

from careergraph.domain.models import AnalyzedJob, InterviewQuestion, ResearchBrief

BEHAVIORAL = [
    "Tell me about a project you are most proud of and your exact contribution.",
    "Describe a time you disagreed with a technical decision. What did you do?",
    "Tell me about a time something you shipped failed in production.",
]


def derive_questions(
    job: AnalyzedJob, research: ResearchBrief | None, limit: int = 8
) -> list[InterviewQuestion]:
    """Technical questions per must-have skill, seniority-specific and behavioral ones, and one
    company question grounded in research facts when available."""
    a, p = job.analysis, job.posting
    qs: list[InterviewQuestion] = []
    for skill in a.must_have[:4]:
        qs.append(
            InterviewQuestion(
                id=f"q{len(qs) + 1}",
                kind="technical",
                skill=skill,
                text=f"Walk me through a production system where you used {skill}. "
                "What trade-offs did you make?",
            )
        )
    if a.seniority in ("senior", "staff", "principal", "lead"):
        qs.append(
            InterviewQuestion(
                id=f"q{len(qs) + 1}",
                kind="behavioral",
                text="How have you raised the bar for engineers around you?",
            )
        )
    for text in BEHAVIORAL:
        qs.append(InterviewQuestion(id=f"q{len(qs) + 1}", kind="behavioral", text=text))
    fact = research.facts[0].text if research and research.facts else ""
    qs.append(
        InterviewQuestion(
            id=f"q{len(qs) + 1}",
            kind="company",
            text=f"Why {p.company}?"
            + (
                f" We describe ourselves like this: '{fact[:140]}'. How does that fit you?"
                if fact
                else ""
            ),
        )
    )
    return qs[:limit]
