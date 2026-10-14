"""Fälle (plan einstellungs-assistent.md, Punkte 11, 12, 16): every problem becomes a case the moment it happens.

One capture for the whole Spark, read by the Einstellungs-Assistent (berater.py: a proposal for each case) and meant
for „Probleme melden“ as well (frage-vor-meldung.md uses the same triggers and the same fingerprint):

    automatic   a tool failed, an error in the request (language model, speech output …), a question no rule
                recognized ended in the web search, a fixed refusal sentence in the answer ("kann ich nicht"), the same
                question twice within 5 minutes after such an answer, the answer check held a figure back
    by people   👎 under an answer (five reasons and a short text), "Das war falsch" right after an answer,
                „Falsch zugeordnet …“ on Funktionen → Weiche
    by melders  the Einstellungs-Assistent's fixed detectors (berater.py) add a case of kind "melder"

Capturing is fixed rules only and never asks a model (milliseconds, at the end of a turn). A case keeps the
fingerprint (kind + group + tool or error, never words), counts, the request ids (Logs → Anfragen) and at most three
examples. The words of a question are kept only when the person reported it with "Frage mitschicken" (👎) or allowed
its name in Logs → Anfragen (Ich → Gespräch, trace_name); never from a guest, never an answer made from outside text.

👍 is counted only (per day, group and tool): no case. With consent its question becomes a protected sentence
("bestätigt gut"): a proposal that would sort it differently is red in the Prüfstand (berater.py).

Who: cases need the admin switch chat.berater; 👍/👎 and "Das war falsch" the switch chat.bewerten plus the profile's
own switch rate_on (both off), guests never. Files: STATE/faelle.json (30 days, 1000 cases), STATE/bewertungen.json
(counts, 31 days), STATE/gut-saetze.json (200). The recent turns (for 👍/👎 and the repeat rule) only in memory,
24 hours, 400 at most.
"""
import hashlib
import json
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import write_json
from core import assistant, json_body

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
KEEP_S = 30 * 86400
MAX_CASES = 1000
MAX_EXAMPLES = 3
MAX_NOTES = 3
MAX_GOOD = 200
CODEWORD = "[Codewort]"   # homeassistant.redact puts this where the code word was
RECENT_S = 24 * 3600
BEHIND = 2          # the speech output fell behind this often in one answer: a case "aussetzer"
ABORT_MIN = 3       # a stopped answer is only worked on once the same kind of question was stopped this often
MAX_RECENT = 400
REPEAT_S = 300
PHRASE_S = 600
COUNT_DAYS = 31
MAX_Q = 300
MAX_NOTE = 200
ID = re.compile(r"[0-9a-f]{8}")
RID = re.compile(r"[0-9a-f]{12}")
TOOL = re.compile(r"[a-z][a-z0-9_]{1,40}")
CODE = re.compile(r"[a-z0-9_]{1,30}")
GROUP = re.compile(r"[a-z+]{1,40}")

# kinds of cases: key -> (German, English, art)   art: auto / person / melder
KINDS = {
    "tool": ("Werkzeug gescheitert", "Tool failed", "auto"),
    "fehler": ("Fehler in der Anfrage", "Error in the request", "auto"),
    "unklar": ("Unklar, dann Websuche", "Unclear, then web search", "auto"),
    "absage": ("Wunsch ohne Funktion", "Wish without a function", "auto"),
    "doppelt": ("Gleiche Frage zweimal", "Same question twice", "auto"),
    "pruefung": ("Antwortprüfung griff", "Answer check held back", "auto"),
    "abbruch": ("Antwort abgebrochen", "Answer stopped", "auto"),
    "aussetzer": ("Aussetzer in der Sprachausgabe", "Gaps in the speech output", "auto"),
    "erfunden": ("Erfundenes vermutet", "Made-up suspected", "auto"),   # systemone.check_answer, from CHECK_MIN
    "schlecht": ("👎 gemeldet", "👎 reported", "person"),
    "weiche": ("Falsch zugeordnet", "Wrongly sorted", "person"),
    "melder": ("Befund", "Finding", "melder"),
}
# the answer begins with a no (the Befund's „Antwort widerspricht“, befund.py): fixed words only
NEG = re.compile(r"(?i)\W*(nein\b|no\b|leider (nicht|kein|nichts)|ich (habe|hab|finde|fand|sehe) (dazu |da |hier )?(nichts|keine?)\b|"
                 r"es gibt (dazu )?(keine?|nichts)\b|(da|dazu) (ist|steht|liegt) nichts|"
                 r"i (did not|didn't|could not|couldn't|can't) find|there (is|are) no\b)")
