"""Cron-like scheduling for supervised bots (v1.2).

Two schedule kinds, declared in ``bot.json``::

    "schedule": {"kind": "interval", "interval_seconds": 3600,
                 "run_seconds": 300, "enabled": true}
    "schedule": {"kind": "daily", "time": "09:00",
                 "duration_seconds": 3600, "enabled": true}

``interval`` re-starts the bot every ``interval_seconds``; when
``run_seconds`` is set, each scheduled run is stopped after that long.
``daily`` keeps the bot running inside a window that opens at local
``time`` each day for ``duration_seconds``.

The scheduler is a single daemon thread ticking once per second. It only
acts on window *edges*, so a bot the user stopped manually is never
fought over until the next window opens. Scheduling state lives on the
:class:`~drs_host.supervisor.SupervisedBot` record (under
``schedule_state``) so status payloads can surface "next start" hints.
"""

from __future__ import annotations

import threading
import time

from .states import BotState

DEFAULT_TICK_SECONDS = 1.0


def _minutes_of_day(clock: str) -> int:
    hours, _, minutes = clock.partition(":")
    return int(hours) * 60 + int(minutes)


def within_daily_window(clock: str, duration_seconds: float, now: float) -> bool:
    """True when ``now`` (epoch) falls inside today's ``HH:MM`` window.

    Windows may wrap past midnight (e.g. 23:50 + 1200s), which is handled
    by comparing minute-of-day ranges in both directions.
    """
    if duration_seconds <= 0:
        return False
    local = time.localtime(now)
    now_minutes = local.tm_hour * 60 + local.tm_min
    now_seconds_of_day = now_minutes * 60 + local.tm_sec
    start_seconds = _minutes_of_day(clock) * 60
    offset = (now_seconds_of_day - start_seconds) % 86400
    return offset < duration_seconds


def next_daily_start(clock: str, now: float) -> float:
    """Epoch timestamp of the next window open at/after ``now``."""
    local = time.localtime(now)
    # 9-field mktime tuple: year, mon, mday, h, m, s, wday, yday, isdst
    today_start = time.mktime(
        (
            local.tm_year,
            local.tm_mon,
            local.tm_mday,
            *_minutes_of_day_pair(clock),
            0,
            0,
            -1,
        )
    )
    if today_start <= now:
        today_start += 86400
    return today_start


def _minutes_of_day_pair(clock: str) -> tuple:
    hours, _, minutes = clock.partition(":")
    return int(hours), int(minutes), 0


class BotScheduler:
    """Starts and stops scheduled bots on their configured windows."""

    def __init__(self, supervisor, *, tick_seconds: float = DEFAULT_TICK_SECONDS):
        self._supervisor = supervisor
        self._tick = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._window_state: dict = {}  # bot_id -> in-window bool (daily kind)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="drs-scheduler", daemon=True
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._tick):
            try:
                self.tick_once(time.time())
            except Exception:  # noqa: BLE001 - the scheduler must never die
                continue

    # ------------------------------------------------------------------ #
    # Scheduling                                                         #
    # ------------------------------------------------------------------ #

    def tick_once(self, now: float) -> None:
        """One scheduling pass over every installed bot."""
        supervisor = self._supervisor
        with supervisor.lock:
            bots = list(supervisor.bots.values())
        for bot in bots:
            spec = bot.manifest.schedule
            if not spec or not spec.get("enabled", True):
                continue
            try:
                if spec["kind"] == "interval":
                    self._apply_interval(bot, spec, now)
                else:
                    self._apply_daily(bot, spec, now)
            except Exception:  # noqa: BLE001 - one bad bot must not starve others
                continue

    def _apply_interval(self, bot, spec: dict, now: float) -> None:
        interval = float(spec["interval_seconds"])
        run_for = spec.get("run_seconds")
        state = bot.schedule_state
        last_start = state.get("last_start")

        if bot.state in BotState.TERMINAL and not bot.detached:
            if last_start is None or now - last_start >= interval:
                result = self._supervisor.start(bot.manifest.id)
                if result.get("ok"):
                    state["last_start"] = now
                    state["next_start_at"] = now + interval
            elif last_start is not None:
                state["next_start_at"] = last_start + interval
        elif (
            run_for is not None
            and last_start is not None
            and bot.state in (BotState.RUNNING, BotState.STARTING, BotState.BACKOFF)
            and now - last_start >= float(run_for)
        ):
            self._supervisor.stop(bot.manifest.id)
            state["next_start_at"] = last_start + interval

    def _apply_daily(self, bot, spec: dict, now: float) -> None:
        clock = spec["time"]
        duration = float(spec.get("duration_seconds", 0) or 0)
        bot_id = bot.manifest.id
        in_window = within_daily_window(clock, duration, now)
        previous = self._window_state.get(bot_id)

        if in_window and previous is not True:
            # Rising edge (or first observation inside a window): start.
            if bot.state in BotState.TERMINAL and not bot.detached:
                self._supervisor.start(bot.manifest.id)
        elif not in_window and previous is True:
            # Falling edge: stop only what the schedule started.
            if bot.state in (BotState.RUNNING, BotState.STARTING, BotState.BACKOFF):
                self._supervisor.stop(bot.manifest.id)

        self._window_state[bot_id] = in_window
        with self._supervisor.lock:
            if in_window and bot.state in BotState.TERMINAL:
                bot.schedule_state["next_start_at"] = None
            elif not in_window:
                bot.schedule_state["next_start_at"] = next_daily_start(clock, now)
