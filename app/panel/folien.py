"""Slide types and the fixed rules for documents the Spark writes (Dominik 2026-10-12: "die präsentationen wirken
immer noch trist ... das muss alles professioneller werden" → plan plaene/praesentationen-professionell.md,
"alle punkte umsetzen 1-6").

1. Slide types instead of bullet points: the model picks one of LAYOUTS per slide and fills only its fields. The
   panel's rules keep the variety (vary): never the same type twice in a row, at most a third lists.
2. Less text: at most MAX_BULLETS points with at most MAX_WORDS words on a slide; what is to be said goes into
   the notes. tighten() moves what is too much into the notes and shortens at a natural break, the
   renderer never shrinks text below its smallest size.
3. Charts only with real numbers: at least 3 values that are not all the same, every one found in the material
   (check_chart); otherwise big numbers or no chart. The source is named under the chart, the key value marked.
6. Facts: every number in what the model wrote must be in the material (the person's words, the facts of this
   turn, own documents, the Kiwix article). numbers() and unbacked() find the others, drop_unbacked() takes them
   out. Small counts (up to 10) and "19. Jahrhundert" do not need a source.

All of this is plain rules on the model's JSON, never the model's judgement.
"""
import re

import symbole

LAYOUTS = {
    "liste": ("Stichpunkte", "Bullet points"),
    "kapitel": ("Kapiteltrenner", "Section divider"),
    "kernaussage": ("Kernaussage", "Key statement"),
    "symbole": ("Symbol-Raster", "Icon grid"),
    "zahlen": ("Große Zahlen", "Big numbers"),
    "ablauf": ("Zeitstrahl oder Ablauf", "Timeline or process"),
    "vergleich": ("Vergleich", "Comparison"),
    "bildtext": ("Bild und Text", "Picture and text"),
    "diagramm": ("Diagramm mit Aussage", "Chart with a message"),
    "fazit": ("Fazit", "Conclusion"),
}
MAX_BULLETS = 4
MAX_WORDS = 8
POINT_WORDS = 12          # the text under a symbol or a step
TITLE_WORDS = 4           # the title of a symbol point
MIN_POINTS, MAX_POINTS = 3, 6
SMALL = 10                # counts up to this need no source
MIN_CHART_VALUES = 3

# words in a heading or note that suggest a type (German and English)
HINTS = (
    ("fazit", r"fazit|zusammenfassung|schluss|ausblick|take.?aways?|conclusion|summary|outlook|wichtigste"),
    ("ablauf", r"geschichte|entstehung|entwicklung|zeitstrahl|chronik|ablauf|schritte?|phasen?|verlauf|prozess|"
               r"history|timeline|steps?|phases?|process|so geht|vorgehen"),
    ("vergleich", r"vergleich|gegenüber|vor.? und nachteile|pro und contra|unterschied|vs\.?|versus|"
                  r"compar|pros and cons|difference"),
    ("diagramm", r"statistik|entwicklung der|anteil|verteilung|zahlen im|statistics|share|distribution"),
    ("zahlen", r"zahlen|fakten|daten|kennzahlen|auf einen blick|facts|figures|key numbers|at a glance"),
    ("kapitel", r"^(teil|kapitel|part|chapter)\b"),
    ("bildtext", r"lage|landschaft|aussehen|bauwerk|ort|region|location|landscape|where"),
)
ROTATE = ("symbole", "kernaussage", "liste", "symbole", "zahlen", "liste")


def guess(heading, note=""):
    t = f"{heading} {note}".casefold()
    for lay, rx in HINTS:
        if re.search(rx, t):
            return lay
    return ""


