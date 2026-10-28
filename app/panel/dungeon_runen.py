"""KI-Dungeon-Master: runes and sockets (plan dungeon-runen/plan.md, Dominik 2026-10-27 „1a 2b 3a 4a 5a 6a 7a 8a 10a
11a“): the catalog's 13 runes and 7 runewords in dungeon_srd.json (thread „DnDAppFiles für den Dungeon-Master“; the rune
names are historical runes, public domain) and their check by fixed rules.

r["runen"] = [{"id", "rang": 1..13 without a gap, "name": [de, en], "sinn": [de, en], "preis", "waffe": W|null,
"ruestung": W|null, "schild": W|null}]: what the rune does in a weapon, in a worn piece (body, head, hands, feet) or in a
shield; null = not there. r["runenwoerter"] = [{"id", "name": [de, en], "runen": [rune ids in this order], "ort":
ORTE_RW, "sockel": len(runen), "ab": level, "zusatz": W}]. A W is an object of WIRKUNG keys only. The panel decides
everything (which rune falls, sockets, effect, cap, price); the model only tells the fixed line. The world's word for a
rune (Rune, Chip, Perle, Siegel) and the sockets per base item are code rules, not catalog fields.

At the table (Stufe 1: sockets and runes; Stufe 2 and 3, Dominik 2026-10-28 „mit runen weiter machen bis zum
schluss“: runewords, the smith's services, fusing, giving runes): the admin's switch dungeonrunen (features.py,
chat.dungeon_runen, off) for the round's host. Off later, runes and sockets stay with the heroes but do nothing and fall
no more (13a, wirkt). Fixed rules of the panel, never the model:
    it["so"]   sockets of a weapon or armour of a rarity up to „rar“ (2b), by its base (3a, sockel_max), from a find or
               one drilled by the smith (it["gebohrt"], at most one a thing, 7a)
    it["ru"]   the rune ids in the sockets, in order; a rune sits for good (5a), only the smith takes them out (6a)
    it["rw"]   the runeword awake in it (match: its runes in this order, exactly as many sockets, a plain base at the
               runeword's place, the hero at its level „ab“; wake) with its extra effect under the runeword's cap
    h["runen"] {rune id: count}: the hero's rune bag beside the bag (it takes no bag place, BEUTEL_MAX runes)
    rd["runen_pech"] fights' finds without a rune in a row (4a: after PECH the next fight's find brings one)
    rd["runen_fund"] {hid: runes found this round}: a find's rune goes to the hero with the fewest
What a rune does at its place comes through the rules that are there (dungeon.item_effects, worn_bonuses, life,
resists, rabatt, dungeon_kampf.rk and attacks), each with its cap (9a, check and the per-hero sums below).
"""
import os
import random
import re

import dungeon_kampf as kampf
from common import DayCounter

ORTE = ("waffe", "ruestung", "schild")                     # where a rune sits
ORTE_RW = ("waffe", "koerper", "nebenhand", "kopf")         # where a runeword sits
WIRKUNG = {"treffer": (1, 2), "schaden": (1, 2), "leben": (1, 8), "rabatt": (1, 20), "gold": (1, 10), "heiltrank": (1, 4),
           "rk": (1, 1), "schutz": (1, 1), "bonus": (1, 1), "effekt": None, "werte": None, "widerstand": None}   # int keys: (lo, hi)
RAENGE = 13
RUNENWORT_MAX = 6           # runes in one runeword
AB_MAX = 20
PREIS_MAX = 4000            # at most „episch“
_ID = re.compile(r"[a-z0-9_]{2,24}")
NAME_MAX = 40


def _pair(x, n=NAME_MAX):
    import dungeon                       # the one helper of the rules (loaded already: dungeon.check_rules calls here)
    return dungeon._pair(x, n)


def _int(x, lo, hi):
    import dungeon
    return dungeon._int(x, lo, hi)


def _art(ort):
    """The art of the base item a rune or runeword sits in (an effect's „nur“ names arts)."""
    return "waffe" if ort == "waffe" else "ruestung"


def wirkung_ok(r, w, ort):
    """A W by fixed rules: only WIRKUNG keys, numbers in their range, "werte" with "bonus", an effect of the rules that
    may sit at this place, a damage type of the list."""
    if not isinstance(w, dict) or not w or not set(w) <= set(WIRKUNG):
        return False
    if any(rng and not _int(w[k], *rng) for k, rng in WIRKUNG.items() if k in w):
        return False
    werte = {x["id"] for x in r.get("werte") or [] if isinstance(x, dict)}
    if ("werte" in w) != ("bonus" in w) or "werte" in w and not (isinstance(w["werte"], list) and w["werte"] and set(w["werte"]) <= werte):
        return False
    if "widerstand" in w and w["widerstand"] not in kampf.SCHADEN_ARTEN:
        return False
    if "effekt" in w:
        e = next((x for x in r.get("effekte") or [] if isinstance(x, dict) and x.get("id") == w["effekt"]), None)
        if e is None or e.get("nur") and _art(ort) not in e["nur"]:
            return False
    return not ("treffer" in w or "schaden" in w) or ort == "waffe"


def check_rules(r):
    """The runes and runewords by fixed rules: German sentences of what is wrong (dungeon.check_rules adds them). Both
    lists are optional; what stands there must be whole."""
    err = []

    def need(ok, text):
        if not ok:
            err.append(text)
    rs = r.get("runen")
    if rs is None and r.get("runenwoerter") is None:
        return err
    by = {}
    need(isinstance(rs, list) and all(isinstance(x, dict) for x in rs), "runen: eine Liste von Runen")
    for x in rs if isinstance(rs, list) else []:
        if not isinstance(x, dict):
            continue
        need(isinstance(x.get("id"), str) and _ID.fullmatch(x["id"]) and x["id"] not in by, f"runen {x.get('id')}: eigene id aus a-z, 0-9 und _")
        by[x.get("id")] = x
        need(_int(x.get("rang"), 1, RAENGE) and _pair(x.get("name")) and _pair(x.get("sinn")) and _int(x.get("preis"), 1, PREIS_MAX),
             f"runen {x.get('id')}: rang 1 bis {RAENGE}, name und sinn als [deutsch, englisch], preis 1 bis {PREIS_MAX}")
        need(all(o in x for o in ORTE) and any(x[o] is not None for o in ORTE)
             and all(x[o] is None or wirkung_ok(r, x[o], o) for o in ORTE),
             f"runen {x.get('id')}: waffe, ruestung und schild je eine Wirkung oder null (Treffer und Schaden nur in der Waffe, "
             "Effekte nur, wo ihr „nur“ passt)")
    if isinstance(rs, list) and rs:
        need(sorted(x.get("rang") for x in rs if isinstance(x, dict) and _int(x.get("rang"), 1, RAENGE)) == list(range(1, len(rs) + 1)),
             "runen: jeder Rang von 1 an genau einmal, ohne Lücke")
    ws = r.get("runenwoerter") or []
    need(isinstance(ws, list) and all(isinstance(x, dict) for x in ws), "runenwoerter: eine Liste von Runenwörtern")
    seen, folgen = set(), set()
    for x in ws if isinstance(ws, list) else []:
        if not isinstance(x, dict):
            continue
        need(isinstance(x.get("id"), str) and _ID.fullmatch(x["id"]) and x["id"] not in seen, f"runenwoerter {x.get('id')}: eigene id")
        seen.add(x.get("id"))
        ru, ort = x.get("runen"), x.get("ort")
        stelle = "waffe" if ort == "waffe" else "schild" if ort == "nebenhand" else "ruestung"
        ok = isinstance(ru, list) and 2 <= len(ru) <= RUNENWORT_MAX and all(isinstance(i, str) and i in by for i in ru)
        need(ok and ort in ORTE_RW and all(by[i].get(stelle) is not None for i in ru) and x.get("sockel") == len(ru)
             and tuple(ru) not in folgen,
             f"runenwoerter {x.get('id')}: runen (2 bis {RUNENWORT_MAX} vorhandene, jede an diesem Ort möglich, keine Folge doppelt), "
             f"ort aus {', '.join(ORTE_RW)}, sockel = Zahl der Runen")
        if ok:
            folgen.add(tuple(ru))
        need(_pair(x.get("name")) and _int(x.get("ab"), 1, AB_MAX) and ort in ORTE_RW and wirkung_ok(r, x.get("zusatz"), _art(ort)),
             f"runenwoerter {x.get('id')}: name als [deutsch, englisch], ab Stufe 1 bis {AB_MAX}, zusatz eine Wirkung")
    return err


