"""
Globe Web Control Plane — Modular REST API Handlers.
Provides direct, authenticated JSON control over every cog and runtime subsystem.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import discord
from aiohttp import web

from auth_handlers import auth as global_auth
from config import settings
from ui import log_err, log_info
from web.auth import COOKIE_NAME, DashboardAuth


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, default=str),
        status=status,
        content_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _snapshot_overview(bot: Any, logs_fn: Callable[[], list[dict[str, str]]]) -> dict[str, Any]:
    tools = bot.get_cog("Tools")
    status = bot.get_cog("Status")
    voice = bot.get_cog("Voice")
    mod = bot.get_cog("Moderation")
    troll = bot.get_cog("Troll")

    user = getattr(bot, "user", None)
    avatar_url = str(user.display_avatar.url) if user and getattr(user, "display_avatar", None) else ""
    lat_raw = getattr(bot, "latency", 0.0) or 0.0
    lat_ms = round(lat_raw * 1000, 1) if lat_raw == lat_raw else 0.0

    from data.tracker import tracker
    uid = user.id if user else 0
    stats = tracker.get_stats(uid, None) if uid else {}
    db_size_kb = round(tracker.db_path.stat().st_size / 1024, 1) if tracker.db_path.exists() else 0.0

    active_vc = None
    for vc in getattr(bot, "voice_clients", []) or []:
        ch = getattr(vc, "channel", None)
        if ch:
            active_vc = {"id": str(ch.id), "name": ch.name, "guild": ch.guild.name}
            break

    return {
        "account": {
            "id": str(user.id) if user else "0",
            "username": str(user) if user else "Offline",
            "global_name": getattr(user, "global_name", None) or (user.name if user else "Globe"),
            "avatar": avatar_url,
            "token_masked": global_auth.masked(),
            "prefix": settings.prefix,
        },
        "runtime": {
            "uptime_s": int(getattr(bot, "uptime_seconds", 0.0)),
            "latency_ms": lat_ms,
            "modules": list(getattr(bot, "_loaded_modules", [])),
            "guilds_count": len(getattr(bot, "guilds", []) or []),
            "friends_count": len(getattr(bot, "friends", []) or []),
            "dms_count": len(getattr(bot, "private_channels", []) or []),
            "db_size_kb": db_size_kb,
            "stats": stats,
        },
        "toggles": {
            "no_prefix": bool(getattr(bot, "_no_prefix_enabled", False)),
            "afk": bool(getattr(bot, "_afk_active", False)),
            "afk_reason": getattr(bot, "_afk_reason", "") or "",
            "privacy": bool(getattr(tools, "_privacy_enabled", False)) if tools else False,
            "gsniper": bool(getattr(tools, "_gsniper_enabled", False)) if tools else False,
            "nitro_sniper": bool(getattr(tools, "_nitro_enabled", False)) if tools else False,
            "startup_rpc": bool(getattr(status, "_startup_rpc_enabled", True)) if status else True,
            "startup_custom_status": bool(getattr(status, "_custom_status_enabled", False)) if status else False,
            "spoofer_running": bool(getattr(status, "_spoofer_running", False)) if status else False,
            "status_rotating": bool(status and status._rotate_task and not status._rotate_task.done()),
            "vanity_target": getattr(tools, "_vanity_target", None) if tools else None,
            "vc_stay_id": str(voice._stay_channel_id) if voice and voice._stay_channel_id else None,
            "vc_follow_id": str(voice._follow_target_id) if voice and voice._follow_target_id else None,
            "active_vc": active_vc,
            "lockdown_guilds": [str(gid) for gid in getattr(mod, "_lockdown_saved", {}).keys()] if mod else [],
            "mimic_count": len(getattr(troll, "_mimic_targets", {})) if troll else 0,
        },
        "logs": logs_fn()[-40:],
    }


def register_routes(
    app: web.Application,
    bot: Any,
    auth: DashboardAuth,
    broadcast: Callable[[dict[str, Any]], Any],
    logs_fn: Callable[[], list[dict[str, str]]],
) -> None:
    """Attach all REST routes to the aiohttp application."""

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def auth_me(request: web.Request) -> web.Response:
        session = auth.verify_cookie(request.cookies.get(COOKIE_NAME))
        if not session:
            return _json({"authenticated": False})
        user = getattr(bot, "user", None)
        return _json({
            "authenticated": True,
            "csrf": session["csrf"],
            "expires_at": session["exp"],
            "account": {
                "id": str(user.id) if user else "0",
                "username": str(user) if user else "Globe",
                "avatar": str(user.display_avatar.url) if user and getattr(user, "display_avatar", None) else "",
                "token_masked": global_auth.masked(),
            },
        })

    async def auth_login(request: web.Request) -> web.Response:
        ip = auth.client_ip(request)
        rem = auth.check_rate_limit(ip)
        if rem is not None:
            return _json({"error": f"Too many attempts. Retry in {int(rem)}s.", "retry_after": rem}, status=429)

        data = await _body(request)
        submitted = str(data.get("token", ""))
        remember = bool(data.get("remember", False))

        if not auth.verify_account_token(submitted):
            lock = auth.record_failure(ip)
            if lock:
                return _json({"error": f"Account token rejected. Locked for {int(lock)}s.", "retry_after": lock}, status=429)
            return _json({"error": "Invalid Discord account token."}, status=401)

        auth.clear_failures(ip)
        ttl = 86400 * 7 if remember else 86400
        cookie_val, csrf = auth.create_session(ttl_seconds=ttl)
        resp = _json({"authenticated": True, "csrf": csrf})
        resp.set_cookie(
            COOKIE_NAME,
            cookie_val,
            max_age=ttl,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        log_info(f"Dashboard authenticated session from {ip}")
        return resp

    async def auth_logout(request: web.Request) -> web.Response:
        resp = _json({"ok": True})
        resp.del_cookie(COOKIE_NAME, path="/")
        return resp

    async def auth_revoke(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        auth.revoke_all_sessions()
        resp = _json({"ok": True, "message": "All sessions invalidated."})
        resp.del_cookie(COOKIE_NAME, path="/")
        return resp

    # ── Overview & Switchboard ────────────────────────────────────────────────

    async def get_overview(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        return _json(_snapshot_overview(bot, logs_fn))

    async def update_toggles(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        key = str(data.get("key", ""))
        val = data.get("value")
        tools = bot.get_cog("Tools")
        status = bot.get_cog("Status")

        if key == "no_prefix":
            bot._no_prefix_enabled = bool(val)
            bot._no_prefix_until = None
        elif key == "afk":
            bot._afk_active = bool(val)
            if not bot._afk_active:
                bot._afk_cooldowns.clear()
            elif "reason" in data:
                bot._afk_reason = str(data.get("reason") or "")
        elif key == "privacy" and tools:
            tools._privacy_enabled = bool(val)
            tools._privacy_until = None
            tools._save_state()
        elif key == "gsniper" and tools:
            tools._gsniper_enabled = bool(val)
            tools._save_state()
        elif key == "nitro_sniper" and tools:
            tools._nitro_enabled = bool(val)
        elif key == "startup_rpc" and status:
            status._startup_rpc_enabled = bool(val)
            status._save_rpc_flag("startup_rpc", status._startup_rpc_enabled)
            if status._startup_rpc_enabled:
                await status.apply_default_rpc()
            else:
                await bot.change_presence(activities=[])
        elif key == "startup_custom_status" and status:
            status._custom_status_enabled = bool(val)
            status._save_rpc_flag("startup_custom_status", status._custom_status_enabled)
            if status._startup_rpc_enabled:
                await status.apply_default_rpc()
        elif key == "prefix" and isinstance(val, str) and val.strip():
            from dotenv import set_key
            clean_p = val.strip()[:8]
            settings.prefix = clean_p  # type: ignore[misc]
            bot.command_prefix = clean_p
            try:
                set_key(".env", "PREFIX", clean_p)
            except Exception:
                pass
        else:
            return _json({"error": f"Unknown toggle '{key}'"}, status=400)

        snap = _snapshot_overview(bot, logs_fn)
        asyncio.create_task(broadcast({"type": "toggles", "data": snap["toggles"]}))
        return _json({"ok": True, "toggles": snap["toggles"]})

    # ── Presence, Profile & Spoofer ───────────────────────────────────────────

    async def set_custom_status(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        text = str(data.get("text", "")).strip()
        if not text:
            await bot.change_presence(activities=[])
            return _json({"ok": True, "state": "cleared"})
        act = discord.CustomActivity(name="Custom Status", state=text[:128])
        await bot.change_presence(activities=[act])
        return _json({"ok": True, "state": text[:128]})

    async def set_online_status(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        mode = str(data.get("status", "online")).lower().strip()
        mapping = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        st = mapping.get(mode)
        if not st:
            return _json({"error": "Use online, idle, dnd, or invisible"}, status=400)
        await bot.change_presence(status=st)
        return _json({"ok": True, "status": mode})

    async def set_rich_activity(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        kind = str(data.get("kind", "playing")).lower().strip()
        title = str(data.get("title", "")).strip()[:128]
        url = str(data.get("url", "")).strip()
        elapsed = str(data.get("elapsed", "")).strip()

        if kind == "clear":
            await bot.change_presence(activity=None)
            return _json({"ok": True, "kind": "clear"})

        if kind == "globe":
            from modules.status import get_default_globe_activities
            from modules.tools import _parse_duration
            offset = 0.0
            if elapsed:
                if ":" in elapsed:
                    parts = elapsed.split(":")
                    try:
                        nums = [float(p) for p in parts]
                        offset = (nums[0] * 3600 + nums[1] * 60 + nums[2]) if len(nums) == 3 else (nums[0] * 60 + nums[1])
                    except ValueError:
                        return _json({"error": "Invalid HH:MM:SS timer"}, status=400)
                else:
                    parsed = _parse_duration(elapsed)
                    if parsed is None:
                        return _json({"error": "Invalid duration (use HH:MM:SS or 45m)"}, status=400)
                    offset = float(parsed)
            start_epoch = time.time() - max(0.0, offset)
            bot._start_epoch = start_epoch
            uid = bot.user.id if bot.user else 0
            await bot.change_presence(activities=get_default_globe_activities(uid, start_epoch))
            return _json({"ok": True, "kind": "globe", "offset_s": int(offset)})

        if not title:
            return _json({"error": "Activity title is required"}, status=400)

        if kind == "streaming":
            act = discord.Streaming(name=title, url=url or "https://twitch.tv/twitch")
        elif kind == "listening":
            act = discord.Activity(type=discord.ActivityType.listening, name=title)
        elif kind == "watching":
            act = discord.Activity(type=discord.ActivityType.watching, name=title)
        else:
            act = discord.Game(name=title)
        await bot.change_presence(activity=act)
        return _json({"ok": True, "kind": kind, "title": title})

    async def set_bio(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        text = str(data.get("text", ""))[:190]
        tools = bot.get_cog("Tools")
        token_val = getattr(bot.http, "token", "") or ""
        if not tools or not token_val:
            return _json({"error": "Unavailable"}, status=503)
        resp = await tools._get_http_client().patch(
            "https://discord.com/api/v9/users/@me/profile",
            headers={"Authorization": token_val},
            json={"bio": text},
        )
        if resp.status_code != 200:
            return _json({"error": f"Discord HTTP {resp.status_code}"}, status=resp.status_code)
        return _json({"ok": True, "bio": text})

    async def set_hypesquad(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        house = str(data.get("house", "")).lower().strip()
        house_map = {"bravery": 1, "brilliance": 2, "balance": 3}
        tools = bot.get_cog("Tools")
        token_val = getattr(bot.http, "token", "") or ""
        if not tools or not token_val:
            return _json({"error": "Unavailable"}, status=503)
        client = tools._get_http_client()
        if house == "leave":
            resp = await client.delete("https://discord.com/api/v9/hypesquad/online", headers={"Authorization": token_val})
        elif house in house_map:
            resp = await client.post("https://discord.com/api/v9/hypesquad/online", headers={"Authorization": token_val}, json={"house_id": house_map[house]})
        else:
            return _json({"error": "Choose bravery, brilliance, balance, or leave"}, status=400)
        return _json({"ok": resp.status_code in (200, 204), "status_code": resp.status_code})

    async def set_status_rotate(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        status = bot.get_cog("Status")
        if not status:
            return _json({"error": "Status module missing"}, status=503)
        data = await _body(request)
        enabled = bool(data.get("enabled", True))
        if not enabled:
            if status._rotate_task and not status._rotate_task.done():
                status._rotate_task.cancel()
                status._rotate_task = None
            return _json({"ok": True, "rotating": False})

        delay = max(5.0, float(data.get("interval", 15)))
        items = [str(s).strip() for s in (data.get("slides") or []) if str(s).strip()]
        if len(items) < 2:
            return _json({"error": "Provide at least 2 slides"}, status=400)
        if status._rotate_task and not status._rotate_task.done():
            status._rotate_task.cancel()

        async def _rotator() -> None:
            idx = 0
            try:
                while True:
                    txt = items[idx % len(items)][:128]
                    try:
                        await bot.change_presence(activities=[discord.CustomActivity(name="Custom Status", state=txt)])
                    except Exception:
                        pass
                    idx += 1
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                pass

        status._rotate_task = asyncio.create_task(_rotator())
        return _json({"ok": True, "rotating": True, "slides": len(items), "interval": delay})

    async def control_spoofer(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        status = bot.get_cog("Status")
        tools = bot.get_cog("Tools")
        if not status or not tools:
            return _json({"error": "Modules missing"}, status=503)
        data = await _body(request)
        action = str(data.get("action", "start"))

        if action == "stop":
            status._spoofer_cancel = True
            return _json({"ok": True, "running": False})

        if status._spoofer_running:
            return _json({"error": "Spoofer already running"}, status=409)

        count = max(1, min(int(data.get("count", 15)), 50))
        interval = max(3.0, min(float(data.get("interval", 6.0)), 30.0))

        async def _run_spoofer() -> None:
            status._spoofer_running = True
            status._spoofer_cancel = False
            try:
                resp = await tools._get_http_client().get("https://discord.com/api/v9/applications/detectable")
                catalog = [g for g in resp.json() if g.get("id") and g.get("name") and g.get("executables")]
                selected = random.sample(catalog, min(count, len(catalog)))
                for idx, game in enumerate(selected, 1):
                    if status._spoofer_cancel:
                        break
                    act = discord.Activity(
                        type=discord.ActivityType.playing,
                        application_id=int(game["id"]),
                        name=game["name"],
                        details="In-Game",
                        timestamps={"start": int(time.time() * 1000)},
                    )
                    await bot.change_presence(activities=[act])
                    await broadcast({
                        "type": "job",
                        "data": {"job": "spoofer", "current": idx, "total": len(selected), "game": game["name"], "done": False},
                    })
                    for _ in range(int(interval * 2)):
                        if status._spoofer_cancel:
                            break
                        await asyncio.sleep(0.5)
                if status._startup_rpc_enabled:
                    await status.apply_default_rpc()
                else:
                    await bot.change_presence(activities=[])
                await broadcast({"type": "job", "data": {"job": "spoofer", "done": True}})
            except Exception as e:
                log_err(f"Web spoofer error: {e}")
            finally:
                status._spoofer_running = False
                status._spoofer_cancel = False

        asyncio.create_task(_run_spoofer())
        return _json({"ok": True, "running": True, "count": count, "interval": interval})

    # ── Intelligence, Snipes, Radar, Stalker, Keywords & Profiler ─────────────

    async def get_snipes(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        q = request.query.get("q", "").strip()
        from data.tracker import tracker
        if q:
            rows = tracker.search_snipes(q, limit=40)
        else:
            conn = tracker._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT channel_id, author_id, author_name, content, attachments, timestamp FROM snipes ORDER BY id DESC LIMIT 40")
            rows = [
                {
                    "channel_id": str(r[0]),
                    "author_id": str(r[1]),
                    "author_name": r[2],
                    "content": r[3],
                    "attachments": [u for u in r[4].split("\n") if u] if r[4] else [],
                    "timestamp": r[5],
                }
                for r in cur.fetchall()
            ]
        return _json({"snipes": rows})

    async def get_radar(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        return _json({"radar": list(tools._ghost_pings)[::-1] if tools else []})

    async def clear_radar(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if tools:
            tools._ghost_pings.clear()
        return _json({"ok": True})

    async def get_stalk(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        return _json({
            "targets": [str(u) for u in sorted(tools._stalk_targets)] if tools else [],
            "logs": list(tools._stalk_logs)[::-1] if tools else [],
        })

    async def update_stalk(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        action = str(data.get("action", "add"))
        uid = int(str(data.get("user_id", "0")).strip())
        if action == "clear":
            tools._stalk_targets.clear()
        elif uid:
            if action == "remove":
                tools._stalk_targets.discard(uid)
            else:
                tools._stalk_targets.add(uid)
        tools._save_state()
        return _json({"ok": True, "targets": [str(u) for u in sorted(tools._stalk_targets)]})

    async def get_keywords(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        return _json({
            "keywords": sorted(tools._keywords) if tools else [],
            "hits": list(tools._keyword_hits)[::-1] if tools else [],
            "webhook_set": bool(tools and tools._alert_webhook),
        })

    async def update_keywords(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        action = str(data.get("action", "add"))
        phrase = str(data.get("phrase", "")).strip().lower()
        if action == "clear":
            tools._keywords.clear()
        elif action == "remove" and phrase:
            tools._keywords.discard(phrase)
        elif phrase:
            tools._keywords.add(phrase)
        tools._save_state()
        return _json({"ok": True, "keywords": sorted(tools._keywords)})

    async def set_alert_webhook(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        url = str(data.get("url", "")).strip()
        tools._alert_webhook = url if url.startswith("https://") else None
        tools._save_state()
        return _json({"ok": True, "webhook_set": bool(tools._alert_webhook)})

    async def vanity_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        if request.method == "DELETE":
            auth.authenticate_request(request, require_csrf=True)
            if tools._vanity_task and not tools._vanity_task.done():
                tools._vanity_task.cancel()
                tools._vanity_task = None
            target = tools._vanity_target
            tools._vanity_target = None
            return _json({"ok": True, "stopped": target})
        if request.method == "POST":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            code = str(data.get("code", "")).rstrip("/").split("/")[-1].strip()
            if not code:
                return _json({"error": "Vanity code required"}, status=400)
            target_gid = int(str(data.get("guild_id") or "0") or 0) or None
            delay = max(5.0, min(float(data.get("interval", 8.0)), 60.0))
            if tools._vanity_task and not tools._vanity_task.done():
                tools._vanity_task.cancel()
            tools._vanity_target = code

            async def _poll() -> None:
                client = tools._get_http_client()
                token_val = getattr(bot.http, "token", "") or ""
                try:
                    while True:
                        resp = await client.get(f"https://discord.com/api/v9/invites/{code}")
                        if resp.status_code == 404:
                            note = "Alert only (no guild set)."
                            if target_gid and token_val:
                                cl = await client.patch(
                                    f"https://discord.com/api/v9/guilds/{target_gid}/vanity-url",
                                    headers={"Authorization": token_val},
                                    json={"code": code},
                                )
                                note = f"Auto-claim HTTP {cl.status_code}"
                            await broadcast({"type": "job", "data": {"job": "vanity", "code": code, "dropped": True, "note": note}})
                            await tools._forward_alert(f"Vanity `{code}` Dropped", note)
                            break
                        await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    pass

            tools._vanity_task = asyncio.create_task(_poll())
            return _json({"ok": True, "target": code, "interval": delay})
        running = bool(tools._vanity_task and not tools._vanity_task.done())
        return _json({"running": running, "target": tools._vanity_target if running else None})

    async def inspect_tool(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        kind = str(data.get("kind", "ip")).lower().strip()
        target = str(data.get("target", "")).strip()
        if not target:
            return _json({"error": "Target input required"}, status=400)
        client = tools._get_http_client()
        try:
            if kind == "ip":
                host = target.replace("https://", "").replace("http://", "").split("/")[0]
                r = await client.get(f"http://ip-api.com/json/{host}?fields=status,message,country,regionName,city,timezone,isp,org,as,query")
                return _json({"ok": True, "kind": "ip", "result": r.json()})
            if kind == "dns":
                host = target.replace("https://", "").replace("http://", "").split("/")[0]
                infos = await asyncio.get_running_loop().getaddrinfo(host, None)
                ips = sorted({i[4][0] for i in infos})
                return _json({"ok": True, "kind": "dns", "result": {"host": host, "records": ips}})
            if kind == "headers":
                url = target if target.startswith(("http://", "https://")) else f"https://{target}"
                resp = await client.head(url, follow_redirects=True)
                return _json({"ok": True, "kind": "headers", "result": {"url": url, "status": resp.status_code, "headers": dict(list(resp.headers.items())[:14])}})
            if kind == "crypto":
                alias_map = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "xrp": "ripple", "doge": "dogecoin", "ltc": "litecoin"}
                cid = alias_map.get(target.lower(), target.lower())
                r = await client.get(f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd&include_24hr_change=true")
                return _json({"ok": True, "kind": "crypto", "result": {"coin": cid, "data": r.json().get(cid)}})
            if kind == "token":
                r = await client.get("https://discord.com/api/v9/users/@me", headers={"Authorization": target})
                if r.status_code != 200:
                    return _json({"ok": True, "kind": "token", "result": {"valid": False, "status": r.status_code}})
                u = r.json()
                return _json({"ok": True, "kind": "token", "result": {"valid": True, "id": u.get("id"), "username": u.get("username"), "mfa": u.get("mfa_enabled"), "verified": u.get("verified")}})
        except Exception as e:
            return _json({"error": str(e)}, status=500)
        return _json({"error": "Unknown tool kind"}, status=400)

    async def friends_action(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        snap_file = Path("data") / "backups" / "friends.json"
        if request.method == "POST":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            act = str(data.get("action", "backup"))
            if act == "backup":
                snap = tools._snapshot_friends()
                snap_file.parent.mkdir(parents=True, exist_ok=True)
                snap_file.write_text(json.dumps({"ts": int(time.time()), "friends": snap}, indent=2), encoding="utf-8")
                return _json({"ok": True, "count": len(snap)})
            token_val = getattr(bot.http, "token", "") or ""
            client = tools._get_http_client()
            resp = await client.get("https://discord.com/api/v9/users/@me/relationships", headers={"Authorization": token_val})
            count = 0
            if resp.status_code == 200:
                target_type = 3 if act == "accept" else 4
                for rel in resp.json():
                    if rel.get("type") == target_type:
                        url = f"https://discord.com/api/v9/users/@me/relationships/{rel['id']}"
                        r = await (client.put(url, headers={"Authorization": token_val}, json={}) if act == "accept" else client.delete(url, headers={"Authorization": token_val}))
                        if r.status_code in (200, 204):
                            count += 1
                        await asyncio.sleep(0.45)
            return _json({"ok": True, "processed": count})

        # GET -> diff
        cur = tools._snapshot_friends()
        if not snap_file.exists():
            return _json({"baseline_exists": False, "current_count": len(cur), "removed": [], "added": []})
        old_data = json.loads(snap_file.read_text(encoding="utf-8"))
        removed, added = tools._diff_relationships(old_data.get("friends", {}), cur)
        return _json({
            "baseline_exists": True,
            "baseline_ts": old_data.get("ts", 0),
            "current_count": len(cur),
            "old_count": len(old_data.get("friends", {})),
            "removed": removed,
            "added": added,
        })

    async def profile_user(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        try:
            uid = int(str(data.get("user_id", "")).strip())
        except ValueError:
            return _json({"error": "Enter a valid numeric Discord user ID"}, status=400)

        target = bot.get_user(uid)
        mutuals = []
        platforms: set[str] = set()
        live_status = "offline"
        voice_loc = None
        for g in bot.guilds:
            m = g.get_member(uid)
            if not m:
                continue
            if not target:
                target = m
            if str(m.status) != "offline":
                live_status = str(m.status)
            if str(getattr(m, "desktop_status", "offline")) != "offline":
                platforms.add("Desktop")
            if str(getattr(m, "mobile_status", "offline")) != "offline":
                platforms.add("Mobile")
            if str(getattr(m, "web_status", "offline")) != "offline":
                platforms.add("Web")
            if m.voice and m.voice.channel and not voice_loc:
                voice_loc = f"{g.name} / #{m.voice.channel.name}"
            mutuals.append({
                "guild": g.name,
                "guild_id": str(g.id),
                "nick": m.nick or "",
                "top_role": m.top_role.name if m.top_role else "none",
            })

        return _json({
            "user_id": str(uid),
            "username": str(target) if target else f"User {uid}",
            "avatar": str(target.display_avatar.url) if target and getattr(target, "display_avatar", None) else "",
            "status": live_status,
            "platforms": sorted(platforms),
            "voice": voice_loc,
            "mutuals": mutuals,
        })

    # ── Guilds, Moderation & Voice ────────────────────────────────────────────

    async def list_guilds(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        mod = bot.get_cog("Moderation")
        locked = set(getattr(mod, "_lockdown_saved", {}).keys()) if mod else set()
        out = []
        for g in bot.guilds:
            vcs = [{"id": str(c.id), "name": c.name, "members": len(c.members)} for c in g.voice_channels[:25]]
            tcs = [{"id": str(c.id), "name": c.name} for c in g.text_channels[:30]]
            out.append({
                "id": str(g.id),
                "name": g.name,
                "icon": str(g.icon.url) if g.icon else "",
                "member_count": g.member_count or len(g.members),
                "roles_count": len(g.roles),
                "channels_count": len(g.channels),
                "locked": g.id in locked,
                "voice_channels": vcs,
                "text_channels": tcs,
            })
        return _json({"guilds": out})

    async def dispatch_send(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        cid_raw = str(data.get("channel_id", "")).strip()
        content = str(data.get("content", "")).strip()[:2000]
        if not cid_raw or not content:
            return _json({"error": "Channel and message content required"}, status=400)
        ch = bot.get_channel(int(cid_raw))
        if not ch:
            return _json({"error": "Channel not found"}, status=404)
        msg = await ch.send(content)
        return _json({"ok": True, "message_id": str(msg.id)})

    async def audit_guild(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        gid = int(request.match_info["id"])
        guild = bot.get_guild(gid)
        if not guild:
            return _json({"error": "Guild not found"}, status=404)
        flags = ("administrator", "manage_guild", "manage_roles", "manage_channels", "manage_webhooks", "ban_members", "kick_members", "mention_everyone")
        default_risks = [f for f in flags if getattr(guild.default_role.permissions, f, False)]
        admin_roles = [r.name for r in guild.roles if not r.is_default() and not r.managed and r.permissions.administrator]
        exposed_ch = [ch.name for ch in guild.channels if (ow := ch.overwrites_for(guild.default_role)) and (ow.manage_webhooks is True or ow.manage_channels is True or ow.manage_permissions is True)]
        return _json({
            "guild": guild.name,
            "roles_scanned": len(guild.roles),
            "channels_scanned": len(guild.channels),
            "everyone_risks": default_risks,
            "admin_roles": admin_roles,
            "exposed_channels": exposed_ch,
        })

    async def backup_guild_download(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        gid = int(request.match_info["id"])
        guild = bot.get_guild(gid)
        if not guild:
            return _json({"error": "Guild not found"}, status=404)
        snap = {
            "id": str(guild.id),
            "name": guild.name,
            "roles": [{"name": r.name, "color": r.color.value, "perms": r.permissions.value} for r in guild.roles if not r.is_default()],
            "categories": [{"name": c.name, "channels": [ch.name for ch in c.channels]} for c in guild.categories],
        }
        return web.Response(
            text=json.dumps(snap, indent=2),
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="globe_backup_{guild.id}.json"'},
        )

    async def guild_lockdown(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        mod = bot.get_cog("Moderation")
        data = await _body(request)
        gid = int(str(data.get("guild_id", "0")))
        lock = bool(data.get("lock", True))
        guild = bot.get_guild(gid)
        if not mod or not guild:
            return _json({"error": "Guild not found"}, status=404)
        changed = 0
        if lock:
            saved = {}
            for ch in guild.text_channels:
                ow = ch.overwrites_for(guild.default_role)
                saved[ch.id] = ow.send_messages
                if ow.send_messages is not False:
                    ow.send_messages = False
                    try:
                        await ch.set_permissions(guild.default_role, overwrite=ow)
                        changed += 1
                        await asyncio.sleep(0.35)
                    except Exception:
                        pass
            mod._lockdown_saved[guild.id] = saved
        else:
            saved = mod._lockdown_saved.pop(guild.id, {})
            for ch in guild.text_channels:
                ow = ch.overwrites_for(guild.default_role)
                target_val = saved.get(ch.id, None)
                if ow.send_messages != target_val:
                    ow.send_messages = target_val
                    try:
                        await ch.set_permissions(guild.default_role, overwrite=ow)
                        changed += 1
                        await asyncio.sleep(0.35)
                    except Exception:
                        pass
        return _json({"ok": True, "locked": lock, "channels_updated": changed})

    async def voice_control(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        voice = bot.get_cog("Voice")
        if not voice:
            return _json({"error": "Voice module missing"}, status=503)
        data = await _body(request)
        act = str(data.get("action", "leave"))

        if act == "leave":
            voice._stay_channel_id = None
            for vc in list(bot.voice_clients):
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
            return _json({"ok": True, "connected": False})

        if act == "join":
            cid = int(str(data.get("channel_id", "0")))
            mode = str(data.get("mode", "deaf")).lower()
            ch = bot.get_channel(cid)
            if not isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                return _json({"error": "Voice channel not found"}, status=404)
            voice._stay_mute = mode in ("deaf", "mute")
            voice._stay_deaf = mode == "deaf"
            voice._stay_channel_id = ch.id
            if ch.guild.voice_client:
                await ch.guild.voice_client.disconnect(force=True)
            await ch.connect(self_deaf=voice._stay_deaf, self_mute=voice._stay_mute, reconnect=True)
            return _json({"ok": True, "channel": ch.name})

        if act == "follow":
            uid_raw = str(data.get("user_id", "")).strip()
            if not uid_raw or uid_raw.lower() == "off":
                voice._follow_target_id = None
                return _json({"ok": True, "follow_id": None})
            voice._follow_target_id = int(uid_raw)
            return _json({"ok": True, "follow_id": str(voice._follow_target_id)})

        return _json({"error": "Invalid action"}, status=400)

    # ── DMs, Bookmarks, Schedules & System ────────────────────────────────────

    async def list_dms(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        out = []
        for ch in getattr(bot, "private_channels", []) or []:
            if isinstance(ch, discord.DMChannel) and ch.recipient:
                out.append({
                    "id": str(ch.id),
                    "recipient": str(ch.recipient),
                    "recipient_id": str(ch.recipient.id),
                    "avatar": str(ch.recipient.display_avatar.url) if ch.recipient.display_avatar else "",
                })
        return _json({"dms": out[:60]})

    async def export_dm(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        cid = int(request.match_info["id"])
        limit = max(10, min(int(request.query.get("limit", "200")), 1000))
        ch = bot.get_channel(cid)
        if not ch:
            return _json({"error": "DM channel not found"}, status=404)
        rows = []
        async for m in ch.history(limit=limit, oldest_first=False):
            ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "unknown"
            rows.append(f"[{ts}] {m.author} ({m.author.id}): {m.content or '[Media/Embed]'}")
        rows.reverse()
        return web.Response(
            text="\n".join(rows),
            content_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="dm_transcript_{cid}.txt"'},
        )

    async def wipe_dm(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        cid = int(request.match_info["id"])
        ch = bot.get_channel(cid)
        if not ch or not bot.user:
            return _json({"error": "DM channel not found"}, status=404)

        async def _wipe_job() -> None:
            deleted = 0
            scanned = 0
            pace = 0.28
            async for m in ch.history(limit=None):
                scanned += 1
                if m.author.id != bot.user.id or m.type not in (discord.MessageType.default, discord.MessageType.reply):
                    continue
                for _ in range(3):
                    try:
                        await m.delete()
                        deleted += 1
                        if deleted % 10 == 0:
                            await broadcast({"type": "job", "data": {"job": "deletedm", "channel_id": str(cid), "deleted": deleted, "scanned": scanned, "done": False}})
                        await asyncio.sleep(pace + random.uniform(0.04, 0.14))
                        break
                    except discord.HTTPException as e:
                        if getattr(e, "status", None) == 429:
                            pace = min(pace + 0.05, 0.75)
                            await asyncio.sleep(float(getattr(e, "retry_after", 2.0) or 2.0) + 0.35)
                        else:
                            break
            await broadcast({"type": "job", "data": {"job": "deletedm", "channel_id": str(cid), "deleted": deleted, "scanned": scanned, "done": True}})

        asyncio.create_task(_wipe_job())
        return _json({"ok": True, "started": True})

    async def bookmarks_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        from data.tracker import tracker
        if request.method == "DELETE":
            auth.authenticate_request(request, require_csrf=True)
            bid = int(request.match_info["id"])
            return _json({"ok": tracker.delete_bookmark(bid)})
        tag = request.query.get("tag", "").strip()
        return _json({"bookmarks": tracker.list_bookmarks(tag=tag, limit=30)})

    async def schedules_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"schedules": []})
        if request.method == "DELETE":
            auth.authenticate_request(request, require_csrf=True)
            sid = int(request.match_info["id"])
            info = tools._schedules.pop(sid, None)
            if info:
                info["task"].cancel()
            return _json({"ok": bool(info)})
        out = [
            {"id": sid, "interval": info["interval"], "channel": info["channel"], "text": info["text"]}
            for sid, info in tools._schedules.items()
        ]
        return _json({"schedules": out})

    async def system_action(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        act = str(data.get("action", ""))
        if act == "reload":
            mod = str(data.get("module", "")).strip().lower()
            await bot.reload_extension(f"modules.{mod}")
            return _json({"ok": True, "reloaded": mod})
        if act == "update":
            import subprocess
            res = subprocess.run(["git", "pull", "--ff-only", "origin", "main"], capture_output=True, text=True, timeout=15)
            reloaded = []
            for m in list(bot._loaded_modules):
                try:
                    await bot.reload_extension(f"modules.{m}")
                    reloaded.append(m)
                except Exception:
                    pass
            return _json({"ok": res.returncode == 0, "git": res.stdout.strip() or res.stderr.strip(), "reloaded": reloaded})
        if act == "restart":
            async def _delayed_exec() -> None:
                await asyncio.sleep(1.0)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            asyncio.create_task(_delayed_exec())
            return _json({"ok": True, "restarting": True})
        return _json({"error": "Unknown system action"}, status=400)

    # Register Routes
    r = app.router
    r.add_get("/api/v1/auth/me", auth_me)
    r.add_post("/api/v1/auth/login", auth_login)
    r.add_post("/api/v1/auth/logout", auth_logout)
    r.add_post("/api/v1/auth/revoke", auth_revoke)

    r.add_get("/api/v1/overview", get_overview)
    r.add_post("/api/v1/toggles", update_toggles)

    r.add_post("/api/v1/presence/custom", set_custom_status)
    r.add_post("/api/v1/presence/status", set_online_status)
    r.add_post("/api/v1/presence/activity", set_rich_activity)
    r.add_post("/api/v1/presence/bio", set_bio)
    r.add_post("/api/v1/presence/hypesquad", set_hypesquad)
    r.add_post("/api/v1/presence/rotate", set_status_rotate)
    r.add_post("/api/v1/presence/spoofer", control_spoofer)

    r.add_get("/api/v1/intel/snipes", get_snipes)
    r.add_get("/api/v1/intel/radar", get_radar)
    r.add_delete("/api/v1/intel/radar", clear_radar)
    r.add_get("/api/v1/intel/stalk", get_stalk)
    r.add_post("/api/v1/intel/stalk", update_stalk)
    r.add_get("/api/v1/intel/keywords", get_keywords)
    r.add_post("/api/v1/intel/keywords", update_keywords)
    r.add_post("/api/v1/intel/webhook", set_alert_webhook)
    r.add_get("/api/v1/intel/vanity", vanity_handler)
    r.add_post("/api/v1/intel/vanity", vanity_handler)
    r.add_delete("/api/v1/intel/vanity", vanity_handler)
    r.add_post("/api/v1/tools/inspect", inspect_tool)
    r.add_get("/api/v1/intel/friends/diff", friends_action)
    r.add_post("/api/v1/intel/friends", friends_action)
    r.add_post("/api/v1/intel/user-profile", profile_user)

    r.add_get("/api/v1/guilds", list_guilds)
    r.add_post("/api/v1/dispatch/send", dispatch_send)
    r.add_get("/api/v1/guilds/{id}/audit", audit_guild)
    r.add_get("/api/v1/guilds/{id}/backup", backup_guild_download)
    r.add_post("/api/v1/guilds/lockdown", guild_lockdown)
    r.add_post("/api/v1/voice", voice_control)

    r.add_get("/api/v1/dms", list_dms)
    r.add_get("/api/v1/dms/{id}/export", export_dm)
    r.add_post("/api/v1/dms/{id}/wipe", wipe_dm)
    r.add_get("/api/v1/bookmarks", bookmarks_handler)
    r.add_delete("/api/v1/bookmarks/{id}", bookmarks_handler)
    r.add_get("/api/v1/schedules", schedules_handler)
    r.add_delete("/api/v1/schedules/{id}", schedules_handler)
    r.add_post("/api/v1/system", system_action)
