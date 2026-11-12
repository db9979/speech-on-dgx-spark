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
    werkzeuge: dict = {}        # tool -> (de, en)
    ohne_werkzeug: tuple = ()   # (regel|ohne, why) when it has no tool: werkzeug_abdeckung.RULES / WITHOUT
    live: tuple = ()            # (node, label, detail, kind, own_service, returns)
    log: tuple = ()             # (logfilter area, first word of the lines)
    nur_eigenes_wort: tuple = ()  # (module, (tool, example de, example en)): tool offered only on the person's word
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
        nur_eigenes_wort=("rechnen", ("rechnen", "Rechne 19 Prozent von 249 Euro aus", "Calculate 19 percent of 249 euros")),
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
}


def feature(key):
    """The arguments of features.Feature for this function (features.FEATURES keeps its own order)."""
    s = STECKBRIEFE[key]
    return {"key": key, "de": s.de, "en": s.en, "group": s.gruppe, "admin": s.schalter, "pref": s.pref,
            "parent": s.parent, "me": s.me, "guide": s.anleitung}


def werkzeug_namen():
    return {tool: names for s in STECKBRIEFE.values() for tool, names in s.werkzeuge.items()}


def live_werkzeuge():
    return {tool: s.live[0] for s in STECKBRIEFE.values() for tool in s.werkzeuge}


def live_knoten():
    return {s.live[0]: s.live[1:5] for s in STECKBRIEFE.values() if s.live}


def live_rueckgabe():
    return {s.live[0]: s.live[5] for s in STECKBRIEFE.values() if s.live}


def log_woerter(area):
    return [s.log[1] for s in STECKBRIEFE.values() if s.log and s.log[0] == area]


def abdeckung():
    return {key: tuple(s.werkzeuge) for key, s in STECKBRIEFE.items() if s.werkzeuge}


def ohne_werkzeug(art):
    """werkzeug_abdeckung.RULES (art "regel": fixed rules instead of a tool) or WITHOUT (art "ohne")."""
    return {key: s.ohne_werkzeug[1] for key, s in STECKBRIEFE.items() if s.ohne_werkzeug[:1] == (art,)}


def nur_spark():
    return {key for key, s in STECKBRIEFE.items() if s.nur_spark}


def nur_eigenes_wort():
    return {s.nur_eigenes_wort[1][0]: s.nur_eigenes_wort[0] for s in STECKBRIEFE.values() if s.nur_eigenes_wort}


def spickzettel():
    return tuple(s.nur_eigenes_wort[1] for s in STECKBRIEFE.values() if s.nur_eigenes_wort)


def begleiter():
    return {key: s.begleiter for key, s in STECKBRIEFE.items() if s.begleiter}


def module():
    return {s.modul[0]: s.modul[1:] for s in STECKBRIEFE.values() if s.modul}
