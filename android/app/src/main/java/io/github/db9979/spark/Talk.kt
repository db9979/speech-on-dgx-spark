package io.github.db9979.spark

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.TimeZone
import java.util.concurrent.LinkedBlockingQueue
import kotlin.math.sqrt

/**
 * The app's own voice ("Android: Spark als Assistent", admin switch chat.android_assist): records the question
 * itself (16 kHz, with Android's echo canceller), sends it to the own Spark like the page does
 * (POST /api/test/asr, then POST /api/chat with client "android"), plays the Spark's voice (24 kHz PCM) and puts
 * question and answer into the profile's history (PUT /api/profile/convos with "add"). It follows the profile's
 * own settings from /api/profile/settings: "Antworten vorlesen" (speak), "Ins Wort fallen" (barge), "Freihändig"
 * (hands). Talking into an answer only lowers it at first; the answer stops when the Spark heard a question
 * (its echo and stranger rules stay on the Spark: "opened" says how the microphone opened by itself).
 * Typed questions wait when the Spark is away (at most QUEUE_MAX, QUEUE_DAY) and go out once it answers again.
 */
class Talk(private val ctx: Context, private val ui: Ui) {
    enum class State { REST, LISTEN, THINK, SPEAK }

    interface Ui {
        fun state(s: State)
        fun status(text: String)
        fun heard(text: String)
        fun answer(text: String)
        fun face(hint: String)
    }

    private val main = Handler(Looper.getMainLooper())
    @Volatile private var gen = 0
    @Volatile var state = State.REST
        private set
    private val msgs = mutableListOf<JSONObject>()
    private var convo = ""
    private var saved = 0
    private var lastAt = 0L
    @Volatile private var player: Player? = null
    private var prefs: JSONObject? = null

    private fun set(s: State) {
        state = s
        main.post { ui.state(s) }
    }

    private fun say(text: String) = main.post { ui.status(text) }

    private fun pref(key: String, dflt: Boolean): Boolean {
        val p = prefs ?: try {
            Api.call(ctx, "GET", "/api/profile/settings").takeIf { it.ok }?.json()?.optJSONObject("settings")
        } catch (_: Exception) {
            null
        }?.also { prefs = it }
        return p?.optBoolean(key, dflt) ?: dflt
    }

    fun micAllowed() = ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    /** Listens for one question. [opened]: how the microphone opened by itself ("hands"), "" after a tap. */
    fun listen(opened: String = "") {
        if (!micAllowed()) {
            say("Das Mikrofon ist für Spark nicht erlaubt.")
            return
        }
        val my = ++gen
        player?.stop()
        set(State.LISTEN)
        say(if (opened == "hands") "Noch eine Frage? Ich höre zu …" else "Ich höre zu …")
        Thread {
            val pcm = capture(my, false, null)
            if (my != gen) return@Thread
            if (pcm == null) {
                set(State.REST)
                say(if (opened == "hands") "Nichts gehört, Mikrofon aus. Tippen zum Sprechen." else "Nichts gehört.")
                return@Thread
            }
            hear(my, pcm, opened)
        }.start()
    }

    /** Stops listening, thinking and speaking. */
    fun stop() {
        gen++
        player?.stop()
        player = null
        set(State.REST)
    }

    /** A typed question. */
    fun type(text: String) {
        val q = text.trim().take(4000)
        if (q.isEmpty()) return
        val my = ++gen
        player?.stop()
        main.post { ui.heard(q) }
        Thread { ask(my, q, null, typed = true) }.start()
    }

