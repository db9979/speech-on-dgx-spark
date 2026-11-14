"""Zustand → Technik, Knoten-Seiten: the pages of preparing, router, answer and tools
(vorbereiten, weiche, antwort, werkzeuge). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "vorbereiten": {
        "stand": "6e900ba45d",
        "bezug": {
            "klaeren.MAX_BUTTONS": ["s7"], "chat_turn.prepare": ["s1", "s13"], "chat_turn.STUFEN": ["s1", "s13"], "chat_turn.shared_stranger": ["s3"],
            "chat.left_out": ["s2", "s4"], "notaus.locked_tools": ["s11"], "chat_turn.notaus_note": ["s8", "s11"],
            "chat.offer_memory": ["s10"], "chat.ha_take": ["s7"], "profiles.quelle": ["s7"], "profiles.pending_replaced": ["s7"], "stoppwort.ende": ["s14"], "proactive.answers_note": ["s14"],
            "regeln": ["s10", "s11"], "regel:Gast oder unbekannte Stimme am Lautsprecher": ["s3"],
        },
        "kurz": ("chat_turn.prepare macht aus einer Chat-Anfrage einen fertigen Gesprächszug, bevor das Sprachmodell "
                 "gefragt wird: wer spricht und was diese Person darf, der Systemprompt, Antworten auf Rückfragen und "
                 "Vorschläge, die Sperren nach fremdem Text und die Liste der angebotenen Werkzeuge. Das geschieht in "
                 "sieben festen Stufen (chat_turn.STUFEN: Eingang, Weg, Wer, Rechte und Sperren, wartendes Ja, "
                 "Werkzeuge, Prompt), jede liest nur, was die Stufen davor gesetzt haben.",
                 "chat_turn.prepare turns a chat request into a finished turn before the language model is asked: who "
                 "speaks and what that person may do, the system prompt, answers to questions back and proposals, the "
                 "locks after outside text and the list of offered tools. That happens in seven fixed stages "
                 "(chat_turn.STUFEN: input, way, who, rights and locks, waiting yes, tools, prompt), each reads only what "
                 "the stages before it set."),
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
            S("s14", "frage", ("Nur ein Stoppwort?", "Only a stop word?"),
              ("stoppwort.ende · vor der Weiche", "stoppwort.ende · before the switch"),
              ("Ist die ganze Nachricht ein Stoppwort oder ein Abschied („Stopp“, „Hör auf“, „Danke, das war's“, "
               "„Tschüss“; die eine Liste in stoppwort.py), endet der Zug hier: kein Modell, kein Werkzeug, nichts wird "
               "gespeichert, eine wartende Rückfrage dieses Gesprächs verfällt. Die Antwort ist nur das Ereignis "
               "„ende“; Seite, Apps und Begleiter hören auf zu sprechen und öffnen das Mikrofon nicht wieder, Telegram "
               "und Siri bekommen ein festes Wort. „Stopp die Musik“ bleibt eine Frage. Antwortet die Person auf eine "
               "Meldung des Spark („Nicht jetzt“, proactive.answers_note), bleibt das die Rückmeldung zur Meldung.",
               "If the whole message is a stop word or a goodbye („Stop“, „Be quiet“, „Thanks, that's all“, „Bye“; "
               "the one list in stoppwort.py), the turn ends here: no model, no tool, nothing is stored, a waiting "
               "question back of this conversation lapses. The answer is only the event „ende“; page, apps and "
               "Begleiter stop speaking and do not open the microphone again, Telegram and Siri get a fixed word. "
               "„Stop the music“ stays a question. When the person answers a note of the Spark („Not now“, "
               "proactive.answers_note), that stays the note's feedback."),
              ("stop", "ja", ("„ende“, kein Modell", "„ende“, no model"))),
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
               "Anfrage. Eine Antwortstimme aus der Anfrage oder vom erkannten Sprecher gilt nur, wenn das Profil mit ihr "
               "sprechen darf (profiles.voice_ok: eine gestaltete Stimme nur die eigene oder eine feste).",
               "Without a profile, or at an own speaker or phone when speech recognition did not clearly hear the "
               "profile's voice (on the phone: and no phone PIN was typed), there is only question and answer: no tool, "
               "no memory, no history. Whose voice it was only the panel itself sets, never the request. An answer "
               "voice from the request or of the recognised speaker counts only when the profile may speak with it "
               "(profiles.voice_ok: a designed voice only its own or a fixed one)."),
              ("info", "ja", ("nur Frage und Antwort", "question and answer only"))),
            S("s4", "schritt", ("Weiche liest die Frage", "The switch reads the question"),
              ("intent.classify_cfg", "intent.classify_cfg"),
              ("Feste Regeln ordnen die eigene letzte Nachricht einer Gruppe zu. Eine neue eigene Bitte, die nicht auf "
               "die Antwort aus fremdem Text zurückzeigt, lässt diese Antwort und ihre Sperre weg. Erkennt keine Regel "
               "die Frage, kann das Modell parallel einmal aus einer festen Liste wählen (wenn der Admin das anhat). "
               "Eine Folgefrage wie „Und morgen?“ übernimmt die Gruppe der eigenen Frage davor (intent.follow_up), "
               "solange diese höchstens {intent.FOLLOW_SECONDS} Sekunden zurückliegt (die Zeit gibt prepare hinein, "
               "intent.asked_age); "
               "Hinweiswörter geben ihre Gruppen dazu, auch neben der Wahl des Modells. Ein Foto mit Änderungswunsch "
               "(bilder.wants_change) ist die Gruppe Bilder, ohne Wahl des Modells.",
               "Fixed rules put the own latest message into a group. A new own request that does not point back at the "
               "answer from outside text leaves that answer and its lock out. If no rule knows the question, the model "
               "may pick once from a fixed list in parallel (when the admin has that on). A follow-up like „And "
               "tomorrow?“ takes the group of the own question before (intent.follow_up), as long as that was at most "
               "{intent.FOLLOW_SECONDS} seconds ago (prepare passes the time in, intent.asked_age); hint words add their groups, "
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
               "(wissensbuch.hint). Hat die Person das Gespräch auf eine ihrer Mappen beschränkt (Feld mappe, eine "
               "eigene ID, vom Panel geprüft), kommen deren Einträge nach den festen Stufen aus, kurz und ganz als fremder "
               "Text dazu (mappen.for_turn); der Zug ist dann gesperrt wie nach fremdem Text.",
               "The admin's system prompt, plus the profile's length and style and a note per channel (watch, Siri, "
               "speaker, phone, Telegram, app, browser). With „Fast answer start“ what holds for this turn only goes with the "
               "question instead of the system prompt, so the server reads it from its cache. With „Trim a large "
               "memory“ a long memory keeps only the newest facts fixed in it (at most {chat.MEMORY_CORE} characters), "
               "plus up to {chat.MEMORY_EXTRA} older ones that share words with the question, for this turn only "
               "(chat.memory_split). When the knowledge book is on and has pages, up to {wissensbuch.HINT_PAGES} page "
               "titles that fit the question best come along, as outside text (wissensbuch.hint). When the person limited "
               "the conversation to one of their collections (field mappe, an own id, checked by the panel), its entries "
               "come along by the fixed levels off, short and whole as outside text (mappen.for_turn); the turn is then "
               "locked as after outside text.")),
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
               "Minuten. Ein direkter Smart-Home-Befehl ohne das nötige Codewort wartet {chat.HA_WAIT_S|min} Minuten, "
               "gebunden an Gerät und Gespräch (chat.ha_take): ein Codewort von einem anderen Gerät des Profils führt "
               "ihn nicht aus und löscht ihn nicht. Ein verneinter Satz ist nie ein direkter Befehl. Hat das Panel gefragt, "
               "welcher Weg gemeint ist (Rückfrage zum Weg, klaeren.weg_answer), liest es die Antwort schon vor der "
               "Weiche: die Wahl führt den Satz davor mit dieser Gruppe aus, „Einfach antworten“ ohne ändernde Werkzeuge, "
               "alles andere lässt die Frage verfallen. Alles, was auf eine Antwort wartet (Ja, Codewort, Rückfrage), "
               "gehört zu seiner Quelle: Art des Geräts, Gespräch und Gerät (profiles.quelle; zwei iPhones, zwei "
               "Lautsprecher oder zwei Browser sind zwei Quellen). Ein schlichtes „Ja“ ohne eigenen Vorschlag, während "
               "einer auf einem anderen Gerät wartet oder von dort ersetzt wurde, führt nichts aus; das Modell bekommt "
               "dazu einen festen Satz (chat_turn.YES_ELSEWHERE).",
               "If the panel asked which device is meant, a button, a number or the name counts as the answer, only in "
               "the same conversation, from the own profile and within {klaeren.ASK_SECONDS|min} minutes. „None of "
               "these“ brings the whole list, „No, the other one“ corrects the last choice. The panel carries out the "
               "choice and offers to remember it; a „yes“ to that counts for {klaeren.REMEMBER_SECONDS|min} minutes. "
               "A direct smart home command without the needed code word waits {chat.HA_WAIT_S|min} minutes, bound to "
               "device and conversation (chat.ha_take): a code word from another device of the profile neither runs nor "
               "clears it. A negated sentence is never a direct command. If the panel asked which way is meant (Ask which "
               "way, klaeren.weg_answer), it reads the answer before the switch already: the choice runs the sentence "
               "before with that group, „Just answer“ without changing tools, anything else lets the question lapse. "
               "Everything that waits on an answer (yes, code word, question back) belongs to its source: kind of "
               "device, conversation and device (profiles.quelle; two iPhones, two speakers or two browsers are two "
               "sources). A plain „yes“ without a proposal of its own, while one waits on another device or was replaced "
               "from there, carries out nothing; the model gets a fixed sentence for it (chat_turn.YES_ELSEWHERE)."),
              ("info", "ja", ("Panel führt die Wahl aus", "panel carries out the choice"))),
            S("s8", "frage", ("Notaus oder Mein Notaus?", "Kill switch or my kill switch?"),
              ("ab Stufe {notaus.STAGE.aktion} keine Aktion", "from stage {notaus.STAGE.aktion} no action"),
              ("Ab Notaus-Stufe {notaus.STAGE.aktion} oder mit dem eigenen Notaus des Profils werden alle wartenden "
               "Vorschläge verworfen; kein „Ja“ führt etwas aus. Lesen und Antworten gehen weiter.",
               "From kill switch stage {notaus.STAGE.aktion} or with the profile's own kill switch every waiting "
               "proposal is dropped; no „yes“ carries anything out. Reading and answering go on."),
              ("info", "ja", ("nur lesen, kein Ja", "read only, no yes"))),
            S("s9", "schritt", ("Ja zu einem Vorschlag", "Yes to a proposal"),
              ("Kalender, Postfach, Listen, Gedächtnis, Anruf, reMarkable", "calendar, mailbox, lists, memory, call, reMarkable"),
              ("Wartet ein Vorschlag aus diesem Gespräch (ein Termin, eine Mail-Änderung, ein Listeneintrag, eine "
               "Korrektur, ein Anruf, eine Antwort fürs reMarkable), entscheidet das Panel über das „Ja“. Ein Ja bestätigt genau eine Sache; jede Antwort "
               "erledigt alle anderen wartenden Vorschläge dieses Gesprächs.",
               "If a proposal of this conversation waits (an appointment, a mail change, a list entry, a correction, a call, an answer for the reMarkable), "
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
               "erst lokal gesucht wird (die Quellen-Weiche sagt intern, extern oder beides, nur für das eigene Profil; "
               "„Auch im Internet suchen“ nimmt die gemerkten eigenen Worte der Frage davor und sucht nur damit im Web; "
               "nie bei einem schlichten „Ja“ oder „Nein“ und nie, wenn es in diesem Zug schon "
               "etwas bestätigt ausgeführt hat), ob es ein eindeutiges Abrufen selbst macht und welches Werkzeug die erste "
               "Runde rufen muss. Mit „Schneller Antwortbeginn“ bekommt eine erkannte Gruppe immer dieselbe Liste in "
               "derselben Reihenfolge, so hält der Server je Gruppe einen Anfang im Cache; nur eine unklare Frage sieht "
               "die volle Liste.",
               "With „Targeted tool choice“ only the question's group stays. Then the panel decides whether to search "
               "locally first (the source switch says internal, external or both, only for the own profile; „Also "
               "search the web“ takes the kept own words of the question before and searches only those on the web; never for "
               "a plain „yes“ or „no“ and never when it already carried out something confirmed "
               "in this turn), whether it does a clear fetch itself and which tool the first round must call. With „Fast "
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
             ["s1", "s14", "s2", "s3", "s3!", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s11!", "s13"],
             ("Antwort ohne Werkzeug: Gäste bekommen nur Frage und Antwort.", "Answer without a tool: guests only get question and answer.")),
            (("„Das zweite“ nach einer Rückfrage", "„The second“ after a question back"),
             ["s1", "s14", "s2", "s3", "s4", "s5", "s6", "s7", "s7!", "s8", "s9", "s10", "s11", "s12", "s13"],
             ("Das Panel schaltet das gewählte Gerät; das Modell sagt nur das Ergebnis.",
              "The panel switches the chosen device; the model only says the result.")),
            (("Notaus Stufe 2, Frage nach Terminen", "Kill switch stage 2, asking for appointments"),
             ["s1", "s14", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!", "s9", "s10", "s11", "s11!", "s12", "s13"],
             ("Nur lesende Werkzeuge; Termine eintragen wird nicht angeboten.", "Only reading tools; adding appointments is not offered.")),
            (("„Stopp“ mit Freihändig", "„Stop“ with hands-free"), ["s1", "s14", "s14!"],
             ("Kein Modell, die Seite sagt „Gestoppt.“ und das Mikrofon bleibt zu.",
              "No model, the page says „Stopped.“ and the microphone stays closed.")),
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
             "Features → Routing: the fixed rules that narrow the tools."),
            ("Funktionen → Ablauf und Freigabe zeigen: Werkzeuge unter der Antwort, ein wartender Vorschlag als Karte mit Ja und Nein "
             "und eine Frage am Ende der Antwort mit ihren Antworten als Knöpfen (Ja/Nein, A oder B), ein kurzes Ja darauf behält "
             "das Thema der Frage davor (nur eigenes Profil und Gerät, Standard aus).",
             "Features → Show steps and approvals: tools below the answer, a waiting proposal as a card with Yes and No "
             "and a question at the end of the answer with its answers as buttons (yes/no, A or B); a short yes to it keeps the "
             "topic of the question before (own profile and device only, default off)."),
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
            ("chat_turn.STUFEN", ("die sieben Stufen in fester Reihenfolge", "the seven stages in fixed order")),
            ("chat_turn.shared_stranger", ("fremde Stimme am Lautsprecher", "unknown voice at a speaker")),
            ("chat.trim_history", ("Verlauf kürzen", "trim the history")),
            ("chat.left_out", ("Antworten aus fremdem Text weglassen", "leave out answers from outside text")),
            ("chat.offer_memory", ("kein memory_save, wenn die Nachricht nur fragt", "no memory_save when the message only asks")),
            ("intent.classify_cfg", ("feste Regeln der Weiche", "the switch's fixed rules")),
            ("klaeren.answer", ("Antwort auf eine Rückfrage", "answer to a question back")),
            ("klaeren.weg_answer", ("Antwort auf die Rückfrage zum Weg", "answer to the question which way")),
            ("features.allowed", ("Freigabe je Funktion", "release per function")),
            ("notaus.locked_tools", ("was der Notaus wegnimmt", "what the kill switch takes away")),
            ("intent.narrow", ("Werkzeuge eingrenzen", "narrow the tools")),
            ("chat_turn.notaus_note", ("Satz für das Modell bei Notaus", "sentence for the model with the kill switch")),
            ("chat.ha_take", ("Befehl mit Codewort nur von seiner Quelle", "command with code word only from its source")),
            ("profiles.quelle", ("die eine Quelle eines Zugs: Art, Gespräch, Gerät", "the one source of a turn: kind, conversation, device")),
            ("profiles.pending_replaced", ("ein Ja, dessen Vorschlag von woanders ersetzt wurde", "a yes whose proposal was replaced from elsewhere")),
            ("stoppwort.ende", ("ein ganzer Satz aus Stoppwörtern beendet das Gespräch", "a whole sentence of stop words ends the talk")),
            ("proactive.answers_note", ("Antwort auf eine Meldung des Spark", "answer to a note of the Spark")),
        ],
        "tests": ["test_klaeren", "test_features", "test_notaus", "test_hardening", "test_weiche", "test_sicherheit_sofort",
                  "test_abbrechen", "test_geraet_statt_profil"],
        "heute": [],
    },
    # ------------------------------------------------------------------ Antwort bauen (chat._answer)
    "weiche": {
        "stand": "13052b11fc",
        "bezug": {
            "intent.GROUPS": ["s4", "s6"], "intent_bench.BENCH": ["s4", "s5"], "intent_alltag.ALLTAG": ["s14"],
            "weiche.KEEP_VERSIONS": ["s4"], "intent.Route": ["s6"], "intent.follow_up": ["s8"],
            "intent.ask_model": ["s10"], "intent.pick_in_time": ["s10"], "intent.lean": ["s12"],
            "weiche.count": ["s14"], "weiche_unklar.anon": ["s14"], "weiche.trace": ["s14"], "intent_alltag.measure": ["s14"], "regeln": ["s9"],
            "intent.OWN_WROTE": ["s5"], "intent.OWN_READ": ["s5"], "intent.OWN_PAPER": ["s5"], "intent.PARCEL_MAIL": ["s5"],
            "intent.NARROW_KEEP": ["s11"], "quellen_bench.BENCH": ["s14"], "quellen_bench.measure": ["s14"],
            "quellen.klasse": ["s14"], "quellen.PROBE_MS": ["s14"], "quellen.blick": ["s14"],
            "regel:Modell ordnet ein": ["s10"], "regel:Knapp": ["s12"],
            "regel:Einordnung mit Wahrscheinlichkeit": ["s10"],
            "intent.negated": ["s11", "s13"], "intent.cancel": ["s2"], "chat.PRIVATE_WORDS": ["s5", "s13"],
            "chat.first_tool": ["s13"], "intent.normalize": ["s4"], "intent.KNOW": ["s5"], "intent.EMERGENCY": ["s5"],
            "intent.LATER": ["s5"], "intent.FOLLOW": ["s8"], "intent.asked_age": ["s8"], "intent_bench.GEGEN": ["s14"],
            "intent_bench.gegen": ["s14"], "intent.ask_route": ["s15"], "intent.ask_texts": ["s15"],
            "intent.ASK_SAYS": ["s15"], "intent.ASK_MAX": ["s15"], "intent.ASK_MAX_CHARS": ["s15"],
            "klaeren.weg_ask": ["s15"], "weiche.learn_choice": ["s15"],
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
                  "kann ein falsch zugeordneter Satz nie mehr erlauben. Er kann ein Werkzeug fehlen lassen oder, bei "
                  "einer Gruppe mit einem einzigen Werkzeug, dieses zur Pflicht machen; darum macht nur ein starkes Wort "
                  "die Websuche zur Pflicht, nie ein privater Satz, und ein verneinter Satz nie ein änderndes Werkzeug.",
                  "Few fitting tools make the model faster and more accurate: it reads less and misses less often. "
                  "Because the switch only takes away from what rights and locks left, a wrongly sorted sentence can "
                  "never allow more. It can leave a tool out or, for a group with a single tool, make that one a must; "
                  "so only a strong word makes the web search a must, never a private sentence, and a negated sentence "
                  "never a changing tool."),
        "ablauf": [
            S("s1", "start", ("Nur die eigene Nachricht", "Only the own message"),
              ("intent.classify_cfg", "intent.classify_cfg"),
              ("Gelesen wird nur die letzte Nachricht der Person selbst, nie eine Antwort davor, fremder Text oder was "
               "das Modell geschrieben hat. Dazu kommen die Wörter, die der Admin unter Funktionen → Weiche gespeichert "
               "hat. Vor allen Regeln läuft ein Schritt Normalisierung (intent.normalize, auch für die Pflicht-Wörter): "
               "„Strassenbahn“ und „Kueche“ in der Schreibweise der Wortlisten, „Wohnzimmerlampe“ als „Wohnzimmer "
               "lampe“, einige englische Wendungen auf Deutsch.",
               "Only the person's own latest message is read, never an answer before, outside text or what the "
               "model wrote. The words the admin saved under Features → Routing are added. Before every rule one "
               "normalization step runs (intent.normalize, also for the must words): „Strassenbahn“ and „Kueche“ in "
               "the spelling of the word lists, „Wohnzimmerlampe“ as „Wohnzimmer lampe“, a few English phrases in "
               "German.")),
            S("s2", "frage", ("Nur Plaudern?", "Only small talk?"),
              ("„Danke“, „Hallo“, „Gute Nacht“", "„thanks“, „hello“, „good night“"),
              ("Ist der ganze Satz ein Gruß oder Dank, ein Stoppwort („Stopp“, „Hör auf“: Grund „Stopp“) oder ruft er "
               "den Wunsch ab („Vergiss es“, „Lass es“, „Schon "
               "gut“, „Nein, doch nicht“: intent.cancel, Grund „Abbruch“), heißt die Gruppe „plaudern“. Die Antwort "
               "bekommt dann gar kein Werkzeug, also nie das Gedächtnis.",
               "If the whole sentence is a greeting or thanks, a stop word („Stop“, „Be quiet“: reason „Stopp“) or "
               "calls the wish off („Never mind“, „Forget it“, "
               "„Leave it“: intent.cancel, reason „Abbruch“), the group is „plaudern“ (small talk). The answer then "
               "gets no tool at all, so never the memory."),
              ("ok", "ja", "s14")),
            S("s3", "frage", ("Frage zum Spark?", "Question about the Spark?"),
              ("vor allen anderen Gruppen", "before every other group"),
              ("„Wie verbinde ich Home Assistant?“ oder „Schalte die Websuche ein“ fragen nach dem Spark selbst, nicht "
               "nach einem Gerät oder einer Suche: Gruppe „spark“. Eine Frage zu Wörtern oder Sprachen zählt nie "
               "dazu, ebenso wenig „Was kannst du mir über die Frauenkirche erzählen?“: Das fragt nach dem Ding, "
               "außer es ist der Spark oder eine seiner Funktionen (hilfe.ABOUT); ebenso „Was ist ein Kalender?“, "
               "außer der Spark ist genannt (hilfe.SPARK_NAMED). Wurde auf einer Seite des Panels „Frag Spark“ benutzt, gilt dieselbe Gruppe nach fester Regel "
               "über den Ort der Frage.",
               "„How do I connect Home Assistant?“ or „Switch on web search“ ask about the Spark itself, not about a "
               "device or a search: group „spark“. A question about words or languages never counts, nor does „What "
               "can you tell me about the Frauenkirche?“: it asks about the thing, unless that is the Spark or one of "
               "its functions (hilfe.ABOUT); likewise „What is a calendar?“, unless the Spark is named "
               "(hilfe.SPARK_NAMED). When „Ask "
               "Spark“ was used on a page of the panel, the same group holds by a fixed rule about where it was "
               "asked."),
              ("ok", "ja", "s9")),
            S("s4", "schritt", ("Wörter je Gruppe", "Words per group"),
              ("eingebaut · Pflicht-Wörter · eigene Wörter", "built in · must words · own words"),
              ("Jede Gruppe hat ihre eingebaute Wortliste (Licht, Termin, Postfach, Schirm …). Ein Schaltverb ohne "
               "Gerät zählt nur als ganzer Befehl, „an“ oder „aus“ am Ende allein nur als „Alles aus“ (eine Liste, "
               "intent.SWITCH_VERB). Die Pflicht-Wörter des Admins und seine eigenen "
               "Wörter je Gruppe (höchstens {intent.MAX_ROUTE_WORDS}, nur ganze Wörter) finden eine Gruppe "
               "zusätzlich, ersetzen aber nichts.",
               "Each group has its built-in word list (light, appointment, mailbox, umbrella …). A switching verb "
               "without a device only counts as a whole command, „on“ or „off“ at the end alone only as „all off“ (one "
               "list, intent.SWITCH_VERB). The admin's must words and own words "
               "per group (at most {intent.MAX_ROUTE_WORDS}, whole words only) find a group as well, but replace "
               "nothing.")),
            S("s5", "schritt", ("Vorrang zwischen Gruppen", "Priority between groups"),
              ("feste Regeln · dann „Nicht bei“", "fixed rules · then „Not with“"),
              ("Treffen mehrere Gruppen, räumen feste Regeln auf: Wetter, Liste, Nachricht, Dokument und „Dokument "
               "erstellen“ gehen vor Smart Home, wenn kein Schaltbefehl dabei ist; Pakete vor Mail, außer jemand hat "
               "„mir geschrieben“ (dann Mail); ein Preis „laut Angebot, Rechnung oder Vertrag“ ist eine eigene Unterlage, "
               "nie die Websuche; eine Lesefrage nach eigenen Daten ohne Suchwort ohne andere Gruppe wird „mail“ "
               "(„Hat mir die Bank geschrieben?“, nur mit genanntem Absender) oder „finden“ („Hat sich der Klempner "
               "gemeldet?“, „Was hatte ich bestellt?“), nie bei Zeitung, Web oder Archiv; „Habe ich neue "
               "Nachrichten?“ ist eine Nachricht, „Was gibt es in den Nachrichten?“ die Websuche; ein Auftrag, der "
               "regelmäßig wiederkommt oder etwas beobachtet, ist ein Agent; eine Frage zu Sprache oder Natur oder "
               "nach einem Unterschied ist nie ein Gerät; ein Preis oder Streik ist die Websuche, nicht iPhone oder "
               "Bahn; „Ruf mich an“ ist der Rückruf des Spark, nicht das iPhone; „Liste der …“ in einer Datei ist "
               "nicht die eigene Liste; ein schwaches Suchwort allein („Ergebnis“, „gewonnen“, „Nachrichten“) in einem "
               "privaten Satz („Ergebnis meiner Blutuntersuchung“, „Nachrichten von Tom“, „Ich habe gewonnen“) ist "
               "keine Websuche. Eine Wissensfrage („Was ist eine Lampe?“, „Wie funktioniert eine Steckdose?“, „Wer hat den "
               "Strom erfunden?“, „Erklär mir …“), ein Witz oder Gedicht über ein Ding und „Ich bin in der Küche“ "
               "verlieren jede handelnde Gruppe, damit Websuche und Wikipedia bleiben, außer ein eigenes Ding oder "
               "ein Raum ist genannt (intent.KNOW); „Liste“ allein zählt nur mit eigenem oder Ortswort. Eine "
               "Notrufnummer bekommt nie den Anruf, sondern gar kein Werkzeug (Grund „Notruf“, intent.EMERGENCY), ein "
               "Anruf für später ist eine Erinnerung (intent.LATER). „Bescheid“ ist ein Amtsbescheid nur zusammengesetzt "
               "oder mit dem Amt, „Sag Anna Bescheid“ eine Nachricht. Zuletzt nehmen die „Nicht bei“-Wörter des Admins "
               "Gruppen wieder heraus.",
               "When several groups match, fixed rules tidy up: weather, list, message, document and „create "
               "document“ come before smart home when there is no switching command; parcels before mail, unless "
               "someone „wrote to me“ (then mail); a price „according to the offer, invoice or contract“ is an own "
               "paper, never the web search; a reading question about the own data without a search word and without "
               "another group becomes „mail“ („Did the bank write to me?“, only with a named sender) or „finden“ "
               "(„Did the plumber get back to me?“, „What did I order?“), never with a newspaper, the web or the "
               "archive; „Do I have "
               "new messages?“ is a message, „What is in the news?“ the web search; a job that comes back regularly "
               "or watches something is an agent; a question about language, nature or a difference is never a "
               "device; a price or a strike is the web search, not the iPhone or the train; „Call me“ is the Spark "
               "calling back, not the iPhone; „a list of …“ in a file is not the own list; a weak search word alone "
               "(„result“, „won“, „news“) in a private sentence („result of my blood test“, „messages from Tom“, „I "
               "won“) is no web search. A knowledge question („What is a lamp?“, „How does a socket work?“, „Who invented "
               "electricity?“, „Explain …“), a joke or poem about a thing and „I am in the kitchen“ lose every acting "
               "group, so web search and Wikipedia stay, unless an own thing or a room is named (intent.KNOW); „list“ "
               "alone only counts with an own or place word. An emergency number never gets the call but no tool at "
               "all (reason „Notruf“, intent.EMERGENCY), a call for later is a reminder (intent.LATER). „Bescheid“ is "
               "an official notice only as a compound or with the office, „Tell Anna“ (Bescheid) a message. Last, the "
               "admin's „Not with“ words take groups out again.")),
            S("s6", "frage", ("Gruppe erkannt?", "Group recognized?"),
              ("eine, zwei oder mehr", "one, two or more"),
              ("Eine Gruppe oder höchstens {intent.MAX_MIXED} gelten als klar und grenzen ein. Mehr Gruppen auf "
               "einmal sind nicht klar genug: dann bleiben alle Werkzeuge. Kommt „finden“ (eigene Daten suchen) "
               "mit zu vielen Gruppen, fällt zuerst „dokument“ weg, denn Finden sucht auch in den Dokumenten.",
               "One group or at most {intent.MAX_MIXED} count as clear and narrow. More groups at once are not "
               "clear enough: then every tool stays. When „finden“ (searching the own data) comes with too many "
               "groups, „dokument“ goes first, since Find searches the documents too."),
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
              ("Ist die Nachricht kurz (höchstens {intent.FOLLOW_MAX} Zeichen), zeigt sie wirklich zurück („und …“, "
               "„wieder“, „auch“, „davon“; nie ein nacktes „es“, „dort“ oder „ihr“, intent.FOLLOW), kam die eigene "
               "Frage davor höchstens {intent.FOLLOW_SECONDS} Sekunden vorher in diesem Gespräch (intent.asked_age, "
               "nur im Speicher; sonst „weiche: Folgefrage zu alt“) "
               "und hatte sie eine klare Gruppe, gilt diese Gruppe wieder. Es zählt nur die "
               "eigene Frage, nie die Antwort. Im Journal steht „weiche: Folgefrage“. Ebenso ein schlichtes „Ja“/„Nein“ "
               "oder ein Knopf der Rückfrage-Karte auf die Frage der Antwort davor (ablauf.was_asked, zehn Minuten, "
               "dasselbe Gespräch): „weiche: Antwort auf Rückfrage“.",
               "If the message is short (at most {intent.FOLLOW_MAX} characters), really points back („and …“, "
               "„again“, „too“, „of it“; never a bare „it“, „there“ or „her“, intent.FOLLOW), the own question before "
               "came at most {intent.FOLLOW_SECONDS} seconds earlier in this conversation (intent.asked_age, memory "
               "only; otherwise „weiche: Folgefrage zu alt“) "
               "and had a clear group, that group holds again. Only the own question "
               "counts, never the answer. The journal says „weiche: Folgefrage“. So does a plain „yes“/„no“ or a "
               "button of the question card to the question of the answer before (ablauf.was_asked, ten minutes, same "
               "conversation): „weiche: Antwort auf Rückfrage“."),
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
               "Schwelle (Standard {systemone.ROUTE_MIN|prozent}); mit Funktionen → Hilfsmodell fragt sie "
               "erst das kleine Hilfsmodell, lädt es noch oder ist es unsicher, sofort das große, die Schwelle bleibt "
               "dieselbe. Die Hinweis-Gruppen bleiben neben der Wahl. In "
               "einer Wartungspause des Sprachmodells wird es nicht gefragt.",
               "If no rule found a group and „Questions no rule recognizes“ is set to the model, the language model "
               "picks one group from the fixed list once (JSON only, only the own message). The question already "
               "runs beside the preparation from its start; the wait is at most {intent.ASK_TIMEOUT} seconds, with "
               "„Fast answer start“ only {intent.CACHED_WAIT|ms} after the preparation. With classification "
               "with probabilities the pick only counts from the threshold (default {systemone.ROUTE_MIN|prozent}); with "
               "Features → Helper model it asks the small helper model first, and while that is loading "
               "or unsure the big one at once, with the same threshold. The hint "
               "groups stay beside the pick. During a maintenance pause of the language model it is not asked."),
              ("info", "ja", ("Grund „Modell“", "reason „Modell“"))),
            S("s11", "schritt", ("Eingrenzen", "Narrow"),
              ("intent.narrow · nie mehr als vorher", "intent.narrow · never more than before"),
              ("Bei einer klaren Gruppe bleiben ihre Werkzeuge, dazu immer {intent.NARROW_KEEP|anzahl} feste "
               "(sich etwas merken, eigene Dokumente, Finden in allen eigenen Daten), die Werkzeuge der Hinweise, die zusätzlichen Werkzeuge des "
               "Admins für diese Gruppe (höchstens {intent.MAX_EXTRA}) und was die eigenen Worte ausdrücklich "
               "nennen („aufs reMarkable“, der Rechner nur, wenn die eigenen Worte ihn nennen oder die Frage am Begleiter "
               "kam). Alles nur, soweit schon angeboten. Ist von der Gruppe nichts angeboten, "
               "steht die Gruppe auf „nicht eingrenzen“ oder ist der Satz verneint („Ruf Mama nicht an“, „Mach das "
               "Licht nicht aus“: intent.negated, eine feste Regel; „nicht vergessen“ zählt nicht), bleiben alle; "
               "das Journal nennt dann „verneint“.",
               "With a clear group its tools stay, plus always {intent.NARROW_KEEP|anzahl} fixed ones (remembering "
               "something, own documents, Find in all own data), the hints' tools, the admin's extra tools for this group (at most "
               "{intent.MAX_EXTRA}) and what the own words name explicitly („onto the reMarkable“, the computer only when the "
               "own words name it or the question came from the companion). All only as far "
               "as already offered. If nothing of the group is offered, the group is set to „do not narrow“ or the "
               "sentence is negated („Don't call Mom“, „Don't turn off the light“: intent.negated, a fixed rule; "
               "„don't forget“ does not count), all stay; the journal then says „verneint“.")),
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
               "Runde muss genau dieses rufen („Wie wird das Wetter?“). Pflicht ist nie ein änderndes Werkzeug aus einer "
               "Admin-Regel, nie die Websuche bei einem privaten Satz (chat.PRIVATE_WORDS) und bei einem verneinten "
               "Satz nur ein lesendes ohne Internet, das dann mit Namen gerufen wird (chat.first_tool). Ein kurzer, eindeutiger Lesesatz („Wie ist "
               "das Wetter heute?“) wird mit „Eindeutiges direkt abrufen“ vom Panel selbst abgerufen, für morgen "
               "und übermorgen mit dem Datum, das das Panel ausrechnet; „Was war meine letzte Bestellung?“ sucht es mit "
               "festen Wörtern in den Mails (intent.DIRECT_ARGS).",
               "One single clear group, one required tool and only that one of the group offered: the first round "
               "must call exactly that one („What will the weather be?“). A must is never a changing tool from an admin "
               "rule, never the web search for a private sentence (chat.PRIVATE_WORDS) and for a negated sentence only "
               "a reading one without the internet, which is then called by name (chat.first_tool). A short, clear reading sentence („What is "
               "the weather today?“) is fetched by the panel itself with „Fetch clear questions directly“, for "
               "tomorrow and the day after with the date the panel works out; „What was my last order?“ is searched in "
               "the mails with fixed words (intent.DIRECT_ARGS).")),
            S("s15", "frage", ("Rückfrage zum Weg?", "Ask which way?"),
              ("intent.ask_route · nur vor einer Änderung", "intent.ask_route · only before a change"),
              ("Mit Funktionen → Rückfrage zum Weg (Standard aus) fragt das Panel, bevor sich etwas ändert, welcher Weg "
               "gemeint ist (intent.ask_route, feste Regeln, nie das Modell): zwei nahe Gruppen, die beide etwas ändern "
               "und angeboten sind (Mail oder Nachricht, Termin oder Erinnerung, Anruf oder Nachricht, Liste oder "
               "Erinnerung), oder eine ändernde Gruppe nur auf schwache Zeichen (nur Hinweiswörter, eine Folgefrage mit "
               "etwas Neuem, die Wahl des Modells unter ihrer Schwelle). Nie bei einer Lese- oder Wissensfrage, einem "
               "verneinten Satz, Abbruch oder Stopp, nach Text von außen, für Gäste, eine fremde Stimme oder MCP, nie "
               "wenn der Satz den Weg selbst nennt oder beide Wünsche verbindet, nie über {intent.ASK_MAX_CHARS} Zeichen, "
               "höchstens einmal je Zug und nie zweimal für denselben Satz (klaeren.weg_ask). Frage und Knöpfe kommen aus "
               "der festen Tabelle intent.ASK_SAYS (intent.ask_texts, höchstens {intent.ASK_MAX} Wege und immer „Einfach "
               "antworten“, gesprochen mit „erstens, zweitens …“); diese Antwort ist nur die Frage, ohne Modell und ohne "
               "Werkzeug. Die Wahl führt den Satz mit der gewählten Gruppe aus (Grund „Rückfrage“), „Einfach antworten“ "
               "ohne ändernde Werkzeuge, und zählt als Korrektur (weiche.learn_choice, nur Gruppen und Zahlen).",
               "With Features → Ask which way (default off) the panel asks which way is meant before anything changes "
               "(intent.ask_route, fixed rules, never the model): two close groups that both change something and are "
               "offered (mail or message, appointment or reminder, call or message, list or reminder), or one changing "
               "group on weak evidence only (hint words only, a follow-up naming something new, the model's pick below "
               "its threshold). Never for a reading or knowledge question, a negated sentence, a cancel or stop, after "
               "outside text, for guests, another voice or MCP, never when the sentence names the way itself or joins "
               "both wishes, never over {intent.ASK_MAX_CHARS} characters, at most once per turn and never twice for the "
               "same sentence (klaeren.weg_ask). Question and buttons come from the fixed table intent.ASK_SAYS "
               "(intent.ask_texts, at most {intent.ASK_MAX} ways and always „Just answer“, spoken with „first, second "
               "…“); this answer is only the question, without the model and without a tool. The choice runs the "
               "sentence with the chosen group (reason „Rückfrage“), „Just answer“ without changing tools, and counts as "
               "a correction (weiche.learn_choice, groups and numbers only)."),
              ("info", "ja", ("nur die feste Frage", "only the fixed question"))),
            S("s14", "ende", ("Journal und Zählung", "Journal and count"),
              ("weiche: Absicht … · weiche-stats.json", "weiche: Absicht … · weiche-stats.json"),
              ("Jeder Zug schreibt eine Zeile „weiche: Absicht … | Grund … | Hinweis … | Werkzeuge x von y | Pflicht "
               "… | gesperrt … | eingrenzen an/aus“; ein Grundwort steht nur da, wenn es noch in der Nachricht "
               "steht. Gezählt werden je Tag und Gruppe nur Anzahlen ({weiche.KEEP_DAYS} Tage), nie ein Wort der "
               "Frage. Mit „Unklare Fragen anonym merken“ kommt eine unklare Frage eines Profils (nie eines Gastes, "
               "nie mit dem Codewort) zusätzlich geschwärzt auf die Weiche-Seite: feste Regeln wie bei „Probleme "
               "melden“, Kontaktnamen und jede Zahl werden Platzhalter, eine zweite Prüfung verwirft, was noch "
               "persönlich wirkt (weiche_unklar.anon); ohne Profil, Gerät und Uhrzeit, versiegelt, höchstens "
               "{weiche_unklar.MAX_ROWS} Sätze, {weiche_unklar.KEEP_DAYS} Tage. Dann geht die Liste an die Antwort.",
               "Every turn writes a line „weiche: Absicht … | Grund … | Hinweis … | Werkzeuge x von y | Pflicht … | "
               "gesperrt … | eingrenzen an/aus“; a reason word only shows when it is still in the message. Per day "
               "and group only counts are kept ({weiche.KEEP_DAYS} days), never a word of the question. With „Keep "
               "unclear questions anonymously“ an unclear question of a profile (never a guest, never with the code "
               "word) also goes redacted onto the switch page: fixed rules as in „Report a problem“, contact names and "
               "every number become placeholders, a second check drops what still looks personal "
               "(weiche_unklar.anon); without profile, device and time, sealed, at most {weiche_unklar.MAX_ROWS} "
               "sentences, {weiche_unklar.KEEP_DAYS} days. Then the list goes to the answer.")),
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
            (("„Ruf Mama nicht an“", "„Don't call Mom“"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s9", "s10", "s11", "s12", "s13", "s14"],
             ("Gruppe iphone, aber verneint: nichts wird eingegrenzt, kein Werkzeug ist Pflicht.",
              "Group iphone, but negated: nothing is narrowed, no tool is a must.")),
            (("„Schreib Tom eine Mail, dass ich später komme“ mit „Rückfrage zum Weg“",
              "„Write Tom a mail that I am late“ with „Ask which way“"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s6!", "s9", "s10", "s11", "s12", "s13", "s15", "s15!", "s14"],
             ("Zwei nahe Gruppen mail und nachricht: das Panel fragt „Soll ich erstens als E-Mail schicken, zweitens als "
              "Nachricht im Haus schicken oder drittens einfach antworten?“, nichts ändert sich vor der Wahl.",
              "Two close groups mail and message: the panel asks „Should I first send it as an e-mail, second send it as a "
              "message at home or third just answer?“, nothing changes before the choice.")),
            (("„Was ist eine Lampe?“", "„What is a lamp?“"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12", "s13", "s14"],
             ("Wissensfrage: Smart Home fällt weg, das Modell behält Websuche und Wikipedia.",
              "Knowledge question: smart home goes, the model keeps web search and Wikipedia.")),
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
            ("{intent_bench.GEGEN|anzahl}", ("Sätze der Gegenprobe", "sentences of the counter check"), "intent_bench.GEGEN"),
            ("{intent.FOLLOW_SECONDS}", ("Sekunden höchstens bis zur Folgefrage", "seconds at most until a follow-up"), "intent.FOLLOW_SECONDS"),
            ("{quellen_bench.BENCH|anzahl}", ("Sätze der Quellen-Messbank", "sentences of the source bench"), "quellen_bench.BENCH"),
            ("{quellen.PROBE_MS}", ("ms höchstens für die Treffer-Probe der Quellen-Weiche", "ms at most for the source switch's hit probe"), "quellen.PROBE_MS"),
            ("{weiche.KEEP_VERSIONS}", ("Versionen für Rückgängig", "versions for undo"), "weiche.KEEP_VERSIONS"),
            ("{intent.ASK_MAX}", ("Wege höchstens in einer Rückfrage zum Weg", "ways at most in one question which way"), "intent.ASK_MAX"),
            ("{intent.ASK_MAX_CHARS}", ("Zeichen höchstens für eine Rückfrage zum Weg", "characters at most for a question which way"), "intent.ASK_MAX_CHARS"),
        ],
        "einstellen": [
            ("Funktionen → Gezielte Werkzeugwahl: ohne diesen Schalter grenzt die Weiche nichts ein (Standard aus).",
             "Features → Targeted tool choice: without this switch the switch narrows nothing (default off)."),
            ("Funktionen → Weiche: eigene Wörter je Gruppe, „Nicht bei“, zusätzliche Werkzeuge, Gruppen ohne Eingrenzen, "
             "Pflicht-Wörter, eigene Testsätze und was Fragen bekommen, die keine Regel erkennt. Jede Änderung läuft "
             "vorher durch alle Testsätze; ändert sich einer, wird erst nach Bestätigung gespeichert. Rückgängig hält "
             "die letzten {weiche.KEEP_VERSIONS} Fassungen.",
             "Features → Routing: own words per group, „Not with“, extra tools, groups without narrowing, must words, "
             "own test sentences and what questions no rule recognizes get. Every change runs through all test "
             "sentences first; if one changes, it is saved only after confirming. Undo keeps the last "
             "{weiche.KEEP_VERSIONS} versions."),
            ("Funktionen → Rückfrage zum Weg: vor einer Änderung fragt das Panel, welcher Weg gemeint ist (Standard aus, "
             "baut auf „Rückfrage statt Raten“).",
             "Features → Ask which way: before a change the panel asks which way is meant (default off, builds on „Ask "
             "instead of guessing“)."),
            ("Funktionen → Eindeutiges direkt abrufen: kurze Lesefragen ruft das Panel selbst ab (Standard aus).",
             "Features → Fetch clear questions directly: the panel fetches short reading questions itself (default off)."),
            ("Funktionen → Weiche abstimmen (Standard aus): das Sprachmodell schlägt Wörter je Gruppe vor, das Panel behält "
             "ein Wort nur, wenn kein Testsatz kippt, die Übungshälfte besser und die Prüfhälfte nicht schlechter wird; "
             "gespeichert wird erst mit „Übernehmen“.",
             "Features → Tune the switch (default off): the language model proposes words per group, the panel keeps a "
             "word only when no test sentence flips, the practice half gets better and the check half no worse; it is "
             "saved only with \"Apply\"."),
            ("Funktionen → Gezielte Werkzeugwahl → Unklare Fragen anonym merken (Standard aus): unklare Fragen der Profile "
             "stehen geschwärzt bei „unklar“ auf der Weiche, mit „Gehört zu …“ zum Feintunen; jedes Profil kann es unter "
             "Ich → Gespräch → Datenschutz für sich ausschalten.",
             "Features → Targeted tool choice → Keep unclear questions anonymously (default off): the profiles' unclear "
             "questions show redacted at „unclear“ on the switch, with „Belongs to …“ for tuning; every profile can "
             "switch it off for itself under Me → Conversation → Privacy."),
        ],
        "sehen": [
            ("Funktionen → Weiche: „Satz ausprobieren“ zeigt den ganzen Weg eines Satzes ohne Modell; dazu Testsätze, "
             "Alltagsquote, Gegenprobe und Statistik (7 Tage, nur Anzahlen).",
             "Features → Routing: „Try a sentence“ shows the whole way of a sentence without the model; also test "
             "sentences, everyday score, counter check and statistics (7 days, counts only)."),
            ("Zustand → Logs: Zeilen „weiche: Absicht …“, „weiche: Folgefrage“, „weiche: Folgefrage zu alt“, "
             "„weiche: Modell-Zuordnung …“ und „weiche: direkt abgerufen“.",
             "Status → Logs: lines „weiche: Absicht …“, „weiche: Folgefrage“, „weiche: Folgefrage zu alt“, "
             "„weiche: Modell-Zuordnung …“ and „weiche: direkt abgerufen“."),
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
            (("Gegenprobe", "Counter check"), [
                ("Die Gegenprobe ({intent_bench.GEGEN|anzahl} Sätze: Wissensfragen mit Alltagswörtern, Verneinungen, "
                 "Plaudern, Stopp und Abbruch, Anrufe) misst die andere Seite: Sätze, die keine oder eine bestimmte "
                 "Gruppe nicht bekommen dürfen. Gezählt werden falsche Sätze und davon die, bei denen die erste Runde "
                 "ein Werkzeug rufen müsste („falsch erzwungen“). Ein Selbsttest erlaubt beiden Zahlen nur zu sinken. "
                 "In app/ druckt python3 panel/intent_bench.py alle drei Messungen und die Verwechslungen je Gruppe.",
                 "The counter check ({intent_bench.GEGEN|anzahl} sentences: knowledge questions with everyday words, "
                 "negations, small talk, stop and cancel, calls) measures the other side: sentences that must get no "
                 "group or not a given one. It counts the wrong ones and of those the ones where the first round would "
                 "have to call a tool („wrongly forced“). A self-test only lets both numbers go down. In app/, python3 "
                 "panel/intent_bench.py prints all three measures and the confusions per group."),
            ]),
            (("Quellen-Messbank", "Source bench"), [
                ("Die Quellen-Messbank ({quellen_bench.BENCH|anzahl} Sätze, deutsch und englisch) prüft für Lese- und "
                 "Wissensfragen, ob der heutige Weg (Weiche, Eingrenzen, „Erst lokal“) intern, extern oder beides "
                 "entscheidet und ob die nötigen eigenen Quellen erreichbar sind: Mail, Anhang, Dokument, Termin, "
                 "Kontakt, Gespräch, Liste, Wissensbuch, Web. Gemessen mit allen Schaltern frei, ohne Daten, Uhr und "
                 "Modell. Ein Selbsttest hält die Untergrenze; sie sinkt nie.",
                 "The source bench ({quellen_bench.BENCH|anzahl} sentences, German and English) checks for reading and "
                 "knowledge questions whether today's way (switch, narrowing, „Local first“) decides internal, "
                 "external or both and whether the needed own sources are reachable: mail, attachment, document, "
                 "appointment, contact, conversation, list, knowledge book, web. Measured with every switch released, "
                 "without data, clock or model. A self-test holds the floor; it never goes down."),
            ]),
            (("Quellen-Weiche (zweite Stufe)", "Source switch (second stage)"), [
                ("Die Weiche hier ist die erste Stufe: sie bestimmt, was eine Handlung braucht. Für eine Wissens- oder "
                 "Lesefrage entscheidet danach die Quellen-Weiche (quellen.klasse) mit festen Regeln, nie das Modell: "
                 "intern (eigene Daten), extern (Welt) oder beides. Eigene Quelle genannt, eine Gruppe der eigenen "
                 "Daten oder ein Besitzwort mit eigenen Daten heißt intern; Aktuelles und Welt (Wetter, Preise, "
                 "Nachrichten, Ämter) extern; zeitloses Wissen und Wie-Fragen zum eigenen Gerät beides. Sonst prüft "
                 "eine Treffer-Probe im eigenen Finden-Index (höchstens {quellen.PROBE_MS} ms, im eigenen Thread, nur "
                 "für das eigene Profil, nie für Gäste, fremde Stimmen oder MCP): starke Treffer intern, schwache "
                 "beides, keine extern. Ohne Finden bleibt es wie vorher. „Erst lokal“ fragt bei intern und beides "
                 "alle freigegebenen Quellen (quellen.blick); bei beides sucht das Panel selbst mit den eigenen "
                 "Worten im Web, bevor eine Mail gelesen ist. Die Messbank misst beide Stufen zusammen.",
                 "The switch here is the first stage: it decides what an action needs. For a knowledge or reading "
                 "question the source switch (quellen.klasse) then decides by fixed rules, never the model: internal "
                 "(own data), external (the world) or both. An own source named, a group of the own data or a word "
                 "of ownership with own data means internal; current things and the world (weather, prices, news, "
                 "offices) external; timeless knowledge and how-to questions about the own device both. Otherwise a "
                 "hit probe in the own Find index decides (at most {quellen.PROBE_MS} ms, in a thread of its own, "
                 "only for the own profile, never for guests, other voices or MCP): strong hits internal, weak ones "
                 "both, none external. Without Find it stays as before. „Local first“ asks every released source for "
                 "internal and both (quellen.blick); for both the panel searches the web itself with the own words, "
                 "before any mail is read. The bench measures both stages together."),
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
            ("intent.negated", ("Verneinung: nie eingrenzen, keine Pflicht", "negation: never narrow, no must")),
            ("intent.cancel", ("„Vergiss es“ als Abbruch ohne Werkzeug", "„Never mind“ as a cancel without any tool")),
            ("chat.PRIVATE_WORDS", ("private Sätze: keine Websuche aus schwachen Wörtern", "private sentences: no web search from weak words")),
            ("chat.first_tool", ("Pflicht-Werkzeug der ersten Runde", "must tool of the first round")),
            ("weiche.count", ("Statistik ohne Inhalt", "statistics without content")),
            ("weiche_unklar.anon", ("unklare Fragen geschwärzt", "unclear questions redacted")),
            ("weiche.trace", ("Satz ausprobieren", "try a sentence")),
            ("intent_alltag.measure", ("Alltagsquote", "everyday score")),
            ("quellen_bench.measure", ("Quellen-Messbank", "source bench")),
            ("intent.OWN_WROTE", ("Lesefrage: jemand hat mir geschrieben → mail", "reading question: someone wrote to me → mail")),
            ("intent.OWN_READ", ("Lesefrage nach eigenen Daten → finden", "reading question about the own data → finden")),
            ("intent.OWN_PAPER", ("Preis laut eigener Unterlage, nie das Web", "price according to an own paper, never the web")),
            ("intent.PARCEL_MAIL", ("Paketwort mit eigener Mail → mail", "parcel word with the own mail → mail")),
            ("intent.NARROW_KEEP", ("bleibt immer beim Eingrenzen", "always kept when narrowing")),
            ("intent.normalize", ("ein Schritt Normalisierung vor allen Regeln", "one normalization step before every rule")),
            ("intent.KNOW", ("Wissensfrage: keine handelnde Gruppe", "knowledge question: no acting group")),
            ("intent.EMERGENCY", ("Notruf: kein Anruf, kein Werkzeug", "emergency number: no call, no tool")),
            ("intent.LATER", ("Anruf für später: Erinnerung", "call for later: reminder")),
            ("intent.FOLLOW", ("Folgefrage nur mit echtem Rückbezug", "follow-up only with a real reference back")),
            ("intent.asked_age", ("Folgefrage nur, solange die Frage davor frisch ist", "follow-up only while the question before is fresh")),
            ("intent_bench.gegen", ("Gegenprobe: falsch und falsch erzwungen", "counter check: wrong and wrongly forced")),
            ("quellen.klasse", ("zweite Stufe: intern, extern oder beides", "second stage: internal, external or both")),
            ("quellen.blick", ("die Quellen des kurzen Blicks je Klasse", "the quick look's sources per class")),
            ("intent.ask_route", ("Rückfrage zum Weg: wann das Panel fragt", "ask which way: when the panel asks")),
            ("intent.ask_texts", ("Frage und Knöpfe aus fester Tabelle", "question and buttons from a fixed table")),
            ("intent.ASK_SAYS", ("die Wege, nach denen gefragt wird", "the ways that are asked about")),
            ("klaeren.weg_ask", ("Frage stellen, nie zweimal derselbe Satz", "ask, never twice the same sentence")),
            ("weiche.learn_choice", ("die Wahl als Korrektur, nur Gruppen und Zahlen", "the choice as a correction, groups and numbers only")),
        ],
        "tests": ["test_intent", "test_klaeren", "test_intent_alltag", "test_quellen_bench", "test_quellen", "test_weiche", "test_weiche_unklar", "test_werkzeuge", "test_systemone"],
        "heute": [],
    },
    "antwort": {
        "stand": "fe17e201ae",
        "bezug": {
            "chat.MAX_SAVES": ["s11"], "chat.LOOP_SAME": ["s11"], "chat._answer": ["s4", "s5", "s11"], "chat_modell.model_turn": ["s4", "s11"], "chat_modell.herkunft_und_chip": ["s3"], "chat_modell.quellenangabe_zeile": ["s3"], "chat_ton.speech_out": ["s8"],
            "chat.split_sentences": ["s5"], "chat.said_key": ["s8"], "chat.no_code": ["s8"],
            "chat.loop_count": ["s11"], "answercheck.known": ["s6"], "answercheck.unsupported": ["s6"],
            "answercheck.fresh": ["s6"], "rechnen.fix": ["s6"],
            "taten.announces": ["s7", "s12"], "vorrat.WAIT": ["s11"], "frisch.nachsatz": ["s12"],
            "laufend.add": ["s14"],
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
               "beantworten“ bekommen Uhrzeit, Datum, Rechnungen (rechnen.calc), Datumsrechnungen und Einheiten als ganzer kurzer Satz den "
               "festen Satz des Panels, ohne Modell und ohne Sofort-Satz davor (sofort.answer, höchstens "
               "{sofort.MAX_CHARS} Zeichen). Ebenso kommt die Rückfrage zum Weg nur als feste Frage des Panels mit "
               "ihren Knöpfen, ohne Modell und ohne Werkzeug, und „Woher weißt du das?“ als feste Antwort des Panels "
               "aus der gemerkten Quelle der letzten Antwort (quellenangabe.antwort).",
               "chat() checks the rate limit, sets the mark „speech is running“ (background work waits) and shows the "
               "profile's other devices „answering“. Then chat_turn.prepare works out rights, locks, system prompt and "
               "the offered tools; _answer takes over. When the language model pauses (maintenance pause, emergency "
               "mode), a fixed sentence comes at once; in emergency mode with Parakeet the fixed commands come first, "
               "without a model (notbetrieb.antwort: Home Assistant, time, reminders). With „Answer simple things at "
               "once“ the time, the date, calculations (rechnen.calc), date calculations and units as a whole short sentence get the panel's fixed "
               "sentence, without a model and without an instant sentence before it (sofort.answer, at most "
               "{sofort.MAX_CHARS} characters). The question which way likewise comes only as the panel's fixed "
               "question with its buttons, without a model and without a tool, and „Where did you get that?“ as the "
               "panel's fixed answer from the kept source of the last answer (quellenangabe.antwort).")),
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
               "Werkzeug-Ergebnis an das Modell, fremder Text eingepackt als Daten; „Erst lokal“ bringt die besten "
               "Treffer aller freigegebenen Quellen mit Quelle und Datum, bei beides dazu die Websuche des Panels mit "
               "den eigenen Worten, und eine Mail darunter sperrt die Antwort wie eine gelesene Mail. Ein Artikel aus "
               "dem eigenen Kiwix und die Seiten der Websuche stehen danach als Quelle unter der Antwort; am Ende "
               "zählt das Panel die Herkunft („Aus: 2 Mails, 1 Termin“) und bietet bei intern ohne Web „Auch im "
               "Internet suchen“ an (chat_modell.herkunft_und_chip). Mit der Quellenangabe (quellenangabe.py) "
               "steht stattdessen unter jeder Wissensantwort jede gelaufene lesende Quelle („Quelle: 2 Mails, Websuche“ "
               "oder „nichts nachgeschlagen, nur Modellwissen“), mit Hinweis, wenn sie nicht zur Klasse der "
               "Quellen-Weiche passt; am Lautsprecher kurz gesprochen (chat_modell.quellenangabe_zeile).",
               "When the preparation decided that the panel acts itself (a switch command, reading states, „search "
               "locally first“, a clear reading request), it runs now. The result goes to the model like a tool "
               "result, outside text wrapped as data; „local first“ brings the best hits of every released source with "
               "source and date, for both also the panel's web search with the own words, and a mail among them locks "
               "the answer like a read mail. An article from the own Kiwix and the pages of the web search then stand "
               "as sources under the answer; at the end the panel counts the origin („From: 2 mails, 1 appointment“) "
               "and for internal without the web offers „Also search the web“ (chat_modell.herkunft_und_chip). With the "
               "source note (quellenangabe.py) every knowledge answer instead names each reading source that ran "
               "(„Source: 2 mails, Web search“ or „nothing looked up, model knowledge only“), with a note when it does "
               "not fit the source switch's class; at a speaker said briefly (chat_modell.quellenangabe_zeile).")),
            S("s4", "schritt", ("Runde vorbereiten", "Prepare a round"),
              ("höchstens vier Werkzeug-Runden", "at most four tool rounds"),
              ("Angeboten wird die Liste ohne gesperrte, wegen Fehlern gestoppte oder zu oft genutzte Werkzeuge. "
               "Verlangt die Frage ein Werkzeug, muss das Modell eines wählen (tool_choice), mit eigener Temperatur. "
               "Die fünfte Runde hat keine Liste mehr: das Modell hört, dass es jetzt antworten soll. Geräte ohne "
               "Bildschirm (Lautsprecher, Telefon, Uhr, Siri, Android-Assistent, CarPlay) bekommen höchstens "
               "{chat.SPOKEN_MAX_TOKENS} Tokens; eine längere Antwort endet am letzten ganzen Satz. Gibt ein Werkzeug "
               "den festen Satz des Panels zurück (Sofort-Karte von Finden: ein Treffer klar vorn), endet die Antwort "
               "dort: gezeigt wird der ganze Satz, gesprochen seine kurze Form, das Modell wird nicht mehr gefragt.",
               "Offered is the list without locked tools, tools stopped after errors or used too often. When the "
               "question needs a tool, the model must choose one (tool_choice), with its own temperature. The fifth "
               "round has no list: the model is told to answer now. Devices without a screen (speaker, phone, watch, "
               "Siri, Android assistant, CarPlay) get at most {chat.SPOKEN_MAX_TOKENS} tokens; a longer answer ends at "
               "its last full sentence. When a tool hands back the panel's fixed sentence (Find's Sofort-Karte: one hit "
               "clearly ahead), the answer ends there: the whole sentence is shown, its short form spoken, the model "
               "is not asked again.")),
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
               "zitierte Name in jeder Datenantwort. Mit „Rechnen mit festem Werkzeug“ rechnet rechnen.fix vorher jede "
               "Rechnung im Satz nach, auch mit Zahlwörtern („17 mal 23 ist 381“, „sechs mal sechs ist 35“) und setzt das Ergebnis des Panels ein; seine Ergebnisse "
               "zählen hier als belegt (answercheck.calc_facts). Solange das an ist, kommt jeder Satz erst fertig.",
               "For data questions answercheck compares every time, date, score and amount in the sentence with "
               "everything the model was given. After a calendar read only figures from this answer count, not from "
               "earlier ones; a quoted appointment title must be in the result. With „Extended answer check“ also "
               "temperatures, km and percentages (rounded counts, answercheck.MORE_SLACK) and every quoted name in "
               "every data answer. With „Exact calculations“ rechnen.fix first computes every calculation in the "
               "sentence again, number words too („17 times 23 is 381“, „six times six is 35“) and puts in the panel's result; its results count as proven here "
               "(answercheck.calc_facts). While that is on, every sentence comes only when it is complete."),
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
               "fasst nach dem ersten Satz alles Wartende zu einem Stück zusammen, damit die Stimme ruhig bleibt. Hat "
               "der Hörer noch mehr als {chat.FOLGE_LEAD} s Ton, geht ein solches Stück als Folgesatz "
               "(X-Spark-Folgesatz) und lässt erste Sätze anderer Antworten vor.",
               "A checked sentence goes to the device as text and into the speech output queue; code blocks are only "
               "shown. A sentence already said in an earlier round is left out. After the first sentence speech output "
               "joins everything waiting into one piece, so the voice stays calm. When the listener still has more "
               "than {chat.FOLGE_LEAD} s of audio, such a piece goes as a follow-up sentence (X-Spark-Folgesatz) and "
               "lets first sentences of other answers go first.")),
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
               "die Gruppe des ersten Werkzeugs und das feste Hinweiswort (weiche.learn), nie ein Wort der Frage. "
               "Lesende Werkzeuge (Kalender, Wetter, Pakete) nehmen ihre Daten aus dem Speicher ihres Dienstes, solange "
               "sie frisch genug sind (Vorrat je Profil, vorrat.take); ein älterer Stand wartet höchstens {vorrat.WAIT} s "
               "auf den Server und kommt sonst mit Stand und Tag („Stand gestern 18:00“, frisch.stand), „schau nochmal nach“ fragt immer den Server. Jede "
               "Antwort hält fest, wie lange die Werkzeuge warteten und woher jeder Dienst kam (latency, Zustand → Prüfen).",
               "Half words before the call are taken back, a finished sentence stays. Every call goes through "
               "chat_tools.run; the result comes back as a tool message. A tool that fails twice the same way is "
               "stopped for this answer. When no rule recognized the question, the switch counts the group of the "
               "first tool and the fixed hint word (weiche.learn), never a word of the question. Reading tools (calendar, "
               "weather, parcels) take their data from their service's memory while it is fresh enough (Vorrat je "
               "Profil, vorrat.take); an older reading waits at most {vorrat.WAIT} s for the server and otherwise comes "
               "with its time and day („as of yesterday 18:00“, frisch.stand), „look again“ always asks the server. Every answer keeps how long the tools waited "
               "and where each service came from (latency, Status → Checks)."),
              ("zurueck", ("nächste Runde", "next round"), "s4")),
            S("s12", "schritt", ("Ehrliche Schlusssätze", "Honest closing sentences"),
              ("feste Sätze statt der weggelassenen", "fixed sentences instead of the dropped ones"),
              ("Fiel ein Satz wegen einer Zahl weg, sagt das Panel „Genauere Angaben dazu habe ich nicht.“; fiel eine "
               "Tat weg, einen festen Satz aus taten.sentence. Kam ein Dienst nur mit einem älteren Stand, fand eine Suche nach Heutigem "
               "nichts von heute oder stammt ein Archiv-Artikel aus einem Kiwix-Buch, das älter als ein Jahr ist, und die Antwort sagt das nicht selbst, hängt das Panel „Nicht ganz aktuell: Wetter: Stand gestern "
               "23:10 Uhr.“ an (frisch.nachsatz, Regel „Stand nennen“ der Antwort-Prüfung). Alle Sätze kommen vom Panel, nie vom Modell. Antwortet das "
               "Sprachmodell nicht, weil es gerade wechselt, neu startet oder gemessen wird, sagt das Panel das mit der "
               "erwarteten Zeit (llmstart.satz, auch in der Wartungspause eines Wechsels).",
               "When a sentence fell out because of a figure, the panel says „I have no more precise details on "
               "that.“; when a deed fell out, a fixed sentence from taten.sentence. When a service came only with an "
               "older reading, a search for today found nothing of today or an archive article comes from a Kiwix book older "
               "than a year, and the answer does not say so itself, the panel "
               "adds „Not quite current: weather: as of yesterday 23:10.“ (frisch.nachsatz, rule „name the stand“ of the "
               "answer check). All of them come from the panel, never from the model. When the language model does not answer because it is switching, restarting or "
               "being measured, the panel says so with the expected time (llmstart.satz, also during a switch's "
               "maintenance pause).")),
            S("s13", "schritt", ("Nachfragen des Panels", "The panel's own questions"),
              ("Korrektur, Gedächtnis, reMarkable, Vorab holen", "correction, memory, reMarkable, fetch ahead"),
              ("Nur wenn nichts Fremdes gelesen wurde: eine gelernte Korrektur zum Merken anbieten oder ein Fakt aus "
               "dem Gedächtnis nachfragen (nach festen Regeln). Danach legt das Panel die Antwort aufs reMarkable, wenn "
               "gewünscht; bietet die Antwort selbst an, sich dort hinzulegen, wartet sie auf ein „Ja“ "
               "(remarkable.propose). Es holt bei einer Rückfrage schon vorab. Ist „Das kannst du auch sagen“ an, hängt das Panel "
               "feste Beispielsätze an (saetze.row, am Bildschirm als Zeile vor dem Ende; saetze.spoken, beim Sprechen "
               "höchstens ein Satz am Tag). Ist „Natürliches Gespräch“ an, kann davor nach einer gesprochenen Antwort ohne "
               "Werkzeug ein fester Hinweis aus eigenen Daten kommen (chat_modell.gespraechshinweis: die Art nach festen "
               "Wörtern der eigenen Sätze, gespraech.pick; nur Zahlen und Uhrzeiten ohne Netz, gespraech.satz; ein „Ja“ "
               "darauf wird eine feste Frage, gespraech.answer); dann kein Beispielsatz. Das Werkzeug-Log des Profils "
               "wird geschrieben.",
               "Only when nothing from outside was read: offer to remember a learned correction or ask about a fact in "
               "memory (by fixed rules). Then the panel puts the answer on the reMarkable when asked; when the answer itself offers to "
               "go there, it waits for a „yes“ (remarkable.propose). It fetches ahead "
               "for a question back. When „You can also say“ is on, the panel adds fixed example sentences (saetze.row, "
               "on a screen as a row before the end; saetze.spoken, while talking at most one sentence a day). When "
               "„Natural conversation“ is on, a spoken answer without a tool may get one fixed hint from the profile's "
               "own data before that (chat_modell.gespraechshinweis: the kind by fixed words of the person's own "
               "sentences, gespraech.pick; only numbers and times without the network, gespraech.satz; a „yes“ to it "
               "becomes a fixed question, gespraech.answer); then no example sentence. The profile's tool log is "
               "written.")),
            S("s14", "ende", ("Strom endet", "Stream ends"),
              ("Anfrage-Verlauf, Fälle, „done“", "request trace, cases, „done“"),
              ("Der Anfrage-Verlauf wird abgeschlossen, Fälle und die Prüfung im Hintergrund laufen erst nach dem "
               "Sprechen. Bricht das Gerät ab (Unterbrechen, Stopp), stoppen Modell und Sprachausgabe sofort. Solange "
               "die Antwort läuft, steht sie in laufend: Notaus Stufe 3 beendet sie mit dem Ereignis „ende“, das Gerät "
               "hört dann auf und öffnet das Mikrofon nicht wieder. Stützt sich die "
               "Antwort auf mindestens zwei eigene Dokumente oder Kiwix-Artikel, merkt wissensbuch.keep_offer sie und "
               "das Gerät zeigt „Ins Wissensbuch“; nur der Klick des Besitzers legt sie ab. Ist Probleme melden für das "
               "Profil frei, merkt meldung.keep_answer Frage, Antwort, Quelle und Weg nur im Speicher (24 Stunden) und "
               "das Gerät zeigt „Melden“; „Mach ein Issue draus“ danach legt den Bericht zu genau dieser Antwort an.",
               "The request trace is closed; cases and the background check run only after speaking. When the device "
               "aborts (barge-in, stop), model and speech output stop at once. While the answer runs it is listed in "
               "laufend: kill switch stage 3 ends it with the event „ende“, the device then stops and does not open the "
               "microphone again. When the answer rests on at least two own "
               "documents or Kiwix articles, wissensbuch.keep_offer keeps it and the device shows „To the knowledge "
               "book“; only the owner's click files it. When Reporting problems is released for the profile, "
               "meldung.keep_answer keeps question, answer, source and way in memory only (24 hours) and the device shows "
               "„Report“; „Mach ein Issue draus“ afterwards makes the report for exactly this answer.")),
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
            ("{vorrat.WAIT} s", ("wartet ein Werkzeug höchstens auf den Server, wenn ein älterer Stand da ist",
                                 "a tool waits at most for the server when an older reading is at hand"), "vorrat.WAIT"),
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
             "Vorschlag als Karte mit Ja und Nein, sonst eine Rückfrage am Ende mit ihren Antworten als Knöpfen (ablauf.asks); "
             "nur Namen und Zahlen, nie Ergebnisse.",
             "Below the answer (Features → Show steps and approvals): every tool with ✓/⚠ and time, a waiting proposal as a "
             "card with Yes and No, else a question at the end with its answers as buttons (ablauf.asks); only names and numbers, "
             "never results."),
        ],
        "code": [
            ("chat.chat", ("Rate-Limit, Sprache zuerst, „antwortet gerade“", "rate limit, speech first, „answering“")),
            ("chat._answer", ("führt Modellseite, Sprachausgabe und Ereignisse zu einem Strom zusammen", "joins model side, speech output and events into one stream")),
            ("laufend.add", ("die laufende Antwort für Notaus Stufe 3", "the running answer for kill switch stage 3")),
            ("chat_ton.speech_out", ("Sätze an die Sprachausgabe, Ton als Strom", "sentences to the speech output, sound as a stream")),
            ("chat_modell.model_turn", ("Runden mit dem Modell, Werkzeuge, Prüfungen", "rounds with the model, tools, checks")),
            ("chat_modell.herkunft_und_chip", ("Herkunftszeile und „Auch im Internet suchen“ unter der Antwort", "line of origin and „Also search the web“ under the answer")),
            ("chat_modell.quellenangabe_zeile", ("Quellenangabe unter der Antwort, am Lautsprecher kurz gesprochen", "source note under the answer, said briefly at a speaker")),
            ("chat.split_sentences", ("schneidet fertige Sätze ab", "cuts finished sentences off")),
            ("chat.said_key", ("erkennt einen schon gesagten Satz", "spots a sentence already said")),
            ("chat.no_code", ("Codeblöcke nur zeigen, nie sprechen", "code blocks only shown, never spoken")),
            ("chat.loop_count", ("zählt Fehlschläge für Fehlerschleife stoppen", "counts failures for stop error loops")),
            ("answercheck.known", ("alle Angaben, die das Modell bekommen hat", "every figure the model was given")),
            ("answercheck.unsupported", ("Angaben im Satz ohne Beleg", "figures in the sentence without proof")),
            ("answercheck.fresh", ("nach dem Kalender nur Angaben dieser Antwort", "after the calendar only this answer's figures")),
            ("rechnen.fix", ("Rechnungen im Satz nachrechnen und berichtigen", "compute calculations in the sentence again and correct them")),
            ("taten.check", ("Tat behauptet, aber kein Werkzeug hat es geschafft", "deed claimed, no tool managed it")),
            ("taten.announces", ("Werkzeugaufruf oder Tat nur angekündigt", "tool call or deed only announced")),
            ("taten.sentence", ("der feste ehrliche Satz", "the fixed honest sentence")),
            ("frisch.nachsatz", ("Stand-Hinweis, wenn etwas nicht aktuell war", "stand note when something was not current")),
        ],
        "tests": ["test_panel", "test_taten", "test_handlungsregel", "test_fast_start", "test_morgen_termine", "test_tagesaktuell"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Werkzeuge (chat_tools.run)
    "werkzeuge": {
        "stand": "b1b794d0b2",
        "bezug": {
            "chat.LOCKED_OUTSIDE": ["s4"], "notaus.INTERNET_TOOLS": ["s3"], "werkzeuge.NAMES": ["s11"],
            "chat_tools.run": ["s2", "s7"], "chat.wrap_outside": ["s9"], "chat.LOCKED_AFTER_MAIL": ["s4"],
            "chat.READS_OUTSIDE": ["s4", "s6"], "notaus.locked_tools": ["s3"], "dienstwacht.tool_down": ["s5"],
            "chat.tool_info": ["s11"], "werkzeuge.label": ["s11"], "regeln": ["s4"], "intent.forget_ok": ["s7"],
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
               "nicht mehr. Gedächtnis-Notizen sind auf {chat.MAX_SAVES} pro Antwort begrenzt; ist das Gedächtnis voll "
               "(nur Gesagtes oder Bestätigtes, profiles._cap), antwortet memory_save „Not done“ mit dem Weg zum Aufräumen. "
               "Was memory_save behält, steht als „Gemerkt: …“ mit „Rückgängig“ unter der Antwort (Gemerkt-Hinweis).",
               "At most {chat.MAX_CALLS} calls per round run, and a tool stopped after errors does not run again. Memory "
               "notes are limited to {chat.MAX_SAVES} per answer; when the memory is full (only things said or confirmed, "
               "profiles._cap), memory_save answers „Not done“ with the way to tidy up. "
               "What memory_save keeps stands as „Remembered: …“ with „Undo“ under the answer (Remembered note).")),
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
               "Termine oder Erinnerungen ändern. Nach einer Mail ist auch alles zu, was ins Internet fragt (Websuche, "
               "Wikipedia, Wetter, Fahrplan), nach eigenen Dokumenten die Websuche "
               "ebenfalls (außer bei „Erst lokal suchen“, dann nur mit den eigenen Worten der Frage; hat das Panel sie "
               "vorab schon gesucht, kommt dieses Ergebnis). Eine Mail unter den Treffern von „Erst lokal“ sperrt wie "
               "eine gelesene Mail. Nach jedem anderen Text von außen geht ein Werkzeug ins Internet nur noch mit Wörtern "
               "aus der eigenen Nachricht oder aus dem, was eine Suche dieser Antwort brachte (ausleiten.py). Ein Lied, das die "
               "Person selbst wünscht, bleibt nach Text von außen offen (own), nach Mail nicht.",
               "When this answer already read text from outside, nothing may change the home, the memory, "
               "appointments or reminders any more. After a mail everything that asks the internet is closed too (web "
               "search, Wikipedia, weather, transit), after own documents the web search "
               "(except with „search locally first“, then only with the question's own words; when the panel searched "
               "them before, that result comes). A mail among the hits of „local first“ locks like a read mail. After any "
               "other outside text a tool goes to the internet only with words from the own message or from what a search "
               "of this answer brought (ausleiten.py). A song "
               "the person asks "
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
               "fremder Text. Eine Stelle ohne die gefragten Wörter fällt weg (lokal.cover); bleibt keine, kommt der feste "
               "Satz chat_tools.NOTHING_FITS statt fremder Stellen. Eine Mappe (aus den eigenen Worten oder der Bindung "
               "des Gesprächs, mappen.fuer_werkzeug) begrenzt document_search und fund_suche auf ihre Einträge auf „ganz“.",
               "Tools that bring outside text (web search, documents, calendar, earlier conversations, camera) set the "
               "mark before they run. From then on the locks of step 4 hold for the rest of the answer. With the "
               "knowledge book document_search brings the fitting page first, then the passages; both are outside text. "
               "A passage without the words asked for drops out (lokal.cover); if none is left, the fixed sentence "
               "chat_tools.NOTHING_FITS comes instead of unrelated passages. A collection (from the own words or the "
               "conversation's binding, mappen.fuer_werkzeug) narrows document_search and fund_suche to its entries set "
               "to whole.")),
            S("s7", "schritt", ("Werkzeug ausführen", "Run the tool"),
              ("Erweiterung oder eingebautes Werkzeug", "extension or built-in tool"),
              ("Erweiterungen bekommen Profil, Gerät und Herkunft vom Panel, nie vom Modell. Smart-Home-Änderungen "
               "brauchen das Codewort in der letzten Nachricht, wenn eines eingestellt ist. Verbindungen zu Diensten "
               "draußen gehen über den Wächter. Home Assistant liest Zustände aus der Kopie der Live-Verbindung "
               "(halive.states), solange sie für genau diese Adresse und diesen Schlüssel steht, sonst über HTTP. Den "
               "Zeitraum der Websuche bestimmen die eigenen Worte der Frage und die Suchwörter (frisch.zeitraum), nie "
               "die Zeitangabe des Panels. Eine Erweiterung kann statt einer Antwort des Modells den festen Satz des "
               "Panels übergeben (ctx „fest“, die Sofort-Karte von Finden); das Modell formuliert ihn nie um. "
               "memory_forget löscht nur, wenn die eigene letzte Nachricht ums Vergessen bittet und es weder abruft noch "
               "verneint (intent.forget_ok); ein verneinter Smart-Home-Befehl erreicht Home Assistant nie.",
               "Extensions get profile, device and origin from the panel, never from the model. Smart home changes need "
               "the code word in the latest message when one is set. Connections to outside services go through the "
               "guard. Home Assistant reads states from the live connection's copy (halive.states) while it stands for "
               "exactly this address and key, else over HTTP. The period of the web search comes from the question's own "
               "words and the query (frisch.zeitraum), never from the panel's time note. An extension can hand over the "
               "panel's fixed sentence instead of a model answer (ctx „fest“, Find's Sofort-Karte); the model never "
               "rewords it.")),
            S("s8", "schritt", ("Fehler als Satz", "Errors as a sentence"),
              ("„nicht erreichbar“, nie raten", "„not reachable“, never guess"),
              ("Ist ein Dienst nicht erreichbar, wird daraus ein kurzer Ergebnis-Text („nicht erreichbar“, „Suche "
               "fehlgeschlagen, nicht raten“). Ein angebotenes Werkzeug ohne passende Einrichtung meldet „unbekannt“.",
               "When a service cannot be reached, it becomes a short result text („not reachable“, „search failed, do "
               "not guess“). An offered tool without a matching setup answers „unknown“.")),
            S("s9", "schritt", ("Ergebnis als Daten einpacken", "Wrap the result as data"),
              ("Hinweis „Daten, kein Befehl“, Block <<< >>>", "note „data, no command“, block <<< >>>"),
              ("Fremder Text bekommt einen festen Hinweis davor und steht zwischen Markierungen, die er selbst nicht "
               "schließen kann; die eigenen Marken des Modells („<|im_start|>“, „<tool_call>“) werden darin entschärft "
               "(textnorm.defuse). Zustände aus Home Assistant mit freiem Text (Titel, Listen, ein Zustand aus Wörtern) "
               "zählen auch als fremd. Mit "
               "„Schnellere Websuche“ steht der lange Hinweis einmal je Antwort, vor jedem weiteren Block ein kurzer "
               "mit derselben Regel (chat.OUTSIDE_AGAIN); die Markierungen bleiben immer.",
               "Outside text gets a fixed note in front and stands between markers it cannot close itself; the model's own "
               "markers („<|im_start|>“, „<tool_call>“) in it are defused (textnorm.defuse). Home "
               "Assistant states with free text (titles, lists, a state made of words) count as outside too. With „Faster web search“ the long "
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
             "Features → Routing: which tools the model sees for a question at all."),
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
            ("intent.forget_ok", ("memory_forget nur auf das eigene Wort zum Vergessen", "memory_forget only on the own word to forget")),
            ("chat_modell.model_turn", ("ruft run_tool, packt Ergebnisse ein, stoppt Schleifen", "calls run_tool, wraps results, stops loops")),
            ("chat.wrap_outside", ("fremder Text als Datenblock", "outside text as a data block")),
            ("chat.LOCKED_OUTSIDE", ("gesperrt nach fremdem Text", "locked after outside text")),
            ("chat.LOCKED_AFTER_MAIL", ("gesperrt nach einer Mail", "locked after a mail")),
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
