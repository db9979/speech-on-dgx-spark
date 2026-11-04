"""Silence never becomes words (fixed rule, no switch).

Speech recognition models write something even when nobody spoke: after an answer the app listens
again, hears a click, its own chime or the room, and the recording comes back as "Ja", "Okay" or
"Untertitel im Auftrag des ZDF". That word then went to the assistant as a question nobody asked.
A fixed rule here decides from the recording itself, before the text counts:

1. Silence: less than MIN_VOICED seconds of the recording are louder than the room → no question,
   whatever the recognition wrote (it also does not need to run).
2. Known phrases of silence: the whole text is one of the sentences models write for silence or
   noise (subtitle credits, "Danke fürs Zuschauen") → no question. Nobody asks the Spark that.
3. A lone short word ("Ja", "Okay", "Danke", "Hm") from a recording with less than FILLER_VOICED
   seconds of voice → no question. A spoken "Ja" is longer than that, so a real yes still counts.
4. The recognition's own hint text read back: with Namen fürs Hören (hoerwoerter.py) the recognition gets a
   list of names ("db, sb, Hans, …, Pool Pump 1, …"); from noise or a quiet room it sometimes writes that list
   back as the text (Dominik 2026-11-04: the list arrived eight times as his question). A text that is mostly
   names of that list (at least ECHO_ITEMS of them, ECHO_SHARE of its parts) → no question. A sentence that
   names one or two devices ("Schalte Pool Pump 1 und Pool Light 1 ein") still counts.

Only numbers about loudness are computed, the audio is not kept. Applies to every caller of
/api/test/asr (app, browser, guests): the decision leaks nothing about anybody."""
import re

import numpy as np

SR = 16000
WIN = SR * 30 // 1000      # 30 ms frames
MIN_LEVEL = 0.005          # quieter than about -46 dBFS is never voice
OVER_FLOOR = 3.0           # voice is this many times louder than the room (20th percentile of the frames)
MAX_GATE = 0.03            # about -30 dBFS always counts as voice (a recording that is speech from end to end)
MIN_VOICED = 0.1           # seconds of voice below which a recording is silence
FILLER_VOICED = 0.2        # seconds of voice a lone short word needs
FILLERS = {"ja", "jaja", "jo", "jep", "okay", "ok", "oke", "okey", "hm", "hmm", "mhm", "ähm", "äh", "ah", "oh",
           "nein", "ne", "nee", "danke", "tschüss", "yes", "yeah", "yep", "no", "thanks", "bye", "uh", "um",
           "so", "gut", "na", "und", "the", "you"}
SILENCE_PHRASES = (
    r"untertitel(ung)? (im auftrag|des|der|von)\b.*", r"(vielen )?dank (fürs|für's|für das) zus(c)?hauen",
    r"copyright\b.*", r".*amara\.org.*", r"thanks? (you )?for watching", r"please subscribe\b.*", r"subtitles? by\b.*",
)
ECHO_ITEMS = 3             # names of the hint list a read-back has at least
ECHO_SHARE = 0.6           # share of the text's parts that are names of the hint list
ECHO_WORDS = 8             # a read-back without commas: at least this many words ...
ECHO_WORD_SHARE = 0.9      # ... nearly all of them words of the hint list
_PHRASE = re.compile(r"^(?:%s)$" % "|".join(SILENCE_PHRASES), re.I)
_NOISE = re.compile(r"^\W*[\[(*♪]+\s*(musik|music|stille|silence|applaus|applause|lachen|laughter|geräusche?|noise)?\s*[\])*♪]+\W*$", re.I)


def voiced_seconds(x):
    """Seconds of a 16 kHz float recording that are clearly louder than its own quietest part."""
    x = np.asarray(x, dtype=np.float32)
    x = x[:len(x) - len(x) % WIN]
    if not len(x):
        return 0.0
    e = np.sqrt(np.mean(x.reshape(-1, WIN) ** 2, axis=1))
    gate = max(MIN_LEVEL, min(MAX_GATE, float(np.percentile(e, 20)) * OVER_FLOOR))
    return float(np.count_nonzero(e > gate)) * WIN / SR


def _plain(text):
    return " ".join(re.findall(r"[\wäöüß.']+", str(text or "").lower())).strip(" .")


def lone_filler(text):
    """The text is just one short filler word (or that word twice)."""
    w = re.findall(r"[\wäöüß]+", str(text or "").lower())
    return 0 < len(w) <= 2 and len(set(w)) == 1 and w[0] in FILLERS


def _items(text):
    return [x for x in (" ".join(re.findall(r"[\wäöüß'\-]+", p.lower())) for p in re.split(r"[,;.\n]", str(text or ""))) if x]


def context_echo(text, ctx):
    """The text is the recognition's hint list (ctx) read back, or a cut-off piece of it."""
    if not ctx or not text:
        return False
    known = set(_items(ctx))
    parts = _items(text)
    hits = sum(1 for p in parts if p in known)
    if hits >= ECHO_ITEMS and hits >= ECHO_SHARE * len(parts):
        return True
    vocab = {w for k in known for w in k.split()}
    words = " ".join(parts).split()
    return len(words) >= ECHO_WORDS and sum(1 for w in words if w in vocab) >= ECHO_WORD_SHARE * len(words)


def check(text, voiced, ctx=""):
    """Why this recording is no question ("silence", "silence phrase", "too short", "context echo"), or None.
    voiced=None (unreadable audio) only checks the text; ctx is the hint text the recognition got."""
    if voiced is not None and voiced < MIN_VOICED:
        return "silence"
    t = str(text or "").strip()
    if not t:
        return None
    if _PHRASE.match(_plain(t)) or _NOISE.match(t):
        return "silence phrase"
    if context_echo(t, ctx):
        return "context echo"
    if voiced is not None and voiced < FILLER_VOICED and lone_filler(t):
        return "too short"
    return None


def measure(data):
    """Seconds of voice in an uploaded recording, None when it cannot be read (then only the text counts)."""
    try:
        import speakers
        return voiced_seconds(speakers.decode(data))
    except Exception:
        return None


def note(reason, client):
    """The journal line for a dropped recording: the reason and the kind of device, never the text."""
    print(f"chat: ignored ({reason}) from {re.sub(r'[^a-z0-9]', '', str(client))[:12] or 'device'}", flush=True)
    try:
        import live
        live.mark("Spracherkennung", "Stille überhört, kein Wort weitergegeben")
    except Exception:
        pass
