package com.drsbot.host.ui.screens

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
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.LocalAppContext
import com.drsbot.host.R
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.service.BotHostService
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.StatusChip
import com.drsbot.host.ui.theme.NeonAmber
import com.drsbot.host.ui.theme.NeonCyan
import com.drsbot.host.ui.theme.NeonMint
import com.drsbot.host.ui.theme.NeonRed
import com.drsbot.host.ui.theme.TextSecondary
import com.drsbot.host.vm.BotsViewModel

@Composable
fun DashboardScreen(
    onOpenBot: (String) -> Unit,
    onOpenImport: () -> Unit,
) {
    val appContext = LocalAppContext.current
    val vm: BotsViewModel = viewModel {
        BotsViewModel(appContext, SettingsStore.get(appContext))
    }
    val bots by vm.bots.collectAsState()

    GlowBackground {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { Spacer(Modifier.height(8.dp)) }
            item {
                Text(
                    text = stringResource(R.string.dashboard_title),
                    style = MaterialTheme.typography.headlineMedium,
                )
            }
            item {
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        text = stringResource(R.string.dashboard_running_bots),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Spacer(Modifier.height(8.dp))
                    val active = bots.filter {
                        it.state == "RUNNING" || it.state == "STARTING"
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
                                    .padding(vertical = 4.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text(bot.name)
                                StatusChip(text = bot.state, color = stateColor(bot.state))
                            }
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(onClick = { BotHostService.start(appContext) }) {
                            Text(stringResource(R.string.dashboard_start_host))
                        }
                        OutlinedButton(onClick = { vm.stopAll() }) {
                            Text(stringResource(R.string.dashboard_stop_all))
                        }
                    }
                }
            }
            item {
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        text = stringResource(R.string.import_title),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Spacer(Modifier.height(8.dp))
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
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column {
                            Text(bot.name, style = MaterialTheme.typography.titleMedium)
                            Text(
                                text = "${bot.id} · v${bot.version}",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        StatusChip(text = bot.state, color = stateColor(bot.state))
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = { onOpenBot(bot.id) }) {
                        Text(stringResource(R.string.bot_logs_title))
                    }
                }
            }
            item { Spacer(Modifier.height(12.dp)) }
        }
    }
}

internal fun stateColor(state: String) = when (state) {
    "RUNNING" -> NeonMint
    "BACKOFF" -> NeonAmber
    "FAILED" -> NeonRed
    "COMPLETED" -> NeonCyan
    else -> TextSecondary
}
