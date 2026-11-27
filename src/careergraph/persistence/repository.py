"""Repository: every read/write of application data. Also the durable usage ledger."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from careergraph.domain.models import (
    AnalyzedJob,
    DocumentDraft,
    MatchResult,
    ProfileSnapshot,
    ShortlistDecision,
)
from careergraph.domain.status import ApplicationStatus, check_transition
from careergraph.llm.usage import UsageRecord
from careergraph.persistence.db import (
    Analysis,
    Application,
    ApplicationEvent,
    DecisionRow,
    LLMUsage,
    MatchRow,
    Posting,
    ProfileCache,
    Requirement,
    Run,
    init_db,
    utcnow,
)


class Repository:
    """Thin, typed data access. Thread-safe for Send branches (one session per call)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._lock = threading.Lock()
        init_db(engine)

    def _s(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    # ------------------------------------------------------------------ usage ledger
    def record(self, rec: UsageRecord) -> None:
        """Persist one LLM call's usage."""
        with self._lock, self._s() as s:
            s.add(
                LLMUsage(
                    run_id=rec.run_id,
                    ts=rec.ts,
                    task=rec.task,
                    tier=rec.tier,
                    model=rec.model,
                    input_tokens=rec.input_tokens,
                    output_tokens=rec.output_tokens,
                    cache_read_tokens=rec.cache_read_tokens,
                    cache_write_tokens=rec.cache_write_tokens,
                    usd=rec.usd,
                    fake=rec.fake,
                )
            )
            s.commit()

    def _totals(self, *where: Any) -> tuple[int, float]:
        with self._s() as s:
            row = s.execute(
                select(
                    func.coalesce(func.sum(LLMUsage.input_tokens + LLMUsage.output_tokens), 0),
                    func.coalesce(func.sum(LLMUsage.usd), 0.0),
                ).where(*where)
            ).one()
        return int(row[0] or 0), float(row[1] or 0.0)

    def run_totals(self, run_id: str) -> tuple[int, float]:
        """(tokens, usd) of one run/thread."""
        return self._totals(LLMUsage.run_id == run_id)

    def day_totals(self, day: date) -> tuple[int, float]:
        """(tokens, usd) of a UTC day."""
        start = datetime.combine(day, time.min, tzinfo=UTC)
        return self._totals(LLMUsage.ts >= start, LLMUsage.ts < start + timedelta(days=1))

    def usage_by_run(self) -> list[dict[str, Any]]:
        """Per-run token and USD totals, newest first (Insights page)."""
        with self._s() as s:
            rows = s.execute(
                select(
                    LLMUsage.run_id,
                    func.min(LLMUsage.ts),
                    func.sum(LLMUsage.input_tokens),
                    func.sum(LLMUsage.output_tokens),
                    func.sum(LLMUsage.usd),
                    func.count(),
                    func.max(LLMUsage.fake.cast(Integer)),
                )
                .group_by(LLMUsage.run_id)
                .order_by(func.min(LLMUsage.ts).desc())
            ).all()
        return [
            {
                "run_id": r[0],
                "started": r[1],
                "input_tokens": int(r[2] or 0),
                "output_tokens": int(r[3] or 0),
                "usd": r[4],
                "calls": int(r[5]),
                "fake": bool(r[6]),
            }
            for r in rows
        ]

    def usage_by_task(self, run_id: str) -> dict[str, int]:
        """Tokens per task for one run."""
        with self._s() as s:
            rows = s.execute(
                select(LLMUsage.task, func.sum(LLMUsage.input_tokens + LLMUsage.output_tokens))
                .where(LLMUsage.run_id == run_id)
                .group_by(LLMUsage.task)
            ).all()
        return {r[0]: int(r[1]) for r in rows}

    # ------------------------------------------------------------------ runs
    def upsert_run(self, thread_id: str, **fields: Any) -> None:
        """Create or update a run row."""
        with self._lock, self._s() as s:
            run = s.get(Run, thread_id) or Run(thread_id=thread_id, mode=fields.get("mode", ""))
            for k, v in fields.items():
                setattr(run, k, v)
            run.updated_at = utcnow()
            s.add(run)
            s.commit()

    def get_run(self, thread_id: str) -> Run | None:
        """One run or None."""
        with self._s() as s:
            return s.get(Run, thread_id)

    def list_runs(self, status: str | None = None) -> list[Run]:
        """Runs, newest first, optionally filtered by status."""
        with self._s() as s:
            q = select(Run).order_by(Run.created_at.desc())
            if status:
                q = q.where(Run.status == status)
            return list(s.scalars(q))

    # ------------------------------------------------------------------ profile
    def get_profile(self, key: str) -> ProfileSnapshot | None:
        """Cached extraction for a combined document hash."""
        with self._s() as s:
            row = s.get(ProfileCache, key)
            return ProfileSnapshot.model_validate(row.snapshot) if row else None

    def put_profile(self, key: str, snap: ProfileSnapshot) -> None:
        """Cache an extraction."""
        with self._lock, self._s() as s:
            s.merge(ProfileCache(key=key, snapshot=snap.model_dump(mode="json")))
            s.commit()

    def latest_profile(self) -> ProfileSnapshot | None:
        """Most recent cached extraction (for `make jobs` without re-ingesting)."""
        with self._s() as s:
            row = s.scalars(select(ProfileCache).order_by(ProfileCache.created_at.desc())).first()
            return ProfileSnapshot.model_validate(row.snapshot) if row else None

    # ------------------------------------------------------------------ postings/analyses
    def cached_analysis(self, content_hash: str) -> AnalyzedJob | None:
        """Analysis for a posting content hash, if already done."""
        with self._s() as s:
            row = s.get(Analysis, content_hash)
            return AnalyzedJob.model_validate(row.data) if row else None

    def cached_analysis_by_posting(self, posting_id: str) -> AnalyzedJob | None:
        """Latest analysis stored for a posting id (offline re-scoring for evals)."""
        with self._s() as s:
            q = (
                select(Analysis)
                .where(Analysis.posting_id == posting_id)
                .order_by(Analysis.created_at.desc())
            )
            row = s.scalars(q).first()
            return AnalyzedJob.model_validate(row.data) if row else None

    def save_analysis(self, job: AnalyzedJob) -> None:
        """Persist posting, analysis and normalised requirements (for the trend chart)."""
        p = job.posting
        with self._lock, self._s() as s:
            s.merge(
                Posting(
                    id=p.id,
                    source=p.source,
                    company=p.company,
                    title=p.title,
                    location=p.location,
                    url=p.url,
                    posted_at=p.posted_at,
                    content_hash=p.content_hash,
                )
            )
            s.merge(
                Analysis(
                    content_hash=p.content_hash,
                    posting_id=p.id,
                    data=job.model_dump(mode="json"),
                    injection_flag=job.injection_flag,
                )
            )
            s.query(Requirement).filter(Requirement.posting_id == p.id).delete()
            for kind, skills in (
                ("must", job.analysis.must_have),
                ("nice", job.analysis.nice_to_have),
            ):
                for skill in skills:
                    s.add(
                        Requirement(posting_id=p.id, skill=skill, kind=kind, posted_at=p.posted_at)
                    )
            s.commit()

    def skills_trend(self, top: int = 8) -> list[dict[str, Any]]:
        """Weekly counts of the most demanded skills (Insights page)."""
        with self._s() as s:
            rows = s.execute(select(Requirement.skill, Requirement.posted_at)).all()
        totals = Counter(r[0] for r in rows)
        keep = {k for k, _ in totals.most_common(top)}
        weekly: Counter[tuple[date, str]] = Counter()
        for skill, posted in rows:
            if skill in keep and posted is not None:
                weekly[(posted - timedelta(days=posted.weekday()), skill)] += 1
        return [{"week": w, "skill": k, "count": c} for (w, k), c in sorted(weekly.items())]

    # ------------------------------------------------------------------ matches/decisions
    def save_matches(self, thread_id: str, results: list[MatchResult]) -> None:
        """Store scored matches for a run."""
        with self._lock, self._s() as s:
            for r in results:
                s.add(
                    MatchRow(
                        thread_id=thread_id,
                        posting_id=r.job_id,
                        score=r.score,
                        shortlisted=r.shortlisted,
                        data=r.model_dump(mode="json"),
                    )
                )
            s.commit()

    def save_decisions(
        self, thread_id: str, items: list[tuple[ShortlistDecision, dict[str, Any]]]
    ) -> None:
        """Store shortlist decisions with job title/company/score for later export."""
        with self._lock, self._s() as s:
            for d, meta in items:
                s.add(
                    DecisionRow(
                        thread_id=thread_id,
                        posting_id=d.job_id,
                        decision=d.decision,
                        reason_tags=[str(t) for t in d.reason_tags],
                        note=d.note,
                        **meta,
                    )
                )
            s.commit()

    def decided_job_ids(self) -> set[str]:
        """Jobs with a final (approve/reject) decision; they are not shortlisted again."""
        with self._s() as s:
            q = select(DecisionRow.posting_id).where(
                DecisionRow.decision.in_(["approve", "reject"])
            )
            return set(s.scalars(q))

    def all_decisions(self) -> list[DecisionRow]:
        """Every decision, oldest first (eval export)."""
        with self._s() as s:
            return list(s.scalars(select(DecisionRow).order_by(DecisionRow.created_at)))

    # ------------------------------------------------------------------ applications
    def save_ready(
        self,
        draft: DocumentDraft,
        *,
        company: str,
        role: str,
        url: str,
        out_dir: str,
        thread_id: str,
    ) -> None:
        """Record an application as READY (CareerGraph never applies for you)."""
        with self._lock, self._s() as s:
            app = s.get(Application, draft.job_id)
            prev = app.status if app else ""
            app = app or Application(job_id=draft.job_id, company=company, role=role, status="")
            app.status, app.url, app.out_dir, app.thread_id = (
                ApplicationStatus.READY,
                url,
                out_dir,
                thread_id,
            )
            app.draft, app.updated_at = draft.model_dump(mode="json"), utcnow()
            s.add(app)
            s.add(
                ApplicationEvent(
                    job_id=draft.job_id, from_status=prev, to_status=ApplicationStatus.READY
                )
            )
            s.commit()

    def set_status(self, job_id: str, new: ApplicationStatus, note: str = "") -> Application:
        """Change status with transition validation.

        Raises:
            KeyError: unknown job id.
            InvalidTransition: the change is not allowed.
        """
        with self._lock, self._s() as s:
            app = s.get(Application, job_id)
            if app is None:
                raise KeyError(job_id)
            check_transition(ApplicationStatus(app.status), new)
            s.add(ApplicationEvent(job_id=job_id, from_status=app.status, to_status=new, note=note))
            app.status, app.updated_at = new, utcnow()
            s.commit()
            return app

    def get_application(self, job_id: str) -> Application | None:
        """One application or None."""
        with self._s() as s:
            return s.get(Application, job_id)

    def list_applications(self) -> list[Application]:
        """All applications, most recently updated first."""
        with self._s() as s:
            return list(s.scalars(select(Application).order_by(Application.updated_at.desc())))

    def application_events(self, job_id: str) -> list[ApplicationEvent]:
        """Status history of one application."""
        with self._s() as s:
            q = (
                select(ApplicationEvent)
                .where(ApplicationEvent.job_id == job_id)
                .order_by(ApplicationEvent.id)
            )
            return list(s.scalars(q))
