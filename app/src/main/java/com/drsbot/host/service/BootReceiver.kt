package com.drsbot.host.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.drsbot.host.data.SettingsStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/** Optional boot autostart, gated by the user's settings toggle. */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.Default).launch {
            try {
                val settings = SettingsStore.get(context).settings.first()
                if (settings.startServiceOnBoot) {
                    BotHostService.start(context)
                }
            } finally {
                pendingResult.finish()
            }
        }
    }
}
