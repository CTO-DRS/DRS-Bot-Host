"""v1.2 feature tests: cron-like schedules, per-bot CPU accounting,
force-stop escalation, HTTP(S) bot imports (with GitHub URL rewriting)
and the start-time requirements policy (off / warn / enforce).
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from drs_host import host_api
from drs_host.manifest import validate_manifest
from drs_host.scheduler import BotScheduler, next_daily_start, within_daily_window
from drs_host.supervisor import BotState, Supervisor
from conftest import EXITING_MAIN, LONG_RUNNING_MAIN, make_bot_dir, make_bot_zip, wait_for

try:
    import resource

    HAS_THREAD_RUSAGE = hasattr(resource, "RUSAGE_THREAD")
except ImportError:  # pragma: no cover - non-Unix CI
    HAS_THREAD_RUSAGE = False

GHOST_PACKAGE = "drs-test-ghost-pkg"

CPU_BURN_MAIN = '''\
total = 0
for _ in range(3):
    for j in range(400_000):
        total += j * j
print("cpu-burn", total)
'''

IGNORES_STOP_MAIN = '''\
import time

# This bot never consults the host stop event on purpose (force-stop test).
while True:
    time.sleep(0.05)
'''


def make_supervisor(tmp_path) -> Supervisor:
    bots_root = tmp_path / "bots"
    bots_root.mkdir(parents=True, exist_ok=True)
    return Supervisor(bots_root)


# --------------------------------------------------------------------- #
# manifest: schedule validation                                          #
# --------------------------------------------------------------------- #

BASE_MANIFEST = {
    "id": "sched-bot",
    "name": "Sched Bot",
    "version": "1.0.0",
    "entrypoint": "main.py",
}


def test_manifest_accepts_interval_schedule():
    document = {
        **BASE_MANIFEST,
        "schedule": {"kind": "interval", "interval_seconds": 30, "run_seconds": 10},
    }
    manifest, errors = validate_manifest(document)
    assert errors == []
    assert manifest.schedule["kind"] == "interval"
    assert manifest.schedule["interval_seconds"] == 30.0
    assert manifest.schedule["run_seconds"] == 10.0
    assert manifest.schedule["enabled"] is True


def test_manifest_accepts_daily_schedule():
    document = {
        **BASE_MANIFEST,
        "schedule": {
            "kind": "daily",
            "time": "07:30",
            "duration_seconds": 600,
            "enabled": False,
        },
    }
    manifest, errors = validate_manifest(document)
    assert errors == []
    assert manifest.schedule["time"] == "07:30"
    assert manifest.schedule["duration_seconds"] == 600.0
    assert manifest.schedule["enabled"] is False


@pytest.mark.parametrize(
    "schedule,fragment",
    [
        ({"kind": "interval"}, "interval_seconds"),
        ({"kind": "hourly", "interval_seconds": 5}, "schedule.kind"),
        ({"kind": "daily", "time": "25:00"}, "schedule.time"),
        ({"kind": "daily"}, "schedule.time"),
        ({"kind": "interval", "interval_seconds": 5, "wat": 1}, "unknown key"),
        ({"kind": "interval", "interval_seconds": True}, "must be a number"),
    ],
)
def test_manifest_rejects_bad_schedules(schedule, fragment):
    document = {**BASE_MANIFEST, "schedule": schedule}
    manifest, errors = validate_manifest(document)
    assert manifest is None
    assert any(fragment in error for error in errors), errors


# --------------------------------------------------------------------- #
# daily window helpers (pure, clock-independent)                         #
# --------------------------------------------------------------------- #

def test_daily_window_membership():
    local = time.localtime()

    def at(hour, minute, second=0):
        return time.mktime(
            (local.tm_year, local.tm_mon, local.tm_mday, hour, minute, second, 0, 0, -1)
        )

    assert within_daily_window("09:00", 3600, at(9, 30))
    assert not within_daily_window("09:00", 3600, at(8, 0))
    assert not within_daily_window("09:00", 3600, at(10, 0, 1))
    # windows may wrap past midnight
    assert within_daily_window("23:50", 1200, at(23, 55))
    assert within_daily_window("23:50", 1200, at(0, 5))
    assert not within_daily_window("23:50", 1200, at(0, 15))


def test_next_daily_start():
    local = time.localtime()

    def at(hour, minute):
        return time.mktime(
            (local.tm_year, local.tm_mon, local.tm_mday, hour, minute, 0, 0, 0, -1)
        )

    nxt = next_daily_start("09:00", at(10, 0))
    assert nxt > at(10, 0)
    rounded = time.localtime(nxt)
    assert (rounded.tm_hour, rounded.tm_min) == (9, 0)


# --------------------------------------------------------------------- #
# scheduler integration (interval kind, short real intervals)            #
# --------------------------------------------------------------------- #

def test_scheduler_interval_starts_and_stops(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            bot_id="sched-bot",
            code=LONG_RUNNING_MAIN,
            manifest={
                "schedule": {
                    "kind": "interval",
                    "interval_seconds": 2.0,
                    "run_seconds": 1.0,
                }
            },
        )
    )
    assert not supervisor.scheduler_running()  # Supervisor() alone does not start it
    scheduler = BotScheduler(supervisor, tick_seconds=0.1)
    scheduler.start()
    try:
        assert wait_for(
            lambda: supervisor.status("sched-bot").get("state") == BotState.RUNNING,
            timeout=5,
        )
        assert wait_for(
            lambda: supervisor.status("sched-bot").get("state")
            in (BotState.STOPPED, BotState.COMPLETED),
            timeout=5,
        )
        stopped = supervisor.status("sched-bot")
        assert stopped["run_count"] == 1
        assert stopped["schedule"]["interval_seconds"] == 2.0
        # the next window opens automatically
        assert wait_for(
            lambda: supervisor.status("sched-bot").get("run_count", 0) >= 2,
            timeout=8,
        )
        assert wait_for(
            lambda: supervisor.status("sched-bot").get("state") == BotState.RUNNING,
            timeout=5,
        )
    finally:
        scheduler.shutdown()
        supervisor.shutdown_all()


def test_disable_schedule_leaves_manual_control(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            bot_id="sched-bot",
            code=LONG_RUNNING_MAIN,
            manifest={
                "schedule": {
                    "kind": "interval",
                    "interval_seconds": 2.0,
                    "run_seconds": 1.0,
                }
            },
        )
    )
    scheduler = BotScheduler(supervisor, tick_seconds=0.1)
    scheduler.start()
    try:
        assert wait_for(
            lambda: supervisor.status("sched-bot").get("state") == BotState.RUNNING,
            timeout=5,
        )
        result = supervisor.set_schedule_enabled("sched-bot", False)
        assert result["ok"]
        assert result["schedule"]["enabled"] is False
        # persisted to bot.json
        stored = json.loads(
            (supervisor.bots_root / "sched-bot" / "bot.json").read_text(encoding="utf-8")
        )
        assert stored["schedule"]["enabled"] is False

        # the active run is NOT killed by disabling; it keeps running...
        time.sleep(1.2)
        running = supervisor.status("sched-bot")
        assert running["state"] == BotState.RUNNING
        # ...until the user stops it manually
        assert supervisor.stop("sched-bot")["ok"]
        # and the scheduler never starts it again
        time.sleep(2.0)
        final = supervisor.status("sched-bot")
        assert final["state"] == BotState.STOPPED
        assert final["run_count"] == 1
    finally:
        scheduler.shutdown()
        supervisor.shutdown_all()


def test_set_schedule_enabled_validation(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src", bot_id="plain-bot"))
    assert not supervisor.set_schedule_enabled("plain-bot", True)["ok"]
    assert not supervisor.set_schedule_enabled("ghost", True)["ok"]
    assert not supervisor.set_schedule_enabled("plain-bot", "yes")["ok"]


# --------------------------------------------------------------------- #
# per-bot CPU accounting (Linux/Android only)                            #
# --------------------------------------------------------------------- #

@pytest.mark.skipif(not HAS_THREAD_RUSAGE, reason="RUSAGE_THREAD unavailable")
def test_cpu_accounting_per_run(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", bot_id="cpu-bot", code=CPU_BURN_MAIN)
    )
    fresh = supervisor.status("cpu-bot")
    assert fresh["cpu_seconds"] == 0.0
    assert fresh["last_cpu_seconds"] is None
    assert fresh["detached"] is False

    assert supervisor.start("cpu-bot")["ok"]
    assert wait_for(
        lambda: supervisor.status("cpu-bot").get("state") == BotState.COMPLETED,
        timeout=15,
    )
    final = supervisor.status("cpu-bot")
    assert final["cpu_seconds"] > 0.0
    assert final["last_cpu_seconds"] > 0.0
    assert supervisor.host_stats()["cpu_seconds"] > 0.0


# --------------------------------------------------------------------- #
# force-stop escalation                                                  #
# --------------------------------------------------------------------- #

def test_stop_warns_then_force_stop_detaches(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", bot_id="stubborn-bot", code=IGNORES_STOP_MAIN)
    )
    assert supervisor.start("stubborn-bot")["ok"]
    assert wait_for(
        lambda: supervisor.status("stubborn-bot").get("state") == BotState.RUNNING,
        timeout=5,
    )

    stopped = supervisor.stop("stubborn-bot", timeout=0.3)
    assert stopped["ok"] and stopped["state"] == BotState.STOPPING
    assert "force_stop" in stopped["warning"]

    forced = supervisor.force_stop("stubborn-bot", grace=0.3)
    assert forced["ok"]
    assert forced["state"] == BotState.FORCE_STOPPED
    assert "detached" in forced["warning"]

    status = supervisor.status("stubborn-bot")
    assert status["state"] == BotState.FORCE_STOPPED
    assert status["detached"] is True
    assert status["state"] in BotState.TERMINAL

    # a zombie exit must not corrupt the record; re-starting is allowed
    restarted = supervisor.start("stubborn-bot")
    assert restarted["ok"]
    assert "may still be running" in restarted.get("warning", "")
    assert wait_for(
        lambda: supervisor.status("stubborn-bot").get("state") == BotState.RUNNING,
        timeout=5,
    )
    supervisor.force_stop("stubborn-bot", grace=0.3)
    supervisor.shutdown_all()


def test_force_stop_on_terminal_bot_is_a_noop(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src", bot_id="quiet-bot"))
    result = supervisor.force_stop("quiet-bot")
    assert result["ok"] and result["state"] == BotState.STOPPED
    supervisor.shutdown_all()


# --------------------------------------------------------------------- #
# requirements policy                                                    #
# --------------------------------------------------------------------- #

def test_requirements_policies(tmp_path):
    host_api.configure(tmp_path / "data")
    host_api.import_folder(
        make_bot_dir(
            tmp_path / "src",
            bot_id="req-bot",
            code=EXITING_MAIN,
            manifest={"requirements": [GHOST_PACKAGE]},
        )
    )
    assert host_api.requirements_policy() == "warn"
    check = host_api.check_requirements("req-bot")
    assert check["ok"] and GHOST_PACKAGE in check["missing"]

    host_api.set_requirements_policy("enforce")
    blocked = host_api.start_bot("req-bot")
    assert not blocked["ok"]
    assert any(GHOST_PACKAGE in error for error in blocked["errors"])
    assert host_api.bot_status("req-bot")["state"] == BotState.STOPPED

    host_api.set_requirements_policy("warn")
    assert host_api.start_bot("req-bot")["ok"]
    assert wait_for(
        lambda: host_api.bot_status("req-bot").get("state") == BotState.COMPLETED
    )
    warnings = [
        record
        for record in host_api.recent_logs("req-bot", 200)
        if "missing requirements" in record["message"]
    ]
    assert len(warnings) == 1 and GHOST_PACKAGE in warnings[0]["message"]

    host_api.set_requirements_policy("off")
    assert host_api.start_bot("req-bot")["ok"]
    assert wait_for(
        lambda: host_api.bot_status("req-bot").get("state") == BotState.COMPLETED
    )
    assert len(host_api.recent_logs("req-bot", 500)) >= len(warnings)
    warnings_after = [
        record
        for record in host_api.recent_logs("req-bot", 500)
        if "missing requirements" in record["message"]
    ]
    assert len(warnings_after) == 1  # no new warning under "off"

    bad = host_api.set_requirements_policy("bogus")
    assert not bad["ok"]
    host_api.set_requirements_policy("warn")  # restore the default


# --------------------------------------------------------------------- #
# URL imports                                                            #
# --------------------------------------------------------------------- #

def test_github_zip_url_rewrites():
    transform = host_api.__dict__  # noqa: F841 - readability only
    from drs_host.downloader import github_zip_url

    assert github_zip_url("https://github.com/owner/repo") == (
        "https://api.github.com/repos/owner/repo/zipball"
    )
    assert github_zip_url("https://github.com/owner/repo.git") == (
        "https://api.github.com/repos/owner/repo/zipball"
    )
    assert github_zip_url("https://github.com/owner/repo/tree/dev") == (
        "https://codeload.github.com/owner/repo/zip/refs/heads/dev"
    )
    assert github_zip_url(
        "https://github.com/owner/repo/archive/refs/heads/main.zip"
    ) == "https://github.com/owner/repo/archive/refs/heads/main.zip"
    assert github_zip_url("https://example.com/bots/x.zip") == (
        "https://example.com/bots/x.zip"
    )
    assert github_zip_url("  https://github.com/owner/repo  ") == (
        "https://api.github.com/repos/owner/repo/zipball"
    )


@pytest.fixture()
def zip_server(tmp_path):
    zip_path = make_bot_zip(tmp_path, bot_id="url-bot")
    payload = zip_path.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            if self.path == "/bot.zip":
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *args):  # silence the test log
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    server.shutdown()
    server.server_close()


def test_import_url_success(zip_server):
    base_url, tmp_path = zip_server
    host_api.configure(tmp_path / "data")
    result = host_api.import_bot_url(f"{base_url}/bot.zip")
    assert result["ok"], result
    assert result["bot_id"] == "url-bot"
    assert host_api.bot_status("url-bot")["ok"]
    # the temporary download is cleaned up
    downloads = tmp_path / "data" / "downloads"
    assert downloads.is_dir() and list(downloads.iterdir()) == []


def test_import_url_http_404(zip_server):
    base_url, tmp_path = zip_server
    host_api.configure(tmp_path / "data")
    result = host_api.import_bot_url(f"{base_url}/missing.zip")
    assert not result["ok"]
    assert any("404" in error for error in result["errors"])


def test_import_url_size_cap(zip_server):
    base_url, tmp_path = zip_server
    host_api.configure(tmp_path / "data", limits={"max_zip_bytes": 64})
    result = host_api.import_bot_url(f"{base_url}/bot.zip")
    assert not result["ok"]
    assert any("large" in error.lower() or "size" in error.lower() for error in result["errors"])


def test_import_url_rejects_non_http():
    import tempfile
    from pathlib import Path

    from drs_host.downloader import download_zip

    with tempfile.TemporaryDirectory() as scratch:
        result = download_zip("ftp://example.com/bot.zip", Path(scratch), max_bytes=1024)
        assert not result["ok"]
        assert any("http" in error.lower() for error in result["errors"])


def test_host_stats_report_process_footprint(zip_server):
    base_url, tmp_path = zip_server
    host_api.configure(tmp_path / "data")
    stats = host_api.host_stats()
    assert "process_rss_bytes" in stats
    assert stats["process_rss_bytes"] > 0
    assert "scheduled" in stats
