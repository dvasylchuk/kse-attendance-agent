"""Tool 1 (REFERENCE IMPLEMENTATION - ticket A1 is closed).

`ingest_timetable_snapshot` is the primary data-source tool: it is the only
place where raw timetable material enters the domain. It parses, normalises,
validates, de-duplicates and versions the timetable, and returns a snapshot id
that every other tool consumes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..domain import parser, store
from ..domain.models import TimetableSnapshot
from ..errors import ErrorCode, ToolError, ok


def ingest_timetable_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    source = args["source"]
    selector = args.get("table_selector", "table.schedule")

    if source == "playwright_html":
        raw = args.get("raw_html")
        if not raw or not raw.strip():
            raise ToolError(
                ErrorCode.INVALID_INPUT,
                "source='playwright_html' requires a non-empty raw_html",
                details={"received_keys": sorted(args)},
            )
        rows = parser.html_to_rows(raw, selector)
        source_ref = args.get("source_ref") or "playwright:live-page"

    elif source == "fixture_html":
        path = _require_path(args)
        rows = parser.html_to_rows(_read_text(path), selector)
        source_ref = args.get("source_ref") or path

    elif source == "local_dataset":
        path = _require_path(args)
        rows = parser.load_json_rows(path)
        source_ref = args.get("source_ref") or path

    else:  # unreachable if the schema is honoured; guards direct calls
        raise ToolError(ErrorCode.INVALID_INPUT, f"unknown source {source!r}")

    sessions, warnings = parser.rows_to_sessions(rows)

    # A genuinely empty week is a SUCCESS with zero sessions, not an error.
    if not sessions:
        return ok(
            {
                "snapshot_id": "",
                "captured_at": datetime.now(UTC).isoformat(),
                "date_from": None,
                "date_to": None,
                "session_count": 0,
                "groups": [],
                "courses": [],
                "rejected_rows": len(warnings),
                "is_new_snapshot": False,
            },
            warnings=warnings + ["timetable parsed successfully but contains no sessions"],
        )

    snapshot_id = parser.snapshot_id_for(source_ref, sessions)
    already = snapshot_id in store.list_snapshot_ids()

    snap = TimetableSnapshot(
        snapshot_id=snapshot_id,
        source={"playwright_html": "playwright", "fixture_html": "fixture",
                "local_dataset": "local_dataset"}[source],
        source_ref=source_ref,
        captured_at=datetime.now(UTC),
        date_from=min(s.date for s in sessions),
        date_to=max(s.date for s in sessions),
        sessions=sessions,
    )
    if not already:
        store.save_snapshot(snap)

    return ok(
        {
            "snapshot_id": snap.snapshot_id,
            "captured_at": snap.captured_at.isoformat(),
            "date_from": snap.date_from.isoformat(),
            "date_to": snap.date_to.isoformat(),
            "session_count": len(snap.sessions),
            "groups": snap.groups(),
            "courses": snap.courses(),
            "rejected_rows": len(warnings),
            "is_new_snapshot": not already,
        },
        warnings=warnings,
    )


def _require_path(args: dict[str, Any]) -> str:
    path = args.get("path")
    if not path:
        raise ToolError(
            ErrorCode.INVALID_INPUT,
            f"source={args['source']!r} requires 'path'",
            details={"received_keys": sorted(args)},
        )
    return path


def _read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise ToolError(
            ErrorCode.DATA_SOURCE_UNAVAILABLE,
            f"file not found: {path}",
            details={"path": path, "cwd": str(Path.cwd())},
        )
    return p.read_text(encoding="utf-8")
