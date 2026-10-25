package com.drsbot.host.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Named accent choices persisted in Settings and applied app-wide. */
object Accents {
    const val CYAN = "cyan"
    const val VIOLET = "violet"
    const val MINT = "mint"
    const val AMBER = "amber"

    val all: List<Pair<String, Color>> = listOf(
        CYAN to NeonCyan,
        VIOLET to NeonViolet,
        MINT to NeonMint,
        AMBER to NeonAmber,
    )

    fun colorFor(key: String?): Color =
        all.firstOrNull { it.first == key }?.second ?: NeonCyan
}

private fun darkGlassScheme(accent: Color) = darkColorScheme(
    primary = accent,
    onPrimary = Color(0xFF06121A),
    primaryContainer = accent.copy(alpha = 0.18f),
    onPrimaryContainer = accent,
    secondary = NeonViolet,
    onSecondary = Color.White,
    tertiary = NeonMint,
    background = DeepSpace,
    onBackground = TextPrimary,
    surface = SpaceNavy,
    onSurface = TextPrimary,
    surfaceVariant = PanelNavy,
    onSurfaceVariant = TextSecondary,
    outline = Color(0x33FFFFFF),
    error = NeonRed,
    onError = Color(0xFF2A0000),
)

private val DrsTypography = Typography(
    headlineMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 26.sp,
        letterSpacing = 0.4.sp,
    ),
    titleLarge = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
    ),
    bodyLarge = TextStyle(
        fontSize = 15.sp,
        lineHeight = 21.sp,
    ),
    bodyMedium = TextStyle(
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    bodySmall = TextStyle(
        fontSize = 12.sp,
        lineHeight = 17.sp,
    ),
    labelLarge = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
    ),
    labelSmall = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 11.sp,
        letterSpacing = 1.4.sp,
    ),
)

private val DrsShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(18.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(30.dp),
)

/** Extra tokens that do not fit Material3's color scheme. */
object DrsThemeTokens {
    val logFontFamily: FontFamily = FontFamily.Monospace
    val statFontFamily: FontFamily = FontFamily.Monospace
    val runningColor: Color = RunningGreen
    val backoffColor: Color = BackoffAmber
    val failedColor: Color = FailedRed
}

@Composable
fun DrsBotHostTheme(
    accent: Color = NeonCyan,
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = darkGlassScheme(accent),
        typography = DrsTypography,
        shapes = DrsShapes,
        content = content,
    )
}
