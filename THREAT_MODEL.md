# SanVi threat model (STRIDE) and risk register

**What we're protecting:** the provider API key (it can spend real money), team keys and budgets, the audit trail, and the prompts teams send.

**How it flows:** team app → SanVi gateway (LiteLLM) → AI provider. Keys and budgets live in Postgres (CloudNativePG). The provider key lives in Vault and reaches the cluster through External Secrets. Argo CD deploys everything from Git.

Method: for each part of the flow, ask the 6 STRIDE questions, then decide: **treat** (add a control), **accept** (record it with a reason and an owner), or **design it out**.

## STRIDE

| Threat | What could happen | Control in SanVi | Status |
|---|---|---|---|
| **S**poofing | Someone calls the gateway pretending to be a team | Per-team virtual keys; revoke in seconds; kill switch | ✅ Treated |
| **T**ampering | A changed or swapped container image runs in the cluster | Image scanned by Trivy, signed with cosign (keyless) in CI; Kyverno admits only signed SanVi images, pinned to the verified digest | ✅ Treated (own images) / R2 (third-party) |
| **T**ampering | Access rules changed without review | Access as code: `access/teams.yaml` by pull request, CI policy check, applied by Argo CD | ✅ Treated |
| **R**epudiation | "I didn't send that request" | Every request logged: key, model, tokens, cost, time | ✅ Treated |
| **I**nformation disclosure | Provider key leaks | Key only in Vault → External Secrets; never in Git (gitleaks scans full history in CI) | ✅ Treated |
| **I**nformation disclosure | Prompts seen by people reading spend dashboards | Grafana reads Postgres through a column-level read-only role; `SELECT messages` is denied (tested) | ✅ Treated |
| **D**enial of service | One team's runaway script exhausts capacity or budget | Per-key rate limits (429), budgets (blocked), 80% budget alert CronJob | ✅ Treated |
| **E**levation of privilege | A compromised pod or job gains wider access | Least-privilege Role for access-sync (Secrets, one namespace); non-root containers enforced by Kyverno; AI agent can only open pull requests | ✅ Treated / R3 (LiteLLM) |
| **E**levation of privilege | A compromised CI job publishes a malicious image | Images pushed only from `main`; signing identity is tied to this workflow on `main`; actions pinned to commit SHAs | ✅ Treated |

## Risk register

Every Checkov check skipped in `.checkov.yaml` or by annotation has a row here.

| ID | Risk | Decision | Reason | Owner | Next step |
|---|---|---|---|---|---|
| R1 | No HEALTHCHECK in the Budget Watch image (CKV_DOCKER_2) | Accept | Short-lived CronJob; Kubernetes ignores Docker HEALTHCHECK | Sandhil | None |
| R2 | Third-party images (LiteLLM, python) pinned by tag, not digest (CKV_K8S_43) | Treat later | Moving tags can change what runs. SanVi's own images are already digest-pinned by Kyverno. Upstream images are scanned and reported in CI | Sandhil | Pin LiteLLM and python by digest |
| R3 | Upstream LiteLLM container not hardened (root, writable filesystem, no seccomp) | Treat later | Hardening needs testing so the gateway still starts. Excluded by name from the non-root policy rather than weakening the rule | Sandhil | Test securityContext + emptyDir mounts on kind, then remove the exclusion |
| R4 | Service account tokens mounted where not needed (CKV_K8S_38) | Treat later | Low impact (default service account, no extra RBAC) | Sandhil | Set `automountServiceAccountToken: false` on gateway and Budget Watch |
| R5 | No NetworkPolicies (CKV2_K8S_6) | Treat later | Any pod in the cluster can reach the gateway and Postgres | Sandhil | Default-deny, then allow gateway → Postgres and apps → gateway |
| R6 | Secrets passed as environment variables (CKV_K8S_35) | Accept for now | LiteLLM reads provider keys from env | Sandhil | Move to file mounts if LiteLLM supports it |
| R7 | access-sync can read Secrets (CKV2_K8S_5) | Accept | Required by design to create team keys; limited to one namespace by a Role | Sandhil | Review if the job's scope grows |
| R8 | CPU limits not set (CKV_K8S_11) | Accept | Deliberate, to avoid CPU throttling; CPU requests are set | Sandhil | None |
| R9 | imagePullPolicy not `Always` (CKV_K8S_15) | Accept | Not needed once images are pinned by tag or digest | Sandhil | None |

## How the pipeline enforces this

`.github/workflows/secure-pipeline.yml` runs on every pull request and every push to `main`:

1. **gitleaks**: no secrets in the full Git history
2. **Checkov**: Kubernetes manifests, the rendered Helm chart and the Dockerfile, with the decisions above
3. **Kyverno tests**: the policies allow good pods and block bad ones
4. **Build → Trivy gate → SBOM**: critical/high vulnerabilities with a fix block the build
5. **On `main` only**: push, cosign keyless sign by digest, attach the SBOM as a signed attestation, verify the signature
6. **Third-party report**: Trivy findings for LiteLLM and python images, for visibility

Lab project, not production. The controls are real and run in CI.
