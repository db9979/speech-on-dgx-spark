"""Seitenänderung ohne Modell (Idee aus OpenFuse, Dominik 2026-11-15 „1-3“): a watch whose task is a web address
compares the page's lines from one run to the next, by fixed rules, without the language model.

The way of comparing follows OpenFuse's apps/server/src/engine/page-diff.ts (MIT License, Copyright (c) 2026 OpenFuse
contributors), ported to Python and changed for the Spark:
  1. The page is read as Markdown (seitentext through chat.page_text: main part only, no menus); each line is cut to
     LINE characters, blanks squeezed, doubles dropped, at most LINES lines.
  2. Only three short hashes per line are kept (the stand), never the page's text: the line itself, the line with
     times blanked out and the line with every number blanked out.
  3. A line that is still there is no news. A line where only a time changed („vor 5 Minuten“ → „vor 6 Minuten“,
     „18:30“ → „18:45“, a date) is no news either. A line where only a number changed (a price, a stock count, a
     version) is „geändert“. Every other new line is „neu“, every line left over is „weg“ (counted, its text is gone).
     Each old line answers for one new line at most, so one line that stayed never hides another that went.
The panel decides what is news; the page's text is data, it is shown in the note and never read as an instruction.
"""
import hashlib
import re

LINES = 300            # lines kept per page
LINE = 200             # characters per line
SHOW_NEW = 5           # lines named in the report per kind
SHOW_CHANGED = 3

# relative times and times of day / dates change on their own: no news
_TIME = re.compile(
    r"\b(?:\d+|an?|one)\s+(?:sec(?:ond)?|min(?:ute)?|hour|hr|day|week|month|year)s?\s+ago\b|"
    r"\bvor\s+(?:\d+|einer?|einem)\s+(?:sekunde|minute|stunde|tag|woche|monat|jahr)(?:e|en|n)?\b|"
    r"\b(?:heute|gestern|today|yesterday)\b|"
    r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:uhr|am|pm)?\b|"
    r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}\b|(?!\d))|\b\d{4}-\d{2}-\d{2}\b",
    re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_ADDR = re.compile(r"https?://[^\s<>\"'`]{4,400}", re.I)


def address(text):
    """The one web address in the text, when the text is that address or asks for changes of it; else None.
    „https://example.org/news“ or „Sag mir, wenn sich https://example.org/news ändert“ → the address."""
    t = str(text or "").strip()
    found = _ADDR.findall(t)
    if len(found) != 1:
        return None
    url = found[0].rstrip(".,;:!?)»“\"'")
    rest = t.replace(found[0], " ").strip(" .,;:!?\"'„“»«")
    if not rest or re.search(r"(?i)\b(änder\w*|geändert|aktualisiert|neu auf|chang\w*|updated?)\b", rest):
        return url
    return None


def title(url):
    """„Änderungen: example.org/news“ for the list."""
    short = re.sub(r"(?i)^https?://(www\.)?", "", str(url or "")).rstrip("/")
    return ("Änderungen: " + short)[:80]


def lines(text):
    """The page's lines for comparing: blanks squeezed, cut, without doubles, at most LINES."""
    out, seen = [], set()
    for raw in str(text or "").splitlines():
        line = re.sub(r"\s+", " ", _CTRL.sub(" ", raw)).strip(" #*>-|")[:LINE].strip()
        if len(line) < 2 or line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= LINES:
            break
    return out


def _h(text):
    return hashlib.blake2s(text.encode(), digest_size=4).hexdigest()


def _keys(line):
    """(the line, without times, without any number) as three short hashes."""
    timeless = _TIME.sub("<t>", line)
    numberless = re.sub(r"(\w)s\b", r"\1", _NUM.sub("#", timeless)).lower()
    return _h(line), _h(timeless), _h(numberless)


def stand(page_lines):
    """What is kept of a run: one string of three hashes per line (8 characters each)."""
    return ["".join(_keys(x)) for x in page_lines]


def _pair(previous, current, k):
    """previous: [hashes]; current: [(line, keys)]. Each current line takes one unused previous line with the same
    key k. Returns (paired current lines, unpaired current lines, unused previous)."""
    open_ = {}
    for h in previous:
        open_.setdefault(h[k * 8:k * 8 + 8], []).append(h)
    paired, unpaired, used = [], [], []
    for item in current:
        bucket = open_.get(item[1][k])
        if bucket:
            used.append(bucket.pop())
            paired.append(item)
        else:
            unpaired.append(item)
    left = list(previous)
    for h in used:
        left.remove(h)
    return paired, unpaired, left


def compare(previous, page_lines):
    """{"neu": [lines], "geaendert": [lines], "weg": count} against the stand of the last run."""
    current = [(x, _keys(x)) for x in page_lines]
    _, rest, left = _pair(list(previous or []), current, 0)
    _, rest, left = _pair(left, rest, 1)
    changed, new, left = _pair(left, rest, 2)
    return {"neu": [x for x, _ in new], "geaendert": [x for x, _ in changed], "weg": len(left)}


def _lines(n):
    return f"{n} Zeile" if n == 1 else f"{n} Zeilen"


def count(diff):
    return len(diff["neu"]) + len(diff["geaendert"]) + int(diff["weg"])


def summary(diff):
    """„3 neu, 1 geändert, 2 weg“ (fixed words and numbers)."""
    parts = [f"{len(diff['neu'])} neu" if diff["neu"] else "", f"{len(diff['geaendert'])} geändert" if diff["geaendert"] else "",
             f"{diff['weg']} weg" if diff["weg"] else ""]
    return ", ".join(p for p in parts if p)


def report(diff, url):
    """The report of a run with changes: fixed words, the counts and the first new and changed lines."""
    out = [f"Die Seite {url} hat sich geändert: {summary(diff)}."]
    if diff["neu"]:
        out += ["", "Neu:"] + [f"- {x}" for x in diff["neu"][:SHOW_NEW]]
        if len(diff["neu"]) > SHOW_NEW:
            out.append(f"- und {len(diff['neu']) - SHOW_NEW} weitere")
    if diff["geaendert"]:
        out += ["", "Geändert:"] + [f"- {x}" for x in diff["geaendert"][:SHOW_CHANGED]]
        if len(diff["geaendert"]) > SHOW_CHANGED:
            out.append(f"- und {len(diff['geaendert']) - SHOW_CHANGED} weitere")
    if diff["weg"]:
        out += ["", f"Weg: {_lines(diff['weg'])}."]
    return "\n".join(out)


def finds(diff, url):
    """The changes as finds of a watch ({"v", "src", "q"}) for Ich → Aufträge and the note."""
    out = [{"v": "Neu", "src": url, "q": x[:200]} for x in diff["neu"][:SHOW_NEW]]
    out += [{"v": "Geändert", "src": url, "q": x[:200]} for x in diff["geaendert"][:SHOW_CHANGED]]
    if not out and diff["weg"]:
        out.append({"v": "Weg", "src": url, "q": _lines(diff["weg"])})
    return out


def push_text(name, diff, url):
    """(title, body) of the note: fixed words, the counts and the first changed line."""
    first = (diff["neu"] or diff["geaendert"] or [""])[0][:120]
    host = re.sub(r"(?i)^https?://(www\.)?", "", url).split("/")[0][:60]
    body = f"{summary(diff)} ({host})." + (f"\n„{first}“" if first else "") + \
        f"\nEigene Aufgabe „{name[:60]}“ · Öffnen: Ich → Aufträge"
    return f"🔔 Seite geändert: {name.removeprefix('Änderungen: ')[:60]}", body
