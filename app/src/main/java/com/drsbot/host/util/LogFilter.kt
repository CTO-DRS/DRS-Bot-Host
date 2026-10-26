package com.drsbot.host.util

import com.drsbot.host.data.LogRecord

/**
 * Client-side log filtering for the bot detail screen: a free-text query
 * (case-insensitive substring match on the message) combined with an exact
 * level filter. Pure function so it is unit-testable on the JVM.
 */
object LogFilter {

    val LEVELS = listOf("ALL", "INFO", "WARNING", "ERROR")

    /**
     * @param level one of [LEVELS]; anything else behaves like "ALL".
     * @param query blank means no text filtering.
     */
    fun apply(logs: List<LogRecord>, query: String, level: String): List<LogRecord> {
        val trimmed = query.trim()
        val levelActive = level in LEVELS && level != "ALL"
        if (trimmed.isEmpty() && !levelActive) return logs
        return logs.filter { record ->
            (!levelActive || record.level.equals(level, ignoreCase = true)) &&
                (trimmed.isEmpty() || record.message.contains(trimmed, ignoreCase = true))
        }
    }

    /** Autoscroll-to-latest only makes sense while no filter hides the tail. */
    fun isPassthrough(query: String, level: String): Boolean =
        query.isBlank() && (level !in LEVELS || level == "ALL")
}
