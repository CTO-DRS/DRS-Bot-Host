package com.drsbot.host.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.LocalAppContext
import com.drsbot.host.R
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.SectionHeader
import com.drsbot.host.ui.components.StatusChip
import com.drsbot.host.ui.theme.DrsThemeTokens
import com.drsbot.host.ui.theme.NeonMint
import com.drsbot.host.ui.theme.NeonRed
import com.drsbot.host.util.Formatters
import com.drsbot.host.util.LogFilter
import com.drsbot.host.vm.BotDetailViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
private fun DetailStat(label: String, value: String) {
    Column(horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = com.drsbot.host.ui.theme.TextSecondary,
        )
    }
}

@Composable
fun BotDetailScreen(
    botId: String,
    onBack: () -> Unit,
) {
    val appContext = LocalAppContext.current
    val vm: BotDetailViewModel = viewModel(key = "bot-detail-$botId") {
        BotDetailViewModel(appContext, botId)
    }
    val state by vm.state.collectAsState()
    val clipboardManager = LocalClipboardManager.current
    val listState = rememberLazyListState()
    val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    val logsUnfiltered = LogFilter.isPassthrough(state.logQuery, state.logLevel)

    // Follow the live tail only while no filter hides it.
    LaunchedEffect(state.filteredLogs.size, logsUnfiltered) {
        if (logsUnfiltered && state.filteredLogs.isNotEmpty()) {
            listState.animateScrollToItem(state.filteredLogs.size - 1)
        }
    }

    // Fill the config editor once the first status payload arrives.
    LaunchedEffect(state.status?.id, state.status?.configJson) {
        vm.loadConfigIntoEditor()
    }

    GlowBackground {
        Column(modifier = Modifier.fillMaxSize()) {
            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "back",
                        tint = MaterialTheme.colorScheme.onBackground,
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = state.status?.name ?: botId,
                        style = MaterialTheme.typography.titleLarge,
                    )
                    Text(
                        text = "${state.status?.id ?: botId} · v${state.status?.version ?: "?"}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                state.status?.let { status ->
                    StatusChip(text = status.state, color = stateColor(status.state))
                }
            }

            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                state = listState,
            ) {
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                        SectionHeader(stringResource(R.string.bot_stats_section))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            DetailStat(
                                label = stringResource(R.string.bot_uptime),
                                value = Formatters.formatUptime(state.status?.uptimeSeconds),
                            )
                            DetailStat(
                                label = stringResource(R.string.bot_runs),
                                value = (state.status?.runCount ?: 0).toString(),
                            )
                            DetailStat(
                                label = stringResource(R.string.bot_restarts),
                                value = (state.status?.restarts ?: 0).toString(),
                            )
                            DetailStat(
                                label = stringResource(R.string.bot_cpu),
                                value = Formatters.formatCpu(state.status?.cpuSeconds),
                            )
                            DetailStat(
                                label = stringResource(R.string.bot_policy),
                                value = state.status?.restartPolicy ?: "--",
                            )
                        }
                    }
                }
                item {
                    val status = state.status
                    if (status?.hasSchedule == true) {
                        GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                            SectionHeader(stringResource(R.string.bot_schedule_section))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                            ) {
                                Column {
                                    Text(
                                        text = stringResource(
                                            R.string.bot_schedule_kind,
                                            status.scheduleKind ?: "?",
                                        ),
                                        style = MaterialTheme.typography.bodyMedium,
                                    )
                                    Text(
                                        text = if (status.scheduleEnabled) {
                                            status.scheduleNextStartAt?.let {
                                                stringResource(
                                                    R.string.bot_schedule_next,
                                                    timeFormat.format(Date((it * 1000).toLong())),
                                                )
                                            } ?: stringResource(R.string.bot_schedule_active)
                                        } else {
                                            stringResource(R.string.bot_schedule_disabled)
                                        },
                                        style = MaterialTheme.typography.bodySmall,
                                        color = com.drsbot.host.ui.theme.TextSecondary,
                                    )
                                }
                                Switch(
                                    checked = status.scheduleEnabled,
                                    onCheckedChange = { vm.toggleSchedule(it) },
                                )
                            }
                        }
                    }
                }
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        state.status?.description?.takeIf { it.isNotBlank() }?.let {
                            Text(it, style = MaterialTheme.typography.bodyMedium)
                            Spacer(Modifier.height(8.dp))
                        }
                        state.requirements?.takeIf { it.known && it.missing.isNotEmpty() }?.let {
                            Text(
                                text = stringResource(
                                    R.string.bot_requirements_missing,
                                    it.missing.joinToString(", "),
                                ),
                                color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Spacer(Modifier.height(8.dp))
                        }
                        // v1.3: on-device pip install of the bot's declared deps
                        if (state.status?.requirements?.isNotEmpty() == true) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(
                                    onClick = { vm.installRequirements() },
                                    enabled = !state.installing,
                                ) {
                                    Text(
                                        text = if (state.installing) {
                                            stringResource(R.string.bot_install_running)
                                        } else {
                                            stringResource(R.string.bot_install_button)
                                        },
                                    )
                                }
                            }
                            state.installError?.let {
                                Spacer(Modifier.height(6.dp))
                                Text(it, color = NeonRed, style = MaterialTheme.typography.bodySmall)
                            }
                            state.install?.let { install ->
                                Spacer(Modifier.height(6.dp))
                                if (install.ok) {
                                    Text(
                                        text = stringResource(
                                            R.string.bot_install_ok,
                                            install.installed.joinToString(", "),
                                        ),
                                        color = NeonMint,
                                        style = MaterialTheme.typography.bodySmall,
                                    )
                                } else {
                                    install.errors.take(6).forEach { line ->
                                        Text(
                                            line,
                                            color = NeonRed,
                                            style = MaterialTheme.typography.bodySmall,
                                        )
                                    }
                                }
                            }
                            Spacer(Modifier.height(8.dp))
                        }
                        val status = state.status
                        if (status != null && status.progressTotal != null) {
                            LinearProgressIndicator(
                                progress = {
                                    (status.progressValue ?: 0).toFloat() / status.progressTotal!!
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = "${status.progressLabel ?: ""} " +
                                    "(${status.progressValue ?: 0}/${status.progressTotal})",
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Spacer(Modifier.height(8.dp))
                        }
                        if (status?.lastError != null) {
                            Text(
                                text = status.lastError!!,
                                color = NeonRed,
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Spacer(Modifier.height(8.dp))
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            val current = state.status
                            if (current != null && !current.isTerminal) {
                                Button(onClick = { vm.stop() }) {
                                    Text(stringResource(R.string.bot_stop))
                                }
                            } else {
                                Button(onClick = { vm.start() }) {
                                    Text(stringResource(R.string.bot_start))
                                }
                            }
                            if (current != null &&
                                (current.state == "STOPPING" || current.detached)
                            ) {
                                Button(
                                    onClick = { vm.forceStop() },
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = NeonRed,
                                    ),
                                ) {
                                    Text(stringResource(R.string.bot_force_stop))
                                }
                            }
                            OutlinedButton(onClick = { vm.restart() }) {
                                Text(stringResource(R.string.bot_restart))
                            }
                            OutlinedButton(onClick = { vm.remove(onRemoved = onBack) }) {
                                Text(stringResource(R.string.bot_remove))
                            }
                        }
                    }
                }
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        SectionHeader(stringResource(R.string.bot_export_section))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { vm.exportLogs() }) {
                                Text(stringResource(R.string.bot_export_logs))
                            }
                            state.export?.let { export ->
                                TextButton(onClick = {
                                    clipboardManager.setText(AnnotatedString(export.path))
                                }) {
                                    Icon(
                                        Icons.Filled.ContentCopy,
                                        contentDescription = "copy path",
                                        tint = MaterialTheme.colorScheme.primary,
                                    )
                                    Spacer(Modifier.width(6.dp))
                                    Text(stringResource(R.string.bot_copy_path))
                                }
                            }
                        }
                        state.exportError?.let {
                            Spacer(Modifier.height(6.dp))
                            Text(it, color = NeonRed, style = MaterialTheme.typography.bodySmall)
                        }
                        state.export?.let { export ->
                            Spacer(Modifier.height(6.dp))
                            Text(
                                text = export.path,
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = DrsThemeTokens.logFontFamily,
                            )
                            Text(
                                text = "${export.files} files · ${Formatters.formatBytes(export.bytes)}",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        SectionHeader(stringResource(R.string.bot_config_section))
                        Text(
                            text = stringResource(R.string.bot_config_hint),
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Spacer(Modifier.height(8.dp))
                        val configText = state.configText
                        if (configText != null) {
                            OutlinedTextField(
                                value = configText,
                                onValueChange = vm::onConfigChange,
                                modifier = Modifier.fillMaxWidth(),
                                minLines = 3,
                                maxLines = 10,
                                textStyle = MaterialTheme.typography.bodySmall.copy(
                                    fontFamily = DrsThemeTokens.logFontFamily,
                                ),
                            )
                            Spacer(Modifier.height(8.dp))
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                            ) {
                                Button(onClick = { vm.saveConfig() }) {
                                    Text(stringResource(R.string.bot_config_save))
                                }
                                state.configMessage?.let {
                                    Text(
                                        text = it,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = if (state.configError) {
                                            NeonRed
                                        } else {
                                            MaterialTheme.colorScheme.primary
                                        },
                                    )
                                }
                            }
                        } else {
                            Text("...", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item {
                    Text(
                        text = stringResource(R.string.bot_logs_title),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(start = 4.dp),
                    )
                }
                item {
                    OutlinedTextField(
                        value = state.logQuery,
                        onValueChange = vm::onLogQueryChange,
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        leadingIcon = {
                            Icon(
                                Icons.Filled.Search,
                                contentDescription = "search logs",
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        },
                        placeholder = {
                            Text(
                                stringResource(R.string.bot_logs_search_hint),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        },
                        textStyle = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = DrsThemeTokens.logFontFamily,
                        ),
                    )
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        LogFilter.LEVELS.forEach { level ->
                            FilterChip(
                                selected = state.logLevel == level,
                                onClick = { vm.onLogLevelChange(level) },
                                label = {
                                    Text(
                                        text = level,
                                        style = MaterialTheme.typography.labelSmall,
                                    )
                                },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor =
                                    MaterialTheme.colorScheme.primary.copy(alpha = 0.2f),
                                ),
                            )
                        }
                    }
                }
                if (state.filteredLogs.isEmpty()) {
                    item {
                        Text(
                            text = stringResource(R.string.bot_logs_empty),
                            style = MaterialTheme.typography.bodySmall,
                            color = com.drsbot.host.ui.theme.TextSecondary,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 8.dp),
                        )
                    }
                }
                items(state.filteredLogs) { record ->
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 4.dp),
                    ) {
                        Column {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(
                                    text = timeFormat.format(Date((record.ts * 1000).toLong())),
                                    style = MaterialTheme.typography.bodySmall,
                                )
                                Text(
                                    text = record.level,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = when (record.level) {
                                        "ERROR" -> NeonRed
                                        "WARNING" -> DrsThemeTokens.backoffColor
                                        else -> MaterialTheme.colorScheme.primary
                                    },
                                )
                            }
                            Text(
                                text = record.message,
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = DrsThemeTokens.logFontFamily,
                            )
                        }
                    }
                }
                item { Spacer(Modifier.height(12.dp)) }
            }
        }
    }
}
