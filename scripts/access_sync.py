#!/usr/bin/env python3
"""SanVi access as code: make gateway keys match access/teams.yaml.
  --validate   check the file against its policy (no gateway needed; used in CI)
  (default)    plan: show what would change
  --apply      make the changes
New keys go into Kubernetes Secrets sanvi-key-<alias> (namespace sanvi) and are never printed.
Teams removed from the file are blocked (reversible), not deleted. Keys not created by this tool are left alone."""
import argparse, json, os, re, subprocess, sys, urllib.request
import yaml

FIELDS = ("models", "max_budget", "rpm_limit", "budget_duration")
TAG = "sanvi-access"

def validate(doc):
    errs, pol, seen = [], doc.get("policy") or {}, set()
    allowed = set(pol.get("allowed_models") or [])
    for t in doc.get("teams") or []:
        a = t.get("alias", "?")
        if not re.fullmatch(r"team-[a-z0-9-]+", a): errs.append(f"{a}: alias must look like team-<name>")
        if a in seen: errs.append(f"{a}: duplicate alias")
        seen.add(a)
        if not t.get("owner"): errs.append(f"{a}: owner is required")
        bad = set(t.get("models") or []) - allowed
        if not t.get("models") or bad: errs.append(f"{a}: models must be from {sorted(allowed)} (bad: {sorted(bad)})")
        b = t.get("max_budget")
        if not isinstance(b, (int, float)) or not 0 < b <= pol.get("max_budget_per_team", 0):
            errs.append(f"{a}: max_budget must be > 0 and <= {pol.get('max_budget_per_team')}")
        r = t.get("rpm_limit")
        if not isinstance(r, int) or not 0 < r <= pol.get("max_rpm", 0): errs.append(f"{a}: rpm_limit must be 1..{pol.get('max_rpm')}")
        if not re.fullmatch(r"\d+[dhm]", str(t.get("budget_duration", ""))): errs.append(f"{a}: budget_duration like 30d")
    return errs

def api(method, path, body=None):
    req = urllib.request.Request(GW + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {ADMIN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def store_key(alias, key):
    yml = subprocess.run(["kubectl", "-n", "sanvi", "create", "secret", "generic", f"sanvi-key-{alias}",
                          "--from-file=key=/dev/stdin", "--dry-run=client", "-o", "yaml"],
                         input=key, capture_output=True, text=True, check=True).stdout
    subprocess.run(["kubectl", "apply", "-f", "-"], input=yml, capture_output=True, text=True, check=True)

def norm(k):
    return {"models": sorted(k.get("models") or []), "max_budget": k.get("max_budget"),
            "rpm_limit": k.get("rpm_limit"), "budget_duration": k.get("budget_duration")}

ap = argparse.ArgumentParser()
ap.add_argument("--file", default="access/teams.yaml")
ap.add_argument("--validate", action="store_true")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()
doc = yaml.safe_load(open(args.file))
errs = validate(doc)
if errs:
    print("POLICY FAILED:"); [print("  x", e) for e in errs]; sys.exit(1)
print(f"policy OK: {len(doc['teams'])} teams")
if args.validate:
    sys.exit(0)

GW = os.environ.get("SANVI_GATEWAY", "http://localhost:4000")
ADMIN = os.environ.get("SANVI_ADMIN_KEY") or sys.exit("Set SANVI_ADMIN_KEY")
live = {k.get("key_alias"): k for k in api("GET", "/key/list?return_full_object=true&size=100").get("keys", [])
        if isinstance(k, dict) and k.get("key_alias")}
want = {t["alias"]: t for t in doc["teams"]}
mode = "APPLY" if args.apply else "PLAN"
print(f"{mode}:")
for a, t in want.items():
    w = {"models": sorted(t["models"]), "max_budget": float(t["max_budget"]),
         "rpm_limit": t["rpm_limit"], "budget_duration": t["budget_duration"]}
    k = live.get(a)
    if not k:
        print(f"  + create {a}  ({', '.join(w['models'])}; ${w['max_budget']}/{w['budget_duration']}; {w['rpm_limit']} rpm)")
        if args.apply:
            r = api("POST", "/key/generate", {"key_alias": a, **w, "metadata": {"managed_by": TAG, "owner": t["owner"]}})
            store_key(a, r["key"]); print(f"    key stored in secret sanvi/sanvi-key-{a}")
        continue
    if (k.get("metadata") or {}).get("managed_by") != TAG:
        print(f"  ! skip {a}: exists but not managed by {TAG}"); continue
    cur = norm(k); cur["max_budget"] = float(cur["max_budget"] or 0)
    diff = {f: (cur[f], w[f]) for f in FIELDS if cur[f] != w[f]}
    if not diff:
        print(f"  = {a} unchanged"); continue
    print(f"  ~ update {a}: " + "; ".join(f"{f} {o} -> {n}" for f, (o, n) in diff.items()))
    if args.apply:
        api("POST", "/key/update", {"key": k["token"], **{f: w[f] for f in diff}})
for a, k in live.items():
    if a in want: continue
    if (k.get("metadata") or {}).get("managed_by") == TAG:
        print(f"  - block {a}  (removed from {args.file})")
        if args.apply and not k.get("blocked"): api("POST", "/key/block", {"key": k["token"]})
    else:
        print(f"  ? {a} unmanaged (left alone)")
if not args.apply:
    print("Run with --apply to make these changes.")
