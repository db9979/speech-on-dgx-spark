# Spark-Begleiter für Windows

Kleines Programm im Infobereich der Taskleiste (unten rechts, ggf. hinter dem Pfeil ˄) für den
eigenen Spark. Es kann:

| Teil | Was es tut | Tastenkürzel (Standard) |
|---|---|---|
| **Schreibhilfe** | markierten Text in einem beliebigen Programm verbessern und zurück einfügen | **Strg+Alt+S** |
| **Frag Spark** | kleines Fenster: Frage tippen (oder sprechen), Antwort lesen, nachfragen | **Strg+Alt+A** |
| **Diktieren** | sprechen, der erkannte Text landet an der Cursorstelle | **Strg+Alt+D** |
| **Meldungen** | Meldungen des Spark als Windows-Hinweis | – |
| **Zustandspunkt** | Punkt im Symbol: grün = erreichbar, grau = nicht erreichbar, rot = Notaus (blau-violett = Update da, siehe unten) | – |
| **Mein-Notaus-Knopf** | Menüpunkt „Mein Notaus auslösen …“ (mit Rückfrage) | – |

**Welche Teile an sind, wird im Panel eingestellt** (Ich → Begleiter, je gekoppeltem Gerät) und gilt
nach spätestens einer Abfrage (normalerweise 30 Sekunden). Dort stehen auch die Voreinstellungen der
Schreibhilfe (Art, Sprache, Wunsch, Vorschau) und der Diktier-Sprache sowie „Mit Windows starten“.
Nur die Tastenkürzel werden im Programm selbst eingestellt.

Texte, Fragen und Aufnahmen gehen nur an den eigenen Spark, sonst nirgendwohin. Keine Telemetrie,
kein Protokoll. Auch Updates kommen nur vom eigenen Spark.

## So sieht er aus

Der Begleiter trägt die Farben und das Gesicht des Panels („Spark-Gesicht“):

- **Symbol** im Infobereich: das Spark-Gesicht mit einem kleinen Punkt unten rechts – grün
  (verbunden), grau (nicht erreichbar), rot (Notaus), in der Akzentfarbe, wenn eine neue Version
  bereitsteht. Das Symbol wird für die Bildschirmauflösung der Taskleiste gezeichnet und bleibt
  auch bei 150 % oder 200 % scharf.
- **Linksklick aufs Symbol** öffnet ein kleines Fenster direkt an der Taskleiste: oben das Gesicht
  mit Profil, Gerät und Zustand, darunter (falls vorhanden) der Update-Hinweis, die eingeschalteten
  Teile mit ihren Tastenkürzeln, „Mein Notaus …“ in Rot, unten **Einstellungen**, **Panel öffnen**
  und **☕ Spark unterstützen**. Es schließt sich, sobald man woanders hinklickt, oder mit **Esc**;
  mit Tab bzw. ↑/↓ und Enter geht alles auch per Tastatur.
- **Rechtsklick aufs Symbol** zeigt weiter das schlichte Menü (Zustand, Teile, Einstellungen, Beenden).
- Die Fenster für **Text verbessern**, **Frag Spark** und die **Einstellungen** haben oben den
  Farbverlauf des Panels; Frag Spark zeigt Fragen und Antworten als Sprechblasen.
- **Hell oder dunkel** folgt der Windows-Einstellung „Standard-App-Modus“ (Einstellungen →
  Personalisierung → Farben) und wechselt sofort mit. Bei **hohem Kontrast** nimmt der Begleiter die
  Systemfarben. Mehrere Bildschirme mit unterschiedlicher Skalierung werden je Bildschirm richtig
  dargestellt.

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
   **Einstellungen …** → **Kopplung** → **Neu koppeln …**). Die Zeile einfügen, Gerätenamen prüfen, **Koppeln**.
3. Im Panel unter Ich → Begleiter die gewünschten Teile für dieses Gerät einschalten.

Adresse und Schlüssel liegen in `%APPDATA%\Spark Begleiter\config.json`; der Schlüssel ist mit
Windows (DPAPI) verschlüsselt und nur unter dem eigenen Windows-Konto lesbar. `https://` geht immer,
`http://` nur im Heimnetz (z. B. `http://192.168.178.10:31080`) – mit Warnung, weil unverschlüsselt.

Wird das Gerät im Panel entfernt, meldet der Begleiter „Der Spark kennt dieses Gerät nicht mehr.
Neu koppeln.“ und öffnet das Koppeln-Fenster.

## Benutzen

**Linksklick** aufs Symbol öffnet das Begleiter-Fenster (siehe oben). **Menü** (Rechtsklick aufs
Symbol): oben der Zustand („Verbunden mit …“, „Spark nicht erreichbar“ oder der Notaus-Text),
darunter die eingeschalteten Teile, ggf. „Aktualisieren auf …“, **Einstellungen …** und **Beenden**.

**Schreibhilfe:** Text markieren, **Strg+Alt+S**.
- Mit Vorschau (Panel-Einstellung): ein Fenster am Mauszeiger (oben steht, aus welchem Programm der
  Text kommt) zeigt die verbesserte Fassung mit markierten Änderungen (entfernt rot durchgestrichen,
  neu grün). Ein Klick auf eine andere Art (Chips oben) schickt den Text gleich neu; bei
  „Übersetzen“ erscheinen die Sprachen als zweite Reihe. **Neu** schickt mit dem Wunsch erneut.
  Unter „Änderungen“, „Ergebnis bearbeiten“ und „Ausgangstext“ lässt sich zwischen Ansicht,
  änderbarem Ergebnis und Original wechseln. **Übernehmen** (Strg+Enter) ersetzt die Markierung,
  **Kopieren** legt das Ergebnis nur in die Zwischenablage, **Esc** schließt.
