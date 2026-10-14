"""Zustand → Technik (plan plaene/technische-doku.md, Dominik 2026-10-13 „1 umsetzen, immer alles aktuell halten“):
how the Spark is built, as a page to click through and as docs/de/architektur.md + docs/en/architecture.md.

One source for both: the parts (MODULE, GRUPPEN), the picture (KNOTEN, KANTEN), the way of one request (SCHRITTE)
and where data lies (speicherorte(), built from speicher.AREAS/LOCAL, backup.STATE_FILES/STATE_LOCAL and the lists
here). `python3 app/panel/hilfe.py --docs` writes the generated parts into both docs (between the markers
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

from fastapi import APIRouter, Depends, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # common.py, also as a script
import backup  # noqa: E402
import guard  # noqa: E402
import speicher  # noqa: E402
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
                "Home Assistant, Mail, Kalender, Aufgaben, Wetter, reMarkable, MCP und was der Spark von selbst tut.",
                "Home Assistant, mail, calendar, tasks, weather, reMarkable, MCP and what the Spark does by itself."),
    "geraete": ("Geräte und Kanäle", "Devices and channels",
                "Apps, Telegram, Uhr, Lautsprecher, Raummodus, Chats und der Verlauf auf allen Geräten.",
                "Apps, Telegram, watch, speakers, room mode, chats and the history on all devices."),
    "betrieb": ("Betrieb", "Operation",
                "Live-Übersicht, Logs, Wächter, Sicherung, Update, Hilfe und die Admin-Seiten.",
                "Live overview, logs, watchers, backup, update, help and the admin pages."),
    "sprache": ("Sprachdienste", "Speech services",
                "Spracherkennung und Sprachausgabe als eigene Dienste, mit Vorrang vor allem anderen.",
                "Speech recognition and speech output as their own services, ahead of everything else."),
}

# every module of app/panel and app/: name -> (group, German line). English comes from the module's docstring.
MODULE = {
    # Zugang und Rechte
    "panel": ("zugang", "Startet das Panel, Middleware (Größe, Herkunft, Notaus), liefert die Seite aus"),
    "core": ("zugang", "Admin-Passwort, Sitzungen, gemeinsame Pfade und Helfer"),
    "guard": ("zugang", "Rate-Limits, Sperren nach falschen Versuchen, fremde Seiten, audit.log"),
    "profiles": ("zugang", "Profile, Geräte, Sitzungen, Gespräche und Gedächtnis pro Profil"),
    "account": ("zugang", "Was ein Gerät für sich selbst darf: Anmelden und eigene Daten"),
    "mfa": ("zugang", "Zweiter Anmeldeschritt mit Code (TOTP) und Wiederherstellungscodes"),
    "passkey": ("zugang", "Passkeys statt Code (Face ID, Touch ID, Windows Hello)"),
    "coadmin": ("zugang", "Profile als Admins: Haupt-Admin, Mit-Admin, Verwalter"),
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
    "chat_turn": ("gespraech", "Bereitet eine Anfrage vor: Rechte, Sperren, Systemprompt, Werkzeuge"),
    "chat_tools": ("gespraech", "Führt die Werkzeugaufrufe des Modells aus und prüft die Sperren erneut"),
    "answercheck": ("gespraech", "Antwort-Prüfung: das Panel entscheidet, ob ein Satz gesagt werden darf"),
    "taten": ("gespraech", "Handlungs-Prüfung: hat ein Werkzeug wirklich getan, was der Satz sagt"),
    "ack": ("gespraech", "Sofortige Rückmeldung aus aufgenommenen Sätzen"),
    "klaeren": ("gespraech", "Rückfrage, Korrektur und Merken von Zuordnungen"),
    "vorab": ("gespraech", "Holt bei einer Rückfrage die Antwort schon vorab"),
    "fixes": ("gespraech", "Lernt aus Korrekturen der Person"),
    "roles": ("gespraech", "Rollen: wie der Assistent antworten soll"),
    "stille": ("gespraech", "Aus Stille werden nie Wörter"),
    "fremdstimme": ("gespraech", "Fernseher und fremde Stimmen im von selbst geöffneten Mikrofon werden keine Frage"),
    "echo": ("gespraech", "Der Assistent antwortet nicht auf seine eigene Stimme"),
    "images": ("gespraech", "Bilder in der Frage: das Sprachmodell sieht sie selbst"),
    "schreib": ("gespraech", "Schreibhilfe: korrigieren, kürzen, übersetzen, entwerfen"),
    "systemone": ("gespraech", "Einordnung mit Wahrscheinlichkeit über qwen38"),
    "tipps": ("gespraech", "Schlägt passende Funktionen vor, die noch aus sind"),
    "stufe": ("gespraech", "Vorrang für Personen in der Warteschlange der Sprachausgabe"),
    # Weiche
    "intent": ("weiche", "Die Weiche: feste Regeln für die eigene letzte Nachricht"),
    "intent_bench": ("weiche", "Testsätze der Weiche"),
    "weiche": ("weiche", "Seite Funktionen → Weiche und ihre Statistik"),
    "werkzeuge": ("weiche", "Verständliche Namen aller Werkzeuge"),
    "werkzeug_abdeckung": ("weiche", "Welche Funktion das Modell mit welchem Werkzeug erreicht (Regel 29)"),
    # Wissen
    "wissen": ("wissen", "Wissen aus eigenen Uploads: Schalter und Kontingent"),
    "documents": ("wissen", "Dokumente pro Profil in wissen.db: Text, Abschnitte mit Kontextzeile, Suche"),
    "doclingdienst": ("wissen", "Docling-Server im Heimnetz: Dokumente und Scans besser lesen"),
    "suchpruefung": ("wissen", "Suchprüfung: Prüffragen messen, wie gut die Dokumentensuche trifft"),
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
    "docrender": ("wissen", "Baut die Dateien (Word, PDF, PowerPoint, Excel) mit festem Code"),
    "folien": ("wissen", "Folientypen und feste Regeln für erstellte Dokumente"),
    "symbole": ("wissen", "Feste Symbole für Folien und Dokumente"),
    "tagebuch": ("wissen", "Spark-Tagebuch: was der Spark selbst getan hat"),
    # Anbindungen
    "homeassistant": ("dienste", "Home Assistant pro Profil"),
    "hamelden": ("dienste", "Home Assistant meldet Ereignisse an den Spark"),
    "mail": ("dienste", "Mail lesen per IMAP"),
    "tidy": ("dienste", "Posteingang aufräumen"),
    "parcels": ("dienste", "Pakete aus Versand-Mails"),
    "calendars": ("dienste", "Kalender und Tagesbriefing"),
    "contacts": ("dienste", "Kontakte per CardDAV, nur lesen"),
    "tasks": ("dienste", "Aufgaben und Einkaufsliste"),
    "weather": ("dienste", "Wetter von Open-Meteo als feste Sätze"),
    "transit": ("dienste", "Bus und Bahn"),
    "extras": ("dienste", "Kleine Zusatzdienste mit ihren Werkzeugen"),
    "mcp": ("dienste", "Werkzeuge von MCP-Servern, die der Admin einträgt"),
    "meinmcp": ("dienste", "Eigene MCP-Dienste pro Profil"),
    "mcpserver": ("dienste", "Der Spark als MCP-Server für andere Programme"),
    "remarkable": ("dienste", "reMarkable-Notizbücher als Wissen"),
    "rmliste": ("dienste", "Werkzeug: was auf dem reMarkable liegt und welche Aufgaben dort stehen"),
    "aendern": ("dienste", "Ändern per Sprache: Lautstärke, Termine und anderes nach „Ja“"),
    "zustand_wz": ("dienste", "Werkzeug: Zustand des Spark per Sprache („Läuft alles?“)"),
    "rmplus": ("dienste", "Mehr mit dem reMarkable: Senden, Ordner, Abgleich"),
    "rmpapier": ("dienste", "Gestaltete Blätter fürs reMarkable"),
    "rmaufgaben": ("dienste", "Aufgabenblatt zum Ankreuzen aufs reMarkable"),
    "agent": ("dienste", "Aufträge im Hintergrund, Zeitpläne, Routinen"),
    "beobachten": ("dienste", "Beobachten: Funde prüfen, nur Neues melden (Eigene Aufgaben)"),
    "proactive": ("dienste", "Meldet sich von selbst, wenn etwas Echtes passiert"),
    # Geräte und Kanäle
    "telegram": ("geraete", "Telegram-Bot für Text und Sprachnachrichten"),
    "iphone": ("geraete", "iPhone-App: Kopplung und Rechte"),
    "android": ("geraete", "Android-App: Download und Kopplung"),
    "apns": ("geraete", "Mitteilungen an die iPhone-App"),
    "push": ("geraete", "Web-Push für Erinnerungen"),
    "appupdate": ("geraete", "Spark-Update aus der iPhone-App"),
    "pebblewatch": ("geraete", "Kopplung der Pebble-Uhr"),
    "watch": ("geraete", "Antworten für die Uhr"),
    "esp32": ("geraete", "Eigene ESP32-Lautsprecher und ihre Firmware"),
    "geraeteupdate": ("geraete", "Übersicht und Hinweise zu Geräte-Updates"),
    "wyoming": ("geraete", "Home Assistant Assist über Wyoming"),
    "begleiter": ("geraete", "Spark-Begleiter für Windows und Mac"),
    "speakers": ("geraete", "Sprechererkennung pro Profil"),
    "spkcode": ("geraete", "Codewort am geteilten Lautsprecher"),
    "room": ("geraete", "Raummodus: hört zu und hilft in einer Pause"),
    "roomfar": ("geraete", "Raummodus auf einem anderen Gerät schalten"),
    "roomlive": ("geraete", "Wo der Raummodus gerade zuhört"),
    "chats": ("geraete", "Chats zwischen den Profilen, verschlüsselt"),
    "verbund": ("geraete", "Spark-Verbund: Chats mit Menschen auf anderen Sparks, signiert"),
    "chatsec": ("geraete", "Private Chats mit Ende-zu-Ende-Verschlüsselung"),
    "messages": ("geraete", "Der Weg des Assistenten in die Chats"),
    "verlauf": ("geraete", "Verlauf auf allen Geräten gleich"),
    "today": ("geraete", "Die Karte „Heute“ oben in Ich"),
    "onboard": ("geraete", "Einrichten an der Hand"),
    "hintergrund": ("geraete", "Ich → Mein Zustand"),
    # Betrieb
    "admin": ("betrieb", "Admin-Seiten: Zustand, Einstellungen, Dienste, Stimmen"),
    "system": ("betrieb", "Sicherung, Echtprüfung der Dienste, Hinweise oben"),
    "monitor": ("betrieb", "Messwerte: GPU, Speicher, CPU"),
    "health": ("betrieb", "Stabilität: Wächter für hängende Dienste, Echtprüfung"),
    "live": ("betrieb", "Live-Übersicht: was der Spark gerade tut"),
    "tracelog": ("betrieb", "Logs → Anfragen: der Weg jeder Anfrage"),
    "logfilter": ("betrieb", "Diagnose-Filter und Hinweise für die Logs"),
    "latency": ("betrieb", "Wartezeit bis zum ersten Ton"),
    "dienstwacht": ("betrieb", "Dienst-Wächter: meldet, wenn ein Dienst fehlt"),
    "faelle": ("betrieb", "Fälle: jedes Problem wird festgehalten"),
    "befund": ("betrieb", "Befund: die Ursache eines Falls"),
    "berater": ("betrieb", "Einstellungs-Assistent: Vorschläge aus Fällen"),
    "berater_katalog": ("betrieb", "Was der Einstellungs-Assistent vorschlagen darf"),
    "quality": ("betrieb", "Qualitätstest gegen das echte Sprachmodell"),
    "backup": ("betrieb", "Sicherungen und Wiederherstellen"),
    "offsite": ("betrieb", "Sicherung nach außen, verschlüsselt"),
    "speicher": ("betrieb", "Kopie meiner Daten pro Profil an einem Speicherort, verschlüsselt"),
    "nas": ("betrieb", "Speicher und NAS: Speicherorte (NAS, Cloud), eine Anmeldung pro Ort für Kopie und Sicherung"),
    "nasquelle": ("betrieb", "Wissensordner: Ordner an einem Speicherort nur lesen und in die Dokumentensuche bringen"),
    "nasablage": ("betrieb", "Ablage-Ordner: spark_ablage im Heimnetz, der einzige Ordner, in den der Spark schreibt; Eingang wird zu Dokumenten"),
    "nashilfe": ("betrieb", "NAS im Heimnetz finden (nur mDNS) und Rechte am Ort zeigen, mit Warnung bei Admin-Konto"),
    "update": ("betrieb", "Updates von GitHub, nur nach grünem Test"),
    "ghtoken": ("betrieb", "Lese-Token für GitHub"),
    "meldung": ("betrieb", "Probleme melden als GitHub-Issue"),
    "undo": ("betrieb", "Rückgängig im Admin-Protokoll"),
    "hilfe": ("betrieb", "Spark-Hilfe und Index der Doku"),
    "wege": ("betrieb", "Sprung-Links in Texten außerhalb des Panels"),
    "technik": ("betrieb", "Diese Seite: Zustand → Technik und die Architektur-Doku"),
    # Sprachdienste (app/)
    "asr_proxy": ("sprache", "Spracherkennung: nimmt an und reicht an die Engine durch"),
    "asr_server": ("sprache", "Spracherkennung als eigener kleiner Dienst"),
    "parakeet": ("sprache", "Zweite Spracherkennung (Parakeet) auf der CPU"),
    "tts_proxy": ("sprache", "Sprachausgabe: nimmt an und reicht an die Engine durch"),
    "tts_server": ("sprache", "Sprachausgabe als eigener kleiner Dienst"),
    "tempo": ("sprache", "Sprechtempo für gestreamte Sprache"),
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
    "geraet": (16, 40, "Browser und Handy", "Browser and phone", "static/js", "", "Nimmt Sprache auf, zeigt Text, spielt Ton.",
               "Records speech, shows text, plays sound.", ["static/js/chat.js"]),
    "apps": (16, 115, "Apps", "Apps", "iPhone, Android", "", "Eigene Apps mit Geräteschlüssel, gleicher Weg wie der Browser.",
             "Own apps with a device key, the same way as the browser.", ["ios/", "android/"]),
    "kanaele": (16, 190, "Telegram, Siri, Uhr", "Telegram, Siri, watch", "Kanäle", "geraete",
                "Kurze Fragen ohne Browser; den Verlauf speichert das Panel selbst.",
                "Short questions without a browser; the panel keeps the history itself.", []),
    "lautsprecher": (16, 265, "Lautsprecher, HA", "Speakers, HA", "esp32 · :31003", "",
                     "ESP32-Lautsprecher und Home Assistant Assist.", "ESP32 speakers and Home Assistant Assist.",
                     ["esp32.py", "wyoming.py"]),
    "mcpc": (16, 340, "MCP-Programme", "MCP programs", "/mcp", "", "Claude, n8n, Open WebUI fragen über den MCP-Server.",
             "Claude, n8n, Open WebUI ask through the MCP server.", ["mcpserver.py"]),
    "middleware": (200, 60, "Middleware", "Middleware", "panel.py", "",
                   "Größenlimit, Herkunft (CSRF) und Notaus, bevor ein Endpunkt die Anfrage liest.",
                   "Size limit, origin (CSRF) and kill switch before an endpoint reads the request.", ["panel.py", "notaus.py"]),
    "zugang": (200, 165, "Anmeldung, Profil", "Login, profile", "guard · profiles", "zugang",
               "Rate-Limit, Anmeldung per Cookie oder Geräteschlüssel, Freigaben. Das Profil kommt nie vom Modell.",
               "Rate limit, login by cookie or device key, releases. The profile never comes from the model.", []),
    "vorbereiten": (380, 60, "Anfrage vorbereiten", "Prepare request", "chat_turn.prepare", "",
                    "Rechte und Sperren, Systemprompt, Rückfrage und die angebotenen Werkzeuge.",
                    "Rights and locks, system prompt, question back and the offered tools.", ["chat_turn.py", "klaeren.py"]),
    "weiche": (380, 165, "Weiche", "Switch", "intent.py", "weiche",
               "Grenzt die Werkzeuge mit festen Regeln ein. Das Modell entscheidet hier nichts.",
               "Narrows the tools by fixed rules. The model decides nothing here.", []),
    "antwort": (560, 60, "Antwort bauen", "Build answer", "chat._answer", "gespraech",
                "Runden mit dem Sprachmodell, Prüfungen, Text und Ton als ein Strom.",
                "Rounds with the language model, checks, text and sound as one stream.", []),
    "werkzeuge": (560, 165, "Werkzeuge", "Tools", "chat_tools.run", "dienste",
                  "Nur angebotene Werkzeuge laufen; Ergebnisse sind Daten, nie Befehle.",
                  "Only offered tools run; results are data, never commands.", ["chat_tools.py"]),
    "wissen": (380, 270, "Wissen", "Knowledge", "documents · wissen", "wissen",
               "Eigene Dokumente, Gedächtnis, Kiwix, erstellte Dokumente.", "Own documents, memory, Kiwix, created documents.", []),
    "waechter": (560, 270, "Wächter", "Guard", "netguard.py", "",
                 "Öffentlich, Heimnetz nur mit Erlaubnis, nie Metadaten oder eigene Ports.",
                 "Public, home network only when allowed, never metadata or own ports.", ["netguard.py"]),
    "betrieb": (200, 270, "Logs und Live", "Logs and live", "tracelog · live", "betrieb",
                "Anfrage-Verlauf, Live-Übersicht, Wächter, Sicherung. Nur feste Wörter und Zahlen.",
                "Request history, live overview, watchers, backup. Only fixed words and numbers.", []),
    "llm": (766, 40, "Sprachmodell", "Language model", ":30001 qwen38", "",
            "Qwen3.8 aus dgx-spark-qwen38 (nicht Teil dieses Repos).", "Qwen3.8 from dgx-spark-qwen38 (not part of this repo).", []),
    "asr": (766, 115, "Spracherkennung", "Speech recognition", ":31001 → :31011", "sprache",
            "Proxy nimmt an, die Engine läuft nur lokal.", "The proxy accepts, the engine runs locally only.", []),
    "tts": (766, 190, "Sprachausgabe", "Speech output", ":31002 → :31012", "",
            "Qwen3-TTS mit eigenen Stimmen.", "Qwen3-TTS with own voices.", ["tts_proxy.py", "tts_server.py", "tempo.py", "textnorm.py"]),
    "aussen": (766, 270, "Dienste draußen", "Outside services", "HA, Mail, Suche …", "",
               "Home Assistant, Kalender, Mail, SearXNG, Kiwix, reMarkable, MCP. Nur über den Wächter.",
               "Home Assistant, calendar, mail, SearXNG, Kiwix, reMarkable, MCP. Only through the guard.", []),
    "state": (200, 375, "state/", "state/", "global", "", "Globaler Zustand: Schlüssel, Statistik, Wächter.",
              "Global state: keys, statistics, watchers.", []),
    "users": (380, 375, "users/ID/", "users/ID/", "pro Profil", "", "Alles eines Profils; kein Profil sieht den Ordner eines anderen.",
              "Everything of one profile; no profile sees another one's folder.", []),
    "ablage": (560, 375, "voices/, backups/", "voices/, backups/", "Stimmen, Sicherungen", "",
               "Geklonte Stimmen und Sicherungen.", "Cloned voices and backups.", []),
    "journal": (766, 375, "journald", "journald", "speech-spark", "", "Alle Dienste, 14 Tage, höchstens 500 MB.",
                "All services, 14 days, at most 500 MB.", []),
}
KANTEN = [("geraet", "middleware"), ("apps", "middleware"), ("kanaele", "middleware"), ("lautsprecher", "middleware"),
          ("mcpc", "middleware"), ("middleware", "zugang"), ("middleware", "asr"), ("zugang", "vorbereiten"),
          ("vorbereiten", "weiche"), ("weiche", "antwort"), ("antwort", "llm"), ("antwort", "werkzeuge"),
          ("werkzeuge", "waechter"), ("waechter", "aussen"), ("werkzeuge", "wissen"), ("antwort", "tts"),
          ("antwort", "geraet"), ("antwort", "betrieb"), ("betrieb", "state"), ("betrieb", "journal"),
          ("wissen", "users"), ("zugang", "users"), ("zugang", "state"), ("tts", "ablage")]
# where a group lives in the picture (the node that lists it)
ORT = {g: k for k, v in KNOTEN.items() for g in [v[5]] if g}

# ---------------------------------------------------------------- the way of one request
# German, English, German text, English text, code, nodes, edges ("a>b")
SCHRITTE = [
    ("Eingabe", "Input", "Das Mikrofon nimmt auf, das Panel reicht den Ton an die Spracherkennung weiter.",
     "The microphone records, the panel hands the sound to speech recognition.", "POST /api/test/asr",
     ["geraet", "middleware", "asr"], ["geraet>middleware", "middleware>asr"]),
    ("Zugang", "Access", "Größe, Herkunft und Notaus, dann Rate-Limit, Anmeldung und Profil.",
     "Size, origin and kill switch, then rate limit, login and profile.", "POST /api/chat · guard.limit · profiles.current",
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
    ("Werkzeuge", "Tools", "Werkzeugaufruf, Wächter, Dienst draußen oder eigenes Wissen; das Ergebnis geht als Daten zurück.",
     "Tool call, guard, outside service or own knowledge; the result comes back as data.", "chat_tools.run() · netguard",
     ["antwort", "werkzeuge", "waechter", "aussen", "wissen"],
     ["antwort>werkzeuge", "werkzeuge>waechter", "waechter>aussen", "werkzeuge>wissen"]),
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
# what is in a file (German, English); every file of the lists below has a line here (test_technik)
INHALT = {
    # users/<id>/
    "convos.json": ("Gespräche", "Conversations"), "toollog.json": ("Werkzeug-Log", "Tool log"),
    "room-history.json": ("Raummodus-Verlauf", "Room mode history"), "memory.json": ("Gedächtnis", "Memory"),
    "learned.json": ("Gelernte Fakten", "Learned facts"), "zuordnungen.json": ("Gemerkte Zuordnungen", "Remembered matches"),
    "tasks.json": ("Aufgaben", "Tasks"), "reminders.json": ("Erinnerungen", "Reminders"),
    "wissen.db": ("Dokumente: Text, Abschnitte mit Kontextzeile, Suche, Vektoren (SQLite)", "Documents: text, sections with context line, search, vectors (SQLite)"),
    "docs/files/": ("Originale der Uploads", "Originals of uploads"), "suchpruefung.json": ("Prüffragen und Läufe der Suchprüfung", "Test questions and runs of the search check"), "erstellt/": ("Erstellte Dokumente", "Created documents"),
    "settings.json": ("Einstellungen", "Settings"), "setup.json": ("Einrichtung", "Setup"),
    "speicher.json": ("Ziele des eigenen Speichers", "Own storage targets"), "speicher-stand.json": ("Stand des Abgleichs", "Sync state"),
    "transit.json": ("Haltestelle", "Stop"), "weather.json": ("Wetter-Ort", "Weather place"),
    "proactive.json": ("Von selbst melden", "Speak up by itself"), "proactive-rules.json": ("Eigene Melde-Regeln", "Own notice rules"),
    "hintergrund.json": ("Mein Zustand", "My status"), "mail.json": ("Mail-Zugang", "Mail account"), "nas.json": ("Speicherorte des Profils (NAS, Cloud)", "Storage places of the profile (NAS, cloud)"), "nasquelle.json": ("Wissensordner des Profils", "Knowledge folders of the profile"), "nasablage.json": ("Ablage-Ordner des Profils", "Filing folder of the profile"), "nasquelle-stand.json": ("Was aus den Wissensordnern gelesen ist", "What was read from the knowledge folders"), "docling-wait": ("Dateien, bis Docling sie gelesen hat", "Files until Docling has read them"), "speicher.vor-nas.json": ("Kopie meiner Daten vor dem Umzug auf Speicherorte", "Copy of my data before the move to storage places"),
    "mail-tidy.json": ("Posteingang aufräumen", "Inbox tidy"), "calendar.json": ("Kalender-Zugang", "Calendar account"),
    "homeassistant.json": ("Home-Assistant-Zugang", "Home Assistant account"), "telegram.json": ("Telegram-Kopplung", "Telegram link"),
    "push.json": ("Push-Abos der Browser", "Browser push subscriptions"), "remarkable.json": ("reMarkable-Zugang", "reMarkable account"),
    "remarkable-lib.json": ("reMarkable-Bibliothek", "reMarkable library"), "mcp-dienste.json": ("Eigene MCP-Dienste", "Own MCP services"),
    "mcp-actions.json": ("MCP-Aktionen", "MCP actions"), "agent.json": ("Aufträge und Routinen", "Jobs and routines"),
    "voice.json": ("Stimmabdruck", "Voiceprint"), "speaker-code.json": ("Codewort am Lautsprecher", "Speaker code word"),
    "chatkeys.json": ("Öffentliche Schlüssel der Geräte", "Devices' public keys"), "contacts.json": ("Kontakte-Zugang", "Contacts account"),
    "ha-events.json": ("Home-Assistant-Ereignisse", "Home Assistant events"), "briefing-sent": ("Briefing gesendet", "Briefing sent"),
    "messages.json": ("Nachrichten-Einstellungen", "Message settings"), "messages": ("Alte Sprachnachrichten", "Old voice messages"),
    "agent-pending.json": ("Wartet auf Ja", "Waiting for yes"), "calendar-pending.json": ("Wartet auf Ja", "Waiting for yes"),
    "fix-pending.json": ("Wartet auf Ja", "Waiting for yes"), "memory-ask.json": ("Offene Frage zum Gedächtnis", "Open memory question"),
    "mail-pending.json": ("Wartet auf Ja", "Waiting for yes"), "mcp-dienste-pending.json": ("Wartet auf Ja", "Waiting for yes"),
    "messages-pending.json": ("Wartet auf Ja", "Waiting for yes"), "tasks-pending.json": ("Wartet auf Ja", "Waiting for yes"),
    "tagebuch.json": ("Spark-Tagebuch", "Spark diary"), "mfa.json": ("Zweiter Schritt des Profils", "Profile's second step"),
    "memory-tidy.json": ("Aufräum-Vorschlag", "Tidy proposal"), "memory-tidy-checked": ("Letzte Aufräum-Prüfung", "Last tidy check"),
    # users/ (global)
    "profiles.json": ("Profile und Geräte", "Profiles and devices"), "sessions.json": ("Anmeldungen", "Logins"),
    "seen.json": ("Zuletzt gesehen", "Last seen"), "secret": ("Schlüssel der Profil-Anmeldung", "Profile login key"),
    "_chats/": ("Chats zwischen Profilen", "Chats between profiles"), "_verbund/": ("Spark-Verbund: andere Sparks, Kontakte, Warteschlange", "Spark network: other Sparks, contacts, queue"), "begleiter.json": ("Begleiter-Geräte", "Companion devices"),
    # state/
    "secret.key": ("Schlüssel für alles Versiegelte", "Key for everything sealed"), "panel-password": ("Admin-Passwort (Hash)", "Admin password (hash)"),
    "admin-session.key": ("Schlüssel der Admin-Sitzung", "Admin session key"), "vorrang-key": ("Schlüssel Panel ↔ Sprachdienste", "Key panel ↔ speech services"),
    "offsite.json": ("Sicherung nach außen", "Offsite backup"), "nas-admin.json": ("NAS-Verbindung des Spark", "The Spark's NAS connection"), "docling.json": ("Docling-Server: Adresse, Zertifikat, Zahlen", "Docling server: address, certificate, counts"), "mfa-admin.json": ("Zweiter Schritt des Admins", "Admin's second step"),
    "apns.json": ("Apple-Push-Schlüssel", "Apple push key"), "apns-tokens.json": ("iPhone-Geräte für Push", "iPhones for push"),
    "github-token.json": ("GitHub-Lese-Token", "GitHub read token"), "vapid.pem": ("Web-Push-Schlüssel", "Web push key"),
    "esp32.json": ("Lautsprecher und Firmware", "Speakers and firmware"), "geraete-updates.json": ("Geräte-Updates", "Device updates"),
    "regel-versionen.json": ("Regel-Versionen", "Rule versions"), "berater.json": ("Vorschläge des Assistenten", "Assistant proposals"),
    "faelle.json": ("Fälle", "Cases"), "gut-saetze.json": ("Mit 👍 bestätigte Fragen", "Questions confirmed with 👍"),
    "bewertungen.json": ("Bewertungen pro Tag", "Ratings per day"), "dienstwacht.json": ("Dienst-Wächter", "Service watcher"),
    "mcp-dienste-admin.json": ("Erlaubte MCP-Ziele", "Allowed MCP hosts"), "mcp-server.json": ("MCP-Programme (Token-Hashes)", "MCP programs (token hashes)"),
    "personen-vorrang.json": ("Vorrang pro Profil", "Priority per profile"), "quality-cases.json": ("Eigene Testfragen", "Own test questions"),
    "quality-history.json": ("Verlauf der Qualitätstests", "Quality test history"), "quality.json": ("Letzter Qualitätstest", "Last quality test"),
    "doc-quotas.json": ("Dokument-Kontingente", "Document quotas"), "admins.json": ("Profile als Admins", "Profiles as admins"),
    "features-seen.json": ("Wann Funktionen frei wurden", "When functions were released"), "join.json": ("Einladungen (Hashes)", "Invitations (hashes)"),
    "guard.json": ("Sperren nach Fehlversuchen", "Lockouts"), "revoked.json": ("Widerrufene Sitzungen", "Revoked sessions"),
    "guard-xff-hinted.json": ("Proxy-Hinweis gezeigt", "Proxy hint shown"), "audit.log": ("Admin-Protokoll, 1 MB", "Admin log, 1 MB"),
    "traces.jsonl": ("Logs → Anfragen, 48 h", "Logs → Requests, 48 h"), "latency.json": ("Wartezeiten", "Waiting times"),
    "livecheck.json": ("Echtprüfung", "Live check"), "live-monitors.json": ("Wandmonitore", "Wall monitors"),
    "dienste-zustand.json": ("Hintergrund-Dienste", "Background services"), "weiche-stats.json": ("Weiche-Statistik", "Switch statistics"),
    "weiche-history.json": ("Weiche-Änderungen", "Switch changes"), "config-undo.json": ("Rückgängig (ohne Geheimnisse)", "Undo (no secrets)"),
    "tipps.json": ("Gezeigte Tipps", "Tips shown"), "iphone-update.json": ("Update aus der iPhone-App", "Update from the iPhone app"),
    "vision.json": ("Bildfragen, 10 min", "Picture questions, 10 min"), "doc-embed.json": ("Vektormodell", "Vector model"), "doc-rank.json": ("Nachsortier-Modell", "Re-ranking model"),
    "notaus.json": ("Notaus", "Kill switch"), "notaus-mine.json": ("Mein Notaus", "My kill switch"),
    "notaus-keys.json": ("Notaus-Auslöser", "Kill switch triggers"), "meldung-token.json": ("Token für Meldungen", "Report token"),
    "meldungen": ("Meldungs-Entwürfe", "Report drafts"), "ack": ("Sofort-Sätze als Ton", "Instant sentences as sound"),
    "android": ("Android-App zum Download", "Android app for download"), "begleiter": ("Begleiter-Updates", "Companion updates"),
    "begleiter-inbox": ("Vom Handy auf den PC, 24 h", "Phone to PC, 24 h"), "speicher-tmp": ("Zwischenablage des eigenen Speichers", "Own storage staging"), "nasquelle-tmp": ("Zwischendateien der Wissensordner, Sekunden", "Knowledge folder staging, seconds"),
    "speech-active": ("Zeitpunkt der letzten Sprache", "Time of last speech"), "speech-spark-asr-engine.json": ("Zustand der ASR-Engine", "ASR engine state"),
    "speech-spark-tts-*.json": ("Zustand der TTS-Engines", "TTS engine state"), "bench-latest.json": ("Letzte Messung", "Last benchmark"),
    "bench-history.json": ("Messungen", "Benchmarks"), "update-progress.json": ("Update-Fortschritt", "Update progress"),
    "update-target": ("Gewünschter Update-Stand", "Requested update target"), "update-night.json": ("Nacht-Update", "Night update"),
    "setup.json@state": ("Einrichtungs-Assistent erledigt", "Setup wizard done"), "telegram.json@state": ("Telegram-Bot", "Telegram bot"),
    "agent.json@state": ("Agent-Stufen, MCP-Dienste", "Agent levels, MCP services"),
    "migrated-chunk10": ("Einmalige Umstellung erledigt", "One-time migration done"), "firmware": ("ESP32-Firmware", "ESP32 firmware"),
}
# per-profile files written through their own helper, not through profiles._path (users/<id>/, never copied)
USERS_SONST = {"mfa.json": "Schlüssel", "memory-tidy.json": "Warteschlange", "memory-tidy-checked": "Zustand"}
# directly under users/ (all profiles together)
USERS_GLOBAL = {"profiles.json": "ja", "sessions.json": "ja", "seen.json": "ja", "secret": "nein", "_chats/": "ja", "_verbund/": "ja",
                "begleiter.json": "ja"}
# state/ files written by the shell scripts or through other names (install.sh, update.sh, engine.sh, core.py)
STATE_SONST = {"admin-session.key", "update-target", "update-night.json", "migrated-chunk10", "speech-spark-tts-*.json",
               "faelle.json", "gut-saetze.json", "nas-admin.json", "bewertungen.json", "weiche-stats.json", "weiche-history.json"}
# what is sealed or hashed: path -> (German, English); the rest lies as plain JSON (0600, owner speech)
VERSCHLUESSELT = {
    "mail.json": ("Passwort versiegelt", "password sealed"), "nas.json": ("Passwort versiegelt", "password sealed"), "calendar.json": ("Passwort versiegelt", "password sealed"),
    "homeassistant.json": ("Token versiegelt", "token sealed"), "remarkable.json": ("Token versiegelt", "token sealed"),
    "mcp-dienste.json": ("Tokens versiegelt", "tokens sealed"), "contacts.json": ("Passwort versiegelt", "password sealed"),
    "speaker-code.json": ("versiegelt", "sealed"), "speicher.json": ("Schlüssel versiegelt", "key sealed"),
    "mfa.json": ("versiegelt", "sealed"), "voice.json": ("versiegelt", "sealed"), "_chats/": ("AES-256-GCM", "AES-256-GCM"), "secret": ("ist ein Schlüssel", "is a key"),
    "secret.key": ("ist der Schlüssel", "is the key"), "panel-password": ("Hash", "hash"), "admin-session.key": ("ist ein Schlüssel", "is a key"),
    "vorrang-key": ("ist ein Schlüssel", "is a key"), "offsite.json": ("versiegelt", "sealed"), "nas-admin.json": ("Passwort versiegelt", "password sealed"), "docling.json": ("Schlüssel versiegelt", "key sealed"), "mfa-admin.json": ("versiegelt", "sealed"),
    "apns.json": ("Schlüssel versiegelt", "key sealed"), "telegram.json@state": ("Token versiegelt", "token sealed"),
    "github-token.json": ("versiegelt", "sealed"), "esp32.json": ("teils versiegelt", "partly sealed"),
    "agent.json@state": ("Tokens versiegelt", "tokens sealed"), "mcp-server.json": ("nur Hashes", "hashes only"),
    "join.json": ("nur Hashes", "hashes only"), "meldung-token.json": ("versiegelt", "sealed"),
    "speicher-tmp": ("AES-256-GCM", "AES-256-GCM"), "vapid.pem": ("ist ein Schlüssel", "is a key"),
    "config-undo.json": ("ohne Geheimnisse", "without secrets"), "messages.json": ("teils versiegelt", "partly sealed"),
}
# the kinds of speicher.LOCAL and USERS_SONST in English
KAT_EN = {"Einstellungen": "Settings", "Zustand": "State", "Login": "Login", "Gerät": "Device", "Stimmabdruck": "Voiceprint",
          "Schlüssel": "Key", "noch nicht angeboten": "not offered yet", "Warteschlange": "Queue",
          "alte Sprachnachrichten (bis zur Übernahme in die Chats)": "old voice messages (until moved into the chats)"}
# the Spark's own places outside state/ and users/
SYSTEM = [
    ("/etc/speech-spark/config.json", ("Alle Einstellungen (Geheimnisse versiegelt)", "All settings (secrets sealed)"), "ja", ("teils", "partly")),
    ("/etc/speech-spark/panel.env, mode, connection.txt", ("Start-Passwort, Installationsart, API-Zugang", "Start password, install mode, API access"), "nein", ("", "")),
    ("/etc/speech-spark/tls/", ("HTTPS-Zertifikat des Panels", "Panel HTTPS certificate"), "nein", ("", "")),
    ("/opt/speech-spark/", ("Code, venvs, installierte Version", "Code, venvs, installed version"), "nein", ("", "")),
    ("/var/lib/speech-spark/hf/", ("Modell-Cache (HuggingFace)", "Model cache (HuggingFace)"), "nein", ("", "")),
    ("/var/lib/speech-spark/firmware/", ("ESP32-Firmware", "ESP32 firmware"), "nein", ("signiert", "signed")),
    ("/var/lib/speech-spark/voices/", ("Geklonte Stimmen (WAV und Text)", "Cloned voices (WAV and text)"), "ja", ("", "")),
    ("/var/lib/speech-spark/backups/", ("Sicherungen: 7 neueste plus 5 Ereignis-Sicherungen", "Backups: newest 7 plus 5 event backups"), "–", ("", "")),
    ("journald (Namespace speech-spark)", ("Logs aller Dienste, 14 Tage, höchstens 500 MB", "Logs of all services, 14 days, at most 500 MB"), "nein", ("", "")),
]


@functools.lru_cache(maxsize=1)
def _en_names():
    """The page's own English names (static/js/i18n.js EN, the menu in base.js), for the menu ways in a docstring."""
    out = {}
    try:
        with open(os.path.join(HERE, "static", "js", "base.js"), encoding="utf-8") as f:
            out.update(re.findall(r"\['[a-z]+',t\('([^']+)','([^']+)'\)\]", f.read()))
        with open(os.path.join(HERE, "static", "js", "i18n.js"), encoding="utf-8") as f:
            m = re.search(r"const EN=(\{.*?\});?\n", f.read(), re.S)
        out.update(json.loads(m.group(1)) if m else {})
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
    for name in sorted(set(backup.STATE_FILES) | set(backup.STATE_LOCAL)):
        key = name + "@state" if name + "@state" in INHALT else name
        rows.append({"pfad": "state/" + name, "ort": "global", "art": "state", "inhalt": INHALT.get(key, ("", "")),
                     "sicherung": "ja" if name in backup.STATE_FILES or name == "panel-password" else "nein",
                     "grund": backup.STATE_LOCAL.get(name, ""), "eigen": "", "schutz": sealed.get(key, ("", ""))})
    return rows


