# graphs/job_search/subgraphs/

## Purpose
Two loops that run once per approved job inside Send branches: `document_factory` (draft
<-> verify) and `research_company` (explicit ReAct with tools).

## How it works
- `document_factory`: `START -> draft_documents -> verify_documents -> (revise? draft : END)`.
  Edited drafts enter at `verify_documents` (`mode="verify"`) and are never auto-redrafted.
  The loop stops when every claim is supported and facts are consistent, or after
  `MAX_REVISIONS`; the draft then carries `flagged` into the review pause.
- `research_company`: `plan_query` (model chooses a tool) -> `tools` (`ToolNode` with
  `web_search`, `fetch_page`) -> `reflect_or_stop` (step/token/page limits) -> back to
  `plan_query` or `write_brief`. Fetches are limited to the company's configured domain; the
  brief keeps only facts citing pages that were actually read.

## Key files
`document_factory.py`, `research_company.py`, `research_tools.py`, `state.py`.

## LangGraph concepts used and why
Subgraphs with their own state schema, compiled once and invoked from branch nodes
(`DOCUMENT_FACTORY.invoke(branch, context=...)`); they inherit the parent's checkpointer.
`ToolNode` executes tool calls; tools receive `ToolRuntime` (services via `.context`, the
domain allowlist via `.state`). No interrupts inside subgraphs.

## Configuration
`MAX_REVISIONS`, `STRONG_MODEL`, `CHEAP_MODEL`, `ENABLE_COMPANY_RESEARCH`, `SEARCH_PROVIDER`,
`RESEARCH_MAX_STEPS`, `RESEARCH_MAX_TOKENS`, `search.yaml` `companies`.

## How to test
`uv run pytest tests/test_routing.py tests/test_research.py`.

## Design decisions and trade-offs
An explicit ReAct loop instead of `create_agent`: every step, limit and tool is visible and
testable (ADR 0001). The cost is a few more lines than a prebuilt agent.

## Extending and gotchas
A new tool needs SafeFetcher for any network access and must return JSON strings.
