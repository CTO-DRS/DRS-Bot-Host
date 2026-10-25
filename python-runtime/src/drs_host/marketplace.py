"""Bot marketplace (v1.4): fetch a curated registry and install from it.

A registry is a small JSON document describing shareable bots::

    {"bots": [
        {"id": "echo-bot",
         "name": "Echo Bot",
         "description": "Replies with your message",
         "version": "1.0.0",
         "author": "DRS",
         "tags": ["demo", "starter"],
         "url": "https://github.com/.../echo-bot.zip"},
        ...
    ]}

Security posture (mirrors the rest of the runtime):

- the registry is fetched over http(s) with a hard 1 MB size cap
- every field is length-limited and sanitized; unknown keys are dropped
- entry ids must be valid bot slugs (the same rule the importer enforces)
- entry URLs must be http/https — ``file://``, ``ftp://`` and data URLs are
  rejected before anything is downloaded
- the actual bot zip still goes through the hardened importer
  (``downloader.import_url`` → ``Supervisor.import_zip``), so a malicious
  registry entry gains no new capabilities

The bundled default registry points at the project's own curated list:
``https://raw.githubusercontent.com/CTO-DRS/DRS-Bot-Host/main/registry/registry.json``
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from urllib.parse import urlsplit

from . import downloader

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/CTO-DRS/DRS-Bot-Host/main/registry/registry.json"
)

REGISTRY_MAX_BYTES = 1024 * 1024  # 1 MB — a registry is metadata, not content
MAX_ENTRIES = 200
FETCH_TIMEOUT = 20.0

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

FIELD_LIMITS = {
    "id": 64,
    "name": 120,
    "description": 600,
    "version": 40,
    "author": 120,
    "url": 500,
}
MAX_TAGS = 8
MAX_TAG_LENGTH = 32


def _clean_text(value, limit: int):
    """Sanitized string or None when the value is absent/empty/oversized."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit:
        return None
    return cleaned


def validate_entry(raw, index: int):
    """Validate one registry entry.

    Returns ``(entry_or_None, error_or_None)``. ``entry`` keeps only the
    whitelisted fields so hostile extra keys never reach the UI.
    """
    if not isinstance(raw, dict):
        return None, f"entry #{index}: not an object"
    entry = {}
    entry["id"] = _clean_text(raw.get("id"), FIELD_LIMITS["id"])
    if entry["id"] is None or not SLUG_RE.match(entry["id"]):
        return None, f"entry #{index}: id is missing or not a valid bot slug"
    entry["name"] = _clean_text(raw.get("name"), FIELD_LIMITS["name"])
    if entry["name"] is None:
        return None, f"entry #{index} ({entry['id']}): name is missing or too long"
    entry["url"] = _clean_text(raw.get("url"), FIELD_LIMITS["url"])
    if entry["url"] is None:
        return None, f"entry #{index} ({entry['id']}): url is missing or too long"
    parts = urlsplit(entry["url"])
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None, f"entry #{index} ({entry['id']}): url must be http/https"
    entry["description"] = _clean_text(
        raw.get("description"), FIELD_LIMITS["description"]
    ) or ""
    entry["version"] = _clean_text(
        raw.get("version"), FIELD_LIMITS["version"]
    ) or ""
    entry["author"] = _clean_text(raw.get("author"), FIELD_LIMITS["author"]) or ""
    tags_raw = raw.get("tags")
    tags = []
    if isinstance(tags_raw, list):
        for tag in tags_raw[:MAX_TAGS]:
            cleaned = _clean_text(tag, MAX_TAG_LENGTH)
            if cleaned:
                tags.append(cleaned)
    entry["tags"] = tags
    return entry, None


def validate_registry(document):
    """Validate a parsed registry document.

    Accepts ``{"bots": [...]}`` (preferred) or a bare top-level list.
    Returns ``(entries, errors)`` — invalid entries are skipped, never fatal
    for the rest of the list.
    """
    errors = []
    if isinstance(document, dict):
        raw_entries = document.get("bots")
    else:
        raw_entries = document
    if not isinstance(raw_entries, list):
        return [], ["registry must be an object with a 'bots' list (or a list)"]
    if len(raw_entries) > MAX_ENTRIES:
        return [], [f"registry too large: {len(raw_entries)} entries (max {MAX_ENTRIES})"]
    entries = []
    seen_ids = set()
    for index, raw in enumerate(raw_entries):
        entry, error = validate_entry(raw, index)
        if error is not None:
            errors.append(error)
            continue
        if entry["id"] in seen_ids:
            errors.append(f"entry #{index}: duplicate id '{entry['id']}'")
            continue
        seen_ids.add(entry["id"])
        entries.append(entry)
    if not entries and not errors:
        errors.append("registry contains no valid entries")
    return entries, errors


def fetch_registry(url=None, *, timeout: float = FETCH_TIMEOUT) -> dict:
    """Download, size-cap and validate a marketplace registry.

    Returns ``{"ok": True, "source": url, "count": n, "bots": [...],
    "errors": [per-entry warnings]}`` or ``{"ok": False, "errors": [...]}``.
    """
    source = (url or DEFAULT_REGISTRY_URL or "").strip()
    parts = urlsplit(source)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return {"ok": False, "errors": [f"unsupported registry URL (http/https only): {source}"]}
    request = urllib.request.Request(
        source,
        headers={
            "User-Agent": downloader.USER_AGENT,
            "Accept": "application/json, */*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                return {"ok": False, "errors": [f"registry fetch failed with HTTP {status}"]}
            payload = response.read(REGISTRY_MAX_BYTES + 1)
    except Exception as exc:  # noqa: BLE001 - network errors become rejections
        return {"ok": False, "errors": [f"registry fetch failed: {exc}"]}
    if len(payload) > REGISTRY_MAX_BYTES:
        return {"ok": False, "errors": [f"registry too large (max {REGISTRY_MAX_BYTES} bytes)"]}
    if not payload:
        return {"ok": False, "errors": ["registry response is empty"]}
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"registry is not valid JSON: {exc}"]}
    entries, errors = validate_registry(document)
    if not entries:
        return {
            "ok": False,
            "errors": errors or ["registry contains no valid entries"],
            "source": source,
        }
    return {
        "ok": True,
        "source": source,
        "count": len(entries),
        "bots": entries,
        "errors": errors,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def install_entry(url, supervisor, *, overwrite: bool = False, timeout: float = 30.0) -> dict:
    """Download a marketplace entry's zip and import it through the supervisor.

    The zip passes through the same hardened pipeline as every other import;
    the registry itself never grants extra privileges.
    """
    target = (url or "").strip()
    parts = urlsplit(downloader.github_zip_url(target))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return {"ok": False, "errors": [f"unsupported bot URL (http/https only): {target}"]}
    return downloader.import_url(target, supervisor, overwrite=overwrite, timeout=timeout)


__all__ = [
    "DEFAULT_REGISTRY_URL",
    "REGISTRY_MAX_BYTES",
    "MAX_ENTRIES",
    "fetch_registry",
    "validate_registry",
    "validate_entry",
    "install_entry",
]
