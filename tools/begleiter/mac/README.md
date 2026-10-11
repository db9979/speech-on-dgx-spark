# Spark-Begleiter für den Mac

Ein kleines Programm in der Menüleiste (kein Symbol im Dock) für den eigenen Spark. Es kann:

| Teil | Was es tut | Kürzel |
|---|---|---|
| **Schreibhilfe** | markierten Text verbessern, übersetzen, kürzen … – mit Vorschau der Änderungen | ⌥⌘S, und „Mit Spark verbessern“ im Dienste-Menü |
| **Frag Spark** | kleines Fenster: Frage tippen (oder sprechen), Antwort als Text; Folgefragen kennen den Zusammenhang | ⌥⌘A |
| **Diktieren** | Kürzel drücken, sprechen, Kürzel noch einmal drücken – der Text steht an der Schreibmarke | ⌥⌘D |
| **Meldungen** | Meldungen des Spark als Mitteilungen von macOS | – |
| **Zustandspunkt** | das Symbol in der Menüleiste zeigt den Zustand (siehe unten) | – |
| **Mein-Notaus-Knopf** | Eintrag „Mein Notaus …“ mit Rückfrage | – |

Welche Teile an sind, wird **zentral im Panel** eingestellt (Ich → Begleiter, für jedes gekoppelte Gerät).
Der Begleiter übernimmt Änderungen beim nächsten Abruf, spätestens nach etwa einer halben Minute.
Die Tastenkürzel stellt man dagegen **hier am Mac** ein (Begleiter-Fenster → „Einstellungen“).

## So sieht er aus

Der Begleiter trägt dieselben Farben wie das Panel des Spark und das **Spark-Gesicht** (der kleine Roboterkopf mit
Farbverlauf). Hell oder dunkel richtet sich nach macOS; „Kontrast erhöhen“ (Bedienungshilfen) macht Linien und
graue Schrift kräftiger.

- **Menüleiste:** das Gesicht als Symbol. Ein farbiger Punkt unten rechts sagt, wenn etwas ist (siehe
  „Zustandspunkt“).
- **Klick aufs Gesicht** öffnet ein kleines Fenster: oben ein Farbverlauf, das Gesicht mit Profil, Gerätename und
  Zustand („verbunden“, „nicht erreichbar“, „Notaus“), darunter gegebenenfalls der Hinweis auf eine neue Version,
  dann die Teile, die an sind, jeweils mit ihrem Tastenkürzel, „Mein Notaus …“ in Rot und unten
  **Einstellungen**, **Panel öffnen** und der gelbe Knopf **☕ Spark unterstützen**. Der Knopf mit dem
  Ein/Aus-Zeichen oben rechts beendet den Begleiter. Esc oder ein Klick daneben schließt das Fenster.
- **Text verbessern**, **Frag Spark**, **Einstellungen** und **Koppeln** haben denselben Farbverlauf oben, runde
  Ecken und die Spark-Knöpfe.

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

Danach startet das Programm normal. Es erscheint als kleines Roboter-Gesicht in der Menüleiste, nicht im Dock.

## Koppeln

1. Im Panel des Spark (im Browser) **Ich → Begleiter → „Gerät koppeln“** wählen. Das Panel zeigt eine
   Einrichtungszeile wie `https://spark.example.de#begleiter=ABCD-EFGH`. Sie gilt 10 Minuten und nur einmal.
2. Beim ersten Start öffnet der Begleiter das Fenster „Spark-Begleiter koppeln“ von selbst (sonst
   Gesicht in der Menüleiste → „Koppeln …“ oder Einstellungen → „Neu koppeln …“).
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
- Oben steht, aus welchem Programm der Text kommt („aus Mail“). Die Art (Korrigieren, Glätten, Kürzer, …) wählt
  man mit einem Klick auf einen der **Chips**; der gewählte ist farbig, und der Spark arbeitet gleich mit der neuen
  Art.
- In der Vorschau ist Entferntes **rot hinterlegt und durchgestrichen**, Hinzugefügtes **grün hinterlegt**. Darunter
  stehen die Zahl der Änderungen und die Dauer („3 Änderungen · 1,2 s“). Das Ergebnis lässt sich vor dem
  Übernehmen noch ändern. ⌘↩ übernimmt, Esc bricht ab.
- Art, Zielsprache, Wunsch und ob es überhaupt eine Vorschau gibt, kommen als Vorgabe aus dem Panel. Ohne Vorschau
  ersetzt ⌥⌘S den markierten Text direkt.

### Frag Spark

