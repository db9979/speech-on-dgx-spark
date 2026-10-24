"""The fight of the KI-Dungeon-Master (Punkt 2 of the review of 2026-10-24 with the foe points 1 and 2 and the item
points 1 and 9, Dominik „Ja, alles umsetzen“ / „Ja, alles nach Empfehlung umsetzen“): the panel sets the encounter by
a budget, rolls every attack and keeps the foes' life; the model only picks foes from the panel's offer and tells
what the dice say.

    budget     the D&D table of a medium encounter per hero (BUDGET by level) times the heroes, half at the children's table
    offer      up to ANGEBOT foes of the bestiary (dungeon_srd.json „gegner“) of the round's world that fit the budget;
               the same turn always offers the same (a seed of round, turn and group), so check and facts agree
    start      the model's begegnung [{id, anzahl}] from the offer only; the panel takes foes away until the adjusted
               experience (D&D multiplier by count) is at most SCHWER times the budget, GEGNER_MAX at most
    attack     a check with ziel (a foe's name) is an attack: d20 + the value's bonus + proficiency against the foe's
               armour class (ruestung); a hit costs the weapon's die + the value's bonus + its rarity (a spell cast
               this turn: its die by grade); a natural 20 doubles the dice, a natural 1 misses
    foes       every foe still up attacks once: the hero who hit it this turn, else one of the standing heroes by the
               seed; d20 + angriff against the hero's armour class (rk), the bestiary's dice + schaden_plus; Eisenhaut
               and Schildwall work on it as on every hit (dungeon.consequences)
    flight     a foe at a quarter of its life or less flees on a d20 of FLUCHT_W or less (never at the children's table:
               there it gives up)
    end        all foes down or fled, or the model's kampf_ende („frieden“, „flucht“): the experience of the defeated
               (half for the fled) divided by the living heroes, one find (anlass „gegner“) for the group

rd["kampf"] = {"gegner": [{k, id, name, zeichen, leben, max, rk, angriff, schaden, plus, wuerfel, ep, aus}], "seit": zug,
               "budget": n, "gefahr": "leicht"|"mittel"|"schwer"}; dungeon.py owns the round and calls in.
"""
import random

# D&D 5e: experience of a medium encounter per character by its level (1..20)
BUDGET = (50, 100, 150, 250, 500, 600, 750, 1000, 1100, 1200, 1600, 2000, 2200, 2500, 2800, 3200, 3900, 4200, 4900, 5700)
MAL = ((11, 3.0), (7, 2.5), (3, 2.0), (2, 1.5), (1, 1.0))   # the multiplier of the experience by the number of foes
GEGNER_MAX = 6             # foes of one encounter
ANZAHL_MAX = 4             # of one kind
ANGEBOT = 5                # foes the panel offers the model
SCHWER = 1.5               # the adjusted experience at most this many times the budget
KIND = 0.5                 # the children's table: half the budget
FLUCHT = 4                 # a foe at a quarter of its life or less …
FLUCHT_W = 9               # … flees on a d20 of this or less
GEFAHR = ((0.75, "leicht"), (1.25, "mittel"), (99.0, "schwer"))
FAUST = 2                  # an attack without a weapon: 1W2 + Stärke
ZAUBER_W = (6, 8, 8, 10, 10, 12)   # the die of an attack spell by its grade 0..5
ENDE = ("frieden", "flucht")       # the model may end a fight without a winner
AUS = ("besiegt", "geflohen")
ZIEL_MAX = 40

SCHEMA_BEGEGNUNG = {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "required": ["id"],
                    "properties": {"id": {"type": "string", "maxLength": 40}, "anzahl": {"type": "integer"}}}}
SCHEMA_ENDE = {"type": "string", "enum": ["", *ENDE]}

