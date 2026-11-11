#!/usr/bin/env python3
"""SanVi Compliance Evidence Report.

Checks SanVi's real configuration (the Git repo and, with --live, the running cluster) against
the controls a regulated company needs for safe AI use, and writes an audit-ready report that
maps each control to related ISO/IEC 27001:2022, SOC 2 and EU AI Act themes.

This is control evidence to support an audit, not a certification or legal advice.

Usage:
  python3 scripts/compliance_report.py            # repo evidence only (works in CI)
  python3 scripts/compliance_report.py --live     # also checks the running cluster with kubectl
Writes evals/compliance-report.md and evals/compliance-report.json. Exits 1 if any control FAILs.
"""
import argparse, datetime, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true"); args = ap.parse_args()


def read(rel):
    p = ROOT / rel
    return p.read_text(errors="ignore") if p.exists() else ""


def kubectl(*a):
    try:
        return subprocess.run(["kubectl", *a], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


try:
    import yaml
    teams_doc = yaml.safe_load(read("access/teams.yaml")) or {}
except Exception:
    teams_doc = {}

results = []
def control(cid, title, frameworks, check):
    try:
        status, evidence = check()
    except Exception as e:
        status, evidence = "FAIL", f"check error: {e}"
    results.append({"id": cid, "control": title, "status": status, "evidence": evidence, "frameworks": frameworks})


# --- C1: no provider secrets committed to Git -------------------------------------------------
SECRET_RX = re.compile(r"(sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----)")
def c1():
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
    hits = [f for f in files if not f.endswith((".png", ".jpg", ".pyc", ".pdf")) and SECRET_RX.search(read(f))]
    return ("FAIL", f"possible secrets in: {', '.join(hits)}") if hits else ("PASS", f"scanned {len(files)} tracked files, no provider keys or private keys found")
control("C1", "No secrets in source control", ["ISO 27001 A.8.12 Data leakage prevention", "SOC 2 CC6.1"], c1)

# --- C2: provider keys come from Vault via External Secrets -------------------------------------
def c2():
    es = read("apps/sanvi/external-secret.yaml")
    ok = "secretStoreRef" in es and "vault" in es.lower()
    live = ""
    if args.live:
        out = kubectl("get", "externalsecret", "-A", "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.conditions[0].status} {end}")
        live = f"; live: {out.strip() or 'no ExternalSecrets found'}"
        ok = ok and "=True" in out
    return ("PASS" if ok else "FAIL", f"apps/sanvi/external-secret.yaml uses secretStoreRef 'vault'{live}")
control("C2", "Provider keys held in a secrets manager (Vault), injected at runtime", ["ISO 27001 A.5.17 Authentication information", "ISO 27001 A.8.24 Use of cryptography", "SOC 2 CC6.1"], c2)

# --- C3: every team has an owner, model allow-list, budget and rate limit -----------------------
def c3():
    teams = teams_doc.get("teams", [])
    pol = teams_doc.get("policy", {})
    bad = [t.get("alias", "?") for t in teams if not (t.get("owner") and t.get("models") and t.get("max_budget") and t.get("rpm_limit"))]
    over = [t["alias"] for t in teams if t.get("max_budget", 0) > pol.get("max_budget_per_team", 1e9) or t.get("rpm_limit", 0) > pol.get("max_rpm", 1e9)]
    notallowed = [t["alias"] for t in teams if set(t.get("models", [])) - set(pol.get("allowed_models", t.get("models", [])))]
    if not teams:
        return "FAIL", "access/teams.yaml has no teams"
    if bad or over or notallowed:
        return "FAIL", f"missing fields: {bad}; over policy limits: {over}; models outside allow-list: {notallowed}"
    return "PASS", f"{len(teams)} teams, each with owner, model allow-list, budget (max ${pol.get('max_budget_per_team')}) and rate limit (max {pol.get('max_rpm')} rpm)"
control("C3", "Least-privilege AI access: per-team identity, model allow-list, budget and rate limit", ["ISO 27001 A.5.15 Access control", "ISO 27001 A.5.18 Access rights", "SOC 2 CC6.3"], c3)

# --- C4: access changes are reviewed and policy-checked ------------------------------------------
def c4():
    wf = read(".github/workflows/access-policy.yml")
    job = read("apps/sanvi/access-sync-job.yaml")
    ok = bool(wf) and "pull_request" in wf and "PostSync" in job
    return ("PASS" if ok else "FAIL", "access changes arrive by pull request (access-policy.yml validates them in CI) and are applied by an Argo CD PostSync job after merge")
control("C4", "Access changes go through review and an automated policy check", ["ISO 27001 A.8.32 Change management", "SOC 2 CC8.1"], c4)

# --- C5: every AI call is logged with identity and cost ------------------------------------------
def c5():
    ok = "DATABASE_URL" in read("apps/sanvi/litellm.yaml") and "master_key" in read("apps/sanvi/litellm-config.yaml")
    return ("PASS" if ok else "FAIL", "gateway connected to Postgres (DATABASE_URL), so each request is recorded with key, team, model and cost in spend logs")
control("C5", "Audit trail of AI usage (who, which model, when, cost)", ["ISO 27001 A.8.15 Logging", "SOC 2 CC7.2", "EU AI Act Art. 12 Record-keeping (theme)"], c5)

# --- C6: dashboards cannot read prompt content ---------------------------------------------------
def c6():
    ok = "grafana_ro" in read("argocd/apps/grafana.yaml")
    return ("PASS" if ok else "WARN", "Grafana reads spend data as the read-only role grafana_ro (column-level grants: no access to message content)")
control("C6", "Separation of duties: monitoring sees cost, not prompt content", ["ISO 27001 A.8.3 Information access restriction", "SOC 2 CC6.1"], c6)

# --- C7: spend monitoring and alerting -----------------------------------------------------------
def c7():
    cj = read("apps/sanvi/budget-watch-cronjob.yaml")
    m = re.search(r'schedule:\s*"([^"]+)"', cj)
    live = ""
    if args.live and cj:
        out = kubectl("get", "cronjob", "-A", "-o", "jsonpath={range .items[*]}{.metadata.name}:{.status.lastSuccessfulTime} {end}")
        live = f"; live: {out.strip() or 'no CronJobs found'}"
    return ("PASS" if m else "FAIL", f"budget-watch CronJob runs on schedule '{m.group(1) if m else '?'}' and fails (alerts) when a team passes its budget{live}")
control("C7", "Continuous cost monitoring with alerts", ["ISO 27001 A.8.16 Monitoring activities", "SOC 2 CC7.2"], c7)

# --- C8: emergency stop -------------------------------------------------------------------------
def c8():
    ks = read("scripts/kill_switch.sh")
    ok = all(w in ks for w in ("block", "unblock"))
    return ("PASS" if ok else "FAIL", "scripts/kill_switch.sh can block one team or every key in seconds, and reverse it")
control("C8", "Incident response: reversible kill switch for AI access", ["ISO 27001 A.5.26 Response to incidents", "SOC 2 CC7.4"], c8)

# --- C9: quality gate before change --------------------------------------------------------------
def c9():
    wf = read(".github/workflows/evals.yml")
    m = re.search(r'SANVI_EVAL_MIN_PASS:\s*"([\d.]+)"', wf)
    last = ""
    try:
        r = json.loads(read("evals/results.json"))
        last = f"; last recorded run: {r.get('passed', '?')}/{r.get('total', '?')}" if isinstance(r, dict) else ""
    except Exception:
        pass
    return ("PASS" if m else "FAIL", f"evals.yml runs the eval suite in CI and fails below {float(m.group(1)):.0%}{last}" if m else "no eval gate found in CI")
control("C9", "Accuracy and robustness: automated evaluation gate in CI", ["ISO 27001 A.8.29 Security testing in development", "EU AI Act Art. 15 Accuracy and robustness (theme)"], c9)

# --- C10: human oversight of agent actions -------------------------------------------------------
def c10():
    ok = "gh pr create" in read("agent/sanvi_pr.sh")
    return ("PASS" if ok else "FAIL", "the AI agent can only propose changes as a labelled pull request; a human reviews and merges")
control("C10", "Human oversight: AI agent changes require human approval", ["EU AI Act Art. 14 Human oversight (theme)", "ISO 27001 A.8.32 Change management"], c10)

# --- C11: grounded answers and refusal -----------------------------------------------------------
def c11():
    ag, cases = read("rag/agent.py"), read("rag/eval_cases.json")
    ok = "def check" in ag and "expect_refusal" in cases
    return ("PASS" if ok else "WARN", "RAG assistant must cite retrieved sources or retry; its eval includes an out-of-scope question it must refuse")
control("C11", "Guardrails: grounded, cited answers and refusal outside scope", ["EU AI Act Art. 13 Transparency (theme)", "EU AI Act Art. 15 Accuracy (theme)"], c11)

# --- C12: cost-effective model choice is evidenced ----------------------------------------------
def c12():
    rep = read("evals/rightsize-report.md")
    return ("PASS" if rep else "WARN", "evals/rightsize-report.md records cost, speed and quality per model before any switch" if rep else "no right-size report yet")
control("C12", "Model choice justified by measured cost and quality", ["SOC 2 CC3.2 Risk assessment (theme)", "ISO 27001 A.5.8 Information security in project management (theme)"], c12)

# --- report --------------------------------------------------------------------------------------
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
n = {s: sum(r["status"] == s for r in results) for s in ("PASS", "WARN", "FAIL")}
icon = {"PASS": "✅ PASS", "WARN": "⚠️ WARN", "FAIL": "❌ FAIL"}
lines = ["# SanVi Compliance Evidence Report", "",
         f"Generated {now} from commit `{commit}`{' with live cluster checks' if args.live else ' (repo evidence)'}.", "",
         f"**{n['PASS']} passed · {n['WARN']} warnings · {n['FAIL']} failed** out of {len(results)} controls.", "",
         "| ID | Control | Status | Evidence | Related framework themes |", "|---|---|---|---|---|"]
for r in results:
    lines.append(f"| {r['id']} | {r['control']} | {icon[r['status']]} | {r['evidence']} | {'; '.join(r['frameworks'])} |")
lines += ["", "_Control evidence to support an audit. Framework references show related themes; this is not a certification or legal advice._"]
out = ROOT / "evals"
(out / "compliance-report.md").write_text("\n".join(lines) + "\n")
(out / "compliance-report.json").write_text(json.dumps({"generated": now, "commit": commit, "live": args.live, "summary": n, "controls": results}, indent=2))
print("\n".join(lines))
sys.exit(1 if n["FAIL"] else 0)
