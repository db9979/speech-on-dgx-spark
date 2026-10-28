"""KI-Dungeon-Master: the admin's rules page as its own tab „Regeln“ (Dominik 2026-10-24 „die regel seite sollte für den
admin hier sein“, „das besarium zu sehen zu bearbeten gegenstände etc.“, „alle punkte umsetzten“). Builds on the game
(dungeon.py: rules, own rules, check_rules), the pictures (dungeon_dingbild.py) and the balance (dungeon_balance.py).

Per part of the catalog (TEILE) a list of rows (picture, name, one line of values, where it comes from, the balance mark)
and the merged entries for the detail. The admin changes one entry at a time: „Ändern“ writes the whole entry with its
id into the own rules, „Ausblenden“ writes {"id", "aus": true}, „Zurück auf mitgeliefert“ takes the own entry out.
Every change passes dungeon.check_rules like the JSON editor (a refused one comes back with its errors); „zu stark“
is only a hint (Dominik „zu stark nur hinweis“). „Nochmal malen“ paints a candidate next to the picture in use, the
admin keeps the new or the old one.

    GET  /api/admin/dungeon/katalog/{teil}         rows and entries of one part
    POST /api/admin/dungeon/katalog/{teil}         {"was": "setzen"|"aus"|"zurueck", "id", "eintrag"?}
    POST /api/admin/dungeon/katalog/{teil}/bild    {"id", "was": "malen"|"neu"|"alt"}
    GET  /api/admin/dungeon/bild/{name}            a catalog picture or a candidate (admin only); ?klein=1 the small copy

Journal lines „dungeon: regelseite | …“ with fixed words and numbers only.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_balance as balance
import dungeon_dingbild as dingbild
import dungeon_kampf as kampf
import dungeon_personen as personen
import dungeon_runen as runen
import dungeon_stimmen as stimmen
import guard
from common import write_json
from core import app_version, auth, json_body

router = APIRouter()
TEILE = ("gegenstaende", "gegner", "klassen", "voelker", "welten", "toene", "zustaende", "hintergruende", "tabellen",
         # Dominik 2026-10-28 „die runen sehe ich die auch unter den regeln wie alles andere?“, „fehlt sonst noch etwas“
         "runen", "runenwoerter", "effekte", "ortsarten", "raeume", "fallen", "raetsel", "begegnungen", "stillstand")
ZAHLEN = "zahlen"              # the fixed numbers of the rules, only to look at (changed in „Für Fortgeschrittene (JSON)“)
ALLE = TEILE + ("personen", ZAHLEN)   # the people of the catalog (dungeon_personen, Personen-Katalog 1) beside the parts of the rules
ZEICHEN_TEIL = {"runen": "ᚱ", "runenwoerter": "ᛟ", "effekte": "✨", "raetsel": "❓", "begegnungen": "👣", "stillstand": "⏳"}   # a row's sign
NAME_KURZ = 48                 # an entry without a name (an effect, a stall event) is named by its sentence's start
ORT_RW = {"waffe": ("Waffe", "weapon"), "koerper": ("Körperrüstung", "body armour"), "nebenhand": ("Schild", "shield"), "kopf": ("Kopf", "head")}
RAUM_ART = {"eingang": ("Eingang", "Entrance"), "gang": ("Gang", "Passage"), "kammer": ("Kammer", "Chamber"), "falle": ("Falle", "Trap"),
            "raetsel": ("Rätsel", "Riddle"), "schatz": ("Schatz", "Treasure"), "waechter": ("Wächter", "Guardian"), "boss": ("Boss", "Boss"),
            "quelle": ("Quelle", "Spring"), "altar": ("Altar", "Altar")}
BEGEGNUNG_ART = {"nichts": ("nichts", "nothing"), "wetter": ("Wetter", "weather"), "hinweis": ("Hinweis", "clue"), "fund": ("Fund", "find"),
                 "gegner": ("Gegner", "foes"), "haendler": ("Händler", "merchant")}
WIRKUNG_ART = {"schaden": ("Zusatzschaden", "extra damage"), "lebensraub": ("Lebensraub", "life drain"), "glueck": ("Glück", "luck"),
               "wachsam": ("Wachsam", "watchful")}
SG_NAME = {"sehr_leicht": ("sehr leicht", "very easy"), "leicht": ("leicht", "easy"), "mittel": ("mittel", "medium"), "schwer": ("schwer", "hard"),
           "sehr_schwer": ("sehr schwer", "very hard"), "fast_unmoeglich": ("fast unmöglich", "nearly impossible")}
ANLASS = {"gegner": ("nach einem Kampf", "after a fight"), "truhe": ("Truhe", "chest"), "belohnung": ("Belohnung", "reward"), "boss": ("Boss", "boss")}
EP_NAME = {"probe": ("gelungene Probe", "check passed"), "ort": ("neuer Ort der Karte", "new place on the map"), "ziel": ("Ziel der Geschichte erreicht", "story goal reached"),
           "akt": ("Akt geschafft", "act done"), "idee": ("gute Idee (zurzeit nicht vergeben)", "good idea (not given at the moment)")}
GRUPPE = {"nsc": ("Figuren", "People"), "orakel": ("Orakel", "Oracle"), "eigen": ("Eigene", "Own")}   # tables (dungeon_tabellen)
TAB_ZEICHEN = {"nsc": "👤", "orakel": "🔮", "eigen": "✎",      # a table's sign in the list: its own, else its group's
               "nsc_aussehen": "👁️", "nsc_art": "🎭", "nsc_wunsch": "💭", "nsc_geheimnis": "🤫", "nsc_beruf": "🛠️",
               "orakel_aktion": "⚡", "orakel_thema": "📜", "orakel_ort": "🗺️", "orakel_merkmal": "🔍", "orakel_wendung": "🔀",
               "orakel_komplikation": "⚠️", "orakel_hinweis": "💡", "orakel_gefahr": "☠️", "orakel_chance": "🍀", "orakel_aerger": "🏘️"}
MIT_BILD = ("gegenstaende", "gegner", "klassen", "voelker", "hintergruende", "welten", "runen")   # welten, peoples, classes,
# backgrounds since Dominik 2026-10-24 „1a 2 und 3“: a people, class or background in the style of the world chosen above;
# runes since Dominik 2026-10-28 „in den regeln sehe ich diese nicht.“, as that world's word (Rune, Chip, Perle, Siegel)
WELT_WAHL = tuple(dingbild.HELD_TEILE) + ("runen",)   # the parts whose pictures follow the world chosen above the list
BODY = 16000              # one entry as JSON
NEU_FUER = 30             # a foe of the bestiary is „neu“ for this many versions after its „seit“ (Bestiarium-Punkt 9)
HELDEN = (2, 3, 4, 5)     # the group sizes the detail shares a foe's EP among


def _lang(request):
    return "en" if request.query_params.get("lang") == "en" else "de"


def _tx(v, li):
    return str(v[li] if isinstance(v, list) and len(v) > li else v[0] if isinstance(v, list) and v else v or "")


def _name(x, li):
    n = x.get("name")
    if n is None and isinstance(x.get("satz") or x.get("text"), list):   # an effect, a stall event: its sentence's start
        t = _tx(x.get("satz") or x.get("text"), li)
        return t.split(":")[0] if ":" in t else t if len(t) <= NAME_KURZ else t[:NAME_KURZ].rsplit(" ", 1)[0] + " …"
    return str(n[li] if isinstance(n, list) and len(n) > li else n or x.get("id", ""))


def _words(v, li):
    """A pair of word lists [German, English]: the page's language."""
    return [str(y) for y in v[li]] if isinstance(v, list) and len(v) > li and isinstance(v[li], list) else []


