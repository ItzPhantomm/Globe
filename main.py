"""
Globe Selfbot — Main Entry Point
Run with: python main.py
"""

from __future__ import annotations

import asyncio
import os
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
    "--key", "-k",
    default=None,
    help="One-time startup key to decrypt vault token (env: GLOBE_KEY)",
    envvar="GLOBE_KEY",
)
@click.option(
    "--encrypt",
    default=None,
    help="Encrypt stored token in .env with the given passphrase and exit",
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    default=False,
    help="Enable debug logging",
)
def main(token: str | None, prefix: str | None, key: str | None, encrypt: str | None, debug: bool) -> None:
    """🌐 Globe — All-in-One Discord Selfbot"""
    if debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Handle one-time token encryption request
    if encrypt:
        try:
            auth.load_token()
            enc = auth.encrypt_current_token(encrypt)
            log_info(f"Token encrypted into .env with AES-256-GCM.\nCiphertext: {enc[:32]}…")
            log_info("Start the bot with: python main.py --key <passphrase> (or export GLOBE_KEY=<passphrase>)")
            sys.exit(0)
        except Exception as e:
            log_err(f"Encryption failed: {e}")
            sys.exit(1)

    # Override prefix from CLI
    if prefix:
        settings.prefix = prefix  # type: ignore[attr-defined]

    # Resolve and validate token (with Vault decryption support)
    resolved_token = auth.load_token(startup_key=key, override_token=token)
    if not auth.validate_token(resolved_token):
        log_err("Invalid token. Exiting.")
        sys.exit(1)

    # Auto-update from GitHub repository on startup
    auto_update_from_github()

    # Kick off the bot
    asyncio.run(_run(resolved_token))


def auto_update_from_github() -> None:
    """Pull latest updates from GitHub repository on bot launch."""
    import subprocess
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        return
    try:
        log_info("Checking GitHub for updates...")
        res = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=8,
            cwd=str(ROOT),
        )
        if res.returncode == 0:
            msg = res.stdout.strip()
            if "Already up to date" in msg:
                log_info("Globe is up to date.")
            else:
                first_line = msg.splitlines()[0] if msg else "Updated."
                log_info(f"Auto-updater: {first_line}")
        else:
            log_warn(f"Auto-update check bypassed: {res.stderr.strip()[:60]}")
    except Exception as e:
        log_warn(f"Auto-update check skipped: {e}")


async def _run(token: str) -> None:
    from core.bot import GlobeBot

    bot = GlobeBot()
    dashboard = None

    # Clear stale env override before restart loops if .env holds switched token
    if token:
        os.environ["DISCORD_TOKEN"] = token

    if settings.dashboard_enabled:
        try:
            from web.server import DashboardServer
            dashboard = DashboardServer(bot=bot, token_provider=lambda: auth.token or token)
            await dashboard.start()
        except Exception as exc:
            log_warn(f"Web Control Plane failed to start: {exc}")
            dashboard = None

    try:
        await bot.start(token, reconnect=True)
    except Exception as exc:
        log_err(f"Fatal: {exc}")
        sys.exit(1)
    finally:
        if dashboard is not None:
            await dashboard.stop()
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    main()
