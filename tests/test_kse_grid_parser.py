"""Ticket B0: schedule.kse.ua does not render <table class="schedule">. This
tests the div-grid parsing path added to parser.html_to_rows against a real
capture of the live page (fixtures/playwright/kse_schedule_real_2026-09-10.html),
not a hand-written stand-in.
"""

from datetime import date

from mcp_servers.schedule_mcp.domain import parser
from mcp_servers.schedule_mcp.errors import ErrorCode, ToolError
from mcp_servers.schedule_mcp.tools.ingest import ingest_timetable_snapshot

REAL_PAGE = "fixtures/playwright/kse_schedule_real_2026-09-10.html"


def _real_html() -> str:
    with open(REAL_PAGE, encoding="utf-8") as fh:
        return fh.read()


def test_grid_rows_use_the_embedded_calendar_date():
    rows = parser.html_to_rows(_real_html())
    assert len(rows) == 4
    for row in rows:
        assert row["course_code"] == "ECON201"
        assert row["course_title"] == "Microeconomics II"
        assert row["kind"] == "Лекція"

    by_group_and_time = {(r["group"], r["time_range"]) for r in rows}
    assert by_group_and_time == {
        ("GR1", "11:30-12:50"),
        ("GR2", "13:30-14:50"),
        ("GR1", "13:30-14:50"),
        ("GR2", "15:00-16:20"),
    }
    dates = {r["date"] for r in rows}
    # week of 2026-09-07 (Monday); events land on Monday and Tuesday
    assert dates == {"2026-09-07", "2026-09-08"}


def test_grid_rows_fall_back_to_source_ref_without_calendar_date():
    html = _real_html().replace('<calendar-date value="2026-09-10"', "<calendar-date")
    rows = parser.html_to_rows(html, source_ref="playwright:live-page:2026-09-10")
    assert {r["date"] for r in rows} == {"2026-09-07", "2026-09-08"}


def test_grid_without_any_date_source_is_parse_failed():
    html = _real_html().replace('<calendar-date value="2026-09-10"', "<calendar-date")
    with __import__("pytest").raises(ToolError) as exc:
        parser.html_to_rows(html)
    assert exc.value.code == ErrorCode.PARSE_FAILED


def test_ingest_real_kse_grid_end_to_end():
    result = ingest_timetable_snapshot({"source": "fixture_html", "path": REAL_PAGE})
    assert result["ok"]
    assert result["data"]["session_count"] == 4
    assert result["data"]["courses"] == ["ECON201"]
    assert date.fromisoformat(result["data"]["date_from"]) == date(2026, 9, 7)
    assert date.fromisoformat(result["data"]["date_to"]) == date(2026, 9, 8)


def test_grid_sessions_have_no_teacher_or_room():
    result = ingest_timetable_snapshot({"source": "fixture_html", "path": REAL_PAGE})
    # room/teacher are hidden by schedule.kse.ua itself unless logged in
    # (verified live, ticket B0) - the parser must not invent placeholder values.
    snapshot_id = result["data"]["snapshot_id"]
    from mcp_servers.schedule_mcp.domain import store

    snap = store.load_snapshot(snapshot_id)
    assert all(s.room is None and s.teacher is None for s in snap.sessions)
