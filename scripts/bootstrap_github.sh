#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-shot GitHub setup. Run once, from the repository root, by the owner.
#
#   gh auth login                      # if you have not already
#   bash scripts/bootstrap_github.sh   # creates the repo, labels, milestones,
#                                      # issues, the project board and pushes
#
# Everything after this is done by the team through issues and PRs. The owner
# does not need to touch GitHub again except to press "merge" (or to let
# auto-merge do it).
# ---------------------------------------------------------------------------
set -euo pipefail

OWNER="${OWNER:-dvasylchuk}"
REPO="${REPO:-kse-attendance-agent}"
VISIBILITY="${VISIBILITY:-private}"
COLLABORATORS="${COLLABORATORS:-}"   # e.g. COLLABORATORS="teammate1 teammate2"

command -v gh >/dev/null || { echo "gh CLI is required: https://cli.github.com"; exit 1; }
command -v jq >/dev/null || { echo "jq is required"; exit 1; }
gh auth status >/dev/null || { echo "run: gh auth login"; exit 1; }

SLUG="$OWNER/$REPO"
echo "==> repository $SLUG"

if gh repo view "$SLUG" >/dev/null 2>&1; then
  echo "    already exists, reusing"
else
  gh repo create "$SLUG" --"$VISIBILITY" --description \
    "Agentic attendance planner: Playwright MCP + custom Schedule MCP server" --disable-wiki
fi

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$SLUG.git"

# ---------------------------------------------------------------------------
echo "==> first commit"
git add -A
git commit -qm "chore: project scaffold, custom MCP server, agent skeleton, docs" || true
git branch -M main
git push -u origin main

# ---------------------------------------------------------------------------
echo "==> collaborators"
for user in $COLLABORATORS; do
  gh api -X PUT "repos/$SLUG/collaborators/$user" -f permission=push >/dev/null \
    && echo "    invited $user"
done

# ---------------------------------------------------------------------------
echo "==> labels"
jq -r '.labels[] | [.name,.color,.description] | @tsv' scripts/tickets.json | tr -d '\r' |
while IFS=$'\t' read -r name color desc; do
  gh label create "$name" --color "$color" --description "$desc" --repo "$SLUG" --force >/dev/null
  echo "    $name"
done

# ---------------------------------------------------------------------------
echo "==> milestones"
jq -r '.milestones[] | [.title,.description] | @tsv' scripts/tickets.json | tr -d '\r' |
while IFS=$'\t' read -r title desc; do
  gh api "repos/$SLUG/milestones" -f title="$title" -f description="$desc" >/dev/null 2>&1 \
    && echo "    $title" || echo "    $title (exists)"
done

# ---------------------------------------------------------------------------
echo "==> issues"
MAP_FILE="$(mktemp)"          # ticket-id -> issue number
BODY_FILE="$(mktemp)"

# pass 1: create every issue
# tr strips CR here because on Windows a native jq.exe emits CRLF, which would
# otherwise get glued onto each id and break the select(.id==$id) match below.
for id in $(jq -r '.tickets[].id' scripts/tickets.json | tr -d '\r'); do
  t=$(jq -c --arg id "$id" '.tickets[] | select(.id==$id)' scripts/tickets.json)
  title=$(jq -r '.title' <<<"$t")
  track=$(jq -r '.track' <<<"$t")
  ms=$(jq -r '.milestone' <<<"$t")
  extra=$(jq -r '(.labels // []) | join(",")' <<<"$t")
  deps=$(jq -r '(.deps // []) | join(" ")' <<<"$t")

  { jq -r '.body' <<<"$t"
    echo
    echo "---"
    echo "**Ticket id:** \`$id\`"
    [ -n "$deps" ] && echo "**Depends on:** $deps (see the checklist comment below)"
    echo
    echo "Claim it by commenting \`/take\`. See \`docs/02-git-workflow.md\`."
  } > "$BODY_FILE"

  labels="$track"
  [ -n "$extra" ] && labels="$labels,$extra"
  [ -n "$deps" ] && labels="$labels,status:blocked" || labels="$labels,status:ready"

  url=$(gh issue create --repo "$SLUG" --title "$title" --body-file "$BODY_FILE" \
        --label "$labels" --milestone "$ms")
  num="${url##*/}"
  echo "$id $num" >> "$MAP_FILE"
  echo "    #$num $title"
done

# pass 2: rewrite dependency ids into real issue links, close the done ones
while read -r id num; do
  t=$(jq -c --arg id "$id" '.tickets[] | select(.id==$id)' scripts/tickets.json)
  deps=$(jq -r '(.deps // []) | join(" ")' <<<"$t")
  if [ -n "$deps" ]; then
    links=""
    for d in $deps; do
      dn=$(awk -v k="$d" '$1==k{print $2}' "$MAP_FILE")
      links="$links #$dn"
    done
    gh issue comment "$num" --repo "$SLUG" \
      --body "Blocked by:$links. When those close, remove \`status:blocked\`, add \`status:ready\` and this becomes takeable."
  fi
  if [ "$(jq -r '.state // "open"' <<<"$t")" = "closed" ]; then
    gh issue close "$num" --repo "$SLUG" --comment "Shipped in the initial scaffold - kept as a reference implementation."
  fi
done < "$MAP_FILE"

# ---------------------------------------------------------------------------
echo "==> project board"
PROJ_URL=$(gh project create --owner "$OWNER" --title "$REPO board" --format json 2>/dev/null | jq -r '.url' || true)
if [ -n "${PROJ_URL:-}" ] && [ "$PROJ_URL" != "null" ]; then
  PROJ_NUM="${PROJ_URL##*/}"
  echo "    $PROJ_URL"
  while read -r _ num; do
    gh project item-add "$PROJ_NUM" --owner "$OWNER" \
      --url "https://github.com/$SLUG/issues/$num" >/dev/null 2>&1 || true
  done < "$MAP_FILE"
  echo "    all issues added to the board"
else
  echo "    skipped (needs the 'project' scope: gh auth refresh -s project)"
fi

# ---------------------------------------------------------------------------
echo "==> branch protection on main"
gh api -X PUT "repos/$SLUG/branches/main/protection" \
  --input - >/dev/null 2>&1 <<'JSON' && echo "    enabled" || echo "    skipped (private repo on a free plan does not support protection)"
{
  "required_status_checks": {"strict": true, "contexts": ["ci"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 1},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

gh api -X PATCH "repos/$SLUG" -F allow_auto_merge=true -F delete_branch_on_merge=true >/dev/null || true

rm -f "$MAP_FILE" "$BODY_FILE"
echo
echo "Done. https://github.com/$SLUG/issues"
