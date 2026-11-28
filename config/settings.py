"""
Globe Selfbot — Configuration & Settings
Plain-dataclass settings loaded from .env — no pydantic required.
Works with any Python 3.10+ environment including Termux.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env on import
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_PATH, override=False)


def _env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)).strip())
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, str(default)).strip().lower()
    return val in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # ── Core ──────────────────────────────────────────────
    discord_token: str = field(default_factory=lambda: _env_str("DISCORD_TOKEN"))
    prefix: str = field(default_factory=lambda: _env_str("PREFIX", "g."))
    owner_id: int = field(default_factory=lambda: _env_int("OWNER_ID", 0))
    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO"))

    # ── Anti-detection ─────────────────────────────────────
    typing_delay_min: int = field(default_factory=lambda: _env_int("TYPING_DELAY_MIN", 300))
    typing_delay_max: int = field(default_factory=lambda: _env_int("TYPING_DELAY_MAX", 1200))

    # ── Behaviour ──────────────────────────────────────────
    auto_delete_delay: int = field(default_factory=lambda: _env_int("AUTO_DELETE_DELAY", 0))
    nitro_sniper: bool = field(default_factory=lambda: _env_bool("NITRO_SNIPER", False))
    afk_message: str = field(
        default_factory=lambda: _env_str("AFK_MESSAGE", "I'm AFK right now.")
    )

    # ── Web Control Plane ──────────────────────────────────
    dashboard_enabled: bool = field(default_factory=lambda: _env_bool("DASHBOARD_ENABLED", True))
    dashboard_host: str = field(default_factory=lambda: _env_str("DASHBOARD_HOST", "127.0.0.1"))
    dashboard_port: int = field(default_factory=lambda: _env_int("DASHBOARD_PORT", 8787))

    # ── Captcha Solver (OpenRouter vision model) ───────────
    openrouter_api_key: str = field(default_factory=lambda: _env_str("OPENROUTER_API_KEY", ""))


# Singleton — import this everywhere
settings = Settings()
