"""KI-Dungeon-Master: the balance bench „Balance-Prüfstand“ (Dominik 2026-10-24 „alle umsetzen“, Idee 5): the panel
plays thousands of fights alone, with the real rules and dice of dungeon_kampf (attacks, foes_turn, hurt, suffers,
flees, expire) and the merged catalog, for every level and group size, without the model and without a round. The
admin sees under Regeln how often the group wins and how much life it loses; a self-test keeps the aim (AIM, 70 to 90
per cent wins at „mittel“).

- A group: GRUPPE_MAX heroes at most, every class of the world in turn from a start the seed draws, the first people,
  built like a player's hero (dungeon.new_hero) and raised like at the table (Review 27.10. B6, raise_to): level by
  level, the first of the two abilities offered, every point on the class's order; gear: the first weapon of its class
  and the best body armour it may wear up to the level's price (GEAR), both of the rarity of the median find from foes
  up to the level by the find table (B11, gear_rarity).
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

With runes (Review 27.10., bericht „Abstimmung mit den Runen“ 4; only while „Runen und Sockel“ works,
dungeon_runen.wirkt): the same groups with the runes a group has found up to its level by the real find and trader
rates (with_runes), set as strong as the caps allow; the self-test keeps their wins at most RUNEN_PLUS points above
those without (the mean of all cells), and the economy sells every rune found.

The night's run (NACHT, once a night) and the admin's „Jetzt durchspielen“ write the table into STATE/dungeon-pruefstand.json
(dateien.py): {"zeit", "kaempfe", "gefahr", "zellen": {"stufe/gruppe": {"siege", "leben", "runden"}},
"runen": the same with runes ({} while they are off), "wirtschaft": {"stufe": {"kaempfe", "einnahmen", "zehntel",
"ausgaben", "verhaeltnis", "fund_max"}}}. Only while „Balance-Prüfstand“ is on (features.py, below the Dungeon-Master).

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
import dungeon_bestiarium
import dungeon_gold as gold
import dungeon_kampf as kampf
import dungeon_runen as runen
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
WIRTSCHAFT = (1.2, 2.0)        # income ÷ expenses of a hero per level (median) the self-test keeps (Wirtschaft Punkt 6)
JACKPOT = 10                   # no single find sells for more than this many times a level's income
LAEUFE = 200                   # runs per level of the economy
GRUPPE_W = 4                   # heroes of the economy's group
RAETSEL = 0.25                 # the part of the experience from riddles, places and acts (no fight, no find)
RUNEN_PLUS = 8                 # per cent points a group may win more often with its runes than without (Review 27.10.)
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


def gear_rarity(r, stufe):
    """The rarity of a hero's gear at this level (Review 27.10. B11): the median of the finds from foes up to this level
    by the find table (dungeon.rarity), so the bench moves with the table and makes no assumption of its own."""
    order = [x["id"] for x in r["seltenheit"]]
    fund = sorted((dungeon.rarity(r, s, w + r["anlass"]["gegner"])[1]["id"] for s in range(1, stufe + 1) for w in range(1, 101)),
                  key=order.index)
    return fund[len(fund) // 2]


def raise_to(r, h, stufe, rng):
    """A hero raised to the level as a player does it (Review 27.10. B6): level by level by dungeon.gain, the first of
    the two abilities offered taken, every level's point on the first value of the class's order below WERT_MAX."""
    reihe = dungeon._by(r, "klassen")[h["klasse"]]["reihe"]
    while h["stufe"] < stufe:
        if not dungeon.gain(r, h, r["stufen_ep"][h["stufe"]] - h["ep"], f"pruefstand|{h['stufe']}", rng):
            break
        if h["wahl"]:
            h["faehigkeiten"].append(h["wahl"][0])
            h["wahl"] = []
        w = next((w for w in reihe if h["werte"][w] < dungeon.WERT_MAX), None)
        if w and h["punkte"]:
            h["punkte"] -= 1
            h["werte"][w] += 1
        dungeon.relife(r, h)
    h["leben"] = h["leben_max"] = dungeon.life(r, h)
    return h


def party(r, n, stufe, rng, runen_rng=None):
    """n heroes of this level built like at the table (Review 27.10. B6): every class of the world in turn from a start
    the seed draws, raised level by level (raise_to), gear of the find table's rarity (gear_rarity); with runen_rng
    also the runes found up to the level (with_runes, its own dice: the same group as without)."""
    ks = [k["id"] for k in r["klassen"]]
    volk = r["voelker"][0]["id"]
    selten = gear_rarity(r, stufe)
    start = rng.randrange(len(ks))
    out = []
    for i in range(n):
        k = ks[(start + i) % len(ks)]
        h = raise_to(r, dungeon.new_hero(r, {"name": f"Held {i + 1}", "volk": volk, "klasse": k}, rng), stufe, rng)
        h["an"]["haupthand"] = dungeon.item(r, dungeon._by(r, "klassen")[k]["waffen"][0], selten, rng)
        a = _armour(r, k, stufe)
        if a:
            h["an"]["koerper"] = dungeon.item(r, a["id"], selten, rng)
        out.append(h)
    return with_runes(r, out, stufe, runen_rng) if runen_rng else out


def occasions(r, stufe, rng):
    """The finds of one level (Wirtschaft Punkt 6): every fight the level takes (the experience to the next level, a
    RAETSEL part from riddles, places and acts), a chest every third fight, a reward and every other level a boss."""
    ep = r["stufen_ep"]
    dxp = ep[stufe] - ep[stufe - 1] if stufe < len(ep) else ep[-1] - ep[-2]
    k = max(1, round((1 - RAETSEL) * dxp / kampf.BUDGET[stufe - 1]))
    return ["gegner"] * k + ["truhe"] * (k // 3) + ["belohnung"] + (["boss"] if rng.random() < 0.5 else [])


def with_runes(r, held, stufe, rng):
    """The group's runes as at the table (Review 27.10., bericht „Abstimmung mit den Runen“ 4): sockets on weapon and
    body armour by dungeon_runen.sockets, the runes of every level's finds (occasions) by dungeon_runen.draw at that
    level's rank, and from the trader every rune of the ranks it sells (KRAEMER, the gold assumed); then each hero
    fills every socket with the rune that makes the thing strongest within the caps (dungeon_runen.fits), a rune not
    yet in the thing first (per value only the strongest bonus counts), the weapon first. More than a player gets: the
    bench's runes are the upper bound."""
    for h in held:
        for it in (h["an"].get("haupthand"), h["an"].get("koerper")):
            if it:
                runen.sockets(dungeon, r, it, rng)
    rd = {}
    for s in range(1, stufe + 1):
        for anlass in occasions(r, s, rng):
            runen.draw(dungeon, r, rd, held, anlass, rng, stufe=s)
    for h in held:
        frei = [it for it in (h["an"].get("haupthand"), h["an"].get("koerper")) if it and it.get("so")]
        rb = h.setdefault("runen", {})
        for x in r.get("runen") or []:
            if x["rang"] <= runen.KRAEMER:
                rb[x["id"]] = rb.get(x["id"], 0) + sum(it["so"] for it in frei)
        for it in frei:
            while len(it["ru"]) < it["so"]:
                z = [(rid not in it["ru"], c[1]["nachher"], rid) for rid in sorted(h["runen"]) if h["runen"][rid]
                     for c in [runen.fits(dungeon, r, h, it, rid)] if c[0] == "ok"]
                if not z:
                    break
                rid = max(z)[2]
                it["ru"].append(rid)
                h["runen"][rid] -= 1
        h["leben"] = h["leben_max"] = dungeon.life(r, h)
    return held