⌥⌘A (oder Klick aufs Gesicht → „Frag Spark“) öffnet ein kleines Fenster wie ein Chat: Frage eintippen, **Senden**
(oder ↩ bzw. ⌘↩). Die eigene Frage steht rechts in einer farbigen Blase, die Antwort des Spark links mit dem Gesicht
daneben, als einfacher Text, der sich markieren und mit **Kopieren** übernehmen lässt. Folgefragen kennen den
Zusammenhang, **Neu** fängt von vorn an. Ist Diktieren an, gibt es einen runden **Mikrofon-Knopf**, um die Frage zu
sprechen.

### Diktieren

⌥⌘D startet die Aufnahme. Oben auf dem Bildschirm erscheint dann immer eine **dunkle Leiste mit rotem Punkt
„Ich höre zu“**, kleinen Pegel-Balken, der Zeit und dem Kürzel zum Beenden, und das Symbol in der Menüleiste wird
zum roten Mikrofon. Noch einmal ⌥⌘D (oder „Fertig“) beendet sie – spätestens
nach 60 Sekunden ist von selbst Schluss. Der Spark schreibt den Text, der Begleiter fügt ihn an der Schreibmarke ein
(mit Bedienungshilfen) bzw. legt ihn in die Zwischenablage. „Verwerfen“ wirft die Aufnahme weg. Aufgenommen wird
nur zwischen den beiden Tastendrücken; die Aufnahme geht nur an den eigenen Spark.

### Meldungen

Meldungen des Spark erscheinen als Mitteilungen von macOS. Beim ersten Mal fragt macOS, ob der Begleiter Mitteilungen
zeigen darf. Meldungen, die schon vor dem Start des Begleiters da waren, zeigt er nicht.

### Zustandspunkt

| Symbol | Bedeutung |
|---|---|
| Gesicht ohne Punkt (in der Farbe der Menüleiste) | Spark erreichbar, alles gut |
| farbiges Gesicht mit **grauem** Punkt | Spark nicht erreichbar (oder noch nicht gekoppelt) – der Begleiter versucht es beim nächsten Abruf wieder |
| farbiges Gesicht mit **rotem** Punkt | Notaus oder Mein Notaus ist an |
| farbiges Gesicht mit **blauviolettem** Punkt | eine neue Version ist da (siehe „Updates“) |
| rotes Mikrofon | Aufnahme läuft |

Im Fenster hinter dem Gesicht steht der Zustand auch in Worten.

### Mein-Notaus-Knopf

Klick aufs Gesicht → **„Mein Notaus …“**, nach einer Rückfrage. Danach hält der Spark für das eigene Profil an, und
auch der Begleiter bekommt keine Antworten mehr (Symbol rot). **Aufheben geht nur im Panel im Browser mit der PIN** –
dafür gibt es „Panel öffnen“.

## Tastenkürzel

Standard: **⌥⌘S** Schreibhilfe, **⌥⌘A** Frag Spark, **⌥⌘D** Diktieren. Ändern unter Einstellungen → „Tastenkürzel“:
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

## Updates

Neue Versionen holt sich der Begleiter **nur von deinem eigenen Spark**, nie direkt aus dem Internet:

1. Der Spark lädt die neue Mac-Version von GitHub und merkt sich Größe und Prüfsumme (SHA-256).
2. Beim nächsten Abruf sieht der Begleiter, dass es eine neuere Version gibt. Das Gesicht in der Menüleiste
   bekommt einen **blauvioletten Punkt**, und im Fenster dahinter steht **„Neue Version 1.0.350 · Geprüft vom Spark ·
   64 MB“** mit dem Knopf **„Aktualisieren“**.
3. Ist „Updates automatisch laden, vor dem Installieren fragen“ an (Standard), lädt der Begleiter die Datei schon
   im Hintergrund vom Spark und prüft sie. **Installiert wird nie ohne deinen Klick auf „Aktualisieren“.** Ist der
   Schalter aus, lädt er erst beim Klick.
4. Beim Klick prüft er noch einmal alles: Größe und SHA-256 der Datei müssen genau zu dem passen, was der Spark
   angekündigt hat, das ausgepackte Programm muss „de.db9979.spark.begleiter“ heißen, die angekündigte Version
   haben und gültig signiert sein. Dann beendet sich der Begleiter, ein kleines Hilfsskript tauscht das Programm
   aus und startet die neue Version.
5. Passt etwas nicht, kommt **„Update beschädigt, nichts geändert.“**, die Datei wird gelöscht, und die alte Version
   läuft einfach weiter. Geht beim Austausch etwas schief, legt das Hilfsskript die alte Version zurück und startet
   sie wieder.

