# PLAN

Checked-off build plan. A fresh session continues from the first unchecked box.
Rules: run `make lint typecheck test` after each phase, then commit (conventional commits).
Never push. No live LLM calls. Never fabricate numbers (see CLAUDE.md).

## P0 Scaffold and user-facing surface
- [x] git init (main), pyproject (uv, py3.12, pinned deps), ruff/pyright/pytest config
- [x] `.env.example` fully commented; `config/*.yaml` fully commented; demo search/profile config
- [x] `config.py`: Settings + strict YAML models, errors name file/key/fix
- [x] `make doctor` (OK/WARN/FAIL + next action, worst-case spend)
- [x] Makefile with `## ` help on every target
- [x] Drift-guard test (env + YAML keys documented, commented, used)
- [x] PII guard script, pre-commit config
- [x] CLAUDE.md, PLAN.md, root README usage section, config/ and profiles/ READMEs

## P1 Foundations
- [x] domain schemas + status enum
- [x] LLM factory (init_chat_model, json_schema structured output), fake LLM, budgets/cost tracking
- [x] skills normalisation, retrieval (BM25 + embeddings + RRF, hashing fallback, disk cache)
- [x] demo data: Sam Demo CV + 2 letters (.md, .tex), GitHub fixture (5 repos), ~30 postings (3 injection, 2 near-dup, 1 German), 5 company web fixtures, eval gold files

## P2 Profile
- [x] document parsers (pypdf, md/txt, tex stripping), GitHub adapter (SSRF-safe, cached)
- [x] ingest_profile, extract_profile (+ pinned evidence.yaml merge, skip-when-unchanged edge), `make profile`

## P3 Jobs
- [x] SSRF-safe fetcher (allowlist, private IP block, redirect revalidation, caps, robots, ETag, rate limit)
- [x] Greenhouse/Lever/Ashby/RSS adapters + fixture transport, injection scanner + wrapping
- [x] find_jobs (filters, dedupe, MAX_JOBS_PER_RUN, content-hash skip), extract_jobs (Send fan-out)

## P4 Match + first pause
- [x] persistence (SQLAlchemy models, schema_version, checkpointer + Store factories, sqlite/postgres)
- [x] match_jobs (criteria, dealbreakers, partial credit, evidence ids, preference adjustment, rationale)
- [x] human_shortlist interrupt + decisions to DB + preferences to Store
- [x] service layer + CLI (run, pending, shortlist, approve, resume)

## P5 Documents
- [x] document_factory subgraph (draft <-> verify loop, MAX_REVISIONS), research_company subgraph (ToolNode)
- [x] human_review interrupt (approve/edit/regenerate/reject, override), render_latex + templates, save_results
- [x] time travel: history, fork; demo command

## P6 UI
- [x] Streamlit pages (Run, Shortlist, Documents, Tracker, Insights) + AppTest smoke tests

## P7 Evals + CI
- [x] eval suites (match, extraction, verifier, injection), thresholds, reports, export-labels
- [x] workflows: ci, security, release, live-eval, dependabot, PR template

## P8 Delivery
- [x] Dockerfile (+ latex target), compose (postgres, cron profiles), Helm chart, ArgoCD, k3s guide
- [x] docs: architecture, security, costs, live-mode, ADRs (>= 7)

## P9 Extras (only if all green)
- [x] tracker graph, interview_prep, mock_interview

## P10 Polish
- [ ] README audit, node cards, `make docs-graphs` + freshness check, full verification
- [x] `NOT_YET_WIRED` in tests/test_drift_guard.py is empty (emptied in P5)
- [ ] tests/test_docs.py PENDING set is empty
