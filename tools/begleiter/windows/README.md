# Spark-Begleiter für Windows

Kleines Programm im Infobereich der Taskleiste (unten rechts, ggf. hinter dem Pfeil ˄) für den
eigenen Spark. Es kann:

| Teil | Was es tut | Tastenkürzel (Standard) |
|---|---|---|
| **Schreibhilfe** | markierten Text in einem beliebigen Programm verbessern und zurück einfügen | **Strg+Alt+S** |
| **Frag Spark** | kleines Fenster: Frage tippen (oder sprechen), Antwort lesen, nachfragen | **Strg+Alt+A** |
| **Diktieren** | sprechen, der erkannte Text landet an der Cursorstelle | **Strg+Alt+D** |
| **Meldungen** | Meldungen des Spark als Windows-Hinweis | – |
| **Zustandspunkt** | Punkt im Symbol: grün = erreichbar, grau = nicht erreichbar, rot = Notaus | – |
| **Mein-Notaus-Knopf** | Menüpunkt „Mein Notaus auslösen …“ (mit Rückfrage) | – |

**Welche Teile an sind, wird im Panel eingestellt** (Ich → Begleiter, je gekoppeltem Gerät) und gilt
nach spätestens einer Abfrage (normalerweise 30 Sekunden). Dort stehen auch die Voreinstellungen der
Schreibhilfe (Art, Sprache, Wunsch, Vorschau) und der Diktier-Sprache sowie „Mit Windows starten“.
Nur die Tastenkürzel werden im Programm selbst eingestellt.

Texte, Fragen und Aufnahmen gehen nur an den eigenen Spark, sonst nirgendwohin. Keine Telemetrie,
kein Protokoll.

## Installieren

1. Unter *Releases* → **begleiter-windows** die passende Datei laden:
   - `SparkBegleiter-x64.exe` für die meisten PCs (Intel/AMD),
   - `SparkBegleiter-arm64.exe` für Windows auf ARM (z. B. Snapdragon).
2. Die .exe an einen festen Ort legen, z. B. `%LOCALAPPDATA%\Spark Begleiter\`, und starten.
   Eine Installation ist nicht nötig, .NET muss nicht installiert sein.
3. Die Datei ist nicht signiert. Windows SmartScreen warnt deshalb beim ersten Start:
   **„Weitere Informationen“ → „Trotzdem ausführen“**.

## Koppeln

1. Im Panel des Spark: **Ich → Begleiter → „Gerät koppeln“**. Es erscheint eine Zeile wie
   `https://speech.example.org#begleiter=ABCD-EFGH` (gilt 10 Minuten, nur einmal).
2. Beim ersten Start öffnet sich „Spark-Begleiter koppeln“ (sonst: Rechtsklick aufs Symbol →
   **Einstellungen …** → **Neu koppeln …**). Die Zeile einfügen, Gerätenamen prüfen, **Koppeln**.
3. Im Panel unter Ich → Begleiter die gewünschten Teile für dieses Gerät einschalten.

Adresse und Schlüssel liegen in `%APPDATA%\Spark Begleiter\config.json`; der Schlüssel ist mit
Windows (DPAPI) verschlüsselt und nur unter dem eigenen Windows-Konto lesbar. `https://` geht immer,
`http://` nur im Heimnetz (z. B. `http://192.168.178.10:31080`) – mit Warnung, weil unverschlüsselt.

Wird das Gerät im Panel entfernt, meldet der Begleiter „Der Spark kennt dieses Gerät nicht mehr.
Neu koppeln.“ und öffnet das Koppeln-Fenster.

## Benutzen

**Menü** (Rechtsklick aufs Symbol): oben der Zustand („Verbunden mit …“, „Spark nicht erreichbar“
oder der Notaus-Text), darunter die eingeschalteten Teile, **Einstellungen …** und **Beenden**.
Linksklick öffnet die Schreibhilfe (oder Frag Spark, wenn die Schreibhilfe aus ist).

**Schreibhilfe:** Text markieren, **Strg+Alt+S**.
- Mit Vorschau (Panel-Einstellung): ein Fenster am Mauszeiger zeigt die verbesserte Fassung mit
  markierten Änderungen (entfernt rot durchgestrichen, neu grün). Art und Wunsch lassen sich ändern,
  **Neu** schickt erneut, **Übernehmen** (Strg+Enter) ersetzt die Markierung, **Kopieren** legt das
  Ergebnis nur in die Zwischenablage, **Esc** schließt.
- Ohne Vorschau: der Text wird mit den Voreinstellungen aus dem Panel verbessert und direkt
  eingefügt (ohne Fenster).

**Frag Spark:** **Strg+Alt+A**, Frage tippen, **Enter** (Umschalt+Enter = neue Zeile). Die Antwort
erscheint als reiner Text; Folgefragen behalten den Zusammenhang. **Kopieren** kopiert die letzte
Antwort. Ist Diktieren an, nimmt **Sprechen** die Frage auf (noch einmal klicken = Stopp).

**Diktieren:** **Strg+Alt+D** startet die Aufnahme (unten rechts erscheint „Aufnahme … (Strg+Alt+D
zum Beenden)“), **Strg+Alt+D** noch einmal beendet sie (oder Klick auf den Hinweis). Der erkannte
Text wird dort eingefügt, wo beim Start der Cursor war. Höchstens 60 Sekunden. Aufgenommen wird nur
in dieser Zeit. Windows muss Desktop-Apps das Mikrofon erlauben (Einstellungen → Datenschutz →
Mikrofon).

**Meldungen** erscheinen als Windows-Hinweis. Beim Start werden ältere Meldungen nicht noch einmal
gezeigt.

**Mein Notaus:** Menü → **Mein Notaus auslösen …** → bestätigen. Danach ist das ganze Profil am
Spark gesperrt, der Punkt wird rot. Aufheben geht nur im Panel im Browser mit der PIN
(Menü → **Panel öffnen (Notaus aufheben) …**).

Hinweise: Die Zwischenablage wird kurz benutzt und danach wiederhergestellt (Text, RTF, HTML,
Bilder, Dateien; seltene Sonderformate gehen dabei verloren); der kurzzeitige Text landet nicht im
Zwischenablage-Verlauf (Win+V). In Programmen, die als Administrator laufen, kann der Begleiter
nicht kopieren/einfügen.

## Tastenkürzel ändern

Rechtsklick aufs Symbol → **Einstellungen …** → in das Feld des Teils klicken und die neue
Kombination drücken. Sie muss Strg oder Alt enthalten. Ist sie schon von einem anderen Programm
belegt, steht das daneben und die alte bleibt. **Standard** stellt Strg+Alt+S / A / D wieder her.
Ausgeschaltete Teile haben kein aktives Tastenkürzel.

In den Einstellungen gibt es außerdem **Panel öffnen**, **Neu koppeln …** und **Entkoppeln …**.

## Entfernen

1. Rechtsklick aufs Symbol → **Einstellungen …** → **Entkoppeln …** (löscht den Schlüssel und
   schaltet „Mit Windows starten“ aus), dann **Beenden**.
2. Im Panel unter Ich → Begleiter das Gerät entfernen.
3. Die .exe löschen und den Ordner `%APPDATA%\Spark Begleiter` löschen.

## Bauen

`dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true`
(bzw. `-r win-arm64`). Das erledigt `.github/workflows/begleiter-windows.yml` bei jeder Änderung
an `tools/begleiter/windows/` und legt die Dateien ins Release `begleiter-windows`.
