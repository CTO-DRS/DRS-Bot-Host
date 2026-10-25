package com.drsbot.host.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.ImportResult
import com.drsbot.host.data.MarketEntry
import com.drsbot.host.data.MarketRegistry
import com.drsbot.host.di.HostGraph
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface MarketUiState {
    data object Loading : MarketUiState
    data class Ready(
        val registry: MarketRegistry,
        val busyUrls: Set<String> = emptySet(),
        val lastInstalled: String? = null,
    ) : MarketUiState
    data class Failure(val errors: List<String>) : MarketUiState
}

/**
 * Curated bot marketplace (v1.4): fetch the registry, install entries
 * through the same hardened downloader/importer as every other import.
 */
class MarketViewModel(private val appContext: Context) : ViewModel() {

    private val repository = HostGraph.repository

    private val _state = MutableStateFlow<MarketUiState>(MarketUiState.Loading)
    val state: StateFlow<MarketUiState> = _state.asStateFlow()

    private val _overwrite = MutableStateFlow(false)
    val overwrite: StateFlow<Boolean> = _overwrite.asStateFlow()

    init {
        refresh()
    }

    fun setOverwrite(enabled: Boolean) {
        _overwrite.value = enabled
    }

    fun refresh() {
        _state.value = MarketUiState.Loading
        viewModelScope.launch {
            repository.marketplaceFetch(appContext).fold(
                onSuccess = { registry: MarketRegistry ->
                    if (registry.ok) {
                        _state.value = MarketUiState.Ready(registry)
                    } else {
                        _state.value = MarketUiState.Failure(
                            registry.errors.ifEmpty { listOf("registry rejected") },
                        )
                    }
                },
                onFailure = { throwable ->
                    _state.value = MarketUiState.Failure(
                        listOf(throwable.message ?: "registry fetch failed"),
                    )
                },
            )
        }
    }

    fun install(entry: MarketEntry) {
        val current = _state.value as? MarketUiState.Ready ?: return
        if (entry.url in current.busyUrls) return
        _state.value = current.copy(busyUrls = current.busyUrls + entry.url)
        viewModelScope.launch {
            val result = runCatching {
                repository.marketplaceInstall(appContext, entry.url, _overwrite.value)
                    .getOrThrow()
            }
            val base = _state.value as? MarketUiState.Ready ?: return@launch
            val stillBusy = base.busyUrls - entry.url
            _state.value = result.fold(
                onSuccess = { import: ImportResult ->
                    if (import.ok && import.botId != null) {
                        base.copy(busyUrls = stillBusy, lastInstalled = import.botId)
                    } else {
                        // Keep the entry list visible; surface the rejection inline.
                        MarketUiState.Failure(
                            import.errors.ifEmpty { listOf("host rejected the install") },
                        )
                    }
                },
                onFailure = { throwable ->
                    MarketUiState.Failure(listOf(throwable.message ?: "install failed"))
                },
            )
        }
    }

    /** Acknowledge the "installed" banner (navigating to Bots clears it). */
    fun consumeInstalled() {
        val current = _state.value as? MarketUiState.Ready ?: return
        _state.value = current.copy(lastInstalled = null)
    }
}
