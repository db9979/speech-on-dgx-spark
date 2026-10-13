# Sicherheits-Checkliste für neuen Code

Vor jedem Commit durchgehen. In der Antwort an Dominik kurz nennen, welche Punkte die Änderung berührt hat. Teil der [Coding-Richtlinie](richtlinien.md); englisch: [docs/en/security-checklist.md](../en/security-checklist.md). Entstanden aus der Prüfung vom 08.10.2026 (V01.0.98); in Klammern steht jeweils die Falle, die dort gefunden wurde. Seit 12.10.2026 wird jede Änderung zusätzlich gegen den Teil **Stand der Technik** am Ende geprüft (Dominik: „alles sicher und nach neuesten technischen Sicherheitsmechanismen“).

## Zugang
- [ ] Für jeden neuen Endpunkt festgelegt: Gast, Profil im Browser, Geräteschlüssel oder Admin.
- [ ] Geheimnisse, Adressen, die ein Token bekommen, Codewort, Push-Ziele und Mail-Konten nur mit Browser-Anmeldung und frischem Code (`browser_profile` + `confirm_code`), nie mit Geräteschlüssel. (Ein Geräteschlüssel konnte die HA-Adresse umbiegen und so das Token abgreifen.)
  - Einzige Ausnahme (V01.0.250, Plan „iPhone-App übernimmt das Panel“, Stufe 9): der Schlüssel der eigenen iPhone-App mit Bereichsschalter „Konten verbinden in der App“, über `secret_profile`: dort ist der zweite Anmeldeschritt Pflicht und jede Änderung braucht einen frischen Code. Codewort und MFA-Einrichtung bleiben im Browser.
  - „Frisch“ heißt seit V01.0.289 (Plan „Zweiten Anmeldeschritt seltener“): ein richtiger Code derselben Anmeldung (Admin-Login, Profil-Browser-Sitzung oder App-Schlüssel) aus den letzten 10 Minuten zählt (`core.CONFIRM_WINDOW`). Wirklich jedes Mal fragen (`admin_code_fresh`, `secret_profile_fresh`, `confirm_code(..., fresh=True)`): zweiter Schritt selbst, Admin-Passwort, Rollen, Sicherungen einspielen/hochladen/herunterladen/umziehen, Codewort, Admin-Modus öffnen, Spark-Update aus der App. Neue Endpunkte dieser Art gehören in diese Liste. Raw `fetch` an solche Endpunkte zeigt nur „code required“: im Browser immer `api()`/`apiTry()` nehmen. Ein Passkey (seit V01.0.295, `passkey.py`, Header `X-Speech-Passkey`) zählt überall wie ein frischer Code; neue Code-Abfragen laufen deshalb immer über `confirm_code`, nie über eigenes `mfa.verify`. In der iPhone-App (seit V01.0.357) laufen Anfragen mit Code über `SparkAPI.confirmed(...)`, nie mit eigenem `X-Speech-Code`-Header, damit „Mit Passkey“ überall geht; Passkeys anlegen bleibt im Browser. Seit V01.0.427 (Plan `plaene/zweiter-faktor-einheitlich.md`) steht jeder Endpunkt mit Code mit Stufe (Bestätigen oder Schutz ändern), Bereich und Text (de/en) in `app/panel/stufen.py` LIST; `test_stufen` schlägt sonst fehl. Die Liste entscheidet, ob die 10 Minuten zählen; neue Knöpfe mit Code bekommen das Schloss (`CODE_LOCKS` in `mfa.js`). Den zweiten Schritt des Notzugangs nie direkt über die Datei lesen, immer `mfa._path(ADMIN)` (verbunden mit dem Haupt-Admin-Profil).
