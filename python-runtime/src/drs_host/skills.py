"""Skill template registry — one-tap, ready-to-run bot blueprints (v1.3).

A *skill* is a curated bot template: manifest defaults, default ``config``,
optional ``requirements`` and the actual source files. ``scaffold_skill``
materialises one into a folder that the strict manifest validator accepts
and the supervisor can import and run without any editing.

The registry is intentionally stdlib-only: every skill marked
``requirements: []`` runs on a bare Chaquopy runtime; the telegram skill
declares its dependency and is installed via ``drs_host.installer`` (or the
build-time package set).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .manifest import _ID_RE, validate_manifest

# --------------------------------------------------------------------- #
# File templates                                                         #
# --------------------------------------------------------------------- #

_ECHO_MAIN = '''\
"""{NAME} — heartbeat bot scaffolded from the 'echo' skill."""

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    interval = float(ctx.config.get("interval_seconds", 5) or 5)
    message = str(ctx.config.get("message", "hello"))
    counter = 0
    ctx.logger.info("started; interval=%.2fs" % interval)
    while not ctx.should_stop:
        ctx.logger.info("[%d] %s" % (counter, message))
        counter += 1
        ctx.sleep_or_stop(interval)
    ctx.logger.info("stopped cleanly after %d ticks" % counter)


main()
'''

_HTTP_POLLER_MAIN = '''\
"""{NAME} — polls a URL every N seconds and logs status changes.

Stdlib only (urllib). Config keys: url, interval_seconds, timeout_seconds.
"""

import hashlib
import urllib.request

from drs_host.sdk import get_context


def fetch(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "drs-bot-host/1.3"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    url = str(ctx.config.get("url", "https://example.com"))
    interval = float(ctx.config.get("interval_seconds", 30) or 30)
    timeout = float(ctx.config.get("timeout_seconds", 10) or 10)
    last_digest = None
    ctx.logger.info("polling %s every %.0fs" % (url, interval))
    while not ctx.should_stop:
        try:
            status, body = fetch(url, timeout)
            digest = hashlib.sha256(body).hexdigest()[:12]
            changed = last_digest is not None and digest != last_digest
            last_digest = digest
            ctx.logger.info(
                "HTTP %s, %d bytes, sha256[:12]=%s%s"
                % (status, len(body), digest, " (CHANGED)" if changed else "")
            )
            if changed:
                ctx.set_progress(label="content changed")
        except Exception as exc:  # noqa: BLE001 - network errors must not kill the bot
            ctx.logger.warning("poll failed: %s" % exc)
        ctx.sleep_or_stop(interval)


main()
'''

_RSS_WATCHER_MAIN = '''\
"""{NAME} — watches an RSS/Atom feed and logs new item titles.

Stdlib only (urllib + xml.etree). Config keys: feed_url, interval_seconds.
"""

import xml.etree.ElementTree as ET
import urllib.request

from drs_host.sdk import get_context


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def fetch_titles(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "drs-bot-host/1.3"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        root = ET.fromstring(response.read())
    titles = []
    for element in root.iter():
        if _local(element.tag) == "item" or _local(element.tag) == "entry":
            for child in element:
                if _local(child.tag) == "title" and (child.text or "").strip():
                    titles.append(child.text.strip())
    return titles


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    feed = str(ctx.config.get("feed_url", "https://hnrss.org/frontpage"))
    interval = float(ctx.config.get("interval_seconds", 120) or 120)
    timeout = float(ctx.config.get("timeout_seconds", 15) or 15)
    seen = set()
    first = True
    ctx.logger.info("watching feed %s" % feed)
    while not ctx.should_stop:
        try:
            titles = fetch_titles(feed, timeout)
            fresh = [t for t in titles if t not in seen]
            for title in fresh:
                seen.add(title)
            if first:
                ctx.logger.info("feed has %d items (baseline stored)" % len(titles))
                first = False
            elif fresh:
                ctx.logger.info("%d new item(s)" % len(fresh))
                for title in fresh[:5]:
                    ctx.logger.info("NEW: %s" % title[:120])
        except Exception as exc:  # noqa: BLE001
            ctx.logger.warning("feed fetch failed: %s" % exc)
        ctx.sleep_or_stop(interval)


main()
'''

_FILE_WATCHER_MAIN = '''\
"""{NAME} — watches a folder and logs created/changed/deleted files.

