#!/usr/bin/env bash
# Repair the settings of an ALREADY created repository.
#
# Run this if the repo was bootstrapped with an older version of
# bootstrap_github.sh, which required one approving review on main. A single
# GitHub account cannot approve its own pull request, so that setting
# deadlocks every PR. This script removes it and keeps CI as the gate.
#
# NOTE for dvasylchuk/kse-attendance-agent specifically: this is currently a
# no-op there. That repo is private on a free plan, so branch protection was
# never enabled on `main` in the first place (GitHub API silently refuses it)
# - there is nothing to remove. Keep this script around anyway: it becomes
# relevant the moment this repo moves to a paid plan or goes public, or for
# any other repo bootstrapped with the old required-review setting.
#
#   bash scripts/fix_repo_settings.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1

OWNER="${OWNER:-dvasylchuk}"
REPO="${REPO:-kse-attendance-agent}"
SLUG="$OWNER/$REPO"

echo "==> current protection on $SLUG:main"
gh api "repos/$SLUG/branches/main/protection" 2>/dev/null \
  | grep -E '"required_approving_review_count"|"strict"|"contexts"' || echo "    (no protection set)"

echo "==> applying: CI required, NO review required"
gh api -X PUT "repos/$SLUG/branches/main/protection" --input - >/dev/null 2>&1 <<'JSON' \
  && echo "    ok" \
  || echo "    could not set protection (private repo on a free plan does not support it) - that is fine, just never push to main directly"
{
  "required_status_checks": {"strict": true, "contexts": ["ci"]},
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

echo "==> enabling auto-merge and branch cleanup"
gh api -X PATCH "repos/$SLUG" -F allow_auto_merge=true -F delete_branch_on_merge=true >/dev/null \
  && echo "    ok"

echo
echo "Done. Verify with:  gh api repos/$SLUG/branches/main/protection"
