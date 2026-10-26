package com.drsbot.host.data

import android.content.Context
import com.chaquo.python.PyObject
import com.drsbot.host.python.PyBridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The single Kotlin entry point to the embedded Python host.
 *
 * Every call:
 *  1. makes sure the interpreter + supervisor are configured,
 *  2. invokes one `drs_host.host_api` function (Chaquopy),
 *  3. round-trips the result through `json.dumps` + `org.json` so no deep
 *     PyObject conversion ever crosses the JNI boundary,
 *  4. runs on Dispatchers.Default (Python calls can block).
 *
 * Rejections ({"ok": false, "errors": [...]}) surface as failed Results that
 * carry the Python-side error text, so the UI can show the real reason.
 */
class BotRepository {

    // ── queries ─────────────────────────────────────────────────────────────

    suspend fun listBots(context: Context): Result<List<BotStatus>> =
        call(context) { api ->
            val array = JSONArray(PyBridge.dumps(api.callAttr("list_bots")))
            List(array.length()) { BotStatus.fromJson(array.getJSONObject(it)) }
        }

    suspend fun botStatus(context: Context, botId: String): Result<BotStatus> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("bot_status", botId)))
            requireOk(obj)
            BotStatus.fromJson(obj)
        }

    suspend fun recentLogs(
        context: Context,
        botId: String,
        limit: Int = 500,
    ): Result<List<LogRecord>> = call(context) { api ->
        val array = JSONArray(PyBridge.dumps(api.callAttr("recent_logs", botId, limit)))
        List(array.length()) { LogRecord.fromJson(array.getJSONObject(it)) }
    }

    suspend fun checkRequirements(context: Context, botId: String): Result<RequirementsCheck> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("check_requirements", botId)))
            RequirementsCheck.fromJson(obj)
        }

    suspend fun runtimeInfo(context: Context): Result<RuntimeInfo> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("runtime_info")))
            RuntimeInfo.fromJson(obj)
        }

    suspend fun hostStats(context: Context): Result<HostStats> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("host_stats")))
            HostStats.fromJson(obj)
        }

    suspend fun exportLogs(context: Context, botId: String): Result<ExportResult> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("export_logs", botId)))
            requireOk(obj)
            ExportResult.fromJson(obj)
        }

    // ── v1.3: skills / installer / web status ─────────────────────────────

    suspend fun listSkills(context: Context): Result<List<SkillInfo>> =
        call(context) { api ->
            val array = JSONArray(PyBridge.dumps(api.callAttr("list_skills")))
            List(array.length()) { SkillInfo.fromJson(array.getJSONObject(it)) }
        }

    suspend fun scaffoldSkill(
        context: Context,
        skill: String,
        name: String,
        destDir: File,
    ): Result<ScaffoldResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("scaffold_skill", skill, name, destDir.absolutePath)),
        )
        ScaffoldResult.fromJson(obj)
    }

    suspend fun installRequirements(context: Context, botId: String): Result<InstallResult> =
        call(context) { api ->
            val obj = JSONObject(
                PyBridge.dumps(api.callAttr("install_bot_requirements", botId)),
            )
            InstallResult.fromJson(obj)
        }

    suspend fun webStatusStart(
        context: Context,
        port: Int,
        token: String = "",
        language: String = "en",
    ): Result<WebStatusInfo> =
        call(context) { api ->
            val obj = JSONObject(
                PyBridge.dumps(
                    api.callAttr("web_status_start", port, token, null, null, language),
                ),
            )
            if (!obj.optBoolean("ok", false)) {
                throw IllegalStateException(obj.errorsMessage())
            }
            WebStatusInfo.fromJson(obj).copy(running = true, port = obj.optInt("port", port))
        }

    suspend fun webStatusStop(context: Context): Result<Boolean> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("web_status_stop")))
            requireOk(obj)
            true
        }

    suspend fun webStatusInfo(context: Context): Result<WebStatusInfo> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("web_status_info")))
            WebStatusInfo.fromJson(obj)
        }

    // ── v1.4: marketplace / backup ──────────────────────────────────────────

    /** Fetches + validates a curated bot registry (default source when null). */
    suspend fun marketplaceFetch(context: Context, url: String? = null): Result<MarketRegistry> =
        call(context) { api ->
            val payload = if (url.isNullOrBlank()) {
                PyBridge.dumps(api.callAttr("marketplace_fetch"))
            } else {
                PyBridge.dumps(api.callAttr("marketplace_fetch", url))
            }
            MarketRegistry.fromJson(JSONObject(payload))
        }

    /** Downloads a marketplace entry's zip and imports it (hardened path). */
    suspend fun marketplaceInstall(
        context: Context,
        url: String,
        overwrite: Boolean = false,
    ): Result<ImportResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("marketplace_install", url, overwrite)),
        )
        ImportResult.fromJson(obj)
    }

    /** Zips every installed bot + metadata under <data>/backups/. */
    suspend fun backupAll(context: Context): Result<BackupResult> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("backup_all")))
            BackupResult.fromJson(obj)
        }

    /** Re-imports every bot from a backup zip (metadata required). */
    suspend fun restoreBackup(
        context: Context,
        zipPath: String,
        overwrite: Boolean = false,
    ): Result<RestoreResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("restore_backup", zipPath, overwrite)),
        )
        RestoreResult.fromJson(obj)
    }

    // ── lifecycle actions ───────────────────────────────────────────────────

    suspend fun start(context: Context, botId: String): Result<Boolean> =
        action(context, "start_bot", botId)

    suspend fun stop(context: Context, botId: String): Result<Boolean> =
        action(context, "stop_bot", botId)

    suspend fun forceStop(context: Context, botId: String): Result<Boolean> =
        action(context, "force_stop_bot", botId)

    suspend fun restart(context: Context, botId: String): Result<Boolean> =
        action(context, "restart_bot", botId)

    suspend fun setScheduleEnabled(
        context: Context,
        botId: String,
        enabled: Boolean,
    ): Result<Boolean> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("set_schedule_enabled", botId, enabled)),
        )
        requireOk(obj)
        true
    }

    // ── v1.6: health checks / registry sources ─────────────────────────

    /** One manual health probe (diagnostic; the host never auto-recovers). */
    suspend fun probeHealth(context: Context, botId: String): Result<HealthProbeResult> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("probe_health", botId)))
            requireOk(obj)
            HealthProbeResult.fromJson(obj)
        }

    /** Enable/disable a bot's health checks (persists to bot.json). */
    suspend fun setHealthEnabled(
        context: Context,
        botId: String,
        enabled: Boolean,
    ): Result<Boolean> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("set_health_enabled", botId, enabled)),
        )
        requireOk(obj)
        true
    }

    /** Saved custom (community) registry URLs, oldest first. */
    suspend fun registrySources(context: Context): Result<List<String>> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("registry_sources")))
            requireOk(obj)
            obj.optJSONArray("sources").toStringList()
        }

    /** Validate + persist one custom registry URL. */
    suspend fun addRegistrySource(context: Context, url: String): Result<Boolean> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("add_registry_source", url)))
            requireOk(obj)
            true
        }

    /** Remove one saved custom registry URL. */
    suspend fun removeRegistrySource(context: Context, url: String): Result<Boolean> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("remove_registry_source", url)))
            requireOk(obj)
            true
        }

    suspend fun setBotConfig(
        context: Context,
        botId: String,
        configJson: String,
    ): Result<Boolean> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("set_bot_config", botId, configJson)),
        )
        requireOk(obj)
        true
    }

    suspend fun remove(context: Context, botId: String): Result<Boolean> =
        action(context, "remove_bot", botId)

    suspend fun stopAll(context: Context): Result<Boolean> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("shutdown_all")))
            requireOk(obj)
            true
        }

    /** off | warn | enforce — what start() does about missing requirements. */
    suspend fun setRequirementsPolicy(context: Context, policy: String): Result<Boolean> =
        call(context) { api ->
            val obj = JSONObject(
                PyBridge.dumps(api.callAttr("set_requirements_policy", policy)),
            )
            requireOk(obj)
            true
        }

    suspend fun startAutostartBots(context: Context): Result<Boolean> =
        call(context) { api ->
            val obj = JSONObject(PyBridge.dumps(api.callAttr("start_autostart_bots")))
            requireOk(obj)
            true
        }

    // ── import ──────────────────────────────────────────────────────────────

    /**
     * ZIP / folder import: the cached material produced by SafIo is validated
     * and copied by the hardened Python importer. Rejections come back as
     * ImportResult(ok=false, errors=[...]) — not exceptions — so ImportViewModel
     * can render the host's reasons verbatim.
     */
    suspend fun importZip(
        context: Context,
        zip: File,
        overwrite: Boolean = false,
    ): Result<ImportResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("import_zip", zip.absolutePath, overwrite)),
        )
        ImportResult.fromJson(obj)
    }

    suspend fun importFolder(
        context: Context,
        folder: File,
        overwrite: Boolean = false,
    ): Result<ImportResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("import_folder", folder.absolutePath, overwrite)),
        )
        ImportResult.fromJson(obj)
    }

    /** Downloads a bot zip over HTTP(S) and imports it through the host. */
    suspend fun importUrl(
        context: Context,
        url: String,
        overwrite: Boolean = false,
    ): Result<ImportResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(api.callAttr("import_bot_url", url, overwrite)),
        )
        ImportResult.fromJson(obj)
    }

    // ── v1.8 GitHub scanner ────────────────────────────────────────────────

    /**
     * Scan a pasted GitHub (or direct .zip/.ibot) link: one download, every
     * bot.json inside validated with the strict importer rules, packaged
     * .zip/.ibot members listed. Scan errors (404, too large, no bots) come
     * back as failed Results carrying the host-side reason.
     */
    suspend fun githubScan(context: Context, url: String): Result<GhScanResult> =
        call(context) { api ->
            val obj = JSONObject(
                PyBridge.dumps(api.callAttr("github_scan", url)),
            )
            if (!obj.optBoolean("ok", false)) {
                throw IllegalStateException(obj.errorsMessage())
            }
            GhScanResult.fromJson(obj)
        }

    /**
     * Import the selected bot directories / packaged members from the last
     * scan (the archive stays cached on the host — no re-download).
     * Partial failures are a SUCCESS Result: inspect [GhImportResult].
     */
    suspend fun githubImportSelected(
        context: Context,
        url: String,
        paths: List<String>,
        overwrite: Boolean = false,
    ): Result<GhImportResult> = call(context) { api ->
        val obj = JSONObject(
            PyBridge.dumps(
                api.callAttr("github_import_selected", url, JSONArray(paths).toString(), overwrite),
            ),
        )
        if (!obj.has("results") && !obj.optBoolean("ok", false)) {
            throw IllegalStateException(obj.errorsMessage())
        }
        GhImportResult.fromJson(obj)
    }

    // ── plumbing ────────────────────────────────────────────────────────────

    private suspend fun <T> call(
        context: Context,
        block: (api: PyObject) -> T,
    ): Result<T> = withContext(Dispatchers.Default) {
        runCatching {
            PyBridge.ensure(context.applicationContext)
            block(PyBridge.api())
        }
    }

    private suspend fun action(
        context: Context,
        pythonFunction: String,
        botId: String,
    ): Result<Boolean> = call(context) { api ->
        val obj = JSONObject(PyBridge.dumps(api.callAttr(pythonFunction, botId)))
        requireOk(obj)
        true
    }

    /** Throws with the Python-side error text when {"ok": false}. */
    private fun requireOk(obj: JSONObject) {
        if (!obj.optBoolean("ok", false)) {
            throw IllegalStateException(obj.errorsMessage())
        }
    }
}