# „Hätte nachsehen sollen in …“ under 👎 (plan vorschlaege-besser.md, V4): chip -> (German, English, tools it means)
SOLL = {
    "dokumente": ("in meinen Dokumenten", "in my documents", ("document_search",)),
    "erstellt": ("in erstellten Dokumenten", "in documents the Spark made", ("document_status", "remarkable_sent")),
    "kalender": ("im Kalender", "in the calendar", ("calendar_events",)),
    "mail": ("in den Mails", "in the mails", ("mail_list", "mail_search")),
    "geraete": ("bei den Geräten", "at the devices", ("home_assistant_states", "home_assistant")),
    "erinnerung": ("bei den Erinnerungen", "in the reminders", ("reminder_list",)),
    "web": ("im Web", "on the web", ("web_search",)),
    "verlauf": ("in früheren Gesprächen", "in earlier conversations", ("history_search",)),
}
# the reasons under 👎: key -> (German, English)
REASONS = {"werkzeug": ("falsches Werkzeug", "wrong tool"), "antwort": ("falsche Antwort", "wrong answer"),
           "langsam": ("zu langsam", "too slow"), "verstanden": ("nicht verstanden", "not understood"),
           "aussprache": ("falsch ausgesprochen", "mispronounced")}
STATUS = ("neu", "vorschlag", "lokal", "issue", "erledigt", "verworfen")
# fixed refusal sentences in the answer (frage-vor-meldung d): they only make a case, nothing else
REFUSAL = re.compile(r"(?i)\b(kann ich (leider |noch |dir |dir leider |dir noch )?nicht|habe (leider )?keinen zugriff|"
                     r"(ist|wäre) (leider )?nicht möglich|dafür habe ich keine (funktion|möglichkeit)|"
                     r"i can(no|')t do that|i (do not|don't) have access)\b")
# "Das war falsch" / "Gut so" right after an answer: the person's whole message, fixed words
_BAD = re.compile(r"(?i)^\s*(nein,?\s*)?(das|es)\s+(war|ist)\s+(falsch|nicht richtig|verkehrt)\s*[.!]*\s*$|"
                  r"^\s*falsche antwort\s*[.!]*\s*$|^\s*that was wrong\s*[.!]*\s*$")
_GOOD = re.compile(r"(?i)^\s*(gut so|passt so|richtig so|das war (gut|richtig)|genau richtig|that was (good|right))"
                   r"\s*[.!]*\s*$")
_lock = threading.Lock()
_recent = {}          # rid -> summary of a finished turn (memory only)
_counts = {"days": None, "dirty": False, "flushed": 0.0}


def _file(name):
    return os.path.join(STATE, name)


def wanted(c=None):
    """Turns are summed up at all (cases or 👍/👎 possible)."""
    c = features.chat_cfg() if c is None else c
    return features.admin_on("berater", c)


def can_rate(uid, c=None):
    return bool(uid) and features.allowed("bewerten", uid, c)


# ---------------------------------------------------------------- the fingerprint (shared with „Probleme melden“)
def fingerprint(kind, group="", tool="", code=""):
    """Kind + group + tool or error: never words, so the same problem lands on one case."""
    return "|".join((kind, group or "-", tool or code or "-"))


def _norm(q):
    return re.sub(r"[^a-zäöüß0-9 ]", "", re.sub(r"\s+", " ", str(q or "").lower())).strip()[:200]


def _hash(q):
    return hashlib.sha256(_norm(q).encode()).hexdigest()[:16] if _norm(q) else ""


