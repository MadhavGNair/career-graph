"""CareerGraphService: the single in-process API used by the CLI and the Streamlit UI.

It owns the compiled graphs, the durable checkpointer/Store and the runtime services, and
turns graph executions into simple outcomes (waiting for shortlist / review, completed,
halted by budget, failed). Every run is a LangGraph thread, so it can be resumed later from
another process.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from careergraph.config import AppConfig, load_app_config
from careergraph.domain.models import (
    DocumentDraft,
    ProfileSnapshot,
    ReviewAction,
    ShortlistDecision,
)
from careergraph.domain.status import ApplicationStatus
from careergraph.graphs.job_search.graph import (
    build_job_search_graph,
    build_jobs_graph,
    build_profile_graph,
)
from careergraph.graphs.tracker.graph import build_tracker_graph
from careergraph.latex.compile import CompileResult
from careergraph.latex.render import template_dirs, write_and_compile
from careergraph.latex.sample import sample_documents
from careergraph.llm.budget import BudgetExceeded
from careergraph.observability import setup_tracing
from careergraph.persistence.checkpoint import open_persistence
from careergraph.persistence.db import Application
from careergraph.service.wiring import Services, build_services

log = logging.getLogger(__name__)

Status = Literal[
    "waiting_shortlist",
    "waiting_review",
    "waiting_mock_interview",
    "completed",
    "halted_budget",
    "failed",
]
EventHandler = Callable[[str, dict[str, Any]], None]


@dataclass
class RunOutcome:
    """What happened when a thread was started or resumed."""

    thread_id: str
    status: Status
    payload: dict[str, Any] | None = None
    error: str = ""
    summary: str = ""

    @property
    def waiting(self) -> bool:
        """True when the thread is paused for human input."""
        return self.status.startswith("waiting")


@dataclass
class PendingThread:
    """A thread that needs the human (or a resume after a halt)."""

    thread_id: str
    waiting_for: str
    created_at: datetime
    items: int = 0
    note: str = ""


@dataclass
class CheckpointInfo:
    """One entry of a thread's history (time travel)."""

    checkpoint_id: str
    step: int
    next: tuple[str, ...]
    source: str
    created_at: str
    writes: list[str] = field(default_factory=list)


def new_thread_id() -> str:
    """Readable, unique thread id."""
    return f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


