"""Tests for PlaywrightTools.capture_timetable (ticket B2).

Uses a fake MCP session (no socket, no browser - CI runs offline) that
returns the exact response shapes observed live against
`npx @playwright/mcp@latest` and recorded in docs/playwright-tools.json:
`browser_navigate`/`browser_evaluate` failures come back as `isError=True`
with a free-text `content[0].text`; a successful `browser_evaluate` wraps its
JSON-encoded return value between a '### Result' heading and a
'### Ran Playwright code' footer, since these tools have no `outputSchema` to
return structured content through.

`poll_interval_sec=0` is passed everywhere so the retry tests run instantly -
capture_timetable sleeps locally between polls (no `browser_wait_for` round
trip), so this needs no mocking of time itself.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent.tools_facade import (
    BrowserStartError,
    PageUnreachableError,
    PlaywrightTools,
    SelectorNeverAppearedError,
)

URL = "https://schedule.kse.ua/?date=2026-09-07&discipline=ECON301"
SELECTOR = "table.schedule"


@dataclass
class _TextContent:
    text: str


@dataclass
class _Result:
    content: list[_TextContent]
    isError: bool = False


def _ok_text(text: str) -> _Result:
    return _Result(content=[_TextContent(text)], isError=False)


def _error(message: str) -> _Result:
    return _Result(content=[_TextContent(f"### Error\n{message}")], isError=True)


def _empty_error() -> _Result:
    return _Result(content=[], isError=True)


def _eval_ok(value: Any) -> _Result:
    return _ok_text(f"### Result\n{json.dumps(value)}\n### Ran Playwright code\n```js\n...\n```")


@dataclass
class FakeSession:
    """Replays queued responses and records every (tool, args) call."""

    queue: list[_Result] = field(default_factory=list)
    calls: list[tuple[str, dict]] = field(default_factory=list)

    async def call_tool(self, name: str, args: dict) -> _Result:
        self.calls.append((name, args))
        return self.queue.pop(0)


def _run(coro):
    return asyncio.run(coro)


def _tools(session: FakeSession, attempts: int = 3) -> PlaywrightTools:
    return PlaywrightTools(session, poll_attempts=attempts, poll_interval_sec=0)


def test_successful_capture_returns_full_document_html():
    html = "<html><body><table class=\"schedule\"></table></body></html>"
    session = FakeSession(queue=[
        _ok_text("navigated"),          # browser_navigate
        _eval_ok(True),                 # selector check: found on first try
        _eval_ok(html),                 # outerHTML
    ])
    pw = _tools(session)

    result = _run(pw.capture_timetable(URL, SELECTOR))

    assert result == html
    tool_names = [name for name, _ in session.calls]
    assert tool_names == ["browser_navigate", "browser_evaluate", "browser_evaluate"]


def test_only_read_only_navigation_tools_are_used():
    """No browser_type / browser_fill_form / browser_click / credentials."""
    session = FakeSession(queue=[_ok_text("nav"), _eval_ok(True), _eval_ok("<html></html>")])
    pw = _tools(session)

    _run(pw.capture_timetable(URL, SELECTOR))

    allowed = {"browser_navigate", "browser_evaluate"}
    assert {name for name, _ in session.calls} <= allowed
    for _, args in session.calls:
        assert "credential" not in json.dumps(args).lower()


def test_selector_polling_retries_before_succeeding():
    session = FakeSession(queue=[
        _ok_text("nav"),
        _eval_ok(False),                # attempt 1: not there yet
        _eval_ok(True),                 # attempt 2: found
        _eval_ok("<html>ready</html>"),
    ])
    pw = _tools(session, attempts=3)

    result = _run(pw.capture_timetable(URL, SELECTOR))

    assert result == "<html>ready</html>"
    assert [n for n, _ in session.calls].count("browser_evaluate") == 3


def test_selector_never_appearing_raises_typed_error_with_correct_wait_budget(monkeypatch):
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("agent.tools_facade.asyncio.sleep", _fake_sleep)

    attempts = 3
    queue = [_ok_text("nav")] + [_eval_ok(False) for _ in range(attempts)]
    session = FakeSession(queue=queue)
    pw = PlaywrightTools(session, poll_attempts=attempts, poll_interval_sec=5)

    with pytest.raises(SelectorNeverAppearedError, match=SELECTOR) as exc_info:
        _run(pw.capture_timetable(URL, SELECTOR))

    # (attempts - 1) waits of 5s each = 10s, not attempts * interval = 15s -
    # no wait follows the last, failed attempt.
    assert "10s" in str(exc_info.value)
    assert slept == [5, 5]
    assert [n for n, _ in session.calls].count("browser_evaluate") == attempts


def test_unreachable_page_raises_page_unreachable_error():
    session = FakeSession(queue=[
        _error("browserBackend.callTool: net::ERR_NAME_NOT_RESOLVED at " + URL),
    ])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError, match="ERR_NAME_NOT_RESOLVED"):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_browser_launch_failure_raises_browser_start_error():
    session = FakeSession(queue=[
        _error("browserType.launch: Executable doesn't exist at /path/to/chromium"),
    ])
    pw = _tools(session)

    with pytest.raises(BrowserStartError, match="Executable doesn't exist"):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_a_plain_network_error_is_not_misclassified_as_a_launch_failure():
    session = FakeSession(queue=[
        _error("browserBackend.callTool: net::ERR_CONNECTION_REFUSED at " + URL),
    ])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_browser_crash_during_selector_polling_is_a_typed_error_not_a_timeout():
    """A dead browser must not be reported as 'selector never appeared' -
    that would blame the page for a problem that is actually the browser's."""
    session = FakeSession(queue=[
        _ok_text("nav"),
        _error("Browser has been closed"),
    ])
    pw = _tools(session, attempts=5)

    with pytest.raises(BrowserStartError, match="Browser has been closed"):
        _run(pw.capture_timetable(URL, SELECTOR))
    # must fail immediately, not burn the whole poll budget first
    assert [n for n, _ in session.calls].count("browser_evaluate") == 1


