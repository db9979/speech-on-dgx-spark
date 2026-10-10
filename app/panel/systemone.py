"""Einordnung mit Wahrscheinlichkeit (V01.0.340): qwen38's POST /v1/systemone for a few fixed questions.

dgx-spark-qwen38 (not ours, proxy v6.19 / qwen38 v1.15 and later) answers typed questions about a text
("state") with probabilities instead of words: a choice from fixed options, a score on fixed levels or a
yes/no. "jev-latest" is only a name there: the Qwen3.8 lane that already runs answers, one token per
question, so it needs no memory of its own and nothing leaves the machine.

Here the model only gives numbers; the panel decides with fixed thresholds what they mean. The questions
and options are fixed in the code, never from outside text. The text being judged (a person's own
message, the head of a mail, a test answer) is data: qwen38 fences it with a token drawn at its start, and
here it is cut to MAX_STATE characters. Only the stored chat.llm_url and key are used (no address from a
request), no redirects, at most MAX_BYTES back, short timeouts. When qwen38 is busy (529), too old (404)
or slow, the caller goes on as without it.

Uses, each with its own admin switch below chat.systemone (all off) and the profile's systemone_on:
  weiche     Gezielte Werkzeugwahl, chat.route_model "systemone": a question no rule recognizes
  mail       Postfach aufräumen, stage 4 (chat.systemone_tidy)
  wichtig    Von selbst melden: important mail by sender and subject (chat.systemone_mail, pro_mail_smart)
  qualitaet  Qualitätstest: a second opinion per case, shown only, never pass or fail (chat.systemone_quality)

Logs ("systemone:" lines) and Zustand → Live carry only the use, the pick, numbers and times, never text.
"""
import json
import re
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import guard
from common import load_config
from core import auth

router = APIRouter()
MODEL = "jev-latest"
MAX_STATE = 4000              # characters of the text being judged
MAX_QUESTIONS = 8
MAX_OPTIONS = 40
MAX_BYTES = 64 * 1024         # of the answer
NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
USES = {"weiche": "Werkzeugwahl", "mail": "Postfach aufräumen", "wichtig": "Wichtige Mail",
        "qualitaet": "Qualitätstest", "test": "Prüfen"}
# the panel's thresholds (Dominik 2026-10-10: "wie empfohlen")
ROUTE_MIN = 0.80              # the switch narrows only from here
TIDY_SURE = 90                # mail tidying moves by itself only from here (percent), else it asks
WICHTIG_MIN = 0.80            # an important mail is said from here
_lock = threading.Lock()
_count = {}                   # per day: use -> n, "busy", "fail", "ms" (sum)
_last = {}                    # use -> (time, ok, ms)
_transport = None             # the self-tests put an httpx.MockTransport here


class Unavailable(Exception):
    """qwen38 gave no usable answer (busy, too old, slow, refused); `why` is a fixed word."""

    def __init__(self, why):
        super().__init__(why)
        self.why = why


