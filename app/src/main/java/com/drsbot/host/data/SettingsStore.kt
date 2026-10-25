package com.drsbot.host.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "drs_host_settings")

/**
 * Persists the three host toggles with Jetpack DataStore.
 * Defaults match SettingsViewModel's initial snapshot exactly.
 */
class SettingsStore private constructor(private val context: Context) {

    val settings: Flow<HostSettings> = context.dataStore.data.map { prefs ->
        HostSettings(
            startServiceOnBoot = prefs[KEY_START_ON_BOOT] ?: false,
            autoStartBots = prefs[KEY_AUTO_START_BOTS] ?: true,
            keepCpuAwake = prefs[KEY_KEEP_CPU_AWAKE] ?: true,
        )
    }

    suspend fun setStartServiceOnBoot(enabled: Boolean) {
        context.dataStore.edit { it[KEY_START_ON_BOOT] = enabled }
    }

    suspend fun setAutoStartBots(enabled: Boolean) {
        context.dataStore.edit { it[KEY_AUTO_START_BOTS] = enabled }
    }

    suspend fun setKeepCpuAwake(enabled: Boolean) {
        context.dataStore.edit { it[KEY_KEEP_CPU_AWAKE] = enabled }
    }

    companion object {
        private val KEY_START_ON_BOOT = booleanPreferencesKey("start_service_on_boot")
        private val KEY_AUTO_START_BOTS = booleanPreferencesKey("auto_start_bots")
        private val KEY_KEEP_CPU_AWAKE = booleanPreferencesKey("keep_cpu_awake")

        @Volatile
        private var instance: SettingsStore? = null

        /** Process-wide singleton; always rooted at the application context. */
        fun get(context: Context): SettingsStore =
            instance ?: synchronized(this) {
                instance ?: SettingsStore(context.applicationContext).also { instance = it }
            }
    }
}
