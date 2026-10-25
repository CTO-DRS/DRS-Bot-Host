"""Structured logging primitives: ring buffers, JSONL file sinks and the
per-bot logger handed out through the SDK."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque


def now() -> float:
    return time.time()


class RingBuffer:
    """Thread-safe bounded log buffer; ``recent`` returns the newest records."""

    def __init__(self, maxlen: int = 2000):
        self._items: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        with self._lock:
            self._items.append(record)

    def recent(self, limit: int = 500) -> list:
        with self._lock:
            items = list(self._items)
        return items[-limit:] if limit else items

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class JsonlFileSink:
    """Append-only JSONL log file with single-generation rotation."""

    def __init__(self, path, max_bytes: int = 1_000_000):
        self.path = str(path)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                if os.path.exists(self.path) and os.path.getsize(self.path) >= self.max_bytes:
                    os.replace(self.path, self.path + ".old")
            except OSError:
                pass  # rotation is best-effort; never block logging
            try:
                parent = os.path.dirname(self.path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line)
            except OSError:
                pass


class BotLogger:
    """Logger injected into a bot via :class:`drs_host.sdk.BotContext`."""

    def __init__(self, bot_id: str, sinks):
        self.bot_id = bot_id
        self._sinks = list(sinks)

    def _log(self, level: str, message) -> dict:
        record = {
            "ts": round(now(), 3),
            "level": level,
            "source": "bot",
            "bot_id": self.bot_id,
            "message": str(message),
        }
        for sink in self._sinks:
            sink.append(record)
        return record

    def debug(self, message) -> dict:
        return self._log("DEBUG", message)

    def info(self, message) -> dict:
        return self._log("INFO", message)

    def warning(self, message) -> dict:
        return self._log("WARNING", message)

    def error(self, message) -> dict:
        return self._log("ERROR", message)
