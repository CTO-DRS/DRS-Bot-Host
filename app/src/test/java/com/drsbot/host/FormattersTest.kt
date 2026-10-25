package com.drsbot.host

import org.junit.Assert.assertEquals
import org.junit.Test

class FormattersTest {

    @Test
    fun formatBytes_scales() {
        assertEquals("980 B", com.drsbot.host.util.Formatters.formatBytes(980))
        assertEquals("1.0 KB", com.drsbot.host.util.Formatters.formatBytes(1024))
        assertEquals("1.2 MB", com.drsbot.host.util.Formatters.formatBytes(1_258_291))
        assertEquals("1.0 GB", com.drsbot.host.util.Formatters.formatBytes(1_073_741_824))
    }

    @Test
    fun formatDuration_composes() {
        assertEquals("45s", com.drsbot.host.util.Formatters.formatDuration(45))
        assertEquals("1m 05s", com.drsbot.host.util.Formatters.formatDuration(65))
        assertEquals("1h 01m", com.drsbot.host.util.Formatters.formatDuration(3_675))
        assertEquals("0s", com.drsbot.host.util.Formatters.formatDuration(-7))
    }
}
