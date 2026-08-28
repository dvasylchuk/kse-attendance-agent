"""Thin typed facade over the two MCP connections.

Keeps the graph nodes readable and gives one place to log every MCP call for
the defence ("show that the agent discovers both MCP connections").
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .config import CONFIG

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


class PlaywrightCaptureError(RuntimeError):
    """Base class for every `capture_timetable` failure.

    Always raised as one of the concrete subclasses below, so `capture_page`
    (agent/graph.py) can tell what kind of failure happened from the
    exception type alone - it currently only needs `type(exc).__name__` for
    `degraded_reason`, but the distinction is real and worth keeping typed
    rather than folding everything into one message string.
    """


class BrowserStartError(PlaywrightCaptureError):
    """The Playwright MCP server could not launch a browser at all."""


class PageUnreachableError(PlaywrightCaptureError):
    """`browser_navigate` failed: DNS, connection refused, bad port, etc."""


class SelectorNeverAppearedError(PlaywrightCaptureError):
    """The configured selector never showed up within the wait budget."""


# Substrings observed (or documented by Playwright) in a browser-launch
# failure message, as opposed to a navigation/network failure or a mid-run
# crash. Playwright MCP does not expose a structured error code for this the
# way the custom schedule-mcp does - this is a best-effort classification
# over free text, not a guarantee; see docs/playwright-tools.json for what
# was actually observed live. "browser has been closed" is a mid-session
# crash rather than a start failure, but it leaves the browser just as
# unusable, so it is classified the same way here.
_LAUNCH_FAILURE_HINTS = (
    "executable doesn't exist",
    "failed to launch",
    "browser has been closed",
    "browser is not installed",
    "playwright install")


class PlaywrightTools:
    """Existing MCP server (Microsoft Playwright MCP).

    `capture_timetable` uses two tools, both confirmed live against
    schedule.kse.ua (ticket B0) with their schemas and one real response
    transcript recorded in docs/playwright-tools.json (ticket B2, extending
    the dump ticket B1 started):

    - `browser_navigate` to load the page;
    - `browser_evaluate`, polled with a `document.querySelector(...)` check,
      to wait for `selector` (there is no tool that waits on a CSS selector
      directly: `browser_wait_for` only supports literal text or a fixed
      delay - confirmed from its schema, not assumed), then called again to
      read `document.documentElement.outerHTML`.

    The wait is a local `asyncio.sleep` between polls, not `browser_wait_for`
    - that tool would add an unverified round trip for something a local
    sleep already does deterministically.

    `browser_snapshot` (the other tool documented in ticket B1) is
    deliberately not used here: it returns an accessibility-tree summary for
    a human to read, not HTML - `ingest_timetable_snapshot`'s parser
    (`mcp_servers/schedule_mcp/domain/parser.py`) runs BeautifulSoup over
    the real document markup, including re-selecting `table_selector` (or
    falling back to the KSE grid parser) from the *whole* page, so this
    returns the full document, not just the matched element's markup.

    Read-only and credential-free by construction: only `browser_navigate`
    and `browser_evaluate` are ever called - no `browser_type`,
    `browser_fill_form`, `browser_click`, or `browser_press_key`.
    """

    def __init__(
        self,
        session: Any,
        poll_attempts: int | None = None,
        poll_interval_sec: float | None = None,
    ) -> None:
        self._session = session
        self._poll_attempts = poll_attempts if poll_attempts is not None else CONFIG.selector_poll_attempts
        self._poll_interval_sec = (
            poll_interval_sec if poll_interval_sec is not None else CONFIG.selector_poll_interval_sec
        )

    async def discover(self) -> list[str]:
        res = await self._session.list_tools()
        names = [t.name for t in res.tools]
        log.info("playwright-mcp exposes %d tools: %s", len(names), names[:15])
        return names

    async def capture_timetable(self, url: str, selector: str) -> str:
        nav = await self._call("browser_navigate", {"url": url})
        if nav.isError:
            raise self._classify(self._text(nav))(self._text(nav))

        found = False
        for attempt in range(self._poll_attempts):
            check = await self._call(
                "browser_evaluate",
                {"function": f"() => !!document.querySelector({json.dumps(selector)})"},
            )
            if check.isError:
                raise self._classify(self._text(check))(self._text(check))
            if self._parse_eval_result(check) is True:
                found = True
                break
            if attempt < self._poll_attempts - 1:
                await asyncio.sleep(self._poll_interval_sec)
        if not found:
            waited = max(self._poll_attempts - 1, 0) * self._poll_interval_sec
            raise SelectorNeverAppearedError(
                f"selector {selector!r} never appeared on {url} after {waited:.0f}s"
            )

        html = await self._call("browser_evaluate", {"function": "() => document.documentElement.outerHTML"})
        if html.isError:
            raise self._classify(self._text(html))(self._text(html))
        result = self._parse_eval_result(html)
        if not isinstance(result, str) or not result:
            raise PageUnreachableError(f"browser_evaluate returned non-HTML content: {result!r}")
        return result

    async def _call(self, name: str, args: dict[str, Any]) -> Any:
        log.info("-> playwright-mcp.%s %s", name, json.dumps(args, ensure_ascii=False)[:200])
        res = await self._session.call_tool(name, args)
        log.info("<- playwright-mcp.%s isError=%s", name, res.isError)
        return res

    @staticmethod
    def _text(res: Any) -> str:
        if not res.content:
            return ""
        return getattr(res.content[0], "text", "")

    @classmethod
    def _parse_eval_result(cls, res: Any) -> Any:
        """Unwrap `browser_evaluate`'s response text.

        The live server does not return its result as MCP structuredContent
        (its outputSchema is null on every tool, confirmed in
        docs/playwright-tools.json) - it wraps a JSON-encoded value between a
        '### Result' heading and a '### Ran Playwright code' footer instead.
        Confirmed empirically against the live server; not documented by the
        tool's schema. Tolerates a trailing CR (Windows-hosted servers) and
        an optional surrounding code fence, since neither is guaranteed by
        anything in the tool's schema.
        """
        text = cls._text(res)
        match = re.search(r"### Result\r?\n(.*?)(?:\r?\n### Ran Playwright code|\Z)", text, re.DOTALL)
        if not match:
            raise PageUnreachableError(f"unexpected browser_evaluate response shape: {text[:200]!r}")
        payload = match.group(1).strip()
        if payload.startswith("```"):
            payload = payload.strip("`").strip()
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PageUnreachableError(f"could not parse browser_evaluate result: {exc}") from exc

    @staticmethod
    def _classify(message: str) -> type[PlaywrightCaptureError]:
        lowered = message.lower()
        if any(hint in lowered for hint in _LAUNCH_FAILURE_HINTS):
            return BrowserStartError
        return PageUnreachableError
