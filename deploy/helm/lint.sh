#!/usr/bin/env bash
# helm lint + helm template | kubeconform for the default, cheap and postgres variants.
# Skips cleanly (exit 0, with a message) when helm or kubeconform is not installed.
set -euo pipefail
CHART="$(cd "$(dirname "$0")" && pwd)/careergraph"
if ! command -v helm >/dev/null; then echo "SKIP: helm not installed"; exit 0; fi
variants=(
  ""
  "-f $CHART/values-cheap.yaml"
  "--set postgres.enabled=true --set ingress.enabled=true --set secret.create=true --set-string config.criteria\\.yaml=threshold:60"
)
for v in "${variants[@]}"; do
  # shellcheck disable=SC2086
  helm lint "$CHART" $v >/dev/null
  echo "helm lint OK ${v:-(defaults)}"
done
if ! command -v kubeconform >/dev/null; then echo "SKIP: kubeconform not installed (helm lint ran)"; exit 0; fi
for v in "${variants[@]}"; do
  # shellcheck disable=SC2086
  helm template test "$CHART" $v | kubeconform -strict -summary -
done
