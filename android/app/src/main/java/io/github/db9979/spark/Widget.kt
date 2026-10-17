package io.github.db9979.spark

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ShortcutInfo
import android.content.pm.ShortcutManager
import android.graphics.drawable.Icon
import android.net.Uri
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.view.View
import android.widget.RemoteViews
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * The Spark widget on the home screen ("Android: Spark als Assistent"): the face, today's numbers (appointments,
 * reminders, unread chats; only numbers, never titles) and where a device of the profile listens in room mode
 * (only where and until when). The microphone opens the assistant sheet. It reads /api/profile/today and
 * /api/room/active with the app's login; the Spark answers only what the profile may see.
 */
class SparkWidget : AppWidgetProvider() {
    override fun onUpdate(ctx: Context, mgr: AppWidgetManager, ids: IntArray) {
        val done = goAsync()
        Thread {
            try { refresh(ctx) } finally { done.finish() }
        }.start()
    }

    companion object {
        /** Draws every Spark widget anew (not on the main thread: it asks the Spark). */
        fun refresh(ctx: Context) {
            val mgr = AppWidgetManager.getInstance(ctx)
            val ids = mgr.getAppWidgetIds(ComponentName(ctx, SparkWidget::class.java))
            if (ids.isEmpty()) return
            val store = Store(ctx)
            val v = RemoteViews(ctx.packageName, R.layout.widget)
            val open = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(ctx, 10, open, PendingIntent.FLAG_IMMUTABLE))
            v.setOnClickPendingIntent(R.id.w_mic, PendingIntent.getActivity(ctx, 11, TalkActivity.intent(ctx),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            var room = ""
            val line = when {
                store.base == null -> "Die App einmal öffnen und anmelden."
                !store.assist -> "Vom Admin noch nicht freigegeben (Android: Spark als Assistent)."
                else -> try {
                    val tz = Uri.encode(TimeZone.getDefault().id)
                    val today = Api.call(ctx, "GET", "/api/profile/today?tz=$tz")
                    if (today.code == 401) "Nicht angemeldet: die App einmal öffnen." else {
                        val r = Api.call(ctx, "GET", "/api/room/active").takeIf { it.ok }?.json()
                        if (r != null && r.optInt("count") > 0) {
                            val until = r.optLong("first_until")
                            room = r.optString("first").take(30) + " hört zu" +
                                (if (until > 0) " bis " + SimpleDateFormat("HH:mm", Locale.GERMANY).format(Date(until)) else "")
                        }
                        numbers(today.json().optJSONObject("cards"))
                    }
                } catch (_: Exception) {
                    "Der Spark ist gerade nicht erreichbar."
                }
            }
            v.setTextViewText(R.id.w_line, line)
            v.setTextViewText(R.id.w_room, room)
            v.setViewVisibility(R.id.w_room, if (room.isEmpty()) View.GONE else View.VISIBLE)
            mgr.updateAppWidget(ids, v)
        }

        /** "2 Termine · 1 Erinnerung · 3 ungelesen" from the cards of /api/profile/today. */
        private fun numbers(cards: org.json.JSONObject?): String {
            if (cards == null) return "Heute nichts Neues."
            val parts = mutableListOf<String>()
            val end = Calendar.getInstance().apply { set(Calendar.HOUR_OF_DAY, 23); set(Calendar.MINUTE, 59) }.timeInMillis / 1000
            val evs = cards.optJSONObject("calendar")?.optJSONArray("next")
            if (evs != null) {
                var n = 0
                for (i in 0 until evs.length()) if ((evs.optJSONObject(i)?.optLong("start") ?: Long.MAX_VALUE) <= end) n++
                if (n > 0) parts.add(if (n == 1) "1 Termin" else "$n Termine")
            }
            val rem = cards.optJSONObject("reminders")?.optInt("count") ?: 0
            if (rem > 0) parts.add(if (rem == 1) "1 Erinnerung" else "$rem Erinnerungen")
            val unread = cards.optJSONObject("messages")?.optInt("unread") ?: 0
            if (unread > 0) parts.add("$unread ungelesen")
            return if (parts.isEmpty()) "Heute nichts Neues." else "Heute: " + parts.joinToString(" · ")
        }

        /**
         * The shortcuts on the app icon (long press): only while the assistant is released; they open the sheet
         * listening, the sheet with the keyboard, and the tabs Heute and Chats of the app (#tab=, android.js).
         */
        fun shortcuts(ctx: Context) {
            val sm = ctx.getSystemService(ShortcutManager::class.java) ?: return
            val base = Store(ctx).base
            if (!Store(ctx).assist || base == null) {
                sm.removeAllDynamicShortcuts()
                return
            }
            val tab = { t: String -> Intent(ctx, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse("$base/#tab=$t")) }
            sm.dynamicShortcuts = listOf(
                ShortcutInfo.Builder(ctx, "listen").setShortLabel("Spark zuhören").setIcon(Icon.createWithResource(ctx, R.drawable.ic_mic_dark))
                    .setIntent(TalkActivity.intent(ctx).setAction(Intent.ACTION_VIEW)).build(),
                ShortcutInfo.Builder(ctx, "type").setShortLabel("Frage schreiben").setIcon(Icon.createWithResource(ctx, R.drawable.ic_note))
                    .setIntent(TalkActivity.intent(ctx, type = true).setAction(Intent.ACTION_VIEW)).build(),
                ShortcutInfo.Builder(ctx, "today").setShortLabel("Heute").setIcon(Icon.createWithResource(ctx, R.drawable.ic_face))
                    .setIntent(tab("today")).build(),
                ShortcutInfo.Builder(ctx, "chats").setShortLabel("Chats").setIcon(Icon.createWithResource(ctx, R.drawable.ic_note))
                    .setIntent(tab("chats")).build())
        }
    }
}

/** The tile "Spark zuhören" in the quick settings: opens the assistant sheet listening (only when released). */
class TalkTile : TileService() {
    override fun onStartListening() {
        super.onStartListening()
        val t = qsTile ?: return
        val on = Store(this).assist
        t.icon = Icon.createWithResource(this, R.drawable.ic_mic)
        t.label = "Spark zuhören"
        t.state = if (on) Tile.STATE_INACTIVE else Tile.STATE_UNAVAILABLE
        t.subtitle = if (on) "" else "nicht freigegeben"
        t.updateTile()
    }

    override fun onClick() {
        super.onClick()
        if (Store(this).assist) collapseTo(this, TalkActivity.intent(this))
        else collapseTo(this, Intent(this, MainActivity::class.java).setAction(Intent.ACTION_ASSIST))
    }
}
