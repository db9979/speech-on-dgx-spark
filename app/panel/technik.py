"""Zustand → Technik (plan plaene/technische-doku.md, Dominik 2026-10-13 „1 umsetzen, immer alles aktuell halten“):
how the Spark is built, as a page to click through and as docs/de/architektur.md + docs/en/architecture.md.

One source for both: the parts (MODULE, GRUPPEN), the picture (KNOTEN, KANTEN), the way of one request (SCHRITTE)
and where data lies (speicherorte(), built from the register dateien.py and the lists here).
`python3 app/panel/hilfe.py --docs` writes the generated parts into both docs (between the markers
<!-- technik:… -->) before it copies the docs into hilfe_docs.json. tests/test_technik.py turns red when a module,
a file under state/ or users/, a node or a step is missing here, or when the docs are not written again, so the
picture stays true with every change.

Admin only (GET /api/admin/technik): only names of modules and paths, never contents, keys, addresses or names of
profiles. Nothing here switches or writes anything; there is no switch (like the changelog, it only describes).
"""
import ast
import functools
import json
import os
import re
import sys

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # common.py, also as a script
import dateien  # noqa: E402
import guard  # noqa: E402
import technik_knoten  # noqa: E402
from core import auth  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
REPO = os.path.dirname(APP)
DOCS = {"de": os.path.join(REPO, "docs", "de", "architektur.md"), "en": os.path.join(REPO, "docs", "en", "architecture.md")}

# ---------------------------------------------------------------- the parts
# group id -> (German, English, German text, English text)
GRUPPEN = {
    "zugang": ("Zugang und Rechte", "Access and rights",
               "Jede Anfrage geht zuerst hier durch: Größe, Herkunft, Notaus, Anmeldung, Profil und Freigaben.",
               "Every request passes here first: size, origin, kill switch, login, profile and releases."),
    "gespraech": ("Gespräch", "Conversation",
                  "Bereitet eine Anfrage vor, fragt das Sprachmodell in Runden und prüft, was gesagt wird.",
                  "Prepares a request, asks the language model in rounds and checks what is said."),
    "weiche": ("Weiche und Werkzeugnamen", "Switch and tool names",
               "Feste Regeln, welche Werkzeuge das Modell für eine Frage sieht. Gibt nie mehr frei als die Rechte.",
               "Fixed rules for which tools the model sees for a question. Never gives more than the rights."),
    "wissen": ("Wissen und Dokumente", "Knowledge and documents",
               "Eigene Dokumente, Gedächtnis, frühere Gespräche, Kiwix und Wikipedia, erstellte Dokumente.",
               "Own documents, memory, earlier conversations, Kiwix and Wikipedia, created documents."),
    "dienste": ("Anbindungen", "Connections",
                "Home Assistant, Aufgaben, Für dich, Wetter, reMarkable, MCP und was der Spark von selbst tut.",
                "Home Assistant, tasks, For you, weather, reMarkable, MCP and what the Spark does by itself."),
    "post": ("Post und Kontakte", "Mail and contacts",
             "Die eigenen Seiten E-Mail, Kalender und Kontakte, der Abruf beim Anbieter, der versiegelte Vorrat und die "
             "Türen für Kalender- und Kontakte-Apps.",
             "The own pages E-mail, Calendar and Contacts, fetching from the provider, the sealed supply and the doors "
             "for calendar and contacts apps."),
    "geraete": ("Geräte und Kanäle", "Devices and channels",
                "Apps, Telegram, Uhr, Lautsprecher, Raummodus, Chats und der Verlauf auf allen Geräten.",
                "Apps, Telegram, watch, speakers, room mode, chats and the history on all devices."),
    "betrieb": ("Betrieb", "Operation",
                "Live-Übersicht, Logs, Wächter, Sicherung, Update, Hilfe und die Admin-Seiten.",
                "Live overview, logs, watchers, backup, update, help and the admin pages."),
    "sprache": ("Sprachdienste", "Speech services",
                "Spracherkennung und Sprachausgabe als eigene Dienste, mit Vorrang vor allem anderen.",
                "Speech recognition and speech output as their own services, ahead of everything else."),
    "fern": ("Fernzugang", "Remote access",
             "Shell, Dateien und Bildschirm eigener Server über ihren Anker, dazu die Spontanhilfe; nur für Admins.",
             "Shell, files and screen of own servers through their anchor, plus spontaneous help; admins only."),
    "teilen": ("Spark teilen", "Spark split",
               "Panel auf einem eigenen Rechner, Modelle auf dem DGX: Kopplung, TLS-Tor, Wärter und Umzug.",
               "Panel on its own computer, models on the DGX: pairing, TLS-Tor, Wärter and the move."),
}