class CareerGraphService:
    """Start, inspect, resume and fork job-search threads."""

    def __init__(self, cfg: AppConfig | None = None, services: Services | None = None) -> None:
        self.cfg = cfg or load_app_config()
        self.services = services or build_services(self.cfg)
        setup_tracing(self.cfg.settings)
        self._stack = ExitStack()
        persistence = self._stack.enter_context(open_persistence(self.cfg.settings))
        self.persistence = persistence.description
        self.store = persistence.store
        self.graph = build_job_search_graph().compile(
            checkpointer=persistence.checkpointer, store=persistence.store, name="job_search"
        )
        self.tracker_graph = build_tracker_graph().compile(
            checkpointer=persistence.checkpointer, store=persistence.store, name="tracker"
        )
        self.jobs_graph = build_jobs_graph().compile(store=persistence.store, name="jobs")
        self.profile_graph = build_profile_graph().compile(name="profile")

    def close(self) -> None:
        """Close DB connections."""
        self._stack.close()

    def __enter__(self) -> CareerGraphService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def repo(self) -> Any:
        """The application repository."""
        return self.services.repo

    # ------------------------------------------------------------------ execution
    @staticmethod
    def _config(thread_id: str, checkpoint_id: str | None = None) -> RunnableConfig:
        cfg: dict[str, Any] = {"thread_id": thread_id}
        if checkpoint_id:
            # get_state() returns configs without checkpoint_ns, but the savers require it
            # when writing (update_state), so it is always set for checkpoint-targeted configs.
            cfg["checkpoint_ns"] = ""
            cfg["checkpoint_id"] = checkpoint_id
        return {"configurable": cfg}

    def _graph_for(self, thread_id: str) -> Any:
        run = self.repo.get_run(thread_id)
        return self.tracker_graph if run is not None and run.kind == "tracker" else self.graph

    def _drive(
        self,
        thread_id: str,
        graph_input: Any,
        on_event: EventHandler | None,
        config: RunnableConfig | None = None,
    ) -> RunOutcome:
        config = config or self._config(thread_id)
        graph = self._graph_for(thread_id)
        self.repo.upsert_run(thread_id, status="running", waiting_for="", note="")
        try:
            for chunk in graph.stream(
                graph_input, config, context=self.services, stream_mode="updates"
            ):
                for node, update in chunk.items():
                    if node != "__interrupt__" and on_event is not None:
                        on_event(node, update or {})
        except BudgetExceeded as exc:
            self.repo.upsert_run(thread_id, status="halted_budget", note=str(exc))
            log.warning("run halted by budget", extra={"thread_id": thread_id})
            return RunOutcome(thread_id, "halted_budget", error=str(exc))
        except Exception as exc:
            log.exception("run failed", extra={"thread_id": thread_id})
            msg = f"{type(exc).__name__}: {exc}"
            self.repo.upsert_run(thread_id, status="failed", note=msg)
            return RunOutcome(thread_id, "failed", error=msg)
        return self._outcome(thread_id)

    def _outcome(self, thread_id: str) -> RunOutcome:
        state = self._graph_for(thread_id).get_state(self._config(thread_id))
        if state.interrupts:
            payload = dict(state.interrupts[0].value)
            kind = str(payload.get("type", "input"))
            self.repo.upsert_run(thread_id, status="waiting", waiting_for=kind)
            return RunOutcome(thread_id, f"waiting_{kind}", payload=payload)  # type: ignore[arg-type]
        summary = str(state.values.get("summary", ""))
        self.repo.upsert_run(thread_id, status="completed", waiting_for="", note=summary[:500])
        return RunOutcome(thread_id, "completed", summary=summary)

    def start_run(self, on_event: EventHandler | None = None) -> RunOutcome:
        """Run the full graph until the first pause (or the end)."""
        thread_id = new_thread_id()
        self.repo.upsert_run(thread_id, mode=self.cfg.settings.app_mode, kind="job_search")
        return self._drive(thread_id, {"run_id": thread_id}, on_event)

    def resume(
        self, thread_id: str, value: Any = None, on_event: EventHandler | None = None
    ) -> RunOutcome:
        """Resume a paused thread with a value, or continue a halted/crashed one with None.

        Raises:
            ValueError: unknown/finished thread, or a value is missing/unexpected.
        """
        state = self._graph_for(thread_id).get_state(self._config(thread_id))
        if not state.values:
            raise ValueError(f"unknown thread {thread_id}")
        if not state.next:
            raise ValueError(f"thread {thread_id} has already finished")
        if state.interrupts and value is None:
            raise ValueError(f"thread {thread_id} is waiting for input; use approve/review")
        if not state.interrupts and value is not None:
            raise ValueError(f"thread {thread_id} is not waiting for input")
        graph_input = Command(resume=value) if state.interrupts else None
        return self._drive(thread_id, graph_input, on_event)

    def pending_payload(self, thread_id: str) -> dict[str, Any] | None:
        """The interrupt payload a thread is waiting on, if any."""
        state = self._graph_for(thread_id).get_state(self._config(thread_id))
        return dict(state.interrupts[0].value) if state.interrupts else None

    def _expect(self, thread_id: str, kind: str) -> dict[str, Any]:
        payload = self.pending_payload(thread_id)
        if not payload or payload.get("type") != kind:
            raise ValueError(f"thread {thread_id} is not waiting for {kind}")
        return payload

    def get_shortlist(self, thread_id: str) -> list[dict[str, Any]]:
        """Ranked shortlist rows of a thread paused at human_shortlist."""
        return list(self._expect(thread_id, "shortlist")["items"])

    def approve_shortlist(
        self,
        thread_id: str,
        decisions: list[ShortlistDecision],
        on_event: EventHandler | None = None,
    ) -> RunOutcome:
        """Resume the shortlist pause.

        Raises:
            ValueError: thread not waiting, or a decision names a job not on the shortlist.
        """
        valid = {i["job_id"] for i in self.get_shortlist(thread_id)}
        unknown = sorted(d.job_id for d in decisions if d.job_id not in valid)
        if unknown:
            raise ValueError(f"not on the shortlist: {', '.join(unknown)}")
        return self.resume(thread_id, [d.model_dump(mode="json") for d in decisions], on_event)

    def get_review(self, thread_id: str) -> dict[str, Any]:
        """Drafts and verification reports of a thread paused at human_review."""
        return self._expect(thread_id, "review")

    def review_documents(
        self, thread_id: str, actions: list[ReviewAction], on_event: EventHandler | None = None
    ) -> RunOutcome:
        """Resume the review pause with one action per job."""
        valid = {d["job_id"] for d in self.get_review(thread_id)["drafts"]}
        unknown = sorted(a.job_id for a in actions if a.job_id not in valid)
        if unknown:
            raise ValueError(f"not under review: {', '.join(unknown)}")
        return self.resume(thread_id, [a.model_dump(mode="json") for a in actions], on_event)

    def list_pending(self) -> list[PendingThread]:
        """Threads waiting for input or resumable after a budget halt or failure."""
        out: list[PendingThread] = []
        for run in self.repo.list_runs():
            if run.kind not in ("job_search", "tracker") or run.status not in (
                "waiting",
                "halted_budget",
                "failed",
            ):
                continue
            state = self._graph_for(run.thread_id).get_state(self._config(run.thread_id))
            if not state.next:
                continue
            if state.interrupts:
                payload = state.interrupts[0].value
                n = len(payload.get("items") or payload.get("drafts") or [])
                out.append(
                    PendingThread(run.thread_id, str(payload.get("type")), run.created_at, n)
                )
            else:
                out.append(
                    PendingThread(
                        run.thread_id, f"resume ({run.status})", run.created_at, 0, run.note
                    )
                )
        return out

    # ------------------------------------------------------------------ time travel
    def history(self, thread_id: str, limit: int = 100) -> list[CheckpointInfo]:
        """Checkpoints of a thread, newest first."""
        out: list[CheckpointInfo] = []
        for snap in self._graph_for(thread_id).get_state_history(
            self._config(thread_id), limit=limit
        ):
            meta = snap.metadata or {}
            out.append(
                CheckpointInfo(
                    checkpoint_id=str((snap.config.get("configurable") or {}).get("checkpoint_id")),
                    step=int(meta.get("step", -1)),
                    next=tuple(snap.next),
                    source=str(meta.get("source", "")),
                    created_at=str(snap.created_at or ""),
                    writes=sorted((meta.get("writes") or {}).keys()),
                )
            )
        return out

    def fork(
        self,
        thread_id: str,
        checkpoint_id: str,
        updates: dict[str, Any] | None = None,
        as_node: str | None = None,
        on_event: EventHandler | None = None,
    ) -> RunOutcome:
        """Replay from a past checkpoint, optionally editing state first (time travel).

        The fork becomes the thread's latest branch; the old branch stays in history.
        """
        target = self._config(thread_id, checkpoint_id)
        graph = self._graph_for(thread_id)
        if not graph.get_state(target).values:
            raise ValueError(f"unknown checkpoint {checkpoint_id} for {thread_id}")
        config = graph.update_state(target, updates, as_node=as_node) if updates else target
        return self._drive(thread_id, None, on_event, config=config)

    # ------------------------------------------------------------------ partial runs
    def run_profile(self, force: bool = True) -> ProfileSnapshot:
        """Nodes 1-2 (`make profile`)."""
        tid = new_thread_id()
        self.repo.upsert_run(tid, mode=self.cfg.settings.app_mode, kind="profile")
        out = self.profile_graph.invoke(
            {"run_id": tid, "force_profile": force}, context=self.services
        )
        self.repo.upsert_run(tid, status="completed")
        profile: ProfileSnapshot = out["profile"]
        return profile

    def run_jobs(self) -> dict[str, Any]:
        """Nodes 1-5 without pausing (`make jobs`)."""
        tid = new_thread_id()
        self.repo.upsert_run(tid, mode=self.cfg.settings.app_mode, kind="jobs")
        out = self.jobs_graph.invoke({"run_id": tid}, context=self.services)
        self.repo.upsert_run(tid, status="completed")
        return out

    # ------------------------------------------------------------------ rendering
    def _template_dirs(self) -> list[Path]:
        s = self.cfg.settings
        return template_dirs(
            s.resolve(s.templates_dir), s.resolve(Path(self.cfg.profile.documents.dir))
        )

    def render(self, job_id: str) -> list[CompileResult]:
        """Re-render a saved application's documents (e.g. after editing a template).

        Raises:
            ValueError: unknown job id.
        """
        app = self.repo.get_application(job_id)
        if app is None:
            raise ValueError(f"no saved application for {job_id}")
        draft = DocumentDraft.model_validate(app.draft)
        s = self.cfg.settings
        _, _, results = write_and_compile(
            draft.cv,
            draft.letter,
            self._template_dirs(),
            Path(app.out_dir),
            s.latex_engine,
            s.latex_timeout_seconds,
        )
        return results

    def render_sample(self) -> tuple[Path, list[CompileResult]]:
        """Render the templates with sample data into OUTPUT_DIR/sample/."""
        s = self.cfg.settings
        cv, letter = sample_documents(self.cfg.profile)
        out = s.resolve(s.output_dir) / "sample"
        _, _, results = write_and_compile(
            cv, letter, self._template_dirs(), out, s.latex_engine, s.latex_timeout_seconds
        )
        return out, results

    # ------------------------------------------------------------------ tracker + insights
    def list_applications(self) -> list[Application]:
        """Tracked applications."""
        return self.repo.list_applications()

    def change_status(
        self, job_id: str, status: str, note: str = "", on_event: EventHandler | None = None
    ) -> RunOutcome:
        """Run the tracker graph: validated transition; "interview" triggers interview prep and a
        mock interview that pauses for each answer."""
        thread_id = f"track-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.repo.upsert_run(thread_id, mode=self.cfg.settings.app_mode, kind="tracker")
        payload = {"run_id": thread_id, "job_id": job_id, "new_status": status, "note": note}
        return self._drive(thread_id, payload, on_event)

    def answer_mock(
        self, thread_id: str, answer: str, on_event: EventHandler | None = None
    ) -> RunOutcome:
        """Answer the current mock-interview question ("/stop" ends the interview)."""
        self._expect(thread_id, "mock_interview")
        return self.resume(thread_id, answer, on_event)

    def set_status(self, job_id: str, status: str, note: str = "") -> Application:
        """Validated status change (e.g. ready -> applied)."""
        return self.repo.set_status(job_id, ApplicationStatus(status), note)

    def skills_trend(self) -> list[dict[str, Any]]:
        """Weekly demand for the most requested skills."""
        return self.repo.skills_trend()

    def usage_by_run(self) -> list[dict[str, Any]]:
        """Token (and USD if priced) usage per run."""
        return self.repo.usage_by_run()
