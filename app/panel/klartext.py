"""Klartext für Zustand → Verbessern (Dominik 2026-10-14: „sprechender machen … warum genau, woher genau, und
Behebungsempfehlung“, Plan „Verbessern verständlicher“ 1–6).

Für jeden Fall eine Karte mit vier Teilen in festen Sätzen: was passiert ist, woher es kommt (Gerät, Zeit,
Werkzeug, Anfrage), warum (der Befund, befund.py) und was hilft. Dazu die eine Quelle für die Klartexte der
Fehlercodes einer Anfrage (Logs → Anfragen, Erklären, Verbessern) und der Fehlerbereiche aus Logs → Diagnose, und die
lesbaren Namen der Einstellungen für die Ideen des Sprachmodells.

Alles hier sind feste Sätze, Werkzeug- und Gruppennamen und Zahlen. Nie Worte einer Frage oder Antwort, nie etwas,
das ein Modell geschrieben hat; die Wege („Zustand → Dienste“) werden auf der Seite zu Sprung-Links.
"""
import re

# error code of a request (tracelog fail: chat.py tts_refusal, llm_error_code, docmake) ->
# (what, de, en), (typical cause, de, en), (what helps, de, en), service of berater.UMGEBUNG or ""
CODES = {
    "tts_http": (("Die Sprachausgabe hat einen Teil der Antwort abgelehnt, ab da kam die Antwort nur als Text.",
                  "The speech output refused part of the answer; from there the answer came as text only."),
                 ("Die Sprachausgabe hat einen Satz nicht angenommen, meist wegen ungewöhnlicher Zeichen darin.",
                  "The speech output did not take a sentence, mostly because of unusual characters in it."),
                 ("Unter Zustand → Logs → Anfragen die Anfrage öffnen und den Schritt der Sprachausgabe ansehen.",
                  "Open the request under Status → Logs → Requests and look at the speech output's step."), "sprechen"),
    "tts_voice": (("Die Sprachausgabe kennt die eingestellte Stimme nicht, die Antwort kam nur als Text.",
                   "The speech output does not know the chosen voice; the answer came as text only."),
                  ("Die Stimme des Profils fehlt in der Sprachausgabe, etwa nach einem Update oder Umbenennen.",
                   "The profile's voice is missing in the speech output, for example after an update or a rename."),
                  ("Die Stimme des Profils neu wählen.", "Choose the profile's voice again."), "sprechen"),
    "tts_long": (("Ein Teil der Antwort war zu lang für die Sprachausgabe, ab da kam sie nur als Text.",
                  "Part of the answer was too long for the speech output; from there it came as text only."),
                 ("Ein Satz war länger, als die Sprachausgabe auf einmal spricht.",
                  "A sentence was longer than the speech output speaks at once."),
                 ("Kommt es öfter vor, als Meldung vorbereiten; die Antwort kam vollständig als Text.",
                  "If it happens often, prepare a report; the whole answer came as text."), ""),
    "tts_error": (("Die Sprachausgabe brach mitten in der Antwort ab.", "The speech output stopped in the middle of the answer."),
                  ("Der Dienst der Sprachausgabe ist mitten im Sprechen ausgestiegen.",
                   "The speech output's service dropped out while speaking."),
                  ("Unter Zustand → Dienste nachsehen, ob die Sprachausgabe läuft.",
                   "Check under Status → Services whether the speech output runs."), "sprechen"),
    "tts_down": (("Die Sprachausgabe war nicht erreichbar, die Antwort kam nur als Text.",
                  "The speech output could not be reached; the answer came as text only."),
                 ("Der Dienst der Sprachausgabe lief nicht oder startete gerade neu.",
                  "The speech output's service was not running or was just restarting."),
                 ("Unter Zustand → Dienste nachsehen, ob die Sprachausgabe läuft.",
                  "Check under Status → Services whether the speech output runs."), "sprechen"),
    "tts_behind": (("Die Sprachausgabe kam mit dem Text nicht hinterher, es gab Pausen.",
                    "The speech output could not keep up with the text; there were gaps."),
                   ("Die Sprachausgabe war ausgelastet oder der erste Ton kam sehr früh.",
                    "The speech output was busy or the first sound came very early."),
                   ("Unter Zustand → Überblick ansehen, was die Sprachausgabe zu der Zeit ausgelastet hat.",
                    "Look under Status → Summary at what kept the speech output busy at that time."), "sprechen"),
    "llm_down": (("Das Sprachmodell war nicht erreichbar.", "The language model could not be reached."),
                 ("Das Sprachmodell (qwen38) lief nicht oder startete gerade neu.",
                  "The language model (qwen38) was not running or was just restarting."),
                 ("Unter Zustand → Dienste nachsehen, ob das Sprachmodell läuft. qwen38 gehört nicht zum Spark: dort "
                  "nichts ändern, nur nachsehen.", "Check under Status → Services whether the language model runs. "
                  "qwen38 is not part of the Spark: change nothing there, only look."), "sprachmodell"),
    "llm_slow": (("Das Sprachmodell hat nicht rechtzeitig geantwortet.", "The language model did not answer in time."),
                 ("Das Sprachmodell war ausgelastet, oft weil gleichzeitig etwas anderes lief.",
                  "The language model was busy, often because something else ran at the same time."),
                 ("Unter Zustand → Überblick ansehen, was das Sprachmodell zu der Zeit belegt hat.",
                  "Look under Status → Summary at what kept the language model busy at that time."), "sprachmodell"),
    "llm_auth": (("Das Sprachmodell hat die Anmeldung abgelehnt.", "The language model refused the login."),
                 ("Der Schlüssel für das Sprachmodell passt nicht mehr.", "The key for the language model no longer fits."),
                 ("Unter Einstellungen → Sprachmodell Adresse und Schlüssel prüfen.",
                  "Check address and key under Settings → Language model."), "sprachmodell"),
    "llm_model": (("Das eingestellte Sprachmodell gibt es dort nicht.", "The chosen language model does not exist there."),
                  ("Der eingestellte Modellname fehlt beim Sprachmodell, etwa nach einem Modellwechsel.",
                   "The chosen model name is missing at the language model, for example after a model change."),
                  ("Unter Einstellungen → Sprachmodell den Namen des Modells prüfen.",
                   "Check the model's name under Settings → Language model."), "sprachmodell"),
    "llm_error": (("Das Sprachmodell hat einen Fehler gemeldet.", "The language model reported an error."),
                  ("Das Sprachmodell hat die Anfrage mit einem Fehler beantwortet.",
                   "The language model answered the request with an error."),
                  ("Unter Zustand → Logs → Diagnose die Fehlerzeile zur selben Zeit ansehen.",
                   "Look at the error line of the same time under Status → Logs → Diagnosis."), "sprachmodell"),
    "docmake": (("Ein Dokument wurde nicht fertig.", "A document was not finished."),
                ("Beim Bauen des Dokuments ist ein Schritt gescheitert.", "A step of building the document failed."),
                ("Unter Zustand → Logs → Anfragen die Anfrage öffnen und den gescheiterten Schritt ansehen.",
                 "Open the request under Status → Logs → Requests and look at the failed step."), ""),
    "error": (("Im Panel ist ein Fehler aufgetreten.", "An error happened in the panel."),
              ("Ein Programmfehler im Panel.", "A program error in the panel."),
              ("Unter Zustand → Logs → Diagnose die Fehlerzeile ansehen und als Meldung vorbereiten.",
               "Look at the error line under Status → Logs → Diagnosis and prepare it as a report."), ""),
}
# an error area of Logs → Diagnose („Als Fall aufnehmen“, berater.admin_area_case): key of logfilter.AREAS (+ other)
# -> (de, en, service of berater.UMGEBUNG or "")
AREAS = {
    "search": ("Die Websuche (SearXNG) meldete einen Fehler.", "The web search (SearXNG) reported an error.", "websuche"),
    "chat": ("Beim Antworten ging etwas schief, meist das Sprachmodell oder die Sprachausgabe.",
             "Something went wrong while answering, mostly the language model or the speech output.", "sprachmodell"),
    "weiche": ("Die Weiche (Einordnung der Fragen) meldete einen Fehler.", "The Weiche (sorting the questions) reported an error.", ""),
    "ha": ("Home Assistant antwortete mit einem Fehler.", "Home Assistant answered with an error.", "homeassistant"),
    "room": ("Ein Lautsprecher im Raum meldete einen Fehler.", "A speaker in a room reported an error.", ""),
    "esp32": ("Ein ESP32-Gerät meldete einen Fehler.", "An ESP32 device reported an error.", ""),
    "watch": ("Die Uhr-App meldete einen Fehler.", "The watch app reported an error.", ""),
    "telegram": ("Telegram meldete einen Fehler.", "Telegram reported an error.", "internet"),
    "mail": ("Der Mail-Server meldete einen Fehler.", "The mail server reported an error.", "mail"),
    "vorrang": ("Der Vorrang für Sprache meldete einen Fehler.", "The priority for speech reported an error.", ""),
    "wissen": ("Das eigene Archiv (Kiwix) oder die eigenen Quellen meldeten einen Fehler.",
               "The own archive (Kiwix) or the own sources reported an error.", "kiwix"),
    "anfrage": ("Das Anfragen-Log konnte nicht schreiben.", "The request log could not write.", "speicher"),
    "speicher": ("Speicher oder Platte meldeten einen Fehler.", "Memory or disk reported an error.", "speicher"),
    "other": ("Eine Fehlerzeile im Log, die zu keinem festen Bereich gehört.",
              "An error line in the log that belongs to no fixed area.", ""),
}
AREA_HELP = (("Unter Zustand → Logs → Diagnose die Fehlerzeile dieses Bereichs ansehen.",
              "Look at this area's error line under Status → Logs → Diagnosis."),
             ("Unter Zustand → Dienste nachsehen, ob der Dienst läuft.", "Check under Status → Services whether the service runs."))

