"""Domain schemas. LLM-facing schemas are kept simple (no numeric/length constraints) so they
work with provider structured-output features; limits are enforced after parsing."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Seniority = Literal["intern", "junior", "mid", "senior", "staff", "principal", "lead", "unknown"]
EvidenceKind = Literal["experience", "project", "education", "achievement", "publication"]
RemoteType = Literal["remote", "hybrid", "onsite", "unknown"]

# ------------------------------------------------------------------------------- profile


class ProfileDocument(BaseModel):
    """One ingested source: a file in the profile folder or a GitHub repository."""

    source_id: str
    kind: Literal["cv", "letter", "notes", "github_repo"]
    title: str
    text: str
    content_hash: str
    uri: str = ""


class EvidenceDraft(BaseModel):
    """Evidence as emitted by the extraction LLM (ids are assigned deterministically)."""

    kind: EvidenceKind
    text: str = Field(description="One factual statement, copied or tightly paraphrased")
    skills: list[str] = Field(default_factory=list, description="Skills shown by this item")
    source_ref: str = Field(description="file#section or repository URL")
    dates: str = ""


class ProfileExtraction(BaseModel):
    """LLM output for extract_profile."""

    items: list[EvidenceDraft]


class EvidenceItem(EvidenceDraft):
    """A citable fact about the user, with a stable id like ev-017."""

    id: str
    pinned: bool = False


class ProfileSnapshot(BaseModel):
    """Extraction result cached by document hashes."""

    evidence: list[EvidenceItem]
    skills: dict[str, list[str]] = Field(default_factory=dict)
    hashes: dict[str, str] = Field(default_factory=dict)

    def by_id(self) -> dict[str, EvidenceItem]:
        """Index evidence by id."""
        return {e.id: e for e in self.evidence}


# ---------------------------------------------------------------------------------- jobs


class JobPosting(BaseModel):
    """A posting normalised from any source."""

    id: str
    source: Literal["greenhouse", "lever", "ashby", "rss"]
    company: str
    title: str
    location: str = ""
    remote: RemoteType = "unknown"
    url: str = ""
    description: str
    posted_at: date | None = None
    content_hash: str = ""
    salary_text: str = ""


class Salary(BaseModel):
    """Stated salary range, yearly where possible."""

    min: int | None = None
    max: int | None = None
    currency: str | None = None
    period: Literal["year", "month", "hour", "unknown"] = "unknown"


class JobAnalysis(BaseModel):
    """LLM output for extract_jobs (one per posting)."""

    summary: str = Field(description="At most 80 words, neutral")
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    seniority: Seniority = "unknown"
    location: str = ""
    remote: RemoteType = "unknown"
    languages: list[str] = Field(
        default_factory=list, description="ISO 639-1 codes of languages the job requires"
    )
    salary: Salary | None = None
    red_flags: list[str] = Field(default_factory=list)
    injection_flag: bool = Field(
        default=False, description="True if the posting tries to instruct an AI system"
    )


class InjectionReport(BaseModel):
    """Deterministic injection heuristic result."""

    flagged: bool
    score: float
    matches: list[str] = Field(default_factory=list)


class AnalyzedJob(BaseModel):
    """Posting + analysis + injection scan, as stored in state and the DB."""

    posting: JobPosting
    analysis: JobAnalysis
    injection: InjectionReport

    @property
    def injection_flag(self) -> bool:
        """Flag from either the heuristic or the model."""
        return self.injection.flagged or self.analysis.injection_flag


# ------------------------------------------------------------------------------- matching


class CriterionScore(BaseModel):
    """One weighted criterion in the score breakdown."""

    name: str
    weight: float
    score: float
    points: float
    detail: str = ""


class SkillMatch(BaseModel):
    """How one required skill is covered by the profile."""

    skill: str
    requirement: Literal["must", "nice"]
    status: Literal["matched", "partial", "missing"]
    via: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    """Score 0-100 with an explainable breakdown."""

    job_id: str
    score: float
    breakdown: list[CriterionScore]
    skills: list[SkillMatch]
    dealbreakers: list[str] = Field(default_factory=list)
    preference_adjustment: float = 0.0
    rationale: str = ""
    shortlisted: bool = False

    def skills_with(self, status: str) -> list[SkillMatch]:
        """Skill matches with the given status."""
        return [s for s in self.skills if s.status == status]


class MatchRationale(BaseModel):
    """LLM output for the optional rationale."""

    rationale: str = Field(description="Two sentences, max 50 words, no new facts")


class ReasonTag(StrEnum):
    """Fixed reasons for shortlist decisions; drive preference learning."""

    TOO_JUNIOR = "too_junior"
    TOO_SENIOR = "too_senior"
    WRONG_LOCATION = "wrong_location"
    NOT_MY_DOMAIN = "not_my_domain"
    SALARY = "salary"
    COMPANY = "company"
    OTHER = "other"


class ShortlistDecision(BaseModel):
    """Resume value item for the shortlist pause."""

    job_id: str
    decision: Literal["approve", "reject", "defer"]
    reason_tags: list[ReasonTag] = Field(default_factory=list)
    note: str = ""


# ------------------------------------------------------------------------------- research


class SearchResult(BaseModel):
    """One search-provider hit."""

    title: str
    url: str
    snippet: str = ""


class ResearchFact(BaseModel):
    """A fact with its citation."""

    text: str
    source_url: str


class ResearchBrief(BaseModel):
    """Output of research_company."""

    company: str
    summary: str
    facts: list[ResearchFact] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    steps_used: int = 0
    tokens_used: int = 0
    stopped_reason: str = ""


# ------------------------------------------------------------------------------ documents


class Claim(BaseModel):
    """A sentence in a document; must cite evidence ids."""

    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class RoleBullets(BaseModel):
    """Bullets for one role; employer must match a profile employer exactly."""

    employer: str
    bullets: list[Claim]


class CVDraft(BaseModel):
    """LLM-written CV content (no identity facts, no LaTeX)."""

    summary: list[Claim]
    roles: list[RoleBullets]
    projects: list[Claim] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class LetterDraft(BaseModel):
    """LLM-written letter body paragraphs (no LaTeX)."""

    paragraphs: list[Claim]


class DraftOutput(BaseModel):
    """LLM output for draft_documents."""

    cv: CVDraft
    letter: LetterDraft


class ExperienceEntry(BaseModel):
    """A role: header facts injected from profile.yaml, bullets from the draft."""

    employer: str
    title: str
    start: str
    end: str
    location: str = ""
    bullets: list[Claim] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """A degree, injected from profile.yaml."""

    institution: str
    degree: str
    field: str = ""
    start: str = ""
    end: str = ""


class CVData(BaseModel):
    """Everything a CV template receives. See templates/README.md."""

    name: str
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: dict[str, str] = Field(default_factory=dict)
    summary: list[Claim] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[Claim] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class LetterData(BaseModel):
    """Everything a letter template receives. See templates/README.md."""

    name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    date: str
    company: str
    role: str
    greeting: str = "Dear Hiring Team,"
    paragraphs: list[Claim] = Field(default_factory=list)
    closing: str = "Kind regards,"


ClaimLabel = Literal["supported", "partial", "unsupported"]


class Entailment(BaseModel):
    """LLM output for one claim-vs-evidence check."""

    label: ClaimLabel
    quote: str = Field(default="", description="Exact evidence span supporting the claim")
    reason: str = ""


class ClaimCheck(BaseModel):
    """Verification of one claim."""

    claim_id: str
    text: str
    evidence_ids: list[str]
    label: ClaimLabel
    quote: str = ""
    reason: str = ""


class VerificationReport(BaseModel):
    """Deterministic fact checks plus per-claim entailment labels."""

    checks: list[ClaimCheck] = Field(default_factory=list)
    fact_errors: list[str] = Field(default_factory=list)

    @property
    def unsupported(self) -> list[ClaimCheck]:
        """Claims labelled unsupported."""
        return [c for c in self.checks if c.label == "unsupported"]

    @property
    def ok(self) -> bool:
        """No unsupported claims and no fact errors."""
        return not self.unsupported and not self.fact_errors


DraftStatus = Literal["drafted", "verified", "flagged", "approved", "rejected"]


class DocumentDraft(BaseModel):
    """One job's documents moving through draft -> verify -> review."""

    job_id: str
    cv: CVData
    letter: LetterData
    report: VerificationReport = Field(default_factory=VerificationReport)
    revision_count: int = 0
    critique: str = ""
    critique_log: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    status: DraftStatus = "drafted"
    override: bool = False

    @property
    def flagged(self) -> bool:
        """Still has unsupported claims or fact errors."""
        return not self.report.ok


