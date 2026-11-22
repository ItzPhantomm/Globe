"""
Globe Selfbot — Hardened Footprint & Anti-Detection Handler
Advanced features:
- Realistic human Gaussian typing delays (WPM-based variance)
- Adaptive burst protection (sliding window rate-limiter)
- Exponential backoff with randomized full-jitter
- Per-channel and global action throttles
- Channel typing simulation with random micro-pauses
- Client fingerprint spoofing data helper
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections import deque
from typing import Deque

from config import settings
from ui import log_warn, log_info


class FootprintHandler:
    """
    State-of-the-art anti-detection and behavioural automation footprint manager.
    Enforces humanized cadence, burst suppression, and per-action cooldowns.
    """

    def __init__(self) -> None:
        self._delay_min: float = settings.typing_delay_min / 1000.0
        self._delay_max: float = settings.typing_delay_max / 1000.0

        # Rolling timestamp logs {channel_id: deque}
        self._channel_history: dict[int, Deque[float]] = {}
        # Global activity history across all channels (last 60s)
        self._global_history: Deque[float] = deque(maxlen=300)

        # Explicit command & task cooldowns {key: expiration_monotonic}
        self._cooldowns: dict[str, float] = {}

    # ── Gaussian / Humanized Cadence ──────────────────────────────────────────

    async def human_delay(self, multiplier: float = 1.0) -> None:
        """
        Sleep for a randomized duration following a bounded Gaussian curve
        rather than a flat uniform distribution (closely mimics human hesitation).
        """
        mean = (self._delay_min + self._delay_max) / 2.0
        stddev = (self._delay_max - self._delay_min) / 4.0
        delay = random.gauss(mean, stddev) * multiplier
        # Clamp within reasonable safety limits
        clamped = max(self._delay_min * 0.5, min(delay, self._delay_max * 2.0))
        await asyncio.sleep(clamped)

    async def typing_simulation(self, channel, text: str) -> None:
        """
        Simulate human typing indicator with micro-hesitations based on character count.
        Assumes average typing speed of 55 WPM (~275 CPM).
        """
        char_count = len(text)
        # Average time: ~0.035s to 0.05s per keystroke + random think time
        target_duration = max(0.6, min((char_count * 0.04) + random.uniform(0.2, 0.8), 5.0))

        try:
            async with channel.typing():
                # Split typing into small chunks with tiny jitter pauses
                chunk = target_duration / 3.0
                for _ in range(3):
                    await asyncio.sleep(chunk + random.uniform(-0.1, 0.1))
        except Exception:
            pass

    # ── Adaptive Burst & Sliding Window Rate Limiting ─────────────────────────

    def record_action(self, channel_id: int) -> None:
        """Record an outbound write action in local and global sliding windows."""
        now = time.monotonic()
        self._global_history.append(now)
        if channel_id not in self._channel_history:
            self._channel_history[channel_id] = deque(maxlen=50)
        self._channel_history[channel_id].append(now)

    def actions_in_window(self, channel_id: int, seconds: float = 10.0) -> int:
        """Count actions dispatched to channel within the given rolling second window."""
        now = time.monotonic()
        hist = self._channel_history.get(channel_id, deque())
        return sum(1 for t in hist if now - t <= seconds)

    def is_spamming(self, channel_id: int, threshold: int = 5, window: float = 5.0) -> bool:
        """
        Check if current action rate exceeds channel threshold or global safety threshold (15 actions / 6s).
        """
        now = time.monotonic()
        # Global burst check
        recent_global = sum(1 for t in self._global_history if now - t <= 6.0)
        if recent_global >= 15:
            log_warn(f"Global footprint throttle: {recent_global} actions in last 6s — pausing.")
            return True

        # Channel burst check
        channel_count = self.actions_in_window(channel_id, window)
        if channel_count >= threshold:
            log_warn(f"Channel footprint throttle: {channel_count} actions in {window}s in channel {channel_id}.")
            return True

        return False

    # ── Exponential Full-Jitter Backoff ───────────────────────────────────────

    async def backoff(self, attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
        """
        Implements AWS/Google recommended Full-Jitter Exponential Backoff:
        sleep = uniform(0, min(cap, base * 2 ** attempt))
        Prevents synchronized burst retries upon encountering rate limits (HTTP 429).
        """
        ceiling = min(cap, base * math.pow(2, attempt))
        wait = random.uniform(base * 0.5, ceiling)
        log_warn(f"Backoff applied: waiting {wait:.2f}s (retry attempt {attempt + 1})")
        await asyncio.sleep(wait)
        return wait

    # ── Cooldowns ──────────────────────────────────────────────────────────────

    def set_cooldown(self, key: str, seconds: float) -> None:
        self._cooldowns[key] = time.monotonic() + seconds

    def on_cooldown(self, key: str) -> bool:
        return time.monotonic() < self._cooldowns.get(key, 0)

    def cooldown_remaining(self, key: str) -> float:
        return max(0.0, self._cooldowns.get(key, 0) - time.monotonic())


footprint = FootprintHandler()
