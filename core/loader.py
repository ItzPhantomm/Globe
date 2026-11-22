"""
Globe Selfbot — Module Loader
Discovers and loads all cogs from the modules/ directory.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from discord.ext import commands

from ui import log_info, log_warn, log_err


class ModuleLoader:
    """Discovers and loads every cog in Globe/modules/."""

    MODULES_PKG = "modules"
    MODULES_PATH = Path(__file__).parent.parent / "modules"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def load_all(self) -> list[str]:
        """Load all modules; return list of successfully loaded names."""
        loaded: list[str] = []

        for finder, name, _ in pkgutil.iter_modules([str(self.MODULES_PATH)]):
            full = f"{self.MODULES_PKG}.{name}"
            try:
                await self.bot.load_extension(full)
                loaded.append(name)
                log_info(f"Loaded module: {name}")
            except Exception as exc:
                log_err(f"Failed to load module '{name}': {exc}")

        return loaded

    async def reload(self, name: str) -> bool:
        full = f"{self.MODULES_PKG}.{name}"
        try:
            await self.bot.reload_extension(full)
            log_info(f"Reloaded module: {name}")
            return True
        except Exception as exc:
            log_err(f"Failed to reload '{name}': {exc}")
            return False

    async def unload(self, name: str) -> bool:
        full = f"{self.MODULES_PKG}.{name}"
        try:
            await self.bot.unload_extension(full)
            log_info(f"Unloaded module: {name}")
            return True
        except Exception as exc:
            log_err(f"Failed to unload '{name}': {exc}")
            return False
