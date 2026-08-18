"""The pause between one ordinary request and the next.

Distinct from :mod:`ratelimit`, which handles the long wait after the site
has explicitly told us to stop. This is the ordinary, no-one-complained
spacing that keeps a batch from arriving all at once.

Two ideas, both aimed at removing dead time without raising the ceiling on
how hard the server is hit:

* **Rate, not gap.** The interval is counted from the moment the previous
  request *started*, so a request that itself took 400ms does not then wait
  a further full interval. Requests per second are unchanged; only the time
  spent waiting for nothing goes away.
* **AIMD.** The interval climbs multiplicatively the moment the site answers
  429 and steps back down additively while it stays happy. A fixed delay
  keeps knocking at exactly the same rate no matter what the site says back;
  this reacts to what the site actually reports.

Because ``PACE_START_SEC`` and ``PACE_FLOOR_SEC`` are the same value, the
additive decrease is purely a *recovery* path — it walks back down after a
429 raised the interval, and never takes a batch below the floor.

The wait is interruptible: it blocks on a :class:`threading.Event` rather
than in :func:`time.sleep`, so a stop lands during the pause instead of
after it.
"""

from __future__ import annotations

import threading
import time

from . import config
from .models import ActionResult, Status


class Pacer:
    """Adaptive, rate-based spacing between requests in one run."""

    def __init__(
        self,
        *,
        start: float = config.PACE_START_SEC,
        floor: float = config.PACE_FLOOR_SEC,
        ceiling: float = config.PACE_CEILING_SEC,
        speedup_after: int = config.PACE_SPEEDUP_AFTER,
        backoff_factor: float = config.PACE_BACKOFF_FACTOR,
        cancel: threading.Event | None = None,
    ) -> None:
        self._floor = max(0.0, float(floor))
        self._ceiling = max(self._floor, float(ceiling))
        self._interval = min(max(float(start), self._floor), self._ceiling)
        self._speedup_after = max(1, int(speedup_after))
        self._backoff_factor = max(1.0, float(backoff_factor))
        self._cancel = cancel if cancel is not None else threading.Event()
        self._streak = 0
        #: When the last request was allowed to start. ``None`` until the
        #: first :meth:`wait`, which is why the first row is never delayed.
        self._last_start: float | None = None

    @classmethod
    def fixed(
        cls, seconds: float, cancel: threading.Event | None = None
    ) -> Pacer:
        """A constant interval that never adapts — 안전 모드, and tests.

        Floor and ceiling meet, so :meth:`on_result` has nothing to move and
        the batch keeps exactly one code path either way.
        """
        return cls(start=seconds, floor=seconds, ceiling=seconds, cancel=cancel)

    # -- state ---------------------------------------------------------------

    @property
    def interval(self) -> float:
        """Seconds currently being aimed for between request starts."""
        return self._interval

    @property
    def adaptive(self) -> bool:
        return self._ceiling > self._floor

    # -- use -----------------------------------------------------------------

    def wait(self) -> bool:
        """Block until the next request may start. False if cancelled.

        Call this immediately *before* each request, not after: that is what
        makes the interval measure request start to request start, and it
        means a batch that ends early never sat through a trailing pause.
        """
        if self._cancel.is_set():
            return False

        if self._last_start is not None:
            remaining = self._interval - (time.monotonic() - self._last_start)
            # `Event.wait` returns True when the event was set, i.e. cancelled.
            if remaining > 0 and self._cancel.wait(remaining):
                return False

        self._last_start = time.monotonic()
        return not self._cancel.is_set()

    def on_rate_limited(self) -> None:
        """The site answered 429: back off hard, right away."""
        if not self.adaptive:
            return
        self._interval = min(self._ceiling, self._interval * self._backoff_factor)
        self._streak = 0

    def on_success(self) -> None:
        """One more request the site did not complain about."""
        if not self.adaptive:
            return
        self._streak += 1
        if self._streak >= self._speedup_after:
            self._streak = 0
            self._interval = max(self._floor, self._interval - self._floor / 2)

    def on_result(self, result: ActionResult) -> None:
        """Convenience for callers already holding a delete :class:`ActionResult`."""
        if result.status is Status.RATE_LIMITED:
            self.on_rate_limited()
        else:
            self.on_success()
