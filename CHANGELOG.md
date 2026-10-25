# Changelog — DRS Bot Host

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] — 2026-10-25

First public engineering release (source complete; APK produced by GitHub Actions).

### Added — Python runtime core (`python-runtime/`, verified locally with pytest)
- `bot.json` manifest specification v1 with strict validation (`drs_host.manifest`).
- Safe ZIP / folder importer with zip-slip protection, size and file-count limits,
  extension whitelist and single-root normalization (`drs_host.importer`).
- Thread-aware stdout capture: bot `print()` output is routed into the bot's own
  log buffer without leaking to other bots (`drs_host.streams`).
- Structured logging: in-memory ring buffer + rotating JSONL file sink (`drs_host.logging`).
- Thread-per-bot runner with context injection (`drs_host.runner`).
- Supervisor with state machine (`STOPPED/STARTING/RUNNING/STOPPING/BACKOFF/COMPLETED/FAILED`),
  restart policies (`never` / `on_failure` / `always`), exponential backoff,
  autostart discovery and installed-bot discovery (`drs_host.supervisor`).
- Public SDK for bots: `get_context()`, logger, `stop_event`, `sleep_or_stop()`,
  `set_progress()` (`drs_host.sdk`).
- `drs_host.host_api` facade consumed by the Android app (via Chaquopy) and the CLI.
- CLI for desktop verification: `python -m drs_host.cli info|list|import|run|stop`.
- 51 pytest tests covering manifest, importer, streams, supervisor, host API.

### Added — Android app (`app/`, Kotlin + Jetpack Compose, built in CI)
- Native Kotlin + Compose UI, dark futuristic glass theme (neon cyan/violet accents).
- Screens: Dashboard, Bots, Import (ZIP via SAF / folder via tree picker),
  Bot Detail (status, progress, controls, live logs), Settings.
- Foreground service `BotHostService` (`specialUse` type) with persistent notification,
  partial wake lock, stop-all action and optional boot autostart.
- Python hosting via Chaquopy 17.1.0 (Python 3.12 embedded).
- DataStore-backed settings (SettingsStore), POST_NOTIFICATIONS handling, battery-optimization exemption.
- Kotlin data layer: BotRepository (suspend API over the PyBridge JSON facade),
  typed models mirroring host_api dicts (BotStatus, LogRecord, RequirementsCheck,
  ImportResult, RuntimeInfo), SettingsStore with DataStore.

### Added — Project infrastructure
- GitHub Actions CI: pytest matrix (3.10/3.11/3.12) + Android `assembleDebug`
  + JVM unit tests + debug APK artifact upload.
- Docs: BOT_SPEC, ARCHITECTURE, BUILD_GUIDE, USER_MANUAL_AR (Arabic).
- Sample bots: `echo-bot`, `config-demo`.
- Apache-2.0 license.
