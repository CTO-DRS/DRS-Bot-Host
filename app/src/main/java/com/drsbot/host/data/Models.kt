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
) {
    /** Mirrors BotState.TERMINAL on the Python side. */
    val isTerminal: Boolean
        get() = state == "STOPPED" || state == "COMPLETED" || state == "FAILED"

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

/** Fleet-wide aggregates produced by host_stats() (v1.1). */
data class HostStats(
    val total: Int,
    val running: Int,
    val failed: Int,
    val restarts: Int,
    val runs: Int,
    val uptimeSeconds: Double,
    val byState: Map<String, Int>,
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

/** User-facing host settings, persisted with DataStore. */
data class HostSettings(
    val startServiceOnBoot: Boolean = false,
    val autoStartBots: Boolean = true,
    val keepCpuAwake: Boolean = true,
    val crashAlerts: Boolean = true,
    val accent: String = "cyan",
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
