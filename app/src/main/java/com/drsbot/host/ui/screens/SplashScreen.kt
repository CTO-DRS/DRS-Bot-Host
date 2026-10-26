package com.drsbot.host.ui.screens

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.drsbot.host.ui.theme.DeepSpace
import com.drsbot.host.ui.theme.DrsThemeTokens
import com.drsbot.host.ui.theme.NeonViolet
import com.drsbot.host.ui.theme.TextSecondary

/**
 * Branded launch splash: a neon ring sweeping around a pulsing core with the
 * wordmark underneath. Pure Canvas + infinite transitions, shown by
 * MainActivity for ~1.4s before crossfading into the nav host.
 */
@Composable
fun SplashScreen(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "splash")
    val sweep by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1200, easing = LinearEasing),
        ),
        label = "sweep",
    )
    val coreAlpha by transition.animateFloat(
        initialValue = 0.35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 600),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "coreAlpha",
    )
    val primary = MaterialTheme.colorScheme.primary

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(DeepSpace),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Canvas(modifier = Modifier.size(96.dp)) {
                val stroke = Stroke(width = 5.dp.toPx(), cap = StrokeCap.Round)
                // Faint full ring as the track.
                drawCircle(
                    color = Color.White.copy(alpha = 0.08f),
                    style = Stroke(width = stroke.width, cap = StrokeCap.Round),
                )
                // Neon arc sweeping around the track.
                drawArc(
                    brush = Brush.sweepGradient(
                        0f to primary,
                        0.75f to NeonViolet,
                        1f to Color.Transparent,
                    ),
                    startAngle = sweep,
                    sweepAngle = 270f,
                    useCenter = false,
                    style = stroke,
                )
                // Pulsing core dot.
                drawCircle(
                    color = primary.copy(alpha = coreAlpha),
                    radius = size.minDimension * 0.14f,
                    center = Offset(size.width / 2f, size.height / 2f),
                )
            }
            Spacer(Modifier.height(20.dp))
            Text(
                text = "D R S",
                style = MaterialTheme.typography.headlineMedium.copy(
                    fontFamily = DrsThemeTokens.statFontFamily,
                    fontWeight = FontWeight.Bold,
                ),
                color = MaterialTheme.colorScheme.onBackground,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = "B O T   H O S T",
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary,
            )
        }
    }
}
