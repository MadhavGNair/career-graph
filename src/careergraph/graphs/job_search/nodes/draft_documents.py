"""draft_documents (document_factory subgraph)

Purpose:      Write a tailored CV body and cover letter as structured JSON (never LaTeX); every
              claim cites evidence ids. Identity facts are injected deterministically afterwards.
Reads:        job, evidence, research, draft (previous revision + critique), critique, run_id
Writes:       draft
Uses LLM?:    STRONG tier, structured output (the only strong-tier call in the system)
Side effects: none
Config keys:  STRONG_MODEL, STRONG_EFFORT, profile.yaml (identity, experience, education)
"""

from __future__ import annotations

from typing import Any

from careergraph.documents.assemble import assemble
from careergraph.domain.models import DocumentDraft, DraftOutput
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.state import DocState
from careergraph.llm.prompts import DRAFT_SYSTEM, draft_prompt


def draft_documents(state: DocState, runtime: Ctx) -> dict[str, Any]:
    """Draft (or revise) one job's documents."""
    ctx = runtime.context
    job, prev = state["job"], state.get("draft")
    revision = prev.revision_count + 1 if prev else 0
    critique = prev.critique if prev else state.get("critique", "")
    evidence = state.get("evidence", [])
    employers = [r.employer for r in ctx.cfg.profile.experience]
    research = state.get("research")
    brief = research.model_dump(include={"summary", "facts"}) if research else None
    job_facts = {
        "title": job.posting.title,
        "company": job.posting.company,
        "must_have": job.analysis.must_have,
        "nice_to_have": job.analysis.nice_to_have,
        "seniority": job.analysis.seniority,
    }
    payload = {
        "job_id": job.posting.id,
        "revision": revision,
        "job": job_facts,
        "evidence": [e.model_dump(mode="json") for e in evidence],
        "employers": employers,
        "critique": critique,
        "unsupported": [c.text for c in prev.report.unsupported] if prev else [],
        "research": brief,
    }
    out = ctx.models.get_model("strong").structured(
        task="draft_documents",
        schema=DraftOutput,
        system=DRAFT_SYSTEM,
        prompt=draft_prompt(
            job_facts, evidence, employers, critique, brief, job.posting.description, job.posting.id
        ),
        payload=payload,
        run_id=state["run_id"],
    )
    cv, letter, notes = assemble(out, ctx.cfg.profile, job, ctx.today)
    draft = DocumentDraft(
        job_id=job.posting.id,
        cv=cv,
        letter=letter,
        revision_count=revision,
        critique_log=prev.critique_log if prev else [],
        notes=notes,
    )
    return {"draft": draft}
