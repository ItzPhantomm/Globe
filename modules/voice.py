"""
Globe — Voice Module
Commands: voiceinfo, vclist, vckick (server perms), vcmove
"""

from __future__ import annotations

import discord
from discord.ext import commands

from config import settings


class Voice(commands.Cog):
    """Voice channel utilities."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── g.voiceinfo ───────────────────────────────────────────────────────────

    @commands.command(name="voiceinfo", aliases=["vi", "vc"])
    async def voiceinfo(self, ctx: commands.Context) -> None:
        """Show info about the voice channel you're in."""
        await ctx.message.delete()
        if not ctx.guild:
            await ctx.send("❌ Not in a server.", delete_after=5)
            return
        member = ctx.guild.get_member(ctx.author.id)
        if not member or not member.voice or not member.voice.channel:
            msg = await ctx.send("❌ You're not in a voice channel.")
            await msg.delete(delay=4)
            return
        vc = member.voice.channel
        members_list = ", ".join(m.display_name for m in vc.members)
        lines = [
            f"🔊 **{vc.name}** (`{vc.id}`)",
            f"**Members ({len(vc.members)}):** {members_list or '—'}",
            f"**Bitrate:** `{vc.bitrate // 1000}kbps`",
            f"**User limit:** `{vc.user_limit or 'unlimited'}`",
            f"**Region:** `{vc.rtc_region or 'auto'}`",
        ]
        msg = await ctx.send("\n".join(lines))
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.vclist ──────────────────────────────────────────────────────────────

    @commands.command(name="vclist", aliases=["vcs", "voicechannels"])
    async def vclist(self, ctx: commands.Context) -> None:
        """List all voice channels in the server and their occupancy."""
        await ctx.message.delete()
        if not ctx.guild:
            await ctx.send("❌ Not in a server.", delete_after=5)
            return
        vcs = [ch for ch in ctx.guild.channels if isinstance(ch, discord.VoiceChannel)]
        if not vcs:
            msg = await ctx.send("❌ No voice channels found.")
        else:
            lines = [f"🔊 **Voice Channels ({len(vcs)}):**"]
            for vc in sorted(vcs, key=lambda c: c.position):
                occ = f"`{len(vc.members)}/{vc.user_limit or '∞'}`"
                lines.append(f"**{vc.name}** {occ}")
            msg = await ctx.send("\n".join(lines))
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── g.vckick ──────────────────────────────────────────────────────────────

    @commands.command(name="vckick")
    async def vckick(self, ctx: commands.Context, *, member: discord.Member) -> None:
        """Disconnect a member from their voice channel (requires Move Members)."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.get_member(ctx.author.id))
        if not perms.move_members:
            await ctx.send("❌ You need **Move Members** permission.", delete_after=5)
            return
        if not member.voice:
            await ctx.send(f"❌ **{member.display_name}** is not in a voice channel.", delete_after=4)
            return
        await member.move_to(None)
        msg = await ctx.send(f"👢 Kicked **{member.display_name}** from voice.")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Voice(bot))
