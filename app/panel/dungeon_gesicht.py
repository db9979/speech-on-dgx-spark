"""KI-Dungeon-Master: Gleiches Gesicht für NSCs (Tabletop-Punkt 15 of 2026-10-25, Dominik „ich hätte gerne alle punkte
umgesetzt“, plan https://claude.ai/artifact/4QwoVfd2irhoQEeLmj5ngK 1a-5a; idea from Project_Infinity, MIT, own code).

Every person of the round's truth with a card (dungeon_nsc) gets one portrait once the table met it: painted by the
minute loop (dungeon_dingbild.due) in the background like a hero's portrait (the game's day limit, the voice first),
only from fixed parts: the world's style, age and gender of the person's fixed voice traits (dungeon_stimmen), the
card's looks, manner and occupation in English, light, angle and mood from the fixed lists (dungeon_dingbild.flair).
Never from the model's text and never with the person's name. A person that has not spoken yet waits WARTE_ZUEGE turns,
so its voice (and with it its gender) is known first. A later scene picture (dungeon.queue_scene) takes up to VORLAGEN
of these portraits as reference pictures (bilder.paint refs), chosen by fixed rules: the people of the last narration
(speaking first, then named), then a hero who acted in that turn and has a portrait, each with a fixed phrase, so a face
stays the same from picture to picture. The host may have a portrait painted again; the old one stays until the new
one is there. Only while „Gesichter für NSCs“ (features "dungeongesicht", admin switch chat.dungeon_gesicht, off) is
allowed for the host, together with „NSC-Gedächtnis und Chronik“ and „Bilder malen“.
A hired companion (dungeon_gefaehrte, D&D ideas round 2, idea 9, Dominik 2026-10-26 „1-9 umsetzten reihenfolge überlasse
ich dir.“) gets its face the same way, at once on hiring, from its fixed line of the table in English (an animal friend at
the children's table as it is), never with its name; only while „Gefährten anheuern“ is allowed for the host together
with this switch and „Bilder malen“. The table shows it instead of 🤝 (gefaehrten[].bild), a scene picture takes it as a
reference when the last narration names the companion. The field:

    rd["nsc"][name]["gesicht"]  {"n": "nsc-<16 hex>", "st": "malt" | "ok" | "weg" | "fehler" | "tag" | "neu", "day", "alt"?}
    rd["gefaehrten"][i]["gesicht"]   the same for a companion (a campaign keeps it with the companion)

The card goes into the next chapter with its portrait (dungeon_nsc.keep); a portrait no round or campaign names goes
with the hourly sweep. Seats see the portrait's name in the people of the view (nsc.leute[].bild) and load it like an
item's picture (dungeon_dingbild.ding, only a seat of a round that names it). Journal lines „dungeon: gesicht | …“,
fixed words and numbers only; Live: numbers only.

    POST /api/profile/dungeon/{rid}/gesicht    {name, lang}: the host has a person's portrait painted again
"""
import asyncio
import base64
import os
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_album as album
import dungeon_gefaehrte as gf
import dungeon_nsc as nsc
import dungeon_stimmen as stimmen
import features
import guard
import profiles
from common import DayCounter
from core import assistant, browser_profile, json_body, spawn

router = APIRouter()

KEY = "dungeongesicht"
NAME = re.compile(r"nsc-[0-9a-f]{16}")
VORLAGEN = 2               # reference pictures one scene takes (bild_server.MAX_REFS)
WARTE_ZUEGE = 2            # a person that has not spoken yet is painted this many turns after it was met
GESICHT_EN = "character portrait, head and shoulders, the face clearly visible"
VORLAGE_EN = "{} from reference image {} with the same face"
HELD_EN = "the hero"
GEFAEHRTE_EN = "a companion of the heroes, "
GEFAEHRTE_VORLAGE_EN = "the companion"
_malt = set()              # portraits on their way (memory: a restart paints again the next day)
_vorlagen = {}             # (rid, bid) -> portrait names of a scene picture on its way
_sweep = [0.0]
_day = DayCounter(gemalt=0, weg=0, vorlagen=0)


