"""Per-bot health checks with auto-recovery (v1.6).

Declared in ``bot.json``::

    "health": {"kind": "http", "url": "http://127.0.0.1:8080/health",
               "interval_seconds": 30, "failure_threshold": 3,
               "recover": "restart", "enabled": true}

    "health": {"kind": "command", "script": "health.py",
               "timeout_seconds": 5, "recover": "force_stop"}

Two probe kinds:

- ``http``: GET the URL; success when the response status equals
  ``expect_status`` (default 200). Timeouts and connection errors count
  as failures.
- ``command``: import the bot-relative ``script`` (a ``.py`` file inside
  the bot folder) and call ``check()`` — return ``True``/``False`` or
  ``(ok, detail)``. Runs in-process (works under Chaquopy on Android,
  where spawning second interpreters is not possible). A ``check()``
  that never returns is treated like any hung probe: the monitor gives
  up after ``timeout_seconds`` and records a timeout failure, while the
  abandoned probe thread dies with the host process.

Only RUNNING (non-detached) bots are probed. After
``failure_threshold`` consecutive failures the monitor applies
``recover``:

- ``none``: stay unhealthy, log only.
- ``restart``: graceful ``Supervisor.restart``.
- ``force_stop``: ``Supervisor.force_stop`` then start again.

After a recovery the counters reset and the bot must produce
``success_threshold`` consecutive successful probes to be healthy
again. Probes for one bot never stack: while a probe thread is
in-flight, later ticks skip that bot; a probe exceeding its deadline is
recorded once as a timeout failure.

Runtime state lives on the :class:`~drs_host.supervisor.SupervisedBot`
record (``health_state``) and is surfaced in every status payload. The
monitor is a single daemon thread ticking once per second, mirroring
the v1.2 scheduler.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .states import BotState

DEFAULT_TICK_SECONDS = 1.0
USER_AGENT = "DRS-Bot-Host-Health/1.6"

HEALTH_UNKNOWN = "unknown"
HEALTH_HEALTHY = "healthy"
HEALTH_UNHEALTHY = "unhealthy"
HEALTH_IDLE = "idle"
HEALTH_DISABLED = "disabled"

TERMINAL_STATES = BotState.TERMINAL


def fresh_health_state(interval_seconds: float = 30.0) -> dict:
    """Initial runtime health state for a freshly imported/started bot."""
    return {
        "status": HEALTH_UNKNOWN,
        "consecutive_failures": 0,
        "consecutive_successes": 0,
        "last_probe_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "last_error": None,
        "recoveries": 0,
        "next_probe_at": None,
        "interval_seconds": float(interval_seconds),
    }


def probe_http(url: str, *, expect_status: int = 200, timeout: float = 5.0) -> tuple:
    """One HTTP probe. Returns ``(ok, detail)``."""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": USER_AGENT, "Connection": "close"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        # An HTTP error status is a *probe result*, not a probe failure.
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - any transport error = unhealthy
        return False, f"{type(exc).__name__}: {exc}"
    if status == int(expect_status):
        return True, f"HTTP {status}"
    return False, f"HTTP {status} (expected {expect_status})"


def probe_command(bot_dir: Path, script: str) -> tuple:
    """One command probe: import ``script`` and call ``check()``.

    Returns ``(ok, detail)``. The module is imported under a throwaway
    name each time so edits take effect on the next probe; ``bot_dir``
    is temporarily on ``sys.path`` so the script can import siblings.
    """
    path = (bot_dir / script).resolve()
    bot_root = Path(bot_dir).resolve()
    if not str(path).startswith(str(bot_root)):
        return False, "script resolves outside the bot folder"
    if not path.is_file():
        return False, f"script not found: {script}"
    module_name = f"_drs_health_{int(time.time() * 1000) % 10_000_000_007}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return False, f"cannot import script: {script}"
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(bot_root))
    try:
        spec.loader.exec_module(module)
    except SystemExit as exc:
        return False, f"check() script called SystemExit({exc.code})"
    except BaseException as exc:  # noqa: BLE001 - user code may raise anything
        return False, f"script import raised: {type(exc).__name__}: {exc}"
    finally:
        for entry in (str(bot_root),):
            while entry in sys.path:
                sys.path.remove(entry)
    check = getattr(module, "check", None)
    if not callable(check):
        return False, "script has no callable check() function"
    try:
        outcome = check()
    except BaseException as exc:  # noqa: BLE001 - user code may raise anything
        return False, f"check() raised: {type(exc).__name__}: {exc}"
    if isinstance(outcome, tuple) and len(outcome) == 2:
        ok, detail = outcome
        if isinstance(ok, bool):
            return ok, str(detail or ("ok" if ok else "failed"))
        return False, "check() tuple must be (bool, detail)"
    if isinstance(outcome, bool):
        return outcome, "ok" if outcome else "check() returned False"
    return False, "check() must return bool or (bool, detail)"


class BotHealthMonitor:
    """Probes RUNNING bots on their configured intervals and recovers them."""

    def __init__(self, supervisor, *, tick_seconds: float = DEFAULT_TICK_SECONDS):
        self._supervisor = supervisor
        self._tick = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # bot_id -> {"thread": Thread, "deadline": float, "counted": bool,
        #            "result": (ok, detail) | None}
        self._inflight: dict = {}
        self._inflight_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="drs-health-monitor", daemon=True
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()

    def reset_bot(self, bot_id: str) -> None:
        """Forget any in-flight probe for ``bot_id`` (called on relaunch).

        A probe result that arrives for a stale run is discarded; the
        next tick probes the fresh run on its normal schedule.
        """
        with self._inflight_lock:
            self._inflight.pop(bot_id, None)

    def _loop(self) -> None:
        while not self._stop.wait(self._tick):
            try:
                self.tick_once(time.time())
            except Exception:  # noqa: BLE001 - the monitor must never die
                continue

    # ------------------------------------------------------------------ #
    # Probing                                                            #
    # ------------------------------------------------------------------ #

    def tick_once(self, now: float) -> None:
        """One monitoring pass over every installed bot."""
        supervisor = self._supervisor
        with supervisor.lock:
            bots = list(supervisor.bots.values())
        for bot in bots:
            try:
                self._apply(bot, now)
            except Exception:  # noqa: BLE001 - one bad bot must not starve others
                continue

    def _apply(self, bot, now: float) -> None:
        config = bot.manifest.health
        state = bot.health_state
        if not config or not config.get("enabled", True):
            state["status"] = HEALTH_DISABLED
            state["next_probe_at"] = None
            return
        running = bot.state in (BotState.RUNNING, BotState.STARTING) and not bot.detached
        if not running:
            state["status"] = HEALTH_IDLE
            state["next_probe_at"] = None
            self._drain_inflight(bot.manifest.id, now, record=False)
            return

        interval = float(config.get("interval_seconds", 30.0))
        state["interval_seconds"] = interval
        bot_id = bot.manifest.id

        # Settle any in-flight probe first.
        if not self._drain_inflight(bot_id, now, record=True):
            return  # a probe is still in flight — skip this tick

        next_at = state.get("next_probe_at")
        if next_at is None:
            state["next_probe_at"] = now + interval
            return
        if now < float(next_at):
            return
        self._launch_probe(bot, config, now)

    def _launch_probe(self, bot, config: dict, now: float) -> None:
        bot_id = bot.manifest.id
        timeout = float(config.get("timeout_seconds", 5.0))
        holder: dict = {"result": None}
        kind = config.get("kind")

        def worker():
            try:
                if kind == "http":
                    ok, detail = probe_http(
                        config["url"],
                        expect_status=int(config.get("expect_status", 200)),
                        timeout=timeout,
                    )
                else:
                    ok, detail = probe_command(bot.bot_dir, config["script"])
                holder["result"] = (ok, str(detail))
            except Exception as exc:  # noqa: BLE001 - probe must never crash
                holder["result"] = (False, f"{type(exc).__name__}: {exc}")

        thread = threading.Thread(
            target=worker, name=f"drs-health-{bot_id}", daemon=True
        )
        thread.start()
        with self._inflight_lock:
            self._inflight[bot_id] = {
                "thread": thread,
                # The deadline lives on the REAL clock: probe threads run in
                # real time even when tick_once() is driven by a synthetic
                # clock (tests). Interval pacing stays on the passed ``now``.
                "deadline": time.time() + timeout,
                "counted": False,
                "result": holder,
            }
        bot.health_state["last_probe_at"] = now
        bot.health_state["next_probe_at"] = now + float(
            config.get("interval_seconds", 30.0)
        )

    def _drain_inflight(self, bot_id: str, now: float, *, record: bool) -> bool:
        """Settle one bot's in-flight probe. Returns True when free to probe.

        With ``record=True`` a probe that missed its deadline is recorded
        once as a timeout failure (the monitor stops tracking the
        abandoned thread; it dies with the host process).
        """
        entry = self._inflight.get(bot_id)
        if entry is None:
            return True
        thread = entry["thread"]
        if thread.is_alive():
            if time.time() < float(entry["deadline"]) or entry["counted"] or not record:
                return False
            entry["counted"] = True
            result = entry["result"].get("result")
            if result is None:
                result = (False, "probe timed out")
            with self._inflight_lock:
                self._inflight.pop(bot_id, None)
            bot = self._supervisor.get(bot_id)
            if bot is not None:
                self._record(bot, ok=result[0], detail=result[1])
            return False
        result = entry["result"].get("result")
        with self._inflight_lock:
            self._inflight.pop(bot_id, None)
        if result is not None and not entry["counted"] and record:
            bot = self._supervisor.get(bot_id)
            if bot is not None:
                self._record(bot, ok=result[0], detail=result[1])
        return True

    def _record(self, bot, *, ok: bool, detail: str) -> None:
        """Account one probe outcome and maybe trigger recovery."""
        state = bot.health_state
        config = bot.manifest.health
        state["last_probe_at"] = time.time()
        if ok:
            state["consecutive_failures"] = 0
            state["consecutive_successes"] = int(
                state.get("consecutive_successes", 0)
            ) + 1
            state["last_success_at"] = state["last_probe_at"]
            state["last_error"] = None
            threshold = int((config or {}).get("success_threshold", 1))
            if state["consecutive_successes"] >= threshold:
                state["status"] = HEALTH_HEALTHY
            else:
                state["status"] = HEALTH_UNKNOWN
            return
        state["consecutive_successes"] = 0
        state["consecutive_failures"] = int(
            state.get("consecutive_failures", 0)
        ) + 1
        state["last_failure_at"] = state["last_probe_at"]
        state["last_error"] = detail
        state["status"] = HEALTH_UNHEALTHY
        threshold = int((config or {}).get("failure_threshold", 3))
        if state["consecutive_failures"] < threshold:
            bot.logger.warning(
                f"health probe failed ({state['consecutive_failures']}/{threshold}): {detail}"
            )
            return
        if (config or {}).get("recover", "restart") == "none":
            bot.logger.warning(
                f"health check failed {threshold} time(s) ({detail}) — "
                "recover is 'none': bot stays flagged unhealthy"
            )
            return
        self._recover(bot, detail)

    def _recover(self, bot, detail: str) -> None:
        """Apply the configured recovery action for a failed-threshold bot."""
        config = bot.manifest.health or {}
        action = config.get("recover", "restart")
        bot_id = bot.manifest.id
        state = bot.health_state
        if bot.state not in (BotState.RUNNING, BotState.STARTING) or bot.detached:
            return
        state["recoveries"] = int(state.get("recoveries", 0)) + 1
        state["consecutive_failures"] = 0
        state["consecutive_successes"] = 0
        state["status"] = HEALTH_UNKNOWN
        state["last_error"] = detail
        bot.logger.warning(
            f"health check failed {threshold_of(config)} times ({detail}) — "
            f"recovering via '{action}'"
        )
        if action == "restart":
            self._supervisor.restart(bot_id)
        elif action == "force_stop":
            stopped = self._supervisor.force_stop(bot_id)
            if stopped.get("ok"):
                started = self._supervisor.start(bot_id)
                if not started.get("ok"):
                    bot.logger.warning(
                        "health recovery start failed: "
                        + "; ".join(started.get("errors", []))
                    )

    # ------------------------------------------------------------------ #
    # Manual probe (API / CLI / UI button)                               #
    # ------------------------------------------------------------------ #

    def probe_once(self, bot_id: str) -> dict:
        """Run a single probe now and return its outcome.

        The result is recorded in the bot's health state but never
        triggers a recovery — manual probes are diagnostics.
        """
        bot = self._supervisor.get(bot_id)
        if bot is None:
            return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
        config = bot.manifest.health
        if not config:
            return {
                "ok": False,
                "errors": [f"bot {bot_id} has no health config in its manifest"],
            }
        kind = config.get("kind")
        timeout = float(config.get("timeout_seconds", 5.0))
        started = time.time()
        if kind == "http":
            ok, detail = probe_http(
                config["url"],
                expect_status=int(config.get("expect_status", 200)),
                timeout=timeout,
            )
        else:
            ok, detail = probe_command(bot.bot_dir, config["script"])
        elapsed_ms = round((time.time() - started) * 1000.0, 1)
        state = bot.health_state
        state["last_probe_at"] = time.time()
        if ok:
            state["consecutive_failures"] = 0
            state["consecutive_successes"] = int(
                state.get("consecutive_successes", 0)
            ) + 1
            state["last_success_at"] = state["last_probe_at"]
            state["last_error"] = None
            state["status"] = HEALTH_HEALTHY
        else:
            state["consecutive_successes"] = 0
            state["consecutive_failures"] = int(
                state.get("consecutive_failures", 0)
            ) + 1
            state["last_failure_at"] = state["last_probe_at"]
            state["last_error"] = detail
            state["status"] = HEALTH_UNHEALTHY
        return {
            "ok": True,
            "id": bot_id,
            "healthy": ok,
            "detail": detail,
            "elapsed_ms": elapsed_ms,
        }


def threshold_of(config: dict) -> int:
    """Configured failure threshold (helper for log wording)."""
    try:
        return int(config.get("failure_threshold", 3))
    except (TypeError, ValueError, AttributeError):
        return 3


__all__ = [
    "BotHealthMonitor",
    "fresh_health_state",
    "probe_http",
    "probe_command",
    "HEALTH_UNKNOWN",
    "HEALTH_HEALTHY",
    "HEALTH_UNHEALTHY",
    "HEALTH_IDLE",
    "HEALTH_DISABLED",
]
