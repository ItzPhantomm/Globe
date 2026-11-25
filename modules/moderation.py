"""
Globe — Moderation Module
Server management, member controls, enforcement, channels, roles, webhooks, and nuking.
Includes complete Role Manager and Webhook Manager suites.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from config import settings
from footprint_handlers import footprint
from ui import log_info, log_warn, log_err

P = settings.prefix


class Moderation(commands.Cog):
    """Enforcement, member moderation, role distribution, channel operations, and webhook management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._forcenick_tasks: dict[int, str] = {}

    # ── Kick & Ban ─────────────────────────────────────────────────────────────

    @commands.command(name="kick", aliases=["k"])
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Kick a member from the server."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.kick_members:
            msg = await ctx.send("❌ Missing **Kick Members** permission.")
            await msg.delete(delay=4)
            return

        try:
            await member.kick(reason=reason)
            footprint.record_action(ctx.channel.id)
            await ctx.send(f"👢 Kicked **{member}** (`{member.id}`). Reason: *{reason}*", delete_after=5)
            log_info(f"Kicked {member} from {ctx.guild.name}")
        except Exception as e:
            await ctx.send(f"❌ Failed to kick: {e}", delete_after=5)

    @commands.command(name="ban", aliases=["b"])
    async def ban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided") -> None:
        """Ban a user from the server by mention or ID."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.ban_members:
            msg = await ctx.send("❌ Missing **Ban Members** permission.")
            await msg.delete(delay=4)
            return

        try:
            await ctx.guild.ban(user, reason=reason, delete_message_days=0)
            footprint.record_action(ctx.channel.id)
            await ctx.send(f"🔨 Banned **{user}** (`{user.id}`). Reason: *{reason}*", delete_after=5)
            log_info(f"Banned {user} from {ctx.guild.name}")
        except Exception as e:
            await ctx.send(f"❌ Failed to ban: {e}", delete_after=5)

    @commands.command(name="unban", aliases=["ub"])
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "Unbanned via Globe") -> None:
        """Unban a user by their user ID."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.ban_members:
            msg = await ctx.send("❌ Missing **Ban Members** permission.")
            await msg.delete(delay=4)
            return

        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=reason)
            footprint.record_action(ctx.channel.id)
            await ctx.send(f"🔓 Unbanned **{user}** (`{user_id}`).", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to unban: {e}", delete_after=5)

    # ── Timeout / Mute ────────────────────────────────────────────────────────

    @commands.command(name="timeout", aliases=["mute", "to"])
    async def timeout(self, ctx: commands.Context, member: discord.Member, minutes: int = 10, *, reason: str = "Timed out via Globe") -> None:
        """Timeout/mute a member for N minutes (default: 10m)."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.moderate_members:
            msg = await ctx.send("❌ Missing **Timeout Members** permission.")
            await msg.delete(delay=4)
            return

        try:
            until = discord.utils.utcnow() + timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
            footprint.record_action(ctx.channel.id)
            await ctx.send(f"⏳ Timed out **{member}** for `{minutes}m`.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Timeout failed: {e}", delete_after=5)

    @commands.command(name="untimeout", aliases=["unmute", "unto"])
    async def untimeout(self, ctx: commands.Context, member: discord.Member) -> None:
        """Remove timeout/mute from a member."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        try:
            await member.timeout(None, reason="Untimeout via Globe")
            await ctx.send(f"🔊 Removed timeout for **{member}**.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to remove timeout: {e}", delete_after=5)

    # ── Nicknames & ForceNick ──────────────────────────────────────────────────

    @commands.command(name="nick", aliases=["nickname", "setnick"])
    async def nick(self, ctx: commands.Context, member: discord.Member, *, nickname: str = "") -> None:
        """Change a member's nickname (pass empty to reset)."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        try:
            new_nick = nickname if nickname else None
            await member.edit(nick=new_nick)
            shown = f"`{nickname}`" if nickname else "Default"
            await ctx.send(f"🏷️ Nickname for **{member}** set to: {shown}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Nickname change failed: {e}", delete_after=5)

    @commands.command(name="forcenick")
    async def forcenick(self, ctx: commands.Context, member: discord.Member, *, nickname: str) -> None:
        """Lock a user's nickname, reverting it whenever they attempt to change it."""
        await ctx.message.delete()
        self._forcenick_tasks[member.id] = nickname
        try:
            await member.edit(nick=nickname)
        except Exception:
            pass
        await ctx.send(f"🔒 Locked **{member}**'s nickname to `{nickname}`.", delete_after=5)

    @commands.command(name="stopforcenick")
    async def stopforcenick(self, ctx: commands.Context, member: discord.Member) -> None:
        """Remove a force-nickname lock from a member."""
        await ctx.message.delete()
        if member.id in self._forcenick_tasks:
            del self._forcenick_tasks[member.id]
            await ctx.send(f"🔓 Unlocked nickname for **{member}**.", delete_after=5)
        else:
            await ctx.send(f"❌ **{member}** is not in force-nick list.", delete_after=4)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.id in self._forcenick_tasks:
            locked_name = self._forcenick_tasks[after.id]
            if after.nick != locked_name:
                try:
                    await after.edit(nick=locked_name)
                except Exception:
                    pass

    # ── Channel Management & Nuke ──────────────────────────────────────────────

    @commands.command(name="slowmode", aliases=["sm"])
    async def slowmode(self, ctx: commands.Context, seconds: int = 0) -> None:
        """Set slowmode for the current channel in seconds (0 to disable)."""
        await ctx.message.delete()
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            status = f"`{seconds}s`" if seconds > 0 else "Disabled"
            await ctx.send(f"⏱️ Channel slowmode set to: {status}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to set slowmode: {e}", delete_after=5)

    @commands.command(name="createtext", aliases=["ctc", "textchan"])
    async def createtext(self, ctx: commands.Context, name: str, is_nsfw: bool = False) -> None:
        """Create a new text channel in the current guild."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        try:
            ch = await ctx.guild.create_text_channel(name=name, nsfw=is_nsfw)
            await ctx.send(f"📁 Created text channel {ch.mention}.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to create text channel: {e}", delete_after=5)

    @commands.command(name="createvoice", aliases=["cvc", "voicechan"])
    async def createvoice(self, ctx: commands.Context, *, name: str) -> None:
        """Create a new voice channel in the current guild."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        try:
            vc = await ctx.guild.create_voice_channel(name=name)
            await ctx.send(f"🔊 Created voice channel **{vc.name}**.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to create voice channel: {e}", delete_after=5)

    @commands.command(name="delchannel", aliases=["delc"])
    async def delchannel(self, ctx: commands.Context, channel: discord.abc.GuildChannel | None = None) -> None:
        """Delete a specified channel or the current channel."""
        await ctx.message.delete()
        target = channel or ctx.channel
        if not isinstance(target, discord.abc.GuildChannel):
            return
        try:
            ch_name = target.name
            await target.delete()
            log_info(f"Deleted channel {ch_name}")
        except Exception as e:
            await ctx.send(f"❌ Failed to delete channel: {e}", delete_after=5)

    @commands.command(name="nuke", aliases=["nukechannel"])
    async def nuke(self, ctx: commands.Context) -> None:
        """Nuke the current channel: clone it with identical permissions and delete the old one."""
        await ctx.message.delete()
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            return

        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.manage_channels:
            msg = await ctx.send("❌ Missing **Manage Channels** permission.")
            await msg.delete(delay=4)
            return

        ch = ctx.channel
        pos = ch.position
        try:
            new_channel = await ch.clone(reason="Channel nuked via Globe")
            await ch.delete(reason="Channel nuked via Globe")
            await new_channel.edit(position=pos)
            await new_channel.send(
                "💥 **Channel Nuked Successfully.**\nhttps://media.giphy.com/media/HhTXt43pk1I1W/giphy.gif",
                delete_after=10,
            )
            log_info(f"Nuked #{ch.name} in {ctx.guild.name}")
        except Exception as e:
            await ctx.send(f"❌ Nuke failed: {e}", delete_after=5)

    # ── Role Manager Suite ─────────────────────────────────────────────────────

    @commands.command(name="createrole", aliases=["crole"])
    async def createrole(self, ctx: commands.Context, color_hex: str, *, name: str) -> None:
        """Create a new role with a hex color: `g.createrole #ff00ff VIP`."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.manage_roles:
            await ctx.send("❌ Missing **Manage Roles** permission.", delete_after=4)
            return

        try:
            clean_hex = color_hex.replace("#", "")
            color_val = int(clean_hex, 16) if clean_hex else 0
            role = await ctx.guild.create_role(name=name, color=discord.Color(color_val), reason="Created via Globe")
            await ctx.send(f"🎨 Created role **{role.name}** (`{role.id}`) with color `#{clean_hex}`.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to create role: {e}", delete_after=5)

    @commands.command(name="delrole", aliases=["drole"])
    async def delrole(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Delete an existing role from the server."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.manage_roles:
            await ctx.send("❌ Missing **Manage Roles** permission.", delete_after=4)
            return
        try:
            role_name = role.name
            await role.delete(reason="Deleted via Globe")
            await ctx.send(f"🗑️ Deleted role **{role_name}**.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to delete role: {e}", delete_after=5)

    @commands.command(name="role", aliases=["giverole", "takerole", "togglerole"])
    async def role(self, ctx: commands.Context, member: discord.Member, *, target_role: discord.Role) -> None:
        """Toggle (assign or remove) a role on a member."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not perms.manage_roles:
            await ctx.send("❌ Missing **Manage Roles** permission.", delete_after=4)
            return

        try:
            if target_role in member.roles:
                await member.remove_roles(target_role, reason="Role removed via Globe")
                await ctx.send(f"➖ Removed **{target_role.name}** from **{member.display_name}**.", delete_after=5)
            else:
                await member.add_roles(target_role, reason="Role assigned via Globe")
                await ctx.send(f"➕ Assigned **{target_role.name}** to **{member.display_name}**.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Role toggle failed: {e}", delete_after=5)

    @commands.command(name="roleall", aliases=["addroleall"])
    async def roleall(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Assign a role to all members in the server."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        progress = await ctx.send(f"🔄 Distributing `{role.name}` to all members…")
        count = 0
        for member in ctx.guild.members:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason="roleall via Globe")
                    count += 1
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
        await progress.edit(content=f"✅ Gave `{role.name}` to `{count}` members.")
        await asyncio.sleep(5)
        await progress.delete()

    @commands.command(name="removeroleall", aliases=["stripall"])
    async def removeroleall(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Remove a role from all members in the server."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        progress = await ctx.send(f"🔄 Stripping `{role.name}` from all members…")
        count = 0
        for member in ctx.guild.members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="removeroleall via Globe")
                    count += 1
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
        await progress.edit(content=f"✅ Stripped `{role.name}` from `{count}` members.")
        await asyncio.sleep(5)
        await progress.delete()

    @commands.command(name="giveallroles")
    async def giveallroles(self, ctx: commands.Context, *, member: discord.Member) -> None:
        """Assign all roles below your highest role to the specified member."""
        await ctx.message.delete()
        if not ctx.guild:
            return
        bot_top = ctx.guild.me.top_role.position
        roles_to_give = [r for r in ctx.guild.roles if r.position < bot_top and not r.is_default()]
        try:
            await member.add_roles(*roles_to_give, reason="giveallroles via Globe")
            await ctx.send(f"✅ Added `{len(roles_to_give)}` roles to **{member}**.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to give roles: {e}", delete_after=5)

    # ── Webhook Manager Suite ──────────────────────────────────────────────────

    @commands.command(name="createwebhook", aliases=["cwh", "hookcreate"])
    async def createwebhook(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, *, name: str = "Globe Webhook") -> None:
        """Create a webhook in the specified or current channel."""
        await ctx.message.delete()
        target_ch = channel or ctx.channel
        if not isinstance(target_ch, discord.TextChannel):
            await ctx.send("❌ Channel must be a text channel.", delete_after=4)
            return

        try:
            hook = await target_ch.create_webhook(name=name, reason="Created via Globe")
            await ctx.send(f"🎣 Created webhook **{hook.name}** in {target_ch.mention}:\n`{hook.url}`", delete_after=12)
            log_info(f"Created webhook {hook.name} in {target_ch.name}")
        except Exception as e:
            await ctx.send(f"❌ Failed to create webhook: {e}", delete_after=5)

    @commands.command(name="listwebhooks", aliases=["hooks", "webhooks"])
    async def listwebhooks(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        """List active webhooks in current channel or guild."""
        await ctx.message.delete()
        if not ctx.guild:
            return

        try:
            if channel:
                hooks = await channel.webhooks()
                header = f"🎣 **Webhooks in #{channel.name} ({len(hooks)}):**"
            else:
                hooks = await ctx.guild.webhooks()
                header = f"🎣 **Server Webhooks ({len(hooks)}):**"

            if not hooks:
                await ctx.send("📋 No active webhooks found.", delete_after=4)
                return

            lines = [header]
            for h in hooks[:12]:
                lines.append(f"• **{h.name}** (`{h.id}`) in <#{h.channel_id}>: `{h.url}`")
            await ctx.send("\n".join(lines), delete_after=15)
        except Exception as e:
            await ctx.send(f"❌ Failed to list webhooks: {e}", delete_after=5)

    @commands.command(name="delwebhook", aliases=["dwh", "hookdel"])
    async def delwebhook(self, ctx: commands.Context, webhook_id_or_url: str) -> None:
        """Delete a webhook by its ID or complete URL."""
        await ctx.message.delete()
        try:
            if "discord.com/api/webhooks" in webhook_id_or_url:
                async with aiohttp.ClientSession() as session:
                    async with session.delete(webhook_id_or_url) as resp:
                        if resp.status in (200, 204):
                            await ctx.send("🗑️ Webhook deleted successfully via URL.", delete_after=5)
                            return
                        else:
                            await ctx.send(f"❌ Webhook delete failed (Status {resp.status}).", delete_after=5)
                            return

            hook_id = int(webhook_id_or_url)
            hook = await self.bot.fetch_webhook(hook_id)
            await hook.delete(reason="Deleted via Globe")
            await ctx.send(f"🗑️ Webhook **{hook.name}** (`{hook_id}`) deleted.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Could not delete webhook: {e}", delete_after=5)

    @commands.command(name="webhooksend", aliases=["whsend", "hookmsg"])
    async def webhooksend(self, ctx: commands.Context, webhook_url: str, *, message_content: str) -> None:
        """Dispatch a message to an external Discord webhook URL."""
        await ctx.message.delete()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json={"content": message_content}) as resp:
                    if resp.status in (200, 204):
                        await ctx.send("🚀 Webhook message dispatched successfully.", delete_after=4)
                    else:
                        await ctx.send(f"❌ Webhook returned error code {resp.status}.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Failed to post to webhook: {e}", delete_after=5)

    # ── Server Backup & Cloner ────────────────────────────────────────────────

    @commands.command(name="backupserver", aliases=["serverbackup", "guildbackup"])
    async def backupserver(self, ctx: commands.Context, guild_id: Optional[int] = None) -> None:
        """
        Snapshot roles, categories, and channels of a server into JSON (`data/backups/`).
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        guild = self.bot.get_guild(guild_id) if guild_id else ctx.guild
        if not guild:
            await ctx.send("> `!` **Guild not found** in cache.", delete_after=5)
            return

        snapshot = {
            "id": guild.id,
            "name": guild.name,
            "roles": [
                {
                    "name": r.name,
                    "color": r.color.value,
                    "permissions": r.permissions.value,
                    "hoist": r.hoist,
                    "mentionable": r.mentionable,
                }
                for r in sorted(guild.roles, key=lambda x: x.position)
                if not r.is_default() and not r.managed
            ],
            "categories": [
                {
                    "name": cat.name,
                    "position": cat.position,
                    "channels": [
                        {
                            "name": ch.name,
                            "type": "text" if isinstance(ch, discord.TextChannel) else "voice",
                            "topic": getattr(ch, "topic", None),
                            "slowmode": getattr(ch, "slowmode_delay", 0),
                            "nsfw": getattr(ch, "nsfw", False),
                            "bitrate": getattr(ch, "bitrate", 64000),
                            "user_limit": getattr(ch, "user_limit", 0),
                        }
                        for ch in sorted(cat.channels, key=lambda c: c.position)
                        if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))
                    ],
                }
                for cat in sorted(guild.categories, key=lambda c: c.position)
            ],
            "uncategorized": [
                {
                    "name": ch.name,
                    "type": "text" if isinstance(ch, discord.TextChannel) else "voice",
                    "topic": getattr(ch, "topic", None),
                    "slowmode": getattr(ch, "slowmode_delay", 0),
                    "nsfw": getattr(ch, "nsfw", False),
                }
                for ch in sorted(guild.channels, key=lambda c: c.position)
                if ch.category is None and isinstance(ch, (discord.TextChannel, discord.VoiceChannel))
            ],
        }

        out_dir = Path("data") / "backups"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{guild.id}.json"
        out_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

        lines = [
            "> `-` **Server Snapshot Saved**",
            f"> `—` **Guild:** **{guild.name}** (`{guild.id}`)",
            f"> `—` **Captured:** `{len(snapshot['roles'])}` roles · `{len(snapshot['categories'])}` categories",
            f"> `•` **File:** `{out_file}`",
        ]
        await ctx.send("\n".join(lines), file=discord.File(out_file), delete_after=20)

    @commands.command(name="cloneserver", aliases=["cloneguild", "copyserver"])
    async def cloneserver(self, ctx: commands.Context, source_id: int, target_id: Optional[int] = None) -> None:
        """
        Clone roles, categories, and channels from a source server into a target server you own/admin.
        Syntax: `g.cloneserver <source_guild_id> [target_guild_id]`
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        src = self.bot.get_guild(source_id)
        dst = self.bot.get_guild(target_id) if target_id else ctx.guild
        if not src or not dst:
            await ctx.send("> `!` **Source or target guild not found.**", delete_after=5)
            return
        if src.id == dst.id:
            await ctx.send("> `!` Source and target guilds cannot be the same.", delete_after=5)
            return

        me = dst.get_member(ctx.author.id)
        if not me or not me.guild_permissions.administrator:
            await ctx.send("> `!` **Administrator** permission required in target guild.", delete_after=5)
            return

        status = await ctx.send(f"> `-` **Cloning `{src.name}` → `{dst.name}`…** *(pacing enabled)*")

        try:
            # 1. Wipe existing non-managed channels on target
            for ch in list(dst.channels):
                try:
                    await ch.delete(reason="Globe cloner reset")
                    await asyncio.sleep(0.35)
                except Exception:
                    pass

            # 2. Recreate roles (top-down order preserved on create)
            roles_created = 0
            for r in reversed(sorted(src.roles, key=lambda x: x.position)):
                if r.is_default() or r.managed:
                    continue
                try:
                    await dst.create_role(
                        name=r.name,
                        permissions=r.permissions,
                        color=r.color,
                        hoist=r.hoist,
                        mentionable=r.mentionable,
                    )
                    roles_created += 1
                    await asyncio.sleep(0.45)
                except Exception:
                    pass

            # 3. Recreate uncategorized channels
            ch_created = 0
            for ch in sorted(src.channels, key=lambda c: c.position):
                if ch.category is not None:
                    continue
                try:
                    if isinstance(ch, discord.TextChannel):
                        await dst.create_text_channel(name=ch.name, topic=ch.topic, slowmode_delay=ch.slowmode_delay, nsfw=ch.nsfw)
                    elif isinstance(ch, discord.VoiceChannel):
                        await dst.create_voice_channel(name=ch.name, user_limit=ch.user_limit)
                    ch_created += 1
                    await asyncio.sleep(0.45)
                except Exception:
                    pass

            # 4. Recreate categories & their children
            for cat in sorted(src.categories, key=lambda c: c.position):
                try:
                    new_cat = await dst.create_category(name=cat.name)
                    await asyncio.sleep(0.4)
                    for ch in sorted(cat.channels, key=lambda c: c.position):
                        if isinstance(ch, discord.TextChannel):
                            await dst.create_text_channel(
                                name=ch.name,
                                category=new_cat,
                                topic=ch.topic,
                                slowmode_delay=ch.slowmode_delay,
                                nsfw=ch.nsfw,
                            )
                        elif isinstance(ch, discord.VoiceChannel):
                            await dst.create_voice_channel(
                                name=ch.name,
                                category=new_cat,
                                user_limit=ch.user_limit,
                            )
                        ch_created += 1
                        await asyncio.sleep(0.45)
                except Exception:
                    pass

            await status.edit(
                content="\n".join([
                    "> `-` **Server Clone Complete**",
                    f"> `—` **Source:** **{src.name}** → **Target:** **{dst.name}**",
                    f"> `—` **Cloned:** `{roles_created}` roles · `{ch_created}` channels",
                    "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
                ])
            )
        except Exception as e:
            await status.edit(content=f"> `!` **Clone Error:** `{e}`")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
