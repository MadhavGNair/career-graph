# Costs

No prices are quoted here: they change. Check your provider's current pricing page and copy
it into `config/pricing.yaml` if you want USD estimates and USD caps.

## Where tokens go (per run)
| Step | Tier | Calls | Avoided when |
|---|---|---|---|
| `extract_profile` | cheap | 1 per document | documents unchanged (content hash) |
| `extract_jobs` | cheap | 1 per **new** posting, max `MAX_JOBS_PER_RUN` | posting content unchanged |
| match rationale | cheap | 1 per shortlisted job (`top_n`) | `ENABLE_MATCH_RATIONALE=false` |
| `research_company` | cheap | up to `RESEARCH_MAX_STEPS` + 1 per approved job | `ENABLE_COMPANY_RESEARCH=false` (default) |
| `draft_documents` | **strong** | 1 per approved job per revision (<= `MAX_REVISIONS` + 1) | you approve fewer jobs |
| `verify_documents` | cheap | 1 per new/changed claim | unchanged claims reuse their label |

Scoring, filtering, dedupe, skill normalisation, retrieval, rendering and the pauses use no LLM.

## Caps
`MAX_TOKENS_PER_RUN`, `MAX_TOKENS_PER_DAY` (always enforced, no prices needed),
`MAX_USD_PER_RUN`, `MAX_USD_PER_DAY` (only with prices). Hitting a cap halts the run with
state checkpointed; `make resume THREAD=...` continues it. `make doctor` prints the
worst case implied by your caps.

## Measured numbers
- **Demo mode** token counts (e.g. the summary line after `make demo`) come from the fake LLM
  (characters / 4): plumbing checks only, not real spend.
- **Real cost per run: not yet measured.** To measure: run in live mode, then open Insights
  (tokens per run, and USD once `config/pricing.yaml` is filled), or query the `llm_usage`
  table.

## Cheap ways to deploy (check current prices yourself)
| Option | Fits when | Notes |
|---|---|---|
| Local only (`make ui`, cron on your laptop) | personal use | zero infrastructure; runs only when the machine is on |
| One small VM with k3s (`deploy/k3s/`) | always-on scheduled runs | SQLite on local disk; 2 vCPU / 4 GB is plenty; back up the volume |
| Scale-to-zero container platforms | UI used rarely | needs Postgres (instances are ephemeral); scheduled run via the platform's cron/job feature |
| Free-tier managed Postgres | multi-node or ephemeral compute | point `DATABASE_URL` at it; check the free tier's storage/connection limits |

Prompt caching is requested for the static system prompts on Anthropic models; prompts shorter
than the model's minimum cacheable length are not cached.
