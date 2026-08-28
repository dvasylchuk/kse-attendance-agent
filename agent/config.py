"""Agent configuration. Everything environment-specific comes from .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    openrouter_api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    model: str = field(default_factory=lambda: os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"))

    schedule_url: str = field(default_factory=lambda: os.environ.get("SCHEDULE_URL", ""))
    table_selector: str = field(
        default_factory=lambda: os.environ.get("SCHEDULE_TABLE_SELECTOR", "table.schedule")
    )

    offline: bool = field(default_factory=lambda: _bool("OFFLINE_MODE"))
    fixture_v1: Path = ROOT / "fixtures/playwright/schedule_page_v1.html"
    fixture_v2: Path = ROOT / "fixtures/playwright/schedule_page_v2.html"

    calendar_path: str = "data/calendar.sample.ics"
    student_path: Path = ROOT / "data/student.sample.json"

    scrape_min_interval_sec: float = field(
        default_factory=lambda: float(os.environ.get("SCRAPE_MIN_INTERVAL_SEC", "3"))
    )
    # How long capture_timetable waits for SCHEDULE_TABLE_SELECTOR to appear
    # before raising SelectorNeverAppearedError: (attempts - 1) * interval
    # seconds, since no wait follows the last attempt. Configurable because a
    # client-rendered page (e.g. schedule.kse.ua after a discipline search)
    # can take longer than a static fixture ever would.
    selector_poll_attempts: int = field(
        default_factory=lambda: int(os.environ.get("SELECTOR_POLL_ATTEMPTS", "10"))
    )
    selector_poll_interval_sec: float = field(
        default_factory=lambda: float(os.environ.get("SELECTOR_POLL_INTERVAL_SEC", "2"))
    )

    def require_llm(self) -> None:
        if not self.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in."
            )


CONFIG = Config()
