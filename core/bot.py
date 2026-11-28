"""
Globe Selfbot — Core Bot Class
Built on discord.py-self with prefix 'g.'
"""

from __future__ import annotations

import asyncio
import re
import sys
import traceback
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from config import settings
from ui import log_info, log_warn, log_err, log_event, log_cmd

_INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite|discordapp\.com/invite)/([A-Za-z0-9-]+)", re.IGNORECASE)

if TYPE_CHECKING:
    pass


class GlobeBot(commands.Bot):
    """
    Central bot class.
    - Self-account (user token) mode via discord.py-self
    - Prefix: g.
    - Modular cog system
    - discord.py-self has NO intents — selfbots receive all events by default
    """

    def __init__(self) -> None:
        # discord.py-self: NO Intents class — selfbots get all events automatically.
        # Valid kwargs flow through Bot → Client → ConnectionState.
        super().__init__(
            command_prefix=settings.prefix,
            self_bot=True,           # discord.py-self: respond only to own messages
            help_command=None,       # We provide our own g.help
            strip_after_prefix=True,
            # max_messages controls the internal message cache size
            max_messages=500,
        )

        self.owner_id: int = settings.owner_id
        self._start_time: float | None = None
        self._loaded_modules: list[str] = []
        self._afk_active: bool = False
        self._afk_reason: str = ""
        self._afk_cooldowns: dict[tuple[int, int], float] = {}
        self._afk_pings: list[dict] = []
        # No-prefix state
        self._no_prefix_enabled: bool = False
        self._no_prefix_until: float | None = None  # None = indefinite or monotonic timestamp

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def _async_setup_hook(self) -> None:
        """Called inside login() right after event loop is bound, BEFORE static_login()."""
        await super()._async_setup_hook()
        # Use ThreadedResolver to fix Android / Termux / Linux DNS resolution issues in aiohttp
        import aiohttp
        if self.http.connector is discord.utils.MISSING or getattr(self.http.connector, "closed", False):
            self.http.connector = aiohttp.TCPConnector(limit=0, resolver=aiohttp.ThreadedResolver())

    async def setup_hook(self) -> None:
        """Called once before the bot connects — load all cogs here."""
        from core.loader import ModuleLoader
        loader = ModuleLoader(self)
        self._loaded_modules = await loader.load_all()

    async def on_ready(self) -> None:
        import time
        first_ready = self._start_time is None
        if first_ready:
            self._start_time = time.monotonic()
            self._start_epoch = time.time()

            from ui import print_startup_table, banner
            from auth_handlers import auth

            # Ensure auth._token is synced with bot's token if not set
            token_str = auth.token or getattr(self.http, "token", "") or settings.discord_token
            if not auth.token and token_str:
                auth._token = token_str

            banner()
            print_startup_table(
                token_preview=auth.masked(),
                prefix=settings.prefix,
                owner_id=self.user.id if self.user else 0,
                module_count=len(self._loaded_modules),
            )
            log_event("ready", f"logged in as {self.user} ({self.user.id if self.user else '?'})")
            log_info(f"Loaded modules: {', '.join(self._loaded_modules) or 'none'}")
        else:
            log_event("reconnect", f"gateway resumed as {self.user}")

        # Explicitly initialize and verify Default Globe Rich Presence
        if status_cog := self.get_cog("Status"):
            if hasattr(status_cog, "apply_default_rpc"):
                await status_cog.apply_default_rpc()

    async def close(self) -> None:
        """Flush buffered tracker records before closing gateway connections."""
        try:
            from data.tracker import tracker
            tracker.flush()
        except Exception:
            pass
        await super().close()

    # ── Command logging via listener (discord.py-self has no on_command event) ──

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context) -> None:
        args_str = " ".join(str(a) for a in ctx.args[2:]) if len(ctx.args) > 2 else ""
        log_cmd(
            ctx_name=ctx.author.name,
            cmd=ctx.command.qualified_name,
            args=args_str,
        )

    # ── Error handling ─────────────────────────────────────────────────────────

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        # Let cog error handlers take priority
        if hasattr(ctx.command, "on_error"):
            return
        if cog := ctx.cog:
            if cog.has_error_handler():
                return

        # Unwrap CheckFailure
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown prefixed messages
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.message.delete()
            msg = await ctx.send(
                f"**Missing argument:** `{error.param.name}` — "
                f"use `{settings.prefix}help {ctx.command.qualified_name}` for usage."
            )
            if settings.auto_delete_delay:
                await msg.delete(delay=settings.auto_delete_delay)
            return
        if isinstance(error, commands.BadArgument):
            msg = await ctx.send(f"**Bad argument:** {error}")
            if settings.auto_delete_delay:
                await msg.delete(delay=settings.auto_delete_delay)
            return
        if isinstance(error, commands.CommandOnCooldown):
            msg = await ctx.send(
                f"**Cooldown:** retry in `{error.retry_after:.1f}s`"
            )
            await msg.delete(delay=4)
            return
        if isinstance(error, commands.CheckFailure):
            return  # Owner-only silently dropped

        # Unknown error — log it
        log_err(f"Unhandled error in {ctx.command}: {error}")
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def on_invite_create(self, invite: discord.Invite) -> None:
        """Track server invites created by the active account."""
        try:
            inviter = getattr(invite, "inviter", None)
            if self.user and inviter and inviter.id == self.user.id:
                from data.tracker import tracker
                tracker.record_invite(
                    user_id=self.user.id,
                    guild_id=invite.guild.id if getattr(invite, "guild", None) else 0,
                    code=invite.code,
                    kind="created",
                )
        except Exception:
            pass

    # ── Message handler ────────────────────────────────────────────────────────

    async def on_message(self, message: discord.Message) -> None:
        # Record message statistics in local sqlite tracker safely (only own account or DMs)
        if self.user and (message.author.id == self.user.id or message.guild is None):
            try:
                from data.tracker import tracker
                tracker.record_message(
                    author_id=message.author.id,
                    guild_id=message.guild.id if message.guild else None,
                    channel_id=message.channel.id,
                )
                if message.author.id == self.user.id and message.content:
                    for code in _INVITE_RE.findall(message.content):
                        tracker.record_invite(
                            user_id=self.user.id,
                            guild_id=message.guild.id if message.guild else None,
                            code=code,
                            kind="shared",
                        )
            except Exception:
                pass

        # Broadcast real-time DM messages to active web dashboard chat sessions
        if message.guild is None:
            cb = getattr(self, "_dashboard_broadcast", None)
            if cb:
                try:
                    atts = [
                        {
                            "filename": a.filename,
                            "url": a.url,
                            "content_type": getattr(a, "content_type", "") or "",
                            "is_image": str(getattr(a, "content_type", "") or "").startswith("image/"),
                            "size": getattr(a, "size", 0),
                        }
                        for a in getattr(message, "attachments", [])
                    ]
                    payload = {
                        "type": "dm_message",
                        "data": {
                            "id": str(message.id),
                            "channel_id": str(message.channel.id),
                            "author_id": str(message.author.id),
                            "author": str(message.author),
                            "global_name": getattr(message.author, "global_name", None) or message.author.name,
                            "avatar": str(message.author.display_avatar.url) if getattr(message.author, "display_avatar", None) else "",
                            "is_self": bool(self.user and message.author.id == self.user.id),
                            "content": message.content or "",
                            "ts_ms": int(message.created_at.timestamp() * 1000) if message.created_at else 0,
                            "attachments": atts,
                        },
                    }
                    asyncio.create_task(cb(payload))
                except Exception:
                    pass

        # AFK auto-reply + missed-ping digest (5m per-user/channel cooldown)
        if self._afk_active and self.user and message.author.id != self.user.id:
            is_dm = message.guild is None
            is_mention = message.guild is not None and self.user in message.mentions
            if is_dm or is_mention:
                import time as _time
                now_mono = _time.monotonic()
                cd_key = (message.channel.id, message.author.id)
                last_reply = self._afk_cooldowns.get(cd_key, 0.0)
                where = f"{message.guild.name} #{getattr(message.channel, 'name', 'ch')}" if message.guild else "DM"
                self._afk_pings.append({
                    "author": str(message.author),
                    "where": where,
                    "content": (message.content or "[Attachment/Embed]")[:100],
                    "jump": message.jump_url,
                    "ts": int(_time.time()),
                })
                if len(self._afk_pings) > 50:
                    self._afk_pings = self._afk_pings[-50:]

                if now_mono - last_reply >= 300.0:
                    self._afk_cooldowns[cd_key] = now_mono
                    reason = self._afk_reason or settings.afk_message
                    try:
                        await message.reply(f"💤 **AFK:** {reason}", mention_author=False)
                    except Exception:
                        pass

        # No-prefix handling for selfbot account
        if (
            self._no_prefix_enabled
            and self.user
            and message.author.id == self.user.id
            and not message.content.startswith(settings.prefix)
        ):
            import time
            if self._no_prefix_until and time.monotonic() > self._no_prefix_until:
                self._no_prefix_enabled = False
                self._no_prefix_until = None
            else:
                # Check if first word exactly matches a registered command name or alias
                tokens = message.content.strip().split()
                if tokens:
                    first_token = tokens[0].lower()
                    # Only trigger if the command exists and is isolated as the first word
                    cmd = self.get_command(first_token)
                    if cmd:
                        # Synthetic prefix injection to invoke the command properly
                        message.content = f"{settings.prefix}{message.content}"

        await self.process_commands(message)

    # ── Utilities ──────────────────────────────────────────────────────────────

    @property
    def uptime_seconds(self) -> float:
        import time
        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    def is_owner_id(self, user_id: int) -> bool:
        """Check if a user ID matches the configured owner or the bot's own account."""
        own_id = self.user.id if self.user else None
        return user_id == self.owner_id or (own_id is not None and user_id == own_id)
