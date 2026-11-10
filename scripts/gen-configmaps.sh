#!/usr/bin/env bash
# Regenerate ConfigMaps that carry repo files into the cluster. Run after editing the source files.
set -euo pipefail
cd "$(dirname "$0")/.."
kubectl -n sanvi create configmap budget-watch-script --from-file=budget_watch.py=scripts/budget_watch.py \
  --dry-run=client -o yaml > apps/sanvi/budget-watch-configmap.yaml
kubectl -n sanvi create configmap access-sync-files \
  --from-file=access_sync.py=scripts/access_sync.py --from-file=teams.yaml=access/teams.yaml \
  --dry-run=client -o yaml > apps/sanvi/access-sync-configmap.yaml
echo "ConfigMaps regenerated"
kubectl -n monitoring create configmap sanvi-dashboard --from-file=sanvi-spend.json=dashboards/sanvi-spend.json \
  --dry-run=client -o yaml | kubectl label --local -f - grafana_dashboard=1 -o yaml > apps/monitoring/sanvi-dashboard.yaml
echo "Dashboard ConfigMap regenerated"
