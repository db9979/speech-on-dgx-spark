"""Rückfrage, Korrektur und Merken (Dominik 2026-10-12, Plan plaene/rueckfrage-und-merken.md).

When a tool the panel runs itself cannot tell which thing is meant ("Fernseher im Wohnzimmer" fits two
devices, "Glotze im Keller" fits none), it does not guess and does not leave it to the model: it asks the
person, with the candidates as buttons (at most four) or the whole list to pick from, and takes the answer
by fixed rules (a button, a number, the name). After it carried out the choice it offers to remember it:
only after a plain yes the words ("fernseher wohnzimmer") stand for that target in this profile from then
on. "Nein, den anderen" right after an action the panel chose among several candidates takes the action
back (only on/off, open/close, to the state read before) and carries out the right one.

Rules (docs/de/richtlinien.md, Teil 2): the candidates come only from the tool's own data, the question is
a fixed sentence, the model never picks and never writes a mapping. A choice counts only in the same
conversation, from the same profile's own login or recognized voice, within two minutes; it carries the
code word of the command it answers and nothing else. Remembering needs a plain yes within 15 minutes. A
mapping is checked against the tool's data each time it is used. Never for guests; admin switch
chat.klaeren, off, then for every profile the admin did not block; remembering has its own (chat.klaeren_merken). The
journal has fixed words and numbers only, never names of devices, contacts or words people said.
"""
import json
import re
import threading
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from core import assistant, browser_profile

router = APIRouter()

ASK_SECONDS = 120          # a choice answers the question only this long
REMEMBER_SECONDS = 15 * 60 # "Soll ich mir das merken?" waits this long for the yes
MAX_BUTTONS = 4
MAX_LIST = 150
MAX_MAPS = 200
MAX_WORDS = 6
_lock = threading.Lock()

# what a mapping can stand for; every area brings its own targets (providers, registered by the modules)
AREAS = {"ha": ("Smart Home", "Smart home")}
PROVIDERS = {}   # area -> async fn(uid) -> [{"id", "name", "room", "info"}]


def provide(area, de, en, fn):
    AREAS[area] = (de, en)
    PROVIDERS[area] = fn


# areas a tool the model calls resolves itself (Stufe C): area -> (tool name, the argument that names the target)
TOOLS = {}


def tool_area(area, de, en, tool, slot):
    AREAS[area] = (de, en)
    TOOLS[area] = (tool, slot)


def on(uid, c=None, s=None):
    return bool(uid) and features.allowed("klaeren", uid, c, s)


def merken_on(uid, c=None, s=None):
    return on(uid, c, s) and features.allowed("klaerenmerken", uid, c, s)


# ---------------------------------------------------------------- words
_STOP = set("der die das den dem des ein eine einen einem einer im in ist sind am an aus auf zu zum zur vom von beim bei "
            "bitte mal mir mich mein meine meinen meinem ganz doch noch jetzt gleich schnell kurz und oder "
            "schalte schalt schalten mach mache machen stell stelle drehe dreh fahre fahr oeffne schliesse "
            "ein einschalten ausschalten anmachen ausmachen anschalten abschalten hoch runter rauf auf zu "
            "the a an my please turn switch on off set".split())
_NUM = {"eins": 1, "ein": 1, "einen": 1, "erste": 1, "ersten": 1, "erstes": 1, "erster": 1, "1": 1, "one": 1, "first": 1,
        "zwei": 2, "zweite": 2, "zweiten": 2, "zweites": 2, "zweiter": 2, "2": 2, "two": 2, "second": 2,
        "drei": 3, "dritte": 3, "dritten": 3, "drittes": 3, "dritter": 3, "3": 3, "three": 3, "third": 3,
        "vier": 4, "vierte": 4, "vierten": 4, "viertes": 4, "vierter": 4, "4": 4, "four": 4, "fourth": 4}
_NONE = re.compile(r"(?i)^\W*(keins?|keine[nrs]?|nichts davon|keins davon|keines davon|abbrechen|vergiss es|lass es|"
                   r"none|cancel|neither|never mind)\b")
