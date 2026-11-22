"""
Globe Selfbot — Main Entry Point
Run with: python main.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# ── Make sure project root is on sys.path ─────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import click
from dotenv import load_dotenv

# Load .env early so Settings picks it up
load_dotenv(ROOT / ".env", override=True)

from auth_handlers import auth
from config import settings
from ui import log_err, log_info, log_warn, banner, console


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.option(
    "--token", "-t",
    default=None,
    help="Discord user token (overrides .env)",
    envvar="DISCORD_TOKEN",
)
@click.option(
    "--prefix", "-p",
    default=None,
    help=f"Command prefix (default: {settings.prefix})",
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    default=False,
    help="Enable debug logging",
)
def main(token: str | None, prefix: str | None, debug: bool) -> None:
    """🌐 Globe — All-in-One Discord Selfbot"""
    if debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Override prefix from CLI
    if prefix:
        settings.prefix = prefix  # type: ignore[attr-defined]

    # Resolve and validate token
    resolved_token = token or auth.load_token()
    if not auth.validate_token(resolved_token):
        log_err("Invalid token. Exiting.")
        sys.exit(1)

    # Kick off the bot
    asyncio.run(_run(resolved_token))


async def _run(token: str) -> None:
    from core.bot import GlobeBot

    bot = GlobeBot()

    try:
        await bot.start(token, reconnect=True)
    except Exception as exc:
        log_err(f"Fatal: {exc}")
        sys.exit(1)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    main()
