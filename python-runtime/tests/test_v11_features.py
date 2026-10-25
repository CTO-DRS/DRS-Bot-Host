"""v1.1 feature tests: host stats, uptime/run-count, log export,
runtime config editing and the bot scaffolder (incl. an end-to-end
scaffold -> import -> reconfigure -> run -> stop cycle).
"""

import json
import zipfile
from pathlib import Path

from drs_host import host_api
from drs_host.manifest import validate_manifest
from drs_host.supervisor import Supervisor, BotState
from conftest import EXITING_MAIN, LONG_RUNNING_MAIN, make_bot_dir, wait_for


def make_supervisor(tmp_path) -> Supervisor:
    bots_root = tmp_path / "bots"
    bots_root.mkdir(parents=True, exist_ok=True)
    return Supervisor(bots_root)


# --------------------------------------------------------------------- #
# run_count + uptime                                                     #
# --------------------------------------------------------------------- #

def test_status_reports_run_count_and_uptime(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src", code=EXITING_MAIN))
    fresh = supervisor.status("echo-bot")
    assert fresh["run_count"] == 0
    assert fresh["uptime_seconds"] is None

    assert supervisor.start("echo-bot")["ok"]
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
    )
    final = supervisor.status("echo-bot")
    assert final["run_count"] == 1
    uptime = final["uptime_seconds"]
    assert uptime is not None and uptime >= 0.0


def test_run_count_increments_across_runs(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src", code=EXITING_MAIN))
    for _ in range(2):
        assert supervisor.start("echo-bot")["ok"]
        assert wait_for(
            lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
        )
    assert supervisor.status("echo-bot")["run_count"] == 2


# --------------------------------------------------------------------- #
# host_stats                                                             #
# --------------------------------------------------------------------- #

def test_host_stats_aggregates_states(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src-a", bot_id="bot-a", code=EXITING_MAIN)
    )
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src-b", bot_id="bot-b", code=LONG_RUNNING_MAIN)
    )
    stats = supervisor.host_stats()
    assert stats["ok"] and stats["total"] == 2
    assert stats["running"] == 0 and stats["by_state"].get("STOPPED") == 2

    assert supervisor.start("bot-a")["ok"]
    assert supervisor.start("bot-b")["ok"]
    assert wait_for(
        lambda: supervisor.status("bot-a").get("state") == BotState.COMPLETED
    )
    stats = supervisor.host_stats()
    assert stats["running"] == 1          # bot-b still running
    assert stats["completed"] == 1
    assert stats["runs"] == 2

    supervisor.shutdown_all()
    stats = supervisor.host_stats()
    assert stats["running"] == 0


def test_host_stats_via_host_api_has_uptime(tmp_path, data_dir):
    host_api.configure(data_dir)
    stats = host_api.host_stats()
    assert stats["ok"]
    assert stats["uptime_seconds"] >= 0.0
    assert stats["total"] == 0


# --------------------------------------------------------------------- #
# export_logs                                                            #
# --------------------------------------------------------------------- #

def test_export_logs_unknown_bot(tmp_path):
    supervisor = make_supervisor(tmp_path)
    result = supervisor.export_logs("ghost")
    assert not result["ok"]
    assert "unknown bot id" in result["errors"][0]


def test_export_logs_produces_zip_with_jsonl(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(
        make_bot_dir(tmp_path / "src", code=LONG_RUNNING_MAIN)
    )
    assert supervisor.start("echo-bot")["ok"]
    assert wait_for(
        lambda: any("long tick" in r["message"] for r in supervisor.recent_logs("echo-bot"))
    )
    supervisor.stop("echo-bot")

    result = supervisor.export_logs("echo-bot")
    assert result["ok"], result
    archive_path = Path(result["path"])
    assert archive_path.exists()
    assert result["bytes"] > 0
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert "runtime.jsonl" in names
        payload = archive.read("runtime.jsonl").decode("utf-8")
        assert "long tick" in payload
    assert result["files"] >= 1


# --------------------------------------------------------------------- #
# set_config                                                             #
# --------------------------------------------------------------------- #

def test_set_config_rejects_non_objects(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src"))
    for bad in ([1, 2], "not json {", 42):
        result = supervisor.set_config("echo-bot", bad)
        assert not result["ok"], bad
    assert not supervisor.set_config("ghost", {"a": 1})["ok"]


def test_set_config_updates_manifest_and_status(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src"))
    result = supervisor.set_config("echo-bot", {"interval": 1.5, "tag": "x"})
    assert result["ok"], result

    status = supervisor.status("echo-bot")
    assert status["config"] == {"interval": 1.5, "tag": "x"}

    on_disk = json.loads(
        (tmp_path / "bots" / "echo-bot" / "bot.json").read_text(encoding="utf-8")
    )
    assert on_disk["config"]["interval"] == 1.5

    # New config is injected into the run context on the next launch.
    assert supervisor.start("echo-bot")["ok"]
    assert wait_for(
        lambda: supervisor.status("echo-bot").get("state") == BotState.COMPLETED
    )
    bot = supervisor.get("echo-bot")
    assert bot.ctx.config["tag"] == "x"


def test_set_config_accepts_json_string(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.import_folder(make_bot_dir(tmp_path / "src"))
    result = supervisor.set_config("echo-bot", '{"k": "v"}')
    assert result["ok"], result
    assert supervisor.status("echo-bot")["config"] == {"k": "v"}


# --------------------------------------------------------------------- #
# scaffold                                                               #
# --------------------------------------------------------------------- #

def test_scaffold_rejects_bad_names(tmp_path):
    assert not host_api.scaffold_bot("", str(tmp_path))["ok"]
    assert not host_api.scaffold_bot("!!!", str(tmp_path))["ok"]

    # Valid once, then the second call hits the existing-target guard.
    first = host_api.scaffold_bot("My Demo Bot", str(tmp_path))
    assert first["ok"], first
    again = host_api.scaffold_bot("My Demo Bot", str(tmp_path))
    assert not again["ok"]
    assert "already exists" in again["errors"][0]


def test_scaffold_output_is_valid_and_importable(tmp_path):
    result = host_api.scaffold_bot("Ticker Bot", str(tmp_path))
    assert result["ok"], result
    folder = Path(result["path"])
    assert (folder / "bot.json").is_file()
    assert (folder / "main.py").is_file()

    document = json.loads((folder / "bot.json").read_text(encoding="utf-8"))
    validated, errors = validate_manifest(document)
    assert validated is not None, errors
    assert validated.id == "ticker-bot"

    supervisor = make_supervisor(tmp_path / "host")
    imported = supervisor.import_folder(folder)
    assert imported["ok"], imported

    # Reconfigure to a fast interval, then run end-to-end.
    assert supervisor.set_config(
        "ticker-bot", {"interval_seconds": 0.05, "message": "hello from Ticker Bot"}
    )["ok"]
    assert supervisor.start("ticker-bot")["ok"]
    assert wait_for(
        lambda: any(
            "hello from Ticker Bot" in r["message"]
            for r in supervisor.recent_logs("ticker-bot")
        )
    )
    assert supervisor.stop("ticker-bot")["ok"]
    assert supervisor.status("ticker-bot")["state"] == BotState.STOPPED
    assert supervisor.status("ticker-bot")["run_count"] == 1
