"""KI-Dungeon-Master: Bilder für Ausrüstung und Zauber (plan dungeon-master/plan.md „5i“, Dominik 2026-10-23 „2“ and
„die Bildgeneration, aber auch startbar per Knopf direkt“). Builds on the game (dungeon.py) and on „Bilder malen“
(bilder.py); the function dungeonbilder (features.py, admin switch chat.dungeon_bilder, off) and the admin's
„Bilder malen“ must be on, else every item keeps its sign (ZEICHEN) and nothing is painted.

Two kinds of pictures, both painted by the fixed rules of the panel (the model chooses nothing):
- the catalog: one picture per entry of dungeon_regeln.json (weapons, armour, jewellery, potions, spells, scrolls,
  the admin's own entries too) in the fixed style of each world (dungeon.style: welten[].bildstil) and in the
  picture book style for the youngest tone while a round of that tone is open. The prompt is built from the
  catalog's English name and a fixed phrase per kind (ART_EN), checked like a picture wish (bilder.refuse_text);
  its hash names the file, so a changed style or name paints anew and the old file goes with the sweep. Painted
  in the night window NACHT (local time) and when the admin presses „Bilder jetzt erstellen“, one at a time
  through the heavy jobs' queue (schwer.py via dungeon._paint: the voice first, Wartungspause „bild“), at most
  TAG_MAX a day, the run stops on Notaus, a missing model or check, a closed switch, and „Anhalten“.
- a find: a named item of a round (the model's name, dungeon.loot) of at least rarity RANG_FUND gets its own
  picture once it is known (unknown magic only after naming), from the style of the round, the catalog's English
  name and the model's name and sentence, checked by dungeon.picture_text (tone, „nie“, taboos, word list, people);
  it counts to the game's day limit (dungeon._bild_take, grenzen.bilder_tag) and needs „Bilder malen“ of the host.
  Found by the minute loop (due), so the game's turn is never held up.

The map (dungeon_karte.py) adds its kinds of places and rooms to the catalog (wanted, painted alike) and an own
picture of every visited place (ort-<hash>, dungeon_karte.queue_orte from due, shown only to seats of its round).
The Bestiarium (dungeon.gegner) is painted alike, with its own fixed phrase FOE_EN, in the style of the worlds a foe
belongs to. On the admin's tab „Regeln“ (dungeon_regelseite.py) „Nochmal malen“ paints one entry again as a candidate
neu-<hash> next to the picture in use (repaint, the same checks and day limit); „Neues behalten“ or „Altes behalten“
settles it, a candidate nobody settles goes with the sweep after NEU_S.

Every picture: FLUX through bilder.paint (NSFW above the limit and a missing check give no picture), the AI marks of
the service kept (bilder.quick_png „kleiner“: SIZE/2), stored as STATE/dungeon-bild/ding-<hash>.png or
fund-<iid>.png next to the scene pictures. Seats see it through view() (add: "bild" and "zeichen" on every item, a
copy); a profile loads it by GET /api/profile/dungeon/ding/<name>, a guest's seat by POST /api/dungeon/ding with its
code. Journal lines „dungeon: dingbild | …“, fixed words and numbers only; Live: dungeon's line, numbers only.

    GET    /api/profile/dungeon/ding/{name}     a picture of an item (the game released for the profile)
    POST   /api/dungeon/ding                    {code, name}: the same for a guest's seat
    GET    /api/admin/dungeon/dingbilder        how far the pictures are (status)
    POST   /api/admin/dungeon/dingbilder        „Bilder jetzt erstellen“: the run starts now, not only at night
    DELETE /api/admin/dungeon/dingbilder        „Anhalten“: the run stops after the picture on its way
"""
import asyncio
import datetime
import hashlib
import os
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_karte
import features
import guard
import profiles
from common import STATE, DayCounter, read_json, write_json
from core import assistant, auth, own_profile, spawn

router = APIRouter()
KEY = "dungeonbilder"
FILE = os.path.join(STATE, "dungeon-dingbilder.json")
SIZE = 512                # painted square, kept at half (bilder.quick_png „kleiner“)
NACHT = (1, 5)            # the night window, local hours [from, to)
TAG_MAX = 300             # catalog pictures asked for a day on the whole Spark
RANG_FUND = 2             # a find from „rar“ on (index in seltenheit) gets its own picture
FEHL_MAX = 2              # a catalog picture refused this often is not tried again (until its prompt changes)
FUNDE_MAX = 2000          # finds the state file remembers
STOP = ("missing", "ohne_pruefung", "dienst", "zeit", "wartung", "memory", "belegt")   # a run ends on these
ART_EN = {"waffe": "a weapon", "ruestung": "a piece of armour", "schmuck": "a piece of jewellery",
          "trank": "a potion in a glass bottle", "zauber": "a magic spell, glowing magical energy",
          "rolle": "a rolled parchment scroll", "schatz": "a precious gem or a small work of art"}
