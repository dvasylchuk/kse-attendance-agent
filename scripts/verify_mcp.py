"""Proof that the custom MCP server starts as its own process and speaks MCP.

Used by CI and as demo step 1/7 at the defence:

    python scripts/verify_mcp.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "ingest_timetable_snapshot",
    "detect_timetable_changes",
    "detect_schedule_conflicts",
    "optimize_attendance_plan",
    "compare_attendance_plans",
}


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.schedule_mcp.server"],
        cwd=str(ROOT),
        env={**os.environ, "SCHEDULE_MCP_STATE_DIR": str(ROOT / ".state")},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        print(f"connected to {init.serverInfo.name} v{init.serverInfo.version}")

        tools = (await session.list_tools()).tools
        names = {t.name for t in tools}
        print(f"discovered {len(names)} tools:")
        for t in tools:
            io = "in+out schema" if t.outputSchema else "in schema only"
            print(f"  - {t.name} ({io})")

        missing = EXPECTED - names
        if missing:
            print(f"MISSING: {sorted(missing)}")
            return 1
        if any(t.outputSchema is None for t in tools):
            print("every tool must declare an outputSchema")
            return 1

        res = await session.call_tool(
            "ingest_timetable_snapshot",
            {"source": "local_dataset", "path": "data/schedule.sample.json"},
        )
        payload = res.structuredContent
        assert payload and payload["ok"], payload
        print(f"primary data-source tool works: snapshot {payload['data']['snapshot_id']} "
              f"with {payload['data']['session_count']} sessions")

        bad = await session.call_tool(
            "ingest_timetable_snapshot",
            {"source": "fixture_html", "path": "fixtures/playwright/schedule_page_broken.html"},
        )
        code = bad.structuredContent["error"]["code"]
        print(f"failure is distinguishable: error code {code}")
        assert code == "PARSE_FAILED", bad.structuredContent
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
