"""Steckbrief pro Funktion (Kritische Prüfung 2026-11-12 point 4, plan /mnt/project-files/steckbrief/plan.md): one place per
function for everything the mandatory list (guideline part 1) used to spread over many files. The lists that need a
part of it read it from here; nothing is written twice (rule 12, test_steckbrief checks that no old table still names it).

Read by (each takes only its own part, the order of its own table stays):
  features.FEATURES          feature(key)        name de/en, group, admin switches, preference, parent, Ich page, guide
  features.SPARK_ONLY        nur_spark()         a setting of the whole Spark, no function a profile uses
  werkzeuge.NAMES            werkzeug_namen()    the readable name of each tool
  live.TOOLS / TARGETS / RETURNS                 the Live node of each tool, the node itself, what it gives back
  logfilter.AREAS            log_woerter(area)   the first word of the function's journal lines
  werkzeug_abdeckung.TOOLS / BY_WORD             the tools of the function, offered only on the person's own word
  werkzeug_abdeckung.RULES / WITHOUT             ohne_werkzeug(art)  why the function has no tool
  spickzettel.KURZ           spickzettel()       an example sentence for a tool offered only on the own word
  werkzeug_abdeckung.SENTENCES saetze()          a typical request per tool
  features.DESK              desk()              the Begleiter parts that carry the function
  technik.MODULE             module()            group and German line of the function's module
  features.DESK_SKIP         begleiter()         why the Begleiter has no part of its own

The bottom layer (test_schichten.GRUND): imports no panel module. Only data, no behaviour.
Pilot „Rechnen“ (V01.1.397), group „Tempo und Genauigkeit“ (V01.1.401); every other function moves here group by
group (test_steckbrief.OHNE_ALT only shrinks). Only what a function has is written: the parts left out keep their
defaults (no tool, no Live node, no own log word, no module of its own).
"""
from typing import NamedTuple


class Steckbrief(NamedTuple):
    de: str                     # the function's name everywhere
    en: str
    gruppe: str                 # features.GROUPS
    schalter: tuple             # chat.* admin switches
    anleitung: str              # guides.js id
    pref: str = ""              # features.Feature.pref: a preference, on unless the profile switched it off
    parent: str = ""            # the function it builds on
    me: str = ""                # the Ich page where the profile sets it up
    werkzeuge: dict = {}        # its own tools: tool -> (de, en); the first function in features.FEATURES that offers a
                                # tool owns it
    auch: tuple = ()            # tools of other functions it offers too (werkzeug_abdeckung.TOOLS)
    knoten: dict = {}           # tool -> Live node, where it is not the node of its own (live)
    ohne_werkzeug: tuple = ()   # (regel|ohne, why) when it has no tool: werkzeug_abdeckung.RULES / WITHOUT
    live: tuple = ()            # (node, label, detail, kind, own_service, returns)
    log: tuple = ()             # (logfilter area, first word of the lines)
    eigenes_wort: dict = {}     # tool -> module: offered only on the person's own word (werkzeug_abdeckung.BY_WORD)
    kurz: tuple = ()            # ((tool, example de, example en), ...): the cheat sheet's short commands (spickzettel.KURZ)
    saetze: dict = {}           # tool -> (typical request de, en): it must reach the tool's group (SENTENCES)
    begleiter_teile: tuple = ()  # the Begleiter parts that carry it (features.DESK, begleiter.PARTS)
    modul: tuple = ()           # (module, technik group, German line)
    begleiter: str = ""         # why the Begleiter has no part of its own: a kind (talk, voice, spark, link, device,
                                # panel) or its own sentence; "" when the function it builds on says it
    nur_spark: bool = False     # features.SPARK_ONLY: a setting of the whole Spark, no function a profile uses


