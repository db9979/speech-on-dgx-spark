"""KI-Dungeon-Master: the balance bench „Balance-Prüfstand“ (Dominik 2026-10-24 „alle umsetzen“, Idee 5): the panel
plays thousands of fights alone, with the real rules and dice of dungeon_kampf (attacks, foes_turn, hurt, suffers,
flees, expire) and the merged catalog, for every level and group size, without the model and without a round. The
admin sees under Regeln how often the group wins and how much life it loses; a self-test keeps the aim (AIM, 70 to 90
per cent wins at „mittel“).

- A group: GRUPPE_MAX heroes at most, the classes in turn (krieger, magier, dieb, heiler, waldlaeufer), the first
  people, built like a player's hero (dungeon.new_hero) and raised to the level; gear by fixed numbers (GEAR): the
  first weapon of its class and the best body armour it may wear up to the level's price, both of the rarity a mean
  find of that level has.
- An encounter of the danger asked: one or two kinds of the whole bestiary, counted until the adjusted experience
  against the budget gives that danger (dungeon_kampf.danger), drawn by the seed.
- A fight: each turn every standing hero drinks its healing potion below a third of its life, else attacks the foe
  with the least life (a class with an attack spell of grade 0 casts it); then the foes' turn. Won when no foe is
  up, lost when no hero stands, RUNDEN turns at most.

The economy (Wirtschaft Punkt 6, Dominik 2026-10-25 „1-12“, economy()): per level LAEUFE runs of a group of GRUPPE_W
heroes through the fights a level takes (the experience to the next level, a quarter from riddles, places and acts),
a chest every third fight, a reward and every other level a boss, every find by dungeon.loot and sold to a merchant of
a drawn kind, never more than its purse holds; against it what a hero spends in normal play: the inn every fourth
fight, a healing potion for a third of its life every second fight, two rumours and a smith shared by the group. A
lesson and „Ausrüstung verbessern“ are what the surplus is for. The self-test keeps income to expenses (median) within
WIRTSCHAFT and no find worth more than JACKPOT times a level's income.

The night's run (NACHT, once a night) and the admin's „Jetzt durchspielen“ write the table into STATE/dungeon-pruefstand.json
(dateien.py): {"zeit", "kaempfe", "gefahr", "zellen": {"stufe/gruppe": {"siege", "leben", "runden"}},
"wirtschaft": {"stufe": {"kaempfe", "einnahmen", "zehntel", "ausgaben", "verhaeltnis", "fund_max"}}}. Only while
„Balance-Prüfstand“ is on (features.py, below the Dungeon-Master).

    GET  /api/admin/dungeon/pruefstand         the last table, the aim, whether it is on and running
    POST /api/admin/dungeon/pruefstand         „Jetzt durchspielen“ (rate-limited, one run at a time)

Journal lines „dungeon: pruefstand | …“ with fixed words and numbers only.
"""
import asyncio
import os
import random
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_gold as gold
import dungeon_kampf as kampf
import features
import guard
from common import STATE, read_json, write_json
from core import auth, json_body

router = APIRouter()
FILE = os.path.join(STATE, "dungeon-pruefstand.json")
AIM = (70, 90)                 # per cent wins at „mittel“ the self-test keeps
GRUPPE_MAX = 5
KAEMPFE = 200                  # fights per level and group size at night and on the button
RUNDEN = 30                    # turns of one fight at most
NACHT = (2, 5)                 # the night window, local hours [from, to)
TRANK = 3                      # a hero drinks its potion at a third of its life or less
GEAR = ((1, 20), (3, 45), (6, 80), (9, 120))   # (from level, the dearest body armour a hero of it wears)
# the rarity of the gear a group of a level typically wears (levels 1 to 10, beyond the last); a fixed assumption of
# the bench, apart from the find table (dungeon.find_row), so a new table never moves the aim by itself
GEAR_SELTEN = ("gewoehnlich", "gewoehnlich", "selten", "selten", "selten", "selten", "rar", "rar", "episch", "episch")
WIRTSCHAFT = (1.2, 2.0)        # income ÷ expenses of a hero per level (median) the self-test keeps (Wirtschaft Punkt 6)
JACKPOT = 10                   # no single find sells for more than this many times a level's income
LAEUFE = 200                   # runs per level of the economy
GRUPPE_W = 4                   # heroes of the economy's group
RAETSEL = 0.25                 # the part of the experience from riddles, places and acts (no fight, no find)
KNOPF_S = 60                   # „Jetzt durchspielen“ at most once a minute
clock = time.time              # the tests set it (no wall clock in a test)
_lock = threading.Lock()
_run = {"laeuft": False, "seit": 0}


