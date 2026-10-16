"""Zustand → Technik, Knoten-Seiten: the pages of state, user data, storage and logs
(state, users, ablage, journal). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "state": {
        "stand": "4099a0b7b5",
        "bezug": {
            "backup.MOVE_MIN": ["s8"], "backup._seal_keys": ["s8"], "backup._check_state": ["s9"],
            "backup._swap": ["s10"], "backup._forget_cached": ["s11"],
        },
        "kurz": ("In state/ liegt, was für den ganzen Spark gilt und keinem Profil gehört: Schlüssel, Zugänge des "
                 "Admins, Telegram-Bot, Push-Schlüssel, Lautsprecher, Zähler, Sperren und Zustände der Dienste. "
                 "Geheimnisse darin sind mit dem Schlüssel des Spark versiegelt.",
                 "state/ holds what applies to the whole Spark and belongs to no profile: keys, the admin's accounts, "
                 "the Telegram bot, push keys, speakers, counters, locks and the state of the services. Secrets in it "
                 "are sealed with the Spark's key."),
        "warum": ("Eine Kopie der Dateien (eine Sicherung, ein Blick in den Ordner) soll keine Passwörter verraten. "
                  "Und was nur auf diesem Gerät Sinn hat (Sperren, Zähler, Caches, Schlüssel), soll nicht mit einer "
                  "Sicherung auf einen anderen Spark wandern.",
                  "A copy of the files (a backup, a look into the folder) should not reveal passwords. And what only "
                  "makes sense on this device (locks, counters, caches, keys) should not travel to another Spark with "
                  "a backup."),
        "ablauf": [
            S("s1", "start", ("Ein Modul merkt sich etwas", "A module keeps something"),
              ("für den ganzen Spark", "for the whole Spark"),
              ("Der Ordner state/ gehört dem Dienst-Benutzer; install.sh legt ihn an. Neue Dateien darin kann nur "
               "der Dienst lesen.",
               "The folder state/ belongs to the service user; install.sh creates it. Only the service can read new "
               "files in it.")),
            S("s2", "frage", ("Ein Geheimnis dabei?", "A secret in it?"),
              ("Passwort, Token, Schlüssel", "password, token, key"),
              ("Passwörter, Tokens und Schlüssel werden versiegelt, bevor sie gespeichert werden. Alles andere geht "
               "direkt zum Schreiben.",
               "Passwords, tokens and keys are sealed before they are stored. Everything else goes straight to "
               "writing."),
              ("ok", "nein", "s5")),
            S("s3", "schritt", ("Schlüssel des Spark holen", "Get the Spark's key"),
              ("state/secret.key", "state/secret.key"),
              ("vault._key liest secret.key. Gibt es ihn nicht, entsteht er einmal (nur lesbar für den Dienst, nie "
               "überschrieben). Danach bleibt er im Speicher des Panels.",
               "vault._key reads secret.key. If there is none, it is made once (readable only for the service, never "
               "overwritten). After that it stays in the panel's memory.")),
            S("s4", "schritt", ("Versiegeln", "Seal"),
              ("enc1: und ein Fernet-Token", "enc1: and a Fernet token"),
              ("vault.seal macht aus dem Wert „enc1:“ und ein Fernet-Token (verschlüsselt und gegen Änderung "
               "geschützt). Ein schon versiegelter Wert bleibt, wie er ist.",
               "vault.seal turns the value into „enc1:“ and a Fernet token (encrypted and protected against "
               "change). A value already sealed stays as it is.")),
            S("s5", "schritt", ("Atomar schreiben", "Write atomically"),
              ("neue Datei nur für den Dienst lesbar", "new file readable for the service only"),
              ("common.write_json schreibt in eine frische Zwischendatei daneben, nie durch einen Link, gibt ihr die "
               "Rechte der alten Datei (eine neue ist nur für den Dienst lesbar) und tauscht sie dann in einem Schritt "
               "aus. Ein Absturz mittendrin lässt die alte Datei ganz.",
               "common.write_json writes into a fresh temporary file next to it, never through a link, gives it the "
               "rights of the old file (a new one is readable for the service only) and then swaps it in one step. "
               "A crash in the middle leaves the old file whole.")),
            S("s6", "schritt", ("Lesen", "Read"),
              ("vault.open_", "vault.open_"),
              ("Ein versiegelter Wert wird mit dem Schlüssel geöffnet. Passt der Schlüssel nicht (Sicherung von einem "
               "anderen Spark), kommt ein leerer Wert zurück und der Zugang muss neu eingetragen werden. Ältere "
               "unversiegelte Werte werden gelesen und beim nächsten Speichern versiegelt.",
               "A sealed value is opened with the key. If the key does not fit (backup from another Spark), an "
               "empty value comes back and the account has to be entered again. Older unsealed values are read and "
               "sealed the next time they are saved.")),
            S("s7", "frage", ("Kommt in die Sicherung?", "Goes into the backup?"),
              ("STATE_FILES oder STATE_LOCAL", "STATE_FILES or STATE_LOCAL"),
              ("Jede Datei in state/ hat genau eine Zeile im Datei-Register dateien.py: mit ihrer Art kommt sie in "
               "jede Sicherung (dateien.STATE_FILES, {dateien.STATE_FILES|anzahl}), sonst steht dort ihr Grund "
               "(dateien.STATE_LOCAL, {dateien.STATE_LOCAL|anzahl}). backup.py nimmt beide Listen von dort. "
               "test_technik findet jeden Namen, den der Code dort schreibt, und verlangt seine Zeile.",
               "Every file in state/ has exactly one line in the file register dateien.py: with its kind it goes "
               "into every backup (dateien.STATE_FILES, {dateien.STATE_FILES|anzahl}), otherwise the line gives its "
               "reason (dateien.STATE_LOCAL, {dateien.STATE_LOCAL|anzahl}). backup.py takes both lists from there. "
               "test_technik finds every name the code writes there and wants its line."),
              ("info", "nein", ("Bleibt auf diesem Gerät: Schlüssel, Sperren, Zähler, Caches",
                                "Stays on this device: keys, locks, counters, caches"))),
            S("s8", "frage", ("Umzugs-Sicherung?", "Move backup?"),
              ("secret.key nur versiegelt mit Passwort", "secret.key only sealed with a password"),
              ("secret.key ist in keiner gewöhnlichen Sicherung. Nur eine Umzugs-Sicherung trägt ihn, versiegelt mit "
               "einem Passwort des Admins (scrypt und Fernet, move-keys.json). Die Anmelde-Schlüssel des Spark sind "
               "in keiner Sicherung.",
               "secret.key is in no ordinary backup. Only a move backup carries it, sealed with a password of the "
               "admin (scrypt and Fernet, move-keys.json). The Spark's login keys are in no backup."),
              ("info", "ja", ("Mit dem Passwort öffnet der neue Spark alle Geheimnisse",
                              "With the password the new Spark opens every secret"))),
            S("s9", "frage", ("Beim Wiederherstellen in Ordnung?", "Fine when restoring?"),
              ("gültig, klein genug, eigener Schlüssel", "valid, small enough, own key"),
              ("_check_state prüft jede Datei der Sicherung: höchstens {backup.MAX_STATE_FILE|mb}, gültiges JSON, "
               "der Push-Schlüssel ein echter EC-Schlüssel. Ein zweiter Schritt des Admins, dessen Geheimnis sich hier "
               "nicht öffnen lässt, wird nicht übernommen; der bisherige bleibt.",
               "_check_state checks every file of the backup: at most {backup.MAX_STATE_FILE|mb}, valid JSON, the push "
               "key a real EC key. An admin second step whose secret cannot be opened here is not taken; the current "
               "one stays."),
              ("stop", "nein", ("Nichts geändert", "Nothing changed"))),
            S("s10", "schritt", ("Einsetzen mit Rückweg", "Put in place with a way back"),
              ("jede Datei einzeln, alter Inhalt gemerkt", "each file on its own, old content kept"),
              ("_swap schreibt jede Datei über eine Zwischendatei (nie durch einen Link) und merkt sich den alten "
               "Inhalt. Geht ein Schritt schief, kommt alles Getauschte zurück.",
               "_swap writes each file through a temporary file (never through a link) and keeps the old content. "
               "If a step fails, everything swapped comes back.")),
            S("s11", "ende", ("Schlüssel neu lesen", "Read the keys again"),
              ("kein alter Schlüssel im Speicher", "no old key in memory"),
              ("_forget_cached lässt die Module, die einen Schlüssel im Speicher halten (vault, push, apns, chats, "
               "verbund, anrufe), ihn neu lesen.",
               "_forget_cached makes the modules that keep a key in memory (vault, push, apns, chats, verbund, "
               "anrufe) read it again.")),
        ],
        "beispiele": [
            (("Telegram-Bot-Token eintragen", "Enter the Telegram bot token"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
             ("Versiegelt gespeichert, kommt in jede Sicherung.", "Stored sealed, goes into every backup.")),
            (("Sperre nach Fehlversuchen", "Lock after failed attempts"), ["s1", "s2", "s2!", "s5", "s6", "s7", "s7!"],
             ("Schlicht gespeichert, bleibt auf diesem Gerät.", "Stored plain, stays on this device.")),
            (("Umzug auf einen neuen Spark", "Move to a new Spark"),
             ["s7", "s8", "s8!", "s9", "s10", "s11"],
             ("Alle Geheimnisse öffnen sich wieder, ohne Neueingabe.", "Every secret opens again, nothing to enter.")),
        ],
        "zahlen": [
            ("{dateien.STATE_FILES|anzahl}", ("Dateien in jeder Sicherung", "files in every backup"), "dateien.STATE_FILES"),
            ("{dateien.STATE_LOCAL|anzahl}", ("Dateien und Ordner, die mit Grund draußen bleiben",
                                              "files and folders that stay out with a reason"), "dateien.STATE_LOCAL"),
            ("{backup.MAX_STATE_FILE|mb}", ("größte Datei beim Wiederherstellen", "largest file when restoring"),
             "backup.MAX_STATE_FILE"),
            ("{backup.MOVE_MIN}", ("Zeichen hat das Umzugs-Passwort mindestens", "characters the move password has at least"),
             "backup.MOVE_MIN"),
        ],
        "einstellen": [
            ("Einstellungen → Sicherung: Sicherung jetzt, Umzugs-Sicherung mit Passwort, Wiederherstellen.",
             "Settings → Backup: back up now, move backup with a password, restore."),
        ],
        "sehen": [
            ("Zustand → Technik: die Tabelle der Speicherorte nennt jede Datei, ob sie in die Sicherung kommt und ob "
             "sie versiegelt ist.",
             "Status → Architecture: the table of storage places names every file, whether it goes into the backup "
             "and whether it is sealed."),
        ],
        "code": [
            ("common.write_json", ("atomar schreiben, Rechte behalten", "write atomically, keep the rights")),
            ("vault._key", ("secret.key holen oder einmal anlegen", "get secret.key or make it once")),
            ("vault.seal", ("versiegeln", "seal")),
            ("vault.open_", ("öffnen, leer bei fremdem Schlüssel", "open, empty with another key")),
            ("dateien.STATE_FILES", ("was in die Sicherung kommt (aus dem Datei-Register)",
                                     "what goes into the backup (from the file register)")),
            ("dateien.STATE_LOCAL", ("was mit Grund draußen bleibt", "what stays out with a reason")),
            ("backup._seal_keys", ("secret.key für den Umzug versiegeln", "seal secret.key for the move")),
            ("backup._check_state", ("Dateien der Sicherung prüfen", "check the files of the backup")),
            ("backup._swap", ("einsetzen mit Rückweg", "put in place with a way back")),
            ("backup._forget_cached", ("Schlüssel neu lesen", "read the keys again")),
        ],
        "tests": ["test_technik", "test_hardening", "test_panel", "test_tempo"],
        "heute": [],
    },

    # ------------------------------------------------------------------ users/ID/
    "users": {
        "stand": "d2a684d847",
        "bezug": {
            "profiles.delete_user": ["s11"], "vault.seal": ["s3"], "speakers._store": ["s3", "s4"],
            "speicher._key": ["s8"], "speicher.local_files": ["s7"], "speicher.seal_file": ["s8"],
            "speicher.copy_once": ["s7", "s8"], "backup._add_dir": ["s10"], "regeln": ["s5", "s7"],
            "regel:Zugänge, Schlüssel, Stimmabdruck": ["s3"],
        },
        "kurz": ("Jedes Profil hat seinen eigenen Ordner users/ID/: Gespräche, Gedächtnis, Aufgaben, Dokumente, "
                 "Einstellungen, Zugänge und den Stimmabdruck. Welcher Ordner gilt, kommt nur aus der Anmeldung. "
                 "Auf Wunsch geht eine verschlüsselte Kopie davon auf einen eigenen Speicher.",
                 "Every profile has its own folder users/ID/: conversations, memory, tasks, documents, settings, "
                 "accounts and the voiceprint. Which folder applies comes only from the login. If wanted, an "
                 "encrypted copy of it goes to an own storage."),
        "warum": ("Was einer Person gehört, darf keine andere sehen, auch nicht über das Sprachmodell. Passwörter "
                  "und der Stimmabdruck sollen auch in einer Kopie der Dateien nicht lesbar sein.",
                  "What belongs to one person must not be seen by another, not even through the language model. "
                  "Passwords and the voiceprint should not be readable even in a copy of the files."),
        "ablauf": [
            S("s1", "start", ("Anfrage mit Profil", "A request with a profile"),
              ("Cookie oder Geräteschlüssel", "cookie or device key"),
              ("profiles.current findet das Profil aus dem signierten Anmelde-Cookie oder dem Geräteschlüssel. Was "
               "das Sprachmodell sagt, wählt nie ein Profil.",
               "profiles.current finds the profile from the signed login cookie or the device key. What the language "
               "model says never picks a profile.")),
            S("s2", "schritt", ("Pfad im eigenen Ordner", "Path in its own folder"),
              ("profiles._path(ID, Datei)", "profiles._path(ID, file)"),
              ("Jede Datei liegt unter users/ID/ mit einem festen Namen aus dem Code. Die ID kommt aus Schritt 1, "
               "nie aus einem Text.",
               "Every file lies under users/ID/ with a fixed name from the code. The ID comes from step 1, never "
               "from a text.")),
            S("s3", "frage", ("Ein Geheimnis dabei?", "A secret in it?"),
              ("Passwort, Token, Stimmabdruck", "password, token, voiceprint"),
              ("Passwörter von Mail, Kalender und Speicherorten, Tokens von Home Assistant und MCP und der Schlüssel "
               "des eigenen Speichers werden mit dem Schlüssel des Spark versiegelt. Der Stimmabdruck (voice.json) ist "
               "biometrisch und wird ganz versiegelt; eine ältere offene Datei wird beim ersten Lesen versiegelt.",
               "Passwords of mail, calendar and storage places, tokens of Home Assistant and MCP and the own "
               "storage key are sealed with the Spark's key. The voiceprint (voice.json) is biometric and is sealed "
               "whole; an older open file is sealed the first time it is read."),
              ("info", "ja", ("Versiegelt mit secret.key", "Sealed with secret.key"))),
            S("s4", "schritt", ("Schreiben nur für den Dienst", "Write for the service only"),
              ("profiles._write", "profiles._write"),
              ("profiles._write legt den Ordner so an, dass nur der Dienst hineinsieht, schreibt eine Zwischendatei, "
               "die nur der Dienst lesen kann, und tauscht sie in einem Schritt aus.",
               "profiles._write creates the folder so that only the service looks into it, writes a temporary file "
               "only the service can read and swaps it in one step.")),
            S("s5", "schritt", ("Jede Datei einsortiert", "Every file sorted"),
              ("speicher.AREAS oder speicher.LOCAL", "speicher.AREAS or speicher.LOCAL"),
              ("Jeder Dateiname hat genau eine Zeile im Datei-Register dateien.py: mit einem Bereich "
               "(dateien.AREAS, darf auf den eigenen Speicher) oder mit seiner Art (dateien.LOCAL, bleibt auf dem "
               "Spark: Schlüssel, Zugänge, Einstellungen, Stimmabdruck, Warteschlangen). speicher.py nimmt beide "
               "Listen von dort. test_technik prüft jeden Namen, den der Code schreibt.",
               "Every file name has exactly one line in the file register dateien.py: with an area (dateien.AREAS, "
               "may go to the own storage) or with its kind (dateien.LOCAL, stays on the Spark: keys, accounts, "
               "settings, voiceprint, queues). speicher.py takes both lists from there. test_technik checks every "
               "name the code writes.")),
            S("s6", "frage", ("Eigener Speicher eingerichtet?", "Own storage set up?"),
              ("Admin-Schalter, Profil, Ziel mit Bereichen", "admin switch, profile, target with areas"),
              ("Nur wenn der Admin den eigenen Speicher freigegeben hat und das Profil ein Ziel mit mindestens einem "
               "Bereich hat (höchstens {speicher.MAX_TARGETS} Ziele).",
               "Only when the admin allowed the own storage and the profile has a target with at least one area (at "
               "most {speicher.MAX_TARGETS} targets)."),
              ("ok", "nein", "s10")),
            S("s7", "schritt", ("Nur Geändertes der gewählten Bereiche", "Only changes of the chosen areas"),
              ("alle {speicher.EVERY|min} Minuten", "every {speicher.EVERY|min} minutes"),
              ("local_files nimmt nur Dateien der gewählten Bereiche: echte Dateien, keine Links, höchstens "
               "{speicher.MAX_FILES} Stück. copy_once schickt nur, was sich seit dem letzten Lauf geändert hat, "
               "höchstens {speicher.RUN_BYTES|mb} pro Lauf; der nächste Lauf macht weiter.",
               "local_files takes only files of the chosen areas: real files, no links, at most {speicher.MAX_FILES}. "
               "copy_once sends only what changed since the last run, at most {speicher.RUN_BYTES|mb} per run; the "
               "next run goes on.")),
            S("s8", "schritt", ("Verschlüsselt, Namen zufällig", "Encrypted, names random"),
              ("AES-256-GCM in Stücken", "AES-256-GCM in pieces"),
              ("seal_file verschlüsselt jede Datei in nummerierten Stücken mit einem eigenen Schlüssel je Objekt "
               "(abgeleitet aus dem Speicher-Schlüssel des Profils und dem Objektnamen). Die Namen auf dem Ziel sind "
               "zufällig; das Ziel sieht nur Rauschen.",
               "seal_file encrypts every file in numbered pieces with a key of its own per object (derived from the "
               "profile's storage key and the object's name). The names on the target are random; the target sees "
               "only noise.")),
            S("s9", "schritt", ("Gelöschtes wartet im Papierkorb", "Deleted waits in the bin"),
              ("{speicher.TRASH_DAYS} Tage", "{speicher.TRASH_DAYS} days"),
              ("Ein gelöschtes oder ersetztes Objekt bleibt {speicher.TRASH_DAYS} Tage auf dem Ziel. Ist das Ziel "
               "nicht erreichbar, ändert sich auf dem Spark nichts; der Besitzer hört nach "
               "{speicher.NOTE_AFTER|min} Minuten einmal davon.",
               "A deleted or replaced object stays {speicher.TRASH_DAYS} days on the target. If the target cannot "
               "be reached, nothing changes on the Spark; the owner hears of it once after {speicher.NOTE_AFTER|min} "
               "minutes."),
              ("stop", ("Ziel weg", "target gone"), ("Später noch einmal", "Again later"))),
            S("s10", "schritt", ("In der Sicherung", "In the backup"),
              ("ohne Anmelde-Schlüssel und Nachrichten", "without login key and messages"),
              ("Die tägliche Sicherung nimmt users/ ganz mit, außer users/secret (signiert die Anmeldungen) und den "
               "Nachrichten zwischen Profilen. SQLite-Dateien werden als stimmige Kopie gepackt.",
               "The daily backup takes users/ whole, except users/secret (signs the logins) and the messages "
               "between profiles. SQLite files are packed as a consistent copy.")),
            S("s11", "frage", ("Profil gelöscht?", "Profile deleted?"),
              ("nur der Admin", "only the admin"),
              ("delete_user nimmt das Profil und seine Geräte aus profiles.json und löscht den Ordner, aber nur wenn "
               "die ID genau die Form einer Profil-ID hat.",
               "delete_user takes the profile and its devices out of profiles.json and deletes the folder, but only "
               "when the ID has exactly the shape of a profile ID."),
              ("stop", "ja", ("Ordner gelöscht", "Folder deleted"))),
            S("s12", "ende", ("Nur für dieses Profil", "Only for this profile"),
              ("kein Profil sieht einen anderen Ordner", "no profile sees another folder"),
              ("Jede Funktion liest nur den Ordner des angemeldeten Profils. Gäste haben keinen Ordner.",
               "Every function reads only the folder of the signed-in profile. Guests have no folder.")),
        ],
        "beispiele": [
            (("Gedächtnis-Eintrag, kein eigener Speicher", "Memory entry, no own storage"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s10", "s11", "s12"],
             ("Liegt im eigenen Ordner und in der Sicherung.", "Lies in its own folder and in the backup.")),
            (("Mail-Passwort eintragen", "Enter a mail password"),
             ["s1", "s2", "s3", "s3!", "s4", "s5", "s6", "s6!", "s10", "s11", "s12"],
             ("Versiegelt, bleibt auf dem Spark (Zugang).", "Sealed, stays on the Spark (account).")),
            (("Dokument mit eigenem Speicher", "Document with own storage"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Verschlüsselte Kopie auf dem Ziel.", "Encrypted copy on the target.")),
        ],
        "regeln": [
            [("Bereich", "Area"), ("Dateien", "Files"), ("Eigener Speicher", "Own storage")],
            [("Gespräche", "Conversations"), "convos.json, toollog.json, room-history.json", "✓"],
            [("Gedächtnis", "Memory"), "memory.json, learned.json, zuordnungen.json", "✓"],
            [("Aufgaben und Erinnerungen", "Tasks and reminders"), "tasks.json, reminders.json", "✓"],
            [("Dokumente", "Documents"), "wissen.db, docs/files/, suchpruefung.json", "✓"],
            [("Erstellte Dokumente", "Created documents"), "erstellt/", "✓"],
            [("Gemalte Bilder", "Painted pictures"), "bilder/", "✓"],
            [("Zugänge, Schlüssel, Stimmabdruck", "Accounts, keys, voiceprint"), ("dateien.LOCAL", "dateien.LOCAL"), "✕"],
        ],
        "zahlen": [
            ("{speicher.MAX_TARGETS}", ("Ziele pro Profil höchstens", "targets per profile at most"), "speicher.MAX_TARGETS"),
            ("{speicher.EVERY|min}", ("Minuten zwischen zwei Läufen", "minutes between two runs"), "speicher.EVERY"),
            ("{speicher.RUN_BYTES|mb}", ("höchstens pro Lauf", "at most per run"), "speicher.RUN_BYTES"),
            ("{speicher.TRASH_DAYS}", ("Tage im Papierkorb des Ziels", "days in the target's bin"), "speicher.TRASH_DAYS"),
            ("{speicher.MAX_FILES}", ("Dateien pro Kopie höchstens", "files per copy at most"), "speicher.MAX_FILES"),
        ],
        "einstellen": [
            ("Ich → Speicher: eigene Ziele (NAS, WebDAV, SFTP, SMB) und welche Bereiche dorthin gehen.",
             "Me → Storage: own targets (NAS, WebDAV, SFTP, SMB) and which areas go there."),
        ],
        "sehen": [
            ("Ich → Speicher: die eigenen Ziele mit Zustand und den letzten Läufen.",
             "Me → Storage: the own targets with their state and the last runs."),
            ("Zustand → Technik: die Tabelle der Speicherorte nennt jede Datei eines Profils, ob sie mitkopiert wird "
             "und ob sie versiegelt ist.",
             "Status → Architecture: the table of storage places names every file of a profile, whether it is "
             "copied and whether it is sealed."),
        ],
        "code": [
            ("profiles.current", ("das Profil aus Cookie oder Geräteschlüssel", "the profile from cookie or device key")),
            ("profiles._path", ("Pfad im Ordner des Profils", "path in the profile's folder")),
            ("profiles._write", ("schreiben nur für den Dienst", "write for the service only")),
            ("profiles.delete_user", ("Profil und Ordner löschen", "delete profile and folder")),
            ("vault.seal", ("versiegeln", "seal")),
            ("speakers._store", ("Stimmabdruck versiegelt", "voiceprint sealed")),
            ("dateien.AREAS", ("was auf den eigenen Speicher darf (aus dem Datei-Register)",
                               "what may go to the own storage (from the file register)")),
            ("speicher._key", ("Speicher-Schlüssel des Profils, versiegelt", "the profile's storage key, sealed")),
            ("speicher.local_files", ("nur die Liste, keine Links", "only the list, no links")),
            ("speicher.seal_file", ("AES-256-GCM in Stücken", "AES-256-GCM in pieces")),
            ("speicher.copy_once", ("ein Lauf der Kopie", "one run of the copy")),
            ("backup._add_dir", ("users/ in die Sicherung", "users/ into the backup")),
        ],
        "tests": ["test_speicher", "test_technik", "test_stimmabdruck", "test_hardening"],
        "heute": [],
    },

    # ------------------------------------------------------------------ voices/, backups/
    "ablage": {
        "stand": "c6f0cd6612",
        "bezug": {
            "backup.MAX_UPLOAD": ["s12"], "admin.add_clone_voice": ["s1", "s2", "s4"],
            "admin.import_clone_voices": ["s6"], "tts_proxy.apply_clone": ["s5"], "panel.stability": ["s7"],
            "backup._add_dir": ["s8"], "backup._prune": ["s10"], "system.backup_ticket": ["s11"],
            "backup._check": ["s12"], "backup.restore": ["s12"], "regeln": ["s8"], "regel:secret.key": ["s9"],
        },
        "kurz": ("In voices/ liegen die geklonten Stimmen (WAV und Text), in backups/ die Sicherungen des Spark. Eine "
                 "Sicherung entsteht einmal am Tag von selbst, vor jedem Update und auf Knopfdruck; die ältesten "
                 "fallen weg.",
                 "voices/ holds the cloned voices (WAV and text), backups/ the Spark's backups. A backup is made once "
                 "a day by itself, before every update and on request; the oldest ones go."),
        "warum": ("Eine Stimme oder ein ganzer Spark soll sich nach einem Fehler, einem Update oder einem Umzug "
                  "zurückholen lassen. Eine Sicherung enthält alles über alle Profile, deshalb ist sie nur für den "
                  "Dienst lesbar und lässt sich nur mit Code herunterladen.",
                  "A voice or a whole Spark should come back after a mistake, an update or a move. A backup holds "
                  "everything about every profile, so only the service can read it and it downloads only with a code."),
        "ablauf": [
            S("s1", "start", ("Admin nimmt eine Stimme auf", "The admin records a voice"),
              ("POST /api/clone-voices", "POST /api/clone-voices"),
              ("Unter Einstellungen → Stimmen lädt der Admin eine Aufnahme hoch, mit Namen und am besten mit dem "
               "gesprochenen Text.",
               "Under Settings → Voices the admin uploads a recording, with a name and best with the spoken text.")),
            S("s2", "frage", ("Name erlaubt?", "Name allowed?"),
              ("Buchstaben, Ziffern, _ und -", "letters, digits, _ and -"),
              ("Der Name wird zum Dateinamen; deshalb nur Buchstaben, Ziffern, Unterstrich und Bindestrich. Die "
               "Aufnahme darf höchstens sechzig MB groß sein.",
               "The name becomes the file name; so only letters, digits, underscore and hyphen. The recording may be "
               "at most sixty MB."),
              ("stop", "nein", ("Abgelehnt (400)", "Refused (400)"))),
            S("s3", "frage", ("Kein WAV?", "Not a WAV?"),
              ("mp3, m4a, webm", "mp3, m4a, webm"),
              ("Die Engine erwartet WAV. Alles andere wandelt ffmpeg in Mono-WAV um, höchstens zwei Minuten lang.",
               "The engine expects WAV. ffmpeg turns anything else into mono WAV, at most two minutes long."),
              ("info", "ja", ("ffmpeg wandelt um", "ffmpeg converts"))),
            S("s4", "schritt", ("Ablegen", "Store"),
              ("voices/Name.wav und Name.txt", "voices/name.wav and name.txt"),
              ("Die Aufnahme wird voices/Name.wav, der Text voices/Name.txt. Ohne Text nutzt die Engine nur die "
               "Klangfarbe.",
               "The recording becomes voices/name.wav, the text voices/name.txt. Without text the engine uses only "
               "the timbre.")),
            S("s5", "schritt", ("Mit der Stimme sprechen", "Speak with the voice"),
              ("nur mit einem Base-Modell", "only with a Base model"),
              ("Ist ein Base-Modell eingestellt, liest der TTS-Dienst die Stimme als eingebettete Aufnahme "
               "(apply_clone) und merkt sie sich, bis sich die Datei ändert.",
               "When a Base model is set, the TTS service reads the voice as an embedded recording (apply_clone) and "
               "keeps it until the file changes.")),
            S("s6", "schritt", ("Stimmen als ZIP", "Voices as a ZIP"),
              ("Export und Import", "export and import"),
              ("Ein Import nimmt nur flache Name.wav und Name.txt, prüft die Größe jeder Datei, bevor etwas entpackt "
               "wird, und benennt bei Gleichstand um, überschreibt oder überspringt, wie gewählt.",
               "An import takes only flat name.wav and name.txt, checks the size of each file before anything is "
               "unpacked and renames, overwrites or skips on a clash, as chosen.")),
            S("s7", "schritt", ("Einmal am Tag", "Once a day"),
              ("wartet, bis gerade niemand spricht", "waits until nobody is speaking"),
              ("Das Panel schaut jede Stunde, ob die letzte Sicherung älter als ein Tag ist. Dann packt es in einer "
               "Pause (vorrang.in_thread), mit niedriger Priorität. Dazu kommen Sicherungen vor jedem Update, "
               "Zurücksetzen und Wiederherstellen.",
               "The panel looks every hour whether the last backup is older than a day. Then it packs in a pause "
               "(vorrang.in_thread), with low priority. Backups before every update, rollback and restore come on "
               "top.")),
            S("s8", "schritt", ("Packen", "Pack"),
              ("ein .tar.gz nur für den Dienst", "a .tar.gz for the service only"),
              ("backup.create schreibt in backups/ (nur für den Dienst) erst eine .part-Datei, dann den fertigen "
               "Namen: backup.json, users/ ohne users/secret und Nachrichten, voices/, config.json, das "
               "Panel-Passwort und die Dateien aus STATE_FILES. SQLite-Dateien kommen als stimmige Kopie hinein.",
               "backup.create writes into backups/ (for the service only) first a .part file, then the final name: "
               "backup.json, users/ without users/secret and messages, voices/, config.json, the panel password and "
               "the files of STATE_FILES. SQLite files go in as a consistent copy.")),
            S("s9", "frage", ("Umzugs-Sicherung?", "Move backup?"),
              ("mit Passwort des Admins", "with the admin's password"),
              ("Mit einem Passwort ({backup.MOVE_MIN} bis {backup.MOVE_MAX} Zeichen) trägt die Sicherung auch "
               "secret.key, versiegelt mit diesem Passwort. Nur der Haupt-Admin mit frischem Code kann sie anlegen.",
               "With a password ({backup.MOVE_MIN} to {backup.MOVE_MAX} characters) the backup also carries "
               "secret.key, sealed with that password. Only the main admin with a fresh code can make one."),
              ("info", "ja", ("secret.key reist versiegelt mit", "secret.key travels along sealed"))),
            S("s10", "schritt", ("Alte aufräumen", "Remove old ones"),
              ("{backup.KEEP} täglich, {backup.KEEP_EVENT} Ereignisse", "{backup.KEEP} daily, {backup.KEEP_EVENT} events"),
              ("_prune behält die neuesten {backup.KEEP} täglichen und manuellen Sicherungen und die neuesten "
               "{backup.KEEP_EVENT} anderen (Update, Wiederherstellen, Umzug). So verdrängen ein paar Updates nie "
               "die täglichen.",
               "_prune keeps the newest {backup.KEEP} daily and manual backups and the newest {backup.KEEP_EVENT} "
               "others (update, restore, move). So a few updates never push the daily ones out.")),
            S("s11", "schritt", ("Herunterladen nur mit Code", "Download only with a code"),
              ("Einmal-Ticket", "one-time ticket"),
              ("Eine Sicherung enthält alle Profile. Der Browser holt mit dem Code ein Ticket, das eine Minute gilt "
               "und einmal benutzbar ist, und lädt damit die Datei.",
               "A backup holds every profile. With the code the browser gets a ticket that is valid for a minute "
               "and usable once, and downloads the file with it.")),
            S("s12", "ende", ("Wiederherstellen", "Restore"),
              ("erst prüfen, dann tauschen", "check first, then swap"),
              ("restore entpackt nur bekannte Pfade, höchstens {backup.MAX_UNPACKED|mb} und nur bei genug freiem "
               "Platz, prüft die Einstellungen wie die Einstellungsseite, legt eine Sicherung des jetzigen Stands an "
               "und tauscht dann users/, voices/, Einstellungen und state-Dateien, mit Rückweg bei einem Fehler.",
               "restore unpacks only known paths, at most {backup.MAX_UNPACKED|mb} and only with enough free space, "
               "checks the settings like the settings page, makes a backup of the current state and then swaps "
               "users/, voices/, settings and state files, with a way back on an error."),
              ("stop", ("Prüfung schlägt fehl", "check fails"), ("Nichts geändert", "Nothing changed"))),
        ],
        "beispiele": [
            (("Stimme aus einer m4a-Datei", "Voice from an m4a file"), ["s1", "s2", "s3", "s3!", "s4", "s5"],
             ("Als WAV abgelegt, das Base-Modell spricht damit.", "Stored as WAV, the Base model speaks with it.")),
            (("Tägliche Sicherung", "Daily backup"), ["s7", "s8", "s9", "s10"],
             ("Neue Sicherung, die älteste tägliche fällt weg.", "New backup, the oldest daily one goes.")),
            (("Umzug auf einen neuen Spark", "Move to a new Spark"), ["s8", "s9", "s9!", "s10", "s11", "s12"],
             ("Alles kommt mit, auch die Geheimnisse.", "Everything comes along, the secrets too.")),
            (("Kaputte Datei hochgeladen", "Broken file uploaded"), ["s12", "s12!"],
             ("Abgelehnt, am Spark ändert sich nichts.", "Refused, nothing changes on the Spark.")),
        ],
        "regeln": [
            [("Teil", "Part"), ("In der Sicherung", "In the backup"), ("Warum", "Why")],
            ["users/", "✓", ("ohne users/secret und Nachrichten zwischen Profilen", "without users/secret and messages between profiles")],
            ["voices/", "✓", ("geklonte Stimmen", "cloned voices")],
            ["config.json", "✓", ("Geheimnisse darin versiegelt", "secrets in it sealed")],
            ["state/", ("nur STATE_FILES und panel-password", "only STATE_FILES and panel-password"), ("der Rest gilt nur hier", "the rest only applies here")],
            ["secret.key", ("nur Umzugs-Sicherung", "move backup only"), ("versiegelt mit Passwort", "sealed with a password")],
        ],
        "zahlen": [
            ("{backup.KEEP}", ("tägliche und manuelle Sicherungen bleiben", "daily and manual backups kept"), "backup.KEEP"),
            ("{backup.KEEP_EVENT}", ("Ereignis-Sicherungen bleiben", "event backups kept"), "backup.KEEP_EVENT"),
            ("{backup.MAX_UPLOAD|mb}", ("größte hochgeladene Sicherung", "largest uploaded backup"), "backup.MAX_UPLOAD"),
            ("{backup.MAX_UNPACKED|mb}", ("entpackt höchstens", "unpacked at most"), "backup.MAX_UNPACKED"),
            ("{backup.MOVE_MIN}–{backup.MOVE_MAX}", ("Zeichen des Umzugs-Passworts", "characters of the move password"),
             "backup.MOVE_MIN"),
        ],
        "einstellen": [
            ("Einstellungen → Stimmen: eigene Stimmen aufnehmen, anhören, als ZIP sichern und einspielen.",
             "Settings → Voices: record own voices, play them, save and load them as a ZIP."),
            ("Einstellungen → Sicherung: Sicherung jetzt, Umzugs-Sicherung, herunterladen, wiederherstellen und die "
             "verschlüsselte Kopie nach außen.",
             "Settings → Backup: back up now, move backup, download, restore and the encrypted copy to the outside."),
        ],
        "sehen": [
            ("Einstellungen → Sicherung: die Liste der Sicherungen mit Zeit, Größe und Anlass.",
             "Settings → Backup: the list of backups with time, size and reason."),
            ("Zustand → Logs → Diagnose, Bereich Speicher: jede tägliche Sicherung und jeder Fehler.",
             "Status → Logs → Diagnosis, area storage: every daily backup and every failure."),
        ],
        "code": [
            ("admin.add_clone_voice", ("Stimme prüfen, umwandeln, ablegen", "check, convert, store a voice")),
            ("admin.import_clone_voices", ("Stimmen aus einem ZIP", "voices from a ZIP")),
            ("tts_proxy.apply_clone", ("mit der Stimme sprechen", "speak with the voice")),
            ("panel.stability", ("tägliche Sicherung in einer Pause", "daily backup in a pause")),
            ("backup.create", ("eine Sicherung packen", "pack a backup")),
            ("backup._add_dir", ("Ordner ohne Anmelde-Schlüssel", "folders without login key")),
            ("backup._prune", ("alte aufräumen", "remove old ones")),
            ("system.backup_ticket", ("Einmal-Ticket zum Herunterladen", "one-time ticket to download")),
            ("backup._check", ("nur bekannte Pfade, Größe, Platz", "only known paths, size, space")),
            ("backup.restore", ("prüfen, sichern, tauschen", "check, back up, swap")),
        ],
        "tests": ["test_panel", "test_hardening", "test_offsite"],
        "heute": [],
    },

    # ------------------------------------------------------------------ journald
    "journal": {
        "stand": "2d9c2f502e",
        "bezug": {
            "logfilter.logfilter": ["s6"], "logfilter.read_journal": ["s8"], "logfilter.redact": ["s9"],
            "logfilter.parse": ["s10"], "logfilter.summary": ["s11"], "logfilter.detail": ["s12"],
            "common.JOURNAL_NAMESPACE": ["s5"], "common.journal": ["s1"], "common.quiet_access_log": ["s4"],
        },
        "kurz": ("Alle Dienste des Spark schreiben ihre Zeilen in einen eigenen Bereich des Systemjournals "
                 "(Namespace speech-spark), mit eigener Grenze für Platz und Alter. Das Panel liest diese Zeilen nur "
                 "für den Admin, schwärzt Geheimnisse und ordnet sie nach festen Wörtern.",
                 "All services of the Spark write their lines into their own part of the system journal (namespace "
                 "speech-spark), with their own limit for space and age. The panel reads these lines only for the "
                 "admin, blacks out secrets and sorts them by fixed words."),
        "warum": ("Logs sollen zeigen, was passiert, ohne zu verraten, was jemand gefragt hat. Und ein gesprächiger "
                  "Dienst darf weder die Platte füllen noch die anderen Logs des Systems verdrängen.",
                  "Logs should show what happens without revealing what someone asked. And a chatty service must "
                  "neither fill the disk nor push out the system's other logs."),
        "ablauf": [
            S("s1", "start", ("Ein Dienst schreibt eine Zeile", "A service writes a line"),
              ("print auf die Standardausgabe", "print to standard output"),
              ("Panel, ASR, TTS, Engines und Wächter schreiben mit print. systemd gibt die Zeile an das Journal; "
               "jede Einheit hat LogNamespace=speech-spark.",
               "Panel, ASR, TTS, engines and watchers write with print. systemd hands the line to the journal; every "
               "unit has LogNamespace=speech-spark.")),
            S("s2", "schritt", ("Feste Wörter und Zahlen", "Fixed words and numbers"),
              ("nie Fragen, Antworten oder Namen", "never questions, answers or names"),
              ("Jede Zeile des Panels beginnt mit einem Wort aus logfilter.AREAS ({logfilter.AREAS|anzahl} Bereiche) "
               "und trägt nur feste Wörter und Zahlen. Ein Profil steht dort nur über profiles.log_name: sein Name nur "
               "mit seiner Zustimmung, sonst „Profil“ und das Ende der ID. test_log_luecken verlangt für jede Aktion "
               "eine Zeile je Ergebnis.",
               "Every line of the panel starts with a word from logfilter.AREAS ({logfilter.AREAS|anzahl} areas) and "
               "carries only fixed words and numbers. A profile appears there only through profiles.log_name: its "
               "name only with its consent, else „Profil“ and the end of its ID. test_log_luecken wants a line for "
               "every outcome of every action.")),
            S("s3", "frage", ("Ausführlich an?", "Detail on?"),
              ("nur Admin, schaltet sich selbst aus", "admin only, switches itself off"),
              ("Für einige Bereiche kann der Admin zusätzliche Zeilen einschalten, höchstens "
               "{logfilter.VERBOSE_MINUTES.2} Minuten. Auch sie tragen nur Zahlen und Entscheidungen; ein Neustart "
               "schaltet sie aus.",
               "For some areas the admin can switch on extra lines, at most {logfilter.VERBOSE_MINUTES.2} minutes. "
               "They too carry only numbers and decisions; a restart switches them off."),
              ("info", "ja", ("Zusätzliche Zeilen mit Zahlen", "Extra lines with numbers"))),
            S("s4", "schritt", ("Abfragen still", "Polls quiet"),
              ("quiet_access_log", "quiet_access_log"),
              ("Erfolgreiche Statusabfragen, die das Panel alle paar Sekunden stellt, schreiben keine Zeile.",
               "Successful status polls the panel makes every few seconds write no line.")),
            S("s5", "schritt", ("Eigener Bereich mit Grenze", "Own part with a limit"),
              ("journald@speech-spark.conf", "journald@speech-spark.conf"),
              ("install.sh schreibt die Grenze für Platz und Alter aus logs.max_mb und logs.keep_days. Ältere Zeilen "
               "löscht journald selbst. Eine Änderung wirkt nach dem nächsten Update oder install.sh.",
               "install.sh writes the limit for space and age from logs.max_mb and logs.keep_days. journald deletes "
               "older lines itself. A change applies after the next update or install.sh.")),
            S("s6", "schritt", ("Admin öffnet die Diagnose", "The admin opens the diagnosis"),
              ("GET /api/logfilter", "GET /api/logfilter"),
              ("Nur der Admin, höchstens {guard.RATE.logs.1} Abrufe pro Minute.",
               "Admin only, at most {guard.RATE.logs.1} calls per minute.")),
            S("s7", "frage", ("Filter aus der festen Liste?", "Filter from the fixed list?"),
              ("Bereich, Zeit, Zeilen", "area, time, lines"),
              ("Bereiche, Zeitfenster (bis {logfilter.MINUTES.4|min} Stunden) und Zeilenzahl (bis "
               "{logfilter.LINES.3}) kommen nur aus festen Listen. Nichts, was der Browser schickt, erreicht eine "
               "Shell.",
               "Areas, time window (up to {logfilter.MINUTES.4|min} hours) and number of lines (up to "
               "{logfilter.LINES.3}) come only from fixed lists. Nothing the browser sends reaches a shell."),
              ("stop", "nein", ("Abgelehnt (400)", "Refused (400)"))),
            S("s8", "schritt", ("Journal lesen", "Read the journal"),
              ("erst der eigene Bereich, dann das System", "first the own part, then the system"),
              ("read_journal fragt journalctl mit dem Namespace, bei alten Installationen ohne ihn das System-Journal. "
               "Höchstens {logfilter.READ_MAX} Zeilen und {logfilter.OUT_MAX|mb} Text.",
               "read_journal asks journalctl with the namespace, for old installs without it the system journal. At "
               "most {logfilter.READ_MAX} lines and {logfilter.OUT_MAX|mb} of text.")),
            S("s9", "schritt", ("Geheimnisse schwärzen", "Black out secrets"),
              ("Bot-Tokens, Schlüssel, Passwörter", "bot tokens, keys, passwords"),
              ("redact ersetzt Telegram-Tokens, Bearer-Schlüssel, key=, token=, password= und Anmeldungen in "
               "Adressen durch Sternchen, bevor eine Zeile das Panel verlässt.",
               "redact replaces Telegram tokens, Bearer keys, key=, token=, password= and logins in addresses with "
               "asterisks before a line leaves the panel.")),
            S("s10", "schritt", ("Bereich und Stufe nach Regeln", "Area and level by rules"),
              ("kein Modell", "no model"),
              ("parse ordnet jede Zeile nach ihrem ersten Wort einem Bereich zu. Fehler und Warnungen erkennt es an "
               "festen Wörtern; bei Web-Anfragen zählt nur der Statuscode, bei Update-Zeilen nie der Betreff.",
               "parse sorts every line into an area by its first word. It spots errors and warnings by fixed words; "
               "for web requests only the status code counts, for update lines never the subject.")),
            S("s11", "schritt", ("Zählen und Hinweis", "Count and hint"),
              ("{logfilter.BUCKETS} Abschnitte je Bereich", "{logfilter.BUCKETS} slices per area"),
              ("summary zählt je Bereich und Stufe, zeichnet einen kleinen Verlauf und hängt an den neuesten Fehler "
               "einen festen Hinweis mit Weg.",
               "summary counts per area and level, draws a small history and adds a fixed hint with a way to the "
               "newest error.")),
            S("s12", "ende", ("Zeilen ans Panel", "Lines to the panel"),
              ("die neuesten passenden", "the newest matching ones"),
              ("Das Panel zeigt die neuesten passenden Zeilen. Sie liegen nur im Journal dieses Spark, nie in einer "
               "Sicherung.",
               "The panel shows the newest matching lines. They lie only in this Spark's journal, never in a "
               "backup.")),
        ],
        "beispiele": [
            (("Fehler der Websuche ansehen", "Look at a web search error"),
             ["s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Zeile im Bereich Suche mit festem Hinweis.", "Line in the search area with a fixed hint.")),
            (("Zeitfenster aus dem Browser verändert", "Time window changed in the browser"), ["s6", "s7", "s7!"],
             ("Abgelehnt, journalctl wird nicht gefragt.", "Refused, journalctl is not asked.")),
            (("Speicher-Lauf eines Profils", "Storage run of a profile"), ["s1", "s2", "s3", "s4", "s5"],
             ("Zeile „speicher: lauf …“ mit Zahlen, das Profil nur als Kürzel.",
              "Line „speicher: lauf …“ with numbers, the profile only as a short form.")),
        ],
        "zahlen": [
            ("{logfilter.AREAS|anzahl}", ("Bereiche der Diagnose", "areas of the diagnosis"), "logfilter.AREAS"),
            ("{logfilter.READ_MAX}", ("Zeilen pro Abruf höchstens gelesen", "lines read per call at most"), "logfilter.READ_MAX"),
            ("{logfilter.OUT_MAX|mb}", ("Journal-Text pro Abruf höchstens", "journal text per call at most"), "logfilter.OUT_MAX"),
            ("{logfilter.LINES.3}", ("Zeilen höchstens angezeigt", "lines shown at most"), "logfilter.LINES"),
            ("{logfilter.VERBOSE_MINUTES.2}", ("Minuten „Ausführlich“ höchstens", "minutes of „detail“ at most"),
             "logfilter.VERBOSE_MINUTES"),
        ],
        "einstellen": [
            ("In den Einstellungen unter Betrieb, Abschnitt Logs: wie viel Platz das Journal höchstens nimmt und wie "
             "lange es Zeilen aufbewahrt (wirkt nach dem nächsten Update).",
             "In the settings under Operation, section Logs: how much space the journal takes at most and how long it "
             "keeps lines (applies after the next update)."),
        ],
        "sehen": [
            ("Zustand → Logs → Diagnose: Filter nach Bereich, Zähler, kleiner Verlauf und der neueste Fehler mit "
             "Hinweis.",
             "Status → Logs → Diagnosis: filter by area, counters, small history and the newest error with a hint."),
            ("Zustand → Logs: die letzten Zeilen jedes Dienstes.", "Status → Logs: the last lines of each service."),
        ],
        "code": [
            ("logfilter.AREAS", ("die festen Bereiche", "the fixed areas")),
            ("logfilter.logfilter", ("der Abruf: nur feste Listen", "the call: fixed lists only")),
            ("logfilter.read_journal", ("Namespace zuerst, Grenzen", "namespace first, limits")),
            ("logfilter.redact", ("Geheimnisse schwärzen", "black out secrets")),
            ("logfilter.parse", ("Bereich und Stufe", "area and level")),
            ("logfilter.summary", ("Zähler, Verlauf, Hinweis", "counts, history, hint")),
            ("logfilter.detail", ("Ausführlich, nur Zahlen", "detail, numbers only")),
            ("common.JOURNAL_NAMESPACE", ("der eigene Bereich", "the own part")),
            ("common.journal", ("letzte Zeilen eines Dienstes", "last lines of a service")),
            ("common.quiet_access_log", ("Statusabfragen still", "status polls quiet")),
            ("profiles.log_name", ("Profil nur mit Zustimmung beim Namen", "profile by name only with consent")),
        ],
        "tests": ["test_logfilter", "test_log_luecken"],
        "heute": [],
    },
}
