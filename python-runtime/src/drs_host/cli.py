"""Command-line interface for desktop verification of the bot runtime.

Examples::

    python -m drs_host.cli info
    python -m drs_host.cli list --data-dir ./data
    python -m drs_host.cli import sample-bots/echo-bot
    python -m drs_host.cli import-url https://github.com/owner/repo
    python -m drs_host.cli run sample-bots/echo-bot --seconds 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import host_api


def _print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _dump_new_logs(bot_id: str, cursor: int) -> int:
    records = host_api.recent_logs(bot_id, limit=1000)
    for record in records[cursor:]:
        ts = record["ts"]
        print(f"[{ts:>10.2f}] {record['level']:<7} {record['message']}")
    return len(records)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="drs-host", description="DRS Bot Host runtime CLI"
    )
    parser.add_argument("--data-dir", default="./data", help="host data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="runtime information")
    sub.add_parser("list", help="list installed bots")

    cmd_import = sub.add_parser("import", help="import a bot folder or zip")
    cmd_import.add_argument("path")
    cmd_import.add_argument("--overwrite", action="store_true")

    cmd_run = sub.add_parser("run", help="import (if needed) and run a bot")
    cmd_run.add_argument("bot", help="bot id or folder path")
    cmd_run.add_argument("--seconds", type=float, default=10.0)
    cmd_run.add_argument("--overwrite", action="store_true")

    cmd_stop = sub.add_parser("stop", help="stop a running bot")
    cmd_stop.add_argument("bot_id")

    cmd_force = sub.add_parser(
        "force-stop", help="detach an unresponsive bot (FORCE_STOPPED)"
    )
    cmd_force.add_argument("bot_id")
    cmd_force.add_argument("--grace", type=float, default=2.0)

    sub.add_parser("stats", help="aggregate host statistics")

    cmd_scaffold = sub.add_parser(
        "scaffold", help="generate a ready-to-import sample bot"
    )
    cmd_scaffold.add_argument("name")
    cmd_scaffold.add_argument("--dest", default=".")

    cmd_export = sub.add_parser("export-logs", help="export a bot's logs to a zip")
    cmd_export.add_argument("bot_id")

    cmd_config = sub.add_parser(
        "set-config", help="replace a bot's config (JSON object string)"
    )
    cmd_config.add_argument("bot_id")
    cmd_config.add_argument("json")

    cmd_url = sub.add_parser(
        "import-url", help="download a bot zip over HTTP(S) and import it"
    )
    cmd_url.add_argument("url")
    cmd_url.add_argument("--overwrite", action="store_true")

    sub.add_parser(
        "gh-scan", help="scan a GitHub link and auto-detect every bot inside"
    ).add_argument("url")

    cmd_gh_import = sub.add_parser(
        "gh-import",
        help="import selected bots from a scanned GitHub archive",
    )
    cmd_gh_import.add_argument("url")
    cmd_gh_import.add_argument(
        "--path", action="append", default=[],
        help="archive-relative bot dir or .zip/.ibot member (repeatable)",
    )
    cmd_gh_import.add_argument(
        "--all", action="store_true", help="import every detected bot"
    )
    cmd_gh_import.add_argument("--overwrite", action="store_true")

    cmd_policy = sub.add_parser(
        "requirements-policy", help="show/set the requirements policy (off/warn/enforce)"
    )
    cmd_policy.add_argument("value", nargs="?", choices=host_api.REQUIREMENTS_POLICIES)

    sub.add_parser("skills", help="list the available skill templates")

    cmd_skill = sub.add_parser(
        "scaffold-skill", help="generate a ready-to-import bot from a skill template"
    )
    cmd_skill.add_argument("skill")
    cmd_skill.add_argument("name")
    cmd_skill.add_argument("--dest", default=".")

    cmd_install = sub.add_parser(
        "install-reqs", help="pip-install a bot's requirements into its site dir"
    )
    cmd_install.add_argument("bot_id")
    cmd_install.add_argument("--timeout", type=float, default=600.0)

    cmd_serve = sub.add_parser(
        "serve-status", help="serve the Wi-Fi fleet status page until Ctrl+C"
    )
    cmd_serve.add_argument("--port", type=int, default=8090)
    cmd_serve.add_argument("--token", default=None)
    cmd_serve.add_argument("--cert", default=None, help="TLS cert (PEM) — enables https")
    cmd_serve.add_argument("--key", default=None, help="TLS key (PEM) — enables https")

    cmd_market = sub.add_parser(
        "market", help="fetch the curated bot marketplace registry"
    )
    cmd_market.add_argument("url", nargs="?", default=None)

    cmd_market_install = sub.add_parser(
        "market-install", help="install a marketplace bot by its URL"
    )
    cmd_market_install.add_argument("url")
    cmd_market_install.add_argument("--overwrite", action="store_true")

    cmd_backup = sub.add_parser(
        "backup", help="zip every installed bot into <data-dir>/backups/"
    )
    cmd_backup.add_argument("--dest", default=None)

    cmd_restore = sub.add_parser(
        "restore", help="re-import every bot from a backup zip"
    )
    cmd_restore.add_argument("zip")
    cmd_restore.add_argument("--overwrite", action="store_true")

    cmd_health = sub.add_parser(
        "health", help="show a bot's health config/state (or toggle with --on/--off)"
    )
    cmd_health.add_argument("bot_id")
    toggle = cmd_health.add_mutually_exclusive_group()
    toggle.add_argument("--on", dest="enable", action="store_true")
    toggle.add_argument("--off", dest="disable", action="store_true")

    cmd_probe = sub.add_parser(
        "health-probe", help="run one manual health probe for a bot"
    )
    cmd_probe.add_argument("bot_id")

    sub.add_parser(
        "registry-list", help="list saved custom marketplace registry sources"
    )
    cmd_reg_add = sub.add_parser(
        "registry-add", help="save a custom marketplace registry URL"
    )
    cmd_reg_add.add_argument("url")
    cmd_reg_rm = sub.add_parser(
        "registry-remove", help="remove a saved custom registry URL"
    )
    cmd_reg_rm.add_argument("url")

    args = parser.parse_args(argv)
    host_api.configure(args.data_dir)

    if args.command == "info":
        _print_json(host_api.runtime_info())
        return 0

    if args.command == "list":
        _print_json(host_api.list_bots())
        return 0

    if args.command == "import":
        result = _import_any(args.path, args.overwrite)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "stop":
        result = host_api.stop_bot(args.bot_id)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "force-stop":
        result = host_api.force_stop_bot(args.bot_id, args.grace)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "import-url":
        result = host_api.import_bot_url(args.url, overwrite=args.overwrite)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "gh-scan":
        result = host_api.github_scan(args.url)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "gh-import":
        if args.all:
            scan = host_api.github_scan(args.url)
            if not scan.get("ok"):
                _print_json(scan)
                return 2
            paths = [b["dir"] for b in scan.get("bots", []) if b.get("valid")]
            if not paths:
                _print_json({"ok": False, "errors": [scan.get("hint") or "no valid bots detected"]})
                return 2
        else:
            paths = list(args.path)
        if not paths:
            _print_json({"ok": False, "errors": ["nothing selected — pass --path or --all"]})
            return 2
        result = host_api.github_import_selected(args.url, paths, overwrite=args.overwrite)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "requirements-policy":
        if args.value:
            result = host_api.set_requirements_policy(args.value)
            _print_json(result)
            return 0 if result.get("ok") else 2
        _print_json({"ok": True, "policy": host_api.requirements_policy()})
        return 0

    if args.command == "stats":
        _print_json(host_api.host_stats())
        return 0

    if args.command == "scaffold":
        result = host_api.scaffold_bot(args.name, args.dest)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "export-logs":
        result = host_api.export_logs(args.bot_id)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "set-config":
        result = host_api.set_bot_config(args.bot_id, args.json)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "skills":
        _print_json(host_api.list_skills())
        return 0

    if args.command == "scaffold-skill":
        result = host_api.scaffold_skill(args.skill, args.name, args.dest)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "install-reqs":
        result = host_api.install_bot_requirements(args.bot_id, args.timeout)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "serve-status":
        started = host_api.web_status_start(args.port, args.token, args.cert, args.key)
        _print_json(started)
        if not started.get("ok"):
            return 2
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            host_api.web_status_stop()
            print("status server stopped")
        return 0

    if args.command == "market":
        result = host_api.marketplace_fetch(args.url)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "market-install":
        result = host_api.marketplace_install(args.url, args.overwrite)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "backup":
        result = host_api.backup_all(args.dest)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "restore":
        result = host_api.restore_backup(args.zip, args.overwrite)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "health":
        if args.enable or args.disable:
            result = host_api.set_health_enabled(args.bot_id, bool(args.enable))
            _print_json(result)
            return 0 if result.get("ok") else 2
        status = host_api.bot_status(args.bot_id)
        if not status.get("ok"):
            _print_json(status)
            return 2
        _print_json({
            "ok": True,
            "id": args.bot_id,
            "health": status.get("health"),
            "health_state": status.get("health_state"),
        })
        return 0

    if args.command == "health-probe":
        result = host_api.probe_health(args.bot_id)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "registry-list":
        _print_json({"ok": True, "sources": host_api.registry_sources()})
        return 0

    if args.command == "registry-add":
        result = host_api.add_registry_source(args.url)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "registry-remove":
        result = host_api.remove_registry_source(args.url)
        _print_json(result)
        return 0 if result.get("ok") else 2

    if args.command == "run":
        return _run(args)

    parser.error(f"unknown command: {args.command}")
    return 2


def _import_any(path: str, overwrite: bool) -> dict:
    if os.path.isdir(path):
        return host_api.import_folder(path, overwrite=overwrite)
    return host_api.import_zip(path, overwrite=overwrite)


def _run(args) -> int:
    bot_ref = args.bot
    if os.path.isdir(bot_ref) or (
        os.path.isfile(bot_ref) and bot_ref.lower().endswith(".zip")
    ):
        result = _import_any(bot_ref, args.overwrite)
        if not result.get("ok"):
            _print_json(result)
            return 2
        bot_id = result["bot_id"]
        print(f"imported: {bot_id}")
    else:
        bot_id = bot_ref
        if not host_api.bot_status(bot_id).get("ok"):
            print(f"unknown bot: {bot_id}", file=sys.stderr)
            return 2

    started = host_api.start_bot(bot_id)
    if not started.get("ok"):
        _print_json(started)
        return 2

    print(f"running {bot_id} for up to {args.seconds}s (Ctrl+C to stop)")
    deadline = time.time() + args.seconds
    cursor = 0
    try:
        while time.time() < deadline:
            time.sleep(0.4)
            cursor = _dump_new_logs(bot_id, cursor)
            status = host_api.bot_status(bot_id)
            if status.get("state") in ("COMPLETED", "FAILED", "STOPPED"):
                break
    except KeyboardInterrupt:
        print("\ninterrupted; stopping bot ...")

    final = host_api.bot_status(bot_id)
    if final.get("state") not in ("COMPLETED", "FAILED", "STOPPED"):
        host_api.stop_bot(bot_id)
        final = host_api.bot_status(bot_id)
        cursor = _dump_new_logs(bot_id, cursor)

    state = final.get("state")
    restarts = final.get("restarts", 0)
    if final.get("last_error"):
        print(f"last error:\n{final['last_error']}")
    print(f"final state: {state} (restarts: {restarts})")
    return 0 if state in ("COMPLETED", "STOPPED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
