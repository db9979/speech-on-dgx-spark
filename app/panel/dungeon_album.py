"""KI-Dungeon-Master: Monster-Album (D&D idea 12, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; own code, the sayings „sage“ of the foes come from the thread „DnDAppFiles für den Dungeon-Master“).

Every hero keeps an album of the foes its group defeated (h["album"] = {foe id: wins}, kept with the hero like its bag, fix).
The more often, the more the album knows (STUFEN): after the first win name, picture, text and the foe's saying, after
the third its values (level, life, armour, attack, damage), after the fifth what hurts it more or less and the states its
blows cause. Only the panel counts (win, at the panel's own „besiegt“); nothing comes from the model.

Its page „Personen“ (NSC-Katalog, Dominik 2026-10-26 „auch in das begegnungs / monster album buch der spieler mit
aufnehemen“): every person of the people catalog (dungeon_personen) the hero's table met counts one meeting per round
(met, at the round's end when the catalog collects; h["personen"] = {catalog id: meetings}). The more often, the more the
page knows (PERSONEN_STUFEN): after the first meeting name, face, looks and world, after the second occupation and manner,
after the fourth the traits and how the person stands towards this hero. Never its wish, secret, role or goal (those
stay with the admin and the host), never a person whose words do not fit the round's tone. Only while the people catalog
is allowed for the host too.

Off by default: the admin's switch dungeonalbum (features.py, chat.dungeon_album) for the round's host.
Journal: fixed words and numbers („dungeon: album | …“), Live only counts.
"""
import re

import dungeon_buch as heldenbuch
import features
from common import DayCounter

KEY = "dungeonalbum"
STUFEN = (1, 3, 5)         # wins for the album's three stages of knowing
ALBUM_MAX = 400            # foes an album keeps (the catalog has about 270)
SIEGE_MAX = 10 ** 6

PERSONEN_STUFEN = (1, 2, 4)   # meetings for the people page's three stages
PERSONEN_MAX = 300         # people an album keeps (the catalog keeps 300)
_ID = re.compile(r"^[a-z0-9_]{1,40}$")

