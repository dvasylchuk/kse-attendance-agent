# Part C — Tool-contract documentation

Every contract below is the contract the model actually sees. The
"Model-facing description" rows are copied verbatim from
`mcp_servers/schedule_mcp/server.py`; the schemas are in
`mcp_servers/schedule_mcp/schemas.py`.

## Shared response envelope

Every tool returns the same envelope, so the caller can always tell a failure
from a successful empty result:

```jsonc
// success
{"ok": true, "data": { ... }, "warnings": ["row 3: unparsable time value '9-00'"]}

// failure
{"ok": false, "error": {"code": "PARSE_FAILED", "message": "...",
                        "details": {...}, "retryable": false}}
```

An empty result is **never** an error. `detect_schedule_conflicts` with nothing
to report returns `{"ok": true, "data": {"conflicts": [], "conflict_count": 0}}`.

Input that violates the JSON Schema is rejected by the MCP SDK **before** the
handler runs, and surfaces as `isError: true` with a message naming the field.
The agent normalises that into the same envelope with code `INVALID_INPUT`
(see `agent/tools_facade.py`).

### Error codes by tool

*Reviewed for ticket A7 against the actual `raise ToolError(...)` call sites in
`mcp_servers/schedule_mcp/` (tools + `domain/`), not from memory. Reproduce
every row below with `python scripts/repro_errors.py`.*

| Code | ingest | changes | conflicts | optimize | compare | `retryable` | Meaning |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `INVALID_INPUT` | ● | ● | ● | ● | ● | always `false` | schema-valid but domain-invalid arguments, or a required argument missing entirely (caught centrally in `server.py`) — retrying the identical call can never succeed, so this is never retryable |
| `PARSE_FAILED` | ● | | ● | ● | | always `false` | markup, dataset or `.ics` calendar could not be parsed. `conflicts` and `optimize` inherit this from `domain/calendar.py` (an invalid calendar file), not just `ingest`'s own HTML/JSON parsing |
| `DATA_SOURCE_UNAVAILABLE` | ● | | ● | ● | | always `false` | dataset or calendar file missing/unreadable; the path does not change on retry |
| `SNAPSHOT_NOT_FOUND` | | ● | ● | ● | | always `false` | unknown `snapshot_id` |
| `PLAN_NOT_FOUND` | | ● | | | ● | always `false` | unknown `plan_id` |
| `INFEASIBLE` | | | | ● | | always `false` | constraints admit no plan; relax `max_campus_days` or `min_coverage_ratio` and call again — retrying unchanged never helps |
| `INTERNAL` | ● | ● | ● | ● | ● | always `true` | unexpected, unclassified exception — the one case where blind retry is plausibly worth it |

`NOT_IMPLEMENTED` existed while A3/A4/A5 were open stubs; no tool raises it
any more (the constant stays defined in `errors.py` for any future ticket that
reopens a stub).

---

## 1. `ingest_timetable_snapshot`

| Contract element | Content |
|---|---|
| **Name** | `ingest_timetable_snapshot` |
| **Purpose** | The primary data-source tool and the only entry point for raw timetable material. The model calls it once per capture, before anything else, and passes the returned `snapshot_id` to every other tool. It is also called again on each re-check of the page, because the university edits the timetable during the term. |
| **Model-facing description** | "Parse a university timetable into a versioned, validated snapshot and return its snapshot_id. This is the entry point of the domain: every other tool takes a snapshot_id produced here. Accepts raw HTML captured from the live schedule page through Playwright MCP, a recorded fixture page, or the prepared local dataset. Normalises times, class kinds and group labels, drops duplicate rows, and reports rejected rows as warnings. Call it again whenever the university may have edited the timetable — identical content yields the same snapshot_id and is not stored twice." |
| **Input schema** | `source` (string, **required**, enum `playwright_html` \| `fixture_html` \| `local_dataset`); `raw_html` (string, ≤4 MB, required when `source=playwright_html`); `path` (string, required for the other two sources, relative to the repo root); `table_selector` (string, default `table.schedule`); `source_ref` (string, optional, provenance label). `additionalProperties: false`. |
| **Output schema** | `data.snapshot_id` (string), `captured_at` (date-time), `date_from` / `date_to` (date), `session_count` (int), `groups` (string[]), `courses` (string[]), `rejected_rows` (int), `is_new_snapshot` (bool — `false` when identical content was already stored). |
| **Error conditions** | `INVALID_INPUT` — `raw_html` empty for `playwright_html`, or `path` missing for a file source. `PARSE_FAILED` — no table matches `table_selector`, table has no header row, or every row failed normalisation (the "page layout changed" case). `DATA_SOURCE_UNAVAILABLE` — the file does not exist; `details` carries the path and the working directory. Individual bad rows are **warnings**, not errors. |
| **Side effects** | Writes `.state/snapshots/<snapshot_id>.json` and appends one line to `.state/snapshots.index.jsonl` — but only when the content is new. No network access: the markup is handed in by the caller. |
| **Example** | Input: `{"source": "local_dataset", "path": "data/schedule.sample.json"}` → Output: `{"ok": true, "data": {"snapshot_id": "snap_a1296ab47ac4", "session_count": 14, "groups": ["BE-3-1","BE-3-2","BE-3-3"], "courses": ["ECON301","FIN220","MGMT150","STAT210"], "rejected_rows": 0, "is_new_snapshot": true}, "warnings": []}` |