# the case kinds of faelle.KINDS as a sentence of what happened ({tool}: the tool's readable name)
WAS = {
    "tool": ("Das Werkzeug „{tool}“ hat nicht geklappt.", 'The tool "{tool}" did not work.'),
    "unklar": ("Keine Regel der Weiche erkannte die Frage, darum hat der Spark im Web gesucht.",
               "No rule of the Weiche recognised the question, so the Spark searched the web."),
    "absage": ("Der Spark hat geantwortet, dass er das nicht kann.", "The Spark answered that it cannot do that."),
    "doppelt": ("Dieselbe Frage kam kurz danach noch einmal: die erste Antwort half wohl nicht.",
                "The same question came again shortly after: the first answer did not help, it seems."),
    "pruefung": ("Die Antwortprüfung hat eine Angabe zurückgehalten, die in keinem Ergebnis stand.",
                 "The answer check held back a detail that was in no result."),
    "abbruch": ("Die Antwort wurde nach dem ersten Ton abgebrochen.", "The answer was stopped after its first sound."),
    "aussetzer": ("Die Sprachausgabe kam mit dem Text nicht hinterher, es gab Pausen.",
                  "The speech output could not keep up with the text; there were gaps."),
    "erfunden": ("Die Antwort nannte Angaben, die in keinem Ergebnis standen.", "The answer named details that were in no result."),
    "angriff": ("Ein gelesener Text (Web, Mail, Dokument) enthielt wohl eine Anweisung an den Assistenten; die festen "
                "Sperren galten trotzdem.", "A text that was read (web, mail, document) probably carried an order to "
                "the assistant; the fixed locks held anyway."),
    "schlecht": ("Eine Person hat die Antwort mit 👎 bewertet.", "A person rated the answer 👎."),
    "weiche": ("Die Frage landete in der falschen Gruppe der Weiche.", "The question landed in the wrong group of the Weiche."),
    "melder": ("Ein fester Melder hat etwas bemerkt.", "A fixed detector noticed something."),
    "fehler": ("In der Anfrage ist ein Fehler aufgetreten.", "An error happened in the request."),
}
# where a case comes from (faelle.KINDS art; a code of Logs → Diagnose)
WOHER = {
    "auto": ("Vom Spark selbst erkannt, als die Antwort fertig war", "Noticed by the Spark itself when the answer was done"),
    "person": ("Von einer Person gemeldet", "Reported by a person"),
    "melder": ("Von einem festen Melder des Einstellungs-Assistenten", "From a fixed detector of the settings assistant"),
    "diagnose": ("Aus Zustand → Logs → Diagnose übernommen", "Taken over from Status → Logs → Diagnosis"),
}


