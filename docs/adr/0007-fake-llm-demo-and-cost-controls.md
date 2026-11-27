# ADR 0007: Fake-LLM demo mode and cost controls

Status: accepted (2026-11-22)

## Decision
- `APP_MODE=demo` swaps in a deterministic, input-dependent fake model behind the same
  `ChatPort` interface, plus fixture HTTP transport; the graph code is identical.
- Token budgets per run and per day are always enforced; USD caps only with configured prices.
  A breach raises `BudgetExceeded`, the run halts with state checkpointed and is resumable.
- Cheap tier for extraction/verification/research, strong tier only for drafting; caching by
  content hash; prompt caching on static system prompts.

## Consequences
Tests, CI, evals and the demo cost nothing and need no keys. Fake-mode metrics prove plumbing,
not model quality; live evals are manual (`live-eval.yml`).
