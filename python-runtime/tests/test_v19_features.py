"""v1.9 feature tests: bilingual (EN/AR) Wi-Fi fleet status page and the
two new curated sample bots (sys-monitor, task-runner) — registry wiring,
strict manifest validation, real import + run flows.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from drs_host import host_api
from drs_host.manifest import validate_manifest
from drs_host.webstatus import _PAGE_AR, _PAGE_EN, normalize_language
from conftest import EXITING_MAIN, LONG_RUNNING_MAIN, make_bot_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "registry" / "registry.json"
SAMPLE_BOTS = REPO_ROOT / "sample-bots"

AR_ONLY_MARKS = ("dir=\"rtl\"", "حالة الأسطول", "قيد التشغيل", "البوت")
EN_ONLY_MARKS = ("fleet status", "running", "refreshes every 5s")


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


# --------------------------------------------------------------------- #
# Language normalization                                                  #
# --------------------------------------------------------------------- #


def test_normalize_language_known_variants():
    assert normalize_language("ar") == "ar"
    assert normalize_language(" AR ") == "ar"
    assert normalize_language("Arabic") == "ar"
    assert normalize_language("العربية") == "ar"
    assert normalize_language("en") == "en"
    assert normalize_language("EN") == "en"


def test_normalize_language_falls_back_to_english():
    for value in (None, "", "fr", "de-DE", 123, "english"):
        assert normalize_language(value) == "en"


def test_both_templates_carry_their_own_markers():
    for mark in ("lang=\"en\"", "<title>DRS Bot Host — Fleet Status</title>"):
        assert mark in _PAGE_EN
    assert "dir=\"rtl\"" not in _PAGE_EN
    for mark in AR_ONLY_MARKS:
        assert mark in _PAGE_AR
    assert "lang=\"ar\"" in _PAGE_AR
    assert "text-align:right" in _PAGE_AR


# --------------------------------------------------------------------- #
# Status page over HTTP (server-side language)                            #
# --------------------------------------------------------------------- #


def test_status_page_defaults_to_english(configured_host, tmp_path):
    bot_dir = make_bot_dir(tmp_path / "src-en", bot_id="page-en", code=EXITING_MAIN)
    assert host_api.import_folder(str(bot_dir))["ok"]
    started = host_api.web_status_start(port=0)
    assert started["ok"] and started["port"] > 0
    base = f"http://127.0.0.1:{started['port']}"

    code, html = _http_get(base + "/")
    assert code == 200
    assert "lang=\"en\"" in html
    assert "fleet status" in html
    assert "__" + "TOTAL" + "__" not in html  # placeholders resolved
    assert host_api.web_status_info()["language"] == "en"


def test_status_page_arabic_is_rtl_with_arabic_labels(configured_host, tmp_path):
    bot_dir = make_bot_dir(tmp_path / "src-ar", bot_id="page-ar", code=EXITING_MAIN)
    assert host_api.import_folder(str(bot_dir))["ok"]
    started = host_api.web_status_start(port=0, language="ar")
    assert started["ok"] and started["port"] > 0
    base = f"http://127.0.0.1:{started['port']}"

    code, html = _http_get(base + "/")
    assert code == 200
    for mark in AR_ONLY_MARKS:
        assert mark in html
    assert "lang=\"ar\"" in html
    assert "fleet status" not in html
    assert "__" + "RUNNING" + "__" not in html

    # JSON API is unchanged by the page language.
    code, payload = _http_get(base + "/api/status")
    assert code == 200
    document = json.loads(payload)
    assert document["ok"] is True
    assert any(bot["id"] == "page-ar" for bot in document["bots"])

    info = host_api.web_status_info()
    assert info["running"] is True and info["language"] == "ar"


def test_status_page_language_switch_requires_restart(configured_host):
    first = host_api.web_status_start(port=0, language="en")
    assert first["ok"]
    base = f"http://127.0.0.1:{first['port']}"
    _, html = _http_get(base + "/")
    assert "lang=\"en\"" in html

    # Language is fixed per server instance; switching needs a restart.
    assert host_api.web_status_stop()["ok"]
    second = host_api.web_status_start(port=0, language="ar")
    assert second["ok"]
    _, html = _http_get(f"http://127.0.0.1:{second['port']}/")
    assert "dir=\"rtl\"" in html
    assert "حالة الأسطول" in html


def test_status_page_arabic_empty_fleet_uses_arabic_hint(configured_host):
    started = host_api.web_status_start(port=0, language="ar")
    assert started["ok"]
    _, html = _http_get(f"http://127.0.0.1:{started['port']}/")
    assert "لا توجد بوتات مثبتة بعد" in html
    assert "no bots installed yet" not in html


# --------------------------------------------------------------------- #
# New sample bots: manifests + registry wiring                            #
# --------------------------------------------------------------------- #


NEW_BOTS = ("sys-monitor", "task-runner")


@pytest.mark.parametrize("bot_id", NEW_BOTS)
def test_new_sample_bot_manifests_are_strict_valid(bot_id):
    manifest_raw = json.loads((SAMPLE_BOTS / bot_id / "bot.json").read_text())
    manifest, errors = validate_manifest(manifest_raw)
    assert errors == []
    assert manifest is not None
    assert manifest.id == bot_id
    assert manifest.requirements == []  # stdlib-only promise
    assert (SAMPLE_BOTS / bot_id / manifest.entrypoint).is_file()


def test_new_bots_are_registered_with_valid_release_urls():
    registry = json.loads(REGISTRY_PATH.read_text())
    entries = {entry["id"]: entry for entry in registry["bots"]}
    assert len(entries) == len(registry["bots"]), "duplicate registry ids"
    for bot_id in NEW_BOTS:
        entry = entries[bot_id]
        url = entry["url"]
        assert url.startswith("https://github.com/CTO-DRS/DRS-Bot-Host/releases/download/v1.9.0/")
        assert url.endswith(f"/{bot_id}.zip")
        assert "stdlib-only" in entry["tags"]


@pytest.mark.parametrize("bot_id", NEW_BOTS)
def test_new_sample_bots_import_and_run(configured_host, tmp_path, bot_id):
    source = SAMPLE_BOTS / bot_id
    work_copy = tmp_path / bot_id
    work_copy.mkdir()
    (work_copy / "bot.json").write_text((source / "bot.json").read_text())
    (work_copy / "main.py").write_text((source / "main.py").read_text())

    imported = host_api.import_folder(str(work_copy))
    assert imported["ok"], imported

    started = host_api.start_bot(bot_id)
    assert started["ok"], started
    try:
        # Both bots must log at least one line within a few seconds.
        deadline = time.time() + 10
        lines = []
        while time.time() < deadline:
            records = host_api.recent_logs(bot_id, 50)
            lines = [str(r.get("message", "")) for r in records]
            if any("started" in line or "task-runner started" in line for line in lines):
                break
            time.sleep(0.05)
        assert lines, f"{bot_id} produced no logs"
    finally:
        host_api.stop_bot(bot_id)
    assert host_api.bot_status(bot_id)["state"] in ("STOPPED", "COMPLETED")


def test_task_runner_completes_all_tasks(configured_host, tmp_path):
    source = SAMPLE_BOTS / "task-runner"
    manifest = json.loads((source / "bot.json").read_text())
    manifest["config"] = {"tasks": ["alpha", "beta"], "per_task_seconds": 0.2}
    work_copy = tmp_path / "tr-run"
    work_copy.mkdir()
    (work_copy / "bot.json").write_text(json.dumps(manifest))
    (work_copy / "main.py").write_text((source / "main.py").read_text())

    assert host_api.import_folder(str(work_copy))["ok"]
    assert host_api.start_bot("task-runner")["ok"]
    try:
        deadline = time.time() + 15
        state = ""
        messages = []
        while time.time() < deadline:
            status = host_api.bot_status("task-runner")
            state = status["state"]
            if state == "COMPLETED":
                break
            time.sleep(0.05)
        records = host_api.recent_logs("task-runner", 100)
        messages = [str(r.get("message", "")) for r in records]
        assert state == "COMPLETED", messages
        assert any("all tasks done" in message for message in messages)
    finally:
        host_api.stop_bot("task-runner")


def test_sys_monitor_interval_respects_config(configured_host, tmp_path):
    source = SAMPLE_BOTS / "sys-monitor"
    manifest = json.loads((source / "bot.json").read_text())
    manifest["config"] = {"interval_seconds": 0.5}
    work_copy = tmp_path / "sm-run"
    work_copy.mkdir()
    (work_copy / "bot.json").write_text(json.dumps(manifest))
    (work_copy / "main.py").write_text((source / "main.py").read_text())

    assert host_api.import_folder(str(work_copy))["ok"]
    assert host_api.start_bot("sys-monitor")["ok"]
    try:
        deadline = time.time() + 10
        samples: list[str] = []
        while time.time() < deadline:
            records = host_api.recent_logs("sys-monitor", 100)
            samples = [str(r.get("message", "")) for r in records if "sample:" in str(r.get("message", ""))]
            if len(samples) >= 2:
                break
            time.sleep(0.05)
        assert len(samples) >= 2, samples
        assert "rss" in samples[0] and "threads" in samples[0]
    finally:
        host_api.stop_bot("sys-monitor")
