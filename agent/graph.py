"""LangGraph flow: the tool results decide what happens next.

    capture_page ──► ingest ──► detect_changes ──┬─(no plan yet / replan)─► conflicts ──► optimize ──► compare ──► report
                        ▲                        └─(plan still valid)──────────────────────────────────────────► report
                        │
                 (retry from fixture on Playwright failure)

Two places where a tool result genuinely drives control flow:
  * `capture_page` failing (unreachable page, missing selector, browser start
    failure) routes to the recorded-fixture branch and marks the run degraded;
  * `detect_timetable_changes.replan_required` decides whether the whole
    optimisation stage runs at all.

OPEN TICKETS on this file: B3 (nodes), B4 (routing), B5 (failure paths).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import CONFIG
from .tools_facade import PlaywrightTools, ScheduleTools


class RunState(TypedDict, total=False):
    # inputs
    home_group: str
    required_courses: list[str]
    preference: dict[str, Any]
    previous_plan_id: str | None
    # produced by the flow
    raw_html: str
    capture_source: Literal["playwright", "fixture"]
    degraded_reason: str | None
    snapshot_id: str
    changes: dict[str, Any]
    replan_required: bool
    conflicts: dict[str, Any]
    baseline_plan_id: str
    optimized_plan_id: str
    comparison: dict[str, Any]
    report: str
    errors: Annotated[list[dict[str, Any]], lambda a, b: (a or []) + (b or [])]


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
async def capture_page(state: RunState, pw: PlaywrightTools) -> dict[str, Any]:
    """Existing MCP server in the flow: navigate + snapshot the public page.

    A failure here is not fatal - it degrades the run to the recorded fixture
    and records why, which is exactly the failure scenario shown at the defence.
    """
    if CONFIG.offline:
        return {
            "raw_html": CONFIG.fixture_v1.read_text(encoding="utf-8"),
            "capture_source": "fixture",
            "degraded_reason": "OFFLINE_MODE=true",
        }
    try:
        await asyncio.sleep(CONFIG.scrape_min_interval_sec)  # respect the site
        html = await pw.capture_timetable(CONFIG.schedule_url, CONFIG.table_selector)
        return {"raw_html": html, "capture_source": "playwright", "degraded_reason": None}
    except Exception as exc:  # noqa: BLE001
        return {
            "raw_html": CONFIG.fixture_v1.read_text(encoding="utf-8"),
            "capture_source": "fixture",
            "degraded_reason": f"playwright MCP failed: {type(exc).__name__}: {exc}",
            "errors": [{"stage": "capture_page", "error": str(exc)}],
        }


async def ingest(state: RunState, sched: ScheduleTools) -> dict[str, Any]:
    """TICKET B3a: call ingest_timetable_snapshot with the captured markup."""
    res = await sched.call(
        "ingest_timetable_snapshot",
        {
            "source": "playwright_html" if state["capture_source"] == "playwright" else "fixture_html",
            **({"raw_html": state["raw_html"]} if state["capture_source"] == "playwright"
               else {"path": str(CONFIG.fixture_v1.relative_to(CONFIG.fixture_v1.parents[2]))}),
            "table_selector": CONFIG.table_selector,
            "source_ref": CONFIG.schedule_url or str(CONFIG.fixture_v1),
        },
    )
    if not res["ok"]:
        return {"errors": [{"stage": "ingest", **res["error"]}]}
    return {"snapshot_id": res["data"]["snapshot_id"]}


async def detect_changes(state: RunState, sched: ScheduleTools) -> dict[str, Any]:
    """TICKET B3b: diff against the previous snapshot; decide whether to replan."""
    args: dict[str, Any] = {"new_snapshot_id": state["snapshot_id"]}
    if state.get("previous_plan_id"):
        args["plan_id"] = state["previous_plan_id"]
    res = await sched.call("detect_timetable_changes", args)
    if not res["ok"]:
        return {"errors": [{"stage": "detect_changes", **res["error"]}], "replan_required": True}
    data = res["data"]
    impact = data.get("plan_impact") or {}
    return {
        "changes": data,
        "replan_required": bool(impact.get("replan_required", True)) or not state.get("previous_plan_id"),
    }


async def conflicts(state: RunState, sched: ScheduleTools) -> dict[str, Any]:
    """TICKET B3c: baseline conflict set for the student's own group."""
    raise NotImplementedError("ticket B3c")


async def optimize(state: RunState, sched: ScheduleTools) -> dict[str, Any]:
    """TICKET B3d: build a home-group baseline plan and an optimised plan.

    On INFEASIBLE, relax `max_campus_days` by one and retry at most twice, then
    report the binding constraint instead of failing the run.
    """
    raise NotImplementedError("ticket B3d")


async def compare(state: RunState, sched: ScheduleTools) -> dict[str, Any]:
    """TICKET B3e: compare baseline vs optimised against the stated preference."""
    raise NotImplementedError("ticket B3e")


async def report(state: RunState) -> dict[str, Any]:
    """TICKET B6: render the final answer with the LLM from the structured data.

    The LLM only phrases what the tools computed. Every number in the report
    must be traceable to a tool result in `state` - no arithmetic in the prompt.
    """
    raise NotImplementedError("ticket B6")


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route_after_changes(state: RunState) -> str:
    return "conflicts" if state.get("replan_required") else "report"


def build_graph(sched: ScheduleTools, pw: PlaywrightTools):
    """TICKET B4: assemble and compile the graph."""
    g = StateGraph(RunState)
    g.add_node("capture_page", lambda s: capture_page(s, pw))
    g.add_node("ingest", lambda s: ingest(s, sched))
    g.add_node("detect_changes", lambda s: detect_changes(s, sched))
    g.add_node("conflicts", lambda s: conflicts(s, sched))
    g.add_node("optimize", lambda s: optimize(s, sched))
    g.add_node("compare", lambda s: compare(s, sched))
    g.add_node("report", report)

    g.add_edge(START, "capture_page")
    g.add_edge("capture_page", "ingest")
    g.add_edge("ingest", "detect_changes")
    g.add_conditional_edges("detect_changes", route_after_changes,
                            {"conflicts": "conflicts", "report": "report"})
    g.add_edge("conflicts", "optimize")
    g.add_edge("optimize", "compare")
    g.add_edge("compare", "report")
    g.add_edge("report", END)
    return g.compile()
