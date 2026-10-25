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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.LocalAppContext
import com.drsbot.host.R
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.NeonButton
import com.drsbot.host.ui.components.StatusChip
import com.drsbot.host.ui.theme.NeonRed
import com.drsbot.host.ui.theme.TextSecondary
import com.drsbot.host.util.Formatters
import com.drsbot.host.vm.BotsViewModel

private val ACTIVE_STATES = setOf("RUNNING", "STARTING", "BACKOFF", "STOPPING")

@Composable
fun BotsScreen(onOpenBot: (String) -> Unit) {
    val appContext = LocalAppContext.current
    val vm: BotsViewModel = viewModel {
        BotsViewModel(appContext, SettingsStore.get(appContext))
    }
    val bots by vm.bots.collectAsState()
    val loadError by vm.loadError.collectAsState()
    val actionMessage by vm.actionMessage.collectAsState()

    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf("ALL") }

    val filtered = bots.filter { bot ->
        val matchesQuery = query.isBlank() ||
            bot.name.contains(query, ignoreCase = true) ||
            bot.id.contains(query, ignoreCase = true)
        val matchesFilter = when (filter) {
            "ACTIVE" -> bot.state in ACTIVE_STATES
            "STOPPED" -> bot.state == "STOPPED" || bot.state == "COMPLETED"
            "FAILED" -> bot.state == "FAILED"
            else -> true
        }
        matchesQuery && matchesFilter
    }

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

            item {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    singleLine = true,
                    placeholder = { Text(stringResource(R.string.bots_search_hint)) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            item {
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf(
                        "ALL" to R.string.filter_all,
                        "ACTIVE" to R.string.filter_active,
                        "STOPPED" to R.string.filter_stopped,
                        "FAILED" to R.string.filter_failed,
                    ).forEach { (key, labelRes) ->
                        FilterChip(
                            selected = filter == key,
                            onClick = { filter = key },
                            label = { Text(stringResource(labelRes)) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor =
                                MaterialTheme.colorScheme.primaryContainer,
                                selectedLabelColor = MaterialTheme.colorScheme.primary,
                            ),
                        )
                    }
                }
            }

            item {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    NeonButton(
                        text = stringResource(R.string.bots_start_all),
                        onClick = { vm.startAll() },
                    )
                    OutlinedButton(onClick = { vm.stopAll() }) {
                        Text(stringResource(R.string.dashboard_stop_all))
                    }
                }
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
            if (filtered.isEmpty()) {
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = stringResource(R.string.dashboard_no_bots),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
            items(filtered, key = { it.id }) { bot ->
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
                            Spacer(Modifier.height(2.dp))
                            Text(
                                text = stringResource(
                                    R.string.bot_runs_uptime,
                                    bot.runCount,
                                    Formatters.formatUptime(bot.uptimeSeconds),
                                ),
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary,
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
                        StatusChip(
                            text = bot.state,
                            color = stateColor(bot.state),
                            pulse = bot.state == "RUNNING",
                        )
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (bot.state in ACTIVE_STATES) {
                            NeonButton(
                                text = stringResource(R.string.bot_stop),
                                onClick = { vm.stop(bot.id) },
                            )
                        } else {
                            NeonButton(
                                text = stringResource(R.string.bot_start),
                                onClick = { vm.start(bot.id) },
                            )
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
