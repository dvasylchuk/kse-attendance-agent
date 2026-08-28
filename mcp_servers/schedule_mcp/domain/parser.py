"""Timetable parsing + normalisation + validation.

Accepts either the raw HTML captured by Playwright MCP, or a pre-parsed JSON
dataset shipped in data/. Both paths go through the SAME normalisation and
validation code — the offline fixture is not a shortcut that returns a
prewritten answer (Part D requirement).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, time, timedelta
from typing import Any

from bs4 import BeautifulSoup

from ..errors import ErrorCode, ToolError
from .models import Modality, Session, SessionKind

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")
_RANGE_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})")

# schedule.kse.ua (verified live, ticket B0) does not render a <table
# class="schedule">: each class session is a `.schedule-event-card` inside a
# `.schedule-grid-cell`, positioned by a fixed (time-slot row, weekday column)
# grid rather than by any per-event date/time attribute. The card's
# aria-label is the only structured text: "CODE · Title · Kind, гр.N".
_KSE_CARD_RE = re.compile(
    r"^(?P<code>\S+)\s*[·•]\s*(?P<title>.+?)\s*[·•]\s*(?P<kind>[^,]+?)"
    r"(?:\s*,\s*гр\.\s*(?P<group>\S+))?\s*$"
)
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

_KIND_ALIASES = {
    "лекція": SessionKind.LECTURE, "лекц": SessionKind.LECTURE, "lecture": SessionKind.LECTURE,
    "семінар": SessionKind.SEMINAR, "practice": SessionKind.SEMINAR, "seminar": SessionKind.SEMINAR,
    "практика": SessionKind.SEMINAR,
    "лаб": SessionKind.LAB, "lab": SessionKind.LAB,
    "екзамен": SessionKind.EXAM, "exam": SessionKind.EXAM,
}


def _parse_time(raw: str) -> time:
    m = _TIME_RE.match(raw)
    if not m:
        raise ToolError(ErrorCode.PARSE_FAILED, f"unparsable time value: {raw!r}")
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise ToolError(ErrorCode.PARSE_FAILED, f"time out of range: {raw!r}")
    return time(h, mi)


def parse_time_range(raw: str) -> tuple[time, time]:
    m = _RANGE_RE.search(raw or "")
    if not m:
        raise ToolError(ErrorCode.PARSE_FAILED, f"unparsable time range: {raw!r}")
    return time(int(m.group(1)), int(m.group(2))), time(int(m.group(3)), int(m.group(4)))


def normalise_kind(raw: str | None) -> SessionKind:
    low = (raw or "").strip().lower()
    for alias, kind in _KIND_ALIASES.items():
        if alias in low:
            return kind
    return SessionKind.SEMINAR


def make_session_id(course_code: str, group: str, d: date, start: time) -> str:
    return f"{course_code}-{group}-{d.isoformat()}-{start.strftime('%H%M')}"


def rows_to_sessions(rows: list[dict[str, Any]]) -> tuple[list[Session], list[str]]:
    """Normalise raw row dicts into validated Session objects.

    Returns (sessions, warnings). Rows that cannot be normalised become
    warnings rather than killing the whole ingest — but a snapshot where EVERY
    row failed raises PARSE_FAILED, so the caller can tell "page changed"
    from "the week is genuinely empty".
    """
    sessions: list[Session] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for idx, row in enumerate(rows):
        try:
            d = row["date"]
            d = d if isinstance(d, date) else date.fromisoformat(str(d).strip())
            if row.get("time_range"):
                start, end = parse_time_range(str(row["time_range"]))
            else:
                start, end = _parse_time(str(row["start"])), _parse_time(str(row["end"]))

            course_code = str(row["course_code"]).strip().upper()
            group = str(row["group"]).strip().upper()
            sid = make_session_id(course_code, group, d, start)
            if sid in seen:
                warnings.append(f"row {idx}: duplicate session {sid} dropped")
                continue
            seen.add(sid)

            sessions.append(
                Session(
                    session_id=sid,
                    course_code=course_code,
                    course_title=str(row.get("course_title") or course_code).strip(),
                    group=group,
                    kind=normalise_kind(row.get("kind")),
                    modality=Modality(str(row.get("modality", "onsite")).lower()),
                    date=d,
                    start=start,
                    end=end,
                    room=(str(row["room"]).strip() if row.get("room") else None),
                    teacher=(str(row["teacher"]).strip() if row.get("teacher") else None),
                    topic=(str(row["topic"]).strip() if row.get("topic") else None),
                )
            )
        except ToolError as exc:
            warnings.append(f"row {idx}: {exc.message}")
        except Exception as exc:  # noqa: BLE001 - row-level tolerance is deliberate
            warnings.append(f"row {idx}: {type(exc).__name__}: {exc}")

    if rows and not sessions:
        raise ToolError(
            ErrorCode.PARSE_FAILED,
            "no row of the timetable could be normalised; the page layout most likely changed",
            details={"rows_seen": len(rows), "warnings": warnings[:10]},
        )
    return sessions, warnings


def html_to_rows(
    html: str, table_selector: str = "table.schedule", source_ref: str | None = None
) -> list[dict[str, Any]]:
    """Extract raw rows from the timetable markup captured by Playwright MCP.

    Two shapes are supported:

    1. A <table> whose <thead> carries the column names (date, time,
       course_code, course_title, group, kind, room, teacher, topic). Column
       order is read from the header, not hard-coded. This is what every
       recorded fixture under fixtures/playwright/ uses.
    2. The real schedule.kse.ua grid (verified live, ticket B0): no <table>
       for session data at all, just `.schedule-event-card` divs positioned
       in a fixed grid. Used automatically when no table matches.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one(table_selector) or soup.find("table")
    if table is not None:
        return _table_rows(table)
    if soup.select(".schedule-event-card"):
        return _kse_grid_rows(soup, source_ref)
    raise ToolError(
        ErrorCode.PARSE_FAILED,
        f"no timetable table found for selector {table_selector!r}",
        details={"selector": table_selector, "html_length": len(html)},
    )


