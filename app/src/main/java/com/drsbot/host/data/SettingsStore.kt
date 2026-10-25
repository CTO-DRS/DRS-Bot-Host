package com.drsbot.host.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
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
            crashAlerts = prefs[KEY_CRASH_ALERTS] ?: true,
            accent = prefs[KEY_ACCENT] ?: "cyan",
            requirementsPolicy = prefs[KEY_REQUIREMENTS_POLICY] ?: "warn",
            webStatusEnabled = prefs[KEY_WEB_STATUS_ENABLED] ?: false,
            webStatusPort = prefs[KEY_WEB_STATUS_PORT] ?: 8090,
            webStatusToken = prefs[KEY_WEB_STATUS_TOKEN] ?: "",
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

    suspend fun setCrashAlerts(enabled: Boolean) {
        context.dataStore.edit { it[KEY_CRASH_ALERTS] = enabled }
    }

    suspend fun setAccent(key: String) {
        context.dataStore.edit { it[KEY_ACCENT] = key }
    }

    suspend fun setRequirementsPolicy(policy: String) {
        context.dataStore.edit { it[KEY_REQUIREMENTS_POLICY] = policy }
    }

    suspend fun setWebStatusEnabled(enabled: Boolean) {
        context.dataStore.edit { it[KEY_WEB_STATUS_ENABLED] = enabled }
    }

    suspend fun setWebStatusPort(port: Int) {
        context.dataStore.edit { it[KEY_WEB_STATUS_PORT] = port }
    }

    suspend fun setWebStatusToken(token: String) {
        context.dataStore.edit { it[KEY_WEB_STATUS_TOKEN] = token }
    }

    companion object {
        private val KEY_START_ON_BOOT = booleanPreferencesKey("start_service_on_boot")
        private val KEY_AUTO_START_BOTS = booleanPreferencesKey("auto_start_bots")
        private val KEY_KEEP_CPU_AWAKE = booleanPreferencesKey("keep_cpu_awake")
        private val KEY_CRASH_ALERTS = booleanPreferencesKey("crash_alerts")
        private val KEY_ACCENT = stringPreferencesKey("accent_color")
        private val KEY_REQUIREMENTS_POLICY = stringPreferencesKey("requirements_policy")
        private val KEY_WEB_STATUS_ENABLED = booleanPreferencesKey("web_status_enabled")
        private val KEY_WEB_STATUS_PORT = intPreferencesKey("web_status_port")
        private val KEY_WEB_STATUS_TOKEN = stringPreferencesKey("web_status_token")

        @Volatile
        private var instance: SettingsStore? = null

        /** Process-wide singleton; always rooted at the application context. */
        fun get(context: Context): SettingsStore =
            instance ?: synchronized(this) {
                instance ?: SettingsStore(context.applicationContext).also { instance = it }
            }
    }
}
