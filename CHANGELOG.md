## [1.9.0] — 2026-10-26

The Wi-Fi status dashboard now speaks the user's language, and the
curated registry grows by two bots.

### Added — Python runtime core (verified locally, 223/223 pytest)
- **Bilingual status page** (`drs_host.webstatus`): `FleetStatusServer`
  accepts `language="ar"` and renders the dashboard right-to-left
  (`lang="ar" dir="rtl"`) with fully translated tiles, table headers,
  empty-fleet hint and footer; the default stays the exact English v1.3
  page. `normalize_language()` maps any input (`ar`, `ara`, `arabic`,
  `العربية`, unknown values) onto `en`/`ar` — old callers are untouched.
  The JSON API is unchanged by the page language, and `web_status_info()`
  now reports the active `language`.
- **Host API**: `web_status_start(port, token, certfile, keyfile,
  language)` — `language` is a positional fifth argument so the Android
  bridge (which passes arguments positionally) can reach it.
- 14 new tests (`test_v19_features.py`): language normalization matrix,
  template markers (EN vs AR), live HTTP checks (English default,
  Arabic RTL + Arabic labels + resolved placeholders, Arabic empty-fleet
  hint, language switch requires restart), and real import→run flows for
  both new sample bots (log polling, state machine, config respected:
  task list + per-task duration + interval).

### Added — Sample bots + registry
- **System Monitor** (`sys-monitor`): long-running service bot sampling
  CPU-time deltas, resident memory, thread count and GC object count on
  a configurable interval (`config.interval_seconds`, clamped 1–3600 s);
  cooperative loop, progress reporting, stdlib only (`os`, `resource`,
  `gc`, `threading`).
- **Task Runner** (`task-runner`): one-shot batch bot (`restart.policy =
  "never"`) that walks a configurable task list
  (`config.tasks`, `config.per_task_seconds`) with live progress and
  finishes `COMPLETED`; every wait is a cooperative
  `ctx.sleep_or_stop` slice, so stopping mid-run is clean.
- Registry grows to five curated bots; new entries point at the
  v1.9.0 release assets (`sys-monitor.zip`, `task-runner.zip`) and both
  manifests validate against the strict `validate_manifest` rules.

### Added — Android app (verified by CI build)
- Status-page language follows the app language everywhere the server
  is started: settings toggle, port change, token change, language
  change (auto-restart so the dashboard switches immediately), and the
  foreground service boot path — resolution of "system" → device locale
  lives in `util/PageLanguage.kt`.
- New hint under the LAN dashboard settings:
  "The browser dashboard follows this app's language (Arabic renders
  right-to-left)." (strings 172/172, EN+AR parity).

## [1.8.0] — 2026-10-26

The GitHub import feature, done properly: paste a link, every bot inside
is auto-detected, import exactly what you select.

### Added — Python runtime core (verified locally, 209/209 pytest)
- **Link scanner** (`drs_host.ghscan`): `parse_github_url()` — repo,
  `/tree/<ref>[/sub/dir]` (slashed refs resolved by probing codeload,
  injectable probe), `/blob/<ref>/<file>.zip|.ibot` (→ raw),
  release assets, `releases/latest` (API-resolved, injectable),
  `archive/*.zip`, raw/codeload, and any direct `.zip`/`.ibot` URL.
  Traversal subpaths and unsupported shapes are refused with honest
  errors. `.ibot` is the canonical bot-package extension (a zip with a
  `bot.json` manifest).
- **Single-download scan**: `fetch_for_scan()` + `scan_zip_for_bots()` —
  every `bot.json` in the archive found and validated with the strict
  importer rules (multi-bot repos), entrypoint presence, requirements,
  sizes and file counts reported, packaged `.zip`/`.ibot` members listed,
  empty archives explained with a hint.
- **Selective import**: `importer.import_bot_from_zip_subtree()` (extract
  only the chosen bot dir into a staged temp folder, then the FULL
  hardened `import_folder` pipeline re-runs) and
  `importer.import_zip_member()` (size-capped member extraction →
  `import_zip`). Path arguments are re-validated (`..`, absolute,
  backslashes, drive letters refused).
