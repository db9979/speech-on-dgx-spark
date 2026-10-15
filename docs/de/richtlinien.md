# Coding-Richtlinie

Gilt für jeden Thread und jeden Menschen, der Code an Speech on DGX Spark ändert. Sie fasst alle Regeln zusammen, die Dominik seit dem 08.10.2026 festgelegt hat; beschlossen am 12.10.2026. Die englische Fassung steht in [docs/en/guidelines.md](../en/guidelines.md), die Sicherheits-Checkliste in [sicherheits-checkliste.md](sicherheits-checkliste.md).

**Die Richtlinie wächst mit:** Wer eine neue allgemeine Regel einführt (neuer Baustein, neues Register, neue Pflicht für jede Funktion), ergänzt sie hier und in der englischen Fassung im selben Commit. `tests/test_richtlinie.py` prüft, dass jeder hier genannte Selbsttest existiert.

**Legende**
- 🧪 Ein Selbsttest erzwingt die Regel (Testname dahinter). Ein Verstoß macht „Tests“ auf GitHub rot, und tars spielt die Version nicht ein.
- 📝 Die Regel ist nur eine Absprache. Kein Test prüft sie.
- ⚠ Noch offen oder nur teilweise gebaut. Siehe Teil 15.

**Quellen**
- **PA**: Projektanweisungen im Claude-Projekt
- **M**: Projekt-Gedächtnis (`[[name]]`)
- **C**: [Sicherheits-Checkliste](sicherheits-checkliste.md)
- **P**: Plan im Projektordner `plaene/` (außerhalb des Repos)
- **D**: `docs/de/technik.md` bzw. `docs/de/sicherheit-und-betrieb.md`
- **T**: Selbsttest in `app/tests/`

---

## 0. Die Grundsätze (Kurzfassung)

1. **Sicherheit nach dem Stand der Technik.** Jede Änderung wird gegen die Sicherheits-Checkliste geprüft, auch gegen ihren Teil „Stand der Technik“.
2. **Alles von außen ist Daten, nie ein Befehl.** Das gilt für Web, Mail, Kalender, Dokumente, Telegram, Geräte und Modellausgaben. Entscheidungen trifft das Panel mit festen Regeln, nie das Modell.
3. **Jede neue Funktion ist standardmäßig aus.** Sie bekommt einen Admin-Schalter. Was der Admin freigibt, geht sofort für jedes Profil; einzelne Profile sperren kann nur der Admin. Profile schalten nichts frei, sie richten nur ihren Teil ein (Konto, Gerät, Ort) und wählen Vorlieben. Neue Profilschalter gibt es nicht mehr (Dominik 2026-10-13, Plan `plaene/freigabe-vereinfachen.md`; die alten fallen im nächsten Schritt weg). **Gäste bekommen nur Frage und Antwort:** keine Funktion, kein Werkzeug, keine persönlichen Daten, keine Einstellungen.
4. **Jeder Endpunkt** hat Anmeldung, Profilbindung, CSRF, Größenlimit und Rate-Limit.
5. **Jede neue Funktion fügt sich überall ein:** Rechte, Weiche, Live, Logs, Hilfe, Englisch, Sicherung und Tests. Die Pflichtliste steht in Teil 1.
6. **Alles, was sich darstellen lässt, steht in der Live-Übersicht.** Dort stehen nur Art, Anzahl und Status, nie Inhalte.
7. **Logs enthalten nur feste Wörter und Zahlen.** Nie Fragen, Antworten, Geheimnisse oder Profilnamen ohne Zustimmung.
8. **Jeder Hinweis mit einem Weg ist ein Sprung-Link, überall** (Panel, Apps, Begleiter, Telegram) und wird bei jeder Umbenennung mitgezogen. Jeder sichtbare Text hat eine englische Fassung, jedes „?“ einen Hilfe-Eintrag.
9. **Für jede Schutzregel gibt es einen Selbsttest.** Tests hängen nicht von der Uhrzeit ab und laufen auch in einer Kopie, die nur `app/` enthält.
10. **Vor jedem Push** über die Push-Warteschlange: wer oben steht, pusht sofort (auch während ein Testlauf läuft), vorher `git pull --rebase`, nächste freie Versionsnummer, Selbsttests grün.
11. **Jede Version** bekommt eine Zeile in CHANGELOG und README, die Details stehen in `docs/de` und `docs/en`. Die README bleibt kurz.
12. **Die Doku ist bei jeder Änderung aktuell** (Dominik 2026-10-13). Jede Änderung zieht im selben Commit Doku, Hilfe und Architektur-Doku mit. Was sich aus dem Code ableiten lässt (Bausteine, Weg einer Anfrage, Speicherorte), wird erzeugt und von einem Selbsttest geprüft, nicht von Hand gepflegt.
13. **Eine Quelle, aufräumen im selben Commit** (Dominik 2026-10-14). Jede Liste, jeder Standardwert, jeder Name und jeder Helfer steht genau einmal; wer etwas ersetzt, löscht das Alte im selben Commit. Siehe Teil 17.

---

## 1. Pflichtliste: Neue Funktion einbinden („Definition of Done“)

Dominik, 2026-10-12: Jede Funktionserweiterung fügt sich genauso in Monitoring, Logging, Weiche und alles andere ein, was nötig ist.

Diese Liste gehört zu jedem Commit, der eine Funktion, ein Werkzeug, einen Dienst, ein Gerät oder einen Kanal hinzufügt oder ändert. Im Ergebnis an Dominik steht kurz, welche Punkte berührt wurden. Nicht zutreffende Punkte bleiben weg.

