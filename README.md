# SanVi

**An AI gateway and DevOps agent for Kubernetes.** Budgets, rate limits, fallback and cost tracking for every LLM call, plus an agent that turns one sentence into a reviewed deployment PR.

> Personal open-source lab project, built step by step.

## Progress
- [x] Day 1: kind cluster, Argo CD, Vault, External Secrets (keys synced from Vault, never stored in Git, rotation with zero redeploys)
- [ ] Day 2: Argo CD app-of-apps (GitOps for everything) + LiteLLM gateway
- [ ] Day 3: per-team virtual keys, budgets, rate limits
- [ ] SanVi Launch agent: one sentence → Dockerfile, Helm chart, CI, Argo CD app, alerts → PR

## How secrets flow
Vault (source of truth) → External Secrets Operator (syncs every 1 min) → Kubernetes Secret → app

Lab note: Vault runs in dev mode (in-memory, root token) for local learning only. Production would use HA Vault, auto-unseal and Kubernetes auth.
