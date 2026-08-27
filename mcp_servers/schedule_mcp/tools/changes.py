"""Tool 2 (REFERENCE IMPLEMENTATION - ticket A2 is closed).

`detect_timetable_changes` exists because the university timetable is edited
during the term. It diffs two snapshots into added / removed / moved sessions
and, when a plan id is supplied, reports which plan items the change
invalidates. Its `replan_required` flag is what drives the agent's re-planning
loop: a tool result that decides the next step.
"""

from __future__ import annotations

from typing import Any

from ..domain import store
from ..domain.models import Session
from ..errors import ok


def _key(s: Session) -> tuple[str, str, str]:
    """Identity of a class independent of when it happens to be scheduled."""
    return (s.course_code, s.group, s.kind.value)


def _slot(s: Session) -> dict[str, Any]:
    return {
        "session_id": s.session_id,
        "course_code": s.course_code,
        "group": s.group,
        "kind": s.kind.value,
        "date": s.date.isoformat(),
        "start": s.start.strftime("%H:%M"),
        "end": s.end.strftime("%H:%M"),
        "room": s.room,
        "topic": s.topic,
    }


def detect_timetable_changes(args: dict[str, Any]) -> dict[str, Any]:
    new_id = args["new_snapshot_id"]
    new_snap = store.load_snapshot(new_id)

    base_id = args.get("baseline_snapshot_id") or store.latest_snapshot_id(exclude=new_id)
    if not base_id:
        return ok(
            {
                "baseline_snapshot_id": None,
                "added": [], "removed": [], "moved": [], "change_count": 0,
            },
            warnings=["no earlier snapshot exists; nothing to diff against"],
        )
    base_snap = store.load_snapshot(base_id)

    course_filter = {c.upper() for c in (args.get("courses") or [])}

    def keep(s: Session) -> bool:
        return not course_filter or s.course_code in course_filter

    new_by_id = {s.session_id: s for s in new_snap.sessions if keep(s)}
    old_by_id = {s.session_id: s for s in base_snap.sessions if keep(s)}

    added_ids = set(new_by_id) - set(old_by_id)
    removed_ids = set(old_by_id) - set(new_by_id)

    # A "move" is a removal and an addition that share the class identity.
    moved: list[dict[str, Any]] = []
    matched_add: set[str] = set()
    matched_rem: set[str] = set()
    old_by_key: dict[tuple[str, str, str], list[str]] = {}
    for rid in removed_ids:
        old_by_key.setdefault(_key(old_by_id[rid]), []).append(rid)
    for aid in sorted(added_ids):
        bucket = old_by_key.get(_key(new_by_id[aid]))
        if bucket:
            rid = bucket.pop(0)
            moved.append({"from": _slot(old_by_id[rid]), "to": _slot(new_by_id[aid])})
            matched_add.add(aid)
            matched_rem.add(rid)

    added = [_slot(new_by_id[i]) for i in sorted(added_ids - matched_add)]
    removed = [_slot(old_by_id[i]) for i in sorted(removed_ids - matched_rem)]
    change_count = len(added) + len(removed) + len(moved)

    data: dict[str, Any] = {
        "baseline_snapshot_id": base_id,
        "added": added,
        "removed": removed,
        "moved": moved,
        "change_count": change_count,
    }

    plan_id = args.get("plan_id")
    if plan_id:
        plan = store.load_plan(plan_id)
        gone = {r["session_id"] for r in removed} | {m["from"]["session_id"] for m in moved}
        invalidated = [
            {"session_id": it.session_id, "course_code": it.course_code,
             "reason": "moved" if it.session_id in {m["from"]["session_id"] for m in moved}
                       else "removed"}
            for it in plan.items
            if it.session_id in gone
        ]
        data["plan_impact"] = {
            "plan_id": plan_id,
            "invalidated_items": invalidated,
            "replan_required": bool(invalidated) or bool(added),
        }

    warnings = []
    if change_count == 0:
        warnings.append("timetable is unchanged between the two snapshots")
    return ok(data, warnings=warnings)
