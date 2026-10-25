"""Thread-aware stdout capture.

Android hosts one Python interpreter (Chaquopy) for every bot, but bots run
in separate threads. ``ThreadAwareStream`` replaces ``sys.stdout`` once per
process and dispatches writes to the stream registered by the *current*
thread, so each bot's ``print()`` output lands in its own log buffer and
never leaks into another bot's logs (or into the host's own output).
"""

from __future__ import annotations

import threading


class ThreadAwareStream:
    """A ``sys.stdout`` replacement with per-thread routing."""

    def __init__(self, fallback):
        self._fallback = fallback
        self._local = threading.local()

    def register(self, stream) -> None:
        """Route writes made by the calling thread to ``stream``."""
        self._local.stream = stream

    def unregister(self) -> None:
        """Restore the calling thread to the fallback stream."""
        self._local.stream = None

    def registered(self) -> bool:
        return getattr(self._local, "stream", None) is not None

    def write(self, s):
        stream = getattr(self._local, "stream", None) or self._fallback
        try:
            return stream.write(s)
        except Exception:  # noqa: BLE001 - never let logging kill a bot thread
            return len(s)

    def flush(self) -> None:
        stream = getattr(self._local, "stream", None) or self._fallback
        try:
            stream.flush()
        except Exception:  # noqa: BLE001
            pass

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return getattr(self._fallback, "encoding", "utf-8")
