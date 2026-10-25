"""``bot.json`` manifest parsing and strict validation.

The manifest is the single source of truth describing an importable bot:
identity, entrypoint, requirements, restart policy and autostart behaviour.
``validate_manifest`` returns ``(manifest, errors)`` and never raises, so both
the Python importer and the Android bridge can surface structured error lists.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SPEC_VERSION = 1

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_PYVER_RE = re.compile(r"^3\.\d{1,2}$")

ALLOWED_KEYS = {
    "spec_version",
    "id",
    "name",
    "version",
    "entrypoint",
    "language",
    "min_python",
    "author",
    "description",
    "requirements",
    "config",
    "restart",
    "auto_start",
}
RESTART_POLICIES = ("never", "on_failure", "always")
RESTART_DEFAULTS = {
    "policy": "on_failure",
    "max_restarts": 5,
    "backoff_seconds": 2.0,
    "backoff_multiplier": 2.0,
    "max_backoff_seconds": 60.0,
}
RESTART_KEYS = set(RESTART_DEFAULTS)


@dataclass
class BotManifest:
    """A validated bot manifest."""

    id: str
    name: str
    version: str
    entrypoint: str
    language: str = "python"
    min_python: Optional[str] = None
    author: str = ""
    description: str = ""
    requirements: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    restart: dict = field(default_factory=lambda: dict(RESTART_DEFAULTS))
    auto_start: bool = False
    spec_version: int = SPEC_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_restart(raw: Any, errors: list) -> dict:
    """Merge a raw ``restart`` object over the defaults, collecting errors."""
    out = dict(RESTART_DEFAULTS)
    if raw is None:
        return out
    if not isinstance(raw, dict):
        errors.append("restart: must be an object")
        return out
    unknown = set(raw) - RESTART_KEYS
    if unknown:
        errors.append("restart: unknown key(s): " + ", ".join(sorted(unknown)))

    policy = raw.get("policy", out["policy"])
    if policy not in RESTART_POLICIES:
        errors.append(
            "restart.policy: must be one of " + ", ".join(RESTART_POLICIES)
        )
    else:
        out["policy"] = policy

    value = raw.get("max_restarts")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            errors.append("restart.max_restarts: must be an integer between 0 and 100")
        else:
            out["max_restarts"] = value

    for key, lo, hi in (
        ("backoff_seconds", 0.0, 3600.0),
        ("backoff_multiplier", 1.0, 100.0),
        ("max_backoff_seconds", 0.0, 86400.0),
    ):
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"restart.{key}: must be a number between {lo} and {hi}")
        elif not lo <= float(value) <= hi:
            errors.append(f"restart.{key}: must be a number between {lo} and {hi}")
        else:
            out[key] = float(value)
    return out


def validate_manifest(data: Any) -> tuple[Optional[BotManifest], list]:
    """Validate a parsed ``bot.json`` document.

    Returns ``(BotManifest, [])`` on success or ``(None, [errors...])`` on
    failure. Unknown keys are rejected so typos never pass silently.
    """
    if not isinstance(data, dict):
        return None, ["manifest: must be a JSON object"]

    errors: list = []
    unknown = set(data) - ALLOWED_KEYS
    if unknown:
        errors.append("unknown key(s): " + ", ".join(sorted(unknown)))

    spec_version = data.get("spec_version", SPEC_VERSION)
    if spec_version != SPEC_VERSION:
        errors.append(
            f"spec_version: unsupported value {spec_version!r} (expected {SPEC_VERSION})"
        )

    bot_id = data.get("id")
    if not isinstance(bot_id, str) or not _ID_RE.match(bot_id):
        errors.append(
            "id: required, 2-64 chars, lowercase letters/digits/'-'/'_', "
            "must start with a letter or digit"
        )

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name: required non-empty string")

    version = data.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        errors.append("version: required semantic version, e.g. 1.0.0")

    entrypoint = data.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint:
        errors.append("entrypoint: required string (relative path to a .py file)")
    else:
        normalized = entrypoint.replace("\\", "/")
        if (
            not normalized.endswith(".py")
            or normalized.startswith("/")
            or ".." in normalized.split("/")
        ):
            errors.append(
                "entrypoint: must be a relative path ending with .py inside the bot folder"
            )

    language = data.get("language", "python")
    if language != "python":
        errors.append("language: only 'python' is supported in this version")

    min_python = data.get("min_python")
    if min_python is not None and (
        not isinstance(min_python, str) or not _PYVER_RE.match(min_python)
    ):
        errors.append("min_python: must look like '3.10'")

    requirements = data.get("requirements", [])
    if not isinstance(requirements, list) or any(
        not isinstance(item, str) for item in requirements
    ):
        errors.append("requirements: must be a list of strings (PyPI package names)")
        requirements = []

    config = data.get("config", {})
    if not isinstance(config, dict):
        errors.append("config: must be a JSON object")
        config = {}

    auto_start = data.get("auto_start", False)
    if not isinstance(auto_start, bool):
        errors.append("auto_start: must be true or false")
        auto_start = False

    restart = _validate_restart(data.get("restart"), errors)

    if errors:
        return None, errors

    manifest = BotManifest(
        id=bot_id,
        name=name.strip(),
        version=version,
        entrypoint=entrypoint,
        language=language,
        min_python=min_python,
        author=str(data.get("author", "") or ""),
        description=str(data.get("description", "") or ""),
        requirements=requirements,
        config=config,
        restart=restart,
        auto_start=auto_start,
        spec_version=spec_version,
    )
    return manifest, []


def python_version_tuple(version: str) -> tuple:
    """Parse a ``3.10``-style version string into a comparable tuple."""
    major, _, minor = version.partition(".")
    return (int(major), int(minor or 0))