| # | Bereich | Was zu tun ist | Erzwungen |
|---|---|---|---|
| 1 | **Rechte und Schalter** | Eintrag in `features.py`: Name de/en, Gruppe, Admin-Schalter `chat.*`, `parent`, Ich-Seite und Anleitung (kein neuer Profilschalter, kein Gastzugang zu Funktionen). Admin-Schalter stehen auf **aus**; die wenigen Vorlieben (`pref=`) auf an. Was ausnahmsweise an ausgeliefert wird, steht mit Grund in `features.DEFAULT_ON`. Module fragen nur `features.allowed/admin_on`. Standardwerte stehen nur in `config.default.json`. Ein Schalter, der nur für den Spark gilt, kommt nach `SPARK_ONLY`. | 🧪 test_features, test_richtlinie (DefaultOn) und Aus-Tests pro Funktion |
| 2 | **Gäste und fremde Stimme** | Gäste bekommen nur Frage und Antwort: kein Werkzeug, keine Funktion, nichts Persönliches. Am geteilten Lautsprecher bekommt eine fremde Stimme nur Gastrechte. Eine neue Funktion braucht dafür nichts zu tun: `features.reason` sagt für Gäste immer „guest“, und `chat_turn` bietet Gästen kein Werkzeug an. | 🧪 test_gaeste und je Funktion („never for guests“) |
| 3 | **Endpunkt** | Er braucht eine Anmeldung (`auth`, `browser_profile`, `secret_profile`, …). Ohne Anmeldung steht er mit Grund in `OPEN`. Dazu Größenlimit vor dem Lesen, Rate-Limit-Schlüssel und Zustandsänderungen nur per POST, PUT oder DELETE. Endpunkte mit Code kommen in `stufen.LIST` und bekommen das Schloss in `mfa.js CODE_LOCKS`. Erreicht die App sie, stehen sie in `APP_PATHS`. | 🧪 test_scanner.test_every_route_has_a_login, test_stufen, test_hardening (Body vor dem Lesen abgelehnt) |
| 4 | **Werkzeug fürs Modell** | Das Werkzeug kommt in genau eine Sperrliste: `READS_OUTSIDE`, `HA_READS`, `LOCKED_OUTSIDE` oder `INSIDE`. Zusatzdienste deklarieren es in ihren `offer()`-Sets. Braucht eine Frage zwingend das Werkzeug, kommt sie in `chat.NEED_TOOLS`. Ist es ein Nachschlage-Werkzeug, kommt es in `chat.LOOKUPS` (höchstens 2 pro Frage). | 🧪 test_scanner.test_every_tool_is_sorted |
| 5 | **Weiche** (`intent.py`) | Die neue Absicht oder Gruppe kommt in `intent.GROUPS` mit ihren Wörtern. Dazu Testsätze in `intent_bench.py` (BENCH), auch für jede gemeldete Fehlzuordnung. Gibt es nur ein passendes Werkzeug, wird es Pflicht-Werkzeug (`forced`). Bei einer neuen Gruppe die Seite Funktionen → Weiche prüfen (Liste, Detail, Statistik). | 🧪 test_intent, test_weiche |
| 6 | **Sofortige Rückmeldung** | Jede neue Weiche-Gruppe und jeder neue direkte Panel-Weg bekommt **mindestens 5** Sätze (de und en) in `ack.PHRASES`, zugeordnet in `ack.group_of`. Die Sätze haben keine Ziffern, kein Ja oder Nein und höchstens 60 Zeichen. Alternativ steht die Gruppe mit Grund in `NO_ACK`. | 🧪 test_ack (Coverage, test_plenty_of_variants) |
| 7 | **Live-Übersicht** (`live.py`) | Für ein Werkzeug: Ziel in `live.TOOLS` und Wort in `live.RETURNS`. Ein neues Ziel kommt mit Zone `spark`, `lan` oder `net` in `TARGETS`. Ein neuer Gerätetyp kommt in `live.CLIENT` und `tracelog.CLIENTS`. Ein neuer Kanal kommt in `live._conns`. Was der Spark von selbst tut, läuft über `live.begin(auto=True)` und `live.within`. Hintergrundarbeit läuft über `vorrang.*` mit festem Namen. Neue Wächter- oder Protokoll-Arten kommen in `guard.LIVE_WORDS` oder `LIVE_SKIP`. Ein neues Push-Tag bekommt ein Wort in `push.WHY`. Nicht eingerichtete Ziele werden über `live.unset()` ausgeblendet. | 🧪 test_live (Werkzeuge, Ziele, Clients, guard-Arten), test_dienstwacht (Knoten pro Dienst) |
| 8 | **Logging** | Journal-Zeilen beginnen mit einem festen Bereich (`chat:`, `weiche:`, `mail:`, …). Ein neuer Bereich kommt in `logfilter.AREAS`. Steht ein fester Hinweis zum Fehler fest, kommt er in `logfilter.HINTS`. In die Zeilen kommen nur feste Wörter, Zahlen und Entscheidungen. Ein Profil steht nur als `profiles.log_name(prof)` darin. Ausführliche Zeilen sind `… detail …` hinter der zeitlich begrenzten Diagnose. Wiederholte Ablehnungen werden einmal geloggt, mit dem Zeitpunkt des nächsten Versuchs. | 🧪 test_logfilter, test_richtlinie (JournalNames), test_schonend, test_log_luecken.Structure; 📝 Präfix-Pflicht |
| 9 | **Anfrage-Verlauf** (`tracelog.py`) | Neue Schritte einer Anfrage laufen über `tr.step(...)`, nur mit `SAFE`-Wörtern und Zahlen (höchstens 40 Schritte, höchstens 8 Infos). Ein Werkzeugname erscheint nur, wenn das Werkzeug angeboten war. | 🧪 test_tracelog (SECRET-Test) |
| 10 | **Dienst-Wächter** | Hängt die Funktion an einem eigenen Dienst (LAN oder Internet), bekommt sie eine Probe in `dienstwacht.py` (über netguard, ohne Zugangsdaten, auf eine Adresse, die der Dienst ohne Anmeldung beantwortet: eine Probe darf dort nie als falsche Anmeldung zählen), einen Live-Knoten und einen festen Satz für „Dienst fehlt“. | 🧪 test_dienstwacht |
| 11 | **Verbindungen nach außen** | Nur über `netguard.client(level, origin=…)`. Die Stufen sind PUBLIC, USER und HOME. Die Notaus-Stufen gelten dabei automatisch. Ein Modul, das selbst verbindet (eigener Dienst auf localhost, Sprachmodell, fester Dienst), steht mit Art und Grund in `netguard.DIRECT_OK`; eine Adresse aus Einstellungen oder fremdem Text gehört nie dorthin. | 📝 (C, SSRF); 🧪 test_hardening, test_waechter_umgehung |
| 12 | **Oberfläche** | Nur die Bausteine aus Teil 6 verwenden. Kein Inline-Code. Jeder Text steht in `i18n.js`. Jede Einstellungszeile mit Feld hat einen Hilfe-Eintrag (`sw:`/`me:`). Wo es passt, kommt eine Zeile in die Suche (Strg K, automatisch über die Bausteine) und eine Zeile in `glanceText()` (Auf einen Blick). | 🧪 test_guides.BuildingBlocks, test_bedienung_hilfe, test_scanner (CSP), test_ui_browser |
| 13 | **Anleitung und Hilfe** | Eine Anleitung in `guides.js` mit den 7 Abschnitten (was, brauchst, einrichten, sagen, verlässt das Haus, aus, wenn nicht). Nach Doku-Änderungen `python3 app/panel/hilfe.py --docs` ausführen. Fragen, die gefunden werden sollen, kommen als Fall in `test_hilfe_quality.py`. Passt es, kommt ein Tipp in `tipps.py` (GAPS) und eine Karte in Ich → Heute (`today.py`). | 🧪 test_guides (jeder Schalter hat eine Anleitung), test_hilfe (Index aktuell), test_hilfe_quality (≥ 60 Fragen) |
| 14 | **Hinweise mit Weg** | „Einschalten unter Funktionen → …“ beginnt mit einem Menünamen und nennt die Schritte mit den heutigen Namen. `way.js` macht daraus von selbst einen Link. Das gilt **überall**: in iPhone- und Android-App, Begleiter, Telegram und Push als Link `…/#weg=<Weg>`. Wird eine Seite oder Zeile umbenannt, werden alle Wege im selben Commit mitgezogen. Hinweise ohne Weg bekommen ein Sprungziel: jeder Hinweis oben auf den Admin-Seiten (`health.alerts`) trägt `go` mit einem Weg und zeigt „Ansehen“ (seit V01.0.447). | 🧪 test_sprunglinks (Panel, Hinweise oben); Apps, Begleiter und Telegram: test_sprunglinks.Outside |
| 15 | **Sicherung** | Eine neue Datei in `state/` (Ordner nur aus `common.STATE`) bekommt eine Zeile im Datei-Register `dateien.py`: mit Einstellungen und ihrer Art (`sicherung=`) kommt sie in die Sicherung (`backup.STATE_FILES`), jede andere mit Grund (`lokal=`, `backup.STATE_LOCAL`) bleibt beim Sichern weg. Geheimnisse liegen nur im vault. | 🧪 test_technik.Storage |
| 16 | **Update und Dienste** | Ein neues Modul, das ASR- oder TTS-Dienste importieren, kommt in `app/restart-map`. Ein neues Paket kommt mit Hash in `requirements-panel.lock`. Eine neue systemd-Unit bekommt `MemoryMax=` und `PrivateTmp=yes`. Eine Seite, die ins Panel gehört, kommt in die Static-Allowlist von `panel.py`. | 🧪 test_rauchtest, test_lock, test_hardening |
| 17 | **Admin-Protokoll und Rückgängig** | Admin-Änderungen der Konfiguration laufen über `undo.py` (ohne Geheimnisse). Empfindliche Schalter kommen in `SENSITIVE`. | 📝 |
| 18 | **Apps** | Jede Funktion mit Ich-Seite oder Einstellung ist in jeder App zu erreichen: einstellen, ansehen, löschen (Dominik 2026-10-14). Android zeigt das Panel selbst (WebView, `appview.js` nimmt die Liste des Panels). Die iPhone-App zeigt eine Seite nativ oder öffnet sie unter „Im Panel öffnen“ in der App; die Liste der Seiten kommt aus `features.ME_PAGES` über `/api/features` (`pages`), nie aus einer Liste in Swift oder Kotlin. Eine neue Ich-Seite kommt nach `ME_PAGES` (und `me.js meAll`, `guides.js ME_NAME`); fehlt sie in der App, steht sie mit Grund in `features.APP_SKIP`. Namen und Rechte liest die App aus `/api/features` und `/api/admin/switches`. Jeder neue Text der App bekommt seine englische Fassung in `Localizable.xcstrings`. Panel-Bereiche öffnet der Admin-Schalter für jedes Profil, kein Schalter je Bereich. | 🧪 test_app_gleichstand, test_features.test_swift_keeps_no_list, test_iphone_panel |
| 19 | **Tests** | Für jede Schutzregel ein Selbsttest. Ein Browser-Test für jede neue Seite (320, 390 und 1280 px). Ein Prüfpunkt unten in `pruefung/praxistest-tars-2.md` im Projektordner (A = Admin, P = Profil). | 📝 (Praxistest), siehe Teil 9 |
| 20 | **Doku** | Eine Zeile in CHANGELOG und README (de und en), Details in `docs/de` und `docs/en`. Neue allgemeine Regeln kommen in diese Richtlinie. | 🧪 test_richtlinie (Versions, Guideline), test_changelog |
| 21 | **Sicherheit nach Stand der Technik** | Die Änderung wird gegen den Teil „Stand der Technik“ der Sicherheits-Checkliste geprüft (Kryptografie, Anmeldung, Header, Lieferkette, LLM-Risiken). | 📝 |
| 22 | **Voraussetzungen** | Baut eine Funktion auf einer anderen auf, steht das als `parent` in `features.py` (die Kette entsteht daraus, `features.chain`). Kein eigener Text „schalte erst X ein“: Hinweise nennen fehlende Schalter über `features.missing_text`, die Seite Funktionen bietet die Kette beim Einschalten mit an (`needs.js`) und sagt beim Ausschalten, was mit ausgeht. Eine Einrichtung, die fehlen kann, kommt nach `features.READY`. | 🧪 test_voraussetzungen, test_voraussetzungen_mit_einschalten |
| 23 | **Einstellungs-Assistent** | Jede neue Einstellung in `config.default.json` oder `profiles.SETTINGS` bekommt im selben Commit ihre Einordnung in `berater_katalog.py`: im Katalog (Stufe A–C, P), in `NEVER_KEYS` (D, nie) oder in `OHNE` / `OHNE_PROFIL` (bewusst nicht vorschlagbar). So kann der Assistent sie vorschlagen oder sicher auslassen. | 🧪 test_einstellungs_assistent.test_every_setting_is_classified |
| 24 | **Kopie meiner Daten** | Jede neue Datei unter `users/<id>/` wird im Datei-Register `dateien.py` eingeordnet: mit `bereich=` (darf verschlüsselt in die Kopie an einem Speicherort, `speicher.AREAS`) oder mit `art=` als Grund (`speicher.LOCAL`) (bleibt immer auf dem Spark: Schlüssel, Logins, Einstellungen, Stimmabdruck, Warteschlangen). Lokal zuerst; der Abgleich läuft im Hintergrund über den Wächter. | 🧪 test_speicher |
| 25 | **Verlauf auf allen Geräten** | Ein neuer Kanal, der für ein Profil antwortet, legt Frage und Antwort über `verlauf.keep` ab (eigenes Tagesgespräch wie Siri, Telegram, Uhr, mit „Ein Gespräch für alle Kanäle“ das heutige Hauptgespräch mit Kanal-Zeichen; eine Stimme, die nicht sicher die des Profils ist, nie dorthin), nie über `save_convo` mit einer alten Kopie. Geräte schicken nur neue Nachrichten (`PUT /api/profile/convos` mit `add`), nur Löschen ersetzt die Kopie. Offene Seiten holen Neues über `?since=`. Jede Änderung meldet `profiles` an die Ereignis-Verbindungen (`verlauf.changed`), darin nur Nummer und Geräteart, nie Inhalte. Eine Kopie im Browser nur, wo `offline_here` es erlaubt (vertrauter Browser, Funktion an); jeder andere Browser löscht sie, Abmelden immer. Gäste bekommen keinen Verlauf auf dem Spark. | 🧪 test_verlauf_sync |
| 26 | **Erstellte Dokumente** | Zahlen in einem erstellten Dokument brauchen einen Beleg aus dem Kiwix, den eigenen Dokumenten, den Worten des Nutzers oder den Fakten des Gesprächs (`folien.drop_unbacked`, `folien.check_chart`), sonst fallen sie weg; Diagramme nur mit mindestens 3 belegten, verschiedenen Werten. Symbole nur aus `app/panel/symbole/` (das Modell nennt ein Wort, nie einen Pfad), nichts aus dem Netz. Bilder nur aus dem eigenen Kiwix über `kiwix.picture_of`, mit eigenem Schalter (aus), neu gespeichert über PIL mit Größen- und Pixelgrenze und mit Quelle auf der Folie. Folientypen und Textlänge regelt `folien.py`, nicht das Modell. | 🧪 test_folien |
| 27 | **Werkzeugname** | Jedes neue Werkzeug (fürs Modell, als Panel-Schritt oder über MCP) bekommt im selben Commit einen verständlichen Namen de/en in `werkzeuge.NAMES`, danach `python3 app/panel/werkzeuge.py --js`. Seiten zeigen Werkzeuge nur über `wzName` (Kopien für Threads über `wzFull`, mit dem internen Namen in Klammern), das Panel über `werkzeuge.label`/`full`; nie den internen Namen allein. | 🧪 test_werkzeuge |
| 28 | **Taten** | Jedes Werkzeug, das etwas ändert (schalten, eintragen, senden, erstellen, merken), bekommt in `taten.KIND` seine Art. Nur dann prüft die Handlungs-Prüfung Sätze wie „ist jetzt an“ gegen sein Ergebnis; die Fehlerschleife gilt ohnehin für alle Werkzeuge. Ein Ergebnis, das nicht geklappt hat, beginnt mit einem der festen Wörter aus `taten.FAILED` („Not done“, „Fehler“ …), ein noch zu bestätigender Vorschlag mit „NOT saved yet“ oder „NOT done yet“. | 🧪 test_taten (Werkzeuge mit Art) |
| 29 | **Werkzeug-Abdeckung** | Jede Funktion aus `features.py` steht im selben Commit in `werkzeug_abdeckung.py`: mit ihren Werkzeugen (`TOOLS`), mit der festen Regel des Panels, die sie beantwortet (`RULES`), oder mit dem Grund, warum es nichts zu fragen gibt (`WITHOUT`). Jedes Werkzeug fürs Modell steht in einer Weiche-Gruppe, in `intent.NARROW_KEEP` oder, wenn das Modul es nur auf das eigene Wort der Person anbietet, in `BY_WORD` mit `keep` in seinem `offer()`; sonst wirft die Weiche es beim Eingrenzen weg. Jedes Werkzeug einer Gruppe hat einen typischen Satz in `SENTENCES`, der dorthin führt, und jedes neue Werkzeug wird in einem Selbsttest einmal wirklich ausgeführt. (Dominik 2026-10-13: „überprüfe ob es für alle Dienste und Infos Werkzeuge gibt“) | 🧪 test_werkzeug_abdeckung |
| 30 | **Technik-Doku** | Die Architektur-Doku (`docs/de/architektur.md`, `docs/en/architecture.md`, Panel Zustand → Technik) kommt aus `technik.py`. Ein neues Modul bekommt in `technik.MODULE` seine Gruppe und eine Zeile; eine neue Datei in `state/` oder unter `users/` bekommt genau eine Zeile im Datei-Register `dateien.py` mit Inhalt (de/en), Sicherung, Bereich der Kopie und Schutz (`schutz=` für versiegelt); daraus entstehen `backup.STATE_FILES`/`STATE_LOCAL`, `speicher.AREAS`/`LOCAL` und `technik.INHALT`/`VERSCHLUESSELT`/`USERS_SONST`, keine Liste davon wird von Hand geschrieben. Ändert sich der Weg einer Anfrage, ziehen `KNOTEN`, `KANTEN` und `SCHRITTE` mit. Jeder Kasten hat seine Knoten-Seite in `technik_knoten.SEITEN_DATEN` (Ablauf, Regeln, Zahlen, Code); ändert sich, wie ein Kasten arbeitet, wird seine Seite im selben Commit angepasst. Zahlen stehen als Platzhalter aus dem Code darin, nie abgetippt; der Fingerabdruck `stand` macht den Test rot, sobald sich der beschriebene Code ändert, bis die Seite geprüft ist (Dominik 2026-10-14). Jede Zahl, Code-Zeile und Regeltabelle kennt ihren Schritt: nennt kein Schritttext sie, steht er in `bezug` der Seite (ein Klick markiert die Blase). Danach `python3 app/panel/hilfe.py --docs`. | 🧪 test_technik |
| 31 | **Aufräumen** | Vor einem neuen Helfer, einer Liste, einem Namen oder einer Einstellung suchen, ob es das schon gibt, und das benutzen. Ersetztes und Totes (Schlüssel, Funktionen, Imports, Texte, CSS) im selben Commit löschen. Nie eine Datei aus der Altlastenliste mit mehr Treffern verlassen. Teil 17. | 🧪 test_aufraeumen |

