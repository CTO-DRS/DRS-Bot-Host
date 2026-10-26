"""GitHub link scanner (v1.8): paste a link, auto-detect every bot inside.

The feature the Android "Import" screen and the CLI are built on:

1. ``parse_github_url`` understands every useful link shape:

   - ``github.com/<owner>/<repo>``                        repo (default branch)
   - ``github.com/<owner>/<repo>/tree/<ref>[/sub/dir]``   branch + optional subfolder
   - ``github.com/<owner>/<repo>/blob/<ref>/<path>.zip``  a single packaged file
   - ``github.com/<owner>/<repo>/releases/download/...``  release asset (direct)
   - ``github.com/<owner>/<repo>/releases/latest``        resolved via the API
   - ``github.com/<owner>/<repo>/archive/*.zip``          direct
   - ``raw.githubusercontent.com/<o>/<r>/<ref>/<f>.zip``  direct
   - ``codeload.github.com/.../zip/...``                  direct
   - any other http(s) URL ending ``.zip`` / ``.ibot``    direct

   ``.ibot`` is the canonical DRS bot-package extension (a zip with a
   ``bot.json`` manifest inside) and is accepted everywhere ``.zip`` is.

2. ``fetch_for_scan`` downloads the archive ONCE with the same hard size
   cap as every other download. Branch refs with slashes are resolved by
   probing codeload (injectable ``probe`` callable; no API quota burned).

3. ``scan_zip_for_bots`` finds EVERY ``bot.json`` in the archive
   (multi-bot repos), validates each manifest with the strict importer
   rules, reports entrypoint presence / requirements / sizes, and lists
   nested ``*.zip`` / ``*.ibot`` files as separate import candidates.

Nothing here trusts the archive: the actual import re-runs the full
hardened importer pipeline (zip-slip, extension allowlist, size limits,
manifest validation) via ``importer.import_bot_from_zip_subtree``.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .importer import _member_ok, _parse_manifest_bytes, _strip_root

IBOT_SUFFIXES = (".zip", ".ibot")
GITHUB_HOSTS = {"github.com", "www.github.com"}
KNOWN_HOSTS = GITHUB_HOSTS | {
    "raw.githubusercontent.com",
    "codeload.github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "media.githubusercontent.com",
}


# --------------------------------------------------------------------- #
# URL parsing                                                            #
# --------------------------------------------------------------------- #

def _safe_subpath(segments) -> tuple:
    """Join ``segments`` into an archive-relative subpath, refusing traversal."""
    if any(
        segment in ("", ".", "..") or "\\" in segment or ":" in segment
        for segment in segments
    ):
        return False, ["subpath contains unsafe segments"]
    return True, "/".join(segments)


def parse_github_url(url, *, probe=None, fetch_json=None) -> dict:
    """Classify a pasted link. Injectable ``probe``/``fetch_json`` keep this
    network-free for tests; both default to real HTTP helpers."""
    raw = str(url or "").strip()
    if not raw:
        return {"ok": False, "errors": ["empty URL"]}
    if "://" not in raw:
        first = urlsplit("https://" + raw)
        if first.netloc.lower() in KNOWN_HOSTS:
            raw = "https://" + raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    if scheme not in ("http", "https"):
        return {"ok": False, "errors": [f"unsupported scheme (http/https only): {raw}"]}

    segments = [s for s in parts.path.split("/") if s]
    base = {"ok": True, "url": raw, "host": host, "subpath": None, "ref": None, "file": None}

    # --- raw / codeload / non-github direct zips ----------------------- #
    if host in ("raw.githubusercontent.com", "codeload.github.com"):
        return {**base, "kind": "zip", "download_url": raw,
                "summary": segments[-1] if segments else raw}

    if host not in GITHUB_HOSTS:
        name = segments[-1] if segments else ""
        if name.lower().endswith(IBOT_SUFFIXES):
            return {**base, "kind": "zip", "download_url": raw, "summary": name}
        return {
            "ok": False,
            "errors": [
                "paste a GitHub link (repo, /tree/…, /blob/…, release asset) "
                "or a direct .zip/.ibot URL"
            ],
        }

    if len(segments) < 2:
        return {"ok": False, "errors": [f"GitHub link needs owner/repo: {raw}"]}
    owner, repo = segments[0], segments[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    head = {**base, "owner": owner, "repo": repo}

    rest = segments[2:]
    if not rest:
        return {**head, "kind": "repo", "summary": f"{owner}/{repo} (default branch)"}

    if rest[0] == "tree" and len(rest) >= 2:
        ref, ref_spec, subpath = _resolve_tree_ref(owner, repo, rest[1:], probe=probe)
        if ref is None:
            return {
                "ok": False,
                "errors": [
                    "could not resolve the branch/tag of this /tree/ link "
                    "(tried the prefixes as branch and tag names)"
                ],
            }
        summary = f"{owner}/{repo} @ {ref}"
        if subpath:
            summary += f" · {subpath}"
        return {
            **head,
            "kind": "tree",
            "ref": ref,
            "ref_spec": ref_spec,
            "subpath": subpath,
            "summary": summary,
        }

    if rest[0] == "blob" and len(rest) >= 3:
        name = rest[-1]
        if not name.lower().endswith(IBOT_SUFFIXES):
            return {
                "ok": False,
                "errors": [
                    "/blob/ links are only followed for .zip/.ibot files; "
                    "use the repo or /tree/ link for source"
                ],
            }
        ref, path = _resolve_blob_ref(owner, repo, rest[1:], probe=probe)
        if ref is None:
            return {"ok": False, "errors": ["could not resolve the /blob/ link"]}
        return {
            **head,
            "kind": "zip",
            "ref": ref,
            "file": path,
            "download_url": (
                f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
            ),
            "summary": f"{owner}/{repo} file {path} @ {ref}",
        }

    if rest[0] == "releases":
        if len(rest) >= 3 and rest[1] == "download":
            return {**head, "kind": "zip", "download_url": raw,
                    "summary": f"{owner}/{repo} release asset {rest[-1]}"}
        # .../releases or .../releases/latest — resolve the newest zip asset.
        tag, asset_url = _resolve_latest_release(owner, repo, fetch_json=fetch_json)
        if asset_url is None:
            return {
                "ok": False,
                "errors": [
                    "no published release with a .zip/.ibot asset found for "
                    f"{owner}/{repo}"
                ],
            }
        return {**head, "kind": "zip", "download_url": asset_url,
                "summary": f"{owner}/{repo} release {tag} · {asset_url.rsplit('/', 1)[-1]}"}

    if rest[0] == "archive" and rest[-1].lower().endswith(IBOT_SUFFIXES):
        return {**head, "kind": "zip", "download_url": raw,
                "summary": f"{owner}/{repo} archive {rest[-1]}"}

    return {
        "ok": False,
        "errors": [
            "unsupported GitHub link shape — use the repo, /tree/<branch>, "
            "/blob/<branch>/<file>.zip, releases asset or archive link"
        ],
    }


def _ref_candidates(segments):
    """Progressive ref candidates for /tree/ and /blob/ links (shortest first).

    Yields ``(split_index, codeload_spec, prefix)`` — branches are probed
    before tags for each prefix length.
    """
    for i in range(1, len(segments) + 1):
        prefix = "/".join(segments[:i])
        yield i, f"refs/heads/{prefix}", prefix
        yield i, f"refs/tags/{prefix}", prefix


def _probe_codeload(owner, repo, spec, *, probe=None) -> bool:
    probe = probe or _default_probe
    url = f"https://codeload.github.com/{owner}/{repo}/zip/{spec}"
    try:
        return bool(probe(url))
    except Exception:  # noqa: BLE001 - probe failures are just "no"
        return False


def _resolve_tree_ref(owner, repo, segments, *, probe=None):
    """Return ``(ref, ref_spec, subpath)`` for the segments after ``/tree/``.

    Branch and tag names may contain slashes, so the boundary between the
    ref and the subfolder is probed against codeload (HEAD, no body). The
    injectable ``probe`` makes this fully testable offline. ``ref_spec``
    is the exact codeload spec (``refs/heads/…`` or ``refs/tags/…``).
    """
    for i, spec, prefix in _ref_candidates(segments):
        if _probe_codeload(owner, repo, spec, probe=probe):
            sub = segments[i:]
            if sub:
                ok, joined_or_errors = _safe_subpath(sub)
                if not ok:
                    return None, None, None
                return prefix, spec, joined_or_errors
            return prefix, spec, None
    return None, None, None


def _resolve_blob_ref(owner, repo, segments, *, probe=None):
    """Return ``(ref, filepath)`` for the segments after ``/blob/``."""
    for i, spec, prefix in _ref_candidates(segments[:-1]):
        if _probe_codeload(owner, repo, spec, probe=probe):
            path = "/".join(segments[i:])
            if _safe_subpath(segments[i:])[0]:
                return prefix, path
    return None, None


def _default_probe(url) -> bool:
    import urllib.request

    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return getattr(response, "status", 200) == 200
    except Exception:  # noqa: BLE001
        return False


def _resolve_latest_release(owner, repo, *, fetch_json=None):
    """Return ``(tag, asset_url)`` for the newest release zip/ibot asset."""
    fetch_json = fetch_json or _default_fetch_json
    data = fetch_json(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
    if not isinstance(data, dict):
        return None, None
    for asset in data.get("assets") or []:
        name = str(asset.get("name", "")).lower()
        url = asset.get("browser_download_url")
        if name.endswith(IBOT_SUFFIXES) and url:
            return data.get("tag_name", "latest"), url
    return None, None


def _default_fetch_json(url):
    import urllib.request

    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------- #
# Download-for-scan                                                      #
# --------------------------------------------------------------------- #

def fetch_for_scan(
    url,
    dest_dir,
    *,
    max_bytes: int,
    timeout: float = 30.0,
    probe=None,
    fetch_json=None,
) -> dict:
    """Parse ``url``, download the archive once, return scan-ready info."""
    from .downloader import download_zip  # local import: avoids a cycle

    parsed = parse_github_url(url, probe=probe, fetch_json=fetch_json)
    if not parsed.get("ok"):
        return parsed
    target = parsed.get("download_url")
    if not target:
        if parsed["kind"] == "repo":
            # api zipball redirect resolves the default branch (anonymous).
            target = f"https://api.github.com/repos/{parsed['owner']}/{parsed['repo']}/zipball"
        elif parsed["kind"] == "tree":
            target = (
                f"https://codeload.github.com/{parsed['owner']}/{parsed['repo']}"
                f"/zip/{parsed['ref_spec']}"
            )
        else:  # pragma: no cover - parse guarantees one of the above
            return {"ok": False, "errors": ["no download target for this link"]}
    fetched = download_zip(target, dest_dir, max_bytes=max_bytes, timeout=timeout)
    if not fetched.get("ok"):
        return fetched
    fetched["resolved"] = {
        key: parsed.get(key)
        for key in ("kind", "owner", "repo", "ref", "ref_spec", "subpath",
                    "file", "summary", "url")
    }
    return fetched


# --------------------------------------------------------------------- #
# Archive scanning                                                       #
# --------------------------------------------------------------------- #

def scan_zip_for_bots(zip_path, subpath=None, *, limits=None) -> dict:
    """Find and validate every bot inside a downloaded archive.

    Returns ``{"ok": True, "bots": [...], "archives": [...], "top": ...}``
    or ``{"ok": False, "errors": [...]}``. Each bot entry:

    ``{"dir", "id", "name", "description", "entrypoint", "entry_ok",
       "requirements", "files", "bytes", "valid", "errors"}``
    """
    from .importer import DEFAULT_LIMITS, IGNORED_DIRS

    limits = {**DEFAULT_LIMITS, **(limits or {})}
    zpath = Path(zip_path)
    if not zpath.is_file():
        return {"ok": False, "errors": [f"archive not found: {zpath}"]}

    if subpath is not None:
        subpath = str(subpath).strip().strip("/")
        if subpath:
            ok, joined_or_errors = _safe_subpath(subpath.split("/"))
            if not ok:
                return {"ok": False, "errors": joined_or_errors}
            subpath = joined_or_errors
        else:
            subpath = None

    try:
        with zipfile.ZipFile(zpath) as archive:
            infos = [i for i in archive.infolist() if not i.is_dir()]
            names = [i.filename for i in infos]
            unsafe = [n for n in names if not _member_ok(n)]
            if unsafe:
                return {
                    "ok": False,
                    "errors": ["unsafe path(s) in archive: " + ", ".join(unsafe[:5])],
                }
            top, mapping = _strip_root(names)
            rel_names = [mapping[n] for n in names]
            original = {mapping[n]: n for n in names}

            def under_sub(rel: str) -> bool:
                if subpath is None:
                    return True
                return rel == subpath or rel.startswith(subpath + "/")

            sizes = {mapping[i.filename]: i.file_size for i in infos}

            bots = []
            for rel in sorted(rel_names):
                if rel.endswith("/") or PurePosixPath(rel).name != "bot.json":
                    continue
                bot_dir = str(PurePosixPath(rel).parent) if str(PurePosixPath(rel).parent) != "." else ""
                if not under_sub(bot_dir):
                    continue
                files = 0
                total = 0
                for other in rel_names:
                    if other == rel:
                        continue
                    if bot_dir == "":
                        files += 1
                        total += sizes.get(other, 0)
                    elif other == bot_dir or other.startswith(bot_dir + "/"):
                        files += 1
                        total += sizes.get(other, 0)
                manifest, errors = _parse_manifest_bytes(archive.read(original[rel]))
                entry_ok = False
                if manifest is not None:
                    entry_rel = f"{bot_dir}/{manifest.entrypoint}" if bot_dir else manifest.entrypoint
                    entry_ok = entry_rel in rel_names
                bots.append({
                    "dir": bot_dir,
                    "id": manifest.id if manifest else None,
                    "name": manifest.name if manifest else None,
                    "description": manifest.description if manifest else "",
                    "entrypoint": manifest.entrypoint if manifest else None,
                    "entry_ok": entry_ok,
                    "requirements": list(manifest.requirements) if manifest else [],
                    "files": files,
                    "bytes": total,
                    "valid": manifest is not None and entry_ok and files <= limits["max_files"],
                    "errors": errors,
                })

            archives = [
                {"path": rel, "bytes": sizes.get(rel, 0)}
                for rel in sorted(rel_names)
                if rel.lower().endswith(IBOT_SUFFIXES) and under_sub(rel)
            ]

            hint = None
            if not bots and not archives:
                hint = (
                    f"no bot.json found{' under ' + subpath if subpath else ''} — "
                    "the archive has no DRS bots (look for a subfolder that "
                    "contains bot.json + main.py, or a packaged .zip/.ibot)"
                )
            return {
                "ok": True,
                "top": top,
                "subpath": subpath,
                "bots": bots,
                "archives": archives,
                "bot_count": len(bots),
                "archive_count": len(archives),
                "hint": hint,
            }
    except zipfile.BadZipFile:
        return {"ok": False, "errors": ["not a valid zip archive"]}


def available_bot_dirs(scan: dict) -> list:
    """Dirs that can be passed to ``import_bot_from_zip_subtree``."""
    return [b["dir"] for b in scan.get("bots", []) if b.get("dir")]