ZEICHEN = {"waffe": "⚔️", "ruestung": "🛡️", "schmuck": "💍", "trank": "🧪", "zauber": "✨", "rolle": "📜", "schatz": "💎"}
ITEM_EN = "game item art, one single object in the centre, plain dark background"
FOE_EN = "creature art for a fantasy bestiary, the whole creature in the centre, plain dark background"   # the Bestiarium (gegner)
NEU = re.compile(r"neu-[0-9a-f]{16}")   # a picture painted again on the admin's „Nochmal malen“, next to the one in use
NEU_S = 86400             # a candidate nobody kept or dropped goes with the sweep after a day
NAME = re.compile(r"ding-[0-9a-f]{16}|fund-i[0-9a-f]{8}|ort-[0-9a-f]{16}")   # ort-: a place of the map (dungeon_karte)
_lauf = {"task": None, "grund": "", "start": 0.0, "gemalt": 0, "stop": False}
_funde = set()            # iids of finds being painted right now
_files = {"m": None, "set": frozenset()}
_sweep = [0.0]
_day = DayCounter(gemalt=0, verworfen=0, ausgefallen=0, funde=0)
clock = time.time        # the one clock of this module (the tests set it, nothing here reads the wall clock else)


def on():
    """The Spark allows it: the game's pictures switch (with the game) and the admin's „Bilder malen“."""
    import bilder
    return features.admin_on(KEY) and features.admin_on(bilder.KEY)


def _state():
    d = read_json(FILE, {})
    for k in ("tag", "fehl", "funde", "letzter"):
        if not isinstance(d.get(k), dict):
            d[k] = {}
    return d


def _save(d):
    if len(d.get("funde") or {}) > FUNDE_MAX:
        d["funde"] = dict(list(d["funde"].items())[-FUNDE_MAX:])
    write_json(FILE, d, mode=0o600, dir_mode=0o700)


def _date():
    return DayCounter.date(clock())


def _today(d):
    t = d["tag"]
    return t.get("n", 0) if t.get("day") == _date() else 0


def files():
    """The names of the item pictures there are (the folder read again only when it changed)."""
    try:
        m = os.stat(dungeon.BILD_DIR).st_mtime_ns
    except FileNotFoundError:
        return frozenset()
    if m != _files["m"]:
        names = os.listdir(dungeon.BILD_DIR)
        _files.update(m=m, set=frozenset(f[:-4] for f in names if f.endswith(".png") and NAME.fullmatch(f[:-4])))
    return _files["set"]


# ---------------------------------------------------------------- the catalog's pictures
def styles(r):
    """The styles to paint in: every world's (dungeon.style), the picture book only while a round of the youngest
    tone is open. Worlds of open rounds first."""
    jung = min(t["id"] for t in r["toene"])
    rs = [v for v in dungeon._read()["runden"].values() if v.get("status") != "ende"]
    used = [v.get("welt") for v in rs]
    welten = sorted(r["welten"], key=lambda w: (w["id"] not in used, r["welten"].index(w)))
    out = []
    for w in welten:
        s = dungeon.style(r, {"welt": w["id"], "ton": None})
        if s not in out:
            out.append(s)
    if any(v.get("ton") == jung for v in rs):
        out.append(dungeon.BILD_KIND)
    return out


def prompt(style, c):
    """The fixed prompt of a catalog entry in a style: the English name, the kind's phrase, a spell's sentence; a foe
    of the Bestiarium (no "art") its own fixed phrase."""
    if "art" not in c:
        return f"{style}, {FOE_EN}: {c['name'][1]}, {dungeon.BILD_ENDE}"
    extra = f", {c['satz'][1]}" if c["art"] == "zauber" and c.get("satz") else ""
    return f"{style}, {ITEM_EN}: {c['name'][1]}, {ART_EN[c['art']]}{extra}, {dungeon.BILD_ENDE}"