**Kommt mit laufenden Umsetzungen dazu** (gilt, sobald die Version auf main ist; der Thread ergänzt dann diese Tabelle und den Test):

| Bereich | Was dann zu tun ist | Thread |
|---|---|---|
| **Statische Dateien** | Jede statische Route und jede öffentliche Datei antwortet; neue Kurzwege geben den Request weiter. | gilt seit V01.0.442, 🧪 test_statische_routen |
| **Hintergrundmodelle** | Die Anzeige sagt „arbeitet“ nur, solange wirklich gerechnet wird, sonst „Standby“ (geladen oder nicht); Mitnutzen eines laufenden Modells verlängert keine Laufzeit und startet es nie (`docembed.embed(..., keep=False)`); die Stopp-Prüfung läuft auch bei Notaus und nach Fehlern. | gilt seit V01.0.444, 🧪 test_wissen.Worker |

**Geplant, noch nicht freigegeben** (keine Regel): Lesestand für den Verlauf (Plan `verlauf-sync.md`), Rückfrage vor GitHub-Meldungen (Plan `frage-vor-meldung.md`).

---

## 2. Sicherheit

Die vollständige Liste ist die **[Sicherheits-Checkliste](sicherheits-checkliste.md)** (etwa 45 Punkte plus „Stand der Technik“). Sie wird vor jedem Commit durchgegangen, und die Antwort nennt die berührten Punkte (PA, C, M [[secure-coding-rules]]). Jede Änderung wird zusätzlich gegen den aktuellen Stand der Technik geprüft (Dominik 2026-10-12); was dort als „noch nicht erfüllt“ steht, wird beim nächsten Berühren der Stelle nachgezogen.

### 2.1 Zugang
- Für jeden Endpunkt ist festgelegt, wer darf: Gast, Profil im Browser, Geräteschlüssel oder Admin. (C; 🧪 test_scanner)
- Für folgende Dinge braucht es eine Browser-Anmeldung und einen frischen Code (`browser_profile` + `confirm_code`), nie den Geräteschlüssel: Geheimnisse, Adressen, die ein Token bekommen, Codewort, Push-Ziele und Mail-Konten. (C)
  - Einzige Ausnahme: der iPhone-App-Schlüssel mit dem Bereichsschalter (`secret_profile`).
- „Frisch“ heißt: richtiger Code derselben Anmeldung in den letzten 10 Minuten.
  - Wirklich jedes Mal gefragt wird bei `*_fresh` bzw. `fresh=True`. Das sind Passwort, zweiter Schritt, Rollen und Haupt-Admin, Sicherungen, Codewort und Spark-Update aus der App.
  - Admins (Panel-Passwort oder Profil mit Rolle, angemeldet mit dem zweiten Schritt) fragt die Stufe „Bestätigen“ nie, nur „Schutz ändern“ (`core.admin_login`). Admin-Rechte kommen nur aus einer Anmeldung mit zweitem Schritt, nie aus PIN oder Übergabe. Neue Admin-Endpunkte nehmen `core.auth`, eine zweite Admin-Stufe gibt es nicht.
  - Ein Passkey zählt wie ein Code. Code-Abfragen laufen deshalb immer über `confirm_code`, nie über ein eigenes `mfa.verify`.
  - (C; 🧪 test_stufen, test_zweiter_schritt, test_passkey)
- Im Browser immer `api()` bzw. `apiTry()` verwenden, nie ein rohes `fetch` an Code-Endpunkte. In der iPhone-App immer `SparkAPI.confirmed`. (C)
- Ändert sich eine Adresse, muss das Token neu eingegeben werden. Zustandsänderungen nie per GET. Schlüssel werden mit `hmac.compare_digest` verglichen. (C)
- Gäste bekommen nur Frage und Antwort: keine Werkzeuge, keine persönlichen Daten, keine Aktionen und keine Fehlertexte, nur Fehlercodes. (C, PA; 🧪 test_gaeste)
- **Geteilte Lautsprecher:** Der Geräteschlüssel allein reicht nicht.
  - Persönliches gibt es nur, wenn die Inhaberstimme in derselben Aufnahme sicher erkannt ist.
  - Wessen Stimme es war, setzt nur das Panel (`request.scope`).
  - Das ist eine feste Regel ohne Schalter. (C, M [[shared-speaker-voice-rule]])
- Rechte prüft immer der Server. Ein ausgeblendeter Reiter heißt nicht „verboten“. (P handy-wie-app)
- Rechteänderungen erreichen offene Seiten ohne Neuladen. Ein Gerät, dessen Funktion aus ist, bekommt 503 und behält seine Kopplung. (🧪 test_rechte_sofort)

### 2.2 Größe und Last
- Body-Limit gilt, bevor gelesen wird. Den Body erst nach der Anmeldung parsen. Uploads mit `read(limit+1)` lesen. (C; 🧪 test_scanner.test_uploads_read_with_a_limit, test_hardening)
- Entpacktes (zip, docx, Sicherung) begrenzen. Audio nur mit 8000 bis 48000 Hz und mit `ffmpeg -t`. ffmpeg und ffprobe nur mit `-protocol_whitelist file,pipe`. (C; 🧪 test_lieferkette)
- Downloads gestreamt und mit Byte-Grenze. Texte für TTS und Chat begrenzt, die letzte Nachricht auf etwa 4000 Zeichen. (C, P Prüfung)
- Rate-Limit pro IP plus globale Semaphore für LLM, ASR und TTS (`guard.limit`, `guard.Slot`). Obergrenzen für Jobs, Werkzeugaufrufe, Suchen und Speicher-Einträge. (C)
- Caches mit Ablauf und Maximalgröße. Schwere Arbeit läuft per `to_thread` mit Budget, nie im Event-Loop. (C; 🧪 test_tempo.OffTheLoop)
- Hintergrundarbeit gibt der Sprache Vorrang: `vorrang.run`, `post`, `in_thread`, `quiet` und `hold`. Höchstens eine Hintergrund-Anfrage gleichzeitig ans Sprachmodell. Das ist eine feste Regel. (M [[vorrang-sprache-plan]]; 🧪 test_vorrang)
- **Wartungspause** (Dominik 2026-10-14): Hintergrundarbeit, die das Sprachmodell fragt, läuft über `vorrang.run`/`post` oder wartet vorher mit `quiet`/`hold(…, model=True)`; so wartet sie auch während einer Wartungspause. Wer das Modell im Vordergrund selbst fragt, prüft vorher `wartung.paused("llm")` und sagt `wartung.sentence` statt auf eine Zeitüberschreitung zu warten. (🧪 test_wartung)

### 2.3 Fremder Text (Prompt-Injection)
- Als fremd gilt: Web, Seiten, Mail, Kalender, Kontakte, Pakete, Dokumente, HA-Zustände, Telegram, im Raum Mitgehörtes und alte Antworten, die daraus gebaut wurden. (C)
- Fremder Text wird als Daten eingepackt (`chat.wrap_outside`). Danach sind Schalten, Gedächtnis, Erinnerungen, Vorschläge, Entwürfe und Hilfe-Karten gesperrt, **auch im nächsten Zug**. Fremder Text wird nie ins Gedächtnis gelernt. (C; 🧪 test_hardening Stage2, test_left_out, test_hilfe)
- Es laufen nur angebotene Werkzeuge. Die Absicht (Weiche) und die Herkunft können nur **einschränken**, nie freigeben. Die Reihenfolge ist Rechte → Sperren → Absicht. (P funktionswahl, hilfe-besser)
- Wer fragt, kommt aus der Anmeldung, nie aus dem Text. (P vorrang-personen)
- Inhalte mit ungeprüftem Absender werden nie als „von DHL“ ausgegeben. (C)
- **Wahrscheinlichkeiten des Modells** (`systemone.py`, qwen38 `/v1/systemone`) sind nur ein Signal: Fragen und Antwortmöglichkeiten stehen fest im Code, der beurteilte Text geht nur als „state“ hin, und das Panel entscheidet mit einer festen Schwelle (Konstante oder Auswahl aus festen Stufen). Unter `systemone.MIN_MASS` Label-Masse gilt eine Antwort als unsicher, dann läuft alles wie ohne. Jeder neue Einsatz bekommt einen Namen in `systemone.USES` und läuft im Hintergrund über `vorrang`. Sicherheit, Rechte, Notaus und die Auswahl bei einer Rückfrage nie über Wahrscheinlichkeiten. (Dominik 2026-10-13; 🧪 test_systemone)

