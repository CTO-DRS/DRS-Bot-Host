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
 * Curated bot marketplace (v1.4) + custom (community) registry sources
 * (v1.6): fetch the registry, install entries through the same hardened
 * downloader/importer as every other import, and manage alternate registry
 * URLs persisted by the host. A fetch without an explicit URL uses the
 * first saved custom source, falling back to the project's own registry.
 */
class MarketViewModel(private val appContext: Context) : ViewModel() {

    private val repository = HostGraph.repository

    private val _state = MutableStateFlow<MarketUiState>(MarketUiState.Loading)
    val state: StateFlow<MarketUiState> = _state.asStateFlow()

    private val _overwrite = MutableStateFlow(false)
    val overwrite: StateFlow<Boolean> = _overwrite.asStateFlow()

    private val _sources = MutableStateFlow<List<String>>(emptyList())
    val sources: StateFlow<List<String>> = _sources.asStateFlow()

    private val _sourceMessage = MutableStateFlow<String?>(null)
    val sourceMessage: StateFlow<String?> = _sourceMessage.asStateFlow()

    init {
        refresh()
    }

    fun setOverwrite(enabled: Boolean) {
        _overwrite.value = enabled
    }

    fun refresh() {
        _state.value = MarketUiState.Loading
        viewModelScope.launch {
            repository.registrySources(appContext).fold(
                onSuccess = { list -> _sources.value = list },
                onFailure = { /* sources are optional; keep whatever we had */ },
            )
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

    /** Fetch a specific registry URL (a saved source or a one-off entry). */
    fun fetchSource(url: String) {
        _state.value = MarketUiState.Loading
        viewModelScope.launch {
            repository.marketplaceFetch(appContext, url).fold(
                onSuccess = { registry: MarketRegistry ->
                    _state.value = if (registry.ok) {
                        MarketUiState.Ready(registry)
                    } else {
                        MarketUiState.Failure(
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

    /** Validate + persist a custom registry URL, then refresh the list. */
    fun addSource(url: String) {
        viewModelScope.launch {
            repository.addRegistrySource(appContext, url).fold(
                onSuccess = {
                    _sourceMessage.value = null
                    _sources.value = repository.registrySources(appContext)
                        .getOrDefault(_sources.value)
                },
                onFailure = { throwable ->
                    _sourceMessage.value = throwable.message ?: "rejected"
                },
            )
        }
    }

    /** Remove a saved custom registry URL. */
    fun removeSource(url: String) {
        viewModelScope.launch {
            repository.removeRegistrySource(appContext, url).fold(
                onSuccess = {
                    _sourceMessage.value = null
                    _sources.value = repository.registrySources(appContext)
                        .getOrDefault(_sources.value)
                },
                onFailure = { throwable ->
                    _sourceMessage.value = throwable.message ?: "rejected"
                },
            )
        }
    }

    /** Acknowledge the sources message (shown inline in the UI). */
    fun consumeSourceMessage() {
        _sourceMessage.value = null
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
