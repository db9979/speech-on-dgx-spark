package io.github.db9979.spark

import android.app.AlertDialog
import android.app.PendingIntent
import android.content.Intent
import android.graphics.drawable.Icon
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import org.json.JSONObject

/**
 * The Notaus as a quick settings tile. It uses the login of the app's page (the WebView's cookie), like NotePoll:
 * an admin (main admin, or a profile in its admin mode) may switch on the big Notaus (stage 2 "Hände weg") or the
 * own one, everyone else only "Mein Notaus". Always behind a question, never by one tap alone. The tile only
 * switches on; lifting stays in the browser at home (admin) or with the PIN (Mein Notaus).
 */
class NotausTile : TileService() {
    private val main = Handler(Looper.getMainLooper())

    override fun onStartListening() {
        super.onStartListening()
        Thread { state()?.let { s -> main.post { show(s) } } }.start()
    }

    override fun onClick() {
        super.onClick()
        Thread {
            val s = state()
            main.post {
                if (s == null) toast("Erst die Spark-App öffnen und anmelden.") else ask(s)
            }
        }.start()
    }

    /** GET /api/notaus with the page's login: {level, may, mine:{on}}; null when signed out or away. */
    private fun state(): JSONObject? = try {
        Api.call(this, "GET", "/api/notaus").takeIf { it.code == 200 }?.json()
    } catch (_: Exception) {
        null
    }

    private fun show(s: JSONObject) {
        val t = qsTile ?: return
        val level = s.optInt("level")
        val mine = s.optJSONObject("mine")?.optBoolean("on") == true
        t.icon = Icon.createWithResource(this, R.drawable.ic_notaus)
        t.label = "Notaus"
        t.state = if (level > 0 || mine) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        t.subtitle = when {
            level > 0 -> "Stufe $level"
            mine -> "Mein Notaus an"
            else -> "aus"
        }
        t.updateTile()
    }

    private fun ask(s: JSONObject) {
        val level = s.optInt("level")
        val mine = s.optJSONObject("mine")?.optBoolean("on") == true
        val admin = s.optBoolean("may")
        val b = AlertDialog.Builder(this).setTitle("Notaus").setNegativeButton("Abbrechen", null)
        when {
            admin && level < 2 -> b.setMessage("Den ganzen Spark auf Stufe 2 „Hände weg“ stellen? Aufheben nur als Admin im Browser im Heimnetz.")
                .setPositiveButton("Ganzer Spark") { _, _ -> send("/api/notaus", "{\"level\":2}") }
                .also { if (!mine) it.setNeutralButton("Mein Notaus") { _, _ -> send("/api/notaus/mine", "{}") } }
            !mine -> b.setMessage("Dein Profil stilllegen? Anmeldungen und Geräte werden gesperrt, in deinem Namen passiert nichts. Aufheben im Browser mit deiner PIN.")
                .setPositiveButton("Mein Notaus") { _, _ -> send("/api/notaus/mine", "{}") }
            else -> {
                val text = if (level > 0) "Der Notaus steht auf Stufe $level." else "Mein Notaus ist schon an. Aufheben im Browser unter Ich → Sicherheit."
                b.setMessage(text)
                // the way in the text as a button: opens that place of the own panel in the app (Wege.kt)
                Store(this).base?.let { base -> Wege.find(text)?.let { b.setPositiveButton("Im Panel öffnen") { _, _ -> openPanel(Wege.link(base, text)) } } }
            }
        }
        try {
            showDialog(b.create())
        } catch (_: Exception) {
            toast("Der Dialog geht hier nicht, bitte die App öffnen.")
        }
    }

    private fun openPanel(url: String) =
        collapseTo(this, Intent(this, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse(url)))

    private fun send(path: String, body: String) {
        Thread {
            val r = try { Api.call(this, "POST", path, body.toByteArray()) } catch (_: Exception) { null }
            val text = when (r?.code) {
                200 -> if (path.endsWith("/mine")) "Mein Notaus ist an." else "Notaus Stufe 2 ist an."
                409 -> "Steht schon so."
                403 -> "Das dürfen nur Admins."
                401, null -> "Nicht angemeldet oder der Spark ist nicht erreichbar."
                else -> "Ging nicht (${r?.code})."
            }
            main.post { toast(text) }
            state()?.let { s -> main.post { show(s) } }
        }.start()
    }

    private fun toast(text: String) = android.widget.Toast.makeText(this, text, android.widget.Toast.LENGTH_LONG).show()
}

/** Opens [i] from a quick settings tile and closes the panel (Android 14 wants a PendingIntent for it). */
internal fun collapseTo(t: TileService, i: Intent) {
    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
    if (Build.VERSION.SDK_INT >= 34) {
        t.startActivityAndCollapse(PendingIntent.getActivity(t, 1, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
    } else {
        @Suppress("DEPRECATION")
        t.startActivityAndCollapse(i)
    }
}