Stdlib only. Config keys: watch_dir, interval_seconds, extensions.
Set watch_dir to an empty string to watch the bot's own directory.
"""

import os
import time

from drs_host.sdk import get_context


def scan(root, extensions):
    snapshot = {}
    for current, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(current, name)
            if extensions and not name.lower().endswith(tuple(extensions)):
                continue
            try:
                stat = os.stat(path)
                snapshot[path] = (stat.st_mtime, stat.st_size)
            except OSError:
                continue
    return snapshot


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    watch_dir = str(ctx.config.get("watch_dir", "") or os.path.dirname(os.path.abspath(__file__)))
    interval = float(ctx.config.get("interval_seconds", 10) or 10)
    extensions = [e.lower() for e in ctx.config.get("extensions", []) or [] if isinstance(e, str)]
    ctx.logger.info("watching %s every %.0fs" % (watch_dir, interval))
    snapshot = scan(watch_dir, extensions)
    ctx.logger.info("baseline: %d file(s)" % len(snapshot))
    while not ctx.should_stop:
        ctx.sleep_or_stop(interval)
        if ctx.should_stop:
            break
        current = scan(watch_dir, extensions)
        for path in sorted(set(current) - set(snapshot)):
            ctx.logger.info("CREATED %s" % path)
        for path in sorted(set(snapshot) - set(current)):
            ctx.logger.info("DELETED %s" % path)
        for path in sorted(set(current) & set(snapshot)):
            if current[path] != snapshot[path]:
                ctx.logger.info("CHANGED %s" % path)
        snapshot = current


main()
'''

_WEBHOOK_RECEIVER_MAIN = '''\
"""{NAME} — tiny webhook receiver on the phone's localhost.

Stdlib http.server. Config keys: port, path, response_text.
Send POSTs to http://127.0.0.1:<port><path>; every request is logged.
Stop the bot to release the port (cooperative stop is checked per request).
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    port = int(ctx.config.get("port", 8899) or 8899)
    path = str(ctx.config.get("path", "/hook") or "/hook")
    response_text = str(ctx.config.get("response_text", "ok") or "ok")

    class Handler(BaseHTTPRequestHandler):
        def _answer(self, code, body):
            payload = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._answer(200, "drs bot host webhook alive")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(min(length, 1_000_000)).decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
                shown = json.dumps(parsed, ensure_ascii=False)[:400]
            except Exception:  # noqa: BLE001
                shown = raw[:400]
            ctx.logger.info("POST %s from %s: %s" % (self.path, self.client_address[0], shown))
            self._answer(200, response_text)

        def log_message(self, *args):  # silence the default stderr noise
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    ctx.logger.info("webhook receiver listening on 127.0.0.1:%d%s" % (port, path))
    try:
        while not ctx.should_stop:
            server.timeout = 1.0
            server.handle_request()
    finally:
        server.server_close()
        ctx.logger.info("webhook receiver closed")


main()
'''

_SCHEDULER_CRON_MAIN = '''\
"""{NAME} — scheduled-window demo (interval schedule in bot.json).

The manifest carries a schedule object, so the host's scheduler starts and
stops this bot automatically inside its configured windows. The script
itself just does periodic work while it is allowed to run.
"""

import datetime

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    interval = float(ctx.config.get("interval_seconds", 20) or 20)
    ctx.logger.info("scheduled run started at %s" % datetime.datetime.now().isoformat(timespec="seconds"))
    counter = 0
    while not ctx.should_stop:
        counter += 1
        ctx.logger.info("scheduled tick %d" % counter)
        ctx.sleep_or_stop(interval)
    ctx.logger.info("window ended after %d tick(s)" % counter)


main()
'''

_TELEGRAM_ECHO_MAIN = '''\
"""{NAME} — Telegram echo bot (requires the python-telegram-bot package).

Config keys: bot_token (required), interval handled by the library itself.
Install the dependency from the bot detail screen ("Install requirements")
or bake it into the APK build (Chaquopy pip block).
"""