AUFGABE_ANGEBOT = {
    "de": "Liegt ein Kampf in der Luft (ein Hinterhalt, Wachen, ein Ungeheuer), wähle in begegnung höchstens drei Gegner "
          "mit id und anzahl nur aus der Liste angebot der Fakten und erzähle, wie sie auftauchen, jeden mit seinem Namen "
          "aus angebot; nenne keine anderen Gegner. Das Panel bestimmt, wie viele kommen und wie stark sie sind; erfinde "
          "keine anderen Gegner mit Werten.",
    "en": "When a fight is in the air (an ambush, guards, a monster), choose at most three foes in begegnung with id and "
          "anzahl only from the list angebot of the facts and tell how they appear, each by its name from angebot; name "
          "no other foes. The panel decides how many come and how strong they are; never invent other foes with numbers."}
AUFGABE_KAMPF = {
    "de": "Es wird gekämpft (Fakten kampf). Das Panel würfelt jeden Angriff: Greift eine Figur in ihrer Aktion einen "
          "Gegner an, gib ihr eine Probe mit ziel = dem Namen des Gegners genau wie in kampf und dem Wert, mit dem sie "
          "angreift; schwer zählt dabei nicht. Erzähle genau, was die Würfe in proben und gegner_zuege sagen: wer "
          "trifft, wer verfehlt, wer fällt oder flieht. Melde für den Kampf keinen Schaden in folgen und lass keinen "
          "Gegner ohne Wurf fallen. Ergeben sich die Gegner oder flieht die Gruppe, setze kampf_ende.",
    "en": "There is a fight (facts kampf). The panel rolls every attack: when a character attacks a foe in its action, "
          "give it a check with ziel = the foe's name exactly as in kampf and the value it attacks with; schwer does "
          "not count then. Tell exactly what the rolls in proben and gegner_zuege say: who hits, who misses, who falls "
          "or flees. Report no damage of the fight in folgen and let no foe fall without a roll. When the foes give "
          "up or the group flees, set kampf_ende."}


def prof(stufe):
    """The proficiency bonus of D&D by level."""
    return 2 + (max(1, int(stufe)) - 1) // 4


def rk(dm, r, h):
    """A hero's armour class (Gegenstands-Punkt 9): 10 + twice the body armour + the other pieces (shield, helmet,
    gauntlets, boots, each with its rarity) + the Geschick bonus, at most 2 in medium (body 2) and none in heavy armour
    (body 3 and more)."""
    body, rest = 0, 0
    for k, it in (h.get("an") or {}).items():
        if not it or dm._c(r, it)["art"] != "ruestung":
            continue
        n = dm._c(r, it).get("schutz", 0) + (0 if it.get("u") else it.get("bonus", 0))
        if k == "koerper":
            body = n
        else:
            rest += n
    g = dm.mod(h["werte"].get("geschick", 10))
    base = dm._c(r, h["an"]["koerper"]).get("schutz", 0) if (h.get("an") or {}).get("koerper") else 0
    g = g if base < 2 else min(g, 2) if base < 3 else min(g, 0)
    return 10 + 2 * body + rest + g


def _mal(n):
    return next(m for k, m in MAL if n >= k)


def budget(dm, r, rd, held):
    """The experience a medium encounter of this group may have (D&D), half at the children's table."""
    b = sum(BUDGET[min(len(BUDGET), max(1, h["stufe"])) - 1] for h in held)
    return int(b * (KIND if dm.kids(r, rd) else 1))


def _foes(dm, r, rd):
    welt = rd.get("welt", "")
    return [g for g in r.get("gegner") or [] if welt in g["welten"] or "alle" in g["welten"]]


def _seed(rd, held, *more):
    return random.Random("|".join(map(str, (rd.get("zug", 0), rd.get("welt", ""), len(held), sum(h["stufe"] for h in held), *more))))


def room(r, rd):
    """The foes a room of the map demands (dungeon_karte puts {"raum": its tag, "ids": [bestiary ids]} into
    rd["raum_gegner"] for a guardian or boss room): their catalog entries, [] without one."""
    rg = rd.get("raum_gegner") or {}
    by = {g["id"]: g for g in r.get("gegner") or []}
    return [by[i] for i in rg.get("ids") or [] if i in by][:ANGEBOT]


