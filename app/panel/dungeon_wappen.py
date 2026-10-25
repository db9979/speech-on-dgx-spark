"""KI-Dungeon-Master: Wappen für Gruppe und Fraktionen (D&D-Idee 10 of 2026-10-25, Dominik „1-12 reihenfolge bestimmst
du wie du alles umsetzten kannst.“, plan /mnt/project-files/plaene/dungeon-dnd-ideen.md; the way of building a coat of
arms from shield, division, tinctures and charge follows Azgaar/Armoria (MIT), own code and own drawings, no part of
WappenWiki, no picture model).

Every coat of arms is built by the panel from a start value, the same every time: shield shape, division, two
tinctures by the old rule (a metal next to a colour), a charge of own simple drawings (CHARGES) in a tincture that
stands out (on a divided field the two tinctures change sides, „verwechselt“). The group's arms come from the round
(its campaign, so they stay from chapter to chapter); the host chooses colour and charge at the start or later
(the rest stays). Each faction (dungeon_fraktionen) gets its own arms from its name, never the group's colour with
the group's charge. A code names an arms (shield-division-tincture-tincture-charge-tincture, every part a word of the
fixed lists below); svg(code) builds the picture and checks it (check: only the elements and attributes of ERLAUBT,
no script, no link, no style), so a seat only ever gets an SVG of the panel's own parts. Only while „Wappen für Gruppe
und Fraktionen“ (features "dungeonwappen", admin switch chat.dungeon_wappen, off) is allowed for the round's host.

    users/<id>/dungeon-wappen.json   {"wahl": {"k:<campaign>" | "r:<round's start>": {"farbe", "zeichen"}}}
                                     the host's choices, at most WAHL_MAX; the hourly sweep drops those of rounds and
                                     campaigns that are gone

The view (dungeon.view through dungeon_dingbild.add, before the sight filter): wappen {gruppe: code, fr: {faction in
small letters: code} for the factions the seat already sees (their clocks, their banner on the map), svg: {code: svg}},
the host's view also the codes of every faction (fraktionen_geheim.alle[].wappen) and the choice (wappen.wahl).
dungeonwappen.js shows them (dmWappen, dmWappenFr, dmWappenGruppe, dmWappenHref for the map). Mails, chapter covers
and the chronicle take gruppe(rd), fraktion(rd, name) and svg(code). Journal lines „dungeon: wappen | …“, fixed words
and numbers only; Live: numbers only.

    POST /api/profile/dungeon/{rid}/wappen    {farbe, zeichen, lang}: the host chooses the group's colour and charge
                                              ({} or "zufall": back to the arms of the start value)
"""
import asyncio
import functools
import hashlib
import random
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import features
import guard
import profiles
from common import DayCounter, read_json, write_json
from core import assistant, browser_profile, json_body

router = APIRouter()

KEY = "dungeonwappen"
DATEI = "dungeon-wappen.json"
WAHL_MAX = 50
SVG_MAX = 8000             # a built arms is far below; check refuses anything longer
W, H = 200, 220            # the shield's box

METALLE = {"gold": ("Gold", "Gold", "#f0bf2c"), "silber": ("Silber", "Silver", "#f3f3ee")}
FARBEN = {"rot": ("Rot", "Red", "#c42032"), "blau": ("Blau", "Blue", "#1f4f9e"), "gruen": ("Grün", "Green", "#2b7a3c"),
          "purpur": ("Purpur", "Purple", "#76388c"), "schwarz": ("Schwarz", "Black", "#28272d")}
TINKTUREN = {**METALLE, **FARBEN}

SCHILDE = {   # own outlines in the 200 × 220 box
    "spitz": "M10 8H190V96C190 152 150 190 100 212C50 190 10 152 10 96Z",
    "rund": "M10 8H190V122A90 90 0 0 1 10 122Z",
    "franz": "M10 8H190V168Q190 194 162 196H128Q106 198 100 214Q94 198 72 196H38Q10 194 10 168Z",
    "tartsche": "M100 6C156 6 190 30 190 84C190 146 150 186 100 214C50 186 10 146 10 84C10 30 44 6 100 6Z",
    "zacken": "M10 8L40 18L70 8H130L160 18L190 8V120C190 168 150 196 100 214C50 196 10 168 10 120Z",
}
# the part of the field in the second tincture (one path, its parts never overlap); "bord" and "haupt" are drawn apart
TEILUNGEN = {
    "schlicht": "",
    "gespalten": "M100 0H200V220H100Z",
    "geteilt": "M0 110H200V220H0Z",
    "schraeg": "M0 0L200 220H0Z",
    "schraeglinks": "M200 0V220H0Z",
    "geviert": "M100 0H200V110H100ZM0 110H100V220H0Z",
    "sparren": "M0 220V186L100 86L200 186V220Z",
    "schraegkreuz": "M0 0H200L100 110ZM0 220L100 110L200 220Z",
    "haupt": "M0 0H200V64H0Z",
    "bord": "",
}
VERWECHSELT = ("gespalten", "geteilt", "schraeg", "schraeglinks", "geviert", "sparren", "schraegkreuz")
LAGE = {"haupt": (100, 142, .86), "bord": (100, 112, .92)}   # where the charge stands and how big (else LAGE_SONST)
LAGE_SONST = (100, 108, 1.15)
BORD = "translate(100 112) scale(.8) translate(-100 -112)"


