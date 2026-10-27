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
    GET  /api/admin/dungeon/bild/{name}            a catalog picture or a candidate (admin only); ?klein=1 the small copy

Journal lines „dungeon: regelseite | …“ with fixed words and numbers only.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_balance as balance
import dungeon_dingbild as dingbild
import dungeon_kampf as kampf
import dungeon_personen as personen
import guard
from common import write_json
from core import app_version, auth, json_body

router = APIRouter()
TEILE = ("gegenstaende", "gegner", "klassen", "voelker", "welten", "toene", "zustaende", "hintergruende", "tabellen")
ALLE = TEILE + ("personen",)   # the people of the catalog (dungeon_personen, Personen-Katalog 1) beside the parts of the rules
GRUPPE = {"nsc": ("Figuren", "People"), "orakel": ("Orakel", "Oracle"), "eigen": ("Eigene", "Own")}   # tables (dungeon_tabellen)
TAB_ZEICHEN = {"nsc": "👤", "orakel": "🔮", "eigen": "✎",      # a table's sign in the list: its own, else its group's
               "nsc_aussehen": "👁️", "nsc_art": "🎭", "nsc_wunsch": "💭", "nsc_geheimnis": "🤫", "nsc_beruf": "🛠️",
               "orakel_aktion": "⚡", "orakel_thema": "📜", "orakel_ort": "🗺️", "orakel_merkmal": "🔍", "orakel_wendung": "🔀",
               "orakel_komplikation": "⚠️", "orakel_hinweis": "💡", "orakel_gefahr": "☠️", "orakel_chance": "🍀", "orakel_aerger": "🏘️"}
MIT_BILD = ("gegenstaende", "gegner", "klassen", "voelker", "hintergruende", "welten")   # welten, peoples, classes,
# backgrounds since Dominik 2026-10-24 „1a 2 und 3“: a people, class or background in the style of the world chosen above
BODY = 16000              # one entry as JSON
NEU_FUER = 30             # a foe of the bestiary is „neu“ for this many versions after its „seit“ (Bestiarium-Punkt 9)
HELDEN = (2, 3, 4, 5)     # the group sizes the detail shares a foe's EP among


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
                           ("Armour " if en else "Rüstung ") + str(x.get("ruestung", 0)), _sign(x.get("angriff", 0)) + " " + dmg, f"{x.get('ep', 0)} EP"])
    if teil == "gegenstaende":
        sel = {s["id"]: s["name"][li] for s in r["seltenheit"]}
        out = [ART.get(x.get("art"), ("", ""))[li], sel.get(x.get("seltenheit"), "gewürfelt" if not en else "rolled")]
        if x.get("wert"):
            out.append(_name(next((v for v in r["werte"] if v["id"] == x["wert"]), {"id": x["wert"]}), li))
        for k, de, enw, pre in (("schaden", "Schaden", "Damage", "W"), ("schutz", "Schutz", "Protection", ""), ("heilung", "Heilung", "Healing", ""),
                                ("grad", "Grad", "Grade", "")):
            if k in x:
                out.append(f"{enw if en else de} {('d' if en else pre) if pre else ''}{x[k]}")
        if isinstance(x.get("segen"), dict):
            sw = next((_name(v, li)[:3].upper() for v in r["werte"] if v["id"] == x["segen"].get("wert")), "")
            out.append(f"{'Blessing' if en else 'Segen'} {sw} +{x['segen'].get('bonus', 0)} × {x['segen'].get('zuege', 1)}".replace("  ", " "))
        if isinstance(x.get("hilft"), dict):
            out.append(("Tool +" if en else "Werkzeug +") + "/".join(str(n) for n in dungeon.WERKZEUG))
        if "preis" in x:
            out.append(f"{x['preis']} {'gold' if en else 'Gold'}")
        return " · ".join(out)
    if teil == "tabellen":                     # Tabletop-Punkt 8: the admin's own tables next to the shipped ones
        return f"{GRUPPE.get(x.get('gruppe'), ('', ''))[li]} · {len(x.get('zeilen') or [])} {'rows' if en else 'Zeilen'}"
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


ART = {"waffe": ("Waffe", "Weapon"), "ruestung": ("Rüstung", "Armour"), "schmuck": ("Schmuck", "Jewellery"),
       "trank": ("Trank", "Potion"), "zauber": ("Zauber", "Spell"), "rolle": ("Schriftrolle", "Scroll"),
       "werkzeug": ("Werkzeug", "Tool"), "schatz": ("Schatz", "Treasure")}


