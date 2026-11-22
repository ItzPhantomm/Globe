"""
Globe — Fun Module
Commands: 8ball, roast, compliment, rate, ship, coinflip, dice, would, pp
"""

from __future__ import annotations

import hashlib
import random

from discord.ext import commands

from config import settings

P = settings.prefix

_8BALL = [
    "It is certain.", "It is decidedly so.", "Without a doubt.",
    "Yes, definitely.", "You may rely on it.", "As I see it, yes.",
    "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.",
    "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]

_ROASTS = [
    "You're the human equivalent of a participation trophy.",
    "I'd roast you, but my mom said I'm not allowed to burn trash.",
    "You're the reason the gene pool needs a lifeguard.",
    "If brains were dynamite, you couldn't blow your nose.",
    "You have the charisma of a damp sock.",
    "I've seen better heads on a pimple.",
    "You're proof that evolution can go in reverse.",
    "Your birth certificate is an apology letter from the condom factory.",
    "If ignorance is bliss, you must be the happiest person alive.",
    "I'd agree with you but then we'd both be wrong.",
]

_COMPLIMENTS = [
    "You have an amazing smile that lights up the room! 😊",
    "You're incredibly thoughtful and kind-hearted. 💙",
    "Your creativity never ceases to amaze me! ✨",
    "You make everyone around you feel comfortable and valued. 🌟",
    "You're one of those people who makes the world better just by existing. 💫",
    "Your determination is truly inspiring! 🔥",
    "You have a heart of gold and a mind to match. 💛",
    "You're the kind of person everyone wants in their corner. 🤝",
]


class Fun(commands.Cog):
    """Fun and entertaining commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── g.8ball ───────────────────────────────────────────────────────────────

    @commands.command(name="8ball", aliases=["8b", "eightball"])
    async def eightball(self, ctx: commands.Context, *, question: str) -> None:
        """Ask the magic 8-ball."""
        await ctx.message.delete()
        answer = random.choice(_8BALL)
        msg = await ctx.send(f"🎱 **Q:** {question}\n**A:** {answer}")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.roast ───────────────────────────────────────────────────────────────

    @commands.command(name="roast", aliases=["burn"])
    async def roast(self, ctx: commands.Context, *, user: str = "someone") -> None:
        """Roast someone (or yourself)."""
        await ctx.message.delete()
        roast_text = random.choice(_ROASTS)
        msg = await ctx.send(f"🔥 **{user}:** {roast_text}")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.compliment ──────────────────────────────────────────────────────────

    @commands.command(name="compliment", aliases=["comp", "nice"])
    async def compliment(self, ctx: commands.Context, *, user: str = "you") -> None:
        """Give someone a compliment."""
        await ctx.message.delete()
        comp = random.choice(_COMPLIMENTS)
        msg = await ctx.send(f"💙 **{user}:** {comp}")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.rate ────────────────────────────────────────────────────────────────

    @commands.command(name="rate")
    async def rate(self, ctx: commands.Context, *, thing: str) -> None:
        """Rate something out of 10 (deterministic per input)."""
        await ctx.message.delete()
        # Deterministic rating so it stays consistent
        h = int(hashlib.md5(thing.lower().encode()).hexdigest(), 16)
        score = h % 11  # 0-10
        bar = "█" * score + "░" * (10 - score)
        emoji = "🔥" if score >= 8 else ("😐" if score >= 5 else "💀")
        msg = await ctx.send(f"{emoji} **{thing}:** `[{bar}]` **{score}/10**")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.ship ────────────────────────────────────────────────────────────────

    @commands.command(name="ship")
    async def ship(self, ctx: commands.Context, person1: str, *, person2: str) -> None:
        """Ship two people together."""
        await ctx.message.delete()
        combined = person1.lower() + person2.lower()
        h = int(hashlib.md5(combined.encode()).hexdigest(), 16)
        pct = h % 101  # 0-100
        bar = "💗" * (pct // 10) + "🖤" * (10 - pct // 10)
        grade = "💞 soulmates!" if pct >= 90 else ("❤️ a match!" if pct >= 70 else ("🤷 meh" if pct >= 40 else "💔 nope"))
        msg = await ctx.send(
            f"💘 **{person1}** + **{person2}**\n`[{bar}]` **{pct}%** — {grade}"
        )
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.coinflip ────────────────────────────────────────────────────────────

    @commands.command(name="coinflip", aliases=["coin", "flip"])
    async def coinflip(self, ctx: commands.Context) -> None:
        """Flip a coin."""
        await ctx.message.delete()
        result = random.choice(["🪙 **Heads!**", "🪙 **Tails!**"])
        msg = await ctx.send(result)
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.dice ────────────────────────────────────────────────────────────────

    @commands.command(name="dice", aliases=["roll", "d"])
    async def dice(self, ctx: commands.Context, sides: int = 6) -> None:
        """Roll an N-sided dice (default: d6)."""
        await ctx.message.delete()
        if sides < 2 or sides > 1000:
            await ctx.send("❌ Sides must be between 2 and 1000.")
            return
        result = random.randint(1, sides)
        msg = await ctx.send(f"🎲 **d{sides}:** rolled `{result}`")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.pp ──────────────────────────────────────────────────────────────────

    @commands.command(name="pp", aliases=["ppsize"])
    async def pp(self, ctx: commands.Context, *, user: str | None = None) -> None:
        """Check the pp size of someone."""
        await ctx.message.delete()
        target = user or ctx.author.display_name
        h = int(hashlib.md5(target.lower().encode()).hexdigest(), 16)
        size = h % 16
        shaft = "=" * size
        msg = await ctx.send(f"🍆 **{target}:** 8{shaft}D  ({size} inches)")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
