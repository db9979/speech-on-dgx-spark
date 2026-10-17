package io.github.db9979.spark

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Notes while the app is closed: every 15 minutes the app asks its Spark (GET /api/android/notes) with the
 * login of its page (the WebView's cookie) and shows what came since the last time. No Google service, no key.
 * The answer is data only: titles and texts are shown as plain text; a way in the text ("Ich → Gedächtnis") only
 * decides which page of the own panel a tap opens (Wege.kt).
 */
class NotePoll : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        Thread {
            try {
                if (!LiveConn.running) when (poll(this)) {   // "Mitteilungen sofort": the lasting connection (LiveConn) on or off
                    true -> LiveConn.start(this)
                    false -> LiveConn.stop(this)
                    null -> {}
                }
            } catch (_: Exception) {
            }
            jobFinished(params, false)
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters) = true

    companion object {
        private const val JOB = 1
        private const val CHANNEL = "notes"
        private const val MAX_ANSWER = 64 * 1024

        fun schedule(ctx: Context) {
            val js = ctx.getSystemService(JobScheduler::class.java) ?: return
            if (js.getPendingJob(JOB) != null) return
            js.schedule(
                JobInfo.Builder(JOB, ComponentName(ctx, NotePoll::class.java))
                    .setPeriodic(15 * 60 * 1000L)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true)
                    .build()
            )
        }

        fun stop(ctx: Context) {
            ctx.getSystemService(JobScheduler::class.java)?.cancel(JOB)
        }

        internal fun cookie(base: String): String? {
            // CookieManager belongs to the main thread
            var c: String? = null
            val done = CountDownLatch(1)
            Handler(Looper.getMainLooper()).post {
                try {
                    c = CookieManager.getInstance().getCookie(base)
                } finally {
                    done.countDown()
                }
            }
            done.await(5, TimeUnit.SECONDS)
            return c
        }

        /** Asks once; returns whether the Spark wants the lasting connection (null: no answer). */
        fun poll(ctx: Context): Boolean? {
            val store = Store(ctx)
            val base = store.base ?: return null
            val c = cookie(base) ?: return null
            val conn = URL("$base/api/android/notes?after=${store.lastNote}").openConnection() as HttpURLConnection
            conn.connectTimeout = 15000
            conn.readTimeout = 15000
            conn.instanceFollowRedirects = false
            conn.setRequestProperty("Cookie", c)
            conn.setRequestProperty("User-Agent", "SparkAndroid/${BuildConfig.VERSION_NAME}")
            try {
                if (conn.responseCode != 200) return null   // signed out, switched off or the Spark is away: try again later
                val text = conn.inputStream.use { s -> readSome(s) }
                val d = JSONObject(text)
                handle(ctx, store, base, d)
                Talk.flush(ctx)          // the Spark answers again: questions that waited go out
                SparkWidget.refresh(ctx)
                return d.optBoolean("live", false)
            } finally {
                conn.disconnect()
            }
        }

        /** Shows the notes of an answer (from poll or LiveConn) and keeps the number of the last one. */
        internal fun handle(ctx: Context, store: Store, base: String, d: JSONObject) {
            val notes = d.optJSONArray("notes")
            var last = store.lastNote
            if (notes != null) {
                for (i in 0 until notes.length()) {
                    val n = notes.optJSONObject(i) ?: continue
                    val num = n.optLong("n")
                    val body = n.optString("body").take(1500)
                    show(ctx, num.toInt(), n.optString("title").take(200), body, Wege.link(base, body))
                    if (num > last) last = num
                }
            }
            if (d.has("assist")) store.flags(d)
            // the Spark started over (restart): its numbers begin at 1 again
            val serverLast = d.optLong("last")
            store.lastNote = if (serverLast < store.lastNote) serverLast else last
            val app = d.optJSONObject("app")
            if (app != null) {
                val code = app.optInt("code")
                if (code > BuildConfig.VERSION_CODE && code > store.toldCode) {
                    store.toldCode = code
                    // "Update in der App": a tap starts the update in the app, else the page with the download link
                    if (d.optBoolean("update", false)) show(ctx, 0, "Neue Spark-App", "Version ${app.optString("version").take(20)} ist da. Antippen zum Aktualisieren.", "$base/", MainActivity.ACTION_UPDATE)
                    else show(ctx, 0, "Neue Spark-App", "Version ${app.optString("version").take(20)} ist da. Antippen zum Laden.", "$base/#me=andbox")
                }
            }
        }

        /** At most MAX_ANSWER bytes of the answer. */
        internal fun readSome(s: java.io.InputStream): String {
            val out = java.io.ByteArrayOutputStream()
            val buf = ByteArray(8192)
            while (out.size() < MAX_ANSWER) {
                val n = s.read(buf, 0, minOf(buf.size, MAX_ANSWER - out.size()))
                if (n < 0) break
                out.write(buf, 0, n)
            }
            return out.toString("UTF-8")
        }

        private fun show(ctx: Context, id: Int, title: String, body: String, open: String, action: String = Intent.ACTION_VIEW) {
            val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Hinweise vom Spark", NotificationManager.IMPORTANCE_HIGH))
            val tap = Intent(ctx, MainActivity::class.java).setAction(action).setData(Uri.parse(open))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            val pi = PendingIntent.getActivity(ctx, id, tap, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val n = Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_note)
                .setContentTitle(title.ifEmpty { "Spark" })
                .setContentText(body)
                .setStyle(Notification.BigTextStyle().bigText(body))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build()
            nm.notify(id, n)
        }
    }
}
