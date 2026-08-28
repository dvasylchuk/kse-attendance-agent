# Instructions for Claude Code working in this repository

This project is worked by **one GitHub account from several machines**, each
running its own Claude Code session. There are no collaborators — every commit,
branch and PR belongs to the same account. That makes GitHub Issues, not chat,
the only place where sessions coordinate.

## 0. Identify this session, every time

Each machine has a stable session name. Read it from the environment:

```bash
echo "$AGENT_NAME"          # e.g. laptop-a, laptop-b, desktop
```

If it is empty, ask the user for a short name and tell them to set it
permanently before doing anything else:

```powershell
# PowerShell, once per machine
[Environment]::SetEnvironmentVariable("AGENT_NAME", "laptop-b", "User")
```

```bash
# macOS / Linux, once per machine
echo 'export AGENT_NAME=laptop-b' >> ~/.zshrc
```

The session name goes into every claim comment and every branch name. Without
it, two machines cannot tell each other apart and will collide.

## 1. Before anything else

```bash
git switch main && git pull --ff-only
gh auth status
bash scripts/next_ticket.sh                 # what is free right now
gh pr list --state open                     # what another machine has in flight
```

Never start work that is not attached to an open issue. If the work has no
ticket, create one first (`gh issue create --template task.yml`).

## 2. Take exactly one ticket

```bash
bash scripts/next_ticket.sh track:A-server        # or track:B-agent / track:C-docs
gh issue comment <N> --body "/take $AGENT_NAME"
```

Then **wait for the bot's reply and read it.** It either confirms the claim and
prints the branch name, or it refuses because the ticket is blocked or another
session already holds it. If it refuses, take a different ticket — never
proceed anyway. A ticket claimed by another machine is being edited right now
on a filesystem you cannot see.

Work on one ticket at a time. Finish it before taking the next.

## 3. Branch

```bash
git switch -c "$AGENT_NAME/a3-detect-schedule-conflicts-12"
```

The session prefix is not decoration: it is how you tell your own stale branch
from a branch another machine pushed.

## 4. Do the work

- The **contract comes first**. Schemas in `mcp_servers/schedule_mcp/schemas.py`
  are frozen. If a ticket genuinely requires changing one, change
  `docs/03-tool-contracts.md` in the same commit and say so in the PR.
- Each stub file's docstring is the specification for that ticket. Read it fully
  before writing code — it already fixes the algorithm and the edge cases.
- Follow the shape of the two reference implementations
  (`tools/ingest.py`, `tools/changes.py`): `ok(...)` on success, `ToolError` on
  failure, warnings for row-level tolerance, and an empty collection for an
  empty result.
- **Stay inside your track's directory.** Track A owns `mcp_servers/`, track B
  owns `agent/`, track C owns `docs/` and `README.md`. Touching another track's
  files is how two machines produce a conflict neither of them can see coming.
- Add tests in `tests/` for every branch you introduce. CI runs offline, so no
  test may open a socket or start a browser.

## 5. Check before pushing

```bash
ruff check .
pytest -q
python scripts/verify_mcp.py
python -m agent.run --offline          # once track B has landed B4
```

## 5b. Run the review agents before you open the PR

This project has one GitHub account, so **no human ever approves a PR**. The
subagents in `.claude/agents/` are the review gate that replaces one. They are
committed to the repository, so every machine has the same ones.

Always, on every ticket:

```
Use the code-reviewer agent on the diff against main for ticket #<N>.
```

Fix everything it marks Critical. Fix Should-fix items or say in the PR body why
you did not. Only then open the PR.

Additionally:

- after implementing or changing any MCP tool, or before tickets C2, A7, D4:
  `Use the mcp-contract-auditor agent.`
- at the end of a milestone, and before tickets C8 and D4:
  `Use the rubric-auditor agent.`

These agents report; they never edit. Applying their findings is your job, in
the same branch, before the PR.

## 6. Open the PR and let it merge itself

```bash
git push -u origin HEAD
gh pr create --fill --body "Closes #<N>

Session: $AGENT_NAME

## Evidence
<paste the command output that proves the DoD>"

gh pr merge --squash --delete-branch --auto
```

There is **no required review** — a single account cannot approve its own pull
request, so CI green is the gate. `--auto` merges the moment CI passes.

**Exception: `--auto` is not allowed for a PR that touches `.github/`,
`schemas.py`, or anything under `scripts/`.** A PR touching any of those is
merged by hand, only after a human has read the diff. Reason: there is no
human review on this project at all, and these three spots are where a mistake
costs the most — CI/workflow permissions, the frozen tool contract, and the
scripts every machine trusts and runs unattended.

Tick every DoD checkbox in the issue before merging. A PR that does not close an
issue, or that leaves DoD boxes unticked, is not finished.

## 7. After the merge

The issue closes, and the `unblock-dependents` workflow turns every ticket whose
dependencies are now satisfied into `status:ready` and comments on it. **That
comment is the signal for the next session — on this machine or another — to
start.**

Report to the user: which ticket closed, which tickets it unblocked, and what
the next session should pick up.

## 8. Picking up work another machine left behind

```bash
git switch main && git pull --ff-only
gh issue list --state closed --limit 10          # what just landed
gh pr list --state merged --limit 5              # and how
gh issue list --state open --label status:ready  # newly unblocked
gh issue list --state open --label status:in-progress   # held elsewhere - do not touch
```

Read the merged PR of a dependency before starting the ticket that depended on
it: its DoD evidence tells you what the interface actually does now, which is
more reliable than the plan.

If a ticket has been `status:in-progress` for a long time and the machine
holding it is not coming back, release it with `/drop` before taking it.

## 9. Rules that are not negotiable

- Never commit `.env`, an API key, a personal access token, a real calendar, or
  a personal Obsidian vault. `data/*.sample.*` and `fixtures/` are the only data
  in git.
- Never make the offline path return a canned answer. Fixtures must go through
  the same parser as live data — this is an explicit grading criterion.
- The custom MCP server never imports from `agent/`. It is a separate process
  with no knowledge of the agent.
- `stdout` of the MCP server belongs to the protocol. Log to `stderr` only.
- Do not push to `main`. Ever — including from the machine that owns the repo.
- Do not work on a ticket you did not successfully claim.
