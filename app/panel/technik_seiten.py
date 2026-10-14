"""Zustand → Technik, Knoten-Seiten: the texts of every box's page (the engine, checks and fingerprint are in
technik_knoten.py, plan plaene/knoten-seiten.md). Texts are (German, English); {mod.NAME|format} and {@auto} are filled
in from the code, never typed. When the way a box works changes, its page changes in the same commit and its "stand"
gets the new fingerprint that tests/test_technik.py names (Dominik 2026-10-14: „ebenso aktuell halten wie alles andere“).
"""


def S(sid, art, name, sub, text, side=None):
    """One step of a page's way. name, sub, text: (German, English). side: (kind, label, text or step id), label is
    "ja"/"nein" or (German, English)."""
    return {"id": sid, "art": art, "name": name, "sub": sub, "text": text, "side": side}


# node id (technik.KNOTEN) -> page
SEITEN_DATEN = {
    "waechter": {
        "stand": "55042873e3",
        "bezug": {
            "notaus.AUTO": ["s4"], "netguard.allowed": ["s3", "s7", "s8"], "netguard.resolve": ["s2"],
            "netguard._Transport": ["s10", "s11"], "netguard._Capped": ["s11"], "netguard.same_site": ["s10"],
            "netguard.own_addresses": ["s3"], "netguard.IMAP4_SSL": ["s9"], "notaus.watch": ["s2"],
            "live.outgoing": ["s2"], "regeln": ["s6", "s8"], "regel:immer": ["s3", "s4", "s7"],
        },
        "kurz": ("Der Wächter entscheidet bei jeder Verbindung, die ein Werkzeug nach außen aufbaut, ob sie sein darf: "
                 "Webseiten aus der Suche, Kalender, Kontakte, Mail, Home Assistant, NAS und MCP-Dienste. "
                 "Er prüft die Adresse, die wirklich angefragt wird, nach festen Regeln; das Sprachmodell fragt er nie.",
                 "The guard decides for every connection a tool opens to the outside whether it may happen: web pages "
                 "from search, calendars, contacts, mail, Home Assistant, NAS and MCP services. It checks the address "
                 "that is really asked, by fixed rules; it never asks the language model."),
        "warum": ("Text von draußen (eine Webseite, eine Mail, ein Kalendereintrag) könnte das Sprachmodell dazu "
                  "bringen, Adressen im Heimnetz, Cloud-Metadaten oder die eigenen Dienste des Spark anzufragen "
                  "(SSRF). Der Wächter lässt das gar nicht erst zu, egal was im Text steht.",
                  "Text from outside (a web page, a mail, a calendar entry) could lead the language model to ask "
                  "addresses in the home network, cloud metadata or the Spark's own services (SSRF). The guard does "
                  "not let that happen, whatever the text says."),
        "ablauf": [
            S("s1", "start", ("Werkzeug will nach außen", "A tool wants out"),
              ("netguard.client(Stufe)", "netguard.client(level)"),
              ("Alles, was eine Adresse aus Einstellungen oder aus fremdem Text ansteuert, holt sich seinen Zugang "
               "über netguard.client mit einer Stufe (heute {@netguard_nutzer|anzahl} Module). Feste eigene Dienste wie das Sprachmodell "
               "laufen direkt; welche das sind und warum, steht in netguard.DIRECT_OK, ein Selbsttest hält die Liste "
               "vollständig.",
               "Everything that goes to an address from settings or from outside text gets its access through "
               "netguard.client with a level (today {@netguard_nutzer|anzahl} modules). Fixed own services like the language model go "
               "directly; which ones and why is listed in netguard.DIRECT_OK, a self-test keeps that list complete.")),
            S("s2", "schritt", ("Name einmal auflösen", "Resolve the name once"),
              ("jede Adresse des Namens wird geprüft", "every address of the name is checked"),
              ("resolve() fragt den Namen genau einmal ab. Hat er mehrere Adressen, muss jede erlaubt sein, sonst ist "
               "Schluss.", "resolve() looks the name up exactly once. If it has several addresses, each one must be "
               "allowed, else it stops.")),
            S("s3", "frage", ("Eigener Dienst?", "Own service?"),
              ("Ports {netguard.OWN_PORTS|bereiche} hier", "ports {netguard.OWN_PORTS|bereiche} here"),
              ("Die Ports der eigenen Dienste sind auf dieser Maschine gesperrt: auf Loopback und auf jeder eigenen "
               "Adresse im LAN oder VPN (own_addresses liest sie jede Minute neu).",
               "The ports of the own services are closed on this machine: on loopback and on every own address in "
               "the LAN or VPN (own_addresses reads them again every minute)."),
              ("stop", "ja", ("Gesperrt", "Blocked"))),
            S("s4", "frage", ("Internet und Notaus an?", "Internet and kill switch on?"),
              ("ab Notaus-Stufe {notaus.STAGE.internet} kein Internet", "from kill switch stage {notaus.STAGE.internet} no internet"),
              ("Ist die Adresse öffentlich und der Notaus mindestens auf Stufe {notaus.STAGE.internet}, geht nichts "
               "ins Internet, egal welche Stufe das Werkzeug hat. Das Heimnetz bleibt erreichbar, wie die Stufe es "
               "erlaubt.",
               "If the address is public and the kill switch is at stage {notaus.STAGE.internet} or higher, nothing "
               "goes to the internet, whatever level the tool has. The home network stays reachable as the level "
               "allows."),
              ("stop", "ja", ("Gesperrt (Notaus)", "Blocked (kill switch)"))),
            S("s5", "frage", ("Öffentliche Adresse?", "Public address?"),
              ("im Internet erreichbar", "reachable on the internet"),
              ("Eine öffentliche Adresse ist auf jeder Stufe erlaubt.", "A public address is allowed at every level."),
              ("ok", "ja", "s9")),
            S("s6", "frage", ("Stufe „nur Internet“?", "Level „internet only“?"),
              ("Seiten aus Suchergebnissen", "pages from search results"),
              ("Was aus Suchergebnissen oder Antworten kommt, darf nie ins Heimnetz ({@stufe_public}).",
               "What comes from search results or answers may never go to the home network ({@stufe_public})."),
              ("stop", "ja", ("Gesperrt", "Blocked"))),
            S("s7", "frage", ("Nie erlaubt?", "Never allowed?"),
              ("169.254 · Multicast · reserviert", "169.254 · multicast · reserved"),
              ("Link-lokale Adressen (169.254.x, dort antworten Cloud-Metadaten), Multicast, unbestimmte und "
               "reservierte Adressen sind auf keiner Stufe erlaubt.",
               "Link-local addresses (169.254.x, where cloud metadata answers), multicast, unspecified and reserved "
               "addresses are allowed at no level."),
              ("stop", "ja", ("Gesperrt", "Blocked"))),
            S("s8", "frage", ("Heimnetz erlaubt?", "Home network allowed?"),
              ("Stufe Heimnetz oder Schalter", "level home or switch"),
              ("Home Assistant und andere Dienste im Heimnetz ({@stufe_home}) dürfen immer. Kalender, Kontakte, "
               "Mail und MCP ({@stufe_user}) nur, wenn unter Einstellungen → Sicherheit → Heimnetz-Adressen erlauben "
               "eingeschaltet ist.",
               "Home Assistant and other services in the home network ({@stufe_home}) always may. Calendars, "
               "contacts, mail and MCP ({@stufe_user}) only when Settings → Security → Allow home network addresses "
               "is on."),
              ("stop", "nein", ("Gesperrt", "Blocked"))),
            S("s9", "schritt", ("Verbinden mit genau dieser Adresse", "Connect to exactly this address"),
              ("kein zweites Nachschlagen · TLS prüft den Namen", "no second look-up · TLS checks the name"),
              ("Die Verbindung geht an die geprüfte Adresse, nicht noch einmal an den Namen. Ein zweites Nachschlagen "
               "könnte anders antworten (DNS-Rebinding). Das Zertifikat wird trotzdem für den Namen geprüft.",
               "The connection goes to the checked address, not to the name again. A second look-up could answer "
               "differently (DNS rebinding). The certificate is still checked for the name.")),
            S("s10", "schritt", ("Passwort nur zur eigenen Seite", "Password only to its own site"),
              ("gleicher Name oder Hauptdomain · nie https → http", "same name or parent domain · never https → http"),
              ("Anmeldedaten gehen nur an die Seite, für die sie eingetragen wurden (gleicher Host oder gleiche "
               "Hauptdomain, etwa die CalDAV-Server von icloud.com), nie über http, wenn die Adresse https war.",
               "Login data only goes to the site it was entered for (same host or same parent domain, like the "
               "CalDAV servers of icloud.com), never over http when the address was https.")),
            S("s11", "schritt", ("Antwort höchstens {netguard.MAX_BYTES|mb}", "Answer at most {netguard.MAX_BYTES|mb}"),
              ("auch nach dem Entpacken", "also after unpacking"),
              ("Antworten werden bei {netguard.MAX_BYTES|mb} abgeschnitten, auch nach dem Entpacken von gzip, damit "
               "eine riesige oder gepackte Antwort den Speicher nicht füllt.",
               "Answers are cut at {netguard.MAX_BYTES|mb}, also after unpacking gzip, so a huge or packed answer "
               "cannot fill the memory."),
              ("stop", ("größer", "larger"), ("Abbruch", "Stopped"))),
            S("s12", "ende", ("Antwort ans Werkzeug", "Answer to the tool"),
              ("nur als Daten, nie als Befehl", "as data only, never as a command"),
              ("Das Werkzeug bekommt die Antwort als Daten. Eine Weiterleitung ist eine neue Verbindung und wird "
               "genauso geprüft, ab Schritt 2.",
               "The tool gets the answer as data. A redirect is a new connection and is checked the same way, from "
               "step 2."),
              ("zurueck", ("Weiterleitung", "redirect"), "s2")),
        ],
        "beispiele": [
            (("Webseite aus der Suche", "Web page from search"), ["s1", "s2", "s3", "s4", "s5", "s5!", "s9", "s10", "s11", "s12"],
             ("Erlaubt: verbunden mit der geprüften öffentlichen Adresse.", "Allowed: connected to the checked public address.")),
            (("Home Assistant im Heimnetz", "Home Assistant at home"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Erlaubt: die Stufe Heimnetz darf ins Heimnetz.", "Allowed: the level home may go to the home network.")),
            (("Kalender im Heimnetz, Schalter aus", "Calendar at home, switch off"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!"],
             ("Gesperrt: Heimnetz-Adressen sind für Nutzer-Dienste aus.", "Blocked: home network addresses are off for user services.")),
            (("Link auf Cloud-Metadaten", "Link to cloud metadata"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!"],
             ("Gesperrt: eine Seite aus der Suche darf nie ins Heimnetz, 169.254 nie.", "Blocked: a page from search never goes home, 169.254 never.")),
            (("Notaus an, Wetter abfragen", "Kill switch on, ask weather"), ["s1", "s2", "s3", "s4", "s4!"],
             ("Gesperrt: bei Notaus geht nichts ins Internet.", "Blocked: with the kill switch nothing goes to the internet.")),
        ],
        "regeln": [
            [("Stufe", "Level"), ("Wer sie nutzt (aus dem Code)", "Who uses it (from the code)"), ("Internet", "Internet"), ("Heimnetz", "Home network")],
            [("nur Internet", "internet only"), ("{@stufe_public}", "{@stufe_public}"), "✓", "✕"],
            [("Nutzer", "user"), ("{@stufe_user}", "{@stufe_user}"), "✓", ("nur mit Schalter", "only with switch")],
            [("Heimnetz", "home"), ("{@stufe_home}", "{@stufe_home}"), "✓", "✓"],
            [("je nach Ziel", "by target"), ("{@stufe_wechselnd}", "{@stufe_wechselnd}"), ("wie das Ziel eingestellt ist", "as the target is set"), ""],
            [("immer", "always"), ("alle", "all"), ("✕ bei Notaus", "✕ with kill switch"), ("✕ eigene Dienste, 169.254, Multicast", "✕ own services, 169.254, multicast")],
        ],
        "zahlen": [
            ("{netguard.MAX_BYTES|mb}", ("größte Antwort", "largest answer"), "netguard.MAX_BYTES"),
            ("{netguard.OWN_PORTS|bereiche}", ("gesperrte eigene Ports", "closed own ports"), "netguard.OWN_PORTS"),
            ("{notaus.AUTO.netguard.0}", ("Sperren in {notaus.AUTO.netguard.1|min} Minuten bis Notaus Stufe 1 (wenn an)",
                                          "blocks in {notaus.AUTO.netguard.1|min} minutes until kill switch stage 1 (if on)"), "notaus.AUTO"),
            ("{notaus.STAGE.internet}", ("Notaus-Stufe ohne Internet", "kill switch stage without internet"), "notaus.STAGE"),
        ],
        "einstellen": [
            ("Einstellungen → Sicherheit → Heimnetz-Adressen erlauben: Kalender, Kontakte, Mail und MCP dürfen auch ins "
             "Heimnetz (Standard aus).",
             "Settings → Security → Allow home network addresses: calendars, contacts, mail and MCP may also go to the "
             "home network (default off)."),
            ("Einstellungen → Sicherheit → Notaus von selbst: viele gesperrte Verbindungen in kurzer Zeit lösen "
             "Notaus Stufe 1 aus (Standard aus).",
             "Settings → Security → Emergency stop by itself: many blocked connections in a short time trigger kill "
             "switch stage 1 (default off)."),
        ],
        "sehen": [
            ("Zustand → Live: eine rote Linie endet mit ✕ an der Wand, mit Adresse und Grund; die Kachel „Wächter "
             "heute“ zählt die Sperren.",
             "Status → Live: a red line ends with ✕ at the wall, with address and reason; the tile „Wächter today“ "
             "counts the blocks."),
            ("Ich → Mein Zustand: ob ein eigener Dienst (Kalender, Mail) antwortet oder die Anmeldung abgelehnt hat.",
             "Me → My status: whether an own service (calendar, mail) answers or refused the login."),
        ],
        "mehr": [
            (("Wenn gesperrt", "When blocked"), [
                ("Das Werkzeug bekommt statt einer Antwort den Fehler Blocked mit dem Grund; es kommt keine Verbindung zustande.",
                 "Instead of an answer the tool gets the error Blocked with the reason; no connection is made."),
                ("Die Sperre zählt für „Notaus von selbst“: {notaus.AUTO.netguard.0} in {notaus.AUTO.netguard.1|min} "
                 "Minuten heben den Notaus auf Stufe 1, wenn der Schalter an ist. Sperren durch den Notaus selbst und "
                 "Proben des Dienst-Wächters zählen nicht.",
                 "The block counts for „Emergency stop by itself“: {notaus.AUTO.netguard.0} in "
                 "{notaus.AUTO.netguard.1|min} minutes raise the kill switch to stage 1 when the switch is on. Blocks by "
                 "the kill switch itself and probes of the service watch do not count."),
            ]),
        ],
        "code": [
            ("netguard.allowed", ("die Regel: nichts oder der Grund", "the rule: nothing or the reason")),
            ("netguard.resolve", ("einmal auflösen, jede Adresse prüfen, Live melden", "resolve once, check every address, tell Live")),
            ("netguard.client", ("der Zugang nach außen für Werkzeuge", "the way out for tools")),
            ("netguard._Transport", ("Passwort-Schutz, Größengrenze, Ergebnis für Mein Zustand", "password guard, size limit, result for My status")),
            ("netguard._Capped", ("schneidet die Antwort ab, auch entpackt", "cuts the answer, also unpacked")),
            ("netguard.same_site", ("gleiche Seite für Anmeldedaten", "same site for login data")),
            ("netguard.own_addresses", ("alle Adressen dieser Maschine", "every address of this machine")),
            ("netguard.IMAP4_SSL", ("Mail über die geprüfte Adresse", "mail over the checked address")),
            ("notaus.watch", ("zählt Sperren für Notaus von selbst", "counts blocks for the automatic kill switch")),
            ("live.outgoing", ("zeigt jede Entscheidung auf Live", "shows each decision on Live")),
        ],
        "tests": ["test_hardening", "test_notaus", "test_waechter_umgehung"],
        "heute": [("guard_ok", ("verbunden", "connected")), ("guard_bad", ("gesperrt", "blocked")),
                  ("guard_cut", ("zu groß, abgebrochen", "too large, stopped"))],
    },
    # ------------------------------------------------------------------ middleware (panel.py, notaus.py)
    "middleware": {
        "stand": "7cf7af3560",
        "bezug": {
            "panel.slow_reads": ["s2"], "panel.emergency": ["s3", "s4"], "notaus.at_home": ["s5"],
            "panel.sessions": ["s7", "s12"], "guard.same_origin": ["s7"], "panel._may_upload": ["s8"],
            "panel.protect": ["s12"], "regeln": ["s4", "s5", "s6"],
        },
        "kurz": ("Die Middleware ist die Schicht in panel.py, durch die jede HTTP-Anfrage geht, bevor ein Endpunkt sie "
                 "liest: Notaus, fremde Seiten (CSRF), Größe der Anfrage und Update-Sperre. Auf dem Rückweg setzt sie "
                 "Schutz-Kopfzeilen, schreibt Änderungen ins Admin-Protokoll und erneuert Anmeldungen.",
                 "The middleware is the layer in panel.py every HTTP request passes before an endpoint reads it: kill "
                 "switch, foreign pages (CSRF), size of the request and update lock. On the way back it sets "
                 "protective headers, writes changes to the admin log and renews logins."),
        "warum": ("FastAPI liest Datei-, Formular- und JSON-Teile, bevor die Anmeldung eines Endpunkts geprüft wird. "
                  "Ohne diese Schicht könnte jeder mit einem riesigen Upload Speicher oder Platte füllen und bekäme sein "
                  "„nicht angemeldet“ erst danach. Ebenso muss der Notaus greifen, bevor irgendein Endpunkt etwas tut, "
                  "und eine fremde Webseite darf die Cookies des Browsers nie für Änderungen benutzen.",
                  "FastAPI reads file, form and JSON parts before an endpoint checks the login. Without this layer "
                  "anyone could fill memory or disk with a huge upload and would get the „not logged in“ only "
                  "afterwards. Likewise the kill switch must hold before any endpoint does anything, and a foreign web "
                  "page must never use the browser's cookies for changes."),
        "ablauf": [
            S("s1", "start", ("Anfrage kommt an", "A request arrives"),
              ("Browser, Apps, Uhr, Lautsprecher, MCP", "browser, apps, watch, speakers, MCP"),
              ("Jede HTTP-Anfrage an das Panel geht durch diese Schicht, von außen nach innen in der Reihenfolge, in "
               "der Starlette die Middleware stapelt (die zuletzt angemeldete liegt außen). Telegram, „Spark fragen“ "
               "über MCP und die Lautsprecher bauen ihre Frage im Panel selbst und rufen chat.chat direkt auf; deren "
               "äußere Anfrage ist vorher schon hier durchgegangen.",
               "Every HTTP request to the panel passes this layer, from the outside in, in the order Starlette stacks "
               "the middleware (the one added last is outermost). Telegram, „Ask Spark“ over MCP and the speakers "
               "build their question inside the panel and call chat.chat directly; their outer request already "
               "passed here.")),
            S("s2", "schritt", ("Zeit messen", "Start the clock"),
              ("slow_reads, ganz außen", "slow_reads, outermost"),
              ("slow_reads misst die ganze Anfrage. Ein Lesen unter /api/, das länger als {panel.SLOW_READ} s "
               "braucht, wird eine Zeile im Journal, je Route höchstens alle {panel.SLOW_EVERY} s; nur das Muster der "
               "Route und die Zeit, nie die Abfrage oder Namen.",
               "slow_reads times the whole request. A read under /api/ that takes longer than {panel.SLOW_READ} s "
               "becomes one journal line, per route at most every {panel.SLOW_EVERY} s; only the route's pattern and "
               "the time, never the query or names.")),
            S("s3", "frage", ("Mein Notaus für diesen Schlüssel?", "My kill switch for this key?"),
              ("notaus.mine_gate", "notaus.mine_gate"),
              ("Trägt die Anfrage einen Geräteschlüssel und hat dessen Profil seinen eigenen Notaus an, bekommt sie "
               "nichts außer dem Stand des Notaus. Sonst merkt sich das Panel, für welches Profil diese Anfrage "
               "handelt, damit die letzte Abwehr tiefer unten weiß, wessen Aktion es wäre.",
               "If the request carries a device key and that key's profile has its own kill switch on, it gets "
               "nothing but the kill switch state. Otherwise the panel notes which profile this request acts for, so "
               "the last line of defence further down knows whose action it would be."),
              ("stop", "ja", ("Gesperrt (503)", "Blocked (503)"))),
            S("s4", "frage", ("Notaus an?", "Kill switch on?"),
              ("notaus.gate", "notaus.gate"),
              ("Ist der Notaus aus, geht die Anfrage gleich weiter zur Herkunftsprüfung. Die Seite selbst und ihre "
               "Dateien kommen immer durch, damit man den Notaus sehen und aufheben kann.",
               "With the kill switch off the request goes straight on to the origin check. The page itself and its "
               "files always pass, so the kill switch can be seen and lifted."),
              ("ok", "nein", "s7")),
            S("s5", "frage", ("Von außen?", "From outside?"),
              ("nicht im Heimnetz", "not in the home network"),
              ("Im Heimnetz ist nur, wer eine private Adresse hat und nicht über einen Proxy kommt, oder über einen "
               "eingetragenen Proxy, der eine private Adresse meldet. Ab Notaus-Stufe {notaus.STAGE.aussen} bekommt "
               "alles von außen nur noch die Seite und den Notaus-Stand.",
               "In the home network is only who has a private address and does not come through a proxy, or comes "
               "through a listed proxy that reports a private address. From kill switch stage "
               "{notaus.STAGE.aussen} everything from outside only gets the page and the kill switch state."),
              ("stop", "ja", ("Von außen gesperrt (503)", "Blocked from outside (503)"))),
            S("s6", "frage", ("Alles still?", "All quiet?"),
              ("Stufe {notaus.STAGE.gespraech}", "stage {notaus.STAGE.gespraech}"),
              ("In Stufe {notaus.STAGE.gespraech} gehen auch im Heimnetz nur noch Anmelden, der Admin-Modus, das "
               "Aufheben des Notaus und das Lesen von Zustand, Logs und Live durch. In den Stufen darunter läuft "
               "im Heimnetz alles weiter; Aktionen hält das Panel dann tiefer unten an.",
               "In stage {notaus.STAGE.gespraech} only logins, the admin mode, lifting the kill switch and reading "
               "status, logs and live pass, also at home. In the stages below everything at home goes on; the panel "
               "then holds actions off further down."),
              ("stop", "ja", ("Alles angehalten (503)", "Everything stopped (503)"))),
            S("s7", "frage", ("Fremde Seite?", "Foreign page?"),
              ("Sec-Fetch-Site oder Origin", "Sec-Fetch-Site or Origin"),
              ("Eine ändernde Anfrage (POST, PUT, PATCH, DELETE), die ein Anmelde-Cookie mitbringt, muss von der "
               "eigenen Seite kommen: der Browser sagt es mit Sec-Fetch-Site, sonst wird Origin mit dem Host "
               "verglichen. Ein anderer Port auf demselben Rechner gilt als fremd. Ohne beide Kopfzeilen ist es kein "
               "Browser (Skripte) und geht durch.",
               "A changing request (POST, PUT, PATCH, DELETE) that carries a login cookie must come from the panel's "
               "own page: the browser says so with Sec-Fetch-Site, else Origin is compared with the host. Another "
               "port on the same machine counts as foreign. With neither header it is not a browser (scripts) and "
               "passes."),
              ("stop", "ja", ("Abgewiesen (403), Eintrag im Admin-Protokoll", "Refused (403), entry in the admin log"))),
            S("s8", "frage", ("Großer Upload ohne Anmeldung?", "Big upload without login?"),
              ("_may_upload", "_may_upload"),
              ("Die Pfade für große Uploads (Sicherungen, Stimmen, Ton, Dokumente, Bilder, MCP) nehmen nur an, wer "
               "überhaupt angemeldet sein könnte: Admin-Cookie, Profil, Admin-Modus oder eine Authorization-Zeile. "
               "Die echte Prüfung kommt danach im Endpunkt; hier geht es nur darum, dass kein Byte eines fremden "
               "Uploads gelesen wird.",
               "The paths for big uploads (backups, voices, sound, documents, pictures, MCP) only accept someone who "
               "could be logged in at all: admin cookie, profile, admin mode or an Authorization line. The real check "
               "comes later in the endpoint; here no byte of a stranger's upload is read."),
              ("stop", "ja", ("Anmeldung nötig (401)", "Login required (401)"))),
            S("s9", "frage", ("Zu groß?", "Too large?"),
              ("common.BodyLimit", "common.BodyLimit"),
              ("Jeder Pfad hat seine Grenze, sonst gilt eine kleine Standardgrenze von zwei MB. Eine zu große "
               "Content-Length wird sofort abgelehnt; beim Lesen zählt BodyLimit zusätzlich mit und bricht ab, sobald "
               "mehr kommt als erlaubt.",
               "Every path has its limit, else a small default of two MB holds. A Content-Length that is too large is "
               "refused at once; while reading, BodyLimit also counts and stops as soon as more arrives than "
               "allowed."),
              ("stop", "ja", ("Zu groß (413)", "Too large (413)"))),
            S("s10", "frage", ("Update läuft?", "Update running?"),
              ("update.update_lock", "update.update_lock"),
              ("Während ein Update läuft, werden Änderungen unter /api/ angehalten. Der Assistent, die Geräte und das "
               "Anmelden bleiben offen (update.UNLOCKED).",
               "While an update runs, changes under /api/ are held. The assistant, the devices and logging in stay "
               "open (update.UNLOCKED)."),
              ("stop", "ja", ("Gesperrt bis zum Ende (423)", "Locked until done (423)"))),
            S("s11", "schritt", ("Endpunkt", "Endpoint"),
              ("Anmeldung, Profil, Rate-Limit", "login, profile, rate limit"),
              ("Erst jetzt liest der Endpunkt die Anfrage und prüft selbst Anmeldung, Profil und Rate-Limit (die "
               "nächste Station, „Anmeldung, Profil“).",
               "Only now the endpoint reads the request and checks login, profile and rate limit itself (the next "
               "box, „Login, profile“).")),
            S("s12", "ende", ("Antwort mit Schutz", "Answer with protection"),
              ("Kopfzeilen · Protokoll · Cookies", "headers · log · cookies"),
              ("Jede Antwort bekommt die Schutz-Kopfzeilen (keine fremden Rahmen, strenge Content-Security-Policy, "
               "auf https auch HSTS), unter /api/ „no-store“. Eine Änderung landet mit wer, Pfad und Status im "
               "Admin-Protokoll, außer gewöhnlicher Nutzung aus guard.QUIET_WHY. Benutzte Anmeldungen werden "
               "erneuert, auf https immer mit Secure.",
               "Every answer gets the protective headers (no foreign frames, a strict Content-Security-Policy, on "
               "https also HSTS), under /api/ „no-store“. A change goes into the admin log with who, path and status, "
               "except normal use from guard.QUIET_WHY. Logins in use are renewed, on https always with Secure.")),
        ],
        "beispiele": [
            (("Einstellung im Browser zu Hause", "Setting in the browser at home"),
             ["s1", "s2", "s3", "s4", "s4!", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Durch: der Endpunkt prüft die Anmeldung, die Änderung steht im Admin-Protokoll.",
              "Passes: the endpoint checks the login, the change is in the admin log.")),
            (("Fremde Webseite schickt ein Formular", "Foreign web page sends a form"),
             ["s1", "s2", "s3", "s4", "s4!", "s7", "s7!"],
             ("Abgewiesen mit 403, bevor ein Endpunkt etwas tut.", "Refused with 403 before any endpoint acts.")),
            (("Notaus Stufe 1, App unterwegs", "Kill switch stage 1, app on the road"),
             ["s1", "s2", "s3", "s4", "s5", "s5!"],
             ("Gesperrt mit 503 und der Stufe; die App zeigt den Notaus.", "Blocked with 503 and the stage; the app shows the kill switch.")),
            (("Großer Upload ohne Anmeldung", "Big upload without login"),
             ["s1", "s2", "s3", "s4", "s4!", "s7", "s8", "s8!"],
             ("Abgewiesen mit 401, kein Byte gelesen.", "Refused with 401, not a byte read.")),
        ],
        "regeln": [
            [("Notaus-Stufe", "Kill switch stage"), ("Von außen", "From outside"), ("Im Heimnetz", "At home")],
            [("aus", "off"), ("alles", "everything"), ("alles", "everything")],
            [("{notaus.STAGE.aussen} und {notaus.STAGE.aktion}", "{notaus.STAGE.aussen} and {notaus.STAGE.aktion}"),
             ("nur die Seite und der Notaus-Stand", "only the page and the kill switch state"),
             ("alles; Aktionen hält das Panel tiefer unten an", "everything; the panel holds actions off further down")],
            [("{notaus.STAGE.gespraech}", "{notaus.STAGE.gespraech}"), ("nur die Seite und der Notaus-Stand", "only the page and the kill switch state"),
             ("Anmelden, Admin-Modus, Aufheben, Zustand und Logs lesen", "logging in, admin mode, lifting, reading status and logs")],
        ],
        "zahlen": [
            ("{notaus.STAGE.aussen}", ("Notaus-Stufe, ab der nichts von außen durchkommt", "kill switch stage from which nothing from outside passes"), "notaus.STAGE"),
            ("{notaus.STAGE.gespraech}", ("Notaus-Stufe, in der auch zu Hause fast alles steht", "kill switch stage in which almost everything stops at home too"), "notaus.STAGE"),
            ("{panel.SLOW_READ} s", ("ab hier gilt ein Lesen als langsam", "from here a read counts as slow"), "panel.SLOW_READ"),
            ("{panel.SLOW_EVERY} s", ("höchstens eine Zeile je Route", "at most one line per route"), "panel.SLOW_EVERY"),
        ],
        "einstellen": [
            ("Einstellungen → Sicherheit → Reverse Proxy: nur von diesen Adressen zählt X-Forwarded-For. Das "
             "entscheidet, wer als „im Heimnetz“ gilt und welche Adresse gesperrt wird.",
             "Settings → Security → Reverse proxy: X-Forwarded-For counts only from these addresses. That decides "
             "who counts as „at home“ and which address gets locked."),
            ("Einstellungen → Sicherheit → Notaus von selbst: viele falsche Anmeldungen, MCP-Anfragen oder gesperrte "
             "Verbindungen von außen lösen Notaus Stufe {notaus.STAGE.aussen} aus (Standard aus).",
             "Settings → Security → Emergency stop by itself: many wrong logins, MCP requests or blocked connections "
             "from outside trigger kill switch stage {notaus.STAGE.aussen} (default off)."),
        ],
        "sehen": [
            ("Zustand → Live: unter Ereignisse steht „fremde Seite abgewiesen“; der Notaus erscheint als Banner.",
             "Status → Live: under events it says „foreign page refused“; the kill switch shows as a banner."),
            ("Logs → Admin-Protokoll: jede Änderung mit wer, Pfad und Status, auch abgewiesene fremde Seiten.",
             "Logs → Admin log: every change with who, path and status, also refused foreign pages."),
            ("Zustand → Logs: langsame Lesezugriffe als Zeile „seite: slow GET …“.",
             "Status → Logs: slow reads as a line „seite: slow GET …“."),
        ],
        "mehr": [
            (("Warum diese Reihenfolge", "Why this order"), [
                ("Der Notaus liegt außen: auch eine fremde Seite oder ein zu großer Upload von außen bekommt bei "
                 "Notaus nur die Stufe zu hören.",
                 "The kill switch is outermost: with it on, even a foreign page or an oversized upload from outside only "
                 "hears the stage."),
                ("Die Herkunft kommt vor der Größe: eine fremde Seite wird abgewiesen, ohne dass ihr Inhalt gelesen wird.",
                 "Origin comes before size: a foreign page is refused without its content being read."),
                ("Was der Notaus tief unten anhält (NotausAktiv), wird als klarer Satz mit 503 beantwortet, nie als "
                 "Serverfehler.",
                 "What the kill switch holds off deep down (NotausAktiv) is answered as a plain sentence with 503, "
                 "never as a server error."),
            ]),
        ],
        "code": [
            ("panel.slow_reads", ("misst jede Anfrage", "times every request")),
            ("panel.emergency", ("Notaus vor jedem Endpunkt", "kill switch before any endpoint")),
            ("notaus.mine_gate", ("Mein Notaus für Geräteschlüssel", "my kill switch for device keys")),
            ("notaus.gate", ("was bei welcher Stufe durchkommt", "what passes at which stage")),
            ("notaus.at_home", ("im Heimnetz oder von außen", "at home or from outside")),
            ("panel.sessions", ("fremde Seiten, Protokoll, Cookies erneuern", "foreign pages, log, renew cookies")),
            ("guard.same_origin", ("die Herkunftsregel", "the origin rule")),
            ("panel._may_upload", ("große Uploads nur mit Anmeldung", "big uploads only with a login")),
            ("common.BodyLimit", ("Größengrenze vor dem Lesen", "size limit before reading")),
            ("update.update_lock", ("Änderungen während eines Updates", "changes during an update")),
            ("panel.protect", ("Schutz-Kopfzeilen", "protective headers")),
        ],
        "tests": ["test_hardening", "test_panel", "test_notaus", "test_seiten_laden"],
        "heute": [],
    },

    # ------------------------------------------------------------------ zugang (guard, core, profiles, features)
    "zugang": {
        "stand": "cd61a46b1b",
        "bezug": {
            "guard.MAX_FAILS": ["s2", "s3"], "guard.MAX_NAME_FAILS": ["s2", "s3"], "guard.LOCK_FIRST": ["s2"],
            "guard.DAY_FAILS": ["s2", "s3"], "guard.failed": ["s3"], "guard.succeeded": ["s5"],
            "account.profile_login": ["s3"], "account.second_step": ["s4"], "core.is_main_admin": ["s6"],
            "profiles._cookie_user": ["s6"], "features.reason": ["s11"], "regeln": ["s6", "s7"],
            "regel:Gast": ["s8", "s10"],
        },
        "kurz": ("Hier entscheidet das Panel, wer eine Anfrage stellt und was diese Person darf: Anmeldung mit "
                 "Passwort oder PIN (mit Sperre nach Fehlversuchen), Cookie oder Geräteschlüssel, Rate-Limit und die "
                 "Freigaben je Funktion. Das Profil kommt nur aus Cookie, Schlüssel oder dem Panel selbst, nie aus dem "
                 "Text einer Anfrage oder vom Modell.",
                 "Here the panel decides who sends a request and what that person may do: login with password or PIN "
                 "(with a lock after wrong attempts), cookie or device key, rate limit and the release per function. "
                 "The profile comes only from the cookie, the key or the panel itself, never from a request's text or "
                 "from the model."),
        "warum": ("Der Spark ist über das Heimnetz und oft über einen Proxy aus dem Internet erreichbar. Ohne Sperre "
                  "ließe sich eine PIN durchprobieren, ohne Rate-Limit könnte eine Seite oder ein Skript die GPU für "
                  "sich nehmen, und ohne feste Bindung an ein Profil könnte eine Anfrage sich als jemand anderes "
                  "ausgeben.",
                  "The Spark is reachable in the home network and often through a proxy from the internet. Without a "
                  "lock a PIN could be guessed, without a rate limit one page or script could take the GPU for itself, "
                  "and without a fixed binding to a profile a request could pretend to be someone else."),
        "ablauf": [
            S("s1", "start", ("Anmelden oder fragen", "Log in or ask"),
              ("/api/login · /api/profile/login · jede Anfrage", "/api/login · /api/profile/login · every request"),
              ("Beim Anmelden bekommt der Browser ein Cookie; Apps, Uhr und Lautsprecher haben stattdessen einen "
               "Geräteschlüssel. Die Schritte 2 bis 5 laufen einmal beim Anmelden, die Schritte ab 6 bei jeder Anfrage.",
               "Logging in gives the browser a cookie; apps, watch and speakers have a device key instead. Steps 2 to "
               "5 run once when logging in, the steps from 6 on with every request.")),
            S("s2", "frage", ("Gesperrt?", "Locked?"),
              ("guard.check", "guard.check"),
              ("Gesperrt wird je Adresse und je Name (oder Admin-Passwort). Die Sperre eines Namens gilt nicht für "
               "einen Browser, der sich mit diesem Namen schon angemeldet hat (Cookie speech_known, gespeichert wird "
               "nur sein Hash). So kann ein Fremder durch Raten den Besitzer nicht aussperren.",
               "Locks are kept per address and per name (or the admin password). A name's lock does not hold for a "
               "browser that logged in to that name before (cookie speech_known, only its hash is kept). So a "
               "stranger guessing cannot lock the owner out."),
              ("stop", "ja", ("Zu viele Fehlversuche (429)", "Too many wrong attempts (429)"))),
            S("s3", "frage", ("Passwort oder PIN richtig?", "Password or PIN right?"),
              ("PBKDF2 · {core.ROUNDS} Runden", "PBKDF2 · {core.ROUNDS} rounds"),
              ("Geprüft wird in einem eigenen Thread. Ein unbekannter Name kostet dieselbe Arbeit wie eine falsche "
               "PIN, die Antwort ist dieselbe. Ein Fehlversuch wartet eine Sekunde, zählt für die Sperre und, wenn er "
               "von außen kommt, für „Notaus von selbst“.",
               "The check runs in its own thread. An unknown name costs the same work as a wrong PIN, the answer is "
               "the same. A wrong attempt waits a second, counts for the lock and, when it comes from outside, for "
               "„Emergency stop by itself“."),
              ("stop", "nein", ("Abgewiesen (401)", "Refused (401)"))),
            S("s4", "frage", ("Zweiter Schritt?", "Second step?"),
              ("Code oder Passkey", "code or passkey"),
              ("Hat das Profil (oder der Admin) den zweiten Schritt an und ist der Browser nicht als vertraut "
               "eingetragen, kommt als Nächstes der Code aus der App oder ein Passkey. Ein falscher Code zählt wie eine "
               "falsche PIN.",
               "If the profile (or the admin) has the second step on and the browser is not trusted, the code from "
               "the app or a passkey comes next. A wrong code counts like a wrong PIN."),
              ("info", "ja", ("Code oder Passkey, dann weiter", "code or passkey, then on"))),
            S("s5", "schritt", ("Cookie setzen", "Set the cookie"),
              ("signiert · Sitzungsliste", "signed · list of sessions"),
              ("Der Zähler der Adresse wird gelöscht; Fehlversuche Fremder für den Namen zählen weiter. Das "
               "Profil-Cookie ist signiert und steht in der Liste der angemeldeten Browser; es gilt höchstens "
               "{profiles.SESSION_DAYS} Tage ohne Nutzung und wird erneuert, solange es benutzt wird. Das Admin-Cookie "
               "ist mit Passwort, einem eigenen Schlüssel dieses Spark und dem zweiten Schritt signiert.",
               "The address's counter is cleared; strangers' wrong attempts for the name keep counting. The profile "
               "cookie is signed and stands in the list of signed-in browsers; it holds at most "
               "{profiles.SESSION_DAYS} days without use and is renewed while used. The admin cookie is signed with "
               "the password, a key of this Spark only and the second step.")),
            S("s6", "schritt", ("Profil bestimmen", "Find the profile"),
              ("profiles.current", "profiles.current"),
              ("Zuerst, was nur das Panel selbst setzt (Telegram, „Spark fragen“ über MCP), dann der Geräteschlüssel "
               "(nur sein Hash ist gespeichert), dann das Cookie: Signatur, Alter, Sitzung noch in der Liste und nicht "
               "abgemeldet.",
               "First what only the panel itself sets (Telegram, „Ask Spark“ over MCP), then the device key (only its "
               "hash is stored), then the cookie: signature, age, session still in the list and not logged out.")),
            S("s7", "frage", ("Schlüssel für diesen Weg frei?", "Key free for this path?"),
              ("Bereich des Schlüssels", "the key's scope"),
              ("Ein Schlüssel mit Bereich (App, Uhr, Raum, Home Assistant, Schreibhilfe, Begleiter) reicht nur für "
               "seine eigenen Pfade und nur, solange Admin und Profil die Funktion anhaben. Ist sie gerade aus oder "
               "hat das Profil seinen eigenen Notaus an, antwortet das Panel mit 503 statt 401, damit die App ihre "
               "Kopplung behält.",
               "A key with a scope (app, watch, room, Home Assistant, writing help, companion) only reaches its own "
               "paths and only while the admin and the profile have the function on. If it is off right now or the "
               "profile has its own kill switch on, the panel answers 503 instead of 401, so the app keeps its "
               "pairing."),
              ("stop", "nein", ("Kein Profil (401 oder 503)", "No profile (401 or 503)"))),
            S("s8", "frage", ("Ohne Profil und Gastzugang aus?", "No profile and guest access off?"),
              ("core.assistant", "core.assistant"),
              ("Ohne Profil kommt nur durch, wer der Admin ist (Cookie oder HTTP Basic, dessen Fehlversuche wie auf "
               "der Anmeldeseite zählen), oder wenn der Admin den Assistenten ohne Passwort freigegeben hat. Gäste "
               "bekommen dann nur Frage und Antwort.",
               "Without a profile only the admin passes (cookie or HTTP Basic, whose wrong attempts count like on the "
               "login page), or anybody when the admin opened the assistant without password. Guests then only get "
               "question and answer."),
              ("stop", "ja", ("Anmeldung nötig (401)", "Login required (401)"))),
            S("s9", "frage", ("Zu viele Anfragen?", "Too many requests?"),
              ("guard.limit", "guard.limit"),
              ("Je Profil, sonst je Adresse, zählt das Panel die Anfragen der letzten Minute: im Chat "
               "{guard.RATE.chat.1} für ein Profil oder den Admin, {guard.RATE.chat.0} für einen Gast.",
               "Per profile, else per address, the panel counts the requests of the last minute: in the chat "
               "{guard.RATE.chat.1} for a profile or the admin, {guard.RATE.chat.0} for a guest."),
              ("stop", "ja", ("Bitte kurz warten (429)", "Please wait a moment (429)"))),
            S("s10", "frage", ("Gast, alle Plätze belegt?", "Guest, all places taken?"),
              ("guard.Slot", "guard.Slot"),
              ("Gäste teilen sich {guard.BUSY.chat} gleichzeitige Plätze im Chat. Ein Platz, den niemand freigibt, "
               "gilt nach {guard.Slot.SLOT_MAX|min} Minuten wieder als frei.",
               "Guests share {guard.BUSY.chat} places at once in the chat. A place nobody frees counts as free again "
               "after {guard.Slot.SLOT_MAX|min} minutes."),
              ("stop", "ja", ("Assistent beschäftigt (429)", "Assistant busy (429)"))),
            S("s11", "schritt", ("Freigabe je Funktion", "Release per function"),
              ("features.allowed", "features.allowed"),
              ("Für jede Funktion fragt das Panel in fester Reihenfolge: Schalter des Admins (und der Funktion, auf "
               "der sie aufbaut), Gast (bekommt nie eine), vom Admin für das Profil gesperrt, eigener Wunsch des "
               "Profils, zweiter Schritt nötig. Gelesen wird bei jeder Anfrage neu, eine Änderung gilt also sofort.",
               "For every function the panel asks in a fixed order: the admin's switch (and the one of the function "
               "it builds on), guest (never gets one), blocked by the admin for the profile, the profile's own wish, "
               "second step needed. It is read anew with every request, so a change holds at once.")),
            S("s12", "ende", ("Weiter zur Vorbereitung", "On to preparing"),
              ("nur die Profil-ID geht weiter", "only the profile id goes on"),
              ("Die Anfrage geht mit ihrem Profil (oder als Gast) an chat_turn.prepare. Die Sprache bekommt Vorrang "
               "vor Hintergrundarbeit, und die anderen offenen Seiten des Profils sehen „antwortet gerade“.",
               "The request goes on with its profile (or as a guest) to chat_turn.prepare. Speech gets priority over "
               "background work, and the profile's other open pages see „answering“.")),
        ],
        "beispiele": [
            (("Anmeldung mit PIN", "Login with PIN"), ["s1", "s2", "s3", "s4", "s5"],
             ("Angemeldet: der Browser hat ein signiertes Cookie.", "Logged in: the browser has a signed cookie.")),
            (("Fremder rät eine PIN", "Stranger guesses a PIN"), ["s1", "s2", "s3", "s3!"],
             ("Abgewiesen; nach {guard.MAX_FAILS} Fehlversuchen ist die Adresse gesperrt.",
              "Refused; after {guard.MAX_FAILS} wrong attempts the address is locked.")),
            (("Frage aus der iPhone-App", "Question from the iPhone app"),
             ["s1", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Durch: Profil aus dem Geräteschlüssel, Freigaben je Funktion.", "Passes: profile from the device key, releases per function.")),
            (("Gast, Gastzugang aus", "Guest, guest access off"), ["s1", "s6", "s7", "s8", "s8!"],
             ("Abgewiesen mit 401: ohne Profil kein Assistent.", "Refused with 401: no assistant without a profile.")),
        ],
        "regeln": [
            [("Weg hinein", "Way in"), ("Wie geprüft", "How checked"), ("Was er erreicht", "What it reaches")],
            [("Browser mit Profil", "Browser with profile"), ("signiertes Cookie, Sitzung in der Liste", "signed cookie, session in the list"),
             ("alles des Profils", "everything of the profile")],
            [("Admin", "Admin"), ("Passwort-Cookie oder HTTP Basic", "password cookie or HTTP Basic"),
             ("Admin-Seiten; HTTP Basic nur ohne zweiten Schritt", "admin pages; HTTP Basic only without a second step")],
            [("Geräteschlüssel ohne Bereich", "Device key without scope"), ("Hash des Schlüssels", "hash of the key"),
             ("Assistent des Profils, keine Verbindungen oder Sicherheit ändern", "the profile's assistant, no changes to connections or security")],
            [("Geräteschlüssel mit Bereich", "Device key with scope"), ("Hash, Pfad, Schalter", "hash, path, switch"),
             ("nur die Pfade seines Bereichs", "only the paths of its scope")],
            [("Gast", "Guest"), ("nur mit Assistent ohne Passwort", "only with assistant without password"),
             ("Frage und Antwort, kein Werkzeug", "question and answer, no tool")],
        ],
        "zahlen": [
            ("{guard.MAX_FAILS}", ("Fehlversuche je Adresse in {guard.WINDOW|min} Minuten bis zur Sperre",
                                   "wrong attempts per address in {guard.WINDOW|min} minutes until the lock"), "guard.MAX_FAILS"),
            ("{guard.MAX_NAME_FAILS}", ("Fehlversuche je Name in {guard.WINDOW|min} Minuten bis zur Sperre",
                                        "wrong attempts per name in {guard.WINDOW|min} minutes until the lock"), "guard.MAX_NAME_FAILS"),
            ("{guard.LOCK_FIRST} s", ("erste Sperre, jede weitere doppelt so lang bis {guard.LOCK_MAX|min} Minuten",
                                      "first lock, each further one twice as long up to {guard.LOCK_MAX|min} minutes"), "guard.LOCK_FIRST"),
            ("{guard.DAY_FAILS}", ("Fehlversuche je Name in 24 Stunden höchstens", "wrong attempts per name in 24 hours at most"), "guard.DAY_FAILS"),
            ("{guard.RATE.chat.1}", ("Chat-Anfragen je Minute für ein Profil", "chat requests per minute for a profile"), "guard.RATE"),
            ("{guard.BUSY.chat}", ("gleichzeitige Plätze für Gäste", "places at once for guests"), "guard.BUSY"),
            ("{profiles.SESSION_DAYS}", ("Tage höchstens für eine Anmeldung im Browser", "days at most for a sign-in in the browser"), "profiles.SESSION_DAYS"),
        ],
        "einstellen": [
            ("Einstellungen → Sicherheit → Assistent ohne Passwort: Gäste dürfen fragen (Standard aus).",
             "Settings → Security → Assistant without password: guests may ask (default off)."),
            ("Einstellungen → Sicherheit → Anmeldung im Browser: wie viele Tage ohne Nutzung ein Profil angemeldet bleibt.",
             "Settings → Security → Sign-in in the browser: how many days without use a profile stays signed in."),
            ("Funktionen → Wer darf was: eine Funktion für einzelne Profile sperren.",
             "Features → Who may do what: block a function for single profiles."),
            ("Ich → Sicherheit: der zweite Schritt eines Profils.", "Me → Security: a profile's second step."),
        ],
        "sehen": [
            ("Zustand → Live: unter Eingang angenommene Zugriffe aus dem Internet und abgewiesene Anmeldungen.",
             "Status → Live: under Eingang accepted access from the internet and refused logins."),
            ("Logs → Admin-Protokoll: Anmeldungen, Fehlversuche und Sperren.", "Logs → Admin log: logins, wrong attempts and locks."),
            ("Ich → Sicherheit: die letzten Anmeldungen des eigenen Profils.", "Me → Security: the latest logins of the own profile."),
        ],
        "mehr": [
            (("Hinter einem Proxy", "Behind a proxy"), [
                ("X-Forwarded-For zählt nur von einem eingetragenen Proxy (oder einem auf dem Spark selbst, solange "
                 "keiner eingetragen ist). Sonst könnte jedes Gerät behaupten, eine andere Adresse zu sein, und die "
                 "Sperre umgehen.",
                 "X-Forwarded-For only counts from a listed proxy (or one on the Spark itself while none is listed). "
                 "Otherwise any device could claim another address and get around the lock."),
            ]),
            (("Abmelden", "Logging out"), [
                ("Ein abgemeldetes Cookie wird auch auf dem Server ungültig, eine Kopie davon geht nicht mehr. "
                 "Beim Admin gilt das für jede Kopie derselben Anmeldung.",
                 "A logged-out cookie becomes invalid on the server too, a copy of it no longer works. For the admin "
                 "this holds for every copy of the same login."),
            ]),
        ],
        "code": [
            ("guard.check", ("Sperre vor dem Prüfen", "lock before checking")),
            ("guard.failed", ("Fehlversuch zählen, sperren", "count a wrong attempt, lock")),
            ("guard.succeeded", ("Zähler löschen, Browser merken", "clear the counter, remember the browser")),
            ("account.profile_login", ("Anmeldung eines Profils", "a profile's login")),
            ("account.second_step", ("Code oder Passkey", "code or passkey")),
            ("core.is_main_admin", ("Admin per Cookie oder HTTP Basic", "admin by cookie or HTTP Basic")),
            ("profiles.current", ("das Profil hinter einer Anfrage", "the profile behind a request")),
            ("profiles._cookie_user", ("Cookie prüfen", "check a cookie")),
            ("core.assistant", ("Profil, Gastzugang oder Admin", "profile, guest access or admin")),
            ("guard.limit", ("Rate-Limit je Minute", "rate limit per minute")),
            ("guard.Slot", ("Plätze für Gäste", "places for guests")),
            ("features.reason", ("warum eine Funktion nicht geht", "why a function is not available")),
        ],
        "tests": ["test_panel", "test_features", "test_rechte_sofort", "test_passkey", "test_coadmin"],
        "heute": [("door_in", ("von außen angenommen", "accepted from outside")), ("door_out", ("abgewiesen", "refused"))],
    },

    # ------------------------------------------------------------------ vorbereiten (chat_turn.prepare, klaeren.py)
    "vorbereiten": {
        "stand": "27c8c48c18",
        "bezug": {
            "klaeren.MAX_BUTTONS": ["s7"], "chat_turn.prepare": ["s1", "s13"], "chat_turn.shared_stranger": ["s3"],
            "chat.left_out": ["s2", "s4"], "notaus.locked_tools": ["s11"], "chat_turn.notaus_note": ["s8", "s11"],
            "regeln": ["s10", "s11"], "regel:Gast oder unbekannte Stimme am Lautsprecher": ["s3"],
        },
        "kurz": ("chat_turn.prepare macht aus einer Chat-Anfrage einen fertigen Gesprächszug, bevor das Sprachmodell "
                 "gefragt wird: wer spricht und was diese Person darf, der Systemprompt, Antworten auf Rückfragen und "
                 "Vorschläge, die Sperren nach fremdem Text und die Liste der angebotenen Werkzeuge.",
                 "chat_turn.prepare turns a chat request into a finished turn before the language model is asked: who "
                 "speaks and what that person may do, the system prompt, answers to questions back and proposals, the "
                 "locks after outside text and the list of offered tools."),
        "warum": ("Das Modell soll nur sehen, was es in diesem Zug wirklich darf. Alles, was entscheidet (Rechte, "
                  "Sperren, ein „Ja“ zu einem Vorschlag, die Auswahl bei einer Rückfrage), macht das Panel hier mit "
                  "festen Regeln; das Modell sagt danach nur das Ergebnis.",
                  "The model should only see what it may really use in this turn. Everything that decides (rights, "
                  "locks, a „yes“ to a proposal, the choice after a question back) the panel does here by fixed rules; "
                  "the model only says the result afterwards."),
        "ablauf": [
            S("s1", "start", ("Nachrichten lesen", "Read the messages"),
              ("nur Text · je {chat.MAX_TURN_CHARS} Zeichen", "text only · {chat.MAX_TURN_CHARS} characters each"),
              ("Übernommen werden nur Textnachrichten von Nutzer und Assistent, jede auf {chat.MAX_TURN_CHARS} "
               "Zeichen gekürzt. Eine Antwort, die der Browser als aus Mail oder fremdem Text gemacht markiert hat, "
               "behält diese Marke.",
               "Only text messages of user and assistant are taken, each cut at {chat.MAX_TURN_CHARS} characters. An "
               "answer the browser marked as made from mail or outside text keeps that mark."),
              ("stop", ("leer", "empty"), ("Keine Nachricht (400)", "No message (400)"))),
            S("s2", "schritt", ("Verlauf kürzen, Sperre übernehmen", "Trim history, carry the lock"),
              ("chat.trim_history", "chat.trim_history"),
              ("Der Verlauf wird auf sein Budget gekürzt. Steht eine Antwort aus fremdem Text unter den letzten drei "
               "Nachrichten, beginnt dieser Zug gesperrt; ältere werden gar nicht mehr mitgeschickt.",
               "The history is trimmed to its budget. If an answer from outside text is among the last three messages, "
               "this turn starts locked; older ones are not sent at all.")),
            S("s3", "frage", ("Gast oder fremde Stimme?", "Guest or unknown voice?"),
              ("kein Profil oder Lautsprecher erkennt die Stimme nicht", "no profile or the speaker does not know the voice"),
              ("Ohne Profil, oder am eigenen Lautsprecher, wenn die Spracherkennung nicht klar die Stimme des Profils "
               "gehört hat, gibt es nur Frage und Antwort: kein Werkzeug, kein Gedächtnis, kein Verlauf. Wessen Stimme "
               "es war, setzt nur das Panel selbst, nie die Anfrage.",
               "Without a profile, or at an own speaker when speech recognition did not clearly hear the profile's "
               "voice, there is only question and answer: no tool, no memory, no history. Whose voice it was only the "
               "panel itself sets, never the request."),
              ("info", "ja", ("nur Frage und Antwort", "question and answer only"))),
            S("s4", "schritt", ("Weiche liest die Frage", "The switch reads the question"),
              ("intent.classify_cfg", "intent.classify_cfg"),
              ("Feste Regeln ordnen die eigene letzte Nachricht einer Gruppe zu. Eine neue eigene Bitte, die nicht auf "
               "die Antwort aus fremdem Text zurückzeigt, lässt diese Antwort und ihre Sperre weg. Erkennt keine Regel "
               "die Frage, kann das Modell parallel einmal aus einer festen Liste wählen (wenn der Admin das anhat). "
               "Eine Folgefrage wie „Und morgen?“ übernimmt die Gruppe der eigenen Frage davor (intent.follow_up); "
               "Hinweiswörter geben ihre Gruppen dazu, auch neben der Wahl des Modells.",
               "Fixed rules put the own latest message into a group. A new own request that does not point back at the "
               "answer from outside text leaves that answer and its lock out. If no rule knows the question, the model "
               "may pick once from a fixed list in parallel (when the admin has that on). A follow-up like „And "
               "tomorrow?“ takes the group of the own question before (intent.follow_up); hint words add their groups, "
               "also beside the model's pick.")),
            S("s5", "schritt", ("Systemprompt bauen", "Build the system prompt"),
              ("Admin-Text, Zeit, Länge, Stil, Kanal", "admin text, time, length, style, channel"),
              ("Der Systemprompt des Admins, dazu Länge und Stil des Profils und ein Hinweis je Kanal (Uhr, Siri, "
               "Lautsprecher, Telegram, App, Browser). Mit „Schneller Antwortbeginn“ geht, was nur für diesen Zug "
               "gilt, mit der Frage statt in den Systemprompt, damit der Server ihn aus dem Cache liest.",
               "The admin's system prompt, plus the profile's length and style and a note per channel (watch, Siri, "
               "speaker, Telegram, app, browser). With „Fast answer start“ what holds for this turn only goes with the "
               "question instead of the system prompt, so the server reads it from its cache.")),
            S("s6", "frage", ("Fester Satz?", "Fixed sentence?"),
              ("Rolle · Notaus · Problem melden · Bewertung", "role · kill switch · report · rating"),
              ("Sätze wie „Spark Notaus“, „Problem melden: …“ oder „Das war falsch“ führt das Panel selbst aus, nur aus "
               "den eigenen Worten des Profils und nie über MCP. Das Modell sagt nur das Ergebnis und bekommt in "
               "diesem Zug kein Werkzeug.",
               "Sentences like „Spark Notaus“, „report a problem: …“ or „that was wrong“ the panel carries out itself, "
               "only from the profile's own words and never over MCP. The model only says the result and gets no tool "
               "in this turn."),
              ("info", "ja", ("Panel führt aus, kein Werkzeug", "panel carries out, no tool"))),
            S("s7", "frage", ("Antwort auf eine Rückfrage?", "Answer to a question back?"),
              ("klaeren.answer", "klaeren.answer"),
              ("Hat das Panel gefragt, welches Gerät gemeint ist, gilt als Antwort ein Knopf, eine Zahl oder der Name, "
               "nur im selben Gespräch, vom eigenen Profil und innerhalb von {klaeren.ASK_SECONDS|min} Minuten. "
               "„Keins davon“ bringt die ganze Liste, „Nein, den anderen“ korrigiert die letzte Wahl. Das Panel führt "
               "die Wahl aus und bietet an, sie sich zu merken; ein „Ja“ dazu zählt {klaeren.REMEMBER_SECONDS|min} "
               "Minuten.",
               "If the panel asked which device is meant, a button, a number or the name counts as the answer, only in "
               "the same conversation, from the own profile and within {klaeren.ASK_SECONDS|min} minutes. „None of "
               "these“ brings the whole list, „No, the other one“ corrects the last choice. The panel carries out the "
               "choice and offers to remember it; a „yes“ to that counts for {klaeren.REMEMBER_SECONDS|min} minutes."),
              ("info", "ja", ("Panel führt die Wahl aus", "panel carries out the choice"))),
            S("s8", "frage", ("Notaus oder Mein Notaus?", "Kill switch or my kill switch?"),
              ("ab Stufe {notaus.STAGE.aktion} keine Aktion", "from stage {notaus.STAGE.aktion} no action"),
              ("Ab Notaus-Stufe {notaus.STAGE.aktion} oder mit dem eigenen Notaus des Profils werden alle wartenden "
               "Vorschläge verworfen; kein „Ja“ führt etwas aus. Lesen und Antworten gehen weiter.",
               "From kill switch stage {notaus.STAGE.aktion} or with the profile's own kill switch every waiting "
               "proposal is dropped; no „yes“ carries anything out. Reading and answering go on."),
              ("info", "ja", ("nur lesen, kein Ja", "read only, no yes"))),
            S("s9", "schritt", ("Ja zu einem Vorschlag", "Yes to a proposal"),
              ("Kalender, Postfach, Listen, Gedächtnis", "calendar, mailbox, lists, memory"),
              ("Wartet ein Vorschlag aus diesem Gespräch (ein Termin, eine Mail-Änderung, ein Listeneintrag, eine "
               "Korrektur), entscheidet das Panel über das „Ja“. Ein Ja bestätigt genau eine Sache; jede Antwort "
               "erledigt alle anderen wartenden Vorschläge dieses Gesprächs.",
               "If a proposal of this conversation waits (an appointment, a mail change, a list entry, a correction), "
               "the panel decides on the „yes“. One yes confirms exactly one thing; every answer settles all other "
               "waiting proposals of this conversation.")),
            S("s10", "schritt", ("Werkzeuge nach Rechten", "Tools by rights"),
              ("features.allowed je Gruppe", "features.allowed per group"),
              ("Jede Werkzeuggruppe kommt nur mit Schalter des Admins, Freigabe für das Profil und den eigenen Daten "
               "dazu: Suche, Gedächtnis, Verlauf, Dokumente, Smart Home, Erinnerungen, Kalender, Mail. Telegram, die "
               "iPhone-App und CarPlay können das nur enger machen, nie weiter. Eine fremde erkannte Stimme an diesem "
               "Gerät bekommt nichts Persönliches.",
               "Each tool group comes only with the admin's switch, the release for the profile and its own data: "
               "search, memory, history, documents, smart home, reminders, calendar, mail. Telegram, the iPhone app "
               "and CarPlay can only make it narrower, never wider. Another recognized voice at this device gets "
               "nothing personal.")),
            S("s11", "frage", ("Etwas nimmt Werkzeuge weg?", "Something takes tools away?"),
              ("Notaus · MCP · Bild · Gast", "kill switch · MCP · picture · guest"),
              ("Der Notaus nimmt Werkzeuge ins Internet oder ändernde weg, „Spark fragen“ über MCP behält nur die "
               "Werkzeuge der Verbindung, ein Bild oder ein fester Satz lässt keines übrig. Für einen Gast wird die "
               "Liste noch einmal geleert, egal was sie gefüllt hat.",
               "The kill switch takes away tools to the internet or that change things, „Ask Spark“ over MCP keeps "
               "only the connection's tools, a picture or a fixed sentence leaves none. For a guest the list is "
               "emptied once more, whatever filled it."),
              ("info", "ja", ("weniger oder keine Werkzeuge", "fewer or no tools"))),
            S("s12", "schritt", ("Weiche grenzt ein", "The switch narrows"),
              ("intent.narrow · nie mehr als die Rechte", "intent.narrow · never more than the rights"),
              ("Mit „Gezielte Werkzeugwahl“ bleibt nur die Gruppe der Frage übrig. Danach entscheidet das Panel, ob "
               "erst lokal gesucht wird, ob es ein eindeutiges Abrufen selbst macht und welches Werkzeug die erste "
               "Runde rufen muss.",
               "With „Targeted tool choice“ only the question's group stays. Then the panel decides whether to search "
               "locally first, whether it does a clear fetch itself and which tool the first round must call.")),
            S("s13", "ende", ("Gesprächszug fertig", "Turn ready"),
              ("an chat._answer", "to chat._answer"),
              ("Der Systemprompt steht vorn, dazu die Werkzeuge und die Sperrregel. Der Notaus wird bei jedem "
               "Werkzeugaufruf neu gelesen: wird er während einer Antwort ausgelöst, hält er den nächsten Aufruf an.",
               "The system prompt goes first, with the tools and the lock rule. The kill switch is read again for every "
               "tool call: triggered during an answer, it holds the next call off.")),
        ],
        "beispiele": [
            (("Gast fragt nach dem Wetter", "Guest asks for the weather"),
             ["s1", "s2", "s3", "s3!", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s11!", "s13"],
             ("Antwort ohne Werkzeug: Gäste bekommen nur Frage und Antwort.", "Answer without a tool: guests only get question and answer.")),
            (("„Das zweite“ nach einer Rückfrage", "„The second“ after a question back"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s7!", "s8", "s9", "s10", "s11", "s12", "s13"],
             ("Das Panel schaltet das gewählte Gerät; das Modell sagt nur das Ergebnis.",
              "The panel switches the chosen device; the model only says the result.")),
            (("Notaus Stufe 2, Frage nach Terminen", "Kill switch stage 2, asking for appointments"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!", "s9", "s10", "s11", "s11!", "s12", "s13"],
             ("Nur lesende Werkzeuge; Termine eintragen wird nicht angeboten.", "Only reading tools; adding appointments is not offered.")),
        ],
        "regeln": [
            [("Wer spricht", "Who speaks"), ("Werkzeuge", "Tools"), ("Persönliches", "Personal data"), ("Ja zu Vorschlägen", "Yes to proposals")],
            [("Profil, eigener Login oder Schlüssel", "Profile, own login or key"), ("nach Freigaben", "by releases"), "✓", "✓"],
            [("andere erkannte Stimme an diesem Gerät", "another recognized voice at this device"), ("allgemeine", "general ones"), "✕", "✕"],
            [("Spark fragen über MCP", "Ask Spark over MCP"), ("nur die der Verbindung", "only the connection's"),
             ("nur lesen, kein Gedächtnis, keine Mail", "read only, no memory, no mail"), "✕"],
            [("Gast oder unbekannte Stimme am Lautsprecher", "Guest or unknown voice at a speaker"), "✕", "✕", "✕"],
        ],
        "zahlen": [
            ("{chat.MAX_TURN_CHARS}", ("Zeichen höchstens je Nachricht", "characters at most per message"), "chat.MAX_TURN_CHARS"),
            ("{klaeren.ASK_SECONDS|min}", ("Minuten gilt eine Auswahl bei einer Rückfrage", "minutes a choice answers a question back"), "klaeren.ASK_SECONDS"),
            ("{klaeren.REMEMBER_SECONDS|min}", ("Minuten wartet „Soll ich mir das merken?“", "minutes „Shall I remember that?“ waits"), "klaeren.REMEMBER_SECONDS"),
            ("{klaeren.MAX_BUTTONS}", ("Knöpfe höchstens bei einer Rückfrage", "buttons at most for a question back"), "klaeren.MAX_BUTTONS"),
            ("{notaus.STAGE.aktion}", ("Notaus-Stufe ohne Aktionen", "kill switch stage without actions"), "notaus.STAGE"),
        ],
        "einstellen": [
            ("Funktionen → Wer darf was: was ein einzelnes Profil nicht bekommt.", "Features → Who may do what: what a single profile does not get."),
            ("Funktionen → Rückfrage statt Raten: das Panel fragt nach, statt zu raten (Standard aus).",
             "Features → Ask instead of guessing: the panel asks instead of guessing (default off)."),
            ("Funktionen → Weiche: die festen Regeln, die die Werkzeuge eingrenzen.",
             "Features → Switch: the fixed rules that narrow the tools."),
        ],
        "sehen": [
            ("Logs → Anfragen: je Frage Gruppe, Werkzeuge „x von y“, Pflichtwerkzeug und Sperre, ohne Inhalt.",
             "Logs → Requests: per question group, tools „x of y“, required tool and lock, without content."),
            ("Zustand → Logs: Zeilen wie „weiche: Absicht …“, „chat: web search …“ oder „notaus: … Werkzeuge nicht angeboten“.",
             "Status → Logs: lines like „weiche: Absicht …“, „chat: web search …“ or „notaus: … Werkzeuge nicht angeboten“."),
        ],
        "code": [
            ("chat_turn.prepare", ("der ganze Ablauf", "the whole way")),
            ("chat_turn.shared_stranger", ("fremde Stimme am Lautsprecher", "unknown voice at a speaker")),
            ("chat.trim_history", ("Verlauf kürzen", "trim the history")),
            ("chat.left_out", ("Antworten aus fremdem Text weglassen", "leave out answers from outside text")),
            ("intent.classify_cfg", ("feste Regeln der Weiche", "the switch's fixed rules")),
            ("klaeren.answer", ("Antwort auf eine Rückfrage", "answer to a question back")),
            ("features.allowed", ("Freigabe je Funktion", "release per function")),
            ("notaus.locked_tools", ("was der Notaus wegnimmt", "what the kill switch takes away")),
            ("intent.narrow", ("Werkzeuge eingrenzen", "narrow the tools")),
            ("chat_turn.notaus_note", ("Satz für das Modell bei Notaus", "sentence for the model with the kill switch")),
        ],
        "tests": ["test_klaeren", "test_features", "test_notaus", "test_hardening", "test_weiche"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Antwort bauen (chat._answer)
    "weiche": {
        "stand": "9885fa671a",
        "bezug": {
            "intent.GROUPS": ["s4", "s6"], "intent_bench.BENCH": ["s4", "s5"], "intent_alltag.ALLTAG": ["s14"],
            "weiche.KEEP_VERSIONS": ["s4"], "intent.Route": ["s6"], "intent.follow_up": ["s8"],
            "intent.ask_model": ["s10"], "intent.pick_in_time": ["s10"], "intent.lean": ["s12"],
            "weiche.count": ["s14"], "weiche.trace": ["s14"], "intent_alltag.measure": ["s14"], "regeln": ["s9"],
            "regel:Modell ordnet ein": ["s10"], "regel:Knapp": ["s12"],
            "regel:Einordnung mit Wahrscheinlichkeit": ["s10"],
        },
        "kurz": ("Die Weiche ordnet die eigene letzte Nachricht einer Gruppe zu (Smart Home, Kalender, Wetter, Mail und "
                 "so weiter, heute {intent.GROUPS|anzahl} Gruppen) und grenzt damit die Werkzeuge ein, die das "
                 "Sprachmodell in diesem Zug sieht. Sie arbeitet mit festen Wortlisten; das Modell darf höchstens "
                 "einmal aus einer festen Liste wählen, wenn keine Regel passt, und auch das kann nur eingrenzen.",
                 "The switch puts the own latest message into a group (smart home, calendar, weather, mail and so on, "
                 "today {intent.GROUPS|anzahl} groups) and so narrows the tools the language model sees in this turn. "
                 "It works with fixed word lists; the model may at most pick once from a fixed list when no rule "
                 "fits, and that too can only narrow."),
        "warum": ("Wenige passende Werkzeuge machen das Modell schneller und treffsicherer: es liest weniger und greift "
                  "seltener daneben. Weil die Weiche nur wegnimmt, was die Rechte und Sperren übrig gelassen haben, "
                  "kann ein falsch zugeordneter Satz nie mehr erlauben, höchstens ein Werkzeug fehlen lassen.",
                  "Few fitting tools make the model faster and more accurate: it reads less and misses less often. "
                  "Because the switch only takes away from what rights and locks left, a wrongly sorted sentence can "
                  "never allow more, at most leave a tool out."),
        "ablauf": [
            S("s1", "start", ("Nur die eigene Nachricht", "Only the own message"),
              ("intent.classify_cfg", "intent.classify_cfg"),
              ("Gelesen wird nur die letzte Nachricht der Person selbst, nie eine Antwort davor, fremder Text oder was "
               "das Modell geschrieben hat. Dazu kommen die Wörter, die der Admin unter Funktionen → Weiche gespeichert "
               "hat.",
               "Only the person's own latest message is read, never an answer before, outside text or what the "
               "model wrote. The words the admin saved under Features → Switch are added.")),
            S("s2", "frage", ("Nur Plaudern?", "Only small talk?"),
              ("„Danke“, „Hallo“, „Gute Nacht“", "„thanks“, „hello“, „good night“"),
              ("Ist der ganze Satz ein Gruß oder Dank, heißt die Gruppe „plaudern“. Die Antwort bekommt dann gar kein "
               "Werkzeug.",
               "If the whole sentence is a greeting or thanks, the group is „plaudern“ (small talk). The answer then "
               "gets no tool at all."),
              ("ok", "ja", "s14")),
            S("s3", "frage", ("Frage zum Spark?", "Question about the Spark?"),
              ("vor allen anderen Gruppen", "before every other group"),
              ("„Wie verbinde ich Home Assistant?“ oder „Schalte die Websuche ein“ fragen nach dem Spark selbst, nicht "
               "nach einem Gerät oder einer Suche: Gruppe „spark“. Eine Frage zu Wörtern oder Sprachen zählt nie "
               "dazu. Wurde auf einer Seite des Panels „Frag Spark“ benutzt, gilt dieselbe Gruppe nach fester Regel "
               "über den Ort der Frage.",
               "„How do I connect Home Assistant?“ or „Switch on web search“ ask about the Spark itself, not about a "
               "device or a search: group „spark“. A question about words or languages never counts. When „Ask "
               "Spark“ was used on a page of the panel, the same group holds by a fixed rule about where it was "
               "asked."),
              ("ok", "ja", "s9")),
            S("s4", "schritt", ("Wörter je Gruppe", "Words per group"),
              ("eingebaut · Pflicht-Wörter · eigene Wörter", "built in · must words · own words"),
              ("Jede Gruppe hat ihre eingebaute Wortliste (Licht, Termin, Postfach, Schirm …). Ein Schaltwort ohne "
               "Gerät („Alles aus“) zählt nur als ganzer Befehl. Die Pflicht-Wörter des Admins und seine eigenen "
               "Wörter je Gruppe (höchstens {intent.MAX_ROUTE_WORDS}, nur ganze Wörter) finden eine Gruppe "
               "zusätzlich, ersetzen aber nichts.",
               "Each group has its built-in word list (light, appointment, mailbox, umbrella …). A switching word "
               "without a device („all off“) only counts as a whole command. The admin's must words and own words "
               "per group (at most {intent.MAX_ROUTE_WORDS}, whole words only) find a group as well, but replace "
               "nothing.")),
            S("s5", "schritt", ("Vorrang zwischen Gruppen", "Priority between groups"),
              ("feste Regeln · dann „Nicht bei“", "fixed rules · then „Not with“"),
              ("Treffen mehrere Gruppen, räumen feste Regeln auf: Wetter, Liste, Nachricht, Dokument und „Dokument "
               "erstellen“ gehen vor Smart Home, wenn kein Schaltbefehl dabei ist; Pakete vor Mail; „Habe ich neue "
               "Nachrichten?“ ist eine Nachricht, „Was gibt es in den Nachrichten?“ die Websuche; ein Auftrag, der "
               "regelmäßig wiederkommt oder etwas beobachtet, ist ein Agent; eine Frage zu Sprache oder Natur ist nie "
               "ein Gerät. Zuletzt nehmen die „Nicht bei“-Wörter des Admins Gruppen wieder heraus.",
               "When several groups match, fixed rules tidy up: weather, list, message, document and „create "
               "document“ come before smart home when there is no switching command; parcels before mail; „Do I have "
               "new messages?“ is a message, „What is in the news?“ the web search; a job that comes back regularly "
               "or watches something is an agent; a question about language or nature is never a device. Last, the "
               "admin's „Not with“ words take groups out again.")),
            S("s6", "frage", ("Gruppe erkannt?", "Group recognized?"),
              ("eine, zwei oder mehr", "one, two or more"),
              ("Eine Gruppe oder höchstens {intent.MAX_MIXED} gelten als klar und grenzen ein. Mehr Gruppen auf "
               "einmal sind nicht klar genug: dann bleiben alle Werkzeuge.",
               "One group or at most {intent.MAX_MIXED} count as clear and narrow. More groups at once are not "
               "clear enough: then every tool stays."),
              ("ok", "ja", "s9")),
            S("s7", "schritt", ("Hinweiswörter merken", "Note hint words"),
              ("intent.hints_of · grenzen nie ein", "intent.hints_of · never narrow"),
              ("Erkennt keine Regel eine Gruppe sicher, sucht die Weiche schwächere Hinweiswörter: „gießen“ deutet "
               "aufs Wetter, „Freitag“ auf den Kalender. Ein Hinweis grenzt nie ein; er sorgt nur dafür, dass die "
               "Werkzeuge seiner Gruppe bleiben, wenn später eingegrenzt wird.",
               "If no rule recognizes a group for sure, the switch looks for weaker hint words: „water the plants“ "
               "points to the weather, „Friday“ to the calendar. A hint never narrows; it only makes sure its group's "
               "tools stay when something narrows later.")),
            S("s8", "frage", ("Folgefrage?", "Follow-up?"),
              ("„Und morgen?“", "„And tomorrow?“"),
              ("Ist die Nachricht kurz (höchstens {intent.FOLLOW_MAX} Zeichen), zeigt zurück („und“, „das“, „es“) "
               "und hatte die eigene Frage direkt davor eine klare Gruppe, gilt diese Gruppe wieder. Es zählt nur die "
               "eigene Frage, nie die Antwort. Im Journal steht „weiche: Folgefrage“.",
               "If the message is short (at most {intent.FOLLOW_MAX} characters), points back („and“, „that“, „it“) "
               "and the own question just before had a clear group, that group holds again. Only the own question "
               "counts, never the answer. The journal says „weiche: Folgefrage“."),
              ("info", "ja", ("Gruppe der Frage davor", "group of the question before"))),
            S("s9", "frage", ("Gezielte Werkzeugwahl an?", "Targeted tool choice on?"),
              ("Schalter des Admins, Freigabe des Profils", "admin's switch, profile release"),
              ("Nur mit diesem Schalter grenzt die Weiche ein, und nicht bei einem Bild oder einem direkten "
               "Smart-Home-Befehl. Ohne ihn bleibt die Gruppe nur für Journal und Statistik; das Modell sieht alle "
               "Werkzeuge, die die Rechte erlauben.",
               "Only with this switch does the switch narrow, and not with a picture or a direct smart home command. "
               "Without it the group only goes to the journal and statistics; the model sees every tool the rights "
               "allow."),
              ("ok", "nein", "s14")),
            S("s10", "frage", ("Modell ordnet ein?", "Model sorts?"),
              ("nur ohne Gruppe · „Modell ordnet ein“", "only without a group · „the model sorts“"),
              ("Hat keine Regel eine Gruppe gefunden und steht „Fragen, die keine Regel erkennt“ auf „Modell“, wählt "
               "das Sprachmodell einmal eine Gruppe aus der festen Liste (nur JSON, nur die eigene Nachricht). Die "
               "Frage läuft schon ab dem Beginn der Vorbereitung nebenher; gewartet wird höchstens "
               "{intent.ASK_TIMEOUT} Sekunden, mit „Schneller Antwortbeginn“ nur {intent.CACHED_WAIT|ms} "
               "nach der Vorbereitung. Mit der Einordnung mit Wahrscheinlichkeit zählt die Wahl erst ab der "
               "Schwelle (Standard {systemone.ROUTE_MIN|prozent}). Die Hinweis-Gruppen bleiben neben der Wahl.",
               "If no rule found a group and „Questions no rule recognizes“ is set to the model, the language model "
               "picks one group from the fixed list once (JSON only, only the own message). The question already "
               "runs beside the preparation from its start; the wait is at most {intent.ASK_TIMEOUT} seconds, with "
               "„Fast answer start“ only {intent.CACHED_WAIT|ms} after the preparation. With classification "
               "with probabilities the pick only counts from the threshold (default {systemone.ROUTE_MIN|prozent}). The hint "
               "groups stay beside the pick."),
              ("info", "ja", ("Grund „Modell“", "reason „Modell“"))),
            S("s11", "schritt", ("Eingrenzen", "Narrow"),
              ("intent.narrow · nie mehr als vorher", "intent.narrow · never more than before"),
              ("Bei einer klaren Gruppe bleiben ihre Werkzeuge, dazu immer {intent.NARROW_KEEP|anzahl} feste "
               "(sich etwas merken, eigene Dokumente, PC), die Werkzeuge der Hinweise, die zusätzlichen Werkzeuge des "
               "Admins für diese Gruppe (höchstens {intent.MAX_EXTRA}) und was die eigenen Worte ausdrücklich "
               "nennen („aufs reMarkable“). Alles nur, soweit schon angeboten. Ist von der Gruppe nichts angeboten "
               "oder steht die Gruppe auf „nicht eingrenzen“, bleiben alle.",
               "With a clear group its tools stay, plus always {intent.NARROW_KEEP|anzahl} fixed ones (remembering "
               "something, own documents, PC), the hints' tools, the admin's extra tools for this group (at most "
               "{intent.MAX_EXTRA}) and what the own words name explicitly („onto the reMarkable“). All only as far "
               "as already offered. If nothing of the group is offered or the group is set to „do not narrow“, all "
               "stay.")),
            S("s12", "frage", ("Knapp?", "Lean?"),
              ("unklar · „Knapp“ · kein Pflicht-Werkzeug", "unclear · „Lean“ · no required tool"),
              ("Bleibt die Frage ohne Gruppe, steht die Einstellung auf „Knapp“ und verlangt kein Pflicht-Wort ein "
               "Werkzeug, bekommt das Modell nur die kurze Liste: Websuche, Wikipedia, Archiv, frühere Gespräche, "
               "die festen Werkzeuge und die Werkzeuge der Hinweis-Gruppen. Es liest weniger und beginnt früher.",
               "If the question stays without a group, the setting is „Lean“ and no must word requires a tool, the "
               "model only gets the short list: web search, Wikipedia, archive, earlier conversations, the fixed "
               "tools and the tools of the hint groups. It reads less and starts sooner."),
              ("info", "ja", ("kurze Liste", "short list"))),
            S("s13", "schritt", ("Erstes Werkzeug festlegen", "Fix the first tool"),
              ("intent.forced · intent.direct", "intent.forced · intent.direct"),
              ("Eine einzige klare Gruppe, ein Pflicht-Werkzeug und nur dieses aus der Gruppe angeboten: die erste "
               "Runde muss genau dieses rufen („Wie wird das Wetter?“). Ein kurzer, eindeutiger Lesesatz („Wie ist "
               "das Wetter heute?“) wird mit „Eindeutiges direkt abrufen“ vom Panel selbst abgerufen, für morgen "
               "und übermorgen mit dem Datum, das das Panel ausrechnet.",
               "One single clear group, one required tool and only that one of the group offered: the first round "
               "must call exactly that one („What will the weather be?“). A short, clear reading sentence („What is "
               "the weather today?“) is fetched by the panel itself with „Fetch clear questions directly“, for "
               "tomorrow and the day after with the date the panel works out.")),
            S("s14", "ende", ("Journal und Zählung", "Journal and count"),
              ("weiche: Absicht … · weiche-stats.json", "weiche: Absicht … · weiche-stats.json"),
              ("Jeder Zug schreibt eine Zeile „weiche: Absicht … | Grund … | Hinweis … | Werkzeuge x von y | Pflicht "
               "… | gesperrt … | eingrenzen an/aus“; ein Grundwort steht nur da, wenn es noch in der Nachricht "
               "steht. Gezählt werden je Tag und Gruppe nur Anzahlen ({weiche.KEEP_DAYS} Tage), nie ein Wort der "
               "Frage. Dann geht die Liste an die Antwort.",
               "Every turn writes a line „weiche: Absicht … | Grund … | Hinweis … | Werkzeuge x von y | Pflicht … | "
               "gesperrt … | eingrenzen an/aus“; a reason word only shows when it is still in the message. Per day "
               "and group only counts are kept ({weiche.KEEP_DAYS} days), never a word of the question. Then the "
               "list goes to the answer.")),
        ],
        "beispiele": [
            (("„Mach das Licht im Wohnzimmer aus“", "„Turn off the living room light“"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s9", "s10", "s11", "s12", "s13", "s14"],
             ("Gruppe smarthome (Wort „Licht“): das Modell sieht nur die Smart-Home-Werkzeuge und die festen.",
              "Group smarthome (word „Licht“): the model only sees the smart home tools and the fixed ones.")),
            (("„Und morgen?“ nach einer Wetterfrage", "„And tomorrow?“ after a weather question"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!", "s9", "s10", "s11", "s12", "s13", "s14"],
             ("Keine Regel greift, aber die Folgefrage übernimmt „wetter“: nur das Wetter-Werkzeug ist Pflicht.",
              "No rule fits, but the follow-up takes „wetter“: only the weather tool is required.")),
            (("„Muss ich die Pflanzen gießen?“ mit „Knapp“", "„Do I need to water the plants?“ with „Lean“"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12", "s12!", "s13", "s14"],
             ("Unklar, Hinweis „gießen“ → wetter: kurze Liste plus Wetter-Werkzeug.",
              "Unclear, hint „gießen“ → weather: short list plus the weather tool.")),
            (("„Danke!“", "„Thanks!“"), ["s1", "s2", "s2!", "s14"],
             ("Gruppe plaudern: Antwort ohne Werkzeug.", "Group small talk: answer without a tool.")),
        ],
        "regeln": [
            [("Fragen, die keine Regel erkennt", "Questions no rule recognizes"), ("Was das Modell sieht", "What the model sees"),
             ("Zeit", "Time")],
            [("Alle Werkzeuge (Standard)", "All tools (default)"), ("alles, was die Rechte erlauben", "everything the rights allow"),
             ("keine zusätzliche", "none added")],
            [("Modell ordnet ein", "the model sorts"), ("die gewählte Gruppe und die Hinweis-Gruppen", "the picked group and the hint groups"),
             ("eine kurze Modellfrage nebenher", "a short model question beside")],
            [("Knapp", "Lean"), ("kurze Liste und Hinweis-Gruppen", "short list and hint groups"), ("keine, beginnt früher", "none, starts sooner")],
            [("Einordnung mit Wahrscheinlichkeit", "Classification with probability"),
             ("die Gruppe erst ab der Schwelle", "the group only from the threshold"), ("eine kurze Einordnung nebenher", "a short classification beside")],
        ],
        "zahlen": [
            ("{intent.GROUPS|anzahl}", ("Gruppen der Weiche", "groups of the switch"), "intent.GROUPS"),
            ("{intent.MAX_MIXED}", ("Gruppen höchstens, die noch eingrenzen", "groups at most that still narrow"), "intent.MAX_MIXED"),
            ("{intent.FOLLOW_MAX}", ("Zeichen höchstens für eine Folgefrage", "characters at most for a follow-up"), "intent.FOLLOW_MAX"),
            ("{intent.ASK_TIMEOUT}", ("Sekunden höchstens für die Wahl des Modells", "seconds at most for the model's pick"), "intent.ASK_TIMEOUT"),
            ("{intent.CACHED_WAIT|ms}", ("Wartezeit mit „Schneller Antwortbeginn“", "waiting with „Fast answer start“"), "intent.CACHED_WAIT"),
            ("{systemone.ROUTE_MIN|prozent}", ("Standard-Schwelle der Einordnung", "default threshold of the classification"), "systemone.ROUTE_MIN"),
            ("{intent_bench.BENCH|anzahl}", ("eingebaute Testsätze", "built-in test sentences"), "intent_bench.BENCH"),
            ("{intent_alltag.ALLTAG|anzahl}", ("Alltagssätze zum Messen", "everyday sentences for measuring"), "intent_alltag.ALLTAG"),
            ("{weiche.KEEP_VERSIONS}", ("Versionen für Rückgängig", "versions for undo"), "weiche.KEEP_VERSIONS"),
        ],
        "einstellen": [
            ("Funktionen → Gezielte Werkzeugwahl: ohne diesen Schalter grenzt die Weiche nichts ein (Standard aus).",
             "Features → Targeted tool choice: without this switch the switch narrows nothing (default off)."),
            ("Funktionen → Weiche: eigene Wörter je Gruppe, „Nicht bei“, zusätzliche Werkzeuge, Gruppen ohne Eingrenzen, "
             "Pflicht-Wörter, eigene Testsätze und was Fragen bekommen, die keine Regel erkennt. Jede Änderung läuft "
             "vorher durch alle Testsätze; ändert sich einer, wird erst nach Bestätigung gespeichert. Rückgängig hält "
             "die letzten {weiche.KEEP_VERSIONS} Fassungen.",
             "Features → Switch: own words per group, „Not with“, extra tools, groups without narrowing, must words, "
             "own test sentences and what questions no rule recognizes get. Every change runs through all test "
             "sentences first; if one changes, it is saved only after confirming. Undo keeps the last "
             "{weiche.KEEP_VERSIONS} versions."),
            ("Funktionen → Eindeutiges direkt abrufen: kurze Lesefragen ruft das Panel selbst ab (Standard aus).",
             "Features → Fetch clear questions directly: the panel fetches short reading questions itself (default off)."),
        ],
        "sehen": [
            ("Funktionen → Weiche: „Satz ausprobieren“ zeigt den ganzen Weg eines Satzes ohne Modell; dazu Testsätze, "
             "Alltagsquote und Statistik (7 Tage, nur Anzahlen).",
             "Features → Switch: „Try a sentence“ shows the whole way of a sentence without the model; also test "
             "sentences, everyday score and statistics (7 days, counts only)."),
            ("Zustand → Logs: Zeilen „weiche: Absicht …“, „weiche: Folgefrage“, „weiche: Modell-Zuordnung …“ und "
             "„weiche: direkt abgerufen“.",
             "Status → Logs: lines „weiche: Absicht …“, „weiche: Folgefrage“, „weiche: Modell-Zuordnung …“ and "
             "„weiche: direkt abgerufen“."),
            ("Logs → Anfragen: je Frage Gruppe, Werkzeuge „x von y“ und was aus der Wahl des Modells wurde.",
             "Logs → Requests: per question group, tools „x of y“ and what became of the model's pick."),
        ],
        "mehr": [
            (("Alltagsquote", "Everyday score"), [
                ("Die Testsätze ({intent_bench.BENCH|anzahl}) halten jede gemeldete Fehlzuordnung fest und müssen alle "
                 "stimmen. Die Alltagssätze ({intent_alltag.ALLTAG|anzahl}) wurden nie zum Einstellen benutzt: sie messen, "
                 "wie viele richtig landen, von einem Hinweis geschützt werden, offen bleiben oder falsch landen. Ein "
                 "Selbsttest verbietet, dass richtig plus geschützt sinkt oder falsch steigt.",
                 "The test sentences ({intent_bench.BENCH|anzahl}) hold every reported wrong turn and must all pass. "
                 "The everyday sentences ({intent_alltag.ALLTAG|anzahl}) were never used for tuning: they measure how "
                 "many land right, are protected by a hint, stay open or land wrong. A self-test forbids right plus "
                 "protected going down or wrong going up."),
            ]),
            (("Werkzeugnamen", "Tool names"), [
                ("Überall, wo ein Werkzeug sichtbar wird, steht ein lesbarer Name aus einer Tabelle "
                 "({werkzeuge.NAMES|anzahl} Werkzeuge), zum Beispiel „Postfach-Überblick“ statt mail_tidy_overview.",
                 "Wherever a tool shows, a readable name comes from one table ({werkzeuge.NAMES|anzahl} tools), for "
                 "example „Mailbox overview“ instead of mail_tidy_overview."),
            ]),
        ],
        "code": [
            ("intent.classify", ("Gruppen nach festen Wörtern und Vorrang", "groups by fixed words and priority")),
            ("intent.Route", ("Gruppe, Grund, Hinweise; wann klar", "group, reason, hints; when clear")),
            ("intent.hints_of", ("Hinweiswörter", "hint words")),
            ("intent.follow_up", ("Folgefrage", "follow-up")),
            ("intent.ask_model", ("Wahl des Modells aus fester Liste", "the model's pick from a fixed list")),
            ("intent.pick_in_time", ("auf die Wahl warten oder abbrechen", "wait for the pick or stop it")),
            ("intent.narrow", ("Werkzeuge eingrenzen", "narrow the tools")),
            ("intent.lean", ("kurze Liste bei „Knapp“", "short list with „Lean“")),
            ("intent.forced", ("Pflicht für die erste Runde", "required first tool")),
            ("weiche.count", ("Statistik ohne Inhalt", "statistics without content")),
            ("weiche.trace", ("Satz ausprobieren", "try a sentence")),
            ("intent_alltag.measure", ("Alltagsquote", "everyday score")),
        ],
        "tests": ["test_intent", "test_intent_alltag", "test_weiche", "test_werkzeuge", "test_systemone"],
        "heute": [],
    },
    "antwort": {
        "stand": "952c4988c3",
        "bezug": {
            "chat.MAX_SAVES": ["s11"], "chat.LOOP_SAME": ["s11"], "chat._answer": ["s4", "s5", "s11"],
            "chat.split_sentences": ["s5"], "chat.said_key": ["s8"], "chat.no_code": ["s8"],
            "chat.loop_count": ["s11"], "answercheck.known": ["s6"], "answercheck.unsupported": ["s6"],
            "answercheck.fresh": ["s6"],
        },
        "kurz": ("Hier entsteht die Antwort: Das Panel fragt das Sprachmodell in Runden, lässt angebotene Werkzeuge "
                 "laufen, prüft jeden fertigen Satz mit festen Regeln und schickt Text und Ton als einen Strom ans Gerät. "
                 "Die Prüfungen entscheidet das Panel, nie das Modell.",
                 "This is where the answer is made: the panel asks the language model in rounds, runs offered tools, "
                 "checks every finished sentence by fixed rules and sends text and sound to the device as one stream. "
                 "The panel decides the checks, never the model."),
        "warum": ("Ein Sprachmodell erfindet gern Uhrzeiten, Beträge oder Taten („Licht ist an“), die nie passiert sind. "
                  "Gesprochen wirkt das wie eine Tatsache. Deshalb sagt das Panel nur Sätze, die zu dem passen, was "
                  "wirklich gelesen oder getan wurde, und beginnt trotzdem schnell zu sprechen.",
                  "A language model likes to make up times, amounts or deeds („the light is on“) that never happened. "
                  "Spoken, that sounds like a fact. So the panel only says sentences that fit what was really read or "
                  "done, and still starts speaking quickly."),
        "ablauf": [
            S("s1", "start", ("Frage kommt an", "Question arrives"),
              ("chat.chat → chat_turn.prepare", "chat.chat → chat_turn.prepare"),
              ("chat() prüft das Rate-Limit, setzt die Marke „Sprache läuft“ (Hintergrundarbeit wartet) und zeigt "
               "den anderen Geräten des Profils „antwortet gerade“. Dann bereitet chat_turn.prepare Rechte, Sperren, "
               "Systemprompt und die angebotenen Werkzeuge vor; _answer übernimmt.",
               "chat() checks the rate limit, sets the mark „speech is running“ (background work waits) and shows the "
               "profile's other devices „answering“. Then chat_turn.prepare works out rights, locks, system prompt and "
               "the offered tools; _answer takes over.")),
            S("s2", "schritt", ("Strom öffnen, Sofort-Satz", "Open the stream, instant sentence"),
              ("drei Aufgaben: Modell, Sprachausgabe, Brücke", "three tasks: model, speech output, bridge"),
              ("Zwei Warteschlangen verbinden alles: eine für die Ereignisse ans Gerät, eine für Sätze an die "
               "Sprachausgabe. Ist die Sofortige Rückmeldung frei, spielt sofort ein aufgenommener Satz (ohne GPU); "
               "bleibt die Antwort danach still, kommt einmal ein Brücken-Satz.",
               "Two queues connect everything: one for events to the device, one for sentences to speech output. When "
               "the instant acknowledgement is allowed, a recorded sentence plays at once (no GPU); if the answer then "
               "stays silent, one bridge sentence follows.")),
            S("s3", "schritt", ("Was das Panel selbst erledigt", "What the panel does itself"),
              ("Smart Home, Erst lokal, direkter Abruf", "smart home, local first, direct fetch"),
              ("Hat die Vorbereitung entschieden, dass das Panel selbst handelt (ein Schaltbefehl, Zustände lesen, "
               "„Erst lokal suchen“, ein eindeutiger Lesewunsch), läuft das jetzt. Das Ergebnis geht wie ein "
               "Werkzeug-Ergebnis an das Modell, fremder Text eingepackt als Daten.",
               "When the preparation decided that the panel acts itself (a switch command, reading states, „search "
               "locally first“, a clear reading request), it runs now. The result goes to the model like a tool "
               "result, outside text wrapped as data.")),
            S("s4", "schritt", ("Runde vorbereiten", "Prepare a round"),
              ("höchstens vier Werkzeug-Runden", "at most four tool rounds"),
              ("Angeboten wird die Liste ohne gesperrte, wegen Fehlern gestoppte oder zu oft genutzte Werkzeuge. "
               "Verlangt die Frage ein Werkzeug, muss das Modell eines wählen (tool_choice), mit eigener Temperatur. "
               "Die fünfte Runde hat keine Liste mehr: das Modell hört, dass es jetzt antworten soll.",
               "Offered is the list without locked tools, tools stopped after errors or used too often. When the "
               "question needs a tool, the model must choose one (tool_choice), with its own temperature. The fifth "
               "round has no list: the model is told to answer now.")),
            S("s5", "schritt", ("Streamen und in Sätze schneiden", "Stream and cut into sentences"),
              ("erster Satz ab {chat.FIRST_CUT} Zeichen am Komma", "first sentence cut at a comma after {chat.FIRST_CUT} characters"),
              ("Die Antwort kommt Stück für Stück. Denktext und als Text geschriebene Werkzeugaufrufe werden nie "
               "gezeigt oder gesprochen. split_sentences schneidet fertige Sätze ab („z. B.“ und „5. Oktober“ sind "
               "kein Satzende); ein langer erster Satz geht schon am Komma los, damit der erste Ton früh kommt.",
               "The answer comes piece by piece. Thinking and tool calls written as text are never shown or spoken. "
               "split_sentences cuts finished sentences off („z. B.“ and „5. Oktober“ are no sentence end); a long "
               "first sentence goes at a comma, so the first sound comes early.")),
            S("s6", "frage", ("Zahl ohne Beleg?", "Figure without proof?"),
              ("Antwort-Prüfung: Uhrzeit, Datum, Spielstand, Betrag", "answer check: time, date, score, amount"),
              ("Bei Datenfragen vergleicht answercheck jede Uhrzeit, jedes Datum, jeden Spielstand und Betrag im Satz "
               "mit allem, was das Modell bekommen hat. Nach einem Kalender-Abruf zählen nur Angaben aus dieser "
               "Antwort, nicht aus früheren; ein zitierter Termin-Titel muss im Ergebnis stehen.",
               "For data questions answercheck compares every time, date, score and amount in the sentence with "
               "everything the model was given. After a calendar read only figures from this answer count, not from "
               "earlier ones; a quoted appointment title must be in the result."),
              ("info", "ja", ("Satz fällt weg, am Ende ein ehrlicher Satz", "Sentence dropped, an honest sentence at the end"))),
            S("s7", "frage", ("Tat ohne Werkzeug?", "Deed without a tool?"),
              ("Taten prüfen", "check deeds"),
              ("Behauptet ein Satz eine Tat („ist jetzt an“, „habe eingetragen“), muss in dieser Antwort ein Werkzeug "
               "dieser Art geklappt haben (taten.check). Gilt nur, wenn ein änderndes Werkzeug angeboten war.",
               "When a sentence claims a deed („is on now“, „entered it“), a tool of that kind must have worked in this "
               "answer (taten.check). Only when a changing tool was offered."),
              ("info", "ja", ("Satz fällt weg, am Ende „hat nicht geklappt“", "Sentence dropped, „did not work“ at the end"))),
            S("s8", "schritt", ("Zeigen und sprechen", "Show and speak"),
              ("nie ein Satz zweimal", "never a sentence twice"),
              ("Ein geprüfter Satz geht als Text ans Gerät und in die Warteschlange der Sprachausgabe; Codeblöcke werden "
               "nur gezeigt. Ein schon gesagter Satz aus einer früheren Runde wird ausgelassen. Die Sprachausgabe "
               "fasst nach dem ersten Satz alles Wartende zu einem Stück zusammen, damit die Stimme ruhig bleibt.",
               "A checked sentence goes to the device as text and into the speech output queue; code blocks are only "
               "shown. A sentence already said in an earlier round is left out. After the first sentence speech output "
               "joins everything waiting into one piece, so the voice stays calm.")),
            S("s9", "frage", ("Datenfrage ohne Nachsehen?", "Data question without looking?"),
              ("ganze Runde zurückgehalten", "whole round held back"),
              ("Braucht die Frage ein Werkzeug und das Modell antwortet ohne eines, wird die ganze Runde nie gesagt. "
               "Das Modell wird einmal neu gefragt, mit dem Hinweis, zuerst das Werkzeug zu nutzen.",
               "When the question needs a tool and the model answers without one, the whole round is never said. The "
               "model is asked once more, told to use the tool first."),
              ("zurueck", "ja", "s4")),
            S("s10", "frage", ("Werkzeug gewünscht?", "Tool wanted?"),
              ("Werkzeugaufrufe dieser Runde", "tool calls of this round"),
              ("Hat das Modell keinen Werkzeugaufruf geschrieben oder ist die Länge erreicht, ist die Antwort fertig. "
               "Bei erreichter Länge wird bis zum letzten Satzende gesprochen, der Rest fällt weg.",
               "When the model wrote no tool call or hit the length limit, the answer is done. At the length limit it is "
               "spoken up to the last sentence end, the rest is dropped."),
              ("ok", "nein", "s12")),
            S("s11", "schritt", ("Werkzeuge ausführen", "Run the tools"),
              ("höchstens {chat.MAX_CALLS} pro Runde", "at most {chat.MAX_CALLS} per round"),
              ("Halbe Worte vor dem Aufruf werden zurückgenommen, ein fertiger Satz bleibt. Jeder Aufruf geht über "
               "chat_tools.run; das Ergebnis kommt als Werkzeug-Nachricht zurück. Scheitert ein Werkzeug zweimal "
               "gleich, wird es für diese Antwort gestoppt.",
               "Half words before the call are taken back, a finished sentence stays. Every call goes through "
               "chat_tools.run; the result comes back as a tool message. A tool that fails twice the same way is "
               "stopped for this answer."),
              ("zurueck", ("nächste Runde", "next round"), "s4")),
            S("s12", "schritt", ("Ehrliche Schlusssätze", "Honest closing sentences"),
              ("feste Sätze statt der weggelassenen", "fixed sentences instead of the dropped ones"),
              ("Fiel ein Satz wegen einer Zahl weg, sagt das Panel „Genauere Angaben dazu habe ich nicht.“; fiel eine "
               "Tat weg, einen festen Satz aus taten.sentence. Beide Sätze kommen vom Panel, nie vom Modell.",
               "When a sentence fell out because of a figure, the panel says „I have no more precise details on "
               "that.“; when a deed fell out, a fixed sentence from taten.sentence. Both come from the panel, never "
               "from the model.")),
            S("s13", "schritt", ("Nachfragen des Panels", "The panel's own questions"),
              ("Korrektur, Gedächtnis, reMarkable, Vorab holen", "correction, memory, reMarkable, fetch ahead"),
              ("Nur wenn nichts Fremdes gelesen wurde: eine gelernte Korrektur zum Merken anbieten oder ein Fakt aus "
               "dem Gedächtnis nachfragen (nach festen Regeln). Danach legt das Panel die Antwort aufs reMarkable, wenn "
               "gewünscht, und holt bei einer Rückfrage schon vorab. Das Werkzeug-Log des Profils wird geschrieben.",
               "Only when nothing from outside was read: offer to remember a learned correction or ask about a fact in "
               "memory (by fixed rules). Then the panel puts the answer on the reMarkable when asked and fetches ahead "
               "for a question back. The profile's tool log is written.")),
            S("s14", "ende", ("Strom endet", "Stream ends"),
              ("Anfrage-Verlauf, Fälle, „done“", "request trace, cases, „done“"),
              ("Der Anfrage-Verlauf wird abgeschlossen, Fälle und die Prüfung im Hintergrund laufen erst nach dem "
               "Sprechen. Bricht das Gerät ab (Unterbrechen), stoppen Modell und Sprachausgabe sofort.",
               "The request trace is closed; cases and the background check run only after speaking. When the device "
               "aborts (barge-in), model and speech output stop at once.")),
        ],
        "beispiele": [
            (("Plaudern ohne Werkzeug", "Small talk without a tool"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s10!", "s12", "s13", "s14"],
             ("Gesprochen ab dem ersten Satz, keine Prüfung greift.", "Spoken from the first sentence, no check steps in.")),
            (("Termine von morgen", "Tomorrow's appointments"), ["s1", "s2", "s3", "s4", "s5", "s9", "s10", "s11", "s11!"],
             ("Das Modell ruft den Kalender, die nächste Runde antwortet aus dem Ergebnis.",
              "The model calls the calendar, the next round answers from the result.")),
            (("Erfundene Uhrzeit", "Made-up time"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s12", "s14"],
             ("Der Satz mit der Uhrzeit wird nie gesagt, dafür ein ehrlicher Satz.",
              "The sentence with the time is never said, an honest sentence instead.")),
            (("„Licht ist an“, Schalten scheiterte", "„Light is on“, switching failed"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s7!", "s12", "s14"],
             ("Statt der Behauptung: „Das hat nicht geklappt: …“.", "Instead of the claim: „That did not work: …“.")),
        ],
        "zahlen": [
            ("{chat.MAX_CALLS}", ("Werkzeugaufrufe pro Runde, mehr laufen nicht", "tool calls per round, more do not run"), "chat.MAX_CALLS"),
            ("{chat.MAX_SAVES}", ("Gedächtnis-Notizen pro Antwort", "memory notes per answer"), "chat.MAX_SAVES"),
            ("{chat.LOOP_SAME}", ("gleiche Fehler, bis ein Werkzeug stoppt (oder {chat.LOOP_ANY} beliebige)",
                                  "same failures until a tool stops (or {chat.LOOP_ANY} of any kind)"), "chat.LOOP_SAME"),
            ("{chat.FIRST_CUT}", ("Zeichen, ab denen der erste Satz am Komma losgeht", "characters after which the first sentence goes at a comma"), "chat.FIRST_CUT"),
        ],
        "einstellen": [
            ("Einstellungen → Sprachmodell: Antwort-Prüfung, Taten prüfen und Fehlerschleife stoppen (alle drei "
             "Standard an).",
             "Settings → Language model: Answer check, Check deeds and Stop error loops (all three on by default)."),
            ("Einstellungen → Sprachmodell: Länge einer Antwort, Temperatur, Vorher nachdenken; unter Erweitert die "
             "Websuchen pro Antwort.",
             "Settings → Language model: Length of an answer, Temperature, Think first; under Advanced the Web "
             "searches per answer."),
        ],
        "sehen": [
            ("Zustand → Logs → Anfragen: jede Runde, jedes Werkzeug, „Antwort-Prüfung“ und „Taten-Prüfung“ mit Zahlen, "
             "nie mit Text.",
             "Status → Logs → Requests: every round, every tool, „answer check“ and „check deeds“ with numbers, never "
             "with text."),
            ("Zustand → Logs → Erweitert → Gespräch: wo die Zeit einer Antwort blieb, bis zum ersten Ton.",
             "Status → Logs → Advanced → Conversation: where the time of an answer went, up to the first sound."),
            ("Zustand → Verbessern: wie oft die eingebauten Regeln heute eingegriffen haben.",
             "Status → Improve: how often the built-in rules stepped in today."),
        ],
        "code": [
            ("chat.chat", ("Rate-Limit, Sprache zuerst, „antwortet gerade“", "rate limit, speech first, „answering“")),
            ("chat._answer", ("Runden, Werkzeuge, Prüfungen, Sprachausgabe als ein Strom", "rounds, tools, checks, speech output as one stream")),
            ("chat.split_sentences", ("schneidet fertige Sätze ab", "cuts finished sentences off")),
            ("chat.said_key", ("erkennt einen schon gesagten Satz", "spots a sentence already said")),
            ("chat.no_code", ("Codeblöcke nur zeigen, nie sprechen", "code blocks only shown, never spoken")),
            ("chat.loop_count", ("zählt Fehlschläge für Fehlerschleife stoppen", "counts failures for stop error loops")),
            ("answercheck.known", ("alle Angaben, die das Modell bekommen hat", "every figure the model was given")),
            ("answercheck.unsupported", ("Angaben im Satz ohne Beleg", "figures in the sentence without proof")),
            ("answercheck.fresh", ("nach dem Kalender nur Angaben dieser Antwort", "after the calendar only this answer's figures")),
            ("taten.check", ("Tat behauptet, aber kein Werkzeug hat es geschafft", "deed claimed, no tool managed it")),
            ("taten.sentence", ("der feste ehrliche Satz", "the fixed honest sentence")),
        ],
        "tests": ["test_panel", "test_taten", "test_handlungsregel", "test_fast_start", "test_morgen_termine"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Werkzeuge (chat_tools.run)
    "werkzeuge": {
        "stand": "88af5ddba6",
        "bezug": {
            "chat.LOCKED_OUTSIDE": ["s4"], "notaus.INTERNET_TOOLS": ["s3"], "werkzeuge.NAMES": ["s11"],
            "chat_tools.run": ["s2", "s7"], "chat.wrap_outside": ["s9"], "chat.LOCKED_MAIL": ["s4"],
            "chat.READS_OUTSIDE": ["s4", "s6"], "notaus.locked_tools": ["s3"], "dienstwacht.tool_down": ["s5"],
            "chat.tool_info": ["s11"], "werkzeuge.label": ["s11"], "regeln": ["s4"],
            "regel:Notaus Stufe {notaus.STAGE.internet}": ["s3"],
            "regel:Notaus Stufe {notaus.STAGE.aktion} oder eigener Notaus": ["s3"],
        },
        "kurz": ("Wenn das Modell ein Werkzeug aufruft, führt chat_tools.run es aus, aber nur, wenn es in dieser Runde "
                 "angeboten war und keine Sperre greift. Das Ergebnis geht als Daten an das Modell zurück, nie als Befehl.",
                 "When the model calls a tool, chat_tools.run carries it out, but only when it was offered in this round "
                 "and no lock applies. The result goes back to the model as data, never as a command."),
        "warum": ("Ein Server-Parser reicht jeden Werkzeugnamen durch, den das Modell schreibt, auch erfundene oder "
                  "gesperrte. Und eine Webseite oder Mail könnte das Modell bitten, das Licht zu schalten oder Daten "
                  "wegzuschicken. Darum prüft das Panel bei jedem Aufruf neu, statt dem Modell zu glauben.",
                  "A server parser passes through any tool name the model writes, also made-up or locked ones. And a web "
                  "page or mail could ask the model to switch the light or send data away. So the panel checks every "
                  "call again instead of trusting the model."),
        "ablauf": [
            S("s1", "start", ("Modell ruft ein Werkzeug", "The model calls a tool"),
              ("aus der Runde in chat._answer", "from the round in chat._answer"),
              ("Höchstens {chat.MAX_CALLS} Aufrufe pro Runde laufen, und ein wegen Fehlern gestopptes Werkzeug läuft "
               "nicht mehr. Gedächtnis-Notizen sind auf {chat.MAX_SAVES} pro Antwort begrenzt.",
               "At most {chat.MAX_CALLS} calls per round run, and a tool stopped after errors does not run again. Memory "
               "notes are limited to {chat.MAX_SAVES} per answer.")),
            S("s2", "frage", ("In dieser Runde angeboten?", "Offered in this round?"),
              ("nur die Liste der Runde", "only the round's list"),
              ("Nur Werkzeuge aus der Liste dieser Runde laufen. Die Liste ist schon um Sperren gekürzt; alles andere "
               "bekommt „nicht verfügbar, nicht noch einmal aufrufen“ oder, nach einer Mail, den Grund der Mail-Sperre.",
               "Only tools on this round's list run. The list is already cut by the locks; anything else gets „not "
               "available, do not call it again“ or, after a mail, the reason of the mail lock."),
              ("stop", "nein", ("Nicht ausgeführt", "Not done"))),
            S("s3", "frage", ("Notaus hält es an?", "Kill switch holds it?"),
              ("bei jedem Aufruf neu gelesen", "read again for every call"),
              ("Der Notaus wird bei jedem Aufruf gelesen, also greift er auch mitten in einer Antwort. Ab Stufe "
               "{notaus.STAGE.internet} sind die Werkzeuge gesperrt, die selbst ins Internet gehen; ab Stufe "
               "{notaus.STAGE.aktion} oder mit dem eigenen Notaus des Profils jedes Werkzeug, das etwas ändert.",
               "The kill switch is read for every call, so it also applies in the middle of an answer. From stage "
               "{notaus.STAGE.internet} the tools that go to the internet by themselves are locked; from stage "
               "{notaus.STAGE.aktion} or with the profile's own kill switch every tool that changes something."),
              ("stop", "ja", ("Gesperrt (Notaus)", "Blocked (kill switch)"))),
            S("s4", "frage", ("Fremder Text gelesen?", "Outside text read?"),
              ("Sperre nach Web, Kalender, Dokumenten, Mail", "lock after web, calendar, documents, mail"),
              ("Hat diese Antwort schon Text von draußen gelesen, darf nichts mehr das Zuhause, das Gedächtnis, "
               "Termine oder Erinnerungen ändern. Nach einer Mail ist auch die Websuche zu, nach eigenen Dokumenten "
               "ebenfalls (außer bei „Erst lokal suchen“, dann nur mit den eigenen Worten der Frage).",
               "When this answer already read text from outside, nothing may change the home, the memory, "
               "appointments or reminders any more. After a mail web search is closed too, also after own documents "
               "(except with „search locally first“, then only with the question's own words)."),
              ("stop", "ja", ("Gesperrt (fremder Text)", "Blocked (outside text)"))),
            S("s5", "frage", ("Dienst gerade weg?", "Service gone right now?"),
              ("Dienst-Wächter", "service watch"),
              ("Sieht der Dienst-Wächter den Dienst dieses Werkzeugs gerade ausgefallen (und der Schalter dafür ist an), "
               "kommt sofort ein fester Satz mit der Uhrzeit des Ausfalls statt eines Versuchs. Die Websuche fragt "
               "erst unten und kann dann aufs eigene Archiv ausweichen.",
               "When the service watch sees this tool's service down (and its switch is on), a fixed sentence with the "
               "time of the outage comes at once instead of a try. Web search checks further down and then can fall back "
               "to the own archive."),
              ("stop", "ja", ("Fester Satz: nicht erreichbar", "Fixed sentence: not reachable"))),
            S("s6", "schritt", ("Lesen markieren", "Mark reading"),
              ("ab hier gilt die Antwort als fremd", "from here the answer counts as outside"),
              ("Werkzeuge, die fremden Text bringen (Websuche, Dokumente, Kalender, frühere Gespräche, Kamera), setzen "
               "die Marke schon vor dem Lauf. Ab dann sind die Sperren aus Schritt 4 für den Rest der Antwort aktiv.",
               "Tools that bring outside text (web search, documents, calendar, earlier conversations, camera) set the "
               "mark before they run. From then on the locks of step 4 hold for the rest of the answer.")),
            S("s7", "schritt", ("Werkzeug ausführen", "Run the tool"),
              ("Erweiterung oder eingebautes Werkzeug", "extension or built-in tool"),
              ("Erweiterungen bekommen Profil, Gerät und Herkunft vom Panel, nie vom Modell. Smart-Home-Änderungen "
               "brauchen das Codewort in der letzten Nachricht, wenn eines eingestellt ist. Verbindungen zu Diensten "
               "draußen gehen über den Wächter.",
               "Extensions get profile, device and origin from the panel, never from the model. Smart home changes need "
               "the code word in the latest message when one is set. Connections to outside services go through the "
               "guard.")),
            S("s8", "schritt", ("Fehler als Satz", "Errors as a sentence"),
              ("„nicht erreichbar“, nie raten", "„not reachable“, never guess"),
              ("Ist ein Dienst nicht erreichbar, wird daraus ein kurzer Ergebnis-Text („nicht erreichbar“, „Suche "
               "fehlgeschlagen, nicht raten“). Ein angebotenes Werkzeug ohne passende Einrichtung meldet „unbekannt“.",
               "When a service cannot be reached, it becomes a short result text („not reachable“, „search failed, do "
               "not guess“). An offered tool without a matching setup answers „unknown“.")),
            S("s9", "schritt", ("Ergebnis als Daten einpacken", "Wrap the result as data"),
              ("Hinweis „Daten, kein Befehl“, Block <<< >>>", "note „data, no command“, block <<< >>>"),
              ("Fremder Text bekommt einen festen Hinweis davor und steht zwischen Markierungen, die er selbst nicht "
               "schließen kann. Zustände aus Home Assistant mit freiem Text (Titel, Listen) zählen auch als fremd.",
               "Outside text gets a fixed note in front and stands between markers it cannot close itself. Home "
               "Assistant states with free text (titles, lists) count as outside too.")),
            S("s10", "schritt", ("Gerät markiert die Antwort", "Device marks the answer"),
              ("Ereignis „outside“ oder „mail“", "event „outside“ or „mail“"),
              ("Das Gerät erfährt, dass die Antwort auf fremdem Text beruht. Solche Antworten gehen später nicht noch "
               "einmal ans Modell.",
               "The device learns that the answer rests on outside text. Such answers do not go to the model again "
               "later.")),
            S("s11", "schritt", ("Festhalten", "Record"),
              ("Name, ok, Zeit; nie Inhalte", "name, ok, time; never contents"),
              ("Die Log-Zeile nennt den Namen nur, wenn er angeboten war, sonst „unbekannt“. Was eine Tat war, merkt "
               "sich taten für die Handlungs-Prüfung. Menschen sehen die verständlichen Namen aus werkzeuge.py.",
               "The log line names the tool only when it was offered, else „unbekannt“. What was a deed is noted by "
               "taten for the action check. People see the readable names from werkzeuge.py.")),
            S("s12", "frage", ("Zweimal gescheitert?", "Failed twice?"),
              ("Fehlerschleife stoppen", "stop error loops"),
              ("Scheitert ein Werkzeug {chat.LOOP_SAME} Mal mit denselben Angaben oder {chat.LOOP_ANY} Mal überhaupt, "
               "wird es für diese Antwort gestoppt und das Modell hört, dass es ehrlich sagen soll, was nicht ging.",
               "When a tool fails {chat.LOOP_SAME} times with the same details or {chat.LOOP_ANY} times at all, it is "
               "stopped for this answer and the model is told to say honestly what did not work."),
              ("info", "ja", ("Für diese Antwort gestoppt", "Stopped for this answer"))),
            S("s13", "ende", ("Ergebnis zurück ans Modell", "Result back to the model"),
              ("als Werkzeug-Nachricht", "as a tool message"),
              ("Das Modell bekommt das Ergebnis in der nächsten Runde als Daten. Was es daraus sagt, prüft wieder "
               "die Antwort (Antwort-Prüfung, Taten prüfen).",
               "The model gets the result as data in the next round. What it says from it is checked again by the "
               "answer (answer check, check deeds).")),
        ],
        "beispiele": [
            (("Termine lesen", "Read appointments"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12", "s13"],
             ("Läuft; das Ergebnis geht eingepackt als Daten zurück.", "Runs; the result goes back wrapped as data.")),
            (("Erfundener Werkzeugname", "Made-up tool name"), ["s1", "s2", "s2!"],
             ("Nicht ausgeführt: das Werkzeug war nicht angeboten.", "Not done: the tool was not offered.")),
            (("Notaus während der Antwort", "Kill switch during the answer"), ["s1", "s2", "s3", "s3!"],
             ("Gesperrt: der nächste Aufruf liest den Notaus neu.", "Blocked: the next call reads the kill switch again.")),
            (("Websuche und Licht in einer Runde", "Web search and light in one round"), ["s1", "s2", "s3", "s4", "s4!"],
             ("Gesperrt: nach der Websuche darf nichts mehr schalten.", "Blocked: after the web search nothing may switch.")),
        ],
        "regeln": [
            [("Lage in dieser Antwort", "State in this answer"), ("Gesperrt", "Locked")],
            [("fremder Text gelesen", "outside text read"),
             ("{chat.LOCKED_OUTSIDE|anzahl} ändernde Werkzeuge und die der Erweiterungen", "{chat.LOCKED_OUTSIDE|anzahl} changing tools and those of extensions")],
            [("Mail gelesen", "mail read"), ("dazu Websuche und neue Termine", "also web search and new appointments")],
            [("eigene Dokumente gelesen", "own documents read"), ("Websuche (bei Erst lokal nur eigene Worte)", "web search (with local first only own words)")],
            [("Notaus Stufe {notaus.STAGE.internet}", "kill switch stage {notaus.STAGE.internet}"),
             ("{notaus.INTERNET_TOOLS|anzahl} Werkzeuge, die selbst ins Internet gehen", "{notaus.INTERNET_TOOLS|anzahl} tools that go to the internet themselves")],
            [("Notaus Stufe {notaus.STAGE.aktion} oder eigener Notaus", "kill switch stage {notaus.STAGE.aktion} or own kill switch"),
             ("jedes Werkzeug, das etwas ändert", "every tool that changes something")],
        ],
        "zahlen": [
            ("{chat.MAX_CALLS}", ("Aufrufe pro Runde", "calls per round"), "chat.MAX_CALLS"),
            ("{chat.MAX_SAVES}", ("Gedächtnis-Notizen pro Antwort", "memory notes per answer"), "chat.MAX_SAVES"),
            ("{chat.LOCKED_OUTSIDE|anzahl}", ("Werkzeuge gesperrt nach fremdem Text", "tools locked after outside text"), "chat.LOCKED_OUTSIDE"),
            ("{notaus.INTERNET_TOOLS|anzahl}", ("Werkzeuge ohne Internet bei Notaus", "tools without internet with the kill switch"), "notaus.INTERNET_TOOLS"),
            ("{werkzeuge.NAMES|anzahl}", ("Werkzeuge mit verständlichem Namen", "tools with a readable name"), "werkzeuge.NAMES"),
        ],
        "einstellen": [
            ("Einstellungen → Sprachmodell: Fehlerschleife stoppen (Standard an) und unter Erweitert die Websuchen pro "
             "Antwort.",
             "Settings → Language model: Stop error loops (on by default) and under Advanced the Web searches per answer."),
            ("Funktionen → Weiche: welche Werkzeuge das Modell für eine Frage überhaupt sieht.",
             "Features → Switch: which tools the model sees for a question at all."),
        ],
        "sehen": [
            ("Zustand → Logs → Anfragen: jeder Aufruf mit verständlichem Namen, ok oder nicht, Länge und ob gesperrt.",
             "Status → Logs → Requests: every call with its readable name, ok or not, length and whether locked."),
            ("Zustand → Live: welches Werkzeug gerade läuft und was der Dienst zurückgab (nur die Art).",
             "Status → Live: which tool runs right now and what the service gave back (only the kind)."),
        ],
        "code": [
            ("chat_tools.run", ("die Prüfungen und alle eingebauten Werkzeuge", "the checks and all built-in tools")),
            ("chat._answer", ("ruft run_tool, packt Ergebnisse ein, stoppt Schleifen", "calls run_tool, wraps results, stops loops")),
            ("chat.wrap_outside", ("fremder Text als Datenblock", "outside text as a data block")),
            ("chat.LOCKED_OUTSIDE", ("gesperrt nach fremdem Text", "locked after outside text")),
            ("chat.LOCKED_MAIL", ("gesperrt nach einer Mail", "locked after a mail")),
            ("chat.READS_OUTSIDE", ("Werkzeuge, die fremden Text bringen", "tools that bring outside text")),
            ("notaus.locked_tools", ("was der Notaus je Stufe sperrt", "what the kill switch locks per stage")),
            ("dienstwacht.tool_down", ("fester Satz, wenn ein Dienst weg ist", "fixed sentence when a service is gone")),
            ("chat.tool_info", ("Zahlen für Logs → Anfragen", "numbers for Logs → Requests")),
            ("werkzeuge.label", ("verständlicher Name eines Werkzeugs", "readable name of a tool")),
        ],
        "tests": ["test_fast_start", "test_dienstwacht", "test_taten", "test_notaus", "test_werkzeuge", "test_werkzeug_abdeckung"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Sprachmodell (chat.llm_url)
    "llm": {
        "stand": "f734738328",
        "bezug": {
            "chat.chat": ["s1"], "chat._answer": ["s2", "s4", "s6"], "chat.llm_model": ["s3"],
            "chat.sampling": ["s4"], "chat.first_within": ["s8"], "chat.ContextFull": ["s7"],
            "chat.llm_error_code": ["s12"], "chat.LLM_GONE": ["s12"], "chat.prompt_sizes": ["s11"],
            "stufe.wait_turn": ["s5"], "vorrang.run": ["s1"],
        },
        "kurz": ("Das Sprachmodell (qwen38 aus dgx-spark-qwen38, nicht Teil dieses Repos) schreibt die Antworten. Das "
                 "Panel spricht es an der eingestellten Adresse über die OpenAI-Schnittstelle an, gestreamt, und sorgt "
                 "dafür, dass Sprache immer vor Hintergrundarbeit kommt.",
                 "The language model (qwen38 from dgx-spark-qwen38, not part of this repo) writes the answers. The panel "
                 "talks to it at the configured address through the OpenAI interface, streamed, and makes sure speech "
                 "always comes before background work."),
        "warum": ("Die GPU teilt sich das Modell mit der Sprachausgabe. Wartet eine Person, darf kein Lernen oder "
                  "Aufräumen im Hintergrund die Antwort bremsen. Und ein hängendes oder fehlendes Modell soll einen "
                  "klaren Satz ergeben, keine Minuten Stille.",
                  "The GPU is shared between the model and speech output. While a person waits, no learning or tidying "
                  "in the background may slow the answer. And a hanging or missing model should give a clear sentence, "
                  "not minutes of silence."),
        "ablauf": [
            S("s1", "start", ("Sprache zuerst", "Speech first"),
              ("vorrang.mark bei jedem Stück", "vorrang.mark with every piece"),
              ("Mit dem Start einer Antwort und bei jedem gestreamten Stück setzt das Panel die Marke „Sprache läuft“. "
               "Hintergrundarbeit am Modell wartet bis {vorrang.GRACE} Sekunden danach und wird abgebrochen, sobald "
               "jemand spricht; nach {vorrang.RETRIES} Abbrüchen gibt sie für diesmal auf.",
               "When an answer starts and with every streamed piece the panel sets the mark „speech is running“. "
               "Background work on the model waits until {vorrang.GRACE} seconds after it and is cancelled as soon as "
               "somebody speaks; after {vorrang.RETRIES} cancels it gives up for this time.")),
            S("s2", "schritt", ("Verbindung für diese Antwort", "Connection for this answer"),
              ("Zeitlimit {chat.TIMEOUT_RANGE.0} bis {chat.TIMEOUT_RANGE.1} s", "time limit {chat.TIMEOUT_RANGE.0} to {chat.TIMEOUT_RANGE.1} s"),
              ("Jede Antwort hat eine eigene Verbindung mit dem eingestellten Zeitlimit (ein Wert außerhalb gilt nicht) "
               "und fünf Sekunden zum Verbinden. Ist ein Schlüssel eingetragen, geht er als Bearer mit. Das Modell ist "
               "ein fester eigener Dienst und läuft nicht über den Wächter.",
               "Every answer has its own connection with the configured time limit (a value outside does not count) and "
               "five seconds to connect. When a key is set, it goes along as Bearer. The model is a fixed own service "
               "and does not go through the guard.")),
            S("s3", "schritt", ("Modellname", "Model name"),
              ("eingestellt oder /models", "configured or /models"),
              ("Ist kein Modell eingestellt, fragt das Panel einmal /models und merkt sich den ersten Namen für "
               "diese Adresse.",
               "When no model is configured, the panel asks /models once and keeps the first name for this address.")),
            S("s4", "schritt", ("Anfrage bauen", "Build the request"),
              ("stream, max_tokens, Temperatur, Denken aus", "stream, max_tokens, temperature, thinking off"),
              ("Die Anfrage streamt, mit Länge, Temperatur, top_p und presence_penalty aus den Einstellungen. Denken ist "
               "aus, außer „Vorher nachdenken“ ist an. Während der Werkzeugwahl gilt die eigene Temperatur dafür. Bei "
               "eingeschalteten Logs meldet der Server, wie viel er gelesen hat und wie viel aus seinem Zwischenspeicher kam.",
               "The request streams, with length, temperature, top_p and presence_penalty from the settings. Thinking is "
               "off unless „Think first“ is on. While a tool is chosen its own temperature applies. With logs on the "
               "server reports how much it read and how much came from its cache.")),
            S("s5", "frage", ("Wartet jemand mit Vorrang?", "Someone with priority waiting?"),
              ("Vorrang für Personen", "priority for people"),
              ("Hat eine andere Person Vorrang und ihre Antwort noch keinen ersten Satz, wartet diese Runde höchstens "
               "die eingestellte Zeit (bis {stufe.WAIT_RANGE.1} Sekunden). Eine Antwort mit Vorrang hält andere "
               "höchstens {stufe.FIRST_MAX} Sekunden auf.",
               "When another person has priority and their answer has no first sentence yet, this round waits at most "
               "the configured time (up to {stufe.WAIT_RANGE.1} seconds). An answer with priority holds others up "
               "for at most {stufe.FIRST_MAX} seconds."),
              ("info", "ja", ("kurz warten, dann weiter", "wait shortly, then go on"))),
            S("s6", "schritt", ("Eine Runde an das Modell", "One round to the model"),
              ("gestreamt (SSE)", "streamed (SSE)"),
              ("Die Runde geht an die eingestellte Adresse. Lehnt der Server die erzwungene Werkzeugwahl ab, geht "
               "dieselbe Runde einmal ohne sie.",
               "The round goes to the configured address. When the server refuses the forced tool choice, the same "
               "round goes once without it.")),
            S("s7", "frage", ("Zu lang für das Modell?", "Too long for the model?"),
              ("HTTP 400 „context“", "HTTP 400 „context“"),
              ("Meldet der Server, dass die Anfrage länger als sein Kontext ist, kürzt das Panel in der ersten Runde den "
               "Verlauf auf ein Viertel des Verlaufsbudgets und fragt einmal neu.",
               "When the server says the request is longer than its context, the panel cuts the history to a quarter of "
               "the history budget in the first round and asks once more."),
              ("zurueck", "ja", "s6")),
            S("s8", "frage", ("Erste Zeile rechtzeitig?", "First line in time?"),
              ("höchstens {chat.FIRST_WAIT} s", "at most {chat.FIRST_WAIT} s"),
              ("Die erste Zeile muss innerhalb von {chat.FIRST_WAIT} Sekunden kommen (oder des kürzeren Zeitlimits). "
               "Ein Modell, das länger schweigt, hängt: die Antwort endet mit einem klaren Satz statt mit Minuten Stille.",
               "The first line must come within {chat.FIRST_WAIT} seconds (or the shorter time limit). A model that stays "
               "silent longer hangs: the answer ends with a clear sentence instead of minutes of silence."),
              ("stop", "nein", ("„antwortet gerade nicht“", "„not answering right now“"))),
            S("s9", "schritt", ("Zeilen lesen", "Read the lines"),
              ("data: … bis [DONE]", "data: … until [DONE]"),
              ("Jede Zeile ist ein Stück JSON. Werkzeugaufrufe kommen in Teilen und werden nach ihrer Nummer "
               "zusammengesetzt; Denktext, den der Server getrennt liefert, wird nur gezählt. Unlesbare Zeilen werden "
               "übersprungen.",
               "Every line is a piece of JSON. Tool calls come in parts and are put together by their number; thinking "
               "the server hands over separately is only counted. Unreadable lines are skipped.")),
            S("s10", "schritt", ("Nur Antworttext weiter", "Only answer text goes on"),
              ("<think> und <tool_call> fallen weg", "<think> and <tool_call> are dropped"),
              ("Denktext im Text (<think> … </think>) und Werkzeugaufrufe, die als Text kommen, werden nie gezeigt oder "
               "gesprochen. Der Rest geht Stück für Stück an „Antwort bauen“.",
               "Thinking inside the text (<think> … </think>) and tool calls that come as text are never shown or "
               "spoken. The rest goes piece by piece to „build answer“.")),
            S("s11", "schritt", ("Runde festhalten", "Record the round"),
              ("Tokens, Zwischenspeicher, Zeiten", "tokens, cache, times"),
              ("Für den Anfrage-Verlauf zählen nur Zahlen: gelesene Tokens, davon aus dem Zwischenspeicher, Größe von "
               "Systemprompt, Werkzeugliste und Verlauf, Zeit bis zum ersten Wort, Wartezeit wegen Vorrang.",
               "For the request trace only numbers count: tokens read, of them from the cache, size of system prompt, "
               "tool list and history, time to the first word, waiting time for priority.")),
            S("s12", "frage", ("Fehler unterwegs?", "Error on the way?"),
              ("nicht erreichbar, zu langsam, Schlüssel", "not reachable, too slow, key"),
              ("Ein Fehler wird zu einem festen Kürzel: nicht erreichbar, zu langsam, Schlüssel abgelehnt, Modell "
               "fehlt. Bei „nicht erreichbar“ und „zu langsam“ wird ein fester Satz auch gesprochen, wenn noch nichts "
               "gesagt war. Gäste sehen nur die Art des Fehlers, nie seinen Text.",
               "An error becomes a fixed code: not reachable, too slow, key refused, model missing. With „not reachable“ "
               "and „too slow“ a fixed sentence is also spoken when nothing was said yet. Guests see only the kind of "
               "error, never its text."),
              ("stop", "ja", ("Fester Satz statt Antwort", "Fixed sentence instead of an answer"))),
            S("s13", "ende", ("Text und Werkzeugaufrufe zurück", "Text and tool calls back"),
              ("an Antwort bauen", "to build answer"),
              ("Die Runde gibt zurück, warum sie endete und welche Werkzeuge das Modell aufrufen will. Was davon "
               "läuft, entscheidet das Panel.",
               "The round returns why it ended and which tools the model wants to call. The panel decides what of it "
               "runs.")),
        ],
        "beispiele": [
            (("Normale Antwort", "Normal answer"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12", "s13"],
             ("Gestreamt, der erste Satz geht sofort zur Sprachausgabe.", "Streamed, the first sentence goes to speech output at once.")),
            (("Zwei Personen, eine mit Vorrang", "Two people, one with priority"), ["s1", "s2", "s3", "s4", "s5", "s5!", "s6"],
             ("Die Runde wartet kurz, bis die Antwort mit Vorrang ihren ersten Satz hat.",
              "The round waits briefly until the answer with priority has its first sentence.")),
            (("Sehr langes Dokument im Verlauf", "Very long document in the history"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s7!"],
             ("Verlauf gekürzt, einmal neu gefragt.", "History cut, asked once more.")),
            (("qwen38 hängt", "qwen38 hangs"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!"],
             ("„Mein Sprachmodell antwortet gerade nicht.“ statt Stille.", "„My language model is not answering right now.“ instead of silence.")),
        ],
        "zahlen": [
            ("{chat.FIRST_WAIT} s", ("bis zur ersten Zeile des Modells", "until the model's first line"), "chat.FIRST_WAIT"),
            ("{chat.TIMEOUT_RANGE.0} bis {chat.TIMEOUT_RANGE.1} s", ("erlaubtes Zeitlimit", "allowed time limit"), "chat.TIMEOUT_RANGE"),
            ("{vorrang.GRACE} s", ("nach Sprache wartet Hintergrundarbeit noch", "background work still waits after speech"), "vorrang.GRACE"),
            ("{vorrang.RETRIES}", ("Abbrüche, bis Hintergrundarbeit aufgibt", "cancels until background work gives up"), "vorrang.RETRIES"),
            ("{stufe.WAIT_RANGE.1} s", ("längste Wartezeit für Vorrang", "longest wait for priority"), "stufe.WAIT_RANGE"),
            ("{stufe.FIRST_MAX} s", ("so lange hält eine Antwort mit Vorrang höchstens auf", "a priority answer holds up at most this long"), "stufe.FIRST_MAX"),
        ],
        "einstellen": [
            ("Einstellungen → Sprachmodell: Adresse, Schlüssel und Modell; dazu Vorher nachdenken, Temperatur und Länge "
             "einer Antwort.",
             "Settings → Language model: Address, Key and Model; also Think first, Temperature and Length of an answer."),
            ("Einstellungen → Sprachmodell, unter Erweitert: Zeitlimit für eine Antwort.",
             "Settings → Language model, under Advanced: Time limit for an answer."),
            ("Funktionen → Vorrang für Personen: ausgewählte Profile bekommen ihre Antwort zuerst.",
             "Features → Priority for people: chosen profiles get their answer first."),
        ],
        "sehen": [
            ("Zustand → Logs → Erweitert → Gespräch: pro Runde gelesene Tokens, davon aus dem Zwischenspeicher, und "
             "die Zeit bis zum ersten Wort.",
             "Status → Logs → Advanced → Conversation: per round tokens read, of them from the cache, and the time to "
             "the first word."),
            ("Zustand → Prüfen → Vorrang für Sprache: ob die Sprachausgabe flüssig bleibt, während das Modell rechnet.",
             "Status → Checks → Speech first: whether speech output stays smooth while the model computes."),
        ],
        "code": [
            ("chat.chat", ("setzt „Sprache läuft“ bei jedem Stück", "sets „speech is running“ with every piece")),
            ("chat._answer", ("Verbindung, Anfrage, Runden (llm_round), Fehlerfälle", "connection, request, rounds (llm_round), errors")),
            ("chat.llm_model", ("Modellname aus Einstellung oder /models", "model name from settings or /models")),
            ("chat.sampling", ("top_p und presence_penalty", "top_p and presence_penalty")),
            ("chat.first_within", ("die erste Zeile muss rechtzeitig kommen", "the first line must come in time")),
            ("chat.ContextFull", ("Anfrage länger als der Kontext", "request longer than the context")),
            ("chat.llm_error_code", ("Fehler als festes Kürzel", "error as a fixed code")),
            ("chat.LLM_GONE", ("der gesprochene Satz, wenn das Modell fehlt", "the spoken sentence when the model is gone")),
            ("chat.prompt_sizes", ("Größe der Teile einer Anfrage", "size of the parts of a request")),
            ("stufe.wait_turn", ("wartet auf eine Antwort mit Vorrang", "waits for an answer with priority")),
            ("vorrang.mark", ("Marke „Sprache läuft“", "mark „speech is running“")),
            ("vorrang.run", ("Hintergrundarbeit weicht der Sprache", "background work gives way to speech")),
        ],
        "tests": ["test_panel", "test_llm_settings", "test_vorrang", "test_stufe", "test_fast_start"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Wissen: how a question finds passages
    "wissen": {
        "stand": "e79f00ee84",
        "bezug": {
            "lokal.MAX_HITS": ["s5"], "wissen.search": ["s1", "s8", "s9"], "documents.search": ["s5", "s6"],
            "documents._terms": ["s5"], "documents.match_docs": ["s4"], "docembed.query": ["s3"],
            "docembed._call": ["s3"], "nachsortieren.rank": ["s10"], "wissen.recent_window": ["s11"],
            "wissen.where": ["s13"], "lokal.look": ["s5"], "gedaechtnis.hint_lines": ["s13"],
            "regeln": ["s1", "s8"], "regel:Geteilte Dokumente": ["s8"], "regel:Gedächtnis": ["s13"],
            "regel:Erst lokal suchen": ["s5"],
        },
        "kurz": ("Wissen ist alles, was der Spark selbst weiß, ohne ins Internet zu gehen: die hochgeladenen Dokumente "
                 "jedes Profils (eine SQLite-Datei wissen.db pro Profil), das Gedächtnis, frühere Gespräche, das eigene "
                 "Kiwix-Archiv und erstellte Dokumente. Die Seite zeigt den Weg, auf dem eine Frage passende Stellen "
                 "in den Dokumenten findet.",
                 "Knowledge is everything the Spark knows without going to the internet: the uploaded documents of "
                 "each profile (one SQLite file wissen.db per profile), the memory, earlier conversations, the own "
                 "Kiwix archive and created documents. This page shows the way a question finds fitting passages in "
                 "the documents."),
        "warum": ("Das Sprachmodell kennt die eigenen Unterlagen nicht. Es bekommt nur die wenigen Stellen, die das "
                  "Panel mit festen Regeln und zwei kleinen Modellen auf dem Prozessor heraussucht, jeweils mit "
                  "Herkunft. Was in einem Dokument steht, ist Text von außen: Daten, nie ein Befehl.",
                  "The language model does not know the own papers. It only gets the few passages the panel picks "
                  "with fixed rules and two small models on the processor, each with its source. What a document "
                  "says is outside text: data, never a command."),
        "ablauf": [
            S("s1", "start", ("Modell ruft document_search", "Model calls document_search"),
              ("nur wenn das Profil Dokumente hat", "only when the profile has documents"),
              ("Das Werkzeug wird nur angeboten, wenn das Profil eigene oder geteilte Dokumente hat, die Funktion für "
               "das Profil frei ist und die Stimme erkannt ist. Gäste und fremde Stimmen am geteilten Lautsprecher "
               "bekommen es nie. Das Profil kommt aus der Anmeldung, nie vom Modell.",
               "The tool is offered only when the profile has own or shared documents, the function is released "
               "for the profile and the voice is recognized. Guests and unknown voices at a shared speaker never "
               "get it. The profile comes from the login, never from the model.")),
            S("s2", "frage", ("Tags oder Art erlaubt?", "Tags or kind allowed?"),
              ("nur mit Steckbrief und Tags", "only with document card and tags"),
              ("Das Modell darf die Suche auf Tags oder eine Dokumentart eingrenzen (höchstens fünf Tags). Ist "
               "„Steckbrief und Tags“ für das Profil aus, werden diese Angaben verworfen und alle Dokumente "
               "durchsucht.",
               "The model may narrow the search to tags or a kind of document (at most five tags). With "
               "„Document card and tags“ off for the profile these are dropped and every document is searched."),
              ("info", "nein", ("Tags und Art verworfen", "Tags and kind dropped"))),
            S("s3", "schritt", ("Bedeutungsvektor der Frage", "Meaning vector of the question"),
              ("höchstens {docembed.QUERY_TIMEOUT} s warten", "wait at most {docembed.QUERY_TIMEOUT} s"),
              ("Mit Bedeutungssuche rechnet ein kleines Vektormodell (eigener Prozess, nur Prozessor) den Vektor der "
               "Frage. Es startet nur bei mindestens {docembed.MIN_FREE_GIB} GiB freiem Speicher und endet nach "
               "{docembed.IDLE_STOP|min} Minuten ohne Arbeit. Kommt kein Vektor, sucht der Spark nur im Volltext, "
               "ohne Fehler.",
               "With meaning search a small vector model (own process, processor only) computes the question's "
               "vector. It starts only with at least {docembed.MIN_FREE_GIB} GiB free memory and ends after "
               "{docembed.IDLE_STOP|min} minutes without work. Without a vector the Spark searches full text only, "
               "without an error."),
              ("info", ("kein Vektor", "no vector"), ("nur Volltext", "full text only"))),
            S("s4", "frage", ("Eingegrenzt?", "Narrowed?"),
              ("Tags oder Art aus dem Steckbrief", "tags or kind from the document card"),
              ("Mit Tags oder Art sucht match_docs zuerst die Dokumente, die alle Tags und die Art tragen. Nur deren "
               "Stellen kommen weiter in Frage; passt keines, gibt es keine Treffer.",
               "With tags or kind, match_docs first finds the documents that carry all tags and the kind. Only "
               "their passages stay in the race; if none fits, there are no hits."),
              ("info", "ja", ("nur diese Dokumente", "only these documents"))),
            S("s5", "schritt", ("Volltext: Wörter und Kontextzeile", "Full text: words and context line"),
              ("SQLite FTS mit BM25", "SQLite FTS with BM25"),
              ("Die Frage wird in Suchwörter zerlegt (Füllwörter weg, Endungen grob gekürzt). Gesucht wird in den "
               "Wörtern jeder Stelle und in ihrer Kontextzeile (Titel, Art, Überschriften), die nur mit "
               "{documents.HEAD_WEIGHT} zählt. Die besten 30 bekommen einen Rang.",
               "The question is split into search words (filler words dropped, endings roughly cut). The search "
               "looks in each passage's words and in its context line (title, kind, headings), which counts only "
               "{documents.HEAD_WEIGHT}. The best 30 get a rank.")),
            S("s6", "schritt", ("Bedeutung dazumischen", "Mix in meaning"),
              ("Ähnlichkeit ab 0,75 · Rangmischung", "similarity from 0.75 · rank fusion"),
              ("Hat die Frage einen Vektor, werden die Vektoren aller Stellen verglichen. Unter 0,75 Ähnlichkeit gilt "
               "nichts als verwandt; die besten 30 darüber bekommen ebenfalls einen Rang. Beide Ränge werden "
               "addiert, so steigt eine Stelle, die in beiden Listen weit oben steht.",
               "If the question has a vector, it is compared with every passage's vector. Below 0.75 similarity "
               "nothing counts as related; the best 30 above get a rank too. Both ranks are added, so a passage "
               "high in both lists rises.")),
            S("s7", "frage", ("Neueste zuerst?", "Newest first?"),
              ("bei reMarkable-Notizen", "with reMarkable notes"),
              ("Mit „Neueste zuerst“ bekommt eine kürzlich geänderte Stelle einen kleinen Vorsprung, etwa zwei Plätze, "
               "der mit dem Alter kleiner wird. Die Passung bleibt wichtiger; jeder Treffer trägt dann sein Datum.",
               "With „Newest first“ a passage changed lately gets a small lead, about two places, which shrinks "
               "with age. Fit stays more important; each hit then carries its date."),
              ("info", "ja", ("kleiner Vorsprung für Neues", "small lead for new pages"))),
            S("s8", "schritt", ("Geteilte Dokumente der anderen", "Shared documents of the others"),
              ("„Für alle“ markiert, nur fertig gelesene", "marked „for everyone“, only fully read ones"),
              ("Mit „Gemeinsame Dokumente“ läuft dieselbe Suche in den Dateien der anderen Profile, aber nur über "
               "Dokumente, die dort „Für alle“ sind. Die Treffer tragen den Namen des Besitzers; alles wird nach Rang "
               "sortiert.",
               "With „Shared documents“ the same search runs in the other profiles' files, but only over documents "
               "marked „for everyone“ there. The hits carry the owner's name; everything is sorted by rank.")),
            S("s9", "frage", ("Treffer nachsortieren an?", "Re-rank hits on?"),
              ("sonst die ersten fünf der Mischung", "else the first five of the mix"),
              ("Ohne Nachsortieren gehen die ersten fünf der Mischung weiter. Mit Nachsortieren reicht die Mischung "
               "ihre besten {nachsortieren.CANDIDATES} weiter.",
               "Without re-ranking the first five of the mix go on. With re-ranking the mix hands over its best "
               "{nachsortieren.CANDIDATES}."),
              ("ok", "nein", "s11")),
            S("s10", "schritt", ("Cross-Encoder ordnet", "Cross-encoder orders"),
              ("unter {nachsortieren.MIN_SCORE} fällt weg", "below {nachsortieren.MIN_SCORE} drops out"),
              ("Ein kleines Modell auf dem Prozessor liest Frage und Stelle zusammen und gibt jeder eine Zahl. "
               "Stellen unter {nachsortieren.MIN_SCORE} beantworten die Frage nicht und fallen weg, die besten fünf "
               "bleiben. Schläft das Modell, ist es belegt, zu langsam oder kaputt, bleibt die Reihenfolge der "
               "Mischung; die Antwort wartet nie länger als eingestellt.",
               "A small model on the processor reads question and passage together and gives each a number. "
               "Passages below {nachsortieren.MIN_SCORE} do not answer the question and drop out, the best five "
               "stay. If the model sleeps, is busy, too slow or broken, the mix's order stays; the answer never "
               "waits longer than set."),
              ("info", ("schläft, belegt, langsam", "asleep, busy, slow"), ("Reihenfolge der Mischung", "order of the mix"))),
            S("s11", "frage", ("„Was habe ich zuletzt notiert?“", "„What did I note lately?“"),
              ("feste Regel auf den eigenen Worten", "fixed rule on the person's own words"),
              ("Fragt die Person mit eigenen Worten nach dem, was sie zuletzt, heute oder diese Woche notiert hat, "
               "kommen die zuletzt geänderten Seiten zuerst. Ist in der Zeit nichts geändert, sagt das Werkzeug das, "
               "statt zu raten.",
               "If the person asks in their own words what they noted lately, today or this week, the pages changed "
               "last come first. If nothing changed in that time, the tool says so instead of guessing."),
              ("info", "ja", ("neueste Seiten zuerst", "newest pages first"))),
            S("s12", "frage", ("Keine Stelle gefunden?", "No passage found?"),
              ("mit Tags: wenigstens die Dokumente", "with tags: at least the documents"),
              ("Findet die Suche nichts, waren aber Tags oder Art genannt, bekommt das Modell die Steckbrief-Zeilen "
               "der passenden Dokumente. Sonst heißt es: nichts gefunden, sag das, rate nicht.",
               "If the search finds nothing but tags or a kind were given, the model gets the card lines of the "
               "fitting documents. Otherwise: nothing found, say so, do not guess."),
              ("stop", "ja", ("Nichts gefunden, nicht raten", "Nothing found, do not guess"))),
            S("s13", "ende", ("Stellen mit Herkunft ans Modell", "Passages with source to the model"),
              ("als Text von außen", "as outside text"),
              ("Jede Stelle geht mit Dokument, Seite und Abschnitt ans Modell. Ab jetzt gilt die Antwort als eine, "
               "die Text von außen gelesen hat: Schalten, Merken und Erinnerungen sind in ihr gesperrt. Das Gerät "
               "zeigt die Quellen.",
               "Each passage goes to the model with document, page and section. From now on the answer counts as "
               "one that read outside text: switching, saving to memory and reminders are locked in it. The device "
               "shows the sources.")),
        ],
        "beispiele": [
            (("Frage nach einer Vertragsklausel", "Question about a contract clause"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12", "s13"],
             ("Gefunden: die Klausel und zwei Nachbarstellen, nachsortiert, mit Seite.",
              "Found: the clause and two neighbouring passages, re-ranked, with page.")),
            (("Vektormodell schläft noch", "Vector model still asleep"),
             ["s1", "s2", "s3", "s3!", "s4", "s5", "s7", "s8", "s9", "s9!", "s11", "s12", "s13"],
             ("Gefunden über den Volltext allein; die Antwort hat nicht gewartet.",
              "Found by full text alone; the answer did not wait.")),
            (("Rechnungen mit Tag, Wörter passen nicht", "Invoices with a tag, words do not fit"),
             ["s1", "s2", "s3", "s4", "s4!", "s5", "s6", "s7", "s8", "s9", "s9!", "s11", "s12", "s12!"],
             ("Keine Stelle, aber die Liste der Dokumente mit dem Tag.", "No passage, but the list of documents with the tag.")),
        ],
        "regeln": [
            [("Quelle", "Source"), ("Wie sie gefunden wird", "How it is found"), ("Wer", "Who")],
            [("Eigene Dokumente", "Own documents"), ("document_search: Volltext, Bedeutung, Nachsortieren", "document_search: full text, meaning, re-ranking"), ("eigenes Profil", "own profile")],
            [("Geteilte Dokumente", "Shared documents"), ("dieselbe Suche, nur „Für alle“", "the same search, only „for everyone“"), ("andere Profile, nie Gäste", "other profiles, never guests")],
            [("Gedächtnis", "Memory"), ("wird nicht gesucht: steht in drei Blöcken im Systemprompt", "not searched: stands in three blocks in the system prompt"), ("eigenes Profil", "own profile")],
            [("Frühere Gespräche", "Earlier conversations"), ("history_search über Wörter", "history_search by words"), ("eigenes Profil", "own profile")],
            [("Kiwix", "Kiwix"), ("archive_search und wikipedia über das eigene Kiwix im Heimnetz", "archive_search and wikipedia via the own Kiwix in the home network"), ("alle Profile, nie Gäste", "all profiles, never guests")],
            [("Erst lokal suchen", "Look locally first"), ("Volltext ohne Warten auf Modelle, vor der ersten Runde", "full text without waiting for models, before the first round"), ("wie die Werkzeuge der Anfrage", "as the request's tools")],
        ],
        "zahlen": [
            ("{nachsortieren.CANDIDATES}", ("Kandidaten für das Nachsortieren", "candidates for re-ranking"), "nachsortieren.CANDIDATES"),
            ("{nachsortieren.MIN_SCORE}", ("Untergrenze des Cross-Encoders", "cross-encoder's lower limit"), "nachsortieren.MIN_SCORE"),
            ("{documents.HEAD_WEIGHT}", ("Gewicht der Kontextzeile", "weight of the context line"), "documents.HEAD_WEIGHT"),
            ("{docembed.QUERY_TIMEOUT} s", ("längstes Warten auf den Fragevektor", "longest wait for the question vector"), "docembed.QUERY_TIMEOUT"),
            ("{docembed.MIN_FREE_GIB} GiB", ("freier Speicher, damit das Vektormodell startet", "free memory for the vector model to start"), "docembed.MIN_FREE_GIB"),
            ("{lokal.MAX_HITS}", ("Treffer höchstens bei „Erst lokal suchen“", "hits at most with „Look locally first“"), "lokal.MAX_HITS"),
        ],
        "einstellen": [
            ("Funktionen → Eigene Dokumente und darunter Bedeutungssuche an: Stellen bekommen einen Bedeutungsvektor "
             "(Standard aus).",
             "Features → Own documents and below it Meaning search on: passages get a meaning vector (default off)."),
            ("Funktionen → Eigene Dokumente und darunter Treffer nachsortieren an: dazu Modellgröße und wie lange "
             "höchstens gewartet wird.",
             "Features → Own documents and below it Re-rank hits on: with model size and the longest wait."),
            ("Funktionen → Eigene Dokumente und darunter Steckbrief und Tags an: Suche nach Tags und Art.",
             "Features → Own documents and below it Document card and tags on: search by tags and kind."),
            ("Funktionen → Eigene Dokumente und darunter Gemeinsame Dokumente an: Dokumente „Für alle“.",
             "Features → Own documents and below it Shared documents on: documents „for everyone“."),
        ],
        "sehen": [
            ("Zustand → Logs → Anfragen: der Schritt „Nachsortieren“ mit Zahl der Kandidaten, behaltenen Stellen und "
             "Zustand des Modells.",
             "Status → Logs → Requests: the step „Nachsortieren“ with the number of candidates, kept passages and "
             "the model's state."),
            ("Zustand → Logs → Diagnose, Bereich Wissen: Zeilen von wissen, docembed, lokal und kiwix, nur feste "
             "Wörter und Zahlen.",
             "Status → Logs → Diagnosis, area Wissen: lines of wissen, docembed, lokal and kiwix, fixed words and "
             "numbers only."),
        ],
        "mehr": [
            (("Erst lokal suchen", "Look locally first"), [
                ("Vor der ersten Runde schaut das Panel selbst in Dokumente, Kiwix und frühere Gespräche, gleichzeitig "
                 "und nur kurz. Die Bedeutungssuche fährt nur mit, wenn ihr Modell schon läuft und frei ist; es wird "
                 "dafür nicht geweckt.",
                 "Before the first round the panel itself looks in documents, Kiwix and earlier conversations, at the "
                 "same time and only briefly. Meaning search only rides along when its model already runs and is free; "
                 "it is not woken for it."),
                ("Eine Stelle zählt nur, wenn sie mindestens {lokal.COVER} der Suchwörter enthält. Was zu spät kommt, "
                 "wird nicht abgewartet.",
                 "A passage only counts when it holds at least {lokal.COVER} of the search words. What comes too late "
                 "is not waited for."),
            ]),
            (("Gedächtnis", "Memory"), [
                ("Das Gedächtnis wird nicht durchsucht. Das Panel sortiert die Fakten mit festen Regeln in drei Blöcke "
                 "(sicher, gelernt, vielleicht veraltet) und gibt sie dem Modell im Systemprompt.",
                 "The memory is not searched. The panel sorts the facts by fixed rules into three blocks (sure, "
                 "learned, maybe out of date) and gives them to the model in the system prompt."),
            ]),
        ],
        "code": [
            ("wissen.search", ("eigene und geteilte Dokumente, Mischung, Nachsortieren", "own and shared documents, mix, re-ranking")),
            ("documents.search", ("Volltext und Vektoren, Rangmischung", "full text and vectors, rank fusion")),
            ("documents._terms", ("Suchwörter aus der Frage", "search words from the question")),
            ("documents.match_docs", ("Dokumente mit Tags und Art", "documents with tags and kind")),
            ("docembed.query", ("Fragevektor oder nichts", "question vector or nothing")),
            ("docembed._call", ("ein Auftrag an den Modellprozess", "one job for the model process")),
            ("nachsortieren.rank", ("Cross-Encoder oder Reihenfolge der Mischung", "cross-encoder or the mix's order")),
            ("wissen.recent_window", ("„zuletzt notiert“ als feste Regel", "„noted lately“ as a fixed rule")),
            ("wissen.where", ("Herkunft einer Stelle für das Modell", "source of a passage for the model")),
            ("lokal.look", ("der kurze Blick vor der Antwort", "the quick look before the answer")),
            ("gedaechtnis.hint_lines", ("Fakten in drei Blöcken", "facts in three blocks")),
        ],
        "tests": ["test_wissen", "test_nachsortieren", "test_abschnitte", "test_lokal", "test_kiwix", "test_gedaechtnis",
                  "test_suchpruefung"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Betrieb: Logs und Live
    "betrieb": {
        "stand": "f9d1d6513d",
        "bezug": {
            "dienstwacht.FAIL_N": ["s5"], "dienstwacht.REPEAT": ["s5"], "backup.KEEP": ["s9"],
            "tracelog.safe": ["s3"], "tracelog.Rec": ["s3", "s6"], "tracelog.finish": ["s8", "s9"],
            "tracelog.shown": ["s10"], "live.step": ["s4"], "logfilter.parse": ["s11"],
            "logfilter.summary": ["s12"], "dienstwacht.round_once": ["s5"], "backup.create": ["s9"],
            "regeln": ["s4", "s5", "s9"], "regel:Live": ["s4"], "regel:Anfrage-Verlauf": ["s9"],
            "regel:Journal": ["s5"], "regel:Dienst-Wächter": ["s5"], "regel:Sicherungen": ["s9"],
        },
        "kurz": ("Betrieb hält fest, was der Spark tut, ohne Inhalte: den Weg jeder Anfrage (Logs → Anfragen), die "
                 "Live-Übersicht, das Journal mit festen Wörtern, den Dienst-Wächter und die Sicherung. Die Seite zeigt, "
                 "welche Spuren eine Anfrage hinterlässt.",
                 "Operation records what the Spark does, without contents: the way of each request (Logs → Requests), "
                 "the live overview, the journal with fixed words, the service watch and the backup. This page shows "
                 "which traces a request leaves."),
        "warum": ("Wer einen Fehler sucht, muss sehen, welchen Weg eine Anfrage nahm und wie lange jeder Schritt "
                  "dauerte. Fragen, Antworten und Werkzeugergebnisse gehören aber der Person; deshalb gehen nur feste "
                  "Wörter, Werkzeugnamen und Zahlen in Log und Verlauf.",
                  "Whoever looks for a fault must see which way a request took and how long each step lasted. "
                  "Questions, answers and tool results belong to the person; so only fixed words, tool names and "
                  "numbers go into the log and the history."),
        "ablauf": [
            S("s1", "start", ("Anfrage kommt an", "A request comes in"),
              ("tracelog.start", "tracelog.start"),
              ("Chat, Schreibhilfe, Dokumente erstellen und was der Spark von selbst tut, legen beim Start einen "
               "Datensatz an: Kanal, Art (Profil, Gast, Admin, Spark) und Gerät.",
               "Chat, writing help, creating documents and what the Spark does by itself create a record at the start: "
               "channel, kind (profile, guest, admin, Spark) and device.")),
            S("s2", "frage", ("Etwas eingeschaltet?", "Anything switched on?"),
              ("Anfragen verfolgen, Live oder Fälle", "trace requests, Live or cases"),
              ("Ist weder „Anfragen verfolgen“ noch die Live-Seite noch der Einstellungs-Assistent an, gibt es keinen "
               "Datensatz. Übrig bleiben nur die Journal-Zeilen der Module.",
               "If neither „Trace requests“ nor the live page nor the settings assistant is on, there is no record. "
               "Only the modules' journal lines remain."),
              ("stop", "nein", ("Kein Verlauf, nur Journal", "No history, only journal"))),
            S("s3", "schritt", ("Schritte mit festen Wörtern", "Steps with fixed words"),
              ("höchstens {tracelog.MAX_STEPS} Schritte", "at most {tracelog.MAX_STEPS} steps"),
              ("Jeder Schritt (Weiche, Modellrunde, Werkzeug, Prüfung, Sprachausgabe) kommt mit Art, Name und Zeit "
               "dazu. Ein Wert geht nur hinein, wenn er eine Zahl oder ein kurzes festes Wort ist; alles andere wird "
               "verworfen. Frage, Antwort, Argumente und Ergebnisse kommen nie hinein.",
               "Each step (switch, model round, tool, check, speech output) is added with kind, name and time. A "
               "value goes in only if it is a number or a short fixed word; anything else is dropped. Question, "
               "answer, arguments and results never go in.")),
            S("s4", "frage", ("Live-Seite an?", "Live page on?"),
              ("nur im Speicher", "in memory only"),
              ("Bei eingeschalteter Live-Seite sieht live.py jeden Schritt sofort: welcher Dienst gefragt wird, was "
               "der Wächter entscheidet, was zurückkommt. Alles bleibt im Speicher und ist nach einem Neustart weg.",
               "With the live page on, live.py sees each step at once: which service is asked, what the guard "
               "decides, what comes back. Everything stays in memory and is gone after a restart."),
              ("info", "ja", ("Zustand → Live zeigt es", "Status → Live shows it"))),
            S("s5", "schritt", ("Journal-Zeilen der Module", "Journal lines of the modules"),
              ("jede beginnt mit einem Bereichswort", "each starts with an area word"),
              ("Unabhängig davon schreibt jedes Modul seine Zeilen ins Journal des Spark. Jede Zeile beginnt mit einem "
               "Wort aus logfilter.AREAS ({logfilter.AREAS|anzahl} Bereiche), Profile nur über profiles.log_name. "
               "Ein Selbsttest prüft beides.",
               "Independently each module writes its lines into the Spark's journal. Every line starts with a word "
               "from logfilter.AREAS ({logfilter.AREAS|anzahl} areas), profiles only through profiles.log_name. A "
               "self-test checks both.")),
            S("s6", "schritt", ("Ende und Bewertung", "End and verdict"),
              ("langsam ab {tracelog.SLOW_S} s", "slow from {tracelog.SLOW_S} s"),
              ("Am Ende bekommt der Datensatz seinen Zustand: Fehler, wenn ein Fehlerwort gesetzt ist, langsam, wenn "
               "der erste Ton später als {tracelog.SLOW_S} s kam, sonst gut.",
               "At the end the record gets its state: error if an error word is set, slow if the first sound came "
               "later than {tracelog.SLOW_S} s, else good.")),
            S("s7", "frage", ("Anfragen verfolgen an?", "Trace requests on?"),
              ("sonst nur Live oder Fälle", "else only Live or cases"),
              ("Ist nur Live oder der Einstellungs-Assistent an, endet der Datensatz hier. Er wird nirgends "
               "geschrieben.",
               "If only Live or the settings assistant is on, the record ends here. It is written nowhere."),
              ("stop", "nein", ("Nicht gespeichert", "Not stored"))),
            S("s8", "schritt", ("Zeile „anfrage:“ ins Journal", "Line „anfrage:“ into the journal"),
              ("Kanal, Werkzeuge, Zeiten, Zustand", "channel, tools, times, state"),
              ("Eine Zeile pro Anfrage: Kennung, Kanal, Einordnung, Werkzeuge mit ok oder nicht ok, Zeit bis zur "
               "Rückmeldung, bis zum ersten Ton und bis zum Ende. Ohne Namen.",
               "One line per request: id, channel, class, tools with ok or not ok, time to the instant reply, to the "
               "first sound and to the end. Without names.")),
            S("s9", "schritt", ("Anfrage-Verlauf auf der Platte", "Request history on disk"),
              ("state/traces.jsonl · {tracelog.MAX_TRACES} Anfragen", "state/traces.jsonl · {tracelog.MAX_TRACES} requests"),
              ("Der Datensatz wird angehängt. Wird die Datei zu groß, bleiben nur die letzten {tracelog.MAX_TRACES} "
               "Anfragen der letzten {tracelog.KEEP_S|min} Minuten. Die Datei ist in keiner Sicherung.",
               "The record is appended. When the file grows too big, only the last {tracelog.MAX_TRACES} requests of "
               "the last {tracelog.KEEP_S|min} minutes stay. The file is in no backup.")),
            S("s10", "schritt", ("Admin liest Logs → Anfragen", "Admin reads Logs → Requests"),
              ("Name nur mit Zustimmung", "name only with consent"),
              ("Nur Admin und Mit-Admins lesen den Verlauf, mit Rate-Limit. Name und Gerät eines Profils stehen nur da, "
               "wenn das Profil es erlaubt; sonst heißt es „Profil“. Zu einer Anfrage zeigt das Panel die "
               "Journal-Zeilen aus ihrer Zeit.",
               "Only the admin and co-admins read the history, with a rate limit. A profile's name and device show "
               "only when the profile allows it; else it says „Profil“. For one request the panel shows the journal "
               "lines from its time.")),
            S("s11", "schritt", ("Journal lesen und einordnen", "Read and sort the journal"),
              ("nur Zahlen gehen an journalctl", "only numbers reach journalctl"),
              ("logfilter liest höchstens {logfilter.READ_MAX} Zeilen; an journalctl gehen nur Zahlen aus festen "
               "Listen. Jede Zeile bekommt ihren Bereich aus dem ersten Wort, ihre Stufe aus festen Fehlerwörtern; "
               "Tokens, Schlüssel und Passwörter werden geschwärzt, bevor die Zeile das Panel verlässt.",
               "logfilter reads at most {logfilter.READ_MAX} lines; only numbers from fixed lists reach journalctl. "
               "Each line gets its area from its first word, its level from fixed error words; tokens, keys and "
               "passwords are blacked out before the line leaves the panel.")),
            S("s12", "ende", ("Diagnose mit festem Hinweis", "Diagnosis with a fixed hint"),
              ("Zähler pro Bereich, neuester Fehler", "counts per area, newest error"),
              ("Die Diagnose zählt Zeilen pro Bereich und zeigt zum neuesten Fehler einen festen Hinweis aus einer "
               "Liste, nie einen vom Modell.",
               "The diagnosis counts lines per area and shows a fixed hint from a list for the newest error, never "
               "one from the model.")),
        ],
        "beispiele": [
            (("Alles an, eine Frage mit Werkzeug", "All on, a question with a tool"),
             ["s1", "s2", "s3", "s4", "s4!", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Live zeigt den Weg, Logs → Anfragen behält ihn, das Journal hat die Zeile „anfrage:“.",
              "Live shows the way, Logs → Requests keeps it, the journal has the line „anfrage:“.")),
            (("Nur die Live-Seite an", "Only the live page on"),
             ["s1", "s2", "s3", "s4", "s4!", "s5", "s6", "s7", "s7!"],
             ("Auf Zustand → Live zu sehen, danach nirgends gespeichert.", "Visible on Status → Live, then stored nowhere.")),
            (("Alles aus", "Everything off"), ["s1", "s2", "s2!"],
             ("Kein Datensatz; nur die Journal-Zeilen der Module.", "No record; only the modules' journal lines.")),
        ],
        "regeln": [
            [("Spur", "Trace"), ("Wo", "Where"), ("Wie lange", "How long"), ("In der Sicherung", "In the backup")],
            [("Live", "Live"), ("Speicher", "memory"), ("bis zum Neustart", "until restart"), "✕"],
            [("Anfrage-Verlauf", "Request history"), ("state/traces.jsonl", "state/traces.jsonl"), ("{tracelog.KEEP_S|min} min", "{tracelog.KEEP_S|min} min"), "✕"],
            [("Journal", "Journal"), ("journald", "journald"), ("wie journald eingestellt ist", "as journald is set"), "✕"],
            [("Dienst-Wächter", "Service watch"), ("state/dienstwacht.json", "state/dienstwacht.json"), ("Ausfälle {dienstwacht.KEEP_LOG|min} min", "outages {dienstwacht.KEEP_LOG|min} min"), "✓"],
            [("Sicherungen", "Backups"), ("backups/", "backups/"), ("{backup.KEEP} tägliche, {backup.KEEP_EVENT} andere", "{backup.KEEP} daily, {backup.KEEP_EVENT} others"), ""],
        ],
        "zahlen": [
            ("{tracelog.MAX_TRACES}", ("Anfragen im Verlauf höchstens", "requests in the history at most"), "tracelog.MAX_TRACES"),
            ("{tracelog.KEEP_S|min} min", ("so lange bleibt eine Anfrage", "so long a request stays"), "tracelog.KEEP_S"),
            ("{tracelog.SLOW_S} s", ("ab hier gilt eine Anfrage als langsam", "from here a request counts as slow"), "tracelog.SLOW_S"),
            ("{dienstwacht.FAIL_N}", ("Fehlproben in Folge, bis ein Dienst als weg gilt", "failed probes in a row until a service counts as gone"), "dienstwacht.FAIL_N"),
            ("{dienstwacht.REPEAT|min} min", ("höchstens eine Ausfall-Meldung pro Dienst", "at most one outage note per service"), "dienstwacht.REPEAT"),
            ("{backup.KEEP}", ("tägliche und eigene Sicherungen, die bleiben", "daily and manual backups kept"), "backup.KEEP"),
        ],
        "einstellen": [
            ("Einstellungen → Spark → Betrieb → Anfragen verfolgen: Logs → Anfragen (Standard aus).",
             "Settings → Spark → Operation → Trace requests: Logs → Requests (default off)."),
            ("Einstellungen → Spark → Betrieb → Logs „Live-Seite“: Zustand → Live (Standard aus).",
             "Settings → Spark → Operation → Logs “Live page”: Status → Live (default off)."),
            ("Funktionen → Dienst-Wächter: Dienste prüfen und Admins bei Ausfall benachrichtigen (Standard aus).",
             "Features → Service watch: look at services and tell the admins about outages (default off)."),
            ("Einstellungen → Sicherung: eine Sicherung von Hand anlegen oder zurückspielen.",
             "Settings → Backup: create a backup by hand or restore one."),
        ],
        "sehen": [
            ("Zustand → Logs → Anfragen: der Weg jeder Anfrage mit Werkzeugen und Zeiten.",
             "Status → Logs → Requests: the way of every request with tools and times."),
            ("Zustand → Logs → Diagnose: Zeilen nach Bereich, Fehler und Warnungen, mit festem Hinweis.",
             "Status → Logs → Diagnosis: lines by area, errors and warnings, with a fixed hint."),
            ("Zustand → Live: laufende Anfragen, Wächter-Entscheidungen und Dienste als Bild.",
             "Status → Live: running requests, guard decisions and services as a picture."),
            ("Zustand → Dienste: was der Dienst-Wächter prüft und die Ausfälle der letzten Tage.",
             "Status → Services: what the service watch looks at and the outages of the last days."),
        ],
        "mehr": [
            (("Dienst-Wächter", "Service watch"), [
                ("Eine Schleife prüft Sprachmodell, Hören, Sprechen, Internet, SearXNG, Kiwix, Home Assistant, Mail, "
                 "Kalender und NAS, je nach Dienst jede Minute oder alle {dienstwacht.SLOW|min} Minuten, ohne "
                 "Anmeldung: eine HTTP-Antwort unter 500 gilt als „antwortet“.",
                 "A loop looks at the language model, listening, speaking, internet, SearXNG, Kiwix, Home Assistant, "
                 "mail, calendar and NAS, each every minute or every {dienstwacht.SLOW|min} minutes, without login: "
                 "an HTTP answer below 500 counts as „answers“."),
                ("Weg ist ein Dienst nach {dienstwacht.FAIL_N} Fehlproben über mindestens {dienstwacht.FAIL_S|min} "
                 "Minuten, zurück nach {dienstwacht.OK_N} guten. Ist das Internet weg, gibt es eine Meldung für alles "
                 "dahinter. Während Update, Start und Notaus Stufe 2 zählt nichts.",
                 "A service is gone after {dienstwacht.FAIL_N} failed probes over at least {dienstwacht.FAIL_S|min} "
                 "minutes, back after {dienstwacht.OK_N} good ones. With the internet gone there is one note for "
                 "everything behind it. During update, start and kill switch stage 2 nothing counts."),
                ("Die Proben gehen über den Wächter, zählen aber nicht auf der Live-Liste und lösen nie „Notaus von "
                 "selbst“ aus.",
                 "The probes go through the guard but do not count on the live list and never trigger the automatic "
                 "kill switch."),
            ]),
            (("Sicherung", "Backup"), [
                ("Einmal am Tag packt das Panel in einer Pause users/, voices/, config.json, das Panel-Passwort und die "
                 "Dateien aus backup.STATE_FILES. Der Schlüssel state/secret.key und die Anmeldeschlüssel sind nicht "
                 "dabei; Datenbanken werden als stimmige Kopie gesichert.",
                 "Once a day in a pause the panel packs users/, voices/, config.json, the panel password and the files "
                 "of backup.STATE_FILES. The key state/secret.key and the login keys are not in it; databases are "
                 "saved as a consistent copy."),
            ]),
        ],
        "code": [
            ("tracelog.start", ("ein Datensatz, wenn etwas an ist", "a record when anything is on")),
            ("tracelog.safe", ("nur Zahlen und kurze feste Wörter", "only numbers and short fixed words")),
            ("tracelog.Rec", ("Schritte, Marken, Zustand", "steps, marks, state")),
            ("tracelog.finish", ("Journal-Zeile und Anfrage-Verlauf", "journal line and request history")),
            ("tracelog.shown", ("Name nur mit Zustimmung", "name only with consent")),
            ("live.step", ("jeder Schritt auf Zustand → Live", "every step on Status → Live")),
            ("logfilter.AREAS", ("die Bereichswörter des Journals", "the journal's area words")),
            ("logfilter.parse", ("Bereich, Stufe, Schwärzen", "area, level, blacking out")),
            ("logfilter.summary", ("Zähler und fester Hinweis", "counts and fixed hint")),
            ("dienstwacht.round_once", ("eine Runde Proben und Meldungen", "one round of probes and notes")),
            ("backup.create", ("eine Sicherung packen", "pack one backup")),
        ],
        "tests": ["test_tracelog", "test_live", "test_logfilter", "test_log_luecken", "test_dienstwacht", "test_hardening",
                  "test_panel"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Dienste draußen
    "aussen": {
        "stand": "44257a9cc2",
        "bezug": {
            "dienstwacht.TIMEOUT": ["s5"], "notaus.locked_tools": ["s3"], "dienstwacht.tool_down": ["s5"],
            "netguard.client": ["s8", "s9", "s10"], "netguard.IMAP4_SSL": ["s9"],
            "homeassistant._client": ["s7", "s9"], "mcp._client": ["s7", "s9", "s10"],
            "chat.web_search": ["s6", "s9"], "regeln": ["s7", "s8"], "regel:SearXNG": ["s6"],
            "regel:Wetter, Fahrplan, Wikipedia": ["s6"], "regel:Sprachmodell": ["s6"],
        },
        "kurz": ("Dienste draußen sind alles, was der Spark über das Netz fragt: Home Assistant, Kalender, Kontakte, "
                 "Mail, SearXNG, Kiwix, reMarkable und MCP-Dienste. Adressen aus Einstellungen gehen über den Wächter "
                 "(netguard) mit einer festen Stufe; feste Dienste wie SearXNG, Wetter, Fahrplan und Wikipedia gehen "
                 "direkt.",
                 "Outside services are everything the Spark asks over the network: Home Assistant, calendars, "
                 "contacts, mail, SearXNG, Kiwix, reMarkable and MCP services. Addresses from settings go through the "
                 "guard (netguard) with a fixed level; fixed services like SearXNG, weather, transit and Wikipedia go "
                 "directly."),
        "warum": ("Ein Werkzeugaufruf kommt vom Modell, und das Modell kann von fremdem Text gelenkt sein. Deshalb "
                  "prüft das Panel vor jedem Aufruf mit festen Regeln, ob er sein darf, und behandelt jede Antwort von "
                  "draußen als Daten.",
                  "A tool call comes from the model, and the model can be steered by outside text. So the panel "
                  "checks by fixed rules before every call whether it may happen, and treats every answer from "
                  "outside as data."),
        "ablauf": [
            S("s1", "start", ("Modell ruft ein Werkzeug", "Model calls a tool"),
              ("chat_tools.run", "chat_tools.run"),
              ("Das Modell nennt ein Werkzeug und Angaben dazu. Wer fragt, steht schon fest (Anmeldung); die "
               "Zugangsdaten des Dienstes liegen versiegelt beim Profil und gehen nie ans Modell.",
               "The model names a tool and details. Who asks is already known (login); the service's login data "
               "lies sealed with the profile and never goes to the model.")),
            S("s2", "frage", ("In dieser Runde angeboten?", "Offered in this round?"),
              ("sonst nicht ausgeführt", "else not run"),
              ("Nur Werkzeuge, die diese Runde angeboten hat, laufen. Ein anderer Name wird nicht ausgeführt.",
               "Only tools this round offered run. Another name is not run."),
              ("stop", "nein", ("Nicht angeboten", "Not offered"))),
            S("s3", "frage", ("Notaus hält es an?", "Kill switch holds it?"),
              ("ab Stufe {notaus.STAGE.internet} Internet, ab {notaus.STAGE.aktion} Handeln",
               "from stage {notaus.STAGE.internet} internet, from {notaus.STAGE.aktion} acting"),
              ("Der Notaus wird bei jedem Aufruf neu gelesen. Ab Stufe {notaus.STAGE.internet} sind die "
               "{notaus.INTERNET_TOOLS|anzahl} Werkzeuge gesperrt, die selbst ins Internet gehen (Websuche, Wetter, "
               "Fahrplan, Wikipedia, Pakete, Seiten lesen); ab Stufe {notaus.STAGE.aktion} oder mit „Mein Notaus“ "
               "jedes Werkzeug, das etwas ändert.",
               "The kill switch is read again for every call. From stage {notaus.STAGE.internet} the "
               "{notaus.INTERNET_TOOLS|anzahl} tools that go to the internet by themselves are locked (web search, "
               "weather, transit, Wikipedia, parcels, reading pages); from stage {notaus.STAGE.aktion} or with „My "
               "kill switch“ every tool that changes something."),
              ("stop", "ja", ("Gesperrt (Notaus)", "Blocked (kill switch)"))),
            S("s4", "frage", ("Schon Text von außen gelesen?", "Outside text read already?"),
              ("dann nichts mehr ändern", "then change nothing more"),
              ("Hat die Antwort schon Mails, Webseiten, Kalender, Dokumente oder ein Archiv gelesen, darf sie nichts "
               "mehr schalten, merken oder eintragen. Die Person muss das in einer neuen Nachricht selbst sagen.",
               "If the answer already read mail, web pages, calendar, documents or an archive, it may no longer "
               "switch, save or enter anything. The person has to say so in a new message."),
              ("stop", "ja", ("Gesperrt nach Text von außen", "Blocked after outside text"))),
            S("s5", "frage", ("Dienst als weg bekannt?", "Service known to be gone?"),
              ("Hinweis, wenn ein Dienst fehlt", "note when a service is missing"),
              ("Sieht der Dienst-Wächter den Dienst dieses Werkzeugs als weg (und ist der Hinweis an), antwortet das "
               "Werkzeug sofort mit einem festen Satz, statt zu warten. Die Websuche versucht dann das eigene Kiwix.",
               "If the service watch sees this tool's service as gone (and the note is on), the tool answers at once "
               "with a fixed sentence instead of waiting. The web search then tries the own Kiwix."),
              ("stop", "ja", ("Fester Satz: gerade nicht erreichbar", "Fixed sentence: not reachable right now"))),
            S("s6", "frage", ("Fester eigener Weg?", "Fixed own way?"),
              ("netguard.DIRECT_OK", "netguard.DIRECT_OK"),
              ("Das Sprachmodell, SearXNG an der eingetragenen Adresse, Wetter, Fahrplan, Wikipedia und feste Dienste "
               "wie Apple-Push laufen direkt, ohne Wächter. Welche Module das dürfen und warum, steht in "
               "netguard.DIRECT_OK; ein Selbsttest meldet jedes Modul, das direkt verbindet und dort fehlt.",
               "The language model, SearXNG at the entered address, weather, transit, Wikipedia and fixed services "
               "like Apple push go directly, without the guard. Which modules may do that and why is listed in "
               "netguard.DIRECT_OK; a self-test reports every module that connects directly and is missing there."),
              ("ok", "ja", "s9")),
            S("s7", "schritt", ("Stufe des Dienstes", "Level of the service"),
              ("Heimnetz · Nutzer · nur Internet", "home · user · internet only"),
              ("Jedes Modul ruft den Wächter mit seiner festen Stufe: Home Assistant und Kiwix mit Heimnetz; Kalender, "
               "Kontakte, Aufgaben, Mail und MCP mit Nutzer; reMarkable und Seiten aus der Suche mit nur Internet. "
               "Die Stufe steht im Code, nicht in den Einstellungen.",
               "Each module calls the guard with its fixed level: Home Assistant and Kiwix with home; calendars, "
               "contacts, tasks, mail and MCP with user; reMarkable and pages from search with internet only. The "
               "level is in the code, not in the settings.")),
            S("s8", "frage", ("Wächter erlaubt die Adresse?", "Guard allows the address?"),
              ("Kasten Wächter", "box Guard"),
              ("Der Wächter löst den Namen einmal auf und prüft jede Adresse: keine eigenen Dienste, kein 169.254, "
               "Heimnetz nur auf Stufe Heimnetz oder mit Schalter, im Notaus kein Internet. Danach verbindet er genau "
               "mit der geprüften Adresse.",
               "The guard resolves the name once and checks every address: no own services, no 169.254, home network "
               "only at level home or with the switch, no internet during the kill switch. Then it connects to "
               "exactly the checked address."),
              ("stop", "nein", ("Gesperrt", "Blocked"))),
            S("s9", "schritt", ("Anfrage an den Dienst", "Request to the service"),
              ("mit versiegeltem Zugang", "with sealed login"),
              ("Das Panel öffnet den Zugang des Profils (Token, Passwort) erst jetzt und schickt ihn nur an die "
               "eingetragene Seite. Mail geht über IMAP mit TLS an die geprüfte Adresse.",
               "The panel unseals the profile's login (token, password) only now and sends it only to the entered "
               "site. Mail goes over IMAP with TLS to the checked address.")),
            S("s10", "frage", ("Antwort zu groß?", "Answer too large?"),
              ("höchstens {netguard.MAX_BYTES|mb}, MCP {mcp.MAX_BYTES|mb}", "at most {netguard.MAX_BYTES|mb}, MCP {mcp.MAX_BYTES|mb}"),
              ("Über den Wächter wird jede Antwort an der Grenze des Moduls abgeschnitten, auch nach dem Entpacken.",
               "Through the guard each answer is cut at the module's limit, also after unpacking."),
              ("stop", "ja", ("Abbruch", "Stopped"))),
            S("s11", "schritt", ("Ergebnis für Mein Zustand und Live", "Result for My status and Live"),
              ("nur ob es antwortet", "only whether it answers"),
              ("Ob der Dienst geantwortet oder die Anmeldung abgelehnt hat, sieht das Profil unter Ich → Mein Zustand; "
               "die Live-Seite zählt, was der Wächter erlaubt oder gesperrt hat. Inhalte gehen nirgends hin.",
               "Whether the service answered or refused the login, the profile sees under Me → My status; the live "
               "page counts what the guard allowed or blocked. Contents go nowhere.")),
            S("s12", "ende", ("Antwort als Daten ans Modell", "Answer as data to the model"),
              ("Text von außen", "outside text"),
              ("Das Werkzeug gibt die Antwort als Daten zurück. Liest es fremden Text (Mail, Kalender, Archiv, "
               "Webseite, MCP im Lesemodus), gilt die Antwort ab jetzt als eine mit Text von außen; siehe Schritt 4.",
               "The tool returns the answer as data. If it reads someone else's text (mail, calendar, archive, web "
               "page, MCP in read mode), the answer counts from now on as one with outside text; see step 4.")),
        ],
        "beispiele": [
            (("Licht im Wohnzimmer an", "Living room light on"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Home Assistant im Heimnetz über die Stufe Heimnetz; geschaltet.", "Home Assistant in the home network at level home; switched.")),
            (("Websuche", "Web search"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s9", "s10", "s11", "s12"],
             ("SearXNG direkt; Seiten aus den Treffern gehen danach über den Wächter.",
              "SearXNG directly; pages from the results then go through the guard.")),
            (("Notaus Stufe 1, Wetter fragen", "Kill switch stage 1, ask weather"), ["s1", "s2", "s3", "s3!"],
             ("Gesperrt, bevor irgendetwas hinausgeht.", "Blocked before anything goes out.")),
            (("Licht schalten nach einer Mail", "Switch a light after a mail"), ["s1", "s2", "s3", "s4", "s4!"],
             ("Gesperrt: eine Mail darf nichts schalten.", "Blocked: a mail may not switch anything.")),
        ],
        "regeln": [
            [("Dienst", "Service"), ("Weg", "Way"), ("Stufe", "Level")],
            [("Home Assistant", "Home Assistant"), ("netguard.client", "netguard.client"), ("Heimnetz", "home")],
            [("Kiwix", "Kiwix"), ("netguard.client", "netguard.client"), ("Heimnetz", "home")],
            [("Kalender, Kontakte, Aufgaben", "Calendars, contacts, tasks"), ("netguard.client", "netguard.client"), ("Nutzer", "user")],
            [("Mail", "Mail"), ("netguard.IMAP4_SSL", "netguard.IMAP4_SSL"), ("Nutzer", "user")],
            [("MCP-Dienste", "MCP services"), ("netguard.client", "netguard.client"), ("Nutzer", "user")],
            [("reMarkable", "reMarkable"), ("netguard.client, nur erlaubte Hosts", "netguard.client, allowed hosts only"), ("nur Internet", "internet only")],
            [("SearXNG", "SearXNG"), ("direkt (netguard.DIRECT_OK)", "direct (netguard.DIRECT_OK)"), ""],
            [("Wetter, Fahrplan, Wikipedia", "Weather, transit, Wikipedia"), ("direkt, feste Adresse", "direct, fixed address"), ""],
            [("Sprachmodell", "Language model"), ("direkt (eigener Dienst)", "direct (own service)"), ""],
        ],
        "zahlen": [
            ("{netguard.MAX_BYTES|mb}", ("größte Antwort über den Wächter", "largest answer through the guard"), "netguard.MAX_BYTES"),
            ("{mcp.MAX_BYTES|mb}", ("größte Antwort eines MCP-Dienstes", "largest answer of an MCP service"), "mcp.MAX_BYTES"),
            ("{notaus.INTERNET_TOOLS|anzahl}", ("Werkzeuge, die ab Notaus-Stufe {notaus.STAGE.internet} ruhen", "tools that rest from kill switch stage {notaus.STAGE.internet}"), "notaus.INTERNET_TOOLS"),
            ("{dienstwacht.TIMEOUT} s", ("längste Probe des Dienst-Wächters", "longest probe of the service watch"), "dienstwacht.TIMEOUT"),
        ],
        "einstellen": [
            ("Einstellungen → Sicherheit → Heimnetz-Adressen erlauben: Kalender, Kontakte, Mail und MCP dürfen auch ins "
             "Heimnetz (Standard aus).",
             "Settings → Security → Allow home network addresses: calendars, contacts, mail and MCP may also go to the "
             "home network (default off)."),
            ("Funktionen → Agent-Funktionen → Dienste per MCP: welche Server und Werkzeuge angeboten werden.",
             "Features → Agent functions → Services over MCP: which servers and tools are offered."),
            ("Funktionen → Dienst-Wächter: Ausfälle sehen, darunter der Hinweis an Nutzer, wenn ein Dienst fehlt.",
             "Features → Service watch: see outages, below it the note to users when a service is missing."),
        ],
        "sehen": [
            ("Zustand → Live: jede Verbindung nach außen als Linie, gesperrte mit Grund.",
             "Status → Live: every connection to the outside as a line, blocked ones with the reason."),
            ("Ich → Mein Zustand: ob der eigene Kalender, die Mail oder Home Assistant antwortet.",
             "Me → My status: whether the own calendar, mail or Home Assistant answers."),
            ("Zustand → Dienste: was gerade erreichbar ist.", "Status → Services: what is reachable right now."),
        ],
        "code": [
            ("chat_tools.run", ("angeboten, Notaus, Text von außen, Dienst weg", "offered, kill switch, outside text, service gone")),
            ("notaus.locked_tools", ("welche Werkzeuge der Notaus sperrt", "which tools the kill switch locks")),
            ("notaus.INTERNET_TOOLS", ("Werkzeuge, die selbst ins Internet gehen", "tools that go to the internet by themselves")),
            ("dienstwacht.tool_down", ("fester Satz, wenn der Dienst weg ist", "fixed sentence when the service is gone")),
            ("netguard.DIRECT_OK", ("wer direkt verbinden darf und warum", "who may connect directly and why")),
            ("netguard.client", ("der Zugang über den Wächter", "the way through the guard")),
            ("netguard.IMAP4_SSL", ("Mail an die geprüfte Adresse", "mail to the checked address")),
            ("homeassistant._client", ("Home Assistant mit Stufe Heimnetz", "Home Assistant at level home")),
            ("mcp._client", ("MCP-Server mit Stufe Nutzer", "MCP server at level user")),
            ("chat.web_search", ("SearXNG direkt", "SearXNG directly")),
        ],
        "tests": ["test_waechter_umgehung", "test_notaus", "test_sperre_ueberall", "test_dienstwacht", "test_kiwix",
                  "test_meinmcp", "test_remarkable"],
        "heute": [("guard_ok", ("verbunden", "connected")), ("guard_bad", ("gesperrt", "blocked"))],
    },
    # ------------------------------------------------------------------ Browser und Handy
    "geraet": {
        "stand": "b79f98a912",
        "bezug": {
            "account.CONVO_BODY": ["s10"], "admin.test_asr": ["s4"], "admin._test_asr": ["s4", "s5"],
            "admin.read_audio": ["s4"], "chat.chat": ["s6", "s7"], "account.profile_save_convo": ["s10"],
            "account.profile_convos": ["s11"], "profiles.append_convo": ["s10"], "profiles._clean_convo": ["s10"],
            "verlauf.stream": ["s11"], "verlauf.begin": ["s6", "s11"], "regeln": ["s6", "s10"],
        },
        "kurz": ("Die Seite im Browser (static/js/chat.js) ist das Gerät: sie nimmt die Frage auf, schickt den Ton zur "
                 "Spracherkennung, schickt den Text an /api/chat und spielt Text und Ton aus einem einzigen Strom ab. "
                 "Die Gespräche eines Profils liegen auf dem Spark, jede offene Seite gleicht sie ab.",
                 "The page in the browser (static/js/chat.js) is the device: it records the question, sends the sound "
                 "to speech recognition, sends the text to /api/chat and plays text and sound from one single stream. "
                 "A profile's conversations live on the Spark, every open page keeps them in step."),
        "warum": ("Gerechnet wird nur auf dem Spark; die Seite bleibt dünn. Browser, Handy-Browser und die Android-App "
                  "(eine WebView) nehmen denselben Weg, deshalb gelten Anmeldung, Grenzen und Regeln an genau einer "
                  "Stelle, und ein Gespräch sieht auf jedem Gerät gleich aus.",
                  "All the computing happens on the Spark; the page stays thin. Browser, phone browser and the Android "
                  "app (a WebView) take the same way, so login, limits and rules apply in exactly one place, and a "
                  "conversation looks the same on every device."),
        "ablauf": [
            S("s1", "start", ("„Sprechen“ getippt", "„Speak“ tapped"),
              ("oder Weckwort, freihändig, Nachfrage", "or wake word, hands-free, follow-up"),
              ("startListening holt das Mikrofon und merkt sich, wie es aufging: von Hand, nach einer Antwort "
               "(Nachfrage), freihändig oder durch Dazwischenreden. Ein Mikrofon, das die Seite selbst geöffnet hat, "
               "nimmt später nur eine bekannte Stimme an.",
               "startListening gets the microphone and remembers how it opened: by hand, after an answer (follow-up), "
               "hands-free or by talking over the answer. A microphone the page opened by itself later only takes a "
               "known voice.")),
            S("s2", "frage", ("Sichere Verbindung?", "Secure connection?"),
              ("Mikrofon nur über https", "microphone only over https"),
              ("Browser geben das Mikrofon nur auf einer sicheren Seite frei. Ohne https zeigt die Seite einen Hinweis "
               "mit der https-Adresse des Panels und nimmt nichts auf.",
               "Browsers only hand out the microphone on a secure page. Without https the page shows a note with the "
               "panel's https address and records nothing."),
              ("stop", "nein", ("Hinweis: Mikrofon braucht https", "Note: the microphone needs https"))),
            S("s3", "schritt", ("Aufnehmen, Satzende erkennen", "Record, find the end of the sentence"),
              ("Pegel, Live-Text, natürlicher Sprecherwechsel", "level, live text, natural turn-taking"),
              ("MediaRecorder nimmt auf, ein Pegelmesser hört auf Stille. Etwa jede Sekunde geht die Aufnahme bis "
               "jetzt zur Spracherkennung und erscheint als blasse Blase. Endet der Satz mit Punkt, Frage- oder "
               "Ausrufezeichen, ist die Frage sofort fertig; endet er auf „und“, „weil“, „ähm“ oder einem Komma, "
               "wartet die Seite etwas länger.",
               "MediaRecorder records, a level meter listens for silence. About every second the recording so far "
               "goes to speech recognition and shows as a pale bubble. If the sentence ends with a full stop, question "
               "or exclamation mark, the question is done at once; if it ends on „and“, „because“, „uhm“ or a comma, "
               "the page waits a little longer.")),
            S("s4", "schritt", ("Ton an /api/test/asr", "Sound to /api/test/asr"),
              ("als WAV, höchstens {admin.MAX_AUDIO|mb}", "as WAV, at most {admin.MAX_AUDIO|mb}"),
              ("Die Seite wandelt die Aufnahme in ein einfaches WAV in Mono (sonst geht das Original). Der Spark prüft "
               "das Rate-Limit ({guard.RATE.asr.1} pro Minute für ein Profil, Gäste höchstens {guard.BUSY.asr} "
               "gleichzeitig), liest höchstens {admin.MAX_AUDIO|mb} und schickt den Ton an die Spracherkennung. "
               "Nebenher misst er auf der CPU, wie viel davon Stimme ist und wessen Stimme es ist.",
               "The page turns the recording into a plain mono WAV (else the original goes). The Spark checks the rate "
               "limit ({guard.RATE.asr.1} per minute for a profile, guests at most {guard.BUSY.asr} at once), reads at "
               "most {admin.MAX_AUDIO|mb} and sends the sound to speech recognition. Alongside it measures on the CPU "
               "how much of it is voice and whose voice it is.")),
            S("s5", "frage", ("Stille, eigene oder fremde Stimme?", "Silence, own or foreign voice?"),
              ("stille · echo · fremdstimme", "stille · echo · fremdstimme"),
              ("Feste Regeln, kein Modell: ein „Ja“ aus Stille oder einem Klick (stille.check), die eigene Stimme des "
               "Spark von einem anderen Gerät (echo.check) und bei selbst geöffnetem Mikrofon eine fremde Stimme, etwa "
               "vom Fernseher (fremdstimme.check), sind keine Frage. Die Antwort ist dann leerer Text mit dem Grund.",
               "Fixed rules, no model: a „yes“ out of silence or a click (stille.check), the Spark's own voice from "
               "another device (echo.check) and, with a microphone the page opened itself, a foreign voice like the TV "
               "(fremdstimme.check) are no question. The answer is then empty text with the reason."),
              ("stop", "ja", ("Überhört, nichts gesendet", "Ignored, nothing sent"))),
            S("s6", "schritt", ("Frage an /api/chat", "Question to /api/chat"),
              ("Verlauf, Gespräch, Stimme, Stimm-Token", "history, conversation, voice, voice token"),
              ("Die Seite schickt die letzten Nachrichten des offenen Gesprächs, seine Kennung, Stimme, Tempo und, wenn "
               "die Stimme erkannt wurde, ein signiertes Einmal-Token. Der Spark prüft das Rate-Limit "
               "({guard.RATE.chat.1} pro Minute für ein Profil, Gäste höchstens {guard.BUSY.chat} gleichzeitig), "
               "lässt Hintergrundarbeit warten (vorrang) und sagt den anderen offenen Seiten des Profils „antwortet "
               "gerade“ (nur die Art des Geräts).",
               "The page sends the last messages of the open conversation, its id, voice, speed and, when the voice "
               "was recognized, a signed one-time token. The Spark checks the rate limit ({guard.RATE.chat.1} per "
               "minute for a profile, guests at most {guard.BUSY.chat} at once), lets background work wait (vorrang) "
               "and tells the profile's other open pages „answering“ (only the kind of device).")),
            S("s7", "schritt", ("Text und Ton in einem Strom", "Text and sound in one stream"),
              ("Server-Sent Events", "server-sent events"),
              ("Die Antwort kommt als Ereignisse: Textstücke, Tonstücke, Suche, Quellen, Rückfragen, Fehler. Der Text "
               "wird höchstens einmal pro Bild neu gezeichnet. Der Ton läuft in einem eigenen Audio-Kontext mit der "
               "Rate der Sprachausgabe; jedes Stück endet mit einer kurzen Blende, damit die Nähte nicht knacken.",
               "The answer comes as events: pieces of text, pieces of sound, search, sources, questions back, errors. "
               "The text is redrawn at most once per frame. The sound plays in its own audio context at the speech "
               "output's rate; every piece ends with a short fade so the seams do not click.")),
            S("s8", "frage", ("Spricht jemand dazwischen?", "Someone talking over it?"),
              ("Unterbrechen beim Vorlesen", "interrupting while it speaks"),
              ("Während die Antwort spielt, hört das Mikrofon weiter. Ist der Pegel eine Weile deutlich über der "
               "eigenen Ausgabe und dem Raum (Fernseher), bricht die Antwort ab, und die schon laufende Aufnahme wird "
               "die nächste Frage.",
               "While the answer plays, the microphone keeps listening. If the level stays clearly above the own "
               "output and the room (TV) for a moment, the answer stops and the recording already running becomes the "
               "next question."),
              ("zurueck", "ja", "s4")),
            S("s9", "frage", ("Fehler im Strom?", "Error in the stream?"),
              ("in einfachen Worten", "in plain words"),
              ("Ein Fehler erscheint unter der Antwort in einfachen Worten; der Admin sieht zusätzlich die technische "
               "Angabe, Gäste nur die Art des Fehlers. Fehlt nur die Sprachausgabe, bleibt die Antwort als Text.",
               "An error shows under the answer in plain words; the admin also sees the technical detail, guests only "
               "the kind of error. If only speech output failed, the answer stays as text."),
              ("info", "ja", ("Antwort als Text oder Hinweis", "Answer as text or a note"))),
            S("s10", "schritt", ("Gespräch speichern", "Store the conversation"),
              ("nur die neuen Nachrichten", "only the new messages"),
              ("Bei einem Profil schickt die Seite nur die neuen Nachrichten (PUT /api/profile/convos mit „add“). Der "
               "Spark hängt sie unter einer Sperre an seine Kopie an, damit ein anderes Gerät nichts überschreibt, und "
               "behält höchstens {profiles.MAX_CONVOS} Gespräche mit je {profiles.MAX_MSGS} Nachrichten.",
               "For a profile the page sends only the new messages (PUT /api/profile/convos with „add“). The Spark "
               "appends them to its copy under a lock, so another device overwrites nothing, and keeps at most "
               "{profiles.MAX_CONVOS} conversations of {profiles.MAX_MSGS} messages each."),
              ("info", ("Gast", "guest"), ("Gäste: nur in diesem Browser", "Guests: in this browser only"))),
            S("s11", "schritt", ("Abgleich mit anderen Geräten", "Sync with other devices"),
              ("?since= · Sofort-Abgleich", "?since= · instant sync"),
              ("Kommt die Seite wieder nach vorn und regelmäßig dazwischen, fragt sie, was sich seit dem letzten Mal "
               "geändert hat; ein anderswo gelöschtes Gespräch schließt sich. Mit dem Sofort-Abgleich hält jede Seite "
               "einen Ereignis-Strom offen, der nur „Gespräch geändert“ und „antwortet gerade“ meldet, nie Inhalte "
               "(höchstens {verlauf.MAX_STREAMS} pro Profil, je {verlauf.STREAM_SECONDS|min} Minuten).",
               "When the page comes to the front again, and regularly in between, it asks what changed since last "
               "time; a conversation deleted elsewhere closes. With instant sync every page keeps an event stream open "
               "that only reports „conversation changed“ and „answering“, never contents (at most "
               "{verlauf.MAX_STREAMS} per profile, {verlauf.STREAM_SECONDS|min} minutes each).")),
            S("s12", "ende", ("Bereit", "Ready"),
              ("wartet, bis der Ton zu Ende ist", "waits until the sound has ended"),
              ("Die Seite wartet, bis die Antwort ausgesprochen ist. Freihändig oder nach einer gesprochenen Frage "
               "mit Nachfrage-Fenster öffnet sie das Mikrofon wieder.",
               "The page waits until the answer is spoken. Hands-free, or after a spoken question with a follow-up "
               "window, it opens the microphone again."),
              ("zurueck", ("freihändig, Nachfrage", "hands-free, follow-up"), "s3")),
        ],
        "beispiele": [
            (("Gesprochene Frage eines Profils", "Spoken question of a profile"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Antwort gehört, auf dem Spark gespeichert, auf den anderen Geräten sichtbar.",
              "Answer heard, stored on the Spark, visible on the other devices.")),
            (("Panel über http geöffnet", "Panel opened over http"), ["s1", "s2", "s2!"],
             ("Kein Mikrofon: die Seite zeigt die https-Adresse.", "No microphone: the page shows the https address.")),
            (("Fernseher im Nachfrage-Fenster", "TV in the follow-up window"), ["s1", "s2", "s3", "s4", "s5", "s5!"],
             ("Überhört: fremde Stimme, es geht keine Frage raus.", "Ignored: a foreign voice, no question goes out.")),
            (("Dazwischenreden", "Talking over the answer"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!", "s4"],
             ("Die Antwort bricht ab, das Gesagte wird die nächste Frage.", "The answer stops, what was said becomes the next question.")),
        ],
        "regeln": [
            [("Wer", "Who"), ("Gespräche liegen", "Conversations live"), ("Fragen pro Minute", "Questions per minute"),
             ("gleichzeitig", "at once")],
            [("Profil", "profile"), ("auf dem Spark, gleich auf jedem Gerät", "on the Spark, the same on every device"),
             "{guard.RATE.chat.1}", ("ohne feste Grenze", "no fixed limit")],
            [("Gast", "guest"), ("nur in diesem Browser", "in this browser only"), "{guard.RATE.chat.0}",
             ("{guard.BUSY.chat} Gäste zusammen", "{guard.BUSY.chat} guests together")],
        ],
        "zahlen": [
            ("{admin.MAX_AUDIO|mb}", ("größte Aufnahme", "largest recording"), "admin.MAX_AUDIO"),
            ("{guard.RATE.chat.1}", ("Fragen pro Minute und Profil", "questions per minute and profile"), "guard.RATE"),
            ("{guard.BUSY.chat}", ("Gäste gleichzeitig im Chat", "guests in the chat at once"), "guard.BUSY"),
            ("{profiles.MAX_CONVOS}", ("Gespräche pro Profil", "conversations per profile"), "profiles.MAX_CONVOS"),
            ("{account.CONVO_BODY|mb}", ("größtes Gespräch beim Speichern", "largest conversation when storing"), "account.CONVO_BODY"),
            ("{verlauf.MAX_STREAMS}", ("offene Seiten mit Sofort-Abgleich pro Profil", "open pages with instant sync per profile"),
             "verlauf.MAX_STREAMS"),
        ],
        "einstellen": [
            ("Ich → Gespräch: die Gesprächs-Einstellungen des Profils, etwa Freihändig und Unterbrechen.",
             "Me → Conversation: the profile's conversation settings, such as hands-free and interrupting."),
            ("Funktionen → Verlauf sofort abgleichen: der Ereignis-Strom zwischen den offenen Seiten (Standard aus).",
             "Features → Instant history sync: the event stream between the open pages (default off)."),
        ],
        "sehen": [
            ("Unter jeder Antwort: Zeiten für Spracherkennung, erstes Wort, ersten Ton und Aussetzer der Sprachausgabe.",
             "Under every answer: times for recognition, first word, first sound and stalls of speech output."),
            ("Logs → Anfragen: jede Frage mit Eingang „Browser“ und ihren Schritten, ohne Inhalt.",
             "Logs → Requests: every question with the input „Browser“ and its steps, without content."),
            ("Zustand → Live: die laufende Anfrage im Bild.", "Status → Live: the running request in the picture."),
        ],
        "code": [
            ("admin.test_asr", ("Rate-Limit, Gast-Plätze, dann die Erkennung", "rate limit, guest places, then recognition")),
            ("admin._test_asr", ("Spracherkennung mit Stille-, Echo- und Fremdstimmen-Prüfung", "recognition with silence, echo and foreign voice checks")),
            ("admin.read_audio", ("liest die Aufnahme mit Größengrenze", "reads the recording with a size limit")),
            ("stille.check", ("Stille wird nie zu Worten", "silence never becomes words")),
            ("echo.check", ("die eigene Stimme des Spark ist keine Frage", "the Spark's own voice is no question")),
            ("chat.chat", ("Grenzen, Vorrang, „antwortet gerade“, dann der Strom", "limits, priority, „answering“, then the stream")),
            ("account.profile_save_convo", ("speichert nur die neuen Nachrichten", "stores only the new messages")),
            ("account.profile_convos", ("Liste und Änderungen seit ?since=", "list and changes since ?since=")),
            ("profiles.append_convo", ("hängt unter Sperre an", "appends under a lock")),
            ("profiles._clean_convo", ("prüft und kürzt ein Gespräch", "checks and trims a conversation")),
            ("verlauf.stream", ("der Sofort-Abgleich je offener Seite", "instant sync per open page")),
            ("verlauf.begin", ("„antwortet gerade“ für die anderen Seiten", "„answering“ for the other pages")),
        ],
        "tests": ["test_verlauf_sync", "test_stille", "test_echo", "test_fremdstimme", "test_follow_up"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Apps
    "apps": {
        "stand": "7857751f40",
        "bezug": {
            "android.TOKEN_SECONDS": ["s3"], "android.TOKEN_USES": ["s3"], "iphone.profile_pair": ["s1", "s2"],
            "iphone.new_code": ["s3"], "iphone.take_code": ["s4"], "iphone.app_pair": ["s4", "s5"],
            "iphone.app_hello": ["s9"], "profiles._app_path": ["s7"], "account.profile_remove_device": ["s11"],
            "android.apk_response": ["s3"], "regeln": ["s6", "s7"], "regel:ohne": ["s10"],
        },
        "kurz": ("Die iPhone-App bekommt beim Koppeln einen eigenen Geräteschlüssel des Profils und spricht damit "
                 "dieselben Endpunkte an wie der Browser. Der Schlüssel öffnet nur eine feste Liste von Pfaden. Die "
                 "Android-App hat keinen eigenen Schlüssel: sie zeigt das Panel in einer WebView und meldet sich an wie "
                 "ein Browser.",
                 "The iPhone app gets its own device key of the profile when it is paired and uses the same endpoints "
                 "as the browser with it. The key only opens a fixed list of paths. The Android app has no key of its "
                 "own: it shows the panel in a WebView and signs in like a browser."),
        "warum": ("Ein Handy geht verloren oder wird weitergegeben. Deshalb kann ein App-Schlüssel nur fragen und "
                  "zuhören, nie Konto, Geräte oder Sicherheit ändern, und er hört sofort auf zu gelten, wenn das Gerät "
                  "im Panel entfernt oder die App ausgeschaltet wird.",
                  "A phone gets lost or passed on. That is why an app key can only ask and listen, never change the "
                  "account, devices or security, and it stops working at once when the device is removed in the panel "
                  "or the app is switched off."),
        "ablauf": [
            S("s1", "start", ("Kopplung anfordern", "Ask for pairing"),
              ("Ich → iPhone, im eigenen Browser", "Me → iPhone, in the own browser"),
              ("Nur die eigene Browser-Anmeldung des Profils darf koppeln, nie ein Geräteschlüssel. Hat das Profil "
               "einen zweiten Anmeldeschritt, braucht es dafür einen Code, denn ein neuer Weg ins Profil entsteht.",
               "Only the profile's own browser login may pair, never a device key. If the profile has a second sign-in "
               "step it needs a code for this, because a new way into the profile is made.")),
            S("s2", "frage", ("App frei und Platz da?", "App allowed and room left?"),
              ("Admin-Schalter, Sperre, höchstens {iphone.MAX_PHONES}", "admin switch, block, at most {iphone.MAX_PHONES}"),
              ("Die App muss vom Admin eingeschaltet und für das Profil nicht gesperrt sein, und das Profil darf "
               "höchstens {iphone.MAX_PHONES} iPhones haben. Die Panel-Adresse muss mit https beginnen und ohne Pfad "
               "sein.",
               "The app must be switched on by the admin and not blocked for the profile, and the profile may have at "
               "most {iphone.MAX_PHONES} iPhones. The panel address must start with https and have no path."),
              ("stop", "nein", ("Abgelehnt", "Refused"))),
            S("s3", "schritt", ("Einmal-Link als QR-Code", "One-time link as QR code"),
              ("gilt {iphone.CODE_SECONDS|min} Minuten, einmal", "valid {iphone.CODE_SECONDS|min} minutes, once"),
              ("new_code macht einen zufälligen Code; im Speicher liegt nur sein Hash. Ein Profil hat höchstens "
               "{iphone.PER_PROFILE} offene Codes, der Spark höchstens {iphone.MAX_PENDING}. Der Link "
               "{iphone.SCHEME}://pair öffnet die App mit Adresse und Code.",
               "new_code makes a random code; only its hash is kept in memory. A profile has at most "
               "{iphone.PER_PROFILE} open codes, the Spark at most {iphone.MAX_PENDING}. The link {iphone.SCHEME}://pair "
               "opens the app with address and code.")),
            S("s4", "frage", ("Code gültig?", "Code valid?"),
              ("POST /api/iphone/pair", "POST /api/iphone/pair"),
              ("Die App schickt den Code. Der Spark prüft das Rate-Limit ({guard.RATE.pair.0} pro Minute und Adresse), "
               "vergleicht den Hash zeitkonstant und löscht den Code beim ersten Treffer. Ein abgelaufener oder schon "
               "benutzter Code passt nie.",
               "The app sends the code. The Spark checks the rate limit ({guard.RATE.pair.0} per minute and address), "
               "compares the hash in constant time and deletes the code at the first hit. An expired or used code "
               "never fits."),
              ("stop", "nein", ("Link passt nicht oder ist abgelaufen", "Link does not fit or has expired"))),
            S("s5", "schritt", ("Eigener Geräteschlüssel", "Own device key"),
              ("Bereich „app“, nur der Hash bleibt", "scope „app“, only the hash stays"),
              ("profiles.add_device erzeugt den Schlüssel und speichert nur seinen SHA-256-Hash in profiles.json. Die "
               "App bekommt ihn genau einmal und legt ihn im Schlüsselbund ab.",
               "profiles.add_device makes the key and stores only its SHA-256 hash in profiles.json. The app gets it "
               "exactly once and keeps it in the keychain."),
              ("info", ("Android", "Android"),
               ("Android: kein Schlüssel; Download-Link mit Einmal-Token, Anmeldung wie im Browser",
                "Android: no key; download link with a one-time token, sign-in as in the browser"))),
            S("s6", "schritt", ("Jede Anfrage mit Schlüssel", "Every request with the key"),
              ("Kopfzeile {profiles.DEVICE_HEADER}", "header {profiles.DEVICE_HEADER}"),
              ("profiles.current sucht den Hash des Schlüssels in der Geräteliste. Ein Geräteschlüssel geht vor dem "
               "Cookie; das Profil kommt so immer aus dem Schlüssel, nie aus dem, was die App schreibt.",
               "profiles.current looks up the key's hash in the device list. A device key comes before the cookie; "
               "the profile always comes from the key, never from what the app writes.")),
            S("s7", "frage", ("Pfad für die App erlaubt?", "Path allowed for the app?"),
              ("{profiles.APP_PATHS|anzahl} feste Pfade und freigegebene Bereiche", "{profiles.APP_PATHS|anzahl} fixed paths and opened areas"),
              ("Ein App-Schlüssel gilt nur für die {profiles.APP_PATHS|anzahl} Pfade in profiles.APP_PATHS (Chat, "
               "Spracherkennung, Gespräche, Erinnerungen, Chats …), ein paar Lese-Muster und die Panel-Bereiche, die "
               "das Profil für die App einzeln freigegeben hat. Alles andere sieht er ohne Profil.",
               "An app key only works for the {profiles.APP_PATHS|anzahl} paths in profiles.APP_PATHS (chat, speech "
               "recognition, conversations, reminders, chats …), a few read patterns and the panel areas the profile "
               "opened for the app one by one. Everything else it sees without a profile."),
              ("stop", "nein", ("Kein Profil (401)", "No profile (401)"))),
            S("s8", "frage", ("App gerade aus oder Mein Notaus?", "App off right now or My kill switch?"),
              ("503 statt 401: die Kopplung bleibt", "503 instead of 401: the pairing stays"),
              ("Ist die App vom Admin aus- oder für das Profil gesperrt, oder hat das Profil Mein Notaus an, gibt es "
               "für diese Anfrage kein Profil. Die App bekommt „gerade nicht“ (503), behält ihre Kopplung und geht "
               "wieder, sobald der Schalter zurück ist.",
               "If the app is switched off by the admin or blocked for the profile, or the profile has My kill switch "
               "on, this request has no profile. The app gets „not now“ (503), keeps its pairing and works again as "
               "soon as the switch is back."),
              ("stop", "ja", ("Gerade nicht (503)", "Not now (503)"))),
            S("s9", "schritt", ("Wie ein Browser des Profils", "Like a browser of the profile"),
              ("/api/chat · /api/test/asr · /api/profile/convos", "/api/chat · /api/test/asr · /api/profile/convos"),
              ("Die App fragt über dieselben Endpunkte wie die Seite, mit denselben Grenzen. Was sie zusätzlich darf "
               "(Smart Home, CarPlay, Zuhören, Dokumente, Bilder), sagt ihr der Spark in /api/iphone/hello; die App "
               "zeigt es nur an und hält sich daran.",
               "The app asks through the same endpoints as the page, with the same limits. What it may do on top "
               "(smart home, CarPlay, listening, documents, pictures) the Spark tells it in /api/iphone/hello; the app "
               "only shows it and follows it.")),
            S("s10", "frage", ("Konto, Geräte oder Sicherheit?", "Account, devices or security?"),
              ("nur im eigenen Browser", "only in the own browser"),
              ("Endpunkte, die Verbindungen, Geräte oder Sicherheit des Profils ändern, nehmen nur die eigene "
               "Browser-Anmeldung (core.browser_profile). Einen Geräteschlüssel lehnen sie ab, außer in einem Bereich, "
               "den das Profil der App freigegeben hat; Geheimnisse brauchen dort zusätzlich einen frischen Code.",
               "Endpoints that change the profile's connections, devices or security only take the own browser login "
               "(core.browser_profile). They refuse a device key, except in an area the profile opened for the app; "
               "secrets need a fresh code there as well."),
              ("stop", "ja", ("Nur im eigenen Browser (403)", "Only in the own browser (403)"))),
            S("s11", "ende", ("Entfernen wirkt sofort", "Removing works at once"),
              ("Ich → iPhone · Gerät entfernen", "Me → iPhone · remove device"),
              ("Wird das iPhone im Panel entfernt, verschwindet der Hash aus der Geräteliste. Die nächste Anfrage der "
               "App findet kein Profil mehr.",
               "When the iPhone is removed in the panel, its hash leaves the device list. The app's next request finds "
               "no profile any more.")),
        ],
        "beispiele": [
            (("iPhone koppeln und fragen", "Pair an iPhone and ask"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"],
             ("Die App hat ihren Schlüssel und fragt wie der Browser.", "The app has its key and asks like the browser.")),
            (("Alter QR-Code", "Old QR code"), ["s1", "s2", "s3", "s4", "s4!"],
             ("Abgelehnt: der Code war schon benutzt oder abgelaufen.", "Refused: the code was used or has expired.")),
            (("App will die PIN ändern", "App wants to change the PIN"), ["s6", "s7", "s8", "s9", "s10", "s10!"],
             ("Abgelehnt: das geht nur im eigenen Browser.", "Refused: that only works in the own browser.")),
            (("Admin schaltet die App aus", "Admin switches the app off"), ["s6", "s7", "s8", "s8!"],
             ("Gerade nicht: die Kopplung bleibt für später.", "Not now: the pairing stays for later.")),
        ],
        "regeln": [
            [("Schlüssel-Bereich", "Key scope"), ("Wer ihn hat", "Who has it"), ("Was er öffnet", "What it opens")],
            [("app", "app"), ("iPhone-App", "iPhone app"), ("profiles.APP_PATHS und freigegebene Bereiche", "profiles.APP_PATHS and opened areas")],
            [("watch", "watch"), ("Pebble-Uhr", "Pebble watch"), ("nur /api/watch/…", "only /api/watch/…")],
            [("desk, write", "desk, write"), ("Spark-Begleiter, Schreibhilfe", "Spark companion, writing help"),
             ("nur ihre eigenen Pfade", "only their own paths")],
            [("ohne", "none"), ("Lautsprecher, Siri-Kurzbefehl, eigene Skripte", "speakers, Siri shortcut, own scripts"),
             ("fragen wie das Profil, nie Konto oder Sicherheit", "asking as the profile, never account or security")],
            [("kein Schlüssel", "no key"), ("Android-App", "Android app"), ("Anmeldung wie ein Browser", "sign-in like a browser")],
        ],
        "zahlen": [
            ("{iphone.CODE_SECONDS|min}", ("Minuten gilt ein Kopplungs-Code", "minutes a pairing code is valid"), "iphone.CODE_SECONDS"),
            ("{iphone.MAX_PHONES}", ("iPhones pro Profil", "iPhones per profile"), "iphone.MAX_PHONES"),
            ("{profiles.APP_PATHS|anzahl}", ("feste Pfade für den App-Schlüssel", "fixed paths for the app key"), "profiles.APP_PATHS"),
            ("{android.TOKEN_SECONDS|min}", ("Minuten gilt ein Android-Download-Link", "minutes an Android download link is valid"),
             "android.TOKEN_SECONDS"),
            ("{android.TOKEN_USES}", ("Downloads pro Android-Link", "downloads per Android link"), "android.TOKEN_USES"),
        ],
        "einstellen": [
            ("Funktionen → iPhone-App und Funktionen → Android-App: die Apps für alle Profile (Standard aus).",
             "Features → iPhone app and Features → Android app: the apps for every profile (default off)."),
            ("Funktionen → Wer darf was: die App für einzelne Profile sperren.",
             "Features → Who may do what: block the app for single profiles."),
            ("Ich → iPhone und Ich → Android: koppeln, Rechte der App, Geräte entfernen.",
             "Me → iPhone and Me → Android: pairing, the app's rights, removing devices."),
        ],
        "sehen": [
            ("Zustand → Live: eine Zeile unter Ereignisse, wenn ein iPhone gekoppelt oder entfernt wird.",
             "Status → Live: a line under events when an iPhone is paired or removed."),
            ("Logs → Anfragen: Fragen der App mit Eingang „iPhone-App“ oder „CarPlay“.",
             "Logs → Requests: the app's questions with the input „iPhone-App“ or „CarPlay“."),
        ],
        "code": [
            ("iphone.profile_pair", ("Kopplungslink nur aus dem eigenen Browser", "pairing link only from the own browser")),
            ("iphone.new_code", ("zufälliger Einmal-Code, nur der Hash", "random one-time code, only the hash")),
            ("iphone.take_code", ("Code einmal einlösen", "redeem a code once")),
            ("iphone.app_pair", ("der erste Kontakt der App", "the app's first contact")),
            ("iphone.app_hello", ("was die App darf, entscheidet der Spark", "what the app may, the Spark decides")),
            ("profiles.add_device", ("Schlüssel erzeugen, Hash speichern", "make a key, store its hash")),
            ("profiles.current", ("Profil aus Schlüssel oder Cookie, Bereiche, Schalter, Notaus", "profile from key or cookie, scopes, switches, kill switch")),
            ("profiles._app_path", ("die feste Pfadliste der App", "the app's fixed path list")),
            ("core.browser_profile", ("nur die eigene Browser-Anmeldung", "only the own browser login")),
            ("account.profile_remove_device", ("Gerät entfernen", "remove a device")),
            ("android.apk_response", ("App-Datei nur mit gültigem Link", "app file only with a valid link")),
        ],
        "tests": ["test_iphone", "test_iphone_panel", "test_android", "test_app_notaus"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Telegram, Siri, Uhr
    "kanaele": {
        "stand": "69b87c165e",
        "bezug": {
            "watch.JOB_TTL": ["s9"], "telegram.loop": ["s1"], "telegram.handle": ["s2", "s3", "s4"],
            "telegram.ask": ["s7", "s8", "s11"], "telegram.transcribe": ["s5"], "chat.siri_ask": ["s1", "s3"],
            "chat.text_ask": ["s6", "s7", "s11"], "chat.watch_ask": ["s1", "s7"], "chat._watch_run": ["s11"],
            "watch.run": ["s8"], "watch.poll": ["s9"], "regeln": ["s1", "s9", "s11"],
        },
        "kurz": ("Telegram, der Siri-Kurzbefehl und die Pebble-Uhr stellen kurze Fragen ohne Browser. Jeder Kanal baut "
                 "daraus eine Anfrage an /api/chat wie ein Gerät, sammelt die Antwort aus dem Strom ein und gibt sie "
                 "in seiner Form zurück. Den Verlauf speichert das Panel selbst im Profil.",
                 "Telegram, the Siri shortcut and the Pebble watch ask short questions without a browser. Each channel "
                 "turns them into a request to /api/chat like a device, collects the answer from the stream and hands "
                 "it back in its own form. The panel itself keeps the history in the profile."),
        "warum": ("Die Kanäle sollen nichts eigenes entscheiden: dieselben Rechte, Sperren und Grenzen wie im Browser "
                  "gelten, weil alles durch denselben Chat läuft. Was ein Kanal zusätzlich mitbringt (fremde "
                  "weitergeleitete Texte, Telegrams Server), wird vorher fest geregelt.",
                  "The channels should decide nothing of their own: the same rights, locks and limits as in the "
                  "browser apply, because everything runs through the same chat. What a channel brings on top "
                  "(forwarded texts of others, Telegram's servers) is settled by fixed rules first."),
        "ablauf": [
            S("s1", "start", ("Frage über einen Kanal", "Question through a channel"),
              ("Telegram · Siri · Pebble-Uhr", "Telegram · Siri · Pebble watch"),
              ("Telegram: das Panel fragt Telegram selbst nach neuen Nachrichten (Long Polling), es braucht keinen "
               "offenen Port. Siri: ein Kurzbefehl schickt den diktierten Text mit einem Geräteschlüssel an "
               "/api/siri/ask. Uhr: das Handy schickt die Frage mit dem Uhr-Schlüssel an /api/watch/ask.",
               "Telegram: the panel asks Telegram for new messages itself (long polling), no open port is needed. "
               "Siri: a shortcut sends the dictated text with a device key to /api/siri/ask. Watch: the phone sends "
               "the question with the watch key to /api/watch/ask.")),
            S("s2", "frage", ("Telegram: Chat verknüpft?", "Telegram: chat linked?"),
              ("nur private Chats, Code aus Ich → Telegram", "private chats only, code from Me → Telegram"),
              ("Gruppen und Kanäle werden nie beantwortet. Ein Chat gehört zu einem Profil, wenn er „/start CODE“ mit "
               "einem Code aus Ich → Telegram geschickt hat (gilt {telegram.CODE_SECONDS|min} Minuten, höchstens "
               "{telegram.MAX_TRIES} falsche Codes pro Chat und Stunde). Ein fremder Chat bekommt höchstens einmal am "
               "Tag einen festen Satz.",
               "Groups and channels are never answered. A chat belongs to a profile once it sent „/start CODE“ with a "
               "code from Me → Telegram (valid {telegram.CODE_SECONDS|min} minutes, at most {telegram.MAX_TRIES} wrong "
               "codes per chat and hour). A stranger's chat gets one fixed sentence at most once a day."),
              ("stop", "nein", ("Fester Satz, sonst nichts", "Fixed sentence, nothing else"))),
            S("s3", "frage", ("Gesperrt oder Mein Notaus?", "Blocked or My kill switch?"),
              ("Schalter je Profil und Kanal", "switch per profile and channel"),
              ("Mein Notaus des Profils, eine Sperre durch den Admin oder ein ausgeschalteter Kanal beenden die Frage. "
               "Telegram antwortet dann mit einem festen Satz; Siri und die Uhr finden zu ihrem Schlüssel kein Profil.",
               "The profile's My kill switch, a block by the admin or a channel switched off end the question. Telegram "
               "then answers with a fixed sentence; Siri and the watch find no profile for their key."),
              ("stop", "ja", ("Keine Antwort, kein Werkzeug", "No answer, no tool"))),
            S("s4", "frage", ("Weitergeleitet?", "Forwarded?"),
              ("fremde Worte sind kein Auftrag", "someone else's words are no order"),
              ("Eine in Telegram weitergeleitete Nachricht stammt von jemand anderem. Sie wird nie als Auftrag "
               "genommen und schaltet auch keine Befehle wie /notaus.",
               "A message forwarded in Telegram comes from someone else. It is never taken as an order and does not "
               "trigger commands like /notaus either."),
              ("stop", "ja", ("Fester Hinweis", "Fixed note"))),
            S("s5", "schritt", ("Sprachnachricht in Text", "Voice message to text"),
              ("höchstens {telegram.MAX_VOICE|mb}", "at most {telegram.MAX_VOICE|mb}"),
              ("Eine Telegram-Sprachnachricht wird mit Größengrenze geladen, mit ffmpeg zu WAV gewandelt (Länge "
               "begrenzt) und von der Spracherkennung des Spark gelesen. Bei Siri diktiert das iPhone, bei der Uhr "
               "das Handy.",
               "A Telegram voice message is loaded with a size limit, turned into WAV by ffmpeg (length capped) and "
               "read by the Spark's speech recognition. With Siri the iPhone dictates, with the watch the phone.")),
            S("s6", "schritt", ("Kurzer Verlauf", "Short history"),
              ("Telegram {telegram.FOLLOW_UP|min} Min. · Siri {chat.SIRI_FOLLOW_UP|min} Min.",
               "Telegram {telegram.FOLLOW_UP|min} min · Siri {chat.SIRI_FOLLOW_UP|min} min"),
              ("Für Nachfragen gehen die letzten acht Nachrichten mit, solange die letzte Frage nicht länger her ist "
               "als {telegram.FOLLOW_UP|min} Minuten (Telegram) oder {chat.SIRI_FOLLOW_UP|min} Minuten (Siri). Die Uhr "
               "schickt ihren Verlauf selbst; Antworten aus fremdem Text erkennt das Panel daran wieder (watch.mark_of).",
               "For follow-ups the last eight messages go along while the last question is no older than "
               "{telegram.FOLLOW_UP|min} minutes (Telegram) or {chat.SIRI_FOLLOW_UP|min} minutes (Siri). The watch "
               "sends its history itself; the panel recognizes answers made from outside text in it again "
               "(watch.mark_of).")),
            S("s7", "schritt", ("Anfrage an /api/chat", "Request to /api/chat"),
              ("wie ein Gerät, mit Kanal-Kennung", "like a device, with a channel tag"),
              ("Der Kanal ruft den Chat im Panel selbst auf. Bei Telegram setzt das Panel das Profil in die Anfrage, "
               "was keine Anfrage von außen kann; Siri und die Uhr tragen ihren Schlüssel. Rechte, Weiche, Grenzen "
               "und Anfrage-Verlauf sind dieselben wie im Browser.",
               "The channel calls the chat inside the panel. For Telegram the panel puts the profile into the request, "
               "which no request from outside can do; Siri and the watch carry their key. Rights, switch, limits and "
               "request history are the same as in the browser.")),
            S("s8", "schritt", ("Antwort einsammeln", "Collect the answer"),
              ("Text, Rücknahmen, Herkunft", "text, retractions, origin"),
              ("Aus dem Strom zählen Textstücke und Rücknahmen. Kam die Antwort aus Mail oder fremdem Text, wird sie "
               "so markiert, damit die nächste Frage gesperrt beginnt. Eine Rückfrage des Panels wird in Telegram zu "
               "Knöpfen, die wie eine getippte Antwort zurückkommen.",
               "From the stream, pieces of text and retractions count. If the answer came from mail or outside text it "
               "is marked so, so the next question starts locked. A question back from the panel becomes buttons in "
               "Telegram that come back like a typed answer.")),
            S("s9", "schritt", ("Ausgabe je Kanal", "Output per channel"),
              ("Text ohne Markdown · Ton für die Uhr", "text without Markdown · sound for the watch"),
              ("Telegram bekommt reinen Text und, wenn das Profil es will, eine Sprachnachricht in seiner Stimme. Siri "
               "bekommt vorlesbaren Text ohne Passwörter und Codes. Die Uhr holt Text und Ton (auf {watch.MAX_AUDIO} "
               "Bytes je Abruf, für ihren kleinen Lautsprecher gepackt) über /api/watch/poll; höchstens "
               "{watch.MAX_RUNNING} Uhr-Antworten laufen gleichzeitig. Der Begleiter bekommt Text ohne Markdown und "
               "zusätzlich die Antwort mit Markdown (höchstens {chat.MD_ANSWER_MAX} Zeichen), wenn darin nicht weniger "
               "Geheimnisse verdeckt sind.",
               "Telegram gets plain text and, if the profile wants it, a voice message in its voice. Siri gets "
               "speakable text without passwords and codes. The watch fetches text and sound (packed for its small "
               "speaker, {watch.MAX_AUDIO} bytes per fetch) through /api/watch/poll; at most {watch.MAX_RUNNING} watch "
               "answers run at once. The companion gets text without Markdown and also the answer with Markdown (at "
               "most {chat.MD_ANSWER_MAX} characters) when it hides no fewer secrets.")),
            S("s10", "schritt", ("Codewort schwärzen", "Black out the code word"),
              ("Smart-Home-Codewort nie im Verlauf", "smart home code word never in the history"),
              ("Vor dem Speichern wird das Smart-Home-Codewort durch [Codewort] ersetzt. In Telegram löscht der Bot die "
               "Nachricht mit dem Codewort oder bittet darum, sie zu löschen.",
               "Before storing, the smart home code word is replaced by [Codewort]. In Telegram the bot deletes the "
               "message with the code word or asks the person to delete it.")),
            S("s11", "ende", ("Im Verlauf des Profils", "In the profile's history"),
              ("ein Gespräch pro Tag und Kanal", "one conversation per day and channel"),
              ("verlauf.keep legt Frage und Antwort in das Tagesgespräch des Kanals („Telegram“, „Siri“, „Uhr“ mit "
               "Datum). Mit „Ein Gespräch für alle Kanäle“ landen sie im Hauptgespräch des Tages, markiert mit ihrem "
               "Kanal.",
               "verlauf.keep puts question and answer into the channel's conversation of the day („Telegram“, „Siri“, "
               "„Uhr“ with the date). With „One conversation for all channels“ they go into the day's main "
               "conversation, marked with their channel.")),
        ],
        "beispiele": [
            (("Telegram-Sprachnachricht", "Telegram voice message"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11"],
             ("Beantwortet und im Gespräch „Telegram“ des Tages gespeichert.", "Answered and kept in the day's „Telegram“ conversation.")),
            (("Fremder schreibt dem Bot", "A stranger writes to the bot"), ["s1", "s2", "s2!"],
             ("Ein fester Satz, sonst nichts.", "One fixed sentence, nothing else.")),
            (("Weitergeleitete Mail mit Auftrag", "Forwarded mail with an order"), ["s1", "s2", "s3", "s4", "s4!"],
             ("Nicht ausgeführt: fremde Worte sind kein Auftrag.", "Not carried out: someone else's words are no order.")),
            (("Siri bei Mein Notaus", "Siri with My kill switch"), ["s1", "s3", "s3!"],
             ("Keine Antwort: der Schlüssel findet kein Profil.", "No answer: the key finds no profile.")),
        ],
        "regeln": [
            [("Kanal", "Channel"), ("Wie er sich ausweist", "How it identifies"), ("Verlauf", "History"), ("Ausgabe", "Output")],
            [("Telegram", "Telegram"), ("verknüpfter privater Chat", "linked private chat"), ("„Telegram“ und Datum", "„Telegram“ and date"),
             ("Text, auf Wunsch Sprachnachricht", "text, voice message if wanted")],
            [("Siri", "Siri"), ("Geräteschlüssel des Profils", "the profile's device key"), ("„Siri“ und Datum", "„Siri“ and date"),
             ("vorlesbarer Text ohne Geheimnisse", "speakable text without secrets")],
            [("Uhr", "watch"), ("Uhr-Schlüssel, nur /api/watch/…", "watch key, only /api/watch/…"), ("„Uhr“ und Datum", "„Uhr“ and date"),
             ("Text ohne Markdown und Ton", "text without Markdown and sound")],
        ],
        "zahlen": [
            ("{telegram.CODE_SECONDS|min}", ("Minuten gilt ein Telegram-Code", "minutes a Telegram code is valid"), "telegram.CODE_SECONDS"),
            ("{telegram.MAX_TRIES}", ("falsche Codes pro Chat und Stunde", "wrong codes per chat and hour"), "telegram.MAX_TRIES"),
            ("{telegram.MAX_VOICE|mb}", ("größte Sprachnachricht", "largest voice message"), "telegram.MAX_VOICE"),
            ("{chat.SIRI_FOLLOW_UP|min}", ("Minuten zählen bei Siri frühere Fragen", "minutes earlier questions count for Siri"),
             "chat.SIRI_FOLLOW_UP"),
            ("{watch.MAX_RUNNING}", ("Uhr-Antworten gleichzeitig", "watch answers at once"), "watch.MAX_RUNNING"),
            ("{watch.JOB_TTL|min}", ("Minuten bleibt eine Uhr-Antwort abrufbar", "minutes a watch answer stays fetchable"), "watch.JOB_TTL"),
        ],
        "einstellen": [
            ("Funktionen → Telegram: Bot-Token und Schalter (Standard aus).", "Features → Telegram: bot token and switch (default off)."),
            ("Ich → Telegram: den eigenen Chat verknüpfen; Sprachnachrichten, private Daten, Smart Home und Mitteilungen "
             "einzeln erlauben.",
             "Me → Telegram: link the own chat; allow voice messages, private data, smart home and notes one by one."),
            ("Ich → Pebble-Uhr: die Uhr koppeln.", "Me → Pebble watch: pair the watch."),
            ("Funktionen → Ein Gespräch für alle Kanäle: alle Kanäle schreiben ins Hauptgespräch des Tages.",
             "Features → One conversation for all channels: every channel writes into the day's main conversation."),
        ],
        "sehen": [
            ("Logs → Anfragen: Eingang „Telegram“, „Siri“ oder „Uhr“, ohne Inhalt.",
             "Logs → Requests: input „Telegram“, „Siri“ or „Uhr“, without content."),
            ("Zustand → Live: die laufende Anfrage im Bild.", "Status → Live: the running request in the picture."),
        ],
        "code": [
            ("telegram.loop", ("fragt Telegram, ruht bei Notaus", "polls Telegram, rests with the kill switch")),
            ("telegram.handle", ("eine Nachricht: Verknüpfung, Sperren, Befehle, Sprache", "one message: link, locks, commands, voice")),
            ("telegram.ask", ("Frage an den Chat, Antwort einsammeln, speichern", "question to the chat, collect the answer, store")),
            ("telegram.transcribe", ("Sprachnachricht über ffmpeg zur Spracherkennung", "voice message through ffmpeg to recognition")),
            ("chat.siri_ask", ("Siri: Profil aus dem Schlüssel", "Siri: profile from the key")),
            ("chat.text_ask", ("Siri und Begleiter: Frage, Antwort, Verlauf", "Siri and companion: question, answer, history")),
            ("chat.watch_ask", ("Uhr: Antwort als Auftrag starten", "watch: start the answer as a job")),
            ("chat._watch_run", ("Uhr: Antwort in den Verlauf", "watch: the answer into the history")),
            ("watch.run", ("liest den Strom in den Uhr-Auftrag", "reads the stream into the watch job")),
            ("watch.poll", ("Text und Ton stückweise", "text and sound piece by piece")),
            ("verlauf.keep", ("Tagesgespräch des Kanals oder Hauptgespräch", "the channel's day conversation or the main one")),
        ],
        "tests": ["test_telegram_tasks", "test_pebble", "test_verlauf_sync", "test_notaus"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Lautsprecher, HA
    "lautsprecher": {
        "stand": "ba4d177dfe",
        "bezug": {
            "wyoming.MAX_CONNS": ["s5"], "esp32.ota": ["s1"], "esp32._activation": ["s2"],
            "esp32.same_board": ["s3"], "esp32.speaker_ws": ["s5"], "esp32.still_allowed": ["s5"],
            "esp32.Session.run_answer": ["s10"], "esp32.Session.code_gate": ["s9"], "esp32.Session.speak": ["s11"],
            "esp32.remember": ["s12"], "wyoming.settings": ["s5"], "wyoming.handle": ["s5"],
            "wyoming._session": ["s7", "s11"], "regeln": ["s5", "s9"],
        },
        "kurz": ("Eigene Lautsprecher sind ESP32-Boards mit der offenen XiaoZhi-Firmware. Sie hören auf ihr Weckwort, "
                 "schicken den Ton über eine WebSocket-Verbindung an den Spark und spielen die Antwort ab. Jeder "
                 "Lautsprecher ist ein Geräteschlüssel seines Profils. Home Assistant Assist nutzt über Wyoming nur "
                 "Spracherkennung und Stimme des Spark.",
                 "Own speakers are ESP32 boards with the open XiaoZhi firmware. They listen for their wake word, send "
                 "the sound to the Spark over a WebSocket connection and play the answer. Every speaker is a device key "
                 "of its profile. Home Assistant Assist only uses the Spark's speech recognition and voice over Wyoming."),
        "warum": ("Ein Lautsprecher steht im Raum, jeder kann mit ihm reden. Deshalb bekommt Persönliches nur die "
                  "Stimme, die sicher als die des Profils erkannt ist (oder das Codewort sagt), und ein Board bekommt "
                  "seinen Schlüssel nur einmal und nur an die Adresse, die den Code gezeigt hat.",
                  "A speaker stands in the room, anyone can talk to it. That is why personal things only go to the "
                  "voice that is surely recognized as the profile's (or says the code word), and a board gets its key "
                  "only once and only at the address that showed the code."),
        "ablauf": [
            S("s1", "start", ("Board startet", "Board starts"),
              ("POST /api/esp32/ota/", "POST /api/esp32/ota/"),
              ("Bei jedem Start fragt das Board mit seiner Kennung, MAC-Adresse und Firmware-Version, welchen Server "
               "und welche Firmware es nehmen soll. Sind die Lautsprecher in Funktionen aus, gibt es nichts (403).",
               "At every start the board asks with its id, MAC address and firmware version which server and which "
               "firmware to use. If speakers are off in Features, it gets nothing (403).")),
            S("s2", "frage", ("Board bekannt?", "Board known?"),
              ("sonst sechsstelliger Code", "else a six-digit code"),
              ("Ein unbekanntes Board bekommt einen sechsstelligen Code für sein Display (gilt "
               "{esp32.CODE_SECONDS|min} Minuten, höchstens {esp32.PENDING_PER_IP} pro Adresse und "
               "{esp32.MAX_PENDING} insgesamt). Das Profil tippt ihn unter Ich → Lautsprecher ein.",
               "An unknown board gets a six-digit code for its display (valid {esp32.CODE_SECONDS|min} minutes, at "
               "most {esp32.PENDING_PER_IP} per address and {esp32.MAX_PENDING} in all). The profile types it in under "
               "Me → Speakers."),
              ("stop", "nein", ("Code am Board, wartet aufs Eintippen", "Code on the board, waiting to be typed in"))),
            S("s3", "frage", ("Gleiches Board?", "Same board?"),
              ("MAC-Adresse passt", "MAC address fits"),
              ("Ist zu einer Board-Kennung schon eine MAC-Adresse bekannt, muss sie passen. Eine kopierte Kennung von "
               "einem anderen Board bekommt keinen Schlüssel und keine Firmware.",
               "Once a MAC address is on record for a board id, it must fit. A copied id from another board gets no "
               "key and no firmware."),
              ("stop", "nein", ("Abgelehnt (403)", "Refused (403)"))),
            S("s4", "schritt", ("Antwort der Start-Prüfung", "Answer of the start check"),
              ("Uhrzeit, Verbindung, Schlüssel einmal, Update", "time, connection, key once, update"),
              ("Das Board bekommt Uhrzeit und WebSocket-Adresse. Den Schlüssel gibt es genau einmal, direkt nach dem "
               "Eintippen, und nur an die Adresse, die den Code gezeigt hat. Eine neuere Firmware wird nur über https "
               "angeboten, über http nur mit dem Schalter des Admins.",
               "The board gets the time and the WebSocket address. The key comes exactly once, right after the code "
               "was typed in, and only to the address that showed the code. A newer firmware is only offered over "
               "https, over http only with the admin's switch.")),
            S("s5", "frage", ("Verbindung erlaubt?", "Connection allowed?"),
              ("WS /api/esp32/ws mit Schlüssel", "WS /api/esp32/ws with key"),
              ("Beim Aufbau prüft der Spark: Notaus Stufe 3 aus, der Schlüssel gehört einem Lautsprecher (nicht einer "
               "Uhr oder einem anderen Gerät), Lautsprecher in Funktionen an und für das Profil nicht gesperrt. Danach "
               "schaut er alle {esp32.RECHECK} Sekunden wieder nach und beendet die Verbindung, wenn sich etwas "
               "geändert hat.",
               "When connecting the Spark checks: kill switch stage 3 off, the key belongs to a speaker (not a watch "
               "or another device), speakers on in Features and not blocked for the profile. Then it looks again every "
               "{esp32.RECHECK} seconds and ends the connection when something changed."),
              ("stop", "nein", ("Verbindung abgelehnt", "Connection refused"))),
            S("s6", "schritt", ("Zuhören", "Listen"),
              ("Weckwort am Board, Satzende am Spark", "wake word on the board, end of sentence on the Spark"),
              ("Nach dem Weckwort schickt das Board Opus-Ton. Der Spark erkennt das Satzende selbst ({esp32.Ear.QUIET} "
               "Sekunden Stille nach Sprache) und nimmt höchstens {esp32.MAX_LISTEN} Sekunden pro Frage.",
               "After the wake word the board sends Opus sound. The Spark finds the end of the sentence itself "
               "({esp32.Ear.QUIET} seconds of silence after speech) and takes at most {esp32.MAX_LISTEN} seconds per "
               "question.")),
            S("s7", "schritt", ("Erkennen und Stimme prüfen", "Recognize and check the voice"),
              ("gleichzeitig auf GPU und CPU", "at the same time on GPU and CPU"),
              ("Die Spracherkennung macht Text daraus. Gleichzeitig prüft speakers.verify, ob es die Stimme des Profils "
               "ist, wenn die Sprechererkennung an ist und das Profil seine Stimme angelernt hat.",
               "Speech recognition makes text of it. At the same time speakers.verify checks whether it is the "
               "profile's voice, when speaker ID is on and the profile has taught its voice.")),
            S("s8", "frage", ("Nichts, Stopp oder eigene Stimme?", "Nothing, stop or own voice?"),
              ("keine Antwort, zurück zum Weckwort", "no answer, back to the wake word"),
              ("Kein Text, ein Stopp-Wort oder die eigene Stimme des Spark von einem anderen Gerät (echo.check) "
               "bekommen keine Antwort. Das Board wartet wieder auf sein Weckwort.",
               "No text, a stop word or the Spark's own voice from another device (echo.check) get no answer. The "
               "board waits for its wake word again."),
              ("stop", "ja", ("Keine Antwort", "No answer"))),
            S("s9", "frage", ("Persönliches ohne sichere Stimme?", "Personal without a sure voice?"),
              ("Codewort am Lautsprecher", "speaker code word"),
              ("Mit Codewort am Lautsprecher: eine unsichere Stimme, die nach Persönlichem fragt, wird nach dem "
               "Codewort gefragt, die Frage wartet. Nach {spkcode.FAILS} falschen Versuchen fragt der Lautsprecher "
               "{spkcode.LOCK|min} Minuten lang nicht mehr. Ohne sichere Stimme gibt es nur Allgemeines.",
               "With the speaker code word: an unsure voice asking for personal things is asked for the code word, "
               "the question waits. After {spkcode.FAILS} wrong tries the speaker does not ask for {spkcode.LOCK|min} "
               "minutes. Without a sure voice there are only general things."),
              ("info", "ja", ("„Sag bitte dein Codewort“", "„Please say your code word“"))),
            S("s10", "schritt", ("Wie ein Gerät an /api/chat", "Like a device to /api/chat"),
              ("Schlüssel und erkannte Stimme in der Anfrage", "key and recognized voice in the request"),
              ("Der Spark ruft den Chat mit dem Schlüssel des Lautsprechers auf; Stimme, Gedächtnis und Raum des "
               "Profils gelten. Wessen Stimme es war, setzt nur das Panel selbst in die Anfrage; war sie nicht sicher "
               "die des Profils, gilt die Frage wie die eines Gastes.",
               "The Spark calls the chat with the speaker's key; the profile's voice, memory and room apply. Whose "
               "voice it was only the panel itself puts into the request; if it was not surely the profile's, the "
               "question counts like a guest's.")),
            S("s11", "schritt", ("Ton zurück", "Sound back"),
              ("Opus {esp32.OUT_RATE} Hz, im Takt", "Opus {esp32.OUT_RATE} Hz, paced"),
              ("Die Antwort geht als Opus mit {esp32.OUT_RATE} Hz im Takt der Wiedergabe zum Board, der Text ohne "
               "Markdown für ein Display. Andere Geräte im Haus wissen, dass gerade der Spark spricht (echo.said).",
               "The answer goes to the board as Opus at {esp32.OUT_RATE} Hz at playback pace, the text without Markdown "
               "for a display. Other devices in the house know the Spark is speaking right now (echo.said).")),
            S("s12", "ende", ("Im Verlauf des Lautsprechers", "In the speaker's history"),
              ("Nachfragen {esp32.FOLLOW_UP|min} Minuten", "follow-ups {esp32.FOLLOW_UP|min} minutes"),
              ("Frage und Antwort kommen in das Tagesgespräch des Lautsprechers, das Codewort geschwärzt. Eine Stimme, "
               "die nicht sicher die des Profils war, wird als fremder Text markiert: die nächste Frage beginnt "
               "gesperrt, und daraus wird nichts über das Profil gelernt.",
               "Question and answer go into the speaker's conversation of the day, the code word blacked out. A voice "
               "that was not surely the profile's is marked as outside text: the next question starts locked, and "
               "nothing about the profile is learned from it.")),
        ],
        "beispiele": [
            (("Inhaber fragt nach seinen Terminen", "The owner asks for appointments"),
             ["s1", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Stimme erkannt: persönliche Antwort, im Tagesgespräch gespeichert.", "Voice recognized: personal answer, kept in the day's conversation.")),
            (("Neues Board", "New board"), ["s1", "s2", "s2!"],
             ("Code auf dem Display, bis das Profil ihn eintippt.", "Code on the display until the profile types it in.")),
            (("Kopierte Board-Kennung", "Copied board id"), ["s1", "s2", "s3", "s3!"],
             ("Abgelehnt: die MAC-Adresse passt nicht.", "Refused: the MAC address does not fit.")),
            (("Gast fragt nach Mails", "A guest asks for mail"), ["s5", "s6", "s7", "s8", "s9", "s9!"],
             ("Codewort erfragt; ohne richtiges Codewort nichts Persönliches.", "Code word asked; without the right one nothing personal.")),
        ],
        "regeln": [
            [("Weg", "Way"), ("Wer darf", "Who may"), ("Was geht", "What works"), ("Persönliches", "Personal things")],
            [("ESP32-Lautsprecher", "ESP32 speaker"), ("Schlüssel eines Lautsprechers, Profil nicht gesperrt", "a speaker's key, profile not blocked"),
             ("Fragen wie das Profil", "questions as the profile"), ("nur bei sicherer Stimme oder Codewort", "only with a sure voice or code word")],
            [("Home Assistant Assist", "Home Assistant Assist"), ("Adressen in der Erlaubt-Liste des Admins", "addresses in the admin's allow list"),
             ("nur Ton zu Text und Text zu Ton", "only sound to text and text to sound"), ("nie", "never")],
        ],
        "mehr": [
            (("Home Assistant Assist (Wyoming)", "Home Assistant Assist (Wyoming)"), [
                ("Ein eigener Server lauscht auf dem Wyoming-Port (Standard 31003), solange der Schalter an ist. Wyoming "
                 "hat kein Passwort; deshalb antwortet er nur Adressen aus der Liste des Admins, mit leerer Liste "
                 "niemandem.",
                 "Its own server listens on the Wyoming port (default 31003) while the switch is on. Wyoming has no "
                 "password; that is why it only answers addresses from the admin's list, with an empty list nobody."),
                ("Home Assistant bekommt nur „Ton rein, Text raus“ und „Text rein, Ton raus“, kein Sprachmodell, kein "
                 "Profil, nichts Persönliches. Höchstens {wyoming.MAX_CONNS} Verbindungen gleichzeitig; Längen werden "
                 "geprüft, bevor gelesen wird; nur Tonformate, die ein Mikrofon schickt.",
                 "Home Assistant only gets „sound in, text out“ and „text in, sound out“, no language model, no "
                 "profile, nothing personal. At most {wyoming.MAX_CONNS} connections at once; lengths are checked "
                 "before reading; only sound formats a microphone sends."),
                ("Abgewiesene Adressen erscheinen auf Zustand → Live unter Eingang und als Vorschlag für die Liste.",
                 "Refused addresses show on Status → Live under input and as a suggestion for the list."),
            ]),
        ],
        "zahlen": [
            ("{esp32.CODE_SECONDS|min}", ("Minuten gilt ein Kopplungs-Code", "minutes a pairing code is valid"), "esp32.CODE_SECONDS"),
            ("{esp32.MAX_LISTEN}", ("Sekunden Ton pro Frage", "seconds of sound per question"), "esp32.MAX_LISTEN"),
            ("{esp32.RECHECK}", ("Sekunden, dann werden die Rechte neu geprüft", "seconds, then the rights are checked again"), "esp32.RECHECK"),
            ("{esp32.FOLLOW_UP|min}", ("Minuten zählen frühere Fragen am Lautsprecher", "minutes earlier questions count at a speaker"),
             "esp32.FOLLOW_UP"),
            ("{spkcode.FAILS}", ("falsche Codewörter bis zur Sperre", "wrong code words until the lock"), "spkcode.FAILS"),
            ("{wyoming.MAX_CONNS}", ("Wyoming-Verbindungen gleichzeitig", "Wyoming connections at once"), "wyoming.MAX_CONNS"),
        ],
        "einstellen": [
            ("Funktionen → Eigene Lautsprecher: Lautsprecher für alle Profile (Standard aus).",
             "Features → Own speakers: speakers for every profile (default off)."),
            ("Ich → Lautsprecher: einrichten, Code eintippen, Raum, Lautstärke, Prüfen und das eigene Codewort.",
             "Me → Speakers: set up, type the code, room, volume, check and the own code word."),
            ("Funktionen → Home Assistant Assist: Wyoming an und die erlaubten Adressen.",
             "Features → Home Assistant Assist: Wyoming on and the allowed addresses."),
        ],
        "sehen": [
            ("Ich → Lautsprecher → Prüfen: was der Lautsprecher zuletzt getan hat (nur im Speicher, weg nach einem Neustart).",
             "Me → Speakers → Check: what the speaker did lately (memory only, gone after a restart)."),
            ("Zustand → Live: Anfragen vom Lautsprecher und von Home Assistant, abgewiesene Wyoming-Adressen unter Eingang.",
             "Status → Live: requests from a speaker and from Home Assistant, refused Wyoming addresses under input."),
        ],
        "code": [
            ("esp32.ota", ("Start-Prüfung: Code, Schlüssel einmal, Update", "start check: code, key once, update")),
            ("esp32._activation", ("sechsstelliger Code mit Grenzen", "six-digit code with limits")),
            ("esp32.same_board", ("MAC muss passen", "MAC must fit")),
            ("esp32.speaker_ws", ("Verbindung annehmen und laufend prüfen", "accept the connection and keep checking")),
            ("esp32.still_allowed", ("Schalter und Gerät noch gültig", "switches and device still valid")),
            ("esp32.Session.run_answer", ("erkennen, filtern, Codewort, antworten", "recognize, filter, code word, answer")),
            ("esp32.Session.code_gate", ("Codewort bei unsicherer Stimme", "code word for an unsure voice")),
            ("esp32.Session.speak", ("Chat mit dem Schlüssel, Ton zurück", "chat with the key, sound back")),
            ("esp32.remember", ("Tagesgespräch, fremde Stimme markiert", "day conversation, foreign voice marked")),
            ("wyoming.settings", ("Schalter, Port, erlaubte Adressen", "switch, port, allowed addresses")),
            ("wyoming.handle", ("nur erlaubte Adressen, höchstens so viele", "only allowed addresses, at most so many")),
            ("wyoming._session", ("Ton zu Text und Text zu Ton", "sound to text and text to sound")),
        ],
        "tests": ["test_esp32", "test_wyoming", "test_notaus", "test_echo"],
        "heute": [],
    },

    # ------------------------------------------------------------------ MCP-Programme
    "mcpc": {
        "stand": "6b2d1629f1",
        "bezug": {
            "mcpserver.MAX_CONNS": ["s3"], "mcpserver.mcp_post": ["s1"], "mcpserver.origin_ok": ["s2"],
            "mcpserver.check_conn": ["s3"], "mcpserver.is_local": ["s4"], "mcpserver.find": ["s3"],
            "mcpserver.tool_ok": ["s7"], "mcpserver.call": ["s8"], "mcpserver.run": ["s9", "s10"],
            "mcpserver.ask": ["s10"], "mcpserver.propose": ["s11"], "mcpserver.decide": ["s11"],
            "mcpserver.carry_out": ["s11"], "regeln": ["s7"], "regel:Sprache": ["s9"], "regel:Lesen": ["s9"],
            "regel:Spark fragen": ["s10"], "regel:Handeln mit Bestätigung": ["s11"],
        },
        "kurz": ("Andere Programme (Claude, n8n, Open WebUI, Home Assistant) nutzen den Spark über das Model Context "
                 "Protocol unter /mcp. Jede Verbindung gehört einem Profil, hat ihren eigenen Schlüssel und ihre "
                 "eigene Werkzeugliste. Lesen geht direkt, Handeln nur als Vorschlag, den das Profil bestätigt.",
                 "Other programs (Claude, n8n, Open WebUI, Home Assistant) use the Spark over the Model Context Protocol "
                 "at /mcp. Every connection belongs to one profile and has its own key and its own tool list. Reading "
                 "works directly, acting only as a proposal the profile confirms."),
        "warum": ("Was ein Programm schickt, ist Text von außen und nie ein Befehl. Deshalb entscheidet das Panel mit "
                  "festen Listen, welches Werkzeug laufen darf, und nichts ändert sich ohne das Ja der Person im "
                  "eigenen Browser.",
                  "What a program sends is outside text and never a command. That is why the panel decides with fixed "
                  "lists which tool may run, and nothing changes without the person's yes in the own browser."),
        "ablauf": [
            S("s1", "start", ("Programm schickt eine Anfrage", "A program sends a request"),
              ("POST /mcp, JSON-RPC 2.0", "POST /mcp, JSON-RPC 2.0"),
              ("Jede Anfrage ist eine JSON-RPC-Nachricht. Ist der MCP-Server vom Admin aus, gibt es den Endpunkt nicht "
               "(404).",
               "Every request is one JSON-RPC message. If the MCP server is off by the admin, the endpoint does not "
               "exist (404).")),
            S("s2", "frage", ("Von einer fremden Webseite?", "From another web page?"),
              ("Origin muss der eigene sein", "Origin must be our own"),
              ("Schickt ein Browser einen Origin, muss es der des Panels sein. So kann keine fremde Seite den "
               "Endpunkt über DNS-Rebinding benutzen.",
               "If a browser sends an Origin, it must be the panel's. So no other page can use the endpoint through DNS "
               "rebinding."),
              ("stop", "ja", ("Abgelehnt (403)", "Refused (403)"))),
            S("s3", "frage", ("Schlüssel gültig?", "Key valid?"),
              ("fester Schlüssel oder OAuth", "fixed key or OAuth"),
              ("Der Bearer-Schlüssel ist ein fester Schlüssel oder ein OAuth-Zugangstoken (gilt "
               "{mcpserver.ACCESS_SECONDS|min} Minuten). Gespeichert sind nur Hashes. Eine Verbindung endet nach "
               "{mcpserver.DAYS} Tagen ohne Nutzung.",
               "The bearer key is a fixed key or an OAuth access token (valid {mcpserver.ACCESS_SECONDS|min} minutes). "
               "Only hashes are stored. A connection ends after {mcpserver.DAYS} days without use."),
              ("stop", "nein", ("Nicht angemeldet (401)", "Not signed in (401)"))),
            S("s4", "frage", ("Heimnetz-Schlüssel von außen?", "Home network key from outside?"),
              ("„lokal“ nur ohne Proxy", "„lokal“ only without a proxy"),
              ("Ein Schlüssel „lokal“ gilt nur, wenn die Gegenstelle eine private Adresse ist, kein Proxy-Kopf in der "
               "Anfrage steht und sie keiner der eingetragenen Reverse Proxys ist. „extern“ geht nur mit dem Schalter "
               "des Admins.",
               "A „lokal“ key only works when the peer is a private address, no proxy header is in the request and it "
               "is none of the listed reverse proxies. „extern“ only works with the admin's switch."),
              ("stop", "ja", ("Abgelehnt (403)", "Refused (403)"))),
            S("s5", "frage", ("Mein Notaus oder Profil gesperrt?", "My kill switch or profile blocked?"),
              ("Schalter je Profil", "switch per profile"),
              ("Mein Notaus des Profils sperrt jeden MCP-Zugang (503); hat der Admin den MCP-Server für das Profil "
               "gesperrt, gibt es nichts (403).",
               "The profile's My kill switch closes every MCP access (503); if the admin blocked the MCP server for the "
               "profile, there is nothing (403)."),
              ("stop", "ja", ("Gesperrt", "Blocked"))),
            S("s6", "schritt", ("Rate-Limit und Größe", "Rate limit and size"),
              ("{guard.RATE.mcp.1} pro Minute je Verbindung", "{guard.RATE.mcp.1} per minute per connection"),
              ("Jede Verbindung darf {guard.RATE.mcp.1} Anfragen pro Minute schicken; eine Anfrage ist höchstens "
               "{mcpserver.MAX_BODY|mb} groß. Viele abgewiesene Anfragen von außen zählen für „Notaus von selbst“.",
               "Every connection may send {guard.RATE.mcp.1} requests per minute; a request is at most "
               "{mcpserver.MAX_BODY|mb}. Many refused requests from outside count for „Emergency stop by itself“.")),
            S("s7", "frage", ("Werkzeug freigegeben?", "Tool allowed?"),
              ("feste Liste · Liste der Verbindung · Schalter", "fixed list · the connection's list · switches"),
              ("Nur Werkzeuge aus der festen Liste ({mcpserver.TOOLS|anzahl}), nur die, die dieser Verbindung gegeben "
               "wurden, und nur, wenn das Profil die Funktion gerade nutzen darf, bei jedem Aufruf neu geprüft. Mail, "
               "Gedächtnis, frühere Gespräche, Einstellungen und Code sind nie dabei ({mcpserver.NEVER|anzahl} Namen "
               "in mcpserver.NEVER).",
               "Only tools from the fixed list ({mcpserver.TOOLS|anzahl}), only those given to this connection, and "
               "only when the profile may use the function right now, checked again on every call. Mail, memory, "
               "earlier conversations, settings and code are never among them ({mcpserver.NEVER|anzahl} names in "
               "mcpserver.NEVER)."),
              ("stop", "nein", ("„nicht freigegeben“", "„not allowed“"))),
            S("s8", "frage", ("Zu viele gleichzeitig?", "Too many at once?"),
              ("{mcpserver.MAX_AT_ONCE} je Verbindung, {mcpserver.MAX_ALL} insgesamt",
               "{mcpserver.MAX_AT_ONCE} per connection, {mcpserver.MAX_ALL} in all"),
              ("Höchstens {mcpserver.MAX_AT_ONCE} Aufrufe einer Verbindung und {mcpserver.MAX_ALL} aller Verbindungen "
               "laufen gleichzeitig.",
               "At most {mcpserver.MAX_AT_ONCE} calls of one connection and {mcpserver.MAX_ALL} of all connections run "
               "at once."),
              ("stop", "ja", ("„bitte gleich noch einmal“", "„please try again“"))),
            S("s9", "schritt", ("Sprache und Lesen", "Speech and reading"),
              ("Stufe „hinten“: Menschen gehen vor", "level „hinten“: people go first"),
              ("Spracherkennung (höchstens {mcpserver.MAX_AUDIO|mb}) und Sprachausgabe (höchstens "
               "{mcpserver.MAX_SPEAK} Zeichen) laufen mit der Stufe „hinten“, damit Menschen am Spark immer zuerst "
               "dran sind. Die Lese-Werkzeuge lesen nur die Daten dieses Profils.",
               "Speech recognition (at most {mcpserver.MAX_AUDIO|mb}) and speech output (at most {mcpserver.MAX_SPEAK} "
               "characters) run at the level „hinten“, so people at the Spark always go first. The reading tools only "
               "read this profile's data.")),
            S("s10", "schritt", ("Spark fragen, nur lesend", "Ask the Spark, read only"),
              ("ein Zug mit den Lese-Werkzeugen der Verbindung", "one turn with the connection's reading tools"),
              ("ask_spark ({guard.RATE.mcpask.1} pro Minute) läuft als ein Zug des Assistenten für das Profil, aber nur "
               "mit den Lese-Werkzeugen dieser Verbindung. Die Frage gilt von Anfang an als fremder Text: nichts wird "
               "geschaltet, gespeichert, gelernt oder gesendet, kein Gedächtnis, nichts davon im Verlauf. Passwörter "
               "und Codes werden aus der Antwort entfernt.",
               "ask_spark ({guard.RATE.mcpask.1} per minute) runs as one turn of the assistant for the profile, but "
               "only with this connection's reading tools. The question counts as outside text from the start: nothing "
               "is switched, stored, learned or sent, no memory, nothing of it in the history. Passwords and codes are "
               "removed from the answer.")),
            S("s11", "frage", ("Soll etwas geändert werden?", "Should something change?"),
              ("nur Vorschlag, das Profil bestätigt", "only a proposal, the profile confirms"),
              ("Smart Home, Erinnerung und Termin werden nur vorgeschlagen (höchstens {mcpserver.MAX_WAITING} offen). "
               "Das Profil bekommt eine Mitteilung und entscheidet unter Ich → Dienste per MCP innerhalb von "
               "{mcpserver.ACTION_SECONDS|min} Minuten; erst dann führt das Panel es aus. Bei Notaus oder gesetztem "
               "Smart-Home-Codewort schaltet ein MCP-Programm nichts.",
               "Smart home, reminder and appointment are only proposed (at most {mcpserver.MAX_WAITING} open). The "
               "profile gets a notice and decides under Me → Services over MCP within {mcpserver.ACTION_SECONDS|min} "
               "minutes; only then the panel carries it out. With the kill switch or a smart home code word set, an MCP "
               "program switches nothing."),
              ("info", "ja", ("Vorgeschlagen, noch nicht ausgeführt", "Proposed, not carried out yet"))),
            S("s12", "ende", ("Antwort ans Programm", "Answer to the program"),
              ("höchstens {mcpserver.MAX_RESULT} Zeichen", "at most {mcpserver.MAX_RESULT} characters"),
              ("Die Antwort wird auf {mcpserver.MAX_RESULT} Zeichen gekürzt. Ins Journal kommt nur, welches Programm, "
               "welches Werkzeug, ob es ging und wie lange, nie Frage oder Antwort.",
               "The answer is cut to {mcpserver.MAX_RESULT} characters. The journal only gets which program, which "
               "tool, whether it worked and how long, never question or answer.")),
        ],
        "beispiele": [
            (("Claude liest die Termine", "Claude reads the appointments"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s12"],
             ("Termine des Profils als Text, gekürzt.", "The profile's appointments as text, cut.")),
            (("Heimnetz-Schlüssel über den Proxy", "Home network key through the proxy"), ["s1", "s2", "s3", "s4", "s4!"],
             ("Abgelehnt: dieser Schlüssel gilt nur im Heimnetz.", "Refused: this key only works at home.")),
            (("n8n will das Licht schalten", "n8n wants to switch the light"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s11", "s11!", "s12"],
             ("Nur vorgeschlagen; es schaltet erst nach dem Ja im Browser.", "Only proposed; it switches after the yes in the browser.")),
            (("Programm will Mails lesen", "Program wants to read mail"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s7!"],
             ("Nicht freigegeben: Mail gibt es über MCP nie.", "Not allowed: mail is never offered over MCP.")),
        ],
        "regeln": [
            [("Gruppe", "Group"), ("Werkzeuge", "Tools"), ("Was passiert", "What happens")],
            [("Sprache", "speech"), ("transcribe, speak, voices", "transcribe, speak, voices"),
             ("Dienste mit Stufe „hinten“", "services at level „hinten“")],
            [("Lesen", "reading"), ("wikipedia, archive_search, document_search, calendar_events, reminder_list, today, write_text",
                                   "wikipedia, archive_search, document_search, calendar_events, reminder_list, today, write_text"),
             ("liest nur, speichert nichts", "only reads, stores nothing")],
            [("Spark fragen", "ask Spark"), ("ask_spark", "ask_spark"), ("ein Zug nur mit Lese-Werkzeugen", "one turn with reading tools only")],
            [("Handeln mit Bestätigung", "acting with confirmation"), ("home_assistant, reminder_set, calendar_add",
                                                                       "home_assistant, reminder_set, calendar_add"),
             ("nur Vorschlag, das Profil sagt Ja", "only a proposal, the profile says yes")],
            [("nie", "never"), ("Mail, Gedächtnis, Verlauf, Einstellungen, Code", "mail, memory, history, settings, code"),
             ("gibt es unter keinem Namen", "offered under no name")],
        ],
        "zahlen": [
            ("{mcpserver.DAYS}", ("Tage ohne Nutzung, dann endet eine Verbindung", "days without use, then a connection ends"), "mcpserver.DAYS"),
            ("{mcpserver.MAX_CONNS}", ("Verbindungen pro Profil", "connections per profile"), "mcpserver.MAX_CONNS"),
            ("{guard.RATE.mcp.1}", ("Anfragen pro Minute je Verbindung", "requests per minute per connection"), "guard.RATE"),
            ("{mcpserver.MAX_AT_ONCE}", ("Aufrufe gleichzeitig je Verbindung", "calls at once per connection"), "mcpserver.MAX_AT_ONCE"),
            ("{mcpserver.MAX_RESULT}", ("Zeichen höchstens in einer Antwort", "characters at most in an answer"), "mcpserver.MAX_RESULT"),
            ("{mcpserver.ACTION_SECONDS|min}", ("Minuten wartet ein Vorschlag auf das Ja", "minutes a proposal waits for the yes"),
             "mcpserver.ACTION_SECONDS"),
        ],
        "einstellen": [
            ("Funktionen → Spark als MCP-Server: der Server für alle Profile (Standard aus).",
             "Features → Spark as MCP server: the server for every profile (default off)."),
            ("Funktionen → Spark als MCP-Server → MCP-Server von außen: Verbindungen über den Reverse Proxy und OAuth.",
             "Features → Spark as MCP server → MCP server from outside: connections through the reverse proxy and OAuth."),
            ("Funktionen → Spark als MCP-Server → MCP: Handeln mit Bestätigung: die Werkzeuge, die etwas vorschlagen.",
             "Features → Spark as MCP server → MCP: acting with confirmation: the tools that propose something."),
            ("Ich → Dienste per MCP: Verbindungen anlegen, Werkzeuge wählen, Vorschläge bestätigen oder ablehnen.",
             "Me → Services over MCP: make connections, pick tools, confirm or decline proposals."),
        ],
        "sehen": [
            ("Zustand → Live: jeder Werkzeug-Aufruf als Anfrage des Programms, von außen unter „Über das Internet“.",
             "Status → Live: every tool call as a request of the program, from outside under „Über das Internet“."),
            ("Ich → Dienste per MCP: die letzten Vorschläge mit ihrem Stand.",
             "Me → Services over MCP: the latest proposals with their state."),
        ],
        "code": [
            ("mcpserver.mcp_post", ("der Endpunkt: Origin, Schlüssel, Limit, Methode", "the endpoint: origin, key, limit, method")),
            ("mcpserver.origin_ok", ("keine fremde Webseite", "no other web page")),
            ("mcpserver.check_conn", ("Schlüssel, Heimnetz, Notaus, Schalter", "key, home network, kill switch, switch")),
            ("mcpserver.is_local", ("wirklich aus dem Heimnetz", "really from the home network")),
            ("mcpserver.find", ("Verbindung zum Hash des Schlüssels", "connection for the key's hash")),
            ("mcpserver.tool_ok", ("darf das Profil dieses Werkzeug jetzt", "may the profile use this tool now")),
            ("mcpserver.call", ("gleichzeitige Aufrufe, Journal-Zeile", "calls at once, journal line")),
            ("mcpserver.run", ("verteilt auf Sprache, Lesen, Fragen, Handeln", "hands out to speech, reading, asking, acting")),
            ("mcpserver.ask", ("ein Zug nur mit Lese-Werkzeugen", "one turn with reading tools only")),
            ("mcpserver.propose", ("Vorschlag statt Handlung", "proposal instead of action")),
            ("mcpserver.decide", ("das Ja des Profils, dann ausführen", "the profile's yes, then carry out")),
            ("mcpserver.carry_out", ("führt nur bestätigte Aktionen aus", "carries out confirmed actions only")),
        ],
        "tests": ["test_mcpserver", "test_notaus"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Spracherkennung
    "asr": {
        "stand": "bd38333a9d",
        "bezug": {
            "parakeet.MAX_AUDIO_S": ["s9"], "admin.test_asr": ["s1"], "admin._test_asr": ["s2", "s4"],
            "common.BodyLimit": ["s5"], "common.PrioGate": ["s7"], "common.audio_rate_ok": ["s8"],
            "asr_proxy.transcriptions": ["s4"], "asr_proxy.engine_status": ["s6"], "parakeet.Recognizer": ["s9"],
        },
        "kurz": ("Die Spracherkennung macht aus einer Aufnahme Text. Das Panel nimmt die Aufnahme an, prüft sie und "
                 "reicht sie an den ASR-Dienst weiter. Dieser Proxy prüft Schlüssel, Größe und Abtastrate, lässt "
                 "Anfragen nach Vorrang warten und gibt sie an die Engine, die nur auf dieser Maschine lauscht.",
                 "Speech recognition turns a recording into text. The panel takes the recording, checks it and hands "
                 "it to the ASR service. That proxy checks key, size and sample rate, lets requests wait by priority "
                 "and passes them to the engine, which listens on this machine only."),
        "warum": ("Eine Aufnahme kommt von draußen: von einem Browser, einer App, einem Lautsprecher. Sie könnte riesig "
                  "sein, eine erfundene Abtastrate tragen oder nur Stille, ein Klick oder die eigene Stimme des Spark "
                  "sein. Feste Regeln fangen das ab, bevor die Grafikkarte rechnet und bevor ein Text als Frage zählt.",
                  "A recording comes from outside: a browser, an app, a speaker. It could be huge, carry a made-up "
                  "sample rate or be only silence, a click or the Spark's own voice. Fixed rules catch that before the "
                  "GPU works and before a text counts as a question."),
        "ablauf": [
            S("s1", "start", ("Aufnahme kommt an", "A recording arrives"),
              ("POST /api/test/asr", "POST /api/test/asr"),
              ("Der Browser schickt die Aufnahme ans Panel. Jeder Anrufer darf nur so oft pro Minute (Profil "
               "{guard.RATE.asr.1}), Gäste teilen sich {guard.BUSY.asr} Plätze gleichzeitig.",
               "The browser sends the recording to the panel. Each caller may only so often per minute (profile "
               "{guard.RATE.asr.1}), guests share {guard.BUSY.asr} places at once.")),
            S("s2", "schritt", ("Höchstens {admin.MAX_AUDIO|mb}", "At most {admin.MAX_AUDIO|mb}"),
              ("Weckwort nur für Profile", "wake word for profiles only"),
              ("read_audio liest die Aufnahme in Stücken und bricht bei {admin.MAX_AUDIO|mb} ab. Ein Weckwort darf "
               "nur ein angemeldetes Profil mitschicken; es geht dann als Hinweis an das Modell.",
               "read_audio reads the recording in pieces and stops at {admin.MAX_AUDIO|mb}. Only a signed-in profile "
               "may send a wake word; it then goes to the model as a hint."),
              ("stop", ("größer", "larger"), ("Abgelehnt (413)", "Refused (413)"))),
            S("s3", "schritt", ("Nebenbei auf dem Prozessor", "Alongside on the CPU"),
              ("Stimme, Stille, fremde Stimme", "voice, silence, other voice"),
              ("Während die Grafikkarte erkennt, laufen auf dem Prozessor schon die Sprechererkennung (wenn an und "
               "ein Profil fragt), die Raum-Stimme, die Prüfung auf eine fremde Stimme und die Messung, wie viel der "
               "Aufnahme wirklich Stimme ist.",
               "While the GPU recognizes, the CPU already runs speaker identification (when on and a profile asks), "
               "the room voice, the check for an unknown voice and the measure of how much of the recording is "
               "really voice.")),
            S("s4", "schritt", ("An den ASR-Dienst", "To the ASR service"),
              ("mit API-Schlüssel und Stufe", "with API key and stage"),
              ("Das Panel schickt die Aufnahme mit dem API-Schlüssel an den Proxy. stufe.asr_level legt die Stufe des "
               "Profils bei, an einem geteilten Lautsprecher aber nicht. Nur das Panel kann eine Stufe setzen: mit "
               "dem Schlüssel aus vorrang-key und nur von dieser Maschine, sonst gilt normal.",
               "The panel sends the recording with the API key to the proxy. stufe.asr_level adds the profile's "
               "stage, but not at a shared speaker. Only the panel can set a stage: with the key from vorrang-key and "
               "only from this machine, else it is normal.")),
            S("s5", "frage", ("Schlüssel und Größe in Ordnung?", "Key and size fine?"),
              ("bevor ein Byte gelesen wird", "before a byte is read"),
              ("BodyLimit lehnt zu große Anfragen und solche ohne den richtigen Schlüssel ab, bevor etwas gelesen "
               "wird. Ohne eingetragenen Schlüssel darf nur diese Maschine selbst fragen.",
               "BodyLimit refuses requests that are too large or lack the right key before anything is read. "
               "Without a key set, only this machine itself may ask."),
              ("stop", "nein", ("Abgelehnt (401 oder 413)", "Refused (401 or 413)"))),
            S("s6", "frage", ("Engine bereit?", "Engine ready?"),
              ("lädt, Fehler oder aus", "loading, error or off"),
              ("engine_status fragt /health der Engine. Antwortet sie nicht, liest der Proxy ihren Zustand und den "
               "der systemd-Einheit und nennt den Grund.",
               "engine_status asks the engine's /health. If it does not answer, the proxy reads its state and that "
               "of the systemd unit and names the reason."),
              ("stop", "nein", ("Nicht bereit (503)", "Not ready (503)"))),
            S("s7", "schritt", ("Warten nach Vorrang", "Wait by priority"),
              ("so viele gleichzeitig wie die Engine nimmt", "as many at once as the engine takes"),
              ("PrioGate lässt so viele Aufnahmen durch, wie die Engine gleichzeitig nimmt (engine_max_seqs). Die "
               "anderen warten nach Stufe, dann nach Ankunft. Wer wartet, rückt alle vier Sekunden eine Stufe auf; "
               "eine laufende Anfrage wird nie unterbrochen.",
               "PrioGate lets as many recordings through as the engine takes at once (engine_max_seqs). The others "
               "wait by stage, then by arrival. Whoever waits moves up a stage every four seconds; a running request "
               "is never stopped."),
              ("stop", ("Schlange voll", "queue full"), ("Besetzt (503)", "Busy (503)"))),
            S("s8", "frage", ("Abtastrate erlaubt?", "Sample rate allowed?"),
              ("{common.RATE_MIN} bis {common.RATE_MAX} Hz", "{common.RATE_MIN} to {common.RATE_MAX} Hz"),
              ("audio_rate_ok liest die Abtastrate aus dem Kopf der Datei (WAV, FLAC, Ogg, WebM) oder fragt "
               "ffprobe. Ein Kopf mit erfundener Rate würde beim Umrechnen den Speicher füllen.",
               "audio_rate_ok reads the sample rate from the file's header (WAV, FLAC, Ogg, WebM) or asks ffprobe. A "
               "header with a made-up rate would fill the memory when it is converted."),
              ("stop", "nein", ("Abgelehnt (415)", "Refused (415)"))),
            S("s9", "schritt", ("Erkennen", "Recognize"),
              ("Qwen3-ASR auf der GPU oder Parakeet auf der CPU", "Qwen3-ASR on the GPU or Parakeet on the CPU"),
              ("Mit Qwen3-ASR geht die Aufnahme an die vLLM-Engine, die nur auf dieser Maschine lauscht; nur "
               "prompt, temperature und stream reichen durch, dazu die Kontextwörter aus den Einstellungen. Mit "
               "Parakeet erkennt der Proxy selbst auf dem Prozessor, in Stücken von höchstens {parakeet.MAX_PIECE_S} "
               "Sekunden, die an einer leisen Stelle geschnitten werden.",
               "With Qwen3-ASR the recording goes to the vLLM engine, which listens on this machine only; only "
               "prompt, temperature and stream pass through, plus the context words from the settings. With "
               "Parakeet the proxy recognizes itself on the CPU, in pieces of at most {parakeet.MAX_PIECE_S} seconds "
               "cut at a quiet spot.")),
            S("s10", "frage", ("Stille, Füllwort oder Echo?", "Silence, filler or echo?"),
              ("feste Regeln, kein Modell", "fixed rules, no model"),
              ("stille.check verwirft Text aus fast stummen Aufnahmen und ein einzelnes „Ja“ oder „Okay“ mit zu "
               "wenig Stimme. Für Profile prüft echo.check, ob der Text die eigene Stimme des Spark von einem anderen "
               "Gerät ist, und fremdstimme, ob ein von selbst geöffnetes Mikrofon eine fremde Stimme hörte.",
               "stille.check drops text from almost silent recordings and a lone „Yes“ or „Okay“ with too little "
               "voice. For profiles echo.check looks whether the text is the Spark's own voice from another device, "
               "and fremdstimme whether a microphone that opened by itself heard an unknown voice."),
              ("stop", "ja", ("Leerer Text, nicht als Frage", "Empty text, no question"))),
            S("s11", "frage", ("Stimme erkannt?", "Voice recognized?"),
              ("Ähnlichkeit ab {speakers.STRICTNESS.normal} und klar vorn", "similarity from {speakers.STRICTNESS.normal} and clearly ahead"),
              ("speakers.identify vergleicht die Aufnahme mit jedem eingelernten Stimmabdruck. Nur ein klarer Treffer "
               "(über der Schwelle der gewählten Strenge und deutlich vor dem Zweiten) zählt. Live zeigt nur "
               "„Stimme erkannt“, nie wessen.",
               "speakers.identify compares the recording with every taught voiceprint. Only a clear match (above the "
               "threshold of the chosen strictness and clearly ahead of the runner-up) counts. Live shows only "
               "„voice recognized“, never whose."),
              ("info", "ja", ("Name und ein Token des Profils gehen mit", "The profile's name and a token go along"))),
            S("s12", "ende", ("Text zurück", "Text back"),
              ("Gäste sehen bei Fehlern nur einen Code", "guests see only a code on errors"),
              ("Der Text geht an das Gerät, das daraus die Frage an den Chat macht. Bei einem Fehler bekommt ein Gast "
               "nur einen festen Code, nie den Text des Dienstes.",
               "The text goes to the device, which turns it into the question to the chat. On an error a guest gets "
               "only a fixed code, never the service's text.")),
        ],
        "beispiele": [
            (("Frage im Browser, Profil", "Question in the browser, profile"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s11!", "s12"],
             ("Text mit erkannter Stimme zurück.", "Text back with the recognized voice.")),
            (("Klick nach der Antwort", "Click after the answer"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s10!"],
             ("Verworfen: zu wenig Stimme, keine Frage.", "Dropped: too little voice, no question.")),
            (("Datei mit erfundener Abtastrate", "File with a made-up sample rate"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!"],
             ("Abgelehnt, bevor die Engine sie sieht.", "Refused before the engine sees it.")),
            (("Engine lädt noch", "Engine still loading"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!"],
             ("Abgelehnt mit dem Grund, das Gerät sagt Bescheid.", "Refused with the reason, the device says so.")),
        ],
        "zahlen": [
            ("{admin.MAX_AUDIO|mb}", ("größte Aufnahme am Panel", "largest recording at the panel"), "admin.MAX_AUDIO"),
            ("{common.RATE_MIN}–{common.RATE_MAX}", ("erlaubte Abtastrate in Hz", "allowed sample rate in Hz"), "common.RATE_MIN"),
            ("{guard.RATE.asr.1}", ("Aufnahmen pro Minute und Profil", "recordings per minute and profile"), "guard.RATE"),
            ("{guard.BUSY.asr}", ("Gäste gleichzeitig", "guests at once"), "guard.BUSY"),
            ("{speakers.STRICTNESS.normal}", ("Schwelle der Sprechererkennung bei normaler Strenge",
                                              "speaker identification threshold at normal strictness"), "speakers.STRICTNESS"),
            ("{parakeet.MAX_AUDIO_S|min}", ("Minuten Ton liest Parakeet höchstens", "minutes of audio Parakeet reads at most"),
             "parakeet.MAX_AUDIO_S"),
        ],
        "einstellen": [
            ("Einstellungen → Spracherkennung: Qwen3-ASR auf der Grafikkarte oder Parakeet auf dem Prozessor, "
             "Sprache und Kontextwörter.",
             "Settings → Speech recognition: Qwen3-ASR on the GPU or Parakeet on the CPU, language and context words."),
            ("Funktionen → Sprechererkennung: Profile an der Stimme erkennen und wie streng (Standard aus).",
             "Features → Speaker recognition: recognize profiles by their voice and how strictly (default off)."),
        ],
        "sehen": [
            ("Zustand → Monitoring: Zustand der Engine, Anfragen, Fehler, mittlere Dauer und die Warteschlange.",
             "Status → Monitoring: engine state, requests, failures, average time and the queue."),
            ("Zustand → Logs → Anfragen: wie lange eine Aufnahme gewartet hat und wie viele sie überholt hat.",
             "Status → Logs → Requests: how long a recording waited and how many it overtook."),
        ],
        "code": [
            ("admin.test_asr", ("Ratenlimit und Plätze für Gäste", "rate limit and places for guests")),
            ("admin._test_asr", ("der Weg im Panel: lesen, nebenbei prüfen, weiterreichen", "the way in the panel: read, check alongside, pass on")),
            ("stufe.asr_level", ("Stufe des Profils, nicht am geteilten Lautsprecher", "the profile's stage, not at a shared speaker")),
            ("common.BodyLimit", ("Größe und Schlüssel vor dem Lesen", "size and key before reading")),
            ("common.PrioGate", ("Warten nach Vorrang", "waiting by priority")),
            ("common.audio_rate_ok", ("Abtastrate aus dem Dateikopf", "sample rate from the file header")),
            ("asr_proxy.transcriptions", ("der Proxy vor der Engine", "the proxy in front of the engine")),
            ("asr_proxy.engine_status", ("bereit, lädt, Fehler oder aus", "ready, loading, error or off")),
            ("parakeet.Recognizer", ("Parakeet auf dem Prozessor", "Parakeet on the CPU")),
            ("stille.check", ("Stille und Füllwörter", "silence and fillers")),
            ("echo.check", ("die eigene Stimme des Spark", "the Spark's own voice")),
            ("speakers.identify", ("wessen Stimme, nur bei klarem Treffer", "whose voice, only on a clear match")),
        ],
        "tests": ["test_units", "test_hardening", "test_stufe", "test_stille", "test_echo", "test_stimmabdruck"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Sprachausgabe
    "tts": {
        "stand": "836b6f0dc0",
        "bezug": {
            "textnorm.NUMBER_MODES": ["s7"], "tts_proxy.speech": ["s1"], "tts_proxy.check_reference": ["s8"],
            "tts_proxy.engine_status": ["s4"], "tts_proxy.apply_clone": ["s8"], "textnorm.speech_markdown": ["s5"],
            "textnorm.hide_secrets": ["s5"], "textnorm.clean_text": ["s6"], "textnorm.guess_language": ["s7"],
            "textnorm.speak_numbers": ["s7"], "common.PrioGate": ["s10"],
        },
        "kurz": ("Die Sprachausgabe macht aus Text Ton. Der TTS-Dienst nimmt einen Satz an, räumt ihn auf, verdeckt "
                 "Geheimnisse, wählt Sprache und Stimme und gibt ihn an die Engine (Qwen3-TTS über vllm-omni), die nur "
                 "auf dieser Maschine lauscht. Der Ton kommt gestreamt zurück.",
                 "Speech output turns text into sound. The TTS service takes a sentence, tidies it, hides secrets, "
                 "picks language and voice and passes it to the engine (Qwen3-TTS via vllm-omni), which listens on "
                 "this machine only. The sound comes back streamed."),
        "warum": ("Ein Lautsprecher im Raum sagt alles laut, was er bekommt. Passwörter und Codes dürfen dort nie "
                  "gesprochen werden, und Zeichen wie Sternchen, Links oder Emojis klingen falsch. Deshalb laufen feste "
                  "Regeln auf jedem Satz, egal woher er kommt: Chat, Lautsprecher, Telegram, Erinnerungen.",
                  "A speaker in the room says out loud whatever it gets. Passwords and codes must never be spoken "
                  "there, and signs like asterisks, links or emojis sound wrong. So fixed rules run on every sentence, "
                  "wherever it comes from: chat, speaker, Telegram, reminders."),
        "ablauf": [
            S("s1", "start", ("Satz zum Sprechen", "A sentence to speak"),
              ("POST /v1/audio/speech", "POST /v1/audio/speech"),
              ("Das Panel schickt jeden Satz einer Antwort mit dem API-Schlüssel und der Stufe des Profils an den "
               "TTS-Dienst. Andere Programme dürfen das mit dem API-Schlüssel auch.",
               "The panel sends every sentence of an answer with the API key and the profile's stage to the TTS "
               "service. Other programs may do so too with the API key.")),
            S("s2", "frage", ("Schlüssel und Größe in Ordnung?", "Key and size fine?"),
              ("bevor ein Byte gelesen wird", "before a byte is read"),
              ("BodyLimit lehnt zu große Anfragen und solche ohne den richtigen Schlüssel ab, bevor etwas gelesen "
               "wird.", "BodyLimit refuses requests that are too large or lack the right key before anything is read."),
              ("stop", "nein", ("Abgelehnt (401 oder 413)", "Refused (401 or 413)"))),
            S("s3", "frage", ("Text gültig?", "Text valid?"),
              ("höchstens {textnorm.MAX_INPUT} Zeichen", "at most {textnorm.MAX_INPUT} characters"),
              ("Der Text darf nicht leer sein und höchstens {textnorm.MAX_INPUT} Zeichen haben. Eine Vorlage-Stimme "
               "nimmt check_reference nur als eingebettete data:audio-Adresse an, nie als Link: die Engine würde "
               "einen Link sonst selbst aus dem Heimnetz holen.",
               "The text must not be empty and may have at most {textnorm.MAX_INPUT} characters. check_reference "
               "takes a reference voice only as an embedded data:audio address, never as a link: the engine would "
               "otherwise fetch a link itself from the home network."),
              ("stop", "nein", ("Abgelehnt (400)", "Refused (400)"))),
            S("s4", "frage", ("Engine bereit?", "Engine ready?"),
              ("Haupt-Engine oder VoiceDesign", "main engine or VoiceDesign"),
              ("Eine VoiceDesign-Anfrage geht an die zweite Engine, wenn sie eingeschaltet ist; alles andere an die "
               "Haupt-Engine. engine_status fragt deren /health und nennt sonst den Grund.",
               "A VoiceDesign request goes to the second engine when it is on; everything else to the main engine. "
               "engine_status asks its /health and otherwise names the reason."),
              ("stop", "nein", ("Nicht bereit (503)", "Not ready (503)"))),
            S("s5", "schritt", ("Markdown weg, Geheimnisse verdeckt", "Markdown off, secrets hidden"),
              ("immer, ohne Schalter", "always, no switch"),
              ("speech_markdown nimmt die Zeichen der Formatierung heraus, dann ersetzt hide_secrets Passwörter, "
               "Codewörter, Einmal-Codes und Schlüssel durch „{textnorm.SECRET_HINT.de}“. Das läuft auf jeder "
               "Anfrage, auch wenn „Text bereinigen“ aus ist; die geschriebene Antwort behält den Wert.",
               "speech_markdown takes out the formatting signs, then hide_secrets replaces passwords, code words, "
               "one-time codes and keys with „{textnorm.SECRET_HINT.en}“. This runs on every request, also when "
               "„Clean text“ is off; the written answer keeps the value.")),
            S("s6", "schritt", ("Text bereinigen", "Clean the text"),
              ("Emojis, Lachen, Links, Code", "emojis, laughter, links, code"),
              ("clean_text nimmt Emojis, „haha“, *lacht*, Codeblöcke und Links heraus, beruhigt auf Wunsch "
               "Ausrufe und setzt ans Zeilenende einen Punkt, damit die Stimme absetzt. Bleibt nichts übrig, kommt "
               "keine Anfrage an die Engine.",
               "clean_text takes out emojis, „haha“, *laughs*, code blocks and links, calms exclamations if wanted "
               "and puts a full stop at the end of a line so the voice settles. If nothing is left, no request goes "
               "to the engine."),
              ("stop", ("nichts übrig", "nothing left"), ("Abgelehnt (400)", "Refused (400)"))),
            S("s7", "schritt", ("Sprache, Aussprache, Zahlen", "Language, pronunciation, numbers"),
              ("feste Regeln vor dem Modell", "fixed rules before the model"),
              ("Steht die Sprache auf Auto, rät guess_language an häufigen Wörtern Deutsch oder Englisch, damit ein "
               "einzelnes englisches Wort nicht den Ton der ganzen Antwort ändert. Dann gilt die eigene "
               "Aussprache-Liste, danach schreibt speak_numbers Datum, Uhrzeit, Geld und Zahlen aus.",
               "When the language is Auto, guess_language guesses German or English from frequent words, so a single "
               "English word does not change the tone of the whole answer. Then the own pronunciation list applies, "
               "after that speak_numbers writes out date, time, money and numbers.")),
            S("s8", "schritt", ("Stimme wählen", "Pick the voice"),
              ("eingebaut, geklont oder beschrieben", "built in, cloned or described"),
              ("Temperatur, top_p und ein fester Seed aus den Einstellungen halten die Stimme von Satz zu Satz gleich. "
               "Ein Base-Modell spricht mit einer geklonten Stimme aus voices/ (apply_clone); ein unbekannter Name "
               "fällt auf die Standardstimme zurück.",
               "Temperature, top_p and a fixed seed from the settings keep the voice the same from sentence to "
               "sentence. A Base model speaks with a cloned voice from voices/ (apply_clone); an unknown name falls "
               "back to the default voice.")),
            S("s9", "frage", ("Gestreamt mit anderem Tempo?", "Streamed at another tempo?"),
              ("die Engine kann das beim Streamen nicht", "the engine cannot do that while streaming"),
              ("vllm-omni nimmt beim Streamen kein Tempo an. Dann streckt tempo.Stretcher den Ton Stück für Stück "
               "selbst (WSOLA, die Tonhöhe bleibt).",
               "vllm-omni takes no tempo when streaming. Then tempo.Stretcher stretches the sound piece by piece "
               "itself (WSOLA, the pitch stays)."),
              ("info", "ja", ("Der Proxy streckt den Ton selbst", "The proxy stretches the sound itself"))),
            S("s10", "schritt", ("Warten nach Vorrang", "Wait by priority"),
              ("ein Tor je Engine", "one gate per engine"),
              ("PrioGate lässt so viele Sätze durch, wie die Engine gleichzeitig nimmt (engine_max_seqs); die "
               "anderen warten nach Stufe, dann nach Ankunft.",
               "PrioGate lets as many sentences through as the engine takes at once (engine_max_seqs); the others "
               "wait by stage, then by arrival."),
              ("stop", ("Schlange voll", "queue full"), ("Besetzt (503)", "Busy (503)"))),
            S("s11", "schritt", ("Engine spricht", "The engine speaks"),
              ("nur auf dieser Maschine, gestreamt", "on this machine only, streamed"),
              ("Die Engine erzeugt den Ton. Gestreamt kommt er als Stücke zurück; das erste Stück ist absichtlich "
               "klein (initial_chunk_frames), damit der Ton schnell beginnt, auch wenn mehrere Anfragen laufen.",
               "The engine makes the sound. Streamed it comes back in pieces; the first piece is small on purpose "
               "(initial_chunk_frames) so the sound starts fast, also when several requests run.")),
            S("s12", "ende", ("Ton zurück", "Sound back"),
              ("Zähler fürs Monitoring", "counters for monitoring"),
              ("Der Proxy reicht den Ton unverändert weiter und zählt nur Dauer, Länge und Fehler für das "
               "Monitoring, nie den Text.",
               "The proxy passes the sound on unchanged and counts only time, length and errors for monitoring, "
               "never the text.")),
        ],
        "beispiele": [
            (("Antwortsatz im Chat", "Answer sentence in the chat"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Gesprochen, gestreamt, mit fester Stimme.", "Spoken, streamed, with a steady voice.")),
            (("Passwort in der Antwort", "Password in the answer"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
             ("Gesprochen wird „{textnorm.SECRET_HINT.de}“, geschrieben bleibt der Wert.",
              "The voice says „{textnorm.SECRET_HINT.en}“, the written answer keeps the value.")),
            (("Nur ein Emoji", "Only an emoji"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!"],
             ("Nichts zu sagen, nichts geht an die Engine.", "Nothing to say, nothing goes to the engine.")),
            (("Schneller sprechen", "Speak faster"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s9!", "s10", "s11", "s12"],
             ("Der Proxy streckt den gestreamten Ton.", "The proxy stretches the streamed sound.")),
        ],
        "zahlen": [
            ("{textnorm.MAX_INPUT}", ("Zeichen pro Anfrage höchstens", "characters per request at most"), "textnorm.MAX_INPUT"),
            ("„{textnorm.SECRET_HINT.de}“", ("sagt die Stimme statt eines Geheimnisses", "the voice says instead of a secret"),
             "textnorm.SECRET_HINT"),
            ("{textnorm.NUMBER_MODES|anzahl}", ("Arten, Zahlen vorzulesen", "ways to read numbers"), "textnorm.NUMBER_MODES"),
        ],
        "einstellen": [
            ("Einstellungen → Sprachausgabe: Modell, Standardstimme, Sprache, Text bereinigen, Zahlen vorlesen und "
             "die eigene Aussprache-Liste.",
             "Settings → Speech output: model, default voice, language, clean text, reading numbers and the own "
             "pronunciation list."),
            ("Einstellungen → Stimmen: eigene Stimmen aufnehmen, anhören und sichern (für ein Base-Modell).",
             "Settings → Voices: record, play and save own voices (for a Base model)."),
        ],
        "sehen": [
            ("Zustand → Monitoring: Zustand der Engines, Anfragen, Fehler, Zeit bis zum ersten Ton und die "
             "Warteschlange.",
             "Status → Monitoring: engine state, requests, failures, time to the first sound and the queue."),
        ],
        "code": [
            ("tts_proxy.speech", ("der Weg eines Satzes durch den Proxy", "the way of a sentence through the proxy")),
            ("tts_proxy.check_reference", ("Vorlage nur eingebettet", "reference only embedded")),
            ("tts_proxy.engine_status", ("bereit, lädt, Fehler oder aus", "ready, loading, error or off")),
            ("tts_proxy.apply_clone", ("geklonte Stimme aus voices/", "cloned voice from voices/")),
            ("textnorm.speech_markdown", ("Markdown-Zeichen weg", "markdown signs off")),
            ("textnorm.hide_secrets", ("Geheimnisse nie sprechen", "never speak secrets")),
            ("textnorm.clean_text", ("Emojis, Lachen, Links, Code", "emojis, laughter, links, code")),
            ("textnorm.guess_language", ("Deutsch oder Englisch raten", "guess German or English")),
            ("textnorm.speak_numbers", ("Zahlen ausschreiben", "write out numbers")),
            ("tempo.Stretcher", ("Tempo beim Streamen", "tempo while streaming")),
            ("common.PrioGate", ("Warten nach Vorrang", "waiting by priority")),
        ],
        "tests": ["test_units", "test_markdown", "test_hardening", "test_stufe", "test_tempo"],
        "heute": [],
    },

    # ------------------------------------------------------------------ state/
    "state": {
        "stand": "5457d99e63",
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
              ("Jede Datei in state/ steht in genau einer Liste: backup.STATE_FILES ({backup.STATE_FILES|anzahl}, "
               "kommen in jede Sicherung) oder backup.STATE_LOCAL ({backup.STATE_LOCAL|anzahl}, mit ihrem Grund). "
               "test_technik findet jeden Namen, den der Code dort schreibt, und verlangt ihn in einer der Listen.",
               "Every file in state/ is in exactly one list: backup.STATE_FILES ({backup.STATE_FILES|anzahl}, go "
               "into every backup) or backup.STATE_LOCAL ({backup.STATE_LOCAL|anzahl}, with their reason). "
               "test_technik finds every name the code writes there and wants it in one of the lists."),
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
               "verbund), ihn neu lesen.",
               "_forget_cached makes the modules that keep a key in memory (vault, push, apns, chats, verbund) read "
               "it again.")),
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
            ("{backup.STATE_FILES|anzahl}", ("Dateien in jeder Sicherung", "files in every backup"), "backup.STATE_FILES"),
            ("{backup.STATE_LOCAL|anzahl}", ("Dateien und Ordner, die mit Grund draußen bleiben",
                                             "files and folders that stay out with a reason"), "backup.STATE_LOCAL"),
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
            ("backup.STATE_FILES", ("was in die Sicherung kommt", "what goes into the backup")),
            ("backup.STATE_LOCAL", ("was mit Grund draußen bleibt", "what stays out with a reason")),
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
        "stand": "798fffaaf3",
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
              ("Jeder Dateiname steht entweder in einem Bereich von speicher.AREAS (darf auf den eigenen Speicher) "
               "oder in speicher.LOCAL (bleibt auf dem Spark, mit Grund: Schlüssel, Zugänge, Einstellungen, "
               "Stimmabdruck, Warteschlangen). test_technik prüft jeden Namen, den der Code schreibt.",
               "Every file name is either in an area of speicher.AREAS (may go to the own storage) or in "
               "speicher.LOCAL (stays on the Spark, with a reason: keys, accounts, settings, voiceprint, queues). "
               "test_technik checks every name the code writes.")),
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
            [("Zugänge, Schlüssel, Stimmabdruck", "Accounts, keys, voiceprint"), ("speicher.LOCAL", "speicher.LOCAL"), "✕"],
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
            ("speicher.AREAS", ("was auf den eigenen Speicher darf", "what may go to the own storage")),
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

