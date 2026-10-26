package com.drsbot.host

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.animation.Crossfade
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import com.drsbot.host.data.HostSettings
import com.drsbot.host.data.SettingsStore
import com.drsbot.host.navigation.AppNavHost
import com.drsbot.host.ui.screens.SplashScreen
import com.drsbot.host.ui.theme.Accents
import com.drsbot.host.ui.theme.DrsBotHostTheme
import kotlinx.coroutines.delay

/** App context exposed to ViewModels created inside composables. */
val LocalAppContext = staticCompositionLocalOf<android.content.Context> {
    error("LocalAppContext not provided")
}

/**
 * AppCompatActivity (not plain ComponentActivity) is required so the
 * appcompat per-app locale delegate works: the in-app language switcher
 * calls AppCompatDelegate.setApplicationLocales(), which recreates this
 * activity and persists the choice on API < 33.
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val appContext = applicationContext
        setContent {
            CompositionLocalProvider(LocalAppContext provides appContext) {
                val settings by SettingsStore.get(appContext)
                    .settings
                    .collectAsState(initial = HostSettings())
                DrsBotHostTheme(accent = Accents.colorFor(settings.accent)) {
                    var splashDone by remember { mutableStateOf(false) }
                    LaunchedEffect(Unit) {
                        delay(SPLASH_MILLIS)
                        splashDone = true
                    }
                    Crossfade(
                        targetState = splashDone,
                        animationSpec = androidx.compose.animation.core.tween(420),
                        label = "splash-crossfade",
                    ) { finished ->
                        if (finished) {
                            AppNavHost()
                        } else {
                            SplashScreen()
                        }
                    }
                }
            }
        }
    }

    private companion object {
        const val SPLASH_MILLIS = 1_400L
    }
}
