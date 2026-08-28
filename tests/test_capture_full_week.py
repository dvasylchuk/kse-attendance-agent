"""Ticket B2b: PlaywrightTools.capture_full_week.

schedule.kse.ua has no unfiltered view (ticket B0): a discipline must be
chosen before any session renders. capture_full_week sweeps a list of
disciplines for one date and merges them into one document
ingest_timetable_snapshot can consume unchanged.

Reuses the FakeSession/response-builders from test_playwright_tools.py (same
verified live wire shapes) rather than redefining them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent import tools_facade
from agent.tools_facade import PlaywrightTools, _rows_to_table_html
from mcp_servers.schedule_mcp.errors import ToolError
from tests.test_playwright_tools import FakeSession, _eval_ok, _ok_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/playwright"
REAL_PAGE = (FIXTURES / "kse_schedule_real_2026-09-10.html").read_text(encoding="utf-8")

URL_TEMPLATE = "https://schedule.kse.ua/?date=YYYY-MM-DD&discipline=<COURSE_CODE>"

# A genuinely empty week: the grid frame (day-of-week header) rendered fine,
# there is just no '.schedule-event-card' for this discipline - the common
# case, confirmed live against a random sample of the KSE course catalog.
EMPTY_WEEK_PAGE = (
    '<html><body><calendar-date value="2026-09-07"></calendar-date>'
    '<div class="schedule-grid-header"><span>пн</span><span>7</span></div>'
    "</body></html>"
)

# Event cards present, but every "·" in their aria-label corrupted - the
# same shape test_kse_grid_parser.py uses to prove the grid parser tells
# "label format changed" apart from "no cards at all".
BROKEN_CARDS_PAGE = REAL_PAGE.replace("·", "|")


def _run(coro):
    return asyncio.run(coro)


def _queue_for_page(html: str) -> list:
    """One discipline's worth of responses: navigate, grid-frame-ready check
    ('.schedule-grid-header', not the fixture's own table selector), then
    outerHTML."""
    return [_ok_text("nav"), _eval_ok(True), _eval_ok(html)]


def test_sweeps_every_discipline_and_merges_into_one_table(monkeypatch):
    monkeypatch.setattr(tools_facade.CONFIG, "scrape_min_interval_sec", 0.0)
    session = FakeSession(queue=[*_queue_for_page(REAL_PAGE), *_queue_for_page(EMPTY_WEEK_PAGE)])
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)

    combined_html = _run(pw.capture_full_week(URL_TEMPLATE, ["ECON201", "EMPTY000"], "2026-09-07"))

    nav_urls = [args["url"] for name, args in session.calls if name == "browser_navigate"]
    assert nav_urls == [
        "https://schedule.kse.ua/?date=2026-09-07&discipline=ECON201",
        "https://schedule.kse.ua/?date=2026-09-07&discipline=EMPTY000",
    ]
    assert combined_html.count("<tr>") == 5  # 1 header + 4 ECON201 sessions, 0 from EMPTY000

    from mcp_servers.schedule_mcp.tools.ingest import ingest_timetable_snapshot

    result = ingest_timetable_snapshot({"source": "playwright_html", "raw_html": combined_html})
    assert result["ok"]
    assert result["data"]["session_count"] == 4
    assert result["data"]["courses"] == ["ECON201"]


def test_grid_markup_disappearing_entirely_raises_instead_of_reading_as_empty(monkeypatch):
    """The wait step polls for '.schedule-grid-header', not the outer page
    shell - so a page whose grid markup was renamed/removed never satisfies
    it and raises SelectorNeverAppearedError, instead of being silently
    treated as this discipline having zero sessions."""
    monkeypatch.setattr(tools_facade.CONFIG, "scrape_min_interval_sec", 0.0)
    session = FakeSession(queue=[_ok_text("nav"), _eval_ok(False)])
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)

    with pytest.raises(tools_facade.SelectorNeverAppearedError):
        _run(pw.capture_full_week(URL_TEMPLATE, ["WEIRD000"], "2026-09-07"))


def test_zero_event_cards_with_grid_frame_intact_is_a_successful_empty_result(monkeypatch):
    monkeypatch.setattr(tools_facade.CONFIG, "scrape_min_interval_sec", 0.0)
    session = FakeSession(queue=_queue_for_page(EMPTY_WEEK_PAGE))
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)

    combined_html = _run(pw.capture_full_week(URL_TEMPLATE, ["EMPTY000"], "2026-09-07"))

    assert combined_html.count("<tr>") == 1  # header only, no error raised


def test_cards_present_but_unparseable_propagates_tagged_with_the_discipline(monkeypatch):
    """Event cards ARE present (so this is not the empty-week case), but
    every label is corrupted - a genuine "page layout changed" failure that
    must propagate, not be swallowed just because a table/card selector
    didn't match something else."""
    monkeypatch.setattr(tools_facade.CONFIG, "scrape_min_interval_sec", 0.0)
    session = FakeSession(queue=_queue_for_page(BROKEN_CARDS_PAGE))
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)

    with pytest.raises(ToolError, match=r"discipline 'ECON201'.*aria-label"):
        _run(pw.capture_full_week(URL_TEMPLATE, ["ECON201"], "2026-09-07"))


def test_rejects_a_url_template_missing_placeholders():
    session = FakeSession(queue=[])
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _run(pw.capture_full_week("https://schedule.kse.ua/", ["ECON201"], "2026-09-07"))
    assert session.calls == []


def test_rejects_an_empty_date():
    session = FakeSession(queue=[])
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)
    with pytest.raises(ValueError, match="date"):
        _run(pw.capture_full_week(URL_TEMPLATE, ["ECON201"], ""))
    assert session.calls == []


def test_respects_scrape_min_interval_between_disciplines(monkeypatch):
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(tools_facade.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(tools_facade.CONFIG, "scrape_min_interval_sec", 3.0)
    session = FakeSession(queue=[*_queue_for_page(EMPTY_WEEK_PAGE), *_queue_for_page(EMPTY_WEEK_PAGE)])
    pw = PlaywrightTools(session, poll_attempts=1, poll_interval_sec=0)

    _run(pw.capture_full_week(URL_TEMPLATE, ["AAA", "BBB"], "2026-09-07"))

    # exactly one throttle between the two disciplines - not zero, not two
    assert slept.count(3.0) == 1


def test_rows_to_table_html_preserves_room_teacher_topic_when_present():
    """_PREFERRED_COLUMNS only covers the KSE-grid fields (which never carry
    room/teacher/topic - schedule.kse.ua hides both without login, ticket
    B0). A row that DOES carry them (e.g. the fixture <table> shape) must
    still round-trip through ingest_timetable_snapshot, not be truncated to
    the six preferred columns."""
    rows = [
        {
            "date": "2026-09-07",
            "time_range": "09:00-10:20",
            "course_code": "ECON301",
            "course_title": "Intermediate Macro",
            "group": "BE-3-1",
            "kind": "lecture",
            "room": "A-201",
            "teacher": "Milovanov T.",
            "topic": "IS-LM",
        }
    ]
    html = _rows_to_table_html(rows)

    from mcp_servers.schedule_mcp.domain import store
    from mcp_servers.schedule_mcp.tools.ingest import ingest_timetable_snapshot

    result = ingest_timetable_snapshot({"source": "playwright_html", "raw_html": html})
    assert result["ok"]
    snap = store.load_snapshot(result["data"]["snapshot_id"])
    session = snap.sessions[0]
    assert session.room == "A-201"
    assert session.teacher == "Milovanov T."
    assert session.topic == "IS-LM"
