"""Symbols for slides and documents (Dominik 2026-10-12, Präsentationen professionell, point 4).

A fixed set of about 160 icons from Lucide (ISC license, symbole/LICENSE-lucide.txt) lies in the repository
as grey masks (symbole/<icon>.png, 192 px): nothing is loaded from the net. The model names a key word from
symbole.txt per point ("berg", "wasser", "euro"); an unknown word is matched against the point's title by the
words of each line, and without a match the Spark takes a neutral one. color() turns a mask into a PNG in the
look's color for PowerPoint, Word and PDF.
"""
import functools
import io
import os
import re

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "symbole")
FALLBACK = "funken"


def _load():
    rows = {}
    try:
        with open(os.path.join(HERE, "symbole.txt"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or "|" not in line:
                    continue
                key, en, icon, more = (x.strip() for x in line.rstrip("\n").split("|"))
                if re.fullmatch(r"[a-z0-9-]{1,40}", icon) and os.path.isfile(os.path.join(HERE, icon + ".png")):
                    rows[key] = {"en": en, "icon": icon, "words": {w.strip().casefold() for w in more.split(",") if w.strip()}}
    except OSError:
        pass
    return rows


ROWS = _load()
EN = {r["en"]: k for k, r in ROWS.items()}
WORD = re.compile(r"[\wäöüß-]+")


def keys():
    """The key words the model may choose from (German), one string for the prompt."""
    return ", ".join(ROWS)


def pick(word, title=""):
    """The key of the symbol for a point: the model's word (German or English), else a match in its title."""
    w = str(word or "").strip().casefold()
    if w in ROWS:
        return w
    if w in EN:
        return EN[w]
    words = set(WORD.findall(f"{w} {title}".casefold()))
    best, hits = FALLBACK, 0
    for k, r in ROWS.items():
        n = len(words & (r["words"] | {k, r["en"]}))
        if n > hits:
            best, hits = k, n
    if hits:
        return best
    # a part of a longer word ("Gebirgszüge" → gebirge)
    for k, r in ROWS.items():
        for x in r["words"] | {k}:
            if len(x) >= 5 and any(x in y for y in words):
                return k
    return FALLBACK if FALLBACK in ROWS else next(iter(ROWS), "")


@functools.lru_cache(maxsize=256)
def color(key, hex_):
    """PNG bytes of a symbol in this color (transparent around it), or b"" when there is none."""
    r = ROWS.get(key)
    if not r or not re.fullmatch(r"[0-9A-Fa-f]{6}", hex_ or ""):
        return b""
    from PIL import Image
    with Image.open(os.path.join(HERE, r["icon"] + ".png")) as m:
        mask = m.convert("L")
        im = Image.new("RGBA", mask.size, tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4)) + (0,))
        im.putalpha(mask)
        out = io.BytesIO()
        im.save(out, "PNG")
    return out.getvalue()
