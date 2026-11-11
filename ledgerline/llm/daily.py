"""The global daily cap on model spend, kept in a small SQLite file so it survives a
restart.

Every live call reserves its worst-case cost before it is made, then settles to what it
really cost. The reservation and the check happen in one write transaction, so two
requests (or two processes sharing the file) can never both spend the last of the
day's allowance. A "day" is a UTC calendar day.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ledgerline.llm.errors import LLMError

CAP_REACHED = "Today's budget for live answers is used up. Try again tomorrow."


class DailyCapReachedError(LLMError):
    """A call's worst case would take today's spend past the daily cap."""

    def __init__(self, spent: float, needed: float, cap: float) -> None:
        super().__init__(CAP_REACHED)
        self.spent = spent
        self.needed = needed
        self.cap = cap


class DailySpend:
    def __init__(
        self,
        path: Path,
        cap_usd: float,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if cap_usd < 0:
            raise ValueError("the daily cap must be >= 0")
        self.path = path
        self.cap_usd = cap_usd
        self.clock = clock
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS spend (day TEXT PRIMARY KEY, usd REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None leaves transactions to the explicit BEGIN below.
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def _day(self) -> str:
        return self.clock().astimezone(UTC).date().isoformat()

    def spent_today(self) -> float:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT usd FROM spend WHERE day = ?", (self._day(),)).fetchone()
        return float(row[0]) if row else 0.0

    def reserve(self, worst_case_usd: float) -> str:
        """Add `worst_case_usd` to today's spend, or refuse if it would pass the cap.
        Returns the day it was charged to, for `settle`."""
        day = self._day()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT usd FROM spend WHERE day = ?", (day,)).fetchone()
            spent = float(row[0]) if row else 0.0
            if spent + worst_case_usd > self.cap_usd:
                conn.execute("ROLLBACK")
                raise DailyCapReachedError(spent, worst_case_usd, self.cap_usd)
            conn.execute(
                "INSERT INTO spend (day, usd) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET usd = usd + excluded.usd",
                (day, worst_case_usd),
            )
            conn.execute("COMMIT")
        finally:
            conn.close()
        return day

    def settle(self, day: str, reserved_usd: float, actual_usd: float) -> None:
        """Replace a reservation with the call's real cost (0 if it was never billed)."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE spend SET usd = MAX(0, usd - ? + ?) WHERE day = ?",
                (reserved_usd, actual_usd, day),
            )
