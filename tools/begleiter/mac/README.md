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
| **Rechtsklick auf Dateien** | im Finder: Dienste → „Mit Spark zusammenfassen / übersetzen / erklären / ins Wissen übernehmen“ | – |
| **Bildschirm fragen** | einen Bereich des Bildschirms aufziehen und den Spark dazu fragen | ⌥⌘B |
| **App erkennen** | die Schreibhilfe erfährt die *Art* des Programms (Mail, Browser, Word …), nie Namen oder Fenstertitel | – |
| **Antwort entwerfen** | zur ausgewählten Mail in Mail einen Antwortentwurf öffnen – gesendet wird nie | ⌥⌘M |
| **Ordner „Spark-Wissen“** | neue oder geänderte Dateien in `~/Spark-Wissen` kommen ins Wissen des Spark | – |
| **Knöpfe in Meldungen** | Meldungen mit „Antworten“, „Später“, „Panel öffnen“; zu „Für dich“ „Erledigt“, „Erinnern“ | – |
| **Spark darf am Mac handeln** | der Spark darf um wenige, fest umrissene Dinge bitten – jedes einzeln mit Rückfrage | – |
| **Weckwort** | „Hey Spark, …“ sagen statt ein Kürzel zu drücken | – |
| **Vorlesen** | markierten Text liest der Spark mit der Stimme des Profils vor | ⌥⌘L |
| **Vom Handy auf den Mac** | Text, Links und Dateien, die du im Panel an diesen Mac schickst, kommen hier an | – |
| **Termine im Begleiter** | „Als Nächstes“ im Begleiter-Fenster, Mitteilung 10 Minuten vor jedem Termin | – |
| **Post im Begleiter** | „Post“ im Begleiter-Fenster: ungelesen und Für dich, dringende Karten mit „Erledigt“/„Erinnern“; wichtige neue Mail als Mitteilung mit „Antwort entwerfen“, „Gelesen“, „Ansehen“ | – |
| **Schnell erfassen** | eine Zeile wie „Zahnarzt Fr 10 Uhr bei Dr. Weber“ als Termin oder Erinnerung; gespeichert erst mit „Eintragen“, danach „Rückgängig“ | ⌃⌥N |
| **Listen im Begleiter** | „Listen“ im Begleiter-Fenster: Listen mit offenen Einträgen, Zahl und neuester Eintrag, „Öffnen“ führt zur Seite Listen | – |
| **Nicht stören erkennen** | bei Anruf, Kamera oder Präsentation hält der Spark seine Meldungen zurück | – |
| **Besprechung mitschreiben** | Mikrofon und Ton des Macs mitschreiben, danach Zusammenfassung und Aufgaben | ⌥⌘R |
| **Smart-Home-Knöpfe** | Abschnitt „Zuhause“ mit den im Panel gewählten Knöpfen | – |
| **Tagesstart und Feierabend** | morgens beim ersten Entsperren und abends beim Sperren ein kurzer Überblick | – |

Die Teile ab „Rechtsklick auf Dateien“ (auch die neuen ab „Vorlesen“) sind anfangs **für alle Geräte aus** und müssen im Panel einzeln eingeschaltet
werden.

Welche Teile an sind, wird **zentral im Panel** eingestellt (Ich → Begleiter, für jedes gekoppelte Gerät).
Der Begleiter übernimmt Änderungen beim nächsten Abruf, spätestens nach etwa einer halben Minute.
Die Tastenkürzel stellt man dagegen **hier am Mac** ein (Begleiter-Fenster → „Einstellungen“).

## So sieht er aus

Der Begleiter trägt dieselben Farben wie das Panel des Spark und das **Spark-Gesicht** (der kleine Roboterkopf mit
Farbverlauf). Hell oder dunkel richtet sich nach macOS; „Kontrast erhöhen“ (Bedienungshilfen) macht Linien und
graue Schrift kräftiger.

- **Menüleiste:** das Gesicht als Symbol. Ein farbiger Punkt unten rechts sagt, wenn etwas ist (siehe
  „Zustandspunkt“).
- **Klick aufs Gesicht** öffnet ein kleines Fenster: oben ein Farbverlauf, das Gesicht mit Gruß („Guten Morgen,
  Dominik“), Gerätename und Zustand als Punkt, rechts das Zahnrad für die **Einstellungen** und das
  Ein/Aus-Zeichen (beendet den Begleiter). Darunter gegebenenfalls der Hinweis auf eine neue Version, dann das Feld
  **„Frag Spark …“** (Enter fragt, das Mikrofon fragt per Sprache), die Befehle als **Kacheln** mit Tastenkürzel
  und Abschnitte wie im Panel: **Als Nächstes**, **Zuhause** und **Dieser Mac** mit Schaltern für Mikrofon und
  Weckwort und Zeilen für Wissen-Ordner, Vom Spark, Nicht stören und Office-Add-ins. Unten **Panel öffnen** und
  „Notaus …“ in Rot. Esc oder ein Klick daneben schließt das Fenster.
