"""KI-Dungeon-Master: Gefährten anheuern (D&D ideas round 2, idea 9, Dominik 2026-10-26 „1-9 umsetzten reihenfolge
überlasse ich dir.“; the hirelings of the old tabletop rules, only as an idea, own code; the companions and their values
per level are the DnDAppFiles thread's, ideen.gefaehrten, ideen.gefaehrten_kinder and ideen.gefaehrte_werte).

In a settlement a hero may hire a companion of the round's world (at the children's table an animal friend) as one more
service of „Gold mit Zweck“ (dungeon_gold.serve, „gefaehrte“): only while fewer than four heroes play, as many as fill
the group up to four, at most MAX. Its values come from the table by the group's level (life, armour class, attack,
damage, pay), its pay is due once a chapter from the hirer's own gold (the first chapter on hiring).
In a fight every companion up attacks by the panel's dice (attacks: d20 + attack against the foe's armour class, at the
foe with the least life left), and the foes may strike it like a hero (targets). A companion at half its life makes a
morale check once a fight (d20 ≥ MORAL, else it flees this fight), at 0 it lies down; after the fight it stands again
(after_fight, never lost for good). A new chapter without the pay: a morale check, else it leaves. It gets no loot and
no experience. In the encounter budget each companion up counts as ANTEIL of a hero (share), so the balance holds.
The model only tells: it gets the companions as data and their blows as receipts.

Off by default: the admin's switch dungeongefaehrte (features.py, chat.dungeon_gefaehrte) for the round's host.
State: rd["gefaehrten"] [{k, id, name, satz, wert, hid, stufe, leben, max, ruestung, angriff, schaden, plus, sold,
kapitel, aus, moral}]; a campaign keeps them (keep, carry).
Journal: fixed words and numbers („dungeon: gefaehrte | …“), Live only counts.
"""
import random

import features
from common import DayCounter

KEY = "dungeongefaehrte"
MAX = 2
GRUPPE = 4                 # companions only fill the group up to this many
MORAL = 10
ANTEIL = 0.5
PREFIX = "gf:"
WAFFE = ("Waffe", "weapon")