# every module of app/panel and app/: name -> (group, German line). English comes from the module's docstring.
MODULE = {
    # Zugang und Rechte
    "panel": ("zugang", "Startet das Panel, Middleware (Notaus, Herkunft, Größe), liefert die Seite aus"),
    "core": ("zugang", "Admin-Passwort, Sitzungen, gemeinsame Pfade und Helfer"),
    "guard": ("zugang", "Rate-Limits, Sperren nach falschen Versuchen, fremde Seiten, audit.log mit Prüfkette"),
    "profiles": ("zugang", "Profile, Geräte, Sitzungen, Gespräche und Gedächtnis pro Profil"),
    "account": ("zugang", "Was ein Gerät für sich selbst darf: Anmelden und eigene Daten"),
    "mfa": ("zugang", "Zweiter Anmeldeschritt mit Code (TOTP) und Wiederherstellungscodes"),
    "passkey": ("zugang", "Passkeys statt Code (Face ID, Touch ID, Windows Hello)"),
    "coadmin": ("zugang", "Profile als Admins: Admin und Verwalter, ohne zweite Stufe"),
    "stufen": ("zugang", "Liste, welche Änderung den Code verlangt"),
    "features": ("zugang", "Alle Funktionen mit Namen und Freigaben an einer Stelle"),
    "join": ("zugang", "Neue Personen per Einladung"),
    "notaus": ("zugang", "Notaus in drei Stufen, von außen nach innen"),
    "notzugang": ("zugang", "Wieder hinein nach einem Aussperren (nur per sudo am Spark)"),
    "vault": ("zugang", "Versiegelt Passwörter und Tokens mit state/secret.key"),
    "signatur": ("zugang", "Prüft signierte Update-Manifeste (Ed25519)"),
    "zertpin": ("zugang", "Zertifikat eines Geräts im Heimnetz festpinnen"),
    "netguard": ("zugang", "Wächter: wohin eine Verbindung nach außen darf"),
    # Gespräch
    "chat": ("gespraech", "Der Assistent: /api/chat, Runden mit dem Modell, Text und Ton als Strom"),
    "llm": ("gespraech", "Der eine Weg zum Sprachmodell: Adresse, Schlüssel, Modellname, Aufruf"),
    "chat_modell": ("gespraech", "Die Modellseite einer Antwort: fragt das Sprachmodell, ruft Werkzeuge, schreibt Sätze"),
    "chat_ton": ("gespraech", "Die Sprachausgabe einer Antwort: Satz für Satz an die Sprachausgabe, Ton als Strom"),
    "chat_turn": ("gespraech", "Bereitet eine Anfrage vor: Rechte, Sperren, Systemprompt, Werkzeuge"),
    "chat_tools": ("gespraech", "Führt die Werkzeugaufrufe des Modells aus und prüft die Sperren erneut"),
    "answercheck": ("gespraech", "Antwort-Prüfung: das Panel entscheidet, ob ein Satz gesagt werden darf"),
    "taten": ("gespraech", "Handlungs-Prüfung: hat ein Werkzeug wirklich getan, was der Satz sagt"),
    "ack": ("gespraech", "Sofortige Rückmeldung aus aufgenommenen Sätzen"),
    "klaeren": ("gespraech", "Rückfrage, Korrektur und Merken von Zuordnungen"),
    "vorab": ("gespraech", "Holt bei einer Rückfrage die Antwort schon vorab"),
    "hoerwoerter": ("gespraech", "Namen fürs Hören: Räume, Geräte und Personen als Kontext für die Spracherkennung"),
    "sofort": ("gespraech", "Einfaches sofort beantworten: Uhrzeit, Datum, Rechnen und Einheiten als fester Satz ohne Modell"),
    "fixes": ("gespraech", "Lernt aus Korrekturen der Person"),
    "roles": ("gespraech", "Rollen: wie der Assistent antworten soll"),
    "stille": ("gespraech", "Aus Stille werden nie Wörter"),
    "fremdstimme": ("gespraech", "Fernseher und fremde Stimmen im von selbst geöffneten Mikrofon werden keine Frage"),
    "echo": ("gespraech", "Der Assistent antwortet nicht auf seine eigene Stimme"),
    "zwischenruf": ("gespraech", "Ins Wort fallen: die Antwort hält an, feste Wörter entscheiden weiter, stopp oder neue Frage"),
    "satzende": ("gespraech", "Satzende am Tonfall: misst an jeder Sprechpause Smart Turn gegen die Wortliste, nur Zahlen"),
    "images": ("gespraech", "Bilder in der Frage: das Sprachmodell sieht sie selbst"),
    "schreib": ("gespraech", "Schreibhilfe: korrigieren, kürzen, übersetzen, entwerfen"),
    "systemone": ("gespraech", "Einordnung mit Wahrscheinlichkeit über das Sprachmodell (LLM-Tor oder qwen38)"),
    "tipps": ("gespraech", "Schlägt passende Funktionen vor, die noch aus sind"),
    "ablauf": ("gespraech", "Zeigt unter der Antwort die benutzten Werkzeuge und einen wartenden Vorschlag als Karte mit Ja und Nein"),
    "saetze": ("gespraech", "Zeigt Sätze für Funktionen, die an sind und noch nie benutzt wurden"),
    "spickzettel": ("gespraech", "Spickzettel zum Ausdrucken: was das Profil sagen kann, aus den Regeln der Weiche erzeugt"),
    "stufe": ("gespraech", "Vorrang für Personen in der Warteschlange der Sprachausgabe"),
    # Weiche
    "intent": ("weiche", "Die Weiche: feste Regeln für die eigene letzte Nachricht"),
    "intent_bench": ("weiche", "Testsätze der Weiche"),
    "intent_alltag": ("weiche", "Alltagssätze der Weiche: nur zum Messen"),
    "weiche": ("weiche", "Seite Funktionen → Weiche und ihre Statistik"),
    "werkzeuge": ("weiche", "Verständliche Namen aller Werkzeuge"),
    "werkzeug_abdeckung": ("weiche", "Welche Funktion das Modell mit welchem Werkzeug erreicht (Regel 29)"),
    # Wissen
    "wissen": ("wissen", "Wissen aus eigenen Uploads: Schalter und Kontingent"),
    "documents": ("wissen", "Dokumente pro Profil in wissen.db: Text, Abschnitte mit Kontextzeile, Suche"),
    "pdftabellen": ("wissen", "Tabellen in PDFs zeilenweise lesen: eine Zeile bleibt ein Eintrag mit Kopfzeile"),
    "doclingdienst": ("wissen", "Docling-Server im Heimnetz: Dokumente und Scans besser lesen"),
    "suchpruefung": ("wissen", "Suchprüfung: Prüffragen messen, wie gut die Dokumentensuche trifft"),
    "wissensbuch": ("wissen", "Wissensbuch: Seiten aus den eigenen Dokumenten, jeder Satz mit Quelle"),
    "wissenskarte": ("wissen", "Wissenskarte: geprüfte Verbindungen zwischen den Seiten des Wissensbuchs, jede mit Quelle"),
    "nachsortieren": ("wissen", "Treffer nachsortieren: ein Cross-Encoder auf dem Prozessor ordnet die Kandidaten"),
    "docembed": ("wissen", "Bedeutungsvektoren für die Dokumentsuche"),
    "embed_worker": ("wissen", "Das Vektormodell im eigenen Prozess"),
    "gedaechtnis": ("wissen", "Gedächtnis mit Beleg und Prüfung"),
    "recall": ("wissen", "Suche in früheren Gesprächen, gelernte Fakten"),
    "memtidy": ("wissen", "Wöchentliches Aufräumen des Gedächtnisses"),
    "lokal": ("wissen", "Erst lokal suchen, bevor etwas nach außen geht"),
    "kiwix": ("wissen", "Eigenes Kiwix als Wissensquelle ohne Internet"),
    "wiki": ("wissen", "Wikipedia für „Was ist …?“"),
    "docmake": ("wissen", "Dokumente erstellen: Aufträge, Vorlagen, Ablage"),
    "bilder": ("wissen", "Bilder malen: Wunsch prüfen, Auftrag, Ablage, Bildkarte"),
    "musik": ("wissen", "Musik machen: Wunsch prüfen, Modell wählen, Auftrag, Ablage, Liedkarte, Musik testen je Modell"),
    "schwer": ("wissen", "Schwere Aufträge: eine Warteschlange für Bild und Musik, immer nur ein Modell, Platz und Wartezeit"),
    "docrender": ("wissen", "Baut die Dateien (Word, PDF, PowerPoint, Excel) mit festem Code"),
    "folien": ("wissen", "Folientypen und feste Regeln für erstellte Dokumente"),
    "symbole": ("wissen", "Feste Symbole für Folien und Dokumente"),
    "tagebuch": ("wissen", "Spark-Tagebuch: was der Spark selbst getan hat"),
    # Anbindungen
    "homeassistant": ("dienste", "Home Assistant pro Profil"),
    "hamelden": ("dienste", "Home Assistant meldet Ereignisse an den Spark"),
    "mail": ("post", "Mail lesen per IMAP"),
    "tidy": ("post", "Posteingang aufräumen"),
    "senden": ("post", "Mails senden auf der Seite E-Mail: Vorschau-Blatt, SMTP über TLS, Kopie in Gesendet, Später senden versiegelt"),
    "antwortvorschlag": ("post", "Antwortvorschläge beim Antworten auf eine Mail: drei Richtungen, umformen, nur im Speicher"),
    "postfach": ("post", "Mails ordnen auf der Seite E-Mail: gelesen, markieren, Archiv, Ordner, Mehrfachauswahl, Löschen in den Papierkorb"),
    "mailregeln": ("post", "Mail-Regeln: wenn Absender/Betreff, dann Ordner, gelesen, markieren; nie löschen; Vorschläge nachts, Statistik"),
    "ichweiss": ("dienste", "Was ich über dich weiß: Interessen als Themen mit Beleg, Wiederkehrendes, Woche, Monat, ein Netz-Tipp am Tag"),
    "fuerdich": ("dienste", "Für dich: findet Rechnungen, Verträge, Bestellungen, Angebote, offene Antworten, Phishing; letzte Lesung versiegelt"),
    "mailansicht": ("post", "Mail formatiert (Seite E-Mail, iPhone): HTML bereinigt, Rahmen ohne Skript, Bilder von außen nur per Klick"),
    "mailvorrat": ("post", "Mail-Vorrat: neueste Kopfzeilen und Texte versiegelt im Profil, Antwort mit Stand bei Ausfall"),
    "frisch": ("gespraech", "Tagesaktuell: jede Quelle gegen heute geprüft, Websuche mit Zeitraum, Stand mit Tag, Hinweis wenn alt"),
    "vorrat": ("dienste", "Vorrat je Profil: Antworten aus dem Speicher, solange frisch genug; versiegelt auf der Platte (Mail, Wetter, Pakete)"),
    "einordnen": ("post", "Alle Mails eines Ordners einordnen: nach Regeln und Aufräum-Stufen, erst Vorschlag, Rückgängig versiegelt"),
    "mailcode": ("post", "Bestätigungscodes: Code aus neuer Mail als Mitteilung aufs genutzte Gerät, nie Telegram, nie im Log"),
    "mailidle": ("post", "Neue Mails sofort: IMAP IDLE für Profile, die ihre Mails gerade lesen, höchstens 4 Verbindungen"),
    "mailstil": ("post", "Mailstil: lernt aus gesendeten Mails, wie das Profil schreibt, für Mail-Entwürfe"),
    "parcels": ("dienste", "Pakete aus Versand-Mails"),
    "geteilt": ("dienste", "Teilen mit Profilen: Dokumente an einzelne Profile, Ich → Geteilt, zurückziehen sofort"),
    "calendars": ("post", "Kalender und Tagesbriefing, einzelne Kalender mit anderen Profilen geteilt"),
    "dungeon_dingbild": ("dienste", "KI-Dungeon-Master: Bilder für Ausrüstung und Zauber, nachts oder auf Knopf gemalt, eigene Bilder für benannte Fundstücke"),
    "dungeon": ("dienste", "KI-Dungeon-Master: Rollenspiel bis 5 per Link; Panel würfelt, Beute, Kampagnen, Geschichten in Akten, Vorlesen"),
    "dungeon_karte": ("dienste", "Dungeon-Master-Karte: Panel würfelt Ortsnetz mit Nebel und Gewölbe (Fallen, Rätsel), Plan gezeichnet; Bilder je Ort"),
    "dungeon_musik": ("dienste", "KI-Dungeon-Master: Musik je Welt und Stimmung im Voraus (Akt n+1, nachts), Geräusche und Würfel im Browser"),
    "dungeon_lied": ("dienste", "Dungeon-Master: Heldenlied des Barden, am Kapitelende feste Strophen mit Heldennamen, gesungen vom Musikmodell"),
    "dungeon_echt": ("dienste", "Dungeon-Master: echte Würfel am Tisch, ein Platz gibt seine Zahl, das Panel prüft und würfelt weiter"),
    "dungeon_ehre": ("dienste", "Dungeon-Master: Ehrungen des Abends, Titel und Urkunden aus den eigenen Würfeln des Panels"),
    "dungeon_schrift": ("dienste", "Dungeon-Master: Schriftstücke als Pergament, der Gastgeber bestimmt, wer sie sieht"),
    "dungeon_kommentar": ("dienste", "Dungeon-Master: Helden kommentieren selbst, je Held, der gehandelt hat, eine kurze geprüfte Zeile in seiner Stimme"),
    "dungeon_personen": ("dienste", "Dungeon-Master: Personen-Katalog, getroffene Personen bleiben und begegnen den Helden wieder"),
    "dungeon_gefaehrte": ("dienste", "Dungeon-Master: Gefährten anheuern in der Siedlung, Hiebe, Moral und Lohn nach festen Regeln des Panels"),
    "dungeon_wunsch": ("dienste", "Dungeon-Master: Herzenswunsch je Held, geheim, je Akt einer reihum für den Erzähler, Erfahrung nach fester Regel"),
    "dungeon_fluestern": ("dienste", "Dungeon-Master: Flüstern mit einer Figur, die Antwort nur für den eigenen Platz, Verrat würfelt das Panel"),
    "dungeon_alarm": ("dienste", "Dungeon-Master: Alarm und Fackeln im Gewölbe, Lärm weckt Streife und Herrn, Licht für 4 Räume"),
    "dungeon_umgebung": ("dienste", "Dungeon-Master: Umgebung nutzen, Kronleuchter, Fässer und Säulen im Kampf, eine Probe, eine feste Wirkung"),
    "dungeon_haltung": ("dienste", "Dungeon-Master: Gegner-Ansagen und Haltung, der nächste Hieb vorher, Abwehr und Ausweichen"),
    "dungeon_rueckfrage": ("dienste", "Dungeon-Master: Rückfrage bei unklaren Aktionen, feste Regeln und Vorschläge aus der Szene"),
    "dungeon_geschichten": ("dienste", "Dungeon-Master: Eigene Geschichten der Gastgeber, bearbeiten, kopieren, ausblenden, neu"),
    "dungeon_buch": ("dienste", "Dungeon-Master: Heldenbuch je Held als PDF im Format des reMarkable, Farbe oder Graustufen"),
    "dungeon_chronik": ("dienste", "Dungeon-Master: Chronikbuch, eine Seite je Kapitel aus den Daten der Runde, als PDF auf dem Spark"),
    "dungeon_kalender": ("dienste", "Dungeon-Master: Kalender der Welt, Monate, Monde und Feste, die Zeit läuft nur über Wege, Rasten und das Gasthaus"),
    "dungeon_zeugen": ("dienste", "Dungeon-Master: Zeugen-Regel, Taten vor Leuten ändern ihre Haltung nach fester Tabelle"),
    "dungeon_wandern": ("dienste", "Dungeon-Master: Wandernde Personen bei langer Rast als Gerücht, kleine Gesten der Personen beim Warten"),
    "dungeon_auftraege": ("dienste", "Dungeon-Master: Aufträge von Personen, Art, Ziel, Lohn und Spuren vom Panel, erfüllt nur durch Belege"),
    "dungeon_mitkommen": ("dienste", "Dungeon-Master: Überreden zum Mitkommen, Haltung und Charisma-Probe des Panels, die Karte nimmt die Person mit"),
    "dungeon_gedanken": ("dienste", "Dungeon-Master: Gedanken lesen, Probe vom Panel, Wunsch und Geheimnis nur für den lesenden Platz"),
    "dungeon_anleiten": ("dienste", "Dungeon-Master: Spieler anleiten (Ansatzpunkte, Knöpfe, stille Spieler), Fortschritt der Geschichte (Wink, Spuren)"),
    "dungeon_tageszeit": ("dienste", "Dungeon-Master: Tageszeit vom Panel, Morgen bis Nacht nach Kalender und Zügen, nachts Läden zu und Dunkelheit ohne Licht"),
    "dungeon_sprachen": ("dienste", "Dungeon-Master: Sprachen der Völker, fremde Laute aus den Namenssilben, die Bedeutung nur für wer die Sprache kann"),
    "dungeon_reise": ("dienste", "Dungeon-Master: Reise-Etappen, Rollen mit je einem Wurf und ein Ereignis der Landschaft auf langen Wegen"),
    "dungeon_rast": ("dienste", "Dungeon-Master: Lagerfeuer und Rast, kurze und lange Rast mit drei Nachtwachen je Landschaft und Fragekarten"),
    "dungeon_narben": ("dienste", "Dungeon-Master: Narben und bleibende Wunden nach fester W20-Tabelle, ein Heiler in der Siedlung nimmt die Folgen"),
    "dungeon_album": ("dienste", "Dungeon-Master: Monster-Album, je Held die besiegten Gegner und die getroffenen Personen, mehr Wissen je Stufe"),
    "dungeon_helfen": ("dienste", "Dungeon-Master: Helfen und Gruppenprobe, feste Regeln auf den Würfen des Panels"),
    "dungeon_knapp": ("dienste", "Dungeon-Master: Knapp daneben, der Platz wählt aufgeben oder zahlen, das Panel würfelt den Preis und wendet ihn an"),
    "dungeon_warten": ("dienste", "Dungeon-Master-Wartezeit: feste Schritte, Würfel vorab, Wissenskarten, Tipps, Tischgespräch"),
    "dungeon_regelseite": ("dienste", "Dungeon-Master-Regeln als Reiter: Katalog, Bestiarium, Runen, Karte, Zahlen, Ändern und Ausblenden, Bild nochmal malen"),
    "dungeon_balance": ("dienste", "Dungeon-Master-Gleichgewicht: feste Tabellen markieren Gegner und Gegenstände als ausgewogen, stark oder zu stark"),
    "dungeon_import": ("dienste", "Dungeon-Master-Abenteuer-Import: ein geschriebenes Abenteuer wird ein Entwurf im Geschichten-Planer, feste Regeln prüfen"),
    "dungeon_erzaehlstand": ("dienste", "Dungeon-Master-Erzähler-Prüfstand: feste Szenen durch das laufende Modell, feste Regeln geben Punkte"),
    "dungeon_protokoll": ("dienste", "Dungeon-Master-Protokoll-Prüfer: jede Erzählung noch einmal durch alle festen Prüfungen, Runden als Prüffälle"),
    "dungeon_pruefstand": ("dienste", "Dungeon-Master-Balance-Prüfstand: spielt Kämpfe mit den echten Regeln allein durch, nachts oder auf Knopf, ohne Modell"),
    "dungeon_gast": ("dienste", "Dungeon-Master-Gast-Konten: Code per Mail, Helden aufbewahren, Zug-Mail, nur Hash der Adresse"),
    "dungeon_stimmen": ("dienste", "Dungeon-Master-Stimmen: Erzähler je Geschichte, eigene NSC-Stimmen aus festen Merkmalen"),
    "dungeon_auto": ("dienste", "Dungeon-Master im Auto: feste Befehle mit Rückfrage, Zusammenfassung, Runde wählen und neu, Stimmen der Runde"),
    "dungeon_vorlesen": ("dienste", "Dungeon-Master-Vorlesen: Stück für Stück, Rede in der Stimme der Figur, die Uhr wartet"),
    "dungeon_gold": ("dienste", "Dungeon-Master-Gold mit Zweck: Gasthaus, Schmied, Lehrstunde und Gerücht in Siedlungen zu festen Preisen"),
    "dungeon_legenden": ("dienste", "Dungeon-Master-Legenden: 20 benannte Einzelstücke je Welt, nur aus Boss, Belohnung oder Truhe, einmal je Kampagne"),
    "dungeon_grenzen": ("dienste", "Dungeon-Master-Grenzen: Grenzen und Schleier je Platz als Wortlisten, anonyme X-Karte erzählt die letzte Szene neu"),
    "dungeon_schreiber": ("dienste", "Dungeon-Master-Schreiber: ein zweiter Modellaufruf schlägt Änderungen vor, das Panel nimmt sie nach festen Grenzen"),
    "dungeon_zufall": ("dienste", "Dungeon-Master-Zufallsregeln: eigene Regeln des Gastgebers mit Chance, Auslöser und Wirkung, das Panel würfelt"),
    "dungeon_nsc": ("dienste", "Dungeon-Master-NSC-Gedächtnis: Karten aus festen Tabellen, Haltung und Beziehungen nach festen Regeln, Chronik und Ruf"),
    "dungeon_gesicht": ("dienste", "Dungeon-Master-Gesichter: ein festes Porträt je Figur, Vorlage für spätere Szenenbilder"),
    "dungeon_wappen": ("dienste", "Dungeon-Master-Wappen: SVG für Gruppe und Fraktionen aus eigenen Teilen, geprüft, ohne Bildmodell"),
    "dungeon_fraktionen": ("dienste", "Dungeon-Master-Fraktionen: Gruppen mit Uhren, das Panel dreht sie nach festen Regeln"),
    "dungeon_quest": ("dienste", "Dungeon-Master-Quest-Gegenstände: benannte Dinge der Geschichte, das Panel prüft jeden Fund"),
    "dungeon_ideen": ("dienste", "Dungeon-Master-Ideen-Tabellen: Krit, Patzer, Landschaften, Reise, Narben, Sagen; feste Regeln prüfen"),
    "dungeon_orakel": ("dienste", "Dungeon-Master-Orakel: Ja oder Nein mit Chaosgrad und Würfe auf die Tabellen, das Panel würfelt"),
    "dungeon_tabellen": ("dienste", "Dungeon-Master-Tabellen: Würfel auf die festen Tabellen des Katalogs und Namen aus Silben"),
    "dungeon_runen": ("dienste", "Dungeon-Master: Runen und Sockel, Katalog, Sockel, Runenbeutel, Deckel, Einsetzen mit Vorschau, Runenwörter, Schmied"),
    "dungeon_geben": ("dienste", "Dungeon-Master: Spielleiter gibt Dinge, Gegenstand, Gold, Runen und EP vom Admin im Spielleiter-Pult, Grenzen des Spiels"),
    "dungeon_bestiarium": ("dienste", "Dungeon-Master: was ein Gegner ist (wesen), wer keinen Streit will und sein gemessenes Kampf-EP"),
    "dungeon_ablage": ("dienste", "Dungeon-Master-Ablage: eine Datei je Runde, Zwischenspeicher nach Änderungszeit"),
    "dungeon_sicht": ("dienste", "Dungeon-Master-Sichtfilter: jedes Geheimnis der Runde mit seinen Betrachtern, letzter Schritt jeder Ansicht"),
    "dungeon_mut": ("dienste", "Dungeon-Master-Heldenmut: einmal am Abend neu würfeln oder kritisch treffen, ein zweiter durch 👍 der Mitspieler"),
    "dungeon_kampf": ("dienste", "Dungeon-Master-Kampf: Begegnung nach Budget, Panel würfelt Angriffe gegen Rüstungsklasse"),
    "dungeon_erzaehler": ("dienste", "Dungeon-Master-Erzähler: Welt-Wahrheit, offene Fäden, Zusammenfassung, Nachbessern nach festen Regeln, Daumen"),
    "mitschreiblink": ("dienste", "Mitschreib-Link: Leute ohne Profil setzen etwas auf eine Liste (Code nach dem #, nur Hash, mit Ablauf)"),
    "listendav": ("dienste", "Listen in Erinnerungen: die Spark-Listen eines Profils als Aufgabenlisten (VTODO) des Kalender-Servers"),
    "kalenderserver": ("post", "Kalender-Server: die Spark-Kalender eines Profils für Kalender-Apps (CalDAV unter /caldav/, App-Passwort)"),
    "sparkkalender": ("post", "Spark-Kalender ohne Konto: Termine nur auf dem Spark, verschlüsselt im Profil, beantwortet CalDAV im Panel selbst"),
    "kalenderspiegel": ("post", "Spark-Kalender: verschlüsselte Kopie jedes CalDAV-Kalenders, holt nur Änderungen, Änderungen der Seite sofort"),
    "kalserie": ("post", "Kalender wie Apple: Wiederholen, Erinnerung, Personen ohne Einladung, Serie nur dieser oder alle künftigen"),
    "vorwaermen": ("dienste", "Vorwärmen: liest beim Anmelden Kalender, Mails, Für dich und Kontakte vorab in den Speicher"),
    "halive": ("dienste", "Home Assistant live: hält für aktive Profile eine Kopie aller Zustände über eine WebSocket-Verbindung"),
    "contacts": ("post", "Kontakte per CardDAV: Seite Kontakte wie Apple, ändern nur mit Schalter, zurück mit ETag"),
    "einladung": ("post", "Einladungen aus Mails: eine .ics-Einladung mit einem Tipp in den Kalender, Antwort an den Einladenden"),
    "kontaktserver": ("post", "Kontakte-Server: das Adressbuch „Auf dem Spark“ für Kontakte-Apps (CardDAV unter /carddav/)"),
    "kontaktkarte": ("post", "Kontakte ändern: Felder prüfen, nur die Zeilen der Seite in der vCard ersetzen, Rest bleibt"),
    "tasks": ("dienste", "Listen für Einkauf und Aufgaben"),
    "vorgaenge": ("dienste", "Alles Offene im Assistenten: Karten mit Knöpfen, Später, Seite Offen, Ja-Knopf, Telegram-Knöpfe"),
    "weather": ("dienste", "Wetter von Open-Meteo als feste Sätze"),
    "transit": ("dienste", "Bus und Bahn"),
    "feeds": ("dienste", "Reddit und Feeds: eigener Reddit-Posteingang, Subreddits und RSS, nur lesen"),
    "extras": ("dienste", "Kleine Zusatzdienste mit ihren Werkzeugen"),
    "mcp": ("dienste", "Werkzeuge von MCP-Servern, die der Admin einträgt"),
    "meinmcp": ("dienste", "Eigene MCP-Dienste pro Profil"),
    "mcpserver": ("dienste", "Der Spark als MCP-Server für andere Programme"),
    "remarkable": ("dienste", "reMarkable-Notizbücher als Wissen"),
    "rmliste": ("dienste", "Werkzeug: was auf dem reMarkable liegt und welche Aufgaben dort stehen"),
    "aendern": ("dienste", "Ändern per Sprache: Lautstärke, Termine und anderes nach „Ja“"),
    "zustand_wz": ("dienste", "Werkzeug: Zustand des Spark per Sprache („Läuft alles?“)"),
    "rechnen": ("gespraech", "Rechnen mit festem Werkzeug: eigener Parser statt eval, Datumsrechnung, Nachrechnen in Antworten"),
    "rmplus": ("dienste", "Mehr mit dem reMarkable: Senden, Ordner, Abgleich"),
    "rmpapier": ("dienste", "Gestaltete Blätter fürs reMarkable"),
    "rmaufgaben": ("dienste", "Aufgabenblatt zum Ankreuzen aufs reMarkable"),
    "agent": ("dienste", "Aufträge im Hintergrund, Zeitpläne, Routinen"),
    "beobachten": ("dienste", "Beobachten: Funde prüfen, nur Neues melden (Eigene Aufgaben)"),
    "auftragsplan": ("dienste", "Aufträge mit Plan, Rückfrage, Vorschlag mit Ja und Nachschieben"),
    "proactive": ("dienste", "Meldet sich von selbst, wenn etwas Echtes passiert"),
    # Geräte und Kanäle
    "telegram": ("geraete", "Telegram-Bot für Text und Sprachnachrichten"),
    "iphone": ("geraete", "iPhone-App: Kopplung und Rechte"),
    "android": ("geraete", "Android-App: Download, Mitteilungen, Update, Assistent und Fingerabdruck"),
    "apns": ("geraete", "Mitteilungen an die iPhone-App"),
    "push": ("geraete", "Web-Push für Erinnerungen"),
    "zustellung": ("geraete", "Mitteilung ans genutzte Gerät: Geräte sagen „gerade benutzt“, sonst die Handy-App"),
    "mitteilungen": ("geraete", "Mitteilung antippen: die Meldung einen Tag mit Nummer, als Karte über dem Gespräch"),
    "appupdate": ("geraete", "Spark-Update aus der iPhone-App"),
    "pruefzugang": ("geraete", "Prüfzugang für die iPhone-App: Code für Apples Prüfung, was er sperrt, Löschen mit den iPhones"),
    "appmerken": ("geraete", "Apps merken sich den letzten Stand: ob eine App ihn behalten darf, langsame Seiten ins Log"),
    "pebblewatch": ("geraete", "Kopplung der Pebble-Uhr"),
    "terminal": ("geraete", "Terminal-Client spark-tui: Kopplung mit gepinntem Zertifikat, Schlüssel nur für Chat, Heute, Aufträge"),
    "kopplung": ("geraete", "Einmal-Codes zum Koppeln: iPhone, Pebble, Schreibhilfe, Begleiter, Terminal"),
    "watch": ("geraete", "Antworten für die Uhr"),
    "esp32": ("geraete", "Eigene ESP32-Lautsprecher und ihre Firmware"),
    "geraeteupdate": ("geraete", "Übersicht und Hinweise zu Geräte-Updates"),
    "wyoming": ("geraete", "Home Assistant Assist über Wyoming"),
    "telefon": ("geraete", "Den Spark anrufen: SIP mit der Telefonanlage, Gespräch wie am Lautsprecher"),
    "telefon_ton": ("geraete", "Ton am Telefon: G.722, G.711 und Umrechnen der Abtastrate"),
    "telefon_ich": ("geraete", "Ich → Telefon: eigene Rufnummern mit Code, Telefon-PIN, Telefonate"),
    "telefon_anruf": ("geraete", "Der Spark ruft an: Weckruf, Erinnerung, Rückruf, Alarm bei Dienstausfall"),
    "begleiter": ("geraete", "Spark-Begleiter für Windows und Mac"),
    "fernsicht": ("geraete", "Bildschirm zeigen und bedienen: Bilder vom Begleiter ins Panel, Eingaben zurück"),
    "bedienen": ("geraete", "Spark bedient den Rechner: ein Schritt nach dem anderen, jeder am Rechner bestätigt"),
    "speakers": ("geraete", "Sprechererkennung pro Profil"),
    "spkcode": ("geraete", "Codewort am geteilten Lautsprecher"),
    "room": ("geraete", "Raummodus: hört zu und hilft in einer Pause"),
    "roomfar": ("geraete", "Raummodus auf einem anderen Gerät schalten"),
    "roomlive": ("geraete", "Wo der Raummodus gerade zuhört"),
    "chats": ("geraete", "Chats zwischen den Profilen, verschlüsselt"),
    "verbund": ("geraete", "Spark-Verbund: Chats mit Menschen auf anderen Sparks, signiert, mit Fotos und Dateien"),
    "verbundgruppe": ("geraete", "Gruppen mit anderen Sparks: die Gruppe gehört ihrem Spark, der sie an die anderen weiterreicht"),
    "anrufe": ("geraete", "Anrufe mit Sprache und Video in Chats zu zweit, Vermittler (TURN) für unterwegs"),
    "rufen": ("geraete", "Anrufe per Assistent: „Ruf Sabine an“ nach festen Regeln, erst nach Ja; Android auch übers Telefon"),
    "chatsec": ("geraete", "Private Chats mit Ende-zu-Ende-Verschlüsselung"),
    "messages": ("geraete", "Der Weg des Assistenten in die Chats"),
    "verlauf": ("geraete", "Verlauf auf allen Geräten gleich"),
    "sse": ("geraete", "Sofort-Ereignisse an offene Seiten und Apps (Chats, Verlauf): ein Strom pro Seite"),
    "today": ("geraete", "Die Karte „Heute“ oben in Ich"),
    "onboard": ("geraete", "Einrichten an der Hand"),
    "hintergrund": ("geraete", "Ich → Mein Zustand"),
    # Betrieb
    "admin": ("betrieb", "Admin-Seiten: Zustand, Einstellungen, Dienste, Stimmen"),
    "system": ("betrieb", "Sicherung, Echtprüfung der Dienste, Hinweise oben"),
    "monitor": ("betrieb", "Messwerte: GPU, Speicher, CPU"),
    "steuer": ("teilen", "Einheiten der Modelle und GPU: hier oder über den Wärter des Modell-Rechners"),
    "notbetrieb": ("teilen", "Notbetrieb mit Parakeet: feste Befehle ohne Sprachmodell, wenn der Modell-Rechner fehlt"),
    "umziehen": ("teilen", "Spark teilen: Umzugs-Sicherung packen und einspielen, wenn das Panel den Rechner wechselt"),
    "health": ("betrieb", "Stabilität: Wächter für hängende Dienste, Echtprüfung"),
    "loopwacht": ("betrieb", "Hänge-Wächter: Logzeile mit der Stelle, wenn das Panel hängt; systemd startet es neu"),
    "live": ("betrieb", "Live-Übersicht: was der Spark gerade tut"),
    "tracelog": ("betrieb", "Logs → Anfragen: der Weg jeder Anfrage"),
    "aktiv": ("betrieb", "Aktiv in den letzten 10 Minuten: Profile und Gäste als Zahl, nur im Speicher (OLED, Monitoring, Live)"),
    "logfilter": ("betrieb", "Diagnose-Filter und Hinweise für die Logs"),
    "latency": ("betrieb", "Wartezeit bis zum ersten Ton"),
    "verbrauch": ("betrieb", "Verbrauchszähler je Modell, Aufgabe und Profil, Kontingent für Tag, Woche und Monat"),
    "dienstwacht": ("betrieb", "Dienst-Wächter: meldet, wenn ein Dienst fehlt"),
    "offline": ("betrieb", "Ohne Internet: Modelle, Uhren, Zeitserver und Namen im Heimnetz auf Knopfdruck geprüft"),
    "wartung": ("betrieb", "Wartungspause: Spark hält an, während ein Modell neu eingespielt wird"),
    "faelle": ("betrieb", "Fälle: jedes Problem wird festgehalten"),
    "befund": ("betrieb", "Befund: die Ursache eines Falls"),
    "klartext": ("betrieb", "Klartext eines Falls: was, woher, warum, was hilft; Fehlercodes in Worten"),
    "berater": ("betrieb", "Einstellungs-Assistent: Vorschläge aus Fällen"),
    "berater_katalog": ("betrieb", "Was der Einstellungs-Assistent vorschlagen darf"),
    "quality": ("betrieb", "Qualitätstest gegen das echte Sprachmodell"),
    "backup": ("betrieb", "Sicherungen und Wiederherstellen"),
    "dateien": ("betrieb", "Datei-Register: jede Datei des Panels einmal, mit Inhalt, Sicherung und Kopie"),
    "offsite": ("betrieb", "Sicherung nach außen, verschlüsselt"),
    "speicher": ("betrieb", "Kopie meiner Daten pro Profil an einem Speicherort, verschlüsselt"),
    "nas": ("betrieb", "Speicher und NAS: Speicherorte (NAS, Cloud), eine Anmeldung pro Ort für Kopie und Sicherung"),
    "nasquelle": ("betrieb", "Wissensordner und Haushaltsordner: Ordner an einem Speicherort nur lesen und in die Dokumentensuche bringen"),
    "auslassen": ("betrieb", "Ordner auslassen: Liste je Profil mit Ordnern und Namen, die der Spark nie liest; schon Gelesenes verlässt die Suche"),
    "nasablage": ("betrieb", "Ablage-Ordner: spark_ablage im Heimnetz, der einzige Ordner, in den der Spark schreibt; Eingang wird zu Dokumenten"),
    "gehaeuse": ("teilen", "Gehäuse des Panel-Rechners (Pironman 5): OLED-Seiten für den Admin, Status-LEDs, Lüftergrenzen"),
    "naszustand": ("betrieb", "Zustand der NAS: Volumes, Pools, USB-Platten, RAID, Festplatten und Temperatur über SNMPv3 (nur lesen, nur Admin)"),
    "nashilfe": ("betrieb", "NAS im Heimnetz finden (nur mDNS) und Rechte am Ort zeigen, mit Warnung bei Admin-Konto"),
    "update": ("betrieb", "Updates von GitHub, nur nach grünem Test"),
    "ghtoken": ("betrieb", "Lese-Token für GitHub"),
    "meldung": ("betrieb", "Probleme melden als GitHub-Issue"),
    "undo": ("betrieb", "Rückgängig im Admin-Protokoll"),
    "hilfe": ("betrieb", "Spark-Hilfe und Index der Doku"),
    "wege": ("betrieb", "Sprung-Links in Texten außerhalb des Panels"),
    "praxistest": ("betrieb", "Zustand → Praxistest: die Prüfpunkte aus praxistest.json, je Punkt klappt, Problem oder später (nur Admins)"),
    "weiche_abstimmen": ("weiche", "Weiche abstimmen: Wortvorschläge des Sprachmodells, mit festen Regeln an den Alltagssätzen gemessen"),
    "weiche_unklar": ("weiche", "Unklare Fragen anonym: feste Schwärzung (wie Probleme melden), Leck-Prüfung, versiegelt, 7 Tage, nur Admin"),
    "werkstattseite": ("betrieb", "Zustand → Werkstatt: Aufträge anfragen, rote Tests noch mal, Ergebnisse mit nächsten Schritten, feste Nachtregel"),
    "angriffsprobe": ("betrieb", "Angriffsprobe: wie oft das echte Sprachmodell Befehlen in fremdem Text folgen würde, nur Zahlen, kein Werkzeug läuft"),
    "modellseite": ("betrieb", "Zustand → Modelle: Katalog, Speicher-Budget, Messen, Wechseln und Zurückholen, eigene Modelle hinzufügen und löschen"),
    "technik": ("betrieb", "Diese Seite: Zustand → Technik und die Architektur-Doku"),
    "technik_knoten": ("betrieb", "Knoten-Seiten: jeder Kasten ganz genau, mit Ablauf, Regeln, Zahlen und Code"),
    "technik_seiten": ("betrieb", "Knoten-Seiten: der Baustein S für einen Schritt"),
    "technik_seiten_zugang": ("betrieb", "Knoten-Seiten Wächter, Middleware und Zugang, Zahlen als Platzhalter aus dem Code"),
    "technik_seiten_anfrage": ("betrieb", "Knoten-Seiten Vorbereiten, Weiche, Antwort und Werkzeuge, Zahlen als Platzhalter aus dem Code"),
    "technik_seiten_kern": ("betrieb", "Knoten-Seiten Sprachmodell, eigenes Wissen und Betrieb, Zahlen als Platzhalter aus dem Code"),
    "technik_seiten_netz": ("betrieb", "Knoten-Seiten Dienste außen, Internet, Spark teilen und Werkstatt, Zahlen als Platzhalter aus dem Code"),
    "technik_seiten_geraete": ("betrieb", "Knoten-Seiten Geräte, Apps, Kanäle, Lautsprecher und MCP, Zahlen als Platzhalter aus dem Code"),
    "technik_seiten_modelle": ("betrieb", "Knoten-Seiten Spracherkennung, Sprachausgabe und Bilder, Zahlen als Platzhalter aus dem Code"),
    "technik_seiten_daten": ("betrieb", "Knoten-Seiten Zustand, Nutzerdaten, Ablage und Logs, Zahlen als Platzhalter aus dem Code"),
    # Sprachdienste (app/)
    "asr_proxy": ("sprache", "Spracherkennung: nimmt an und reicht an die Engine durch"),
    "asr_server": ("sprache", "Spracherkennung als eigener kleiner Dienst"),
    "parakeet": ("sprache", "Zweite Spracherkennung (Parakeet) auf der CPU"),
    "smartturn": ("sprache", "Satzende am Tonfall: Smart Turn hört am Tonfall, ob ein Satz fertig klingt (nur messen)"),
    "tts_proxy": ("sprache", "Sprachausgabe: nimmt an und reicht an die Engine durch"),
    "tts_server": ("sprache", "Sprachausgabe als eigener kleiner Dienst"),
    "tempo": ("sprache", "Sprechtempo für gestreamte Sprache"),
    "kurzref": ("sprache", "Kürzere Referenz einer geklonten Stimme: schneidet an einer Pause, behält die Wörter des eigenen Textes"),
    "bild_server": ("sprache", "Bild-Dienst: startet FLUX.2 klein bei Bedarf, prüft und kennzeichnet jedes Bild"),
    "llmstart": ("sprache", "Was das eigene Sprachmodell beim Wechseln und Starten tut: feste Schritte, Zeiten, Phase der Engine, Satz für den Chat"),
    "modelle": ("sprache", "Modell-Katalog (modelle.json): Regeln je Eintrag, Prüfung der Dateien, Messen, Regeln für Wechsel und eigene Modelle"),
    "dockertor": ("sprache", "Docker-Tor: legt den Socket einer Engine in Docker (ohne Netz) auf 127.0.0.1, nur beim Messen"),
    "llm_tor": ("sprache", "LLM-Tor: Tür zum eigenen Sprachmodell mit Schlüssel, Feldgrenzen, System One und Lebensprobe"),
    "tlstor": ("teilen", "TLS-Tor: Tür des Modell-Rechners für ein Panel auf einem anderen Rechner (TLS 1.3, nur vom Panel-Rechner)"),
    "teilen": ("teilen", "Spark teilen: Firewall-Regeln für die Tür des Modell-Rechners, Fingerabdruck des Zertifikats"),
    "werkstatt": ("betrieb", "Werkstatt: feste Regeln für Aufträge, Sandbox ohne Netz und Daten, OpenCode, Code-Messung mit 10 Reparaturen"),
    "tarswart": ("teilen", "Wärter: feste Handgriffe auf dem Modell-Rechner (Zustand, Einheiten starten, GPU) für ein Panel anderswo"),
    "rechner": ("teilen", "Werte eines Rechners: CPU (auch je Dienst), Speicher, Platte, Netz, Temperatur, Strom (für beide Rechner gleich)"),
    "rundlauf": ("betrieb", "Rundlauf-Wächter: alle paar Minuten ein Probelauf durch Sprechen, Hören, Sprachmodell; meldet über den Dienst-Wächter"),
    "spontanhilfe": ("fern", "Spontanhilfe: Nummer und Link, Seite /hilfe mit eigener CSP, WebRTC zwischen zwei Browsern, Shell über den Anker"),
    "fernzugang": ("fern", "Fernzugang: Seite per Code entsperrt, Anker, Einmal-Code, Terminal mit Ticket, Host-Schlüssel fest, Shell gehalten"),
    "ferngross": ("fern", "Fernzugang, große Dateien: in Teilen mit SHA-256, per Link (curl) oder vom NAS, Prüfsumme vor dem Umbenennen"),
    "fernbild": ("fern", "Fernzugang, Bildschirm: guacd auf 127.0.0.1, VNC oder RDP durch den Anker, erst nur ansehen, höchstens 15 Bilder/s"),
    "fernanker": ("fern", "Fernzugang, Anker aktualisieren: eigener Ed25519-Schlüssel im Tresor, signierte neue Version, nie zurück"),
    "fernordner": ("fern", "Fernzugang, Ordner: eine Ebene, Name und Symbol, Reihenfolge per Ziehen, nur Ordnung, Rechte je System"),
    "fernnotiz": ("fern", "Fernzugang, Notizen je System: versiegelt, 10 Fassungen, Tresor-Hinweis, Assistent liest nur mit Haken"),
    "ferndateien": ("fern", "Fernzugang, Dateien: SFTP in derselben SSH-Verbindung, Liste, Einmal-Link zum Laden, Hochladen mit Größengrenze"),
    "wachposten": ("zugang", "Wachposten: feste Regeln auf dem Änderungsprotokoll melden den Admins Sperren, neue Zugänge, geänderten Schutz"),
    "schirm": ("teilen", "Steuerzentrale am Bildschirm: was die Textanzeige zeigt, nur lokal mit Schlüssel; der Dienst folgt dem Schalter"),
    "steuerzentrale": ("teilen", "Textanzeige auf tty1: zeichnet die Steuerzentrale, Schrift nach Auflösung, dunkel nach Zeitplan"),
    "rechnerblick": ("teilen", "Zustand → Überblick → Rechner: beide Rechner nebeneinander, Kurven, Hinweise nach festen Regeln"),
    "rechenteile": ("teilen", "Wer rechnet gerade: CPU je Teil des Panels aus seinen Threads und Hilfsprozessen"),
    "einordnung": ("sprache", "Regeln für System-One-Fragen, gemeinsam für Panel und LLM-Tor"),
    "bildmodell": ("sprache", "Bildmodelle: Varianten, Dateien mit festen Prüfsummen, Laden bei der Installation"),
    "musik_server": ("sprache", "Musik-Dienst: startet ACE-Step 1.5 bei Bedarf, prüft und kennzeichnet jedes Lied"),
    "musikmodell": ("sprache", "Musikmodelle: Varianten, Dateien mit festen Prüfsummen, Laden bei der Installation"),
    "bedarf": ("sprache", "Engine nur bei Bedarf: Kindprozess starten, nach Ruhe beenden, nur eine zur Zeit (bedarf.lock)"),
    "textnorm": ("sprache", "Text aufräumen vor der Sprachausgabe"),
    "common": ("sprache", "Gemeinsame Helfer für die Dienste: Einstellungen, Zustand"),
    "api_watchdog": ("sprache", "Wächter ohne Panel (Installationsart „api“)"),
    "bench": ("sprache", "Leistung messen"),
    "vorrang": ("sprache", "Sprache zuerst: Hintergrundarbeit wartet"),
}
NO_MODULE = {"selftest"}   # app/selftest.py runs the tests, it is not part of the Spark

