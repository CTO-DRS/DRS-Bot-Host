package com.drsbot.host.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.drsbot.host.BuildConfig
import com.drsbot.host.R
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.ui.components.GlassCard
import com.drsbot.host.ui.components.GlowBackground
import com.drsbot.host.ui.components.SectionHeader
import com.drsbot.host.ui.theme.Accents
import com.drsbot.host.vm.SettingsViewModel

private const val REPO_URL = "https://github.com/CTO-DRS/DRS-Bot-Host"
private const val RELEASES_URL = "$REPO_URL/releases"

@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    val vm: SettingsViewModel = viewModel {
        SettingsViewModel(
            context.applicationContext,
            SettingsStore.get(context.applicationContext),
        )
    }
    val settings by vm.settings.collectAsState()
    val runtime by vm.runtimeInfo.collectAsState()
    val batteryExempt by vm.batteryExempt.collectAsState()

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { }

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
                text = stringResource(R.string.settings_title),
                style = MaterialTheme.typography.headlineMedium,
            )

            GlassCard(modifier = Modifier.fillMaxWidth(), accent = true) {
                SectionHeader(stringResource(R.string.settings_appearance))
                Text(
                    text = stringResource(R.string.settings_accent),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = stringResource(R.string.settings_accent_summary),
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Accents.all.forEach { (key, color) ->
                        AccentSwatch(
                            color = color,
                            selected = settings.accent == key,
                            onSelect = { vm.setAccent(key) },
                        )
                    }
                }
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                SectionHeader(stringResource(R.string.settings_requirements))
                Text(
                    text = stringResource(R.string.settings_requirements_summary),
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("off", "warn", "enforce").forEach { policy ->
                        FilterChip(
                            selected = settings.requirementsPolicy == policy,
                            onClick = { vm.setRequirementsPolicy(policy) },
                            label = {
                                Text(
                                    when (policy) {
                                        "off" -> stringResource(R.string.req_policy_off)
                                        "enforce" -> stringResource(R.string.req_policy_enforce)
                                        else -> stringResource(R.string.req_policy_warn)
                                    },
                                )
                            },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = MaterialTheme.colorScheme.primary.copy(
                                    alpha = 0.2f,
                                ),
                            ),
                        )
                    }
                }
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                SettingRow(
                    title = stringResource(R.string.settings_autostart_service),
                    subtitle = stringResource(R.string.settings_autostart_service_summary),
                    checked = settings.startServiceOnBoot,
                    onChange = vm::setStartServiceOnBoot,
                )
                SettingRow(
                    title = stringResource(R.string.settings_autostart_bots),
                    subtitle = stringResource(R.string.settings_autostart_bots_summary),
                    checked = settings.autoStartBots,
                    onChange = vm::setAutoStartBots,
                )
                SettingRow(
                    title = stringResource(R.string.settings_keep_awake),
                    subtitle = stringResource(R.string.settings_keep_awake_summary),
                    checked = settings.keepCpuAwake,
                    onChange = vm::setKeepCpuAwake,
                )
                SettingRow(
                    title = stringResource(R.string.settings_crash_alerts),
                    subtitle = stringResource(R.string.settings_crash_alerts_summary),
                    checked = settings.crashAlerts,
                    onChange = { enabled ->
                        vm.setCrashAlerts(enabled)
                        if (enabled && Build.VERSION.SDK_INT >= 33 &&
                            ContextCompat.checkSelfPermission(
                                context,
                                Manifest.permission.POST_NOTIFICATIONS,
                            ) != PackageManager.PERMISSION_GRANTED
                        ) {
                            permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        }
                    },
                )
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = stringResource(R.string.settings_battery),
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = if (batteryExempt) {
                        stringResource(R.string.settings_not_optimized)
                    } else {
                        stringResource(R.string.settings_optimized)
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
                Button(onClick = { requestBatteryExemption(context) }) {
                    Text(stringResource(R.string.settings_battery))
                }
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = stringResource(R.string.settings_runtime_info),
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(6.dp))
                runtime?.let { info ->
                    InfoLine("drs_host", "v" + info.hostVersion)
                    InfoLine("python", info.pythonVersion)
                    InfoLine("platform", info.platform)
                    InfoLine("bots", info.botCount.toString())
                    InfoLine("data", info.dataDir)
                } ?: Text("...", style = MaterialTheme.typography.bodySmall)
            }

            GlassCard(modifier = Modifier.fillMaxWidth()) {
                SectionHeader(stringResource(R.string.settings_about))
                InfoLine(stringResource(R.string.settings_version), "v" + BuildConfig.VERSION_NAME)
                InfoLine(
                    stringResource(R.string.settings_repo),
                    "CTO-DRS/DRS-Bot-Host",
                    modifier = Modifier.clickable { openUrl(context, REPO_URL) },
                )
                InfoLine(
                    stringResource(R.string.settings_release),
                    RELEASES_URL.substringAfter("//"),
                    modifier = Modifier.clickable { openUrl(context, RELEASES_URL) },
                )
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
private fun AccentSwatch(
    color: Color,
    selected: Boolean,
    onSelect: () -> Unit,
) {
    Box(
        modifier = Modifier
            .size(36.dp)
            .clip(CircleShape)
            .background(
                androidx.compose.ui.graphics.Brush.radialGradient(
                    listOf(color, color.copy(alpha = 0.55f)),
                ),
            )
            .border(
                width = if (selected) 3.dp else 1.dp,
                color = if (selected) Color.White else Color.White.copy(alpha = 0.25f),
                shape = CircleShape,
            )
            .clickable(onClick = onSelect),
    )
}

@Composable
private fun SettingRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(subtitle, style = MaterialTheme.typography.bodySmall)
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun InfoLine(label: String, value: String, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
        Text(
            value,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(start = 16.dp),
        )
    }
}

private fun openUrl(context: Context, url: String) {
    runCatching {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    }
}

private fun requestBatteryExemption(context: Context) {
    val powerManager = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
    if (powerManager?.isIgnoringBatteryOptimizations(context.packageName) == true) return
    val intent = Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
        data = Uri.parse("package:${context.packageName}")
    }
    runCatching { context.startActivity(intent) }
}
