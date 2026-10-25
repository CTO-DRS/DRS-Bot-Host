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

    suspend fun webStatusStart(context: Context, port: Int): Result<WebStatusInfo> =
        call(context) { api ->
            val obj = JSONObject(
                PyBridge.dumps(api.callAttr("web_status_start", port)),
            )
            if (!obj.optBoolean("ok", false)) {
                throw IllegalStateException(obj.errorsMessage())
            }
            WebStatusInfo(running = true, port = obj.optInt("port", port), protected = false)
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