# ---------------------------------------------------------------- one finished turn
def summary(tr, who, ask, said, outside=False, now=None, off=False):
    """What a finished turn leaves for cases and 👍/👎: fixed words and numbers from the trace record (tracelog.Rec),
    the question only in memory (and only kept with a case when allowed, see _consent)."""
    now = time.time() if now is None else now
    if CODEWORD in str(ask or ""):   # a sentence with the smart-home code word: never kept, never „gleich zweimal“
        ask = ""
    steps = list(getattr(tr, "steps", None) or [])
    tools = [(s["n"], (s.get("x") or {}).get("ok", True)) for s in steps
             if s.get("k") == "tool" and not (s.get("x") or {}).get("panel") and TOOL.fullmatch(str(s.get("n")))]
    held = sum(int((s.get("x") or {}).get("held") or 0) for s in steps if s.get("k") == "check")
    label = str(getattr(tr, "intent", "") or "unklar")
    marks = dict(getattr(tr, "marks", None) or {})
    behind = sum(int((s.get("x") or {}).get("behind") or 0) for s in steps if s.get("k") == "tts")
    # for the Befund (befund.py): tool names only (offered, had to be called, found nothing) and whether the answer
    # said „nein / nichts“ (fixed words), never the answer itself
    names = lambda xs: [n for n in xs if isinstance(n, str) and TOOL.fullmatch(n)][:60]   # noqa: E731
    empty = [s["n"] for s in steps if s.get("k") == "tool" and (s.get("x") or {}).get("empty")]
    return {"t": now, "who": who and who.get("id"), "kind": getattr(tr, "kind", "guest"), "client": getattr(tr, "client", "other"),
            "group": label if GROUP.fullmatch(label) else "unklar", "tools": tools[:12],
            "errors": [e for e in (getattr(tr, "errors", None) or []) if CODE.fullmatch(e)][:5],
            "held": held, "sound": marks.get("sound"), "end": marks.get("end"),
            "trace": tr.id if getattr(tr, "persist", False) else "", "q": str(ask or "")[:MAX_Q],
            "h": _hash(ask), "refusal": bool(REFUSAL.search(str(said or "")[:2000])), "outside": bool(outside), "vote": None,
            "behind": behind, "off": bool(off), "offered": names(getattr(tr, "offered", None) or []),
            "need": names(getattr(tr, "need", None) or []), "empty": names(empty)[:12],
            "neg": bool(NEG.match(str(said or "")[:300]))}


def triggers(s, before=None):
    """The automatic cases of one turn by fixed rules: [(kind, tool, code)]."""
    out = []
    for name, ok in s["tools"]:
        if not ok:
            out.append(("tool", name, ""))
    for code in s["errors"]:
        out.append(("fehler", "", code))
    if s["group"] == "unklar" and any(n == "web_search" for n, _ in s["tools"]):
        out.append(("unklar", "web_search", ""))
    failed = any(k in ("tool", "fehler") for k, _, _ in out)
    # a function that is only switched off: the hint under the answer (and „Funktionen vorschlagen“) says so, no case
    if s["refusal"] and not failed and s["group"] != "plaudern" and not s["outside"] and not s.get("off"):
        out.append(("absage", "", ""))
    if s["held"]:
        out.append(("pruefung", "", ""))
    if s.get("behind", 0) >= BEHIND:   # the speech output fell behind the text more than once (Aussetzer)
        out.append(("aussetzer", "", "tts_behind"))
    if before and before.get("bad") and s["h"] and before.get("h") == s["h"]:
        out.append(("doppelt", "", ""))
    return out


def _last_of(who, now, skip=None, within=REPEAT_S):
    best = None
    for rid, x in _recent.items():
        if rid != skip and x.get("who") == who and now - x["t"] <= within and (best is None or x["t"] > best[1]["t"]):
            best = (rid, x)
    return best


