"""host_api facade tests (the exact surface the Android bridge calls)."""

from drs_host import host_api
from conftest import LONG_RUNNING_MAIN, make_bot_dir, make_bot_zip, wait_for


def setup_function(function):
    # isolate global state between tests
    host_api._supervisor = None
    host_api._available_packages = None


def test_configure_creates_storage(tmp_path):
    result = host_api.configure(tmp_path / "data")
    assert result["ok"]
    assert (tmp_path / "data" / "bots").is_dir()
    info = host_api.runtime_info()
    assert info["ok"]
    assert info["bots"] == 0
    assert info["drs_host"] == "1.2.0"


def test_configure_requires_argument():
    try:
        host_api.list_bots()
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_full_lifecycle(tmp_path):
    host_api.configure(tmp_path / "data")
    imported = host_api.import_zip(make_bot_zip(tmp_path / "z"))
    assert imported["ok"], imported
    bot_id = imported["bot_id"]

    assert len(host_api.list_bots()) == 1

    started = host_api.start_bot(bot_id)
    assert started["ok"], started
    assert wait_for(
        lambda: host_api.bot_status(bot_id).get("state")
        in ("RUNNING", "COMPLETED", "STOPPED")
    )
    stopped = host_api.stop_bot(bot_id)
    assert stopped["ok"], stopped
    assert host_api.bot_status(bot_id)["state"] == "STOPPED"

    logs = host_api.recent_logs(bot_id, limit=100)
    assert logs and all({"ts", "level", "source", "message"} <= set(r) for r in logs)

    assert host_api.restart_bot(bot_id)["ok"]
    assert wait_for(
        lambda: host_api.bot_status(bot_id).get("state") in ("RUNNING", "COMPLETED")
    )
    host_api.stop_bot(bot_id)
    assert host_api.remove_bot(bot_id)["ok"]
    assert host_api.list_bots() == []


def test_unknown_id_errors(tmp_path):
    host_api.configure(tmp_path / "data")
    status = host_api.bot_status("ghost")
    assert not status["ok"]
    assert any("unknown bot id" in e for e in status["errors"])
    assert host_api.recent_logs("ghost") == []


def test_requirements_check(tmp_path):
    host_api.configure(tmp_path / "data")
    host_api.import_folder(
        make_bot_dir(
            tmp_path / "src",
            code=LONG_RUNNING_MAIN,
            manifest={"requirements": ["requests", "drs-test-ghost>=1.0"]},
        )
    )
    unknown = host_api.check_requirements("echo-bot")
    assert unknown["known"] is False

    host_api.set_available_packages(["requests", "aiohttp"])
    result = host_api.check_requirements("echo-bot")
    assert result["known"] is True
    assert result["missing"] == ["drs-test-ghost>=1.0"]
    assert host_api.available_packages() == ["aiohttp", "requests"]


def test_folder_import_and_autostart(tmp_path):
    host_api.configure(tmp_path / "data")
    imported = host_api.import_folder(
        make_bot_dir(
            tmp_path / "src",
            manifest={"auto_start": True},
        )
    )
    assert imported["ok"], imported
    started = host_api.start_autostart_bots()
    assert started["ok"]
    assert started["started"] == ["echo-bot"]
    host_api.stop_bot("echo-bot")
    host_api.shutdown_all()
