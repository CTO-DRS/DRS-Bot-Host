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
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.StatusChip
import com.drsbot.host.ui.theme.NeonRed
import com.drsbot.host.vm.BotsViewModel

@Composable
fun BotsScreen(onOpenBot: (String) -> Unit) {
    val appContext = LocalAppContext.current
    val vm: BotsViewModel = viewModel {
        BotsViewModel(appContext, SettingsStore.get(appContext))
    }
    val bots by vm.bots.collectAsState()
    val loadError by vm.loadError.collectAsState()
    val actionMessage by vm.actionMessage.collectAsState()

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
                    text = stringResource(R.string.bots_title),
                    style = MaterialTheme.typography.headlineMedium,
                )
            }
            loadError?.let { error ->
                item {
                    Text(text = error, color = NeonRed, style = MaterialTheme.typography.bodySmall)
                }
            }
            actionMessage?.let { message ->
                item {
                    Text(
                        text = message,
                        color = NeonRed,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.clickable { vm.clearActionMessage() },
                    )
                }
            }
            if (bots.isEmpty()) {
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = stringResource(R.string.dashboard_no_bots),
                            style = MaterialTheme.typography.bodyMedium,
                        )
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
                        Column(modifier = Modifier.weight(1f)) {
                            Text(bot.name, style = MaterialTheme.typography.titleMedium)
                            Text(
                                text = "${bot.id} · v${bot.version} · ${bot.restartPolicy}",
                                style = MaterialTheme.typography.bodySmall,
                            )
                            if (!bot.lastError.isNullOrBlank()) {
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    text = bot.lastError!!.lineSequence().firstOrNull() ?: "",
                                    color = NeonRed,
                                    style = MaterialTheme.typography.bodySmall,
                                    maxLines = 2,
                                )
                            }
                        }
                        StatusChip(text = bot.state, color = stateColor(bot.state))
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (bot.state == "RUNNING" || bot.state == "STARTING" || bot.state == "BACKOFF") {
                            Button(onClick = { vm.stop(bot.id) }) {
                                Text(stringResource(R.string.bot_stop))
                            }
                        } else {
                            Button(onClick = { vm.start(bot.id) }) {
                                Text(stringResource(R.string.bot_start))
                            }
                        }
                        OutlinedButton(onClick = { vm.restart(bot.id) }) {
                            Text(stringResource(R.string.bot_restart))
                        }
                    }
                }
            }
            item { Spacer(Modifier.height(12.dp)) }
        }
    }
}