_day = DayCounter(eintraege=0, aufgestiegen=0, personen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def stage(n):
    """The album's stage for n wins: 0 none, 1 to len(STUFEN)."""
    return sum(1 for s in STUFEN if n >= s)


def win(dm, rd, gid):
    """A foe of this kind is defeated: one more win in the album of every hero of the fight that is still at the table."""
    if not on(rd) or not gid:
        return
    pids = set((rd.get("kampf") or {}).get("helden") or [])
    for pid, p in dm.seated(rd):
        if pid not in pids:
            continue
        a = p["held"].setdefault("album", {})
        if gid not in a and len(a) >= ALBUM_MAX:
            continue
        n = min(SIEGE_MAX, a.get(gid, 0) + 1)
        if stage(n) > stage(n - 1):
            _day.bump("eintraege" if n == 1 else "aufgestiegen")
            print(f"dungeon: album | stufe {stage(n)}", flush=True)
        a[gid] = n
        heldenbuch.notiere(rd, p, "kampf", gid)   # the hero's chronicle (dungeon_buch, never raises)


def view(dm, r, rd, h, lang):
    """The own hero's album for the table, most wins first: per stage only what the album knows; None while off."""
    if not h or not on(rd):
        return None
    import dungeon_dingbild as db
    import dungeon_kampf as kampf
    li = 1 if lang == "en" else 0
    cat = dm._by(r, "gegner")
    have = db.files() if db.on() else frozenset()
    out = []
    for gid, n in sorted((h.get("album") or {}).items(), key=lambda x: -x[1]):
        c = cat.get(gid)
        if not c or not stage(n):
            continue
        e = {"id": gid, "name": c["name"][li], "zeichen": c.get("zeichen", ""), "siege": n, "stufe": stage(n), "info": c["info"][li],
             "sage": (c.get("sage") or ["", ""])[li], "bild": kampf._picture(r, rd, gid, have),
             "naechste": next((s for s in STUFEN if s > n), 0)}
        if stage(n) >= 2:
            e.update(werte={"stufe": c["stufe"], "leben": c["leben"], "rk": c["ruestung"], "angriff": c["angriff"],
                            "schaden": f"{c.get('anzahl_wuerfel', 1)}{'d' if li else 'W'}{c['schaden']}"})
        if stage(n) >= 3:
            e.update({x: [kampf.ART_NAME[a][li] for a in c.get(x) or [] if a in kampf.ART_NAME] for x in ("resistenz", "immun", "schwaeche")},
                     zustaende=[z["name"][li] for z in r.get("zustaende") or [] if z["id"] in (c.get("zustaende") or [])])
        out.append(e)
    return out


def people_on(rd):
    import dungeon_personen as personen
    return on(rd) and personen.on(rd)


def people_stage(n):
    """The people page's stage for n meetings: 0 none, 1 to len(PERSONEN_STUFEN)."""
    return sum(1 for s in PERSONEN_STUFEN if n >= s)


def met(dm, rd, cid):
    """From dungeon_personen.collect at the round's end: the catalog's person cid was met by this table, one more meeting
    in the album of every living hero at the table."""
    if not people_on(rd) or not _ID.match(str(cid or "")):
        return
    for _, p in dm.seated(rd):
        h = p["held"]
        if h.get("tot"):
            continue
        a = h.setdefault("personen", {})
        if cid not in a and len(a) >= PERSONEN_MAX:
            continue
        n = min(SIEGE_MAX, a.get(cid, 0) + 1)
        if people_stage(n) > people_stage(n - 1):
            _day.bump("personen")
            print(f"dungeon: album | person stufe {people_stage(n)}", flush=True)
        a[cid] = n
        heldenbuch.notiere(rd, p, "person", cid)   # the hero's chronicle (dungeon_buch, never raises)


def people(dm, r, rd, h, lang):
    """The own hero's page „Personen“, most met first: per stage only what the page knows; None while off."""
    if not h or not people_on(rd):
        return None
    import dungeon_dingbild as db
    import dungeon_nsc as nsc
    import dungeon_personen as personen
    li = 1 if lang == "en" else 0
    d = personen.load()
    welten = {w["id"]: w["name"][li] for w in r.get("welten") or []}
    out = []
    for cid, n in sorted((h.get("personen") or {}).items(), key=lambda x: (-x[1], x[0])):
        x = d.get(cid)
        if not x or not people_stage(n) or dm.bad_words(r, rd, personen._text(r, x)):
            continue
        k = x.get("karte") or {}
        feld = lambda f: (k.get(f) or ["", ""])[li]   # noqa: E731
        e = {"id": cid, "name": x["name"], "treffen": n, "stufe": people_stage(n), "welt": welten.get(x.get("welt"), ""),
             "aussehen": feld("aussehen"), "bild": db.person_pic(r, x) or (x.get("gesicht") or {}).get("n") or "",   # as on the rules page
             "zeichen": "👤",
             "naechste": next((s for s in PERSONEN_STUFEN if s > n), 0)}
        if people_stage(n) >= 2:
            e.update(beruf=feld("beruf"), art=feld("art"))
        if people_stage(n) >= 3:
            e["wesen"] = nsc.trait_words(x, li)
            v = (x.get("haltung") or {}).get(h.get("name", "").lower())
            if isinstance(v, int) and not isinstance(v, bool):
                e["haltung"] = nsc.word(v, li)
        out.append(e)
    return out


def knows_face(name, heroes):
    """dungeon_gesicht.may_see: a person's face for a seat whose round has a hero that met the person (the page shows it)."""
    ids = {cid for h in heroes for cid in (h.get("personen") or {})}
    if not ids:
        return False
    import dungeon_personen as personen
    return any((x.get("gesicht") or {}).get("n") == name for cid, x in personen.load().items() if cid in ids)


def fix(r, h):
    """A hero read from a file: its album only with the catalog's foes and whole numbers of wins, at most ALBUM_MAX; its
    people page only with ids of the catalog's form and whole numbers of meetings, at most PERSONEN_MAX."""
    ids = {g["id"] for g in r.get("gegner") or []}
    ok = lambda n: isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= SIEGE_MAX   # noqa: E731
    a = h.get("album")
    h["album"] = dict(list((k, n) for k, n in a.items() if k in ids and ok(n))[:ALBUM_MAX]) if isinstance(a, dict) else {}
    p = h.get("personen")
    h["personen"] = dict(list((k, n) for k, n in p.items() if _ID.match(str(k)) and ok(n))[:PERSONEN_MAX]) if isinstance(p, dict) else {}


def for_live():
    """Numbers only: new album entries and stages reached today, people stages reached today."""
    t = _day.counts()
    return {k: t[k] for k in ("eintraege", "aufgestiegen", "personen")}