### 2.4 Bestätigen und Handeln
- Pro Profil gibt es genau einen offenen Vorschlag. Er gilt nur für dasselbe Gerät, ein schlichtes „Ja“ und 15 Minuten. (C; 🧪 test_hardening)
- Home Assistant läuft mit einer Allowlist von Domains. Mail wird nie gelöscht. (C)
- Vorschlagskarten (Hilfe, Tipps, Einstellungs-Assistent) schalten nie selbst. Erst der Tipp der Person auf „Übernehmen“ schaltet, mit denselben Prüfungen wie das Formular. Sicherheit wird nie per Karte abgeschwächt, dafür gibt es nur „Zeig mir wo“. (P panel-hilfe, funktionen-entdecken, einstellungs-assistent)

### 2.5 Verbindungen nach außen (SSRF)
- Nur http(s), nur über `netguard`. Loopback, private und link-local Adressen sind gesperrt, außer der Admin erlaubt das Heimnetz. (C)
- Die geprüfte IP wird festgehalten, jede Weiterleitung neu geprüft. Zugangsdaten gehen nur an denselben Origin. Nie ein Rückfall auf http, TLS-Prüfung ist an. (C)

### 2.6 Injektion
- Kein `shell=True`, `eval`, `exec`, `os.system`, `pickle` oder `yaml.load`. (C; 🧪 test_scanner.test_no_dangerous_calls)
- HTML nur über `textContent` oder `esc()` und `data-`-Attribute. Strenge CSP `script-src 'self'`: kein Inline-Skript, keine `on…=`-Handler, Knöpfe über `data-on` bzw. `onAttr`. (C, D; 🧪 test_scanner.test_no_inline_script_for_the_strict_csp, test_csp_is_strict, test_hardening)
  - ⚠ Die allgemeine Regel „Daten nie über innerHTML“ ist nur für einzelne Dateien getestet.
- **Antworten des Modells** zeigt das Panel nur über `md.render` (md.js): Knoten mit `createElement`/`textContent`, nur erlaubte Elemente, keine Bilder, Links nur http(s) zu öffentlichen Adressen (wie netguard), mit `noopener noreferrer`, bei abweichendem Linktext mit Hostname. Geräte ohne Formatierung (Telegram, Siri, Begleiter, reMarkable, Uhr, Lautsprecher-Display) bekommen `textnorm.plain_markdown`, die Stimme immer `textnorm.speech_markdown` (in beiden Sprachdiensten vor `hide_secrets`, unabhängig von `tts.clean_text`); Codeblöcke werden nie gesprochen (`chat.no_code`). Ein neuer Kanal, der Antworten zeigt, wählt eins davon. (Dominik 2026-10-12; 🧪 test_markdown)
- **Jeder Satz einer Antwort kommt nur einmal**, im Chat und in der Stimme. Text der Antwort geht nur über `take()`/`speak()` in `chat.py`; schreibt das Modell schon vor einem Werkzeug-Aufruf Text, zeigt die nächste Runde ihre Sätze erst vollständig und lässt jeden schon gesagten weg (`chat.said_key`, Logs → Anfragen „Wiederholung weggelassen“). Ein neuer Weg, der Text in die Antwort gibt, nutzt diese Stellen. (Dominik 2026-10-12; 🧪 test_answer_never_twice)
- Konfigurationswerte werden beim Speichern, beim Wiederherstellen und in `install.sh` gleich geprüft. IMAP-Werte nur als druckbares ASCII. (C)

### 2.7 Geheimnisse und Logs
- Geheimnisse liegen nur im vault und werden nie zurückgegeben. Nie in Logs oder Fehlertexten, nie `str(e)` mit Token. (C, PA)
- Passwörter, Codes, PINs und Schlüssel werden **nie gesprochen** (`textnorm.hide_secrets`). Das ist eine feste Regel ohne Schalter. (M [[secrets-never-spoken]]; 🧪 test_units.Secrets)
- **Stille wird nie zu Wörtern:** Was die Spracherkennung aus einer Aufnahme ohne Stimme, aus einem typischen Stille-Satz („Untertitel im Auftrag des ZDF“) oder als einzelnes kurzes Wort aus fast stimmloser Aufnahme macht, ist keine Frage (`stille.check` in `/api/test/asr`). Ein neuer Weg, der Aufnahmen in Text verwandelt und weitergibt, nutzt `stille.measure`/`stille.check`. Feste Regel ohne Schalter. (Dominik 2026-10-13; 🧪 test_stille)
- Codewörter gehen nie ans Modell, nie in den Verlauf, die Diagnose oder das Journal. (C)
- Passwörter und Schlüssel werden nur ins Formular getippt, nie in den Chat. (P funktionen-entdecken)

### 2.8 root-Grenze, Update, Lieferkette
- root folgt keinen Symlinks in Ordnern von `speech`. Schreiben nur über `put_file` bzw. `as_svc`. (C; 🧪 test_hardening)
- Pakete mit fester Version und Hash (`--require-hashes`). Nichts aus der Konfiguration landet ungeprüft in einem root-Skript. (C; 🧪 test_lock)
- Sicherheitsheader auf jeder Antwort (X-Frame-Options, nosniff, Referrer-Policy, CSP, Permissions-Policy). (🧪 test_bedienung)
- Rücksprung nur auf die gemerkte vorige Version. Unterschriften scheitern geschlossen. (🧪 test_hardening, test_lieferkette)

---

## 3. Funktionen, Schalter, Rechte

- **Standardmäßig aus:** ein Admin-Schalter; freigegeben gilt es für jedes Profil, nie für Gäste. (PA; 🧪 test_features, test_gaeste und Aus-Tests pro Funktion)
- **Ausnahmen:** Feste Schutzregeln haben gar keinen Schalter, wenn Dominik „nie“ oder „immer“ gesagt hat. Das sind Geheimnisse nie sprechen, Vorrang für Sprache und die Inhaberstimme am Lautsprecher. (M, D)
- **Von selbst geöffnetes Mikrofon:** Öffnet eine Seite, App oder ein Gerät das Mikrofon ohne Tippen oder Weckwort (Ins-Wort-Fallen, Rückfrage-Fenster, Freihändig), sagt die Aufnahme das dem Panel (`opened` an `/api/test/asr`). Dann zählt mit angelerntem Stimmabdruck nur eine bekannte Stimme, und ohne Abdruck muss die Stimme über dem gelernten Raumpegel liegen; Fernseher und fremde Stimmen werden nie eine Frage. Feste Schutzregel ohne Schalter, wie die Stille-Regel. (Dominik 2026-10-13, Anfrage d80a75; 🧪 test_fremdstimme)
- **An ausgeliefert** werden nur reine Schutz- und Stabilitätsfunktionen und die Grundfunktionen von Anfang an. Jede steht mit Grund in `features.DEFAULT_ON` (Dominik 2026-10-12). Ein neuer Wert `true` in `config.default.json` ohne Eintrag dort ist rot. (🧪 test_richtlinie.DefaultOn)
- **Ein Register:** Jede Funktion steht genau einmal in `features.py`. Gespeicherte Schlüssel werden nie umbenannt, das Register übersetzt. Werte liest man nur über `profiles.effective(uid)`. Die Reihenfolge ist Admin-Vorgabe, dann eigene Werte, dann Gerät; Gerätewerte gibt es nur für Ortsabhängiges. (D, P vereinheitlichen; 🧪 test_features)
- **Gesperrt heißt sichtbar:** Gesperrte Zeilen werden grau mit Grund gezeigt („Vom Admin ausgeschaltet“), nicht versteckt. Unter Ich stehen sie gesammelt in einem zugeklappten Kasten. Den Grund liefert `features.reason()`, nie das Modell. (D, P einstellungen-neu)
- **Die Funktionen-Seite bleibt kurz.** Neue Unterfunktionen kommen als Unterschalter (`data-show`) unter ihren Hauptschalter. (M; 🧪 test_ui_browser Höhenbudget)
- **Vorlieben nur für Ungefragtes, an und unter Ich abschaltbar:** Eine Funktion bekommt nur dann eine Profil-Vorliebe (`pref=` in `features.py`), wenn der Spark damit von sich aus etwas tut (melden, ansagen, auf ein Gerät schicken, aufräumen). Die Vorliebe steht von Anfang an auf an, fehlt sie in den Einstellungen, gilt an; sie steht in `profiles.NO_PRESET` und im selben Commit als Schalter auf der Ich-Seite aus `me`. Alles andere hat keinen Profilschalter. (Dominik 2026-10-13; 🧪 test_features)
- **Sperre gilt überall:** Was für ein Profil handelt, fragt `features.allowed`; `features.admin_on` nur an Admin-Seiten oder Spark-weiten Stellen, jede mit Grund in `test_sperre_ueberall.ADMIN_ON_OK`. Eigene Daten ansehen und löschen geht auch gesperrt: Die Löschwege der Funktion lassen DELETE durch, und Ich zeigt an der Stelle der verborgenen Seite eine Karte der Funktion mit „Daten löschen“. Dafür trägt jedes Modul mit eigenen Daten eines Profils Anzahl und Löschen in `features.OWN` ein; was bewusst fehlt, steht mit Grund in `test_eigene_daten.OHNE`. (Dominik 2026-10-13/14; 🧪 test_sperre_ueberall, test_eigene_daten)
- **Rollen:** Logs, Anfragen und Live sehen Panel-Passwort und Profile mit Rolle Admin, der Verwalter nicht. (P anfrage-verfolgen, live-uebersicht)
- Bauen nur nach Dominiks OK. Bei größeren Funktionen erst einen Plan unter `plaene/` mit Bildern, nummerierten Punkten und ★-Empfehlung. (PA, M)

---

## 4. Logging und Diagnose

