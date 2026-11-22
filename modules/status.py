"""
Globe — Status & Presence Module
Commands: stream, play, listen, watch, stopactivity, setstatus, defaultrpc
Allows custom Rich Presence activity manipulation for selfbot accounts.
Default Globe Rich Presence with profile image, Watching status, elapsed start timer, and interactive buttons.
"""

from __future__ import annotations

import time
import discord
from discord.ext import commands

from config import settings
from ui import log_info, log_err

GLOBE_IMAGE_URL = "https://cdn.discordapp.com/attachments/1564278072574738513/1573984310942367806/ed7972243781a8a0a24bebad02f7b4dc.jpg"
GLOBE_REPO_URL = "https://github.com/ItzPhantomm/Globe"

# Permanent raw asset hosted on the official Globe repository
GLOBE_REPO_URL = "https://github.com/ItzPhantomm/Globe"
GLOBE_RAW_IMAGE_URL = "https://raw.githubusercontent.com/ItzPhantomm/Globe/main/assets/globe.jpg"


class CustomRpcActivity(discord.BaseActivity):
    """Direct Discord Gateway compatible activity supporting custom buttons and rich assets."""

    def __init__(self, data: dict) -> None:
        self._data = data
        self.type = discord.ActivityType(data.get("type", 3))

    def to_dict(self) -> dict:
        return self._data


def get_default_globe_activity(user_id: int | None = None, start_time: float | None = None) -> discord.BaseActivity:
    """Build the official default Globe Rich Presence activity."""
    friend_link = f"https://discord.com/users/{user_id}" if user_id else "https://discord.com"
    start_ms = int((start_time if start_time else time.time()) * 1000)

    # Standard discord.py-self Activity structure with metadata button_urls
    try:
        return discord.Activity(
            type=discord.ActivityType.watching,
            name="Globe",
            application_id=1440261825852739706,
            details="Your All in one Selfbot",
            state="Active · Clean & Fast",
            timestamps={"start": start_ms},
            assets={
                "large_image": GLOBE_RAW_IMAGE_URL,
                "large_text": "Globe Selfbot",
            },
            buttons=["Use Globe!", "Add Friend"],
            metadata={
                "button_urls": [GLOBE_REPO_URL, friend_link],
            },
        )
    except Exception:
        payload = {
            "name": "Globe",
            "type": 3,
            "application_id": 1440261825852739706,
            "details": "Your All in one Selfbot",
            "state": "Active · Clean & Fast",
            "timestamps": {"start": start_ms},
            "assets": {
                "large_image": GLOBE_RAW_IMAGE_URL,
                "large_text": "Globe Selfbot",
            },
            "buttons": ["Use Globe!", "Add Friend"],
            "metadata": {
                "button_urls": [GLOBE_REPO_URL, friend_link],
            },
        }
        return CustomRpcActivity(payload)


class Status(commands.Cog):
    """Presence and custom activity management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._init_done: bool = False

    async def apply_default_rpc(self) -> bool:
        """Apply official default Globe Rich Presence and verify."""
        try:
            user_id = self.bot.user.id if self.bot.user else None
            # Retrieve bot start epoch for runtime counter
            start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
            activity = get_default_globe_activity(user_id, start_epoch)
            await self.bot.change_presence(activity=activity)
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
        activity = get_default_globe_activity(user_id, start_epoch)
        await self.bot.change_presence(activity=activity)
        msg = await ctx.send("🌐 Presence reset to official **Globe Rich Presence**.")
        await msg.delete(delay=4)

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
