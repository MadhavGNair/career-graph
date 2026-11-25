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


def main() -> None:
    """Console entry point: render config errors without tracebacks."""
    try:
        app()
    except ConfigErrors as exc:
        console.print(f"[red]{exc.render()}[/]")
        sys.exit(2)


if __name__ == "__main__":
    main()
