"""Flip `status:blocked` -> `status:ready` once a ticket's dependencies close.

Run by .github/workflows/unblock.yml on every issue close. Ticket ids are
matched by the `[A3]` prefix in the issue title, so the board stays in sync
with scripts/tickets.json without any manual bookkeeping.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

REPO = os.environ["REPO"]
ROOT = Path(__file__).resolve().parents[1]


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    spec = json.loads((ROOT / "scripts/tickets.json").read_text(encoding="utf-8"))
    deps = {t["id"]: t.get("deps", []) for t in spec["tickets"]}

    issues = json.loads(gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "200",
                           "--json", "number,title,state,labels"))
    by_id: dict[str, dict] = {}
    for it in issues:
        m = re.match(r"\[([A-D]\d+)\]", it["title"])
        if m:
            by_id[m.group(1)] = it

    for tid, issue in by_id.items():
        if issue["state"] != "OPEN":
            continue
        labels = {lbl["name"] for lbl in issue["labels"]}
        if "status:blocked" not in labels:
            continue
        blockers = [d for d in deps.get(tid, [])
                    if d in by_id and by_id[d]["state"] == "OPEN"]
        if blockers:
            continue
        num = str(issue["number"])
        gh("issue", "edit", num, "--repo", REPO,
           "--remove-label", "status:blocked", "--add-label", "status:ready")
        gh("issue", "comment", num, "--repo", REPO,
           "--body", f"All dependencies of `{tid}` are closed. This ticket is now **ready** - "
                     f"comment `/take` to claim it.")
        print(f"unblocked {tid} (#{num})")


if __name__ == "__main__":
    main()