STECKBRIEFE = {
    # rechnen.py (Dominik 2026-10-22): the tool rechnen and the check of sums, the panel computes, never the model;
    # nothing leaves the Spark
    "rechnen": Steckbrief(
        de="Rechnen mit festem Werkzeug", en="Exact calculations", gruppe="talk", schalter=("rechnen",),
        anleitung="rechnen", werkzeuge={"rechnen": ("Rechnen", "Calculate")},
        live=("rechnen", "Rechnen", "fester Rechner · auf dem Spark", "spark", False, "Ergebnis"),
        log=("chat", "rechnen"),
        eigenes_wort={"rechnen": "rechnen"},
        kurz=(("rechnen", "Rechne 19 Prozent von 249 Euro aus", "Calculate 19 percent of 249 euros"),),
        modul=("rechnen", "gespraech", "Rechnen mit festem Werkzeug: eigener Parser statt eval, Datumsrechnung, "
                                       "Nachrechnen in Antworten"),
        begleiter="talk"),
    "toolthink": Steckbrief(de="Bei der Werkzeugwahl nachdenken", en="Thinking while choosing tools", gruppe="speed",
        schalter=("tool_thinking",), anleitung="toolthink", me="setbox",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"), begleiter="spark"),
    "routing": Steckbrief(de="Gezielte Werkzeugwahl", en="Targeted tool choice", gruppe="speed",
        schalter=("routing",), anleitung="routing", me="setbox",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"), begleiter="spark"),
    "direct": Steckbrief(de="Eindeutiges direkt abrufen", en="Fetch clear questions directly", gruppe="speed",
        schalter=("direct_read",), anleitung="direct", me="setbox",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"), begleiter="spark"),
    # hoerwoerter.py (plan genauer-und-schneller, 5): the speech recognition gets the names of rooms, devices, people
    "hoeren": Steckbrief(de="Namen fürs Hören", en="Names for listening", gruppe="speed", schalter=("hoer_namen",),
        anleitung="hoeren", ohne_werkzeug=("ohne", "Einstellung, wie die Spracherkennung hört"), begleiter="spark"),
    # sofort.py (plan genauer-und-schneller, 6): time, date, arithmetic and units as the panel's fixed sentence
    "sofort": Steckbrief(de="Einfaches sofort beantworten", en="Answer simple things at once", gruppe="speed",
        schalter=("sofort",), anleitung="sofort", ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"),
        begleiter="spark",
        modul=("sofort", "gespraech", "Einfaches sofort beantworten: Uhrzeit, Datum, Rechnen und Einheiten als "
                                      "fester Satz ohne Modell")),
    # chat.memory_split (plan genauer-und-schneller, 4): a long memory keeps a fixed core, older facts only when they fit
    "gedkurz": Steckbrief(de="Großes Gedächtnis kürzen", en="Trim a large memory", gruppe="speed",
        schalter=("memory_trim",), anleitung="gedkurz",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"), begleiter="spark"),
    "ack": Steckbrief(de="Sofortige Rückmeldung", en="Instant acknowledgement", gruppe="speed",
        schalter=("instant_ack",), anleitung="ack", parent="routing", me="setbox",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"),
        modul=("ack", "gespraech", "Sofortige Rückmeldung aus aufgenommenen Sätzen")),
    # weiche_abstimmen.py (plan opencode-werkstatt, point 1): the model proposes words, fixed rules keep what helps
    "weicheabstimmen": Steckbrief(de="Weiche abstimmen", en="Tune the switch", gruppe="speed",
        schalter=("route_tune",), anleitung="weicheabstimmen", parent="routing",
        ohne_werkzeug=("ohne", "weiche_abstimmen.py: nur der Admin auf Funktionen → Weiche; das Modell schlägt "
                               "Wörter vor, feste Regeln messen, kein Werkzeug"),
        nur_spark=True),
    # weiche_unklar.py (plan unklare-fragen): unclear questions kept anonymized for the admin to tune the Weiche with;
    # a preference, because the Spark keeps something of the profile's questions without being asked
    "weicheunklar": Steckbrief(de="Unklare Fragen anonym merken", en="Keep unclear questions anonymously",
        gruppe="speed", schalter=("route_unklar",), anleitung="weicheunklar", pref="unklar_anon", parent="routing",
        me="setbox",
        ohne_werkzeug=("ohne", "weiche_unklar.py: das Panel merkt unklare Fragen anonym für den Admin auf Funktionen "
                               "→ Weiche, kein Werkzeug")),
    "vorab": Steckbrief(de="Vorab holen bei Rückfrage", en="Fetch ahead on a question back", gruppe="speed",
        schalter=("prefetch",), anleitung="vorab", parent="routing", me="setbox",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten entstehen"),
        modul=("vorab", "gespraech", "Holt bei einer Rückfrage die Antwort schon vorab")),
    # the LLM-Tor's /v1/systemone (systemone.py): probabilities instead of words, the panel decides with fixed thresholds
    "einordnung": Steckbrief(de="Einordnung mit Wahrscheinlichkeit", en="Classification with probabilities",
        gruppe="speed", schalter=("systemone",), anleitung="einordnung", me="setbox",
        ohne_werkzeug=("ohne", "Signal fürs Panel, keine Bitte"), begleiter="spark",
        modul=("einordnung", "sprache", "Regeln für System-One-Fragen, gemeinsam für Panel und LLM-Tor")),
    "einordnungpost": Steckbrief(de="Einordnung beim Postfach aufräumen", en="Classification when tidying the inbox",
        gruppe="speed", schalter=("systemone_tidy", "mail_tidy", "mail"), anleitung="einordnungpost",
        parent="einordnung", me="setbox", ohne_werkzeug=("ohne", "Signal fürs Panel, keine Bitte")),
    "einordnungtest": Steckbrief(de="Einordnung im Qualitätstest", en="Classification in the quality test",
        gruppe="speed", schalter=("systemone_quality",), anleitung="einordnungtest", parent="einordnung",
        ohne_werkzeug=("ohne", "Signal fürs Panel, keine Bitte")),
    "einordnungrat": Steckbrief(de="Einordnung im Einstellungs-Assistenten",
        en="Classification in the settings assistant", gruppe="speed", schalter=("systemone_berater", "berater"),
        anleitung="einordnungrat", parent="einordnung", ohne_werkzeug=("ohne", "Signal fürs Panel, keine Bitte")),
    "einordnungcheck": Steckbrief(de="Antworten im Hintergrund prüfen", en="Check answers in the background",
        gruppe="speed", schalter=("systemone_check", "berater"), anleitung="einordnungcheck", parent="einordnung",
        me="setbox", ohne_werkzeug=("ohne", "Signal fürs Panel, keine Bitte")),
    # Nicht belegte Antworten markieren (Issue 3 in spark-meldungen, Dominik 2026-11-14 „Ok“): the background check's
    # „erfunden“ shows under the answer, with „Nochmal nachschauen“; a speaker hears one fixed sentence (systemone.py)
    "unbelegt": Steckbrief(de="Nicht belegte Antworten markieren", en="Mark answers that are not backed up",
        gruppe="speed", schalter=("unbelegt_mark", "systemone_check", "berater"), anleitung="unbelegt",
        parent="einordnungcheck", me="setbox",
        ohne_werkzeug=("ohne", "Signal fürs Panel unter der Antwort, keine Bitte")),
    "einordnungklage": Steckbrief(de="Beschwerde erkennen", en="Recognize complaints", gruppe="speed",
        schalter=("systemone_klage", "loop_stop"), anleitung="einordnungklage", parent="einordnung", me="setbox",
        ohne_werkzeug=("ohne", "Signal fürs Panel, keine Bitte")),
    # the small helper model on the model computer (systemone.HELFER_USES, Dominik 2026-10-25), the language model
    # stands in whenever it is not ready
    "helfer": Steckbrief(de="Hilfsmodell", en="Helper model", gruppe="speed", schalter=("helfer",),
        anleitung="helfer",
        ohne_werkzeug=("ohne", "Hilfsmodell für feste Einordnungen (systemone.HELFER_USES), keine Bitte"),
        begleiter="spark", nur_spark=True),
    "helferangriff": Steckbrief(de="Hilfsmodell erkennt Angriffe", en="Helper model spots attacks", gruppe="speed",
        schalter=("helfer_angriff", "systemone", "berater"), anleitung="helferangriff", parent="helfer",
        ohne_werkzeug=("ohne", "Hilfsmodell prüft gelesenen Text im Hintergrund, keine Bitte"), nur_spark=True),
    # chat.web_search (plan genauer-und-schneller, 7): 3 s per page, the fitting parts, 10 minutes in memory
    "suchschnell": Steckbrief(de="Schnellere Websuche", en="Faster web search", gruppe="talk",
        schalter=("search_fast",), anleitung="suchschnell", parent="search",
        ohne_werkzeug=("ohne", "Einstellung, wie die Websuche liest")),
    "lokal": Steckbrief(de="Erst lokal suchen", en="Look locally first", gruppe="talk", schalter=("local_first",),
        anleitung="lokal", me="setbox",
        ohne_werkzeug=("regel", "lokal.py: schaut vor der Antwort in den eigenen Quellen nach"), begleiter="talk",
        modul=("lokal", "wissen", "Erst lokal suchen, bevor etwas nach außen geht")),
    # quellenangabe.py (Dominik 2026-11-13): under every answer that wants to know something the sources that ran,
    # by fixed rules; „Woher weißt du das?“ answered by the panel; a hint when the source does not fit the question
    "quelle": Steckbrief(de="Quellenangabe", en="Source note", gruppe="talk", schalter=("source_note",),
        anleitung="quelle", me="setbox",
        ohne_werkzeug=("regel", "quellenangabe.py: „Woher weißt du das?“ beantwortet das Panel aus der letzten Antwort"),
        live=("quelle", "Quellenangabe", "Quellen unter Antworten · auf dem Spark", "spark", False, "Zeile"),
        log=("chat", "quelle"), begleiter="talk",
        modul=("quellenangabe", "gespraech", "Quellenangabe: woher eine Antwort stammt, nach festen Regeln, "
                                             "„Woher weißt du das?“, Hinweis bei unpassender Quelle")),
    # the spoken sentence at the end of an answer at a speaker, phone, watch, Siri or in the car: a preference,
    # because the Spark says something more without being asked
    "quellesagen": Steckbrief(de="Quelle im Gespräch ansagen", en="Say the source in conversation", gruppe="talk",
        schalter=("source_note",), anleitung="quellesagen", pref="quelle_sagen", parent="quelle", me="setbox",
        ohne_werkzeug=("ohne", "ein Satz am Ende einer gesprochenen Antwort"), begleiter="voice"),
    "roles": Steckbrief(de="Rollen per Sprache", en="Roles by voice", gruppe="talk", schalter=("roles",),
        anleitung="roles", me="setbox",
        ohne_werkzeug=("regel", "roles.py: „Sei der Butler“, „Welche Rollen gibt es?“, „Sei wieder normal“"),
        begleiter="talk", modul=("roles", "gespraech", "Rollen: wie der Assistent antworten soll")),
    "style": Steckbrief(de="Eigener Gesprächsstil", en="Own conversation style", gruppe="talk",
        schalter=("own_style",), anleitung="style", me="setbox", ohne_werkzeug=("ohne", "wirkt auf jede Antwort"),
        begleiter="talk"),
    "follow": Steckbrief(de="Rückfrage ohne Weckwort", en="Follow-up without wake word", gruppe="talk",
        schalter=("follow_up",), anleitung="follow", me="setbox",
        ohne_werkzeug=("ohne", "Verhalten am Lautsprecher"), begleiter="voice"),
    "selfecho": Steckbrief(de="Eigene Stimme überhören", en="Ignore my own voice", gruppe="talk",
        schalter=("no_self_echo",), anleitung="selfecho", me="setbox",
        ohne_werkzeug=("ohne", "Verhalten am Lautsprecher"), begleiter="voice"),
    # stimmdesign.py (Dominik 2026-11-11, plan eigene-stimme): 20 fixed voices and own ones from fields, made once with
    # VoiceDesign, then cloned by the Base engine (tts.klon_enabled); READY needs both on the speech output
    "stimmdesign": Steckbrief(de="Eigene Stimmen gestalten", en="Design own voices", gruppe="talk",
        schalter=("stimmdesign",), anleitung="stimmdesign", me="setbox",
        ohne_werkzeug=("ohne", "Einstellung, mit welcher Stimme Antworten klingen (Ich → Gespräch → Eigene Stimme)"),
        begleiter="panel",
        modul=("stimmdesign", "sprache", "Eigene Stimmen gestalten: 20 fertige und eigene Stimmen aus festen "
                                         "Feldern, einmal mit VoiceDesign gemacht, dann geklont")),
    # zwischenruf.py (plan ins-wort-fallen): a barge-in only pauses the answer; fixed words decide on, stop or question
    "anhalten": Steckbrief(de="Ins Wort fallen: erst anhalten", en="Barge-in: pause first", gruppe="talk",
        schalter=("barge_hold",), anleitung="anhalten", me="setbox",
        ohne_werkzeug=("ohne", "Verhalten beim Ins-Wort-Fallen"), begleiter="voice"),
    # satzende.py, smartturn.py (plan ins-wort-fallen B1): Smart Turn hears at each pause whether you sound done; measures only
    "satzende": Steckbrief(de="Satzende am Tonfall", en="Turn end by tone", gruppe="talk", schalter=("turn_tone",),
        anleitung="satzende", me="setbox", ohne_werkzeug=("ohne", "Messung an Sprechpausen, kein Werkzeug"),
        begleiter="voice",
        modul=("satzende", "gespraech", "Satzende am Tonfall: misst an jeder Sprechpause Smart Turn gegen die "
                                        "Wortliste, nur Zahlen")),
    "fixes": Steckbrief(de="Aus Korrekturen lernen", en="Learning from corrections", gruppe="talk",
        schalter=("learn_fixes",), anleitung="fixes", parent="memory", me="setbox",
        ohne_werkzeug=("regel", "fixes.py: erkennt eine Korrektur, ein Ja merkt sie"),
        modul=("fixes", "gespraech", "Lernt aus Korrekturen der Person")),
    "klaeren": Steckbrief(de="Rückfrage statt Raten", en="Ask instead of guessing", gruppe="talk",
        schalter=("klaeren",), anleitung="klaeren", me="setbox",
        ohne_werkzeug=("regel", "klaeren.py: fragt bei mehreren Treffern zurück"), begleiter="talk",
        modul=("klaeren", "gespraech", "Rückfrage (welches Ding, welcher Weg), Korrektur und Merken von Zuordnungen")),
    "klaerenmerken": Steckbrief(de="Auswahl merken", en="Remember the choice", gruppe="talk",
        schalter=("klaeren_merken",), anleitung="klaerenmerken", parent="klaeren", me="setbox",
        ohne_werkzeug=("regel", "klaeren.py: „Merk dir das“ nach der Rückfrage")),
    # Rückfragen der Weiche (klaeren.py area "weg", intent.ask_route, P5): before a change, which way a wish goes
    "klaerenweg": Steckbrief(de="Rückfrage zum Weg", en="Ask which way", gruppe="talk", schalter=("klaeren_weg",),
        anleitung="klaerenweg", parent="klaeren",
        ohne_werkzeug=("regel", "intent.ask_route und klaeren.py: fragt vor einer Änderung, welcher Weg gemeint ist")),
    # ablauf.py: the tools of an answer under it, a waiting proposal as a card with Ja and Nein
    "ablauf": Steckbrief(de="Ablauf und Freigabe zeigen", en="Show steps and approvals", gruppe="talk",
        schalter=("show_steps",), anleitung="ablauf",
        ohne_werkzeug=("ohne", "Einstellung, wie Antworten gezeigt werden (ablauf.py)"), begleiter="talk",
        modul=("ablauf", "gespraech", "Zeigt unter der Antwort die benutzten Werkzeuge und einen wartenden Vorschlag "
                                      "als Karte mit Ja und Nein")),
    "images": Steckbrief(de="Bilder erkennen", en="Picture recognition", gruppe="talk", schalter=("images",),
        anleitung="images", me="setbox",
        ohne_werkzeug=("regel", "images.py: das Bild geht mit der Frage ans Modell"), begleiter="talk",
        modul=("images", "gespraech", "Bilder in der Frage: das Sprachmodell sieht sie selbst")),
    "tippspush": Steckbrief(de="Funktionen vorschlagen von selbst", en="Suggesting functions by itself",
        gruppe="day", schalter=("feature_tips_push", "feature_tips"), anleitung="tippspush", pref="pro_tips",
        parent="proactive", me="probox", ohne_werkzeug=("ohne", "meldet sich von selbst")),
    "tippsstimme": Steckbrief(de="Tipps beim Sprechen", en="Tips while talking", gruppe="talk",
        schalter=("feature_sentences_voice",), anleitung="tippsstimme", pref="voice_tips", parent="tippssaetze",
        me="setbox", ohne_werkzeug=("ohne", "ein Satz am Ende einer gesprochenen Antwort, kein Werkzeug")),
    "vorrang": Steckbrief(de="Vorrang für Personen", en="Priority for people", gruppe="talk",
        schalter=("person_priority",), anleitung="vorrang", ohne_werkzeug=("ohne", "Schutzregel für Personen"),
        begleiter="spark", modul=("vorrang", "sprache", "Sprache zuerst: Hintergrundarbeit wartet")),
    # gedaechtnis.py (plan gedaechtnis-pruefen/plan.md): evidence per fact, fixed rules mark what may be out of date
    "gedpruefen": Steckbrief(de="Gedächtnis prüfen", en="Memory check", gruppe="data", schalter=("memory_check",),
        anleitung="gedpruefen", parent="memory", me="factbox",
        ohne_werkzeug=("regel", "gedaechtnis.py: „Stimmt das noch?“ und die Antwort darauf")),
    "gedfragen": Steckbrief(de="Nachfrage zum Gedächtnis", en="Memory check-back", gruppe="data",
        schalter=("memory_ask",), anleitung="gedfragen", parent="gedpruefen", me="setbox",
        ohne_werkzeug=("regel", "gedaechtnis.py: Nachfrage zum Gedächtnis")),
    "gedthemen": Steckbrief(de="Themen im Gedächtnis", en="Memory topics", gruppe="data",
        schalter=("memory_topics",), anleitung="gedthemen", parent="gedpruefen", me="factbox",
        ohne_werkzeug=("ohne", "ordnet das Gedächtnis im Hintergrund")),
    # gemerkt.py (plan nutzerwissen, Punkt 1): „Gemerkt: …“ under the answer with „Rückgängig“, learned ones as a card
    "gedhinweis": Steckbrief(de="Gemerkt-Hinweis", en="Remembered note", gruppe="data", schalter=("memory_note",),
        anleitung="gedhinweis", parent="memory", me="factbox",
        ohne_werkzeug=("regel", "aendern.py: „Mach das rückgängig“ nach memory_save nimmt den Fakt zurück "
                                "(gemerkt.take_back)")),
    "docpics": Steckbrief(de="Bilder und Scans lesen", en="Read pictures and scans", gruppe="data",
        schalter=("doc_pictures",), anleitung="docpics", parent="documents", me="docbox",
        ohne_werkzeug=("ohne", "wirkt beim Einlesen")),
    "docmeaning": Steckbrief(de="Bedeutungssuche", en="Meaning search", gruppe="data", schalter=("doc_semantic",),
        anleitung="docmeaning", parent="documents", me="docbox", ohne_werkzeug=("ohne", "wirkt beim Suchen")),
    "docfiles": Steckbrief(de="Originale aufbewahren", en="Keep originals", gruppe="data",
        schalter=("doc_originals",), anleitung="docfiles", parent="documents", me="docbox",
        ohne_werkzeug=("ohne", "wirkt beim Einlesen")),
    "docnight": Steckbrief(de="Lange Dokumente nachts lesen", en="Read long documents at night", gruppe="data",
        schalter=("doc_night",), anleitung="docnight", parent="documents", me="docbox",
        ohne_werkzeug=("ohne", "wirkt beim Einlesen")),
    # geteilt.py (plan teilen-profile, Dominik 2026-10-20 „ok“): one way to share for every kind, Ich → Geteilt; a
    # document to single profiles, calendars and lists listed and taken back there. The note is a preference.
    "teilen": Steckbrief(de="Teilen mit Profilen", en="Sharing with profiles", gruppe="data", schalter=("share",),
        anleitung="teilen", me="teilbox",
        ohne_werkzeug=("ohne", "kein Werkzeug in Stufe 1: geteilt wird nur im Dialog am Dokument (Ich → Dokumente → "
                               "Teilen), die Suche des anderen findet es über document_search"),
        begleiter="panel",
        modul=("teilen", "teilen", "Spark teilen: Firewall-Regeln für die Tür des Modell-Rechners, Fingerabdruck des "
                                   "Zertifikats")),
    "teilenhinweis": Steckbrief(de="Hinweis auf Geteiltes", en="Note on shared things", gruppe="data",
        schalter=("share",), anleitung="teilenhinweis", pref="share_note", parent="teilen", me="teilbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: eine Mitteilung, wenn jemand etwas teilt (push.send)")),
    # Docling-Server (doclingdienst.py): for all profiles once the admin sets it up; each may say "not my files"
    # (preference doc_docling, on by default) because the files leave the Spark for the server in the home network
    "docling": Steckbrief(de="Docling-Server", en="Docling server", gruppe="data", schalter=("docling",),
        anleitung="docling", pref="doc_docling", parent="documents", me="docbox",
        ohne_werkzeug=("ohne", "wirkt beim Einlesen (liest im Hintergrund)")),
    "rmfresh": Steckbrief(de="Neueste zuerst", en="Newest first", gruppe="data", schalter=("remarkable_fresh",),
        anleitung="rmfresh", parent="remarkable", me="rmbox", ohne_werkzeug=("ohne", "wirkt beim Abgleich")),
    "rmmorning": Steckbrief(de="Morgenblatt", en="Morning sheet", gruppe="data", schalter=("remarkable_plus",),
        anleitung="rmplus", pref="rm_morning", parent="rmsend", me="rmbox",
        ohne_werkzeug=("ohne", "kommt von selbst aufs Papier")),
    "rmask": Steckbrief(de="@Spark auf Papier", en="@Spark on paper", gruppe="data", schalter=("remarkable_plus",),
        anleitung="rmplus", parent="rmsend", me="rmbox", ohne_werkzeug=("ohne", "läuft auf dem Papier")),
    "rmmeet": Steckbrief(de="Besprechungen zusammenfassen", en="Meeting summaries", gruppe="data",
        schalter=("remarkable_plus",), anleitung="rmplus", parent="rmsend", me="rmbox",
        ohne_werkzeug=("ohne", "läuft auf dem Papier")),
    "rmweek": Steckbrief(de="Wochenrückblick", en="Week in review", gruppe="data", schalter=("remarkable_plus",),
        anleitung="rmplus", pref="rm_week", parent="rmsend", me="rmbox",
        ohne_werkzeug=("ohne", "kommt von selbst aufs Papier")),
    "rminbox": Steckbrief(de="Eingang pro Tag", en="Daily inbox", gruppe="data", schalter=("remarkable_plus",),
        anleitung="rmplus", pref="rm_inbox", parent="rmsend", me="rmbox",
        ohne_werkzeug=("ohne", "läuft auf dem Papier")),
    "rmguide": Steckbrief(de="Spark-Anleitung auf dem reMarkable", en="Spark guide on the reMarkable", gruppe="data",
        schalter=("remarkable_plus",), anleitung="rmplus", parent="rmsend", me="rmbox",
        ohne_werkzeug=("ohne", "kommt von selbst aufs Papier")),
    # paper for the reMarkable (rmpapier.py): one admin switch for three functions
    "rmpapier": Steckbrief(de="Gestaltete Blätter zum Ankreuzen", en="Designed sheets to tick", gruppe="data",
        schalter=("remarkable_paper",), anleitung="rmpapier", parent="rmsend", me="rmbox",
        ohne_werkzeug=("ohne", "gestaltet die Blätter"),
        modul=("rmpapier", "dienste", "Gestaltete Blätter fürs reMarkable")),
    "rmordner": Steckbrief(de="Ordner nach Art", en="Folders by kind", gruppe="data", schalter=("remarkable_paper",),
        anleitung="rmpapier", parent="rmsend", me="rmbox", ohne_werkzeug=("ohne", "ordnet die Ablage")),
    "rmaufraeumen": Steckbrief(de="Selbst aufräumen", en="Tidy up by itself", gruppe="data",
        schalter=("remarkable_paper",), anleitung="rmpapier", pref="rm_tidy", parent="rmordner", me="rmbox",
        ohne_werkzeug=("ohne", "räumt die Ablage auf")),
    # Bilder ändern (bilder.from_turn, plan bildbearbeitung, Stufe 2a): an own photo or picture changed by FLUX.2 [klein];
    # the panel picks the picture by a fixed rule, never the model
    "bildaendern": Steckbrief(de="Bilder ändern", en="Changing pictures", gruppe="data",
        schalter=("bilder_aendern",), anleitung="bildaendern", parent="bilder", me="bildbox",
        ohne_werkzeug=("regel", "bilder.py: Foto im Chat mit Änderungswunsch, das Panel startet die Änderung nach "
                                "fester Regel")),
    # KI-Dungeon-Master (dungeon.py, plan dungeon-master): a role-playing round for up to five players, also without a
    # profile by seat link; the model narrates, the panel rolls and gives loot, experience, levels and trades by fixed rules
    "dungeon": Steckbrief(de="KI-Dungeon-Master", en="AI Dungeon Master", gruppe="data", schalter=("dungeon",),
        anleitung="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon.py: kein Werkzeug, ein Spiel auf seiner eigenen Seite (Erzählung nur als "
                               "Daten, Werte vom Panel)"),
        begleiter="panel",
        modul=("dungeon", "dienste", "KI-Dungeon-Master: Rollenspiel bis 5 per Link; Panel würfelt, Beute, "
                                     "Kampagnen, Geschichten in Akten, Vorlesen")),
    # Ausdünnen 1 (dungeon_tiefe.py, Dominik 2026-11-11 „Ok“): the game's parts hang on the game and its Regeltiefe
    # (einfach/voll, chat.dungeon_tiefe and per round) or on one of these six switches, never one switch per part
    # Bilder und Heldenlied (dungeon_dingbild, dungeon_gesicht, dungeon_wappen, dungeon_album, dungeon_lied): pictures
    # for gear, spells, faces and arms, the monster album and the bard's song; painting needs „Bilder malen“ too
    "dungeonbilder": Steckbrief(de="Bilder und Heldenlied", en="Pictures and hero song", gruppe="data",
        schalter=("dungeon_bilder",), anleitung="dungeonbilder", parent="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon_dingbild.py: kein Werkzeug, Bilder für den Katalog des Spiels, gemalt nachts "
                               "oder auf Knopf des Admins nach fester Regel")),
    # Zweite Prüfung durch das Modell (dungeon_erzaehler Richter, dungeon_schreiber, dungeon_kommentar): a second model
    # call per turn after the fixed checks, about 2 to 4 seconds more
    "dungeonpruefung": Steckbrief(de="Zweite Prüfung durch das Modell", en="Second check by the model",
        gruppe="data", schalter=("dungeon_pruefung",), anleitung="dungeonpruefung", parent="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon_erzaehler.py/dungeon_schreiber.py/dungeon_kommentar.py: kein Werkzeug, das "
                               "Modell gibt nach den festen Prüfungen nur eine Wahrscheinlichkeit, Vorschläge und "
                               "Zeilen als Daten, das Panel entscheidet nach festen Grenzen")),
    # Gäste mit E-Mail (dungeon_gast.py): guests sign in with a code from the admin's mailbox and keep their heroes
    "dungeongast": Steckbrief(de="Gäste mit E-Mail", en="Guests with e-mail", gruppe="data",
        schalter=("dungeon_gast",), anleitung="dungeongast", parent="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon_gast.py: kein Werkzeug, Gast-Konten des Spiels mit festem Code per Mail und "
                               "fester Zug-Mail, nie Modelltext")),
    # Bücher (dungeon_chronik.py, dungeon_buch.py): the campaign's chronicle book and the hero book to the reMarkable
    # (that one needs „Aufs reMarkable schicken“ too)
    "dungeonbuecher": Steckbrief(de="Chronik und Heldenbuch", en="Chronicle and hero book", gruppe="data",
        schalter=("dungeon_buecher",), anleitung="dungeonbuecher", parent="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon_chronik.py/dungeon_buch.py: kein eigenes Werkzeug; „Schick mein Heldenbuch "
                               "aufs reMarkable“ geht über remarkable_sheet (rmplus.SHEETS heldenbuch), sonst "
                               "schickt das Panel nach Rundenende von selbst")),
    # Eigene Geschichten (dungeon_geschichten.py, dungeon_import.py): edit, copy and delete stories, „＋ Neue Geschichte“
    # and the adventure import
    "dungeongeschichten": Steckbrief(de="Eigene Geschichten und Import", en="Own stories and import", gruppe="data",
        schalter=("dungeon_geschichten",), anleitung="dungeongeschichten", parent="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon_geschichten.py: kein Werkzeug, der Gastgeber bearbeitet seine Geschichten "
                               "selbst, der Planer schreibt nur Daten, das Panel prüft sie mit festen Regeln")),
    # Prüfstände (dungeon_pruefstand.py, dungeon_erzaehlstand.py): the balance bench at night and the narrator bench on
    # the admin's button
    "dungeonpruefstand": Steckbrief(de="Prüfstände", en="Test benches", gruppe="data",
        schalter=("dungeon_pruefstand",), anleitung="dungeonpruefstand", parent="dungeon", me="dmbox",
        ohne_werkzeug=("ohne", "dungeon_pruefstand.py: kein Werkzeug, der Admin-Prüfstand spielt Kämpfe mit festen "
                               "Regeln und Würfeln, ohne Modell")),
    # Suchprüfung (suchpruefung.py, plan suche-schaerfen, Stufe 1): test questions measure how often the search
    # finds the right passage; the admin's release is enough (no profile switch, Freigabe rule 2026-10-13)
    "suchpruefung": Steckbrief(de="Suchprüfung", en="Search check", gruppe="data", schalter=("search_check",),
        anleitung="suchpruefung", parent="documents", me="docbox",
        ohne_werkzeug=("ohne", "misst im Hintergrund, wie gut die Suche trifft (Ich → Dokumente)"),
        modul=("suchpruefung", "wissen", "Suchprüfung: Prüffragen messen, wie gut die Dokumentensuche trifft")),
    "nachsortieren": Steckbrief(de="Treffer nachsortieren", en="Re-rank hits", gruppe="data", schalter=("rerank",),
        anleitung="nachsortieren", parent="documents", me="docbox",
        ohne_werkzeug=("ohne", "wirkt beim Suchen in den Dokumenten"),
        modul=("nachsortieren", "wissen", "Treffer nachsortieren: ein Cross-Encoder auf dem Prozessor ordnet die "
                                          "Kandidaten")),
    # Wissensbuch (wissensbuch.py, plan wissensbuch after Karpathy's LLM Wiki): own documents worked once into pages
    # with a source per sentence; the panel's fixed rules decide what stays, never the model
    "wissensbuch": Steckbrief(de="Wissensbuch", en="Knowledge book", gruppe="data", schalter=("knowledge_book",),
        anleitung="wissensbuch", parent="documents", me="wbbox",
        ohne_werkzeug=("ohne", "arbeitet im Hintergrund, Fragen beantwortet document_search aus den Seiten"),
        modul=("wissensbuch", "wissen", "Wissensbuch: Seiten aus eigenen Dokumenten, jeder Satz mit Quelle; "
                                        "Suchindex FTS5, Lesefunktion liste")),
    # Wissenskarte (wissenskarte.py, plan wissensgraph): the pages of the Wissensbuch as a map with checked connections
    "wissenskarte": Steckbrief(de="Wissenskarte", en="Knowledge map", gruppe="data", schalter=("knowledge_map",),
        anleitung="wissenskarte", parent="wissensbuch", me="wbbox",
        ohne_werkzeug=("ohne", "arbeitet im Hintergrund, die Karte steht im Wissensbuch (Seite Karte)"),
        modul=("wissenskarte", "wissen", "Wissenskarte: geprüfte Verbindungen und Punkte aus Dokumenten mit Quelle, "
                                         "Aufbau im Speicher, Wortindex, Suchliste")),
    # Knoten aus Dokumenten (wissenskarte.py, plan wissensgraph Stufe 2): people, companies, places, contracts, accounts
    # and deadlines of the documents as own points of the map; the panel's fixed rules decide, never the model
    "wissensknoten": Steckbrief(de="Personen, Firmen und Fristen", en="People, companies and deadlines",
        gruppe="data", schalter=("knowledge_ents",), anleitung="wissensknoten", parent="wissenskarte", me="wbbox",
        ohne_werkzeug=("ohne", "arbeitet im Hintergrund, Personen, Firmen und Fristen stehen als Knoten auf der "
                               "Karte im Wissensbuch")),
    # Karte hilft der Suche (wissenskarte.liste, plan wissensgraph Stufe 3): the points from documents give the document
    # search a third list of hits (the words name a point, its neighbours, their places); fixed rules, never the model
    "kartensuche": Steckbrief(de="Karte hilft der Suche", en="Map helps the search", gruppe="data",
        schalter=("knowledge_search",), anleitung="kartensuche", parent="wissensknoten", me="wbbox",
        ohne_werkzeug=("ohne", "kein eigenes Werkzeug, document_search findet über die Karte mit (wissenskarte.liste "
                               "als dritte Trefferliste)")),
    # Finden, Stufe B (fundmail.py): every mail of the inbox, archive and sent folder with its attachments in the index,
    # sealed (marks and AES-GCM), read in slices in quiet minutes and at night; needs E-Mail lesen
    "fundmail": Steckbrief(de="Mails und Anhänge finden", en="Find mail and attachments", gruppe="data",
        schalter=("fund_mail", "fund", "mail"), anleitung="fundmail", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "sammelt nur Mails und Anhänge in den Index ein, Fragen beantwortet fund_suche "
                               "(Finden in allen Daten)"),
        modul=("fundmail", "wissen", "Finden: alle Mails und Anhänge in Scheiben eingelesen, versiegelt (AES-GCM) "
                                     "mit Blind-Marken je Profil")),
    # Finden, Stufe C (fundquellen.py): each source a sub-switch of Finden, off, and it follows the function it comes
    # from (fundquellen.frei): appointments of the own calendars from the Spark's copy and contacts sealed like mail;
    # conversations only as date and channel (their words through recall); lists, reminders, pictures, songs clear
    "fundtermine": Steckbrief(de="Termine finden", en="Find appointments", gruppe="data",
        schalter=("fund_termine", "fund", "calendar"), anleitung="fundtermine", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "sammelt nur Termine in den Index ein, Fragen beantwortet fund_suche (Finden in allen "
                               "Daten)")),
    "fundkontakte": Steckbrief(de="Kontakte finden", en="Find contacts", gruppe="data",
        schalter=("fund_kontakte", "fund", "contacts"), anleitung="fundkontakte", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "sammelt nur Kontakte in den Index ein, Fragen beantwortet fund_suche (Finden in "
                               "allen Daten)")),
    "fundchats": Steckbrief(de="Gespräche finden", en="Find conversations", gruppe="data",
        schalter=("fund_chats", "fund", "history"), anleitung="fundchats", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "sammelt nur Datum und Kanal früherer Gespräche in den Index ein, Fragen beantwortet "
                               "fund_suche (Finden in allen Daten)")),
    "fundlisten": Steckbrief(de="Listen und Erinnerungen finden", en="Find lists and reminders", gruppe="data",
        schalter=("fund_listen", "fund"), anleitung="fundlisten", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "sammelt nur Listen und Erinnerungen in den Index ein, Fragen beantwortet fund_suche "
                               "(Finden in allen Daten)")),
    "fundmedien": Steckbrief(de="Bilder und Lieder finden", en="Find pictures and songs", gruppe="data",
        schalter=("fund_medien", "fund"), anleitung="fundmedien", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "sammelt nur Bilder und Lieder in den Index ein, Fragen beantwortet fund_suche "
                               "(Finden in allen Daten)")),
    # Finden, Stufe D (fund.schlagworte_due): the language model proposes tags in quiet minutes, the panel keeps only
    # what its fixed rules allow (fund.pruefe), always marked „vom Modell“, the own tags win; off, never for guests
    "fundschlagworte": Steckbrief(de="Schlagworte vom Modell", en="Tags by the model", gruppe="data",
        schalter=("fund_schlagworte", "fund"), anleitung="fundschlagworte", parent="fund", me="fundbox",
        ohne_werkzeug=("ohne", "arbeitet im Hintergrund, schlägt nur Schlagworte für den Index vor, Fragen "
                               "beantwortet fund_suche (Finden in allen Daten)")),
    "suchfragen": Steckbrief(de="Prüffragen vom Spark", en="Test questions by the Spark", gruppe="data",
        schalter=("search_check_auto",), anleitung="suchfragen", parent="suchpruefung", me="docbox",
        ohne_werkzeug=("ohne", "schreibt im Hintergrund Prüffragen für die Suchprüfung")),
    # Home Assistant tells the Spark (hamelden.py): each part below "Von selbst melden"
    "halive": Steckbrief(de="Sofort-Meldungen aus Home Assistant", en="Instant notes from Home Assistant",
        gruppe="day", schalter=("ha_live", "homeassistant"), anleitung="halive", pref="pro_ha_live",
        parent="proactive", me="probox", ohne_werkzeug=("ohne", "meldet sich von selbst"),
        modul=("halive", "dienste", "Home Assistant live: Kopie aller Zustände über eine WebSocket-Verbindung (Ping, "
                                    "Keepalive, bald neu verbunden)")),
    "haloud": Steckbrief(de="Haus-Meldungen über Lautsprecher", en="House notes on speakers", gruppe="day",
        schalter=("ha_loud", "homeassistant", "messages_announce", "chats"), anleitung="haloud", pref="pro_ha_loud",
        parent="proactive", me="probox", ohne_werkzeug=("ohne", "meldet sich von selbst")),
    "haevent": Steckbrief(de="Home Assistant meldet an Spark", en="Home Assistant tells the Spark", gruppe="day",
        schalter=("ha_events", "homeassistant"), anleitung="haevent", pref="pro_ha_events", parent="proactive",
        me="probox", ohne_werkzeug=("ohne", "meldet sich von selbst")),
    "havoice": Steckbrief(de="Smart-Home-Regel per Sprache", en="Smart home rule by voice", gruppe="day",
        schalter=("ha_voice_rules", "homeassistant"), anleitung="havoice", parent="proactive", me="probox",
        ohne_werkzeug=("regel", "hamelden.py: „Sag mir Bescheid, wenn die Haustür aufgeht“, erst nach Ja")),
    "mailwichtig": Steckbrief(de="Wichtige Mails erkennen", en="Recognize important mail", gruppe="day",
        schalter=("systemone_mail", "systemone", "mail"), anleitung="mailwichtig", pref="pro_mail_smart",
        parent="proactive", me="mailbox", ohne_werkzeug=("ohne", "meldet sich von selbst")),
    # zustellung.py (plan benachrichtigung-geraet, Dominik 2026-10-20 "ok"): a note goes to the device in use right now,
    # else to the phone app
    "notedevice": Steckbrief(de="Mitteilung ans genutzte Gerät", en="Notes to the device in use", gruppe="day",
        schalter=("note_device", "reminders"), anleitung="notedevice", parent="reminders",
        ohne_werkzeug=("ohne", "kein Werkzeug: wählt nur, auf welches Gerät eine Mitteilung geht (zustellung.py), "
                               "feste Regeln des Panels")),
    # tasks.py (plan listen-teilen Stufe 2, Dominik 2026-10-20 „3a“): share an own list with another profile, see or
    # put on and tick off; a note when others put something on (preference list_note)
    "listshare": Steckbrief(de="Listen teilen", en="Share lists", gruppe="day", schalter=("tasks_share", "tasks"),
        anleitung="listshare", parent="tasks", me="taskbox",
        ohne_werkzeug=("regel", "tasks.py: tasks_show, tasks_add und tasks_change erreichen geteilte Listen („Setz "
                                "Butter auf Sabines Einkaufsliste“), Löschen nur der Besitzer")),
    "listnote": Steckbrief(de="Hinweis bei neuen Einträgen", en="Note on new entries", gruppe="day",
        schalter=("tasks_share", "tasks"), anleitung="listshare", pref="list_note", parent="listshare", me="taskbox",
        ohne_werkzeug=("regel", "tasks.py: ein Hinweis von selbst, wenn andere etwas auf eine geteilte Liste setzen; "
                                "nichts zu fragen")),
    "listdav": Steckbrief(de="Listen in Erinnerungen", en="Lists in Reminders", gruppe="day",
        schalter=("tasks_dav", "tasks", "calendar_server", "calendar"), anleitung="listdav", parent="tasks",
        me="taskbox",
        ohne_werkzeug=("regel", "listendav.py: kein Werkzeug, die Listen als Aufgabenlisten des Kalender-Servers "
                                "(die Kalender-App ändert sie, nicht das Modell)")),
    "listlink": Steckbrief(de="Mitschreib-Link", en="Write link", gruppe="day", schalter=("tasks_link", "tasks"),
        anleitung="listlink", parent="tasks", me="taskbox",
        ohne_werkzeug=("regel", "mitschreiblink.py: kein Werkzeug, eine Seite für Leute ohne Profil (nur eintragen, "
                                "nie das Modell)")),
    "mystatus": Steckbrief(de="Mein Zustand", en="My status", gruppe="day", schalter=("my_status",),
        anleitung="mystatus", me="bgbox", ohne_werkzeug=("ohne", "Seite Ich → Mein Zustand"), begleiter="panel"),
    # package F of the redde ideas (auftragsplan.py): plan, question, proposal and Nachschieben inside a job
    "auftragsplan": Steckbrief(de="Aufträge mit Plan, Rückfrage und Vorschlag",
        en="Jobs with plan, questions and proposals", gruppe="day", schalter=("agent_plan",),
        anleitung="auftragsplan", parent="agent", me="agentbox",
        ohne_werkzeug=("ohne", "Werkzeuge nur innerhalb eines Auftrags (auftragsplan.py), Antworten und Ja unter Ich "
                               "→ Aufträge"),
        modul=("auftragsplan", "dienste", "Aufträge mit Plan, Rückfrage, Vorschlag mit Ja und Nachschieben")),
    "mcp": Steckbrief(de="Dienste per MCP", en="Services over MCP", gruppe="day", schalter=("agent_mcp",),
        anleitung="mcp", parent="agent",
        ohne_werkzeug=("regel", "agent.py: die Werkzeuge der Dienste (mcp_…), bleiben, wenn der Dienst genannt wird"),
        modul=("mcp", "dienste", "Werkzeuge von MCP-Servern, die der Admin einträgt")),
    # each profile its own MCP services (meinmcp.py); needs no agent level, only the switches
    "mymcp": Steckbrief(de="Eigene MCP-Dienste", en="Own MCP services", gruppe="day", schalter=("mcp_own",),
        anleitung="mymcp", parent="mcp", me="mymcpbox",
        ohne_werkzeug=("regel", "meinmcp.py: die Werkzeuge der eigenen Dienste (mcpu_…), bleiben, wenn der Dienst "
                                "genannt wird")),
    "mymcpjobs": Steckbrief(de="Eigene MCP-Dienste in Aufträgen", en="Own MCP services in jobs", gruppe="day",
        schalter=("mcp_own_jobs",), anleitung="mymcpjobs", parent="mymcp", me="mymcpbox",
        ohne_werkzeug=("ohne", "wirkt in Aufträgen")),
    "mymcpoauth": Steckbrief(de="Eigene MCP-Dienste mit Anmeldung", en="Own MCP services with sign-in", gruppe="day",
        schalter=("mcp_own_oauth",), anleitung="mymcpoauth", parent="mymcp", me="mymcpbox",
        ohne_werkzeug=("ohne", "Anmeldung beim Dienst nur in der Oberfläche")),
    "chatgroups": Steckbrief(de="Gruppen-Chats", en="Group chats", gruppe="day", schalter=("chats_groups",),
        anleitung="chatgroups", parent="chats", me="setbox", ohne_werkzeug=("ohne", "Gruppen in der Oberfläche")),
    "chatmedia": Steckbrief(de="Fotos, Dateien und Sprache in Chats", en="Photos, files and voice in chats",
        gruppe="day", schalter=("chats_media",), anleitung="chatmedia", parent="chats", me="setbox",
        ohne_werkzeug=("ohne", "Fotos und Dateien in der Oberfläche")),
    "chatinvite": Steckbrief(de="In einen Chat einladen", en="Invite into a chat", gruppe="day",
        schalter=("chats_invite",), anleitung="chatinvite", parent="chats", me="setbox",
        ohne_werkzeug=("ohne", "Einladen in der Oberfläche")),
    "chatprivate": Steckbrief(de="Private Chats (Ende-zu-Ende)", en="Private chats (end-to-end)", gruppe="day",
        schalter=("chats_private",), anleitung="chatprivate", parent="chats", me="setbox",
        ohne_werkzeug=("ohne", "Ende-zu-Ende: der Spark kann sie bewusst nicht lesen")),
    # verbund.py (plan plaene/spark-verbund.md): chats with people on other Sparks; needs the own address from outside
    "verbund": Steckbrief(de="Chats mit anderen Sparks", en="Chats with other Sparks", gruppe="day",
        schalter=("chats_verbund",), anleitung="verbund", parent="chats",
        ohne_werkzeug=("ohne", "Nachrichten anderer Sparks sind fremder Text und gehen bewusst nie an das "
                               "Sprachmodell"),
        modul=("verbund", "geraete", "Spark-Verbund: Chats mit Menschen auf anderen Sparks, signiert, mit Fotos und "
                                     "Dateien")),
    "verbundmedia": Steckbrief(de="Fotos und Dateien zu anderen Sparks", en="Photos and files to other Sparks",
        gruppe="day", schalter=("verbund_media",), anleitung="verbundmedia", parent="verbund",
        ohne_werkzeug=("ohne", "Fotos und Dateien anderer Sparks sind fremde Daten und gehen bewusst nie an das "
                               "Sprachmodell")),
    "verbundgruppen": Steckbrief(de="Gruppen mit anderen Sparks", en="Groups with other Sparks", gruppe="day",
        schalter=("verbund_groups",), anleitung="verbundgruppen", parent="verbund",
        ohne_werkzeug=("ohne", "Gruppen mit anderen Sparks sind Chats zwischen Menschen; ihre Nachrichten gehen "
                               "bewusst nie an das Sprachmodell")),
    # anrufe.py (plan plaene/messenger-d-v2.md): voice and video calls in a chat of two; from outside through the
    # Vermittler (coturn on tars), which needs the address from outside
    "anrufe": Steckbrief(de="Anrufe (Sprache und Video)", en="Calls (voice and video)", gruppe="day",
        schalter=("chats_calls",), anleitung="anrufe", parent="chats",
        ohne_werkzeug=("ohne", "Anrufen geht nur auf der Seite, mit Kamera und Mikrofon des Geräts"),
        modul=("anrufe", "geraete", "Anrufe mit Sprache und Video in Chats zu zweit, Vermittler (TURN) für unterwegs")),
    "anrufeturn": Steckbrief(de="Anrufe von unterwegs", en="Calls when away", gruppe="day", schalter=("calls_turn",),
        anleitung="anrufeturn", parent="anrufe", ohne_werkzeug=("ohne", "Vermittler im Hintergrund")),
    # rufen.py (Dominik 2026-10-18): „Ruf Sabine an“ to the assistant, a call after the person's yes; on Android also
    # „übers Telefon“ with the own address book
    "anrufassistent": Steckbrief(de="Anrufe per Assistent", en="Calls by the assistant", gruppe="day",
        schalter=("calls_assistant",), anleitung="anrufassistent", parent="anrufe",
        ohne_werkzeug=("regel", "rufen.py: „Ruf Sabine an“, „Videoanruf mit Sabine“, „Ruf Mama übers Telefon an“, "
                                "erst nach Ja")),
    # calendars.py (Dominik 2026-10-18 „1a 2a“): share one calendar with another profile, see or see and enter;
    # private appointments only as „belegt“
    "calshare": Steckbrief(de="Kalender teilen", en="Share calendars", gruppe="day",
        schalter=("calendar_share", "calendar"), anleitung="calshare", parent="calendar", me="calbox",
        ohne_werkzeug=("regel", "calendars.py: calendar_events liest geteilte Kalender mit („Was hat Sabine "
                                "morgen?“), calendar_add trägt in einen genannten ein, erst nach Ja")),
    # kalenderserver.py (Dominik 2026-10-19 „1a-5a“, Spark-Kalender Stufe 4): the profile's Spark calendars for the
    # calendar app of the iPhone (CalDAV, an app password per profile)
    "calserver": Steckbrief(de="Kalender-Server für Kalender-Apps", en="Calendar server for calendar apps",
        gruppe="day", schalter=("calendar_server", "calendar"), anleitung="calserver", parent="calendar",
        me="calbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: Kalender-Apps erreichen den Spark über CalDAV (kalenderserver.py), "
                               "Termine per Sprache über calendar_add")),
    "feedsmelden": Steckbrief(de="Neues aus Feeds melden", en="Telling news from feeds", gruppe="day",
        schalter=("feeds", "proactive"), anleitung="feeds", pref="pro_feeds", parent="proactive", me="probox",
        ohne_werkzeug=("ohne", "meldet sich von selbst")),
    # „Mach ein Issue draus“ (meldung.by_answer, Dominik 2026-11-13): a report for one answer goes out at once,
    # anonymized, only when the leak check finds nothing; off, the draft waits for the person's look
    "meldendirekt": Steckbrief(de="Antwort-Meldungen direkt an GitHub", en="Answer reports straight to GitHub",
        gruppe="sec", schalter=("report_direct",), anleitung="meldendirekt", parent="melden", me="rpbox",
        ohne_werkzeug=("regel", "meldung.py: „Mach ein Issue draus“ und „Melden“ unter der Antwort")),
    # postfach.py (plan kalender-mail Stufe 2, Mailclient Stufe A): on the page E-Mail read/unread, flag, archive, move
    # (also several at once), every folder read, own folders made, renamed, removed when empty
    "mailmanage": Steckbrief(de="Mails ordnen", en="Order mail", gruppe="post", schalter=("mail_manage", "mail"),
        anleitung="mailmanage", parent="mail", me="mailbox",
        ohne_werkzeug=("ohne", "nur Knöpfe auf der Seite E-Mail (gelesen, Archiv, Verschieben); per Stimme ordnet "
                               "Postfach aufräumen")),
    # spaeter.py (pl_mail-Ideen 2, Dominik 2026-11-13 „1-7“): a mail out of the inbox into „<KI folder>/Später“ and back,
    # unread, at a fixed time; buttons only, never the model
    "mailspaeter": Steckbrief(de="Zurückstellen", en="Snooze mail", gruppe="post",
        schalter=("mail_later", "mail_manage", "mail"), anleitung="mailspaeter", parent="mailmanage", me="mailbox",
        ohne_werkzeug=("ohne", "nur Knöpfe auf der Seite E-Mail und in den Apps (Später, Jetzt zurückholen); die "
                               "Mail kommt zu einer festen Zeit von selbst zurück"),
        modul=("spaeter", "post", "Zurückstellen: Mail in „Später“ und zur gewählten Zeit ungelesen zurück in den "
                                  "Posteingang")),
    "mailsend": Steckbrief(de="Mails senden", en="Send mail", gruppe="post", schalter=("mail_send", "mail"),
        anleitung="mailsend", parent="mail", me="mailbox",
        ohne_werkzeug=("ohne", "kein Werkzeug fürs Modell: Vorschau-Blatt auf der Seite, per Sprache feste Sätze des "
                               "Panels (senden.answer) mit Ja")),
    # mailidle.py (Vorwärmen Stufe C, Dominik 2026-10-19 „6a“): IMAP IDLE for profiles that read mail lately, new mail
    # and its rules within seconds, at most mailidle.MAX_OPEN connections
    # postfach.py „Löschen“ (Dominik 2026-10-20): the person moves a message into the trash and back, or removes one
    # there for good after the page's own question; rules, the model, „Für dich“ and the voice never delete
    "maildelete": Steckbrief(de="Mails löschen", en="Delete mail", gruppe="post",
        schalter=("mail_delete", "mail_manage", "mail"), anleitung="maildelete", parent="mailmanage", me="mailbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: nur Knopf, Taste oder Ziehen auf der Seite E-Mail; Modell, Regeln, "
                               "Für dich und Stimme löschen nie")),
    # mailregeln.py „Sortieren aus Korrekturen lernen“ (Dominik 2026-10-30, plan mail-lernen 3a 4a 5a): a mail the Spark sorted and
    # the person put elsewhere (or into „Falsch sortiert“) is a correction; fixed thresholds make an exception, pause a
    # rule and bring the card „Regel-Vorschlag“; never the model
    "maillearn": Steckbrief(de="Sortieren aus Korrekturen lernen", en="Learn sorting from corrections",
        gruppe="post", schalter=("mail_learn", "mail_manage", "mail"), anleitung="maillearn", parent="mailmanage",
        me="mailbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: erkennt umsortierte Mails nach festen Regeln (Seite, Regel-Lauf, "
                               "Nachtlauf), Knöpfe nur auf der Karte Regel-Vorschlag")),
    # einladung.py (Dominik 2026-10-21 „ja alles umsetzen 1-6“, Punkt 3): an invitation (.ics) in a mail into a calendar
    # with one tap, Zusagen/Vielleicht/Absagen to the organiser (with „Mails senden“)
    "einladungen": Steckbrief(de="Einladungen aus Mails", en="Invitations from mail", gruppe="post",
        schalter=("mail_invites", "mail", "calendar"), anleitung="einladungen", parent="mail", me="mailbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: die Einladung nimmt nur der Tipp auf der Seite E-Mail an, nie der "
                               "Assistent")),
    "mailidle": Steckbrief(de="Neue Mails sofort", en="New mail at once", gruppe="post",
        schalter=("mail_idle", "mail"), anleitung="mailidle", parent="mail", me="mailbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: hält die Posteingänge per IMAP IDLE offen, die Seite E-Mail und die "
                               "Mail-Regeln bekommen neue Mails in Sekunden"),
        modul=("mailidle", "post", "Neue Mails sofort: IMAP IDLE für Profile, die ihre Mails gerade lesen, höchstens "
                                   "4 Verbindungen")),
    # mailcode.py (Dominik 2026-10-21 „5“): a new mail with a confirmation code as a note on the device in use, never
    # Telegram, the code never logged; needs Neue Mails sofort
    "mailcode": Steckbrief(de="Bestätigungscodes", en="Confirmation codes", gruppe="post",
        schalter=("mail_code", "mail_idle", "mail"), anleitung="mailcode", parent="mailidle", me="mailbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: feste Regeln finden den Code in einer neuen Mail, eine Mitteilung "
                               "aufs genutzte Gerät, nie Telegram"),
        modul=("mailcode", "post", "Bestätigungscodes: Code aus neuer Mail als Mitteilung aufs genutzte Gerät, nie "
                                   "Telegram, nie im Log")),
    "mailstil": Steckbrief(de="Mailstil lernen", en="Learn mail style", gruppe="post", schalter=("mail_style",),
        anleitung="mailstil", parent="mail", me="mailbox",
        ohne_werkzeug=("ohne", "wirkt in jedem Mail-Entwurf (mail_draft, Begleiter); gelernt wird nur auf Knopfdruck "
                               "unter E-Mail → Einstellungen"),
        modul=("mailstil", "post", "Mailstil: lernt aus gesendeten Mails, wie das Profil schreibt, für Mail-Entwürfe")),
    # ichweiss.py (stages 3 and 4, „3a 4a 6a 7a“): interests with their evidence (count after „Stimmt“), Wiederkehrendes,
    # the week and the month, one web tip a day; part of the same switch, its own page under Ich
    "ichweiss": Steckbrief(de="Was ich über dich weiß", en="What I know about you", gruppe="post",
        schalter=("mail_insight",), anleitung="ichweiss", parent="fuerdich", me="wissbox",
        ohne_werkzeug=("ohne", "eine Seite unter Ich → Was ich über dich weiß; Fristen und Rückblick per Sprache "
                               "über fuer_dich"),
        modul=("ichweiss", "dienste", "Was ich über dich weiß: Interessen als Themen mit Beleg, Wiederkehrendes, "
                                      "Woche, Monat, ein Netz-Tipp am Tag")),
    "schreibapps": Steckbrief(de="Schreibhilfe in anderen Programmen", en="Writing help in other programs",
        gruppe="post", schalter=("write_apps",), anleitung="schreibapps", parent="schreib", me="writebox",
        ohne_werkzeug=("ohne", "Kanal in anderen Programmen")),
    # contacts.py page Kontakte (Apple-Stil „6a“): a card changed in its own address book (ETag), new ones there or on the Spark
    "kontakteaendern": Steckbrief(de="Kontakte ändern", en="Edit contacts", gruppe="post",
        schalter=("contacts_edit", "contacts"), anleitung="kontakteaendern", parent="contacts", me="conbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: nur Bearbeiten auf der Seite Kontakte und in der iPhone-App; Modell "
                               "und Stimme ändern nie Kontakte")),
    # kontaktserver.py (Apple-Stil „6a“ Stufe 3b): the address book „Auf dem Spark“ for the iPhone's Kontakte app (CardDAV,
    # the Kalender-Server's app password)
    "kontaktserver": Steckbrief(de="Kontakte für Kontakte-Apps", en="Contacts for contacts apps", gruppe="post",
        schalter=("contacts_server", "contacts", "calendar_server"), anleitung="kontaktserver", parent="contacts",
        me="conbox",
        ohne_werkzeug=("ohne", "kein Werkzeug: Kontakte-Apps erreichen den Spark über CardDAV (kontaktserver.py)"),
        modul=("kontaktserver", "post", "Kontakte-Server: das Adressbuch „Auf dem Spark“ für Kontakte-Apps (CardDAV "
                                        "unter /carddav/)")),
    "room": Steckbrief(de="Raum-Modus", en="Room mode", gruppe="home", schalter=("room",), anleitung="room",
        me="roombox",
        ohne_werkzeug=("regel", "room.py, roomfar.py: „Raummodus an/aus“, „Ist der Raummodus im Wohnzimmer an?“"),
        begleiter="device", modul=("room", "geraete", "Raummodus: hört zu und hilft in einer Pause")),
    "roomtv": Steckbrief(de="Fernsehstimmen überhören", en="Ignore TV voices", gruppe="home",
        schalter=("room_voices",), anleitung="roomtv", parent="room", me="roombox",
        ohne_werkzeug=("ohne", "Verhalten im Raum-Modus")),
    "roomha": Steckbrief(de="Raum-Modus für Home Assistant", en="Room mode for Home Assistant", gruppe="home",
        schalter=("room_ha",), anleitung="roomha", parent="room", me="roombox",
        ohne_werkzeug=("ohne", "Verhalten im Raum-Modus")),
    "espstopp": Steckbrief(de="Stopp beim Vorlesen", en="Stop while it speaks", gruppe="home",
        schalter=("esp32_stop", "esp32"), anleitung="espstopp", parent="esp32", me="espbox",
        ohne_werkzeug=("regel", "esp32.py: „Stopp“ beim Vorlesen")),
    "roomfar": Steckbrief(de="Raum-Modus aus der Ferne starten", en="Start room mode from afar", gruppe="home",
        schalter=("room_remote", "esp32"), anleitung="roomfar", parent="room", me="roombox",
        ohne_werkzeug=("regel", "roomfar.py: „Raummodus im Wohnzimmer an“, erst nach Ja"),
        modul=("roomfar", "geraete", "Raummodus auf einem anderen Gerät schalten")),
    "wyoming": Steckbrief(de="Home Assistant Assist (Wyoming)", en="Home Assistant Assist (Wyoming)", gruppe="home",
        schalter=("wyoming",), anleitung="wyoming", ohne_werkzeug=("ohne", "Kanal für Home Assistant Assist"),
        begleiter="device", modul=("wyoming", "geraete", "Home Assistant Assist über Wyoming")),
    # Den Spark anrufen (telefon.py, plan telefon-anruf.md): the Spark as an IP phone at the home's PBX
    "telefon": Steckbrief(de="Telefon", en="Phone", gruppe="home", schalter=("telefon",), anleitung="telefon",
        me="telbox", ohne_werkzeug=("ohne", "Kanal: Anruf über die Telefonanlage"), begleiter="device",
        modul=("telefon", "geraete", "Den Spark anrufen: SIP mit der Telefonanlage, Gespräch wie am Lautsprecher")),
    # handsets nobody assigned get questions and answers as a guest (never a tool); off: a sentence, then hang up
    "telefongast": Steckbrief(de="Telefon: Gäste annehmen", en="Phone: take guests", gruppe="home",
        schalter=("telefon_gaeste", "telefon"), anleitung="telefongast", parent="telefon",
        ohne_werkzeug=("ohne", "Gäste am Telefon: nur Frage und Antwort")),
    # calls from outside through the PBX: confirmed own numbers (Ich → Telefon) as their profile, with Gäste also unknown ones
    "telefonaussen": Steckbrief(de="Telefon: Anrufe von außen", en="Phone: calls from outside", gruppe="home",
        schalter=("telefon_aussen", "telefon"), anleitung="telefonaussen", parent="telefon",
        ohne_werkzeug=("ohne", "Anrufe von außen: die bestätigte Nummer wählt das Profil")),
    # a service gone 10 minutes or more: a call to the admin besides the note, never in the quiet hours
    "telefonalarm": Steckbrief(de="Telefon: Anruf bei Dienstausfall", en="Phone: call on outages", gruppe="home",
        schalter=("telefon_alarm", "telefon_anrufen", "telefon", "svc_watch"), anleitung="telefonalarm",
        parent="telefonanrufen", ohne_werkzeug=("ohne", "Alarm-Anruf an den Admin, vom Dienst-Wächter ausgelöst")),
    "telegram": Steckbrief(de="Telegram", en="Telegram", gruppe="go", schalter=("telegram",), anleitung="telegram",
        me="tgbox", ohne_werkzeug=("ohne", "Kanal"), begleiter="device",
        modul=("telegram", "geraete", "Telegram-Bot für Text und Sprachnachrichten")),
    "android": Steckbrief(de="Android-App", en="Android app", gruppe="go", schalter=("android",),
        anleitung="android", me="andbox", ohne_werkzeug=("ohne", "Kanal"), begleiter="device",
        modul=("android", "geraete", "Android-App: Download, Mitteilungen, Update, Assistent und Fingerabdruck")),
    "androidlive": Steckbrief(de="Android: Mitteilungen sofort", en="Android: notes at once", gruppe="go",
        schalter=("android_live",), anleitung="androidlive", pref="android_live", parent="android", me="andbox",
        ohne_werkzeug=("ohne", "Kanal")),
    "androidupdate": Steckbrief(de="Android: Update in der App", en="Android: update in the app", gruppe="go",
        schalter=("android_update",), anleitung="androidupdate", parent="android", me="andbox",
        ohne_werkzeug=("ohne", "macht die App selbst")),
    "androidassist": Steckbrief(de="Android: Spark als Assistent", en="Android: Spark as assistant", gruppe="go",
        schalter=("android_assist",), anleitung="androidassist", parent="android", me="andbox",
        ohne_werkzeug=("ohne", "Kanal")),
    "androidlock": Steckbrief(de="Android: Fingerabdruck für Admins", en="Android: fingerprint for admins",
        gruppe="go", schalter=("android_lock",), anleitung="androidlock", parent="android", me="andbox",
        ohne_werkzeug=("ohne", "macht die App selbst")),
    "begleitermeeting": Steckbrief(de="Besprechungen mitschreiben", en="Write along in meetings", gruppe="go",
        schalter=("desk_meeting",), anleitung="begleitermeeting", parent="begleiter", me="deskbox",
        ohne_werkzeug=("ohne", "startet am Begleiter")),
    # Rechner fernsteuern, Stufe 2 (fernsicht.py): look at the own PC or Mac and, when allowed there, operate it
    "begleiterschirm": Steckbrief(de="Bildschirm zeigen und bedienen", en="Show and operate the screen", gruppe="go",
        schalter=("desk_view",), anleitung="begleiterschirm", parent="begleiter", me="deskbox",
        ohne_werkzeug=("ohne", "startet unter Ich → Begleiter, bedient wird mit Maus und Tastatur, nicht per Sprache")),
    "pebble": Steckbrief(de="Pebble-Uhr", en="Pebble watch", gruppe="go", schalter=("pebble",),
        anleitung="pebblepair", me="pebbox", ohne_werkzeug=("ohne", "Kanal"), begleiter="device"),
    # more on the watch (pebblewatch.py, plan pebble-ideen/plan.md): follow-ups to tap, the profile's own fixed commands,
    # its reminders and timers kept on the watch as wake-ups (they ring without the phone)
    "pebblefolge": Steckbrief(de="Uhr: Nachfragen zum Antippen", en="Watch: follow-ups to tap", gruppe="go",
        schalter=("pebble_follow",), anleitung="pebblefolge", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: Vorschläge unter einer Antwort")),
    "pebbleschnell": Steckbrief(de="Uhr: Schnellbefehle", en="Watch: quick commands", gruppe="go",
        schalter=("pebble_quick",), anleitung="pebbleschnell", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: feste Sätze gehen als Frage")),
    "pebbleerinnern": Steckbrief(de="Uhr: Erinnerungen und Timer am Handgelenk",
        en="Watch: reminders and timers on the wrist", gruppe="go", schalter=("pebble_remind", "reminders"),
        anleitung="pebbleerinnern", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: die Erinnerungs-Werkzeuge bleiben dieselben")),
    # Paket 2: a watchface of its own, the day and the week, outage notes for admins, quick notes (with the place)
    "pebblezifferblatt": Steckbrief(de="Spark-Zifferblatt", en="Spark watchface", gruppe="go",
        schalter=("pebble_face",), anleitung="pebblezifferblatt", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: das Zifferblatt zeigt nur an")),
    "pebbletag": Steckbrief(de="Uhr: Mein Tag und meine Woche", en="Watch: my day and my week", gruppe="go",
        schalter=("pebble_day",), anleitung="pebbletag", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: feste Sätze aus den eigenen Daten")),
    "pebblemeldung": Steckbrief(de="Uhr: Meldungen für Admins", en="Watch: notes for admins", gruppe="go",
        schalter=("pebble_alerts", "svc_watch"), anleitung="pebblemeldung", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: zeigt die Meldungen des Dienst-Wächters")),
    "pebblemerken": Steckbrief(de="Uhr: Schnell merken", en="Watch: quick notes", gruppe="go",
        schalter=("pebble_note", "memory"), anleitung="pebblemerken", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: dasselbe Gedächtnis wie „merk dir“")),
    "pebbleort": Steckbrief(de="Uhr: Ort beim Merken", en="Watch: place with a note", gruppe="go",
        schalter=("pebble_place", "pebble_note", "memory"), anleitung="pebbleort", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: der Ort hängt am gemerkten Satz")),
    # Paket 3: the chats on the watch (with reply suggestions), a remote for picked devices, steps, pulse and sleep
    "pebblechat": Steckbrief(de="Uhr: Nachrichten", en="Watch: messages", gruppe="go",
        schalter=("pebble_chat", "chats"), anleitung="pebblechat", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: dieselben Chats wie im Panel, geschickt nur auf Tippen")),
    "pebbleantwort": Steckbrief(de="Uhr: Antwortvorschläge", en="Watch: reply suggestions", gruppe="go",
        schalter=("pebble_reply", "pebble_chat", "chats"), anleitung="pebbleantwort", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: Vorschläge zum Antippen, das Modell schickt nichts")),
    "pebblefern": Steckbrief(de="Uhr: Fernbedienung", en="Watch: remote", gruppe="go", schalter=("pebble_remote",),
        anleitung="pebblefern", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: feste Tasten für selbst gewählte Geräte")),
    "pebblegesund": Steckbrief(de="Uhr: Schritte, Puls und Schlaf", en="Watch: steps, pulse and sleep", gruppe="go",
        schalter=("pebble_health",), anleitung="pebblegesund", parent="pebble", me="pebbox",
        ohne_werkzeug=("ohne", "macht die Uhr selbst: nur Zahlen der Uhr, nie für das Modell")),
    # spark-tui in a terminal (terminal.py): chat, conversations, Heute and the agent's jobs, paired by a setup line
    "terminal": Steckbrief(de="Terminal-Client", en="Terminal client", gruppe="go", schalter=("terminal",),
        anleitung="terminal", me="termbox", ohne_werkzeug=("ohne", "Kanal"), begleiter="device",
        modul=("terminal", "geraete", "Terminal-Client spark-tui: Kopplung mit gepinntem Zertifikat, Schlüssel nur "
                                      "für Chat, Heute, Aufträge")),
    # new firmware and app versions for the devices (geraeteupdate.py): overview, notes, speakers at night, XiaoZhi
    "geraeteupdate": Steckbrief(de="Geräte-Updates", en="Device updates", gruppe="go", schalter=("dev_updates",),
        anleitung="geraeteupdate", me="setbox", ohne_werkzeug=("ohne", "läuft im Hintergrund"), begleiter="spark",
        modul=("geraeteupdate", "geraete", "Übersicht und Hinweise zu Geräte-Updates")),
    "geraetenacht": Steckbrief(de="Lautsprecher nachts aktualisieren", en="Update speakers at night", gruppe="go",
        schalter=("dev_updates_night", "esp32"), anleitung="geraetenacht", pref="devup_night",
        parent="geraeteupdate", me="setbox", ohne_werkzeug=("ohne", "läuft im Hintergrund")),
    "xiaozhihinweis": Steckbrief(de="Hinweis auf neue XiaoZhi-Version", en="Note on a new XiaoZhi version",
        gruppe="go", schalter=("dev_updates_upstream",), anleitung="xiaozhihinweis", parent="geraeteupdate",
        ohne_werkzeug=("ohne", "meldet sich von selbst")),
    "mcpserver": Steckbrief(de="Spark als MCP-Server", en="Spark as MCP server", gruppe="go",
        schalter=("mcp_server",), anleitung="mcpserver", me="mcpbox",
        ohne_werkzeug=("ohne", "Schnittstelle für andere Programme"), begleiter="device",
        modul=("mcpserver", "dienste", "Der Spark als MCP-Server für andere Programme")),
    "mcpextern": Steckbrief(de="MCP-Server von außen (OAuth)", en="MCP server from outside (OAuth)", gruppe="go",
        schalter=("mcp_server_extern",), anleitung="mcpextern", parent="mcpserver", me="mcpbox",
        ohne_werkzeug=("ohne", "Schnittstelle für andere Programme")),
    "mcpact": Steckbrief(de="MCP: Handeln mit Bestätigung", en="MCP: acting with confirmation", gruppe="go",
        schalter=("mcp_server_act",), anleitung="mcpact", parent="mcpserver", me="mcpbox",
        ohne_werkzeug=("ohne", "Schnittstelle für andere Programme")),
    # Sprachmodell per API (llmapi.py): own programs use the plain language model at /v1 with a key of their profile
    "llmapi": Steckbrief(de="Sprachmodell per API", en="Language model by API", gruppe="go", schalter=("llm_api",),
        anleitung="llmapi", me="llmapibox", ohne_werkzeug=("ohne", "Schnittstelle für andere Programme"),
        begleiter="device",
        modul=("llmapi", "dienste", "Sprachmodell per API: OpenAI-kompatibel unter /v1 mit Schlüssel je Profil")),
    "llmapiextern": Steckbrief(de="Sprachmodell per API von außen", en="Language model by API from outside",
        gruppe="go", schalter=("llm_api_extern",), anleitung="llmapiextern", parent="llmapi", me="llmapibox",
        ohne_werkzeug=("ohne", "Schnittstelle für andere Programme")),
    # Spark-Assistent per API (llmapi.ASSIST): the model "spark-assistent" is one read-only turn of the assistant, like „Spark fragen“
    "llmapiassist": Steckbrief(de="Spark-Assistent per API", en="Spark assistant by API", gruppe="go",
        schalter=("llm_api_assistant",), anleitung="llmapiassist", parent="llmapi", me="llmapibox",
        ohne_werkzeug=("ohne", "Schnittstelle für andere Programme"), begleiter="device"),
    # Open WebUI einbinden (openwebui.py): one step makes its key and MCP connection; the menu links to it, the Wächter watches it
    "openwebui": Steckbrief(de="Open WebUI einbinden", en="Open WebUI integration", gruppe="go",
        schalter=("openwebui",), anleitung="openwebui", parent="llmapi", me="llmapibox",
        ohne_werkzeug=("ohne", "Schnittstelle für andere Programme"), begleiter="device",
        modul=("openwebui", "dienste", "Open WebUI einbinden: Schlüssel und MCP-Zugang in einem Schritt, Menü-Link, "
                                       "Wächter")),
    "iphonepush": Steckbrief(de="Push an die iPhone-App", en="Push to the iPhone app", gruppe="go",
        schalter=("iphone_push",), anleitung="iphonepush", pref="app_push", parent="iphone", me="appbox",
        ohne_werkzeug=("ohne", "Kanal")),
    "iphonepanel": Steckbrief(de="Panel-Bereiche in der iPhone-App", en="Panel areas in the iPhone app", gruppe="go",
        schalter=("iphone_panel",), anleitung="iphonepanel", parent="iphone", me="appbox",
        ohne_werkzeug=("ohne", "Kanal")),
    # appmerken.py: the iPhone and the Android app keep the last state of their profile on the phone (no files, no keys)
    "appmerken": Steckbrief(de="Apps merken sich den letzten Stand", en="Apps keep the last state", gruppe="go",
        schalter=("app_cache",), anleitung="appmerken",
        ohne_werkzeug=("ohne", "Speicher in der App, nichts zu fragen"), begleiter="device",
        modul=("appmerken", "geraete", "Apps merken sich den letzten Stand: ob eine App ihn behalten darf, langsame "
                                       "Seiten ins Log")),
    # pruefzugang.py: Apple's app review pairs with a typed code instead of the 10-minute link
    "iphonepruef": Steckbrief(de="Prüfzugang für die iPhone-App", en="Review access for the iPhone app", gruppe="go",
        schalter=("iphone_review",), anleitung="iphonepruef", parent="iphone",
        ohne_werkzeug=("ohne", "Zugang für Apples Prüfung in der Oberfläche")),
    "iphoneupdate": Steckbrief(de="Spark-Update über die iPhone-App", en="Spark update from the iPhone app",
        gruppe="go", schalter=("iphone_update",), anleitung="iphoneupdate", parent="iphone",
        ohne_werkzeug=("ohne", "nur mit Code in der App")),
    "speaker": Steckbrief(de="Sprechererkennung", en="Speaker recognition", gruppe="sec", schalter=("speaker_id",),
        anleitung="speaker", me="voicebox", ohne_werkzeug=("ohne", "Schutzregel"), begleiter="panel"),
    "spkcode": Steckbrief(de="Codewort am Lautsprecher", en="Code word at a speaker", gruppe="sec",
        schalter=("speaker_code", "esp32"), anleitung="spkcode", parent="speaker", me="espbox",
        ohne_werkzeug=("ohne", "Schutzregel"), modul=("spkcode", "geraete", "Codewort am geteilten Lautsprecher")),
    "mfa": Steckbrief(de="Zweiter Anmeldeschritt", en="Second sign-in step", gruppe="sec", schalter=("mfa",),
        anleitung="mfa", me="secbox", ohne_werkzeug=("ohne", "Zugangsgeheimnis"),
        begleiter="stays in the panel; the Begleiter's settings (Übersicht) link to its place (Meine Daten on the "
                  "Ich page Sicherheit)",
        modul=("mfa", "zugang", "Zweiter Anmeldeschritt mit Code (TOTP) und Wiederherstellungscodes")),
    # reports as GitHub issues with anonymized log lines (meldung.py); what goes out is shown before
    "melden": Steckbrief(de="Probleme melden", en="Reporting problems", gruppe="sec", schalter=("report",),
        anleitung="melden", me="rpbox", ohne_werkzeug=("regel", "meldung.py: „Spark, Problem melden: …“"),
        begleiter="stays in the panel; the Begleiter's Kopplung page opens it (Problem melden …)"),
    # Erfundenes automatisch melden (Dominik 2026-11-14 „Ok“): an answer the background check holds for made up becomes a
    # report like „Melden“ under it, at most systemone.MARK_REPORTS a day; with „direkt an GitHub“ an issue at once
    "meldenerfunden": Steckbrief(de="Erfundenes automatisch melden", en="Report made-up answers by itself",
        gruppe="sec", schalter=("report_madeup", "report"), anleitung="meldenerfunden", parent="melden", me="rpbox",
        ohne_werkzeug=("regel", "systemone.py: nach der Antwort-Prüfung, nie das Modell")),
    "meldenadmin": Steckbrief(de="Admin über Meldungen informieren", en="Tell admins about reports", gruppe="sec",
        schalter=("report_notify",), anleitung="meldenadmin", parent="melden", me="rpbox",
        ohne_werkzeug=("ohne", "meldet sich von selbst")),
    # verbrauch.py (plan plaene/token-zaehler.md): how much the models do, numbers only; each profile sees its own
    # under Ich → Verbrauch; the quota limits a profile's language model tokens per day, week and month (admins never)
    "verbrauch": Steckbrief(de="Verbrauchszähler", en="Usage counter", gruppe="sec", schalter=("usage_count",),
        anleitung="verbrauch", me="usebox",
        ohne_werkzeug=("ohne", "Seiten Zustand → Verbrauch und Ich → Verbrauch, nur Zahlen"), begleiter="panel",
        modul=("verbrauch", "betrieb", "Verbrauchszähler je Modell, Aufgabe und Profil, Kontingent für Tag, Woche "
                                       "und Monat")),
    "kontingent": Steckbrief(de="Kontingent", en="Quota", gruppe="sec", schalter=("usage_quota",),
        anleitung="kontingent", parent="verbrauch", me="usebox",
        ohne_werkzeug=("ohne", "fester Satz im Gespräch, kein Werkzeug")),
    # dienstwacht.py: the Spark looks at its services and tells the admins when one is gone and when it is back
    "dienstwacht": Steckbrief(de="Dienst-Wächter", en="Service watch", gruppe="sec", schalter=("svc_watch",),
        anleitung="dienstwacht", pref="svc_note", me="setbox", ohne_werkzeug=("ohne", "meldet sich von selbst"),
        begleiter="spark", modul=("dienstwacht", "betrieb", "Dienst-Wächter: meldet, wenn ein Dienst fehlt")),
    # rundlauf.py: every few minutes a real round trip (speak, hear, ask the model); told through the Dienst-Wächter
    "rundlauf": Steckbrief(de="Rundlauf prüfen", en="Round-trip check", gruppe="sec", schalter=("rundlauf",),
        anleitung="rundlauf", parent="dienstwacht",
        ohne_werkzeug=("ohne", "rundlauf.py: ein fester Probelauf durch Sprechen, Hören und Sprachmodell nach festen "
                               "Regeln, nur Zahlen, kein Werkzeug"),
        nur_spark=True,
        modul=("rundlauf", "betrieb", "Rundlauf-Wächter: alle paar Minuten ein Probelauf durch Sprechen, Hören, "
                                      "Sprachmodell; meldet über den Dienst-Wächter")),
    # wachposten.py: fixed rules on the change log (lockouts, new ways in, protection changed, log changed, quality
    # worse) notify the admins; the Selbst-Notaus (notaus.AUTO) stays apart
    "wachposten": Steckbrief(de="Wachposten", en="Sentry", gruppe="sec", schalter=("wachposten",),
        anleitung="wachposten",
        ohne_werkzeug=("ohne", "wachposten.py: feste Regeln auf dem Änderungsprotokoll melden den Admins, nichts zu "
                               "fragen, kein Werkzeug"),
        begleiter="spark", nur_spark=True,
        modul=("wachposten", "zugang", "Wachposten: feste Regeln auf dem Änderungsprotokoll melden den Admins "
                                       "Sperren, neue Zugänge, geänderten Schutz")),
    # wartung.py: while the language model, ASR or TTS is updated the Spark pauses on purpose (fixed sentence, background waits)
    "wartung": Steckbrief(de="Wartungspause", en="Maintenance pause", gruppe="sec", schalter=("wartung",),
        anleitung="wartung",
        ohne_werkzeug=("ohne", "Zustand → Wartungspause; in der Pause sagt das Panel einen festen Satz statt einer "
                               "Antwort"),
        begleiter="spark", nur_spark=True,
        modul=("wartung", "betrieb", "Wartungspause: Spark hält an, während ein Modell neu eingespielt wird")),
    "wartungauto": Steckbrief(de="Wartungspause bei Neustart", en="Maintenance pause on restart", gruppe="sec",
        schalter=("wartung_auto",), anleitung="wartungauto", parent="wartung",
        ohne_werkzeug=("ohne", "wartung.py: das Panel pausiert selbst, wenn ein Modell neu startet; kein Werkzeug"),
        nur_spark=True),
    # notbetrieb.py: with the models on another computer, Parakeet on this one hears while they are gone (fixed commands)
    "notbetriebasr": Steckbrief(de="Notbetrieb mit Parakeet", en="Emergency mode with Parakeet", gruppe="sec",
        schalter=("notbetrieb_asr",), anleitung="notbetriebasr",
        ohne_werkzeug=("ohne", "notbetrieb.py: feste Befehle nach festen Regeln, nur im Notbetrieb, kein "
                               "Sprachmodell und kein Werkzeug"),
        begleiter="spark", nur_spark=True),
    # gehaeuse.py: the case of a panel computer (Pironman 5): OLED pages for the admin, status LEDs, fan thresholds
    "gehaeuse": Steckbrief(de="Gehäuse", en="Case", gruppe="sec", schalter=("gehaeuse",), anleitung="gehaeuse",
        ohne_werkzeug=("ohne", "gehaeuse.py: Anzeige und LEDs am Panel-Rechner nach festen Regeln, nur Zahlen und "
                               "Status, kein Werkzeug"),
        begleiter="spark", nur_spark=True,
        modul=("gehaeuse", "teilen", "Gehäuse des Panel-Rechners (Pironman 5): OLED-Seiten für den Admin, "
                                     "Status-LEDs, Lüftergrenzen")),
    # systemupdates.py + ../sysupdate.py (Dominik 2026-11-04 „1a-4a“): the operating system of both computers, OpenCode and
    # the Python packages (OSV), firmware shown; installed only by the fixed root unit with a fresh code, never while
    # somebody talks, never a restart without the admin; admins only, no tool for the model
    "systemupdates": Steckbrief(de="System-Updates", en="System updates", gruppe="sec", schalter=("system_updates",),
        anleitung="systemupdates",
        ohne_werkzeug=("ohne", "systemupdates.py: nur der Admin im Panel, eingespielt wird ein fester Ablauf als "
                               "root mit frischem Code; das Modell bekommt kein Werkzeug"),
        begleiter="spark", nur_spark=True,
        modul=("systemupdates", "betrieb", "System-Updates: Betriebssystem beider Rechner prüfen und fest "
                                           "einspielen, OpenCode und OSV, Firmware nur zeigen")),
    # schwachstellen.py + ../osv.py (Dominik 2026-11-13 „1“): known holes in the Spark's packages, engines, Docker images
    # and operating system against OSV, with a fixed action each; only names and versions go out, only ids come back;
    # admins only, no tool for the model
    "schwachstellen": Steckbrief(de="Schwachstellen", en="Vulnerabilities", gruppe="sec", schalter=("schwachstellen",),
        anleitung="schwachstellen",
        ohne_werkzeug=("ohne", "schwachstellen.py: nur der Admin im Panel, feste Prüfung gegen OSV mit festen "
                               "Handlungssätzen; das Modell bekommt kein Werkzeug"),
        live=("schwachstellen", "Schwachstellen", "OSV · nur Paketnamen und Versionen · Internet", "net", False,
              "Kennungen, Schweregrad und Version mit Fix"),
        log=("system", "schwachstellen"),
        begleiter="spark", nur_spark=True,
        modul=("schwachstellen", "betrieb", "Schwachstellen: Pakete, Engines, Docker-Abbilder und Betriebssystem "
                                            "gegen OSV, je Fund ein fester Handlungssatz")),
    "systemnachtpanel": Steckbrief(de="System-Updates nachts auf dem Panel-Rechner",
        en="System updates at night on the panel computer", gruppe="sec", schalter=("system_updates_night_panel",),
        anleitung="systemnachtpanel", parent="systemupdates",
        ohne_werkzeug=("ohne", "systemupdates.py: der feste Ablauf nachts nach festen Regeln (Nachtfenster, "
                               "Sprechpause), kein Werkzeug"),
        nur_spark=True),
    "systemnachtmodelle": Steckbrief(de="System-Updates nachts auf dem Modell-Rechner",
        en="System updates at night on the model computer", gruppe="sec", schalter=("system_updates_night_models",),
        anleitung="systemnachtmodelle", parent="systemupdates",
        ohne_werkzeug=("ohne", "systemupdates.py und der feste Wärter-Befehl systemupdate_tun nachts nach festen "
                               "Regeln, kein Werkzeug"),
        nur_spark=True),
    # schirm.py + steuerzentrale.py (B9): the control centre as text on the panel computer's screen (tty1), no desktop
    "schirm": Steckbrief(de="Steuerzentrale am Bildschirm", en="Control centre on the screen", gruppe="sec",
        schalter=("schirm",), anleitung="schirm",
        ohne_werkzeug=("ohne", "schirm.py und steuerzentrale.py: Textanzeige am Bildschirm des Panel-Rechners, nur "
                               "Art, Ort, Zeit und Zahlen, kein Werkzeug"),
        begleiter="spark", nur_spark=True,
        modul=("schirm", "teilen", "Steuerzentrale am Bildschirm: was die Textanzeige zeigt, nur lokal mit "
                                   "Schlüssel; der Dienst folgt dem Schalter")),
    # modelle.py stage E4: admins switch the model of one kind under Zustand → Modelle (root unit speech-spark-wechsel)
    "modellwechsel": Steckbrief(de="Modelle wechseln", en="Switch models", gruppe="sec",
        schalter=("modelle_wechseln",), anleitung="modellwechsel",
        ohne_werkzeug=("ohne", "Zustand → Modelle, nur Admins mit frischem Code; Wechsel und Messen laufen als root "
                               "in speech-spark-wechsel und speech-spark-messen-wunsch, kein Werkzeug"),
        begleiter="spark", nur_spark=True),
    # modelle.py stage E5: the admin adds own Hugging Face models (language model, image understanding) under fixed rules
    "modelleeigen": Steckbrief(de="Eigene Modelle", en="Own models", gruppe="sec", schalter=("modelle_eigene",),
        anleitung="modelleeigen", parent="modellwechsel",
        ohne_werkzeug=("ohne", "Zustand → Modelle, nur Admins; das Panel liest nur Metadaten von Hugging Face, kein "
                               "Werkzeug"),
        nur_spark=True),
    # werkstattseite.py + werkstatt.py (plan opencode-werkstatt): test run, code measurement, diagnosis and repairs in a
    # sandbox on the model computer (OpenCode, no data, no internet, no push); admins only, the patch goes to a person
    "werkstatt": Steckbrief(de="Werkstatt", en="Workshop", gruppe="sec", schalter=("werkstatt",),
        anleitung="werkstatt",
        ohne_werkzeug=("ohne", "werkstattseite.py: Aufträge nur vom Admin auf der Seite oder nach der festen "
                               "Nachtregel; der Agent bekommt kein Werkzeug, das Code laufen lässt"),
        begleiter="spark", nur_spark=True,
        modul=("werkstatt", "betrieb", "Werkstatt: feste Regeln für Aufträge, Sandbox ohne Netz und Daten, OpenCode, "
                                       "Code-Messung mit 10 Reparaturen")),
    "werkstattnacht": Steckbrief(de="Jede Nacht testen", en="Test every night", gruppe="sec",
        schalter=("werkstatt_nacht",), anleitung="werkstattnacht", parent="werkstatt",
        ohne_werkzeug=("ohne", "werkstattseite.py: feste Nachtregel im Panel (Testlauf, danach Code-Messung), kein "
                               "Werkzeug"),
        nur_spark=True),
    # entwickeln.py + entwickelnseite.py (plan opencode-pi, package 1): OpenCode with the own language model in the
    # terminal of the panel computer (user spark-dev, its own clone), local changes installed like an update (Weg B)
    "entwickeln": Steckbrief(de="Entwickeln auf dem Pi", en="Develop on the Pi", gruppe="sec",
        schalter=("entwickeln",), anleitung="entwickeln",
        ohne_werkzeug=("ohne", "entwickeln.py: OpenCode nur im Terminal von spark-dev, einspielen nur ein Admin "
                               "(Kommandozeile oder Panel-Endpunkt); das Modell im Gespräch bekommt kein Werkzeug "
                               "dafür"),
        begleiter="spark", nur_spark=True,
        modul=("entwickeln", "betrieb", "Entwickeln auf dem Pi: OpenCode für spark-dev, lokal prüfen, testen, "
                                        "einspielen; Zweig an GitHub; Terminal-Einheit")),
    # entwickeln.py an_github (package 2, Weg A): spark-dev's branch to GitHub as opencode/<thema> for a Claude thread
    # to review; root pushes it with its own deploy key, never main, never forced; spark-dev stays off the internet
    "entwickelngithub": Steckbrief(de="An GitHub geben", en="Hand to GitHub", gruppe="sec",
        schalter=("entwickeln_github",), anleitung="entwickelngithub", parent="entwickeln",
        ohne_werkzeug=("ohne", "entwickeln.py an_github: nur ein Admin gibt den Zweig weiter (Kommandozeile oder "
                               "Panel-Endpunkt mit Code), feste Regeln, kein Werkzeug fürs Modell"),
        nur_spark=True),
    # entwickelnseite.py (package 3): a shell as spark-dev in the browser under Zustand → Werkstatt → Entwickeln, a fresh
    # code every session; root's fixed program starts it in a unit of its own, never as the panel's user or root
    "entwickelnterminal": Steckbrief(de="Terminal im Browser", en="Terminal in the browser", gruppe="sec",
        schalter=("entwickeln_terminal",), anleitung="entwickelnterminal", parent="entwickeln",
        ohne_werkzeug=("ohne", "entwickelnseite.py: eine Shell als spark-dev nur für einen Admin im Browser mit "
                               "frischem Code; das Modell im Gespräch bekommt kein Werkzeug dafür und sieht nie, was "
                               "dort läuft"),
        nur_spark=True),
    # fernzugang.py + anker/spark-anker.py (plan ssh-vermittlung, stage 1): the shell of a server elsewhere in the
    # browser; the server's anchor calls the panel, admins only, no tool for the model
    "fernzugang": Steckbrief(de="Fernzugang zu Servern", en="Remote access to servers", gruppe="sec",
        schalter=("fernzugang",), anleitung="fernzugang",
        ohne_werkzeug=("ohne", "fernzugang.py: die Shell eines Fern-Servers nur vom Admin auf Fernzugang → Systeme; "
                               "das Modell bekommt kein Werkzeug und nie eine Ausgabe der Shell"),
        begleiter="an admin page, stays in the panel; the Begleiter's settings (Übersicht) link to it for an admin",
        nur_spark=True,
        modul=("fernzugang", "fern", "Fernzugang: Seite per Code entsperrt, Anker, Einmal-Code, Terminal mit Ticket, "
                                     "Host-Schlüssel fest, Shell gehalten")),
    # a push to the admins when a remote session opens from the internet or a new place (on under the switch)
    "fernzugangmeldung": Steckbrief(de="Meldung bei Fernsitzung", en="Note on a remote session", gruppe="sec",
        schalter=("fernzugang_meldung",), anleitung="fernzugangmeldung", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernzugang.py: feste Mitteilung an die Admins und eine feste Zeile im Journal des "
                               "Servers nach festen Regeln, nie eine Adresse, kein Werkzeug"),
        nur_spark=True),
    # Mehrere Sitzungen Stufe 4 (Dominik 2026-10-30 „alle“, mockup 4-an-alle): one line into several open shells, off
    "fernzugangalle": Steckbrief(de="An alle senden im Fernzugang", en="Send to all in remote access", gruppe="sec",
        schalter=("fernzugang_alle",), anleitung="fernzugangalle", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernzugang.py: eine Zeile an mehrere offene Shells desselben Admins nach festen "
                               "Regeln (eine Art System, nie die Vorsicht-Liste), nach Rückfrage im Browser; kein "
                               "Werkzeug, das Modell fügt dort nie ein"),
        nur_spark=True),
    # spontanhilfe.py (plan spontanhilfe, S1): a person shares her screen once in the browser (/hilfe), admins only
    "spontanhilfe": Steckbrief(de="Spontanhilfe", en="Spontaneous help", gruppe="sec", schalter=("spontanhilfe",),
        anleitung="spontanhilfe", parent="fernzugang",
        ohne_werkzeug=("ohne", "spontanhilfe.py: eine Person teilt einmal ihren Bildschirm im Browser, nur Admins "
                               "helfen; das Modell bekommt kein Werkzeug und nie ein Bild oder den Chat"),
        nur_spark=True,
        modul=("spontanhilfe", "fern", "Spontanhilfe: Nummer und Link, Seite /hilfe mit eigener CSP, WebRTC zwischen "
                                       "zwei Browsern, Shell über den Anker")),
    # spontansteuern.py (plan spontanhilfe S2a): the admin moves the mouse and types, through the SparkHilfe program the
    # person starts herself; three consents (fresh code, her download, her „Erlauben“)
    "spontansteuern": Steckbrief(de="Steuern bei der Spontanhilfe", en="Control in spontaneous help", gruppe="sec",
        schalter=("spontansteuern",), anleitung="spontansteuern", parent="spontanhilfe",
        ohne_werkzeug=("ohne", "spontansteuern.py: Steuern bei der Spontanhilfe bedient nur der Admin im eigenen "
                               "Browser, nach drei Zustimmungen; das Modell bekommt kein Werkzeug und nie ein Bild"),
        modul=("spontansteuern", "fern", "Spontanhilfe Steuern: SparkHilfe (Windows, Mac notarisiert und neu "
                                         "gepackt, Linux X11), Einmal-Schlüssel, Bild, Eingaben")),
    # stage 2b: „Frag den Assistenten“ beside the terminal, the own language model only, no tool, admins only
    "fernzuganghilfe": Steckbrief(de="Assistent im Fernzugang", en="Assistant in remote access", gruppe="sec",
        schalter=("fernzugang_hilfe",), anleitung="fernzuganghilfe", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernzugang.py: der Assistent neben dem Terminal antwortet nur mit Text, jeder Befehl "
                               "wird ein Vorschlag zum Einfügen, Enter drückt der Mensch; kein Werkzeug, er tippt nie"),
        nur_spark=True),
    # fernbild.py (plan ssh-vermittlung stage 4): the screen of a paired system through guacd, admins only, first only watching
    "fernbild": Steckbrief(de="Bildschirm im Fernzugang", en="Screen in remote access", gruppe="sec",
        schalter=("fernbild",), anleitung="fernbild", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernbild.py: der Bildschirm eines Systems nur vom Admin im eigenen Browser, erst nur "
                               "ansehen; das Modell bekommt kein Werkzeug und nie ein Bild"),
        nur_spark=True,
        modul=("fernbild", "fern", "Fernzugang, Bildschirm: guacd auf 127.0.0.1, VNC oder RDP durch den Anker, erst "
                                   "nur ansehen, höchstens 15 Bilder/s")),
    "fernbildablage": Steckbrief(de="Zwischenablage beim Bildschirm", en="Clipboard with the screen", gruppe="sec",
        schalter=("fernbild_zwischenablage",), anleitung="fernbildablage", parent="fernbild",
        ohne_werkzeug=("ohne", "fernbild.py: die Zwischenablage nur während „Steuern“ des Admins, nach festen Regeln "
                               "im Panel; kein Werkzeug"),
        nur_spark=True),
    # fernnotiz.py (Dominik 2026-10-29 08:57): a note per paired system, sealed, admins only behind the page's unlock
    "fernnotizen": Steckbrief(de="Notizen im Fernzugang", en="Notes in remote access", gruppe="sec",
        schalter=("fernzugang_notizen",), anleitung="fernnotizen", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernnotiz.py: Notizen je System schreibt nur der Admin auf der entsperrten Seite; "
                               "das Modell liest sie nur als Daten mit „Assistent darf lesen“, kein Werkzeug"),
        nur_spark=True),
    # fernordner.py (Dominik 2026-10-29 09:18 „A“): the paired systems in folders, only an order, admins only
    "fernordner": Steckbrief(de="Ordner im Fernzugang", en="Folders in remote access", gruppe="sec",
        schalter=("fernzugang_ordner",), anleitung="fernordner", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernordner.py: Ordner ordnen nur die Liste der Systeme für den Admin auf der "
                               "entsperrten Seite; Rechte bleiben je System, das Modell sieht keine Ordner, kein "
                               "Werkzeug"),
        nur_spark=True,
        modul=("fernordner", "fern", "Fernzugang, Ordner: eine Ebene, Name und Symbol, Reihenfolge per Ziehen, nur "
                                     "Ordnung, Rechte je System")),
    # fernals.py (Dominik 2026-11-03 „1“): „Dateien“ as root or another user the server named (sudo spark-anker dateien als …),
    # or in folders a Windows server gave free; plus a switch per system with a fresh code; read only, writing its own step
    "fernals": Steckbrief(de="Dateien als anderer Benutzer", en="Files as another user", gruppe="sec",
        schalter=("fernals",), anleitung="fernals", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernals.py: Dateien als anderer Benutzer öffnet nur der Admin im eigenen Browser, "
                               "nach Freigabe am Server und Schalter je System; das Modell bekommt kein Werkzeug"),
        modul=("fernals", "fern", "Fernzugang, Dateien als anderer Benutzer: sudo nur für den sftp-server mit -R, "
                                  "Freigabe am Server und je System")),
    "ferngross": Steckbrief(de="Große Dateien im Fernzugang", en="Big files in remote access", gruppe="sec",
        schalter=("fernzugang_gross",), anleitung="ferngross", parent="fernzugang",
        ohne_werkzeug=("ohne", "ferngross.py: große Dateien in Teilen, per Link oder vom NAS nur vom Admin in seiner "
                               "Dateien-Sitzung, feste Befehle, Prüfsumme; kein Werkzeug"),
        nur_spark=True,
        modul=("ferngross", "fern", "Fernzugang, große Dateien: in Teilen mit SHA-256, per Link (curl) oder vom NAS, "
                                    "Prüfsumme vor dem Umbenennen")),
    # fernweb.py (Dominik 2026-10-30 „1a, 2a“): the web pages of a paired system through its anchor, own origin, admins only
    "fernweb": Steckbrief(de="Webdienste im Fernzugang", en="Web services in remote access", gruppe="sec",
        schalter=("fernweb",), anleitung="fernweb", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernweb.py: Webseiten eines gekoppelten Systems nur im Browser des Admins über die "
                               "eigene Tunnel-Tür, feste Ziel-Regeln; kein Werkzeug, das Modell sieht nichts davon"),
        nur_spark=True,
        modul=("fernweb", "fern", "Fernzugang, Webdienste: eigene Tunnel-Tür (Port 31090), Ziele nach festen Regeln, "
                                  "Cookies je Dienst getrennt")),
    # fernsshtermy.py (Dominik 2026-11-06 „alle empfehlungen umsetzten“): sshTermy reaches the paired systems through the
    # panel as a jump host (Vermittler-Protokoll v1), SSH end to end, the panel passes bytes only; admins only
    "fernsshtermy": Steckbrief(de="sshTermy als Jump-Host", en="sshTermy as jump host", gruppe="sec",
        schalter=("fernzugang_sshtermy",), anleitung="fernsshtermy", parent="fernzugang",
        ohne_werkzeug=("ohne", "fernsshtermy.py: sshTermy reicht über den Spark SSH Ende-zu-Ende durch, gekoppelt "
                               "und entsperrt nur vom Admin; das Modell sieht keine Bytes, kein Werkzeug"),
        nur_spark=True,
        modul=("fernsshtermy", "fern", "Fernzugang, sshTermy als Jump-Host: rohe Bytes zum sshd, ein Schlüssel je "
                                       "Gerät, je Schlüssel entsperrt")),
    # angriffsprobe.py: how often the real model would follow an order in outside text (numbers only, nothing runs)
    "angriffsprobe": Steckbrief(de="Angriffsprobe", en="Attack probe", gruppe="sec", schalter=("angriffsprobe",),
        anleitung="angriffsprobe", parent="werkstatt",
        ohne_werkzeug=("ohne", "angriffsprobe.py: Knopf auf der Werkstatt-Seite, misst das Sprachmodell, kein "
                               "Werkzeug"),
        nur_spark=True,
        modul=("angriffsprobe", "betrieb", "Angriffsprobe: wie oft das echte Sprachmodell Befehlen in fremdem Text "
                                           "folgen würde, nur Zahlen, kein Werkzeug läuft")),
    # nas.py (plan plaene/synology-bauplan.md): the places of a profile (NAS or cloud connected once), Ich → Speicher
    "nas": Steckbrief(de="Speicher und NAS", en="Storage and NAS", gruppe="data", schalter=("nas_on",),
        anleitung="nas", me="storebox",
        ohne_werkzeug=("ohne", "Speicherorte mit Anmeldung für Kopie und Sicherung, kein Werkzeug"),
        begleiter="panel",
        modul=("nas", "betrieb", "Speicher und NAS: Speicherorte (NAS, Cloud), eine Anmeldung pro Ort für Kopie und "
                                 "Sicherung")),
    # speicher.py: a copy of the profile's data at one of its places (WebDAV, SFTP, SMB) or a folder the admin mounted
    "speicher": Steckbrief(de="Kopie meiner Daten", en="Copy of my data", gruppe="data", schalter=("storage_own",),
        anleitung="speicher", parent="nas", me="storebox", ohne_werkzeug=("ohne", "läuft im Hintergrund"),
        modul=("speicher", "betrieb", "Kopie meiner Daten pro Profil an einem Speicherort, verschlüsselt")),
    # nasquelle.py (S2): folders at a place read into the profile's own document search, only reading
    "nasquelle": Steckbrief(de="Wissensordner", en="Knowledge folders", gruppe="data", schalter=("nas_sources",),
        anleitung="nasquelle", parent="nas", me="storebox",
        ohne_werkzeug=("ohne", "Wissensordner landen in der Dokumentensuche: document_search und Erst lokal finden "
                               "sie, kein eigenes Werkzeug"),
        modul=("nasquelle", "betrieb", "Wissensordner und Haushaltsordner: Ordner an einem Speicherort nur lesen und "
                                       "in die Dokumentensuche bringen")),
    # nasquelle.py (S5): an admin profile picks one folder at its place "für alle"; every profile finds what is in it
    "nashaushalt": Steckbrief(de="Haushaltsordner", en="Household folder", gruppe="data", schalter=("nas_shared",),
        anleitung="nashaushalt", parent="nasquelle", me="storebox",
        ohne_werkzeug=("ohne", "Haushaltsordner landen als geteilte Dokumente in der Suche: document_search und Erst "
                               "lokal finden sie, kein eigenes Werkzeug")),
    "speicherlan": Steckbrief(de="Speicher im Heimnetz", en="Storage in the home network", gruppe="data",
        schalter=("storage_lan",), anleitung="speicherlan", parent="speicher", me="storebox",
        ohne_werkzeug=("ohne", "Einstellung des Speichers")),
    "speicherordner": Steckbrief(de="Ordner auf dem Spark", en="Folder on the Spark", gruppe="data",
        schalter=("storage_folder",), anleitung="speicherordner", parent="speicher", me="storebox",
        ohne_werkzeug=("ohne", "Einstellung des Speichers")),
    "speicherauslagern": Steckbrief(de="Originale auslagern", en="Move originals out", gruppe="data",
        schalter=("storage_offload",), anleitung="speicherauslagern", parent="speicher", me="storebox",
        ohne_werkzeug=("ohne", "läuft im Hintergrund")),
    "dienstnutzer": Steckbrief(de="Hinweis, wenn ein Dienst fehlt", en="Note when a service is missing",
        gruppe="talk", schalter=("svc_watch_users",), anleitung="dienstnutzer", parent="dienstwacht", me="setbox",
        ohne_werkzeug=("regel", "dienstwacht.py: fester Satz, wenn der Dienst eines Werkzeugs fehlt")),
    # verlauf.py (plan plaene/verlauf-sync.md): the history on every device of the profile
    "verlaufsync": Steckbrief(de="Verlauf sofort abgleichen", en="Instant history sync", gruppe="talk",
        schalter=("history_live",), anleitung="verlaufsync", me="setbox",
        ohne_werkzeug=("ohne", "Abgleich im Hintergrund"), begleiter="talk"),
    "eingespraech": Steckbrief(de="Ein Gespräch für alle Kanäle", en="One conversation for all channels",
        gruppe="talk", schalter=("history_one",), anleitung="eingespraech", me="setbox",
        ohne_werkzeug=("ohne", "Abgleich im Hintergrund"), begleiter="talk"),
    "offlinelesen": Steckbrief(de="Verlauf offline lesen", en="Read history offline", gruppe="talk",
        schalter=("history_offline",), anleitung="offlinelesen", me="setbox",
        ohne_werkzeug=("ohne", "Abgleich im Hintergrund"), begleiter="talk"),
    # Einstellungs-Assistent (faelle.py, berater.py): problems become cases, cases proposals from a fixed catalog
    "berater": Steckbrief(de="Einstellungs-Assistent", en="Settings assistant", gruppe="talk", schalter=("berater",),
        anleitung="berater",
        ohne_werkzeug=("regel", "berater.py: „Was schlägt der Berater vor?“, „Wie werden die Antworten schneller?“"),
        begleiter="spark", modul=("berater", "betrieb", "Einstellungs-Assistent: Vorschläge aus Fällen")),
    "beratererklaeren": Steckbrief(de="Anfragen erklären", en="Explain requests", gruppe="talk",
        schalter=("berater_explain",), anleitung="beratererklaeren", parent="berater",
        ohne_werkzeug=("regel", "berater.py: „Warum hast du eben …?“")),
    "beraterchat": Steckbrief(de="Den Assistenten nach Vorschlägen fragen", en="Ask the assistant for proposals",
        gruppe="talk", schalter=("berater_chat",), anleitung="beraterchat", parent="berater", me="setbox",
        ohne_werkzeug=("regel", "berater.py: nach Vorschlägen fragen")),
    "beraterhinweis": Steckbrief(de="Hinweis bei neuem Vorschlag", en="Note on a new proposal", gruppe="talk",
        schalter=("berater_notify",), anleitung="beraterhinweis", pref="berater_note", parent="berater", me="setbox",
        ohne_werkzeug=("ohne", "meldet sich von selbst")),
    "beraterissue": Steckbrief(de="Fälle als Meldung vorbereiten", en="Prepare cases as reports", gruppe="talk",
        schalter=("berater_issue",), anleitung="beraterissue", parent="berater",
        ohne_werkzeug=("ohne", "nur in der Oberfläche")),
    "beraterauto": Steckbrief(de="Autopilot für kleine Änderungen", en="Autopilot for small changes", gruppe="talk",
        schalter=("berater_auto",), anleitung="beraterauto", parent="berater",
        ohne_werkzeug=("ohne", "Entscheidung des Admins")),
    "beraterideen": Steckbrief(de="Ideen außerhalb des Katalogs", en="Ideas outside the catalog", gruppe="talk",
        schalter=("berater_ideas",), anleitung="beraterideen", parent="berater",
        ohne_werkzeug=("ohne", "Entscheidung des Admins")),
    "beraterana": Steckbrief(de="Fall analysieren", en="Analyse a case", gruppe="talk",
        schalter=("berater_analyse",), anleitung="beraterana", parent="berater",
        ohne_werkzeug=("ohne", "nur in der Oberfläche")),
    "beraterundo": Steckbrief(de="Automatisch zurücknehmen", en="Undo automatically", gruppe="talk",
        schalter=("berater_auto_undo",), anleitung="beraterundo", parent="berater",
        ohne_werkzeug=("ohne", "Entscheidung des Admins")),
    "berateru": Steckbrief(de="Schritte für die Umgebung", en="Steps for the environment", gruppe="talk",
        schalter=("berater_env",), anleitung="berateru", parent="berater",
        ohne_werkzeug=("ohne", "nur in der Oberfläche")),
    "beratermich": Steckbrief(de="Vorschläge für mein Profil", en="Proposals for my profile", gruppe="talk",
        schalter=("berater_me",), anleitung="beratermich", parent="berater", me="setbox",
        ohne_werkzeug=("ohne", "nur in der Oberfläche")),
    "bewerten": Steckbrief(de="👍/👎 unter Antworten", en="👍/👎 under answers", gruppe="talk", schalter=("bewerten",),
        anleitung="bewerten", parent="berater", me="setbox",
        ohne_werkzeug=("regel", "faelle.py: „Das war falsch“, „Gut so“")),
    "beraterwarum": Steckbrief(de="„Warum?“ für alle Profile", en='"Why?" for every profile', gruppe="talk",
        schalter=("berater_why",), anleitung="beraterwarum", parent="berater", me="setbox",
        ohne_werkzeug=("regel", "berater.py: „Warum?“ für alle Profile")),
    "bewertenzurueck": Steckbrief(de="Rückmeldung, wenn es behoben ist", en="Feedback when it is fixed",
        gruppe="talk", schalter=("bewerten_back",), anleitung="bewertenzurueck", pref="rate_back", parent="bewerten",
        me="setbox", ohne_werkzeug=("ohne", "meldet sich von selbst")),
    "search": Steckbrief(de="Websuche", en="Web search", gruppe="talk", schalter=("search",), anleitung="search",
        werkzeuge={"web_search": ("Websuche", "Web search")}, knoten={"web_search": "web"},
        saetze={"web_search": ("Was gibt es Neues in den Nachrichten?", "What is new in the news?")},
        begleiter="talk"),
    "wiki": Steckbrief(de="Wikipedia direkt", en="Wikipedia straight away", gruppe="talk", schalter=("wiki",),
        anleitung="wiki", me="setbox",
        werkzeuge={"wikipedia": ("Wikipedia", "Wikipedia"), "article_more": ("Artikel weiterlesen", "Read on")},
        knoten={"wikipedia": "wiki", "article_more": "wiki"},
        saetze={"wikipedia": ("Schau in Wikipedia nach Albert Einstein", "Look up Albert Einstein in Wikipedia")},
        begleiter="talk", modul=("wiki", "wissen", "Wikipedia für „Was ist …?“")),
    "kiwix": Steckbrief(de="Eigenes Kiwix-Archiv", en="Own Kiwix archive", gruppe="talk", schalter=("kiwix",),
        anleitung="kiwix", me="setbox", werkzeuge={"archive_search": ("Eigenes Archiv", "Own archive")},
        auch=("article_more",), knoten={"archive_search": "kiwix"},
        saetze={"archive_search": ("Schau in meinem Archiv nach Sauerteig", "Look in my archive for sourdough")},
        begleiter="talk", modul=("kiwix", "wissen", "Eigenes Kiwix als Wissensquelle ohne Internet")),
    "hilfe": Steckbrief(de="Hilfe zum Spark", en="Help with the Spark", gruppe="talk", schalter=("spark_help",),
        anleitung="hilfe", me="setbox", werkzeuge={"spark_hilfe": ("Spark-Hilfe", "Spark help")},
        knoten={"spark_hilfe": "hilfe"},
        saetze={"spark_hilfe": ("Wie stelle ich die Websuche ein?", "How do I set up the web search?")},
        begleiter="talk", modul=("hilfe", "betrieb", "Spark-Hilfe und Index der Doku")),
    "hilfevorschlag": Steckbrief(de="Einstellungen vorschlagen", en="Suggesting settings", gruppe="talk",
        schalter=("spark_suggest",), anleitung="hilfevorschlag", parent="hilfe", me="setbox",
        werkzeuge={"spark_vorschlag": ("Spark-Vorschlag", "Spark suggestion")}, knoten={"spark_vorschlag": "hilfe"},
        saetze={"spark_vorschlag": ("Was empfiehlst du mir an Einstellungen?", "Which settings do you recommend?")}),
    "hilfeseite": Steckbrief(de="Frag Spark auf jeder Seite", en="Ask Spark on every page", gruppe="talk",
        schalter=("spark_drawer",), anleitung="hilfeseite", parent="hilfe", me="setbox", auch=("spark_hilfe",)),
    # tipps.py: the assistant points out a function that would help and helps setting it up
    "tipps": Steckbrief(de="Funktionen vorschlagen", en="Suggesting functions", gruppe="talk",
        schalter=("feature_tips",), anleitung="tipps", parent="hilfe", me="setbox", auch=("spark_hilfe",),
        modul=("tipps", "gespraech", "Schlägt passende Funktionen vor, die noch aus sind")),
    # saetze.py: functions that are on but never used, with a sentence to say (Ich → Was ich kann)
    "tippssaetze": Steckbrief(de="Das kannst du auch sagen", en="You can also say", gruppe="talk",
        schalter=("feature_sentences",), anleitung="tippssaetze", parent="tipps", me="kannbox",
        auch=("spark_hilfe",)),
    "memory": Steckbrief(de="Gedächtnis", en="Memory", gruppe="data", schalter=("memory",), anleitung="memory",
        me="factbox", werkzeuge={"memory_save": ("Merken", "Remember"), "memory_forget": ("Vergessen", "Forget")},
        knoten={"memory_save": "mem", "memory_forget": "mem"},
        saetze={"memory_save": ("Merk dir, dass ich Tee mag", "Remember that I like tea"), "memory_forget": ("Vergiss, dass ich Tee mag", "Forget that I like tea")},
        begleiter="link"),
    "history": Steckbrief(de="Frühere Gespräche", en="Past conversations", gruppe="data", schalter=("history",),
        anleitung="history", me="setbox",
        werkzeuge={"history_search": ("Frühere Gespräche", "Earlier conversations")},
        knoten={"history_search": "mem"},
        saetze={"history_search": ("Haben wir schon mal darüber gesprochen?", "Did we talk about this before?")},
        begleiter="panel"),
    "documents": Steckbrief(de="Eigene Dokumente", en="Own documents", gruppe="data", schalter=("documents",),
        anleitung="documents", me="docbox",
        werkzeuge={"document_search": ("Eigene Dokumente", "Own documents"), "document_list": ("Dokumentliste", "Document list")},
        knoten={"document_search": "mem", "document_list": "mem"},
        saetze={"document_search": ("Wann läuft meine Versicherung ab?", "When does my insurance end?"), "document_list": ("Welche Dokumente habe ich?", "Which documents do I have?")},
        begleiter_teile=("folder",),
        modul=("documents", "wissen", "Dokumente pro Profil in wissen.db: Text, Abschnitte mit Kontextzeile, Suche, Vektoren als float16")),
    "docshared": Steckbrief(de="Gemeinsame Dokumente", en="Shared documents", gruppe="data",
        schalter=("doc_shared",), anleitung="docshared", parent="documents", me="docbox", auch=("document_search",)),
    "remarkable": Steckbrief(de="reMarkable-Notizen", en="reMarkable notes", gruppe="data", schalter=("remarkable",),
        anleitung="remarkable", parent="docpics", me="rmbox",
        werkzeuge={"remarkable_library": ("reMarkable-Ablage", "reMarkable library")}, auch=("document_search",),
        knoten={"remarkable_library": "rm"}, eigenes_wort={"remarkable_library": "rmliste"},
        kurz=(("remarkable_library", "Was liegt auf meinem reMarkable?", "What is on my reMarkable?"),),
        modul=("remarkable", "dienste", "reMarkable-Notizbücher als Wissen")),
    "rmsend": Steckbrief(de="Aufs reMarkable schicken", en="Sending to the reMarkable", gruppe="data",
        schalter=("remarkable_send",), anleitung="rmsend", parent="remarkable", me="rmbox",
        werkzeuge={"remarkable_note": ("Notiz aufs reMarkable", "Note to the reMarkable"), "remarkable_sent": ("Aufs reMarkable Gelegtes", "Put on the reMarkable")},
        knoten={"remarkable_note": "rm", "remarkable_sent": "rm"},
        eigenes_wort={"remarkable_note": "remarkable", "remarkable_sent": "remarkable"}),
    "rmtodo": Steckbrief(de="Aufgaben vom reMarkable", en="Tasks from the reMarkable", gruppe="data",
        schalter=("remarkable_plus",), anleitung="rmplus", parent="rmsend", me="rmbox", auch=("remarkable_library",)),
    "rmweb": Steckbrief(de="Webseiten und Anhänge aufs reMarkable", en="Web pages and attachments to the reMarkable",
        gruppe="data", schalter=("remarkable_plus",), anleitung="rmplus", parent="rmsend", me="rmbox",
        werkzeuge={"remarkable_page": ("Webseite aufs reMarkable", "Web page to the reMarkable"), "remarkable_attachment": ("Mail-Anhang aufs reMarkable", "Mail attachment to the reMarkable")},
        knoten={"remarkable_page": "rm", "remarkable_attachment": "rm"},
        eigenes_wort={"remarkable_page": "remarkable", "remarkable_attachment": "remarkable"},
        kurz=(("remarkable_page", "Schick den Artikel aufs reMarkable", "Send the article to the reMarkable"),)),
    "rmaufgaben": Steckbrief(de="Aufgabenblatt zum Ankreuzen", en="Task sheet to tick", gruppe="data",
        schalter=("remarkable_tasks",), anleitung="rmaufgaben", parent="rmpapier", me="rmbox",
        werkzeuge={"remarkable_sheet": ("Blatt aufs reMarkable", "Sheet to the reMarkable")},
        knoten={"remarkable_sheet": "rm"}, eigenes_wort={"remarkable_sheet": "remarkable"},
        modul=("rmaufgaben", "dienste", "Aufgabenblatt zum Ankreuzen aufs reMarkable")),
    # Dokumente erstellen (docmake.py, plan dokumente-erstellen): letters, presentations, tables ... as files
    "erstellen": Steckbrief(de="Dokumente erstellen", en="Creating documents", gruppe="data", schalter=("doc_make",),
        anleitung="erstellen", parent="documents", me="docbox",
        werkzeuge={"document_plan": ("Dokument planen", "Plan document"), "document_change": ("Dokument ändern", "Change document"), "document_status": ("Dokument-Stand", "Document status"), "document_send": ("Dokument senden", "Send document")},
        knoten={"document_plan": "make", "document_change": "make", "document_status": "make", "document_send": "make"},
        saetze={"document_plan": ("Mach eine Präsentation über den Mauerfall", "Make a presentation about the fall of the Berlin Wall")}),
    "erstellenvorlagen": Steckbrief(de="Eigene Vorlagen", en="Own templates", gruppe="data",
        schalter=("doc_make_templates",), anleitung="erstellenvorlagen", parent="erstellen", me="docbox",
        auch=("document_plan",)),
    # pictures for slides from the own Kiwix (docmake.wiki_pictures; Präsentationen professionell, point 5)
    "erstellenbilder": Steckbrief(de="Bilder aus dem Kiwix", en="Pictures from the Kiwix", gruppe="data",
        schalter=("doc_make_wikipics",), anleitung="erstellenbilder", parent="erstellen", me="docbox",
        auch=("document_plan",)),
    # Bilder malen (bilder.py, bild_server.py, plan bildgenerierung): FLUX.2 [klein] on the Spark, installed by install.sh --bild
    "bilder": Steckbrief(de="Bilder malen", en="Painting pictures", gruppe="data", schalter=("bilder",),
        anleitung="bilder", me="bildbox", werkzeuge={"bild_malen": ("Bild malen", "Paint picture")},
        knoten={"bild_malen": "bild"},
        saetze={"bild_malen": ("Mal mir eine Katze auf einem Skateboard", "Paint me a cat on a skateboard")},
        begleiter="panel", modul=("bilder", "wissen", "Bilder malen: Wunsch prüfen, Auftrag, Ablage, Bildkarte")),
    # Musik machen (musik.py, musik_server.py, plan musik M1): ACE-Step 1.5 on the model computer, install.sh --musik
    "musik": Steckbrief(de="Musik machen", en="Making music", gruppe="data", schalter=("musik",), anleitung="musik",
        me="musikbox", werkzeuge={"musik_machen": ("Musik machen", "Make music")}, knoten={"musik_machen": "musik"},
        saetze={"musik_machen": ("Mach mir ein Lied über unsere Katze", "Make me a song about our cat")},
        begleiter="panel",
        modul=("musik", "wissen", "Musik machen: Wunsch prüfen, Modell wählen, Auftrag, Ablage, Liedkarte, Musik testen je Modell")),
    # Musik bearbeiten (musik.py, plan musik-experte, Stufe E1): an own song or an own file changed into a new version
    # (Abschnitt neu, Verlängern, Musikrichtung, Remix, Schneiden, Tempo und Tonart); the panel picks the song
    "musikbearbeiten": Steckbrief(de="Musik bearbeiten", en="Editing music", gruppe="data",
        schalter=("musik_bearbeiten",), anleitung="musikbearbeiten", parent="musik", me="musikbox",
        werkzeuge={"musik_bearbeiten": ("Musik bearbeiten", "Edit music")}, knoten={"musik_bearbeiten": "musik"},
        saetze={"musik_bearbeiten": ("Mach mein letztes Lied 30 Sekunden länger", "Make my last song 30 seconds longer")}),
    "docbrief": Steckbrief(de="Steckbrief und Tags", en="Document card and tags", gruppe="data",
        schalter=("doc_brief",), anleitung="docbrief", parent="documents", me="docbox", auch=("document_search",)),
    # Auswertungen je Dokument (auswertung.py, plan open-notebook Stufe 2): Kurzfassung and Kernaussagen by themselves in
    # quiet minutes, the rest per click; every point with its place, checked by the panel's fixed rules, never the model
    "auswertungen": Steckbrief(de="Auswertungen", en="Analyses", gruppe="data", schalter=("doc_auswertung",),
        anleitung="auswertungen", parent="documents", me="docbox",
        werkzeuge={"dokument_auswertung": ("Auswertung eines Dokuments", "Analysis of a document")},
        knoten={"dokument_auswertung": "mem"},
        saetze={"dokument_auswertung": ("Was sind die Kernaussagen im Mietvertrag?", "What are the key points of the lease?")}),
    # Aufnahmen abschreiben (abschrift.py, plan open-notebook Stufe 3a): recordings uploaded under Ich → Dokumente are
    # transcribed by the own speech recognition in quiet minutes, 30 s at a time; the transcript is outside text
    "docaudio": Steckbrief(de="Aufnahmen abschreiben", en="Transcribe recordings", gruppe="data",
        schalter=("doc_audio",), anleitung="docaudio", parent="documents", me="docbox", auch=("document_search",)),
    # Links als Dokument (doklink.py, plan open-notebook Stufe 4): public pages and files behind addresses the person
    # gives become documents (netguard.hole_oeffentlich, wissen.aufnehmen); "Neu abrufen" only on a click; outside text
    "doclink": Steckbrief(de="Links als Dokument", en="Links as documents", gruppe="data", schalter=("doc_link",),
        anleitung="doclink", parent="documents", me="docbox",
        werkzeuge={"link_als_dokument": ("Link als Dokument", "Link as document")}, auch=("document_search",),
        knoten={"link_als_dokument": "links"},
        saetze={"link_als_dokument": ("Speicher https://example.org/artikel als Dokument", "Save https://example.org/article as a document")}),
    # YouTube-Links abschreiben (ytquelle.py, plan open-notebook Stufe 3b): a YouTube link given through Links als
    # Dokument (so doc_link too) is fetched as its sound track by the pinned yt-dlp, only through the netguard proxy
    # (netproxy.py, fixed host list), and transcribed like a recording; without yt-dlp the link says how to install it
    "docyoutube": Steckbrief(de="YouTube-Links abschreiben", en="Transcribe YouTube links", gruppe="data",
        schalter=("doc_youtube", "doc_link"), anleitung="docyoutube", parent="docaudio", me="docbox",
        auch=("link_als_dokument", "document_search")),
    # Mappen (mappen.py, plan open-notebook Stufe 1, Dominik 2026-10-30 „1a 2a“): own documents, Wissensbuch pages and
    # notes bundled per undertaking, a context level per entry; a conversation bound to a Mappe gets its entries as data
    "mappen": Steckbrief(de="Mappen", en="Collections", gruppe="data", schalter=("mappen",), anleitung="mappen",
        parent="documents", me="mpbox",
        werkzeuge={"mappe_liste": ("Mappen auflisten", "List collections"), "mappe_stand": ("Mappe ansehen", "Show collection"), "mappe_dazu": ("In Mappe legen", "Put into collection")},
        knoten={"mappe_liste": "mem", "mappe_stand": "mem", "mappe_dazu": "mem"},
        saetze={"mappe_liste": ("Welche Mappen habe ich?", "Which collections do I have?"), "mappe_stand": ("Was liegt in der Mappe Urlaub?", "What is in the collection Holiday?"), "mappe_dazu": ("Leg den Mietvertrag in die Mappe Wohnung", "Put the lease into the collection Flat")},
        begleiter="set up, looked at and deleted on the panel's page Mappen and in the iPhone app; its tools and the Mappe filter of document_search and fund_suche work in Frag Spark like in every answer",
        modul=("mappen", "wissen", "Mappen: Dokumente, Seiten und Notizen bündeln, Kontext-Stufe je Eintrag (aus, kurz, ganz) nach festen Regeln")),
    # Hörstück aus einer Mappe (hoerstueck.py, plan open-notebook Stufe 5, Push 5a; Dominik: drei feste Stimmen, die der
    # Admin wählt): a talk of two or three voices about one Mappe, the model writes only a script, the panel checks every
    # line by fixed rules and the speech output reads it line by line in quiet minutes
    "hoerstueck": Steckbrief(de="Hörstück aus einer Mappe", en="Audio overview", gruppe="data",
        schalter=("hoerstueck",), anleitung="hoerstueck", parent="mappen", me="mpbox",
        werkzeuge={"hoerstueck_machen": ("Hörstück machen", "Make audio overview")},
        knoten={"hoerstueck_machen": "mem"},
        saetze={"hoerstueck_machen": ("Mach ein Hörstück aus der Mappe Wohnung", "Make an audio overview of the collection Flat")},
        begleiter="listened to in the panel, the iPhone app (native player) and Telegram; made, looked at and deleted on the panel's page Mappen; hoerstueck_machen works in Frag Spark like in every answer",
        modul=("hoerstueck", "wissen", "Hörstück aus einer Mappe: Drehbuch nur als JSON, jede Zeile fest geprüft, Zeile für Zeile gesprochen")),
    # Hörstück als Diskussion (hoerstueck_diskussion.py, plan open-notebook hoerstueck-diskussion, Dominik 2026-11-10
    # „als Schalter für Diskussion“): plan, chapters with contributions of several sentences, role cards and a fixed
    # measure per chapter; off, the Hörstück stays as before
    "hoerstueckdisk": Steckbrief(de="Hörstück als Diskussion", en="Audio overview as a discussion", gruppe="data",
        schalter=("hoerstueck_diskussion",), anleitung="hoerstueckdisk", parent="hoerstueck", me="mpbox",
        auch=("hoerstueck_machen",)),
    # Finden (fund.py, plan such-index, Stufe A): one index over the own data with fields and tags, the page Finden,
    # Strg K and the tool fund_suche; each source follows its own function (documents, NAS, reMarkable, Wissensbuch)
    "fund": Steckbrief(de="Finden in allen Daten", en="Find in all data", gruppe="data", schalter=("fund",),
        anleitung="fund", me="fundbox", werkzeuge={"fund_suche": ("In allen Daten finden", "Find in all data")},
        knoten={"fund_suche": "mem"},
        saetze={"fund_suche": ("Such meine Rechnung von Thomann", "Find my invoice from Thomann")},
        begleiter_teile=("find",),
        modul=("fund", "wissen", "Finden: Suchindex über die eigenen Daten, Felder und Schlagworte nach festen Regeln, Blind-Marken je Profil")),
    "proactive": Steckbrief(de="Von selbst melden", en="Speaking up by itself", gruppe="day",
        schalter=("proactive",), anleitung="proactive", pref="pro_on", me="probox",
        werkzeuge={"home_rules_list": ("Smart-Home-Regeln", "Smart home rules"), "home_rule_delete": ("Regel löschen", "Delete rule"), "proactive_pause": ("Meldungen pausieren", "Pause notes")},
        knoten={"home_rules_list": "ha", "home_rule_delete": "ha", "proactive_pause": "mem"},
        eigenes_wort={"home_rules_list": "hamelden", "home_rule_delete": "hamelden", "proactive_pause": "aendern"},
        kurz=(("proactive_pause", "Meld dich heute nicht mehr", "No more notes today"),), begleiter_teile=("notes",),
        modul=("proactive", "dienste", "Meldet sich von selbst, wenn etwas Echtes passiert")),
    "hacam": Steckbrief(de="Kamerabild beschreiben", en="Describe a camera picture", gruppe="day",
        schalter=("ha_camera", "homeassistant"), anleitung="hacam", pref="pro_ha_cam", parent="proactive",
        me="probox", werkzeuge={"camera_describe": ("Kamerabild", "Camera picture")},
        knoten={"camera_describe": "ha"},
        saetze={"camera_describe": ("Was sieht die Kamera an der Haustür?", "What does the camera at the front door see?")}),
    "reminders": Steckbrief(de="Timer und Erinnerungen", en="Timers and reminders", gruppe="day",
        schalter=("reminders",), anleitung="reminders",
        werkzeuge={"reminder_set": ("Erinnerung stellen", "Set reminder"), "reminder_list": ("Erinnerungen zeigen", "List reminders"), "reminder_cancel": ("Erinnerung löschen", "Cancel reminder")},
        knoten={"reminder_set": "mem", "reminder_list": "mem", "reminder_cancel": "mem"},
        saetze={"reminder_set": ("Erinnere mich in zehn Minuten an den Tee", "Remind me about the tea in ten minutes"), "reminder_list": ("Welche Erinnerungen habe ich?", "Which reminders do I have?"), "reminder_cancel": ("Lösch die Erinnerung zum Ofen", "Delete the reminder about the oven")},
        begleiter_teile=("capture", "notes")),
    # Alles Offene im Assistenten (vorgaenge.py, plan assistent-zentrale): cards with buttons in the conversation, Später,
    # the page Offen; a child row under Timer und Erinnerungen (the Funktionen page is near its height limit)
    "vorgaenge": Steckbrief(de="Alles Offene im Assistenten", en="Everything open in the assistant", gruppe="day",
        schalter=("vorgaenge",), anleitung="vorgaenge", parent="reminders", me="vgbox",
        werkzeuge={"offen_zeigen": ("Was offen ist", "What is open")}, knoten={"offen_zeigen": "cal"},
        eigenes_wort={"offen_zeigen": "vorgaenge"},
        kurz=(("offen_zeigen", "Was ist noch offen?", "What is still open?"),), begleiter_teile=("actions", "offen"),
        modul=("vorgaenge", "dienste", "Alles Offene im Assistenten: Karten mit Knöpfen, Später, Seite Offen, Ja-Knopf, Telegram-Knöpfe")),
    "tasks": Steckbrief(de="Listen für Einkauf und Aufgaben", en="Lists for shopping and tasks", gruppe="day",
        schalter=("tasks",), anleitung="tasks", me="taskbox",
        werkzeuge={"tasks_show": ("Liste zeigen", "Show list"), "tasks_add": ("Auf die Liste", "Add to list"), "tasks_change": ("Liste ändern", "Change list")},
        knoten={"tasks_show": "cal", "tasks_add": "cal", "tasks_change": "cal"},
        saetze={"tasks_show": ("Was steht auf der Einkaufsliste?", "What is on the shopping list?"), "tasks_add": ("Setz Milch auf die Einkaufsliste", "Put milk on the shopping list"), "tasks_change": ("Hak Milch ab", "Tick off milk")},
        begleiter_teile=("lists",),
        modul=("tasks", "dienste", "Listen für Einkauf und Aufgaben, wie Apple Erinnerungen: Farbe, Reihenfolge, Info je Eintrag, Erinnern zur Uhrzeit")),
    "agent": Steckbrief(de="Aufträge", en="Jobs", gruppe="day", schalter=("agent",), anleitung="agent",
        me="agentbox",
        werkzeuge={"agent_list": ("Agenten zeigen", "List agents"), "agent_task": ("Agent beauftragen", "Agent task"), "agent_schedule": ("Agent planen", "Schedule agent"), "routine_save": ("Ablauf speichern", "Save routine"), "agent_change": ("Auftrag ändern", "Change job")},
        knoten={"agent_list": "mem", "agent_task": "mem", "agent_schedule": "mem", "routine_save": "mem", "agent_change": "mem"},
        saetze={"agent_list": ("Was machen meine Agenten?", "What are my agents doing?"), "agent_schedule": ("Plane einen Agenten für jeden Montag", "Plan an agent for every Monday"), "agent_change": ("Pausiere den Agenten mit dem Wochenbericht", "Pause the agent with the weekly report")},
        begleiter="panel", modul=("agent", "dienste", "Aufträge im Hintergrund, Zeitpläne, Routinen")),
    # watches (beobachten.py): admin release only, every profile with agent functions, never guests
    "beobachten": Steckbrief(de="Beobachten", en="Watching", gruppe="day", schalter=("agent_watch",),
        anleitung="beobachten", parent="agent", me="agentbox",
        werkzeuge={"agent_watch": ("Beobachten anlegen", "Set up watching")}, auch=("agent_change",),
        knoten={"agent_watch": "mem"},
        saetze={"agent_watch": ("Beobachte den Preis der Bauknecht B6R 88", "Watch the price of the Bauknecht B6R 88")},
        modul=("beobachten", "dienste", "Beobachten: Funde prüfen, nur Neues melden (Eigene Aufgaben)")),
    # chats.py (plan plaene/messenger.md): chats between the people of this Spark, like a messenger; since V01.0.488
    # also what "Nachrichten an andere" did (plan plaene/nachrichten-in-chats.md): "Sag Anna …", "an alle", Durchsagen
    "chats": Steckbrief(de="Chats", en="Chats", gruppe="day", schalter=("chats",), anleitung="chats", me="setbox",
        werkzeuge={"message_send": ("Nachricht senden", "Send message"), "message_read": ("Nachrichten lesen", "Read messages")},
        knoten={"message_send": "mem", "message_read": "mem"},
        saetze={"message_send": ("Schick Anna eine Nachricht, dass ich später komme", "Send Anna a message that I will be late"), "message_read": ("Habe ich neue Nachrichten?", "Do I have new messages?")},
        begleiter="panel", modul=("chats", "geraete", "Chats zwischen den Profilen, verschlüsselt")),
    "messages_all": Steckbrief(de="Nachricht an alle", en="Message to everybody", gruppe="day",
        schalter=("messages_all",), anleitung="messages_all", pref="msg_all", parent="chats", me="setbox",
        auch=("message_send",)),
    "calendar": Steckbrief(de="Kalender", en="Calendar", gruppe="day", schalter=("calendar",), anleitung="calendar",
        me="calbox",
        werkzeuge={"calendar_events": ("Termine lesen", "Read appointments"), "calendar_add": ("Termin eintragen", "Add appointment"), "calendar_change": ("Termin ändern", "Change appointment"), "daily_briefing": ("Tagesüberblick", "Daily briefing")},
        knoten={"calendar_events": "cal", "calendar_add": "cal", "calendar_change": "cal", "daily_briefing": "cal"},
        saetze={"calendar_events": ("Welche Termine habe ich morgen?", "Which appointments do I have tomorrow?"), "calendar_add": ("Trag morgen um 10 einen Termin beim Zahnarzt ein", "Put a dentist appointment tomorrow at 10 in my calendar"), "calendar_change": ("Verschieb den Zahnarzttermin auf Freitag", "Move the dentist appointment to Friday"), "daily_briefing": ("Was hab ich heute vor?", "What am I up to today?")},
        begleiter_teile=("agenda", "capture")),
    "weather": Steckbrief(de="Wetter", en="Weather", gruppe="day", schalter=("weather",), anleitung="weather",
        me="wxbox", werkzeuge={"weather": ("Wetter", "Weather")}, knoten={"weather": "weather"},
        saetze={"weather": ("Wie wird das Wetter morgen?", "What will the weather be like tomorrow?")},
        begleiter="panel", modul=("weather", "dienste", "Wetter von Open-Meteo als feste Sätze")),
    # feeds.py (Dominik 2026-10-17, plan reddit/plan.md): own Reddit inbox, subreddits and other feeds, read only
    "feeds": Steckbrief(de="Reddit und Feeds", en="Reddit and feeds", gruppe="day", schalter=("feeds",),
        anleitung="feeds", me="feedbox", werkzeuge={"feeds_news": ("Reddit und Feeds", "Reddit and feeds")},
        knoten={"feeds_news": "feeds"},
        saetze={"feeds_news": ("Was gibt's Neues auf Reddit?", "What's new on Reddit?")}, begleiter="panel",
        modul=("feeds", "dienste", "Reddit und Feeds: eigener Reddit-Posteingang, Subreddits und RSS, nur lesen")),
    "mail": Steckbrief(de="E-Mail lesen", en="Reading e-mail", gruppe="post", schalter=("mail",), anleitung="mail",
        me="mailbox",
        werkzeuge={"mail_list": ("Mails auflisten", "List mails"), "mail_search": ("Mails suchen", "Search mails"), "mail_read": ("Mail lesen", "Read mail"), "mail_draft": ("Mail-Entwurf", "Mail draft")},
        knoten={"mail_list": "mail", "mail_search": "mail", "mail_read": "mail", "mail_draft": "mail"},
        saetze={"mail_list": ("Habe ich neue Mails?", "Do I have new mail?"), "mail_read": ("Lies mir die Mail von Anna vor", "Read me the mail from Anna")},
        begleiter_teile=("post",), modul=("mail", "post", "Mail lesen per IMAP")),
    "tidy": Steckbrief(de="Postfach aufräumen", en="Inbox tidying", gruppe="post", schalter=("mail_tidy",),
        anleitung="tidy", parent="mail", me="mailbox",
        werkzeuge={"mail_tidy_overview": ("Postfach-Überblick", "Mailbox overview"), "mail_tidy_propose": ("Postfach aufräumen", "Tidy mailbox")},
        knoten={"mail_tidy_overview": "mail", "mail_tidy_propose": "mail"},
        saetze={"mail_tidy_overview": ("Räum mein Postfach auf", "Tidy up my inbox")},
        modul=("tidy", "post", "Posteingang aufräumen")),
    "parcels": Steckbrief(de="Pakete", en="Parcels", gruppe="post", schalter=("parcels",), anleitung="parcels",
        parent="mail", me="mailbox", werkzeuge={"parcels": ("Pakete", "Parcels")}, knoten={"parcels": "parcels"},
        saetze={"parcels": ("Wann kommt meine Amazon-Bestellung?", "When does my Amazon order arrive?")},
        modul=("parcels", "dienste", "Pakete aus Versand-Mails")),
    # fuerdich.py (plan persoenlicher-assistent, Dominik 2026-10-18): bills, contracts, orders, offers, open replies and
    # phishing found in the own mails by fixed rules; tab „Für dich“ on the mail page
    "fuerdich": Steckbrief(de="Für dich aus Mails", en="For you from mail", gruppe="post",
        schalter=("mail_insight",), anleitung="fuerdich", parent="mail", me="mailbox",
        werkzeuge={"fuer_dich": ("Für dich", "For you"), "fuer_dich_tun": ("Für dich: erledigen", "For you: act")},
        knoten={"fuer_dich": "mail", "fuer_dich_tun": "mail"},
        saetze={"fuer_dich": ("Was muss ich diese Woche erledigen?", "What do I have to do this week?"), "fuer_dich_tun": ("Die Rechnung von Nummer zwei ist erledigt", "Number two is done")},
        modul=("fuerdich", "dienste", "Für dich: findet Rechnungen, Verträge, Bestellungen, Angebote, offene Antworten, Phishing; letzte Lesung versiegelt")),
    "schreib": Steckbrief(de="Schreibhilfe", en="Writing help", gruppe="post", schalter=("write_help",),
        anleitung="schreib", me="writebox", begleiter_teile=("write", "mail", "office"),
        ohne_werkzeug=("ohne", "das Modell formuliert selbst"),
        modul=("schreib", "gespraech", "Schreibhilfe: korrigieren, kürzen, übersetzen, entwerfen")),
    "contacts": Steckbrief(de="Kontakte", en="Contacts", gruppe="post", schalter=("contacts",), anleitung="contacts",
        me="conbox", werkzeuge={"contacts_search": ("Kontakte", "Contacts")}, knoten={"contacts_search": "contacts"},
        saetze={"contacts_search": ("Wie ist die Telefonnummer von Anna?", "What is Anna's phone number?")},
        begleiter="panel",
        modul=("contacts", "post", "Kontakte per CardDAV: Seite Kontakte wie Apple, ändern nur mit Schalter, zurück mit ETag")),
    "ha": Steckbrief(de="Home Assistant", en="Home Assistant", gruppe="home", schalter=("homeassistant",),
        anleitung="ha", me="habox",
        werkzeuge={"home_assistant": ("Smart Home", "Smart home"), "home_assistant_action": ("Geräte schalten", "Switch devices"), "home_assistant_states": ("Zustände lesen", "Read states"), "home_assistant_history": ("Verlauf", "History"), "home_assistant_todo": ("Home-Assistant-Listen", "Home Assistant lists")},
        knoten={"home_assistant": "ha", "home_assistant_action": "ha", "home_assistant_states": "ha", "home_assistant_history": "ha", "home_assistant_todo": "ha"},
        saetze={"home_assistant": ("Mach das Licht im Wohnzimmer aus", "Switch off the light in the living room"), "home_assistant_states": ("Ist die Haustür zu?", "Is the front door closed?"), "home_assistant_history": ("Wann ist die Waschmaschine fertig?", "When is the washing machine done?")},
        begleiter_teile=("home",)),
    "esp32": Steckbrief(de="Eigene Lautsprecher (ESP32)", en="Own speakers (ESP32)", gruppe="home",
        schalter=("esp32",), anleitung="esp32", me="espbox", werkzeuge={"speaker_volume": ("Lautstärke", "Volume")},
        knoten={"speaker_volume": "geraete"}, eigenes_wort={"speaker_volume": "aendern"},
        kurz=(("speaker_volume", "Mach leiser", "Quieter"),), begleiter="device",
        modul=("esp32", "geraete", "Eigene ESP32-Lautsprecher und ihre Firmware")),
    "messages_announce": Steckbrief(de="Durchsagen auf Lautsprechern", en="Announcements on speakers", gruppe="home",
        schalter=("messages_announce",), anleitung="messages_announce", parent="chats", me="setbox",
        werkzeuge={"message_announce": ("Durchsage", "Announcement")}, knoten={"message_announce": "mem"},
        saetze={"message_announce": ("Durchsage im Wohnzimmer: Essen ist fertig", "Announcement in the living room: dinner is ready")}),
    # the Spark calls (telefon_anruf.py, T4): wake-up calls and reminders the profile ordered, call backs; the
    # preference telefon_anrufbar lets each profile say no
    "telefonanrufen": Steckbrief(de="Telefon: der Spark ruft an", en="Phone: the Spark calls", gruppe="home",
        schalter=("telefon_anrufen", "telefon"), anleitung="telefonanrufen", pref="telefon_anrufbar",
        parent="telefon", me="telbox", werkzeuge={"anruf_planen": ("Anrufen lassen", "Have the Spark call")},
        knoten={"anruf_planen": "telefon"},
        saetze={"anruf_planen": ("Ruf mich morgen um sieben an", "Call me tomorrow at seven")}),
    "transit": Steckbrief(de="Bus und Bahn", en="Bus and train", gruppe="go", schalter=("transit",),
        anleitung="transit", me="trbox", werkzeuge={"transit": ("Bus und Bahn", "Transit")},
        knoten={"transit": "transit"},
        saetze={"transit": ("Wann fährt die nächste S-Bahn?", "When does the next S-Bahn leave?")},
        begleiter="panel", modul=("transit", "dienste", "Bus und Bahn")),
    "begleiter": Steckbrief(de="Spark-Begleiter am PC und Mac", en="Spark companion on PC and Mac", gruppe="go",
        schalter=("desk",), anleitung="begleiter", me="deskbox",
        werkzeuge={"pc_action": ("Rechner-Aktion", "Computer action"), "pc_send": ("An den Rechner", "Send to computer")},
        knoten={"pc_action": "desk", "pc_send": "desk"},
        eigenes_wort={"pc_action": "begleiter", "pc_send": "begleiter"},
        begleiter_teile=("ask", "dictate", "notes", "status", "notaus", "files", "screen", "context", "actions", "act", "wake", "speak", "inbox", "quiet", "meeting", "daily", "view"),
        modul=("begleiter", "geraete", "Spark-Begleiter für Windows und Mac")),
    "begleitertun": Steckbrief(de="Begleiter darf am PC handeln", en="Companion may act on the PC", gruppe="go",
        schalter=("desk_act",), anleitung="begleitertun", parent="begleiter", me="deskbox", auch=("pc_action",)),
    # Stufe 3 (bedienen.py): the Spark operates the own computer step by step, every step confirmed there
    "begleiterbedienen": Steckbrief(de="Spark bedient den Rechner", en="Spark operates the computer", gruppe="go",
        schalter=("desk_operate",), anleitung="begleiterbedienen", parent="begleiter", me="deskbox",
        werkzeuge={"pc_look": ("Bildschirm ansehen", "Look at the screen")}, knoten={"pc_look": "desk"},
        eigenes_wort={"pc_look": "begleiter"}),
    "iphone": Steckbrief(de="iPhone-App", en="iPhone app", gruppe="go", schalter=("iphone",), anleitung="iphone",
        me="appbox", werkzeuge={"iphone_action": ("iPhone-Aktion", "iPhone action")},
        knoten={"iphone_action": "push"}, saetze={"iphone_action": ("Ruf Mama an", "Call Mum")}, begleiter="device",
        modul=("iphone", "geraete", "iPhone-App: Kopplung und Rechte")),
    # codeauftrag.py (package 3b): an admin types a code order in the panel's or the app's chat; OpenCode works on it once
    # as spark-dev on its own branch, the card shows the change; installing stays the admin's step with a fresh code
    "entwickelnauftrag": Steckbrief(de="Code-Auftrag im Chat", en="Code order in the chat", gruppe="sec",
        schalter=("entwickeln_auftrag",), anleitung="entwickelnauftrag", parent="entwickeln",
        werkzeuge={"code_auftrag": ("Code-Auftrag", "Code order")}, knoten={"code_auftrag": "mem"},
        eigenes_wort={"code_auftrag": "codeauftrag"},
        saetze={"code_auftrag": ("Code-Auftrag: im Wetter soll die Windrichtung stehen", "Code order: show the wind direction in the weather")},
        nur_spark=True),
    # nasablage.py (S4): spark_ablage at a place in the home network; made documents and, after "Ja", own things go
    # into Erstellt/, files put into Eingang/ come into Dokumente; the only folder the Spark writes to
    "nasablage": Steckbrief(de="Ablage-Ordner", en="Filing folder", gruppe="data", schalter=("nas_drop",),
        anleitung="nasablage", parent="nas", me="storebox",
        werkzeuge={"nas_ablegen": ("Auf der NAS ablegen", "Save to the NAS")}, knoten={"nas_ablegen": "nasablage"},
        eigenes_wort={"nas_ablegen": "nasablage"},
        modul=("nasablage", "betrieb", "Ablage-Ordner: spark_ablage im Heimnetz, der einzige Ordner, in den der Spark schreibt; Eingang wird zu Dokumenten")),
    # naszustand.py (S6): the main admin lets the Spark read how the NAS is doing (SNMPv3); only admin profiles ask
    "naszustand": Steckbrief(de="Zustand der NAS", en="NAS status", gruppe="data", schalter=("nas_status",),
        anleitung="naszustand", parent="nas", werkzeuge={"nas_zustand": ("Zustand der NAS", "NAS status")},
        knoten={"nas_zustand": "naszustand"}, eigenes_wort={"nas_zustand": "naszustand"},
        kurz=(("nas_zustand", "Ist die Synology voll?", "Is the Synology full?"),),
        modul=("naszustand", "betrieb", "Zustand der NAS: Volumes, Pools, USB-Platten, RAID, Festplatten und Temperatur über SNMPv3 (nur lesen, nur Admin)")),
    "tagebuch": Steckbrief(de="Spark-Tagebuch", en="Spark diary", gruppe="talk", schalter=("tagebuch",),
        anleitung="tagebuch", me="setbox", werkzeuge={"spark_tagebuch": ("Spark-Tagebuch", "Spark diary")},
        knoten={"spark_tagebuch": "mem"},
        saetze={"spark_tagebuch": ("Was hast du heute für mich gemacht?", "What did you do for me today?")},
        begleiter="talk", modul=("tagebuch", "wissen", "Spark-Tagebuch: was der Spark selbst getan hat")),
    # Zustand per Sprache (zustand_wz.py, plan werkzeug-abdeckung Paket 4): „Läuft alles?“, „Wann wurde gesichert?“
    "sparkzustand": Steckbrief(de="Zustand per Sprache", en="Status by voice", gruppe="talk",
        schalter=("status_voice",), anleitung="sparkzustand",
        werkzeuge={"spark_zustand": ("Spark-Zustand", "Spark status")}, knoten={"spark_zustand": "mem"},
        eigenes_wort={"spark_zustand": "zustand_wz"},
        saetze={"spark_zustand": ("Wann wurde zuletzt gesichert?", "When was the last backup?")}, begleiter="talk"),
    # Ändern per Sprache (aendern.py, plan werkzeug-abdeckung Paket 6): „Mach das rückgängig“ nach dem Ja
    "rueckgaengig": Steckbrief(de="Rückgängig per Sprache", en="Undo by voice", gruppe="talk",
        schalter=("undo_voice",), anleitung="rueckgaengig", werkzeuge={"undo_last": ("Rückgängig", "Undo")},
        knoten={"undo_last": "mem"}, eigenes_wort={"undo_last": "aendern"},
        kurz=(("undo_last", "Mach das rückgängig", "Undo that"),), begleiter="talk"),
}


def feature(key):
    """The arguments of features.Feature for this function (features.FEATURES keeps its own order)."""
    s = STECKBRIEFE[key]
    return {"key": key, "de": s.de, "en": s.en, "group": s.gruppe, "admin": s.schalter, "pref": s.pref,
            "parent": s.parent, "me": s.me, "guide": s.anleitung}


def werkzeug_namen():
    return {tool: names for s in STECKBRIEFE.values() for tool, names in s.werkzeuge.items()}


def live_werkzeuge():
    return {tool: s.knoten.get(tool) or s.live[0] for s in STECKBRIEFE.values() for tool in s.werkzeuge
            if s.knoten.get(tool) or s.live}


def live_knoten():
    return {s.live[0]: s.live[1:5] for s in STECKBRIEFE.values() if s.live}


def live_rueckgabe():
    return {s.live[0]: s.live[5] for s in STECKBRIEFE.values() if s.live}


def log_woerter(area):
    return [s.log[1] for s in STECKBRIEFE.values() if s.log and s.log[0] == area]


def abdeckung():
    return {key: tuple(s.werkzeuge) + s.auch for key, s in STECKBRIEFE.items() if s.werkzeuge or s.auch}


def ohne_werkzeug(art):
    """werkzeug_abdeckung.RULES (art "regel": fixed rules instead of a tool) or WITHOUT (art "ohne")."""
    return {key: s.ohne_werkzeug[1] for key, s in STECKBRIEFE.items() if s.ohne_werkzeug[:1] == (art,)}


def nur_spark():
    return {key for key, s in STECKBRIEFE.items() if s.nur_spark}


def nur_eigenes_wort():
    return {tool: mod for s in STECKBRIEFE.values() for tool, mod in s.eigenes_wort.items()}


def spickzettel():
    return tuple(k for s in STECKBRIEFE.values() for k in s.kurz)


def saetze():
    return {tool: pair for s in STECKBRIEFE.values() for tool, pair in s.saetze.items()}


def desk():
    return {key: s.begleiter_teile for key, s in STECKBRIEFE.items() if s.begleiter_teile}


def begleiter():
    return {key: s.begleiter for key, s in STECKBRIEFE.items() if s.begleiter}


def module():
    return {s.modul[0]: s.modul[1:] for s in STECKBRIEFE.values() if s.modul}
