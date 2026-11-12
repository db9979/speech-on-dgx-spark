"""Steckbrief pro Funktion (Kritische Prüfung 2026-11-12 point 4, plan /mnt/project-files/steckbrief/plan.md): one place per
function for everything the mandatory list (guideline part 1) used to spread over many files. The lists that need a
part of it read it from here; nothing is written twice (rule 12, test_steckbrief checks that no old table still names it).

Read by (each takes only its own part, the order of its own table stays):
  features.FEATURES          feature(key)        name de/en, group, admin switches, guide
  werkzeuge.NAMES            werkzeug_namen()    the readable name of each tool
  live.TOOLS / TARGETS / RETURNS                 the Live node of each tool, the node itself, what it gives back
  logfilter.AREAS            log_woerter(area)   the first word of the function's journal lines
  werkzeug_abdeckung.TOOLS / BY_WORD             the tools of the function, offered only on the person's own word
  spickzettel.KURZ           spickzettel()       an example sentence for a tool offered only on the own word
  technik.MODULE             module()            group and German line of the function's module
  features.DESK_SKIP         begleiter()         why the Begleiter has no part of its own

The bottom layer (test_schichten.GRUND): imports no panel module. Only data, no behaviour.
Pilot „Rechnen“; every other function moves here group by group (test_steckbrief.OHNE_ALT only shrinks).
"""
from typing import NamedTuple


class Steckbrief(NamedTuple):
    de: str                     # the function's name everywhere
    en: str
    gruppe: str                 # features.GROUPS
    schalter: tuple             # chat.* admin switches
    anleitung: str              # guides.js id
    werkzeuge: dict             # tool -> (de, en)
    live: tuple                 # (node, label, detail, kind, own_service, returns)
    log: tuple                  # (logfilter area, first word of the lines)
    nur_eigenes_wort: tuple     # (module, (tool, example de, example en)) or (): tool offered only on the person's word
    modul: tuple                # (module, technik group, German line)
    begleiter: str              # why the Begleiter has no part of its own: features.DESK_SKIP kind (talk, voice, spark, link, device)


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
}


def feature(key):
    """The arguments of features.Feature for this function (features.FEATURES keeps its own order)."""
    s = STECKBRIEFE[key]
    return {"key": key, "de": s.de, "en": s.en, "group": s.gruppe, "admin": s.schalter, "guide": s.anleitung}


def werkzeug_namen():
    return {tool: names for s in STECKBRIEFE.values() for tool, names in s.werkzeuge.items()}


def live_werkzeuge():
    return {tool: s.live[0] for s in STECKBRIEFE.values() for tool in s.werkzeuge}


def live_knoten():
    return {s.live[0]: s.live[1:5] for s in STECKBRIEFE.values()}


def live_rueckgabe():
    return {s.live[0]: s.live[5] for s in STECKBRIEFE.values()}


def log_woerter(area):
    return [s.log[1] for s in STECKBRIEFE.values() if s.log[0] == area]


def abdeckung():
    return {key: tuple(s.werkzeuge) for key, s in STECKBRIEFE.items()}


def nur_eigenes_wort():
    return {s.nur_eigenes_wort[1][0]: s.nur_eigenes_wort[0] for s in STECKBRIEFE.values() if s.nur_eigenes_wort}


def spickzettel():
    return tuple(s.nur_eigenes_wort[1] for s in STECKBRIEFE.values() if s.nur_eigenes_wort)


def begleiter():
    return {key: s.begleiter for key, s in STECKBRIEFE.items()}


def module():
    return {s.modul[0]: s.modul[1:] for s in STECKBRIEFE.values()}