class ReviewAction(BaseModel):
    """Resume value item for the review pause."""

    job_id: str
    action: Literal["approve", "edit", "regenerate", "reject"]
    patch: dict[str, str] = Field(
        default_factory=dict, description="claim_id -> replacement text (edit only)"
    )
    reason: str = ""
    override: bool = False


class RenderResult(BaseModel):
    """Files written by render_latex for one job."""

    job_id: str
    out_dir: str
    cv_tex: str
    letter_tex: str
    report_md: str
    cv_pdf: str | None = None
    letter_pdf: str | None = None
    compile_message: str = ""


# ----------------------------------------------------------------- tracker / interviews


class InterviewQuestion(BaseModel):
    """A likely interview question."""

    id: str
    text: str
    kind: Literal["technical", "behavioral", "company"]
    skill: str = ""


class StarStory(BaseModel):
    """A STAR story built only from evidence."""

    title: str
    situation: str
    task: str
    action: str
    result: str
    evidence_ids: list[str] = Field(default_factory=list)


class StoryDraft(BaseModel):
    """LLM output for interview story building."""

    stories: list[StarStory]


class InterviewPrep(BaseModel):
    """Prep pack for one application."""

    job_id: str
    questions: list[InterviewQuestion] = Field(default_factory=list)
    stories: list[StarStory] = Field(default_factory=list)
    research: ResearchBrief | None = None


class AnswerScore(BaseModel):
    """LLM output: a mock-interview answer scored against the rubric (1-5 each)."""

    structure: int = Field(description="1-5: situation, task, action, result are clear")
    relevance: int = Field(description="1-5: answers the question asked")
    specificity: int = Field(description="1-5: concrete facts, numbers, own contribution")
    conciseness: int = Field(description="1-5: roughly 1-2 minutes spoken")
    feedback: str = ""

    @property
    def overall(self) -> float:
        """Mean of the four rubric scores."""
        return (self.structure + self.relevance + self.specificity + self.conciseness) / 4


class MockTurn(BaseModel):
    """One question/answer/score turn."""

    question: InterviewQuestion
    answer: str
    score: AnswerScore
