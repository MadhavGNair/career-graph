# llm/

## Purpose
One narrow interface (`ChatPort`) for every model call, two implementations (live via
LangChain `init_chat_model`, and a deterministic fake), and token/USD budgets that halt a run
gracefully.

## How it works
```mermaid
flowchart LR
  Node -->|structured(task, schema, system, prompt, payload, run_id)| Port{ChatPort}
  Port -->|APP_MODE=live| Live[LiveChat: init_chat_model + json_schema output]
  Port -->|APP_MODE=demo| Fake[FakeChat: task handlers]
  Live --> Budget
  Fake --> Budget
  Budget -->|check before call| Ledger[(usage ledger: DB)]
  Budget -->|record after call| Ledger
```
- `get_model(tier)` (`ModelFactory.get_model`): `cheap` = `CHEAP_MODEL` (extraction, rationale,
  verification, research), `strong` = `STRONG_MODEL` (drafting only).
- `structured()` uses provider-native structured output (`method="json_schema"` on Anthropic)
  with `include_raw=True` so token usage (incl. cache reads/writes) is recorded.
- `tool_step()` binds tools for one ReAct step (company research). Tool choice is left to the
  model: forced tool choice is rejected by some current models.
- Static system prompts are sent as a content block with `cache_control: ephemeral` on
  Anthropic. Prompts below the provider's minimum cacheable length are silently not cached.

## LangGraph concepts used and why
Models are not graph nodes; nodes obtain them from the runtime context
(`runtime.context.models.get_model(tier)`). `BudgetExceeded` raised inside a node stops the
run; the checkpointer keeps everything done so far, so `resume` continues where it stopped.

## Key files
| File | What |
|---|---|
| `factory.py` | `ModelFactory.get_model(tier)`: fake in demo, live otherwise |
| `port.py` | `ChatPort` protocol, `LiveChat`, usage extraction |
| `fake.py` | deterministic handlers: keyword extraction, evidence-based drafting, token-overlap entailment, scripted research loop; the fabrication scenario |
| `prompts.py` | static system prompts and user-prompt builders (untrusted text is delimited) |
| `budget.py` | `Budget.check/record`, `BudgetExceeded` |
| `usage.py` | `UsageRecord`, ledger protocol, in-memory ledger, USD estimate |

## Configuration
`CHEAP_MODEL`, `STRONG_MODEL`, `CHEAP_EFFORT`, `STRONG_EFFORT`, `MAX_OUTPUT_TOKENS_PER_CALL`,
`LLM_TIMEOUT_SECONDS`, `ANTHROPIC_API_KEY`, `MAX_TOKENS_PER_RUN`, `MAX_TOKENS_PER_DAY`,
`MAX_USD_PER_RUN`, `MAX_USD_PER_DAY`, `DEMO_FABRICATE_JOB`; prices in `config/pricing.yaml`.

## Verified API facts (langchain-anthropic 1.7.12, langchain 1.5.2; checked in source)
- `init_chat_model("anthropic:<model>", ...)` returns `ChatAnthropic`; `effort=` is accepted.
- `with_structured_output(method="json_schema")` uses Anthropic structured outputs
  (`output_config.format`); the default `function_calling` method uses tool calling, which is
  not forced on models that reject forced tool choice (e.g. Sonnet 5.5).
- `ChatAnthropic` refuses non-default `temperature` for Sonnet 5.5 / Fable models, so no
  sampling parameters are sent.
- Default model ids `claude-haiku-5-5` (cheap) and `claude-sonnet-5-5` (strong) were taken from
  Anthropic's current model list (cached 2026-11-03). Live calls were **not** made in
  development; see `docs/live-mode.md`.

## How to run and test
`uv run pytest tests/test_llm.py`. Live mode is covered by mocked tests that assert the exact
arguments (`json_schema`, `include_raw`, `cache_control`, `effort`, no `temperature`).

## Design decisions and trade-offs
- **Fake behind the same port** instead of LangChain's fake chat models: the fake reads the
  structured payload the prompt was built from, so it is input-dependent and deterministic.
  The trade-off is that fake-mode results say nothing about model quality.
- **Budgets checked before each call**: simple and exact enough; a single call can overshoot
  a cap by its own size, then the next call halts the run (`BudgetExceeded`) with state
  checkpointed. `make resume THREAD=...` continues after raising the cap.
- Tokens work without prices; USD caps apply only when `config/pricing.yaml` has prices.

## Extending and gotchas
- New task: add a prompt in `prompts.py`, a fake handler in `fake.py`, and call
  `get_model(tier).structured(task=...)` from a node.
- Another provider: set `CHEAP_MODEL=openai:...` etc. and install its LangChain package;
  only Anthropic is verified here and `make doctor` warns for others.
