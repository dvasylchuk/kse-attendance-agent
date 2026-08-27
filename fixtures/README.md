# Recorded fixtures

| File | What it is | Used for |
|---|---|---|
| `playwright/schedule_page_v1.html` | the timetable as first captured | the default offline run |
| `playwright/schedule_page_v2.html` | the same week after the university moved one class and added another | the `detect_timetable_changes` / re-planning demo |
| `playwright/schedule_page_broken.html` | a 503 page with no timetable table | the `PARSE_FAILED` demo |

## How they were produced

`scripts/make_demo_data.py` generates all three deterministically, along with
`data/schedule.sample.json`, `data/calendar.sample.ics` and
`data/student.sample.json`:

```bash
python scripts/make_demo_data.py
```

To re-record from a real page instead, capture the timetable region through
Playwright MCP and save the markup here under the same names. The parser reads
column meanings from the table header, so a real page with differently ordered
columns still works as long as the header names match.

## Why replay is not a shortcut

`OFFLINE_MODE=true` changes exactly one thing: where the markup comes from.
The bytes then go through the identical path —
`parser.html_to_rows` → `parser.rows_to_sessions` → validation → snapshot —
as markup captured live. There is no branch anywhere that returns a stored
answer, and no tool behaves differently in offline mode.

You can verify that claim: `mcp_servers/schedule_mcp/tools/ingest.py` selects a
*source of bytes* and then falls into shared code. Nothing downstream of
`rows_to_sessions` knows or can know which mode produced the input.

## Data safety

Every name, room and teacher in these fixtures is synthetic. The `.ics`
calendar is a sample, not anyone's real calendar. No personal data belongs in
this directory.