- **Host API**: `github_scan(url)` (result cached: `ghscan-latest.zip` +
  sha256-checked meta, so the import step never re-downloads) and
  `github_import_selected(url, subdirs, overwrite)` — per-item results,
  partial failures reported, bots registered with the supervisor on
  success, JSON-string or list input for Chaquopy.
- **CLI**: `gh-scan URL` and `gh-import URL [--path …]… [--all]
  [--overwrite]` (verified end-to-end against a local HTTP server:
  scan → import --all → list).
- 41 new tests (`test_v18_features.py`): parser matrix with stubbed
  probes/fetch_json, real-HTTP fetch, multi-bot/top-stripped scans,
  invalid manifests, missing entrypoints, subpath filtering/traversal,
  subtree imports (success/overwrite/unknown-dir hints/bad file types),
  member imports (nested `.ibot`, not-found, size cap, non-archive),
  host-API scan+import flow with the HTTP server shut down between scan
  and import to PROVE the cache is reused, root-bot `""` selection, 404,
  and input validation.

### Added — Android app (verified by CI build + JVM tests)
- **Scanner card** (Import screen): paste link → **Scan** (primary) or
  the classic direct **Download & import**; results show the resolved
  summary, auto-detected bots with checkboxes (single valid bot
  pre-selected automatically), per-bot requirements + file counts,
  invalid manifests in red, packaged files section, "Import selected (n)"
  with a per-item outcome summary. Scan errors surface the host's real
  reason (404, size cap, unsupported link).
- New tolerant parsers: `GhDetectedBot`, `GhArchiveEntry`, `GhScanResult`,
  `GhImportItem`, `GhImportResult`; repository `githubScan()` /
  `githubImportSelected()`; strings EN + AR (171/171 parity);
  versionCode 9 / versionName 1.8.0.

## [1.7.0] — 2026-10-26

In-app language switcher (System / English / العربية) and credential
honesty: hosting bots never required tokens — now the UI says so.

### Added — Android app (verified by CI build + JVM tests)
- **In-app language switcher**: Settings → Appearance → Language with
  System default / English / العربية chips, applied instantly via the
  appcompat per-app locale delegate (`AppCompatDelegate.
  setApplicationLocales()`). Arabic mirrors the whole layout RTL
  (`supportsRtl` + full `values-ar` resources, 146/146 keys).
- **Per-app language integration**: `android:localeConfig` +
  `locales_config.xml` so Android 13+ keeps the system Settings → Apps →
  Language picker in sync; on API < 33 appcompat persists the choice.
- `MainActivity` is now an `AppCompatActivity` (required by the locale
  delegate); the XML theme parent moved to `Theme.AppCompat.NoActionBar`.

### Changed
- **Token honesty**: skill-template note now states explicitly that most
  skills need no tokens or API keys (only the optional Telegram template
  and the optional status-page shared secret use credentials — hosting
  plain Python bots requires none).

### Docs
- README: v1.7.0 badge + APK link, language-switcher feature, an explicit
  "no tokens required" line in the feature list.

## [1.6.0] — 2026-10-26

Per-bot health checks with auto-recovery + custom (community) registry
sources — the two verifiable items from the post-1.5 roadmap (standalone
Python binaries stay honestly future work). 168/168 pytest locally.

### Added — Python runtime core (verified locally, 168/168 pytest)
- **Health checks** (`drs_host.healthcheck`): a `health` object in
  `bot.json` — `kind: "http"` (GET, `expect_status`) or `kind: "command"`
  (bot-relative `.py` script exposing `check()` → bool | (bool, detail);
  in-process, no shell/argv, Chaquopy-safe). Strict validation: kinds,
  ranges (interval 5–86400 s, timeout 1–60 s, thresholds 1–100), recover
  actions (`none | restart | force_stop`), script path traversal refused,
  unknown keys rejected. `BotHealthMonitor` is a 1 Hz daemon thread
  mirroring the scheduler: probes RUNNING (non-detached) bots only,
  one probe thread per bot at a time, real-clock timeout accounting
  (a hung `check()` is recorded once as a timeout failure), recovery
  escalation, cumulative `recoveries` counter, `probe_health()` manual
  diagnostic (never auto-recovers), `set_health_enabled()` persisted to
  `bot.json`, and full `health` + `health_state` in every status payload.
