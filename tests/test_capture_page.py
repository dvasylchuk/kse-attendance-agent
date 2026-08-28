"""Ticket B2b: agent/graph.py's capture_page node.

Covers the two branches this ticket introduced: an empty required_courses
list degrading loudly instead of silently falling back to a discipline-less
capture, and capture_full_week being called with the student's actual
course list and an explicit Europe/Kyiv date (not the host machine's local
date/time, which would drift with wherever the agent happens to run).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from agent import graph
from agent.config import CONFIG


def _run(coro):
    return asyncio.run(coro)


class _RecordingPlaywrightTools:
    def __init__(self, html: str = "<table class='schedule'></table>") -> None:
        self.html = html
        self.calls: list[tuple] = []

    async def capture_full_week(self, url_template, disciplines, date):
        self.calls.append((url_template, disciplines, date))
        return self.html


def test_empty_required_courses_degrades_without_navigating(monkeypatch):
    monkeypatch.setattr(CONFIG, "offline", False)
    pw = _RecordingPlaywrightTools()

    result = _run(graph.capture_page({"required_courses": []}, pw))

    assert result["capture_source"] == "fixture"
    assert "required_courses" in result["degraded_reason"]
    assert pw.calls == []  # never touched the browser


def test_calls_capture_full_week_with_courses_and_kyiv_date(monkeypatch):
    monkeypatch.setattr(CONFIG, "offline", False)
    pw = _RecordingPlaywrightTools()
    state = {"required_courses": ["ECON301", "STAT210"]}

    result = _run(graph.capture_page(state, pw))

    assert result["capture_source"] == "playwright"
    assert result["degraded_reason"] is None
    assert len(pw.calls) == 1
    url_template, disciplines, date = pw.calls[0]
    assert url_template == CONFIG.schedule_url
    assert disciplines == ["ECON301", "STAT210"]
    assert date == datetime.now(ZoneInfo("Europe/Kyiv")).date().isoformat()


def test_offline_mode_never_touches_playwright_regardless_of_courses(monkeypatch):
    monkeypatch.setattr(CONFIG, "offline", True)
    pw = _RecordingPlaywrightTools()

    result = _run(graph.capture_page({"required_courses": ["ECON301"]}, pw))

    assert result["capture_source"] == "fixture"
    assert result["degraded_reason"] == "OFFLINE_MODE=true"
    assert pw.calls == []