_LIST = re.compile(r"(?i)\b(liste|alle geräte|alle geraete|zeig mir alle|list|show all)\b")
_CORRECT = re.compile(r"(?i)^\W*(nein|nee|falsch|nicht (den|die|das)|ich meinte|ich mein|den anderen|die andere|das andere|"
                      r"no|wrong|i meant|the other)\b")

# the words of a correction itself, left out before reading which device it names
_CORRECT_WORDS = set("nein nee noe falsch nicht ich meinte mein meine meinen meinst eigentlich doch sondern den die das der "
                     "anderen andere anderes no wrong i meant mean the other one not".split())


def _same(a, b):
    """The same conversation on the same kind of device ("client:convo"), exactly: an answer from another
    chat never answers this one's question (the panel's chat names its conversation from the first message on)."""
    return str(a)[:120] == str(b)[:120]


def _norm(t):
    t = str(t or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("_", " "), (".", " ")):
        t = t.replace(a, b)
    return t


def words(text):
    """The words that name the thing, in a fixed order: the key a mapping is stored and found under."""
    t = re.sub(r"(?i)\[codewort\]|\bcode\s*-?\s*wort\b(\s+(ist|lautet))?", " ", str(text or ""))
    ws = [w for w in re.findall(r"[a-z0-9]+", _norm(t)) if len(w) > 1 and w not in _STOP]
    return " ".join(sorted(set(ws))[:MAX_WORDS])


def _forms(w):
    out = [w]
    for end in ("ern", "er", "en", "n", "s", "e"):
        if len(w) - len(end) >= 4 and w.endswith(end):
            out.append(w[:-len(end)])
    return out


def _fits(ws, cand):
    hay = _norm(" ".join([cand.get("name", ""), cand.get("room", ""), str(cand.get("id", ""))]))
    return all(any(f in hay for f in _forms(w)) for w in ws)


def pick(text, cands):
    """The candidate a short answer names: a number ("zwei", "die erste"), or words that fit exactly one
    candidate's name or room. None when it names none or several."""
    t = _norm(text)
    ws = [w for w in re.findall(r"[a-z0-9]+", t) if w not in _STOP and w not in ("den", "die", "das", "nummer", "number")]
    nums = [_NUM[w] for w in ws if w in _NUM]
    if len(nums) == 1 and len(ws) <= 3 and nums[0] <= len(cands):
        return cands[nums[0] - 1]
    ws = [w for w in ws if w not in _NUM and len(w) > 1]
    if not ws:
        return None
    hits = [c for c in cands if _fits(ws, c)]
    if len(hits) == 1:
        return hits[0]
    exact = [c for c in hits if _norm(c.get("name", "")).strip() == " ".join(ws)]
    return exact[0] if len(exact) == 1 else None


# ---------------------------------------------------------------- waiting questions (memory only, short-lived)
_waiting = {}   # uid -> {"kind": "choice"|"remember", ...}
_last = {}      # uid -> the last action the panel chose among several candidates (for "Nein, den anderen")


def _short(c):
    return {"id": str(c["id"])[:200], "name": str(c.get("name") or c["id"])[:60], "room": str(c.get("room") or "")[:40],
            "info": str(c.get("info") or "")[:40]}


def ask(uid, src, area, said, cands, act, code_ok=False, full=False, en=False):
    """Puts one question to the person: which of cands. Returns the chat event (buttons or the whole list).
    act: what to do with the choice (the module's own fixed data, e.g. {"service": "turn_on"})."""
    cands = [_short(c) for c in cands if isinstance(c, dict) and c.get("id")][:MAX_LIST]
    qid = uuid.uuid4().hex[:12]
    with _lock:
        _waiting[uid] = {"kind": "choice", "id": qid, "t": time.time(), "src": str(src)[:120], "area": area,
                         "words": words(said), "said": str(said)[:120], "cands": cands, "act": dict(act or {}),
                         "code_ok": bool(code_ok), "list": bool(full)}
    print(f"klaeren: frage {area} {len(cands)} kandidaten{' liste' if full else ''}", flush=True)
    _count("frage")
    return {"type": "choice", "id": qid, "area": area, "list": bool(full),
            "options": [{"n": i + 1, "label": c["name"], "room": c["room"], "info": c["info"]}
                        for i, c in enumerate(cands if full else cands[:MAX_BUTTONS])],
            "none": "Keins davon" if not en else "None of these"}


