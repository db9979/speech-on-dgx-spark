"""Datei-Register: every file and folder the panel keeps, listed once (Richtlinie Teil 17, Aufräumen Schritt 8).

One entry per file in state/ (common.STATE), in a profile folder users/<id>/ or directly under users/: what it holds
(German and English, for Zustand → Technik and docs/*/architektur.md), whether it goes into a backup or why not,
which area of „Kopie meiner Daten“ may copy it, and how it is protected. The lists the other modules work with are
built from here and nowhere else: backup.STATE_FILES / STATE_LOCAL (what a backup holds), speicher.AREAS / LOCAL
(what the own storage copies), technik.INHALT / VERSCHLUESSELT / USERS_SONST / USERS_GLOBAL / STATE_SONST (the
architecture page). A new file gets one line here; tests/test_technik.py and test_speicher find every name the
code writes and turn red while it is missing. Names never change: an update must find the data already there.
Pure data, no imports: every module may use it.
"""
from collections import namedtuple

# ort: "state" (state/), "profil" (users/<id>/), "users" (directly under users/), "anderswo" (only described here)
# sicherung: state/ the kind a backup checks ("json", "pem"), "" = stays out (lokal says why); users/ "ja" or "nein"
# bereich: the area of „Kopie meiner Daten“ (BEREICHE) that may copy it; art: the kind of a profile file that stays
# on the Spark; helfer: written through its own helper, not profiles._path; schutz: sealed or hashed (German,
# English); sonst: written by the shell scripts or under another name (the scan in test_technik does not see it)
Datei = namedtuple("Datei", "name ort de en sicherung lokal bereich art helfer schutz sonst")


def profil(name, de, en, bereich="", art="", helfer=False, schutz=None):
    return Datei(name, "profil", de, en, "", "", bereich, art, helfer, schutz, False)


def users(name, de, en, sicherung, schutz=None):
    return Datei(name, "users", de, en, sicherung, "", "", "", False, schutz, False)


def state(name, de, en, sicherung="", lokal="", schutz=None, sonst=False):
    return Datei(name, "state", de, en, sicherung, lokal, "", "", False, schutz, sonst)


def anderswo(name, de, en):
    return Datei(name, "anderswo", de, en, "", "", "", "", False, None, False)


# the areas a profile may copy to its own storage: id -> (German, English). A fixed allowlist: keys, logins,
# passwords of other services, settings and voice prints are in none of them (speicher.py, point 7)
BEREICHE = {
    "gespraeche": ("Gespräche", "Conversations"),
    "gedaechtnis": ("Gedächtnis", "Memory"),
    "alltag": ("Aufgaben und Erinnerungen", "Tasks and reminders"),
    "dokumente": ("Dokumente (Text, Suche, Originale)", "Documents (text, search, originals)"),
    "erstellt": ("Erstellte Dokumente", "Created documents"),
    "bilder": ("Gemalte Bilder", "Painted pictures"),
    "musik": ("Eigene Lieder", "Own songs"),
}

