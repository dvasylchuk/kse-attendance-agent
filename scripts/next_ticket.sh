#!/usr/bin/env bash
# Print the next ticket that is free to take, optionally filtered by track.
#   bash scripts/next_ticket.sh                 # any track
#   bash scripts/next_ticket.sh track:A-server  # only the server track
set -euo pipefail
TRACK="${1:-}"
ARGS=(issue list --state open --label status:ready --limit 50
      --json number,title,labels,assignees,milestone)
[ -n "$TRACK" ] && ARGS+=(--label "$TRACK")

gh "${ARGS[@]}" | jq -r '
  map(select((.assignees|length)==0))
  | sort_by(.title)
  | if length == 0 then
      "No ready & unassigned ticket. Everything is either blocked or claimed."
    else
      .[] | "#\(.number)  \(.title)\n        milestone: \(.milestone.title // "-")\n        claim: gh issue comment \(.number) --body \"/take\""
    end'
