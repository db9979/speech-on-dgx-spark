"""Zustand → Technik, Knoten-Seiten: the pages of preparing, router, answer and tools
(vorbereiten, weiche, antwort, werkzeuge). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "vorbereiten": {
        "stand": "22ef7aeda9",
        "bezug": {
            "klaeren.MAX_BUTTONS": ["s7"], "chat_turn.prepare": ["s1", "s13"], "chat_turn.shared_stranger": ["s3"],
            "chat.left_out": ["s2", "s4"], "notaus.locked_tools": ["s11"], "chat_turn.notaus_note": ["s8", "s11"],
            "chat.offer_memory": ["s10"],
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
               "behält diese Marke. Eine Frage vom Assistenten-Blatt der Android-App kommt nur durch, wenn „Android: Spark "
               "als Assistent“ für das Profil freigegeben ist (sonst 403).",
               "Only text messages of user and assistant are taken, each cut at {chat.MAX_TURN_CHARS} characters. An "
               "answer the browser marked as made from mail or outside text keeps that mark. A question from the Android "
               "app's assistant sheet only passes when „Android: Spark as assistant“ is released for the profile (else 403)."),
              ("stop", ("leer", "empty"), ("Keine Nachricht (400)", "No message (400)"))),
            S("s2", "schritt", ("Verlauf kürzen, Sperre übernehmen", "Trim history, carry the lock"),
              ("chat.trim_history", "chat.trim_history"),
              ("Der Verlauf wird auf sein Budget gekürzt. Steht eine Antwort aus fremdem Text unter den letzten drei "
               "Nachrichten, beginnt dieser Zug gesperrt; ältere werden gar nicht mehr mitgeschickt. Wünscht sich die "
               "Person in eigenen Worten ein Lied, bleibt so eine Antwort bis {musik.BACK} Nachrichten zurück als Daten "
               "dabei (Akkorde, Stil). Eine Bildschirm-Beschreibung kommt nur als fester Hinweis mit und sperrt nichts.",
               "The history is trimmed to its budget. If an answer from outside text is among the last three messages, "
               "this turn starts locked; older ones are not sent at all. When the person asks for a song in their own "
               "words, such an answer up to {musik.BACK} messages back stays along as data (chords, style). A screen "
               "description only comes along as a fixed note and locks nothing.")),
            S("s3", "frage", ("Gast oder fremde Stimme?", "Guest or unknown voice?"),
              ("kein Profil oder Lautsprecher/Telefon erkennt die Stimme nicht",
               "no profile or the speaker/phone does not know the voice"),
              ("Ohne Profil, oder am eigenen Lautsprecher oder Telefon, wenn die Spracherkennung nicht klar die Stimme "
               "des Profils gehört hat (am Telefon: und keine Telefon-PIN getippt wurde), gibt es nur Frage und Antwort: "
               "kein Werkzeug, kein Gedächtnis, kein Verlauf. Wessen Stimme es war, setzt nur das Panel selbst, nie die "
               "Anfrage.",
               "Without a profile, or at an own speaker or phone when speech recognition did not clearly hear the "
               "profile's voice (on the phone: and no phone PIN was typed), there is only question and answer: no tool, "
               "no memory, no history. Whose voice it was only the panel itself sets, never the request."),
              ("info", "ja", ("nur Frage und Antwort", "question and answer only"))),
            S("s4", "schritt", ("Weiche liest die Frage", "The switch reads the question"),
              ("intent.classify_cfg", "intent.classify_cfg"),
              ("Feste Regeln ordnen die eigene letzte Nachricht einer Gruppe zu. Eine neue eigene Bitte, die nicht auf "
               "die Antwort aus fremdem Text zurückzeigt, lässt diese Antwort und ihre Sperre weg. Erkennt keine Regel "
               "die Frage, kann das Modell parallel einmal aus einer festen Liste wählen (wenn der Admin das anhat). "
               "Eine Folgefrage wie „Und morgen?“ übernimmt die Gruppe der eigenen Frage davor (intent.follow_up); "
               "Hinweiswörter geben ihre Gruppen dazu, auch neben der Wahl des Modells. Ein Foto mit Änderungswunsch "
               "(bilder.wants_change) ist die Gruppe Bilder, ohne Wahl des Modells.",
               "Fixed rules put the own latest message into a group. A new own request that does not point back at the "
               "answer from outside text leaves that answer and its lock out. If no rule knows the question, the model "
               "may pick once from a fixed list in parallel (when the admin has that on). A follow-up like „And "
               "tomorrow?“ takes the group of the own question before (intent.follow_up); hint words add their groups, "
               "also beside the model's pick. A photo with a wish to change it (bilder.wants_change) is the group "
               "pictures, without the model's pick.")),
            S("s5", "schritt", ("Systemprompt bauen", "Build the system prompt"),
              ("Admin-Text, Zeit, Länge, Stil, Kanal", "admin text, time, length, style, channel"),
              ("Der Systemprompt des Admins, dazu Länge und Stil des Profils und ein Hinweis je Kanal (Uhr, Siri, "
               "Lautsprecher, Telefon, Telegram, App, Browser). Mit „Schneller Antwortbeginn“ geht, was nur für diesen Zug "
               "gilt, mit der Frage statt in den Systemprompt, damit der Server ihn aus dem Cache liest. Mit „Großes "
               "Gedächtnis kürzen“ stehen bei einem langen Gedächtnis nur die neuesten Fakten fest darin (höchstens "
               "{chat.MEMORY_CORE} Zeichen), dazu bis zu {chat.MEMORY_EXTRA} ältere, die Wörter mit der Frage teilen, "
               "nur für diesen Zug (chat.memory_split). Ist das Wissensbuch an und hat Seiten, kommen bis zu "
               "{wissensbuch.HINT_PAGES} Seitentitel dazu, die am besten zur Frage passen, als fremder Text "
               "(wissensbuch.hint).",
               "The admin's system prompt, plus the profile's length and style and a note per channel (watch, Siri, "
               "speaker, phone, Telegram, app, browser). With „Fast answer start“ what holds for this turn only goes with the "
               "question instead of the system prompt, so the server reads it from its cache. With „Trim a large "
               "memory“ a long memory keeps only the newest facts fixed in it (at most {chat.MEMORY_CORE} characters), "
               "plus up to {chat.MEMORY_EXTRA} older ones that share words with the question, for this turn only "
               "(chat.memory_split). When the knowledge book is on and has pages, up to {wissensbuch.HINT_PAGES} page "
               "titles that fit the question best come along, as outside text (wissensbuch.hint).")),
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
              ("Kalender, Postfach, Listen, Gedächtnis, Anruf", "calendar, mailbox, lists, memory, call"),
              ("Wartet ein Vorschlag aus diesem Gespräch (ein Termin, eine Mail-Änderung, ein Listeneintrag, eine "
               "Korrektur, ein Anruf), entscheidet das Panel über das „Ja“. Ein Ja bestätigt genau eine Sache; jede Antwort "
               "erledigt alle anderen wartenden Vorschläge dieses Gesprächs.",
               "If a proposal of this conversation waits (an appointment, a mail change, a list entry, a correction, a call), "
               "the panel decides on the „yes“. One yes confirms exactly one thing; every answer settles all other "
               "waiting proposals of this conversation.")),
            S("s10", "schritt", ("Werkzeuge nach Rechten", "Tools by rights"),
              ("features.allowed je Gruppe", "features.allowed per group"),
              ("Jede Werkzeuggruppe kommt nur mit Schalter des Admins, Freigabe für das Profil und den eigenen Daten "
               "dazu: Suche, Gedächtnis, Verlauf, Dokumente, Smart Home, Erinnerungen, Kalender, Mail. Telegram, die "
               "iPhone-App und CarPlay können das nur enger machen, nie weiter. Eine fremde erkannte Stimme an diesem "
               "Gerät bekommt nichts Persönliches. Eine Nachricht, die nur fragt („Weißt du, wie mein Bruder heißt?“: "
               "ein Satz mit Fragezeichen, nichts zum Merken), bekommt kein memory_save (chat.offer_memory), damit "
               "kein erfundener Fakt gespeichert wird.",
               "Each tool group comes only with the admin's switch, the release for the profile and its own data: "
               "search, memory, history, documents, smart home, reminders, calendar, mail. Telegram, the iPhone app "
               "and CarPlay can only make it narrower, never wider. Another recognized voice at this device gets "
               "nothing personal. A message that only asks („Do you know my brother's name?“: one sentence with a "
               "question mark, nothing to remember) gets no memory_save (chat.offer_memory), so no made-up fact is "
               "saved.")),
            S("s11", "frage", ("Etwas nimmt Werkzeuge weg?", "Something takes tools away?"),
              ("Notaus · MCP · Bild · Gast", "kill switch · MCP · picture · guest"),
              ("Der Notaus nimmt Werkzeuge ins Internet oder ändernde weg, „Spark fragen“ über MCP behält nur die "
               "Werkzeuge der Verbindung, ein Bild, ein fester Satz oder ein fester Weg des Panels "
               "(Anrufe per Assistent, rufen.py) lässt keines übrig. Für einen Gast wird die "
               "Liste noch einmal geleert, egal was sie gefüllt hat.",
               "The kill switch takes away tools to the internet or that change things, „Ask Spark“ over MCP keeps "
               "only the connection's tools, a picture, a fixed sentence or a fixed panel path "
               "(calls by the assistant, rufen.py) leaves none. For a guest the list is "
               "emptied once more, whatever filled it."),
              ("info", "ja", ("weniger oder keine Werkzeuge", "fewer or no tools"))),
            S("s12", "schritt", ("Weiche grenzt ein", "The switch narrows"),
              ("intent.narrow · nie mehr als die Rechte", "intent.narrow · never more than the rights"),
              ("Mit „Gezielte Werkzeugwahl“ bleibt nur die Gruppe der Frage übrig. Danach entscheidet das Panel, ob "
               "erst lokal gesucht wird, ob es ein eindeutiges Abrufen selbst macht und welches Werkzeug die erste "
               "Runde rufen muss. Mit „Schneller Antwortbeginn“ bekommt eine erkannte Gruppe immer dieselbe Liste in "
               "derselben Reihenfolge, so hält der Server je Gruppe einen Anfang im Cache; nur eine unklare Frage sieht "
               "die volle Liste.",
               "With „Targeted tool choice“ only the question's group stays. Then the panel decides whether to search "
               "locally first, whether it does a clear fetch itself and which tool the first round must call. With „Fast "
               "answer start“ a recognized group always gets the same list in the same order, so the server keeps one "
               "start per group in its cache; only an unclear question sees the full list.")),
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
            ("Personen und Geräte → Gesperrte Funktionen: was ein einzelnes Profil nicht bekommt.", "People and devices → Blocked functions: what a single profile does not get."),
            ("Funktionen → Rückfrage statt Raten: das Panel fragt nach, statt zu raten (Standard aus).",
             "Features → Ask instead of guessing: the panel asks instead of guessing (default off)."),
            ("Funktionen → Weiche: die festen Regeln, die die Werkzeuge eingrenzen.",
             "Features → Switch: the fixed rules that narrow the tools."),
            ("Funktionen → Ablauf und Freigabe zeigen: Werkzeuge unter der Antwort, ein wartender Vorschlag als Karte mit Ja und Nein "
             "(nur eigenes Profil und Gerät, Standard aus).",
             "Features → Show steps and approvals: tools below the answer, a waiting proposal as a card with Yes and No "
             "(own profile and device only, default off)."),
        ],
        "sehen": [
            ("Logs → Anfragen: je Frage Gruppe, Werkzeuge „x von y“, Pflichtwerkzeug und Sperre, ohne Inhalt.",
             "Logs → Requests: per question group, tools „x of y“, required tool and lock, without content."),
            ("Zustand → Logs: Zeilen wie „weiche: Absicht …“, „chat: web search …“, „chat: memory_save not offered …“ "
             "oder „notaus: … Werkzeuge nicht angeboten“.",
             "Status → Logs: lines like „weiche: Absicht …“, „chat: web search …“, „chat: memory_save not offered …“ or "
             "„notaus: … Werkzeuge nicht angeboten“."),
        ],
        "code": [
            ("chat_turn.prepare", ("der ganze Ablauf", "the whole way")),
            ("chat_turn.shared_stranger", ("fremde Stimme am Lautsprecher", "unknown voice at a speaker")),
            ("chat.trim_history", ("Verlauf kürzen", "trim the history")),
            ("chat.left_out", ("Antworten aus fremdem Text weglassen", "leave out answers from outside text")),
            ("chat.offer_memory", ("kein memory_save, wenn die Nachricht nur fragt", "no memory_save when the message only asks")),
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
        "stand": "cf74e4420b",
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
               "regelmäßig wiederkommt oder etwas beobachtet, ist ein Agent; eine Frage zu Sprache oder Natur oder "
               "nach einem Unterschied ist nie ein Gerät; ein Preis oder Streik ist die Websuche, nicht iPhone oder "
               "Bahn; „Ruf mich an“ ist der Rückruf des Spark, nicht das iPhone; „Liste der …“ in einer Datei ist "
               "nicht die eigene Liste. Zuletzt nehmen die „Nicht bei“-Wörter des Admins Gruppen wieder heraus.",
               "When several groups match, fixed rules tidy up: weather, list, message, document and „create "
               "document“ come before smart home when there is no switching command; parcels before mail; „Do I have "
               "new messages?“ is a message, „What is in the news?“ the web search; a job that comes back regularly "
               "or watches something is an agent; a question about language, nature or a difference is never a "
               "device; a price or a strike is the web search, not the iPhone or the train; „Call me“ is the Spark "
               "calling back, not the iPhone; „a list of …“ in a file is not the own list. Last, the "
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
               "Schwelle (Standard {systemone.ROUTE_MIN|prozent}). Die Hinweis-Gruppen bleiben neben der Wahl. In "
               "einer Wartungspause des Sprachmodells wird es nicht gefragt.",
               "If no rule found a group and „Questions no rule recognizes“ is set to the model, the language model "
               "picks one group from the fixed list once (JSON only, only the own message). The question already "
               "runs beside the preparation from its start; the wait is at most {intent.ASK_TIMEOUT} seconds, with "
               "„Fast answer start“ only {intent.CACHED_WAIT|ms} after the preparation. With classification "
               "with probabilities the pick only counts from the threshold (default {systemone.ROUTE_MIN|prozent}). The hint "
               "groups stay beside the pick. During a maintenance pause of the language model it is not asked."),
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
            ("Funktionen → Weiche abstimmen (Standard aus): das Sprachmodell schlägt Wörter je Gruppe vor, das Panel behält "
             "ein Wort nur, wenn kein Testsatz kippt, die Übungshälfte besser und die Prüfhälfte nicht schlechter wird; "
             "gespeichert wird erst mit „Übernehmen“.",
             "Features → Tune the switch (default off): the language model proposes words per group, the panel keeps a "
             "word only when no test sentence flips, the practice half gets better and the check half no worse; it is "
             "saved only with \"Apply\"."),
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
        "stand": "36177d2171",
        "bezug": {
            "chat.MAX_SAVES": ["s11"], "chat.LOOP_SAME": ["s11"], "chat._answer": ["s4", "s5", "s11"], "chat_modell.model_turn": ["s4", "s11"], "chat_ton.speech_out": ["s8"],
            "chat.split_sentences": ["s5"], "chat.said_key": ["s8"], "chat.no_code": ["s8"],
            "chat.loop_count": ["s11"], "answercheck.known": ["s6"], "answercheck.unsupported": ["s6"],
            "answercheck.fresh": ["s6"], "taten.announces": ["s7", "s12"],
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
               "Systemprompt und die angebotenen Werkzeuge vor; _answer übernimmt. Ist das Sprachmodell pausiert "
               "(Wartungspause, Notbetrieb), kommt sofort ein fester Satz; im Notbetrieb mit Parakeet vorher die festen "
               "Befehle ohne Modell (notbetrieb.antwort: Home Assistant, Uhrzeit, Erinnerungen). Mit „Einfaches sofort "
               "beantworten“ bekommen Uhrzeit, Datum, einfache Rechnungen und Einheiten als ganzer kurzer Satz den "
               "festen Satz des Panels, ohne Modell und ohne Sofort-Satz davor (sofort.answer, höchstens "
               "{sofort.MAX_CHARS} Zeichen).",
               "chat() checks the rate limit, sets the mark „speech is running“ (background work waits) and shows the "
               "profile's other devices „answering“. Then chat_turn.prepare works out rights, locks, system prompt and "
               "the offered tools; _answer takes over. When the language model pauses (maintenance pause, emergency "
               "mode), a fixed sentence comes at once; in emergency mode with Parakeet the fixed commands come first, "
               "without a model (notbetrieb.antwort: Home Assistant, time, reminders). With „Answer simple things at "
               "once“ the time, the date, simple arithmetic and units as a whole short sentence get the panel's fixed "
               "sentence, without a model and without an instant sentence before it (sofort.answer, at most "
               "{sofort.MAX_CHARS} characters).")),
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
               "Die fünfte Runde hat keine Liste mehr: das Modell hört, dass es jetzt antworten soll. Geräte ohne "
               "Bildschirm (Lautsprecher, Telefon, Uhr, Siri, Android-Assistent, CarPlay) bekommen höchstens "
               "{chat.SPOKEN_MAX_TOKENS} Tokens; eine längere Antwort endet am letzten ganzen Satz.",
               "Offered is the list without locked tools, tools stopped after errors or used too often. When the "
               "question needs a tool, the model must choose one (tool_choice), with its own temperature. The fifth "
               "round has no list: the model is told to answer now. Devices without a screen (speaker, phone, watch, "
               "Siri, Android assistant, CarPlay) get at most {chat.SPOKEN_MAX_TOKENS} tokens; a longer answer ends at "
               "its last full sentence.")),
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
               "Antwort, nicht aus früheren; ein zitierter Termin-Titel muss im Ergebnis stehen. Mit „Antwort-Prüfung "
               "erweitern“ auch Temperaturen, km und Prozent (gerundet zählt, answercheck.MORE_SLACK) und jeder "
               "zitierte Name in jeder Datenantwort.",
               "For data questions answercheck compares every time, date, score and amount in the sentence with "
               "everything the model was given. After a calendar read only figures from this answer count, not from "
               "earlier ones; a quoted appointment title must be in the result. With „Extended answer check“ also "
               "temperatures, km and percentages (rounded counts, answercheck.MORE_SLACK) and every quoted name in "
               "every data answer."),
              ("info", "ja", ("Satz fällt weg, am Ende ein ehrlicher Satz", "Sentence dropped, an honest sentence at the end"))),
            S("s7", "frage", ("Tat ohne Werkzeug?", "Deed without a tool?"),
              ("Taten prüfen", "check deeds"),
              ("Behauptet ein Satz eine Tat („ist jetzt an“, „habe eingetragen“), muss in dieser Antwort ein Werkzeug "
               "dieser Art geklappt haben (taten.check). Ein Satz, der einen Werkzeugaufruf oder eine Tat nur "
               "ankündigt („Ich rufe das Timer-Werkzeug auf …“), wird nie gesagt; kommt danach kein Werkzeug, sagt "
               "das Panel am Ende seinen festen Satz (taten.announces). Klappt ein Werkzeug der behaupteten Art "
               "später in derselben Antwort („Ich mache das Lied.“ vor musik_machen), fällt der Satz still weg. Gilt, wenn ein änderndes Werkzeug oder gar "
               "keines angeboten war.",
               "When a sentence claims a deed („is on now“, „entered it“), a tool of that kind must have worked in this "
               "answer (taten.check). A sentence that only announces a tool call or a deed („I'm calling the timer "
               "tool …“) is never said; when no tool follows, the panel says its fixed sentence at the end "
               "(taten.announces). When a tool of the claimed kind works later in the same answer („I'm making the "
               "song.“ before musik_machen), the sentence is left out silently. Applies when a changing tool or none at all was offered."),
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
               "gleich, wird es für diese Antwort gestoppt. Hatte keine Regel die Frage erkannt, zählt die Weiche "
               "die Gruppe des ersten Werkzeugs und das feste Hinweiswort (weiche.learn), nie ein Wort der Frage.",
               "Half words before the call are taken back, a finished sentence stays. Every call goes through "
               "chat_tools.run; the result comes back as a tool message. A tool that fails twice the same way is "
               "stopped for this answer. When no rule recognized the question, the switch counts the group of the "
               "first tool and the fixed hint word (weiche.learn), never a word of the question."),
              ("zurueck", ("nächste Runde", "next round"), "s4")),
            S("s12", "schritt", ("Ehrliche Schlusssätze", "Honest closing sentences"),
              ("feste Sätze statt der weggelassenen", "fixed sentences instead of the dropped ones"),
              ("Fiel ein Satz wegen einer Zahl weg, sagt das Panel „Genauere Angaben dazu habe ich nicht.“; fiel eine "
               "Tat weg, einen festen Satz aus taten.sentence. Beide Sätze kommen vom Panel, nie vom Modell. Antwortet das "
               "Sprachmodell nicht, weil es gerade wechselt, neu startet oder gemessen wird, sagt das Panel das mit der "
               "erwarteten Zeit (llmstart.satz, auch in der Wartungspause eines Wechsels).",
               "When a sentence fell out because of a figure, the panel says „I have no more precise details on "
               "that.“; when a deed fell out, a fixed sentence from taten.sentence. Both come from the panel, never "
               "from the model. When the language model does not answer because it is switching, restarting or "
               "being measured, the panel says so with the expected time (llmstart.satz, also during a switch's "
               "maintenance pause).")),
            S("s13", "schritt", ("Nachfragen des Panels", "The panel's own questions"),
              ("Korrektur, Gedächtnis, reMarkable, Vorab holen", "correction, memory, reMarkable, fetch ahead"),
              ("Nur wenn nichts Fremdes gelesen wurde: eine gelernte Korrektur zum Merken anbieten oder ein Fakt aus "
               "dem Gedächtnis nachfragen (nach festen Regeln). Danach legt das Panel die Antwort aufs reMarkable, wenn "
               "gewünscht, und holt bei einer Rückfrage schon vorab. Ist „Das kannst du auch sagen“ an, hängt das Panel "
               "feste Beispielsätze an (saetze.row, am Bildschirm als Zeile vor dem Ende; saetze.spoken, beim Sprechen "
               "höchstens ein Satz am Tag). Das Werkzeug-Log des Profils wird geschrieben.",
               "Only when nothing from outside was read: offer to remember a learned correction or ask about a fact in "
               "memory (by fixed rules). Then the panel puts the answer on the reMarkable when asked and fetches ahead "
               "for a question back. When „You can also say“ is on, the panel adds fixed example sentences (saetze.row, "
               "on a screen as a row before the end; saetze.spoken, while talking at most one sentence a day). The "
               "profile's tool log is written.")),
            S("s14", "ende", ("Strom endet", "Stream ends"),
              ("Anfrage-Verlauf, Fälle, „done“", "request trace, cases, „done“"),
              ("Der Anfrage-Verlauf wird abgeschlossen, Fälle und die Prüfung im Hintergrund laufen erst nach dem "
               "Sprechen. Bricht das Gerät ab (Unterbrechen), stoppen Modell und Sprachausgabe sofort. Stützt sich die "
               "Antwort auf mindestens zwei eigene Dokumente oder Kiwix-Artikel, merkt wissensbuch.keep_offer sie und "
               "das Gerät zeigt „Ins Wissensbuch“; nur der Klick des Besitzers legt sie ab.",
               "The request trace is closed; cases and the background check run only after speaking. When the device "
               "aborts (barge-in), model and speech output stop at once. When the answer rests on at least two own "
               "documents or Kiwix articles, wissensbuch.keep_offer keeps it and the device shows „To the knowledge "
               "book“; only the owner's click files it.")),
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
            ("Unter der Antwort (Funktionen → Ablauf und Freigabe zeigen): jedes Werkzeug mit ✓/⚠ und Zeit, ein wartender "
             "Vorschlag als Karte mit Ja und Nein; nur Namen und Zahlen, nie Ergebnisse.",
             "Below the answer (Features → Show steps and approvals): every tool with ✓/⚠ and time, a waiting proposal as a "
             "card with Yes and No; only names and numbers, never results."),
        ],
        "code": [
            ("chat.chat", ("Rate-Limit, Sprache zuerst, „antwortet gerade“", "rate limit, speech first, „answering“")),
            ("chat._answer", ("führt Modellseite, Sprachausgabe und Ereignisse zu einem Strom zusammen", "joins model side, speech output and events into one stream")),
            ("chat_ton.speech_out", ("Sätze an die Sprachausgabe, Ton als Strom", "sentences to the speech output, sound as a stream")),
            ("chat_modell.model_turn", ("Runden mit dem Modell, Werkzeuge, Prüfungen", "rounds with the model, tools, checks")),
            ("chat.split_sentences", ("schneidet fertige Sätze ab", "cuts finished sentences off")),
            ("chat.said_key", ("erkennt einen schon gesagten Satz", "spots a sentence already said")),
            ("chat.no_code", ("Codeblöcke nur zeigen, nie sprechen", "code blocks only shown, never spoken")),
            ("chat.loop_count", ("zählt Fehlschläge für Fehlerschleife stoppen", "counts failures for stop error loops")),
            ("answercheck.known", ("alle Angaben, die das Modell bekommen hat", "every figure the model was given")),
            ("answercheck.unsupported", ("Angaben im Satz ohne Beleg", "figures in the sentence without proof")),
            ("answercheck.fresh", ("nach dem Kalender nur Angaben dieser Antwort", "after the calendar only this answer's figures")),
            ("taten.check", ("Tat behauptet, aber kein Werkzeug hat es geschafft", "deed claimed, no tool managed it")),
            ("taten.announces", ("Werkzeugaufruf oder Tat nur angekündigt", "tool call or deed only announced")),
            ("taten.sentence", ("der feste ehrliche Satz", "the fixed honest sentence")),
        ],
        "tests": ["test_panel", "test_taten", "test_handlungsregel", "test_fast_start", "test_morgen_termine"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Werkzeuge (chat_tools.run)
    "werkzeuge": {
        "stand": "f710b6ceeb",
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
              ("aus der Runde in chat_modell.model_turn", "from the round in chat_modell.model_turn"),
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
               "ebenfalls (außer bei „Erst lokal suchen“, dann nur mit den eigenen Worten der Frage). Ein Lied, das die "
               "Person selbst wünscht, bleibt nach Text von außen offen (own), nach Mail nicht.",
               "When this answer already read text from outside, nothing may change the home, the memory, "
               "appointments or reminders any more. After a mail web search is closed too, also after own documents "
               "(except with „search locally first“, then only with the question's own words). A song the person asks "
               "for stays open after outside text (own), not after mail."),
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
               "die Marke schon vor dem Lauf. Ab dann sind die Sperren aus Schritt 4 für den Rest der Antwort aktiv. "
               "document_search bringt mit dem Wissensbuch zuerst die passende Seite, dann die Stellen; beides ist "
               "fremder Text.",
               "Tools that bring outside text (web search, documents, calendar, earlier conversations, camera) set the "
               "mark before they run. From then on the locks of step 4 hold for the rest of the answer. With the "
               "knowledge book document_search brings the fitting page first, then the passages; both are outside text.")),
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
               "schließen kann. Zustände aus Home Assistant mit freiem Text (Titel, Listen) zählen auch als fremd. Mit "
               "„Schnellere Websuche“ steht der lange Hinweis einmal je Antwort, vor jedem weiteren Block ein kurzer "
               "mit derselben Regel (chat.OUTSIDE_AGAIN); die Markierungen bleiben immer.",
               "Outside text gets a fixed note in front and stands between markers it cannot close itself. Home "
               "Assistant states with free text (titles, lists) count as outside too. With „Faster web search“ the long "
               "note stands once per answer, before every further block a short one with the same rule "
               "(chat.OUTSIDE_AGAIN); the markers always stay.")),
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
            ("Unter der Antwort (Ablauf und Freigabe zeigen): jedes angebotene Werkzeug mit verständlichem Namen, ✓/⚠ "
             "und Zeit (ablauf.step), nie seine Angaben oder sein Ergebnis.",
             "Below the answer (Show steps and approvals): every offered tool with its readable name, ✓/⚠ and time "
             "(ablauf.step), never its arguments or its result."),
        ],
        "code": [
            ("chat_tools.run", ("die Prüfungen und alle eingebauten Werkzeuge", "the checks and all built-in tools")),
            ("chat_modell.model_turn", ("ruft run_tool, packt Ergebnisse ein, stoppt Schleifen", "calls run_tool, wraps results, stops loops")),
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
}
