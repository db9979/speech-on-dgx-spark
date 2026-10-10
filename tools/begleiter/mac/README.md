# Spark-Begleiter für den Mac

Ein kleines Programm in der Menüleiste (kein Symbol im Dock) für den eigenen Spark. Es kann:

| Teil | Was es tut | Kürzel |
|---|---|---|
| **Schreibhilfe** | markierten Text verbessern, übersetzen, kürzen … – mit Vorschau der Änderungen | ⌥⌘S, und „Mit Spark verbessern“ im Dienste-Menü |
| **Frag Spark** | kleines Fenster: Frage tippen (oder sprechen), Antwort als Text; Folgefragen kennen den Zusammenhang | ⌥⌘A |
| **Diktieren** | Kürzel drücken, sprechen, Kürzel noch einmal drücken – der Text steht an der Schreibmarke | ⌥⌘D |
| **Meldungen** | Meldungen des Spark als Mitteilungen von macOS | – |
| **Zustandspunkt** | das Symbol in der Menüleiste zeigt den Zustand (siehe unten) | – |
| **Mein-Notaus-Knopf** | Menüpunkt „Mein Notaus auslösen …“ mit Rückfrage | – |

Welche Teile an sind, wird **zentral im Panel** eingestellt (Ich → Begleiter, für jedes gekoppelte Gerät).
Der Begleiter übernimmt Änderungen beim nächsten Abruf, spätestens nach etwa einer halben Minute.
Die Tastenkürzel stellt man dagegen **hier am Mac** ein (Menü → „Einstellungen …“).

Voraussetzung: macOS 13 (Ventura) oder neuer, Apple-Chip oder Intel.

## Installieren

