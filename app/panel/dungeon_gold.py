"""KI-Dungeon-Master: Gold mit Zweck (Idee 9 of 2026-10-24, Dominik „alle umsetzen“).

In a settlement (a place of the map of a settled kind, SIEDLUNG, outside a vault) or wherever a merchant stands, a
hero may pay for fixed offers of the panel, never of the model, priced by the group's level:
- Gasthaus: a night at the inn, a full rest for the whole group (life and spell charges), once a game evening;
- Schmied: a tool that broke on a natural 1 is mended and back in the bag (the last KAPUTT_MAX broken ones are kept);
- Lehrstunde: +1 on one value until the round or chapter ends (one at a time);
- Gerücht: a hint at the next place of the map toward the goal, once per place;
- Ausrüstung verbessern (Wirtschaft Punkt 7, Dominik 2026-10-25 „1-12“): a weapon or armour of the hero one rarity
  better, up to „episch“, for its full price at the new rarity; known from then on.
The inn grows with the level like the finds (PREIS per level and hero); the balance bench measures the economy
(dungeon_pruefstand.economy) and its self-test keeps income to expenses between 1.2 and 2.
Only while „Gold mit Zweck“ is allowed for the round's host (features "dungeongold"). The hero's move goes through the
seat's „held“ endpoint ({was: "dienst", id, i, wert}).
"""
import time

SIEDLUNG = ("dorf", "stadt", "taverne", "station", "basar", "hafen")
DIENSTE = ("gasthaus", "schmied", "lehre", "geruecht", "verbessern")
PREIS = {"gasthaus": 10, "schmied": 5, "lehre": 20, "geruecht": 3}   # gold per level of the group (the inn: per hero)
VERBESSERN_ARTEN = ("waffe", "ruestung")
VERBESSERN_BIS = "episch"   # the smith never makes a legend
KAPUTT_MAX = 5
NAMEN = {"gasthaus": (("Gasthaus", "Inn"), ("Eine Nacht für alle: volles Leben und alle Zauber wieder da.", "A night for everyone: full life and all spells back.")),
         "schmied": (("Schmied", "Smith"), ("Ein zerbrochenes Werkzeug wird wieder ganz.", "A broken tool is made whole again.")),
         "lehre": (("Lehrstunde", "Lesson"), ("+1 auf einen Wert bis zum Ende der Runde.", "+1 on one value until the round ends.")),
         "geruecht": (("Gerücht", "Rumour"), ("Ein Hinweis auf den nächsten Ort.", "A hint at the next place.")),
         "verbessern": (("Ausrüstung verbessern", "Improve gear"), ("Eine Waffe oder Rüstung wird eine Seltenheit besser, bis episch.", "A weapon or armour gets one rarity better, up to epic."))}
RICHTUNG = (("im Osten", "to the east"), ("im Südosten", "to the south-east"), ("im Süden", "to the south"), ("im Südwesten", "to the south-west"),
            ("im Westen", "to the west"), ("im Nordwesten", "to the north-west"), ("im Norden", "to the north"), ("im Nordosten", "to the north-east"))
clock = time.time


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeongold", rd["owner"])


def evening():
    return time.strftime("%Y-%m-%d", time.localtime(clock()))


def here(rd):
    """The settlement the group stands in: the place's name, the merchant's name, or "" for none."""
    k = rd.get("karte")
    if k and k.get("drin") is None and 0 <= k.get("hier", -1) < len(k.get("orte") or []) and k["orte"][k["hier"]].get("art") in SIEDLUNG:
        return k["orte"][k["hier"]]["name"]
    return (rd.get("markt") or {}).get("name", "")


def price(dm, rd, was):
    """A service's price by the group's level (the inn per hero); „verbessern“ goes by the piece (better_price)."""
    if was == "verbessern":
        return 0
    level = dm.group_level(dm._living(rd))
    return PREIS[was] * level * (len(dm._living(rd)) if was == "gasthaus" else 1)


def better(dm, r, it):
    """The rarity one better for the smith, or None: only a weapon or armour without a fixed rarity, never a legend,
    at most VERBESSERN_BIS."""
    c = dm._c(r, it)
    ids = [x["id"] for x in r["seltenheit"]]
    if c["art"] not in VERBESSERN_ARTEN or c.get("seltenheit") or it.get("leg") or it["s"] not in ids:
        return None
    k = ids.index(it["s"]) + 1
    return ids[k] if k <= ids.index(VERBESSERN_BIS) else None


