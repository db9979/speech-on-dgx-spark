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

    /** The app version whose update strip the person closed (it comes back with the next version). */
    var skipCode: Int
        get() = prefs.getInt("skip_code", 0)
        set(v) = prefs.edit().putInt("skip_code", v).apply()

    /** Akku: how long the Spark holds one question of "Mitteilungen sofort" (LiveConn), and since when a proxy
     *  forced the short hold (after a day the app tries the long one again). */
    var liveHold: Int
        get() = prefs.getInt("live_hold", 0)
        set(v) = prefs.edit().putInt("live_hold", v).apply()

    var liveShortSince: Long
        get() = prefs.getLong("live_short_since", 0)
        set(v) = prefs.edit().putLong("live_short_since", v).apply()

    /** What the Spark released for this profile's app (from /api/profile/android and every note answer): the
     *  assistant (TalkActivity, widget, tile, shortcuts) and the lock for admins. The Spark checks again itself. */
    var assist: Boolean
        get() = prefs.getBoolean("assist", false)
        set(v) = prefs.edit().putBoolean("assist", v).apply()

    var lock: Boolean
        get() = prefs.getBoolean("lock", false)
        set(v) = prefs.edit().putBoolean("lock", v).apply()

    /** The login in the app has admin rights (a profile with a role, or the panel password). */
    var admin: Boolean
        get() = prefs.getBoolean("admin", false)
        set(v) = prefs.edit().putBoolean("admin", v).apply()

    /** When the app went to the background unlocked (the lock asks again after Lock.AFTER). */
    var leftAt: Long
        get() = prefs.getLong("left_at", 0)
        set(v) = prefs.edit().putLong("left_at", v).apply()

    /** Typed questions that wait for the Spark (Talk.queue): a JSON list of {"q", "t"}, at most Talk.QUEUE_MAX. */
    var queue: String
        get() = prefs.getString("queue", "[]") ?: "[]"
        set(v) = prefs.edit().putString("queue", v).apply()

    /** Takes the flags of an answer of the Spark (keys missing in an older Spark: off). */
    fun flags(d: org.json.JSONObject) {
        assist = d.optBoolean("assist", false)
        lock = d.optBoolean("lock", false)
        admin = d.optBoolean("admin", false)
    }

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
