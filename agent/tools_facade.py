"""Thin typed facade over the two MCP connections.

Keeps the graph nodes readable and gives one place to log every MCP call for
the defence ("show that the agent discovers both MCP connections").
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from mcp_servers.schedule_mcp.domain.parser import html_to_rows
from mcp_servers.schedule_mcp.errors import ToolError as DomainParseError

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

    # ------------------------------------------------------------------ #
    # Ticket B2b: schedule.kse.ua has no unfiltered view (ticket B0) - a
    # discipline must be chosen before any session renders. capture_timetable
    # above handles one already-known page; this sweeps a whole list of
    # disciplines for one date and merges them into one document.
    # ------------------------------------------------------------------ #
    async def capture_full_week(self, url_template: str, disciplines: list[str], date: str) -> str:
        """Visit every discipline in `disciplines` for `date` and merge their
        sessions into one `<table class="schedule">` document.

        `url_template` is the confirmed pattern
        `https://schedule.kse.ua/?date=YYYY-MM-DD&discipline=<COURSE_CODE>`
        (see docs/00-execution-plan.md); `YYYY-MM-DD` and `<COURSE_CODE>` are
        substituted per discipline. Raises ValueError immediately - before
        touching the browser - if either placeholder is missing or `date` is
        falsy, rather than silently navigating the same unfiltered URL once
        per discipline.

        Waits for `.schedule-grid-header` (one of the day-of-week column
        headers, confirmed always present whenever the grid itself rendered,
        whether or not this particular discipline has any sessions that
        week - `mcp_servers/schedule_mcp/domain/parser.py`'s own grid parser
        requires it unconditionally too). This deliberately does not wait on
        an event-card selector: most current disciplines genuinely have zero
        sessions in an arbitrary week (confirmed live against a random
        sample of the KSE course catalog - see the PR body), and waiting on
        e.g. `.schedule-event-card` directly would misreport every one of
        them as SelectorNeverAppearedError after burning the full poll
        budget, instead of the empty-but-successful result it actually is.

        Deliberately NOT `calendar-date[value]` (the filter card's date
        picker) either: that element is part of the page's outer shell, not
        the grid, so it survives even if the grid's own markup were renamed -
        which would then have every discipline silently read as "zero
        sessions" instead of failing loudly. `.schedule-grid-header` is
        specific to the grid actually being intact, so if it disappears the
        wait step keeps polling and eventually raises
        SelectorNeverAppearedError.

        Once the grid frame is confirmed present, whether THIS discipline has
        any sessions is decided by counting `.schedule-event-card` elements
        directly in the captured HTML - not by pattern-matching
        `html_to_rows`' error message, which would silently misclassify any
        future rewording of that message (or an unrelated parser bug) as
        "no sessions" instead of surfacing it. Zero cards is skipped as a
        legitimate empty result; one or more cards means `html_to_rows` is
        expected to succeed, and any `ToolError` it does raise propagates
        unconditionally, tagged with which discipline it came from.

        Always parses with the parser's own default `table_selector`
        ("table.schedule") regardless of `SCHEDULE_TABLE_SELECTOR`: the live
        KSE page never has a `<table>` at all, so the parser's own
        `.schedule-event-card` fallback is what actually runs - passing a
        grid-specific selector through as `table_selector` would instead
        make `soup.select_one` match a stray card `<div>` as "the table" and
        fail with a confusing "table has no header row" (verified live).

        SCRAPE_MIN_INTERVAL_SEC is honoured between every discipline visited,
        not just once per run.
        """
        if "YYYY-MM-DD" not in url_template or "<COURSE_CODE>" not in url_template:
            raise ValueError(
                f"url_template {url_template!r} is missing the YYYY-MM-DD and/or "
                "<COURSE_CODE> placeholder - refusing to navigate the same URL "
                "once per discipline"
            )
        if not date:
            raise ValueError("capture_full_week requires a non-empty date")

        all_rows: list[dict[str, Any]] = []
        for i, code in enumerate(disciplines):
            if i > 0:
                await asyncio.sleep(CONFIG.scrape_min_interval_sec)
            page_url = url_template.replace("YYYY-MM-DD", date).replace("<COURSE_CODE>", code)
            page_html = await self.capture_timetable(page_url, _KSE_GRID_FRAME_SELECTOR)
            if not BeautifulSoup(page_html, "lxml").select(".schedule-event-card"):
                continue  # grid frame confirmed rendered above; genuinely zero sessions
            try:
                all_rows.extend(html_to_rows(page_html, source_ref=page_url))
            except DomainParseError as exc:
                raise type(exc)(
                    exc.code, f"discipline {code!r}: {exc.message}", exc.details, exc.retryable
                ) from exc
        return _rows_to_table_html(all_rows)


_KSE_GRID_FRAME_SELECTOR = ".schedule-grid-header"

# Preferred column order when re-serialising rows into a synthetic table;
# any other key actually present in a row (room, teacher, topic, modality)
# is appended rather than dropped, so a discipline whose rows do carry them
# does not silently lose that data.
_PREFERRED_COLUMNS = ["date", "time_range", "course_code", "course_title", "group", "kind"]


def _rows_to_table_html(rows: list[dict[str, Any]]) -> str:
    """Re-serialise parsed rows into the canonical `<table class="schedule">`
    shape `ingest_timetable_snapshot` already parses and is tested against.

    capture_full_week visits one discipline at a time, so a single capture
    only ever covers one course's grid. Re-emitting every discipline's rows
    as one table - instead of concatenating raw grid HTML fragments, which
    would break the grid parser's cell-count and calendar-date checks - lets
    ingest build one snapshot for the whole week without any change to its
    frozen contract.
    """
    extra = sorted({key for row in rows for key in row} - set(_PREFERRED_COLUMNS))
    columns = [*_PREFERRED_COLUMNS, *extra]
    head = "".join(f"<th>{html_lib.escape(c)}</th>" for c in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html_lib.escape(str(row.get(c, '')))}</td>" for c in columns)
        body.append(f"<tr>{cells}</tr>")
    return f'<table class="schedule"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'