- [ ] Ändert sich die Adresse, muss das Token neu eingegeben werden.
- [ ] Zustandsänderungen nur per POST/PUT/DELETE, nie per GET. (`?take=true`)
- [ ] Gäste bekommen nur Frage und Antwort: keine Werkzeuge, keine persönlichen Daten, keine Aktionen und keine Fehlertexte, nur Fehlercodes.
- [ ] Eine fremde erkannte Stimme bekommt nur nicht-persönliche Werkzeuge.
- [ ] Geteilte Geräte (Lautsprecher im Raum): Der Geräteschlüssel allein zählt nicht als Inhaber. Persönliches nur, wenn die Sprechererkennung in derselben Aufnahme die Inhaberstimme sicher erkennt; sonst Gastrechte, früherer Verlauf geht nicht mit. Wessen Stimme es war, setzt nur das Panel (Request-Scope), nie die Anfrage. (V01.0.226: fremde Stimme bekam die Mails des Inhabers.)
- [ ] Gesprochenes Codewort (Lautsprecher, V01.0.297): nur für eine Stimme, die schon fast sicher der Inhaber ist, nie für eine fremde; eigenes Codewort, nicht das Smart-Home-Codewort; der Satz damit geht nie ans Modell, in Verlauf, Diagnose, Anzeige oder Log; Sperre nach Fehlversuchen mit Mitteilung.
- [ ] Vergleiche von Schlüsseln und Codes laufen mit `hmac.compare_digest`.

## Größe und Last
- [ ] Größenlimit für den Request-Body, bevor etwas gelesen wird. Upload mit `read(limit+1)` lesen. Den Body erst nach der Anmeldung parsen (FastAPI liest `File`/`Form` vor den Dependencies).
- [ ] Bei Entpacktem (zip, docx, Sicherung) die Größe nach dem Entpacken begrenzen. (docx-Bombe)
- [ ] Audio: Abtastrate 8000 bis 48000 Hz, Dauer begrenzt (`ffmpeg -t`), Ausgabe mit Byte-Grenze lesen. (1-Hz-WAV, FLAC-Bombe)
- [ ] Downloads gestreamt und mit Byte-Grenze (CalDAV, CardDAV, webcal, Seiten).
- [ ] Textlänge für TTS und Chat begrenzt, auch für die letzte Nachricht.
- [ ] Rate-Limit pro IP und eine globale Semaphore für LLM, ASR und TTS, besonders für Gäste.
- [ ] Obergrenze für Jobs, Werkzeugaufrufe pro Runde, Suchen pro Antwort und Speicher-Einträge.
- [ ] Caches haben ein Ablaufdatum und eine Maximalgröße, und der Schlüssel enthält keine sekundengenauen Zeiten.
- [ ] Schwere synchrone Arbeit (RRULE-Expansion, große Regex, ffmpeg) läuft per `to_thread` mit Zeit- und Mengenbudget, nie im Event-Loop. (Ein `FREQ=SECONDLY`-Termin hat das Panel eingefroren.)
- [ ] Neue systemd-Units haben `MemoryMax=` und `PrivateTmp=yes`.

## Fremder Text (Prompt-Injection)
- [ ] Als fremd gilt: Web, Seiten, Mail, Kalender, Kontakte, Pakete, Dokumente, HA-Zustände und -Attribute, Telegram, Raum-Mitgehörtes sowie alte Antworten, die daraus gebaut wurden.
- [ ] Fremder Text wird beim Modell als Daten eingepackt (`_wrap`), und Trennzeichen darin werden entschärft.
- [ ] Ein neues lesendes Werkzeug kommt nach `READS_OUTSIDE`.
- [ ] Nach fremdem Text sind Schalten, Gedächtnis, Erinnerungen, Vorschläge und Entwürfe gesperrt, und zwar auch im nächsten Zug. (Das „Fremd“-Kennzeichen ging beim nächsten Zug verloren.)
- [ ] Antworten aus fremdem Text werden markiert (`outside`-Event) und nie ins Gedächtnis gelernt.
- [ ] Nur angebotene Werkzeuge laufen. Ein neues Werkzeug steht in den passenden Sperrlisten.
- [ ] Codewort und Geheimnisse gehen nie ans Modell, an die Suche, in den Verlauf, das Protokoll oder Erinnerungen (Raum-Cues).
- [ ] Inhalte, deren Absender nicht geprüft ist (DKIM/DMARC), werden nicht als „von DHL“ oder „von Kontakt X“ ausgegeben.