def test_page_disappearing_between_selector_check_and_html_read_is_unreachable():
    session = FakeSession(queue=[
        _ok_text("nav"),
        _eval_ok(True),
        _error("Execution context was destroyed, most likely because of a navigation"),
    ])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError, match="Execution context was destroyed"):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_malformed_evaluate_response_is_reported_not_raised_as_a_bare_exception():
    session = FakeSession(queue=[
        _ok_text("nav"),
        _eval_ok(True),
        _ok_text("not the expected ### Result shape at all"),
    ])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError, match="unexpected browser_evaluate response shape"):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_unparseable_json_in_result_is_reported_not_raised_as_a_bare_exception():
    session = FakeSession(queue=[
        _ok_text("nav"),
        _eval_ok(True),
        _ok_text("### Result\nnot valid json{{\n### Ran Playwright code\n```js\n...\n```"),
    ])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError, match="could not parse browser_evaluate result"):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_non_string_result_from_evaluate_is_rejected():
    """A null/number/bool outerHTML read must not silently become
    state["raw_html"] and surface as a confusing INVALID_INPUT two nodes
    later in ingest_timetable_snapshot."""
    session = FakeSession(queue=[_ok_text("nav"), _eval_ok(True), _eval_ok(None)])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError, match="non-HTML content"):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_empty_error_content_does_not_crash_and_is_still_unreachable():
    session = FakeSession(queue=[_empty_error()])
    pw = _tools(session)

    with pytest.raises(PageUnreachableError):
        _run(pw.capture_timetable(URL, SELECTOR))


def test_response_with_trailing_cr_and_code_fence_still_parses():
    """Neither a trailing \\r nor a code-fenced result is guaranteed by the
    tool's schema - both were seen as plausible variants of the live shape,
    so the parser must tolerate them rather than only the exact bytes one
    manual probe happened to produce."""
    html = "<html>ok</html>"
    fenced = f"### Result\r\n```\r\n{json.dumps(html)}\r\n```\r\n### Ran Playwright code\r\n..."
    session = FakeSession(queue=[_ok_text("nav"), _eval_ok(True), _ok_text(fenced)])
    pw = _tools(session)

    result = _run(pw.capture_timetable(URL, SELECTOR))

    assert result == html
