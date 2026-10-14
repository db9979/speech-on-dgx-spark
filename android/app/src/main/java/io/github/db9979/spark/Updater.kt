package io.github.db9979.spark

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.widget.Toast
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * "Update in der App" (admin switch chat.android_update): the app asks its own Spark which version it keeps
 * (GET /api/profile/android, never GitHub), loads it from GET /api/android/apk with the page's sign-in into its
 * cache and checks it before Android sees it: size and SHA-256 as the Spark said, the package name, a higher
 * version code and the same signing certificate as the installed app. Then Android's package installer takes
 * it; Android checks the signature against the installed app once more and asks the person ("Aktualisieren").
 * Anything that does not fit deletes the file and installs nothing.
 */
object Updater {
    private const val MAX_APK = 40L * 1024 * 1024
    private const val CHANNEL = "update"
    private val SHA = Regex("[0-9a-f]{64}")
    private val VERSION = Regex("\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}")

    class Offer(val version: String, val code: Int, val size: Long, val sha: String)

    /** What the Spark said: the version it keeps (null: none) and whether this profile may update in the app. */
    class Answer(val offer: Offer?, val allowed: Boolean) {
        val newer get() = allowed && offer != null && offer.code > BuildConfig.VERSION_CODE
    }

    class Fail(msg: String) : Exception(msg)

    @Volatile
    var busy = false

    private fun open(base: String, path: String): HttpURLConnection {
        val c = NotePoll.cookie(base) ?: throw Fail("Nicht angemeldet: in der App einmal anmelden.")
        val conn = URL("$base$path").openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 30000
        conn.instanceFollowRedirects = false   // only the own Spark, never somewhere else
        conn.setRequestProperty("Cookie", c)
        conn.setRequestProperty("User-Agent", "SparkAndroid/${BuildConfig.VERSION_NAME}")
        return conn
    }

    /** Asks the own Spark (not on the main thread). Null when it does not answer or the app is off. */
    fun ask(ctx: Context): Answer? {
        val base = Store(ctx).base ?: return null
        val conn = try {
            open(base, "/api/profile/android")
        } catch (_: Fail) {
            return null
        }
        try {
            if (conn.responseCode != 200) return null
            val d = JSONObject(conn.inputStream.use { NotePoll.readSome(it) })
            val a = d.optJSONObject("app")
            val offer = a?.let {
                val v = it.optString("version")
                val sha = it.optString("sha256")
                val size = it.optLong("size")
                val code = it.optInt("code")
                if (VERSION.matches(v) && SHA.matches(sha) && size in 1..MAX_APK && code > 0) Offer(v, code, size, sha) else null
            }
            return Answer(offer, d.optBoolean("update", false) && d.optBoolean("on", false))
        } catch (_: Exception) {
            return null
        } finally {
            conn.disconnect()
        }
    }