- Alle Dienste schreiben ins Journal-Namespace `speech-spark` (500 MB, 14 Tage). Ständige Statusabfragen und die Abrufe der Logs-Seite werden nicht geloggt. (D)
- **Format:** `bereich: was | Grund | Zahlen`. Der Bereich ist ein festes Wort vor dem Doppelpunkt. Bereiche, die im Panel filterbar sein sollen, stehen in `logfilter.AREAS`. (D, P logs-darstellung; 📝)
- **Nur feste Wörter, Zahlen und Entscheidungen.** Nie Fragetext, Antworttext, Werkzeug-Argumente, Ergebnisse, Geheimnisse oder Fehlertexte fremder Server. (P anfrage-verfolgen, M; 🧪 test_tracelog, test_hintergrund, test_logfilter)
- **Profilnamen** erscheinen in Journal, Anfragen und Live nur mit Zustimmung des Profils (`trace_name`, `live_names`). Im Journal steht ein Profil nur als `profiles.log_name(prof)`: der Name mit Zustimmung, sonst „Profil“ und das Ende der Kennung. Das Admin-Protokoll (`guard.log`) nennt weiter, wer etwas geändert hat. (Dominik 2026-10-12; 🧪 test_richtlinie.JournalNames)
- **Stufen:** Rot und gelb werden über feste Wortlisten bestimmt (`logfilter.ERR`, `WARN`), bei Webserver-Zeilen nur über den Statuscode. Erwartbare Störungen (Dienst kurz weg, Rate-Limit) sind Warnungen mit „retry in …“, keine Fehler. (D; 🧪 test_logfilter)
- **Ausführliche Diagnose** ist pro Bereich nur zeitlich begrenzt an (15 min, 1 h oder 4 h, nach einem Neustart aus) und schreibt nur `… detail …`-Zeilen mit Zahlen. (D)
- **Jedes Ergebnis einer Aktion steht im Journal.** Was außerhalb des Panels etwas ändert oder anderen etwas sagt (Durchsage, Nachricht, Liste, Erinnerung, Termin, Mail, Mitteilung, Werkzeug, Rechner, eigener Dienst, Gedächtnis), schreibt für jedes Ergebnis eine Zeile: erledigt, abgelehnt (mit festem Grund wie `notaus`, `hourly limit`) oder Fehler (Art der Ausnahme). Jeder Werkzeugaufruf schreibt `chat: tool <name> ok|not ok|not offered | ms`. Ausnahmen im Admin-Protokoll (`guard.QUIET`) sind genaue Pfade, nie ein zu kurzes Präfix: `/api/chat` verschluckte sonst alle `/api/chats/`-Änderungen. (Dominik 2026-10-13; 🧪 test_log_luecken, test_messages.Speakers.test_every_announcement_writes_a_journal_line)
- **Alles Neue kommt ins Log, geprüft von Tests** (Dominik 2026-10-13: „alles neues immer im log mit aufnehmen“): Jede Journal-Zeile beginnt mit einem Wort aus `logfilter.AREAS`, ein neues Wort kommt im selben Commit in einen Bereich (mit Knopf in `logs.js`). Eine Funktion hinter einer Notaus-Sperre (`notaus.stop`, `refuse`, `blocks`) schreibt eine Zeile oder sagt in `ACTION_OK` (Test), woher ihre Zeile kommt. Jede Ausnahme im Admin-Protokoll steht mit Grund in `guard.QUIET_WHY`. Was Live unter Ereignisse zeigt, steht als `ereignis:` auch im Journal, ob Live an ist oder nicht. Keine Zeile zeigt, was jemand gesagt oder geschrieben hat, was ein fremder Server antwortet, oder eine rohe Profil-ID: nur die Länge (`len`) oder `profiles.log_name`; Ausnahmen mit Grund in `CONTENT_OK` (Test). (🧪 test_log_luecken.Structure)
- **Keine Logflut:** Eine wiederholte Ablehnung wird einmal geloggt, mit dem Zeitpunkt des nächsten Versuchs. (🧪 test_schonend.QuieterLogs)
- **Anfrage-Verlauf** (Logs → Anfragen): eine `anfrage:`-Zeile pro Anfrage, Schritte über `tracelog`, höchstens 48 h bzw. 500 Anfragen, nicht in der Sicherung. (M [[anfrage-verfolgen-plan]])
- **Für Dominik:** Logs kommen über Zustand → Logs → Diagnose, „Kopieren für Thread“, bzw. über Logs → Anfragen, nicht über Konsolenbefehle. (M)
- **Nach außen** (GitHub-Meldungen) gilt eine Erlaubnisliste statt einer Sperrliste. Ersetzt wird durch `[PERSON-n]`, `[IP]` usw. Bei einem Leck wird nicht gesendet. (P probleme-melden)
- Fehler-Fingerabdrücke bestehen aus Art, Funktion und Fehlerart, nie aus Wörtern. (P frage-vor-meldung)

---

## 5. Live-Übersicht und Monitoring

- **Regel (PA, Dominik 2026-10-10):** Alles, was sich darstellen lässt, steht unter Zustand → Live und auf dem Monitor `/live`. Das gilt neu und rückwirkend, **im selben Commit wie die Funktion** (Dominik 2026-10-12). Lücken stehen in `live-uebersicht/was-fehlt.md`. (M [[live-monitor-aktuell-halten]]; 🧪 test_live)
- **Nur Art, Anzahl und Status, nie Inhalte.** Externe Ziele nur als Dienst- oder Hostname. Namen nur über `live._who` mit Zustimmung. Nie Passwort- oder Code-Werte. (PA, D; 🧪 test_live.test_request_shows_without_any_text)
- **Nur Eingerichtetes** wird gezeigt (`live.unset`). Proxy-Erkennung zählt nur fürs Bild, nie für Entscheidungen. (M)
- `live.py` hält alles nur im Arbeitsspeicher. Die Admin-Seite fragt jede Sekunde ab. Der Monitor ist nur im Heimnetz, mit Kopplungscode. (M)
  - Der alte Plan nannte SSE; gebaut ist die Abfrage.
- **Dienst-Zustand:** Ein Dienst gilt als weg nach 3 Fehlproben und 3 Minuten, als zurück nach 2 guten Proben. Höchstens eine Meldung je 30 Minuten. Fällt das Internet aus, kommt eine Sammelmeldung. Meldungen bestehen aus festen Sätzen. Gezeigt wird das als Banner `health.alerts`, als Zustand-Karte und als Live-Knoten. (M [[dienst-ausfall-plan]])
- **Hintergrundarbeit** meldet ihren Stand mit festen Gründen (sprache, nacht, tageslimit, pause, …). (P hintergrund-status)

---

## 6. Oberfläche: Layout, Bausteine, Design

- **Design „Klar“** (2026-10-08): Seitenleiste am Rechner, Leiste unten am Handy. Die App-Ansicht beginnt unter 760 px. (M [[panel-design-directions]])
- **Menü** (Stand 2026-10-11): Assistent · Ich | Zustand · Funktionen · Personen und Geräte · Einstellungen, dazu Strg/⌘ K. Die Einstellungsgruppen sind Assistent, Sprache und Spark. (D; 🧪 test_guides.MenuStructure)
- **Seitengerüst** (`docs/de/technik.md` → Bausteine), nur diese Teile verwenden:
  - **Kopf:** `h2.pt` mit `.pintro` (ein Satz). Abschnitte sind `h3.sec`, die `seite.js` in Kästen `.sgrp` legt.
  - **Zeile:** `setrow` mit Name und einem Satz links, genau ein Bedienelement rechts. Schalter `.tgl`, nie `label.chk`. Für 2 bis 4 Möglichkeiten Segmentknöpfe.
  - **Hilfetext:** höchstens ein Satz und ≤ 140 Zeichen sichtbar, der Rest hinter „Mehr“. „Erweitert“ steht immer in `details.adv`.
  - **Speichern:** eine schwebende Speichern-Leiste pro Seite. Sofort-Aktionen stehen in einem eigenen Abschnitt „wirkt sofort“.
  - **Listen:** Muster „Liste mit Detailbereich“ (`ld-`), am Handy wird das Detail eine eigene Seite. Ich-Seiten nutzen `ichteile.js` (Unterreiter mit Zahl, Statuskarte, ⋯-Menü, 10 Zeilen + „Weitere zeigen“, Gefahrenzone) und **keine inneren Scroll-Kästen**.
  - (D, P einstellungen-neu, ich-aufraeumen; 🧪 test_guides.BuildingBlocks, test_einstellungen_neu, test_ich_aufraeumen)
- **Breite:** Kein seitliches Scrollen bei 320, 390 und 1280 px. Kein Element ragt am Handy über den Rand. (🧪 test_ui_browser, test_ich_aufraeumen)
- **Rahmen:** Alle Seiten mit Seitenleiste (Zustand, Funktionen, Personen und Geräte, Einstellungen, Ich) nutzen den einen Rahmen aus `app.css` (`--frame`, `--sidecol`, `--sidegap`): Seitenleiste und Inhalt stehen auf jedem Reiter an derselben Stelle und gleich breit, keine Seite setzt eine eigene Breite. (D 2026-10-14; 🧪 test_seitenrahmen)
- **Höhe:** Der Assistent füllt das Fenster (nur der Verlauf scrollt). Höhenbudgets gelten für die Funktionen-Seite (< 2450 px bei 1280) und Personen und Geräte (< 1500 px). (🧪 test_ui_browser, test_einstellungen_neu)
- **Handy:** Tippziele mindestens 44 px, Eingabefelder 16 px, Safe-Area beachten. Das Gesicht bzw. „Frag Spark“ liegt nie über Bedienelementen. (P handy-wie-app; teils 🧪)
- **Statusfarben** grün, gelb und rot. „Braucht dich“ hat immer einen Knopf dorthin. Bernstein (`--c4`) gibt es im Live-Bild nur für Internet. (P design-klar, M)
- **Browser-Cache:** HTML ist `no-store`, CSS und JS werden mit `?v=VERSION` geladen, `/api` ist `no-store`. (🧪 test_panel.Page)
- **Laden sichtbar** (seit V01.0.459, Plan `seiten-laden.md`): Was eine Seite oder ein Kasten beim Öffnen lädt, läuft über `ladeBox`/`lzb` (`laden.js`): Platzhalter, „wird aktualisiert …“, „dauert länger als sonst …“ und der Fehler mit „Noch einmal“ stehen im Kasten selbst; ein Fehler nimmt der Seite nichts weg und meldet nie ab (nur 401). Mehrere Kästen laden gleichzeitig (`lzPool`, höchstens 4), nie in einer `await`-Kette. Nach 30 s ohne Antwort zeigt der Kasten den Fehler mit „Noch einmal“; die Anfrage wird nicht abgebrochen, kommt die Antwort doch noch, erscheint der Inhalt. Browser-Tests warten nach dem Öffnen einer Seite auf `lzIdle()` (alle Kästen geladen), nie auf eine feste Pause: ein Schalter, der vorher umgelegt wird, würde von den ankommenden Einstellungen zurückgesetzt. (🧪 test_seiten_laden)
- **Ruhig, nichts springt** (seit V01.0.558, Dominik 2026-10-14, Plan `ruhige-seiten.md`): Was der Anwender offen hat, bleibt offen und an seiner Stelle. Speichern und Schalten laden die Seite nie neu: geänderte Funktionen kommen beim nächsten Seitenwechsel ins Menü (`whoPendingGo`). Muss die Seite selbst neu laden (neue Version, Update fertig, Sprache), geht das nur über `verReload()`, das die Stelle merkt (Seite, Unterseite, offene Funktion, Person oder Ich-Bereich, Scroll) und `placeBack` wiederherstellt; kein neues `location.reload()` dafür. Aufgeklappte Teile (`details`) bleiben beim Neuzeichnen offen oder zu, wie der Anwender sie gestellt hat (`laden.js`). Abfragen auf Zeit zeichnen nur, was sich geändert hat (`setHtml`), und laufen schnell nur, solange ihre Seite zu sehen ist. Während das Update-Fenster offen ist (`updBusy()`), schweigt alles andere: kein Band, keine Versionsleiste, keine Abfrage dahinter, der Balken läuft nur vorwärts. Fragen stellt das Panel im eigenen Fenster, nicht mit `confirm()`. Die Apps halten es genauso: feste Kennungen für Zeilen, neue Einträge nur anhängen, offene Seiten verschwinden nicht von selbst. (🧪 test_ruhige_seiten)
- **Alle Panel-Skripte teilen einen globalen Namensraum.** Neue Funktionsnamen gegen alle JS-Dateien prüfen. (M [[dienst-ausfall-plan]]; 📝)
- **Begriffe:** „Ich“ (nicht „Mein Profil“), „Zustand“ (nicht Übersicht), „Personen und Geräte“ (nicht Profile), „Betrieb“ (nicht System), „Spark“, „Admin-Rechte“ (Rollen meint die Sprech-Rollen). Alte Seitennamen sind verboten. (P ordnung-und-darstellung, bedienung-gesamt; 🧪 test_bedienung_hilfe.Names, test_guides)