# ---------------------------------------------------------------- the picture
# id -> x, y, German, English, small line, group (its modules are listed), German text, English text, extra files
KNOTEN = {
    "geraet": (24, 34, "Browser und Handy", "Browser and phone", "static/js", "", "Nimmt Sprache auf, zeigt Text, spielt Ton.",
               "Records speech, shows text, plays sound.", ["static/js/chat.js"]),
    "apps": (194, 34, "Apps", "Apps", "iPhone, Android", "", "Eigene Apps: iPhone mit Geräteschlüssel, Android mit Anmeldung wie im Browser.",
             "Own apps: iPhone with a device key, Android signed in like the browser.", ["ios/", "android/"]),
    "kanaele": (704, 34, "Telegram, Siri, Uhr", "Telegram, Siri, watch", "Kanäle", "geraete",
                "Kurze Fragen ohne Browser; den Verlauf speichert das Panel selbst.",
                "Short questions without a browser; the panel keeps the history itself.", []),
    "lautsprecher": (364, 34, "Lautsprecher/Telefon", "Speakers, phone", ":31003 · :31060", "",
                     "ESP32-Lautsprecher, Home Assistant Assist und Anrufe über die Telefonanlage.",
                     "ESP32 speakers, Home Assistant Assist and calls through the telephone system.",
                     ["esp32.py", "wyoming.py", "telefon.py", "telefon_ton.py", "telefon_ich.py", "telefon_anruf.py"]),
    "mcpc": (534, 34, "MCP-Programme", "MCP programs", "/mcp", "", "Claude, n8n, Open WebUI fragen über den MCP-Server.",
             "Claude, n8n, Open WebUI ask through the MCP server.", ["mcpserver.py"]),
    "middleware": (24, 222, "Middleware", "Middleware", "panel.py", "",
                   "Notaus, Herkunft (CSRF) und Größenlimit, in dieser Reihenfolge, bevor ein Endpunkt die Anfrage liest.",
                   "Kill switch, origin (CSRF) and size limit, in this order, before an endpoint reads the request.", ["panel.py", "notaus.py"]),
    "sicherheit": (24, 350, "Sicherheit", "Security", "alle Schichten", "",
                   "Wie alle Schutzschichten zusammenspielen: das Modell schlägt vor, das Panel entscheidet.",
                   "How all layers of protection work together: the model proposes, the panel decides.",
                   ["wachposten.py", "vault.py", "stufen.py"]),
    "zugang": (194, 222, "Anmeldung, Profil", "Login, profile", "guard · profiles", "zugang",
               "Rate-Limit, Anmeldung per Cookie oder Geräteschlüssel, Freigaben; Admin-Rechte nur aus einer Profil-Anmeldung mit zweitem Schritt. Das Profil kommt nie vom Modell.",
               "Rate limit, login by cookie or device key, releases; admin rights only from a profile login with the second step. The profile never comes from the model.", []),
    "vorbereiten": (364, 222, "Anfrage vorbereiten", "Prepare request", "chat_turn.prepare", "",
                    "Rechte und Sperren, Systemprompt, Rückfrage und die angebotenen Werkzeuge.",
                    "Rights and locks, system prompt, question back and the offered tools.", ["chat_turn.py", "klaeren.py"]),
    "weiche": (534, 222, "Weiche", "Switch", "intent.py", "weiche",
               "Grenzt die Werkzeuge mit festen Regeln ein. Passt keine, wählt das Modell höchstens eine Gruppe, die nur eingrenzt.",
               "Narrows the tools by fixed rules. If none fits, the model picks one group at most, which only narrows.", []),
    "antwort": (704, 222, "Antwort bauen", "Build answer", "chat._answer", "gespraech",
                "Runden mit dem Sprachmodell, Prüfungen, Text und Ton als ein Strom.",
                "Rounds with the language model, checks, text and sound as one stream.", []),
    "werkzeuge": (704, 350, "Werkzeuge", "Tools", "chat_tools.run", "dienste",
                  "Nur angebotene Werkzeuge laufen; Ergebnisse sind Daten, nie Befehle.",
                  "Only offered tools run; results are data, never commands.", ["chat_tools.py"]),
    "wissen": (534, 350, "Wissen", "Knowledge", "documents · wissen", "wissen",
               "Eigene Dokumente, Gedächtnis, Kiwix, erstellte Dokumente.", "Own documents, memory, Kiwix, created documents.", []),
    "waechter": (704, 476, "Wächter", "Guard", "netguard.py", "",
                 "Öffentlich, Heimnetz nur mit Erlaubnis, nie Metadaten oder eigene Ports.",
                 "Public, home network only when allowed, never metadata or own ports.", ["netguard.py"]),
    "betrieb": (364, 350, "Logs und Live", "Logs and live", "tracelog · live", "betrieb",
                "Anfrage-Verlauf, Live-Übersicht, Wächter, Sicherung. Nur feste Wörter und Zahlen.",
                "Request history, live overview, watchers, backup. Only fixed words and numbers.", []),
    "llm": (896, 344, "Sprachmodell", "Language model", ":31006 → :31016", "",
            "Das eigene Modell (vLLM) hinter dem LLM-Tor (:31006 → :31016, Bildverständnis :31017 und Hilfsmodell :31018 bei Bedarf), eingeschaltet mit "
            "speech-spark modelle llm uebernehmen; bis dahin oder nach … zurueck Qwen3.8 aus dgx-spark-qwen38 (:30001). Ein Modell "
            "in Docker (Qwen3.8 Flash Next) läuft vorerst nur zum Messen: festes Image, ohne Netz, Socket über das Docker-Tor.",
            "The own model (vLLM) behind the LLM-Tor (:31006 → :31016, image understanding :31017 and helper model :31018 on demand), switched on with "
            "speech-spark modelle llm uebernehmen; until then or after … zurueck Qwen3.8 from dgx-spark-qwen38 (:30001). A model in "
            "Docker (Qwen3.8 Flash Next) runs only to be measured for now: pinned image, no network, socket through the Docker-Tor.",
            ["llm_tor.py", "einordnung.py", "modelle.py", "dockertor.py"]),
    "asr": (896, 196, "Spracherkennung", "Speech recognition", ":31001 → :31011", "sprache",
            "Proxy nimmt an, die Engine läuft nur lokal.", "The proxy accepts, the engine runs locally only.", []),
    "tts": (896, 418, "Sprachausgabe", "Speech output", ":31002 → :31012", "",
            "Qwen3-TTS mit eigenen Stimmen.", "Qwen3-TTS with own voices.", ["tts_proxy.py", "tts_server.py", "tempo.py", "kurzref.py", "textnorm.py"]),
    "bild": (896, 490, "Bilder und Musik", "Pictures and music", ":31005 → :31015\n:31004 → :31014", "",
             "FLUX.2 klein (:31005 → :31015) und ACE-Step 1.5 (:31004 → :31014) auf dem Spark, nur lokal; jede Engine lädt "
             "beim ersten Auftrag und entlädt nach Ruhe. Immer nur eine zur Zeit: eine Warteschlange im Panel, die Sperre "
             "bedarf.lock auf dem Spark.",
             "FLUX.2 klein (:31005 → :31015) and ACE-Step 1.5 (:31004 → :31014) on the Spark, local only; each engine loads "
             "at the first job and unloads when idle. Only one at a time: one queue in the panel, the lock bedarf.lock on "
             "the Spark.",
             ["bilder.py", "bild_server.py", "bildmodell.py", "musik.py", "musik_server.py", "musikmodell.py", "bedarf.py",
              "schwer.py"]),
    "aussen": (620, 706, "Dienste im Heimnetz", "Services at home", "HA, NAS, Kiwix …", "",
               "Home Assistant, NAS, Kiwix, SearXNG und MCP-Dienste im eigenen Netz. Über den Wächter mit Stufe Heimnetz; "
               "feste Dienste mit Grund in netguard.DIRECT_OK.",
               "Home Assistant, NAS, Kiwix, SearXNG and MCP services in the own network. Through the guard at level home; "
               "fixed services with a reason in netguard.DIRECT_OK.", []),
    "internet": (780, 794, "Dienste im Internet", "Internet services", "IMAP, CalDAV, Web", "",
                 "Mail und Kalender beim Anbieter, Seiten aus der Suche, Wetter, Fahrplan, Wikipedia, reMarkable, Telegram, "
                 "Update-Prüfung. Über den Wächter oder feste Adressen; der Notaus schaltet sie ab.",
                 "Mail and calendars at the provider, pages from search, weather, transit, Wikipedia, reMarkable, Telegram, "
                 "update check. Through the guard or fixed addresses; the kill switch turns them off.", []),
    "teilen": (896, 270, "Spark teilen", "Spark split", "TLS-Tor · :31007", "teilen",
               "Nur wenn das Panel auf einem eigenen Rechner läuft: jeder Weg zu den Modellen geht durch das TLS-Tor "
               "(TLS 1.3, beim Koppeln angeheftetes Zertifikat), Befehle an den Wärter sind unterschrieben. Zustand → Überblick "
               "zeigt dann beide Rechner nebeneinander.",
               "Only when the panel runs on its own computer: every way to the models goes through the TLS-Tor "
               "(TLS 1.3, certificate pinned at the pairing), commands to the Wärter are signed. Status → Summary "
               "then shows both computers side by side.", ["tlstor.py", "tarswart.py", "teilen.py", "rechner.py"]),
    "state": (194, 610, "state/", "state/", "global", "", "Globaler Zustand: Schlüssel, Statistik, Wächter.",
              "Global state: keys, statistics, watchers.", []),
    "users": (534, 610, "users/ID/", "users/ID/", "pro Profil", "", "Alles eines Profils; kein Profil sieht den Ordner eines anderen.",
              "Everything of one profile; no profile sees another one's folder.", []),
    "ablage": (896, 610, "voices/, backups/", "voices/, backups/", "Stimmen, Backups", "",
               "Geklonte Stimmen und Sicherungen.", "Cloned voices and backups.", []),
    "werkstatt": (24, 476, "Werkstatt", "Workshop", "werkstatt.py", "",
                  "Nur für Admins: Testlauf, Code-Messung, Diagnose und Reparatur in einer Sandbox auf dem DGX, ohne Daten und "
                  "Internet; heraus kommen Zahlen und ein Patch zum Ansehen, eingespielt wird nichts. Dazu die Angriffsprobe "
                  "im Panel: nur Zahlen, kein Werkzeug läuft.",
                  "Admins only: test run, code measurement, diagnosis and repair in a sandbox on the DGX, without data and "
                  "internet; numbers and a patch to look at come out, nothing is installed. Plus the attack probe in the "
                  "panel: numbers only, no tool runs.",
                  ["werkstatt.py", "werkstattseite.py", "angriffsprobe.py"]),
    "post": (534, 476, "Post und Kontakte", "Mail and contacts", "/caldav · /carddav", "post",
             "Eigene Seiten E-Mail, Kalender, Kontakte; Abruf beim Anbieter über den Wächter, Vorrat versiegelt, "
             "Antwort mit Stand, Kalender- und Kontakte-Apps durch eine eigene Tür.",
             "Own pages E-mail, Calendar, Contacts; fetched from the provider through the guard, supply sealed, answer "
             "with its time, calendar and contacts apps through a door of their own.",
             ["mail.py", "calendars.py", "contacts.py", "mailvorrat.py", "senden.py", "kalenderserver.py", "kontaktserver.py",
              "static/js/post.js", "static/js/kalender.js", "static/js/kontakte.js"]),
    "fernzugang": (194, 350, "Fernzugang", "Remote access", "SSH · SFTP · guacd", "fern",
                   "Shell, Dateien und Bildschirm eigener Server durch ihren Anker, dazu die Spontanhilfe. Nur Admins, Seite "
                   "per Code entsperrt, Einmal-Ticket je Fenster, angehefteter Host-Schlüssel; guacd nur auf 127.0.0.1.",
                   "Shell, files and screen of own servers through their anchor, plus spontaneous help. Admins only, page "
                   "unlocked by code, one-time ticket per window, pinned host key; guacd on 127.0.0.1 only.",
                   ["static/js/fernzugang.js", "static/js/spontanhilfe.js"]),
    "fernserver": (24, 794, "Fern-Server", "Remote servers", "spark-anker", "",
                   "Eigene Server im Heimnetz oder im Internet mit dem Anker: er verbindet sich selbst hinaus zum Panel "
                   "(WSS, direkt oder über den Reverse-Proxy), kein offener Port dort.",
                   "Own servers at home or on the internet with the anchor: it connects out to the panel by itself (WSS, "
                   "directly or through the reverse proxy), no open port there.", ["anker/spark-anker.py"]),
    "journal": (364, 610, "journald", "journald", "speech-spark", "", "Alle Dienste; wie lange und wie viel, stellt der Admin ein (Standard 14 Tage, 500 MB).",
                "All services; how long and how much is set by the admin (default 14 days, 500 MB).", []),
}
KANTEN = [("geraet", "middleware"), ("apps", "middleware"), ("kanaele", "middleware"), ("lautsprecher", "middleware"),
          ("mcpc", "middleware"), ("middleware", "zugang"), ("middleware", "asr"), ("zugang", "vorbereiten"),
          ("vorbereiten", "weiche"), ("weiche", "antwort"), ("antwort", "llm"), ("antwort", "werkzeuge"),
          ("werkzeuge", "waechter"), ("waechter", "aussen"), ("waechter", "internet"), ("werkzeuge", "wissen"), ("antwort", "tts"), ("werkzeuge", "bild"),
          ("antwort", "geraet"), ("antwort", "betrieb"), ("betrieb", "state"), ("betrieb", "journal"),
          ("wissen", "users"), ("zugang", "users"), ("zugang", "state"), ("tts", "ablage"), ("zugang", "werkstatt"),
          ("werkzeuge", "post"), ("post", "waechter"), ("post", "users"),
          ("zugang", "fernzugang"), ("fernserver", "fernzugang")]
