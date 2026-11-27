# deploy/argocd/

## Purpose
GitOps: let ArgoCD keep a cluster in sync with the Helm chart in this repository.

## How it works
`application.yaml` points ArgoCD at `deploy/helm/careergraph` with `values.yaml` +
`values-cheap.yaml`, creates the `careergraph` namespace and auto-syncs (prune + self-heal).

## Key files
`application.yaml`.

## LangGraph concepts used and why
None; durability comes from the PVC (SQLite) or Postgres behind the checkpointer.

## Configuration
Replace `REPLACE_ME` (repo URL, image repository). Create the Secret `careergraph-secrets`
with `ANTHROPIC_API_KEY`, `UI_PASSWORD` (and `POSTGRES_PASSWORD` if `postgres.enabled`).

## How to run and test
`kubectl apply -n argocd -f deploy/argocd/application.yaml`. Validate the rendered chart with
`make k8s-lint`. **Not applied to any cluster during development.**

## Design decisions and trade-offs
Secrets stay out of Git; ArgoCD only manages non-secret manifests.

## Extending and gotchas
Pin `targetRevision` to a tag for reproducible deploys.
