"""v1.4 feature tests: marketplace, backup/restore, status-page TLS."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import EXITING_MAIN, LONG_RUNNING_MAIN, make_bot_dir, wait_for

from drs_host import backup as backup_mod
from drs_host import host_api, marketplace
from drs_host.supervisor import Supervisor


# --------------------------------------------------------------------- #
# Local HTTP helper (registry + bot zip serving)                         #
# --------------------------------------------------------------------- #


@contextlib.contextmanager
def serve_directory(root: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _http_get(url: str, timeout: float = 5.0) -> tuple:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# --------------------------------------------------------------------- #
# Marketplace: registry validation                                       #
# --------------------------------------------------------------------- #


VALID_ENTRY = {
    "id": "echo-bot",
    "name": "Echo Bot",
    "description": "Replies with your message",
    "version": "1.0.0",
    "author": "DRS",
    "tags": ["demo", "starter"],
    "url": "https://example.com/echo-bot.zip",
    "hostile_extra_key": "must-not-survive",
}


def test_validate_registry_accepts_valid_document():
    entries, errors = marketplace.validate_registry({"bots": [VALID_ENTRY]})
    assert errors == []
    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == "echo-bot"
    assert entry["tags"] == ["demo", "starter"]
    assert "hostile_extra_key" not in entry


def test_validate_registry_accepts_bare_list():
    entries, errors = marketplace.validate_registry([VALID_ENTRY])
    assert errors == [] and len(entries) == 1


def test_validate_registry_drops_bad_entries_but_keeps_good_ones():
    document = {
        "bots": [
            VALID_ENTRY,
            "not-an-object",
            {**VALID_ENTRY, "id": "Bad Slug!"},
            {**VALID_ENTRY, "id": "no-name", "name": ""},
            {**VALID_ENTRY, "id": "no-url", "url": ""},
            {**VALID_ENTRY, "id": "ftp-url", "url": "ftp://example.com/x.zip"},
            {**VALID_ENTRY, "id": "echo-bot"},  # duplicate id
        ]
    }
    entries, errors = marketplace.validate_registry(document)
    assert [entry["id"] for entry in entries] == ["echo-bot"]
    assert len(errors) == 6


def test_validate_registry_rejects_oversized_and_empty():
    entries, errors = marketplace.validate_registry(
        {"bots": [{**VALID_ENTRY, "id": f"bot-{i}"} for i in range(marketplace.MAX_ENTRIES + 1)]}
    )
    assert entries == [] and "too large" in errors[0]
    entries, errors = marketplace.validate_registry({"bots": []})
    assert entries == [] and errors


def test_fetch_registry_rejects_unsupported_scheme():
    result = marketplace.fetch_registry("file:///etc/passwd")
    assert not result["ok"] and "http/https" in result["errors"][0]


def test_fetch_registry_over_local_http(tmp_path):
    (tmp_path / "registry.json").write_text(
        json.dumps({"bots": [VALID_ENTRY]}), encoding="utf-8"
    )
    with serve_directory(tmp_path) as base:
        result = marketplace.fetch_registry(f"{base}/registry.json")
    assert result["ok"], result
    assert result["count"] == 1
    assert result["bots"][0]["id"] == "echo-bot"
    assert result["source"].endswith("/registry.json")


def test_fetch_registry_rejects_oversize_bad_json_and_404(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"x" * (marketplace.REGISTRY_MAX_BYTES + 2))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with serve_directory(tmp_path) as base:
        big = marketplace.fetch_registry(f"{base}/big.bin")
        assert not big["ok"] and "too large" in big["errors"][0]

        broken = marketplace.fetch_registry(f"{base}/broken.json")
        assert not broken["ok"] and "not valid JSON" in broken["errors"][0]

        missing = marketplace.fetch_registry(f"{base}/nope.json")
        assert not missing["ok"]


# --------------------------------------------------------------------- #
# Marketplace: install round-trip through the hardened importer          #
# --------------------------------------------------------------------- #


def test_marketplace_install_roundtrip(tmp_path):
    zip_path = make_bot_dir(tmp_path / "src", bot_id="market-bot")
    zipped = tmp_path / "market-bot.zip"
    with zipfile.ZipFile(zipped, "w") as archive:
        for path in sorted(zip_path.rglob("*")):
            archive.write(path, path.relative_to(zip_path))

    with serve_directory(tmp_path) as base:
        supervisor = Supervisor(tmp_path / "bots")
        bad = marketplace.install_entry("ftp://example.com/x.zip", supervisor)
        assert not bad["ok"] and "http/https" in bad["errors"][0]

        result = marketplace.install_entry(f"{base}/market-bot.zip", supervisor)
        assert result["ok"], result
        assert result["bot_id"] == "market-bot"
        assert supervisor.get("market-bot") is not None

        again = marketplace.install_entry(f"{base}/market-bot.zip", supervisor)
        assert not again["ok"] and "already installed" in again["errors"][0]

        forced = marketplace.install_entry(
            f"{base}/market-bot.zip", supervisor, overwrite=True
        )
        assert forced["ok"], forced


def test_host_api_marketplace_and_cli(tmp_path, capsys):
    from drs_host.cli import main

    host_api.configure(tmp_path / "data")
    zip_path = make_bot_dir(tmp_path / "src", bot_id="api-market-bot")
    zipped = tmp_path / "bot.zip"
    with zipfile.ZipFile(zipped, "w") as archive:
        for path in sorted(zip_path.rglob("*")):
            archive.write(path, path.relative_to(zip_path))
    with serve_directory(tmp_path) as base:
        fetched = host_api.marketplace_fetch(f"{base}/missing-registry.json")
        assert not fetched["ok"]  # network path is exercised; registry served separately

        (tmp_path / "registry.json").write_text(
            json.dumps({"bots": [{**VALID_ENTRY, "url": f"{base}/bot.zip"}]}),
            encoding="utf-8",
        )
        registry = host_api.marketplace_fetch(f"{base}/registry.json")
        assert registry["ok"] and registry["count"] == 1
        installed = host_api.marketplace_install(registry["bots"][0]["url"])
        assert installed["ok"], installed

    assert host_api.bot_status("api-market-bot")["ok"]
    try:
        assert (
            main([
                "--data-dir", str(tmp_path / "data"),
                "market-install", "ftp://example.com/x.zip",
            ])
            == 2
        )
    finally:
        host_api.shutdown_all()


# --------------------------------------------------------------------- #
# Backup & restore                                                       #
# --------------------------------------------------------------------- #


@pytest.fixture()
def populated_host(data_dir):
    host_api.configure(data_dir)
    first = host_api.import_folder(
        str(make_bot_dir(data_dir.parent / "src-a", bot_id="backup-one"))
    )
    second = host_api.import_folder(
        str(
            make_bot_dir(
                data_dir.parent / "src-b",
                bot_id="backup-two",
                code=LONG_RUNNING_MAIN,
                files={"extra/notes.md": "# hello"},
            )
        )
    )
    assert first["ok"] and second["ok"], (first, second)
    yield host_api
    host_api.shutdown_all()


def test_backup_creates_zip_with_metadata(populated_host, data_dir):
    started = populated_host.start_bot("backup-two")
    assert started["ok"]
    assert wait_for(
        lambda: populated_host.bot_status("backup-two")["state"] == "RUNNING"
    )
    result = populated_host.backup_all()
    assert result["ok"], result
    assert result["bots"] == ["backup-one", "backup-two"]
    path = Path(result["path"])
    assert path.is_file() and path.parent.name == "backups"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert "backup.json" in names
        assert "bots/backup-one/bot.json" in names
        assert "bots/backup-two/extra/notes.md" in names
        metadata = json.loads(archive.read("backup.json"))
    assert metadata["kind"] == "drs-bot-host-backup"
    assert metadata["bot_count"] == 2
    populated_host.stop_bot("backup-two")


def test_backup_excludes_logs_and_pycache(populated_host, data_dir):
    bot_dir = data_dir / "bots" / "backup-one"
    (bot_dir / "logs").mkdir()
    (bot_dir / "logs" / "runtime.jsonl").write_text('{"ts":1}\n', encoding="utf-8")
    (bot_dir / "__pycache__").mkdir()
    (bot_dir / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00")
    result = populated_host.backup_all()
    assert result["ok"], result
    with zipfile.ZipFile(result["path"]) as archive:
        names = archive.namelist()
    assert not any("logs/" in name or "__pycache__" in name for name in names)


def test_backup_with_no_bots_is_rejected(data_dir):
    host_api.configure(data_dir)
    try:
        result = host_api.backup_all()
        assert not result["ok"] and "nothing to back up" in result["errors"][0]
    finally:
        host_api.shutdown_all()


def test_restore_roundtrip_into_fresh_host(populated_host, data_dir, tmp_path):
    backup = populated_host.backup_all()
    assert backup["ok"], backup
    populated_host.shutdown_all()

    fresh_data = tmp_path / "fresh-data"
    (fresh_data / "bots").mkdir(parents=True)
    host_api.configure(fresh_data)
    try:
        missing = host_api.restore_backup(str(tmp_path / "nope.zip"))
        assert not missing["ok"]

        restored = host_api.restore_backup(backup["path"])
        assert restored["ok"], restored
        assert restored["restored"] == ["backup-one", "backup-two"]
        assert host_api.bot_status("backup-one")["ok"]
        assert host_api.bot_status("backup-two")["ok"]

        # A restored bot is a first-class citizen: it runs to completion.
        assert host_api.start_bot("backup-one")["ok"]
        assert wait_for(
            lambda: host_api.bot_status("backup-one")["state"] == "COMPLETED"
        )

        again = host_api.restore_backup(backup["path"])
        assert not again["ok"] and again["failures"]
        forced = host_api.restore_backup(backup["path"], overwrite=True)
        assert forced["ok"], forced
    finally:
        host_api.shutdown_all()


def test_restore_rejects_foreign_zip(tmp_path, data_dir):
    host_api.configure(data_dir)
    try:
        foreign = tmp_path / "foreign.zip"
        with zipfile.ZipFile(foreign, "w") as archive:
            archive.writestr("random/file.txt", "hello")
        result = host_api.restore_backup(str(foreign))
        assert not result["ok"] and "backup.json" in result["errors"][0]

        corrupt = tmp_path / "corrupt.zip"
        corrupt.write_bytes(b"PK\x03\x04 not really a zip")
        assert not host_api.restore_backup(str(corrupt))["ok"]
    finally:
        host_api.shutdown_all()


def test_cli_backup_and_restore(tmp_path, capsys):
    from drs_host.cli import main

    data_dir_a = tmp_path / "data-a"
    (data_dir_a / "bots").mkdir(parents=True)
    src = make_bot_dir(tmp_path / "src", bot_id="cli-backup-bot")
    assert main(["--data-dir", str(data_dir_a), "import", str(src)]) == 0
    capsys.readouterr()  # drain the import JSON before parsing the next command

    assert main(["--data-dir", str(data_dir_a), "backup"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] and Path(payload["path"]).is_file()

    data_dir_b = tmp_path / "data-b"
    (data_dir_b / "bots").mkdir(parents=True)
    assert main(["--data-dir", str(data_dir_b), "restore", payload["path"]]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["restored"] == ["cli-backup-bot"]

    assert (
        main(["--data-dir", str(data_dir_b), "list"])
        == 0
    )
    listed = json.loads(capsys.readouterr().out)
    assert [bot["id"] for bot in listed] == ["cli-backup-bot"]


# --------------------------------------------------------------------- #
# Status page TLS (user-supplied PEM certs)                              #
# --------------------------------------------------------------------- #


def _has_crypto_toolchain() -> bool:
    if importlib.util.find_spec("cryptography") is not None:
        return True
    return shutil.which("openssl") is not None


def _make_self_signed(directory: Path) -> tuple:
    """cert.pem/key.pem via cryptography (if present) or the openssl CLI."""
    cert, key = directory / "cert.pem", directory / "key.pem"
    if importlib.util.find_spec("cryptography") is not None:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "localhost")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert_obj = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key_obj.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .sign(key_obj, hashes.SHA256())
        )
        key.write_bytes(
            key_obj.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        cert.write_bytes(cert_obj.public_bytes(serialization.Encoding.PEM))
        return str(cert), str(key)

    openssl = shutil.which("openssl")
    subprocess.run(
        [
            openssl, "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "2", "-nodes", "-subj", "/CN=localhost",
        ],
        check=True, capture_output=True,
    )
    return str(cert), str(key)


def test_web_status_tls_rejects_partial_or_missing_files(data_dir):
    host_api.configure(data_dir)
    try:
        cert, key = _make_self_signed(data_dir)
        only_cert = host_api.web_status_start(0, None, cert, None)
        assert not only_cert["ok"] and "both certfile and keyfile" in only_cert["errors"][0]

        missing = host_api.web_status_start(0, None, str(data_dir / "ghost.pem"), key)
        assert not missing["ok"] and "cannot read" in missing["errors"][0]
    finally:
        host_api.shutdown_all()


@pytest.mark.skipif(
    not _has_crypto_toolchain(),
    reason="needs cryptography or the openssl CLI to mint a test certificate",
)
def test_web_status_tls_serves_https(data_dir):
    import ssl as ssl_mod

    host_api.configure(data_dir)
    try:
        cert, key = _make_self_signed(data_dir)
        started = host_api.web_status_start(0, "tok", cert, key)
        assert started["ok"], started
        port = started["port"]

        info = host_api.web_status_info()
        assert info["running"] and info["tls"] is True and info["protected"] is True

        context = ssl_mod.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl_mod.CERT_NONE
        base = f"https://127.0.0.1:{port}"

        with urllib.request.urlopen(base + "/api/status?key=tok", context=context, timeout=5) as response:
            document = json.loads(response.read().decode("utf-8"))
        assert document["ok"] is True and "bots" in document

        try:
            urllib.request.urlopen(base + "/api/status?key=wrong", context=context, timeout=5)
            raise AssertionError("expected HTTP 401")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        host_api.web_status_stop()
        host_api.shutdown_all()


def test_web_status_info_reports_plain_http(data_dir):
    host_api.configure(data_dir)
    try:
        started = host_api.web_status_start(0)
        assert started["ok"]
        info = host_api.web_status_info()
        assert info["running"] and info["tls"] is False and info["protected"] is False
    finally:
        host_api.web_status_stop()
        host_api.shutdown_all()
