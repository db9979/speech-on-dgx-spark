"""KI-Dungeon-Master: Heldenbuch aufs reMarkable (plan /mnt/project-files/remarkable-dungeon/plan.md, Dominik 2026-10-27
„Nach Empfehlung umsetzen, aber auch gerne in Farbe … und guck auch, dass es für das Layout für das reMarkable Pro Move
auch passt“, „Farbe oder Graustufen“ as a choice of the device).

One book per hero of a profile, a PDF in the page format of the profile's reMarkable (rmpapier.MODELS: rm2, Paper Pro,
Paper Pro Move), style „Altes Grimoire“: a frame, the hero's arms, tabs on the right (on the narrow Move a bar at the
bottom) that jump to the parts, bookmarks for the device's contents. Parts:
  Inhalt        the parts with their pages and „Neu seit der letzten Ausgabe“ (from the fingerprint of the last one)
  I Heldenbogen values, life, armour, gold, load, the six scores, what it wears, abilities, bag, protection, scars
  II Chronik    the hero's own chronicle h["chronik"] (notiere): evenings, chapters, fights, people met, levels; the
                fellow heroes only with name, people and class (what everybody saw at the table)
  III Personen  the album's page „Personen“ (dungeon_album.people): only what the hero's meetings unlocked, never wish,
                secret, role or goal; „x von y“
  IV Bestiarium the Monster-Album (dungeon_album.view) by its stages 1/3/5, „x von y Arten“
  V Dinge       what it wears and carries, each with its fixed lines
Pictures only the panel's own (portrait, faces, bestiary and item pictures from dungeon.BILD_DIR), opened again with
Pillow under a pixel bound and scaled to the device's pixels: 16 grey steps dithered (Floyd–Steinberg) on the rm2 and
in „Graustufen“, colour on Paper Pro and Move; without a picture a drawn symbol. Colour is never the only sign: the
rarity is written, a stage is filled dots, the life bar has its numbers.
Three layouts (LAYOUT): rm2 and Paper Pro two columns where it fits, the Move one column with relatively larger type,
tables broken into lines, the hero's sheet over several pages; every text is measured and cut to its box, a box that
does not fit goes to the next page (Buch.overflow records anything drawn outside the page's area, the self test
checks it is empty for every model).
A second document „Notizen – <Held>“ (lined pages with tabs) goes once and is never replaced: handwriting in the book
stays in its old edition (remarkable.place makes a new one, the old goes to „Archiv“), notes belong there.

When: automatically after a round's end or a chapter's end (runde_ende, kapitel_ende from dungeon.py: the hero is
queued, BUENDEL_S later in a quiet minute, at most AUTO_TAG automatic books per hero and day, so an evening with several
chapters gives one upload; unchanged since the last edition: nothing goes), and on „Jetzt schicken“ (Dungeon-Master →
Helden) or „Schick mein Heldenbuch aufs reMarkable“ (rmplus.SHEETS „heldenbuch“). Uploads count in the reMarkable's
daily limits (remarkable.AUTO_DAY, SEND_DAY); data leave the Spark only on the reMarkable's own way.

The chronicle h["chronik"]: at most CHRONIK_MAX entries of fixed kinds (ARTEN) with catalog ids, whole numbers and the
names of fellow heroes (NAME); never a text of the model. Written only while this function is allowed for the hero's
profile (notiere), checked whenever a hero is read (pruefe, from dungeon.fix_hero). A failure here never stops a turn.

Off by default: the admin's switch chat.dungeon_buch (features „dungeonbuch“, below the Dungeon-Master) and „Aufs
reMarkable schicken“ (features.READY); guests and seats without a profile (Figur-Code, guest account) never.
Journal: „dungeon: buch | …“ with fixed words and numbers; Live only counts.

    users/<id>/dungeon-buch.json   {"warte": {hid: due}, "buecher": {hid: {fp, ausgabe, t, z, tag, n}}, "notizen": {hid: t}}

    GET  /api/profile/dungeon/buch                 the profile's books: state per hero, model, colour
    GET  /api/profile/dungeon/buch/{hid}.pdf       the book as a PDF (preview, made on the Spark)
    POST /api/profile/dungeon/buch/{hid}/senden    „Jetzt schicken“: the book (and the notes once) onto the reMarkable
"""
import asyncio
import hashlib
import io
import json
import math
import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import features
import guard
import profiles
from common import DayCounter, read_json, write_json
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "dungeonbuch"
DATEI = "dungeon-buch.json"
ARTEN = ("kampf", "person", "abend", "kapitel")   # the kinds of a chronicle entry
CHRONIK_MAX = 300          # entries a hero's chronicle keeps (the oldest go first)
MIT_MAX = 4                # fellow heroes of an evening
NAME = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' \-]{0,23}")   # a hero's name as the table showed it
_ID = re.compile(r"[a-z0-9_]{1,40}")
_HID = re.compile(r"h[0-9a-f]{10}")
_BILD = re.compile(r"[A-Za-z0-9_\-]{1,80}")
ZAHL_MAX = 10 ** 6
T_MIN = 1_500_000_000      # a time in a chronicle entry: after 2017, before T_MAX
T_MAX = 4_000_000_000
BUENDEL_S = 30 * 60        # after a round's end the book waits this long: the next chapter of the evening joins it
AUTO_TAG = 1               # automatic books per hero and day (the button is not counted here)
BILDER_MAX = 60            # pictures in one book
BILD_PIXEL = 16_000_000    # a picture with more pixels is left out (Pillow's bound before decoding)
BILD_BYTES = 12 * 1024 * 1024
GRUPPE_MAX = 14            # events shown per chapter of the chronicle (the rest as a count)
LISTE_MAX = 120            # foes / people shown
NEU_MAX = 6                # lines of „Neu seit der letzten Ausgabe“
BODY = 256

_day = DayCounter(gesendet=0, unveraendert=0, abgelehnt=0, fehler=0, vorschau=0, notizen=0)
_last = {"s": 0.0}


def on(uid):
    """The book for this profile: its switch (with the Dungeon-Master) and „Aufs reMarkable schicken“; never a guest."""
    return bool(uid) and features.allowed(KEY, uid) and features.allowed("rmsend", uid)


def connected(uid):
    import remarkable
    return bool(remarkable.load(uid).get("token"))


# ---------------------------------------------------------------- the chronicle (h["chronik"])
def _int(x, lo=0, hi=ZAHL_MAX):
    return isinstance(x, int) and not isinstance(x, bool) and lo <= x <= hi


def _mit(rd, pid, dm):
    """The fellow heroes of a seat: name, people and class ids, nothing else."""
    out = []
    for p2, q in dm.seated(rd):
        h = q.get("held") or {}
        if p2 == pid or not NAME.fullmatch(str(h.get("name") or "")):
            continue
        out.append({"name": h["name"], "volk": str(h.get("volk") or "")[:40], "klasse": str(h.get("klasse") or "")[:40]})
    return out[:MIT_MAX]


def notiere(rd, p, art, cid="", now=None, dm=None, pid=""):
    """One entry into the chronicle of a seat's hero (a profile's own hero only, and only while the book is allowed
    for that profile). kampf/person: cid a catalog id (a second win of the same foe in the same chapter counts up);
    abend/kapitel: the chapter's number, the hero's level, the world and the fellow heroes. Never raises."""
    try:
        uid = p.get("uid") if isinstance(p, dict) else None
        h = p.get("held") if uid else None
        if not h or art not in ARTEN or not on(uid):
            return False
        now = int(time.time() if now is None else now)
        k = rd.get("kapitel", 1) if _int(rd.get("kapitel"), 1) else 1
        ch = h.get("chronik") if isinstance(h.get("chronik"), list) else []
        if art in ("kampf", "person"):
            if not _ID.fullmatch(str(cid or "")):
                return False
            last = ch[-1] if ch else None
            if last and last.get("a") == art and last.get("id") == cid and last.get("k") == k and now - last.get("t", 0) < 6 * 3600:
                last["n"] = min(ZAHL_MAX, last.get("n", 1) + 1)
            else:
                ch.append({"a": art, "t": now, "k": k, "id": cid, "n": 1})
        else:
            e = {"a": art, "t": now, "k": k, "s": h.get("stufe", 1) if _int(h.get("stufe"), 1, 100) else 1}
            if _ID.fullmatch(str(rd.get("welt") or "")):
                e["w"] = rd["welt"]
            if dm is not None:
                e["mit"] = _mit(rd, pid, dm)
            ch.append(e)
        h["chronik"] = ch[-CHRONIK_MAX:]
        return True
    except Exception as e:
        print(f"dungeon: buch | fehler | notiere {type(e).__name__}", flush=True)
        return False


def pruefe(h):
    """dungeon.fix_hero: the chronicle only as a list of entries of the fixed kinds with catalog ids, whole numbers and
    fellow heroes' names, at most CHRONIK_MAX; anything else goes."""
    ch = h.get("chronik")
    out = []
    for e in ch if isinstance(ch, list) else []:
        if not isinstance(e, dict) or e.get("a") not in ARTEN or not _int(e.get("t"), T_MIN, T_MAX) or not _int(e.get("k"), 1, 10000):
            continue
        x = {"a": e["a"], "t": e["t"], "k": e["k"]}
        if e["a"] in ("kampf", "person"):
            if not _ID.fullmatch(str(e.get("id") or "")) or not _int(e.get("n"), 1):
                continue
            x.update(id=e["id"], n=e["n"])
        else:
            x["s"] = e["s"] if _int(e.get("s"), 1, 100) else 1
            if _ID.fullmatch(str(e.get("w") or "")):
                x["w"] = e["w"]
            mit = e.get("mit")
            if isinstance(mit, list):
                x["mit"] = [{"name": m["name"], "volk": m["volk"], "klasse": m["klasse"]} for m in mit[:MIT_MAX]
                            if isinstance(m, dict) and NAME.fullmatch(str(m.get("name") or ""))
                            and _ID.fullmatch(str(m.get("volk") or "")) and _ID.fullmatch(str(m.get("klasse") or ""))]
        out.append(x)
    if out or "chronik" in h:
        h["chronik"] = out[-CHRONIK_MAX:]
    return h


def runde_ende(dm, rd, now=None):
    """dungeon._end: every seated profile hero gets its evening in the chronicle and its book is queued. Never raises."""
    try:
        n = 0
        for pid, p in dm.seated(rd):
            if notiere(rd, p, "abend", now=now, dm=dm, pid=pid):
                anstossen(p["uid"], p["held"]["hid"], now)
                n += 1
        if n:
            print(f"dungeon: buch | chronik | abend | {n} helden", flush=True)
    except Exception as e:
        print(f"dungeon: buch | fehler | runde {type(e).__name__}", flush=True)


def kapitel_ende(dm, rd, now=None):
    """dungeon.end_chapter (where the log says „kapitel_ende“): the chapter in every seated profile hero's chronicle,
    the hero kept again (its file was written at the round's end), its book queued. Never raises."""
    try:
        n = 0
        for pid, p in dm.seated(rd):
            if notiere(rd, p, "kapitel", now=now, dm=dm, pid=pid):
                dm.keep_seat(p)
                anstossen(p["uid"], p["held"]["hid"], now)
                n += 1
        if n:
            print(f"dungeon: buch | chronik | kapitel | {n} helden", flush=True)
    except Exception as e:
        print(f"dungeon: buch | fehler | kapitel {type(e).__name__}", flush=True)


