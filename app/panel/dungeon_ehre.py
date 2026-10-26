"""KI-Dungeon-Master: Ehrungen des Abends (D&D idea 1, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; the idea of a fight's statistics from Drowbe/coffee-pub-blacksmith, own code and texts).

While a round runs, the panel counts per seat from its own dice receipts (count): hits, critical hits, damage, natural
20s and 1s, checks passed, sneaking passed, friends helped and life given to them. When the round ends (also by the end
of a chapter), award gives every title of the fixed list (TITEL) to the hero with the most, and every hero a certificate
with its numbers; the log entry "ehrung" carries it all (the table draws the certificate, the music thread plays its
fanfare). Only numbers of the panel, never of the model; at the children's table only the friendly titles.
"""
import features

EHRE = "dungeonehrungen"     # the switch „Ehrungen des Abends“ (features.py) for the round's host
ZAHLEN = ("treffer", "krit", "schaden", "zwanzig", "eins", "proben", "schatten", "rettet", "heilung")
ZAHL_MAX = 10 ** 6
# a title: id, the number it counts, the least for it, its name [de, en], its name at the children's table (None: none)
TITEL = (("klinge", "schaden", 1, ["Klinge des Abends", "Blade of the evening"], ["Mutigstes Herz", "Bravest heart"]),
         ("retter", "rettet", 1, ["Retter des Abends", "Rescuer of the evening"], ["Bester Freund", "Best friend"]),
         ("glueck", "zwanzig", 1, ["Glückskind", "Lucky one"], ["Glückskind", "Lucky one"]),
         ("schatten", "schatten", 2, ["Stillster Schatten", "Quietest shadow"], ["Leisester Fuchs", "Quietest fox"]),
         ("pech", "eins", 3, ["Pechvogel", "Hard-luck hero"], None))


def on(rd):
    return bool(rd.get("owner")) and features.allowed(EHRE, rd["owner"])


def count(rd, pid, **n):
    """Adds a seat's numbers of a roll (only with the switch; unknown keys and negative numbers count nothing)."""
    if not pid or not on(rd):
        return
    e = rd.setdefault("ehre", {}).setdefault(pid, {})
    for k, v in n.items():
        if k in ZAHLEN and isinstance(v, int) and v > 0:
            e[k] = min(ZAHL_MAX, e.get(k, 0) + v)


def award(rd, seats, kids):
    """The honours of the evening: each title to the seat with the most of its number (at least its least; a tie goes
    to the first seat), and one certificate per seat with numbers. seats: [(pid, name)] in the order of the table.
    Returns the log entry's fields, or None when nobody has a number."""
    z = rd.get("ehre") or {}
    seats = [(pid, name) for pid, name in seats if any(z.get(pid, {}).values())]
    if not seats:
        return None
    li = 1 if rd.get("lang") == "en" else 0
    titel = []
    for tid, k, least, name, kind in TITEL:
        if kids and not kind:
            continue
        best = max(seats, key=lambda s: z[s[0]].get(k, 0))
        if z[best[0]].get(k, 0) >= least:
            titel.append({"id": tid, "titel": (kind if kids else name)[li], "pid": best[0], "name": best[1], "zahl": z[best[0]][k]})
    urkunden = [{"pid": pid, "name": name, "zahlen": {k: z[pid].get(k, 0) for k in ZAHLEN if not (kids and k == "eins")},
                 "titel": [t["titel"] for t in titel if t["pid"] == pid]} for pid, name in seats]
    return {"titel": titel, "urkunden": urkunden}