def offer(dm, r, rd, held):
    """The foes the model may choose from this turn: of the round's world, one of them alone within the budget, the
    nearest to a third of it first, ANGEBOT drawn from the best twelve by the turn's seed; in a room of the map only
    its foes (room). [] in a fight."""
    if rd.get("kampf") or not held:
        return []
    if room(r, rd):
        return room(r, rd)
    b = budget(dm, r, rd, held)
    fit = [g for g in _foes(dm, r, rd) if 0 < g["ep"] <= b * SCHWER]
    fit.sort(key=lambda g: (abs(g["ep"] - b / 3), g["id"]))
    top = fit[:12]
    return sorted(_seed(rd, held).sample(top, min(ANGEBOT, len(top))), key=lambda g: g["ep"])


def offer_facts(dm, r, rd, held, li):
    return [{"id": g["id"], "name": g["name"][li], "stufe": g["stufe"], "groesse": g.get("groesse", "mittel")}
            for g in offer(dm, r, rd, held)]


def adjusted(foes):
    return int(sum(g["ep"] for g in foes) * _mal(len(foes)))


def check_encounter(dm, r, rd, held, obj):
    """The model's begegnung by fixed rules: only offered ids, one entry per id, anzahl 1..ANZAHL_MAX, then the
    strongest taken away until the adjusted experience fits SCHWER times the budget (one foe always stays); in a
    room of the map each of its foes once. Returns [(catalog entry, count)] or []."""
    if not isinstance(obj, list) or rd.get("kampf"):
        return []
    have = {g["id"]: g for g in offer(dm, r, rd, held)}
    out, seen = [], set()
    for x in obj[:3]:
        if not isinstance(x, dict) or x.get("id") not in have or x["id"] in seen:
            continue
        seen.add(x["id"])
        n = x.get("anzahl") if isinstance(x.get("anzahl"), int) and not isinstance(x.get("anzahl"), bool) else 1
        out.append([have[x["id"]], max(1, min(ANZAHL_MAX, n))])
    b = budget(dm, r, rd, held) * SCHWER
    if room(r, rd):                              # a room's guardian or boss comes once each, as the map wants it
        return [(g, 1) for g, _ in out]
    while out:
        flat = [g for g, n in out for _ in range(n)]
        if len(flat) <= GEGNER_MAX and (adjusted(flat) <= b or len(flat) == 1):
            break
        i = max(range(len(out)), key=lambda j: (out[j][0]["ep"], out[j][1]))
        out[i][1] -= 1
        if not out[i][1]:
            out.pop(i)
    return [(g, n) for g, n in out]


def start(dm, r, rd, held, wahl, li):
    """An encounter into the round: the foes with their bestiary values, numbered when several of a kind come."""
    if not wahl:
        return None
    gegner = []
    for g, n in wahl:
        for j in range(n):
            gegner.append({"k": f"g{len(gegner) + 1}", "id": g["id"], "name": g["name"][li] + (f" {j + 1}" if n > 1 else ""),
                           "zeichen": g.get("zeichen", ""), "leben": g["leben"], "max": g["leben"], "rk": g["ruestung"],
                           "angriff": g["angriff"], "schaden": g["schaden"], "plus": g.get("schaden_plus", 0),
                           "wuerfel": g.get("anzahl_wuerfel", 1), "ep": g["ep"], "aus": ""})
    b = budget(dm, r, rd, held)
    ratio = adjusted([{"ep": x["ep"]} for x in gegner]) / max(1, b)
    rd["kampf"] = {"gegner": gegner, "seit": rd.get("zug", 0), "budget": b, "gefahr": next(n for m, n in GEFAHR if ratio <= m)}
    if room(r, rd) and {g["id"] for g, _ in wahl} <= set(rd["raum_gegner"]["ids"]):
        rd["kampf"]["raum"] = rd["raum_gegner"]["raum"]
    dm._log(rd, "begegnung", gegner=[dict(card(dm, r, rd, g["id"], "en" if li else "de"), anzahl=n) for g, n in wahl],
            gefahr=rd["kampf"]["gefahr"])
    dm._day.bump("begegnungen")
    print(f"dungeon: kampf | start | {len(gegner)} gegner | {rd['kampf']['gefahr']}", flush=True)
    return rd["kampf"]