def question(cands, said="", en=False, full=False, near=False):
    """The fixed sentence for the question (spoken and shown); names come from the tool's own data.
    near: the candidates fit only some of the words ("Glotze im Dachboden": the TVs, but no attic)."""
    if full or not cands:
        return ("I can't find that exactly. Pick the right one from the list." if en else
                "Das finde ich so nicht. Such dir das Richtige aus der Liste aus.")
    names = [c.get("name", "") for c in cands[:MAX_BUTTONS]]
    lst = ", ".join(names[:-1]) + (" or " if en else " oder ") + names[-1] if len(names) > 1 else names[0]
    if near:
        return (f"I can't find that exactly. Do you mean {lst}?" if en else
                f"Das finde ich so nicht genau. Meinst du {lst}?")
    return (f"Several fit: {lst}. Which one do you mean?" if en else f"Da passen mehrere: {lst}. Welches meinst du?")


def did(uid, src, area, said, chosen, act, before, cands, code_ok=False):
    """The panel carried out act on chosen among several candidates: "Nein, den anderen" may correct it."""
    with _lock:
        _last[uid] = {"t": time.time(), "src": str(src)[:120], "area": area, "words": words(said), "said": str(said)[:120],
                      "chosen": _short(chosen), "act": dict(act or {}), "before": before,
                      "cands": [_short(c) for c in cands][:MAX_LIST], "code_ok": bool(code_ok)}


def offer(uid, src, area, said, target, en=False):
    """Offers to remember that the words stand for target. Returns the question, or "" when nothing to offer."""
    ws = words(said)
    if not ws or not merken_on(uid):
        return ""
    have = lookup(uid, area, ws, touch=False)
    if have and have["id"] == target["id"]:
        return ""
    with _lock:
        _waiting[uid] = {"kind": "remember", "t": time.time(), "src": str(src)[:120], "area": area, "words": ws,
                         "said": str(said)[:120], "target": _short(target)}
    shown = _shown(said)
    return (f"Shall I remember that “{shown}” is {target['name']}?" if en else
            f"Soll ich mir merken, dass „{shown}“ {target['name']} ist?")


def remember_event(area, en=False):
    """The two buttons under "Soll ich mir merken …?"; a tap sends the plain word."""
    return {"type": "choice", "id": uuid.uuid4().hex[:12], "area": area, "list": False, "kind": "remember",
            "options": [{"n": 1, "label": "Ja, merken" if not en else "Yes, remember", "send": "Ja" if not en else "Yes"},
                        {"n": 2, "label": "Nein" if not en else "No", "send": "Nein" if not en else "No"}], "none": ""}


def _shown(said):
    """The person's own words for the question, without the code word and the switching verbs."""
    t = re.sub(r"(?i)\[codewort\]|,?\s*\bcode\s*-?\s*wort\b.*$", "", str(said or ""))
    ws = [w for w in re.findall(r"[\wäöüÄÖÜß]+", t) if _norm(w) not in _STOP or _norm(w) in ("im", "in", "am")]
    while ws and _norm(ws[0]) in ("im", "in", "am"):
        ws.pop(0)
    while ws and _norm(ws[-1]) in ("im", "in", "am", "ein", "an", "aus"):
        ws.pop()
    return " ".join(ws)[:60]