---

## 7. Texte, Hinweise, Hilfe, Englisch

- **Sprung-Links (PA, 2026-10-12):** Jede Meldung, die auf eine Stelle verweist, hat einen direkten Link dorthin, soweit die Person die Stelle sehen darf.
  - Der Weg beginnt mit einem Menünamen (Einstellungen, Funktionen, Zustand, Personen und Geräte, Ich). Kleingeschriebene Schritte sind Aktionen.
  - Das gilt für feste Texte, Server-Meldungen und Antworten des Assistenten.
  - Auch Zahlen, Zeilen und Schilder, die für eine Stelle stehen, sind Sprung-Links (PA, 2026-10-14: „sollte klickbar sein und direkt hinbringen“): jede Zeile einer Karte unter Zustand öffnet ihre Stelle (`way.js` `WAY_CARDS` oder `data-way`), jede Zahl wie die Kacheln „Heute“ ist ein Link (`wayFirst`). Eine neue Karte bekommt im selben Commit ihr Ziel; `test_sprunglinks` prüft jede Karte.
  - (M [[sprung-links]]; 🧪 test_sprunglinks)
  - **Überall** (Dominik 2026-10-12): Auch iPhone- und Android-App, Begleiter, Telegram und Push-Mitteilungen zeigen Wege als Link (`…/#weg=<Weg>` öffnet die Stelle im Panel). Wird eine Seite, ein Reiter oder eine Zeile umbenannt, werden alle Wege im selben Commit mitgezogen, auch in Doku, Hilfe und Apps. Neue Texte in den Apps laufen über deren Hilfen (`SparkAPI.way`, `Wege.text`, `Wege.cs`, `Wege.kt`), Telegram und Push über `wege.py`; in einer App heißt es „im Panel unter Einstellungen → …“. (🧪 test_sprunglinks.Outside prüft dieselbe Regel in allen Apps und ihre Wege im Panel)
  - Hinweise ohne Weg (oben auf den Admin-Seiten, Zustand-Karten) bekommen ein Sprungziel dorthin, wo man handeln oder nachsehen kann.
- **Englisch:** Jeder sichtbare Text in `index.html` steht in `i18n.js`, auch `title` und `aria-label`. Neue Texte aus JS über `t()` bzw. `tt(de,en)`. Server-Sätze gibt es auf Deutsch und Englisch. Die englische Doku nutzt englische Menünamen. (D; 🧪 test_bedienung_hilfe.English/Names, test_guides)
- **Fehler als Sätze:** `errSay`/`errRaw` aus `base.js`. Keine Pfade, kein `f"… failed: {e}"`, keine rohen englischen Ausnahmen. Gäste sehen nie interne Adressen. (D; 🧪 test_bedienung_hilfe.PlainErrors)
- **„?“** gibt es nur, wo die Hilfe die Zeile kennt. Jede Einstellungszeile mit Feld hat einen `sw:`-Eintrag. (🧪 test_bedienung_hilfe.QuestionMarks)
- **Anleitungen:** Jeder Schalter hat eine Anleitung in `guides.js` mit 7 Abschnitten. (🧪 test_guides)
- **Hilfe-Antworten:** höchstens 3 Treffer und etwa 1200 Zeichen. Wege nur aus der festen Liste. Die Herkunft kommt aus dem Panel, nie aus der Frage. (P hilfe-besser; 🧪 test_hilfe_quality)
- **Tipps sparsam:** höchstens 1 pro Gespräch und 3 pro Woche. „Nicht mehr zeigen“ gilt für immer. Keine Tipps nach fremdem Text, im Notaus oder für Gäste. (P funktionen-entdecken)
- **Mitteilungen** (Push): pro Version nur einmal, nie nachts, nicht in der Ruhezeit des Profils. Systemmeldungen sind feste Sätze ohne Namen. (P iphone-update, firmware-verteilen, home-assistant-meldungen)
- **Gesprochene Brückensätze** (`ack.PHRASES`) werden laufend erweitert, mit viel Abwechslung: mindestens 5 pro Gruppe, nie einer der letzten 6. (M [[sofortige-rueckmeldung]], Dominik 2026-10-11/12; 🧪 test_ack)
- Antworten nennen die Quelle kurz („Laut deinem Archiv …“). Links werden nie vorgelesen. (P erst-lokal)

---

## 8. Sprachmodell, Weiche, Werkzeuge

- **Die Weiche** liest nur die eigene letzte Nachricht. Sie schränkt nur ein und schreibt pro Zug eine Zeile `weiche:`. (M [[funktionswahl-plan]])
- **Fehlzuordnungen:** Regel in `intent.py` korrigieren und den Satz in `intent_bench.py` aufnehmen. (M; 🧪 test_intent)
- **Modellfehler im Panel beheben** (NEED_TOOLS, Antwortprüfung), nicht nur im Prompt. Dazu immer einen Selbsttest. (M [[answer-check-and-fixes]])
- **Texte an das Modell nennen nur Werkzeuge, die in dieser Antwort angeboten sind.** Sonst ruft es ein nicht angebotenes Werkzeug (Logs → Anfragen: „unbekannt“). (M [[ha-states-tool]]; 🧪 test_panel)
- **Datumsangaben** in Qualitätsfällen relativ zu heute, nie fest. (M)
- **Uhrzeiten von außen** (Mail-Kopfzeilen, Kalender, Bahn, Home Assistant) werden vor dem Vorlesen oder Zeigen in die Zone der Person umgerechnet (`chat.user_zone`, sonst `chat.system_zone`, Europe/Berlin), nie mit dem Versatz des Absenders ausgegeben. (Dominik 2026-10-12: Mail von 20:30 als 18:30 vorgelesen; 🧪 test_mail_zeit)
- **Denktext:** Jeder neue LLM-Aufruf, der mit Denken laufen kann, nimmt `common.no_think`, nicht die eigene `<think>`-Regex. (M [[think-tag-doppelt]])
- **Erst lokal, dann extern:** Dokumente, Kiwix, Verlauf. Daten bleiben möglichst im LAN. Kein zweites Modell nur für eine Teilfunktion (GPU-Speicher). Dokumente erstellen geht offline. (P erst-lokal, hilfe-besser, praesentationen-professionell)
- **Nie ändern:** dgx-spark-qwen38 auf den Ports 30000–30099, und nie automatisch abschalten oder löschen (nur ein Befehl, den der Admin selbst aufruft und der vorher fragt). Eigene Ports liegen bei 31001–31443, eigene Engines nur auf 127.0.0.1. (M; Dominik 2026-10-14)
- **Modelle nur aus dem Katalog:** Jedes Modell, das der Spark selbst betreibt, steht als Zeile in `app/modelle.json` und wird nur über `app/modelle.py` gelesen: feste Revision (ein voller Commit), Speicheranteil höchstens `modelle.ANTEIL_MAX` (0,80; darüber friert der GB10 ein), nie `trust_remote_code`, nur Safetensors und Textdateien (nie Pickle oder Python-Code), jede Datei nach dem Laden gegen ihre Prüfsumme geprüft und vor jedem Start auf Dateiart und Verweise, Engine-Schalter nur aus den Katalogfeldern, eine Engine startet nur mit festem Commit (aus dem Katalog oder der geprüften Messung). Messen schaltet qwen38 nie dauerhaft ab; nur `speech-spark modelle llm uebernehmen` deaktiviert es (nach Notiz, mit Rundlauf und selbsttätigem Weg zurück), entfernt wird es nur mit `qwen38-aufraeumen` auf Befehl nach gelungenem Umzug. (Dominik 2026-10-14, Plan eigene-modelle; 🧪 test_modelle, test_llm_tor, test_umzug)
- **Das eigene Sprachmodell nur durch das LLM-Tor:** Die Engines hören nur auf 127.0.0.1; von außen geht es nur über `llm_tor.py` (`llm.port`) mit API-Schlüssel und Größenlimit. Das Tor lässt nur die Felder aus `llm_tor.FELDER` durch (keine Token-IDs, kein `logit_bias`, `n` ist 1, `top_logprobs` höchstens `modelle.LOGPROBS_MAX`), setzt den Modellnamen und die Stichproben-Werte aus dem Katalog, und welches Modell antwortet, entscheidet eine feste Regel (`zum_sehen`), nie das Modell. Das Journal bekommt nur feste Wörter und Zahlen. (Plan eigene-modelle, Stufe E2; 🧪 test_llm_tor)
- **Werkzeuge heißen für Menschen verständlich:** sichtbar steht der Name aus `werkzeuge.NAMES` (de/en), der interne Name nur klein daneben oder in Kopien für Threads. (Dominik 2026-10-12; 🧪 test_werkzeuge)
- **Eigenes Tun ins Spark-Tagebuch:** Jede Funktion, die für eine Person etwas tut (schalten, erinnern, Entwurf ablegen, Datei erstellen oder schicken, Nachricht senden), ruft `tagebuch.note(uid, art, titel, ref, before, src)` mit fester Art; Titel von außen mit `src="web"` oder `"mail"`. Fragen nach dem eigenen Tun beantwortet das Modell nur aus `spark_tagebuch` oder `document_status`. (P vorschlaege-besser; 🧪 test_tagebuch)
- **Fehler mit Regeln beheben, nicht mit Code:** Was der Admin im Panel einstellen kann (Pflicht-Wörter, Werkzeug-Hinweise, Weiche), schlägt der Einstellungs-Assistent nur aus festen Vorlagen vor; das Modell schreibt nie den Text einer Regel, und eine Regel übernimmt sich nie von selbst aus den Meldungen einer einzigen Person. (P vorschlaege-besser; 🧪 test_regeln_admin, test_regeln_v3)

---

## 9. Tests

- **Für jede Schutzregel ein Selbsttest.** Für jeden Befund einer Prüfung ein Regressionstest. (PA, C; 🧪 test_pruefung, test_hardening)
- **Nur nachgebaute Dienste:** Kein Test spricht echte Modelle, Home Assistant, Mail oder Kalender an (`tests/helpers.py`). Den echten Test auf tars macht Dominik. (D)
- **Keine Uhrzeit-Abhängigkeit:** Zeiten werden übergeben. tars testet in der Zeitzone Europe/Berlin, GitHub in UTC. (PA, M)
  - ⚠ Das prüft kein Test allgemein.