def _stern(spitzen, aussen, innen, dreh=-90):
    import math
    p = []
    for i in range(spitzen * 2):
        r, a = (aussen if i % 2 == 0 else innen), math.radians(dreh + i * 180 / spitzen)
        p.append(f"{r * math.cos(a):.1f} {r * math.sin(a):.1f}")
    return "M" + "L".join(p) + "Z"


def _sonne():
    import math
    rays = []
    for i in range(12):
        a, b = math.radians(i * 30 - 7.5), math.radians(i * 30 + 7.5)
        m = math.radians(i * 30)
        rays.append(f"M{27 * math.cos(a):.1f} {27 * math.sin(a):.1f}L{48 * math.cos(m):.1f} {48 * math.sin(m):.1f}"
                    f"L{27 * math.cos(b):.1f} {27 * math.sin(b):.1f}Z")
    return "M-22 0A22 22 0 1 0 22 0A22 22 0 1 0 -22 0Z" + "".join(rays)


_RUND = "M{a} {y}A{r} {r} 0 1 0 {b} {y}A{r} {r} 0 1 0 {a} {y}Z"


def _kreis(x, y, r):
    return _RUND.format(a=x - r, b=x + r, y=y, r=r)


# own drawings in a box of -50 … 50 around the middle (fill-rule evenodd: a part inside another is a hole)
CHARGES = {
    "stern": (("Stern", "Star"), _stern(5, 47, 19)),
    "sonne": (("Sonne", "Sun"), _sonne()),
    "mond": (("Mond", "Moon"), "M14 -44A46 46 0 1 0 14 44A50 50 0 0 1 14 -44Z"),
    "kreuz": (("Kreuz", "Cross"), "M-12 -46H12V-12H46V12H12V46H-12V12H-46V-12H-12Z"),
    "raute": (("Raute", "Lozenge"), "M0 -48L34 0L0 48L-34 0Z"),
    "ring": (("Ring", "Ring"), _kreis(0, 0, 40) + _kreis(0, 0, 25)),
    "herz": (("Herz", "Heart"), "M0 44C-8 32 -46 12 -46 -14C-46 -34 -30 -44 -18 -44C-8 -44 -2 -38 0 -30C2 -38 8 -44 18 -44"
                                "C30 -44 46 -34 46 -14C46 12 8 32 0 44Z"),
    "schwert": (("Schwert", "Sword"), "M0 -52L7 -42V14H-7V-42ZM-26 14H26V22H-26ZM-4 22H4V39H-4Z" + _kreis(0, 45, 6)),
    "turm": (("Turm", "Tower"), "M-32 -46H-20V-36H-6V-46H6V-36H20V-46H32V-22H-32ZM-26 -22H26V48H-26Z"
                                "M-9 48V30A9 9 0 0 1 9 30V48ZM-4 -10H4V4H-4Z"),
    "krone": (("Krone", "Crown"), "M-40 28L-46 -24L-22 2L0 -38L22 2L46 -24L40 28ZM-40 32H40V44H-40Z"
                                  + _kreis(-46, -31, 5) + _kreis(0, -45, 5) + _kreis(46, -31, 5)),
    "schluessel": (("Schlüssel", "Key"), _kreis(0, -30, 16) + _kreis(0, -30, 8) + "M-4 -14H4V48H-4ZM4 30H18V38H4ZM4 42H14V48H4Z"),
    "baum": (("Baum", "Tree"), "M0 -48C18 -48 30 -36 30 -22C42 -18 46 -6 40 6C36 16 24 18 14 14H-14C-24 18 -36 16 -40 6"
                               "C-46 -6 -42 -18 -30 -22C-30 -36 -18 -48 0 -48ZM-7 14H7V46H-7Z"),
    "berg": (("Berg", "Mountain"), "M-48 44L-24 -4L-12 12L4 -40L26 4L34 -8L48 44Z"),
    "blitz": (("Blitz", "Lightning"), "M8 -50L-26 6H-2L-12 50L28 -10H4L18 -50Z"),
    "kelch": (("Kelch", "Chalice"), "M-30 -40H30C30 -12 18 4 0 6C-18 4 -30 -12 -30 -40ZM-4 6H4V34H-4ZM-22 34H22L26 46H-26Z"),
    "fisch": (("Fisch", "Fish"), "M-46 0C-30 -20 0 -24 22 -8L44 -24V24L22 8C0 24 -30 20 -46 0Z" + _kreis(-27, -4, 4)),
}