def _num(v, li):
    return f"{v:g}" if li else f"{v:g}".replace(".", ",")


def _welten(r, x, li):
    """The worlds an entry of the map's tables counts in (none named: all)."""
    wn = {w["id"]: _name(w, li) for w in r["welten"]}
    return ", ".join(wn.get(w, w) for w in x["welten"]) if x.get("welten") else ("all" if li else "alle")


def _sign(v):
    return f"+{v}" if v >= 0 else str(v)


def line(teil, x, r, li):
    """One line of values for a row (fixed words, the catalog's numbers)."""
    en = li == 1
    if teil == "gegner":
        s = {0.125: "⅛", 0.25: "¼", 0.5: "½"}.get(x.get("stufe"), f"{x.get('stufe', 0):g}")
        dmg = f"{x.get('anzahl_wuerfel', 1)}{'d' if en else 'W'}{x.get('schaden', 0)}" + (f"+{x['schaden_plus']}" if x.get("schaden_plus") else "")
        return " · ".join([("Level " if en else "Stufe ") + s, ("Life " if en else "Leben ") + str(x.get("leben", 0)),
                           ("Armour " if en else "Rüstung ") + str(x.get("ruestung", 0)), _sign(x.get("angriff", 0)) + " " + dmg, f"{x.get('ep', 0)} EP"])
    if teil == "gegenstaende":
        sel = {s["id"]: s["name"][li] for s in r["seltenheit"]}
        out = [ART.get(x.get("art"), ("", ""))[li], sel.get(x.get("seltenheit"), "gewürfelt" if not en else "rolled")]
        if x.get("wert"):
            out.append(_name(next((v for v in r["werte"] if v["id"] == x["wert"]), {"id": x["wert"]}), li))
        for k, de, enw, pre in (("schaden", "Schaden", "Damage", "W"), ("schutz", "Schutz", "Protection", ""), ("heilung", "Heilung", "Healing", ""),
                                ("grad", "Grad", "Grade", "")):
            if k in x:
                out.append(f"{enw if en else de} {('d' if en else pre) if pre else ''}{x[k]}")
        if isinstance(x.get("segen"), dict):
            sw = next((_name(v, li)[:3].upper() for v in r["werte"] if v["id"] == x["segen"].get("wert")), "")
            out.append(f"{'Blessing' if en else 'Segen'} {sw} +{x['segen'].get('bonus', 0)} × {x['segen'].get('zuege', 1)}".replace("  ", " "))
        if isinstance(x.get("hilft"), dict):
            out.append(("Tool +" if en else "Werkzeug +") + "/".join(str(n) for n in dungeon.WERKZEUG))
        if "preis" in x:
            out.append(f"{x['preis']} {'gold' if en else 'Gold'}")
        return " · ".join(out)
    if teil == "tabellen":                     # Tabletop-Punkt 8: the admin's own tables next to the shipped ones
        return f"{GRUPPE.get(x.get('gruppe'), ('', ''))[li]} · {len(x.get('zeilen') or [])} {'rows' if en else 'Zeilen'}"
    L = lambda de, enw: enw if en else de          # noqa: E731
    if teil == "runen":
        return " · ".join([L("Rang ", "Rank ") + str(x.get("rang", 0)), _tx(x.get("sinn"), li), f"{x.get('preis', 0)} {L('Gold', 'gold')}"])
    if teil == "runenwoerter":
        rn = {k: _name(v, li) for k, v in runen.by(r).items()}
        return " · ".join([" + ".join(rn.get(k, k) for k in x.get("runen") or []), ORT_RW.get(x.get("ort"), (x.get("ort", ""),) * 2)[li],
                           L("ab Stufe ", "from level ") + str(x.get("ab", 1))])
    if teil == "effekte":
        nur = ", ".join(ART.get(a, (a, a))[li] for a in x.get("nur") or []) or L("jedes Ding", "any thing")
        was = WIRKUNG_ART.get(x.get("wirkung"), (None, None))[li] or _name(next((v for v in r["werte"] if v["id"] == x.get("wert")), {"id": x.get("wert", "")}), li) + f" +{x.get('bonus', 0)}"
        return " · ".join(filter(None, [was, kampf.ART_NAME.get(x.get("art"), ("", ""))[li], nur]))
    if teil == "ortsarten":
        return " · ".join(filter(None, [_welten(r, x, li), L("Startort", "start") if x.get("start") else "", L("mit Gewölbe", "with a vault") if x.get("gewoelbe") else ""]))
    if teil in ("raeume", "begegnungen"):
        art = (RAUM_ART if teil == "raeume" else BEGEGNUNG_ART).get(x.get("art"), (x.get("art", ""),) * 2)[li]
        return " · ".join([art, L("Gewicht ", "weight ") + str(x.get("gewicht", 1)), _welten(r, x, li)])
    if teil == "fallen":
        a, b = (x.get("schaden") or [0, 0])[:2]
        wn = _name(next((v for v in r["werte"] if v["id"] == x.get("wert")), {"id": x.get("wert", "")}), li)
        return " · ".join([f"{wn} {L('SG', 'DC')} {x.get('schwer', 0)}", L(f"Schaden {a} bis {b}", f"damage {a} to {b}"), _welten(r, x, li)])
    if teil == "raetsel":
        return _tx(x.get("frage"), li)
    if teil == "stillstand":
        return L("mild, auch am Kindertisch", "mild, also at the children's table") if x.get("mild") else L("nicht am Kindertisch", "not at the children's table")
    kurz = {w["id"]: _name(w, li)[:3].upper() for w in r["werte"]}
    if teil == "klassen":
        return " · ".join([" · ".join(kurz.get(k, k) for k in (x.get("reihe") or [])[:2]), ("Life " if en else "Leben ") + str(x.get("leben", 0)),
                           f"{len(x.get('faehigkeiten') or [])} {'abilities' if en else 'Fähigkeiten'}"])
    if teil in ("voelker", "hintergruende"):
        return " · ".join(f"{kurz.get(k, k)} +{v}" for k, v in (x.get("werte") or {}).items()) or ""
    if teil == "zustaende":
        return " · ".join([w.replace("_", " ") for w in x.get("wirkung") or []] + ([f"{x['runden']} {'rounds' if en else 'Runden'}"] if x.get("runden") else []))
    s = x.get("satz") or x.get("info")
    return str(s[li] if isinstance(s, list) and len(s) > li else s or "")


ART = {"waffe": ("Waffe", "Weapon"), "ruestung": ("Rüstung", "Armour"), "schmuck": ("Schmuck", "Jewellery"),
       "trank": ("Trank", "Potion"), "zauber": ("Zauber", "Spell"), "rolle": ("Schriftrolle", "Scroll"),
       "werkzeug": ("Werkzeug", "Tool"), "schatz": ("Schatz", "Treasure")}


