"""
Globe Embedded Web Server (aiohttp.web + WebSocket Real-Time Telemetry Hub).
Runs inside GlobeBot's existing asyncio event loop for zero-IPC control.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any, Callable

from aiohttp import WSMsgType, web

from config import settings
from ui import log_info, log_warn
from ui.console import register_log_listener, unregister_log_listener
from web.api_routes import register_routes
from web.auth import DashboardAuth

STATIC_DIR = Path(__file__).parent / "static"


class DashboardServer:
    """Lifecycle wrapper for Globe's embedded aiohttp control plane."""

    def __init__(
        self,
        bot: Any,
        token_provider: Callable[[], str | None],
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.bot = bot
        self.host = host or settings.dashboard_host
        self.port = port or settings.dashboard_port
        self.auth = DashboardAuth(token_provider)
        self.app = self._build_app()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._recent_logs: deque[dict[str, str]] = deque(maxlen=120)
        self._telemetry_task: asyncio.Task | None = None
        self._log_cb = self._on_log_entry

    def _on_log_entry(self, entry: dict[str, str]) -> None:
        self._recent_logs.append(entry)
        if self._ws_clients:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.broadcast({"type": "log", "data": entry}))
            except RuntimeError:
                pass

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if not self._ws_clients:
            return
        raw = json.dumps(payload, default=str)
        dead: list[web.WebSocketResponse] = []
        for ws in list(self._ws_clients):
            if ws.closed:
                dead.append(ws)
                continue
            try:
                await ws.send_str(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    async def _telemetry_loop(self) -> None:
        """Push gateway latency and active switchboard telemetry every 4s."""
        try:
            while True:
                await asyncio.sleep(4.0)
                if not self._ws_clients:
                    continue
                lat_raw = getattr(self.bot, "latency", 0.0) or 0.0
                lat_ms = round(lat_raw * 1000, 1) if lat_raw == lat_raw else 0.0
                status_cog = self.bot.get_cog("Status")
                await self.broadcast({
                    "type": "telemetry",
                    "data": {
                        "latency_ms": lat_ms,
                        "uptime_s": int(getattr(self.bot, "uptime_seconds", 0.0)),
                        "guilds": len(getattr(self.bot, "guilds", []) or []),
                        "friends": len(getattr(self.bot, "friends", []) or []),
                        "spoofer_running": bool(getattr(status_cog, "_spoofer_running", False)) if status_cog else False,
                    },
                })
        except asyncio.CancelledError:
            pass

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        try:
            self.auth.authenticate_request(request, require_csrf=False)
        except web.HTTPException as exc:
            raise exc

        ws = web.WebSocketResponse(heartbeat=25.0)
        await ws.prepare(request)
        self._ws_clients.add(ws)

        # Send buffered recent logs on initial connect
        try:
            await ws.send_str(json.dumps({
                "type": "init",
                "data": {"logs": list(self._recent_logs)[-60:]},
            }))
            async for msg in ws:
                if msg.type == WSMsgType.TEXT and msg.data == "ping":
                    await ws.send_str('{"type":"pong"}')
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._ws_clients.discard(ws)
        return ws

    @staticmethod
    async def _index_handler(request: web.Request) -> web.FileResponse:
        return web.FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    def _build_app(self) -> web.Application:
        app = web.Application()
        register_routes(app, self.bot, self.auth, self.broadcast, lambda: list(self._recent_logs))
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/", self._index_handler)
        if STATIC_DIR.exists():
            app.router.add_static("/static", STATIC_DIR, show_index=False)
        return app

    async def start(self) -> None:
        register_log_listener(self._log_cb)
        self._runner = web.AppRunner(self.app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        log_info(f"Web Control Plane active at http://{self.host}:{self.port}")

    async def stop(self) -> None:
        unregister_log_listener(self._log_cb)
        if self._telemetry_task and not self._telemetry_task.done():
            self._telemetry_task.cancel()
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()
        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception as e:
                log_warn(f"Dashboard cleanup warning: {e}")
