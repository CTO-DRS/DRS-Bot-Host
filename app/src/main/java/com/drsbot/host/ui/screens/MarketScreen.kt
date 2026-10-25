package com.drsbot.host.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.LocalAppContext
import com.drsbot.host.R
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.NeonButton
import com.drsbot.host.ui.components.SectionHeader
import com.drsbot.host.ui.theme.NeonAmber
import com.drsbot.host.ui.theme.NeonMint
import com.drsbot.host.ui.theme.NeonRed
import com.drsbot.host.vm.MarketUiState
import com.drsbot.host.vm.MarketViewModel

/**
 * Curated marketplace (v1.4): a validated registry of shareable bots, each
 * installed through the same hardened download/import pipeline as a manual
 * URL import. The registry source is the project's own curated list; the
 * host validates every field before anything reaches this screen.
 */
@Composable
fun MarketScreen(onInstalled: (String) -> Unit) {
    val appContext = LocalAppContext.current
    val vm: MarketViewModel = viewModel { MarketViewModel(appContext) }
    val state by vm.state.collectAsState()
    val overwrite by vm.overwrite.collectAsState()

    when (val current = state) {
        is MarketUiState.Ready -> {
            if (current.lastInstalled != null) {
                val botId = current.lastInstalled!!
                LaunchedEffect(botId) {
                    onInstalled(botId)
                    vm.consumeInstalled()
                }
            }
        }
        else -> Unit
    }

    GlowBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResource(R.string.market_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = stringResource(R.string.market_note),
                style = MaterialTheme.typography.bodySmall,
            )

            when (val current = state) {
                is MarketUiState.Loading -> {
                    GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                        Text(stringResource(R.string.market_loading), style = MaterialTheme.typography.bodySmall)
                    }
                }
                is MarketUiState.Failure -> {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        SectionHeader(stringResource(R.string.market_error_title))
                        current.errors.forEach { error ->
                            Text(
                                text = error,
                                color = NeonRed,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        NeonButton(
                            text = stringResource(R.string.market_retry),
                            onClick = vm::refresh,
                        )
                    }
                }
                is MarketUiState.Ready -> {
                    GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                        SectionHeader(stringResource(R.string.market_source))
                        Text(
                            text = current.registry.source,
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Text(
                            text = stringResource(R.string.market_count, current.registry.bots.size),
                            style = MaterialTheme.typography.bodySmall,
                            color = NeonMint,
                        )
                        current.registry.warnings.forEach { warning ->
                            Text(
                                text = warning,
                                color = NeonAmber,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }

                    current.registry.bots.forEach { entry ->
                        MarketEntryCard(
                            title = entry.name,
                            version = entry.version,
                            author = entry.author,
                            description = entry.description,
                            tags = entry.tags,
                            busy = entry.url in current.busyUrls,
                            onInstall = { vm.install(entry) },
                        )
                    }

                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = overwrite, onCheckedChange = vm::setOverwrite)
                            Text(
                                text = stringResource(R.string.market_overwrite),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
private fun MarketEntryCard(
    title: String,
    version: String,
    author: String,
    description: String,
    tags: List<String>,
    busy: Boolean,
    onInstall: () -> Unit,
) {
    GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        if (version.isNotBlank() || author.isNotBlank()) {
            Text(
                text = listOfNotNull(
                    version.takeIf { it.isNotBlank() }?.let { "v$it" },
                    author.takeIf { it.isNotBlank() },
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        if (description.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(description, style = MaterialTheme.typography.bodySmall)
        }
        if (tags.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text = tags.joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = NeonAmber,
            )
        }
        Spacer(Modifier.height(10.dp))
        NeonButton(
            text = if (busy) stringResource(R.string.market_installing)
            else stringResource(R.string.market_install),
            onClick = onInstall,
            enabled = !busy,
        )
    }
}
