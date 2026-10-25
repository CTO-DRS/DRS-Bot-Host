package com.drsbot.host.util

import android.app.ActivityManager
import android.content.Context
import android.os.BatteryManager

/** Snapshot of device telemetry shown on the dashboard's System card. */
data class DeviceInfo(
    val batteryPercent: Int?,
    val memoryUsedBytes: Long,
    val memoryTotalBytes: Long,
)

object DeviceReader {

    /** Best-effort read; any failure degrades to null/zero rather than throwing. */
    fun read(context: Context): DeviceInfo {
        val battery = try {
            val manager = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
            val value = manager?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
            if (value in 1..100) value else null
        } catch (_: Exception) {
            null
        }

        val memory = try {
            val activityManager =
                context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
            val info = ActivityManager.MemoryInfo()
            activityManager?.getMemoryInfo(info)
            (info.totalMem - info.availMem) to info.totalMem
        } catch (_: Exception) {
            0L to 0L
        }

        return DeviceInfo(
            batteryPercent = battery,
            memoryUsedBytes = memory.first.coerceAtLeast(0L),
            memoryTotalBytes = memory.second.coerceAtLeast(0L),
        )
    }
}
