"""Zustand → Technik, Knoten-Seiten: the step helper S. The texts of every box's page are in technik_seiten_*.py
(the engine, the order of the parts, checks and fingerprint are in technik_knoten.py, plan plaene/knoten-seiten.md).
Texts are (German, English); {mod.NAME|format} and {@auto} are filled
in from the code, never typed. When the way a box works changes, its page changes in the same commit and its "stand"
gets the new fingerprint that tests/test_technik.py names (Dominik 2026-10-14: „ebenso aktuell halten wie alles andere“).
"""


def S(sid, art, name, sub, text, side=None):
    """One step of a page's way. name, sub, text: (German, English). side: (kind, label, text or step id), label is
    "ja"/"nein" or (German, English)."""
    return {"id": sid, "art": art, "name": name, "sub": sub, "text": text, "side": side}
