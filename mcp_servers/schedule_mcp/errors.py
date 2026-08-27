"""Error taxonomy for the Schedule MCP server.

Rubric requirement (Part B): "return errors in a form that lets the caller
distinguish failure from a successful empty result."

Contract:
  * SUCCESS  -> {"ok": true,  "data": {...}, "warnings": [...]}
  * FAILURE  -> {"ok": false, "error": {"code": "...", "message": "...",
                                        "details": {...}, "retryable": bool}}

An empty result is a SUCCESS with an empty collection inside `data`, plus an
explicit counter (e.g. {"conflicts": [], "conflict_count": 0}). It is never
signalled by an error, and never by an empty payload.
"""

from __future__ import annotations

from typing import Any


class ErrorCode:
    """Stable, model-facing error codes. Do not rename without a doc update."""

    INVALID_INPUT = "INVALID_INPUT"          # schema-valid but domain-invalid arguments
    PARSE_FAILED = "PARSE_FAILED"            # timetable markup could not be parsed
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
    DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"   # dataset file missing/unreadable
    INFEASIBLE = "INFEASIBLE"                # constraints admit no valid plan
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"      # stub still open as a ticket
    INTERNAL = "INTERNAL"


class ToolError(Exception):
    """Raised inside a tool; converted into the FAILURE envelope by the server."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "retryable": self.retryable,
            },
        }


def ok(data: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    """Build the SUCCESS envelope."""
    return {"ok": True, "data": data, "warnings": warnings or []}