def code(c):
    """The entry of CODES for an error code, by its prefix like the request list does (tts_http_413 is tts_http)."""
    c = str(c or "")
    if c in CODES:
        return CODES[c]
    k = "tts_http" if c.startswith("tts_http") else "tts_error" if c.startswith("tts") else \
        "llm_error" if c.startswith("llm") else "error"
    return CODES[k]


def code_text(c):
    """(de, en) of what an error code means; an area of Logs → Diagnose by its own sentence."""
    if c in AREAS:
        return AREAS[c][:2]
    return code(c)[0]


def for_js():
    """{code: [de, en]} for Logs → Anfragen (logs.js rerr): the same sentences as here."""
    return {k: list(v[0]) for k, v in CODES.items()}


def _tool(t, en):
    import werkzeuge
    return werkzeuge.label(t, en)


def _group(g):
    import intent
    return ", ".join(intent.LABELS.get(x, x) for x in str(g or "").split("+") if x and x != "unklar")


def card(case, found):
    """The four parts for one case: {"was", "woher", "warum", "hilft"}; each sentence as [de, en]. `found` is the
    case's Befund (befund.diagnose)."""
    import befund
    import faelle
    kind = case.get("kind") or ""
    c, tool = case.get("code") or "", case.get("tool") or ""
    if kind == "fehler" and c:
        was = list(code_text(c))
    elif kind == "melder" and case.get("title"):
        was = [WAS["melder"][0] + " " + case["title"], WAS["melder"][1] + " " + case["title"]]
    else:
        de, en = WAS.get(kind, WAS["fehler"])
        was = [de.format(tool=_tool(tool, False)), en.format(tool=_tool(tool, True))]
        if kind == "schlecht" and case.get("grund") in faelle.REASONS:
            r = faelle.REASONS[case["grund"]]
            was = [was[0][:-1] + f": {r[0]}.", was[1][:-1] + f": {r[1]}."]
        if kind == "weiche" and case.get("want"):
            g = _group(case["want"])
            was = [was[0][:-1] + f", richtig wäre {g}.", was[1][:-1] + f", right would be {g}."]
    ex = [x for x in case.get("examples") or [] if isinstance(x, dict)]
    src = "diagnose" if kind == "fehler" and c in AREAS and not any(x.get("trace") for x in ex) else \
        case.get("art") if case.get("art") in WOHER else faelle.KINDS.get(kind, ("", "", "auto"))[2]
    woher = {"src": list(WOHER.get(src, WOHER["auto"])),
             "clients": list(dict.fromkeys(x["client"] for x in ex if x.get("client")))[:4],
             "traces": [x["trace"] for x in ex if x.get("trace")][-3:],
             "tool": [_tool(tool, False), _tool(tool, True)] if tool else None,
             "group": _group(case.get("group")), "n": int(case.get("n") or 1),
             "who": len(case.get("who") or []) if isinstance(case.get("who"), list) else int(case.get("who") or 0),
             "first": case.get("t"), "last": case.get("last") or case.get("t")}
    warum = [[de, en] for de, en in zip(befund.text(found), befund.text(found, True))]
    hilft = []
    for o in found:
        h = befund.KLASSEN[o["k"]][2]
        if list(h) not in hilft:
            hilft.append(list(h))
    if kind in ("fehler", "aussetzer") and c:
        if c in AREAS:
            extra = [AREA_HELP[1], AREA_HELP[0]] if AREAS[c][2] else [AREA_HELP[0]]
        else:
            e = code(c)
            warum.append([f"Typische Ursache: {e[1][0]}", f"Typical cause: {e[1][1]}"])
            extra = [e[2]]
        for h in extra:
            if list(h) not in hilft:
                hilft.insert(0, list(h))
    return {"was": was, "woher": woher, "warum": warum, "hilft": hilft[:4]}