def _spell(r, h):
    """The class's attack spell of grade 0 (a blessing with its own die in dungeon_kampf.attacks), "" for none."""
    cat = dungeon._by(r, "gegenstaende")
    z = (dungeon._by(r, "klassen")[h["klasse"]].get("zauber") or {}).get("0") or []
    return next((x for x in z if x in cat and cat[x].get("segen") and cat[x].get("schaden_art")), "")


# ---------------------------------------------------------------- an encounter
def encounter(r, held, gefahr, rng, tries=200, pool=None):
    """[(catalog foe, count)] of the danger asked, one or two kinds, [] when none fits; pool: only these foes (the
    templates people fight with, weighted: dungeon_personen.pool); never a peaceful foe, as at the table."""
    b = kampf.budget(dungeon, r, {}, held)
    fit = [g for g in (r.get("gegner") or [] if pool is None else pool) if 0 < g["ep"] <= b * kampf.SCHWER
           and not dungeon_bestiarium.friedlich(g)]          # like the table (dungeon_kampf._foes): never a peaceful one
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


def cell(r, stufe, gruppe, gefahr, kaempfe, seed, pool=None, mit_runen=False):
    """The bench for one level and group size: {"siege": per cent, "leben": per cent lost in the won fights,
    "runden": mean turns}; None when no encounter of the danger fits. mit_runen: the same groups with their runes."""
    rng = random.Random(f"{seed}|{stufe}|{gruppe}|{gefahr}")
    rrng = random.Random(f"{seed}|{stufe}|{gruppe}|{gefahr}|runen") if mit_runen else None
    won, lost, runden, n = 0, [], 0, 0
    for _ in range(kaempfe):
        held = party(r, gruppe, stufe, rng, rrng)
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


