"""
Globe Web Control Plane — Authentication, Session Signing, CSRF & Rate-Limit Shield.
Authenticates directly against the active Discord account token in volatile RAM
using constant-time verification, HMAC-SHA256 signed cookies, and per-IP lockout.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Callable

from aiohttp import web

COOKIE_NAME = "globe_session"
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 120.0
_WINDOW_SECONDS = 180.0


class DashboardAuth:
    """Manages token-based login, signed HttpOnly cookies, CSRF tokens, and IP rate limits."""

    def __init__(self, token_provider: Callable[[], str | None]) -> None:
        self._token_provider = token_provider
        self._secret: bytes = self._load_or_create_secret()
        self._attempts: dict[str, list[float]] = {}
        self._lockouts: dict[str, float] = {}

    @staticmethod
    def _load_or_create_secret() -> bytes:
        try:
            from data.tracker import tracker
            existing = tracker.get_state("web_secret")
            if existing and len(existing) >= 32:
                return bytes.fromhex(existing)
            new_secret = os.urandom(32)
            tracker.set_state("web_secret", new_secret.hex())
            return new_secret
        except Exception:
            return os.urandom(32)

    def revoke_all_sessions(self) -> None:
        """Rotate signing secret so every issued session cookie becomes immediately invalid."""
        new_secret = os.urandom(32)
        self._secret = new_secret
        try:
            from data.tracker import tracker
            tracker.set_state("web_secret", new_secret.hex())
        except Exception:
            pass

    @staticmethod
    def client_ip(request: web.Request) -> str:
        """Resolve originating IP honoring Cloudflare Tunnel headers."""
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return request.remote or "unknown"

    def check_rate_limit(self, ip: str) -> float | None:
        """Return remaining lockout seconds if IP is rate-limited, else None."""
        now = time.monotonic()
        until = self._lockouts.get(ip)
        if until:
            if now < until:
                return round(until - now, 1)
            self._lockouts.pop(ip, None)
            self._attempts.pop(ip, None)
        return None

    def record_failure(self, ip: str) -> float | None:
        """Record failed auth attempt and return lockout duration if threshold tripped."""
        now = time.monotonic()
        recent = [t for t in self._attempts.get(ip, []) if now - t <= _WINDOW_SECONDS]
        recent.append(now)
        self._attempts[ip] = recent
        if len(recent) >= _MAX_ATTEMPTS:
            self._lockouts[ip] = now + _LOCKOUT_SECONDS
            self._attempts[ip] = []
            return _LOCKOUT_SECONDS
        return None

    def clear_failures(self, ip: str) -> None:
        self._attempts.pop(ip, None)
        self._lockouts.pop(ip, None)

    def verify_account_token(self, submitted: str) -> bool:
        """Verify submitted Discord token against active account token in constant time."""
        active = (self._token_provider() or "").strip().strip("'\"")
        candidate = (submitted or "").strip().strip("'\"")
        if candidate.lower().startswith("bearer "):
            candidate = candidate[7:].strip()
        if not active or not candidate:
            return False
        return hmac.compare_digest(candidate.encode("utf-8"), active.encode("utf-8"))

    def _sign(self, payload_b64: str) -> str:
        sig = hmac.new(self._secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    def csrf_for_session(self, session_id: str) -> str:
        return hmac.new(
            self._secret,
            f"csrf:{session_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:32]

    def create_session(self, ttl_seconds: int = 86400) -> tuple[str, str]:
        """Return (signed_cookie_value, csrf_token)."""
        sid = secrets.token_hex(16)
        payload = {"sid": sid, "exp": int(time.time()) + ttl_seconds}
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        token = f"{b64}.{self._sign(b64)}"
        return token, self.csrf_for_session(sid)

    def verify_cookie(self, cookie_val: str | None) -> dict[str, Any] | None:
        """Validate cookie signature and expiration, returning payload + csrf if valid."""
        if not cookie_val or "." not in cookie_val:
            return None
        b64, sig = cookie_val.split(".", 1)
        expected_sig = self._sign(b64)
        if not hmac.compare_digest(sig, expected_sig):
            return None
        try:
            padded = b64 + "=" * (-len(b64) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
            if int(data.get("exp", 0)) < int(time.time()):
                return None
            data["csrf"] = self.csrf_for_session(data["sid"])
            return data
        except Exception:
            return None

    def authenticate_request(self, request: web.Request, require_csrf: bool = False) -> dict[str, Any]:
        """Raise HTTPUnauthorized / HTTPForbidden if session or CSRF is invalid."""
        session = self.verify_cookie(request.cookies.get(COOKIE_NAME))
        if not session:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "Authentication required"}),
                content_type="application/json",
            )
        if require_csrf:
            hdr = request.headers.get("X-Globe-CSRF", "")
            if not hdr or not hmac.compare_digest(hdr, session["csrf"]):
                raise web.HTTPForbidden(
                    text=json.dumps({"error": "Invalid CSRF token"}),
                    content_type="application/json",
                )
        return session
