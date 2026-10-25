package com.drsbot.host.data

import org.json.JSONArray
import org.json.JSONObject

/**
 * Data classes mirroring the JSON dicts produced by the Python runtime
 * (drs_host.host_api). Parsing is explicit and tolerant: any missing or
 * null field falls back to a safe default instead of crashing the UI.
 */

/** One bot as reported by the Python supervisor (list_bots / bot_status). */
data class BotStatus(
    val id: String,
    val name: String,
    val version: String,
    val state: String,
    val description: String,
    val lastError: String?,
    val restartPolicy: String,
    val autoStart: Boolean,
    val restarts: Int,
    val runCount: Int,
    val uptimeSeconds: Double?,
    val progressValue: Int?,
    val progressTotal: Int?,
    val progressLabel: String?,
    val cpuSeconds: Double = 0.0,
    val lastCpuSeconds: Double? = null,
    val detached: Boolean = false,
    val scheduleKind: String? = null,
    val scheduleEnabled: Boolean = false,
    val scheduleNextStartAt: Double? = null,
    val isolation: String = "thread",
    val isolationEffective: String = "thread",
    val configJson: String = "{}",
) {
    /** Mirrors BotState.TERMINAL on the Python side. */
    val isTerminal: Boolean
        get() = state == "STOPPED" || state == "COMPLETED" ||
            state == "FAILED" || state == "FORCE_STOPPED"

    val hasSchedule: Boolean
        get() = scheduleKind != null

    companion object {
        fun fromJson(o: JSONObject): BotStatus {
            val progress = o.optJSONObject("progress")
            val policy = o.optJSONObject("restart_policy")
            return BotStatus(
                id = o.optString("id"),
                name = o.optString("name"),
                version = o.optString("version", "?"),
                state = o.optString("state", "STOPPED"),
                description = o.optString("description", ""),
                lastError = o.optString("last_error").takeIf { it.isNotBlank() },
                // Flatten {policy, max_restarts, ...} into a compact display string.
                restartPolicy = policy?.let {
                    "${it.optString("policy", "manual")} ×${it.optInt("max_restarts", 0)}"
                } ?: "manual",
                autoStart = o.optBoolean("auto_start", false),
                restarts = o.optInt("restarts", 0),
                runCount = o.optInt("run_count", 0),
                uptimeSeconds = if (o.isNull("uptime_seconds")) {
                    null
                } else {
                    o.optDouble("uptime_seconds").takeIf { !it.isNaN() }
                },
                progressValue = progress?.optNullableInt("value"),
                progressTotal = progress?.optNullableInt("total"),
                progressLabel = progress?.optString("label")?.takeIf { it.isNotBlank() },
                cpuSeconds = o.optDouble("cpu_seconds", 0.0).takeIf { !it.isNaN() } ?: 0.0,
                lastCpuSeconds = if (o.isNull("last_cpu_seconds")) {
                    null
                } else {
                    o.optDouble("last_cpu_seconds").takeIf { !it.isNaN() }
                },
                detached = o.optBoolean("detached", false),
                scheduleKind = o.optJSONObject("schedule")
                    ?.optString("kind")
                    ?.takeIf { it.isNotBlank() },
                scheduleEnabled = o.optJSONObject("schedule")
                    ?.optBoolean("enabled", false) ?: false,
                scheduleNextStartAt = if (o.isNull("schedule_state")) {
                    null
                } else {
                    o.optJSONObject("schedule_state")
                        ?.optDouble("next_start_at")
                        ?.takeIf { !it.isNaN() }
                },
                configJson = o.optJSONObject("config")?.toString() ?: "{}",
                isolation = o.optString("isolation", "thread"),
                isolationEffective = o.optString("isolation_effective", "thread"),
            )
        }
    }
}

/** One structured log line (ts is epoch seconds, as produced by BotLogger). */
data class LogRecord(
    val ts: Double,
    val level: String,
    val message: String,
) {
    companion object {
        fun fromJson(o: JSONObject): LogRecord = LogRecord(
            ts = o.optDouble("ts", 0.0),
            level = o.optString("level", "INFO"),
            message = o.optString("message", ""),
        )
    }
}

/** Result of comparing a bot's requirements against the baked-in packages. */
data class RequirementsCheck(
    val known: Boolean,
    val missing: List<String>,
) {
    companion object {
        fun fromJson(o: JSONObject): RequirementsCheck = RequirementsCheck(
            known = o.optBoolean("known", false),
            missing = o.optJSONArray("missing").toStringList(),
        )
    }
}

/** Outcome of a ZIP / folder import performed by the verified Python importer. */
data class ImportResult(
    val ok: Boolean,
    val botId: String?,
    val files: Int,
    val bytes: Long,
    val errors: List<String>,
) {
    companion object {
        fun fromJson(o: JSONObject): ImportResult = ImportResult(
            ok = o.optBoolean("ok", false),
            botId = o.optString("bot_id").takeIf { it.isNotBlank() },
            files = o.optInt("files", 0),
            bytes = o.optLong("bytes", 0),
            errors = o.optJSONArray("errors").toStringList(),
        )
    }
}

