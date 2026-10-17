package io.github.db9979.spark

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.provider.OpenableColumns
import java.io.ByteArrayOutputStream

/**
 * Sharing files to Spark (Teilen → Spark in another app): photos and documents, at most MAX_FILES at once. The
 * person picks what happens, nothing is sent by itself:
 * - a photo "Dazu fragen": made smaller here (1280 px, drawn anew, so no place or camera data goes along) and
 *   attached to the conversation (POST /api/chat/image, needs "Bilder erkennen"); the page shows it (#pic=, android.js)
 *   and the person asks;
 * - "In Meine Dokumente ablegen": a photo through the same upload into the documents (POST /api/profile/wissen/picture),
 *   any other file to POST /api/profile/docs (needs "Dokumente"), then "Dazu fragen" puts a question into the text
 *   field (#ask=, never sent by itself).
 * The Spark checks every right and limit itself; the app only shows its answer.
 */
object Share {
    private const val MAX_FILES = 3
    private const val MAX_READ = 100 * 1024 * 1024   // the Spark's own limit decides; this only keeps the phone safe
    private const val SIDE = 1280

    class File(val uri: Uri, val name: String, val type: String) {
        val picture get() = type.startsWith("image/")
    }

    /** The files of a share (ACTION_SEND or ACTION_SEND_MULTIPLE), at most MAX_FILES. */
    @Suppress("DEPRECATION")
    fun files(a: Activity, i: Intent): List<File> {
        val uris = when (i.action) {
            Intent.ACTION_SEND -> listOfNotNull(i.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))
            Intent.ACTION_SEND_MULTIPLE -> i.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM).orEmpty()
            else -> emptyList()
        }
        return uris.filter { it.scheme == "content" }.take(MAX_FILES).map { u ->
            val type = a.contentResolver.getType(u) ?: i.type ?: "application/octet-stream"
            var name = "datei"
            try {
                a.contentResolver.query(u, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                    if (c.moveToFirst()) name = c.getString(0) ?: name
                }
            } catch (_: Exception) {}
            File(u, name.take(120), type)
        }
    }

    /** Asks the person what to do with the files; [open] loads a page of the own Spark in the app. */
    fun offer(a: Activity, files: List<File>, open: (String) -> Unit) {
        if (files.isEmpty()) return
        val pics = files.all { it.picture }
        val what = if (files.size == 1) "„${files[0].name}“" else "${files.size} Dateien"
        AlertDialog.Builder(a).setTitle("An Spark")
            .setMessage(if (pics) "$what: dazu fragen oder unter „Meine Dokumente“ ablegen?" else "$what unter „Meine Dokumente“ ablegen? Danach kannst du dazu fragen.")
            .setPositiveButton(if (pics) "Dazu fragen" else "Ablegen und fragen") { _, _ -> run(a, files, ask = true, open = open) }
            .setNeutralButton("Nur ablegen") { _, _ -> run(a, files, ask = false, open = open) }
            .setNegativeButton("Abbrechen", null)
            .show()
    }

    private fun run(a: Activity, files: List<File>, ask: Boolean, open: (String) -> Unit) {
        val wait = AlertDialog.Builder(a).setMessage("Lade zum Spark …").setCancelable(false).show()
        Thread {
            val ids = mutableListOf<String>()
            val stored = mutableListOf<String>()
            var problem = ""
            for (f in files) {
                try {
                    if (f.picture) {
                        val id = picture(a, f)
                        if (ask) ids.add(id) else {
                            val r = Api.json(a, "POST", "/api/profile/wissen/picture", org.json.JSONObject().put("id", id))
                            if (r.ok) stored.add(f.name) else problem = reason(r)
                        }
                    } else {
                        val data = a.contentResolver.openInputStream(f.uri)?.use { Api.readAtMost(it, MAX_READ) }
                            ?: throw IllegalStateException("Die Datei ist zu groß.")
                        val r = Api.upload(a, "/api/profile/docs", f.name, f.type, data, timeout = 180000)
                        if (r.ok) stored.add(f.name) else problem = reason(r)
                    }
                } catch (e: Exception) {
                    problem = (e as? Api.NoLogin)?.message ?: (e as? IllegalStateException)?.message ?: "Der Spark ist gerade nicht erreichbar."
                }
            }
            a.runOnUiThread {
                wait.dismiss()
                val base = Store(a).base ?: return@runOnUiThread
                when {
                    ids.isNotEmpty() -> open("$base/#pic=" + ids.joinToString(","))
                    ask && stored.isNotEmpty() -> open("$base/#ask=" + Uri.encode("Fass das Dokument „${stored[0]}“ kurz zusammen."))
                }
                val text = when {
                    problem.isNotEmpty() -> "Nicht alles angekommen: $problem"
                    !ask && stored.isNotEmpty() -> "Unter „Meine Dokumente“ abgelegt. Der Spark liest es gleich."
                    else -> ""
                }
                if (text.isNotEmpty()) {
                    val b = AlertDialog.Builder(a).setTitle("An Spark").setMessage(text).setPositiveButton("OK", null)
                    // a way in the Spark's reason ("Funktionen → Bilder erkennen") opens there (Wege.kt)
                    Wege.find(text)?.let { b.setNeutralButton("Im Panel öffnen") { _, _ -> open(Wege.link(base, text)) } }
                    b.show()
                }
            }
        }.start()
    }

    /** A photo smaller and drawn anew as JPEG, attached to the conversation; its id. */
    private fun picture(a: Activity, f: File): String {
        val bmp = ImageDecoder.decodeBitmap(ImageDecoder.createSource(a.contentResolver, f.uri)) { d, info, _ ->
            val big = maxOf(info.size.width, info.size.height)
            if (big > SIDE) d.setTargetSize(info.size.width * SIDE / big, info.size.height * SIDE / big)
            d.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
        }
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 85, out)
        bmp.recycle()
        val r = Api.call(a, "POST", "/api/chat/image", out.toByteArray(), "image/jpeg", 60000)
        if (!r.ok) throw IllegalStateException(reason(r))
        return r.json().optString("id").ifEmpty { throw IllegalStateException("Der Spark hat das Bild nicht angenommen.") }
    }

    private fun reason(r: Api.Resp) = when (r.code) {
        401 -> "Nicht angemeldet: in der App einmal anmelden."
        403 -> r.detail.ifEmpty { "Vom Admin nicht freigegeben." }
        413 -> "Die Datei ist zu groß für den Spark."
        415 -> "Diese Dateiart nimmt der Spark nicht an."
        429 -> "Gerade zu viele auf einmal. Gleich noch einmal."
        else -> r.detail.ifEmpty { "Ging nicht (${r.code})." }
    }
}
