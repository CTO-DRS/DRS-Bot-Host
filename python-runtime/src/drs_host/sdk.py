"""Public SDK used *inside* bots::

    from drs_host.sdk import get_context

    ctx = get_context()
    while not ctx.should_stop:
        ctx.logger.info("working ...")
        ctx.sleep_or_stop(5)

The context is injected into the bot thread by the runner, so bots never
touch host internals directly.
"""

from __future__ import annotations

import contextvars
import threading


class StopRequested(Exception):
    """Raised by the host when a bot must stop immediately."""


class BotContext:
    """Everything a bot is allowed to know about its host and run."""

    def __init__(self, bot_id: str, name: str, config: dict, stop_event: threading.Event, logger):
        self.bot_id = bot_id
        self.name = name
        self.config = dict(config or {})
        self.stop_event = stop_event
        self.logger = logger
        self._progress = {"value": None, "total": None, "label": None}
        self._progress_lock = threading.Lock()

    @property
    def should_stop(self) -> bool:
        """True once the host asked this bot to stop."""
        return self.stop_event.is_set()

    def sleep_or_stop(self, seconds: float) -> bool:
        """Sleep up to ``seconds``.

        Returns True if a stop was requested during the wait (the bot should
        exit promptly), False if the full interval elapsed. Bots that poll
        ``should_stop`` between short sleeps remain fully cooperative.
        """
        if seconds <= 0:
            return self.stop_event.is_set()
        return self.stop_event.wait(timeout=seconds)

    def set_progress(self, value=None, total=None, label=None) -> None:
        """Publish optional progress information shown in the app UI."""
        with self._progress_lock:
            self._progress = {"value": value, "total": total, "label": label}

    def snapshot_progress(self) -> dict:
        with self._progress_lock:
            return dict(self._progress)


_current: contextvars.ContextVar = contextvars.ContextVar("drs_bot_context", default=None)


def get_context() -> BotContext | None:
    """Return the running bot's context, or None outside a bot thread."""
    return _current.get()


def set_context(ctx: BotContext):
    """Install a context for the current thread (used by the runner)."""
    return _current.set(ctx)


def reset_context(token) -> None:
    """Restore the previous context (used by the runner on exit)."""
    _current.reset(token)
