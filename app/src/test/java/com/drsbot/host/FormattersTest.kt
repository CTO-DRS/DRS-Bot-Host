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

    @Test
    fun formatUptime_handlesNullAndValues() {
        assertEquals("--", com.drsbot.host.util.Formatters.formatUptime(null))
        assertEquals("--", com.drsbot.host.util.Formatters.formatUptime(-1.0))
        assertEquals("--", com.drsbot.host.util.Formatters.formatUptime(Double.NaN))
        assertEquals("42s", com.drsbot.host.util.Formatters.formatUptime(42.7))
        assertEquals("1m 05s", com.drsbot.host.util.Formatters.formatUptime(65.2))
        assertEquals("1h 01m", com.drsbot.host.util.Formatters.formatUptime(3_675.0))
        assertEquals("0s", com.drsbot.host.util.Formatters.formatUptime(0.0))
    }

    @Test
    fun formatCpu_handlesNullAndValues() {
        assertEquals("--", com.drsbot.host.util.Formatters.formatCpu(null))
        assertEquals("--", com.drsbot.host.util.Formatters.formatCpu(-0.5))
        assertEquals("--", com.drsbot.host.util.Formatters.formatCpu(Double.NaN))
        assertEquals("0.00s", com.drsbot.host.util.Formatters.formatCpu(0.0))
        assertEquals("0.42s", com.drsbot.host.util.Formatters.formatCpu(0.42))
        assertEquals("12.50s", com.drsbot.host.util.Formatters.formatCpu(12.5))
        assertEquals("1m 05s", com.drsbot.host.util.Formatters.formatCpu(65.4))
        assertEquals("1h 01m", com.drsbot.host.util.Formatters.formatCpu(3_675.0))
    }
}