def name_of(p):
    return "ding-" + hashlib.sha256(p.encode()).hexdigest()[:16]


def wanted(r):
    """[(name, prompt)] of every catalog picture there should be, in painting order (style by style): the items,
    then the map's kinds of places and rooms (dungeon_karte.bilder), then the foes of that world (dungeon.gegner)."""
    out, seen = [], set()
    for s in styles(r):
        welten = {w["id"] for w in r["welten"] if dungeon.style(r, {"welt": w["id"], "ton": None}) == s} or {w["id"] for w in r["welten"]}
        foes = [c for c in r.get("gegner") or [] if "alle" in c.get("welten", ["alle"]) or welten & set(c.get("welten") or [])]
        for n, p in [(name_of(prompt(s, c)), prompt(s, c)) for c in r["gegenstaende"]] + dungeon_karte.bilder(r, s) + \
                [(name_of(prompt(s, c)), prompt(s, c)) for c in foes]:
            if n not in seen:
                seen.add(n)
                out.append((n, p))
    return out


def _ok_text(p):
    """A catalog prompt passes the picture rules (the admin's entries are data too)."""
    import bilder
    return not bilder.refuse_text("", p)


def missing(r, d=None):
    d = _state() if d is None else d
    have = files()
    return [(n, p) for n, p in wanted(r) if n not in have and d["fehl"].get(n, 0) < FEHL_MAX]


def _night(now):
    h = datetime.datetime.fromtimestamp(now).hour
    return NACHT[0] <= h < NACHT[1]


def start(grund):
    """Starts a run (grund "nacht" or "knopf") unless one runs; returns False when it cannot (off or running)."""
    if not on() or (_lauf["task"] and not _lauf["task"].done()):
        return False
    _lauf.update(grund=grund, start=clock(), gemalt=0, stop=False)
    _lauf["task"] = spawn(_run(grund), name="dungeon-dingbild")
    print(f"dungeon: dingbild | lauf start | {grund}", flush=True)
    return True


def stop():
    if _lauf["task"] and not _lauf["task"].done():
        _lauf["stop"] = True
        print("dungeon: dingbild | lauf anhalten", flush=True)
        return True
    return False


def _end_why(grund):
    """Why the run should end before the next picture ("" = go on)."""
    import notaus
    import schwer
    if _lauf["stop"]:
        return "angehalten"
    if not on():
        return "aus"
    if notaus.blocks("auto"):
        return "notaus"
    if grund == "nacht" and not _night(clock()):
        return "morgen"
    if _today(_state()) >= TAG_MAX:
        return "tag"
    if schwer.full():
        return "voll"
    return ""


async def paint_one(n, p):
    """One picture through the game's painter (dungeon._paint), kept at half size with its AI marks. Returns "ok"
    or the reason it did not come (dungeon.BILD_GRUENDE)."""
    import bilder
    try:
        png = await dungeon._paint(secrets.token_hex(6), p, SIZE, SIZE)
        png, _, _ = await asyncio.to_thread(bilder.quick_png, png, "kleiner")
        await asyncio.to_thread(dungeon._bild_save, n, png)
        return "ok"
    except ValueError as e:
        return dungeon._bild_why(e)
    except Exception:   # noqa: BLE001 - every picture ends with a journal line
        return "dienst"


