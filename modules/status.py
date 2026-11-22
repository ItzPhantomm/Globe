"""
Globe — Status & Presence Module
Commands: stream, play, listen, watch, stopactivity, setstatus, defaultrpc
Allows custom Rich Presence activity manipulation for selfbot accounts.
Default Globe Rich Presence with profile image, Watching status, elapsed start timer, and interactive buttons.
Synchronizes both Rich Presence Activity and Custom Status to ensure 100% visibility.
"""

from __future__ import annotations

import time
import discord
from discord.ext import commands

from config import settings
from ui import log_info, log_err

# Official Discord Application configuration for Globe
GLOBE_APP_ID = 1574047159374844055
GLOBE_ASSET_ID = "1574047737283092570"
GLOBE_REPO_URL = "https://github.com/ItzPhantomm/Globe"


class CustomRpcActivity(discord.BaseActivity):
    """Direct Discord Gateway compatible activity supporting custom buttons and rich assets."""

    def __init__(self, data: dict) -> None:
        self._data = data
        self.type = discord.ActivityType(data.get("type", 3))

    def to_dict(self) -> dict:
        return self._data


def get_default_globe_activities(user_id: int | None = None, start_time: float | None = None) -> list[discord.BaseActivity]:
    """Build the official default Globe Rich Presence activities list."""
    friend_link = f"https://discord.com/users/{user_id}" if user_id else "https://discord.com"
    start_ms = int((start_time if start_time else time.time()) * 1000)

    # 1. Primary Rich Presence Activity (Watching Globe with elapsed timer and interactive buttons)
    # Uses official Discord Application ID & verified Rich Presence Art Asset Snowflake ID
    rpc_payload = {
        "name": "Globe",
        "type": 3,
        "application_id": GLOBE_APP_ID,
        "details": "Globe",
        "state": "Active. Made by ylemn",
        "timestamps": {"start": start_ms},
        "assets": {
            "large_image": GLOBE_ASSET_ID,
            "large_text": "Globe Selfbot",
        },
        "buttons": ["Use Globe!", "Add Friend"],
        "metadata": {
            "button_urls": [GLOBE_REPO_URL, friend_link],
        },
    }
    primary_act = CustomRpcActivity(rpc_payload)

    # 2. Custom Status Activity (Guarantees public visibility to non-friends, mutual server members, and DMs)
    custom_status = discord.CustomActivity(
        name="Custom Status",
        state="Watching Globe · Made by ylemn",
    )

    return [primary_act, custom_status]


