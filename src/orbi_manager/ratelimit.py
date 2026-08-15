"""Cooldown after the site rate-limits a destructive request.

Kept in its own module so the UI can render a countdown without touching the
network code.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from . import config

TickCallback = Callable[[int], None]


class Cooldown:
    """Sleeps ``seconds`` in one-second steps, reporting the remainder.

    The sleep is interruptible: :meth:`cancel` makes an in-flight ``wait``
    return immediately so the UI can stop a batch without waiting out a full
    60 second pause.
    """

    def __init__(self, seconds: int = config.DELETE_COOLDOWN_SEC) -> None:
        self.seconds = max(int(seconds), config.MIN_COOLDOWN_SEC)
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def wait(self, on_tick: TickCallback | None = None) -> bool:
        """Wait out the cooldown. Returns False if it was cancelled early."""
        for remaining in range(self.seconds, 0, -1):
            if self._cancelled.is_set():
                return False
            if on_tick is not None:
                on_tick(remaining)
            time.sleep(1)
        if on_tick is not None:
            on_tick(0)
        return not self._cancelled.is_set()
