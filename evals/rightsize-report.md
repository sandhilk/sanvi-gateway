# SanVi Right-Size report

Workload: SanVi Launch eval suite (5 cases). Baseline: **sanvi-smart**.

| Model | Pass rate | Avg attempts | Cost per run | Avg time per case |
|---|---|---|---|---|
| sanvi-smart | 5/5 (100%) | 1.0 | $0.2079 | 22.9s |
| sanvi-fast | 5/5 (100%) | 1.0 | $0.0094 | 13.7s |

**Recommendation: switch this workload to sanvi-fast.** Same quality (5/5) at 95% lower cost.
At $50/month on sanvi-smart, that is about **$48/month saved** ($573/year).

Rule: recommend the cheapest model whose pass rate is at least the baseline's and at least 80%.
