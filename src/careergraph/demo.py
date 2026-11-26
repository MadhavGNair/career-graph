"""`make demo`: the whole flow, end to end, with the fake LLM and the fictional Sam Demo.

The two human pauses are answered by a scripted "human" so you can watch every stage; run
`make run` + `make ui` to make the decisions yourself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from careergraph.config import load_app_config, load_settings
from careergraph.domain.models import ReasonTag, ReviewAction, ShortlistDecision
from careergraph.persistence.checkpoint import sqlite_path
from careergraph.service.api import CareerGraphService, RunOutcome

Printer = Callable[[str], None]


def scripted_decisions(items: list[dict[str, Any]], fabricate_job: str) -> list[ShortlistDecision]:
    """Approve the top 3 (always including the fabrication-scenario job if shortlisted), reject
    one data-science role as not_my_domain, defer the rest."""
    ids = [i["job_id"] for i in items]
    approve = ids[:3]
    if fabricate_job in ids and fabricate_job not in approve:
        approve = [fabricate_job, *ids[:2]]
    out = [ShortlistDecision(job_id=j, decision="approve") for j in approve]
    ds = next(
        (
            i["job_id"]
            for i in items
            if "Data Scientist" in i["title"] and i["job_id"] not in approve
        ),
        None,
    )
    if ds:
        out.append(
            ShortlistDecision(job_id=ds, decision="reject", reason_tags=[ReasonTag.NOT_MY_DOMAIN])
        )
    return out


def scripted_review(payload: dict[str, Any]) -> list[ReviewAction]:
    """Approve verified drafts; reject drafts still flagged (no override)."""
    return [
        ReviewAction(job_id=d["job_id"], action="reject", reason="still flagged after revisions")
        if d["flagged"]
        else ReviewAction(job_id=d["job_id"], action="approve")
        for d in payload["drafts"]
    ]


def run_demo(
    say: Printer, on_event: Callable[[str, dict[str, Any]], None] | None = None
) -> RunOutcome:
    """Reset demo state, run, answer both pauses, render, and return the final outcome."""
    settings = load_settings(app_mode="demo", enable_company_research=True)
    if not settings.is_postgres:  # demo state only; live data is never touched here
        app_db = Path(settings.db_url.split("///", 1)[-1])
        for base in (app_db, sqlite_path(settings)):
            for suffix in ("", "-wal", "-shm"):
                Path(f"{base}{suffix}").unlink(missing_ok=True)
    with CareerGraphService(load_app_config(settings)) as svc:
        say("1/4 Running: profile -> jobs -> matching (fake LLM, fixtures, no network)")
        out = svc.start_run(on_event)
        if out.status != "waiting_shortlist" or out.payload is None:
            return out
        items = out.payload["items"]
        decisions = scripted_decisions(items, settings.demo_fabricate_job)
        say(f"2/4 Shortlist pause ({len(items)} jobs). Scripted human decides:")
        for d in decisions:
            say(f"    {d.decision:8} {d.job_id} {' '.join(t.value for t in d.reason_tags)}")
        out = svc.approve_shortlist(out.thread_id, decisions, on_event)
        if out.status != "waiting_review" or out.payload is None:
            return out
        say("3/4 Review pause. Draft/verify loop results:")
        for d in out.payload["drafts"]:
            state = "FLAGGED" if d["flagged"] else "verified"
            say(f"    {d['job_id']}: {state}, revisions={d['revision_count']}")
            for entry in d["critique_log"]:
                say("      caught: " + entry.replace("\n", "\n      "))
        out = svc.review_documents(out.thread_id, scripted_review(out.payload), on_event)
        say("4/4 Rendered and saved:")
        say(out.summary)
        for app in svc.list_applications():
            say(f"    tracker: {app.job_id} -> {app.status} ({app.out_dir})")
        return out