# the picture's size and one box (the browser draws from these, test_technik checks every box and line inside)
BILD = (1084, 862)
KASTEN = (156, 52)
# zones (Dominik 2026-10-14 „lan, internet, intern“, plan technische-doku/ueberblick 1+3): id -> kind (colour), German,
# English, x, y, width, height, x of the label (left of it a line passes)
ZONEN = {
    "geraete": ("geraet", "Geräte · im Heimnetz oder unterwegs", "Devices · at home or on the way", 8, 8, 864, 100, 20),
    "spark": ("spark", "DGX Spark · intern", "DGX Spark · inside", 8, 154, 1068, 524, 560),
    "panel": ("panel", "Panel :31080 / :31443 · bei Spark teilen auf eigenem Rechner",
              "Panel :31080 / :31443 · with the Spark split on its own computer", 16, 178, 860, 382, 200),
    "modelle": ("modelle", "Modelle · auf dem DGX", "Models · on the DGX", 888, 178, 180, 382, 900),
    "speicher": ("speicher", "Speicher", "Storage", 16, 588, 1052, 82, 28),
    "heimnetz": ("lan", "Heimnetz · geht raus", "Home network · going out", 8, 686, 1068, 80, 20),
    "internet": ("net", "Internet · geht raus", "Internet · going out", 8, 774, 1068, 80, 20),
}
# how a device comes in: "lan" directly in the home network, "net" on the way through the reverse proxy or a bot
REIN = {"geraet": ("lan", "net"), "apps": ("lan", "net"), "lautsprecher": ("lan",), "mcpc": ("lan", "net"), "kanaele": ("net",)}
# the look of the boxes (Dominik 2026-10-21 „alles“ after „nicht schön“): a colour bar per kind with a legend right of
# the devices, a symbol before the line of every box, and a tab on a box that only exists in one setup
FARBEN = {"geraet": ("Geräte", "Devices"), "zugang": ("Zugang und Schutz", "Access and protection"),
          "gespraech": ("Gespräch", "Conversation"), "wissen": ("Wissen", "Knowledge"),
          "post": ("Post und Kontakte", "Mail and contacts"), "betrieb": ("Betrieb", "Operation"),
          "modell": ("Modelle", "Models"), "speicher": ("Speicher", "Storage"), "aussen": ("Draußen", "Outside")}
