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

private val DarkGlassScheme = darkColorScheme(
    primary = NeonCyan,
    onPrimary = Color(0xFF00232A),
    primaryContainer = Color(0xFF003444),
    onPrimaryContainer = NeonCyan,
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
        letterSpacing = 0.2.sp,
    ),
    titleLarge = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
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
    val runningColor: Color = RunningGreen
    val backoffColor: Color = BackoffAmber
    val failedColor: Color = FailedRed
}

@Composable
fun DrsBotHostTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkGlassScheme,
        typography = DrsTypography,
        shapes = DrsShapes,
        content = content,
    )
}