import os

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("no host context; run this bot inside DRS Bot Host")
        return
    try:
        from telegram.ext import Application, MessageHandler, filters
    except ImportError as exc:
        ctx.logger.error(
            "python-telegram-bot is not installed: %s — use the "
            "Install requirements action on this bot" % exc
        )
        raise SystemExit(1)

    token = str(ctx.config.get("bot_token", "") or os.environ.get("BOT_TOKEN", ""))
    if not token:
        ctx.logger.error("config.bot_token is missing")
        raise SystemExit(1)

    application = Application.builder().token(token).build()

    async def echo(update, context):
        if update and update.message:
            ctx.logger.info("echoing to %s" % (update.message.chat_id,))
            await update.message.reply_text(update.message.text)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    ctx.logger.info("telegram bot starting (long polling)")
    application.run_polling(stop_signals=None)


main()
'''

_GENERIC_README = """\
# {NAME}

Scaffolded by `drs_host scaffold_skill` from the **{SKILL}** skill.

- `bot.json` — manifest (identity, requirements, config, schedule)
- `main.py`  — the skill's entrypoint, ready to run unmodified
{EXTRA}
Tune `config` in `bot.json` (or from the app via the config editor).
"""

_TELEGRAM_README_EXTRA = """
## Setup

1. Put your bot token into `bot.json` → `config` → `bot_token`.
2. Install the dependency: bot detail screen → *Install requirements*
   (needs pip on the runtime; on desktop this just works).
"""


def _manifest_template(skill: dict, slug: str, name: str) -> dict:
    document = {
        "spec_version": 1,
        "id": slug,
        "name": name,
        "version": "0.1.0",
        "entrypoint": skill.get("entrypoint", "main.py"),
        "language": "python",
        "author": "drs_host skills",
        "description": "%s — %s skill" % (name, skill["key"]),
        "requirements": list(skill.get("requirements", [])),
        "config": dict(skill.get("config", {})),
        "restart": {"policy": "on_failure", "max_restarts": 3},
        "auto_start": False,
    }
    if skill.get("schedule"):
        document["schedule"] = dict(skill["schedule"])
    if skill.get("config_hidden"):
        document["config"] = {k: v for k, v in document["config"].items()}
    return document


def _normalize_skill(skill: dict) -> dict:
    return {
        "key": str(skill.get("key", "")),
        "title": str(skill.get("title", skill.get("key", ""))),
        "description": str(skill.get("description", "")),
        "requirements": list(skill.get("requirements", [])),
        "config": dict(skill.get("config", {})),
        "schedule": dict(skill["schedule"]) if skill.get("schedule") else None,
        "entrypoint": str(skill.get("entrypoint", "main.py")),
        "files": dict(skill.get("files", {})),
    }


# --------------------------------------------------------------------- #
# Registry                                                               #
# --------------------------------------------------------------------- #

SKILLS: list = [
    _normalize_skill({
        "key": "echo",
        "title": "Heartbeat / Echo",
        "description": "Logs a message every N seconds — the minimal working bot and the default scaffold.",
        "config": {"interval_seconds": 5.0, "message": "hello from DRS Bot Host"},
        "files": {"main.py": _ECHO_MAIN},
    }),
    _normalize_skill({
        "key": "http-poller",
        "title": "HTTP URL Poller",
        "description": "Fetches a URL every N seconds, logs status/size and detects content changes. Stdlib only.",
        "config": {
            "url": "https://example.com",
            "interval_seconds": 30.0,
            "timeout_seconds": 10.0,
        },
        "files": {"main.py": _HTTP_POLLER_MAIN},
    }),
    _normalize_skill({
        "key": "rss-watcher",
        "title": "RSS / Atom Watcher",
        "description": "Watches a feed and logs newly appearing item titles. Stdlib only.",
        "config": {
            "feed_url": "https://hnrss.org/frontpage",
            "interval_seconds": 120.0,
            "timeout_seconds": 15.0,
        },
        "files": {"main.py": _RSS_WATCHER_MAIN},
    }),
    _normalize_skill({
        "key": "file-watcher",
        "title": "Folder File Watcher",
        "description": "Logs created/changed/deleted files inside a directory. Stdlib only.",
        "config": {"watch_dir": "", "interval_seconds": 10.0, "extensions": []},
        "files": {"main.py": _FILE_WATCHER_MAIN},
    }),
    _normalize_skill({
        "key": "webhook-receiver",
        "title": "Local Webhook Receiver",
        "description": "Tiny localhost HTTP server that logs every POST — perfect for testing integrations. Stdlib only.",
        "config": {"port": 8899, "path": "/hook", "response_text": "ok"},
        "files": {"main.py": _WEBHOOK_RECEIVER_MAIN},
    }),
    _normalize_skill({
        "key": "scheduler-cron",
        "title": "Scheduled Window Demo",
        "description": "Bot driven by the host scheduler: manifest schedule starts/stops it automatically in its window.",
        "config": {"interval_seconds": 20.0},
        "schedule": {"kind": "interval", "interval_seconds": 300.0, "run_seconds": 60.0, "enabled": True},
        "files": {"main.py": _SCHEDULER_CRON_MAIN},
    }),
    _normalize_skill({
        "key": "telegram-echo",
        "title": "Telegram Echo Bot",
        "description": "Telegram long-polling echo bot built on python-telegram-bot (dependency installed on demand).",
        "requirements": ["python-telegram-bot"],
        "config": {"bot_token": ""},
        "files": {
            "main.py": _TELEGRAM_ECHO_MAIN,
            "requirements.txt": "python-telegram-bot>=21.0\n",
        },
    }),
]

_SKILL_KEYS = {skill["key"] for skill in SKILLS}


# --------------------------------------------------------------------- #
# Public API                                                             #
# --------------------------------------------------------------------- #


def list_skills() -> list:
    """Machine-readable skill catalogue (returned verbatim by host_api)."""
    return [
        {
            "key": skill["key"],
            "title": skill["title"],
            "description": skill["description"],
            "requirements": list(skill["requirements"]),
            "config": dict(skill["config"]),
            "schedule": dict(skill["schedule"]) if skill["schedule"] else None,
        }
        for skill in SKILLS
    ]


def get_skill(key: str):
    for skill in SKILLS:
        if skill["key"] == key:
            return skill
    return None


def slugify(name: str) -> str:
    """Derive a manifest-legal bot id from a free-form display name."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def scaffold_skill(skill_key: str, name: str, dest) -> dict:
    """Materialise skill ``skill_key`` as ``<dest>/<slug>/``. Never raises."""
    skill = get_skill(str(skill_key or "").strip())
    if skill is None:
        return {
            "ok": False,
            "errors": [
                "unknown skill: %r — known skills: %s"
                % (skill_key, ", ".join(sorted(_SKILL_KEYS)))
            ],
        }
    clean = (name or "").strip()
    if not clean:
        return {"ok": False, "errors": ["bot name is required"]}

    slug = slugify(clean)
    if not _ID_RE.match(slug):
        return {
            "ok": False,
            "errors": [
                "cannot derive a valid bot id from %r (got %r; need 2-64 chars "
                "of [a-z0-9-_])" % (clean, slug)
            ],
        }

    target_root = Path(dest)
    target = target_root / slug
    if target.exists():
        return {"ok": False, "errors": ["target already exists: %s" % target]}

    manifest = _manifest_template(skill, slug, clean)
    manifest["config"] = {
        **manifest["config"],
        **{
            key: value
            for key, value in skill["config"].items()
            if key not in manifest["config"]
        },
    }
    validated, errors = validate_manifest(manifest)
    if validated is None:
        return {"ok": False, "errors": errors}

    extra = ""
    if skill["key"] == "telegram-echo":
        extra = _TELEGRAM_README_EXTRA
    readme = _GENERIC_README.replace("{NAME}", clean).replace("{SKILL}", skill["title"]).replace(
        "{EXTRA}", extra
    )

    written = []
    try:
        target.mkdir(parents=True, exist_ok=False)
        (target / "bot.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written.append("bot.json")
        for relpath, template in skill["files"].items():
            content = template.replace("{NAME}", clean)
            target_path = target / relpath
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            written.append(relpath)
        (target / "README.md").write_text(readme, encoding="utf-8")
        written.append("README.md")
    except OSError as exc:
        return {"ok": False, "errors": ["write failed: %s" % exc], "files": written}

    return {
        "ok": True,
        "skill": skill["key"],
        "id": slug,
        "path": str(target),
        "files": written,
    }