- **Einstellungen** haben links ein Seitenmenü wie das Panel: Übersicht (Zustand und was im Panel an ist),
  Frag Spark, Tastenkürzel, Tagesstart, Wissen-Ordner und unter „Gerät“ Berechtigungen, Kopplung, Über und Update.
  Seiten von Teilen, die aus sind, fehlen.
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

⌥⌘A (oder Klick aufs Gesicht → Feld „Frag Spark …“) öffnet ein kleines Fenster wie ein Chat: Frage eintippen, **Senden**
(oder ↩ bzw. ⌘↩). Die eigene Frage steht rechts in einer farbigen Blase, die Antwort des Spark links mit dem Gesicht
daneben, als einfacher Text, der sich markieren und mit **Kopieren** übernehmen lässt. Folgefragen kennen den
Zusammenhang, **Neu** fängt von vorn an. Ist Diktieren an, gibt es einen runden **Mikrofon-Knopf**, um die Frage zu
sprechen.

**Karten unter der Antwort** (wie im Panel und im iPhone): fragt der Spark zurück („Soll ich … eintragen?“), stehen
**Ja** und **Nein** darunter, bei „A oder B?“ die beiden Teile und „Anders …“; wartet ein Vorschlag auf dein Ja
(„Termin wartet auf dein Ja“), ebenso. Ein Klick schickt nur dieses Wort, als hättest du es getippt; entscheiden tut
der Spark mit seinen festen Regeln. Hat die Antwort Termine oder eine Mail gelesen, öffnet **Im Kalender ansehen ↗**
bzw. **Mail öffnen ↗** die Seite im Panel. Ist im Panel „Ablauf und Freigabe zeigen“ an, steht unter der Antwort
klein, welche Werkzeuge der Spark benutzt hat und wie lange es dauerte.

### Diktieren

⌥⌘D startet die Aufnahme. Oben auf dem Bildschirm erscheint dann immer eine **dunkle Leiste mit rotem Punkt
„Ich höre zu“**, kleinen Pegel-Balken, der Zeit und dem Kürzel zum Beenden, und das Symbol in der Menüleiste wird
zum roten Mikrofon. Noch einmal ⌥⌘D (oder „Fertig“) beendet sie – spätestens
nach 60 Sekunden ist von selbst Schluss. Der Spark schreibt den Text, der Begleiter fügt ihn an der Schreibmarke ein
(mit Bedienungshilfen) bzw. legt ihn in die Zwischenablage. „Verwerfen“ wirft die Aufnahme weg. Aufgenommen wird
nur zwischen den beiden Tastendrücken; die Aufnahme geht nur an den eigenen Spark.

Ist Diktieren an, hat außerdem jedes freie Textfeld in den Begleiter-Fenstern einen kleinen **Mikrofon-Knopf**:
„Antwort entwerfen“ (Stichpunkte, Mail-Text), „Text verbessern“ (Wunsch, Dein Text, Ergebnis) und „Bildschirm
fragen“ (Frage). Klick startet, ■ beendet; der erkannte Text wird ans Feld angehängt und nie ausgeführt.

### Meldungen

Meldungen des Spark erscheinen als Mitteilungen von macOS. Beim ersten Mal fragt macOS, ob der Begleiter Mitteilungen
zeigen darf. Meldungen, die schon vor dem Start des Begleiters da waren, zeigt er nicht.

### Rechtsklick auf Dateien

Im Finder eine oder mehrere Dateien auswählen (bis zu 10), Rechtsklick → **Dienste** → **„Mit Spark
zusammenfassen“**, **„… übersetzen“** (ins Deutsche), **„… erklären“** oder **„… ins Wissen übernehmen“**. Die
Antwort erscheint im Fenster von „Frag Spark“ und lässt sich dort kopieren; „ins Wissen übernehmen“ meldet nur kurz,
wie viele Dateien übernommen wurden (oder schon da waren). Der Spark nimmt PDF, Word, Excel, PowerPoint, ODT, Text,
Markdown, E-Mails (.eml), HTML und Bilder (JPG, PNG, HEIC) bis 20 MB. Ist der Teil im Panel aus, sagt der Begleiter
das nur kurz und schickt nichts.

Fehlen die Einträge: Systemeinstellungen → Tastatur → Tastaturkurzbefehle → Dienste → „Dateien und Ordner“ die
„Mit Spark …“-Einträge einschalten; notfalls einmal ab- und wieder anmelden.