def _user_rows():
    rows = []
    for area, (_de, _en, files) in speicher.AREAS.items():
        for f in files:
            rows.append(("users/ID/" + f, f, area))
    for f in list(speicher.LOCAL) + list(USERS_SONST):
        rows.append(("users/ID/" + f + ("/" if f == "messages" else ""), f, ""))
    out = []
    for pfad, f, area in rows:
        kat = speicher.LOCAL.get(f) or USERS_SONST.get(f) or ""
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
    nodes = [{"id": k, "x": v[0], "y": v[1], "name": v[2 + i], "sub": v[4], "group": v[5], "text": v[6 + i], "files": v[8],
              "store": k in ("state", "users", "ablage", "journal")} for k, v in KNOTEN.items()]
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
    return {"version": version, "groups": groups, "nodes": nodes, "edges": [list(e) for e in KANTEN], "steps": steps,
            "storage": rows, "areas": {k: v[1 if en else 0] for k, v in speicher.AREAS.items()}}


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


def mermaid(lang="de"):
    """The picture of the page as a Mermaid flowchart (same nodes and edges)."""
    i = 1 if lang == "en" else 0
    lines = ["```mermaid", "flowchart LR"]
    for k, v in KNOTEN.items():
        shape = ('[("', '")]') if k in ("state", "users", "ablage", "journal") else ('["', '"]')
        lines.append(f'  {k}{shape[0]}{v[2 + i]}<br/>{v[4]}{shape[1]}')
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


BLOCKS = ("bild", "datenfluss", "bausteine", "speicher")
MARK = re.compile(r"(<!-- technik:(\w+) -->\n)(?:.*?\n)?(<!-- /technik:\2 -->)", re.S)


def render_doc(text, lang):
    """The doc with every generated part written again from the code."""
    return MARK.sub(lambda m: m.group(1) + block(m.group(2), lang) + "\n" + m.group(3), text)


def write_docs():
    """Writes the generated parts into docs/de/architektur.md and docs/en/architecture.md (hilfe.py --docs calls it)."""
    data.cache_clear()
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


if __name__ == "__main__" and "--docs" in sys.argv:
    write_docs()   # hilfe.py --docs does the same and says what it wrote