- **Nur-`app/`-Kopie:** Tests, die Dateien außerhalb von `app/` lesen (`install.sh`, `update.sh`, `.github`, `docs`, `ios`), rufen `skipTest` auf, wenn die Datei fehlt. Neue Tests deshalb einmal so laufen lassen: `cp -r app /tmp/x/ && cd /tmp/x/app && python selftest.py discover -s tests`. (M [[selftest-app-only]])
- **Browser-Tests** warten auf einen Zustand, nie auf eine feste Zeit. Kontexte mit `bypass_csp=True`. Breiten 320, 390 und 1280 px. (M)
- **Tests schreiben keine unbekannten Konfig-Schlüssel**, schreiben die Konfiguration atomar (`helpers.write_config`) und schalten in `tearDown` Schleifen ab, die sie eingeschaltet haben. (M)
- **Ein Panel pro Testklasse, und es hört mit ihr auf:** Browser-Tests starten das Panel nur mit `helpers.serve_panel(cls, port)`, das es nach der Klasse wieder stoppt. Sonst laufen seine Hintergrund-Schleifen für den Rest des Laufs weiter, jede Klasse fügt eine Kopie hinzu, das Panel wird immer langsamer und nimmt späteren Tests die Arbeit weg. Tests hinterlassen keine Geräte, Verbindungen oder Profile, die spätere Tests stören; Paare wie `python -m unittest tests.test_chats tests.test_meldung` finden solche Lecks. (2026-10-13, main rot nach V01.0.473; 🧪 test_testserver)
- **Ports für Test-Server bleiben reserviert:** Ein Port für einen Test-Server kommt nur aus `helpers._port()`, das ihn gebunden hält, bis `helpers._serve` oder `helpers.take_port` (für Server, die selbst lauschen) ihn benutzt; nie einen Port holen und wieder freigeben. Ein belegter Port scheitert sofort statt 60 s zu warten (Lauf von V01.0.489: ein Port war auf dem Runner belegt, jeder Test wartete erneut, Abbruch nach 45 min). Selbsttest `test_testserver`.
- **Ein zweiter Versuch** (Dominik 2026-10-11): Ein roter Test bekommt genau einen zweiten Versuch (`app/selftest.py`).
  - Zweimal rot heißt rot. Bei mehr als 5 Fehlern gibt es keinen zweiten Versuch.
  - Grün erst im zweiten Versuch gibt eine sichtbare WARNUNG, und der Test muss trotzdem repariert werden.
  - (🧪 test_selftest_runner)
- **Nie** einen Test überspringen, abschwächen oder stilllegen, um grün zu werden. (PA, M)
- **Rauchtest** (`test_rauchtest`) bleibt schnell. Er ist der einzige Test, den tars bei bereits geprüften Versionen ausführt. (M [[schonende-updates]])
- **Qualitätstest** (echtes Modell): Ein roter Fall wird zuerst darauf geprüft, ob die Regex zu streng ist, und erst dann als Modellfehler behandelt. (M)
- **Praxistest:** Jede Funktion bekommt einen Prüfpunkt unten in `pruefung/praxistest-tars-2.md`. (M; 📝)
- **Prüfbank der Dokumentensuche:** Wer an der Dokumentensuche (`documents.py` Zerlegen, Suche, Mischen, später Nachsortieren) etwas ändert, lässt `test_suchpruefung` laufen. Die feste Prüfbank `tests/data/suchbank.json` muss mit der Wortsuche mindestens `FLOOR` Prozent unter den ersten 5 finden. Die Untergrenze wird nur angehoben, wenn die Suche besser geworden ist, nie gesenkt, um grün zu werden; neue Fragen kommen nur mit ehrlich gemessener Zahl dazu. (2026-10-13, Plan suche-schaerfen; 🧪 test_suchpruefung)

---

## 10. Repo, Push-Ablauf, CI, Releases

- **Direkt auf main.** Vor jedem Commit `git pull`, Patch-Nummer in `app/VERSION` erhöhen (V01.0.541). (PA)
- **Sammel-Push (PA, Dominik 2026-10-13, ersetzt „auf den Testlauf warten“):**
  1. Gepusht wird der Reihe nach über die Push-Warteschlange (`push-warteschlange.md`); nur wer ganz oben steht, pusht, nie vordrängeln.
  2. Wer oben steht, pusht sofort, auch wenn ein Lauf „Tests“ für main läuft oder wartet: vorher `git pull --rebase`, **nächste freie Versionsnummer zum Push-Zeitpunkt** (nie vorab reservieren), Selbsttests grün. Danach eigene Zeile entfernen, der Nächste ist sofort dran.
  3. GitHub testet am Ende nur den neuesten Stand: der laufende Lauf endet, von den wartenden bleibt nur der neueste (`cancel-in-progress: false`).
  4. Wird der Lauf auf main rot: PUSH-STOPP für alle; der Koordinator bestimmt den Verursacher und setzt dessen ROT-FIX nach oben.
- **Tests in Teilen (V01.0.502):** „Tests“ läuft in vier Teilen gleichzeitig (`selftest.py --part K/4`), geschnitten nach Testmodulen und ihrer Dauer in `app/tests/dauer.json` (ein Modul bleibt zusammen, weil manche Tests auf frühere Klassen ihres Moduls bauen; nur eine sehr lange Klasse mit Einträgen je Test wird Test für Test verteilt); zusammen enthalten die Teile jeden Test genau einmal. Der Job „Ergebnis“ zählt die Fehler aller Teile zusammen, die Grenze von 5 Fehlern gilt für den ganzen Lauf. Wird ein Teil deutlich länger als die anderen, `dauer.json` neu messen. (🧪 test_selftest_runner)
- **PUSH-STOPP:** Sagt der Koordinator „PUSH-STOPP“, wird nicht gepusht, bis er die Sperre ausdrücklich aufhebt. (M)
- **PROJEKT-SPERRE:** Steht eine Zeile „PROJEKT-SPERRE …“ oben in der Warteschlange, pusht nur der dort genannte Thread nach main; andere planen nur, dringende Fehler gehen über den Koordinator an diesen Thread. Die Sperre endet, wenn der Koordinator die Zeile entfernt. (M)
- **Commit-Nachricht:** `V01.0.541 Kurzbeschreibung`. Die CHANGELOG-Zeilen entstehen daraus. Ein einfaches „merge main“ als Nachricht vermeiden. (📝)
- **Workflows** (repo-absichern, 2026-10-11):
  - Jedes `uses:` ist auf einen 40-stelligen SHA mit `# vN` gepinnt. `contents: write` nur auf Job-Ebene. `persist-credentials: false`.
  - Signierschlüssel und Releases nur mit `environment: release`. Kein `pull_request_target`.
  - (🧪 test_workflows)
- **`cancel-in-progress: false`** in `tests.yml` nie wieder auf true setzen. (M [[tests-lauf-nicht-abbrechen]])
- **Update-Schranke:** tars spielt nur den neuesten main-Commit mit grünem „Tests“-Lauf ein. (🧪 test_hardening)
- **Releases:** Alte GitHub-Releases immer löschen, nur das neueste pro Reihe behalten. Ein neuer Release-Workflow kommt in die `workflow_run`-Liste von `releases-aufraeumen.yml`. (PA, M [[releases-aufraeumen]]; 🧪 test_releases_aufraeumen)
- **Ubuntu 26:** GitHub `ubuntu-latest` wechselt ab 2026-10-19. GitHub nutzt Python 3.11. (M)

---

## 11. Dokumentation und Versionen

- **README.md und README.de.md bleiben kurz** (etwa 90 Zeilen): Installation, „Letzte Änderungen“ mit genau 10 Zeilen, Schaubild, Links in `docs/`. (PA, M [[readme-layout]])
- **Pro Version** eine Zeile oben in `CHANGELOG.md` im Format `- **V01.0.541** · YYYY-MM-DD · Text` (sonst fehlt sie in „Was ist neu“) und in beiden READMEs, die älteste Zeile fällt raus. (PA; 🧪 test_changelog prüft nur das Format)
  - VERSION, die neueste CHANGELOG-Zeile und die erste Zeile beider READMEs stimmen überein, jede README hat genau 10 Zeilen. (🧪 test_richtlinie.Versions)
- **Details** stehen nur in `docs/de/*.md` und `docs/en/*.md`, beide Sprachen gleich gegliedert. Danach `hilfe.py --docs` ausführen. (PA; 🧪 test_hilfe.test_docs_copy_is_current)
- **Doku immer aktuell** (Dominik 2026-10-13): Jede Änderung zieht Doku, Hilfe und Architektur-Doku im selben Commit mit. Die Blöcke zwischen `<!-- technik:… -->` in `architektur.md`/`architecture.md` schreibt `hilfe.py --docs` aus dem Code; nie von Hand ändern. (PA; 🧪 test_technik.Docs)
- **Pläne** liegen unter `/mnt/project-files/plaene/` mit „Stand“ (Datum, Version), ★ für die Empfehlung und „Fragen an Dominik“. Bilder kommen aus dem echten Panel bzw. aus Mockups. (P)

---

## 12. Betrieb, Update, Ressourcen

- Etwa 10 GiB freier Speicher auf tars. DGX OS beendet unter etwa 8 GiB. Neue Dienste brauchen `MemoryMax=`. (M, D; 🧪 test_hardening)
- Ein Update unterbricht etwa 8 Sekunden. Nächtliche Arbeit läuft nicht während eines Updates (`update.update_running()`). Geräte-Runden laufen ab 05:15. (M)
- Selbsttest auf tars mit `nice 19` und `ionice`. Prioritäten-Code mit `nice -n 19` testen. (M)
- Die Panel-venv entsteht aus dem Lock nur, wenn venv-panel neu ist. Eine neue Bibliothek braucht deshalb einen Installationsweg für bestehende Installationen. (M)
- Fragen an `api.github.com` nur über `ghtoken.get` (Token nur lesen, 401 → ohne Token weiter), nie für Erreichbarkeits-Proben: ohne Token teilen sich alle Geräte im Heimnetz 60 pro Stunde. (D; 🧪 test_ghtoken, test_update_check)

---

## 13. Zusammenarbeit (Threads und Dominik)

- Antworten auf Deutsch, kurze nummerierte Vorschläge mit markierter Empfehlung. Bei größeren Funktionen erst Plan, dann bauen. (PA)
- Im Ergebnis steht, welche Punkte der Sicherheits-Checkliste und der Pflichtliste (Teil 1) berührt wurden. Bei neuen Funktionen auch, was in Live ergänzt wurde. (PA)
- Eine neue allgemeine Regel kommt im selben Commit in diese Richtlinie (de und en) und, wenn möglich, in einen Selbsttest.
- Gibt es eine neue Version, zuerst in Dominiks Trace prüfen, welche Version tars schon hat. (M)
- Berühren zwei Threads dieselbe Datei, sagt der Koordinator es beiden. (M)

---

## 14. Was Selbsttests schon erzwingen (Übersicht)

