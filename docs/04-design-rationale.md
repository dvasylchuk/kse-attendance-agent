# Design rationale

*(Submission requirement 6. Sections marked TODO are ticket C4.)*

## Why Playwright MCP is the relevant existing server

The problem starts with data the university publishes only as a rendered page.
There is no timetable API, no feed, no export. Of the three approved servers,
Obsidian operates on notes the student writes and OpenWeather on weather —
neither can reach the source of truth this project depends on. A browser-driving
server is not a decorative addition here; without it the agent has nothing to
plan over.

It also gives a realistic, non-artificial failure surface. A scraper breaks in
ways that matter: the host is down, the page moves, the markup changes so the
selector no longer matches. Each of those produces a different observable
behaviour in the agent, which is exactly what the defence has to show.

The boundary is deliberately narrow: navigate to one public page, wait for one
selector, read. No login, no form submission, no irreversible action, and a
minimum interval between navigations.

## Why each custom tool belongs at the MCP boundary

The dividing line used throughout: **the model decides what to ask for; the
server decides what is true.** Anything that must be deterministic, testable,
or resistant to a model that wants to produce a pleasing answer lives in the
server.

- `ingest_timetable_snapshot` — the trust boundary. Raw markup is untrusted and
  changes shape; letting the model read the table directly would make every
  downstream number unverifiable. After ingest, everything is a validated
  domain object with provenance.
- `detect_timetable_changes` — comparing two versions of a timetable is exact
  work with a subtle rule (a moved class is not a cancellation plus a new
  class). A model doing this by eye across two long tables would silently miss
  rows. Its `replan_required` output is the flow's control signal.
- `detect_schedule_conflicts` — overlap arithmetic with travel buffers and
  hard/soft distinctions. Cheap to get subtly wrong in prose, trivial to test in
  code.
- `optimize_attendance_plan` — a constrained combinatorial search. This is the
  clearest case: an LLM asked to "pick the best combination" produces a
  plausible answer that is usually not optimal and never reproducible.
- `compare_attendance_plans` — the verdict must follow from the numbers, not
  from the phrasing of the question. Keeping it in the server means the model
  cannot talk itself into "supported".

Note what is *not* a tool: no generic file reader, no HTTP wrapper, no "list all
sessions". Those would be plumbing, and the assignment explicitly discounts them.

## How the tool set supports the workflow

The five tools form a loop rather than a list:

```
capture ─► ingest ─► detect_changes ──replan_required=false──► report
                          │
                          └─true─► conflicts ─► optimize ─► compare ─► report
                                                    │
                                              INFEASIBLE
                                                    │
                                        relax max_campus_days, retry
```

Two genuine feedback edges: `replan_required` decides whether the expensive
branch runs at all, and `INFEASIBLE` makes the agent change its own request and
call the same tool again with a relaxed constraint. Neither is a fixed sequence
of preselected calls.

## Trade-offs and known limitations

- **Parser coupling.** `ingest_timetable_snapshot` expects a table whose header
  names the columns. A university page that uses a grid layout instead would
  need a new adapter. Chosen deliberately: a header-driven parser is honest
  about breaking, whereas a positional parser would silently mis-assign columns.
- **Snapshot identity is content-based.** Two captures of an unchanged page
  produce the same `snapshot_id`, which makes re-runs cheap — but it also means
  a purely cosmetic edit (a renamed room) registers as a change. Acceptable: a
  false "changed" costs one re-plan, a false "unchanged" costs a missed class.
- **Substitution rule is coarse.** Topic equality is a proxy for "the same
  material". A real registry would expose session-level learning outcomes; the
  demo dataset does not, so an empty topic is treated as compatible.
- **Local `.ics` instead of a live calendar.** The assignment requires a public
  no-auth API or a local dataset, and a live calendar is neither. The cost is
  that the student must re-export the file when their commitments change.
- **The optimiser is exact only because the instance is small.** A few hundred
  candidate sessions per week make exhaustive search realistic. A
  faculty-wide timetable would need an ILP formulation or a heuristic with a
  documented optimality gap.
- **The LLM never computes.** The final report only phrases numbers already in
  the state. That keeps every figure traceable but makes the output less fluent
  than a model given freedom.

## TODO for ticket C4

- [ ] add the measured campus-day reduction from the demo dataset once A4 lands
- [ ] record the actual Playwright tool names used, from `docs/playwright-tools.json`
- [ ] state the observed runtime of one full offline run
