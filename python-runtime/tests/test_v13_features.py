"""v1.3 feature tests: skills, on-device installer, web status, process isolation."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import EXITING_MAIN, LONG_RUNNING_MAIN, make_bot_dir, wait_for

from drs_host import host_api, installer, skills
from drs_host.manifest import validate_manifest
from drs_host.supervisor import Supervisor
from drs_host import isolation as isolation_mod


# --------------------------------------------------------------------- #
# Skills                                                                 #
# --------------------------------------------------------------------- #


def test_skill_catalogue_is_populated_and_unique():
    catalogue = skills.list_skills()
    keys = [item["key"] for item in catalogue]
    assert len(keys) >= 7
    assert len(keys) == len(set(keys))
    for item in catalogue:
        assert item["title"] and item["description"]
        assert isinstance(item["requirements"], list)
        assert isinstance(item["config"], dict)


def test_scaffold_every_skill_produces_valid_manifest(tmp_path):
    for item in skills.list_skills():
        result = skills.scaffold_skill(item["key"], "Skill " + item["key"], tmp_path)
        assert result["ok"], (item["key"], result)
        document = json.loads((Path(result["path"]) / "bot.json").read_text())
        manifest, errors = validate_manifest(document)
        assert manifest is not None, (item["key"], errors)
        assert manifest.id == skills.slugify("Skill " + item["key"])
        for written in result["files"]:
            assert (Path(result["path"]) / written).is_file()


def test_scaffold_scheduler_skill_carries_schedule(tmp_path):
    result = skills.scaffold_skill("scheduler-cron", "Cron Demo", tmp_path)
    assert result["ok"]
    document = json.loads((Path(result["path"]) / "bot.json").read_text())
    assert document["schedule"]["kind"] == "interval"
    assert document["schedule"]["enabled"] is True


def test_scaffold_telegram_skill_declares_requirement(tmp_path):
    result = skills.scaffold_skill("telegram-echo", "TG Echo", tmp_path)
    assert result["ok"]
    document = json.loads((Path(result["path"]) / "bot.json").read_text())
    assert "python-telegram-bot" in document["requirements"]
    assert (Path(result["path"]) / "requirements.txt").is_file()


def test_scaffold_skill_rejects_unknown_and_duplicates(tmp_path):
    unknown = skills.scaffold_skill("no-such-skill", "X Bot", tmp_path)
    assert not unknown["ok"] and "unknown skill" in unknown["errors"][0]
    first = skills.scaffold_skill("echo", "Dup Bot", tmp_path)
    assert first["ok"]
    second = skills.scaffold_skill("echo", "Dup Bot", tmp_path)
    assert not second["ok"] and "already exists" in second["errors"][0]


def test_host_api_skills_endpoints(data_dir):
    host_api.configure(data_dir)
    catalogue = host_api.list_skills()
    assert any(item["key"] == "http-poller" for item in catalogue)
    result = host_api.scaffold_skill("echo", "API Echo", data_dir / "out")
    assert result["ok"] and (Path(result["path"]) / "main.py").is_file()


# --------------------------------------------------------------------- #
# Installer                                                              #
# --------------------------------------------------------------------- #

MICRO_PKG_SETUP = """\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "drs-micropkg"
version = "0.1.0"
description = "micro package for drs_host installer tests"