def better_price(dm, r, it):
    """The full price of the piece at its better rarity (Wirtschaft Punkt 7: dear, so gold stays useful later)."""
    s = better(dm, r, it)
    return dm.price(r, dict(it, s=s)) if s else 0


def broke(rd, h, it):
    """A tool broke on a natural 1 (apply): kept for the smith while „Gold mit Zweck“ is on."""
    if on(rd):
        h["kaputt"] = ((h.get("kaputt") or []) + [dict(it, n=1)])[-KAPUTT_MAX:]


def _next_place(rd):
    """The place a rumour names: the first one not visited on the way to the goal, else an unvisited neighbour."""
    k = rd["karte"]
    n, seen = len(k["orte"]), set(k.get("besucht") or [])
    nb = {i: set() for i in range(n)}
    for a, b in k.get("wege") or []:
        nb[a].add(b)
        nb[b].add(a)
    back, todo = {k["hier"]: None}, [k["hier"]]
    while todo:                                  # breadth first from here
        x = todo.pop(0)
        for y in sorted(nb[x]):
            if y not in back:
                back[y] = x
                todo.append(y)
    way, x = [], k.get("ziel")
    while x is not None and x in back:
        way.append(x)
        x = back[x]
    for i in reversed(way):
        if i not in seen:
            return i
    rest = sorted(y for y in nb[k["hier"]] if y not in seen)
    return rest[0] if rest else -1


