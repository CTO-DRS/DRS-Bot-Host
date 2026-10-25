<div dir="rtl">

# DRS Bot Host 🤖📱

**منصة استضافة وإدارة بوتات بايثون داخل هاتف أندرويد — الهاتف نفسه هو السيرفر.**
مفتوح المصدر بالكامل، بلا أي استضافة مدفوعة.

[![CI](https://github.com/CTO-DRS/DRS-Bot-Host/actions/workflows/ci.yml/badge.svg)](https://github.com/CTO-DRS/DRS-Bot-Host/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-1.0.0-blue)
![license](https://img.shields.io/badge/license-Apache--2.0-green)
![python](https://img.shields.io/badge/hosted%20runtime-CPython%203.12-yellow)

> **📥 تحميل التطبيق / Download the APK:**
> [**DRS-Bot-Host-v1.0.0-debug.apk**](https://github.com/CTO-DRS/DRS-Bot-Host/releases/download/v1.0.0/DRS-Bot-Host-v1.0.0-debug.apk) (55 MB, arm64-v8a + x86_64)
> من صفحة الإصدارات / from the [Releases page](https://github.com/CTO-DRS/DRS-Bot-Host/releases) — SHA-256: `20079391…cb95501`

</div>

---

## What it is

DRS Bot Host turns an Android phone into a small bot server:

- **Import bots** as a ZIP archive or a project folder (SAF picker).
- **Host them continuously** via a `specialUse` foreground service with an
  optional boot autostart and partial wake lock.
- **Restart policies** per bot (`never` / `on_failure` / `always`) with
  exponential backoff, all implemented in the verified Python core.
- **Watch live logs** per bot (ring buffer + rotating JSONL on disk).
- **Dark futuristic glass UI** (Kotlin + Jetpack Compose, neon cyan/violet).
- **No server, no fees**: the embedded CPython 3.12 runtime (Chaquopy 17.1.0,
  MIT) runs everything on-device.

## Verification status — honest engineering

| Component | Status |
|---|---|
| Python core (`python-runtime/`): manifest, importer, streams, logging, runner, supervisor, host_api, cli | ✅ **51/51 pytest passing** (locally executed + CI matrix 3.10/3.11/3.12), `compileall` clean |
| End-to-end bot hosting on desktop (import ZIP/folder → run → cooperative stop) | ✅ Executed locally via `drs_host.cli` |
| Android app (`app/`): Compose UI, service, PyBridge, data layer | ✅ **Compiled + JVM unit tests + `assembleDebug` green in CI** (sandbox has no Android SDK, so validation happens on GitHub Actions) |
| CI: pytest matrix (3.10/3.11/3.12) + `assembleDebug` + JVM tests + APK artifact | ✅ **Green** — debug APK (~34 MB, embedded CPython for arm64-v8a/x86_64) published as the `drs-bot-host-debug-apk` artifact |

## Repository layout

```
├── app/                     # Android app (Kotlin + Jetpack Compose + Chaquopy)
├── python-runtime/          # Verified hosting core (pytest-tested, zero deps)
│   ├── src/drs_host/        #   manifest, importer, streams, logging, runner,
│   │                        #   supervisor, host_api, sdk, cli
│   └── tests/               #   51 tests
├── sample-bots/             # echo-bot, config-demo (both runnable)
├── docs/                    # BOT_SPEC, ARCHITECTURE, BUILD_GUIDE, USER_MANUAL_AR
├── .github/workflows/ci.yml # Python tests + Android APK build
└── scripts/push_to_github.sh
```

## Quick start (desktop, no phone needed)

```bash
cd python-runtime
python3 -m pytest tests -q                                   # 51 passed
PYTHONPATH=src python3 -m drs_host.cli --data-dir /tmp/drs \
    run ../sample-bots/echo-bot --seconds 4                  # real hosting demo
```

## Build the APK

Easiest: push to GitHub → CI artifact `drs-bot-host-debug-apk`.
Local build requirements (JDK 17, Gradle 8.11.1, Android SDK, Python 3.12):
see **docs/BUILD_GUIDE.md**. User manual (Arabic): **docs/USER_MANUAL_AR.md**.
Bot contract: **docs/BOT_SPEC.md**.

## Roadmap (post-1.0)

- Process-level isolation (Termux-style Python binaries) with force-kill.
- On-device pip install for bot requirements (removing the build-time constraint).
- Per-bot CPU/RAM accounting, schedules (cron-like start windows).
- Bot store: import directly from a Git URL.

<div dir="rtl">

## الترخيص

Apache-2.0 — استخدم وعدّل ووزّع بحرية مع الحفاظ على الإشعار القانوني.

</div>
