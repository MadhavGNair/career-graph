"""Markdown + JSON eval reports and label export."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from careergraph.evals.suites import SuiteResult
from careergraph.persistence.repository import Repository

DISCLAIMER = (
    "Fake-mode evals use the deterministic fake LLM: they verify pipeline logic (parsing, "
    "normalisation, routing, scoring, verification plumbing), NOT model quality."
)


def write_reports(results: list[SuiteResult], out_dir: Path) -> tuple[Path, Path]:
    """Write eval-<mode>-<timestamp>.{json,md}; return both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    mode = results[0].mode if results else "none"
    base = out_dir / f"eval-{mode}-{stamp}"
    payload: dict[str, Any] = {
        "generated_at": stamp,
        "mode": mode,
        "disclaimer": DISCLAIMER
        if mode == "fake"
        else "Live mode: real model outputs on fictional fixtures.",
        "suites": [
            {
                "suite": r.suite,
                "metrics": r.metrics,
                "thresholds": r.thresholds,
                "passed": r.passed,
                "failures": r.failures,
                "notes": r.notes,
                "details": r.details,
            }
            for r in results
        ],
    }
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str))
    lines = [f"# CareerGraph eval report ({mode})", "", f"_{payload['disclaimer']}_", ""]
    for r in results:
        lines += [
            f"## {r.suite}: {'PASS' if r.passed else 'FAIL'}",
            "",
            "| metric | value | threshold |",
            "|---|---|---|",
        ]
        lines += [
            f"| {k} | {v:.3f} | {r.thresholds.get(k, '-')} |" for k, v in sorted(r.metrics.items())
        ]
        lines += [f"- {n}" for n in r.notes] + [""]
    base.with_suffix(".md").write_text("\n".join(lines))
    return base.with_suffix(".json"), base.with_suffix(".md")


def export_labels(repo: Repository, out: Path) -> int:
    """Turn your approve/reject decisions into a triage-label file (latest decision per job)."""
    labels: dict[str, dict[str, Any]] = {}
    for d in repo.all_decisions():
        if d.decision in ("approve", "reject"):
            labels[d.posting_id] = {
                "label": d.decision,
                "tags": list(d.reason_tags),
                "title": d.title,
                "company": d.company,
            }
    out.parent.mkdir(parents=True, exist_ok=True)
    header = "# Exported from your CareerGraph decisions. Personal data: keep out of git.\n"
    out.write_text(header + yaml.safe_dump(labels, sort_keys=True, allow_unicode=True))
    return len(labels)
