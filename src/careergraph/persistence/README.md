# persistence/

## Purpose
Durable state: the application DB (postings, analyses, matches, decisions, applications,
LLM usage) and LangGraph's checkpointer + Store. SQLite by default, Postgres when
`DATABASE_URL` points at it.

## How it works
```mermaid
flowchart LR
  subgraph SQLite default
    A[(data/careergraph-<mode>.db<br/>SQLAlchemy app tables)]
    L[(data/langgraph-<mode>.db<br/>SqliteSaver + SqliteStore)]
  end
  subgraph Postgres optional
    P[(one database: app tables + PostgresSaver + PostgresStore)]
  end
```
- App tables: `create_all` + a `schema_version` row (Alembic is the planned next step, ADR 0003).
- Checkpointer: every super-step of every thread is saved, which is what makes pauses,
  crash recovery, budget halts and time travel work.
- Store: cross-thread memory (learned preferences).
- Serializer: `JsonPlusSerializer(allowed_msgpack_modules=<all domain types>)`. langgraph 1.2
  warns that unregistered types will be blocked in a future version; registering ours now
  makes deserialisation strict (only LangGraph's safe types + ours).

## Key files
`db.py` (models, engine with WAL + busy timeout), `repository.py` (all queries; also the
durable usage ledger for budgets), `checkpoint.py` (saver/store factory, serializer).

## LangGraph concepts used and why
**Checkpointer** (`SqliteSaver`/`PostgresSaver`): durable threads, `interrupt()`/resume,
`get_state_history`, `update_state` forks. **Store** (`SqliteStore`/`PostgresStore`).

## Configuration
`DATABASE_URL` (empty = SQLite under `DATA_DIR`), `DATA_DIR`.

## How to run and test
`uv run pytest tests/test_persistence.py tests/test_service.py`. Postgres was **not**
exercised in this environment's tests; the code paths use the verified constructors and
`setup()` calls (see `docs/live-mode.md` for a local Postgres check with docker compose).

## Design decisions and trade-offs
- Demo and live use separate SQLite files so demo data never pollutes your real history.
- LangGraph state is in its own SQLite file to avoid writer contention with app tables.
- The saver and store use separate SQLite connections: `SqliteStore` manages its own
  transactions and needs autocommit (`isolation_level=None`), as in its `from_conn_string`.

## Extending and gotchas
Changing a domain model that is stored in checkpoints affects resuming old threads; add
fields with defaults. New stored types must live in `domain/models.py` to be allow-listed.
