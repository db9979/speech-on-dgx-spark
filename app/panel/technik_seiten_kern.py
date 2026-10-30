"""Zustand → Technik, Knoten-Seiten: the pages of language model, own knowledge and operation
(llm, wissen, betrieb). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "llm": {
        "stand": "4369c7ec11",
        "bezug": {
            "chat.chat": ["s1"], "chat._answer": ["s2", "s4", "s6"], "llm.model": ["s3"], "llm.url": ["s1"], "llm.complete": ["s1"],
            "chat.sampling": ["s4"], "chat.first_within": ["s8"], "chat.ContextFull": ["s7"],
            "chat.llm_error_code": ["s12"], "chat.LLM_GONE": ["s12"], "chat.prompt_sizes": ["s11"],
            "stufe.wait_turn": ["s5"], "vorrang.run": ["s1"], "wartung.paused": ["s1w"], "wartung.sentence": ["s1w"], "wartung.MAX_MIN": ["s1w"],
            "verbrauch.llm": ["s11"], "verbrauch.over": ["s5"], "verbrauch.warn": ["s11"],
            "wartung.auto_tick": ["s1w"], "wartung.AUTO_MIN": ["s1w"],
        },
        "kurz": ("Das Sprachmodell schreibt die Antworten: das eigene hinter dem LLM-Tor oder qwen38 aus dgx-spark-qwen38 "
                 "(nicht Teil dieses Repos). Das "
                 "Panel spricht es an der eingestellten Adresse über die OpenAI-Schnittstelle an, gestreamt, und sorgt "
                 "dafür, dass Sprache immer vor Hintergrundarbeit kommt. Adresse, Schlüssel und Modellname stehen nur in llm.py; "
                 "jede Hintergrundaufgabe fragt über llm.complete. Mit Funktionen → Hilfsmodell → Für kurze Texte "
                 "schreibt die Aufträge aus llm.HELFER_JOBS erst das kleine Hilfsmodell, sonst sofort das große.",
                 "The language model writes the answers: the own one behind the LLM-Tor or qwen38 from dgx-spark-qwen38 "
                 "(not part of this repo). The panel "
                 "talks to it at the configured address through the OpenAI interface, streamed, and makes sure speech "
                 "always comes before background work. Address, key and model name live only in llm.py; every "
                 "background job asks through llm.complete. With Features → Helper model → For short texts the small "
                 "helper model writes the jobs in llm.HELFER_JOBS first, else the big one at once."),
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
            S("s1w", "frage", ("Wartungspause?", "Maintenance pause?"),
              ("Zustand → Wartungspause", "Status → Maintenance pause"),
              ("Hat ein Admin das Sprachmodell für ein Update angehalten, fragt das Panel es gar nicht erst: die Antwort "
               "ist sofort ein fester Satz mit der Restzeit, auch die Weiche und System One fragen nicht. "
               "Hintergrundarbeit am Modell wartet, bis die Pause endet, und zählt das nicht als Abbruch. Am Ende der "
               "Zeit endet die Pause erst, wenn das Modell {wartung.OK_N}-mal hintereinander antwortet. Mit „Automatisch bei "
               "Neustart“ pausiert das Panel selbst, sobald ein Dienst des Sprachmodells (eigenes oder qwen38) neu startet oder umschaltet (höchstens "
               "{wartung.AUTO_MIN} min), und macht weiter, sobald das Modell wieder antwortet. Läuft das Modell auf einem "
               "anderen Rechner, der nicht antwortet (Notbetrieb, steuer.weg), gilt dasselbe mit dem Satz „Der Spark macht "
               "gerade Pause.“; der Dienst-Wächter meldet den Ausfall trotzdem. Mit Funktionen → Notbetrieb mit Parakeet "
               "hört dann Parakeet auf dem Panel-Rechner, und feste Befehle (Home Assistant, Uhrzeit, Erinnerungen) "
               "gehen ohne Modell (notbetrieb.antwort).",
               "When an admin paused the language model for an update, the panel does not ask it at all: the answer is "
               "a fixed sentence with the time left at once, the Weiche and System One do not ask either. Background "
               "work on the model waits until the pause ends and does not count that as a cancel. At the end of the "
               "time the pause only ends once the model answers {wartung.OK_N} times in a row. With “Automatically on "
               "restart” the panel pauses by itself as soon as a language model service (own or qwen38) restarts or switches (at most "
               "{wartung.AUTO_MIN} min) and goes on once the model answers again. When the model runs on another "
               "computer that does not answer (emergency mode, steuer.weg), the same holds with the sentence “The Spark "
               "is taking a break right now.”; the Dienst-Wächter still reports the outage. With Features → Emergency "
               "mode with Parakeet, Parakeet on the panel computer then hears, and fixed commands (Home Assistant, time, "
               "reminders) work without a model (notbetrieb.antwort)."),
              ("stop", "ja", ("„Ich werde gerade aktualisiert …“", "„I am being updated right now …“"))),
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
              ("Die Anfrage streamt, mit Länge, Temperatur, top_p, top_k und presence_penalty aus den Einstellungen "
               "(0 = Standard des Servers; der Qualitätstest vergleicht mit der Qwen-Empfehlung). Denken ist "
               "aus, außer „Vorher nachdenken“ ist an. Während der Werkzeugwahl gilt die eigene Temperatur dafür. Der "
               "Server meldet am Ende immer, wie viel er gelesen und geschrieben hat und wie viel aus seinem "
               "Zwischenspeicher kam.",
               "The request streams, with length, temperature, top_p, top_k and presence_penalty from the settings (0 = "
               "the server's default; the quality test compares with Qwen's recommendation). Thinking is "
               "off unless „Think first“ is on. While a tool is chosen its own temperature applies. The server always "
               "reports at the end how much it read and wrote and how much came from its cache.")),
            S("s5", "frage", ("Wartet jemand mit Vorrang?", "Someone with priority waiting?"),
              ("Vorrang für Personen", "priority for people"),
              ("Hat eine andere Person Vorrang und ihre Antwort noch keinen ersten Satz, wartet diese Runde höchstens "
               "die eingestellte Zeit (bis {stufe.WAIT_RANGE.1} Sekunden). Eine Antwort mit Vorrang hält andere "
               "höchstens {stufe.FIRST_MAX} Sekunden auf. Davor prüft das Panel das Kontingent (Tag, Woche, Monat): ein "
               "Profil darüber bekommt einen festen Satz statt einer Antwort, feste Befehle ohne Modell gehen weiter.",
               "When another person has priority and their answer has no first sentence yet, this round waits at most "
               "the configured time (up to {stufe.WAIT_RANGE.1} seconds). An answer with priority holds others up "
               "for at most {stufe.FIRST_MAX} seconds. Before that the quota (day, week, month) is checked: a profile "
               "over it gets a fixed sentence instead of an answer, fixed commands without a model still work."),
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
               "Systemprompt, Werkzeugliste und Verlauf, Zeit bis zum ersten Wort, Wartezeit wegen Vorrang. Der "
               "Verbrauchszähler zählt gelesene und geschriebene Tokens je Aufgabe und Profil (ohne Meldung des Servers "
               "geschätzt, rund {verbrauch.CHARS_PER_TOKEN} Zeichen je Token).",
               "For the request trace only numbers count: tokens read, of them from the cache, size of system prompt, "
               "tool list and history, time to the first word, waiting time for priority. The usage counter counts "
               "tokens read and written per task and profile (estimated without the server's report, about "
               "{verbrauch.CHARS_PER_TOKEN} characters per token).")),
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
            (("Sprachmodell hängt", "Language model hangs"), ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s8!"],
             ("„Mein Sprachmodell antwortet gerade nicht.“ statt Stille.", "„My language model is not answering right now.“ instead of silence.")),
            (("Sprachmodell wird neu eingespielt", "Language model is being updated"), ["s1", "s1w", "s1w!"],
             ("„Ich werde gerade aktualisiert und bin in etwa 20 Minuten wieder da.“", "„I am being updated right now and will be back in about 20 minutes.“")),
        ],
        "zahlen": [
            ("{chat.FIRST_WAIT} s", ("bis zur ersten Zeile des Modells", "until the model's first line"), "chat.FIRST_WAIT"),
            ("{chat.TIMEOUT_RANGE.0} bis {chat.TIMEOUT_RANGE.1} s", ("erlaubtes Zeitlimit", "allowed time limit"), "chat.TIMEOUT_RANGE"),
            ("{vorrang.GRACE} s", ("nach Sprache wartet Hintergrundarbeit noch", "background work still waits after speech"), "vorrang.GRACE"),
            ("{vorrang.RETRIES}", ("Abbrüche, bis Hintergrundarbeit aufgibt", "cancels until background work gives up"), "vorrang.RETRIES"),
            ("{stufe.WAIT_RANGE.1} s", ("längste Wartezeit für Vorrang", "longest wait for priority"), "stufe.WAIT_RANGE"),
            ("{stufe.FIRST_MAX} s", ("so lange hält eine Antwort mit Vorrang höchstens auf", "a priority answer holds up at most this long"), "stufe.FIRST_MAX"),
            ("{wartung.MIN_MIN} bis {wartung.MAX_MIN} min", ("Dauer einer Wartungspause", "length of a maintenance pause"), "wartung.MAX_MIN"),
            ("{wartung.AUTO_MIN} min", ("längste automatische Pause, bevor sie als Ausfall zählt", "longest automatic pause before it counts as an outage"), "wartung.AUTO_MIN"),
        ],
        "einstellen": [
            ("Einstellungen → Sprachmodell: Adresse, Schlüssel und Modell; dazu Vorher nachdenken, Temperatur und Länge "
             "einer Antwort.",
             "Settings → Language model: Address, Key and Model; also Think first, Temperature and Length of an answer."),
            ("Einstellungen → Sprachmodell, unter Erweitert: Zeitlimit für eine Antwort.",
             "Settings → Language model, under Advanced: Time limit for an answer."),
            ("Funktionen → Vorrang für Personen: ausgewählte Profile bekommen ihre Antwort zuerst.",
             "Features → Priority for people: chosen profiles get their answer first."),
            ("Zustand → Wartungspause: das Sprachmodell vor einem Update anhalten (auch sudo speech-spark pause llm 30).",
             "Status → Maintenance pause: pause the language model before an update (also sudo speech-spark pause llm 30)."),
            ("Funktionen → Verbrauchszähler: zählt Tokens je Modell, Aufgabe und Profil; darunter das Kontingent "
             "je Profil für Tag, Woche und Monat.",
             "Features → Usage counter: counts tokens per model, task and profile; below it the quota per profile for "
             "day, week and month."),
            ("Funktionen → Wartungspause → Automatisch bei Neustart: pausiert von selbst, wenn das Sprachmodell neu startet.",
             "Features → Maintenance pause → Automatically on restart: pauses by itself when the language model restarts."),
        ],
        "sehen": [
            ("Zustand → Logs → Erweitert → Gespräch: pro Runde gelesene Tokens, davon aus dem Zwischenspeicher, und "
             "die Zeit bis zum ersten Wort.",
             "Status → Logs → Advanced → Conversation: per round tokens read, of them from the cache, and the time to "
             "the first word."),
            ("Zustand → Verbrauch: Tokens je Tag, Modell, Bereich und Profil.",
             "Status → Usage: tokens per day, model, area and profile."),
            ("Unter der Antwort (Ablauf und Freigabe zeigen): die Werkzeuge der Runden mit Name, ✓/⚠ und Zeit.",
             "Below the answer (Show steps and approvals): the tools of the rounds with name, ✓/⚠ and time."),
            ("Zustand → Prüfen → Vorrang für Sprache: ob die Sprachausgabe flüssig bleibt, während das Modell rechnet.",
             "Status → Checks → Speech first: whether speech output stays smooth while the model computes."),
            ("Spark teilen: Läuft das Panel auf einem anderen Rechner, stehen Sprachmodell, Spracherkennung, Sprachausgabe "
             "und Bilder auf dem Modell-Rechner (Zustand → Live, Kasten „Modell-Rechner“); das Panel erreicht sie nur über "
             "das TLS-Tor mit festem Zertifikat und steuert sie über den Wärter.",
             "Spark split: when the panel runs on another computer, language model, speech recognition, speech output "
             "and pictures are on the model computer (Status → Live, box \"Model computer\"); the panel reaches them only "
             "through the TLS-Tor with a pinned certificate and controls them through the Wärter."),
        ],
        "code": [
            ("chat.chat", ("setzt „Sprache läuft“ bei jedem Stück", "sets „speech is running“ with every piece")),
            ("chat._answer", ("Verbindung, Anfrage, Runden (llm_round), Fehlerfälle", "connection, request, rounds (llm_round), errors")),
            ("llm.model", ("Modellname aus Einstellung oder /models", "model name from settings or /models")),
            ("llm.url", ("die eine Adresse des Sprachmodells", "the one address of the language model")),
            ("llm.complete", ("Aufruf jeder Hintergrundaufgabe, wartet in vorrang", "the call of every background job, waits in vorrang")),
            ("chat.sampling", ("top_p, top_k und presence_penalty", "top_p, top_k and presence_penalty")),
            ("chat.first_within", ("die erste Zeile muss rechtzeitig kommen", "the first line must come in time")),
            ("chat.ContextFull", ("Anfrage länger als der Kontext", "request longer than the context")),
            ("chat.llm_error_code", ("Fehler als festes Kürzel", "error as a fixed code")),
            ("chat.LLM_GONE", ("der gesprochene Satz, wenn das Modell fehlt", "the spoken sentence when the model is gone")),
            ("chat.prompt_sizes", ("Größe der Teile einer Anfrage", "size of the parts of a request")),
            ("stufe.wait_turn", ("wartet auf eine Antwort mit Vorrang", "waits for an answer with priority")),
            ("vorrang.mark", ("Marke „Sprache läuft“", "mark „speech is running“")),
            ("vorrang.run", ("Hintergrundarbeit weicht der Sprache", "background work gives way to speech")),
            ("wartung.paused", ("Wartungspause: das Modell wird nicht gefragt", "maintenance pause: the model is not asked")),
            ("wartung.auto_tick", ("Wartungspause von selbst, wenn das Sprachmodell neu startet", "maintenance pause by itself when the language model restarts")),
            ("wartung.sentence", ("der feste Satz mit der Restzeit", "the fixed sentence with the time left")),
            ("verbrauch.llm", ("zählt Tokens einer Runde", "counts the tokens of a round")),
            ("verbrauch.over", ("welche Grenze ist voll: Tag, Woche oder Monat?", "which limit is full: day, week or month?")),
            ("verbrauch.warn", ("Vorwarnung unter der Antwort, einmal je Zeitraum", "the warning under the answer, once per period")),
        ],
        "tests": ["test_panel", "test_llm_settings", "test_vorrang", "test_stufe", "test_fast_start", "test_wartung"],
        "heute": [("vb_llm_calls", ("Anfragen", "requests")), ("vb_llm_in", ("Tokens gelesen", "tokens read")),
                  ("vb_llm_out", ("Tokens geschrieben", "tokens written"))],
    },
    # ------------------------------------------------------------------ Wissen: how a question finds passages
    "wissen": {
        "stand": "fce761974e",
        "bezug": {
            "lokal.MAX_HITS": ["s5"], "wissen.search": ["s1", "s8", "s9"], "documents.search": ["s5", "s6"],
            "documents._terms": ["s5"], "documents.match_docs": ["s4"], "docembed.query": ["s3"],
            "docembed._call": ["s3"], "nachsortieren.rank": ["s10"], "wissen.recent_window": ["s11"], "frisch.spanne": ["s11"],
            "fund.pruefe": ["s13"], "fund.sofort_satz": ["s13"], "fund.klar_vorn": ["s13"],
            "wissen.where": ["s13"], "lokal.look": ["s5"], "gedaechtnis.hint_lines": ["s13"], "profiles._cap": ["s13"],
            "gedaechtnis.slot_of": ["s13"], "gemerkt.take_back": ["s13"],
            "regeln": ["s1", "s8"], "regel:Geteilte Dokumente": ["s8"], "regel:Gedächtnis": ["s13"],
            "regel:Erst lokal suchen": ["s5"], "regel:Wissensbuch": ["s13"], "wissensbuch.answer_block": ["s13"],
            "wissensbuch.PAGES_PER_DOC": ["s13"], "wissensbuch.MAX_PAGES": ["s13"],
            "wissensbuch.SAMPLE": ["s13"], "wissenskarte.view": ["s13"], "wissenskarte.check_edge": ["s13"],
            "wissenskarte.EDGES_PER_DOC": ["s13"], "wissenskarte.VIEW_NODES": ["s13"], "wissenskarte.VIEW_EDGES": ["s13"],
            "wissenskarte.WEG_MOST": ["s13"], "wissenskarte.rund_um": ["s13"], "wissenskarte.weg": ["s13"],
            "wissensbuch.search_pages": ["s13"], "wissensbuch._fts_sync": ["s13"], "wissensbuch.liste": ["s13"], "documents._similar": ["s6"],
            "documents.VEC_BLOCK": ["s6"], "wissenskarte.MAX_EDGES": ["s13"], "wissenskarte.DAY": ["s13"],
            "wissenskarte.check_ent": ["s13"], "wissenskarte.finde_knoten": ["s13"], "wissenskarte.knoten_liste": ["s13"],
            "wissenskarte.zusammen": ["s13"], "wissenskarte.ENT_PER_DOC": ["s13"], "wissenskarte.MAX_ENT": ["s13"],
            "wissenskarte.ENT_DAY": ["s13"], "wissenskarte.ENT_NAME_LEN": ["s13"],
            "wissenskarte.knoten_von_dok": ["s13"], "wissenskarte.liste": ["s6"], "wissenskarte.trifft": ["s6"], "documents._karte": ["s6"],
            "documents.KARTE_WEIGHT": ["s6"], "wissenskarte.KARTE_MOST": ["s6"], "wissenskarte.KARTE_KNOTEN": ["s6"],
            "regel:Wissenskarte": ["s6"],
            "pdftabellen.read": ["s5"], "documents._rows": ["s5"], "documents.due_tables": ["s5"], "lokal.excerpt": ["s5"],
            "pdftabellen.BUDGET_S": ["s5"], "documents.TABLE": ["s5"], "lokal.MAX_HIT_CHARS": ["s5"],
            "wissensmessung.lauf": ["s6"], "wissensmessung._synth": ["s6"], "wissensmessung.MESSTEILE": ["s6"],
        },
        "kurz": ("Wissen ist alles, was der Spark selbst weiß, ohne ins Internet zu gehen: die hochgeladenen Dokumente "
                 "jedes Profils (eine SQLite-Datei wissen.db pro Profil), das Gedächtnis, frühere Gespräche, das eigene "
                 "Kiwix-Archiv und erstellte Dokumente. Die Seite zeigt den Weg, auf dem eine Frage passende Stellen "
                 "in den Dokumenten findet. Finden (fund.py, eigene Datei fund.db pro Profil) legt darüber einen "
                 "Index aus Titeln, Feldern und Schlagworten nach festen Regeln und nutzt für den Text dieselbe Suche; "
                 "Mails und Anhänge (fundmail.py) liest es in ruhigen Minuten in Scheiben ein und hält sie nur "
                 "versiegelt (AES-GCM) mit ihren Wörtern als HMAC-Marken; Termine und Kontakte (fundquellen.py) "
                 "ebenso, Gespräche nur mit Datum und Kanal (ihre Wörter sucht recall.liste), Listen, Erinnerungen, "
                 "Bilder und Lieder wie ihre Quelle. Zeiträume („letzte Woche“, „2023“) rechnet frisch.spanne nach "
                 "festen Regeln, „vom OP“ sucht den letzten vergangenen Termin im eigenen Kalender (fund.bezug_aus): "
                 "14 Tage davor bis 60 danach steht weiter oben, nie eine harte Grenze. Mit „Schlagworte vom Modell“ "
                 "schlägt das Sprachmodell in ruhigen Minuten Schlagworte vor; fund.pruefe behält nur Kategorien der "
                 "festen Liste und Namen, die wörtlich im Eintrag stehen, verknüpft Personen, Firmen und Orte mit den "
                 "Punkten der Wissenskarte (nur lesend) und lässt weg, was die Person entfernt hat. Ein klarer Treffer "
                 "kommt als fester Satz des Panels (fund.sofort_satz), nie mit Worten des Modells.",
                 "Knowledge is everything the Spark knows without going to the internet: the uploaded documents of "
                 "each profile (one SQLite file wissen.db per profile), the memory, earlier conversations, the own "
                 "Kiwix archive and created documents. This page shows the way a question finds fitting passages in "
                 "the documents. Find (fund.py, its own file fund.db per profile) adds an index of titles, fields "
                 "and tags by fixed rules on top and uses the same search for the text; mail and attachments "
                 "(fundmail.py) it reads in slices in quiet minutes and keeps only sealed (AES-GCM) with their words "
                 "as HMAC marks; appointments and contacts (fundquellen.py) likewise, conversations only with date "
                 "and channel (recall.liste searches their words), lists, reminders, pictures and songs like their "
                 "source. Periods („last week“, „2023“) come from frisch.spanne by fixed rules, „from the surgery“ "
                 "looks for the last past appointment in the own calendar (fund.bezug_aus): 14 days before to 60 "
                 "after rank higher, never a hard limit. With „Tags by the model“ the language model proposes tags in "
                 "quiet minutes; fund.pruefe keeps only categories of the fixed list and names that stand in the entry "
                 "word for word, links people, companies and places to the points of the knowledge map (read only) "
                 "and leaves out what the person removed. A clear hit comes as the panel's fixed sentence "
                 "(fund.sofort_satz), never in the model's words."),
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
               "Frage. Es startet nur bei mindestens {docembed.MIN_FREE_GIB} GiB freiem Speicher (auf einem Panel-Rechner "
               "{docembed.MIN_FREE_PANEL_GIB} GiB) und endet nach "
               "{docembed.IDLE_STOP|min} Minuten ohne Arbeit. Kommt kein Vektor, sucht der Spark nur im Volltext, "
               "ohne Fehler.",
               "With meaning search a small vector model (own process, processor only) computes the question's "
               "vector. It starts only with at least {docembed.MIN_FREE_GIB} GiB free memory (on a panel computer "
               "{docembed.MIN_FREE_PANEL_GIB} GiB) and ends after "
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
               "addiert, so steigt eine Stelle, die in beiden Listen weit oben steht. Die Vektoren liegen als "
               "float16 im Speicher (halb so viel wie float32); gerechnet wird blockweise je {documents.VEC_BLOCK} "
               "Stellen in float32, die Rangfolge bleibt gleich. Neu gelesen werden sie nur, wenn sich Stellen oder "
               "genutzte Dokumente ändern; solange noch Vektoren fehlen, höchstens alle {documents.VEC_CATCHUP_S} Sekunden. "
               "Mit „Karte hilft der Suche“ kommt eine dritte Liste aus der Wissenskarte dazu (wissenskarte.liste): "
               "nennen die Suchwörter einen Punkt (Person, Firma, Ort …), zählen seine Stellen und die seiner Nachbarn, "
               "höchstens {wissenskarte.KARTE_MOST}, mit dem Gewicht {documents.KARTE_WEIGHT}; eine Stelle nur aus der "
               "Karte steht so hinter jeder, die Wörter oder Bedeutung fanden. Nur für die eigenen Dokumente.",
               "If the question has a vector, it is compared with every passage's vector. Below 0.75 similarity "
               "nothing counts as related; the best 30 above get a rank too. Both ranks are added, so a passage "
               "high in both lists rises. The vectors are kept in memory as float16 (half of float32); they are "
               "reckoned in float32 block by block, {documents.VEC_BLOCK} passages at a time, so the ranking stays "
               "the same. They are read again only when passages or used documents change; while vectors are still "
               "missing, at most every {documents.VEC_CATCHUP_S} seconds. With „Map helps the search“ a third list "
               "from the knowledge map joins (wissenskarte.liste): if the search words name a point (person, company, "
               "place …), its passages and those of its neighbours count, at most {wissenskarte.KARTE_MOST}, with the "
               "weight {documents.KARTE_WEIGHT}; a passage only from the map so stands behind every one words or "
               "meaning found. Only for the own documents.")),
            S("s7", "frage", ("Neueste zuerst?", "Newest first?"),
              ("bei reMarkable-Notizen", "with reMarkable notes"),
              ("Mit „Neueste zuerst“ bekommt eine kürzlich geänderte Stelle einen kleinen Vorsprung, etwa zwei Plätze, "
               "der mit dem Alter kleiner wird. Die Passung bleibt wichtiger; jeder Treffer trägt dann sein Datum.",
               "With „Newest first“ a passage changed lately gets a small lead, about two places, which shrinks "
               "with age. Fit stays more important; each hit then carries its date."),
              ("info", "ja", ("kleiner Vorsprung für Neues", "small lead for new pages"))),
            S("s8", "schritt", ("Geteilte Dokumente der anderen", "Shared documents of the others"),
              ("„Für alle“ oder einzeln geteilt, nur fertig gelesene", "„for everyone“ or shared singly, only fully read ones"),
              ("Mit „Gemeinsame Dokumente“ läuft dieselbe Suche in den Dateien der anderen Profile, aber nur über "
               "Dokumente, die dort „Für alle“ sind oder mit „Teilen mit Profilen“ einzeln mit diesem Profil geteilt (documents.Offer). Ist der Haushaltsordner für das Profil frei, läuft sie auch im "
               "Bestand des Haushalts (users/haushalt/). Die Treffer tragen den Namen des Besitzers oder „Haushalt“; "
               "alles wird nach Rang sortiert.",
               "With „Shared documents“ the same search runs in the other profiles' files, but only over documents "
               "marked „for everyone“ there or shared singly with this profile through „Sharing with profiles“ (documents.Offer). With the household folder released for the profile it also runs in the "
               "household's store (users/haushalt/). The hits carry the owner's name or „Haushalt“; everything is "
               "sorted by rank.")),
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
              ("Eine Stelle geht nur weiter, wenn sie mindestens {lokal.COVER} der Suchwörter enthält (Füllwörter wie "
               "„Informationen“ oder „Archiv“ zählen nicht); eine Händlerliste mit nur „Dresden“ ist keine Antwort zur "
               "Frauenkirche. Fällt so alles weg, sagt ein fester Satz: nichts Passendes, sag das und such im Archiv "
               "oder im Web, wenn angeboten. Findet die Suche nichts, waren aber Tags oder Art genannt, bekommt das "
               "Modell die Steckbrief-Zeilen der passenden Dokumente. Sonst heißt es: nichts gefunden, sag das, rate nicht.",
               "A passage only goes on when it holds at least {lokal.COVER} of the search words (filler words like "
               "„information“ or „archive“ do not count); a dealer list with only „Dresden“ is no answer about the "
               "Frauenkirche. If all drop out so, a fixed sentence says: nothing fitting, say so and look in the archive "
               "or on the web if offered. If the search finds nothing but tags or a kind were given, the model gets the "
               "card lines of the fitting documents. Otherwise: nothing found, say so, do not guess."),
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
            [("Geteilte Dokumente", "Shared documents"), ("dieselbe Suche, nur „Für alle“ oder einzeln geteilt", "the same search, only „for everyone“ or shared singly"), ("andere Profile, nie Gäste", "other profiles, never guests")],
            [("Gedächtnis", "Memory"), ("wird nicht gesucht: steht in drei Blöcken im Systemprompt", "not searched: stands in three blocks in the system prompt"), ("eigenes Profil", "own profile")],
            [("Frühere Gespräche", "Earlier conversations"), ("history_search über Wörter", "history_search by words"), ("eigenes Profil", "own profile")],
            [("Kiwix", "Kiwix"), ("archive_search und wikipedia über das eigene Kiwix im Heimnetz", "archive_search and wikipedia via the own Kiwix in the home network"), ("alle Profile, nie Gäste", "all profiles, never guests")],
            [("Erst lokal suchen", "Look locally first"), ("Volltext ohne Warten auf Modelle, vor der ersten Runde", "full text without waiting for models, before the first round"), ("wie die Werkzeuge der Anfrage", "as the request's tools")],
            [("Wissensbuch", "Knowledge book"), ("document_search: passende Seiten vor den Stellen", "document_search: fitting pages before the passages"), ("eigenes Profil, nur eigene Dokumente", "own profile, own documents only")],
            [("Wissenskarte", "Knowledge map"), ("dritte Trefferliste: Punkte, die die Frage nennt, und ihre Nachbarn", "third list of hits: points the question names and their neighbours"), ("eigenes Profil, nur eigene Dokumente in der Suche", "own profile, own documents in the search only")],
        ],
        "zahlen": [
            ("{nachsortieren.CANDIDATES}", ("Kandidaten für das Nachsortieren", "candidates for re-ranking"), "nachsortieren.CANDIDATES"),
            ("{nachsortieren.MIN_SCORE}", ("Untergrenze des Cross-Encoders", "cross-encoder's lower limit"), "nachsortieren.MIN_SCORE"),
            ("{documents.HEAD_WEIGHT}", ("Gewicht der Kontextzeile", "weight of the context line"), "documents.HEAD_WEIGHT"),
            ("{docembed.QUERY_TIMEOUT} s", ("längstes Warten auf den Fragevektor", "longest wait for the question vector"), "docembed.QUERY_TIMEOUT"),
            ("{docembed.MIN_FREE_GIB} GiB", ("freier Speicher, damit das Vektormodell startet", "free memory for the vector model to start"), "docembed.MIN_FREE_GIB"),
            ("{docembed.MIN_FREE_PANEL_GIB} GiB", ("dasselbe auf einem Panel-Rechner (Spark teilen)", "the same on a panel computer (Spark teilen)"), "docembed.MIN_FREE_PANEL_GIB"),
            ("{lokal.MAX_HITS}", ("Treffer höchstens bei „Erst lokal suchen“", "hits at most with „Look locally first“"), "lokal.MAX_HITS"),
            ("{lokal.MAX_HIT_CHARS}", ("Zeichen je Treffer bei „Erst lokal suchen“, um die Suchwörter", "characters per hit with „Look locally first“, around the search words"), "lokal.MAX_HIT_CHARS"),
            ("{documents.TABLE}", ("Zeichen, bis zu denen eine Tabelle eine Stelle bleibt", "characters up to which a table stays one passage"), "documents.TABLE"),
            ("{pdftabellen.BUDGET_S} s", ("längste Zeit je PDF für das Lesen der Tabellen", "longest time per PDF for reading its tables"), "pdftabellen.BUDGET_S"),
            ("{wissensbuch.PAGES_PER_DOC}", ("Seiten, die ein Dokument im Wissensbuch ändern darf", "pages one document may change in the knowledge book"), "wissensbuch.PAGES_PER_DOC"),
            ("{wissensbuch.MAX_PAGES}", ("Seiten im Wissensbuch pro Profil", "pages in the knowledge book per profile"), "wissensbuch.MAX_PAGES"),
            ("{wissensbuch.SAMPLE}", ("Sätze, die das Modell nachts gegen ihre Quelle prüft (Standard)", "sentences the model checks against their source at night (default)"), "wissensbuch.SAMPLE"),
            ("{wissenskarte.EDGES_PER_DOC}", ("Verbindungen, die ein Dokument in die Wissenskarte bringen darf", "connections one document may bring into the knowledge map"), "wissenskarte.EDGES_PER_DOC"),
            ("{wissenskarte.MAX_EDGES}", ("Verbindungen in der Wissenskarte pro Profil", "connections in the knowledge map per profile"), "wissenskarte.MAX_EDGES"),
            ("{wissenskarte.VIEW_NODES}", ("Punkte, die die Karte auf einmal zeigt", "points the map shows at once"), "wissenskarte.VIEW_NODES"),
            ("{wissenskarte.VIEW_EDGES}", ("Verbindungen, die die Karte auf einmal zeigt", "connections the map shows at once"), "wissenskarte.VIEW_EDGES"),
            ("{wissenskarte.WEG_MOST}", ("Schritte, die wissenskarte.weg höchstens sucht", "steps wissenskarte.weg looks for at most"), "wissenskarte.WEG_MOST"),
            ("{documents.VEC_BLOCK}", ("Stellen je Block beim Vergleich der Vektoren", "passages per block when comparing vectors"), "documents.VEC_BLOCK"),
            ("{wissenskarte.DAY}", ("Dokumente am Tag für die Wissenskarte (Standard)", "documents a day for the knowledge map (default)"), "wissenskarte.DAY"),
            ("{wissenskarte.ENT_PER_DOC}", ("Personen, Firmen, Orte, Verträge, Konten und Fristen, die ein Dokument bringen darf", "people, companies, places, contracts, accounts and deadlines one document may bring"), "wissenskarte.ENT_PER_DOC"),
            ("{wissenskarte.MAX_ENT}", ("solche Punkte pro Profil", "such points per profile"), "wissenskarte.MAX_ENT"),
            ("{wissenskarte.ENT_NAME_LEN}", ("Zeichen, die der Name eines solchen Punktes höchstens hat", "characters the name of such a point has at most"), "wissenskarte.ENT_NAME_LEN"),
            ("{wissenskarte.ENT_DAY}", ("Dokumente am Tag für diese Punkte (Standard)", "documents a day for these points (default)"), "wissenskarte.ENT_DAY"),
            ("{wissenskarte.KARTE_MOST}", ("Stellen, die die Karte der Suche höchstens nennt", "passages the map names to the search at most"), "wissenskarte.KARTE_MOST"),
            ("{wissenskarte.KARTE_KNOTEN}", ("Punkte, die die Suchwörter höchstens treffen", "points the search words hit at most"), "wissenskarte.KARTE_KNOTEN"),
            ("{documents.KARTE_WEIGHT}", ("Gewicht der Liste aus der Karte", "weight of the list from the map"), "documents.KARTE_WEIGHT"),
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
            ("Funktionen → Eigene Dokumente und darunter Wissensbuch an: Seiten aus den eigenen Dokumenten, dazu "
             "wie viele Dokumente am Tag.",
             "Features → Own documents and below it Knowledge book on: pages from the own documents, with how many "
             "documents a day."),
            ("Funktionen → Eigene Dokumente → Wissensbuch und darunter Wissenskarte an: Verbindungen zwischen den "
             "Seiten, zu sehen im Menü Wissensbuch auf der Seite Karte, dazu wie viele Dokumente am Tag (eigene Grenze).",
             "Features → Own documents → Knowledge book and below it Knowledge map on: connections between the "
             "pages, shown in the menu Knowledge book on the page Map, with how many documents a day (own limit)."),
            ("Funktionen → Eigene Dokumente → Wissensbuch → Wissenskarte und darunter Personen, Firmen und Fristen an: "
             "eigene Punkte aus den Dokumenten auf der Karte, dazu wie viele Dokumente am Tag (eigene Grenze).",
             "Features → Own documents → Knowledge book → Knowledge map and below it People, companies and deadlines "
             "on: points of their own from the documents on the map, with how many documents a day (own limit)."),
            ("Funktionen → Eigene Dokumente → Wissensbuch → Wissenskarte → Personen, Firmen und Fristen und darunter "
             "Karte hilft der Suche an: die Karte als dritte Trefferliste der Dokumentsuche (Standard aus).",
             "Features → Own documents → Knowledge book → Knowledge map → People, companies and deadlines and below it "
             "Map helps the search on: the map as third list of hits of the document search (default off)."),
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
            (("Wissensbuch", "Knowledge book"), [
                ("In ruhigen Minuten bekommt das Sprachmodell ein eigenes Dokument in nummerierten Stellen und höchstens "
                 "{wissensbuch.CANDIDATES} bestehende Seiten, die das Panel nach gemeinsamen Wörtern mit Titel, "
                 "Absender und Tags auswählt. Das Modell schlägt Sätze als JSON vor, jeden mit der Nummer seiner Stelle.",
                 "In quiet minutes the language model gets an own document in numbered passages and at most "
                 "{wissensbuch.CANDIDATES} existing pages the panel picks by words shared with title, sender and tags. "
                 "The model proposes sentences as JSON, each with the number of its passage."),
                ("Das Panel behält einen Satz nur, wenn seine Stelle existiert, jede Zahl und jedes Datum darin in der "
                 "Stelle steht, er höchstens {wissensbuch.MAX_LEN} Zeichen hat und weder Link noch Befehl enthält. Sagt "
                 "er dasselbe wie ein Satz der Seite mit anderer Zahl, bleiben beide als Widerspruch stehen. Ein Dokument "
                 "ändert höchstens {wissensbuch.PAGES_PER_DOC} Seiten.",
                 "The panel keeps a sentence only when its passage exists, every number and date in it stands in the "
                 "passage, it has at most {wissensbuch.MAX_LEN} characters and holds neither link nor command. If it "
                 "says the same as a sentence of the page with another number, both stay as a contradiction. One "
                 "document changes at most {wissensbuch.PAGES_PER_DOC} pages."),
                ("Bei einer Frage legt document_search die passendsten Seiten vor die Stellen, jeder Satz mit Quelle. "
                 "Die Seiten sind Text von außen wie die Dokumente.",
                 "On a question document_search puts the best fitting pages before the passages, each sentence with "
                 "its source. The pages are outside text like the documents."),
                ("Die passenden Seiten findet ein eigener Suchindex (SQLite FTS5, Tabelle wb_fts: Titel und Sätze "
                 "jeder Seite als Suchwörter). Feste SQL-Trigger merken sich jede Seite, deren Titel oder Sätze sich "
                 "ändern, und vor jedem Speichern schreibt das Panel ihre Zeile neu (wissensbuch._fts_sync); ein "
                 "Buch von vorher bekommt den Index einmal. Gezählt wird wie bisher: gemeinsame Wörter, der Titel "
                 "dreifach. Fehlt FTS5, zählt das Panel die Wörter aller Seiten wie früher. Andere Teile des Panels "
                 "lesen über wissensbuch.liste nur Seiten-Ids mit Rang (höchstens {wissensbuch.LISTE_MOST}, nur das "
                 "eigene Profil, nur wenn das Wissensbuch für es frei ist).",
                 "The fitting pages are found by an own search index (SQLite FTS5, table wb_fts: title and sentences "
                 "of each page as search words). Fixed SQL triggers note every page whose title or sentences change, "
                 "and before each save the panel writes its row again (wissensbuch._fts_sync); a book from before gets "
                 "the index once. The count is as before: shared words, the title three times. Without FTS5 the panel "
                 "counts the words of all pages as it used to. Other parts of the panel read only page ids with their "
                 "rank through wissensbuch.liste (at most {wissensbuch.LISTE_MOST}, only the own profile, only when "
                 "the knowledge book is allowed for it)."),
                ("Nachts (im Fenster der Suchprüfung, einmal je Profil) prüft das Panel mit festen Regeln: ein neu "
                 "gelesenes Dokument wird neu eingearbeitet, Sätze verschwundener Dokumente gehen, gedaechtnis.check "
                 "markiert vorbeigegangene Daten und alte Zeitwörter als „veraltet?“. Danach beantwortet das Modell für "
                 "bis zu {wissensbuch.SAMPLE} Sätze nur „steht das so in der Stelle?“; ein Nein entfernt den Satz. "
                 "Gelöschte oder ausgelassene Dokumente nehmen ihre Sätze sofort mit (documents.on_gone).",
                 "At night (in the search check's window, once per profile) the panel checks by fixed rules: a document "
                 "read again is worked in again, sentences of vanished documents go, gedaechtnis.check marks passed "
                 "dates and old time words as „out of date?“. Then the model answers for up to {wissensbuch.SAMPLE} "
                 "sentences only „does the passage say so?“; a no removes the sentence. Deleted or left-out documents "
                 "take their sentences at once (documents.on_gone)."),
                ("Stützt sich eine Antwort auf mindestens {wissensbuch.OFFER_MIN} Quellen (Dokumente oder Kiwix-Artikel), "
                 "merkt sich das Panel sie eine Stunde im Speicher; erst der Klick „Ins Wissensbuch“ legt sie als Seite "
                 "„Antwort“ ab. Jeder Satz braucht eine Stelle aus diesen Quellen mit allen seinen Zahlen und genug "
                 "gemeinsamen Wörtern. Export als Obsidian-Ordner (ZIP); nachts eine Kopie in den Ablage-Ordner, wenn "
                 "das Profil automatisch ablegt und sich das Buch geändert hat.",
                 "When an answer rests on at least {wissensbuch.OFFER_MIN} sources (documents or Kiwix articles), the "
                 "panel keeps it in memory for an hour; only the click „To the knowledge book“ files it as a page "
                 "„Answer“. Every sentence needs a passage from these sources with all its numbers and enough shared "
                 "words. Export as Obsidian folder (ZIP); at night a copy into the filing folder when the profile files "
                 "automatically and the book changed."),
            ]),
            (("Wissenskarte", "Knowledge map"), [
                ("Ist die Wissenskarte an, bekommt das Sprachmodell nach dem Wissensbuch dasselbe Dokument noch einmal "
                 "mit höchstens {wissenskarte.NODES_PER_DOC} Seiten, die das Panel auswählt (die Seiten des Dokuments "
                 "und Seiten, deren Titel es nennt). Das Modell schlägt Verbindungen als JSON vor, jede mit einer Art "
                 "aus einer festen Liste und der Nummer ihrer Stelle.",
                 "When the knowledge map is on, the language model gets the same document again after the knowledge "
                 "book, with at most {wissenskarte.NODES_PER_DOC} pages the panel picks (the document's pages and "
                 "pages whose title it names). The model proposes connections as JSON, each with a kind from a fixed "
                 "list and the number of its passage."),
                ("Das Panel behält eine Verbindung nur, wenn beide Seiten angeboten waren, beide in der Stelle genannt "
                 "sind, jede Zahl des Zusatzes in der Stelle steht und eine Ursache (führte zu, verursacht, erhöht, "
                 "senkt) ein Wort des Grundes in der Stelle hat. Höchstens {wissenskarte.EDGES_PER_DOC} je Dokument; "
                 "„Stimmt nicht“ bringt dieselbe Verbindung aus demselben Dokument nie wieder.",
                 "The panel keeps a connection only when both pages were offered, both are named in the passage, "
                 "every number of the detail stands in the passage and a cause (led to, causes, raises, lowers) has a "
                 "word of reason in the passage. At most {wissenskarte.EDGES_PER_DOC} per document; „Not right“ never "
                 "brings the same connection back from the same document."),
                ("Die Karte zeichnen Browser und App mit eigenem Code aus Namen und Arten, nie aus SVG, Mermaid oder "
                 "DOT des Modells. Das Panel liefert nur den sichtbaren Teil mit höchstens {wissenskarte.VIEW_NODES} "
                 "Punkten; der Export als Mermaid- oder Graphviz-Text entsteht aus festem Code mit gereinigten Namen.",
                 "Browser and app draw the map with their own code from names and kinds, never from SVG, Mermaid or "
                 "DOT of the model. The panel only answers the visible part with at most {wissenskarte.VIEW_NODES} "
                 "points; the export as Mermaid or Graphviz text comes from fixed code with cleaned names."),
                ("Den sichtbaren Teil wählt SQLite: Verbindungen je Seite und Dokument zählt eine feste Abfrage, und "
                 "rund um eine Seite läuft WITH RECURSIVE höchstens zwei Schritte über die Verbindungen; UNION nimmt "
                 "jede Seite je Schritt nur einmal, ein Ring läuft also nie weiter. Nur die gewählten Punkte und "
                 "höchstens {wissenskarte.VIEW_EDGES} Verbindungen kommen ins Panel. Zwei feste Abfragen mit Werten "
                 "nur als Parameter, nie aus Text des Modells: wissenskarte.rund_um (Seiten um eine Seite) und "
                 "wissenskarte.weg (kürzester Weg zwischen zwei Seiten, höchstens {wissenskarte.WEG_MOST} Schritte).",
                 "SQLite picks the visible part: a fixed query counts the connections per page and document, and "
                 "around a page WITH RECURSIVE walks at most two steps over the connections; UNION takes each page "
                 "only once per step, so a ring never runs on. Only the chosen points and at most "
                 "{wissenskarte.VIEW_EDGES} connections reach the panel. Two fixed queries with values only as "
                 "parameters, never from the model's text: wissenskarte.rund_um (pages around a page) and "
                 "wissenskarte.weg (shortest way between two pages, at most {wissenskarte.WEG_MOST} steps)."),
            ]),
            (("Personen, Firmen und Fristen", "People, companies and deadlines"), [
                ("Ist der Schalter unter der Wissenskarte an, schlägt das Sprachmodell nach den Verbindungen je Stelle "
                 "eines Dokuments nur JSON vor: Personen, Firmen, Orte, Verträge, Konten und Fristen mit Art und "
                 "Nummer der Stelle. Das Panel behält einen Namen nur nach festen Regeln (wissenskarte.check_ent): die "
                 "Art aus der festen Liste, der Name steht in der Stelle (klein, ohne Akzente, Leerzeichen "
                 "zusammengezogen), 2 bis {wissenskarte.ENT_NAME_LEN} Zeichen ohne Link, Auszeichnung oder Befehl, eine "
                 "Frist nur mit Datum in der Stelle, ein Konto nur als IBAN oder Nummer; höchstens "
                 "{wissenskarte.ENT_PER_DOC} je Dokument und {wissenskarte.MAX_ENT} je Profil. Verbindungen dieser "
                 "Punkte prüft dieselbe Regel wie die der Seiten.",
                 "When the switch below the knowledge map is on, the language model proposes only JSON per passage of a "
                 "document after the connections: people, companies, places, contracts, accounts and deadlines with "
                 "kind and the number of the passage. The panel keeps a name only by fixed rules "
                 "(wissenskarte.check_ent): the kind from the fixed list, the name stands in the passage (lower case, "
                 "without accents, spaces drawn together), 2 to {wissenskarte.ENT_NAME_LEN} characters without link, "
                 "markup or command, a deadline only with a date in the passage, an account only as IBAN or number; at "
                 "most {wissenskarte.ENT_PER_DOC} per document and {wissenskarte.MAX_ENT} per profile. Connections of "
                 "these points are checked by the same rule as those of the pages."),
                ("Jeder Punkt hat eine feste Nummer (wk_ent) und seine Stellen (wk_ment: Dokument und Stück). Andere "
                 "Teile lesen nur: wissenskarte.finde_knoten (genau über Name und andere Namen) und "
                 "wissenskarte.knoten_liste (nach Namen sortiert) und wissenskarte.knoten_von_dok (die Punkte eines "
                 "Dokuments nach Art und Name, höchstens {wissenskarte.LISTE_MOST}). Zusammenführen (wissenskarte.zusammen), Umbenennen "
                 "und Löschen geschehen nur per Klick der Besitzerin oder des Besitzers mit dem Code von „Bestätigen“, "
                 "nie durch das Modell; jede Änderung meldet wissenskarte.GEAENDERT. Geht ein Dokument, gehen seine "
                 "Stellen sofort mit, ein Punkt ohne Stelle verschwindet.",
                 "Every point has a fixed number (wk_ent) and its passages (wk_ment: document and piece). Other parts "
                 "only read: wissenskarte.finde_knoten (exactly by name and other names) and wissenskarte.knoten_liste "
                 "(sorted by name) and wissenskarte.knoten_von_dok (the points of one document by kind and name, at most "
                 "{wissenskarte.LISTE_MOST}). Merging (wissenskarte.zusammen), renaming and deleting happen only by the owner's "
                 "click with the code of „Confirm“, never by the model; every change reports to "
                 "wissenskarte.GEAENDERT. When a document goes, its passages go with it at once, a point without a "
                 "passage disappears."),
            ]),
            (("Karte hilft der Suche", "Map helps the search"), [
                ("wissenskarte.liste(uid, worte, k) gibt Stück-Ids mit Rang ab 1 zurück, nur lesend (SQLite mit mode=ro) "
                 "und nur für das eigene Profil. Feste Regeln, nie das Modell: Die Suchwörter treffen einen Punkt, wenn "
                 "sein Name oder ein anderer Name ganz in der Frage steht (verglichen wie wissenskarte.ent_norm) oder "
                 "ein Wort des Namens ab {wissenskarte.KARTE_WORT} Buchstaben, das keine Zahl und keine Rechtsform ist "
                 "(wissenskarte.trifft); höchstens {wissenskarte.KARTE_KNOTEN} Punkte. Dazu kommen ihre Nachbarn einen "
                 "Schritt weit (dieselbe Abfrage wie wissenskarte.rund_um) und von allen die Stellen in genutzten, "
                 "gelesenen Dokumenten. Eine Stelle mit einem genannten Punkt steht vor einer mit nur Nachbarn, mehr "
                 "Punkte vor weniger, höchstens {wissenskarte.KARTE_MOST}.",
                 "wissenskarte.liste(uid, worte, k) returns piece ids with a rank from 1, read only (SQLite with "
                 "mode=ro) and only for the own profile. Fixed rules, never the model: the search words hit a point when "
                 "its name or another name stands whole in the question (compared like wissenskarte.ent_norm) or a "
                 "word of the name with at least {wissenskarte.KARTE_WORT} letters that is no number and no legal form "
                 "(wissenskarte.trifft); at most {wissenskarte.KARTE_KNOTEN} points. Their neighbours one step away "
                 "join (the same query as wissenskarte.rund_um), and of all of them the passages in used, read "
                 "documents. A passage with a named point stands before one with only neighbours, more points before "
                 "fewer, at most {wissenskarte.KARTE_MOST}."),
                ("documents.search mischt die Liste wie die anderen mit 60 plus Platz, gewichtet mit "
                 "{documents.KARTE_WEIGHT}, und nur Stellen, die dieselbe Bedingung der Suche durchlässt "
                 "(documents._karte). Ein so gefundener Treffer trägt „karte“, unter der Antwort steht „über die "
                 "Wissenskarte“. Die Suchprüfung misst die Mischung mit der Karte als eigenen Balken. Fällt die Karte "
                 "aus, sucht die Suche ohne sie weiter und schreibt eine Zeile „wissen: kartensuche fehler“.",
                 "documents.search mixes the list like the others with 60 plus place, weighed {documents.KARTE_WEIGHT}, "
                 "and only passages the same condition of the search lets through (documents._karte). A hit found so "
                 "carries „karte“, below the answer it says „via the knowledge map“. The search check measures the mix "
                 "with the map as a bar of its own. If the map fails, the search goes on without it and writes a line "
                 "„wissen: kartensuche fehler“."),
            ]),
            (("Erst lokal suchen", "Look locally first"), [
                ("Vor der ersten Runde schaut das Panel selbst in Dokumente, Kiwix und frühere Gespräche, gleichzeitig "
                 "und nur kurz. Die Bedeutungssuche fährt nur mit, wenn ihr Modell schon läuft und frei ist; es wird "
                 "dafür nicht geweckt.",
                 "Before the first round the panel itself looks in documents, Kiwix and earlier conversations, at the "
                 "same time and only briefly. Meaning search only rides along when its model already runs and is free; "
                 "it is not woken for it."),
                ("Eine Stelle zählt nur, wenn sie mindestens {lokal.COVER} der Suchwörter enthält (ein langes Wort darf um "
                 "ein bis zwei Buchstaben vertippt sein, lokal.same). Was zu spät kommt, "
                 "wird nicht abgewartet. Das Kiwix hat eine eigene Zeitgrenze (Standard {lokal.DEFAULT_KIWIX_MS} ms, "
                 "die übrigen Quellen {lokal.DEFAULT_MS} ms) und fragt je Frage höchstens {kiwix.MAX_SEARCH_BOOKS} "
                 "Bücher: die größte deutsche Wikipedia und die Bücher, deren Titel oder Beschreibung zur Frage passt "
                 "(kiwix.pick). Ein Archiv-Artikel steht als Quelle mit Stand unter der Antwort.",
                 "A passage only counts when it holds at least {lokal.COVER} of the search words (a long word may be mistyped "
                 "by one or two letters, lokal.same). What comes too late "
                 "is not waited for. The Kiwix has its own time limit (default {lokal.DEFAULT_KIWIX_MS} ms, the other "
                 "sources {lokal.DEFAULT_MS} ms) and asks at most {kiwix.MAX_SEARCH_BOOKS} books per question: the "
                 "biggest German Wikipedia and the books whose title or description fits the question (kiwix.pick). "
                 "An archive article stands as a dated source under the answer."),
                ("Von einer Stelle aus den Dokumenten bekommt das Modell höchstens {lokal.MAX_HIT_CHARS} Zeichen, und zwar "
                 "das Stück mit den Suchwörtern, nicht den Anfang (lokal.excerpt). Aus einer Tabelle sind das die "
                 "Kopfzeile und die Zeilen mit den seltensten Suchwörtern: ein Wort, das in jeder Zeile steht "
                 "(„Karte“), zählt wenig, „Durchfall“ in einer Zeile viel; Zeilen mit weniger als halb so viel "
                 "Gewicht wie die beste kommen nicht dazu.",
                 "From a passage of the documents the model gets at most {lokal.MAX_HIT_CHARS} characters, namely the "
                 "part with the search words, not the start (lokal.excerpt). From a table that is the head row and "
                 "the rows with the rarest search words: a word in every row („card“) counts little, „diarrhoea“ in "
                 "one row a lot; rows with less than half the weight of the best are not added."),
            ]),
            (("Tabellen in PDFs", "Tables in PDFs"), [
                ("pypdf liest eine Tabelle Zelle für Zelle, jede Zelle auf eigener Zeile; welche Karte zu welcher "
                 "Beschwerde gehört, ginge verloren. pdftabellen.read sieht sich darum jede PDF-Seite mit pdfium an: "
                 "die gezeichneten Linien und Kästen geben die Zeilen, senkrechte Linien oder Lücken im Text die "
                 "Spalten, und jede Zelle bekommt den Text aus ihrem eigenen Kasten. Jede Zeile wird zu einer Zeile "
                 "„| Durchfall | SR 18 … | Hinweis |“. Eine Seite ohne gezeichnete Tabelle bleibt, wie pypdf sie las. "
                 "Nach {pdftabellen.BUDGET_S} s je Dokument bleiben die übrigen Seiten ebenso.",
                 "pypdf reads a table cell by cell, each cell on its own line; which card belongs to which complaint "
                 "would be lost. pdftabellen.read therefore looks at every PDF page with pdfium: the drawn lines and "
                 "boxes give the rows, vertical lines or gaps in the text the columns, and each cell gets the text "
                 "from its own box. Each row becomes one line „| Diarrhoea | SR 18 … | Note |“. A page without a "
                 "drawn table stays as pypdf read it. After {pdftabellen.BUDGET_S} s per document the remaining "
                 "pages stay so too."),
                ("Eine Tabelle bis {documents.TABLE} Zeichen bleibt eine Stelle. Eine längere wird nur zwischen "
                 "ihren Zeilen geteilt (documents._rows), und jedes Stück beginnt mit ihrer Kopfzeile.",
                 "A table up to {documents.TABLE} characters stays one passage. A longer one is cut only between its "
                 "rows (documents._rows), and every piece starts with its head row."),
                ("PDFs von vorher sieht das Panel in ruhigen Minuten eins nach dem anderen an (documents.due_tables): "
                 "ist das Original aufbewahrt und hat es eine Tabelle, wird es neu gelesen; sonst bleibt es, wie es "
                 "ist. Ohne Original hilft nur neu hochladen.",
                 "PDFs from before are looked at one by one in quiet minutes (documents.due_tables): if the original "
                 "is kept and has a table, it is read again; otherwise it stays as it is. Without the original only "
                 "uploading it again helps."),
            ]),
            (("Gedächtnis", "Memory"), [
                ("Das Gedächtnis wird nicht durchsucht. Das Panel sortiert die Fakten mit festen Regeln in drei Blöcke "
                 "(sicher, gelernt, vielleicht veraltet) und gibt sie dem Modell im Systemprompt.",
                 "The memory is not searched. The panel sorts the facts by fixed rules into three blocks (sure, "
                 "learned, maybe out of date) and gives them to the model in the system prompt."),
                ("Höchstens {profiles.MAX_FACTS} Fakten je Profil, ohne stilles Wegwerfen (profiles._cap, auch beim "
                 "Aufräumen): darüber gehen zuerst die ältesten von selbst gelernten, nie bestätigten. Gesagtes, "
                 "Korrigiertes, von Hand Geändertes, Aufgeräumtes und Bestätigtes geht nie; bleibt nur solches, wird "
                 "der neue Fakt abgelehnt (memory_save: „Not done“ mit dem Weg Ich → Gedächtnis), eine Zeile "
                 "„gedaechtnis: voll“ je Tag.",
                 "At most {profiles.MAX_FACTS} facts per profile, without silent throwing away (profiles._cap, also when "
                 "tidying): above that the oldest facts learned by itself and never confirmed go first. What was said, "
                 "corrected, changed by hand, tidied or confirmed never goes; when only such facts are left, the new "
                 "fact is refused (memory_save: „Not done“ with the way Me → Memory), one line „gedaechtnis: voll“ a day."),
                ("Feste Themen (gedaechtnis.SLOTS: Wohnort, Arbeitgeber, Beruf, Partner, Kinder, Geburtstag, Ernährung, "
                 "Haustier, Auto, Namen, Lieblings-…, je mit „wer“) erkennt nur das Panel an festen Mustern "
                 "(gedaechtnis.slot_of). Je Platz hält ein Fakt den Wert: Gesagtes oder Korrigiertes gibt ihm den neuen "
                 "Wortlaut, der alte bleibt als frühere Fassung (höchstens {profiles.MAX_PREV}, Grund „platz“). Ein von "
                 "selbst gelernter Wert ersetzt nie einen bestätigten: er wartet als Angebot am Fakt mit der Karte "
                 "„Übernehmen / Verwerfen“. Das Modell bekommt je Platz nur den Wert, der ihn hält, nie frühere "
                 "Fassungen oder ein Angebot.",
                 "Fixed topics (gedaechtnis.SLOTS: home, employer, job, partner, children, birthday, diet, pet, car, names, "
                 "favourites, each with „who“) only the panel recognizes by fixed patterns (gedaechtnis.slot_of). Per place "
                 "one fact holds the value: something said or corrected gives it the new wording, the old one stays as an "
                 "earlier version (at most {profiles.MAX_PREV}, reason „platz“). A value learned by itself never replaces "
                 "a confirmed one: it waits as an offer on the fact with the card „Take it / Discard“. The model gets per "
                 "place only the value that holds it, never earlier versions or an offer."),
                ("Gemerkt-Hinweis (gemerkt.py): memory_save schickt Nummer und Stand des Fakts (gemerkt.rev_of) mit, "
                 "unter der Antwort steht „Gemerkt: …“ mit „Rückgängig“; das Gespräch behält nur die Nummern. "
                 "Rückgängig (gemerkt.take_back) geht nur, solange der Fakt seitdem unverändert ist: ein neuer Fakt geht, "
                 "ein fester Platz bekommt seine frühere Fassung zurück. Von selbst Gelerntes wird eine Karte „Gemerkt von "
                 "selbst“ (bis zu {gemerkt.CARD_MAX} Fakten, {gemerkt.OFFEN_TAGE} Tage) mit „Stimmt“ und „Rückgängig“; "
                 "ihr Titel nennt nur eine Zahl, nie den Fakt.",
                 "Remembered note (gemerkt.py): memory_save sends the fact's number and state along (gemerkt.rev_of), "
                 "under the answer stands „Remembered: …“ with „Undo“; the conversation keeps only the numbers. Undo "
                 "(gemerkt.take_back) works only while the fact is unchanged since: a new fact goes, a fixed place gets "
                 "its earlier version back. What was learned by itself becomes a card „Remembered by itself“ (up to "
                 "{gemerkt.CARD_MAX} facts, {gemerkt.OFFEN_TAGE} days) with „That's right“ and „Undo“; its title names "
                 "only a number, never the fact."),
            ]),
            (("Wissen messen", "Measuring knowledge"), [
                ("Zustand → Prüfen → Wissen messen misst Zeiten und Speicher dieser Wege, für den Test mit 5000 "
                 "Dokumenten: die Vektor-Matrix (float16, MB und Speicher des Prozesses vorher und nachher), die "
                 "Dokumentsuche mit und ohne Karte, wissensbuch.liste, view, rund_um, weg und wissenskarte.liste, je "
                 "Median und p95 über {wissensmessung.PROBEN} feste Beispiele aus den eigenen Titeln und Namen, dazu "
                 "Seiten, Punkte, Verbindungen und Verbindungen je Dokument. Nur Zahlen, nie ein Titel oder Name.",
                 "Status → Checks → Measure knowledge measures times and memory of these ways, for the test with 5000 "
                 "documents: the vector matrix (float16, MB and the process's memory before and after), the document "
                 "search with and without the map, wissensbuch.liste, view, rund_um, weg and wissenskarte.liste, each "
                 "median and p95 over {wissensmessung.PROBEN} fixed samples from the own titles and names, and pages, "
                 "points, connections and connections per document. Numbers only, never a title or a name."),
                ("Gemessen wird in einem eigenen Prozess mit niedriger Priorität (nice und SCHED_IDLE, ein Thread), "
                 "erst in einer ruhigen Minute, höchstens {wissensmessung.MAX_S} s, einer zur Zeit (wissensmessung.lauf). "
                 "Spricht jemand, hört er auf. Erfundene Dokumente entstehen aus festem Zufall in einem Wegwerf-Profil "
                 "unter state/wissensmessung-tmp und sind danach weg; die Grenzen des echten Codes gelten dabei, und der "
                 "Lauf sagt, wie viel die Dokumente ohne sie gebracht hätten. Ein echtes Profil wird nur gelesen "
                 "(PRAGMA query_only).",
                 "It measures in a process of its own with low priority (nice and SCHED_IDLE, one thread), only in a "
                 "quiet minute, at most {wissensmessung.MAX_S} s, one at a time (wissensmessung.lauf). If somebody "
                 "speaks, it stops. Made-up documents come from a fixed seed in a throwaway profile under "
                 "state/wissensmessung-tmp and are gone afterwards; the limits of the real code hold, and the run says "
                 "how much the documents would have brought without them. A real profile is only read (PRAGMA "
                 "query_only)."),
                ("Andere Teile hängen sich als Messteil an (wissensmessung.MESSTEILE: Name und fn(ordner, anzahl), "
                 "nur Zahlen, nur im Wegwerf-Ordner des Laufs).",
                 "Other parts join as a measuring part (wissensmessung.MESSTEILE: a name and fn(ordner, anzahl), "
                 "numbers only, only in the run's throwaway folder)."),
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
            ("frisch.spanne", ("Zeitraum aus den eigenen Worten, feste Regeln", "period from the own words, fixed rules")),
            ("fund.pruefe", ("Schlagworte des Modells nur nach festen Regeln", "the model's tags only by fixed rules")),
            ("fund.klar_vorn", ("ein Treffer klar vorn: feste Regel", "one hit clearly ahead: a fixed rule")),
            ("fund.sofort_satz", ("Sofort-Karte: fester Satz des Panels", "Sofort-Karte: the panel's fixed sentence")),
            ("wissen.where", ("Herkunft einer Stelle für das Modell", "source of a passage for the model")),
            ("lokal.look", ("der kurze Blick vor der Antwort", "the quick look before the answer")),
            ("lokal.excerpt", ("das Stück einer Stelle mit den Suchwörtern", "the part of a passage with the search words")),
            ("pdftabellen.read", ("Tabellen in PDFs zeilenweise lesen", "read tables in PDFs row by row")),
            ("documents._rows", ("lange Tabellen nur zwischen Zeilen teilen", "cut long tables only between rows")),
            ("documents.due_tables", ("PDFs von vorher neu lesen, wenn sie Tabellen haben", "read PDFs from before again when they have tables")),
            ("wissensbuch.answer_block", ("passende Seiten des Wissensbuchs mit Quellen", "fitting pages of the knowledge book with sources")),
            ("wissenskarte.check_edge", ("feste Regeln für jede vorgeschlagene Verbindung", "fixed rules for every proposed connection")),
            ("wissenskarte.view", ("der sichtbare Teil der Karte", "the visible part of the map")),
            ("wissenskarte.rund_um", ("Seiten um eine Seite, WITH RECURSIVE", "pages around a page, WITH RECURSIVE")),
            ("wissenskarte.weg", ("kürzester Weg zwischen zwei Seiten", "shortest way between two pages")),
            ("wissenskarte.check_ent", ("feste Regeln für jede Person, Firma, Frist …", "fixed rules for every person, company, deadline …")),
            ("wissenskarte.finde_knoten", ("Punkte genau über Name und andere Namen, nur lesend", "points exactly by name and other names, read only")),
            ("wissenskarte.knoten_liste", ("Punkte einer Art nach Namen, nur lesend", "points of one kind by name, read only")),
            ("wissenskarte.knoten_von_dok", ("Punkte eines Dokuments nach Art und Name, nur lesend", "points of one document by kind and name, read only")),
            ("wissenskarte.zusammen", ("zwei Punkte zusammenführen, nur per Klick", "merge two points, only by click")),
            ("wissensbuch.search_pages", ("passende Seiten über den Suchindex wb_fts", "fitting pages through the search index wb_fts")),
            ("wissensbuch._fts_sync", ("Suchindex der Seiten nachziehen", "bring the pages' search index up to date")),
            ("wissensbuch.liste", ("Seiten-Ids mit Rang für andere Teile, nur lesend", "page ids with rank for other parts, read only")),
            ("wissenskarte.liste", ("Stück-Ids aus der Karte für die Suche, nur lesend", "piece ids from the map for the search, read only")),
            ("wissenskarte.trifft", ("trifft ein Suchwort einen Punkt? feste Regel", "does a search word hit a point? fixed rule")),
            ("documents._karte", ("die Liste der Karte in die Mischung, mit den Filtern der Suche", "the map's list into the mix, with the search's filters")),
            ("documents._similar", ("Ähnlichkeit blockweise in float32", "similarity block by block in float32")),
            ("gedaechtnis.hint_lines", ("Fakten in drei Blöcken", "facts in three blocks")),
            ("profiles._cap", ("Obergrenze: nur alte gelernte Fakten machen Platz", "cap: only old learned facts make room")),
            ("gedaechtnis.slot_of", ("fester Themen-Platz eines Fakts nach festen Mustern", "a fact's fixed topic place by fixed patterns")),
            ("gemerkt.take_back", ("Rückgängig nur bei unverändertem Fakt", "undo only while the fact is unchanged")),
            ("wissensmessung.lauf", ("eine Messung im eigenen Prozess, bricht bei Sprache ab", "one measurement in its own process, stops on speech")),
            ("wissensmessung._synth", ("das Wegwerf-Profil aus festem Zufall, mit den Grenzen des Codes", "the throwaway profile from a fixed seed, with the code's limits")),
            ("wissensmessung.MESSTEILE", ("die Messteile, erweiterbar", "the measuring parts, extensible")),
        ],
        "tests": ["test_wissen", "test_nachsortieren", "test_abschnitte", "test_lokal", "test_kiwix", "test_gedaechtnis",
                  "test_gedaechtnis_grenze", "test_gemerkt",
                  "test_suchpruefung", "test_wissensbuch", "test_wissenskarte", "test_wissensknoten", "test_kartensuche",
                  "test_wissensmessung"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Betrieb: Logs und Live
    "betrieb": {
        "stand": "04582c5bff",
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
               "Datensatz an: Kanal, Art (Profil, Gast, Admin, Spark) und Gerät. Vor jedem Schalter zählt aktiv.py "
               "die Anfrage für „Aktiv 10 min“ (OLED, Monitoring, Live): ein Profil einmal, ein Gast je Gerät als "
               "gekürzter Hash, nichts vom Spark selbst, nur im Speicher.",
               "Chat, writing help, creating documents and what the Spark does by itself create a record at the start: "
               "channel, kind (profile, guest, admin, Spark) and device. Before any switch aktiv.py counts the request "
               "for „Aktiv 10 min“ (OLED, Monitoring, Live): a profile once, a guest per device as a shortened hash, "
               "nothing of the Spark itself, in memory only.")),
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
            ("Funktionen → Wartungspause: vor einem Update Sprachmodell, Spracherkennung oder Sprachausgabe anhalten "
             "(Standard aus), dann Zustand → Wartungspause.",
             "Features → Maintenance pause: pause the language model, speech recognition or speech output before an "
             "update (default off), then Status → Maintenance pause."),
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
                 "Anmeldung: eine HTTP-Antwort unter 500 gilt als „antwortet“. Home Assistant wird unter {dienstwacht.HA_PATH} "
                 "gefragt, das es ohne Token beantwortet; /api/ ohne Token zählte dort als falsche Anmeldung.",
                 "A loop looks at the language model, listening, speaking, internet, SearXNG, Kiwix, Home Assistant, "
                 "mail, calendar and NAS, each every minute or every {dienstwacht.SLOW|min} minutes, without login: "
                 "an HTTP answer below 500 counts as „answers“. Home Assistant is asked for {dienstwacht.HA_PATH}, which it "
                 "answers without a token; /api/ without a token counted there as a failed login."),
                ("Weg ist ein Dienst nach {dienstwacht.FAIL_N} Fehlproben über mindestens {dienstwacht.FAIL_S|min} "
                 "Minuten, zurück nach {dienstwacht.OK_N} guten. Ist das Internet weg, gibt es eine Meldung für alles "
                 "dahinter. Während Update, Start und Notaus Stufe 2 zählt nichts, ebenso nicht für einen Teil in der "
                 "Wartungspause, bis deren Zeit um ist.",
                 "A service is gone after {dienstwacht.FAIL_N} failed probes over at least {dienstwacht.FAIL_S|min} "
                 "minutes, back after {dienstwacht.OK_N} good ones. With the internet gone there is one note for "
                 "everything behind it. During update, start and kill switch stage 2 nothing counts, nor for a part in "
                 "the maintenance pause until its time is up."),
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
}
