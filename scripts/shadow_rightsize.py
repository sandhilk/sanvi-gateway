#!/usr/bin/env python3
"""SanVi Shadow Right-Sizer: replay a sample of real-style requests per workload through the
baseline model and a cheaper candidate, have the baseline model grade the candidate's answer
against its own, and report per workload whether switching is safe and what it would save.

Everything goes through the SanVi gateway, so keys, budgets and logs stay in your cluster
(the prompts themselves still go to the model provider, as normal traffic does).

Usage:
  shadow_rightsize.py [--sample evals/shadow_sample.jsonl] [--spend evals/shadow_workloads.json]
                      [--baseline sanvi-smart] [--candidate sanvi-fast] [--min-win 0.9]
Needs SANVI_GATEWAY (default http://localhost:4000) and SANVI_AGENT_KEY (a key allowed to use both models).
"""
import argparse, json, os, pathlib, re, sys, time, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--sample", default=str(ROOT / "evals" / "shadow_sample.jsonl"))
ap.add_argument("--spend", default=str(ROOT / "evals" / "shadow_workloads.json"),
                help="JSON map: workload -> current monthly spend on the baseline (any currency)")
ap.add_argument("--baseline", default="sanvi-smart")
ap.add_argument("--candidate", default="sanvi-fast")
ap.add_argument("--min-win", type=float, default=0.9,
                help="share of samples where the candidate must be judged as good as the baseline")
ap.add_argument("--out", default=str(ROOT / "evals" / "shadow-report.md"))
args = ap.parse_args()

GATEWAY = os.environ.get("SANVI_GATEWAY", "http://localhost:4000").rstrip("/")
KEY = os.environ.get("SANVI_AGENT_KEY")
if not KEY:
    sys.exit("set SANVI_AGENT_KEY (type it with: read -s SANVI_AGENT_KEY && export SANVI_AGENT_KEY)")

JUDGE = """You are grading two answers to the same request. Answer A is the reference.
Score answer B from 1 to 5 for whether it does the job as well as A for this request:
5 = as good or better, 4 = slightly worse but fully acceptable, 3 = noticeably worse,
2 = misses important parts, 1 = wrong. Reply with JSON only: {"score": <1-5>, "reason": "<short>"}

REQUEST:
%s

ANSWER A:
%s

ANSWER B:
%s"""


def chat(model, messages, max_tokens=800):
    """Call the gateway; return (text, cost_usd, seconds). Cost comes from LiteLLM's response header."""
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(f"{GATEWAY}/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    t0 = time.time()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
                cost = float(r.headers.get("x-litellm-response-cost") or 0)
                return data["choices"][0]["message"]["content"] or "", cost, round(time.time() - t0, 2)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2 ** attempt * 3)
                continue
            sys.exit(f"gateway error {e.code} for {model}: {e.read()[:300]!r}")


def judge(request_text, ref, cand):
    text, cost, _ = chat(args.baseline, [{"role": "user", "content": JUDGE % (request_text, ref, cand)}], 200)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        j = json.loads(m.group(0)) if m else {}
        return int(j.get("score", 0)), str(j.get("reason", ""))[:120], cost
    except (ValueError, TypeError):
        return 0, "judge reply not parseable", cost


samples = [json.loads(l) for l in pathlib.Path(args.sample).read_text().splitlines() if l.strip()]
spend = json.loads(pathlib.Path(args.spend).read_text()) if pathlib.Path(args.spend).exists() else {}

per = {}
for i, s in enumerate(samples, 1):
    w = s["workload"]
    msgs = s.get("messages") or [{"role": "user", "content": s["prompt"]}]
    req_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    print(f"[{i}/{len(samples)}] {w}: {s.get('id', '')}", flush=True)
    ref, c_base, t_base = chat(args.baseline, msgs)
    cand, c_cand, t_cand = chat(args.candidate, msgs)
    score, reason, c_judge = judge(req_text, ref, cand)
    print(f"   score {score}/5  baseline ${c_base:.5f} {t_base}s  candidate ${c_cand:.5f} {t_cand}s", flush=True)
    r = per.setdefault(w, {"n": 0, "wins": 0, "base_cost": 0.0, "cand_cost": 0.0, "judge_cost": 0.0,
                           "base_s": 0.0, "cand_s": 0.0, "fails": []})
    r["n"] += 1
    r["wins"] += score >= 4
    r["base_cost"] += c_base; r["cand_cost"] += c_cand; r["judge_cost"] += c_judge
    r["base_s"] += t_base; r["cand_s"] += t_cand
    if score < 4:
        r["fails"].append(f"{s.get('id', i)}: {score}/5, {reason}")

lines = ["# SanVi Shadow Right-Size report", "",
         f"Baseline **{args.baseline}** vs candidate **{args.candidate}**, judged by {args.baseline}. "
         f"Switch rule: candidate as good (score 4+) on at least {args.min_win:.0%} of samples.", "",
         "| Workload | Samples | Candidate as good | Cost per request (base → candidate) | Speed (base → candidate) | Verdict | Monthly spend now | Monthly saving |",
         "|---|---|---|---|---|---|---|---|"]
total_now = total_save = shadow_cost = 0.0
for w, r in per.items():
    win = r["wins"] / r["n"]
    cut = 1 - r["cand_cost"] / r["base_cost"] if r["base_cost"] else 0
    ok = win >= args.min_win and cut > 0
    now = float(spend.get(w, 0))
    save = now * cut if ok else 0
    total_now += now; total_save += save
    shadow_cost += r["base_cost"] + r["cand_cost"] + r["judge_cost"]
    lines.append(f"| {w} | {r['n']} | {r['wins']}/{r['n']} ({win:.0%}) | "
                 f"${r['base_cost'] / r['n']:.5f} → ${r['cand_cost'] / r['n']:.5f} ({cut:.0%} cheaper) | "
                 f"{r['base_s'] / r['n']:.1f}s → {r['cand_s'] / r['n']:.1f}s | "
                 f"{'**switch**' if ok else 'stay'} | {now:,.0f} | {save:,.0f} |")
lines += ["", f"**Projected saving: {total_save:,.0f} per month on {total_now:,.0f} "
              f"({(total_save / total_now if total_now else 0):.0%}), about {total_save * 12:,.0f} per year.**",
          f"Cost of this shadow run (all calls incl. judging): ${shadow_cost:.4f}.", ""]
fails = [(w, f) for w, r in per.items() for f in r["fails"]]
if fails:
    lines += ["Where the candidate fell short (keep these on the baseline):", ""]
    lines += [f"- {w}: {f}" for w, f in fails]
    lines.append("")
lines += ["Notes: projection = current spend x measured cost cut, only for workloads that pass the rule. "
          "Grow the sample before acting; re-run after any prompt or model change."]
report = "\n".join(lines)
pathlib.Path(args.out).write_text(report + "\n")
print("\n" + report)