def _vnum(v):
    """V01.1.038 → 1038 (the series after V01.0.999 goes on at V01.1.000); None for anything else."""
    p = str(v or "").lstrip("Vv").split(".")
    return int(p[1]) * 1000 + int(p[2]) if len(p) == 3 and all(n.isdigit() for n in p) else None


def frisch(x, jetzt=None):
    """A foe added in the last NEU_FUER versions (its „seit“), shown as „neu“ in the bestiary."""
    a, b = _vnum(x.get("seit")), _vnum(jetzt if jetzt is not None else app_version())
    return a is not None and b is not None and 0 <= b - a < NEU_FUER


def arten(x):
    """A foe's damage kind and what hurts it more or less, as kind ids (only known ones)."""
    return {"art": x.get("schaden_art", "hieb"), **{k: [a for a in x.get(k) or [] if a in kampf.ART_NAME] for k in ("resistenz", "immun", "schwaeche")}}


def werte(teil, x, r, li):
    """What an entry does, as [label, value] pairs for the detail (Dominik 2026-10-24 „sollten immer auch Werte
    anzeigen wie stark, was sie bewirken“): the catalog's numbers in fixed words, the same lines the table shows."""
    en = li == 1
    w = {v["id"]: _name(v, li) for v in r["werte"]}
    L = lambda de, enw: enw if en else de          # noqa: E731
    out = []
    if teil == "gegenstaende":
        out.append([L("Art", "Kind"), ART.get(x.get("art"), (x.get("art", ""),) * 2)[li]])
        try:                                        # what it does at the table (dungeon.item_view, common rarity)
            it = {"i": 0, "id": x["id"], "s": x.get("seltenheit") or r["seltenheit"][0]["id"]}
            for z in dungeon.item_view(r, it, "en" if en else "de")["zeilen"]:
                out.append([L("Wirkung", "Effect"), z.replace(" + 0", "")])
        except (KeyError, IndexError, TypeError):
            pass
        if x.get("wert"):
            out.append([L("Zählt auf", "Uses"), w.get(x["wert"], x["wert"])])
        if x.get("ziel"):
            out.append([L("Für", "For"), {"selbst": L("sich selbst", "oneself"), "gruppe": L("die ganze Gruppe", "the whole group"),
                                          "verbuendeter": L("einen Freund, den die Aktion nennt", "a friend the action names")}.get(x["ziel"], x["ziel"])])
        if isinstance(x.get("rettung"), dict) and x["rettung"].get("wert"):   # Kampf-Audit H4: the foe's saving throw
            out.append([L("Rettungswurf des Gegners", "Foe's saving throw"), w.get(x["rettung"]["wert"], x["rettung"]["wert"])
                        + (L(", geschafft: halber Schaden", ", passed: half damage") if x.get("halb") else L(", geschafft: keine Wirkung", ", passed: no effect"))])
        if x.get("art") == "zauber" and x.get("zustand"):
            z = {v["id"]: _name(v, li) for v in r.get("zustaende") or []}
            out.append([L("Zustand beim Gegner", "Condition on the foe"), z.get(x["zustand"], x["zustand"])])
        if x.get("grad"):
            out.append([L("Zaubergrad", "Spell grade"), str(x["grad"])])
        if x.get("klassen"):
            k = {c["id"]: _name(c, li) for c in r["klassen"]}
            out.append([L("Klassen", "Classes"), ", ".join(k.get(c, c) for c in x["klassen"])])
        if x.get("platz"):
            out.append([L("Getragen an", "Worn on"), str(x["platz"])])
        out.append([L("Gewicht", "Weight"), f"{x.get('kg', 0):g} kg"])
        if "preis" in x:
            out.append([L("Preis", "Price"), f"{x['preis']} {L('Gold', 'gold')}" + ("" if x.get("seltenheit") else L(" (mal Seltenheit)", " (times rarity)"))])
    elif teil == "gegner":
        d = x.get("schaden", 0)
        n = x.get("anzahl_wuerfel", 1)
        avg = n * (d + 1) / 2 + x.get("schaden_plus", 0)
        out += [[L("Stufe", "Level"), line("gegner", x, r, li).split(" · ")[0].split(" ")[-1]], [L("Leben", "Life"), str(x.get("leben", 0))],
                [L("Rüstung", "Armour"), str(x.get("ruestung", 0)) + L(" (so schwer ist er zu treffen)", " (how hard it is to hit)")],
                [L("Angriff", "Attack"), f"W20 {_sign(x.get('angriff', 0))}" if not en else f"d20 {_sign(x.get('angriff', 0))}"],
                [L("Schaden", "Damage"), f"{n}{'d' if en else 'W'}{d}" + (f"+{x['schaden_plus']}" if x.get("schaden_plus") else "") + L(f", im Schnitt {avg:g}", f", {avg:g} on average")],
                ["EP", str(x.get("ep", 0)) + L(" für die Gruppe", " for the group")]]
        if isinstance(x.get("werte"), dict) and x["werte"]:
            out.append([L("Werte", "Values"), " · ".join(f"{w.get(k, k)[:3].upper()} {v}" for k, v in x["werte"].items())])
        if x.get("zustaende"):
            z = {c["id"]: _name(c, li) for c in r.get("zustaende") or []}
            out.append([L("Kann bewirken", "Can cause"), ", ".join(z.get(c, c) for c in x["zustaende"])])
            sg = x["sg"] if isinstance(x.get("sg"), int) else kampf.RETTUNG + int(x.get("stufe", 0) // 4)   # Kampf-Audit N6
            out.append([L("Rettungswurf dagegen", "Save against it"), L(f"SG {sg}", f"DC {sg}")])
        if x.get("groesse"):
            out.append([L("Größe", "Size"), str(x["groesse"])])
        a = arten(x)
        k = lambda i: f"{kampf.ART_ZEICHEN.get(i, '')} {kampf.ART_NAME[i][li]}".strip()       # noqa: E731
        out.append([L("Schadensart", "Damage kind"), k(a["art"]) if a["art"] in kampf.ART_NAME else ""])
        for f, de, enw in (("schwaeche", "Schwäche (doppelt)", "Weak to (double)"), ("resistenz", "Widerstand (halb)", "Resists (half)"),
                           ("immun", "Immun (kein Schaden)", "Immune (no damage)")):
            out.append([L(de, enw), ", ".join(k(i) for i in a[f])])
        if kampf.blows(x) > 1:                   # Tabletop-Punkt 12: the multiattack
            out.append([L("Angriffe je Zug", "Attacks a turn"), str(kampf.blows(x))])
        if x.get("boss"):
            out.append([L("Boss", "Boss"), L(f"+{int(kampf.BOSS_LEBEN * 100)} % Leben je Held ab dem zweiten, ab halbem Leben Phase 2 "
                                             f"(+{kampf.BOSS_PHASE} zum Treffen), mindestens zwei Angriffe je Zug, Fund eine Seltenheit besser",
                                             f"+{int(kampf.BOSS_LEBEN * 100)} % life per hero beyond the first, phase 2 at half life "
                                             f"(+{kampf.BOSS_PHASE} to hit), at least two attacks a turn, its find one rarity better")])
        out.append([L("EP je Held", "EP per hero"), " · ".join(f"{n}: {int(x.get('ep', 0)) // n}" for n in HELDEN)])
        wn = [_name(w, li) for w in r["welten"] if kampf.plays_in(r, x, w["id"])]
        out.append([L("Welten", "Worlds"), L("alle", "all") if len(wn) == len(r["welten"]) else ", ".join(wn)])
        if frisch(x):
            out.append([L("Neu", "New"), str(x["seit"])])
    elif teil == "runen":
        out.append([L("Bedeutung", "Meaning"), _tx(x.get("sinn"), li)])
        for o, de, enw in (("waffe", "In einer Waffe", "In a weapon"), ("ruestung", "In getragener Rüstung", "In worn armour"),
                           ("schild", "In einem Schild", "In a shield")):
            out.append([L(de, enw), runen.line(r, x[o], li) if isinstance(x.get(o), dict) else L("passt nicht", "does not fit")])
        rang = int(x.get("rang", 1))
        out.append([L("Fällt", "Falls"), L(f"ab Gruppenstufe {max(1, rang - runen.RANG_PLUS)}", f"from group level {max(1, rang - runen.RANG_PLUS)}")
                    + (L(", auch beim Krämer", ", also at the trader") if rang <= runen.KRAEMER else "")])
        out.append([L("Preis", "Price"), L(f"{x.get('preis', 0)} Gold, Händler zahlen {runen.sell_price(r, x['id'])}",
                                           f"{x.get('preis', 0)} gold, merchants pay {runen.sell_price(r, x['id'])}")])
    elif teil == "runenwoerter":
        rn = {k: _name(v, li) for k, v in runen.by(r).items()}
        out += [[L("Runen in dieser Reihenfolge", "Runes in this order"), ", ".join(rn.get(k, k) for k in x.get("runen") or [])],
                [L("In", "In"), ORT_RW.get(x.get("ort"), (x.get("ort", ""),) * 2)[li] + L(f" mit {x.get('sockel', 0)} Sockeln", f" with {x.get('sockel', 0)} sockets")],
                [L("Ab Stufe", "From level"), str(x.get("ab", 1))],
                [L("Dazu", "Adds"), runen.line(r, x["zusatz"], li) if isinstance(x.get("zusatz"), dict) else ""],
                [L("Am Tisch", "At the table"), L("noch nicht: Runenwörter kommen mit Stufe 2 der Runen", "not yet: runewords come with stage 2 of the runes")]]
    elif teil == "effekte":
        out += [[L("Wirkung", "Effect"), WIRKUNG_ART.get(x.get("wirkung"), ("", ""))[li]],
                [L("Schadensart", "Damage kind"), f"{kampf.ART_ZEICHEN.get(x.get('art'), '')} {kampf.ART_NAME[x['art']][li]}".strip() if x.get("art") in kampf.ART_NAME else ""],
                [L("Hebt", "Raises"), f"{w.get(x.get('wert'), x.get('wert') or '')} +{x['bonus']}" if x.get("bonus") else ""],
                [L("Nur an", "Only on"), ", ".join(ART.get(a, (a, a))[li] for a in x.get("nur") or [])]]
    elif teil == "ortsarten":
        out += [[L("Welten", "Worlds"), _welten(r, x, li)], [L("Startort", "Start place"), L("ja", "yes") if x.get("start") else L("nein", "no")],
                [L("Gewölbe darunter", "Vault below"), L("ja", "yes") if x.get("gewoelbe") else L("nein", "no")],
                [L("Feste Namen", "Fixed names"), ", ".join(_words(x.get("namen"), li))],
                [L("Wortteile für neue Namen", "Word parts for new names"), ", ".join(_words(x.get("teile"), li))]]
    elif teil in ("raeume", "begegnungen"):
        art = (RAUM_ART if teil == "raeume" else BEGEGNUNG_ART).get(x.get("art"), (x.get("art", ""),) * 2)[li]
        out += [[L("Art", "Kind"), art], [L("Gewicht", "Weight"), str(x.get("gewicht", 1)) + L(" (so oft wird es gezogen, im Vergleich)", " (how often it is drawn, compared)")],
                [L("Welten", "Worlds"), _welten(r, x, li)]]
    elif teil == "fallen":
        a, b = (x.get("schaden") or [0, 0])[:2]
        out += [[L("Rettungswurf", "Saving throw"), L(f"W20 + {w.get(x.get('wert'), '')} gegen SG {x.get('schwer', 0)}, je zwei Stufen der Gruppe +1",
                                                       f"d20 + {w.get(x.get('wert'), '')} against DC {x.get('schwer', 0)}, +1 per two levels of the group")],
                [L("Schaden", "Damage"), L(f"{a} bis {b}, geschafft die Hälfte, Rüstung hilft nicht", f"{a} to {b}, passed half of it, armour does not help")],
                [L("Welten", "Worlds"), _welten(r, x, li)]]
    elif teil == "raetsel":
        out += [[L("Frage", "Question"), _tx(x.get("frage"), li)], [L("Hinweis", "Hint"), _tx(x.get("hinweis"), li)],
                [L("Lösung", "Answer"), " / ".join(_words(x.get("loesung"), li))]]
    elif teil == "stillstand":
        out += [[L("Ereignis", "Event"), _tx(x.get("text"), li)], [L("Am Kindertisch", "At the children's table"), L("ja", "yes") if x.get("mild") else L("nein", "no")]]
    elif teil == "tabellen":
        z = x.get("zeilen") or []
        wn = {w["id"]: _name(w, li) for w in r["welten"]}
        out += [[L("Gruppe", "Group"), GRUPPE.get(x.get("gruppe"), ("", ""))[li]], [L("Zeilen", "Rows"), str(len(z))],
                [L("Würfel", "Die"), (f"W{len(z)}" if not en else f"d{len(z)}") + L(", jede Zeile gleich oft; in einer Welt nur die Zeilen für sie",
                                                                                    ", every row as often; in a world only the rows for it")],
                [L("Nur in Welten", "Only in worlds"), ", ".join(sorted({wn.get(w, w) for y in z if isinstance(y, dict) for w in y.get("welten") or []}))]]
    elif teil == "zustaende":
        out += [[L("Wirkung", "Effect"), ", ".join(v.replace("_", " ") for v in x.get("wirkung") or [])]]
        if x.get("runden"):
            out.append([L("Dauer", "Lasts"), f"{x['runden']} " + L("Runden", "rounds")])
    return [z for z in out if z[1]]


def tafel(x, r, li):
    """A table's rows for the detail (Dominik 2026-10-25 „ich sehe gar nicht die tabellen“): the number, the text in the
    page's language and the worlds of a row that only counts in some."""
    wn = {w["id"]: _name(w, li) for w in r["welten"]}
    return [{"n": i + 1, "t": str(y["t"][li] if len(y["t"]) > li else y["t"][0]), "w": ", ".join(wn.get(w, w) for w in y.get("welten") or [])}
            for i, y in enumerate(x.get("zeilen") or []) if isinstance(y, dict) and isinstance(y.get("t"), list) and y["t"]]


def _an(key):
    import features
    try:
        return bool(features.admin_on(key))
    except Exception:  # noqa: BLE001 - a broken config: shown as off
        return False


def kasten(teil, r, li):
    """The fixed rules around a part, above its list (Dominik 2026-10-28 „die runen … mit Sockeln, Obergrenzen und dem
    Schalter“): the switch with its way (a jump link on the page) and [label, value] pairs from the code's constants."""
    L = lambda de, enw: enw if li else de          # noqa: E731
    if teil in ("runen", "runenwoerter"):
        an, sw = _an(runen.KEY), {"name": L("Runen und Sockel", "Runes and sockets"),
                                  "weg": L("Funktionen → KI-Dungeon-Master → Runen und Sockel", "Features → AI Dungeon Master → Runes and sockets")}
        sel = [_name(x, li) for x in r["seltenheit"]]
        d = runen.DECKEL
        sp = runen.SOCKEL_PLATZ
        zeilen = [[L("Sockel", "Sockets"), L(f"Waffen und Rüstungen bis „{sel[runen.SOCKEL_BIS]}“ kommen zu {runen.SOCKEL_FUND} von 100 aus einem Fund mit Sockeln: "
                                               f"eine Waffe ab W{runen.SOCKEL_GROSS} 3, sonst 2; Körper {sp['koerper']}, Schild {sp['nebenhand']}, Kopf {sp['kopf']}, "
                                               f"Hände {sp['haende']}, Füße {sp['fuesse']}",
                                               f"Weapons and armour up to \"{sel[runen.SOCKEL_BIS]}\" come from a find with sockets {runen.SOCKEL_FUND} times in 100: "
                                               f"a weapon from d{runen.SOCKEL_GROSS} 3, else 2; body {sp['koerper']}, shield {sp['nebenhand']}, head {sp['kopf']}, "
                                               f"hands {sp['haende']}, feet {sp['fuesse']}")]]
        if teil == "runen":
            f = runen.FUND
            zeilen += [[L("Funde", "Finds"), L(f"eine Rune nach einem Kampf zu {f['gegner']}, aus einer Truhe zu {f['truhe']}, als Belohnung zu {f['belohnung']} von 100, "
                                               f"von einem Boss immer; nach {runen.PECH} Kampffunden ohne Rune kommt die nächste sicher; höchster Rang: Gruppenstufe + {runen.RANG_PLUS}",
                                               f"a rune after a fight {f['gegner']}, from a chest {f['truhe']}, as a reward {f['belohnung']} times in 100, from a boss always; "
                                               f"after {runen.PECH} fights' finds without a rune the next one surely; highest rank: group level + {runen.RANG_PLUS}")],
                       [L("Krämer", "Trader"), L(f"verkauft die Ränge 1 bis {runen.KRAEMER}, je {runen.KRAEMER_N[0]} bis {runen.KRAEMER_N[1]}; jeder Händler kauft Runen zum halben Preis",
                                                 f"sells ranks 1 to {runen.KRAEMER}, {runen.KRAEMER_N[0]} to {runen.KRAEMER_N[1]} of each; every merchant buys runes at half the price")],
                       [L("Runenbeutel", "Rune bag"), L(f"höchstens {runen.BEUTEL_MAX} Runen je Held, neben der Tasche", f"at most {runen.BEUTEL_MAX} runes per hero, beside the bag")]]
        zeilen += [[L("Obergrenzen", "Caps"), L(f"ein Ding mit Runen höchstens so stark wie „{sel[3]}“ (Waffe {_num(d['waffe'], li)}, Körper {_num(d['koerper'], li)}, "
                                                 f"die übrigen {_num(d['rest'], li)}); Treffer höchstens +{runen.TREFFER_MAX}; Rüstungsklasse aus Runen +{runen.RK_DING} je Ding "
                                                 f"und +{runen.RK_HELD} je Held; Leben aus Runen +{runen.LEBEN_HELD} je Held; {runen.WIDERSTAND_DING} Widerstandsart je Ding; "
                                                 "jedes Element einmal je Ding",
                                                 f"a thing with runes at most as strong as \"{sel[3]}\" (weapon {_num(d['waffe'], li)}, body {_num(d['koerper'], li)}, "
                                                 f"the rest {_num(d['rest'], li)}); to hit at most +{runen.TREFFER_MAX}; armour class from runes +{runen.RK_DING} per thing "
                                                 f"and +{runen.RK_HELD} per hero; life from runes +{runen.LEBEN_HELD} per hero; {runen.WIDERSTAND_DING} resistance per thing; "
                                                 "each element once per thing")],
                   [L("Einsetzen", "Setting"), L("im Heldenbogen unter Tasche, mit Vorschau, nie im Kampf; danach sitzt die Rune fest",
                                                  "in the hero sheet under bag, with a preview, never in a fight; then the rune stays in for good")],
                   [L("Welten", "Worlds"), ", ".join(f"{_name(w, li)}: {runen.word(w['id'], li)}" for w in r["welten"])]]
        if teil == "runenwoerter":
            zeilen.insert(0, [L("Am Tisch", "At the table"), L("noch nicht: Runenwörter, Sockel bohren und Herauslösen kommen mit Stufe 2 der Runen",
                                                               "not yet: runewords, drilling sockets and taking runes out come with stage 2 of the runes")])
        return {"schalter": dict(sw, an=an), "zeilen": zeilen}
    if teil == "stillstand":
        return {"schalter": {"name": L("Spieler anleiten", "Guide the players"), "an": _an("dungeonanleiten"),
                             "weg": L("Funktionen → KI-Dungeon-Master → Spieler anleiten", "Features → AI Dungeon Master → Guide the players")},
                "zeilen": [[L("Wann", "When"), L("Kommt die Geschichte ein paar Züge nicht voran (Einsteiger nach 1, Normal nach 2 erzählten Zügen, Erfahren nie), "
                                                 "lässt die Erzählung erst etwas Greifbares auftauchen, einen Zug später würfelt das Panel eines dieser Ereignisse, "
                                                 "danach kommt ein Tipp aus der Szene",
                                                 "When the story does not move on for a few turns (beginner after 1, normal after 2 told turns, experienced never), "
                                                 "the narration first lets something tangible appear, one turn later the panel rolls one of these events, "
                                                 "then comes a tip from the scene")],
                           [L("Kindertisch", "Children's table"), L("nur die milden", "only the mild ones")]]}
    return None


def zahlen(lang="de"):
    """The fixed numbers of the rules as rows to look at (Dominik 2026-10-28 „fehlt sonst noch etwas unter den regeln?“):
    levels and experience, the find table, gold, prices, the difficulty of a check, the encounter budget and the limits.
    Only what the panel uses; changed in „Für Fortgeschrittene (JSON)“ (stufen_ep, ladungen, faehigkeit_auf, ep, fundtabelle,
    anlass, pech_schutz, gold, preise, grenzen) or in the code (difficulty, budget)."""
    li = 1 if lang == "en" else 0
    L = lambda de, enw: enw if li else de          # noqa: E731
    r = dungeon.rules()
    sel = r["seltenheit"]
    g = r["grenzen"]
    se, la, fa = r["stufen_ep"], r["ladungen"], set(r["faehigkeit_auf"])
    stufen = {"kopf": [L("Stufe", "Level"), L("EP ab", "EP from"), L("Ladungen Grad 1–5", "Charges grade 1–5"), L("Neue Fähigkeit", "New ability")],
              "zeilen": [[str(i + 1), str(se[i]), " · ".join(map(str, la[i])) if i < len(la) else "", "✓" if i + 1 in fa else ""] for i in range(len(se))]}
    fund = {"kopf": [L("Stufe", "Level")] + [_name(s, li) for s in sel[1:]],
            "zeilen": [[str(i + 1)] + [L("nie", "never") if v >= dungeon.NIE else L(f"ab {v}", f"from {v}") for v in z] for i, z in enumerate(r["fundtabelle"])]}
    preise = {"kopf": [L("Art", "Kind"), L("Grundpreis", "Base price")], "zeilen": [[ART.get(a, (a, a))[li], f"{p} {L('Gold', 'gold')}"] for a, p in r["preise"].items()]}
    budget = {"kopf": [L("Stufe", "Level"), L("EP je Held (mittel)", "EP per hero (medium)")], "zeilen": [[str(i + 1), str(b)] for i, b in enumerate(kampf.BUDGET[:g["stufe_max"]])]}
    ep = dict(r["ep"], probe=r["ep"]["probe"] * dungeon.PROBE_EP_SG // 10)   # a check's experience as the table gives it
    an = ", ".join(f"{ANLASS[k][li]} +{v}" for k, v in r["anlass"].items() if k in ANLASS)
    rows = [
        ("stufen", "📈", L("Stufen und Erfahrung", "Levels and experience"), L(f"{len(se)} Stufen, höchstens Stufe {g['stufe_max']}", f"{len(se)} levels, at most level {g['stufe_max']}"),
         [[L("Aufstieg", "Level up"), L("mit den EP der nächsten Stufe, höchstens einmal je Abend", "with the EP of the next level, at most once an evening")]], stufen),
        ("erfahrung", "⭐", L("Erfahrung", "Experience"), " · ".join(f"{EP_NAME[k][li]} {v}" for k, v in ep.items() if k in EP_NAME and k != "idee"),
         [[EP_NAME[k][li], str(v) + (L(" für jeden Helden", " for every hero") if k in ("ort", "ziel", "akt") else "")] for k, v in ep.items() if k in EP_NAME]
         + [[L("Ein Kampf", "A fight"), L("jeder Held das Budget seiner Stufe, mal wie schwer der Kampf war und welcher Teil der Gegner besiegt ist "
                                             "(geflohen oder Frieden zählt halb)", "every hero its level's budget, times how hard the fight was and the share of the foes "
                                             "beaten (fled or peace counts half)")]], None),
        ("fund", "🎁", L("Fundtabelle", "Find table"), L(f"W100 + Anlass, {len(r['fundtabelle'])} Stufen", f"d100 + occasion, {len(r['fundtabelle'])} levels"),
         [[L("Wurf", "Roll"), L("W100 plus Anlass: ", "d100 plus occasion: ") + an],
          [L("Pech-Schutz", "Bad-luck guard"), L(f"nach {r['pech_schutz'] - 1} Funden ohne Seltenes ist der nächste mindestens „{_name(sel[1], li)}“",
                                                 f"after {r['pech_schutz'] - 1} finds without a rare one the next is at least \"{_name(sel[1], li)}\"")]]
         + [[_name(s, li), f"+{s['bonus']} · " + L("Preis", "price") + f" ×{s['preis']}"] for s in sel], fund),
        ("gold", "💰", L("Gold", "Gold"), " · ".join(f"{ANLASS[k][li]} {a}–{b}" for k, (a, b) in r["gold"].items() if k in ANLASS),
         [[ANLASS[k][li], L(f"{a} bis {b} × Gruppenstufe, für jeden Helden", f"{a} to {b} × group level, for every hero")] for k, (a, b) in r["gold"].items() if k in ANLASS], None),
        ("preise", "🏷", L("Preise", "Prices"), L(f"{len(r['preise'])} Arten, mal Seltenheit", f"{len(r['preise'])} kinds, times rarity"),
         [[L("Regel", "Rule"), L("Grundpreis der Art mal dem Faktor der Seltenheit; Tränke, Schriftrollen, Zauber und Werkzeug den halben Faktor; ein fester Preis im Katalog gilt",
                                 "base price of the kind times the rarity's factor; potions, scrolls, spells and tools half the factor; a fixed price in the catalog counts")],
          [L("Händlerrabatt", "Merchant discount"), L(f"{dungeon.RABATT[0]} % je Punkt Charisma-Bonus, höchstens {dungeon.RABATT[1]} %",
                                                      f"{dungeon.RABATT[0]} % per point of the Charisma bonus, at most {dungeon.RABATT[1]} %")]], preise),
        ("sg", "🎯", L("Schwierigkeit einer Probe", "Difficulty of a check"), " · ".join(f"{SG_NAME[k][li]} {v}" for k, v in dungeon.PROBE_SG.items()),
         [[L("Regel", "Rule"), L("das Modell nennt nur die Stufe, das Panel setzt die Zahl; W20 + Wert muss sie erreichen, eine 20 gelingt immer, eine 1 nie",
                                 "the model names only the level, the panel sets the number; d20 + value has to reach it, a 20 always passes, a 1 never")]]
         + [[SG_NAME[k][li], L(f"SG {v}", f"DC {v}")] for k, v in dungeon.PROBE_SG.items()], None),
        ("budget", "⚔️", L("Begegnungen", "Encounters"), L(f"Budget je Held, {g['stufe_max']} Stufen", f"budget per hero, {g['stufe_max']} levels"),
         [[L("Regel", "Rule"), L("die EP aller Gegner, gezählt nach ihrem gemessenen Kampf-EP: das Budget jedes Helden nach seiner Stufe, zusammengezählt, "
                                 "mal dem Faktor der Gruppengröße, am Kindertisch die Hälfte",
                                 "the EP of all foes, counted by their measured fight EP: every hero's budget by its level, added up, "
                                 "times the factor of the group's size, half at the children's table")],
          [L("Gruppengröße", "Group size"), " · ".join(f"{i + 1}: ×{_num(f, li)}" for i, f in enumerate(kampf.GRUPPE)) + L(f", je weiterer +{_num(kampf.GRUPPE_PLUS, li)}", f", each more +{_num(kampf.GRUPPE_PLUS, li)}")],
          [L("Gefahr", "Danger"), L(f"leicht bis ×{_num(kampf.GEFAHR[0][0], li)}, mittel bis ×{_num(kampf.GEFAHR[1][0], li)}, darüber schwer",
                                    f"easy up to ×{_num(kampf.GEFAHR[0][0], li)}, medium up to ×{_num(kampf.GEFAHR[1][0], li)}, above that hard")]], budget),
        ("grenzen", "⚙️", L("Grenzen", "Limits"), L(f"bis {g['spieler']} Spieler, Stufe {g['stufe_max']}", f"up to {g['spieler']} players, level {g['stufe_max']}"),
         [[L("Spieler", "Players"), str(g["spieler"])], [L("Zeit je Zug", "Time per turn"), ", ".join(f"{s} s" for s in g["zug_s"]) + L(f" (Standard {g['zug_standard']} s)", f" (default {g['zug_standard']} s)")],
          [L("Runde läuft", "Round lasts"), ", ".join(f"{h} h" for h in g["stunden"])], [L("Höchste Stufe", "Top level"), str(g["stufe_max"])],
          [L("Spielbilder am Tag", "Game pictures a day"), str(g.get("bilder_tag", dungeon.BILDER_TAG))]], None)]
    zeilen = []
    for i, z, n, zl, w, t in rows:
        row = {"id": i, "name": n, "zeichen": z, "zeile": zl, "werte": [x for x in w if x[1]], "stand": "grund", "art": ""}
        if t:
            row["tabelle"] = t
        zeilen.append(row)
    return {"teil": ZAHLEN, "zeilen": zeilen, "eintraege": {}, "fest": True, "bilder_an": False,
            "kasten": {"zeilen": [[L("Ändern", "Change"), L("in Für Fortgeschrittene (JSON); Schwierigkeit und Budget misst der Prüfstand und stehen im Code",
                                                            "in Advanced (JSON); difficulty and budget are measured by the bench and live in the code")]]}}


def _welt_of(r, welt):
    """The world a people, class or background is shown and painted in: the one asked for if there is one, else the
    first."""
    ids = [w["id"] for w in r["welten"]]
    return welt if welt in ids else ids[0]


def view(teil, lang="de", welt=""):
    """{"teil", "zeilen": [...], "eintraege": {id: entry}}: the merged part with where each entry comes from; the people
    of the catalog from dungeon_personen (Personen-Katalog 1)."""
    if teil == "personen":
        return personen.view(lang)
    if teil == ZAHLEN:
        return zahlen(lang)
    li = 1 if lang == "en" else 0
    r = dungeon.rules()
    welt = _welt_of(r, welt)
    grund = {x["id"] for x in dungeon._base_rules(srd=False).get(teil) or []}
    base = {x["id"]: x for x in dungeon._base_rules().get(teil) or []}
    own = {x.get("id"): x for x in dungeon.own_rules().get(teil) or [] if isinstance(x, dict)}
    have = dingbild.files() if teil in MIT_BILD else frozenset()
    neu = set(dingbild.candidates()) if teil in MIT_BILD else set()
    rows, entries = [], {}
    for x in list(r.get(teil) or []) + [base[i] for i, o in own.items() if o.get("aus") and i in base]:
        i = x["id"]
        o = own.get(i)
        stand = "aus" if o and o.get("aus") else "geaendert" if o and i in base else "eigen" if o else "grund" if i in grund else "srd"
        row = {"id": i, "name": _name(x, li), "zeichen": x.get("zeichen") or ZEICHEN_TEIL.get(teil) or dingbild.ZEICHEN.get(x.get("art"), "")
               or (TAB_ZEICHEN.get(i) or TAB_ZEICHEN.get(x.get("gruppe"), "") if teil == "tabellen" else ""),
               "zeile": line(teil, x, r, li), "werte": werte(teil, x, r, li), "stand": stand, "art": x.get("art", "")}
        if teil == "gegner":
            row["marke"] = balance.foe(x, lang)
            row["stufe"] = x.get("stufe", 0)
            row.update(welten=[w["id"] for w in r["welten"] if kampf.plays_in(r, x, w["id"])], boss=bool(x.get("boss")), frisch=frisch(x), arten=arten(x))
        elif teil == "tabellen":
            row["tafel"] = tafel(x, r, li)
        elif teil == "gegenstaende":
            row["marke"] = balance.item(x, lang)
            row["selten"] = x.get("seltenheit") or ""      # the frame's colour (dungeon.js DMSEL); "" = rolled
            if row["selten"] and x.get("art") in r["preise"]:   # Wirtschaft Punkt 1: a fixed rarity has its final price (0: a legend)
                row["preis"] = dungeon.price(r, {"id": i, "s": row["selten"]})
        if teil in MIT_BILD:
            n, _ = dingbild.entry_pic(r, teil, x, welt)
            row["bild"] = n if n in have else ""
            cur = dingbild._current(r, x, teil, welt)[0]
            row["neu"] = "neu-" + cur[5:] if "neu-" + cur[5:] in neu else ""
            row["bv"], row["nv"] = dungeon.bild_v(row["bild"]), dungeon.bild_v(row["neu"])   # the browser keeps it until it changes
        rows.append(row)
        entries[str(i)] = x
    out = {"teil": teil, "zeilen": rows, "eintraege": entries, "bilder_an": dingbild.on()}
    k = kasten(teil, r, li)
    if k:
        out["kasten"] = k
    if teil in WELT_WAHL:              # the world the pictures are in, and the worlds to choose from (dungeon.js)
        out.update(welt=welt, welten=[{"id": w["id"], "name": _name(w, li)} for w in r["welten"]])
    if teil == "gegner":             # the filters (worlds) and the symbols of the damage kinds (dungeon.js dmRArt)
        out.update(weltfilter=[{"id": w["id"], "name": _name(w, li)} for w in r["welten"]],
                   arten={a: {"zeichen": kampf.ART_ZEICHEN.get(a, ""), "name": kampf.ART_NAME[a][li]} for a in kampf.SCHADEN_ARTEN})
    if teil == "gegenstaende":       # the ladder a rolled item climbs (dungeon.rarity: W100 + 2 × level)
        ft = r["fundtabelle"]                        # the first level a rarity can be found at (Wirtschaft Punkt 5)
        ab = [1] + [next((i + 1 for i, z in enumerate(ft) if z[k] < dungeon.NIE), 0) for k in range(len(r["seltenheit"]) - 1)]
        out["seltenheiten"] = [{"id": s["id"], "name": _name(s, li), "bonus": s["bonus"], "stufe": a, "preis": s["preis"]}
                               for s, a in zip(r["seltenheit"], ab)]
    return out


def change(teil, was, i, eintrag=None):
    """One entry of the own rules set, hidden or taken back; refused (ValueError with the errors) unless the rules
    still pass. Returns the hint of the balance for the entry (or None). A person goes to dungeon_personen."""
    if teil == "personen":
        if not personen.admin_on():
            raise LookupError("personen aus")
        return personen.change(was, i, eintrag)
    own = dungeon.own_rules()
    own = own if isinstance(own, dict) else {}
    ids = {str(x["id"]): x["id"] for x in dungeon._base_rules().get(teil) or []}
    i = ids.get(str(i), i)                              # a tone's id is a number
    lst = [x for x in own.get(teil) or [] if isinstance(x, dict) and str(x.get("id")) != str(i)]
    if was == "setzen":
        if not isinstance(eintrag, dict) or str(eintrag.get("id")) != str(i):
            raise ValueError(["id"])
        lst.append(eintrag)
    elif was == "aus":
        lst.append({"id": i, "aus": True})
    elif was != "zurueck":
        raise ValueError(["was"])
    own = dict(own, **{teil: lst})
    if not own[teil]:
        own.pop(teil)
    errs = [f"{teil}: höchstens {dungeon.EIGENE_MAX} eigene Einträge"] if len(lst) > dungeon.EIGENE_MAX else []
    errs += dungeon.check_rules(dungeon.merge(dungeon._base_rules(), own))
    if errs:
        print(f"dungeon: regelseite | abgelehnt | {len(errs)} fehler", flush=True)
        raise ValueError(errs[:20])
    write_json(dungeon.EIGENE, own, 2, 0o600, False, 0o700)
    dungeon._rules["r"] = None
    print(f"dungeon: regelseite | {was} | {teil}", flush=True)
    if was == "setzen" and teil in ("gegner", "gegenstaende"):
        m = balance.foe(eintrag) if teil == "gegner" else balance.item(eintrag)
        return m if m["marke"] in ("stark", "zu_stark") else None
    return None


def _entry(teil, i):
    x = (personen.load() if teil == "personen" else {str(k): v for k, v in dungeon._by(dungeon.rules(), teil).items()}).get(str(i))
    if not x:
        raise LookupError("eintrag")
    return x


@router.get("/api/admin/dungeon/katalog/{teil}", dependencies=[Depends(auth)])
async def katalog(teil: str, request: Request):
    guard.limit(request, "dungeonregel", admin=True)
    if teil not in ALLE:
        raise HTTPException(404, "teil")
    if teil == "personen" and not personen.admin_on():
        raise HTTPException(404, "personen aus")
    out = await asyncio.to_thread(view, teil, _lang(request), request.query_params.get("welt", "")[:40])
    if teil == "personen":                 # whether the voices from a description run (Dominik 2026-10-27 „stimme klang bei alles gleich“)
        out["stimme_design"] = await dungeon.design_up()
    return dungeon.json_out(request, out)


@router.post("/api/admin/dungeon/katalog/{teil}", dependencies=[Depends(auth)])
async def katalog_change(teil: str, request: Request):
    guard.limit(request, "dungeonregel", admin=True)
    if teil not in ALLE or teil == ZAHLEN:
        raise HTTPException(404, "teil")
    if teil == "personen" and not personen.admin_on():
        raise HTTPException(404, "personen aus")
    b = await json_body(request, BODY)
    i = str(b.get("id") or "")
    if not i or len(i) > 40:
        raise HTTPException(400, "id")
    try:
        hint = await asyncio.to_thread(change, teil, str(b.get("was") or ""), i, b.get("eintrag"))
    except ValueError as e:
        raise HTTPException(422, e.args[0] if e.args and isinstance(e.args[0], list) else ["eintrag"])
    except LookupError as e:
        raise dungeon._http(e)
    out = await asyncio.to_thread(view, teil, _lang(request), request.query_params.get("welt", "")[:40])
    out["hinweis"] = hint
    return out


@router.post("/api/admin/dungeon/personen/probe", dependencies=[Depends(auth)])
async def personen_probe(request: Request):
    """{"stimme": {alter, geschlecht, klang, wesen, tempo}, "lang"}: the fixed sentence in the voice the admin chose for a
    person of the catalog (dungeon_stimmen's fixed words; without VoiceDesign the rules' fixed NPC voice), as WAV."""
    guard.limit(request, "dungeonprobe", admin=True)
    if not personen.admin_on():
        raise HTTPException(404, "personen aus")
    b = await json_body(request, 2000)
    try:
        t = stimmen.clean(b.get("stimme"))
        if not t:
            raise ValueError("stimme")
        r = await asyncio.to_thread(dungeon.rules)
        v = dungeon.voices(r)
        await dungeon.design_up()          # a fresh look at the speech output, never a stale „not running“
        wav, ersatz = await dungeon.probe("", "en" if b.get("lang") == "en" else "de", stimmen.describe(t),
                                          v["npc_w"] if t["geschlecht"] == "weiblich" else v["npc"])
    except ValueError:
        print("dungeon: personen | probe | abgelehnt", flush=True)
        raise HTTPException(400, "stimme")
    except (RuntimeError, asyncio.TimeoutError) as e:
        print(f"dungeon: stimmprobe | fehler | klang | {str(e)[:20] or type(e).__name__}", flush=True)
        raise HTTPException(503, "Die Sprachausgabe ist gerade belegt.")
    print("dungeon: personen | probe", flush=True)
    return dungeon._probe_out(wav, ersatz)


@router.post("/api/admin/dungeon/katalog/{teil}/bild", dependencies=[Depends(auth)])
async def katalog_bild(teil: str, request: Request):
    """„Nochmal malen“ (was "malen"), then „Neues behalten“ ("neu") or „Altes behalten“ ("alt")."""
    guard.limit(request, "dungeonbild", admin=True)
    if teil not in MIT_BILD and not (teil == "personen" and personen.admin_on()):   # a person's face (Dominik 2026-10-27)
        raise HTTPException(404, "teil")
    b = await json_body(request, 2000)
    was = b.get("was")
    try:
        c = await asyncio.to_thread(_entry, teil, str(b.get("id") or ""))
        r = dungeon.rules()
        welt = _welt_of(r, str(b.get("welt") or ""))
        if was == "malen":
            why, neu = await dingbild.repaint(r, c, True, teil, welt)   # only an admin reaches this: no day limit
            if why != "ok":
                raise HTTPException(409, why)
            if not dingbild.entry_pic(r, teil, c, welt)[1]:   # „🖌 Malen“ of a missing picture: nothing to compare
                await asyncio.to_thread(dingbild.settle, r, c, True, teil, welt)
                return {"neu": "", "bild": dingbild.entry_pic(r, teil, c, welt)[0]}
            return {"neu": neu}
        if was not in ("neu", "alt"):
            raise HTTPException(400, "was")
        await asyncio.to_thread(dingbild.settle, r, c, was == "neu", teil, welt)
        return {"ok": True}
    except LookupError as e:
        raise dungeon._http(e)


@router.get("/api/admin/dungeon/bild/{name}", dependencies=[Depends(auth)])
async def bild(name: str, request: Request, klein: int = 0):
    """klein=1: the small copy for the list (dungeon.small_png; Dominik 2026-10-25: 391 full pictures held up the panel)."""
    guard.limit(request, "dungeonding", admin=True)
    if not (dingbild.NAME.fullmatch(name) or dingbild.NEU.fullmatch(name)):
        raise HTTPException(404, "bild")
    try:
        return dungeon._png_out(await asyncio.to_thread(dungeon.small_png if klein else dungeon._png, name))
    except LookupError as e:
        raise dungeon._http(e)


def counts():
    """Numbers for Live: own entries per part, hidden ones, candidates waiting."""
    own = dungeon.own_rules()
    own = own if isinstance(own, dict) else {}
    lst = [x for t in TEILE for x in own.get(t) or [] if isinstance(x, dict)]
    return {"eigene": sum(1 for x in lst if not x.get("aus")), "aus": sum(1 for x in lst if x.get("aus")),
            "kandidaten": len(dingbild.candidates()), "json": len(json.dumps(own))}
