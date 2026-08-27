"""On-disk store for timetable snapshots and produced plans.

Snapshots are append-only and versioned: the timetable at the university
changes during the term, so a plan is only valid relative to the snapshot it
was built from. `detect_timetable_changes` diffs two snapshots and tells the
agent whether an existing plan is still valid.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..errors import ErrorCode, ToolError
from .models import AttendancePlan, TimetableSnapshot


def state_dir() -> Path:
    d = Path(os.environ.get("SCHEDULE_MCP_STATE_DIR", "./.state"))
    (d / "snapshots").mkdir(parents=True, exist_ok=True)
    (d / "plans").mkdir(parents=True, exist_ok=True)
    return d


def save_snapshot(snap: TimetableSnapshot) -> Path:
    path = state_dir() / "snapshots" / f"{snap.snapshot_id}.json"
    path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    _append_index("snapshots", {
        "snapshot_id": snap.snapshot_id,
        "captured_at": snap.captured_at.isoformat(),
        "source": snap.source,
        "source_ref": snap.source_ref,
        "sessions": len(snap.sessions),
    })
    return path


def load_snapshot(snapshot_id: str) -> TimetableSnapshot:
    path = state_dir() / "snapshots" / f"{snapshot_id}.json"
    if not path.exists():
        raise ToolError(
            ErrorCode.SNAPSHOT_NOT_FOUND,
            f"no snapshot {snapshot_id}; call ingest_timetable_snapshot first",
            details={"snapshot_id": snapshot_id, "known": list_snapshot_ids()[:10]},
        )
    return TimetableSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def list_snapshot_ids() -> list[str]:
    return sorted(p.stem for p in (state_dir() / "snapshots").glob("*.json"))


def latest_snapshot_id(exclude: str | None = None) -> str | None:
    entries = [e for e in _read_index("snapshots") if e["snapshot_id"] != exclude]
    if not entries:
        return None
    return max(entries, key=lambda e: e["captured_at"])["snapshot_id"]


def save_plan(plan: AttendancePlan) -> Path:
    path = state_dir() / "plans" / f"{plan.plan_id}.json"
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_plan(plan_id: str) -> AttendancePlan:
    path = state_dir() / "plans" / f"{plan_id}.json"
    if not path.exists():
        raise ToolError(
            ErrorCode.PLAN_NOT_FOUND,
            f"no plan {plan_id}",
            details={"plan_id": plan_id, "known": sorted(p.stem for p in path.parent.glob('*.json'))[:10]},
        )
    return AttendancePlan.model_validate_json(path.read_text(encoding="utf-8"))


def _index_path(name: str) -> Path:
    return state_dir() / f"{name}.index.jsonl"


def _append_index(name: str, entry: dict[str, Any]) -> None:
    with _index_path(name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_index(name: str) -> list[dict[str, Any]]:
    p = _index_path(name)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out