def up(rd):
    return [g for g in (rd.get("kampf") or {}).get("gegner") or [] if not g["aus"]]


def _named(rd, ziel):
    z = str(ziel or "").strip().lower()[:ZIEL_MAX]
    return next((g for g in up(rd) if g["name"].lower() == z), None) or \
        next((g for g in up(rd) if z and g["name"].lower().startswith(z)), None)


def _weapon(dm, r, h):
    it = (h.get("an") or {}).get("haupthand")
    return it if it and dm._c(r, it)["art"] == "waffe" else None


def _dice(rng, n, w):
    return sum(rng.randint(1, w) for _ in range(n))


def attacks(dm, r, rd, proben, rng=None):
    """The checks with ziel in a fight become attacks (taken out of proben). Returns (the rest, the attack results);
    every number from here: the foe's life is only changed in apply (hit)."""
    rng = rng or random
    if not rd.get("kampf"):
        return [{k: v for k, v in p.items() if k != "ziel"} for p in proben], []
    rest, out, life = [], [], {g["k"]: g["leben"] for g in up(rd)}
    li = 1 if rd["lang"] == "en" else 0
    for p in proben:
        g = _named(rd, p.get("ziel")) if p.get("ziel") else None
        if not g or life.get(g["k"], 0) <= 0:
            rest.append({k: v for k, v in p.items() if k != "ziel"})
            continue
        h = rd["plaetze"][p["pid"]]["held"]
        a = rd["offen"].get(p["pid"]) or {}
        spell = dm._by(r, "gegenstaende").get(a.get("kraft") or "")
        wp = _weapon(dm, r, h)
        if spell and spell.get("segen"):
            wert, wuerfel, plus, mit = spell["segen"]["wert"], ZAUBER_W[min(5, spell.get("grad", 0))], spell["segen"]["bonus"], spell["name"][li].split(": ", 1)[-1]
        elif wp:
            c = dm._c(r, wp)
            wert, wuerfel, plus, mit = c["wert"], c["schaden"], 0 if wp.get("u") else wp.get("bonus", 0), wp.get("eigen") or c["name"][li]
        else:
            wert, wuerfel, plus, mit = "staerke", FAUST, 0, ("Fäuste" if not li else "fists")
        vt = p.get("vt") or ""
        ws = [rng.randint(1, 20) for _ in range(2 if vt else 1)]
        w = max(ws) if vt == "vorteil" else min(ws)
        bonus = dm.total(r, h, wert) + prof(h["stufe"]) + (plus if spell else 0)
        hit = w == 20 or (w != 1 and w + bonus >= g["rk"])
        n = 0
        if hit:
            n = max(1, _dice(rng, 2 if w == 20 else 1, wuerfel) + dm.mod(h["werte"].get(wert, 10)) + (0 if spell else plus))
            life[g["k"]] -= n
        out.append({"pid": p["pid"], "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": mit, "wert": wert, "w": w,
                    "ws": ws, "vt": vt, "bonus": bonus, "gesamt": w + bonus, "rk": g["rk"], "treffer": hit, "krit": w == 20,
                    "schaden": n, "faellt": hit and life[g["k"]] <= 0})
    return rest, out


