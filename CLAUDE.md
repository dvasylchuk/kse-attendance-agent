# Instructions for Claude Code working in this repository

Every teammate runs their own Claude Code session against this repo. This file
is the shared protocol so three sessions can work in parallel without
colliding, and so a session can pick up where another one stopped.

## 0. Before anything else

```bash
gh auth status                       # you need the gh CLI authenticated
bash scripts/next_ticket.sh          # what is free to take right now
```

Never start work that is not attached to an open issue. If the work you want to
do has no ticket, create one first (`gh issue create --template task.yml`).

## 1. Take exactly one ticket

```bash
bash scripts/next_ticket.sh track:A-server     # or track:B-agent / track:C-docs
gh issue comment <N> --body "/take"
```

The `ticket-claim` workflow assigns you, swaps `status:ready` for
`status:in-progress`, and prints the branch name. If it answers that the ticket
is blocked or already claimed, **pick another one** — do not proceed anyway.

Work on one ticket at a time. Finish it before taking the next.

## 2. Branch

```bash
git switch main && git pull --ff-only
git switch -c a3-detect-schedule-conflicts-12      # <ticket>-<slug>-<issue number>
```

## 3. Do the work

- The **contract comes first**. Schemas in `mcp_servers/schedule_mcp/schemas.py`
  are frozen. If a ticket genuinely requires changing one, change
  `docs/03-tool-contracts.md` in the same commit and say so in the PR.
- Each stub file's docstring is the specification for that ticket. Read it fully
  before writing code — it already fixes the algorithm and the edge cases.
- Follow the shape of the two reference implementations
  (`tools/ingest.py`, `tools/changes.py`): `ok(...)` on success, `ToolError` on
  failure, warnings for row-level tolerance, and an empty collection for an
  empty result.
- Add tests in `tests/` for every branch you introduce. CI runs offline, so no
  test may open a socket or start a browser.

## 4. Check before pushing

```bash
ruff check .
pytest -q
python scripts/verify_mcp.py
python -m agent.run --offline          # once track B has landed B4
```

## 5. Open the PR

```bash
git push -u origin HEAD
gh pr create --fill --body "Closes #<N>

## Evidence
<paste the command output that proves the DoD>"
```

Tick every DoD checkbox in the issue. A PR that does not close an issue, or
that leaves DoD boxes unticked, is not ready for review.

## 6. Review someone else's PR, then merge

Any teammate can approve — the repository owner is deliberately not a required
reviewer, so nothing queues behind one person.

```bash
gh pr list --state open
gh pr review <N> --approve      # or --request-changes with specifics
gh pr merge <N> --squash --delete-branch --auto
```

When the PR merges, the issue closes, and the `unblock-dependents` workflow
turns every ticket whose dependencies are now satisfied into `status:ready` and
comments on it. **That comment is the signal for the next session to start.**

## 7. Picking up after someone else

```bash
git switch main && git pull --ff-only
gh issue list --state open --label status:ready      # newly unblocked work
gh issue list --state closed --limit 10              # what just landed
gh pr list --state merged --limit 5
```

Read the closed ticket's PR before starting a ticket that depended on it — the
DoD evidence in that PR tells you what the interface actually does now.

## 8. Rules that are not negotiable

- Never commit `.env`, an API key, a real personal calendar, or a personal
  Obsidian vault. `data/*.sample.*` and `fixtures/` are the only data in git.
- Never make the offline path return a canned answer. Fixtures must go through
  the same parser as live data — this is an explicit grading criterion.
- The custom MCP server never imports from `agent/`. It is a separate process
  with no knowledge of the agent.
- `stdout` of the MCP server belongs to the protocol. Log to `stderr` only.
- Do not push to `main`. Ever.