    // ------------------------------------------------------------ recording
    /**
     * Records until the speaker pauses. [barge]: while an answer plays (a stricter start, no time limit while
     * [still] holds; [loud] runs at the first sign of a voice). Null when nobody spoke.
     */
    @SuppressLint("MissingPermission")
    private fun capture(my: Int, barge: Boolean, still: (() -> Boolean)?, loud: (() -> Unit)? = null): ByteArray? {
        val frame = RATE_IN / 50   // 20 ms
        val min = AudioRecord.getMinBufferSize(RATE_IN, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = try {
            AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, RATE_IN, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, maxOf(min, RATE_IN))
        } catch (_: Exception) {
            return null
        }
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            return null
        }
        val aec = if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(rec.audioSessionId) else null
        val ns = if (NoiseSuppressor.isAvailable()) NoiseSuppressor.create(rec.audioSessionId) else null
        aec?.enabled = true
        ns?.enabled = true
        val out = ByteArrayOutputStream()
        val ring = ArrayDeque<ByteArray>()
        val buf = ShortArray(frame)
        var floor = 0.0
        var frames = 0
        var voiced = 0
        var started = false
        var quiet = 0
        try {
            rec.startRecording()
            while (my == gen && (still == null || still())) {
                val n = rec.read(buf, 0, frame)
                if (n <= 0) break
                frames++
                val bytes = toBytes(buf, n)
                val level = rms(buf, n)
                if (!started) {
                    if (frames <= 10) floor = if (frames == 1) level else floor * 0.8 + level * 0.2
                    if (!barge && frames == 10) floor = minOf(floor, 1200.0)   // someone who starts at once is no room noise
                    ring.addLast(bytes)
                    if (ring.size > 25) ring.removeFirst()   // 0.5 s before the voice belongs to the question
                    val start = if (barge) maxOf(floor * 3.5, 1600.0) else maxOf(floor * 3.0, 350.0)
                    voiced = if (frames > 5 && level > start) voiced + 1 else 0
                    if (voiced >= (if (barge) 15 else 3)) {   // 300 ms over an answer, 60 ms otherwise
                        started = true
                        ring.forEach { out.write(it) }
                        loud?.invoke()
                    } else {
                        if (level < start) floor = floor * 0.97 + level * 0.03
                        if (!barge && frames * 20 > NO_VOICE_MS) return null
                    }
                } else {
                    out.write(bytes)
                    quiet = if (level < maxOf(floor * 2.0, 250.0)) quiet + 20 else 0
                    if (quiet >= PAUSE_MS || out.size() > RATE_IN * 2 * MAX_SECONDS) break
                }
            }
        } catch (_: Exception) {
            return null
        } finally {
            try { rec.stop() } catch (_: Exception) {}
            aec?.release()
            ns?.release()
            rec.release()
        }
        return if (started && my == gen) wav(out.toByteArray(), RATE_IN) else null
    }

    /** The recording as text from the Spark; then the question. */
    private fun hear(my: Int, wav: ByteArray, opened: String) {
        set(State.THINK)
        say("Erkenne Sprache …")
        val r = try {
            Api.upload(ctx, "/api/test/asr", "frage.wav", "audio/wav", wav,
                mapOf("language" to "auto") + (if (opened.isNotEmpty()) mapOf("opened" to opened) else emptyMap()))
        } catch (e: Exception) {
            if (my == gen) { set(State.REST); say(why(e)) }
            return
        }
        if (my != gen) return
        if (!r.ok) { set(State.REST); say(fail(r)); return }
        val d = r.json()
        val text = d.optString("text").trim()
        if (text.isEmpty()) {
            set(State.REST)
            val ign = d.optString("ignored")
            say(when {
                ign.contains("foreign") -> "Fremde Stimme überhört, zum Beispiel vom Fernseher."
                ign.contains("own") || ign.contains("pause") -> "Eigene Stimme überhört."
                ign.isNotEmpty() -> "Nichts gehört."
                else -> "Nichts verstanden."
            })
            return
        }
        main.post { ui.heard(text) }
        ask(my, text, d.optJSONObject("speaker")?.optString("token")?.takeIf { it.isNotEmpty() }, typed = false)
    }

    // ------------------------------------------------------------ the question and the answer
    private fun ask(my: Int, text: String, speaker: String?, typed: Boolean) {
        val now = System.currentTimeMillis()
        if (now - lastAt > NEW_AFTER_MS) {   // after a pause a new conversation, like the iPhone app
            msgs.clear()
            saved = 0
            convo = java.lang.Long.toString(now, 36)
        }
        lastAt = now
        val q = JSONObject().put("role", "user").put("content", text)
        msgs.add(q)
        set(State.THINK)
        say("Antwort kommt …")
        main.post { ui.face(""); ui.answer("") }
        val speak = pref("speak", true)
        val body = JSONObject().put("messages", JSONArray(msgs.takeLast(20)))
            .put("tz", TimeZone.getDefault().id).put("client", "android").put("convo", convo)
        if (!speak) body.put("speak", false)
        if (speaker != null) body.put("speaker", speaker)
        val p = if (speak) Player(ctx) else null
        player = p
        var full = ""
        var err = ""
        var mail = false
        var outside = false
        var got = false
        try {
            val conn = Api.open(ctx, "POST", "/api/chat", 300000)
            try {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Accept", "text/event-stream")
                conn.outputStream.use { it.write(body.toString().toByteArray()) }
                val code = conn.responseCode
                if (code !in 200..299) {
                    err = fail(Api.Resp(code, conn.errorStream?.use { NotePoll.readSome(it) } ?: ""))
                } else {
                    got = true
                    conn.inputStream.bufferedReader().useLines { lines ->
                        for (line in lines) {
                            if (my != gen) break
                            if (!line.startsWith("data:")) continue
                            val ev = try { JSONObject(line.substring(5)) } catch (_: Exception) { continue }
                            when (ev.optString("type")) {
                                "text" -> { full += ev.optString("delta"); show(full) }
                                "retract", "truncated" -> { full = full.dropLast(ev.optInt("drop").coerceAtLeast(0)); show(full) }
                                "audio" -> if (p != null) {
                                    try { p.add(Base64.decode(ev.optString("audio"), Base64.DEFAULT)) } catch (_: Exception) {}
                                    if (state != State.SPEAK) { set(State.SPEAK); say("Spricht …"); barge(my, p) }
                                }
                                "mail" -> { mail = true; main.post { ui.face("mail") } }
                                "outside" -> outside = true
                                "search", "docsearch", "historysearch" -> main.post { ui.face("search") }
                                "calendar", "briefing" -> main.post { ui.face("calendar") }
                                "home" -> main.post { ui.face("home") }
                                "memory" -> main.post { ui.face("memory") }
                                // Anrufe per Assistent (rufen.py), after the person's yes: a Spark call opens the app,
                                // whose page shows the call with „Anrufen“; „übers Telefon“ opens the phone app with the
                                // number, the person still taps the green button there
                                "anruf" -> main.post { openApp() }
                                "waehlen" -> ev.optString("number").takeIf { NUMBER.matches(it) }?.let { n -> main.post { dial(n) } }
                                "error" -> if (err.isEmpty()) err = ev.optString("message").take(200)
                            }
                        }
                    }
                }
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            if (typed && !got && e is IOException && queue(ctx, text)) {
                msgs.remove(q)
                if (my == gen) { set(State.REST); say("Keine Verbindung zum Spark. Die Frage geht raus, sobald er wieder antwortet.") }
                return
            }
            err = why(e)
        }
        p?.finish()
        if (my != gen) return
        if (full.isNotBlank()) {
            val a = JSONObject().put("role", "assistant").put("content", full.trim())
            if (mail) a.put("mail", true) else if (outside) a.put("outside", true)
            msgs.add(a)
            save()
        } else {
            msgs.remove(q)
        }
        if (err.isNotEmpty()) { main.post { ui.face("error") }; say(err) }
        // after the voice: hands-free listens again, else rest
        val done = {
            if (my == gen) {
                if (err.isEmpty() && full.isNotBlank() && pref("hands", false)) listen("hands")
                else { set(State.REST); if (err.isEmpty()) say("Tippen zum Sprechen.") }
            }
        }
        if (p != null) p.whenDone { main.post(done) } else main.post(done)
    }

    private fun openApp() {
        val base = Store(ctx).base ?: return
        try {
            ctx.startActivity(Intent(ctx, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse("$base/"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))
        } catch (_: Exception) {}
    }

    private fun dial(number: String) {
        try {
            ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + number.filter { it.isDigit() || it == '+' }))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (_: Exception) {}
    }

    private fun show(text: String) {
        val clean = plain(text)
        main.post { ui.answer(clean) }
    }

    /** "Ins Wort fallen": while the answer plays, a voice lowers it; a question the Spark heard ends it. */
    private fun barge(my: Int, p: Player) {
        if (!pref("barge", true) || !micAllowed()) return
        Thread {
            while (my == gen && p.busy()) {
                val pcm = capture(my, true, { my == gen && p.busy() }) { p.duck(true) } ?: break
                if (my != gen) return@Thread
                val r = try {
                    Api.upload(ctx, "/api/test/asr", "frage.wav", "audio/wav", pcm, mapOf("language" to "auto", "opened" to "barge"))
                } catch (_: Exception) {
                    null
                }
                val text = r?.takeIf { it.ok }?.json()?.optString("text")?.trim().orEmpty()
                if (text.isEmpty() || my != gen) { p.duck(false); continue }   // the Spark's own voice, a click, the TV
                val next = ++gen
                p.stop()
                main.post { ui.heard(text) }
                ask(next, text, r?.json()?.optJSONObject("speaker")?.optString("token")?.takeIf { it.isNotEmpty() }, typed = false)
                return@Thread
            }
        }.start()
    }

    /** New messages into the profile's history (the same list as the panel's Protokoll). */
    private fun save() {
        val add = JSONArray()
        msgs.drop(saved).takeLast(60).forEach { add.put(it) }
        if (add.length() == 0) return
        val title = msgs.firstOrNull { it.optString("role") == "user" }?.optString("content")?.take(60) ?: return
        saved = msgs.size
        val body = JSONObject().put("id", convo).put("title", title).put("add", add)
        Thread { try { Api.json(ctx, "PUT", "/api/profile/convos", body) } catch (_: Exception) {} }.start()
    }

    private fun fail(r: Api.Resp) = when (r.code) {
        401 -> "Nicht angemeldet: die App einmal öffnen und anmelden."
        403 -> r.detail.ifEmpty { "Vom Admin nicht freigegeben." }
        429 -> "Gerade zu viele Fragen. Gleich noch einmal."
        503 -> r.detail.ifEmpty { "Der Spark ist gerade beschäftigt." }
        else -> "Ging nicht (${r.code})."
    }

    private fun why(e: Exception) = when (e) {
        is Api.NoLogin -> e.message ?: ""
        is IOException -> "Der Spark ist gerade nicht erreichbar."
        else -> "Ging nicht."
    }

    /** The Spark's voice: 24 kHz PCM pieces as they come, lowered while someone talks into it. */
    class Player(ctx: Context) {
        private val am = ctx.getSystemService(AudioManager::class.java)
        private val attrs = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
        private val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK).setAudioAttributes(attrs).build()
        private val track = AudioTrack.Builder().setAudioAttributes(attrs)
            .setAudioFormat(AudioFormat.Builder().setSampleRate(RATE_OUT).setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setBufferSizeInBytes(RATE_OUT * 2).setTransferMode(AudioTrack.MODE_STREAM).build()
        private val q = LinkedBlockingQueue<ByteArray>()
        @Volatile private var ended = false
        @Volatile private var stopped = false
        @Volatile private var written = 0L
        private val writer = Thread {
            try {
                while (!stopped) {
                    val b = q.poll(200, java.util.concurrent.TimeUnit.MILLISECONDS) ?: if (ended) break else continue
                    track.write(b, 0, b.size)
                    written += b.size / 2
                }
            } catch (_: Exception) {}
        }

        init {
            am?.requestAudioFocus(focus)
            track.play()
            writer.start()
        }

        fun add(pcm: ByteArray) { if (!stopped) q.add(pcm) }

        fun finish() { ended = true }

        fun busy() = !stopped && (!ended || q.isNotEmpty() || writer.isAlive ||
            (track.playbackHeadPosition.toLong() and 0xffffffffL) < written)

        fun duck(on: Boolean) { try { track.setVolume(if (on) 0.25f else 1f) } catch (_: Exception) {} }

        fun stop() {
            if (stopped) return
            stopped = true
            q.clear()
            try { track.pause(); track.flush(); track.stop() } catch (_: Exception) {}
            track.release()
            am?.abandonAudioFocusRequest(focus)
        }

        /** Runs [then] once the last piece was heard (or the player stopped). */
        fun whenDone(then: () -> Unit) {
            Thread {
                while (busy()) Thread.sleep(100)
                stop()
                then()
            }.start()
        }
    }

    companion object {
        const val RATE_IN = 16000
        const val RATE_OUT = 24000
        const val NO_VOICE_MS = 8000
        const val PAUSE_MS = 900
        const val MAX_SECONDS = 30
        const val NEW_AFTER_MS = 10 * 60 * 1000L
        // a phone number from the Spark for „übers Telefon“ (rufen.NUMBER)
        val NUMBER = Regex("\\+?[0-9][0-9 /()\\-]{2,28}")
        const val QUEUE_MAX = 10
        const val QUEUE_DAY = 24 * 3600 * 1000L
        private const val CHANNEL = "answers"

        fun rms(b: ShortArray, n: Int): Double {
            var e = 0.0
            for (i in 0 until n) e += b[i].toDouble() * b[i]
            return sqrt(e / maxOf(1, n))
        }

        fun toBytes(b: ShortArray, n: Int): ByteArray {
            val bb = ByteBuffer.allocate(n * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (i in 0 until n) bb.putShort(b[i])
            return bb.array()
        }

        /** 16-bit mono PCM as a WAV file. */
        fun wav(pcm: ByteArray, rate: Int): ByteArray {
            val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            h.put("RIFF".toByteArray()).putInt(36 + pcm.size).put("WAVE".toByteArray())
            h.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate * 2).putShort(2).putShort(16)
            h.put("data".toByteArray()).putInt(pcm.size)
            return h.array() + pcm
        }

        /** The answer without Markdown signs (the app's own parts show plain text). */
        fun plain(md: String): String = md
            .replace(Regex("```[\\s\\S]*?```"), "")
            .replace(Regex("(?m)^#{1,6}\\s*"), "")
            .replace(Regex("\\*\\*|__|`"), "")
            .replace(Regex("\\[([^\\]]{1,200})]\\((https?://[^)\\s]{1,500})\\)"), "$1 ($2)")
            .trim()

        // -------------------------------------------------------- questions that wait for the Spark
        /** Keeps a typed question for later; false when the list is full. */
        fun queue(ctx: Context, text: String): Boolean {
            val s = Store(ctx)
            val now = System.currentTimeMillis()
            val old = try { JSONArray(s.queue) } catch (_: Exception) { JSONArray() }
            val keep = JSONArray()
            for (i in 0 until old.length()) old.optJSONObject(i)?.takeIf { now - it.optLong("t") < QUEUE_DAY }?.let { keep.put(it) }
            if (keep.length() >= QUEUE_MAX) return false
            keep.put(JSONObject().put("q", text.take(4000)).put("t", now))
            s.queue = keep.toString()
            return true
        }

        fun waiting(ctx: Context) = try { JSONArray(Store(ctx).queue).length() } catch (_: Exception) { 0 }

        @Volatile private var flushing = false

        /** Sends the waiting questions (not on the main thread); each answer comes as a note and into the history. */
        fun flush(ctx: Context) {
            if (flushing || waiting(ctx) == 0) return
            flushing = true
            try {
                val s = Store(ctx)
                val list = try { JSONArray(s.queue) } catch (_: Exception) { JSONArray() }
                val now = System.currentTimeMillis()
                var i = 0
                while (i < list.length()) {
                    val item = list.optJSONObject(i)
                    if (item == null || now - item.optLong("t") >= QUEUE_DAY) { i++; continue }
                    val q = item.optString("q")
                    val answer = try { quiet(ctx, q) } catch (_: IOException) { break } catch (_: Exception) { null }
                    if (answer != null) note(ctx, q, answer)
                    i++
                }
                val rest = JSONArray()
                for (k in i until list.length()) list.optJSONObject(k)?.let { rest.put(it) }
                s.queue = rest.toString()
            } finally {
                flushing = false
            }
        }

        /** One question without voice; the answer text, or null when the Spark refused it (it is dropped then). */
        private fun quiet(ctx: Context, q: String): String? {
            val id = java.lang.Long.toString(System.currentTimeMillis(), 36)
            val msg = JSONObject().put("role", "user").put("content", q)
            val body = JSONObject().put("messages", JSONArray().put(msg)).put("tz", TimeZone.getDefault().id)
                .put("client", "android").put("speak", false).put("convo", id)
            val conn = Api.open(ctx, "POST", "/api/chat", 300000)
            var full = ""
            try {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Accept", "text/event-stream")
                conn.outputStream.use { it.write(body.toString().toByteArray()) }
                if (conn.responseCode !in 200..299) return null
                conn.inputStream.bufferedReader().useLines { lines ->
                    for (line in lines) {
                        if (!line.startsWith("data:")) continue
                        val ev = try { JSONObject(line.substring(5)) } catch (_: Exception) { continue }
                        when (ev.optString("type")) {
                            "text" -> full += ev.optString("delta")
                            "retract", "truncated" -> full = full.dropLast(ev.optInt("drop").coerceAtLeast(0))
                        }
                    }
                }
            } finally {
                conn.disconnect()
            }
            val a = full.trim().ifEmpty { return null }
            val add = JSONArray().put(msg).put(JSONObject().put("role", "assistant").put("content", a))
            try { Api.json(ctx, "PUT", "/api/profile/convos", JSONObject().put("id", id).put("title", q.take(60)).put("add", add)) } catch (_: Exception) {}
            return plain(a)
        }

        private fun note(ctx: Context, q: String, a: String) {
            val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Antworten auf wartende Fragen", NotificationManager.IMPORTANCE_DEFAULT))
            val base = Store(ctx).base ?: return
            val tap = Intent(ctx, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse("$base/"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            val id = (System.currentTimeMillis() % 100000).toInt() + 200000
            val pi = PendingIntent.getActivity(ctx, id, tap, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val body = "„${q.take(200)}“\n\n${a.take(1500)}"
            nm.notify(id, Notification.Builder(ctx, CHANNEL).setSmallIcon(R.drawable.ic_note)
                .setContentTitle("Antwort vom Spark").setContentText(a.take(200))
                .setStyle(Notification.BigTextStyle().bigText(body)).setContentIntent(pi).setAutoCancel(true).build())
        }
    }
}