def turn_end(tr, who, ask, said, outside=False, now=None, off=False):
    """Called once when an answer is done (chat.py events). Returns the id for 👍/👎 when the person may rate, else
    None. Never raises."""
    try:
        c = features.chat_cfg()
        if tr is None or not wanted(c):
            return None
        now = time.time() if now is None else now
        s = summary(tr, who, ask, said, outside, now, off)
        rid = secrets.token_hex(6)
        with _lock:
            prev = _last_of(s["who"], now) if s["who"] else None
            _recent[rid] = s
            _trim(now)
        found = triggers(s, prev[1] if prev else None)
        s["bad"] = any(k in ("tool", "absage") for k, _, _ in found)
        for kind, tool, code in found:
            add(kind, s, tool=tool, code=code, now=now)
        return rid if can_rate(s["who"], c) else None
    except Exception as e:
        print("faelle:", type(e).__name__, flush=True)
        return None


def aborted(tr, who, ask, now=None):
    """The person stopped an answer after its first sound (barge-in, stop): a case "abbruch" (fixed rules, never a
    model; proposals only from ABORT_MIN on). Called from chat.py when a turn ends early. Never raises."""
    try:
        if tr is None or not wanted() or (getattr(tr, "marks", None) or {}).get("sound") is None:
            return None
        s = summary(tr, who, ask, "", False, now)
        return add("abbruch", s, now=now)
    except Exception as e:
        print("faelle:", type(e).__name__, flush=True)
        return None


def _trim(now):
    for rid in [r for r, x in _recent.items() if now - x["t"] > RECENT_S]:
        _recent.pop(rid, None)
    while len(_recent) > MAX_RECENT:
        _recent.pop(next(iter(_recent)))


def _consent(uid, asked=False):
    """The words of a question may stay with a case: the person sent them with 👎 itself, or allowed its name in
    Logs → Anfragen. Guests never."""
    if not uid:
        return False
    return asked or profiles.settings(uid).get("trace_name") is True


# ---------------------------------------------------------------- cases
def _read():
    try:
        with open(_file("faelle.json")) as f:
            d = json.load(f)
        rows = d.get("cases") if isinstance(d, dict) else None
        return [x for x in rows if isinstance(x, dict) and ID.fullmatch(str(x.get("id")))] if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _write(rows):
    os.makedirs(STATE, exist_ok=True)
    write_json(_file("faelle.json"), {"cases": rows})


def _keep(rows, now):
    rows = [x for x in rows if now - float(x.get("last", x.get("t", 0))) <= KEEP_S]
    for x in rows:   # kept before V01.0.4xx: a sentence with the code word loses its words
        x["examples"] = [{k: v for k, v in e.items() if not (k == "q" and CODEWORD in str(v))}
                         for e in x.get("examples", []) if isinstance(e, dict)]
    return rows[-MAX_CASES:]


