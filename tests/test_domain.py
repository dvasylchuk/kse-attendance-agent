"""Ticket A6: parser/store unit tests, deterministic fixtures, and the shared
envelope-shape guarantee every tool must honour."""

import asyncio
from datetime import date

import pytest

from mcp_servers.schedule_mcp import server
from mcp_servers.schedule_mcp.domain import parser, store
from mcp_servers.schedule_mcp.domain.models import TimetableSnapshot
from mcp_servers.schedule_mcp.errors import ErrorCode, ToolError

VALID_ROW = {
    "date": "2026-09-07",
    "time_range": "09:00-10:20",
    "course_code": "ECON301",
    "course_title": "Intermediate Macroeconomics",
    "group": "BE-3-1",
    "kind": "lecture",
}


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #

def test_malformed_time_is_a_warning_not_a_crash():
    rows = [VALID_ROW, {**VALID_ROW, "time_range": "not-a-time"}]
    sessions, warnings = parser.rows_to_sessions(rows)
    assert len(sessions) == 1
    assert any("row 1" in w for w in warnings)


def test_duplicate_row_is_dropped_with_a_warning():
    rows = [VALID_ROW, dict(VALID_ROW)]
    sessions, warnings = parser.rows_to_sessions(rows)
    assert len(sessions) == 1
    assert any("duplicate" in w for w in warnings)


def test_empty_table_is_an_empty_success_not_an_error():
    sessions, warnings = parser.rows_to_sessions([])
    assert sessions == []
    assert warnings == []


def test_changed_layout_where_every_row_fails_raises_parse_failed():
    rows = [{"date": "not-a-date"}, {"course_code": "X"}]
    with pytest.raises(ToolError) as exc:
        parser.rows_to_sessions(rows)
    assert exc.value.code == ErrorCode.PARSE_FAILED
    assert exc.value.details["rows_seen"] == 2


def test_html_with_no_table_raises_parse_failed():
    with pytest.raises(ToolError) as exc:
        parser.html_to_rows("<html><body><p>no timetable here</p></body></html>")
    assert exc.value.code == ErrorCode.PARSE_FAILED


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def test_snapshot_round_trip():
    sessions, _ = parser.rows_to_sessions([VALID_ROW])
    snap = TimetableSnapshot(
        snapshot_id="snap_roundtrip_test",
        source="local_dataset",
        source_ref="tests/test_domain.py",
        captured_at="2026-08-28T00:00:00Z",
        date_from=date(2026, 9, 7),
        date_to=date(2026, 9, 7),
        sessions=sessions,
    )
    store.save_snapshot(snap)
    loaded = store.load_snapshot("snap_roundtrip_test")
    assert loaded.snapshot_id == snap.snapshot_id
    assert loaded.sessions == snap.sessions
    assert snap.snapshot_id in store.list_snapshot_ids()


def test_snapshot_not_found():
    with pytest.raises(ToolError) as exc:
        store.load_snapshot("snap_does_not_exist_at_all")
    assert exc.value.code == ErrorCode.SNAPSHOT_NOT_FOUND


# --------------------------------------------------------------------------- #
# every tool returns the shared envelope shape, success or failure
# --------------------------------------------------------------------------- #

def _assert_envelope(payload: dict) -> None:
    assert isinstance(payload.get("ok"), bool)
    if payload["ok"]:
        assert "data" in payload and isinstance(payload["data"], dict)
        assert isinstance(payload.get("warnings", []), list)
    else:
        error = payload["error"]
        assert set(error) >= {"code", "message", "details", "retryable"}
        assert isinstance(error["code"], str)


@pytest.mark.parametrize("tool_name", sorted(server.HANDLERS))
def test_every_tool_returns_the_envelope_shape(tool_name: str):
    # Every handler is exercised with an empty argument dict: each one is
    # missing a required field, so this reliably hits the FAILURE path
    # through server.call_tool's own try/except - proving the envelope is
    # produced by the shared server plumbing, not by each tool individually.
    payload = asyncio.run(server.call_tool(tool_name, {}))
    _assert_envelope(payload)
    assert payload["ok"] is False