def answer(uid, src, text, own=True):
    """The person's answer to a waiting question of this conversation, by fixed rules:
    {"kind": "choice", "cand", "act", "area", "said", "code_ok", "undo"?}, {"kind": "list", ...}, {"kind": "none"},
    {"kind": "remember", "yes": bool, ...} or None (not an answer: the question lapses when it is something else)."""
    now = time.time()
    text = str(text or "")
    with _lock:
        w = _waiting.get(uid)
        last = _last.get(uid)
    if not own:
        return None
    if w and _same(w["src"], src):
        limit = ASK_SECONDS if w["kind"] == "choice" else REMEMBER_SECONDS
        if now - w["t"] > limit:
            drop(uid)
            w = None
    else:
        w = None
    if w and w["kind"] == "remember":
        import calendars
        if calendars.confirms(text):
            drop(uid)
            return {"kind": "remember", "yes": True, "area": w["area"], "words": w["words"], "said": w["said"],
                    "target": w["target"]}
        if re.match(r"(?i)^\W*(nein|nee|no|lieber nicht|nicht merken|nope)\b", text) and len(text.split()) <= 4:
            drop(uid)
            return {"kind": "remember", "yes": False, "area": w["area"]}
        drop(uid)   # something else: the offer lapses
    elif w and w["kind"] == "choice":
        if len(text.split()) <= 10:
            if _NONE.search(text):
                drop(uid)
                if not w["list"]:   # "keins davon": the whole list next
                    return {"kind": "list", "area": w["area"], "said": w["said"], "act": w["act"], "code_ok": w["code_ok"]}
                return {"kind": "none", "area": w["area"]}
            if _LIST.search(text) and not w["list"]:
                drop(uid)
                return {"kind": "list", "area": w["area"], "said": w["said"], "act": w["act"], "code_ok": w["code_ok"]}
            c = pick(text, w["cands"])
            if c:
                drop(uid)
                _count("auswahl")
                return {"kind": "choice", "cand": c, "act": w["act"], "area": w["area"], "said": w["said"],
                        "code_ok": w["code_ok"], "undo": None}
        drop(uid)   # a new question: the choice lapses
    # "Nein, den anderen": corrects the last action the panel chose among several candidates
    if last and _same(last["src"], src) and now - last["t"] <= ASK_SECONDS and _CORRECT.search(text) \
            and len(text.split()) <= 12:
        others = [c for c in last["cands"] if c["id"] != last["chosen"]["id"]]
        rest = " ".join(w for w in re.findall(r"\w+", _norm(text)) if w not in _CORRECT_WORDS)
        c = pick(rest, others) or (others[0] if len(others) == 1 and re.search(
            r"(?i)\b(andere[nrs]?|other)\b", text) else None)
        if c:
            with _lock:
                _last.pop(uid, None)
            _count("korrektur")
            return {"kind": "choice", "cand": c, "act": last["act"], "area": last["area"], "said": last["said"],
                    "code_ok": last["code_ok"], "undo": {"cand": last["chosen"], "before": last["before"]}}
    return None


# ---------------------------------------------------------------- inside a tool the model called (Stufe C)
def _usable(ctx):
    """Asking and mappings only for the profile's own login or voice, never on outside text (a mail, a page)."""
    who = (ctx or {}).get("who")
    return bool(who and ctx.get("own") and not ctx.get("outside_before", ctx.get("outside")) and on(who["id"]))


def pinned(ctx, area, said):
    """The target the panel fixed for the words a tool got: the person's choice in this turn (only for exactly
    the words of the question), else the profile's mapping for these words. None: the tool resolves as before."""
    pin = (ctx or {}).get("pin")
    if pin and pin.get("area") == area and words(pin.get("said")) == words(said):
        pin["used"] = True   # chat.py offers to remember it afterwards
        return pin["cand"]
    if not _usable(ctx):
        return None
    hit = lookup(ctx["who"]["id"], area, words(said))
    return {"id": hit["id"], "name": hit["name"], "room": hit.get("room", "")} if hit else None


def ask_tool(ctx, area, said, cands, args, en=False, near=False, slot=None):
    """A tool the model called cannot tell which target is meant: asks the person (the buttons go to the chat at
    once) and returns the text for the model, or None when asking is not for this turn (then the tool goes on
    as before). The choice later runs the same tool with the same arguments, the target fixed by the panel."""
    if not _usable(ctx) or len(cands) < 2 or area not in TOOLS:
        return None
    tool, slot = TOOLS[area][0], slot or TOOLS[area][1]
    act = {"tool": tool, "args": {k: v for k, v in dict(args or {}).items() if isinstance(v, (str, int, float, bool))}, "slot": slot}
    ev = ask(ctx["who"]["id"], ctx.get("src") or "", area, said, cands, act, code_ok=bool(ctx.get("code_ok")), en=en)
    out = ctx.get("out")
    if out is not None:
        try:
            out.put_nowait(ev)
        except Exception:
            pass
    return ("Not done yet: the panel asks the person which one is meant. Say exactly this question and nothing "
            "else: «" + question(cands, en=en, near=near) + "» Call no tool.")


