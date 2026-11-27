# .github/

## Purpose
CI/CD definitions. This repository was built locally and never pushed, so **none of these
workflows has run yet**; they were written against action versions verified on 2026-11-22.

## How it works
| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | push to main, PRs | PII/secret guard, ruff, pyright, pytest (incl. demo smoke + AppTest), fake-mode eval gate, diagram freshness, eval reports artifact; docker build (no push) + `doctor` inside the image; helm lint + kubeconform |
| `security.yml` | weekly + manual | pip-audit on the locked deps, Trivy fs + image scan, gitleaks |
| `release.yml` | tag `v*` | build and push the image to GHCR |
| `live-eval.yml` | manual only | evals with real models (secret `ANTHROPIC_API_KEY`), capped by `MAX_TOKENS_PER_RUN/DAY`, reports uploaded |
| `dependabot.yml` | weekly | uv, GitHub Actions, Docker base image |

## Key files
`workflows/*.yml`, `dependabot.yml`, `PULL_REQUEST_TEMPLATE.md`.

## LangGraph concepts used and why
None directly; CI runs the graph through the tests and the eval gate with the fake LLM.

## Configuration
Repo secret `ANTHROPIC_API_KEY` (live-eval only). `GITHUB_TOKEN` is provided by Actions.

## How to run and test
Locally: `make check eval docs-graphs k8s-lint`. Workflow syntax was not executed (no push).

## Design decisions and trade-offs
- `astral-sh/setup-uv` is pinned to `v10.4.0` (there is no floating `v10` tag).
- `aquasecurity/trivy-action` is pinned to a commit SHA because its tags were force-pushed to
  malware in March 2026 (advisory GHSA-69fq-xp46-6x23).
- Live evals are manual and never gate merges: they cost money and vary run to run.

## Extending and gotchas
Keep CI keyless: anything needing a key belongs in `live-eval.yml`.