def bench(r, kaempfe=KAEMPFE, gefahr="mittel", seed="pruefstand", stufen=None, gruppen=None, pool=None, mit_runen=False):
    """The whole table {"stufe/gruppe": cell}; a cell without a fitting encounter is left out. pool: only these foes;
    mit_runen: the groups with their runes (with_runes; the runes do something only while dungeon_runen.wirkt)."""
    out = {}
    for s in stufen or range(1, r["grenzen"]["stufe_max"] + 1):
        for g in gruppen or range(1, GRUPPE_MAX + 1):
            c = cell(r, s, g, gefahr, kaempfe, seed, pool, mit_runen)
            if c:
                out[f"{s}/{g}"] = c
    return out


def economy(r, laeufe=LAEUFE, seed="wirtschaft", stufen=None, mit_runen=False):
    """The economy per level {"stufe": {"kaempfe", "einnahmen" (median of a hero), "zehntel" (the worst tenth),
    "ausgaben", "verhaeltnis", "fund_max" (the most one find sold for)}} by the real loot, prices and services;
    mit_runen: every rune of the finds (dungeon_runen.draw, its own dice) sold too."""
    out = {}
    welt = r["welten"][0]["id"]
    for stufe in stufen or range(1, r["grenzen"]["stufe_max"] + 1):
        rng = random.Random(f"{seed}|{stufe}")
        rrng = random.Random(f"{seed}|{stufe}|runen")
        kaempfe = occasions(r, stufe, random.Random(0)).count("gegner")
        kasse = kaempfe / 4 * dungeon.KASSE * stufe          # a merchant every fourth fight
        ein, top, leben = [], 0, 0
        for _ in range(laeufe):
            held = party(r, GRUPPE_W, stufe, rng)
            for h in held:
                h["gold"] = 0
            verkauf, rd = 0, {}
            for anlass in occasions(r, stufe, rng):
                _, it, _ = dungeon.loot(r, held, anlass, stufe, rng, welt=welt)
                x = min(dungeon.sell_price(r, it, {"art": rng.choice(sorted(dungeon.HAENDLER))}), dungeon.KASSE * stufe)
                verkauf += x
                top = max(top, x)
                rid = mit_runen and runen.draw(dungeon, r, rd, held, anlass, rrng, stufe=stufe)[1]
                if rid:
                    verkauf += runen.sell_price(r, rid)
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
        zr = bench(r, mit_runen=True) if runen.wirkt() else {}
        w = economy(r, mit_runen=bool(zr))
        write_json(FILE, {"zeit": int(clock()), "kaempfe": KAEMPFE, "gefahr": "mittel", "zellen": z, "wirtschaft": w,
                          "runen": zr, "nacht": _date() if grund == "nacht" else last().get("nacht", "")})
        if zr:
            print(f"dungeon: pruefstand | runen | {runes_plus(z, zr)} punkte", flush=True)
        unter = sum(1 for c in z.values() if c["siege"] < AIM[0])
        aussen = sum(1 for c in w.values() if not WIRTSCHAFT[0] <= c["verhaeltnis"] <= WIRTSCHAFT[1])
        print(f"dungeon: pruefstand | fertig | {len(z)} zellen | {unter} unter dem ziel | {aussen} stufen wirtschaft ausserhalb | {int(time.monotonic() - t0)} s", flush=True)
    except Exception as e:
        print(f"dungeon: pruefstand | fehler | {type(e).__name__}", flush=True)
    finally:
        _run["laeuft"] = False
    return True


def runes_plus(z, zr):
    """How many per cent points more the groups win with their runes, the mean over the cells of both tables."""
    ks = [k for k in z if k in zr]
    return round(sum(zr[k]["siege"] - z[k]["siege"] for k in ks) / max(1, len(ks)), 1)


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
            "wirtschaft": d.get("wirtschaft", {}), "wirtschaft_ziel": list(WIRTSCHAFT), "runen": d.get("runen", {}),
            "runen_plus": runes_plus(d.get("zellen", {}), d.get("runen", {})) if d.get("runen") else None, "runen_ziel": RUNEN_PLUS}


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
    d = last()
    z = d.get("zellen") or {}
    return {"zellen": len(z), "unter": sum(1 for c in z.values() if c["siege"] < AIM[0]),
            "ueber": sum(1 for c in z.values() if c["siege"] > AIM[1]), "laeuft": _run["laeuft"],
            "runen_plus": runes_plus(z, d["runen"]) if d.get("runen") else None}
