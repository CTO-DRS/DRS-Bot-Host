package com.drsbot.host.vm

import android.content.Context
import android.net.Uri
import android.os.PowerManager
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.BackupResult
import com.drsbot.host.data.HostSettings
import com.drsbot.host.data.RestoreResult
import com.drsbot.host.data.RuntimeInfo
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.data.WebStatusInfo
import com.drsbot.host.di.HostGraph
import com.drsbot.host.util.DeviceReader
import com.drsbot.host.util.PageLanguage
import com.drsbot.host.util.SafIo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File

class SettingsViewModel(
    private val appContext: Context,
    private val settingsStore: SettingsStore,
) : ViewModel() {

    private val repository = HostGraph.repository

    private val _settings = MutableStateFlow(
        HostSettings(
            startServiceOnBoot = false,
            autoStartBots = true,
            keepCpuAwake = true,
            crashAlerts = true,
            accent = "cyan",
            requirementsPolicy = "warn",
            webStatusEnabled = false,
            webStatusPort = 8090,
            webStatusToken = "",
            language = "system",
        ),
    )
    val settings: StateFlow<HostSettings> = _settings.asStateFlow()

    private val _runtimeInfo = MutableStateFlow<RuntimeInfo?>(null)
    val runtimeInfo: StateFlow<RuntimeInfo?> = _runtimeInfo.asStateFlow()

    private val _webStatus = MutableStateFlow(WebStatusInfo(running = false, port = 0, protected = false))
    val webStatus: StateFlow<WebStatusInfo> = _webStatus.asStateFlow()

    private val _batteryExempt = MutableStateFlow(false)
    val batteryExempt: StateFlow<Boolean> = _batteryExempt.asStateFlow()

    /** LAN IPv4 for the status-page URL; refreshed with the runtime info. */
    private val _lanIp = MutableStateFlow("")
    val lanIp: StateFlow<String> = _lanIp.asStateFlow()

    /** One-shot backup/restore feedback (null clears it). */
    private val _backupMessage = MutableStateFlow<String?>(null)
    val backupMessage: StateFlow<String?> = _backupMessage.asStateFlow()

    private val _backupWorking = MutableStateFlow(false)
    val backupWorking: StateFlow<Boolean> = _backupWorking.asStateFlow()

    init {
        viewModelScope.launch {
            settingsStore.settings.collect { value ->
                val previousPolicy = _settings.value.requirementsPolicy
                val previousToken = _settings.value.webStatusToken
                val previousLanguage = _settings.value.language
                _settings.value = value
                // Push the persisted policy into the Python runtime on change.
                if (value.requirementsPolicy != previousPolicy) {
                    repository.setRequirementsPolicy(appContext, value.requirementsPolicy)
                }
                // Restart the status server when the token changed so the new
                // secret takes effect immediately (v1.4 token management).
                if (value.webStatusToken != previousToken && value.webStatusEnabled) {
                    repository.webStatusStart(
                        appContext,
                        value.webStatusPort,
                        value.webStatusToken,
                        PageLanguage.resolve(value.language),
                    )
                    refreshRuntime()
                }
                // Restart the status server when the UI language changed so the
                // browser dashboard matches (v1.9 bilingual status page).
                if (value.language != previousLanguage && value.webStatusEnabled) {
                    repository.webStatusStart(
                        appContext,
                        value.webStatusPort,
                        value.webStatusToken,
                        PageLanguage.resolve(value.language),
                    )
                    refreshRuntime()
                }
            }
        }
        // Make sure the runtime policy matches the persisted one on entry.
        viewModelScope.launch {
            repository.setRequirementsPolicy(appContext, _settings.value.requirementsPolicy)
        }
        refreshRuntime()
        refreshBatteryState()
    }

    fun refreshRuntime() {
        viewModelScope.launch {
            _runtimeInfo.value = repository.runtimeInfo(appContext).getOrNull()
        }
        viewModelScope.launch {
            _webStatus.value = repository.webStatusInfo(appContext)
                .getOrDefault(WebStatusInfo(running = false, port = 0, protected = false))
        }
        viewModelScope.launch {
            _lanIp.value = DeviceReader.lanIpAddress()
        }
    }

    fun refreshBatteryState() {
        val powerManager =
            appContext.getSystemService(Context.POWER_SERVICE) as? PowerManager
        _batteryExempt.value = powerManager?.isIgnoringBatteryOptimizations(appContext.packageName) ?: false
    }

    fun setStartServiceOnBoot(enabled: Boolean) = viewModelScope.launch {
        settingsStore.setStartServiceOnBoot(enabled)
    }

    fun setAutoStartBots(enabled: Boolean) = viewModelScope.launch {
        settingsStore.setAutoStartBots(enabled)
    }

    fun setKeepCpuAwake(enabled: Boolean) = viewModelScope.launch {
        settingsStore.setKeepCpuAwake(enabled)
    }

    fun setCrashAlerts(enabled: Boolean) = viewModelScope.launch {
        settingsStore.setCrashAlerts(enabled)
    }

    fun setAccent(key: String) = viewModelScope.launch {
        settingsStore.setAccent(key)
    }

    fun setRequirementsPolicy(policy: String) = viewModelScope.launch {
        settingsStore.setRequirementsPolicy(policy)
        repository.setRequirementsPolicy(appContext, policy)
    }

    fun setWebStatusEnabled(enabled: Boolean) = viewModelScope.launch {
        settingsStore.setWebStatusEnabled(enabled)
        // Keep the runtime server in sync immediately (the service also does
        // this on boot / settings change).
        if (enabled) {
            val snapshot = _settings.value
            repository.webStatusStart(
                appContext,
                snapshot.webStatusPort,
                snapshot.webStatusToken,
                PageLanguage.resolve(snapshot.language),
            )
        } else {
            repository.webStatusStop(appContext)
        }
        refreshRuntime()
    }

    fun setWebStatusPort(port: Int) = viewModelScope.launch {
        val clamped = port.coerceIn(1024, 65535)
        settingsStore.setWebStatusPort(clamped)
        if (_settings.value.webStatusEnabled) {
            repository.webStatusStart(
                appContext,
                clamped,
                _settings.value.webStatusToken,
                PageLanguage.resolve(_settings.value.language),
            )
        }
        refreshRuntime()
    }

    fun setWebStatusToken(token: String) = viewModelScope.launch {
        settingsStore.setWebStatusToken(token)
    }

    /**
     * v1.6 in-app language switch. Persist the preference (drives the chip
     * UI) and apply the appcompat per-app locale, which recreates the
     * activity so every stringResource() re-resolves. "system" clears the
     * override; on Android 13+ the choice also appears in system settings.
     */
    fun setLanguage(language: String) = viewModelScope.launch {
        settingsStore.setLanguage(language)
        val locales = when (language) {
            "en" -> LocaleListCompat.forLanguageTags("en")
            "ar" -> LocaleListCompat.forLanguageTags("ar")
            else -> LocaleListCompat.getEmptyLocaleList()
        }
        AppCompatDelegate.setApplicationLocales(locales)
    }

    /** Zip every installed bot into <data>/backups/ and report the path. */
    fun backupAll() {
        if (_backupWorking.value) return
        _backupWorking.value = true
        _backupMessage.value = null
        viewModelScope.launch {
            val message = repository.backupAll(appContext).fold(
                onSuccess = { result: BackupResult ->
                    if (result.ok) {
                        "OK: ${result.botCount} bot(s) → ${result.path}"
                    } else {
                        result.errors.joinToString("; ").ifBlank { "backup rejected" }
                    }
                },
                onFailure = { it.message ?: "backup failed" },
            )
            _backupMessage.value = message
            _backupWorking.value = false
        }
    }

    /** Copy a SAF-picked backup zip into the cache and restore it. */
    fun restoreFrom(uri: Uri) {
        if (_backupWorking.value) return
        _backupWorking.value = true
        _backupMessage.value = null
        viewModelScope.launch {
            val message = runCatching {
                val cached = SafIo.copyUriToCache(
                    appContext,
                    uri,
                    "restore-${System.currentTimeMillis()}.zip",
                )
                try {
                    repository.restoreBackup(appContext, cached.absolutePath, overwrite = true)
                        .getOrThrow()
                } finally {
                    cached.delete()
                }
            }.fold(
                onSuccess = { result: RestoreResult ->
                    if (result.ok) {
                        "OK: ${result.count} bot(s) restored — ${result.restored.joinToString(", ")}"
                    } else {
                        (result.errors + result.failures).joinToString("; ")
                            .ifBlank { "restore rejected" }
                    }
                },
                onFailure = { it.message ?: "restore failed" },
            )
            _backupMessage.value = message
            _backupWorking.value = false
        }
    }

    fun clearBackupMessage() {
        _backupMessage.value = null
    }
}
