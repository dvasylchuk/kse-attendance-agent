"""Parser/store unit tests, deterministic fixtures, and the shared envelope
and error-taxonomy guarantees every tool must honour."""

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
    # missing a required field, so this reliably hits server.call_tool's own
    # required-argument check - proving the envelope is produced by the
    # shared server plumbing, not by each tool individually.
    payload = asyncio.run(server.call_tool(tool_name, {}))
    _assert_envelope(payload)
    assert payload["ok"] is False
    # A missing required argument is a client mistake, not an unclassified
    # crash: retrying the identical call can never succeed.
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT
    assert payload["error"]["retryable"] is False


def test_unclassified_exception_is_internal_and_retryable(monkeypatch):
    def _boom(_args):
        raise RuntimeError("something genuinely unexpected")

    monkeypatch.setitem(server.HANDLERS, "ingest_timetable_snapshot", _boom)
    payload = asyncio.run(server.call_tool("ingest_timetable_snapshot", {"source": "local_dataset"}))
    _assert_envelope(payload)
    assert payload["ok"] is False
    assert payload["error"]["code"] == ErrorCode.INTERNAL
    assert payload["error"]["retryable"] is True


def test_a_keyerror_bug_inside_a_handler_is_still_internal_not_invalid_input(monkeypatch):
    # All required arguments are present - this KeyError comes from a bug
    # deep inside the tool's own logic, not from a missing caller argument,
    # and must not be misreported as the caller's fault.
    def _boom(_args):
        return {}["not_a_real_key"]

    monkeypatch.setitem(server.HANDLERS, "ingest_timetable_snapshot", _boom)
    payload = asyncio.run(server.call_tool(
        "ingest_timetable_snapshot", {"source": "local_dataset", "path": "data/schedule.sample.json"},
    ))
    _assert_envelope(payload)
    assert payload["ok"] is False
    assert payload["error"]["code"] == ErrorCode.INTERNAL
    assert payload["error"]["retryable"] is True
