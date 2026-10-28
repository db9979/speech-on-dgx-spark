"""KI-Dungeon-Master: Spielleiter gibt Dinge (Dominik 2026-10-28 „der admin soll die möglichkeit haben den karakteren
items zu geben (gegenstände gold runen etc.)“, „1a 2a 3a 4a 5a“).

The round's host gives a hero at the table something from the catalog, in the game master console under „Nur für
dich“ → „Geben“ (1a): only while the admin's switch dungeongeben (features.py, chat.dungeon_geben, off, 5a) is on
and the request comes from the admin: the panel's admin login or the host's own login as an admin profile (admin).
Never a guest, never the model. The panel checks everything by the game's own rules (3a):
    ding   an item of the catalog of the round's world (dungeon.in_world) at a rarity up to „episch“ (a fixed
           rarity stays), never a legend nor a quest thing (2a), into the bag only when it has room
    gold   GOLD_GEBEN at most at once, the hero's gold never above dungeon.GOLD_MAX
    rune   RUNEN_GEBEN at most at once, only while „Runen und Sockel“ is on, never above the rune bag's
           dungeon_runen.BEUTEL_MAX
    ep     at most up to the hero's next level (never more than one level at once, dungeon.gain as at the end)
At the table a fixed line „Der Spielleiter gibt Arvid: Langschwert.“ (log art "geben"), and the next narration
tells it as a find or a gift (4a: facts "spielleiter_gibt", task). Journal and day counters: fixed words and numbers.
"""
from common import DayCounter

KEY = "dungeongeben"
ARTEN = ("ding", "gold", "rune", "ep")
GOLD_GEBEN = 1000           # gold at once
RUNEN_GEBEN = 5             # runes of one kind at once
STAPEL_GEBEN = 5            # pieces of a stackable item at once (potions, arrows)
_day = DayCounter(ding=0, gold=0, rune=0, ep=0, abgelehnt=0)

AUFGABE = {"de": " Der Spielleiter hat in diesem Zug etwas gegeben (spielleiter_gibt): Erzähle es als Fund oder Geschenk in "
                 "der Szene, nenne es so, wie es dasteht, erfinde nichts dazu.",
           "en": " The game master gave something this turn (spielleiter_gibt): tell it as a find or a gift in the scene, "
                 "name it as it stands, invent nothing more."}


def on(rd):
    """The admin's switch for the round's host."""
    import features
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def admin(request, uid):
    """Whether this request comes from the admin: the panel's own admin login (the panel password, core.is_main_admin)
    or the host's own login as an admin profile (coadmin.session, role „admin“, not „Verwalter“). Never a guest."""
    import coadmin
    import core
    try:
        if core.is_main_admin(request, None):
            return True
        s = coadmin.session(request)
    except Exception:  # noqa: BLE001 - no session: no admin
        return False
    return bool(s) and s.get("role") == "admin" and s.get("id") == uid


def items(dm, r, rd):
    """The catalog items the host may give in this world: no legend, no quest thing, no fixed legendary rarity."""
    top = r["seltenheit"][-1]["id"]
    return [c for c in r["gegenstaende"] if dm.in_world(c, rd.get("welt")) and not c.get("quest") and c.get("seltenheit") != top]


def catalog(dm, r, rd, lang):
    """The things to choose from, once when the console's „Geben“ opens: [{id, name, art, s}] by kind and name (s: a
    fixed rarity, "" = the host picks one)."""
    li = 1 if lang == "en" else 0
    return sorted(({"id": c["id"], "name": c["name"][li], "art": c["art"], "s": c.get("seltenheit") or ""} for c in items(dm, r, rd)),
                  key=lambda x: (x["art"], x["name"].lower()))


def rarities(r):
    """The rarities up to „episch“ (2a: never a legend)."""
    ids = [x["id"] for x in r["seltenheit"]]
    return r["seltenheit"][:ids.index("episch") + 1] if "episch" in ids else r["seltenheit"][:-1]


def ep_max(r, h):
    """The experience at most to give now: up to the hero's next level, 0 at the top."""
    se = r["stufen_ep"]
    if h["stufe"] >= r["grenzen"]["stufe_max"] or h["stufe"] >= len(se):
        return 0
    return max(0, se[h["stufe"]] - h["ep"])


def view(dm, r, rd, uid, lang):
    """The console's „Geben“ for the host: the heroes with what each may still get, the rarities, the runes; None while
    off or for anyone else. The page shows it only in its admin mode, every request checks the admin again (admin);
    the things come once when it opens (catalog, GET …/geben)."""
    if rd.get("owner") != uid or rd.get("status") == "ende" or not on(rd):
        return None
    import dungeon_runen as runen
    li = 1 if lang == "en" else 0
    return {"helden": [{"pid": pid, "name": p["held"]["name"], "ep_max": ep_max(r, p["held"]), "gold": p["held"]["gold"],
                        "platz": dm.TASCHE - len(p["held"]["tasche"]), "runen": sum((p["held"].get("runen") or {}).values())}
                       for pid, p in dm.seated(rd) if not p["held"].get("tot")],
            "selten": [{"id": x["id"], "name": x["name"][li]} for x in rarities(r)],
            "runen": [{"id": x["id"], "name": x["name"][li]} for x in r.get("runen") or []] if runen.on(rd) and runen.wirkt() else [],
            "gold_max": GOLD_GEBEN, "runen_max": RUNEN_GEBEN, "stapel_max": STAPEL_GEBEN}


