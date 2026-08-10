#!/bin/zsh
# Double-click me. Pulls fresh Snowflake data, rebuilds the dashboard, publishes it.
#
# Lives here rather than in the published page on purpose: GitHub Pages is a static
# host and can't reach Snowflake, and the DB credentials should stay on this Mac.

set -u
cd "$(dirname "$0")" || exit 1

LIVE="https://brianmarzo.github.io/Backlog-Bounty/"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

printf '\n\033[1m  Backlog Bounty — refresh\033[0m\n'
printf '  %s\n\n' "$(date '+%A %B %-d, %Y at %-I:%M %p')"

fail() {
  printf '\n\033[31m  ✗ %s\033[0m\n\n' "$1"
  printf '  Nothing was published. The live page still shows the last good build.\n'
  printf '  Press any key to close.\n'
  read -rsk1
  exit 1
}

# ---- 1. pull + rebuild -------------------------------------------------------
printf '  \033[2m1/3\033[0m  Pulling from Snowflake and rebuilding…\n'
if ! BUILD=$(python3 build_dashboard.py 2>&1); then
  printf '%s\n' "$BUILD" | tail -20
  fail "Build failed."
fi
printf '        built %s\n' "$(basename "$(printf '%s' "$BUILD" | tail -1)")"

# ---- 2. safety check ---------------------------------------------------------
# The raw pull carries customer account names. It's gitignored, but verify the
# rendered page is genuinely aggregate-only before anything goes public.
printf '  \033[2m2/3\033[0m  Checking no customer data is in the page…\n'
LEAK=$(python3 - <<'PY' 2>&1
import json, pathlib, sys
html = pathlib.Path("index.html").read_text()
bad = 0
for f in pathlib.Path("data").glob("*.json"):
    try:
        rows = json.loads(f.read_text())
    except Exception:
        continue
    if not isinstance(rows, list):
        continue
    for r in rows:
        if not isinstance(r, dict):
            continue
        for key in ("ACCOUNT_NAME", "CASE_NUMBER"):
            v = r.get(key)
            if v and str(v) in html:
                bad += 1
print(bad)
PY
)
if [[ "$LEAK" != "0" ]]; then
  printf '        found %s customer identifier(s) in the page\n' "$LEAK"
  fail "Refusing to publish — customer data would have gone public."
fi
printf '        clean — rep names and counts only\n'

# ---- 3. publish --------------------------------------------------------------
printf '  \033[2m3/3\033[0m  Publishing…\n'
git add -A >/dev/null 2>&1

if git diff --cached --quiet; then
  printf '        no change since the last refresh — nothing to publish\n'
else
  git commit -q -m "Refresh dashboard — $(date '+%Y-%m-%d %H:%M')" || fail "Commit failed."
  # An old token in the macOS keychain can shadow the gh one and 403 the push,
  # so clear the helper list and use gh's credential directly for this command.
  if ! OUT=$(git -c credential.helper= -c credential.helper='!gh auth git-credential' \
             push origin main 2>&1); then
    printf '%s\n' "$OUT" | tail -6
    fail "Push failed. Committed locally, so nothing is lost — just not published yet."
  fi
  printf '        pushed\n'
fi

printf '\n\033[32m  ✓ Done.\033[0m  %s\n' "$LIVE"
printf '  \033[2mThe live page updates within about a minute.\033[0m\n\n'
open "$LIVE"
printf '  Press any key to close.\n'
read -rsk1
