"""
Globe — Status & Presence Module
Commands: stream, play, listen, watch, stopactivity, setstatus, defaultrpc
Allows custom Rich Presence activity manipulation for selfbot accounts.
Default Globe Rich Presence with profile image, Watching status, elapsed start timer, and interactive buttons.
Synchronizes both Rich Presence Activity and Custom Status to ensure 100% visibility.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
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
    # Fully compatible across both modern and legacy discord.py-self builds (Android/Termux & Linux)
    activity_button_cls = getattr(discord, "ActivityButton", None)
    buttons_param: list[Any]
    if activity_button_cls is not None:
        try:
            btn1 = activity_button_cls(label="Try Globe!", url=GLOBE_REPO_URL)
            btn2 = activity_button_cls(label="Add Friend", url=friend_link)
            buttons_param = [btn1, btn2]
        except Exception:
            buttons_param = ["Try Globe!", "Add Friend"]
    else:
        buttons_param = ["Try Globe!", "Add Friend"]

    try:
        primary_act = discord.Activity(
            name="Globe",
            type=discord.ActivityType.watching,
            application_id=GLOBE_APP_ID,
            details="Globe",
            state="Active. Made by ylemn",
            timestamps={"start": start_ms},
            assets={"large_image": GLOBE_ASSET_ID, "large_text": "Globe Selfbot"},
            buttons=buttons_param,
            metadata={"button_urls": [GLOBE_REPO_URL, friend_link]},
        )
    except Exception:
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
            "buttons": ["Try Globe!", "Add Friend"],
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
        self._spoofer_running: bool = False
        self._spoofer_cancel: bool = False

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
        if self._spoofer_running:
            self._spoofer_cancel = True
        user_id = self.bot.user.id if self.bot.user else ctx.author.id
        start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
        activities = get_default_globe_activities(user_id, start_epoch)
        await self.bot.change_presence(activities=activities, edit_settings=False)
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

    @commands.command(name="publicrpc", aliases=["makepublic", "shareactivity"])
    async def publicrpc(self, ctx: commands.Context) -> None:
        """
        Ensure your Rich Presence and Game Activity are publicly broadcast to non-friends and mutual servers.
        Configures user account settings to enable show_current_game and re-syncs presence across Discord.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        status_msg = await ctx.send("> `—` **Updating Discord Activity Privacy to Public…**")
        applied_settings = False
        try:
            if hasattr(self.bot, "settings") and self.bot.settings:
                # Update account-level protobuf settings so Discord broadcasts games/activities to non-friends
                await self.bot.settings.edit(show_current_game=True)
                applied_settings = True
        except Exception as e:
            log_err(f"Failed to patch user settings: {e}")

        # Re-apply dual presence broadcast with edit_settings=True
        user_id = self.bot.user.id if self.bot.user else ctx.author.id
        start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
        activities = get_default_globe_activities(user_id, start_epoch)
        try:
            await self.bot.change_presence(activities=activities, status=discord.Status.online, edit_settings=True)
        except Exception as e:
            log_err(f"Failed to re-broadcast public presence: {e}")

        setting_note = "Enabled `show_current_game` on account" if applied_settings else "Broadcasting public activity and custom status"
        lines = [
            "> `-` **Public Rich Presence Visibility Configured**",
            f"> `—` **Account Privacy Sync:** {setting_note}",
            "> `—` **Non-Friend Broadcast:** Active (Rich Activity + Custom Status sync)",
            "> `—` **Server Popouts:** Visible to all server members & direct messages",
            "> `•` *Tip: Ensure 'Display current activity as a status message' is enabled in your Discord Settings > Activity Privacy.*",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        await status_msg.edit(content="\n".join(lines))
        await status_msg.delete(delay=10)

    # ── Batch Badge & Game Variety Telemetry Spoofer ──────────────────────────

    @commands.command(name="badgespoofer", aliases=["spoofbadges", "batchspoofer", "gamespoofer"])
    async def badgespoofer(self, ctx: commands.Context, *args: str) -> None:
        """
        Simulate detectable game sessions to advance Discord's Game Variety and Game Time badges.
        Usage:
          g.badgespoofer [count] [interval]
          g.badgespoofer variety [count] [interval]
          g.badgespoofer play <game_name>
          g.badgespoofer stop
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        # 1. Stop / Cancel sub-command
        if args and args[0].lower() in ("stop", "cancel", "halt", "quit", "exit"):
            if self._spoofer_running:
                self._spoofer_cancel = True
                msg = await ctx.send("> `—` **Halting active spoofer session…**")
                await msg.delete(delay=4)
            else:
                user_id = self.bot.user.id if self.bot.user else ctx.author.id
                start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
                activities = get_default_globe_activities(user_id, start_epoch)
                await self.bot.change_presence(activities=activities, edit_settings=False)
                msg = await ctx.send("> `—` **No active spoofer. Restored Globe Rich Presence.**")
                await msg.delete(delay=4)
            return

        # 2. Single game playtime farming sub-command (e.g. g.badgespoofer play Counter-Strike 2)
        if args and args[0].lower() == "play":
            game_name = " ".join(args[1:]).strip() if len(args) > 1 else "Grand Theft Auto V"
            if not game_name:
                game_name = "Grand Theft Auto V"
            game_act = discord.Activity(
                name=game_name,
                type=discord.ActivityType.playing,
                timestamps={"start": int(time.time() * 1000)},
                details="In Game",
                state="Playing",
            )
            await self.bot.change_presence(activity=game_act, edit_settings=False)
            play_lines = [
                "> `-` **Single Game Telemetry Active**",
                f"> `—` **Game Title:** `{game_name}`",
                "> `—` **Status:** Live session active · Accumulating playtime towards **Game Time Badge**",
                f"> `•` *Run `{settings.prefix}badgespoofer stop` or `{settings.prefix}defaultrpc` to restore Globe presence.*",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
            msg = await ctx.send("\n".join(play_lines))
            await msg.delete(delay=15)
            return

        # 3. Batch Game Variety Mode
        if self._spoofer_running:
            msg = await ctx.send("> `!` **A spoofer session is already running.** Type `g.badgespoofer stop` first.")
            await msg.delete(delay=5)
            return

        # Parse count and interval from args
        count = 15
        interval = 5.0
        numeric_args: list[int] = []
        for a in args:
            if a.isdigit():
                numeric_args.append(int(a))

        if len(numeric_args) >= 1:
            count = max(1, min(numeric_args[0], 50))
        if len(numeric_args) >= 2:
            interval = max(3.0, min(float(numeric_args[1]), 30.0))

        status_msg = await ctx.send("> `—` **Connecting to Discord Detectable Catalog…**")

        try:
            import httpx
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await client.get("https://discord.com/api/v9/applications/detectable")
                games_catalog = resp.json()
        except Exception as e:
            await status_msg.edit(content=f"> `!` **Catalog Fetch Failed:** `{e}`")
            await status_msg.delete(delay=6)
            return

        # Filter valid games with executable signatures and IDs
        valid_games = [g for g in games_catalog if g.get("id") and g.get("name") and g.get("executables")]
        if not valid_games:
            await status_msg.edit(content="> `!` **No detectable games found in Discord catalog.**")
            await status_msg.delete(delay=5)
            return

        import random
        selected_games = random.sample(valid_games, min(count, len(valid_games)))
        total_games = len(selected_games)

        self._spoofer_running = True
        self._spoofer_cancel = False
        batch_start = time.time()

        initial_lines = [
            "> `-` **Batch Game Variety Spoofer — Starting**",
            f"> `—` **Target Count:** `{total_games}` verified titles",
            f"> `—` **Hold Pace:** `{interval:.0f}s` per title (anti-flood guard)",
            "> `—` **Target Badge:** Discord Game Variety & Game Time Badges",
            "> `•` *Initiating gateway session stream now…*",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        await status_msg.edit(content="\n".join(initial_lines))
        await asyncio.sleep(1.5)

        idx = 0
        for idx, g in enumerate(selected_games, 1):
            if self._spoofer_cancel:
                break

            g_id = int(g["id"])
            g_name = g.get("name", "Unknown Game")
            g_icon = g.get("icon_hash")

            act_kwargs: dict[str, Any] = {
                "name": g_name,
                "type": discord.ActivityType.playing,
                "application_id": g_id,
                "timestamps": {"start": int(time.time() * 1000)},
                "details": "In Game",
                "state": "Playing",
            }
            if g_icon:
                act_kwargs["assets"] = {"large_image": g_icon, "large_text": g_name}

            game_act = discord.Activity(**act_kwargs)

            try:
                # edit_settings=False ensures Gateway Opcode 3 is sent directly without hitting REST settings rate limits
                await self.bot.change_presence(activity=game_act, edit_settings=False)
            except Exception as e:
                log_err(f"Presence broadcast error during spoofing: {e}")

            # Calculate live timing and status
            now = time.time()
            elapsed_sec = int(now - batch_start)
            remaining_sec = max(0, int((total_games - idx) * interval))
            elapsed_str = f"{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}"
            remaining_str = f"{remaining_sec // 60:02d}:{remaining_sec % 60:02d}"
            pct = int((idx / total_games) * 100)

            live_lines = [
                "> `-` **Batch Game Variety Spoofer — Active**",
                f"> `—` **Live Progress:** `[{idx}/{total_games}]` ({pct}%)",
                f"> `—` **Active Game:** `{g_name}`",
                f"> `—` **Application ID:** `{g_id}`",
                f"> `—` **Live Time:** `{elapsed_str}` elapsed · `{remaining_str}` remaining",
                f"> `—` **Hold Cadence:** `{interval:.0f}s` per detectable title",
                "> `•` *Live status streaming to Discord Gateway telemetry…*",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
            try:
                await status_msg.edit(content="\n".join(live_lines))
            except Exception:
                pass

            # Sleep in 0.5s increments to respond immediately if user cancels
            steps = int(interval * 2)
            for _ in range(steps):
                if self._spoofer_cancel:
                    break
                await asyncio.sleep(0.5)

        # Restore official Globe Rich Presence
        user_id = self.bot.user.id if self.bot.user else ctx.author.id
        start_epoch = getattr(self.bot, "_start_epoch", None) or time.time()
        activities = get_default_globe_activities(user_id, start_epoch)
        try:
            await self.bot.change_presence(activities=activities, edit_settings=False)
        except Exception as e:
            log_err(f"Failed to restore Globe presence: {e}")

        total_sec = int(time.time() - batch_start)
        total_str = f"{total_sec // 60:02d}:{total_sec % 60:02d}"

        if self._spoofer_cancel:
            done_lines = [
                "> `-` **Batch Game Variety Spoofer — Stopped**",
                f"> `—` **Status:** `Cancelled by user`",
                f"> `—` **Titles Spoofed:** `{idx - 1}/{total_games}` verified applications",
                f"> `—` **Session Duration:** `{total_str}`",
                "> `—` **Rich Presence:** Restored to official Globe Rich Presence",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
        else:
            sample_titles = ", ".join(f"`{g.get('name', 'Unknown')}`" for g in selected_games[:5])
            done_lines = [
                "> `-` **Batch Game Variety Spoofer — Done**",
                f"> `—` **Status:** `Completed`",
                f"> `—` **Titles Simulated:** `{total_games}/{total_games}` verified applications registered",
                f"> `—` **Total Elapsed:** `{total_str}`",
                f"> `—` **Sample Processed:** {sample_titles}…",
                "> `—` **Rich Presence:** Restored to official Globe Rich Presence",
                "> `•` *Discord Game Variety badge refreshes within 24–72 hours on user profile cache.*",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]

        try:
            await status_msg.edit(content="\n".join(done_lines))
        except Exception:
            pass

        # IMPORTANT: Keep the completed message permanently in channel (do not delete)
        self._spoofer_running = False
        self._spoofer_cancel = False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Status(bot))
