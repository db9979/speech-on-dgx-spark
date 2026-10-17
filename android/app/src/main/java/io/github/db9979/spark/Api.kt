package io.github.db9979.spark

import android.content.Context
import android.webkit.CookieManager
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * Requests of the app's own parts (assistant, sharing, widget, tiles) to the own Spark with the page's login: the
 * same cookie the WebView holds, never a key of the app's own. Only the Spark's address, no redirects (nothing
 * else ever gets the cookie). Never on the main thread (the cookie belongs to the main thread, NotePoll.cookie).
 */
object Api {
    class Resp(val code: Int, val text: String) {
        fun json(): JSONObject = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
        val ok get() = code in 200..299
        /** The Spark's reason in {"detail": "…"} (fixed words), else "". */
        val detail get() = json().optString("detail").take(200)
    }

    /** No address or not signed in: nothing was asked. */
    class NoLogin : Exception("Nicht angemeldet: die App einmal öffnen und anmelden.")

    fun open(ctx: Context, method: String, path: String, timeout: Int = 15000): HttpURLConnection {
        val base = Store(ctx).base ?: throw NoLogin()
        val c = NotePoll.cookie(base) ?: throw NoLogin()
        val conn = URL(base + path).openConnection() as HttpURLConnection
        conn.connectTimeout = 10000
        conn.readTimeout = timeout
        conn.instanceFollowRedirects = false
        conn.requestMethod = method
        conn.setRequestProperty("Cookie", c)
        conn.setRequestProperty("User-Agent", "SparkAndroid/${BuildConfig.VERSION_NAME}")
        return conn
    }

    /** One request with an optional body; the answer (at most NotePoll's size) as text. */
    fun call(ctx: Context, method: String, path: String, body: ByteArray? = null,
             type: String = "application/json", timeout: Int = 15000): Resp {
        val conn = open(ctx, method, path, timeout)
        try {
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", type)
                conn.setFixedLengthStreamingMode(body.size)
                conn.outputStream.use { it.write(body) }
            }
            val code = conn.responseCode
            // Mein Notaus ends every login of the profile and hands this one a fresh cookie: give it to the page
            val base = Store(ctx).base
            if (base != null) conn.headerFields["Set-Cookie"]?.forEach { v ->
                Handler(Looper.getMainLooper()).post { CookieManager.getInstance().setCookie(base, v) }
            }
            val stream = if (code < 400) conn.inputStream else conn.errorStream
            return Resp(code, stream?.use { NotePoll.readSome(it) } ?: "")
        } finally {
            conn.disconnect()
        }
    }

    fun json(ctx: Context, method: String, path: String, body: JSONObject? = null, timeout: Int = 15000) =
        call(ctx, method, path, body?.toString()?.toByteArray(), timeout = timeout)

    /** A file as multipart/form-data (field "file") plus plain text fields. */
    fun upload(ctx: Context, path: String, name: String, type: String, data: ByteArray,
               fields: Map<String, String> = emptyMap(), timeout: Int = 60000): Resp {
        val b = "spark-" + System.nanoTime()
        val out = ByteArrayOutputStream()
        for ((k, v) in fields) out.write("--$b\r\nContent-Disposition: form-data; name=\"$k\"\r\n\r\n$v\r\n".toByteArray())
        val safe = name.replace(Regex("[\\r\\n\"\\\\]"), "").take(120).ifEmpty { "datei" }
        out.write("--$b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"$safe\"\r\nContent-Type: $type\r\n\r\n".toByteArray())
        out.write(data)
        out.write("\r\n--$b--\r\n".toByteArray())
        return call(ctx, "POST", path, out.toByteArray(), "multipart/form-data; boundary=$b", timeout)
    }

    /** At most [limit] bytes of a stream; null when it is longer. */
    fun readAtMost(s: InputStream, limit: Int): ByteArray? {
        val out = ByteArrayOutputStream()
        val buf = ByteArray(16384)
        while (true) {
            val n = s.read(buf)
            if (n < 0) return out.toByteArray()
            out.write(buf, 0, n)
            if (out.size() > limit) return null
        }
    }
}