[tool.setuptools]
packages = ["drs_micropkg"]
"""

MICRO_PKG_MODULE = """\
MARKER = "drs-micropkg-installed-ok"
VERSION = "0.1.0"
"""


@pytest.fixture(scope="module")
def micro_pkg_wheelhouse(tmp_path_factory):
    """Build a tiny wheel locally so the pip install is offline-deterministic."""
    source = tmp_path_factory.mktemp("micropkg")
    (source / "pyproject.toml").write_text(MICRO_PKG_SETUP, encoding="utf-8")
    package_dir = source / "drs_micropkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(MICRO_PKG_MODULE, encoding="utf-8")
    house = tmp_path_factory.mktemp("wheelhouse")
    completed = subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel",
            "--no-deps", "--no-build-isolation", "-w", str(house), str(source),
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    wheels = list(house.glob("*.whl"))
    assert wheels, "wheel build produced no artifacts"
    return house


def test_pip_probe_true_on_desktop():
    assert installer.pip_runtime_available() is True
    assert host_api.pip_available() is True


def test_collector_rejects_urls_options_and_local_paths(tmp_path):
    bot_dir = tmp_path / "b"
    bot_dir.mkdir()
    (bot_dir / "requirements.txt").write_text(
        "# comment line\n"
        "six==1.16.0\n"
        "https://example.com/x.zip\n"
        "git+https://github.com/o/r\n"
        "-r other.txt\n"
        "-e .\n"
        "/etc/passwd\n"
        "!!!not-a-requirement!!!\n"
        "pytest>=8\n",
        encoding="utf-8",
    )
    merged, errors = installer.collect_requirements(bot_dir, ["six"])
    assert merged == ["six", "six==1.16.0", "pytest>=8"]
    assert len(errors) == 6
    assert any("forbidden" in e for e in errors)
    assert any("unparsable" in e for e in errors)


def test_real_pip_install_into_bot_site_dir(tmp_path, micro_pkg_wheelhouse):
    result = installer.install_requirements(
        "installer-bot",
        tmp_path / "botdir",
        tmp_path / "data",
        ["drs-micropkg==0.1.0"],
        timeout=120,
        find_links=str(micro_pkg_wheelhouse),
    )
    assert result["ok"], result
    target = Path(result["target"])
    assert (target / "drs_micropkg" / "__init__.py").is_file()
    assert result["installed"] == ["drs-micropkg==0.1.0"]


def test_site_dir_cleanup_on_remove(tmp_path, micro_pkg_wheelhouse):
    supervisor = Supervisor(tmp_path / "bots")
    bot_dir = make_bot_dir(tmp_path / "src", bot_id="cleanup-bot")
    imported = supervisor.import_folder(bot_dir)
    assert imported["ok"]
    installed = installer.install_requirements(
        "cleanup-bot",
        bot_dir,
        tmp_path,
        ["drs-micropkg==0.1.0"],
        timeout=120,
        find_links=str(micro_pkg_wheelhouse),
    )
    assert installed["ok"]
    assert installer.bot_site_dir(tmp_path, "cleanup-bot").is_dir()
    removed = supervisor.remove("cleanup-bot")
    assert removed["ok"]
    assert not installer.bot_site_dir(tmp_path, "cleanup-bot").exists()


def test_installed_packages_importable_during_bot_run(tmp_path, micro_pkg_wheelhouse):
    """Full wiring: install → run → bot imports from its own site dir."""
    data_dir = tmp_path / "host-data"
    host_api.configure(data_dir)
    try:
        bot_dir = make_bot_dir(
            tmp_path / "src",
            bot_id="site-bot",
            code=(
                "import drs_micropkg\n"
                "print('WIRING-' + drs_micropkg.MARKER)\n"
            ),
        )
        imported = host_api.import_folder(str(bot_dir))
        assert imported["ok"]
        installed = installer.install_requirements(
            "site-bot", bot_dir, data_dir, ["drs-micropkg==0.1.0"],
            timeout=120, find_links=str(micro_pkg_wheelhouse),
        )
        assert installed["ok"]
        assert host_api.start_bot("site-bot")["ok"]
        assert wait_for(
            lambda: host_api.bot_status("site-bot").get("state")
            in ("COMPLETED", "FAILED")
        ), "bot did not finish"
        status = host_api.bot_status("site-bot")
        assert status["state"] == "COMPLETED", status.get("last_error")
        messages = [r["message"] for r in host_api.recent_logs("site-bot", 100)]
        assert any(
            "WIRING-drs-micropkg-installed-ok" in m for m in messages
        ), messages
    finally:
        host_api.web_status_stop()
        host_api.shutdown_all()


# --------------------------------------------------------------------- #
# Web status page                                                        #
# --------------------------------------------------------------------- #


@pytest.fixture()
def configured_host(data_dir):
    host_api.configure(data_dir)
    yield data_dir
    host_api.web_status_stop()
    host_api.shutdown_all()


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def test_web_status_serves_html_and_json(configured_host, tmp_path):
    bot_dir = make_bot_dir(tmp_path / "src", bot_id="web-bot", code=EXITING_MAIN)
    assert host_api.import_folder(str(bot_dir))["ok"]
    started = host_api.web_status_start(port=0)
    assert started["ok"] and started["port"] > 0
    base = f"http://127.0.0.1:{started['port']}"

    code, html = _http_get(base + "/")
    assert code == 200 and "DRS Bot Host" in html and "web-bot" in html

    code, body = _http_get(base + "/api/status")
    document = json.loads(body)
    assert code == 200 and document["ok"] is True
    ids = [bot["id"] for bot in document["bots"]]
    assert "web-bot" in ids

    code, body = _http_get(base + "/api/bots/web-bot/logs?limit=10")
    assert code == 200 and json.loads(body)["id"] == "web-bot"

    code, _ = _http_get(base + "/nope")
    assert code == 404

    info = host_api.web_status_info()
    assert info["running"] and info["port"] == started["port"]


def test_web_status_token_protection(configured_host):
    started = host_api.web_status_start(port=0, token="s3cret")
    assert started["ok"]
    base = f"http://127.0.0.1:{started['port']}"

    code, _ = _http_get(base + "/api/status")
    assert code == 401
    code, _ = _http_get(base + f"/api/status?key={started['port']}")
    assert code == 401  # wrong key
    code, body = _http_get(base + "/api/status?key=s3cret")
    assert code == 200 and json.loads(body)["ok"] is True

    request = urllib.request.Request(base + "/api/status")
    request.add_header("Authorization", "Bearer s3cret")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200

    stopped = host_api.web_status_stop()
    assert stopped["ok"] and stopped["stopped"] is True
    assert host_api.web_status_info()["running"] is False


def test_web_status_start_twice_is_idempotent(configured_host):
    first = host_api.web_status_start(port=0)
    assert first["ok"]
    second = host_api.web_status_start(port=0)
    assert second["ok"] and second.get("already") is True
    assert second["port"] == first["port"]


# --------------------------------------------------------------------- #
# Process isolation                                                      #
# --------------------------------------------------------------------- #


def test_isolation_manifest_validation():
    ok, errors = validate_manifest({
        "id": "iso-bot", "name": "Iso", "version": "1.0.0",
        "entrypoint": "main.py", "isolation": "process",
    })
    assert ok and errors == []
    bad, errors = validate_manifest({
        "id": "iso-bot", "name": "Iso", "version": "1.0.0",
        "entrypoint": "main.py", "isolation": "docker",
    })
    assert bad is None and any("isolation" in e for e in errors)


def test_process_probe_on_desktop():
    assert isolation_mod.process_runtime_available() is True


def _process_bot(tmp_path, bot_id: str, code: str):
    return make_bot_dir(
        tmp_path / ("src-" + bot_id),
        bot_id=bot_id,
        code=code,
        manifest={"isolation": "process"},
    )


def test_process_mode_runs_and_stops_cooperatively(tmp_path):
    supervisor = Supervisor(tmp_path / "bots")
    imported = supervisor.import_folder(
        _process_bot(tmp_path, "proc-bot", LONG_RUNNING_MAIN)
    )
    assert imported["ok"], imported
    assert supervisor.start("proc-bot")["ok"]
    assert wait_for(lambda: supervisor.status("proc-bot")["isolation_effective"] == "process")
    assert wait_for(
        lambda: any("long tick" in r["message"] for r in supervisor.recent_logs("proc-bot", 50))
    ), "child stdout was not piped into bot logs"
    assert wait_for(lambda: supervisor.status("proc-bot")["state"] == "RUNNING")
    stopped = supervisor.stop("proc-bot")
    assert stopped["ok"] and stopped["state"] == "STOPPED"
    status = supervisor.status("proc-bot")
    assert status["state"] == "STOPPED"
    assert status["isolation"] == "process" and status["isolation_effective"] == "process"


def test_process_mode_reports_crashes(tmp_path):
    supervisor = Supervisor(tmp_path / "bots")
    assert supervisor.import_folder(
        _process_bot(tmp_path, "crash-proc", "raise ValueError('child boom')\n")
    )["ok"]
    assert supervisor.start("crash-proc")["ok"]
    assert wait_for(
        lambda: supervisor.status("crash-proc")["state"] in ("FAILED", "BACKOFF")
    ), supervisor.status("crash-proc")
    status = supervisor.status("crash-proc")
    if status["state"] == "BACKOFF":  # on_failure policy may schedule a retry
        supervisor.stop("crash-proc")
    assert "child process exited with code 1" in (status.get("last_error") or "")


def test_process_mode_force_stop_kills_for_real(tmp_path):
    supervisor = Supervisor(tmp_path / "bots")
    stubborn = (
        "import time\n"
        "print('stubborn-alive', flush=True)\n"
        "while True:\n"
        "    time.sleep(0.2)\n"  # never checks the stop event
    )
    assert supervisor.import_folder(
        _process_bot(tmp_path, "stubborn-proc", stubborn)
    )["ok"]
    assert supervisor.start("stubborn-proc")["ok"]
    # Wait until the child is actually executing bot code: a SIGTERM that
    # arrives during interpreter boot (before the handler is installed)
    # legitimately terminates the child.
    assert wait_for(
        lambda: any(
            "stubborn-alive" in r["message"]
            for r in supervisor.recent_logs("stubborn-proc", 50)
        )
    ), "child never printed its boot line"
    supervisor.stop("stubborn-proc", timeout=1.0)
    assert supervisor.status("stubborn-proc")["state"] in ("STOPPING", "RUNNING")
    forced = supervisor.force_stop("stubborn-proc")
    assert forced["ok"]
    assert wait_for(
        lambda: supervisor.status("stubborn-proc")["state"]
        in ("STOPPED", "FORCE_STOPPED")
    )
    status = supervisor.status("stubborn-proc")
    assert status["state"] in ("STOPPED", "FORCE_STOPPED")
    runner = supervisor.get("stubborn-proc").thread
    if isinstance(runner, isolation_mod.ProcessRunner):
        assert runner.process is not None
        assert runner.process.poll() is not None, "child survived SIGKILL"


def test_process_mode_falls_back_to_threads_when_unavailable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(isolation_mod, "process_runtime_available", lambda: False)
    supervisor = Supervisor(tmp_path / "bots")
    assert supervisor.import_folder(
        _process_bot(tmp_path, "fallback-bot", EXITING_MAIN)
    )["ok"]
    assert supervisor.start("fallback-bot")["ok"]
    status = supervisor.status("fallback-bot")
    assert status["isolation_effective"] == "thread"
    assert wait_for(lambda: supervisor.status("fallback-bot")["state"] == "COMPLETED")
    messages = [r["message"] for r in supervisor.recent_logs("fallback-bot", 50)]
    assert any("falling back to thread mode" in m for m in messages)


def test_child_runner_usage_error():
    from drs_host.child_runner import child_main

    assert child_main([]) == 2


# --------------------------------------------------------------------- #
# CLI smoke                                                              #
# --------------------------------------------------------------------- #


def test_cli_skills_and_scaffold_skill(tmp_path, capsys):
    from drs_host.cli import main

    assert main(["--data-dir", str(tmp_path / "d"), "skills"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) >= 7

    assert (
        main([
            "--data-dir", str(tmp_path / "d"),
            "scaffold-skill", "http-poller", "CLI Poller", "--dest", str(tmp_path / "out"),
        ])
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    assert (Path(generated["path"]) / "bot.json").is_file()
