"""State schemas of the two subgraphs."""

from __future__ import annotations

from typing import Required, TypedDict

from langgraph.graph import MessagesState

from careergraph.domain.models import AnalyzedJob, DocumentDraft, EvidenceItem, ResearchBrief


class DocState(TypedDict, total=False):
    """document_factory: one job's draft <-> verify loop."""

    run_id: Required[str]
    job: Required[AnalyzedJob]
    evidence: list[EvidenceItem]
    evidence_pool: list[EvidenceItem]
    research: ResearchBrief | None
    draft: DocumentDraft | None
    critique: str
    mode: str
    revise: bool


class ResearchState(MessagesState, total=False):
    """research_company: one company's ReAct loop."""

    run_id: Required[str]
    job_id: str
    company: Required[str]
    allowed_domains: list[str]
    steps: int
    tokens: int
    stop_reason: str
    brief: ResearchBrief | None
