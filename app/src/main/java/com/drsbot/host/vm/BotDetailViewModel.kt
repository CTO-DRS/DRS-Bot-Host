package com.drsbot.host.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.BotStatus
import com.drsbot.host.data.ExportResult
import com.drsbot.host.data.LogRecord
import com.drsbot.host.data.RequirementsCheck
import com.drsbot.host.di.HostGraph
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class BotDetailState(
    val status: BotStatus? = null,
    val logs: List<LogRecord> = emptyList(),
    val requirements: RequirementsCheck? = null,
    val error: String? = null,
    val export: ExportResult? = null,
    val exportError: String? = null,
)

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
        _state.value = BotDetailState(
            status = statusResult.getOrNull(),
            logs = logsResult.getOrDefault(emptyList()),
            requirements = reqResult.getOrNull(),
            error = statusResult.exceptionOrNull()?.message,
        )
    }

    fun start() = launchAction { repository.start(appContext, botId) }

    fun stop() = launchAction { repository.stop(appContext, botId) }

    fun restart() = launchAction { repository.restart(appContext, botId) }

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
