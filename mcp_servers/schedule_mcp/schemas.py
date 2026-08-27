"""Explicit MCP input/output JSON Schemas.

Kept hand-written (rather than auto-derived) because these ARE the contract the
model reads. Every constraint here is enforced again in the tool body — the
schema guides the model, the body guarantees the invariant.
"""

from __future__ import annotations

ENVELOPE_ERROR = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "enum": [
                "INVALID_INPUT", "PARSE_FAILED", "SNAPSHOT_NOT_FOUND", "PLAN_NOT_FOUND",
                "DATA_SOURCE_UNAVAILABLE", "INFEASIBLE", "NOT_IMPLEMENTED", "INTERNAL",
            ],
        },
        "message": {"type": "string"},
        "details": {"type": "object"},
        "retryable": {"type": "boolean"},
    },
    "required": ["code", "message", "retryable"],
}


def envelope(data_schema: dict) -> dict:
    """Wrap a tool's success payload in the shared ok/error envelope."""
    return {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean", "description": "false means the call failed; an empty "
                                                     "result is ok=true with empty collections"},
            "data": data_schema,
            "warnings": {"type": "array", "items": {"type": "string"}},
            "error": ENVELOPE_ERROR,
        },
        "required": ["ok"],
    }


# --------------------------------------------------------------------------- #
# 1. ingest_timetable_snapshot
# --------------------------------------------------------------------------- #
INGEST_INPUT = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "enum": ["playwright_html", "fixture_html", "local_dataset"],
            "description": "Where the raw timetable comes from. 'playwright_html' = markup just "
                           "captured from the live page; 'fixture_html' = recorded page in "
                           "fixtures/; 'local_dataset' = prepared JSON in data/.",
        },
        "raw_html": {
            "type": "string",
            "maxLength": 4000000,
            "description": "Required when source='playwright_html'. The outerHTML of the "
                           "timetable region captured through Playwright MCP.",
        },
        "path": {
            "type": "string",
            "description": "Required when source is 'fixture_html' or 'local_dataset'. Path "
                           "relative to the repository root.",
        },
        "table_selector": {
            "type": "string",
            "default": "table.schedule",
            "description": "CSS selector of the timetable table inside raw_html.",
        },
        "source_ref": {
            "type": "string",
            "description": "Human-readable origin (page URL or file path) recorded in the "
                           "snapshot for provenance.",
        },
    },
    "required": ["source"],
    "additionalProperties": False,
}

INGEST_OUTPUT = envelope({
    "type": "object",
    "properties": {
        "snapshot_id": {"type": "string"},
        "captured_at": {"type": "string", "format": "date-time"},
        "date_from": {"type": "string", "format": "date"},
        "date_to": {"type": "string", "format": "date"},
        "session_count": {"type": "integer"},
        "groups": {"type": "array", "items": {"type": "string"}},
        "courses": {"type": "array", "items": {"type": "string"}},
        "rejected_rows": {"type": "integer"},
        "is_new_snapshot": {"type": "boolean",
                            "description": "false when an identical snapshot already existed"},
    },
    "required": ["snapshot_id", "session_count", "groups", "courses"],
})


# --------------------------------------------------------------------------- #
# 2. detect_timetable_changes
# --------------------------------------------------------------------------- #
CHANGES_INPUT = {
    "type": "object",
    "properties": {
        "new_snapshot_id": {"type": "string", "description": "The freshly ingested snapshot."},
        "baseline_snapshot_id": {
            "type": "string",
            "description": "Snapshot to compare against. Defaults to the most recent stored "
                           "snapshot other than new_snapshot_id.",
        },
        "plan_id": {
            "type": "string",
            "description": "Optional. When given, the tool also reports which items of that plan "
                           "are invalidated by the change and whether re-planning is required.",
        },
        "courses": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 40,
            "description": "Optional filter: only report changes for these course codes.",
        },
    },
    "required": ["new_snapshot_id"],
    "additionalProperties": False,
}

CHANGES_OUTPUT = envelope({
    "type": "object",
    "properties": {
        "baseline_snapshot_id": {"type": "string"},
        "added": {"type": "array", "items": {"type": "object"}},
        "removed": {"type": "array", "items": {"type": "object"}},
        "moved": {"type": "array", "items": {"type": "object"},
                  "description": "Same course+group+kind, different date/time/room"},
        "change_count": {"type": "integer"},
        "plan_impact": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "invalidated_items": {"type": "array", "items": {"type": "object"}},
                "replan_required": {"type": "boolean"},
            },
        },
    },
    "required": ["added", "removed", "moved", "change_count"],
})