**Why it belongs at the MCP boundary:** it is the trust boundary. Everything
after it operates on validated domain objects, so no other tool ever has to
handle malformed HTML, and the model is never handed raw markup to interpret.

---

## 2. `detect_timetable_changes`

| Contract element | Content |
|---|---|
| **Name** | `detect_timetable_changes` |
| **Purpose** | Answers "did the university move anything, and does my current plan still hold?" It is the tool whose result decides the agent's next step: `replan_required` gates the entire optimisation branch. |
| **Model-facing description** | "Diff a freshly ingested timetable snapshot against an earlier one and report added, removed and moved classes. Given a plan_id it also reports which items of that plan the change invalidates and whether re-planning is required. Use this after every re-scrape before trusting an existing attendance plan." |
| **Input schema** | `new_snapshot_id` (string, **required**); `baseline_snapshot_id` (string, optional — defaults to the most recent stored snapshot other than the new one); `plan_id` (string, optional — enables the plan-impact section); `courses` (string[], ≤40, optional filter). |
| **Output schema** | `data.baseline_snapshot_id`, `added[]`, `removed[]`, `moved[]` (each `{from, to}` slot pair), `change_count` (int), and — when `plan_id` was given — `plan_impact: {plan_id, invalidated_items[], replan_required}`. |
| **Error conditions** | `SNAPSHOT_NOT_FOUND` for either id, with the known ids in `details`. `PLAN_NOT_FOUND` for an unknown `plan_id`. **No earlier snapshot at all is a success**, not an error: empty diffs plus the warning "no earlier snapshot exists". An unchanged timetable is likewise a success with `change_count: 0`. |
| **Side effects** | None. Read-only over `.state/`. |
| **Example** | Input: `{"new_snapshot_id": "snap_08044e32b73c", "baseline_snapshot_id": "snap_38244b758da5"}` → Output: `{"ok": true, "data": {"change_count": 2, "added": [{"session_id": "ECON301-BE-3-3-2026-09-12-1400", ...}], "removed": [], "moved": [{"from": {"session_id": "STAT210-BE-3-2-2026-09-09-1040", "room": "B-105"}, "to": {"session_id": "STAT210-BE-3-2-2026-09-11-1040", "room": "B-107"}}]}, "warnings": []}` |

**Design decision worth defending:** a "move" is not a separate record in the
data — it is inferred by matching a removal and an addition that share
`(course_code, group, kind)`. Reporting a moved class as an unrelated
removal + addition would make the plan-impact analysis lie: the class was not
cancelled, it was rescheduled, and the student still needs it.

---

## 3. `detect_schedule_conflicts` — *ticket A3*

| Contract element | Content |
|---|---|
| **Name** | `detect_schedule_conflicts` |
| **Purpose** | Establishes which candidate sessions are actually attendable, before any optimisation happens. The baseline call uses the student's own group and produces the "here is what you would miss if you changed nothing" figure. |
| **Model-facing description** | "Check candidate timetable sessions against the student's exported .ics calendar and against each other, and return typed conflicts (hard calendar clash, soft clash, session overlap, insufficient travel gap) with overlap minutes. Use it to find out which classes of the student's own group are unattendable before asking for an optimised plan. An empty conflict list is a successful result, not an error." |
| **Input schema** | `snapshot_id` (string, **required**); `session_ids` (string[], **required**, 1–500); `calendar_path` (string, default `data/calendar.sample.ics`); `min_gap_minutes` (int, 0–240, default 30 — travel/settle buffer); `include_soft` (bool, default `true`). |
| **Output schema** | `data.conflicts[]` (`{kind, session_id, against, overlap_minutes, explanation}`), `conflict_count` (int), `blocked_session_ids` (string[]), `checked_sessions` (int), `calendar_blocks` (int). |
| **Error conditions** | `SNAPSHOT_NOT_FOUND`; `INVALID_INPUT` when a `session_id` is not in the snapshot (offending ids listed in `details`); `DATA_SOURCE_UNAVAILABLE` when the `.ics` file is missing; `PARSE_FAILED` when it is not valid iCalendar. |
| **Side effects** | None. Reads the local `.ics` file; no calendar account is ever contacted. |
| **Example** | *(to be filled from a real captured call when A3 lands — see ticket C2)* |

---

## 4. `optimize_attendance_plan` — *ticket A4*