Liegt der Begleiter in einem Ordner, in den er nicht schreiben darf (oder startet macOS ihn aus einem Download-Ordner
an einem versteckten Ort), legt er die geprüfte neue Version in
`~/Library/Application Support/Spark Begleiter/update/bereit/` und zeigt sie im Finder: Begleiter beenden und sie
selbst in „Programme“ ziehen.

**Einstellungen → Über** zeigt die eigene Version, Mac-Typ (Apple-Chip oder Intel), mit welchem Spark er gekoppelt
ist und den Stand der Updates; **„Nach Updates suchen“** fragt den Spark sofort. Ein selbst gebautes Programm ohne
Versionsnummer („Entwicklungsversion“, 0.0.0) bietet nie ein Update an.

Der Begleiter schickt bei jedem Abruf nur seine Versionsnummer und „mac“ mit, damit der Spark die passende Datei
kennt – sonst nichts.

*Hinweis:* Weil das Programm ohne Apple-Zertifikat signiert ist, fragt macOS nach einem Update eventuell neu nach
Bedienungshilfen bzw. dem Schlüsselbund (siehe „Freigaben“).

## Spark unterstützen

Der Spark ist kostenlos. Wer mag, kann dem Entwickler einen Kaffee spendieren: der gelbe Knopf **„☕ Spark
unterstützen“** im Fenster hinter dem Gesicht bzw. **„☕ Buy me a coffee“** unter Einstellungen → Über. Erst der
Klick öffnet die Seite auf buymeacoffee.com im Browser; der Begleiter selbst ruft dort nichts auf. Die Adresse kommt
vom Spark, angenommen wird aber nur eine `https://buymeacoffee.com/…`-Adresse, sonst nimmt er die feste
`https://buymeacoffee.com/zquu1xu570`.

## Autostart

Ob der Begleiter bei der Anmeldung startet, stellt man im Panel ein (Ich → Begleiter). Der Begleiter trägt sich
dann selbst als Anmeldeobjekt ein (Systemeinstellungen → Allgemein → Anmeldeobjekte); macOS zeigt dazu eine
Mitteilung.

## Entfernen

1. Einstellungen → Allgemein → **„Entkoppeln …“** (löscht den Schlüssel aus dem Schlüsselbund).
2. Im Panel unter **Ich → Begleiter** das Gerät entfernen – dann gilt der Schlüssel auch auf dem Spark nicht mehr.
3. Klick aufs Gesicht → Ein/Aus-Knopf oben rechts (beendet den Begleiter), dann „Spark-Begleiter“ aus „Programme“
   in den Papierkorb legen.
4. Falls gewünscht: Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen bzw. Mikrofon den Eintrag
   „Spark-Begleiter“ entfernen, und unter Allgemein → Anmeldeobjekte ebenso. Die eigenen Einstellungen (die
   Tastenkürzel und der Update-Schalter) liegen in `~/Library/Preferences/de.db9979.spark.begleiter.plist`, geladene
   Updates in `~/Library/Application Support/Spark Begleiter/` – beides kann weg.

Wird das Gerät im Panel entfernt, während der Begleiter läuft, meldet er „Der Spark kennt dieses Gerät nicht mehr.
Neu koppeln.“, vergisst den Schlüssel und öffnet das Koppel-Fenster.

## Selbst bauen

Nur mit den Xcode-Kommandozeilenwerkzeugen (Xcode 16, macOS 15 SDK):

```sh
tools/begleiter/mac/build.sh
open tools/begleiter/mac/build/Spark-Begleiter.app
```

Das Skript baut für arm64 und x86_64 (`swiftc`, Swift 5 Sprachmodus), fügt beides mit `lipo` zusammen, legt die
Version aus `app/VERSION` ins `Info.plist` (`V01.0.342` → `1.0.342`; fehlt die Datei, wird es `0.0.0`, eine
Entwicklungsversion ohne Updates) und signiert ad hoc (`codesign -s -`). Mit
`SIGN_IDENTITY="Developer ID Application: …"` signiert es stattdessen mit diesem Zertifikat und Hardened Runtime.
Der Workflow `.github/workflows/begleiter-mac.yml` macht dasselbe und veröffentlicht das Zip (und `begleiter.json`
mit Version, Größe und SHA-256 für den Spark) im Release `begleiter-mac`; sind die Secrets `MAC_DEVID_P12` und `MAC_DEVID_P12_PASSWORD` gesetzt, signiert er zusätzlich mit
Developer ID und lässt das Programm notarisieren.
