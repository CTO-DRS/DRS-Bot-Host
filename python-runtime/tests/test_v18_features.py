"""v1.8 — GitHub link scanner: paste a link, auto-detect and import bots."""

from __future__ import annotations

import json
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from drs_host import ghscan, host_api
from drs_host.downloader import download_zip
from drs_host.importer import import_bot_from_zip_subtree, import_zip_member

MANIFEST = {
    "id": "scan-bot",
    "name": "Scan Bot",
    "version": "1.0.0",
    "entrypoint": "main.py",
    "description": "scanner test bot",
    "requirements": ["requests"],
}
MAIN = 'print("hello from scan")\n'


# --------------------------------------------------------------------- #
# helpers                                                                #
# --------------------------------------------------------------------- #

def write_bot_zip(path: Path, layout: dict) -> Path:
    """layout maps archive member name -> text content (str or bytes)."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in layout.items():
            archive.writestr(name, content)
    return path


MULTI_BOT = {
    "repo-main/README.md": "multi-bot demo repo",
    "repo-main/alpha/bot.json": json.dumps(MANIFEST),
    "repo-main/alpha/main.py": MAIN,
    "repo-main/beta/bot.json": json.dumps({**MANIFEST, "id": "beta-bot"}),
    "repo-main/beta/main.py": MAIN,
    "repo-main/packs/legacy.ibot": "placeholder (replaced with real bytes in some tests)",
}

ROOT_BOT = {
    "bot.json": json.dumps(MANIFEST),
    "main.py": MAIN,
}

# A real nested zip built first, then embedded as a member.
NESTED_INNER = {
    "inner-bot/bot.json": json.dumps({**MANIFEST, "id": "inner-bot"}),
    "inner-bot/main.py": MAIN,
}


@pytest.fixture()
def nested_zip(tmp_path) -> Path:
    inner = write_bot_zip(tmp_path / "inner.ibot", NESTED_INNER)
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("bundle/notes.txt", "outer wrapper")
        archive.writestr("bundle/helper.ibot", inner.read_bytes())
    return outer


@pytest.fixture()
def zip_server():
    """Serve a couple of archives for fetch-level tests."""
    payloads: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            if self.path in payloads:
                body = payloads[self.path]
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *args):  # silence the test log
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, payloads
    server.shutdown()
    server.server_close()


# --------------------------------------------------------------------- #
# parse_github_url                                                       #
# --------------------------------------------------------------------- #

def probe_ok_for(specs):
    def probe(url):
        return any(spec in url for spec in specs)
    return probe


def test_parse_repo_link():
    parsed = ghscan.parse_github_url("https://github.com/owner/repo")
    assert parsed["ok"] and parsed["kind"] == "repo"
    assert parsed["owner"] == "owner" and parsed["repo"] == "repo"


def test_parse_scheme_less_github_link():
    parsed = ghscan.parse_github_url("  github.com/owner/repo  ")
    assert parsed["ok"] and parsed["kind"] == "repo"


def test_parse_tree_single_ref():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/tree/main",
        probe=probe_ok_for(["refs/heads/main"]),
    )
    assert parsed["ok"] and parsed["kind"] == "tree"
    assert parsed["ref"] == "main" and parsed["subpath"] is None


def test_parse_tree_with_subpath():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/tree/main/bots/alpha",
        probe=probe_ok_for(["refs/heads/main"]),
    )
    assert parsed["ref"] == "main" and parsed["subpath"] == "bots/alpha"


def test_parse_tree_slashed_branch_via_probe():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/tree/feature/one/two/bots/x",
        probe=probe_ok_for(["refs/heads/feature/one/two"]),
    )
    assert parsed["ref"] == "feature/one/two"
    assert parsed["subpath"] == "bots/x"


def test_parse_tree_tag_fallback():
    def probe(url):
        return "refs/tags/v1.2" in url

    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/tree/v1.2", probe=probe,
    )
    assert parsed["ref"] == "v1.2"


def test_parse_tree_unresolvable_ref():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/tree/ghost", probe=lambda url: False,
    )
    assert not parsed["ok"]


def test_parse_tree_refuses_traversal_subpath():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/tree/main/../..",
        probe=probe_ok_for(["refs/heads/main"]),
    )
    assert not parsed["ok"]


def test_parse_blob_zip_becomes_raw_url():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/blob/main/dist/bot.zip",
        probe=probe_ok_for(["refs/heads/main"]),
    )
    assert parsed["ok"] and parsed["kind"] == "zip"
    assert parsed["download_url"] == (
        "https://raw.githubusercontent.com/owner/repo/main/dist/bot.zip"
    )


def test_parse_blob_non_zip_refused():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/blob/main/README.md",
        probe=probe_ok_for(["refs/heads/main"]),
    )
    assert not parsed["ok"]


def test_parse_release_asset_direct():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/releases/download/v1.0/my-bot.zip",
    )
    assert parsed["ok"] and parsed["kind"] == "zip"
    assert parsed["download_url"].endswith("my-bot.zip")


def test_parse_release_latest_via_api_stub():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/releases/latest",
        fetch_json=lambda url: {
            "tag_name": "v2.0",
            "assets": [{"name": "bundle.ibot",
                        "browser_download_url": "https://x/bundle.ibot"}],
        },
    )
    assert parsed["ok"] and parsed["download_url"] == "https://x/bundle.ibot"


def test_parse_release_latest_without_assets():
    parsed = ghscan.parse_github_url(
        "https://github.com/owner/repo/releases/latest",
        fetch_json=lambda url: {"tag_name": "v2.0", "assets": []},
    )
    assert not parsed["ok"]


def test_parse_direct_variants():
    assert ghscan.parse_github_url(
        "https://github.com/o/r/archive/refs/heads/main.zip"
    )["kind"] == "zip"
    assert ghscan.parse_github_url(
        "https://raw.githubusercontent.com/o/r/main/bot.zip"
    )["kind"] == "zip"
    assert ghscan.parse_github_url(
        "https://codeload.github.com/o/r/zip/refs/heads/main"
    )["kind"] == "zip"
    assert ghscan.parse_github_url("https://example.com/bots/x.zip")["kind"] == "zip"
    assert ghscan.parse_github_url("https://example.com/bots/x.ibot")["kind"] == "zip"


def test_parse_rejects_garbage():
    assert not ghscan.parse_github_url("")["ok"]
    assert not ghscan.parse_github_url("ftp://example.com/x.zip")["ok"]
    assert not ghscan.parse_github_url("https://github.com/owner")["ok"]
    assert not ghscan.parse_github_url("https://example.com/page.html")["ok"]


# --------------------------------------------------------------------- #
# fetch_for_scan                                                         #
# --------------------------------------------------------------------- #

def test_fetch_direct_zip(zip_server, tmp_path):
    server, payloads = zip_server
    payloads["/bot.zip"] = write_bot_zip(tmp_path / "p.zip", ROOT_BOT).read_bytes()
    fetched = ghscan.fetch_for_scan(
        f"http://127.0.0.1:{server.server_address[1]}/bot.zip", tmp_path, max_bytes=10**7,
    )
    assert fetched["ok"] and fetched["resolved"]["kind"] == "zip"
    assert Path(fetched["path"]).is_file()


def test_fetch_repo_and_tree_target_rewrite(tmp_path, monkeypatch):
    captured = {}

    def fake_download_zip(url, dest_dir, **kwargs):
        captured["url"] = url
        target = tmp_path / "fake.zip"
        write_bot_zip(target, ROOT_BOT)
        return {"ok": True, "path": str(target), "bytes": 1}

    monkeypatch.setattr("drs_host.downloader.download_zip", fake_download_zip)
    fetched = ghscan.fetch_for_scan("https://github.com/owner/repo", tmp_path, max_bytes=10**7)
    assert fetched["ok"]
    assert captured["url"] == "https://api.github.com/repos/owner/repo/zipball"

    fetched = ghscan.fetch_for_scan(
        "https://github.com/owner/repo/tree/v1",
        tmp_path, max_bytes=10**7,
        probe=probe_ok_for(["refs/tags/v1"]),
    )
    assert fetched["ok"]
    assert captured["url"] == "https://codeload.github.com/owner/repo/zip/refs/tags/v1"
    assert fetched["resolved"]["ref"] == "v1"


def test_fetch_rejects_bad_url(tmp_path):
    result = ghscan.fetch_for_scan("https://example.com/page.html", tmp_path, max_bytes=100)
    assert not result["ok"]


def test_download_zip_still_works(tmp_path):
    target = write_bot_zip(tmp_path / "plain.zip", ROOT_BOT)
    result = download_zip(
        target.as_uri().replace("file://", "http://localhost/"), tmp_path, max_bytes=10,
    )
    # localhost refuses, but the URL itself is accepted (http/https check only)
    assert not result["ok"] and "download failed" in result["errors"][0]


# --------------------------------------------------------------------- #
# scan_zip_for_bots                                                      #
# --------------------------------------------------------------------- #

def test_scan_single_root_bot(tmp_path):
    archive = write_bot_zip(tmp_path / "root.zip", ROOT_BOT)
    scan = ghscan.scan_zip_for_bots(archive)
    assert scan["ok"] and scan["bot_count"] == 1
    bot = scan["bots"][0]
    assert bot["dir"] == "" and bot["id"] == "scan-bot" and bot["valid"]
    assert bot["entry_ok"] and bot["requirements"] == ["requests"]


def test_scan_multi_bot_repo(tmp_path):
    inner = write_bot_zip(tmp_path / "legacy.ibot", NESTED_INNER)
    layout = dict(MULTI_BOT)
    layout["repo-main/packs/legacy.ibot"] = inner.read_bytes()
    archive = write_bot_zip(tmp_path / "multi.zip", layout)
    scan = ghscan.scan_zip_for_bots(archive)
    assert scan["ok"] and scan["bot_count"] == 2
    dirs = {b["dir"] for b in scan["bots"]}
    assert dirs == {"alpha", "beta"}          # top folder stripped
    assert scan["archive_count"] == 1
    assert scan["archives"][0]["path"] == "packs/legacy.ibot"


def test_scan_invalid_manifest_reported(tmp_path):
    archive = write_bot_zip(tmp_path / "bad.zip", {
        "bot.json": "{not json",
        "main.py": MAIN,
    })
    scan = ghscan.scan_zip_for_bots(archive)
    assert scan["ok"] and scan["bot_count"] == 1
    bot = scan["bots"][0]
    assert not bot["valid"] and bot["errors"]


def test_scan_missing_entrypoint(tmp_path):
    archive = write_bot_zip(tmp_path / "noentry.zip", {
        "bot.json": json.dumps(MANIFEST),
        "other.py": MAIN,
    })
    scan = ghscan.scan_zip_for_bots(archive)
    bot = scan["bots"][0]
    assert not bot["entry_ok"] and not bot["valid"]


def test_scan_subpath_filter(tmp_path):
    archive = write_bot_zip(tmp_path / "multi.zip", MULTI_BOT)
    scan = ghscan.scan_zip_for_bots(archive, subpath="beta")
    assert [b["dir"] for b in scan["bots"]] == ["beta"]


def test_scan_subpath_traversal_refused(tmp_path):
    archive = write_bot_zip(tmp_path / "multi.zip", MULTI_BOT)
    scan = ghscan.scan_zip_for_bots(archive, subpath="../evil")
    assert not scan["ok"]


def test_scan_no_bots_hint(tmp_path):
    archive = write_bot_zip(tmp_path / "empty.zip", {"README.md": "nothing here"})
    scan = ghscan.scan_zip_for_bots(archive)
    assert scan["ok"] and scan["bot_count"] == 0 and scan["hint"]


def test_scan_unsafe_members_refused(tmp_path):
    archive = write_bot_zip(tmp_path / "evil.zip", {
        "../evil.txt": "boom",
        "bot.json": json.dumps(MANIFEST),
    })
    scan = ghscan.scan_zip_for_bots(archive)
    assert not scan["ok"] and "unsafe" in scan["errors"][0]


def test_scan_not_a_zip(tmp_path):
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"definitely not a zip")
    assert not ghscan.scan_zip_for_bots(junk)["ok"]


# --------------------------------------------------------------------- #
# importer: subtree + packaged member                                    #
# --------------------------------------------------------------------- #

def test_import_subtree_success(tmp_path):
    archive = write_bot_zip(tmp_path / "multi.zip", MULTI_BOT)
    bots_root = tmp_path / "bots"
    result = import_bot_from_zip_subtree(archive, "alpha", bots_root)
    assert result["ok"] and result["bot_id"] == "scan-bot", result
    assert (bots_root / "scan-bot" / "main.py").is_file()
    assert not (bots_root / "scan-bot" / "beta").exists()


def test_import_subtree_overwrite_semantics(tmp_path):
    archive = write_bot_zip(tmp_path / "multi.zip", MULTI_BOT)
    bots_root = tmp_path / "bots"
    assert import_bot_from_zip_subtree(archive, "beta", bots_root)["ok"]
    again = import_bot_from_zip_subtree(archive, "beta", bots_root)
    assert not again["ok"] and "already installed" in again["errors"][0]
    forced = import_bot_from_zip_subtree(archive, "beta", bots_root, overwrite=True)
    assert forced["ok"] and forced["bot_id"] == "beta-bot"


def test_import_subtree_unknown_dir_lists_available(tmp_path):
    archive = write_bot_zip(tmp_path / "multi.zip", MULTI_BOT)
    result = import_bot_from_zip_subtree(archive, "ghost", tmp_path / "bots")
    assert not result["ok"] and "alpha" in result["errors"][0]


def test_import_subtree_refuses_traversal(tmp_path):
    archive = write_bot_zip(tmp_path / "multi.zip", MULTI_BOT)
    for evil in ("../evil", "/abs", "a\\b", ""):
        result = import_bot_from_zip_subtree(archive, evil, tmp_path / "bots")
        assert not result["ok"], evil


def test_import_subtree_rejects_bad_file_types(tmp_path):
    archive = write_bot_zip(tmp_path / "exe.zip", {
        "README.md": "root doc keeps the top folder unstripped",
        "alpha/bot.json": json.dumps(MANIFEST),
        "alpha/main.py": MAIN,
        "alpha/tool.exe": "MZ...",
    })
    result = import_bot_from_zip_subtree(archive, "alpha", tmp_path / "bots")
    assert not result["ok"] and "not allowed" in result["errors"][0]


def test_import_zip_member_nested_ibot(tmp_path, nested_zip):
    # The outer archive is top-stripped (bundle/* -> *), so the scanner
    # reports the member as "helper.ibot" — the same name the importer accepts.
    result = import_zip_member(nested_zip, "helper.ibot", tmp_path / "bots")
    assert result["ok"] and result["bot_id"] == "inner-bot", result
    assert (tmp_path / "bots" / "inner-bot" / "main.py").is_file()


def test_import_zip_member_not_found(tmp_path, nested_zip):
    result = import_zip_member(nested_zip, "ghost.ibot", tmp_path / "bots")
    assert not result["ok"] and "not found" in result["errors"][0]


def test_import_zip_member_size_cap(tmp_path, nested_zip):
    result = import_zip_member(
        nested_zip, "helper.ibot", tmp_path / "bots", limits={"max_zip_bytes": 8},
    )
    assert not result["ok"] and "too large" in result["errors"][0]


def test_import_zip_member_non_archive_refused(tmp_path, nested_zip):
    result = import_zip_member(nested_zip, "notes.txt", tmp_path / "bots")
    assert not result["ok"] and ".zip/.ibot" in result["errors"][0]


# --------------------------------------------------------------------- #
# host_api: scan + import selected                                       #
# --------------------------------------------------------------------- #

def _serve(server, payloads, path, body):
    payloads[path] = body


def test_github_scan_and_import_flow(zip_server, tmp_path):
    server, payloads = zip_server
    payloads["/multi.zip"] = write_bot_zip(tmp_path / "m.zip", MULTI_BOT).read_bytes()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    host_api.configure(tmp_path / "data")

    scan = host_api.github_scan(f"{base}/multi.zip")
    assert scan["ok"] and scan["bot_count"] == 2, scan
    assert scan["resolved"]["summary"].endswith("multi.zip")
    cache = tmp_path / "data" / "downloads" / "ghscan-latest.zip"
    assert cache.is_file()

    # Import ONLY alpha — prove the cache is reused by killing the server.
    server.shutdown()
    result = host_api.github_import_selected(f"{base}/multi.zip", ["alpha"])
    assert result["ok"] and result["imported"] == 1, result
    assert result["bot_ids"] == ["scan-bot"]
    assert host_api.bot_status("scan-bot")["ok"]

    # Unknown paths are reported per item, not as a global crash; beta is
    # still importable (never touched before), the ghost path is not.
    result = host_api.github_import_selected(
        f"{base}/multi.zip", ["beta", "nope/ghost"],
    )
    assert not result["ok"] and result["failed"] == 1 and result["imported"] == 1
    assert "not found" in result["results"][1]["errors"][0]

    # Re-import without overwrite is refused per item (alpha exists now).
    result = host_api.github_import_selected(f"{base}/multi.zip", ["alpha"])
    assert not result["ok"] and "already installed" in result["results"][0]["errors"][0]

    # JSON string input works too (Chaquopy bridge passes JSON).
    result = host_api.github_import_selected(
        f"{base}/multi.zip", json.dumps(["beta"]), overwrite=True,
    )
    assert result["ok"] and "beta-bot" in result["bot_ids"]


def test_github_scan_import_root_bot(zip_server, tmp_path):
    server, payloads = zip_server
    payloads["/root.zip"] = write_bot_zip(tmp_path / "r.zip", ROOT_BOT).read_bytes()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    host_api.configure(tmp_path / "data2")

    scan = host_api.github_scan(f"{base}/root.zip")
    assert scan["ok"] and scan["bots"][0]["dir"] == ""

    result = host_api.github_import_selected(f"{base}/root.zip", [""])
    assert result["ok"] and result["bot_ids"] == ["scan-bot"]


def test_github_scan_404(zip_server, tmp_path):
    server, payloads = zip_server
    base = f"http://127.0.0.1:{server.server_address[1]}"
    host_api.configure(tmp_path / "data3")
    result = host_api.github_scan(f"{base}/missing.zip")
    assert not result["ok"] and any("404" in e for e in result["errors"])


def test_github_import_requires_selection(zip_server, tmp_path):
    result = host_api.github_import_selected("https://example.com/x.zip", [])
    assert not result["ok"]
    result = host_api.github_import_selected("https://example.com/x.zip", "not-json")
    assert not result["ok"]
