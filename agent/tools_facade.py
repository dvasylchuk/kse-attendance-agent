"""Thin typed facade over the two MCP connections.

Keeps the graph nodes readable and gives one place to log every MCP call for
the defence ("show that the agent discovers both MCP connections").
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("agent.mcp")


class ScheduleTools:
    """Custom MCP server. Returns the parsed ok/error envelope."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def discover(self) -> list[str]:
        res = await self._session.list_tools()
        names = [t.name for t in res.tools]
        log.info("schedule-mcp exposes %d tools: %s", len(names), names)
        return names

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        log.info("-> schedule-mcp.%s %s", name, json.dumps(args, ensure_ascii=False)[:300])
        res = await self._session.call_tool(name, args)
        if res.structuredContent is not None:
            payload = res.structuredContent
        else:  # schema-level rejection by the SDK, before our handler runs
            payload = {
                "ok": False,
                "error": {"code": "INVALID_INPUT", "message": res.content[0].text,
                          "details": {"stage": "mcp_input_validation"}, "retryable": False},
            }
        log.info("<- schedule-mcp.%s ok=%s", name, payload.get("ok"))
        return payload


class PlaywrightTools:
    """Existing MCP server (Microsoft Playwright MCP).

    TICKET B2: implement `capture_timetable` using the tools this server
    actually exposes (browser_navigate, browser_snapshot / browser_evaluate).
    Record the real tool names and their schemas into
    docs/03-tool-contracts.md#playwright - do not copy them from memory.
    """

    def __init__(self, session: Any) -> None:
        self._session = session

    async def discover(self) -> list[str]:
        res = await self._session.list_tools()
        names = [t.name for t in res.tools]
        log.info("playwright-mcp exposes %d tools: %s", len(names), names[:15])
        return names

    async def capture_timetable(self, url: str, selector: str) -> str:
        raise NotImplementedError("ticket B2")
