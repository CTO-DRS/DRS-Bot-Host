package com.drsbot.host.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.LocalAppContext
import com.drsbot.host.R
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.service.BotHostService
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.NeonButton
import com.drsbot.host.ui.components.SectionHeader
import com.drsbot.host.ui.components.StatTile
import com.drsbot.host.ui.components.StatusChip
import com.drsbot.host.util.DeviceReader
import com.drsbot.host.util.Formatters
import com.drsbot.host.vm.BotsViewModel

@Composable
fun DashboardScreen(
    onOpenBot: (String) -> Unit,
    onOpenImport: () -> Unit,
) {
    val appContext = LocalAppContext.current
    val context = LocalContext.current
    val vm: BotsViewModel = viewModel {
        BotsViewModel(appContext, SettingsStore.get(appContext))
    }
    val bots by vm.bots.collectAsState()
    val stats by vm.stats.collectAsState()

    val device = DeviceReader.read(context)

    GlowBackground {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { Spacer(Modifier.height(8.dp)) }
            item {
                Column {
                    Text(
                        text = "D R S   B O T   H O S T",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = stringResource(R.string.dashboard_title),
                        style = MaterialTheme.typography.headlineMedium,
                    )
                }
            }

            // KPI tiles
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile(
                        value = (stats?.total ?: bots.size).toString(),
                        label = stringResource(R.string.stat_bots),
                        accent = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.weight(1f),
                    )
                    StatTile(
                        value = (stats?.running ?: 0).toString(),
                        label = stringResource(R.string.stat_running),
                        accent = com.drsbot.host.ui.theme.NeonMint,
                        modifier = Modifier.weight(1f),
                    )
                    StatTile(
                        value = (stats?.failed ?: 0).toString(),
                        label = stringResource(R.string.stat_failed),
                        accent = com.drsbot.host.ui.theme.NeonRed,
                        modifier = Modifier.weight(1f),
                    )
                    StatTile(
                        value = (stats?.restarts ?: 0).toString(),
                        label = stringResource(R.string.stat_restarts),
                        accent = com.drsbot.host.ui.theme.NeonAmber,
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            // Host service control
            item {
                GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                    SectionHeader(stringResource(R.string.dashboard_service_section))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        NeonButton(
                            text = stringResource(R.string.dashboard_start_host),
                            onClick = { BotHostService.start(appContext) },
                        )
                        OutlinedButton(onClick = { vm.stopAll() }) {
                            Text(stringResource(R.string.dashboard_stop_all))
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = { vm.startAll() }) {
                        Text(stringResource(R.string.dashboard_start_all))
                    }
                }
            }

            // System telemetry
            item {
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    SectionHeader(stringResource(R.string.dashboard_system_section))
                    InfoRow(
                        label = stringResource(R.string.system_battery),
                        value = device.batteryPercent?.let { "$it%" } ?: "--",
                    )
                    InfoRow(
                        label = stringResource(R.string.system_memory),
                        value = if (device.memoryTotalBytes > 0) {
                            "${Formatters.formatBytes(device.memoryUsedBytes)} / " +
                                Formatters.formatBytes(device.memoryTotalBytes)
                        } else {
                            "--"
                        },
                    )
                    InfoRow(
                        label = stringResource(R.string.system_host_uptime),
                        value = Formatters.formatUptime(stats?.uptimeSeconds),
                    )
                }
            }

            // Active bots with live pulse
            item {
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    SectionHeader(stringResource(R.string.dashboard_running_bots))
                    val active = bots.filter {
                        it.state == "RUNNING" || it.state == "STARTING" ||
                            it.state == "BACKOFF" || it.state == "STOPPING"
                    }
                    if (active.isEmpty()) {
                        Text(
                            text = stringResource(R.string.dashboard_no_bots),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    } else {
                        active.forEach { bot ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { onOpenBot(bot.id) }
                                    .padding(vertical = 4.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Column {
                                    Text(bot.name)
                                    Text(
                                        text = Formatters.formatUptime(bot.uptimeSeconds),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = com.drsbot.host.ui.theme.TextSecondary,
                                    )
                                }
                                StatusChip(
                                    text = bot.state,
                                    color = stateColor(bot.state),
                                    pulse = bot.state == "RUNNING",
                                )
                            }
                        }
                    }
                }
            }

            // Import shortcut
            item {
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    SectionHeader(stringResource(R.string.import_title))
                    Text(
                        text = stringResource(R.string.import_note),
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(10.dp))
                    OutlinedButton(onClick = onOpenImport) {
                        Text(stringResource(R.string.import_pick_zip))
                    }
                }
            }

            items(bots, key = { it.id }) { bot ->
                GlassCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenBot(bot.id) },
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column {
                            Text(bot.name, style = MaterialTheme.typography.titleMedium)
                            Text(
                                text = "${bot.id} · v${bot.version} · " +
                                    stringResource(R.string.bot_runs_label, bot.runCount),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        StatusChip(text = bot.state, color = stateColor(bot.state))
                    }
                }
            }
            item { Spacer(Modifier.height(12.dp)) }
        }
    }
}

@Composable
internal fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall)
        Text(
            value,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}

internal fun stateColor(state: String) = when (state) {
    "RUNNING" -> com.drsbot.host.ui.theme.NeonMint
    "BACKOFF" -> com.drsbot.host.ui.theme.NeonAmber
    "FAILED" -> com.drsbot.host.ui.theme.NeonRed
    "COMPLETED" -> com.drsbot.host.ui.theme.NeonCyan
    else -> com.drsbot.host.ui.theme.TextSecondary
}
