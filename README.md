# Attendance Planner Agent

A domain-specific data agent that decides **which study group's classes a
student should attend, on which days**, so that they cover as much of their
required coursework as possible in as few days on campus as possible, without
colliding with their personal calendar.

The university allows attending another group's session of the same course.
That turns a fixed timetable into a real combinatorial choice — and the
timetable is edited during the term, so a plan has to be re-checked whenever
the page changes.

## Architecture

```
                    ┌─────────────────────────────┐
                    │  agent (LangGraph, python)  │
                    │  MCP client for both servers│
                    └───────┬─────────────┬───────┘
             stdio          │             │          stdio
        ┌──────────────────-┘             └───────────────────┐
        ▼                                                     ▼
┌──────────────────────────┐                    ┌────────────────────────────┐
│ Playwright MCP (existing)│                    │ schedule-mcp (custom)      │
│ npx @playwright/mcp      │                    │ python -m mcp_servers...   │
│ separate process         │                    │ separate process           │
└───────────┬──────────────┘                    └─────────────┬──────────────┘
            ▼                                                 ▼
   public timetable page                        data/ dataset + .ics calendar
                                                 .state/ snapshots and plans
```

Both MCP servers run as their own OS processes, started independently of the
agent. Nothing is in-process.

| | Server | Role |
|---|---|---|
| Part A | [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp) | Reads the public timetable page. There is no public API for it, so a browser-driving server is the honest way to get the data. |
| Part B | `schedule-mcp` (this repo, `mcp_servers/schedule_mcp/`) | Five domain tools over the timetable: ingest, diff, conflict detection, optimisation, plan comparison. |

## The five custom tools

| Tool | What it does | Beyond retrieval? |
|---|---|---|
| `ingest_timetable_snapshot` | Parses, normalises, validates and versions a timetable into an immutable snapshot. Primary data-source tool. | yes — parsing, validation, dedup |
| `detect_timetable_changes` | Diffs two snapshots into added / removed / moved classes and reports which plan items a change invalidates. | yes — comparison, impact analysis |
| `detect_schedule_conflicts` | Typed conflicts against the student's `.ics` calendar and between sessions, with overlap minutes and travel buffers. | yes — domain rules |
| `optimize_attendance_plan` | Constrained optimisation: minimum campus days at a required coverage, with legal cross-group substitution. | yes — planning |
| `compare_attendance_plans` | Tests the student's stated preference against the plans and returns structured evidence and a verdict. | yes — hypothesis testing |

Full contracts: [`docs/03-tool-contracts.md`](docs/03-tool-contracts.md).

## Prerequisites

- Python 3.11+
- Node.js 18+ (only for the Playwright MCP server)
- `gh` CLI (only for working the ticket board)
- An OpenRouter API key for the agent's final report step

## Install

```bash
git clone https://github.com/dvasylchuk/kse-attendance-agent.git
cd kse-attendance-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in OPENROUTER_API_KEY and SCHEDULE_URL
```

No secret is committed. `.env` is git-ignored; `.env.example` documents every
variable.

## Target schedule page (ticket B0)

`SCHEDULE_URL` in your own `.env` should point at:

```
https://schedule.kse.ua/?date=YYYY-MM-DD&discipline=<COURSE_CODE>
```

Confirmed live, 2026-08-28: public, no login required to view a discipline's
sessions. Three things this confirmation surfaced that shape how B2 and the
domain parser have to work:

- **There is no default full-timetable view.** The page shows nothing until a
  discipline is chosen via its search box (e.g. `discipline=ECON201`); there
  is no "browse everything" mode for an anonymous visitor.
