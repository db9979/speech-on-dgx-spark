"""KI-Dungeon-Master: Monster-Album (D&D idea 12, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; own code, the sayings „sage“ of the foes come from the thread „DnDAppFiles für den Dungeon-Master“).

Every hero keeps an album of the foes its group defeated (h["album"] = {foe id: wins}, kept with the hero like its bag, fix).
The more often, the more the album knows (STUFEN): after the first win name, picture, text and the foe's saying, after
the third its values (level, life, armour, attack, damage), after the fifth what hurts it more or less and the states its
blows cause. Only the panel counts (win, at the panel's own „besiegt“); nothing comes from the model.

Off by default: the admin's switch dungeonalbum (features.py, chat.dungeon_album) for the round's host.
Journal: fixed words and numbers („dungeon: album | …“), Live only counts.
"""
import features
from common import DayCounter

KEY = "dungeonalbum"
STUFEN = (1, 3, 5)         # wins for the album's three stages of knowing
ALBUM_MAX = 400            # foes an album keeps (the catalog has about 270)
SIEGE_MAX = 10 ** 6

_day = DayCounter(eintraege=0, aufgestiegen=0)


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


def fix(r, h):
    """A hero read from a file: its album only with the catalog's foes and whole numbers of wins, at most ALBUM_MAX."""
    ids = {g["id"] for g in r.get("gegner") or []}
    a = h.get("album")
    h["album"] = dict(list((k, n) for k, n in a.items() if k in ids and isinstance(n, int) and not isinstance(n, bool)
                           and 1 <= n <= SIEGE_MAX)[:ALBUM_MAX]) if isinstance(a, dict) else {}


def for_live():
    """Numbers only: new album entries and stages reached today."""
    t = _day.counts()
    return {k: t[k] for k in ("eintraege", "aufgestiegen")}