/** Fleet-wide aggregates produced by host_stats() (v1.1 + v1.2 fields). */
data class HostStats(
    val total: Int,
    val running: Int,
    val failed: Int,
    val restarts: Int,
    val runs: Int,
    val uptimeSeconds: Double,
    val byState: Map<String, Int>,
    val scheduled: Int = 0,
    val cpuSeconds: Double = 0.0,
    val processRssBytes: Long = 0,
) {
    companion object {
        fun fromJson(o: JSONObject): HostStats {
            val byState = mutableMapOf<String, Int>()
            o.optJSONObject("by_state")?.let { obj ->
                val keys = obj.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    byState[key] = obj.optInt(key, 0)
                }
            }
            return HostStats(
                total = o.optInt("total", 0),
                running = o.optInt("running", 0),
                failed = o.optInt("failed", 0),
                restarts = o.optInt("restarts", 0),
                runs = o.optInt("runs", 0),
                uptimeSeconds = o.optDouble("uptime_seconds", 0.0),
                byState = byState,
                scheduled = o.optInt("scheduled", 0),
                cpuSeconds = o.optDouble("cpu_seconds", 0.0).takeIf { !it.isNaN() } ?: 0.0,
                processRssBytes = o.optLong("process_rss_bytes", 0),
            )
        }
    }
}

/** Result of export_logs(): a zip bundle path under the host data dir. */
data class ExportResult(
    val path: String,
    val files: Int,
    val bytes: Long,
) {
    companion object {
        fun fromJson(o: JSONObject): ExportResult = ExportResult(
            path = o.optString("path"),
            files = o.optInt("files", 0),
            bytes = o.optLong("bytes", 0),
        )
    }
}

/** One skill template from the v1.3 skill registry. */
data class SkillInfo(
    val key: String,
    val title: String,
    val description: String,
    val requirements: List<String>,
) {
    companion object {
        fun fromJson(o: JSONObject): SkillInfo = SkillInfo(
            key = o.optString("key"),
            title = o.optString("title", o.optString("key")),
            description = o.optString("description"),
            requirements = o.optJSONArray("requirements").toStringList(),
        )
    }
}

/** Outcome of scaffold_skill(): a folder ready for import_folder. */
data class ScaffoldResult(
    val ok: Boolean,
    val botId: String?,
    val path: String,
    val errors: List<String>,
) {
    companion object {
        fun fromJson(o: JSONObject): ScaffoldResult = ScaffoldResult(
            ok = o.optBoolean("ok", false),
            botId = o.optString("id").takeIf { it.isNotBlank() },
            path = o.optString("path"),
            errors = o.optJSONArray("errors").toStringList(),
        )
    }
}

/** Outcome of install_bot_requirements(): per-bot pip install into its site dir. */
data class InstallResult(
    val ok: Boolean,
    val installed: List<String>,
    val target: String,
    val outputTail: List<String>,
    val errors: List<String>,
) {
    companion object {
        fun fromJson(o: JSONObject): InstallResult = InstallResult(
            ok = o.optBoolean("ok", false),
            installed = o.optJSONArray("installed").toStringList(),
            target = o.optString("target"),
            outputTail = o.optJSONArray("output_tail").toStringList(),
            errors = o.optJSONArray("errors").toStringList(),
        )
    }
}

/** Current state of the Wi-Fi status web server. */
data class WebStatusInfo(
    val running: Boolean,
    val port: Int,
    val protected: Boolean,
) {
    companion object {
        fun fromJson(o: JSONObject): WebStatusInfo = WebStatusInfo(
            running = o.optBoolean("running", false),
            port = o.optInt("port", 0),
            protected = o.optBoolean("protected", false),
        )
    }
}

/** User-facing host settings, persisted with DataStore. */
data class HostSettings(
    val startServiceOnBoot: Boolean = false,
    val autoStartBots: Boolean = true,
    val keepCpuAwake: Boolean = true,
    val crashAlerts: Boolean = true,
    val accent: String = "cyan",
    val requirementsPolicy: String = "warn",
    val webStatusEnabled: Boolean = false,
    val webStatusPort: Int = 8090,
)

/** Metadata about the embedded Python runtime (Settings screen). */
data class RuntimeInfo(
    val hostVersion: String,
    val pythonVersion: String,
    val platform: String,
    val botCount: Int,
    val dataDir: String,
) {
    companion object {
        fun fromJson(o: JSONObject): RuntimeInfo = RuntimeInfo(
            hostVersion = o.optString("drs_host", "?"),
            pythonVersion = o.optString("python", "?"),
            platform = o.optString("platform", "?"),
            botCount = o.optInt("bots", 0),
            dataDir = o.optString("data_dir", ""),
        )
    }
}

// ── small org.json helpers shared by the parsers above ──────────────────────

internal fun JSONArray?.toStringList(): List<String> {
    if (this == null) return emptyList()
    return List(length()) { index -> optString(index) }.filter { it.isNotBlank() }
}

internal fun JSONObject.optNullableInt(key: String): Int? =
    if (has(key) && !isNull(key)) optInt(key) else null

/** Human-readable message from the standard {"ok": false, "errors": [...]} shape. */
internal fun JSONObject.errorsMessage(fallback: String = "host rejected the request"): String {
    val messages = optJSONArray("errors").toStringList()
    return messages.joinToString("; ").ifBlank { fallback }
}
