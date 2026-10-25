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

Teil 2 (Kampf-Tiefe, Bestiarium-Punkte 4-6 and item point 2, Dominik 2026-10-24 „alles nach empfehlung umsetzten“):
    weapons    eigenschaften of the catalog, each a fixed rule (EIGENSCHAFT_REGEL): finesse and a throw take the better
               of Stärke and Geschick, vielseitig with a free off hand rolls a die two sides bigger, schwer without
               Stärke 13 attacks at a disadvantage, leicht is critical from 19, reichweite keeps the foe it hit at a
               distance (its attack on that hero this turn at a disadvantage)
    kinds      every hit has a damage kind (the weapon's schaden_art, a spell's, a foe's); a foe's resistenz halves it,
               immun stops it, schwaeche doubles it
    states     a foe's hit may cause one of its zustaende: the hero saves with d20 + Konstitution (Weisheit for the mind)
               against RETTUNG + a quarter of the foe's level; failed, the state lasts its runden turns and works by its
               wirkung (ZUSTAND_WIRKUNG); all end with the fight
    bosses     a foe with boss: more life per hero (BOSS_LEBEN), a second phase at half life (+BOSS_PHASE to hit, once
               a log line), two attacks a turn, its find one rarity better (dungeon.give_loot „boss“)

rd["kampf"] = {"gegner": [{k, id, name, zeichen, leben, max, rk, angriff, schaden, plus, wuerfel, ep, aus, art, resistenz,
               immun, schwaeche, zustaende, boss, phase}], "seit": zug, "budget": n, "gefahr": "leicht"|"mittel"|"schwer"};
hero states in h["zust"] = [{"id", "bis": zug}]; dungeon.py owns the round and calls in.
"""
import random

# D&D 5e: experience of a medium encounter per character by its level (1..20)
# the experience of a medium encounter per hero and level: levels 1 to 10 measured with the balance bench (dungeon_pruefstand,
# Dominik 2026-10-24 Idee 5) so a group wins 70 to 90 per cent at „mittel“; beyond the heroes' top level the D&D table
BUDGET = (83, 121, 291, 342, 408, 532, 802, 907, 600, 648, 1600, 2000, 2200, 2500, 2800, 3200, 3900, 4200, 4900, 5700)
REGLER = 25                # the game master's dial (Idee 6): the next encounters at most this many per cent easier or harder
REGLER_HOCH = 10           # after a fight won with less than REGLER_LEICHT of the group's life lost: this much harder
REGLER_LEICHT = 0.25
REGLER_RUNTER = 15         # after a fight with a hero down, lost or fled from: this much easier
GRUPPE = (0.8, 0.35)       # the budget times 0.8 for one hero and 0.35 more for each further one (more heroes hit more often)
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
EIGENSCHAFTEN = ("leicht", "finesse", "reichweite", "wurf", "schwer", "vielseitig")
SCHADEN_ARTEN = ("hieb", "stich", "wucht", "feuer", "kaelte", "blitz", "saeure", "gift", "nekrotisch", "strahlend", "psychisch",
                 "donner", "energie")
ART_NAME = {"hieb": ("Hieb", "slashing"), "stich": ("Stich", "piercing"), "wucht": ("Wucht", "bludgeoning"), "feuer": ("Feuer", "fire"),
            "kaelte": ("Kälte", "cold"), "blitz": ("Blitz", "lightning"), "saeure": ("Säure", "acid"), "gift": ("Gift", "poison"),
            "nekrotisch": ("nekrotisch", "necrotic"), "strahlend": ("strahlend", "radiant"), "psychisch": ("psychisch", "psychic"),
            "donner": ("Donner", "thunder"), "energie": ("Energie", "force")}
ART_ZEICHEN = {"hieb": "🗡️", "stich": "🏹", "wucht": "🔨", "feuer": "🔥", "kaelte": "❄️", "blitz": "⚡", "saeure": "🧪", "gift": "🐍",
               "nekrotisch": "🌑", "strahlend": "☀️", "psychisch": "🧠", "donner": "💥", "energie": "✨"}   # the bestiary's symbols
EIGENSCHAFT_REGEL = {                       # what each property does at the table, as the item's line says it
    "leicht": ("leicht: kritisch schon ab 19", "light: critical from 19"),
    "finesse": ("Finesse: trifft mit Stärke oder Geschick, dem besseren", "finesse: hits with Strength or Dexterity, the better"),
    "reichweite": ("Reichweite: wen du triffst, greift dich mit Nachteil an", "reach: whoever you hit attacks you at a disadvantage"),
    "wurf": ("Wurf: geworfen mit dem besseren von Stärke und Geschick", "thrown: thrown with the better of Strength and Dexterity"),
    "schwer": ("schwer: unter Stärke 13 mit Nachteil", "heavy: at a disadvantage below Strength 13"),
    "vielseitig": ("vielseitig: mit freier zweiter Hand ein größerer Würfel", "versatile: a bigger die with the off hand free")}
SCHWER_STAERKE = 13        # a heavy weapon wants this Stärke, else its attack is at a disadvantage
LEICHT_KRIT = 19           # a light weapon is critical from this natural roll
WURF_WORTE = ("wirf", "werf", "wurf", "schleuder", "throw", "hurl", "toss")   # an action that throws (eigenschaft wurf)
RETTUNG = 10               # a state's save: this + a quarter of the foe's level
GEIST = ("bezaubert", "veraengstigt")   # states of the mind: saved with Weisheit, the rest with Konstitution
BRENNT = 4                 # schaden_pro_zug: 1W4 at each of the foes' turns
BOSS_LEBEN = 0.5           # a boss: its life times 1 + this per hero beyond the first
BOSS_PHASE = 2             # a boss at half life: this much more to hit, once

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
          "Gegner ohne Wurf fallen. wirkt sagt, ob der Gegner den Schaden halbiert (resistenz), gar nicht nimmt (immun) "
          "oder doppelt (schwaeche); zustand mit gerettet false heißt, die Figur leidet jetzt daran (erzähle es), "
          "kann_nicht, dass sie wegen eines Zustands nicht angreifen konnte. Ein Gegner mit boss und phase 2 wird "
          "jetzt gefährlicher. Ergeben sich die Gegner oder flieht die Gruppe, setze kampf_ende.",
    "en": "There is a fight (facts kampf). The panel rolls every attack: when a character attacks a foe in its action, "
          "give it a check with ziel = the foe's name exactly as in kampf and the value it attacks with; schwer does "
          "not count then. Tell exactly what the rolls in proben and gegner_zuege say: who hits, who misses, who falls "
          "or flees. Report no damage of the fight in folgen and let no foe fall without a roll. wirkt says whether the "
          "foe halves the damage (resistenz), takes none (immun) or double (schwaeche); zustand with gerettet false means "
          "the character now suffers it (tell it), kann_nicht that a state kept it from attacking. A foe with boss "
          "and phase 2 grows more dangerous now. When the foes give up or the group flees, set kampf_ende."}


def prof(stufe):
    """The proficiency bonus of D&D by level."""
    return 2 + (max(1, int(stufe)) - 1) // 4


WIRKUNG = ("schaden", "lebensraub", "glueck", "wachsam")   # what an item's effect does by a fixed rule (Gegenstands-Punkt 3)
WIRKUNG_W = 6             # „schaden“: +1d6 of its kind on a hit (twice on a critical)
RAUB_W = 4                # „lebensraub“: the hero heals 1d4 on a hit


def effects(dm, r, h, wirkung, it=None):
    """The known effects with this wirkung the hero wears (or of the one item it); an unknown item counts only by its base."""
    its = [it] if it else dm.worn(h)
    return [e for x in its for e in dm.item_effects(r, x) if e.get("wirkung") == wirkung]


def lucky(dm, r, h, w, rng):
    """„glueck“: a natural 1 is rolled again once. Returns (the roll, rolled again)."""
    if w == 1 and effects(dm, r, h, "glueck"):
        return rng.randint(1, 20), True
    return w, False


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
    return 10 + 2 * body + rest + g + len(effects(dm, r, h, "wachsam"))


def _mal(n):
    return next(m for k, m in MAL if n >= k)


def budget(dm, r, rd, held):
    """The experience a medium encounter of this group may have: BUDGET per hero, times GRUPPE for the group's size,
    half at the children's table."""
    b = sum(BUDGET[min(len(BUDGET), max(1, h["stufe"])) - 1] for h in held) * (GRUPPE[0] + GRUPPE[1] * (len(held) - 1))
    return int(b * (KIND if dm.kids(r, rd) else 1) * (1 + dial(rd) / 100))


def dial_on(rd):
    """The game master's dial works for this round: „Spielleiter-Regler“ allowed for its host."""
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonregler", rd["owner"])


def dial(rd):
    """The dial's per cent (-REGLER..REGLER) for the next encounter, 0 while it is off."""
    return max(-REGLER, min(REGLER, int(rd.get("regler", 0)))) if dial_on(rd) else 0


def turn_dial(dm, r, rd):
    """After a fight, once its last hits are in the heroes' life (dungeon.apply after consequences), by fixed numbers: won with little life lost → REGLER_HOCH harder, a hero down, a lost fight or
    a flight → REGLER_RUNTER easier, else as it was; at most ±REGLER, at the children's table never above 0. The
    host can hold it (rd["regler_fest"]). Returns the step (+, - or 0)."""
    k = rd.pop("kampf_aus", None)
    if not k or not dial_on(rd):
        return 0
    held, why = [p["held"] for _, p in dm.seated(rd)], k["why"]
    if rd.get("regler_fest"):
        print("dungeon: regler | fest", flush=True)
        return 0
    voll = k.get("leben0") or 0
    lost = 1 - sum(max(0, h["leben"]) for h in held) / voll if voll else 0
    down = any(dm.zustand(h) for h in held)
    step = -REGLER_RUNTER if down or why == "flucht" else REGLER_HOCH if lost < REGLER_LEICHT else 0
    top = 0 if dm.kids(r, rd) else REGLER
    was = int(rd.get("regler", 0))
    rd["regler"] = max(-REGLER, min(top, was + step))
    step = rd["regler"] - was
    if step > 0:
        dm._day.bump("regler_hoch")
        print(f"dungeon: regler | hoch | {rd['regler']}", flush=True)
    elif step < 0:
        dm._day.bump("regler_runter")
        print(f"dungeon: regler | runter | {rd['regler']}", flush=True)
    else:
        print(f"dungeon: regler | gleich | {rd['regler']}", flush=True)
    return step


def plays_in(r, g, welt):
    """Whether a foe of the bestiary meets heroes in the world: „alle“ everywhere, else its worlds; a world no foe names
    for itself (the own world, a new one of the admin) takes the foes of dungeon_legenden.SONST (Bestiarium-Punkt 3)."""
    from dungeon_legenden import SONST
    w = welt if any(welt in x["welten"] for x in r.get("gegner") or []) else SONST
    return "alle" in g["welten"] or w in g["welten"]


def _foes(dm, r, rd):
    welt = rd.get("welt", "")
    return [g for g in r.get("gegner") or [] if plays_in(r, g, welt)]


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


def lineup(wahl, li, n_held):
    """The foes of an encounter with their bestiary values, numbered when several of a kind come; a boss has more life
    the more heroes stand against it (start, and the balance bench dungeon_pruefstand)."""
    gegner = []
    for g, n in wahl:
        for j in range(n):
            gegner.append({"k": f"g{len(gegner) + 1}", "id": g["id"], "name": g["name"][li] + (f" {j + 1}" if n > 1 else ""),
                           "zeichen": g.get("zeichen", ""), "leben": g["leben"], "max": g["leben"], "rk": g["ruestung"],
                           "angriff": g["angriff"], "schaden": g["schaden"], "plus": g.get("schaden_plus", 0),
                           "wuerfel": g.get("anzahl_wuerfel", 1), "ep": g["ep"], "aus": "", "art": g.get("schaden_art", ""),
                           **{x: list(g.get(x) or []) for x in ("resistenz", "immun", "schwaeche", "zustaende")},
                           "boss": bool(g.get("boss")), "phase": 1})
            if g.get("boss"):
                gegner[-1]["leben"] = gegner[-1]["max"] = int(g["leben"] * (1 + BOSS_LEBEN * max(0, n_held - 1)))
    return gegner


def danger(adj, b):
    """The danger word of an encounter: its adjusted experience against the medium budget (GEFAHR)."""
    return next(n for m, n in GEFAHR if adj / max(1, b) <= m)


def start(dm, r, rd, held, wahl, li):
    """An encounter into the round: the foes with their bestiary values, numbered when several of a kind come."""
    if not wahl:
        return None
    gegner = lineup(wahl, li, len(held))
    b = budget(dm, r, rd, held)
    rd["kampf"] = {"gegner": gegner, "seit": rd.get("zug", 0), "budget": b, "gefahr": danger(adjusted(gegner), b),
                   "leben0": sum(max(0, h["leben"]) for h in held)}
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
        eig = ()
        if spell and spell.get("segen"):
            wert, wuerfel, plus, mit = spell["segen"]["wert"], ZAUBER_W[min(5, spell.get("grad", 0))], spell["segen"]["bonus"], spell["name"][li].split(": ", 1)[-1]
            art = spell.get("schaden_art") or "energie"
        elif wp:
            c = dm._c(r, wp)
            wert, wuerfel, plus, mit = c["wert"], c["schaden"], 0 if wp.get("u") else wp.get("bonus", 0), wp.get("eigen") or c["name"][li]
            art, eig = c.get("schaden_art", ""), tuple(c.get("eigenschaften") or ())
        else:
            wert, wuerfel, plus, mit, art = "staerke", FAUST, 0, ("Fäuste" if not li else "fists"), "wucht"
        wirft = "wurf" in eig and any(x in str(a.get("text", "")).lower() for x in WURF_WORTE)
        if "finesse" in eig or wirft:            # the better of Stärke and Geschick
            wert = max(("staerke", "geschick"), key=lambda x: (dm.total(r, h, x), x == wert))
        if "vielseitig" in eig and not (h.get("an") or {}).get("nebenhand"):
            wuerfel += 2                          # both hands on it
        vt = p.get("vt") or ""
        if "schwer" in eig and h["werte"].get("staerke", 10) < SCHWER_STAERKE:
            vt = "" if vt == "vorteil" else "nachteil"
        vt = _state_vt(r, h, vt, "angriff")
        if blocked(r, h):                     # a state that takes the turn (gelähmt, betäubt …): no attack
            out.append({"pid": p["pid"], "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": mit, "wert": wert, "w": 0,
                        "ws": [], "vt": "", "bonus": 0, "gesamt": 0, "rk": g["rk"], "treffer": False, "krit": False, "schaden": 0,
                        "faellt": False, "kann_nicht": blocked(r, h)})
            continue
        bonus = dm.total(r, h, wert) + prof(h["stufe"]) + (plus if spell else 0)
        mut = False
        gl = False
        for _ in range(2):
            ws = [rng.randint(1, 20) for _ in range(2 if vt else 1)]
            w = max(ws) if vt == "vorteil" else min(ws)
            if not gl:
                w, gl = lucky(dm, r, h, w, rng)
            krit = w >= (LEICHT_KRIT if "leicht" in eig else 20)
            hit = krit or (w != 1 and w + bonus >= g["rk"])
            if krit or mut or not dm.mut.wants(rd, p["pid"]):
                break
            dm.mut.spend(rd, p["pid"])            # Heldenmut (Idee 8): a hit becomes critical, a miss is rolled again once
            mut = True
            if hit:
                krit = True
                break
        n, wirkt, extra, raub = 0, "", [], 0
        if hit:
            n = max(1, _dice(rng, 2 if krit else 1, wuerfel) + dm.mod(h["werte"].get(wert, 10)) + (0 if spell else plus))
            n, wirkt = against(g, art, n)
            for e in effects(dm, r, h, "schaden", wp) if wp and not spell else ():   # a burning blade: its own kind, its own resistances
                m, _ = against(g, e["art"], _dice(rng, 2 if krit else 1, WIRKUNG_W))
                extra.append({"art": e["art"], "schaden": m})
                n += m
            if wp and not spell and effects(dm, r, h, "lebensraub", wp):
                raub = rng.randint(1, RAUB_W)
            life[g["k"]] -= n
        out.append({"pid": p["pid"], "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": mit, "wert": wert, "w": w,
                    "ws": ws, "vt": vt, "bonus": bonus, "gesamt": w + bonus, "rk": g["rk"], "treffer": hit, "krit": krit,
                    "schaden": n, "faellt": hit and life[g["k"]] <= 0, "art": art, "wirkt": wirkt,
                    "eig": [x for x in eig if x != "wurf" or wirft], **({"mut": True} if mut else {}),
                    **({"extra": extra} if extra else {}), **({"raub": raub} if raub else {}), **({"glueck": True} if gl else {})})
    return rest, out


def against(g, art, n):
    """A hit's damage after the foe's resistances: (damage, "immun"|"resistenz"|"schwaeche"|"")."""
    if art and art in g.get("immun", ()):
        return 0, "immun"
    if art and art in g.get("resistenz", ()):
        return max(1, n // 2), "resistenz"
    if art and art in g.get("schwaeche", ()):
        return n * 2, "schwaeche"
    return n, ""


def _states(r, h):
    """A hero's states in force: their catalog entries."""
    by = {z["id"]: z for z in r.get("zustaende") or []}
    return [by[x["id"]] for x in h.get("zust") or [] if x.get("id") in by]


def has(r, h, wirkung):
    return any(wirkung in z["wirkung"] for z in _states(r, h))


def blocked(r, h):
    """The state that takes a hero's turn (kein_zug), "" for none."""
    return next((z["id"] for z in _states(r, h) if "kein_zug" in z["wirkung"]), "")


def _state_vt(r, h, vt, wofuer):
    """Advantage or disadvantage by the hero's states: wofuer "angriff" (own attack), "gegen" (a foe's attack on it),
    "probe" (a check); for "gegen" the advantage is the foe's. Both cancel to a plain roll, like the burden (dungeon.roll)."""
    up_, down = {"angriff": ("vorteil_angriff", "nachteil_angriff"), "gegen": ("vorteil_gegen", "nachteil_gegen"),
                 "probe": ("", "nachteil_proben")}[wofuer]
    plus, minus = up_ and has(r, h, up_), has(r, h, down)
    if plus and not minus:
        return "" if vt == "nachteil" else "vorteil"
    if minus and not plus:
        return "" if vt == "vorteil" else "nachteil"
    return vt


def foes_turn(dm, r, rd, hits, rng=None):
    """Every foe still up after the heroes' attacks attacks one hero (a boss twice): the last who hit it, else one
    standing hero by the seed. A hit may cause one of the foe's states (save), a state that burns or bleeds costs
    BRENNT at each turn. [{k, gegner, pid, name, w, ws, vt, gesamt, rk, treffer, schaden, art, zustand, rettung}]."""
    rng = rng or random
    if not rd.get("kampf"):
        return []
    down = {x["ziel"] for x in hits if x["faellt"]}
    standing = [(pid, p["held"]) for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    if not standing:
        return []
    out = []
    zs = {z["id"]: z for z in r.get("zustaende") or []}
    for g in up(rd):
        if g["k"] in down:
            continue
        for zug in range(2 if g.get("boss") else 1):
            by = [x["pid"] for x in hits if x["ziel"] == g["k"] and x["treffer"]]
            pid, h = (next(((q, hh) for q, hh in standing if by and q == by[-1]), None) if not zug else None) or standing[rng.randrange(len(standing))]
            vt = _state_vt(r, h, "", "gegen")
            if any(x["ziel"] == g["k"] and x["pid"] == pid and x["treffer"] and "reichweite" in x.get("eig", ()) for x in hits):
                vt = "" if vt == "vorteil" else "nachteil"    # kept at a distance by a reach weapon
            ws = [rng.randint(1, 20) for _ in range(2 if vt else 1)]
            w = max(ws) if vt == "vorteil" else min(ws)
            ac = rk(dm, r, h)
            plus = BOSS_PHASE if g.get("phase") == 2 else 0
            hit = w == 20 or (w != 1 and w + g["angriff"] + plus >= ac)
            n = max(1, _dice(rng, g["wuerfel"] * (2 if w == 20 else 1), g["schaden"]) + g["plus"]) if hit else 0
            x = {"k": g["k"], "gegner": g["name"], "pid": pid, "name": h["name"], "w": w, "ws": ws, "vt": vt, "bonus": g["angriff"] + plus,
                 "gesamt": w + g["angriff"] + plus, "rk": ac, "treffer": hit, "krit": w == 20, "schaden": n, "art": g.get("art", "")}
            frei = [z for z in g.get("zustaende") or [] if z in zs and z not in {y["id"] for y in h.get("zust") or []}]
            if hit and frei:                     # the hit may cause a state: the hero saves
                z = frei[rng.randrange(len(frei))]
                wert = "weisheit" if z in GEIST else "konstitution"
                dc = RETTUNG + int(dm._by(r, "gegner").get(g["id"], {}).get("stufe", 0) // 4)
                rw = rng.randint(1, 20)
                x["rettung"] = {"zustand": z, "wert": wert, "w": rw, "gesamt": rw + dm.total(r, h, wert), "gegen": dc,
                                "ok": rw + dm.total(r, h, wert) >= dc}
            out.append(x)
    for pid, h in standing:                       # burning, bleeding: every turn of the foes
        for z in _states(r, h):
            if "schaden_pro_zug" in z["wirkung"]:
                out.append({"k": "", "zustand_schaden": z["id"], "pid": pid, "name": h["name"], "schaden": rng.randint(1, BRENNT)})
    return out


def zug_facts(r, rd, x):
    """One of the foes' turn for the model: an attack (with a state's save), or a state's damage."""
    if x.get("zustand_schaden"):
        return {"zustand": _zname(r, rd, x["zustand_schaden"]), "trifft": x["name"], "schaden": x["schaden"]}
    rw = x.get("rettung")
    return {"gegner": x["gegner"], "greift_an": x["name"], "trifft": x["treffer"], "schaden": x["schaden"],
            **({"zustand": _zname(r, rd, rw["zustand"]), "gerettet": rw["ok"]} if rw else {})}


def facts(dm, r, rd, held, li):
    """The fight for the model: every foe with its life, or the offer when there is none."""
    k = rd.get("kampf")
    if k:
        return {"kampf": {"gefahr": k["gefahr"], "gegner": [{"name": g["name"], "leben": f"{max(0, g['leben'])}/{g['max']}",
                                                              **({"aus": g["aus"]} if g["aus"] else {}),
                                                              **({"boss": True, "phase": g.get("phase", 1)} if g.get("boss") else {})}
                                                             for g in k["gegner"]]}}
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
    expire(dm, rd)
    for x in hits:
        g = by.get(x["ziel"])
        if not g or g["aus"]:
            continue
        if x.get("kann_nicht"):
            dm._log(rd, "angriff", pid=x["pid"], name=x["name"], gegner=g["name"], mit=x["mit"], kann_nicht=_zname(r, rd, x["kann_nicht"]),
                    treffer=False, schaden=0)
            print("dungeon: kampf | kann nicht", flush=True)
            continue
        dm._log(rd, "angriff", pid=x["pid"], name=x["name"], gegner=g["name"], mit=x["mit"], w=x["w"], ws=x["ws"], vt=x["vt"],
                bonus=x["bonus"], gesamt=x["gesamt"], rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"],
                sart=x.get("art", ""), wirkt=x.get("wirkt", ""), eig=x.get("eig", []), **{k: x[k] for k in ("mut", "extra", "raub", "glueck") if x.get(k)})
        dm._day.bump("treffer" if x["treffer"] else "daneben")
        held = (dict(dm.seated(rd)).get(x["pid"]) or {}).get("held")
        if x.get("raub") and held and not dm.zustand(held):     # life drain: the hero heals by the panel's die
            dm.heal(held, x["raub"])
            print("dungeon: kampf | lebensraub", flush=True)
        was = hurt(g, x["schaden"]) if x["treffer"] else ""
        if was == "besiegt":
            dm._log(rd, "gegner", gegner=g["name"], was="besiegt")
            dm._day.bump("besiegt")
        elif was == "phase2":
            dm._log(rd, "gegner", gegner=g["name"], was="phase2")
            print("dungeon: kampf | boss | phase2", flush=True)
    seats = dict(dm.seated(rd))
    for x in zuege:
        if x.get("zustand_schaden") and x["pid"] in seats and not dm.zustand(seats[x["pid"]]["held"]):
            dm._log(rd, "zustand", pid=x["pid"], name=x["name"], zustand=_zname(r, rd, x["zustand_schaden"]), schaden=x["schaden"])
            folgen.append({"pid": x["pid"], "art": "schaden", "zahl": x["schaden"], "gegner": _zname(r, rd, x["zustand_schaden"])})
            continue
        g = by.get(x["k"])
        if not g or g["aus"] or x["pid"] not in seats or dm.zustand(seats[x["pid"]]["held"]):
            continue
        dm._log(rd, "angriff", gegner=g["name"], pid=x["pid"], name=x["name"], w=x["w"], ws=x.get("ws", [x["w"]]), vt=x.get("vt", ""),
                bonus=x["bonus"], gesamt=x["gesamt"], rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"], von_gegner=True)
        if x["treffer"]:
            folgen.append({"pid": x["pid"], "art": "schaden", "zahl": x["schaden"], "gegner": g["name"]})
        rw = x.get("rettung")
        if rw:
            suffers(r, rd, seats[x["pid"]]["held"], rw)
            dm._log(rd, "rettung", pid=x["pid"], name=x["name"], gegner=g["name"], zustand=_zname(r, rd, rw["zustand"]), wert=rw["wert"],
                    w=rw["w"], gesamt=rw["gesamt"], gegen=rw["gegen"], ok=rw["ok"])
            if rw["ok"]:
                print("dungeon: kampf | rettung | ok", flush=True)
            else:
                print("dungeon: kampf | rettung | zustand", flush=True)
    for g in up(rd):
        if flees(g, rng):
            dm._log(rd, "gegner", gegner=g["name"], was="aufgegeben" if dm.kids(r, rd) else "geflohen")
            dm._day.bump("geflohen")
    if not up(rd) or ende in ENDE:
        end(dm, r, rd, ep, ende)
    return folgen


def hurt(g, n):
    """A hero's hit on a foe: its life down; "besiegt" at 0, "phase2" when a boss comes to half its life (its second
    phase), else ""."""
    g["leben"] = max(0, g["leben"] - n)
    if g["leben"] <= 0:
        g["aus"] = "besiegt"
        return "besiegt"
    if g.get("boss") and g.get("phase") == 1 and g["leben"] * 2 <= g["max"]:
        g["phase"] = 2
        return "phase2"
    return ""


def suffers(r, rd, h, rw):
    """A failed save puts its state on the hero for the state's turns (once)."""
    z = next((z for z in r.get("zustaende") or [] if z["id"] == rw["zustand"]), None)
    if z and not rw["ok"] and z["id"] not in {y["id"] for y in h.get("zust") or []}:
        h.setdefault("zust", []).append({"id": z["id"], "bis": rd.get("zug", 0) + z["runden"]})


def flees(g, rng):
    """A foe at a quarter of its life or less flees on a d20 of FLUCHT_W or less."""
    if 0 < g["leben"] * FLUCHT <= g["max"] and rng.randint(1, 20) <= FLUCHT_W:
        g["aus"] = "geflohen"
        return True
    return False


def _zname(r, rd, zid):
    z = next((z for z in r.get("zustaende") or [] if z["id"] == zid), None)
    return z["name"][1 if rd.get("lang") == "en" else 0] if z else zid


def expire(dm, rd, all_=False):
    """The heroes' states whose turns are over go (all of them when the fight ends)."""
    for _, p in dm.seated(rd):
        h = p["held"]
        if h.get("zust"):
            h["zust"] = [] if all_ else [x for x in h["zust"] if x.get("bis", 0) >= rd.get("zug", 0)]
            if not h["zust"]:
                h.pop("zust")


def end(dm, r, rd, ep, why=""):
    """The fight is over: the defeated foes' experience (half for the fled ones; Idee 7: all of the foes still up when
    it ends in peace in a turn with a check passed, k["geschafft"], dungeon.apply) divided by the living heroes into ep
    (pid -> number, apply gives it to the table), one find for the group, a line for the log. A won fight of a room
    of the map leaves rd["sieg"] = the room's tag for dungeon_karte (the way is free)."""
    k = rd.pop("kampf", None)
    if not k:
        return
    expire(dm, rd, all_=True)
    besiegt = [g for g in k["gegner"] if g["aus"] == "besiegt"]
    flohen = [g for g in k["gegner"] if g["aus"] == "geflohen"]
    frieden = [g for g in k["gegner"] if not g["aus"]] if why == "frieden" and k.get("geschafft") else []   # Idee 7
    alle = sum(g["ep"] for g in besiegt + frieden) + sum(g["ep"] // 2 for g in flohen)
    each = -(-alle // max(1, len(ep))) if ep else 0
    for pid in ep:
        ep[pid] += each
    if k.get("raum") and not why:
        rd["sieg"] = k["raum"]
        rd.pop("raum_gegner", None)
    dm._log(rd, "kampf", was=why or "sieg", besiegt=len(besiegt), geflohen=len(flohen), ep=each, boss=any(g.get("boss") for g in besiegt),
            frieden=len(frieden))
    rd["kampf_aus"] = {"leben0": k.get("leben0", 0), "why": why}      # for the dial, after the last hits are in (turn_dial)
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
                leben=max(0, g["leben"]), max=g["max"], aus=g["aus"], phase=g.get("phase", 1), bild=_picture(r, rd, g["id"], have)) for g in k["gegner"]]
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
            "zustaende": [{"name": z["name"][li], "info": z["info"][li]} for z in r.get("zustaende") or [] if z["id"] in (c.get("zustaende") or [])],
            # Kampf Teil 2: its damage kind, what hurts it more or less, a boss
            "art": ART_NAME[c["schaden_art"]][li] if c.get("schaden_art") in ART_NAME else "",
            **{x: [ART_NAME[a][li] for a in c.get(x) or [] if a in ART_NAME] for x in ("resistenz", "immun", "schwaeche")},
            "boss": bool(c.get("boss"))}


def for_live(rs):
    return {"kaempfe_laufen": sum(1 for v in rs if v.get("kampf")), "gegner_stehen": sum(len(up(v)) for v in rs)}
