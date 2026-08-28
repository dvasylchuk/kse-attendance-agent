"""Tests for detect_schedule_conflicts (ticket A3)."""

from datetime import date, time

import pytest

from mcp_servers.schedule_mcp.domain import store
from mcp_servers.schedule_mcp.domain.models import Session, SessionKind, TimetableSnapshot
from mcp_servers.schedule_mcp.errors import ErrorCode, ToolError
from mcp_servers.schedule_mcp.tools.conflicts import detect_schedule_conflicts

CALENDAR = "fixtures/conflicts/calendar.ics"


def _session(session_id: str, d: date, start: str, end: str, group: str = "BE-3-1") -> Session:
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    return Session(
        session_id=session_id,
        course_code="ECON301",
        course_title="Intermediate Macroeconomics",
        group=group,
        kind=SessionKind.LECTURE,
        date=d,
        start=time(h1, m1),
        end=time(h2, m2),
    )


HARD_SESSION = _session("hard-1", date(2026, 9, 7), "09:00", "10:00")
SOFT_SESSION = _session("soft-1", date(2026, 9, 8), "11:00", "12:00")
TRAVEL_SESSION = _session("travel-1", date(2026, 9, 9), "13:00", "14:00")
OVERLAP_A = _session("overlap-a", date(2026, 9, 10), "10:00", "11:00", group="BE-3-1")
OVERLAP_B = _session("overlap-b", date(2026, 9, 10), "10:30", "11:30", group="BE-3-2")
EMPTY_SESSION = _session("empty-1", date(2026, 9, 11), "08:00", "09:00")

ALL_SESSIONS = [HARD_SESSION, SOFT_SESSION, TRAVEL_SESSION, OVERLAP_A, OVERLAP_B, EMPTY_SESSION]


@pytest.fixture()
def snapshot_id() -> str:
    snap = TimetableSnapshot(
        snapshot_id="snap_conflicts_test",
        source="local_dataset",
        source_ref="tests/test_conflicts.py",
        captured_at="2026-08-28T00:00:00Z",
        date_from=date(2026, 9, 7),
        date_to=date(2026, 9, 11),
        sessions=ALL_SESSIONS,
    )
    store.save_snapshot(snap)
    return snap.snapshot_id


def _by_kind(conflicts: list[dict], kind: str) -> list[dict]:
    return [c for c in conflicts if c["kind"] == kind]


def test_hard_calendar_overlap(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [HARD_SESSION.session_id],
        "calendar_path": CALENDAR,
    })
    assert res["ok"]
    hard = _by_kind(res["data"]["conflicts"], "calendar_hard")
    assert len(hard) == 1
    assert hard[0]["session_id"] == HARD_SESSION.session_id
    assert hard[0]["overlap_minutes"] == 30
    assert res["data"]["blocked_session_ids"] == [HARD_SESSION.session_id]


def test_soft_calendar_overlap(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [SOFT_SESSION.session_id],
        "calendar_path": CALENDAR,
    })
    assert res["ok"]
    soft = _by_kind(res["data"]["conflicts"], "calendar_soft")
    assert len(soft) == 1
    assert soft[0]["overlap_minutes"] == 30
    # soft conflicts do not block attendance
    assert res["data"]["blocked_session_ids"] == []


def test_soft_conflict_excluded_when_include_soft_false(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [SOFT_SESSION.session_id],
        "calendar_path": CALENDAR,
        "include_soft": False,
    })
    assert res["ok"]
    assert res["data"]["conflicts"] == []
    assert res["data"]["conflict_count"] == 0


def test_travel_infeasible_gap(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [TRAVEL_SESSION.session_id],
        "calendar_path": CALENDAR,
    })
    assert res["ok"]
    travel = _by_kind(res["data"]["conflicts"], "travel_infeasible")
    assert len(travel) == 1
    assert travel[0]["session_id"] == TRAVEL_SESSION.session_id
    assert res["data"]["blocked_session_ids"] == [TRAVEL_SESSION.session_id]


def test_session_vs_session_overlap(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [OVERLAP_A.session_id, OVERLAP_B.session_id],
        "calendar_path": CALENDAR,
    })
    assert res["ok"]
    overlaps = _by_kind(res["data"]["conflicts"], "session_overlap")
    assert len(overlaps) == 2  # one entry per side of the pair
    assert {c["session_id"] for c in overlaps} == {OVERLAP_A.session_id, OVERLAP_B.session_id}
    assert all(c["overlap_minutes"] == 30 for c in overlaps)
    assert res["data"]["blocked_session_ids"] == sorted([OVERLAP_A.session_id, OVERLAP_B.session_id])


def test_no_conflicts_is_a_success(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [EMPTY_SESSION.session_id],
        "calendar_path": CALENDAR,
    })
    assert res["ok"] is True
    assert res["data"]["conflicts"] == []
    assert res["data"]["conflict_count"] == 0
    assert res["data"]["blocked_session_ids"] == []
    assert res["data"]["checked_sessions"] == 1
    assert res["warnings"]


def test_unknown_session_id_is_invalid_input(snapshot_id: str):
    with pytest.raises(ToolError) as exc:
        detect_schedule_conflicts({
            "snapshot_id": snapshot_id,
            "session_ids": [HARD_SESSION.session_id, "does-not-exist"],
            "calendar_path": CALENDAR,
        })
    assert exc.value.code == ErrorCode.INVALID_INPUT
    assert exc.value.details["unknown_session_ids"] == ["does-not-exist"]


def test_missing_calendar_file_is_data_source_unavailable(snapshot_id: str):
    with pytest.raises(ToolError) as exc:
        detect_schedule_conflicts({
            "snapshot_id": snapshot_id,
            "session_ids": [HARD_SESSION.session_id],
            "calendar_path": "fixtures/nope.ics",
        })
    assert exc.value.code == ErrorCode.DATA_SOURCE_UNAVAILABLE


def test_all_sessions_checked_together(snapshot_id: str):
    res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": [s.session_id for s in ALL_SESSIONS],
        "calendar_path": CALENDAR,
    })
    assert res["ok"]
    assert res["data"]["checked_sessions"] == 6
    assert res["data"]["calendar_blocks"] == 3
