package com.drsbot.host.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.BotStatus
import com.drsbot.host.data.ExportResult
import com.drsbot.host.data.InstallResult
import com.drsbot.host.data.LogRecord
import com.drsbot.host.data.RequirementsCheck
import com.drsbot.host.di.HostGraph
import com.drsbot.host.util.LogFilter
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.json.JSONTokener

data class BotDetailState(
    val status: BotStatus? = null,
    val logs: List<LogRecord> = emptyList(),
    val requirements: RequirementsCheck? = null,
    val error: String? = null,
    val export: ExportResult? = null,
    val exportError: String? = null,
    val configText: String? = null,
    val configMessage: String? = null,
    val configError: Boolean = false,
    val logQuery: String = "",
    val logLevel: String = LogFilter.LEVELS.first(),
    val installing: Boolean = false,
    val install: InstallResult? = null,
    val installError: String? = null,
) {
    /** Log stream narrowed by the active search query + level filter. */
    val filteredLogs: List<LogRecord>
        get() = LogFilter.apply(logs, logQuery, logLevel)
}

/** Polls one bot's status + logs for the detail screen. */
class BotDetailViewModel(
    private val appContext: Context,
    private val botId: String,
) : ViewModel() {

    private val repository = HostGraph.repository

    private val _state = MutableStateFlow(BotDetailState())
    val state: StateFlow<BotDetailState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            while (true) {
                refresh()
                delay(1_500)
            }
        }
    }

    suspend fun refresh() {
        val statusResult = repository.botStatus(appContext, botId)
        val logsResult = repository.recentLogs(appContext, botId, limit = 400)
        val reqResult = repository.checkRequirements(appContext, botId)
        val current = _state.value
        _state.value = BotDetailState(
            status = statusResult.getOrNull(),
            logs = logsResult.getOrDefault(emptyList()),
            requirements = reqResult.getOrNull(),
            error = statusResult.exceptionOrNull()?.message,
            // keep the user's in-progress editor content across polls
            configText = current.configText,
            configMessage = current.configMessage,
            configError = current.configError,
            // keep the active log search across polls
            logQuery = current.logQuery,
            logLevel = current.logLevel,
            // keep transient installer state across polls
            installing = current.installing,
            install = current.install,
            installError = current.installError,
        )
    }

    fun onLogQueryChange(text: String) {
        _state.value = _state.value.copy(logQuery = text)
    }

    fun onLogLevelChange(level: String) {
        _state.value = _state.value.copy(logLevel = level)
    }

    /** Pretty-prints the bot's current config into the editor (once). */
    fun loadConfigIntoEditor() {
        val config = _state.value.status?.configJson ?: return
        if (_state.value.configText != null) return
        val pretty = runCatching {
            // config is always a JSON object on the Python side; pretty-print it
            (JSONTokener(config).nextValue() as? org.json.JSONObject)?.toString(2)
        }.getOrNull() ?: config
        _state.value = _state.value.copy(configText = pretty)
    }

    fun onConfigChange(text: String) {
        _state.value = _state.value.copy(configText = text, configMessage = null)
    }

    fun saveConfig() {
        val text = _state.value.configText ?: return
        viewModelScope.launch {
            repository.setBotConfig(appContext, botId, text)
                .onSuccess {
                    _state.value = _state.value.copy(
                        configMessage = "saved — applies on next start",
                        configError = false,
                    )
                    refresh()
                }
                .onFailure { failure ->
                    _state.value = _state.value.copy(
                        configMessage = failure.message ?: "rejected",
                        configError = true,
                    )
                }
        }
    }

    fun start() = launchAction { repository.start(appContext, botId) }

    /**
     * pip-install the bot's declared requirements into its per-bot site dir
     * (v1.3). Result (including pip output tail) is shown in the UI.
     */
    fun installRequirements() {
        if (_state.value.installing) return
        _state.value = _state.value.copy(installing = true, installError = null)
        viewModelScope.launch {
            repository.installRequirements(appContext, botId)
                .onSuccess { result ->
                    _state.value = _state.value.copy(
                        installing = false,
                        install = result,
                        installError = null,
                    )
                    refresh()
                }
                .onFailure { failure ->
                    _state.value = _state.value.copy(
                        installing = false,
                        installError = failure.message,
                    )
                }
        }
    }

    fun stop() = launchAction { repository.stop(appContext, botId) }

    fun forceStop() = launchAction { repository.forceStop(appContext, botId) }

    fun restart() = launchAction { repository.restart(appContext, botId) }

    fun toggleSchedule(enabled: Boolean) = launchAction {
        repository.setScheduleEnabled(appContext, botId, enabled)
    }

    fun remove(onRemoved: () -> Unit) {
        viewModelScope.launch {
            val result = repository.remove(appContext, botId)
            if (result.getOrDefault(false)) onRemoved() else refresh()
        }
    }

    /** Zip the bot's JSONL logs; the result path is shown + copyable in the UI. */
    fun exportLogs() {
        viewModelScope.launch {
            repository.exportLogs(appContext, botId)
                .onSuccess { result ->
                    _state.value = _state.value.copy(export = result, exportError = null)
                }
                .onFailure { failure ->
                    _state.value = _state.value.copy(exportError = failure.message)
                }
        }
    }

    private fun launchAction(action: suspend () -> Result<Boolean>) {
        viewModelScope.launch {
            action()
            refresh()
        }
    }
}
