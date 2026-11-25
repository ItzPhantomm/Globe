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
import base64
import re
import socket
import time
from collections import deque
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


# ── Morse Code Translation Tables ─────────────────────────────────────────────

MORSE_MAP: dict[str, str] = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....",
    "6": "-....", "7": "--...", "8": "---..", "9": "----.", "0": "-----",
    ",": "--..--", ".": ".-.-.-", "?": "..--..", "/": "-..-.", "-": "-....-",
    "(": "-.--.", ")": "-.--.-", "!": "-.-.--", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "_": "..--.-", '"': ".-..-.",
    "$": "...-..-", "@": ".--.-.", "'": ".----.",
}
REVERSE_MORSE_MAP: dict[str, str] = {v: k for k, v in MORSE_MAP.items()}


class Tools(commands.Cog):
    """Network inspection, token auditing, nitro sniper, reminders & automation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._http_client: httpx.AsyncClient | None = None
        self._reminders: list[asyncio.Task] = []
        self._nitro_enabled: bool = settings.nitro_sniper
        self._sniped_codes: set[str] = set()
        self._auto_react: dict[int, list[str]] = {}
        self._auto_reply: dict[int, list[AutoReplyRule]] = {}
        self._privacy_enabled: bool = False
        self._privacy_until: float | None = None
        self._pending_privacy_messages: dict[int, list[int]] = {}
        self._ghost_pings: deque[dict[str, Any]] = deque(maxlen=50)
        self._stalk_targets: set[int] = set()
        self._stalk_logs: deque[dict[str, Any]] = deque(maxlen=100)
        self._gsniper_enabled: bool = False
        self._gsniper_entered: set[int] = set()
        self._schedules: dict[int, dict[str, Any]] = {}
        self._schedule_seq: int = 0
        self._alert_webhook: str | None = None
        self._keywords: set[str] = set()
        self._keyword_hits: deque[dict[str, Any]] = deque(maxlen=50)
        self._vanity_task: asyncio.Task | None = None
        self._vanity_target: str | None = None
        self._hydrate_state()

    def _hydrate_state(self) -> None:
        """Restore persisted flags/lists from SQLite so settings survive restarts."""
        import json
        try:
            from data.tracker import tracker
            if wh := tracker.get_state("alert_webhook"):
                self._alert_webhook = wh
            if raw_kw := tracker.get_state("keywords"):
                self._keywords = set(json.loads(raw_kw))
            if raw_st := tracker.get_state("stalk_targets"):
                self._stalk_targets = {int(x) for x in json.loads(raw_st)}
            if tracker.get_state("gsniper_enabled") == "1":
                self._gsniper_enabled = True
            if tracker.get_state("privacy_enabled") == "1":
                self._privacy_enabled = True
        except Exception:
            pass

    def _save_state(self) -> None:
        """Persist active surveillance/automation flags to SQLite."""
        import json
        try:
            from data.tracker import tracker
            tracker.set_state("alert_webhook", self._alert_webhook or "")
            tracker.set_state("keywords", json.dumps(sorted(self._keywords)))
            tracker.set_state("stalk_targets", json.dumps(sorted(self._stalk_targets)))
            tracker.set_state("gsniper_enabled", "1" if self._gsniper_enabled else "0")
            tracker.set_state("privacy_enabled", "1" if self._privacy_enabled else "0")
        except Exception:
            pass

    async def _resolve_input(self, ctx: commands.Context, text: str | None) -> str | None:
        """Return provided text or content of replied-to message."""
        if text:
            return text.strip()
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                return ref_msg.content.strip()
            except Exception:
                return None
        return None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Provide a persistent, connection-pooled HTTP client instance."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        return self._http_client

    async def cog_unload(self) -> None:
        """Release persistent HTTP client connections on module reload."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

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
            client = self._get_http_client()
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
            client = self._get_http_client()
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
            client = self._get_http_client()
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
            client = self._get_http_client()
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
            client = self._get_http_client()
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
            client = self._get_http_client()
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

    # ── Morse Code Converter & Decoder ────────────────────────────────────────

    @commands.command(name="morse", aliases=["morsecode", "morsify"])
    async def morse(self, ctx: commands.Context, *, text: str | None = None) -> None:
        """
        Convert text to Morse code or decode Morse code into plain text.
        Auto-detects whether the input is text or Morse code.
        Can be used by replying to a message or providing text directly.
        """
        await ctx.message.delete()
        raw_text = text
        if not raw_text and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                raw_text = ref_msg.content.strip()
            except Exception:
                pass

        if not raw_text:
            msg = await ctx.send(f"> `!` **Usage:** `{settings.prefix}morse <text or morse code>` *(or reply to a message)*")
            await msg.delete(delay=5)
            return

        cleaned_check = set(raw_text.replace(" ", "").replace("/", "").replace("|", "").replace("-", "").replace(".", ""))
        is_morse = len(cleaned_check) == 0 and ("." in raw_text or "-" in raw_text)

        if is_morse:
            clean = raw_text.replace(" / ", " | ").replace("   ", " | ")
            words = clean.split("|")
            decoded_words: list[str] = []
            for w in words:
                tokens = w.strip().split()
                chars = [REVERSE_MORSE_MAP.get(token, "?") for token in tokens if token]
                if chars:
                    decoded_words.append("".join(chars))
            result = " ".join(decoded_words)
            action = "Decoded (Morse → Text)"
        else:
            words = raw_text.upper().split(" ")
            morse_words: list[str] = []
            for w in words:
                morse_chars = [MORSE_MAP[c] for c in w if c in MORSE_MAP]
                if morse_chars:
                    morse_words.append(" ".join(morse_chars))
            result = " / ".join(morse_words)
            action = "Encoded (Text → Morse)"

        lines = [
            f"> `-` **Morse Code Converter** · *{action}*",
            f"> `—` **Input:** `{raw_text[:120]}`",
            f"> `•` **Result:** `{result}`",
            f"> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="demorse", aliases=["unmorse", "morsedecode"])
    async def demorse(self, ctx: commands.Context, *, morse_input: str | None = None) -> None:
        """Decode Morse code into readable plain text."""
        await ctx.message.delete()
        raw_code = morse_input
        if not raw_code and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                raw_code = ref_msg.content.strip()
            except Exception:
                pass

        if not raw_code:
            msg = await ctx.send(f"> `!` **Usage:** `{settings.prefix}demorse <morse code>` *(or reply to a message)*")
            await msg.delete(delay=5)
            return

        clean = raw_code.replace(" / ", " | ").replace("   ", " | ")
        words = clean.split("|")
        decoded_words: list[str] = []
        for w in words:
            tokens = w.strip().split()
            chars = [REVERSE_MORSE_MAP.get(token, "?") for token in tokens if token]
            if chars:
                decoded_words.append("".join(chars))
        result = " ".join(decoded_words)

        lines = [
            "> `-` **Morse Code Decoder**",
            f"> `—` **Code:** `{raw_code[:120]}`",
            f"> `•` **Plaintext:** `{result}`",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="b64", aliases=["base64"])
    async def b64(self, ctx: commands.Context, mode: str | None = None, *, text: str | None = None) -> None:
        """
        Base64 encode/decode. Usage: `g.b64 <text>` (auto) or `g.b64 encode|decode <text>`.
        """
        await ctx.message.delete()
        if mode and mode.lower() in ("encode", "enc", "e", "decode", "dec", "d"):
            action_mode = mode.lower()
            raw = await self._resolve_input(ctx, text)
        else:
            action_mode = "auto"
            combined = f"{mode} {text}".strip() if (mode and text) else mode
            raw = await self._resolve_input(ctx, combined)

        if not raw:
            await ctx.send(f"> `!` **Usage:** `{settings.prefix}b64 [encode|decode] <text>`", delete_after=5)
            return

        if action_mode in ("decode", "dec", "d"):
            try:
                res = base64.b64decode(raw.encode("utf-8"), validate=True).decode("utf-8")
                label = "Decoded (Base64 → Text)"
            except Exception as e:
                await ctx.send(f"> `!` **Base64 Decode Error:** `{e}`", delete_after=5)
                return
        elif action_mode in ("encode", "enc", "e"):
            res = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
            label = "Encoded (Text → Base64)"
        else:
            # Auto-detect valid padded Base64 printable UTF-8
            try:
                decoded_bytes = base64.b64decode(raw.encode("utf-8"), validate=True)
                decoded_str = decoded_bytes.decode("utf-8")
                if decoded_str.isprintable() and len(raw) >= 4 and len(raw) % 4 == 0:
                    res = decoded_str
                    label = "Decoded (Base64 → Text)"
                else:
                    raise ValueError
            except Exception:
                res = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
                label = "Encoded (Text → Base64)"

        await ctx.send("\n".join([
            f"> `-` **Base64 Converter** · *{label}*",
            f"> `—` **Input:** `{raw[:120]}`",
            f"> `•` **Result:** `{res[:1500]}`",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]))

    @commands.command(name="hex", aliases=["hexify", "unhex"])
    async def hex_cmd(self, ctx: commands.Context, *, text: str | None = None) -> None:
        """Auto-detecting UTF-8 ↔ Hexadecimal converter."""
        await ctx.message.delete()
        raw = await self._resolve_input(ctx, text)
        if not raw:
            await ctx.send(f"> `!` **Usage:** `{settings.prefix}hex <text or hex>`", delete_after=5)
            return

        compact = raw.replace(" ", "").removeprefix("0x")
        if len(compact) >= 2 and len(compact) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in compact):
            try:
                res = bytes.fromhex(compact).decode("utf-8")
                label = "Decoded (Hex → Text)"
            except Exception:
                res = raw.encode("utf-8").hex(" ")
                label = "Encoded (Text → Hex)"
        else:
            res = raw.encode("utf-8").hex(" ")
            label = "Encoded (Text → Hex)"

        await ctx.send("\n".join([
            f"> `-` **Hex Converter** · *{label}*",
            f"> `—` **Input:** `{raw[:120]}`",
            f"> `•` **Result:** `{res[:1500]}`",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]))

    @commands.command(name="bin", aliases=["binary", "unbin"])
    async def bin_cmd(self, ctx: commands.Context, *, text: str | None = None) -> None:
        """Auto-detecting Text ↔ 8-bit Binary converter."""
        await ctx.message.delete()
        raw = await self._resolve_input(ctx, text)
        if not raw:
            await ctx.send(f"> `!` **Usage:** `{settings.prefix}bin <text or binary>`", delete_after=5)
            return

        bits = raw.replace(" ", "")
        if len(bits) >= 8 and len(bits) % 8 == 0 and set(bits).issubset({"0", "1"}):
            try:
                res = "".join(chr(int(bits[i:i + 8], 2)) for i in range(0, len(bits), 8))
                label = "Decoded (Binary → Text)"
            except Exception:
                res = " ".join(format(b, "08b") for b in raw.encode("utf-8"))
                label = "Encoded (Text → Binary)"
        else:
            res = " ".join(format(b, "08b") for b in raw.encode("utf-8"))
            label = "Encoded (Text → Binary)"

        await ctx.send("\n".join([
            f"> `-` **Binary Converter** · *{label}*",
            f"> `—` **Input:** `{raw[:120]}`",
            f"> `•` **Result:** `{res[:1500]}`",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]))

    # ── Passive Intelligence: Ghost-Ping Radar & Mutuals OSINT ───────────────

    @commands.command(name="radar", aliases=["ghostpings", "pings", "gpradar"])
    async def radar(self, ctx: commands.Context, action: str | None = None) -> None:
        """
        Inspect caught ghost-pings (`@you`, `@everyone`, `@here`, or your roles) across all servers.
        Use `g.radar clear` to wipe the log.
        """
        await ctx.message.delete()
        if action and action.lower() in ("clear", "wipe", "reset"):
            self._ghost_pings.clear()
            await ctx.send("> `-` **Ghost-Ping Radar Cleared.**", delete_after=4)
            return

        if not self._ghost_pings:
            await ctx.send("> `-` **Ghost-Ping Radar:** No deleted mentions recorded yet.", delete_after=6)
            return

        lines = [f"> `-` **Ghost-Ping Radar ({len(self._ghost_pings)} caught)**"]
        for entry in list(self._ghost_pings)[-8:][::-1]:
            lines.append(
                f"> `—` **{entry['author']}** in **{entry['where']}** (<t:{entry['ts']}:R>): `{entry['content'][:140]}`"
            )
        lines.append("> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**")
        await ctx.send("\n".join(lines), delete_after=25)

    @commands.command(name="mutuals", aliases=["shared", "finduser"])
    async def mutuals(self, ctx: commands.Context, *, user: discord.User) -> None:
        """Scan all mutual guilds for a user's nickname, top role, status, and live voice channel."""
        await ctx.message.delete()
        shared_lines: list[str] = []
        active_vc: str | None = None
        status_str = "offline"

        for guild in self.bot.guilds:
            m = guild.get_member(user.id)
            if not m:
                continue
            if str(m.status) != "offline":
                status_str = str(m.status)
            nick = f" (nick: `{m.nick}`)" if m.nick else ""
            top_role = m.top_role.name if m.top_role and not m.top_role.is_default() else "none"
            vc_tag = ""
            if m.voice and m.voice.channel:
                vc_tag = f" · 🔊 `{m.voice.channel.name}`"
                active_vc = f"**{guild.name}** → `#{m.voice.channel.name}`"
            shared_lines.append(f"> `—` **{guild.name}**{nick} · role `{top_role}`{vc_tag}")

        header = [
            f"> `-` **Mutuals OSINT:** **{user}** (`{user.id}`)",
            f"> `•` **Shared Guilds:** `{len(shared_lines)}` · **Status:** `{status_str}`",
        ]
        if active_vc:
            header.append(f"> `•` **Live Voice:** {active_vc}")

        body = shared_lines[:15] if shared_lines else ["> `—` *No mutual servers in cache.*"]
        footer = ["> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**"]
        await ctx.send("\n".join(header + body + footer), delete_after=25)

    # ── Relationship Backup & Unfriend/Block Detector ─────────────────────────

    @staticmethod
    def _diff_relationships(
        old_friends: dict[str, dict[str, str]],
        new_friends: dict[str, dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Return (removed, added) friend records between two {uid: info} snapshots."""
        removed = [old_friends[uid] for uid in old_friends if uid not in new_friends]
        added = [new_friends[uid] for uid in new_friends if uid not in old_friends]
        return removed, added

    def _snapshot_friends(self) -> dict[str, dict[str, str]]:
        friends: dict[str, dict[str, str]] = {}
        for rel in getattr(self.bot, "friends", []) or []:
            u = getattr(rel, "user", rel)
            uid = str(getattr(u, "id", ""))
            if uid:
                friends[uid] = {
                    "id": uid,
                    "username": str(getattr(u, "name", u)),
                    "global_name": str(getattr(u, "global_name", "") or ""),
                }
        return friends

    @commands.command(name="friendsbackup", aliases=["backupfriends", "fbackup"])
    async def friendsbackup(self, ctx: commands.Context) -> None:
        """Snapshot your current Discord friends list to `data/backups/friends.json`."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        import json
        from pathlib import Path

        snap = self._snapshot_friends()
        out_dir = Path("data") / "backups"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "friends.json"
        out_file.write_text(json.dumps({"ts": int(time.time()), "friends": snap}, indent=2), encoding="utf-8")

        await ctx.send(
            f"> `-` **Friends Snapshot Saved:** `{len(snap)}` friends archived to `{out_file}`.",
            delete_after=8,
        )

    @commands.command(name="friendsdiff", aliases=["unfriended", "fdiff", "whounfriended"])
    async def friendsdiff(self, ctx: commands.Context) -> None:
        """Compare live friends against your last snapshot to expose silent unfriends/blocks."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        import json
        from pathlib import Path

        out_file = Path("data") / "backups" / "friends.json"
        if not out_file.exists():
            snap = self._snapshot_friends()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps({"ts": int(time.time()), "friends": snap}, indent=2), encoding="utf-8")
            await ctx.send(
                f"> `-` **Baseline Created:** `{len(snap)}` friends saved. Run `{settings.prefix}friendsdiff` later to detect changes.",
                delete_after=8,
            )
            return

        old_data = json.loads(out_file.read_text(encoding="utf-8"))
        old_friends = old_data.get("friends", {})
        cur_friends = self._snapshot_friends()
        removed, added = self._diff_relationships(old_friends, cur_friends)

        lines = [
            f"> `-` **Relationship Diff** · *Baseline <t:{old_data.get('ts', 0)}:R>*",
            f"> `•` **Current Friends:** `{len(cur_friends)}` (was `{len(old_friends)}`)",
        ]
        if removed:
            rem_str = ", ".join(f"**{r['username']}** (`{r['id']}`)" for r in removed[:10])
            lines.append(f"> `—` **Removed / Unfriended ({len(removed)}):** {rem_str}")
        else:
            lines.append("> `—` **Removed / Unfriended:** `0`")
        if added:
            add_str = ", ".join(f"**{a['username']}** (`{a['id']}`)" for a in added[:10])
            lines.append(f"> `—` **Newly Added ({len(added)}):** {add_str}")
        lines.append("> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**")
        await ctx.send("\n".join(lines), delete_after=25)

    # ── Real-Time User Stalker ────────────────────────────────────────────────

    @commands.command(name="stalk", aliases=["watchuser", "trackuser"])
    async def stalk(self, ctx: commands.Context, target: str) -> None:
        """
        Monitor a user's username, display name, avatar, and online transitions.
        Pass `off` / `clear` to stop all tracking, or a user to toggle.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        if target.lower() in ("off", "clear", "stop"):
            self._stalk_targets.clear()
            self._save_state()
            await ctx.send("> `-` **User Stalker Cleared.**", delete_after=4)
            return
        try:
            user = await commands.UserConverter().convert(ctx, target)
        except Exception:
            await ctx.send(f"> `!` **User not found:** `{target}`", delete_after=4)
            return
        if user.id in self._stalk_targets:
            self._stalk_targets.remove(user.id)
            self._save_state()
            await ctx.send(f"> `-` **Stopped Stalking:** **{user}** (`{user.id}`).", delete_after=5)
        else:
            self._stalk_targets.add(user.id)
            self._save_state()
            await ctx.send(f"> `-` **Now Stalking:** **{user}** (`{user.id}`) · use `{settings.prefix}stalklog` to view events.", delete_after=6)

    @commands.command(name="stalklog", aliases=["stalklogs", "watchlog"])
    async def stalklog(self, ctx: commands.Context, user: discord.User | None = None) -> None:
        """View recorded username, avatar, and status transitions from stalked users."""
        await ctx.message.delete()
        entries = list(self._stalk_logs)
        if user:
            entries = [e for e in entries if e["uid"] == user.id]
        if not entries:
            await ctx.send(f"> `-` **Stalker Log:** No events captured (`{len(self._stalk_targets)}` target(s) armed).", delete_after=6)
            return
        lines = [f"> `-` **Stalker Activity Log ({len(entries)} events)**"]
        for e in entries[-10:][::-1]:
            lines.append(f"> `—` <t:{e['ts']}:R> **{e['user']}**: {e['detail']}")
        lines.append("> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**")
        await ctx.send("\n".join(lines), delete_after=25)

    # ── Giveaway & Drop Sniper ────────────────────────────────────────────────

    @commands.command(name="gsniper", aliases=["giveawaysniper", "gw"])
    async def gsniper(self, ctx: commands.Context, mode: str | None = None) -> None:
        """Toggle automated giveaway sniper (`g.gsniper on|off`). Uses human-jitter delay."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        if mode and mode.lower() in ("on", "enable", "1"):
            self._gsniper_enabled = True
        elif mode and mode.lower() in ("off", "disable", "0"):
            self._gsniper_enabled = False
        else:
            self._gsniper_enabled = not self._gsniper_enabled
        state = "🟢 **ENABLED** *(1.5s–4.5s human jitter)*" if self._gsniper_enabled else "🔴 **DISABLED**"
        await ctx.send(f"> `-` **Giveaway Sniper:** {state}", delete_after=6)

    # ── Recurring Message Scheduler ───────────────────────────────────────────

    @commands.command(name="schedule", aliases=["sched", "autorepeat", "autobump"])
    async def schedule_cmd(self, ctx: commands.Context, interval: str, *, message_text: str) -> None:
        """
        Schedule a recurring message in the current channel (e.g. `g.schedule 2h !d bump`).
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        secs = _parse_duration(interval)
        if not secs or secs < 15:
            await ctx.send("> `!` **Invalid interval.** Minimum `15s` (e.g. `60s`, `15m`, `2h`).", delete_after=5)
            return

        self._schedule_seq += 1
        sid = self._schedule_seq
        ch = ctx.channel

        async def _runner() -> None:
            try:
                while True:
                    await asyncio.sleep(secs)
                    if not footprint.is_spamming(ch.id):
                        try:
                            await ch.send(message_text)
                            footprint.record_action(ch.id)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_runner())
        self._schedules[sid] = {
            "task": task,
            "interval": interval,
            "channel": getattr(ch, "name", str(ch.id)),
            "text": message_text[:60],
        }
        await ctx.send(
            f"> `-` **Schedule `#{sid}` Armed:** Every `{interval}` → `{message_text[:60]}`",
            delete_after=6,
        )

    @commands.command(name="schedules", aliases=["listschedules", "jobs"])
    async def schedules_list(self, ctx: commands.Context) -> None:
        """List active recurring scheduled messages."""
        await ctx.message.delete()
        if not self._schedules:
            await ctx.send("> `-` **Schedules:** None active.", delete_after=5)
            return
        lines = [f"> `-` **Active Schedules ({len(self._schedules)})**"]
        for sid, info in self._schedules.items():
            lines.append(f"> `—` **`#{sid}`** every `{info['interval']}` in `#{info['channel']}`: `{info['text']}`")
        await ctx.send("\n".join(lines), delete_after=15)

    @commands.command(name="unschedule", aliases=["stopschedule", "delschedule"])
    async def unschedule_cmd(self, ctx: commands.Context, schedule_id: str) -> None:
        """Cancel a scheduled message by ID, or pass `all`."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        if schedule_id.lower() == "all":
            count = len(self._schedules)
            for info in self._schedules.values():
                info["task"].cancel()
            self._schedules.clear()
            await ctx.send(f"> `-` **Cancelled all `{count}` schedules.**", delete_after=5)
            return
        try:
            sid = int(schedule_id.lstrip("#"))
            info = self._schedules.pop(sid, None)
            if info:
                info["task"].cancel()
                await ctx.send(f"> `-` **Cancelled Schedule `#{sid}`.**", delete_after=4)
            else:
                await ctx.send(f"> `!` Schedule `#{sid}` not found.", delete_after=4)
        except ValueError:
            await ctx.send(f"> `!` Invalid schedule ID `{schedule_id}`.", delete_after=4)

    # ── Alert Webhook, Global Keyword Notifier, Vanity Watcher & Activity Profiler

    async def _forward_alert(self, title: str, body: str) -> None:
        """Forward high-priority events (radar/stalk/keywords) to configured private webhook."""
        if not self._alert_webhook:
            return
        try:
            client = self._get_http_client()
            await client.post(
                self._alert_webhook,
                json={"content": f"**[Globe Alert] {title}**\n{body[:1800]}"},
            )
        except Exception:
            pass

    @commands.command(name="alertwebhook", aliases=["logwebhook", "setalert"])
    async def alertwebhook(self, ctx: commands.Context, webhook_url: str) -> None:
        """Configure or disable (`off`) a private Discord webhook for radar/stalk/keyword alerts."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        if webhook_url.lower() in ("off", "clear", "none", "stop"):
            self._alert_webhook = None
            self._save_state()
            await ctx.send("> `-` **Alert Webhook Disabled.**", delete_after=4)
            return
        if not webhook_url.startswith("https://"):
            await ctx.send("> `!` Provide a valid Discord webhook URL.", delete_after=4)
            return
        self._alert_webhook = webhook_url.strip()
        self._save_state()
        await ctx.send("> `-` **Alert Webhook Armed:** Forwarding radar, stalk & keyword hits.", delete_after=5)

    @commands.command(name="kw", aliases=["keyword", "keywords", "watchword"])
    async def kw(self, ctx: commands.Context, action: str = "list", *, phrase: str = "") -> None:
        """
        Global keyword sniper across all servers.
        Syntax: `g.kw add <phrase>`, `g.kw del <phrase>`, `g.kw list`, `g.kw clear`
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        act = action.lower()
        if act == "add" and phrase.strip():
            self._keywords.add(phrase.strip().lower())
            self._save_state()
            await ctx.send(f"> `-` **Keyword Armed:** `{phrase.strip().lower()}`", delete_after=5)
        elif act in ("del", "remove", "rm") and phrase.strip():
            self._keywords.discard(phrase.strip().lower())
            self._save_state()
            await ctx.send(f"> `-` **Keyword Removed:** `{phrase.strip().lower()}`", delete_after=5)
        elif act == "clear":
            self._keywords.clear()
            self._save_state()
            await ctx.send("> `-` **All Keywords Cleared.**", delete_after=4)
        else:
            kw_list = ", ".join(f"`{k}`" for k in sorted(self._keywords)) or "*none*"
            await ctx.send(f"> `-` **Watched Keywords ({len(self._keywords)}):** {kw_list}", delete_after=12)

    @commands.command(name="kwlog", aliases=["keywordlog", "kwhits"])
    async def kwlog(self, ctx: commands.Context) -> None:
        """View recent global keyword hits."""
        await ctx.message.delete()
        if not self._keyword_hits:
            await ctx.send("> `-` **Keyword Hits:** None recorded.", delete_after=5)
            return
        lines = [f"> `-` **Keyword Hits ({len(self._keyword_hits)})**"]
        for h in list(self._keyword_hits)[-8:][::-1]:
            lines.append(f"> `—` **{h['kw']}** by **{h['author']}** (<t:{h['ts']}:R>): `{h['content'][:100]}` [Jump]({h['jump']})")
        await ctx.send("\n".join(lines), delete_after=20)

    @commands.command(name="vanitywatch", aliases=["vanity", "snipervanity"])
    async def vanitywatch(self, ctx: commands.Context, code_or_invite: str, target_guild_id: int | None = None, interval: float = 8.0) -> None:
        """
        Monitor a Discord vanity URL code and alert (or auto-claim on a Boost Lvl 3 guild) if it drops.
        """
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        code = code_or_invite.rstrip("/").split("/")[-1].strip()
        if not code:
            return
        delay = max(5.0, min(interval, 60.0))
        if self._vanity_task and not self._vanity_task.done():
            self._vanity_task.cancel()

        self._vanity_target = code
        ch = ctx.channel

        async def _poll_vanity() -> None:
            client = self._get_http_client()
            token_val = getattr(self.bot.http, "token", "") or settings.discord_token
            try:
                while True:
                    resp = await client.get(f"https://discord.com/api/v9/invites/{code}")
                    if resp.status_code == 404:
                        claim_note = "Alert only (no target guild set)."
                        if target_guild_id and token_val:
                            claim = await client.patch(
                                f"https://discord.com/api/v9/guilds/{target_guild_id}/vanity-url",
                                headers={"Authorization": token_val},
                                json={"code": code},
                            )
                            claim_note = f"Auto-claim HTTP `{claim.status_code}`!"
                        msg_txt = f"> `-` **VANITY DROPPED:** `discord.gg/{code}` returned `404`! ({claim_note})"
                        try:
                            await ch.send(msg_txt)
                        except Exception:
                            pass
                        await self._forward_alert(f"Vanity `{code}` Dropped", claim_note)
                        break
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                pass

        self._vanity_task = asyncio.create_task(_poll_vanity())
        await ctx.send(
            f"> `-` **Vanity Watch Armed:** `discord.gg/{code}` every `{delay:.0f}s`.",
            delete_after=6,
        )

    @commands.command(name="vanitystop", aliases=["stopvanity"])
    async def vanitystop(self, ctx: commands.Context) -> None:
        """Stop active vanity URL monitoring."""
        await ctx.message.delete()
        if self._vanity_task and not self._vanity_task.done():
            self._vanity_task.cancel()
            self._vanity_task = None
            await ctx.send(f"> `-` **Vanity Watch Stopped** (`{self._vanity_target}`).", delete_after=4)
        else:
            await ctx.send("> `!` No vanity watch active.", delete_after=4)

    @staticmethod
    def _compute_activity_profile(timestamps: list[float]) -> tuple[str, int]:
        """Return (peak_window_utc_str, peak_hour) from epoch timestamps."""
        if not timestamps:
            return "Unknown", 0
        buckets = [0] * 24
        for ts in timestamps:
            hr = datetime.utcfromtimestamp(ts).hour
            buckets[hr] += 1
        peak_hr = max(range(24), key=lambda h: buckets[h])
        end_hr = (peak_hr + 4) % 24
        return f"{peak_hr:02d}:00–{end_hr:02d}:00 UTC", peak_hr

    @commands.command(name="activity", aliases=["tzprofile", "activehours", "sleepcheck"])
    async def activity_cmd(self, ctx: commands.Context, target: discord.User, count: int = 1000) -> None:
        """Gather up to N messages (default 1000) by a user in this channel to profile active hours & timezone."""
        await ctx.message.delete()
        target_goal = max(10, min(count, 1000))
        max_scan = 10000
        status_msg = await ctx.send(f"> `-` **Profiling {target}:** Gathering up to `{target_goal}` messages…")

        timestamps: list[float] = []
        scanned = 0
        async for m in ctx.channel.history(limit=max_scan):
            if m.id == status_msg.id:
                continue
            scanned += 1
            if m.author.id == target.id and m.created_at:
                timestamps.append(m.created_at.timestamp())
                if len(timestamps) >= target_goal:
                    break
            if scanned % 1000 == 0:
                try:
                    await status_msg.edit(
                        content=f"> `-` **Profiling {target}:** `{len(timestamps)}/{target_goal}` collected (`{scanned}` scanned)…"
                    )
                except Exception:
                    pass

        if not timestamps:
            await status_msg.edit(content=f"> `!` No messages from **{target}** in the last `{scanned}` messages here.")
            await status_msg.delete(delay=5)
            return

        peak_window, peak_hr = self._compute_activity_profile(timestamps)
        # Heuristic: typical afternoon/evening peak is ~18:00 local time
        est_offset = ((18 - peak_hr + 12) % 24) - 12
        sign = "+" if est_offset >= 0 else ""
        lines = [
            f"> `-` **Activity & Timezone Profiler:** **{target}**",
            f"> `—` **User Messages Collected:** `{len(timestamps)}` (scanned `{scanned}` total)",
            f"> `—` **Peak Active Window:** `{peak_window}`",
            f"> `•` **Estimated Timezone:** `UTC{sign}{est_offset}` *(heuristic)*",
            "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
        ]
        await status_msg.edit(content="\n".join(lines))
        await status_msg.delete(delay=25)

    # ── Friend Request Hygiene, Webhook Inspector & QR Generator ──────────────

    @commands.command(name="acceptfriends", aliases=["acceptall", "acceptreqs"])
    async def acceptfriends(self, ctx: commands.Context) -> None:
        """Accept all pending incoming Discord friend requests."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        token_val = getattr(self.bot.http, "token", "") or settings.discord_token
        client = self._get_http_client()
        accepted = 0
        try:
            resp = await client.get(
                "https://discord.com/api/v9/users/@me/relationships",
                headers={"Authorization": token_val},
            )
            if resp.status_code != 200:
                await ctx.send(f"> `!` Relationships API HTTP `{resp.status_code}`.", delete_after=5)
                return
            for rel in resp.json():
                if rel.get("type") == 3:  # Incoming friend request
                    put_r = await client.put(
                        f"https://discord.com/api/v9/users/@me/relationships/{rel['id']}",
                        headers={"Authorization": token_val},
                        json={},
                    )
                    if put_r.status_code in (200, 204):
                        accepted += 1
                    await asyncio.sleep(0.5)
            await ctx.send(f"> `-` **Accepted `{accepted}` incoming friend requests.**", delete_after=6)
        except Exception as e:
            await ctx.send(f"> `!` **Accept Friends Error:** `{e}`", delete_after=5)

    @commands.command(name="clearoutgoing", aliases=["cancelreqs", "clearreqs"])
    async def clearoutgoing(self, ctx: commands.Context) -> None:
        """Cancel all pending outgoing friend requests."""
        await ctx.message.delete()
        if not self.bot.is_owner_id(ctx.author.id):
            return
        token_val = getattr(self.bot.http, "token", "") or settings.discord_token
        client = self._get_http_client()
        cancelled = 0
        try:
            resp = await client.get(
                "https://discord.com/api/v9/users/@me/relationships",
                headers={"Authorization": token_val},
            )
            if resp.status_code != 200:
                await ctx.send(f"> `!` Relationships API HTTP `{resp.status_code}`.", delete_after=5)
                return
            for rel in resp.json():
                if rel.get("type") == 4:  # Outgoing friend request
                    del_r = await client.delete(
                        f"https://discord.com/api/v9/users/@me/relationships/{rel['id']}",
                        headers={"Authorization": token_val},
                    )
                    if del_r.status_code in (200, 204):
                        cancelled += 1
                    await asyncio.sleep(0.5)
            await ctx.send(f"> `-` **Cancelled `{cancelled}` outgoing friend requests.**", delete_after=6)
        except Exception as e:
            await ctx.send(f"> `!` **Clear Outgoing Error:** `{e}`", delete_after=5)

    @commands.command(name="webhookinfo", aliases=["whinfo", "checkwebhook"])
    async def webhookinfo(self, ctx: commands.Context, webhook_url: str) -> None:
        """Inspect a Discord webhook URL without posting any message."""
        await ctx.message.delete()
        if "discord.com/api/webhooks" not in webhook_url:
            await ctx.send("> `!` Invalid Discord webhook URL.", delete_after=4)
            return
        try:
            client = self._get_http_client()
            resp = await client.get(webhook_url.strip())
            if resp.status_code != 200:
                await ctx.send(f"> `!` Webhook returned HTTP `{resp.status_code}`.", delete_after=5)
                return
            d = resp.json()
            lines = [
                "> `-` **Webhook Inspection**",
                f"> `—` **Name:** **{d.get('name')}** (`{d.get('id')}`)",
                f"> `—` **Guild ID:** `{d.get('guild_id')}` · **Channel ID:** `{d.get('channel_id')}`",
                f"> `•` **Type:** `{d.get('type')}` · **App ID:** `{d.get('application_id') or 'None'}`",
                "> `°` **__Globe__ — Minimal, Clean & Polished Architecture.**",
            ]
            await ctx.send("\n".join(lines), delete_after=20)
        except Exception as e:
            await ctx.send(f"> `!` **Webhook Info Error:** `{e}`", delete_after=5)

    @commands.command(name="qr", aliases=["qrcode"])
    async def qr_cmd(self, ctx: commands.Context, *, payload: str) -> None:
        """Generate a scannable QR code PNG for any URL or text."""
        await ctx.message.delete()
        import io
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=320x320&data={quote_plus(payload[:500])}"
        try:
            client = self._get_http_client()
            resp = await client.get(url)
            if resp.status_code != 200:
                await ctx.send(f"> `!` QR service returned HTTP `{resp.status_code}`.", delete_after=4)
                return
            await ctx.send(
                f"> `-` **QR Code:** `{payload[:80]}`",
                file=discord.File(io.BytesIO(resp.content), filename="qrcode.png"),
            )
        except Exception as e:
            await ctx.send(f"> `!` **QR Error:** `{e}`", delete_after=4)

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
                client = self._get_http_client()
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
            client = self._get_http_client()
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
            if "discord.gift" in message.content or "discord.com/gift" in message.content:
                codes = GIFT_RE.findall(message.content)
                for code in codes:
                    if code not in self._sniped_codes:
                        self._sniped_codes.add(code)
                        log_info(f"Nitro sniper: Detected code {code[:6]}… in #{message.channel}")
                        t0 = time.monotonic()
                        try:
                            token_val = getattr(self.bot.http, "token", "") or settings.discord_token
                            client = self._get_http_client()
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

        # 1b. Giveaway Sniper Listener
        if (
            self._gsniper_enabled
            and message.author.bot
            and message.id not in self._gsniper_entered
            and message.guild is not None
        ):
            embed_blob = " ".join(
                f"{e.title or ''} {e.description or ''}" for e in message.embeds
            ).lower()
            is_giveaway = (
                "giveaway" in embed_blob
                or "giveaway" in message.content.lower()
                or "react with 🎉" in embed_blob
            )
            if is_giveaway:
                self._gsniper_entered.add(message.id)
                import random
                await asyncio.sleep(random.uniform(1.5, 4.5))
                if not footprint.is_spamming(message.channel.id):
                    try:
                        # Try clicking an Enter/Join button first if present, else react 🎉
                        clicked = False
                        for row in getattr(message, "components", []):
                            for comp in getattr(row, "children", []):
                                lbl = (getattr(comp, "label", "") or "").lower()
                                if any(k in lbl for k in ("enter", "join", "participate")):
                                    await comp.click()
                                    clicked = True
                                    break
                            if clicked:
                                break
                        if not clicked:
                            await message.add_reaction("🎉")
                        footprint.record_action(message.channel.id)
                        log_info(f"Giveaway sniper entered {message.id} in #{message.channel}")
                    except Exception:
                        pass

        # 1c. Global Keyword Notifier
        if self._keywords and message.author.id != self.bot.user.id and not message.author.bot and message.content:
            low = message.content.lower()
            for kw in self._keywords:
                if kw in low:
                    self._keyword_hits.append({
                        "kw": kw,
                        "author": str(message.author),
                        "content": message.content[:140],
                        "jump": message.jump_url,
                        "ts": int(time.time()),
                    })
                    asyncio.create_task(self._forward_alert(
                        f"Keyword `{kw}`",
                        f"**{message.author}**: {message.content[:300]}\n{message.jump_url}",
                    ))
                    break

        # 2. Channel Auto-react & Auto-reply
        if message.author.id == self.bot.user.id:
            # 3. DM Privacy Mode: Check duration expiry & track outgoing DM messages
            if self._privacy_enabled:
                if self._privacy_until and time.monotonic() >= self._privacy_until:
                    self._privacy_enabled = False
                    self._privacy_until = None
                    log_info("DM Privacy mode auto-disabled (duration expired).")

                if message.guild is None or isinstance(message.channel, discord.DMChannel):
                    if not message.content.startswith(settings.prefix):
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

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Capture deleted messages that mentioned us, @everyone/@here, or our roles."""
        if not self.bot.user or message.author.bot or message.author.id == self.bot.user.id:
            return
        mentioned = (
            self.bot.user in message.mentions
            or message.mention_everyone
            or (
                message.guild is not None
                and isinstance(me := message.guild.get_member(self.bot.user.id), discord.Member)
                and any(r in message.role_mentions for r in me.roles)
            )
        )
        if not mentioned:
            return
        where = f"{message.guild.name} #{getattr(message.channel, 'name', 'ch')}" if message.guild else "DM"
        content = message.content or ("[Attachment]" if message.attachments else "[Embed]")
        self._ghost_pings.append({
            "author": str(message.author),
            "where": where,
            "content": content,
            "ts": int(time.time()),
        })

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        """Log username, global name, and avatar changes for stalked targets."""
        if after.id not in self._stalk_targets:
            return
        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"username `{before.name}` → `{after.name}`")
        if getattr(before, "global_name", None) != getattr(after, "global_name", None):
            changes.append(f"display `{before.global_name}` → `{after.global_name}`")
        if str(before.display_avatar.url) != str(after.display_avatar.url):
            changes.append(f"avatar changed ([new]({after.display_avatar.url}))")
        if changes:
            self._stalk_logs.append({
                "uid": after.id,
                "user": str(after),
                "detail": "; ".join(changes),
                "ts": int(time.time()),
            })

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """Log online/offline status transitions for stalked targets."""
        if after.id not in self._stalk_targets:
            return
        if str(before.status) != str(after.status):
            # Deduplicate identical rapid multi-guild presence fires within 3s
            now_ts = int(time.time())
            detail = f"status `{before.status}` → `{after.status}`"
            if self._stalk_logs and self._stalk_logs[-1]["uid"] == after.id and self._stalk_logs[-1]["detail"] == detail and now_ts - self._stalk_logs[-1]["ts"] <= 3:
                return
            self._stalk_logs.append({
                "uid": after.id,
                "user": str(after),
                "detail": detail,
                "ts": now_ts,
            })


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tools(bot))
