# tests/

## Purpose
Prove the system works without keys or network: unit tests per module, node and routing
tests, service tests, Streamlit smoke tests and a headless end-to-end demo test.

## How it works
Every test uses demo settings pointing at a temp directory (`tests/conftest.py`), the fake
LLM and the fixture HTTP transport. The developer's `.env` and shell variables are ignored.

| File | Covers |
|---|---|
| `test_config.py`, `test_drift_guard.py`, `test_doctor.py` | validation messages, documented/commented/used knobs, doctor |
| `test_llm.py` | budgets (token + USD), fake handlers vs gold, live client with mocks (json_schema, cache_control, effort, no temperature) |
| `test_skills.py`, `test_retrieval.py` | normalisation, hybrid search |
| `test_fetcher.py` | SSRF: scheme, allowlist, private IPs (v4/v6/mapped), redirects, caps, robots, rate limit, ETag |
| `test_sources.py`, `test_profile.py`, `test_jobs_nodes.py` | adapters on ATS fixtures, filters/dedupe vs gold, injection fixtures, fan-out, hash skip, cap |
| `test_matching.py`, `test_service.py` | scoring, dealbreakers, preferences, pause/resume across processes, budget halt, crash resume |
| `test_documents.py`, `test_routing.py`, `test_research.py` | fact checks, patches, routers, revision-cap termination, research limits |
| `test_latex.py` | escaping, golden-file render (`golden/`), overrides, graceful no-engine |
| `test_persistence.py` | serializer allowlist, schema version, status transitions |
| `test_ui.py` | AppTest smoke tests for every page + a full flow through the forms |
| `test_demo_smoke.py` | Definition-of-Done flow incl. forced fabrication, crash/resume and a time-travel fork |
| `test_evals.py`, `test_docs.py` | eval gates; README sections; diagram freshness |

## Key files
`conftest.py` (isolation), `helpers.py` (`demo_services`, `demo_service`), `golden/`.

## LangGraph concepts used and why
Tests exercise real compiled graphs with real SQLite checkpointers: interrupts, `Command`
resumes, `get_state_history`, `update_state` forks and Send fan-out are all asserted.

## Configuration
None needed. Markers: `slow` (end-to-end), `network`, `postgres` (both unused by default).

## How to run and test
`make test` (all), `make test-fast` (skips `slow`), `UPDATE_GOLDEN=1 uv run pytest
tests/test_latex.py` after an intentional template change.

## Design decisions and trade-offs
Deterministic fakes make exact assertions possible (which draft revises, which job is
shortlisted). They do not measure model quality; that is what `--mode live` evals are for.

## Extending and gotchas
LaTeX compilation and Postgres tests skip cleanly when the tool/DB is absent.