def add(kind, s, tool="", code="", grund="", note="", asked=False, melder="", title="", want="", own=False, now=None,
        soll=""):
    """A case of `kind` from a turn summary `s` (or {} for a melder): a new one, or the open one with the same
    fingerprint counts up. `want`: the group the sentence belongs in (Weiche, „Falsch zugeordnet“); `own`: the
    sentence is the admin's own (typed on Funktionen → Weiche, kept). Returns the case."""
    if kind not in KINDS:
        raise ValueError("kind")
    now = time.time() if now is None else now
    s = s or {}
    group = s.get("group") or ""
    group = group if GROUP.fullmatch(group) else ""
    tool = tool if TOOL.fullmatch(tool or "") else ""
    code = code if CODE.fullmatch(code or "") else ""
    melder = melder if CODE.fullmatch(melder or "") else ""
    grund = grund if grund in REASONS else ""
    want = want if GROUP.fullmatch(want or "") and "+" not in want else ""
    fp = fingerprint(kind, group, tool or melder or want, code or grund)
    who = s.get("who")
    ex = {"t": round(now, 1), "trace": s.get("trace") or "", "client": s.get("client") or ""}
    if "offered" in s:      # the Befund's facts of this turn: tool names and yes/no only (befund.facts)
        import befund
        ex["f"] = befund.facts(s)
    if isinstance(s.get("sound"), (int, float)) and not isinstance(s.get("sound"), bool):
        ex["sound"] = int(s["sound"])   # ms to the first sound (a number only; stopped answers, Punkt 11)
    if s.get("q") and CODEWORD not in s["q"] and (own or _consent(who, asked)) and not s.get("outside"):
        ex["q"] = s["q"][:MAX_Q]
    with _lock:
        rows = _keep(_read(), now)
        case = next((x for x in rows if x.get("fp") == fp and x.get("status") in ("neu", "vorschlag")), None)
        if case is None:
            case = {"id": secrets.token_hex(4), "t": round(now, 1), "fp": fp, "kind": kind, "art": KINDS[kind][2],
                    "group": group, "tool": tool, "code": code, "grund": grund, "melder": melder,
                    "title": str(title or "")[:120], "want": want, "n": 0, "who": [], "examples": [], "notes": [], "status": "neu",
                    "pid": ""}
            rows.append(case)
        case["n"] = int(case.get("n", 0)) + 1
        case["last"] = round(now, 1)
        if who and who not in case["who"] and len(case["who"]) < 20:
            case["who"].append(who)
        case["examples"] = (case.get("examples", []) + [ex])[-MAX_EXAMPLES:]
        note = re.sub(r"\s+", " ", str(note or "")).strip()[:MAX_NOTE]
        if note and note.isprintable():
            case["notes"] = (case.get("notes", []) + [note])[-MAX_NOTES:]
        if title:
            case["title"] = str(title)[:120]
        if want:
            case["want"] = want
        if soll in SOLL:    # the person's chip: counted per chip, the most named one is the case's expectation
            c = case.setdefault("soll", {})
            c[soll] = int(c.get(soll, 0)) + 1
        _write(rows)
    if kind == "melder":   # a detector of the Einstellungs-Assistent: its name and its fixed sentence (berater.melders)
        said = re.sub(r"[^\w ,.:()%-]", "", str(title or "-"))[:100]
        print(f"faelle: melder {melder or '-'} | {said} | {group or '-'} | {tool or '-'} | {case['n']}× | "
              f"Fall {case['id']} (Zustand → Verbessern)", flush=True)
    else:
        print(f"faelle: {kind} | {group or '-'} | {tool or code or melder or grund or '-'} | {case['n']}×", flush=True)
    _live_mark(kind)
    try:
        import berater
        berater.wake()
    except Exception:
        pass
    return case


def cases(now=None):
    with _lock:
        return _keep(_read(), time.time() if now is None else now)


def get(cid):
    return next((x for x in cases() if x["id"] == cid), None)


def set_want_tool(cid, tool):
    """The admin's „Erwartetes Werkzeug“ for a case (befund.expected); one tool, the case starts over as „neu“."""
    if not TOOL.fullmatch(str(tool)):
        raise ValueError("tool")
    with _lock:
        rows = _read()
        case = next((x for x in rows if x["id"] == cid), None)
        if not case:
            return None
        case["want_tool"] = [tool]
        case["status"] = "neu"
        _write(rows)
    return case


def set_status(cid, status, pid=None):
    if status not in STATUS:
        raise ValueError("status")
    with _lock:
        rows = _read()
        case = next((x for x in rows if x["id"] == cid), None)
        if not case:
            return None
        case["status"] = status
        if status in ("erledigt", "verworfen", "issue", "lokal"):
            case["done"] = round(time.time(), 1)
        if pid is not None:
            case["pid"] = pid
        _write(rows)
        return case


def drop_count(cid):
    """A 👎 taken back: one less; a case that came only from it is dropped."""
    with _lock:
        rows = _read()
        case = next((x for x in rows if x["id"] == cid), None)
        if not case:
            return
        case["n"] = max(0, int(case.get("n", 1)) - 1)
        if not case["n"] and case.get("status") in ("neu", "vorschlag"):
            case["status"] = "verworfen"
        _write(rows)


