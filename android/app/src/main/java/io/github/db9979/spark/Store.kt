package io.github.db9979.spark

import android.content.Context
import android.net.Uri

/** What the app keeps: the Spark's address and the last note it showed. Never a password or key. */
class Store(ctx: Context) {
    private val prefs = ctx.getSharedPreferences("spark", Context.MODE_PRIVATE)

    var base: String?
        get() = prefs.getString("base", null)
        set(v) = prefs.edit().putString("base", v).apply()

    var lastNote: Long
        get() = prefs.getLong("last_note", 0)
        set(v) = prefs.edit().putLong("last_note", v).apply()

    /** The app version a "new version" note was shown for (once per version). */
    var toldCode: Int
        get() = prefs.getInt("told_code", 0)
        set(v) = prefs.edit().putInt("told_code", v).apply()

    companion object {
        private val BASE = Regex("https://[A-Za-z0-9.\\-]+(:\\d{1,5})?")

        /** "https://name" or "https://name:port", nothing else: the page needs https for the microphone. */
        fun cleanBase(input: String): String? {
            var s = input.trim().trimEnd('/')
            if (!s.contains("://")) s = "https://$s"
            return if (BASE.matches(s)) s.lowercase() else null
        }

        /** True when [url] is on the Spark itself (same scheme, host and port). */
        fun sameOrigin(base: String, url: String): Boolean {
            val a = Uri.parse(base)
            val b = Uri.parse(url)
            return a.scheme == b.scheme && a.host.equals(b.host, ignoreCase = true) && port(a) == port(b)
        }

        private fun port(u: Uri) = if (u.port == -1) 443 else u.port
    }
}
