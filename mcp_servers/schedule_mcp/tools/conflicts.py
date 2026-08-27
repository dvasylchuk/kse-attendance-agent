"""Tool 3 - OPEN TICKET A3 (Track A).

`detect_schedule_conflicts` cross-checks candidate sessions against the
student's exported calendar and against each other.

WHAT TO IMPLEMENT (the contract in schemas.CONFLICTS_INPUT/OUTPUT is fixed;
do not change it without updating docs/03-tool-contracts.md):

  1. store.load_snapshot(snapshot_id); resolve session_ids -> Session objects.
     An unknown session id is INVALID_INPUT with the offending ids in details.
  2. calendar.load_busy_blocks(calendar_path).
  3. For each session x block: compute overlap in minutes.
       overlap > 0 and block.hard      -> CALENDAR_HARD
       overlap > 0 and not block.hard  -> CALENDAR_SOFT   (skip if include_soft is False)
       overlap == 0 but the gap between them is < min_gap_minutes and the
       session is ONSITE                                  -> TRAVEL_INFEASIBLE
  4. For each pair of sessions on the same date: overlap > 0 -> SESSION_OVERLAP.
  5. blocked_session_ids = sessions with at least one CALENDAR_HARD,
     SESSION_OVERLAP or TRAVEL_INFEASIBLE conflict.
  6. Zero conflicts is a SUCCESS: ok({"conflicts": [], "conflict_count": 0, ...}).

DEFINITION OF DONE
  * tests/test_conflicts.py covers: hard overlap, soft overlap, travel gap,
    session-vs-session overlap, and the empty (no conflict) case;
  * an unknown session_id returns INVALID_INPUT, not a crash;
  * a missing calendar file surfaces as DATA_SOURCE_UNAVAILABLE.
"""

from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, ToolError


def detect_schedule_conflicts(args: dict[str, Any]) -> dict[str, Any]:
    raise ToolError(
        ErrorCode.NOT_IMPLEMENTED,
        "detect_schedule_conflicts is not implemented yet (ticket A3)",
        details={"ticket": "A3", "contract": "docs/03-tool-contracts.md#detect_schedule_conflicts"},
    )
