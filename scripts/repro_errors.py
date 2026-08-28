"""One scripted reproduction per error code in the taxonomy (ticket A7).

Connects to the real running server over stdio - the same path
`scripts/verify_mcp.py` exercises - and drives one call per designed error
code, printing `{tool} -> {code} retryable={bool}` and asserting the code and
`retryable` flag are what docs/03-tool-contracts.md claims.

    python scripts/repro_errors.py

`INTERNAL` is deliberately not reproduced here: it is the unclassified
fallback for a genuinely unexpected exception, not a designed error path, so
there is no legitimate input that reliably triggers it. `NOT_IMPLEMENTED` is
retired - every tool ships an implementation now.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def _call(session: ClientSession, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    return (await session.call_tool(tool, args)).structuredContent


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.schedule_mcp.server"],
        cwd=str(ROOT),
        env={**os.environ, "SCHEDULE_MCP_STATE_DIR": str(ROOT / ".state-repro")},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        snap = await _call(session, "ingest_timetable_snapshot",
                            {"source": "local_dataset", "path": "data/schedule.sample.json"})
        assert snap["ok"], snap
        snapshot_id = snap["data"]["snapshot_id"]

        cases: list[tuple[str, str, dict[str, Any]]] = [
            ("INVALID_INPUT", "detect_schedule_conflicts", {
                "snapshot_id": snapshot_id, "session_ids": ["does-not-exist"],
            }),
            ("PARSE_FAILED", "ingest_timetable_snapshot", {
                "source": "fixture_html", "path": "fixtures/playwright/schedule_page_broken.html",
            }),
            ("DATA_SOURCE_UNAVAILABLE", "ingest_timetable_snapshot", {
                "source": "fixture_html", "path": "fixtures/nope.html",
            }),
            ("SNAPSHOT_NOT_FOUND", "detect_timetable_changes", {
                "new_snapshot_id": "snap_does_not_exist",
            }),
            ("PLAN_NOT_FOUND", "compare_attendance_plans", {
                "plan_ids": ["plan_nope_1", "plan_nope_2"],
            }),
            ("INFEASIBLE", "optimize_attendance_plan", {
                "snapshot_id": snapshot_id, "home_group": "BE-3-1",
                "required_courses": ["ECON301", "STAT210", "MGMT150", "FIN220"],
                "max_campus_days": 1,
            }),
        ]

        for expected_code, tool, args in cases:
            payload = await _call(session, tool, args)
            assert not payload["ok"], f"{tool} unexpectedly succeeded: {payload}"
            error = payload["error"]
            print(f"{tool} -> {error['code']} retryable={error['retryable']}")
            assert error["code"] == expected_code, f"expected {expected_code}, got {error}"
            assert error["retryable"] is False, f"{expected_code} must not be retryable: {error}"

        print(f"all {len(cases)} designed error codes reproduced, none retryable")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
