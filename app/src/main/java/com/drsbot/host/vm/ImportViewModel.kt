package com.drsbot.host.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drsbot.host.data.GhImportResult
import com.drsbot.host.data.GhScanResult
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

/** v1.8 GitHub scanner UI state: scan results + selection + import outcome. */
data class GhUiState(
    val scanning: Boolean = false,
    val importing: Boolean = false,
    val scannedUrl: String = "",
    val scan: GhScanResult? = null,
    val selected: Set<String> = emptySet(),
    val lastImport: GhImportResult? = null,
)

/** Handles ZIP / folder imports coming from the SAF pickers. */
class ImportViewModel(private val appContext: Context) : ViewModel() {

    private val repository = HostGraph.repository

    private val _state = MutableStateFlow<ImportUiState>(ImportUiState.Idle)
    val state: StateFlow<ImportUiState> = _state.asStateFlow()

    private val _overwrite = MutableStateFlow(false)
    val overwrite: StateFlow<Boolean> = _overwrite.asStateFlow()

    private val _skills = MutableStateFlow<List<SkillInfo>>(emptyList())
    val skills: StateFlow<List<SkillInfo>> = _skills.asStateFlow()

    private val _ghState = MutableStateFlow(GhUiState())
    val ghState: StateFlow<GhUiState> = _ghState.asStateFlow()

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

    // ── v1.8 GitHub scanner ──────────────────────────────────────────────

    /** Scan a pasted link once; auto-detect bots and pre-select when there is exactly one. */
    fun scanGithub(rawUrl: String) {
        val url = rawUrl.trim()
        if (url.isEmpty()) {
            _state.value = ImportUiState.Failure(listOf("Enter a link first"))
            return
        }
        _ghState.value = _ghState.value.copy(
            scanning = true, scan = null, selected = emptySet(), lastImport = null,
        )
        viewModelScope.launch {
            runCatching { repository.githubScan(appContext, url).getOrThrow() }.fold(
                onSuccess = { scan ->
                    val autoSelect = if (scan.bots.size == 1 && scan.bots[0].valid) {
                        setOf(scan.bots[0].dir)
                    } else {
                        emptySet()
                    }
                    _ghState.value = GhUiState(scan = scan, scannedUrl = url, selected = autoSelect)
                },
                onFailure = { throwable ->
                    _ghState.value = _ghState.value.copy(scanning = false)
                    _state.value = ImportUiState.Failure(
                        listOf(throwable.message ?: "Scan failed"),
                    )
                },
            )
        }
    }

    fun toggleGhSelection(path: String) {
        val current = _ghState.value.selected
        _ghState.value = _ghState.value.copy(
            selected = if (path in current) current - path else current + path,
        )
    }

    /** Import every selected bot dir / packaged member from the cached scan. */
    fun importSelectedGh() {
        val gh = _ghState.value
        if (gh.scannedUrl.isEmpty() || gh.selected.isEmpty()) return
        _ghState.value = gh.copy(importing = true, lastImport = null)
        viewModelScope.launch {
            runCatching {
                repository.githubImportSelected(
                    appContext, gh.scannedUrl, gh.selected.toList(), _overwrite.value,
                ).getOrThrow()
            }.fold(
                onSuccess = { result ->
                    _ghState.value = _ghState.value.copy(
                        importing = false,
                        lastImport = result,
                        selected = result.results.filter { !it.ok }
                            .map { it.path }.toSet(),
                    )
                    val firstBot = result.botIds.firstOrNull()
                    if (firstBot != null) {
                        val okItems = result.results.filter { it.ok }
                        _state.value = ImportUiState.Success(
                            firstBot,
                            okItems.sumOf { it.files },
                            okItems.sumOf { it.bytes },
                        )
                    } else {
                        _state.value = ImportUiState.Failure(
                            result.results.filter { !it.ok }
                                .flatMap { it.errors }
                                .ifEmpty { listOf("Import rejected by host") },
                        )
                    }
                },
                onFailure = { throwable ->
                    _ghState.value = _ghState.value.copy(importing = false)
                    _state.value = ImportUiState.Failure(
                        listOf(throwable.message ?: "Import failed"),
                    )
                },
            )
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
