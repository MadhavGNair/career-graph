"""report.md written next to the .tex files: why this job, what was verified, sources."""

from __future__ import annotations

from careergraph.domain.models import AnalyzedJob, DocumentDraft, MatchResult, ResearchBrief


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def build_report(
    draft: DocumentDraft,
    job: AnalyzedJob,
    match: MatchResult | None,
    research: ResearchBrief | None,
    compile_message: str,
) -> str:
    """Markdown report for one application."""
    p = job.posting
    lines = [
        f"# {p.title} at {p.company}",
        "",
        f"- Posting: {p.url or '(no url)'}",
        f"- Location: {p.location} ({job.analysis.remote})",
        f"- Status: {draft.status}{' (approved with override)' if draft.override else ''}",
        f"- Revisions: {draft.revision_count}",
        f"- LaTeX: {compile_message}",
        "",
        "CareerGraph never applies for you. Review both documents before sending them.",
        "",
    ]
    if job.injection_flag:
        lines += [
            "> WARNING: this posting was flagged for prompt injection:",
            *[f"> - {m}" for m in job.injection.matches],
            "",
        ]
    if match:
        lines += [
            f"## Match score {match.score:.0f}/100",
            "",
            "| criterion | weight | score | points |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {c.name} | {c.weight:.2f} | {c.score:.2f} | {c.points:.1f} |"
            for c in match.breakdown
        ]
        lines += ["", f"Rationale: {match.rationale}", ""]
    lines += [
        "## Claim verification",
        "",
        "| claim | label | text | evidence | quote |",
        "|---|---|---|---|---|",
    ]
    for c in draft.report.checks:
        ids = ", ".join(c.evidence_ids)
        lines.append(f"| {c.claim_id} | {c.label} | {_cell(c.text)} | {ids} | {_cell(c.quote)} |")
    if draft.report.fact_errors:
        lines += ["", "### Fact errors", *[f"- {e}" for e in draft.report.fact_errors]]
    if draft.critique_log:
        lines += ["", "### Revision history", *[f"```\n{c}\n```" for c in draft.critique_log]]
    if research:
        lines += [
            "",
            f"## Company research ({research.confidence} confidence)",
            "",
            research.summary,
            "",
        ]
        lines += [f"- {f.text} ([source]({f.source_url}))" for f in research.facts]
    return "\n".join(lines) + "\n"
