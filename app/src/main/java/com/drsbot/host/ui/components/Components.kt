package com.drsbot.host.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.drsbot.host.ui.theme.DeepSpace
import com.drsbot.host.ui.theme.GlassBorderA
import com.drsbot.host.ui.theme.GlassBorderB
import com.drsbot.host.ui.theme.GlassFillA
import com.drsbot.host.ui.theme.GlassFillB
import com.drsbot.host.ui.theme.NeonCyan
import com.drsbot.host.ui.theme.NeonViolet

/**
 * Dark futuristic "glass" surface: translucent gradient fill, gradient hairline
 * border, rounded 20dp corners. Real blur is intentionally not applied here so
 * the look is consistent across all API levels; ambient glow comes from
 * [GlowBackground] behind the content.
 */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    cornerRadius: Int = 20,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(cornerRadius.dp)
    Box(
        modifier = modifier
            .clip(shape)
            .background(
                Brush.linearGradient(listOf(GlassFillA, GlassFillB)),
            )
            .border(
                width = 1.dp,
                brush = Brush.linearGradient(listOf(GlassBorderA, GlassBorderB)),
                shape = shape,
            )
            .padding(16.dp),
    ) {
        Column(content = content)
    }
}

/**
 * Full-screen ambient backdrop: deep-space base with two soft neon orbs.
 * Pure Canvas drawing - cheap, and identical on every device.
 */
@Composable
fun GlowBackground(
    modifier: Modifier = Modifier,
    content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(DeepSpace),
    ) {
        Canvas(modifier = Modifier.matchParentSize()) {
            val radius = size.minDimension * 0.55f
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(NeonCyan.copy(alpha = 0.14f), Color.Transparent),
                    center = Offset(size.width * 0.85f, size.height * 0.08f),
                    radius = radius,
                ),
                radius = radius,
                center = Offset(size.width * 0.85f, size.height * 0.08f),
            )
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(NeonViolet.copy(alpha = 0.16f), Color.Transparent),
                    center = Offset(size.width * 0.10f, size.height * 0.92f),
                    radius = radius,
                ),
                radius = radius,
                center = Offset(size.width * 0.10f, size.height * 0.92f),
            )
        }
        content()
    }
}

/** Small rounded status pill used across the bot cards. */
@Composable
fun StatusChip(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(50)
    Box(
        modifier = modifier
            .clip(shape)
            .background(color.copy(alpha = 0.16f))
            .border(1.dp, color.copy(alpha = 0.55f), shape)
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        androidx.compose.material3.Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            color = color,
        )
    }
}
