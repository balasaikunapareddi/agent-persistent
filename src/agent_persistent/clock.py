from __future__ import annotations
import time
class VirtualClock:
    """Injectable clock: virtual time advances without real sleeps."""
    def __init__(self, start: float = 1700000000.0):
        self._now=float(start)
    def now(self)->float: return self._now
    def advance(self, seconds: float)->float:
        self._now+=float(seconds); return self._now
    def advance_days(self, days: float)->float: return self.advance(days*86400)
class SystemClock:
    def now(self)->float: return time.time()