def on():
    return features.admin_on("dungeonpruefstand")


# ---------------------------------------------------------------- a group
def _armour(r, klasse, stufe):
    """The best body armour (schutz, then the cheaper) of the class up to the level's price."""
    bis = max(p for ab, p in GEAR if stufe >= ab)
    fit = [x for x in r["gegenstaende"] if x["art"] == "ruestung" and not x.get("platz") and x.get("preis", 0) <= bis
           and (not x.get("klassen") or klasse in x["klassen"])]
    return max(fit, key=lambda x: (x.get("schutz", 0), -x.get("preis", 0), x["id"]), default=None)


def party(r, n, stufe, rng):
    """n heroes of this level, the classes in turn, ready for a fight."""
    ks = [k["id"] for k in r["klassen"]]
    volk = r["voelker"][0]["id"]
    selten = GEAR_SELTEN[min(len(GEAR_SELTEN), max(1, stufe)) - 1]
    out = []
    for i in range(n):
        k = ks[i % len(ks)]
        h = dungeon.new_hero(r, {"name": f"Held {i + 1}", "volk": volk, "klasse": k}, rng)
        h["stufe"] = stufe
        h["leben"] = h["leben_max"] = dungeon.life(r, h)
        h["an"]["haupthand"] = dungeon.item(r, dungeon._by(r, "klassen")[k]["waffen"][0], selten, rng)
        a = _armour(r, k, stufe)
        if a:
            h["an"]["koerper"] = dungeon.item(r, a["id"], selten, rng)
        out.append(h)
    return out


def _spell(r, h):
    """The class's attack spell of grade 0 (a blessing with its own die in dungeon_kampf.attacks), "" for none."""
    cat = dungeon._by(r, "gegenstaende")
    z = (dungeon._by(r, "klassen")[h["klasse"]].get("zauber") or {}).get("0") or []
    return next((x for x in z if x in cat and cat[x].get("segen") and cat[x].get("schaden_art")), "")


# ---------------------------------------------------------------- an encounter
def encounter(r, held, gefahr, rng, tries=200, pool=None):
    """[(catalog foe, count)] of the danger asked, one or two kinds, [] when none fits; pool: only these foes (the
    templates people fight with, weighted: dungeon_personen.pool)."""
    b = kampf.budget(dungeon, r, {}, held)
    fit = [g for g in (r.get("gegner") or [] if pool is None else pool) if 0 < g["ep"] <= b * kampf.SCHWER]
    if not fit:
        return []
    for _ in range(tries):
        kinds = rng.sample(fit, min(len(fit), rng.choice((1, 2))))
        wahl = [(g, rng.randint(1, kampf.ANZAHL_MAX)) for g in kinds]
        flat = [g for g, n in wahl for _ in range(n)]
        if len(flat) <= kampf.GEGNER_MAX and kampf.danger(kampf.adjusted(flat, len(held)), b) == gefahr:
            return wahl
    return []


# ---------------------------------------------------------------- a fight
def fight(r, held, wahl, rng):
    """One fight to its end: {"sieg": bool, "leben": share of the group's life lost, "runden"}."""
    rd = {"lang": "de", "zug": 0, "offen": {}, "log": [],
          "plaetze": {f"p{i}": {"held": h, "made": i} for i, h in enumerate(held)}}
    rd["kampf"] = {"gegner": kampf.lineup(wahl, 0, len(held))}
    voll = sum(h["leben"] for h in held)
    spells = {f"p{i}": _spell(r, h) for i, h in enumerate(held)}
    n = 0
    for n in range(1, RUNDEN + 1):
        rd["zug"] = n
        rd["offen"] = {}                         # a new turn: only this turn's actions, like the table
        kampf.expire(dungeon, rd)
        proben = []
        for pid, p in dungeon.seated(rd):
            h = p["held"]
            if dungeon.zustand(h):
                continue
            trank = next((it for it in h["tasche"] if dungeon._c(r, it).get("heilung") and dungeon._c(r, it)["art"] == "trank"), None)
            if trank and h["leben"] * TRANK <= h["leben_max"]:
                h["tasche"].remove(trank)
                dungeon.heal(h, dungeon._c(r, trank)["heilung"] + trank.get("bonus", 0))
                continue
            g = min(kampf.up(rd), key=lambda x: (x["leben"], x["k"]))
            rd["offen"][pid] = {"text": f"Ich greife {g['name']} an.", **({"kraft": spells[pid]} if spells[pid] else {})}
            proben.append({"pid": pid, "ziel": g["name"], "vt": ""})
        _, hits = kampf.attacks(dungeon, r, rd, proben, rng)
        by = {g["k"]: g for g in rd["kampf"]["gegner"]}
        for x in hits:
            if x["treffer"] and not by[x["ziel"]]["aus"]:
                kampf.hurt(by[x["ziel"]], x["schaden"])
        if kampf.up(rd):
            seats = dict(dungeon.seated(rd))
            for x in kampf.foes_turn(dungeon, r, rd, hits, rng):
                h = seats[x["pid"]]["held"]
                if dungeon.zustand(h) or (x.get("k") and by[x["k"]]["aus"]):
                    continue
                if x.get("zustand_schaden") or x["treffer"]:
                    h["leben"] = max(0, h["leben"] - x["schaden"])
                if x.get("rettung"):
                    kampf.suffers(r, rd, h, x["rettung"])
            for g in kampf.up(rd):
                kampf.flees(g, rng)
        if not kampf.up(rd) or all(dungeon.zustand(h) for h in held):
            break
    sieg = not kampf.up(rd)
    return {"sieg": sieg, "leben": 1 - sum(max(0, h["leben"]) for h in held) / max(1, voll), "runden": n}