### Bildschirm fragen

⌥⌘B: Der Mauszeiger wird zum Fadenkreuz (das ist das eigene Bildschirmfoto-Werkzeug von macOS). Einen Bereich
aufziehen – Leertaste wechselt zur Auswahl eines Fensters, Esc bricht ab. Dann öffnet sich ein kleines Fenster mit
dem Ausschnitt, den Chips **Erklären**, **Text herauslesen**, **Übersetzen** und einem Feld für eine Frage (freiwillig).
„Fragen“ schickt das Bild an den eigenen Spark, die Antwort steht im Fenster von „Frag Spark“. Das Bild wird auf
höchstens 2000 Pixel Kantenlänge verkleinert; die kurz angelegte Datei liegt in einem privaten Zwischenordner und wird
gleich nach dem Lesen gelöscht.

Beim ersten Mal braucht der Begleiter die Freigabe **Bildschirmaufnahme** (siehe „Freigaben“).

### App erkennen

Ist der Teil an, schickt die Schreibhilfe mit, *welche Art* Programm vorne war, als das Kürzel kam – „mail“,
„outlook“, „word“, „browser“, „chat“, „code“ … oder „other“. So schreibt der Spark in Mail eher wie eine Mail und in
Slack eher wie im Chat. Bestimmt wird das am Mac aus der Kennung des Programms; **Namen, Fenstertitel oder Inhalte
gehen nie mit**.

### Antwort entwerfen (Mail)

In **Mail** eine Mail auswählen, ⌥⌘M drücken (oder Klick aufs Gesicht → „Antwort entwerfen“). Ein kleines Fenster
zeigt Absender und Betreff; dort kann man in Stichpunkten sagen, was drinstehen soll („zusagen, Dienstag 10 Uhr“) –
oder es leer lassen. „Entwurf schreiben“ lässt den Spark antworten, dann öffnet Mail ein **neues Antwortfenster** mit
dem Vorschlag über der zitierten Mail. **Der Begleiter sendet nie** – lesen, anpassen und selbst auf „Senden“ klicken.

Gelesen werden nur Absender, Betreff und Text der ausgewählten Mail (höchstens 20000 Zeichen). Beim ersten Mal fragt
macOS, ob der Begleiter Mail steuern darf (siehe „Freigaben“).

**Outlook:** Das neue Outlook für Mac lässt sich nicht so steuern. Ist Outlook vorne, nimmt ⌥⌘M den markierten Text
der Mail (mit Bedienungshilfen) oder man fügt ihn im Fenster ein; der Entwurf kommt in die Zwischenablage – im
Antwortfenster von Outlook mit **⌘V** einfügen.

Im Fenster holt **„3 Vorschläge“** drei kurze Antworten zur Mail; ein Klick übernimmt einen, danach formen „Kürzer“,
„Freundlicher“, „Förmlicher“ und „Englisch“ ihn um. Gesendet wird auch hier nie.

### Ordner „Spark-Wissen“

Ist der Teil an, legt der Begleiter den Ordner **`~/Spark-Wissen`** an (Einstellungen → Allgemein → „Anderen Ordner
wählen …“ nimmt einen anderen). Alle 15 Sekunden schaut er hinein: Neue oder geänderte Dateien gehen ins Wissen des
Spark, sobald sie 10 Sekunden lang nicht mehr verändert wurden. Versteckte, temporäre und halb geladene Dateien bleiben
liegen, ebenso Dateiarten, die der Spark nicht nimmt. Höchstens **50 Dateien am Tag**; der Rest folgt am nächsten
Tag. Danach kommt eine Mitteilung „3 Dateien ins Wissen übernommen“.

Welche Dateien schon geschickt wurden, merkt sich der Begleiter in
`~/Library/Application Support/Spark Begleiter/wissen-ordner.json` (Pfad, Größe, Änderungszeit, SHA-256). Eine
Datei, die nur angefasst, aber nicht verändert wurde, geht nicht noch einmal; eine, die der Spark schon kennt, zählt
als erledigt.

Unterordner, die im Panel unter **Ich → Dokumente → Ausgelassene Ordner** stehen (ein Ordner oder eine Namensregel
wie „Archiv“ oder „Alt*“), schaut der Begleiter nicht an; was er von dort geschickt hatte, vergisst er, damit „Wieder
zulassen“ es neu schickt. Zu jeder Datei nennt er ihren Unterordner, und die Namen der Unterordner (nur Namen) gehen
ans Panel, damit es sie als Baum zeigt. Nach dem Update auf diese Fassung geht jede schon geschickte Datei einmal mit
ihrem Ordner neu (zählt nicht für die 50 am Tag).

