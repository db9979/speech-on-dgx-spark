package io.github.db9979.spark

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * "Mitteilungen sofort" (android.py, admin switch and the profile's own): one lasting connection to the own Spark
 * instead of a question every 15 minutes. The app asks GET /api/android/wait, which answers as soon as a note is
 * there or after 50 seconds with nothing, and asks again. Android shows a quiet lasting notice for it (a
 * foreground service); no Google service, no key: the same login (the WebView's cookie) as NotePoll.
 * The connection ends when the Spark answers 401/403 or "live": false, and when the app is signed out.
 */
class LiveConn : Service() {
    @Volatile private var run = true
    private var worker: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            foreground()
        } catch (_: Exception) {   // Android does not allow it right now (started from the background)
            stopSelf()
            return START_NOT_STICKY
        }
        if (worker?.isAlive != true) {
            run = true
            running = true
            worker = Thread { loop() }.also { it.start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        run = false
        running = false
        worker?.interrupt()
        super.onDestroy()
    }

    private fun foreground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm?.createNotificationChannel(NotificationChannel(CHANNEL, "Verbindung zum Spark", NotificationManager.IMPORTANCE_MIN))
        val tap = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val n = Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_note)
            .setContentTitle("Mit dem Spark verbunden")
            .setContentText("Mitteilungen kommen sofort.")
            .setContentIntent(tap)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(ID, n)
        }
    }

    private fun loop() {
        var pause = FIRST_PAUSE
        while (run) {
            val r = try {
                once()
            } catch (_: InterruptedException) {
                return
            } catch (_: Exception) {
                null
            }
            try {
                when (r) {
                    true -> {          // answered: ask again (a short breath so nothing can spin)
                        pause = FIRST_PAUSE
                        Thread.sleep(1000)
                    }
                    false -> {         // switched off or signed out: back to the question every 15 minutes
                        stopSelf()
                        return
                    }
                    null -> {          // the Spark or the network is away: wait longer each time, at most 5 minutes
                        Thread.sleep(pause)
                        pause = minOf(pause * 2, MAX_PAUSE)
                    }
                }
            } catch (_: InterruptedException) {
                return
            }
        }
    }

    /** One question: true to ask again, false to end the connection, null to try again later. */
    private fun once(): Boolean? {
        val store = Store(this)
        val base = store.base ?: return false
        val c = NotePoll.cookie(base) ?: return false
        val conn = URL("$base/api/android/wait?after=${store.lastNote}").openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 75000   // the Spark answers after 50 seconds at the latest
        conn.instanceFollowRedirects = false
        conn.setRequestProperty("Cookie", c)
        conn.setRequestProperty("User-Agent", "SparkAndroid/${BuildConfig.VERSION_NAME}")
        try {
            val code = conn.responseCode
            if (code == 401 || code == 403) return false
            if (code != 200) return null
            val d = JSONObject(conn.inputStream.use { s -> NotePoll.readSome(s) })
            NotePoll.handle(this, store, base, d)
            return d.optBoolean("live", false)
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private const val CHANNEL = "live"
        private const val ID = 7001
        private const val FIRST_PAUSE = 5_000L
        private const val MAX_PAUSE = 300_000L

        /** True while the connection runs in this process (NotePoll then does not ask itself). */
        @Volatile var running = false

        fun start(ctx: Context) {
            try {
                ctx.startForegroundService(Intent(ctx, LiveConn::class.java))
            } catch (_: Exception) {   // not allowed from the background: the next time the app is opened
            }
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, LiveConn::class.java))
        }

        /** From the open app: ask the Spark once and start or end the connection accordingly. */
        fun check(ctx: Context) {
            val app = ctx.applicationContext
            Thread {
                val live = try {
                    NotePoll.poll(app)
                } catch (_: Exception) {
                    null
                }
                when (live) {
                    true -> if (!running) start(app)
                    false -> stop(app)
                    null -> {}
                }
            }.start()
        }
    }
}
