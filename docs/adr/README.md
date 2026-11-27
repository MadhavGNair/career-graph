# Architecture decision records
| ADR | Decision |
|---|---|
| [0001](0001-explicit-stategraph.md) | Explicit StateGraph instead of prebuilt agents |
| [0002](0002-service-layer-streamlit.md) | In-process service layer + Streamlit, no API/SPA |
| [0003](0003-sqlite-default-postgres-optional.md) | SQLite default, Postgres optional, durable Store |
| [0004](0004-in-process-hybrid-retrieval.md) | In-process hybrid retrieval vs pgvector |
| [0005](0005-workflow-vs-agent-matching.md) | Matching as a workflow, LLM only where needed |
| [0006](0006-json-not-latex.md) | LLM emits JSON, never LaTeX |
| [0007](0007-fake-llm-demo-and-cost-controls.md) | Fake-LLM demo mode and cost controls |
| [0008](0008-interrupts-top-level-only.md) | Interrupts only at the top level |