# ---------------------------------------------------------------- Stufe 1 at the table: sockets and runes
KEY = "dungeonrunen"
SOCKEL_BIS = 2             # the rank of the rarity up to which a thing has sockets (2b: up to „rar“)
SOCKEL_FUND = 30           # percent of the finds of such a thing that come with their sockets
SOCKEL_GROSS = 8           # a weapon with this die or more has 3 sockets, else 2 (3a)
SOCKEL_PLATZ = {"koerper": 3, "kopf": 2, "nebenhand": 2, "haende": 1, "fuesse": 1}   # armour by its place (3a)
FUND = {"gegner": 5, "truhe": 15, "belohnung": 20, "boss": 100}   # percent a find brings a rune (4a, a boss always)
PECH = 8                   # fights' finds without a rune, then the next one brings a rune surely (4a)
RANG_PLUS = 2              # the highest rank that falls: the group's level + 2
KRAEMER = 4                # a trader sells the ranks 1 to KRAEMER (4a; review 27.10.: shops only up to rank 4)
KRAEMER_N = (1, 3)         # of each rank
BEUTEL_MAX = 40            # runes in one hero's rune bag
DECKEL = {"waffe": 6.5, "koerper": 6.0, "rest": 3.0}   # 9a: a thing with runes at most as strong as „episch“
EFFEKT_STAERKE = {"schaden": 3.5, "lebensraub": 2.5}  # a rune's effect for the cap (any other 1, a value's its bonus)
EFFEKT_WAFFE = 3.5         # a weapon's own effect (from „rar“ on) counts as +1W6 whatever it is (the plan's scale)
RK_DING, RK_HELD = 2, 3    # armour class from runes per thing and per hero (9a)
LEBEN_HELD = 8             # life from runes per hero (9a)
WIDERSTAND_DING = 1        # damage kinds from runes per thing (9a)
WIDERSTAND_RW = 2          # a thing with a runeword: two
DECKEL_RW = {"waffe": 10.0, "koerper": 8.0, "rest": 4.0}   # 9a: a runeword at most as strong as „legendär“
RW_WERT = 8                # a runeword's worth: the runes' prices and its base's price RW_WERT times more (plan)
# the smith's services for runes (6a, 7a, 8a; dungeon_gold.serve, only with „Gold mit Zweck“ and while on)
DIENSTE = ("sockel", "loesen", "verschmelzen")
BOHREN = 25                # drilling a socket: gold × the group's level × the new socket count, never fails
ZERSTOEREN = 5             # taking the runes out and breaking them: gold × the group's level
RETTEN = 2                 # taking them out whole: the runes' prices / RETTEN (half), they go back into the bag
VERSCHMELZEN = 3           # the same runes fused into one of the next rank
VERSCHMELZEN_BIS = 9       # the highest rank fusing makes (10 to 13 only from finds)
VERSCHMELZEN_TEIL = 4      # its price: the new rune's price / VERSCHMELZEN_TEIL
TREFFER_MAX = 3            # to hit from the rarity and the runes of a weapon together (dungeon.BONUS_MAX, 9a)
# 10a: the same rules in every world, only the word changes (like dungeon_karte.SCHLUESSEL): [one, many] in [de, en]
ART_WELT = {"fantasy": (("Rune", "rune"), ("Runen", "runes")), "scifi": (("Chip", "chip"), ("Chips", "chips")),
            "piraten": (("Perle", "pearl"), ("Perlen", "pearls")), "horror": (("Siegel", "seal"), ("Siegel", "seals"))}
GRUENDE = ("ok", "voll", "deckel", "kampf", "aus", "sockel")   # why an insert goes or not (journal, preview)
_day = DayCounter(gefunden=0, eingesetzt=0, abgelehnt=0, gekauft=0, verkauft=0, sockel=0, runenwoerter=0, gebohrt=0,
                  geloest=0, verschmolzen=0, geschenkt=0)
_wirkt = {"k": None, "v": False}


