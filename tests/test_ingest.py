"""Reference tests for the implemented tools. Model A3/A4/A5 tests on these."""

import pytest

from mcp_servers.schedule_mcp.errors import ErrorCode, ToolError
from mcp_servers.schedule_mcp.tools.changes import detect_timetable_changes
from mcp_servers.schedule_mcp.tools.ingest import ingest_timetable_snapshot

V1 = "fixtures/playwright/schedule_page_v1.html"
V2 = "fixtures/playwright/schedule_page_v2.html"
BROKEN = "fixtures/playwright/schedule_page_broken.html"


def test_ingest_local_dataset_and_fixture_agree():
    a = ingest_timetable_snapshot({"source": "local_dataset", "path": "data/schedule.sample.json"})
    b = ingest_timetable_snapshot({"source": "fixture_html", "path": V1})
    assert a["ok"] and b["ok"]
    assert a["data"]["session_count"] == b["data"]["session_count"]
    assert a["data"]["groups"] == b["data"]["groups"]


def test_ingest_is_content_addressed():
    a = ingest_timetable_snapshot({"source": "fixture_html", "path": V1})
    b = ingest_timetable_snapshot({"source": "fixture_html", "path": V1})
    assert a["data"]["snapshot_id"] == b["data"]["snapshot_id"]
    assert b["data"]["is_new_snapshot"] is False


def test_broken_page_is_a_failure_not_an_empty_success():
    with pytest.raises(ToolError) as exc:
        ingest_timetable_snapshot({"source": "fixture_html", "path": BROKEN})
    assert exc.value.code == ErrorCode.PARSE_FAILED


def test_missing_file_is_data_source_unavailable():
    with pytest.raises(ToolError) as exc:
        ingest_timetable_snapshot({"source": "fixture_html", "path": "fixtures/nope.html"})
    assert exc.value.code == ErrorCode.DATA_SOURCE_UNAVAILABLE


def test_playwright_source_requires_html():
    with pytest.raises(ToolError) as exc:
        ingest_timetable_snapshot({"source": "playwright_html", "raw_html": "   "})
    assert exc.value.code == ErrorCode.INVALID_INPUT


def test_changes_detects_one_move_and_one_addition():
    a = ingest_timetable_snapshot({"source": "fixture_html", "path": V1})
    b = ingest_timetable_snapshot({"source": "fixture_html", "path": V2})
    res = detect_timetable_changes({
        "new_snapshot_id": b["data"]["snapshot_id"],
        "baseline_snapshot_id": a["data"]["snapshot_id"],
    })
    assert res["ok"]
    assert len(res["data"]["moved"]) == 1
    assert len(res["data"]["added"]) == 1
    assert res["data"]["removed"] == []
    assert res["data"]["change_count"] == 2


def test_identical_snapshots_are_an_empty_success():
    a = ingest_timetable_snapshot({"source": "fixture_html", "path": V1})
    res = detect_timetable_changes({
        "new_snapshot_id": a["data"]["snapshot_id"],
        "baseline_snapshot_id": a["data"]["snapshot_id"],
    })
    assert res["ok"] is True
    assert res["data"]["change_count"] == 0
    assert res["warnings"]


def test_unknown_snapshot_is_not_found():
    with pytest.raises(ToolError) as exc:
        detect_timetable_changes({"new_snapshot_id": "snap_doesnotexist"})
    assert exc.value.code == ErrorCode.SNAPSHOT_NOT_FOUND
