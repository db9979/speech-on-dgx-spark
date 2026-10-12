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
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

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
        request("GET", "/api/notaus", null)?.takeIf { it.first == 200 }?.let { JSONObject(it.second) }
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

    private fun openPanel(url: String) {
        val i = Intent(this, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse(url))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 1, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(i)
        }
    }

    private fun send(path: String, body: String) {
        Thread {
            val r = try { request("POST", path, body) } catch (_: Exception) { null }
            val text = when (r?.first) {
                200 -> if (path.endsWith("/mine")) "Mein Notaus ist an." else "Notaus Stufe 2 ist an."
                409 -> "Steht schon so."
                403 -> "Das dürfen nur Admins."
                401, null -> "Nicht angemeldet oder der Spark ist nicht erreichbar."
                else -> "Ging nicht (${r?.first})."
            }
            main.post { toast(text) }
            state()?.let { s -> main.post { show(s) } }
        }.start()
    }

    /** One request to the own Spark with the page's login; (status, body) or null without an address or login. */
    private fun request(method: String, path: String, body: String?): Pair<Int, String>? {
        val base = Store(this).base ?: return null
        val c = NotePoll.cookie(base) ?: return null
        val conn = URL(base + path).openConnection() as HttpURLConnection
        conn.connectTimeout = 10000
        conn.readTimeout = 10000
        conn.instanceFollowRedirects = false
        conn.requestMethod = method
        conn.setRequestProperty("Cookie", c)
        conn.setRequestProperty("User-Agent", "SparkAndroid/${BuildConfig.VERSION_NAME}")
        try {
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toByteArray()) }
            }
            val code = conn.responseCode
            // Mein Notaus ends every login of the profile and hands this one a fresh cookie: give it to the page
            conn.headerFields["Set-Cookie"]?.forEach { v -> main.post { CookieManager.getInstance().setCookie(base, v) } }
            val stream = if (code < 400) conn.inputStream else conn.errorStream
            return code to (stream?.use { NotePoll.readSome(it) } ?: "")
        } finally {
            conn.disconnect()
        }
    }

    private fun toast(text: String) = android.widget.Toast.makeText(this, text, android.widget.Toast.LENGTH_LONG).show()
}
