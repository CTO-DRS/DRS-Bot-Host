"""Entry point executed INSIDE the isolated bot child process.

Invoked by the parent as::

    <python> -m drs_host.child_runner <bot_dir> <entrypoint>

Responsibilities:

- install a SIGTERM handler that sets the cooperative stop event, so the
  regular SDK (``ctx.should_stop`` / ``ctx.sleep_or_stop``) works across
  the process boundary;
- publish a minimal ``BotContext`` for the bot thread (no logger: the
  child prints, the parent's ProcessRunner pipes stdout into the bot's
  ring buffer + JSONL sink);
- run the entrypoint with ``runpy`` under ``__main__`` exactly like the
  in-process runner does.

Exit codes: 0 = completed, 1 = crashed (traceback printed to stdout,
which the parent logs), 2 = usage error.
"""

from __future__ import annotations

import runpy
import signal
import sys
import threading
import traceback
from pathlib import Path


def install_sigterm_handler(stop_event: threading.Event) -> None:
    if os_name() != "posix":
        return

    def _handler(signum, frame):  # noqa: ARG001 - signature fixed by signal API
        stop_event.set()

    try:
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):  # pragma: no cover - non-main thread / exotic
        pass


def os_name() -> str:
    return __import__("os").name


def child_main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python -m drs_host.child_runner <bot_dir> <entrypoint>")
        return 2
    bot_dir = Path(argv[0])
    entrypoint = argv[1]

    from .sdk import BotContext, set_context

    stop_event = threading.Event()
    install_sigterm_handler(stop_event)
    set_context(BotContext("child", "child", {}, stop_event, None))

    try:
        runpy.run_path(str(bot_dir / entrypoint), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        return 0 if code in (None, 0) else (code if isinstance(code, int) else 1)
    except BaseException:  # noqa: BLE001 - mirror the in-process crash report
        traceback.print_exc(file=sys.stdout)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - real child entry
    raise SystemExit(child_main())
