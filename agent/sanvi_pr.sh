#!/usr/bin/env bash
# SanVi PR step: turn a validated agent output (out/<app>) into a reviewable pull request.
# Never pushes to main. Files go to generated/<app>, which Argo CD does not watch.
# Usage: agent/sanvi_pr.sh <app-name> ["original request"]
set -euo pipefail
APP=${1:?usage: sanvi_pr.sh <app-name> [\"request\"]}
ASK=${2:-"(request not recorded)"}
SRC="out/$APP"
ALLOWED=${SANVI_ALLOWED_REPOS:-sandhilk/sanvi-gateway}
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

# --- guard rails ---
[[ "$APP" =~ ^[a-z0-9-]+$ ]] || { echo "STOP: invalid app name"; exit 1; }
[[ -f "$SRC/Dockerfile" && -d "$SRC/chart" ]] || { echo "STOP: no agent output in $SRC"; exit 1; }
[[ ",$ALLOWED," == *",$REPO,"* ]] || { echo "STOP: $REPO is not in SANVI_ALLOWED_REPOS"; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "STOP: uncommitted changes - commit or stash first"; exit 1; }

# --- re-validate as proof for the reviewer ---
helm lint "$SRC/chart" >/tmp/sanvi_lint.txt 2>&1 || { cat /tmp/sanvi_lint.txt; echo "STOP: helm lint failed"; exit 1; }
helm template "$APP" "$SRC/chart" | kubeconform -strict -ignore-missing-schemas -summary >/tmp/sanvi_kc.txt 2>&1 \
  || { cat /tmp/sanvi_kc.txt; echo "STOP: kubeconform failed"; exit 1; }
if grep -qE '^USER[[:space:]]+(root|0)([[:space:]]|$)' "$SRC/Dockerfile"; then echo "STOP: Dockerfile runs as root"; exit 1; fi
ROOT=$(grep -qE '^USER ' "$SRC/Dockerfile" && echo "PASS: non-root USER set" || echo "WARN: no USER line")

# --- branch, copy, commit, push ---
BASE=$(git rev-parse --abbrev-ref HEAD)
BR="sanvi/$APP-$(date +%Y%m%d-%H%M%S)"
git switch -q -c "$BR"
mkdir -p generated && rm -rf "generated/$APP" && cp -r "$SRC" "generated/$APP"
git add -f "generated/$APP"
git commit -q -m "sanvi-agent: add $APP (Dockerfile + Helm chart)"
git push -q -u origin "$BR"

# --- PR with a reviewer summary ---
FILES=$(cd generated && find "$APP" -type f | sort | sed 's/^/- `/; s/$/`/')
cat > /tmp/sanvi_pr_body.md <<BODY
**Opened by the SanVi Launch agent. A human must review before merge.**

### Request
> $ASK

### Files (\`generated/$APP/\`)
$FILES

### Validation (re-run before opening this PR)
- helm lint: \`$(tail -1 /tmp/sanvi_lint.txt)\`
- kubeconform: \`$(tail -1 /tmp/sanvi_kc.txt)\`
- Dockerfile: $ROOT

### Safety
- Opened on a branch; the agent never pushes to \`main\`.
- \`generated/\` is **not** watched by Argo CD, so merging does not deploy anything.
- Allowed repos only (\`SANVI_ALLOWED_REPOS\`).
BODY
gh label create sanvi-agent --color 6f42c1 --description "Opened by the SanVi Launch agent" >/dev/null 2>&1 || true
URL=$(gh pr create --base main --head "$BR" --label sanvi-agent \
      --title "sanvi-agent: deploy $APP (Dockerfile + Helm chart)" --body-file /tmp/sanvi_pr_body.md)
git switch -q "$BASE"
echo "PR opened: $URL"
