# Speech auf DGX Spark

[English](README.md) | **Deutsch**

Version V01.0.81 · Idee: Dominik Bornhäußer

Ein Skript installiert **Qwen3-ASR** (Spracherkennung) und **Qwen3-TTS** (Sprachausgabe) als systemd-Dienste auf einer NVIDIA DGX Spark (GB10). Dazu kommt eine Weboberfläche für Konfiguration und Monitoring. Das Setup läuft neben [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38).

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

Am Ende gibt das Skript die Adresse des Panels, das Passwort und den API-Schlüssel aus. Danach macht es einen Rundlauf-Test: TTS spricht einen Satz (auch gestreamt, mit Zeit bis zum ersten Ton), ASR transkribiert ihn wieder. Alles läuft nativ als systemd-Dienste, ohne Docker.

## Nur die Modelle bereitstellen (ohne Webportal)

Die erste Installation fragt im Terminal, was installiert werden soll:

1. **Komplett:** Modelle, APIs und das Webportal mit dem Assistenten (wie bisher).
2. **Nur die Modelle mit ihren APIs:** für andere Dienste (Open WebUI, eigene Apps, Home Assistant …), ohne Webportal, Passwort und Zertifikat.

Danach fragt sie, welche Modelle es sein sollen (Spracherkennung Qwen3-ASR 1.7B, 0.6B, Parakeet oder keine; Sprachausgabe Qwen3-TTS 0.6B, 1.7B oder keine; VoiceDesign ja oder nein, jeweils mit grob geschätztem Speicherbedarf) und ob die APIs im Netz erreichbar sein sollen oder nur auf der Spark selbst (`127.0.0.1`, z. B. hinter einem eigenen Reverse-Proxy). Ein API-Schlüssel wird immer erzeugt und ist Pflicht. Spätere Aufrufe und Updates fragen nicht noch einmal. Ohne Fragen geht es mit Optionen:

```bash
sudo ./install.sh --mode api --asr 1.7b --tts 0.6b --yes   # nur Modelle, im Netz erreichbar
sudo ./install.sh --mode api --asr parakeet --tts none --local --yes
```

Am Ende stehen Adressen, Schlüssel und fertige `curl`-Beispiele auf dem Bildschirm und in `/etc/speech-spark/connection.txt` (nur für root lesbar). Ohne Portal übernimmt der Befehl `speech-spark` dessen Aufgaben:

| Befehl | Wirkung |
|---|---|
| `sudo speech-spark status` | Dienste, Modelle, freier Speicher, letztes Update |
| `sudo speech-spark info` | Adressen, API-Schlüssel, Beispiele, Werte für Open WebUI |
| `sudo speech-spark key new` | neuer API-Schlüssel (der alte gilt sofort nicht mehr) |
| `sudo speech-spark models` | Modelle neu wählen, gleiche Fragen wie bei der Installation |
| `sudo speech-spark update` | Update wie der Knopf im Portal (`--check` zeigt nur, was neu ist) |
| `sudo speech-spark logs tts -n 100` | letzte Log-Zeilen (asr, tts, asr-engine, tts-engine, tts-design, watch, update, all) |
| `sudo speech-spark panel enable` | Webportal nachrüsten; Modelle und API-Schlüssel bleiben |
| `sudo speech-spark panel disable` | Webportal entfernen; Profile und Daten bleiben auf der Platte |

Den Wächter für hängende Dienste, der sonst im Portal läuft, übernimmt ohne Portal der Dienst `speech-spark-watch` mit denselben Regeln. Nach einem Update spricht die Sprachausgabe einen Satz, und die Spracherkennung muss ihn verstehen; klappt das nicht, spielt das Update die vorige Version wieder ein. Die Selbsttests laufen in beiden Arten vor jedem Update. Das Chat-Modell (qwen38) gehört nicht zu diesem Repo und bleibt davon unberührt. Läuft Open WebUI in Docker auf derselben Spark, müssen die APIs im Netz erreichbar sein (`127.0.0.1` im Container ist der Container selbst).

## Sprach-Chat

Der **Assistent** braucht das Mikrofon, und Browser erlauben das nur über https. Das Panel läuft deshalb zusätzlich auf `https://SPARK:31443` mit einem selbst erstellten Zertifikat; der Browser warnt beim ersten Aufruf einmal. Die LLM-Verbindung steht unter Einstellungen → Assistent (Standard: qwen38 auf `http://127.0.0.1:30001/v1`). Den API-Schlüssel von qwen38 übernimmt der Installer aus `~/.config/qwen38/api-key` des Benutzers, der `sudo ./install.sh` aufruft. Das Nachdenken des Modells ist für den Chat aus, damit die Antwort sofort beginnt. Ein animiertes Assistenten-Gesicht zeigt, ob es zuhört, nachdenkt oder spricht; der Mund folgt der Stimme. Dasselbe Gesicht sitzt auf jedem Reiter unten rechts, so lässt sich von überall im Panel sprechen.

**Startseite und Passwort:** Das Panel öffnet mit dem Assistenten. Monitoring, Einstellungen, Stimmen und Logs brauchen das Panel-Passwort (Knopf „Einstellungen“; die Anmeldung endet nach 7 Tagen ohne Nutzung und verlängert sich, solange sie benutzt wird). „Assistent ohne Passwort“ unter Einstellungen → Sicherheit ist bei neuen Installationen aus: Dann sind Gäste ausgesperrt, Profile melden sich auf der Startseite mit Name und PIN an (Geräte mit Schlüssel laufen weiter), der Admin über „Admin“. Eingeschaltet ist der Assistent für alle im Netz offen, auch ohne Profil. Das Passwort ändert sich unter Einstellungen → Sicherheit. Skripte können weiter HTTP Basic nutzen.

**Auf dem Handy:** Unter 760 Pixel Breite öffnet die Seite mit dem großen Gesicht (antippen = sprechen) und zwei Knöpfen darunter: „Einstellungen“ öffnet das Fenster „Ich“ (oben „Hey Spark“), „Verlauf“ die Messenger-Ansicht. Die passt genau auf den Bildschirm: oben eine schmale Leiste mit Pfeil zurück zum Gesicht, kleinem Gesicht, Status, Profil und Menü, in der Mitte der Verlauf, unten Textfeld und runder Mikrofonknopf (während der Antwort ein Stopp-Knopf). Der Browser merkt sich, welche der beiden Ansichten zuletzt offen war. Das Menü (☰) enthält neues Gespräch, frühere Gespräche, Gesprächs-Einstellungen, Sprache, Hell/Dunkel und für Admins alle Reiter.

**Als App aufs Handy:** `https://SPARK:31443` im Handy-Browser öffnen, Zertifikatswarnung bestätigen, dann im Browser-Menü „Zum Startbildschirm hinzufügen“ (iPhone: Safari → Teilen → „Zum Home-Bildschirm“). Der Assistent startet dann mit eigenem Icon im Vollbild. Mit dem selbst erstellten Zertifikat legt Android eine Verknüpfung statt einer installierten App an; das funktioniert genauso, nur ohne Eintrag in der App-Liste.

**Bessere Spracherkennung:** Die feste Standardsprache (Einstellungen → Spracherkennung, etwa Deutsch) statt „auto“ hilft bei kurzen Sätzen am meisten. Im Feld „Kontext“ stehen Namen und Fachbegriffe, die oft falsch erkannt werden; das Modell bevorzugt sie dann. Das 1.7B-Modell erkennt spürbar genauer als 0.6B und braucht etwa 2–3 GiB mehr Speicher.

