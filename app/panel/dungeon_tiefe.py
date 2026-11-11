"""KI-Dungeon-Master: Regeltiefe, the one table of which game part hangs on which switch (plan „Spark ausdünnen“,
Punkt 1, Dominik 2026-11-11 „Ok“ to the plan „Dungeon-Schalter: 58 auf 8“).

Before, every part of the game had its own admin switch (58 in all, with many half combinations nobody played). Now:
- KERN: on with the KI-Dungeon-Master itself (story progress, lines and X-card, asking back, people, writings …);
- VOLL: the extra rules (crits, rest, travel, scars, factions, gold, runes …), on in a round with the Regeltiefe
  „voll“; the admin sets the standard (chat.dungeon_tiefe), the host chooses per round when making it and in the
  Spielleiter-Pult (rd["tiefe"]);
- PULT: the host's tools in the Spielleiter-Pult (give things, stages, random rules, oracle, real dice), without a
  switch: they only act when the host uses them;
- the rest hangs on one of six own switches (SCHALTER: pictures, the model's second check, guests, books, own
  stories, benches), each a function in features.py.
Every module asks an(teil, rd) for its round (or fuer/admin_an without one) and never features.allowed with a part.
„Nur Narben“ is no switch any more but a choice of the round (rd["nur_narben"]).

The old switches (chat.dungeon_krit …) are read once at the start (uebernehmen): the Regeltiefe becomes „voll“ when at
least half of the VOLL parts were on (Entscheidung 2a), a new switch is on when one of its old ones was (never the
pictures by themselves); then the old
keys leave the stored config. The journal only counts („dungeon: regeltiefe | uebernommen | voll | n“).
"""
import json

import features

EINFACH, VOLL = "einfach", "voll"
TIEFEN = {EINFACH: ("Einfach", "Simple"), VOLL: ("Voll", "Full")}
STANDARD = "dungeon_tiefe"      # the admin's standard for new rounds and rounds without a choice (chat.dungeon_tiefe)

KERN = ("dungeonfortschritt", "dungeongrenzen", "dungeonrueckfrage", "dungeonerzfehler", "dungeonanleiten", "dungeonnsc",
        "dungeonpersonen", "dungeonschrift", "dungeonquest", "dungeontageszeit")
VOLL_TEILE = ("dungeonkrit", "dungeonehrungen", "dungeonknapp", "dungeonhelfen", "dungeonrast", "dungeonreise",
              "dungeonsprachen", "dungeonkalender", "dungeonzeugen", "dungeongedanken", "dungeonmitkommen",
              "dungeonauftraege", "dungeonwandern", "dungeongesten", "dungeonumgebung", "dungeongefaehrte",
              "dungeonwunsch", "dungeonalarm", "dungeonfluestern", "dungeonhaltung", "dungeonnarben", "dungeonheldenmut",
              "dungeonfraktionen", "dungeongold", "dungeonrunen", "dungeonregler")
PULT = ("dungeongeben", "dungeonstufen", "dungeonzufall", "dungeonorakel", "dungeonechtwuerfel")
# the six own switches (features.py) and the parts on each
SCHALTER = {"dungeonbilder": ("dungeonbilder", "dungeongesicht", "dungeonwappen", "dungeonalbum", "dungeonheldenlied"),
            "dungeonpruefung": ("dungeonrichter", "dungeonschreiber", "dungeonkommentar"),
            "dungeongast": ("dungeongast",),
            "dungeonbuecher": ("dungeonchronik", "dungeonbuch"),
            "dungeongeschichten": ("dungeongeschichten", "dungeonimport"),
            "dungeonpruefstand": ("dungeonpruefstand", "dungeonerzaehlstand")}
GRUPPE = {**dict.fromkeys(KERN, "kern"), **dict.fromkeys(VOLL_TEILE, VOLL), **dict.fromkeys(PULT, "pult"),
          **{t: sw for sw, ts in SCHALTER.items() for t in ts}}