def endpoint(ccfg):
    """The stored LLM address with /systemone, or "" (only http(s), as Einstellungen → Sprachmodell keeps it)."""
    url = str(ccfg.get("llm_url") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[^\s/?#]+(/[^\s?#]*)?", url):
        return ""
    return url + "/systemone"


def _headers(ccfg):
    h = {"Content-Type": "application/json"}
    if ccfg.get("llm_key"):
        h["Authorization"] = f"Bearer {ccfg['llm_key']}"
    return h


def clean_state(text):
    """The text being judged: control characters out, at most MAX_STATE characters."""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(text or ""))
    return t[:MAX_STATE]


def choice(instructions, options):
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def score(instructions, levels):
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def noul(instructions):
    return {"type": "noul", "instructions": instructions}


def body(state, questions):
    """The request: the questions are the panel's own (checked here), the state is data."""
    if not isinstance(questions, dict) or not 0 < len(questions) <= MAX_QUESTIONS:
        raise ValueError("questions")
    for name, q in questions.items():
        if not NAME.fullmatch(name) or not isinstance(q, dict) or q.get("type") not in ("choice", "score", "noul"):
            raise ValueError("question " + str(name)[:32])
        crit = q.get("criteria")
        if q["type"] == "choice" and not (isinstance(crit, dict) and 1 < len(crit) <= MAX_OPTIONS
                                           and all(NAME.fullmatch(k) for k in crit)):
            raise ValueError("choice " + name)
        if q["type"] == "score" and not (isinstance(crit, list) and 1 < len(crit) <= 10):
            raise ValueError("score " + name)
    return {"model": MODEL, "state": clean_state(state), "questions": questions}


def _p(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0 else None


def parse(data, questions):
    """{name: {"pick", "p", "probs"} | {"yes"} | {"score", "probs"}} for exactly the questions asked; anything
    missing, outside 0..1 or naming an option that was not offered makes the whole answer unusable."""
    ans = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(ans, dict):
        raise Unavailable("ohne Antwort")
    out = {}
    for name, q in questions.items():
        a = ans.get(name)
        if not isinstance(a, dict):
            raise Unavailable("unvollständig")
        if q["type"] == "noul":
            p = _p(a.get("noul"))
            if p is None:
                raise Unavailable("unlesbar")
            out[name] = {"yes": p}
            continue
        probs = a.get("probabilities")
        keys = list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]
        if not isinstance(probs, dict) or set(probs) - set(keys):
            raise Unavailable("unlesbar")
        probs = {k: _p(probs.get(k, 0.0)) for k in keys}
        if any(v is None for v in probs.values()):
            raise Unavailable("unlesbar")
        if q["type"] == "choice":
            pick = max(keys, key=lambda k: probs[k])
            out[name] = {"pick": pick, "p": probs[pick], "probs": probs}
        else:
            s = sum(int(k) * v for k, v in probs.items())
            out[name] = {"score": round(s, 3), "probs": probs, "top": int(max(keys, key=lambda k: probs[k]))}
    return out


def _read(r):
    if r.status_code == 529 or r.status_code == 503:
        raise Unavailable("ausgelastet")
    if r.status_code in (404, 405):
        raise Unavailable("fehlt (qwen38 älter als v1.15?)")
    if r.status_code in (401, 403):
        raise Unavailable("Schlüssel abgelehnt")
    if r.status_code != 200:
        raise Unavailable(f"HTTP {r.status_code}")
    raw = r.content
    if len(raw) > MAX_BYTES:
        raise Unavailable("Antwort zu groß")
    try:
        return json.loads(raw)
    except ValueError:
        raise Unavailable("unlesbar")


def _note(use, ok, ms, why=""):
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _count.get("day") != day:
            _count.clear()
            _count["day"] = day
        if ok:
            _count[use] = _count.get(use, 0) + 1
            _count["ms"] = _count.get("ms", 0) + ms
        else:
            _count["busy" if why == "ausgelastet" else "fail"] = _count.get("busy" if why == "ausgelastet" else "fail", 0) + 1
        _last[use] = (time.time(), ok, ms)
    print(f"systemone: {USES.get(use, use)} " + (f"{ms} ms" if ok else f"nicht genutzt ({why}), weiter ohne"), flush=True)
    if not ok:
        try:
            import live
            if live.on():
                live.event("Einordnung", f"{USES.get(use, use)}: {why}, weiter ohne")
        except Exception:
            pass


def _prep(ccfg, use, state, questions):
    if use not in USES:
        raise ValueError("use")
    url = endpoint(ccfg)
    if not url:
        raise Unavailable("keine Adresse")
    return url, body(state, questions)


async def ask(ccfg, use, state, questions, timeout=4.0):
    """The parsed answers, or Unavailable. For the conversation itself: never waits for speech."""
    url, payload = _prep(ccfg, use, state, questions)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=2), follow_redirects=False,
                                     trust_env=False, transport=_transport) as c:
            r = await c.post(url, json=payload, headers=_headers(ccfg))
        out = parse(_read(r), questions)
    except Unavailable as e:
        _note(use, False, 0, e.why)
        raise
    except (httpx.HTTPError, OSError) as e:
        why = "zu langsam" if isinstance(e, httpx.TimeoutException) else "nicht erreichbar"
        _note(use, False, 0, why)
        raise Unavailable(why)
    _note(use, True, int((time.monotonic() - t0) * 1000))
    return out


def ask_sync(ccfg, use, state, questions, timeout=20.0, job=""):
    """The same from a worker thread (mail tidying); with `job` it first waits while somebody speaks."""
    url, payload = _prep(ccfg, use, state, questions)
    if job:
        import vorrang
        vorrang.hold(job)
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=5), follow_redirects=False, trust_env=False,
                          transport=_transport) as c:
            r = c.post(url, json=payload, headers=_headers(ccfg))
        out = parse(_read(r), questions)
    except Unavailable as e:
        _note(use, False, 0, e.why)
        raise
    except (httpx.HTTPError, OSError) as e:
        why = "zu langsam" if isinstance(e, httpx.TimeoutException) else "nicht erreichbar"
        _note(use, False, 0, why)
        raise Unavailable(why)
    _note(use, True, int((time.monotonic() - t0) * 1000))
    return out