def _basis(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and dungeon.pictures_on(rd["owner"])


def on(rd):
    """The host may: this switch, „NSC-Gedächtnis und Chronik“ and „Bilder malen“."""
    return _basis(rd) and nsc.on(rd)


def gf_on(rd):
    """The companions' faces: this switch, „Gefährten anheuern“ and „Bilder malen“."""
    return _basis(rd) and gf.on(rd)


def people(rd):
    """[(key, record)] of everyone who gets a portrait here: the cards (nsc) and the hired companions (key gf:…)."""
    out = list((rd.get("nsc") or {}).items()) if on(rd) else []
    if gf_on(rd):
        out += [(c["k"], c) for c in gf.all_(rd) if isinstance(c, dict) and gf.is_one(c.get("k"))]
    return out


def _find(rd, key):
    if gf.is_one(key):
        return next((c for c in gf.all_(rd) if isinstance(c, dict) and c.get("k") == key), None)
    return (rd.get("nsc") or {}).get(key)


def who(rd, x):
    """Age and gender of the person by its fixed voice traits (the same the speech output uses), as English words."""
    n = stimmen.data()["npc"]
    t = stimmen._of(rd, x["name"])
    if t["alter"] == "kind":
        return {"weiblich": "a girl", "maennlich": "a boy"}.get(t["geschlecht"], "a child")
    return f"{n['alter'][t['alter']]} {n['geschlecht'][t['geschlecht']]}"


def text(rd, x):
    """The person's fixed description from its card (English column of the tables); a companion's from its fixed line."""
    if gf.is_one(x.get("k")):
        s = str((x.get("satz") or ["", ""])[-1]).strip().rstrip(".")
        return GEFAEHRTE_EN + s[:1].lower() + s[1:]
    k = x.get("karte") or {}
    out = who(rd, x)
    if k.get("beruf"):
        out += f" ({k['beruf'][1]})"
    if k.get("aussehen"):
        out += f" who {k['aussehen'][1]}"
    if k.get("art"):
        out += f", {k['art'][1]} in manner"
    return out


def prompt(r, rd, key, x):
    """The portrait's prompt, or ("", why) when the checks refuse the description."""
    import dungeon_dingbild as db
    t, why = dungeon.picture_text(r, rd, text(rd, x))
    if why:
        return "", why
    style = dungeon.style(r, rd)
    return f"{style}, {GESICHT_EN}, {t}, {db.flair(style, {'id': 'nsc:' + key}, 'gesicht')}, {dungeon.BILD_ENDE}", ""


def _due(rd, key, x, today):
    """Whether the person's portrait is to be painted now (not yet, or again on the host's wish); a companion at once."""
    g = x.get("gesicht") or {}
    comp = gf.is_one(key)
    if (x.get("gesehen") is None and not comp) or g.get("n") in _malt or g.get("st") in ("ok", "weg"):
        return False
    if g.get("st") in ("tag", "fehler", "malt") and g.get("day") == today:
        return False
    spoke = comp or key in (rd.get("npc_stimmen") or {})
    return g.get("st") == "neu" or spoke or rd.get("zug", 0) - x["gesehen"] >= WARTE_ZUEGE


def queue():
    """Inside dungeon._lock: every person met (and every companion hired) in a running round without its portrait, of a
    host who may, within the game's day limit. Returns [(rid, key, name, prompt)] to paint (dungeon_dingbild.due)."""
    import dungeon_dingbild as db
    import schwer
    r = dungeon.rules()
    out, today = [], db._date()
    with dungeon._lock:
        d = dungeon._read()
        changed = False
        for rid, rd in d["runden"].items():
            if rd.get("status") != "laeuft":
                continue
            for key, x in people(rd):
                if not _due(rd, key, x, today):
                    continue
                g = x.get("gesicht") or {}
                alt = g.get("n") if g.get("st") == "neu" else g.get("alt")
                p, why = prompt(r, rd, key, x)
                if not why and dungeon._bild_tag_voll(r, d, rd):
                    why = "tag"
                if not why and schwer.full():
                    continue
                changed = True
                if why:
                    x["gesicht"] = {"n": alt, "st": "ok", "day": today} if alt else {"st": "tag" if why == "tag" else "weg", "day": today}
                    print(f"dungeon: gesicht | abgelehnt | {why if why in ('tag', 'wortliste', 'person', 'leer') else 'regel'}", flush=True)
                    continue
                n = "nsc-" + secrets.token_hex(8)
                dungeon._bild_take(d)
                x["gesicht"] = {"n": n, "st": "malt", "day": today, **({"alt": alt} if alt else {})}
                _malt.add(n)
                out.append((rid, key, n, p))
        if changed:
            dungeon._write(d)
    return out


async def paint(rid, key, n, p):
    """One portrait through the game's painter; the card notes how it went (a repaint that failed keeps the old one)."""
    import dungeon_dingbild as db
    t0 = time.perf_counter()
    try:
        res = await db.paint_one(n, p)
    finally:
        _malt.discard(n)

    def note():
        with dungeon._lock:
            d = dungeon._read()
            x = _find(d["runden"].get(rid) or {}, key)
            if not x or (x.get("gesicht") or {}).get("n") != n:
                return
            alt, day = x["gesicht"].get("alt"), db._date()
            if res == "ok":
                x["gesicht"] = {"n": n, "st": "ok", "day": day}
                if alt:
                    dungeon._bild_rm(alt)
            elif alt:
                x["gesicht"] = {"n": alt, "st": "ok", "day": day}
                dungeon._bild_rm(n)
            else:
                x["gesicht"] = {"st": "weg" if res in ("pruefung", "ohne_pruefung") else "fehler", "day": day}
            dungeon._write(d)
    await asyncio.to_thread(note)
    _day.bump("gemalt" if res == "ok" else "weg")
    print(f"dungeon: gesicht | {res} | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)


# ---------------------------------------------------------------- the scene picture's reference pictures
def _ok(x, have):
    """The portrait to show and to take as a reference: the painted one, while a new one is on its way the old one."""
    g = x.get("gesicht") or {}
    n = g.get("n") if g.get("st") in ("ok", "neu") else g.get("alt") if g.get("st") == "malt" else None
    return n if n and n in have else ""


def vorlagen(r, rd):
    """Inside the lock, when a scene picture is queued: up to VORLAGEN portraits by fixed rules (the last narration's
    people, speaking first, then named; then a hero who acted in that turn) and the fixed phrase for each. Returns
    ([names], text to add to the scene's prompt)."""
    import dungeon_dingbild as db
    pp = dict(people(rd))
    if not pp:
        return [], ""
    e = next((e for e in reversed(rd.get("log") or []) if e.get("art") == "dm"), None)
    if not e:
        return [], ""
    have = db.files()
    low = str(e.get("text", "")).lower()
    keys = [str(x.get("name", "")).lower() for x in e.get("npc") or []]
    keys += sorted((k for k in pp if not gf.is_one(k) and k in low), key=low.index)
    seen = {k: min(low.index(w) for w in ws) for k, ws in
            ((k, [str(w).lower() for w in pp[k].get("name") or [] if str(w).strip() and str(w).lower() in low]) for k in pp if gf.is_one(k)) if ws}
    keys += sorted(seen, key=seen.get)                  # then the companions the narration names
    names, phrases = [], []
    for k in keys:
        n = _ok(pp[k], have) if k in pp else ""
        if n and n not in names and len(names) < VORLAGEN:
            names.append(n)
            phrases.append(VORLAGE_EN.format(GEFAEHRTE_VORLAGE_EN if gf.is_one(k) else f"the {who(rd, pp[k]).split(' ', 1)[1]}", len(names)))
    for a in rd.get("log") or []:
        if len(names) >= VORLAGEN:
            break
        h = (rd["plaetze"].get(a.get("pid")) or {}).get("held") if a.get("art") == "aktion" and a.get("n") == e.get("n") else None
        n = "held-" + h["hid"] if h and h.get("bild") is not None else ""
        if n and n not in names and os.path.exists(dungeon.bild_file(n)):
            names.append(n)
            phrases.append(VORLAGE_EN.format(HELD_EN, len(names)))
    return names, "".join(", " + p for p in phrases)


def merke(rid, bid, names):
    if names:
        while len(_vorlagen) >= 20:               # a scene picture that never started keeps no entry for long
            _vorlagen.pop(next(iter(_vorlagen)))
        _vorlagen[(rid, bid)] = list(names)
        _day.bump("vorlagen")


def refs(rid, bid):
    """The reference pictures of a scene picture on its way, as base64 (none that went meanwhile)."""
    out = []
    for n in _vorlagen.pop((rid, bid), []):
        try:
            with open(dungeon.bild_file(n), "rb") as f:
                out.append(base64.b64encode(f.read()).decode())
        except OSError:
            pass
    return out or None


# ---------------------------------------------------------------- what a seat sees, what is kept
def add(rd, out):
    """dungeon.view (through dungeon_dingbild.add): the portrait's name on every person met (nsc.leute[].bild), the
    host's „Neu malen“ on its secret card (nsc_geheim[].gesicht: "ok" may be painted again, "malt" on its way), the
    companion's face on its row (gefaehrten[].bild)."""
    import dungeon_dingbild as db
    if isinstance(out.get("gefaehrten"), list) and gf_on(rd):
        have = db.files()
        for c in out["gefaehrten"]:
            x = _find(rd, str(c.get("k", "")))
            c["bild"] = _ok(x, have) if x else ""
    if not isinstance(out.get("nsc"), dict) or not on(rd):
        return out
    have = db.files()
    ns = rd.get("nsc") or {}
    for p in out["nsc"].get("leute") or []:
        x = ns.get(str(p.get("name", "")).lower())
        p["bild"] = _ok(x, have) if x else ""
    for name, g in (out.get("nsc_geheim") or {}).items():
        x = ns.get(name.lower())
        st = (x.get("gesicht") or {}).get("st") if x else None
        g["gesicht"] = "malt" if st in ("malt", "neu") else "ok" if st in ("ok", "weg", "fehler", "tag") else ""
    return out


def keep(d):
    """The portraits a round or a campaign still names (the sweep keeps them)."""
    out = set()

    def card(xs):
        for x in xs:
            g = x.get("gesicht") if isinstance(x, dict) else None
            if isinstance(g, dict):
                out.update(n for n in (g.get("n"), g.get("alt")) if n)
    for v in [*d["runden"].values(), *(c for uid in profiles.user_ids() for c in dungeon.campaigns(uid).values())]:
        card(_alle(v))
    import dungeon_personen                      # the people of the catalog keep their faces (Personen-Katalog 1)
    return out | dungeon_personen.portraits()


def sweep(now):
    """At most every hour: the portraits nobody names any more."""
    import dungeon_dingbild as db
    if now - _sweep[0] < 3600:
        return 0
    _sweep[0] = now
    gone = [n for n in db.files() if n.startswith("nsc-") and n not in _malt]
    if gone:
        k = keep(dungeon._read())
        gone = [n for n in gone if n not in k]
    for n in gone:
        dungeon._bild_rm(n)
    if gone:
        print(f"dungeon: gesicht | aufgeraeumt | {len(gone)} bilder", flush=True)
    return len(gone)


def _alle(v):
    """Every card and companion of a round or a campaign (the records that may hold a portrait)."""
    ns, gs = v.get("nsc"), v.get("gefaehrten")
    return [*(ns.values() if isinstance(ns, dict) else ()), *(gs if isinstance(gs, list) else ())]


def may_see(name, uid=None, rid=None):
    """An nsc- picture only for a seat of a round that names it, or whose heroes met that person of the catalog (the
    album's page „Personen“; a guest's seat by rid, a profile that hosts or sits in it by uid). Any other name pattern
    is not this module's (True)."""
    if not str(name).startswith("nsc-"):
        return True
    for r_id, v in dungeon._read()["runden"].items():
        if rid is not None and r_id != rid:
            continue
        if uid is not None and v.get("owner") != uid and not any(p.get("uid") == uid for p in v["plaetze"].values()):
            continue
        if any(isinstance(x, dict) and name in ((x.get("gesicht") or {}).get("n"), (x.get("gesicht") or {}).get("alt")) for x in _alle(v)):
            return True
        if album.people_on(v) and album.knows_face(name, [p["held"] for p in v["plaetze"].values() if p.get("held")]):
            return True                          # the album page „Personen“ of a hero at that table shows the face
    return False


def for_live():
    """Numbers only: portraits there are, on their way, painted and refused today, scenes with reference pictures."""
    if not features.admin_on(KEY):
        return {"on": False}
    rs = [v for v in dungeon._read()["runden"].values() if v.get("status") == "laeuft"]
    return {"on": True, "da": sum(1 for v in rs for x in _alle(v) if isinstance(x, dict) and (x.get("gesicht") or {}).get("st") == "ok"),
            "malt": len(_malt), **_day.counts()}


def neu(uid, rid, name):
    """The host's „Neu malen“: the person's portrait comes again with the next minute (the old one until then).
    Raises LookupError or ValueError(why of dungeon.BILD_NEIN)."""
    import dungeon_dingbild as db
    r = dungeon.rules()
    with dungeon._lock:
        d = dungeon._read()
        rd = dungeon._round(d, rid)
        x = (rd.get("nsc") or {}).get(str(name or "").strip().lower()[:nsc.NAME_LEN])
        if rd["owner"] != uid or rd["status"] != "laeuft" or not x or x.get("gesehen") is None:
            raise LookupError("figur")
        g = x.get("gesicht") or {}
        why = "aus" if not on(rd) else "malt" if g.get("st") in ("malt", "neu") else "tag" if dungeon._bild_tag_voll(r, d, rd) else ""
        if why:
            print(f"dungeon: gesicht | abgelehnt | {why}", flush=True)
            raise ValueError(why)
        x["gesicht"] = {"n": g["n"], "st": "neu", "day": db._date()} if g.get("n") and g.get("st") == "ok" else {"st": "neu", "day": db._date()}
        dungeon._write(d)
    print("dungeon: gesicht | neu malen", flush=True)


@router.post("/api/profile/dungeon/{rid}/gesicht", dependencies=[Depends(assistant)])
async def gesicht_neu(rid: str, request: Request, prof=Depends(browser_profile)):
    """{name, lang}: the host has a person's portrait painted again."""
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeonbild", uid)
    b = await json_body(request, dungeon.BODY)
    try:
        await asyncio.to_thread(neu, uid, rid, b.get("name"))
    except ValueError as e:
        raise HTTPException(409, dungeon._nein(str(e), dungeon._lang(b)))
    except LookupError as e:
        raise dungeon._http(e)
    for job in await asyncio.to_thread(queue):
        spawn(paint(*job), name="dungeon-gesicht")
    return await asyncio.to_thread(dungeon.view, rid, dungeon._seat_uid(rid, uid))
