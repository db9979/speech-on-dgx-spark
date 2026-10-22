"""Zustand → Technik, Knoten-Seiten: the pages of speech recognition, speech output and pictures
(asr, tts, bild). Rules and placeholders as in technik_seiten.py; the engine and the order are in technik_knoten.py."""
from technik_seiten import S

SEITEN = {
    "asr": {
        "stand": "1cea7b6fc6",
        "bezug": {
            "parakeet.MAX_AUDIO_S": ["s9"], "common.NOTASR_PORT": ["s9"], "common.NOTASR_IDLE": ["s9"], "admin.test_asr": ["s1"], "admin._test_asr": ["s2", "s4"],
            "common.BodyLimit": ["s5"], "common.PrioGate": ["s7"], "common.audio_rate_ok": ["s8"],
            "asr_proxy.transcriptions": ["s4"], "asr_proxy.engine_status": ["s6"], "parakeet.Recognizer": ["s9"],
            "satzende.start": ["s3"], "asr_proxy.turn": ["s3"],
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
               "nur ein angemeldetes Profil mitschicken; es geht dann als Hinweis an das Modell. Mit „Namen fürs "
               "Hören“ legt hoerwoerter.prompt die Namen der Profile, Kontakte, Räume und Geräte des Profils bei "
               "(höchstens {hoerwoerter.MAX_WORDS}, geteilte Lautsprecher nur Profilnamen).",
               "read_audio reads the recording in pieces and stops at {admin.MAX_AUDIO|mb}. Only a signed-in profile "
               "may send a wake word; it then goes to the model as a hint. With „Names for listening“ "
               "hoerwoerter.prompt adds the names of the profiles and the profile's contacts, rooms and devices (at "
               "most {hoerwoerter.MAX_WORDS}, shared speakers only profile names)."),
              ("stop", ("größer", "larger"), ("Abgelehnt (413)", "Refused (413)"))),
            S("s3", "schritt", ("Nebenbei auf dem Prozessor", "Alongside on the CPU"),
              ("Stimme, Stille, fremde Stimme", "voice, silence, other voice"),
              ("Während die Grafikkarte erkennt, laufen auf dem Prozessor schon die Sprechererkennung (wenn an und "
               "ein Profil fragt), die Raum-Stimme, die Prüfung auf eine fremde Stimme und die Messung, wie viel der "
               "Aufnahme wirklich Stimme ist. Bei einer Sprechpause mit „Satzende am Tonfall“ fragt satzende.start "
               "nebenbei Smart Turn auf dem Modell-Rechner (asr_proxy.turn), nur für eine Zahl zur Messung.",
               "While the GPU recognizes, the CPU already runs speaker identification (when on and a profile asks), "
               "the room voice, the check for an unknown voice and the measure of how much of the recording is "
               "really voice. At a speaking pause with „Turn end by tone“ satzende.start also asks Smart Turn on the "
               "model computer (asr_proxy.turn), only for a number to measure.")),
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
               "Sekunden, die an einer leisen Stelle geschnitten werden. Im Notbetrieb mit Parakeet (Panel-Rechner, "
               "Modell-Rechner weg) führt common.model_url die Aufnahme zu speech-spark-notasr auf Port "
               "{common.NOTASR_PORT}, nur für den Rechner selbst: derselbe Proxy mit Parakeet, geladen bei der ersten Aufnahme, entladen nach "
               "{common.NOTASR_IDLE|min} Minuten ohne eine.",
               "With Qwen3-ASR the recording goes to the vLLM engine, which listens on this machine only; only "
               "prompt, temperature and stream pass through, plus the context words from the settings. With "
               "Parakeet the proxy recognizes itself on the CPU, in pieces of at most {parakeet.MAX_PIECE_S} seconds "
               "cut at a quiet spot. In emergency mode with Parakeet (panel computer, model computer gone) "
               "common.model_url takes the recording to speech-spark-notasr on port {common.NOTASR_PORT}, only for the computer itself: the same "
               "proxy with Parakeet, loaded at the first recording, unloaded after {common.NOTASR_IDLE|min} minutes "
               "without one.")),
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
            ("{common.NOTASR_PORT}", ("Port von Parakeet im Notbetrieb, nur 127.0.0.1", "port of Parakeet in emergency mode, only 127.0.0.1"),
             "common.NOTASR_PORT"),
            ("{common.NOTASR_IDLE|min}", ("Minuten ohne Aufnahme, dann entlädt Parakeet im Notbetrieb",
                                          "minutes without a recording, then Parakeet unloads in emergency mode"), "common.NOTASR_IDLE"),
        ],
        "einstellen": [
            ("Einstellungen → Spracherkennung: Qwen3-ASR auf der Grafikkarte oder Parakeet auf dem Prozessor, "
             "Sprache und Kontextwörter.",
             "Settings → Speech recognition: Qwen3-ASR on the GPU or Parakeet on the CPU, language and context words."),
            ("Funktionen → Sprechererkennung: Profile an der Stimme erkennen und wie streng (Standard aus).",
             "Features → Speaker recognition: recognize profiles by their voice and how strictly (default off)."),
        ],
        "sehen": [
            ("Zustand → Verbrauch: gehörte Sekunden je Tag, Aufgabe und Profil.",
             "Status → Usage: seconds heard per day, task and profile."),
            ("Zustand → Überblick: Zustand der Engine, Anfragen, Fehler, mittlere Dauer und die Warteschlange.",
             "Status → Summary: engine state, requests, failures, average time and the queue."),
            ("Zustand → Logs → Anfragen: wie lange eine Aufnahme gewartet hat und wie viele sie überholt hat.",
             "Status → Logs → Requests: how long a recording waited and how many it overtook."),
        ],
        "code": [
            ("admin.test_asr", ("Ratenlimit und Plätze für Gäste; bei angehaltener Antwort die Entscheidung aus zwischenruf.py",
                                "rate limit and places for guests; for a paused answer the decision from zwischenruf.py")),
            ("admin._test_asr", ("der Weg im Panel: lesen, nebenbei prüfen, weiterreichen", "the way in the panel: read, check alongside, pass on")),
            ("stufe.asr_level", ("Stufe des Profils, nicht am geteilten Lautsprecher", "the profile's stage, not at a shared speaker")),
            ("common.BodyLimit", ("Größe und Schlüssel vor dem Lesen", "size and key before reading")),
            ("common.PrioGate", ("Warten nach Vorrang", "waiting by priority")),
            ("common.audio_rate_ok", ("Abtastrate aus dem Dateikopf", "sample rate from the file header")),
            ("asr_proxy.transcriptions", ("der Proxy vor der Engine", "the proxy in front of the engine")),
            ("asr_proxy.engine_status", ("bereit, lädt, Fehler oder aus", "ready, loading, error or off")),
            ("asr_proxy.turn", ("Smart Turn: wie fertig das Ende klingt, 0 bis 1", "Smart Turn: how finished the end sounds, 0 to 1")),
            ("satzende.start", ("Pause messen, nur Zahlen", "measure a pause, numbers only")),
            ("parakeet.Recognizer", ("Parakeet auf dem Prozessor", "Parakeet on the CPU")),
            ("stille.check", ("Stille und Füllwörter", "silence and fillers")),
            ("echo.check", ("die eigene Stimme des Spark", "the Spark's own voice")),
            ("speakers.identify", ("wessen Stimme, nur bei klarem Treffer", "whose voice, only on a clear match")),
        ],
        "tests": ["test_units", "test_hardening", "test_stufe", "test_stille", "test_echo", "test_stimmabdruck"],
        "heute": [("vb_asr_calls", ("Aufnahmen", "recordings")), ("vb_asr_amount", ("Sekunden gehört", "seconds heard"))],
    },

    # ------------------------------------------------------------------ Sprachausgabe
    "tts": {
        "stand": "78a22c423b",
        "bezug": {
            "textnorm.NUMBER_MODES": ["s7"], "tts_proxy.speech": ["s1"], "tts_proxy.check_reference": ["s8"],
            "tts_proxy.engine_status": ["s4"], "tts_proxy.apply_clone": ["s8"], "textnorm.speech_markdown": ["s5"],
            "textnorm.hide_secrets": ["s5"], "textnorm.clean_text": ["s6"], "textnorm.guess_language": ["s7"],
            "textnorm.speak_numbers": ["s7"], "common.PrioGate": ["s10"], "kurzref.cut_at": ["s8"],
            "kurzref.keep_words": ["s8"], "tts_proxy.shorten": ["s8"], "kurzref.MIN_S": ["s8"], "kurzref.SLACK_S": ["s8"],
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
               "Aussprache-Liste, danach schreibt speak_abbreviations Abkürzungen aus („z. B.“, „ca.“, „€/Monat“) und "
               "speak_numbers Datum, Uhrzeit, Geld, Zahlen und Einheiten (km/h, kWh, kg, GB …).",
               "When the language is Auto, guess_language guesses German or English from frequent words, so a single "
               "English word does not change the tone of the whole answer. Then the own pronunciation list applies, "
               "after that speak_abbreviations writes out abbreviations („z. B.“, „ca.“, „€/Monat“) and speak_numbers "
               "date, time, money, numbers and units (km/h, kWh, kg, GB …).")),
            S("s8", "schritt", ("Stimme wählen", "Pick the voice"),
              ("eingebaut, geklont oder beschrieben", "built in, cloned or described"),
              ("Temperatur, top_p und ein fester Seed aus den Einstellungen halten die Stimme von Satz zu Satz gleich. "
               "Ein Base-Modell spricht mit einer geklonten Stimme aus voices/ (apply_clone); ein unbekannter Name "
               "fällt auf die Standardstimme zurück. Mit „Referenz der eigenen Stimme kürzen“ (tts.ref_max_s) nimmt "
               "es statt einer langen Aufnahme ein Stück davon: kurzref.cut_at schneidet einmal an der leisesten "
               "Stelle vor der Grenze, die Spracherkennung schreibt das Stück auf, kurzref.keep_words behält davon "
               "die Wörter des eigenen Textes (mindestens {kurzref.MATCH|prozent} gleich, sonst bleibt die ganze "
               "Aufnahme). Bis das Stück fertig ist, gilt die ganze Aufnahme.",
               "Temperature, top_p and a fixed seed from the settings keep the voice the same from sentence to "
               "sentence. A Base model speaks with a cloned voice from voices/ (apply_clone); an unknown name falls "
               "back to the default voice. With „Shorten the reference of your own voice“ (tts.ref_max_s) it takes a "
               "piece of a long recording instead: kurzref.cut_at cuts once at the quietest point before the limit, "
               "speech recognition writes the piece down, kurzref.keep_words keeps the words of the own text "
               "(at least {kurzref.MATCH|prozent} alike, else the whole recording stays). Until the piece is ready, "
               "the whole recording applies.")),
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
               "klein (initial_chunk_frames), damit der Ton schnell beginnt, auch wenn mehrere Anfragen laufen. "
               "„Mehrere Stimmen gleichzeitig“ (tts.engine_decode_batch) bündelt im Decoder bis zu 2 oder 4 Stimmen "
               "mit CUDA-Graphen, „Gleichen Anfang merken“ (tts.engine_prefix_cache) lässt die Engine den gleichen "
               "Anfang der Sätze einer Stimme wiederverwenden; beide stehen auf aus (Standard von vllm-omni).",
               "The engine makes the sound. Streamed it comes back in pieces; the first piece is small on purpose "
               "(initial_chunk_frames) so the sound starts fast, also when several requests run. „Several voices at "
               "once“ (tts.engine_decode_batch) batches up to 2 or 4 voices in the decoder with CUDA graphs, "
               "„Remember the same beginning“ (tts.engine_prefix_cache) lets the engine reuse the same beginning of "
               "a voice's sentences; both are off (vllm-omni's default).")),
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
            ("{kurzref.MIN_S} s", ("bleiben von einer gekürzten Referenz mindestens", "a shortened reference keeps at least"),
             "kurzref.MIN_S"),
            ("{kurzref.SLACK_S} s", ("länger als die Grenze, erst dann wird gekürzt", "longer than the limit before it is cut"),
             "kurzref.SLACK_S"),
        ],
        "einstellen": [
            ("Einstellungen → Sprachausgabe: Modell, Standardstimme, Sprache, Text bereinigen, Zahlen vorlesen und "
             "die eigene Aussprache-Liste.",
             "Settings → Speech output: model, default voice, language, clean text, reading numbers and the own "
             "pronunciation list."),
            ("Einstellungen → Stimmen: eigene Stimmen aufnehmen, anhören und sichern (für ein Base-Modell).",
             "Settings → Voices: record, play and save own voices (for a Base model)."),
            ("Einstellungen → Sprachausgabe → Erweitert: „Referenz der eigenen Stimme kürzen“, „Mehrere Stimmen "
             "gleichzeitig“ und „Gleichen Anfang merken“ (alle aus); vorher und nachher Zustand → Prüfen → Leistung "
             "messen.",
             "Settings → Speech output → Advanced: „Shorten the reference of your own voice“, „Several voices at "
             "once“ and „Remember the same beginning“ (all off); before and after Status → Checks → Measure "
             "performance."),
        ],
        "sehen": [
            ("Zustand → Verbrauch: gesprochene Sekunden je Tag, Aufgabe und Profil.",
             "Status → Usage: seconds spoken per day, task and profile."),
            ("Zustand → Überblick: Zustand der Engines, Anfragen, Fehler, Zeit bis zum ersten Ton und die "
             "Warteschlange.",
             "Status → Summary: engine state, requests, failures, time to the first sound and the queue."),
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
            ("tts_proxy.shorten", ("Referenz einmal kürzen", "shorten the reference once")),
            ("kurzref.cut_at", ("leiseste Stelle vor der Grenze", "quietest point before the limit")),
            ("kurzref.keep_words", ("Wörter des eigenen Textes behalten", "keep the words of the own text")),
            ("common.PrioGate", ("Warten nach Vorrang", "waiting by priority")),
        ],
        "tests": ["test_units", "test_markdown", "test_hardening", "test_stufe", "test_tempo", "test_kurzref"],
        "heute": [("vb_tts_calls", ("Ausgaben", "outputs")), ("vb_tts_amount", ("Sekunden gesprochen", "seconds spoken"))],
    },

    # ------------------------------------------------------------------ Bilder malen (and Musik machen in the same box)
    "bild": {
        "stand": "f368ac974e",
        "bezug": {
            "bilder.MAX_PICS": ["s4"], "schwer.WAITING": ["s4"], "bilder.JOB_SECONDS": ["s5"], "bilder.NSFW_MAX": ["s8"],
            "schwer.run": ["s5"], "schwer.pick": ["s5"], "schwer.hint": ["s5"], "schwer.BUNDLE": ["s5"],
            "schwer.MEM_WAIT_S": ["s6"], "bedarf.OnDemand.claim": ["s6"],
            "bildmodell.STEPS": ["s7"], "bilder.keep": ["s10"], "bild_server.Engine.paint": ["s7"],
            "bedarf.OnDemand": ["s6"], "musik_server.Engine.make": ["s7"], "musik_server.finish": ["s9"],
            "musik._measure": ["s5"], "musik.start": ["s4"], "musik.keep": ["s10"], "musik._work": ["s5"], "musik.refuse_text": ["s3"],
            "musik.plan_edit": ["s4"], "musik.start_edit": ["s1"], "musik.tone": ["s1"], "musik.upload": ["s1"],
            "musik_server.edit_body": ["s7"], "musik.write_lyrics": ["s3"], "musik.MAX_VERSIONS": ["s4"], "musik.UPLOADS_DAY": ["s4"],
        },
        "kurz": ("Bilder malen macht aus einem Wunsch ein Bild, auf dem Spark selbst. Das Panel prüft den Wunsch mit "
                 "festen Regeln und gibt ihn an den Bild-Dienst, der nur auf dieser Maschine lauscht. Der lädt FLUX.2 "
                 "klein erst beim ersten Bild, prüft das fertige Bild und gibt den Speicher nach einer Ruhezeit frei.\n\n"
                 "Musik machen läuft daneben genauso: aus einem Wunsch unter Ich → Musik oder musik_machen im Gespräch "
                 "wird ein Lied (ohne Angabe instrumental, 2 Minuten). Der Musik-Dienst auf :31004 lädt ACE-Step 1.5 "
                 "nur für ein Lied, im Modell, das der Admin gewählt hat, und gibt den Speicher nach einer Ruhezeit "
                 "frei; „Musik testen“ misst jedes installierte Modell. Beide Dienste teilen die Engine bei Bedarf aus "
                 "bedarf.py. Musik bearbeiten macht aus einem eigenen Lied eine neue Fassung (Abschnitt neu, "
                 "verlängern, Musikrichtung, Remix, neuer Text) mit demselben Modell; Schneiden, Tempo und Tonart "
                 "macht der Musik-Dienst sofort mit ffmpeg, ohne Modell. Eigene Dateien nur mit dem Rechte-Haken."
                 "\n\nImmer nur eins der beiden Modelle ist geladen (Dominik 2026-10-18): Bilder und Lieder "
                 "stehen in einer Warteschlange im Panel (schwer.py); wer hinter anderen wartet, hört Platz und "
                 "ungefähre Dauer.",
                 "Painting pictures turns a wish into a picture, on the Spark itself. The panel checks the wish with "
                 "fixed rules and hands it to the picture service, which listens on this machine only. It loads FLUX.2 "
                 "klein only at the first picture, checks the finished picture and frees the memory after a quiet time.\n\n"
                 "Making music works the same way next to it: a wish under Me → Music or musik_machen in the "
                 "conversation becomes a song (instrumental and 2 minutes unless asked). The music service on :31004 "
                 "loads ACE-Step 1.5 only for a song, in the model the admin picked, and frees the memory after a quiet "
                 "time; \"Test music\" measures every installed model. Both services share the on-demand engine of "
                 "bedarf.py. Editing music turns an own song into a new version (part anew, extend, genre, remix, "
                 "new lyrics) with the same model; cutting, tempo and key the music service does at once with ffmpeg, "
                 "without a model. Own files only with the rights tick."
                 "\n\nOnly one of the two models is loaded at a time (Dominik 2026-10-18): pictures and songs "
                 "stand in one queue in the panel (schwer.py); who waits behind others hears the place and about how "
                 "long it takes."),
        "warum": ("Ein Bildmodell kann alles malen, auch Nacktes, Gewalt oder echte Menschen. Darüber entscheidet nie das "
                  "Sprachmodell, sondern feste Regeln vor und nach dem Malen. Und das Modell braucht viel gemeinsamen "
                  "Speicher: es darf das Sprachmodell und die Stimme nie verdrängen.",
                  "A picture model can paint anything, also nudity, violence or real people. The language model never "
                  "decides that; fixed rules before and after painting do. And the model needs a lot of shared "
                  "memory: it must never push out the language model or the voice."),
        "ablauf": [
            S("s1", "start", ("Ein Bildwunsch", "A picture wish"),
              ("Ich → Bilder oder bild_malen im Gespräch", "Me → Pictures or bild_malen in the conversation"),
              ("Ein Profil schreibt einen Wunsch unter Ich → Bilder, oder die Weiche-Gruppe „bild“ bietet im Gespräch "
               "das Werkzeug bild_malen an; das Modell schreibt dazu einen englischen Prompt. Bilder ändern startet "
               "ohne Werkzeug: bilder.from_turn nimmt nach fester Regel das Foto dieser Nachricht oder das Ergebnis "
               "der letzten Änderung, unter Ich → Bilder ein eigenes Bild. Alles landet in bilder.start. Schnellknöpfe "
               "(drehen, heller, schwarzweiß …) brauchen kein Modell: bilder.quick_png macht sie sofort im Panel. "
               "Ein Liedwunsch kommt genauso über Ich → Musik oder die Gruppe „musik“ mit musik_machen in musik.start; "
               "eine Änderung eines eigenen Liedes über Ich → Musik oder musik_bearbeiten in musik.start_edit (das Panel "
               "nimmt das Lied, nie das Modell), Schneiden und Tempo ohne Modell in musik.tone, eine eigene Datei mit "
               "dem Rechte-Haken in musik.upload.",
               "A profile writes a wish under Me → Pictures, or the router group \"bild\" offers the tool bild_malen in "
               "the conversation; the model writes an English prompt for it. Changing pictures starts without a "
               "tool: bilder.from_turn takes by a fixed rule the photo of this message or the result of the last "
               "change, under Me → Pictures an own picture. Everything ends in bilder.start. Quick buttons (rotate, brighter, "
               "black and white …) need no model: bilder.quick_png does them at once on the panel. "
               "A song wish comes the same way through Me → Music or the group \"musik\" with musik_machen into musik.start; "
               "a change of an own song through Me → Music or musik_bearbeiten into musik.start_edit (the panel picks "
               "the song, never the model), cutting and tempo without a model into musik.tone, an own file with the "
               "rights tick into musik.upload.")),
            S("s2", "frage", ("Funktion frei?", "Feature released?"),
              ("Admin-Schalter, keine Sperre, kein Gast", "admin switch, no block, no guest"),
              ("features.allowed fragt die Freigabe: der Admin hat Bilder malen eingeschaltet und dieses Profil nicht "
               "gesperrt. Gäste bekommen das Werkzeug nie; nach fremdem Text und bei Notaus Stufe 2 ist es gesperrt.",
               "features.allowed asks the release: the admin switched painting pictures on and did not block this profile. "
               "Guests never get the tool; after outside text and at kill switch stage 2 it is locked."),
              ("stop", "nein", ("Hinweis mit Weg zum Schalter", "Hint with the way to the switch"))),
            S("s3", "frage", ("Wunsch erlaubt?", "Wish allowed?"),
              ("Wortliste und bekannte Personen", "word list and known people"),
              ("bilder.refuse_text prüft Wunsch und Prompt gegen eine feste Wortliste (nichts Sexuelles, keine Gewalt, "
               "keine Hasssymbole) und gegen die Namen der Profile und Kontakte. Für Lieder prüft musik.refuse_text Wunsch, Beschreibung und "
               "Liedtext gegen die Wortliste und Geheimnisse, Wunsch und Beschreibung auf „im Stil von“ einem Künstler (im Gespräch mit festem Hinweis, die Beschreibung ohne Namen neu zu schicken); Namen gehen. „Text schreiben“ "
               "(musik.write_lyrics) lässt das Sprachmodell den Liedtext aus der Beschreibung schreiben und Künstlernamen in "
               "Stilwörter setzen; das Panel schneidet „im Stil von …“ heraus und lehnt ab, wenn ein Name bleibt. Das Modell kann das nicht umgehen.",
               "bilder.refuse_text checks wish and prompt against a fixed word list (nothing sexual, no violence, no "
               "hate symbols) and against the names of profiles and contacts. For songs musik.refuse_text checks wish, description and "
               "lyrics against the word list and secrets, wish and description for \"in the style of\" an artist (in the conversation with a fixed hint to send the description again without names); names are fine. \"Write lyrics\" "
               "(musik.write_lyrics) has the language model write the lyrics from the description and turn artist names "
               "into style words; the panel cuts \"in the style of …\" out and refuses if a name stays. The model cannot get around it."),
              ("stop", "nein", ("Feste Absage, nichts gemalt", "Fixed refusal, nothing painted"))),
            S("s4", "frage", ("Innerhalb der Grenzen?", "Within the limits?"),
              ("pro Tag, Platz, Warteschlange", "per day, space, queue"),
              ("Pro Profil gelten Bilder pro Tag (gleitend 24 Stunden), Platz und höchstens {bilder.MAX_PICS} Bilder; "
               "Lieder: Lieder pro Tag, Platz und längstes Lied (musik.start), je Lied höchstens {musik.MAX_VERSIONS} "
               "Fassungen, {musik.UPLOADS_DAY} eigene Dateien am Tag; jede Zahl einer Änderung prüft musik.plan_edit. Auf dem ganzen Spark warten höchstens "
               "{schwer.WAITING} schwere Aufträge, Bilder und Lieder zusammen.",
               "Per profile there are pictures per day (rolling 24 hours), space and at most {bilder.MAX_PICS} "
               "pictures; songs: songs per day, space and the longest song (musik.start), at most {musik.MAX_VERSIONS} "
               "versions per song, {musik.UPLOADS_DAY} own files a day; musik.plan_edit checks every number of a change. On the whole Spark at most "
               "{schwer.WAITING} heavy jobs wait, pictures and songs together."),
              ("stop", "nein", ("Abgelehnt mit Grund", "Refused with the reason"))),
            S("s5", "schritt", ("Warten auf Pause und Platz", "Wait for a pause and the place"),
              ("Sprache zuerst, ein Modell zur Zeit", "speech first, one model at a time"),
              ("Der Auftrag läuft im Hintergrund (bilder._work, musik._work): er wartet, bis niemand spricht (vorrang), "
               "und stellt sich in die eine Warteschlange für Bilder und Lieder (schwer.run). Die feste Regel "
               "schwer.pick nimmt den ältesten; solange die geladene Art noch wartet, kommt sie zuerst, aber höchstens "
               "{schwer.BUNDLE}-mal hintereinander, während die andere Art wartet. Ist eine andere Art dran, beendet das "
               "Panel zuerst das geladene Modell. Wer hinter anderen steht, bekommt einen festen Satz mit Platz und "
               "ungefährer Dauer (schwer.hint), die Karte zeigt „Wartet · Platz 2 von 3“. Ein Bild darf höchstens "
               "{bilder.JOB_SECONDS} Sekunden brauchen.",
               "The job runs in the background (bilder._work, musik._work): it waits until nobody speaks (vorrang) and "
               "joins the one queue for pictures and songs (schwer.run). The fixed rule schwer.pick takes the oldest; "
               "while the loaded kind still waits it goes first, but at most {schwer.BUNDLE} times in a row while the "
               "other kind waits. When another kind is next, the panel first ends the loaded model. Who stands behind "
               "others gets a fixed sentence with the place and about how long (schwer.hint), the card shows "
               "\"Waiting · place 2 of 3\". A picture may take at most {bilder.JOB_SECONDS} seconds.")),
            S("s6", "frage", ("Modell geladen?", "Model loaded?"),
              ("sonst laden, wenn genug Speicher frei ist", "else load, when enough memory is free"),
              ("bild_server.Engine.start nimmt zuerst den einen Platz (bedarf.OnDemand.claim, Sperre bedarf.lock: hält "
               "ihn der Musik-Dienst, antwortet er „belegt“) und startet sd-server als eigenen Prozess auf 127.0.0.1, "
               "aber nur, wenn genug gemeinsamer Speicher frei ist; sonst bleibt alles andere ungestört. Zu wenig "
               "Speicher beendet den Auftrag nicht: er behält seinen Platz und versucht es alle 30 Sekunden neu, "
               "höchstens {schwer.MEM_WAIT_S} Sekunden lang.",
               "bild_server.Engine.start first takes the one place (bedarf.OnDemand.claim, lock bedarf.lock: when the "
               "music service holds it, it answers \"belegt\") and starts sd-server as its own process on 127.0.0.1, "
               "but only when enough shared memory is free; otherwise everything else stays undisturbed. Too little "
               "memory does not end the job: it keeps its place and tries again every 30 seconds, for at most "
               "{schwer.MEM_WAIT_S} seconds."),
              ("stop", "nein", ("Zu lange zu wenig Speicher, abgesagt", "Too little memory for too long, given up"))),
            S("s7", "schritt", ("Malen", "Paint"),
              ("FLUX.2 klein, {bildmodell.STEPS} Schritte", "FLUX.2 klein, {bildmodell.STEPS} steps"),
              ("Die Engine malt das Bild in {bildmodell.STEPS} Schritten in der gewählten Größe; ihre eigene Ausgabe "
               "kommt nie ins Journal, weil sie den Prompt nennen würde.",
               "The engine paints the picture in {bildmodell.STEPS} steps at the chosen size; its own output never "
               "reaches the journal, because it would name the prompt.")),
            S("s8", "frage", ("Bild unbedenklich?", "Picture harmless?"),
              ("Bildprüfung nach dem Malen", "image check after painting"),
              ("bild_server.nsfw_share lässt einen Klassifikator auf der CPU das Bild prüfen. Über "
               "{bilder.NSFW_MAX} wird es verworfen; fehlt die Prüfung, zeigt das Panel nichts.",
               "bild_server.nsfw_share lets a classifier on the CPU check the picture. Above {bilder.NSFW_MAX} it is "
               "discarded; without the check the panel shows nothing."),
              ("stop", "nein", ("Verworfen, nichts gespeichert", "Discarded, nothing stored"))),
            S("s9", "schritt", ("Als KI-Bild kennzeichnen", "Mark as AI picture"),
              ("neu kodiert, mit Kennzeichen", "re-encoded, with marking"),
              ("bild_server.finish kodiert das Bild neu als PNG und schreibt hinein, dass es KI-erzeugt ist, ein "
               "geändertes Bild KI-bearbeitet (auch als IPTC-Angabe).",
               "bild_server.finish re-encodes the picture as PNG and writes into it that it is AI-made, a changed "
               "picture AI-edited (also as an IPTC entry).")),
            S("s10", "ende", ("Bild abgelegt", "Picture stored"),
              ("users/ID/bilder/, Karte, Push", "users/ID/bilder/, card, push"),
              ("Das Bild kommt mit seinem Auftrag in den Ordner des Profils (bilder.keep), die Karte im Chat und in "
               "der iPhone-App zeigt es, auch in einem wieder geöffneten Gespräch; über App oder Telegram kommt ein "
               "Push. Nach einer Ruhezeit beendet der Bild-Dienst die Engine und gibt den Speicher frei. Ein Lied liegt "
               "als MP3 unter users/ID/musik/ (musik.keep), mit Abspieler im Chat und unter Ich → Musik.",
               "The picture goes into the profile's folder with its job (bilder.keep), the card in the chat and in "
               "the iPhone app shows it, also in a conversation opened again; a push goes out through the app or "
               "Telegram. After a quiet time the picture service stops the engine and frees the memory. A song is kept "
               "as MP3 under users/ID/musik/ (musik.keep), with a player in the chat and under Me → Music.")),
        ],
        "beispiele": [
            (("Katze auf einem Skateboard", "Cat on a skateboard"),
             ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10"],
             ("Gemalt, gekennzeichnet, in der Galerie.", "Painted, marked, in the gallery.")),
            (("Bild vom eigenen Profilnamen", "Picture of the own profile name"), ["s1", "s2", "s3", "s3!"],
             ("Feste Absage, das Modell wird nicht gefragt.", "Fixed refusal, the model is not asked.")),
            (("Zu wenig Speicher frei", "Too little memory free"), ["s1", "s2", "s3", "s4", "s5", "s6", "s6!"],
             ("Nichts geladen, Sprache läuft weiter.", "Nothing loaded, speech keeps running.")),
        ],
        "zahlen": [
            ("{bilder.MAX_PICS}", ("Bilder pro Profil höchstens", "pictures per profile at most"), "bilder.MAX_PICS"),
            ("{schwer.WAITING}", ("Bilder und Lieder warten höchstens", "pictures and songs wait at most"), "schwer.WAITING"),
            ("{schwer.BUNDLE}", ("dieselbe Art höchstens hintereinander", "the same kind at most in a row"), "schwer.BUNDLE"),
            ("{schwer.MEM_WAIT_S}", ("Sekunden Warten auf Speicher höchstens", "seconds of waiting for memory at most"),
             "schwer.MEM_WAIT_S"),
            ("{bilder.NSFW_MAX}", ("Anteil der Bildprüfung, ab dem verworfen wird", "image check share above which it is discarded"),
             "bilder.NSFW_MAX"),
            ("{bildmodell.STEPS}", ("Schritte pro Bild", "steps per picture"), "bildmodell.STEPS"),
            ("{musik.MAX_VERSIONS}", ("Fassungen je Lied höchstens", "versions per song at most"), "musik.MAX_VERSIONS"),
            ("{musik.UPLOADS_DAY}", ("eigene Musikdateien am Tag höchstens", "own music files a day at most"), "musik.UPLOADS_DAY"),
            ("{bilder.JOB_SECONDS}", ("Sekunden pro Auftrag höchstens", "seconds per job at most"), "bilder.JOB_SECONDS"),
        ],
        "einstellen": [
            ("Installation: sudo ./install.sh --bild 4b-q8 (oder 4b-q4, 9b-q8, 9b-q4, none).",
             "Installation: sudo ./install.sh --bild 4b-q8 (or 4b-q4, 9b-q8, 9b-q4, none)."),
            ("Funktionen → Bilder malen: Schalter, Bilder pro Tag, Platz, längste Seite, Entladen nach Minuten, "
             "„Bild testen“.",
             "Features → Painting pictures: switch, pictures per day, space, longest side, unload after minutes, "
             "\"Bild testen\"."),
            ("Musik: sudo ./install.sh --musik 2b (oder 2b-klein, xl, none; mehrere nacheinander bleiben alle); "
             "Funktionen → Musik machen: Schalter, Modell, Lieder pro Tag, Platz, längstes Lied; Zustand → Prüfen → "
             "„Musik testen“ misst jedes installierte Modell.",
             "Music: sudo ./install.sh --musik 2b (or 2b-klein, xl, none; several in a row all stay); Features → Making "
             "music: switch, model, songs per day, space, longest song; State → Checks → \"Test music\" measures every "
             "installed model."),
            ("Funktionen → Musik machen → Musik bearbeiten: Schalter (aus); dann unter Ich → Musik am Lied „Bearbeiten“ "
             "und im Menü „⋯“ „Eigene Datei hochladen“.",
             "Features → Making music → Editing music: switch (off); then under Me → Music \"Edit\" on a song and "
             "\"Upload an own file\" in the \"⋯\" menu."),
        ],
        "sehen": [
            ("Zustand → Live: Ziel „Bilder malen“ nur mit Zahlen; Logs → Diagnose, Bereich „Bild“.",
             "State → Live: target \"Painting pictures\" with numbers only; Logs → Diagnosis, area \"Bild\"."),
            ("Zustand → Live: Ziel „Musik machen“ mit Liedern und der letzten Messung in Zahlen; Logs → Diagnose, "
             "Bereich „Musik“.",
             "State → Live: target \"Making music\" with songs and the last measurement in numbers; Logs → Diagnosis, "
             "area \"Musik\"."),
            ("Zustand → Live: unter „Im Hintergrund“ jedes Bild und Lied mit „wartet auf den Platz“ oder „wartet auf "
             "Speicher“, an den Zielen „hat den Platz“; Logs → Diagnose, Bereich „Schwere Aufträge“.",
             "State → Live: under \"In the background\" every picture and song with \"waiting for the place\" or "
             "\"waiting for memory\", at the targets \"has the place\"; Logs → Diagnosis, area \"Heavy jobs\"."),
        ],
        "code": [
            ("bilder.start", ("Wunsch annehmen", "accept a wish")),
            ("features.allowed", ("Freigabe für das Profil", "release for the profile")),
            ("bilder.refuse_text", ("Wortliste und Personen", "word list and people")),
            ("bilder._work", ("Auftrag im Hintergrund", "job in the background")),
            ("bilder.keep", ("Bild ablegen", "store the picture")),
            ("bild_server.Engine.start", ("Engine laden", "load the engine")),
            ("bild_server.Engine.paint", ("Malen", "paint")),
            ("bild_server.nsfw_share", ("Bildprüfung", "image check")),
            ("bild_server.finish", ("Kennzeichnen und neu kodieren", "mark and re-encode")),
            ("bedarf.OnDemand", ("Engine bei Bedarf, für Bild und Musik", "engine on demand, for pictures and music")),
            ("bedarf.OnDemand.claim", ("Der eine Platz auf dem Spark", "the one place on the Spark")),
            ("schwer.run", ("Warteschlange: Platz, Wechsel, Speicher", "queue: place, switch, memory")),
            ("schwer.pick", ("Wer als Nächstes dran ist", "who is next")),
            ("schwer.hint", ("Fester Satz mit Platz und Dauer", "fixed sentence with place and time")),
            ("musik_server.Engine.make", ("Ein Lied in zwei Schritten", "one song in two steps")),
            ("musik_server.finish", ("MP3 prüfen und als KI-erzeugt kennzeichnen", "check the MP3 and mark it AI-made")),
            ("musik.start", ("Liedwunsch annehmen", "accept a song wish")),
            ("musik.refuse_text", ("Wortliste, Künstler, Geheimnisse", "word list, artists, secrets")),
            ("musik.write_lyrics", ("Liedtext aus der Beschreibung, Namen zu Stilwörtern", "lyrics from the description, names to style words")),
            ("musik._work", ("Lied im Hintergrund", "song in the background")),
            ("musik.keep", ("Lied ablegen", "store the song")),
            ("musik._measure", ("Musik testen je Modell", "test music per model")),
            ("musik.start_edit", ("Änderung eines Liedes annehmen", "accept a change of a song")),
            ("musik.plan_edit", ("Jede Zahl der Änderung prüfen", "check every number of the change")),
            ("musik.tone", ("Schneiden, Tempo, Tonart ohne Modell", "cut, tempo, key without a model")),
            ("musik.upload", ("Eigene Datei mit Rechte-Haken", "own file with the rights tick")),
            ("musik_server.edit_body", ("Feste Felder für repaint und cover", "fixed fields for repaint and cover")),
        ],
        "tests": ["test_bilder", "test_musik", "test_musik_liedtext", "test_schwer"],
        "heute": [],
    },

    # ------------------------------------------------------------------ state/
}
