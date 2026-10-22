"""Ins Wort fallen: erst anhalten, dann entscheiden (admin chat.barge_hold, off by default).

Without it a quarter of a second of voice over the answer cut the answer off: a cough, a "mhm" or a "ja, genau"
ended it as well. With it the page (chat.js) and the iPhone app (Assistant.swift) only pause the answer and record
as before; the model keeps writing behind. The recording comes to /api/test/asr with "hold", and the panel decides
here with a fixed rule, never the model (idea from sonia-assistant, plan "Ins Wort fallen und Satzende am Tonfall"):

1. "weiter": nothing heard, the own voice (echo.py), a voice that is not the profile's (fremdstimme.py), silence
   (stille.py) or only words that tell "I am listening" (BACK: "mhm", "ja", "okay", "genau" …). The answer plays on
   where it stopped.
2. "stopp": only words that say stop (STOP: "Stopp", "Halt", "Ruhe", "Danke, reicht" …). The answer ends, what was
   spoken stays.
3. "frage": anything else. The answer ends, what was spoken stays, and the sentence is the new question. After an
   answer that ended on a question ("asked") even "ja" is an answer and counts as a question.

The page plays on by itself when no decision comes within HOLD_MAX seconds (recognition down or slow). Only the
decision and its fixed reason go to the journal and to Live, never the words."""
import json
import re

HOLD_MAX = 4   # seconds the page waits for a decision before the answer plays on (chat.js, Assistant.swift)
MAX_WORDS = 4  # a longer recording is always a question
BACK = {"mhm", "mhmm", "hm", "hmm", "aha", "ah", "äh", "ähm", "ehm", "oh", "ja", "jaja", "jo", "ok", "okay", "oke", "okey",
        "genau", "richtig", "stimmt", "gut", "schön", "klar", "verstehe", "ach so", "alles klar", "ja genau", "na klar",
        "uh-huh", "uh huh", "uhhuh", "yes", "yeah", "yep", "right", "sure", "i see", "got it", "cool", "nice", "um", "uh"}
STOP = {"stopp", "stop", "halt", "ruhe", "still", "sei still", "hör auf", "aufhören", "schluss", "genug", "reicht",
        "das reicht", "es reicht", "danke reicht", "abbrechen", "abbruch", "enough", "that's enough", "be quiet", "quiet",
        "shut up", "cancel", "stop it"}
CALL = {"spark", "jarvis", "computer", "hey", "hallo"}   # the wake words may stand in front: "Spark, stopp"
WHY = {"leer": "nothing heard", "ueberhoert": "ignored voice", "rueckmeldung": "listening words",
       "stoppwort": "stop words", "rueckfrage": "answer to a question", "satz": "a sentence"}
LIVE = {"weiter": "Angehalten, läuft weiter", "stopp": "Angehalten, gestoppt", "frage": "Angehalten, neue Frage"}


def on(uid):
    """The admin released it and this profile may use it (never guests)."""
    import features
    return bool(uid) and features.allowed("anhalten", uid)


def _words(text):
    return re.findall(r"[\wäöüß'-]+", str(text or "").lower())[:MAX_WORDS + 1]


def _cover(words, phrases):
    """The phrases (one or two words each) the words are made of, read from the left; None when a word is left over."""
    got, i = [], 0
    while i < len(words):
        two = " ".join(words[i:i + 2])
        if i + 1 < len(words) and two in phrases:
            got.append(two)
            i += 2
        elif words[i] in phrases:
            got.append(words[i])
            i += 1
        else:
            return None
    return got


def decide(text, ignored="", asked=False):
    """(decision, reason): decision "weiter", "stopp" or "frage", reason a key of WHY."""
    if ignored:
        return "weiter", "ueberhoert"
    words = _words(text)
    if not words:
        return "weiter", "leer"
    if len(words) > MAX_WORDS:
        return "frage", "satz"
    got = _cover(words, STOP | BACK | CALL)
    if got and any(p in STOP for p in got):
        return "stopp", "stoppwort"
    if got and any(p in BACK for p in got):
        return ("frage", "rueckfrage") if asked else ("weiter", "rueckmeldung")
    return "frage", "satz"


def note(decision, why, client=""):
    """The journal line and the Live event: the decision and its fixed reason, never the words."""
    dev = re.sub(r"[^a-z0-9]", "", str(client))[:12] or "device"
    print(f"hoeren: zwischenruf {decision} | {WHY.get(why, why)} | from {dev}", flush=True)
    try:
        import live
        live.mark("Ins Wort fallen", LIVE[decision])
    except Exception:
        pass


def attach(res, uid, asked=False, client=""):
    """The answer of /api/test/asr with the decision added ("barge"); left as it was when it is no recognition
    (an error: the page plays on by itself) or the profile may not use it."""
    if not on(uid):
        return res
    got = res
    if not isinstance(res, dict):
        if getattr(res, "status_code", 0) != 200:
            return res
        try:
            got = json.loads(bytes(res.body))
        except (ValueError, TypeError, AttributeError):
            return res
        if not isinstance(got, dict):
            return res
    decision, why = decide(got.get("text"), got.get("ignored") or "", asked)
    note(decision, why, client)
    return dict(got, barge=decision)
