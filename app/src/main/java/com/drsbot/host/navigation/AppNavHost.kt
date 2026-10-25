package com.drsbot.host.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.NavType
import com.drsbot.host.R
import com.drsbot.host.ui.screens.BotDetailScreen
import com.drsbot.host.ui.screens.BotsScreen
import com.drsbot.host.ui.screens.DashboardScreen
import com.drsbot.host.ui.screens.ImportScreen
import com.drsbot.host.ui.screens.MarketScreen
import com.drsbot.host.ui.screens.SettingsScreen

object Routes {
    const val DASHBOARD = "dashboard"
    const val BOTS = "bots"
    const val MARKET = "market"
    const val IMPORT = "import"
    const val SETTINGS = "settings"
    const val BOT_DETAIL = "bot/{botId}"

    fun botDetail(botId: String) = "bot/$botId"
}

private data class TopDestination(val route: String, val labelRes: Int, val icon: @Composable () -> Unit)

@Composable
fun AppNavHost() {
    val navController: NavHostController = rememberNavController()
    val destinations = listOf(
        TopDestination(Routes.DASHBOARD, R.string.nav_dashboard) {
            Icon(Icons.Filled.Dashboard, contentDescription = null)
        },
        TopDestination(Routes.BOTS, R.string.nav_bots) {
            Icon(Icons.Filled.SmartToy, contentDescription = null)
        },
        TopDestination(Routes.MARKET, R.string.nav_market) {
            Icon(Icons.Filled.Storefront, contentDescription = null)
        },
        TopDestination(Routes.IMPORT, R.string.nav_import) {
            Icon(Icons.Filled.AddCircle, contentDescription = null)
        },
        TopDestination(Routes.SETTINGS, R.string.nav_settings) {
            Icon(Icons.Filled.Settings, contentDescription = null)
        },
    )

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route

    Scaffold(
        bottomBar = {
            NavigationBar {
                destinations.forEach { destination ->
                    NavigationBarItem(
                        selected = currentRoute == destination.route,
                        onClick = {
                            navController.navigate(destination.route) {
                                popUpTo(Routes.DASHBOARD) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = destination.icon,
                        label = { Text(stringResource(destination.labelRes)) },
                    )
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Routes.DASHBOARD,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(Routes.DASHBOARD) {
                DashboardScreen(
                    onOpenBot = { botId -> navController.navigate(Routes.botDetail(botId)) },
                    onOpenImport = { navController.navigate(Routes.IMPORT) },
                )
            }
            composable(Routes.BOTS) {
                BotsScreen(
                    onOpenBot = { botId -> navController.navigate(Routes.botDetail(botId)) },
                )
            }
            composable(Routes.MARKET) {
                MarketScreen(
                    onInstalled = { botId ->
                        navController.navigate(Routes.botDetail(botId)) {
                            popUpTo(Routes.MARKET)
                        }
                    },
                )
            }
            composable(Routes.IMPORT) {
                ImportScreen(
                    onImported = { botId ->
                        navController.navigate(Routes.botDetail(botId)) {
                            popUpTo(Routes.IMPORT)
                        }
                    },
                )
            }
            composable(Routes.SETTINGS) {
                SettingsScreen()
            }
            composable(
                route = Routes.BOT_DETAIL,
                arguments = listOf(navArgument("botId") { type = NavType.StringType }),
            ) { entry ->
                val botId = entry.arguments?.getString("botId").orEmpty()
                BotDetailScreen(
                    botId = botId,
                    onBack = { navController.popBackStack() },
                )
            }
        }
    }
}