class Status(commands.Cog):
    """Presence and custom activity management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._init_done: bool = False

    async def apply_default_rpc(self) -> bool:
        """Apply official default Globe Rich Presence and verify."""
        try:
            user_id = self.bot.user.id if self.bot.user else None
            start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
            activities = get_default_globe_activities(user_id, start_epoch)
            
            # Send dual presence: rich activity + custom status
            await self.bot.change_presence(activities=activities)
            self._init_done = True
            log_info("Rpc Initialized successful")
            return True
        except Exception as e:
            log_err(f"Rpc initialization failed: {e}")
            return False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Apply default Globe Rich Presence on ready and verify."""
        if not self._init_done:
            await self.apply_default_rpc()

    @commands.command(name="defaultrpc", aliases=["globerpc", "resetrpc"])
    async def defaultrpc(self, ctx: commands.Context) -> None:
        """Reset presence back to default Globe Rich Presence."""
        await ctx.message.delete()
        user_id = self.bot.user.id if self.bot.user else ctx.author.id
        start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
        activities = get_default_globe_activities(user_id, start_epoch)
        await self.bot.change_presence(activities=activities)
        msg = await ctx.send("🌐 Presence reset to official **Globe Rich Presence**.")
        await msg.delete(delay=4)

    @commands.command(name="rpctimer", aliases=["settimer", "rpctime"])
    async def rpctimer(self, ctx: commands.Context, target_time: str) -> None:
        """
        Manually adjust the elapsed start timer of the Globe Rich Presence.
        Supports formatted timestamps (e.g. `00:16:01`, `10:30`) or durations (`2h`, `45m`).
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        def _parse_time_offset(val: str) -> float | None:
            val = val.strip().lower()
            if ":" in val:
                parts = val.split(":")
                if len(parts) == 3:
                    try:
                        h, m, s = map(float, parts)
                        return h * 3600 + m * 60 + s
                    except ValueError:
                        return None
                elif len(parts) == 2:
                    try:
                        m, s = map(float, parts)
                        return m * 60 + s
                    except ValueError:
                        return None
            from modules.tools import _parse_duration
            return _parse_duration(val)

        offset_seconds = _parse_time_offset(target_time)
        if offset_seconds is None or offset_seconds < 0:
            await ctx.send(
                "> `!` **Invalid Timer Format:** Use `HH:MM:SS` (e.g. `00:16:01`), `MM:SS` (`10:30`), or duration (`2h`, `45m`).",
                delete_after=6,
            )
            return

        # Calculate retroactive start epoch so Discord displays exact requested elapsed time
        custom_start_epoch = time.time() - offset_seconds
        self.bot._start_epoch = custom_start_epoch

        user_id = self.bot.user.id if self.bot.user else ctx.author.id
        activities = get_default_globe_activities(user_id, custom_start_epoch)
        await self.bot.change_presence(activities=activities)

        h, rem = divmod(int(offset_seconds), 3600)
        m, s = divmod(rem, 60)
        formatted_display = f"{h:02d}:{m:02d}:{s:02d}"

        lines = [
            f"> `-` **Globe Rich Presence Timer Synchronized**",
            f"> `—` **Elapsed Time Set:** `{formatted_display}` elapsed",
            f"> `—` **Timestamp Base:** <t:{int(custom_start_epoch)}:R>",
            f"> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        msg = await ctx.send("\n".join(lines))
        await msg.delete(delay=6)

    @commands.command(name="stream", aliases=["streaming"])
    async def stream(self, ctx: commands.Context, stream_url: str, *, title: str) -> None:
        """Set your presence to Streaming (e.g. `g.stream https://twitch.tv/ninja Grinding Globe`)."""
        await ctx.message.delete()
        activity = discord.Streaming(name=title, url=stream_url)
        await self.bot.change_presence(activity=activity)
        msg = await ctx.send(f"💜 Presence updated to **Streaming**: `{title}`")
        await msg.delete(delay=4)

    @commands.command(name="play", aliases=["playing", "game"])
    async def play(self, ctx: commands.Context, *, game: str) -> None:
        """Set your presence to Playing (e.g. `g.play Valorant`)."""
        await ctx.message.delete()
        activity = discord.Game(name=game)
        await self.bot.change_presence(activity=activity)
        msg = await ctx.send(f"🎮 Presence updated to **Playing**: `{game}`")
        await msg.delete(delay=4)

    @commands.command(name="listen", aliases=["listening"])
    async def listen(self, ctx: commands.Context, *, music: str) -> None:
        """Set your presence to Listening (e.g. `g.listen Spotify`)."""
        await ctx.message.delete()
        activity = discord.Activity(type=discord.ActivityType.listening, name=music)
        await self.bot.change_presence(activity=activity)
        msg = await ctx.send(f"🎧 Presence updated to **Listening to**: `{music}`")
        await msg.delete(delay=4)

    @commands.command(name="watch", aliases=["watching"])
    async def watch(self, ctx: commands.Context, *, movie: str) -> None:
        """Set your presence to Watching (e.g. `g.watch Anime`)."""
        await ctx.message.delete()
        activity = discord.Activity(type=discord.ActivityType.watching, name=movie)
        await self.bot.change_presence(activity=activity)
        msg = await ctx.send(f"🎬 Presence updated to **Watching**: `{movie}`")
        await msg.delete(delay=4)

    @commands.command(name="stopactivity", aliases=["clearactivity", "noactivity"])
    async def stopactivity(self, ctx: commands.Context) -> None:
        """Clear active Rich Presence activity."""
        await ctx.message.delete()
        await self.bot.change_presence(activity=None)
        msg = await ctx.send("🧹 Activity status cleared.")
        await msg.delete(delay=4)

    @commands.command(name="setstatus", aliases=["status"])
    async def setstatus(self, ctx: commands.Context, status_type: str) -> None:
        """Set online status mode (`online`, `idle`, `dnd`, `invisible`)."""
        await ctx.message.delete()
        mapping = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
            "offline": discord.Status.invisible,
        }
        st = mapping.get(status_type.lower())
        if not st:
            msg = await ctx.send("❌ Status must be one of: `online`, `idle`, `dnd`, `invisible`")
            await msg.delete(delay=4)
            return

        await self.bot.change_presence(status=st)
        msg = await ctx.send(f"🟢 Status set to `{status_type.lower()}`")
        await msg.delete(delay=4)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Status(bot))
