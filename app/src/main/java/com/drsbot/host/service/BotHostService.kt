package com.drsbot.host.service

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.drsbot.host.DrsApp
import com.drsbot.host.MainActivity
import com.drsbot.host.R
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.di.HostGraph
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

/**
 * The "small server" anchor: a specialUse foreground service that keeps the
 * process (and therefore the embedded Python interpreter and all bot threads)
 * alive while the app is not visible.
 */
class BotHostService : LifecycleService() {

    private var wakeLock: PowerManager.WakeLock? = null
    private var alertsEnabled: Boolean = true
    private var knownFailed: Set<String> = emptySet()

    override fun onCreate() {
        super.onCreate()
        // Configure the interpreter + storage synchronously so that any bot
        // started right after the service is up finds a ready host.
        runBlocking {
            HostGraph.repository.listBots(applicationContext) // triggers PyBridge.ensure + configure
        }
        promoteToForeground("Bot host is running")
        observeBots()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_STOP_ALL -> {
                lifecycleScope.launch {
                    HostGraph.repository.stopAll(applicationContext)
                    updateNotification("All bots stopped")
                }
            }
            else -> {
                lifecycleScope.launch {
                    val settingsFlow = SettingsStore.get(applicationContext).settings
                    val snapshot = settingsFlow.first()
                    if (snapshot.autoStartBots) {
                        HostGraph.repository.startAutostartBots(applicationContext)
                    }
                    if (snapshot.keepCpuAwake) {
                        acquireWakeLock()
                    }
                    syncWebStatus(snapshot.webStatusEnabled, snapshot.webStatusPort, snapshot.webStatusToken)
                }
            }
        }
        return START_STICKY
    }

    private fun observeBots() {
        lifecycleScope.launch {
            val repository = HostGraph.repository
            launch {
                SettingsStore.get(applicationContext).settings.collect { settings ->
                    alertsEnabled = settings.crashAlerts
                    syncWebStatus(settings.webStatusEnabled, settings.webStatusPort, settings.webStatusToken)
                }
            }
            while (true) {
                delay(5_000)
                repository.listBots(applicationContext)
                    .onSuccess { bots ->
                        val running = bots.count {
                            it.state == "RUNNING" || it.state == "STARTING" || it.state == "BACKOFF"
                        }
                        updateNotification(
                            if (running == 0) getString(R.string.notif_no_bots)
                            else getString(R.string.notif_bots_running, running),
                        )
                        raiseFailureAlerts(bots)
                    }
            }
        }
    }

    /** Notify once for every bot that newly entered FAILED since the last poll. */
    private fun raiseFailureAlerts(bots: List<com.drsbot.host.data.BotStatus>) {
        val failedNow = bots.filter { it.state == "FAILED" }.map { it.id }.toSet()
        val fresh = failedNow - knownFailed
        knownFailed = failedNow
        if (!alertsEnabled || fresh.isEmpty()) return
        if (
            Build.VERSION.SDK_INT >= 33 &&
            androidx.core.content.ContextCompat.checkSelfPermission(
                this,
                android.Manifest.permission.POST_NOTIFICATIONS,
            ) != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        fresh.forEach { botId ->
            val bot = bots.firstOrNull { it.id == botId } ?: return@forEach
            val reason = bot.lastError?.lineSequence()?.firstOrNull()
                ?: getString(R.string.notif_failed_default)
            val notification = NotificationCompat.Builder(this, DrsApp.CHANNEL_ALERTS)
                .setSmallIcon(android.R.drawable.stat_notify_error)
                .setContentTitle(getString(R.string.notif_failed_title, bot.name))
                .setContentText(reason)
                .setStyle(NotificationCompat.BigTextStyle().bigText(reason))
                .setAutoCancel(true)
                .setContentIntent(
                    PendingIntent.getActivity(
                        this,
                        botId.hashCode(),
                        Intent(this, MainActivity::class.java),
                        PendingIntent.FLAG_IMMUTABLE,
                    ),
                )
                .build()
            manager.notify(
                DrsApp.NOTIFICATION_ALERT_BASE_ID + (botId.hashCode() and 0x7fffffff) % 100_000,
                notification,
            )
        }
    }

    private fun syncWebStatus(enabled: Boolean, port: Int, token: String) {
        lifecycleScope.launch {
            if (enabled) {
                HostGraph.repository.webStatusStart(applicationContext, port, token)
                    .onFailure {
                        android.util.Log.w("BotHostService", "web status start failed: ${it.message}")
                    }
            } else {
                HostGraph.repository.webStatusStop(applicationContext)
            }
        }
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val powerManager = getSystemService(Context.POWER_SERVICE) as? PowerManager
        wakeLock = powerManager?.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "drsbot:host",
        )?.apply { acquire() }
    }

    private fun buildNotification(text: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val stopAllIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, BotHostService::class.java).setAction(ACTION_STOP_ALL),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, DrsApp.CHANNEL_HOST)
            .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openIntent)
            .addAction(0, getString(R.string.dashboard_stop_all), stopAllIntent)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    private fun promoteToForeground(text: String) {
        val notification = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            ServiceCompat.startForeground(
                this,
                DrsApp.NOTIFICATION_HOST_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            ServiceCompat.startForeground(
                this,
                DrsApp.NOTIFICATION_HOST_ID,
                notification,
                0,
            )
        }
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(DrsApp.NOTIFICATION_HOST_ID, buildNotification(text))
    }

    override fun onDestroy() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP_ALL = "com.drsbot.host.action.STOP_ALL"

        fun start(context: Context) {
            val intent = Intent(context, BotHostService::class.java)
            context.startForegroundService(intent)
        }
    }
}
