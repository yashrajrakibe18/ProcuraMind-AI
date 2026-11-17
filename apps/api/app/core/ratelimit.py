"""Tiny in-process sliding-window limiter for login attempts (use a shared store behind multiple workers)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from procureai.shared.errors import AppError


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max, self.window = max_events, window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            raise RateLimited("Too many attempts. Please wait a minute and try again.")

    def hit(self, key: str) -> None:
        self._events[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._events.pop(key, None)


login_limiter = SlidingWindowLimiter(max_events=8, window_seconds=60)