| Test | Erzwingt |
|---|---|
| test_scanner | keine gefährlichen Aufrufe, Login an jeder Route (sonst OPEN mit Grund), Upload-Limits, strenge CSP, Werkzeuge sortiert |
| test_hardening | Body vor dem Lesen begrenzt, root-Schreibwege, Unit-Limits, nur grüne Versionen, Fremdtext-Sperren |
| test_stufen | jeder Code-Endpunkt mit Stufe in `stufen.LIST` |
| test_features | ein Register, Freigabe gilt für jedes Profil, Sperre nur durch den Admin, Vorlieben starten an, keine eigene Prüfung, ein Standardwert |
| test_live | jedes Werkzeug, Ziel, jeder Client und jede guard-Art im Live-Bild, keine Inhalte |
| test_testserver | Panel einer Browser-Testklasse stoppt mit ihr, keiner startet es anders |
| test_werkzeuge | jedes Werkzeug hat einen Namen de/en, Seiten lesen dieselbe Tabelle |
| test_ack | jede Weiche-Gruppe hat ≥ 5 Brückensätze |
| test_intent, test_weiche | Weiche-Regeln und BENCH-Sätze |
| test_tracelog, test_logfilter | Logs und Anfragen nur feste Wörter und Zahlen, Filter sicher |
| test_sprunglinks | jeder Weg beginnt mit einem Menünamen und wird gefunden |
| test_bedienung_hilfe | Englisch, Fehler als Sätze, „?“ mit Hilfe, alte Namen verboten |
| test_guides | Seitenbausteine, Menü, Anleitung pro Schalter, ≤ 140 Zeichen |
| test_hilfe, test_hilfe_quality | Hilfe-Index aktuell, ≥ 60 Alltagsfragen richtig |
| test_seiten_laden | Seiten laden über `ladeBox`, Ich gleichzeitig, Fehler im Kasten, nach 30 s „Noch einmal“, Band „Spark antwortet nicht“, langsame Lesezugriffe in Diagnose |
| test_ruhige_seiten | Speichern lädt nicht neu, Neuladen kommt an dieselbe Stelle, ein ruhiges Update-Fenster (kein Band, Balken nur vorwärts), Aufgeklapptes bleibt offen, Zustand fragt nur sichtbar alle 3 s |
| test_ui_browser, test_ich_aufraeumen, test_einstellungen_neu | keine Breite über den Rand (320/390/1280), Höhenbudgets, keine inneren Scroll-Kästen |
| test_seitenrahmen | ein Rahmen für alle Seiten mit Seitenleiste: gleiche Stelle und Breite auf jedem Reiter, nichts breiter als das Handy |
| test_workflows, test_lock, test_lieferkette | gepinnte Actions, Rechte, Signierumgebung, Paket-Hashes, ffmpeg-Whitelist |
| test_selftest_runner | ein zweiter Versuch, > 5 kein Versuch, Warnung |
| test_rauchtest | jedes Modul lädt, `restart-map` vollständig |
| test_technik | jedes Modul, jede Datei in `state/` und `users/` in der Architektur-Doku und in Sicherung oder lokaler Liste, Doku-Blöcke aktuell, Seite Technik nur für Admins |
| test_changelog | CHANGELOG-Format |
| test_releases_aufraeumen | nur neuestes Release pro Reihe |
| test_app_gleichstand | eine Liste der Ich-Seiten, jede Seite in den Apps erreichbar (Ausnahmen mit Grund), Seiten folgen der Freigabe, App-Texte mit Englisch |
| test_aufraeumen | keine neuen Doppel: eigener `<think>`-Filter, doppelter Dict-Schlüssel, ungenutzter Import, eigenes JSON-Schreiben, eigener Modellaufruf, roher `fetch(`, abweichende Namen in features.py und guides.js (Altlastenliste schrumpft nur) |
| test_richtlinie | an ausgelieferte Werte mit Grund, Journal ohne Profilnamen, VERSION/CHANGELOG/README im Einklang, Richtlinie de/en vorhanden und ihre Testnamen gültig |

**Nur Absprache (kein Test):**
- Push-Reihenfolge
- Uhrzeit-Unabhängigkeit allgemein
- Log-Präfix
- `undo.py` / `SENSITIVE`
- Praxistest-Punkt
- „Daten nie über innerHTML“ (allgemein)
- globale JS-Namen
- Commit-Nachricht
- Prüfung gegen den Stand der Technik

---

## 15. Veraltet und noch offen

**Veraltet (gilt nicht mehr):**
- Feature-Pause vom 2026-10-09: Sie ist aufgehoben. Es gilt „bauen nach Dominiks ausdrücklichem OK“.
- Menü-Stände vor dem 11.10. („Übersicht“, „Einbinden“, die alte Profilseite, Handy-Leiste „Assistent · Ich · Zustand · Verwalten“): Es gilt Teil 6.
- Funktionen-Seite als „Wer darf was“-Tabelle bzw. Kurzzeilen: Es gilt Liste plus Detail.
- Live-Übersicht mit SSE bzw. „Blaupause“: gebaut sind 1-s-Abfrage und „1 Fluss“.
- Hilfe mit 3–5 Treffern: Es gelten höchstens 3.

**Geplant, aber nicht gebaut (keine Regel, bis gebaut):**
- zentrale Seitenliste `js/pages.js`
- Trace-ID vor jeder Logzeile (`[a7f3]`)
- Übersetzung über Schlüssel statt über Textvergleich
- gemeinsames `jsonstore` bzw. `llm.complete()` (Prüfung Paket 7)

**Offen (Live-Übersicht, `live-uebersicht/was-fehlt.md`):** GitHub-Meldungen als eigener Knoten, Einzelschritte im Morgenüberblick, Anzahl der Begleiter, eigenes Gerät „Schreibhilfe“, reMarkable-Schritte.

**Offen (Sicherheit):** siehe „Stand der Technik → noch nicht erfüllt“ in der [Sicherheits-Checkliste](sicherheits-checkliste.md).

---

## 16. Beschlüsse vom 12.10.2026

1. Standardmäßig an nur mit Grund in `features.DEFAULT_ON`, geprüft durch `test_richtlinie`.
2. Diese Richtlinie liegt in `docs/de/richtlinien.md` und `docs/en/guidelines.md`; `CLAUDE.md` im Repo fasst sie zusammen; README und Projektanweisungen verweisen darauf.
3. Neuer Selbsttest für VERSION, CHANGELOG und README.
4. Die Sicherheits-Checkliste liegt im Repo (`docs/de/sicherheits-checkliste.md`, `docs/en/security-checklist.md`) und hat einen Teil „Stand der Technik“, gegen den jede Änderung geprüft wird.
5. Sprung-Links gelten überall und werden bei jeder Änderung mitgezogen.
6. Journalzeilen nennen Profile nur mit deren Zustimmung.

---

## 17. Aufräumen: eine Quelle (Dominik 2026-10-14)

„… dass wir keine doppelten Einstellungseinträge haben, doppelte Datenführung, doppelte was weiß ich, dass es einfach immer alles sauber ist.“ Plan und Bestandsaufnahme: `plaene/aufraeumen-und-apps.md` im Projektordner.

1. **Eine Quelle.** Jede Liste, jeder Standardwert, jeder Name, jeder Dateiname und jeder Helfer steht genau einmal. Braucht ihn eine zweite Stelle (JS, Swift, Kotlin, Doku), wird die Kopie erzeugt (wie `werkzeuge.py --js`, `hilfe.py --docs`) oder ein Selbsttest gleicht sie ab.
2. **Erst suchen, dann bauen.** Vor einem neuen Helfer, einer Liste oder einer Einstellung prüfen, ob es das schon gibt: `common.write_json`/`read_json`, `common.STATE` (Zustandsordner), `dateien.py` (Datei-Register: jede Datei des Panels mit Inhalt, Sicherung und Kopie), `common.no_think`, `common.load_config`, `llm.complete` (Sprachmodell), `core.json_body` (Anfrage-Inhalt), `common.DayCounter` (Zahlen von heute), `kopplung.Codes` (Einmal-Codes zum Koppeln), `sse.Hub` (Ereignisse an offene Seiten), `geraeteupdate.newer` (Versionen vergleichen), `profiles.pending_set`/`pending_get` (offener Vorschlag mit Frist), `features`, `profiles.SETTINGS`, `profiles.CHOICES`, `netguard.client`, `api()`/`apiTry()` in JS, die Bausteine aus Teil 6. Vorhandenes benutzen oder erweitern, nie kopieren.
3. **Aufräumen im selben Commit.** Wer etwas ersetzt oder entfernt, löscht das Alte mit: Schlüssel (die alten kommen in die Liste entfernter Schlüssel), Funktionen, Imports, Übersetzungen in `i18n.js`, CSS-Regeln, Altnamen und Hüllen.
4. **Standardwerte nur an einer Stelle:** `config.default.json` für den Spark, `profiles.SETTINGS` für Profile, deren erlaubte Werte und Grenzen in `profiles.CHOICES`/`RANGES`. Kein zweiter Standardwert im Code; der Browser bekommt Vorgaben, Listen und Grenzen von `/api/profile/settings` (me.js `loadSettings`, `SDEF`, `SETC`).
5. **Keine neuen Doppel, die alten werden weniger.** `test_aufraeumen` führt je Prüfung eine Altlastenliste mit dem Stand vom 14.10.2026. Eine Datei darf nie mehr Treffer haben als ihr Eintrag; hat sie weniger, wird ihr Eintrag im selben Commit gesenkt. Die Liste wird also nur kürzer. Ein Import, der nur für seine Nebenwirkung da ist, bekommt `# noqa: F401`.
6. **Die große Aufräumaktion** (Abbau der Altlastenliste) startet erst, wenn kein anderer Thread mehr auf main baut (Dominik 2026-10-14), damit der ganze Code einmal einen sauberen Stand bekommt. Bis dahin räumt niemand Altlasten in Dateien auf, an denen ein anderer Thread arbeitet.
7. **Keine Prüf-Hüllen.** Keine einzeilige Funktion, die nur `features.allowed(…)` weiterreicht: direkt `features.allowed` aufrufen (für Gäste ist es schon falsch, ein `bool(uid) and` davor ist unnötig). Ausnahme nur, wo die Funktion als Rückruf übergeben wird (`profiles.*_GATE`) oder ein Test sie ersetzt. Die Hüllen um `features.admin_on` bleiben: sie sind die geprüften Stellen der Liste `ADMIN_ON_OK` (test_sperre_ueberall).

| Prüfung in test_aufraeumen | Gemeinsame Stelle |
|---|---|
| OwnThinkFilter | `common.no_think` |
| DoubleDictKey | ein Schlüssel einmal |
| UnusedImport | löschen oder `# noqa: F401` mit Grund |
| OwnJsonWrite | `common.write_json` (frischer Name statt festem `.tmp`) |
| OwnModelCall | geplant: ein gemeinsames `llm.complete` |
| RawFetch | `api()`/`apiTry()` aus base.js (Anmeldung, Code-Dialog, Notaus, Ladeleiste) |
| SameNames | Gruppen und Namen aus `features.py` |
| SettingCopies | Vorgaben und erlaubte Werte aus `profiles.SETTINGS`/`CHOICES` (Browser: `SDEF`, `SETC`) |
| StateFolder | Zustandsordner nur aus `common.STATE` |
| FileRegister | Dateilisten nur aus dem Datei-Register `dateien.py` |
| CheckWrapper | `features.allowed` direkt, keine Hülle |
