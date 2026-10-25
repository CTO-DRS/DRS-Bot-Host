"""Shared fixtures and bot-builder helpers for the runtime test suite."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXITING_MAIN = '''\
from drs_host.sdk import get_context

ctx = get_context()
for i in range(3):
    if ctx:
        ctx.logger.info("tick %d" % i)
    else:
        print("standalone tick %d" % i)
    if ctx:
        ctx.sleep_or_stop(0.05)
'''

LONG_RUNNING_MAIN = '''\
from drs_host.sdk import get_context

ctx = get_context()
i = 0
while not ctx.should_stop:
    ctx.logger.info("long tick %d" % i)
    ctx.sleep_or_stop(0.05)
    i += 1
'''

CRASHING_MAIN = '''\
from drs_host.sdk import get_context

ctx = get_context()
ctx.logger.info("about to crash")
raise RuntimeError("boom")
'''

PRINT_MAIN = '''\
from drs_host.sdk import get_context

print("hello-from-print")
ctx = get_context()
if ctx:
    ctx.logger.info("hello-from-sdk")
'''


def make_bot_dir(
    root: Path,
    bot_id: str = "echo-bot",
    entrypoint: str = "main.py",
    code: str | None = None,
    manifest: dict | None = None,
    files: dict | None = None,
) -> Path:
    directory = root
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "id": bot_id,
        "name": bot_id.replace("-", " ").title(),
        "version": "1.0.0",
        "entrypoint": entrypoint,
        "description": "test bot",
    }
    if manifest:
        document.update(manifest)
    (directory / "bot.json").write_text(json.dumps(document), encoding="utf-8")
    (directory / entrypoint).write_text(code or EXITING_MAIN, encoding="utf-8")
    for name, content in (files or {}).items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return directory


def make_bot_zip(tmp_path: Path, **kwargs) -> Path:
    source = make_bot_dir(tmp_path / "src", **kwargs)
    zip_path = tmp_path / "bot.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for path in sorted(source.rglob("*")):
            archive.write(path, path.relative_to(source))
    return zip_path


@pytest.fixture()
def data_dir(tmp_path) -> Path:
    path = tmp_path / "data"
    (path / "bots").mkdir(parents=True)
    return path


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.02) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())
