"""extract_jobs (runs once per posting, in parallel, via Send)

Purpose:      Scan one posting for prompt injection, extract a structured JobAnalysis, normalise
              its skills and persist it (also feeds the skills-demand-over-time chart).
Reads:        branch payload {run_id, posting}
Writes:       analyses[posting.id]  (merged by the reducer)
Uses LLM?:    cheap tier, structured output; NO tools (untrusted input)
Side effects: writes postings, analyses, requirements tables
Config keys:  CHEAP_MODEL, skills.yaml
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import AnalyzedJob, JobAnalysis
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobBranch
from careergraph.llm.prompts import EXTRACT_JOB_SYSTEM, extract_job_prompt
from careergraph.security.injection import scan

MAX_SUMMARY_WORDS = 80


def extract_jobs(branch: JobBranch, runtime: Ctx) -> dict[str, Any]:
    """Analyse one posting."""
    ctx = runtime.context
    posting = branch["posting"]
    report = scan(f"{posting.title}\n{posting.description}")
    raw = ctx.models.get_model("cheap").structured(
        task="extract_job",
        schema=JobAnalysis,
        system=EXTRACT_JOB_SYSTEM,
        prompt=extract_job_prompt(posting),
        payload={"posting": posting.model_dump(mode="json")},
        run_id=branch["run_id"],
    )
    must = ctx.skills.normalize_all(raw.must_have)
    analysis = raw.model_copy(
        update={
            "summary": " ".join(raw.summary.split()[:MAX_SUMMARY_WORDS]),
            "must_have": must,
            "nice_to_have": [
                s for s in ctx.skills.normalize_all(raw.nice_to_have) if s not in must
            ],
            "languages": sorted({lang.lower()[:2] for lang in raw.languages if lang}),
        }
    )
    job = AnalyzedJob(posting=posting, analysis=analysis, injection=report)
    ctx.repo.save_analysis(job)
    return {"analyses": {posting.id: job}}
