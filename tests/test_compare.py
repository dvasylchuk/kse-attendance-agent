"""Tests for compare_attendance_plans (ticket A5)."""

from datetime import date

import pytest

from mcp_servers.schedule_mcp.domain import store
from mcp_servers.schedule_mcp.domain.models import AttendancePlan
from mcp_servers.schedule_mcp.errors import ErrorCode, ToolError
from mcp_servers.schedule_mcp.tools.compare import compare_attendance_plans


def _plan(plan_id: str, snapshot_id: str, days: int, coverage: float, subs: int) -> AttendancePlan:
    return AttendancePlan(
        plan_id=plan_id,
        snapshot_id=snapshot_id,
        objective="balanced",
        items=[],
        campus_days=[date(2026, 9, 7 + i) for i in range(days)],
        coverage_ratio=coverage,
        covered_sessions=round(coverage * 5),
        required_sessions=5,
        skipped=[],
        substitutions_used=subs,
    )


@pytest.fixture()
def plans() -> dict[str, AttendancePlan]:
    baseline = _plan("plan_baseline", "snap_x", days=3, coverage=0.6, subs=0)
    good = _plan("plan_good", "snap_x", days=2, coverage=1.0, subs=4)
    bad = _plan("plan_bad", "snap_x", days=4, coverage=0.5, subs=1)
    other_snapshot = _plan("plan_other_snap", "snap_y", days=1, coverage=0.9, subs=0)
    for p in (baseline, good, bad, other_snapshot):
        store.save_plan(p)
    return {"baseline": baseline, "good": good, "bad": bad, "other_snapshot": other_snapshot}


def test_supported_when_a_plan_meets_the_preference(plans):
    res = compare_attendance_plans({
        "plan_ids": ["plan_baseline", "plan_good", "plan_bad"],
        "preference": {"max_campus_days": 3, "min_coverage_ratio": 0.8, "max_substitutions": 5},
    })
    assert res["ok"]
    data = res["data"]
    assert data["verdict"] == "supported"
    assert data["recommended_plan_id"] == "plan_good"
    assert data["baseline_plan_id"] == "plan_baseline"
    assert len(data["comparisons"]) == 2  # baseline itself is excluded
    good_cmp = next(c for c in data["comparisons"] if c["plan_id"] == "plan_good")
    assert good_cmp["satisfies_preference"] is True
    assert good_cmp["campus_days_delta"] == -1
    assert good_cmp["substitutions_delta"] == 4
    assert good_cmp["violated"] == []


def test_contradicted_when_no_plan_meets_the_preference(plans):
    res = compare_attendance_plans({
        "plan_ids": ["plan_baseline", "plan_bad"],
        "preference": {"max_campus_days": 1, "min_coverage_ratio": 0.9, "max_substitutions": 0},
    })
    assert res["ok"]
    data = res["data"]
    assert data["verdict"] == "contradicted"
    # baseline has better coverage than bad, so it is the closest miss
    assert data["recommended_plan_id"] == "plan_baseline"
    bad_cmp = next(c for c in data["comparisons"] if c["plan_id"] == "plan_bad")
    assert bad_cmp["satisfies_preference"] is False
    assert set(bad_cmp["violated"]) == {"max_campus_days", "min_coverage_ratio", "max_substitutions"}


def test_inconclusive_with_no_preference(plans):
    res = compare_attendance_plans({"plan_ids": ["plan_baseline", "plan_good"]})
    assert res["ok"]
    data = res["data"]
    assert data["verdict"] == "inconclusive"
    assert data["recommended_plan_id"] == "plan_good"  # highest coverage regardless
    assert res["warnings"]


def test_inconclusive_across_different_snapshots(plans):
    res = compare_attendance_plans({
        "plan_ids": ["plan_baseline", "plan_other_snap"],
        "preference": {"min_coverage_ratio": 0.5},
    })
    assert res["ok"]
    data = res["data"]
    assert data["verdict"] == "inconclusive"
    assert any("snapshot" in w for w in res["warnings"])


def test_unknown_plan_id_is_not_found(plans):
    with pytest.raises(ToolError) as exc:
        compare_attendance_plans({"plan_ids": ["plan_baseline", "plan_does_not_exist"]})
    assert exc.value.code == ErrorCode.PLAN_NOT_FOUND