### Knöpfe in Meldungen

Mit diesem Teil haben Meldungen des Spark (sofern der Spark sie anbietet) Knöpfe – in der Mitteilung auf „Optionen“
bzw. den Pfeil klicken:

- **Antworten**: ein Textfeld direkt in der Mitteilung. Die Antwort geht mit Bezug auf die Meldung an den Spark; seine
  Antwort kommt als Mitteilung und steht auch im Fenster von „Frag Spark“. Ohne Text öffnet sich „Frag Spark“ mit der
  Meldung als Bezug.
- **Später**: die Meldung kommt in einer Stunde noch einmal (merkt sich macOS).
- **Panel öffnen**: öffnet das Panel im Browser, und zwar an der Stelle, die die Meldung nennt („E-Mail → Für dich“,
  „Ich → Gedächtnis“).
- Zu einer Frist oder einem Verdacht aus **Für dich**: **Erledigt** (die Karte gilt als erledigt) und **Erinnern**
  (Erinnerung am Tag vor der Frist). Welche Knöpfe eine Meldung hat, legt das Panel nach ihrer Art fest, nie ihr Text.

### Spark darf am Mac handeln

Mit diesem Teil darf der Spark **bitten**, etwas am Mac zu tun. Jede einzelne Bitte erscheint als Dialog vorne auf dem
Bildschirm: **„Spark möchte: … Erlauben?“** mit **Erlauben** und **Nein**. Ohne Antwort gilt nach 60 Sekunden „Nein“.
Möglich ist nur:

| Bitte | Was der Begleiter tut |
|---|---|
| Adresse öffnen | nur `http://`- und `https://`-Adressen, im Standardbrowser |
| Programm starten | nur ein Programm aus der Liste, die im Panel für dieses Gerät eingetragen ist (Pfad wie `/Applications/Safari.app`, Kennung wie `com.apple.Safari` oder Name) |
| Medien | Wiedergabe/Pause, nächster, voriger Titel (wie die Medientasten) |
| Lautstärke | lauter, leiser, Ton aus/an (wie die Tasten) |
| Bildschirm sperren | sofort sperren |
| Text zeigen | ein Fenster mit einfachem Text |

| Programm nach vorn | ein Programm aus der Liste nach vorn holen (läuft es nicht, wird es gestartet) |
| Fenster | das Fenster vorn schließen (⌘W), ins Dock (⌘M), zoomen oder Vollbild (⌃⌘F) |
| Taste | nur aus einer festen Liste: Bild ab/auf (Folien), Leertaste, Return, Esc, Tab, ⌘Z, ⇧⌘Z, ⌘C, ⌘V, ⌘S, ⌘R, ⌘F |
| Tippen | die eigenen Worte der Person (höchstens 500 Zeichen) ins Fenster vorn |
| Ordner | Dokumente, Downloads, Schreibtisch, Bilder, Musik, Filme, Zuletzt benutzt |
| Mac | Ruhezustand, Bildschirm aus (`pmset`) |
| Kurzbefehl | ein hier freigegebener Kurzbefehl aus der App Kurzbefehle (`shortcuts run`) |

Alles andere lehnt der Begleiter ab, auch wenn es der Spark schickt; dieselbe Bitte läuft nie zweimal. Medien- und
Lautstärketasten, Fenster, Tasten und Tippen brauchen die Freigabe **Bedienungshilfen**.

Unter **Am PC handeln einstellen** (im Menü des Begleiters) legst du fest, welche Arten **ohne Rückfrage** laufen
(danach zeigt der Begleiter einen Hinweis; Seiten, Tippen und Text zeigen fragen immer), und welche **Kurzbefehle**
der Spark nennen darf. Beides geht nur hier am Mac, nie aus dem Panel; „Künftig ohne Rückfrage“ lässt sich auch direkt
im Dialog anhaken. Bitten kommen sofort an: der Begleiter wartet mit `GET /api/desk/wait` auf sie.

**Rechner fernsteuern, Stufe 2: Bildschirm zeigen und bedienen** (Teil `view`, Admin-Schalter `chat.desk_view`):
Tippt man im Panel unter Ich → Begleiter „Bildschirm ansehen“ oder „Bedienen“, fragt der Begleiter hier: **Ablehnen**,
**Nur ansehen** oder **Erlauben** (nur bei „Bedienen“); ohne Antwort nach 60 s gilt Ablehnen. Danach zeigt er einen
roten Rahmen und oben eine Leiste mit **Beenden**, schickt bis zu vier JPEG-Bilder je Sekunde vom Hauptbildschirm
(`screencapture -x -m`, die Datei liegt in einem privaten Ordner und wird sofort gelöscht, höchstens 1600 Pixel) und
führt nach „Erlauben“ Klicks, Mausbewegungen, Scrollen, feste Tasten (keine ⌘-Leertaste, kein ⌘-Tab) und getippten
Text aus. Braucht **Bildschirmaufnahme**, zum Bedienen **Bedienungshilfen**. Beenden auch mit Mein Notaus.

