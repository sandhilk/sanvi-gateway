#!/usr/bin/env python3
"""SanVi Right-Size Advisor: run the same eval suite on each model and recommend the cheapest one
that keeps quality (pass rate >= baseline and >= minimum). Never recommends a switch that loses quality.
Usage: rightsize.py [--models sanvi-smart,sanvi-fast] [--monthly-spend 50]
Needs SANVI_GATEWAY, SANVI_ADMIN_KEY and SANVI_AGENT_KEY (a key allowed to use every model listed)."""
import argparse, json, os, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVALS, RESULTS = ROOT / "evals" / "run_evals.py", ROOT / "evals" / "results.json"
ap = argparse.ArgumentParser()
ap.add_argument("--models", default="sanvi-smart,sanvi-fast", help="first one is the baseline")
ap.add_argument("--monthly-spend", type=float, default=50.0, help="current monthly spend on the baseline, in USD")
ap.add_argument("--min-pass", type=float, default=0.8)
args = ap.parse_args()
models = [m.strip() for m in args.models.split(",") if m.strip()]
original = RESULTS.read_text() if RESULTS.exists() else None

rows = []
for m in models:
    print(f"== evaluating {m} ...", flush=True)
    t0 = time.time()
    p = subprocess.run([sys.executable, str(EVALS)], env={**os.environ, "SANVI_MODEL": m},
                       capture_output=True, text=True, timeout=3600)
    out = p.stdout + p.stderr
    s = re.search(r"(\d+)/(\d+) passed .*?avg attempts ([\d.]+), cost \$([\d.]+)", out)
    if not s:
        print(out[-800:]); sys.exit(f"could not read eval summary for {m}")
    passed, total, attempts, cost = int(s[1]), int(s[2]), float(s[3]), float(s[4])
    secs = []
    if RESULTS.exists():
        data = json.loads(RESULTS.read_text())
        cases = data.get("results", data) if isinstance(data, dict) else data
        secs = [c.get("seconds", 0) for c in cases if isinstance(c, dict)]
        (ROOT / "evals" / f"rightsize-{m}.json").write_text(RESULTS.read_text())
    rows.append({"model": m, "passed": passed, "total": total, "rate": passed / total, "attempts": attempts,
                 "cost": cost, "avg_s": round(sum(secs) / len(secs), 1) if secs else round(time.time() - t0, 1)})
    print(f"   {passed}/{total} passed, avg attempts {attempts}, cost ${cost:.4f}", flush=True)

if original is not None:
    RESULTS.write_text(original)   # keep the committed baseline results untouched

base = rows[0]
ok = [r for r in rows if r["rate"] >= base["rate"] and r["rate"] >= args.min_pass]
best = min(ok, key=lambda r: r["cost"]) if ok else base
lines = ["# SanVi Right-Size report", "",
         f"Workload: SanVi Launch eval suite ({base['total']} cases). Baseline: **{base['model']}**.", "",
         "| Model | Pass rate | Avg attempts | Cost per run | Avg time per case |",
         "|---|---|---|---|---|"]
for r in rows:
    lines.append(f"| {r['model']} | {r['passed']}/{r['total']} ({r['rate']:.0%}) | {r['attempts']} | ${r['cost']:.4f} | {r['avg_s']}s |")
lines.append("")
if best["model"] == base["model"]:
    lines.append(f"**Recommendation: stay on {base['model']}.** No cheaper model kept the same quality.")
else:
    pct = 1 - best["cost"] / base["cost"] if base["cost"] else 0
    lines.append(f"**Recommendation: switch this workload to {best['model']}.** Same quality "
                 f"({best['passed']}/{best['total']}) at {pct:.0%} lower cost.")
    lines.append(f"At ${args.monthly_spend:.0f}/month on {base['model']}, that is about "
                 f"**${args.monthly_spend * pct:.0f}/month saved** (${args.monthly_spend * pct * 12:.0f}/year).")
lines.append("")
lines.append(f"Rule: recommend the cheapest model whose pass rate is at least the baseline's and at least {args.min_pass:.0%}.")
report = "\n".join(lines)
(ROOT / "evals" / "rightsize-report.md").write_text(report + "\n")
print("\n" + report)
