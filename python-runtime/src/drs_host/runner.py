"""Runs one bot entrypoint inside a managed, daemon thread.

The runner:

- injects the :class:`drs_host.sdk.BotContext` into the thread (contextvar)
- registers a stdout adapter so ``print()`` becomes per-bot INFO logs
- executes the entrypoint through ``runpy`` with ``__name__ == "__main__"``
  (both guard-based and top-level bot scripts work)
- classifies the outcome: ``COMPLETED``, ``STOPPED`` or ``FAILED`` with a
  full traceback, and reports it to the supervisor via ``on_exit``.

Python threads cannot be force-killed; termination is cooperative through
``ctx.stop_event`` / ``ctx.sleep_or_stop()``. This is a documented v1.0
contract (see docs/BOT_SPEC.md).
"""

from __future__ import annotations

import runpy
import sys
import threading
import traceback
from pathlib import Path

from .sdk import StopRequested, set_context, reset_context


class _StreamAdapter:
    """Turns a stream of writes into line-based INFO log records."""

    def __init__(self, logger):
        self._logger = logger
        self._buffer = ""

    def write(self, s):
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._logger.info(line)
        return len(s)

    def flush(self):
        if self._buffer.strip():
            self._logger.info(self._buffer)
        self._buffer = ""


class BotRunner(threading.Thread):
    """Executes a single bot run and reports the outcome."""

    def __init__(self, ctx, bot_dir, entrypoint, stream_hub, on_exit):
        super().__init__(name=f"drs-bot-{ctx.bot_id}", daemon=True)
        self.ctx = ctx
        self.bot_dir = Path(bot_dir)
        self.entrypoint = entrypoint
        self.stream_hub = stream_hub
        self._on_exit = on_exit

    def run(self) -> None:
        state = "COMPLETED"
        error = None
        token = set_context(self.ctx)
        adapter = None
        swapped = False
        try:
            if self.stream_hub is not None:
                adapter = _StreamAdapter(self.ctx.logger)
                self.stream_hub.register(adapter)
                if sys.stdout is not self.stream_hub:
                    self._original_stdout = sys.stdout
                    sys.stdout = self.stream_hub
                    swapped = True
            sys.argv = [self.entrypoint]
            self.ctx.logger.info(f"starting entrypoint {self.entrypoint}")
            runpy.run_path(str(self.bot_dir / self.entrypoint), run_name="__main__")
        except StopRequested:
            state = "STOPPED"
        except SystemExit as exc:
            code = exc.code
            if code in (None, 0):
                state = "COMPLETED"
            else:
                state = "FAILED"
                error = f"SystemExit: {code}"
                self.ctx.logger.error(error)
        except BaseException as exc:  # noqa: BLE001 - bots may raise anything
            state = "FAILED"
            error = "".join(traceback.format_exception(exc)).strip()
            self.ctx.logger.error(f"bot crashed: {error}")
        finally:
            if swapped and sys.stdout is self.stream_hub:
                sys.stdout = self._original_stdout
            if self.stream_hub is not None:
                self.stream_hub.unregister()
            reset_context(token)
            try:
                self._on_exit(state, error)
            except Exception:  # noqa: BLE001 - supervisor callbacks must not hang
                pass
