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
from datetime import date, time
from typing import Any

from bs4 import BeautifulSoup

from ..errors import ErrorCode, ToolError
from .models import Modality, Session, SessionKind

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")
_RANGE_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})")

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


def html_to_rows(html: str, table_selector: str = "table.schedule") -> list[dict[str, Any]]:
    """Extract raw rows from the timetable markup captured by Playwright MCP.

    Expected shape: a <table> whose <thead> carries the column names
    (date, time, course_code, course_title, group, kind, room, teacher, topic).
    Column order is read from the header, not hard-coded.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one(table_selector) or soup.find("table")
    if table is None:
        raise ToolError(
            ErrorCode.PARSE_FAILED,
            f"no timetable table found for selector {table_selector!r}",
            details={"selector": table_selector, "html_length": len(html)},
        )

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
