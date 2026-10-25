"""Supervisor tests: lifecycle, restart policies, backoff, stopping."""

import io
import time

from drs_host.supervisor import Supervisor, BotState
from drs_host.streams import ThreadAwareStream
from conftest import (
    EXITING_MAIN,
    LONG_RUNNING_MAIN,
    CRASHING_MAIN,
    PRINT_MAIN,
    make_bot_dir,
    wait_for,
)

FAST_RESTART = {
    "restart": {
        "policy": "on_failure",
        "max_restarts": 2,
        "backoff_seconds": 0.01,
        "backoff_multiplier": 1.0,
    }
}


def make_supervisor(tmp_path, **kwargs) -> Supervisor:
    bots_root = tmp_path / "bots"
    bots_root.mkdir(parents=True, exist_ok=True)
    return Supervisor(bots_root, **kwargs)


def test_import_registers_bot(tmp_path):
    supervisor = make_supervisor(tmp_path)
    result = supervisor.import_folder(make_bot_dir(tmp_path / "src"))
    assert result["ok"], result
    bots = supervisor.list_bots()
    assert len(bots) == 1
    assert bots[0]["id"] == "echo-bot"
    assert bots[0]["state"] == BotState.STOPPED


def test_clean_run_completes(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src"))
    assert supervisor.start("echo-bot")["ok"]
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
    )
    logs = supervisor.recent_logs("echo-bot")
    assert any("tick 2" in record["message"] for record in logs)


def test_crash_then_exhausted_restarts(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", code=CRASHING_MAIN, manifest=FAST_RESTART)
    )
    supervisor.start("echo-bot")
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.FAILED
    )
    status = supervisor.status("echo-bot")
    assert status["restarts"] == 2
    assert "boom" in (status["last_error"] or "")


def test_policy_never_fails_fast(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            code=CRASHING_MAIN,
            manifest={"restart": {"policy": "never"}},
        )
    )
    supervisor.start("echo-bot")
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.FAILED
    )
    assert supervisor.status("echo-bot")["restarts"] == 0


def test_policy_always_restarts_clean_exits(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            code=EXITING_MAIN,
            manifest={
                "restart": {
                    "policy": "always",
                    "max_restarts": 2,
                    "backoff_seconds": 0.01,
                    "backoff_multiplier": 1.0,
                }
            },
        )
    )
    supervisor.start("echo-bot")
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
        and supervisor.status("echo-bot").get("restarts") == 2
    )


def test_stop_running_bot(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", code=LONG_RUNNING_MAIN)
    )
    supervisor.start("echo-bot")
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.RUNNING
    )
    result = supervisor.stop("echo-bot")
    assert result["ok"], result
    assert result["state"] == BotState.STOPPED
    assert supervisor.status("echo-bot")["state"] == BotState.STOPPED


def test_stop_without_backoff_restart(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            code=CRASHING_MAIN,
            manifest={
                "restart": {
                    "policy": "on_failure",
                    "max_restarts": 50,
                    "backoff_seconds": 0.05,
                    "backoff_multiplier": 1.0,
                }
            },
        )
    )
    supervisor.start("echo-bot")
    assert wait_for(lambda: supervisor.status("echo-bot").get("restarts") >= 1)
    assert supervisor.stop("echo-bot")["ok"]
    time.sleep(0.3)
    status = supervisor.status("echo-bot")
    assert status["state"] in (BotState.STOPPED, BotState.STOPPING)
    assert status["restarts"] == 0


def test_start_twice_rejected(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", code=LONG_RUNNING_MAIN)
    )
    assert supervisor.start("echo-bot")["ok"]
    result = supervisor.start("echo-bot")
    assert not result["ok"]
    assert any("already running" in e for e in result["errors"])
    supervisor.stop("echo-bot")


def test_unknown_bot_rejected(tmp_path):
    supervisor = make_supervisor(tmp_path)
    for call in (
        supervisor.start("ghost"),
        supervisor.stop("ghost"),
        supervisor.remove("ghost"),
        supervisor.status("ghost"),
    ):
        assert not call["ok"]
        assert any("unknown bot id" in e for e in call["errors"])


def test_remove_requires_terminal_state(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", code=LONG_RUNNING_MAIN)
    )
    supervisor.start("echo-bot")
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.RUNNING
    )
    result = supervisor.remove("echo-bot")
    assert not result["ok"]
    assert any("stop it before removing" in e for e in result["errors"])
    supervisor.stop("echo-bot")
    assert supervisor.remove("echo-bot")["ok"]
    assert supervisor.list_bots() == []


def test_discover_installed(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src"))
    revived = Supervisor(tmp_path / "bots")
    assert revived.discover_installed() == 1
    assert revived.status("echo-bot")["ok"]
    assert revived.status("echo-bot")["state"] == BotState.STOPPED


def test_print_capture_via_stream_hub(tmp_path):
    fallback = io.StringIO()
    supervisor = make_supervisor(
        tmp_path, stream_hub=ThreadAwareStream(fallback)
    )
    supervisor.import_folder(make_bot_dir(tmp_path / "src", code=PRINT_MAIN))
    supervisor.start("echo-bot")
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
    )
    logs = supervisor.recent_logs("echo-bot")
    printed = [r for r in logs if "hello-from-print" in r["message"]]
    sdk_logged = [r for r in logs if "hello-from-sdk" in r["message"]]
    assert printed and printed[0]["level"] == "INFO"
    assert sdk_logged
    assert "hello-from-print" not in fallback.getvalue()


def test_min_python_guard(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            code=LONG_RUNNING_MAIN,
            manifest={"min_python": "3.99"},
        )
    )
    result = supervisor.start("echo-bot")
    assert not result["ok"]
    assert any("requires Python" in e for e in result["errors"])


def test_autostart_bots(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(
            tmp_path / "src",
            code=EXITING_MAIN,
            manifest={"auto_start": True},
        )
    )
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src2", bot_id="manual-bot")
    )
    result = supervisor.start_autostart_bots()
    assert result["ok"]
    assert result["started"] == ["echo-bot"]
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
    )
    assert supervisor.status("manual-bot")["state"] == BotState.STOPPED
