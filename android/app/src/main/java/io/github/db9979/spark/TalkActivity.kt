package io.github.db9979.spark

import android.Manifest
import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * "Android: Spark als Assistent" (admin switch chat.android_assist): the Spark as a sheet over whatever app is open.
 * It comes from the assistant button (long press on power or home, once Spark is the phone's digital assistant app),
 * the tile "Spark zuhören", the widget and the shortcuts on the app icon. On the lock screen the phone is unlocked
 * first: the Spark answers with the profile's own data, so nobody else may ask. Released only by the admin: without
 * it the button opens the app with its page as before (#talk). The voice itself is Talk.
 */
class TalkActivity : Activity(), Talk.Ui {
    private lateinit var store: Store
    private lateinit var talk: Talk
    private lateinit var face: FaceView
    private lateinit var status: TextView
    private lateinit var heard: TextView
    private lateinit var answer: TextView
    private lateinit var input: EditText
    private lateinit var mic: Button
    private var started = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        if (store.base == null) {
            app(null)
            return
        }
        talk = Talk(this, this)
        setContentView(build())
        if (Build.VERSION.SDK_INT >= 35) {
            window.decorView.setOnApplyWindowInsetsListener { v, insets ->
                val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
                v.setPadding(b.left, b.top, b.right, b.bottom)
                WindowInsets.CONSUMED
            }
        }
        setShowWhenLocked(true)
        val km = getSystemService(KeyguardManager::class.java)
        if (km != null && km.isKeyguardLocked) {
            status.text = "Erst das Handy entsperren."
            km.requestDismissKeyguard(this, object : KeyguardManager.KeyguardDismissCallback() {
                override fun onDismissSucceeded() = check()
                override fun onDismissCancelled() = finish()
                override fun onDismissError() = finish()
            })
        } else {
            check()
        }
    }

    /** The admin's release (asked fresh when the app does not know it yet), then the microphone, then listen. */
    private fun check() {
        if (store.assist) return begin()
        status.text = "Frage den Spark …"
        Thread {
            try { Api.call(this, "GET", "/api/profile/android").takeIf { it.ok }?.let { store.flags(it.json()) } } catch (_: Exception) {}
            runOnUiThread { if (store.assist) begin() else app(Intent.ACTION_ASSIST) }
        }.start()
    }

    private fun begin() {
        if (isFinishing) return
        started = true
        Thread { Talk.flush(this) }.start()   // questions that waited for the Spark go out now
        val wait = Talk.waiting(this)
        if (wait > 0) heard.text = if (wait == 1) "1 Frage wartet auf den Spark." else "$wait Fragen warten auf den Spark."
        if (intent?.getBooleanExtra(EXTRA_TYPE, false) == true) {
            status.text = "Frage schreiben"
            input.requestFocus()
            input.postDelayed({ getSystemService(InputMethodManager::class.java)?.showSoftInput(input, 0) }, 200)
        } else if (!talk.micAllowed()) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
        } else {
            talk.listen()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode != REQ_MIC) return
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) talk.listen()
        else status.text = "Ohne Mikrofon geht nur Schreiben."
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (started && intent.getBooleanExtra(EXTRA_TYPE, false)) input.requestFocus()
        else if (started && talk.state == Talk.State.REST) talk.listen()
    }

    override fun onStop() {
        super.onStop()
        if (!started) return   // the unlock screen covers the sheet for a moment
        talk.stop()
        if (!isChangingConfigurations) finish()   // the sheet belongs to the moment it was opened for
    }

    /** The whole app instead of the sheet ([action]: ACTION_ASSIST opens its page listening, as before). */
    private fun app(action: String?) {
        startActivity(Intent(this, MainActivity::class.java).setAction(action ?: Intent.ACTION_MAIN)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }

    // ------------------------------------------------------------ Talk.Ui
    override fun state(s: Talk.State) {
        face.state = s
        mic.text = if (s == Talk.State.REST) "🎤 Sprechen" else "■ Stopp"
    }

    override fun status(text: String) { status.text = text }

    override fun heard(text: String) { heard.text = "„$text“" }

    override fun answer(text: String) { answer.text = text; answer.visibility = if (text.isEmpty()) View.GONE else View.VISIBLE }

    override fun face(hint: String) { face.hint = hint }

    // ------------------------------------------------------------ the sheet
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()

    private fun build(): View {
        val dark = (resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
            android.content.res.Configuration.UI_MODE_NIGHT_YES
        val fg = if (dark) Color.WHITE else Color.rgb(29, 35, 48)
        val soft = if (dark) Color.LTGRAY else Color.rgb(85, 85, 102)
        val root = FrameLayout(this)
        root.setBackgroundColor(Color.argb(110, 0, 0, 0))
        root.setOnClickListener { finish() }
        val sheet = LinearLayout(this)
        sheet.orientation = LinearLayout.VERTICAL
        sheet.gravity = Gravity.CENTER_HORIZONTAL
        sheet.isClickable = true   // taps on the sheet do not close it
        sheet.setPadding(dp(18), dp(16), dp(18), dp(18))
        sheet.background = GradientDrawable().apply {
            setColor(if (dark) Color.rgb(28, 30, 36) else Color.WHITE)
            cornerRadii = FloatArray(8) { i -> if (i < 4) dp(24).toFloat() else 0f }
        }
        face = FaceView(this)
        face.setOnClickListener { toggle() }
        face.contentDescription = "Spark"
        sheet.addView(face, LinearLayout.LayoutParams(dp(96), dp(96)))
        status = TextView(this).apply { textSize = 17f; setTextColor(fg); typeface = Typeface.DEFAULT_BOLD; gravity = Gravity.CENTER }
        heard = TextView(this).apply { textSize = 14f; setTextColor(soft); gravity = Gravity.CENTER }
        answer = TextView(this).apply { textSize = 16f; setTextColor(fg); setTextIsSelectable(true); visibility = View.GONE }
        val scroll = object : ScrollView(this) {
            override fun onMeasure(w: Int, h: Int) =   // at most 40 % of the screen, the rest stays visible
                super.onMeasure(w, View.MeasureSpec.makeMeasureSpec(resources.displayMetrics.heightPixels * 2 / 5, View.MeasureSpec.AT_MOST))
        }
        scroll.addView(answer)
        val lp = { top: Int -> LinearLayout.LayoutParams(-1, -2).also { it.topMargin = dp(top) } }
        sheet.addView(status, lp(8))
        sheet.addView(heard, lp(4))
        sheet.addView(scroll, lp(10))
        val row = LinearLayout(this)
        row.gravity = Gravity.BOTTOM   // the arrow stays at the last line while the field grows
        input = EditText(this).apply {
            hint = "Frage schreiben"
            // a long question wraps and grows up to 5 lines, then scrolls; the key stays "Senden" (plan eingabefelder 6a)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            setHorizontallyScrolling(false)
            minLines = 1
            maxLines = 5
            setRawInputType(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
            imeOptions = EditorInfo.IME_ACTION_SEND
            setTextColor(fg)
            setOnEditorActionListener { _, _, _ -> send(); true }
        }
        val go = Button(this).apply { text = "➤"; contentDescription = "Senden"; setOnClickListener { send() } }
        row.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(go, LinearLayout.LayoutParams(dp(56), -2))
        sheet.addView(row, lp(10))
        val buttons = LinearLayout(this)
        mic = Button(this).apply { text = "🎤 Sprechen"; isAllCaps = false; setOnClickListener { toggle() } }
        val whole = Button(this).apply { text = "⤢ Ganze App"; isAllCaps = false; setOnClickListener { app(null) } }
        buttons.addView(mic, LinearLayout.LayoutParams(0, -2, 1f))
        buttons.addView(whole, LinearLayout.LayoutParams(0, -2, 1f))
        sheet.addView(buttons, lp(6))
        root.addView(sheet, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        return root
    }

    private fun toggle() {
        if (!started) return
        if (talk.state == Talk.State.REST) {
            if (talk.micAllowed()) talk.listen() else requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
        } else {
            talk.stop()
            status.text = "Angehalten."
        }
    }

    private fun send() {
        if (!started) return
        val q = input.text.toString()
        if (q.isBlank()) return
        input.setText("")
        talk.type(q)
    }

    companion object {
        private const val REQ_MIC = 1
        const val EXTRA_TYPE = "type"

        /** The sheet from a tile, the widget or a shortcut; [type]: with the keyboard instead of listening. */
        fun intent(ctx: Context, type: Boolean = false): Intent =
            Intent(ctx, TalkActivity::class.java).putExtra(EXTRA_TYPE, type)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
    }
}