# --------------------------------------------------------------------------- #
# 3. detect_schedule_conflicts
# --------------------------------------------------------------------------- #
CONFLICTS_INPUT = {
    "type": "object",
    "properties": {
        "snapshot_id": {"type": "string"},
        "session_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 500,
            "description": "Candidate sessions to check. Use the sessions of the student's home "
                           "group to obtain the baseline conflict set.",
        },
        "calendar_path": {
            "type": "string",
            "default": "data/calendar.sample.ics",
            "description": "Exported .ics calendar. Local file only; no account access.",
        },
        "min_gap_minutes": {
            "type": "integer", "minimum": 0, "maximum": 240, "default": 30,
            "description": "Travel/settle buffer required between an onsite session and any "
                           "adjacent busy block. Overlap smaller than this is TRAVEL_INFEASIBLE.",
        },
        "include_soft": {"type": "boolean", "default": True},
    },
    "required": ["snapshot_id", "session_ids"],
    "additionalProperties": False,
}

CONFLICTS_OUTPUT = envelope({
    "type": "object",
    "properties": {
        "conflicts": {"type": "array", "items": {"type": "object"}},
        "conflict_count": {"type": "integer"},
        "blocked_session_ids": {"type": "array", "items": {"type": "string"}},
        "checked_sessions": {"type": "integer"},
        "calendar_blocks": {"type": "integer"},
    },
    "required": ["conflicts", "conflict_count", "checked_sessions"],
})


# --------------------------------------------------------------------------- #
# 4. optimize_attendance_plan
# --------------------------------------------------------------------------- #
OPTIMIZE_INPUT = {
    "type": "object",
    "properties": {
        "snapshot_id": {"type": "string"},
        "home_group": {"type": "string", "description": "The student's own group, e.g. 'BE-3-1'."},
        "required_courses": {
            "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 20,
            "description": "Course codes that must be covered.",
        },
        "objective": {
            "type": "string", "enum": ["min_days", "max_coverage", "balanced"], "default": "balanced",
            "description": "min_days = fewest campus days even at the cost of coverage; "
                           "max_coverage = attend as many required sessions as possible; "
                           "balanced = maximise coverage subject to max_campus_days.",
        },
        "max_campus_days": {
            "type": "integer", "minimum": 1, "maximum": 6, "default": 3,
            "description": "Hard cap on distinct on-campus days per week.",
        },
        "min_coverage_ratio": {
            "type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.7,
            "description": "Plan is INFEASIBLE below this share of required sessions.",
        },
        "allow_cross_group": {
            "type": "boolean", "default": True,
            "description": "Allow attending another group's session of the same course. "
                           "Substitution is only legal when course_code matches and topic "
                           "matches (or either topic is empty).",
        },
        "calendar_path": {"type": "string", "default": "data/calendar.sample.ics"},
        "min_gap_minutes": {"type": "integer", "minimum": 0, "maximum": 240, "default": 30},
    },
    "required": ["snapshot_id", "home_group", "required_courses"],
    "additionalProperties": False,
}

OPTIMIZE_OUTPUT = envelope({
    "type": "object",
    "properties": {
        "plan_id": {"type": "string"},
        "objective": {"type": "string"},
        "items": {"type": "array", "items": {"type": "object"}},
        "campus_days": {"type": "array", "items": {"type": "string", "format": "date"}},
        "campus_day_count": {"type": "integer"},
        "coverage_ratio": {"type": "number"},
        "covered_sessions": {"type": "integer"},
        "required_sessions": {"type": "integer"},
        "substitutions_used": {"type": "integer"},
        "skipped": {"type": "array", "items": {"type": "object"},
                    "description": "{session_id, reason} for every uncovered required session"},
    },
    "required": ["plan_id", "items", "campus_days", "coverage_ratio"],
})


# --------------------------------------------------------------------------- #
# 5. compare_attendance_plans
# --------------------------------------------------------------------------- #
COMPARE_INPUT = {
    "type": "object",
    "properties": {
        "plan_ids": {
            "type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 5,
            "description": "Plans to compare. The first one is treated as the baseline.",
        },
        "preference": {
            "type": "object",
            "description": "The student's stated preference, tested against the numbers.",
            "properties": {
                "max_campus_days": {"type": "integer", "minimum": 1, "maximum": 6},
                "min_coverage_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "max_substitutions": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
    },
    "required": ["plan_ids"],
    "additionalProperties": False,
}

COMPARE_OUTPUT = envelope({
    "type": "object",
    "properties": {
        "baseline_plan_id": {"type": "string"},
        "comparisons": {"type": "array", "items": {"type": "object"},
                        "description": "per plan: deltas in campus_days, coverage_ratio, "
                                       "substitutions, plus satisfies_preference"},
        "recommended_plan_id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["supported", "contradicted", "inconclusive"],
                    "description": "Whether the stated preference is achievable in the data."},
        "rationale": {"type": "string"},
    },
    "required": ["baseline_plan_id", "comparisons", "verdict"],
})
