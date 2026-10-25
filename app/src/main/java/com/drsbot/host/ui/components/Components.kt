package com.drsbot.host.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.drsbot.host.ui.theme.DeepSpace
import com.drsbot.host.ui.theme.GlassBorderA
import com.drsbot.host.ui.theme.GlassBorderB
import com.drsbot.host.ui.theme.GlassFillA
import com.drsbot.host.ui.theme.GlassFillB
import com.drsbot.host.ui.theme.GridLine
import com.drsbot.host.ui.theme.NeonViolet
import com.drsbot.host.ui.theme.ScanGlow
import com.drsbot.host.ui.theme.TextSecondary

/**
 * Dark futuristic "glass" surface: translucent gradient fill, gradient
 * hairline border, rounded corners. With [accent] the border is tinted with
 * the theme's primary accent so key cards (host service, stats) pop.
 */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    cornerRadius: Int = 20,
    accent: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(cornerRadius.dp)
    val primary = MaterialTheme.colorScheme.primary
    val borderBrush = if (accent) {
        Brush.linearGradient(listOf(primary.copy(alpha = 0.55f), GlassBorderB))
    } else {
        Brush.linearGradient(listOf(GlassBorderA, GlassBorderB))
    }
    Box(
        modifier = modifier
            .clip(shape)
            .background(
                Brush.linearGradient(listOf(GlassFillA, GlassFillB)),
            )
            .border(width = 1.dp, brush = borderBrush, shape = shape)
            .padding(16.dp),
    ) {
        Column(content = content)
    }
}

/**
 * Full-screen animated tech backdrop: deep-space base, faint engineering
 * grid, two slowly drifting neon orbs and a periodic scanline sweep.
 * Pure Canvas drawing (single pass, no allocations per frame beyond the
 * cached brushes) so it stays cheap on low-end devices.
 */
@Composable
fun GlowBackground(
    modifier: Modifier = Modifier,
    content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit,
) {
    val transition = rememberInfiniteTransition(label = "backdrop")
    val drift by transition.animateFloat(
        initialValue = 0f,
        targetValue = (2.0 * Math.PI).toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 36_000, easing = LinearEasing),
        ),
        label = "drift",
    )
    val scan by transition.animateFloat(
        initialValue = -0.2f,
        targetValue = 1.2f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 9_000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "scan",
    )

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(DeepSpace),
    ) {
        Canvas(modifier = Modifier.matchParentSize()) {
            // Engineering grid.
            val step = 28.dp.toPx()
            if (step > 0f) {
                var x = 0f
                while (x <= size.width) {
                    drawLine(GridLine, Offset(x, 0f), Offset(x, size.height), 1f)
                    x += step
                }
                var y = 0f
                while (y <= size.height) {
                    drawLine(GridLine, Offset(0f, y), Offset(size.width, y), 1f)
                    y += step
                }
            }

            // Two neon orbs orbiting their anchors.
            val radius = size.minDimension * 0.55f
            val cyan = MaterialTheme.colorScheme.primary
            val orbAX = size.width * (0.82f + 0.08f * kotlin.math.sin(drift))
            val orbAY = size.height * (0.10f + 0.05f * kotlin.math.cos(drift * 1.3f))
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(cyan.copy(alpha = 0.16f), Color.Transparent),
                    center = Offset(orbAX, orbAY),
                    radius = radius,
                ),
                radius = radius,
                center = Offset(orbAX, orbAY),
            )
            val orbBX = size.width * (0.12f + 0.06f * kotlin.math.cos(drift * 0.8f))
            val orbBY = size.height * (0.90f + 0.05f * kotlin.math.sin(drift * 1.1f))
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(NeonViolet.copy(alpha = 0.18f), Color.Transparent),
                    center = Offset(orbBX, orbBY),
                    radius = radius,
                ),
                radius = radius,
                center = Offset(orbBX, orbBY),
            )

            // Scanline sweep.
            val scanY = scan * size.height
            val bandHeight = size.height * 0.12f
            drawRect(
                brush = Brush.verticalGradient(
                    colors = listOf(Color.Transparent, ScanGlow, Color.Transparent),
                    startY = scanY - bandHeight / 2f,
                    endY = scanY + bandHeight / 2f,
                ),
                topLeft = Offset(0f, scanY - bandHeight / 2f),
                size = androidx.compose.ui.geometry.Size(size.width, bandHeight),
            )
        }
        content()
    }
}

/** Small rounded status pill; [pulse] adds a live "breathing" dot. */
@Composable
fun StatusChip(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
    pulse: Boolean = false,
) {
    val shape = RoundedCornerShape(50)
    val dotAlpha = if (pulse) {
        val transition = rememberInfiniteTransition(label = "pulse")
        val alpha by transition.animateFloat(
            initialValue = 0.35f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = 900),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "dotAlpha",
        )
        alpha
    } else {
        1f
    }
    Row(
        modifier = modifier
            .clip(shape)
            .background(color.copy(alpha = 0.16f))
            .border(1.dp, color.copy(alpha = 0.55f), shape)
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(color.copy(alpha = dotAlpha)),
        )
        Spacer(Modifier.width(6.dp))
        Text(text = text, style = MaterialTheme.typography.labelLarge, color = color)
    }
}

/** Primary call-to-action: horizontal neon gradient with subtle glow border. */
@Composable
fun NeonButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val primary = MaterialTheme.colorScheme.primary
    val shape = RoundedCornerShape(14.dp)
    val alpha = if (enabled) 1f else 0.4f
    Box(
        modifier = modifier
            .clip(shape)
            .background(
                Brush.horizontalGradient(
                    listOf(primary.copy(alpha = 0.9f * alpha), NeonViolet.copy(alpha = 0.75f * alpha)),
                ),
            )
            .border(1.dp, Color.White.copy(alpha = 0.18f * alpha), shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            color = Color(0xFF06121A),
        )
    }
}

/** Dashboard KPI tile: big monospace value, small caps label, accent bar. */
@Composable
fun StatTile(
    value: String,
    label: String,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(16.dp)
    Box(
        modifier = modifier
            .clip(shape)
            .background(Brush.linearGradient(listOf(GlassFillA, GlassFillB)))
            .border(1.dp, GlassBorderB, shape)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        Column {
            Text(
                text = value,
                style = MaterialTheme.typography.titleLarge.copy(
                    fontFamily = com.drsbot.host.ui.theme.DrsThemeTokens.statFontFamily,
                    fontWeight = FontWeight.Bold,
                ),
                color = accent,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary,
            )
            Spacer(Modifier.height(6.dp))
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(2.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(
                        Brush.horizontalGradient(
                            listOf(accent.copy(alpha = 0.9f), accent.copy(alpha = 0.05f)),
                        ),
                    ),
            )
        }
    }
}

/** Small-caps section label with a leading accent dash. */
@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    Row(
        modifier = modifier.padding(bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(width = 14.dp, height = 2.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(primary),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = text.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary,
        )
    }
}
