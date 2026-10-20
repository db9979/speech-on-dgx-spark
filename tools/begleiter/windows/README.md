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
| **Rechtsklick auf Dateien** | Explorer-Untermenü „Mit Spark“: Zusammenfassen, Übersetzen, Erklären, Ins Wissen übernehmen | – |
| **Bildschirm fragen** | Bereich am Bildschirm aufziehen, dann erklären lassen, Text herauslesen oder übersetzen | **Strg+Alt+B** |
| **App erkennen** | die Schreibhilfe erfährt, aus welcher *Art* Programm der Text kommt (z. B. Outlook, Browser) | – |
| **Antwort entwerfen** | Antwort auf die offene/markierte Mail in Outlook als Entwurf – wird nie gesendet | **Strg+Alt+M** |
| **Ordner Spark-Wissen** | neue und geänderte Dateien in einem Ordner gehen automatisch ins Wissen | – |
| **Knöpfe in Meldungen** | Meldungen mit **Antworten**, **Später**, **Panel öffnen**; zu „Für dich“ **Erledigt**, **Erinnern**, **Ansehen** | – |
| **Spark darf am PC handeln** | der Spark darf um wenige, fest umrissene Handlungen bitten – jede einzeln mit Rückfrage | – |
| **Weckwort** | auf „Hey Spark“ (Wort aus dem Panel) hören und die Frage beantworten | – |
| **Vorlesen** | markierten Text in der eigenen Stimme des Profils vorlesen | **Strg+Alt+L** |
| **Vom Handy auf den PC** | Text, Links und Dateien, die man am Handy „an den PC“ schickt | – |
| **Termine im Begleiter** | „Als Nächstes“ im Begleiter-Fenster, Hinweis 10 Minuten vor jedem Termin | – |
| **Post im Begleiter** | „Post“ im Begleiter-Fenster: ungelesen und Für dich, dringende Karten mit **Erledigt**/**Erinnern**; wichtige neue Mail als Meldung mit **Antwort entwerfen**, **Gelesen**, **Ansehen** | – |
| **Schnell erfassen** | eine Zeile wie „Zahnarzt Fr 10 Uhr bei Dr. Weber“ als Termin oder Erinnerung; gespeichert erst mit **Eintragen**, danach **Rückgängig** | **Strg+Alt+N** |
| **Listen im Begleiter** | „Listen“ im Begleiter-Fenster: Listen mit offenen Einträgen, Zahl und neuester Eintrag, **Öffnen** führt zur Seite Listen | – |
| **Nicht stören erkennen** | bei Telefonat/Videokonferenz oder Präsentation hält der Spark Meldungen zurück | – |
| **Besprechung mitschreiben** | Mikrofon und Systemton mitschreiben, danach Zusammenfassung und Aufgaben | **Strg+Alt+R** |
| **Smart-Home-Knöpfe** | Knöpfe „Zuhause“ im Begleiter-Fenster (Licht, Szenen, Skripte) | – |
| **Tagesstart und Feierabend** | morgens beim ersten Entsperren ein Überblick, abends beim Sperren der Ausblick auf morgen | – |

Die Teile ab „Rechtsklick auf Dateien“ sind für jedes Gerät **aus**, bis sie im Panel eingeschaltet werden.

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
  mit Gruß („Guten Morgen, Dominik“), Gerät und Zustand als Punkt („alles läuft“), rechts das Zahnrad
  für die **Einstellungen** und ✕. Darunter (falls vorhanden) der Update-Hinweis, dann das Feld
  **„Frag Spark …“** (Enter schickt die Frage ab, der Mikrofon-Knopf fragt per Sprache), die Befehle
  als **Kacheln** mit ihrem Tastenkürzel (Text verbessern, Diktieren, Bildschirm fragen, Vorlesen …)
  und Abschnitte wie im Panel: **Als Nächstes** (Termine), **Meldungen** (mit Anzahl), **Zuhause**
  und **Dieser Rechner** mit Schaltern für Mikrofon und Weckwort und Zeilen für Wissen-Ordner und
  Office-Add-ins. Unten **Panel öffnen** und rechts „Notaus …“ in Rot. Es schließt sich, sobald man
  woanders hinklickt, oder mit **Esc**; mit Tab bzw. ↑/↓ und Enter geht alles auch per Tastatur.
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
Fragt der Spark zurück („Soll ich … eintragen?“) oder wartet ein Vorschlag auf dein Ja, stehen unter der Antwort
Knöpfe: **Ja** und **Nein**, bei „A oder B?“ die beiden Teile und „Anders …“ (setzt nur den Cursor ins Feld). Ein Klick
schickt nur dieses Wort, als hättest du es getippt; entscheiden tut der Spark mit seinen festen Regeln. Hat die Antwort
Termine oder eine Mail gelesen, öffnet **Im Kalender ansehen ↗** bzw. **Mail öffnen ↗** die Seite im Panel. Ist im
Panel „Ablauf und Freigabe zeigen“ an, steht in der Zeile darüber, welche Werkzeuge benutzt wurden und wie lange es
dauerte.

**Diktieren:** **Strg+Alt+D** startet die Aufnahme (unten rechts erscheint eine dunkle Pille „Ich
höre zu“ mit rotem Punkt, Zeit, Pegel und dem Tastenkürzel), **Strg+Alt+D** noch einmal beendet sie
(oder Klick auf die Pille). Der erkannte
Text wird dort eingefügt, wo beim Start der Cursor war. Höchstens 60 Sekunden. Aufgenommen wird nur
in dieser Zeit. Windows muss Desktop-Apps das Mikrofon erlauben (Einstellungen → Datenschutz →
Mikrofon).

**Einsprechen in den Fenstern:** Ist Diktieren an, hat jedes freie Textfeld der Begleiter-Fenster rechts einen
kleinen **Mikrofon-Knopf**: „Antwort entwerfen“ (Stichpunkte, Mail-Text), „Text verbessern“ (Wunsch, Ausgangstext,
Ergebnis) und „Bildschirm fragen“ (Frage). Klick startet, ■ beendet; der erkannte Text kommt an die Schreibmarke
und wird nie ausgeführt. Nicht in Codewort-Feldern.

**Meldungen** erscheinen als Windows-Hinweis. Beim Start werden ältere Meldungen nicht noch einmal
gezeigt.

**Rechtsklick auf Dateien:** Rechtsklick auf eine Datei (PDF, Word, Excel, PowerPoint, ODT, Text,
Markdown, E-Mail .eml, HTML, JPG, PNG, HEIC; höchstens 20 MB) → **Mit Spark** → **Zusammenfassen**,
**Übersetzen** (in die Sprache der Schreibhilfe aus dem Panel), **Erklären** oder **Ins Wissen übernehmen**.
Das Ergebnis erscheint im Fenster „Frag Spark“ (mit **Kopieren**); „Ins Wissen übernehmen“ meldet sich mit
einem Hinweis („… ist jetzt im Wissen“ bzw. „schon im Wissen“). Unter **Windows 11** steht „Mit Spark“ im
klassischen Menü: Rechtsklick → **Weitere Optionen anzeigen** (oder Umschalt+F10 / Umschalt+Rechtsklick).
Das Menü wird nur für das eigene Windows-Konto eingetragen (unter `HKCU\Software\Classes`, ohne
Administratorrechte, ohne Shell-Erweiterung) und nur, solange der Teil an ist; wird er ausgeschaltet,
verschwindet es wieder. Läuft der Begleiter noch nicht, startet ihn der Menüpunkt.

**Bildschirm fragen:** **Strg+Alt+B** dunkelt alle Bildschirme ab; einen Bereich mit der Maus aufziehen
(**Esc** oder Rechtsklick bricht ab). Danach erscheint ein kleines Fenster mit Vorschau, einem Feld für eine
Frage (optional) und den Knöpfen **Erklären** (auch Enter), **Text herauslesen** und **Übersetzen**. Die
Antwort kommt im Fenster „Frag Spark“. Der Ausschnitt wird nur im Speicher verkleinert (lange Seite höchstens
2000 Pixel, höchstens 6 MB) und an den eigenen Spark geschickt – nie auf die Festplatte geschrieben.

**App erkennen:** Ist der Teil an, schickt die Schreibhilfe nur die *Kategorie* des Programms mit, aus dem der
markierte Text kommt: outlook, word, excel, powerpoint, browser (Edge, Chrome, Firefox, Brave, Opera,
Vivaldi), teams, chat (Slack, Discord, WhatsApp, Telegram, Signal), code (VS Code, Visual Studio, IntelliJ,
Notepad++) oder other. Fenstertitel, Dateinamen oder Inhalte anderer Programme gehen nie mit.

**Antwort entwerfen:** Im **klassischen Outlook** eine Mail öffnen oder markieren, **Strg+Alt+M** (oder
Begleiter-Fenster → **Antwort entwerfen**). Ein kleines Fenster zeigt, auf wen geantwortet wird; optional
Stichpunkte eintippen (z. B. „Termin passt, Unterlagen Freitag“), **Entwurf öffnen**. Der Spark schreibt die
Antwort, Outlook öffnet ein Antwortfenster mit dem Text über der Originalmail. **Gesendet wird nie** – das
macht man selbst. Das **neue Outlook** (und andere Mailprogramme) lässt sich nicht steuern: dann vorher den
Text der Mail markieren und Strg+Alt+M drücken (oder ihn im Fenster einfügen); die fertige Antwort liegt
danach in der Zwischenablage – **in die Antwort einfügen (Strg+V)**.
Im Fenster holt **3 Vorschläge** drei kurze Antworten zur Mail; ein Klick übernimmt einen, danach formen
**Kürzer**, **Freundlicher**, **Förmlicher** und **Englisch** ihn um. Gesendet wird auch hier nie.

**Ordner Spark-Wissen:** Beim Einschalten legt der Begleiter `%USERPROFILE%\Spark-Wissen` an (anderer Ordner:
Einstellungen → **Kopplung** → **Ordner wählen …**). Neue oder geänderte Dateien darin (auch in Unterordnern)
gehen nach 10 Sekunden Ruhe ins Wissen des Spark – höchstens 50 am Tag; danach ein Hinweis „n Dateien ins
Wissen übernommen“. Versteckte Dateien, Office-Sperrdateien (`~$…`) und halbe Downloads (`.tmp`, `.part`,
`.crdownload`) werden übersprungen. Welche Dateien schon übernommen sind (Pfad, Größe, Zeit, SHA-256), steht
in `%LOCALAPPDATA%\Spark Begleiter\wissen.json`. Unterordner, die im Panel unter **Ich → Dokumente → Ausgelassene
Ordner** stehen (ein Ordner oder eine Namensregel wie „Archiv“ oder „Alt*“), schaut der Begleiter nicht an und vergisst,
was er von dort geschickt hatte; „Wieder zulassen“ schickt es neu. Zu jeder Datei nennt er ihren Unterordner, die Namen
der Unterordner (nur Namen) gehen alle 10 Minuten ans Panel für den Ordnerbaum. Nach dem Update geht jede schon
übernommene Datei einmal mit ihrem Ordner neu (zählt nicht für die 50 am Tag).

**Knöpfe in Meldungen:** Meldungen mit Knöpfen erscheinen zusätzlich im Begleiter-Fenster (Klick aufs Symbol
oder auf den Hinweis) unter „Meldungen“: **Antworten** öffnet „Frag Spark“ mit der Meldung als Zitat – die
Antwort bezieht sich dann auf diese Meldung; **Später** zeigt sie in einer Stunde noch einmal (solange der
Begleiter läuft); **Panel öffnen** öffnet das Panel im Browser. Die Knöpfe richten sich nach der Art der Meldung,
das Panel legt sie fest (nie der Text der Meldung): eine Frist oder ein Verdacht aus **Für dich** hat **Erledigt**
(markiert die Karte als erledigt), **Erinnern** (Erinnerung am Tag vor der Frist) und **Ansehen** (öffnet E-Mail →
Für dich im Panel). Nennt eine Meldung einen Weg („… unter Ich → Gedächtnis“, „E-Mail → Für dich“), führt „Ansehen“
genau dorthin.

**Spark darf am PC handeln:** Der Spark kann um eine Handlung bitten; der Begleiter fragt **jedes Mal** in
einem Fenster im Vordergrund: „Spark möchte: … Erlauben?“ mit der genauen Beschreibung darunter.
**Nein** ist vorausgewählt, ohne Antwort gilt nach 60 Sekunden „Nein“. Erlaubt sind nur: eine
http-/https-Adresse im Browser öffnen, ein Programm aus der Liste dieses Geräts im Panel starten, die
Medientasten (Wiedergabe/Pause, nächster, vorheriger Titel), Lautstärke (lauter, leiser, stumm), den PC
sperren und eine Nachricht als reinen Text anzeigen. Alles andere lehnt der Begleiter ab. Jede Bitte wird
höchstens einmal ausgeführt. Damit man die Programme im Panel nur auswählen muss, schickt der Begleiter – nur
solange der Teil an ist – beim Start, beim Einschalten und einmal am Tag die Liste der Startmenü-Einträge
(Name und Pfad der Verknüpfung, ohne Deinstallieren-/Hilfe-Einträge, höchstens 600) an den Spark.

**Rechner fernsteuern, Stufe 1:** Dazu kommen feste Befehle: ein freigegebenes Programm nach vorn holen, das
Fenster vorn schließen, minimieren, maximieren oder auf Vollbild (F11) stellen, feste Tasten (Bild ab/auf für
Folien, Leertaste, Eingabe, Esc, Tab, Strg+Z/Y/C/V/S/F, F5), Text tippen (nur die eigenen Worte der Person, höchstens
500 Zeichen), einen Ordner öffnen (Dokumente, Downloads, Desktop, Bilder, Musik, Videos, Zuletzt verwendet), Ruhezustand,
Bildschirm aus und Kurzbefehle. Freie Tastenkombinationen (Win+R, Strg+Alt+Entf) gibt es nicht. Im Menü unter
**Am PC handeln einstellen …** legst du fest, welche Arten **ohne Rückfrage** laufen (danach zeigt der Begleiter einen
Hinweis; Seiten, Tippen und Text zeigen fragen immer), und gibst **Kurzbefehle** frei (.ps1, .bat, .cmd, .lnk, .exe;
der Spark kennt nur den Namen). Beides geht nur hier am PC, nie aus dem Panel. „Künftig ohne Rückfrage“ lässt sich
auch direkt in der Rückfrage anhaken. Bitten kommen sofort an: der Begleiter wartet mit `GET /api/desk/wait` auf sie.

**Rechner fernsteuern, Stufe 2: Bildschirm zeigen und bedienen** (Teil `view`, Admin-Schalter `chat.desk_view`):
Tippt man im Panel unter Ich → Begleiter „Bildschirm ansehen“ oder „Bedienen“, fragt der Begleiter hier: **Ablehnen**
(vorgewählt), **Nur ansehen** oder **Erlauben** (nur bei „Bedienen“); ohne Antwort nach 60 s gilt Ablehnen. Danach
zeigt er einen roten Rahmen und oben eine Leiste mit **Beenden**, schickt bis zu vier JPEG-Bilder je Sekunde vom
Hauptbildschirm (höchstens 1600 Pixel breit, nur im Speicher) und führt nach „Erlauben“ Klicks, Mausbewegungen,
Scrollen, feste Tasten (`ActDo.ViewKeys`, keine Windows-Taste, kein Alt+Tab) und getippten Text aus. Beenden auch im
Menü (**Bildschirm-Sitzung beenden**) und mit Mein Notaus. Die Anfrage kommt mit `GET /api/desk/wait`.

**Rechner fernsteuern, Stufe 3: Spark bedient den Rechner** (Admin-Schalter `chat.desk_operate`, Teile `act` und
`view`): Sagt man „Spark, schreib in Outlook an Anna …“, kommt dieselbe Anfrage mit dem Auftrag; Ablehnen ist
vorgewählt. Danach bekommt der Begleiter einen Schritt nach dem anderen (`"t":"step"`: Klick, Doppelklick,
Rechtsklick, Scrollen, feste Taste, Text) und zeigt jeden mit rot markiertem Ziel: **Stopp** (vorgewählt),
**Überspringen** oder **Erlauben**; ohne Antwort nach 60 s gilt Stopp. Erst nach „Erlauben“ holt er das Programm
von vorher wieder nach vorn und führt den Schritt aus, dann meldet er `POST /api/desk/view/step`. Text, der nicht
im Auftrag stand, steht als Warnung darüber; „Spark fragt nach“ (Nein / Weiter) kommt, wenn auf dem Bildschirm etwas
wie eine Anweisung stand. Mit jedem Bild schickt er Name und Pfad des Programms vorn, der Spark prüft es gegen die
freigegebenen. Die Frage ist ein eigenes Fenster (`StepForm`), der rote Ring (`ViewMarker`) klickt durch; beide und die Leiste sind aus den Bildern ausgenommen (`WDA_EXCLUDEFROMCAPTURE`).

**Bildschirm beschreiben** (gleicher Schalter, Teil `view`): Fragt man „Was siehst du auf meinem Mac?“, kommt die
Anfrage mit `want` `look` und der Frage; der Begleiter fragt **Ablehnen** (vorgewählt) oder **Erlauben**, schickt danach
ein Bild, und der Spark beendet die Sitzung selbst. Ältere Begleiter zeigen dafür die gewöhnliche Frage „Bildschirm zeigen“.

**Weckwort:** Ist der Teil an, hört der Begleiter am Standard-Mikrofon mit – sichtbar am **Ring um das
Symbol**. Erst wenn es lauter als das Grundrauschen wird, nimmt er den Satz auf (bis zu einer kurzen Pause,
höchstens 5 Sekunden) und lässt den Spark prüfen, ob das Weckwort darin war; sonst wird nichts geschickt
oder gespeichert. „Hey Spark, wie wird das Wetter?“ → die Antwort erscheint in „Frag Spark“. Nur „Hey Spark“
→ kurzer Ton und die Pille „Ich höre zu“, dann die Frage sprechen (bis zur Pause, höchstens 15 Sekunden).
Im Begleiter-Fenster schaltet der Schalter **Weckwort** unter „Dieser Rechner“ das Zuhören ab (Ring
verschwindet), bis man ihn wieder einschaltet. Während eines Diktats hört das Weckwort nicht mit.

**Vorlesen:** Text markieren, **Strg+Alt+L**. Der Spark liest ihn in der Stimme des Profils vor (höchstens 5000
Zeichen); unten rechts erscheint die Pille „Spark liest vor“ mit **Stop**. **Strg+Alt+L** noch einmal stoppt ebenfalls.
Im Begleiter-Fenster bzw. Menü liest **Zwischenablage vorlesen** den kopierten Text vor. Der Ton wird nur im
Speicher gehalten.

**Antworten vorlesen (Frag Spark):** Ist Vorlesen an, steht oben im Fenster „Frag Spark“ der Knopf **Antworten
vorlesen: …** (Klick schaltet weiter; ebenso unter Einstellungen → **Kopplung**): **nur bei gesprochenen Fragen**
(Standard), **immer** oder **nie**. Gesprochen ist eine Frage, die mit dem Mikrofon-Knopf im Fenster (braucht
Diktieren) oder mit dem Weckwort gestellt wurde; getippte Fragen bleiben still, außer bei „immer“. Die Antwort
läuft über dieselbe Pille „Spark liest vor“ mit **Stop**; eine neue Frage (oder der Mikrofon-Knopf) beendet das
Vorlesen.

**Vom Handy auf den PC:** Was am Handy „an den PC“ geschickt wird, kommt mit der nächsten Abfrage an:
*Text* liegt danach in der Zwischenablage (Hinweis „Vom Spark: Text liegt in der Zwischenablage“); bei einem *Link*
fragt der Begleiter „Link öffnen?“ mit **Öffnen**, **Kopieren** und **Nein** (geöffnet werden nur http- und
https-Links); eine *Datei* (höchstens 20 MB) landet in `Downloads\Vom Spark` – nie wird etwas überschrieben,
gleiche Namen bekommen „(2)“, „(3)“ … Ein Klick auf den Hinweis öffnet den Ordner. Jedes Stück kommt nur einmal
(gemerkt in `%LOCALAPPDATA%\Spark Begleiter\inbox-erledigt.json`).

**Termine im Begleiter:** Im Begleiter-Fenster steht unter **Als Nächstes**, was in den nächsten 24 Stunden
ansteht (Termine mit Ort, Erinnerungen), alle 5 Minuten aufgefrischt. 10 Minuten vor jedem Termin kommt ein
Hinweis mit Titel und Uhrzeit. Meldungen im Begleiter-Fenster bekommen den Knopf **In 20 Min erinnern**. Termine aus
Kalendern, die andere Profile mit dir teilen, tragen den Namen des Profils; ein Klick auf einen Termin öffnet den Tag im
Kalender des Panels.

**Post im Begleiter:** Im Begleiter-Fenster steht unter **Post**, wie viele Mails ungelesen sind und wie viele Karten
in „Für dich“ warten, darunter die bis zu 3 dringenden Karten mit **Erledigt**, **Erinnern** und **Ansehen**; **E-Mail
öffnen** springt ins Panel. Alle 5 Minuten und bei einer neuen Mail aufgefrischt. Eine wichtige neue Mail (von
Kontakten oder Menschen, denen du geschrieben hast; welche, entscheidet der Spark) kommt als Meldung mit **Antwort
entwerfen** (Frag Spark mit der Bitte im Feld, gesendet wird nichts), **Gelesen** (nur mit „Mails ordnen“) und
**Ansehen**. Absender und Betreff sind nur Text.

**Schnell erfassen:** **Strg+Alt+N** (oder Kachel **Erfassen**) öffnet ein kleines Fenster für eine Zeile wie
„Zahnarzt Fr 10 Uhr bei Dr. Weber“; markierter Text kommt mit. Der Spark zeigt, was er erkannt hat (Termin oder
Erinnerung, Tag und Uhrzeit, Ort). Gespeichert wird erst mit **Eintragen**, danach 10 Minuten lang **Rückgängig**.
„Milch, Eier auf Einkauf“ legt die Einträge auf diese Liste (Art **Liste**).

**Listen im Begleiter:** Im Begleiter-Fenster stehen unter **Listen** die Listen mit offenen Einträgen, je mit Zahl und dem
neuesten Eintrag (auch wer ihn ergänzt hat); **Öffnen** führt zur Seite Listen.

**Nicht stören erkennen:** Benutzt ein anderes Programm Mikrofon oder Kamera (Teams, Zoom, Telefon …) oder läuft
eine PowerPoint-Bildschirmpräsentation bzw. ein Vollbildprogramm/der Präsentationsmodus, sagt der Begleiter dem
Spark bei jeder Abfrage „beschäftigt“. Der Spark hält Meldungen so lange zurück und schickt danach eine
Zusammenfassung. Am Symbol erscheint ein kleiner **Mond**. Der Begleiter liest dafür nur, *dass* Mikrofon/Kamera
benutzt werden (Windows-Datenschutzliste), nie *was*; die eigene Aufnahme (Diktieren, Weckwort, Besprechung)
zählt nicht.

**Besprechung mitschreiben:** Im Begleiter-Fenster **Besprechung mitschreiben** oder **Strg+Alt+R**. Beim ersten
Mal fragt der Begleiter: „Alle Beteiligten müssen einverstanden sein, dass mitgeschrieben wird.“ –
**Verstanden, starten**. Solange aufgenommen wird, steht oben auf dem Bildschirm eine rote Pille „Besprechung wird
mitgeschrieben · mm:ss · **Beenden**“, die sich nicht verdecken lässt. Aufgenommen werden das Mikrofon und der
Systemton (was die Lautsprecher/das Headset abspielen, also auch die anderen in Teams/Zoom); geht der Systemton
nicht, sagt der Begleiter Bescheid und schreibt nur das Mikrofon mit. Alle 30 Sekunden geht ein Stück an den
eigenen Spark, auf dem PC bleibt nichts. Höchstens 3 Stunden. Nach **Beenden** (oder Strg+Alt+R) erscheint ein
Fenster mit der Zusammenfassung (**Kopieren**) und den erkannten Aufgaben zum Ankreuzen (keine vorausgewählt):
**Ausgewählte auf die Liste** mit **Liste: … ▾** zum Wählen (Standard „Aufgaben“; „bis“ wird zum Datum des
Eintrags, die Quelle heißt „aus Besprechung“), **Als Erinnerung**, **Aufs reMarkable** (wenn im Panel eingerichtet,
Ordner „Besprechungen“) und **Schließen**. Sind die Listen für das Profil nicht freigegeben, bleibt nur
**Ausgewählte als Erinnerung**. Während der
Besprechung hört das Weckwort nicht mit und Diktieren geht nicht.

**Smart-Home-Knöpfe:** Im Begleiter-Fenster unter **Zuhause** stehen die Knöpfe, die im Panel für dieses Gerät
festgelegt sind: Schalter zeigen „an“/„aus“ (an = farbig), Szenen und Skripte lösen beim Klick aus. Verlangt der
Spark ein **Codewort**, fragt der Begleiter danach (verdeckte Eingabe, wird nicht gespeichert).

**Tagesstart und Feierabend:** Beim ersten Entsperren (oder Start des Begleiters) ab 06:00 kommt einmal am Tag
der Tagesstart, beim Sperren des PCs ab 17:30 einmal der Feierabend (die ersten Termine von morgen und offene
Aufgaben) – als Hinweis und als Text im Fenster „Frag Spark“. Beides lässt sich unter Einstellungen →
**Kopplung** → „Tagesstart und Feierabend“ einzeln ausschalten, die Uhrzeiten sind dort änderbar.

**Mein Notaus:** Menü → **Mein Notaus auslösen …** → bestätigen. Danach ist das ganze Profil am
Spark gesperrt, der Punkt wird rot. Aufheben geht nur im Panel im Browser mit der PIN
(Menü → **Panel öffnen (Notaus aufheben) …**).

Hinweise: Die Zwischenablage wird kurz benutzt und danach wiederhergestellt (Text, RTF, HTML,
Bilder, Dateien; seltene Sonderformate gehen dabei verloren); der kurzzeitige Text landet nicht im
Zwischenablage-Verlauf (Win+V). In Programmen, die als Administrator laufen, kann der Begleiter
nicht kopieren/einfügen.

## Office-Add-ins

Teil „Office-Add-ins“ (im Panel pro Gerät, aus). Im Menü dann **Office-Add-ins einrichten …**; der Begleiter fragt
vorher und trägt alles nur für das eigene Windows-Konto ein (keine Administratorrechte).

- **Outlook classic:** Knopf „Spark“ im Menüband: im Hauptfenster und beim Lesen *Antwort entwerfen* und
  *Übersetzen*, beim Verfassen *Text verbessern* und *Übersetzen*. Geht auch mit iCloud- und IMAP-Konten. Das Add-in
  (`tools/begleiter/outlook-classic`, liegt unter `%LOCALAPPDATA%\SparkBegleiter\Office`) schickt nur ein festes Wort
  an den laufenden Begleiter; ohne laufenden Begleiter sagt es das. Wirkt nach dem nächsten Start von Outlook.
- **Word und Excel:** Knopf „Spark Schreibhilfe“ (das Office-Add-in der Schreibhilfe). Dafür das Panel einmal über
  seine https-Adresse öffnen, unter Ich → Begleiter speichern und „In anderen Programmen“ einschalten.
- **Neues Outlook und Outlook im Web:** der Begleiter zeigt `spark-outlook.xml` im Explorer und öffnet
  <https://aka.ms/olksideload>; dort *Aus Datei hinzufügen* (nur Microsoft 365, Exchange, Outlook.com).

Teil aus oder *Entfernen*: alles wird wieder ausgetragen.

## Updates

Neue Versionen holt der Spark selbst (von GitHub) und merkt sich ihre Prüfsumme. Der Begleiter fragt
**nur seinen eigenen Spark** – nie GitHub oder eine andere Adresse:

1. Bei jeder Abfrage nennt der Begleiter dem Spark seine Version und Bauart (x64 oder ARM64).
2. Hat der Spark eine neuere Version, bekommt das Symbol einen Punkt in der Akzentfarbe und das
   Begleiter-Fenster zeigt „Neue Version … · Geprüft vom Spark · NN MB“ mit **Aktualisieren**.
3. Ist **„Updates automatisch laden, vor dem Installieren fragen“** an (Standard, unter
   Einstellungen → Über und Update), lädt der Begleiter die Datei schon im Hintergrund; dann steht dort
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

**Einstellungen → Über und Update** zeigt Version, Bauart, den gekoppelten Spark und den Update-Zustand;
**Nach Updates suchen** fragt den Spark sofort. Ein selbst gebautes Programm (Version 1.0.0) heißt
dort „Entwicklungsversion“ und bekommt keine Updates angeboten.

## Kaffee

Der Spark ist kostenlos. Wer ihn unterstützen möchte: **☕ Buy me a coffee** unter Einstellungen →
Über und Update (Abschnitt „Spark unterstützen“) öffnet die Seite des Entwicklers bei
buymeacoffee.com im Standardbrowser – nur auf Klick, sonst wird nichts geladen. Die Adresse kann der
Spark vorgeben; angenommen werden nur Adressen der Form `https://buymeacoffee.com/…`.

## Tastenkürzel ändern

Klick aufs Symbol → Zahnrad (**Einstellungen**) → im Seitenmenü **Tastenkürzel** → in das Feld des Teils klicken und die neue
Kombination drücken. Sie muss Strg oder Alt enthalten. Ist sie schon von einem anderen Programm
belegt, steht das daneben und die alte bleibt. **Standard** stellt Strg+Alt+S / A / D / B / M / L / R wieder her.
Ausgeschaltete Teile haben kein aktives Tastenkürzel.

Das Einstellungsfenster hat links ein Seitenmenü wie das Panel: **Übersicht** (Zustand als Satz und
die Liste, welche Teile das Panel eingeschaltet hat; sechs Zeilen, der Rest hinter „Weitere … zeigen“),
**Frag Spark**, **Tastenkürzel**, **Tagesstart**, **Wissen-Ordner** und unter „Gerät“ **Kopplung**
(**Panel öffnen**, **Neu koppeln …**, **Entkoppeln …** in Rot) und **Über und Update**. Seiten von
Teilen, die aus sind, fehlen im Menü.

## Entfernen

1. Rechtsklick aufs Symbol → **Einstellungen …** → **Kopplung** → **Entkoppeln …** (löscht den Schlüssel,
   schaltet „Mit Windows starten“ aus und entfernt das Explorer-Menü „Mit Spark“), dann **Beenden**.
   Wer das vergessen hat: `SparkBegleiter.exe --entfernen` trägt Explorer-Menü und Autostart ebenfalls aus.
2. Im Panel unter Ich → Begleiter das Gerät entfernen.
3. Die .exe löschen und die Ordner `%APPDATA%\Spark Begleiter` und `%LOCALAPPDATA%\Spark Begleiter`
   löschen. Der Ordner `Spark-Wissen` gehört dir und bleibt, bis du ihn selbst löschst.

## Bauen

`dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:Version=1.0.NNN`
(bzw. `-r win-arm64`). Das erledigt `.github/workflows/begleiter-windows.yml` bei jeder Änderung
an `tools/begleiter/windows/`: Die Version kommt aus `app/VERSION` („V01.0.342“ → `1.0.342`), die
Dateien und `begleiter.json` (Version, Größe, SHA-256 je Bauart – das prüft der Spark) landen im
Release `begleiter-windows`. Ohne `-p:Version` ist es Version 1.0.0, eine Entwicklungsversion ohne
Updates.
