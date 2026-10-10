# Spark Schreibhilfe für den Browser

Erweiterung für Chrome, Edge (auch Windows auf ARM) und Firefox (ab 128). Sie verbessert markierten Text
in Webmail (Gmail, iCloud Mail, GMX, web.de, Outlook im Web) und in jedem anderen Textfeld – mit deinem
eigenen Spark. Der Text geht nur an deinen Spark, nirgendwo sonst hin. Keine Telemetrie.

## Installieren

Zip-Datei aus dem Spark-Panel herunterladen und in einen festen Ordner entpacken
(der Ordner muss bleiben, der Browser lädt die Erweiterung von dort).

**Chrome / Edge**

1. `chrome://extensions` bzw. `edge://extensions` öffnen.
2. **Entwicklermodus** einschalten (Chrome: oben rechts, Edge: links).
3. **Entpackte Erweiterung laden** → den entpackten Ordner wählen (der Ordner mit `manifest.json`).
4. Optional: über das Puzzle-Symbol die Schreibhilfe an die Symbolleiste anheften.

**Firefox (ab 128)**

1. `about:debugging#/runtime/this-firefox` öffnen.
2. **Temporäres Add-on laden …** → im entpackten Ordner die Datei `manifest.json` wählen.
3. Hinweis: Firefox vergisst eine so geladene Erweiterung beim nächsten Neustart. Dauerhaft geht es nur
   mit einer von Mozilla signierten Fassung (oder in Firefox Developer Edition/Nightly mit
   `xpinstall.signatures.required = false`).

## Koppeln

1. Im Spark-Panel: **Ich → Schreibhilfe → „Programm koppeln“**. Du bekommst eine Einrichtungszeile wie
   `https://spark.example.org#schreib=ABCD-EFGH` (10 Minuten gültig, nur einmal).
2. Einstellungen der Erweiterung öffnen (Rechtsklick auf das Symbol → Optionen/Einstellungen; ohne
   Kopplung öffnen sie sich beim ersten Benutzen von selbst).
3. Zeile einfügen, Gerätename anpassen (Vorgabe „Browser“), **Koppeln** klicken.
4. Der Browser fragt nach Zugriff auf genau die Adresse deines Spark – erlauben.

https:// geht immer. Unverschlüsseltes http:// nur im Heimnetz (z. B. `http://192.168.178.171:31080`),
dann mit Warnhinweis. Danach steht dort „Gekoppelt mit <Profil> auf <Adresse>“.

## Benutzen

- Text markieren → Rechtsklick → **Mit Spark verbessern** → Korrigieren, Glätten, Kürzer, Freundlicher,
  Förmlicher, Ins Englische oder Ins Deutsche.
- Oder **Strg+Umschalt+Y** (Mac: **⌘+Umschalt+Y**) bzw. Klick auf das Symbol: nutzt die Standard-Aktion
  aus den Einstellungen. In einem einfachen Textfeld ohne Markierung wird das ganze Feld genommen.
- Es erscheint ein Fenster mit „Der Spark schreibt …“, danach die Änderungen (rot durchgestrichen =
  entfernt, grün = neu) und das Ergebnis zum Nachbearbeiten.
- **Übernehmen** (oder Strg+Enter) ersetzt die Markierung, **Kopieren** legt das Ergebnis in die
  Zwischenablage, **Abbrechen**/Esc schließt. Über die Auswahl oben lässt sich eine andere Art neu anfordern.
- Meldet der Spark „nicht gekoppelt“, in den Einstellungen neu koppeln.

Das Tastenkürzel lässt sich ändern: `chrome://extensions/shortcuts`, `edge://extensions/shortcuts`,
in Firefox unter Add-ons → Zahnrad → „Tastenkombinationen für Erweiterungen verwalten“.

## Entfernen

1. In den Einstellungen **Entkoppeln** (löscht den Schlüssel und den Zugriff auf den Spark).
2. Im Spark-Panel unter Ich → Schreibhilfe das Gerät entfernen.
3. Erweiterung in `chrome://extensions` / `edge://extensions` bzw. `about:addons` entfernen.

## Grenzen

- Auf geschützten Seiten (Browser-Einstellungen, Web-Stores, PDF-Ansicht) geht es nicht; das Symbol zeigt
  dann kurz ein rotes „!“.
- Schreibfelder in eingebetteten Rahmen einer anderen Adresse brauchen die optionale Freigabe
  „Auf allen Seiten erlauben“ in den Einstellungen.
- Sehr eigenwillige Editoren können „Übernehmen“ ablehnen oder die Formatierung der Markierung verlieren;
  dann „Kopieren“ und selbst einfügen.
