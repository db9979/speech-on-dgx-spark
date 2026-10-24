"""Gleichgewicht of the Dungeon Master's catalog (Dominik 2026-10-24 „prüfung … ob es overpowerd ist“, „1-5“, „zu stark
nur hinweis“): fixed tables, never the model. Each foe and item gets a mark and one sentence why:

- Foes: what a foe of its level usually has (life, armour, attack bonus, damage per round), a smooth table fitted once to
  the 142 SRD foes of dungeon_srd.json (their medians per level). Defence = life against the usual life, a point of
  armour more or less counts a tenth; attack the same with damage and attack bonus. The mark is the mean of both.
- Items: a budget per rarity (gewöhnlich 0 … legendär 4; an item without a fixed rarity counts as gewöhnlich, the dice
  give it its bonus later): weapon damage, armour, healing, a blessing's bonus × turns, a spell's grade for its rarity,
  and a price below the rarity's floor.

Marks: "schwach" (only foes, under half), "ok", "stark" (over budget), "zu_stark" (over budget by more than a quarter, a
grade by two). „Zu stark“ is only a hint: saving never stops at it (the hard limits stay in dungeon.check_rules).
"""

MARKEN = ("schwach", "ok", "stark", "zu_stark")
NAMEN = {"schwach": ("schwach", "weak"), "ok": ("ausgewogen", "balanced"), "stark": ("stark", "strong"),
         "zu_stark": ("zu stark", "too strong")}
RANG = {"gewoehnlich": 0, "selten": 1, "rar": 2, "episch": 3, "legendaer": 4}
PREIS_AB = (0, 50, 200, 500, 1500)      # the least price a fixed rarity should cost; cheaper reads „stark“


# ---------------------------------------------------------------- foes
def usual(stufe):
    """(life, armour, attack bonus, damage per round) a foe of this level usually has (fitted to the SRD foes)."""
    s = max(0.125, float(stufe))
    return 15 + 17 * s, 12.5 + 0.45 * s, 3.5 + 0.65 * s, 4 + 2.2 * s


def per_round(g):
    """The mean damage of one attack: dice × (sides + 1) / 2 + plus."""
    return int(g.get("anzahl_wuerfel") or 1) * (int(g.get("schaden") or 0) + 1) / 2 + int(g.get("schaden_plus") or 0)


def _mark(score):
    return "zu_stark" if score > 1.6 else "stark" if score > 1.3 else "schwach" if score < 0.5 else "ok"


def foe(g, lang="de"):
    """{"marke", "name", "grund", "wert"} for one foe of the catalog."""
    en = lang == "en"
    hp, ac, atk, dpr = usual(g.get("stufe", 1))
    d = per_round(g)
    defe = g.get("leben", 0) / hp * (1 + 0.1 * (g.get("ruestung", 0) - ac))
    off = d / dpr * (1 + 0.1 * (g.get("angriff", 0) - atk))
    score = (defe + off) / 2
    m = _mark(score)
    lv = _lvl(g.get("stufe", 1))
    if off >= defe:
        grund = (f"Schaden {d:g} pro Runde mit +{g.get('angriff', 0)}, üblich für Stufe {lv} sind etwa {dpr:.0f} mit +{atk:.0f}.",
                 f"Damage {d:g} per round at +{g.get('angriff', 0)}, usual for level {lv} is about {dpr:.0f} at +{atk:.0f}.")
    else:
        grund = (f"Leben {g.get('leben', 0)} und Rüstung {g.get('ruestung', 0)}, üblich für Stufe {lv} sind etwa {hp:.0f} und {ac:.0f}.",
                 f"Life {g.get('leben', 0)} and armour {g.get('ruestung', 0)}, usual for level {lv} is about {hp:.0f} and {ac:.0f}.")
    return {"marke": m, "name": NAMEN[m][en], "grund": grund[en], "wert": round(score, 2)}


def _lvl(s):
    return {0.125: "⅛", 0.25: "¼", 0.5: "½"}.get(s, f"{s:g}")


# ---------------------------------------------------------------- items
def item(x, lang="de"):
    """{"marke", "name", "grund", "wert"} for one item of the catalog: the worst of its parts."""
    en = lang == "en"
    rank = RANG.get(x.get("seltenheit"), 0)
    out = []                                            # (ratio, mark, (de, en))

    def over(v, limit, what):
        r = v / limit if limit else 0
        if r > 1:
            out.append((r, "zu_stark" if r > 1.25 else "stark",
                        (f"{what[0]} {v:g}, für diese Seltenheit sind höchstens {limit:g} üblich.",
                         f"{what[1]} {v:g}, for this rarity at most {limit:g} is usual.")))
    if x.get("art") == "waffe":
        over(x.get("schaden", 0), 12 + 2 * rank, ("Schadenswürfel W", "Damage die d"))
    if x.get("art") == "ruestung":
        over(x.get("schutz", 0), 4 + rank // 2, ("Schutz", "Protection"))
    if x.get("heilung"):
        limit = 6 + 5 * int(x.get("grad") or 0) if x.get("art") == "zauber" else 12 + 4 * rank
        over(x["heilung"], limit, ("Heilung", "Healing"))
    seg = x.get("segen")
    if isinstance(seg, dict):
        over(seg.get("bonus", 0) * max(1, seg.get("zuege", 1)), 6 + 3 * rank, ("Segen (Bonus × Züge)", "Blessing (bonus × turns)"))
    if x.get("art") == "zauber" and x.get("seltenheit") in RANG:
        g = int(x.get("grad") or 0)
        if g > rank + 1:
            out.append((g - rank, "zu_stark" if g - rank > 2 else "stark",
                        (f"Zauber Grad {g}, für diese Seltenheit ist Grad {rank + 1} üblich.",
                         f"Spell grade {g}, for this rarity grade {rank + 1} is usual.")))
    if x.get("seltenheit") in RANG and "preis" in x and x["preis"] < PREIS_AB[rank]:
        out.append((1.01, "stark", (f"Preis {x['preis']}, diese Seltenheit kostet sonst ab {PREIS_AB[rank]}.",
                                    f"Price {x['preis']}, this rarity costs {PREIS_AB[rank]} or more.")))
    if not out:
        return {"marke": "ok", "name": NAMEN["ok"][en], "grund": "", "wert": 1.0}
    r, m, g = max(out, key=lambda o: (MARKEN.index(o[1]), o[0]))
    return {"marke": m, "name": NAMEN[m][en], "grund": g[en], "wert": round(r, 2)}


def summary(r, lang="de"):
    """{"gegner": {id: mark}, "gegenstaende": {id: mark}} over the merged catalog (the admin's rules page)."""
    return {"gegner": {g["id"]: foe(g, lang) for g in r.get("gegner") or []},
            "gegenstaende": {x["id"]: item(x, lang) for x in r.get("gegenstaende") or []}}