# ---------------------------------------------------------------- 👍 / 👎
def _days():
    if _counts["days"] is None:
        try:
            with open(_file("bewertungen.json")) as f:
                d = json.load(f)
            _counts["days"] = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _counts["days"] = {}
    return _counts["days"]


def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _count(s, good, step, now):
    days = _days()
    day = days.setdefault(_day(now), {"g": {}, "t": {}})
    i = 0 if good else 1
    for part, keys in (("g", [s.get("group") or "unklar"]), ("t", sorted({n for n, _ in s.get("tools", [])}))):
        for k in keys:
            row = day.setdefault(part, {}).setdefault(k, [0, 0])
            row[i] = max(0, row[i] + step)
    oldest = _day(now - COUNT_DAYS * 86400)
    for old in [d for d in days if d <= oldest]:
        days.pop(old, None)
    _counts["dirty"] = True
    if time.monotonic() - _counts["flushed"] >= 30:
        _flush()


def _flush():
    if not _counts["dirty"]:
        return
    try:
        os.makedirs(STATE, exist_ok=True)
        write_json(_file("bewertungen.json"), _counts["days"])
        _counts["dirty"] = False
        _counts["flushed"] = time.monotonic()
    except OSError as e:
        print("faelle: Bewertungen nicht gespeichert", type(e).__name__, flush=True)


def quota(days=7, now=None, part="g"):
    """{group or tool: [good, bad]} over the last `days` days."""
    now = time.time() if now is None else now
    keep = {_day(now - i * 86400) for i in range(days)}
    out = {}
    with _lock:
        for day, d in _days().items():
            if day not in keep or not isinstance(d, dict):
                continue
            for k, row in (d.get(part) or {}).items():
                if isinstance(row, list) and len(row) == 2:
                    o = out.setdefault(k, [0, 0])
                    o[0] += int(row[0])
                    o[1] += int(row[1])
    return out


def _good_read():
    try:
        with open(_file("gut-saetze.json")) as f:
            d = json.load(f)
        return [x for x in d if isinstance(x, dict) and isinstance(x.get("q"), str)] if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def good_sentences():
    """The questions people liked (with consent) and the group the switch gave them: [{"q", "want"}]."""
    with _lock:
        return [{"q": x["q"], "want": x.get("want", "")} for x in _good_read() if CODEWORD not in x["q"]]


def _good_add(s, now):
    if not s.get("q") or not _consent(s.get("who")) or s.get("outside"):
        return
    want = "" if s.get("group") == "unklar" else s.get("group", "")
    if want == "plaudern":
        return
    rows = [x for x in _good_read() if _norm(x["q"]) != _norm(s["q"])]
    rows.append({"q": s["q"][:200], "want": want, "t": round(now)})
    write_json(_file("gut-saetze.json"), rows[-MAX_GOOD:])


def rate(rid, uid, good, grund="", note="", with_q=False, now=None, soll=""):
    """One person's 👍 or 👎 for one of their answers (changeable). Returns {"vote", "case"}."""
    now = time.time() if now is None else now
    with _lock:
        s = _recent.get(rid)
        if not s or s.get("who") != uid or now - s["t"] > RECENT_S:
            raise KeyError(rid)
        before = s.get("vote")
        if before == ("gut" if good else "schlecht") and not note and not grund:
            return {"vote": before, "case": s.get("case")}
        if before:
            _count(s, before == "gut", -1, now)
        s["vote"] = "gut" if good else "schlecht"
        _count(s, good, 1, now)
        old_case = s.get("case")
        if good:
            s["case"] = None
            try:
                _good_add(s, now)
            except OSError:
                pass
    if good and old_case:
        drop_count(old_case)
    case = None
    if not good:
        c = add("schlecht", dict(s, q=s["q"] if with_q else ""), tool=_tool_of(s, grund), grund=grund, note=note,
                asked=with_q, now=now, soll=soll if soll in SOLL else "")
        case = c["id"]
        with _lock:
            if rid in _recent:
                _recent[rid]["case"] = case
    _live_mark("gut" if good else "schlecht")
    if s.get("trace"):   # the thumb on its request in Zustand → Logs → Anfragen (tracelog.vote)
        try:
            import tracelog
            tracelog.vote(s["trace"], "gut" if good else "schlecht", grund, case, now)
        except OSError as e:
            print("faelle: Bewertung nicht an der Anfrage", type(e).__name__, flush=True)
    return {"vote": "gut" if good else "schlecht", "case": case}