FARBE = {**dict.fromkeys(("geraet", "apps", "kanaele", "lautsprecher", "mcpc"), "geraet"),
         **dict.fromkeys(("middleware", "zugang", "sicherheit", "waechter"), "zugang"),
         **dict.fromkeys(("vorbereiten", "weiche", "antwort", "werkzeuge"), "gespraech"),
         "wissen": "wissen", "post": "post", "fernzugang": "zugang", "fernserver": "aussen", "betrieb": "betrieb", "werkstatt": "betrieb",
         **dict.fromkeys(("llm", "asr", "tts", "bild", "teilen"), "modell"),
         **dict.fromkeys(("state", "users", "ablage", "journal"), "speicher"), "aussen": "aussen", "internet": "aussen"}
SYMBOL = {"geraet": "💻", "apps": "📱", "kanaele": "💬", "lautsprecher": "🔊", "mcpc": "🧩", "middleware": "🚦",
          "zugang": "🔑", "sicherheit": "🛡️", "waechter": "🧱", "vorbereiten": "📝", "weiche": "🔀", "antwort": "💡",
          "werkzeuge": "🛠️", "wissen": "📚", "post": "✉️", "betrieb": "📊", "werkstatt": "🧪", "llm": "🧠",
          "asr": "🎙️", "tts": "🗣️", "bild": "🎨", "teilen": "🔗", "state": "🗄️", "users": "👤", "ablage": "💾",
          "journal": "📜", "aussen": "🏠", "internet": "🌐",
          "fernzugang": "⌨️", "fernserver": "🖥️"}
