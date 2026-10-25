"""Thread-per-bot supervision with restart policies and exponential backoff.

State machine per bot::

    STOPPED ──start──> STARTING ──> RUNNING ──exit──> COMPLETED / FAILED
                         │              │
                         └────stop────> STOPPING ──> STOPPED
    FAILED ──policy allows──> BACKOFF ──timer──> STARTING (restarts += 1)

Termination is cooperative (threads cannot be force-killed in Python).
A bot that ignores ``stop_event`` stays in ``STOPPING`` with an explicit
warning in its status — an honest, documented v1.0 limitation.
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
from .logging import BotLogger, JsonlFileSink, RingBuffer
from .manifest import BotManifest, validate_manifest, python_version_tuple
from .runner import BotRunner
from .sdk import BotContext

CONFIG_MAX_BYTES = 64 * 1024


class BotState:
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    BACKOFF = "BACKOFF"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    TERMINAL = {STOPPED, COMPLETED, FAILED}


class SupervisedBot:
    """Mutable runtime record for one installed bot."""

    def __init__(self, manifest: BotManifest, bot_dir: Path):
        self.manifest = manifest
        self.bot_dir = Path(bot_dir)
        self.state = BotState.STOPPED
        self.thread: BotRunner | None = None
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

    def __init__(self, bots_root, *, limits=None, sleeper=time.sleep, stream_hub=None):
        self.bots_root = Path(bots_root)
        self._limits = limits
        self._sleeper = sleeper
        self._lock = threading.RLock()
        self._bots: dict[str, SupervisedBot] = {}
        self.stream_hub = stream_hub

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
            "restarts": sum(int(record.get("restarts", 0) or 0) for record in bots),
            "runs": sum(int(record.get("run_count", 0) or 0) for record in bots),
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
            bot.restarts = 0
            self._launch(bot)
        return {"ok": True, "id": bot_id, "state": bot.state}

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
        runner = BotRunner(
            bot.ctx,
            bot.bot_dir,
            bot.manifest.entrypoint,
            self.stream_hub,
            on_exit=lambda state, error, b=bot: self._on_exit(b, state, error),
        )
        bot.thread = runner
        runner.start()
        if bot.state == BotState.STARTING and runner.is_alive():
            bot.state = BotState.RUNNING

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
                        "it is unresponsive and will be reported as STOPPING"
                    ),
                }
        with self._lock:
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
        return {"ok": True, "id": bot_id}

    def shutdown_all(self) -> dict:
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

    def _on_exit(self, bot: SupervisedBot, state: str, error) -> None:
        policy = bot.manifest.restart
        with self._lock:
            bot.stopped_at = time.time()
            bot.last_error = error
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