- **Teacher and room are hidden without login.** Every session card carries a
  lock icon labelled "Увійдіть, щоб побачити викладачів та аудиторії" ("Log
  in to see teachers and rooms"). `ingest_timetable_snapshot` correctly
  stores these as `null` for sessions captured from this page — it does not
  invent placeholder values.
- **The group field is course-relative, not institutional.** The page only
  exposes "гр.1" / "гр.2" (this course's own group numbering), not the
  `BE-3-1`-style group codes used elsewhere in this project's domain model.
  Sessions parsed from the real page get `GR1` / `GR2` etc.; matching that
  against a student's actual home group is not something the source page can
  answer, and is out of scope for B0.

The page is a CSS grid (`.schedule-event-card` divs inside `.schedule-grid-cell`),
not a `<table>`. `parser.html_to_rows` (in `mcp_servers/schedule_mcp/domain/`)
detects this automatically — no config change needed — and is tested against
a real capture at
[`fixtures/playwright/kse_schedule_real_2026-09-10.html`](fixtures/playwright/kse_schedule_real_2026-09-10.html)
in `tests/test_kse_grid_parser.py`. The exact CSS classes and grid layout it
depends on are recorded in
[`docs/00-execution-plan.md`](docs/00-execution-plan.md).

**Fallback if the real page's layout changes before the defence:** offline
mode (below) never depends on the live site — it replays a recorded fixture
through this same parser. If `schedule.kse.ua` changes its markup, capture a
fresh page (`python -m agent.run --discover-only` proves the connection,
then a Playwright MCP `navigate` + `evaluate(outerHTML)` captures the page),
save it under `fixtures/playwright/`, and add a test pinning the new
structure the same way `test_kse_grid_parser.py` does — the demo itself can
run entirely offline regardless.

## Start the two processes independently

**Terminal 1 — the custom MCP server** (this is what the defence starts first):

```bash
python -m mcp_servers.schedule_mcp.server
```

It speaks MCP over stdio and logs to stderr. To verify it without the agent:

```bash
python scripts/verify_mcp.py
```

**Terminal 2 — the Playwright MCP server**:

```bash
npx -y @playwright/mcp@latest --headless --isolated
```

Verified against `@playwright/mcp` **0.0.79** (`npx -y @playwright/mcp@latest --version`,
2026-08-28). `@latest` is what every machine launches, so this number is a
snapshot of what it resolved to when last verified, not a lockfile pin — if a
newer release changes tool names or schemas, re-run
`python -m agent.run --discover-only` and re-check
[`docs/playwright-tools.json`](docs/playwright-tools.json), which holds the
`browser_navigate` / `browser_snapshot` contracts dumped from the live server.

**Terminal 3 — the agent:**

```bash
python -m agent.run --discover-only          # proves both connections
python -m agent.run --home-group BE-3-1 --courses ECON301,STAT210,MGMT150,FIN220
python -m agent.run --offline                # recorded fixture, no network
```

The agent spawns each MCP server itself over stdio when you run it; the
standalone commands above exist so the servers can be started, inspected and
failed independently — which is exactly what the defence requires.

## Offline / replay mode

`OFFLINE_MODE=true` (or `--offline`) makes the run read
`fixtures/playwright/schedule_page_v1.html` instead of navigating. The fixture
goes through **the same parser** as live markup — there is no branch that
returns a prewritten answer. See [`fixtures/README.md`](fixtures/README.md).

## Repository map

| Path | Contents |
|---|---|
| `mcp_servers/schedule_mcp/` | the custom MCP server: `server.py`, `schemas.py`, `errors.py`, `tools/`, `domain/` |
| `agent/` | LangGraph flow, MCP client wiring, CLI |
| `data/` | deterministic demo dataset and sample `.ics` calendar |
| `fixtures/playwright/` | recorded timetable pages (v1, v2, broken, and a real schedule.kse.ua capture) |
| `docs/` | plan, git workflow, tool contracts, rationale, demo script, rubric self-check |
| `scripts/` | GitHub bootstrap, ticket helpers, MCP verification, demo-data generator |
| `tests/` | offline unit tests |

## Documentation

- [`PROJECT.md`](PROJECT.md) — що це за проєкт і навіщо (українською, почни звідси)
- [`docs/01-plan.md`](docs/01-plan.md) — план роботи і розподіл на треки
- [`docs/02-git-workflow.md`](docs/02-git-workflow.md) — як працює команда
- [`docs/03-tool-contracts.md`](docs/03-tool-contracts.md) — Part C contracts
- [`docs/04-design-rationale.md`](docs/04-design-rationale.md) — design rationale
- [`docs/05-demo-checklist.md`](docs/05-demo-checklist.md) — defence script
- [`docs/06-architecture.md`](docs/06-architecture.md) — flow and boundaries
- [`docs/07-rubric-selfcheck.md`](docs/07-rubric-selfcheck.md) — evidence per rubric row
- [`CLAUDE.md`](CLAUDE.md) — protocol for Claude Code sessions in this repo

## Data and safety boundaries

- Only a public timetable page is navigated. No login, no form submission, no
  irreversible action.
- The personal calendar is a **local exported `.ics` file**. The agent never
  accesses a calendar account.
- `SCRAPE_MIN_INTERVAL_SEC` throttles navigation.
- The custom server's only side effect is writing snapshots and plans into
  `.state/`, which is git-ignored.