LEGENDE = (892, 18)            # x, y of the legend's first row (14 apart)
NUR_BEI = {"teilen": ("nur bei Spark teilen", "only with Spark split")}
# the two doors where the devices' way enters the Spark: kind, German, English, x, y (on the edge of the zone spark)
TUEREN = [("lan", "Heimnetz: direkt", "Home network: directly", 112, 154),
          ("net", "Unterwegs: über den Reverse-Proxy", "On the way: through the reverse proxy", 290, 154)]
# every line drawn at right angles, from the edge of one box to the edge of the other ("a>b": points)
_BUS = 128
LINIEN = {
    **{f"{k}>middleware": [(x + 150, 86), (x + 150, _BUS), (102, _BUS), (102, 222)]
       for k, x in (("geraet", 24), ("apps", 194), ("lautsprecher", 364), ("mcpc", 534), ("kanaele", 704))},
    "middleware>zugang": [(180, 248), (194, 248)], "zugang>vorbereiten": [(350, 248), (364, 248)],
    "vorbereiten>weiche": [(520, 248), (534, 248)], "weiche>antwort": [(690, 248), (704, 248)],
    "middleware>asr": [(154, 222), (154, 208), (896, 208)],
    "antwort>geraet": [(742, 222), (742, _BUS), (174, _BUS), (174, 86)],
    "antwort>llm": [(860, 236), (884, 236), (884, 370), (896, 370)],
    "antwort>tts": [(860, 262), (876, 262), (876, 444), (896, 444)],
    "werkzeuge>bild": [(860, 376), (868, 376), (868, 516), (896, 516)],
    "antwort>werkzeuge": [(782, 274), (782, 350)], "werkzeuge>wissen": [(704, 376), (690, 376)],
    "werkzeuge>waechter": [(782, 402), (782, 476)],
    "waechter>aussen": [(762, 528), (762, 706)], "waechter>internet": [(822, 528), (822, 794)],
    "antwort>betrieb": [(730, 274), (730, 312), (480, 312), (480, 350)],
    "betrieb>journal": [(442, 402), (442, 610)], "betrieb>state": [(380, 402), (380, 590), (300, 590), (300, 610)],
    "zugang>state": [(350, 266), (357, 266), (357, 580), (240, 580), (240, 610)],
    "zugang>users": [(330, 274), (330, 300), (527, 300), (527, 598), (560, 598), (560, 610)],
    "wissen>users": [(534, 394), (527, 394), (527, 598), (560, 598), (560, 610)],
    "werkzeuge>post": [(720, 402), (720, 440), (650, 440), (650, 476)], "post>waechter": [(690, 502), (704, 502)],
    "post>users": [(612, 528), (612, 610)],
    "tts>ablage": [(1052, 444), (1060, 444), (1060, 636), (1052, 636)],
    "zugang>werkstatt": [(350, 266), (357, 266), (357, 440), (187, 440), (187, 502), (180, 502)],
    "zugang>fernzugang": [(272, 274), (272, 350)],
    "fernserver>fernzugang": [(172, 794), (172, 560), (272, 560), (272, 402)],
}

