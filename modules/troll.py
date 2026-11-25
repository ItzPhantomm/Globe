"""
Globe — Troll Module
Lighthearted trolling, ghost pings, spam controls, and fake notifications.
Directly ports popular Avarice trolling features into Globe with rate-limit and footprint guards.
"""

from __future__ import annotations

import asyncio
import random
import time
import discord
from discord.ext import commands

from config import settings
from footprint_handlers import footprint
from ui import log_info, log_warn


class Troll(commands.Cog):
    """Trolling, ghost pinging, text flooding, mimicry, and interactive pranks."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._mimic_targets: dict[int, int] = {}  # {channel_id: user_id}
        self._react_targets: dict[int, str] = {}  # {user_id: emoji}
        self._last_mimic_ts: float = 0.0

    # ── Ghost Ping ────────────────────────────────────────────────────────────

    @commands.command(name="ghostping", aliases=["gp"])
    async def ghostping(self, ctx: commands.Context, target: discord.User, channel: discord.TextChannel | None = None) -> None:
        """Send a mention that is immediately deleted so only the notification remains."""
        await ctx.message.delete()
        dest = channel or ctx.channel
        try:
            m = await dest.send(f"{target.mention}")
            await m.delete()
            footprint.record_action(dest.id)
            log_info(f"Ghost-pinged {target} in #{dest.name}")
        except Exception as e:
            await ctx.send(f"❌ Failed to ghostping: {e}", delete_after=4)

    @commands.command(name="ghostpingrole", aliases=["gpr"])
    async def ghostpingrole(self, ctx: commands.Context, role: discord.Role, channel: discord.TextChannel | None = None) -> None:
        """Ghost ping an entire role instantly."""
        await ctx.message.delete()
        dest = channel or ctx.channel
        try:
            m = await dest.send(f"{role.mention}")
            await m.delete()
            footprint.record_action(dest.id)
        except Exception as e:
            await ctx.send(f"❌ Failed to ghostping role: {e}", delete_after=4)

    # ── Flood / Spam ──────────────────────────────────────────────────────────

    @commands.command(name="spam")
    async def spam(self, ctx: commands.Context, amount: int, *, message: str) -> None:
        """
        Send a message N times (max: 25) with humanized footprint jitter.
        `g.spam 5 Hello!`
        """
        await ctx.message.delete()
        count = min(max(amount, 1), 25)

        for i in range(count):
            if footprint.is_spamming(ctx.channel.id, threshold=15, window=10.0):
                await ctx.send("⚠️ Spam safety throttle triggered.", delete_after=4)
                break
            try:
                await ctx.send(message)
                footprint.record_action(ctx.channel.id)
                await asyncio.sleep(0.45)
            except Exception:
                break

    @commands.command(name="massmention", aliases=["mm"])
    async def massmention(self, ctx: commands.Context) -> None:
        """Mention all visible members in batches of 15 and immediately purge."""
        await ctx.message.delete()
        if not ctx.guild:
            return

        members = [m.mention for m in ctx.guild.members if not m.bot][:45]
        if not members:
            return

        chunks = [members[i:i + 15] for i in range(0, len(members), 15)]
        for chunk in chunks:
            try:
                m = await ctx.send(" ".join(chunk))
                await asyncio.sleep(0.5)
                await m.delete()
            except Exception:
                break

    # ── Interactive Trolling ──────────────────────────────────────────────────

    @commands.command(name="faketyping", aliases=["typeforever"])
    async def faketyping(self, ctx: commands.Context, seconds: int = 15) -> None:
        """Hold the typing status in the channel for N seconds."""
        await ctx.message.delete()
        duration = min(max(seconds, 3), 120)
        async with ctx.channel.typing():
            await asyncio.sleep(duration)

    @commands.command(name="fakehack", aliases=["hack"])
    async def fakehack(self, ctx: commands.Context, target: discord.User) -> None:
        """Run an animated joke 'hacking' sequence against a user."""
        await ctx.message.delete()
        steps = [
            f"💻 Commencing breach on **{target.name}**…",
            f"🔍 Extracting Discord credentials… [Token: `MTA4{random.randint(100,999)}●●●●`]",
            f"📡 Enumerating IP address… `192.168.{random.randint(1,254)}.{random.randint(1,254)}`",
            f"📂 Dumping private direct messages…",
            f"✅ Breach complete: Forwarding reports to Dark Web.",
        ]
        msg = await ctx.send(steps[0])
        for step in steps[1:]:
            await asyncio.sleep(1.8)
            try:
                await msg.edit(content=step)
            except Exception:
                break
        await asyncio.sleep(4)
        await msg.delete()

    # ── Stealth / Live Mimic & React Spam ─────────────────────────────────────

    @commands.command(name="mimic", aliases=["copycat", "echo_user"])
    async def mimic(self, ctx: commands.Context, target: discord.User) -> None:
        """Mirror every message sent by a target user in this channel."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        if self.bot.user and target.id == self.bot.user.id:
            await ctx.send("❌ Cannot mimic yourself.", delete_after=4)
            return
        self._mimic_targets[ctx.channel.id] = target.id
        await ctx.send(f"> `-` **Mimic Armed:** Mirroring **{target}** in this channel.", delete_after=5)

    @commands.command(name="unmimic", aliases=["stopmimic"])
    async def unmimic(self, ctx: commands.Context) -> None:
        """Stop mimicking users in the current channel."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        removed = self._mimic_targets.pop(ctx.channel.id, None)
        if removed:
            await ctx.send("> `-` **Mimic Stopped** in this channel.", delete_after=4)
        else:
            await ctx.send("> `!` No active mimic in this channel.", delete_after=4)

    @commands.command(name="reactspam", aliases=["rspam", "stalkreact"])
    async def reactspam(self, ctx: commands.Context, target: discord.User, emoji: str | None = None) -> None:
        """
        Auto-react to every new message from a target user across all visible channels.
        Omit emoji (or pass `off`) to stop reacting to that user.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        if not emoji or emoji.lower() in ("off", "stop", "clear"):
            self._react_targets.pop(target.id, None)
            await ctx.send(f"> `-` **React-Spam Stopped** for **{target}**.", delete_after=4)
            return
        self._react_targets[target.id] = emoji
        await ctx.send(f"> `-` **React-Spam Armed:** Reacting {emoji} to **{target}**.", delete_after=5)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.bot.user or message.author.id == self.bot.user.id or message.author.bot:
            return

        # 1. Live Mimic
        mimic_uid = self._mimic_targets.get(message.channel.id)
        if mimic_uid == message.author.id and message.content:
            now = time.monotonic()
            if now - self._last_mimic_ts >= 1.2 and not footprint.is_spamming(message.channel.id, threshold=10, window=10.0):
                self._last_mimic_ts = now
                try:
                    await message.channel.send(message.content[:1900])
                    footprint.record_action(message.channel.id)
                except Exception:
                    pass

        # 2. Target React Spam
        if emoji := self._react_targets.get(message.author.id):
            try:
                await message.add_reaction(emoji)
                footprint.record_action(message.channel.id)
            except Exception:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Troll(bot))
