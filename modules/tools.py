"""
Globe — Tools Module
Advanced practical tools:
- Nitro Sniper & Gift redemption
- Channel automation: auto-react, auto-reply rules
- Token checker & formatter
- Network tools: IP geolocation, DNS lookup, HTTP headers inspector
- Crypto/Coin market price query
- Reminders, timers & timestamp utility
- Weather & Urban lookups
"""

from __future__ import annotations

import asyncio
import re
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

import discord
import httpx
from discord.ext import commands

from config import settings
from footprint_handlers import footprint
from ui import log_info, log_warn, log_err

P = settings.prefix

GIFT_RE = re.compile(r"(?:discord\.gift|discord\.com/gifts?)/([a-zA-Z0-9]+)", re.IGNORECASE)
REDEEM_URL = "https://discord.com/api/v9/entitlements/gift-codes/{code}/redeem"


@dataclass
class AutoReplyRule:
    trigger: str
    response: str
    is_regex: bool = False
    exact_match: bool = False


def _parse_duration(text: str) -> float | None:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    text = text.strip().lower()
    if len(text) < 2:
        return None
    unit = text[-1]
    if unit not in units:
        return None
    try:
        val = float(text[:-1])
        return val * units[unit]
    except ValueError:
        return None


class Tools(commands.Cog):
    """Network inspection, token auditing, nitro sniper, reminders & automation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._reminders: list[asyncio.Task] = []
        self._nitro_enabled: bool = settings.nitro_sniper
        self._sniped_codes: set[str] = set()
        self._auto_react: dict[int, list[str]] = {}
        self._auto_reply: dict[int, list[AutoReplyRule]] = {}
        self._privacy_enabled: bool = False
        self._privacy_until: float | None = None
        self._pending_privacy_messages: dict[int, list[int]] = {}

    # ── DM Privacy Mode (Auto-delete seen messages in DMs) ─────────────────────

    @commands.command(name="privacy", aliases=["dmprivacy", "ephemeral", "autowipe"])
    async def privacy(self, ctx: commands.Context, duration: str | None = None) -> None:
        """
        Toggle DM Privacy mode on/off (optional duration: g.privacy 10m or g.privacy 1h).
        When enabled, your messages in Direct Messages (DMs) are automatically and immediately
        deleted the moment the recipient views/reads/types/reacts or replies.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return

        if self._privacy_enabled and not duration:
            self._privacy_enabled = False
            self._privacy_until = None
            self._pending_privacy_messages.clear()
            lines = [
                "> `-` **DM Privacy Mode:** `DISABLED`",
                "> `—` **Status:** Normal message retention restored in Direct Messages",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
            msg = await ctx.send("\n".join(lines))
            await msg.delete(delay=5)
            log_info("DM Privacy mode disabled.")
            return

        self._privacy_enabled = True
        duration_desc = "Indefinite (until toggled off)"

        if duration:
            secs = _parse_duration(duration)
            if secs:
                self._privacy_until = time.monotonic() + secs
                duration_desc = f"`{duration}` (auto-disables after {duration})"
            else:
                self._privacy_until = None
        else:
            self._privacy_until = None

        lines = [
            "> `-` **DM Privacy Mode:** `ENABLED`",
            f"> `—` **Duration:** {duration_desc}",
            "> `—` **Trigger:** Immediate self-destruct upon recipient read/seen event",
            "> `—` **Detection Vectors:** Typing indicator, read acknowledgment, reply, reaction",
            "> `—` **Scope:** Direct Messages (DMs) only",
            "> `•` *Your messages in DMs will self-destruct as soon as the recipient opens, reads, reacts, or replies.*",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        msg = await ctx.send("\n".join(lines))
        await msg.delete(delay=8)
        log_info(f"DM Privacy mode enabled ({duration_desc}).")

    # ── Nitro Sniper ──────────────────────────────────────────────────────────

    @commands.command(name="sniper", aliases=["nitrosniper", "ns"])
    async def sniper_toggle(self, ctx: commands.Context) -> None:
        """Toggle the Nitro gift code sniper on/off."""
        if not self.bot.is_owner_id(ctx.author.id):
            return
        await ctx.message.delete()
        self._nitro_enabled = not self._nitro_enabled
        state = "✅ **enabled**" if self._nitro_enabled else "❌ **disabled**"
        msg = await ctx.send(f"🎁 Nitro sniper {state}")
        await msg.delete(delay=5)

    # ── Channel Automation ────────────────────────────────────────────────────

    @commands.command(name="autoreact", aliases=["ar_react", "react"])
    async def autoreact(self, ctx: commands.Context, *emojis: str) -> None:
        """Set auto-react emojis for current channel (leave blank to clear)."""
        await ctx.message.delete()
        if not emojis:
            self._auto_react.pop(ctx.channel.id, None)
            await ctx.send("🧹 Auto-react cleared.", delete_after=4)
        else:
            self._auto_react[ctx.channel.id] = list(emojis)
            await ctx.send(f"⚡ Auto-react active: {' '.join(emojis)}", delete_after=5)

    @commands.command(name="autoreply", aliases=["arp"])
    async def autoreply(self, ctx: commands.Context, trigger: str, *, response: str) -> None:
        """Add auto-reply rule: `g.autoreply /regex/ Hello` or `g.autoreply keyword Hello`."""
        await ctx.message.delete()
        is_regex = trigger.startswith("/") and trigger.endswith("/")
        clean_trig = trigger[1:-1] if is_regex else trigger

        rule = AutoReplyRule(trigger=clean_trig, response=response, is_regex=is_regex)
        if ctx.channel.id not in self._auto_reply:
            self._auto_reply[ctx.channel.id] = []
        self._auto_reply[ctx.channel.id].append(rule)

        kind = "regex" if is_regex else "text"
        await ctx.send(f"✅ Auto-reply added [{kind}]: `{trigger}` → `{response}`", delete_after=5)

    @commands.command(name="stopar", aliases=["clearar", "noar"])
    async def stopar(self, ctx: commands.Context) -> None:
        """Clear all auto-reply rules configured in this channel."""
        await ctx.message.delete()
        self._auto_reply.pop(ctx.channel.id, None)
        await ctx.send("🧹 Auto-reply rules cleared.", delete_after=4)

    @commands.command(name="listar", aliases=["showar"])
    async def listar(self, ctx: commands.Context) -> None:
        """List active auto-reply rules in this channel."""
        await ctx.message.delete()
        rules = self._auto_reply.get(ctx.channel.id, [])
        if not rules:
            await ctx.send("📋 No auto-reply rules active in this channel.", delete_after=4)
            return

        lines = [f"📋 **Auto-reply Rules ({len(rules)}):**"]
        for i, r in enumerate(rules, 1):
            kind = "regex" if r.is_regex else "text"
            lines.append(f"`{i}.` [{kind}] `{r.trigger}` → `{r.response}`")
        await ctx.send("\n".join(lines))

    # ── Advanced Token Checker & Info ──────────────────────────────────────────

    @commands.command(name="checktoken", aliases=["tokeninfo", "tokencheck"])
    async def checktoken(self, ctx: commands.Context, token_str: str) -> None:
        """Inspect a Discord user token: check validity, username, email, phone, 2FA, Nitro & flags."""
        await ctx.message.delete()
        clean = token_str.strip().strip("'\"")

        url = "https://discord.com/api/v9/users/@me"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url, headers={"Authorization": clean})
                if resp.status_code == 200:
                    d = resp.json()
                    uname = f"{d.get('username')}#{d.get('discriminator', '0')}"
                    uid = d.get("id")
                    email = d.get("email") or "None"
                    phone = d.get("phone") or "None"
                    mfa = "Enabled" if d.get("mfa_enabled") else "Disabled"
                    nitro_types = {0: "None", 1: "Nitro Classic", 2: "Nitro", 3: "Nitro Basic"}
                    nitro = nitro_types.get(d.get("premium_type", 0), "None")
                    verified = "Yes" if d.get("verified") else "No"

                    lines = [
                        f"🔒 **Token Status: VALID**",
                        f"**User:** `{uname}` (`{uid}`)",
                        f"**Email:** `{email}` (Verified: {verified})",
                        f"**Phone:** `{phone}`",
                        f"**2FA / MFA:** `{mfa}`",
                        f"**Nitro Tier:** `{nitro}`",
                    ]
                    await ctx.send("\n".join(lines), delete_after=20)
                elif resp.status_code == 401:
                    await ctx.send("❌ **Token Status: INVALID / EXPIRED** (HTTP 401)", delete_after=6)
                elif resp.status_code == 403:
                    await ctx.send("⚠️ **Token Status: LOCKED / PHONE VERIFICATION REQUIRED** (HTTP 403)", delete_after=6)
                else:
                    await ctx.send(f"⚠️ Token returned HTTP {resp.status_code}.", delete_after=6)
        except Exception as e:
            await ctx.send(f"❌ Token check error: {e}", delete_after=5)

    # ── Network & Diagnostics Tools ───────────────────────────────────────────

    @commands.command(name="iplookup", aliases=["geo", "ip"])
    async def iplookup(self, ctx: commands.Context, ip_or_host: str) -> None:
        """Lookup geographic and ISP data for an IP or domain."""
        await ctx.message.delete()
        try:
            target = ip_or_host.replace("https://", "").replace("http://", "").split("/")[0]
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(f"http://ip-api.com/json/{target}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query")
                data = r.json()

            if data.get("status") == "success":
                lines = [
                    f"🌐 **IP Geolocation: `{data.get('query')}`**",
                    f"**Location:** {data.get('city')}, {data.get('regionName')}, {data.get('country')} ({data.get('zip', '—')})",
                    f"**Coordinates:** `{data.get('lat')}, {data.get('lon')}`",
                    f"**Timezone:** `{data.get('timezone')}`",
                    f"**ISP / Org:** {data.get('isp')} ({data.get('org', '—')})",
                    f"**AS:** `{data.get('as')}`",
                ]
                await ctx.send("\n".join(lines), delete_after=25)
            else:
                await ctx.send(f"❌ IP lookup failed: {data.get('message', 'Not found')}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Geolocation error: {e}", delete_after=5)

    @commands.command(name="dns", aliases=["resolve", "nslookup"])
    async def dns(self, ctx: commands.Context, domain: str) -> None:
        """Resolve IP addresses associated with a domain name."""
        await ctx.message.delete()
        host = domain.replace("https://", "").replace("http://", "").split("/")[0]
        try:
            loop = asyncio.get_running_loop()
            addr_info = await loop.getaddrinfo(host, None)
            unique_ips = sorted(list({info[4][0] for info in addr_info}))
            ip_str = "\n".join(f"• `{ip}`" for ip in unique_ips)
            await ctx.send(f"📡 **DNS Resolution for `{host}` ({len(unique_ips)}):**\n{ip_str}", delete_after=15)
        except Exception as e:
            await ctx.send(f"❌ DNS resolution failed: {e}", delete_after=5)

    @commands.command(name="headers", aliases=["httpheaders", "curlhead"])
    async def headers(self, ctx: commands.Context, url: str) -> None:
        """Fetch and inspect HTTP response headers from a server or endpoint."""
        await ctx.message.delete()
        target = url if url.startswith(("http://", "https://")) else f"https://{url}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.head(target, follow_redirects=True)
                lines = [f"🌐 **HTTP Headers for `{target}`** (Status: `{resp.status_code}`)"]
                for k, v in list(resp.headers.items())[:12]:
                    lines.append(f"• **{k}:** `{v[:80]}`")
                await ctx.send("\n".join(lines), delete_after=20)
        except Exception as e:
            await ctx.send(f"❌ Header fetch error: {e}", delete_after=5)

    @commands.command(name="crypto", aliases=["price", "btc", "eth"])
    async def crypto(self, ctx: commands.Context, coin: str = "bitcoin") -> None:
        """Check live cryptocurrency price and 24h market change (e.g. `g.crypto solana`)."""
        await ctx.message.delete()
        coin_clean = coin.lower().strip()
        alias_map = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "xrp": "ripple", "doge": "dogecoin", "ltc": "litecoin"}
        coin_id = alias_map.get(coin_clean, coin_clean)

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true")
                data = r.json()

            if coin_id in data:
                price = data[coin_id]["usd"]
                change = data[coin_id].get("usd_24h_change", 0.0)
                sign = "📈 +" if change >= 0 else "📉 "
                await ctx.send(f"🪙 **{coin_id.upper()}:** `${price:,.2f} USD` ({sign}{change:.2f}% 24h)")
            else:
                await ctx.send(f"❌ Cryptocurrency `{coin}` not found.", delete_after=4)
        except Exception as e:
            await ctx.send(f"❌ Market price fetch failed: {e}", delete_after=5)

    # ── Reminders & Timestamp ─────────────────────────────────────────────────

    @commands.command(name="remind", aliases=["remindme", "timer"])
    async def remind(self, ctx: commands.Context, duration: str, *, task_text: str) -> None:
        """Set a reminder countdown: `g.remind 10m Take a break`."""
        await ctx.message.delete()
        secs = _parse_duration(duration)
        if not secs:
            await ctx.send("❌ Invalid duration (use: `30s`, `15m`, `2h`, `1d`).", delete_after=4)
            return

        ts = discord.utils.format_dt(discord.utils.utcnow() + timedelta(seconds=secs), style="R")
        ack = await ctx.send(f"⏰ Reminder set for {ts}: *{task_text}*")

        async def _run_reminder():
            await asyncio.sleep(secs)
            try:
                await ctx.channel.send(f"⏰ **Reminder alert:**\n> {task_text}")
            except Exception:
                pass

        self._reminders.append(asyncio.create_task(_run_reminder()))
        if settings.auto_delete_delay:
            await ack.delete(delay=settings.auto_delete_delay)

    @commands.command(name="timestamp", aliases=["ts", "time"])
    async def timestamp(self, ctx: commands.Context) -> None:
        """Show current Unix epoch timestamp and format styles."""
        await ctx.message.delete()
        now = int(time.time())
        lines = [
            f"🕐 **Discord Timestamp:** `<t:{now}:F>` (<t:{now}:R>)",
            f"**Raw Epoch:** `{now}`",
        ]
        await ctx.send("\n".join(lines))

    # ── External Lookups ──────────────────────────────────────────────────────

    @commands.command(name="weather", aliases=["wttr", "w"])
    async def weather(self, ctx: commands.Context, *, location: str) -> None:
        """Look up weather conditions for a location via wttr.in."""
        await ctx.message.delete()
        url = f"https://wttr.in/{quote_plus(location)}?format=4"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url, follow_redirects=True)
                await ctx.send(f"🌤️ {resp.text.strip()}")
        except Exception as e:
            await ctx.send(f"❌ Weather check failed: {e}", delete_after=4)

    @commands.command(name="urban", aliases=["ud", "define"])
    async def urban(self, ctx: commands.Context, *, term: str) -> None:
        """Search term definition on Urban Dictionary."""
        await ctx.message.delete()
        url = f"https://api.urbandictionary.com/v0/define?term={quote_plus(term)}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url)
                data = resp.json().get("list", [])
            if not data:
                await ctx.send(f"❌ No definitions found for `{term}`.", delete_after=4)
                return
            top = data[0]
            defn = top["definition"][:380].replace("[", "").replace("]", "")
            await ctx.send(f"📖 **Urban: {term}**\n>>> {defn}")
        except Exception as e:
            await ctx.send(f"❌ Lookup failed: {e}", delete_after=5)

    # ── Advanced OSINT Link & Invite / Guild Intelligence ────────────────────

    @commands.command(name="linkinfo", aliases=["link", "linkosint", "urlinfo"])
    async def linkinfo(self, ctx: commands.Context, url: str) -> None:
        """Deep OSINT inspection of a URL: redirects, IP/DNS, security headers, metadata, certificate info."""
        await ctx.message.delete()
        target = url if url.startswith(("http://", "https://")) else f"https://{url}"
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(target)
            hostname = parsed.hostname or ""
            
            # DNS resolution
            loop = asyncio.get_running_loop()
            try:
                addr_info = await loop.getaddrinfo(hostname, None)
                ips = sorted(list({info[4][0] for info in addr_info}))
            except Exception:
                ips = []

            # HTTP Trace & Redirect chain
            redirect_chain: list[str] = []
            final_resp = None
            headers_captured: dict[str, str] = {}
            html_title = ""
            server_software = "Hidden"

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False) as client:
                resp = await client.get(target, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
                final_resp = resp
                for r in resp.history:
                    redirect_chain.append(f"{r.status_code} → `{r.url}`")
                headers_captured = dict(resp.headers)
                server_software = headers_captured.get("server", "Hidden/Cloudflare")

                # Extract HTML title and meta description
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text[:30000], "html.parser")
                    if soup.title and soup.title.string:
                        html_title = soup.title.string.strip()[:80]
                except Exception:
                    pass

            # Security Headers audit
            sec_headers = []
            for h in ["content-security-policy", "strict-transport-security", "x-frame-options", "x-content-type-options"]:
                if h in headers_captured:
                    sec_headers.append(f"`{h}`: ✅")
                else:
                    sec_headers.append(f"`{h}`: ❌")

            hops_str = "None (Direct)" if not redirect_chain else " → ".join(redirect_chain)
            ips_str = ", ".join(f"`{ip}`" for ip in ips[:4]) if ips else "Unknown"
            
            content_type = headers_captured.get("content-type", "unknown").split(";")[0]
            status_code = final_resp.status_code if final_resp else "N/A"

            lines = [
                f"> `-` **URL Deep OSINT Analysis**",
                f"> `—` **Target URL:** `{target}`",
                f"> `—` **Resolved Host:** `{hostname}`",
                f"> `—` **Resolved IP(s):** {ips_str}",
                f"> `—` **Status & Type:** HTTP `{status_code}` · `{content_type}`",
                f"> `—` **Server Header:** `{server_software}`",
                f"> `—` **Redirect Chain:** {hops_str}",
            ]
            if html_title:
                lines.append(f"> `—` **Page Title:** {html_title}")
            lines.append(f"> `—` **Security Headers:** {' · '.join(sec_headers)}")

            await ctx.send("\n".join(lines))
        except Exception as e:
            await ctx.send(f"> `!` **OSINT Error:** Failed to analyze URL: `{e}`", delete_after=6)

    @commands.command(name="invinfo", aliases=["invite", "serverlookup", "guildlookup", "invosint"])
    async def invinfo(self, ctx: commands.Context, invite_or_guild_id: str) -> None:
        """Deep OSINT inspection of a Discord invite code, invite URL, or Guild ID."""
        await ctx.message.delete()
        raw = invite_or_guild_id.strip()
        
        # Extract code if URL was provided
        code = raw
        if "discord.gg/" in raw:
            code = raw.split("discord.gg/")[1].split("/")[0].split("?")[0]
        elif "discord.com/invite/" in raw:
            code = raw.split("discord.com/invite/")[1].split("/")[0].split("?")[0]

        is_snowflake = code.isdigit() and len(code) >= 17

        # Case 1: Snowflake Guild ID Lookup (checks local client cache or widget API)
        if is_snowflake:
            guild_id = int(code)
            cached_guild = self.bot.get_guild(guild_id)
            if cached_guild:
                owner_str = f"{cached_guild.owner} (`{cached_guild.owner_id}`)" if cached_guild.owner else f"`{cached_guild.owner_id}`"
                created_ts = int(cached_guild.created_at.timestamp())
                boost_tier = f"Tier {cached_guild.premium_tier} ({cached_guild.premium_subscription_count} boosts)"
                features = ", ".join(f"`{f}`" for f in list(cached_guild.features)[:6]) or "None"

                lines = [
                    f"> `-` **Guild OSINT (Mutual / In Cache)**",
                    f"> `—` **Name:** **{cached_guild.name}** (`{cached_guild.id}`)",
                    f"> `—` **Owner:** {owner_str}",
                    f"> `—` **Created:** <t:{created_ts}:F> (<t:{created_ts}:R>)",
                    f"> `—` **Members:** `{cached_guild.member_count:,}` (Humans & Bots)",
                    f"> `—` **Channels:** `{len(cached_guild.channels)}` | **Roles:** `{len(cached_guild.roles)}` | **Emojis:** `{len(cached_guild.emojis)}`",
                    f"> `—` **Boosts:** {boost_tier}",
                    f"> `—` **Features:** {features}",
                    f"> `—` **Vanity URL:** `{cached_guild.vanity_url_code or 'None'}`",
                ]
                if cached_guild.icon:
                    lines.append(f"> `—` **Icon Asset:** [Open Icon]({cached_guild.icon.url})")
                await ctx.send("\n".join(lines))
                return

            # If not in cache, query Discord Guild Widget / Discovery API endpoint
            try:
                token_val = getattr(self.bot.http, "token", "") or settings.discord_token
                async with httpx.AsyncClient(timeout=8.0) as client:
                    w_resp = await client.get(f"https://discord.com/api/v9/guilds/{guild_id}/widget.json")
                    if w_resp.status_code == 200:
                        w_data = w_resp.json()
                        w_name = w_data.get("name", "Unknown")
                        presence_count = len(w_data.get("members", []))
                        instant_invite = w_data.get("instant_invite", "None")
                        lines = [
                            f"> `-` **Guild Widget OSINT**",
                            f"> `—` **Name:** **{w_name}** (`{guild_id}`)",
                            f"> `—` **Status:** Widget Enabled",
                            f"> `—` **Active Online Tracked:** `{presence_count}`",
                            f"> `—` **Instant Invite Discovered:** `{instant_invite}`",
                        ]
                        await ctx.send("\n".join(lines))
                        return
                    else:
                        await ctx.send(f"> `!` **Guild OSINT:** Guild `{guild_id}` is not in bot cache and Widget API returned `{w_resp.status_code}` (Widget disabled or private).", delete_after=6)
                        return
            except Exception as e:
                await ctx.send(f"> `!` **Guild OSINT Error:** `{e}`", delete_after=5)
                return

        # Case 2: Invite Code / Link Deep OSINT via Discord API with with_counts & with_expiration
        try:
            token_val = getattr(self.bot.http, "token", "") or settings.discord_token
            async with httpx.AsyncClient(timeout=8.0) as client:
                headers = {"Authorization": token_val} if token_val else {}
                resp = await client.get(
                    f"https://discord.com/api/v9/invites/{code}?with_counts=true&with_expiration=true",
                    headers=headers
                )
                if resp.status_code == 404:
                    await ctx.send(f"> `!` **Invite OSINT:** Invite code `{code}` is invalid or expired.", delete_after=5)
                    return
                elif resp.status_code != 200:
                    await ctx.send(f"> `!` **Invite OSINT:** Discord API error `{resp.status_code}`.", delete_after=5)
                    return
                
                data = resp.json()

            guild = data.get("guild", {})
            channel = data.get("channel", {})
            inviter = data.get("inviter", {})
            
            guild_id = guild.get("id", "Unknown")
            guild_name = guild.get("name", "Direct DM / Group")
            total_members = data.get("approximate_member_count", "N/A")
            presence_count = data.get("approximate_presence_count", "N/A")
            verification_level = guild.get("verification_level", "Unknown")
            nsfw_level = guild.get("nsfw_level", "Unknown")
            features = ", ".join(f"`{f}`" for f in guild.get("features", [])[:6]) or "None"
            vanity = guild.get("vanity_url_code", "None")

            # Calculate guild snowflake creation timestamp
            guild_created_ts = None
            if str(guild_id).isdigit():
                created_ms = (int(guild_id) >> 22) + 1420070400000
                guild_created_ts = int(created_ms / 1000)

            channel_name = channel.get("name", "Unknown")
            channel_id = channel.get("id", "Unknown")

            expires_at = data.get("expires_at")
            expires_str = "Never / Permanent" if not expires_at else f"`{expires_at}`"

            lines = [
                f"> `-` **Discord Invite Deep Intelligence**",
                f"> `—` **Invite Code:** `{code}`",
                f"> `—` **Guild Name:** **{guild_name}** (`{guild_id}`)",
            ]
            if guild_created_ts:
                lines.append(f"> `—` **Guild Created:** <t:{guild_created_ts}:F> (<t:{guild_created_ts}:R>)")
            
            lines.extend([
                f"> `—` **Members:** `{total_members:,}` total · `{presence_count:,}` online" if isinstance(total_members, int) else f"> `—` **Members:** `{total_members}`",
                f"> `—` **Target Channel:** `#{channel_name}` (`{channel_id}`)",
                f"> `—` **Expires:** {expires_str}",
                f"> `—` **Verification Level:** `{verification_level}` · **NSFW Level:** `{nsfw_level}`",
                f"> `—` **Vanity Code:** `{vanity}`",
                f"> `—` **Guild Features:** {features}",
            ])

            if inviter:
                inv_name = inviter.get("username", "Unknown")
                inv_id = inviter.get("id", "Unknown")
                lines.append(f"> `—` **Created By:** `{inv_name}` (`{inv_id}`)")

            if guild.get("icon"):
                icon_hash = guild["icon"]
                icon_url = f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png?size=1024"
                lines.append(f"> `—` **Icon Asset:** [Server Icon]({icon_url})")
            
            if guild.get("splash"):
                splash_hash = guild["splash"]
                splash_url = f"https://cdn.discordapp.com/splashes/{guild_id}/{splash_hash}.png?size=1024"
                lines.append(f"> `—` **Invite Splash:** [Splash Image]({splash_url})")

            if guild.get("banner"):
                banner_hash = guild["banner"]
                banner_url = f"https://cdn.discordapp.com/banners/{guild_id}/{banner_hash}.png?size=1024"
                lines.append(f"> `—` **Server Banner:** [Banner Image]({banner_url})")

            await ctx.send("\n".join(lines))
        except Exception as e:
            await ctx.send(f"> `!` **Invite OSINT Error:** `{e}`", delete_after=6)

    # ── Automation & Sniper Listeners ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.bot.user:
            return

        # 1. Nitro Sniper Listener
        if self._nitro_enabled and message.author.id != self.bot.user.id:
            codes = GIFT_RE.findall(message.content)
            for code in codes:
                if code not in self._sniped_codes:
                    self._sniped_codes.add(code)
                    log_info(f"Nitro sniper: Detected code {code[:6]}… in #{message.channel}")
                    t0 = time.monotonic()
                    try:
                        token_val = getattr(self.bot.http, "token", "") or settings.discord_token
                        async with httpx.AsyncClient(timeout=8) as client:
                            resp = await client.post(
                                REDEEM_URL.format(code=code),
                                headers={"Authorization": token_val},
                                json={"channel_id": str(message.channel.id)},
                            )
                        ms = round((time.monotonic() - t0) * 1000)
                        if resp.status_code == 200:
                            log_info(f"Nitro sniped in {ms}ms! 🎉")
                            await message.channel.send(f"🎉 Nitro sniped in `{ms}ms`!")
                        elif resp.status_code == 429:
                            log_warn(f"Nitro sniper rate-limited ({ms}ms)")
                    except Exception as e:
                        log_err(f"Nitro sniper request error: {e}")

        # 2. Channel Auto-react & Auto-reply
        if message.author.id == self.bot.user.id:
            # 3. DM Privacy Mode: Check duration expiry & track outgoing DM messages
            if self._privacy_enabled:
                if self._privacy_until and time.monotonic() >= self._privacy_until:
                    self._privacy_enabled = False
                    self._privacy_until = None
                    log_info("DM Privacy mode auto-disabled (duration expired).")

                if message.guild is None or isinstance(message.channel, discord.DMChannel):
                    if not message.content.startswith(P):
                        self._pending_privacy_messages.setdefault(message.channel.id, []).append(message.id)
            return

        # 3. DM Privacy Mode: Incoming DM message from other party -> wipe all seen messages
        if self._privacy_enabled:
            if message.guild is None or isinstance(message.channel, discord.DMChannel):
                await self._wipe_dm_seen_messages(message.channel.id)

        emojis = self._auto_react.get(message.channel.id, [])
        for em in emojis:
            try:
                await message.add_reaction(em)
                await asyncio.sleep(0.25)
                footprint.record_action(message.channel.id)
            except Exception:
                pass

        rules = self._auto_reply.get(message.channel.id, [])
        for r in rules:
            matched = False
            if r.is_regex:
                try:
                    matched = bool(re.search(r.trigger, message.content, re.IGNORECASE))
                except re.error:
                    pass
            elif r.exact_match:
                matched = message.content.strip().lower() == r.trigger.lower()
            else:
                matched = r.trigger.lower() in message.content.lower()

            if matched:
                if footprint.is_spamming(message.channel.id):
                    break
                try:
                    await asyncio.sleep(footprint._delay_min)
                    await message.channel.send(r.response)
                    footprint.record_action(message.channel.id)
                except Exception:
                    pass
                break

    async def _wipe_dm_seen_messages(self, channel_id: int) -> None:
        """Immediately delete pending outgoing messages in a DM once seen."""
        msg_ids = self._pending_privacy_messages.pop(channel_id, [])

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return

        # Delete tracked messages
        for mid in msg_ids:
            try:
                msg = getattr(self.bot, "_connection", None)
                message = msg._get_message(mid) if msg else None
                if message is None:
                    message = await channel.fetch_message(mid)
                if message and self.bot.user and message.author.id == self.bot.user.id:
                    await message.delete()
                    await asyncio.sleep(0.2)
            except Exception:
                pass

        # Scan and purge any recent own messages in this DM to guarantee zero residual messages
        try:
            async for m in channel.history(limit=10):
                if self.bot.user and m.author.id == self.bot.user.id:
                    try:
                        await m.delete()
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_typing(self, channel: discord.abc.Messageable, user: discord.User | discord.Member, when: datetime) -> None:
        """Wipe DM messages immediately when recipient starts typing (seen indicator)."""
        if not self._privacy_enabled or not self.bot.user:
            return
        if getattr(channel, "guild", None) is not None:
            return
        if user.id == self.bot.user.id:
            return
        await self._wipe_dm_seen_messages(channel.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Wipe DM messages immediately when recipient reacts to a message (seen indicator)."""
        if not self._privacy_enabled or not self.bot.user:
            return
        if payload.guild_id is not None:
            return
        if payload.user_id == self.bot.user.id:
            return
        await self._wipe_dm_seen_messages(payload.channel_id)

    @commands.Cog.listener()
    async def on_raw_message_ack(self, raw: Any) -> None:
        """Wipe DM messages immediately upon gateway read acknowledgment event."""
        if not self._privacy_enabled or not self.bot.user:
            return
        channel_id = getattr(raw, "channel_id", None)
        if channel_id and (channel_id in self._pending_privacy_messages or self.bot.get_channel(channel_id) is None):
            await self._wipe_dm_seen_messages(channel_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tools(bot))