# where a group lives in the picture (the node that lists it)
ORT = {g: k for k, v in KNOTEN.items() for g in [v[5]] if g}

# ---------------------------------------------------------------- the way of one request
# German, English, German text, English text, code, nodes, edges ("a>b")
SCHRITTE = [
    ("Eingabe", "Input", "Das Mikrofon nimmt auf, das Panel reicht den Ton an die Spracherkennung weiter.",
     "The microphone records, the panel hands the sound to speech recognition.", "POST /api/test/asr",
     ["geraet", "middleware", "asr"], ["geraet>middleware", "middleware>asr"]),
    ("Zugang", "Access", "Notaus, Herkunft und Größe, dann Rate-Limit, Anmeldung und Profil.",
     "Kill switch, origin and size, then rate limit, login and profile.", "POST /api/chat · guard.limit · profiles.current",
     ["geraet", "middleware", "zugang"], ["geraet>middleware", "middleware>zugang"]),
    ("Vorbereiten", "Prepare", "Sprache zuerst (vorrang), andere Geräte sehen „antwortet gerade“, dann Rechte, Sperren, Systemprompt.",
     "Speech first (vorrang), other devices see \"answering\", then rights, locks, system prompt.", "chat_turn.prepare()",
     ["zugang", "vorbereiten"], ["zugang>vorbereiten"]),
    ("Weiche", "Switch", "Feste Regeln grenzen die Werkzeuge ein; ein klarer Lesewunsch läuft direkt.",
     "Fixed rules narrow the tools; a clear reading request runs directly.", "intent.classify_cfg() · intent.narrow()",
     ["vorbereiten", "weiche"], ["vorbereiten>weiche"]),
    ("Modell", "Model", "Sofort-Satz, Anfrage-Verlauf, dann Runden mit dem Sprachmodell, gestreamt.",
     "Instant sentence, request trace, then rounds with the language model, streamed.", "chat._answer()",
     ["weiche", "antwort", "llm"], ["weiche>antwort", "antwort>llm"]),
    ("Werkzeuge", "Tools", "Werkzeugaufruf, Wächter, Dienst im Heimnetz oder im Internet oder eigenes Wissen; das Ergebnis geht als Daten zurück.",
     "Tool call, guard, a service in the home network or on the internet, or own knowledge; the result comes back as data.",
     "chat_tools.run() · netguard",
     ["antwort", "werkzeuge", "waechter", "aussen", "internet", "wissen"],
     ["antwort>werkzeuge", "werkzeuge>waechter", "waechter>aussen", "waechter>internet", "werkzeuge>wissen"]),
    ("Antwort", "Answer", "Sätze gehen an die Sprachausgabe; Text und Ton kommen als ein Strom zum Gerät.",
     "Sentences go to speech output; text and sound reach the device as one stream.", "SSE · /v1/audio/speech",
     ["antwort", "tts", "geraet"], ["antwort>tts", "antwort>geraet"]),
    ("Speichern", "Store", "Das Gerät legt den Verlauf ab, das Panel Werkzeug-Log, Gedächtnis, Tagebuch, Anfrage-Verlauf und Journal.",
     "The device stores the history, the panel the tool log, memory, diary, request trace and journal.",
     "PUT /api/profile/convos · tracelog.finish",
     ["geraet", "middleware", "zugang", "users", "wissen", "antwort", "betrieb", "state", "journal"],
     ["geraet>middleware", "middleware>zugang", "zugang>users", "wissen>users", "antwort>betrieb", "betrieb>state", "betrieb>journal"]),
]

# ---------------------------------------------------------------- where data lies
# what is in a file (German, English), what is sealed, the profile files with their own helper, the files directly
# under users/ and the state/ files the scans cannot see: built from the register dateien.py (one line per file)
INHALT, VERSCHLUESSELT, USERS_SONST = dateien.INHALT, dateien.VERSCHLUESSELT, dateien.USERS_SONST
USERS_GLOBAL, STATE_SONST = dateien.USERS_GLOBAL, dateien.STATE_SONST
# the kinds of dateien.LOCAL and USERS_SONST in English
KAT_EN = {"Einstellungen": "Settings", "Gesundheit": "Health", "Zustand": "State", "Login": "Login", "Gerät": "Device", "Stimmabdruck": "Voiceprint",
          "Schlüssel": "Key", "noch nicht angeboten": "not offered yet", "Warteschlange": "Queue", "Termine": "Appointments", "Mails": "Mails",
          "alte Sprachnachrichten (bis zur Übernahme in die Chats)": "old voice messages (until moved into the chats)"}
# the Spark's own places outside state/ and users/
SYSTEM = [
    ("/etc/speech-spark/config.json", ("Alle Einstellungen (Geheimnisse versiegelt)", "All settings (secrets sealed)"), "ja", ("teils", "partly")),
    ("/etc/speech-spark/panel.env, mode, connection.txt", ("Start-Passwort, Installationsart, API-Zugang", "Start password, install mode, API access"), "nein", ("", "")),
    ("/etc/speech-spark/tls/", ("HTTPS-Zertifikat des Panels", "Panel HTTPS certificate"), "nein", ("", "")),
    ("/opt/speech-spark/", ("Code, venvs, installierte Version", "Code, venvs, installed version"), "nein", ("", "")),
    ("/var/lib/speech-spark/hf/", ("Modell-Cache (HuggingFace)", "Model cache (HuggingFace)"), "nein", ("", "")),
    ("/var/lib/speech-spark/firmware/", ("ESP32-Firmware", "ESP32 firmware"), "nein", ("signiert", "signed")),
    ("/var/lib/speech-spark/voices/", ("Geklonte Stimmen (WAV und Text), in kurz/ gekürzte Referenzen", "Cloned voices (WAV and text), shortened references in kurz/"), "ja", ("", "")),
    ("/var/lib/speech-spark/backups/", ("Sicherungen: 7 neueste plus 5 Ereignis-Sicherungen", "Backups: newest 7 plus 5 event backups"), "–", ("", "")),
    ("journald (Namespace speech-spark)", ("Logs aller Dienste, Dauer und Größe nach Einstellung", "Logs of all services, time and size as set"), "nein", ("", "")),
]


@functools.lru_cache(maxsize=1)
def _en_names():
    """The page's own English names (static/js/i18n.js EN, the menu in base.js), for the menu ways in a docstring."""
    out = {}
    try:
        with open(os.path.join(HERE, "static", "js", "i18n.js"), encoding="utf-8") as f:
            m = re.search(r"const EN=(\{.*?\});?\n", f.read(), re.S)
        out.update(json.loads(m.group(1)) if m else {})
        # the menu wins: „Überblick“ is „Summary“ in Zustand, though a tab elsewhere calls it „Overview“
        with open(os.path.join(HERE, "static", "js", "base.js"), encoding="utf-8") as f:
            out.update(re.findall(r"\['[a-z]+',t\('([^']+)','([^']+)'\)\]", f.read()))
    except (OSError, ValueError):
        pass
    return out


def _en_ways(line):
    """„Ich → Mein Zustand“ in a docstring becomes „Me → My status“: the English docs use the English menu. Next to
    each arrow the longest run of up to 3 words that the page translates is swapped."""
    names = _en_names()
    parts = line.split(" → ")
    for n in range(len(parts) - 1):
        left = parts[n].split(" ")
        for k in (3, 2, 1):
            tail = " ".join(left[-k:]).strip("„“\"(")
            if len(left) >= k and tail in names:
                pre = left[-k][:len(left[-k]) - len(left[-k].lstrip("„“\"("))]
                parts[n] = " ".join(left[:-k] + [pre + names[tail]])
                break
    for n in range(1, len(parts)):
        right = parts[n].split(" ")
        for k in (3, 2, 1):
            head = " ".join(right[:k])
            core = head.rstrip(".,:;)“\"")
            if len(right) >= k and core in names:
                parts[n] = " ".join([names[core] + head[len(core):]] + right[k:])
                break
    return " → ".join(parts)


def _en_line(name):
    """The first sentence of a module's docstring (English, from the code)."""
    for base in (HERE, APP):
        p = os.path.join(base, name + ".py")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    doc = ast.get_docstring(ast.parse(f.read())) or ""
            except (OSError, SyntaxError, ValueError):
                return ""
            doc = " ".join(doc.split())
            doc = re.sub(r"\s*\((?:[^()]*(?:plan|V\d{2}\.|Dominik|Paket|Plan)[^()]*)\)", "", doc)   # where it came from
            m = re.match(r"(.+?[.!?])(\s|$)", doc)
            line = _en_ways((m.group(1) if m else doc).rstrip(":"))
            return line if len(line) <= 160 else line[:157].rstrip() + " …"
    return ""


def module_files():
    """Every module of the Spark: app/panel/*.py and app/*.py (without the test runner)."""
    out = {f[:-3]: "app/panel/" + f for f in os.listdir(HERE) if f.endswith(".py")}
    out.update({f[:-3]: "app/" + f for f in os.listdir(APP) if f.endswith(".py") and f[:-3] not in NO_MODULE})
    return out


def _state_rows():
    rows = []
    sealed = VERSCHLUESSELT
    for name in sorted(set(dateien.STATE_FILES) | set(dateien.STATE_LOCAL)):
        key = name + "@state" if name + "@state" in INHALT else name
        rows.append({"pfad": "state/" + name, "ort": "global", "art": "state", "inhalt": INHALT.get(key, ("", "")),
                     "sicherung": "ja" if name in dateien.STATE_FILES or name == "panel-password" else "nein",
                     "grund": dateien.STATE_LOCAL.get(name, ""), "eigen": "", "schutz": sealed.get(key, ("", ""))})
    return rows


