"""
Globe Web Control Plane — Modular REST API Handlers.
Provides direct, authenticated JSON control over every cog and runtime subsystem.
"""

from __future__ import annotations

import asyncio
import io
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

    # Gather live Discord member presence + saved Status cog config for frontend hydration
    live_me = None
    for g in getattr(bot, "guilds", []) or []:
        m = getattr(g, "me", None)
        if m is not None:
            live_me = m
            break
    raw_live_st = str(getattr(live_me, "status", "") or "").lower()
    if raw_live_st == "offline":
        raw_live_st = "invisible"
    live_activities = []
    for a in (getattr(live_me, "activities", []) or []):
        aname = getattr(a, "name", "") or ""
        if aname:
            atype = getattr(getattr(a, "type", None), "name", "activity")
            adet = getattr(a, "details", None) or getattr(a, "state", None) or ""
            live_activities.append({"type": str(atype), "name": str(aname), "detail": str(adet)})

    presence_config = {}
    if status:
        cfg_st = getattr(status, "_online_status", "") or ""
        effective_st = cfg_st if cfg_st in ("online", "idle", "dnd", "invisible") else (
            raw_live_st if raw_live_st in ("online", "idle", "dnd", "invisible") else "online"
        )
        cfg_kind = getattr(status, "_activity_kind", "globe") or "globe"
        cfg_title = getattr(status, "_activity_title", "") or ("Globe" if cfg_kind == "globe" else "")
        presence_config = {
            "online_status": effective_st,
            "activity_kind": cfg_kind,
            "activity_title": cfg_title,
            "activity_extra": getattr(status, "_activity_extra", ""),
            "custom_status_text": getattr(status, "_custom_status_text", ""),
            "hypesquad_house": getattr(status, "_hypesquad_house", "leave"),
            "bio_text": getattr(status, "_bio_text", ""),
            "rotate_interval": getattr(status, "_rotate_interval", 15.0),
            "rotate_slides": getattr(status, "_rotate_slides", []),
            "live_activities": live_activities,
        }

    # Gather spoofer live stats
    spoofer_stats = {
        "running": bool(getattr(status, "_spoofer_running", False)) if status else False,
        "current": getattr(status, "_spoofer_current", 0) if status else 0,
        "total": getattr(status, "_spoofer_total", 0) if status else 0,
        "game": getattr(status, "_spoofer_game", "") if status else "",
        "app_id": getattr(status, "_spoofer_app_id", "") if status else "",
        "interval": getattr(status, "_spoofer_interval", 6.0) if status else 6.0,
        "elapsed_s": int(time.time() - status._spoofer_started_at) if status and getattr(status, "_spoofer_running", False) and getattr(status, "_spoofer_started_at", 0) else 0,
        "completed_total": getattr(status, "_spoofer_completed_total", 0) if status else 0,
    }

    return {
        "account": {
            "id": str(user.id) if user else "0",
            "username": str(user) if user else "Offline",
            "global_name": getattr(user, "global_name", None) or (user.name if user else "Globe"),
            "avatar": avatar_url,
            "token_masked": global_auth.masked(),
            "prefix": settings.prefix,
        },
        "presence_config": presence_config,
        "spoofer": spoofer_stats,
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

    def _sync_active_account_vault() -> None:
        user = getattr(bot, "user", None)
        tok = auth._token_provider() or getattr(getattr(bot, "http", None), "token", "") or ""
        if user and tok:
            avatar = str(user.display_avatar.url) if getattr(user, "display_avatar", None) else ""
            gname = getattr(user, "global_name", None) or getattr(user, "name", None) or str(user)
            auth.register_account(str(user.id), str(user), gname, avatar, tok)

    async def auth_me(request: web.Request) -> web.Response:
        session = auth.verify_cookie(request.cookies.get(COOKIE_NAME))
        if not session:
            return _json({"authenticated": False})
        _sync_active_account_vault()
        user = getattr(bot, "user", None)
        return _json({
            "authenticated": True,
            "csrf": session["csrf"],
            "expires_at": session["exp"],
            "account": {
                "id": str(user.id) if user else "0",
                "username": str(user) if user else "Globe",
                "global_name": getattr(user, "global_name", None) or (user.name if user else "Globe"),
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
        _sync_active_account_vault()
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
        status = bot.get_cog("Status")
        if not text:
            await bot.change_presence(activities=[])
            if status:
                status._custom_status_text = ""
                status._save_str("custom_status_text", "")
            return _json({"ok": True, "state": "cleared"})
        act = discord.CustomActivity(name="Custom Status", state=text[:128])
        await bot.change_presence(activities=[act])
        if status:
            status._custom_status_text = text[:128]
            status._save_str("custom_status_text", text[:128])
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
        status = bot.get_cog("Status")
        if status:
            status._online_status = mode
            status._save_str("online_status", mode)
        return _json({"ok": True, "status": mode})

    async def set_rich_activity(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        kind = str(data.get("kind", "playing")).lower().strip()
        title = str(data.get("title", "")).strip()[:128]
        url = str(data.get("url", "")).strip()
        elapsed = str(data.get("elapsed", "")).strip()

        status = bot.get_cog("Status")
        if kind == "clear":
            await bot.change_presence(activity=None)
            if status:
                status._activity_kind = "clear"
                status._activity_title = ""
                status._activity_extra = ""
                status._save_str("activity_kind", "clear")
                status._save_str("activity_title", "")
                status._save_str("activity_extra", "")
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
            st_enum = status._discord_status_enum() if status else None
            if st_enum is not None:
                await bot.change_presence(activities=get_default_globe_activities(uid, start_epoch), status=st_enum)
            else:
                await bot.change_presence(activities=get_default_globe_activities(uid, start_epoch))
            if status:
                status._activity_kind = "globe"
                status._activity_title = "Globe"
                status._activity_extra = elapsed
                status._save_str("activity_kind", "globe")
                status._save_str("activity_title", "Globe")
                status._save_str("activity_extra", elapsed)
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
        status = bot.get_cog("Status")
        if status:
            status._activity_kind = kind
            status._activity_title = title
            status._activity_extra = url or elapsed
            status._save_str("activity_kind", kind)
            status._save_str("activity_title", title)
            status._save_str("activity_extra", url or elapsed)
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
        status = bot.get_cog("Status")
        if status:
            status._bio_text = text
            status._save_str("bio_text", text)
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
        status = bot.get_cog("Status")
        if status and resp.status_code in (200, 204):
            status._hypesquad_house = house
            status._save_str("hypesquad_house", house)
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

        status._rotate_interval = delay
        status._rotate_slides = items
        status._save_str("rotate_interval", str(delay))
        status._save_str("rotate_slides", "\n".join(items))
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
            batch_start = time.time()
            status._spoofer_started_at = batch_start
            status._spoofer_total = count
            status._spoofer_current = 0
            status._spoofer_game = "Loading catalog..."
            status._spoofer_app_id = ""
            status._spoofer_interval = interval
            try:
                resp = await tools._get_http_client().get("https://discord.com/api/v9/applications/detectable")
                catalog = [g for g in resp.json() if g.get("id") and g.get("name") and g.get("executables")]
                selected = random.sample(catalog, min(count, len(catalog)))
                total = len(selected)
                status._spoofer_total = total
                st_enum = status._discord_status_enum()
                for idx, game in enumerate(selected, 1):
                    if status._spoofer_cancel:
                        break
                    gname = game["name"]
                    gid = str(game["id"])
                    status._spoofer_current = idx
                    status._spoofer_game = gname
                    status._spoofer_app_id = gid
                    status._spoofer_completed_total += 1
                    act = discord.Activity(
                        type=discord.ActivityType.playing,
                        application_id=int(game["id"]),
                        name=gname,
                        details="In-Game",
                        timestamps={"start": int(time.time() * 1000)},
                    )
                    st_enum = status._discord_status_enum()
                    if st_enum is not None:
                        await bot.change_presence(activities=[act], status=st_enum)
                    else:
                        await bot.change_presence(activities=[act])
                    ticks = max(1, int(interval))
                    for sec_i in range(ticks):
                        if status._spoofer_cancel:
                            break
                        elapsed_s = int(time.time() - batch_start)
                        remaining_s = max(0, int((total - idx) * interval + (ticks - sec_i)))
                        pct = int((idx / max(1, total)) * 100)
                        await broadcast({
                            "type": "job",
                            "data": {
                                "job": "spoofer",
                                "current": idx,
                                "total": total,
                                "game": gname,
                                "app_id": gid,
                                "elapsed_s": elapsed_s,
                                "remaining_s": remaining_s,
                                "pct": pct,
                                "completed_total": status._spoofer_completed_total,
                                "done": False,
                            },
                        })
                        await asyncio.sleep(1.0)
                await status.apply_default_rpc()
                status._save_str("spoofer_completed_total", str(status._spoofer_completed_total))
                await broadcast({
                    "type": "job",
                    "data": {
                        "job": "spoofer",
                        "done": True,
                        "cancelled": status._spoofer_cancel,
                        "completed_total": status._spoofer_completed_total,
                        "elapsed_s": int(time.time() - batch_start),
                    },
                })
            except Exception as e:
                log_err(f"Web spoofer error: {e}")
                await broadcast({"type": "job", "data": {"job": "spoofer", "done": True, "error": str(e)}})
            finally:
                status._spoofer_running = False
                status._spoofer_cancel = False
                status._spoofer_game = ""
                status._spoofer_app_id = ""

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
        raw_uid = str(data.get("user_id", "")).strip()
        if raw_uid.lower() in ("me", "self", "@me") and getattr(bot, "user", None):
            uid = int(bot.user.id)
        else:
            try:
                uid = int(raw_uid)
            except ValueError:
                return _json({"error": "Enter a valid numeric Discord user ID (or 'me')"}, status=400)

        target = bot.get_user(uid)
        mutuals = []
        platforms: set[str] = set()
        live_status = "offline"
        voice_loc = None
        activities_out: list[dict[str, str]] = []

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
            if not activities_out and getattr(m, "activities", None):
                for a in m.activities:
                    atype = getattr(a.type, "name", "activity") if hasattr(a, "type") else "activity"
                    adet = getattr(a, "state", None) or getattr(a, "details", None) or ""
                    activities_out.append({"type": atype, "name": getattr(a, "name", "") or "", "detail": str(adet)})
            roles_list = [r.name for r in reversed(m.roles) if not r.is_default()][:8]
            joined_iso = m.joined_at.strftime("%Y-%m-%d") if getattr(m, "joined_at", None) else "—"
            boost_iso = m.premium_since.strftime("%Y-%m-%d") if getattr(m, "premium_since", None) else ""
            mutuals.append({
                "guild": g.name,
                "guild_id": str(g.id),
                "nick": m.nick or "",
                "top_role": m.top_role.name if m.top_role and not m.top_role.is_default() else "@everyone",
                "joined": joined_iso,
                "boosting": boost_iso,
                "roles": roles_list,
            })

        if not target:
            try:
                target = await bot.fetch_user(uid)
            except Exception:
                target = None

        badges: list[str] = []
        flags = getattr(target, "public_flags", None) if target else None
        if flags:
            flag_names = [
                ("staff", "Staff"), ("partner", "Partner"), ("hypesquad", "HypeSquad"),
                ("hypesquad_bravery", "Bravery"), ("hypesquad_brilliance", "Brilliance"),
                ("hypesquad_balance", "Balance"), ("bug_hunter", "Bug Hunter"),
                ("bug_hunter_level_2", "Bug Hunter II"), ("early_supporter", "Early Supporter"),
                ("verified_bot_developer", "Verified Bot Dev"), ("active_developer", "Active Dev"),
            ]
            for attr, label in flag_names:
                if getattr(flags, attr, False):
                    badges.append(label)

        # Enrich with Discord REST profile when token is active
        bio = ""
        pronouns = ""
        banner_url = str(target.banner.url) if target and getattr(target, "banner", None) else ""
        nitro_since = ""
        connected: list[dict[str, str]] = []
        token_val = getattr(bot.http, "token", "") or ""
        if token_val:
            try:
                resp = await tools._get_http_client().get(
                    f"https://discord.com/api/v9/users/{uid}/profile?with_mutual_guilds=false&with_mutual_friends=false",
                    headers={"Authorization": token_val},
                )
                if resp.status_code == 200:
                    pdata = resp.json()
                    up = pdata.get("user_profile") or {}
                    bio = up.get("bio") or ""
                    pronouns = up.get("pronouns") or ""
                    nitro_since = (pdata.get("premium_since") or "")[:10]
                    connected = [
                        {"type": str(c.get("type", "")), "name": str(c.get("name", ""))}
                        for c in (pdata.get("connected_accounts") or [])[:8]
                    ]
                    uobj = pdata.get("user") or {}
                    if uobj.get("banner") and not banner_url:
                        ext = "gif" if str(uobj["banner"]).startswith("a_") else "png"
                        banner_url = f"https://cdn.discordapp.com/banners/{uid}/{uobj['banner']}.{ext}?size=600"
            except Exception:
                pass

        created_iso = "—"
        age_days = 0
        if target and getattr(target, "created_at", None):
            created_iso = target.created_at.strftime("%Y-%m-%d %H:%M UTC")
            age_days = max(0, int((time.time() - target.created_at.timestamp()) // 86400))

        from data.tracker import tracker
        msg_stats = tracker.get_stats(uid, None)

        return _json({
            "user_id": str(uid),
            "username": str(target) if target else f"User {uid}",
            "global_name": getattr(target, "global_name", None) or (target.name if target else f"User {uid}"),
            "avatar": str(target.display_avatar.url) if target and getattr(target, "display_avatar", None) else "",
            "banner": banner_url,
            "is_bot": bool(getattr(target, "bot", False)),
            "created_at": created_iso,
            "age_days": age_days,
            "badges": badges,
            "bio": bio,
            "pronouns": pronouns,
            "nitro_since": nitro_since,
            "connected_accounts": connected,
            "status": live_status,
            "platforms": sorted(platforms),
            "activities": activities_out,
            "voice": voice_loc,
            "mutuals": mutuals,
            "messages_global": msg_stats.get("global_all", 0),
            "messages_today": msg_stats.get("global_today", 0),
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

    async def dispatch_webhook(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        url = str(data.get("url", "")).strip()
        content = str(data.get("content", "")).strip()[:2000]
        username = str(data.get("username", "")).strip()[:80]
        if not url.startswith("https://discord.com/api/webhooks/") and not url.startswith("https://canary.discord.com/api/webhooks/"):
            return _json({"error": "Valid Discord webhook URL required"}, status=400)
        if not content:
            return _json({"error": "Message content required"}, status=400)
        payload: dict[str, Any] = {"content": content}
        if username:
            payload["username"] = username
        r = await tools._get_http_client().post(url, json=payload)
        return _json({"ok": r.status_code in (200, 204), "status": r.status_code})

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

    def _snowflake_ms(sf: Any) -> int:
        try:
            val = int(sf or 0)
            return ((val >> 22) + 1420070400000) if val > 0 else 0
        except Exception:
            return 0

    def _serialize_dm_msg(m: Any) -> dict[str, Any]:
        ref_info = None
        ref = getattr(m, "reference", None)
        if ref and getattr(ref, "resolved", None) and isinstance(ref.resolved, discord.Message):
            rm = ref.resolved
            ref_info = {
                "id": str(rm.id),
                "author": getattr(rm.author, "global_name", None) or getattr(rm.author, "name", None) or str(rm.author),
                "content": (rm.content or "[Attachment]")[:120],
            }
        elif ref and getattr(ref, "message_id", None):
            ref_info = {"id": str(ref.message_id), "author": "Message", "content": "Referenced message"}
        atts = [
            {
                "filename": a.filename,
                "url": a.url,
                "content_type": getattr(a, "content_type", "") or "",
                "is_image": str(getattr(a, "content_type", "") or "").startswith("image/")
                or str(a.filename).lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")),
                "size": getattr(a, "size", 0),
            }
            for a in (getattr(m, "attachments", []) or [])
        ]
        embeds = [
            {"title": e.title or "", "description": (e.description or "")[:300]}
            for e in (getattr(m, "embeds", []) or [])[:3]
        ]
        return {
            "id": str(m.id),
            "channel_id": str(m.channel.id),
            "author_id": str(m.author.id),
            "author": str(m.author),
            "global_name": getattr(m.author, "global_name", None) or getattr(m.author, "name", None) or str(m.author),
            "avatar": str(m.author.display_avatar.url) if getattr(m.author, "display_avatar", None) else "",
            "is_self": bool(getattr(bot, "user", None) and m.author.id == bot.user.id),
            "content": m.content or "",
            "created_at": m.created_at.strftime("%H:%M") if getattr(m, "created_at", None) else "",
            "ts_ms": int(m.created_at.timestamp() * 1000) if getattr(m, "created_at", None) else _snowflake_ms(m.id),
            "attachments": atts,
            "embeds": embeds,
            "reply_to": ref_info,
        }

    async def list_dms(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        from data.tracker import tracker
        dm_ts = tracker.get_dm_last_activity()
        items = []
        for ch in getattr(bot, "private_channels", []) or []:
            is_dm = isinstance(ch, discord.DMChannel) and ch.recipient
            is_group = isinstance(ch, discord.GroupChannel)
            if not (is_dm or is_group):
                continue
            last_sf = getattr(ch, "last_message_id", None)
            last_ms = max(_snowflake_ms(last_sf), int(dm_ts.get(ch.id, 0.0) * 1000), _snowflake_ms(ch.id))
            last_msg = getattr(ch, "last_message", None)
            preview = (getattr(last_msg, "content", "") or "")[:72] if last_msg else ""
            if is_dm:
                rec = ch.recipient
                label = getattr(rec, "global_name", None) or getattr(rec, "name", None) or str(rec)
                uname = str(rec)
                rid = str(rec.id)
                av = str(rec.display_avatar.url) if rec.display_avatar else ""
            else:
                label = getattr(ch, "name", None) or f"Group ({len(getattr(ch, 'recipients', []))})"
                uname = f"{len(getattr(ch, 'recipients', []))} members"
                rid = ""
                av = str(ch.icon.url) if getattr(ch, "icon", None) else ""
            items.append({
                "id": str(ch.id),
                "recipient": uname,
                "global_name": label,
                "recipient_id": rid,
                "avatar": av,
                "is_group": is_group,
                "last_message_id": str(last_sf or ""),
                "last_ms": last_ms,
                "_sf_sort": int(last_sf or 0),
                "preview": preview,
            })
        items.sort(key=lambda x: (x["last_ms"], x["_sf_sort"], int(x["id"])), reverse=True)
        for it in items:
            it.pop("_sf_sort", None)
        return _json({"dms": items[:80]})

    async def _resolve_channel(cid: int) -> Any:
        ch = bot.get_channel(cid)
        if not ch:
            try:
                ch = await bot.fetch_channel(cid)
            except Exception:
                ch = None
        return ch

    async def _channel_messages_get(request: web.Request, cid: int) -> web.Response:
        limit = max(5, min(int(request.query.get("limit", "40")), 100))
        before_raw = request.query.get("before", "").strip()
        ch = await _resolve_channel(cid)
        if not ch:
            return _json({"error": "Channel not found"}, status=404)

        kwargs: dict[str, Any] = {"limit": limit, "oldest_first": False}
        if before_raw.isdigit():
            kwargs["before"] = discord.Object(id=int(before_raw))

        rows = []
        async for m in ch.history(**kwargs):
            rows.append(_serialize_dm_msg(m))
        rows.reverse()

        rec = getattr(ch, "recipient", None)
        recipients_meta = []
        if rec:
            recipients_meta.append({"id": str(rec.id), "name": getattr(rec, "global_name", None) or rec.name, "username": str(rec)})
        elif getattr(ch, "recipients", None):
            for r_u in ch.recipients[:10]:
                recipients_meta.append({"id": str(r_u.id), "name": getattr(r_u, "global_name", None) or r_u.name, "username": str(r_u)})

        return _json({
            "channel_id": str(cid),
            "messages": rows,
            "has_more": len(rows) == limit,
            "recipients": recipients_meta,
        })

    async def _channel_messages_post(request: web.Request, cid: int) -> web.Response:
        ch = await _resolve_channel(cid)
        if not ch:
            return _json({"error": "Channel not found"}, status=404)

        content = ""
        reply_to = ""
        mention_author = True
        files: list[discord.File] = []

        if (request.content_type or "").startswith("multipart/"):
            reader = await request.multipart()
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == "content":
                    content = (await part.text()).strip()[:2000]
                elif part.name == "reply_to":
                    reply_to = (await part.text()).strip()
                elif part.name == "mention_author":
                    mention_author = (await part.text()).strip().lower() not in ("0", "false", "no")
                elif part.name == "file" and part.filename:
                    buf = bytearray()
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        if len(buf) > 25 * 1024 * 1024:
                            return _json({"error": "Attachment exceeds 25 MB limit"}, status=413)
                    if buf:
                        files.append(discord.File(io.BytesIO(bytes(buf)), filename=part.filename))
        else:
            data = await _body(request)
            content = str(data.get("content", "")).strip()[:2000]
            reply_to = str(data.get("reply_to", "")).strip()
            mention_author = bool(data.get("mention_author", True))

        if not content and not files:
            return _json({"error": "Message text or attachment required"}, status=400)

        send_kwargs: dict[str, Any] = {}
        if content:
            send_kwargs["content"] = content
        if files:
            send_kwargs["files"] = files
        if reply_to.isdigit():
            send_kwargs["reference"] = ch.get_partial_message(int(reply_to))
            send_kwargs["mention_author"] = mention_author

        msg = await ch.send(**send_kwargs)
        return _json({"ok": True, "message": _serialize_dm_msg(msg)})

    async def dm_messages_get(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        return await _channel_messages_get(request, int(request.match_info["id"]))

    async def dm_messages_post(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        return await _channel_messages_post(request, int(request.match_info["id"]))

    async def guild_channel_messages_get(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        return await _channel_messages_get(request, int(request.match_info["cid"]))

    async def guild_channel_messages_post(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        return await _channel_messages_post(request, int(request.match_info["cid"]))

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
        if request.method == "POST":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            cid = int(str(data.get("channel_id", "0") or "0"))
            interval_str = str(data.get("interval", "")).strip()
            text = str(data.get("text", "")).strip()[:1900]
            ch = bot.get_channel(cid)
            if not ch or not text or not interval_str:
                return _json({"error": "Valid channel_id, interval, and text required"}, status=400)
            from modules.tools import _parse_duration
            secs = _parse_duration(interval_str)
            if secs is None or secs < 15:
                return _json({"error": "Minimum interval is 15s (e.g. 30s, 15m, 1h)"}, status=400)
            tools._schedule_seq += 1
            sid = tools._schedule_seq

            async def _sched_loop() -> None:
                try:
                    while True:
                        await asyncio.sleep(secs)
                        try:
                            await ch.send(text)
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    pass

            task = asyncio.create_task(_sched_loop())
            tools._schedules[sid] = {
                "task": task,
                "interval": interval_str,
                "channel": getattr(ch, "name", str(cid)),
                "text": text[:60],
            }
            return _json({"ok": True, "id": sid})
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

    # ── Analytics, Channel Automation, Encoder, Cleanup & Troll ──────────────

    async def get_analytics(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        from data.tracker import tracker
        uid = bot.user.id if getattr(bot, "user", None) else 0
        hourly = tracker.get_hourly_activity(uid, hours=24) if uid else []
        stats = tracker.get_stats(uid, None) if uid else {}
        detailed = tracker.get_detailed_analytics(uid, bot=bot, days=14) if uid else {}
        return _json({"hourly": hourly, "stats": stats, **detailed})

    # ── Discord Orb Quest Completor ───────────────────────────────────────────

    async def quests_get(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        qcog = bot.get_cog("Quests")
        if not qcog:
            return _json({"error": "Quests module missing"}, status=503)
        sync = request.query.get("sync", "1") != "0"
        if sync and not qcog._running:
            snap = await qcog.sync_state()
        else:
            snap = qcog.snapshot()
        return _json(snap)

    async def quests_start(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        qcog = bot.get_cog("Quests")
        if not qcog:
            return _json({"error": "Quests module missing"}, status=503)
        started = await qcog.start_runner(broadcast)
        if not started:
            return _json({"error": "Quest runner already running"}, status=409)
        return _json({"ok": True, **qcog.snapshot()})

    async def quests_stop(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        qcog = bot.get_cog("Quests")
        if not qcog:
            return _json({"error": "Quests module missing"}, status=503)
        qcog.stop_runner()
        return _json({"ok": True, **qcog.snapshot()})

    async def quests_config(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        qcog = bot.get_cog("Quests")
        if not qcog:
            return _json({"error": "Quests module missing"}, status=503)
        data = await _body(request)
        cfg = qcog.update_config(data)
        return _json({"ok": True, "config": cfg, **qcog.snapshot()})

    async def automation_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools module missing"}, status=503)
        if request.method == "POST":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            kind = str(data.get("kind", "autoreply"))
            cid = int(str(data.get("channel_id", "0") or "0"))
            if not cid:
                return _json({"error": "Valid channel ID required"}, status=400)
            if kind == "autoreact":
                emojis = [str(e).strip() for e in (data.get("emojis") or []) if str(e).strip()]
                if emojis:
                    tools._auto_react[cid] = emojis
                else:
                    tools._auto_react.pop(cid, None)
            elif kind == "autoreply":
                from modules.tools import AutoReplyRule
                trig = str(data.get("trigger", "")).strip()
                resp_txt = str(data.get("response", "")).strip()
                if not trig or not resp_txt:
                    return _json({"error": "Trigger and response required"}, status=400)
                is_re = trig.startswith("/") and trig.endswith("/") and len(trig) > 2
                clean = trig[1:-1] if is_re else trig
                tools._auto_reply.setdefault(cid, []).append(AutoReplyRule(trigger=clean, response=resp_txt, is_regex=is_re))
        elif request.method == "DELETE":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            kind = str(data.get("kind", "autoreply"))
            cid = int(str(data.get("channel_id", "0") or "0"))
            if kind == "autoreact":
                tools._auto_react.pop(cid, None)
            else:
                tools._auto_reply.pop(cid, None)

        reacts = [{"channel_id": str(k), "emojis": v} for k, v in tools._auto_react.items()]
        replies = [
            {
                "channel_id": str(k),
                "rules": [{"trigger": r.trigger, "response": r.response, "is_regex": r.is_regex} for r in rules],
            }
            for k, rules in tools._auto_reply.items()
        ]
        return _json({"autoreact": reacts, "autoreply": replies})

    async def encode_tool(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        import base64
        import hashlib
        from modules.tools import MORSE_MAP, REVERSE_MORSE_MAP
        data = await _body(request)
        mode = str(data.get("mode", "b64_enc"))
        text = str(data.get("text", ""))
        if not text:
            return _json({"error": "Input text required"}, status=400)
        try:
            if mode == "b64_enc":
                out = base64.b64encode(text.encode()).decode()
            elif mode == "b64_dec":
                out = base64.b64decode(text.encode()).decode("utf-8", errors="replace")
            elif mode == "hex_enc":
                out = text.encode().hex(" ")
            elif mode == "hex_dec":
                out = bytes.fromhex(text.replace(" ", "")).decode("utf-8", errors="replace")
            elif mode == "bin_enc":
                out = " ".join(f"{b:08b}" for b in text.encode())
            elif mode == "bin_dec":
                bits = text.split()
                out = bytes(int(b, 2) for b in bits).decode("utf-8", errors="replace")
            elif mode == "morse_enc":
                out = " ".join(MORSE_MAP.get(c.upper(), "?") for c in text)
            elif mode == "morse_dec":
                out = "".join(REVERSE_MORSE_MAP.get(tok, " ") if tok != "/" else " " for tok in text.split())
            elif mode == "sha256":
                out = hashlib.sha256(text.encode()).hexdigest()
            else:
                return _json({"error": "Unknown encoder mode"}, status=400)
            return _json({"ok": True, "output": out})
        except Exception as exc:
            return _json({"error": str(exc)}, status=400)

    async def guild_cleanup(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        cid = int(str(data.get("channel_id", "0") or "0"))
        action = str(data.get("action", "topchatters"))
        ch = bot.get_channel(cid)
        if not ch:
            return _json({"error": "Channel not found"}, status=404)
        if action == "slowmode":
            secs = max(0, min(int(data.get("seconds", 0)), 21600))
            await ch.edit(slowmode_delay=secs)
            return _json({"ok": True, "detail": f"Slowmode set to {secs}s in #{ch.name}"})
        if action in ("purgelinks", "purgebots"):
            limit = max(1, min(int(data.get("limit", 100)), 250))
            deleted = 0
            async for m in ch.history(limit=limit):
                hit = (m.author.bot if action == "purgebots" else ("http://" in m.content or "https://" in m.content or "discord.gg/" in m.content))
                if hit:
                    try:
                        await m.delete()
                        deleted += 1
                        await asyncio.sleep(0.35)
                    except Exception:
                        pass
            return _json({"ok": True, "detail": f"Removed {deleted} messages in #{ch.name}"})
        if action == "topchatters":
            counts: dict[str, int] = {}
            async for m in ch.history(limit=200):
                if not m.author.bot:
                    counts[str(m.author)] = counts.get(str(m.author), 0) + 1
            ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]
            return _json({"ok": True, "top": [{"user": u, "count": c} for u, c in ranked]})
        return _json({"error": "Unknown cleanup action"}, status=400)

    async def troll_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        troll = bot.get_cog("Troll")
        if not troll:
            return _json({"error": "Troll module missing"}, status=503)
        if request.method == "POST":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            act = str(data.get("action", ""))
            if act == "mimic":
                cid = int(str(data.get("channel_id", "0") or "0"))
                uid = int(str(data.get("user_id", "0") or "0"))
                if cid and uid:
                    troll._mimic_targets[cid] = uid
                elif cid:
                    troll._mimic_targets.pop(cid, None)
            elif act == "react":
                uid = int(str(data.get("user_id", "0") or "0"))
                emoji = str(data.get("emoji", "")).strip()
                if uid and emoji:
                    troll._react_targets[uid] = emoji
                elif uid:
                    troll._react_targets.pop(uid, None)
        return _json({
            "mimic": [{"channel_id": str(c), "user_id": str(u)} for c, u in troll._mimic_targets.items()],
            "react": [{"user_id": str(u), "emoji": e} for u, e in troll._react_targets.items()],
        })

    # ── Phase 1–5 Expansion: Server Chat/Mod/Voice, Ops Console, Snipers & Assets ──

    async def guild_selfpurge(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        cid = int(str(data.get("channel_id", "0") or "0"))
        limit = max(1, min(int(data.get("limit", 40)), 120))
        ch = await _resolve_channel(cid)
        if not ch or not bot.user:
            return _json({"error": "Channel not found"}, status=404)
        deleted = 0
        async for m in ch.history(limit=limit):
            if m.author.id == bot.user.id:
                try:
                    await m.delete()
                    deleted += 1
                    await asyncio.sleep(0.32)
                except Exception:
                    pass
        return _json({"ok": True, "deleted": deleted, "detail": f"Deleted {deleted} own message(s)"})

    async def guild_member_action(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        gid = int(request.match_info["id"])
        guild = bot.get_guild(gid)
        if not guild:
            return _json({"error": "Guild not found"}, status=404)
        data = await _body(request)
        act = str(data.get("action", "")).lower().strip()
        uid = int(str(data.get("user_id", "0") or "0"))
        reason = str(data.get("reason", "")).strip() or "Dashboard action"
        if not uid:
            return _json({"error": "Valid user_id required"}, status=400)
        member = guild.get_member(uid)
        try:
            if act == "unban":
                user_obj = discord.Object(id=uid)
                await guild.unban(user_obj, reason=reason)
                return _json({"ok": True, "detail": f"Unbanned {uid}"})
            if not member:
                return _json({"error": "Member not cached in guild"}, status=404)
            if act == "kick":
                await member.kick(reason=reason)
            elif act == "ban":
                await member.ban(reason=reason, delete_message_days=0)
            elif act == "timeout":
                from datetime import timedelta
                mins = max(1, min(int(data.get("minutes", 10)), 10080))
                await member.timeout(timedelta(minutes=mins), reason=reason)
            elif act == "nick":
                nick = str(data.get("nick", "")).strip()[:32] or None
                await member.edit(nick=nick, reason=reason)
            elif act == "role":
                rid = int(str(data.get("role_id", "0") or "0"))
                role = guild.get_role(rid)
                if not role:
                    return _json({"error": "Role not found"}, status=404)
                if role in member.roles:
                    await member.remove_roles(role, reason=reason)
                    return _json({"ok": True, "detail": f"Removed @{role.name} from {member}"})
                await member.add_roles(role, reason=reason)
                return _json({"ok": True, "detail": f"Added @{role.name} to {member}"})
            else:
                return _json({"error": "Unknown member action"}, status=400)
            return _json({"ok": True, "detail": f"{act.title()} applied to {member}"})
        except Exception as exc:
            return _json({"error": str(exc)}, status=400)

    async def guild_webhooks_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        gid = int(request.match_info["id"])
        guild = bot.get_guild(gid)
        if not guild:
            return _json({"error": "Guild not found"}, status=404)
        if request.method == "POST":
            auth.authenticate_request(request, require_csrf=True)
            data = await _body(request)
            cid = int(str(data.get("channel_id", "0") or "0"))
            name = str(data.get("name", "Globe Hook")).strip()[:80] or "Globe Hook"
            ch = guild.get_channel(cid)
            if not ch:
                return _json({"error": "Channel not found in guild"}, status=404)
            wh = await ch.create_webhook(name=name)
            return _json({"ok": True, "webhook": {"id": str(wh.id), "name": wh.name, "url": wh.url, "channel": ch.name}})
        if request.method == "DELETE":
            auth.authenticate_request(request, require_csrf=True)
            wid = int(request.match_info["wid"])
            hooks = await guild.webhooks()
            target = next((h for h in hooks if h.id == wid), None)
            if not target:
                return _json({"error": "Webhook not found"}, status=404)
            await target.delete()
            return _json({"ok": True})
        hooks = await guild.webhooks()
        return _json({
            "webhooks": [
                {"id": str(h.id), "name": h.name, "url": h.url, "channel": getattr(h.channel, "name", "—")}
                for h in hooks[:40]
            ]
        })

    async def guild_clone(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        src_id = int(str(data.get("source_id", "0") or "0"))
        dst_id = int(str(data.get("target_id", "0") or "0"))
        src = bot.get_guild(src_id)
        dst = bot.get_guild(dst_id)
        if not src or not dst or src.id == dst.id:
            return _json({"error": "Provide distinct valid Source and Target Guild IDs"}, status=400)

        async def _clone_job() -> None:
            try:
                for ch in list(dst.channels):
                    try:
                        await ch.delete()
                        await asyncio.sleep(0.35)
                    except Exception:
                        pass
                for r_obj in list(dst.roles):
                    if not r_obj.is_default() and not r_obj.managed:
                        try:
                            await r_obj.delete()
                            await asyncio.sleep(0.3)
                        except Exception:
                            pass
                for r_obj in reversed(src.roles):
                    if not r_obj.is_default() and not r_obj.managed:
                        try:
                            await dst.create_role(name=r_obj.name, permissions=r_obj.permissions, colour=r_obj.colour, hoist=r_obj.hoist, mentionable=r_obj.mentionable)
                            await asyncio.sleep(0.35)
                        except Exception:
                            pass
                for cat in src.categories:
                    try:
                        ncat = await dst.create_category(name=cat.name)
                        for ch in cat.channels:
                            if isinstance(ch, discord.TextChannel):
                                await dst.create_text_channel(name=ch.name, category=ncat, topic=ch.topic, slowmode_delay=ch.slowmode_delay)
                            elif isinstance(ch, discord.VoiceChannel):
                                await dst.create_voice_channel(name=ch.name, category=ncat)
                            await asyncio.sleep(0.35)
                    except Exception:
                        pass
                await broadcast({"type": "job", "data": {"job": "clone", "done": True, "source": src.name, "target": dst.name}})
            except Exception as exc:
                await broadcast({"type": "job", "data": {"job": "clone", "done": True, "error": str(exc)}})

        asyncio.create_task(_clone_job())
        return _json({"ok": True, "started": True})

    async def voice_roster(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        active = []
        for g in getattr(bot, "guilds", []) or []:
            for vc in getattr(g, "voice_channels", []) or []:
                if getattr(vc, "members", None):
                    active.append({
                        "guild_id": str(g.id),
                        "guild": g.name,
                        "channel_id": str(vc.id),
                        "channel": vc.name,
                        "members": [
                            {
                                "id": str(m.id),
                                "name": getattr(m, "global_name", None) or m.name,
                                "avatar": str(m.display_avatar.url) if getattr(m, "display_avatar", None) else "",
                                "mute": bool(getattr(getattr(m, "voice", None), "self_mute", False) or getattr(getattr(m, "voice", None), "mute", False)),
                                "deaf": bool(getattr(getattr(m, "voice", None), "self_deaf", False) or getattr(getattr(m, "voice", None), "deaf", False)),
                            }
                            for m in vc.members[:30]
                        ],
                    })
        return _json({"roster": active[:25]})

    async def voice_extra_control(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        act = str(data.get("action", ""))
        if act == "moveall":
            src = bot.get_channel(int(str(data.get("source_id", "0") or "0")))
            dst = bot.get_channel(int(str(data.get("dest_id", "0") or "0")))
            if not src or not dst:
                return _json({"error": "Source or destination VC not found"}, status=404)
            moved = 0
            for m in list(getattr(src, "members", [])):
                try:
                    await m.move_to(dst)
                    moved += 1
                    await asyncio.sleep(0.25)
                except Exception:
                    pass
            return _json({"ok": True, "moved": moved})
        if act == "vckick":
            gid = int(str(data.get("guild_id", "0") or "0"))
            uid = int(str(data.get("user_id", "0") or "0"))
            g = bot.get_guild(gid)
            m = g.get_member(uid) if g else None
            if not m or not getattr(m, "voice", None):
                return _json({"error": "Member not in voice"}, status=404)
            await m.move_to(None)
            return _json({"ok": True})
        return _json({"error": "Invalid voice extra action"}, status=400)

    async def afk_pings_handler(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        if request.method == "DELETE":
            auth.authenticate_request(request, require_csrf=True)
            if hasattr(bot, "_afk_pings"):
                bot._afk_pings.clear()
            return _json({"ok": True})
        return _json({
            "afk": bool(getattr(bot, "_afk_active", False)),
            "reason": getattr(bot, "_afk_reason", "") or "",
            "pings": list(getattr(bot, "_afk_pings", []))[::-1],
        })

    async def intel_esnipes(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        util = bot.get_cog("Utility")
        rows = []
        if util and getattr(util, "_edited", None):
            for cid, dq in util._edited.items():
                for rec in dq:
                    rows.append({
                        "channel_id": str(cid),
                        "author": str(rec.author),
                        "before": getattr(rec, "before", "") or "",
                        "after": getattr(rec, "content", "") or "",
                        "timestamp": rec.timestamp.timestamp() if getattr(rec, "timestamp", None) else 0,
                    })
        rows.sort(key=lambda x: x["timestamp"], reverse=True)
        return _json({"esnipes": rows[:40]})

    async def intel_snipers(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        tools = bot.get_cog("Tools")
        return _json({
            "snipers": list(getattr(tools, "_sniper_logs", []))[::-1] if tools else [],
            "keyword_hits": list(getattr(tools, "_keyword_hits", []))[::-1] if tools else [],
        })

    async def system_exec(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        raw = str(data.get("command", "")).strip()
        if not raw:
            return _json({"error": "Command required"}, status=400)
        if raw.startswith(settings.prefix):
            raw = raw[len(settings.prefix):].strip()
        parts = raw.split()
        cmd = bot.get_command(parts[0].lower()) if parts else None
        if not cmd:
            return _json({"ok": False, "output": [f"Unknown command: {parts[0] if parts else raw}"]})

        captured: list[str] = []

        class _WebMsg:
            id = 0
            author = getattr(bot, "user", None)
            content = f"{settings.prefix}{raw}"
            guild = None
            channel = None
            async def delete(self, **kw: Any) -> None:
                return None
            async def reply(self, txt: str = "", **kw: Any) -> Any:
                if txt:
                    captured.append(txt)
                return self

        class _WebCh:
            id = 0
            name = "web-console"
            async def send(self, txt: str = "", **kw: Any) -> Any:
                if txt:
                    captured.append(txt)
                return _WebMsg()

        wch = _WebCh()
        wmsg = _WebMsg()
        wmsg.channel = wch

        class _WebCtx:
            def __init__(self) -> None:
                self.bot = bot
                self.command = cmd
                self.cog = cmd.cog
                self.author = getattr(bot, "user", None)
                self.guild = None
                self.channel = wch
                self.message = wmsg
                self.prefix = settings.prefix
                self.invoked_with = parts[0]
            async def send(self, content: str = "", **kw: Any) -> Any:
                if content:
                    captured.append(str(content))
                return wmsg
            async def reply(self, content: str = "", **kw: Any) -> Any:
                return await self.send(content)

        ctx = _WebCtx()
        try:
            args_str = parts[1:]
            sig_params = list(cmd.clean_params.values())
            if not sig_params:
                await cmd.callback(cmd.cog, ctx) if cmd.cog else await cmd.callback(ctx)
            elif len(sig_params) == 1 and sig_params[0].kind == sig_params[0].KEYWORD_ONLY:
                val = " ".join(args_str)
                await cmd.callback(cmd.cog, ctx, **{sig_params[0].name: val}) if cmd.cog else await cmd.callback(ctx, **{sig_params[0].name: val})
            else:
                await cmd.callback(cmd.cog, ctx, *args_str) if cmd.cog else await cmd.callback(ctx, *args_str)
        except Exception as exc:
            captured.append(f"Error: {exc}")
        return _json({"ok": True, "command": raw, "output": captured or [f"Executed '{raw}'"]})

    async def invite_inspect(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        code = str(data.get("invite", "")).rstrip("/").split("/")[-1].split("?")[0].strip()
        if not code:
            return _json({"error": "Invite code required"}, status=400)
        resp = await tools._get_http_client().get(f"https://discord.com/api/v9/invites/{code}?with_counts=true&with_expiration=true")
        if resp.status_code != 200:
            return _json({"error": f"Discord HTTP {resp.status_code}"}, status=resp.status_code)
        d = resp.json()
        g = d.get("guild") or {}
        inv = d.get("inviter") or {}
        return _json({
            "ok": True,
            "result": {
                "code": d.get("code"),
                "guild": g.get("name"),
                "guild_id": g.get("id"),
                "members": d.get("approximate_member_count"),
                "online": d.get("approximate_presence_count"),
                "vanity": g.get("vanity_url_code"),
                "boosts": g.get("premium_subscription_count"),
                "verification_level": g.get("verification_level"),
                "inviter": inv.get("username"),
                "expires_at": d.get("expires_at"),
            },
        })

    async def steal_emoji(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        gid = int(str(data.get("guild_id", "0") or "0"))
        name = str(data.get("name", "")).strip()[:32]
        src = str(data.get("source", "")).strip()
        guild = bot.get_guild(gid)
        if not guild or not src:
            return _json({"error": "Valid guild_id and emoji/URL required"}, status=400)
        import re as _re
        m = _re.match(r"<(a?):([A-Za-z0-9_]+):(\d+)>", src)
        if m:
            anim, ename, eid = m.groups()
            ext = "gif" if anim else "png"
            url = f"https://cdn.discordapp.com/emojis/{eid}.{ext}"
            name = name or ename
        elif src.isdigit():
            url = f"https://cdn.discordapp.com/emojis/{src}.png"
        else:
            url = src
        if not name:
            name = "stolen_emoji"
        img_resp = await tools._get_http_client().get(url)
        if img_resp.status_code != 200:
            return _json({"error": f"Failed to fetch image (HTTP {img_resp.status_code})"}, status=400)
        em = await guild.create_custom_emoji(name=name, image=img_resp.content)
        return _json({"ok": True, "emoji": str(em), "name": em.name, "id": str(em.id)})

    async def translate_tool(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        if not tools:
            return _json({"error": "Tools missing"}, status=503)
        data = await _body(request)
        text = str(data.get("text", "")).strip()[:1500]
        target = str(data.get("target_lang", "en")).strip()[:10] or "en"
        if not text:
            return _json({"error": "Text required"}, status=400)
        r = await tools._get_http_client().get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text},
        )
        arr = r.json()
        translated = "".join(seg[0] for seg in (arr[0] or []) if seg and seg[0])
        return _json({"ok": True, "translated": translated, "detected": arr[2] if len(arr) > 2 else "auto"})

    async def qr_tool(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        import base64
        import qrcode
        import qrcode.image.svg
        data = await _body(request)
        text = str(data.get("text", "")).strip()[:1000]
        if not text:
            return _json({"error": "Text or URL required"}, status=400)
        buf = io.BytesIO()
        try:
            img = qrcode.make(text)
            img.save(buf, format="PNG")
            mime = "image/png"
        except Exception:
            buf = io.BytesIO()
            img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage)
            img.save(buf)
            mime = "image/svg+xml"
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return _json({"ok": True, "data_uri": f"data:{mime};base64,{b64}"})

    async def set_profile_identity(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        tools = bot.get_cog("Tools")
        token_val = getattr(bot.http, "token", "") or ""
        if not tools or not token_val:
            return _json({"error": "Unavailable"}, status=503)
        data = await _body(request)
        payload: dict[str, Any] = {}
        if "global_name" in data:
            payload["global_name"] = str(data.get("global_name", "")).strip()[:32]
        if data.get("avatar_url"):
            import base64
            img_r = await tools._get_http_client().get(str(data["avatar_url"]).strip())
            if img_r.status_code != 200:
                return _json({"error": "Could not download avatar URL"}, status=400)
            ct = img_r.headers.get("content-type", "image/png").split(";")[0]
            payload["avatar"] = f"data:{ct};base64,{base64.b64encode(img_r.content).decode('ascii')}"
        if not payload:
            return _json({"error": "Provide global_name or avatar_url"}, status=400)
        r = await tools._get_http_client().patch(
            "https://discord.com/api/v9/users/@me",
            headers={"Authorization": token_val},
            json=payload,
        )
        if r.status_code != 200:
            return _json({"error": f"Discord HTTP {r.status_code}"}, status=r.status_code)
        return _json({"ok": True})

    async def troll_extra(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        act = str(data.get("action", ""))
        cid = int(str(data.get("channel_id", "0") or "0"))
        ch = await _resolve_channel(cid)
        if not ch:
            return _json({"error": "Channel not found"}, status=404)
        if act == "faketyping":
            secs = max(3, min(int(data.get("seconds", 12)), 90))
            async def _type_job() -> None:
                async with ch.typing():
                    await asyncio.sleep(secs)
            asyncio.create_task(_type_job())
            return _json({"ok": True, "detail": f"Typing in #{getattr(ch, 'name', cid)} for {secs}s"})
        if act == "ghostedit":
            first = str(data.get("text", "...")).strip()[:1800] or "..."
            edit_to = str(data.get("edit_to", "")).strip()[:1800]
            delay = max(1.0, min(float(data.get("delay", 3.0)), 30.0))
            async def _ge_job() -> None:
                m = await ch.send(first)
                await asyncio.sleep(delay)
                if edit_to:
                    await m.edit(content=edit_to)
                else:
                    await m.delete()
            asyncio.create_task(_ge_job())
            return _json({"ok": True, "detail": "Ghost-edit dispatched"})
        return _json({"error": "Unknown tactical action"}, status=400)

    # ── Multi-Account Vault & Token Management ────────────────────────────────

    async def _verify_discord_token(raw_token: str) -> dict[str, Any]:
        clean = raw_token.strip().strip("'\"")
        if len(clean) < 30:
            raise ValueError("Token format is too short.")
        tools = bot.get_cog("Tools")
        if not tools:
            raise RuntimeError("Tools HTTP client unavailable")
        resp = await tools._get_http_client().get(
            "https://discord.com/api/v9/users/@me",
            headers={"Authorization": clean},
        )
        if resp.status_code != 200:
            raise ValueError(f"Discord rejected token (HTTP {resp.status_code}).")
        u = resp.json()
        uid = str(u.get("id", ""))
        uname = f"{u.get('username', 'user')}#{u.get('discriminator', '0')}"
        gname = u.get("global_name") or u.get("username") or uname
        av = u.get("avatar")
        avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{av}.png?size=128" if av and uid else ""
        return {"id": uid, "username": uname, "global_name": gname, "avatar": avatar_url, "token": clean}

    def _activate_token_and_restart(new_token: str) -> None:
        from dotenv import set_key
        clean = new_token.strip().strip("'\"")
        env_path = Path(".env")
        if not env_path.exists():
            env_path.write_text("", encoding="utf-8")
        set_key(str(env_path), "DISCORD_TOKEN", clean)
        global_auth._token = clean
        global_auth.save_token_to_file(clean)
        settings.discord_token = clean  # type: ignore[misc]
        os.environ["DISCORD_TOKEN"] = clean

        async def _delayed_exec() -> None:
            await asyncio.sleep(1.0)
            os.execv(sys.executable, [sys.executable] + sys.argv)

        asyncio.create_task(_delayed_exec())

    async def accounts_list(request: web.Request) -> web.Response:
        auth.authenticate_request(request)
        _sync_active_account_vault()
        uid = str(bot.user.id) if getattr(bot, "user", None) else ""
        return _json({"accounts": auth.list_accounts(uid)})

    async def accounts_add(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        tok = str(data.get("token", "")).strip()
        switch_now = bool(data.get("switch_now", False))
        try:
            info = await _verify_discord_token(tok)
        except ValueError as exc:
            return _json({"error": str(exc)}, status=400)
        except Exception as exc:
            return _json({"error": str(exc)}, status=503)

        auth.register_account(info["id"], info["username"], info["global_name"], info["avatar"], info["token"])
        global_auth.save_token_to_file(info["token"])
        if switch_now:
            _activate_token_and_restart(info["token"])
            return _json({"ok": True, "restarting": True, "active_id": info["id"]})
        uid = str(bot.user.id) if getattr(bot, "user", None) else ""
        return _json({"ok": True, "accounts": auth.list_accounts(uid), "added": info["id"]})

    async def accounts_delete(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        aid = str(request.match_info["id"])
        uid = str(bot.user.id) if getattr(bot, "user", None) else ""
        if aid == uid:
            return _json({"error": "Cannot remove the currently active account."}, status=400)
        tok = auth.get_account_token(aid)
        ok = auth.remove_account(aid)
        if tok:
            global_auth.remove_token_from_file(tok)
        return _json({"ok": ok, "accounts": auth.list_accounts(uid)})

    async def accounts_switch(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        aid = str(data.get("account_id", "")).strip()
        tok = auth.get_account_token(aid) if aid else str(data.get("token", "")).strip()
        if not tok:
            return _json({"error": "Account token not found in vault."}, status=404)
        _activate_token_and_restart(tok)
        return _json({"ok": True, "restarting": True, "account_id": aid})

    async def update_active_token(request: web.Request) -> web.Response:
        auth.authenticate_request(request, require_csrf=True)
        data = await _body(request)
        tok = str(data.get("token", "")).strip()
        try:
            info = await _verify_discord_token(tok)
        except ValueError as exc:
            return _json({"error": str(exc)}, status=400)
        except Exception as exc:
            return _json({"error": str(exc)}, status=503)
        auth.register_account(info["id"], info["username"], info["global_name"], info["avatar"], info["token"])
        _activate_token_and_restart(info["token"])
        return _json({"ok": True, "restarting": True, "account_id": info["id"], "username": info["username"]})

    # Register Routes
    r = app.router
    r.add_get("/api/v1/auth/me", auth_me)
    r.add_post("/api/v1/auth/login", auth_login)
    r.add_post("/api/v1/auth/logout", auth_logout)
    r.add_post("/api/v1/auth/revoke", auth_revoke)

    r.add_get("/api/v1/accounts", accounts_list)
    r.add_post("/api/v1/accounts", accounts_add)
    r.add_delete("/api/v1/accounts/{id}", accounts_delete)
    r.add_post("/api/v1/accounts/switch", accounts_switch)
    r.add_post("/api/v1/settings/token", update_active_token)

    r.add_get("/api/v1/overview", get_overview)
    r.add_get("/api/v1/analytics", get_analytics)
    r.add_post("/api/v1/toggles", update_toggles)

    r.add_post("/api/v1/presence/custom", set_custom_status)
    r.add_post("/api/v1/presence/status", set_online_status)
    r.add_post("/api/v1/presence/activity", set_rich_activity)
    r.add_post("/api/v1/presence/bio", set_bio)
    r.add_post("/api/v1/presence/profile", set_profile_identity)
    r.add_post("/api/v1/presence/hypesquad", set_hypesquad)
    r.add_post("/api/v1/presence/rotate", set_status_rotate)
    r.add_post("/api/v1/presence/spoofer", control_spoofer)

    r.add_get("/api/v1/intel/snipes", get_snipes)
    r.add_get("/api/v1/intel/esnipes", intel_esnipes)
    r.add_get("/api/v1/intel/snipers", intel_snipers)
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
    r.add_post("/api/v1/tools/invite-inspect", invite_inspect)
    r.add_post("/api/v1/tools/steal-emoji", steal_emoji)
    r.add_post("/api/v1/tools/translate", translate_tool)
    r.add_post("/api/v1/tools/qr", qr_tool)
    r.add_post("/api/v1/tools/encode", encode_tool)
    r.add_get("/api/v1/tools/automation", automation_handler)
    r.add_post("/api/v1/tools/automation", automation_handler)
    r.add_delete("/api/v1/tools/automation", automation_handler)
    r.add_get("/api/v1/troll/control", troll_handler)
    r.add_post("/api/v1/troll/control", troll_handler)
    r.add_post("/api/v1/troll/extra", troll_extra)
    r.add_get("/api/v1/intel/friends/diff", friends_action)
    r.add_post("/api/v1/intel/friends", friends_action)
    r.add_post("/api/v1/intel/user-profile", profile_user)

    r.add_get("/api/v1/guilds", list_guilds)
    r.add_get("/api/v1/guilds/{id}/channels/{cid}/messages", guild_channel_messages_get)
    r.add_post("/api/v1/guilds/{id}/channels/{cid}/messages", guild_channel_messages_post)
    r.add_post("/api/v1/guilds/{id}/selfpurge", guild_selfpurge)
    r.add_post("/api/v1/guilds/{id}/members/action", guild_member_action)
    r.add_get("/api/v1/guilds/{id}/webhooks", guild_webhooks_handler)
    r.add_post("/api/v1/guilds/{id}/webhooks", guild_webhooks_handler)
    r.add_delete("/api/v1/guilds/{id}/webhooks/{wid}", guild_webhooks_handler)
    r.add_post("/api/v1/guilds/clone", guild_clone)
    r.add_post("/api/v1/guilds/cleanup", guild_cleanup)
    r.add_post("/api/v1/dispatch/send", dispatch_send)
    r.add_post("/api/v1/dispatch/webhook", dispatch_webhook)
    r.add_get("/api/v1/guilds/{id}/audit", audit_guild)
    r.add_get("/api/v1/guilds/{id}/backup", backup_guild_download)
    r.add_post("/api/v1/guilds/lockdown", guild_lockdown)
    r.add_get("/api/v1/voice/roster", voice_roster)
    r.add_post("/api/v1/voice", voice_control)
    r.add_post("/api/v1/voice/extra", voice_extra_control)

    r.add_get("/api/v1/afk/pings", afk_pings_handler)
    r.add_delete("/api/v1/afk/pings", afk_pings_handler)
    r.add_get("/api/v1/dms", list_dms)
    r.add_get("/api/v1/dms/{id}/messages", dm_messages_get)
    r.add_post("/api/v1/dms/{id}/messages", dm_messages_post)
    r.add_get("/api/v1/dms/{id}/export", export_dm)
    r.add_post("/api/v1/dms/{id}/wipe", wipe_dm)
    r.add_get("/api/v1/quests", quests_get)
    r.add_post("/api/v1/quests/start", quests_start)
    r.add_post("/api/v1/quests/stop", quests_stop)
    r.add_post("/api/v1/quests/config", quests_config)
    r.add_get("/api/v1/bookmarks", bookmarks_handler)
    r.add_delete("/api/v1/bookmarks/{id}", bookmarks_handler)
    r.add_get("/api/v1/schedules", schedules_handler)
    r.add_post("/api/v1/schedules", schedules_handler)
    r.add_delete("/api/v1/schedules/{id}", schedules_handler)
    r.add_post("/api/v1/system", system_action)
    r.add_post("/api/v1/system/exec", system_exec)
