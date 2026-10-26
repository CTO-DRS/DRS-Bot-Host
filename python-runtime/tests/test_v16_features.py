"""v1.6 feature tests: per-bot health checks (HTTP + command probes,
thresholds, auto-recovery, manual probes, enable/disable persistence)
and custom (community) marketplace registry sources.
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from drs_host import host_api, marketplace
from drs_host.healthcheck import (
    HEALTH_DISABLED,
    HEALTH_HEALTHY,
    HEALTH_IDLE,
    HEALTH_UNHEALTHY,
    probe_command,
    probe_http,
)
from drs_host.manifest import validate_manifest
from drs_host.supervisor import BotState, Supervisor
from conftest import LONG_RUNNING_MAIN, make_bot_dir

BASE_MANIFEST = {
    "id": "hc-bot",
    "name": "HC Bot",
    "version": "1.0.0",
    "entrypoint": "main.py",
}


class _Router(BaseHTTPRequestHandler):
    """Tiny test server: /good -> 200, /bad -> 404, others 500."""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/good":
            self.send_response(200)
        elif self.path == "/bad":
            self.send_response(404)
        else:
            self.send_response(500)
        self.end_headers()

    def log_message(self, *args):  # silence request logging
        pass


@pytest.fixture()
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Router)
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def make_supervisor(tmp_path) -> Supervisor:
    bots_root = tmp_path / "bots"
    bots_root.mkdir(parents=True, exist_ok=True)
    return Supervisor(bots_root)


def import_health_bot(supervisor, tmp_path, *, health, bot_id="hc-bot"):
    directory = make_bot_dir(
        tmp_path / "src",
        bot_id=bot_id,
        code=LONG_RUNNING_MAIN,
        manifest={"health": health},
    )
    result = supervisor.import_folder(directory)
    assert result.get("ok"), result
    return result["bot_id"]


# --------------------------------------------------------------------- #
# manifest: health validation                                            #
# --------------------------------------------------------------------- #


def test_manifest_accepts_http_health():
    document = {
        **BASE_MANIFEST,
        "health": {"kind": "http", "url": "http://127.0.0.1:9000/health"},
    }
    manifest, errors = validate_manifest(document)
    assert errors == []
    assert manifest.health["kind"] == "http"
    assert manifest.health["expect_status"] == 200
    assert manifest.health["interval_seconds"] == 30.0
    assert manifest.health["timeout_seconds"] == 5.0
    assert manifest.health["failure_threshold"] == 3
    assert manifest.health["success_threshold"] == 1
    assert manifest.health["recover"] == "restart"
    assert manifest.health["enabled"] is True


def test_manifest_accepts_command_health():
    document = {
        **BASE_MANIFEST,
        "health": {"kind": "command", "script": "checks/health.py", "recover": "none"},
    }
    manifest, errors = validate_manifest(document)
    assert errors == []
    assert manifest.health["script"] == "checks/health.py"
    assert manifest.health["recover"] == "none"


def test_manifest_without_health_is_none():
    manifest, errors = validate_manifest(BASE_MANIFEST)
    assert errors == []
    assert manifest.health is None


@pytest.mark.parametrize(
    "health,fragment",
    [
        ({"kind": "tcp", "url": "http://x.dev"}, "health.kind"),
        ({"kind": "http"}, "health.url"),
        ({"kind": "http", "url": "ftp://x.dev"}, "health.url"),
        ({"kind": "http", "url": "http://x.dev", "expect_status": 99}, "expect_status"),
        ({"kind": "http", "url": "http://x.dev", "expect_status": True}, "expect_status"),
        ({"kind": "command"}, "health.script"),
        ({"kind": "command", "script": "/abs/path.py"}, "health.script"),
        ({"kind": "command", "script": "../evil.py"}, "health.script"),
        ({"kind": "command", "script": "run.sh"}, "health.script"),
        ({"kind": "http", "url": "http://x.dev", "interval_seconds": 1}, "interval_seconds"),
        ({"kind": "http", "url": "http://x.dev", "timeout_seconds": 0}, "timeout_seconds"),
        ({"kind": "http", "url": "http://x.dev", "failure_threshold": 0}, "failure_threshold"),
        ({"kind": "http", "url": "http://x.dev", "success_threshold": 101}, "success_threshold"),
        ({"kind": "http", "url": "http://x.dev", "recover": "kill"}, "health.recover"),
        ({"kind": "http", "url": "http://x.dev", "wat": 1}, "unknown key"),
        ({"kind": "http", "url": "http://x.dev", "enabled": "yes"}, "health.enabled"),
        ("nope", "health: must be an object"),
    ],
)
def test_manifest_rejects_bad_health(health, fragment):
    document = {**BASE_MANIFEST, "health": health}
    manifest, errors = validate_manifest(document)
    assert manifest is None
    assert any(fragment in error for error in errors), errors


# --------------------------------------------------------------------- #
# probe primitives                                                       #
# --------------------------------------------------------------------- #


def test_probe_http_success_and_mismatch(http_server):
    ok, detail = probe_http(f"{http_server}/good", timeout=5.0)
    assert ok and detail == "HTTP 200"
    ok, detail = probe_http(f"{http_server}/good", expect_status=204, timeout=5.0)
    assert not ok and "expected 204" in detail
    ok, detail = probe_http(f"{http_server}/bad", timeout=5.0)
    assert not ok and detail == "HTTP 404"


def test_probe_http_connection_refused(tmp_path):
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead_port = sock.getsockname()[1]
    sock.close()
    ok, detail = probe_http(f"http://127.0.0.1:{dead_port}/health", timeout=1.0)
    assert not ok
    assert ("ConnectionRefused" in detail) or ("URLError" in detail) or ("Error" in detail)


def test_probe_command_bool_and_tuple(tmp_path):
    script = (
        "def check():\n"
        "    return True\n"
    )
    (tmp_path / "health.py").write_text(script, encoding="utf-8")
    ok, detail = probe_command(tmp_path, "health.py")
    assert ok and detail == "ok"

    script_tuple = (
        "def check():\n"
        "    return (True, 'all systems nominal')\n"
    )
    (tmp_path / "health2.py").write_text(script_tuple, encoding="utf-8")
    ok, detail = probe_command(tmp_path, "health2.py")
    assert ok and "nominal" in detail


def test_probe_command_failures(tmp_path):
    (tmp_path / "false.py").write_text("def check():\n    return False\n", encoding="utf-8")
    ok, detail = probe_command(tmp_path, "false.py")
    assert not ok and "False" in detail

    (tmp_path / "raise.py").write_text(
        "def check():\n    raise ValueError('nope')\n", encoding="utf-8"
    )
    ok, detail = probe_command(tmp_path, "raise.py")
    assert not ok and "ValueError" in detail and "nope" in detail

    (tmp_path / "nocheck.py").write_text("x = 1\n", encoding="utf-8")
    ok, detail = probe_command(tmp_path, "nocheck.py")
    assert not ok and "check()" in detail

    (tmp_path / "badtype.py").write_text("def check():\n    return 'yes'\n", encoding="utf-8")
    ok, detail = probe_command(tmp_path, "badtype.py")
    assert not ok and "bool" in detail

    ok, detail = probe_command(tmp_path, "missing.py")
    assert not ok and "not found" in detail


# --------------------------------------------------------------------- #
# monitor: statuses, thresholds, recovery                                #
# --------------------------------------------------------------------- #


def test_status_includes_health_and_health_state(tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={"kind": "http", "url": "http://127.0.0.1:9/health"},
    )
    status = supervisor.status(bot_id)
    assert status["ok"]
    assert status["health"]["kind"] == "http"
    state = status["health_state"]
    assert state["status"] == "unknown"
    assert state["consecutive_failures"] == 0
    assert state["recoveries"] == 0


def _drive(supervisor, bot_id, ticks, *, settle: float = 0.08):
    """Drive tick_once with synthetic timestamps.

    A short REAL pause between ticks lets probe threads finish on the real
    clock (their timeout deadline is also real); interval pacing itself is
    synthetic, so tests stay fast.
    """
    monitor = supervisor._health_monitor
    for index, now in enumerate(ticks):
        if index:
            time.sleep(settle)
        monitor.tick_once(now)


def test_monitor_marks_unhealthy_after_threshold(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "http",
            "url": f"{http_server}/bad",
            "interval_seconds": 5,
            "failure_threshold": 3,
            "recover": "none",
        },
    )
    assert supervisor.start(bot_id).get("ok")
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6, base + 11.5, base + 16.5, base + 21.5])
    state = supervisor.get(bot_id).health_state
    assert state["status"] == HEALTH_UNHEALTHY
    assert state["consecutive_failures"] == 3
    assert state["last_error"] == "HTTP 404"
    assert state["recoveries"] == 0


def test_monitor_marks_healthy_on_success(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "http",
            "url": f"{http_server}/good",
            "interval_seconds": 5,
            "recover": "none",
        },
    )
    assert supervisor.start(bot_id).get("ok")
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6, base + 11.5])
    state = supervisor.get(bot_id).health_state
    assert state["status"] == HEALTH_HEALTHY
    assert state["consecutive_successes"] == 1
    assert state["last_success_at"] is not None


def test_monitor_success_threshold_requires_streak(http_server, tmp_path):
    """success_threshold=2: one success keeps 'unknown', two make healthy."""
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "http",
            "url": f"{http_server}/good",
            "interval_seconds": 5,
            "success_threshold": 2,
            "recover": "none",
        },
    )
    assert supervisor.start(bot_id).get("ok")
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6, base + 11.5, base + 16.5])
    state = supervisor.get(bot_id).health_state
    assert state["status"] == HEALTH_HEALTHY
    assert state["consecutive_successes"] == 2


def test_monitor_idle_when_bot_stopped(tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={"kind": "http", "url": "http://127.0.0.1:9/health"},
    )
    base = time.time()
    _drive(supervisor, bot_id, [base])
    assert supervisor.get(bot_id).health_state["status"] == HEALTH_IDLE


def test_monitor_disabled_health(tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "http",
            "url": "http://127.0.0.1:9/health",
            "enabled": False,
        },
    )
    assert supervisor.start(bot_id).get("ok")
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6])
    state = supervisor.get(bot_id).health_state
    assert state["status"] == HEALTH_DISABLED
    assert state["last_probe_at"] is None


def test_monitor_recovers_via_restart(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "http",
            "url": f"{http_server}/bad",
            "interval_seconds": 5,
            "failure_threshold": 2,
            "recover": "restart",
        },
    )
    assert supervisor.start(bot_id).get("ok")
    first_run_count = supervisor.get(bot_id).run_count
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6, base + 11.5, base + 16.5, base + 21.5])
    bot = supervisor.get(bot_id)
    assert bot.health_state["recoveries"] == 1
    assert bot.run_count == first_run_count + 1
    assert bot.state in (BotState.RUNNING, BotState.STARTING, BotState.STOPPING)


def test_health_state_resets_on_start_but_keeps_recoveries(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "http",
            "url": f"{http_server}/bad",
            "interval_seconds": 5,
            "failure_threshold": 3,
            "recover": "none",
        },
    )
    assert supervisor.start(bot_id).get("ok")
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6, base + 11.5])
    before = supervisor.get(bot_id).health_state
    assert before["consecutive_failures"] == 1
    before["recoveries"] = 4  # simulate an earlier auto-recovery
    supervisor.get(bot_id).health_state["recoveries"] = 4

    assert supervisor.stop(bot_id).get("ok")
    assert supervisor.start(bot_id).get("ok")
    after = supervisor.get(bot_id).health_state
    assert after["consecutive_failures"] == 0
    assert after["status"] == "unknown"
    assert after["recoveries"] == 4


def test_monitor_command_probe_and_recovery_none(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "command",
            "script": "health.py",
            "interval_seconds": 5,
            "failure_threshold": 1,
            "recover": "none",
        },
        bot_id="cmd-bot",
    )
    # Rewrite the bot's health script after import: it must fail.
    bot_dir = supervisor.get(bot_id).bot_dir
    (bot_dir / "health.py").write_text(
        "def check():\n    return (False, 'queue backlog')\n", encoding="utf-8"
    )
    assert supervisor.start(bot_id).get("ok")
    base = time.time()
    _drive(supervisor, bot_id, [base, base + 6, base + 11.5])
    state = supervisor.get(bot_id).health_state
    assert state["status"] == HEALTH_UNHEALTHY
    assert state["consecutive_failures"] == 1
    assert "backlog" in state["last_error"]


def test_probe_timeout_is_recorded_as_failure(tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={
            "kind": "command",
            "script": "health.py",
            "interval_seconds": 5,
            "timeout_seconds": 1,
            "failure_threshold": 1,
            "recover": "none",
        },
        bot_id="slow-bot",
    )
    bot_dir = supervisor.get(bot_id).bot_dir
    (bot_dir / "health.py").write_text(
        "import time\n\ndef check():\n    time.sleep(5.0)\n    return True\n",
        encoding="utf-8",
    )
    assert supervisor.start(bot_id).get("ok")
    # Launch a probe, then let REAL time cross its 1.0s deadline while the
    # check() thread is still sleeping — the monitor must record a timeout.
    monitor = supervisor._health_monitor
    base = time.time()
    monitor.tick_once(base)        # arms next_probe_at
    monitor.tick_once(base + 6)    # launches the probe (real deadline ~ +1s)
    time.sleep(1.4)
    monitor.tick_once(base + 12)   # drain: thread alive past its deadline
    state = supervisor.get(bot_id).health_state
    assert state["status"] == HEALTH_UNHEALTHY
    assert "timed out" in state["last_error"]
    assert state["consecutive_failures"] == 1


# --------------------------------------------------------------------- #
# set_health_enabled + manual probe API                                  #
# --------------------------------------------------------------------- #


def test_set_health_enabled_persists(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={"kind": "http", "url": f"{http_server}/good"},
    )
    result = supervisor.set_health_enabled(bot_id, False)
    assert result.get("ok")
    assert result["health"]["enabled"] is False
    document = json.loads(
        (supervisor.get(bot_id).bot_dir / "bot.json").read_text(encoding="utf-8")
    )
    assert document["health"]["enabled"] is False
    assert supervisor.set_health_enabled(bot_id, True).get("ok")
    # non-bool rejected
    assert not supervisor.set_health_enabled(bot_id, "yes").get("ok")


def test_set_health_enabled_requires_health_config(tmp_path):
    supervisor = make_supervisor(tmp_path)
    directory = make_bot_dir(tmp_path / "src", bot_id="plain-bot")
    assert supervisor.import_folder(directory).get("ok")
    result = supervisor.set_health_enabled("plain-bot", False)
    assert not result.get("ok")
    assert "no health config" in result["errors"][0]


def test_manual_probe_api(http_server, tmp_path):
    supervisor = make_supervisor(tmp_path)
    bot_id = import_health_bot(
        supervisor,
        tmp_path,
        health={"kind": "http", "url": f"{http_server}/good"},
    )
    result = supervisor.probe_health(bot_id)
    assert result["ok"] and result["healthy"] is True
    assert result["detail"] == "HTTP 200"
    assert result["elapsed_ms"] >= 0
    assert supervisor.get(bot_id).health_state["status"] == HEALTH_HEALTHY

    # A manual probe never triggers recovery even at/over the threshold.
    supervisor2 = make_supervisor(tmp_path / "second")
    bot2 = import_health_bot(
        supervisor2,
        tmp_path / "second",
        health={
            "kind": "http",
            "url": f"{http_server}/bad",
            "failure_threshold": 1,
            "recover": "restart",
        },
    )
    result2 = supervisor2.probe_health(bot2)
    assert result2["ok"] and result2["healthy"] is False
    assert supervisor2.get(bot2).health_state["recoveries"] == 0
    assert supervisor2.get(bot2).state == BotState.STOPPED  # was never started

    assert not supervisor.probe_health("ghost").get("ok")


def test_manual_probe_requires_health_config(tmp_path):
    supervisor = make_supervisor(tmp_path)
    directory = make_bot_dir(tmp_path / "src", bot_id="plain-bot")
    assert supervisor.import_folder(directory).get("ok")
    result = supervisor.probe_health("plain-bot")
    assert not result.get("ok")
    assert "no health config" in result["errors"][0]


# --------------------------------------------------------------------- #
# custom (community) registry sources                                    #
# --------------------------------------------------------------------- #


def test_registry_sources_store_roundtrip(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assert marketplace.load_registry_sources(data_dir) == []
    assert marketplace.resolve_registry_url(data_dir) == marketplace.DEFAULT_REGISTRY_URL

    added = marketplace.add_registry_source(data_dir, "  https://community.example/reg.json  ")
    assert added["ok"] and added["added"] is True
    # duplicate add is idempotent, not an error
    again = marketplace.add_registry_source(data_dir, "https://community.example/reg.json")
    assert again["ok"] and again["added"] is False

    assert marketplace.resolve_registry_url(data_dir) == "https://community.example/reg.json"
    assert marketplace.resolve_registry_url(data_dir, "https://explicit.example/r.json") == (
        "https://explicit.example/r.json"
    )

    bad = marketplace.add_registry_source(data_dir, "file:///etc/passwd")
    assert not bad["ok"] and "http/https" in bad["errors"][0]
    bad = marketplace.add_registry_source(data_dir, "not a url")
    assert not bad["ok"]

    removed = marketplace.remove_registry_source(data_dir, "https://community.example/reg.json")
    assert removed["ok"]
    missing = marketplace.remove_registry_source(data_dir, "https://community.example/reg.json")
    assert not missing["ok"]
    assert marketplace.load_registry_sources(data_dir) == []


def test_registry_sources_persist_across_instances(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    marketplace.add_registry_source(data_dir, "https://a.example/r.json")
    marketplace.add_registry_source(data_dir, "https://b.example/r.json")
    assert marketplace.load_registry_sources(data_dir) == [
        "https://a.example/r.json",
        "https://b.example/r.json",
    ]


def test_registry_sources_capped(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for index in range(marketplace.MAX_SOURCES):
        result = marketplace.add_registry_source(data_dir, f"https://s{index}.example/r.json")
        assert result["ok"]
    over = marketplace.add_registry_source(data_dir, "https://overflow.example/r.json")
    assert not over["ok"] and "max 20" in over["errors"][0]


def test_marketplace_fetch_prefers_custom_source(http_server, tmp_path):
    """host_api.marketplace_fetch() without a URL uses the saved source."""

    class _RegistryHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            payload = json.dumps(
                {
                    "bots": [
                        {
                            "id": "community-bot",
                            "name": "Community Bot",
                            "description": "from a custom registry",
                            "version": "1.0.0",
                            "url": f"{http_server}/community-bot.zip",
                        }
                    ]
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    registry_server = ThreadingHTTPServer(("127.0.0.1", 0), _RegistryHandler)
    import threading

    thread = threading.Thread(target=registry_server.serve_forever, daemon=True)
    thread.start()
    try:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        host_api.configure(data_dir)
        saved = host_api.add_registry_source(
            f"http://127.0.0.1:{registry_server.server_address[1]}/registry.json"
        )
        assert saved["ok"]
        result = host_api.marketplace_fetch()
        assert result["ok"], result
        assert result["count"] == 1
        assert result["bots"][0]["id"] == "community-bot"
        assert result["source"].startswith("http://127.0.0.1:")
    finally:
        registry_server.shutdown()
        registry_server.server_close()
        host_api.shutdown_all()


# --------------------------------------------------------------------- #
# CLI                                                                    #
# --------------------------------------------------------------------- #


def test_cli_health_and_registry_commands(tmp_path, capsys):
    from drs_host.cli import main

    data_dir = tmp_path / "data"
    bot_dir = make_bot_dir(
        tmp_path / "src",
        bot_id="hc-bot",
        code=LONG_RUNNING_MAIN,
        manifest={"health": {"kind": "http", "url": "http://127.0.0.1:9/health"}},
    )
    assert main(["--data-dir", str(data_dir), "import", str(bot_dir)]) == 0
    capsys.readouterr()  # drop the import result; each block below reads its own

    # health show
    assert main(["--data-dir", str(data_dir), "health", "hc-bot"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["kind"] == "http"
    assert payload["health_state"]["status"] == "unknown"

    # health --off / --on persist
    assert main(["--data-dir", str(data_dir), "health", "hc-bot", "--off"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["enabled"] is False
    assert main(["--data-dir", str(data_dir), "health", "hc-bot", "--on"]) == 0
    capsys.readouterr()

    # manual probe (dead port -> probe executes, reports unhealthy)
    assert main(["--data-dir", str(data_dir), "health-probe", "hc-bot"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["healthy"] is False

    # registry source commands
    assert main(["--data-dir", str(data_dir), "registry-list"]) == 0
    assert json.loads(capsys.readouterr().out)["sources"] == []
    assert main(
        ["--data-dir", str(data_dir), "registry-add", "https://community.example/r.json"]
    ) == 0
    capsys.readouterr()
    assert main(["--data-dir", str(data_dir), "registry-list"]) == 0
    assert json.loads(capsys.readouterr().out)["sources"] == [
        "https://community.example/r.json"
    ]
    assert main(
        ["--data-dir", str(data_dir), "registry-remove", "https://community.example/r.json"]
    ) == 0
    capsys.readouterr()
    # unknown bot id -> exit code 2
    assert main(["--data-dir", str(data_dir), "health", "ghost"]) == 2