def _table_rows(table: Any) -> list[dict[str, Any]]:
    header_cells = [th.get_text(strip=True).lower() for th in table.select("thead th")]
    if not header_cells:
        first = table.find("tr")
        header_cells = [c.get_text(strip=True).lower() for c in first.find_all(["th", "td"])] if first else []
    if not header_cells:
        raise ToolError(ErrorCode.PARSE_FAILED, "timetable table has no header row")

    rows: list[dict[str, Any]] = []
    body_rows = table.select("tbody tr") or table.find_all("tr")[1:]
    for tr in body_rows:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells or len(cells) < 2:
            continue
        rows.append({header_cells[i]: cells[i] for i in range(min(len(cells), len(header_cells)))})
    return rows


def _kse_grid_rows(soup: BeautifulSoup, source_ref: str | None) -> list[dict[str, Any]]:
    """Parse the real schedule.kse.ua layout.

    No event card carries its own date, so the visible week's Monday has to
    come from elsewhere on the page. The `<calendar-date value="...">` custom
    element (the filter card's date picker) carries the exact navigated date
    and is preferred; if that element is ever removed, we fall back to an
    ISO date embedded in `source_ref` (the convention capture_timetable, B2,
    is expected to follow: put the navigated `?date=` there). Column 0 =
    Monday, confirmed empirically against the live page (ticket B0): 6 day
    columns (Mon-Sat, no Sunday classes), one row per `Час пари N` time slot,
    cells in fixed row-major (slot outer, day inner) DOM order.

    Known gap, documented rather than silently guessed at: the card only
    exposes a *relative* group number ("гр.1"/"гр.2"), not the institutional
    group code (e.g. BE-3-1) used elsewhere in this domain, and teacher/room
    are hidden by the site itself unless logged in - both come back as None.

    Two failure modes are deliberately distinguished rather than both being
    "silently drop the row": if EVERY event card fails to match the expected
    aria-label shape, that means the label format itself changed, and this
    raises PARSE_FAILED immediately - the alternative (returning zero rows)
    would look identical to "this student genuinely has no classes this
    week" downstream. If only SOME cards fail to match, each one is turned
    into a row that is guaranteed to fail Session validation with the raw
    label in the message, so it surfaces as a row-level warning through the
    normal tolerance path in rows_to_sessions instead of being lost.
    """
    calendar_node = soup.select_one("calendar-date[value]")
    raw_date = calendar_node["value"] if calendar_node else None
    m = _ISO_DATE_RE.search(raw_date or "") or _ISO_DATE_RE.search(source_ref or "")
    if not m:
        raise ToolError(
            ErrorCode.PARSE_FAILED,
            "schedule.kse.ua grid has no per-event date in the markup, and "
            "neither <calendar-date value=...> nor source_ref carried one",
            details={"source_ref": source_ref},
        )
    anchor = date.fromisoformat(m.group(1))
    week_start = anchor - timedelta(days=anchor.weekday())

    headers: list[int] = []
    for node in soup.select(".schedule-grid-header"):
        day_spans = [s.get_text(strip=True) for s in node.find_all("span")]
        if len(day_spans) < 2 or not day_spans[-1].isdigit():
            raise ToolError(ErrorCode.PARSE_FAILED, "a day-of-week header has no day-of-month number")
        headers.append(int(day_spans[-1]))
    if not headers:
        raise ToolError(ErrorCode.PARSE_FAILED, "no day-of-week header ('schedule-grid-header') found in the grid")
    for i, day_of_month in enumerate(headers):
        expected = (week_start + timedelta(days=i)).day
        if day_of_month != expected:
            raise ToolError(
                ErrorCode.PARSE_FAILED,
                "grid header date does not match the anchor week; "
                "<calendar-date value=...> may be stale relative to the rendered grid",
                details={"column": i, "header_day": day_of_month, "expected_day": expected},
            )
    n_days = len(headers)

    slot_times: list[tuple[str, str]] = []
    for node in soup.select('[aria-label^="Час пари"]'):
        parts = [d.get_text(strip=True) for d in node.find_all("div", recursive=False) if d.get_text(strip=True)]
        if len(parts) < 2:
            raise ToolError(ErrorCode.PARSE_FAILED, "a time-slot legend entry has no start/end time")
        slot_times.append((parts[0], parts[-1]))
    if not slot_times:
        raise ToolError(ErrorCode.PARSE_FAILED, "no time-slot legend ('Час пари N') found in the grid")
    n_slots = len(slot_times)

    cells = soup.select(".schedule-grid-cell")
    if not cells or len(cells) != n_slots * n_days:
        raise ToolError(
            ErrorCode.PARSE_FAILED,
            "grid cell count does not match time-slots x day-headers; layout likely changed",
            details={"cells": len(cells), "slots": n_slots, "days": n_days},
        )

    rows: list[dict[str, Any]] = []
    unmatched_labels: list[str] = []
    for idx, cell in enumerate(cells):
        slot_idx, day_idx = divmod(idx, n_days)
        start_s, end_s = slot_times[slot_idx]
        session_date = week_start + timedelta(days=day_idx)
        for card in cell.select(".schedule-event-card"):
            label = (card.get("aria-label") or "").strip()
            match = _KSE_CARD_RE.match(label)
            if not match:
                unmatched_labels.append(label or "<empty aria-label>")
                continue
            group = match.group("group")
            rows.append(
                {
                    "date": session_date.isoformat(),
                    "time_range": f"{start_s}-{end_s}",
                    "course_code": match.group("code"),
                    "course_title": match.group("title"),
                    "group": f"GR{group}" if group else "GR0",
                    "kind": match.group("kind"),
                }
            )

    if unmatched_labels and not rows:
        raise ToolError(
            ErrorCode.PARSE_FAILED,
            "schedule.kse.ua event cards did not match the expected aria-label "
            "format ('CODE · Title · Kind, гр.N'); the page layout most likely changed",
            details={"unmatched_labels": unmatched_labels[:10]},
        )
    for label in unmatched_labels:
        # date deliberately unparsable: rows_to_sessions rejects this row and
        # its warning message carries the raw label, instead of the row
        # being lost with no trace.
        rows.append({"date": f"unrecognised schedule.kse.ua event card: {label}"})
    return rows


def load_json_rows(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError as exc:
        raise ToolError(
            ErrorCode.DATA_SOURCE_UNAVAILABLE,
            f"dataset file not found: {path}",
            details={"path": path},
        ) from exc
    except json.JSONDecodeError as exc:
        raise ToolError(
            ErrorCode.PARSE_FAILED, f"dataset is not valid JSON: {exc}", details={"path": path}
        ) from exc
    rows = payload.get("sessions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ToolError(ErrorCode.PARSE_FAILED, "dataset must be a list or {'sessions': [...]}")
    return rows


def snapshot_id_for(source_ref: str, sessions: list[Session]) -> str:
    digest = hashlib.sha256()
    digest.update(source_ref.encode())
    for s in sorted(sessions, key=lambda x: x.session_id):
        digest.update(s.session_id.encode())
    return "snap_" + digest.hexdigest()[:12]