# ---------------------------------------------------------------- the profile's state
def _file(uid):
    return profiles._path(uid, DATEI)


def _state(uid):
    d = read_json(_file(uid), {})
    for k in ("warte", "buecher", "notizen"):
        d[k] = {h: v for h, v in (d.get(k) or {}).items() if _HID.fullmatch(str(h))} if isinstance(d.get(k), dict) else {}
    return d


def _save(uid, d):
    write_json(_file(uid), {k: d.get(k) or {} for k in ("warte", "buecher", "notizen")}, mode=0o600)


def anstossen(uid, hid, now=None):
    """The hero's book is due BUENDEL_S after the last end of the evening (a later end moves it on)."""
    if not on(uid) or not _HID.fullmatch(str(hid)):
        return
    d = _state(uid)
    d["warte"][hid] = int((time.time() if now is None else now) + BUENDEL_S)
    _save(uid, d)


def clear(uid):
    try:
        os.remove(_file(uid))
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- what goes into the book
def _rdf(uid, welt, lang):
    """A round's frame for the album's views: the profile as host (its switches), the world of the hero's last evening."""
    return {"owner": uid, "ton": "", "lang": lang, "welt": welt, "plaetze": {}, "plan": None}


def _welt(h):
    for e in reversed(h.get("chronik") or []):
        if e.get("w"):
            return e["w"]
    return ""


def _li(lang):
    return 1 if lang == "en" else 0


def inhalt(dm, uid, h, lang):
    """Everything the book shows, from the panel's own data only (the renderer draws nothing else): a dict."""
    import dungeon_album as album
    r = dm.rules()
    li = _li(lang)
    welt = _welt(h)
    hv = dm.hero_view(r, h, lang, welt=welt)
    rdf = _rdf(uid, welt, lang)
    try:
        bestien = album.view(dm, r, rdf, h, lang)
    except Exception as e:
        print(f"dungeon: buch | fehler | album {type(e).__name__}", flush=True)
        bestien = None
    try:
        personen = album.people(dm, r, rdf, h, lang)
    except Exception as e:
        print(f"dungeon: buch | fehler | personen {type(e).__name__}", flush=True)
        personen = None
    voelker, klassen, gegner = dm._by(r, "voelker"), dm._by(r, "klassen"), dm._by(r, "gegner")
    welten = {w["id"]: w["name"][li] for w in r.get("welten") or []}
    people = {e["id"]: e for e in personen or []}
    # the chronicle: groups by chapter, newest first
    gruppen, cur = [], None
    abend = 0
    stufe = None
    for e in h.get("chronik") or []:
        if cur is None or cur["k"] != e["k"] or cur.get("zu"):
            cur = {"k": e["k"], "abende": [], "t": [e["t"], e["t"]], "mit": [], "ereignisse": [], "zu": False, "welt": ""}
            gruppen.append(cur)
        cur["t"][1] = e["t"]
        if e["a"] == "kampf":
            c = gegner.get(e["id"])
            if c:
                cur["ereignisse"].append({"a": "kampf", "name": c["name"][li], "n": e["n"], "id": e["id"]})
        elif e["a"] == "person":
            x = people.get(e["id"])
            if x:                                   # only people the album shows (its stages and word checks)
                cur["ereignisse"].append({"a": "person", "name": x["name"], "n": e["n"], "beruf": x.get("beruf", "")})
        else:
            if e["a"] == "abend":
                abend += 1
                cur["abende"].append(abend)
            else:
                cur["zu"] = True
            if stufe is not None and e["s"] > stufe:
                cur["ereignisse"].append({"a": "stufe", "s": e["s"]})
            stufe = e["s"]
            cur["welt"] = welten.get(e.get("w"), cur["welt"])
            for m in e.get("mit") or []:
                v, k = voelker.get(m["volk"]), klassen.get(m["klasse"])
                row = {"name": m["name"], "volk": v["name"][li] if v else "", "klasse": k["name"][li] if k else ""}
                if row not in cur["mit"]:
                    cur["mit"].append(row)
    for g in gruppen:
        merged = []
        for x in g["ereignisse"]:      # one line per foe of a chapter: 3× Goblin
            y = next((m for m in merged if x["a"] == "kampf" and m["a"] == "kampf" and m["id"] == x["id"]), None)
            if y:
                y["n"] += x["n"]
            else:
                merged.append(dict(x))
        g["mehr"] = max(0, len(merged) - GRUPPE_MAX)
        g["ereignisse"] = merged[:GRUPPE_MAX]
        g["mit"] = g["mit"][:MIT_MAX]
    gruppen.reverse()
    import dungeon_personen
    alle_leute = len(dungeon_personen.load())
    album_on = bestien is not None
    out = {
        "lang": lang, "hid": h["hid"],
        "held": {k: hv.get(k) for k in ("name", "volk", "klasse", "stufe", "satz", "ep", "ep_naechste", "gold", "leben",
                                        "leben_max", "rk", "kg", "trag", "belastet", "geschlecht_name")},
        "werte": [{"id": w["id"], "kurz": w["kurz"], "name": w["name"], "wert": w["wert"], "mod": w["gesamt"]} for w in hv["werte"]],
        "an": [dict(_ding(it), platz=k) for k, it in hv["an"].items() if it],
        "tasche": [_ding(it) for it in hv["tasche"]],
        "faehigkeiten": [{"name": x["name"], "satz": x["satz"]} for x in hv["faehigkeiten"]],
        "schutz": list(hv.get("widerstand") or []) + [f"{x['wert']} +{x['bonus']}" for x in hv.get("segen") or []],
        "zust": [x["name"] for x in hv.get("zust") or []],
        "narben": [x["t"] for x in hv.get("narben") or []],
        "portrait": ("held-" + h["hid"]) if h.get("bild") is not None else "",
        "welt": welten.get(welt, ""),
        "chronik": gruppen,
        "album": album_on,
        "bestien": (bestien or [])[:LISTE_MAX],
        "bestien_alle": len(r.get("gegner") or []),
        "siege": sum((h.get("album") or {}).values()),
        "personen": (personen or [])[:LISTE_MAX] if personen is not None else None,
        "personen_alle": alle_leute,
        "z": {"s": hv["stufe"], "a": dict(h.get("album") or {}), "p": dict(h.get("personen") or {}),
              "k": sum(1 for e in h.get("chronik") or [] if e["a"] == "kapitel"),
              "i": sorted(it["i"] for it in hv["tasche"] + [x for x in hv["an"].values() if x])},
    }
    _pictures(dm, r, welt, out)
    return out


def _ding(it):
    return {"i": it["i"], "id": it["id"], "art": it["art"], "name": it["name"], "selten": it["selten"], "selten_name": it["selten_name"],
            "zeilen": list(it["zeilen"])[:8], "info": it.get("info", ""), "kg": it["kg"], "n": it.get("n", 1), "satz": it.get("satz", "")}


def _pictures(dm, r, welt, out):
    """Only the names of pictures the panel has (dungeon.BILD_DIR): the items' pictures of their world."""
    try:
        import dungeon_dingbild as db
        if not db.on():
            return
        have = db.files()
        items = dm._by(r, "gegenstaende")
        for it in out["an"] + out["tasche"]:
            c = items.get(it["id"])
            n = db.picture_of(r, c, welt)[0] if c else ""
            it["bild"] = n if n in have else ""
    except Exception as e:
        print(f"dungeon: buch | fehler | bilder {type(e).__name__}", flush=True)


