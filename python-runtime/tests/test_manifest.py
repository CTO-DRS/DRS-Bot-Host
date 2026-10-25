"""Manifest validation tests."""

from drs_host.manifest import validate_manifest, python_version_tuple

BASE = {
    "id": "my-bot",
    "name": "My Bot",
    "version": "1.0.0",
    "entrypoint": "main.py",
}


def test_minimal_manifest_is_valid():
    manifest, errors = validate_manifest(BASE)
    assert errors == []
    assert manifest.id == "my-bot"
    assert manifest.language == "python"
    assert manifest.restart["policy"] == "on_failure"
    assert manifest.restart["max_restarts"] == 5
    assert manifest.auto_start is False
    assert manifest.spec_version == 1


def test_full_manifest_roundtrip():
    document = {
        **BASE,
        "author": "DRS",
        "description": "demo",
        "min_python": "3.10",
        "requirements": ["requests", "numpy>=2.0"],
        "config": {"interval": 2},
        "auto_start": True,
        "restart": {"policy": "always", "max_restarts": 3, "backoff_seconds": 0.5},
    }
    manifest, errors = validate_manifest(document)
    assert errors == []
    dumped = manifest.to_dict()
    assert dumped["requirements"] == ["requests", "numpy>=2.0"]
    assert dumped["restart"]["max_restarts"] == 3
    assert dumped["restart"]["backoff_multiplier"] == 2.0  # default kept


def test_non_object_rejected():
    manifest, errors = validate_manifest(["not", "an", "object"])
    assert manifest is None
    assert any("must be a JSON object" in e for e in errors)


def test_unknown_keys_rejected():
    manifest, errors = validate_manifest({**BASE, "hax": True})
    assert manifest is None
    assert any("unknown key(s): hax" in e for e in errors)


def test_bad_id_rejected():
    for bad in ("A", "-x", "Has Space", "x" * 65):
        manifest, errors = validate_manifest({**BASE, "id": bad})
        assert manifest is None
        assert any("id:" in e for e in errors)


def test_bad_semver_rejected():
    manifest, errors = validate_manifest({**BASE, "version": "1.0"})
    assert manifest is None
    assert any("version:" in e for e in errors)


def test_entrypoint_rules():
    for bad in ("main.txt", "/abs/main.py", "../main.py", ""):
        manifest, errors = validate_manifest({**BASE, "entrypoint": bad})
        assert manifest is None
        assert any("entrypoint:" in e for e in errors)


def test_language_restricted_to_python():
    manifest, errors = validate_manifest({**BASE, "language": "nodejs"})
    assert manifest is None
    assert any("language:" in e for e in errors)


def test_restart_policy_validation():
    manifest, errors = validate_manifest({**BASE, "restart": {"policy": "sometimes"}})
    assert manifest is None
    assert any("restart.policy" in e for e in errors)

    manifest, errors = validate_manifest({**BASE, "restart": {"max_restarts": -1}})
    assert manifest is None
    assert any("restart.max_restarts" in e for e in errors)


def test_restart_unknown_key():
    manifest, errors = validate_manifest({**BASE, "restart": {"retry": True}})
    assert manifest is None
    assert any("unknown key(s): retry" in e for e in errors)


def test_requirements_and_config_types():
    manifest, errors = validate_manifest({**BASE, "requirements": "requests"})
    assert manifest is None
    assert any("requirements:" in e for e in errors)

    manifest, errors = validate_manifest({**BASE, "config": [1]})
    assert manifest is None
    assert any("config:" in e for e in errors)


def test_auto_start_must_be_bool():
    manifest, errors = validate_manifest({**BASE, "auto_start": "yes"})
    assert manifest is None
    assert any("auto_start:" in e for e in errors)


def test_spec_version_guard():
    manifest, errors = validate_manifest({**BASE, "spec_version": 99})
    assert manifest is None
    assert any("spec_version" in e for e in errors)


def test_min_python_shape():
    manifest, errors = validate_manifest({**BASE, "min_python": "3.x"})
    assert manifest is None
    assert any("min_python:" in e for e in errors)

    manifest, errors = validate_manifest({**BASE, "min_python": "3.11"})
    assert errors == []
    assert python_version_tuple(manifest.min_python) == (3, 11)