1. Auf GitHub im Release [**begleiter-mac**](https://github.com/db9979/speech-on-dgx-spark/releases/tag/begleiter-mac)
   die Datei `Spark-Begleiter-mac.zip` herunterladen.
2. Entpacken (Doppelklick) und **„Spark-Begleiter“ in den Ordner „Programme“ ziehen**. Von dort klappen
   Autostart und das Dienste-Menü am zuverlässigsten.

## Erster Start

Das Programm ist (noch) nicht von Apple notarisiert. macOS fragt deshalb beim ersten Start nach:

- **Rechtsklick** (oder ctrl-Klick) auf „Spark-Begleiter“ im Ordner „Programme“ → **„Öffnen“** → im
  Hinweis noch einmal **„Öffnen“**.
- Klappt das nicht (neuere macOS-Versionen): einmal normal öffnen, den Hinweis schließen, dann
  **Systemeinstellungen → Datenschutz & Sicherheit**, ganz nach unten scrollen und bei „Spark-Begleiter“
  auf **„Dennoch öffnen“** klicken.

Danach startet das Programm normal. Es erscheint als ✨ in der Menüleiste, nicht im Dock.

## Koppeln

1. Im Panel des Spark (im Browser) **Ich → Begleiter → „Gerät koppeln“** wählen. Das Panel zeigt eine
   Einrichtungszeile wie `https://spark.example.de#begleiter=ABCD-EFGH`. Sie gilt 10 Minuten und nur einmal.
2. Beim ersten Start öffnet der Begleiter das Fenster „Spark-Begleiter koppeln“ von selbst (sonst
   Menüleiste → „Koppeln …“ oder Einstellungen → „Neu koppeln …“).
3. Die Zeile einfügen und **„Koppeln“** drücken. Wer mag, gibt stattdessen Adresse und Code einzeln ein.

Unverschlüsselt (`http://`) geht nur im Heimnetz (localhost, 127.x, 10.x, 192.168.x, 172.16–31.x,
Namen auf `.local`); sonst immer die `https://`-Adresse des Spark nehmen.

Der Schlüssel liegt danach im **Schlüsselbund** (Eintrag „Spark Begleiter“, Konto = Adresse des Spark), nie in
einer Datei. Der Begleiter redet nur mit dieser einen Adresse, ohne Cookies und ohne Zwischenspeicher, und
schickt nichts an andere Stellen (keine Telemetrie).

## Die Teile

### Schreibhilfe

- **Dienste-Menü (ohne besondere Freigabe):** Text markieren, Rechtsklick → **Dienste → „Mit Spark verbessern“**
  (oder im Programm-Menü → Dienste). Es öffnet sich das Fenster der Schreibhilfe; „Übernehmen“ ersetzt die
  Markierung. Taucht der Eintrag nicht auf: Systemeinstellungen → Tastatur → Tastaturkurzbefehle → Dienste →
  Text → „Mit Spark verbessern“ einschalten; notfalls einmal ab- und wieder anmelden.
- **Kürzel ⌥⌘S:** Text markieren, ⌥⌘S drücken. Der Begleiter kopiert die Markierung (⌘C), zeigt die Vorschau und
  fügt „Übernehmen“ wieder an der Stelle ein (⌘V). Die Zwischenablage ist danach wieder wie vorher. Dafür braucht
  er die Freigabe **Bedienungshilfen** (siehe unten). Ohne sie öffnet sich das Fenster leer: Text einfügen, das
  Ergebnis kommt in die Zwischenablage („Text ist in der Zwischenablage“).
- In der Vorschau ist Entferntes **rot und durchgestrichen**, Hinzugefügtes **grün**. Das Ergebnis lässt sich vor
  dem Übernehmen noch ändern. ⌘↩ übernimmt, Esc bricht ab.
- Art (Korrigieren, Glätten, Kürzer, …), Zielsprache, Wunsch und ob es überhaupt eine Vorschau gibt, kommen als
  Vorgabe aus dem Panel. Ohne Vorschau ersetzt ⌥⌘S den markierten Text direkt.

### Frag Spark

⌥⌘A (oder Menü → „Frag Spark …“) öffnet ein kleines Fenster: Frage eintippen, **Senden** (oder ↩ bzw. ⌘↩). Die Antwort
steht als einfacher Text darunter, lässt sich markieren und mit **Kopieren** übernehmen. Folgefragen kennen den
Zusammenhang. Ist Diktieren an, gibt es einen **Mikrofon-Knopf**, um die Frage zu sprechen.

### Diktieren

⌥⌘D startet die Aufnahme. Oben auf dem Bildschirm erscheint dann immer ein **roter Hinweis „Aufnahme läuft“**, und
das Symbol in der Menüleiste wird zum roten Mikrofon. Noch einmal ⌥⌘D (oder „Fertig“) beendet sie – spätestens
nach 60 Sekunden ist von selbst Schluss. Der Spark schreibt den Text, der Begleiter fügt ihn an der Schreibmarke ein
(mit Bedienungshilfen) bzw. legt ihn in die Zwischenablage. „Verwerfen“ wirft die Aufnahme weg. Aufgenommen wird
nur zwischen den beiden Tastendrücken; die Aufnahme geht nur an den eigenen Spark.

### Meldungen

Meldungen des Spark erscheinen als Mitteilungen von macOS. Beim ersten Mal fragt macOS, ob der Begleiter Mitteilungen
zeigen darf. Meldungen, die schon vor dem Start des Begleiters da waren, zeigt er nicht.

### Zustandspunkt

| Symbol | Bedeutung |
|---|---|
| ✨ normal | Spark erreichbar |
| ✨ grau | Spark nicht erreichbar (oder noch nicht gekoppelt) – der Begleiter versucht es beim nächsten Abruf wieder |
| 🛑 rot | Notaus oder Mein Notaus ist an |
| 🎙 rot | Aufnahme läuft |

Die erste Zeile im Menü sagt es auch in Worten.

### Mein-Notaus-Knopf

Menü → **„Mein Notaus auslösen …“**, nach einer Rückfrage. Danach hält der Spark für das eigene Profil an, und
auch der Begleiter bekommt keine Antworten mehr (Symbol rot). **Aufheben geht nur im Panel im Browser mit der PIN** –
dafür gibt es „Panel öffnen“.

## Tastenkürzel

Standard: **⌥⌘S** Schreibhilfe, **⌥⌘A** Frag Spark, **⌥⌘D** Diktieren. Ändern unter Menü → „Einstellungen …“:
auf das Kürzel klicken, die neue Kombination drücken (sie braucht ⌘, ⌥ oder ⌃; Esc bricht ab). „Standard“ stellt
das ursprüngliche Kürzel wieder her. Ist eine Kombination schon von macOS oder einem anderen Programm belegt, steht
das dort in Rot. Ein Teil, der im Panel aus ist, hat kein Kürzel. Die Kürzel selbst brauchen keine Freigabe.

## Freigaben

- **Bedienungshilfen** (Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen): nur nötig, damit der
  Begleiter für dich ⌘C/⌘V drücken kann (Schreibhilfe per Kürzel, Diktat an der Schreibmarke). Er fragt einmal mit
  einer Erklärung; später geht es über Einstellungen → „Erlauben …“. Klappt das Einfügen nach dem Erlauben nicht
  sofort, den Begleiter einmal beenden und neu starten.
  *Hinweis:* Weil das Programm nicht mit einem Apple-Zertifikat signiert ist, kann macOS nach einem **Update** die
  Freigabe nicht mehr zuordnen. Dann in der Liste „Spark-Begleiter“ mit „–“ entfernen und neu erlauben. Aus demselben
  Grund kann macOS nach einem Update einmal fragen, ob der Begleiter auf den Schlüsselbund-Eintrag zugreifen darf
  („Immer erlauben“).
- **Mikrofon**: fragt macOS beim ersten Diktat. Später unter Systemeinstellungen → Datenschutz & Sicherheit →
  Mikrofon.
- **Mitteilungen**: fragt macOS, sobald „Meldungen“ an ist.

## Autostart

Ob der Begleiter bei der Anmeldung startet, stellt man im Panel ein (Ich → Begleiter). Der Begleiter trägt sich
dann selbst als Anmeldeobjekt ein (Systemeinstellungen → Allgemein → Anmeldeobjekte); macOS zeigt dazu eine
Mitteilung.

## Entfernen

1. Menü → „Einstellungen …“ → **„Entkoppeln …“** (löscht den Schlüssel aus dem Schlüsselbund).
2. Im Panel unter **Ich → Begleiter** das Gerät entfernen – dann gilt der Schlüssel auch auf dem Spark nicht mehr.
3. Menü → „Spark-Begleiter beenden“, dann „Spark-Begleiter“ aus „Programme“ in den Papierkorb legen.
4. Falls gewünscht: Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen bzw. Mikrofon den Eintrag
   „Spark-Begleiter“ entfernen, und unter Allgemein → Anmeldeobjekte ebenso. Die eigenen Einstellungen (nur die
   Tastenkürzel) liegen in `~/Library/Preferences/de.db9979.spark.begleiter.plist`.

Wird das Gerät im Panel entfernt, während der Begleiter läuft, meldet er „Der Spark kennt dieses Gerät nicht mehr.
Neu koppeln.“, vergisst den Schlüssel und öffnet das Koppel-Fenster.

## Selbst bauen

Nur mit den Xcode-Kommandozeilenwerkzeugen (Xcode 16, macOS 15 SDK):

```sh
tools/begleiter/mac/build.sh
open tools/begleiter/mac/build/Spark-Begleiter.app
```

Das Skript baut für arm64 und x86_64 (`swiftc`, Swift 5 Sprachmodus), fügt beides mit `lipo` zusammen, legt die
Version aus `app/VERSION` ins `Info.plist` und signiert ad hoc (`codesign -s -`). Mit
`SIGN_IDENTITY="Developer ID Application: …"` signiert es stattdessen mit diesem Zertifikat und Hardened Runtime.
Der Workflow `.github/workflows/begleiter-mac.yml` macht dasselbe und veröffentlicht das Zip im Release
`begleiter-mac`; sind die Secrets `MAC_DEVID_P12` und `MAC_DEVID_P12_PASSWORD` gesetzt, signiert er zusätzlich mit
Developer ID und lässt das Programm notarisieren.
