package com.drsbot.host.vm

import android.content.Context
import android.os.PowerManager
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.HostSettings
import com.drsbot.host.data.RuntimeInfo
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.data.WebStatusInfo
import com.drsbot.host.di.HostGraph
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

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
        ),
    )
    val settings: StateFlow<HostSettings> = _settings.asStateFlow()

    private val _runtimeInfo = MutableStateFlow<RuntimeInfo?>(null)
    val runtimeInfo: StateFlow<RuntimeInfo?> = _runtimeInfo.asStateFlow()

    private val _webStatus = MutableStateFlow(WebStatusInfo(running = false, port = 0, protected = false))
    val webStatus: StateFlow<WebStatusInfo> = _webStatus.asStateFlow()

    private val _batteryExempt = MutableStateFlow(false)
    val batteryExempt: StateFlow<Boolean> = _batteryExempt.asStateFlow()

    init {
        viewModelScope.launch {
            settingsStore.settings.collect { value ->
                val previous = _settings.value.requirementsPolicy
                _settings.value = value
                // Push the persisted policy into the Python runtime on change.
                if (value.requirementsPolicy != previous) {
                    repository.setRequirementsPolicy(appContext, value.requirementsPolicy)
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
            val port = _settings.value.webStatusPort
            repository.webStatusStart(appContext, port)
        } else {
            repository.webStatusStop(appContext)
        }
        refreshRuntime()
    }

    fun setWebStatusPort(port: Int) = viewModelScope.launch {
        val clamped = port.coerceIn(1024, 65535)
        settingsStore.setWebStatusPort(clamped)
        if (_settings.value.webStatusEnabled) {
            repository.webStatusStart(appContext, clamped)
        }
        refreshRuntime()
    }
}