def vary(want, can=None):
    """The types after the variety rules: never the same twice in a row, at most a third lists (at least one
    allowed). can(i, layout) says whether slide i may become that type (default: always)."""
    can = can or (lambda i, x: True)
    out = list(want)
    most_lists = max(1, len(out) // 3)
    alts = {"liste": ("symbole", "kernaussage", "fazit"), "symbole": ("liste", "kernaussage"),
            "kernaussage": ("symbole", "liste"), "zahlen": ("symbole", "liste"), "ablauf": ("symbole", "liste"),
            "vergleich": ("symbole", "liste"), "bildtext": ("symbole", "liste"), "diagramm": ("zahlen", "symbole", "liste"),
            "fazit": ("liste", "symbole"), "kapitel": ("kernaussage", "symbole")}
    for i in range(len(out)):
        prev = out[i - 1] if i else ""
        lists = sum(1 for x in out[:i] if x == "liste")
        if out[i] == prev or (out[i] == "liste" and lists >= most_lists):
            for a in alts.get(out[i], ("symbole",)):
                if a != prev and not (a == "liste" and lists >= most_lists) and can(i, a) and \
                        (i + 1 >= len(out) or a != out[i + 1]):
                    out[i] = a
                    break
    return out


def plan_layouts(sections, kind):
    """Sets "layout" on every section of an outline (the model's choice when it is one of LAYOUTS, else a guess
    from the heading, else in turn), then the variety rules. Only presentations get types."""
    if kind != "praesentation":
        for s in sections:
            s.pop("layout", None)
        return sections
    n = len(sections)
    want = []
    for i, s in enumerate(sections):
        lay = s.get("layout") if s.get("layout") in LAYOUTS else guess(s.get("heading", ""), s.get("note", ""))
        if not lay:
            lay = "fazit" if i == n - 1 and n >= 4 else ROTATE[i % len(ROTATE)]
        want.append(lay)
    for s, lay in zip(sections, vary(want)):
        s["layout"] = lay
    return sections


# ---------------------------------------------------------------- what the model wrote → the type it can be
def _words(t):
    return len(str(t or "").split())


def has(sec, lay):
    """Whether the section holds what a type needs."""
    pts, steps, cmp_ = sec.get("points") or [], sec.get("steps") or [], sec.get("compare") or {}
    return {"liste": bool(sec.get("bullets")),
            "kapitel": True,
            "kernaussage": bool(sec.get("quote")),
            "symbole": MIN_POINTS <= len(pts) or MIN_POINTS <= len(sec.get("bullets") or []) <= MAX_POINTS,
            "zahlen": len(sec.get("stats") or []) >= 1,
            "ablauf": len(steps) >= MIN_POINTS,
            "vergleich": bool((cmp_.get("left") or {}).get("points") and (cmp_.get("right") or {}).get("points")),
            "bildtext": bool(sec.get("pictures") or sec.get("wikipic")),
            "diagramm": bool(sec.get("chart")),
            "fazit": bool(sec.get("bullets") or pts)}.get(lay, False)


def to_points(bullets):
    """Bullets as symbol points (title = the bullet, the symbol from its words)."""
    return [{"icon": symbole.pick("", b), "title": b, "text": ""} for b in bullets][:MAX_POINTS]


def settle(sec, want):
    """The type the written section really gets: the wanted one when its fields are there, else the one its
    fields fit (chart, numbers, steps, comparison, points, statement, list)."""
    if want and has(sec, want):
        lay = want
    else:
        lay = next((x for x in ("diagramm", "zahlen", "ablauf", "vergleich", "symbole", "kernaussage", "liste")
                    if has(sec, x) and (x != "symbole" or sec.get("points"))), "")
        if not lay:
            lay = "kernaussage" if (sec.get("paras") and not sec.get("bullets")) else "liste"
            if lay == "kernaussage":
                sec["quote"] = " ".join(sec.pop("paras"))[:400]
    if lay == "symbole" and not sec.get("points"):
        sec["points"] = to_points(sec.pop("bullets", []))
    sec["layout"] = lay
    return sec


def convert(sec, lay):
    """Turns a written section into another type when vary() asks (only between types that keep the text)."""
    cur = sec.get("layout")
    if cur == lay:
        return sec
    if lay == "symbole" and sec.get("bullets"):
        sec["points"] = to_points(sec.pop("bullets"))
    elif lay in ("liste", "fazit") and sec.get("points") and not sec.get("bullets"):
        sec["bullets"] = [p["title"] + (f": {p['text']}" if p.get("text") else "") for p in sec.pop("points")][:MAX_BULLETS]
    elif lay == "kernaussage" and not sec.get("quote"):
        first = (sec.get("bullets") or [p["title"] for p in sec.get("points") or []] or [""])[0]
        if not first:
            return sec
        sec["quote"] = first
    if not has(sec, lay):
        return sec
    sec["layout"] = lay
    return sec


def vary_written(sections):
    """vary() over the finished slides, changing only what convert() can change without losing text."""
    want = [s.get("layout") or "liste" for s in sections]
    new = vary(want, lambda i, x: x in ("symbole", "liste", "fazit") and (has(sections[i], x) or
               (x == "symbole" and bool(sections[i].get("bullets"))) or (x in ("liste", "fazit") and bool(sections[i].get("points")))))
    return [convert(s, lay) if lay != s.get("layout") else s for s, lay in zip(sections, new)]


# ---------------------------------------------------------------- 2. less text
BREAK = re.compile(r"\s+[–—-]\s+|[,;:(]\s*")


def shorten(t, most):
    """At most `most` words: at a natural break (comma, dash, colon) when there is one early enough, else the
    first words with "…"."""
    t = str(t or "")
    words = t.split()
    if len(words) <= most:
        return t
    best = ""
    for m in BREAK.finditer(t):
        part = t[:m.start()].strip()
        if 2 <= _words(part) <= most:
            best = part
    return best or " ".join(words[:most]).rstrip(",;:") + " …"


def too_long(sec):
    """What breaks the slide rules: [description] for the one more try of the model."""
    out = []
    bl = sec.get("bullets") or []
    if len(bl) > MAX_BULLETS:
        out.append(f"{len(bl)} Stichpunkte (höchstens {MAX_BULLETS})")
    out += [f"Stichpunkt „{b[:60]}“ hat {_words(b)} Wörter (höchstens {MAX_WORDS})" for b in bl if _words(b) > MAX_WORDS]
    for p in sec.get("points") or []:
        if _words(p.get("title")) > TITLE_WORDS or _words(p.get("text")) > POINT_WORDS:
            out.append(f"Punkt „{p.get('title', '')[:40]}“ zu lang")
    for p in sec.get("steps") or []:
        if _words(p.get("text")) > POINT_WORDS:
            out.append(f"Schritt „{p.get('label', '')[:40]}“ zu lang")
    if sec.get("paras") and sum(_words(x) for x in sec["paras"]) > 30:
        out.append("zu viel Fließtext auf der Folie (gehört in notes)")
    return out


def tighten(sec):
    """The hard rule after the model's second try: extra points and long text into the notes, short at breaks."""
    moved = []
    bl = sec.get("bullets") or []
    if len(bl) > MAX_BULLETS:
        moved += bl[MAX_BULLETS:]
        bl = bl[:MAX_BULLETS]
    short = []
    for b in bl:
        s = shorten(b, MAX_WORDS)
        if s != b:
            moved.append(b)
        short.append(s)
    if bl or "bullets" in sec:
        sec["bullets"] = short
    for p in sec.get("points") or []:
        t, x = shorten(p.get("title", ""), TITLE_WORDS), shorten(p.get("text", ""), POINT_WORDS)
        if (t, x) != (p.get("title", ""), p.get("text", "")):
            moved.append(f"{p.get('title', '')}: {p.get('text', '')}".strip(": "))
        p["title"], p["text"] = t, x
    for p in sec.get("steps") or []:
        x = shorten(p.get("text", ""), POINT_WORDS)
        if x != p.get("text", ""):
            moved.append(f"{p.get('label', '')}: {p.get('text', '')}")
        p["text"] = x
    if sec.get("paras") and sum(_words(x) for x in sec["paras"]) > 30:
        moved += sec["paras"]
        sec["paras"] = [shorten(sec["paras"][0], 25)]
    if moved:
        sec["notes"] = (sec.get("notes", "") + "\n" + "\n".join(f"• {m}" for m in moved)).strip()[:1500]
    return sec


# ---------------------------------------------------------------- 6. facts: numbers only with a source
NUM = re.compile(r"(?<![\w.,])\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d+)?|(?<![\w.,])\d+(?:[.,]\d+)?")
CENTURY = re.compile(r"\s*\.?\s*(jh\b|jahrhundert|century|th century)", re.I)
# a small number is a count ("3 Gründe") unless a unit or a range makes it a measurement ("5–10 km", "8 %")
UNIT = re.compile(r"\s*(?:[–—-]|bis\b|to\b|%|‰|°|€|\$|£|prozent|percent|km|m\b|cm|mm|m²|m³|kg|g\b|t\b|l\b|"
                  r"mio|mrd|million|milliard|billion|tausend|thousand|grad|kw|mw|gw|ps\b|h\b|std|min\b|sek|jahr|year|"
                  r"tag|day|monat|month|woche|week|mal\b|x\b|euro|dollar)", re.I)
RANGE_BEFORE = re.compile(r"(?:[–—-]|\bbis|\bto)\s*$", re.I)


def _norm(tok):
    """A number as its digits (separators and a leading zero do not count): "133.000" → "133000", "5,5" → "55"."""
    d = re.sub(r"\D", "", tok).lstrip("0")
    return d or "0"


def numbers(t):
    """The numbers of a text that need a source: [(as written, digits)]."""
    out = []
    t = str(t or "")
    for m in NUM.finditer(t):
        tok = m.group(0).strip()
        if re.fullmatch(r"\d+", tok) and int(tok) <= SMALL and not UNIT.match(t[m.end():]) and \
                not RANGE_BEFORE.search(t[max(0, m.start() - 5):m.start()]):
            continue
        if re.fullmatch(r"\d{1,2}", tok) and CENTURY.match(t[m.end():]):
            continue
        out.append((tok, _norm(tok)))
    return out


def known(*texts):
    """The digits of all numbers in the material (with small ones, so "3" in a sentence counts anyway)."""
    out = set()
    for t in texts:
        for m in NUM.finditer(str(t or "")):
            out.add(_norm(m.group(0)))
            for part in re.split(r"[.,  ]", m.group(0)):   # "5,5" also backs "5" (rounded, as written there)
                if part:
                    out.add(_norm(part))
    return out


def _texts(sec):
    """(place, text) of everything a reader sees on a section."""
    yield "heading", sec.get("heading", "")
    for k in ("bullets", "paras"):
        for i, x in enumerate(sec.get(k) or []):
            yield f"{k}.{i}", x
    if sec.get("quote"):
        yield "quote", sec["quote"]
    for i, s in enumerate(sec.get("stats") or []):
        yield f"stats.{i}", s.get("value", "") + " " + s.get("label", "")
    for i, p in enumerate(sec.get("points") or []):
        yield f"points.{i}", p.get("title", "") + " " + p.get("text", "")
    for i, p in enumerate(sec.get("steps") or []):
        yield f"steps.{i}", p.get("label", "") + " " + p.get("text", "")
    for side in ("left", "right"):
        c = (sec.get("compare") or {}).get(side) or {}
        for i, x in enumerate(c.get("points") or []):
            yield f"compare.{side}.{i}", x
    for i, r in enumerate((sec.get("table") or {}).get("rows") or []):
        yield f"table.{i}", " ".join(r)


def unbacked(sec, have):
    """The numbers on a section that are not in the material: [as written]."""
    out = []
    for _, t in _texts(sec):
        out += [tok for tok, d in numbers(t) if d not in have and tok not in out]
    ch = sec.get("chart") or {}
    for v in [v for s in ch.get("series") or [] for v in s.get("values") or []]:
        if not _value_known(v, have, True):
            out.append(_show(v))
    return out


def _show(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def _value_known(v, have, strict=False):
    """A chart value is in the material (strict: a small one too; a chart is a measurement)."""
    v = float(v)
    if not strict and v.is_integer() and abs(v) <= SMALL:
        return True
    cands = {_norm(_show(abs(v))), _norm(f"{abs(v):.1f}"), _norm(f"{abs(v):.2f}")}
    return bool(cands & have)


def drop_unbacked(sec, have, fallback_heading=""):
    """Takes out what carries a number without a source; returns how many things went."""
    gone = 0

    def bad(t):
        return any(d not in have for _, d in numbers(t))
    if bad(sec.get("heading", "")):
        sec["heading"] = fallback_heading or re.sub(r"\s*\d[\d.,]*\s*", " ", sec["heading"]).strip()
        gone += 1
    for k in ("bullets", "paras"):
        if sec.get(k):
            keep = [x for x in sec[k] if not bad(x)]
            gone += len(sec[k]) - len(keep)
            sec[k] = keep
    if sec.get("quote") and bad(sec["quote"]):
        sec.pop("quote")
        gone += 1
    for k, f in (("stats", lambda s: s.get("value", "") + " " + s.get("label", "")),
                 ("points", lambda p: p.get("title", "") + " " + p.get("text", "")),
                 ("steps", lambda p: p.get("label", "") + " " + p.get("text", ""))):
        if sec.get(k):
            keep = [x for x in sec[k] if not bad(f(x))]
            gone += len(sec[k]) - len(keep)
            sec[k] = keep
            if not keep:
                sec.pop(k)
    cmp_ = sec.get("compare")
    if cmp_:
        for side in ("left", "right"):
            c = cmp_.get(side) or {}
            keep = [x for x in c.get("points") or [] if not bad(x)]
            gone += len(c.get("points") or []) - len(keep)
            c["points"] = keep
    tb = sec.get("table")
    if tb:
        keep = [r for r in tb.get("rows") or [] if not bad(" ".join(r))]
        gone += len(tb.get("rows") or []) - len(keep)
        tb["rows"] = keep
        if not keep and not tb.get("head"):
            sec.pop("table")
    return gone


def check_chart(sec, have, origins):
    """3. The chart stays only with at least 3 values, not all the same, each in the material. Then it gets the
    source (the origin that holds most of its values) and the key value (the model's or the biggest). Else its
    backed values become big numbers, or it goes. Returns what happened: "ok", "zahlen", "weg" or ""."""
    ch = sec.get("chart")
    if not ch:
        return ""
    vals = [v for s in ch.get("series") or [] for v in s.get("values") or []]
    first = (ch.get("series") or [{}])[0].get("values") or []
    good = len(first) >= MIN_CHART_VALUES and len(set(first)) > 1 and all(_value_known(v, have, True) for v in vals)
    if good:
        best, most = "", 0
        for name, nums in origins:
            n = sum(1 for v in vals if _value_known(v, nums, True))
            if n > most:
                best, most = name, n
        ch["source"] = best
        labels = ch.get("labels") or []
        hl = ch.get("highlight")
        if hl not in labels and first:
            hl = labels[max(range(len(first)), key=lambda i: first[i])] if labels else ""
        ch["highlight"] = hl or ""
        return "ok"
    sec.pop("chart")
    labels = ch.get("labels") or []
    backed = [(labels[i] if i < len(labels) else "", v) for i, v in enumerate(first) if _value_known(v, have, True)]
    if backed and not sec.get("stats"):
        sec["stats"] = [{"value": _show(v).replace(".", ","), "label": lab} for lab, v in backed[:3]]
        return "zahlen"
    return "weg"
