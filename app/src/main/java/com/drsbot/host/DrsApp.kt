package com.drsbot.host

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager

class DrsApp : Application() {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_HOST,
            getString(R.string.notif_channel_host),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notif_channel_host_desc)
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)

        val alerts = NotificationChannel(
            CHANNEL_ALERTS,
            getString(R.string.notif_channel_alerts),
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = getString(R.string.notif_channel_alerts_desc)
        }
        manager.createNotificationChannel(alerts)
    }

    companion object {
        const val CHANNEL_HOST = "bot_host"
        const val CHANNEL_ALERTS = "bot_alerts"
        const val NOTIFICATION_HOST_ID = 1001
        const val NOTIFICATION_ALERT_BASE_ID = 2001
    }
}
