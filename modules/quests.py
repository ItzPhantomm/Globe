"""
Globe — Discord Orb Quest Completor Cog
Safely fetches live Discord Orbs balance and pending quests, filters by reward type
(default: Orbs-only), and completes eligible video/play/activity quests with
humanized stealth timing, jittered heartbeats, and live WebSocket telemetry.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from discord.ext import commands

from config import settings
from ui import log_err, log_info, log_warn

SUPPORTED_TASKS = (
    "WATCH_VIDEO",
    "WATCH_VIDEO_ON_MOBILE",
    "PLAY_ON_DESKTOP",
    "PLAY_ACTIVITY",
    "STREAM_ON_DESKTOP",
)

_DEFAULT_CONFIG: dict[str, Any] = {
    "orbs_only": True,
    "auto_enroll": True,
    "pace_mode": "stealth",
    "allowed_tasks": list(SUPPORTED_TASKS),
}


def _build_super_properties() -> str:
    payload = {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": "1.0.9185",
        "os_version": "10.0.22631",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "browser_user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9185 Chrome/130.0.6723.191 Electron/33.4.0 Safari/537.36"
        ),
        "browser_version": "33.4.0",
        "client_build_number": 382491,
        "client_event_source": None,
    }
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


_SUPER_PROPS = _build_super_properties()
_CLIENT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "discord/1.0.9185 Chrome/130.0.6723.191 Electron/33.4.0 Safari/537.36"
)


class Quests(commands.Cog):
    """Orb Quest Completor with configurable filtering and humanized anti-detection pacing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._http: httpx.AsyncClient | None = None
        self._running: bool = False
        self._cancel: bool = False
        self._task: asyncio.Task | None = None
        self._orb_balance: int = 0
        self._completed_session_orbs: int = 0
        self._completed_total_orbs: int = self._load_int("quest_completed_orbs", 0)
        self._completed_count: int = self._load_int("quest_completed_count", 0)
        self._config: dict[str, Any] = self._load_config()
        self._quests_cache: list[dict[str, Any]] = []
        self._current_quest_id: str = ""
        self._current_quest_name: str = ""
        self._status_line: str = "Standby"
        self._last_sync: float = 0.0

    @staticmethod
    def _load_int(key: str, default: int) -> int:
        try:
            from data.tracker import tracker
            raw = tracker.get_state(key)
            return int(raw) if raw is not None else default
        except Exception:
            return default

    @staticmethod
    def _save_state(key: str, value: str) -> None:
        try:
            from data.tracker import tracker
            tracker.set_state(key, value)
        except Exception:
            pass

    def _load_config(self) -> dict[str, Any]:
        cfg = dict(_DEFAULT_CONFIG)
        try:
            from data.tracker import tracker
            raw = tracker.get_state("quest_config")
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    cfg["orbs_only"] = bool(loaded.get("orbs_only", True))
                    cfg["auto_enroll"] = bool(loaded.get("auto_enroll", True))
                    mode = str(loaded.get("pace_mode", "stealth")).lower()
                    cfg["pace_mode"] = mode if mode in ("stealth", "standard") else "stealth"
                    tasks = loaded.get("allowed_tasks")
                    if isinstance(tasks, list) and tasks:
                        cfg["allowed_tasks"] = [t for t in tasks if t in SUPPORTED_TASKS] or list(SUPPORTED_TASKS)
        except Exception:
            pass
        return cfg

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Update and persist quest filter & stealth pacing settings."""
        if "orbs_only" in patch:
            self._config["orbs_only"] = bool(patch["orbs_only"])
        if "auto_enroll" in patch:
            self._config["auto_enroll"] = bool(patch["auto_enroll"])
        if "pace_mode" in patch:
            m = str(patch["pace_mode"]).lower().strip()
            if m in ("stealth", "standard"):
                self._config["pace_mode"] = m
        if isinstance(patch.get("allowed_tasks"), list):
            clean = [t for t in patch["allowed_tasks"] if t in SUPPORTED_TASKS]
            if clean:
                self._config["allowed_tasks"] = clean
        self._save_state("quest_config", json.dumps(self._config))
        return dict(self._config)

    def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=14.0, follow_redirects=True)
        return self._http

    def _token(self) -> str:
        return (getattr(getattr(self.bot, "http", None), "token", "") or settings.discord_token or "").strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._token(),
            "User-Agent": _CLIENT_UA,
            "X-Super-Properties": _SUPER_PROPS,
            "X-Discord-Locale": "en-US",
            "Content-Type": "application/json",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/quests",
        }

    async def cog_unload(self) -> None:
        self._cancel = True
        if self._task and not self._task.done():
            self._task.cancel()
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    @staticmethod
    def _is_expired(expires_at: str | None) -> bool:
        if not expires_at:
            return False
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return exp <= datetime.now(timezone.utc)
        except Exception:
            return False

    @classmethod
    def parse_quest(cls, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw Discord quest object into UI-friendly telemetry."""
        qid = str(raw.get("id", ""))
        cfg = raw.get("config") or {}
        msgs = cfg.get("messages") or {}
        app = cfg.get("application") or {}
        user_st = raw.get("user_status") or {}

        rewards = ((cfg.get("rewards_config") or {}).get("rewards")) or []
        orb_reward = 0
        reward_names: list[str] = []
        is_orbs = False
        for rw in rewards:
            r_type = rw.get("type")
            qty = int(rw.get("orb_quantity") or 0)
            r_name = ((rw.get("messages") or {}).get("name")) or rw.get("name") or ""
            if r_name:
                reward_names.append(str(r_name))
            if qty > 0 or r_type == 4 or "orb" in str(r_name).lower():
                is_orbs = True
                orb_reward += qty if qty > 0 else 0

        task_cfg = cfg.get("task_config_v2") or cfg.get("task_config") or {}
        tasks = task_cfg.get("tasks") or {}
        task_type = ""
        seconds_needed = 0
        for candidate in SUPPORTED_TASKS:
            if candidate in tasks:
                task_type = candidate
                seconds_needed = int((tasks[candidate] or {}).get("target") or 0)
                break
        if not task_type and tasks:
            first_k = next(iter(tasks.keys()))
            task_type = str(first_k)
            seconds_needed = int((tasks[first_k] or {}).get("target") or 0)

        progress_map = user_st.get("progress") or {}
        seconds_done = float(((progress_map.get(task_type) or {}).get("value")) or 0)
        enrolled_at = user_st.get("enrolled_at")
        completed_at = user_st.get("completed_at")
        claimed_at = user_st.get("claimed_at")
        pct = 100 if completed_at else min(99, int((seconds_done / max(1, seconds_needed)) * 100)) if seconds_needed else 0

        return {
            "id": qid,
            "name": msgs.get("quest_name") or app.get("name") or f"Quest {qid}",
            "game_name": app.get("name") or msgs.get("game_title") or "Discord Quest",
            "application_id": str(app.get("id") or ""),
            "expires_at": cfg.get("expires_at") or "",
            "expired": cls._is_expired(cfg.get("expires_at")),
            "orb_reward": orb_reward,
            "is_orbs": is_orbs,
            "reward_label": f"{orb_reward} Orbs" if orb_reward > 0 else (", ".join(reward_names) or "Reward"),
            "task_type": task_type,
            "supported": task_type in SUPPORTED_TASKS,
            "seconds_done": round(seconds_done, 1),
            "seconds_needed": seconds_needed,
            "pct": pct,
            "enrolled": bool(enrolled_at),
            "completed": bool(completed_at),
            "claimed": bool(claimed_at),
        }

    async def sync_state(self) -> dict[str, Any]:
        """Fetch live Orbs balance and pending quests from Discord REST API."""
        tok = self._token()
        if not tok:
            return self.snapshot()
        client = self._get_client()
        hdrs = self._headers()

        # 1. Fetch live Orbs balance
        try:
            bal_resp = await client.get("https://discord.com/api/v9/users/@me/virtual-currency/balance", headers=hdrs)
            if bal_resp.status_code == 200:
                bdata = bal_resp.json()
                self._orb_balance = int(bdata.get("balance", self._orb_balance) or 0)
        except Exception:
            pass

        # 2. Fetch quests
        try:
            q_resp = await client.get("https://discord.com/api/v9/quests/@me", headers=hdrs)
            if q_resp.status_code == 200:
                raw_quests = q_resp.json().get("quests") or []
                parsed = [self.parse_quest(q) for q in raw_quests]
                self._quests_cache = [q for q in parsed if not q["expired"]]
                self._last_sync = time.time()
            elif q_resp.status_code == 401:
                self._status_line = "Token rejected by Discord"
        except Exception as exc:
            log_warn(f"Quest sync error: {exc}")

        return self.snapshot()

    def filtered_pending_quests(self) -> list[dict[str, Any]]:
        orbs_only = bool(self._config.get("orbs_only", True))
        allowed = set(self._config.get("allowed_tasks") or SUPPORTED_TASKS)
        out = []
        for q in self._quests_cache:
            if q["completed"] or q["expired"] or not q["supported"]:
                continue
            if orbs_only and not q["is_orbs"]:
                continue
            if q["task_type"] not in allowed:
                continue
            out.append(q)
        return out

    def snapshot(self) -> dict[str, Any]:
        pending_eligible = self.filtered_pending_quests()
        return {
            "running": self._running,
            "orb_balance": self._orb_balance,
            "completed_session_orbs": self._completed_session_orbs,
            "completed_total_orbs": self._completed_total_orbs,
            "completed_count": self._completed_count,
            "current_quest_id": self._current_quest_id,
            "current_quest_name": self._current_quest_name,
            "status_line": self._status_line,
            "config": dict(self._config),
            "pending_eligible_count": len(pending_eligible),
            "quests": list(self._quests_cache),
            "last_sync": int(self._last_sync),
        }

    async def _sleep_cancelable(self, seconds: float) -> bool:
        """Sleep in 0.5s slices so cancel takes effect immediately; return True if cancelled."""
        steps = max(1, int(seconds * 2))
        for _ in range(steps):
            if self._cancel:
                return True
            await asyncio.sleep(0.5)
        return self._cancel

    async def _emit(self, broadcast: Callable[[dict[str, Any]], Any] | None) -> None:
        if broadcast:
            try:
                await broadcast({"type": "job", "data": {"job": "quests", **self.snapshot()}})
            except Exception:
                pass

    async def start_runner(self, broadcast: Callable[[dict[str, Any]], Any] | None = None) -> bool:
        """Start humanized background Orb quest runner."""
        if self._running:
            return False
        self._running = True
        self._cancel = False
        self._completed_session_orbs = 0
        self._status_line = "Syncing pending quests..."
        await self._emit(broadcast)

        async def _run() -> None:
            client = self._get_client()
            try:
                await self.sync_state()
                targets = self.filtered_pending_quests()
                if not targets:
                    uncompleted = [q for q in self._quests_cache if not q["completed"] and not q["expired"]]
                    if uncompleted:
                        self._status_line = f"{len(uncompleted)} pending quest(s) skipped by Orbs-only / task filters"
                    else:
                        self._status_line = "No eligible pending quests found"
                    await self._emit(broadcast)
                    return

                is_stealth = self._config.get("pace_mode", "stealth") == "stealth"
                for q in targets:
                    if self._cancel:
                        break
                    qid = q["id"]
                    self._current_quest_id = qid
                    self._current_quest_name = q["name"]
                    hdrs = self._headers()

                    # Optional auto-enrollment with human reaction pause
                    if not q["enrolled"] and self._config.get("auto_enroll", True):
                        self._status_line = f"Enrolling in {q['name']}..."
                        await self._emit(broadcast)
                        if await self._sleep_cancelable(random.uniform(1.8, 3.8)):
                            break
                        er = await client.post(
                            f"https://discord.com/api/v9/quests/{qid}/enroll",
                            headers=hdrs,
                            json={"location": 11, "is_targeted": False},
                        )
                        if er.status_code == 429:
                            retry_s = float(er.json().get("retry_after", 5.0) or 5.0)
                            await self._sleep_cancelable(retry_s + 1.0)
                        elif er.status_code in (200, 204):
                            q["enrolled"] = True
                        else:
                            log_warn(f"Quest enroll failed ({er.status_code}): {er.text[:140]}")
                            self._status_line = f"Enroll failed HTTP {er.status_code} on {q['name']}"
                            await self._emit(broadcast)

                    needed = max(1, int(q["seconds_needed"]))
                    done_s = float(q["seconds_done"])
                    ttype = q["task_type"]

                    if ttype in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"):
                        # Humanized scrubbed progression respecting wall-clock guardrails
                        step_min, step_max = (4.0, 6.0) if is_stealth else (6.0, 8.0)
                        wait_min, wait_max = (3.2, 4.8) if is_stealth else (2.2, 3.2)
                        fail_streak = 0
                        while done_s < needed and not self._cancel:
                            next_s = min(float(needed), done_s + random.uniform(step_min, step_max))
                            self._status_line = f"Watching {q['name']} ({int(next_s)}/{needed}s)"
                            vr = await client.post(
                                f"https://discord.com/api/v9/quests/{qid}/video-progress",
                                headers=hdrs,
                                json={"timestamp": round(next_s, 3)},
                            )
                            if vr.status_code == 429:
                                retry_s = float(vr.json().get("retry_after", 4.0) or 4.0)
                                await self._sleep_cancelable(retry_s + 0.8)
                                continue
                            if vr.status_code == 200:
                                fail_streak = 0
                                done_s = next_s
                                q["seconds_done"] = round(done_s, 1)
                                q["pct"] = min(100, int((done_s / needed) * 100))
                                body = vr.json()
                                if body.get("completed_at"):
                                    q["completed"] = True
                                    q["pct"] = 100
                                    break
                            elif vr.status_code == 400 and fail_streak < 5:
                                # Wall-clock guardrail hit; pace 1:1 and retry
                                fail_streak += 1
                                step_min, step_max = 1.5, 2.5
                                wait_min, wait_max = 3.0, 4.0
                                await self._sleep_cancelable(3.0)
                                continue
                            else:
                                log_warn(f"Video quest progress error ({vr.status_code}): {vr.text[:140]}")
                                self._status_line = f"Video error HTTP {vr.status_code} on {q['name']}"
                                await self._emit(broadcast)
                                break
                            await self._emit(broadcast)
                            if done_s >= needed:
                                break
                            if await self._sleep_cancelable(random.uniform(wait_min, wait_max)):
                                break
                    else:
                        # Play / Activity / Stream heartbeat loop with realistic cadence & jitter
                        hb_min, hb_max = (22.0, 32.0) if is_stealth else (16.0, 21.0)
                        app_id = q["application_id"]
                        while not self._cancel:
                            self._status_line = f"Playing {q['game_name']} ({int(done_s)}/{needed}s)"
                            await self._emit(broadcast)
                            payload: dict[str, Any] = {"terminal": False}
                            if ttype in ("PLAY_ACTIVITY", "STREAM_ON_DESKTOP"):
                                payload["stream_key"] = f"call:{qid}:1"
                            elif app_id:
                                payload["application_id"] = app_id

                            hr = await client.post(
                                f"https://discord.com/api/v9/quests/{qid}/heartbeat",
                                headers=hdrs,
                                json=payload,
                            )
                            if hr.status_code == 429:
                                retry_s = float(hr.json().get("retry_after", 6.0) or 6.0)
                                await self._sleep_cancelable(retry_s + 1.0)
                                continue
                            if hr.status_code == 200:
                                hdata = hr.json()
                                prog = ((hdata.get("progress") or {}).get(ttype) or {}).get("value")
                                if prog is not None:
                                    done_s = float(prog)
                                else:
                                    done_s = min(float(needed), done_s + hb_min)
                                q["seconds_done"] = round(done_s, 1)
                                q["pct"] = min(100, int((done_s / needed) * 100))
                                if hdata.get("completed_at") or done_s >= needed:
                                    payload["terminal"] = True
                                    await client.post(
                                        f"https://discord.com/api/v9/quests/{qid}/heartbeat",
                                        headers=hdrs,
                                        json=payload,
                                    )
                                    q["completed"] = True
                                    q["pct"] = 100
                                    break
                            else:
                                log_warn(f"Quest heartbeat failed ({hr.status_code}): {hr.text[:140]}")
                                self._status_line = f"Heartbeat HTTP {hr.status_code} on {q['name']}"
                                await self._emit(broadcast)
                                break

                            if await self._sleep_cancelable(random.uniform(hb_min, hb_max)):
                                break

                    if q["completed"] or done_s >= needed:
                        q["completed"] = True
                        q["pct"] = 100
                        earned = int(q.get("orb_reward") or 0)
                        self._completed_session_orbs += earned
                        self._completed_total_orbs += earned
                        self._completed_count += 1
                        self._save_state("quest_completed_orbs", str(self._completed_total_orbs))
                        self._save_state("quest_completed_count", str(self._completed_count))
                        log_info(f"Completed quest '{q['name']}' (+{earned} Orbs)")

                    # Human pause between quests
                    if await self._sleep_cancelable(random.uniform(3.0, 6.5)):
                        break

                await self.sync_state()
                self._status_line = "Cancelled by user" if self._cancel else "All pending quests finished"
            except asyncio.CancelledError:
                self._status_line = "Stopped"
            except Exception as exc:
                log_err(f"Quest runner error: {exc}")
                self._status_line = f"Error: {exc}"
            finally:
                self._running = False
                self._cancel = False
                self._current_quest_id = ""
                self._current_quest_name = ""
                await self._emit(broadcast)

        self._task = asyncio.create_task(_run())
        return True

    def stop_runner(self) -> None:
        self._cancel = True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quests(bot))
