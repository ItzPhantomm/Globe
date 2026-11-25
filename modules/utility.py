"""
Globe — Utility Module (Consolidated)
Combines General, Utility, Steal, Info, Snipe, AFK, and Settings (prefix, token management).
Includes paginated help menu with clean block-quote UI.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import platform
import random
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from dotenv import set_key

from config import settings
from footprint_handlers import footprint
from ui import log_info, log_warn, log_err

ENV_PATH = Path(".env")
CUSTOM_EMOJI_RE = re.compile(r"<(a)?:([a-zA-Z0-9_]+):([0-9]+)>")


@dataclass
class SniperRecord:
    content: str
    author: str
    author_id: int
    avatar: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    before: str | None = None
    attachments: list[str] = field(default_factory=list)


def _fmt_uptime(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def _badges(user: discord.User) -> str:
    flags = user.public_flags
    badges = []
    if flags.staff:
        badges.append("👨‍💼 Staff")
    if flags.partner:
        badges.append("🤝 Partner")
    if flags.hypesquad:
        badges.append("🏠 HypeSquad")
    if flags.bug_hunter:
        badges.append("🐛 Bug Hunter")
    if flags.early_supporter:
        badges.append("💜 Early Supporter")
    if flags.verified_bot_developer:
        badges.append("🤖 Bot Dev")
    if flags.active_developer:
        badges.append("👨‍💻 Active Dev")
    return "  ".join(badges) if badges else "—"


class Utility(commands.Cog):
    """Core controls, help, presence inspection, steal, settings & general tools."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._deleted: dict[int, deque[SniperRecord]] = defaultdict(lambda: deque(maxlen=10))
        self._edited: dict[int, deque[SniperRecord]] = defaultdict(lambda: deque(maxlen=10))
        self._afk_active: bool = False
        self._afk_reason: str = ""

    # ── General & Core Controls ────────────────────────────────────────────────

    @commands.command(name="ping", aliases=["p"])
    async def ping(self, ctx: commands.Context) -> None:
        """Check WebSocket and gateway latency."""
        await ctx.message.delete()
        lat = round(self.bot.latency * 1000)
        msg = await ctx.send(f"🌐 **Pong!** `{lat}ms`")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    @commands.command(name="uptime", aliases=["up"])
    async def uptime(self, ctx: commands.Context) -> None:
        """Show how long Globe has been running."""
        await ctx.message.delete()
        up = _fmt_uptime(self.bot.uptime_seconds)
        msg = await ctx.send(f"⏱️ **Uptime:** `{up}`")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    @commands.command(name="about", aliases=["info", "globe"])
    async def about(self, ctx: commands.Context) -> None:
        """Display Globe system diagnostics and runtime architecture."""
        await ctx.message.delete()
        lat = round(self.bot.latency * 1000)
        up = _fmt_uptime(self.bot.uptime_seconds)
        mods = len(self.bot._loaded_modules) if hasattr(self.bot, "_loaded_modules") else "?"
        cmds = len([c for c in self.bot.commands if not c.hidden])
        lines = [
            f"**🌐 Globe Selfbot**",
            f"",
            f"**prefix** `{settings.prefix}`  **latency** `{lat}ms`  **uptime** `{up}`",
            f"**modules** `{mods}`  **commands** `{cmds}`",
            f"**python** `{platform.python_version()}`  **discord.py-self** `{discord.__version__}`",
        ]
        msg = await ctx.send("\n".join(lines))
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    @commands.command(name="reload", aliases=["rl"])
    async def reload(self, ctx: commands.Context, module: str) -> None:
        """Hot-reload a module from disk without restarting."""
        if not self.bot.is_owner_id(ctx.author.id):
            return
        await ctx.message.delete()
        from core.loader import ModuleLoader
        loader = ModuleLoader(self.bot)
        ok = await loader.reload(module)
        status = "✅ reloaded" if ok else "❌ failed"
        msg = await ctx.send(f"{status} `{module}`")
        await msg.delete(delay=4)

    @commands.command(name="restart", aliases=["reboot", "rb"])
    async def restart(self, ctx: commands.Context) -> None:
        """Restart the Globe selfbot process."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        lines = [
            "> `-` **Globe Selfbot — Rebooting System**",
            "> `—` **Trigger:** Process restart initiated by owner",
            "> `—` **Runtime:** Relaunching Python interpreter instance",
            "> `•` *Rebooting now…*",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        msg = await ctx.send("\n".join(lines))
        await asyncio.sleep(1.0)
        try:
            await self.bot.close()
        except Exception:
            pass
        import os, sys
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(name="update", aliases=["upgrade", "gitpull", "hotreload", "pull"])
    async def update(self, ctx: commands.Context) -> None:
        """
        Pull latest commits from GitHub and hot-restart all modules in memory without stopping or dropping Rich Presence.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        status_msg = await ctx.send(
            "> `—` **Connecting to GitHub repository & checking upstream commits…**"
        )

        import subprocess
        from core.loader import ModuleLoader
        from pathlib import Path

        repo_root = Path(__file__).parent.parent
        git_dir = repo_root / ".git"

        if not git_dir.exists():
            await status_msg.edit(content="> `!` **Git Error:** No local `.git` repository detected.")
            await status_msg.delete(delay=6)
            return

        old_commit = "unknown"
        try:
            old_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo_root),
                text=True,
                timeout=5,
            ).strip()
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        def _run_git_pull() -> tuple[int, str, str]:
            res = subprocess.run(
                ["git", "pull", "--ff-only", "origin", "main"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()

        try:
            code, stdout, stderr = await loop.run_in_executor(None, _run_git_pull)
        except Exception as e:
            await status_msg.edit(content=f"> `!` **Git Pull Failed:** `{e}`")
            await status_msg.delete(delay=6)
            return

        if code != 0:
            err_msg = stderr or stdout or "Conflict or network failure"
            await status_msg.edit(content=f"> `!` **Git Pull Error:** `{err_msg[:200]}`")
            await status_msg.delete(delay=8)
            return

        new_commit = old_commit
        try:
            new_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo_root),
                text=True,
                timeout=5,
            ).strip()
        except Exception:
            pass

        # Hot-restart all modules in memory without stopping or dropping gateway connection
        loader = ModuleLoader(self.bot)
        all_mods = await loader.load_all()
        target_mods = list(self.bot._loaded_modules or all_mods)
        reloaded: list[str] = []
        failed: list[str] = []
        for m in target_mods:
            ok = await loader.reload(m)
            if ok:
                reloaded.append(m)
            else:
                failed.append(m)

        # Re-synchronize official Globe Rich Presence (RPC) & Status to ensure uninterrupted broadcast
        rpc_synced = False
        try:
            if status_cog := self.bot.get_cog("Status"):
                if hasattr(status_cog, "apply_default_rpc"):
                    await status_cog.apply_default_rpc()
                    rpc_synced = True
        except Exception as e:
            log_err(f"RPC re-sync error after hot update: {e}")

        is_fresh = old_commit != new_commit
        state_title = "Globe Selfbot — Updated & Hot-Restarted" if is_fresh else "Globe Selfbot — Up to Date & Refreshed"
        summary_line = stdout.splitlines()[-1] if stdout else "Up to date"
        rpc_note = "Active & Synchronized (0s downtime)" if rpc_synced else "Gateway presence active"

        lines = [
            f"> `-` **{state_title}**",
            f"> `—` **Commit State:** `{old_commit}` → `{new_commit}` (`origin/main`)",
            f"> `—` **Git Result:** `{summary_line}`",
            f"> `—` **Hot Restart:** `{len(reloaded)}` modules reloaded in-memory",
            f"> `—` **Process State:** Zero downtime · Connection & Gateway intact",
            f"> `—` **Rich Presence (RPC):** {rpc_note}",
            "> `•` *Live update completed without killing process or losing state.*",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        await status_msg.edit(content="\n".join(lines))
        await status_msg.delete(delay=12)

    @commands.command(name="modules", aliases=["mods"])
    async def modules(self, ctx: commands.Context) -> None:
        """List active modules in priority order."""
        await ctx.message.delete()
        ordered = ["Utility", "Moderation", "Tools", "Troll", "Fun", "Status", "Voice"]
        active = [m for m in ordered if m in self.bot.cogs]
        listed = "  ".join(f"`{m}`" for m in active)
        msg = await ctx.send(f"📦 **Active Modules ({len(active)}):** {listed}")
        if settings.auto_delete_delay:
            await msg.delete(delay=settings.auto_delete_delay)

    # ── Paginated Help Menu ───────────────────────────────────────────────────

    @commands.command(name="help", aliases=["h", "cmds", "commands"])
    async def help_cmd(self, ctx: commands.Context, module: Optional[str] = None, page: Optional[int] = 1) -> None:
        """
        Show all modules or detailed paginated commands for a module.
        Syntax: `g.help [module] [page]`
        """
        await ctx.message.delete()
        p = settings.prefix

        # Desired UI module priority order
        ORDERED_MODULES = [
            ("Utility", "General controls, help, inspection, text tools, steal, snipe, AFK & settings"),
            ("Moderation", "Kicks, bans, unbans, timeouts, nicknames, nuke, slowmode & role management"),
            ("Tools", "Encodings, cryptographic hashes, weather, nitro sniper, auto-reply & auto-react"),
            ("Troll", "Ghost pings, spam controls, mass mentions, fake typing & prank scripts"),
            ("Fun", "8ball, roast, ship, dice, coinflip, deterministic ratings, pp size & jokes"),
            ("Status", "Custom Rich Presence activities (stream, play, listen, watch) and online states"),
            ("Voice", "Voice state inspection, guild voice directory & occupancy, kick from voice"),
        ]

        if not module:
            # Main modules overview in exact requested order
            lines = [
                f"> `-` **Welcome to Globe! The most complete, lightweight, and modern all-in-one Discord selfbot.**",
                f"> Built with precision on `discord.py-self`, Globe gives you effortless control over your account with an ultra-clean block-quote UI, intelligent anti-detection footprint safeguards, and modular architecture.\n",
                f"**Modules Overview (`{len(ORDERED_MODULES)}` Active Modules)**\n",
            ]
            for name, desc in ORDERED_MODULES:
                if name in self.bot.cogs:
                    lines.append(f"> `—` **`{name.lower()}`**")
                    lines.append(f"> {desc}\n")

            lines.extend([
                f"**__Want To Inspect A Specific Module?__**",
                f"Run **`{p}help <module> [page]`** (e.g., `{p}h moderation` or `{p}h utility 2`) to view the command checklist.\n",
                f"> `•` **__Make Sure To Give It A Try!__**",
                f"> `°` **__Globe__ — Shaping Modern Selfbot Architecture. Minimal, Clean & Fast.**",
            ])
            await ctx.send("\n".join(lines))
            return

        # Handle numeric first arg like `g.h 2` -> treat as general overview or check if module name
        target_name = module.strip().lower()
        matched_cog = None
        for name, cog in self.bot.cogs.items():
            if name.lower() == target_name:
                matched_cog = cog
                break

        if not matched_cog:
            msg = await ctx.send(f"❌ No module found named `{module}`. Use `{p}help` to view all available modules.")
            await msg.delete(delay=5)
            return

        cog_cmds = [c for c in matched_cog.get_commands() if not c.hidden]
        sorted_cmds = sorted(cog_cmds, key=lambda c: c.name)

        # Chunk into pages (6 commands per page keeps blocks within safe 2000 char limits without cutting descriptions)
        PER_PAGE = 6
        total_pages = max(1, (len(sorted_cmds) + PER_PAGE - 1) // PER_PAGE)
        current_page = max(1, min(page or 1, total_pages))

        start_idx = (current_page - 1) * PER_PAGE
        page_cmds = sorted_cmds[start_idx:start_idx + PER_PAGE]

        lines = [
            f"> `-` **Globe Selfbot — Module: __{matched_cog.qualified_name}__** (Page {current_page}/{total_pages})",
            f"> Showing `{len(page_cmds)}` of `{len(sorted_cmds)}` commands. Prefix: `{p}`\n",
            f"**__Available Commands__**\n",
        ]

        for c in page_cmds:
            aliases_str = f" (aliases: `{'`, `'.join(c.aliases)}`)" if c.aliases else ""
            desc = c.brief or c.help or "No description provided."
            sig = f" {c.signature}" if c.signature else ""
            lines.append(f"> `—` **`{p}{c.name}{sig}`**{aliases_str}")
            lines.append(f"> {desc}\n")

        if total_pages > 1:
            lines.append(f"> `•` **Navigation:** Use `{p}h {matched_cog.qualified_name.lower()} <page>` (e.g. `{p}h {matched_cog.qualified_name.lower()} {min(current_page + 1, total_pages)}`)")
        else:
            lines.append(f"> `•` **Tip:** Arguments inside `<>` are required, `[]` are optional.")
        lines.append(f"> `°` **__Globe__ — Minimal, Clean, Polished Architecture.**")

        await ctx.send("\n".join(lines))

    # ── Settings Commands ──────────────────────────────────────────────────────

    @commands.command(name="setprefix", aliases=["prefix", "changeprefix"])
    async def setprefix(self, ctx: commands.Context, new_prefix: str) -> None:
        """Change the command prefix in memory and save to .env."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        clean_p = new_prefix.strip()
        if not clean_p:
            await ctx.send("❌ Prefix cannot be empty.", delete_after=4)
            return

        old_prefix = settings.prefix
        settings.prefix = clean_p
        self.bot.command_prefix = clean_p

        try:
            if not ENV_PATH.exists():
                ENV_PATH.write_text("")
            set_key(str(ENV_PATH), "PREFIX", clean_p)
        except Exception as e:
            log_err(f"Failed to persist prefix to .env: {e}")

        await ctx.send(f"✅ Prefix updated from `{old_prefix}` to `{clean_p}`.", delete_after=5)
        log_info(f"Prefix changed to {clean_p}")

    @commands.command(name="settoken", aliases=["changetoken"])
    async def settoken(self, ctx: commands.Context, new_token: str) -> None:
        """Change and update the Discord token stored in .env."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        clean_tok = new_token.strip().strip("'\"")
        if len(clean_tok) < 50:
            await ctx.send("❌ Token is too short to be valid.", delete_after=4)
            return

        settings.discord_token = clean_tok
        from auth_handlers import auth
        auth._token = clean_tok

        try:
            if not ENV_PATH.exists():
                ENV_PATH.write_text("")
            set_key(str(ENV_PATH), "DISCORD_TOKEN", clean_tok)
        except Exception as e:
            log_err(f"Failed to write token to .env: {e}")

        await ctx.send(f"✅ Token updated to: `{auth.masked()}` (Restart required to apply session).", delete_after=5)
        log_info(f"Token updated to {auth.masked()}")

    @commands.command(name="addtoken")
    async def addtoken(self, ctx: commands.Context, token_str: str) -> None:
        """Add/save a token to .env if not currently configured."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        clean_tok = token_str.strip().strip("'\"")
        if len(clean_tok) < 50:
            await ctx.send("❌ Token is too short to be valid.", delete_after=4)
            return

        settings.discord_token = clean_tok
        from auth_handlers import auth
        auth._token = clean_tok
        auth._persist_token(clean_tok)

        await ctx.send(f"✅ Token registered to `.env` & `token.txt`: `{auth.masked()}`.", delete_after=5)

    @commands.command(name="removetoken", aliases=["deltoken", "cleartoken"])
    async def removetoken(self, ctx: commands.Context, target_token: Optional[str] = None) -> None:
        """Remove a token from .env and token.txt (pass token or omit to remove active token)."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        from auth_handlers import auth
        tok_to_remove = target_token.strip().strip("'\"") if target_token else settings.discord_token

        if target_token:
            auth.remove_token_from_file(tok_to_remove)
            await ctx.send(f"🧹 Token removed from `token.txt`.", delete_after=5)
            return

        settings.discord_token = ""
        auth._token = ""
        auth.remove_token_from_file(tok_to_remove)

        try:
            if ENV_PATH.exists():
                set_key(str(ENV_PATH), "DISCORD_TOKEN", "")
        except Exception as e:
            log_err(f"Failed to clear token in .env: {e}")

        await ctx.send("🧹 Active token cleared from `.env` and `token.txt`.", delete_after=5)
        log_warn("Discord token cleared from configuration")

    @commands.command(name="tokens", aliases=["listtokens", "tokenslist"])
    async def tokens(self, ctx: commands.Context) -> None:
        """List all accounts and tokens saved in token.txt."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        from auth_handlers import auth
        all_tokens = auth.get_saved_tokens()
        if not all_tokens:
            await ctx.send("📋 No tokens currently stored in `token.txt`.", delete_after=5)
            return

        lines = [f"> `-` **Stored Tokens in `token.txt` ({len(all_tokens)})**"]
        for idx, t in enumerate(all_tokens, 1):
            uid = auth.extract_user_id(t)
            masked = t[:6] + "●" * 14 + t[-4:]
            active_marker = " *(Active)*" if t == settings.discord_token else ""
            lines.append(f"**{idx}.** User `{uid or 'Unknown'}`: `{masked}`{active_marker}")

        lines.append(f"\n*Switch active token anytime with `{settings.prefix}settoken <token>`*")
        await ctx.send("\n".join(lines), delete_after=20)

    @commands.command(name="mytoken", aliases=["showtoken", "curtoken"])
    async def mytoken(self, ctx: commands.Context) -> None:
        """
        Inspect the active session token with interactive confirmation.
        Prompts 'Are you sure?' before rendering the token in copy-paste format.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        from auth_handlers import auth
        active_tok = auth.token or getattr(self.bot.http, "token", "") or settings.discord_token
        if not active_tok:
            await ctx.send("❌ No active token found in memory or environment.", delete_after=5)
            return

        prompt_msg = await ctx.send(
            "> `-` **Active Account Security Prompt**\n"
            "> `—` **Warning:** Revealing your active account token gives full access to your account.\n"
            "> `—` **Are you sure you want to display your current token?**\n"
            "> `•` *Type `yes` or `y` in this channel within 15 seconds to confirm.*"
        )

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            confirm_msg = await self.bot.wait_for("message", check=check, timeout=15.0)
            user_reply = confirm_msg.content.strip().lower()
            try:
                await confirm_msg.delete()
            except Exception:
                pass

            if user_reply in ("yes", "y"):
                user_id = self.bot.user.id if self.bot.user else auth.extract_user_id(active_tok)
                user_name = str(self.bot.user) if self.bot.user else "Selfbot Account"
                masked = active_tok[:6] + "●" * 16 + active_tok[-4:]

                lines = [
                    f"> `-` **Current Account Token**",
                    f"> `—` **Account:** **{user_name}** (`{user_id}`)",
                    f"> `—` **Preview:** `{masked}`",
                    f"> `—` **Copy-Paste Block:**",
                    f"```{active_tok}```",
                    f"> `•` *Auto-deleting in 30 seconds for your safety.*",
                    f"> `°` **__Globe__ — Minimal, Clean & Secure Architecture.**",
                ]
                await prompt_msg.edit(content="\n".join(lines))
                await prompt_msg.delete(delay=30)
            else:
                await prompt_msg.edit(content="> `—` **Action cancelled.** Token was not displayed.")
                await prompt_msg.delete(delay=5)
        except asyncio.TimeoutError:
            await prompt_msg.edit(content="> `—` **Confirmation timed out.** Token was not displayed.")
            await prompt_msg.delete(delay=5)

    @commands.command(name="vault", aliases=["encrypttoken", "tokenvault"])
    async def vault_cmd(self, ctx: commands.Context, action: str = "status", *, passphrase: str | None = None) -> None:
        """
        Manage encrypted token vault (AES-256-GCM + PBKDF2).
        Usage: g.vault status or g.vault encrypt <one_time_startup_key>
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        from auth_handlers import auth
        from core import vault

        act = action.lower()
        if act in ("status", "info"):
            raw_token = settings.discord_token
            is_enc = vault.is_encrypted(raw_token)
            status_badge = "`ENCRYPTED (AES-256-GCM)`" if is_enc else "`PLAINTEXT (Unprotected)`"
            lines = [
                "> `-` **Globe Vault — Token Security Status**",
                f"> `—` **Storage Format:** {status_badge}",
                "> `—` **Cipher:** AES-256-GCM authenticated encryption",
                "> `—` **Key Derivation:** PBKDF2-HMAC-SHA256 (480,000 rounds)",
                "> `—` **Memory Lifecycle:** Plaintext exists only in RAM; never leaves process",
                f"> `•` *To lock token on disk: `{settings.prefix}vault encrypt <passphrase>`*",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
            msg = await ctx.send("\n".join(lines))
            await msg.delete(delay=10)
            return

        if act in ("encrypt", "lock"):
            if not passphrase:
                msg = await ctx.send(f"> `!` **Usage:** `{settings.prefix}vault encrypt <startup_passphrase>`")
                await msg.delete(delay=5)
                return

            try:
                enc = auth.encrypt_current_token(passphrase.strip())
                lines = [
                    "> `-` **Globe Vault — Token Encrypted Successfully**",
                    "> `—` **Status:** Plaintext token erased from `.env` and `token.txt`",
                    f"> `—` **Ciphertext:** `{enc[:32]}…`",
                    "> `—` **Next Launch:** Bot will require your one-time startup key (`--key` or prompt)",
                    "> `•` *Your token is now 100% immune to VPS disk dumps or file inspection.*",
                    "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
                ]
                msg = await ctx.send("\n".join(lines))
                await msg.delete(delay=12)
            except Exception as e:
                msg = await ctx.send(f"> `!` **Vault Encryption Failed:** `{e}`")
                await msg.delete(delay=5)

    @commands.command(name="gettoken", aliases=["extracttoken", "mobiletoken", "fetchtoken"])
    async def gettoken(self, ctx: commands.Context, email: str, *, password: str) -> None:
        """
        Authenticate directly with Discord to extract account token on mobile without a PC.
        Syntax: `g.gettoken <email/phone> <password>`
        Deletes invocation immediately to preserve credentials.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        from ext_token import TokenExtractor
        extractor = TokenExtractor()

        status_msg = await ctx.send("🔄 **Contacting Discord authentication gateway via Android client emulation…**")

        async def _in_chat_mfa_prompt(prompt_text: str) -> str:
            await status_msg.edit(content=f"{prompt_text}\n*Reply with your code in chat within 60 seconds.*")

            def check(m: discord.Message) -> bool:
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                code_msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                code_val = code_msg.content.strip()
                try:
                    await code_msg.delete()
                except Exception:
                    pass
                return code_val
            except asyncio.TimeoutError:
                return ""

        result = await extractor.authenticate(email, password, mfa_prompt=_in_chat_mfa_prompt)

        if result.success and result.token:
            masked = result.token[:6] + "●" * 16 + result.token[-4:]
            lines = [
                f"> `-` **Mobile Token Extractor: Extraction Successful**",
                f"**• Account User ID:** `{result.user_id or 'Resolved'}`",
                f"**• Masked Preview:** `{masked}`",
                f"**• Raw Token:** ||`{result.token}`|| *(Click spoiler to reveal)*",
                f"\n*You can save this directly into `.env` using `g.settoken <token>`*",
            ]
            await status_msg.edit(content="\n".join(lines))
        else:
            if result.requires_passkey_only:
                await status_msg.edit(content=f"⚠️ **Passkey Barrier:** {result.error}")
            else:
                await status_msg.edit(content=f"❌ **Extraction Failed:** {result.error}")

    @commands.command(name="noprefix", aliases=["np"])
    async def noprefix(self, ctx: commands.Context, duration: Optional[str] = None) -> None:
        """
        Toggle No-Prefix mode on or off. Optional duration (e.g. `g.np 10m` or `g.np 1h`).
        If enabled, commands trigger directly (e.g. `ping`, `ui`).
        Sentences like 'ban this guy' or 'bro kick him' are safely ignored.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        import time
        from modules.tools import _parse_duration

        if self.bot._no_prefix_enabled and not duration:
            # Toggle off
            self.bot._no_prefix_enabled = False
            self.bot._no_prefix_until = None
            await ctx.send("🔴 **No-Prefix mode:** `DISABLED`", delete_after=5)
            log_info("No-prefix mode disabled.")
            return

        # Toggle on or set duration
        self.bot._no_prefix_enabled = True
        duration_desc = "Indefinite (until toggled off)"

        if duration:
            secs = _parse_duration(duration)
            if secs:
                self.bot._no_prefix_until = time.monotonic() + secs
                duration_desc = f"`{duration}` (auto-disables after {duration})"
            else:
                self.bot._no_prefix_until = None
        else:
            self.bot._no_prefix_until = None

        await ctx.send(f"🟢 **No-Prefix mode:** `ENABLED` — Duration: {duration_desc}\n*Commands trigger directly on first word (e.g. `ui`, `ping`). Sentences like 'ban this guy' are ignored.*", delete_after=8)
        log_info(f"No-prefix mode enabled ({duration_desc}).")

    # ── Steal Utilities ───────────────────────────────────────────────────────

    @commands.command(name="steal", aliases=["stealemoji", "se"])
    async def steal(self, ctx: commands.Context, emoji_input: str, name: str | None = None) -> None:
        """Steal a custom Discord emoji into current server or extract source link."""
        await ctx.message.delete()
        match = CUSTOM_EMOJI_RE.search(emoji_input)
        if not match:
            msg = await ctx.send("❌ Provide a valid custom Discord emoji (e.g., `<:name:id>` or `<a:name:id>`).")
            await msg.delete(delay=5)
            return

        is_animated = bool(match.group(1))
        default_name = match.group(2)
        emoji_id = match.group(3)
        target_name = name or default_name

        ext = "gif" if is_animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=1024"

        if ctx.guild and ctx.guild.me and ctx.guild.me.guild_permissions.manage_emojis_and_stickers:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            new_emoji = await ctx.guild.create_custom_emoji(name=target_name, image=data)
                            await ctx.send(f"✅ Added {new_emoji} as `:{target_name}:` to **{ctx.guild.name}**!")
                            return
            except Exception as e:
                log_err(f"Failed to add emoji: {e}")

        await ctx.send(f"🖼️ **Stolen Emoji ({target_name}):**\n{url}")

    @commands.command(name="stealsticker", aliases=["ss"])
    async def stealsticker(self, ctx: commands.Context) -> None:
        """Steal the sticker from the message you replied to."""
        await ctx.message.delete()
        ref = ctx.message.reference
        if not ref or not ref.message_id:
            msg = await ctx.send("❌ Reply to a message containing a sticker.")
            await msg.delete(delay=5)
            return

        try:
            target_msg = await ctx.channel.fetch_message(ref.message_id)
        except Exception:
            msg = await ctx.send("❌ Could not fetch replied message.")
            await msg.delete(delay=5)
            return

        if not target_msg.stickers:
            msg = await ctx.send("❌ The replied message does not contain a sticker.")
            await msg.delete(delay=5)
            return

        sticker = target_msg.stickers[0]
        url = sticker.url

        if ctx.guild and ctx.guild.me and ctx.guild.me.guild_permissions.manage_emojis_and_stickers and sticker.format != discord.StickerFormatType.lottie:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            file = discord.File(data, filename=f"{sticker.name}.png")
                            new_sticker = await ctx.guild.create_sticker(
                                name=sticker.name,
                                description=sticker.description or "Stolen with Globe",
                                emoji="⭐",
                                file=file,
                            )
                            await ctx.send(f"✅ Added sticker **{new_sticker.name}** to **{ctx.guild.name}**!")
                            return
            except Exception as e:
                log_err(f"Failed to add sticker: {e}")

        await ctx.send(f"🖼️ **Sticker:** `{sticker.name}` (`{sticker.id}`)\n{url}")

    # ── Text & Message Tools ──────────────────────────────────────────────────

    @commands.command(name="say", aliases=["s", "echo"])
    async def say(self, ctx: commands.Context, *, text: str) -> None:
        """Echo a message and delete your command invocation."""
        await ctx.message.delete()
        await ctx.send(text)

    @commands.command(name="mock")
    async def mock(self, ctx: commands.Context, *, text: str) -> None:
        """AlTeRnAtInG cAsE mocking text."""
        await ctx.message.delete()
        result = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text))
        await ctx.send(result)

    @commands.command(name="reverse", aliases=["rev"])
    async def reverse(self, ctx: commands.Context, *, text: str) -> None:
        """Reverse the given text."""
        await ctx.message.delete()
        await ctx.send(text[::-1])

    @commands.command(name="clap")
    async def clap(self, ctx: commands.Context, *, text: str) -> None:
        """Add 👏 between every word."""
        await ctx.message.delete()
        await ctx.send(" 👏 ".join(text.split()))

    @commands.command(name="uwu", aliases=["owo"])
    async def uwu(self, ctx: commands.Context, *, text: str) -> None:
        """UwU / OwO text styler."""
        await ctx.message.delete()
        result = text.replace("r", "w").replace("l", "w").replace("R", "W").replace("L", "W")
        result = re.sub(r"n([aeiou])", r"ny\1", result)
        result = re.sub(r"N([aeiou])", r"Ny\1", result)
        suffixes = [" uwu", " owo", " >w<", " :3", " ✨"]
        await ctx.send(result + random.choice(suffixes))

    @commands.command(name="vaporwave", aliases=["vaporise", "vaporize"])
    async def vaporwave(self, ctx: commands.Context, *, text: str) -> None:
        """Convert text into full-width ｖａｐｏｒｗａｖｅ characters."""
        await ctx.message.delete()
        result = ""
        for char in text:
            code = ord(char)
            if 0x21 <= code <= 0x7E:
                result += chr(code + 0xFEE0)
            elif code == 0x20:
                result += chr(0x3000)
            else:
                result += char
        await ctx.send(result)

    @commands.command(name="big", aliases=["emojify"])
    async def big(self, ctx: commands.Context, *, text: str) -> None:
        """Convert text into regional indicator emoji blocks."""
        await ctx.message.delete()
        result = ""
        for c in text.lower():
            if c.isalpha():
                result += f":regional_indicator_{c}: "
            elif c == " ":
                result += "   "
            else:
                result += f"{c} "
        await ctx.send(result)

    @commands.command(name="rand", aliases=["random", "rng"])
    async def rand(self, ctx: commands.Context, low: int = 1, high: int = 100) -> None:
        """Generate a random number in range [low] to [high]."""
        await ctx.message.delete()
        if low > high:
            low, high = high, low
        await ctx.send(f"🎲 `{random.randint(low, high)}` (range: {low}–{high})", delete_after=6)

    @commands.command(name="choose", aliases=["pick"])
    async def choose(self, ctx: commands.Context, *, options: str) -> None:
        """Pick an option from comma-separated choices: `g.choose pizza, burger, tacos`."""
        await ctx.message.delete()
        choices = [o.strip() for o in options.split(",") if o.strip()]
        if not choices:
            await ctx.send("❌ Provide comma-separated options.", delete_after=4)
            return
        await ctx.send(f"🎯 **{random.choice(choices)}**", delete_after=8)

    @commands.command(name="copy")
    async def copy(self, ctx: commands.Context, msg_id: int) -> None:
        """Fetch and duplicate a message by ID into current channel."""
        await ctx.message.delete()
        try:
            target = await ctx.channel.fetch_message(msg_id)
            await ctx.send(target.content or "(Message contains no text content)")
        except Exception:
            await ctx.send("❌ Could not fetch message.", delete_after=4)

    # ── Advanced Information Lookups ───────────────────────────────────────────

    @commands.command(name="userinfo", aliases=["ui", "whois", "user"])
    async def userinfo(self, ctx: commands.Context, *, user: discord.Member | discord.User | None = None) -> None:
        """Display comprehensive, advanced account inspection data for a target user or yourself."""
        await ctx.message.delete()
        target = user or ctx.author
        created = discord.utils.format_dt(target.created_at, style="F") + f" ({discord.utils.format_dt(target.created_at, style='R')})"

        # Status & Client platforms
        status_emoji = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🟡 Idle",
            discord.Status.dnd: "🔴 Do Not Disturb",
            discord.Status.offline: "⚪ Offline / Invisible",
        }

        lines = [
            f"> `-` **Account Inspection: __{target}__** (`{target.id}`)",
            f"**• Account Created:** {created}",
            f"**• Bot Account:** {'Yes' if target.bot else 'No'}",
            f"**• Profile Badges:** {_badges(target)}",
        ]

        if isinstance(target, discord.Member):
            joined = discord.utils.format_dt(target.joined_at, style="F") + f" ({discord.utils.format_dt(target.joined_at, style='R')})" if target.joined_at else "—"
            top_role = target.top_role.mention if target.top_role.id != ctx.guild.id else "@everyone"
            user_status = status_emoji.get(target.status, str(target.status).title())

            # Devices / Client types
            devices = []
            if getattr(target, "desktop_status", None) and target.desktop_status != discord.Status.offline:
                devices.append("Desktop 💻")
            if getattr(target, "mobile_status", None) and target.mobile_status != discord.Status.offline:
                devices.append("Mobile 📱")
            if getattr(target, "web_status", None) and target.web_status != discord.Status.offline:
                devices.append("Web 🌐")
            client_str = " | ".join(devices) if devices else "None detected"

            # Boosting info
            boosting_since = discord.utils.format_dt(target.premium_since, style="R") if getattr(target, "premium_since", None) else "Not boosting"

            # Roles list (top 8)
            member_roles = [r.mention for r in target.roles if not r.is_default()]
            roles_str = ", ".join(reversed(member_roles[:8])) if member_roles else "None"
            if len(member_roles) > 8:
                roles_str += f" *(+{len(member_roles) - 8} more)*"

            lines.extend([
                f"**• Server Joined:** {joined}",
                f"**• Top Role:** {top_role}",
                f"**• Nickname:** {target.display_name}",
                f"**• Status & Platform:** {user_status} ({client_str})",
                f"**• Server Booster:** {boosting_since}",
                f"**• Roles ({len(member_roles)}):** {roles_str}",
            ])

        # Query local SQLite message activity tracker
        from data.tracker import tracker
        stats = tracker.get_stats(target.id, ctx.guild.id if ctx.guild else None)
        if ctx.guild:
            lines.append(f"**• Activity Track:** `{stats['guild_all']}` msgs in this guild (`{stats['guild_today']}` today) | `{stats['global_all']}` global")
        else:
            lines.append(f"**• Activity Track:** `{stats['global_all']}` msgs global (`{stats['global_today']}` today)")

        # High-res Avatar & Banner link
        av_url = target.display_avatar.url
        banner_url = getattr(target, "banner", None).url if getattr(target, "banner", None) else None
        links = [f"[Avatar]({av_url})"]
        if banner_url:
            links.append(f"[Banner]({banner_url})")
        lines.append(f"**• Media:** {' · '.join(links)}")

        await ctx.send("\n".join(lines))

    @commands.command(name="serverinfo", aliases=["si", "guild", "server"])
    async def serverinfo(self, ctx: commands.Context) -> None:
        """Display advanced server analytics, breakdown, roles, channels, and vanity stats."""
        await ctx.message.delete()
        g = ctx.guild
        if not g:
            await ctx.send("❌ Not inside a server.", delete_after=4)
            return

        created = discord.utils.format_dt(g.created_at, style="F") + f" ({discord.utils.format_dt(g.created_at, style='R')})"
        vanity = f" | **Vanity:** `{g.vanity_invite}`" if getattr(g, "vanity_invite", None) else ""

        # Channels breakdown
        text_count = len(g.text_channels)
        voice_count = len(g.voice_channels)
        categories = len(g.categories)

        # Member counts (bots vs humans)
        bots = sum(1 for m in g.members if m.bot)
        humans = g.member_count - bots if g.member_count else len(g.members) - bots

        # Security & Verification
        sec_levels = {
            discord.VerificationLevel.none: "None (Unrestricted)",
            discord.VerificationLevel.low: "Low (Must have verified email)",
            discord.VerificationLevel.medium: "Medium (Registered > 5m)",
            discord.VerificationLevel.high: "High (Member of server > 10m)",
            discord.VerificationLevel.highest: "Highest (Must have verified phone)",
        }
        verif = sec_levels.get(g.verification_level, str(g.verification_level))

        # Server Features (top 6 highlighted)
        features_list = [f.lower().replace("_", " ").title() for f in g.features[:6]]
        features_str = ", ".join(features_list) if features_list else "Standard Guild"

        lines = [
            f"> `-` **Server Intelligence: __{g.name}__** (`{g.id}`){vanity}",
            f"**• Server Owner:** <@{g.owner_id}>",
            f"**• Created:** {created}",
            f"**• Members ({g.member_count}):** `{humans}` Humans | `{bots}` Bots",
            f"**• Channel Layout:** `{text_count}` Text | `{voice_count}` Voice | `{categories}` Categories",
            f"**• Roles & Emojis:** `{len(g.roles)}` Roles | `{len(g.emojis)}` Emojis | `{len(getattr(g, 'stickers', []))}` Stickers",
            f"**• Boost Metrics:** Tier `{g.premium_tier}` (`{g.premium_subscription_count}` boosts)",
            f"**• Verification Level:** {verif}",
            f"**• Enabled Features:** {features_str}",
        ]

        if g.icon:
            lines.append(f"**• Server Icon:** [Open Image]({g.icon.url})")

        await ctx.send("\n".join(lines))

    @commands.command(name="messages", aliases=["msgs", "msg"])
    async def messages(self, ctx: commands.Context, target: Optional[discord.User] = None, scope: Optional[str] = None) -> None:
        """
        Check tracked messages count.
        Syntax: `g.msg [user] [global/server]` (e.g. `g.msg`, `g.msg global`, `g.msg @user`)
        """
        await ctx.message.delete()
        from data.tracker import tracker

        user_target = target or ctx.author
        stats = tracker.get_stats(user_target.id, ctx.guild.id if ctx.guild else None)

        is_global = (scope and scope.lower() == "global") or (target and str(target).lower() == "global") or not ctx.guild

        if is_global:
            lines = [
                f"📊 **Global Message Stats for __{user_target}__**",
                f"• **All-time Across All Servers & DMs:** `{stats['global_all']}` msgs",
                f"• **Sent Today (Global):** `{stats['global_today']}` msgs",
                f"• **Direct Messages (DMs):** `{stats['dms_all']}` msgs (`{stats['dms_today']}` today)",
            ]
        else:
            lines = [
                f"📊 **Server Message Stats for __{user_target}__** ({ctx.guild.name})",
                f"• **All-time in This Server:** `{stats['guild_all']}` msgs",
                f"• **Sent in This Server Today:** `{stats['guild_today']}` msgs",
                f"• **Global All-time:** `{stats['global_all']}` msgs (`{stats['global_today']}` today)",
            ]

        await ctx.send("\n".join(lines), delete_after=15)

    @commands.command(name="invites", aliases=["invs", "inv"])
    async def invites(self, ctx: commands.Context, scope: Optional[str] = None) -> None:
        """
        Check active invites for current server or globally across all your servers.
        Syntax: `g.inv [global]`
        """
        await ctx.message.delete()

        if scope and scope.lower() == "global":
            # Global invites inspection across all guilds
            lines = ["🌐 **Global Invites Directory:**"]
            total_invites = 0
            for g in self.bot.guilds[:15]:
                try:
                    if g.me.guild_permissions.manage_guild:
                        g_invites = await g.invites()
                        if g_invites:
                            total_invites += len(g_invites)
                            top = g_invites[0]
                            lines.append(f"• **{g.name}:** `{len(g_invites)}` invites (e.g. `{top.url}` uses: `{top.uses}`) ")
                except Exception:
                    pass

            if total_invites == 0:
                await ctx.send("📋 No accessible invites found across servers (requires Manage Server perms).", delete_after=5)
                return

            await ctx.send("\n".join(lines[:12]), delete_after=20)
            return

        # Server-side invites
        if not ctx.guild:
            await ctx.send("❌ Not inside a server. Use `g.inv global` to inspect all servers.", delete_after=5)
            return

        try:
            if not ctx.guild.me.guild_permissions.manage_guild:
                # Fallback to vanity or single invite if no manage perms
                if ctx.guild.vanity_invite:
                    await ctx.send(f"🔗 **Vanity Invite:** {ctx.guild.vanity_invite}", delete_after=12)
                else:
                    await ctx.send("❌ Missing **Manage Server** permission to inspect guild invites.", delete_after=4)
                return

            inv_list = await ctx.guild.invites()
            if not inv_list:
                await ctx.send(f"📋 No active invites found in **{ctx.guild.name}**.", delete_after=5)
                return

            lines = [f"🔗 **Invites for __{ctx.guild.name}__ ({len(inv_list)}):**"]
            for inv in inv_list[:8]:
                inviter = inv.inviter.name if inv.inviter else "Unknown"
                max_u = str(inv.max_uses) if inv.max_uses else "∞"
                lines.append(f"• `{inv.code}` by **{inviter}** — Uses: `{inv.uses}/{max_u}` | URL: {inv.url}")

            await ctx.send("\n".join(lines), delete_after=20)
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch invites: {e}", delete_after=5)

    @commands.command(name="id")
    async def id_cmd(self, ctx: commands.Context, *, target: discord.User | discord.Role | discord.TextChannel | None = None) -> None:
        """Grab the snowflake ID of a user, channel, role, or yourself."""
        await ctx.message.delete()
        t = target or ctx.author
        await ctx.send(f"🆔 `{t.id}` ({getattr(t, 'name', str(t))})")

    # ── Snipe Cache ───────────────────────────────────────────────────────────

    @commands.command(name="snipe", aliases=["sn", "deleted"])
    async def snipe(self, ctx: commands.Context, index: int = 1) -> None:
        """Retrieve deleted messages/images in this channel (index 1-10, default: 1)."""
        await ctx.message.delete()
        history = self._deleted.get(ctx.channel.id)
        if not history:
            await ctx.send("❌ No deleted messages cached in this channel.", delete_after=4)
            return
        idx = max(1, min(index, len(history)))
        rec = history[-idx]
        lines = [
            f"> `-` **Sniped Message #{idx}/{len(history)}** · **{rec.author}** (`{rec.timestamp.strftime('%H:%M:%S UTC')}`)",
        ]
        if rec.content:
            lines.append(f"> `—` {rec.content[:1500]}")
        for att_url in rec.attachments[:4]:
            lines.append(f"> `•` **Attachment:** {att_url}")
        await ctx.send("\n".join(lines))

    @commands.command(name="esnipe", aliases=["editsnipe", "es"])
    async def esnipe(self, ctx: commands.Context, index: int = 1) -> None:
        """Retrieve edited messages in this channel (index 1-10, default: 1)."""
        await ctx.message.delete()
        history = self._edited.get(ctx.channel.id)
        if not history:
            await ctx.send("❌ No edited messages cached in this channel.", delete_after=4)
            return
        idx = max(1, min(index, len(history)))
        rec = history[-idx]
        lines = [
            f"> `-` **Edit-Sniped #{idx}/{len(history)}** · **{rec.author}**",
            f"> `—` **Before:** {rec.before[:900] if rec.before else '—'}",
            f"> `•` **After:** {rec.content[:900] if rec.content else '—'}",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="clearsnipe", aliases=["cs"])
    async def clearsnipe(self, ctx: commands.Context) -> None:
        """Clear snipe records for this channel."""
        await ctx.message.delete()
        self._deleted.pop(ctx.channel.id, None)
        self._edited.pop(ctx.channel.id, None)
        await ctx.send("🧹 Channel snipe cache cleared.", delete_after=4)

    # ── AFK State ─────────────────────────────────────────────────────────────

    @commands.command(name="afk")
    async def afk(self, ctx: commands.Context, *, reason: str = "") -> None:
        """Activate Smart AFK mode (5m reply cooldown + missed-ping digest)."""
        await ctx.message.delete()
        self._afk_active = True
        self._afk_reason = reason
        self.bot._afk_active = True
        self.bot._afk_reason = reason
        self.bot._afk_cooldowns.clear()
        self.bot._afk_pings.clear()
        tag = f" — *{reason}*" if reason else ""
        await ctx.send(f"💤 **AFK Enabled**{tag}", delete_after=5)

    @commands.command(name="unafk", aliases=["back"])
    async def unafk(self, ctx: commands.Context) -> None:
        """Turn off AFK mode and print a digest of missed pings."""
        await ctx.message.delete()
        self._afk_active = False
        self.bot._afk_active = False
        pings = list(getattr(self.bot, "_afk_pings", []))
        self.bot._afk_pings.clear()
        if not pings:
            await ctx.send("👋 **AFK Disabled.** Welcome back — `0` missed pings.", delete_after=5)
            return
        lines = [f"> `-` **AFK Disabled — Missed Pings ({len(pings)})**"]
        for p in pings[-8:][::-1]:
            lines.append(f"> `—` **{p['author']}** in **{p['where']}** (<t:{p['ts']}:R>): `{p['content']}` [Jump]({p['jump']})")
        lines.append("> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**")
        await ctx.send("\n".join(lines), delete_after=25)

    @commands.command(name="afkpings", aliases=["missedpings"])
    async def afkpings(self, ctx: commands.Context) -> None:
        """View pings received while AFK without disabling AFK."""
        await ctx.message.delete()
        pings = list(getattr(self.bot, "_afk_pings", []))
        if not pings:
            await ctx.send("> `-` **AFK Pings:** None recorded.", delete_after=5)
            return
        lines = [f"> `-` **AFK Missed Pings ({len(pings)})**"]
        for p in pings[-8:][::-1]:
            lines.append(f"> `—` **{p['author']}** in **{p['where']}**: `{p['content']}` [Jump]({p['jump']})")
        await ctx.send("\n".join(lines), delete_after=20)

    # ── Media & Asset Utilities ───────────────────────────────────────────────

    @commands.command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx: commands.Context, user: Optional[discord.User] = None) -> None:
        """Fetch high-resolution avatar URLs (Global and Server) for a user."""
        await ctx.message.delete()
        target = user or ctx.author
        global_av = target.avatar.url if target.avatar else target.default_avatar.url
        
        lines = [
            f"> `-` **Avatar Asset:** **{target}** (`{target.id}`)",
            f"> `—` **Global Avatar:** [Open Asset]({global_av})",
        ]
        if ctx.guild:
            member = ctx.guild.get_member(target.id)
            if member and member.guild_avatar:
                lines.append(f"> `—` **Server Avatar:** [Open Asset]({member.guild_avatar.url})")
        
        await ctx.send("\n".join(lines))

    @commands.command(name="banner", aliases=["userbanner", "ubanner"])
    async def banner(self, ctx: commands.Context, user: Optional[discord.User] = None) -> None:
        """Fetch user profile banner image link or accent color."""
        await ctx.message.delete()
        target = user or ctx.author
        try:
            fetched = await self.bot.fetch_user(target.id)
            if fetched.banner:
                lines = [
                    f"> `-` **User Banner:** **{fetched}** (`{fetched.id}`)",
                    f"> `—` **Asset Link:** [Open Banner]({fetched.banner.url})",
                ]
            elif fetched.accent_color:
                lines = [
                    f"> `-` **User Banner:** **{fetched}** (`{fetched.id}`)",
                    f"> `—` **Accent Color:** `{fetched.accent_color}`",
                ]
            else:
                lines = [
                    f"> `-` **User Banner:** **{fetched}** (`{fetched.id}`)",
                    f"> `—` No custom banner or accent color set.",
                ]
            await ctx.send("\n".join(lines))
        except Exception as e:
            await ctx.send(f"> `!` **Banner Error:** Failed to fetch user: `{e}`", delete_after=5)

    @commands.command(name="servericon", aliases=["sicon", "icon"])
    async def servericon(self, ctx: commands.Context) -> None:
        """Get high-resolution CDN link for the current server's icon."""
        await ctx.message.delete()
        if not ctx.guild:
            await ctx.send("❌ This command must be used within a server.", delete_after=4)
            return
        if not ctx.guild.icon:
            await ctx.send(f"> `-` **Server Icon:** Server **{ctx.guild.name}** has no icon set.")
            return
        lines = [
            f"> `-` **Server Icon:** **{ctx.guild.name}**",
            f"> `—` **Asset Link:** [Open Icon]({ctx.guild.icon.url})",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="serverbanner", aliases=["sbanner"])
    async def serverbanner(self, ctx: commands.Context) -> None:
        """Get high-resolution CDN link for the current server's banner or splash."""
        await ctx.message.delete()
        if not ctx.guild:
            await ctx.send("❌ This command must be used within a server.", delete_after=4)
            return
        lines = [f"> `-` **Server Assets:** **{ctx.guild.name}**"]
        has_asset = False
        if ctx.guild.banner:
            lines.append(f"> `—` **Banner Link:** [Open Banner]({ctx.guild.banner.url})")
            has_asset = True
        if ctx.guild.splash:
            lines.append(f"> `—` **Splash Link:** [Open Splash]({ctx.guild.splash.url})")
            has_asset = True
        if not has_asset:
            lines.append("> `—` No custom banner or splash image uploaded.")
        await ctx.send("\n".join(lines))

    # ── Channel, Role & Server Inspection ────────────────────────────────────

    @commands.command(name="channelinfo", aliases=["ci"])
    async def channelinfo(self, ctx: commands.Context, channel: Optional[discord.abc.GuildChannel] = None) -> None:
        """Inspect channel properties, bitrate, slowmode, category, and creation date."""
        await ctx.message.delete()
        target = channel or ctx.channel
        created_ts = int(target.created_at.timestamp()) if target.created_at else 0
        lines = [
            f"> `-` **Channel Diagnostic:** **#{target.name}** (`{target.id}`)",
            f"> `—` **Type:** `{type(target).__name__}`",
            f"> `—` **Created:** <t:{created_ts}:F> (<t:{created_ts}:R>)",
        ]
        if hasattr(target, "category") and target.category:
            lines.append(f"> `—` **Category:** `{target.category.name}` (`{target.category.id}`)")
        if hasattr(target, "slowmode_delay"):
            lines.append(f"> `—` **Slowmode:** `{target.slowmode_delay}s`")
        if hasattr(target, "bitrate"):
            lines.append(f"> `—` **Bitrate:** `{target.bitrate // 1000}kbps`")
        if hasattr(target, "nsfw"):
            lines.append(f"> `—` **NSFW:** `{'Yes' if target.nsfw else 'No'}`")
        await ctx.send("\n".join(lines))

    @commands.command(name="roleinfo", aliases=["ri"])
    async def roleinfo(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Inspect role permissions, member count, color hex, and creation date."""
        await ctx.message.delete()
        created_ts = int(role.created_at.timestamp())
        lines = [
            f"> `-` **Role Diagnostic:** **{role.name}** (`{role.id}`)",
            f"> `—` **Color Hex:** `{str(role.color).upper()}`",
            f"> `—` **Created:** <t:{created_ts}:F> (<t:{created_ts}:R>)",
            f"> `—` **Members with Role:** `{len(role.members):,}`",
            f"> `—` **Position:** `{role.position}` | **Hoisted:** `{role.hoist}` | **Mentionable:** `{role.mentionable}`",
            f"> `—` **Permissions Bitfield:** `{role.permissions.value}`",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="perms", aliases=["permissions", "checkperms"])
    async def perms(self, ctx: commands.Context, *, target: Optional[str] = None) -> None:
        """Inspect all permissions for a user (@mention / ID) or role in the current server."""
        await ctx.message.delete()
        if not ctx.guild:
            await ctx.send("❌ This command must be used within a server.", delete_after=4)
            return

        subject_user: Optional[discord.Member] = None
        subject_role: Optional[discord.Role] = None

        if not target:
            # Defaults to command invoker
            subject_user = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        else:
            raw = target.strip()
            # 1. Try finding role mention or ID/name
            clean_id = raw.replace("<@&", "").replace("<@!", "").replace("<@", "").replace(">", "").strip()
            if clean_id.isdigit():
                subject_role = ctx.guild.get_role(int(clean_id))
                if not subject_role:
                    subject_user = ctx.guild.get_member(int(clean_id))
            
            if not subject_role and not subject_user:
                # Search roles by name
                for r in ctx.guild.roles:
                    if r.name.lower() == raw.lower():
                        subject_role = r
                        break
            
            if not subject_role and not subject_user:
                # Search members by name
                for m in ctx.guild.members:
                    if m.name.lower() == raw.lower() or (m.nick and m.nick.lower() == raw.lower()):
                        subject_user = m
                        break

        if not subject_user and not subject_role:
            await ctx.send(f"❌ Could not resolve `{target}` to a member or role in this server.", delete_after=4)
            return

        # Case A: Inspecting a Role
        if subject_role:
            perms_obj = subject_role.permissions
            pos = subject_role.position
            color_hex = str(subject_role.color).upper()
            
            if perms_obj.administrator:
                allowed_list = ["Administrator (All Permissions Granted)"]
            else:
                allowed_list = [name.replace("_", " ").title() for name, value in perms_obj if value]

            allowed_str = ", ".join(f"`{p}`" for p in allowed_list) if allowed_list else "`None`"
            lines = [
                f"> `-` **Role Permissions Audit**",
                f"> `—` **Role:** **{subject_role.name}** (`{subject_role.id}`)",
                f"> `—` **Position:** `#{pos}` of `{len(ctx.guild.roles)}` · **Color:** `{color_hex}`",
                f"> `—` **Total Granted:** `{len(allowed_list)}` permissions",
                f"> `—` **Allowed Permissions:**",
                f"> {allowed_str}",
            ]
            await ctx.send("\n".join(lines))
            return

        # Case B: Inspecting a Member (Deduplicating across all assigned roles + @everyone)
        if subject_user:
            guild_perms = subject_user.guild_permissions
            top_role = subject_user.top_role
            role_count = len(subject_user.roles) - 1  # Excluding @everyone
            
            if guild_perms.administrator:
                allowed_list = ["Administrator (Bypasses All Channel Overwrites)"]
            else:
                allowed_list = [name.replace("_", " ").title() for name, value in guild_perms if value]

            # High-value permissions quick breakdown
            flags = []
            if guild_perms.administrator:
                flags.append("👑 Admin")
            if guild_perms.manage_guild:
                flags.append("⚙️ Manage Server")
            if guild_perms.ban_members:
                flags.append("🔨 Ban")
            if guild_perms.kick_members:
                flags.append("👢 Kick")
            if guild_perms.manage_channels:
                flags.append("📁 Manage Channels")
            if guild_perms.manage_roles:
                flags.append("🛡️ Manage Roles")
            if guild_perms.manage_messages:
                flags.append("🗑️ Manage Msgs")
            if guild_perms.mention_everyone:
                flags.append("📢 Mass Mention")
            key_perms_str = " · ".join(flags) if flags else "Standard Member"

            allowed_str = ", ".join(f"`{p}`" for p in allowed_list) if allowed_list else "`None`"
            lines = [
                f"> `-` **Member Effective Permissions Audit**",
                f"> `—` **Target:** **{subject_user}** (`{subject_user.id}`)",
                f"> `—` **Highest Role:** `{top_role.name}` (Pos `#{top_role.position}`)",
                f"> `—` **Assigned Roles:** `{role_count}` roles",
                f"> `—` **Key Clearance:** {key_perms_str}",
                f"> `—` **Total Granted:** `{len(allowed_list)}` permissions (Deduplicated)",
                f"> `—` **Effective Permissions:**",
                f"> {allowed_str}",
            ]
            await ctx.send("\n".join(lines))

    @commands.command(name="firstmessage", aliases=["firstmsg", "fm", "fmsg"])
    async def firstmessage(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        """Fetch the first message ever recorded in the specified or current channel."""
        await ctx.message.delete()
        target_ch = channel or ctx.channel
        try:
            # Snowflake query right after channel inception boundary
            async for first in target_ch.history(limit=1, oldest_first=True):
                jump_url = first.jump_url
                author = first.author
                ts = int(first.created_at.timestamp()) if first.created_at else 0
                preview = first.content[:150] if first.content else "[Embed / Attachment]"
                lines = [
                    f"> `-` **Channel Genesis Message**",
                    f"> `—` **Author:** **{author}** (`{author.id}`)",
                    f"> `—` **Sent:** <t:{ts}:F> (<t:{ts}:R>)",
                    f"> `—` **Jump Link:** [Jump To Message]({jump_url})",
                    f"> `—` **Preview:** {preview}",
                ]
                await ctx.send("\n".join(lines))
                return
            await ctx.send("❌ No messages found in channel history.", delete_after=4)
        except Exception as e:
            await ctx.send(f"> `!` **Genesis Fetch Error:** `{e}`", delete_after=5)

    @commands.command(name="raw", aliases=["rawmsg"])
    async def raw(self, ctx: commands.Context, message_id: Optional[int] = None) -> None:
        """Inspect unrendered raw Markdown content of a message (or replied message)."""
        await ctx.message.delete()
        target_msg = None
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                target_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except Exception:
                pass
        elif message_id:
            try:
                target_msg = await ctx.channel.fetch_message(message_id)
            except Exception:
                pass

        if not target_msg:
            await ctx.send("❌ Reply to a message or provide a message ID to view raw Markdown.", delete_after=4)
            return

        clean_raw = discord.utils.escape_markdown(target_msg.content) if target_msg.content else "[No text content]"
        lines = [
            f"> `-` **Raw Message Source:** (`{target_msg.id}`)",
            f"> `—` **Author:** **{target_msg.author}** (`{target_msg.author.id}`)",
            f"```text\n{clean_raw[:1700]}\n```",
        ]
        await ctx.send("\n".join(lines))

    # ── Calculation & Translation ─────────────────────────────────────────────

    @commands.command(name="calc", aliases=["math"])
    async def calc(self, ctx: commands.Context, *, expression: str) -> None:
        """Safely calculate a mathematical expression."""
        await ctx.message.delete()
        allowed = set("0123456789+-*/().,% eE")
        if not set(expression).issubset(allowed):
            await ctx.send("❌ Expression contains unsupported characters.", delete_after=4)
            return
        try:
            # Safe evaluation with restricted globals/locals
            res = eval(expression, {"__builtins__": None}, {})
            await ctx.send(f"> `-` **Calculator:** `{expression}` = **`{res}`**")
        except Exception as e:
            await ctx.send(f"> `!` **Math Error:** `{e}`", delete_after=4)

    @commands.command(name="hashencode", aliases=["hash"])
    async def hashencode(self, ctx: commands.Context, *, text: str) -> None:
        """Generate MD5, SHA1, and SHA256 hashes for text."""
        await ctx.message.delete()
        b = text.encode("utf-8")
        md5_h = hashlib.md5(b).hexdigest()
        sha1_h = hashlib.sha1(b).hexdigest()
        sha256_h = hashlib.sha256(b).hexdigest()
        lines = [
            f"> `-` **Cryptographic Hashes**",
            f"> `—` **MD5:** `{md5_h}`",
            f"> `—` **SHA1:** `{sha1_h}`",
            f"> `—` **SHA256:** `{sha256_h}`",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="translate", aliases=["tr"])
    async def translate(self, ctx: commands.Context, *, query: Optional[str] = None) -> None:
        """Translate text (or replied message) to English. Handles Hinglish & any foreign language."""
        await ctx.message.delete()
        import json
        import urllib.parse
        import urllib.request

        text_to_translate = ""
        target_lang = "en"

        # Check if user replied to a message
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                text_to_translate = ref_msg.content.strip()
                # If query provided with reply, treat query as optional target language code (e.g. `g.tr es`)
                if query and len(query.strip()) <= 5:
                    target_lang = query.strip().lower()
            except Exception:
                pass

        if not text_to_translate:
            if not query:
                await ctx.send("❌ Reply to a message or provide text: `g.tr kya kar rahe ho bhai`", delete_after=5)
                return
            
            # Check if first word is a language code: e.g. `g.tr es hello my friend`
            parts = query.split(maxsplit=1)
            if len(parts) == 2 and len(parts[0]) in (2, 3) and parts[0].isalpha():
                target_lang = parts[0].lower()
                text_to_translate = parts[1]
            else:
                text_to_translate = query

        try:
            # Query Google Translate API with client=dict-chrome-ex for native Hinglish & foreign text detection
            encoded_text = urllib.parse.quote(text_to_translate)
            url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=auto&tl={target_lang}&q={encoded_text}"
            
            loop = asyncio.get_running_loop()
            def _fetch():
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=6) as response:
                    return response.read().decode("utf-8")

            res_raw = await loop.run_in_executor(None, _fetch)
            data = json.loads(res_raw)
            
            # Result format is [[translated_text, detected_lang]]
            if isinstance(data, list) and len(data) > 0:
                first_item = data[0]
                if isinstance(first_item, list):
                    trans_text = first_item[0]
                    detected_lang = first_item[1] if len(first_item) > 1 else "auto"
                else:
                    trans_text = str(data[0])
                    detected_lang = "auto"
            else:
                trans_text = str(data)
                detected_lang = "auto"

            lines = [
                f"> `-` **Universal Translation [{detected_lang.upper()} → {target_lang.upper()}]**",
                f"> `—` **Original:** {text_to_translate[:200]}",
                f"> `—` **Translated:** **{trans_text}**",
            ]
            await ctx.send("\n".join(lines))
        except Exception as e:
            await ctx.send(f"> `!` **Translation Error:** `{e}`", delete_after=5)

    # ── Self-Purge Utility ───────────────────────────────────────────────────

    @commands.command(name="selfpurge", aliases=["spurge", "purge", "sp", "clearself"])
    async def selfpurge(self, ctx: commands.Context, limit: int = 50) -> None:
        """
        Purge your own sent messages in the current channel or Direct Message (DM).
        Usage: g.selfpurge [amount] or g.spurge [amount] (default: 50, max: 500)
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        target_limit = max(1, min(limit, 500))
        channel_name = f"#{ctx.channel.name}" if hasattr(ctx.channel, "name") and ctx.channel.name else "Direct Message"
        status_msg = await ctx.send(
            f"> `-` **Self-Purge Initialized**\n"
            f"> `—` **Target Count:** `{target_limit}` messages\n"
            f"> `—` **Target Author:** `{ctx.author.name}`\n"
            f"> `—` **Channel:** `{channel_name}`\n"
            f"> `•` *Scanning channel history and purging own messages…*"
        )

        deleted_count = 0
        scanned_count = 0

        try:
            # Scan channel history (before the status message)
            scan_cap = min(target_limit * 4, 1500)
            async for msg in ctx.channel.history(limit=scan_cap, before=status_msg):
                scanned_count += 1
                if self.bot.user and msg.author.id == self.bot.user.id and msg.id != status_msg.id:
                    try:
                        await msg.delete()
                        deleted_count += 1
                        await asyncio.sleep(0.35)
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        break
                    except discord.HTTPException as e:
                        if getattr(e, "status", None) == 429:
                            await asyncio.sleep(2.0)
                        else:
                            pass

                if deleted_count >= target_limit:
                    break

            completion_lines = [
                "> `-` **Self-Purge Completed**",
                f"> `—` **Messages Deleted:** `{deleted_count}` own messages wiped",
                f"> `—` **Channel:** `{channel_name}`",
                f"> `—` **Scanned Depth:** `{scanned_count}` messages parsed",
                "> `•` *Purge finished with zero residual author footprint.*",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
            await status_msg.edit(content="\n".join(completion_lines))
            await status_msg.delete(delay=6)

        except Exception as e:
            await status_msg.edit(content=f"> `!` **Self-Purge Error:** `{e}`")
            await status_msg.delete(delay=5)

    @commands.command(name="exportchat", aliases=["exportdm", "chatexport", "transcript"])
    async def exportchat(self, ctx: commands.Context, limit: int = 200) -> None:
        """
        Export channel or DM message history into a clean Markdown transcript file.
        Syntax: `g.exportchat [limit]` (max: 1000, default: 200)
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        target_limit = max(1, min(limit, 1000))
        ch_name = getattr(ctx.channel, "name", None) or f"dm-{getattr(ctx.channel, 'recipient', ctx.channel.id)}"
        status_msg = await ctx.send(f"> `-` **Exporting up to `{target_limit}` messages from `{ch_name}`…**")

        try:
            records: list[str] = []
            async for msg in ctx.channel.history(limit=target_limit, oldest_first=False):
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if msg.created_at else "unknown"
                body = msg.content or ""
                if msg.attachments:
                    att_str = " ".join(a.url for a in msg.attachments)
                    body = f"{body} [Attachments: {att_str}]".strip()
                if not body and msg.embeds:
                    body = "[Embed]"
                records.append(f"[{ts}] {msg.author} ({msg.author.id}): {body}")

            records.reverse()
            header = f"# Globe Chat Transcript — {ch_name}\n# Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n# Messages: {len(records)}\n\n"
            payload = (header + "\n".join(records)).encode("utf-8")
            file_obj = discord.File(io.BytesIO(payload), filename=f"transcript_{ctx.channel.id}.txt")
            await status_msg.delete()
            await ctx.send(
                f"> `-` **Transcript Exported:** `{len(records)}` messages from **{ch_name}**",
                file=file_obj,
            )
        except Exception as e:
            await status_msg.edit(content=f"> `!` **Export Error:** `{e}`")
            await status_msg.delete(delay=5)

    @commands.command(name="deletedm", aliases=["wipedm", "cleandm", "nukedm"])
    async def deletedm(self, ctx: commands.Context) -> None:
        """
        Wipe ALL messages sent by you in the current DM channel using adaptive rate-limit pacing.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id) or not self.bot.user:
            return
        if ctx.guild is not None:
            await ctx.send(f"> `!` `{settings.prefix}deletedm` only runs inside DMs/Group DMs.", delete_after=5)
            return

        status_msg = await ctx.send("> `-` **DM Wipe Initiated:** Scanning & clearing your messages…")
        deleted_count = 0
        scanned_count = 0
        pace = 0.28

        try:
            async for msg in ctx.channel.history(limit=None):
                scanned_count += 1
                if msg.id == status_msg.id:
                    continue
                if msg.author.id != self.bot.user.id:
                    continue
                if msg.type not in (discord.MessageType.default, discord.MessageType.reply):
                    continue

                for attempt in range(3):
                    try:
                        await msg.delete()
                        deleted_count += 1
                        if deleted_count % 15 == 0:
                            try:
                                await status_msg.edit(
                                    content=f"> `-` **DM Wipe Running:** `{deleted_count}` deleted (`{scanned_count}` scanned)…"
                                )
                            except Exception:
                                pass
                        await asyncio.sleep(pace + random.uniform(0.04, 0.14))
                        break
                    except discord.HTTPException as e:
                        status_code = getattr(e, "status", None)
                        if status_code == 429:
                            retry_after = getattr(e, "retry_after", 2.0) or 2.0
                            pace = min(pace + 0.05, 0.75)
                            await asyncio.sleep(float(retry_after) + 0.35)
                        elif status_code in (403, 404):
                            break
                        else:
                            await asyncio.sleep(0.5)

            await status_msg.edit(
                content="\n".join([
                    "> `-` **DM Wipe Complete**",
                    f"> `—` **Own Messages Deleted:** `{deleted_count}`",
                    f"> `—` **Messages Scanned:** `{scanned_count}`",
                    "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
                ])
            )
            await status_msg.delete(delay=5)
        except Exception as e:
            await status_msg.edit(content=f"> `!` **DM Wipe Error:** `{e}`")
            await status_msg.delete(delay=5)

    @commands.command(name="snipesearch", aliases=["ssearch", "findsnipe"])
    async def snipesearch(self, ctx: commands.Context, *, query: str) -> None:
        """Search the last 500 persisted deleted messages by keyword or username."""
        await ctx.message.delete()
        from data.tracker import tracker

        hits = tracker.search_snipes(query, limit=8)
        if not hits:
            await ctx.send(f"> `-` **Snipe Forensics:** No matches for `{query}`.", delete_after=5)
            return
        lines = [f"> `-` **Snipe Forensics (`{len(hits)}` matches for `{query}`)**"]
        for h in hits:
            lines.append(
                f"> `—` **{h['author_name']}** (<t:{int(h['timestamp'])}:R>): `{h['content'][:120]}`"
            )
        lines.append("> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**")
        await ctx.send("\n".join(lines), delete_after=25)

    @commands.command(name="stealall", aliases=["cloneemojis", "stealemojis"])
    async def stealall(self, ctx: commands.Context, source_guild_id: int, limit: int = 15) -> None:
        """Clone custom emojis from another mutual server into the current server."""
        await ctx.message.delete()
        if not ctx.guild or not self.bot.is_owner_id(ctx.author.id):
            return
        src = self.bot.get_guild(source_guild_id)
        if not src:
            await ctx.send("> `!` **Source guild not found in cache.**", delete_after=5)
            return

        cap = max(1, min(limit, 30))
        emojis = list(src.emojis)[:cap]
        if not emojis:
            await ctx.send("> `!` Source guild has no custom emojis.", delete_after=4)
            return

        status_msg = await ctx.send(f"> `-` **Cloning `{len(emojis)}` emojis from `{src.name}`…**")
        added = 0
        async with aiohttp.ClientSession() as session:
            for em in emojis:
                try:
                    async with session.get(str(em.url)) as resp:
                        if resp.status != 200:
                            continue
                        img_bytes = await resp.read()
                    await ctx.guild.create_custom_emoji(name=em.name, image=img_bytes)
                    added += 1
                    await asyncio.sleep(1.2)
                except Exception:
                    pass
        await status_msg.edit(content=f"> `-` **Cloned `{added}/{len(emojis)}` emojis** from **{src.name}**.")
        await status_msg.delete(delay=8)

    @commands.command(name="closedms", aliases=["cleardms", "dmclean"])
    async def closedms(self, ctx: commands.Context, count: int = 20) -> None:
        """Close up to N open 1-on-1 DM channels in your sidebar (preserves history)."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        cap = max(1, min(count, 100))
        dm_channels = [ch for ch in self.bot.private_channels if isinstance(ch, discord.DMChannel)][:cap]
        closed = 0
        for ch in dm_channels:
            if ch.id == ctx.channel.id:
                continue
            try:
                await ch.close()
                closed += 1
                await asyncio.sleep(0.35)
            except Exception:
                pass
        await ctx.send(f"> `-` **Closed `{closed}` DM channels** from sidebar.", delete_after=5)

    @commands.command(name="ghostedit", aliases=["gedit", "trickedit"])
    async def ghostedit(self, ctx: commands.Context, *, payload: str) -> None:
        """Send an initial message and edit it after 1.2s: `g.ghostedit initial | final`."""
        await ctx.message.delete()
        if "|" not in payload:
            await ctx.send(f"> `!` **Usage:** `{settings.prefix}ghostedit <initial> | <final>`", delete_after=5)
            return
        first, second = [part.strip() for part in payload.split("|", 1)]
        if not first or not second:
            return
        m = await ctx.send(first[:1900])
        await asyncio.sleep(1.2)
        try:
            await m.edit(content=second[:1900])
        except Exception:
            pass

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        att_urls = [a.proxy_url or a.url for a in message.attachments] if message.attachments else []
        content = message.content or ""
        if not content and message.embeds:
            emb = message.embeds[0]
            content = f"[Embed: {emb.title or emb.description or 'Rich Embed'}]"
        if not content and not att_urls:
            return
        if message.channel.id not in self._deleted and len(self._deleted) >= 128:
            self._deleted.pop(next(iter(self._deleted)))
        self._deleted[message.channel.id].append(
            SniperRecord(
                content=content,
                author=str(message.author),
                author_id=message.author.id,
                avatar=str(message.author.display_avatar.url),
                timestamp=message.created_at.replace(tzinfo=None) if message.created_at else datetime.utcnow(),
                attachments=att_urls,
            )
        )
        try:
            from data.tracker import tracker
            tracker.record_snipe(
                channel_id=message.channel.id,
                author_id=message.author.id,
                author_name=str(message.author),
                content=content,
                attachments=att_urls,
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.content or before.content == after.content or before.author.bot:
            return
        if before.channel.id not in self._edited and len(self._edited) >= 128:
            self._edited.pop(next(iter(self._edited)))
        self._edited[before.channel.id].append(
            SniperRecord(
                content=after.content,
                author=str(before.author),
                author_id=before.author.id,
                avatar=str(before.author.display_avatar.url),
                timestamp=before.created_at.replace(tzinfo=None) if before.created_at else datetime.utcnow(),
                before=before.content,
            )
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