**Rechner fernsteuern, Stufe 3: Spark bedient den Rechner** (Admin-Schalter `chat.desk_operate`, Teile `act` und
`view`): Sagt man „Spark, schreib in Outlook an Anna …“, kommt dieselbe Anfrage mit dem Auftrag; Ablehnen ist
vorgewählt. Danach bekommt der Begleiter einen Schritt nach dem anderen (`"t":"step"`: Klick, Doppelklick,
Rechtsklick, Scrollen, feste Taste, Text) und zeigt jeden mit rot markiertem Ziel: **Stopp** (vorgewählt),
**Überspringen** oder **Erlauben**; ohne Antwort nach 60 s gilt Stopp. Erst nach „Erlauben“ holt er das Programm
von vorher wieder nach vorn und führt den Schritt aus, dann meldet er `POST /api/desk/view/step`. Text, der nicht
im Auftrag stand, steht als Warnung darüber; „Spark fragt nach“ (Nein / Weiter) kommt, wenn auf dem Bildschirm etwas
wie eine Anweisung stand. Mit jedem Bild schickt er Name und Pfad des Programms vorn, der Spark prüft es gegen die
freigegebenen. Die Frage ist ein Hinweisfenster, der rote Ring klickt durch; beide und die Leiste sind aus den Bildern ausgenommen (`sharingType = .none`). Braucht „Bildschirmaufnahme“ und „Bedienungshilfen“.

**Bildschirm beschreiben** (gleicher Schalter, Teil `view`): Fragt man „Was siehst du auf meinem Mac?“, kommt die
Anfrage mit `want` `look` und der Frage; der Begleiter fragt **Ablehnen** (vorgewählt) oder **Erlauben**, schickt danach
ein Bild, und der Spark beendet die Sitzung selbst. Ältere Begleiter zeigen dafür die gewöhnliche Frage „Bildschirm zeigen“.

Damit man die Programme im Panel **auswählen** kann statt Name und Pfad zu tippen, schickt der Begleiter, solange
dieser Teil an ist, die Liste der installierten Programme an den Spark: beim Start, wenn der Teil eingeschaltet
wird, und einmal am Tag. Darin stehen nur Name und Pfad der `.app`-Programme aus `/Applications`,
`/Applications/Utilities`, `/System/Applications` (mit `Utilities`) und `~/Applications` (je zwei Ebenen tief),
höchstens 600.

### Weckwort

Ist der Teil an, hört der Begleiter über das Mikrofon auf das Weckwort des Spark (Standard **„Hey Spark“**, im Panel
für den ganzen Spark eingestellt). Er schneidet dafür nur Sätze heraus, die lauter als das Grundrauschen sind (bis
5 Sekunden), und schickt sie an den eigenen Spark, der prüft, ob das Weckwort darin war. Sonst bleibt nichts liegen.

- **„Hey Spark, wie wird das Wetter morgen?“** – die Frage geht gleich an den Spark, die Antwort steht im Fenster von
  „Frag Spark“.
- **„Hey Spark“** allein – ein kurzer Ton („Tink“), dann die Frage sagen; nach einer kurzen Pause (höchstens 15 Sekunden)
  geht sie an den Spark.

Solange das Weckwort hört, zeigt macOS den **orangen Mikrofon-Punkt** in der Menüleiste, und das Gesicht hat unten
rechts einen **türkisen Ring**. Klick aufs Gesicht → Schalter **„Weckwort“** unter „Dieser Mac“ schaltet das Mikrofon ab, bis man
„Weckwort fortsetzen“ wählt (das merkt sich der Begleiter auch über einen Neustart). Ganz aus geht es im Panel.
Während eines Diktats wird nichts ans Weckwort geschickt.

### Vorlesen

Text markieren, **⌥⌘L** drücken: Der Begleiter kopiert den markierten Text (wie die Schreibhilfe, dafür braucht er die
Freigabe **Bedienungshilfen**; die Zwischenablage ist danach wie vorher) und schickt ihn an den Spark, der ihn mit der
Stimme deines Profils spricht. Oben auf dem Bildschirm steht solange **„Spark liest vor“** mit **Stopp**; ⌥⌘L noch
einmal hält ebenfalls an. Höchstens 5000 Zeichen. Im Begleiter-Fenster liest **„Zwischenablage vorlesen“** den
kopierten Text. Die Sprachausgabe bleibt nur im Speicher.