## Bestätigen und Handeln
- [ ] Es gibt pro Profil genau einen offenen Vorschlag. Er gilt nur für dasselbe Gerät, ein schlichtes „Ja“ und 15 Minuten. Jede neue Antwort verwirft ihn.
- [ ] Die Stimmprüfung für „Ja“ gehört zur selben Aufnahme wie der Text.
- [ ] Home Assistant läuft mit einer Allowlist von Domains, nicht mit einer Sperrliste (`script`, `automation`, `button` usw. bleiben draußen).
- [ ] Mail wird nie gelöscht. Verschieben nur mit geprüfter UIDVALIDITY und exaktem Abgleich von Absender und Message-ID nach SEARCH.

## Anfragen nach außen (SSRF)
- [ ] Nur http(s). Loopback, private und link-local Adressen sind gesperrt, außer der Admin erlaubt das Heimnetz ausdrücklich.
- [ ] Die geprüfte IP wird festgehalten (kein zweites DNS, also keine DNS-Rebinding-Lücke), und jede Weiterleitung wird neu geprüft.
- [ ] Zugangsdaten gehen nur an denselben Origin (auch bei hrefs aus PROPFIND), es gibt nie einen Rückfall auf http, und TLS-Prüfung ist an.
- [ ] `ref_audio` und Ähnliches nur als `data:` mit Größengrenze, nie als URL.

## Injektion
- [ ] `subprocess` nur mit Listen-Argumenten, nie `shell=True`, `eval` oder `exec`. Kein `pickle` und kein `allow_pickle` auf Fremddaten.
- [ ] IMAP-Werte nur aus druckbarem ASCII ohne CR/LF, gequotet. (Eine Message-ID mit `=0D=0A`)
- [ ] HTML wird über `textContent` oder `esc()` plus `data-`-Attribute gebaut, nie über inline `onclick` mit Werten.
- [ ] Konfigurationswerte werden beim Speichern, beim Wiederherstellen und in `install.sh` gleich geprüft. In Bash nur Ziffern oder feste Werte übernehmen.

## Geheimnisse und Logs
- [ ] Geheimnisse liegen nur im vault und werden nach dem Speichern nie zurückgegeben.
- [ ] Logs und Fehlertexte enthalten keine Tokens. Bot-Tokens und Schlüssel werden geschwärzt, also nicht `str(e)` von httpx mit Token in der URL ausgeben.
- [ ] `/health` und ähnliche offene Seiten zeigen nur einen Status, keine Fehlertexte und keine Namen.

## root-Grenze und Update
- [ ] root folgt keinen Symlinks in Ordnern, die `speech` gehören (`chown -h`, vorher löschen).
- [ ] Neue Pakete werden mit fester Version installiert.
- [ ] Nichts aus der Konfiguration landet ungeprüft in einem root-Skript.

## Vor dem Commit
- [ ] Neue Schalter stehen standardmäßig auf aus: ein Admin-Schalter, kein neuer Profilschalter; eine Sperre für einzelne Profile setzt nur der Admin.
- [ ] Jede neue Schutzregel hat einen Selbsttest.
- [ ] Alle Selbsttests sind grün.

## Stand der Technik

Jede Änderung wird nicht nur gegen die Fallen oben geprüft, sondern auch dagegen, ob sie dem heutigen Stand der Sicherheitstechnik entspricht. Wird ein Maßstab neu herausgegeben oder ein Verfahren als schwach eingestuft, wird dieser Teil im selben Commit angepasst und die Liste „Noch nicht erfüllt“ ergänzt.

