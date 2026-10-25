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


_ER = re.compile(r"\b(er|sie|he|she)\b")
_SEX = {"er": "maennlich", "he": "maennlich", "sie": "weiblich", "she": "weiblich"}


def _after(low, b):
    """The words right after a quote when a comma follows it („…“, warnt er leise), up to the next quote."""
    if not low[b:b + 3].lstrip().startswith(","):
        return ""
    x = low[b:b + NACH]
    cut = min([i for i in (x.find(q) for q in "„\"»“") if i > 0] or [len(x)])
    return x[:cut]


def around(text, a, b):
    """The words that say how a quote is spoken: those right after it („…“, flüstert er mit archaischer Stimme) or
    the clause right before it when it ends in a colon (Kael zischt: „…“), else ""."""
    low = str(text).lower()
    before = re.split(r"[.!?…“”\"»«]", low[max(0, a - VOR):a])[-1]
    return _after(low, b) or (before if before.rstrip().endswith(":") else "")


def pronoun(text, b):
    """The gender the words after a quote give its speaker („…“, warnt er leise: maennlich), else ""."""
    m = _ER.search(_after(str(text).lower(), b))
    return _SEX[m.group(1)] if m else ""


def _speaker(text, a, b, names, sex_of=None):
    """Who says the quote text[a:b]: a name right after it („…“, sagt Grimma), else the last one named before it
    whose gender does not contradict the pronoun after the quote („…“, warnt er: no woman, Dominik 2026-10-24 „wurde
    von einer Frauenstimme gesagt - er ist aber männlich“), one whose kept gender is that of the pronoun first."""
    low = text.lower()
    after = _after(low, b)
    hit = [(after.find(n), n) for n in names if n and after.find(n) >= 0]
    if hit:
        return min(hit)[1]
    p = pronoun(text, b)
    before = low[max(0, a - VOR):a]
    hit = [(bool(p and sex_of and sex_of(n) == p), before.rfind(n), n) for n in names if n and before.rfind(n) >= 0
           and not (p and sex_of and sex_of(n) not in ("", p))]
    return max(hit)[2] if hit else ""


def rede(text, names, sex_of=None):
    """The narration as [(speaker, piece, quoted, gender, around)]: plain narration with speaker "", every quote with
    the name of who says it (lower case, one of names) or "" when nobody is named, the gender of the pronoun after it
    ("maennlich", "weiblich" or "") for its voice, and the words around it that say how it is spoken (around).
    sex_of(name) gives a name's gender or "". A quote that only goes on (no name after it, no pronoun, nobody named
    since the last quote: »Kein Fremder hier«, sagt er heiser. »Nur Schatten.«) keeps the last quote's speaker and
    gender (Dominik 2026-10-25 „die stimme war weiblich obwohl er genannt ist“)."""
    text = str(text or "")
    low = text.lower()
    names = sorted({str(n).strip().lower() for n in names if str(n).strip()}, key=len, reverse=True)
    out, i, last = [], 0, None
    for m in _REDE.finditer(text):
        said = next(x for x in m.groups() if x).strip()
        if not re.search(r"\w", said):
            continue
        plain = text[i:m.start()].strip(" ,:–-")
        if re.search(r"\w", plain):
            out.append(("", plain, False, "", ""))
        wer, sex = _speaker(text, m.start(), m.end(), names, sex_of), pronoun(text, m.end())
        if last and not sex and not any(n in _after(low, m.end()) for n in names) \
                and not any(n in low[last[2]:m.start()] for n in names):
            wer, sex = last[0], last[1]
        out.append((wer, said, True, sex, around(text, m.start(), m.end())))
        last = (wer, sex, m.end())
        i = m.end()
    rest = text[i:].strip(" ,:–-")
    if re.search(r"\w", rest):
        out.append(("", rest, False, "", ""))
    return out


def in_text(line, text):
    """Whether an NPC's line already stands in the narration's quotes, as one quote or split in several („Ihr versteht
    es nicht“, stammelt er, „es ist ein Gefängnis.“): then it is read once, at its place, and not shown again
    (Dominik 2026-10-24 „beim vorlesen der npc sagst du die namen mit“)."""
    w = lambda s: " " + re.sub(r"[^\w]+", " ", str(s).lower()).strip() + " "
    said = w(" ".join(x[1] for x in rede(text, []) if x[2]))
    return w(line).strip() != "" and w(line) in said
