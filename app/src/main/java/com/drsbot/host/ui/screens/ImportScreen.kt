package com.drsbot.host.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.LocalAppContext
import com.drsbot.host.R
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.theme.NeonAmber
import com.drsbot.host.ui.theme.NeonMint
import com.drsbot.host.ui.theme.NeonRed
import com.drsbot.host.vm.ImportUiState
import com.drsbot.host.vm.ImportViewModel

@Composable
fun ImportScreen(onImported: (String) -> Unit) {
    val appContext = LocalAppContext.current
    val vm: ImportViewModel = viewModel { ImportViewModel(appContext) }
    val state by vm.state.collectAsState()
    val overwrite by vm.overwrite.collectAsState()

    val zipPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri -> uri?.let(vm::importZip) }

    val folderPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree(),
    ) { uri -> uri?.let(vm::importFolder) }

    // Navigate to the freshly imported bot once.
    when (val current = state) {
        is ImportUiState.Success -> {
            androidx.compose.runtime.LaunchedEffect(current.botId) {
                onImported(current.botId)
                vm.reset()
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
                text = stringResource(R.string.import_title),
                style = MaterialTheme.typography.headlineMedium,
            )

            GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                Text(
                    text = stringResource(R.string.import_skills_title),
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    text = stringResource(R.string.import_skills_note),
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
                val skills = vm.skills.collectAsState().value
                if (skills.isEmpty()) {
                    Text("...", style = MaterialTheme.typography.bodySmall)
                } else {
                    skills.forEach { skill ->
                        SkillRow(
                            title = skill.title,
                            description = skill.description,
                            requires = skill.requirements.joinToString(", "),
                            enabled = state !is ImportUiState.Working,
                            onCreate = { vm.createFromSkill(skill) },
                        )
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }

            GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                Text(
                    text = stringResource(R.string.import_skills_title),
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    text = stringResource(R.string.import_skills_note),
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
                val skills = vm.skills.collectAsState().value
                if (skills.isEmpty()) {
                    Text("...", style = MaterialTheme.typography.bodySmall)
                } else {
                    skills.forEach { skill ->
                        SkillRow(
                            title = skill.title,
                            description = skill.description,
                            requires = skill.requirements.joinToString(", "),
                            enabled = state !is ImportUiState.Working,
                            onCreate = { vm.createFromSkill(skill) },
                        )
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = stringResource(R.string.import_url_title),
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    text = stringResource(R.string.import_url_note),
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
                var url by remember { mutableStateOf("") }
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    placeholder = { Text(stringResource(R.string.import_url_hint)) },
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(
                        onClick = { vm.importUrl(url) },
                        enabled = state !is ImportUiState.Working && url.isNotBlank(),
                    ) {
                        Text(stringResource(R.string.import_url_button))
                    }
                }
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = stringResource(R.string.import_pick_zip),
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    text = stringResource(R.string.import_note),
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(onClick = {
                        zipPicker.launch(arrayOf("application/zip", "application/octet-stream"))
                    }) {
                        Text(stringResource(R.string.import_pick_zip))
                    }
                }
                Spacer(Modifier.height(10.dp))
                OutlinedButton(onClick = { folderPicker.launch(null) }) {
                    Text(stringResource(R.string.import_pick_folder))
                }
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = overwrite, onCheckedChange = vm::setOverwrite)
                    Text(
                        text = stringResource(R.string.import_overwrite),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }

            when (val current = state) {
                is ImportUiState.Working -> {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Text("...", style = MaterialTheme.typography.titleMedium)
                    }
                }
                is ImportUiState.Success -> {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = current.botId,
                            color = NeonMint,
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Text(
                            text = "${current.files} files · ${current.bytes} bytes",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                is ImportUiState.Failure -> {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        current.errors.forEach { error ->
                            Text(
                                text = error,
                                color = NeonRed,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
                else -> Unit
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
private fun SkillRow(
    title: String,
    description: String,
    requires: String,
    enabled: Boolean,
    onCreate: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(title, style = MaterialTheme.typography.titleSmall)
        Text(description, style = MaterialTheme.typography.bodySmall)
        if (requires.isNotBlank()) {
            Text(
                text = stringResource(R.string.import_skills_requires, requires),
                color = NeonAmber,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        Spacer(Modifier.height(6.dp))
        Button(onClick = onCreate, enabled = enabled) {
            Text(stringResource(R.string.import_skills_create))
        }
    }
}