_day = DayCounter(angeheuert=0, hiebe=0, am_boden=0, geflohen=0, gegangen=0, sold=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def is_one(pid):
    return str(pid or "").startswith(PREFIX)


def rows(dm, r, rd):
    """The companions to hire at this table: the animal friends at the children's table, else those of the world."""
    i = r.get("ideen") or {}
    if dm.kids(r, rd):
        return list(i.get("gefaehrten_kinder") or [])
    return [x for x in i.get("gefaehrten") or [] if x.get("welt") == rd.get("welt")]


def werte(r, stufe):
    t = (r.get("ideen") or {}).get("gefaehrte_werte") or []
    return next((x for x in t if x["stufe"] == max(1, min(len(t), stufe))), None)


def sold(dm, r, rd):
    """A companion's pay for a chapter by the group's level."""
    w = werte(r, dm.group_level(dm._living(rd)))
    return w["sold"] if w else 0


def all_(rd):
    return rd.get("gefaehrten") or []


def up(rd):
    """The companions with the group in this chapter and on their feet (paid, not down, not fled)."""
    if not on(rd):
        return []
    return [c for c in all_(rd) if not c.get("aus") and c.get("kapitel", 0) >= rd.get("kapitel", 0)]


def slots(dm, rd):
    return max(0, min(MAX, GRUPPE - len(dm._living(rd))) - len(all_(rd)))


def candidates(dm, r, rd):
    """The companions still to hire here: {id, name, satz} in the round's language, [] when the group is full."""
    if not on(rd) or not slots(dm, rd):
        return []
    li = 1 if rd.get("lang") == "en" else 0
    have = {c["id"] for c in all_(rd)}
    return [{"id": x["id"], "name": x["name"][li], "satz": x["satz"][li]} for x in rows(dm, r, rd) if x["id"] not in have]


def hire(dm, r, rd, pid, h, gid):
    """From dungeon_gold.serve: the hero hires one; returns the sentences for the log (serve takes the gold)."""
    if not on(rd):
        raise PermissionError("gold")
    if not slots(dm, rd):
        print("dungeon: gefaehrte | voll", flush=True)
        raise OverflowError("gefaehrten")
    x = next((x for x in rows(dm, r, rd) if x["id"] == gid and x["id"] not in {c["id"] for c in all_(rd)}), None)
    if not x:
        print("dungeon: gefaehrte | unbekannt", flush=True)
        raise ValueError("gefaehrte")
    stufe = dm.group_level(dm._living(rd))
    w = werte(r, stufe)
    c = {"k": PREFIX + x["id"], "id": x["id"], "name": list(x["name"]), "satz": list(x["satz"]), "wert": x.get("wert", "staerke"),
         "hid": h.get("hid", ""), "stufe": w["stufe"], "leben": w["leben"], "max": w["leben"], "ruestung": w["ruestung"],
         "angriff": w["angriff"], "schaden": w["schaden"], "plus": w["schaden_plus"], "sold": w["sold"],
         "kapitel": rd.get("kapitel", 0), "aus": "", "moral": False}
    rd.setdefault("gefaehrten", []).append(c)
    _day.bump("angeheuert")
    print("dungeon: gefaehrte | angeheuert", flush=True)
    return (f"{h['name']} heuert {x['name'][0]} an: {x['satz'][0]}", f"{h['name']} hires {x['name'][1]}: {x['satz'][1]}")


def pay(dm, r, rd, rng=None):
    """In dungeon.apply: the pay of a new chapter from the hirer's gold once the hirer sits at the table; without it a
    morale check, else the companion leaves."""
    rng = rng or random
    if not on(rd):
        return
    heroes = {p["held"].get("hid"): (pid, p["held"]) for pid, p in dm.seated(rd)}
    li = 1 if rd.get("lang") == "en" else 0
    for c in list(all_(rd)):
        if c.get("kapitel", 0) >= rd.get("kapitel", 0) or c.get("hid") not in heroes:
            continue
        pid, h = heroes[c["hid"]]
        n = sold(dm, r, rd)
        if h.get("gold", 0) >= n:
            h["gold"] -= n
            c["kapitel"] = rd.get("kapitel", 0)
            dm._log(rd, "gefaehrte", pid=pid, name=c["name"][li], was="sold", gold=n)
            _day.bump("sold")
            print(f"dungeon: gefaehrte | sold | {n} gold", flush=True)
        elif rng.randint(1, 20) >= MORAL:
            c["kapitel"] = rd.get("kapitel", 0)
            dm._log(rd, "gefaehrte", pid=pid, name=c["name"][li], was="ohne_sold")
            print("dungeon: gefaehrte | ohne sold | bleibt", flush=True)
        else:
            rd["gefaehrten"].remove(c)
            dm._log(rd, "gefaehrte", pid=pid, name=c["name"][li], was="gegangen")
            _day.bump("gegangen")
            print("dungeon: gefaehrte | gegangen", flush=True)


def share(rd):
    """What the companions up add to the group in the encounter budget (dungeon_kampf.budget)."""
    return ANTEIL * len(up(rd))


def attacks(dm, r, rd, hits, rng=None):
    """In run_turn after the heroes' attacks: every companion up strikes the foe with the least life left; hit entries
    like the heroes' (pid is the companion's k)."""
    import dungeon_kampf as kampf
    rng = rng or random
    if not rd.get("kampf"):
        return []
    li = 1 if rd.get("lang") == "en" else 0
    life = {g["k"]: g["leben"] for g in kampf.up(rd)}
    for x in hits:
        if x.get("treffer") and x.get("ziel") in life:
            life[x["ziel"]] -= x["schaden"]
    out = []
    for c in up(rd):
        gs = [g for g in kampf.up(rd) if life.get(g["k"], 0) > 0]
        if not gs:
            break
        g = min(gs, key=lambda g: (life[g["k"]], g["k"]))
        w = rng.randint(1, 20)
        krit = w == 20
        hit = krit or (w != 1 and w + c["angriff"] >= g["rk"])
        n, wirkt = 0, ""
        if hit:
            n, wirkt = kampf.against(g, "wucht", max(1, sum(rng.randint(1, c["schaden"]) for _ in range(2 if krit else 1)) + c["plus"]))
            life[g["k"]] -= n
        out.append({"pid": c["k"], "name": c["name"][li], "ziel": g["k"], "gegner": g["name"], "mit": WAFFE[li], "wert": c["wert"],
                    "w": w, "ws": [w], "vt": "", "bonus": c["angriff"], "gesamt": w + c["angriff"], "rk": g["rk"], "treffer": hit,
                    "krit": krit, "schaden": n, "faellt": hit and life[g["k"]] <= 0, "art": "wucht", "wirkt": wirkt, "eig": [],
                    "gefaehrte": True})
    if out:
        _day.bump("hiebe", len(out))
    return out


def targets(rd):
    """The companions up as targets of the foes: (k, a stand-in with name, armour class and no states)."""
    li = 1 if rd.get("lang") == "en" else 0
    return [(c["k"], {"name": c["name"][li], "zust": [], "gefaehrte": True, "ruestung": c["ruestung"], "werte": {}})
            for c in up(rd)] if rd.get("kampf") else []


def struck(dm, rd, x, rng=None):
    """In dungeon_kampf.apply: a foe's blow at a companion; down at 0, a morale check once a fight at half its life."""
    rng = rng or random
    c = next((c for c in all_(rd) if c["k"] == x.get("pid")), None)
    if not c or c.get("aus"):
        return
    li = 1 if rd.get("lang") == "en" else 0
    dm._log(rd, "angriff", gegner=x["gegner"], pid="", name=c["name"][li], w=x["w"], ws=x.get("ws", [x["w"]]), vt=x.get("vt", ""),
            bonus=x["bonus"], gesamt=x["gesamt"], rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"], von_gegner=True,
            **({"beleg": x["beleg"]} if x.get("beleg") else {}))
    if not x["treffer"]:
        return
    c["leben"] = max(0, c["leben"] - x["schaden"])
    if c["leben"] <= 0:
        c["aus"] = "am_boden"
        dm._log(rd, "gefaehrte", name=c["name"][li], was="am_boden")
        _day.bump("am_boden")
        print("dungeon: gefaehrte | am boden", flush=True)
    elif c["leben"] * 2 <= c["max"] and not c.get("moral"):
        c["moral"] = True
        if rng.randint(1, 20) < MORAL:
            c["aus"] = "geflohen"
            dm._log(rd, "gefaehrte", name=c["name"][li], was="geflohen")
            _day.bump("geflohen")
            print("dungeon: gefaehrte | moral | geflohen", flush=True)
        else:
            print("dungeon: gefaehrte | moral | bleibt", flush=True)


def after_fight(rd):
    """In dungeon_kampf.end: who lay down or fled stands with the group again (at least 1 life)."""
    for c in all_(rd):
        if c.get("aus") in ("am_boden", "geflohen"):
            c["aus"] = ""
        c["leben"] = max(1, c["leben"])
        c["moral"] = False


def facts(rd, li):
    """The companions with the group, only as data for the narrator."""
    cs = up(rd)
    return {"gefaehrten": [{"name": c["name"][li], "satz": c["satz"][li], "leben": f"{c['leben']}/{c['max']}"} for c in cs]} if cs else {}


AUFGABE = {
    "de": (" Gefährten in den Fakten (gefaehrten) gehen mit der Gruppe; ihre Hiebe würfelt das Panel (Belege), sie "
           "entscheiden nie für einen Spieler. Lass sie kurz in ihrer Art reagieren."),
    "en": (" Companions in the facts (gefaehrten) go with the group; the panel rolls their blows (receipts), they never "
           "decide for a player. Let them react briefly in their manner."),
}


def task(rd, lang):
    return AUFGABE[lang] if up(rd) else ""


def view(dm, rd):
    """The companions for the table: name, line, life, whether up, who hired them."""
    if not on(rd) or not all_(rd):
        return None
    li = 1 if rd.get("lang") == "en" else 0
    who = {p["held"].get("hid"): p["held"]["name"] for _, p in dm.seated(rd)}
    return [{"k": c["k"], "name": c["name"][li], "satz": c["satz"][li], "leben": c["leben"], "max": c["max"], "aus": c.get("aus", ""),
             "dabei": c.get("kapitel", 0) >= rd.get("kapitel", 0), "von": who.get(c.get("hid"), "")} for c in all_(rd)]


def keep(rd):
    """What a campaign keeps: the companions, on their feet, unpaid for the next chapter."""
    return {"gefaehrten": [dict(c, aus="", moral=False, leben=max(1, c["leben"])) for c in all_(rd)]} if all_(rd) else {}


def carry(kampagne):
    g = kampagne.get("gefaehrten")
    return {"gefaehrten": [c for c in g if isinstance(c, dict) and is_one(c.get("k"))][:MAX]} if isinstance(g, list) else {}


def for_live():
    """Numbers only: hired, blows, down, fled, left, pay today."""
    t = _day.counts()
    return {k: t[k] for k in ("angeheuert", "hiebe", "am_boden", "geflohen", "gegangen", "sold")}
