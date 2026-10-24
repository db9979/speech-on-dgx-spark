"""KI-Dungeon-Master: the admin's rules page as its own tab „Regeln“ (Dominik 2026-10-24 „die regel seite sollte für den
admin hier sein“, „das besarium zu sehen zu bearbeten gegenstände etc.“, „alle punkte umsetzten“). Builds on the game
(dungeon.py: rules, own rules, check_rules), the pictures (dungeon_dingbild.py) and the balance (dungeon_balance.py).

Per part of the catalog (TEILE) a list of rows (picture, name, one line of values, where it comes from, the balance mark)
and the merged entries for the detail. The admin changes one entry at a time: „Ändern“ writes the whole entry with its
id into the own rules, „Ausblenden“ writes {"id", "aus": true}, „Zurück auf mitgeliefert“ takes the own entry out.
Every change passes dungeon.check_rules like the JSON editor (a refused one comes back with its errors); „zu stark“
is only a hint (Dominik „zu stark nur hinweis“). „Nochmal malen“ paints a candidate next to the picture in use, the
admin keeps the new or the old one.

    GET  /api/admin/dungeon/katalog/{teil}         rows and entries of one part
    POST /api/admin/dungeon/katalog/{teil}         {"was": "setzen"|"aus"|"zurueck", "id", "eintrag"?}
    POST /api/admin/dungeon/katalog/{teil}/bild    {"id", "was": "malen"|"neu"|"alt"}
    GET  /api/admin/dungeon/bild/{name}            a catalog picture or a candidate (admin only)

Journal lines „dungeon: regelseite | …“ with fixed words and numbers only.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_balance as balance
import dungeon_dingbild as dingbild
import guard
from common import write_json
from core import auth, json_body

router = APIRouter()
TEILE = ("gegenstaende", "gegner", "klassen", "voelker", "welten", "toene", "zustaende", "hintergruende")
MIT_BILD = ("gegenstaende", "gegner")
BODY = 16000              # one entry as JSON


def _lang(request):
    return "en" if request.query_params.get("lang") == "en" else "de"


def _name(x, li):
    n = x.get("name")
    return str(n[li] if isinstance(n, list) and len(n) > li else n or x.get("id", ""))


def _sign(v):
    return f"+{v}" if v >= 0 else str(v)


def line(teil, x, r, li):
    """One line of values for a row (fixed words, the catalog's numbers)."""
    en = li == 1
    if teil == "gegner":
        s = {0.125: "⅛", 0.25: "¼", 0.5: "½"}.get(x.get("stufe"), f"{x.get('stufe', 0):g}")
        dmg = f"{x.get('anzahl_wuerfel', 1)}{'d' if en else 'W'}{x.get('schaden', 0)}" + (f"+{x['schaden_plus']}" if x.get("schaden_plus") else "")
        return " · ".join([("Level " if en else "Stufe ") + s, ("Life " if en else "Leben ") + str(x.get("leben", 0)),
                           ("Armour " if en else "Rüstung ") + str(x.get("ruestung", 0)), _sign(x.get("angriff", 0)) + " " + dmg])
    if teil == "gegenstaende":
        sel = {s["id"]: s["name"][li] for s in r["seltenheit"]}
        out = [sel.get(x.get("seltenheit"), "gewürfelt" if not en else "rolled")]
        for k, de, enw, pre in (("schaden", "Schaden", "Damage", "W"), ("schutz", "Schutz", "Protection", ""), ("heilung", "Heilung", "Healing", ""),
                                ("grad", "Grad", "Grade", "")):
            if k in x:
                out.append(f"{enw if en else de} {('d' if en else pre) if pre else ''}{x[k]}")
        if isinstance(x.get("segen"), dict):
            out.append(f"{'Blessing' if en else 'Segen'} +{x['segen'].get('bonus', 0)} × {x['segen'].get('zuege', 1)}")
        if "preis" in x:
            out.append(f"{x['preis']} {'gold' if en else 'Gold'}")
        return " · ".join(out)
    kurz = {w["id"]: _name(w, li)[:3].upper() for w in r["werte"]}
    if teil == "klassen":
        return " · ".join([" · ".join(kurz.get(k, k) for k in (x.get("reihe") or [])[:2]), ("Life " if en else "Leben ") + str(x.get("leben", 0)),
                           f"{len(x.get('faehigkeiten') or [])} {'abilities' if en else 'Fähigkeiten'}"])
    if teil in ("voelker", "hintergruende"):
        return " · ".join(f"{kurz.get(k, k)} +{v}" for k, v in (x.get("werte") or {}).items()) or ""
    if teil == "zustaende":
        return " · ".join([w.replace("_", " ") for w in x.get("wirkung") or []] + ([f"{x['runden']} {'rounds' if en else 'Runden'}"] if x.get("runden") else []))
    s = x.get("satz") or x.get("info")
    return str(s[li] if isinstance(s, list) and len(s) > li else s or "")


def view(teil, lang="de"):
    """{"teil", "zeilen": [...], "eintraege": {id: entry}}: the merged part with where each entry comes from."""
    li = 1 if lang == "en" else 0
    r = dungeon.rules()
    grund = {x["id"] for x in dungeon._base_rules(srd=False).get(teil) or []}
    base = {x["id"]: x for x in dungeon._base_rules().get(teil) or []}
    own = {x.get("id"): x for x in dungeon.own_rules().get(teil) or [] if isinstance(x, dict)}
    have = dingbild.files() if teil in MIT_BILD else frozenset()
    neu = set(dingbild.candidates()) if teil in MIT_BILD else set()
    rows, entries = [], {}
    for x in list(r.get(teil) or []) + [base[i] for i, o in own.items() if o.get("aus") and i in base]:
        i = x["id"]
        o = own.get(i)
        stand = "aus" if o and o.get("aus") else "geaendert" if o and i in base else "eigen" if o else "grund" if i in grund else "srd"
        row = {"id": i, "name": _name(x, li), "zeichen": x.get("zeichen") or dingbild.ZEICHEN.get(x.get("art"), ""),
               "zeile": line(teil, x, r, li), "stand": stand, "art": x.get("art", "")}
        if teil == "gegner":
            row["marke"] = balance.foe(x, lang)
            row["stufe"] = x.get("stufe", 0)
        elif teil == "gegenstaende":
            row["marke"] = balance.item(x, lang)
            row["selten"] = x.get("seltenheit") or ""      # the frame's colour (dungeon.js DMSEL); "" = rolled
        if teil in MIT_BILD:
            n, _ = dingbild.picture_of(r, x)
            row["bild"] = n if n in have else ""
            row["neu"] = "neu-" + n[5:] if "neu-" + n[5:] in neu else ""
        rows.append(row)
        entries[str(i)] = x
    out = {"teil": teil, "zeilen": rows, "eintraege": entries, "bilder_an": dingbild.on()}
    if teil == "gegenstaende":       # the ladder a rolled item climbs (dungeon.rarity: W100 + 2 × level)
        out["seltenheiten"] = [{"id": s["id"], "name": _name(s, li), "ab": s["ab"], "bonus": s["bonus"],
                                "stufe": s["stufe_min"], "preis": s["preis"]} for s in r["seltenheit"]]
    return out


def change(teil, was, i, eintrag=None):
    """One entry of the own rules set, hidden or taken back; refused (ValueError with the errors) unless the rules
    still pass. Returns the hint of the balance for the entry (or None)."""
    own = dungeon.own_rules()
    own = own if isinstance(own, dict) else {}
    ids = {str(x["id"]): x["id"] for x in dungeon._base_rules().get(teil) or []}
    i = ids.get(str(i), i)                              # a tone's id is a number
    lst = [x for x in own.get(teil) or [] if isinstance(x, dict) and str(x.get("id")) != str(i)]
    if was == "setzen":
        if not isinstance(eintrag, dict) or str(eintrag.get("id")) != str(i):
            raise ValueError(["id"])
        lst.append(eintrag)
    elif was == "aus":
        lst.append({"id": i, "aus": True})
    elif was != "zurueck":
        raise ValueError(["was"])
    own = dict(own, **{teil: lst})
    if not own[teil]:
        own.pop(teil)
    errs = [f"{teil}: höchstens {dungeon.EIGENE_MAX} eigene Einträge"] if len(lst) > dungeon.EIGENE_MAX else []
    errs += dungeon.check_rules(dungeon.merge(dungeon._base_rules(), own))
    if errs:
        print(f"dungeon: regelseite | abgelehnt | {len(errs)} fehler", flush=True)
        raise ValueError(errs[:20])
    write_json(dungeon.EIGENE, own, 2, 0o600, False, 0o700)
    dungeon._rules["r"] = None
    print(f"dungeon: regelseite | {was} | {teil}", flush=True)
    if was == "setzen" and teil in ("gegner", "gegenstaende"):
        m = balance.foe(eintrag) if teil == "gegner" else balance.item(eintrag)
        return m if m["marke"] in ("stark", "zu_stark") else None
    return None


def _entry(teil, i):
    x = {str(k): v for k, v in dungeon._by(dungeon.rules(), teil).items()}.get(str(i))
    if not x:
        raise LookupError("eintrag")
    return x


@router.get("/api/admin/dungeon/katalog/{teil}", dependencies=[Depends(auth)])
async def katalog(teil: str, request: Request):
    guard.limit(request, "dungeonregel", admin=True)
    if teil not in TEILE:
        raise HTTPException(404, "teil")
    return await asyncio.to_thread(view, teil, _lang(request))


@router.post("/api/admin/dungeon/katalog/{teil}", dependencies=[Depends(auth)])
async def katalog_change(teil: str, request: Request):
    guard.limit(request, "dungeonregel", admin=True)
    if teil not in TEILE:
        raise HTTPException(404, "teil")
    b = await json_body(request, BODY)
    i = str(b.get("id") or "")
    if not i or len(i) > 40:
        raise HTTPException(400, "id")
    try:
        hint = await asyncio.to_thread(change, teil, str(b.get("was") or ""), i, b.get("eintrag"))
    except ValueError as e:
        raise HTTPException(422, e.args[0] if e.args and isinstance(e.args[0], list) else ["eintrag"])
    out = await asyncio.to_thread(view, teil, _lang(request))
    out["hinweis"] = hint
    return out


@router.post("/api/admin/dungeon/katalog/{teil}/bild", dependencies=[Depends(auth)])
async def katalog_bild(teil: str, request: Request):
    """„Nochmal malen“ (was "malen"), then „Neues behalten“ ("neu") or „Altes behalten“ ("alt")."""
    guard.limit(request, "dungeonbild", admin=True)
    if teil not in MIT_BILD:
        raise HTTPException(404, "teil")
    b = await json_body(request, 2000)
    was = b.get("was")
    try:
        c = await asyncio.to_thread(_entry, teil, str(b.get("id") or ""))
        r = dungeon.rules()
        if was == "malen":
            why, neu = await dingbild.repaint(r, c)
            if why != "ok":
                raise HTTPException(409, why)
            if not dingbild.picture_of(r, c)[1]:          # „🖌 Malen“ of a missing picture: nothing to compare
                await asyncio.to_thread(dingbild.settle, r, c, True)
                return {"neu": "", "bild": dingbild.picture_of(r, c)[0]}
            return {"neu": neu}
        if was not in ("neu", "alt"):
            raise HTTPException(400, "was")
        await asyncio.to_thread(dingbild.settle, r, c, was == "neu")
        return {"ok": True}
    except LookupError as e:
        raise dungeon._http(e)


@router.get("/api/admin/dungeon/bild/{name}", dependencies=[Depends(auth)])
async def bild(name: str, request: Request):
    guard.limit(request, "dungeonding", admin=True)
    if not (dingbild.NAME.fullmatch(name) or dingbild.NEU.fullmatch(name)):
        raise HTTPException(404, "bild")
    try:
        return dungeon._png_out(await asyncio.to_thread(dungeon._png, name))
    except LookupError as e:
        raise dungeon._http(e)


def counts():
    """Numbers for Live: own entries per part, hidden ones, candidates waiting."""
    own = dungeon.own_rules()
    own = own if isinstance(own, dict) else {}
    lst = [x for t in TEILE for x in own.get(t) or [] if isinstance(x, dict)]
    return {"eigene": sum(1 for x in lst if not x.get("aus")), "aus": sum(1 for x in lst if x.get("aus")),
            "kandidaten": len(dingbild.candidates()), "json": len(json.dumps(own))}