    /** Loads the APK into the cache, at most the size the Spark named, and checks its SHA-256 on the way. */
    fun fetch(ctx: Context, offer: Offer, progress: (Long) -> Unit): File {
        val base = Store(ctx).base ?: throw Fail("Keine Spark-Adresse.")
        val f = File(ctx.cacheDir, "update.apk")
        f.delete()
        val conn = open(base, "/api/android/apk")
        try {
            when (conn.responseCode) {
                200 -> {}
                403 -> throw Fail("Update in der App hat der Admin nicht freigegeben.")
                409 -> throw Fail("Der Spark hat die App noch nicht geholt.")
                else -> throw Fail("Der Spark gibt die App gerade nicht heraus (${conn.responseCode}).")
            }
            val md = MessageDigest.getInstance("SHA-256")
            var n = 0L
            conn.inputStream.use { inp ->
                FileOutputStream(f).use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val r = inp.read(buf)
                        if (r < 0) break
                        n += r
                        if (n > offer.size) throw Fail("Die Datei ist größer als gemeldet.")
                        md.update(buf, 0, r)
                        out.write(buf, 0, r)
                        progress(n)
                    }
                }
            }
            if (n != offer.size) throw Fail("Die Datei ist unvollständig.")
            if (hex(md.digest()) != offer.sha) throw Fail("Die Prüfsumme passt nicht.")
            return f
        } catch (e: Exception) {
            f.delete()
            throw e
        } finally {
            conn.disconnect()
        }
    }

    /** The own checks before Android sees the file: package name, version code, signing certificate. */
    fun check(ctx: Context, f: File, offer: Offer) {
        val pm = ctx.packageManager
        val flags = PackageManager.GET_SIGNING_CERTIFICATES
        val info = pm.getPackageArchiveInfo(f.path, flags) ?: throw Fail("Die Datei ist keine gültige App.")
        if (info.packageName != ctx.packageName) throw Fail("Die Datei ist nicht die Spark-App.")
        if (info.longVersionCode <= BuildConfig.VERSION_CODE.toLong() || info.longVersionCode != offer.code.toLong()) {
            throw Fail("Die Versionsnummer passt nicht.")
        }
        val own = signers(pm.getPackageInfo(ctx.packageName, flags))
        val theirs = signers(info)
        // the new file must carry the installed app's certificate (a rotated key lists the old one in its history);
        // when Android cannot read it from the file here, its installer still checks it and refuses
        if (own.isNotEmpty() && theirs.isNotEmpty() && !theirs.containsAll(own)) throw Fail("Der Signierschlüssel passt nicht.")
    }

    private fun signers(p: PackageInfo): Set<String> {
        val s = p.signingInfo ?: return emptySet()
        val certs = (if (s.hasMultipleSigners()) s.apkContentsSigners else s.signingCertificateHistory) ?: return emptySet()
        val md = MessageDigest.getInstance("SHA-256")
        return certs.map { hex(md.digest(it.toByteArray())) }.toSet()
    }

    /** Hands the checked file to Android's package installer; Android asks the person and checks the signature. */
    fun install(ctx: Context, f: File) {
        val pi = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(ctx.packageName)
        params.setSize(f.length())
        val id = pi.createSession(params)
        try {
            pi.openSession(id).use { s ->
                s.openWrite("spark.apk", 0, f.length()).use { out ->
                    f.inputStream().use { it.copyTo(out) }
                    s.fsync(out)
                }
                val done = Intent(ctx, InstallDone::class.java).setPackage(ctx.packageName)
                // the installer fills in its status: the intent must be mutable (explicit, only to our own receiver)
                val mut = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
                val pend = PendingIntent.getBroadcast(ctx, id, done, PendingIntent.FLAG_UPDATE_CURRENT or mut)
                s.commit(pend.intentSender)
            }
        } catch (e: Exception) {
            try {
                pi.abandonSession(id)
            } catch (_: Exception) {
            }
            throw e
        } finally {
            f.delete()
        }
    }

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }

    internal fun note(ctx: Context, title: String, body: String) {
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "App-Update", NotificationManager.IMPORTANCE_DEFAULT))
        val tap = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val pi = PendingIntent.getActivity(ctx, 7, tap, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        nm.notify(7, Notification.Builder(ctx, CHANNEL).setSmallIcon(R.drawable.ic_note)
            .setContentTitle(title).setContentText(body).setContentIntent(pi).setAutoCancel(true).build())
    }
}

/** The installer's answer: show Android's own question, or say why nothing was installed. */
class InstallDone : BroadcastReceiver() {
    override fun onReceive(ctx: Context, i: Intent) {
        Updater.busy = false
        when (i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val ask: Intent? = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                else @Suppress("DEPRECATION") i.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                Updater.busy = ask != null
                ask?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                try {
                    if (ask != null) ctx.startActivity(ask)
                } catch (_: Exception) {
                    Updater.busy = false
                }
            }
            PackageInstaller.STATUS_SUCCESS -> {}   // Android replaces the app; Replaced tells the person
            PackageInstaller.STATUS_FAILURE_ABORTED -> {}   // the person tapped "Abbrechen"
            else -> Toast.makeText(ctx, "Update nicht installiert: Android hat es abgelehnt (anderer Signierschlüssel?).", Toast.LENGTH_LONG).show()
        }
    }
}

/** After the app was replaced: a note to open it again (Android does not start it by itself). */
class Replaced : BroadcastReceiver() {
    override fun onReceive(ctx: Context, i: Intent) {
        if (i.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        Updater.note(ctx, "Spark ist aktualisiert", "Version ${BuildConfig.VERSION_NAME}. Antippen zum Öffnen.")
    }
}
