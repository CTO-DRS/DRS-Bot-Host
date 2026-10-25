package com.drsbot.host.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.BotStatus
import com.drsbot.host.data.HostStats
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.di.HostGraph
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Polls the Python supervisor and exposes the bot list + fleet stats. */
class BotsViewModel(
    private val appContext: Context,
    settingsStore: SettingsStore,
) : ViewModel() {

    private val repository = HostGraph.repository

    private val _bots = MutableStateFlow<List<BotStatus>>(emptyList())
    val bots: StateFlow<List<BotStatus>> = _bots.asStateFlow()

    private val _stats = MutableStateFlow<HostStats?>(null)
    val stats: StateFlow<HostStats?> = _stats.asStateFlow()

    private val _loadError = MutableStateFlow<String?>(null)
    val loadError: StateFlow<String?> = _loadError.asStateFlow()

    private val _actionMessage = MutableStateFlow<String?>(null)
    val actionMessage: StateFlow<String?> = _actionMessage.asStateFlow()

    val settings = settingsStore.settings

    init {
        viewModelScope.launch {
            while (true) {
                refresh()
                delay(1_500)
            }
        }
    }

    suspend fun refresh() {
        repository.listBots(appContext)
            .onSuccess { _bots.value = it; _loadError.value = null }
            .onFailure { _loadError.value = it.message }
        repository.hostStats(appContext)
            .onSuccess { _stats.value = it }
    }

    fun start(botId: String) = launchAction { repository.start(appContext, botId) }

    fun stop(botId: String) = launchAction { repository.stop(appContext, botId) }

    fun restart(botId: String) = launchAction { repository.restart(appContext, botId) }

    fun remove(botId: String) = launchAction { repository.remove(appContext, botId) }

    fun stopAll() = launchAction { repository.stopAll(appContext) }

    /** Starts every bot that is currently in a terminal state. */
    fun startAll() {
        viewModelScope.launch {
            val candidates = _bots.value.filter { it.isTerminal }.map { it.id }
            for (botId in candidates) {
                repository.start(appContext, botId)
            }
            if (candidates.isEmpty()) {
                _actionMessage.value = null
            }
            refresh()
        }
    }

    private fun launchAction(action: suspend () -> Result<Boolean>) {
        viewModelScope.launch {
            action()
                .onSuccess { if (!it) _actionMessage.value = "Action rejected by host" }
                .onFailure { _actionMessage.value = it.message ?: "Action failed" }
            refresh()
        }
    }

    fun clearActionMessage() {
        _actionMessage.value = null
    }
}
