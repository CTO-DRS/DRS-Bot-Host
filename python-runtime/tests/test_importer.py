"""Importer tests: happy paths, traversal, limits, collisions."""

import json
import zipfile

from drs_host.importer import import_zip, import_folder, peek_zip, peek_folder
from conftest import make_bot_dir, make_bot_zip


def test_zip_happy_path(tmp_path, data_dir):
    zpath = make_bot_zip(tmp_path)
    result = import_zip(zpath, data_dir / "bots")
    assert result["ok"], result
    assert result["bot_id"] == "echo-bot"
    installed = data_dir / "bots" / "echo-bot"
    assert (installed / "main.py").is_file()
    assert (installed / "bot.json").is_file()
    normalized = json.loads((installed / "bot.json").read_text(encoding="utf-8"))
    assert normalized["id"] == "echo-bot"
    assert normalized["restart"]["policy"] == "on_failure"


def test_zip_with_single_root_folder_is_normalized(tmp_path, data_dir):
    source = make_bot_dir(tmp_path / "src")
    zpath = tmp_path / "wrapped.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        for path in sorted(source.rglob("*")):
            archive.write(path, f"my-bot/{path.relative_to(source)}")
    result = import_zip(zpath, data_dir / "bots")
    assert result["ok"], result
    assert (data_dir / "bots" / "echo-bot" / "main.py").is_file()


def test_zip_missing_manifest(tmp_path, data_dir):
    zpath = tmp_path / "empty.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("main.py", "print('hi')\n")
    result = import_zip(zpath, data_dir / "bots")
    assert not result["ok"]
    assert any("bot.json not found" in e for e in result["errors"])


def test_zip_bad_json(tmp_path, data_dir):
    zpath = tmp_path / "bad.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("bot.json", "{not json")
    result = import_zip(zpath, data_dir / "bots")
    assert not result["ok"]
    assert any("not valid JSON" in e for e in result["errors"])


def test_zip_slip_blocked(tmp_path, data_dir):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("bot.json", json.dumps(
            {"id": "evil", "name": "Evil", "version": "1.0.0", "entrypoint": "main.py"}
        ))
        archive.writestr("main.py", "print('hi')\n")
        info = zipfile.ZipInfo("../escaped.txt")
        archive.writestr(info, "pwned")
    result = import_zip(zpath, data_dir / "bots")
    assert not result["ok"]
    assert any("unsafe path" in e for e in result["errors"])
    assert not (data_dir.parent / "escaped.txt").exists()


def test_absolute_path_entry_blocked(tmp_path, data_dir):
    zpath = tmp_path / "abs.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("bot.json", json.dumps(
            {"id": "abs", "name": "Abs", "version": "1.0.0", "entrypoint": "main.py"}
        ))
        archive.writestr("/etc/passwd", "root")
    result = import_zip(zpath, data_dir / "bots")
    assert not result["ok"]
    assert any("unsafe path" in e for e in result["errors"])


def test_disallowed_extension_blocked(tmp_path, data_dir):
    zpath = tmp_path / "sh.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("bot.json", json.dumps(
            {"id": "sh", "name": "Sh", "version": "1.0.0", "entrypoint": "main.py"}
        ))
        archive.writestr("main.py", "print('hi')\n")
        archive.writestr("install.sh", "rm -rf /\n")
    result = import_zip(zpath, data_dir / "bots")
    assert not result["ok"]
    assert any("file type not allowed" in e for e in result["errors"])


def test_missing_entrypoint_rolls_back(tmp_path, data_dir):
    zpath = tmp_path / "noentry.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("bot.json", json.dumps(
            {"id": "noentry", "name": "NoEntry", "version": "1.0.0", "entrypoint": "run.py"}
        ))
        archive.writestr("main.py", "print('hi')\n")
    result = import_zip(zpath, data_dir / "bots")
    assert not result["ok"]
    assert any("entrypoint not found" in e for e in result["errors"])
    assert not (data_dir / "bots" / "noentry").exists()


def test_id_collision_and_overwrite(tmp_path, data_dir):
    zpath = make_bot_zip(tmp_path)
    bots = data_dir / "bots"
    assert import_zip(zpath, bots)["ok"]
    again = import_zip(zpath, bots)
    assert not again["ok"]
    assert any("already installed" in e for e in again["errors"])
    assert import_zip(zpath, bots, overwrite=True)["ok"]


def test_oversize_limit(tmp_path, data_dir):
    zpath = make_bot_zip(tmp_path)
    result = import_zip(zpath, data_dir / "bots", limits={"max_zip_bytes": 10})
    assert not result["ok"]
    assert any("too large" in e for e in result["errors"])


def test_folder_import_and_collision(tmp_path, data_dir):
    source = make_bot_dir(tmp_path / "mybot")
    result = import_folder(source, data_dir / "bots")
    assert result["ok"], result
    assert (data_dir / "bots" / "echo-bot" / "main.py").is_file()
    again = import_folder(source, data_dir / "bots")
    assert not again["ok"]
    assert import_folder(source, data_dir / "bots", overwrite=True)["ok"]


def test_folder_import_parent_picker(tmp_path, data_dir):
    make_bot_dir(tmp_path / "outer" / "inner-bot")
    result = import_folder(tmp_path / "outer", data_dir / "bots")
    assert result["ok"], result
    assert (data_dir / "bots" / "echo-bot" / "main.py").is_file()


def test_peek_zip_and_folder(tmp_path):
    zpath = make_bot_zip(tmp_path)
    manifest, errors = peek_zip(zpath)
    assert errors == []
    assert manifest.id == "echo-bot"
    manifest, errors = peek_folder(make_bot_dir(tmp_path / "f"))
    assert errors == []
    assert manifest.id == "echo-bot"
