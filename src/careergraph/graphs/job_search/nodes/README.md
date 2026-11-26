# graphs/job_search/nodes/

## Purpose
One file per node. Each file is small (under ~80 lines) and starts with a header:
Purpose / Reads / Writes / Uses LLM? / Side effects / Config keys.

## How it works
A node is `def name(state, runtime: Runtime[Services]) -> dict` returning a partial state
update. Branch nodes (`extract_jobs`, `document_factory`, `research_company`) receive their
`Send` payload instead of the full state. Nodes call helpers (`matching/`, `documents/`,
`sources/`, `llm/`) and never construct adapters themselves: everything comes from
`runtime.context`, which is why demo and live run the same node code.

## Key files
Main graph: `ingest_profile`, `extract_profile`, `find_jobs`, `extract_jobs`, `match_jobs`,
`human_shortlist`, `research_company`, `select_evidence`, `document_factory`, `human_review`,
`render_latex`, `save_results`. Subgraph nodes: `draft_documents`, `verify_documents`,
`plan_query`, `reflect_or_stop`, `write_brief`.

## LangGraph concepts used and why
Runtime context injection, `interrupt()` in the two pause nodes, `runtime.store` for
preferences, subgraph invocation inside branch nodes. See `../README.md` for the full table.

## Configuration
Listed in each file's header.

## How to test
Unit-test nodes through tiny graphs (see `tests/test_jobs_nodes.py`) or through the service
(`tests/test_service.py`).

## Design decisions and trade-offs
Small nodes with explicit headers make the graph readable as documentation and keep each
LLM call isolated, testable and swappable.

## Extending and gotchas
Keep side effects after `interrupt()`; keep branch nodes free of interrupts.
