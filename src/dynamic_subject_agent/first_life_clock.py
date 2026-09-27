"""A single online window lease; no wall-clock catch-up or canonical writer."""
from threading import RLock
from time import monotonic


class FirstLifeClock:
    def __init__(self, clock=monotonic):
        self._clock = clock
        self._lock = RLock()
        self._owner = None
        self._last = self._expires = 0.0
        self._seconds = 0.0
        self._busy = False

    def heartbeat(self, session, *, paused, allow_step=True):
        with self._lock:
            now = self._clock()
            if self._owner is None or now >= self._expires:
                self._owner, self._last, self._expires, self._seconds = session, now, now + 15, 0.0
                return False, "online-baseline"
            if session != self._owner:
                return False, "another-life-window"
            elapsed = max(0.0, min(15.0, now - self._last))
            self._last, self._expires = now, now + 15
            self._seconds = 0.0 if paused else min(60.0, self._seconds + elapsed)
            if not allow_step:
                return False, "pending-lease-renewed"
            if paused or self._busy or self._seconds < 60:
                return False, "paused" if paused else "no-decision-boundary"
            self._seconds -= 60
            self._busy = True
            return True, "online-step"

    def simulation(self, *, paused):
        with self._lock:
            if paused or self._busy: return False
            self._busy = True
            return True

    def share(self):
        with self._lock:
            if self._busy or self._owner is None or self._clock() >= self._expires: return False
            self._busy = True
            return True

    def reset_pause(self):
        with self._lock:
            self._seconds = 0.0
            self._last = self._clock()

    def finished(self):
        with self._lock: self._busy = False

    def lease_valid(self):
        with self._lock: return self._owner is not None and self._clock() < self._expires

    def busy(self):
        with self._lock: return self._busy
