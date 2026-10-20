# Spark Schreibhilfe für Outlook, Word und Excel

Ein Office-Add-in (Aufgabenbereich), das Texte mit dem eigenen Spark verbessert. Alle Dateien liefert das
Spark-Panel selbst aus (`{base}/office/…`); Texte gehen nur an den eigenen Spark.

**Voraussetzung:** Das Panel ist über **https mit gültigem Zertifikat** erreichbar (Office lehnt http und
selbstsignierte Zertifikate ab).

## Einrichten

1. Im Panel: **Ich → Schreibhilfe → In anderen Programmen** das passende Manifest herunterladen
   (`manifest-outlook.xml`, `manifest-word.xml` oder `manifest-excel.xml`, Adresse ist schon eingetragen).
2. In Office hochladen:
   - **Outlook** (neu, klassisch, Mac, im Web): *Add-ins abrufen → Meine Add-ins → Benutzerdefiniertes
     Add-in hinzufügen → Aus Datei hinzufügen*. Im Web: <https://aka.ms/olksideload>.
   - **Word / Excel**: *Einfügen → Add-ins → Meine Add-ins → Mein Add-in hochladen*
     (Windows/Mac ggf. über einen freigegebenen Ordner-Katalog, siehe Microsoft-Hilfe „Sideload“).
3. Knopf **Spark Schreibhilfe** anklicken (Outlook: im Menüband beim Lesen/Verfassen; Word/Excel: Start).
4. Einmal koppeln: im Panel *Ich → Schreibhilfe → Programm koppeln*, den Code `XXXX-XXXX` (oder die ganze
   Zeile) eingeben, Gerätename wählen. Der Schlüssel liegt im lokalen Speicher des Add-ins.

**Einfacher mit dem Spark-Begleiter:** Teil „Office-Add-ins“ einschalten, dann im Begleiter *Office-Add-ins
einrichten*. Word und Excel trägt er selbst ein, für Outlook zeigt er die Datei und öffnet die Seite zum Hinzufügen.
Für **Outlook classic** bringt er einen eigenen Knopf mit, der auch mit iCloud- und IMAP-Konten geht.


## Benutzen

- **Outlook verfassen:** Text markieren (ohne Markierung: ganzer Text) → *Markierten Text verbessern* →
  Änderungen prüfen → *Übernehmen*. Bei Antworten zusätzlich *Antwort entwerfen* (fügt am Cursor ein).
- **Outlook lesen:** *Antwort entwerfen* (optional Stichpunkte) → *Als Antwort öffnen*; oder *Mail übersetzen*.
  Bei *Antwort entwerfen* holt *3 Vorschläge* drei kurze Antworten; danach formen *Kürzer*, *Freundlicher*,
  *Förmlicher* und *Englisch* die Antwort um.
- **Word:** Text markieren → verbessern → *Übernehmen* ersetzt die Markierung.
- **Excel:** genau eine Zelle mit Text markieren → verbessern → *In Zelle schreiben*.

## Grenzen

- Wird der ganze Mailtext ersetzt, geht seine Formatierung verloren (es erscheint ein Hinweis).
- Hat sich die Markierung bis zum Übernehmen geändert, wird nichts ersetzt – dann *Kopieren* nutzen.
- Excel: keine Formeln, keine Mehrfachauswahl. Outlook mobil wird nicht unterstützt.
- Alte Office-Versionen mit Internet-Explorer-Ansicht (Office 2016/2019 ohne Microsoft 365) gehen nicht.
- Wird der lokale Speicher von Office geleert, muss neu gekoppelt werden.
