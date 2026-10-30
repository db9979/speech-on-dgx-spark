"""Zustand → Technik, Knoten-Seiten: the pages of outside services, internet and Spark split
(aussen, internet, teilen, werkstatt, post). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "aussen": {
        "stand": "b71a45f2a2",
        "bezug": {
            "dienstwacht.TIMEOUT": ["s5"], "notaus.locked_tools": ["s3"], "dienstwacht.tool_down": ["s5"],
            "netguard.client": ["s8", "s9", "s10"], "netguard.IMAP4_SSL": ["s9"],
            "homeassistant._client": ["s7", "s9"], "mcp._client": ["s7", "s9", "s10"],
            "chat.web_search": ["s6", "s9"], "regeln": ["s7", "s8"], "regel:SearXNG": ["s6"],
            "regel:Wetter, Fahrplan, Wikipedia": ["s6"], "regel:Sprachmodell": ["s6"],
        },
        "kurz": ("Dienste im Heimnetz sind, was der Spark im eigenen Netz fragt: Home Assistant, NAS, Kiwix, SearXNG und "
                 "MCP-Dienste, auf Wunsch auch Kalender, Kontakte und Mail. Adressen aus Einstellungen gehen über den "
                 "Wächter (netguard) mit einer festen Stufe; feste Dienste wie SearXNG gehen direkt. Der Weg eines "
                 "Werkzeugaufrufs ist derselbe wie für die Dienste im Internet (eigener Kasten).",
                 "Services at home are what the Spark asks in the own network: Home Assistant, NAS, Kiwix, SearXNG "
                 "and MCP services, on request also calendars, contacts and mail. Addresses from settings go through "
                 "the guard (netguard) with a fixed level; fixed services like SearXNG go directly. The way of a tool "
                 "call is the same as for the internet services (own box)."),
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
               "netguard.DIRECT_OK; ein Selbsttest meldet jedes Modul, das direkt verbindet und dort fehlt. Fragt die "
               "Person nach Heutigem oder den letzten Tagen (feste Wörter, frisch.zeitraum), sucht SearXNG nur in diesem "
               "Zeitraum (bei Nachrichten auch in seiner Kategorie News); jeder Treffer trägt sein Datum, ältere fallen weg.",
               "The language model, SearXNG at the entered address, weather, transit, Wikipedia and fixed services "
               "like Apple push go directly, without the guard. Which modules may do that and why is listed in "
               "netguard.DIRECT_OK; a self-test reports every module that connects directly and is missing there. When "
               "the person asks for today or the last days (fixed words, frisch.zeitraum), SearXNG searches only that "
               "period (for news also its news category); every hit carries its date, older ones are dropped."),
              ("ok", "ja", "s9")),
            S("s7", "schritt", ("Stufe des Dienstes", "Level of the service"),
              ("Heimnetz · Nutzer · nur Internet", "home · user · internet only"),
              ("Jedes Modul ruft den Wächter mit seiner festen Stufe: Home Assistant und Kiwix mit Heimnetz; Kalender, "
               "Kontakte, Aufgaben, Mail und MCP mit Nutzer; reMarkable und Seiten aus der Suche mit nur Internet. "
               "Die Live-Verbindung zu Home Assistant (halive) prüft ihre Adresse ebenso mit Heimnetz. "
               "Die Stufe steht im Code, nicht in den Einstellungen.",
               "Each module calls the guard with its fixed level: Home Assistant and Kiwix with home; calendars, "
               "contacts, tasks, mail and MCP with user; reMarkable and pages from search with internet only. The "
               "live connection to Home Assistant (halive) checks its address with home as well. The level is in the code, "
               "not in the settings.")),
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
               "eingetragene Seite. Mail geht über IMAP mit TLS an die geprüfte Adresse. Mit „Schnellere Websuche“ "
               "hat jede Trefferseite höchstens {chat.PAGE_SECONDS} s, bringt die zur Frage passenden Stellen, und "
               "dieselbe Suche kommt {chat.SEARCH_CACHE|min} Minuten lang aus dem Arbeitsspeicher.",
               "The panel unseals the profile's login (token, password) only now and sends it only to the entered "
               "site. Mail goes over IMAP with TLS to the checked address. With „Faster web search“ each result page "
               "gets at most {chat.PAGE_SECONDS} s, brings the parts that fit the question, and the same search comes "
               "from memory for {chat.SEARCH_CACHE|min} minutes.")),
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
            ("Funktionen → Aufträge → Dienste per MCP: welche Server und Werkzeuge angeboten werden.",
             "Features → Jobs → Services over MCP: which servers and tools are offered."),
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
    "internet": {
        "stand": "40ecf5dc08",
        "bezug": {
            "regeln": ["s3", "s4"], "regel:Seiten aus der Suche": ["s4", "s5"], "regel:Mail, Kalender, Kontakte": ["s4", "s5"],
            "regel:reMarkable": ["s4", "s5"], "regel:Wetter, Fahrplan, Wikipedia": ["s3"], "regel:Telegram": ["s7"],
            "regel:Update-Prüfung": ["s7"], "regel:Apple-Push": ["s7"],
        },
        "kurz": ("Dienste im Internet sind alles, was der Spark außerhalb des Hauses fragt: Mail und Kalender beim Anbieter, "
                 "Seiten aus der Suche, Wetter, Fahrplan, Wikipedia, reMarkable, dazu Telegram, Apple-Push und die "
                 "Update-Prüfung. Werkzeuge gehen über den Wächter oder eine feste Adresse; der Notaus schaltet sie ab.",
                 "Internet services are everything the Spark asks outside the house: mail and calendars at the provider, "
                 "pages from search, weather, transit, Wikipedia, reMarkable, plus Telegram, Apple push and the update "
                 "check. Tools go through the guard or a fixed address; the kill switch turns them off."),
        "warum": ("Was ins Internet geht, verlässt das Haus. Deshalb nur mit festen Regeln, nur an geprüfte Adressen, mit "
                  "begrenzter Antwort, und ein Notaus, der alles Internet auf einmal anhält.",
                  "What goes to the internet leaves the house. So only by fixed rules, only to checked addresses, with a "
                  "limited answer, and a kill switch that stops all internet at once."),
        "ablauf": [
            S("s1", "start", ("Werkzeug will ins Internet", "A tool wants to the internet"),
              ("chat_tools.run", "chat_tools.run"),
              ("Das Modell hat ein angebotenes Werkzeug gerufen, das einen Dienst im Internet braucht. Welche Werkzeuge "
               "überhaupt angeboten werden, haben Rechte und Weiche schon entschieden.",
               "The model called an offered tool that needs a service on the internet. Which tools are offered at all "
               "was decided by the rights and the switch already.")),
            S("s2", "frage", ("Notaus hält das Internet an?", "Kill switch stops the internet?"),
              ("ab Stufe {notaus.STAGE.internet}", "from stage {notaus.STAGE.internet}"),
              ("Ab Stufe {notaus.STAGE.internet} ruhen die {notaus.INTERNET_TOOLS|anzahl} Werkzeuge, die selbst ins "
               "Internet gehen (notaus.INTERNET_TOOLS); notaus.locked_tools wird bei jedem Aufruf neu gelesen.",
               "From stage {notaus.STAGE.internet} the {notaus.INTERNET_TOOLS|anzahl} tools that go to the internet by "
               "themselves rest (notaus.INTERNET_TOOLS); notaus.locked_tools is read again for every call."),
              ("stop", "ja", ("Gesperrt (Notaus)", "Blocked (kill switch)"))),
            S("s3", "frage", ("Feste Adresse?", "Fixed address?"),
              ("netguard.DIRECT_OK", "netguard.DIRECT_OK"),
              ("Wetter, Fahrplan und Wikipedia fragen eine feste Adresse aus dem Code oder den Admin-Einstellungen, nie "
               "eine aus fremdem Text. Welche Module direkt verbinden dürfen und warum, steht in netguard.DIRECT_OK.",
               "Weather, transit and Wikipedia ask a fixed address from the code or the admin settings, never one from "
               "outside text. Which modules may connect directly and why is listed in netguard.DIRECT_OK."),
              ("ok", "ja", "s6")),
            S("s4", "schritt", ("Über den Wächter", "Through the guard"),
              ("netguard.client mit fester Stufe", "netguard.client with a fixed level"),
              ("Seiten aus der Suche und reMarkable fragen mit Stufe nur Internet (netguard.PUBLIC), Mail, Kalender und "
               "Kontakte mit Stufe Nutzer. Die Stufe steht im Code.",
               "Pages from search and reMarkable ask at level internet only (netguard.PUBLIC), mail, calendars and "
               "contacts at level user. The level is in the code.")),
            S("s5", "frage", ("Adresse erlaubt?", "Address allowed?"),
              ("Kasten Wächter", "box Guard"),
              ("netguard.allowed prüft jede aufgelöste Adresse: keine eigenen Dienste, kein 169.254, kein Heimnetz auf "
               "Stufe nur Internet.",
               "netguard.allowed checks every resolved address: no own services, no 169.254, no home network at level "
               "internet only."),
              ("stop", "nein", ("Gesperrt", "Blocked"))),
            S("s6", "ende", ("Antwort als Daten", "Answer as data"),
              ("höchstens {netguard.MAX_BYTES|mb}", "at most {netguard.MAX_BYTES|mb}"),
              ("Die Antwort wird an der Grenze abgeschnitten und geht als Daten ans Modell, nie als Befehl.",
               "The answer is cut at the limit and goes to the model as data, never as a command.")),
            S("s7", "schritt", ("Was der Spark selbst schickt", "What the Spark sends by itself"),
              ("Telegram, Push, Update", "Telegram, push, update"),
              ("Ohne Werkzeug gehen nur feste Wege hinaus: die Telegram-Bot-API, Apple- und Browser-Push an bekannte "
               "Dienste und die Update-Prüfung bei GitHub, jede mit Grund in netguard.DIRECT_OK.",
               "Without a tool only fixed ways go out: the Telegram bot API, Apple and browser push to known services "
               "and the update check at GitHub, each with a reason in netguard.DIRECT_OK.")),
        ],
        "beispiele": [
            (("Seite aus der Suche lesen", "Read a page from search"), ["s1", "s2", "s3", "s4", "s5", "s6"],
             ("Über den Wächter mit Stufe nur Internet; gelesen.", "Through the guard at level internet only; read.")),
            (("Wetter fragen", "Ask the weather"), ["s1", "s2", "s3", "s3!", "s6"],
             ("Feste Adresse, ohne Wächter.", "Fixed address, without the guard.")),
            (("Notaus Stufe 1, Websuche", "Kill switch stage 1, web search"), ["s1", "s2", "s2!"],
             ("Gesperrt, nichts geht hinaus.", "Blocked, nothing goes out.")),
        ],
        "regeln": [
            [("Dienst", "Service"), ("Weg", "Way")],
            [("Seiten aus der Suche", "Pages from search"), ("Wächter, nur Internet", "guard, internet only")],
            [("Mail, Kalender, Kontakte", "Mail, calendars, contacts"), ("Wächter, Stufe Nutzer", "guard, level user")],
            [("reMarkable", "reMarkable"), ("Wächter, nur erlaubte Hosts", "guard, allowed hosts only")],
            [("Wetter, Fahrplan, Wikipedia", "Weather, transit, Wikipedia"), ("feste Adresse", "fixed address")],
            [("Telegram", "Telegram"), ("feste Adresse, Bot-API", "fixed address, bot API")],
            [("Update-Prüfung", "Update check"), ("GitHub, fest", "GitHub, fixed")],
            [("Apple-Push", "Apple push"), ("fest", "fixed")],
        ],
        "zahlen": [
            ("{notaus.INTERNET_TOOLS|anzahl}", ("Werkzeuge, die selbst ins Internet gehen", "tools that go to the internet by themselves"), "notaus.INTERNET_TOOLS"),
            ("{netguard.MAX_BYTES|mb}", ("größte Antwort über den Wächter", "largest answer through the guard"), "netguard.MAX_BYTES"),
        ],
        "einstellen": [
            ("Einstellungen → Sicherheit, Notaus: Stufe {notaus.STAGE.internet} hält alles Internet der Werkzeuge an.",
             "Settings → Security, kill switch: stage {notaus.STAGE.internet} stops all internet of the tools."),
        ],
        "sehen": [
            ("Zustand → Live: jeder Weg ins Internet in Bernstein, gesperrte mit Grund.",
             "Status → Live: every way to the internet in amber, blocked ones with the reason."),
        ],
        "code": [
            ("notaus.INTERNET_TOOLS", ("Werkzeuge, die selbst ins Internet gehen", "tools that go to the internet by themselves")),
            ("notaus.locked_tools", ("was der Notaus sperrt", "what the kill switch locks")),
            ("netguard.DIRECT_OK", ("feste Wege mit Grund", "fixed ways with a reason")),
            ("netguard.client", ("der Weg über den Wächter", "the way through the guard")),
            ("netguard.allowed", ("erlaubte Adresse je Stufe", "allowed address per level")),
        ],
        "tests": ["test_waechter_umgehung", "test_notaus"],
        "heute": [("guard_ok", ("verbunden", "connected")), ("guard_bad", ("gesperrt", "blocked"))],
    },
    "teilen": {
        "stand": "84addc44c5",
        "bezug": {
            "teilen.CODE_SECS": ["s2"], "teilen.schluessel": ["s3"], "teilen.regeln": ["s4"], "tlstor.server_context": ["s5"],
            "tlstor.allowed": ["s5"], "steuer.call": ["s6"], "tarswart.check": ["s7"], "tarswart.COMMANDS": ["s7"],
            "steuer.weg": ["s8"], "steuer.GONE": ["s8"], "tarswart.WINDOW": ["s7"],
            "rechner.messen": ["s9"], "rechnerblick.warnungen": ["s9"], "rechnerblick.TEMP_WARN": ["s9"],
            "rechnerblick.PLATTE_MIN_PCT": ["s9"], "rechnerblick.RAM_MIN_GIB": ["s9"],
            "rechner.dienste_cpu": ["s9"], "rechenteile.messen": ["s9"], "rechnerblick.spitze": ["s9"],
            "rechnerblick.LEERLAUF_PCT": ["s9"],
            "schirm.schirm_zustand": ["s10"], "schirm.abgleich": ["s10"], "schirm.an_jetzt": ["s10"],
            "steuerzentrale.schrift": ["s10"], "schirm.SIEHT_S": ["s10"],
        },
        "kurz": ("Spark teilen stellt das Panel auf einen eigenen Rechner, zum Beispiel einen Raspberry Pi 5; die Modelle "
                 "bleiben auf dem DGX. Zwischen beiden geht alles durch das TLS-Tor des DGX, und feste Handgriffe wie "
                 "Dienste starten, Modelle wechseln oder messen und „Lange Gespräche“ einstellen erledigt dort der Wärter. Ohne Spark teilen läuft alles auf dem "
                 "DGX, und dieser Kasten tut nichts.",
                 "The Spark split puts the panel on its own computer, for example a Raspberry Pi 5; the models stay on "
                 "the DGX. Everything between the two goes through the DGX's TLS-Tor, and fixed handles like starting "
                 "services, switching or measuring models and setting \"Long conversations\" are done there by the Wärter. Without the split everything runs on the "
                 "DGX and this box does nothing."),
        "warum": ("Sprache, Text und Bilder gehen dann durch das Heimnetz. Niemand im Netz soll mitlesen, sich als DGX "
                  "ausgeben oder dem DGX Befehle geben können.",
                  "Speech, text and pictures then cross the home network. No one in the network should read along, pose "
                  "as the DGX or give the DGX commands."),
        "ablauf": [
            S("s1", "start", ("Installation geteilt", "Shared install"),
              ("install.sh --mode api --teilen", "install.sh --mode api --teilen"),
              ("Der DGX bekommt ein eigenes Zertifikat, das TLS-Tor, den Wärter und die Firewall. Die Dienste hören dann "
               "nur noch auf 127.0.0.1.",
               "The DGX gets its own certificate, the TLS-Tor, the Wärter and the firewall. The services then listen on "
               "127.0.0.1 only.")),
            S("s2", "schritt", ("Kopplungscode", "Pairing code"),
              ("{teilen.CODE_LEN} Zeichen, {teilen.CODE_SECS} s, einmal", "{teilen.CODE_LEN} characters, {teilen.CODE_SECS} s, once"),
              ("Der DGX zeigt einen Code und wartet auf Port {teilen.KOPPEL_PORT}, nur solange der Code gilt; nach "
               "{teilen.CODE_TRIES} falschen Versuchen ist er weg.",
               "The DGX shows a code and waits on port {teilen.KOPPEL_PORT}, only while the code lives; after "
               "{teilen.CODE_TRIES} wrong tries it is gone.")),
            S("s3", "frage", ("Beweis passt zum Zertifikat?", "Proof fits the certificate?"),
              ("scrypt(Code, Fingerabdruck)", "scrypt(code, fingerprint)"),
              ("Der Panel-Rechner beweist den Code mit einem Schlüssel aus Code und dem Fingerabdruck des Zertifikats, das "
               "er sieht. Wer sich dazwischenstellt, zeigt ein anderes Zertifikat, und der Beweis passt nicht.",
               "The panel computer proves the code with a key from the code and the fingerprint of the certificate it "
               "sees. Whoever stands in between shows another certificate, and the proof does not fit."),
              ("stop", "nein", ("Nicht gekoppelt", "Not paired"))),
            S("s4", "schritt", ("Zertifikat angeheftet, Firewall zu", "Certificate pinned, firewall shut"),
              ("nur der Panel-Rechner", "only the panel computer"),
              ("Der Panel-Rechner merkt sich genau dieses Zertifikat und bekommt einen eigenen Wärter-Schlüssel. Die "
               "Firewall des DGX (teilen.regeln) lässt die Ports der Tür nur für ihn zu.",
               "The panel computer keeps exactly this certificate and gets its own Wärter key. The DGX's firewall "
               "(teilen.regeln) opens the door's ports for it only.")),
            S("s5", "frage", ("Verbindung zum TLS-Tor erlaubt?", "Connection to the TLS-Tor allowed?"),
              ("TLS 1.3, nur api.tls_from", "TLS 1.3, only api.tls_from"),
              ("Jede Anfrage an Spracherkennung, Sprachausgabe, Sprachmodell, Bilder und Wärter geht durch das Tor. Es "
               "spricht nur TLS 1.3 und lässt nur den Panel-Rechner herein; den Inhalt liest es nie.",
               "Every request to speech recognition, speech output, the language model, pictures and the Wärter goes "
               "through the door. It speaks TLS 1.3 only and lets only the panel computer in; it never reads the "
               "content."),
              ("stop", "nein", ("Abgewiesen", "Refused"))),
            S("s6", "schritt", ("Befehl an den Wärter", "Command to the Wärter"),
              ("unterschrieben, mit Zeit und Nummer", "signed, with time and number"),
              ("steuer.call schickt einen Befehl mit Zeitstempel und einer Nummer, die nur einmal gilt, unterschrieben "
               "mit dem Wärter-Schlüssel.",
               "steuer.call sends a command with a time stamp and a number that counts only once, signed with the Wärter "
               "key.")),
            S("s7", "frage", ("Unterschrift, Zeit, Nummer, Befehl gültig?", "Signature, time, number, command valid?"),
              ("{tarswart.COMMANDS|anzahl} feste Befehle", "{tarswart.COMMANDS|anzahl} fixed commands"),
              ("tarswart.check prüft die Unterschrift, eine Zeit höchstens {tarswart.WINDOW} s daneben, die Nummer nur "
               "einmal und einen Befehl aus der festen Liste. Keine Shell, keine freien Namen.",
               "tarswart.check checks the signature, a time at most {tarswart.WINDOW} s off, the number only once and a "
               "command from the fixed list. No shell, no free names."),
              ("stop", "nein", ("Abgelehnt", "Refused"))),
            S("s9", "schritt", ("Werte beider Rechner", "Values of both computers"),
              ("alle 3 s, nur Zahlen", "every 3 s, numbers only"),
              ("rechner.messen misst CPU, Speicher, Platte, Netz, Temperatur und Strom; der Wärter schickt die Werte des "
               "DGX mit seinem Zustand. rechnerblick.warnungen meldet mit festen Regeln: Panel-Rechner ab "
               "{rechnerblick.TEMP_WARN} °C, gedrosselt oder zu wenig Strom, weniger als {rechnerblick.RAM_MIN_GIB} GiB "
               "frei; auf jedem Rechner weniger als {rechnerblick.PLATTE_MIN_PCT} % Platte frei; der DGX antwortet nicht. "
               "„Wer rechnet gerade“: rechner.dienste_cpu nimmt den Anteil jedes Dienstes an der CPU aus den Zählern von "
               "systemd, rechenteile.messen die Teile des Panels aus seinen Threads und Hilfsprozessen; rechnerblick.spitze "
               "nennt den größten ab {rechnerblick.LEERLAUF_PCT} %, darunter ist Leerlauf. rechnerblick.wer hält die "
               "Liste ruhig: immer {rechnerblick.ZEILEN} Zeilen in fester Reihenfolge, gewählt über 20 Minuten, 0 % statt "
               "weg; beide Karten zeigen dieselben Zeilen auf gleicher Höhe (Spiegel-Karten). Dienste, die nur für einen "
               "Auftrag starten (rechnerblick.ABRUF: Bildverständnis, Werkstatt, Gehäuse), stehen in Ruhe als „bereit“; "
               "was auf dem DGX nicht installiert ist, fehlt.",
               "rechner.messen measures CPU, memory, disk, network, temperature and power; the Wärter sends the DGX's "
               "values with its status. rechnerblick.warnungen warns by fixed rules: the panel computer from "
               "{rechnerblick.TEMP_WARN} °C, throttled or short of power, less than {rechnerblick.RAM_MIN_GIB} GiB free; "
               "on either computer less than {rechnerblick.PLATTE_MIN_PCT} % disk free; the DGX not answering. „Who is "
               "computing now“: rechner.dienste_cpu takes each service's share of the CPU from systemd's counters, "
               "rechenteile.messen the panel's parts from its threads and worker processes; rechnerblick.spitze names "
               "the biggest from {rechnerblick.LEERLAUF_PCT} % on, below that it is idle. rechnerblick.wer keeps the "
               "list still: always {rechnerblick.ZEILEN} lines in a fixed order, chosen over 20 minutes, 0 % instead of "
               "gone; both cards show the same rows at the same height (mirror cards). Services that start only for a "
               "job (rechnerblick.ABRUF: image understanding, Werkstatt, case) rest as „ready“; what is not installed on "
               "the DGX is left out.")),
            S("s10", "schritt", ("Steuerzentrale am Bildschirm", "Control centre on the screen"),
              ("tty1, nur lokal mit Schlüssel", "tty1, local only with a key"),
              ("Ist Funktionen → Steuerzentrale am Bildschirm an, startet schirm.abgleich den Dienst und lässt ihn beim "
               "Booten von selbst starten, ohne Anmeldung. steuerzentrale.py fragt jede Sekunde schirm.schirm_zustand, "
               "nur von 127.0.0.1 und mit dem eigenen Schlüssel, und zeichnet Fluss, beide Rechner, Dienste und Kurven "
               "als Text; nur Art, Ort, Zeit und Zahlen. steuerzentrale.schrift wählt die Schrift nach der Auflösung "
               "für genug Spalten und Zeilen, schirm.an_jetzt schaltet nach den Zeiten dunkel. Aus geschaltet, startet schirm.anmeldung die Anmeldung auf tty1 wieder; ein Neustart der Anzeige hält ein Update nie an.",
               "When Features → Control centre on the screen is on, schirm.abgleich starts the unit and lets it start "
               "at boot by itself, without signing in. steuerzentrale.py asks schirm.schirm_zustand every second, only "
               "from 127.0.0.1 and with its own key, and draws the flow, both computers, services and curves as text; "
               "only kind, place, time and numbers. steuerzentrale.schrift picks the font by the resolution for at "
               "enough columns and rows, schirm.an_jetzt makes it dark by the times. Switched off, schirm.anmeldung starts the sign-in on tty1 again; a restart of the screen never stops an update.")),
            S("s8", "ende", ("Notbetrieb, wenn der DGX fehlt", "Notbetrieb when the DGX is missing"),
              ("nach {steuer.GONE} s ohne Antwort", "after {steuer.GONE} s without an answer"),
              ("Antwortet der DGX nicht mehr, laufen Chats, Erinnerungen und Logs auf dem Panel-Rechner weiter, und "
               "Sprachfragen bekommen einen festen Satz.",
               "When the DGX no longer answers, chats, reminders and logs go on on the panel computer, and speech "
               "questions get a fixed sentence.")),
        ],
        "beispiele": [
            (("Pi koppeln", "Pair a Pi"), ["s1", "s2", "s3", "s4"],
             ("Gekoppelt, Zertifikat angeheftet.", "Paired, certificate pinned.")),
            (("Falscher Rechner dazwischen", "Wrong computer in between"), ["s1", "s2", "s3", "s3!"],
             ("Der Beweis passt nicht, keine Kopplung.", "The proof does not fit, no pairing.")),
            (("Modell wechseln vom Pi", "Switch the model from the Pi"), ["s5", "s6", "s7"],
             ("Der Wärter startet den Wechsel mit seinen eigenen Regeln.", "The Wärter starts the switch by its own rules.")),
            (("Fremdes Gerät fragt das Tor", "A stranger asks the door"), ["s5", "s5!"],
             ("Abgewiesen vor dem Handshake.", "Refused before the handshake.")),
        ],
        "zahlen": [
            ("{teilen.CODE_SECS} s", ("lebt ein Kopplungscode", "a pairing code lives"), "teilen.CODE_SECS"),
            ("{tarswart.WINDOW} s", ("darf die Zeit eines Befehls daneben liegen", "a command's time may be off"), "tarswart.WINDOW"),
            ("{tarswart.COMMANDS|anzahl}", ("feste Befehle des Wärters", "fixed commands of the Wärter"), "tarswart.COMMANDS"),
            ("{steuer.GONE} s", ("ohne Antwort bis zum Notbetrieb", "without an answer until Notbetrieb"), "steuer.GONE"),
            ("{rechnerblick.TEMP_WARN} °C", ("Hinweis, der Panel-Rechner ist warm", "note, the panel computer is warm"), "rechnerblick.TEMP_WARN"),
            ("{rechnerblick.PLATTE_MIN_PCT} %", ("Platte frei, darunter ein Hinweis", "disk free, below it a note"), "rechnerblick.PLATTE_MIN_PCT"),
            ("{rechnerblick.RAM_MIN_GIB} GiB", ("Arbeitsspeicher frei am Panel-Rechner, darunter ein Hinweis", "memory free on the panel computer, below it a note"), "rechnerblick.RAM_MIN_GIB"),
            ("{rechnerblick.LEERLAUF_PCT} %", ("CPU, ab der der größte Dienst als „rechnet gerade“ gilt", "CPU from which the biggest service counts as „computing now“"), "rechnerblick.LEERLAUF_PCT"),
            ("{schirm.SIEHT_S} s", ("ohne Frage der Steuerzentrale, dann gilt der Bildschirm als dunkel", "without a question from the control centre, then the screen counts as dark"), "schirm.SIEHT_S"),
        ],
        "einstellen": [
            ("Auf den Rechnern selbst: sudo speech-spark teilen code, teilen koppeln, umziehen und zurueckholen "
             "(Anleitung „Spark teilen“).",
             "On the computers themselves: sudo speech-spark teilen code, teilen koppeln, umziehen and zurueckholen "
             "(guide „Spark split“)."),
            ("Funktionen → Steuerzentrale am Bildschirm: an und aus, Anzeige an ab und aus ab (Uhr), Schriftgröße.",
             "Features → Control centre on the screen: on and off, screen on from and off from (hour), font size."),
        ],
        "sehen": [
            ("Zustand → Live: Kasten „Modell-Rechner“ mit erreichbar, Dienste, Version und Pause.",
             "Status → Live: box „Model computer“ with reachable, services, version and pause."),
            ("Zustand → Überblick → Rechner: beide Rechner nebeneinander mit Kurven der letzten 20 Minuten und „Wer "
             "rechnet gerade“ (Dienste und Teile des Panels mit ihrem Anteil an der CPU, Streifen der letzten 20 Minuten); "
             "Live zeigt dazu den Kasten „Panel-Rechner“, beide Kästen mit „am meisten …“.",
             "Status → Summary → Computers: both computers side by side with curves of the last 20 minutes and „Who is "
             "computing now“ (services and the panel's parts with their share of the CPU, strip of the last 20 minutes); "
             "Live adds the box „Panel computer“, both boxes with „am meisten …“."),
            ("Der Bildschirm am Panel-Rechner selbst; Zustand → Live zeigt im Kasten „Steuerzentrale“, ob er gerade zeigt.",
             "The screen on the panel computer itself; Status → Live shows in the box „Control centre“ whether it shows right now."),
        ],
        "code": [
            ("teilen.CODE_SECS", ("Lebensdauer des Codes", "life of the code")),
            ("teilen.schluessel", ("Schlüssel aus Code und Fingerabdruck", "key from code and fingerprint")),
            ("teilen.regeln", ("Firewall nur für den Panel-Rechner", "firewall for the panel computer only")),
            ("tlstor.server_context", ("TLS 1.3 mit eigenem Zertifikat", "TLS 1.3 with its own certificate")),
            ("tlstor.allowed", ("nur der Panel-Rechner", "only the panel computer")),
            ("steuer.call", ("unterschriebener Befehl", "signed command")),
            ("tarswart.check", ("Unterschrift, Zeit, Nummer, Befehl", "signature, time, number, command")),
            ("tarswart.COMMANDS", ("die festen Befehle", "the fixed commands")),
            ("steuer.weg", ("Notbetrieb erkennen", "spot Notbetrieb")),
            ("rechner.messen", ("Werte eines Rechners", "values of one computer")),
            ("rechnerblick.warnungen", ("Hinweise nach festen Regeln", "notes by fixed rules")),
            ("rechner.dienste_cpu", ("CPU je Dienst aus systemd", "CPU per service from systemd")),
            ("rechenteile.messen", ("CPU je Teil des Panels", "CPU per part of the panel")),
            ("rechnerblick.spitze", ("wer am meisten rechnet", "who computes most")),
            ("schirm.schirm_zustand", ("nur lokal und mit Schlüssel", "local only and with a key")),
            ("schirm.abgleich", ("Dienst folgt dem Schalter", "unit follows the switch")),
            ("schirm.an_jetzt", ("dunkel nach den Zeiten", "dark by the times")),
            ("steuerzentrale.schrift", ("Schrift nach Auflösung", "font by resolution")),
        ],
        "tests": ["test_teilen", "test_umziehen", "test_rechner", "test_steuerzentrale"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Werkstatt
    "werkstatt": {
        "stand": "5bb801c557",
        "bezug": {
            "werkstattseite.auftrag_geben": ["s1"], "werkstattseite.nacht_art": ["s1"], "werkstattseite.NACHT_FENSTER_H": ["s1"],
            "werkstatt.pruefen": ["s2"], "werkstatt.TEXT_MAX": ["s2"],
            "werkstatt.wunsch_nehmen": ["s3"], "werkstatt.WUNSCH_S": ["s3"], "werkstatt.sandbox": ["s4"],
            "werkstatt.kopie": ["s5"], "werkstatt.git_umgebung": ["s5"],
            "werkstatt.rechte": ["s7"], "werkstatt.testlauf": ["s8"],
            "werkstatt.TEILE": ["s8"], "werkstatt.namen_testen": ["s8"], "werkstattseite.nachtest_namen": ["s1"],
            "werkstatt.NAMEN_MAX": ["s2"], "werkstatt.pruefe_ergebnis": ["s9"], "werkstatt.AUFTRAEGE_MAX": ["s9"],
            "werkstatt.PATCH_MAX": ["s9"],
        },
        "kurz": ("Die Werkstatt lässt einen Admin auf dem Modell-Rechner den vollen Testlauf laufen und mit OpenCode den Code "
                 "messen, ein Problem untersuchen oder eine Reparatur vorschlagen. Alles läuft in einer abgeschotteten Kopie "
                 "des Codes; heraus kommen nur Zahlen, eine Antwort und ein Patch zum Ansehen. Eingespielt wird nie etwas.",
                 "The workshop lets an admin run the full test run on the model computer and, with OpenCode, measure the code, "
                 "look into a problem or propose a repair. Everything runs in a sealed-off copy of the code; only numbers, an "
                 "answer and a patch to look at come out. Nothing is ever installed."),
        "warum": ("Code, den ein Modell schreibt oder startet, darf nie an die Daten, die Schlüssel oder ins Internet kommen und "
                  "nie selbst etwas ändern. Deshalb entscheidet das Panel mit festen Regeln, und die Sandbox kann nichts außer "
                  "ihrer eigenen Kopie.",
                  "Code a model writes or starts must never reach the data, the keys or the internet, and never change "
                  "anything by itself. So the panel decides by fixed rules, and the sandbox can do nothing but its own copy."),
        "ablauf": [
            S("s1", "start", ("Auftrag oder Nachtregel", "Order or night rule"),
              ("Zustand → Werkstatt, nur Admin", "Status → Workshop, admin only"),
              ("Ein Admin tippt auf der Seite Zustand → Werkstatt „Alles testen“, „Problem untersuchen“, „Reparatur "
               "versuchen“ oder „Sprachmodell messen“ an (werkstattseite.auftrag_geben; die drei mit Sprachmodell brauchen "
               "den Code der zweiten Stufe). „Nur die roten noch mal testen“ nennt nur das Ergebnis; die Namen nimmt "
               "werkstattseite.nachtest_namen aus dem gespeicherten Ergebnis, nie von der Seite. Ist „Jede Nacht testen“ an, startet "
               "werkstattseite.nacht_art in den ersten {werkstattseite.NACHT_FENSTER_H} Stunden nach der eingestellten "
               "Stunde einen Testlauf und nach einem Modellwechsel eine Code-Messung. Die Kachel „Angriffe prüfen“ "
               "(eigener Schalter Angriffsprobe) bleibt im Panel: angriffsprobe.lauf fragt das Sprachmodell je Fall des "
               "Angriffs-Selbsttests einmal und zählt nur, ob es dem versteckten Befehl gefolgt wäre; kein Werkzeug läuft, "
               "gespeichert werden nur Zahlen.",
               "On the page Status → Workshop an admin taps \"Test everything\", \"Look into a problem\", \"Try a repair\" or "
               "\"Measure the language model\" (werkstattseite.auftrag_geben; the three with the language model need the "
               "second-step code). \"Test only the red ones again\" names only the result; werkstattseite.nachtest_namen takes "
               "the names from the kept result, never from the page. With \"Test every night\" on, werkstattseite.nacht_art starts "
               "a test run in the first {werkstattseite.NACHT_FENSTER_H} hours after the set hour, and a code measurement "
               "after a model switch. The tile \"Probe attacks\" (its own switch Angriffsprobe) stays in the panel: "
               "angriffsprobe.lauf asks the language model once per case of the attack self-test and only counts whether it "
               "would have followed the hidden order; no tool runs, only numbers are kept.")),
            S("s2", "frage", ("Feste Regeln erfüllt?", "Fixed rules met?"),
              ("{werkstatt.ARTEN|anzahl} Arten, Text bis {werkstatt.TEXT_MAX} Zeichen", "{werkstatt.ARTEN|anzahl} kinds, text up to {werkstatt.TEXT_MAX} characters"),
              ("werkstatt.pruefen nimmt nur eine bekannte Art, nichts läuft schon, OpenCode und das eigene Sprachmodell sind "
               "da, wo die Art sie braucht. Der Text des Admins wird gesäubert und eingezäunt: er beschreibt nur das Problem. "
               "„Rote Tests noch mal“ nimmt nur Testnamen, jeden einmal, höchstens {werkstatt.NAMEN_MAX}.",
               "werkstatt.pruefen takes only a known kind, nothing runs yet, OpenCode and the own language model are there "
               "where the kind needs them. The admin's text is cleaned and fenced: it only describes the problem. "
               "\"Red tests again\" takes only test names, each once, at most {werkstatt.NAMEN_MAX}."),
              ("stop", "nein", ("Abgelehnt mit festem Grund", "Refused with a fixed reason"))),
            S("s3", "schritt", ("Wunsch an root", "Wish to root"),
              ("einmal, höchstens {werkstatt.WUNSCH_S} s alt", "once, at most {werkstatt.WUNSCH_S} s old"),
              ("Das Panel schreibt einen Wunsch und darf per sudo nur die feste Einheit speech-spark-werkstatt starten. "
               "werkstatt.wunsch_nehmen liest ihn als root genau einmal und prüft alles noch einmal.",
               "The panel writes a wish and may start only the fixed unit speech-spark-werkstatt through sudo. "
               "werkstatt.wunsch_nehmen reads it as root exactly once and checks everything again.")),
            S("s4", "schritt", ("Sandbox", "Sandbox"),
              ("eigener Nutzer, nur das LLM-Tor", "own user, only the LLM-Tor"),
              ("werkstatt.sandbox startet den Auftrag mit systemd-run als Nutzer spark-werkstatt: nur sein eigener Ordner "
               "ist beschreibbar, Daten, Einstellungen und Schlüssel des Spark sind unsichtbar, Netz nur zu diesem Rechner und "
               "dort per nftables nur zum LLM-Tor (prüft den Schlüssel) und zu den freien Ports der eigenen Tests, nie zu einer "
               "Engine oder zum Panel; ohne diese Sperre startet kein Auftrag. Speicher- und Zeitgrenze je Art (werkstatt.GRENZE_S).",
               "werkstatt.sandbox starts the order with systemd-run as the user spark-werkstatt: only its own folder is "
               "writable, the Spark's data, settings and keys are invisible, network only to this computer and there, by "
               "nftables, only to the LLM-Tor (it checks the key) and the free ports of its own tests, never an engine or the "
               "panel; without this firewall no order starts. A memory and time limit per kind (werkstatt.GRENZE_S).")),
            S("s5", "frage", ("Kopie des Codes gemacht?", "Copy of the code made?"),
              ("git clone von /opt/speech-spark/src", "git clone of /opt/speech-spark/src"),
              ("werkstatt.kopie klont den Klon des Installers, nie von GitHub. Weil er root gehört, nennt werkstatt.git_umgebung "
               "genau diesen Ordner in einer eigenen git-Datei der Sandbox als sicher.",
               "werkstatt.kopie clones the installer's clone, never from GitHub. Because root owns it, werkstatt.git_umgebung "
               "names exactly this folder as safe in the sandbox's own git file."),
              ("stop", "nein", ("Code-Kopie fehlt", "Code copy missing"))),
            S("s6", "frage", ("Nur Tests?", "Only tests?"),
              ("ohne OpenCode und Sprachmodell", "without OpenCode and language model"),
              ("Alles testen und „Rote Tests noch mal“ brauchen weder OpenCode noch das Sprachmodell; sie gehen gleich zu "
               "den Tests.",
               "Test everything and \"Red tests again\" need neither OpenCode nor the language model; they go straight to "
               "the tests."),
              ("ok", "ja", "s8")),
            S("s7", "schritt", ("OpenCode mit festen Rechten", "OpenCode with fixed rights"),
              ("Version {werkstatt.OPENCODE_VERSION}, Prüfsumme fest", "version {werkstatt.OPENCODE_VERSION}, checksum pinned"),
              ("werkstatt.rechte: Diagnose liest nur, Reparatur darf Dateien der Kopie ändern und die Selbsttests starten; "
               "kein Web, kein git push, jeder andere Befehl abgelehnt. Das Sprachmodell fragt OpenCode über das LLM-Tor "
               "ganz hinten in der Reihe, damit Gespräche vorgehen.",
               "werkstatt.rechte: diagnosis only reads, repair may change files of the copy and start the self-tests; no "
               "web, no git push, every other command refused. OpenCode asks the language model through the LLM-Tor at the "
               "very back of the line, so conversations go first.")),
            S("s8", "schritt", ("Selbsttests", "Self-tests"),
              ("in {werkstatt.TEILE} Teilen, zweimal rot ist rot", "in {werkstatt.TEILE} parts, red twice is red"),
              ("werkstatt.testlauf lässt die Selbsttests der Kopie laufen wie GitHub; wer beim zweiten Versuch grün wird, "
               "zählt als wackelig. Übersprungene Tests (kein Browser in der Kopie) zählen als nicht gelaufen, nie als "
               "grün. werkstatt.namen_testen lässt bei „Rote Tests noch mal“ jeden genannten Test einzeln in einem eigenen "
               "Prozess laufen: jetzt grün, weiter rot oder nicht gelaufen.",
               "werkstatt.testlauf runs the copy's self-tests like GitHub; whatever turns green on the second try counts as "
               "wobbly. Skipped tests (no browser in the copy) count as not run, never as green. For \"Red tests again\" "
               "werkstatt.namen_testen runs each named test alone in its own process: green now, still red or not run.")),
            S("s9", "schritt", ("Ergebnis als Daten", "Result as data"),
              ("die letzten {werkstatt.AUFTRAEGE_MAX}", "the last {werkstatt.AUFTRAEGE_MAX}"),
              ("werkstatt.pruefe_ergebnis nimmt nur bekannte Felder, Zahlen im Rahmen und Wörter aus festen Listen; ein Patch "
               "über {werkstatt.PATCH_MAX} Zeichen wird gekürzt. Die Seite zeigt alles nur als Text, dazu mit festen Sätzen, "
               "was das Ergebnis heißt und was als Nächstes geht.",
               "werkstatt.pruefe_ergebnis takes only known fields, numbers in range and words from fixed lists; a patch over "
               "{werkstatt.PATCH_MAX} characters is cut. The page shows everything as text only, with fixed sentences on what "
               "the result means and what can come next.")),
            S("s10", "ende", ("Der Admin entscheidet", "The admin decides"),
              ("nichts wird eingespielt", "nothing is installed"),
              ("Den Patch gibt der Admin einem Claude-Thread oder einem Menschen; die Werkstatt spielt nie etwas ein und "
               "pusht nie.",
               "The admin hands the patch to a Claude thread or a person; the workshop never installs or pushes anything.")),
        ],
        "beispiele": [
            (("Testlauf in der Nacht", "Test run at night"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s8", "s9"],
             ("Grün, rot und wackelig stehen unter Zustand → Werkstatt.", "Green, red and wobbly show under Status → Workshop.")),
            (("Rote Tests noch mal", "Red tests again"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s8", "s9"],
             ("Jeder rote Test einzeln: jetzt grün oder weiter rot.", "Each red test alone: green now or still red.")),
            (("Reparatur vorschlagen", "Propose a repair"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10"],
             ("Ein Patch mit Testergebnis zum Ansehen.", "A patch with its test result to look at.")),
            (("Kein eigenes Sprachmodell", "No own language model"), ["s1", "s2", "s2!"],
             ("Abgelehnt, bevor etwas startet.", "Refused before anything starts.")),
        ],
        "zahlen": [
            ("{werkstatt.WUNSCH_S} s", ("darf ein Wunsch alt sein", "a wish may be old"), "werkstatt.WUNSCH_S"),
            ("{werkstatt.TEXT_MAX}", ("Zeichen höchstens im Auftrag", "characters at most in an order"), "werkstatt.TEXT_MAX"),
            ("{werkstatt.TEILE}", ("Teile des Testlaufs gleichzeitig", "parts of the test run at once"), "werkstatt.TEILE"),
            ("{werkstatt.NAMEN_MAX}", ("Testnamen höchstens je Ergebnis und „noch mal“", "test names at most per result and \"again\""), "werkstatt.NAMEN_MAX"),
            ("{werkstatt.AUFTRAEGE_MAX}", ("Ergebnisse bleiben", "results are kept"), "werkstatt.AUFTRAEGE_MAX"),
            ("{werkstatt.PATCH_MAX}", ("Zeichen eines Patches, mehr wird gekürzt", "characters of a patch, more is cut"), "werkstatt.PATCH_MAX"),
            ("{werkstattseite.NACHT_FENSTER_H} h", ("nach der Stunde darf die Nacht starten", "after the hour the night may start"), "werkstattseite.NACHT_FENSTER_H"),
        ],
        "einstellen": [
            ("Auf dem Modell-Rechner einmal sudo ./install.sh --werkstatt (OpenCode mit fester Version und Prüfsumme).",
             "On the model computer once sudo ./install.sh --werkstatt (OpenCode with a pinned version and checksum)."),
            ("Funktionen → Werkstatt: an und aus, „Jede Nacht testen“ mit der Startstunde.",
             "Features → Workshop: on and off, \"Test every night\" with the start hour."),
            ("Zustand → Werkstatt: die vier Aufträge starten, Ergebnisse ansehen, rote Tests noch mal, für Claude kopieren, löschen.",
             "Status → Workshop: start the four orders, look at results, red tests again, copy for Claude, delete."),
        ],
        "sehen": [
            ("Zustand → Werkstatt: links der Verlauf, rechts ein Ergebnis mit großen Zahlen, was es heißt (etwa „Was heißt "
             "rot?“), den roten Tests nach Bereich, Antwort oder Patch und den nächsten Schritten.",
             "Status → Workshop: the history on the left, one result on the right with big numbers, what it means (such as "
             "\"What does red mean?\"), the red tests by area, the answer or patch and the next steps."),
            ("Zustand → Live, Monitoring und die Steuerzentrale: Teil „Werkstatt“ mit Art und Status, nie Inhalte.",
             "Status → Live, Monitoring and the control centre: part \"Workshop\" with kind and status, never contents."),
        ],
        "code": [
            ("werkstattseite.auftrag_geben", ("Auftrag vom Panel", "order from the panel")),
            ("werkstattseite.nacht_art", ("feste Nachtregel", "fixed night rule")),
            ("werkstatt.pruefen", ("feste Regeln eines Auftrags", "fixed rules of an order")),
            ("werkstatt.wunsch_nehmen", ("root nimmt den Wunsch einmal", "root takes the wish once")),
            ("werkstatt.sandbox", ("Grenzen der Sandbox", "limits of the sandbox")),
            ("werkstatt.kopie", ("Kopie aus dem Klon des Installers", "copy from the installer's clone")),
            ("werkstatt.git_umgebung", ("nur dieser Klon gilt als sicher", "only this clone counts as safe")),
            ("werkstatt.rechte", ("Rechte von OpenCode", "OpenCode's rights")),
            ("werkstatt.testlauf", ("Selbsttests in Teilen", "self-tests in parts")),
            ("werkstatt.namen_testen", ("rote Tests einzeln noch mal", "red tests alone again")),
            ("werkstattseite.nachtest_namen", ("Namen nur aus dem Ergebnis", "names only from the result")),
            ("werkstatt.pruefe_ergebnis", ("Ergebnis als Daten", "result as data")),
        ],
        "tests": ["test_werkstatt"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Post, Kalender, Kontakte
    "post": {
        "stand": "7b48661066",
        "bezug": {
            "kalenderserver.login": ["s2", "s10"], "kontaktserver._write": ["s10"], "kontaktserver.MAX_CARDS": ["s10"],
            "mail.MAX_ACCOUNTS": ["s3"], "mail.lookup": ["s1", "s5", "s7"], "calendars.view": ["s1"],
            "netguard.IMAP4_SSL": ["s4"], "mail.TIMEOUT": ["s4"], "kalenderspiegel.objects": ["s4"],
            "mailvorrat.keep_heads": ["s6"], "mailvorrat.HEADS": ["s6"], "mailvorrat.TEXTS": ["s6"], "vorrat.seal": ["s6"],
            "frisch.stand": ["s7"], "senden.preview": ["s9"], "senden.send": ["s9"], "senden.MAX_DAY": ["s9"],
            "contacts.save": ["s9"], "senden.later": ["s9"], "einordnen.start": ["s9"], "mailcode.arrived": ["s8"],
        },
        "kurz": ("Die Seiten E-Mail, Kalender und Kontakte und der Assistent lesen dieselben Daten: Postfächer per IMAP, "
                 "Kalender und Adressbücher per CalDAV und CardDAV beim Anbieter, dazu die Spark-Kalender und das Adressbuch "
                 "„Auf dem Spark“. Was zuletzt kam, liegt versiegelt im Profil, damit Seite und Antwort sofort da sind; jede "
                 "Antwort aus dem Vorrat nennt ihren Stand. Kalender- und Kontakte-Apps kommen durch eine eigene Tür.",
                 "The pages E-mail, Calendar and Contacts and the assistant read the same data: mailboxes by IMAP, "
                 "calendars and address books by CalDAV and CardDAV at the provider, plus the Spark calendars and the "
                 "address book \"On the Spark\". What came last lies sealed in the profile, so page and answer are there at "
                 "once; every answer from the supply names its time. Calendar and contacts apps come through a door of "
                 "their own."),
        "warum": ("Mails, Termine und Kontakte sind die privatesten Daten eines Profils und kommen von fremden Leuten. "
                  "Deshalb sind sie immer Daten, nie Befehle, liegen nur versiegelt auf der Platte, und alles, was nach "
                  "außen geht (senden, ändern, löschen), braucht einen eigenen Schalter und den Tipp des Menschen.",
                  "Mail, appointments and contacts are a profile's most private data and come from other people. So they "
                  "are always data, never commands, lie on the disk only sealed, and everything that goes out (send, "
                  "change, delete) needs a switch of its own and the person's tap."),
        "ablauf": [
            S("s1", "start", ("Seite, Frage oder App", "Page, question or app"),
              ("E-Mail, Kalender, Kontakte, Assistent", "E-mail, Calendar, Contacts, assistant"),
              ("Das Profil öffnet eine eigene Seite (calendars.view für den Kalender, mail.lookup für die Mails) oder fragt "
               "den Assistenten, der dieselben Helfer nimmt. Oder eine Kalender- oder Kontakte-App auf dem Handy meldet sich.",
               "The profile opens a page of its own (calendars.view for the calendar, mail.lookup for mail) or asks the "
               "assistant, which takes the same helpers. Or a calendar or contacts app on the phone signs in.")),
            S("s2", "frage", ("Eine Kalender- oder Kontakte-App?", "A calendar or contacts app?"),
              ("/caldav/ und /carddav/", "/caldav/ and /carddav/"),
              ("Apps kommen nicht durch die Anmeldung des Panels, sondern durch kalenderserver.login: Profil-Kennung und "
               "App-Passwort.",
               "Apps do not come through the panel's login but through kalenderserver.login: profile id and app password."),
              ("ok", "ja", "s10")),
            S("s3", "frage", ("Freigegeben und eingerichtet?", "Released and set up?"),
              ("Admin-Schalter, höchstens {mail.MAX_ACCOUNTS} Postfächer", "admin switch, at most {mail.MAX_ACCOUNTS} mailboxes"),
              ("Jede Seite braucht ihren Admin-Schalter, das Profil darf nicht gesperrt sein, Gäste nie. Ohne Postfach oder "
               "Kalender zeigt die Seite einen Hinweis mit Weg zu den Einstellungen.",
               "Every page needs its admin switch, the profile must not be blocked, guests never. Without a mailbox or "
               "calendar the page shows a hint with the way to its settings."),
              ("stop", "nein", ("Hinweis mit Weg", "Hint with a way"))),
            S("s4", "schritt", ("Abruf beim Anbieter", "Fetch from the provider"),
              ("über den Wächter, {mail.TIMEOUT} s je Postfach", "through the guard, {mail.TIMEOUT} s per mailbox"),
              ("Mails per IMAP über netguard.IMAP4_SSL, das die Adresse prüft; Kalender über eine verschlüsselte Kopie je "
               "Kalender, die nur Änderungen holt (kalenderspiegel.objects). Was kommt, ist Text fremder Leute: das Modell "
               "bekommt es eingezäunt als Daten.",
               "Mail by IMAP through netguard.IMAP4_SSL, which checks the address; calendars through an encrypted copy per "
               "calendar that fetches only changes (kalenderspiegel.objects). What comes is other people's text: the model "
               "gets it fenced as data.")),
            S("s5", "frage", ("Rechtzeitig zurück?", "Back in time?"),
              ("sonst der Vorrat", "else the supply"),
              ("Der Assistent wartet nur kurz (mail.lookup). Ist der Anbieter langsam oder weg, antwortet er aus der letzten "
               "Liste oder dem Vorrat, nie mit einer von vor Tagen.",
               "The assistant waits only briefly (mail.lookup). If the provider is slow or away, it answers from the last "
               "listing or the supply, never with one from days ago."),
              ("ok", "nein", "s7")),
            S("s6", "schritt", ("Vorrat versiegelt", "Supply sealed"),
              ("{mailvorrat.HEADS} Kopfzeilen je Postfach, {mailvorrat.TEXTS} Texte", "{mailvorrat.HEADS} headers per mailbox, {mailvorrat.TEXTS} texts"),
              ("mailvorrat.keep_heads behält die neuesten Kopfzeilen, dazu die zuletzt gelesenen Texte; vorrat.seal "
               "versiegelt sie mit dem Schlüssel des Spark im Ordner des Profils.",
               "mailvorrat.keep_heads keeps the newest headers, plus the texts read last; vorrat.seal seals them with the "
               "Spark's key in the profile's folder.")),
            S("s7", "schritt", ("Antwort mit Stand", "Answer with its time"),
              ("der Stand nennt den Tag", "the time names the day"),
              ("Kommt etwas nicht frisch vom Anbieter, sagt frisch.stand mit festem Satz, von wann es ist („Stand gestern "
               "18:00“). Die Seiten zeigen sofort, was da ist, und laden im Hintergrund nach.",
               "When something is not fresh from the provider, frisch.stand says with a fixed sentence when it is from "
               "(\"as of yesterday 18:00\"). The pages show at once what is there and load the rest behind.")),
            S("s8", "frage", ("Etwas ändern?", "Change something?"),
              ("senden, ordnen, Kontakt ändern", "send, order, change a contact"),
              ("Lesen ist alles, was ohne weitere Schalter geht. Ein Bestätigungscode aus einer neuen Mail wird mit eigenem "
               "Schalter nur eine Mitteilung aufs genutzte Gerät (mailcode.arrived), nie über Telegram, nie im Log.",
               "Reading is all that works without further switches. A confirmation code from a new mail becomes, with a "
               "switch of its own, only a note on the device in use (mailcode.arrived), never by Telegram, never in a log."),
              ("ok", "nein", "s11")),
            S("s9", "schritt", ("Ändern mit Prüfung", "Change with a check"),
              ("eigener Schalter, Tipp des Menschen", "switch of its own, the person's tap"),
              ("Eine Mail geht erst nach dem Vorschau-Blatt und dem Tipp auf Senden raus (senden.preview, senden.send, "
               "höchstens {senden.MAX_DAY} am Tag). „Später senden“ legt sie bis zur Zeit versiegelt ab (senden.later); "
               "brach ein Senden ab, geht sie nie ein zweites Mal. „Alle Mails hier einordnen“ (einordnen.start) schlägt erst vor "
               "und verschiebt nach festen Regeln erst nach dem Tipp, mit Rückgängig. contacts.save schreibt eine Karte mit If-Match zurück: hat sie sich "
               "inzwischen geändert, wird nichts überschrieben.",
               "A mail goes out only after the preview sheet and the tap on Send (senden.preview, senden.send, at most "
               "{senden.MAX_DAY} a day). \"Send later\" keeps it sealed until its time (senden.later); if a sending broke "
               "off, it never goes a second time. \"Sort every mail here\" (einordnen.start) proposes first and moves by fixed "
               "rules only after the tap, with Undo. contacts.save writes a card back with If-Match: if it changed meanwhile, nothing is "
               "overwritten."),
              ("ok", ("fertig", "done"), "s11")),
            S("s10", "schritt", ("Tür für Apps", "Door for apps"),
              ("nur die eigenen Kalender und Kontakte", "only the own calendars and contacts"),
              ("kalenderserver.login weist fremde Webseiten ab, sperrt falsche Passwörter wie eine PIN, hält Mein Notaus "
               "und den Schalter ein und zählt die Lastgrenze. Danach sieht die App nur die Spark-Kalender und das Adressbuch "
               "„Auf dem Spark“ des Profils; kontaktserver._write nimmt je Karte eine vCard, höchstens "
               "{kontaktserver.MAX_CARDS}, und schreibt nur mit „Kontakte ändern“.",
               "kalenderserver.login refuses other sites' web pages, locks wrong passwords like a PIN, keeps My emergency "
               "stop and the switch and counts the rate limit. Then the app sees only the profile's Spark calendars and the "
               "address book \"On the Spark\"; kontaktserver._write takes one vCard per card, at most "
               "{kontaktserver.MAX_CARDS}, and writes only with \"Edit contacts\".")),
            S("s11", "ende", ("Nur eigene Daten", "Own data only"),
              ("users/ID/, versiegelt", "users/ID/, sealed"),
              ("Kein Profil sieht die Post, Termine oder Kontakte eines anderen, außer einem Kalender, den der Besitzer "
               "teilt.",
               "No profile sees another one's mail, appointments or contacts, except a calendar its owner shares.")),
        ],
        "beispiele": [
            (("Wie viele ungelesene Mails?", "How many unread mails?"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!"],
             ("Antwort aus dem Postfach, frisch.", "Answer from the mailbox, fresh.")),
            (("Postfach antwortet nicht", "Mailbox does not answer"), ["s1", "s2", "s3", "s4", "s5", "s5!", "s7", "s8", "s8!"],
             ("Antwort aus dem Vorrat mit Stand.", "Answer from the supply with its time.")),
            (("Mail senden", "Send a mail"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s9!"],
             ("Erst nach dem Tipp auf Senden.", "Only after the tap on Send.")),
            (("Kontakte-App des iPhone", "The iPhone's Contacts app"), ["s1", "s2", "s2!", "s10", "s11"],
             ("Nur das Adressbuch „Auf dem Spark“.", "Only the address book \"On the Spark\".")),
        ],
        "zahlen": [
            ("{mail.MAX_ACCOUNTS}", ("Postfächer höchstens je Profil", "mailboxes at most per profile"), "mail.MAX_ACCOUNTS"),
            ("{mail.TIMEOUT} s", ("wartet ein Postfach höchstens", "a mailbox is waited for at most"), "mail.TIMEOUT"),
            ("{mailvorrat.HEADS}", ("Kopfzeilen je Postfach im Vorrat", "headers per mailbox in the supply"), "mailvorrat.HEADS"),
            ("{mailvorrat.TEXTS}", ("Mailtexte je Profil im Vorrat", "mail texts per profile in the supply"), "mailvorrat.TEXTS"),
            ("{senden.MAX_DAY}", ("Mails höchstens am Tag", "mails at most a day"), "senden.MAX_DAY"),
            ("{kontaktserver.MAX_CARDS}", ("Karten im Adressbuch „Auf dem Spark“", "cards in the address book \"On the Spark\""),
             "kontaktserver.MAX_CARDS"),
        ],
        "einstellen": [
            ("Funktionen → Post und Kontakte: E-Mail lesen, Mails ordnen und senden, Kalender, Kontakte, Kontakte ändern, "
             "Kalender-Server und Kontakte für Kontakte-Apps.",
             "Features → Mail and contacts: reading e-mail, order and send mail, calendar, contacts, edit contacts, calendar "
             "server and contacts for contacts apps."),
            ("Postfächer, Kalender und Adressbücher richtet jedes Profil auf seiner Seite unter Einstellungen ein.",
             "Each profile sets up mailboxes, calendars and address books on its page under settings."),
        ],
        "sehen": [
            ("Die Seiten E-Mail, Kalender und Kontakte im Menü, auf dem iPhone unter Assistent.",
             "The pages E-mail, Calendar and Contacts in the menu, on the iPhone under Assistant."),
            ("Zustand → Live: Abrufe, Vorrat und Türen nur mit Art, Anzahl und Status, nie Inhalte.",
             "Status → Live: fetches, supply and doors only with kind, count and status, never contents."),
        ],
        "code": [
            ("mail.lookup", ("Mails mit Stand", "mail with its time")),
            ("calendars.view", ("Termine für die Seite", "appointments for the page")),
            ("netguard.IMAP4_SSL", ("IMAP nur zu geprüften Adressen", "IMAP only to checked addresses")),
            ("kalenderspiegel.objects", ("Kalender-Kopie holt Änderungen", "calendar copy fetches changes")),
            ("mailvorrat.keep_heads", ("Vorrat der Kopfzeilen", "supply of headers")),
            ("vorrat.seal", ("versiegelt auf der Platte", "sealed on the disk")),
            ("frisch.stand", ("Stand mit Tag", "time with its day")),
            ("senden.preview", ("Vorschau-Blatt", "preview sheet")),
            ("senden.send", ("senden nach dem Tipp", "send after the tap")),
            ("senden.later", ("später senden, versiegelt", "send later, sealed")),
            ("einordnen.start", ("einen Ordner einordnen, erst Vorschlag", "sort a folder, a proposal first")),
            ("mailcode.arrived", ("Bestätigungscode als Mitteilung", "confirmation code as a note")),
            ("contacts.save", ("Karte zurück mit If-Match", "card back with If-Match")),
            ("kalenderserver.login", ("Tür für Kalender- und Kontakte-Apps", "door for calendar and contacts apps")),
            ("kontaktserver._write", ("Karte einer Kontakte-App", "card from a contacts app")),
        ],
        "tests": ["test_mailvorrat", "test_vorrat", "test_mails_senden", "test_kalenderserver", "test_kontaktserver",
                  "test_kontakte_seite", "test_kalenderspiegel", "test_mailcode", "test_einordnen"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Browser und Handy
    # ------------------------------------------------------------------ Fernzugang (Dominik 2026-10-29 „in Technik → Überblick fehlt die Fernwartung“)
    "fernzugang": {
        "stand": "cd2eda00d7",
        "bezug": {
            "fernzugang.entsperrt_bis": ["s2"], "fernzugang.admin_pair": ["s3"], "fernzugang.link_file": ["s3"], "fernzugang.admin_confirm": ["s3"], "fernzugang.CODE_S": ["s3"], "fernzugang.TICKET_S": ["s4"], "fernzugang.terminal_ws": ["s4"], "fernzugang.hostkey_wrong": ["s5"], "fernzugang.HALTEN_S": ["s6"], "ferndateien.listing": ["s6"], "fernbild.GUACD": ["s6"], "fernbild.FPS": ["s6"], "spontanhilfe.admin_new": ["s7"], "spontanhilfe.NUMMER_S": ["s7"], "fernzugang.notaus_close": ["s8"], "fernzugang.MAX_ANKER": ["s3"], "fernnotiz.fuer_modell": ["s6"], "fernnotiz.FASSUNGEN": ["s6"], "fernordner.view": ["s6"], "fernordner.MAX_ORDNER": ["s6"], "ferngross.upload_piece": ["s6"], "ferngross.TEIL": ["s6"],
        },
        "kurz": ("Der Fernzugang öffnet Shell, Dateien und Bildschirm eines eigenen Servers im Browser, ohne offenen Port "
                 "dort: der Anker auf dem Server verbindet sich selbst zum Panel, das Panel spricht SSH durch diese "
                 "Leitung. Dazu die Spontanhilfe: eine Person teilt ihren Bildschirm mit einer Nummer. Nur für Admins, "
                 "nie für Gäste, kein Werkzeug des Sprachmodells.",
                 "Remote access opens the shell, files and screen of an own server in the browser, without an open port "
                 "there: the anchor on the server connects to the panel by itself, the panel speaks SSH through that "
                 "line. Plus spontaneous help: a person shares their screen with a number. Admins only, never guests, "
                 "no tool of the language model."),
        "warum": ("Eine Shell auf einem Server ist das Mächtigste, was das Panel öffnen kann. Deshalb eine eigene Schranke "
                  "vor der Seite (entsperren mit Code oder Passkey), ein Einmal-Ticket je Fenster, ein beim Koppeln "
                  "angehefteter Host-Schlüssel und Logs nur mit festen Wörtern: was auf dem Server getippt wird und was "
                  "er zeigt, speichert das Panel nie.",
                  "A shell on a server is the most powerful thing the panel can open. So a barrier of its own in front "
                  "of the page (unlock with a code or passkey), a one-time ticket per window, a host key pinned at "
                  "pairing and logs with fixed words only: what is typed on the server and what it shows is never "
                  "stored by the panel."),
        "ablauf": [
            S("s1", "start", ("Admin öffnet den Fernzugang", "Admin opens remote access"),
              ("fernzugang.admin_on", "fernzugang.admin_on"),
              ("Funktionen → Fernzugang zu Servern ist standardmäßig aus (fernzugang.admin_on) und nur für Admins mit "
               "zweitem Schritt; Gäste und das Sprachmodell erreichen ihn nie.",
               "Features → Remote access to servers is off by default (fernzugang.admin_on) and only for admins with "
               "the second step; guests and the language model never reach it.")),
            S("s2", "frage", ("Seite entsperrt?", "Page unlocked?"),
              ("{fernzugang.ENTSPERRT_MIN.0} bis {fernzugang.ENTSPERRT_MIN.1} Minuten", "{fernzugang.ENTSPERRT_MIN.0} to {fernzugang.ENTSPERRT_MIN.1} minutes"),
              ("Ein Code oder Passkey entsperrt die Seite für {fernzugang.ENTSPERRT_MIN.0} bis {fernzugang.ENTSPERRT_MIN.1} "
               "Minuten, nur für diese Anmeldung (in der eigenen iPhone-App für deren Schlüssel, fernzugang._tor) und vom "
               "selben Ort (fernzugang.entsperrt_bis); Sperren, Abmelden und Notaus sperren sofort, ein Neustart auch.",
               "A code or passkey unlocks the page for {fernzugang.ENTSPERRT_MIN.0} to {fernzugang.ENTSPERRT_MIN.1} "
               "minutes, only for this login (in the own iPhone app for its key, fernzugang._tor) and from the same place "
               "(fernzugang.entsperrt_bis); locking, logging out and the kill switch lock at once, a restart too."),
              ("stop", "nein", ("Gesperrt, nichts zu sehen", "Locked, nothing to see"))),
            S("s3", "schritt", ("Koppeln", "Pairing"),
              ("Einmal-Code {fernzugang.CODE_S|min} min", "one-time code {fernzugang.CODE_S|min} min"),
              ("„Koppeln“ fragt den Code jedes Mal neu (fernzugang.admin_pair) und zeigt eine Zeile für den Server mit "
               "einem Einmal-Code, {fernzugang.CODE_S|min} Minuten gültig, dazu einen Einmal-Link mit QR-Code, der auf dem "
               "neuen System nur diese Zeile zeigt, nie den Code (fernzugang.link_check). Windows: der Link gibt einmal die "
               "Datei spark-anker-einrichten.cmd (fernzugang.link_file) mit Einmal-Schlüssel statt Code; das System wartet dann, "
               "bis der Admin es mit Code oder Passkey bestätigt (fernzugang.admin_confirm). Höchstens {fernzugang.MAX_ANKER} Systeme; "
               "jedes bekommt einen eigenen SSH-Schlüssel des Panels, sein Host-Schlüssel wird angeheftet.",
               "„Pair“ asks for the code every time (fernzugang.admin_pair) and shows one line for the server with a "
               "one-time code, valid {fernzugang.CODE_S|min} minutes, plus a one-time link with a QR code that shows only "
               "this line on the new system, never the code (fernzugang.link_check). Windows: the link gives the file "
               "spark-anker-einrichten.cmd once (fernzugang.link_file) with a one-time key instead of the code; the system then "
               "waits until the admin confirms it with a code or passkey (fernzugang.admin_confirm). At most {fernzugang.MAX_ANKER} systems; each gets "
               "an SSH key of the panel of its own, its host key is pinned.")),
            S("s4", "schritt", ("Ticket für das Fenster", "Ticket for the window"),
              ("{fernzugang.TICKET_S} s, einmal", "{fernzugang.TICKET_S} s, once"),
              ("„Shell“ gibt ein Einmal-Ticket (fernzugang.admin_session), das {fernzugang.TICKET_S} Sekunden lang genau "
               "ein Web-Terminal öffnet (fernzugang.terminal_ws); höchstens {fernzugang.SITZUNGEN.1} Sitzungen zugleich.",
               "„Shell“ hands out a one-time ticket (fernzugang.admin_session) that opens exactly one web terminal for "
               "{fernzugang.TICKET_S} seconds (fernzugang.terminal_ws); at most {fernzugang.SITZUNGEN.1} sessions at once.")),
            S("s5", "frage", ("Anderer Host-Schlüssel?", "Another host key?"),
              ("fernzugang.hostkey_wrong", "fernzugang.hostkey_wrong"),
              ("Zeigt der Server einen anderen Host-Schlüssel als beim Koppeln, gibt es keine Verbindung "
               "(fernzugang.hostkey_wrong); nach einer Neuinstallation entfernen und neu koppeln.",
               "If the server shows another host key than at pairing, there is no connection "
               "(fernzugang.hostkey_wrong); after a reinstall remove and pair again."),
              ("stop", "ja", ("Keine Verbindung", "No connection"))),
            S("s6", "schritt", ("Shell, Dateien, Bildschirm", "Shell, files, screen"),
              ("SSH · SFTP · guacd", "SSH · SFTP · guacd"),
              ("SSH läuft durch den Kanal des Ankers; reißt das Fenster ab, wartet die Shell {fernzugang.HALTEN_S} Sekunden. "
               "Ein Lebenszeichen alle {fernzugang.MESS_S} Sekunden misst Laufzeit und Rate; die Ausgabe "
               "wartet in höchstens {fernzugang.STAU} Stücken auf das Fenster, dann bremst SSH den Server (Gegendruck). "
               "Dateien über SFTP in derselben Verbindung (ferndateien.listing), Laden mit Einmal-Link für "
               "{ferndateien.LINK_S} Sekunden; große Dateien in Teilen von {ferngross.TEIL|mb} MB mit SHA-256 je Stück "
               "(ferngross.upload_piece). Der Bildschirm geht über guacd nur auf 127.0.0.1 (fernbild.GUACD), höchstens "
               "{fernbild.FPS} Bilder je Sekunde. Der Assistent (fernzugang.admin_help) fragt nur das eigene Modell und "
               "schlägt vor, getippt wird nie von selbst. Notizen je System liegen versiegelt, "
               "{fernnotiz.FASSUNGEN} Fassungen bleiben; das Modell liest sie nur mit Haken (fernnotiz.fuer_modell). Ordner ordnen nur die Liste "
               "(fernordner.view), höchstens {fernordner.MAX_ORDNER}; Rechte bleiben je System.",
               "SSH runs through the anchor's channel; if the window drops, the shell waits {fernzugang.HALTEN_S} seconds. "
               "A heartbeat every {fernzugang.MESS_S} seconds measures round trip and rate; output waits "
               "for the window in at most {fernzugang.STAU} pieces, then SSH slows the server (backpressure). "
               "Files through SFTP in the same connection (ferndateien.listing), downloads with a one-time link for "
               "{ferndateien.LINK_S} seconds; big files in pieces of {ferngross.TEIL|mb} MB with a SHA-256 per piece "
               "(ferngross.upload_piece). The screen goes through guacd on 127.0.0.1 only (fernbild.GUACD), at most "
               "{fernbild.FPS} pictures a second. The assistant (fernzugang.admin_help) asks only the own model and "
               "suggests, nothing is typed by itself. Notes per system are stored sealed, "
               "{fernnotiz.FASSUNGEN} versions stay; the model reads them only when ticked (fernnotiz.fuer_modell). Folders only order the list "
               "(fernordner.view), at most {fernordner.MAX_ORDNER}; rights stay per system.")),
            S("s7", "schritt", ("Spontanhilfe", "Spontaneous help"),
              ("Nummer {spontanhilfe.NUMMER_S|min} min", "number {spontanhilfe.NUMMER_S|min} min"),
              ("Eine Hilfe (spontanhilfe.admin_new) gibt eine Nummer für {spontanhilfe.NUMMER_S|min} Minuten, nach "
               "{spontanhilfe.FEHL} falschen ist sie tot. Der Bildschirm geht per WebRTC direkt zwischen den zwei Browsern, "
               "von unterwegs über TURN auf tars; das Panel vermittelt nur.",
               "A help (spontanhilfe.admin_new) gives a number for {spontanhilfe.NUMMER_S|min} minutes, after "
               "{spontanhilfe.FEHL} wrong ones it is dead. The screen goes by WebRTC directly between the two browsers, "
               "on the way through TURN on tars; the panel only connects them.")),
            S("s8", "ende", ("Logs und Verlauf", "Logs and history"),
              ("fernzugang.log", "fernzugang.log"),
              ("Logs nur mit festen Wörtern und Zahlen (fernzugang.log), der Verlauf nur Zeit, System, Admin, Art und "
               "Dauer (fernzugang.verlauf_add). Der Notaus schließt jede Leitung (fernzugang.notaus_close).",
               "Logs with fixed words and numbers only (fernzugang.log), the history only time, system, admin, kind and "
               "duration (fernzugang.verlauf_add). The kill switch closes every line (fernzugang.notaus_close).")),
        ],
        "beispiele": [
            (("Shell öffnen", "Open a shell"), ["s1", "s2", "s4", "s5", "s6", "s8"],
             ("Entsperrt, Ticket, Host-Schlüssel passt: die Shell läuft.", "Unlocked, ticket, host key fits: the shell runs.")),
            (("Server neu installiert", "Server reinstalled"), ["s1", "s2", "s4", "s5", "s5!"],
             ("Anderer Host-Schlüssel: keine Verbindung.", "Another host key: no connection.")),
            (("Seite gesperrt", "Page locked"), ["s1", "s2", "s2!"],
             ("Erst mit Code oder Passkey entsperren.", "Unlock with a code or passkey first.")),
        ],
        "zahlen": [
            ("{fernzugang.CODE_S|min} min", ("gilt ein Einmal-Code zum Koppeln", "a one-time pairing code is valid"), "fernzugang.CODE_S"),
            ("{fernzugang.TICKET_S} s", ("gilt ein Ticket für ein Fenster", "a ticket for one window is valid"), "fernzugang.TICKET_S"),
            ("{fernzugang.HALTEN_S} s", ("wartet eine abgerissene Shell", "a dropped shell waits"), "fernzugang.HALTEN_S"),
            ("{fernzugang.MAX_ANKER}", ("gekoppelte Systeme höchstens", "paired systems at most"), "fernzugang.MAX_ANKER"),
            ("{fernbild.FPS}", ("Bilder je Sekunde höchstens", "pictures a second at most"), "fernbild.FPS"),
            ("{fernnotiz.FASSUNGEN}", ("Fassungen einer Notiz bleiben", "versions of a note stay"), "fernnotiz.FASSUNGEN"),
            ("{fernordner.MAX_ORDNER}", ("Ordner höchstens", "folders at most"), "fernordner.MAX_ORDNER"),
            ("{ferngross.TEIL|mb} MB", ("ist ein Stück einer großen Datei", "is one piece of a big file"), "ferngross.TEIL"),
            ("{spontanhilfe.NUMMER_S|min} min", ("gilt eine Nummer der Spontanhilfe", "a number of spontaneous help is valid"), "spontanhilfe.NUMMER_S"),
        ],
        "einstellen": [
            ("Funktionen → Fernzugang zu Servern: einschalten, Systeme koppeln, Bildschirm, Spontanhilfe, Notizen und Ordner.",
             "Features → Remote access to servers: switch on, pair systems, screen, spontaneous help, notes and folders."),
        ],
        "sehen": [
            ("Zustand → Live: offene Sitzungen und Anker nach Art und Anzahl, nie ein Inhalt.",
             "Status → Live: open sessions and anchors by kind and count, never a content."),
        ],
        "code": [
            ("fernzugang.entsperrt_bis", ("wie lange die Seite entsperrt ist", "how long the page is unlocked")),
            ("fernzugang.admin_pair", ("Koppeln mit Einmal-Code", "pairing with a one-time code")),
            ("fernzugang.link_file", ("Windows: die Datei spark-anker-einrichten.cmd mit Einmal-Schlüssel, einmal", "Windows: the file spark-anker-einrichten.cmd with a one-time key, once")),
            ("fernzugang.admin_confirm", ("neues System erst nach Bestätigung mit Code oder Passkey", "a new system only after confirming with a code or passkey")),
            ("fernzugang.terminal_ws", ("das Web-Terminal mit Ticket", "the web terminal with a ticket")),
            ("fernzugang.hostkey_wrong", ("angehefteter Host-Schlüssel", "pinned host key")),
            ("ferndateien.listing", ("Dateien über SFTP", "files through SFTP")),
            ("fernbild.GUACD", ("guacd nur auf 127.0.0.1", "guacd on 127.0.0.1 only")),
            ("spontanhilfe.admin_new", ("eine neue Spontanhilfe", "a new spontaneous help")),
            ("fernzugang.notaus_close", ("Notaus schließt jede Leitung", "kill switch closes every line")),
            ("fernnotiz.fuer_modell", ("die Notiz nur mit Haken für das Modell", "the note for the model only when ticked")),
            ("fernordner.view", ("Ordner: nur die Reihenfolge der Liste", "folders: only the order of the list")),
            ("ferngross.upload_piece", ("große Datei: ein Stück nur ganz und mit passender SHA-256", "big file: a piece only whole and with a matching SHA-256")),
        ],
        "tests": ["test_fernzugang", "test_fernbild", "test_spontanhilfe", "test_ferngross"],
        "heute": [],
    },
    "fernserver": {
        "stand": "63b29291b1",
        "bezug": {
            "fernzugang.command": ["s1"], "fernzugang.anker_pair": ["s2"], "fernzugang.by_key": ["s3"], "fernzugang.anker_ws": ["s3"], "fernzugang.PULS_S": ["s4"], "fernzugang.MAX_MSG": ["s4"], "fernzugang.anker_removed": ["s6"], "fernzugang.ABBAU_TAGE": ["s6"], "fernanker.admin_update": ["s7"], "fernanker.stand": ["s7"],
        },
        "kurz": ("Ein Fern-Server ist ein eigener Rechner (Linux oder Mac) im Heimnetz oder im Internet, auf dem der Anker "
                 "läuft: ein kleines Programm, das sich selbst zum Panel verbindet und dort den Weg zu seinem SSH öffnet.",
                 "A remote server is an own computer (Linux or Mac) at home or on the internet that runs the anchor: a "
                 "small program that connects to the panel by itself and opens the way to its SSH there."),
        "warum": ("So braucht der Server keinen offenen Port und keine Weiterleitung im Router: die Leitung geht von ihm "
                  "hinaus, wie ein Browser von unterwegs. Das Panel kennt jeden Anker an seinem eigenen Schlüssel.",
                  "So the server needs no open port and no forwarding in the router: the line goes out from it, like a "
                  "browser on the way. The panel knows every anchor by its own key."),
        "ablauf": [
            S("s1", "start", ("Eine Zeile auf dem Server", "One line on the server"),
              ("curl … | sudo python3 -", "curl … | sudo python3 -"),
              ("Die Seite zeigt eine Zeile aus der Adresse, auf der der Browser ist (fernzugang.command); sie lädt den "
               "Anker vom eigenen Panel und richtet ihn als eigenen Systemdienst ein.",
               "The page shows one line from the address the browser is on (fernzugang.command); it loads the anchor "
               "from the own panel and sets it up as a system service of its own.")),
            S("s2", "schritt", ("Koppeln mit dem Einmal-Code", "Pairing with the one-time code"),
              ("fernzugang.anker_pair", "fernzugang.anker_pair"),
              ("Der Anker meldet sich einmal mit dem Code (fernzugang.anker_pair) und bekommt seinen Geräteschlüssel; das "
               "Panel behält davon nur den SHA-256, dazu Host-Schlüssel und Name. Im Heimnetz nennt das Panel dazu seine "
               "eigene Adresse dort mit der SHA-256 seines Zertifikats; der Anker versucht sie zuerst.",
               "The anchor signs in once with the code (fernzugang.anker_pair) and gets its device key; the panel keeps "
               "only its SHA-256, plus host key and name. At home the panel also names its own address there with the "
               "SHA-256 of its certificate; the anchor tries it first.")),
            S("s3", "frage", ("Schlüssel bekannt?", "Key known?"),
              ("fernzugang.by_key", "fernzugang.by_key"),
              ("Jede Verbindung des Ankers (fernzugang.anker_ws) zeigt den Geräteschlüssel; unbekannt oder entfernt heißt "
               "abgewiesen (fernzugang.by_key), mit Rate-Limit.",
               "Every connection of the anchor (fernzugang.anker_ws) shows the device key; unknown or removed means "
               "refused (fernzugang.by_key), with a rate limit."),
              ("stop", "nein", ("Abgewiesen", "Refused"))),
            S("s4", "schritt", ("Leitung nach draußen", "Line going out"),
              ("WSS · {fernzugang.PULS_S} s", "WSS · {fernzugang.PULS_S} s"),
              ("Der Anker hält eine WebSocket-Leitung mit TLS zum Panel, direkt im Heimnetz oder über den Reverse-Proxy, "
               "mit Lebenszeichen alle {fernzugang.PULS_S} Sekunden; jede Nachricht höchstens {fernzugang.MAX_MSG} Bytes.",
               "The anchor keeps a WebSocket line with TLS to the panel, directly at home or through the reverse proxy, "
               "with a heartbeat every {fernzugang.PULS_S} seconds; every message at most {fernzugang.MAX_MSG} bytes.")),
            S("s5", "schritt", ("Kanal zum eigenen SSH", "Channel to its own SSH"),
              ("127.0.0.1:22 · {fernzugang.USER}", "127.0.0.1:22 · {fernzugang.USER}"),
              ("Nur auf Bitte des Panels öffnet der Anker einen Kanal zu seinem sshd auf 127.0.0.1 (binnen "
               "{fernzugang.OPEN_S} Sekunden); angemeldet wird als Benutzer {fernzugang.USER} nur mit dem Schlüssel des "
               "Panels, sudo nur, wenn der Admin es dort einträgt.",
               "Only when the panel asks does the anchor open a channel to its sshd on 127.0.0.1 (within "
               "{fernzugang.OPEN_S} seconds); the login is user {fernzugang.USER} with the panel's key only, sudo only "
               "when the admin adds it there.")),
            S("s7", "schritt", ("Aktualisieren", "Update"),
              ("signiert, nie zurück", "signed, never back"),
              ("„Aktualisieren“ schickt einem Anker ab {fernanker.UPDATE_MIN.0}.{fernanker.UPDATE_MIN.1}.{fernanker.UPDATE_MIN.2}, "
               "der online und ohne offene Sitzung ist, die neue Version über seinen Kanal (fernanker.admin_update), nie "
               "einen Schritt zurück. Der Anker lädt das Programm nur vom eigenen Panel und prüft SHA-256 und die "
               "Unterschrift mit dem beim Koppeln angehefteten Schlüssel (fernanker.stand); erreicht die neue Version das "
               "Panel nicht, geht er zur alten zurück. Ältere Anker bekommen eine Zeile zum Einfügen.",
               "„Update“ sends an anchor from {fernanker.UPDATE_MIN.0}.{fernanker.UPDATE_MIN.1}.{fernanker.UPDATE_MIN.2} "
               "that is online and has no open session the new version over its channel (fernanker.admin_update), never a "
               "step back. The anchor loads the program from its own panel only and checks SHA-256 and the signature with "
               "the key pinned at pairing (fernanker.stand); if the new version does not reach the panel, it goes back to "
               "the old one. Older anchors get a line to paste.")),
            S("s6", "ende", ("Entfernen", "Remove"),
              ("fernzugang.anker_removed", "fernzugang.anker_removed"),
              ("„Entfernen“ lässt den Anker sich selbst abbauen und meldet es (fernzugang.anker_removed); ein entfernter, "
               "der nie wiederkommt, ist nach {fernzugang.ABBAU_TAGE} Tagen vergessen.",
               "„Remove“ lets the anchor take itself down and report it (fernzugang.anker_removed); a removed one that "
               "never comes back is forgotten after {fernzugang.ABBAU_TAGE} days.")),
        ],
        "beispiele": [
            (("Server einrichten", "Set up a server"), ["s1", "s2", "s3", "s4"],
             ("Gekoppelt und online.", "Paired and online.")),
            (("Alter Schlüssel nach dem Entfernen", "Old key after removal"), ["s3", "s3!"],
             ("Abgewiesen.", "Refused.")),
        ],
        "zahlen": [
            ("{fernzugang.PULS_S} s", ("Lebenszeichen auf der Leitung", "heartbeat on the line"), "fernzugang.PULS_S"),
            ("{fernzugang.MAX_MSG} Bytes", ("eine Nachricht höchstens", "one message at most"), "fernzugang.MAX_MSG"),
            ("{fernzugang.ABBAU_TAGE}", ("Tage, bis ein entfernter vergessen ist", "days until a removed one is forgotten"), "fernzugang.ABBAU_TAGE"),
        ],
        "einstellen": [
            ("Funktionen → Fernzugang zu Servern: Koppeln, Entfernen, Bildschirm einrichten.",
             "Features → Remote access to servers: pair, remove, set up the screen."),
        ],
        "sehen": [
            ("Funktionen → Dienst-Wächter: ein Anker, der zu lange offline ist.",
             "Features → Service watch: an anchor that is offline too long."),
        ],
        "code": [
            ("fernzugang.command", ("die eine Zeile", "the one line")),
            ("fernzugang.anker_pair", ("Koppeln des Ankers", "pairing of the anchor")),
            ("fernzugang.anker_ws", ("die Leitung des Ankers", "the anchor's line")),
            ("fernzugang.by_key", ("Anker am Schlüssel erkennen", "know an anchor by its key")),
            ("fernzugang.anker_removed", ("Abbau gemeldet", "removal reported")),
            ("fernanker.admin_update", ("Aktualisieren über den Kanal", "update over the channel")),
            ("fernanker.stand", ("signierter Stand des Programms", "signed state of the program")),
        ],
        "tests": ["test_fernzugang"],
        "heute": [],
    },
}
