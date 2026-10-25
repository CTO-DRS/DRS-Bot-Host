package com.drsbot.host

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.staticCompositionLocalOf
import com.drsbot.host.data.HostSettings
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.navigation.AppNavHost
import com.drsbot.host.ui.theme.Accents
import com.drsbot.host.ui.theme.DrsBotHostTheme

/** App context exposed to ViewModels created inside composables. */
val LocalAppContext = staticCompositionLocalOf<android.content.Context> {
    error("LocalAppContext not provided")
}

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val appContext = applicationContext
        setContent {
            CompositionLocalProvider(LocalAppContext provides appContext) {
                val settings by SettingsStore.get(appContext)
                    .settings
                    .collectAsState(initial = HostSettings())
                DrsBotHostTheme(accent = Accents.colorFor(settings.accent)) {
                    AppNavHost()
                }
            }
        }
    }
}