CODE = re.compile("-".join((f"({'|'.join(SCHILDE)})", f"({'|'.join(TEILUNGEN)})", f"({'|'.join(TINKTUREN)})",
                            f"({'|'.join(TINKTUREN)})", f"({'|'.join(CHARGES)})", f"({'|'.join(TINKTUREN)}|x)")))

ERLAUBT = {"svg": {"xmlns", "viewBox"}, "defs": set(), "g": {"clip-path"}, "clipPath": {"id"},
           "radialGradient": {"id", "cx", "cy", "r"}, "stop": {"offset", "stop-color", "stop-opacity"},
           "rect": {"width", "height", "fill"},
           "path": {"d", "fill", "fill-rule", "clip-rule", "transform", "stroke", "stroke-width", "stroke-opacity", "stroke-linejoin"}}
_WERT = re.compile(r"[#0-9A-Za-z .,\-]*|url\(#[a-z0-9-]+\)")
_DREH = re.compile(r"((translate\(-?[0-9.]+ -?[0-9.]+\)|scale\([0-9.]+\)) ?)+")   # transform: only moving and sizing
_NS = "http://www.w3.org/2000/svg"

NEIN = {"aus": ("Für diese Runde sind „Wappen für Gruppe und Fraktionen“ nicht freigegeben.",
                "Coats of arms for group and factions are not released for this round."),
        "wert": ("Diese Farbe oder dieses Zeichen gibt es nicht.", "There is no such colour or charge.")}


class SvgFremd(ValueError):
    """An SVG that is not only of the panel's own parts (check); never goes to a page."""


class Nein(ValueError):
    """A refusal of the host's choice ("aus" | "wert"); the endpoint answers with its own sentence (NEIN), not through
    dungeon._http and its table of reasons."""


_lock = threading.Lock()
_sweep = [0.0]
_day = DayCounter(gewaehlt=0, abgelehnt=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _rng(seed):
    return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))


def make(seed, farbe=None, zeichen=None):
    """The code of the arms of a start value; farbe and zeichen (the host's choice) take the place of the drawn ones,
    everything else stays (every value is drawn, chosen or not)."""
    g = _rng(seed)
    schild, teilung = g.choice(list(SCHILDE)), g.choice(list(TEILUNGEN))
    t1, z, u2, uz = g.choice(list(TINKTUREN)), g.choice(list(CHARGES)), g.random(), g.random()
    t1 = farbe if farbe in TINKTUREN else t1
    z = zeichen if zeichen in CHARGES else z
    gegen = list(FARBEN if t1 in METALLE else METALLE)          # a metal next to a colour, a colour next to a metal
    t2 = gegen[int(u2 * len(gegen))]
    if teilung in VERWECHSELT:
        tz = "x"
    else:
        frei = [k for k in gegen if k != t2]
        tz = frei[int(uz * len(frei))]
    return "-".join((schild, teilung, t1, t2, z, tz))


def _parts(code):
    m = CODE.fullmatch(str(code or ""))
    return m.groups() if m else None


def check(svg):
    """The arms' SVG only of the elements and attributes of ERLAUBT, values without anything that could fetch or run
    (only url(#…) to a part of the same picture). Raises SvgFremd (a ValueError) otherwise."""
    from defusedxml import ElementTree as DET
    if not isinstance(svg, str) or len(svg) > SVG_MAX:
        raise SvgFremd()
    try:
        root = DET.fromstring(svg)
    except Exception:
        raise SvgFremd()
    if root.tag != f"{{{_NS}}}svg":
        raise SvgFremd()
    for el in root.iter():
        tag = el.tag[len(_NS) + 2:] if el.tag.startswith(f"{{{_NS}}}") else None
        if tag not in ERLAUBT or (el.text or "").strip() or (el.tail or "").strip():
            raise SvgFremd()
        for k, v in el.attrib.items():
            if k not in ERLAUBT[tag] or not (_DREH if k == "transform" else _WERT).fullmatch(v):
                raise SvgFremd()