DATEIEN = [
    # users/<id>/: what the own storage may copy (speicher.AREAS), by area
    profil("convos.json", "Gespräche", "Conversations", bereich="gespraeche"),
    profil("toollog.json", "Werkzeug-Log", "Tool log", bereich="gespraeche"),
    profil("room-history.json", "Raummodus-Verlauf", "Room mode history", bereich="gespraeche"),
    profil("memory.json", "Gedächtnis", "Memory", bereich="gedaechtnis"),
    profil("learned.json", "Lesemarken des Lernens aus Gesprächen", "Read marks of learning from conversations", bereich="gedaechtnis"),
    profil("zuordnungen.json", "Gemerkte Zuordnungen", "Remembered matches", bereich="gedaechtnis"),
    profil("tasks.json", "Aufgaben", "Tasks", bereich="alltag"),
    profil("geteilt.json", "Geteilt: welche Dokumente mit welchen Profilen, seit wann; wann Ich → Geteilt zuletzt offen war",
           "Shared: which documents with which profiles, since when; when Me → Shared was last open", art="Einstellungen"),
    profil("reminders.json", "Erinnerungen", "Reminders", bereich="alltag"),
    profil("wissen.db", "Dokumente: Text, Abschnitte mit Kontextzeile, Suche, Vektoren (SQLite)", "Documents: text, sections with context line, search, vectors (SQLite)", bereich="dokumente"),
    profil("docs/files/", "Originale der Uploads", "Originals of uploads", bereich="dokumente"),
    profil("fund.db", "Finden: Suchindex über die eigenen Daten (Titel, Felder, Schlagworte, eigene Schlagworte; SQLite)",
           "Find: search index over the own data (titles, fields, tags, own tags; SQLite)", bereich="dokumente",
           schutz=("Marken mit eigenem Schlüssel je Profil (HMAC)", "marks with a key of its own per profile (HMAC)")),
    profil("suchpruefung.json", "Prüffragen und Läufe der Suchprüfung", "Test questions and runs of the search check", bereich="dokumente"),
    profil("erstellt/", "Erstellte Dokumente", "Created documents", bereich="erstellt"),
    profil("bilder/", "Gemalte Bilder und ihr Verzeichnis (Prompt, Wunsch, Größe)", "Painted pictures and their index (prompt, wish, size)", bereich="bilder"),
    profil("musik/", "Eigene Lieder und ihr Verzeichnis (Wunsch, Beschreibung, Liedtext, Länge)", "Own songs and their index (wish, description, lyrics, length)", bereich="musik"),
    # users/<id>/: everything else stays on the Spark (speicher.LOCAL), with its kind: keys, logins, settings,
    # voiceprint, queues and marks (Richtlinie Teil 1, "Kopie meiner Daten")
    profil("settings.json", "Einstellungen", "Settings", art="Einstellungen"),
    profil("setup.json", "Einrichtung", "Setup", art="Einstellungen"),
    profil("speicher.json", "Ziele des eigenen Speichers", "Own storage targets", art="Einstellungen", schutz=("Schlüssel versiegelt", "key sealed")),
    profil("speicher-stand.json", "Stand des Abgleichs", "Sync state", art="Zustand"),
    profil("transit.json", "Haltestelle", "Stop", art="Einstellungen"),
    profil("feeds.json", "Reddit und Feeds: Quellen, Stichwörter, zuletzt gekommene Titel", "Reddit and feeds: sources, keywords, latest titles", art="Login", schutz=("Feed-Adressen versiegelt", "feed addresses sealed")),
    profil("weather.json", "Wetter-Ort", "Weather place", art="Einstellungen"),
    profil("proactive.json", "Von selbst melden", "Speak up by itself", art="Einstellungen"),
    profil("proactive-rules.json", "Eigene Melde-Regeln", "Own notice rules", art="Einstellungen"),
    profil("hintergrund.json", "Mein Zustand", "My status", art="Einstellungen"),
    profil("mail.json", "Mail-Zugang", "Mail account", art="Login", schutz=("Passwort versiegelt", "password sealed")),
    profil("nas.json", "Speicherorte des Profils (NAS, Cloud)", "Storage places of the profile (NAS, cloud)", art="Login", schutz=("Passwort versiegelt", "password sealed")),
    profil("nasquelle.json", "Wissensordner des Profils", "Knowledge folders of the profile", art="Einstellungen"),
    profil("nasquelle-stand.json", "Was aus den Wissensordnern gelesen ist", "What was read from the knowledge folders", art="Zustand"),
    profil("auslassen.json", "Ausgelassene Ordner und Namensregeln des Profils", "Left-out folders and name rules of the profile", art="Einstellungen"),
    profil("nasablage.json", "Ablage-Ordner des Profils", "Filing folder of the profile", art="Einstellungen"),
    profil("speicher.vor-nas.json", "Kopie meiner Daten vor dem Umzug auf Speicherorte", "Copy of my data before the move to storage places", art="Login"),
    profil("mail-vorrat.bin", "Mail-Vorrat: die neuesten Kopfzeilen (300 je Postfach, 30 Tage) und bis zu 40 Mailtexte ohne Anhänge",
           "Mail supply: the newest headers (300 per mailbox, 30 days) and up to 40 mail texts without attachments", art="Mails",
           schutz=("versiegelt", "sealed")),  # mailvorrat.py
    profil("wetter-vorrat.bin", "Wetter-Vorrat: die letzte Vorhersage für den eigenen Ort", "Weather supply: the last forecast for the own place",
           art="Zustand", schutz=("versiegelt", "sealed")),  # weather.SUPPLY
    profil("pakete-vorrat.bin", "Paket-Vorrat: die zuletzt aus den Mails gelesenen Sendungen", "Parcel supply: the parcels last read from the mails",
           art="Mails", schutz=("versiegelt", "sealed")),  # parcels.SUPPLY
    profil("mail-tidy.json", "Posteingang aufräumen", "Inbox tidy", art="Einstellungen"),
    profil("fuerdich-vorrat.bin", "Für dich: die letzte Lesung je Postfach (gefundene Einträge mit Absender, Betreff und Zeit, kein Mailtext)",
           "For you: the last reading per mailbox (found entries with sender, subject and time, no mail text)", art="Mails",
           schutz=("versiegelt", "sealed")),  # fuerdich.py
    profil("fuerdich.json", "Für dich: was du als erledigt oder uninteressant markiert hast (nur Prüfsummen)",
           "For you: what you marked as done or not interesting (only checksums)", art="Einstellungen"),
    profil("vorgaenge.json", "Offen: was dich braucht, was du auf später gelegt hast und was erledigt ist (Titel und Zustand der Karten); ein Vorschlag, der auf dein Ja wartet, mit dem Text der Mail nur bis zur Antwort",
           "Open: what needs you, what you put off for later and what is done (titles and state of the cards); a proposal waiting for your yes, with the mail's text only until it is answered", art="Warteschlange"),
    profil("dungeon-helden.json", "KI-Dungeon-Master: deine Helden mit Stufe, Werten, Ausrüstung und Fähigkeiten (nur Spieldaten)",
           "AI Dungeon Master: your heroes with level, values, equipment and abilities (game data only)", art="Zustand"),  # dungeon.py
    profil("dungeon-kampagnen.json", "KI-Dungeon-Master: deine Kampagnen mit „Bisher geschah“, den Erzählungen des letzten Kapitels und den Figuren der Gäste",
           "AI Dungeon Master: your campaigns with the story so far, the last chapter's narrations and the guests' characters", art="Zustand"),  # dungeon.py
    profil("dungeon-buch.json", "KI-Dungeon-Master: Heldenbuch aufs reMarkable, je Held die letzte Ausgabe (Nummer, Zeit, Prüfsumme, Zahlen für „Neu seit“) und was noch wartet",
           "AI Dungeon Master: hero book to the reMarkable, per hero the last edition (number, time, checksum, counts for „new since“) and what still waits", art="Zustand"),  # dungeon_buch.py
    profil("dungeon-wappen.json", "KI-Dungeon-Master: Farbe und Zeichen, die du als Gastgeber für das Wappen deiner Gruppe gewählt hast",
           "AI Dungeon Master: colour and charge you chose as host for your group's arms", art="Zustand"),  # dungeon_wappen.py
    profil("interessen.json", "Was ich über dich weiß: bestätigte und abgelehnte Interessen mit Thema und Absendern und der letzte Netz-Tipp (kein Betreff, keine Mail)",
           "What I know about you: confirmed and refused interests with topic and senders and the last web tip (no subject, never a mail)", art="Einstellungen"),
    profil("mailstil.json", "Mailstil (nur die Zusammenfassung, keine Mail)", "Mail style (only the summary, never a mail)", art="Einstellungen"),
    profil("mail-regeln.json", "Mail-Regeln der Seite E-Mail und Regel-Vorschläge (Absender, Wörter, Ordner; keine Mail)",
           "Mail rules of the E-mail page and rule suggestions (senders, words, folders; never a mail)", art="Einstellungen"),  # mailregeln.py
    profil("mail-spaeter.bin", "Später senden: geplante Mails bis zum Senden, danach einen Tag die Zeile ohne Text",
           "Send later: planned mails until they go out, after that for a day the line without text", art="Warteschlange",
           schutz=("versiegelt", "sealed")),  # senden.py
    profil("mail-einordnen.bin", "Alle Mails hier einordnen: der letzte Lauf für „Rückgängig“ (Ordner und Message-IDs, keine Mail), 30 Tage",
           "Sort every mail here: the last run for \"Undo\" (folders and Message-IDs, never a mail), 30 days", art="Zustand",
           schutz=("versiegelt", "sealed")),  # einordnen.py
    profil("spark-kalender.json", "Spark-Kalender: Termine der Kalender ohne Konto (nur hier)", "Spark calendar: appointments of the calendars without an account (only here)",
           art="Termine", schutz=("versiegelt", "sealed")),  # sparkkalender.py
    profil("kalender-server.json", "Kalender-Server: Prüfwert des App-Passworts für Kalender-Apps", "Calendar server: check value of the app password for calendar apps",
           art="Login", schutz=("nur der Hash", "hash only")),  # kalenderserver.py
    profil("calendar.json", "Kalender-Zugang und Freigaben an andere Profile", "Calendar account and shares with other profiles", art="Login", schutz=("Passwort versiegelt", "password sealed")),
    profil("homeassistant.json", "Home-Assistant-Zugang", "Home Assistant account", art="Login", schutz=("Token versiegelt", "token sealed")),
    profil("telegram.json", "Telegram-Kopplung", "Telegram link", art="Login"),
    profil("push.json", "Push-Abos der Browser", "Browser push subscriptions", art="Gerät"),
    profil("remarkable.json", "reMarkable-Zugang", "reMarkable account", art="Login", schutz=("Token versiegelt", "token sealed")),
    profil("remarkable-lib.json", "reMarkable-Bibliothek", "reMarkable library", art="Zustand"),
    profil("mcp-dienste.json", "Eigene MCP-Dienste", "Own MCP services", art="Login", schutz=("Tokens versiegelt", "tokens sealed")),
    profil("mcp-actions.json", "MCP-Aktionen", "MCP actions", art="Zustand"),
    profil("agent.json", "Aufträge und Routinen", "Jobs and routines", art="Einstellungen"),
    profil("voice.json", "Stimmabdruck", "Voiceprint", art="Stimmabdruck", schutz=("versiegelt", "sealed")),
    profil("speaker-code.json", "Codewort am Lautsprecher", "Speaker code word", art="Schlüssel", schutz=("versiegelt", "sealed")),
    profil("telefon.json", "Rufnummern, Telefon-PIN und Telefonate", "Phone numbers, phone PIN and calls", art="Einstellungen",
           schutz=("Nummern und PIN versiegelt", "numbers and PIN sealed")),
    profil("chatkeys.json", "Öffentliche Schlüssel der Geräte", "Devices' public keys", art="Schlüssel"),
    profil("contacts.json", "Kontakte-Zugang", "Contacts account", art="noch nicht angeboten", schutz=("Passwort versiegelt", "password sealed")),
    profil("ha-events.json", "Home-Assistant-Ereignisse", "Home Assistant events", art="Zustand"),
    profil("briefing-sent", "Briefing gesendet", "Briefing sent", art="Zustand"),
    profil("messages.json", "Nachrichten-Einstellungen", "Message settings", art="Einstellungen", schutz=("teils versiegelt", "partly sealed")),
    profil("messages", "Alte Sprachnachrichten", "Old voice messages", art="alte Sprachnachrichten (bis zur Übernahme in die Chats)"),
    profil("agent-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("calendar-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("fix-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("memory-ask.json", "Offene Frage zum Gedächtnis", "Open memory question", art="Warteschlange"),
    profil("mail-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("mcp-dienste-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("messages-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("rufen-pending.json", "Anruf wartet auf Ja", "Call waiting for yes", art="Warteschlange"),
    profil("senden-pending.json", "Mail per Sprache wartet auf Ja", "Mail by voice waiting for yes", art="Warteschlange"),
    profil("tasks-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("remarkable-pending.json", "Wartet auf Ja", "Waiting for yes", art="Warteschlange"),
    profil("rueckfrage-pending.json", "Letzte Rückfrage des Assistenten (10 Minuten, nur ihre Knöpfe)", "The assistant's last question back (10 minutes, only its buttons)", art="Warteschlange"),
    profil("tagebuch.json", "Spark-Tagebuch", "Spark diary", art="Zustand"),
    profil("gesundheit.json", "Schritte, Puls und Schlaf von der Pebble-Uhr (30 Tage)", "Steps, pulse and sleep from the Pebble watch (30 days)",
           art="Gesundheit", schutz=("versiegelt", "sealed")),
    profil("docling-wait", "Dateien, bis Docling sie gelesen hat", "Files until Docling has read them", art="Warteschlange"),
    # users/<id>/: written through their own helper, not through profiles._path (never copied)
    profil("mfa.json", "Zweiter Schritt des Profils", "Profile's second step", art="Schlüssel", helfer=True, schutz=("versiegelt", "sealed")),
    profil("memory-tidy.json", "Aufräum-Vorschlag", "Tidy proposal", art="Warteschlange", helfer=True),
    profil("memory-tidy-checked", "Letzte Aufräum-Prüfung", "Last tidy check", art="Zustand", helfer=True),
    # directly under users/ (all profiles together); sicherung: in a backup or not
    users("profiles.json", "Profile und Geräte", "Profiles and devices", sicherung="ja"),
    users("sessions.json", "Anmeldungen", "Logins", sicherung="ja"),
    users("seen.json", "Zuletzt gesehen", "Last seen", sicherung="ja"),
    users("secret", "Schlüssel der Profil-Anmeldung", "Profile login key", sicherung="nein", schutz=("ist ein Schlüssel", "is a key")),
    users("_chats/", "Chats zwischen Profilen", "Chats between profiles", sicherung="ja", schutz=("AES-256-GCM", "AES-256-GCM")),
    users("_verbund/", "Spark-Verbund: andere Sparks, Kontakte, Warteschlange", "Spark network: other Sparks, contacts, queue", sicherung="ja"),
    users("begleiter.json", "Begleiter-Geräte", "Companion devices", sicherung="ja"),
    # state/: shared state of this Spark that goes into every backup (not the logs, counters, lockouts or
    # login keys); sicherung: the kind backup checks on restore
    state("nas-admin.json", "NAS-Verbindung des Spark", "The Spark's NAS connection", sicherung="json", sonst=True, schutz=("Passwort versiegelt", "password sealed")),  # the admin's NAS connection (nas.py): address, user, password sealed, pinned certificate
    state("offsite.json", "Sicherung nach außen", "Offsite backup", sicherung="json", schutz=("versiegelt", "sealed")),  # Sicherung nach außen: WebDAV address, user, password and backup password (sealed)
    state("docling.json", "Docling-Server: Adresse, Zertifikat, Zahlen", "Docling server: address, certificate, counts", sicherung="json", schutz=("Schlüssel versiegelt", "key sealed")),  # Docling-Server: address, key (sealed), accepted certificate
    state("naszustand.json", "Zustand der NAS: Adresse, SNMP-Benutzer, letzte Werte", "NAS status: address, SNMP user, newest values", sicherung="json", schutz=("Passwörter versiegelt", "passwords sealed")),  # Zustand der NAS: host, SNMPv3 user, both passwords sealed, the newest values
    state("mfa-admin.json", "Zweiter Schritt des Admins", "Admin's second step", sicherung="json", schutz=("versiegelt", "sealed")),  # the admin's second step (secret sealed with secret.key)
    state("apns.json", "Apple-Push-Schlüssel", "Apple push key", sicherung="json", schutz=("Schlüssel versiegelt", "key sealed")),  # iPhone push: Apple key (sealed), key id, team
    state("apns-tokens.json", "iPhone-Geräte für Push", "iPhones for push", sicherung="json"),  # iPhone push: the devices' tokens
    state("telegram.json", "Telegram-Bot", "Telegram bot", sicherung="json", schutz=("Token versiegelt", "token sealed")),  # Telegram bot (token sealed)
    state("github-token.json", "GitHub-Lese-Token", "GitHub read token", sicherung="json", schutz=("versiegelt", "sealed")),  # read-only GitHub token for update checks and downloads (sealed, ghtoken.py)
    state("vapid.pem", "Web-Push-Schlüssel", "Web push key", sicherung="pem", schutz=("ist ein Schlüssel", "is a key")),  # browser push key: the browsers' push subscriptions belong to it
    state("telefon.json", "Telefon: Zugang zur Anlage, Mobilteile", "Phone: access to the PBX, handsets", sicherung="json", schutz=("Kennwort versiegelt", "password sealed")),  # Den Spark anrufen (telefon.py): PBX access (password sealed), handsets → profiles, numbers seen lately (internal only)
    state("esp32.json", "Lautsprecher und Firmware", "Speakers and firmware", sicherung="json", schutz=("teils versiegelt", "partly sealed")),  # ESP32 speakers: board variant, firmware, automatic updates
    state("agent.json", "Agent-Stufen, MCP-Dienste", "Agent levels, MCP services", sicherung="json", schutz=("Tokens versiegelt", "tokens sealed")),  # agent levels and MCP services (tokens sealed)
    state("geraete-updates.json", "Geräte-Updates", "Device updates", sicherung="json"),  # Geräte-Updates: versions seen, notes due, the night round of the speakers
    state("regel-versionen.json", "Regel-Versionen", "Rule versions", sicherung="json"),  # Einstellungs-Assistent: the own rules before each change (Version 3)
    state("berater.json", "Vorschläge des Assistenten", "Assistant proposals", sicherung="json"),  # Einstellungs-Assistent: proposals, what was there before, Nachkontrolle
    state("faelle.json", "Fälle", "Cases", sicherung="json", sonst=True),  # its cases (fingerprints, counts, at most three examples with consent)
    state("gut-saetze.json", "Mit 👍 bestätigte Fragen", "Questions confirmed with 👍", sicherung="json", sonst=True),  # questions confirmed with 👍 (with consent): protected in the Prüfstand
    state("mail-gesendet.json", "Mails senden: heute gesendete Mails je Profil (nur Zahlen)", "Send mail: mails sent today per profile (numbers only)", sicherung="json"),
    state("wachposten.json", "Wachposten: wartende Meldungen (Regel, feste Wörter, Zeit) und Zeiten der gesendeten", "Sentry: waiting notes (rule, fixed words, time) and times of those sent", sicherung="json"),
    state("dienstwacht.json", "Dienst-Wächter", "Service watcher", sicherung="json"),  # Dienst-Wächter: services taken off the list, their state, outages of 7 days, notes due
    state("mcp-dienste-admin.json", "Erlaubte MCP-Ziele", "Allowed MCP hosts", sicherung="json"),  # own MCP services of profiles: hosts the admin allows, blocked services
    state("mcp-server.json", "MCP-Programme (Token-Hashes)", "MCP programs (token hashes)", sicherung="json", schutz=("nur Hashes", "hashes only")),  # programs connected to the Spark as an MCP server (only hashes of their tokens)
    state("personen-vorrang.json", "Vorrang pro Profil", "Priority per profile", sicherung="json"),  # priority for people: the stage the admin gave each profile (stufe.py)
    state("quality-cases.json", "Eigene Testfragen", "Own test questions", sicherung="json"),  # own quality test questions
    state("quality-history.json", "Verlauf der Qualitätstests", "Quality test history", sicherung="json"),
    state("setup.json", "Einrichtungs-Assistent erledigt", "Setup wizard done", sicherung="json"),  # first-start wizard done
    state("doc-quotas.json", "Dokument-Kontingente", "Document quotas", sicherung="json"),  # the admin's own document space per profile (wissen.py)
    state("admins.json", "Profile als Admins", "Profiles as admins", sicherung="json"),  # profiles as admins: roles and the main admin profile (coadmin.py)
    state("ohne-tageslimit.json", "Profile ohne Tageslimit", "Profiles without daily limit", sicherung="json"),  # profiles the admin freed from daily limits (coadmin.py)
    state("features-seen.json", "Wann Funktionen frei wurden", "When functions were released", sicherung="json"),  # when each function was first on („neu freigegeben“ in tipps.py, features.py)
    state("verbrauch-kontingent.json", "eigene Kontingente und Nachschlag", "Own quotas and extras", sicherung="json"),  # Kontingent: the admin's own limits per profile (verbrauch.py)
    state("iphone-pruef.json", "Prüfzugänge für die iPhone-App (Hashes)", "Review accesses for the iPhone app (hashes)", sicherung="json", schutz=("nur Hashes", "hashes only")),  # Apple's app review (pruefzugang.py)
    state("mitschreib-links.json", "Mitschreib-Links für Listen (Hashes)", "Write links for lists (hashes)", sicherung="json", schutz=("nur Hashes", "hashes only")),  # links for people without a profile to put entries on one list (mitschreiblink.py)
    state("dungeon-runden.json", "KI-Dungeon-Master: gemeinsame Werte aller Runden (Bilder des Tages, Daumen je Welt)", "AI Dungeon Master: shared values of all rounds (pictures of the day, thumbs per world)", sicherung="json"),  # rounds of the game (dungeon.py)
    state("dungeon-runden", "KI-Dungeon-Master: eine Datei je Runde mit Plätzen (Hashes der Links), Helden, Aktionen und Erzählung", "AI Dungeon Master: one file per round with seats (hashes of the links), heroes, actions and narration", lokal="laufende Runden, gehen Stunden nach ihrem Ende", schutz=("nur Hashes", "hashes only")),  # dungeon_ablage.py (Punkt 14)
    state("dungeon-gaeste.json", "KI-Dungeon-Master: Gast-Konten (Hash der Adresse, Hashes der Geräte, Helden; Adresse nur versiegelt bei Zug-Mails)", "AI Dungeon Master: guest accounts (hash of the address, hashes of the devices, heroes; the address only sealed for turn mails)", sicherung="json", schutz=("versiegelt", "sealed")),  # guest accounts (dungeon_gast.py)
    state("dungeon-pruefstand.json", "KI-Dungeon-Master: Ergebnis des Balance-Prüfstands (Siege, verlorenes Leben und Runden je Stufe und Gruppengröße, ohne und mit Runen, gegen Herr und Boss)", "AI Dungeon Master: the balance bench's result (wins, life lost and turns per level and group size, without and with runes, against master and boss)", sicherung="json"),  # balance bench (dungeon_pruefstand.py)
    state("dungeon-erzaehlstand.json", "KI-Dungeon-Master: Ergebnis des Erzähler-Prüfstands (Punkte, Gründe und Zeiten je Szene und Modell, ohne Erzähltext)", "AI Dungeon Master: the narrator bench's result (points, reasons and times per scene and model, without narration text)", sicherung="json"),  # narrator bench (dungeon_erzaehlstand.py)
    state("dungeon-erzaehlfehler.json", "KI-Dungeon-Master: Erzähler-Fehler (Züge mit 👎 und festem Grund: Aktionen, Würfe und Erzählung, Helden mit den Namen des Prüfstands, ohne Profil und Runde) und die daraus übernommenen Prüfstand-Szenen", "AI Dungeon Master: narrator errors (turns with 👎 and a fixed reason: actions, dice and narration, heroes with the bench's names, without profile and round) and the bench scenes taken over from them", sicherung="json"),  # narrator errors (dungeon_erzaehlstand.py)
    state("dungeon-figuren.json", "KI-Dungeon-Master: Helden von Gästen zum Mitnehmen (Hashes der Figur-Codes)", "AI Dungeon Master: heroes of guests to take along (hashes of the hero codes)", sicherung="json", schutz=("nur Hashes", "hashes only")),  # Figur-Codes (dungeon.py)
    state("dungeon-bild", "KI-Dungeon-Master: Szenenbilder einer Runde (höchstens 12, gehen mit der Runde), Heldenporträts, Kapitel-Titelbilder und Bilder für Ausrüstung und Zauber (PNG)", "AI Dungeon Master: scene pictures of a round (at most 12, they go with the round), hero portraits, chapter covers and pictures for gear and spells (PNG)", lokal="Bilder des Spiels, gehen mit Runde, Held oder Kampagne"),  # pictures (dungeon.py, Stufe 3)
    state("dungeon-bild-klein", "KI-Dungeon-Master: kleine Kopien der Bilder für Listen (höchstens 96 Pixel, gehen mit ihrem Bild)", "AI Dungeon Master: small copies of the pictures for lists (96 pixels at most, they go with their picture)", lokal="kleine Bilder, entstehen von selbst neu"),  # small copies (dungeon.small_png)
    state("dungeon-ton", "KI-Dungeon-Master: die vorgelesenen letzten Züge einer Runde (WAV und MP3, höchstens 3 je Runde)", "AI Dungeon Master: the last turns of a round read aloud (WAV and MP3, at most 3 per round)", lokal="Ton der letzten Züge, geht mit der Runde"),  # read aloud (dungeon.py)
    state("dungeon-klone", "KI-Dungeon-Master: die Stimme jeder Figur als Klon-Vorlage, wenn die Sprachausgabe ein Base-Modell hat (WAV mit dem gesprochenen Satz, höchstens 200, für alle Runden)", "AI Dungeon Master: every character's voice as clone reference when the speech output has a Base model (WAV with the sentence spoken, at most 200, for all rounds)", lokal="Stimmen der Figuren, werden neu gemacht"),  # clone references (dungeon.py klon_keep)
    state("dungeon-musik.json", "KI-Dungeon-Master: Musik vorbereiten an oder aus, Stücke je Welt und Stimmung, Speicherplatz", "AI Dungeon Master: prepare music on or off, pieces per world and mood, storage", sicherung="json"),  # Funktionen → KI-Dungeon-Master → Regeln anpassen → Musik am Tisch (dungeon_musik.py)
    state("dungeon-lieder", "KI-Dungeon-Master: Heldenlieder je Runde und Kapitel vom eigenen Musikmodell (MP3 mit den Namen der Helden)", "AI Dungeon Master: hero songs per round and chapter from the own music model (MP3 with the heroes' names)", lokal="lässt sich neu singen, gehört zur Runde"),  # dungeon_lied.py
    state("dungeon-musik", "KI-Dungeon-Master: Musikstücke je Welt und Stimmung vom eigenen Musikmodell (MP3, für alle Runden, nichts Persönliches)", "AI Dungeon Master: music pieces per world and mood from the own music model (MP3, for every round, nothing personal)", lokal="lässt sich jederzeit neu machen, groß"),  # dungeon_musik.py
    state("dungeon-personen.json", "KI-Dungeon-Master: Personen-Katalog mit Karte, Wesen, Rolle, Stimme, Gesicht und Haltung zu den Helden (nur Spieldaten)", "AI Dungeon Master: people catalog with card, traits, role, voice, face and attitude towards the heroes (game data only)", sicherung="json"),  # Personen-Katalog (dungeon_personen.py)
    state("dungeon-geschichten.json", "KI-Dungeon-Master: Geschichten des Admins und der Gastgeber mit Akten, Wendepunkten und Tabus", "AI Dungeon Master: the stories of the admin and the hosts with acts, turning points and taboos", sicherung="json"),  # Funktionen → KI-Dungeon-Master → Geschichten (dungeon.py)
    state("dungeon-geschichten-aus.json", "KI-Dungeon-Master: Geschichten, die ein Gastgeber ausgeblendet hat (nur IDs)", "AI Dungeon Master: stories a host hid (ids only)", sicherung="json"),  # Funktionen → Meine Daten → Eigene Geschichten (dungeon_geschichten.py)
    state("dungeon-dingbilder.json", "KI-Dungeon-Master: Stand der Bilder für Ausrüstung und Zauber (letzter Lauf, Tageszahl, abgelehnte Einträge, gemalte Fundstücke)", "AI Dungeon Master: state of the pictures for gear and spells (last run, count of the day, refused entries, painted finds)", lokal="Stand des Malens, wird neu aufgebaut"),  # dungeon_dingbild.py
    state("dungeon-regeln.json", "KI-Dungeon-Master: eigene Regeln und Katalog-Einträge des Admins", "AI Dungeon Master: the admin's own rules and catalog entries", sicherung="json"),  # Funktionen → KI-Dungeon-Master (dungeon.py)
    state("join.json", "Einladungen (Hashes)", "Invitations (hashes)", sicherung="json", schutz=("nur Hashes", "hashes only")),  # new people by invitation: the switch, invitations (code hashes) (join.py)
    # state/: every other file or folder, with the reason it stays out of a backup
    state("secret.key", "Schlüssel für alles Versiegelte", "Key for everything sealed", lokal="Schlüssel: nur verschlüsselt in der Umzugs-Sicherung (move-keys.json)", schutz=("ist der Schlüssel", "is the key")),
    state("panel-password", "Admin-Passwort (Hash)", "Admin password (hash)", lokal="kommt einzeln in die Sicherung (eigener Weg in create)", schutz=("Hash", "hash")),
    state("admin-session.key", "Schlüssel der Admin-Sitzung", "Admin session key", lokal="Schlüssel der Admin-Sitzung: nach einem Umzug neu anmelden", sonst=True, schutz=("ist ein Schlüssel", "is a key")),
    state("vorrang-key", "Schlüssel Panel ↔ Sprachdienste", "Key panel ↔ speech services", lokal="Schlüssel zwischen Panel und Sprachdiensten, entsteht neu", schutz=("ist ein Schlüssel", "is a key")),
    state("guard.json", "Sperren nach Fehlversuchen", "Lockouts", lokal="Sperren nach Fehlversuchen, kurzlebig"),
    state("revoked.json", "Widerrufene Sitzungen", "Revoked sessions", lokal="widerrufene Sitzungen, kurzlebig"),
    state("guard-xff-hinted.json", "Proxy-Hinweis gezeigt", "Proxy hint shown", lokal="Hinweis gezeigt"),
    state("audit.log", "Änderungsprotokoll mit Prüfkette, je Datei 1 MB, ein Jahr (audit.log.1 …)", "Change log with hash chain, 1 MB per file, one year (audit.log.1 …)",
          lokal="Protokoll dieses Geräts; versiegelte Kopie mit der Sicherung nach außen", schutz=("Prüfkette (SHA-256)", "hash chain (SHA-256)")),
    state("offsite-protokoll.enc.part", "Versiegelte Kopie des Änderungsprotokolls auf dem Weg zum NAS", "Sealed change log copy on its way to the NAS", lokal="nur während des Hochladens, danach gelöscht"),
    state("audit.log.lock", "Schreibsperre des Änderungsprotokolls (leer)", "Write lock of the change log (empty)", lokal="leere Sperrdatei"),
    state("traces.jsonl", "Logs → Anfragen, 48 h", "Logs → Requests, 48 h", lokal="Anfrage-Verlauf, 48 h"),
    state("latency.json", "Wartezeiten", "Waiting times", lokal="Statistik"),
    state("verbrauch.json", "Verbrauch je Modell, Aufgabe und Profil (nur Zahlen)", "Usage per model, task and profile (numbers only)", lokal="Statistik des Verbrauchszählers (Tage und Monate, nur Zahlen)"),
    state("verbrauch-stand.json", "Stand der Kontingente (Tag, Woche, Monat; nur Zahlen)", "Running totals of the quotas (day, week, month; numbers only)", lokal="Zählt bis zum Ende des Zeitraums, Löschen der eigenen Zahlen setzt es nicht zurück"),
    state("livecheck.json", "Echtprüfung", "Live check", lokal="letzte Echtprüfung"),
    state("satzende.json", "Satzende am Tonfall: Messung an Sprechpausen (nur Zahlen)", "Turn end by tone: measurement at speaking pauses (numbers only)", lokal="Messung, nur Zahlen, endet nach 200 Pausen oder 7 Tagen"),
    state("kalender-spiegel", "Spark-Kalender: Kopie jedes CalDAV-Kalenders (je Kalender-Eintrag eine Datei)",
          "Spark calendar: copy of every CalDAV calendar (one file per calendar entry)",
          lokal="Kopie der Kalender, holt sie nach einem Umzug neu vom Server", schutz=("versiegelt", "sealed")),  # kalenderspiegel.py
    state("rundlauf.json", "Probeläufe des Rundlauf-Wächters (Zeiten in ms, feste Wörter)", "Test runs of the round-trip check (times in ms, fixed words)",
          lokal="Messwerte dieses Geräts, ein neuer Rechner misst neu"),
    state("waerter.key", "Schlüssel für den Wärter des Modell-Rechners", "Key for the model computer's Wärter",
          lokal="Schlüssel der Kopplung: nach einem Umzug wird neu gekoppelt", schutz=("ist ein Schlüssel", "is a key"),
          sonst=True),  # Spark teilen (tarswart.py, steuer.py): written by the pairing, the same on both computers
    state("live-monitors.json", "Wandmonitore", "Wall monitors", lokal="Wandmonitore dieses Geräts"),
    state("dienste-zustand.json", "Hintergrund-Dienste", "Background services", lokal="Zustand der Hintergrund-Dienste"),
    state("weiche-stats.json", "Weiche-Statistik", "Switch statistics", lokal="Statistik", sonst=True),
    state("bedarf.lock", "Sperre: nur ein Modell bei Bedarf zur Zeit (Bild oder Musik)",
          "Lock: only one model on demand at a time (pictures or music)", lokal="leere Sperrdatei, nur auf dem Spark"),
    state("bild-test.json", "Letztes Probebild (Bild testen)", "Last sample picture (Test a picture)", lokal="Messwert dieses Geräts (Bild testen)"),
    state("musik-test.json", "Letzte Messung (Musik testen)", "Last measurement (Test music)", lokal="Messwerte dieses Geräts (Musik testen)"),
    state("musik-test-2b-1.mp3", "Probestück 1 mit 2B (Musik testen)", "Sample 1 with 2B (Test music)", lokal="entsteht beim nächsten Test neu"),
    state("musik-test-2b-2.mp3", "Probestück 2 mit 2B (Musik testen)", "Sample 2 with 2B (Test music)", lokal="entsteht beim nächsten Test neu"),
    state("musik-test-2b-klein-1.mp3", "Probestück 1 mit 2B klein (Musik testen)", "Sample 1 with 2B small (Test music)", lokal="entsteht beim nächsten Test neu"),
    state("musik-test-2b-klein-2.mp3", "Probestück 2 mit 2B klein (Musik testen)", "Sample 2 with 2B small (Test music)", lokal="entsteht beim nächsten Test neu"),
    state("musik-test-xl-1.mp3", "Probestück 1 mit XL (Musik testen)", "Sample 1 with XL (Test music)", lokal="entsteht beim nächsten Test neu"),
    state("musik-test-xl-2.mp3", "Probestück 2 mit XL (Musik testen)", "Sample 2 with XL (Test music)", lokal="entsteht beim nächsten Test neu"),
    state("weiche-unklar.json", "Unklare Fragen der Weiche, anonymisiert (höchstens 100, 7 Tage)", "Unclear questions of the switch, anonymized (at most 100, 7 days)", lokal="Hilfe zum Abstimmen, kurz aufbewahrt", schutz=("versiegelt", "sealed")),
    state("weiche-history.json", "Weiche-Änderungen", "Switch changes", lokal="Verlauf der Weiche-Änderungen (die Regeln selbst stehen in config.json)", sonst=True),
    state("bewertungen.json", "Bewertungen pro Tag", "Ratings per day", lokal="Zähler pro Tag", sonst=True),
    state("quality.json", "Letzter Qualitätstest", "Last quality test", lokal="letztes Ergebnis"),
    state("config-undo.json", "Rückgängig (ohne Geheimnisse)", "Undo (no secrets)", lokal="Rückgängig dieses Geräts", schutz=("ohne Geheimnisse", "without secrets")),
    state("tipps.json", "Gezeigte Tipps", "Tips shown", lokal="gezeigte Tipps"),
    state("iphone-update.json", "Update aus der iPhone-App", "Update from the iPhone app", lokal="Hinweise zum Update, entstehen neu"),
    state("vision.json", "Bildfragen, 10 min", "Picture questions, 10 min", lokal="Ergebnisse von Bildfragen, 10 Minuten"),
    state("doc-embed.json", "Vektormodell", "Vector model", lokal="Zustand des Vektormodells"),
    state("doc-rank.json", "Nachsortier-Modell", "Re-ranking model", lokal="Prüfsummen des Nachsortier-Modells, entstehen neu"),
    state("notaus.json", "Notaus", "Kill switch", lokal="Notaus gilt nur auf diesem Gerät"),
    state("wartung.json", "Wartungspause", "Maintenance pause", lokal="Wartungspause gilt nur für das laufende Update"),
    state("praxistest-stand.json", "Praxistest: je Prüfpunkt die Markierung (klappt, Problem, später) und die Zeit", "Hands-on test: per point the mark (works, problem, later) and the time", "json"),
    state("modelle-messung.json", "Messung der Modelle (nur Zahlen)", "Model measurement (numbers only)", lokal="Messwert dieses Geräts (speech-spark modelle messen)"),
    state("qwen38-vorher.json", "Vor dem Umzug: laufende qwen38-Dienste und alte Adresse des Sprachmodells", "Before the move: running qwen38 services and the language model's old address", lokal="gilt nur für dieses Gerät (speech-spark modelle llm uebernehmen, zurueck)"),
    state("qwen38-vorher.json.alt", "Die Notiz des letzten Umzugs nach dem Weg zurück", "The last move's note after the way back", lokal="gilt nur für dieses Gerät", sonst=True),
    state("llm-start.json", "Was das eigene Sprachmodell beim Wechseln oder Starten gerade tut: Schritt, Sekunden, feste Wörter", "What the own language model does while it switches or starts: step, seconds, fixed words", lokal="gilt nur für dieses Gerät (speech-spark modelle wechseln, Lange Gespräche)"),
    state("llm-startzeiten.json", "Je Modell die Sekunden seines letzten Starts (für die erwartete Zeit)", "Per model the seconds of its last start (for the expected time)", lokal="gilt nur für dieses Gerät"),
    state("modelle-wechsel.json", "Je Art das Modell vor dem letzten Wechsel (7 Tage zurückholbar)", "Per kind the model before the last switch (7 days to bring back)", lokal="gilt nur für dieses Gerät (speech-spark modelle wechseln, zurueckholen)"),
    state("modelle-eigene.json", "Eigene Modelle des Admins (Hugging-Face-Name, fester Commit, Speicherbedarf)", "The admin's own models (Hugging Face name, pinned commit, memory need)", lokal="gilt nur für dieses Gerät (Zustand → Modelle, Eigene Modelle)"),
    state("modelle-wunsch.json", "Wunsch des Panels für den nächsten Modellwechsel oder „Lange Gespräche“, Sekunden", "The panel's wish for the next model switch or \"Long conversations\", seconds", lokal="wird vom Wechsel sofort gelesen und gelöscht"),
    state("modelle-probe.json", "Welches Modell gerade ausprobiert wird (Zustand → Modelle „Ausprobieren“), Sekunden", "Which model is being tried (Status → Models \"Try\"), seconds", lokal="nach einem Tag, einem Wechsel oder „Verwerfen“ weg"),
    state("werkstatt-wunsch.json", "Wunsch des Panels für den nächsten Auftrag der Werkstatt (Art, Text des Admins), Sekunden", "The panel's wish for the Workshop's next order (kind, the admin's text), seconds", lokal="wird von der Werkstatt sofort gelesen und gelöscht"),
    state("angriffsprobe.json", "Angriffsprobe: die letzten 20 Läufe mit Fall-Kennungen und Zahlen je Tarnung und Werkzeug, nie ein Text", "Attack probe: the last 20 runs with case ids and counts per disguise and tool, never a text", lokal="Ergebnisse dieses Geräts (Zustand → Werkstatt)"),
    state("fernzugang.json", "Fernzugang: gekoppelte Fern-Server (Name, System, Host-Schlüssel, Zeiten), je Server ein eigener SSH-Schlüssel des Panels, der Geräteschlüssel des Ankers nur als SHA-256", "Remote access: paired remote servers (name, system, host key, times), per server an own SSH key of the panel, the anchor's device key only as SHA-256", lokal="Kopplungen dieses Panels (Fernzugang → Systeme)", schutz=("SSH-Schlüssel versiegelt, Geräteschlüssel nur als Hash", "SSH key sealed, device key only as a hash")),
    state("fernanker.json", "Fernzugang: der Signaturschlüssel des Panels für das Aktualisieren der Anker (Ed25519; der private Teil nur versiegelt im Tresor)", "Remote access: the panel's signing key for updating the anchors (Ed25519; the private half only sealed in the vault)", lokal="Signaturschlüssel dieses Panels (Fernzugang → Systeme → Aktualisieren)", schutz=("privater Teil versiegelt", "private half sealed")),
    state("fernnotizen.json", "Fernzugang: die Notiz je System (Text versiegelt, „Assistent darf lesen“, Zeit, die letzten 10 Fassungen versiegelt); löschen unter Fernzugang → Systeme (Kasten Notizen) oder mit dem System", "Remote access: the note per system (text sealed, \"Assistant may read\", time, the last 10 versions sealed); delete under Remote access → Systems (box Notes) or with the system", lokal="Notizen zu den Kopplungen dieses Panels, versiegelt mit seinem Tresor (wie fernzugang.json)", schutz=("Text versiegelt", "text sealed")),
    state("fernordner.json", "Fernzugang: die Ordner (Name, Symbol, Reihenfolge) und welches System in welchem Ordner liegt; löschen unter Fernzugang → Systeme (Ordner anklicken → Löschen), die Systeme bleiben", "Remote access: the folders (name, symbol, order) and which system lies in which folder; delete under Remote access → Systems (click a folder → Delete), the systems stay", lokal="Ordnung der Kopplungen dieses Panels (Fernzugang → Systeme)"),
    state("fernzugang-verlauf.json", "Fernzugang: Verlauf der Sitzungen der letzten Tage (Zeit, System, Admin, Art, Dauer, Zuhause oder Internet), nie eine Adresse oder ein Inhalt; löschen unter Fernzugang → Systeme → Verlauf", "Remote access: history of the sessions of the last days (time, system, admin, kind, duration, home or internet), never an address or content; delete under Remote access → Systems → History",
          lokal="Verlauf dieses Panels, nur Zeiten und Namen; gehört nicht in die Sicherung"),
    state("spontanhilfe-verlauf.json", "Spontanhilfe: Verlauf der letzten Tage (Zeit, Admin, Art, Dauer, Zuhause oder Internet, verfallene oder gesperrte Nummern), nie der Name der Person, eine Adresse, ein Bild oder der Chat; löschen unter Fernzugang → Spontanhilfe → Verlauf der Spontanhilfe", "Spontaneous help: history of the last days (time, admin, kind, duration, home or internet, expired or locked numbers), never the person's name, an address, a picture or the chat; delete under Remote access → Spontaneous help → History of spontaneous help",
          lokal="Verlauf dieses Panels, nur Zeiten und Zahlen; gehört nicht in die Sicherung"),
    state("werkstatt.json", "Ergebnisse der Werkstatt: letzte 20 Aufträge mit Antwort und Patch, Code-Messung je Sprachmodell, letzter Testlauf", "The Workshop's results: last 20 orders with answer and patch, code measurement per language model, last test run", lokal="Ergebnisse dieses Geräts (Funktionen → Werkstatt)"),
    state("docker-modelle", "Modelle in Docker: Zwischenspeicher der Engine (Kernel) und ihr Socket, je Modell", "Models in Docker: the engine's cache (kernels) and its socket, per model", lokal="wird beim nächsten Messen neu gebaut"),
    state("modelle-messen-wunsch.json", "Wunsch des Panels für die nächste Messung (Zustand → Modelle „Messen“), Sekunden", "The panel's wish for the next measurement (Status → Models \"Measure\"), seconds", lokal="wird von der Messung sofort gelesen und gelöscht"),
    state("gehaeuse-wunsch.json", "Wunsch des Panels für das Gehäuse (einrichten, entfernen, neu starten), Sekunden", "The panel's wish for the case (set up, remove, restart), seconds", lokal="wird von der Einrichtung sofort gelesen und gelöscht"),
    state("schirm.key", "Schlüssel der Steuerzentrale am Bildschirm (nur der Dienstnutzer liest ihn)", "Key of the control centre on the screen (only the service user reads it)",
          lokal="gilt nur für dieses Gerät, das Panel macht ihn neu", schutz=("nur Dienstnutzer", "service user only")),
    state("wartung-satz-de.pcm", "Wartungssatz als Ton", "Maintenance sentence as sound", lokal="Wartungssatz für Lautsprecher, macht der Spark selbst neu"),
    state("wartung-satz-en.pcm", "Wartungssatz als Ton (Englisch)", "Maintenance sentence as sound (English)", lokal="Wartungssatz für Lautsprecher, macht der Spark selbst neu"),
    state("notbetrieb-satz-de.pcm", "Notbetrieb-Satz als Ton", "Emergency sentence as sound", lokal="Satz für Lautsprecher, wenn der Modell-Rechner fehlt; macht der Spark selbst neu"),
    state("notbetrieb-saetze", "Feste Sätze und Bausteine für den Notbetrieb als Ton", "Fixed sentences and building blocks for emergency mode as sound", lokal="Sätze für Lautsprecher, wenn der Modell-Rechner fehlt; macht der Spark selbst neu"),
    state("umzug-hinweis.json", "Hinweis nach dem Umzug (nur die Zeit)", "Hint after the move (time only)", lokal="gilt nur für den Rechner, auf den das Panel umgezogen ist (14 Tage)"),
    state("notbetrieb-satz-en.pcm", "Notbetrieb-Satz als Ton (Englisch)", "Emergency sentence as sound (English)", lokal="Satz für Lautsprecher, wenn der Modell-Rechner fehlt; macht der Spark selbst neu"),
    state("nasquelle-tmp", "Zwischendateien der Wissensordner, Sekunden", "Knowledge folder staging, seconds", lokal="Zwischendateien beim Lesen von Wissensordnern, werden sofort gelöscht"),
    state("notaus-mine.json", "Mein Notaus", "My kill switch", lokal="Notaus gilt nur auf diesem Gerät"),
    state("notaus-keys.json", "Notaus-Auslöser", "Kill switch triggers", lokal="Auslöser gelten nur auf diesem Gerät"),
    state("meldung-token.json", "Token für Meldungen", "Report token", lokal="Token wird neu eingetragen", schutz=("versiegelt", "sealed")),
    state("meldungen", "Meldungs-Entwürfe", "Report drafts", lokal="Entwürfe, kurzlebig"),
    state("ack", "Sofort-Sätze als Ton", "Instant sentences as sound", lokal="Ton-Cache, entsteht neu"),
    state("android", "Android-App zum Download", "Android app for download", lokal="Download-Cache"),
    state("begleiter", "Begleiter-Updates", "Companion updates", lokal="Download-Cache"),
    state("begleiter-inbox", "Vom Handy auf den PC, 24 h", "Phone to PC, 24 h", lokal="Dateien vom Handy, 24 h"),
    state("speicher-tmp", "Zwischenablage des eigenen Speichers", "Own storage staging", lokal="Zwischenablage", schutz=("AES-256-GCM", "AES-256-GCM")),
    state("speech-active", "Zeitpunkt der letzten Sprache", "Time of last speech", lokal="Zeitmarke"),
    state("speech-spark-llm.json", "Zustand der Engine des eigenen Sprachmodells", "Own language model engine state", lokal="Zustand der Engine"),
    state("speech-spark-asr-engine.json", "Zustand der ASR-Engine", "ASR engine state", lokal="Zustand der Engine"),
    state("speech-spark-tts-*.json", "Zustand der TTS-Engines", "TTS engine state", lokal="Zustand der Engines", sonst=True),
    state("bench-latest.json", "Letzte Messung", "Last benchmark", lokal="Messung dieses Geräts"),
    state("bench-history.json", "Messungen", "Benchmarks", lokal="Messungen dieses Geräts"),
    state("update-progress.json", "Update-Fortschritt", "Update progress", lokal="Update-Fortschritt"),
    state("update-target", "Gewünschter Update-Stand", "Requested update target", lokal="Update-Auftrag", sonst=True),
    state("update-night.json", "Nacht-Update", "Night update", lokal="Nacht-Update", sonst=True),
    state("migrated-chunk10", "Einmalige Umstellung erledigt", "One-time migration done", lokal="Marke einer einmaligen Umstellung", sonst=True),
    # described here, lying elsewhere: the firmware folder next to state/ (technik.SYSTEM lists the path)
    anderswo("firmware", "ESP32-Firmware", "ESP32 firmware"),
]

# ---------------------------------------------------------------- the lists built from the register
_NAMEN = {d.name for d in DATEIEN if d.ort in ("profil", "users")}


def schluessel(d):
    """The name in INHALT and VERSCHLUESSELT: a file in state/ with the name of a profile file gets "@state"."""
    return d.name + "@state" if d.ort == "state" and d.name in _NAMEN else d.name


# backup.py: name -> kind of every file in state/ a backup holds; every other one with the reason it stays out
STATE_FILES = {d.name: d.sicherung for d in DATEIEN if d.ort == "state" and d.sicherung}
STATE_LOCAL = {d.name: d.lokal for d in DATEIEN if d.ort == "state" and not d.sicherung}
# speicher.py: area -> (German, English, files or folders "x/" in the profile folder); the rest with its kind
AREAS = {a: (de, en, tuple(d.name for d in DATEIEN if d.bereich == a)) for a, (de, en) in BEREICHE.items()}
LOCAL = {d.name: d.art for d in DATEIEN if d.ort == "profil" and not d.bereich and not d.helfer}
# technik.py: what is in a file, what is sealed, the files the scans of test_technik cannot see
INHALT = {schluessel(d): (d.de, d.en) for d in DATEIEN}
VERSCHLUESSELT = {schluessel(d): d.schutz for d in DATEIEN if d.schutz}
USERS_SONST = {d.name: d.art for d in DATEIEN if d.helfer}
USERS_GLOBAL = {d.name: d.sicherung for d in DATEIEN if d.ort == "users"}
STATE_SONST = {d.name for d in DATEIEN if d.sonst}
