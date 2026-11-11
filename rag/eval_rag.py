#!/usr/bin/env python3
"""SanVi Docs Assistant, step 3: evaluate the RAG agent.

For each question we check two things:
  retrieval  - did the expected document land in the top-k chunks?
  answer     - does the answer contain the expected fact and stay grounded (cites a retrieved source)?
Plus one out-of-scope question the agent must refuse rather than invent.
Exits 1 if the overall pass rate is below --min (default 80%), so it can gate CI like evals.yml.
"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from agent import ask, NOT_FOUND

CASES = json.loads((pathlib.Path(__file__).parent / "eval_cases.json").read_text())
ap = argparse.ArgumentParser(); ap.add_argument("--min", type=float, default=0.8); a = ap.parse_args()

passed = 0; rows = []
for c in CASES:
    t0 = time.time(); out = ask(c["q"]); dt = time.time() - t0
    srcs = [d["source"] for d in out["docs"]]
    ans = out["answer"].lower()
    if c.get("expect_refusal"):
        ok_r = True; ok_a = NOT_FOUND.lower() in ans
    else:
        ok_r = any(c["source"].lower() in s.lower() for s in srcs)
        ok_a = out["grounded"] and all(k.lower() in ans for k in c["must_contain"])
    ok = ok_r and ok_a; passed += ok
    rows.append((c["q"], ok_r, ok_a, ok, dt))
    print(f"{'PASS' if ok else 'FAIL'}  retrieval={'ok' if ok_r else 'miss'}  answer={'ok' if ok_a else 'bad'}  {dt:.1f}s  {c['q']}")
rate = passed / len(CASES)
print(f"\nRAG eval: {passed}/{len(CASES)} passed ({rate:.0%}), threshold {a.min:.0%}")
sys.exit(0 if rate >= a.min else 1)