async def _run(grund):
    why, tried = "fertig", set()          # a picture that did not come waits for the next run
    try:
        while True:
            why = await asyncio.to_thread(_end_why, grund) or "fertig"
            if why != "fertig":
                break
            r = dungeon.rules()
            todo = [x for x in await asyncio.to_thread(missing, r) if x[0] not in tried]
            if not todo:
                break
            n, p = todo[0]
            tried.add(n)
            t0 = time.perf_counter()
            res = await paint_one(n, p) if _ok_text(p) else "wortliste"

            def note():
                d = _state()
                if res != "wortliste":            # every picture asked for counts, so a refusing check cannot run on
                    d["tag"] = {"day": _date(), "n": _today(d) + 1}
                if res != "ok":
                    d["fehl"][n] = d["fehl"].get(n, 0) + (FEHL_MAX if res == "wortliste" else 1)
                _save(d)
            await asyncio.to_thread(note)
            if res == "ok":
                _lauf["gemalt"] += 1
            _day.bump("gemalt" if res == "ok" else "verworfen" if res in ("pruefung", "ohne_pruefung", "wortliste") else "ausgefallen")
            print(f"dungeon: dingbild | {res} | katalog | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
            if res in STOP:
                why = res
                break
    finally:
        def last():
            d = _state()
            d["letzter"] = {"grund": grund, "start": _lauf["start"], "ende": clock(), "gemalt": _lauf["gemalt"], "warum": why}
            if grund == "nacht":
                d["nacht"] = _date()
            _save(d)
        await asyncio.to_thread(last)
        print(f"dungeon: dingbild | lauf ende | {why} | {_lauf['gemalt']} gemalt", flush=True)


# ---------------------------------------------------------------- a named find's own picture
def _finds(r, rd):
    """The named items of the round's heroes and its ground that are known and rare enough."""
    rank = [x["id"] for x in r["seltenheit"]]
    items = list(rd.get("boden") or [])
    for p in rd["plaetze"].values():
        h = p.get("held") or {}
        items += [x for x in (h.get("an") or {}).values() if x] + list(h.get("tasche") or [])
    return [it for it in items if it.get("eigen") and not it.get("u") and it.get("s") in rank and rank.index(it["s"]) >= RANG_FUND
            and it.get("id") in dungeon._by(r, "gegenstaende")]


def find_prompt(r, rd, it):
    c = dungeon._by(r, "gegenstaende")[it["id"]]
    return f"{ART_EN[c['art']]}, {c['name'][1]}, a unique treasure named {it['eigen']}" + (f", {it['satz']}" if it.get("satz") else "")


def queue_finds():
    """Inside dungeon._lock: every named find without a picture, of rounds whose host has „Bilder malen“, within the
    game's day limit (dungeon._bild_take). Returns [(name, prompt)] to paint."""
    import schwer
    r = dungeon.rules()
    out = []
    with dungeon._lock:
        d = dungeon._read()
        st = _state()
        have, taken, changed = files(), False, False
        for rid, rd in d["runden"].items():
            if rd.get("status") != "laeuft" or not dungeon.pictures_on(rd["owner"]):
                continue
            for it in _finds(r, rd):
                n = "fund-" + it["i"]
                f = st["funde"].get(it["i"]) or {}
                if n in have or it["i"] in _funde or f.get("st") in ("ok", "weg") or f.get("st") == "tag" and f.get("day") == _date():
                    continue
                text, why = dungeon.picture_text(r, rd, find_prompt(r, rd, it))
                if not why and dungeon._bild_count(d) >= r["grenzen"].get("bilder_tag", dungeon.BILDER_TAG):
                    why = "tag"
                if not why and schwer.full():
                    continue
                if why:
                    st["funde"][it["i"]] = {"st": "tag" if why == "tag" else "weg", "day": _date()}
                    changed = True
                    print(f"dungeon: dingbild | abgelehnt | fund | {why}", flush=True)
                    continue
                dungeon._bild_take(d)
                taken = True
                _funde.add(it["i"])
                out.append((n, f"{dungeon.style(r, rd)}, {text}, {dungeon.BILD_ENDE}"))
        if taken:
            dungeon._write(d)
        if changed:
            _save(st)
    return out


async def paint_find(n, p):
    t0 = time.perf_counter()
    iid = n[5:]
    try:
        res = await paint_one(n, p)
    finally:
        _funde.discard(iid)

    def note():
        d = _state()
        d["funde"][iid] = {"st": "ok" if res == "ok" else "weg" if res in ("pruefung", "ohne_pruefung") else "fehler", "day": _date()}
        _save(d)
    await asyncio.to_thread(note)
    _day.bump("funde" if res == "ok" else "verworfen" if res in ("pruefung", "ohne_pruefung") else "ausgefallen")
    print(f"dungeon: dingbild | {res} | fund | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)


# ---------------------------------------------------------------- the minute loop (panel.py every_minute)
async def due():
    """Each minute: the finds, the night's run once a night, the sweep at most hourly."""
    now = clock()
    if not on():
        return
    for n, p in await asyncio.to_thread(queue_finds):
        spawn(paint_find(n, p), name="dungeon-dingbild")
    for rid, i, n, p in await asyncio.to_thread(dungeon_karte.queue_orte):
        spawn(dungeon_karte.paint_ort(rid, i, n, p), name="dungeon-dingbild")
    if _night(now) and await asyncio.to_thread(lambda: _state().get("nacht") != _date()):
        if await asyncio.to_thread(lambda: bool(missing(dungeon.rules()))):
            start("nacht")
    await asyncio.to_thread(sweep, now)


def sweep(now=None, force=False):
    """At most every hour: catalog pictures no style or entry asks for any more, finds no round, hero, Figur-Code or
    campaign keeps."""
    now = clock() if now is None else now
    if not force and now - _sweep[0] < 3600:
        return 0
    _sweep[0] = now
    r = dungeon.rules()
    keep = {n for n, _ in wanted(r)}
    iids = set()

    def held(h):
        for x in list((h or {}).get("an", {}).values()) + list((h or {}).get("tasche") or []):
            if isinstance(x, dict):
                iids.add(x.get("i"))
    d = dungeon._read()
    orte = dungeon_karte.keep(d)
    for v in d["runden"].values():
        for p in v["plaetze"].values():
            held(p.get("held"))
        iids.update(x.get("i") for x in v.get("boden") or [])
    for f in dungeon._read_fig()["figuren"].values():
        held(f.get("held"))
    for uid in profiles.user_ids():
        for h in dungeon.heroes(uid):
            held(h)
        for c in dungeon.campaigns(uid).values():
            for h in c.get("gaeste") or []:
                held(h)
    gone = 0
    for n in candidates():
        try:
            if now - os.path.getmtime(dungeon.bild_file(n)) > NEU_S:
                dungeon._bild_rm(n)
                gone += 1
        except OSError:
            pass
    for n in files():
        if n.startswith("ding-") and n not in keep or n.startswith("fund-") and n[5:] not in iids or n.startswith("ort-") and n not in orte:
            dungeon._bild_rm(n)
            gone += 1
    if gone:
        print(f"dungeon: dingbild | aufgeraeumt | {gone} bilder", flush=True)
    return gone


# ---------------------------------------------------------------- what a seat sees (dungeon.view)
def add(r, rd, out):
    """dungeon.view's last step: every item of the view (bags, slots, ground, merchant, offers, log) gets "zeichen"
    (the sign of its kind) and "bild" (the name of its picture, "" while there is none): a find's own once known,
    else the catalog's in the round's style. Items are copied, nothing of the round changes."""
    have = files() if on() else frozenset()
    style = dungeon.style(r, rd)
    cat = dungeon._by(r, "gegenstaende")

    def item(x):
        c = cat.get(x["id"])
        bild = ""
        if c and have:
            f = "fund-" + str(x.get("i"))
            bild = f if not x.get("u") and f in have else name_of(prompt(style, c))
            bild = bild if bild in have else ""
        return dict(x, zeichen=ZEICHEN.get(x.get("art"), dungeon.ZEICHEN), bild=bild)

    def walk(v):
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            w = {k: walk(x) for k, x in v.items()}
            return item(w) if {"i", "id", "art", "selten"} <= w.keys() else w
        return v
    for k in list(out):
        out[k] = walk(out[k])
    return out


# ---------------------------------------------------------------- „Nochmal malen“ (the admin's rules page)
def candidates():
    try:
        return [f[:-4] for f in os.listdir(dungeon.BILD_DIR) if f.endswith(".png") and NEU.fullmatch(f[:-4])]
    except FileNotFoundError:
        return []


def picture_of(r, c, welt=""):
    """The name of a catalog entry's picture in the style of its world (the first it belongs to, else the first
    world), and whether it is there."""
    n = name_of(prompt(dungeon.style(r, {"welt": welt or _welt(r, c), "ton": None}), c))
    return n, n in files()


def _welt(r, c):
    ws = [w for w in c.get("welten") or [] if w != "alle"]
    return ws[0] if ws else r["welten"][0]["id"]


async def repaint(r, c):
    """Paints a catalog entry's picture once more as a candidate neu-<hash> next to the one in use (the same checks
    and day limit as every catalog picture). Returns ("ok", name) or (reason, "")."""
    if not on():
        return "aus", ""
    d = _state()
    if _today(d) >= TAG_MAX:
        return "tag", ""
    n, _ = picture_of(r, c)
    p = prompt(dungeon.style(r, {"welt": _welt(r, c), "ton": None}), c)
    if not _ok_text(p):
        return "pruefung", ""
    neu = "neu-" + n[5:]
    why = await paint_one(neu, p)

    def note():
        d = _state()
        d["tag"] = {"day": _date(), "n": _today(d) + 1}
        _save(d)
    await asyncio.to_thread(note)
    print(f"dungeon: dingbild | nochmal | {why}", flush=True)
    return (why, neu if why == "ok" else "")


def settle(r, c, keep_new):
    """„Neues behalten“ puts the candidate in place of the picture, „Altes behalten“ drops it."""
    n, _ = picture_of(r, c)
    neu = "neu-" + n[5:]
    if not os.path.exists(dungeon.bild_file(neu)):
        raise LookupError("bild")
    if keep_new:
        os.replace(dungeon.bild_file(neu), dungeon.bild_file(n))
    else:
        dungeon._bild_rm(neu)
    print(f"dungeon: dingbild | nochmal | {'neu behalten' if keep_new else 'alt behalten'}", flush=True)


# ---------------------------------------------------------------- Live and the admin's page
def status(r=None):
    r = r or dungeon.rules()
    d = _state()
    w = wanted(r)
    have = files()
    return {"an": features.admin_on(KEY), "bilder": on(), "fertig": sum(1 for n, _ in w if n in have), "von": len(w),
            "abgelehnt": sum(1 for n, _ in w if d["fehl"].get(n, 0) >= FEHL_MAX and n not in have),
            "funde": sum(1 for n in have if n.startswith("fund-")), "heute": _today(d), "tag_max": TAG_MAX,
            "nacht": [f"{NACHT[0]:02d}:00", f"{NACHT[1]:02d}:00"], "stile": len(styles(r)),
            "laeuft": bool(_lauf["task"] and not _lauf["task"].done()), "grund": _lauf["grund"], "gemalt": _lauf["gemalt"],
            "letzter": d["letzter"]}


def for_live():
    """Numbers only: pictures there are, missing, painted today, refused, failed, whether a run is on."""
    if not features.admin_on(KEY):
        return {"on": False}
    t = _day.counts()
    have = files()
    return {"on": True, "da": sum(1 for n in have if n.startswith("ding-")), "funde_da": sum(1 for n in have if n.startswith("fund-")),
            "gemalt": t["gemalt"], "funde": t["funde"], "verworfen": t["verworfen"], "ausgefallen": t["ausgefallen"],
            "laeuft": bool(_lauf["task"] and not _lauf["task"].done()), "malt_funde": len(_funde)}


# ---------------------------------------------------------------- endpoints
def _png(name):
    if not NAME.fullmatch(str(name or "")):
        raise LookupError("bild")
    return dungeon._png(name)


@router.get("/api/profile/dungeon/ding/{name}", dependencies=[Depends(assistant)])
async def ding(name: str, request: Request, prof=Depends(own_profile)):
    """A picture of an item, for a profile the game is released for."""
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeonding", uid)
    try:
        if not await asyncio.to_thread(dungeon_karte.may_see, name, uid=uid):
            raise LookupError("bild")
        return dungeon._png_out(await asyncio.to_thread(_png, name))
    except LookupError as e:
        raise dungeon._http(e)


@router.post("/api/dungeon/ding")
async def gast_ding(request: Request):
    """{"code", "name"}: a picture of an item for a guest's seat."""
    b, rid, _ = await dungeon._guest(request)
    guard.limit(request, "dungeonding")
    try:
        if not await asyncio.to_thread(dungeon_karte.may_see, b.get("name"), rid=rid):
            raise LookupError("bild")
        return dungeon._png_out(await asyncio.to_thread(_png, b.get("name")))
    except LookupError as e:
        raise dungeon._http(e)


@router.get("/api/admin/dungeon/dingbilder", dependencies=[Depends(auth)])
async def admin_status():
    """How far the pictures are (the admin's page asks again every few seconds while a run is on)."""
    return await asyncio.to_thread(status)


@router.post("/api/admin/dungeon/dingbilder", dependencies=[Depends(auth)])
async def admin_start(request: Request):
    """„Bilder jetzt erstellen“: the run starts now (the same rules as at night, without the window)."""
    guard.limit(request, "dungeonding", admin=True)
    if not on():
        print("dungeon: dingbild | abgelehnt | aus", flush=True)
        raise HTTPException(409, "aus")
    if not start("knopf"):
        print("dungeon: dingbild | abgelehnt | laeuft", flush=True)
    return await asyncio.to_thread(status)


@router.delete("/api/admin/dungeon/dingbilder", dependencies=[Depends(auth)])
async def admin_stop():
    """„Anhalten“: the run ends after the picture on its way."""
    if not stop():
        print("dungeon: dingbild | anhalten | kein lauf", flush=True)
    return await asyncio.to_thread(status)