def _user_rows():
    rows = []
    for area, (_de, _en, files) in dateien.AREAS.items():
        for f in files:
            rows.append(("users/ID/" + f, f, area))
    for f in list(dateien.LOCAL) + list(USERS_SONST):
        rows.append(("users/ID/" + f + ("/" if f == "messages" else ""), f, ""))
    out = []
    for pfad, f, area in rows:
        kat = dateien.LOCAL.get(f) or USERS_SONST.get(f) or ""
        excluded = f in ("messages", "messages-pending.json")   # backup._add_dir leaves them out
        out.append({"pfad": pfad, "ort": "profil", "art": "users", "inhalt": INHALT.get(f, ("", "")),
                    "sicherung": "nein" if excluded else "ja", "grund": kat, "eigen": area,
                    "schutz": VERSCHLUESSELT.get(f, ("", ""))})
    for f, bak in USERS_GLOBAL.items():
        out.append({"pfad": "users/" + f, "ort": "global", "art": "users", "inhalt": INHALT.get(f, ("", "")),
                    "sicherung": bak, "grund": "", "eigen": "", "schutz": VERSCHLUESSELT.get(f, ("", ""))})
    return out


def speicherorte():
    """Every place the Spark writes, as rows: path, where (profile or global), content, backup, own storage, protection."""
    sys_rows = [{"pfad": p, "ort": "system", "art": "system", "inhalt": what, "sicherung": bak, "grund": "", "eigen": "",
                 "schutz": prot} for p, what, bak, prot in SYSTEM]
    return sys_rows + _user_rows() + _state_rows()


@functools.lru_cache(maxsize=2)
def data(lang="de"):
    en = lang == "en"
    i = 1 if en else 0
    files = module_files()
    groups = []
    for gid, g in GRUPPEN.items():
        mods = sorted(n for n, (grp, _de) in MODULE.items() if grp == gid and n in files)
        groups.append({"id": gid, "name": g[i], "text": g[2 + i], "node": ORT.get(gid, ""),
                       "modules": [{"name": n, "file": files[n], "text": _en_line(n) if en else MODULE[n][1]} for n in mods]})
    nodes = [{"id": k, "x": v[0], "y": v[1], "name": v[2 + i], "sub": v[4], "group": v[5], "farbe": FARBE[k], "symbol": SYMBOL[k], "nur": NUR_BEI.get(k, ("", ""))[i], "text": v[6 + i], "files": v[8],
              "store": k in ("state", "users", "ablage", "journal"), "page": k in technik_knoten.SEITEN_DATEN} for k, v in KNOTEN.items()]
    steps = [{"name": s[i], "text": s[2 + i], "code": s[4], "nodes": s[5], "edges": s[6]} for s in SCHRITTE]
    rows = []
    for r in speicherorte():
        grund = r["grund"] if not en else KAT_EN.get(r["grund"], "") if r["art"] == "users" else ""
        rows.append(dict(r, inhalt=r["inhalt"][i], schutz=r["schutz"][i], grund=grund))
    try:
        import update
        version = update.app_version()
    except Exception:
        version = ""
    pic = {"size": list(BILD), "box": list(KASTEN), "rein": {k: list(v) for k, v in REIN.items()},
           "zones": [{"id": z, "kind": v[0], "name": v[1 + i], "x": v[3], "y": v[4], "w": v[5], "h": v[6], "lx": v[7]}
                     for z, v in ZONEN.items()],
           "doors": [{"kind": t[0], "name": t[1 + i], "x": t[3], "y": t[4]} for t in TUEREN],
           "lines": {k: [list(p) for p in v] for k, v in LINIEN.items()},
           "legend": {"x": LEGENDE[0], "y": LEGENDE[1], "kinds": [{"kind": k, "name": v[i]} for k, v in FARBEN.items()]}}
    return {"version": version, "groups": groups, "nodes": nodes, "edges": [list(e) for e in KANTEN], "steps": steps, "pic": pic,
            "storage": rows, "areas": {k: v[1 if en else 0] for k, v in dateien.AREAS.items()}}


# ---------------------------------------------------------------- the docs (generated parts)
TXT = {
    "de": {"modul": "Modul", "aufgabe": "Aufgabe", "pfad": "Pfad", "inhalt": "Inhalt", "sicherung": "Sicherung",
           "eigen": "Kopie meiner Daten", "schutz": "Schutz", "grund": "Art", "ja": "ja", "nein": "nein",
           "sys": "System", "glob": "users/ (alle Profile)", "prof": "users/ID/ (pro Profil)", "state": "state/ (global)",
           "code": "Im Code", "schritt": "Schritt"},
    "en": {"modul": "Module", "aufgabe": "Task", "pfad": "Path", "inhalt": "Content", "sicherung": "Backup",
           "eigen": "Copy of my data", "schutz": "Protection", "grund": "Kind", "ja": "yes", "nein": "no",
           "sys": "System", "glob": "users/ (all profiles)", "prof": "users/ID/ (per profile)", "state": "state/ (global)",
           "code": "In the code", "schritt": "Step"},
}


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def zone_of(nid):
    """The innermost zone a box lies in (the smallest one around it)."""
    x, y = KNOTEN[nid][:2]
    w, h = KASTEN
    around = [z for z, v in ZONEN.items() if v[3] <= x and x + w <= v[3] + v[5] and v[4] <= y and y + h <= v[4] + v[6]]
    return min(around, key=lambda z: ZONEN[z][5] * ZONEN[z][6]) if around else ""


def _inner(z, y):
    """True when zone z lies inside zone y."""
    a, b = ZONEN[z], ZONEN[y]
    return z != y and b[3] <= a[3] and a[3] + a[5] <= b[3] + b[5] and b[4] <= a[4] and a[4] + a[6] <= b[4] + b[6]


def mermaid(lang="de"):
    """The picture of the page as a Mermaid flowchart (same zones, nodes and edges)."""
    i = 1 if lang == "en" else 0

    def node(k):
        v = KNOTEN[k]
        shape = ('[("', '")]') if k in ("state", "users", "ablage", "journal") else ('["', '"]')
        return f'{k}{shape[0]}{v[2 + i]}<br/>{v[4].replace(chr(10), "<br/>")}{shape[1]}'

    def parent(z):
        outer = [y for y in ZONEN if _inner(z, y)]
        return min(outer, key=lambda y: ZONEN[y][5] * ZONEN[y][6]) if outer else ""

    def sub(z, ind):
        out = [f'{ind}subgraph z_{z}["{ZONEN[z][1 + i]}"]']
        out += [sub(c, ind + "  ") for c in ZONEN if parent(c) == z]
        out += [f"{ind}  {node(k)}" for k in KNOTEN if zone_of(k) == z]
        return "\n".join(out + [f"{ind}end"])

    lines = ["```mermaid", "flowchart TB"]
    lines += [sub(z, "  ") for z in ZONEN if not parent(z)]
    lines += [f"  {node(k)}" for k in KNOTEN if not zone_of(k)]
    for a, b in KANTEN:
        lines.append(f"  {a} --> {b}")
    lines.append("```")
    return "\n".join(lines)


def block(name, lang="de"):
    d = data(lang)
    x = TXT[lang]
    if name == "bild":
        return mermaid(lang)
    if name == "bausteine":
        out = []
        for g in d["groups"]:
            out += [f"### {g['name']}", "", g["text"], "", f"| {x['modul']} | {x['aufgabe']} |", "|---|---|"]
            out += [f"| `{m['file']}` | {_cell(m['text'])} |" for m in g["modules"]]
            out.append("")
        return "\n".join(out).rstrip()
    if name == "knoten":
        return technik_knoten.doc(lang, {n["id"]: n["name"] for n in d["nodes"]})
    if name == "datenfluss":
        out = []
        for n, s in enumerate(d["steps"], 1):
            out.append(f"{n}. **{s['name']}**: {s['text']} {x['code']}: `{s['code']}`")
        return "\n".join(out)
    if name == "speicher":
        out = []
        heads = {"system": x["sys"], "global-users": x["glob"], "profil": x["prof"], "state": x["state"]}
        groups = {"system": [], "global-users": [], "profil": [], "state": []}
        for r in d["storage"]:
            k = "system" if r["art"] == "system" else "state" if r["art"] == "state" else "profil" if r["ort"] == "profil" else "global-users"
            groups[k].append(r)
        yn = {"ja": x["ja"], "nein": x["nein"]}
        for k in ("system", "global-users", "profil", "state"):
            out += [f"### {heads[k]}", ""]
            if k == "profil":
                out += [f"| {x['pfad']} | {x['inhalt']} | {x['grund']} | {x['schutz']} | {x['sicherung']} | {x['eigen']} |",
                        "|---|---|---|---|---|---|"]
                out += [f"| `{r['pfad']}` | {_cell(r['inhalt'])} | {_cell(r['grund'])} | {_cell(r['schutz'] or '–')} | "
                        f"{yn.get(r['sicherung'], r['sicherung'])} | {_cell(d['areas'].get(r['eigen'], '–'))} |" for r in groups[k]]
            else:
                out += [f"| {x['pfad']} | {x['inhalt']} | {x['schutz']} | {x['sicherung']} |", "|---|---|---|---|"]
                out += [f"| `{r['pfad']}` | {_cell(r['inhalt'])} | {_cell(r['schutz'] or '–')} | {yn.get(r['sicherung'], r['sicherung'])} |"
                        for r in groups[k]]
            out.append("")
        return "\n".join(out).rstrip()
    raise KeyError(name)


BLOCKS = ("bild", "datenfluss", "bausteine", "speicher", "knoten")
MARK = re.compile(r"(<!-- technik:(\w+) -->\n)(?:.*?\n)?(<!-- /technik:\2 -->)", re.S)


def render_doc(text, lang):
    """The doc with every generated part written again from the code."""
    return MARK.sub(lambda m: m.group(1) + block(m.group(2), lang) + "\n" + m.group(3), text)


def write_docs():
    """Writes the generated parts into docs/de/architektur.md and docs/en/architecture.md (hilfe.py --docs calls it)."""
    data.cache_clear()
    technik_knoten.seite.cache_clear()
    changed = []
    for lang, path in DOCS.items():
        with open(path, encoding="utf-8") as f:
            old = f.read()
        new = render_doc(old, lang)
        if new != old:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            changed.append(path)
    return changed


# ---------------------------------------------------------------- the page
router = APIRouter()


@router.get("/api/admin/technik", dependencies=[Depends(auth)])
def technik(request: Request, lang: str = "de"):
    """Zustand → Technik: parts, picture, steps and storage places (names and paths only)."""
    guard.limit(request, "technik", None, True)
    return data("en" if lang == "en" else "de")


@router.get("/api/admin/technik/knoten/{nid}", dependencies=[Depends(auth)])
def technik_knoten_seite(request: Request, nid: str, lang: str = "de"):
    """Zustand → Technik, Knoten-Seite: how one box works (texts from technik_knoten.py, numbers from the code) and
    today's counts of it (numbers only)."""
    guard.limit(request, "technikseite", None, True)
    lang = "en" if lang == "en" else "de"
    page = technik_knoten.seite(nid, lang) if nid in KNOTEN else None
    if not page:
        raise HTTPException(404, "no page for this box")
    v = KNOTEN[nid]
    return dict(page, name=v[3 if lang == "en" else 2], sub=v[4], group=v[5], files=v[8],
                neighbours=sorted({b if a == nid else a for a, b in KANTEN if nid in (a, b)}), today=technik_knoten.heute(nid))


if __name__ == "__main__" and "--docs" in sys.argv:
    write_docs()   # hilfe.py --docs does the same and says what it wrote