def cell(r, stufe, gruppe, gefahr, kaempfe, seed, pool=None):
    """The bench for one level and group size: {"siege": per cent, "leben": per cent lost in the won fights,
    "runden": mean turns}; None when no encounter of the danger fits."""
    rng = random.Random(f"{seed}|{stufe}|{gruppe}|{gefahr}")
    won, lost, runden, n = 0, [], 0, 0
    for _ in range(kaempfe):
        held = party(r, gruppe, stufe, rng)
        wahl = encounter(r, held, gefahr, rng, pool=pool)
        if not wahl:
            continue
        x = fight(r, held, wahl, rng)
        n += 1
        runden += x["runden"]
        if x["sieg"]:
            won += 1
            lost.append(x["leben"])
    if not n:
        return None
    return {"siege": round(100 * won / n), "leben": round(100 * sum(lost) / max(1, len(lost))), "runden": round(runden / n, 1)}


def bench(r, kaempfe=KAEMPFE, gefahr="mittel", seed="pruefstand", stufen=None, gruppen=None, pool=None):
    """The whole table {"stufe/gruppe": cell}; a cell without a fitting encounter is left out. pool: only these foes."""
    out = {}
    for s in stufen or range(1, r["grenzen"]["stufe_max"] + 1):
        for g in gruppen or range(1, GRUPPE_MAX + 1):
            c = cell(r, s, g, gefahr, kaempfe, seed, pool)
            if c:
                out[f"{s}/{g}"] = c
    return out


