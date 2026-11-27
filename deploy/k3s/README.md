# deploy/k3s/

## Purpose
Run CareerGraph on one small VM with k3s: the cheapest "real Kubernetes" setup, with a
scheduled run every morning and the UI behind a password.

## How it works
k3s bundles containerd, the `local-path` storage class (SQLite on the VM disk) and Traefik
(Ingress). The Helm chart deploys the UI Deployment, a CronJob and a PVC.

## Key files
This guide; the chart in `deploy/helm/careergraph/` (`values-cheap.yaml`).

## LangGraph concepts used and why
The CronJob runs `careergraph run`, which stops at the shortlist interrupt; state is in the
SQLite checkpointer on the PVC, so the UI pod resumes the same thread later.

## Configuration
Steps (provision the VM yourself; nothing here creates cloud resources):

```bash
# 1. on the VM (2 vCPU / 4 GB is plenty; check your provider's current prices)
curl -sfL https://get.k3s.io | sh -
sudo kubectl get nodes

# 2. secrets (never in Git)
kubectl create namespace careergraph
kubectl -n careergraph create secret generic careergraph-secrets \
  --from-literal=ANTHROPIC_API_KEY=... --from-literal=UI_PASSWORD=...
kubectl -n careergraph create secret generic careergraph-profile \
  --from-file=cv.md=./profiles/me/cv.md --from-file=evidence.yaml=./profiles/me/evidence.yaml

# 3. install (image from your GHCR after release.yml, or import a local build:
#    docker save careergraph:dev | sudo k3s ctr images import -)
helm install cg deploy/helm/careergraph -n careergraph \
  -f deploy/helm/careergraph/values-cheap.yaml \
  --set image.repository=ghcr.io/<you>/careergraph \
  --set profile.existingSecret=careergraph-profile \
  --set-file config.search\.yaml=config/search.yaml \
  --set-file config.criteria\.yaml=config/criteria.yaml \
  --set-file config.profile\.yaml=config/profile.yaml \
  --set-file config.skills\.yaml=config/skills.yaml \
  --set-file config.pricing\.yaml=config/pricing.yaml

# 4. open the UI through an SSH tunnel (no public exposure needed)
kubectl -n careergraph port-forward svc/cg-careergraph 8501:80
```
Set `config.profile.yaml`'s `documents.dir` to `profiles/me` (the Secret mount).

## How to run and test
`make k8s-lint` renders and lints the chart. This guide was **not executed** in development
(no VM or cluster was provisioned).

## Design decisions and trade-offs
SQLite on `local-path` works because UI and CronJob run on the same node (RWO volume). For
more than one node, enable `postgres.enabled` or point `DATABASE_URL` at managed Postgres.

## Extending and gotchas
- Enable the Ingress only with `UI_PASSWORD` set (and TLS).
- Back up the PVC (`/data`): it holds your history, checkpoints and learned preferences.
