# Changelog — DRS Bot Host

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] — 2026-10-25

Modern tech-focused visual overhaul + feature batch.

### Added — Python runtime core (verified locally, 62/62 pytest)
- `host_stats()`: fleet aggregates (total / by state / running / failed /
  restarts / runs) + host uptime, exposed on the dashboard KPI tiles.
- Per-bot metrics: `run_count` and `uptime_seconds` (live while running,
  last-run duration once terminal) in every status payload.
- `export_logs(bot_id)`: bundles a bot's JSONL logs into a timestamped zip
  under `<data_dir>/exports/`.
- `set_bot_config(bot_id, config)`: replace a bot's `config` object at
  runtime (dict or JSON string); validated through the full manifest
  validator, persisted to `bot.json`, applied on next start.
- `drs_host.scaffold.scaffold_bot(name, dest)`: generates a ready-to-import
  sample bot (bot.json + main.py + README) from a free-form name; new CLI
  commands `stats`, `scaffold`, `export-logs`, `set-config`.
- 12 new tests (62 total) including an end-to-end
  scaffold → import → reconfigure → run → stop cycle.

### Added — Android app
- User-selectable accent color (cyan / violet / mint / amber) persisted in
  DataStore and applied app-wide instantly.
- Animated tech backdrop: engineering grid, drifting neon orbs, scanline
  sweep; `GlassCard` accent borders, gradient `NeonButton`, KPI `StatTile`,
  `SectionHeader`, status chips with a live pulse dot.
- Dashboard: KPI tile row, host service card with start-all / stop-all,
  system telemetry card (battery, memory, host uptime).
- Bots screen: live search by name/id, state filter chips (all / active /
  stopped / failed), bulk start-all / stop-all, per-bot uptime + run count.
- Bot detail: statistics card (uptime / runs / restarts / policy) and
  one-tap log export with copy-to-clipboard path.
- Settings: appearance section, crash-alerts toggle with Android 13+
  runtime permission request, About card (version, repository, releases).
- `BotHostService` posts a failure notification (dedicated channel) the
  first time each bot enters `FAILED`; honours the crash-alerts toggle and
  checks POST_NOTIFICATIONS on API 33+.

### Changed
- versionCode 2, versionName 1.1.0; `buildConfig` feature enabled.

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