def _direction(a, b):
    import math
    ang = math.degrees(math.atan2(b["y"] - a["y"], b["x"] - a["x"])) % 360
    return RICHTUNG[int((ang + 22.5) // 45) % 8]


def serve(dm, r, rd, pid, h, b):
    """{id, i, wert}: one offer of the settlement for the hero by fixed rules; raises the game's refusals."""
    li = 1 if rd["lang"] == "en" else 0
    was = b.get("id")
    if not on(rd):
        print("dungeon: dienst | aus", flush=True)
        raise PermissionError("gold")
    if was not in DIENSTE:
        print("dungeon: dienst | unbekannt", flush=True)
        raise ValueError("dienst")
    if not here(rd) or rd.get("kampf"):
        print(f"dungeon: dienst | {was} | keine siedlung", flush=True)
        raise LookupError("siedlung")
    pieces = dm.worn(h) + h["tasche"]
    teil = next((x for x in pieces if x["i"] == b.get("i")), None) if was == "verbessern" else None
    if was == "verbessern" and (not teil or not better(dm, r, teil)):
        print("dungeon: dienst | verbessern | nein", flush=True)
        raise ValueError("verbessern")
    preis = better_price(dm, r, teil) if teil else price(dm, rd, was)
    if h["gold"] < preis:
        print(f"dungeon: dienst | {was} | zu wenig gold", flush=True)
        raise ValueError("gold")
    text = ""
    if was == "gasthaus":
        if rd.get("gasthaus") == evening():
            print("dungeon: dienst | gasthaus | schon", flush=True)
            raise FileExistsError("gasthaus")
        rd["gasthaus"] = evening()
        for p_id, p in dm.seated(rd):
            z = p["held"]
            if z.get("tot") or z.get("ohnmacht"):
                continue
            was0 = z["leben"]
            dm.heal(z, z["leben_max"])
            z["ladungen"] = dm.full_charges(r, z)
            dm.stood_up(rd, p_id, z, was0)
            if p_id != pid:
                dm.keep_seat(p)
        text = (f"{h['name']} zahlt eine Nacht im Gasthaus. Die Gruppe ruht sich aus: volles Leben, alle Zauber wieder da.",
                f"{h['name']} pays for a night at the inn. The group rests: full life, all spells back.")
    elif was == "schmied":
        it = next((x for x in h.get("kaputt") or [] if x["i"] == b.get("i")), None)
        if not it or not dm.room(r, h, [it]):
            print("dungeon: dienst | schmied | nein", flush=True)
            raise ValueError("schmied")
        h["kaputt"].remove(it)
        dm.bag_add(r, h, it)
        name = dm.item_view(r, it, rd["lang"])["name"]
        text = (f"Der Schmied macht {name} von {h['name']} wieder ganz.", f"The smith makes {h['name']}'s {name} whole again.")
    elif was == "lehre":
        if b.get("wert") not in h["werte"] or (h.get("lehre") or {}).get("wert") == b["wert"]:
            print("dungeon: dienst | lehre | nein", flush=True)
            raise ValueError("lehre")
        h["lehre"] = {"wert": b["wert"]}
        wn = dm._by(r, "werte")[b["wert"]]["name"][li]
        text = (f"{h['name']} nimmt eine Lehrstunde: {wn} +1 bis zum Ende der Runde.", f"{h['name']} takes a lesson: {wn} +1 until the round ends.")
    elif was == "verbessern":
        alt = dm.item_view(r, teil, rd["lang"])["name"]
        teil["s"] = better(dm, r, teil)
        teil["bonus"] = dm._by(r, "seltenheit")[teil["s"]]["bonus"]
        teil.pop("u", None)                   # the smith knows what it made
        dm.draw_effect(r, teil, dm.random)
        neu = dm._by(r, "seltenheit")[teil["s"]]["name"]
        text = (f"Der Schmied macht {alt} von {h['name']} besser: jetzt {neu[0]}.", f"The smith makes {h['name']}'s {alt} better: now {neu[1]}.")
    else:
        k = rd.get("karte")
        if not k or k.get("geruecht") == k["hier"]:
            print("dungeon: dienst | geruecht | schon", flush=True)
            raise FileExistsError("geruecht")
        i = _next_place(rd)
        if i < 0:
            print("dungeon: dienst | geruecht | nichts", flush=True)
            raise LookupError("geruecht")
        k["geruecht"] = k["hier"]
        o = k["orte"][i]
        rw = _direction(k["orte"][k["hier"]], o)
        text = (f"Ein Gerücht für {h['name']}: Man erzählt sich von {o['name']}, {rw[0]}.", f"A rumour for {h['name']}: people talk of {o['name']}, {rw[1]}.")
    h["gold"] -= preis
    dm._log(rd, "dienst", pid=pid, name=h["name"], was=was, gold=preis, text=list(text))
    dm._day.bump("dienste")
    print(f"dungeon: dienst | {was} | {preis} gold", flush=True)


def view(dm, r, rd, pid):
    """The settlement's offers for the own seat; None while off, outside a settlement or in a fight."""
    p = rd["plaetze"].get(pid) or {}
    h = p.get("held")
    if not h or not on(rd) or rd.get("status") == "ende" or rd.get("kampf") or not here(rd):
        return None
    li = 1 if rd["lang"] == "en" else 0
    k = rd.get("karte") or {}
    besser = [x for x in dm.worn(h) + h["tasche"] if better(dm, r, x)]
    frei = {"gasthaus": rd.get("gasthaus") != evening(), "schmied": bool(h.get("kaputt")),
            "lehre": True, "geruecht": bool(k) and k.get("geruecht") != k.get("hier") and _next_place(rd) >= 0, "verbessern": bool(besser)}
    held = dm._living(rd)
    # Siedlung mit Leben (Dominik 2026-10-25 „so umsetzten“, 1a 3a 5b): the time of day for the head, the group's gold only
    # shown, and per service the calculation of its price (gold per level, level, heroes for the inn)
    return {"name": here(rd), "gold": h["gold"], "lehre": (h.get("lehre") or {}).get("wert", ""),
            "gold_gruppe": sum(p["held"]["gold"] for _, p in dm.seated(rd)), "tageszeit": rd.get("tageszeit") or "tag",
            "stufe": dm.group_level(held), "helden": len(held),
            "dienste": [{"id": x, "name": NAMEN[x][0][li], "satz": NAMEN[x][1][li], "preis": price(dm, rd, x), "frei": frei[x],
                         "je": PREIS.get(x, 0)} for x in DIENSTE],
            "kaputt": [dm.item_view(r, x, rd["lang"]) for x in h.get("kaputt") or []],
            "verbessern": [dict(dm.item_view(r, x, rd["lang"]), preis=better_price(dm, r, x),
                                neu=dm._by(r, "seltenheit")[better(dm, r, x)]["name"][li]) for x in besser]}
