"""KI-Dungeon-Master: reading aloud part by part (Punkt 16 and 17 of the review of 2026-10-24, Dominik „das vorlesen
klappt nicht zuverlässig“, „alle vorschläge umsetzten“, „die klingen gleich wie die des erzählers“, „ja, alles so
umsetzten“).

- A turn is read in pieces of one or a few sentences, each its own WAV (STATE/dungeon-ton/<rid>-<n>-<k>.wav). The first
  piece is short, so the first sound comes after a second or two; the seats play the pieces one after the other while
  the next ones are made.
- Every piece gets a second try, then the fixed voice; a piece that still fails is left out and the rest goes on.
- What stands in quotes in the narration is spoken by whoever says it: the person named right after („…“, sagt Grimma)
  or right before it, an NPC in its voice, a hero in its own, anyone else in the NPC voice; never by the narrator.
- While a round reads aloud, its clock waits: the reading time and the turn's time start after the last piece
  (at most SPRICHT_MAX).

Only fixed rules of the panel; the model's text is only cut and matched against names.
"""
import re

TEIL_MIN = 60              # characters: shorter sentences go together into one piece
TEIL_MAX = 240             # characters of one piece at most (a longer sentence is cut at a comma or a space)
ERST_MAX = 140             # the very first piece of a turn: one short sentence, so the first sound comes soon
SPRICHT_MAX = 240          # seconds the clock waits for the reading at most
NACH = 40                  # characters after a quote where „sagt Grimma“ names the speaker
VOR = 120                  # characters before a quote where the speaker may be named

_SATZ = re.compile(r"(?<=[.!?…])[\"“”»«]?\s+")
_REDE = re.compile(r'„([^“”"]+)[“”"]|"([^"]+)"|»([^«]+)«|“([^”]+)”')


def _cut(s, n):
    """A sentence longer than n cut at the last comma (else space) before n."""
    out = []
    while len(s) > n:
        i = max(s.rfind(", ", 0, n), s.rfind("; ", 0, n))
        i = i + 1 if i > n // 3 else (s.rfind(" ", 0, n) if s.rfind(" ", 0, n) > n // 3 else n)
        out.append(s[:i].strip())
        s = s[i:].strip()
    return out + ([s] if s else [])


def saetze(text, first=False):
    """The pieces of one text: sentences, short ones together up to TEIL_MIN, none over TEIL_MAX; with first the
    opening piece is a single sentence of at most ERST_MAX."""
    s = [x for y in _SATZ.split(re.sub(r"\s+", " ", str(text or "")).strip()) for x in _cut(y.strip(), TEIL_MAX) if x]
    out = []
    for x in s:
        if out and len(out[-1]) < TEIL_MIN and len(out[-1]) + 1 + len(x) <= TEIL_MAX and not (first and len(out) == 1):
            out[-1] += " " + x
        else:
            out.append(x)
    if first and out and len(out[0]) > ERST_MAX:
        out[:1] = _cut(out[0], ERST_MAX)
    return [x for x in out if x]


def _speaker(text, a, b, names):
    """Who says the quote text[a:b]: a name right after it when a comma follows the quote („…“, sagt Grimma), else
    the last one named before it."""
    low = text.lower()
    after = low[b:b + NACH] if low[b:b + 3].lstrip().startswith(",") else ""
    hit = [(after.find(n), n) for n in names if n and after.find(n) >= 0]
    if hit:
        return min(hit)[1]
    before = low[max(0, a - VOR):a]
    hit = [(before.rfind(n), n) for n in names if n and before.rfind(n) >= 0]
    return max(hit)[1] if hit else ""


def rede(text, names):
    """The narration as [(speaker, piece, quoted)]: plain narration with speaker "", every quote with the name of who
    says it (lower case, one of names) or "" when nobody is named."""
    text = str(text or "")
    names = sorted({str(n).strip().lower() for n in names if str(n).strip()}, key=len, reverse=True)
    out, i = [], 0
    for m in _REDE.finditer(text):
        said = next(x for x in m.groups() if x).strip()
        if not re.search(r"\w", said):
            continue
        plain = text[i:m.start()].strip(" ,:–-")
        if re.search(r"\w", plain):
            out.append(("", plain, False))
        out.append((_speaker(text, m.start(), m.end(), names), said, True))
        i = m.end()
    rest = text[i:].strip(" ,:–-")
    if re.search(r"\w", rest):
        out.append(("", rest, False))
    return out


def same(a, b):
    """Whether two spoken lines are the same words (an NPC's line that also stands in the narration is read once)."""
    w = lambda s: re.sub(r"[^\w]+", " ", str(s).lower()).strip()
    return w(a) == w(b)
