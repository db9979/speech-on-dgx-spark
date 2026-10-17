package io.github.db9979.spark

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.SystemClock
import android.view.View
import kotlin.math.abs
import kotlin.math.sin

/**
 * The assistant's face in the app's own parts (drawn, no picture): blinks at rest, a red ring while it listens,
 * a turning arc while it thinks, a moving mouth while it speaks. [hint] is a fixed name from the Spark's events
 * (search, calendar, mail, home, memory, error), shown as a small sign; never text of an answer.
 */
class FaceView(ctx: Context) : View(ctx) {
    var state = Talk.State.REST
        set(v) { field = v; invalidate() }
    var hint = ""
        set(v) { field = v; invalidate() }

    private val skin = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(59, 130, 246) }
    private val visor = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(15, 23, 42) }
    private val eye = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(165, 243, 252) }
    private val antenna = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(34, 211, 238) }
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(165, 243, 252); style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val sign = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val box = RectF()

    override fun onDraw(c: Canvas) {
        val t = SystemClock.uptimeMillis()
        val s = minOf(width, height).toFloat()
        val cx = width / 2f
        val cy = height / 2f
        val r = s * 0.40f
        ring.strokeWidth = s * 0.05f
        when (state) {
            Talk.State.LISTEN -> {   // listening: red, like the antenna in the panel
                antenna.color = Color.rgb(229, 57, 53)
                ring.color = Color.rgb(229, 57, 53)
                ring.alpha = (150 + 100 * sin(t / 180.0)).toInt().coerceIn(60, 255)
                c.drawCircle(cx, cy, r + s * 0.06f, ring)
            }
            Talk.State.THINK -> {
                ring.color = Color.rgb(45, 108, 223)
                ring.alpha = 255
                box.set(cx - r - s * 0.06f, cy - r - s * 0.06f, cx + r + s * 0.06f, cy + r + s * 0.06f)
                c.drawArc(box, (t / 3 % 360).toFloat(), 90f, false, ring)
            }
            else -> {}
        }
        if (state != Talk.State.LISTEN) antenna.color = Color.rgb(34, 211, 238)
        // the robot of the panel and the app icon: blue head, dark visor, light eyes and smile, antenna
        box.set(cx - r, cy - r * 0.85f, cx + r, cy + r * 0.85f)
        c.drawRoundRect(box, r * 0.4f, r * 0.4f, skin)
        box.set(cx - r * 0.74f, cy - r * 0.6f, cx + r * 0.74f, cy + r * 0.6f)
        c.drawRoundRect(box, r * 0.28f, r * 0.28f, visor)
        c.drawCircle(cx, cy - r * 1.05f, r * 0.12f, antenna)
        val blink = state == Talk.State.REST && t % 4200 < 140
        val ew = r * 0.22f
        val eh = if (blink) r * 0.04f else r * 0.22f
        for (dx in floatArrayOf(-r * 0.3f, r * 0.3f)) {
            box.set(cx + dx - ew / 2, cy - r * 0.16f - eh / 2, cx + dx + ew / 2, cy - r * 0.16f + eh / 2)
            c.drawOval(box, eye)
        }
        line.strokeWidth = r * 0.08f
        val mw = r * 0.5f
        if (state == Talk.State.SPEAK) {
            val open = r * (0.05f + 0.14f * abs(sin(t / 95.0)).toFloat())
            box.set(cx - mw / 2, cy + r * 0.24f - open / 2, cx + mw / 2, cy + r * 0.24f + open / 2)
            c.drawOval(box, eye)
        } else {
            box.set(cx - mw / 2, cy + r * 0.02f, cx + mw / 2, cy + r * 0.34f)
            c.drawArc(box, 20f, 140f, false, line)
        }
        val mark = when (hint) {
            "search" -> "🔍"; "calendar" -> "📅"; "mail" -> "✉️"; "home" -> "💡"; "memory" -> "📝"; "error" -> "?"; "happy" -> "✓"
            else -> ""
        }
        if (mark.isNotEmpty()) {
            sign.textSize = s * 0.22f
            c.drawText(mark, cx + r * 0.85f, cy - r * 0.55f, sign)
        }
        if (state != Talk.State.REST || blink || t % 4200 > 4000) postInvalidateOnAnimation() else postInvalidateDelayed(4000 - t % 4200)
    }
}