def fingerprint(data, m):
    return hashlib.sha256(json.dumps([data, m["key"], m["color"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


def neu(data, z):
    """„Neu seit der letzten Ausgabe“: a few fixed lines from the last edition's counts z (None: the first edition)."""
    en = data["lang"] == "en"
    if not z:
        return []
    out = []
    zn = data["z"]
    for k in range(z.get("k", 0) + 1, zn["k"] + 1):
        out.append(("Kapitel abgeschlossen" if not en else "Chapter closed") + f" ({k}.)")
    if zn["s"] > z.get("s", zn["s"]):
        out.append((f"Stufe {zn['s']} statt {z['s']}" if not en else f"Level {zn['s']} instead of {z['s']}"))
    import dungeon_album as album
    for e in data["bestien"]:
        alt = (z.get("a") or {}).get(e["id"], 0)
        if not alt:
            out.append((f"Neu im Bestiarium: {e['name']}" if not en else f"New in the bestiary: {e['name']}"))
        elif album.stage(alt) < e["stufe"]:
            out.append((f"{e['name']}: mehr bekannt ({e['siege']}. Sieg)" if not en else f"{e['name']}: more known ({e['siege']}th win)"))
    for e in data["personen"] or []:
        if not (z.get("p") or {}).get(e["id"]):
            out.append((f"Neu getroffen: {e['name']}" if not en else f"Newly met: {e['name']}"))
    alt_i = set(z.get("i") or [])
    for it in data["an"] + data["tasche"]:
        if it["i"] not in alt_i:
            out.append((f"Gefunden: {it['name']}" if not en else f"Found: {it['name']}") + (f" ({it['selten_name']})" if it["selten_name"] else ""))
    return out[:NEU_MAX]


# ---------------------------------------------------------------- pictures
def _picture(dm, name, wmm, hmm, m, grau):
    """A picture of the panel's own folder, opened again with Pillow, cut to the box's shape and scaled to the device's
    pixels; 16 grey steps dithered (Floyd–Steinberg) for a grey book, else colour. PNG bytes or None."""
    if not name or not _BILD.fullmatch(name):
        return None
    try:
        from PIL import Image, ImageOps
        path = dm.bild_file(name)
        if os.path.getsize(path) > BILD_BYTES:
            return None
        with Image.open(path) as im:
            if im.width * im.height > BILD_PIXEL:
                return None
            im.load()
            im = im.convert("RGB")
        px = (max(8, round(wmm / 25.4 * m["ppi"])), max(8, round(hmm / 25.4 * m["ppi"])))
        im = ImageOps.fit(im, px, Image.LANCZOS)
        if grau:
            pal = Image.new("P", (1, 1))
            pal.putpalette(sum(([v, v, v] for v in range(0, 256, 17)), []) + [0] * (3 * 240))
            im = im.convert("RGB").quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG).convert("L")
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        return b.getvalue()
    except Exception as e:      # a broken or strange file: the drawn symbol instead
        print(f"dungeon: buch | bild fehlt | {type(e).__name__}", flush=True)
        return None


# ---------------------------------------------------------------- layout per model (rmpapier.MODELS)
# mm. links: the reMarkable's toolbar sits at the left edge; reiter: tabs on the right (rm2, Pro) or a bar at the
# bottom (Move); s: type size relative to the physical page (the Move's page is narrow: the same size reads larger)
LAYOUT = {"rm2": {"spalten": 2, "s": 1.0, "links": 12.0, "rand": 8.0, "reiter": "rechts", "bild": 32.0, "ding": 12.0},
          "pro": {"spalten": 2, "s": 1.06, "links": 13.0, "rand": 9.0, "reiter": "rechts", "bild": 36.0, "ding": 14.0},
          "move": {"spalten": 1, "s": 0.94, "links": 7.0, "rand": 5.0, "reiter": "unten", "bild": 26.0, "ding": 11.0}}
# strong, well apart colours for the Gallery 3 screen (Paper Pro, Move), with the panel's paper colours of rmpapier
FARBEN = {"rot": (205, 30, 45), "blau": (25, 85, 205), "gruen": (20, 140, 65), "gold": (215, 150, 0), "violett": (125, 50, 175),
          "orange": (230, 105, 0), "tuerkis": (0, 145, 170), "braun": (125, 75, 30), "tinte": (28, 22, 40), "weinrot": (130, 25, 45)}
WERT_FARBE = {"staerke": "rot", "geschick": "gruen", "konstitution": "orange", "intelligenz": "blau", "weisheit": "tuerkis", "charisma": "violett"}
SELTEN_FARBE = {"gewoehnlich": "braun", "selten": "gruen", "rar": "blau", "episch": "violett", "legendaer": "orange"}
TEILE = (("held", "Heldenbogen", "Hero sheet", "Held", "Hero"), ("chronik", "Chronik der Begegnungen", "Chronicle of encounters", "Chronik", "Chronicle"),
         ("personen", "Personen", "People", "Personen", "People"), ("bestien", "Bestiarium", "Bestiary", "Bestien", "Beasts"),
         ("dinge", "Gegenstände", "Items", "Dinge", "Items"))
RUEMISCH = ("I", "II", "III", "IV", "V", "VI")


class Buch:
    """One book in the page format of a model m (rmpapier.model) and colour or grey. Positions are mm from the top left;
    everything drawn goes through _box, which records what lies outside the page's area (overflow)."""

    def __init__(self, dm, m, farbe, lang, titel, seiten=None):
        from fpdf import FPDF
        import docrender
        import rmpapier
        self.dm, self.m, self.lang, self.en = dm, m, lang, lang == "en"
        self.L = LAYOUT.get(m["key"], LAYOUT["rm2"])
        self.farbe = bool(farbe and m["color"])
        self.W, self.H = m["mm"]
        self.s = self.L["s"]
        self.c = dict(rmpapier.COLOR if self.farbe else rmpapier.GRAY)
        self.k = FARBEN if self.farbe else {k: (0, 0, 0) for k in FARBEN}
        self.x0 = self.L["links"]
        tab = 9.0 if self.L["reiter"] == "rechts" else 0.0
        self.x1 = self.W - self.L["rand"] - tab
        self.y0 = self.L["rand"] + 4
        self.y1 = self.H - self.L["rand"] - (15.5 if self.L["reiter"] == "unten" else 9)
        self.seiten = seiten or {}
        self.overflow, self.bilder, self.teil = [], 0, ""
        doc = self.doc = FPDF(unit="mm", format=(self.W, self.H))
        doc.set_auto_page_break(False)
        doc.set_margins(self.x0, self.y0, self.W - self.x1)
        doc.set_creator("Spark")
        doc.set_title(rmpapier.clean(titel, 200))
        reg, bold = docrender._font_files()
        d = os.path.dirname(reg) if reg else ""
        ser, serb = os.path.join(d, "DejaVuSerif.ttf"), os.path.join(d, "DejaVuSerif-Bold.ttf")
        self.uni = bool(reg)
        if reg:
            doc.add_font("Sans", "", reg)
            doc.add_font("Sans", "B", bold)
            if os.path.isfile(ser) and os.path.isfile(serb):
                doc.add_font("Serif", "", ser)
                doc.add_font("Serif", "B", serb)
                self.fam = "Serif"
            else:
                self.fam = "Sans"
            self.sans = "Sans"
        else:
            self.fam = self.sans = "Helvetica"
        self.links = {t[0]: doc.add_link(page=(seiten or {}).get(t[0], 1)) for t in TEILE}
        self.links["inhalt"] = doc.add_link(page=1)
        self.y = self.y0
        self.stand = ""

    # -- text
    def tx(self, s):
        import rmpapier
        s = rmpapier.clean(s)
        if self.uni:
            return s
        import docrender
        return "".join(docrender.LATIN1.get(ch, ch) for ch in s).encode("latin-1", "replace").decode("latin-1")

    def font(self, size, b=False, color="fg", sans=False):
        self.doc.set_font(self.sans if sans else self.fam, "B" if b else "", size * self.s)
        self.doc.set_text_color(*self._col(color))

    def _col(self, color):
        if isinstance(color, tuple):
            return color
        return self.c.get(color) or self.k.get(color) or self.c["fg"]

    def _box(self, x, y, w, h):
        if x < -0.01 or y < -0.01 or x + w > self.W + 0.01 or y + h > self.H + 0.01 or \
                (self.teil and (y + h > self.y1 + 0.6 or y < self.y0 - 12 or x < self.x0 - 0.6 or x + w > self.x1 + 0.6)):
            self.overflow.append((self.doc.page, self.teil, round(x, 1), round(y, 1), round(w, 1), round(h, 1)))

    def lines(self, text, w, size, b=False, most=99, sans=False):
        """The lines text takes in width w; cut to most lines (the last one with „…“)."""
        self.font(size, b, sans=sans)
        t = self.tx(text)
        if not t.strip():
            return []
        out = self.doc.multi_cell(w, 1, t, dry_run=True, output="LINES")
        if len(out) > most:
            out = out[:most]
            last = out[-1]
            while last and self.doc.get_string_width(last + "…") > w:
                last = last[:-1]
            out[-1] = last.rstrip() + "…"
        return out

    def lh(self, size):
        return size * self.s * 0.43

    def write(self, x, y, text, w, size, b=False, color="fg", most=99, align="L", sans=False):
        """Text in the box from (x, y), width w: returns its height."""
        ls = self.lines(text, w, size, b, most, sans)
        self.font(size, b, color, sans)
        lh = self.lh(size)
        for i, ln in enumerate(ls):
            self.doc.set_xy(x, y + i * lh)
            self.doc.cell(w, lh, ln, align=align)
        self._box(x, y, w, len(ls) * lh)
        return len(ls) * lh

    def height(self, text, w, size, b=False, most=99, sans=False):
        return len(self.lines(text, w, size, b, most, sans)) * self.lh(size)

    def caps(self, x, y, text, size, color="fg", b=True, w=None):
        """Small capitals of the old books: capitals at size, the rest as smaller capitals; cut to w. Returns the width."""
        d = self.doc
        t = self.tx(text)
        parts, cur = [], ""
        for ch in t:
            big = not ch.isalpha() or ch.isupper()
            if parts and parts[-1][0] == big:
                parts[-1][1] += ch
            else:
                parts.append([big, ch])
        xx = x
        lim = x + (w if w is not None else self.x1 - x)
        d.set_text_color(*self._col(color))
        for big, s in parts:
            sz = size if big else size * 0.78
            d.set_font(self.fam, "B" if b else "", sz * self.s)
            s = s if big else s.upper()
            while s and xx + d.get_string_width(s) > lim:
                s = s[:-1]
            d.text(xx, y, s)
            xx += d.get_string_width(s)
            cur += s
            if xx >= lim:
                break
        self._box(x, y - size * self.s * 0.3, xx - x, size * self.s * 0.36)
        return xx - x

    # -- drawing
    def fill(self, color):
        self.doc.set_fill_color(*self._col(color))

    def draw(self, color, width=0.3):
        self.doc.set_draw_color(*self._col(color))
        self.doc.set_line_width(width)

    def rrect(self, x, y, w, h, style="D", r=1.6):
        self.doc.rect(x, y, w, h, style=style, round_corners=r > 0, corner_radius=r)
        self._box(x, y, w, h)

    def dots(self, x, y, n, of=3, r=1.1, color="tinte"):
        """Stages as filled and empty dots (a stage never only by colour)."""
        for i in range(of):
            self.draw(color, 0.3)
            self.fill(color if i < n else "paper")
            self.doc.ellipse(x + i * (2 * r + 0.8), y, 2 * r, 2 * r, style="DF")
        self._box(x, y, of * (2 * r + 0.8), 2 * r)
        return of * (2 * r + 0.8)

    def bar(self, x, y, w, h, frac, color):
        self.draw("tinte", 0.35)
        self.fill("paper")
        self.rrect(x, y, w, h, "DF", h / 2)
        f = max(0.0, min(1.0, frac))
        if f > 0.02:
            self.fill(color)
            self.rrect(x, y, max(h, w * f), h, "F", h / 2)
            self.draw("tinte", 0.35)
            self.rrect(x, y, w, h, "D", h / 2)

    # -- symbols drawn with lines (no font has them; nothing from outside)
    def icon(self, kind, x, y, sz, color="tinte"):
        d = self.doc
        c = self._col(color)
        d.set_fill_color(*c)
        d.set_draw_color(*c)
        d.set_line_width(max(0.25, sz * 0.07))
        u = sz / 10.0
        P = lambda pts: [(x + a * u, y + b * u) for a, b in pts]   # noqa: E731
        if kind == "herz":
            d.ellipse(x + 0.6 * u, y + 1.2 * u, 4.6 * u, 4.4 * u, style="F")
            d.ellipse(x + 4.8 * u, y + 1.2 * u, 4.6 * u, 4.4 * u, style="F")
            d.polygon(P([(0.75, 4.4), (9.25, 4.4), (5, 9.4)]), style="F")
        elif kind == "schild":
            d.polygon(P([(5, 0.4), (9.2, 1.8), (9.2, 5), (5, 9.6), (0.8, 5), (0.8, 1.8)]), style="F")
            d.set_draw_color(255, 255, 255)
            d.line(x + 5 * u, y + 1.6 * u, x + 5 * u, y + 8.2 * u)
            d.line(x + 1.9 * u, y + 4.4 * u, x + 8.1 * u, y + 4.4 * u)
        elif kind == "muenze":
            d.ellipse(x + 0.5 * u, y + 0.5 * u, 9 * u, 9 * u, style="F")
            d.set_fill_color(255, 255, 255)
            d.polygon(P([(5, 2.2), (5.9, 4.2), (8, 4.3), (6.4, 5.6), (7, 7.7), (5, 6.5), (3, 7.7), (3.6, 5.6), (2, 4.3), (4.1, 4.2)]), style="F")
        elif kind == "beutel":
            d.ellipse(x + 1 * u, y + 3 * u, 8 * u, 6.8 * u, style="F")
            d.polygon(P([(3.2, 1), (6.8, 1), (6, 3.6), (4, 3.6)]), style="F")
        elif kind == "schwert":
            d.polygon(P([(5, 0.2), (6, 1.6), (6, 6.4), (4, 6.4), (4, 1.6)]), style="F")
            d.rect(x + 2.2 * u, y + 6.4 * u, 5.6 * u, 1 * u, style="F")
            d.rect(x + 4.5 * u, y + 7.4 * u, 1 * u, 1.8 * u, style="F")
            d.ellipse(x + 4.2 * u, y + 9 * u, 1.6 * u, 1 * u, style="F")
        elif kind == "kampf":
            d.set_line_width(sz * 0.12)
            d.line(x + 1.5 * u, y + 1.5 * u, x + 8.5 * u, y + 8.5 * u)
            d.line(x + 8.5 * u, y + 1.5 * u, x + 1.5 * u, y + 8.5 * u)
            d.set_line_width(sz * 0.1)
            d.line(x + 0.8 * u, y + 6.6 * u, x + 3.4 * u, y + 9.2 * u)
            d.line(x + 9.2 * u, y + 6.6 * u, x + 6.6 * u, y + 9.2 * u)
        elif kind == "maske":
            d.polygon(P([(1, 1.5), (9, 1.5), (9, 5), (5, 9.5), (1, 5)]), style="F")
            d.set_fill_color(255, 255, 255)
            d.ellipse(x + 2.4 * u, y + 3.3 * u, 2 * u, 1.3 * u, style="F")
            d.ellipse(x + 5.6 * u, y + 3.3 * u, 2 * u, 1.3 * u, style="F")
        elif kind == "kralle":
            d.set_line_width(sz * 0.1)
            for a in (2, 5, 8):
                d.line(x + a * u, y + 0.8 * u, x + (a - 1.2) * u, y + 9.2 * u)
        elif kind == "stern":
            pts = [(5 + (4.6 if i % 2 == 0 else 1.9) * math.cos(math.radians(-90 + 36 * i)),
                    5.3 + (4.6 if i % 2 == 0 else 1.9) * math.sin(math.radians(-90 + 36 * i))) for i in range(10)]
            d.polygon(P(pts), style="F")
        elif kind == "rolle":
            d.rect(x + 2 * u, y + 1 * u, 6 * u, 8 * u, style="F")
            d.set_draw_color(255, 255, 255)
            for a in (3, 4.8, 6.6):
                d.line(x + 3.2 * u, y + a * u, x + 6.8 * u, y + a * u)
        elif kind == "feder":
            d.polygon(P([(8.8, 0.8), (6, 6.4), (3.4, 7.6), (4.6, 4.4)]), style="F")
            d.line(x + 4 * u, y + 7 * u, x + 1.2 * u, y + 9.6 * u)
        elif kind == "trank":
            d.ellipse(x + 1.8 * u, y + 3.4 * u, 6.4 * u, 6.2 * u, style="F")
            d.rect(x + 4 * u, y + 0.8 * u, 2 * u, 3 * u, style="F")
        elif kind == "ring":
            d.set_line_width(sz * 0.14)
            d.ellipse(x + 2 * u, y + 2.6 * u, 6 * u, 6 * u, style="D")
            d.polygon(P([(5, 0.4), (6.4, 2.2), (5, 3.4), (3.6, 2.2)]), style="F")
        elif kind == "schloss":
            d.rect(x + 2 * u, y + 4.4 * u, 6 * u, 5 * u, style="F")
            d.set_line_width(sz * 0.11)
            d.ellipse(x + 3.1 * u, y + 1 * u, 3.8 * u, 6 * u, style="D")
        elif kind == "zurueck":
            d.polygon(P([(1, 4.5), (4.6, 1.4), (4.6, 3.3), (9, 3.3), (9, 5.7), (4.6, 5.7), (4.6, 7.6)]), style="F")
        self._box(x, y, sz, sz)

    def ding_icon(self, art):
        return {"waffe": "schwert", "ruestung": "schild", "schmuck": "ring", "trank": "trank", "zauber": "stern",
                "rolle": "rolle", "werkzeug": "beutel", "schatz": "muenze"}.get(art, "beutel")

    def wappen(self, x, y, w, seed):
        """The hero's arms: a shield divided by a bend, two tinctures and a star from its id (always the same)."""
        d = self.doc
        n = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
        tinkturen = ("rot", "blau", "gruen", "violett", "weinrot", "tuerkis")
        a, b = self._col(tinkturen[n % len(tinkturen)]), self._col("gold")
        h = w * 1.18
        u = w / 10.0
        shape = [(x + 0.4 * u, y), (x + 9.6 * u, y), (x + 9.6 * u, y + 5.6 * u), (x + 5 * u, y + h), (x + 0.4 * u, y + 5.6 * u)]
        d.set_fill_color(*a)
        d.set_draw_color(*self._col("tinte"))
        d.set_line_width(0.5)
        d.polygon(shape, style="DF")
        half = [(x + 5 * u, y), (x + 9.6 * u, y), (x + 9.6 * u, y + 5.6 * u), (x + 5 * u, y + h)]
        if self.farbe:
            d.set_fill_color(*b)
            d.polygon(half, style="F")
        else:                                       # grey: the second tincture as hatching (heraldry's own way)
            d.set_fill_color(255, 255, 255)
            d.polygon(half, style="F")
            d.set_line_width(0.25)
            d.set_draw_color(0, 0, 0)
            yy = y + 0.9 * u
            while yy < y + h - 0.6 * u:          # horizontal lines inside the right half of the shield
                xr = x + 9.6 * u if yy <= y + 5.6 * u else x + 9.6 * u - (yy - y - 5.6 * u) / (h - 5.6 * u) * 4.6 * u
                if xr > x + 5.2 * u:
                    d.line(x + 5 * u, yy, xr, yy)
                yy += w / 14
        d.set_draw_color(*self._col("tinte"))
        d.set_line_width(0.5)
        d.polygon(shape, style="D")
        self.icon("stern", x + 2.3 * u, y + 2.2 * u, 5.4 * u, "paper" if not self.farbe else (255, 255, 255))
        self._box(x, y, w, h)
        return h

    # -- the page
    def frame(self):
        """The frame of the old books: a strong and a thin line, small rings at the corners."""
        d, W, H = self.doc, self.W, self.H
        o = 2.4 if self.m["key"] == "move" else 3.2
        self.draw("weinrot" if self.farbe else "tinte", 0.9)
        d.rect(o, o, W - 2 * o, H - 2 * o)
        self.draw("tinte", 0.25)
        d.rect(o + 1.4, o + 1.4, W - 2 * o - 2.8, H - 2 * o - 2.8)
        self.fill("gold" if self.farbe else "tinte")
        for cx, cy in ((o, o), (W - o, o), (o, H - o), (W - o, H - o)):
            d.ellipse(cx - 1.2, cy - 1.2, 2.4, 2.4, style="F")

    def tabs(self):
        d = self.doc
        names = [("inhalt", "Inhalt" if not self.en else "Contents", "")] + \
                [(t[0], t[4] if self.en else t[3], RUEMISCH[i]) for i, t in enumerate(TEILE)]
        if self.L["reiter"] == "rechts":
            top, bot = self.H * 0.12, self.H * 0.84
            hh = (bot - top) / len(names)
            x = self.W - self.L["rand"] - 9.0 + 1.0
            for i, (k, name, num) in enumerate(names):
                y = top + i * hh
                act = k == self.teil or (k == "inhalt" and not self.teil)
                self.draw("tinte", 0.35)
                self.fill("acc" if act and self.farbe else ("tinte" if act else "paper"))
                d.rect(x, y + 0.4, 7.2, hh - 0.8, style="DF", round_corners=True, corner_radius=1.2)
                self.font(6.6, True, "paper" if act else "tinte", sans=True)
                label = self.tx((num + " · " if num else "") + name)
                while d.get_string_width(label) > hh - 3 and len(label) > 3:
                    label = label[:-1]
                with d.rotation(-90, x + 3.6, y + hh / 2):
                    d.text(x + 3.6 - d.get_string_width(label) / 2, y + hh / 2 + 0.9, label)
                d.link(x, y, 7.2, hh, self.links[k])
        else:
            n = len(names)
            y = self.H - self.L["rand"] - 7.4
            w = (self.x1 - self.x0) / n
            for i, (k, name, num) in enumerate(names):
                xx = self.x0 + i * w
                act = k == self.teil or (k == "inhalt" and not self.teil)
                self.draw("tinte", 0.3)
                self.fill("acc" if act and self.farbe else ("tinte" if act else "paper"))
                d.rect(xx + 0.3, y, w - 0.6, 6.2, style="DF", round_corners=True, corner_radius=1.2)
                self.font(5.6, True, "paper" if act else "tinte", sans=True)
                label = self.tx(name)
                while d.get_string_width(label) > w - 1.2 and len(label) > 2:
                    label = label[:-1]
                d.text(xx + w / 2 - d.get_string_width(label) / 2, y + 4.1, label)
                d.link(xx, y, w, 6.2, self.links[k])

    def footer(self):
        d = self.doc
        y = self.H - self.L["rand"] - (8.8 if self.L["reiter"] == "unten" else 2.6)
        self.font(6.8, False, "mut", sans=True)
        if self.teil:
            d.set_xy(self.x0, y - 3)
            d.cell(20, 3.4, self.tx("← " + ("Inhalt" if not self.en else "Contents")))
            d.link(self.x0, y - 3, 20, 3.4, self.links["inhalt"])
        d.set_xy(self.x0 + 18, y - 3)
        d.cell(self.x1 - self.x0 - 36, 3.4, self.tx(self.stand), align="C")
        d.set_xy(self.x1 - 18, y - 3)
        d.cell(18, 3.4, self.tx(("Seite " if not self.en else "Page ") + str(d.page)), align="R")

    def page(self, title="", sub=""):
        self.doc.add_page()
        self.frame()
        self.tabs()
        self.footer()
        self.y = self.y0
        if title:
            self.caps(self.x0, self.y + 6.2 * self.s, title, 17 if self.m["key"] != "move" else 14, "tinte")
            self.y += 8.6 * self.s
            if sub:
                self.y += self.write(self.x0, self.y, sub, self.x1 - self.x0, 9, color="mut", most=2) + 0.6
            self.rule()

    def rule(self, double=True):
        self.draw("weinrot" if self.farbe else "tinte", 0.5)
        self.doc.line(self.x0, self.y + 0.6, self.x1, self.y + 0.6)
        if double:
            self.draw("tinte", 0.2)
            self.doc.line(self.x0, self.y + 1.4, self.x1, self.y + 1.4)
        self.y += 3.6

    def need(self, h, title="", sub=""):
        if self.y + h > self.y1:
            self.page(title, sub)
            return True
        return False

    def start(self, key, title, sub=""):
        self.teil = key
        self.page(title, sub)
        self.doc.set_link(self.links[key], page=self.doc.page)
        self.doc.start_section(self.tx(title))
        self.seiten[key] = self.doc.page
        self.weiter = (title, sub)

    def head(self, text, color="tinte"):
        """A heading inside a part with a line to the right."""
        sz = 11
        self.need(10 * self.s + 8, *self.weiter)
        y = self.y + 4.6 * self.s
        w = self.caps(self.x0, y, text, sz, color)
        self.draw("tinte", 0.35)
        if self.x0 + w + 3 < self.x1:
            self.doc.line(self.x0 + w + 2.5, y - 1.3, self.x1, y - 1.3)
        self.y += 7.4 * self.s

    def grid(self, items, cols, measure, draw, gap=2.6):
        """Cards in rows of cols; a row that does not fit goes to the next page (with the part's title again)."""
        w = (self.x1 - self.x0 - gap * (cols - 1)) / cols
        for i in range(0, len(items), cols):
            row = items[i:i + cols]
            h = max(measure(x, w) for x in row)
            h = min(h, self.y1 - self.y0 - 30)
            self.need(h, *self.weiter)
            for j, x in enumerate(row):
                draw(x, self.x0 + j * (w + gap), self.y, w, h)
            self.y += h + gap

    def chips(self, texts, color="tinte", size=8.4):
        """Pills that flow into lines."""
        d = self.doc
        h = self.lh(size) + 2.2
        x = self.x0
        self.need(h + 1, *self.weiter)
        for t in texts:
            self.font(size, False, "fg")
            s = self.tx(t)
            while d.get_string_width(s) + 5 > self.x1 - self.x0 and len(s) > 4:
                s = s[:-2] + "…"
            w = d.get_string_width(s) + 5
            if x + w > self.x1:
                x = self.x0
                self.y += h + 1.4
                self.need(h + 1, *self.weiter)
            self.draw(color, 0.35)
            self.rrect(x, self.y, w, h, "D", h / 2)
            self.font(size, False, "fg")
            d.set_xy(x, self.y + 1.1)
            d.cell(w, h - 2.2, s, align="C")
            x += w + 1.6
        self.y += h + 2.4

    def bild(self, name, x, y, w, h, fallback, color="tinte"):
        """A picture of the panel or the drawn symbol in a frame."""
        data = None
        if name and self.bilder < BILDER_MAX:
            data = _picture(self.dm, name, w, h, self.m, not self.farbe)
        self.draw("tinte", 0.45)
        if data:
            self.doc.image(io.BytesIO(data), x=x, y=y, w=w, h=h)
            self.bilder += 1
            self.rrect(x, y, w, h, "D", 1.2)
        else:
            self.fill("tint")
            self.rrect(x, y, w, h, "DF", 1.2)
            s = min(w, h) * 0.56
            self.icon(fallback, x + (w - s) / 2, y + (h - s) / 2, s, color)

    def finish(self):
        return bytes(self.doc.output())


# ---------------------------------------------------------------- the parts
def _t(b, de, en):
    return en if b.en else de


def _inhalt(b, data, ausgabe, neue):
    b.teil = ""
    b.page()
    b.doc.set_link(b.links["inhalt"], page=b.doc.page)
    b.doc.start_section(b.tx(_t(b, "Inhalt", "Contents")))
    cw = b.x1 - b.x0
    move = b.m["key"] == "move"
    ws = 22 if move else 30
    b.y += 2
    hh = b.wappen(b.x0 + (cw - ws) / 2, b.y, ws, data["hid"])
    b.y += hh + 4
    b.y += b.write(b.x0, b.y, _t(b, "Das Heldenbuch von", "The hero book of"), cw, 10, color="mut", align="C")
    b.font(22 if not move else 17, True)
    name = data["held"]["name"]
    tw = b.doc.get_string_width(b.tx(name))
    b.caps(b.x0 + max(0, (cw - tw) / 2), b.y + 7 * b.s, name, 22 if not move else 17, "tinte", w=cw)
    b.y += 10 * b.s
    hv = data["held"]
    sub = f"{hv['volk']} · {hv['klasse']} · {_t(b, 'Stufe', 'Level')} {hv['stufe']}" + (f" · {data['welt']}" if data["welt"] else "")
    b.y += b.write(b.x0, b.y, sub, cw, 10, color="mut", align="C", most=2) + 2
    b.rule()
    zeilen = (("held", "schild", _t(b, "Werte, Ausrüstung, Fähigkeiten, Narben", "Values, gear, abilities, scars")),
              ("chronik", "rolle", _chronik_sub(b, data)),
              ("personen", "maske", _personen_sub(b, data)),
              ("bestien", "kralle", _bestien_sub(b, data)),
              ("dinge", "schwert", _t(b, f"{len(data['an'])} angelegt · {len(data['tasche'])} in der Tasche",
                                      f"{len(data['an'])} worn · {len(data['tasche'])} in the bag")))
    for i, (k, ic, sub) in enumerate(zeilen):
        t = TEILE[i]
        rh = 12.5 * b.s
        y = b.y
        b.font(12, True)
        b.doc.set_xy(b.x0, y + 1)
        b.doc.cell(9, 6, RUEMISCH[i])
        b.icon(ic, b.x0 + 9.5, y + 1.4, 5.2, ["rot", "weinrot", "violett", "gruen", "blau"][i])
        b.write(b.x0 + 17, y + 0.6, t[2] if b.en else t[1], cw - 30, 11.5, True, most=1)
        b.write(b.x0 + 17, y + 6.2 * b.s, sub, cw - 30, 8.4, color="mut", most=1)
        n = str(b.seiten.get(k, ""))
        b.draw("tinte", 0.45)
        b.rrect(b.x1 - 11, y + 1.4, 11, 6.4, "D", 3.2)
        b.font(11, True)
        b.doc.set_xy(b.x1 - 11, y + 1.6)
        b.doc.cell(11, 6, n, align="C")
        b.doc.link(b.x0, y, cw, rh, b.links[k])
        b.y += rh
        b.draw("tinte", 0.3)
        b.doc.line(b.x0, b.y - 1.2, b.x1, b.y - 1.2)
    b.y += 3
    if neue:
        lines = [b.lines("• " + x, cw - 8, 9, most=2) for x in neue]
        h = sum(len(x) for x in lines) * b.lh(9) + 11
        if b.y + h > b.y1:
            lines, h = lines[:2], sum(len(x) for x in lines[:2]) * b.lh(9) + 11
        b.draw("weinrot" if b.farbe else "tinte", 0.6)
        b.rrect(b.x0, b.y, cw, h, "D", 2.4)
        b.caps(b.x0 + 4, b.y + 5.4, _t(b, "Neu seit der letzten Ausgabe", "New since the last edition"), 9.5, "weinrot" if b.farbe else "tinte")
        yy = b.y + 8.4
        for ls in lines:
            for ln in ls:
                b.font(9)
                b.doc.set_xy(b.x0 + 4, yy)
                b.doc.cell(cw - 8, b.lh(9), ln)
                yy += b.lh(9)
        b.y += h + 3
    note = _t(b, "Handschrift bleibt bei einer neuen Ausgabe in der alten (Ordner „Archiv“). Für Notizen gibt es das Dokument „Notizen – "
                 + name + "“, das der Spark nie ersetzt.",
              "Handwriting stays in the old edition when a new one comes (folder „Archiv“). For notes there is the document „Notizen – "
              + name + "“, which the Spark never replaces.")
    if b.y + b.height(note, cw, 7.6) <= b.y1:
        b.y += b.write(b.x0, b.y, note, cw, 7.6, color="mut")


def _chronik_sub(b, data):
    g = data["chronik"]
    ab = sum(len(x["abende"]) for x in g)
    ka = sum(1 for x in g if x["zu"])
    return _t(b, f"{ab} Abende · {ka} Kapitel", f"{ab} evenings · {ka} chapters")


def _personen_sub(b, data):
    if data["personen"] is None:
        return _t(b, "Personen-Album ist aus", "People album is off")
    return _t(b, f"{len(data['personen'])} von {data['personen_alle']} bekannt", f"{len(data['personen'])} of {data['personen_alle']} known")


def _bestien_sub(b, data):
    if not data["album"]:
        return _t(b, "Monster-Album ist aus", "Monster album is off")
    return _t(b, f"{len(data['bestien'])} Arten von {data['bestien_alle']} · {data['siege']} Siege",
              f"{len(data['bestien'])} kinds of {data['bestien_alle']} · {data['siege']} wins")


def _held(b, data):
    hv = data["held"]
    b.start("held", hv["name"], f"{hv['volk']} · {hv['klasse']} · {_t(b, 'Stufe', 'Level')} {hv['stufe']}")
    cw = b.x1 - b.x0
    move = b.m["key"] == "move"
    P = b.L["bild"]
    tw = cw - P - 4
    y = b.y
    yy = y
    if not move:
        hh = b.wappen(b.x0, y, 14, data["hid"])
        tx0, tw = b.x0 + 18, tw - 18
        yy = y
    else:
        hh, tx0 = 0, b.x0
    if hv.get("satz"):
        yy += b.write(tx0, yy, "„" + hv["satz"] + "“", tw, 9.4, color="fg", most=5) + 1.5
    if hv.get("geschlecht_name"):
        yy += b.write(tx0, yy, hv["geschlecht_name"], tw, 8.4, color="mut", most=1)
    if data["zust"]:
        yy += b.write(tx0, yy, _t(b, "Zustand: ", "State: ") + ", ".join(data["zust"]), tw, 8.4, b=True, color="rot", most=2)
    b.bild(data["portrait"], b.x1 - P, y, P, P * 1.15, "maske")
    b.y = max(yy, y + hh, y + P * 1.15) + 3
    # experience
    ep, nx = hv["ep"], hv["ep_naechste"]
    b.need(12, *b.weiter)
    b.bar(b.x0, b.y, cw, 3.4, (ep / nx) if nx else 1.0, "violett")
    b.y += 4.6
    b.write(b.x0, b.y, _t(b, f"Erfahrung {ep:,} EP", f"Experience {ep:,} XP").replace(",", "." if not b.en else ","), cw / 2, 8.6)
    b.write(b.x0 + cw / 2, b.y, (_t(b, f"Stufe {hv['stufe'] + 1} bei {nx:,} EP", f"Level {hv['stufe'] + 1} at {nx:,} XP") if nx
                                 else _t(b, "höchste Stufe", "highest level")).replace(",", "." if not b.en else ","), cw / 2, 8.6, align="R")
    b.y += 6
    # life, armour, gold, load
    tiles = [("herz", "rot", f"{hv['leben']}/{hv['leben_max']}", _t(b, "Leben", "Life"), hv["leben"] / max(1, hv["leben_max"])),
             ("schild", "blau", str(hv["rk"]), _t(b, "Rüstung", "Armour"), None),
             ("muenze", "gold", str(hv["gold"]), _t(b, "Gold", "Gold"), None),
             ("beutel", "braun", f"{round(hv['kg'])}/{round(hv['trag'])}", _t(b, "Last kg", "Load kg"), hv["kg"] / max(1, hv["trag"]))]

    def tile_h(x, w):
        return 15 * b.s

    def tile(x, xx, yy, w, h):
        ic, col, num, lab, frac = x
        b.draw(col if b.farbe else "tinte", 0.6)
        b.rrect(xx, yy, w, h, "D", 2)
        b.icon(ic, xx + 2.2, yy + 3, 6.4 * b.s, col)
        tx = xx + 4 + 6.4 * b.s
        b.write(tx, yy + 1.6, num, w - (tx - xx) - 1, 14 if not move else 12.5, True, most=1)
        b.write(tx, yy + 8 * b.s, lab.upper(), w - (tx - xx) - 1, 6.6, color="mut", most=1, sans=True)
        if frac is not None:
            col2 = col if not (ic == "herz" and frac < 0.34) else "rot"
            b.bar(tx, yy + h - 3, w - (tx - xx) - 2.4, 1.6, frac, col2)
    b.grid(tiles, 4 if not move else 2, tile_h, tile)
    # the six values as shields
    werte = data["werte"]

    def shield_h(x, w):
        return min(w * 1.12, 25.0 * b.s)

    def shield(x, xx, yy, w, h):
        d = b.doc
        xx, w = xx + (w - h / 1.12) / 2, h / 1.12          # never wider than its height allows (the Move's three a row)
        col = WERT_FARBE.get(x["id"], "tinte")
        u = w / 10
        shape = [(xx + 0.3 * u, yy), (xx + 9.7 * u, yy), (xx + 9.7 * u, yy + 6.6 * u), (xx + 5 * u, yy + h), (xx + 0.3 * u, yy + 6.6 * u)]
        b.draw(col if b.farbe else "tinte", 0.7)
        b.fill("paper")
        d.polygon(shape, style="DF")
        if b.farbe:
            b.fill(col)
            d.rect(xx + 0.3 * u, yy, 9.4 * u, 2.4 * u, style="F")
        else:
            b.fill("tinte")
            d.rect(xx + 0.3 * u, yy, 9.4 * u, 2.4 * u, style="F")
        b.write(xx, yy + 0.35 * u, x["kurz"], w, 7.4, True, color="paper", align="C", most=1, sans=True)
        b.write(xx, yy + 2.9 * u, str(x["wert"]), w, 19 if not move else 16, True, align="C", most=1)
        m = x["mod"]
        pill = ("+" if m > 0 else "±" if m == 0 else "-") + str(abs(m))
        pw = 3.6 * u
        b.fill("tinte")
        b.rrect(xx + 5 * u - pw / 2, yy + 7.2 * u, pw, 2.1 * u, "F", 1.0 * u)
        b.write(xx + 5 * u - pw / 2, yy + 7.25 * u, pill, pw, 7.4, True, color="paper", align="C", most=1, sans=True)
        b._box(xx, yy, w, h)
    b.grid(werte, 6 if not move else 3, shield_h, shield, gap=3)
    # what it wears
    if data["an"]:
        b.head(_t(b, "Angelegt", "Worn"))
        _ding_zeilen(b, data["an"], 2 if not move else 1, kurz=True)
    if data["faehigkeiten"]:
        b.head(_t(b, "Fähigkeiten", "Abilities"))

        def fh(x, w):
            return b.height(x["name"], w - 3, 10, True, 1) + b.height(x["satz"], w - 3, 8.4, most=4) + 2

        def fd(x, xx, yy, w, h):
            b.fill("acc" if b.farbe else "tinte")
            b.doc.rect(xx, yy, 0.9, h - 1, style="F")
            hh = b.write(xx + 2.6, yy, x["name"], w - 3, 10, True, most=1)
            b.write(xx + 2.6, yy + hh, x["satz"], w - 3, 8.4, most=4)
        b.grid(data["faehigkeiten"], 2 if not move else 1, fh, fd)
    if data["tasche"]:
        b.head(_t(b, "Tasche", "Bag"))
        b.chips([x["name"] + (f" ×{x['n']}" if x["n"] > 1 else "") for x in data["tasche"]])
    if data["schutz"]:
        b.head(_t(b, "Schutz", "Protection"))
        b.chips(data["schutz"], "blau")
    b.head(_t(b, "Narben", "Scars"))
    if data["narben"]:
        for n in data["narben"]:
            h = b.height(n, b.x1 - b.x0 - 6, 9, most=3)
            b.need(h + 1, *b.weiter)
            b.icon("kralle", b.x0, b.y + 0.4, 3.6, "weinrot")
            b.y += b.write(b.x0 + 5.5, b.y, n, b.x1 - b.x0 - 6, 9, most=3) + 1.2
    else:
        b.y += b.write(b.x0, b.y, _t(b, "Noch keine Narbe.", "No scar yet."), b.x1 - b.x0, 9, color="mut")


def _ding_zeilen(b, items, cols, kurz=False):
    slot = {"kopf": ("Kopf", "Head"), "hals": ("Hals", "Neck"), "koerper": ("Körper", "Body"), "haupthand": ("Haupthand", "Main hand"),
            "nebenhand": ("Nebenhand", "Off hand"), "haende": ("Hände", "Hands"), "guertel": ("Gürtel", "Belt"), "fuesse": ("Füße", "Feet"),
            "ring1": ("Ring", "Ring"), "ring2": ("Ring", "Ring")}
    D = b.L["ding"]

    def text(x):
        z = [x["selten_name"]] if x["selten_name"] else []
        z += x["zeilen"][:1 if kurz else 8]
        return " · ".join(z) if kurz else "\n".join(z + ([x["info"]] if x.get("info") else []))

    def mh(x, w):
        tw = w - D - 3
        top = b.height(slot[x["platz"]][1 if b.en else 0], tw, 7, most=1) if x.get("platz") else 0
        return max(D + 1.5, top + b.height(x["name"], tw, 9.6, True, 2) + b.height(text(x), tw, 7.8, most=3 if kurz else 9) + 1.8)

    def dd(x, xx, yy, w, h):
        col = SELTEN_FARBE.get(x["selten"], "tinte")
        b.bild(x.get("bild", ""), xx, yy + 0.4, D, D, b.ding_icon(x["art"]), col)
        tx, tw = xx + D + 2.4, w - D - 3
        y2 = yy
        if x.get("platz"):
            y2 += b.write(tx, y2, slot[x["platz"]][1 if b.en else 0], tw, 7, color="mut", most=1, sans=True)
        y2 += b.write(tx, y2, x["name"] + (f" ×{x['n']}" if x["n"] > 1 else ""), tw, 9.6, True, color=col if b.farbe else "fg", most=2)
        b.write(tx, y2, text(x), tw, 7.8, most=3 if kurz else 9)
        b.draw("line", 0.25)
        b.doc.line(xx, yy + h + 1, xx + w, yy + h + 1)
    b.grid(items, cols, mh, dd)


def _chronik(b, data):
    b.start("chronik", _t(b, "Chronik der Begegnungen", "Chronicle of encounters"),
            _t(b, "Wann, mit wem und gegen was – neueste zuerst", "When, with whom and against what – newest first"))
    cw = b.x1 - b.x0
    gs = data["chronik"]
    if not gs:
        b.y += b.write(b.x0, b.y, _t(b, "Die Chronik füllt sich ab dem nächsten Abend am Tisch: jedes Ende einer Runde, jedes Kapitel, jeder Sieg und jede Begegnung.",
                                     "The chronicle fills from the next evening at the table: every end of a round, every chapter, every win and every meeting."),
                       cw, 9.4, color="mut") + 3
        rest = []
        if data["bestien"]:
            rest.append(_t(b, f"Bisher besiegt: {len(data['bestien'])} Arten in {data['siege']} Siegen.",
                           f"Defeated so far: {len(data['bestien'])} kinds in {data['siege']} wins."))
        if data["personen"]:
            rest.append(_t(b, f"Bisher getroffen: {len(data['personen'])} Personen.", f"Met so far: {len(data['personen'])} people."))
        if data["narben"]:
            rest.append(_t(b, f"Narben: {len(data['narben'])}.", f"Scars: {len(data['narben'])}."))
        for x in rest:
            b.y += b.write(b.x0, b.y, x, cw, 9.4) + 1
        return
    lx = b.x0 + 3.2
    for g in gs:
        head = _t(b, f"Kapitel {g['k']}", f"Chapter {g['k']}") + ("" if g["zu"] else _t(b, " · läuft", " · running"))
        ab = g["abende"]
        sub = (_t(b, "Abend ", "Evening ") + (f"{ab[0]}–{ab[-1]}" if len(ab) > 1 else str(ab[0])) + " · " if ab else "") + \
            time.strftime("%d.%m.%Y", time.localtime(g["t"][0])) + \
            ("–" + time.strftime("%d.%m.%Y", time.localtime(g["t"][1])) if time.strftime("%x", time.localtime(g["t"][0])) != time.strftime("%x", time.localtime(g["t"][1])) else "") + \
            (f" · {g['welt']}" if g["welt"] else "")
        mit = (_t(b, "mit ", "with ") + " · ".join(f"{m['name']} ({m['volk']}, {m['klasse']})" for m in g["mit"])) if g["mit"] else ""
        hh = 8 + b.height(sub, cw - 9, 8.4, most=2) + (b.height(mit, cw - 9, 8.4, most=3) if mit else 0)
        b.need(hh + 12, *b.weiter)
        y = b.y
        b.fill("weinrot" if b.farbe else "tinte")
        b.doc.ellipse(lx - 3.2, y, 6.4, 6.4, style="F")
        b.font(9, True, "paper")
        b.doc.set_xy(lx - 3.2, y + 0.9)
        b.doc.cell(6.4, 4.6, str(g["k"]), align="C")
        b.caps(b.x0 + 9, y + 4.6, head, 12, "tinte")
        yy = y + 7
        yy += b.write(b.x0 + 9, yy, sub, cw - 9, 8.4, color="mut", most=2)
        if mit:
            yy += b.write(b.x0 + 9, yy, mit, cw - 9, 8.4, most=3)
        b.y = yy + 2
        evs = g["ereignisse"]
        if not evs:
            b.y += b.write(b.x0 + 9, b.y, _t(b, "Keine Kämpfe und Begegnungen notiert.", "No fights and meetings noted."), cw - 9, 8.4, color="mut") + 2
        for e in evs:
            if e["a"] == "kampf":
                ic, col, t1 = "kampf", "rot", _t(b, f"Kampf: {e['n']}× {e['name']}", f"Fight: {e['n']}× {e['name']}")
                t2 = _t(b, "besiegt", "defeated")
            elif e["a"] == "person":
                ic, col, t1 = "maske", "violett", e["name"]
                t2 = " · ".join(x for x in (e.get("beruf"), _t(b, f"{e['n']}× getroffen", f"met {e['n']}×")) if x)
            else:
                ic, col, t1 = "stern", "gold", _t(b, f"Stufe {e['s']} erreicht", f"Level {e['s']} reached")
                t2 = ""
            h = 3 + b.height(t1, cw - 21, 9.6, True, 2) + (b.height(t2, cw - 21, 8, most=2) if t2 else 0)
            h = max(h, 9)
            b.need(h + 1.4, *b.weiter)
            b.draw("tinte", 0.6)
            b.doc.line(lx, b.y - 1.4, lx, b.y + h + 0.4)
            b.doc.line(lx, b.y + h / 2, b.x0 + 9, b.y + h / 2)
            b.draw(col if b.farbe else "tinte", 0.45 if e["a"] != "kampf" else 0.8)
            b.rrect(b.x0 + 9, b.y, cw - 9, h, "D", 1.6)
            b.icon(ic, b.x0 + 11, b.y + (h - 5.4) / 2, 5.4, col)
            inner = b.height(t1, cw - 21, 9.6, True, 2) + (b.height(t2, cw - 21, 8, most=2) if t2 else 0)
            yy = b.y + (h - inner) / 2
            yy += b.write(b.x0 + 19, yy, t1, cw - 21, 9.6, True, most=2)
            if t2:
                b.write(b.x0 + 19, yy, t2, cw - 21, 8, color="mut", most=2)
            b.y += h + 1.6
        if g["mehr"]:
            b.y += b.write(b.x0 + 9, b.y, _t(b, f"… und {g['mehr']} weitere", f"… and {g['mehr']} more"), cw - 9, 8.4, color="mut") + 1
        b.y += 2.4


def _personen(b, data):
    b.start("personen", _t(b, "Personen", "People"),
            _t(b, f"Wer {data['held']['name']} begegnet ist · je öfter, desto mehr steht hier",
               f"Who {data['held']['name']} met · the more often, the more is written here"))
    cw = b.x1 - b.x0
    ps = data["personen"]
    if ps is None:
        b.y += b.write(b.x0, b.y, _t(b, "Die Album-Seite „Personen“ ist aus (Funktionen → KI-Dungeon-Master → Personen-Katalog).",
                                     "The album page „People“ is off (Features → AI Dungeon Master → People catalog)."), cw, 9.4, color="mut")
        return
    b.y += b.write(b.x0, b.y, _t(b, f"{len(ps)} von {data['personen_alle']} Personen der Welt bekannt.",
                                 f"{len(ps)} of {data['personen_alle']} people of the world known."), cw, 8.6, color="mut") + 2
    if not ps:
        b.y += b.write(b.x0, b.y, _t(b, "Noch niemand getroffen.", "Nobody met yet."), cw, 9.4, color="mut")
    P = b.L["bild"] * 0.55

    def felder(x):
        z = []
        if x.get("welt"):
            z.append((_t(b, "Welt", "World"), x["welt"]))
        if x.get("aussehen"):
            z.append((_t(b, "Aussehen", "Looks"), x["aussehen"]))
        z.append((_t(b, "Beruf", "Occupation"), x["beruf"]) if x.get("beruf") else (_t(b, "Beruf", "Occupation"), _t(b, "ab 2 Treffen", "from 2 meetings")))
        if x.get("art"):
            z.append((_t(b, "Art", "Manner"), x["art"]))
        if x.get("wesen"):
            z.append((_t(b, "Wesen", "Traits"), ", ".join(x["wesen"])))
        z.append((_t(b, "Haltung", "Attitude"), x["haltung"]) if x.get("haltung") else (_t(b, "Haltung", "Attitude"), _t(b, "ab 4 Treffen", "from 4 meetings")))
        return [f"{k}: {v}" for k, v in z]

    def ph(x, w):
        tw = w - P - 5
        return max(P * 1.15 + 9, 3 + b.height(x["name"], tw, 10.4, True, 2) + sum(b.height(f, tw, 8, most=3) for f in felder(x)) + 7)

    def pd(x, xx, yy, w, h):
        b.draw("violett" if b.farbe else "tinte", 0.6)
        b.rrect(xx, yy, w, h, "D", 2)
        b.bild(x.get("bild", ""), xx + 2, yy + 2, P, P * 1.15, "maske", "violett")
        tx, tw = xx + P + 4, w - P - 5
        y2 = yy + 2
        y2 += b.write(tx, y2, x["name"], tw, 10.4, True, most=2)
        for f in felder(x):
            y2 += b.write(tx, y2, f, tw, 8, most=3)
        lab = _t(b, f"{x['treffen']}× getroffen", f"met {x['treffen']}×")
        b.write(xx + 2, yy + h - 4.6, lab, w - 14, 7.6, color="mut", most=1, align="R")
        b.dots(xx + w - 10.5, yy + h - 4.4, x["stufe"], color="violett" if b.farbe else "tinte")
    b.grid(ps, 2 if b.m["key"] != "move" else 1, ph, pd)
    leg = _t(b, "Ein Punkt je Stufe: 1. Treffen Name, Gesicht, Aussehen, Welt · 2. Treffen Beruf und Art · 4. Treffen Wesen und Haltung. Wunsch und Geheimnis stehen nie im Buch.",
             "One dot per stage: 1st meeting name, face, looks, world · 2nd meeting occupation and manner · 4th meeting traits and attitude. Wish and secret are never in the book.")
    b.need(b.height(leg, cw, 7.6) + 1, *b.weiter)
    b.y += b.write(b.x0, b.y, leg, cw, 7.6, color="mut")


def _bestien(b, data):
    b.start("bestien", _t(b, "Bestiarium", "Bestiary"),
            _t(b, "Je öfter besiegt, desto mehr verrät das Album", "The more often defeated, the more the album tells"))
    cw = b.x1 - b.x0
    if not data["album"]:
        b.y += b.write(b.x0, b.y, _t(b, "Das Monster-Album ist aus (Funktionen → KI-Dungeon-Master → Monster-Album).",
                                     "The monster album is off (Features → AI Dungeon Master → Monster album)."), cw, 9.4, color="mut")
        return
    bs = data["bestien"]
    b.y += b.write(b.x0, b.y, _t(b, f"{len(bs)} Arten von {data['bestien_alle']} · {data['siege']} Siege",
                                 f"{len(bs)} kinds of {data['bestien_alle']} · {data['siege']} wins"), cw, 8.6, color="mut") + 2
    if not bs:
        b.y += b.write(b.x0, b.y, _t(b, "Noch kein Gegner besiegt.", "No foe defeated yet."), cw, 9.4, color="mut")
    P = b.L["bild"] * 0.55

    def cr(v):
        return {0.125: "1/8", 0.25: "1/4", 0.5: "1/2"}.get(v, str(v).removesuffix(".0"))

    def zeilen(x):
        z = []
        if x.get("info"):
            z.append(x["info"])
        if x.get("sage"):
            z.append("„" + x["sage"] + "“")
        if x["stufe"] >= 3:
            for k, de, en in (("schwaeche", "Verwundbar", "Vulnerable"), ("resistenz", "Widersteht", "Resists"), ("immun", "Immun", "Immune")):
                if x.get(k):
                    z.append(f"{_t(b, de, en)}: {', '.join(x[k])}")
            if x.get("zustaende"):
                z.append(_t(b, "Bewirkt: ", "Causes: ") + ", ".join(x["zustaende"]))
        else:
            z.append(_t(b, f"\U0001f512 Schwächen und Zustände: nach {max(0, 5 - x['siege'])} weiteren Siegen",
                        f"\U0001f512 Weaknesses and states: after {max(0, 5 - x['siege'])} more wins"))
        return z

    def kopf(x):
        if x.get("werte"):
            v = x["werte"]
            return _t(b, f"Leben {v['leben']} · RK {v['rk']} · Angriff +{v['angriff']} · Schaden {v['schaden']} · Herausforderung {cr(v['stufe'])}",
                      f"Life {v['leben']} · AC {v['rk']} · attack +{v['angriff']} · damage {v['schaden']} · challenge {cr(v['stufe'])}")
        return _t(b, f"\U0001f512 Werte: nach {max(0, 3 - x['siege'])} weiteren Siegen", f"\U0001f512 Values: after {max(0, 3 - x['siege'])} more wins")

    def zeile(z, x, y, w, draw=True):
        if z.startswith("\U0001f512"):
            if draw:
                b.icon("schloss", x, y + 0.5, 2.8, "mut")
                return b.write(x + 3.6, y, z[2:], w - 3.6, 8, color="mut", most=4)
            return b.height(z[2:], w - 3.6, 8, most=4)
        return b.write(x, y, z, w, 8, most=4) if draw else b.height(z, w, 8, most=4)

    def bh(x, w):
        tw = w - P - 7
        top = b.height(x["name"], tw - 11, 10.4, True, 2) + 4.6 + zeile(kopf(x), 0, 0, tw, False)
        return 4 + max(P, top) + 1.5 + sum(zeile(z, 0, 0, w - 4, False) for z in zeilen(x)) + 1

    def bd(x, xx, yy, w, h):
        b.draw("rot" if b.farbe else "tinte", 0.6)
        b.rrect(xx, yy, w, h, "D", 2)
        b.bild(x.get("bild", ""), xx + 2, yy + 2, P, P, "kralle", "rot")
        tx, tw = xx + P + 4.5, w - P - 7
        y2 = yy + 2
        y2 += b.write(tx, y2, x["name"], tw - 11, 10.4, True, most=2)
        b.dots(xx + w - 10.5, yy + 2.6, x["stufe"], color="rot" if b.farbe else "tinte")
        y2 += b.write(tx, y2 + 0.3, _t(b, f"{x['siege']}× besiegt", f"defeated {x['siege']}×"), tw, 7.6, color="mut", most=1) + 0.6
        y2 += zeile(kopf(x), tx, y2, tw)
        y2 = max(y2, yy + 2 + P) + 1.5
        for z in zeilen(x):
            y2 += zeile(z, xx + 2, y2, w - 4)
    b.grid(bs, 2 if b.m["key"] != "move" else 1, bh, bd)
    leg = _t(b, "Ein Punkt je Stufe: 1. Sieg Bild und Sage · 3. Sieg Werte · 5. Sieg Schwächen und Zustände",
             "One dot per stage: 1st win picture and saying · 3rd win values · 5th win weaknesses and states")
    b.need(b.height(leg, cw, 7.6) + 1, *b.weiter)
    b.y += b.write(b.x0, b.y, leg, cw, 7.6, color="mut")


def _dinge(b, data):
    b.start("dinge", _t(b, "Gegenstände", "Items"), _t(b, "Was der Held trägt und bei sich hat", "What the hero wears and carries"))
    cols = 2 if b.m["key"] != "move" else 1
    if data["an"]:
        b.head(_t(b, "Angelegt", "Worn"))
        _ding_zeilen(b, data["an"], cols)
    b.head(_t(b, "Tasche", "Bag"))
    if data["tasche"]:
        _ding_zeilen(b, data["tasche"], cols)
    else:
        b.y += b.write(b.x0, b.y, _t(b, "Die Tasche ist leer.", "The bag is empty."), b.x1 - b.x0, 9, color="mut")


def render(dm, data, m, farbe, ausgabe=1, neue=(), stand="", seiten=None):
    """The book's PDF: (bytes, Buch). Pages of the parts are known only after a first run: the contents page takes
    them from seiten (render twice)."""
    titel = ("Heldenbuch – " if data["lang"] != "en" else "Hero book – ") + data["held"]["name"]
    b = Buch(dm, m, farbe, data["lang"], titel, seiten)
    b.stand = stand
    _inhalt(b, data, ausgabe, list(neue))
    b.seiten = dict(b.seiten)
    for part in (_held, _chronik, _personen, _bestien, _dinge):
        part(b, data)
    return b.finish(), b


def build(dm, data, m, farbe, ausgabe=1, neue=(), now=None):
    """Both runs: the second with the parts' pages on the contents page."""
    now = time.time() if now is None else now
    en = data["lang"] == "en"
    stand = (f"Ausgabe {ausgabe} · " if not en else f"Edition {ausgabe} · ") + time.strftime("%d.%m.%Y", time.localtime(now))
    _, first = render(dm, data, m, farbe, ausgabe, neue, stand)
    return render(dm, data, m, farbe, ausgabe, neue, stand, seiten=first.seiten)


def notizen(dm, data, m, farbe):
    """„Notizen – <Held>“: a lined page per part with tabs that jump between them; sent once, never replaced."""
    b = Buch(dm, m, farbe, data["lang"], ("Notizen – " if data["lang"] != "en" else "Notes – ") + data["held"]["name"])
    for i, t in enumerate(TEILE):
        b.teil = t[0]
        b.page(_t(b, "Notizen · ", "Notes · ") + (t[2] if b.en else t[1]), data["held"]["name"])
        b.doc.set_link(b.links[t[0]], page=b.doc.page)
        b.doc.start_section(b.tx(t[2] if b.en else t[1]))
        b.draw("line", 0.25)
        pitch = 8.0
        y = b.y + pitch
        while y < b.y1 - 1:
            b.doc.line(b.x0, y, b.x1, y)
            y += pitch
    return b.finish()


# ---------------------------------------------------------------- making and sending
class ZuGross(ValueError):
    """The book is larger than the reMarkable takes (remarkable.MAX_FILE)."""


def _hero(dm, uid, hid):
    if not _HID.fullmatch(str(hid)):
        raise LookupError("held")
    h = next((x for x in dm.heroes(uid) if x["hid"] == hid), None)
    if not h:
        raise LookupError("held")
    return h


def _model(uid):
    import rmpapier
    return rmpapier.model_of(uid)


def make(uid, hid, lang="de", now=None):
    """(pdf, data, info) for the profile's own hero, in the profile's device format and colour."""
    import dungeon as dm
    h = _hero(dm, uid, hid)
    m = _model(uid)
    data = inhalt(dm, uid, h, lang)
    st = _state(uid)["buecher"].get(hid) or {}
    fp = fingerprint({k: v for k, v in data.items() if k != "z"}, m)
    ausgabe = int(st.get("ausgabe") or 0) + (0 if st.get("fp") == fp else 1) or 1
    pdf, b = build(dm, data, m, True, ausgabe, neu(data, st.get("z")), now)
    import remarkable
    if len(pdf) > remarkable.MAX_FILE:
        raise ZuGross()
    return pdf, data, {"seiten": b.doc.page, "bilder": b.bilder, "fp": fp, "ausgabe": ausgabe, "m": m, "overflow": b.overflow}


async def senden(uid, hid, auto=False, now=None):
    """The book onto the reMarkable (the same document while it has no handwriting, remarkable.place), the notes once.
    Returns a fixed word: gesendet, unveraendert, aus, kein_geraet, limit, fehler."""
    import remarkable
    now = time.time() if now is None else now
    if not on(uid):
        print("dungeon: buch | uebersprungen | aus", flush=True)
        return "aus"
    if not connected(uid):
        print("dungeon: buch | uebersprungen | kein_geraet", flush=True)
        return "kein_geraet"
    lang = "en" if profiles.settings(uid).get("lang") == "en" else "de"
    try:
        pdf, data, info = await asyncio.to_thread(make, uid, hid, lang, now)
    except LookupError:
        print("dungeon: buch | uebersprungen | kein_held", flush=True)
        return "kein_held"
    except ZuGross:
        _day.bump("abgelehnt")
        print("dungeon: buch | uebersprungen | gross", flush=True)
        return "fehler"
    st = _state(uid)
    alt = st["buecher"].get(hid) or {}
    if auto and alt.get("fp") == info["fp"]:
        st["warte"].pop(hid, None)
        _save(uid, st)
        _day.bump("unveraendert")
        print("dungeon: buch | uebersprungen | unveraendert", flush=True)
        return "unveraendert"
    titel = ("Heldenbuch – " if lang != "en" else "Hero book – ") + data["held"]["name"]
    t0 = time.time()
    try:
        await remarkable.place(uid, titel, pdf, "pdf", own=f"dungeonbuch:{hid}", auto=auto)
    except ValueError as e:
        why = "limit" if "heute" in str(e) else "gross" if "groß" in str(e) else "eingabe"
        _day.bump("abgelehnt")
        print(f"dungeon: buch | uebersprungen | {why}", flush=True)
        return "limit" if why == "limit" else "fehler"
    except Exception as e:
        _day.bump("fehler")
        print(f"dungeon: buch | fehler | {type(e).__name__}", flush=True)
        _live_job(uid, t0, False)
        return "fehler"
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    st = _state(uid)
    b = st["buecher"].get(hid) or {}
    st["buecher"][hid] = {"fp": info["fp"], "ausgabe": info["ausgabe"], "t": int(now), "z": data["z"],
                          "tag": day, "n": (b.get("n", 0) if b.get("tag") == day else 0) + (1 if auto else 0),
                          "seiten": info["seiten"]}
    st["warte"].pop(hid, None)
    _save(uid, st)
    _day.bump("gesendet")
    _live_job(uid, t0, True)
    print(f"dungeon: buch | gesendet | seiten {info['seiten']} | bilder {info['bilder']} | {'auto' if auto else 'knopf'}", flush=True)
    if hid not in st["notizen"]:
        try:
            m = info["m"]
            import dungeon as dm
            nb = await asyncio.to_thread(notizen, dm, data, m, True)
            await remarkable.place(uid, ("Notizen – " if lang != "en" else "Notes – ") + data["held"]["name"], nb, "pdf",
                                   auto=auto)
            st = _state(uid)
            st["notizen"][hid] = int(now)
            _save(uid, st)
            _day.bump("notizen")
            print("dungeon: buch | notizen | gesendet", flush=True)
        except Exception as e:
            print(f"dungeon: buch | notizen | fehler {type(e).__name__}", flush=True)
    return "gesendet"


def _live_job(uid, t0, ok):
    try:
        import live
        live.job("Heldenbuch", "reMarkable", t0, ok=ok, uid=uid)
    except Exception:
        pass


def due(uid, now):
    """The heroes whose book is due: queued, the time come, not yet AUTO_TAG automatic books today."""
    st = _state(uid)
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    out = []
    for hid, t in st["warte"].items():
        b = st["buecher"].get(hid) or {}
        if isinstance(t, int) and t <= now and not (b.get("tag") == day and b.get("n", 0) >= AUTO_TAG):
            out.append(hid)
    return out


async def due_once(idle=True, now=None, uids=None):
    """Each minute (panel.remarkable_sync): at most one book, only in a quiet minute. Returns the word or None."""
    if not idle or not features.admin_on(KEY):
        return None
    now = time.time() if now is None else now
    for uid in uids or profiles.user_ids():
        if not os.path.exists(_file(uid)):
            continue
        if not on(uid):
            continue
        for hid in due(uid, now):
            try:
                import live
                live.bg("Dungeon: Heldenbuch", "run")
            except Exception:
                pass
            t0 = time.time()
            word = await senden(uid, hid, auto=True, now=now)
            try:
                import live
                live.bg_done("Dungeon: Heldenbuch", word in ("gesendet", "unveraendert"), time.time() - t0, word)
            except Exception:
                pass
            if word in ("aus", "kein_geraet", "kein_held", "limit", "fehler"):
                st = _state(uid)
                if word == "kein_held":
                    st["warte"].pop(hid, None)
                else:      # tomorrow again, never every minute
                    st["warte"][hid] = int(now + 86400)
                _save(uid, st)
            return word
    return None


def public(uid):
    """For the page: per own hero its edition, when it went, whether it waits; the device's format and colour."""
    import dungeon as dm
    import rmpapier
    st = _state(uid)
    m = rmpapier.model_of(uid)
    out = []
    for h in dm.heroes(uid):
        b = st["buecher"].get(h["hid"]) or {}
        out.append({"hid": h["hid"], "name": h["name"], "ausgabe": b.get("ausgabe", 0), "t": b.get("t", 0),
                    "seiten": b.get("seiten", 0), "wartet": st["warte"].get(h["hid"], 0), "notizen": h["hid"] in st["notizen"]})
    return {"on": on(uid), "admin": features.admin_on(KEY), "verbunden": connected(uid) if on(uid) else False,
            "fehlt": features.missing_text(KEY, uid) if not on(uid) else "", "modell": m["key"], "farbe": bool(m["color"]),
            "helden": out}


def for_live():
    """Numbers only: books sent, unchanged, refused, failed, previews and notes today, profiles waiting."""
    return dict(_day.counts())


# ---------------------------------------------------------------- routes
def _need(uid):
    import dungeon as dm
    dm._need(uid)
    if not on(uid):
        _day.bump("abgelehnt")
        print("dungeon: buch | abgelehnt | aus", flush=True)
        raise HTTPException(403, features.missing_text(KEY, uid) or "aus")


@router.get("/api/profile/dungeon/buch", dependencies=[Depends(assistant)])
async def buch_info(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)
    import dungeon as dm
    dm._need(uid)
    out = await asyncio.to_thread(public, uid)
    print(f"dungeon: buch | ansehen | {len(out['helden'])} helden", flush=True)
    return out


@router.get("/api/profile/dungeon/buch/{hid}.pdf", dependencies=[Depends(assistant)])
async def buch_pdf(hid: str, request: Request, prof=Depends(own_profile)):
    """The book as the reMarkable would get it (preview), made on the Spark."""
    uid = prof["id"]
    guard.limit(request, "dungeonpdf", uid)
    _need(uid)
    lang = "en" if request.query_params.get("lang") == "en" else "de"
    try:
        pdf, _, info = await asyncio.to_thread(make, uid, hid, lang)
    except (LookupError, ValueError) as e:
        _day.bump("abgelehnt")
        print(f"dungeon: buch | abgelehnt | {type(e).__name__}", flush=True)
        raise HTTPException(404, "held")
    _day.bump("vorschau")
    print(f"dungeon: buch | vorschau | seiten {info['seiten']}", flush=True)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="heldenbuch.pdf"',
                                                                "Cache-Control": "no-store"})


@router.post("/api/profile/dungeon/buch/{hid}/senden", dependencies=[Depends(assistant)])
async def buch_senden(hid: str, request: Request, prof=Depends(browser_profile)):
    """„Jetzt schicken“: the book now (the reMarkable's daily limit for sending counts), the notes once."""
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)
    await json_body(request, BODY, lenient=True)
    _need(uid)
    import dungeon as dm
    try:
        _hero(dm, uid, hid)
    except LookupError:
        _day.bump("abgelehnt")
        print("dungeon: buch | abgelehnt | held", flush=True)
        raise HTTPException(404, "held")
    if not connected(uid):
        print("dungeon: buch | abgelehnt | kein_geraet", flush=True)
        raise HTTPException(409, "kein_geraet")
    word = await senden(uid, hid)
    if word != "gesendet":
        raise HTTPException(429 if word == "limit" else 502, word)
    return await asyncio.to_thread(public, uid)


async def sheet(uid):
    """rmplus „Schick mein Heldenbuch aufs reMarkable“: the book of the hero played last. A sentence."""
    import dungeon as dm
    hs = dm.heroes(uid)
    if not hs:
        return "Du hast noch keinen Helden."
    h = max(hs, key=lambda x: max([e["t"] for e in x.get("chronik") or []] or [0]))
    word = await senden(uid, h["hid"])
    return {"gesendet": f"Das Heldenbuch von {h['name']} liegt jetzt auf deinem reMarkable.",
            "kein_geraet": "Nicht geschickt: kein reMarkable verbunden.",
            "limit": "Nicht geschickt: heute schon zu oft aufs reMarkable geschickt.",
            "aus": "Nicht geschickt: das Heldenbuch ist aus."}.get(word, "Nicht geschickt: Fehler beim Schicken.")
