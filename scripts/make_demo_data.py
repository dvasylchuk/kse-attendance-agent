"""Regenerate the deterministic demo dataset and the recorded page fixtures.

The two fixtures differ by exactly one moved class and one added class, so the
`detect_timetable_changes` demo is reproducible.
Run:  python scripts/make_demo_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COURSES = {
    "ECON301": "Intermediate Macroeconomics",
    "STAT210": "Applied Statistics",
    "MGMT150": "Organisational Behaviour",
    "FIN220": "Corporate Finance",
}

# (date, time_range, course, group, kind, room, teacher, topic)
BASE = [
    ("2026-09-07", "09:00-10:20", "ECON301", "BE-3-1", "lecture", "A-201", "Milovanov T.", "IS-LM"),
    ("2026-09-07", "10:40-12:00", "STAT210", "BE-3-1", "seminar", "B-105", "Brik T.", "Regression I"),
    ("2026-09-07", "14:00-15:20", "MGMT150", "BE-3-2", "seminar", "A-110", "Shapoval N.", "Teams"),
    ("2026-09-08", "09:00-10:20", "FIN220",  "BE-3-1", "lecture", "A-201", "Bilousova O.", "WACC"),
    ("2026-09-08", "12:20-13:40", "MGMT150", "BE-3-1", "seminar", "A-110", "Shapoval N.", "Teams"),
    ("2026-09-09", "09:00-10:20", "ECON301", "BE-3-2", "lecture", "A-201", "Milovanov T.", "IS-LM"),
    ("2026-09-09", "10:40-12:00", "STAT210", "BE-3-2", "seminar", "B-105", "Brik T.", "Regression I"),
    ("2026-09-09", "14:00-15:20", "FIN220",  "BE-3-2", "lecture", "A-201", "Bilousova O.", "WACC"),
    ("2026-09-10", "09:00-10:20", "ECON301", "BE-3-3", "lecture", "A-202", "Milovanov T.", "IS-LM"),
    ("2026-09-10", "10:40-12:00", "MGMT150", "BE-3-3", "seminar", "A-110", "Shapoval N.", "Teams"),
    ("2026-09-10", "12:20-13:40", "STAT210", "BE-3-3", "seminar", "B-105", "Brik T.", "Regression I"),
    ("2026-09-11", "09:00-10:20", "FIN220",  "BE-3-3", "lecture", "A-201", "Bilousova O.", "WACC"),
    ("2026-09-11", "14:00-15:20", "ECON301", "BE-3-1", "seminar", "A-203", "Milovanov T.", "IS-LM app"),
    ("2026-09-12", "10:40-12:00", "ECON301", "BE-3-2", "seminar", "A-203", "Milovanov T.", "IS-LM app"),
]

# v2 of the page: STAT210/BE-3-2 moved to another day, one new ECON301 seminar appears.
CHANGED = [r for r in BASE if not (r[2] == "STAT210" and r[3] == "BE-3-2")] + [
    ("2026-09-11", "10:40-12:00", "STAT210", "BE-3-2", "seminar", "B-107", "Brik T.", "Regression I"),
    ("2026-09-12", "14:00-15:20", "ECON301", "BE-3-3", "seminar", "A-203", "Milovanov T.", "IS-LM app"),
]

HEADERS = ["date", "time_range", "course_code", "course_title", "group", "kind", "room", "teacher", "topic"]


def rows(data):
    for d, tr, code, group, kind, room, teacher, topic in sorted(data):
        yield [d, tr, code, COURSES[code], group, kind, room, teacher, topic]


def to_html(data, title):
    head = "".join(f"<th>{h}</th>" for h in HEADERS)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows(data))
    return (
        "<!doctype html><html lang=\"uk\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1>"
        "<p class=\"note\">Recorded fixture of the public timetable page. "
        "Captured for offline replay of the defence demo.</p>"
        f"<table class=\"schedule\"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        "</body></html>"
    )


def to_json(data):
    return {"sessions": [dict(zip(HEADERS, r, strict=True)) for r in rows(data)]}


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//kse-attendance-agent//demo//EN
BEGIN:VEVENT
UID:work-mon
SUMMARY:Part-time job shift
DTSTART:20260907T100000
DTEND:20260907T160000
END:VEVENT
BEGIN:VEVENT
UID:work-wed
SUMMARY:Part-time job shift
DTSTART:20260909T130000
DTEND:20260909T180000
END:VEVENT
BEGIN:VEVENT
UID:gym-fri
SUMMARY:Gym (optional)
TRANSP:TRANSPARENT
DTSTART:20260911T090000
DTEND:20260911T103000
END:VEVENT
BEGIN:VEVENT
UID:family-sat
SUMMARY:Family lunch
DTSTART:20260912T120000
DTEND:20260912T150000
END:VEVENT
END:VCALENDAR
"""

STUDENT = {
    "student_id": "demo-student",
    "home_group": "BE-3-1",
    "required_courses": ["ECON301", "STAT210", "MGMT150", "FIN220"],
    "preference": {"max_campus_days": 3, "min_coverage_ratio": 0.75, "max_substitutions": 4},
}


def main() -> None:
    (ROOT / "fixtures" / "playwright").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    (ROOT / "fixtures/playwright/schedule_page_v1.html").write_text(
        to_html(BASE, "Timetable - week 2026-09-07 (v1)"), encoding="utf-8")
    (ROOT / "fixtures/playwright/schedule_page_v2.html").write_text(
        to_html(CHANGED, "Timetable - week 2026-09-07 (v2, edited by the university)"),
        encoding="utf-8")
    (ROOT / "fixtures/playwright/schedule_page_broken.html").write_text(
        "<!doctype html><html><body><h1>503 Service Unavailable</h1>"
        "<p>The timetable service is temporarily down.</p></body></html>", encoding="utf-8")

    (ROOT / "data/schedule.sample.json").write_text(
        json.dumps(to_json(BASE), ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "data/calendar.sample.ics").write_text(ICS, encoding="utf-8")
    (ROOT / "data/student.sample.json").write_text(
        json.dumps(STUDENT, ensure_ascii=False, indent=2), encoding="utf-8")
    print("demo data regenerated")


if __name__ == "__main__":
    main()