@functools.lru_cache(maxsize=256)
def svg(code):
    """The checked SVG of a code ("" for anything that is not a code)."""
    p = _parts(code)
    if not p:
        return ""
    schild, teilung, t1, t2, z, tz = p
    i = "w" + hashlib.sha256(code.encode()).hexdigest()[:8]   # own ids: two arms inline in one mail never mix
    sh, div, ch = SCHILDE[schild], TEILUNGEN[teilung], CHARGES[z][1]
    x, y, s = LAGE.get(teilung, LAGE_SONST)
    tr = f"translate({x} {y}) scale({s})"

    def charge(fill):
        return (f'<path d="{ch}" transform="{tr}" fill="{TINKTUREN[fill][2]}" fill-rule="evenodd" stroke="#000" '
                f'stroke-opacity=".45" stroke-width="2.4" stroke-linejoin="round"/>')
    defs = [f'<clipPath id="{i}-s"><path d="{sh}"/></clipPath>',
            f'<radialGradient id="{i}-g" cx=".32" cy=".26" r=".85"><stop offset="0" stop-color="#fff" stop-opacity=".38"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".22"/></radialGradient>']
    body = [f'<rect width="{W}" height="{H}" fill="{TINKTUREN[t1][2]}"/>']
    if teilung == "bord":
        body = [f'<rect width="{W}" height="{H}" fill="{TINKTUREN[t2][2]}"/>',
                f'<path d="{sh}" transform="{BORD}" fill="{TINKTUREN[t1][2]}" stroke="#000" stroke-opacity=".3" stroke-width="2"/>']
    elif div:
        body.append(f'<path d="{div}" fill="{TINKTUREN[t2][2]}"/>')
    if tz == "x":
        defs += [f'<clipPath id="{i}-a"><path d="{div}"/></clipPath>',
                 f'<clipPath id="{i}-b"><path d="M0 0H{W}V{H}H0Z{div}" clip-rule="evenodd"/></clipPath>']
        body += [f'<g clip-path="url(#{i}-a)">{charge(t1)}</g>', f'<g clip-path="url(#{i}-b)">{charge(t2)}</g>']
    else:
        body.append(charge(tz))
    out = (f'<svg xmlns="{_NS}" viewBox="0 0 {W} {H}"><defs>{"".join(defs)}</defs>'
           f'<g clip-path="url(#{i}-s)">{"".join(body)}<path d="{sh}" fill="url(#{i}-g)"/></g>'
           f'<path d="{sh}" fill="none" stroke="#000" stroke-opacity=".6" stroke-width="5" stroke-linejoin="round"/></svg>')
    check(out)
    return out


@functools.lru_cache(maxsize=32)
def zeichen_svg(z):
    """A charge alone, for the host's choice (gold with a dark edge: seen on a light and a dark page)."""
    if z not in CHARGES:
        return ""
    out = (f'<svg xmlns="{_NS}" viewBox="-56 -56 112 112"><path d="{CHARGES[z][1]}" fill="{METALLE["gold"][2]}" fill-rule="evenodd" '
           f'stroke="#000" stroke-opacity=".6" stroke-width="3" stroke-linejoin="round"/></svg>')
    check(out)
    return out


def stamm(rd):
    """What the group's arms hang on: the campaign (they stay from chapter to chapter), else the round's start."""
    return f"k:{rd['kid']}" if rd.get("kid") else f"r:{rd.get('made', 0)}"


def _file(uid):
    return profiles._path(uid, DATEI)


def _choices(uid):
    d = read_json(_file(uid), {})
    w = d.get("wahl") if isinstance(d, dict) else None
    return w if isinstance(w, dict) else {}


def _group(rd, wahl=None):
    w = (wahl if wahl is not None else _choices(rd["owner"])).get(stamm(rd)) or {}
    return make(f"gruppe|{rd['owner']}|{stamm(rd)}", w.get("farbe"), w.get("zeichen"))


def gruppe(rd):
    """The code of the group's arms ("" while off)."""
    return _group(rd) if on(rd) else ""


def _faction(rd, name, group):
    g = _parts(group)
    for n in range(6):          # never the group's colour with the group's charge
        c = make(f"fraktion|{rd['owner']}|{stamm(rd)}|{str(name).strip().lower()}|{n}")
        p = _parts(c)
        if not g or (p[2], p[4]) != (g[2], g[4]):
            return c
    return c


def fraktion(rd, name):
    """The code of a faction's arms ("" while off or without a name)."""
    return _faction(rd, name, _group(rd)) if on(rd) and str(name or "").strip() else ""


