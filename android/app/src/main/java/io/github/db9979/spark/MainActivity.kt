package io.github.db9979.spark

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.inputmethod.EditorInfo
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.window.OnBackInvokedDispatcher

/**
 * The whole app: the Spark's page in a WebView (on a phone it looks like the iPhone app, appview.js) and a
 * small native screen for the address. The page signs in like a browser; the app adds the microphone for the
 * page, file upload, the Android back gesture, the assistant button (#talk), text shared from other apps
 * (#ask=…, only into the text field) and notes while closed (NotePoll). Links to other sites open in the
 * browser; the app never loads anything but its own Spark.
 */
class MainActivity : Activity() {
    private lateinit var store: Store
    private lateinit var root: FrameLayout
    private lateinit var web: WebView
    private lateinit var setup: LinearLayout
    private lateinit var address: EditText
    private lateinit var hint: TextView
    private var pendingMic: PermissionRequest? = null
    private var pendingFiles: ValueCallback<Array<Uri>>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        root = FrameLayout(this)
        web = makeWeb()
        setup = makeSetup()
        root.addView(web, FrameLayout.LayoutParams(-1, -1))
        root.addView(setup, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        // Android 15 draws behind the system bars: keep the page clear of them and of the keyboard
        if (Build.VERSION.SDK_INT >= 35) {
            root.setOnApplyWindowInsetsListener { v, insets ->
                val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime() or WindowInsets.Type.displayCutout())
                v.setPadding(b.left, b.top, b.right, b.bottom)
                WindowInsets.CONSUMED
            }
        }
        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT) { goBack() }
        }
        if (savedInstanceState != null && store.base != null) {
            web.restoreState(savedInstanceState)
            showWeb()
        } else {
            open(intent)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        open(intent)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    @Deprecated("Android 12 and older")
    override fun onBackPressed() {
        goBack()
    }

    private fun goBack() {
        when {
            setup.visibility == View.VISIBLE && store.base != null -> showWeb()
            web.canGoBack() -> web.goBack()
            else -> moveTaskToBack(true)
        }
    }

    // ------------------------------------------------------------ what to show for an intent
    private fun open(intent: Intent?) {
        val base = store.base
        if (base == null) {
            showSetup(null)
            return
        }
        when (intent?.action) {
            Intent.ACTION_ASSIST -> load("$base/#talk")
            Intent.ACTION_SEND -> {
                val text = intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty().take(4000)
                load(if (text.isBlank()) "$base/" else "$base/#ask=" + Uri.encode(text))
            }
            // a tapped note: only pages of the own Spark (another app may send anything here)
            Intent.ACTION_VIEW -> {
                val url = intent.dataString
                load(if (url != null && Store.sameOrigin(base, url)) url else "$base/")
            }
            else -> if (web.url == null) load("$base/")
        }
        NotePoll.schedule(this)
        askNotes()
    }

    private fun load(url: String) {
        showWeb()
        web.loadUrl(url)
    }

    // ------------------------------------------------------------ the page
    @SuppressLint("SetJavaScriptEnabled")
    private fun makeWeb(): WebView {
        val w = WebView(this)
        w.settings.javaScriptEnabled = true
        w.settings.domStorageEnabled = true
        w.settings.mediaPlaybackRequiresUserGesture = false
        w.settings.allowFileAccess = false
        w.settings.allowContentAccess = false
        w.settings.userAgentString = w.settings.userAgentString + " SparkAndroid/" + BuildConfig.VERSION_NAME
        CookieManager.getInstance().setAcceptCookie(true)
        w.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                val base = store.base ?: return true
                val url = req.url.toString()
                if (Store.sameOrigin(base, url)) return false
                outside(req.url)   // other sites in the browser, never inside the app
                return true
            }

            override fun onReceivedError(view: WebView, req: WebResourceRequest, err: WebResourceError) {
                if (req.isForMainFrame) showSetup("Der Spark ist nicht erreichbar (${err.description}). Adresse prüfen oder später noch einmal.")
            }
        }
        w.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                val base = store.base
                val mic = request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)
                if (base == null || !mic || !Store.sameOrigin(base, request.origin.toString())) {
                    request.deny()
                    return
                }
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                } else {
                    pendingMic?.deny()
                    pendingMic = request
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
                }
            }

            override fun onShowFileChooser(view: WebView, cb: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                pendingFiles?.onReceiveValue(null)
                pendingFiles = cb
                return try {
                    startActivityForResult(params.createIntent(), REQ_FILES)
                    true
                } catch (_: ActivityNotFoundException) {
                    pendingFiles = null
                    false
                }
            }
        }
        // a new app version (Ich → Android-App) and other files: the browser downloads, Android installs
        w.setDownloadListener { url, _, _, _, _ -> outside(Uri.parse(url)) }
        return w
    }

    private fun outside(uri: Uri) {
        if (uri.scheme != "https" && uri.scheme != "http" && uri.scheme != "mailto" && uri.scheme != "tel") return
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (_: ActivityNotFoundException) {
        }
    }

    @Deprecated("startActivityForResult")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQ_FILES) {
            pendingFiles?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
            pendingFiles = null
        } else {
            super.onActivityResult(requestCode, resultCode, data)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode == REQ_MIC) {
            val ok = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
            pendingMic?.let { if (ok) it.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else it.deny() }
            pendingMic = null
        }
    }

    private fun askNotes() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTES)
        }
    }

    // ------------------------------------------------------------ the address screen
    private fun makeSetup(): LinearLayout {
        val dark = (resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
            android.content.res.Configuration.UI_MODE_NIGHT_YES
        val fg = if (dark) Color.WHITE else Color.BLACK
        val box = LinearLayout(this)
        box.orientation = LinearLayout.VERTICAL
        box.gravity = Gravity.CENTER_VERTICAL
        val pad = (24 * resources.displayMetrics.density).toInt()
        box.setPadding(pad, pad, pad, pad)
        box.setBackgroundColor(if (dark) Color.BLACK else Color.rgb(242, 242, 247))
        val title = TextView(this)
        title.text = "Spark"
        title.textSize = 34f
        title.setTextColor(fg)
        title.typeface = android.graphics.Typeface.DEFAULT_BOLD
        hint = TextView(this)
        hint.textSize = 16f
        hint.setTextColor(if (dark) Color.LTGRAY else Color.DKGRAY)
        address = EditText(this)
        address.hint = "https://speech.example.de"
        address.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        address.imeOptions = EditorInfo.IME_ACTION_GO
        address.setTextColor(fg)
        address.setSingleLine()
        address.setOnEditorActionListener { _, _, _ -> save(); true }
        val go = Button(this)
        go.text = "Verbinden"
        go.setOnClickListener { save() }
        val lp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        lp.topMargin = pad / 2
        box.addView(title, lp)
        box.addView(hint, LinearLayout.LayoutParams(lp))
        box.addView(address, LinearLayout.LayoutParams(lp))
        box.addView(go, LinearLayout.LayoutParams(lp))
        box.visibility = View.GONE
        return box
    }

    private fun showSetup(problem: String?) {
        hint.text = problem ?: "Adresse deines Spark, so wie du ihn im Browser öffnest (mit https und echtem Zertifikat, z. B. über deinen Reverse Proxy). Danach meldest du dich wie im Browser mit Name und PIN an."
        address.setText(store.base ?: "")
        setup.visibility = View.VISIBLE
        web.visibility = View.INVISIBLE
    }

    private fun showWeb() {
        setup.visibility = View.GONE
        web.visibility = View.VISIBLE
    }

    private fun save() {
        val base = Store.cleanBase(address.text.toString())
        if (base == null) {
            hint.text = "Bitte so eingeben: https://name oder https://name:port (ohne Pfad)."
            return
        }
        if (base != store.base) {
            web.clearHistory()
            store.lastNote = 0
        }
        store.base = base
        load("$base/")
        NotePoll.schedule(this)
        askNotes()
    }

    companion object {
        private const val REQ_MIC = 1
        private const val REQ_FILES = 2
        private const val REQ_NOTES = 3
    }
}
