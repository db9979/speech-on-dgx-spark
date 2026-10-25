"""KI-Dungeon-Master: Zufallsregeln des Gastgebers (Tabletop-Punkt 9 of 2026-10-25, Dominik „ich hätte gerne alle punkte
umgesetzt“, idea from AnyWorld, MIT, own code).

The host may give a round up to ZUFALL_MAX rules of their own: a name, a chance in percent, a trigger (every told turn,
a fight starting, a new place), an effect (damage, healing, gold won or lost, a hint for the narration) and whether one
roll counts for the whole group or one roll for each hero. The panel rolls a d100 when the trigger comes, applies the
effect by its own rules and writes every roll into the feed; the model only hears a hint as data (facts „zufall“),
never as an instruction, and never sees the rules. Only the host sees and sets them (dungeon_sicht: „zufall“).
The rules live in rd["zufall"] = [{"name", "prozent", "ausloeser", "wirkung", "zahl", "text", "wer"}].
Only while „Zufallsregeln“ is allowed for the round's host (features "dungeonzufall").
"""
import random

ZUFALL_MAX = 5
NAME_LEN = 30
TEXT_LEN = 120
AUSLOESER = {"zug": ("Jeder Zug", "Every turn"), "kampf": ("Ein Kampf beginnt", "A fight starts"),
             "ort": ("Ein neuer Ort", "A new place")}
WIRKUNGEN = {"schaden": ("Schaden", "Damage", (1, 6)), "heilung": ("Heilung", "Healing", (1, 6)),
             "gold": ("Gold dazu", "Gold won", (1, 50)), "verlust": ("Gold weg", "Gold lost", (1, 50)),
             "hinweis": ("Hinweis an die Erzählung", "Hint for the narration", (0, 0))}
WER = {"alle": ("Ein Wurf für alle", "One roll for all"), "je": ("Ein Wurf je Held", "One roll per hero")}


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonzufall", rd["owner"])


def clean(dm, b):
    """The host's rules from a request body by fixed limits; ValueError("zufall") for anything else."""
    rules = b.get("regeln")
    if not isinstance(rules, list) or len(rules) > ZUFALL_MAX:
        raise ValueError("zufall")
    out = []
    for x in rules:
        if not isinstance(x, dict):
            raise ValueError("zufall")
        name = dm.plain(x.get("name"), NAME_LEN)
        p, z = x.get("prozent"), x.get("zahl", 0)
        w = x.get("wirkung")
        if (not name or x.get("ausloeser") not in AUSLOESER or w not in WIRKUNGEN or x.get("wer") not in WER
                or not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= 100 or not isinstance(z, int) or isinstance(z, bool)):
            raise ValueError("zufall")
        lo, hi = WIRKUNGEN[w][2]
        text = dm.plain(x.get("text"), TEXT_LEN) if w == "hinweis" else ""
        if w == "hinweis" and len(text) < 5 or w != "hinweis" and not lo <= z <= hi:
            raise ValueError("zufall")
        out.append({"name": name, "prozent": p, "ausloeser": x["ausloeser"], "wirkung": w, "zahl": z if w != "hinweis" else 0,
                    "text": text, "wer": x["wer"]})
    return out


def put(dm, rd, b):
    """The host replaces the round's rules (an empty list takes them all back)."""
    if not on(rd):
        raise PermissionError("zufall aus")
    rules = clean(dm, b)
    for x in rules:
        if dm.bad_words(dm.rules(), rd, x["name"] + " " + x["text"]):
            raise ValueError("wortliste")
    rd["zufall"] = rules
    print(f"dungeon: zufall | gesetzt | {len(rules)} regeln", flush=True)


def view(rd, host, lang):
    """The host's rules and the choices; every other seat nothing (dungeon_sicht.NUR_GASTGEBER)."""
    if not host or not on(rd):
        return None
    li = 1 if lang == "en" else 0
    return {"regeln": [dict(x) for x in rd.get("zufall") or []], "max": ZUFALL_MAX, "name_max": NAME_LEN, "text_max": TEXT_LEN,
            "ausloeser": [[k, v[li]] for k, v in AUSLOESER.items()], "wirkungen": [[k, v[li], v[2][0], v[2][1]] for k, v in WIRKUNGEN.items()],
            "wer": [[k, v[li]] for k, v in WER.items()]}


def roll(dm, r, rd, trigger, rng=None):
    """The rules of this trigger rolled (d100, a hit at or below the chance) and their effects applied by the panel's
    rules; every roll a line in the feed. Returns the hints of the hits for the narration's data."""
    if not on(rd) or not rd.get("zufall"):
        return []
    rng = rng or random
    heroes = [(pid, p) for pid, p in dm.seated(rd) if not p["held"].get("tot")]
    hints = []
    for x in rd["zufall"]:
        if x["ausloeser"] != trigger or not heroes:
            continue
        groups = [heroes] if x["wer"] == "alle" else [[h] for h in heroes]
        for g in groups:
            w = rng.randint(1, 100)
            hit = w <= x["prozent"]
            wer = "" if x["wer"] == "alle" else g[0][1]["held"]["name"]
            dm._log(rd, "zufall", regel=x["name"], w=w, prozent=x["prozent"], treffer=hit, wirkung=x["wirkung"], zahl=x["zahl"],
                    **({"name": wer, "pid": g[0][0]} if wer else {}))
            dm._day.bump("zufall_treffer" if hit else "zufall_daneben")
            print(f"dungeon: zufall | {trigger} | {'treffer' if hit else 'daneben'}", flush=True)
            if not hit:
                continue
            if x["wirkung"] == "hinweis":
                hints.append({"regel": x["name"], "hinweis": x["text"]})
                continue
            for pid, p in g:
                h = p["held"]
                if x["wirkung"] in ("schaden", "heilung"):
                    dm.consequences(r, rd, [{"pid": pid, "art": x["wirkung"], "zahl": x["zahl"]}], dict(dm.seated(rd)))
                elif x["wirkung"] == "gold":
                    h["gold"] = min(dm.GOLD_MAX, h["gold"] + x["zahl"])
                else:
                    h["gold"] = max(0, h["gold"] - x["zahl"])
    return hints


def facts(hints):
    """The hints of this turn's hits for the model, as data (facts „zufall“), each with its markers broken up."""
    import textnorm
    return {"zufall": [{"regel": textnorm.defuse(h["regel"]), "hinweis": textnorm.defuse(h["hinweis"])} for h in hints]} if hints else {}


def for_live(rs):
    return {"zufall_regeln": sum(len(v.get("zufall") or []) for v in rs)}
