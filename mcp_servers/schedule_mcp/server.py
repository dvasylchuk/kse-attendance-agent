"""Schedule MCP server - a standalone process, started independently of the agent.

    python -m mcp_servers.schedule_mcp.server          # stdio transport

The low-level MCP Server API is used on purpose: tool discovery, explicit
input/output schemas and the error envelope are all visible in this file
rather than hidden behind a decorator framework.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from . import schemas
from .errors import ErrorCode, ToolError
from .tools.changes import detect_timetable_changes
from .tools.compare import compare_attendance_plans
from .tools.conflicts import detect_schedule_conflicts
from .tools.ingest import ingest_timetable_snapshot
from .tools.optimize import optimize_attendance_plan

logging.basicConfig(
    level=os.environ.get("SCHEDULE_MCP_LOG_LEVEL", "INFO"),
    stream=sys.stderr,  # stdout is the MCP transport - never print there
    format="%(asctime)s schedule-mcp %(levelname)s %(message)s",
)
log = logging.getLogger("schedule-mcp")

SERVER_NAME = "schedule-mcp"
SERVER_VERSION = "0.1.0"

HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "ingest_timetable_snapshot": ingest_timetable_snapshot,
    "detect_timetable_changes": detect_timetable_changes,
    "detect_schedule_conflicts": detect_schedule_conflicts,
    "optimize_attendance_plan": optimize_attendance_plan,
    "compare_attendance_plans": compare_attendance_plans,
}

TOOLS: list[Tool] = [
    Tool(
        name="ingest_timetable_snapshot",
        description=(
            "Parse a university timetable into a versioned, validated snapshot and return its "
            "snapshot_id. This is the entry point of the domain: every other tool takes a "
            "snapshot_id produced here. Accepts raw HTML captured from the live schedule page "
            "through Playwright MCP, a recorded fixture page, or the prepared local dataset. "
            "Normalises times, class kinds and group labels, drops duplicate rows, and reports "
            "rejected rows as warnings. Call it again whenever the university may have edited "
            "the timetable - identical content yields the same snapshot_id and is not stored "
            "twice."
        ),
        inputSchema=schemas.INGEST_INPUT,
        outputSchema=schemas.INGEST_OUTPUT,
    ),
    Tool(
        name="detect_timetable_changes",
        description=(
            "Diff a freshly ingested timetable snapshot against an earlier one and report added, "
            "removed and moved classes. Given a plan_id it also reports which items of that plan "
            "the change invalidates and whether re-planning is required. Use this after every "
            "re-scrape before trusting an existing attendance plan."
        ),
        inputSchema=schemas.CHANGES_INPUT,
        outputSchema=schemas.CHANGES_OUTPUT,
    ),
    Tool(
        name="detect_schedule_conflicts",
        description=(
            "Check candidate timetable sessions against the student's exported .ics calendar and "
            "against each other, and return typed conflicts (hard calendar clash, soft clash, "
            "session overlap, insufficient travel gap) with overlap minutes. Use it to find out "
            "which classes of the student's own group are unattendable before asking for an "
            "optimised plan. An empty conflict list is a successful result, not an error."
        ),
        inputSchema=schemas.CONFLICTS_INPUT,
        outputSchema=schemas.CONFLICTS_OUTPUT,
    ),
    Tool(
        name="optimize_attendance_plan",
        description=(
            "Build an attendance plan that covers the required courses in as few days on campus "
            "as possible, allowed to substitute another study group's session of the same course "
            "when the topic matches. Honours a hard cap on campus days, a minimum coverage ratio "
            "and the student's calendar. Returns the chosen session per course, the campus days, "
            "the coverage ratio, the substitutions used and a reason for every skipped session. "
            "Fails with INFEASIBLE when the constraints admit no plan - relax max_campus_days or "
            "min_coverage_ratio and call again."
        ),
        inputSchema=schemas.OPTIMIZE_INPUT,
        outputSchema=schemas.OPTIMIZE_OUTPUT,
    ),
    Tool(
        name="compare_attendance_plans",
        description=(
            "Compare two or more attendance plans against the student's stated preference and "
            "return structured evidence: per-plan deltas in campus days, coverage and "
            "substitutions, which constraints each plan violates, a recommended plan and a "
            "verdict of supported / contradicted / inconclusive. Use it to decide between a "
            "baseline home-group plan and an optimised one instead of judging by eye."
        ),
        inputSchema=schemas.COMPARE_INPUT,
        outputSchema=schemas.COMPARE_OUTPUT,
    ),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}

app = Server(SERVER_NAME, version=SERVER_VERSION)


@app.list_tools()
async def list_tools() -> list[Tool]:
    log.info("tool discovery: %d tools", len(TOOLS))
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}
    handler = HANDLERS.get(name)
    if handler is None:
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"unknown tool {name!r}",
            details={"known_tools": sorted(HANDLERS)},
        ).to_payload()

    log.info("call %s args=%s", name, sorted(args))

    # A required top-level argument is absent. The MCP SDK's own inputSchema
    # validation catches this before a real client ever reaches the handler,
    # but a handler invoked directly (unit tests, a future direct import from
    # agent/) has no such gate - so it is checked explicitly here, rather than
    # via a broad `except KeyError` around the handler call, which would also
    # swallow an unrelated KeyError raised by a genuine bug deep inside the
    # tool's own logic and misreport it as a client mistake.
    missing = sorted(set(TOOLS_BY_NAME[name].inputSchema.get("required", [])) - set(args))
    if missing:
        log.warning("%s missing required argument(s): %s", name, missing)
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"missing required argument(s): {missing}",
            details={"missing_arguments": missing},
        ).to_payload()

    try:
        # Tools are synchronous CPU/IO-bound work; keep the event loop free.
        payload = await asyncio.to_thread(handler, args)
    except ToolError as exc:
        log.warning("%s failed: %s %s", name, exc.code, exc.message)
        payload = exc.to_payload()
    except Exception as exc:
        log.exception("%s crashed", name)
        payload = ToolError(
            ErrorCode.INTERNAL,
            f"unexpected {type(exc).__name__}: {exc}",
            retryable=True,
        ).to_payload()

    # Returning a dict makes the SDK place it in `structuredContent` (validated
    # against outputSchema) and mirror it as JSON text in `content`.
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


async def _main() -> None:
    log.info("starting %s v%s (state=%s)", SERVER_NAME, SERVER_VERSION,
             os.environ.get("SCHEDULE_MCP_STATE_DIR", "./.state"))
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
