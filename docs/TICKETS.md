# Ticket board (mirror of scripts/tickets.json)

The live board is GitHub Issues. This file is the offline copy so the plan is
readable in the repository. Regenerate with `python scripts/render_tickets.py`.

Status is not tracked here - GitHub labels are the source of truth:
`status:ready`, `status:in-progress`, `status:review`, `status:blocked`.

## Track A - custom MCP server

| Id | Ticket | Depends on | Milestone |
|---|---|---|---|
| `A1` | ingest_timetable_snapshot (DONE - reference implementation) ✅ | - | M1 Custom MCP server |
| `A2` | detect_timetable_changes (DONE - reference implementation) ✅ | - | M1 Custom MCP server |
| `A3` | Implement detect_schedule_conflicts | - | M1 Custom MCP server |
| `A4` | Implement optimize_attendance_plan | A3 | M1 Custom MCP server |
| `A5` | Implement compare_attendance_plans | A4 | M1 Custom MCP server |
| `A6` | Domain unit tests + deterministic fixtures | A5 | M1 Custom MCP server |
| `A7` | Error-taxonomy review across all five tools | A5 | M1 Custom MCP server |

## Track B - agent and Playwright MCP

| Id | Ticket | Depends on | Milestone |
|---|---|---|---|
| `B0` | Select and verify the real public schedule page and selector | - | M2 Agent + Playwright |
| `B1` | Verify Playwright MCP connection and record its real contract | - | M2 Agent + Playwright |
| `B2` | Implement PlaywrightTools.capture_timetable | B1, B0 | M2 Agent + Playwright |
| `B3` | Implement the graph nodes conflicts / optimize / compare / report | A5, B2 | M2 Agent + Playwright |
| `B4` | Assemble and verify the LangGraph routing | B3 | M2 Agent + Playwright |
| `B5` | Failure handling and offline replay mode | B2 | M2 Agent + Playwright |
| `B6` | Final report rendering via OpenRouter | B3 | M2 Agent + Playwright |
| `B7` | CLI ergonomics for the defence | B4 | M2 Agent + Playwright |

## Track C - documentation, fixtures, ops

| Id | Ticket | Depends on | Milestone |
|---|---|---|---|
| `C1` | README: prerequisites, install, config, independent start commands | - | M3 Documentation |
| `C2` | Part C contracts for all five custom tools | A5 | M3 Documentation |
| `C3` | Document the Playwright MCP tool contract in project context | B1 | M3 Documentation |
| `C4` | Design rationale | A5, B4 | M3 Documentation |
| `C0` | Decide defence format and verify recording pipeline | - | M4 Defence readiness |
| `C5` | Defence script and demo checklist | B4, C0 | M4 Defence readiness |
| `C6` | Fixtures and replay instructions | B5 | M3 Documentation |
| `C7` | Operational and security review | - | M4 Defence readiness |
| `C8` | Rubric self-check | C2, C4, C5 | M4 Defence readiness |

## Track D - integration and defence

| Id | Ticket | Depends on | Milestone |
|---|---|---|---|
| `D1` | End-to-end rehearsal, offline | B4, A6 | M4 Defence readiness |
| `D2` | End-to-end rehearsal, live page | D1, B0 | M4 Defence readiness |
| `D3` | Failure-scenario rehearsal | B5 | M4 Defence readiness |
| `D4` | Final repository review before submission | C8, D2, D3 | M4 Defence readiness |
