"""Tests for optimize_attendance_plan (ticket A4), against the demo dataset."""

import pytest

from mcp_servers.schedule_mcp.errors import ErrorCode, ToolError
from mcp_servers.schedule_mcp.tools.ingest import ingest_timetable_snapshot
from mcp_servers.schedule_mcp.tools.optimize import optimize_attendance_plan

HOME_GROUP = "BE-3-1"
REQUIRED_COURSES = ["ECON301", "STAT210", "MGMT150", "FIN220"]

# BE-3-1's own timetable spans 5 distinct (course_code, kind, topic) units across
# 3 distinct days (Mon 2026-09-07, Tue 2026-09-08, Fri 2026-09-11) - see
# data/schedule.sample.json. That is the naive home-group-only baseline.
BASELINE_DAYS = 3


@pytest.fixture()
def snapshot_id() -> str:
    res = ingest_timetable_snapshot({"source": "local_dataset", "path": "data/schedule.sample.json"})
    assert res["ok"]
    return res["data"]["snapshot_id"]


def _base_args(snapshot_id: str, **overrides) -> dict:
    args = {
        "snapshot_id": snapshot_id,
        "home_group": HOME_GROUP,
        "required_courses": REQUIRED_COURSES,
        "calendar_path": "data/calendar.sample.ics",
    }
    args.update(overrides)
    return args


def test_plan_reduces_campus_days_versus_home_baseline(snapshot_id: str):
    res = optimize_attendance_plan(_base_args(snapshot_id))
    assert res["ok"]
    data = res["data"]
    assert data["required_sessions"] == 5
    assert data["campus_day_count"] < BASELINE_DAYS
    assert data["coverage_ratio"] == 1.0
    assert data["covered_sessions"] == 5
    assert data["skipped"] == []


def test_deterministic_plan_id_for_identical_input(snapshot_id: str):
    a = optimize_attendance_plan(_base_args(snapshot_id))
    b = optimize_attendance_plan(_base_args(snapshot_id))
    assert a["data"]["plan_id"] == b["data"]["plan_id"]
    assert a["data"]["plan_id"].startswith("plan_")


def test_skipped_sessions_carry_a_machine_readable_reason(snapshot_id: str):
    res = optimize_attendance_plan(_base_args(
        snapshot_id, max_campus_days=1, min_coverage_ratio=0.5,
    ))
    assert res["ok"]
    data = res["data"]
    assert data["campus_day_count"] == 1
    assert data["skipped"], "expected at least one skipped session with a 1-day budget"
    for item in data["skipped"]:
        assert set(item) == {"session_id", "reason"}
        assert item["reason"] in {"blocked_by_calendar", "excluded_by_day_or_time_budget"}


def test_infeasible_when_day_budget_is_too_tight(snapshot_id: str):
    with pytest.raises(ToolError) as exc:
        optimize_attendance_plan(_base_args(snapshot_id, max_campus_days=1))
    assert exc.value.code == ErrorCode.INFEASIBLE
    assert exc.value.details["best_coverage_ratio"] < 0.7
    assert exc.value.details["binding_constraint"] in {"max_campus_days", "min_coverage_ratio"}


def test_unknown_home_group_is_invalid_input(snapshot_id: str):
    with pytest.raises(ToolError) as exc:
        optimize_attendance_plan(_base_args(snapshot_id, home_group="ZZ-9-9"))
    assert exc.value.code == ErrorCode.INVALID_INPUT


def test_required_course_absent_from_home_group_is_invalid_input(snapshot_id: str):
    with pytest.raises(ToolError) as exc:
        optimize_attendance_plan(_base_args(snapshot_id, required_courses=["ECON301", "NOPE404"]))
    assert exc.value.code == ErrorCode.INVALID_INPUT
    assert "NOPE404" in exc.value.details["missing_courses"]


def test_no_cross_group_still_finds_a_plan(snapshot_id: str):
    res = optimize_attendance_plan(_base_args(
        snapshot_id, allow_cross_group=False, min_coverage_ratio=0.0, max_campus_days=6,
    ))
    assert res["ok"]
    data = res["data"]
    assert data["substitutions_used"] == 0
    assert all(not it["substituted"] for it in data["items"])
