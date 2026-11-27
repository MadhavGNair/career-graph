# Live mode

Everything in development ran in demo mode. Live mode is implemented and unit-tested with
mocks, but **no live model call, job-board request or GitHub request was made** while building
it. Try it step by step.

## 1. Files to edit
| File | Set |
|---|---|
| `.env` | `APP_MODE=live`, `ANTHROPIC_API_KEY=...`, optionally `GITHUB_TOKEN`, `HTTP_CONTACT`, budgets |
| `config/profile.yaml` | your identity, experience, education (exact; the verifier checks drafts against it), `github.username` |
| `profiles/me/` | your CV (.pdf/.md/.txt/.tex), letters, optional `evidence.yaml` |
| `config/search.yaml` | real Greenhouse/Lever/Ashby slugs or RSS URLs (`enabled: true`), titles, locations; `companies` domains if you enable research |
| `config/criteria.yaml` | weights, threshold, dealbreakers, salary floor |
| `config/pricing.yaml` | optional current prices for USD caps |

## 2. Check, then go slowly
```bash
make doctor                       # must show no FAIL
make profile                      # nodes 1-2: inspect the evidence list it prints
MAX_JOBS_PER_RUN=5 make jobs      # nodes 1-5 without pausing; inspect scores
make run                          # full graph until the shortlist pause
```
Then approve one job, review the drafts in `make ui`, and check `outputs/`.

## 3. Things that may need adjusting (unverified)
- Model ids default to `anthropic:claude-haiku-5-5` (cheap) and `anthropic:claude-sonnet-5-5`
  (strong), taken from Anthropic's model list. If a call fails with "model not found", change
  `CHEAP_MODEL`/`STRONG_MODEL`.
- Structured output uses `method="json_schema"` (Anthropic structured outputs). If a model
  rejects a schema, the error names the task; simplify that schema in `domain/models.py`.
- fastembed downloads `BAAI/bge-small-en-v1.5` on first use into `CACHE_DIR`
  (`EMBEDDING_BACKEND=hashing` avoids the download).
- Real postings have messier sections than fixtures; extraction quality is unknown until you
  run `careergraph eval run --mode live`.

## 4. Postgres (optional)
Verified locally against `postgres:17-alpine`:
```bash
docker compose --profile postgres up -d postgres
DATABASE_URL=postgresql://careergraph:careergraph@localhost:5432/careergraph make doctor
```
Inside compose use `DATABASE_URL=postgresql://careergraph:careergraph@postgres:5432/careergraph`.

## 5. Tracing (optional)
`LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` sends full prompts (including your CV) to
LangSmith. Off by default.
