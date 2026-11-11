# SanVi Helm chart

One-command install of the SanVi gateway into any Kubernetes cluster (EKS, AKS, GKE, on-prem, kind).

## What it installs
- **Gateway** (LiteLLM, OpenAI-compatible API) with your model list
- **Postgres** for keys, budgets and the audit trail: a CloudNativePG cluster, or your own Postgres (e.g. RDS)
- **Budget Watch** CronJob: warns at 80%, alerts at 100%, optional Slack/Teams webhook
- **Secrets**: from a Secret you create, or synced from Vault / AWS Secrets Manager / Azure Key Vault (External Secrets Operator)

## Quick start (existing Secret + CloudNativePG)
```bash
# prerequisites: CloudNativePG operator installed (or set database.mode=external)
kubectl create namespace sanvi
kubectl -n sanvi create secret generic llm-keys \
  --from-literal=LLM_API_KEY="$PROVIDER_KEY" \
  --from-literal=LITELLM_MASTER_KEY="sk-$(openssl rand -hex 16)"
helm install sanvi ./charts/sanvi -n sanvi
```
Type the provider key into the variable yourself (`read -s PROVIDER_KEY`); never commit it.

## Common options
| Value | Default | Use |
|---|---|---|
| `secrets.mode` | `existingSecret` | `externalSecret` to sync from a secrets manager |
| `database.mode` | `cloudnativepg` | `external` + `database.external.secretName` for RDS/Cloud SQL |
| `database.cloudnativepg.instances` | `1` | `3` for high availability |
| `models` | Sonnet, Haiku, mock | your providers and models |
| `budgetWatch.schedule` | every 15 min | alert frequency |
| `gateway.image` | `main-stable` | pin a tag in production |

Then add teams with `access/teams.yaml` + `scripts/access_sync.py` (see the main README).