def _wahl_view(rd, wahl, li):
    w = wahl.get(stamm(rd)) or {}
    return {"farbe": w.get("farbe") or "", "zeichen": w.get("zeichen") or "",
            "farben": [[k, v[li], v[2]] for k, v in TINKTUREN.items()], "zeichen_alle": [[k, v[0][li], zeichen_svg(k)] for k, v in CHARGES.items()]}


def add(rd, out):
    """dungeon.view (through dungeon_dingbild.add): the codes and their SVG a seat may see (see above)."""
    if not on(rd):
        return out
    wahl = _choices(rd["owner"])
    g = _group(rd, wahl)
    names = {str(u.get("name", "")).lower() for u in ((out.get("fraktionen") or {}).get("uhren") or [])}
    names |= {str(o["fr"]).lower() for o in ((out.get("karte") or {}).get("orte") or []) if o.get("fr")}
    fr = {n: _faction(rd, n, g) for n in sorted(names) if n}
    codes = {g, *fr.values()}
    for x in (out.get("fraktionen_geheim") or {}).get("alle") or []:
        x["wappen"] = _faction(rd, x.get("name", ""), g)
        codes.add(x["wappen"])
    out["wappen"] = {"gruppe": g, "fr": fr, "svg": {c: svg(c) for c in sorted(codes)}}
    if out.get("gastgeber"):
        out["wappen"]["wahl"] = _wahl_view(rd, wahl, 1 if out.get("lang") == "en" else 0)
    return out


def choose(uid, rid, b):
    """The host's choice of the group's colour and charge ({} or zufall: the start value's again). Raises LookupError
    or Nein("aus" | "wert")."""
    rd = dungeon._round(dungeon._read(), rid)
    if rd["owner"] != uid or rd.get("status") != "laeuft":
        raise LookupError("runde")
    if not on(rd):
        _day.bump("abgelehnt")
        print("dungeon: wappen | abgelehnt | aus", flush=True)
        raise Nein("aus")
    farbe, zeichen = b.get("farbe") or "", b.get("zeichen") or ""
    if (farbe and farbe not in TINKTUREN) or (zeichen and zeichen not in CHARGES):
        _day.bump("abgelehnt")
        print("dungeon: wappen | abgelehnt | wert", flush=True)
        raise Nein("wert")
    with _lock:
        wahl = _choices(uid)
        k = stamm(rd)
        wahl.pop(k, None)
        if (farbe or zeichen) and b.get("zufall") is not True:
            wahl[k] = {"farbe": farbe, "zeichen": zeichen}
        while len(wahl) > WAHL_MAX:
            wahl.pop(next(iter(wahl)))
        write_json(_file(uid), {"wahl": wahl}, mode=0o600)
    _day.bump("gewaehlt")
    print(f"dungeon: wappen | gewaehlt | {'zufall' if k not in wahl else 'eigen'}", flush=True)


def sweep(now):
    """At most every hour: the choices of rounds and campaigns that are gone."""
    if now - _sweep[0] < 3600:
        return 0
    _sweep[0] = now
    rs = dungeon._read()["runden"].values()
    gone = 0
    for uid in profiles.user_ids():
        with _lock:
            wahl = _choices(uid)
            if not wahl:
                continue
            da = {stamm(v) for v in rs if v.get("owner") == uid} | {f"k:{kid}" for kid in dungeon.campaigns(uid)}
            keep = {k: v for k, v in wahl.items() if k in da}
            if len(keep) < len(wahl):
                gone += len(wahl) - len(keep)
                write_json(_file(uid), {"wahl": keep}, mode=0o600)
    if gone:
        print(f"dungeon: wappen | aufgeraeumt | {gone} wahlen", flush=True)
    return gone


def for_live():
    """Numbers only: rounds with arms, own choices, chosen and refused today."""
    if not features.admin_on(KEY):
        return {"on": False}
    rs = [v for v in dungeon._read()["runden"].values() if v.get("status") == "laeuft"]
    return {"on": True, "runden": sum(1 for v in rs if on(v)), **_day.counts()}


@router.post("/api/profile/dungeon/{rid}/wappen", dependencies=[Depends(assistant)])
async def wappen_wahl(rid: str, request: Request, prof=Depends(browser_profile)):
    """{farbe, zeichen, zufall, lang}: the host chooses the group's colour and charge."""
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dungeon.BODY)
    try:
        await asyncio.to_thread(choose, uid, rid, b)
    except Nein as e:
        raise HTTPException(409 if str(e) == "aus" else 400, NEIN[str(e)][1 if dungeon._lang(b) == "en" else 0])
    except LookupError as e:
        raise dungeon._http(e)
    return await asyncio.to_thread(dungeon.view, rid, dungeon._seat_uid(rid, uid))