- **Custom registry sources** (`drs_host.marketplace`): validated,
  deduped, persisted (max 20) http(s) registry URLs in
  `<data_dir>/registry_sources.json`; `resolve_registry_url()` — explicit
  → first saved → curated default — wired into `marketplace_fetch()`.
- **CLI**: `health [bot] [--on|--off]`, `health-probe [bot]`,
  `registry-add` / `registry-remove` / `registry-list`.
- 43 new tests: manifest validation matrix, probe primitives against a
  real local HTTP server (200 / mismatch / 404 / refused), command-probe
  tuple/raise/missing-`check()`/bad-return/missing-file, threshold and
  streak semantics, idle/disabled states, auto-recovery via a real
  supervised restart, counter reset with recovery preservation, real
  deadline timeout accounting, enable persistence, manual probe API,
  registry round-trip/cap/parse-survival, and a live custom-registry
  fetch through `host_api.marketplace_fetch()`.

### Added — Android app (verified by CI build + JVM tests)
- **Health card** (bot detail): probe kind + target, live status colouring
  (healthy mint / unhealthy red), failures + recoveries counters, last
  probe error, **Probe now** button with busy state, and an enable switch
  persisting to `bot.json`. New tolerant parsers: `HealthConfig`,
  `HealthState`, `HealthProbeResult`.
- **Registry sources editor** (Market tab): monospace URL field, Save /
  Use / Remove per saved source, "Default registry" reset, inline
  host-side rejection text; fetch-without-source honours the first saved
  source. New `OutlinedNeonButton` component.
- Strings EN + AR; versionCode 7 / versionName 1.6.0.

### Docs
- README: v1.6.0 badge + APK link, features, verification row 168/168,
  "What shipped in v1.6", roadmap updated (registry *editor* remains).
- BOT_SPEC: `health` manifest row + full Arabic v1.6 section.

## [1.5.0] — 2026-10-26

Closing the "modern tech look + more features" request: log search/filter
and a branded splash screen on top of the v1.4 fleet platform
(runtime verified locally at 125/125 pytest).

### Added — Android app (verified by CI build + JVM tests)
- **Log search & level filter** (bot detail): monospace search field plus
  ALL / INFO / WARNING / ERROR chips; live-tail autoscroll pauses while a
  filter is active and resumes when cleared. `LogFilter` is a pure,
  JVM-unit-tested function (6 new unit tests).
- **Animated splash screen**: neon sweep ring + pulsing core + wordmark,
  ~1.4 s, crossfading into the nav host (pure Compose, no new dependency).

### Docs
- README: v1.5.0 badge + APK link, log-search/splash features, corrected
  verification row to the actually-run 125/125 count.

## [1.4.0] — 2026-10-26

Marketplace + fleet backup + status-page security: the post-1.3 roadmap
(minus standalone Python binaries, still honestly future work).

### Added — Python runtime core (verified locally, 125/125 pytest)
- **Bot marketplace** (`drs_host.marketplace`): fetch a curated registry
  over http(s) with a 1 MB cap and strict per-entry validation (slug ids,
  http/https urls, field-length limits, unknown keys dropped, duplicate
  ids rejected). `install_entry()` routes the entry's zip through the same
  hardened downloader/importer as every manual import — a registry grants
  no new privileges. Exposed as `marketplace_fetch` / `marketplace_install`
  and CLI `market` / `market-install`.
- **Fleet backup & restore** (`drs_host.backup`): `backup_all()` zips every
  installed bot (sources + manifest; logs, `__pycache__` and pip site-dirs
  excluded) with a `backup.json` metadata manifest into
  `<data>/backups/drs-backup-<stamp>.zip`. `restore_backup()` requires that
  metadata (a random zip cannot pose as a backup) and re-imports each bot
  folder through `Supervisor.import_folder` — full manifest validation,
  extension whitelist, size limits, overwrite guard. Exposed as
  `backup_all` / `restore_backup` and CLI `backup` / `restore`.
- **Status-page TLS** (`drs_host.webstatus`): optional https via
  user-supplied PEM `certfile` + `keyfile` (both-or-neither, existence
  checked, honest errors). `web_status_start(port, token, certfile,
  keyfile)`; `web_status_info()` reports `tls`. CLI `serve-status --cert
  --key`. Certificates are user-supplied by design: the embedded Android
  runtime does not ship a cert-generator.
