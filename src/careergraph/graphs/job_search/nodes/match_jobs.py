"""match_jobs

Purpose:      Score every analysed posting against the profile, apply dealbreakers, the
              threshold and top N, and attach a short rationale to shortlisted jobs.
Reads:        profile, analyses, run_id; Store: learned preferences
Writes:       matches, shortlist
Uses LLM?:    mostly deterministic; optional cheap-tier rationale per shortlisted job
Side effects: writes matches table
Config keys:  criteria.yaml (weights, threshold, top_n, related_skill_credit, target_seniority,
              salary_floor, dealbreakers, preference); ENABLE_MATCH_RATIONALE; EMBEDDING_*
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import MatchRationale
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.llm.prompts import RATIONALE_SYSTEM, rationale_prompt
from careergraph.matching.scoring import ScoringContext, default_rationale, score_job, shortlist
from careergraph.memory import preferences
from careergraph.retrieval.index import HybridIndex


def match_jobs(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Score, rank and shortlist."""
    ctx = runtime.context
    crit = ctx.cfg.criteria
    profile = state.get("profile")
    assert profile is not None, "match_jobs needs a profile (run ingest/extract first)"
    docs = [(e.id, f"{e.text} {' '.join(e.skills)}") for e in profile.evidence]
    sctx = ScoringContext(ctx.cfg, profile, HybridIndex(docs, ctx.embedder), ctx.skills)
    weights = preferences.load(runtime.store) if crit.preference.enabled else {}
    decided = ctx.repo.decided_job_ids()
    jobs = {k: v for k, v in state.get("analyses", {}).items() if k not in decided}
    results = [score_job(j, sctx, preferences.adjustment(weights, j)) for j in jobs.values()]
    picked = shortlist(results, crit.threshold, crit.top_n)
    llm = ctx.models.get_model("cheap")
    final = []
    for r in results:
        r = r.model_copy(
            update={"shortlisted": r.job_id in picked, "rationale": default_rationale(r)}
        )
        if r.shortlisted and ctx.settings.enable_match_rationale:
            facts = {
                "title": jobs[r.job_id].posting.title,
                "company": jobs[r.job_id].posting.company,
                "score": r.score,
                "matched": [m.skill for m in r.skills_with("matched")],
                "partial": [f"{m.skill} (via {m.via})" for m in r.skills_with("partial")],
                "missing": [m.skill for m in r.skills_with("missing")],
                "breakdown": {c.name: c.score for c in r.breakdown},
            }
            out = llm.structured(
                task="match_rationale",
                schema=MatchRationale,
                system=RATIONALE_SYSTEM,
                prompt=rationale_prompt(facts),
                payload=facts,
                run_id=state["run_id"],
            )
            r = r.model_copy(update={"rationale": " ".join(out.rationale.split()[:50])})
        final.append(r)
    final.sort(key=lambda r: (-r.score, r.job_id))
    ctx.repo.save_matches(state["run_id"], final)
    return {"matches": final, "shortlist": picked}
