package com.drsbot.host

import com.drsbot.host.data.LogRecord
import com.drsbot.host.util.LogFilter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LogFilterTest {

    private val logs = listOf(
        LogRecord(1.0, "INFO", "bot started"),
        LogRecord(2.0, "WARNING", "retry scheduled"),
        LogRecord(3.0, "ERROR", "connection refused"),
        LogRecord(4.0, "INFO", "bot stopped"),
    )

    @Test
    fun passthrough_whenNoFilter() {
        assertEquals(logs, LogFilter.apply(logs, "", "ALL"))
        assertEquals(logs, LogFilter.apply(logs, "   ", "ALL"))
    }

    @Test
    fun levelFilter_isCaseInsensitiveExact() {
        val errors = LogFilter.apply(logs, "", "ERROR")
        assertEquals(listOf("connection refused"), errors.map { it.message })

        val warns = LogFilter.apply(logs, "", "warning")
        assertEquals(listOf("retry scheduled"), warns.map { it.message })
    }

    @Test
    fun textQuery_matchesCaseInsensitive() {
        val hits = LogFilter.apply(logs, "BOT", "ALL")
        assertEquals(listOf("bot started", "bot stopped"), hits.map { it.message })
    }

    @Test
    fun combinedFilters_intersect() {
        val hits = LogFilter.apply(logs, "connection", "ERROR")
        assertEquals(listOf("connection refused"), hits.map { it.message })

        // text matches two records, level keeps only the error one
        val narrow = LogFilter.apply(logs, "b", "ERROR")
        assertEquals(listOf("connection refused"), narrow.map { it.message })
    }

    @Test
    fun unknownLevelBehavesLikeAll() {
        assertEquals(logs, LogFilter.apply(logs, "", "TRACE"))
    }

    @Test
    fun passthroughFlagTracksFilterState() {
        assertTrue(LogFilter.isPassthrough("", "ALL"))
        assertFalse(LogFilter.isPassthrough("err", "ALL"))
        assertFalse(LogFilter.isPassthrough("", "ERROR"))
    }
}
