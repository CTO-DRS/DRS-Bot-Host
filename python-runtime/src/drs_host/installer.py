"""On-device requirements installer (v1.3).

Installs a bot's declared dependencies into a per-bot ``site`` directory
using pip running *in-process* (``pip._internal.cli.main``), so no subprocess
or network-capable shell is required. On Chaquopy runtimes that ship pip the
install genuinely works on the phone; where pip is absent the probe reports
it honestly instead of pretending.

Layout per bot::

    <data_dir>/site/<bot_id>/        ← pip --target destination
    <data_dir>/bots/<bot_id>/...     ← bot sources (unchanged)

The supervisor prepends the bot's site directory to ``sys.path`` for the
duration of each run (see runner.py), so installed packages are importable
by that bot without leaking into the build-time package set.

Security / resource guards:

- requirements come from ``bot.json`` (already validated as a string list)
  and/or ``requirements.txt`` inside the bot folder;
- every declared requirement must look like a plain PyPI requirement line;
  direct URLs (``http(s)://``, ``git+``, local paths, ``-r``/``-e`` flags)
  are rejected to keep installs inside the package index;
- pip output is captured (never printed) and a bounded tail is returned.
"""

from __future__ import annotations

import re
import shutil
import sys
import threading
from pathlib import Path

INSTALL_TIMEOUT_SECONDS = 600
OUTPUT_TAIL_LINES = 40
MAX_REQUIREMENTS = 50
MAX_SITE_BYTES = 512 * 1024 * 1024  # 512 MB soft cap per bot

# A conservative PyPI requirement line: name + optional extras + specifiers
# + optional environment marker. No URLs, no local paths, no options.
_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"(\[[A-Za-z0-9,._-]+\])?"
    r"([<>=!~]=?|===)?"
    r"[A-Za-z0-9._*+!-]*"
    r"(\s*;\s*.+)?$"
)
_FORBIDDEN_PREFIXES = ("-", "http://", "https://", "git+", "svn+", "hg+", "bzr+", "file:", "/")
_LOCK = threading.Lock()


class InstallError(Exception):
    pass


def pip_runtime_available() -> bool:
    """True when the running interpreter ships pip (importable)."""
    try:
        import pip  # noqa: F401

        return True
    except Exception:  # noqa: BLE001 - Chaquopy builds may omit pip
        return False


def bot_site_dir(data_dir, bot_id: str) -> Path:
    """Per-bot package installation directory."""
    return Path(data_dir) / "site" / str(bot_id)


def _parse_requirements_text(text: str, errors: list) -> list:
    requirements = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
            errors.append(f"forbidden requirement line: {line[:80]!r}")
            continue
        if not _REQUIREMENT_RE.match(line):
            errors.append(f"unparsable requirement line: {line[:80]!r}")
            continue
        requirements.append(line)
    return requirements


def collect_requirements(bot_dir: Path, manifest_requirements: list) -> tuple[list, list]:
    """Merge bot.json requirements with requirements.txt (deduplicated)."""
    errors: list = []
    declared = [str(item).strip() for item in (manifest_requirements or []) if str(item).strip()]
    parsed_file: list = []
    req_file = Path(bot_dir) / "requirements.txt"
    if req_file.is_file():
        try:
            text = req_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read requirements.txt: {exc}")
            text = ""
        parsed_file = _parse_requirements_text(text, errors)
    merged = list(dict.fromkeys(declared + parsed_file))
    if len(merged) > MAX_REQUIREMENTS:
        errors.append(
            f"too many requirements ({len(merged)} > {MAX_REQUIREMENTS})"
        )
        merged = merged[:MAX_REQUIREMENTS]
    return merged, errors


def _run_pip(
    requirements: list,
    target: Path,
    timeout: float,
    find_links: str | None = None,
) -> tuple[bool, str]:
    """Run pip in-process with a watchdog; returns (finished, combined_output)."""
    import contextlib
    import io

    from pip._internal.cli.main import main as pip_main

    args = [
        "install",
        "--no-input",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--target",
        str(target),
    ]
    if find_links:
        # Only supplied programmatically (tests / trusted hosts); never
        # reachable from bot-controlled data.
        args += ["--find-links", str(find_links)]
    args += list(requirements)
    stdout, stderr = io.StringIO(), io.StringIO()

    def _invoke():
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            pip_main(args)

    thread = threading.Thread(target=_invoke, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return False, "pip install timed out after %.0fs" % timeout
    output = (stdout.getvalue() + "\n" + stderr.getvalue()).strip()
    return True, output


def install_requirements(
    bot_id: str,
    bot_dir,
    data_dir,
    requirements: list,
    *,
    timeout: float = INSTALL_TIMEOUT_SECONDS,
    find_links: str | None = None,
) -> dict:
    """Install ``requirements`` into the bot's site dir. Never raises."""
    errors: list = []
    if not pip_runtime_available():
        return {
            "ok": False,
            "errors": [
                "pip is not available in this runtime — on Android, bake the "
                "packages into the APK (Chaquopy pip block) instead"
            ],
        }
    requirements, parse_errors = collect_requirements(Path(bot_dir), requirements)
    errors.extend(parse_errors)
    if errors:
        return {"ok": False, "errors": errors}
    if not requirements:
        return {"ok": True, "installed": [], "target": "", "note": "no requirements declared"}

    target = bot_site_dir(data_dir, bot_id)
    with _LOCK:  # one pip at a time — pip is not concurrency-safe
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"ok": False, "errors": [f"cannot create site dir: {exc}"]}
        try:
            ok, output = _run_pip(requirements, target, timeout, find_links=find_links)
        except Exception as exc:  # noqa: BLE001 - any pip failure is a rejection
            return {"ok": False, "errors": [f"pip failed: {exc}"]}
        finally:
            _enforce_site_cap(target)

    tail_lines = output.splitlines()[-OUTPUT_TAIL_LINES:]
    if not ok:
        return {
            "ok": False,
            "errors": ["pip install failed — output tail follows"] + tail_lines,
            "target": str(target),
        }

    # Verify the declared top-level packages actually import from the target.
    import importlib.util

    installed, missing = [], []
    for requirement in requirements:
        name = re.split(r"[<>=!~;\[\s]", requirement, maxsplit=1)[0].lower()
        found = any((target / f"{candidate}").exists() for candidate in (
            name, name.replace("-", "_"),
        ))
        if found:
            installed.append(requirement)
        else:
            missing.append(requirement)
    if missing:
        return {
            "ok": False,
            "errors": [
                "pip reported success but these packages are not in the site dir: "
                + ", ".join(missing)
            ],
            "target": str(target),
            "output_tail": tail_lines,
        }
    return {
        "ok": True,
        "installed": installed,
        "target": str(target),
        "output_tail": tail_lines,
    }


def _enforce_site_cap(target: Path) -> None:
    total = 0
    for path in target.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    if total > MAX_SITE_BYTES:
        shutil.rmtree(target, ignore_errors=True)


def site_dir_for_run(bot_dir, data_dir, bot_id: str):
    """Site dir to prepend during a run, or None (exists check only)."""
    candidate = bot_site_dir(data_dir, bot_id)
    if candidate.is_dir():
        return candidate
    return None


def uninstall_site_dir(data_dir, bot_id: str) -> None:
    """Best-effort cleanup when a bot is removed."""
    target = bot_site_dir(data_dir, str(bot_id))
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def debug_probe() -> dict:  # pragma: no cover - diagnostics helper
    return {
        "pip_available": pip_runtime_available(),
        "python": sys.version.split()[0],
    }
