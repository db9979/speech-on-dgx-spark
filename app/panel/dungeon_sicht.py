"""KI-Dungeon-Master: Sichtfilter (Tabletop-Punkt 3 of 2026-10-25, Dominik „ich hätte gerne alle punkte umgesetzt“,
idea from loreweaver, MIT, own code).

Every secret of a round is named once in GEHEIM with who may see it: the host („gastgeber“), another seat at the table
(„spieler“, a guest the same; the TV and the app show a seat's view), the car („auto“: what dungeon_auto reads aloud)
and the language model („modell“: dungeon.facts and dungeon.system_text). sicht(doc, betrachter) is the last step of
the table's view (dungeon.view): whatever the view built, a seat that is not the host never gets the host's keys
(NUR_GASTGEBER) nor a foe's life as numbers. The self-test test_every_secret_stays_with_its_viewers plants a marker in
each secret and looks for it in what each viewer gets (docs): it must stand exactly where GEHEIM allows it.
A new secret of the game comes into GEHEIM in the same commit as the secret itself.
"""
import json

BETRACHTER = ("gastgeber", "spieler", "auto", "modell")
NUR_GASTGEBER = ("plan", "wahrheit", "dinge", "regler", "mail_vorschau", "bild_grund")


def _foe(rd, m):
    import dungeon
    import dungeon_kampf
    g = dungeon_kampf.lineup([(dungeon.rules()["gegner"][0], 1)], 0, 1)
    g[0].update(leben=m, max=m + 1)
    rd["kampf"] = {"gegner": g, "seit": rd.get("zug", 0), "budget": 100, "gefahr": "mittel", "leben0": 10,
                   "helden": [k for k, p in rd["plaetze"].items() if p.get("held")]}


def _seat(rd, key, val):
    p = next(p for p in rd["plaetze"].values() if p.get("uid") == rd["owner"])
    p[key] = val


def _offen(rd, m):
    pid = next(k for k, p in rd["plaetze"].items() if p.get("uid") == rd["owner"])
    rd["offen"][pid] = {"text": m, "t": 0}


def _ooc(rd, m):
    pid = next(k for k, p in rd["plaetze"].items() if p.get("uid") == rd["owner"])
    rd["log"].append({"art": "ooc", "pid": pid, "text": m, "n": rd.get("zug", 0)})


def _tisch(rd, m):
    pid = next(k for k, p in rd["plaetze"].items() if p.get("uid") == rd["owner"])
    rd.setdefault("tisch", []).append({"n": 1, "pid": pid, "name": "Arvid", "text": m, "t": 0})


# id: (what, who may see it, how the self-test plants a marker in a round)
GEHEIM = {
    "wahrheit": (("Die verborgene Wahrheit der Runde", "The round's hidden truth"), {"gastgeber", "modell"},
                 lambda rd, m: rd.update(wahrheit={"kern": m})),
    "plan": (("Ziel und Akte der Geschichte", "The story's goal and acts"), {"gastgeber", "modell"},
             lambda rd, m: rd.update(plan={"titel": "Plan", "ziel": m, "gegner": "", "orte": [], "tabus": [], "idee": "",
                                           "akte": [{"titel": "Eins", "inhalt": "Anfang", "wende": "", "zuege": 3}]}, akt=0, akt_zug=1)),
    "dinge": (("Die festen Merkmale der Dinge", "The things' fixed features"), {"gastgeber", "modell"},
              lambda rd, m: rd.update(dinge=[{"name": "Truhe", "merkmale": m, "ort": "", "zug": rd.get("zug", 0)}])),
    "gegner_leben": (("Das Leben eines Gegners als Zahl", "A foe's life as a number"), {"gastgeber", "modell"}, _foe),
    "aktion_offen": (("Die Aktion eines anderen Platzes, bevor der Zug zu ist", "Another seat's action before the turn closes"),
                     {"gastgeber", "modell"}, _offen),
    "ooc": (("Eine Frage an den Spielleiter außerhalb des Spiels", "A question to the game master outside the game"),
            {"gastgeber"}, _ooc),
    "tisch": (("Das Tischgespräch", "The table talk"), {"gastgeber", "spieler"}, _tisch),
    "platz_schluessel": (("Der Schlüssel eines Platzes (nur als Hash)", "A seat's key (only as a hash)"), set(),
                         lambda rd, m: _seat(rd, "h", m)),
    "geraet": (("Das Gerät eines Platzes (nur als Hash)", "A seat's device (only as a hash)"), set(),
               lambda rd, m: _seat(rd, "geraet", m)),
}


def sicht(doc, betrachter):
    """The table's view for one viewer: the host gets it as it is; every other seat gets None for whatever NUR_GASTGEBER
    holds (an empty value stays as it is) and no numbers of a foe's life (dungeon_kampf.view gives them the state as a
    word)."""
    if betrachter == "gastgeber":
        return doc
    out = {k: None if k in NUR_GASTGEBER and v else v for k, v in doc.items()}
    k = out.get("kampf")
    if isinstance(k, dict) and k.get("gegner"):
        out["kampf"] = dict(k, gegner=[{x: y for x, y in g.items() if x not in ("leben", "max")} for g in k["gegner"]])
    return out


def docs(dm, rid, host, guest):
    """What each viewer gets of a round, as one text each (for the leak self-test): the view of the host's and of a
    guest's seat, what the car reads for the guest, and the model's data and rules."""
    import dungeon_auto
    r = dm.rules()
    rd = dm._read()["runden"][rid]
    li = 1 if rd.get("lang") == "en" else 0
    auto = [dungeon_auto.stand(rd, li, host=False) or [], dungeon_auto.summary(r, rd, guest, li, 0)]
    return {"gastgeber": json.dumps(dm.view(rid, host), ensure_ascii=False),
            "spieler": json.dumps(dm.view(rid, guest), ensure_ascii=False),
            "auto": json.dumps(auto, ensure_ascii=False),
            "modell": dm.facts(r, rd) + dm.system_text(r, rd, "erzaehlen")}