**Maßstäbe**
- [ ] Web und API: OWASP ASVS 5.0, Stufe 2; Anmeldung, Geheimnisse und Admin-Wege Stufe 3.
- [ ] Sprachmodell-Wege: OWASP Top 10 for LLM Applications 2025 (Prompt-Injection, Datenabfluss, zu viel Handlungsmacht, ungeprüfte Ausgabe, unbegrenzter Verbrauch).
- [ ] Kryptografie und TLS: BSI TR-02102 bzw. NIST-Empfehlungen; TLS nach Mozilla „intermediate“ oder strenger.
- [ ] Lieferkette: feste Versionen mit Hash, gepinnte Actions, Signaturen (SLSA-Gedanke: nachvollziehbar gebaut, geprüft geladen).

**Kryptografie**
- [ ] Nur geprüfte Bibliotheken (`hashlib`, `secrets`, `hmac`, `cryptography`), nie eigene Verfahren. Zufall nur aus `secrets`.
- [ ] Neue Verschlüsselung nur mit AEAD (AES-256-GCM oder ChaCha20-Poly1305), eigener Schlüssel pro Zweck, Nonce nie doppelt.
- [ ] Neue Passwort-Ableitung mit scrypt oder Argon2id; PBKDF2-SHA256 nur mit mindestens der aktuellen OWASP-Rundenzahl.
- [ ] Signaturen mit Ed25519; Prüfungen scheitern geschlossen.

**Verbindungen**
- [ ] Nur TLS 1.2 oder neuer, TLS 1.3 bevorzugt; Zertifikatsprüfung nie aus; kein Rückfall auf http.
- [ ] HSTS auf https.

**Anmeldung und Sitzung**
- [ ] Passkeys (WebAuthn) vor Codes; zweiter Schritt als TOTP oder Passkey, nie SMS.
- [ ] Sitzungs-Cookies `HttpOnly`, `Secure` auf https, `SameSite=Strict` oder `Lax`; neue Sitzungskennung nach Anmeldung und Rechte-Wechsel; „überall abmelden“ möglich.
- [ ] Sperre und Verzögerung nach Fehlversuchen pro Name und pro Browser.

**Browser**
- [ ] Strenge CSP (`script-src 'self'`, kein `unsafe-eval`, keine Inline-Skripte), `frame-ancestors`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- [ ] Modellausgaben und fremde Texte werden in der Oberfläche nie als HTML ausgeführt.

**Lieferkette und Betrieb**
- [ ] Neue Pakete mit Version und Hash im Lock; neue Actions per SHA gepinnt; Dependabot-Hinweise zeitnah übernehmen.
- [ ] Geheimnisse nie im Repo (Secret Scanning mit Push-Schutz ist an).
- [ ] Bekannte Schwachstellen in Abhängigkeiten werden geprüft, bevor eine Version mit neuen Paketen ausgeliefert wird.

**Regelmäßige Prüfung**
- [ ] Vor großen Versionen und mindestens einmal im Monat eine skeptische Gesamtprüfung gegen diese Maßstäbe (wie am 08.10. und 11.10.2026). Jeder Befund bekommt einen Selbsttest.

**Noch nicht erfüllt** (wird beim nächsten Berühren der Stelle nachgezogen; Stand 12.10.2026)
- PBKDF2-SHA256 mit 200.000 Runden für Admin-Passwort und PIN (`core.ROUNDS`, `profiles.PIN_ROUNDS`); OWASP empfiehlt heute 600.000 oder Argon2id/scrypt. Umstellung mit Neuberechnung beim nächsten Anmelden.
- Fernet (AES-CBC plus HMAC) im vault und bei Umzugsschlüsseln: sicher, aber kein AEAD; neue Teile nehmen AES-GCM, ein Wechsel nur mit Umzug der vorhandenen Daten.
- Kein automatischer Schwachstellen-Abgleich der Python-Pakete (z. B. gegen die OSV-Datenbank) in „Tests“.
- Signierte Geräte-Updates sind gebaut, aber ohne Schlüssel aus (`UPDATE_SIGNING_KEY` fehlt noch).
- `style-src 'unsafe-inline'` bleibt wegen älterer Safari-Versionen in der iPhone-App.
- Mindest-TLS-Version des eigenen https-Servers ist nicht ausdrücklich festgelegt (prüfen).
