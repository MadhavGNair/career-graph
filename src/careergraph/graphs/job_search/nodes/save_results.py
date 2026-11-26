"""save_results

Purpose:      Record rendered applications as "ready" in the tracker, total the run's token
              usage (and USD when priced) and write a human summary of where the files are.
Reads:        rendered, drafts, analyses, approved, decisions, run_id
Writes:       summary
Uses LLM?:    deterministic
Side effects: writes applications + application_events tables
Config keys:  config/pricing.yaml (USD only when prices are set)
"""

from __future__ import annotations

from typing import Any

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState


def save_results(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Persist ready applications and summarise the run."""
    ctx = runtime.context
    run_id = state["run_id"]
    analyses, drafts = state.get("analyses", {}), state.get("drafts", {})
    lines: list[str] = []
    for job_id, r in state.get("rendered", {}).items():
        p = analyses[job_id].posting
        ctx.repo.save_ready(
            drafts[job_id],
            company=p.company,
            role=p.title,
            url=p.url,
            out_dir=r.out_dir,
            thread_id=run_id,
        )
        pdf = "PDF compiled" if r.cv_pdf else "no PDF (.tex only)"
        lines.append(f"- READY {p.company}: {p.title}\n  {r.out_dir}  ({pdf})")
    for job_id, d in drafts.items():
        if job_id in state.get("approved", []) and d.status not in (
            "approved",
            "verified",
            "rejected",
        ):
            lines.append(f"- NOT RENDERED {job_id}: status {d.status} (unsupported claims remain)")
        elif d.status == "rejected":
            lines.append(f"- rejected in review: {job_id}")
    if not state.get("approved"):
        lines.append(f"- no jobs approved ({len(state.get('decisions', []))} decisions recorded)")
    tokens, usd = ctx.repo.run_totals(run_id)
    cost = f", ~${usd:.4f} (from config/pricing.yaml)" if usd else ""
    fake = " (fake LLM: plumbing check, not real spend)" if ctx.settings.is_demo else ""
    lines.append(f"- LLM usage this run: {tokens:,} tokens{cost}{fake}")
    return {"summary": "\n".join(lines)}