# the old switches as they stood in the config until V01.1.371, only to take them over once (uebernehmen)
ALT = {"dungeonkrit": "dungeon_krit", "dungeonehrungen": "dungeon_ehrungen", "dungeonknapp": "dungeon_knapp",
       "dungeonhelfen": "dungeon_helfen", "dungeonrast": "dungeon_rast", "dungeonreise": "dungeon_reise",
       "dungeonsprachen": "dungeon_sprachen", "dungeonkalender": "dungeon_kalender", "dungeonzeugen": "dungeon_zeugen",
       "dungeongedanken": "dungeon_gedanken", "dungeonmitkommen": "dungeon_mitkommen",
       "dungeonauftraege": "dungeon_auftraege", "dungeonwandern": "dungeon_wandern", "dungeongesten": "dungeon_gesten",
       "dungeonumgebung": "dungeon_umgebung", "dungeongefaehrte": "dungeon_gefaehrte", "dungeonwunsch": "dungeon_wunsch",
       "dungeonalarm": "dungeon_alarm", "dungeonfluestern": "dungeon_fluestern", "dungeonhaltung": "dungeon_haltung",
       "dungeonnarben": "dungeon_narben", "dungeonheldenmut": "dungeon_heldenmut",
       "dungeonfraktionen": "dungeon_fraktionen", "dungeongold": "dungeon_gold", "dungeonrunen": "dungeon_runen",
       "dungeonregler": "dungeon_regler", "dungeonfortschritt": "dungeon_fortschritt", "dungeongrenzen": "dungeon_grenzen",
       "dungeonrueckfrage": "dungeon_rueckfrage", "dungeonerzfehler": "dungeon_erzfehler",
       "dungeonanleiten": "dungeon_anleiten", "dungeonnsc": "dungeon_nsc", "dungeonpersonen": "dungeon_personen",
       "dungeonschrift": "dungeon_schrift", "dungeonquest": "dungeon_quest", "dungeontageszeit": "dungeon_tageszeit",
       "dungeongeben": "dungeon_geben", "dungeonstufen": "dungeon_stufen", "dungeonzufall": "dungeon_zufall",
       "dungeonorakel": "dungeon_orakel", "dungeonechtwuerfel": "dungeon_echtwuerfel",
       "dungeongesicht": "dungeon_gesicht", "dungeonwappen": "dungeon_wappen", "dungeonalbum": "dungeon_album",
       "dungeonheldenlied": "dungeon_heldenlied", "dungeonrichter": "dungeon_richter",
       "dungeonschreiber": "dungeon_schreiber", "dungeonkommentar": "dungeon_kommentar",
       "dungeonchronik": "dungeon_chronik", "dungeonbuch": "dungeon_buch", "dungeonimport": "dungeon_import",
       "dungeonerzaehlstand": "dungeon_erzaehlstand", "dungeonnarbennur": "dungeon_narben_nur"}


def gueltig(v):
    """A Regeltiefe the panel knows (a string of TIEFEN), never anything else from a request or the config."""
    return isinstance(v, str) and v in TIEFEN


def standard(c=None):
    """The admin's Regeltiefe for new rounds (Funktionen → KI-Dungeon-Master → Regeltiefe), einfach unless set."""
    v = (features.chat_cfg() if c is None else c).get(STANDARD)
    return v if gueltig(v) else EINFACH


def tiefe(rd):
    """The round's Regeltiefe: the host's choice, else the admin's standard (rounds from before keep the standard)."""
    v = rd.get("tiefe")
    return v if gueltig(v) else standard()


def neu(rd, v):
    """A new round: the host's choice in the form stays with the round when it differs from the admin's standard;
    otherwise the round follows the standard, also when the admin changes it later."""
    if gueltig(v) and v != standard():
        rd["tiefe"] = v