def waiting(uid, src):
    with _lock:
        w = _waiting.get(uid)
    return bool(w and _same(w["src"], src))


def drop(uid):
    with _lock:
        _waiting.pop(uid, None)


# ---------------------------------------------------------------- mappings (users/<id>/zuordnungen.json)
def _file(uid):
    return profiles._path(uid, "zuordnungen.json")


def load(uid):
    try:
        with open(_file(uid)) as f:
            rows = json.load(f)
        return [r for r in rows if isinstance(r, dict) and r.get("area") in AREAS and r.get("words") and r.get("id")] \
            if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save(uid, rows):
    rows.sort(key=lambda r: -r.get("last", r.get("since", 0)))
    profiles._write(_file(uid), rows[:MAX_MAPS])


def lookup(uid, area, ws, touch=True):
    """The mapping for exactly these words in this area, or None."""
    if not ws or not on(uid):
        return None
    with _lock:
        rows = load(uid)
        hit = next((r for r in rows if r["area"] == area and r["words"] == ws), None)
        if hit and touch:
            hit["used"] = int(hit.get("used", 0)) + 1
            hit["last"] = int(time.time())
            _save(uid, rows)
    if hit and touch:
        print(f"klaeren: zuordnung genutzt {area}", flush=True)
        _count("genutzt")
    return hit


def remember(uid, area, ws, target, how="chat"):
    with _lock:
        rows = [r for r in load(uid) if not (r["area"] == area and r["words"] == ws)]
        row = {"mid": uuid.uuid4().hex[:12], "area": area, "words": ws, "id": target["id"],
               "name": str(target.get("name") or "")[:60], "room": str(target.get("room") or "")[:40],
               "since": int(time.time()), "used": 0, "how": how}
        rows.append(row)
        _save(uid, rows)
    print(f"klaeren: zuordnung gemerkt {area}", flush=True)
    _count("gemerkt")
    return row


def forget_target(uid, area, target_id):
    """A target that is gone: its mappings go too."""
    with _lock:
        rows = load(uid)
        keep = [r for r in rows if not (r["area"] == area and r["id"] == target_id)]
        if len(keep) != len(rows):
            _save(uid, keep)


# ---------------------------------------------------------------- numbers for Zustand → Live
_stats = {"day": "", "n": {}}


def _count(kind):
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _stats["day"] != day:
            _stats.update(day=day, n={})
        _stats["n"][kind] = _stats["n"].get(kind, 0) + 1


def for_live():
    """Kinds and counts only: questions waiting, choices, mappings remembered and used today."""
    day = time.strftime("%Y-%m-%d")
    with _lock:
        n = dict(_stats["n"]) if _stats["day"] == day else {}
        now = time.time()
        open_ = sum(1 for w in _waiting.values() if now - w["t"] <= (ASK_SECONDS if w["kind"] == "choice" else REMEMBER_SECONDS))
    return {"offen": open_, "fragen": n.get("frage", 0), "auswahl": n.get("auswahl", 0), "korrektur": n.get("korrektur", 0),
            "gemerkt": n.get("gemerkt", 0), "genutzt": n.get("genutzt", 0)}


# ---------------------------------------------------------------- endpoints: Ich → Gedächtnis → Zuordnungen
def _prof(request, write=False):
    """Reading: the profile's login or a device key; changing only in the profile's own browser login."""
    prof = browser_profile(request) if write else profiles.current(request)
    if not prof:
        raise HTTPException(403, "Zuordnungen gibt es nur mit Profil.")
    if not on(prof["id"]):
        raise HTTPException(403, "Rückfrage und Merken ist aus.")
    return prof


async def _body(request, most=2048):
    raw = await request.body()
    if len(raw) > most:
        raise HTTPException(413, "too large")
    try:
        b = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    if not isinstance(b, dict):
        raise HTTPException(400, "object expected")
    return b


def _public(r):
    return {k: r.get(k) for k in ("mid", "area", "words", "id", "name", "room", "since", "used", "last", "how")}


