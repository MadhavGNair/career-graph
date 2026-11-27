"""Tracker graph state and the interview_prep subgraph state."""

from __future__ import annotations

import operator
from typing import Annotated, Required, TypedDict

from careergraph.domain.models import (
    AnalyzedJob,
    EvidenceItem,
    InterviewPrep,
    MockTurn,
    ResearchBrief,
)


class TrackerState(TypedDict, total=False):
    """One status change (and, for interviews, prep + a mock interview)."""

    run_id: Required[str]
    job_id: Required[str]
    new_status: Required[str]
    note: str
    old_status: str
    error: str
    prep: InterviewPrep | None
    turn: int
    pending_answer: str
    transcript: Annotated[list[MockTurn], operator.add]
    summary: str


class PrepState(TypedDict, total=False):
    """interview_prep subgraph."""

    run_id: Required[str]
    job: Required[AnalyzedJob]
    evidence: list[EvidenceItem]
    research: ResearchBrief | None
    prep: InterviewPrep | None