def _tool_of(s, grund):
    """The tool a 👎 is about: for "falsches Werkzeug" the one that ran (the first), else none."""
    if grund == "werkzeug" and s.get("tools"):
        return s["tools"][0][0]
    return ""


def phrase(text):
    """"gut" / "schlecht" when the whole message is a fixed rating sentence, else None."""
    t = str(text or "")[:80]
    if _BAD.match(t):
        return "schlecht"
    if _GOOD.match(t):
        return "gut"
    return None


def by_phrase(uid, verdict, now=None):
    """"Das war falsch" / "Gut so": rates the person's last answer of the last 10 minutes. Returns the sentence to say
    (German)."""
    now = time.time() if now is None else now
    if not can_rate(uid):
        return "Bewerten geht für dich gerade nicht. " + features.missing_text("bewerten", uid)
    with _lock:
        last = _last_of(uid, now, within=PHRASE_S)
    if not last:
        return "Ich finde keine Antwort der letzten Minuten, die ich notieren könnte."
    try:
        rate(last[0], uid, verdict == "gut", grund="antwort" if verdict == "schlecht" else "", now=now)
    except KeyError:
        return "Ich finde keine Antwort der letzten Minuten, die ich notieren könnte."
    return "Danke, ich habe es notiert." if verdict == "schlecht" else "Danke, freut mich."


# ---------------------------------------------------------------- Live (counts only)
_live = {"day": "", "n": {}}


def _live_mark(kind):
    day = _day(time.time())
    if _live["day"] != day:
        _live.update(day=day, n={})
    _live["n"][kind] = _live["n"].get(kind, 0) + 1


def for_live(now=None):
    """Today: 👍, 👎 and new cases (numbers only)."""
    day = _day(time.time() if now is None else now)
    n = _live["n"] if _live["day"] == day else {}
    return {"gut": n.get("gut", 0), "schlecht": n.get("schlecht", 0),
            "faelle": sum(v for k, v in n.items() if k in KINDS)}


# ---------------------------------------------------------------- endpoint: 👍 / 👎 under an answer
@router.post("/api/chat/rate", dependencies=[Depends(assistant)])
async def post_rate(request: Request):
    """{id, good, grund?, text?, frage?, soll?}: the person's own vote for one of their answers of the last 24 hours."""
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(403, "Bewerten gibt es nur mit Profil.")
    guard.limit(request, "rate", prof["id"])
    b = await json_body(request, 2048)
    if not RID.fullmatch(str(b.get("id"))) or not isinstance(b.get("good"), bool):
        raise HTTPException(400, "id and good")
    if not can_rate(prof["id"]):
        raise HTTPException(403, "Bewerten ist aus.")
    grund = b.get("grund") if b.get("grund") in REASONS else ""
    note = b.get("text") if isinstance(b.get("text"), str) else ""
    if len(note) > MAX_NOTE or (note and not note.replace("\n", " ").isprintable()):
        raise HTTPException(400, f"text: höchstens {MAX_NOTE} Zeichen")
    if not b["good"] and _day_bad(prof["id"]) >= 10:
        raise HTTPException(429, "Heute höchstens 10 Meldungen.")
    try:
        res = rate(b["id"], prof["id"], b["good"], grund, note, b.get("frage") is True,
                   soll=b.get("soll") if b.get("soll") in SOLL else "")
    except KeyError:
        raise HTTPException(404, "Diese Antwort ist zu alt oder nicht deine.")
    if not b["good"]:
        _bad_today.setdefault(prof["id"], []).append(time.time())
    return res


_bad_today = {}


def _day_bad(uid):
    now = time.time()
    rows = [t for t in _bad_today.get(uid, []) if now - t < 86400]
    _bad_today[uid] = rows
    return len(rows)

