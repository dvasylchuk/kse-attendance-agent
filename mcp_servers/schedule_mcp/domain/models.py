"""Canonical domain model of the attendance-planning domain.

These pydantic models are the single source of truth for every MCP tool
schema: `model_json_schema()` output is what the model sees over MCP, so the
field descriptions and constraints here ARE the model-facing contract.
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT"]


class SessionKind(str, Enum):
    LECTURE = "lecture"
    SEMINAR = "seminar"
    LAB = "lab"
    EXAM = "exam"


class Modality(str, Enum):
    ONSITE = "onsite"
    ONLINE = "online"
    HYBRID = "hybrid"


class Session(BaseModel):
    """One timetabled class of one group."""

    session_id: str = Field(description="Stable id, format: <course_code>-<group>-<iso_date>-<start>")
    course_code: str = Field(min_length=2, max_length=32, description="e.g. 'ECON301'")
    course_title: str = Field(min_length=1, max_length=200)
    group: str = Field(min_length=1, max_length=32, description="Study group label, e.g. 'BE-3-1'")
    kind: SessionKind
    modality: Modality = Modality.ONSITE
    date: date
    start: time
    end: time
    room: str | None = Field(default=None, max_length=64)
    teacher: str | None = Field(default=None, max_length=120)
    topic: str | None = Field(
        default=None,
        max_length=200,
        description="Topic label. Cross-group substitution is only allowed between "
        "sessions of the same course_code AND the same topic (or empty topic).",
    )

    @model_validator(mode="after")
    def _end_after_start(self) -> Session:
        if self.end <= self.start:
            raise ValueError(f"session {self.session_id}: end {self.end} <= start {self.start}")
        return self

    @property
    def weekday(self) -> str:
        return ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][self.date.weekday()]

    def minutes(self) -> int:
        return (self.end.hour * 60 + self.end.minute) - (self.start.hour * 60 + self.start.minute)


class BusyBlock(BaseModel):
    """A block of personal time the student cannot give up (job, commute, gym)."""

    block_id: str
    title: str = Field(max_length=200)
    start: datetime
    end: datetime
    hard: bool = Field(
        default=True,
        description="hard=true blocks attendance outright; hard=false only costs a penalty.",
    )

    @model_validator(mode="after")
    def _end_after_start(self) -> BusyBlock:
        if self.end <= self.start:
            raise ValueError(f"busy block {self.block_id}: end <= start")
        return self


class TimetableSnapshot(BaseModel):
    """An immutable, versioned parse of the university timetable."""

    snapshot_id: str
    source: Literal["playwright", "fixture", "local_dataset"]
    source_ref: str = Field(description="URL or file path the snapshot was built from")
    captured_at: datetime
    date_from: date
    date_to: date
    sessions: list[Session]

    def groups(self) -> list[str]:
        return sorted({s.group for s in self.sessions})

    def courses(self) -> list[str]:
        return sorted({s.course_code for s in self.sessions})


class ConflictKind(str, Enum):
    CALENDAR_HARD = "calendar_hard"
    CALENDAR_SOFT = "calendar_soft"
    SESSION_OVERLAP = "session_overlap"
    TRAVEL_INFEASIBLE = "travel_infeasible"


class Conflict(BaseModel):
    kind: ConflictKind
    session_id: str
    against: str = Field(description="block_id or the other session_id")
    overlap_minutes: int = Field(ge=0)
    explanation: str


class PlanItem(BaseModel):
    course_code: str
    session_id: str
    group: str
    substituted: bool = Field(description="True when this is not the student's home group")
    date: date
    start: time
    end: time


class AttendancePlan(BaseModel):
    plan_id: str
    snapshot_id: str
    objective: Literal["min_days", "max_coverage", "balanced"]
    items: list[PlanItem]
    campus_days: list[date]
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    covered_sessions: int
    required_sessions: int
    skipped: list[dict] = Field(default_factory=list, description="{session_id, reason}")
    substitutions_used: int
