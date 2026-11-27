# ADR 0002: In-process service layer + Streamlit instead of an API + SPA

Status: accepted (2026-11-22)

## Context
One user, a handful of runs per day. An HTTP API plus a JavaScript frontend means two
deployables, auth between them, a build toolchain and more surface to secure.

## Decision
A Python `CareerGraphService` is the single entry point; the CLI and a Streamlit app call it
in-process. No FastAPI, no Node.

## Consequences
- Deploy one image; the UI is plain Python and testable with `AppTest`.
- Streamlit reruns whole pages and is not multi-user; acceptable here.
- To add an API later: wrap service methods one-to-one in FastAPI routes (`start_run`,
  `get_shortlist`, `approve_shortlist`, `get_review`, `review_documents`, `history`, `fork`),
  keep the graph and persistence unchanged, and add auth in front.