Auch **„Frag Spark“** kann seine Antworten vorlesen. Einstellbar im Fenster (Lautsprecher-Knopf unten) oder unter
Einstellungen → „Vorlesen“: **immer**, **nur bei gesprochenen Fragen** (Standard: mit dem Mikrofon-Knopf im Fenster
oder mit dem Weckwort gefragt) oder **nie**. Getippte Fragen bleiben still, außer bei „immer“. Eine neue Frage oder
„Stopp“ beendet das Vorlesen. Ohne den Teil „Vorlesen“ wird nichts vorgelesen.

### Vom Handy auf den Mac

Was du im Panel (z. B. am Handy) an dieses Gerät schickst, kommt mit dem nächsten Abruf an:

- **Text** liegt in der Zwischenablage, dazu die Mitteilung „Vom Spark: Text liegt in der Zwischenablage“.
- **Link**: Rückfrage „Link öffnen?“ mit **Öffnen**, **Kopieren**, **Nein**. Geöffnet werden nur `http://`- und
  `https://`-Adressen.
- **Datei** (bis 20 MB): landet in **Downloads/Vom Spark** (macOS fragt beim ersten Mal nach dem Zugriff auf
  „Downloads“). Eine vorhandene Datei wird nie überschrieben, sondern „Name (2).pdf“ angelegt. Die Mitteilung hat
  den Knopf **Ordner öffnen**.

Jedes Stück kommt genau einmal an; danach meldet der Begleiter dem Spark „erledigt“ (auch bei „Nein“).

### Termine im Begleiter

Alle 5 Minuten holt der Begleiter die Termine und Erinnerungen der nächsten 24 Stunden. Im Begleiter-Fenster steht
der Abschnitt **„Als Nächstes“**; 10 Minuten vor jedem Termin kommt eine Mitteilung mit Titel und Uhrzeit (einmal je
Termin). Meldungen des Spark bekommen zusätzlich den Knopf **„In 20 Min erinnern“**. Termine aus Kalendern, die andere
Profile mit dir teilen, tragen den Namen des Profils; ein Klick auf einen Termin öffnet den Tag im Kalender des Panels.

### Post im Begleiter

Im Begleiter-Fenster steht der Abschnitt **„Post“**: wie viele Mails ungelesen sind und wie viele Karten in „Für dich“
warten, darunter die bis zu 3 dringenden Karten mit **„Erledigt“**, **„Erinnern“** und **„Ansehen“**; „E-Mail öffnen“
springt ins Panel. Alle 5 Minuten, beim Öffnen des Fensters und bei einer neuen Mail aufgefrischt. Eine wichtige neue
Mail (welche, entscheidet der Spark) kommt als Mitteilung mit **„Antwort entwerfen“** (Frag Spark mit der Bitte im
Feld, gesendet wird nichts), **„Gelesen“** (nur mit „Mails ordnen“) und **„Ansehen“**. Bei verborgenen Vorschauen
zeigt der Sperrbildschirm nur „Neue Mail“.

### Schnell erfassen

⌃⌥N (oder die Kachel „Erfassen“) öffnet ein kleines Fenster für eine Zeile wie „Zahnarzt Fr 10 Uhr bei Dr. Weber“;
markierter Text kommt mit. Der Spark zeigt, was er erkannt hat (Termin oder Erinnerung, Tag und Uhrzeit, Ort).
Gespeichert wird erst mit **„Eintragen“**, danach 10 Minuten lang **„Rückgängig“**.
„Milch, Eier auf Einkauf“ legt die Einträge auf diese Liste (Art „Liste“).

### Listen im Begleiter

Im Begleiter-Fenster stehen unter **„Listen“** die Listen mit offenen Einträgen, je mit Zahl und dem neuesten Eintrag
(auch wer ihn ergänzt hat); „Öffnen“ führt zur Seite Listen.

### Nicht stören erkennen

Alle 10 Sekunden schaut der Begleiter, ob ein **anderes** Programm das Mikrofon oder die Kamera benutzt (ein Anruf)
oder ob das Programm vorne ein Fenster über den ganzen Bildschirm zeigt (Präsentation, Vollbild). Dann sagt er dem
Spark nur „Anruf“ bzw. „Präsentation“ – keine Programmnamen. Der Spark hält seine Meldungen so lange zurück und
schickt danach eine Zusammenfassung. In der Menüleiste hat das Gesicht oben links einen kleinen **Mond**.
Das eigene Mikrofon (Diktat, Weckwort, Besprechung) zählt nicht; solange das Weckwort hört, erkennt der Begleiter
Anrufe daher nur an der Kamera und am Vollbild.

