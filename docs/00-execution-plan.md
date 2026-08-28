# Execution plan: confirmed real-data target (ticket B0)

Referenced from issue #34 and its "Blocks: #10 (B2), #18 (C3), #25 (D2)"
comment. This file is what those tickets should read before touching the
capture/parsing path — it records what B0 actually found on the live page,
not what the original synthetic fixtures assumed.

## Confirmed target

```
https://schedule.kse.ua/?date=YYYY-MM-DD&discipline=<COURSE_CODE>
```

Public, no login required to view a discipline's sessions. Verified live on
2026-08-28 via Playwright MCP `navigate` + `snapshot` + `evaluate`.

## How this differs from the original assumption

The project's synthetic fixtures (`fixtures/playwright/schedule_page_v1.html`
etc.) and the domain parser were both built around a `<table class="schedule">`
with one `<tr>` per session and a fixed column set (date, time_range,
course_code, course_title, group, kind, room, teacher, topic). The real page
does not work that way:

| Assumption | Reality |
|---|---|
| A `<table class="schedule">` lists every session | A CSS grid (`.schedule-grid-cell` divs positioned by time-slot row × weekday column); the actual session card is `.schedule-event-card`, an absolutely-positioned `<div>` inside its cell |
| Browsing shows the whole institution's timetable | Nothing renders until a discipline is chosen via the search box (`placeholder="Дисципліна"`); there is no unfiltered view |
| `teacher` and `room` are readable anonymously | Both are hidden behind a lock icon, `aria-label="Увійдіть, щоб побачити викладачів та аудиторії"`, unless logged in |
| `group` is the institutional code (e.g. `BE-3-1`) | The card only exposes a course-relative number, `"гр.1"` / `"гр.2"`, with no visible link to the institutional group taxonomy |
| Each row carries its own date | No event carries a date attribute; the visible week's Monday has to be read from `<calendar-date value="YYYY-MM-DD">`, the filter card's date picker, then combined with the day's column index (0 = Monday, confirmed empirically: 6 columns, Mon-Sat, no Sunday classes) |

## What was changed because of this

- `mcp_servers/schedule_mcp/domain/parser.py`: `html_to_rows` now tries the
  `<table>` path first (unchanged, so every existing fixture and test keeps
  working), and falls back to `_kse_grid_rows` when no table matches but
  `.schedule-event-card` elements are present. See that function's docstring
  for the exact grid-position math and its documented gaps (course-relative
  group numbers, no teacher/room).
- A real capture is committed at
  `fixtures/playwright/kse_schedule_real_2026-09-10.html` and covered by
  `tests/test_kse_grid_parser.py` — parsed through the same code path as
  live data, not a hand-written stand-in.
- `docs/playwright-tools.json` records the confirmed target under
  `confirmed_target_B0`.
- `.env.example`'s `SCHEDULE_TABLE_SELECTOR` comment explains the fallback;
  the variable's default value does not need to change, since detection is
  automatic.

## Still open for later tickets

- **B2** (`PlaywrightTools.capture_timetable`) needs to actually drive the
  discipline search box before a snapshot/evaluate call will see any
  session data — navigating to `?discipline=CODE` directly (as this ticket
  did) works and avoids a form-fill step, so B2 should prefer that over
  typing into the search box at runtime.
- **C3** (Playwright MCP tool contract docs) should describe this page's
  actual shape, not a generic "public timetable" description.
- **D2** (live-page rehearsal) should budget for the discipline-must-be-known
  constraint: the demo has to pick specific course codes in advance rather
  than browsing a group's full timetable in one call.
- Reconciling the course-relative `гр.N` numbering against this project's
  `BE-3-1`-style group codes is unresolved; nothing in the live page answers
  it, so any attendance plan built from real (not fixture) data will need a
  documented assumption or a manual mapping, not a scraped one.
