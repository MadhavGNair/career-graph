"""render_latex

Purpose:      Fill the LaTeX templates (yours in <documents dir>/templates override templates/)
              with approved drafts, compile to PDF if an engine exists, and write report.md.
Reads:        drafts, approved, analyses, matches, research
Writes:       rendered {job_id: RenderResult}
Uses LLM?:    deterministic
Side effects: writes OUTPUT_DIR/<date>/<company>-<role>/{cv.tex, letter.tex, cv.pdf?, letter.pdf?,
              report.md}; runs tectonic/pdflatex when available
Config keys:  TEMPLATES_DIR, OUTPUT_DIR, LATEX_ENGINE, LATEX_TIMEOUT_SECONDS,
              REQUIRE_DOCUMENT_REVIEW (when false, verified drafts count as approved)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from careergraph.documents.report import build_report
from careergraph.domain.models import RenderResult
from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.latex.render import template_dirs, write_and_compile


def slug(text: str) -> str:
    """Filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "job"


def render_latex(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Render and (optionally) compile every approved draft."""
    ctx = runtime.context
    s = ctx.settings
    ok = {"approved"} if s.require_document_review else {"approved", "verified"}
    analyses, research = state.get("analyses", {}), state.get("research", {})
    matches = {m.job_id: m for m in state.get("matches", [])}
    dirs = template_dirs(s.resolve(s.templates_dir), s.resolve(Path(ctx.cfg.profile.documents.dir)))
    rendered: dict[str, RenderResult] = {}
    for job_id, draft in state.get("drafts", {}).items():
        if draft.status not in ok or job_id not in state.get("approved", []):
            continue
        job = analyses[job_id]
        out = (
            s.resolve(s.output_dir)
            / ctx.today.isoformat()
            / f"{slug(job.posting.company)}-{slug(job.posting.title)}"
        )
        cv_path, letter_path, results = write_and_compile(
            draft.cv, draft.letter, dirs, out, s.latex_engine, s.latex_timeout_seconds
        )
        message = "; ".join(f"{r.engine}: {r.message}" for r in results)
        report = build_report(draft, job, matches.get(job_id), research.get(job_id), message)
        (out / "report.md").write_text(report, encoding="utf-8")
        rendered[job_id] = RenderResult(
            job_id=job_id,
            out_dir=str(out),
            cv_tex=str(cv_path),
            letter_tex=str(letter_path),
            report_md=str(out / "report.md"),
            cv_pdf=str(results[0].pdf) if results[0].pdf else None,
            letter_pdf=str(results[1].pdf) if results[1].pdf else None,
            compile_message=message,
        )
    return {"rendered": rendered}
