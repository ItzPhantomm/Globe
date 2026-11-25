"""
Globe — Voice Module
Commands: voiceinfo, vclist, vckick, joinvc, leavevc, vcfollow, vcmoveall
"""

from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

from config import settings
from ui import log_info, log_warn


class Voice(commands.Cog):
    """Voice channel utilities, persistent 24/7 stay, and member movement."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._stay_channel_id: int | None = None
        self._stay_mute: bool = True
        self._stay_deaf: bool = True
        self._follow_target_id: int | None = None
        self._reconnect_lock = asyncio.Lock()

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

    # ── g.joinvc / g.leavevc (24/7 Persistent Stay) ───────────────────────────

    @commands.command(name="joinvc", aliases=["jvc", "vcstay", "247vc"])
    async def joinvc(
        self,
        ctx: commands.Context,
        channel: discord.VoiceChannel | discord.StageChannel | None = None,
        mode: str = "deaf",
    ) -> None:
        """
        Join and stay 24/7 in a voice channel (auto-reconnects if disconnected).
        Modes: `deaf` (default: mute+deaf), `mute` (mute only), `open` (unmuted).
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        target_vc = channel
        if target_vc is None and ctx.guild:
            me = ctx.guild.get_member(ctx.author.id)
            if me and me.voice and me.voice.channel:
                target_vc = me.voice.channel

        if target_vc is None:
            await ctx.send(f"> `!` **Usage:** `{settings.prefix}joinvc <channel_id_or_name> [deaf|mute|open]`", delete_after=5)
            return

        m = mode.lower()
        self._stay_mute = m in ("deaf", "mute")
        self._stay_deaf = m == "deaf"
        self._stay_channel_id = target_vc.id

        try:
            if ctx.guild and ctx.guild.voice_client:
                await ctx.guild.voice_client.disconnect(force=True)
            await target_vc.connect(self_deaf=self._stay_deaf, self_mute=self._stay_mute, reconnect=True)
            lines = [
                "> `-` **24/7 Voice Stay Activated**",
                f"> `—` **Channel:** **{target_vc.name}** (`{target_vc.id}`)",
                f"> `—` **State:** `mute={self._stay_mute}` · `deaf={self._stay_deaf}`",
                "> `•` *Auto-reconnect armed on disconnect.*",
            ]
            await ctx.send("\n".join(lines), delete_after=8)
            log_info(f"24/7 VC stay joined: {target_vc.name} ({target_vc.id})")
        except Exception as e:
            self._stay_channel_id = None
            await ctx.send(f"> `!` **Voice Connect Error:** `{e}`", delete_after=5)

    @commands.command(name="leavevc", aliases=["lvc", "dcvc"])
    async def leavevc(self, ctx: commands.Context) -> None:
        """Disconnect from voice and disarm 24/7 VC stay."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        self._stay_channel_id = None
        disconnected = 0
        for vc in list(self.bot.voice_clients):
            try:
                await vc.disconnect(force=True)
                disconnected += 1
            except Exception:
                pass
        await ctx.send(f"> `-` **Disconnected** (`{disconnected}` voice session(s) closed).", delete_after=5)

    # ── g.vcfollow ────────────────────────────────────────────────────────────

    @commands.command(name="vcfollow", aliases=["followvc", "vcf"])
    async def vcfollow(self, ctx: commands.Context, target: str | None = None) -> None:
        """
        Automatically follow a target user whenever they switch voice channels.
        Pass `off` / `stop` or invoke without args to disable.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        if not target or target.lower() in ("off", "stop", "none", "clear"):
            self._follow_target_id = None
            await ctx.send("> `-` **VC Follow:** `DISABLED`", delete_after=5)
            return

        try:
            user = await commands.UserConverter().convert(ctx, target)
        except Exception:
            await ctx.send(f"> `!` **User not found:** `{target}`", delete_after=5)
            return

        self._follow_target_id = user.id
        lines = [
            "> `-` **VC Follow Armed**",
            f"> `—` **Target:** **{user}** (`{user.id}`)",
            f"> `•` *Disable anytime with `{settings.prefix}vcfollow off`*",
        ]
        await ctx.send("\n".join(lines), delete_after=8)

        # Immediately join if target is already in a mutual VC
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if member and member.voice and member.voice.channel:
                try:
                    if guild.voice_client:
                        await guild.voice_client.move_to(member.voice.channel)
                    else:
                        await member.voice.channel.connect(self_deaf=True, self_mute=True)
                except Exception:
                    pass
                break

    # ── g.vcmoveall ───────────────────────────────────────────────────────────

    @commands.command(name="vcmoveall", aliases=["moveall", "vcma"])
    async def vcmoveall(
        self,
        ctx: commands.Context,
        source: discord.VoiceChannel,
        destination: discord.VoiceChannel,
    ) -> None:
        """Move all members from one voice channel to another (requires Move Members)."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        me = ctx.guild.get_member(ctx.author.id)
        if not me or not ctx.channel.permissions_for(me).move_members:
            await ctx.send("> `!` **Missing Permission:** `Move Members` required.", delete_after=5)
            return

        members = list(source.members)
        if not members:
            await ctx.send(f"> `!` **{source.name}** has no members to move.", delete_after=4)
            return

        moved = 0
        for m in members:
            try:
                await m.move_to(destination)
                moved += 1
                await asyncio.sleep(0.25)
            except Exception:
                pass

        await ctx.send(
            f"> `-` **Moved `{moved}/{len(members)}` members** from **{source.name}** → **{destination.name}**.",
            delete_after=6,
        )

    # ── Voice State Listener ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if not self.bot.user:
            return

        # 1. Persistent 24/7 stay auto-reconnect
        if (
            member.id == self.bot.user.id
            and self._stay_channel_id is not None
            and after.channel is None
        ):
            async with self._reconnect_lock:
                await asyncio.sleep(2.0)
                if self._stay_channel_id is None:
                    return
                ch = self.bot.get_channel(self._stay_channel_id)
                if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                    try:
                        await ch.connect(self_deaf=self._stay_deaf, self_mute=self._stay_mute, reconnect=True)
                        log_info(f"24/7 VC stay reconnected to {ch.name}")
                    except Exception as e:
                        log_warn(f"24/7 VC reconnect failed: {e}")

        # 2. VC Follow target user across channels
        if (
            self._follow_target_id is not None
            and member.id == self._follow_target_id
            and before.channel != after.channel
            and after.channel is not None
        ):
            try:
                vc_client = member.guild.voice_client
                if vc_client:
                    await vc_client.move_to(after.channel)
                else:
                    await after.channel.connect(self_deaf=True, self_mute=True)
            except Exception:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Voice(bot))
