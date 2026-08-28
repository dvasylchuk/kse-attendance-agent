"""Tool 4 (ticket A4 - implemented). The core decision of the domain.

`optimize_attendance_plan` picks, for every required course, which group's
session to attend, so the student covers as much as possible in as few
campus days as possible without colliding with their calendar.

Algorithm
---------
1. `required_sessions` = the home group's distinct (course_code, kind, topic)
   units for the required courses. Each unit's candidate sessions are the
   home session plus, when `allow_cross_group`, any other group's session of
   the same course_code + kind whose topic is compatible (equal or either is
   empty).
2. `detect_schedule_conflicts` is called once over every distinct candidate
   id to get the calendar-driven CALENDAR_HARD / TRAVEL_INFEASIBLE verdicts
   (its own SESSION_OVERLAP verdicts are ignored here: those fire between
   *alternative* candidates for different units that would never be
   scheduled together, so they are not a real conflict yet). A candidate
   blocked by the calendar is dropped.
3. The instance is small, so the search is exact: every combination of
   distinct candidate dates up to the day budget is tried; for each day-set
   a backtracking search picks at most one legal, non-overlapping candidate
   per unit, maximising coverage, then minimising substitutions, then
   minimising the latest finish time. `max_coverage` ignores the day cap
   (its own description says so); `min_days` and `balanced` respect it.
4. If the winning plan's coverage is below `min_coverage_ratio`, this raises
   INFEASIBLE with the best achievable ratio and whether relaxing
   `max_campus_days` would fix it.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from datetime import date as date_cls
from datetime import datetime
from typing import Any

from ..domain import store
from ..domain.models import AttendancePlan, PlanItem, Session
from ..errors import ErrorCode, ToolError, ok
from .conflicts import detect_schedule_conflicts

_NODE_BUDGET_PER_DAY_SET = 20_000
_MAX_DAY_SETS_EVALUATED = 5_000

UnitKey = tuple[str, str, str]


def _unit_key(s: Session) -> UnitKey:
    return (s.course_code, s.kind.value, s.topic or "")


def _topic_compatible(a: str | None, b: str | None) -> bool:
    return a is None or b is None or a == b


def _bounds(s: Session) -> tuple[datetime, datetime]:
    return datetime.combine(s.date, s.start), datetime.combine(s.date, s.end)


def _time_overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _solve_for_day_set(
    unit_keys: list[UnitKey],
    legal_candidates: dict[UnitKey, list[Session]],
    home_units: dict[UnitKey, Session],
    day_set: frozenset[date_cls],
) -> dict[str, Any]:
    """Backtracking search: at most one legal, non-overlapping candidate per unit."""
    units: list[tuple[UnitKey, list[Session]]] = []
    for key in unit_keys:
        cands = [s for s in legal_candidates[key] if s.date in day_set]
        cands.sort(key=lambda s: (s.session_id != home_units[key].session_id, s.date, s.start, s.group))
        units.append((key, cands))
    units.sort(key=lambda u: len(u[1]))

    best_key: tuple[int, int, float] = (-1, 0, 0.0)
    best_assignment: dict[UnitKey, Session] = {}
    nodes = 0

    def solution_key(count: int, subs: int, finish: datetime | None) -> tuple[int, int, float]:
        finish_epoch = finish.timestamp() if finish else 0.0
        return (count, -subs, -finish_epoch)

    def backtrack(
        idx: int,
        chosen: dict[UnitKey, Session],
        day_intervals: dict[date_cls, list[tuple[datetime, datetime]]],
        count: int,
        subs: int,
    ) -> None:
        nonlocal nodes, best_key, best_assignment
        nodes += 1
        if nodes > _NODE_BUDGET_PER_DAY_SET:
            return
        if idx == len(units):
            finish = max((datetime.combine(s.date, s.end) for s in chosen.values()), default=None)
            key = solution_key(count, subs, finish)
            if key > best_key:
                best_key = key
                best_assignment = dict(chosen)
            return

        remaining = len(units) - idx
        if best_key[0] != -1 and count + remaining < best_key[0]:
            return

        unit_key, cands = units[idx]
        for s in cands:
            s_start, s_end = _bounds(s)
            bucket = day_intervals.setdefault(s.date, [])
            if any(_time_overlaps(s_start, s_end, bs, be) for bs, be in bucket):
                continue
            bucket.append((s_start, s_end))
            chosen[unit_key] = s
            backtrack(
                idx + 1, chosen, day_intervals, count + 1,
                subs + (0 if s.session_id == home_units[unit_key].session_id else 1),
            )
            bucket.pop()
            del chosen[unit_key]

        backtrack(idx + 1, chosen, day_intervals, count, subs)

    backtrack(0, {}, {}, 0, 0)
    days_used = sorted({s.date for s in best_assignment.values()})
    return {
        "count": max(best_key[0], 0),
        "subs": -best_key[1] if best_key[0] > 0 else 0,
        "assignment": best_assignment,
        "days_used": days_used,
    }


def _priority_key(objective: str, result: dict[str, Any]) -> tuple:
    count = result["count"]
    days = len(result["days_used"])
    subs = result["subs"]
    finish = max((datetime.combine(s.date, s.end) for s in result["assignment"].values()), default=None)
    finish_epoch = finish.timestamp() if finish else 0.0
    if objective == "min_days":
        return (-days, count, -subs, -finish_epoch)
    return (count, -days, -subs, -finish_epoch)


def _plan_id_for(norm: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(norm, sort_keys=True, default=str).encode()).hexdigest()
    return "plan_" + digest[:12]


def optimize_attendance_plan(args: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = args["snapshot_id"]
    home_group = args["home_group"]
    required_courses = sorted(dict.fromkeys(args["required_courses"]))
    objective = args.get("objective", "balanced")
    max_campus_days = args.get("max_campus_days", 3)
    min_coverage_ratio = args.get("min_coverage_ratio", 0.7)
    allow_cross_group = args.get("allow_cross_group", True)
    calendar_path = args.get("calendar_path", "data/calendar.sample.ics")
    min_gap_minutes = args.get("min_gap_minutes", 30)

    snap = store.load_snapshot(snapshot_id)

    home_sessions = [s for s in snap.sessions if s.group == home_group]
    if not home_sessions:
        raise ToolError(
            ErrorCode.INVALID_INPUT,
            f"home_group {home_group!r} has no sessions in snapshot {snapshot_id}",
            details={"snapshot_id": snapshot_id, "home_group": home_group},
        )

    course_set = set(required_courses)
    missing = sorted(c for c in course_set if not any(s.course_code == c for s in home_sessions))
    if missing:
        raise ToolError(
            ErrorCode.INVALID_INPUT,
            f"home_group {home_group!r} has no sessions for required course(s): {missing}",
            details={"missing_courses": missing, "home_group": home_group},
        )

    home_units: dict[UnitKey, Session] = {}
    for s in home_sessions:
        if s.course_code in course_set:
            home_units.setdefault(_unit_key(s), s)
    required_sessions = len(home_units)
    unit_keys = sorted(home_units.keys())

    all_candidates: dict[UnitKey, list[Session]] = {}
    for key, home_s in home_units.items():
        course_code, kind, _topic = key
        cands = [home_s]
        if allow_cross_group:
            for s in snap.sessions:
                if s.group == home_group or s.course_code != course_code or s.kind.value != kind:
                    continue
                if _topic_compatible(s.topic, home_s.topic):
                    cands.append(s)
        all_candidates[key] = cands

    distinct_ids = sorted({s.session_id for cands in all_candidates.values() for s in cands})
    conflict_res = detect_schedule_conflicts({
        "snapshot_id": snapshot_id,
        "session_ids": distinct_ids,
        "calendar_path": calendar_path,
        "min_gap_minutes": min_gap_minutes,
        "include_soft": True,
    })
    calendar_blocked = {
        c["session_id"] for c in conflict_res["data"]["conflicts"]
        if c["kind"] in ("calendar_hard", "travel_infeasible")
    }

    legal_candidates: dict[UnitKey, list[Session]] = {
        key: [s for s in cands if s.session_id not in calendar_blocked]
        for key, cands in all_candidates.items()
    }
    all_dates = sorted({s.date for cands in legal_candidates.values() for s in cands})

    bound = len(all_dates) if objective == "max_coverage" else min(max_campus_days, len(all_dates))

    best_result: dict[str, Any] | None = None
    best_priority: tuple | None = None
    evaluated = 0
    for size in range(1, bound + 1):
        for combo in itertools.combinations(all_dates, size):
            if evaluated >= _MAX_DAY_SETS_EVALUATED:
                break
            evaluated += 1
            result = _solve_for_day_set(unit_keys, legal_candidates, home_units, frozenset(combo))
            prio = _priority_key(objective, result)
            if best_priority is None or prio > best_priority:
                best_priority = prio
                best_result = result

    if best_result is None:
        best_result = {"count": 0, "subs": 0, "assignment": {}, "days_used": []}

    covered = best_result["count"]
    coverage_ratio = covered / required_sessions

    if coverage_ratio < min_coverage_ratio:
        unrestricted = _solve_for_day_set(unit_keys, legal_candidates, home_units, frozenset(all_dates))
        best_possible_ratio = unrestricted["count"] / required_sessions
        binding = "max_campus_days" if best_possible_ratio >= min_coverage_ratio else "min_coverage_ratio"
        raise ToolError(
            ErrorCode.INFEASIBLE,
            f"best achievable coverage is {coverage_ratio:.2f}, below min_coverage_ratio={min_coverage_ratio}",
            details={
                "best_coverage_ratio": coverage_ratio,
                "best_possible_coverage_ratio": best_possible_ratio,
                "binding_constraint": binding,
                "max_campus_days": max_campus_days,
                "min_coverage_ratio": min_coverage_ratio,
            },
        )

    assignment = best_result["assignment"]
    items = [
        PlanItem(
            course_code=s.course_code,
            session_id=s.session_id,
            group=s.group,
            substituted=s.session_id != home_units[key].session_id,
            date=s.date,
            start=s.start,
            end=s.end,
        )
        for key, s in sorted(assignment.items(), key=lambda kv: (kv[1].date, kv[1].start))
    ]
    campus_days = sorted(best_result["days_used"])
    substitutions_used = sum(1 for it in items if it.substituted)

    skipped = []
    for key in unit_keys:
        if key in assignment:
            continue
        reason = "blocked_by_calendar" if not legal_candidates[key] else "excluded_by_day_or_time_budget"
        skipped.append({"session_id": home_units[key].session_id, "reason": reason})

    norm_args = {
        "snapshot_id": snapshot_id, "home_group": home_group, "required_courses": required_courses,
        "objective": objective, "max_campus_days": max_campus_days, "min_coverage_ratio": min_coverage_ratio,
        "allow_cross_group": allow_cross_group, "calendar_path": calendar_path, "min_gap_minutes": min_gap_minutes,
    }
    plan_id = _plan_id_for(norm_args)

    plan = AttendancePlan(
        plan_id=plan_id,
        snapshot_id=snapshot_id,
        objective=objective,
        items=items,
        campus_days=campus_days,
        coverage_ratio=coverage_ratio,
        covered_sessions=covered,
        required_sessions=required_sessions,
        skipped=skipped,
        substitutions_used=substitutions_used,
    )
    store.save_plan(plan)

    return ok(
        {
            "plan_id": plan.plan_id,
            "objective": objective,
            "items": [it.model_dump(mode="json") for it in items],
            "campus_days": [d.isoformat() for d in campus_days],
            "campus_day_count": len(campus_days),
            "coverage_ratio": coverage_ratio,
            "covered_sessions": covered,
            "required_sessions": required_sessions,
            "substitutions_used": substitutions_used,
            "skipped": skipped,
        },
        warnings=[] if not skipped else [f"{len(skipped)} required session(s) could not be covered"],
    )