def choose(rd, v):
    """The host's choice for the round (making it, Spielleiter-Pult); ValueError for anything else."""
    if not gueltig(v):
        raise ValueError()
    rd["tiefe"] = v


def nur_narben(rd):
    """„Nur Narben“ for this round: every wound keeps to its look, never a consequence (the host's choice)."""
    return rd.get("nur_narben") is True


def schalter(teil):
    """The switch (features.py) the part hangs on: the game itself for KERN, VOLL and PULT, else its own."""
    g = GRUPPE[teil]
    return "dungeon" if g in ("kern", "pult", VOLL) else g


def an(teil, rd):
    """The part works in this round: its switch allowed for the round's host, a VOLL part only at Regeltiefe voll."""
    owner = rd.get("owner")
    if not owner or not features.allowed(schalter(teil), owner):
        return False
    return GRUPPE[teil] != VOLL or tiefe(rd) == VOLL


def fuer(teil, uid):
    """The part may work for this profile's rounds (pages without a round: the catalog, the books): a VOLL part as
    soon as the game is allowed, since every host may choose voll."""
    return bool(uid) and features.allowed(schalter(teil), uid)


def admin_an(teil, c=None):
    """The Spark allows the part at all (night jobs, the rules page, the admin's catalog)."""
    return features.admin_on(schalter(teil), c)


def fehlt(teil, uid, lang="de"):
    """Why the part does not work for this profile, as a sentence with its way (features.missing_text)."""
    return features.missing_text(schalter(teil), uid, lang)


def view(rd, host, li):
    """The round's Regeltiefe for the table; the host gets the choice and „Nur Narben“ (Spielleiter-Pult)."""
    out = {"wert": tiefe(rd), "name": TIEFEN[tiefe(rd)][li]}
    if host:
        out.update(wahl=[[k, v[li]] for k, v in TIEFEN.items()], nur_narben=nur_narben(rd))
    return out


def counts(runden):
    """Live: open rounds per Regeltiefe, only numbers."""
    rs = [v for v in runden if v.get("status") != "ende"]
    return {"einfach": sum(1 for v in rs if tiefe(v) == EINFACH), "voll": sum(1 for v in rs if tiefe(v) == VOLL),
            "nur_narben": sum(1 for v in rs if nur_narben(v))}


def uebernehmen(path=None):
    """Once at the start: the old switches of the stored config become the Regeltiefe and the new switches, then they
    go. Returns the number of old keys taken over (0: nothing to do)."""
    from common import CONFIG_PATH, write_json
    path = path or CONFIG_PATH
    try:
        with open(path) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return 0
    ch = cfg.get("chat") if isinstance(cfg, dict) else None
    if not isinstance(ch, dict):
        return 0
    old = {t: ch[k] is True for t, k in ALT.items() if k in ch}
    if not old:
        return 0
    if sum(1 for t in VOLL_TEILE if old.get(t)) * 2 >= len(VOLL_TEILE):
        ch[STANDARD] = VOLL
    else:
        ch.setdefault(STANDARD, EINFACH)
    for sw, ts in SCHALTER.items():   # never the pictures: painting needs the picture model and the admin's yes
        if sw != "dungeonbilder" and any(old.get(t) for t in ts if t != sw):
            ch[features.BY_KEY[sw].admin[0]] = True
    for k in ALT.values():
        ch.pop(k, None)
    write_json(path, cfg, indent=2, mode=0o640)
    print(f"dungeon: regeltiefe | uebernommen | {ch[STANDARD]} | {len(old)}", flush=True)
    return len(old)


def _check():
    """The table is complete: every part in exactly one group (test_dungeon_tiefe looks at the modules)."""
    teile = list(KERN) + list(VOLL_TEILE) + list(PULT) + [t for ts in SCHALTER.values() for t in ts]
    assert len(teile) == len(set(teile)), "a part in two groups"
    assert all(sw in features.BY_KEY for sw in SCHALTER), "a switch missing in features.py"


_check()
