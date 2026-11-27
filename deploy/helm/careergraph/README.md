# deploy/helm/careergraph/

## Purpose
Helm chart: Streamlit UI Deployment, a CronJob running `careergraph run`, a PVC for SQLite,
caches and outputs, ConfigMap (your YAML config), Secret (optional), Ingress (optional) and an
optional in-cluster Postgres StatefulSet.

## How it works
| Template | Renders |
|---|---|
| `deployment.yaml` | UI, health probes on `/_stcore/health`, non-root uid 10001, all capabilities dropped |
| `cronjob.yaml` | `careergraph run` on `cron.schedule`, `concurrencyPolicy: Forbid`, `backoffLimit: 0` |
| `pvc.yaml` | `/data` (SQLite DBs, caches, outputs) |
| `configmap.yaml` | `config/*.yaml` from `--set-file config.<name>=...` (else image defaults) |
| `secret.yaml` | only when `secret.create=true`; prefer `secret.existingSecret` |
| `ingress.yaml` | optional |
| `postgres.yaml` | optional StatefulSet + headless Service; sets `DATABASE_URL` |

## Key files
`values.yaml` (every key commented), `values-cheap.yaml` (one small node), `templates/`,
`../lint.sh`.

## LangGraph concepts used and why
The UI and the CronJob share one durable checkpointer (PVC or Postgres): a scheduled run
pauses at the shortlist and the UI resumes it.

## Configuration
See `values.yaml`. Secrets (`ANTHROPIC_API_KEY`, `UI_PASSWORD`, `POSTGRES_PASSWORD`,
optional `GITHUB_TOKEN`) go in the Secret.

## How to run and test
`make k8s-lint` (helm lint for default, cheap and postgres variants; kubeconform when
installed). In development `helm lint` passed for all three variants with helm v4.0.1;
**kubeconform was not installed, so schema validation is unverified** (CI installs it).

## Design decisions and trade-offs
One replica and `Recreate` strategy: SQLite and the in-process service are single-writer.
Postgres removes that limit for the data, not for the UI's in-process design (fine for one user).

## Extending and gotchas
- `image.repository` is a placeholder until you publish an image.
- With SQLite, UI and CronJob must schedule on the same node (RWO).