@router.get("/api/profile/zuordnungen", dependencies=[Depends(assistant)])
def get_maps(request: Request):
    prof = _prof(request)
    guard.limit(request, "zuordnung", prof["id"])
    return {"items": [_public(r) for r in load(prof["id"])], "areas": {k: list(v) for k, v in AREAS.items()},
            "pick": [k for k in AREAS if k in PROVIDERS],   # areas whose targets can be listed ("Eigene Namen vergeben")
            "merken": merken_on(prof["id"])}


@router.get("/api/profile/zuordnungen/ziele", dependencies=[Depends(assistant)])
async def get_targets(request: Request, area: str = "ha"):
    """What the profile can map words to in one area (its own devices, contacts ...), for the list."""
    prof = _prof(request)
    guard.limit(request, "zuordnung", prof["id"])
    if area not in PROVIDERS:
        raise HTTPException(404, "unknown area")
    try:
        items = await PROVIDERS[area](prof["id"])
    except Exception as e:   # the service is down: say so, never its text
        print(f"klaeren: ziele {area} nicht lesbar ({type(e).__name__})", flush=True)
        raise HTTPException(502, "Gerade nicht erreichbar.")
    return {"items": [_short(c) for c in items][:MAX_LIST]}


async def _target(uid, area, tid):
    if area not in PROVIDERS:
        raise HTTPException(400, "area")
    try:
        items = await PROVIDERS[area](uid)
    except Exception:
        raise HTTPException(502, "Gerade nicht erreichbar.")
    hit = next((c for c in items if str(c.get("id")) == str(tid)), None)
    if not hit:
        raise HTTPException(400, "Dieses Ziel gibt es nicht.")
    return hit


def _clean_words(raw):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 120 or not raw.isprintable():
        raise HTTPException(400, "Wörter: 1 bis 120 Zeichen")
    ws = words(raw)
    if not ws:
        raise HTTPException(400, "Darin steht kein Wort, das etwas benennt.")
    return ws


@router.post("/api/profile/zuordnungen", dependencies=[Depends(assistant)])
async def add_map(request: Request):
    """{area, words, id}: the profile names one of its own things itself ("Eigene Namen vergeben")."""
    prof = _prof(request, True)
    guard.limit(request, "zuordnungset", prof["id"])
    b = await _body(request)
    area = b.get("area")
    ws = _clean_words(b.get("words"))
    tgt = await _target(prof["id"], area, b.get("id"))
    if len(load(prof["id"])) >= MAX_MAPS and not lookup(prof["id"], area, ws, touch=False):
        raise HTTPException(409, f"Höchstens {MAX_MAPS} Zuordnungen.")
    return _public(remember(prof["id"], area, ws, tgt, how="hand"))


@router.put("/api/profile/zuordnungen/{mid}", dependencies=[Depends(assistant)])
async def change_map(mid: str, request: Request):
    """{words?, id?}: other words or another target."""
    prof = _prof(request, True)
    guard.limit(request, "zuordnungset", prof["id"])
    b = await _body(request)
    rows = load(prof["id"])
    row = next((r for r in rows if r.get("mid") == mid), None)
    if not row:
        raise HTTPException(404, "not found")
    if "words" in b:
        row["words"] = _clean_words(b["words"])
    if "id" in b:
        t = await _target(prof["id"], row["area"], b["id"])
        row.update(id=t["id"], name=str(t.get("name") or "")[:60], room=str(t.get("room") or "")[:40])
    with _lock:
        rows = [r for r in load(prof["id"]) if r.get("mid") != mid and not (r["area"] == row["area"] and r["words"] == row["words"])]
        rows.append(row)
        _save(prof["id"], rows)
    return _public(row)


@router.delete("/api/profile/zuordnungen/{mid}", dependencies=[Depends(assistant)])
def delete_map(mid: str, request: Request):
    prof = _prof(request, True)
    guard.limit(request, "zuordnungset", prof["id"])
    with _lock:
        rows = load(prof["id"])
        keep = [r for r in rows if r.get("mid") != mid]
        if len(keep) == len(rows):
            raise HTTPException(404, "not found")
        _save(prof["id"], keep)
    return {"ok": True}
