"""Durable LangGraph checkpointer + Store for SQLite (default) or Postgres (DATABASE_URL).

Verified against langgraph-checkpoint-sqlite 3.1.3 / -postgres 3.2.1 (installed source):
SqliteSaver(conn), SqliteStore(conn).setup(), PostgresSaver(conn).setup(),
PostgresStore(conn).setup(). Both stores persist across processes.
"""

from __future__ import annotations

import inspect
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.store.base import BaseStore
from pydantic import BaseModel

from careergraph.config import Settings
from careergraph.domain import models as domain_models


def domain_types() -> list[type]:
    """Every Pydantic model and enum defined in careergraph.domain.models."""
    return [
        obj
        for _, obj in inspect.getmembers(domain_models, inspect.isclass)
        if obj.__module__ == domain_models.__name__ and issubclass(obj, BaseModel | Enum)
    ]


def make_serializer() -> JsonPlusSerializer:
    """Serializer that only deserialises LangGraph's safe types plus our domain types.

    Without an explicit allowlist, langgraph 1.2 deserialises any type with a warning and
    announces it will block unregistered types in a future version.
    """
    return JsonPlusSerializer(allowed_msgpack_modules=domain_types())


@dataclass
class GraphPersistence:
    """Checkpointer and Store sharing one backend."""

    checkpointer: BaseCheckpointSaver[Any]
    store: BaseStore
    description: str


def sqlite_path(settings: Settings) -> Path:
    """LangGraph state lives next to (not inside) the app DB to avoid lock contention."""
    return settings.resolve(settings.data_dir) / f"langgraph-{settings.app_mode}.db"


@contextmanager
def open_persistence(settings: Settings) -> Iterator[GraphPersistence]:
    """Open checkpointer + store for the configured backend; closes connections on exit."""
    serde = make_serializer()
    if settings.is_postgres:
        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.store.postgres import PostgresStore
        from psycopg import Connection
        from psycopg.rows import dict_row

        url = settings.db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        conn: Any = cast(Any, Connection).connect(
            url, autocommit=True, prepare_threshold=0, row_factory=dict_row
        )
        try:
            saver = PostgresSaver(conn, serde=serde)
            store = PostgresStore(conn)
            saver.setup()
            store.setup()
            yield GraphPersistence(saver, store, "postgres")
        finally:
            conn.close()
        return
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.store.sqlite import SqliteStore

    path = sqlite_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        saver = SqliteSaver(conn, serde=serde)
        store = SqliteStore(conn)
        store.setup()
        yield GraphPersistence(saver, store, f"sqlite:{path.name}")
    finally:
        conn.close()
