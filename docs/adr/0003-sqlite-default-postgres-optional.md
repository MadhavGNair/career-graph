# ADR 0003: SQLite by default, Postgres optional; durable Store in both

Status: accepted (2026-11-22)

## Context
The checkpointer and the Store must be durable. A personal tool should start with zero
infrastructure.

## Decision
- Default: SQLite files under `DATA_DIR`: `careergraph-<mode>.db` (app tables) and
  `langgraph-<mode>.db` (`SqliteSaver` + `SqliteStore`).
- `DATABASE_URL=postgresql://...`: app tables, `PostgresSaver` and `PostgresStore` share one DB.
- A persistent SQLite Store **exists** (`langgraph.store.sqlite.SqliteStore`, verified in
  langgraph-checkpoint-sqlite 3.1.3), so no custom preferences table was needed.
- Schema: SQLAlchemy `create_all` + a `schema_version` row. Next step: Alembic migrations once
  the schema changes after first real use.

## Consequences
Single-writer SQLite limits deployments to one node (fine for k3s on one VM). The saver and
store use separate SQLite connections (the Store needs autocommit). Postgres was verified
locally against `postgres:17-alpine`.
