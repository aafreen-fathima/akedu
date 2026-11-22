"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root (two levels up from this file: app/ -> backend/ -> project root)
load_dotenv(BASE_DIR.parent / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("AKEDU_DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'akedu.db'}"))
    upload_dir: Path = field(default_factory=lambda: Path(_env("AKEDU_UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))))
    secret_key: str = field(default_factory=lambda: _env("AKEDU_SECRET_KEY", "dev-only-change-me"))
    max_upload_mb: int = field(default_factory=lambda: int(_env("AKEDU_MAX_UPLOAD_MB", "10")))

    # LLM gateway (ADR-02): ollama | openai | heuristic
    llm_provider: str = field(default_factory=lambda: _env("AKEDU_LLM_PROVIDER", "ollama"))
    llm_model: str = field(default_factory=lambda: _env("AKEDU_LLM_MODEL", "llama3.1:8b"))
    llm_base_url: str = field(default_factory=lambda: _env("AKEDU_LLM_BASE_URL", "http://localhost:11434"))
    llm_api_key: str = field(default_factory=lambda: _env("AKEDU_LLM_API_KEY", ""))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("AKEDU_LLM_TIMEOUT_S", "300")))
    llm_num_ctx: int = field(default_factory=lambda: int(_env("AKEDU_LLM_NUM_CTX", "32768")))
    llm_labels: bool = field(default_factory=lambda: _env("AKEDU_LLM_LABELS", "false").lower() == "true")

    # Crunch rule (R6) and planner defaults (ADR-03)
    crunch_window_days: int = 7
    crunch_min_count: int = field(default_factory=lambda: int(_env("AKEDU_CRUNCH_MIN_COUNT", "3")))
    crunch_min_weight: float = field(default_factory=lambda: float(_env("AKEDU_CRUNCH_MIN_WEIGHT", "30")))
    crunch_rule_version: str = "crunch-v1"
    full_day_hours: float = field(default_factory=lambda: float(_env("AKEDU_FULL_DAY_HOURS", "8")))
    max_blocks_per_day: int = field(default_factory=lambda: int(_env("AKEDU_MAX_BLOCKS_PER_DAY", "2")))

    # Term seeded on first start
    term_name: str = field(default_factory=lambda: _env("AKEDU_TERM_NAME", "Fall 2026"))
    term_start: str = field(default_factory=lambda: _env("AKEDU_TERM_START", "2026-09-08"))
    term_end: str = field(default_factory=lambda: _env("AKEDU_TERM_END", "2026-12-22"))
    term_breaks: str = field(default_factory=lambda: _env("AKEDU_TERM_BREAKS", "2026-10-12:2026-10-18"))

    seed_demo: bool = field(default_factory=lambda: _env("AKEDU_SEED_DEMO", "true").lower() == "true")

    # Fixed "today" for demos and tests (YYYY-MM-DD); empty = real date
    today_override: str = field(default_factory=lambda: _env("AKEDU_TODAY", ""))

    def today(self) -> date:
        return date.fromisoformat(self.today_override) if self.today_override else date.today()


settings = Settings()
