#!/usr/bin/env bash
# Push DRS-Bot-Host to GitHub. The token is used in-memory ONLY:
# it is never written to git config, remote URLs on disk, or any file.
#
# Usage:
#   ./scripts/push_to_github.sh <GITHUB_TOKEN> [--create]
#
#   --create  create the repository first (requires repo scope on the token)
set -euo pipefail

OWNER="CTO-DRS"
REPO="DRS-Bot-Host"
BRANCH="main"

TOKEN="${1:-}"
MODE_CREATE=false
if [[ "${2:-}" == "--create" ]]; then
  MODE_CREATE=true
fi

if [[ -z "$TOKEN" ]]; then
  echo "Usage: $0 <GITHUB_TOKEN> [--create]"
  exit 1
fi

AUTH_HEADER="Authorization: Bearer ${TOKEN}"
API="https://api.github.com"

# 1) Verify token
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH_HEADER" "$API/user")
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "ERROR: token verification failed (HTTP $HTTP_CODE)"; exit 1
fi
echo "[ok] token verified"

# 2) Optionally create the repository
if $MODE_CREATE; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST -H "$AUTH_HEADER" -H "Accept: application/vnd.github+json" \
    "$API/user/repos" \
    -d '{"name":"'"$REPO"'","description":"Host and manage Python bots on an Android phone","private":false,"has_wiki":false}')
  if [[ "$HTTP_CODE" == "201" ]]; then
    echo "[ok] repository created: $OWNER/$REPO"
  elif [[ "$HTTP_CODE" == "422" ]]; then
    echo "[ok] repository already exists"
  else
    echo "ERROR: repository creation failed (HTTP $HTTP_CODE)"; exit 1
  fi
fi

# 3) Push (credential helper disabled; token only in the one-shot URL)
git -c credential.helper= push "https://x-access-token:${TOKEN}@github.com/${OWNER}/${REPO}.git" "$BRANCH"
echo "[ok] pushed $BRANCH -> github.com/$OWNER/$REPO"
echo "     (remember to revoke this token after use — it appeared in chat)"