def foes_turn(dm, r, rd, hits, rng=None):
    """Every foe still up after the heroes' attacks attacks one hero: the last who hit it, else one standing hero by
    the seed. [{k, gegner, pid, name, w, gesamt, rk, treffer, schaden}]."""
    rng = rng or random
    if not rd.get("kampf"):
        return []
    down = {x["ziel"] for x in hits if x["faellt"]}
    standing = [(pid, p["held"]) for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    if not standing:
        return []
    out = []
    for g in up(rd):
        if g["k"] in down:
            continue
        by = [x["pid"] for x in hits if x["ziel"] == g["k"] and x["treffer"]]
        pid, h = next(((q, hh) for q, hh in standing if by and q == by[-1]), None) or standing[rng.randrange(len(standing))]
        w = rng.randint(1, 20)
        ac = rk(dm, r, h)
        hit = w == 20 or (w != 1 and w + g["angriff"] >= ac)
        n = max(1, _dice(rng, g["wuerfel"] * (2 if w == 20 else 1), g["schaden"]) + g["plus"]) if hit else 0
        out.append({"k": g["k"], "gegner": g["name"], "pid": pid, "name": h["name"], "w": w, "bonus": g["angriff"],
                    "gesamt": w + g["angriff"], "rk": ac, "treffer": hit, "krit": w == 20, "schaden": n})
    return out


def facts(dm, r, rd, held, li):
    """The fight for the model: every foe with its life, or the offer when there is none."""
    k = rd.get("kampf")
    if k:
        return {"kampf": {"gefahr": k["gefahr"], "gegner": [{"name": g["name"], "leben": f"{max(0, g['leben'])}/{g['max']}",
                                                              **({"aus": g["aus"]} if g["aus"] else {})} for g in k["gegner"]]}}
    o = offer_facts(dm, r, rd, held, li)
    return {"angebot": o} if o else {}


def task(rd, lang):
    return " " + (AUFGABE_KAMPF if rd.get("kampf") else AUFGABE_ANGEBOT)[lang]


def apply(dm, r, rd, hits, zuege, ende, ep, rng=None):
    """The rolled fight into the round: the heroes' hits on the foes, flight, the foes' attacks as consequences for
    dungeon.consequences, the end. Returns the foes' hits as folgen [{pid, art, zahl, gegner}]."""
    rng = rng or random
    k = rd.get("kampf")
    if not k:
        return []
    by = {g["k"]: g for g in k["gegner"]}
    folgen = []
    for x in hits:
        g = by.get(x["ziel"])
        if not g or g["aus"]:
            continue
        dm._log(rd, "angriff", pid=x["pid"], name=x["name"], gegner=g["name"], mit=x["mit"], w=x["w"], ws=x["ws"], vt=x["vt"],
                bonus=x["bonus"], gesamt=x["gesamt"], rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"])
        dm._day.bump("treffer" if x["treffer"] else "daneben")
        if x["treffer"]:
            g["leben"] = max(0, g["leben"] - x["schaden"])
            if g["leben"] <= 0:
                g["aus"] = "besiegt"
                dm._log(rd, "gegner", gegner=g["name"], was="besiegt")
                dm._day.bump("besiegt")
    seats = dict(dm.seated(rd))
    for x in zuege:
        g = by.get(x["k"])
        if not g or g["aus"] or x["pid"] not in seats or dm.zustand(seats[x["pid"]]["held"]):
            continue
        dm._log(rd, "angriff", gegner=g["name"], pid=x["pid"], name=x["name"], w=x["w"], bonus=x["bonus"], gesamt=x["gesamt"],
                rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"], von_gegner=True)
        if x["treffer"]:
            folgen.append({"pid": x["pid"], "art": "schaden", "zahl": x["schaden"], "gegner": g["name"]})
    for g in up(rd):
        if 0 < g["leben"] * FLUCHT <= g["max"] and rng.randint(1, 20) <= FLUCHT_W:
            g["aus"] = "geflohen"
            dm._log(rd, "gegner", gegner=g["name"], was="aufgegeben" if dm.kids(r, rd) else "geflohen")
            dm._day.bump("geflohen")
    if not up(rd) or ende in ENDE:
        end(dm, r, rd, ep, ende)
    return folgen


def end(dm, r, rd, ep, why=""):
    """The fight is over: the defeated foes' experience (half for the fled ones) divided by the living heroes into ep
    (pid -> number, apply gives it to the table), one find for the group, a line for the log. A won fight of a room
    of the map leaves rd["sieg"] = the room's tag for dungeon_karte (the way is free)."""
    k = rd.pop("kampf", None)
    if not k:
        return
    besiegt = [g for g in k["gegner"] if g["aus"] == "besiegt"]
    flohen = [g for g in k["gegner"] if g["aus"] == "geflohen"]
    alle = sum(g["ep"] for g in besiegt) + sum(g["ep"] // 2 for g in flohen)
    each = -(-alle // max(1, len(ep))) if ep else 0
    for pid in ep:
        ep[pid] += each
    if k.get("raum") and not why:
        rd["sieg"] = k["raum"]
        rd.pop("raum_gegner", None)
    dm._log(rd, "kampf", was=why or "sieg", besiegt=len(besiegt), geflohen=len(flohen), ep=each)
    dm._day.bump("kaempfe")
    print(f"dungeon: kampf | ende | {why or 'sieg'} | {len(besiegt)} besiegt | {len(flohen)} geflohen", flush=True)
    return besiegt


def view(dm, r, rd):
    """The fight bar: every foe with its sign, picture, life and whether it is out. None without a fight."""
    k = rd.get("kampf")
    if not k:
        return None
    import dungeon_dingbild as db
    have = db.files() if db.on() else frozenset()
    lang, cat = "en" if rd.get("lang") == "en" else "de", dm._by(r, "gegner")
    out = [dict(card(dm, r, rd, g["id"], lang) if g["id"] in cat else {}, k=g["k"], id=g["id"], name=g["name"], zeichen=g["zeichen"],
                leben=max(0, g["leben"]), max=g["max"], aus=g["aus"], bild=_picture(r, rd, g["id"], have)) for g in k["gegner"]]
    return {"gegner": out, "gefahr": k["gefahr"], "stehen": len(up(rd))}


def _picture(r, rd, gid, have):
    import dungeon_dingbild as db
    c = next((x for x in r.get("gegner") or [] if x["id"] == gid), None)
    n = db.picture_of(r, c, rd.get("welt", ""))[0] if c and have else ""
    return n if n in have else ""


def pictures(dm, r, rd, out):
    """view's step for the log: every foe of an encounter card gets "bild" (its bestiary picture, "" while none)."""
    import dungeon_dingbild as db
    have = db.files() if db.on() else frozenset()
    out["log"] = [dict(e, gegner=[dict(g, bild=_picture(r, rd, g["id"], have)) for g in e["gegner"]]) if e.get("art") == "begegnung" else e
                  for e in out.get("log") or []]


def card(dm, r, rd, gid, lang):
    """One foe of the bestiary for its window at the table: picture, text and values."""
    li = 1 if lang == "en" else 0
    c = dm._by(r, "gegner")[gid]
    return {"id": c["id"], "name": c["name"][li], "info": c["info"][li], "zeichen": c.get("zeichen", ""), "stufe": c["stufe"],
            "leben": c["leben"], "rk": c["ruestung"], "angriff": c["angriff"], "groesse": c.get("groesse", "mittel"),
            "schaden": f"{c.get('anzahl_wuerfel', 1)}{'W' if not li else 'd'}{c['schaden']}" + (f"+{c['schaden_plus']}" if c.get("schaden_plus", 0) > 0 else
                                                                                               f"{c['schaden_plus']}" if c.get("schaden_plus", 0) < 0 else ""),
            "ep": c["ep"],
            # for the big window (Dominik 2026-10-24 „click auf beute etc. sollte ein fenster aufgehen lassen um es genauer zu
            # betrachten - auch gegener“, 1a): the six scores with their bonus and what its blows can cause
            "werte": [{"kurz": w["name"][li][:3].upper(), "name": w["name"][li], "wert": (c.get("werte") or {}).get(w["id"], 10),
                       "mod": dm.mod((c.get("werte") or {}).get(w["id"], 10))} for w in r["werte"]],
            "zustaende": [{"name": z["name"][li], "info": z["info"][li]} for z in r.get("zustaende") or [] if z["id"] in (c.get("zustaende") or [])]}


def for_live(rs):
    return {"kaempfe_laufen": sum(1 for v in rs if v.get("kampf")), "gegner_stehen": sum(len(up(v)) for v in rs)}