- Ohne Vorschau: der Text wird mit den Voreinstellungen aus dem Panel verbessert und direkt
  eingefügt (ohne Fenster).

**Frag Spark:** **Strg+Alt+A**, Frage tippen, **Enter** (Umschalt+Enter = neue Zeile). Die Antwort
erscheint als Sprechblase mit reinem Text; Folgefragen behalten den Zusammenhang. **Kopieren** unter
einer Antwort (oder Rechtsklick auf die Blase, oder Strg+C) kopiert sie. Ist Diktieren an, nimmt der
**Mikrofon-Knopf** die Frage auf (noch einmal klicken = Stopp).

**Diktieren:** **Strg+Alt+D** startet die Aufnahme (unten rechts erscheint eine dunkle Pille „Ich
höre zu“ mit rotem Punkt, Zeit, Pegel und dem Tastenkürzel), **Strg+Alt+D** noch einmal beendet sie
(oder Klick auf die Pille). Der erkannte
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

## Updates

Neue Versionen holt der Spark selbst (von GitHub) und merkt sich ihre Prüfsumme. Der Begleiter fragt
**nur seinen eigenen Spark** – nie GitHub oder eine andere Adresse:

1. Bei jeder Abfrage nennt der Begleiter dem Spark seine Version und Bauart (x64 oder ARM64).
2. Hat der Spark eine neuere Version, bekommt das Symbol einen Punkt in der Akzentfarbe und das
   Begleiter-Fenster zeigt „Neue Version … · Geprüft vom Spark · NN MB“ mit **Aktualisieren**.
3. Ist **„Updates automatisch laden, vor dem Installieren fragen“** an (Standard, unter
   Einstellungen → Über), lädt der Begleiter die Datei schon im Hintergrund; dann steht dort
   „Bereit zum Installieren“. Installiert wird **nie ohne Klick** auf „Aktualisieren“.
4. Vor dem Installieren werden Größe **und** SHA-256 der Datei mit den Angaben des Spark verglichen.
   Passt etwas nicht, wird die Datei gelöscht („Update beschädigt, nichts geändert.“) und die alte
   Version läuft weiter.
5. Passt alles, beendet sich der Begleiter, die neue Version ersetzt die alte .exe (die alte wird
   kurz als `.old` daneben gelegt) und startet neu („Aktualisiert auf Version …“). Geht dabei
   etwas schief, bleibt die alte .exe und startet wieder.

Die Datei wird in `%LOCALAPPDATA%\Spark Begleiter\update\` geladen. Liegt die .exe in einem Ordner,
in den das eigene Konto nicht schreiben darf (z. B. `C:\Program Files`), öffnet der Begleiter den
Update-Ordner und sagt Bescheid – dann die alte .exe von Hand ersetzen. Deshalb am besten einen
eigenen Ordner wie `%LOCALAPPDATA%\Spark Begleiter\` verwenden.

**Einstellungen → Über** zeigt Version, Bauart, den gekoppelten Spark und den Update-Zustand;
**Nach Updates suchen** fragt den Spark sofort. Ein selbst gebautes Programm (Version 1.0.0) heißt
dort „Entwicklungsversion“ und bekommt keine Updates angeboten.

## Kaffee

Der Spark ist kostenlos. Wer ihn unterstützen möchte: **☕ Spark unterstützen** im Begleiter-Fenster
bzw. **☕ Buy me a coffee** unter Einstellungen → Über öffnet die Seite des Entwicklers bei
buymeacoffee.com im Standardbrowser – nur auf Klick, sonst wird nichts geladen. Die Adresse kann der
Spark vorgeben; angenommen werden nur Adressen der Form `https://buymeacoffee.com/…`.

## Tastenkürzel ändern

Klick aufs Symbol → **Einstellungen** → Reiter **Tastenkürzel** → in das Feld des Teils klicken und die neue
Kombination drücken. Sie muss Strg oder Alt enthalten. Ist sie schon von einem anderen Programm
belegt, steht das daneben und die alte bleibt. **Standard** stellt Strg+Alt+S / A / D wieder her.
Ausgeschaltete Teile haben kein aktives Tastenkürzel.

Im Reiter **Kopplung** gibt es außerdem **Panel öffnen**, **Neu koppeln …** und **Entkoppeln …**
sowie die Liste, welche Teile das Panel eingeschaltet hat.

## Entfernen

1. Rechtsklick aufs Symbol → **Einstellungen …** → **Kopplung** → **Entkoppeln …** (löscht den Schlüssel und
   schaltet „Mit Windows starten“ aus), dann **Beenden**.
2. Im Panel unter Ich → Begleiter das Gerät entfernen.
3. Die .exe löschen und die Ordner `%APPDATA%\Spark Begleiter` und `%LOCALAPPDATA%\Spark Begleiter\update`
   löschen.

## Bauen

`dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:Version=1.0.NNN`
(bzw. `-r win-arm64`). Das erledigt `.github/workflows/begleiter-windows.yml` bei jeder Änderung
an `tools/begleiter/windows/`: Die Version kommt aus `app/VERSION` („V01.0.342“ → `1.0.342`), die
Dateien und `begleiter.json` (Version, Größe, SHA-256 je Bauart – das prüft der Spark) landen im
Release `begleiter-windows`. Ohne `-p:Version` ist es Version 1.0.0, eine Entwicklungsversion ohne
Updates.
