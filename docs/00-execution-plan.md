# Execution plan: road to submission

This file is the single place that ties the assignment text
(`docs/assignment.md`) to the ticket board (`docs/TICKETS.md` / GitHub
Issues) and states, in one place, when the project is actually done. It does
not replace the other `docs/0N-*.md` files — it points at them. For what B0
actually found on the real schedule page, see
[`docs/B0-real-data-findings.md`](B0-real-data-findings.md) — that file kept
its own name because it is ticket-specific evidence, not the master plan.

Ticket numbers below are GitHub issue numbers. `#34` (`B0`, now closed) and
`#35` (`C0`) are new tickets opened by this gap analysis; every other ticket
already existed.

## 1. Requirement coverage matrix

Legend: **Ticket** = closes/produces the evidence. **Evidence** = the
artifact a grader (or we, at the defence) can point at.

### Part A — existing MCP server (Playwright)

| Requirement | Ticket | Evidence |
|---|---|---|
| Configure the server as an MCP connection | B1 (#9, closed) | `agent/config.py` + `python -m agent.run --discover-only` output |
| Discover and call ≥1 of its tools | B1 (#9, closed), B0 (#34, closed) | `docs/playwright-tools.json` dumped from the live server |
| Incorporate a tool result into a later step / final output | B2 (#10), B3 (#11) | captured markup feeds `ingest_timetable_snapshot`; traced in `docs/06-architecture.md` |
| Inspect and explain the tool contract (name, description, args, result, errors, side effects) | C3 (#18) | `docs/03-tool-contracts.md`, last section |
| Explain why this server has a reasonable role | C4 (#19) | `docs/04-design-rationale.md`, "Why Playwright MCP is the relevant existing server" |
| Demonstrate one realistic failure during defence | D3 (#26), C5 (#20) | Segment 4 of `docs/05-demo-checklist.md` |
| Real public, no-login page actually confirmed (not the `.env.example` placeholder) | **B0 (#34) — closed** | `https://schedule.kse.ua/?date=...&discipline=...`, confirmed live via Playwright MCP; see `docs/B0-real-data-findings.md` |

**Note from B0's findings** (see the linked file for the full detail): the
real page is a CSS grid keyed by discipline search, not a browsable table —
teacher/room are hidden unless logged in, and course-relative `гр.N` group
numbers do not map cleanly onto this project's `BE-3-1`-style group codes.
B2, C3, and D2 all need to account for this; it is not optional polish.

### Part B — custom MCP server

| Requirement | Ticket | Evidence |
|---|---|---|
| Runs in a separate process | A1/A2 (#2, #3, done) | `python -m mcp_servers.schedule_mcp.server` in its own terminal |
| Independently startable during defence | D1 (#24), C5 (#20) | Segment 1 of the demo script |
| ≥3 distinct substantive tools | A3, A4, A5 (#4, #5, #6) | 5 tools total (with A1/A2); `python scripts/verify_mcp.py` |
| Explicit input/output schema per tool | A1/A2 done, A6 (#7) | `mcp_servers/schedule_mcp/schemas.py` |
| ≥1 tool accessing a primary data source | A1 (#2, done) | `ingest_timetable_snapshot` |
| Public no-auth API **or** local/downloadable dataset | already chosen: local dataset | `data/` + fixtures; network only via Playwright, not the custom server |
| Used in a complete, meaningful workflow | B3, B4 (#11, #12) | `agent/graph.py`, the replan loop |
| Errors distinguishable from a successful empty result | A7 (#8, done) | `docs/03-tool-contracts.md` error table; `{ok,data,warnings}` / `{ok:false,error{...}}` envelope |
| Substantive-tool criteria (domain purpose, meaningful processing, designed contract, distinct responsibility, observable contribution) | A3, A4, A5 | conflicts/optimize/compare are computation, not retrieval — see `docs/04-design-rationale.md` |
| ≥2 of the three required tools go beyond search/retrieval | A3, A4, A5 | `detect_schedule_conflicts`, `optimize_attendance_plan`, `compare_attendance_plans` — none is a search tool |

### Part C — tool-contract documentation (all eight rows, custom and existing)

| Contract row | Custom server ticket | Existing server ticket |
|---|---|---|
| Name | C2 (#17) | C3 (#18) |
| Purpose | C2 (#17) | C3 (#18) |
| Model-facing description (verbatim) | C2 (#17) | C3 (#18) |
| Input schema | C2 (#17) | C3 (#18), from `docs/playwright-tools.json` |
| Output schema | C2 (#17) | C3 (#18) |
| Error conditions | C2 (#17), A7 (#8) | C3 (#18) |
| Side effects | C2 (#17) | C3 (#18) |
| Example (real captured input/output pair) | C2 (#17) | C3 (#18) |

### Part D — operational requirements

| Requirement | Ticket | Evidence |
|---|---|---|
| No credentials/tokens/secrets committed | C7 (#22) | `git log -p` sweep, CI secret scan |
| Env vars / ignored local config for env-specific settings | C7 (#22), already scaffolded | `.env.example`, `.gitignore` |
| Respect published rate limits | B2 (#10), C7 (#22) | `SCRAPE_MIN_INTERVAL_SEC` |
| Network API → recorded genuine fixtures + documented replay/offline mode | B5 (#13), C6 (#21) | `fixtures/`, `fixtures/README.md`, `OFFLINE_MODE` |
| Fixtures preserve the real parsing path | C6 (#21) | explicit statement + proof in `fixtures/README.md`; B0 already committed one real capture (`fixtures/playwright/kse_schedule_real_2026-09-10.html`) parsed through the production parser, not a stand-in |
| Local/downloadable dataset with no runtime network need → dataset is the deterministic demo input | already true for the custom server | `data/` is the deterministic input; fixtures cover the Playwright leg separately |
| Repository contains everything needed to reproduce the demo | C1 (#16), D1 (#24), D4 (#27) | fresh-clone rehearsal by a second machine |

### Submission checklist (items 1–7)

| Item | Ticket | Evidence |
|---|---|---|
| 1. Agent integration + MCP config, secrets removed | C7 (#22) | `.env.example`, `agent/config.py` |
| 2. Custom MCP server source | A1–A7 (#2–#8) | `mcp_servers/schedule_mcp/` |
| 3. README: prerequisites, install, config, independent start commands | C1 (#16) | `README.md` |
| 4. Tool-contract documentation | C2 (#17), C3 (#18) | `docs/03-tool-contracts.md` |
| 5. Recorded API fixtures + replay instructions | C6 (#21) | `fixtures/`, `fixtures/README.md` |
| 6. Design rationale (relevance, tool boundary, workflow support, trade-offs) | C4 (#19) | `docs/04-design-rationale.md` |
| 7. Defence/demo checklist or script | C5 (#20), **C0 (#35) — new** | `docs/05-demo-checklist.md` |

### Demonstration steps (1–9)

| # | Step | Ticket | Evidence |
|---|---|---|---|
| 1 | Start the custom MCP server independently | D1 (#24), C5 (#20) | Segment 1 |
| 2 | Show the agent discovers both connections | B1 (#9, closed), C5 (#20) | `--discover-only` output |
| 3 | Invoke a tool from the existing server successfully | B2 (#10) | Segment 2 |
| 4 | Existing server's result affects a later step / final output | B3 (#11) | Segment 2 trace |
| 5 | Briefly explain that tool's contract and role | C3 (#18), C5 (#20) | Segment 2 narration |
| 6 | Run one complete workflow using the custom server | B4 (#12), C5 (#20) | Segment 3 |
| 7 | Show evidence that ≥3 custom tools are exposed | A6 (#7) | `scripts/verify_mcp.py` output on screen |
| 8 | Explain one important custom tool contract + design decision | C5 (#20) | Segment 3 "Explain one contract decision in depth" |
| 9 | Demonstrate one realistic failure of the existing server | D3 (#26), C5 (#20) | Segment 4 |
| — | Format actually chosen and rehearsed (live vs recorded), recording pipeline verified | **C0 (#35) — new** | see below |

### Assessment rubric (six sections, 100 pts)

| Section | Points | Primary tickets |
|---|---:|---|
| 1. MCP architecture and protocol correctness | 25 | A1/A2 (done), B1 (#9, closed), B0 (#34, closed), D1 (#24) |
| 2. Documentation and design rationale | 25 | C1–C4 (#16–#19) |
| 3. Custom tool and schema design | 18 | A3–A7 (#4–#8) |
| 4. Integration into the agent workflow | 14 | B3, B4 (#11, #12) |
| 5. Existing-server integration and failure demo | 10 | B1, B5, D3 (#9, #13, #26) |
| 6. Operational robustness and responsible data access | 8 | C6, C7 (#21, #22) |
| — self-check that all six actually hold | — | C8 (#23) |

### Minimum-condition rule (four conditions — none may fail)

| Condition | Ticket | Evidence |
|---|---|---|
| ≥3 qualifying custom tools exposed | A3–A5 (#4–#6) | `verify_mcp.py` shows 5 |
| A qualifying primary data-source tool exists | A1 (#2, done) | `ingest_timetable_snapshot` |
| Both MCP connections can be called successfully | B1 (#9, closed), B0 (#34, closed) | discovery confirmed for both; schedule-mcp invoked live; **Playwright's `capture_timetable` is still `NotImplementedError` (B2, #10) — this condition does not fully hold until B2 lands** |
| Agent incorporates both servers into its flows | B3, B4 (#11, #12) | `agent/graph.py` — **currently fails before node 1 runs; see the rubric-auditor baseline on tracking issue #37** |

As of this writing two of the four minimum conditions are not yet actually
satisfied end to end (both are B2/B4 work, already in flight). This is
expected at this point in the schedule, not a regression — flagged here so
"the matrix says covered" is never mistaken for "the matrix says done."

### Explicitly unacceptable submissions — how each is avoided

| Unacceptable pattern | Why we do not hit it |
|---|---|
| Existing connection configured but unused | Playwright's captured markup is consumed by `ingest_timetable_snapshot` and drives `detect_timetable_changes` → `replan_required`; it is not a standalone demo call (B2, B3). |
| Custom "server" as functions inside the agent process | `mcp_servers/schedule_mcp` is a separate OS process over stdio; it never imports from `agent/`, and D1 verifies process separation from a fresh clone. |
| Hard-coded demo answers presented as tool results | Fixtures replay through the same parser as live markup (C6 DoD requires an explicit statement + proof); B0 already committed one real capture parsed through the production code path; the optimizer and comparator compute from data, no LLM inside a tool (A4, A5). |
| Secrets committed | C7 sweeps `git log -p` for key patterns; `.env` is git-ignored; `.env.example` holds no real values. |
| External server outside the approved list / unmaintained substitute | Playwright MCP (`microsoft/playwright-mcp`) is on the approved list; B1 pins and records the exact version used. |

## 2. Critical path and day-by-day sequence

Unchanged from `docs/01-plan.md`'s critical path, with the two new tickets
inserted where they actually block work. B0 has already landed, ahead of
this sequence:

```
day 1   B0 (done)      (parallel with whatever A/C work remains)
day 2   B1 (done), B2   C1, C7
day 3   B3             C6
day 4   B4             C2, C3
day 5   B5, B6         C4
day 6   B7             C0, C5, C8
day 7   D1, D2, D3, D4                    ← rehearsal + submission
```

Critical path now: **B2 → B3 → B4 → D1 → D2 → D4**, with **C0 → C5** feeding
into D2/D3 rehearsal timing and **A-track already closed**, so it no longer
gates anything.

If track A had still been open this would matter; it is not — A1–A7 are all
closed. The only remaining gate on Track A's side is that nobody touches
`mcp_servers/` again except in response to something the B-track integration
surfaces (B0 already needed one such change: the grid-page fallback in
`domain/parser.py`).

## 3. Machine allocation

| Machine | Owns | Picks up next |
|---|---|---|
| `laptop-a` | Track A (`mcp_servers/`) — closed. Available for **Track D** (integration/rehearsal) once B4 lands, or for whichever track is free per `bash scripts/next_ticket.sh`. | B2 (#10) if Track B needs a second pair of hands, otherwise pick up a ready Track C ticket (C1, C7, or C0). |
| `laptop-b` | Track B (`agent/`) | B2 (#10) — now unblocked, since B0 and B1 are both closed. |
| Whichever machine is free | Track C (`docs/`, `fixtures/`, `README.md`) | C1, C7 are `status:ready` now; C0 (#35) is also `status:ready` and should be picked up early since it gates C5's segment timing. |

Track ownership stays as defined in `CLAUDE.md`: A → laptop-a, B → laptop-b,
C → whichever machine is free. C0 stays inside `docs/`, so it does not create
a new cross-track conflict surface.

## 4. Definition of ready-to-submit

The project may be handed in only when **all** of the following hold, each
with its own command or file as proof:

1. **No open ticket labelled `rubric`.**
   `gh issue list --state open --label rubric` returns nothing.
2. **Minimum-condition rule fully satisfied.**
   `python scripts/verify_mcp.py` shows 5 tools; `python -m agent.run --discover-only` shows both connections; `python -m agent.run --offline` completes end to end with both servers contributing to the state (not just discovered).
3. **`docs/07-rubric-selfcheck.md` has no empty Evidence cell.**
   Owned by C8 (#23); this is the actual scoring proxy — if a row cannot be filled with a file path or command, defence readiness is not real yet.
4. **C0 is closed before C5/D2 are attempted.**
   Otherwise the demo script is written against an undecided defence format and an unverified recording pipeline. (B0, the matching gap for the target page, is already closed.)
5. **A from-scratch clone reproduces the offline demo, run by a machine that did not write the code.**
   D1 (#24)'s DoD; this is the only realistic test of "the repository contains all instructions and non-sensitive resources required to reproduce the demonstration."
6. **The failure demonstration is honest, not staged-and-recovered.**
   `degraded_reason` visible in output, stated out loud (D3, #26).
7. **The recording (if that format is chosen) exists as one continuous take and fits 10–15 minutes.**
   C0 (#35)'s DoD; verified with a dry run before the real recording.
8. **PR merged for every ticket, `main` green on CI.**
   `gh pr list --state open` is empty; `gh run list --branch main --limit 1` is green.

## 5. Risks

| Risk | Likelihood | What we do |
|---|---|---|
| The course-relative `гр.N` group numbering on the real page never reconciles cleanly with this project's `BE-3-1`-style group codes. | Medium-high — B0 found no data-level link between the two. | Document an explicit, stated mapping assumption for the demo's chosen courses rather than trying to solve it generally; say so out loud at the defence as a known limitation, per `docs/04-design-rationale.md`'s trade-offs section. |
| University changes the page layout again between now and the defence, breaking both the table and the grid-fallback selectors. | Medium — the whole project already assumes this happens mid-semester. | This is exactly what `detect_timetable_changes` and the fixture-switch demo are built to demonstrate; re-verify the selector once, right before recording (part of C0's dry run), and keep the offline fallback (`fixtures/playwright/kse_schedule_real_2026-09-10.html`) current. |
| `teacher`/`room` stay hidden behind the login wall, so B3/B6's final report can never state them for real (non-fixture) data. | High — confirmed structural, not a bug. | State this as a documented limitation rather than working around it with a login flow, which the assignment explicitly discourages ("no credentials" boundary in `docs/04-design-rationale.md`). |
| B2 needs to drive the discipline search per course rather than reading one unfiltered page, multiplying the number of Playwright calls per run. | Medium | Budget for it explicitly in B2/B3's implementation and in D2's live-page rehearsal timing; `docs/B0-real-data-findings.md` already recommends navigating straight to `?discipline=CODE` instead of typing into the search box, which keeps this to one call per course. |
| C0's format decision gets deferred until the last week, and the dry run reveals the script overruns 15 minutes. | Medium | C0 is scheduled early (day 1–2 of the remaining C-track work) specifically so a timing problem surfaces while there is still time to trim `docs/05-demo-checklist.md`, not the night before submission. |
| A rubric gap surfaces late because `docs/07-rubric-selfcheck.md` was filled in optimistically rather than with real evidence. | Medium | C8 is explicitly the last C-track ticket before D-track rehearsal; D1's DoD requires "every deviation from the script filed as a ticket," which is the safety net if C8 missed something. The zero-point rubric-auditor baseline on tracking issue #37 already found one such gap (the graph currently fails at node 1) before it could hide until C8. |
| Auto-merge on a PR that happens to touch `.github/`, `schemas.py`, or `scripts/` (including this plan's edits to `scripts/tickets.json`). | Certain for *this* PR. | This PR is explicitly submitted without `--auto` per `CLAUDE.md`'s exception, and merged by hand after review. |