**Zweite Erkennung: Parakeet.** Unter Einstellungen → Spracherkennung → „Erkennung“ schaltet der Admin zwischen Qwen3-ASR (Grafikkarte) und Parakeet um ([primeline/parakeet-primeline](https://huggingface.co/primeline/parakeet-primeline), deutsch nachtrainiertes NVIDIA Parakeet TDT 0.6B v3; geladen wird [flozen1981/parakeet-primeline-onnx](https://huggingface.co/flozen1981/parakeet-primeline-onnx), ein ONNX-Export davon in int8, per sherpa-onnx; Idee aus [winidi/dictate](https://github.com/winidi/dictate)). Parakeet läuft auf dem Prozessor, braucht etwa 1 GiB, und die Qwen3-ASR-Engine wird dabei gestoppt. Es kennt keinen Kontext, und ein Stream liefert den ganzen Text auf einmal. Der erste Start lädt etwa 640 MB herunter.

**Gespräch-Komfort:** Der Assistent kennt Datum und Uhrzeit (Zeitzone des Browsers; abschaltbar unter Einstellungen → Assistent). Gespräche bleiben im Browser gespeichert und lassen sich oben im Verlauf wieder öffnen oder löschen. Mit „Live-Transkript“ erscheint der Text schon beim Sprechen; in der Sprechpause liegt die Erkennung meist schon fertig vor, dann entfällt dieser Schritt am Ende.

**Websuche:** Unter Einstellungen → Funktionen „Websuche“ einschalten und unter Einstellungen → Websuche die Adresse deiner SearXNG-Instanz eintragen. Ist in der `settings.yml` von SearXNG unter `search: formats:` auch `json` erlaubt, nutzt das Panel die JSON-Schnittstelle, sonst liest es die normale Ergebnisseite; „Verbindung testen“ zeigt, ob es klappt. Das LLM sucht dann selbst, wenn eine Frage aktuelle Informationen braucht (dafür braucht der LLM-Server Tool-Calling, qwen38 hat es an). Der Assistent sagt kurz „Ich schaue kurz nach“, liest die besten Seiten und zeigt die Quellen unter der Antwort.

**Aktivierungswort „Hey Spark“:** Mit dem Haken unter dem Gespräch lauscht der Assistent dauerhaft. Sagst du „Hey Spark“, hört er zu; „Hey Spark, wie wird das Wetter?“ in einem Zug geht direkt als Frage durch. Der Browser erkennt Sprachpausen, das Wort selbst prüft die Spracherkennung auf dem Spark, es geht nichts ins Internet. Der Bildschirm bleibt dabei an; auf dem Handy die App im Vordergrund lassen.

**Das Fenster „Ich“:** Der Knopf mit deinem Namen (oder „Gast“) oben im Verlauf und das Einstellungs-Symbol unter dem Gesicht öffnen dasselbe Fenster. Links steht eine kurze Liste: Gespräch, und angemeldet Gedächtnis, Protokoll und Sicherheit, dazu je nach eingeschalteten Funktionen Dokumente, Kalender, E-Mail, Smart Home, Stimme, Von selbst und Raum-Modus; als Gast steht dort „Anmelden“. Unter „Gespräch“ liegen Zuhören (bei Stille beenden, Live-Transkript, Ins-Wort-Fallen und wie empfindlich), Antwort (Stimme, nur mit Profil; Sprechtempo, Antwortlänge) und Anzeige. Gäste hören immer die Standardstimme. Angemeldet liegen die Einstellungen im Profil auf dem Spark und gelten auf jedem Gerät, auch für Lautsprecher mit Geräteschlüssel; als Gast nur im Browser. „Hey Spark“ stellt jedes Gerät selbst ein, weil es Mikrofon und Bildschirm wach hält. Die Vorgaben für Gäste und neue Profile stehen unter Einstellungen → Gespräch. Das Sprechtempo ändert die Stimmlage nicht; es wirkt auch für andere Apps, die `speed` an die TTS-API senden (vllm-omni-Backend).

**Eigene Dokumente:** Angemeldete Profile laden im Fenster „Ich“ eigene Dateien hoch (PDF mit Textebene, Word, Text, Markdown, HTML, CSV; je bis 20 MB). Fragt man danach, sucht der Assistent darin und nennt das Dokument unter der Antwort. Die Suche läuft über Stichwörter auf dem Spark, ohne zusätzliches Modell. Gäste können nichts hochladen, und kein Profil sieht die Dokumente eines anderen. Abschaltbar unter Einstellungen → Funktionen.

**Nachrichten im Verlauf:** Fährt man über eine Nachricht (am Handy: antippen), erscheinen ein Papierkorb und bei Antworten ein Lautsprecher. Der Papierkorb löscht die Nachricht, bei einer Frage samt Antwort. Der Lautsprecher liest die Antwort noch einmal vor.

**Timer und Erinnerungen:** „Erinnere mich in 10 Minuten an den Ofen“ oder „Erinnere mich morgen um 8 an den Termin“. Offene Erinnerungen stehen als kleine Chips unter den Schaltern (✕ löscht), „Welche Timer laufen?“ und „Lösch den Ofen-Timer“ gehen auch per Sprache. Wenn es soweit ist, klingelt die Seite, zeigt die Erinnerung im Verlauf und sagt sie an; liegt der Tab im Hintergrund, kommt zusätzlich eine Browser-Benachrichtigung. Das klappt, solange die Seite offen ist. Profile speichern ihre Erinnerungen auf dem Spark (jedes offene Gerät des Profils klingelt), Gäste nur im eigenen Browser. Abschaltbar unter Einstellungen → Funktionen.

**Erinnerungen als Mitteilung** (nur Profile): Im Fenster „Ich“ unter „Gespräch“ schaltet „Erinnerungen auf diesem Gerät → Einschalten“ Push-Mitteilungen ein. Dann kommt eine Erinnerung auch, wenn die Seite zu ist, und nur auf die Geräte dieses Profils. Das braucht https mit gültigem Zertifikat (z. B. hinter einem Reverse-Proxy); auf dem iPhone die Seite zuerst über „Teilen → Zum Home-Bildschirm“ als App anlegen. Der Spark schickt dabei nur an die Push-Dienste der Browser (Apple, Google, Mozilla, Microsoft), verschlüsselt.

**Tagesbriefing als Mitteilung** (nur Profile): Darunter stellt jedes Profil unter „Tagesbriefing als Mitteilung“ eine Uhrzeit ein. Dann kommt jeden Morgen zu dieser Zeit ein kurzes Briefing (Termine, Erinnerungen, ungelesene Mails, eigene Themen) auf alle Geräte des Profils mit eingeschalteten Mitteilungen und steht danach auch im Verlauf. „Aus“ schaltet es ab.

**Tagesbriefing und Kalender:** „Guten Morgen“ oder „Was steht heute an?“, und der Assistent liest die Termine von heute und morgen, die heutigen Erinnerungen und ein paar Sätze zu deinen Themen vor (z. B. „Wetter Berlin“, über deine SearXNG). „Was habe ich am Freitag?“ geht auch. Jedes Profil verbindet im Fenster „Ich“, Reiter Kalender, einen oder mehrere Kalender (bis zu 8); ein Termin, der in zwei Kalendern steht, wird einmal vorgelesen. Jeder ist eine CalDAV-Adresse mit Benutzer und App-Passwort (iCloud: https://caldav.icloud.com mit Apple-ID und app-spezifischem Passwort von appleid.apple.com; Nextcloud: …/remote.php/dav; Radicale …) oder ein Abo-Link mit webcal://, webcals:// oder https:// (Google: „Privatadresse im iCal-Format“, ein öffentlicher iCloud-Kalender). Neue Termine: „Trag Zahnarzt Dienstag 10 Uhr ein“, und der Assistent liest einen Vorschlag vor; erst wenn du im selben Gespräch schlicht mit Ja antwortest, schreibt das Panel selbst ihn in den ersten CalDAV-Kalender (auf Wunsch mit Erinnerung). Abo-Links bleiben nur lesend. Das Passwort bleibt auf dem Spark und wird nie wieder angezeigt. Gäste haben keinen Kalender. Abschaltbar unter Einstellungen → Funktionen.

**E-Mail lesen:** „Hab ich neue Mails?“, „Was schreibt Anna?“, „Lies mir die Mail von der Telekom vor“. Jedes Profil verbindet im Fenster „Ich“, Reiter E-Mail, bis zu 4 Postfächer per IMAP: iCloud (imap.mail.me.com, deine iCloud-Mailadresse und ein neues app-spezifisches Passwort von appleid.apple.com), Gmail (imap.gmail.com, App-Passwort, braucht die Bestätigung in zwei Schritten), GMX und web.de (vorher in deren Einstellungen IMAP erlauben) oder ein anderer IMAP-Server mit TLS. Outlook/Microsoft 365 geht noch nicht (braucht OAuth). Der Assistent liest nur den Posteingang der letzten 30 Tage und ändert nichts: Das Postfach wird schreibgeschützt geöffnet, keine Mail wird gesendet, gelöscht, verschoben oder als gelesen markiert. Er fasst Mails zusammen und liest sie nur auf Bitte wörtlich vor; im Tagesbriefing nennt er die ungelesenen Mails. Mailtext gilt als fremder Inhalt: Hat der Assistent in einer Antwort eine Mail gelesen, kann er in dieser Antwort keine Smart-Home-Geräte schalten, das Gedächtnis nicht ändern, keine Erinnerungen löschen, nicht im Netz suchen und keine Termine eintragen, damit eine präparierte Mail nichts auslösen kann; Antworten aus Mails lernt er nicht ins Gedächtnis. Gäste und eine fremde Stimme an einem anderen Gerät haben keinen Zugriff. Das Passwort liegt verschlüsselt auf dem Spark und wird nie wieder angezeigt. Aus, bis es unter Einstellungen → Funktionen eingeschaltet wird.

**Postfach aufräumen** (Einstellungen → Funktionen → „Postfach aufräumen“, standardmäßig aus; braucht „E-Mail lesen“; nur Profile): Der Spark sortiert Werbung, Newsletter, Rechnungen, Benachrichtigungen und Social-Media-Mails in Ordner unter `Spark/` (z. B. `Spark/Werbung`), damit im Posteingang nur Wichtiges bleibt. Er verschiebt nur, er löscht nie, sendet nie und markiert nichts als gelesen. Kann der Mailserver kein IMAP MOVE (iCloud), kopiert er die Mail in den Zielordner, prüft, dass die Kopie angekommen ist, und entfernt erst dann genau dieses Original aus dem Posteingang (UIDPLUS); andere Mails rührt er dabei nicht an. Jedes Profil wählt im Fenster „Ich“, Reiter „Aufräumen“, für jedes Postfach einzeln: Aus, Vorschau (zeigt nur, was er verschieben würde; zum Start eine Woche empfohlen), Sicher automatisch (verschiebt nur, was eine Regel oder eindeutige Kopfzeilen wie List-Unsubscribe belegen) oder Voll automatisch (auch, wenn das Modell sich zu mindestens 85 % sicher ist). Geprüft werden alle 5, 15 (Standard) oder 60 Minuten nur die neuen Mails. Wer entscheidet, in dieser Reihenfolge: Geschützt bleiben Leute, denen du geschrieben hast (Gesendet-Ordner), Anmelde- und Sicherheitsmails und deine Liste „Immer im Posteingang“; dann deine Regeln (Absender oder @Domain); dann feste Kopfzeilen; erst danach das Sprachmodell, das nur eine Kategorie aus der festen Liste zurückgeben darf und keine Werkzeuge hat. Rechnungen und Benachrichtigungen fragt er vorher nach, ebenso bei unklaren Mails; deine Antwort wird auf Wunsch zur Regel. Legst du eine verschobene Mail zurück in den Posteingang, verschiebt er sie nicht noch einmal und fragt nach. Bremsen: höchstens 200 Mails pro Lauf, und würde ein Lauf mehr als die Hälfte von mindestens 10 neuen Mails verschieben, hält er an und legt alles in die Vorschau. Jede Verschiebung steht 30 Tage im Verlauf und lässt sich zurücknehmen. „Altlasten“ schlägt einmalig vor, was aus den letzten 90 Tagen wohin gehört; verschoben wird erst nach „Verschieben“. Per Sprache: „Räum mein Postfach auf“, „Verschieb alles von Lidl in Werbung“, „Mach das rückgängig“; der Assistent liest einen Vorschlag vor und das Panel führt ihn erst nach deinem schlichten „Ja“ aus. **Antwort-Entwürfe** (pro Postfach einschaltbar): „Schreib Anna, dass ich komme“ legt nach deinem „Ja“ einen Entwurf im Entwürfe-Ordner ab; senden musst du selbst in deiner Mail-App. Gäste und fremde Stimmen haben keinen Zugriff.

**Raum-Modus** (Einstellungen → Funktionen → „Raum-Modus“, standardmäßig aus; nur Profile): Der Schalter „Raum“ unter dem Gesicht lässt den Assistenten an diesem Gerät für eine gewählte Zeit (15 Minuten bis 4 Stunden, endet von selbst) dem Gespräch im Raum zuhören; ein oranger Punkt zeigt es an. In einer Pause hilft er, wenn ein fester Auslöser fiel: eine offene Frage („Wann wurde eigentlich …?“, mit Websuche, im Zweifel nichts), ein Termin („Freitag um 10 zum Zahnarzt“ → „Soll ich das eintragen?“), „kalt“, „zu warm“ oder „zu dunkel“ (die echte Temperatur des Raums aus Home Assistant und das Angebot, die Heizung um ein Grad zu ändern oder das Licht anzumachen) und Einkäufe („Wir brauchen noch Milch“ → Einkaufsliste in Home Assistant). Geändert wird nur nach einem „Ja“, bei Smart Home mit Codewort, wenn eines gesetzt ist. Im Fenster „Ich“ unter „Raum-Modus“ stellt jedes Gerät ein: Dauer, wie viel er sagen darf (nur Fragen, auch Hinweise, auch Kommentare), jede Art einzeln, den Raum des Geräts in Home Assistant und „Nur als Text“ (still im Verlauf statt gesprochen). Das Gehörte bleibt nur fünf Minuten im Arbeitsspeicher des Panels und wird nie gespeichert; Gedächtnis, Mails und frühere Gespräche nutzt der Raum-Modus nicht. Alle im Raum sollten wissen, dass er zuhört.

**Von selbst melden** (Einstellungen → Funktionen → „Von selbst melden“, standardmäßig aus; nur Profile): Jedes Profil schaltet im Fenster „Ich“ unter „Von selbst“ ein, ob und wozu sich der Assistent ungefragt meldet, jede Art einzeln: Termin-Vorlauf („In 20 Minuten: Zahnarzt. Soll ich dich um 9:55 Uhr noch einmal erinnern?“, ein „Ja“ setzt die Erinnerung), eigene Smart-Home-Regeln („Whirlpool über 37,5“, „Bad Fenster ist offen und Regen ist an“, „Waschmaschine Leistung unter 5, mindestens 3 Minuten“; nur lesen, nie schalten), eine kurze Begrüßung mit dem nächsten Termin oder der nächsten Erinnerung, wenn das Gespräch nach mindestens drei Stunden wieder geöffnet wird, höchstens eine Nachfrage am Tag zu einem Vorhaben von gestern, neue Mails von festgelegten Absendern (nur Absender und Betreff) und ein Wetterhinweis für morgen über die Websuche. Dazu Ruhezeit, Höchstzahl pro Tag und „Mitlernen“: „Nicht jetzt“ gibt zwei Stunden Ruhe, „Das interessiert mich nicht“ halbiert, wie oft diese Art kommen darf (zurücksetzbar). Wann sich der Assistent meldet, entscheidet das Panel nach festen Regeln aus echten Daten; wo das Modell formuliert (Nachfrage, Wetter), zählt seine Antwort nur, wenn sie wörtlich aus den Daten zitiert. Ist das Gespräch offen, spricht er die Meldung, sonst kommt sie als Push-Mitteilung. Jede Meldung steht mit Grund im Protokoll.

**Natürlicher Sprecherwechsel** (standardmäßig an, Gesprächs-Einstellungen): In einer kurzen Sprechpause wird die Aufnahme schon erkannt. Ist der Satz fertig, endet dein Zug sofort und genau dieser Text wird die Frage, die Antwort kommt also spürbar früher. Nach „und …“, „weil …“, „ähm“ oder einem Komma wartet der Assistent bis zu 2 s, ob du weitersprichst.

**Jeden Tag neues Gespräch** (standardmäßig an, Gesprächs-Einstellungen → Anzeige): Die erste Frage eines neuen Tages beginnt ein neues Gespräch; die älteren bleiben im Verlauf und lassen sich auswählen und fortsetzen.

**Sprechererkennung** (standardmäßig aus, Einstellungen → Funktionen): Jedes Profil liest im Fenster „Ich“ drei kurze Sätze vor. Erkennt der Assistent danach eine Stimme eindeutig, antwortet er für dieses Profil, mit dessen Gedächtnis, Dokumenten, Erinnerungen und Stimme, auch an einem Gast-Gerät. Im Verlauf steht dann „🎙 Name“ unter der Frage. Spricht an einem Gerät jemand anderes als der Angemeldete, bekommt der Assistent nur diese eine Frage (nicht das Gespräch des Geräts), und der Wortwechsel landet nicht im Verlauf oder Gedächtnis des Angemeldeten. Bei unklarer Stimme bleibt alles, wie es ist. Die Erkennung läuft auf dem Prozessor des Spark (Resemblyzer-Modell, Apache 2.0) und braucht keinen GPU-Speicher. Die Strenge ist einstellbar. Eine Stimme ist kein Passwort: Wer sehr ähnlich klingt oder eine Aufnahme abspielt, kann ein Profil erwischen.

**Profile und Gedächtnis:** Unter Nutzer → Profile und Geräte legt der Admin Profile mit Name und PIN an. Im Gespräch meldet man sich über den Knopf „Gast“ oben im Verlauf mit Name und PIN an. Angemeldet merkt sich der Assistent Dinge dauerhaft, wenn man es ihm sagt („Merk dir, dass ich vegetarisch esse“) oder wenn sie später nützlich sind, und vergisst sie auf Zuruf; im Fenster „Ich“ steht, was er weiß, zum Löschen. Gedächtnis und Gespräche gehören fest zum Profil und liegen auf dem Spark, so erscheint derselbe Verlauf auf jedem Gerät, auf dem man angemeldet ist: Welches Profil fragt, entscheidet nur die Anmeldung (Cookie) oder der Geräteschlüssel, nie das Modell, und Gäste bekommen kein Gedächtnis. Lautsprecher und eigene Programme bekommen unter Nutzer → Profile und Geräte einen Geräteschlüssel, der fest zu einem Profil gehört, und senden ihn als Header `X-Speech-Device` an `/api/chat`. Eine neue PIN meldet alle Browser des Profils ab; ein gelöschtes Profil nimmt sein Gedächtnis und seine Geräte mit. Die Daten liegen auf dem Spark unter `/var/lib/speech-spark/users`, je Profil ein eigener Ordner.

**Home Assistant** (Einstellungen → Funktionen → „Home Assistant“, standardmäßig aus): Jedes Profil verbindet im Fenster „Ich“ unter „Smart Home“ sein eigenes Home Assistant mit Adresse (z. B. `http://homeassistant.local:8123`) und langlebigem Zugriffstoken (Home Assistant: dein Profil → Sicherheit; am besten für einen eigenen Benutzer ohne Admin-Rechte). Danach klappt im Gespräch „Mach das Licht im Wohnzimmer an“ oder „Wie warm ist es im Bad?“. Die Befehle gehen an Home Assistants eigenes Assist (`/api/conversation/process`), daher lässt sich nur schalten, was dort für Assist freigegeben ist (Einstellungen → Sprachassistenten → Freigeben). Geräte, die Assist nicht kennt, schaltet der Assistent direkt über ihren Dienst (z. B. `switch.turn_on`), außer Schlösser, Alarmanlagen und Updates. Mit einem **Codewort** (Fenster „Ich“ → Smart Home) schaltet der Assistent erst, wenn das Codewort in derselben Nachricht steht („Licht aus, Codewort Sonnenblume“); fehlt es, fragt er danach. Das prüft das Panel selbst, nicht das Sprachmodell; das Modell und die gespeicherten Gespräche sehen nur „[Codewort]“, gespeichert wird es verschlüsselt und mit etwas Toleranz für die Spracherkennung verglichen (ein, zwei falsche Buchstaben, „Apollo 13“ = „Apollo dreizehn“). Abfragen brauchen kein Codewort. Außerdem (Ideen aus ha-mcp): Verlauf („Wie warm war es gestern im Bad?“, „Wann ging die Haustür zuletzt auf?“), mehrere Geräte auf einmal („Alle Lichter im Wohnzimmer aus“, jedes einzeln geprüft; ein unbekannter Raum schaltet nie das ganze Haus), fehlertolerante Gerätesuche („Samsong“) und Listen wie die Einkaufsliste (vorlesen, hinzufügen, abhaken; Ändern mit Codewort). Fragen nach Werten, Zuständen, Zonen und wo jemand ist liest der Assistent dagegen direkt (`/api/states`): Er sieht alle Geräte, Sensoren, Zonen und Personen, die der Benutzer des Tokens sehen darf, auch ohne Freigabe. Die Räume (Bereiche) kann Home Assistant nur einem Admin-Token verraten; ohne Admin findet der Assistent Geräte nur über ihren Namen. Nur dieses Profil kann sein Home Assistant nutzen: Gäste nie, und eine per Sprechererkennung erkannte Stimme an einem fremden Gerät auch nicht. Der Token wird vor dem Speichern geprüft, bleibt auf dem Spark (`users/<id>/homeassistant.json`, Rechte 0600) und geht nie zurück an den Browser.

**Gespräche durchsuchen**: Die Lupe neben der Gesprächsauswahl (am Handy im Menü) sucht in allen früheren Gesprächen, mit Profil in denen des Profils, als Gast in denen des Browsers. Ein Klick öffnet das Gespräch an der Stelle.

**Frühere Gespräche** (Einstellungen → Funktionen → „Frühere Gespräche“, standardmäßig an; nur Profile): Der Assistent schlägt nach, worüber ihr früher gesprochen habt („Was hast du mir letzte Woche zum Grill gesagt?“, „Worüber haben wir gestern geredet?“), und sucht dabei nur in den gespeicherten Gesprächen des eigenen Profils. Gespräche, die zehn Minuten ruhen, liest er außerdem einmal im Hintergrund nach, wenn gerade niemand spricht, und übernimmt höchstens drei dauerhafte Fakten pro Gespräch ins Gedächtnis des Profils; im Fenster „Ich“ stehen sie mit „automatisch“ markiert und lassen sich löschen. Jedes Profil kann dieses Lernen in den Gesprächseinstellungen abschalten („Aus Gesprächen lernen“). Einmal pro Woche (oder per „Aufräumen vorschlagen“) schlägt der Assistent vor, doppelte Einträge zusammenzufassen und überholte zu entfernen; erst wenn man den Vorschlag unter Ich → Gedächtnis übernimmt, ändert sich etwas. Mit eingeschalteten Mitteilungen kommt dazu ein Hinweis.

**Aussprache:** Unter Einstellungen → Sprachausgabe → Aussprache steht eine Regel pro Zeile, etwa `DGX = De Ge Ix`. Sie gilt für ganze Wörter und für jede Sprachausgabe, auch aus Open WebUI.

**Ins Wort fallen:** Während der Assistent spricht, hört das Mikrofon weiter zu. Wer etwa eine Viertelsekunde lang redet, unterbricht die Antwort, und das Gesagte wird gleich die nächste Frage. Das hängt an der Echounterdrückung des Browsers; unterbricht sich der Assistent mit lautem Lautsprecher selbst, hilft ein Kopfhörer oder der Haken „Ins Wort fallen“ unter dem Gespräch.

**Eigene Stimme:** Unter Nutzer → Stimmen lässt sich eine Referenz direkt mit dem Mikrofon aufnehmen (den vorgeschlagenen Text vorlesen, etwa 10 Sekunden); das Transkript füllt die Spracherkennung aus. Klonen braucht ein Base-Modell (Einstellungen → Sprachausgabe → Modell `…-Base`), danach die neue Stimme als Standardstimme eintragen. Eine deutsche Referenz klingt im Deutschen deutlich gleichmäßiger als die festen Sprecher, die keine deutschen Muttersprachler sind. Unter Nutzer → Stimmen lassen sich einzelne oder alle eigenen Stimmen als ZIP exportieren (Referenz-Audio und Transkript) und auf diesem oder einem anderen Spark wieder importieren; bei gleichem Namen wird umbenannt, ersetzt oder übersprungen.

## Logs

Alle Speech-Dienste schreiben in ein eigenes Journal (`journalctl --namespace=speech-spark -u 'speech-spark-*'`), das auf 500 MB und 14 Tage begrenzt ist; ältere Einträge löscht journald automatisch. Einstellbar unter Einstellungen → System, wirksam nach dem nächsten Update. Die ständigen Statusabfragen des Panels landen gar nicht erst im Log.

## Aktualisieren

Im Panel unter **System**: Dort steht die installierte Version, und es wird angezeigt, wenn auf GitHub eine neuere liegt (mit der Liste der Änderungen). **Update installieren** holt den neuen Stand und installiert ihn. Einstellungen, Modelle und Stimmen bleiben, das Protokoll läuft live mit. Schon installierte Pakete werden dabei nicht aktualisiert; nachgeladen wird nur, was die neue Version braucht. Bevor die neue Version live geht, läuft der Selbsttest. Schlägt er oder ein Schritt davor fehl (Download, Pakete), bricht das Update ab, und die Dienste laufen unverändert mit der alten Version weiter. Geht nach dem Umschalten etwas schief, spielt `update.sh` die vorige Version wieder ein und sagt das im Protokoll. Während das Update läuft, sperrt ein Fortschrittsfenster das Panel (auch andere Tabs und Handys: der Server nimmt keine Änderungen an, der Assistent antwortet weiter); über den Neustart des Panels verbindet sich die Seite neu und lädt am Ende von selbst. Ist es nach 20 Minuten nicht fertig, gibt es „Neu laden“ und „Update abbrechen“.

Auf der Konsole geht dasselbe mit:

```bash
sudo speech-spark update                       # aktualisieren (oder: sudo /opt/speech-spark/src/update.sh)
sudo /opt/speech-spark/src/update.sh --check   # nur anzeigen, was neu ist
```

Der Installer legt dafür eine eigene Git-Kopie unter `/opt/speech-spark/src` an. Wo du das Repo ursprünglich geklont hast, spielt danach keine Rolle mehr.

**Einmalig für Installationen vor dem Update-Button:** im geklonten Repo `git pull` und `sudo ./install.sh`. Danach geht es per Button.

| Option | Wirkung |
|---|---|
| `--mode full` / `--mode api` | komplett mit Webportal / nur die Modelle mit ihren APIs (siehe oben) |
| `--asr 1.7b\|0.6b\|parakeet\|none`, `--tts 0.6b\|1.7b\|none`, `--voicedesign` | Modelle ohne Rückfrage wählen |
| `--local` / `--network` | APIs nur auf `127.0.0.1` / im ganzen Netz (Standard) |
| `--yes` | nichts fragen; was nicht angegeben ist, bleibt wie es ist (neu: komplett) |
| `--small` | 0.6B-Modelle statt 1.7B (weniger Speicher) |
| `--tts-backend transformers` | TTS ohne Streaming über `qwen-tts` statt vllm-omni (Standard: `vllm-omni`) |
| `--asr-backend transformers` | ASR über `qwen-asr` statt vLLM, eine Anfrage nach der anderen (Standard: `vllm`) |
| `--no-asr` / `--no-tts` | nur einen der beiden Dienste installieren |
| `--password XYZ` | Panel-Passwort setzen (sonst wird eins erzeugt) |
| `--no-download` | Modelle erst beim ersten Start laden |
| `--no-smoke` | Rundlauf-Test am Ende überspringen |
| `--uninstall` | wie `./uninstall.sh` (siehe unten) |

Ein erneuter Aufruf aktualisiert den Code und ergänzt in den Python-Umgebungen, was fehlt; schon installierte Pakete bleiben, wie sie sind. Die bestehende Konfiguration bleibt erhalten, neue Einstellungen werden ergänzt.

## Selbsttest

Jede Installation und jedes Update führt den Selbsttest des Panels aus (`app/tests`), gegen nachgebaute LLM-, TTS- und Home-Assistant-Server in einem Wegwerf-Ordner: Anmeldung und Zugang, dass Profile nie Gedächtnis, Dokumente, Gespräche, Postfächer oder Home Assistant eines anderen sehen, die Werkzeuge im Gespräch, das Lernen aus Gesprächen, Kalender und Textbereinigung. Er läuft, bevor die neue Version live geht. Bei einem Update bricht ein Fehler das Update ab, und die alte Version läuft weiter; bei einer Erstinstallation wird er nur gemeldet. Das Ergebnis steht im Update-Protokoll. Von Hand: `cd /opt/speech-spark/app && sudo /opt/speech-spark/venv-panel/bin/python -m unittest discover -s tests -t .`

## Sicherheit

- **Assistent ohne Passwort**: Bei neuen Installationen aus. Dann erreichen nur Profile (Name und PIN) und Geräte mit Schlüssel den Assistenten. Schalter unter *Einstellungen → Sicherheit*.
- **Sperre bei falschen Versuchen**: Nach 5 falschen Passwörtern oder PINs von einer Adresse (oder 10 für einen Profilnamen oder das Admin-Passwort, egal von wo) wartet das Panel erst 1 Minute, bei jeder weiteren Sperre doppelt so lange, höchstens eine Stunde. Pro Name gibt es außerdem höchstens 30 falsche Versuche am Tag. Adressen, von denen sich jemand schon einmal richtig angemeldet hat, sperrt ein Fremder damit nicht aus. Die Zähler überstehen einen Neustart des Panels.
- **Reverse-Proxy**: Hinter einem Reverse-Proxy im LAN (z. B. Synology) zählt die echte Adresse aus `X-Forwarded-For`, damit ein Ratender nicht alle aussperrt. Unter *Einstellungen → Sicherheit → Adressen des Reverse-Proxys* die Adresse des Proxys eintragen; dann glaubt das Panel diese Angabe nur von dort, sonst von jedem Gerät im Heimnetz.
- **Anmeldungen laufen ab**: Die Admin-Anmeldung nach 7 Tagen ohne Nutzung, eine Profil-Anmeldung nach 90 Tagen; solange sie benutzt wird, verlängert sie sich. Abmelden beendet die Anmeldung auch auf dem Server. Unter *Ich → Sicherheit* meldet „Überall abmelden“ das Profil in allen anderen Browsern ab. Auf https (auch hinter dem Proxy) sind die Cookies `Secure`.
- **Zweiter Anmeldeschritt (Authenticator-App)**: Für den Admin unter *Einstellungen → Sicherheit*, für Profile unter *Ich → Sicherheit*, wenn der Admin es unter *Einstellungen → Funktionen* freigibt (aus bei neuen Installationen; jedes Profil entscheidet selbst). Einrichten per QR-Code, danach fragt die Anmeldung nach dem sechsstelligen Code; dazu 10 Wiederherstellungscodes für ein verlorenes Handy. „Diesem Browser 30 Tage vertrauen“ spart den Code am eigenen Gerät; „Überall abmelden“ (Profil) bzw. „Allen Browsern das Vertrauen entziehen“ (Admin) beendet das. Solange der Admin ihn an hat, geht HTTP Basic nicht mehr, und Passwort ändern, Sicherung wiederherstellen, Geräteschlüssel anlegen oder umhängen und PINs ändern verlangen jedes Mal einen Code. Geräte mit Schlüssel (Lautsprecher, Siri, Pebble, Handy) brauchen keinen Code. Notausgang: Admin `sudo rm /var/lib/speech-spark/state/mfa-admin.json`; ein Profil setzt der Admin unter *Nutzer → Profile* zurück.
- **Fremder Text schaltet nichts**: Hat der Assistent in einer Antwort Webseiten, Kalender, Dokumente oder frühere Gespräche gelesen, kann in dieser Antwort nichts mehr Home Assistant schalten, das Gedächtnis ändern oder Erinnerungen löschen; nach einer E-Mail auch nicht im Netz suchen oder Termine eintragen. Das Panel führt nur Werkzeuge aus, die es dem Modell in diesem Schritt angeboten hat.
- **Websuche**: Ergebnisseiten liest das Panel nur von öffentlichen Adressen, nie aus dem Heimnetz.
- **Termine**: Einen vorgeschlagenen Termin bestätigt nur ein schlichtes „Ja“ im selben Gespräch.
- **Sprechererkennung**: Das Ergebnis der Erkennung gibt es nur für angemeldete Profile und Geräte, und es gilt nur dort. Eine fremde Stimme an einem Gerät bekommt Antworten, ändert aber kein Gedächtnis.
- **Keine Änderungen von fremden Seiten**: Ändernde Anfragen mit Login-Cookie müssen von der Panel-Seite selbst kommen (`Sec-Fetch-Site`/`Origin`). Skripte mit Geräteschlüssel oder HTTP Basic betrifft das nicht.
- **Geheimnisse verschlüsselt**: Kalender- und Mail-Passwörter und Home-Assistant-Tokens liegen verschlüsselt in den Profilordnern; der Schlüssel liegt getrennt in `/var/lib/speech-spark/state/secret.key`.
- **Geräte**: *Nutzer → Profile und Geräte* und *Ich → Sicherheit* zeigen, wann und von wo jeder Geräteschlüssel zuletzt benutzt wurde; ein Klick sperrt ihn.
- **Änderungsprotokoll**: *Übersicht → Logs → Änderungsprotokoll* zeigt Anmeldungen, falsche Versuche, Sperren und jede Änderung mit Zeit, Adresse und wer es war (`/var/lib/speech-spark/state/audit.log`).

## Stabilität

- **Sicherung**: Jeden Tag, vor jedem Update, vor jeder Rückkehr zur vorigen Version und vor jedem Wiederherstellen sichert das Panel Profile (Gedächtnis, Gespräche, Dokumente, Kalender, E-Mail-Konten, Smart Home, Stimmerkennung), geklonte Stimmen, Einstellungen und Panel-Passwort nach `/var/lib/speech-spark/backups`. Getrennt gezählt bleiben die letzten sieben täglichen oder von Hand angelegten und die letzten fünf vor Update, Rückkehr oder Wiederherstellen. Unter *Übersicht → System und Update → Sicherung* lässt sich jede Sicherung laden, wiederherstellen oder löschen, und eine heruntergeladene Datei wiederherstellen. Beim Wiederherstellen prüft das Panel die Einstellungen wie die Einstellungsseite, begrenzt die Größe und tauscht alle Teile oder keinen; vorher wird der jetzige Stand gesichert. Passwörter und Tokens liegen verschlüsselt in der Sicherung, der Schlüssel nicht: Auf einem anderen Spark müssen Kalender- und Mail-Passwörter und Home-Assistant-Tokens neu eingegeben werden.
- **Zurück zur vorigen Version**: Nach einem Update zeigt die Update-Karte „Zurück zur vorigen Version“. Das installiert die Version wieder, die vorher lief (nur Versionen aus dem offiziellen Zweig). Von Hand: `sudo /opt/speech-spark/src/update.sh --to <commit>`.
- **Wächter** (*Einstellungen → System*, standardmäßig an): Startet ASR, TTS oder eine Engine neu, wenn sie 5 Minuten nicht antwortet, 5 Minuten arbeitet, ohne eine Anfrage fertigzustellen, oder 45 Minuten lädt; höchstens dreimal pro Stunde. Jeder Neustart steht oben auf den Admin-Seiten und im Änderungsprotokoll.
- **Funktionsprüfung**: Nach jedem Update (und auf Knopfdruck) antwortet das Sprachmodell einmal, die Sprachausgabe spricht einen Satz und die Spracherkennung muss ihn wieder verstehen. Ein Fehler steht oben auf den Admin-Seiten.
- **Qualitätstest**: Nach jedem Update (wenn die Funktionsprüfung klappt) und auf Knopfdruck (*Übersicht → System und Update → Qualitätstest → Jetzt prüfen*) stellt das Panel dem echten Sprachmodell 20 feste Fragen mit vorbereiteten Werkzeug-Ergebnissen (Termine, Mails, Erinnerungen, Suche, Gedächtnis) und prüft, ob es das richtige Werkzeug nimmt und nur sagt, was im Ergebnis steht. Echte Daten werden dabei weder gelesen noch geändert.
- **Speicherwarnung**: Fällt der freie Speicher unter *Einstellungen → System → Warnen unter* (Standard 10 GiB), zeigt das Panel oben auf jeder Admin-Seite eine Warnung; DGX OS beendet ab etwa 8 GiB Prozesse.

## Deinstallieren

```bash
sudo ./uninstall.sh            # Dienste, Code, venvs und sudoers-Regel entfernen; Konfig, Modelle und Stimmen bleiben
sudo ./uninstall.sh --purge    # zusätzlich Konfig, Modelle, Stimmen und den Benutzer speech löschen
sudo ./uninstall.sh --yes      # ohne Rückfrage
```

dgx-spark-qwen38 wird dabei nicht angefasst.

## Was installiert wird

| Teil | Wo | Port |
|---|---|---|
| ASR-Dienst `speech-spark-asr` (nimmt Anfragen an, reicht sie an die Engine durch) | `/opt/speech-spark/venv-panel` | 31001 |
| ASR-Engine `speech-spark-asr-engine` (vLLM) | `/opt/speech-spark/venv-engine` | 31011, nur lokal |
| TTS-Dienst `speech-spark-tts` (nimmt Anfragen an, reicht sie an die Engine durch) | `/opt/speech-spark/venv-panel` | 31002 |
| TTS-Engine `speech-spark-tts-engine` (vllm-omni) | `/opt/speech-spark/venv-engine` | 31012, nur lokal |
| optional VoiceDesign-Engine `speech-spark-tts-design` | `/opt/speech-spark/venv-engine` | 31013, nur lokal |
| Update `speech-spark-update` (läuft nur auf Knopfdruck) | `/opt/speech-spark/src` | |
| Panel `speech-spark-panel` (nur komplett) | `/opt/speech-spark/venv-panel` | 31080, https 31443 |
| Wächter `speech-spark-watch` (nur ohne Portal) | `/opt/speech-spark/venv-panel` | |
| Befehl `speech-spark` | `/usr/local/bin` | |
| Messskript `speech-spark-bench` | `/usr/local/bin` | |
| Konfiguration | `/etc/speech-spark/config.json`, Installationsart in `mode`, Verbindungsdaten in `connection.txt`, Passwort in `panel.env` (ein im Panel geändertes Passwort liegt als Hash in `/var/lib/speech-spark/state/panel-password` und hat Vorrang) | |
| Modelle, geklonte Stimmen | `/var/lib/speech-spark/hf`, `/var/lib/speech-spark/voices` | |

Alle Dienste laufen als Systembenutzer `speech`. Per sudoers darf das Panel die Speech-Dienste und Engines starten, stoppen und neu starten und das Update anstoßen, sonst nichts.

## Die Oberfläche

Beim ersten Admin-Login führt ein **Einrichtungsassistent** durch Passwort, Sprachmodell (mit Verbindungstest), Stimme (zum Anhören), Profile, Zugang und Funktionen und endet mit der Funktionsprüfung. Erneut starten: *Übersicht → System und Update → Einrichtung erneut starten*.

Das Menü hat fünf Punkte; Übersicht, Nutzer und Einbinden haben oben eine kleine Leiste mit Unterseiten.

- **Assistent**: Sprach-Chat mit dem LLM von dgx-spark-qwen38. Sprechen (oder tippen), die Antwort kommt als Text und gestreamte Sprache, Satz für Satz, während das LLM noch schreibt. Freihändig hört das Panel nach jeder Antwort wieder zu; Leertaste oder „Sprechen“ unterbricht.
- **Übersicht**: *Monitoring* (GPU-Auslastung, freier Unified Memory, Temperatur, CPU mit Verlauf; pro Dienst Status, Anfragen, Latenz, RTF, Start/Stopp/Neustart; die laufende qwen38-Lane), *System und Update* (Version, Update, Qualitätstest, Funktionsprüfung, Sicherung, Leistung messen) und *Logs*.
- **Einstellungen**: links die Unterseiten. Ganz oben *Funktionen*: ein Schalter pro Fähigkeit (Gedächtnis, Frühere Gespräche, Dokumente, Websuche, Erinnerungen, Kalender, Home Assistant, E-Mail, Von selbst melden, Raum-Modus, Sprechererkennung); Details einer Funktion erscheinen erst, wenn sie an ist. Danach Assistent (LLM), Gespräch (Vorgaben), Websuche, Sprachausgabe, Spracherkennung (Qwen3-ASR oder Parakeet), Sicherheit (Assistent ohne Passwort, Passwort, API-Schlüssel, Ports, Adressen des Reverse-Proxys) und System (Speicherschutz, Wächter, Logs). Technisches steht unter „Erweitert“. Jede Unterseite speichert für sich; neu gestartet werden nur die Dienste, deren Einstellungen sich geändert haben.
- **Nutzer**: *Profile und Geräte* sowie *Stimmen* (Referenzaufnahmen zum Klonen, nur mit einem `Base`-TTS-Modell).
- **Einbinden**: *Anleitungen* mit fertigen Werten für Open WebUI, andere OpenAI-kompatible Apps, die Pebble-Uhr, curl und Python, und *Testen* (Audiodatei transkribieren, Text anhören).

Das Panel gibt es auf Deutsch und Englisch; der Knopf oben rechts schaltet um (Standard: Sprache des Browsers).

## APIs (OpenAI-ähnlich)

```bash
# Transkription
curl http://SPARK:31001/v1/audio/transcriptions -F file=@aufnahme.webm -F language=de
# -> {"text": "...", "usage": {"type": "duration", "seconds": 4}, "processing_s": 0.6}

# Sprachausgabe
curl http://SPARK:31002/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Hallo Welt","voice":"ryan","language":"German"}' -o hallo.mp3
```

`GET /health` liefert bei beiden Diensten Status und Zähler, `GET /v1/voices` (TTS) die verfügbaren Stimmen, `GET /v1/models` das geladene Modell.

Die Spracherkennung nimmt alles, was ffmpeg lesen kann (wav, mp3, webm, mp4, ogg …), und lange Aufnahmen. `language` als Code (`de`) oder Name (`German`), ohne Angabe erkennt das Modell die Sprache selbst. `response_format`: `json`, `text` oder `verbose_json` (mit `language` und `duration`, ohne Zeitstempel). Mit `-F stream=true` kommt der Text stückweise als Server-Sent Events im OpenAI-Format (`transcription.chunk`, am Ende `[DONE]`).

### Gestreamte Sprachausgabe

Mit `"stream": true` (und `"response_format": "pcm"`, das ist dann der Standard) kommt die Antwort als Server-Sent Events, sobald die ersten Laute erzeugt sind:

```
event: speech.audio.delta
data: {"type": "speech.audio.delta", "audio": "<base64>", "response_format": "pcm"}
...
event: speech.audio.done
data: {"type": "speech.audio.done", "usage": {...}}
```

`audio` ist PCM, 16 bit, mono, 24 kHz. Bei einem Fehler kommt `speech.audio.error`. Das ist das Format von vllm-omni, der Dienst reicht es unverändert durch.

```bash
curl -N http://SPARK:31002/v1/audio/speech -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"input":"Hallo Welt","voice":"ryan","language":"German","stream":true,"response_format":"pcm"}'
```

**Gleichmäßigere Aussprache:** Qwen würfelt mit `temperature` 0.9 und `top_p` 1.0, dadurch schwanken Tempo und Betonung von Satz zu Satz. Der Server setzt deshalb `temperature` 0.7, `top_p` 0.9 und `seed` 42 (Einstellungen → Sprachausgabe). Pro Anfrage überschreibbar mit denselben Feldern. In Open WebUI „Antwort aufteilen“ auf **Absätze** stellen: Jeder Teil wird einzeln erzeugt, längere Teile klingen zusammenhängender. Standardsprache fest auf „German“ stellen statt „auto“.

**Lachen und Stimmungswechsel:** Das Modell liest Emojis, „haha“, `*lacht*` und Markdown als Hinweise und lacht dann oder wechselt den Ton. Der Server entfernt das vor dem Sprechen (Einstellungen → Sprachausgabe → „Text bereinigen“, Standard an).

**Zu viel Gefühl:** Ausrufezeichen und Ausrufe („Oh“, „Wow“) lassen die Stimme Begeisterung spielen. Mit „Ruhig sprechen lassen“ (Standard an) macht der Server aus „!“ einen Punkt und streicht solche Ausrufe am Satzanfang. Die Standard-Systemanweisung des Sprach-Chats bittet das LLM außerdem um schlichte, ruhige Alltagssprache.

**Zahlen:** Der Server schreibt Zahlen vor dem Sprechen aus, weil das Modell sonst rät. Datum, Uhrzeit, Geldbeträge, Prozent und Kommazahlen werden zu Wörtern („am 06.10.2026 um 9:30 Uhr, 49,90 €“ → „am sechsten Oktober zweitausendsechsundzwanzig um neun Uhr dreißig, neunundvierzig Euro neunzig“), Telefonnummern zu Zweierblöcken. Einstellungen → Sprachausgabe → „Zahlen vorlesen“: als Wörter (Standard), in Zweierblöcken, Ziffer für Ziffer oder unverändert. Funktioniert für Deutsch und Englisch.

**Sprechstil** (wie die Stimme spricht): `"instructions": "ruhig und freundlich, eher langsam"` in der Anfrage. Ohne Angabe gilt die Standard-Anweisung aus Einstellungen → Sprachausgabe. Beispiele: „Begeistert, etwas schneller“, „Sachlich wie eine Nachrichtensprecherin“, „Leise und beruhigend“. Nur die 1.7B-Modelle (CustomVoice, VoiceDesign) werten Anweisungen aus; die 0.6B-Modelle ignorieren sie (laut Qwen-Modellkarte).

**VoiceDesign** (Stimme per Beschreibung): `"task_type": "VoiceDesign"` und `"instructions": "tiefe, ruhige Männerstimme"`. Dafür braucht es ein eigenes Modell. Im Panel unter Einstellungen → Sprachausgabe „VoiceDesign zusätzlich bereitstellen“ einschalten. Das startet eine zweite Engine mit nochmal demselben Speicherbedarf.

Im Panel unter **Testen** spielt „gestreamt“ den Ton schon während der Erzeugung ab und zeigt die Zeit bis zum ersten Ton.

### Allgemein

Die Dienste verhalten sich wie die OpenAI-Audio-API: TTS liefert standardmäßig mp3 (auch wav, flac, opus, pcm), STT versteht `response_format=text`, und die Sprache darf ein ISO-Code wie `de` sein. OpenAI-Stimmnamen wie `alloy` landen bei der Standardstimme. Ist im Panel ein API-Schlüssel gesetzt, müssen Apps `Authorization: Bearer <Schlüssel>` senden.

### Open WebUI

Admin-Panel → Einstellungen → Audio:

| Feld | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | Schlüssel aus dem Panel (Einstellungen → Sicherheit → API-Schlüssel; der Installer setzt immer einen) | dito |
| Modell | beliebig | beliebig |
| Stimme | | z. B. `ryan` |

Läuft Open WebUI in Docker auf derselben Spark, statt `SPARK` entweder die LAN-IP oder `host.docker.internal` nehmen (Container mit `--add-host=host.docker.internal:host-gateway`). Das Panel zeigt diese Werte im Reiter „Einbinden“ zum Kopieren an.

### „Hey Siri, frag Spark“

Ein iPhone-Kurzbefehl schickt die diktierte Frage an `POST /api/siri/ask` (Header `X-Speech-Device` mit
einem Geräteschlüssel deines Profils, Inhalt `{"text": "..."}`) und lässt Siri das Feld `answer`
vorlesen. Geht ohne geöffnete Seite, auch auf der Apple Watch, mit AirPods und mit CarPlay; Nachfragen
innerhalb von 10 Minuten kennen den Zusammenhang, die Fragen eines Tages stehen als Gespräch im Profil.
Schritt für Schritt unter Einbinden → Anleitungen.

### Pebble-Uhr

Die Watch-App „Spark“ (`app/pebble/speech-spark.pbw`, Quellcode in `pebble/`) bringt den Sprach-Chat auf Pebble Time 2 und Core 2 Duo, mit Antwort als Text und über den Lautsprecher der Uhr. Auf Pebble Round 2 kommt die Antwort nur als Text. Sie braucht eine Uhr-Firmware mit Lautsprecher-API (ab etwa v4.9.170).

1. Im Panel unter **Nutzer → Profile und Geräte** beim eigenen Profil ein Gerät „Pebble“ anlegen und den Schlüssel kopieren.
2. Auf dem gekoppelten Handy `http://SPARK:31080/pebble/speech-spark.pbw` laden und mit der Pebble-App öffnen.
3. In der Pebble-App bei „Spark“ die Einstellungen öffnen: Spark-Adresse (`http://SPARK:31080`) und Geräteschlüssel eintragen. Einstellungen und „Start App“ bleiben grau, solange die Pebble-App die Uhr nicht als verbunden sieht (Tab Devices).
4. Auf der Uhr: SELECT fragt (Diktat über das Handy), nochmal SELECT stoppt die Sprache, lang SELECT beginnt ein neues Gespräch. Ein kleines Gesicht oben zeigt, ob Spark zuhört, nachdenkt oder spricht; der Mund folgt der Sprache. Die Uhr-Einstellung Settings → Sounds & Haptics → Volume begrenzt, wie laut die App werden kann.

Das Handy muss die Spark erreichen, zu Hause im WLAN, unterwegs über ein VPN wie Tailscale. Die App nutzt HTTP, weil die Pebble-App dem selbstsignierten Zertifikat nicht vertraut. Auf der Spark laufen dafür `POST /api/watch/ask` und `GET /api/watch/poll`: die Antwort wird wie im Sprach-Chat erzeugt (kurz gehalten), der Ton für den kleinen Lautsprecher verdichtet (leise Silben angehoben, Spitzen weich begrenzt) und als 8-kHz-IMA-ADPCM an die Uhr geschickt.

## Leistung messen

Im Panel unter **Übersicht → System und Update → Leistung messen** oder auf der Konsole:

```bash
sudo speech-spark-bench                 # Zeit bis zum ersten Ton, Tempo einzeln und parallel, Speicher je Dienst
sudo speech-spark-bench --parallel 8    # mehr gleichzeitige Anfragen
sudo speech-spark-bench --audio a.wav   # Spracherkennung mit eigener Aufnahme
```

Die Messung geht über die öffentlichen Ports, misst also das, was Apps sehen. Das letzte Ergebnis steht in `/var/lib/speech-spark/state/bench-latest.json`. Die Speicheranteile der Engines (Konfiguration) sind Startwerte: nach der Messung passend einstellen.

## Neben dgx-spark-qwen38

- **Ports**: qwen38 nutzt 30000 bis 30099 (Engine 30000, Proxy 30001, Bild 30020, Video 30022, Cockpit 30090/30091). Speech nutzt 31001, 31002, 31080 und 31443 (Panel über https); die Engines auf 31011, 31012 und 31013 hören nur auf 127.0.0.1. Das Panel lehnt Ports im Bereich von qwen38 ab, und das Installationsskript bricht ab, wenn ein Port schon belegt ist.
- **Speicher**: Die GB10 hat einen gemeinsamen Pool von 128 GB für CPU und GPU. Die qwen38-Lanes reservieren davon einen festen Anteil: 50 % bei `stock`/`fp8`, 76 % im 1M-Modus und 85 % bei `flash`. Laut qwen38-Doku bleiben bei `flash` im Leerlauf nur ~16,6 GiB frei, und unter ~8 GiB beendet earlyoom von DGX OS Prozesse. Deshalb gilt:
  - Erkennt das Skript eine flash- oder 1M-Lane, wählt es automatisch die 0.6B-Modelle.
  - Bevor ein Dienst sein Modell lädt, prüft er, ob danach noch die Reserve frei bleibt (Standard 10 GiB). Wenn nicht, lädt er nicht und zeigt im Panel `blocked` mit Begründung.
  - Wird der Speicher trotzdem knapp, beendet das System zuerst die Speech-Dienste (`OOMScoreAdjust=900`), nicht die LLM-Lane und nicht sshd.
  - Speech startet nach den qwen38-Lanes, damit diese ihren festen Anteil zuerst belegen.
  - Die Engines starten nacheinander, weil vLLM beim Start den freien Speicher misst und parallele Starts sich gegenseitig den Anteil wegnehmen.
- **Lane-Wechsel**: Wechselst du im Cockpit auf `flash`, bleiben die schon geladenen Speech-Modelle im Speicher. Mit 1.7B-Modellen kann das zu knapp werden. Dann vorher ASR und TTS im Panel stoppen oder auf 0.6B umstellen.
- **GPU-Zeit**: ASR und TTS teilen sich die GPU mit dem LLM. Während einer Transkription oder Sprachausgabe wird das LLM etwas langsamer.

## Warum die Installation so aussieht

- **PyTorch aus dem cu130-Index**: Das aarch64-torch auf PyPI hat kein CUDA. Ein einfaches `pip install qwen-tts` würde also auf der CPU laufen. torch und torchaudio müssen außerdem aus demselben Index kommen, sonst lädt `libtorchaudio.so` nicht.
- **Kein flash-attn**: Es gibt kein ARM-Wheel, und für sm_121 lässt es sich laut Berichten nicht bauen. Beide Modelle laufen stattdessen mit PyTorch-SDPA.
- **Getrennte venvs**: qwen-asr verlangt `transformers==4.57.6`, qwen-tts `transformers==4.57.3`.
- **ASR mit vLLM**: vLLM 0.30 kann Qwen3-ASR selbst, mit `/v1/audio/transcriptions`, Streaming und mehreren Anfragen gleichzeitig. Es läuft in derselben Umgebung wie die TTS-Engine. `qwen-asr[vllm]` wird nicht gebraucht (es würde vllm 0.14 erzwingen).
- **TTS mit vllm-omni**: `qwen-tts` kann nicht stückweise ausgeben. Das Qwen-Team verweist für Streaming auf vllm-omni. vllm 0.30.0 und vllm-omni 0.30.0 haben ARM-Pakete auf PyPI (CUDA 13) und werden nativ in einer eigenen Umgebung installiert, ohne Docker.
- **Engine-Speicher**: vLLM reserviert beim Start einen festen Anteil des *gesamten* Speicherpools, bei TTS pro Stufe (Talker und Code2Wav) getrennt. Die Voreinstellungen (ASR 1.7B 0,06, 0.6B 0,035; TTS 0,04 + 0,025) sind knapp gewählt, damit Speech neben der qwen38-`stock`-Lane Platz findet. Ist ein Anteil zu klein, bricht die Engine beim Start mit „No available memory for the cache blocks“ ab. Dann im Panel den Anteil erhöhen.

## Fehlersuche

| Symptom | Lösung |
|---|---|
| Installer: „torch in venv-… has no CUDA“ | `sudo ./install.sh` erneut ausführen. Hilft das nicht, `/opt/speech-spark/venv-*` löschen und neu installieren. |
| Panel zeigt `blocked` | Zu wenig Speicher neben der laufenden qwen38-Lane. Auf 0.6B umstellen, die Reserve senken (auf eigenes Risiko) oder die große Lane stoppen. |
| Panel zeigt `error` | Fehlertext im Panel und unter Logs ansehen. |
| `no kernel image is available` | Ein Paket wurde ohne Blackwell-Kernel gebaut. Prüfen mit `/opt/speech-spark/venv-asr/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| TTS-Engine startet nicht | Panel → Logs → TTS-Engine. Bei „not enough KV cache“ o. Ä. die Speicheranteile der Engine im Panel erhöhen. Der erste Start lädt das Modell und dauert länger. |
| Update schlägt fehl | Panel → Übersicht → System und Update → Update-Protokoll. Die alte Version läuft weiter oder wird wieder eingespielt; das Protokoll sagt, was passiert ist. |
| Port belegt | Port in `/etc/speech-spark/config.json` ändern und das Skript erneut ausführen. |

Die Speicherschätzungen pro Modell (`MODEL_GIB` in `app/common.py`) sind grobe Annahmen und noch nicht auf einer Spark gemessen. Nach dem ersten Lauf sollten sie mit den Werten aus dem Panel korrigiert werden.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Die Modelle (Qwen3-ASR, Qwen3-TTS) und Pakete (vLLM, vllm-omni, PyTorch) werden bei der Installation geladen und stehen unter ihren eigenen Lizenzen. Dieses Projekt steht in keiner Verbindung zu NVIDIA oder dem Qwen-Team.
