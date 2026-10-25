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
            "Bot host",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Persistent status of the bot hosting service"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL_HOST = "bot_host"
        const val NOTIFICATION_HOST_ID = 1001
    }
}