### Besprechung mitschreiben

Nur auf Klick im Begleiter-Fenster („Besprechung mitschreiben“) oder mit **⌥⌘R**. Beim ersten Mal fragt der
Begleiter: *„Alle Beteiligten müssen einverstanden sein, dass mitgeschrieben wird.“* → **Verstanden, starten**.
Solange es läuft, steht oben rechts eine **rote Leiste** „Besprechung wird mitgeschrieben · mm:ss · Beenden“, die
sich nicht ausblenden lässt (auch über Vollbild-Programmen). Aufgenommen werden das Mikrofon und – mit der Freigabe
**Bildschirmaufnahme** – der Ton des Macs (die anderen im Anruf); ohne diese Freigabe nur das Mikrofon, und die
Leiste sagt das. Alle 30 Sekunden geht ein Stück an den Spark; auf dem Mac wird nichts gespeichert. Höchstens
3 Stunden.

Nach **Beenden** öffnet sich ein Fenster mit der Zusammenfassung (markierbar, **Kopieren**) und den Aufgaben zum
Ankreuzen (keine ist vorab angekreuzt): **Ausgewählte als Erinnerung**, **Aufs reMarkable** (nur wenn im Panel
eingerichtet) und **Schließen**. Diesen Teil muss zusätzlich der Admin freigeben.

### Smart-Home-Knöpfe

Im Begleiter-Fenster gibt es den Abschnitt **„Zuhause“** mit den Knöpfen, die im Panel für dieses Gerät gewählt
sind; Schalter zeigen „an“/„aus“. Verlangt der Spark für einen Knopf ein **Codewort**, fragt der Begleiter danach in
einem Passwortfeld und schickt es nur für diesen einen Druck mit – gespeichert wird es nicht.

### Tagesstart und Feierabend

Morgens beim ersten Aufwachen oder Entsperren des Macs (bzw. beim Start des Begleiters) ab **06:00** kommt ein kurzer
Überblick, abends beim **Sperren des Bildschirms** ab **17:30** die ersten Termine von morgen und offene Aufgaben –
je einmal am Tag, als Mitteilung und im Fenster von „Frag Spark“. An/aus und die Uhrzeiten unter Einstellungen →
„Tagesstart und Feierabend“ (nur auf diesem Mac); dort zeigt **„Jetzt zeigen“** den Text sofort.

### Zustandspunkt

| Symbol | Bedeutung |
|---|---|
| Gesicht ohne Punkt (in der Farbe der Menüleiste) | Spark erreichbar, alles gut |
| farbiges Gesicht mit **grauem** Punkt | Spark nicht erreichbar (oder noch nicht gekoppelt) – der Begleiter versucht es beim nächsten Abruf wieder |
| farbiges Gesicht mit **rotem** Punkt | Notaus oder Mein Notaus ist an |
| farbiges Gesicht mit **blauviolettem** Punkt | eine neue Version ist da (siehe „Updates“) |
| farbiges Gesicht mit **türkisem Ring** | das Weckwort hört zu |
| kleiner **Mond** oben links | „Nicht stören erkennen“: Anruf oder Präsentation erkannt, Meldungen warten |
| rotes Mikrofon | Aufnahme läuft (Diktat oder Besprechung) |

Im Fenster hinter dem Gesicht steht der Zustand auch in Worten.

### Mein-Notaus-Knopf

Klick aufs Gesicht → unten **„Notaus …“**, nach einer Rückfrage. Danach hält der Spark für das eigene Profil an, und
auch der Begleiter bekommt keine Antworten mehr (Symbol rot). **Aufheben geht nur im Panel im Browser mit der PIN** –
dafür gibt es „Panel öffnen“.

## Office-Add-ins

Teil „Office-Add-ins“ (im Panel pro Gerät, aus). Im Menü dann **Office-Add-ins einrichten**; der Begleiter fragt
vorher. **Word und Excel** bekommen den Knopf „Spark Schreibhilfe“ (Datei im Ordner `wef` der Programme). Für
**Outlook** zeigt er `spark-outlook.xml` im Finder und öffnet <https://aka.ms/olksideload>; dort *Aus Datei
hinzufügen* (nur Microsoft 365, Exchange, Outlook.com). Voraussetzung: das Panel einmal über seine https-Adresse
öffnen, unter Ich → Begleiter speichern und „In anderen Programmen“ der Schreibhilfe einschalten. Teil aus: die
Dateien werden wieder entfernt.

## Tastenkürzel

