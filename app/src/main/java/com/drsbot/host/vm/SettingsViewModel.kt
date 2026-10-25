package com.drsbot.host.vm

import android.content.Context
import android.os.PowerManager
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.HostSettings
import com.drsbot.host.data.RuntimeInfo
import com.drsbot.host.data.SettingsStore
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
        ),
    )
    val settings: StateFlow<HostSettings> = _settings.asStateFlow()

    private val _runtimeInfo = MutableStateFlow<RuntimeInfo?>(null)
    val runtimeInfo: StateFlow<RuntimeInfo?> = _runtimeInfo.asStateFlow()

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
}
