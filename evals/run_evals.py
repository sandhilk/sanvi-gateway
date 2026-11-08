#!/usr/bin/env python3
"""SanVi Launch evals: run fixed prompts through the agent; report pass rate, attempts and cost.
Exits 1 if the pass rate is below SANVI_EVAL_MIN_PASS (default 0.8), so it can gate CI."""
import json, os, pathlib, re, subprocess, sys, time, urllib.request

CASES = [
    {"id": "python-api", "ask": "Deploy a Python FastAPI service called payments on port 8080 with 2 replicas, health check at /health, 256Mi memory"},
    {"id": "node-web", "ask": "Deploy a Node.js Express app called web-frontend on port 3000 with 3 replicas, readiness check at /ready"},
    {"id": "go-single", "ask": "Deploy a Go API called inventory on port 9090 with 1 replica, liveness check at /healthz, 128Mi memory"},
    {"id": "java-api", "ask": "Deploy a Java Spring Boot service called orders on port 8081 with 2 replicas, health at /actuator/health, 512Mi memory"},
    {"id": "python-env", "ask": "Deploy a Python Flask app called notifications on port 5000 with 2 replicas, health at /health, and an environment variable LOG_LEVEL=info"},
]
MIN_PASS = float(os.environ.get("SANVI_EVAL_MIN_PASS", "0.8"))
GATEWAY = os.environ.get("SANVI_GATEWAY", "http://localhost:4000")
AGENT = pathlib.Path(__file__).resolve().parent.parent / "agent" / "sanvi_launch.py"


def spend():
    """Agent key's recorded spend in USD (needs SANVI_ADMIN_KEY); None if unavailable."""
    admin, key = os.environ.get("SANVI_ADMIN_KEY"), os.environ.get("SANVI_AGENT_KEY")
    if not admin or not key:
        return None
    req = urllib.request.Request(f"{GATEWAY}/key/info?key={key}", headers={"Authorization": f"Bearer {admin}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return float(json.load(r)["info"].get("spend") or 0)
    except Exception:
        return None


def run(case):
    t0 = time.time()
    p = subprocess.run([sys.executable, str(AGENT), case["ask"]], capture_output=True, text=True, timeout=900)
    out = (p.stdout + p.stderr).strip()
    tries = [int(n) for n in re.findall(r"\[attempt (\d+)/", out)]
    return {"id": case["id"], "passed": p.returncode == 0 and "PASS:" in out,
            "attempts": max(tries) if tries else 0, "seconds": round(time.time() - t0, 1),
            "last_line": out.splitlines()[-1][:120] if out else ""}


def main():
    before = spend()
    results = []
    for c in CASES:
        print(f"running {c['id']} ...", flush=True)
        r = run(c)
        results.append(r)
        print(f"  {'PASS' if r['passed'] else 'FAIL'}  attempts={r['attempts']}  {r['seconds']}s", flush=True)
    time.sleep(20)  # the gateway records spend asynchronously
    after = spend()
    passed = sum(r["passed"] for r in results)
    rate = passed / len(results)
    passing = [r["attempts"] for r in results if r["passed"]]
    summary = {"pass_rate": round(rate, 2), "passed": passed, "total": len(results),
               "avg_attempts": round(sum(passing) / len(passing), 2) if passing else None,
               "cost_usd": round(after - before, 4) if before is not None and after is not None else None,
               "results": results}
    print(f"\nSanVi Launch evals: {passed}/{len(results)} passed ({rate:.0%}), "
          f"avg attempts {summary['avg_attempts']}, cost ${summary['cost_usd']}")
    pathlib.Path(__file__).with_name("results.json").write_text(json.dumps(summary, indent=2))
    sys.exit(0 if rate >= MIN_PASS else 1)


if __name__ == "__main__":
    main()
