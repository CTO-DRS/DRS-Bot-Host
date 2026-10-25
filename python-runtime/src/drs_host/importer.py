"""Safe ZIP / folder importer for bots.

Every import passes through the same checks regardless of source:

- archive size, decompressed size and file-count limits (zip-bomb guard)
- path-traversal protection (``..``, absolute paths, backslashes, drive letters)
- extension whitelist
- strict ``bot.json`` manifest validation
- entrypoint existence check
- id collision handling with explicit ``overwrite``

A zip whose entries share a single top-level folder is normalized, so both
``bot.json|main.py`` and ``my-bot/bot.json|my-bot/main.py`` layouts import.
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from .manifest import validate_manifest

DEFAULT_LIMITS = {
    "max_zip_bytes": 25 * 1024 * 1024,
    "max_total_bytes": 100 * 1024 * 1024,
    "max_files": 500,
}
ALLOWED_SUFFIXES = {
    ".py",
    ".json",
    ".txt",
    ".md",
    ".csv",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".toml",
}
IGNORED_DIRS = {"__pycache__", ".git", ".svn", ".idea", "__MACOSX"}


def _member_ok(name: str) -> bool:
    """Reject absolute paths, traversal, backslashes and drive letters."""
    if not name:
        return False
    if name.startswith("/") or "\\" in name:
        return False
    first = name.split("/", 1)[0]
    if ":" in first:
        return False
    if any(part == ".." for part in PurePosixPath(name).parts):
        return False
    return True


def _strip_root(names: list) -> tuple:
    """If all entries share one top-level *folder*, strip it.

    A top-level folder counts only when at least one entry is nested under
    it, so a zip that is just ``bot.json`` at the root is left untouched.

    Returns ``(top_or_None, {zip_name: relative_path})``.
    """
    tops: dict = {}
    for name in names:
        if not name.strip("/"):
            continue
        parts = PurePosixPath(name).parts
        tops.setdefault(parts[0], 0)
        if len(parts) >= 2:
            tops[parts[0]] += 1
    if len(tops) == 1 and sum(tops.values()) > 0:
        top = next(iter(tops))
        if top in IGNORED_DIRS:
            return None, {n: n for n in names}
        mapping = {n: n[len(top):].lstrip("/") for n in names}
        return top, mapping
    return None, {n: n for n in names}


def _limits_overlay(limits) -> dict:
    overlay = dict(DEFAULT_LIMITS)
    if limits:
        overlay.update(limits)
    return overlay


def _parse_manifest_bytes(raw: bytes):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"bot.json is not valid JSON: {exc}"]
    return validate_manifest(data)


def _write_normalized_manifest(dest: Path, manifest) -> None:
    (dest / "bot.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def import_zip(zip_path, bots_root, *, overwrite: bool = False, limits=None) -> dict:
    """Extract a bot zip into ``bots_root/<id>`` after full validation."""
    limits = _limits_overlay(limits)
    zpath = Path(zip_path)
    if not zpath.is_file():
        return {"ok": False, "errors": [f"zip file not found: {zpath}"]}
    if zpath.stat().st_size > limits["max_zip_bytes"]:
        return {
            "ok": False,
            "errors": [
                f"zip file too large: {zpath.stat().st_size} bytes "
                f"(max {limits['max_zip_bytes']})"
            ],
        }

    try:
        with zipfile.ZipFile(zpath) as archive:
            infos = archive.infolist()
            file_infos = [i for i in infos if not i.is_dir()]
            if len(file_infos) > limits["max_files"]:
                return {
                    "ok": False,
                    "errors": [
                        f"too many files: {len(file_infos)} (max {limits['max_files']})"
                    ],
                }
            total = sum(i.file_size for i in file_infos)
            if total > limits["max_total_bytes"]:
                return {
                    "ok": False,
                    "errors": [
                        f"decompressed size too large: {total} bytes "
                        f"(max {limits['max_total_bytes']})"
                    ],
                }

            names = [i.filename for i in infos]
            unsafe = [n for n in names if not _member_ok(n)]
            if unsafe:
                return {
                    "ok": False,
                    "errors": ["unsafe path(s) in zip: " + ", ".join(unsafe[:5])],
                }

            _, mapping = _strip_root(names)
            manifest_name = next(
                (n for n in names if not n.endswith("/") and mapping.get(n) == "bot.json"),
                None,
            )
            if manifest_name is None:
                return {"ok": False, "errors": ["bot.json not found at the root of the zip"]}

            manifest, errors = _parse_manifest_bytes(archive.read(manifest_name))
            if manifest is None:
                return {"ok": False, "errors": errors}

            for info in file_infos:
                rel = mapping[info.filename]
                if rel == "bot.json":
                    continue
                if Path(rel).suffix.lower() not in ALLOWED_SUFFIXES:
                    return {"ok": False, "errors": [f"file type not allowed: {rel}"]}

            dest = Path(bots_root) / manifest.id
            if dest.exists():
                if not overwrite:
                    return {
                        "ok": False,
                        "errors": [
                            f"bot id already installed: {manifest.id} (use overwrite=True)"
                        ],
                    }
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)

            dest_real = str(dest.resolve())
            copied = 0
            for info in file_infos:
                rel = mapping[info.filename]
                target = dest / rel
                resolved = str(target.resolve())
                if not (resolved == dest_real or resolved.startswith(dest_real + os.sep)):
                    shutil.rmtree(dest, ignore_errors=True)
                    return {"ok": False, "errors": [f"unsafe resolved path: {rel}"]}
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                copied += 1

            if not (dest / manifest.entrypoint).is_file():
                shutil.rmtree(dest, ignore_errors=True)
                return {
                    "ok": False,
                    "errors": [f"entrypoint not found in bot folder: {manifest.entrypoint}"],
                }

            _write_normalized_manifest(dest, manifest)
            return {
                "ok": True,
                "bot_id": manifest.id,
                "manifest": manifest.to_dict(),
                "files": copied,
                "bytes": total,
            }
    except zipfile.BadZipFile:
        return {"ok": False, "errors": ["not a valid zip archive"]}


def import_folder(src, bots_root, *, overwrite: bool = False, limits=None) -> dict:
    """Copy a bot folder into ``bots_root/<id>`` after full validation.

    If ``src`` itself has no ``bot.json`` but exactly one sub-folder does,
    that sub-folder is used (folder-picker ergonomics).
    """
    limits = _limits_overlay(limits)
    src = Path(src)
    if not src.is_dir():
        return {"ok": False, "errors": [f"folder not found: {src}"]}

    if not (src / "bot.json").is_file():
        candidates = [
            child
            for child in sorted(src.iterdir())
            if child.is_dir() and (child / "bot.json").is_file()
        ]
        if len(candidates) == 1:
            src = candidates[0]
        else:
            return {
                "ok": False,
                "errors": ["bot.json not found in the folder (or in exactly one sub-folder)"],
            }

    try:
        data = json.loads((src / "bot.json").read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"bot.json is not valid JSON: {exc}"]}
    manifest, errors = validate_manifest(data)
    if manifest is None:
        return {"ok": False, "errors": errors}

    files = [
        path
        for path in sorted(src.rglob("*"))
        if path.is_file()
        and not (set(path.relative_to(src).parts) & IGNORED_DIRS)
        and path.suffix.lower() != ".pyc"
    ]
    if len(files) > limits["max_files"]:
        return {
            "ok": False,
            "errors": [f"too many files: {len(files)} (max {limits['max_files']})"],
        }
    total = sum(path.stat().st_size for path in files)
    if total > limits["max_total_bytes"]:
        return {
            "ok": False,
            "errors": [f"total size too large: {total} bytes (max {limits['max_total_bytes']})"],
        }
    for path in files:
        rel = path.relative_to(src)
        if rel.name != "bot.json" and path.suffix.lower() not in ALLOWED_SUFFIXES:
            return {"ok": False, "errors": [f"file type not allowed: {rel}"]}

    dest = Path(bots_root) / manifest.id
    if dest.exists():
        if not overwrite:
            return {
                "ok": False,
                "errors": [
                    f"bot id already installed: {manifest.id} (use overwrite=True)"
                ],
            }
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".idea"),
    )

    if not (dest / manifest.entrypoint).is_file():
        shutil.rmtree(dest, ignore_errors=True)
        return {
            "ok": False,
            "errors": [f"entrypoint not found in bot folder: {manifest.entrypoint}"],
        }

    _write_normalized_manifest(dest, manifest)
    return {
        "ok": True,
        "bot_id": manifest.id,
        "manifest": manifest.to_dict(),
        "files": len(files),
        "bytes": total,
    }


def peek_zip(zip_path) -> tuple:
    """Validate the manifest inside a zip without extracting anything."""
    zpath = Path(zip_path)
    if not zpath.is_file():
        return None, [f"zip file not found: {zpath}"]
    try:
        with zipfile.ZipFile(zpath) as archive:
            names = archive.namelist()
            unsafe = [n for n in names if not _member_ok(n)]
            if unsafe:
                return None, ["unsafe path(s) in zip: " + ", ".join(unsafe[:5])]
            _, mapping = _strip_root(names)
            manifest_name = next(
                (n for n in names if not n.endswith("/") and mapping.get(n) == "bot.json"),
                None,
            )
            if manifest_name is None:
                return None, ["bot.json not found at the root of the zip"]
            return _parse_manifest_bytes(archive.read(manifest_name))
    except zipfile.BadZipFile:
        return None, ["not a valid zip archive"]


def peek_folder(folder) -> tuple:
    """Validate the manifest inside a folder without copying anything."""
    src = Path(folder)
    if not src.is_dir():
        return None, [f"folder not found: {src}"]
    if not (src / "bot.json").is_file():
        candidates = [
            child
            for child in sorted(src.iterdir())
            if child.is_dir() and (child / "bot.json").is_file()
        ]
        if len(candidates) == 1:
            src = candidates[0]
        else:
            return None, ["bot.json not found in the folder (or in exactly one sub-folder)"]
    try:
        data = json.loads((src / "bot.json").read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"bot.json is not valid JSON: {exc}"]
    return validate_manifest(data)
