package io.github.db9979.spark

import android.net.Uri

/**
 * Ways into the panel in texts ("Aufheben unter Ich → Sicherheit"): tapping opens `<Spark>/#weg=<way>`, the panel
 * jumps there itself (way.js). Same rule as wege.py on the Spark. Only navigation inside the own panel.
 */
object Wege {
    private const val ROOTS = "Einstellungen|Funktionen|Zustand|Personen und Geräte|Ich|Settings|Features|Status|People and devices|Me|Kalender|Calendar|E-Mail|E-mail|Listen|Lists|Offen|Open|Kontakte|Contacts|Wissensbuch|Knowledge book|Finden|Find|Mappen|Collections|Dungeon-Master|Dungeon Master|Fernzugang|Remote access"
    private val WAY = Regex("(?<![\\w-])(?<!Mein )(?<!My )(?<!→ )(?:$ROOTS)\\s*→[^\\n.;:()!?]{1,160}")

    /** The first way in a text, or null. */
    fun find(text: String): String? =
        WAY.find(text.take(6000))?.value?.trim(' ', ',', '–', '-')?.take(200)?.ifEmpty { null }

    /** The panel page for the first way in a text, else the given fallback. */
    fun link(base: String, text: String, fallback: String = "$base/"): String =
        find(text)?.let { "$base/#weg=" + Uri.encode(it) } ?: fallback
}