# ---------------------------------------------------------------- settings by their name (ideas of the model)
_PLACES = {}


def places():
    """{"sec.key": (name, way)} of every setting with a row on a page (hilfe.setting_rows), for the ideas: the admin
    reads „Anfragen verfolgen (Einstellungen → … → Logs)“, never logs.trace."""
    if not _PLACES:
        import hilfe
        pages = hilfe.cfg_pages()
        for r in hilfe.setting_rows():
            if r["id"] and "." in r["id"] and r["de"]:
                where = "Funktionen" if r["pane"] == "feat" else "Einstellungen → " + pages.get(r["pane"], r["pane"])
                _PLACES.setdefault(r["id"], (r["de"], where + " → " + r["de"]))
    return _PLACES


KEY = re.compile(r"\b([a-z]{2,12})\.([a-z][a-z0-9_]{1,40})\b")
NAME = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def readable(text, keys=()):
    """A model's idea in plain words: a setting key becomes its name in quotes, a tool's internal name its readable
    name. Keys of `keys` without a row on a page become „eine Einstellung“; everything else stays as written."""
    import werkzeuge
    p = places()

    def key(m):
        k = m.group(0)
        if k in p:
            return f"„{p[k][0]}“"
        return "eine Einstellung" if k in keys else k
    text = KEY.sub(key, str(text or ""))
    return NAME.sub(lambda m: f"„{werkzeuge.label(m.group(0))}“" if m.group(0) in werkzeuge.NAMES else m.group(0), text)
