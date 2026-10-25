package com.drsbot.host.util

import java.util.Locale

/** Small pure formatting helpers (covered by a JVM unit test). */
object Formatters {

    /** 1234567 -> "1.2 MB"; 980 -> "980 B". */
    fun formatBytes(bytes: Long): String {
        if (bytes < 1024) return "$bytes B"
        val units = listOf("KB", "MB", "GB", "TB")
        var value = bytes.toDouble()
        var unitIndex = -1
        while (value >= 1024.0 && unitIndex < units.size - 1) {
            value /= 1024.0
            unitIndex++
        }
        return String.format(Locale.US, "%.1f %s", value, units[unitIndex])
    }

    /** 65 -> "1m 05s"; 3675 -> "1h 01m". */
    fun formatDuration(seconds: Long): String {
        val total = if (seconds < 0) 0 else seconds
        val hours = total / 3600
        val minutes = (total % 3600) / 60
        val secs = total % 60
        return when {
            hours > 0 -> String.format(Locale.US, "%dh %02dm", hours, minutes)
            minutes > 0 -> String.format(Locale.US, "%dm %02ds", minutes, secs)
            else -> String.format(Locale.US, "%ds", secs)
        }
    }
}
