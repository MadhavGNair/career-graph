"""derive_questions (interview_prep subgraph)

Purpose:      Likely questions from the JobAnalysis (must-have skills, seniority) plus
              behavioral and company questions (grounded in research facts when present).
Reads:        job, research
Writes:       prep (questions)
Uses LLM?:    deterministic
Side effects: none
Config keys:  none
"""

from __future__ import annotations

from typing import Any

from careergraph.documents.interview import derive_questions as derive
from careergraph.domain.models import InterviewPrep
from careergraph.graphs.tracker.state import PrepState


def derive_questions(state: PrepState) -> dict[str, Any]:
    """Build the question list."""
    job = state["job"]
    research = state.get("research")
    return {
        "prep": InterviewPrep(
            job_id=job.posting.id, questions=derive(job, research), research=research
        )
    }