Standard: **⌥⌘S** Schreibhilfe, **⌥⌘A** Frag Spark, **⌥⌘D** Diktieren, **⌥⌘B** Bildschirm fragen, **⌥⌘M** Antwort
entwerfen, **⌥⌘L** Vorlesen, **⌥⌘R** Besprechung mitschreiben. Ändern unter Einstellungen → „Tastenkürzel“:
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
- **Mikrofon**: fragt macOS beim ersten Diktat, beim ersten Mitschreiben einer Besprechung bzw. sobald das Weckwort an
  ist. Später unter Systemeinstellungen →
  Datenschutz & Sicherheit → Mikrofon.
- **Bildschirmaufnahme** (für „Bildschirm fragen“ und für den Ton des Macs beim Mitschreiben einer Besprechung): Systemeinstellungen → Datenschutz & Sicherheit →
  Bildschirm- & Systemaudioaufnahme (bei macOS 13: „Bildschirmaufnahme“) → „Spark-Begleiter“ einschalten. Der
  Begleiter fragt beim ersten ⌥⌘B mit einer Erklärung; danach den Begleiter **einmal beenden und neu starten**.
  Ohne Freigabe nimmt er nichts auf. Neuere macOS-Versionen fragen gelegentlich nach, ob die Freigabe bleiben soll.
- **Automation für Mail** (für „Antwort entwerfen“): macOS fragt beim ersten ⌥⌘M „Spark-Begleiter möchte Mail
  steuern“ → „OK“. Später unter Systemeinstellungen → Datenschutz & Sicherheit → Automation → Spark-Begleiter → Mail.
- **Mitteilungen**: fragt macOS, sobald „Meldungen“, „Knöpfe in Meldungen“, der Ordner „Spark-Wissen“, „Vom Handy
  auf den Mac“, „Termine im Begleiter“, „Post im Begleiter“ oder „Tagesstart und Feierabend“ an ist.
- **Downloads-Ordner** (für „Vom Handy auf den Mac“): macOS fragt bei der ersten Datei.
- **Kamera**: „Nicht stören erkennen“ schaut nur nach, ob ein anderes Programm die Kamera benutzt; der Begleiter
  schaltet sie nie selbst ein.
- Auch Bildschirmaufnahme und Automation muss macOS nach einem **Update** eines nicht von Apple signierten Programms
  eventuell neu zuordnen (siehe oben).

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
5. Passt etwas nicht, kommt **„Update beschädigt (…), nichts geändert.“** mit dem Schritt in Klammern (Größe, Prüfsumme, Auspacken, Kennung oder Version, Signatur), die Datei wird gelöscht, und die alte Version
   läuft einfach weiter. Geht beim Austausch etwas schief, legt das Hilfsskript die alte Version zurück und startet
   sie wieder.

Liegt der Begleiter in einem Ordner, in den er nicht schreiben darf (oder startet macOS ihn aus einem Download-Ordner
an einem versteckten Ort), legt er die geprüfte neue Version in
`~/Library/Application Support/Spark Begleiter/update/bereit/` und zeigt sie im Finder: Begleiter beenden und sie
selbst in „Programme“ ziehen.

**Einstellungen → Über und Update** zeigt die eigene Version, Mac-Typ (Apple-Chip oder Intel), mit welchem Spark er gekoppelt
ist und den Stand der Updates; **„Nach Updates suchen“** fragt den Spark sofort. Ein selbst gebautes Programm ohne
Versionsnummer („Entwicklungsversion“, 0.0.0) bietet nie ein Update an.

Der Begleiter schickt bei jedem Abruf nur seine Versionsnummer und „mac“ mit, damit der Spark die passende Datei
kennt – sonst nichts.

*Hinweis:* Weil das Programm ohne Apple-Zertifikat signiert ist, fragt macOS nach einem Update eventuell neu nach
Bedienungshilfen bzw. dem Schlüsselbund (siehe „Freigaben“).

## Spark unterstützen

Der Spark ist kostenlos. Wer mag, kann dem Entwickler einen Kaffee spendieren: der gelbe Knopf **„☕ Buy me a coffee“**
unter Einstellungen → Über und Update (Abschnitt „Spark unterstützen“). Erst der
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
4. Falls gewünscht: Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen, Mikrofon, Bildschirmaufnahme und Automation den Eintrag
   „Spark-Begleiter“ entfernen, und unter Allgemein → Anmeldeobjekte ebenso. Die eigenen Einstellungen (die
   Tastenkürzel, der Update-Schalter, der Ordner und „Weckwort pausieren“) liegen in `~/Library/Preferences/de.db9979.spark.begleiter.plist`, geladene
   Updates und die Liste des Ordners „Spark-Wissen“ in `~/Library/Application Support/Spark Begleiter/` – beides
   kann weg. Der Ordner `~/Spark-Wissen` selbst bleibt, bis man ihn löscht.

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
