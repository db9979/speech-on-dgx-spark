# Spark Schreibhilfe für Windows

Kleines Programm im Infobereich der Taskleiste: Text in einem beliebigen Programm markieren
(Outlook, Word, Excel, Browser …), **Strg+Alt+S** drücken – ein Fenster am Mauszeiger zeigt die
vom eigenen Spark verbesserte Fassung mit markierten Änderungen (entfernt rot durchgestrichen,
neu grün). **Übernehmen** ersetzt die Markierung durch das Ergebnis.

Der Text geht nur an den eigenen Spark, sonst nirgendwohin. Keine Telemetrie, kein Protokoll.

## Installieren

1. Unter *Releases* → **schreibhilfe-windows** die passende Datei laden:
   - `SparkSchreibhilfe-x64.exe` für die meisten PCs (Intel/AMD),
   - `SparkSchreibhilfe-arm64.exe` für Windows auf ARM (z. B. Snapdragon).
2. Die .exe an einen festen Ort legen, z. B. `%LOCALAPPDATA%\SparkSchreibhilfe\`, und starten.
   Eine Installation ist nicht nötig, .NET muss nicht installiert sein.
3. Die Datei ist nicht signiert. Windows SmartScreen warnt deshalb beim ersten Start:
   **„Weitere Informationen“ → „Trotzdem ausführen“**.

## Koppeln

1. Im Panel des Spark: **Ich → Schreibhilfe → „Programm koppeln“**. Es erscheint eine Zeile wie
   `https://speech.example.org#schreib=ABCD-EFGH` (gilt 10 Minuten, nur einmal).
2. Beim ersten Start öffnet sich „Einrichten“ (sonst: Rechtsklick aufs Symbol → **Einrichten …**).
   Die Zeile einfügen, Gerätenamen prüfen, **Koppeln**.

Adresse und Schlüssel liegen in `%APPDATA%\SparkSchreibhilfe\config.json`; der Schlüssel ist mit
Windows (DPAPI) verschlüsselt und nur unter dem eigenen Windows-Konto lesbar. `https://` geht immer,
`http://` nur im Heimnetz (z. B. `http://192.168.178.10:31080`) – mit Warnung, weil unverschlüsselt.

## Benutzen

- Text markieren, **Strg+Alt+S**. Ist nichts markiert, bleibt das Textfeld leer zum Einfügen.
- Art wählen (Korrigieren, Glätten, Kürzer, Freundlicher, Förmlicher, Übersetzen), optional einen
  Wunsch eintragen, **Neu** schickt den Text erneut.
- Das Ergebnis lässt sich vor dem Übernehmen noch ändern. **Übernehmen** (Strg+Enter) fügt ein,
  **Kopieren** legt es nur in die Zwischenablage, **Esc** schließt.
- Linksklick aufs Symbol öffnet das Fenster ohne markierten Text; dann landet das Ergebnis in der
  Zwischenablage.
- Rechtsklick aufs Symbol: **Mit Windows starten** ein/aus.

Hinweise: Die Zwischenablage wird kurz benutzt und danach wiederhergestellt (Text, RTF, HTML, Bilder,
Dateien; seltene Sonderformate gehen dabei verloren). In Programmen, die als Administrator laufen,
kann die Schreibhilfe nicht kopieren/einfügen. Meldet der Spark „nicht mehr gekoppelt“, im Fenster
**Neu koppeln** wählen.

## Deinstallieren

1. Rechtsklick aufs Symbol → „Mit Windows starten“ ausschalten → **Beenden**.
2. Die .exe löschen und den Ordner `%APPDATA%\SparkSchreibhilfe` löschen.
3. Im Panel unter Ich → Schreibhilfe das Gerät entfernen.

## Bauen

`dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true`
(bzw. `-r win-arm64`). Das erledigt `.github/workflows/schreibhilfe-windows.yml` bei jeder Änderung
an `tools/schreibhilfe/windows/` und legt die Dateien ins Release `schreibhilfe-windows`.