- 18 new tests (125 total): registry validation matrix, real fetches
  against a local HTTP server (valid / oversized / invalid JSON / 404),
  marketplace install round-trip incl. duplicate + overwrite semantics,
  backup zip structure + exclusions, restore into a fresh host with the
  restored bots actually running, foreign-zip + corrupt-zip rejections,
  CLI backup/restore, TLS round-trip (self-signed cert) + partial/missing
  file rejections, plain-http info fields.

### Added — Android app (compile-verified by CI; no local SDK, stated honestly)
- **Market tab** (new, Storefront icon): fetches the curated registry,
  per-entry install buttons with busy states, overwrite checkbox, retry
  card, per-entry warnings; installing navigates to the bot detail screen.
- **Status-page token management**: masked access-token field (visibility
  toggle) persisted in DataStore; changing it restarts the server
  immediately (settings collector + foreground service both pass it to
  `web_status_start`). The running URL now shows the device's real
  site-local IPv4 and the correct http/https scheme from
  `web_status_info().tls`.
- **Backup & restore card** in Settings: one-tap fleet backup (result path
  shown) and SAF-picked restore, with inline success/error feedback.
- BUGFIX: ImportScreen rendered the entire skills card twice (copy-paste
  error introduced in v1.3).
- versionCode 5, versionName 1.4.0; strings in English + Arabic.

### Curated registry (in-repo, served to the Market tab)
- `registry/registry.json` lists three stdlib-only bots published as
  release assets on v1.4.0: **echo-bot**, **config-demo** and
  **webhook-receiver** — each verified by a real supervised CLI run before
  publishing.

## [1.3.0] — 2026-10-26

"All skills" delivery: the remaining post-1.2 roadmap plus a skill template
system — process isolation with a real kill, on-device requirements installs
and a Wi-Fi fleet status page.

### Added — Python runtime core (verified locally, 107/107 pytest)
- **Skill templates** (`drs_host.skills`): seven curated, ready-to-run bot
  blueprints — `echo`, `http-poller`, `rss-watcher`, `file-watcher`,
  `webhook-receiver`, `scheduler-cron` (manifest schedule demo) and
  `telegram-echo` (declares `python-telegram-bot`). `scaffold_skill()`
  materialises a valid, importable bot folder; `list_skills()` exposes the
  catalogue to the app and CLI (`skills`, `scaffold-skill`).
- **On-device requirements installer** (`drs_host.installer`): pip runs
  in-process (with a watchdog thread) and installs into a per-bot site dir
  `<data>/site/<bot_id>`; requirements merge `bot.json` + `requirements.txt`
  through a strict security filter (URLs, `git+`, local paths and pip
  options are rejected); a 512 MB soft cap guards the site dir; the runner
  prepends the site dir to `sys.path` for each run; removed bots lose their
  site dir. Exposed as `install_bot_requirements` + CLI `install-reqs`.
- **Process isolation** (`drs_host.isolation` + `drs_host.child_runner`):
  `"isolation": "process"` in `bot.json` runs the bot as a separate CPython
  subprocess — cooperative stop via SIGTERM→stop-event bridging, and
  `force_stop` escalates to a **real SIGKILL** (no zombie threads). Child
  stdout is piped into the bot's ring/JSONL logs; CPU is accounted via
  `getrusage(RUSAGE_CHILDREN)` deltas. Runtimes without a standalone python
  binary (Android/Chaquopy) fall back to thread mode with an honest warning
  in the bot log. New status fields: `isolation`, `isolation_effective`.
- **Wi-Fi fleet status page** (`drs_host.webstatus`): opt-in
  `ThreadingHTTPServer` serving a dark auto-refreshing HTML dashboard at
  `/`, a JSON API at `/api/status` and per-bot logs at
  `/api/bots/<id>/logs?limit=N`; optional shared-secret token (`?key=` or
  `Authorization: Bearer`); port 0 supported (OS-assigned, reported back).
  Exposed as `web_status_start/stop/info` + CLI `serve-status`.
- 22 new tests (107 total): skill catalogue/scaffolds, installer security
  filter, a **real offline pip install** (local wheelhouse) verified down to
  "bot imports the installed package during a supervised run", web status
  (HTML/JSON/401/404/idempotent start), process-mode lifecycle (cooperative
  stop, crash reporting, real-kill force stop, thread fallback) and CLI.

