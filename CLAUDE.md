# CLAUDE.md: guide for coding agents

CareerGraph is a single-user LangGraph job-search copilot. Backend first. Read `PLAN.md` and
continue from the first unchecked box.

## Commands
- `make setup` (uv sync), `make lint`, `make typecheck`, `make test`, `make test-fast`, `make check`
- `make demo` full flow with fake LLM; `make doctor`; `make eval`; `make docs-graphs`
- CLI entry point: `uv run careergraph --help`

## Hard rules
- No live LLM calls, no keys, no network in tests/evals/demo. Fake LLM + fixtures only.
- Never write benchmark/eval/cost numbers into docs unless measured in-session; label fake-mode
  numbers as plumbing checks. Otherwise "not yet measured" + how to measure.
- Never use real personal data. Demo user "Sam Demo" and all companies are fictional.

## Conventions
- Python 3.12, fully typed, Google-style docstrings on public functions/classes.
- One file per graph node in `src/careergraph/graphs/job_search/nodes/`, < ~80 lines, header
  docstring: Purpose / Reads / Writes / Uses LLM? / Side effects / Config keys.
- `graphs/job_search/graph.py` is the readable table of contents; keep wiring there.
- Nodes never import adapters directly: they get services from the LangGraph runtime context
  (`runtime.context`), so demo and live share the exact same node code.
- Interrupts only at the top level, never inside Send branches or subgraphs.
- Every new env var goes into `Settings` and `.env.example` (with a comment); every YAML key into
  the config models and the YAML file (with a comment). The drift guard enforces this.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`).

## Verified third-party facts (re-verify when upgrading)
See `docs/architecture.md#verified-apis` for what was checked, against which version, and how.
