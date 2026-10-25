"""Facade API consumed by the Android app (via Chaquopy) and the CLI.

Every function returns plain, JSON-serializable dicts/lists so the Kotlin
side can bridge them safely with ``json.dumps`` and never depends on
deep PyObject conversion.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import threading
import time
from pathlib import Path

from . import __version__, scaffold
from .streams import ThreadAwareStream
from .supervisor import REQUIREMENTS_POLICIES, Supervisor

_supervisor: Supervisor | None = None
_data_dir: str | None = None
_available_packages: set | None = None
_hub: ThreadAwareStream | None = None
_lock = threading.Lock()
_STARTED_AT = time.time()


def configure(data_dir, *, limits=None) -> dict:
    """Initialize storage + supervisor + scheduler and discover installed bots."""
    global _supervisor, _data_dir, _hub
    base = Path(data_dir)
    (base / "bots").mkdir(parents=True, exist_ok=True)
    _install_stream_hub()
    with _lock:
        if _supervisor is not None:
            _supervisor.shutdown_all()  # stops the previous scheduler thread
        _data_dir = str(base)
        _supervisor = Supervisor(
            base / "bots",
            limits=limits,
            stream_hub=_hub,
            requirements_checker=_missing_requirements,
        )
        discovered = _supervisor.discover_installed()
        _supervisor.start_scheduler()
    return {"ok": True, "data_dir": _data_dir, "discovered": discovered}


def _ensure() -> Supervisor:
    if _supervisor is None:
        raise RuntimeError("drs_host.host_api.configure(data_dir) must be called first")
    return _supervisor


def _install_stream_hub() -> None:
    global _hub
    if not isinstance(sys.stdout, ThreadAwareStream):
        sys.stdout = ThreadAwareStream(sys.stdout)
    _hub = sys.stdout  # type: ignore[assignment]


# --------------------------------------------------------------------- #
# Runtime metadata                                                      #
# --------------------------------------------------------------------- #

def runtime_info() -> dict:
    supervisor = _ensure()
    return {
        "ok": True,
        "drs_host": __version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "data_dir": _data_dir,
        "bots": len(supervisor.list_bots()),
        "uptime_seconds": round(time.time() - _STARTED_AT, 3),
    }


def set_available_packages(names) -> dict:
    """Declare which PyPI packages were baked into the APK at build time."""
    global _available_packages
    _available_packages = {str(name) for name in names}
    return {"ok": True, "count": len(_available_packages)}


def available_packages() -> list:
    return sorted(_available_packages or [])


def _package_name(requirement: str) -> str:
    return re.split(r"[<>=!~;\[\s]", requirement.strip(), maxsplit=1)[0].lower()


def _importable_module(name: str) -> bool:
    """Best-effort importability probe for a PyPI-style package name."""
    if not name:
        return False
    lowered = name.lower()
    candidates = [name, lowered, name.replace("-", "_"), lowered.replace("-", "_")]
    for candidate in dict.fromkeys(candidates):
        try:
            if importlib.util.find_spec(candidate) is not None:
                return True
        except (ImportError, ValueError, AttributeError):
            continue
    return False


def _missing_requirements(manifest) -> list:
    """Requirements that are neither baked in nor importable right now."""
    missing = []
    for requirement in manifest.requirements:
        name = _package_name(requirement)
        baked = _available_packages is not None and name in _available_packages
        if not baked and not _importable_module(name):
            missing.append(requirement)
    return missing


def check_requirements(bot_id) -> dict:
    """Report which of a bot's declared requirements look unavailable.

    Two sources are consulted: the build-time package set declared via
    ``set_available_packages`` and a best-effort ``find_spec`` probe of the
    live interpreter (handles common name/module mismatches like
    ``Pillow`` -> ``PIL`` only when names coincide; genuinely different
    module names are reported as best-effort results).
    """
    supervisor = _ensure()
    bot = supervisor.get(bot_id)
    if bot is None:
        return {"ok": False, "errors": [f"unknown bot id: {bot_id}"], "known": False, "missing": []}
    return {
        "ok": True,
        "known": _available_packages is not None,
        "missing": _missing_requirements(bot.manifest),
    }


def requirements_policy() -> str:
    """Current start-time requirements policy: off | warn | enforce."""
    return _ensure().requirements_policy


def set_requirements_policy(policy) -> dict:
    """Control what start() does with missing requirements.

    ``off`` never checks; ``warn`` starts the bot but logs a warning;
    ``enforce`` refuses to start with a clear error.
    """
    supervisor = _ensure()
    if policy not in REQUIREMENTS_POLICIES:
        return {
            "ok": False,
            "errors": [
                "policy must be one of " + ", ".join(REQUIREMENTS_POLICIES)
            ],
        }
    supervisor.requirements_policy = policy
    return {"ok": True, "policy": policy}


# --------------------------------------------------------------------- #
# Installation                                                          #
# --------------------------------------------------------------------- #

def import_zip(zip_path, overwrite: bool = False) -> dict:
    """Positional ``overwrite``: Chaquopy's callAttr passes positionally."""
    return _ensure().import_zip(zip_path, overwrite=overwrite)