| Contract element | Content |
|---|---|
| **Name** | `optimize_attendance_plan` |
| **Purpose** | The core decision of the domain: which group's session to attend for each required course, so the student spends the fewest days on campus at an acceptable coverage. |
| **Model-facing description** | "Build an attendance plan that covers the required courses in as few days on campus as possible, allowed to substitute another study group's session of the same course when the topic matches. Honours a hard cap on campus days, a minimum coverage ratio and the student's calendar. Returns the chosen session per course, the campus days, the coverage ratio, the substitutions used and a reason for every skipped session. Fails with INFEASIBLE when the constraints admit no plan — relax max_campus_days or min_coverage_ratio and call again." |
| **Input schema** | `snapshot_id`, `home_group`, `required_courses` (1–20) — **required**; `objective` (`min_days` \| `max_coverage` \| `balanced`, default `balanced`); `max_campus_days` (int 1–6, default 3); `min_coverage_ratio` (number 0–1, default 0.7); `allow_cross_group` (bool, default `true`); `calendar_path`; `min_gap_minutes` (int 0–240, default 30). |
| **Output schema** | `data.plan_id`, `objective`, `items[]` (`{course_code, session_id, group, substituted, date, start, end}`), `campus_days[]`, `campus_day_count`, `coverage_ratio`, `covered_sessions`, `required_sessions`, `substitutions_used`, `skipped[]` (`{session_id, reason}`). |
| **Error conditions** | `SNAPSHOT_NOT_FOUND`; `INVALID_INPUT` when `home_group` is absent from the snapshot or a required course has no sessions; `INFEASIBLE` when the best achievable coverage is below `min_coverage_ratio` — `details` carries the best ratio and the binding constraint, so the agent knows *which* constraint to relax. It calls `detect_schedule_conflicts` internally to drop calendar-blocked candidates, so a `DATA_SOURCE_UNAVAILABLE` or `PARSE_FAILED` calendar failure propagates unchanged. |
| **Side effects** | Writes `.state/plans/<plan_id>.json`. Deterministic: identical input yields an identical `plan_id`. |
| **Example** | *(to be filled from a real captured call when A4 lands — see ticket C2)* |

**Why this belongs at the MCP boundary and not in the agent:** the substitution
rule (same `course_code` **and** compatible `topic`) is an academic-policy
constraint, not a prompt. Putting it in the server makes it testable,
deterministic and impossible for the model to bend when it is under pressure to
produce a nice-looking answer.

---

## 5. `compare_attendance_plans` — *ticket A5*

| Contract element | Content |
|---|---|
| **Name** | `compare_attendance_plans` |
| **Purpose** | Turns "is my preference actually achievable?" into evidence. Used to choose between the home-group baseline and the optimised plan without the model doing arithmetic. |
| **Model-facing description** | "Compare two or more attendance plans against the student's stated preference and return structured evidence: per-plan deltas in campus days, coverage and substitutions, which constraints each plan violates, a recommended plan and a verdict of supported / contradicted / inconclusive. Use it to decide between a baseline home-group plan and an optimised one instead of judging by eye." |
| **Input schema** | `plan_ids` (string[], **required**, 2–5, first is the baseline); `preference` (object, optional: `max_campus_days` 1–6, `min_coverage_ratio` 0–1, `max_substitutions` ≥0). `additionalProperties: false`. |
| **Output schema** | `data.baseline_plan_id`, `comparisons[]` (`{plan_id, campus_days_delta, coverage_delta, substitutions_delta, satisfies_preference, violated[]}`), `recommended_plan_id`, `verdict` (`supported` \| `contradicted` \| `inconclusive`), `rationale`. |
| **Error conditions** | `PLAN_NOT_FOUND` for any id. Plans built from different `snapshot_id`s do not fail — they return `inconclusive` **with a warning**, because comparing numbers across timetable versions would be misleading. |
| **Side effects** | None. |
| **Example** | *(to be filled from a real captured call when A5 lands — see ticket C2)* |

---

## The existing server: Microsoft Playwright MCP

> Ticket C3 replaces the placeholders below with the schema dumped from the
> running server into `docs/playwright-tools.json`. Do not paraphrase from
> memory — the assignment asks for the contract as this project observes it.

| Contract element | Content |
|---|---|
| **Server** | [`@playwright/mcp`](https://github.com/microsoft/playwright-mcp), started as `npx -y @playwright/mcp@latest --headless --isolated`, pinned version recorded in the README. |
| **Role in this project** | The university publishes its timetable as a rendered web page with no public API. Playwright MCP is the only approved server that can turn that page into structured text the agent can hand to `ingest_timetable_snapshot`. It is used read-only: navigate, wait, read. |
| **Tool documented** | *navigate tool* — exact name and schema from `docs/playwright-tools.json` |
| **Arguments and constraints** | *from the dumped schema* |
| **Returned content** | *from the dumped schema* — the page snapshot / accessibility tree that is passed on as `raw_html` |
| **Error conditions** | Server not started (the stdio process fails to spawn); page unreachable or DNS failure; navigation timeout; the timetable selector never appearing; the browser binary missing (`npx playwright install`). |
| **Side effects** | Starts a headless browser process, opens a network connection to the timetable host, and writes into an isolated browser profile. No cookies or credentials are supplied; nothing is submitted. Navigation is throttled by `SCRAPE_MIN_INTERVAL_SEC`. |

**Failure demonstrated at the defence:** the Playwright MCP process is not
started. The agent reports the failed connection, records
`degraded_reason`, and continues from the recorded fixture — and it says so in
the final output, so the user is never handed fixture data as if it were live.
