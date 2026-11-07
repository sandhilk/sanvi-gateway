#!/usr/bin/env python3
"""SanVi Launch v0: one sentence -> validated Dockerfile + Helm chart.
Every model call goes through the SanVi gateway, using the agent's own budget-capped key."""
import json, os, pathlib, re, subprocess, sys, urllib.request, urllib.error

GATEWAY = os.environ.get("SANVI_GATEWAY", "http://localhost:4000")
KEY = os.environ.get("SANVI_AGENT_KEY") or sys.exit("Set SANVI_AGENT_KEY first")
MODEL = os.environ.get("SANVI_MODEL", "sanvi-smart")
MAX_TRIES = 3
OUT = pathlib.Path("out")

SYSTEM = """You are SanVi Launch, a platform engineering agent.
Turn the user's request into Kubernetes deployment files.
Return ONLY one JSON object, no other text:
{"name": "<service-name>", "files": {"<relative path>": "<file content>"}, "summary": "<3 short lines: what you built and why>"}
Required files:
- Dockerfile: multi-stage where sensible, non-root USER, no secrets
- chart/Chart.yaml (apiVersion: v2)
- chart/values.yaml
- chart/templates/deployment.yaml: resource requests and limits, readiness and liveness probes,
  securityContext with runAsNonRoot and allowPrivilegeEscalation false
- chart/templates/service.yaml
- chart/templates/pdb.yaml: PodDisruptionBudget (policy/v1) when replicas > 1
Use the service name for resource names. No TODOs or placeholders. Valid YAML only."""


def call(messages):
    """Send the conversation to the gateway. Gateway errors (budget, rate limit) stop the agent."""
    body = json.dumps({"model": MODEL, "messages": messages, "max_tokens": 8000}).encode()
    req = urllib.request.Request(f"{GATEWAY}/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Gateway refused the request (HTTP {e.code}): {e.read().decode()[:300]}")


def parse(text):
    """Pull the JSON object out of the model's reply."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object found")
    return json.loads(m.group(0))


def write(plan):
    """Write files under out/<name>/, refusing any path that tries to escape."""
    name = re.sub(r"[^a-z0-9-]", "-", plan["name"].lower())
    base = OUT / name
    for rel, content in plan["files"].items():
        if rel.startswith("/") or ".." in pathlib.Path(rel).parts:
            raise ValueError(f"unsafe path from model: {rel}")
        f = base / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    return base


def validate(d):
    """Real checks, not trust: helm lint, render, schema-validate, Dockerfile rules."""
    errs = []
    chart = d / "chart"
    r = subprocess.run(["helm", "lint", str(chart)], capture_output=True, text=True)
    if r.returncode:
        errs.append("helm lint failed:\n" + (r.stdout + r.stderr)[-3000:])
    t = subprocess.run(["helm", "template", "svc", str(chart)], capture_output=True, text=True)
    if t.returncode:
        errs.append("helm template failed:\n" + t.stderr[-3000:])
    else:
        k = subprocess.run(["kubeconform", "-strict", "-summary", "-"], input=t.stdout, capture_output=True, text=True)
        if k.returncode:
            errs.append("kubeconform failed:\n" + (k.stdout + k.stderr)[-3000:])
    df = d / "Dockerfile"
    if not df.exists():
        errs.append("Dockerfile is missing")
    elif not re.search(r"^USER\s+(?!root\b|0\b)\S+", df.read_text(), re.M):
        errs.append("Dockerfile must switch to a non-root USER")
    return errs


def main():
    ask = " ".join(sys.argv[1:]) or sys.exit('usage: sanvi_launch.py "<one sentence>"')
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ask}]
    for attempt in range(1, MAX_TRIES + 1):
        print(f"[attempt {attempt}/{MAX_TRIES}] generating via SanVi gateway ...")
        reply = call(msgs)
        try:
            plan = parse(reply)
            out = write(plan)
            errs = validate(out)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            errs = [f"Your reply could not be used: {e}. Return only the JSON object."]
        if not errs:
            print(f"\nPASS: all checks green. Files in {out}/")
            print(plan.get("summary", ""))
            return
        print("  checks failed:", *[e.splitlines()[0] for e in errs], sep="\n   - ")
        msgs += [{"role": "assistant", "content": reply},
                 {"role": "user", "content": "Validation failed. Fix ALL of these and return the full JSON again:\n\n" + "\n\n".join(errs)}]
    sys.exit(f"\nGave up after {MAX_TRIES} attempts. Errors are shown above.")


if __name__ == "__main__":
    main()
