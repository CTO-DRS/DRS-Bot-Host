"""Process-level bot isolation with a *real* kill (v1.3).

Thread mode (the default) cannot hard-kill a stuck bot. Process mode runs
each bot as a separate CPython subprocess spawned from the very interpreter
that hosts drs_host:

- desktop / CI: ``sys.executable`` spawns a real child process, so
  ``force_stop`` escalates to ``SIGKILL`` — the bot *always* dies;
- Android / Chaquopy: the embedded runtime has no standalone python
  binary, the probe reports ``available: false`` and the supervisor falls
  back to thread mode with an honest warning (documented, not hidden).

Protocol between host and child:

- child command: ``<python> -m drs_host.child_runner <bot_dir> <entrypoint>``
  (``PYTHONPATH`` is extended with the drs_host package parent + the bot's
  pip site directory);
- child stdout lines → parent logs them into the bot's ring buffer + JSONL
  sink via the regular logger;
- cooperative stop: parent sends ``SIGTERM``; the child's handler sets the
  in-child stop event so ``ctx.sleep_or_stop`` wakes up and the bot exits
  cleanly;
- force stop: parent sends ``SIGKILL`` (``Popen.kill()``) — the child dies
  immediately;
- CPU accounting: ``getrusage(RUSAGE_CHILDREN)`` deltas inside the watcher
  thread give the child's utime+stime on Linux.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import traceback
from pathlib import Path

_PROBE_CACHE: dict = {"available": None}


def process_runtime_available(timeout: float = 15.0) -> bool:
    """True when we can spawn a real CPython child (desktop/CI), else False.

    The probe runs ``<sys.executable> -c 'print(3)'`` once and caches the
    verdict; on Android/Chaquopy there is no standalone python binary so the
    subprocess either cannot start or is not CPython.
    """
    if _PROBE_CACHE["available"] is not None:
        return _PROBE_CACHE["available"]
    available = False
    executable = sys.executable
    try:
        if executable:
            completed = subprocess.run(
                [executable, "-c", "import sys; print(sys.version_info[0])"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            available = completed.returncode == 0 and completed.stdout.strip().startswith("3")
    except Exception:  # noqa: BLE001 - Android/Chaquopy and exotic runtimes land here
        available = False
    _PROBE_CACHE["available"] = available
    return available


def reset_probe_cache() -> None:
    """Test helper: forget the probe verdict."""
    _PROBE_CACHE["available"] = None


def drs_host_parent_dir() -> str:
    """Filesystem parent of the drs_host package (for child PYTHONPATH)."""
    try:
        return str(Path(__file__).resolve().parent.parent)
    except Exception:  # noqa: BLE001
        return ""


def build_child_env(site_dir=None, extra_pythonpath: str = "") -> dict:
    """Environment for the child process: PYTHONPATH + unbuffered output."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    entries = []
    for candidate in (extra_pythonpath, drs_host_parent_dir(),
                      str(site_dir) if site_dir else ""):
        if candidate and candidate not in entries:
            entries.append(candidate)
    existing = env.get("PYTHONPATH", "")
    if existing:
        entries.extend(part for part in existing.split(os.pathsep) if part)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


class ProcessRunner(threading.Thread):
    """Watchdog thread mirroring the BotRunner contract used by Supervisor.

    The supervisor relies only on: ``start()``, ``is_alive()``, ``join()``
    and the ``on_exit(runner, state, error, cpu_used=...)`` callback.
    """

    def __init__(self, ctx, bot_dir, entrypoint, on_exit, *, env: dict | None = None):
        super().__init__(name=f"drs-proc-{ctx.bot_id}", daemon=True)
        self.ctx = ctx
        self.bot_dir = Path(bot_dir)
        self.entrypoint = entrypoint
        self._on_exit = on_exit
        self._env = env or build_child_env()
        self.process: subprocess.Popen | None = None
        self._stop_forwarded = threading.Event()

    # -- control surface used by the supervisor --------------------------

    def request_stop(self) -> None:
        """Cooperative stop: SIGTERM → the child sets its stop event."""
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "posix":
                    process.send_signal(signal.SIGTERM)
                else:  # pragma: no cover - Windows path
                    process.terminate()
            except (OSError, ProcessLookupError):
                pass

    def kill(self) -> None:
        """Hard stop: the child process dies for real."""
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except (OSError, ProcessLookupError):
                pass

    def alive(self) -> bool:
        process = self.process
        return process is not None and process.poll() is None

    # -- watcher loop ------------------------------------------------------

    def run(self) -> None:
        state = "COMPLETED"
        error = None
        cpu_used = None
        try:
            self.ctx.logger.info(
                "spawning isolated process: %s -m drs_host.child_runner %s"
                % (sys.executable, self.entrypoint)
            )
            baseline = _children_cpu()  # RUSAGE_CHILDREN before this spawn
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "drs_host.child_runner",
                    str(self.bot_dir),
                    self.entrypoint,
                ],
                cwd=str(self.bot_dir),
                env=self._env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            bridge = threading.Thread(target=self._forward_stop, daemon=True)
            bridge.start()
            assert self.process.stdout is not None
            for line in self.process.stdout:
                text = line.rstrip("\n")
                if text:
                    self.ctx.logger.info(text)
            code = self.process.wait()
            cpu_used = _children_delta(baseline, _children_cpu())
            self.ctx.logger.info("child process exited with code %s" % code)
            if code == 0:
                state = "COMPLETED"
            elif self._stop_forwarded.is_set():
                state = "STOPPED"
            else:
                state = "FAILED"
                error = "child process exited with code %s" % code
                self.ctx.logger.error(error)
        except Exception as exc:  # noqa: BLE001 - spawn failures are bot failures
            state = "FAILED"
            error = "".join(traceback.format_exception(exc)).strip()
            self.ctx.logger.error(f"process runner crashed: {error}")
        finally:
            try:
                self._on_exit(self, state, error, cpu_used=cpu_used)
            except Exception:  # noqa: BLE001
                pass

    def _forward_stop(self) -> None:
        """Bridge the host-side stop_event to the child process."""
        while True:
            if self.ctx.stop_event.wait(timeout=0.2):
                self._stop_forwarded.set()
                self.request_stop()
                return
            if not self.alive():
                return


def _children_cpu():
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return usage.ru_utime + usage.ru_stime
    except Exception:  # noqa: BLE001
        return None


def _children_delta(before, after):
    """RUSAGE_CHILDREN delta across one child's lifetime.

    Note: when several process-isolated bots run concurrently, RUSAGE_CHILDREN
    aggregates all terminated children, so a bot's cpu_used may include a
    sibling that exited in the same window — an honest, documented
    approximation (thread mode keeps exact per-thread accounting).
    """
    if before is None or after is None:
        return None
    return max(0.0, after - before)
