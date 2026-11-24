"""`careergraph` command line. Thin: every command calls the service layer or a helper."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table

from careergraph.config import ConfigErrors, load_settings
from careergraph.doctor import run_checks

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="CareerGraph job-search copilot",
)
console = Console()

_STYLE = {"OK": "green", "WARN": "yellow", "FAIL": "red"}


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
    from careergraph.config import load_app_config

    load_app_config(load_settings())
    console.print("[green]config OK[/]")


def main() -> None:
    """Console entry point: render config errors without tracebacks."""
    try:
        app()
    except ConfigErrors as exc:
        console.print(f"[red]{exc.render()}[/]")
        sys.exit(2)


if __name__ == "__main__":
    main()
