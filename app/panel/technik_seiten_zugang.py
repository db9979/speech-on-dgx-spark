"""Zustand → Technik, Knoten-Seiten: the pages of the guard, middleware and access
(waechter, middleware, zugang). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "waechter": {
        "stand": "0e36dcde85",
        "bezug": {
            "notaus.AUTO": ["s4"], "netguard.allowed": ["s3", "s7", "s8"], "netguard.resolve": ["s2"],
            "netguard._Transport": ["s10", "s11"], "netguard._Capped": ["s11"], "netguard.same_site": ["s10"],
            "netguard.own_addresses": ["s3"], "netguard.model_addresses": ["s3"], "netguard.IMAP4_SSL": ["s9"], "notaus.watch": ["s2"],
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
               "Adresse im LAN oder VPN (own_addresses liest sie jede Minute neu). Laufen die Modelle auf einem "
               "anderen Rechner (models.host), gelten seine Adressen genauso (model_addresses).",
               "The ports of the own services are closed on this machine: on loopback and on every own address in "
               "the LAN or VPN (own_addresses reads them again every minute). When the models run on another "
               "computer (models.host), its addresses count the same (model_addresses)."),
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
            ("netguard.model_addresses", ("die Adressen des Modell-Rechners, wenn er ein anderer ist",
                                          "the model computer's addresses when it is another one")),
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
        "stand": "8380709088",
        "bezug": {
            "panel.slow_reads": ["s2"], "panel.emergency": ["s3", "s4"], "notaus.at_home": ["s5"],
            "panel.sessions": ["s7", "s11", "s12"], "guard.same_origin": ["s7"], "panel._may_upload": ["s8"],
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
              ("In Stufe {notaus.STAGE.gespraech} gehen auch im Heimnetz nur noch Anmelden, das "
               "Aufheben des Notaus und das Lesen von Zustand, Logs und Live durch. In den Stufen darunter läuft "
               "im Heimnetz alles weiter; Aktionen hält das Panel dann tiefer unten an.",
               "In stage {notaus.STAGE.gespraech} only logins, lifting the kill switch and reading "
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
               "überhaupt angemeldet sein könnte: Admin-Cookie, Profil oder eine Authorization-Zeile. Die Datei "
               "eines anderen Sparks (/api/verbund/blob) nur, wenn Verbund und Dateien an sind und der Absender ein "
               "erlaubter Spark mit bekanntem Schlüssel ist. Die echte Prüfung kommt danach im Endpunkt; hier geht "
               "es nur darum, dass kein Byte eines fremden Uploads gelesen wird.",
               "The paths for big uploads (backups, voices, sound, documents, pictures, MCP) only accept someone who "
               "could be logged in at all: admin cookie, profile or an Authorization line. Another Spark's file "
               "(/api/verbund/blob) only when Verbund and files are on and the sender is an allowed Spark with a "
               "known key. The real check comes later in the endpoint; here no byte of a stranger's upload is read."),
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
               "nächste Station, „Anmeldung, Profil“). Ist der Verbrauchszähler an, merkt sich die Anfrage vorher, "
               "für welches Profil sie läuft: was sie die Modelle fragt, zählt für dieses Profil.",
               "Only now the endpoint reads the request and checks login, profile and rate limit itself (the next "
               "box, „Login, profile“). With the usage counter on, the request first notes which profile it runs "
               "for: what it asks the models counts for that profile.")),
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
             ("Anmelden, Aufheben, Zustand und Logs lesen", "logging in, lifting, reading status and logs")],
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
        "stand": "78b276ef2f",
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
               "ist mit Passwort, einem eigenen Schlüssel dieses Spark und dem zweiten Schritt signiert. War der "
               "zweite Schritt dabei (Code, Passkey oder vertrauter Browser), trägt die Sitzung sein Zeichen: nur "
               "dann zählt eine Admin-Rolle des Profils, ohne eigene Admin-Anmeldung.",
               "The address's counter is cleared; strangers' wrong attempts for the name keep counting. The profile "
               "cookie is signed and stands in the list of signed-in browsers; it holds at most "
               "{profiles.SESSION_DAYS} days without use and is renewed while used. The admin cookie is signed with "
               "the password, a key of this Spark only and the second step. When the second step was part of it "
               "(code, passkey or a trusted browser) the session carries its mark: only then does a profile's "
               "admin role count, without an admin sign-in of its own.")),
            S("s6", "schritt", ("Profil bestimmen", "Find the profile"),
              ("profiles.current", "profiles.current"),
              ("Zuerst, was nur das Panel selbst setzt (Telegram, „Spark fragen“ über MCP), dann der Geräteschlüssel "
               "(nur sein Hash ist gespeichert), dann das Cookie: Signatur, Alter, Sitzung noch in der Liste und nicht "
               "abgemeldet.",
               "First what only the panel itself sets (Telegram, „Ask Spark“ over MCP), then the device key (only its "
               "hash is stored), then the cookie: signature, age, session still in the list and not logged out.")),
            S("s7", "frage", ("Schlüssel für diesen Weg frei?", "Key free for this path?"),
              ("Bereich des Schlüssels", "the key's scope"),
              ("Ein Schlüssel mit Bereich (App, Uhr, Raum, Home Assistant, Schreibhilfe, Begleiter, Terminal) reicht nur für "
               "seine eigenen Pfade und nur, solange Admin und Profil die Funktion anhaben. Ist sie gerade aus oder "
               "hat das Profil seinen eigenen Notaus an, antwortet das Panel mit 503 statt 401, damit die App ihre "
               "Kopplung behält.",
               "A key with a scope (app, watch, room, Home Assistant, writing help, companion, terminal) only reaches its own "
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
            (("Admin-Profil meldet sich mit Code an", "Admin profile signs in with its code"), ["s1", "s2", "s3", "s4", "s5"],
             ("Angemeldet und gleich Admin: die Sitzung trägt das Zeichen des zweiten Schritts.",
              "Signed in and admin at once: the session carries the second step's mark.")),
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
            [("Profil mit Admin-Rolle", "Profile with an admin role"),
             ("Cookie mit Zeichen des zweiten Schritts oder App-Schlüssel von danach", "cookie with the second step's mark or an app key made after it"),
             ("Admin-Seiten seiner Rolle; nur „Schutz ändern“ fragt den Code", "the admin pages of its role; only „change protection“ asks for the code")],
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
            ("Personen und Geräte → Gesperrte Funktionen: eine Funktion für einzelne Profile sperren.",
             "People and devices → Blocked functions: block a function for single profiles."),
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
}