### Added — Android app (validated by CI build)
- **Skill templates card** on the Import screen: browse the registry and
  create + import a bot in one tap (scaffold → import pipeline with cache
  cleanup).
- **Install requirements** action on the bot detail screen with live
  "Installing…" state, success list and pip output tail.
- **Wi-Fi status page settings card**: enable/disable, port field
  (1024–65535), live running/URL hint; the foreground service keeps the
  server in sync with the persisted setting (boot included).
- Data layer: `listSkills` / `scaffoldSkill` / `installRequirements` /
  `webStatusStart|Stop|Info` repository calls; tolerant models
  (`SkillInfo`, `ScaffoldResult`, `InstallResult`, `WebStatusInfo`);
  `BotStatus.isolation`/`isolation_effective`; DataStore-backed
  `webStatusEnabled`/`webStatusPort`.
- versionCode 4, versionName 1.3.0; new strings in English + Arabic.

# Changelog — DRS Bot Host

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.2.0] — 2026-10-25

Roadmap delivery: schedules, CPU telemetry, force-stop, URL imports,
requirements policy and the config editor.

### Added — Python runtime core (verified locally, 85/85 pytest)
- **Schedules** in `bot.json`: `{"kind": "interval", "interval_seconds": N,
  "run_seconds": M}` and `{"kind": "daily", "time": "HH:MM",
  "duration_seconds": N}` with strict validation (`drs_host.manifest`).
- `drs_host.scheduler.BotScheduler`: daemon thread ticking once per second;
  acts on window *edges* so manually stopped bots are never fought over;
  `next_start_at` hints in status payloads; enable/disable per bot persists
  to `bot.json` (`set_schedule_enabled`).
- **Per-bot CPU accounting**: `resource.getrusage(RUSAGE_THREAD)` deltas per
  run in `drs_host.runner`; `cpu_seconds` / `last_cpu_seconds` in status,
  fleet aggregate in `host_stats`.
- **Force-stop escalation**: `Supervisor.force_stop()` detaches an
  unresponsive thread and marks the bot `FORCE_STOPPED` (new terminal state);
  exit callbacks are matched against the currently tracked runner so zombie
  runs can never corrupt live state; `start()` warns when a detached thread
  may still be running.
- **URL imports** (`drs_host.downloader`): streaming HTTPS download with a
  hard size cap, GitHub repo/`.git`/`tree` URL rewriting to zipballs,
  temp-file cleanup; exposed as `import_bot_url` + CLI `import-url`.
- **Requirements policy**: `set_requirements_policy(off|warn|enforce)` —
  start-time check that combines the build-time package set with a
  best-effort `find_spec` importability probe; `enforce` blocks the start,
  `warn` logs a warning into the bot's own log.
- Host telemetry: `process_rss_bytes` (VmRSS) and `scheduled` count in
  `host_stats`.
- New CLI commands: `force-stop`, `import-url`, `requirements-policy`.
- 23 new tests (85 total) covering schedules (validation, interval
  integration, daily windows incl. midnight wrap, disable semantics), CPU
  accounting, force-stop lifecycle, URL imports (success / 404 / size cap /
  scheme guard / GitHub rewriting) and all three requirements policies.

### Added — Android app
- Bot detail: **schedule card** (kind, next window, enable/disable switch),
  **CPU stat tile**, **force-stop button** (shown while STOPPING or
  detached) and a **config editor** (JSON textarea validated by
  `set_bot_config`, status message on save/reject) — editor content
  survives the 1.5 s status polling.
- Import screen: **import from URL** card (GitHub-aware).
- Dashboard: host process memory and scheduled-bot rows; `FORCE_STOPPED`
  chip color.
- Settings: **requirements policy** selector (off / warn / enforce)
  persisted in DataStore and pushed into the Python runtime.
- versionCode 3, versionName 1.2.0.

### Changed
- `drs_host` runtime version 1.2.0; `BotState` extracted to
  `drs_host.states` (no circular import between supervisor and scheduler);
  `check_requirements` now reports best-effort missing packages even before
  `set_available_packages` is called.

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
