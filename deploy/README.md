# deploy/

## Purpose
Ways to run CareerGraph beyond `make ui`: Docker, docker compose, Kubernetes (Helm), GitOps
(ArgoCD) and a single-VM k3s guide. Nothing here provisions cloud resources.

## How it works
| Path | What | Verified in development |
|---|---|---|
| `docker/Dockerfile` | slim non-root runtime image (UI + CLI + CronJob); optional `latex` target with tectonic | runtime image **built and run** (doctor, full demo, UI health); measured size 1.17 GB (ML and UI dependencies dominate); `latex` target **not built** |
| `../docker-compose.yml` | app; `--profile postgres`; `--profile cron` | not run with compose; the Postgres backend itself was verified against a local postgres:17-alpine container |
| `helm/careergraph/` | chart | `helm lint` OK (3 variants); kubeconform not installed |
| `argocd/` | Application manifest | not applied |
| `k3s/` | single-VM guide | not executed |

## Key files
See the table.

## LangGraph concepts used and why
All deployments share the same durability model: checkpointer + Store in SQLite (volume) or
Postgres, so pauses survive restarts and the CronJob/UI split works.

## Configuration
Environment variables from `.env.example`; secrets via env/Secrets only.

## How to run and test
`make docker-build`, `make docker-up`, `make k8s-lint`.

## Design decisions and trade-offs
One image for everything keeps deployment simple; LaTeX is a separate target because a TeX
engine and its package cache would bloat the default image.

## Extending and gotchas
The compose file binds the UI to 127.0.0.1 only. Expose it remotely only behind TLS with
`UI_PASSWORD` set.