def give(dm, r, rid, rd, uid, b, rng=None):
    """{an: pid, art: ding|gold|rune|ep, id, s, n}: the host's gift by the game's rules; raises the game's refusals.
    Returns the fixed line (de, en). The request's admin check (admin) comes before, in dungeon.geben."""
    import dungeon_runen as runen
    if not on(rd):
        raise PermissionError("geben aus")
    if rd.get("owner") != uid or rd.get("status") == "ende":
        raise LookupError("gastgeber")
    art, p = b.get("art"), rd["plaetze"].get(b.get("an")) if isinstance(b.get("an"), str) else None
    h = p and p.get("held")
    n = b.get("n", 1)
    if art not in ARTEN or not h or h.get("tot") or not isinstance(n, int) or isinstance(n, bool) or n < 1:
        _day.bump("abgelehnt")
        print("dungeon: geben | nein", flush=True)
        raise ValueError("geben")
    li = 1 if rd.get("lang") == "en" else 0
    if art == "ding":
        c = next((x for x in items(dm, r, rd) if x["id"] == b.get("id")), None)
        s = (c.get("seltenheit") or b.get("s") or r["seltenheit"][0]["id"]) if c else None
        if not c or s not in {x["id"] for x in rarities(r)} or n > (STAPEL_GEBEN if c["art"] in dm.STAPEL_ARTEN else 1):
            _day.bump("abgelehnt")
            print("dungeon: geben | ding | nein", flush=True)
            raise ValueError("geben")
        it = dm.item(r, c["id"], s, rng=rng or dm.random)
        it.pop("u", None)                         # the game master knows what it gives
        if n > 1:
            it["n"] = n
        if not dm.room(r, h, [it]):
            _day.bump("abgelehnt")
            print("dungeon: geben | ding | voll", flush=True)
            raise ValueError("geben voll")
        dm.bag_add(r, h, it)
        ding = (f"{n} " if n > 1 else "") + dm.item_view(r, it, rd["lang"])["name"]
    elif art == "gold":
        if n > GOLD_GEBEN or h["gold"] >= dm.GOLD_MAX:
            _day.bump("abgelehnt")
            print("dungeon: geben | gold | nein", flush=True)
            raise ValueError("geben")
        n = min(n, dm.GOLD_MAX - h["gold"])
        h["gold"] += n
        ding = f"{n} Gold" if not li else f"{n} gold"
    elif art == "rune":
        x = runen.by(r).get(b.get("id"))
        if not x or not runen.on(rd) or not runen.wirkt() or n > RUNEN_GEBEN or sum((h.get("runen") or {}).values()) + n > runen.BEUTEL_MAX:
            _day.bump("abgelehnt")
            print("dungeon: geben | rune | nein", flush=True)
            raise ValueError("geben")
        rb = h.setdefault("runen", {})
        rb[x["id"]] = rb.get(x["id"], 0) + n
        ding = (f"{n} " if n > 1 else "") + f"{runen.word(rd.get('welt', ''), li, n > 1)} {x['name'][li]}"
    else:
        if n > ep_max(r, h):
            _day.bump("abgelehnt")
            print("dungeon: geben | ep | nein", flush=True)
            raise ValueError("geben ep")
        import time
        neu = dm.gain(r, h, n, f"{rid}:{time.strftime('%Y-%m-%d')}")      # one level an evening, as at the end
        ding = f"{n} EP"
        if neu:
            dm._log(rd, "stufe", pid=b["an"], name=h["name"], stufe=neu)
            dm._day.bump("stufen")
            print(f"dungeon: stufe | {neu}", flush=True)
            if runen.on(rd):
                runen.wake(dm, r, rd, h)
    dm._log(rd, "geben", pid=b["an"], name=h["name"], ding=ding)
    dm.keep_seat(p)
    _day.bump(art)
    print(f"dungeon: geben | {art} | ok", flush=True)
    return (f"Der Spielleiter gibt {h['name']}: {ding}.", f"The game master gives {h['name']}: {ding}.")


def facts(rd):
    """This turn's gifts for the narration (4a): [{wer, was}]."""
    return [{"wer": x["name"], "was": x["ding"]} for x in rd.get("log") or [] if x.get("art") == "geben" and x.get("n") == rd.get("zug")]


def task(rd, lang):
    return AUFGABE[lang] if facts(rd) else ""


def for_live():
    """Numbers only: things, gold, runes and experience given today, refused."""
    return _day.counts()
