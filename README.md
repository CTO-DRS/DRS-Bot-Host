<div dir="rtl">

# DRS Bot Host 🤖📱

**منصة استضافة وإدارة بوتات بايثون داخل هاتف أندرويد — الهاتف نفسه هو السيرفر.**
مفتوح المصدر بالكامل، بلا أي استضافة مدفوعة.

[![CI](https://github.com/CTO-DRS/DRS-Bot-Host/actions/workflows/ci.yml/badge.svg)](https://github.com/CTO-DRS/DRS-Bot-Host/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-1.6.0-blue)
![license](https://img.shields.io/badge/license-Apache--2.0-green)
![python](https://img.shields.io/badge/hosted%20runtime-CPython%203.12-yellow)

> **📥 تحميل التطبيق / Download the APK:**
> [**DRS-Bot-Host-v1.6.0-debug.apk**](https://github.com/CTO-DRS/DRS-Bot-Host/releases/download/v1.6.0/DRS-Bot-Host-v1.6.0-debug.apk) (arm64-v8a + x86_64)
> من صفحة الإصدارات / from the [Releases page](https://github.com/CTO-DRS/DRS-Bot-Host/releases)

</div>

---

## What it is

DRS Bot Host turns an Android phone into a small bot server:

- **Import bots** as a ZIP archive or a project folder (SAF picker).
- **Host them continuously** via a `specialUse` foreground service with an
  optional boot autostart and partial wake lock.
- **Restart policies** per bot (`never` / `on_failure` / `always`) with
  exponential backoff, all implemented in the verified Python core.
- **Watch live logs** per bot (ring buffer + rotating JSONL on disk),
  **search them** (free-text query + ALL/INFO/WARNING/ERROR level chips;
  live-tail autoscroll pauses while filtering) and **export them to a
  zip** with one tap.
- **Fleet dashboard**: KPI tiles (bots / active / failed / restarts),
  system telemetry (battery, memory, host uptime).
- **Crash alerts**: a notification the moment a bot enters `FAILED`.
- **Skill templates**: create a working bot with one tap — URL poller,
  RSS watcher, file watcher, webhook receiver, scheduled-window demo,
  Telegram echo (dependency auto-installed) and the classic heartbeat.
- **On-device pip installs**: each bot gets its own private site directory;
  install its declared packages from the bot detail screen (security
  filtered: no URLs, no git, no local paths).
- **Process isolation with a real kill**: `"isolation": "process"` runs a
  bot as a separate Python process — force-stop becomes a true SIGKILL
  (falls back to threads on runtimes without a standalone python binary).
- **Wi-Fi status page**: opt-in LAN dashboard (dark HTML + JSON API,
  optional token) served by the phone itself.
- **Personalize**: pick the accent color (cyan / violet / mint / amber) and
  the interface language (**System / English / العربية**) — Arabic mirrors
  the whole layout RTL and stays in sync with Android 13's per-app
  language setting.
- **No tokens, no accounts**: bots are plain Python scripts hosted
  locally; the platform never requires tokens or sign-ups. Only opt-in
  extras use credentials (the Telegram skill template needs a Telegram
  token; the Wi-Fi status page can optionally be locked with a secret).
- **Dark futuristic glass UI** (Kotlin + Jetpack Compose) with an animated
  engineering-grid backdrop, neon orbs and a scanline sweep, plus a
  **branded splash screen** (neon sweep ring, crossfades into the app).
- **Per-bot health checks with auto-recovery** (v1.6): declare an HTTP probe
  (or a bot-relative `check()` script) and the host watches every running
  bot on an interval — consecutive failures escalate to a graceful
  restart, a force-stop + restart, or just a flagged state; a "Probe now"
  button and an enable switch live in the bot detail screen.
- **Custom (community) registries** (v1.6): point the Market tab at your
  own registry JSON (a gist, a LAN server, anywhere http/https) — sources
  are validated, persisted and one tap away; a fetch without an explicit
  source uses the first saved one.
- **No server, no fees**: the embedded CPython 3.12 runtime (Chaquopy 17.1.0,
  MIT) runs everything on-device.

## Verification status — honest engineering

| Component | Status |
|---|---|
| Python core (`python-runtime/`): manifest, importer, streams, logging, runner, supervisor, scheduler, healthcheck, downloader, backup, marketplace, skills, installer, isolation, webstatus, host_api, cli, scaffold | ✅ **168/168 pytest passing** (locally executed + CI matrix 3.10/3.11/3.12), `compileall` clean |
| End-to-end bot hosting on desktop (import ZIP/folder → run → cooperative stop; scaffold → import → reconfigure → run) | ✅ Executed locally via `drs_host.cli` |
| Android app (`app/`): Compose UI, service, PyBridge, data layer | ✅ **Compiled + JVM unit tests + `assembleDebug` green in CI** (sandbox has no Android SDK, so validation happens on GitHub Actions) |
| CI: pytest matrix (3.10/3.11/3.12) + `assembleDebug` + JVM tests + APK artifact | ✅ **Green** — debug APK (embedded CPython for arm64-v8a/x86_64) published as the `drs-bot-host-debug-apk` artifact and attached to Releases |

## Repository layout

```
├── app/                     # Android app (Kotlin + Jetpack Compose + Chaquopy)
├── python-runtime/          # Verified hosting core (pytest-tested, zero deps)
│   ├── src/drs_host/        #   manifest, importer, streams, logging, runner,
│   │                        #   supervisor, scheduler, downloader, host_api,
│   │                        #   sdk, cli
│   └── tests/               #   125 tests
├── sample-bots/             # echo-bot, config-demo (both runnable)
├── docs/                    # BOT_SPEC, ARCHITECTURE, BUILD_GUIDE, USER_MANUAL_AR
├── .github/workflows/ci.yml # Python tests + Android APK build
└── scripts/push_to_github.sh
```

## Quick start (desktop, no phone needed)

```bash
cd python-runtime
python3 -m pytest tests -q                                   # 125 passed
PYTHONPATH=src python3 -m drs_host.cli --data-dir /tmp/drs \
    run ../sample-bots/echo-bot --seconds 4                  # real hosting demo
PYTHONPATH=src python3 -m drs_host.cli scaffold "My Bot" --dest /tmp/bots
PYTHONPATH=src python3 -m drs_host.cli --data-dir /tmp/drs stats
```

## Build the APK

Easiest: push to GitHub → CI artifact `drs-bot-host-debug-apk`.
Local build requirements (JDK 17, Gradle 8.11.1, Android SDK, Python 3.12):
see **docs/BUILD_GUIDE.md**. User manual (Arabic): **docs/USER_MANUAL_AR.md**.
Bot contract: **docs/BOT_SPEC.md**.

## What shipped in v1.2

- **Schedules (cron-like)**: `"kind": "interval"` and `"daily"` windows in `bot.json`,
  a scheduler thread with per-bot enable/disable, next-window hints in the UI.
- **Per-bot CPU accounting** via `getrusage(RUSAGE_THREAD)`; host process RSS on the dashboard.
- **Force-stop escalation**: bots that ignore the cooperative stop event are detached
  (`FORCE_STOPPED`); zombie exit callbacks can no longer corrupt live state.
- **Import from URL**: HTTPS zip download with a hard size cap; GitHub repo / tree links
  are rewritten to zipballs automatically.
- **Requirements policy** (off / warn / enforce) checked at start time with a best-effort
  importability probe.
- **Config editor UI** backed by `set_bot_config`, plus schedule display/toggle and the
  force-stop button in the bot detail screen.

## What shipped in v1.3

- **Skill templates** (`drs_host.skills`): seven curated one-tap bots,
  surfaced on the app's Import screen and via the CLI.
- **On-device requirements installer** (`drs_host.installer`): in-process
  pip into a per-bot site dir, strict requirement filtering, per-bot
  `sys.path` wiring, 512 MB cap.
- **Process isolation** (`drs_host.isolation`): real subprocess per bot with
  SIGTERM→stop-event bridging and a true SIGKILL on force-stop; thread-mode
  fallback where no standalone python binary exists (e.g. Chaquopy).
- **Wi-Fi fleet status page** (`drs_host.webstatus`): dark HTML dashboard +
  JSON API + per-bot log endpoint, optional shared-secret token.

> On-device process isolation needs a standalone Python binary; inside
> Chaquopy the app keeps thread mode (probed at runtime, honestly reported
> in each bot's log). Termux-style binaries remain future work.

## What shipped in v1.4

- **Bot market** (new tab): a curated registry of ready-to-run bots
  (`registry/registry.json` in this repo), fetched and strictly validated
  by `drs_host.marketplace` — slug ids, http/https URLs, field limits,
  unknown keys dropped. Installs ride the same hardened
  download→import pipeline as a manual URL import; a registry entry gains
  no new privileges. The first registry ships three stdlib-only bots
  (**echo-bot**, **config-demo**, **webhook-receiver**), each verified by a
  real supervised run before publishing.
- **Fleet backup & restore** (`drs_host.backup`): one zip with every bot's
  sources + manifest + `backup.json` metadata (logs and pip site-dirs
  excluded). Restore requires the metadata manifest and re-imports every
  bot through the full validation pipeline. One tap each in Settings.
- **Status-page token management + TLS**: a masked access-token field in
  Settings (changing it restarts the server), the real LAN IP + scheme in
  the URL display, and optional https with user-supplied PEM certificates
  (`serve-status --cert/--key` or the API).
- Fixed: the Import screen rendered the skill-templates card twice.

## What shipped in v1.6

- **Per-bot health checks** (`drs_host.healthcheck`): declare a `health`
  object in `bot.json` — an `http` probe (GET, expected status) or a
  `command` probe (a bot-relative `.py` script whose `check()` returns a
  bool or `(bool, detail)`; runs in-process, no shell, no argv). A
  1 Hz monitor thread probes every RUNNING bot on its interval with
  per-probe timeout accounting; `failure_threshold` consecutive failures
  trigger `recover`: `restart` (graceful), `force_stop` (detach + start),
  or `none` (stay flagged unhealthy). `success_threshold` consecutive
  successes mark the bot healthy again; the recovery counter survives
  restarts. Runtime state (`health_state`) ships in every status payload.
- **Manual probes + persistence**: `host_api.probe_health()` (diagnostic,
  never auto-recovers), `set_health_enabled()` persisted to `bot.json`,
  CLI `health` / `health --on|--off` / `health-probe`, and a bot-detail
  health card (probe target, live status colouring, failures/recoveries,
  last error, Probe-now button, enable switch).
- **Custom (community) registry sources** (`drs_host.marketplace`):
  `add_registry_source` / `remove_registry_source` / `registry_sources`
  persist an ordered list of http(s) registry URLs in the host data dir
  (max 20, deduped, strictly shape-checked). `marketplace_fetch()` without
  an explicit URL resolves: explicit → first saved source → the project's
  curated default. The Market tab gained a sources editor (add / use /
  remove) with a monospace URL field and inline host-side rejection text.
- Verified locally: **168/168 pytest** (43 new v1.6 tests: validation
  matrix, real HTTP probes against a local server, probe tuples/raises/
  missing-`check()`, timeout accounting with a real deadline, idle/
  disabled semantics, recovery via a real supervised restart, registry
  source round-trip + a live custom-registry fetch) + real-CLI smoke.

## Roadmap (post-1.6)

- Termux-style standalone Python binaries for on-device process isolation
  (needs ~30 MB of bundled runtime per ABI — deliberately not faked).
- In-app registry editor for authoring registries on-device (the v1.6
  sources feature covers consuming community registries).

<div dir="rtl">

## الترخيص

Apache-2.0 — استخدم وعدّل ووزّع بحرية مع الحفاظ على الإشعار القانوني.

</div>
