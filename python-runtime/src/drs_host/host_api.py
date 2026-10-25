"""Facade API consumed by the Android app (via Chaquopy) and the CLI.

Every function returns plain, JSON-serializable dicts/lists so the Kotlin
side can bridge them safely with ``json.dumps`` and never depends on
deep PyObject conversion.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

from . import __version__, scaffold
from .streams import ThreadAwareStream
from .supervisor import Supervisor

_supervisor: Supervisor | None = None
_data_dir: str | None = None
_available_packages: set | None = None
_hub: ThreadAwareStream | None = None
_lock = threading.Lock()
_STARTED_AT = time.time()


def configure(data_dir, *, limits=None) -> dict:
    """Initialize storage + supervisor and discover installed bots."""
    global _supervisor, _data_dir, _hub
    base = Path(data_dir)
    (base / "bots").mkdir(parents=True, exist_ok=True)
    _install_stream_hub()
    with _lock:
        _data_dir = str(base)
        _supervisor = Supervisor(base / "bots", limits=limits, stream_hub=_hub)
        discovered = _supervisor.discover_installed()
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


def check_requirements(bot_id) -> dict:
    """Compare a bot's declared requirements against the built-in set."""
    supervisor = _ensure()
    bot = supervisor.get(bot_id)
    if bot is None:
        return {"ok": False, "errors": [f"unknown bot id: {bot_id}"], "known": False, "missing": []}
    if _available_packages is None:
        return {"ok": True, "known": False, "missing": []}
    missing = [
        requirement
        for requirement in bot.manifest.requirements
        if _package_name(requirement) not in _available_packages
    ]
    return {"ok": True, "known": True, "missing": missing}


# --------------------------------------------------------------------- #
# Installation                                                          #
# --------------------------------------------------------------------- #

def import_zip(zip_path, overwrite: bool = False) -> dict:
    """Positional ``overwrite``: Chaquopy's callAttr passes positionally."""
    return _ensure().import_zip(zip_path, overwrite=overwrite)


def import_folder(folder, overwrite: bool = False) -> dict:
    return _ensure().import_folder(folder, overwrite=overwrite)


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


def restart_bot(bot_id) -> dict:
    return _ensure().restart(bot_id)


def start_autostart_bots() -> dict:
    return _ensure().start_autostart_bots()


def recent_logs(bot_id, limit: int = 500) -> list:
    return _ensure().recent_logs(bot_id, limit)


def host_stats() -> dict:
    """Fleet-wide dashboard statistics + host uptime."""
    stats = _ensure().host_stats()
    stats["uptime_seconds"] = round(time.time() - _STARTED_AT, 3)
    return stats


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
