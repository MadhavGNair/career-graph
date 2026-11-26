"""verify_documents (document_factory subgraph)

Purpose:      Check a draft: deterministic fact checks (identity facts exact, evidence ids exist,
              degrees and years grounded) plus a per-claim entailment label (supported, partial,
              unsupported) with the supporting evidence quote. Decide whether to revise.
Reads:        draft, evidence_pool, job, research, run_id
Writes:       draft (report, critique, status), revise
Uses LLM?:    cheap tier, one structured call per NEW claim (unchanged claims reuse results)
Side effects: none
Config keys:  CHEAP_MODEL, MAX_REVISIONS
"""

from __future__ import annotations

from typing import Any

from careergraph.documents.claims import iter_claims
from careergraph.documents.verify import build_critique, fact_errors
from careergraph.domain.models import ClaimCheck, Entailment, VerificationReport
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.state import DocState
from careergraph.llm.prompts import VERIFY_SYSTEM, verify_prompt


def verify_documents(state: DocState, runtime: Ctx) -> dict[str, Any]:
    """Verify every claim; set revise=True when the loop should draft again."""
    ctx = runtime.context
    draft = state.get("draft")
    assert draft is not None, "verify_documents needs a draft"
    pool = {e.id: e for e in state.get("evidence_pool", [])}
    job, research = state["job"], state.get("research")
    context = f"{job.posting.company} {job.posting.title} " + " ".join(
        f.text for f in (research.facts if research else [])
    )
    errors = fact_errors(draft, ctx.cfg.profile, pool) + draft.notes
    known = {(c.text, tuple(c.evidence_ids)): c for c in draft.report.checks}
    llm = ctx.models.get_model("cheap")
    checks: list[ClaimCheck] = []
    for claim_id, claim in iter_claims(draft):
        hit = known.get((claim.text, tuple(claim.evidence_ids)))
        if hit is not None:
            checks.append(hit.model_copy(update={"claim_id": claim_id}))
            continue
        cited = [pool[i] for i in claim.evidence_ids if i in pool]
        ent = llm.structured(
            task="verify_claim",
            schema=Entailment,
            system=VERIFY_SYSTEM,
            prompt=verify_prompt(claim, cited),
            payload={
                "claim": claim.text,
                "evidence": [e.model_dump(mode="json") for e in cited],
                "context": context,
            },
            run_id=state["run_id"],
        )
        checks.append(
            ClaimCheck(
                claim_id=claim_id,
                text=claim.text,
                evidence_ids=claim.evidence_ids,
                **ent.model_dump(),
            )
        )
    report = VerificationReport(checks=checks, fact_errors=errors)
    critique = build_critique([(c.claim_id, c.text, c.reason) for c in report.unsupported], errors)
    # Human edits (mode=verify) are re-verified but never redrafted automatically.
    can_revise = state.get("mode") != "verify" and draft.revision_count < ctx.settings.max_revisions
    revise = not report.ok and can_revise
    log = draft.critique_log + (
        [f"revision {draft.revision_count}:\n{critique}"] if critique else []
    )
    status = "verified" if report.ok else "flagged"
    new = draft.model_copy(
        update={"report": report, "critique": critique, "critique_log": log, "status": status}
    )
    return {"draft": new, "revise": revise}
