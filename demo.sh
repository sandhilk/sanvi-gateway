#!/usr/bin/env bash
# SanVi demo: GitOps, gateway controls, agent. Needs SANVI_ADMIN_KEY + SANVI_AGENT_KEY and the port-forward on 4000.
G=localhost:4000; H='Content-Type: application/json'
say(){ echo; echo -e "\033[1;36m▶ $1\033[0m"; sleep 2; }
call(){ curl -s -o /dev/null -w "HTTP %{http_code}\n" $G/v1/chat/completions -H "$H" ${1:+-H "Authorization: Bearer $1"} \
  -d '{"model":"sanvi-mock","messages":[{"role":"user","content":"hi"}]}'; }
clear; echo -e "\033[1;35mSanVi: an open-source AI platform for Kubernetes\033[0m"; sleep 2
say "1. The whole platform is deployed from Git by Argo CD"
kubectl -n argocd get applications
say "2. No key? Rejected."
call
say "3. A team key with a limit of 2 requests per minute"
K=$(curl -s $G/key/generate -H "Authorization: Bearer $SANVI_ADMIN_KEY" -H "$H" -d '{"key_alias":"demo-team","models":["sanvi-mock"],"rpm_limit":2}' | python3 -c "import sys,json;print(json.load(sys.stdin)['key'])")
call $K; call $K; call $K
say "4. Key leaked? Revoke it: locked out instantly."
curl -s $G/key/delete -H "Authorization: Bearer $SANVI_ADMIN_KEY" -H "$H" -d "{\"keys\":[\"$K\"]}" >/dev/null; sleep 1; call $K
say "5. The agent: one sentence in, validated deployment files out"
python3 agent/sanvi_launch.py "Deploy a Python FastAPI service called checkout on port 8080 with 2 replicas, health check at /health"
find out/checkout -type f | sort
say "6. Evals: 5 fixed prompts"
python3 -c "import json;d=json.load(open('evals/results.json'));print(f\"{d['passed']}/{d['total']} passed, avg attempts {d['avg_attempts']}, cost \${d['cost_usd']}\")"
echo; echo -e "\033[1;35mgithub.com/sandhilk/sanvi-gateway\033[0m"
