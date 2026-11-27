"""`careergraph` command line. Thin: every command calls the service layer or a helper."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from careergraph.config import ConfigErrors, load_app_config, load_settings
from careergraph.doctor import run_checks
from careergraph.domain.models import ReasonTag, ShortlistDecision
from careergraph.observability import setup_logging
from careergraph.service.api import CareerGraphService, RunOutcome

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="CareerGraph job-search copilot",
)
console = Console()
_STYLE = {"OK": "green", "WARN": "yellow", "FAIL": "red"}


@contextmanager
def service() -> Iterator[CareerGraphService]:
    """Open the service with logging configured; errors become friendly messages."""
    settings = load_settings()
    setup_logging(settings)
    svc = CareerGraphService(load_app_config(settings))
    try:
        yield svc
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None
    finally:
        svc.close()


def on_event(node: str, update: dict[str, Any]) -> None:
    """Print one line per finished node."""
    detail = ""
    if node == "find_jobs" and "funnel" in update:
        f = update["funnel"]
        detail = (
            f"fetched {f['fetched']}, new {f['new']}, cached {f['cached']}, "
            f"duplicates {len(f['duplicates'])}"
        )
    elif node == "match_jobs":
        detail = (
            f"{len(update.get('shortlist', []))} shortlisted of {len(update.get('matches', []))}"
        )
    elif node == "extract_jobs":
        detail = ", ".join(update.get("analyses", {}))
    console.print(f"  [green]done[/] {node} [dim]{detail}[/]")


def report(outcome: RunOutcome) -> None:
    """Explain an outcome and the next command."""
    t = outcome.thread_id
    if outcome.status == "waiting_shortlist":
        console.print(f"[bold]Paused for your shortlist.[/] thread: [cyan]{t}[/]")
        print_shortlist(outcome.payload["items"] if outcome.payload else [])
        console.print(f"Next: make approve THREAD={t} JOBS=<id1>,<id2> [REJECT=<id>:<tag>]")
    elif outcome.status == "waiting_review":
        console.print(f"[bold]Paused for document review.[/] thread: [cyan]{t}[/]")
        print_review(outcome.payload or {})
        console.print(f"Next: make review THREAD={t}   (or edit/regenerate in the UI)")
    elif outcome.status == "waiting_mock_interview" and outcome.payload:
        q = outcome.payload["question"]
        turn, of = outcome.payload["turn"], outcome.payload["of"]
        console.print(f"[bold]Mock interview {turn}/{of}[/] ({q['kind']})")
        console.print(f"  {q['text']}")
        if outcome.payload["story_hints"]:
            console.print(
                f"  [dim]Your STAR stories: {'; '.join(outcome.payload['story_hints'])}[/]"
            )
        console.print(
            f'Next: careergraph interview answer {t} "<your answer>"   ("/stop" to finish)'
        )
    elif outcome.status == "completed":
        console.print(f"[green]Completed[/] {t}\n{outcome.summary}")
    elif outcome.status == "halted_budget":
        console.print(
            f"[yellow]Halted by budget[/] {t}: {outcome.error}\nNext: make resume THREAD={t}"
        )
    else:
        console.print(
            f"[red]Failed[/] {t}: {outcome.error}\n"
            f"State is checkpointed. Next: make resume THREAD={t}"
        )


def print_shortlist(items: list[dict[str, Any]]) -> None:
    """Rich table of shortlist rows."""
    table = Table(show_lines=False)
    for col in ("#", "job id", "score", "title", "company", "matched", "missing", "flags"):
        table.add_column(col, overflow="fold")
    for i in items:
        flags = ("INJECTION " if i["injection_flag"] else "") + " ".join(i["red_flags"])
        table.add_row(
            str(i["rank"]),
            i["job_id"],
            f"{i['score']:.0f}",
            i["title"],
            i["company"],
            ", ".join(m["skill"] for m in i["matched"]),
            ", ".join(m["skill"] for m in i["missing"]),
            f"[red]{flags}[/]" if flags else "",
        )
    console.print(table)


def print_review(payload: dict[str, Any]) -> None:
    """Summary of drafts under review."""
    for d in payload.get("drafts", []):
        mark = "[red]FLAGGED[/]" if d["flagged"] else "[green]ok[/]"
        console.print(
            f"  {d['job_id']}: {mark} revisions={d['revision_count']} "
            f"unsupported={d['unsupported']} partial={d['partial']} "
            f"fact_errors={len(d['fact_errors'])}"
        )


@app.command()
def doctor() -> None:
    """Check .env, mode, keys, LaTeX, DB, profile, config and worst-case spend."""
    checks = run_checks()
    table = Table(show_header=True, header_style="bold")
    for col in ("status", "check", "detail", "next action"):
        table.add_column(col, overflow="fold")
    for c in checks:
        table.add_row(f"[{_STYLE[c.status]}]{c.status}[/]", c.name, c.detail, c.action)
    console.print(table)
    if any(c.status == "FAIL" for c in checks):
        raise typer.Exit(1)


@app.command("validate-config")
def validate_config() -> None:
    """Validate .env and every config/*.yaml file."""
    load_app_config(load_settings())
    console.print("[green]config OK[/]")


@app.command()
def run() -> None:
    """Run the full graph until the first pause (cron uses this too)."""
    with service() as svc:
        console.print(
            f"[bold]CareerGraph run[/] mode={svc.cfg.settings.app_mode} store={svc.persistence}"
        )
        report(svc.start_run(on_event))


@app.command()
def resume(thread: str) -> None:
    """Continue a thread halted by a budget cap or a crash."""
    with service() as svc:
        report(svc.resume(thread, None, on_event))


@app.command()
def pending() -> None:
    """List threads waiting for input or resumable."""
    with service() as svc:
        rows = svc.list_pending()
        if not rows:
            console.print("Nothing pending.")
        for p in rows:
            console.print(
                f"  [cyan]{p.thread_id}[/] waiting for {p.waiting_for} "
                f"({p.items} items) {p.note[:80]}"
            )


@app.command()
def shortlist(thread: str) -> None:
    """Show the shortlist of a paused thread."""
    with service() as svc:
        print_shortlist(svc.get_shortlist(thread))


def parse_cli_decisions(jobs: str, reject: str, defer: str) -> list[ShortlistDecision]:
    """`a,b` approve; `c:too_junior+salary,d` reject with tags; `e` defer."""
    out: list[ShortlistDecision] = []
    for j in filter(None, (x.strip() for x in jobs.split(","))):
        out.append(ShortlistDecision(job_id=j, decision="approve"))
    for item in filter(None, (x.strip() for x in reject.split(","))):
        job_id, _, tags = item.partition(":")
        out.append(
            ShortlistDecision(
                job_id=job_id,
                decision="reject",
                reason_tags=[ReasonTag(t) for t in tags.split("+") if t],
            )
        )
    for j in filter(None, (x.strip() for x in defer.split(","))):
        out.append(ShortlistDecision(job_id=j, decision="defer"))
    return out


@app.command()
def approve(
    thread: str,
    jobs: str = typer.Option("", help="comma-separated job ids to approve"),
    reject: str = typer.Option("", help="id[:tag+tag],... to reject"),
    defer: str = typer.Option("", help="comma-separated job ids to defer"),
) -> None:
    """Resume the shortlist pause. Jobs you do not mention are deferred."""
    with service() as svc:
        report(svc.approve_shortlist(thread, parse_cli_decisions(jobs, reject, defer), on_event))


@app.command()
def profile() -> None:
    """Re-ingest documents/GitHub and re-extract evidence (nodes 1-2)."""
    with service() as svc:
        snap = svc.run_profile(force=True)
        console.print(f"{len(snap.evidence)} evidence items, {len(snap.skills)} skills")
        for e in snap.evidence:
            console.print(f"  {e.id} [{e.kind}] {e.text[:90]} [dim]{', '.join(e.skills)}[/]")


@app.command()
def jobs() -> None:
    """Find, analyse and score jobs (nodes 1-5) without pausing."""
    from careergraph.matching.payload import shortlist_items

    with service() as svc:
        out = svc.run_jobs()
        console.print(
            json.dumps({k: v for k, v in out["funnel"].items() if k != "duplicates"}, default=str)
        )
        print_shortlist(shortlist_items(out["matches"], out["shortlist"], out["analyses"]))


@app.command()
def history(thread: str) -> None:
    """Checkpoint history of a thread (newest first)."""
    with service() as svc:
        table = Table()
        for col in ("checkpoint", "step", "source", "wrote", "next"):
            table.add_column(col, overflow="fold")
        for h in svc.history(thread):
            table.add_row(
                h.checkpoint_id, str(h.step), h.source, ",".join(h.writes), ",".join(h.next)
            )
        console.print(table)


@app.command()
def fork(
    thread: str,
    checkpoint: str,
    set_: str = typer.Option("", "--set", help='JSON state update, e.g. \'{"shortlist": ["id"]}\''),
    as_node: str = typer.Option("", help="apply the update as if this node wrote it"),
) -> None:
    """Replay a thread from a checkpoint, optionally editing state first."""
    updates = json.loads(set_) if set_ else None
    with service() as svc:
        report(svc.fork(thread, checkpoint, updates, as_node or None, on_event))


@app.command()
def review(
    thread: str,
    action: str = typer.Option("approve-all", help="approve-all | reject-all"),
    override: bool = typer.Option(False, help="also approve drafts still flagged after revisions"),
) -> None:
    """Resume the review pause (use the UI to edit or regenerate single drafts)."""
    from careergraph.domain.models import ReviewAction

    with service() as svc:
        drafts = svc.get_review(thread)["drafts"]
        actions: list[ReviewAction] = []
        for d in drafts:
            if action == "reject-all":
                actions.append(
                    ReviewAction(job_id=d["job_id"], action="reject", reason="rejected via CLI")
                )
            elif d["flagged"] and not override:
                console.print(
                    f"[yellow]{d['job_id']} is flagged; rejecting (pass --override to approve)[/]"
                )
                actions.append(ReviewAction(job_id=d["job_id"], action="reject", reason="flagged"))
            else:
                actions.append(
                    ReviewAction(job_id=d["job_id"], action="approve", override=override)
                )
        report(svc.review_documents(thread, actions, on_event))


@app.command()
def render(job: str) -> None:
    """Re-render a saved application's .tex (and PDF if an engine exists)."""
    with service() as svc:
        for r in svc.render(job):
            console.print(f"{r.engine}: {r.message}")


@app.command("render-sample")
def render_sample() -> None:
    """Render the templates with sample data into OUTPUT_DIR/sample/."""
    with service() as svc:
        out, results = svc.render_sample()
        console.print(f"wrote {out}/cv.tex and letter.tex")
        for r in results:
            console.print(f"  {r.engine}: {r.message}")


tracker_app = typer.Typer(help="Tracked applications")
app.add_typer(tracker_app, name="tracker")


@tracker_app.command("list")
def tracker_list() -> None:
    """List applications and their status."""
    with service() as svc:
        apps = svc.list_applications()
        if not apps:
            console.print("No applications yet.")
        for a in apps:
            console.print(f"  [cyan]{a.job_id}[/] {a.status:10} {a.company}: {a.role}  {a.out_dir}")


@tracker_app.command("set")
def tracker_set(job: str, status: str, note: str = "") -> None:
    """Change status via the tracker graph (validated; "interview" starts prep + mock interview)."""
    with service() as svc:
        report(svc.change_status(job, status, note, on_event))


interview_app = typer.Typer(help="Mock interview (started by `tracker set <job> interview`)")
app.add_typer(interview_app, name="interview")


@interview_app.command("answer")
def interview_answer(thread: str, text: str) -> None:
    """Answer the current question; "/stop" ends the interview."""
    with service() as svc:
        report(svc.answer_mock(thread, text, on_event))


@app.command()
def demo() -> None:
    """Full end-to-end demo with the fake LLM and fixtures (resets demo data only)."""
    from careergraph.demo import run_demo

    setup_logging(load_settings(log_format="console", log_level="WARNING"))
    out = run_demo(console.print, on_event)
    if out.status != "completed":
        report(out)
        raise typer.Exit(1)
    console.print(
        "\n[bold green]Demo complete.[/] Open the UI with: [bold]make ui[/] (http://127.0.0.1:8501)"
    )


@app.command()
def ui() -> None:
    """Start the Streamlit UI bound to UI_HOST:UI_PORT."""
    import subprocess

    from careergraph.config import REPO_ROOT

    s = load_settings()
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(REPO_ROOT / "ui" / "app.py"),
        "--server.address",
        s.ui_host,
        "--server.port",
        str(s.ui_port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    console.print(f"UI on http://{s.ui_host}:{s.ui_port}")
    raise typer.Exit(subprocess.call(cmd))


eval_app = typer.Typer(help="Evaluation suites")
app.add_typer(eval_app, name="eval")


@eval_app.command("run")
def eval_run(
    suite: str = typer.Option("all", help="all | match | extraction | verifier | injection"),
    mode: str = typer.Option("fake", help="fake (CI gate) | live (real models, costs tokens)"),
    labels: str = typer.Option(
        "", help="match only: YAML from `eval export-labels` (offline re-score)"
    ),
) -> None:
    """Run eval suites, write Markdown + JSON reports, exit 1 if a fake-mode gate fails."""
    from pathlib import Path

    from careergraph.evals.report import DISCLAIMER, write_reports
    from careergraph.evals.suites import SUITES, SuiteResult, match_suite_from_labels, run_suite

    settings = load_settings()
    setup_logging(settings.model_copy(update={"log_level": "WARNING"}))
    if mode not in ("fake", "live"):
        raise typer.BadParameter("mode must be fake or live")
    results: list[SuiteResult] = []
    if labels:
        with service() as svc:
            results.append(match_suite_from_labels(svc.cfg, svc.repo, Path(labels), svc.store))
    else:
        for name in SUITES if suite == "all" else [suite]:
            results.append(run_suite(name, settings, mode))  # type: ignore[arg-type]
    if mode == "fake" and not labels:
        console.print(f"[dim]{DISCLAIMER}[/]")
    for r in results:
        status = "[green]PASS[/]" if r.passed else f"[red]FAIL {r.failures}[/]"
        metrics = ", ".join(f"{k}={v:.3f}" for k, v in sorted(r.metrics.items()))
        console.print(f"{r.suite:10} {status} {metrics}")
    js, md = write_reports(results, settings.resolve(settings.output_dir) / "evals")
    console.print(f"reports: {md} {js}")
    if not all(r.passed for r in results):
        raise typer.Exit(1)


@eval_app.command("export-labels")
def eval_export_labels(
    out: str = typer.Option("", help="output YAML (default OUTPUT_DIR/evals/my_labels.yaml)"),
) -> None:
    """Turn your own approve/reject decisions into an eval dataset."""
    from pathlib import Path

    from careergraph.evals.report import export_labels

    with service() as svc:
        s = svc.cfg.settings
        target = Path(out) if out else s.resolve(s.output_dir) / "evals" / "my_labels.yaml"
        n = export_labels(svc.repo, target)
        console.print(
            f"exported {n} labels to {target}. Re-score offline with: "
            f"careergraph eval run --suite match --labels {target}"
        )


@app.command("docs-graphs")
def docs_graphs(check: bool = typer.Option(False, help="fail if diagrams are stale (CI)")) -> None:
    """Regenerate Mermaid diagrams from the compiled graphs into the READMEs."""
    from careergraph.devtools.graph_docs import main as graph_docs_main

    raise typer.Exit(graph_docs_main(["--check"] if check else []))


def main() -> None:
    """Console entry point: render config errors without tracebacks."""
    try:
        app()
    except ConfigErrors as exc:
        console.print(f"[red]{exc.render()}[/]")
        sys.exit(2)


if __name__ == "__main__":
    main()