def economy(r, laeufe=LAEUFE, seed="wirtschaft", stufen=None):
    """The economy per level {"stufe": {"kaempfe", "einnahmen" (median of a hero), "zehntel" (the worst tenth),
    "ausgaben", "verhaeltnis", "fund_max" (the most one find sold for)}} by the real loot, prices and services."""
    out = {}
    welt = r["welten"][0]["id"]
    ep = r["stufen_ep"]
    for stufe in stufen or range(1, r["grenzen"]["stufe_max"] + 1):
        rng = random.Random(f"{seed}|{stufe}")
        dxp = ep[stufe] - ep[stufe - 1] if stufe < len(ep) else ep[-1] - ep[-2]
        kaempfe = max(1, round((1 - RAETSEL) * dxp / kampf.BUDGET[stufe - 1]))
        kasse = kaempfe / 4 * dungeon.KASSE * stufe          # a merchant every fourth fight
        ein, top, leben = [], 0, 0
        for _ in range(laeufe):
            held = party(r, GRUPPE_W, stufe, rng)
            for h in held:
                h["gold"] = 0
            verkauf = 0
            for anlass in ["gegner"] * kaempfe + ["truhe"] * (kaempfe // 3) + ["belohnung"] + (["boss"] if rng.random() < 0.5 else []):
                _, it, _ = dungeon.loot(r, held, anlass, stufe, rng, welt=welt)
                x = min(dungeon.sell_price(r, it, {"art": rng.choice(sorted(dungeon.HAENDLER))}), dungeon.KASSE * stufe)
                verkauf += x
                top = max(top, x)
            ein.append((sum(h["gold"] for h in held) + min(verkauf, kasse)) / GRUPPE_W)
            leben = sum(h["leben_max"] for h in held) / GRUPPE_W
        aus = (kaempfe / 4 * gold.PREIS["gasthaus"] * stufe + kaempfe / 2 * dungeon.HEIL_GOLD * leben / 3
               + (2 * gold.PREIS["geruecht"] + gold.PREIS["schmied"]) * stufe / GRUPPE_W)
        ein.sort()
        med = ein[len(ein) // 2]
        out[str(stufe)] = {"kaempfe": kaempfe, "einnahmen": round(med), "zehntel": round(ein[len(ein) // 10]),
                           "ausgaben": round(aus), "verhaeltnis": round(med / max(1, aus), 2), "fund_max": top}
    return out


# ---------------------------------------------------------------- the run, the night, the page
def last():
    return read_json(FILE, {}) or {}


def _go(grund):
    """One run in this thread; one at a time."""
    with _lock:
        if _run["laeuft"]:
            return False
        _run.update(laeuft=True, seit=int(clock()))
    print(f"dungeon: pruefstand | start | {grund}", flush=True)
    try:
        t0 = time.monotonic()
        r = dungeon.rules()
        z = bench(r)
        w = economy(r)
        write_json(FILE, {"zeit": int(clock()), "kaempfe": KAEMPFE, "gefahr": "mittel", "zellen": z, "wirtschaft": w,
                          "nacht": _date() if grund == "nacht" else last().get("nacht", "")})
        unter = sum(1 for c in z.values() if c["siege"] < AIM[0])
        aussen = sum(1 for c in w.values() if not WIRTSCHAFT[0] <= c["verhaeltnis"] <= WIRTSCHAFT[1])
        print(f"dungeon: pruefstand | fertig | {len(z)} zellen | {unter} unter dem ziel | {aussen} stufen wirtschaft ausserhalb | {int(time.monotonic() - t0)} s", flush=True)
    except Exception as e:
        print(f"dungeon: pruefstand | fehler | {type(e).__name__}", flush=True)
    finally:
        _run["laeuft"] = False
    return True


def _date():
    return time.strftime("%Y-%m-%d", time.localtime(clock()))


def _spawn(grund):
    threading.Thread(target=_go, args=(grund,), daemon=True, name="dm-pruefstand").start()


async def due():
    """Each minute from the panel's loop: the night's run once a night while it is on."""
    if not on() or not NACHT[0] <= time.localtime(clock()).tm_hour < NACHT[1] or _run["laeuft"]:
        return
    if await asyncio.to_thread(lambda: last().get("nacht") != _date()):
        await asyncio.to_thread(_go, "nacht")


def view():
    """The page's data: the last table, the aim, on/running."""
    d = last()
    return {"an": on(), "laeuft": _run["laeuft"], "ziel": list(AIM), "gruppe_max": GRUPPE_MAX, "zeit": d.get("zeit", 0),
            "kaempfe": d.get("kaempfe", 0), "gefahr": d.get("gefahr", "mittel"), "zellen": d.get("zellen", {}),
            "wirtschaft": d.get("wirtschaft", {}), "wirtschaft_ziel": list(WIRTSCHAFT)}


@router.get("/api/admin/dungeon/pruefstand", dependencies=[Depends(auth)])
async def show(request: Request):
    guard.limit(request, "dungeonpruef", admin=True)
    return await asyncio.to_thread(view)


@router.post("/api/admin/dungeon/pruefstand", dependencies=[Depends(auth)])
async def now(request: Request):
    guard.limit(request, "dungeonpruef", admin=True)
    await json_body(request, 200)
    if not on():
        print("dungeon: pruefstand | knopf | aus", flush=True)
        raise HTTPException(409, "aus")
    if _run["laeuft"]:
        print("dungeon: pruefstand | knopf | laeuft", flush=True)
        return view()
    if clock() - _run["seit"] < KNOPF_S:
        print("dungeon: pruefstand | knopf | zu oft", flush=True)
        raise HTTPException(429, "zu oft")
    _spawn("knopf")
    print("dungeon: pruefstand | knopf | ok", flush=True)
    return dict(view(), laeuft=True)


def counts():
    """For the live overview: the table's cells, how many below and above the aim, whether a run is on."""
    z = last().get("zellen") or {}
    return {"zellen": len(z), "unter": sum(1 for c in z.values() if c["siege"] < AIM[0]),
            "ueber": sum(1 for c in z.values() if c["siege"] > AIM[1]), "laeuft": _run["laeuft"]}
