"""Zustand → Technik, Knoten-Seiten: the pages of devices, apps, channels, speakers and MCP
(geraet, apps, kanaele, lautsprecher, mcpc). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "geraet": {
        "stand": "617a78b229",
        "bezug": {
            "account.CONVO_BODY": ["s10"], "admin.test_asr": ["s4"], "admin._test_asr": ["s4", "s5"],
            "admin.read_audio": ["s4"], "chat.chat": ["s6", "s7"], "account.profile_save_convo": ["s10"],
            "account.profile_convos": ["s11"], "profiles.append_convo": ["s10"], "profiles._clean_convo": ["s10"],
            "verlauf.stream": ["s11"], "sse.Hub.stream": ["s11"], "verlauf.begin": ["s6", "s11"],
            "regeln": ["s6", "s10"],
        },
        "kurz": ("Die Seite im Browser (static/js/chat.js) ist das Gerät: sie nimmt die Frage auf, schickt den Ton zur "
                 "Spracherkennung, schickt den Text an /api/chat und spielt Text und Ton aus einem einzigen Strom ab. "
                 "Die Gespräche eines Profils liegen auf dem Spark, jede offene Seite gleicht sie ab.",
                 "The page in the browser (static/js/chat.js) is the device: it records the question, sends the sound "
                 "to speech recognition, sends the text to /api/chat and plays text and sound from one single stream. "
                 "A profile's conversations live on the Spark, every open page keeps them in step."),
        "warum": ("Gerechnet wird nur auf dem Spark; die Seite bleibt dünn. Browser, Handy-Browser und die Android-App "
                  "(eine WebView) nehmen denselben Weg, deshalb gelten Anmeldung, Grenzen und Regeln an genau einer "
                  "Stelle, und ein Gespräch sieht auf jedem Gerät gleich aus. Die Seite bleibt ruhig: Speichern lädt sie nie "
                  "neu, muss sie doch neu laden (neue Version, Update fertig), kommt sie an dieselbe Stelle zurück, und "
                  "beim Update zeigt nur ein Fenster den Fortschritt.",
                  "All the computing happens on the Spark; the page stays thin. Browser, phone browser and the Android "
                  "app (a WebView) take the same way, so login, limits and rules apply in exactly one place, and a "
                  "conversation looks the same on every device. The page stays calm: saving never reloads it, when it must "
                  "reload (new version, update finished) it comes back to the same place, and during an update one "
                  "window alone shows the progress."),
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
               "geändert hat; ein anderswo gelöschtes Gespräch schließt sich. Mit dem Sofort-Abgleich hält jede sichtbare "
               "Seite einen Ereignis-Strom offen, der nur „Gespräch geändert“ und „antwortet gerade“ meldet, nie "
               "Inhalte (höchstens {verlauf.MAX_STREAMS} pro Profil, je {verlauf.STREAM_SECONDS|min} Minuten); eine "
               "verdeckte Seite schließt ihn, um den Akku zu schonen, und fragt beim Zurückkommen nach.",
               "When the page comes to the front again, and regularly in between, it asks what changed since last "
               "time; a conversation deleted elsewhere closes. With instant sync every visible page keeps an event "
               "stream open that only reports „conversation changed“ and „answering“, never contents (at most "
               "{verlauf.MAX_STREAMS} per profile, {verlauf.STREAM_SECONDS|min} minutes each); a hidden page closes "
               "it to save the battery and asks again on coming back.")),
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
            ("profiles._clean_convo", ("prüft und kürzt ein Gespräch; eine Beschreibung des Bildschirms (bedienen.look) wird nur als Hinweis gespeichert", "checks and trims a conversation; a description of the screen (bedienen.look) is stored only as a note")),
            ("verlauf.stream", ("der Sofort-Abgleich je offener Seite", "instant sync per open page")),
            ("sse.Hub.stream", ("ein Strom je Seite: Warteschlange, Lebenszeichen, Aufräumen",
                                "one stream per page: queue, keep-alive, cleanup")),
            ("verlauf.begin", ("„antwortet gerade“ für die anderen Seiten", "„answering“ for the other pages")),
        ],
        "tests": ["test_verlauf_sync", "test_stille", "test_echo", "test_fremdstimme", "test_follow_up"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Apps
    "apps": {
        "stand": "0aadaa68fe",
        "bezug": {
            "android.TOKEN_SECONDS": ["s3"], "android.TOKEN_USES": ["s3"], "iphone.profile_pair": ["s1", "s2"],
            "kopplung.Codes.new": ["s3"], "kopplung.Codes.take": ["s4"], "iphone.app_pair": ["s4", "s5"],
            "iphone.app_hello": ["s9"], "profiles._app_path": ["s7"], "account.profile_remove_device": ["s11"],
            "android.apk_response": ["s3"], "regeln": ["s6", "s7"], "regel:ohne": ["s10"],
            "terminal.profile_pair": ["s1", "s2"], "terminal.setup_base": ["s3"], "terminal.program_pair": ["s4", "s5"],
            "terminal.reaches": ["s7"], "terminal.CODE_SECONDS": ["s3"], "terminal.MAX_DEVICES": ["s2"],
            "regel:tui": ["s7"], "android.assist_gate": ["s9"], "android.flags": ["s9"],
            "zustellung.api_da": ["s9"],
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
              ("kopplung.py macht einen zufälligen Code (144 Bit); im Speicher liegt nur sein Hash. Ein Profil hat höchstens "
               "{iphone.PER_PROFILE} offene Codes, der Spark höchstens {iphone.MAX_PENDING}. Der Link "
               "{iphone.SCHEME}://pair öffnet die App mit Adresse und Code.",
               "kopplung.py makes a random code (144 bits); only its hash is kept in memory. A profile has at most "
               "{iphone.PER_PROFILE} open codes, the Spark at most {iphone.MAX_PENDING}. The link {iphone.SCHEME}://pair "
               "opens the app with address and code.")),
            S("s4", "frage", ("Code gültig?", "Code valid?"),
              ("POST /api/iphone/pair", "POST /api/iphone/pair"),
              ("Die App schickt den Code. Der Spark prüft das Rate-Limit ({guard.RATE.pair.0} pro Minute und Adresse), "
               "vergleicht den Hash zeitkonstant und löscht den Code beim ersten Treffer. Ein abgelaufener oder schon "
               "benutzter Code passt nie. Ist es kein Link-Code, prüft pruefzugang.py einen getippten Prüf-Code für "
               "Apples Prüfung ({pruefzugang.LENGTH} Zeichen, {pruefzugang.DAYS} Tage, höchstens {pruefzugang.MAX_USES} "
               "iPhones, nur bei eingeschaltetem Prüfzugang); falsche Prüf-Codes sperren die Adresse wie falsche PINs.",
               "The app sends the code. The Spark checks the rate limit ({guard.RATE.pair.0} per minute and address), "
               "compares the hash in constant time and deletes the code at the first hit. An expired or used code "
               "never fits. If it is no link code, pruefzugang.py checks a typed review code for Apple's review "
               "({pruefzugang.LENGTH} signs, {pruefzugang.DAYS} days, at most {pruefzugang.MAX_USES} iPhones, only "
               "with the review access on); wrong review codes lock the address like wrong PINs."),
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
               "Spracherkennung, Gespräche, Erinnerungen, Chats, Anrufe …), ein paar Lese-Muster, die Panel-Bereiche (Admin-Schalter "
               "iPhone-App mit Panel) und „Meine Sachen“ (iphone.THINGS, je Teil nur mit der Freigabe seiner eigenen Funktion). "
               "Alles andere sieht er ohne Profil.",
               "An app key only works for the {profiles.APP_PATHS|anzahl} paths in profiles.APP_PATHS (chat, speech "
               "recognition, conversations, reminders, chats, calls …), a few read patterns, the panel areas (admin switch "
               "iPhone app with panel) and \"My things\" (iphone.THINGS, each part only with the release of its own function). "
               "Everything else it sees without a profile."),
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
               "zeigt es nur an und hält sich daran. Anrufe zwischen Profilen klingeln über einen VoIP-Push von Apple, "
               "der nur die zufällige Nummer des Anrufs trägt; wer anruft, fragt die App beim Spark nach. Für private "
               "Chats macht die App ihren eigenen Schlüssel im Secure Enclave; der Spark bekommt nur die öffentliche Hälfte. "
               "Das Blatt der Android-App über anderen Apps fragt als Gerät „android“, nur solange „Android: Spark als "
               "Assistent“ freigegeben ist (android.assist_gate). Ob die App den letzten Stand der Seiten behalten darf, sagt "
               "hello mit „keep“ (appmerken.keep); bei Nein löscht sie ihn. Mit „Mitteilung ans genutzte Gerät“ "
               "sagen App und Seiten jede Minute nur, ob sie gerade benutzt werden (POST /api/zustellung/da, der Begleiter "
               "mit seiner Leerlaufzeit); zustellung.pick schickt eine Mitteilung dann an das Gerät mit der letzten Eingabe "
               "der letzten {zustellung.ACTIVE} Sekunden, sonst gleich an die Handy-App.",
               "The app asks through the same endpoints as the page, with the same limits. What it may do on top "
               "(smart home, CarPlay, listening, documents, pictures) the Spark tells it in /api/iphone/hello; the app "
               "only shows it and follows it. Calls between profiles ring through a VoIP push from Apple that carries "
               "only the call's random number; the app asks the Spark who calls. For private chats the app makes its own "
               "key in the Secure Enclave; the Spark only gets the public half. The Android app's sheet over other apps asks as "
               "device „android“ only while „Android: Spark as assistant“ is released (android.assist_gate). Whether the app may keep the pages' last state, hello says with "
               "„keep“ (appmerken.keep); on no it deletes it. With „Notes to the device in use“ the app and the pages only say "
               "every minute whether they are in use right now (POST /api/zustellung/da, the companion with its idle time); "
               "zustellung.pick then sends a note to the device with the last input within the last {zustellung.ACTIVE} "
               "seconds, else to the phone app at once."),
              ("info", ("Terminal", "Terminal"),
               ("Terminal-Client: Schlüssel-Bereich „tui“, nur {terminal.TUI_RULES|anzahl} Regeln (Chat, Gespräche, Heute, Kalender mit Schnell eintragen, Mails lesen, Aufträge)",
                "terminal client: key scope „tui“, only {terminal.TUI_RULES|anzahl} rules (chat, conversations, Today, calendar with quick add, reading mail, jobs)"))),
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
            [("tui", "tui"), ("Terminal-Client spark-tui", "terminal client spark-tui"),
             ("terminal.TUI_RULES: Chat, Gespräche, Heute, Kalender, Aufträge", "terminal.TUI_RULES: chat, conversations, Today, calendar, jobs")],
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
            ("{terminal.CODE_SECONDS|min}", ("Minuten gilt eine Kopplungszeile fürs Terminal", "minutes a terminal pairing line is valid"),
             "terminal.CODE_SECONDS"),
            ("{terminal.MAX_DEVICES}", ("Terminals pro Profil", "terminals per profile"), "terminal.MAX_DEVICES"),
            ("{zustellung.ACTIVE}", ("Sekunden nach der letzten Eingabe gilt ein Gerät als benutzt",
                                     "seconds after the last input a device counts as in use"), "zustellung.ACTIVE"),
        ],
        "einstellen": [
            ("Funktionen → iPhone-App und Funktionen → Android-App: die Apps für alle Profile (Standard aus).",
             "Features → iPhone app and Features → Android app: the apps for every profile (default off)."),
            ("Personen und Geräte → Gesperrte Funktionen: die App für einzelne Profile sperren.",
             "People and devices → Blocked functions: block the app for single profiles."),
            ("Ich → iPhone und Ich → Android: koppeln, Rechte der App, Geräte entfernen.",
             "Me → iPhone and Me → Android: pairing, the app's rights, removing devices."),
            ("Funktionen → Terminal-Client und Ich → Terminal: Programm holen, koppeln (zu Hause gepinnt, extern wie im "
             "Browser geprüft), entfernen.",
             "Features → Terminal client and Me → Terminal: get the program, pair (pinned at home, checked as in the "
             "browser from outside), remove."),
        ],
        "sehen": [
            ("Zustand → Live: eine Zeile unter Ereignisse, wenn ein iPhone gekoppelt oder entfernt wird.",
             "Status → Live: a line under events when an iPhone is paired or removed."),
            ("Logs → Anfragen: Fragen der App mit Eingang „iPhone-App“ oder „CarPlay“, vom Android-Blatt „Android-App“.",
             "Logs → Requests: the app's questions with the input „iPhone-App“ or „CarPlay“, from the Android sheet „Android-App“."),
            ("Zustand → Live: offene Terminals als Anzahl unter Verbindungen. Zustand → Logs: im Bereich „Apps“ die „terminal:“-Zeilen.",
             "Status → Live: open terminals as a number under connections. Status → Logs: the „terminal:“ lines in the area „Apps“."),
        ],
        "code": [
            ("iphone.profile_pair", ("Kopplungslink nur aus dem eigenen Browser", "pairing link only from the own browser")),
            ("kopplung.Codes.new", ("zufälliger Einmal-Code, nur der Hash (auch Pebble, Schreibhilfe, Begleiter)",
                                    "random one-time code, only the hash (also Pebble, writing help, companion)")),
            ("kopplung.Codes.take", ("Code einmal einlösen, zeitkonstant verglichen", "redeem a code once, compared in constant time")),
            ("iphone.app_pair", ("der erste Kontakt der App", "the app's first contact")),
            ("iphone.app_hello", ("was die App darf, entscheidet der Spark", "what the app may, the Spark decides")),
            ("profiles.add_device", ("Schlüssel erzeugen, Hash speichern", "make a key, store its hash")),
            ("profiles.current", ("Profil aus Schlüssel oder Cookie, Bereiche, Schalter, Notaus", "profile from key or cookie, scopes, switches, kill switch")),
            ("profiles._app_path", ("die feste Pfadliste der App", "the app's fixed path list")),
            ("core.browser_profile", ("nur die eigene Browser-Anmeldung", "only the own browser login")),
            ("account.profile_remove_device", ("Gerät entfernen", "remove a device")),
            ("android.apk_response", ("App-Datei nur mit gültigem Link", "app file only with a valid link")),
            ("android.flags", ("was die Android-App selbst einschaltet: Assistent, Fingerabdruck", "what the Android app switches on itself: assistant, fingerprint")),
            ("android.assist_gate", ("Fragen des Android-Blatts nur mit Freigabe, nie Gäste", "questions of the Android sheet only when released, never guests")),
            ("zustellung.pick", ("Mitteilung ans benutzte Gerät, sonst an die Handy-App", "note to the device in use, else to the phone app")),
            ("zustellung.api_da", ("nur „gerade benutzt“ oder „weg“, nur Seiten und Apps", "only „in use“ or „away“, only pages and the apps")),
            ("terminal.profile_pair", ("Kopplungszeile fürs Terminal nur aus dem eigenen Browser", "terminal pairing line only from the own browser")),
            ("terminal.setup_base", ("zu Hause gepinnt, extern nur https", "pinned at home, outside https only")),
            ("terminal.program_pair", ("der erste Kontakt des Terminals", "the terminal's first contact")),
            ("terminal.reaches", ("die feste Regelliste des Terminals", "the terminal's fixed rule list")),
        ],
        "tests": ["test_iphone", "test_iphone_panel", "test_android", "test_app_notaus", "test_kopplung", "test_terminal",
                  "test_zustellung"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Telegram, Siri, Uhr
    "kanaele": {
        "stand": "4ad8e8b956",
        "bezug": {
            "watch.JOB_TTL": ["s9"], "telegram.loop": ["s1"], "telegram.handle": ["s2", "s3", "s4"],
            "telegram.ask": ["s7", "s8", "s11"], "telegram.transcribe": ["s5"], "chat.siri_ask": ["s1", "s3"],
            "chat.text_ask": ["s6", "s7", "s11"], "chat.watch_ask": ["s1", "s7"], "chat._watch_run": ["s11"],
            "watch.run": ["s8"], "watch.poll": ["s9"], "regeln": ["s1", "s9", "s11"],
            "watch.follow_ups": ["s9"], "watch.follow_clean": ["s9"], "pebblewatch.watch_sync": ["s9"],
            "pebblewatch.watch_reminder": ["s9"], "pebblewatch.watch_blick": ["s9"], "pebblewatch.watch_brief": ["s9"],
            "pebblewatch.watch_note": ["s9"], "pebblewatch.watch_chat": ["s9"], "pebblewatch.watch_chat_send": ["s9"],
            "pebblewatch.reply_clean": ["s9"], "pebblewatch.watch_remote_act": ["s9"], "pebblewatch.watch_health": ["s9"],
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
               "Knöpfen, die wie eine getippte Antwort zurückkommen; ohne Rückfrage werden die Beispielsätze von „Das "
               "kannst du auch sagen“ zu Antworttasten.",
               "From the stream, pieces of text and retractions count. If the answer came from mail or outside text it "
               "is marked so, so the next question starts locked. A question back from the panel becomes buttons in "
               "Telegram that come back like a typed answer; without one, the example sentences of „You can also say“ "
               "become reply buttons.")),
            S("s9", "schritt", ("Ausgabe je Kanal", "Output per channel"),
              ("Text ohne Markdown · Ton für die Uhr", "text without Markdown · sound for the watch"),
              ("Telegram bekommt reinen Text und, wenn das Profil es will, eine Sprachnachricht in seiner Stimme. Siri "
               "bekommt vorlesbaren Text ohne Passwörter und Codes. Die Uhr holt Text und Ton (auf {watch.MAX_AUDIO} "
               "Bytes je Abruf, für ihren kleinen Lautsprecher gepackt) über /api/watch/poll, nur das Profil, das gefragt hat (fremde Auftrags-Nummern geben 404); höchstens "
               "{watch.MAX_RUNNING} Uhr-Antworten laufen gleichzeitig. Der Begleiter bekommt Text ohne Markdown und "
               "zusätzlich die Antwort mit Markdown (höchstens {chat.MD_ANSWER_MAX} Zeichen), wenn darin nicht weniger "
               "Geheimnisse verdeckt sind. Mit ihren Schaltern bekommt die Uhr außerdem bis zu {watch.FOLLOW_MAX} "
               "Nachfragen zum Antippen (das Modell schlägt nur vor, watch.follow_clean lässt nur kurze Fragen ohne Ja, "
               "Nein, Links oder Zahlen durch; nie nach Mail, Web oder einem Vorschlag; endet die Antwort mit einer Frage, "
               "sind deren Knöpfe aus ablauf.asks die Nachfragen), einen Vorschlag als ✓ und ✕ "
               "und über /api/watch/sync die Schnellbefehle und die nächsten {pebblewatch.AGENDA_MAX} Erinnerungen, "
               "die sie selbst als Wecker klingeln lässt; Push wartet zuerst auf sie. Das Spark-Zifferblatt holt alle 15 "
               "Minuten über /api/watch/blick den nächsten Termin, die nächste Erinnerung, das Wetter, einen Tipp und "
               "für Admins einen Ausfall; /api/watch/brief baut Mein Tag und Meine Woche aus festen Sätzen, "
               "/api/watch/merken legt einen diktierten Satz ins Gedächtnis (mit Ort auf etwa 100 m nur mit eigenem "
               "Schalter). /api/watch/chats und /api/watch/chat zeigen die letzten Chats (ohne private) und schicken "
               "eine angetippte oder diktierte Antwort über chats.send; bis zu {pebblewatch.REPLY_MAX} Vorschläge "
               "des Modells prüft pebblewatch.reply_clean fest. /api/watch/fern schaltet nur Geräte der eigenen Liste "
               "mit festen Tasten (nie mit Smart-Home-Codewort), /api/watch/gesundheit legt Schritte, Puls und Schlaf "
               "versiegelt ins Profil, nie für das Modell.",
               "Telegram gets plain text and, if the profile wants it, a voice message in its voice. Siri gets "
               "speakable text without passwords and codes. The watch fetches text and sound (packed for its small "
               "speaker, {watch.MAX_AUDIO} bytes per fetch) through /api/watch/poll, only for the profile that asked (a foreign job number gives 404); at most {watch.MAX_RUNNING} watch "
               "answers run at once. The companion gets text without Markdown and also the answer with Markdown (at "
               "most {chat.MD_ANSWER_MAX} characters) when it hides no fewer secrets. With its switches the watch also "
               "gets up to {watch.FOLLOW_MAX} follow-ups to tap (the model only suggests, watch.follow_clean keeps short "
               "questions without yes, no, links or numbers; never after mail, web or a proposal; when the answer ends with a "
               "question, its buttons from ablauf.asks are the follow-ups), a proposal as ✓ and "
               "✕, and through /api/watch/sync the quick commands and the next {pebblewatch.AGENDA_MAX} reminders, "
               "which it rings itself as wake-ups; push waits for it first. The Spark watchface fetches the next appointment, "
               "reminder, weather, a hint and for admins an outage through /api/watch/blick every 15 minutes; "
               "/api/watch/brief builds My day and My week from fixed sentences, /api/watch/merken keeps a dictated "
               "sentence in memory (with the place to about 100 m only with its own switch). /api/watch/chats and "
               "/api/watch/chat show the latest chats (no private ones) and send a tapped or dictated reply through "
               "chats.send; up to {pebblewatch.REPLY_MAX} suggestions of the model pass the fixed check "
               "pebblewatch.reply_clean. /api/watch/fern switches only devices on the own list with fixed buttons "
               "(never with a smart home code word), /api/watch/gesundheit keeps steps, pulse and sleep sealed in the "
               "profile, never for the model.")),
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
            ("{watch.FOLLOW_MAX}", ("Nachfragen zum Antippen auf der Uhr", "follow-ups to tap on the watch"), "watch.FOLLOW_MAX"),
            ("{pebblewatch.AGENDA_MAX}", ("Erinnerungen und Timer auf der Uhr", "reminders and timers on the watch"),
             "pebblewatch.AGENDA_MAX"),
        ],
        "einstellen": [
            ("Funktionen → Telegram: Bot-Token und Schalter (Standard aus).", "Features → Telegram: bot token and switch (default off)."),
            ("Ich → Telegram: den eigenen Chat verknüpfen; Sprachnachrichten, private Daten, Smart Home und Mitteilungen "
             "einzeln erlauben.",
             "Me → Telegram: link the own chat; allow voice messages, private data, smart home and notes one by one."),
            ("Ich → Pebble-Uhr: die Uhr koppeln, die Adresse unterwegs (nur https), die Schnellbefehle, die Geräte der "
             "Fernbedienung und die eigenen Schritte, Puls und Schlaf (ansehen, löschen).",
             "Me → Pebble watch: pair the watch, the address on the road (https only), the quick commands, the devices of "
             "the remote and the own steps, pulse and sleep (see, delete)."),
            ("Funktionen → Pebble-Uhr: Nachfragen, Schnellbefehle, Erinnerungen am Handgelenk, Spark-Zifferblatt, Mein Tag "
             "und meine Woche, Meldungen für Admins, Schnell merken und Ort beim Merken, Nachrichten, Antwortvorschläge, "
             "Fernbedienung, Schritte, Puls und Schlaf, je ein Schalter (Standard aus).",
             "Features → Pebble watch: follow-ups, quick commands, reminders on the wrist, Spark watchface, my day and my "
             "week, notes for admins, quick notes and place with a note, messages, reply suggestions, remote, steps, pulse "
             "and sleep, one switch each (default off)."),
            ("Funktionen → Ein Gespräch für alle Kanäle: alle Kanäle schreiben ins Hauptgespräch des Tages.",
             "Features → One conversation for all channels: every channel writes into the day's main conversation."),
        ],
        "sehen": [
            ("Logs → Anfragen: Eingang „Telegram“, „Siri“ oder „Uhr“, ohne Inhalt.",
             "Logs → Requests: input „Telegram“, „Siri“ or „Uhr“, without content."),
            ("Zustand → Live: die laufende Anfrage im Bild.", "Status → Live: the running request in the picture."),
            ("Zustand → Logs: die Zeilen „watch: sync“, „watch: reminder …“ und „watch: Nachfragen“, ohne Inhalt.",
             "Status → Logs: the lines „watch: sync“, „watch: reminder …“ and „watch: Nachfragen“, without content."),
        ],
        "code": [
            ("telegram.loop", ("fragt Telegram, ruht bei Notaus", "polls Telegram, rests with the kill switch")),
            ("telegram.handle", ("eine Nachricht: Verknüpfung, Sperren, Befehle, Sprache", "one message: link, locks, commands, voice")),
            ("telegram.ask", ("Frage an den Chat, Antwort einsammeln, speichern", "question to the chat, collect the answer, store")),
            ("telegram.transcribe", ("Sprachnachricht über ffmpeg zur Spracherkennung", "voice message through ffmpeg to recognition")),
            ("chat.siri_ask", ("Siri: Profil aus dem Schlüssel", "Siri: profile from the key")),
            ("chat.text_ask", ("Siri und Begleiter: Frage, Antwort, Verlauf, beim Begleiter dazu die Karten (desk_cards)", "Siri and companion: question, answer, history, for the companion also the cards (desk_cards)")),
            ("chat.watch_ask", ("Uhr: Antwort als Auftrag starten", "watch: start the answer as a job")),
            ("chat._watch_run", ("Uhr: Antwort in den Verlauf", "watch: the answer into the history")),
            ("watch.run", ("liest den Strom in den Uhr-Auftrag", "reads the stream into the watch job")),
            ("watch.poll", ("Text und Ton stückweise", "text and sound piece by piece")),
            ("watch.follow_ups", ("Nachfragen vom Modell, mit Zeitgrenze", "follow-ups from the model, with a time limit")),
            ("watch.follow_clean", ("feste Prüfung der Nachfragen", "fixed check of the follow-ups")),
            ("pebblewatch.watch_sync", ("Schnellbefehle und Erinnerungen für die Uhr", "quick commands and reminders for the watch")),
            ("pebblewatch.watch_reminder", ("Erinnerung auf der Uhr: gespielt, später, beenden, +1, Stopp",
                                            "reminder on the watch: played, later, end, +1, stop")),
            ("pebblewatch.watch_blick", ("was das Spark-Zifferblatt zeigt", "what the Spark watchface shows")),
            ("pebblewatch.watch_brief", ("Mein Tag und Meine Woche, feste Sätze", "My day and My week, fixed sentences")),
            ("pebblewatch.watch_note", ("Schnell merken ins Gedächtnis", "quick note into memory")),
            ("pebblewatch.watch_chat", ("ein Chat auf der Uhr, mit Antworten", "one chat on the watch, with replies")),
            ("pebblewatch.watch_chat_send", ("Antwort von der Uhr in den Chat", "reply from the watch into the chat")),
            ("pebblewatch.reply_clean", ("feste Prüfung der Antwortvorschläge", "fixed check of the reply suggestions")),
            ("pebblewatch.watch_remote_act", ("Fernbedienung: eigene Liste, feste Tasten", "remote: own list, fixed buttons")),
            ("pebblewatch.watch_health", ("Schritte, Puls, Schlaf versiegelt ins Profil", "steps, pulse, sleep sealed into the profile")),
            ("verlauf.keep", ("Tagesgespräch des Kanals oder Hauptgespräch", "the channel's day conversation or the main one")),
        ],
        "tests": ["test_telegram_tasks", "test_pebble", "test_verlauf_sync", "test_notaus"],
        "heute": [],
    },

    # ------------------------------------------------------------------ Lautsprecher, HA
    "lautsprecher": {
        "stand": "b7fb8cbd82",
        "bezug": {
            "wyoming.MAX_CONNS": ["s5"], "esp32.ota": ["s1"], "esp32._activation": ["s2"],
            "esp32.same_board": ["s3"], "esp32.speaker_ws": ["s5"], "esp32.still_allowed": ["s5"],
            "esp32.Session.run_answer": ["s10"], "esp32.Session.code_gate": ["s9"], "esp32.Session.speak": ["s11"],
            "esp32.remember": ["s12"], "wyoming.settings": ["s5"], "wyoming.handle": ["s5"],
            "wyoming._session": ["s7", "s11"], "regeln": ["s5", "s9"],
            "telefon.Call.start": ["s5"], "telefon.Call.outside": ["s5"], "telefon.Call.pin": ["s9"], "telefon_ich.try_code": ["s5"], "telefon_ich.pin_attempt": ["s9"],
            "telefon_ich.FAILS": ["s9"], "telefon.MAX_CALLS": ["s5"], "telefon.MAX_CALL": ["s10"], "telefon.Call.voice_result": ["s9"], "telefon.Call._chat": ["s10", "s11"],
            "telefon.Call.dial": ["s5"], "telefon_anruf.target": ["s5"], "telefon_anruf.call_back": ["s9"],
            "telefon_anruf.alarm_tick": ["s5"], "telefon_anruf.DAY_LIMIT": ["s5"], "telefon_anruf.ALARM_AFTER": ["s5"],
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
               "{spkcode.LOCK|min} Minuten lang nicht mehr. Ohne sichere Stimme gibt es nur Allgemeines. Eine sichere "
               "Stimme in einer kurzen Frage ohne Persönliches bekommt die Rechte des Inhabers wie ohne Codewort.",
               "With the speaker code word: an unsure voice asking for personal things is asked for the code word, "
               "the question waits. After {spkcode.FAILS} wrong tries the speaker does not ask for {spkcode.LOCK|min} "
               "minutes. Without a sure voice there are only general things. A sure voice in a short question asking "
               "nothing personal gets the owner's rights as without the code word."),
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
            (("Wartungspause der Sprachausgabe", "Maintenance pause of the speech output"), ["s5", "s10", "s11"],
             ("Antwort auf dem Display, zu hören der kurze Wartungssatz aus einer Datei (sonst ein Ton); bei pausierter "
              "Spracherkennung sagt der Lautsprecher den Satz gleich nach dem Weckwort.",
              "Answer on the display, the short maintenance sentence from a file to hear (else a tone); with the speech "
              "recognition paused the speaker says the sentence right after the wake word.")),
            (("Notbetrieb mit Parakeet", "Emergency mode with Parakeet"), ["s5", "s10", "s11"],
             ("Modell-Rechner weg: Parakeet auf dem Panel-Rechner hört, ein fester Befehl („Licht an“, „Wie spät ist es?“) "
              "wird ohne Modell ausgeführt; zu hören sind vorher gemachte Sätze und Bausteine (notbetrieb.ton).",
              "Model computer gone: Parakeet on the panel computer hears, a fixed command (“lights on”, “what time is it?”) "
              "runs without a model; to hear are sentences and building blocks made before (notbetrieb.ton).")),
        ],
        "regeln": [
            [("Weg", "Way"), ("Wer darf", "Who may"), ("Was geht", "What works"), ("Persönliches", "Personal things")],
            [("ESP32-Lautsprecher", "ESP32 speaker"), ("Schlüssel eines Lautsprechers, Profil nicht gesperrt", "a speaker's key, profile not blocked"),
             ("Fragen wie das Profil", "questions as the profile"), ("nur bei sicherer Stimme oder Codewort", "only with a sure voice or code word")],
            [("Home Assistant Assist", "Home Assistant Assist"), ("Adressen in der Erlaubt-Liste des Admins", "addresses in the admin's allow list"),
             ("nur Ton zu Text und Text zu Ton", "only sound to text and text to sound"), ("nie", "never")],
            [("Telefon, Mobilteil eines Profils", "phone, a profile's handset"), ("interne Nummer, vom Admin zugeordnet", "internal number, assigned by the admin"),
             ("Fragen wie das Profil", "questions as the profile"), ("nur bei sicherer Stimme", "only with a sure voice")],
            [("Telefon, gemeinsames Mobilteil", "phone, shared handset"), ("interne Nummer als gemeinsam", "internal number as shared"),
             ("die Stimme wählt das Profil, sonst Gast", "the voice picks the profile, else guest"), ("nur bei sicherer Stimme", "only with a sure voice")],
            [("Telefon von außen oder nicht zugeordnet", "phone from outside or not assigned"), ("niemand (Gast nur mit Admin-Schalter)", "nobody (guest only with the admin switch)"),
             ("abgewiesen oder ein Satz", "refused or one sentence"), ("nie", "never")],
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
                 "geprüft, bevor gelesen wird; nur Tonformate, die ein Mikrofon schickt. „describe“ antwortet sofort mit der "
                 "Stimmenliste aus dem Speicher (alle {wyoming.VOICES_TTL|min} Minuten neu gelesen), weil Home Assistant "
                 "nur 1 Sekunde wartet.",
                 "Home Assistant only gets „sound in, text out“ and „text in, sound out“, no language model, no "
                 "profile, nothing personal. At most {wyoming.MAX_CONNS} connections at once; lengths are checked "
                 "before reading; only sound formats a microphone sends. „describe“ answers at once with the voice list from "
                 "memory (read again every {wyoming.VOICES_TTL|min} minutes), because Home Assistant waits only 1 second."),
                ("Abgewiesene Adressen erscheinen auf Zustand → Live unter Eingang und als Vorschlag für die Liste.",
                 "Refused addresses show on Status → Live under input and as a suggestion for the list."),
            ]),
            (("Den Spark anrufen (Telefon)", "Calling the Spark (phone)"), [
                ("Der Spark meldet sich an der Telefonanlage im Heimnetz als IP-Telefon an (SIP über UDP, Port "
                 "{telefon.SIP_PORT}, Digest-Anmeldung, alle {telefon.REG_EXPIRES|min} Minuten erneuert). Nachrichten nimmt er "
                 "nur von der Adresse der Anlage, höchstens {telefon.MAX_MSG} Bytes und {telefon.PER_SECOND} je Sekunde; "
                 "Ton (RTP) nur von der Adresse aus deren SDP, die im Heimnetz liegen muss. Den Ton hinaus schickt ein eigener "
                 "Faden im 20-ms-Takt, unabhängig von der Ereignis-Schleife des Panels; Sprache beginnt erst, wenn "
                 "{telefon.PREBUF} Pakete bereitliegen oder der Satz fertig ist, nach jeder Lücke wartet er auf mehr "
                 "(höchstens {telefon.PREBUF_MAX}). Die Logzeile am Ende nennt Lücken, verspätete Pakete und die "
                 "Rechenzeit fürs Kodieren je Sekunde Ton.",
                 "The Spark signs in at the telephone system in the home network as an IP phone (SIP over UDP, port "
                 "{telefon.SIP_PORT}, digest sign-in, renewed every {telefon.REG_EXPIRES|min} minutes). It takes messages "
                 "only from the system's address, at most {telefon.MAX_MSG} bytes and {telefon.PER_SECOND} per second; "
                 "sound (RTP) only from the address in its SDP, which has to be in the home network. The sound out goes from "
                 "a thread of its own at a 20 ms beat, independent of the panel's event loop; speech starts only once "
                 "{telefon.PREBUF} packets are ready or the sentence is complete, after every gap it waits for more (at "
                 "most {telefon.PREBUF_MAX}). The log line at the end names gaps, late packets and the time spent "
                 "encoding per second of sound."),
                ("Ein Anruf läuft wie eine Frage am Lautsprecher: Satzende mit derselben Pegelprüfung, Spracherkennung, "
                 "Stimmprüfung, Chat mit dem Profil (gesetzt nur vom Panel), Antwort in G.722 oder G.711 zurück. Ein "
                 "Mobilteil eines Profils bekommt Persönliches nur bei sicherer Stimme; am gemeinsamen Telefon wählt die "
                 "Stimme das Profil. Nach {telefon.QUIET_ASK} Sekunden Stille „Noch etwas?“, nach weiteren "
                 "{telefon.QUIET_END} legt er auf; höchstens {telefon.MAX_CALL|min} Minuten. Ein Abschied („Tschüss“, „Danke, "
                 "das war's“, „Ich lege auf“, auch mitten in der Antwort) und direkt nach „Noch etwas?“ ein „Nein danke“ "
                 "beenden das Gespräch: „Tschüss!“, dann legt der Spark selbst auf (feste Wortlisten BYE_WORDS und "
                 "NO_MORE, nie das Modell). Legt das Telefon auf, beendet sein BYE den Anruf sofort; kommt keins an "
                 "(Router, Leitung), legt der Spark nach {telefon.RTP_GONE} Sekunden ohne jedes Tonpaket auf, außer "
                 "das Telefon hat gehalten.",
                 "A call runs like a question at a speaker: end of sentence with the same level check, speech "
                 "recognition, voice check, chat with the profile (set only by the panel), answer back in G.722 or G.711. "
                 "A profile's handset gets personal things only with a sure voice; at the shared phone the voice picks "
                 "the profile. After {telefon.QUIET_ASK} seconds of silence „Noch etwas?“, after another "
                 "{telefon.QUIET_END} it hangs up; at most {telefon.MAX_CALL|min} minutes. A goodbye („Tschüss“, „Danke, "
                 "das war's“, „Ich lege auf“, also in the middle of an answer) and right after „Noch etwas?“ a „Nein "
                 "danke“ end the call: „Tschüss!“, then the Spark hangs up itself (fixed word lists BYE_WORDS and "
                 "NO_MORE, never the model). When the phone hangs up, its BYE ends the call at once; if none arrives "
                 "(router, line), the Spark hangs up after {telefon.RTP_GONE} seconds without any sound packet, unless "
                 "the phone put the call on hold."),
                ("Von außen: eine eigene Nummer, die unter Ich → Telefon auf ihren Code wartet, tippt ihn "
                 "({telefon_ich.CODE_LEN} Ziffern, {telefon_ich.CODE_SECONDS|min} Minuten, {telefon_ich.CODE_TRIES} "
                 "Versuche), dann legt er auf. Mit „Anrufe von außen“ wählt eine bestätigte Nummer ihr Profil, "
                 "Persönliches aber nur bei sicherer Stimme oder PIN, weil sich Nummern fälschen lassen; mit „Gäste“ "
                 "auch unbekannte Nummern als Gast, höchstens {telefon.GUESTS} am Tag. Logs und Live nennen nie eine "
                 "Nummer von außen.",
                 "From outside: an own number waiting for its code under Me → Phone types it ({telefon_ich.CODE_LEN} "
                 "digits, {telefon_ich.CODE_SECONDS|min} minutes, {telefon_ich.CODE_TRIES} tries), then it hangs up. "
                 "With „Anrufe von außen“ a confirmed number picks its profile, but personal things only with a sure "
                 "voice or the PIN, because numbers can be forged; with guests also unknown numbers as a guest, at most "
                 "{telefon.GUESTS} a day. Logs and Live never name a number from outside."),
                ("Die Telefon-PIN (Ziffern, dann #) steht für den Rest des Gesprächs für die Stimme: am Mobilteil für "
                 "dessen Profil, am gemeinsamen Telefon für das Profil, dem sie gehört. {telefon_ich.FAILS} falsche in "
                 "{telefon_ich.FAIL_WINDOW|min} Minuten sperren sie an diesem Telefon {telefon_ich.LOCK|min} Minuten. "
                 "Gespeichert als gesalzener Hash im Tresor; nie gesprochen, angezeigt oder im Log.",
                 "The phone PIN (digits, then #) stands for the voice for the rest of the call: on a handset for its "
                 "profile, at the shared phone for the profile it belongs to. {telefon_ich.FAILS} wrong ones in "
                 "{telefon_ich.FAIL_WINDOW|min} minutes lock it at that phone for {telefon_ich.LOCK|min} minutes. Stored "
                 "as a salted hash in the vault; never spoken, shown or logged."),
                ("Der Spark ruft an (Schalter „Der Spark ruft an“): Weckruf und Erinnerung, die ein Profil selbst "
                 "bestellt (Werkzeug anruf_planen, nur Zeit, Art und Text, nie eine Nummer), der Rückruf und der Alarm. "
                 "Er ruft nur das zugeordnete Mobilteil oder, mit „auch bestätigte eigene Nummern“, die bestätigte "
                 "Nummer des Profils an; höchstens {telefon_anruf.DAY_LIMIT} Anrufe je Profil und Tag, nie bei „Nicht "
                 "stören“; nicht abgehoben einmal nach {telefon_anruf.RETRY|min} Minuten, dann eine Mitteilung. Eine "
                 "Erinnerung liest er erst vor, wenn Stimme oder PIN passen. Rückruf: Wer von außen mit unsicherer "
                 "Stimme „Ruf mich zurück“ sagt, wird unter der hinterlegten bestätigten Nummer angerufen, eine "
                 "gefälschte Nummer erreicht so nie den Fälscher.",
                 "The Spark calls (switch „Der Spark ruft an“): wake-up call and reminder a profile orders itself (tool "
                 "anruf_planen, only time, kind and text, never a number), the call back and the alarm. It only calls the "
                 "assigned handset or, with „also confirmed own numbers“, the profile's confirmed number; at most "
                 "{telefon_anruf.DAY_LIMIT} calls per profile and day, never during „Nicht stören“; not answered once more "
                 "after {telefon_anruf.RETRY|min} minutes, then a note. It reads a reminder only once voice or PIN fit. "
                 "Call back: whoever calls from outside with an unsure voice and says „Ruf mich zurück“ is called at the "
                 "stored confirmed number, so a forged number never reaches the forger."),
                ("Alarm bei Dienstausfall: Ist ein Dienst {telefon_anruf.ALARM_AFTER|min} Minuten oder länger weg, ruft "
                 "der Spark den Admin an, höchstens einmal in {telefon_anruf.ALARM_EVERY|min} Minuten. Nie zwischen 22 "
                 "und 7 Uhr (dienstwacht.NIGHT, für Anrufe immer), in den Ruhezeiten des Admins oder bei „Nicht "
                 "stören“; ist der Dienst danach noch weg, kommt der Anruf dann.",
                 "Alarm on outages: if a service is gone {telefon_anruf.ALARM_AFTER|min} minutes or longer, the Spark "
                 "calls the admin, at most once in {telefon_anruf.ALARM_EVERY|min} minutes. Never between 10 pm and 7 am "
                 "(dienstwacht.NIGHT, always for calls), in the admin's quiet hours or during „Nicht stören“; if the "
                 "service is still gone afterwards, the call comes then."),
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
            ("{telefon.MAX_CALLS}", ("Anrufe gleichzeitig höchstens", "calls at once at most"), "telefon.MAX_CALLS"),
            ("{telefon.MAX_CALL|min}", ("Minuten dauert ein Anruf höchstens", "minutes a call lasts at most"), "telefon.MAX_CALL"),
            ("{telefon_ich.FAILS}", ("falsche Telefon-PINs bis zur Sperre", "wrong phone PINs until the lock"), "telefon_ich.FAILS"),
            ("{telefon_anruf.DAY_LIMIT}", ("Anrufe vom Spark je Profil und Tag", "calls from the Spark per profile and day"),
             "telefon_anruf.DAY_LIMIT"),
            ("{telefon_anruf.ALARM_AFTER|min}", ("Minuten Ausfall bis zum Alarm-Anruf", "minutes of outage until the alarm call"),
             "telefon_anruf.ALARM_AFTER"),
        ],
        "einstellen": [
            ("Funktionen → Eigene Lautsprecher: Lautsprecher für alle Profile (Standard aus).",
             "Features → Own speakers: speakers for every profile (default off)."),
            ("Ich → Lautsprecher: einrichten, Code eintippen, Raum, Lautstärke, Prüfen und das eigene Codewort.",
             "Me → Speakers: set up, type the code, room, volume, check and the own code word."),
            ("Funktionen → Home Assistant Assist: Wyoming an und die erlaubten Adressen.",
             "Features → Home Assistant Assist: Wyoming on and the allowed addresses."),
            ("Funktionen → Telefon: Assistent mit vier Schritten, Mobilteile zuordnen, Testanruf, Anrufe von "
             "außen, unbekannte Anrufer als Gast, der Spark ruft an, Anruf bei Dienstausfall.",
             "Features → Phone: wizard with four steps, assign handsets, test call, calls from outside, "
             "unknown callers as guests, the Spark calls, call on outages."),
            ("Ich → Telefon: eigene Rufnummern mit Code bestätigen, Telefon-PIN, Anrufe vom Spark erlauben und geplante "
             "löschen, Telefonate löschen.",
             "Me → Phone: confirm own phone numbers with a code, phone PIN, allow calls from the Spark and delete planned "
             "ones, delete calls."),
        ],
        "sehen": [
            ("Ich → Lautsprecher → Prüfen: was der Lautsprecher zuletzt getan hat (nur im Speicher, weg nach einem Neustart).",
             "Me → Speakers → Check: what the speaker did lately (memory only, gone after a restart)."),
            ("Zustand → Live: Anfragen vom Lautsprecher und von Home Assistant, abgewiesene Wyoming-Adressen unter Eingang.",
             "Status → Live: requests from a speaker and from Home Assistant, refused Wyoming addresses under input."),
            ("Zustand → Live: die Telefonanlage mit angemeldet ja/nein und den Anrufen von heute in Zahlen.",
             "Status → Live: the telephone system with signed in yes/no and today's calls in numbers."),
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
            ("telefon.Call.start", ("wer anruft: intern, Profil, gesperrt, besetzt", "who calls: internal, profile, blocked, busy")),
            ("telefon.Call.outside", ("von außen: Code, bekannte Nummer, Gast", "from outside: code, known number, guest")),
            ("telefon.Call.pin", ("Telefon-PIN prüfen, Sperre", "check the phone PIN, lock")),
            ("telefon_ich.try_code", ("Code einer eigenen Nummer", "code of an own number")),
            ("telefon_ich.pin_attempt", ("PIN je Telefon zählen und sperren", "count and lock the PIN per phone")),
            ("telefon.Call.voice_result", ("Stimme wählt oder bestätigt das Profil", "the voice picks or confirms the profile")),
            ("telefon.Call._chat", ("Chat mit dem Profil, Ton zurück", "chat with the profile, sound back")),
            ("telefon.Call.dial", ("der Spark ruft an: INVITE, Digest, Abbruch", "the Spark calls: INVITE, digest, cancel")),
            ("telefon_anruf.target", ("wen er anruft: Mobilteil oder bestätigte Nummer", "whom it calls: handset or confirmed number")),
            ("telefon_anruf.call_back", ("Rückruf nur an die bestätigte Nummer", "call back only to the confirmed number")),
            ("telefon_anruf.alarm_tick", ("Alarm-Anruf mit Ruhezeiten", "alarm call with quiet hours")),
        ],
        "tests": ["test_esp32", "test_wyoming", "test_telefon", "test_notaus", "test_echo"],
        "heute": [],
    },

    # ------------------------------------------------------------------ MCP-Programme
    "mcpc": {
        "stand": "f2f838ba09",
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
               "Das Profil bekommt eine Mitteilung und entscheidet unter Ich → Spark als MCP-Server innerhalb von "
               "{mcpserver.ACTION_SECONDS|min} Minuten; erst dann führt das Panel es aus. Bei Notaus oder gesetztem "
               "Smart-Home-Codewort schaltet ein MCP-Programm nichts.",
               "Smart home, reminder and appointment are only proposed (at most {mcpserver.MAX_WAITING} open). The "
               "profile gets a notice and decides under Me → Spark as MCP server within {mcpserver.ACTION_SECONDS|min} "
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
            ("Ich → Spark als MCP-Server: Verbindungen anlegen, Werkzeuge wählen, Vorschläge bestätigen oder ablehnen.",
             "Me → Spark as MCP server: make connections, pick tools, confirm or decline proposals."),
        ],
        "sehen": [
            ("Zustand → Live: jeder Werkzeug-Aufruf als Anfrage des Programms, von außen unter „Über das Internet“.",
             "Status → Live: every tool call as a request of the program, from outside under „Über das Internet“."),
            ("Ich → Spark als MCP-Server: die letzten Vorschläge mit ihrem Stand.",
             "Me → Spark as MCP server: the latest proposals with their state."),
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
}
