package com.drsbot.host.di

import android.content.Context
import com.drsbot.host.data.BotRepository
import com.drsbot.host.data.SettingsStore

/**
 * Minimal hand-rolled service locator. The object graph is tiny on purpose;
 * introducing Hilt for three singletons would add more wiring than value.
 */
object HostGraph {

    val repository: BotRepository by lazy { BotRepository() }

    fun settings(context: Context): SettingsStore = SettingsStore.get(context)
}