def for_live(now=None):
    """Zustand → Live: how often today, per use, and how often it was busy or failed. Numbers only."""
    day = time.strftime("%Y-%m-%d", time.localtime(now or time.time()))
    with _lock:
        c = dict(_count) if _count.get("day") == day else {}
    uses = {k: c.get(k, 0) for k in USES if k != "test"}
    n = sum(uses.values())
    return {"n": n, "uses": uses, "busy": c.get("busy", 0), "fail": c.get("fail", 0),
            "ms": round(c.get("ms", 0) / n) if n else 0}


# ---------------------------------------------------------------- the fixed questions of each use
def route_question(names, labels):
    """The switch (intent.py): one choice from the groups plus "unklar"."""
    opts = {n: labels.get(n, n) for n in names}
    opts["unklar"] = "passt zu keiner Gruppe oder ist eine allgemeine Frage oder Plauderei"
    return {"absicht": choice("Worum bittet die Person mit dieser Nachricht? Wähle die Gruppe der Werkzeuge, die sie braucht.",
                              opts)}


def route_pick(ans, names, minimum=ROUTE_MIN):
    """(pick or None, p): only a group of the list, never "unklar", only from `minimum` on."""
    a = ans.get("absicht") or {}
    pick, p = a.get("pick"), a.get("p") or 0.0
    return (pick if pick in names and p >= minimum else None), p


TIDY_OPTIONS = {
    "wichtig": "persönlich, von einem Menschen, Arbeit, Behörde, Bank, Versicherung, Gesundheit, Schule, Verein mit "
               "persönlichem Bezug, alles, was der Empfänger wahrscheinlich selbst lesen will",
    "werbung": "Angebote, Rabatte, Shops",
    "newsletter": "abonnierte Infos, Blogs, Neuigkeiten",
    "rechnungen": "Rechnungen, Bestellungen, Versand, Buchungen",
    "benachrichtigungen": "automatische Hinweise von Apps und Konten",
    "social": "soziale Netzwerke",
}


def tidy_question():
    return {"kategorie": choice("In welche Kategorie gehört diese E-Mail?", TIDY_OPTIONS)}


def wichtig_question():
    return {"wichtig": noul("Diese E-Mail ist persönlich oder dringend und der Empfänger will sicher gleich davon "
                            "erfahren (keine Werbung, kein Newsletter, keine automatische Benachrichtigung).")}


QUALITY_LEVELS = ["beantwortet die Frage nicht", "beantwortet die Frage teilweise", "beantwortet die Frage vollständig"]


def quality_questions():
    return {"passt": score("Wie gut beantwortet die Antwort die Frage mit den Werkzeugergebnissen?", QUALITY_LEVELS),
            "erfunden": noul("Die Antwort nennt Angaben (Zeiten, Namen, Beträge, Termine), die weder in der Frage noch "
                             "in den Werkzeugergebnissen stehen.")}


# ---------------------------------------------------------------- Funktionen → Einordnung → Prüfen (admin)
TEST_SENTENCE = "Mach bitte das Licht im Wohnzimmer aus."


@router.post("/api/admin/systemone/test", dependencies=[Depends(auth)])
async def admin_test(request: Request):
    """One question of the switch through /v1/systemone with the stored address: whether qwen38 answers, how
    fast, and what it picks. The admin's own sentence (at most 500 characters) or a fixed one; nothing stored."""
    guard.limit(request, "systemone", admin=True)
    try:
        b = await request.json()
    except ValueError:
        b = {}
    text = b.get("text") if isinstance(b, dict) else None
    if text is not None and (not isinstance(text, str) or len(text) > 500):
        raise HTTPException(400, "text: höchstens 500 Zeichen")
    text = (text or "").strip() or TEST_SENTENCE
    import intent
    ccfg = load_config().get("chat", {})
    names = list(intent.INTENT_NAMES)
    t0 = time.monotonic()
    try:
        ans = await ask(ccfg, "test", text, route_question(names, intent.GROUP_SAYS), timeout=15)
    except Unavailable as e:
        return {"ok": False, "why": e.why}
    a = ans["absicht"]
    top = sorted(a["probs"].items(), key=lambda kv: -kv[1])[:3]
    return {"ok": True, "ms": int((time.monotonic() - t0) * 1000), "pick": a["pick"], "p": round(a["p"], 3),
            "top": [[k, round(v, 3)] for k, v in top], "used": a["pick"] != "unklar" and a["p"] >= ROUTE_MIN,
            "sentence": text == TEST_SENTENCE}