def on(rd):
    """Runes fall and are set at this table: the admin's switch for the round's host."""
    import features
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def wirkt():
    """Whether runes do anything (13a: off, they stay with the heroes but do nothing): the admin's switch, read again
    only when the config file changed (the rules ask it in every fight and check)."""
    import common
    import features
    try:
        st = os.stat(common.CONFIG_PATH)
        k = (common.CONFIG_PATH, st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return False
    if k != _wirkt["k"]:
        try:
            v = features.admin_on(KEY)
        except Exception:  # noqa: BLE001 - a broken config: runes do nothing
            v = False
        _wirkt.update(k=k, v=bool(v))
    return _wirkt["v"]


def by(r):
    return {x["id"]: x for x in r.get("runen") or [] if isinstance(x, dict)}


def words(r):
    return {x["id"]: x for x in r.get("runenwoerter") or [] if isinstance(x, dict)}


def word(welt, li, many=False):
    """The world's word for a rune (10a)."""
    return ART_WELT.get(welt, ART_WELT["fantasy"])[1 if many else 0][li]


def place(dm, r, it):
    """Where a thing takes runes: "waffe", "schild" (a shield in the off hand), "ruestung" (body, head, hands, feet) or
    None (jewellery and the rest)."""
    c = dm._c(r, it)
    if c["art"] == "waffe":
        return "waffe"
    if c["art"] == "ruestung" and dm.places(r, c):
        return "schild" if dm.places(r, c)[0] == "nebenhand" else "ruestung"
    return None


def body_part(dm, r, it):
    c = dm._c(r, it)
    return dm.places(r, c)[0] if dm.places(r, c) else ""


def rw_place(dm, r, it):
    """Where a thing takes a runeword (ORTE_RW): a weapon "waffe", a shield "nebenhand", armour by its body part, else ""."""
    o = place(dm, r, it)
    return "waffe" if o == "waffe" else "nebenhand" if o == "schild" else body_part(dm, r, it) if o else ""


def match(dm, r, it, ru=None):
    """The runeword the runes ru (else the thing's) make in this thing, or None: the runeword's runes in its order,
    exactly as many sockets, a plain base („gewöhnlich“, known), at the runeword's place."""
    ru = list(it.get("ru") or []) if ru is None else list(ru)
    if not ru or it.get("so") != len(ru) or it.get("u") or it.get("s") != r["seltenheit"][0]["id"]:
        return None
    o = rw_place(dm, r, it)
    return next((x for x in words(r).values() if x.get("runen") == ru and x.get("ort") == o), None)


def word_of(r, it):
    """The runeword awake in a thing (it["rw"], set by the panel only), or None."""
    return words(r).get(it["rw"]) if it.get("rw") else None


def sockel_max(dm, r, it):
    """The sockets a thing can have by its base (3a): a weapon of SOCKEL_GROSS or more 3, else 2; armour by its place;
    0 for anything else, above „rar“ (2b), a legend or an unknown thing."""
    ids = [x["id"] for x in r["seltenheit"]]
    if it.get("leg") or it.get("u") or it.get("s") not in ids or ids.index(it["s"]) > SOCKEL_BIS or not place(dm, r, it):
        return 0
    c = dm._c(r, it)
    if c["art"] == "waffe":
        return 3 if c.get("schaden", 0) >= SOCKEL_GROSS else 2
    return SOCKEL_PLATZ.get(body_part(dm, r, it), 0)


def give_sockets(dm, r, rd, it, rng=None):
    """A find of a thing that can have sockets comes with them in SOCKEL_FUND of a hundred (only while on)."""
    n = on(rd) and sockets(dm, r, it, rng)
    if n:
        _day.bump("sockel")
        print(f"dungeon: rune | sockel | {n}", flush=True)


def sockets(dm, r, it, rng=None):
    """The roll of give_sockets (the balance bench rolls it too): the sockets the thing gets now, 0 for none."""
    rng = rng or random
    n = sockel_max(dm, r, it)
    if not n or "so" in it or rng.randrange(100) >= SOCKEL_FUND:
        return 0
    it["so"], it["ru"] = n, []
    return n


def _w(r, it, ort, ru=None, rw=None):
    """The Ws of the runes in a thing at its place and its runeword's extra (ru and rw: another list and runeword for
    the preview; without ru the thing's own and its awake runeword)."""
    rs = by(r)
    rw = word_of(r, it) if ru is None else rw
    return [rs[x][ort] for x in (it.get("ru") or [] if ru is None else ru) if x in rs and rs[x].get(ort)] + ([rw["zusatz"]] if rw else [])


def wirkungen(dm, r, it, ru=None, rw=None):
    """The Ws of the runes in a thing and of its runeword, [] while the switch is off (13a) or without runes."""
    if not (it.get("ru") if ru is None else ru) or not wirkt():
        return []
    o = place(dm, r, it)
    return _w(r, it, o, ru, rw) if o else []


def effects(dm, r, it, ru=None, rw=None):
    """The catalog effects (r["effekte"]) the runes of a thing and its runeword give, each once and none the thing has
    already (the same element counts once a thing, 9a): for dungeon.item_effects."""
    eff = dm._by(r, "effekte")
    own = {it.get("eff"), it.get("eff2")}
    out = []
    for w in wirkungen(dm, r, it, ru, rw):
        e = eff.get(w.get("effekt"))
        if e and e["id"] not in own and e not in out:
            out.append(e)
    return out


def _value(h, w):
    """The value a rune of „werte“ raises: the hero's higher of its list (Ansuz: Intelligenz or Weisheit)."""
    ws = w["werte"]
    return max(ws, key=lambda x: (h["werte"].get(x, 10), -ws.index(x))) if h else ws[0]


def value_bonuses(dm, r, h, it):
    """[(value, bonus)] of the runes of a thing (dungeon.worn_bonuses: the strongest of a value counts, B13)."""
    return [(_value(h, w), w["bonus"]) for w in wirkungen(dm, r, it) if w.get("werte")]


def hit(dm, r, it):
    """To hit from the runes of a weapon: only for its attacks (never in it["bonus"], which counts in checks), the
    rarity's bonus and the runes together at most TREFFER_MAX."""
    n = sum(w.get("treffer", 0) for w in wirkungen(dm, r, it))
    return max(0, min(n, TREFFER_MAX - (0 if it.get("u") else it.get("bonus", 0))))


def damage(dm, r, it):
    return sum(w.get("schaden", 0) for w in wirkungen(dm, r, it))


def _ac(dm, r, it, ws):
    k = 2 if body_part(dm, r, it) == "koerper" else 1      # the body counts twice in the armour class
    return sum(w.get("rk", 0) + w.get("schutz", 0) * k for w in ws)


def armour(dm, r, h):
    """The armour class from the runes the hero wears: at most RK_DING a thing (check) and RK_HELD a hero."""
    return min(RK_HELD, sum(min(RK_DING, _ac(dm, r, it, wirkungen(dm, r, it))) for it in dm.worn(h)))


def life(dm, r, h):
    """Life from the runes the hero wears, at most LEBEN_HELD."""
    return min(LEBEN_HELD, sum(w.get("leben", 0) for it in dm.worn(h) for w in wirkungen(dm, r, it)))


def resists(dm, r, h):
    return {w["widerstand"] for it in dm.worn(h) for w in wirkungen(dm, r, it) if w.get("widerstand")}


def discount(dm, r, h):
    """The merchant's discount from runes in percent (Fehu; dungeon.rabatt keeps its cap)."""
    return sum(w.get("rabatt", 0) for it in dm.worn(h) for w in wirkungen(dm, r, it))


def gold(dm, r, h):
    """Gold per defeated foe from the weapon's runes (Fehu), once a hero."""
    return max((w.get("gold", 0) for it in dm.worn(h) if place(dm, r, it) == "waffe" for w in wirkungen(dm, r, it)), default=0)


def potion(dm, r, h):
    """Life more from a healing potion (Berkano in a shield), at most WIRKUNG["heiltrank"]."""
    return min(WIRKUNG["heiltrank"][1], sum(w.get("heiltrank", 0) for it in dm.worn(h) for w in wirkungen(dm, r, it)))


def strength(dm, r, it, ru=None, rw=None):
    """A thing's magic strength for the cap (9a), in the units of dungeon.strength: its rarity's bonus (twice on the
    body), its own effect (a weapon's EFFEKT_WAFFE, armour's by EFFEKT_STAERKE), every effect of its runes once
    (EFFEKT_STAERKE, a value's effect its bonus, else 1), the runes' hit and damage half a point each, a value +1 one,
    armour class and protection one (protection twice on the body). So „rar“ with a +1W6 rune is always too strong."""
    k = 2 if body_part(dm, r, it) == "koerper" else 1
    n = (0 if it.get("u") else it.get("bonus", 0)) * k
    eff = dm._by(r, "effekte")
    own = [eff[x] for x in (it.get("eff"), it.get("eff2")) if x in eff and not it.get("u")]
    ws = _w(r, it, place(dm, r, it), ru, rw) if place(dm, r, it) else []
    n += sum(EFFEKT_WAFFE if place(dm, r, it) == "waffe" else _eff(e) for e in own)
    n += sum(_eff(e) for e in (eff.get(w.get("effekt")) for w in ws) if e) - sum(_eff(e) for e in _twice(own, ws, eff))
    for w in ws:
        n += 0.5 * (w.get("treffer", 0) + w.get("schaden", 0)) + w.get("bonus", 0) + w.get("rk", 0) + w.get("schutz", 0) * k
    return round(n, 2)


def _eff(e):
    return EFFEKT_STAERKE.get(e.get("wirkung"), e.get("bonus") or 1)


def _twice(own, ws, eff):
    """Effects of runes counted more than once (the same element twice, or one the thing has): counted once."""
    seen, out = {e["id"] for e in own}, []
    for w in ws:
        e = eff.get(w.get("effekt"))
        if e and e["id"] in seen:
            out.append(e)
        elif e:
            seen.add(e["id"])
    return out


def extra(dm, r, it):
    """The runes' strength besides their effects, for dungeon.strength (▲/▼; the effects come through item_effects)."""
    k = 2 if body_part(dm, r, it) == "koerper" else 1
    return sum(0.5 * (w.get("treffer", 0) + w.get("schaden", 0)) + w.get("bonus", 0) + w.get("rk", 0) + w.get("schutz", 0) * k
               for w in wirkungen(dm, r, it))


def worth(r, it, base=0):
    """What the runes in a thing add to its worth (dungeon.price): their prices, with a runeword awake its base's
    price base RW_WERT times more."""
    rs = by(r)
    return sum(rs[x]["preis"] for x in it.get("ru") or [] if x in rs) + (base * RW_WERT if word_of(r, it) else 0)


def cap(dm, r, it, rw=False):
    """The strength a thing with runes may have at most (9a), with a runeword (rw) the runeword's."""
    d = DECKEL_RW if rw else DECKEL
    o = place(dm, r, it)
    return d["waffe"] if o == "waffe" else d["koerper"] if body_part(dm, r, it) == "koerper" else d["rest"]


def check(dm, r, rd, h, it, rid):
    """Whether the rune rid may go into the thing it: (reason, numbers). Reasons: "aus" (switch), "kampf" (never in a
    fight, 5a), "sockel" (no sockets, unknown rune, not at this place), "voll" (every socket taken), "deckel" (stronger
    than „episch“, to hit above TREFFER_MAX, armour class above RK_DING, a second damage kind, the same element twice),
    "ok"."""
    if not on(rd) or not wirkt():
        return "aus", {}
    if rd.get("kampf"):
        return "kampf", {}
    return fits(dm, r, h, it, rid)


def fits(dm, r, h, it, rid):
    """The rules part of check (the balance bench sets its runes by it): "sockel", "voll", "deckel" or "ok", with
    the numbers; "wort" names the runeword the rune completes, "wach" whether it wakes now (the hero at its level),
    then under the runeword's cap."""
    o, rs = place(dm, r, it), by(r)
    if rid not in rs or not it.get("so") or not o or not rs[rid].get(o) or not (h.get("runen") or {}).get(rid):
        return "sockel", {}
    ru = list(it.get("ru") or [])
    if len(ru) >= it["so"]:
        return "voll", {}
    neu = ru + [rid]
    m = match(dm, r, it, neu)
    wach = m if m and h.get("stufe", 1) >= m["ab"] else None
    vorher, nachher, deckel = strength(dm, r, it, ru), strength(dm, r, it, neu, wach), cap(dm, r, it, bool(wach))
    zahlen = {"vorher": vorher, "nachher": nachher, "deckel": deckel, "wort": m["id"] if m else "", "wach": bool(wach)}
    return ("deckel" if over(dm, r, it, neu, wach) else "ok"), zahlen


def over(dm, r, it, ru, rw=None):
    """Whether the runes ru (and the runeword rw) in a thing break a cap (9a): stronger than its cap, the same element
    twice, to hit above TREFFER_MAX, armour class above RK_DING, more damage kinds than WIDERSTAND_DING (a runeword
    WIDERSTAND_RW)."""
    ws = _w(r, it, place(dm, r, it), ru, rw)
    eff = dm._by(r, "effekte")
    return strength(dm, r, it, ru, rw) > cap(dm, r, it, bool(rw)) or bool(_twice([eff[x] for x in (it.get("eff"), it.get("eff2")) if x in eff], ws, eff)) \
        or sum(w.get("treffer", 0) for w in ws) + it.get("bonus", 0) > TREFFER_MAX or _ac(dm, r, it, ws) > RK_DING \
        or len({w["widerstand"] for w in ws if w.get("widerstand")}) > (WIDERSTAND_RW if rw else WIDERSTAND_DING)


def line(r, w, li):
    """What a W does in one fixed line (the bag, the socket line, the preview)."""
    eff = {x["id"]: x for x in r.get("effekte") or []}
    wn = {x["id"]: x["name"][li] for x in r.get("werte") or []}
    out = []
    if w.get("treffer"):
        out.append((f"+{w['treffer']} Treffer" if not li else f"+{w['treffer']} to hit"))
    if w.get("schaden"):
        out.append((f"+{w['schaden']} Schaden" if not li else f"+{w['schaden']} damage"))
    if w.get("werte"):
        out.append(" oder ".join(wn.get(x, x) for x in w["werte"]) if not li else " or ".join(wn.get(x, x) for x in w["werte"]))
        out[-1] += f" +{w['bonus']}" + ((" (der höhere)" if not li else " (the higher)") if len(w["werte"]) > 1 else "")
    if w.get("leben"):
        out.append((f"+{w['leben']} Leben max." if not li else f"+{w['leben']} max. life"))
    if w.get("rk"):
        out.append((f"Rüstungsklasse +{w['rk']}" if not li else f"armour class +{w['rk']}"))
    if w.get("schutz"):
        out.append((f"Schutz +{w['schutz']}" if not li else f"protection +{w['schutz']}"))
    if w.get("rabatt"):
        out.append((f"Händlerrabatt +{w['rabatt']} %" if not li else f"merchant discount +{w['rabatt']} %"))
    if w.get("gold"):
        out.append((f"+{w['gold']} Gold je besiegtem Gegner" if not li else f"+{w['gold']} gold per defeated foe"))
    if w.get("heiltrank"):
        out.append((f"Heiltränke heilen +{w['heiltrank']}" if not li else f"healing potions heal +{w['heiltrank']}"))
    if w.get("widerstand"):
        a = w["widerstand"]
        out.append(("Widerstand gegen " if not li else "resistance to ") + kampf.ART_ZEICHEN[a] + " " + kampf.ART_NAME[a][li])
    if w.get("effekt") in eff:
        out.append(eff[w["effekt"]]["satz"][li].rstrip("."))
    return ", ".join(out)


def item_lines(dm, r, it, li):
    """The socket line of a thing for dungeon.item_view: each rune with what it does here, the free sockets; a note
    while the switch is off."""
    if not it.get("so"):
        return []
    rs, o = by(r), place(dm, r, it)
    teile = [f"{rs[x]['name'][li]} ({line(r, rs[x][o], li)})" for x in it.get("ru") or [] if x in rs and o and rs[x].get(o)]
    frei = it["so"] - len(it.get("ru") or [])
    teile += [("frei" if not li else "free")] * max(0, frei)
    out = [("Sockel {}: " if not li else "Sockets {}: ").format(it["so"]) + " · ".join(teile)]
    rw, m = word_of(r, it), match(dm, r, it)
    if rw:
        out.append(("Runenwort {}: {}" if not li else "Runeword {}: {}").format(rw["name"][li], line(r, rw["zusatz"], li)))
    elif m:
        out.append(("Runenwort {} erwacht ab Stufe {}." if not li else "Runeword {} wakes from level {}.").format(m["name"][li], m["ab"]))
    if it.get("ru") and not wirkt():
        out.append("Runen ruhen: auf diesem Spark gerade aus." if not li else "Runes rest: switched off on this Spark right now.")
    return out


def fix(dm, r, h):
    """A hero read from a file: the rune bag only with runes of the catalog and whole counts, a thing's sockets only
    as its base allows and its runes only of the catalog at its place."""
    rs = by(r)
    rb = h.get("runen")
    h["runen"] = {k: int(v) for k, v in rb.items() if k in rs and isinstance(v, int) and not isinstance(v, bool) and v > 0} \
        if isinstance(rb, dict) else {}
    while sum(h["runen"].values()) > BEUTEL_MAX:
        k = max(h["runen"], key=lambda x: (h["runen"][x], x))
        h["runen"][k] -= 1
        h["runen"] = {k: v for k, v in h["runen"].items() if v > 0}
    for it in h["tasche"] + dm.worn(h):
        n = sockel_max(dm, r, it)
        if not n or not isinstance(it.get("so"), int) or isinstance(it.get("so"), bool) or it["so"] < 1:
            it.pop("so", None)
            it.pop("ru", None)
            continue
        it["so"] = min(it["so"], n)
        o = place(dm, r, it)
        ru = it.get("ru") if isinstance(it.get("ru"), list) else []
        it["ru"] = [x for x in ru if isinstance(x, str) and x in rs and rs[x].get(o)][:it["so"]]
        if it.get("gebohrt") is not True:
            it.pop("gebohrt", None)
        m = match(dm, r, it)
        if not m or it.get("rw") != m["id"]:
            it.pop("rw", None)                   # a runeword only where its runes sit as the panel set it


def bag(dm, r, h, lang, welt=""):
    """The hero's rune bag for the sheet: each rune with its count and what it does at each place, and where it fits
    now (the own things with a free socket that take it)."""
    li = 1 if lang == "en" else 0
    rs = by(r)
    frei = [it for it in dm.worn(h) + h["tasche"] if it.get("so") and len(it.get("ru") or []) < it["so"]]
    out = []
    for k, n in sorted((h.get("runen") or {}).items(), key=lambda x: rs[x[0]]["rang"] if x[0] in rs else 99):
        if k not in rs:
            continue
        x = rs[k]
        out.append({"id": k, "name": x["name"][li], "sinn": x["sinn"][li], "rang": x["rang"], "n": n, "preis": x["preis"],
                    "wirkung": {o: line(r, x[o], li) if x.get(o) else "" for o in ORTE},
                    "ziele": [it["i"] for it in frei if x.get(place(dm, r, it) or "")]})
    return {"wort": word(welt, li), "woerter": word(welt, li, True), "runen": out, "max": BEUTEL_MAX,
            "an": wirkt(), "frei": len(frei), "runenwoerter": goals(dm, r, h, li)}


ORT_NAME = {"waffe": ("Waffe", "weapon"), "koerper": ("Körper", "body"), "nebenhand": ("Schild", "shield"), "kopf": ("Kopf", "head")}


def goals(dm, r, h, li):
    """Every runeword as a goal to gather (plan, open question 3: known from the start): its runes in order and which
    of them the hero has (in the bag or set already), the place, sockets, level and extra, and the own things that
    take it now (a plain base at its place, exactly its sockets, the runes so far its start)."""
    rs, own = by(r), h.get("runen") or {}
    out = []
    for x in words(r).values():
        dinge = [it for it in dm.worn(h) + h["tasche"] if rw_place(dm, r, it) == x["ort"] and it.get("so") == x["sockel"]
                 and not it.get("u") and it.get("s") == r["seltenheit"][0]["id"] and (it.get("ru") or []) == x["runen"][:len(it.get("ru") or [])]]
        done = next((it for it in dinge if it.get("rw") == x["id"]), None)
        gesetzt = max((len(it.get("ru") or []) for it in dinge), default=0)
        out.append({"id": x["id"], "name": x["name"][li], "ort": ORT_NAME[x["ort"]][li], "sockel": x["sockel"], "ab": x["ab"],
                    "zusatz": line(r, x["zusatz"], li), "fertig": bool(done),
                    "runen": [{"id": k, "name": rs[k]["name"][li], "hat": j < gesetzt or bool(own.get(k))} for j, k in enumerate(x["runen"]) if k in rs],
                    "dinge": [dm.item_view(r, it, "en" if li else "de")["name"] for it in dinge if it is not done]})
    return out


def missing(r, g):
    """The names of a goal's runes the hero has not (the car's „Was fehlt für Sturmlied?“)."""
    return [x["name"] for x in g["runen"] if not x["hat"]]


def _rank(r, stufe, rng):
    """A rank up to the group's level + RANG_PLUS, the low ones more often (rank k by weight top − k + 1)."""
    top = max(1, min(len(r.get("runen") or []), stufe + RANG_PLUS))
    return rng.choices(range(1, top + 1), weights=[top - k + 1 for k in range(1, top + 1)])[0]


def find(dm, r, rd, held, anlass, rng=None):
    """A find's rune (4a): FUND percent by its occasion, a boss always, after PECH fights' finds without one surely;
    its rank by _rank; to the hero of held with the fewest runes found this round (the first on a tie), into its rune
    bag (a full bag: none). Returns the rune id or ""."""
    if not on(rd):
        return ""
    h, rid = draw(dm, r, rd, held, anlass, rng)
    if not rid:
        return ""
    li = 1 if rd.get("lang") == "en" else 0
    k = by(r)[rid]["rang"]
    dm._log(rd, "rune", was="fund", name=h["name"], rune=by(r)[rid]["name"][li], wort=word(rd.get("welt", ""), li), rang=k)
    _day.bump("gefunden")
    print(f"dungeon: rune | fund | rang {k}", flush=True)
    return rid


def draw(dm, r, rd, held, anlass, rng=None, stufe=None):
    """The roll of find (the balance bench draws by it too): (hero, rune id) into its rune bag, (None, "") for none;
    the rank by the group's level or stufe."""
    rng = rng or random
    if not held or anlass not in FUND or not r.get("runen"):
        return None, ""
    kampf_fund = anlass in ("gegner", "boss")
    pech = rd.get("runen_pech", 0)
    if not (rng.randrange(100) < FUND[anlass] or kampf_fund and pech >= PECH):
        if kampf_fund:
            rd["runen_pech"] = pech + 1
        return None, ""
    rd["runen_pech"] = 0
    gezaehlt = rd.setdefault("runen_fund", {})
    h = min(held, key=lambda x: (gezaehlt.get(x["hid"], 0), held.index(x)))
    if sum((h.get("runen") or {}).values()) >= BEUTEL_MAX:
        print("dungeon: rune | fund | beutel voll", flush=True)
        return None, ""
    k = _rank(r, stufe or dm.group_level(held), rng)
    rid = next(x["id"] for x in r["runen"] if x["rang"] == k)
    rb = h.setdefault("runen", {})
    rb[rid] = rb.get(rid, 0) + 1
    gezaehlt[h["hid"]] = gezaehlt.get(h["hid"], 0) + 1
    return h, rid


def stock(dm, r, rd, art, rng=None):
    """A trader's runes (4a): ranks 1 to KRAEMER, KRAEMER_N of each; none at another merchant or while off."""
    rng = rng or random
    if art != "kraemer" or not on(rd):
        return {}
    return {x["id"]: rng.randint(*KRAEMER_N) for x in r.get("runen") or [] if x["rang"] <= KRAEMER}


def buy_price(dm, r, h, rid):
    return max(1, -(-by(r)[rid]["preis"] * (100 - dm.rabatt(r, h)) // 100))


def sell_price(r, rid):
    return max(1, by(r)[rid]["preis"] // 2)


def market_view(dm, r, rd, h, lang):
    """The trader's runes and what the own runes fetch (half their price) for the merchant window."""
    m = rd.get("markt") or {}
    if not on(rd):
        return {}
    li, rs = (1 if lang == "en" else 0), by(r)
    return {"wort": word(rd.get("welt", ""), li, True),
            "ware": [{"id": k, "name": rs[k]["name"][li], "sinn": rs[k]["sinn"][li], "n": n, "preis": buy_price(dm, r, h, k) if h else rs[k]["preis"]}
                     for k, n in sorted((m.get("runen") or {}).items(), key=lambda x: rs[x[0]]["rang"]) if k in rs and n > 0],
            "verkauf": {k: sell_price(r, k) for k in (h.get("runen") or {}) if k in rs} if h else {}}


def act(dm, r, rd, pid, h, b):
    """The seat's rune move (dungeon.hero_act, was "rune"): {tun: "pruefen"|"einsetzen", rune, i} sets a rune into an
    own thing (worn or in the bag) after the preview; {tun: "kaufen"|"verkaufen", rune} at the merchant. Returns the
    preview for "pruefen" ({"rune_vorschau": …}), else None. Refusals: ValueError("rune …") with a fixed word."""
    tun, rid = b.get("tun"), b.get("rune")
    if tun not in ("pruefen", "einsetzen", "kaufen", "verkaufen") or not isinstance(rid, str) or rid not in by(r):
        raise ValueError("rune")
    li = 1 if rd.get("lang") == "en" else 0
    if tun in ("kaufen", "verkaufen"):
        return _trade(dm, r, rd, pid, h, tun, rid, li)
    it = next((x for x in dm.worn(h) + h["tasche"] if x["i"] == b.get("i")), None)
    if not it or not (h.get("runen") or {}).get(rid):
        raise ValueError("rune")
    grund, z = check(dm, r, rd, h, it, rid)
    if tun == "pruefen":
        print(f"dungeon: rune | pruefen | {grund}", flush=True)
        return {"rune_vorschau": preview(dm, r, rd, h, it, rid, grund, z, li)}
    if grund != "ok":
        _day.bump("abgelehnt")
        print(f"dungeon: rune | einsetzen | {grund}", flush=True)
        if grund == "kampf":
            raise FileExistsError("rune kampf")
        if grund == "aus":
            raise ValueError("rune aus")
        if grund == "voll":
            raise OverflowError("rune voll")
        if grund == "deckel":
            raise ValueError("rune deckel")
        raise ValueError("rune sockel")
    h["runen"][rid] -= 1
    h["runen"] = {k: v for k, v in h["runen"].items() if v > 0}
    it["ru"] = list(it.get("ru") or []) + [rid]
    dm._log(rd, "rune", was="eingesetzt", name=h["name"], rune=by(r)[rid]["name"][li], ding=dm.item_view(r, it, rd["lang"])["name"],
            wort=word(rd.get("welt", ""), li))
    _day.bump("eingesetzt")
    print("dungeon: rune | einsetzen | ok", flush=True)
    wake(dm, r, rd, h)
    if dm.life(r, h) != h["leben_max"]:
        dm.relife(r, h)                          # Uruz or Berkano in a thing worn: the life counts at once
    return None


def wake(dm, r, rd, h):
    """Every runeword of the hero's things whose runes are complete wakes once the hero has its level (after an
    insert and a new level), only under the runeword's caps; a fixed line at the table, then its picture (picture
    thread, dungeon_dingbild.runenwort). Returns how many woke."""
    n = 0
    for it in dm.worn(h) + h["tasche"]:
        m = match(dm, r, it)
        if not m or it.get("rw") or h.get("stufe", 1) < m["ab"]:
            continue
        if over(dm, r, it, list(it["ru"]), m):
            print("dungeon: rune | runenwort | deckel", flush=True)
            continue
        it["rw"] = m["id"]
        li = 1 if rd.get("lang") == "en" else 0
        dm._log(rd, "rune", was="runenwort", name=h["name"], runenwort=m["name"][li], ding=dm.item_view(r, it, rd["lang"])["name"],
                wirkung=line(r, m["zusatz"], li))
        _day.bump("runenwoerter")
        print("dungeon: rune | runenwort | ok", flush=True)
        n += 1
        try:
            import dungeon_dingbild
            if hasattr(dungeon_dingbild, "runenwort"):
                dungeon_dingbild.runenwort(r, rd, it)      # its own find picture (picture thread)
        except Exception:  # noqa: BLE001 - a picture never stops the game
            print("dungeon: rune | runenwort | bild fehler", flush=True)
    if n and dm.life(r, h) != h["leben_max"]:
        dm.relife(r, h)
    return n


def preview(dm, r, rd, h, it, rid, grund, z, li):
    """What the insert would do, in fixed sentences: the rune, the socket, what it does there, the strength against
    the cap, or why not."""
    x, o = by(r)[rid], place(dm, r, it)
    name = dm.item_view(r, it, rd["lang"])["name"]
    n = len(it.get("ru") or []) + 1
    warum = {"aus": ("Runen sind auf diesem Spark gerade aus.", "Runes are switched off on this Spark right now."),
             "kampf": ("Erst der Kampf: Solange er läuft, setzt niemand eine Rune ein.", "First the fight: nobody sets a rune while it runs."),
             "sockel": ("Das passt dort nicht: ein Ding mit freiem Sockel, an dem diese Rune wirkt.", "That does not fit there: a thing with a free socket where this rune works."),
             "voll": ("Jeder Sockel ist schon belegt.", "Every socket is taken already."),
             "deckel": ("Zu stark: höchstens wie „episch“ ({deckel}), wäre {nachher}; Treffer höchstens +3, Rüstungsklasse aus Runen höchstens +2 je Ding, "
                        "eine Widerstandsart je Ding, jedes Element nur einmal.",
                        "Too strong: at most like \"epic\" ({deckel}), would be {nachher}; to hit at most +3, armour class from runes at most +2 a thing, "
                        "one kind of resistance a thing, each element once.")}
    if grund != "ok":
        t = warum[grund][li]
        return {"ok": False, "grund": grund, "text": t.format(deckel=_num(z.get("deckel"), li), nachher=_num(z.get("nachher"), li)) if z else t}
    m = words(r).get(z.get("wort") or "")
    wort = "" if not m else (f" Dann erwacht das Runenwort {m['name'][0]}: {line(r, m['zusatz'], 0)}." if z.get("wach") and not li else
                             f" Then the runeword {m['name'][1]} wakes: {line(r, m['zusatz'], 1)}." if z.get("wach") else
                             f" Das Runenwort {m['name'][0]} erwacht erst ab Stufe {m['ab']}, bis dahin wirken nur die Runen." if not li else
                             f" The runeword {m['name'][1]} wakes only from level {m['ab']}, until then only the runes work.")
    t = (f"{x['name'][li]} in Sockel {n} von {name}: {line(r, x[o], li)}.{wort} Stärke {_num(z['vorher'], li)} → {_num(z['nachher'], li)} "
         f"(höchstens {_num(z['deckel'], li)}). Die Rune sitzt danach fest." if not li else
         f"{x['name'][li]} into socket {n} of {name}: {line(r, x[o], li)}.{wort} Strength {_num(z['vorher'], li)} → {_num(z['nachher'], li)} "
         f"(at most {_num(z['deckel'], li)}). The rune stays in for good.")
    return {"ok": True, "grund": "ok", "text": t, "rune": rid, "i": it["i"], **({"runenwort": m["name"][li], "wach": bool(z.get("wach"))} if m else {})}


def _num(x, li):
    if x is None:
        return ""
    s = f"{x:.1f}".rstrip("0").rstrip(".")
    return s if li else s.replace(".", ",")


def _trade(dm, r, rd, pid, h, tun, rid, li):
    m = rd.get("markt")
    if rd.get("kampf"):
        raise FileExistsError("markt kampf")
    if not on(rd):
        raise ValueError("rune aus")
    if not m:
        raise LookupError("haendler")
    import dungeon_tageszeit as tageszeit
    if tageszeit.zu(rd, "markt"):
        raise LookupError("nacht")
    x = by(r)[rid]
    if tun == "kaufen":
        preis = buy_price(dm, r, h, rid)
        if (m.get("runen") or {}).get(rid, 0) < 1 or h["gold"] < preis or sum((h.get("runen") or {}).values()) >= BEUTEL_MAX:
            print("dungeon: rune | kauf | abgelehnt", flush=True)
            raise ValueError("kaufen")
        m["runen"][rid] -= 1
        h["gold"] -= preis
        m["kasse"] = m.get("kasse", 0) + preis
        rb = h.setdefault("runen", {})
        rb[rid] = rb.get(rid, 0) + 1
        _day.bump("gekauft")
    else:
        preis = sell_price(r, rid)
        if not (h.get("runen") or {}).get(rid):
            raise ValueError("verkaufen")
        if preis > m.get("kasse", 0):
            print("dungeon: rune | verkauf | kasse leer", flush=True)
            raise ValueError("kasse")
        m["kasse"] -= preis
        h["runen"][rid] -= 1
        h["runen"] = {k: v for k, v in h["runen"].items() if v > 0}
        h["gold"] = min(dm.GOLD_MAX, h["gold"] + preis)
        _day.bump("verkauft")
    dm._log(rd, "handel", pid=pid, name=h["name"], was="kauf" if tun == "kaufen" else "verkauf",
            ding=f"{word(rd.get('welt', ''), li)} {x['name'][li]}", gold=preis)
    print(f"dungeon: rune | {'kauf' if tun == 'kaufen' else 'verkauf'} | rang {x['rang']}", flush=True)


# ---------------------------------------------------------------- Stufe 2 and 3: the smith's services, giving runes
def drillable(dm, r, it):
    """The socket count after the smith drills one (7a), 0 for none: at most one drilled socket a thing, never above
    its base's sockets (sockel_max), never into a thing with a runeword awake."""
    n = it.get("so", 0)
    if it.get("gebohrt") or it.get("rw") or n >= sockel_max(dm, r, it):
        return 0
    return n + 1


def rescue_price(r, it):
    """Taking the runes out whole (6a): half their prices."""
    rs = by(r)
    return max(1, sum(rs[x]["preis"] for x in it.get("ru") or [] if x in rs) // RETTEN)


def fused(r, rid):
    """The rune VERSCHMELZEN of rid make (8a): the next rank, at most VERSCHMELZEN_BIS; None else."""
    x = by(r).get(rid)
    if not x or x["rang"] >= VERSCHMELZEN_BIS:
        return None
    return next((y for y in by(r).values() if y["rang"] == x["rang"] + 1), None)


def fuse_price(r, rid):
    return max(1, fused(r, rid)["preis"] // VERSCHMELZEN_TEIL)


def service_price(dm, r, rd, h, b):
    """(price, target) of one of the smith's rune services (dungeon_gold.serve): {id: "sockel", i} drills a socket,
    {id: "loesen", i, wert: "zerstoeren"|"retten"} takes the runes out, {id: "verschmelzen", wert: rune id} fuses
    VERSCHMELZEN runes into one. Refusals: ValueError with a fixed word."""
    was = b.get("id")
    if not on(rd) or not wirkt():
        raise ValueError("rune aus")
    if was == "verschmelzen":
        rid = b.get("wert")
        if not isinstance(rid, str) or not fused(r, rid) or (h.get("runen") or {}).get(rid, 0) < VERSCHMELZEN:
            print("dungeon: dienst | verschmelzen | nein", flush=True)
            raise ValueError("verschmelzen")
        return fuse_price(r, rid), rid
    it = next((x for x in dm.worn(h) + h["tasche"] if x["i"] == b.get("i")), None)
    level = dm.group_level(dm._living(rd))
    if was == "sockel":
        n = drillable(dm, r, it) if it else 0
        if not n:
            print("dungeon: dienst | sockel | nein", flush=True)
            raise ValueError("bohren")
        return BOHREN * level * n, it
    if not it or not it.get("ru") or b.get("wert") not in ("zerstoeren", "retten"):
        print("dungeon: dienst | loesen | nein", flush=True)
        raise ValueError("loesen")
    if b["wert"] == "retten" and sum((h.get("runen") or {}).values()) + len(it["ru"]) > BEUTEL_MAX:
        print("dungeon: dienst | loesen | beutel voll", flush=True)
        raise ValueError("loesen voll")
    return (rescue_price(r, it) if b["wert"] == "retten" else ZERSTOEREN * level), it


def service(dm, r, rd, h, b, ziel):
    """Does the smith's rune service on its target (after service_price and the payment check): the fixed line
    (de, en) for the table."""
    li = 1 if rd.get("lang") == "en" else 0
    w = word(rd.get("welt", ""), 0, True), word(rd.get("welt", ""), 1, True)
    if b["id"] == "verschmelzen":
        x, y = by(r)[ziel], fused(r, ziel)
        rb = h["runen"]
        rb[ziel] -= VERSCHMELZEN
        rb[y["id"]] = rb.get(y["id"], 0) + 1
        h["runen"] = {k: v for k, v in rb.items() if v > 0}
        _day.bump("verschmolzen")
        print(f"dungeon: dienst | verschmelzen | rang {y['rang']}", flush=True)
        return (f"Der Schmied verschmilzt für {h['name']} {VERSCHMELZEN} {w[0]} {x['name'][0]} zu {y['name'][0]}.",
                f"The smith fuses {VERSCHMELZEN} {w[1]} {x['name'][1]} into {y['name'][1]} for {h['name']}.")
    name = dm.item_view(r, ziel, rd["lang"])["name"]
    if b["id"] == "sockel":
        ziel["so"] = drillable(dm, r, ziel)
        ziel.setdefault("ru", [])
        ziel["gebohrt"] = True
        _day.bump("gebohrt")
        print(f"dungeon: dienst | sockel | {ziel['so']}", flush=True)
        return (f"Der Schmied bohrt {name} von {h['name']} einen Sockel: jetzt {ziel['so']}.",
                f"The smith drills a socket into {h['name']}'s {name}: now {ziel['so']}.")
    ru, rw = list(ziel["ru"]), word_of(r, ziel)
    ziel["ru"] = []
    ziel.pop("rw", None)                         # a runeword always goes out (6a)
    if b["wert"] == "retten":
        rb = h.setdefault("runen", {})
        for x in ru:
            rb[x] = rb.get(x, 0) + 1
    if dm.life(r, h) != h["leben_max"]:
        dm.relife(r, h)
    _day.bump("geloest")
    print(f"dungeon: dienst | loesen | {b['wert']}", flush=True)
    erlischt = (f" Das Runenwort {rw['name'][0]} erlischt." if rw else "", f" The runeword {rw['name'][1]} goes out." if rw else "")
    if b["wert"] == "retten":
        return (f"Der Schmied löst {len(ru)} {w[0]} aus {name} von {h['name']}, sie sind wieder im Beutel.{erlischt[0]}",
                f"The smith takes {len(ru)} {w[1]} out of {h['name']}'s {name}, they are back in the bag.{erlischt[1]}")
    return (f"Der Schmied bricht {len(ru)} {w[0]} aus {name} von {h['name']}, die Sockel sind frei.{erlischt[0]}",
            f"The smith breaks {len(ru)} {w[1]} out of {h['name']}'s {name}, the sockets are free.{erlischt[1]}")


def smith_view(dm, r, rd, h, li):
    """What the smith can do with runes for the hero (the settlement window): things to drill with the price and the
    new socket count, things with runes with both prices for taking them out, runes to fuse."""
    if not on(rd) or not wirkt():
        return {}
    level = dm.group_level(dm._living(rd))
    lang = "en" if li else "de"
    pieces = dm.worn(h) + h["tasche"]
    rs = by(r)
    return {"wort": word(rd.get("welt", ""), li, True),
            "sockel": [dict(dm.item_view(r, it, lang), preis=BOHREN * level * n, neu=n) for it in pieces if (n := drillable(dm, r, it))],
            "loesen": [dict(dm.item_view(r, it, lang), zerstoeren=ZERSTOEREN * level, retten=rescue_price(r, it),
                            runenwort=(word_of(r, it) or {}).get("name", ["", ""])[li],
                            platz=sum((h.get("runen") or {}).values()) + len(it["ru"]) <= BEUTEL_MAX) for it in pieces if it.get("ru")],
            "verschmelzen": [{"id": k, "name": rs[k]["name"][li], "n": n, "neu": fused(r, k)["name"][li], "preis": fuse_price(r, k)}
                             for k, n in sorted((h.get("runen") or {}).items(), key=lambda x: rs[x[0]]["rang"] if x[0] in rs else 99)
                             if k in rs and n >= VERSCHMELZEN and fused(r, k)]}


def give(dm, r, rd, h, an, rid):
    """One rune from the hero's bag to another hero at the table (plan: giving goes like the bag's „schenken“);
    never in a fight, never into a full bag. Refusals: ValueError("rune schenken")."""
    if not on(rd) or rd.get("kampf") or not isinstance(rid, str) or not (h.get("runen") or {}).get(rid) \
            or sum((an.get("runen") or {}).values()) >= BEUTEL_MAX:
        print("dungeon: rune | schenken | nein", flush=True)
        raise ValueError("rune schenken")
    h["runen"][rid] -= 1
    h["runen"] = {k: v for k, v in h["runen"].items() if v > 0}
    rb = an.setdefault("runen", {})
    rb[rid] = rb.get(rid, 0) + 1
    li = 1 if rd.get("lang") == "en" else 0
    dm._log(rd, "rune", was="geschenkt", name=h["name"], an=an["name"], rune=by(r)[rid]["name"][li], wort=word(rd.get("welt", ""), li))
    _day.bump("geschenkt")
    print("dungeon: rune | schenken | ok", flush=True)


def word_mark(dm, r, w, lang="de"):
    """The balance mark of a runeword for the rules page (plan point 4, dungeon_balance's format): its strength in a
    plain base of its place with its sockets against the runeword's cap; above it „zu stark“, from 80 of 100 „stark“,
    under 30 „schwach“."""
    import dungeon_balance as balance
    en = lang == "en"
    base = r["seltenheit"][0]["id"]
    it = next((x for x in ({"i": "", "id": c["id"], "s": base, "bonus": 0, "so": w.get("sockel"), "ru": list(w.get("runen") or [])}
                           for c in r["gegenstaende"] if not c.get("seltenheit"))
               if rw_place(dm, r, x) == w.get("ort") and sockel_max(dm, r, x) >= (w.get("sockel") or 0)), None)
    if not it:
        return {"marke": "zu_stark", "name": balance.NAMEN["zu_stark"][en], "grund": "Kein Grundteil dafür." if not en else "No base for it.", "wert": 0}
    n, d = strength(dm, r, it, it["ru"], w), cap(dm, r, it, True)
    m = "zu_stark" if n > d or over(dm, r, it, it["ru"], w) else "stark" if n >= 0.8 * d else "schwach" if n < 0.3 * d else "ok"
    return {"marke": m, "name": balance.NAMEN[m][en], "wert": round(n / d, 2),
            "grund": f"Stärke {_num(n, 0)} von höchstens {_num(d, 0)}." if not en else f"Strength {_num(n, 1)} of at most {_num(d, 1)}."}


def fight_gold(dm, r, rd, held, besiegt):
    """Fehu in a weapon: GOLD per defeated foe for its hero, once a hero (after the fight's find)."""
    if not besiegt:
        return
    for h in held:
        g = gold(dm, r, h) * besiegt
        if g:
            h["gold"] = min(dm.GOLD_MAX, h["gold"] + g)
            print(f"dungeon: rune | gold | {g}", flush=True)


def for_live():
    """Numbers only: runes found, set, refused, bought and sold, things found with sockets, runewords woken, sockets
    drilled, things emptied, runes fused and given today."""
    t = _day.counts()
    return {k: t[k] for k in ("gefunden", "eingesetzt", "abgelehnt", "gekauft", "verkauft", "sockel", "runenwoerter", "gebohrt",
                              "geloest", "verschmolzen", "geschenkt")}
