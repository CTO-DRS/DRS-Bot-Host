"""Thread-per-bot supervision with restart policies and exponential backoff.

State machine per bot::

    STOPPED ──start──> STARTING ──> RUNNING ──exit──> COMPLETED / FAILED
                         │              │
                         └────stop────> STOPPING ──> STOPPED
    FAILED ──policy allows──> BACKOFF ──timer──> STARTING (restarts += 1)

Termination is cooperative (threads cannot be force-killed in Python).
A bot that ignores ``stop_event`` stays in ``STOPPING``; the explicit
``force_stop()`` escalation (v1.2) detaches such a thread and marks the bot
``FORCE_STOPPED`` — the zombie thread keeps running until the host process
exits (on Android the OS can still kill the whole service), but it can no
longer influence the bot's state. Exit callbacks are matched against the
currently tracked runner, so detached runs never corrupt live state.
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path

from . import importer
from . import installer
from . import isolation as isolation_mod
from .logging import BotLogger, JsonlFileSink, RingBuffer
from .manifest import BotManifest, validate_manifest, python_version_tuple
from .runner import BotRunner
from .scheduler import BotScheduler
from .sdk import BotContext
from .states import BotState  # re-exported for backwards compatibility

__all__ = ["BotState", "Supervisor", "SupervisedBot", "REQUIREMENTS_POLICIES"]

CONFIG_MAX_BYTES = 64 * 1024
REQUIREMENTS_POLICIES = ("off", "warn", "enforce")


class SupervisedBot:
    """Mutable runtime record for one installed bot."""

    def __init__(self, manifest: BotManifest, bot_dir: Path):
        self.manifest = manifest
        self.bot_dir = Path(bot_dir)
        self.state = BotState.STOPPED
        self.thread: BotRunner | None = None
        self.isolation_effective = "thread"
        self.stop_event = threading.Event()
        self.ctx = BotContext(
            manifest.id, manifest.name, manifest.config, self.stop_event, None
        )
        self.restarts = 0
        self.run_count = 0
        self.last_error = None
        self.started_at = None
        self.stopped_at = None
        self.stop_requested = False
        self.detached = False
        self.cpu_seconds = 0.0
        self.last_cpu_seconds = None
        self.schedule_state = {"last_start": None, "next_start_at": None}
        self.ring = RingBuffer()
        self.file_sink = JsonlFileSink(self.bot_dir / "logs" / "runtime.jsonl")
        self.logger = BotLogger(manifest.id, [self.ring, self.file_sink])
        self.ctx = BotContext(
            manifest.id, manifest.name, manifest.config, self.stop_event, self.logger
        )

    def status(self) -> dict:
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "entrypoint": self.manifest.entrypoint,
            "description": self.manifest.description,
            "author": self.manifest.author,
            "requirements": self.manifest.requirements,
            "config": self.manifest.config,
            "auto_start": self.manifest.auto_start,
            "restart_policy": self.manifest.restart,
            "state": self.state,
            "restarts": self.restarts,
            "run_count": self.run_count,
            "uptime_seconds": self._uptime_seconds(),
            "cpu_seconds": round(self.cpu_seconds, 3),
            "last_cpu_seconds": (
                round(self.last_cpu_seconds, 3)
                if self.last_cpu_seconds is not None
                else None
            ),
            "detached": self.detached,
            "isolation": self.manifest.isolation,
            "isolation_effective": self.isolation_effective,
            "schedule": self.manifest.schedule,
            "schedule_state": {
                "next_start_at": self.schedule_state.get("next_start_at"),
            },
            "last_error": self.last_error,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "progress": self.ctx.snapshot_progress(),
        }

    def _uptime_seconds(self):
        """Live uptime while active; last run duration once terminal/backoff."""
        if self.started_at is None:
            return None
        if self.state in (BotState.STARTING, BotState.RUNNING, BotState.STOPPING):
            return max(0.0, round(time.time() - self.started_at, 3))
        if self.stopped_at is not None:
            return max(0.0, round(self.stopped_at - self.started_at, 3))
        return None


class Supervisor:
    """Owns installed bots, their threads, logs and restart behaviour."""

    def __init__(self, bots_root, *, limits=None, sleeper=time.sleep, stream_hub=None,
                 requirements_checker=None):
        self.bots_root = Path(bots_root)
        self._limits = limits
        self._sleeper = sleeper
        self._lock = threading.RLock()
        self._bots: dict[str, SupervisedBot] = {}
        self.stream_hub = stream_hub
        self._requirements_checker = requirements_checker
        self.requirements_policy = "warn"
        self._scheduler = BotScheduler(self)

    # -- introspection used by the scheduler ---------------------------

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def bots(self) -> dict:
        return self._bots

    def limits_overlay(self) -> dict:
        """Effective importer limits (defaults merged with custom overrides)."""
        overlay = dict(importer.DEFAULT_LIMITS)
        if self._limits:
            overlay.update(self._limits)
        return overlay

    # ------------------------------------------------------------------ #
    # Scheduler                                                          #
    # ------------------------------------------------------------------ #

    def start_scheduler(self) -> dict:
        """Start the cron-like scheduler thread (interval/daily windows)."""
        self._scheduler.start()
        return {"ok": True}

    def scheduler_running(self) -> bool:
        thread = self._scheduler._thread
        return thread is not None and thread.is_alive()

    def set_schedule_enabled(self, bot_id, enabled) -> dict:
        """Enable/disable a bot's schedule (persists to bot.json)."""
        if not isinstance(enabled, bool):
            return {"ok": False, "errors": ["enabled must be true or false"]}
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
            if bot.manifest.schedule is None:
                return {
                    "ok": False,
                    "errors": [f"bot {bot_id} has no schedule in its manifest"],
                }
            manifest_path = bot.bot_dir / "bot.json"
            try:
                document = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                return {"ok": False, "errors": [f"cannot read bot.json: {exc}"]}
            document.setdefault("schedule", {})["enabled"] = enabled
            manifest, errors = validate_manifest(document)
            if manifest is None:
                return {"ok": False, "errors": errors}
            manifest_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            bot.manifest = manifest
        return {"ok": True, "id": bot_id, "schedule": manifest.schedule}

    # ------------------------------------------------------------------ #
    # Installation                                                       #
    # ------------------------------------------------------------------ #

    def import_zip(self, zip_path, *, overwrite: bool = False) -> dict:
        manifest, errors = importer.peek_zip(zip_path)
        if manifest is None:
            return {"ok": False, "errors": errors}
        blocked = self._overwrite_guard(manifest, overwrite)
        if blocked:
            return blocked
        result = importer.import_zip(
            zip_path, self.bots_root, overwrite=overwrite, limits=self._limits
        )
        return self._after_import(result)

    def import_folder(self, folder, *, overwrite: bool = False) -> dict:
        manifest, errors = importer.peek_folder(folder)
        if manifest is None:
            return {"ok": False, "errors": errors}
        blocked = self._overwrite_guard(manifest, overwrite)
        if blocked:
            return blocked
        result = importer.import_folder(
            folder, self.bots_root, overwrite=overwrite, limits=self._limits
        )
        return self._after_import(result)

    def _overwrite_guard(self, manifest: BotManifest, overwrite: bool):
        with self._lock:
            existing = self._bots.get(manifest.id)
            if (
                existing is not None
                and overwrite
                and existing.state not in BotState.TERMINAL
            ):
                return {
                    "ok": False,
                    "errors": [
                        f"bot {manifest.id} is {existing.state}; stop it before overwriting"
                    ],
                }
        return None

    def _after_import(self, result: dict) -> dict:
        if result.get("ok"):
            with self._lock:
                self._bots[result["bot_id"]] = SupervisedBot(
                    BotManifest(**result["manifest"]),
                    self.bots_root / result["bot_id"],
                )
        return result

    def discover_installed(self) -> int:
        """Re-register bots found on disk (used after an app restart)."""
        count = 0
        if not self.bots_root.is_dir():
            return count
        for directory in sorted(self.bots_root.iterdir()):
            manifest_path = directory / "bot.json"
            if not (directory.is_dir() and manifest_path.is_file()):
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            manifest, _errors = validate_manifest(data)
            if manifest is None:
                continue
            with self._lock:
                if manifest.id not in self._bots:
                    self._bots[manifest.id] = SupervisedBot(manifest, directory)
                    count += 1
        return count

    # ------------------------------------------------------------------ #
    # Queries                                                            #
    # ------------------------------------------------------------------ #

    def get(self, bot_id) -> SupervisedBot | None:
        with self._lock:
            return self._bots.get(bot_id)

    def list_bots(self) -> list:
        with self._lock:
            return [bot.status() for bot in self._bots.values()]

    def status(self, bot_id) -> dict:
        with self._lock:
            bot = self._bots.get(bot_id)
        if bot is None:
            return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
        return {"ok": True, **bot.status()}

    def recent_logs(self, bot_id, limit: int = 500) -> list:
        with self._lock:
            bot = self._bots.get(bot_id)
        if bot is None:
            return []
        return bot.ring.recent(limit)

    def host_stats(self) -> dict:
        """Aggregate fleet statistics for the dashboard."""
        with self._lock:
            bots = [bot.status() for bot in self._bots.values()]
        by_state: dict = {}
        for record in bots:
            state = record["state"]
            by_state[state] = by_state.get(state, 0) + 1
        scheduled = sum(
            1
            for bot in self._bots.values()
            if bot.manifest.schedule and bot.manifest.schedule.get("enabled", True)
        )
        return {
            "ok": True,
            "total": len(bots),
            "by_state": by_state,
            "running": (
                by_state.get(BotState.RUNNING, 0)
                + by_state.get(BotState.STARTING, 0)
                + by_state.get(BotState.BACKOFF, 0)
            ),
            "failed": by_state.get(BotState.FAILED, 0),
            "completed": by_state.get(BotState.COMPLETED, 0),
            "scheduled": scheduled,
            "restarts": sum(int(record.get("restarts", 0) or 0) for record in bots),
            "runs": sum(int(record.get("run_count", 0) or 0) for record in bots),
            "cpu_seconds": round(
                sum(float(record.get("cpu_seconds", 0.0) or 0.0) for record in bots), 3
            ),
        }

    def export_logs(self, bot_id) -> dict:
        """Bundle a bot's JSONL logs into ``<data_dir>/exports/<id>-<stamp>.zip``."""
        with self._lock:
            bot = self._bots.get(bot_id)
        if bot is None:
            return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
        exports_dir = self.bots_root.parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        path = exports_dir / f"{bot_id}-logs-{stamp}.zip"
        files = 0
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            logs_dir = bot.bot_dir / "logs"
            if logs_dir.is_dir():
                for item in sorted(logs_dir.iterdir()):
                    if item.is_file():
                        archive.write(item, arcname=item.name)
                        files += 1
        return {
            "ok": True,
            "id": bot_id,
            "path": str(path),
            "files": files,
            "bytes": path.stat().st_size,
        }

    def set_config(self, bot_id, config) -> dict:
        """Merge/replace a bot's ``config`` object in bot.json.

        Accepts a dict or a JSON string (the Android bridge passes strings).
        The new config is validated through the full manifest validator and
        takes effect on the bot's next start.
        """
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError as exc:
                return {"ok": False, "errors": [f"config is not valid JSON: {exc}"]}
        if not isinstance(config, dict):
            return {"ok": False, "errors": ["config must be a JSON object"]}
        try:
            encoded = json.dumps(config, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "errors": [f"config is not JSON-serializable: {exc}"]}
        if len(encoded.encode("utf-8")) > CONFIG_MAX_BYTES:
            return {
                "ok": False,
                "errors": [f"config too large (limit {CONFIG_MAX_BYTES} bytes)"],
            }
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
            manifest_path = bot.bot_dir / "bot.json"
            try:
                document = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                return {"ok": False, "errors": [f"cannot read bot.json: {exc}"]}
            document["config"] = config
            manifest, errors = validate_manifest(document)
            if manifest is None:
                return {"ok": False, "errors": errors}
            manifest_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            bot.manifest = manifest
        return {
            "ok": True,
            "id": bot_id,
            "config": config,
            "note": "applies on next start",
        }

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def start(self, bot_id) -> dict:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
            if bot.state in (BotState.RUNNING, BotState.STARTING):
                return {"ok": False, "errors": [f"bot {bot_id} is already running"]}
            if bot.state == BotState.STOPPING:
                return {"ok": False, "errors": [f"bot {bot_id} is still stopping"]}
            if bot.manifest.min_python:
                required = python_version_tuple(bot.manifest.min_python)
                if sys.version_info[:2] < required:
                    return {
                        "ok": False,
                        "errors": [
                            f"bot {bot_id} requires Python {bot.manifest.min_python}, "
                            f"host has {sys.version_info[0]}.{sys.version_info[1]}"
                        ],
                    }
            missing = None
            if self._requirements_checker is not None and self.requirements_policy != "off":
                missing = self._requirements_checker(bot.manifest)
                if missing and self.requirements_policy == "enforce":
                    return {
                        "ok": False,
                        "errors": [
                            f"bot {bot_id} is missing required packages: "
                            f"{', '.join(missing)} — install them or relax the "
                            f"requirements policy"
                        ],
                    }
                if missing:
                    bot.logger.warning(
                        "missing requirements: " + ", ".join(missing)
                    )
            detached = bot.detached
            bot.restarts = 0
            self._launch(bot)
        response = {"ok": True, "id": bot_id, "state": bot.state}
        if detached:
            response["warning"] = (
                "a previously force-stopped thread may still be running"
            )
        return response

    def start_autostart_bots(self) -> dict:
        started = []
        with self._lock:
            candidates = [
                bot.manifest.id
                for bot in self._bots.values()
                if bot.manifest.auto_start and bot.state in BotState.TERMINAL
            ]
        for bot_id in candidates:
            if self.start(bot_id).get("ok"):
                started.append(bot_id)
        return {"ok": True, "started": started}

    def _launch(self, bot: SupervisedBot) -> None:
        """Spawn a fresh run of ``bot``; caller must hold the lock."""
        bot.stop_requested = False
        bot.detached = False
        bot.stop_event = threading.Event()
        bot.ctx = BotContext(
            bot.manifest.id,
            bot.manifest.name,
            bot.manifest.config,
            bot.stop_event,
            bot.logger,
        )
        bot.state = BotState.STARTING
        bot.started_at = time.time()
        bot.stopped_at = None
        bot.last_error = None
        bot.run_count += 1
        site_dir = installer.site_dir_for_run(bot.bot_dir, self.bots_root.parent, bot.manifest.id)
        runner = self._build_runner(bot, site_dir)
        bot.thread = runner
        runner.start()
        if bot.state == BotState.STARTING and runner.is_alive():
            bot.state = BotState.RUNNING

    def _build_runner(self, bot: SupervisedBot, site_dir):
        """Pick the runner class: real process isolation when available."""
        on_exit = lambda thread, state, error, cpu_used=None, b=bot: self._on_exit(  # noqa: E731
            b, thread, state, error, cpu_used=cpu_used
        )
        if bot.manifest.isolation == "process":
            if isolation_mod.process_runtime_available():
                bot.isolation_effective = "process"
                return isolation_mod.ProcessRunner(
                    bot.ctx,
                    bot.bot_dir,
                    bot.manifest.entrypoint,
                    on_exit,
                    env=isolation_mod.build_child_env(site_dir=site_dir),
                )
            bot.isolation_effective = "thread"
            bot.logger.warning(
                "isolation=process requested but no standalone python runtime is "
                "available here — falling back to thread mode (force-stop stays "
                "cooperative)"
            )
        else:
            bot.isolation_effective = "thread"
        return BotRunner(
            bot.ctx,
            bot.bot_dir,
            bot.manifest.entrypoint,
            self.stream_hub,
            on_exit=on_exit,
            site_dir=site_dir,
        )

    def stop(self, bot_id, timeout: float = 8.0) -> dict:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
            if bot.state in BotState.TERMINAL:
                bot.stop_requested = False
                return {"ok": True, "id": bot_id, "state": bot.state}
            bot.stop_requested = True
            bot.stop_event.set()
            bot.state = BotState.STOPPING
            thread = bot.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
            if thread.is_alive():
                return {
                    "ok": True,
                    "id": bot_id,
                    "state": BotState.STOPPING,
                    "warning": (
                        "bot thread did not exit within the grace period; "
                        "use force_stop to detach it"
                    ),
                }
        with self._lock:
            if bot.state == BotState.STOPPING:
                bot.state = BotState.STOPPED
                bot.stopped_at = time.time()
                bot.restarts = 0
        return {"ok": True, "id": bot_id, "state": bot.state}

    def force_stop(self, bot_id, grace: float = 2.0) -> dict:
        """Escalated stop for unresponsive bots (v1.2; real kill in v1.3).

        Thread mode: Python threads cannot be killed in-process, so a thread
        that ignores the stop event is *detached*: the bot is marked
        ``FORCE_STOPPED`` and the zombie thread is no longer tracked.

        Process mode (``isolation: "process"`` + a desktop-class runtime):
        the child *process* is ``SIGKILL``ed — no zombie survives.
        """
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
            if bot.state in BotState.TERMINAL:
                return {"ok": True, "id": bot_id, "state": bot.state}
            bot.stop_requested = True
            bot.stop_event.set()
            bot.state = BotState.STOPPING
            thread = bot.thread
            runner_is_process = isinstance(thread, isolation_mod.ProcessRunner)
        if runner_is_process and thread is not None:
            thread.kill()  # a real kill — the child cannot ignore SIGKILL
            thread.join(grace)
            with self._lock:
                if bot.state == BotState.STOPPING:
                    bot.state = BotState.STOPPED
                    bot.stopped_at = time.time()
                    bot.restarts = 0
                    bot.logger.warning("force-stopped: child process was SIGKILLed")
                    return {
                        "ok": True,
                        "id": bot_id,
                        "state": BotState.STOPPED,
                        "note": "process killed (isolation=process)",
                    }
                return {"ok": True, "id": bot_id, "state": bot.state}
        if thread is not None and thread.is_alive():
            thread.join(grace)
        with self._lock:
            if thread is not None and thread.is_alive():
                bot.detached = True
                bot.thread = None
                bot.state = BotState.FORCE_STOPPED
                bot.stopped_at = time.time()
                bot.restarts = 0
                bot.logger.warning(
                    "force-stopped: the bot thread ignored the stop request and "
                    "was detached; it may keep running until the host process exits"
                )
                return {
                    "ok": True,
                    "id": bot_id,
                    "state": BotState.FORCE_STOPPED,
                    "warning": (
                        "thread unresponsive — detached from supervision; it may "
                        "keep running until the host process exits"
                    ),
                }
            if bot.state == BotState.STOPPING:
                bot.state = BotState.STOPPED
                bot.stopped_at = time.time()
                bot.restarts = 0
        return {"ok": True, "id": bot_id, "state": bot.state}

    def restart(self, bot_id) -> dict:
        if not self.get(bot_id):
            return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
        stopped = self.stop(bot_id)
        if not stopped.get("ok"):
            return stopped
        return self.start(bot_id)

    def remove(self, bot_id) -> dict:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return {"ok": False, "errors": [f"unknown bot id: {bot_id}"]}
            if bot.state not in BotState.TERMINAL:
                return {
                    "ok": False,
                    "errors": [f"bot {bot_id} is {bot.state}; stop it before removing"],
                }
            del self._bots[bot_id]
        shutil.rmtree(self.bots_root / bot_id, ignore_errors=True)
        installer.uninstall_site_dir(self.bots_root.parent, bot_id)
        return {"ok": True, "id": bot_id}

    def shutdown_all(self) -> dict:
        self._scheduler.shutdown()
        with self._lock:
            running = [
                bot.manifest.id
                for bot in self._bots.values()
                if bot.state not in BotState.TERMINAL
            ]
        for bot_id in running:
            self.stop(bot_id)
        return {"ok": True, "stopped": running}

    # ------------------------------------------------------------------ #
    # Restart machinery                                                  #
    # ------------------------------------------------------------------ #

    def _on_exit(
        self,
        bot: SupervisedBot,
        runner: BotRunner,
        state: str,
        error,
        cpu_used=None,
    ) -> None:
        if runner is not bot.thread:
            return  # a detached/zombie run exited — never touch live state
        policy = bot.manifest.restart
        with self._lock:
            bot.stopped_at = time.time()
            bot.last_error = error
            if cpu_used is not None:
                bot.cpu_seconds += float(cpu_used)
                bot.last_cpu_seconds = float(cpu_used)
            if bot.stop_requested:
                bot.state = BotState.STOPPED
                bot.restarts = 0
                return
            wants_restart = (
                state == "FAILED" and policy["policy"] in ("on_failure", "always")
            ) or (state == "COMPLETED" and policy["policy"] == "always")
            if wants_restart and bot.restarts < policy["max_restarts"]:
                delay = min(
                    policy["backoff_seconds"] * (policy["backoff_multiplier"] ** bot.restarts),
                    policy["max_backoff_seconds"],
                )
                bot.state = BotState.BACKOFF
                self._schedule_restart(bot, delay)
                return
            bot.state = BotState.COMPLETED if state == "COMPLETED" else BotState.FAILED

    def _schedule_restart(self, bot: SupervisedBot, delay: float) -> None:
        def worker():
            self._sleeper(delay)
            with self._lock:
                if bot.state != BotState.BACKOFF or bot.stop_requested:
                    return
                bot.restarts += 1
                self._launch(bot)

        threading.Thread(
            target=worker,
            name=f"drs-restart-{bot.manifest.id}",
            daemon=True,
        ).start()
