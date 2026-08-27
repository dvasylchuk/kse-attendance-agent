"""Wiring of the two MCP connections.

Connection 1 (existing, approved list): Microsoft Playwright MCP - launched as
a separate stdio process via `npx @playwright/mcp@latest`.
Connection 2 (custom): the Schedule MCP server in this repository, launched as
`python -m mcp_servers.schedule_mcp.server`.

Both are separate OS processes. Neither runs inside the agent process.
"""

from __future__ import annotations

import sys
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import CONFIG, ROOT


def server_specs(include_playwright: bool = True) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {
        "schedule": {
            "command": sys.executable,
            "args": ["-m", "mcp_servers.schedule_mcp.server"],
            "cwd": str(ROOT),
            "transport": "stdio",
            "env": {"SCHEDULE_MCP_STATE_DIR": str(ROOT / ".state")},
        }
    }
    # In offline mode the browser connection is deliberately not started: the
    # run then reads the recorded page from fixtures/ through the same parser.
    if include_playwright and not CONFIG.offline:
        specs["playwright"] = {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest", "--headless", "--isolated"],
            "transport": "stdio",
        }
    return specs


def build_client(include_playwright: bool = True) -> MultiServerMCPClient:
    return MultiServerMCPClient(server_specs(include_playwright))
