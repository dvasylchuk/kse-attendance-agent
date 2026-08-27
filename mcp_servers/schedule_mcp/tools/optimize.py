"""Tool 4 - OPEN TICKET A4 (Track A). The core of the project.

`optimize_attendance_plan` picks, for every required course, which group's
session to attend, so that the student covers as much as possible in as few
campus days as possible without colliding with their calendar.

WHAT TO IMPLEMENT:

  1. Load the snapshot. Split its sessions into:
       home     = sessions of home_group for a required course
       variants = sessions of ANY group for the same course_code where
                  substitution is legal: same course_code AND
                  (topic equal, or either topic is None).
     required_sessions = number of DISTINCT (course_code, kind, topic) units
     that the home group has for the required courses. That, not the raw
     session count, is the coverage denominator.
  2. Drop every candidate that detect_schedule_conflicts marks blocked. Reuse
     that function - do not re-implement the overlap maths.
  3. Search. The instance is small (< ~200 candidates), so an exact search is
     realistic and preferable to a heuristic:
       - enumerate subsets of campus days up to max_campus_days
         (C(6,3) = 20 combinations for the default), and for each day set take
         the best legal assignment; OR
       - formulate as ILP if you prefer (pulp is not currently a dependency).
     Tie-breaks, in order: higher coverage, fewer campus days, fewer
     substitutions, earlier finish time.
  4. Objectives:
       min_days     -> minimise campus days first, coverage second
       max_coverage -> maximise coverage first, ignore max_campus_days
       balanced     -> maximise coverage subject to campus_days <= max_campus_days
  5. If the best plan's coverage_ratio < min_coverage_ratio, raise
     ToolError(INFEASIBLE) whose details carry the best achievable ratio and
     the binding constraint. This is a FAILURE, not an empty success - the
     agent is supposed to relax a constraint and retry.
  6. Persist with store.save_plan() and return the plan_id.

DEFINITION OF DONE
  * a plan that reduces campus days versus the home-group baseline on the
    demo dataset;
  * every skipped required session carries a machine-readable reason;
  * INFEASIBLE is reachable by tightening max_campus_days to 1;
  * tests/test_optimizer.py asserts determinism: same input -> same plan_id.
"""

from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, ToolError


def optimize_attendance_plan(args: dict[str, Any]) -> dict[str, Any]:
    raise ToolError(
        ErrorCode.NOT_IMPLEMENTED,
        "optimize_attendance_plan is not implemented yet (ticket A4)",
        details={"ticket": "A4", "contract": "docs/03-tool-contracts.md#optimize_attendance_plan"},
    )
