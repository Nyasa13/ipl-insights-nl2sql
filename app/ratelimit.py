"""Tiny in-memory limiter so strangers cannot drain your free LLM quota.
Per-client sliding window plus a global daily cap. Single process only (fine for a demo)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, daily_cap: int):
        self.per_minute, self.daily_cap = per_minute, daily_cap
        self._hits: dict[str, deque] = defaultdict(deque)
        self._day, self._day_count = time.strftime("%Y-%m-%d"), 0
        self._lock = threading.Lock()

    def check(self, client: str) -> tuple[bool, str]:
        now = time.time()
        with self._lock:
            today = time.strftime("%Y-%m-%d")
            if today != self._day:
                self._day, self._day_count = today, 0
            if self._day_count >= self.daily_cap:
                return False, "Daily demo quota reached. Please try again tomorrow."
            q = self._hits[client]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False, f"Rate limit: max {self.per_minute} questions per minute."
            q.append(now)
            self._day_count += 1
            return True, ""
