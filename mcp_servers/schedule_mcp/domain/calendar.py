"""Personal calendar (.ics) -> BusyBlock conversion."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..errors import ErrorCode, ToolError
from .models import BusyBlock

_SOFT_HINTS = ("optional", "tentative", "gym", "необов", "можливо")


def load_busy_blocks(path: str) -> list[BusyBlock]:
    """Read an exported .ics calendar into hard/soft busy blocks.

    Soft blocks are recognised by a hint word in the summary or by an ICS
    TRANSP:TRANSPARENT / STATUS:TENTATIVE marker. Everything else is hard.
    """
    try:
        from icalendar import Calendar
    except ImportError as exc:  # pragma: no cover
        raise ToolError(ErrorCode.INTERNAL, "icalendar package is not installed") from exc

    try:
        with open(path, "rb") as fh:
            cal = Calendar.from_ical(fh.read())
    except FileNotFoundError as exc:
        raise ToolError(
            ErrorCode.DATA_SOURCE_UNAVAILABLE,
            f"calendar file not found: {path}",
            details={"path": path},
        ) from exc
    except Exception as exc:
        raise ToolError(
            ErrorCode.PARSE_FAILED, f"calendar is not valid iCalendar: {exc}", details={"path": path}
        ) from exc

    blocks: list[BusyBlock] = []
    for i, comp in enumerate(cal.walk("VEVENT")):
        start = comp.get("dtstart")
        end = comp.get("dtend")
        if start is None:
            continue
        s = start.dt
        e = end.dt if end is not None else s + timedelta(hours=1)
        if not isinstance(s, datetime):
            s = datetime.combine(s, datetime.min.time())
        if not isinstance(e, datetime):
            e = datetime.combine(e, datetime.min.time())
        s, e = s.replace(tzinfo=None), e.replace(tzinfo=None)
        if e <= s:
            continue
        summary = str(comp.get("summary") or "busy")
        soft = str(comp.get("transp") or "").upper() == "TRANSPARENT" \
            or str(comp.get("status") or "").upper() == "TENTATIVE" \
            or any(h in summary.lower() for h in _SOFT_HINTS)
        blocks.append(
            BusyBlock(
                block_id=str(comp.get("uid") or f"evt-{i}"),
                title=summary[:200],
                start=s,
                end=e,
                hard=not soft,
            )
        )
    return blocks
