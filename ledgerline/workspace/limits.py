"""The limits on what a workspace may hold, and the per-IP rate limiter.

Every limit is enforced on the server. The upload limits apply while a file streams in,
so an oversized file is refused before it is fully read."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

MB = 1024 * 1024


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 10 * MB
    max_files: int = 10
    max_columns: int = 200
    max_rows: int = 1_000_000
    max_cell_chars: int = 10_000
    # Messages shown per file; the rest are counted ("and N more like this").
    max_messages: int = 20
    # All workspaces together, raw uploads and loaded databases included.
    disk_cap_bytes: int = 2 * 1024 * MB
    workspaces_per_ip: int = 3
    asks_per_hour: int = 30
    uploads_per_hour: int = 20
    idle_days: int = 7


class RateLimiter:
    """At most `limit` events per key in any `window_s` seconds (a sliding window).
    It lives in the process, so each server process counts on its own."""

    def __init__(
        self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Count one event for `key`, or refuse it if the window is full."""
        now = self.clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= now - self.window_s:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True
