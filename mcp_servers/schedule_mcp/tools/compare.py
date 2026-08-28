"""Tool 5 (ticket A5 - implemented).

`compare_attendance_plans` tests the student's stated preference ("no more
than 3 days on campus and I still want 80% coverage") against the plans that
were actually produced, and returns structured evidence rather than prose.
The verdict is derived purely from the numbers - no LLM involvement here.
"""

from __future__ import annotations

from typing import Any

from ..domain import store
from ..domain.models import AttendancePlan
from ..errors import ok

_CONSTRAINT_CHECKS = {
    "max_campus_days": lambda plan, bound: len(plan.campus_days) <= bound,
    "min_coverage_ratio": lambda plan, bound: plan.coverage_ratio >= bound,
    "max_substitutions": lambda plan, bound: plan.substitutions_used <= bound,
}


def _violated(plan: AttendancePlan, preference: dict[str, Any]) -> list[str]:
    return [
        name for name, bound in preference.items()
        if name in _CONSTRAINT_CHECKS and not _CONSTRAINT_CHECKS[name](plan, bound)
    ]


def _comparison(plan: AttendancePlan, baseline: AttendancePlan, preference: dict[str, Any]) -> dict[str, Any]:
    violated = _violated(plan, preference)
    return {
        "plan_id": plan.plan_id,
        "campus_days_delta": len(plan.campus_days) - len(baseline.campus_days),
        "coverage_delta": plan.coverage_ratio - baseline.coverage_ratio,
        "substitutions_delta": plan.substitutions_used - baseline.substitutions_used,
        "satisfies_preference": not violated,
        "violated": violated,
    }


def compare_attendance_plans(args: dict[str, Any]) -> dict[str, Any]:
    plan_ids: list[str] = args["plan_ids"]
    preference: dict[str, Any] = args.get("preference") or {}

    plans = [store.load_plan(pid) for pid in plan_ids]
    baseline = plans[0]

    mismatched = sorted({p.plan_id for p in plans if p.snapshot_id != baseline.snapshot_id})
    warnings: list[str] = []
    if mismatched:
        warnings.append(
            f"plans built from different snapshots than the baseline ({baseline.plan_id}): "
            f"{mismatched}; deltas across them are not directly comparable"
        )

    comparisons = [_comparison(p, baseline, preference) for p in plans[1:]]

    # Baseline participates in "which plan is best" scoring even though it is
    # not itself listed in `comparisons` (the contract only asks for
    # non-baseline records there).
    violated_by_id = {baseline.plan_id: _violated(baseline, preference)}
    violated_by_id.update({c["plan_id"]: c["violated"] for c in comparisons})
    plans_by_id = {p.plan_id: p for p in plans}

    if not preference:
        verdict = "inconclusive"
        warnings.append("no preference was given to test the plans against")
        recommended = max(plans, key=lambda p: (p.coverage_ratio, -len(p.campus_days))).plan_id
        rationale = "No preference was given, so no plan can be judged supported or contradicted."
    else:
        satisfying = [pid for pid, v in violated_by_id.items() if not v]
        if mismatched:
            verdict = "inconclusive"
        elif satisfying:
            verdict = "supported"
        else:
            verdict = "contradicted"

        if satisfying:
            recommended = max(
                satisfying,
                key=lambda pid: (plans_by_id[pid].coverage_ratio, -len(plans_by_id[pid].campus_days)),
            )
            plan = plans_by_id[recommended]
            rationale = (
                f"{recommended} satisfies the preference with "
                f"{plan.coverage_ratio:.0%} coverage on {len(plan.campus_days)} campus day(s)."
            )
        else:
            recommended = min(
                violated_by_id,
                key=lambda pid: (
                    len(violated_by_id[pid]),
                    -plans_by_id[pid].coverage_ratio,
                    len(plans_by_id[pid].campus_days),
                ),
            )
            rationale = (
                f"No plan satisfies the preference; {recommended} comes closest, "
                f"violating {violated_by_id[recommended]}."
            )
        if mismatched:
            rationale += " Snapshots differ across the compared plans, so this is not conclusive."

    return ok(
        {
            "baseline_plan_id": baseline.plan_id,
            "comparisons": comparisons,
            "recommended_plan_id": recommended,
            "verdict": verdict,
            "rationale": rationale,
        },
        warnings=warnings,
    )
