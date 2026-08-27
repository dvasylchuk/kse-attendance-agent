# Defence / demo script (10–15 minutes)

The nine numbered requirements from the assignment map onto the segments below.
Rehearse with `docs/07-rubric-selfcheck.md` open.

**Before you start recording:** three terminals open in the repo root, venv
active, `.env` filled, `.state/` deleted so the run is clean, browser windows
closed except the one you need.

---

## Segment 1 — Independent startup and architecture (2 min)

*Covers demo requirements 1, 2 and 7.*

```bash
# terminal 1 — the custom server, started BEFORE and INDEPENDENTLY of the agent
python -m mcp_servers.schedule_mcp.server
```

Say: it is a separate OS process, speaks MCP over stdio, logs to stderr because
stdout belongs to the protocol.

```bash
# terminal 2 — proof of discovery and of five exposed tools
python scripts/verify_mcp.py
```

Point at the output: five tools, each with **both** an input and an output
schema.

```bash
# terminal 3 — the existing server, also its own process
npx -y @playwright/mcp@latest --headless --isolated

# and the agent discovering both connections
python -m agent.run --discover-only
```

Show `docs/06-architecture.md` — one diagram, thirty seconds, then move on.

---

## Segment 2 — Existing MCP server inside an agent flow (2–3 min)

*Covers demo requirements 3, 4 and 5.*

```bash
python -m agent.run --home-group BE-3-1 --courses ECON301,STAT210,MGMT150,FIN220
```

Narrate as it runs:

1. the agent calls the Playwright navigate tool on the public timetable page;
2. the captured markup goes into `ingest_timetable_snapshot` — **this is the
   result being used by a later step**, not a standalone demo call;
3. name the tool contract out loud: arguments, what comes back, what can go
   wrong, and that it is read-only (see `docs/03-tool-contracts.md`, last
   section).

Then trace one value: pick a visible cell on the page, and follow it through
`raw_html → Session → PlanItem → the sentence in the report`, using the trace
in `docs/06-architecture.md`.

---

## Segment 3 — Custom MCP end-to-end workflow (3–4 min)

*Covers demo requirements 6 and 8.*

Show the full run producing: the conflict set for the home group, the optimised
plan, the comparison verdict, and the final recommendation.

Then demonstrate that the timetable changing drives the flow:

```bash
# re-run against the edited page (one class moved, one added)
python -m agent.run --offline --fixture v2 --previous-plan-id <plan id from the run above>
```

`detect_timetable_changes` reports 1 moved + 1 added, marks the affected plan
item invalid, sets `replan_required: true`, and the agent re-optimises. Say
plainly: **this is the tool result deciding the next step.**

Explain one contract decision in depth. The strongest one:

> A moved class is detected by matching a removal and an addition that share
> `(course_code, group, kind)`. If it were reported as an unrelated cancellation
> plus a new class, the plan-impact analysis would tell the student they had
> lost a class they can still attend.

Alternative if asked about schema design: why `optimize_attendance_plan` takes
`objective` as a three-value enum rather than free-form weights — a constrained
enum is something a model can select correctly; a weight vector is not.

---

## Segment 4 — Failure scenario and offline mode (2 min)

*Covers demo requirement 9.* Show **one** properly, mention the others.

```bash
# stop the Playwright MCP process in terminal 3 (Ctrl-C), then:
python -m agent.run --home-group BE-3-1 --courses ECON301,STAT210
```

Expected: the agent reports the failed connection with the cause, sets
`degraded_reason`, continues from the recorded fixture, and **states in the
final output that the data is not live**. Emphasise that it does not pretend.

Two more, each one command:

```bash
# invalid tool input — rejected by the MCP schema layer before the handler runs
python -c "…"   # see docs/07-rubric-selfcheck.md for the exact one-liner

# the optimiser has no feasible plan — the agent relaxes and retries
python -m agent.run --offline --max-campus-days 1
```

Say why the fixture is not a cheat: it goes through the same parser as live
markup (`fixtures/README.md`), so the parsing and validation path is exercised
identically.

---

## Segment 5 — Questions and one variation (3–4 min)

Be ready to do these live, without help:

| Likely request | Your move |
|---|---|
| "Use a different valid input" | `--home-group BE-3-2`, or `--max-campus-days 2`, or a different course set |
| "Give it an invalid input" | `--courses NOPE999` → `INVALID_INPUT` naming the unknown course; or `source: "nonsense"` → rejected at the schema layer |
| "Identify a side effect" | `ls .state/snapshots/ .state/plans/` — the only writes the server makes; everything else is read-only |
| "Where did this value come from?" | the trace chain in `docs/06-architecture.md` |
| "Change one configuration setting" | `SCHEDULE_TABLE_SELECTOR` in `.env`, or `min_gap_minutes` in the tool call |
| "Why is this a tool and not a prompt?" | determinism, testability, and that the substitution rule is academic policy, not style |

---

## Final checks before recording

- [ ] `rm -rf .state` so the demo starts clean
- [ ] `git status` clean — no uncommitted local hacks
- [ ] `.env` filled but **not** on screen at any point
- [ ] terminal font large enough to read on the recording
- [ ] one continuous take; only the head and tail may be trimmed
- [ ] camera on, audio checked
- [ ] you can explain every file you wrote, unaided — this is graded
