"""Tool 5 - OPEN TICKET A5 (Track A).

`compare_attendance_plans` tests the student's stated preference ("no more
than 3 days on campus and I still want 80% coverage") against the plans that
were actually produced, and returns structured evidence rather than prose.

WHAT TO IMPLEMENT:

  1. store.load_plan() for every id; the first is the baseline.
  2. For each non-baseline plan produce a comparison record:
       {plan_id, campus_days_delta, coverage_delta, substitutions_delta,
        satisfies_preference: bool, violated: [constraint names]}
  3. verdict:
       "supported"     - at least one plan satisfies every stated preference
       "contradicted"  - no plan does, and the best achievable value is
                         reported per violated constraint
       "inconclusive"  - the preference object is empty or only partially
                         comparable (e.g. plans built from different snapshots;
                         detect this via plan.snapshot_id and warn)
  4. recommended_plan_id: the satisfying plan with the highest coverage; if
     none satisfies, the plan with the smallest total violation.
  5. rationale: one short sentence built from the numbers, not free-form text.

DEFINITION OF DONE
  * comparing two plans from different snapshot_ids emits a warning and never
    silently compares incomparable numbers;
  * verdict is derived from the numbers only - no LLM involvement inside the
    tool;
  * tests cover supported / contradicted / inconclusive.
"""

from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, ToolError


def compare_attendance_plans(args: dict[str, Any]) -> dict[str, Any]:
    raise ToolError(
        ErrorCode.NOT_IMPLEMENTED,
        "compare_attendance_plans is not implemented yet (ticket A5)",
        details={"ticket": "A5", "contract": "docs/03-tool-contracts.md#compare_attendance_plans"},
    )
