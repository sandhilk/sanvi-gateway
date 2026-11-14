# SanVi Compliance Evidence Report

Generated 2026-11-11 11:26 UTC from commit `8cf6b1d` (repo evidence).

**12 passed · 0 warnings · 0 failed** out of 12 controls.

| ID | Control | Status | Evidence | Related framework themes |
|---|---|---|---|---|
| C1 | No secrets in source control | ✅ PASS | scanned 57 tracked files, no provider keys or private keys found | ISO 27001 A.8.12 Data leakage prevention; SOC 2 CC6.1 |
| C2 | Provider keys held in a secrets manager (Vault), injected at runtime | ✅ PASS | apps/sanvi/external-secret.yaml uses secretStoreRef 'vault' | ISO 27001 A.5.17 Authentication information; ISO 27001 A.8.24 Use of cryptography; SOC 2 CC6.1 |
| C3 | Least-privilege AI access: per-team identity, model allow-list, budget and rate limit | ✅ PASS | 3 teams, each with owner, model allow-list, budget (max $10) and rate limit (max 120 rpm) | ISO 27001 A.5.15 Access control; ISO 27001 A.5.18 Access rights; SOC 2 CC6.3 |
| C4 | Access changes go through review and an automated policy check | ✅ PASS | access changes arrive by pull request (access-policy.yml validates them in CI) and are applied by an Argo CD PostSync job after merge | ISO 27001 A.8.32 Change management; SOC 2 CC8.1 |
| C5 | Audit trail of AI usage (who, which model, when, cost) | ✅ PASS | gateway connected to Postgres (DATABASE_URL), so each request is recorded with key, team, model and cost in spend logs | ISO 27001 A.8.15 Logging; SOC 2 CC7.2; EU AI Act Art. 12 Record-keeping (theme) |
| C6 | Separation of duties: monitoring sees cost, not prompt content | ✅ PASS | Grafana reads spend data as the read-only role grafana_ro (column-level grants: no access to message content) | ISO 27001 A.8.3 Information access restriction; SOC 2 CC6.1 |
| C7 | Continuous cost monitoring with alerts | ✅ PASS | budget-watch CronJob runs on schedule '*/15 * * * *' and fails (alerts) when a team passes its budget | ISO 27001 A.8.16 Monitoring activities; SOC 2 CC7.2 |
| C8 | Incident response: reversible kill switch for AI access | ✅ PASS | scripts/kill_switch.sh can block one team or every key in seconds, and reverse it | ISO 27001 A.5.26 Response to incidents; SOC 2 CC7.4 |
| C9 | Accuracy and robustness: automated evaluation gate in CI | ✅ PASS | evals.yml runs the eval suite in CI and fails below 80%; last recorded run: 5/5 | ISO 27001 A.8.29 Security testing in development; EU AI Act Art. 15 Accuracy and robustness (theme) |
| C10 | Human oversight: AI agent changes require human approval | ✅ PASS | the AI agent can only propose changes as a labelled pull request; a human reviews and merges | EU AI Act Art. 14 Human oversight (theme); ISO 27001 A.8.32 Change management |
| C11 | Guardrails: grounded, cited answers and refusal outside scope | ✅ PASS | RAG assistant must cite retrieved sources or retry; its eval includes an out-of-scope question it must refuse | EU AI Act Art. 13 Transparency (theme); EU AI Act Art. 15 Accuracy (theme) |
| C12 | Model choice justified by measured cost and quality | ✅ PASS | evals/rightsize-report.md records cost, speed and quality per model before any switch | SOC 2 CC3.2 Risk assessment (theme); ISO 27001 A.5.8 Information security in project management (theme) |

_Control evidence to support an audit. Framework references show related themes; this is not a certification or legal advice._
