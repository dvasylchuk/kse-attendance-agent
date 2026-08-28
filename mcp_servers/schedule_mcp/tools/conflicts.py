"""Tool 3 (ticket A3 - implemented).

`detect_schedule_conflicts` cross-checks candidate sessions against the
student's exported calendar and against each other. See the module docstring
history in git for the original ticket spec; the contract lives in
schemas.CONFLICTS_INPUT/OUTPUT and docs/03-tool-contracts.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..domain import calendar, store
from ..domain.models import Conflict, ConflictKind, Modality, Session
from ..errors import ErrorCode, ToolError, ok


def _overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    delta = (earliest_end - latest_start).total_seconds() / 60
    return int(delta) if delta > 0 else 0


def _gap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    """Distance in minutes between two non-overlapping intervals."""
    if a_end <= b_start:
        return int((b_start - a_end).total_seconds() / 60)
    return int((a_start - b_end).total_seconds() / 60)


def detect_schedule_conflicts(args: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = args["snapshot_id"]
    session_ids = args["session_ids"]
    calendar_path = args.get("calendar_path", "data/calendar.sample.ics")
    min_gap_minutes = args.get("min_gap_minutes", 30)
    include_soft = args.get("include_soft", True)

    snap = store.load_snapshot(snapshot_id)
    by_id = {s.session_id: s for s in snap.sessions}

    unknown = sorted(sid for sid in session_ids if sid not in by_id)
    if unknown:
        raise ToolError(
            ErrorCode.INVALID_INPUT,
            f"unknown session_id(s): {unknown}",
            details={"unknown_session_ids": unknown},
        )

    sessions = [by_id[sid] for sid in session_ids]
    blocks = calendar.load_busy_blocks(calendar_path)

    conflicts: list[Conflict] = []
    blocked: set[str] = set()

    def add(kind: ConflictKind, session_id: str, against: str, overlap_minutes: int, explanation: str) -> None:
        conflicts.append(
            Conflict(
                kind=kind,
                session_id=session_id,
                against=against,
                overlap_minutes=overlap_minutes,
                explanation=explanation,
            )
        )
        if kind in (ConflictKind.CALENDAR_HARD, ConflictKind.SESSION_OVERLAP, ConflictKind.TRAVEL_INFEASIBLE):
            blocked.add(session_id)

    def _bounds(s: Session) -> tuple[datetime, datetime]:
        return datetime.combine(s.date, s.start), datetime.combine(s.date, s.end)

    for s in sessions:
        s_start, s_end = _bounds(s)
        for b in blocks:
            overlap = _overlap_minutes(s_start, s_end, b.start, b.end)
            if overlap > 0:
                if b.hard:
                    add(
                        ConflictKind.CALENDAR_HARD, s.session_id, b.block_id, overlap,
                        f"overlaps hard calendar block '{b.title}' by {overlap} min",
                    )
                elif include_soft:
                    add(
                        ConflictKind.CALENDAR_SOFT, s.session_id, b.block_id, overlap,
                        f"overlaps soft calendar block '{b.title}' by {overlap} min",
                    )
            elif s.modality == Modality.ONSITE:
                gap = _gap_minutes(s_start, s_end, b.start, b.end)
                if gap < min_gap_minutes:
                    add(
                        ConflictKind.TRAVEL_INFEASIBLE, s.session_id, b.block_id, 0,
                        f"only {gap} min between this onsite session and busy block '{b.title}' "
                        f"(needs {min_gap_minutes})",
                    )

    for i in range(len(sessions)):
        for j in range(i + 1, len(sessions)):
            a, other = sessions[i], sessions[j]
            if a.date != other.date:
                continue
            a_start, a_end = _bounds(a)
            o_start, o_end = _bounds(other)
            overlap = _overlap_minutes(a_start, a_end, o_start, o_end)
            if overlap > 0:
                add(
                    ConflictKind.SESSION_OVERLAP, a.session_id, other.session_id, overlap,
                    f"overlaps session {other.session_id} ({other.course_code}) by {overlap} min",
                )
                add(
                    ConflictKind.SESSION_OVERLAP, other.session_id, a.session_id, overlap,
                    f"overlaps session {a.session_id} ({a.course_code}) by {overlap} min",
                )

    data = {
        "conflicts": [c.model_dump(mode="json") for c in conflicts],
        "conflict_count": len(conflicts),
        "blocked_session_ids": sorted(blocked),
        "checked_sessions": len(sessions),
        "calendar_blocks": len(blocks),
    }
    warnings = [] if conflicts else ["no conflicts found for the given sessions"]
    return ok(data, warnings=warnings)
