"""Application tables (SQLAlchemy 2). Created with create_all plus a schema_version row;
Alembic is the planned next step (ADR 0003)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text, event
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = 1


def utcnow() -> datetime:
    """Timezone-aware now (UTC)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base."""


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    __tablename__ = "runs"
    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="job_search")
    mode: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), default="running")
    waiting_for: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    parent_thread: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProfileCache(Base):
    __tablename__ = "profile_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Posting(Base):
    __tablename__ = "postings"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    posting_id: Mapped[str] = mapped_column(String(128), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    injection_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    posting_id: Mapped[str] = mapped_column(String(128), index=True)
    skill: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class MatchRow(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    posting_id: Mapped[str] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Float)
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    posting_id: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(8))
    reason_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    company: Mapped[str] = mapped_column(String(200), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = "applications"
    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    company: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16))
    url: Mapped[str] = mapped_column(Text, default="")
    out_dir: Mapped[str] = mapped_column(Text, default="")
    thread_id: Mapped[str] = mapped_column(String(64), default="")
    draft: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(128), index=True)
    from_status: Mapped[str] = mapped_column(String(16), default="")
    to_status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    task: Mapped[str] = mapped_column(String(64))
    tier: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    fake: Mapped[bool] = mapped_column(Boolean, default=False)


def make_engine(url: str) -> Engine:
    """Create the engine; SQLite gets WAL mode and a busy timeout for concurrent branches."""
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return engine
    url = url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


def init_db(engine: Engine) -> None:
    """Create tables and record the schema version."""
    from sqlalchemy.orm import Session

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        if s.get(SchemaVersion, SCHEMA_VERSION) is None:
            s.add(SchemaVersion(version=SCHEMA_VERSION))
            s.commit()
