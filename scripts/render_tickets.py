"""Render scripts/tickets.json into docs/TICKETS.md (the offline mirror of the board)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKS = {
    "track:A-server": "Track A - custom MCP server",
    "track:B-agent": "Track B - agent and Playwright MCP",
    "track:C-docs": "Track C - documentation, fixtures, ops",
    "track:D-integration": "Track D - integration and defence",
}


def main() -> None:
    spec = json.loads((ROOT / "scripts/tickets.json").read_text(encoding="utf-8"))
    out = [
        "# Ticket board (mirror of scripts/tickets.json)",
        "",
        "The live board is GitHub Issues. This file is the offline copy so the plan is",
        "readable in the repository. Regenerate with `python scripts/render_tickets.py`.",
        "",
        "Status is not tracked here - GitHub labels are the source of truth:",
        "`status:ready`, `status:in-progress`, `status:review`, `status:blocked`.",
        "",
    ]
    for label, heading in TRACKS.items():
        rows = [t for t in spec["tickets"] if t["track"] == label]
        if not rows:
            continue
        out += [f"## {heading}", "", "| Id | Ticket | Depends on | Milestone |", "|---|---|---|---|"]
        for t in rows:
            deps = ", ".join(t.get("deps", [])) or "-"
            done = " ✅" if t.get("state") == "closed" else ""
            title = t["title"].split("] ", 1)[-1]
            out.append(f"| `{t['id']}` | {title}{done} | {deps} | {t['milestone']} |")
        out.append("")
    (ROOT / "docs/TICKETS.md").write_text("\n".join(out), encoding="utf-8")
    print(f"docs/TICKETS.md: {len(spec['tickets'])} tickets")


if __name__ == "__main__":
    main()
