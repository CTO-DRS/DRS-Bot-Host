package com.drsbot.host.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.ImportResult
import com.drsbot.host.data.SkillInfo
import com.drsbot.host.di.HostGraph
import com.drsbot.host.util.SafIo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File

sealed interface ImportUiState {
    data object Idle : ImportUiState
    data object Working : ImportUiState
    data class Success(val botId: String, val files: Int, val bytes: Long) : ImportUiState
    data class Failure(val errors: List<String>) : ImportUiState
}

/** Handles ZIP / folder imports coming from the SAF pickers. */
class ImportViewModel(private val appContext: Context) : ViewModel() {

    private val repository = HostGraph.repository

    private val _state = MutableStateFlow<ImportUiState>(ImportUiState.Idle)
    val state: StateFlow<ImportUiState> = _state.asStateFlow()

    private val _overwrite = MutableStateFlow(false)
    val overwrite: StateFlow<Boolean> = _overwrite.asStateFlow()

    private val _skills = MutableStateFlow<List<SkillInfo>>(emptyList())
    val skills: StateFlow<List<SkillInfo>> = _skills.asStateFlow()

    init {
        refreshSkills()
    }

    /** One-tap bot templates (v1.3 skill registry). */
    fun refreshSkills() {
        viewModelScope.launch {
            _skills.value = HostGraph.repository.listSkills(appContext).getOrDefault(emptyList())
        }
    }

    /** Materialises a skill template into the cache and imports it. */
    fun createFromSkill(skill: SkillInfo) {
        _state.value = ImportUiState.Working
        viewModelScope.launch {
            val result = runCatching {
                val dest = File(appContext.cacheDir, "skill-${System.currentTimeMillis()}")
                try {
                    val scaffolded = HostGraph.repository
                        .scaffoldSkill(appContext, skill.key, skill.title, dest)
                        .getOrThrow()
                    if (!scaffolded.ok) {
                        throw IllegalStateException(
                            scaffolded.errors.joinToString("; ").ifBlank { "scaffold rejected" },
                        )
                    }
                    val folder = File(scaffolded.path!!)
                    try {
                        HostGraph.repository.importFolder(appContext, folder, overwrite = true)
                            .getOrThrow()
                    } finally {
                        folder.deleteRecursively()
                    }
                } finally {
                    dest.parentFile?.let { parent ->
                        parent.listFiles { f -> f.name.startsWith("skill-") }
                            ?.forEach { it.deleteRecursively() }
                    }
                }
            }
            publish(result)
        }
    }

    fun setOverwrite(enabled: Boolean) {
        _overwrite.value = enabled
    }

    fun importZip(uri: android.net.Uri) {
        _state.value = ImportUiState.Working
        viewModelScope.launch {
            val result = runCatching {
                val cached = SafIo.copyUriToCache(
                    appContext,
                    uri,
                    "bot-${System.currentTimeMillis()}.zip",
                )
                try {
                    repository.importZip(appContext, cached, _overwrite.value)
                } finally {
                    cached.delete()
                }
            }
            publish(result.map { it.getOrThrow() })
        }
    }

    fun importFolder(treeUri: android.net.Uri) {
        _state.value = ImportUiState.Working
        viewModelScope.launch {
            val result = runCatching {
                val cached: File = SafIo.copyTreeToCache(
                    appContext,
                    treeUri,
                    "folder-${System.currentTimeMillis()}",
                )
                try {
                    repository.importFolder(appContext, cached, _overwrite.value)
                } finally {
                    cached.deleteRecursively()
                }
            }
            publish(result.map { it.getOrThrow() })
        }
    }

    /** Downloads a bot zip over HTTP(S) and imports it (GitHub links supported). */
    fun importUrl(rawUrl: String) {
        val url = rawUrl.trim()
        if (url.isEmpty()) {
            _state.value = ImportUiState.Failure(listOf("Enter a bot URL first"))
            return
        }
        _state.value = ImportUiState.Working
        viewModelScope.launch {
            val result = runCatching {
                repository.importUrl(appContext, url, _overwrite.value).getOrThrow()
            }
            publish(result)
        }
    }

    private fun publish(result: Result<ImportResult>) {
        result.fold(
            onSuccess = { import ->
                if (import.ok && import.botId != null) {
                    _state.value = ImportUiState.Success(import.botId, import.files, import.bytes)
                } else {
                    _state.value = ImportUiState.Failure(
                        import.errors.ifEmpty { listOf("Import rejected by host") },
                    )
                }
            },
            onFailure = { throwable ->
                _state.value = ImportUiState.Failure(
                    listOf(throwable.message ?: "Import failed"),
                )
            },
        )
        SafIo.clearCache(appContext)
    }

    fun reset() {
        _state.value = ImportUiState.Idle
    }
}