def _vnum(v):
    """V01.1.038 → 1038 (the series after V01.0.999 goes on at V01.1.000); None for anything else."""
    p = str(v or "").lstrip("Vv").split(".")
    return int(p[1]) * 1000 + int(p[2]) if len(p) == 3 and all(n.isdigit() for n in p) else None


def frisch(x, jetzt=None):
    """A foe added in the last NEU_FUER versions (its „seit“), shown as „neu“ in the bestiary."""
    a, b = _vnum(x.get("seit")), _vnum(jetzt if jetzt is not None else app_version())
    return a is not None and b is not None and 0 <= b - a < NEU_FUER


def arten(x):
    """A foe's damage kind and what hurts it more or less, as kind ids (only known ones)."""
    return {"art": x.get("schaden_art", "hieb"), **{k: [a for a in x.get(k) or [] if a in kampf.ART_NAME] for k in ("resistenz", "immun", "schwaeche")}}


def werte(teil, x, r, li):
    """What an entry does, as [label, value] pairs for the detail (Dominik 2026-10-24 „sollten immer auch Werte
    anzeigen wie stark, was sie bewirken“): the catalog's numbers in fixed words, the same lines the table shows."""
    en = li == 1
    w = {v["id"]: _name(v, li) for v in r["werte"]}
    L = lambda de, enw: enw if en else de          # noqa: E731
    out = []
    if teil == "gegenstaende":
        out.append([L("Art", "Kind"), ART.get(x.get("art"), (x.get("art", ""),) * 2)[li]])
        try:                                        # what it does at the table (dungeon.item_view, common rarity)
            it = {"i": 0, "id": x["id"], "s": x.get("seltenheit") or r["seltenheit"][0]["id"]}
            for z in dungeon.item_view(r, it, "en" if en else "de")["zeilen"]:
                out.append([L("Wirkung", "Effect"), z.replace(" + 0", "")])
        except (KeyError, IndexError, TypeError):
            pass
        if x.get("wert"):
            out.append([L("Zählt auf", "Uses"), w.get(x["wert"], x["wert"])])
        if x.get("ziel"):
            out.append([L("Für", "For"), {"selbst": L("sich selbst", "oneself"), "gruppe": L("die ganze Gruppe", "the whole group"),
                                          "verbuendeter": L("einen Freund, den die Aktion nennt", "a friend the action names")}.get(x["ziel"], x["ziel"])])
        if isinstance(x.get("rettung"), dict) and x["rettung"].get("wert"):   # Kampf-Audit H4: the foe's saving throw
            out.append([L("Rettungswurf des Gegners", "Foe's saving throw"), w.get(x["rettung"]["wert"], x["rettung"]["wert"])
                        + (L(", geschafft: halber Schaden", ", passed: half damage") if x.get("halb") else L(", geschafft: keine Wirkung", ", passed: no effect"))])
        if x.get("art") == "zauber" and x.get("zustand"):
            z = {v["id"]: _name(v, li) for v in r.get("zustaende") or []}
            out.append([L("Zustand beim Gegner", "Condition on the foe"), z.get(x["zustand"], x["zustand"])])
        if x.get("grad"):
            out.append([L("Zaubergrad", "Spell grade"), str(x["grad"])])
        if x.get("klassen"):
            k = {c["id"]: _name(c, li) for c in r["klassen"]}
            out.append([L("Klassen", "Classes"), ", ".join(k.get(c, c) for c in x["klassen"])])
        if x.get("platz"):
            out.append([L("Getragen an", "Worn on"), str(x["platz"])])
        out.append([L("Gewicht", "Weight"), f"{x.get('kg', 0):g} kg"])
        if "preis" in x:
            out.append([L("Preis", "Price"), f"{x['preis']} {L('Gold', 'gold')}" + ("" if x.get("seltenheit") else L(" (mal Seltenheit)", " (times rarity)"))])
    elif teil == "gegner":
        d = x.get("schaden", 0)
        n = x.get("anzahl_wuerfel", 1)
        avg = n * (d + 1) / 2 + x.get("schaden_plus", 0)
        out += [[L("Stufe", "Level"), line("gegner", x, r, li).split(" · ")[0].split(" ")[-1]], [L("Leben", "Life"), str(x.get("leben", 0))],
                [L("Rüstung", "Armour"), str(x.get("ruestung", 0)) + L(" (so schwer ist er zu treffen)", " (how hard it is to hit)")],
                [L("Angriff", "Attack"), f"W20 {_sign(x.get('angriff', 0))}" if not en else f"d20 {_sign(x.get('angriff', 0))}"],
                [L("Schaden", "Damage"), f"{n}{'d' if en else 'W'}{d}" + (f"+{x['schaden_plus']}" if x.get("schaden_plus") else "") + L(f", im Schnitt {avg:g}", f", {avg:g} on average")],
                ["EP", str(x.get("ep", 0)) + L(" für die Gruppe", " for the group")]]
        if isinstance(x.get("werte"), dict) and x["werte"]:
            out.append([L("Werte", "Values"), " · ".join(f"{w.get(k, k)[:3].upper()} {v}" for k, v in x["werte"].items())])
        if x.get("zustaende"):
            z = {c["id"]: _name(c, li) for c in r.get("zustaende") or []}
            out.append([L("Kann bewirken", "Can cause"), ", ".join(z.get(c, c) for c in x["zustaende"])])
            sg = x["sg"] if isinstance(x.get("sg"), int) else kampf.RETTUNG + int(x.get("stufe", 0) // 4)   # Kampf-Audit N6
            out.append([L("Rettungswurf dagegen", "Save against it"), L(f"SG {sg}", f"DC {sg}")])
        if x.get("groesse"):
            out.append([L("Größe", "Size"), str(x["groesse"])])
        a = arten(x)
        k = lambda i: f"{kampf.ART_ZEICHEN.get(i, '')} {kampf.ART_NAME[i][li]}".strip()       # noqa: E731
        out.append([L("Schadensart", "Damage kind"), k(a["art"]) if a["art"] in kampf.ART_NAME else ""])
        for f, de, enw in (("schwaeche", "Schwäche (doppelt)", "Weak to (double)"), ("resistenz", "Widerstand (halb)", "Resists (half)"),
                           ("immun", "Immun (kein Schaden)", "Immune (no damage)")):
            out.append([L(de, enw), ", ".join(k(i) for i in a[f])])
        if kampf.blows(x) > 1:                   # Tabletop-Punkt 12: the multiattack
            out.append([L("Angriffe je Zug", "Attacks a turn"), str(kampf.blows(x))])
        if x.get("boss"):
            out.append([L("Boss", "Boss"), L(f"+{int(kampf.BOSS_LEBEN * 100)} % Leben je Held ab dem zweiten, ab halbem Leben Phase 2 "
                                             f"(+{kampf.BOSS_PHASE} zum Treffen), mindestens zwei Angriffe je Zug, Fund eine Seltenheit besser",
                                             f"+{int(kampf.BOSS_LEBEN * 100)} % life per hero beyond the first, phase 2 at half life "
                                             f"(+{kampf.BOSS_PHASE} to hit), at least two attacks a turn, its find one rarity better")])
        out.append([L("EP je Held", "EP per hero"), " · ".join(f"{n}: {int(x.get('ep', 0)) // n}" for n in HELDEN)])
        wn = [_name(w, li) for w in r["welten"] if kampf.plays_in(r, x, w["id"])]
        out.append([L("Welten", "Worlds"), L("alle", "all") if len(wn) == len(r["welten"]) else ", ".join(wn)])
        if frisch(x):
            out.append([L("Neu", "New"), str(x["seit"])])
    elif teil == "tabellen":
        z = x.get("zeilen") or []
        wn = {w["id"]: _name(w, li) for w in r["welten"]}
        out += [[L("Gruppe", "Group"), GRUPPE.get(x.get("gruppe"), ("", ""))[li]], [L("Zeilen", "Rows"), str(len(z))],
                [L("Würfel", "Die"), (f"W{len(z)}" if not en else f"d{len(z)}") + L(", jede Zeile gleich oft; in einer Welt nur die Zeilen für sie",
                                                                                    ", every row as often; in a world only the rows for it")],
                [L("Nur in Welten", "Only in worlds"), ", ".join(sorted({wn.get(w, w) for y in z if isinstance(y, dict) for w in y.get("welten") or []}))]]
    elif teil == "zustaende":
        out += [[L("Wirkung", "Effect"), ", ".join(v.replace("_", " ") for v in x.get("wirkung") or [])]]
        if x.get("runden"):
            out.append([L("Dauer", "Lasts"), f"{x['runden']} " + L("Runden", "rounds")])
    return [z for z in out if z[1]]


def tafel(x, r, li):
    """A table's rows for the detail (Dominik 2026-10-25 „ich sehe gar nicht die tabellen“): the number, the text in the
    page's language and the worlds of a row that only counts in some."""
    wn = {w["id"]: _name(w, li) for w in r["welten"]}
    return [{"n": i + 1, "t": str(y["t"][li] if len(y["t"]) > li else y["t"][0]), "w": ", ".join(wn.get(w, w) for w in y.get("welten") or [])}
            for i, y in enumerate(x.get("zeilen") or []) if isinstance(y, dict) and isinstance(y.get("t"), list) and y["t"]]


def _welt_of(r, welt):
    """The world a people, class or background is shown and painted in: the one asked for if there is one, else the
    first."""
    ids = [w["id"] for w in r["welten"]]
    return welt if welt in ids else ids[0]


def view(teil, lang="de", welt=""):
    """{"teil", "zeilen": [...], "eintraege": {id: entry}}: the merged part with where each entry comes from; the people
    of the catalog from dungeon_personen (Personen-Katalog 1)."""
    if teil == "personen":
        return personen.view(lang)
    li = 1 if lang == "en" else 0
    r = dungeon.rules()
    welt = _welt_of(r, welt)
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
        row = {"id": i, "name": _name(x, li), "zeichen": x.get("zeichen") or dingbild.ZEICHEN.get(x.get("art"), "")
               or (TAB_ZEICHEN.get(i) or TAB_ZEICHEN.get(x.get("gruppe"), "") if teil == "tabellen" else ""),
               "zeile": line(teil, x, r, li), "werte": werte(teil, x, r, li), "stand": stand, "art": x.get("art", "")}
        if teil == "gegner":
            row["marke"] = balance.foe(x, lang)
            row["stufe"] = x.get("stufe", 0)
            row.update(welten=[w["id"] for w in r["welten"] if kampf.plays_in(r, x, w["id"])], boss=bool(x.get("boss")), frisch=frisch(x), arten=arten(x))
        elif teil == "tabellen":
            row["tafel"] = tafel(x, r, li)
        elif teil == "gegenstaende":
            row["marke"] = balance.item(x, lang)
            row["selten"] = x.get("seltenheit") or ""      # the frame's colour (dungeon.js DMSEL); "" = rolled
            if row["selten"] and x.get("art") in r["preise"]:   # Wirtschaft Punkt 1: a fixed rarity has its final price (0: a legend)
                row["preis"] = dungeon.price(r, {"id": i, "s": row["selten"]})
        if teil in MIT_BILD:
            n, _ = dingbild.entry_pic(r, teil, x, welt)
            row["bild"] = n if n in have else ""
            cur = dingbild._current(r, x, teil, welt)[0]
            row["neu"] = "neu-" + cur[5:] if "neu-" + cur[5:] in neu else ""
            row["bv"], row["nv"] = dungeon.bild_v(row["bild"]), dungeon.bild_v(row["neu"])   # the browser keeps it until it changes
        rows.append(row)
        entries[str(i)] = x
    out = {"teil": teil, "zeilen": rows, "eintraege": entries, "bilder_an": dingbild.on()}
    if teil in dingbild.HELD_TEILE:     # the world the pictures are in, and the worlds to choose from (dungeon.js)
        out.update(welt=welt, welten=[{"id": w["id"], "name": _name(w, li)} for w in r["welten"]])
    if teil == "gegner":             # the filters (worlds) and the symbols of the damage kinds (dungeon.js dmRArt)
        out.update(weltfilter=[{"id": w["id"], "name": _name(w, li)} for w in r["welten"]],
                   arten={a: {"zeichen": kampf.ART_ZEICHEN.get(a, ""), "name": kampf.ART_NAME[a][li]} for a in kampf.SCHADEN_ARTEN})
    if teil == "gegenstaende":       # the ladder a rolled item climbs (dungeon.rarity: W100 + 2 × level)
        ft = r["fundtabelle"]                        # the first level a rarity can be found at (Wirtschaft Punkt 5)
        ab = [1] + [next((i + 1 for i, z in enumerate(ft) if z[k] < dungeon.NIE), 0) for k in range(len(r["seltenheit"]) - 1)]
        out["seltenheiten"] = [{"id": s["id"], "name": _name(s, li), "bonus": s["bonus"], "stufe": a, "preis": s["preis"]}
                               for s, a in zip(r["seltenheit"], ab)]
    return out


def change(teil, was, i, eintrag=None):
    """One entry of the own rules set, hidden or taken back; refused (ValueError with the errors) unless the rules
    still pass. Returns the hint of the balance for the entry (or None). A person goes to dungeon_personen."""
    if teil == "personen":
        if not personen.admin_on():
            raise LookupError("personen aus")
        return personen.change(was, i, eintrag)
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
    x = (personen.load() if teil == "personen" else {str(k): v for k, v in dungeon._by(dungeon.rules(), teil).items()}).get(str(i))
    if not x:
        raise LookupError("eintrag")
    return x


@router.get("/api/admin/dungeon/katalog/{teil}", dependencies=[Depends(auth)])
async def katalog(teil: str, request: Request):
    guard.limit(request, "dungeonregel", admin=True)
    if teil not in ALLE:
        raise HTTPException(404, "teil")
    if teil == "personen" and not personen.admin_on():
        raise HTTPException(404, "personen aus")
    return dungeon.json_out(request, await asyncio.to_thread(view, teil, _lang(request), request.query_params.get("welt", "")[:40]))


@router.post("/api/admin/dungeon/katalog/{teil}", dependencies=[Depends(auth)])
async def katalog_change(teil: str, request: Request):
    guard.limit(request, "dungeonregel", admin=True)
    if teil not in ALLE:
        raise HTTPException(404, "teil")
    if teil == "personen" and not personen.admin_on():
        raise HTTPException(404, "personen aus")
    b = await json_body(request, BODY)
    i = str(b.get("id") or "")
    if not i or len(i) > 40:
        raise HTTPException(400, "id")
    try:
        hint = await asyncio.to_thread(change, teil, str(b.get("was") or ""), i, b.get("eintrag"))
    except ValueError as e:
        raise HTTPException(422, e.args[0] if e.args and isinstance(e.args[0], list) else ["eintrag"])
    except LookupError as e:
        raise dungeon._http(e)
    out = await asyncio.to_thread(view, teil, _lang(request), request.query_params.get("welt", "")[:40])
    out["hinweis"] = hint
    return out


@router.post("/api/admin/dungeon/katalog/{teil}/bild", dependencies=[Depends(auth)])
async def katalog_bild(teil: str, request: Request):
    """„Nochmal malen“ (was "malen"), then „Neues behalten“ ("neu") or „Altes behalten“ ("alt")."""
    guard.limit(request, "dungeonbild", admin=True)
    if teil not in MIT_BILD and not (teil == "personen" and personen.admin_on()):   # a person's face (Dominik 2026-10-27)
        raise HTTPException(404, "teil")
    b = await json_body(request, 2000)
    was = b.get("was")
    try:
        c = await asyncio.to_thread(_entry, teil, str(b.get("id") or ""))
        r = dungeon.rules()
        welt = _welt_of(r, str(b.get("welt") or ""))
        if was == "malen":
            why, neu = await dingbild.repaint(r, c, True, teil, welt)   # only an admin reaches this: no day limit
            if why != "ok":
                raise HTTPException(409, why)
            if not dingbild.entry_pic(r, teil, c, welt)[1]:   # „🖌 Malen“ of a missing picture: nothing to compare
                await asyncio.to_thread(dingbild.settle, r, c, True, teil, welt)
                return {"neu": "", "bild": dingbild.entry_pic(r, teil, c, welt)[0]}
            return {"neu": neu}
        if was not in ("neu", "alt"):
            raise HTTPException(400, "was")
        await asyncio.to_thread(dingbild.settle, r, c, was == "neu", teil, welt)
        return {"ok": True}
    except LookupError as e:
        raise dungeon._http(e)


@router.get("/api/admin/dungeon/bild/{name}", dependencies=[Depends(auth)])
async def bild(name: str, request: Request, klein: int = 0):
    """klein=1: the small copy for the list (dungeon.small_png; Dominik 2026-10-25: 391 full pictures held up the panel)."""
    guard.limit(request, "dungeonding", admin=True)
    if not (dingbild.NAME.fullmatch(name) or dingbild.NEU.fullmatch(name)):
        raise HTTPException(404, "bild")
    try:
        return dungeon._png_out(await asyncio.to_thread(dungeon.small_png if klein else dungeon._png, name))
    except LookupError as e:
        raise dungeon._http(e)


def counts():
    """Numbers for Live: own entries per part, hidden ones, candidates waiting."""
    own = dungeon.own_rules()
    own = own if isinstance(own, dict) else {}
    lst = [x for t in TEILE for x in own.get(t) or [] if isinstance(x, dict)]
    return {"eigene": sum(1 for x in lst if not x.get("aus")), "aus": sum(1 for x in lst if x.get("aus")),
            "kandidaten": len(dingbild.candidates()), "json": len(json.dumps(own))}