def import_folder(folder, overwrite: bool = False) -> dict:
    return _ensure().import_folder(folder, overwrite=overwrite)


def import_bot_url(url, overwrite: bool = False) -> dict:
    """Download a bot zip over HTTP(S) and import it (GitHub links supported)."""
    from . import downloader

    return downloader.import_url(url, _ensure(), overwrite=overwrite)


def remove_bot(bot_id) -> dict:
    return _ensure().remove(bot_id)


# --------------------------------------------------------------------- #
# Lifecycle + logs                                                      #
# --------------------------------------------------------------------- #

def list_bots() -> list:
    return _ensure().list_bots()


def bot_status(bot_id) -> dict:
    return _ensure().status(bot_id)


def start_bot(bot_id) -> dict:
    return _ensure().start(bot_id)


def stop_bot(bot_id) -> dict:
    return _ensure().stop(bot_id)


def force_stop_bot(bot_id, grace: float = 2.0) -> dict:
    """Escalated stop: detach an unresponsive bot thread (FORCE_STOPPED)."""
    return _ensure().force_stop(bot_id, grace)


def restart_bot(bot_id) -> dict:
    return _ensure().restart(bot_id)


def set_schedule_enabled(bot_id, enabled) -> dict:
    """Enable/disable a bot's cron-like schedule (persists to bot.json)."""
    return _ensure().set_schedule_enabled(bot_id, enabled)


def start_autostart_bots() -> dict:
    return _ensure().start_autostart_bots()


def recent_logs(bot_id, limit: int = 500) -> list:
    return _ensure().recent_logs(bot_id, limit)


def host_stats() -> dict:
    """Fleet-wide dashboard statistics + host uptime + process footprint."""
    stats = _ensure().host_stats()
    stats["uptime_seconds"] = round(time.time() - _STARTED_AT, 3)
    stats["process_rss_bytes"] = process_rss_bytes()
    return stats


def process_rss_bytes() -> int:
    """Resident memory of the host process (0 when unavailable)."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/status", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:  # noqa: BLE001 - telemetry must never raise
        return 0


def export_logs(bot_id) -> dict:
    """Zip a bot's JSONL logs into ``<data_dir>/exports/`` and return its path."""
    return _ensure().export_logs(bot_id)


def set_bot_config(bot_id, config) -> dict:
    """Update a bot's ``config`` (dict or JSON string); applies on next start.

    The Android bridge passes a JSON string positionally via callAttr.
    """
    return _ensure().set_config(bot_id, config)


def scaffold_bot(name, dest) -> dict:
    """Generate a ready-to-import sample bot folder."""
    return scaffold.scaffold_bot(str(name), dest)


def shutdown_all() -> dict:
    if _supervisor is None:
        return {"ok": True, "stopped": []}
    return _supervisor.shutdown_all()
