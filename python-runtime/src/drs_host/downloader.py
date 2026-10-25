"""Download-a-bot support (v1.2): fetch a bot zip over HTTP(S) and import it.

``github_zip_url`` rewrites friendly GitHub links into direct zip URLs:

- ``github.com/<owner>/<repo>``            -> ``api.github.com/.../zipball``
  (follows the redirect to the default branch; anonymous, rate-limited)
- ``github.com/<owner>/<repo>/tree/<ref>`` -> codeload zipball of that ref
- ``github.com/.../archive/<something>.zip`` and release asset links are
  kept as-is (already direct zips)

``download_zip`` streams the response to disk with a hard size cap (zip-bomb
guard at the transport level) and hands the file to the hardened importer in
``importer.py`` — the archive itself is never trusted.
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

USER_AGENT = "DRS-Bot-Host"
CHUNK = 64 * 1024


def github_zip_url(url: str) -> str:
    """Rewrite a GitHub repo/tree URL into a direct zip download URL.

    Non-GitHub URLs and already-direct links are returned unchanged
    (stripped of whitespace). No network access happens here.
    """
    cleaned = (url or "").strip()
    parts = urlsplit(cleaned)
    if parts.netloc.lower() not in {"github.com", "www.github.com"}:
        return cleaned
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 2:
        return cleaned
    owner, repo = segments[0], segments[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if len(segments) == 2:
        # Default branch unknown — the API zipball endpoint redirects for us.
        return f"https://api.github.com/repos/{owner}/{repo}/zipball"
    if segments[2] == "tree" and len(segments) >= 4:
        ref = "/".join(segments[3:])
        return f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}"
    return cleaned


def download_zip(
    url,
    dest_dir,
    *,
    max_bytes: int,
    timeout: float = 30.0,
) -> dict:
    """Stream ``url`` into ``dest_dir`` as a temporary zip file.

    Returns ``{"ok": True, "path": ..., "bytes": n}`` or the standard
    ``{"ok": False, "errors": [...]}`` shape. Only http/https is allowed and
    the transfer is aborted as soon as ``max_bytes`` is exceeded.
    """
    target = github_zip_url(str(url))
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return {"ok": False, "errors": [f"unsupported URL (http/https only): {url}"]}

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    path = dest_dir / f"url-import-{stamp}-{int(time.time() * 1000) % 10000}.zip"

    request = urllib.request.Request(
        target,
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip, */*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                return {
                    "ok": False,
                    "errors": [f"download failed with HTTP {status}"],
                }
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                return {
                    "ok": False,
                    "errors": [
                        f"download too large: {declared} bytes (max {max_bytes})"
                    ],
                }
            received = 0
            with open(path, "wb") as out:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > max_bytes:
                        out.close()
                        path.unlink(missing_ok=True)
                        return {
                            "ok": False,
                            "errors": [
                                f"download exceeded the size limit "
                                f"({max_bytes} bytes); aborted"
                            ],
                        }
                    out.write(chunk)
    except Exception as exc:  # noqa: BLE001 - network errors become rejections
        path.unlink(missing_ok=True)
        return {"ok": False, "errors": [f"download failed: {exc}"]}

    if received == 0:
        path.unlink(missing_ok=True)
        return {"ok": False, "errors": ["downloaded file is empty"]}
    return {"ok": True, "path": str(path), "bytes": received, "url": target}


def import_url(
    url,
    supervisor,
    *,
    overwrite: bool = False,
    timeout: float = 30.0,
    cleanup: bool = True,
) -> dict:
    """Download a bot zip and import it through the supervisor's pipeline.

    The downloaded file is validated by the same hardened importer used for
    SAF imports (manifest checks, zip-slip protection, size limits).
    """
    limits = supervisor.limits_overlay()
    downloads_dir = supervisor.bots_root.parent / "downloads"
    fetched = download_zip(url, downloads_dir, max_bytes=limits["max_zip_bytes"], timeout=timeout)
    if not fetched.get("ok"):
        return fetched
    try:
        return supervisor.import_zip(fetched["path"], overwrite=overwrite)
    finally:
        if cleanup:
            Path(fetched["path"]).unlink(missing_ok=True)


__all__ = ["github_zip_url", "download_zip", "import_url", "USER_AGENT"]
