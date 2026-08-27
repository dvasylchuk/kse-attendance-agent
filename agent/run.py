"""CLI entry point.

    python -m agent.run --home-group BE-3-1 --courses ECON301,STAT210,MGMT150,FIN220
    python -m agent.run --offline           # recorded fixture, no network
    python -m agent.run --discover-only     # just prove both connections work
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from .config import CONFIG
from .mcp_clients import build_client
from .tools_facade import PlaywrightTools, ScheduleTools

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home-group", default="BE-3-1")
    ap.add_argument("--courses", default="ECON301,STAT210,MGMT150,FIN220")
    ap.add_argument("--max-campus-days", type=int, default=3)
    ap.add_argument("--min-coverage", type=float, default=0.75)
    ap.add_argument("--previous-plan-id", default=None)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--discover-only", action="store_true")
    args = ap.parse_args()

    if args.offline:
        CONFIG.offline = True

    client = build_client(include_playwright=not CONFIG.offline)
    async with client.session("schedule") as sched_session:
        sched = ScheduleTools(sched_session)
        sched_names = await sched.discover()

        pw_names: list[str] = []
        pw = None
        if not CONFIG.offline:
            async with client.session("playwright") as pw_session:
                pw = PlaywrightTools(pw_session)
                pw_names = await pw.discover()

        if args.discover_only:
            print(json.dumps({"schedule_mcp": sched_names, "playwright_mcp": pw_names}, indent=2))
            return

        # TICKET B4: run the compiled graph here.
        from .graph import build_graph

        graph = build_graph(sched, pw)
        state = await graph.ainvoke({
            "home_group": args.home_group,
            "required_courses": args.courses.split(","),
            "preference": {
                "max_campus_days": args.max_campus_days,
                "min_coverage_ratio": args.min_coverage,
            },
            "previous_plan_id": args.previous_plan_id,
        })
        print(state.get("report") or json.dumps(state, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
