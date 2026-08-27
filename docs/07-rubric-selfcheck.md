# Rubric self-check (100 points)

Fill the Evidence column with a file path, a command, or a timestamp in the
recording. A row without evidence is not done. Ticket **C8** owns this file.

## Minimum-condition rules — must all be true

| Condition | Status | Evidence |
|---|---|---|
| At least three qualifying custom tools exposed | ⬜ | `python scripts/verify_mcp.py` shows 5 |
| A qualifying primary data-source tool exists | ⬜ | `ingest_timetable_snapshot` |
| Both MCP connections can be called successfully | ⬜ | `python -m agent.run --discover-only` |
| The agent incorporates both servers into its flows | ⬜ | `agent/graph.py` + the full run |

## 1. MCP architecture and protocol correctness — 25

| Requirement | Status | Evidence |
|---|---|---|
| Both connections initialise | ⬜ | |
| Custom server independently startable, process-separated | ⬜ | `python -m mcp_servers.schedule_mcp.server` in its own terminal |
| Discovery and invocation follow MCP | ⬜ | `scripts/verify_mcp.py` |
| Configuration reproducible | ⬜ | fresh clone by a teammate (ticket D1) |
| Clear boundaries agent / client / server / data | ⬜ | `docs/06-architecture.md` |

## 2. Documentation and design rationale — 25

| Requirement | Status | Evidence |
|---|---|---|
| Complete contracts for all custom tools | ⬜ | `docs/03-tool-contracts.md` |
| Accurate explanation of one existing tool | ⬜ | same file, last section + `docs/playwright-tools.json` |
| Clear setup instructions | ⬜ | `README.md` |
| Trade-offs, limitations, errors, side effects explained | ⬜ | `docs/04-design-rationale.md` |

## 3. Custom tool and schema design — 18

| Requirement | Status | Evidence |
|---|---|---|
| ≥3 substantive, distinct tools | ⬜ | 5 exposed |
| ≥2 go beyond search/retrieval | ⬜ | optimise, compare, diff, ingest — 4 of 5 |
| Names and descriptions guide correct selection | ⬜ | `server.py` descriptions |
| Schemas explicit and constrained | ⬜ | `schemas.py` — enums, ranges, `additionalProperties: false` |
| Outputs structured and usable | ⬜ | `outputSchema` on every tool |

## 4. Integration into the agent workflow — 14

| Requirement | Status | Evidence |
|---|---|---|
| Both connections in coherent agentic flows | ⬜ | `agent/graph.py` |
| Tool results influence subsequent behaviour | ⬜ | `replan_required` routing; `INFEASIBLE` retry |
| Integrations clearly motivated | ⬜ | `docs/04-design-rationale.md` |

## 5. Existing-server integration and failure demo — 10

| Requirement | Status | Evidence |
|---|---|---|
| Configured, discovered, invoked, incorporated | ⬜ | |
| Role and one contract explained accurately | ⬜ | |
| A realistic failure reproduced and surfaced | ⬜ | ticket D3 |

## 6. Operational robustness and responsible data access — 8

| Requirement | Status | Evidence |
|---|---|---|
| No secrets committed | ⬜ | CI secret scan + `git log -p` sweep (ticket C7) |
| Rate limits respected | ⬜ | `SCRAPE_MIN_INTERVAL_SEC` |
| Errors distinguishable from empty results | ⬜ | `docs/03-tool-contracts.md` error table |
| Fixture replay faithful and reproducible | ⬜ | `fixtures/README.md` |
| Side effects controlled | ⬜ | writes confined to `.state/` |

---

## What actually gets a submission to full marks

Beyond the checkboxes, four things separate a competent submission from an
excellent one:

1. **The loop has to be visible.** A grader must see one tool result change what
   the agent does next. Show the `replan_required = false` short-circuit *and*
   the `true` branch on the same recording — one run that skips optimisation
   entirely proves the branch is real.
2. **The failure must be honest.** A staged failure that immediately recovers
   into a perfect answer reads as artificial. Show the error text, show
   `degraded_reason` in the output, and say out loud that the data is no longer
   live.
3. **Every number must be traceable.** Expect "where did this come from?".
   Rehearse the trace in `docs/06-architecture.md` until you can do it without
   the notes.
4. **You must be able to defend the design choices.** Not "we used an enum
   because it is cleaner", but "a constrained enum is something a model selects
   correctly, a weight vector is not". Read
   `docs/04-design-rationale.md` twice before recording.
