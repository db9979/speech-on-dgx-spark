"""Bilder malen (plan plaene/bildgenerierung.md, Dominik 2026-10-14 „1c 2a 3a 4a 5a 6a 7a 8b“): pictures from a
wish, painted on the Spark by FLUX.2 [klein] (bild_server.py on 127.0.0.1, image.port).

Ways in: the tool bild_malen in the conversation (the language model writes the English picture prompt from the
person's words, Dominik 4a, shown under the picture) and Ich → Bilder (the person's own sentence goes as it is).
The panel decides everything else with fixed rules: size from the format and image.max_side, 4 steps, one picture
at a time on the whole Spark, at most WAITING waiting, one open job per profile, image.day_limit pictures per
profile in 24 hours, image.store_mb per profile.

Protection (Dominik 5a, fixed rules, no switch): a word list before painting (the wish and the prompt, de and en),
no pictures of people the Spark knows by name (profiles, the profile's contacts), the image check of bild_server
after painting (a fixed threshold NSFW_MAX decides; without the check no picture at all), and every picture
marked as made by an AI (bild_server). Text from outside (mail, web, documents) never starts a picture: bild_malen
is a changing tool, locked after outside text (chat.LOCKED_OUTSIDE via the extras' "changes"), and from Notaus
stage 2 on. Guests never get the tool or the page; a blocked profile only sees „Daten löschen“.

Speech first (vorrang): a job waits until the spoken answer is over, the picture itself runs while nobody speaks.
Storage users/<id>/bilder/<pic>.png and index.json (speicher.AREAS "bilder"). Journal lines start with "bilder:",
fixed words and numbers only: never a wish, a prompt or a name (profiles.log_name)."""
import asyncio
import base64
import os
import re
import secrets
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

import features
import guard
import notaus
import profiles
import wartung
from common import DayCounter, STATE, load_config, model_url
from core import api_headers, assistant, auth, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "bilder"
MAX_WISH = 500
MAX_PROMPT = 1000
MAX_PICS = 300              # pictures per profile, whatever the space
NSFW_MAX = 0.5              # the image check's share above which a picture is thrown away (fixed rule)
WAITING = 10                # open jobs on the whole Spark
JOB_SECONDS = 12 * 60       # waiting for a pause, loading the model and painting
FOLLOW_SECONDS = 10 * 60    # after a picture wish, "noch einmal in Blau" or "ja, fiktiv" is understood without the words
MAX_PNG = 40 * 1024 * 1024
DAY_S = 24 * 3600
ID = re.compile(r"[0-9a-f]{12}")
PNG_SIG = b"\x89PNG\r\n\x1a\n"
CTRL = re.compile(r"[\x00-\x1f\x7f<>\ud800-\udfff]")
# format -> (width share, height share, German, English)
FORMATS = {"quadrat": (1, 1, "Quadrat", "Square"), "quer": (4, 3, "Querformat", "Landscape"),
           "hoch": (3, 4, "Hochformat", "Portrait"), "breit": (16, 9, "Breitbild", "Widescreen")}
TEST_PROMPT = "a red apple on a wooden kitchen table, soft morning light, photo"

# a wish for a picture in the person's own words (the Weiche's group "bild" and offer below); "Was ist auf dem
# Bild?" (Bilder erkennen, images.py) has no painting word and stays there
WORDS = re.compile(
    r"(?i)\b(male|malen|zeichne|zeichnen|skizzier\w*|illustrier\w*|paint|draw)\b"
    r"|^\s*(?:bitte\s+)?mal\s+(?:mir\s+|uns\s+|bitte\s+)*(?:ein|eine|einen)\s+(?!frage\b)\w+"
    r"|\b(erstell\w*|mach\w*|generier\w*|erzeug\w*|entwirf|entwerf\w*|gestalte\w*|create|make|generate|design)\b"
    r".{0,60}\b(bild|bildchen|zeichnung|illustration|logo|malvorlage|ausmalbild|poster|grafik|hintergrundbild|"
    r"wallpaper|avatar|picture|image|drawing|illustration|coloring page)\b"
    r"|\b(malvorlage|ausmalbild)\b"
    # the noun first, the verb at the end („Kannst du mir ein Bild von … erstellen?“, Dominik 2026-10-15): only a new
    # picture (ein/eine/einen) and only the verbs of making one, so „Was ist auf dem Bild?“ stays with Bilder erkennen
    r"|\b(ein|eine|einen)\s+(?:\w+\s+){0,2}(bild|bildchen|zeichnung|illustration|logo|poster|grafik|"
    r"hintergrundbild|wallpaper|avatar)\b.{0,120}\b(erstellen|malen|zeichnen|generieren|erzeugen|machen|"
    r"entwerfen|gestalten|anfertigen)\b")
AGAIN = re.compile(r"(?i)\b(nochmal|noch einmal|noch ein|nochmals|anders|andere[nrs]?|aber|statt|lieber|heller|"
                   r"dunkler|bunter|größer|kleiner|again|another|instead|but)\b")
# a short yes to the assistant's question after a wish („Ja, fiktiv“, „Passt“; Dominik 2026-10-14: it searched the
# web instead of painting): only within FOLLOW_SECONDS after the person's own wish, and only a short message
YES = re.compile(r"(?i)^\W*(ja|jo|jep|jawohl|ok|okay|passt|genau|gern|gerne|mach|los|klar|super|fiktiv\w*|"
                 r"yes|yep|yeah|sure|fine|fictional)\b")
YES_MAX = 120
# fixed word list (Dominik 5a): nothing sexual, no nudity, no gore, no hate symbols, no fakes of people
BAD = re.compile(
    r"(?i)\b(nackt\w*|nacktheit|nude\w*|naked|nudity|nsfw|porn\w*|sex\w*|erotik\w*|erotisch\w*|erotic\w*|hentai|"
    r"topless|oben ohne|genital\w*|brüste|brust frei|busen|penis|vagina|unterwäsche|dessous|lingerie|"
    r"kinderporn\w*|missbrauch\w*|vergewaltig\w*|rape|"
    r"gore|enthaupt\w*|decapitat\w*|verstümmel\w*|mutilat\w*|leiche|leichen|corpses?|blutbad|massaker|massacre|"
    r"folter\w*|tortur\w*|"
    r"hakenkreuz\w*|swastika|nazi\w*|ss-rune\w*|hitler|kkk|deepfake\w*|face ?swap)\b")

TOOL = {"type": "function", "function": {
    "name": "bild_malen",
    "description": "Paints a picture on the Spark (FLUX.2 klein) from the user's wish. Write prompt_en yourself: one "
                   "vivid English description of the picture (subject, setting, style, light, colours), at most 80 "
                   "words, nothing else. Never real or named people, nothing sexual or violent. The picture is "
                   "painted in the background and shown to the user; do not describe it as if you could see it.",
    "parameters": {"type": "object", "required": ["prompt_en"], "properties": {
        "prompt_en": {"type": "string", "description": "the picture described in English"},
        "wunsch": {"type": "string", "description": "the user's wish in their own words, short"},
        "format": {"type": "string", "enum": list(FORMATS), "description": "quadrat (default), quer, hoch, breit"}}}}}
HINT = ("bild_malen malt ein Bild auf dem Spark. Rufe es nur auf, wenn die Person selbst ein Bild, eine Zeichnung, "
        "ein Logo oder eine Malvorlage möchte; schreib prompt_en auf Englisch. Danach ein kurzer Satz, dass das Bild "
        "gemalt wird und gleich erscheint (im Chat und unter Ich → Bilder). Sagt die Person nach einer Rückfrage zum "
        "Bild nur „ja“ oder „passt“, male jetzt das besprochene Bild mit bild_malen; keine Websuche, kein anderer "
        "Bilddienst. Erfundene Personen sind erlaubt, echte bekannte Personen nie.")

_lock = threading.Lock()
_paint = []                 # [asyncio.Lock] of the running loop: one picture at a time
_jobs = {}                  # jid -> job
_tasks = set()
_recent = {}                # uid -> time of the last picture or wish, also a refused one (FOLLOW_SECONDS)
_count = DayCounter(done=0, failed=0, refused=0)
BACKGROUND = True           # tests run _work themselves


# ---------------------------------------------------------------- switches and limits
def cfg():
    return load_config("image")


def admin_on():
    return features.admin_on(KEY)


def limits(c=None):
    c = cfg() if c is None else c
    return {"day": int(c["day_limit"]), "store_mb": int(c["store_mb"]), "max_side": int(c["max_side"]),
            "idle_min": int(c["idle_min"]), "wish": MAX_WISH, "pics": MAX_PICS}


def size(fmt, max_side):
    """(width, height) for a format: the long side max_side, both multiples of 16."""
    a, b = FORMATS.get(fmt, FORMATS["quadrat"])[:2]
    long_ = max(256, min(2048, int(max_side) // 16 * 16))
    short = max(256, round(long_ * min(a, b) / max(a, b) / 16) * 16)
    return (long_, short) if a >= b else (short, long_)


def off_hint(uid, lang="de"):
    t = features.missing_text(KEY, uid, lang)
    if lang == "en":
        return "Painting pictures is not available. " + (t or "Ask the admin (Features → Painting pictures).")
    return ("Bilder malen geht gerade nicht. " + (t or "Frag den Admin (Funktionen → Bilder malen).")
            + " Sag das so in einem Satz und beschreibe kein Bild.")


def clean(v, most):
    return re.sub(r"\s+", " ", CTRL.sub(" ", str(v or ""))).strip()[:most]


def names(uid):
    """Names of people the Spark knows (every profile's name and call name, the profile's contacts): no picture
    may show them (a fixed rule against fakes of real people)."""
    out = set()
    for p in profiles.names():
        for n in (p.get("name"), p.get("call")):
            for w in re.findall(r"\w{3,}", str(n or "")):
                out.add(w.lower())
    try:
        import contacts
        if contacts.usable(uid):
            for c in contacts.cards(uid)[:2000]:
                for w in re.findall(r"\w{4,}", str(c.get("name") or "")):
                    out.add(w.lower())
    except Exception:
        pass
    return out


def refuse_text(uid, *texts):
    """The reason in fixed words when the word list or the names rule refuses, else ""."""
    joined = " ".join(str(t or "") for t in texts)
    if BAD.search(joined):
        return "wortliste"
    words = set(w.lower() for w in re.findall(r"\w{3,}", joined))
    if words & names(uid):
        return "person"
    return ""


REFUSED = {"wortliste": ("Das male ich nicht: der Wunsch fällt unter die festen Regeln (nichts Sexuelles, keine "
                         "Gewalt, keine Hasssymbole).", "I won't paint that: the wish falls under the fixed rules "
                         "(nothing sexual, no violence, no hate symbols)."),
           "person": ("Bilder von Personen, die der Spark kennt, malt er nicht.",
                      "The Spark does not paint people it knows by name."),
           "pruefung": ("Die Bildprüfung hat das Bild zurückgehalten.", "The image check held the picture back."),
           "ohne_pruefung": ("Die Bildprüfung fehlt; ohne sie gibt es kein Bild (Admin: install.sh --bild).",
                             "The image check is missing; without it there is no picture (admin: install.sh --bild)."),
           "memory": ("Gerade ist zu wenig Speicher frei; das Bildmodell startet erst, wenn mehr frei ist.",
                      "Too little memory is free right now; the picture model starts once more is free."),
           "missing": ("Das Bildmodell ist nicht installiert (Admin: sudo ./install.sh --bild 4b-q8).",
                       "The picture model is not installed (admin: sudo ./install.sh --bild 4b-q8)."),
           "dienst": ("Der Bild-Dienst antwortet gerade nicht.", "The picture service does not answer right now."),
           "zeit": ("Das Bild dauerte zu lange.", "The picture took too long."),
           "notaus": ("Der Notaus hält das gerade an.", "The Notaus holds this off right now."),
           "wartung": ("Bilder malen wird gerade gewartet; bitte etwas später noch einmal.",
                       "Painting pictures is being maintained right now; please try again a little later.")}


# ---------------------------------------------------------------- storage (users/<id>/bilder/)
def _dir(uid):
    if not re.fullmatch(r"[\w\-]{1,64}", str(uid or "")):
        raise ValueError("bad profile")
    return profiles._path(uid, "bilder")


def _index_file(uid):
    return os.path.join(_dir(uid), "index.json")


def all_pics(uid):
    """The profile's pictures, newest first."""
    try:
        p = _index_file(uid)
        if os.path.islink(p):
            return []
        import json
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        items = [x for x in d.get("items") or [] if isinstance(x, dict) and ID.fullmatch(str(x.get("id") or ""))]
    except (OSError, ValueError):
        return []
    return sorted(items, key=lambda x: -float(x.get("t") or 0))


def _save_index(uid, items):
    profiles._write(_index_file(uid), {"items": items[:MAX_PICS]})


def pic_path(uid, pid):
    if not ID.fullmatch(str(pid or "")):
        return None
    p = os.path.join(_dir(uid), pid + ".png")
    return p if os.path.isfile(p) and not os.path.islink(p) else None


def used_bytes(uid):
    return sum(int(x.get("bytes") or 0) for x in all_pics(uid))


def today_count(uid, now=None):
    now = time.time() if now is None else now
    return sum(1 for x in all_pics(uid) if now - float(x.get("t") or 0) < DAY_S)


def keep(uid, png, meta):
    """Stores one picture and its line in the index; returns the line."""
    pid = secrets.token_hex(6)
    os.makedirs(_dir(uid), mode=0o700, exist_ok=True)
    p = os.path.join(_dir(uid), pid + ".png")
    with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(png)
    row = dict(meta, id=pid, bytes=len(png), t=round(time.time(), 1))
    with _lock:
        _save_index(uid, [row] + all_pics(uid))
    return row


def delete(uid, pid):
    with _lock:
        items = all_pics(uid)
        rest = [x for x in items if x["id"] != pid]
        if len(rest) == len(items):
            return False
        _save_index(uid, rest)
    p = pic_path(uid, pid)
    if p:
        os.unlink(p)
    return True


def clear(uid):
    """Every picture of the profile (Ich → Bilder „Alle löschen“, Daten löschen of the Freigabe)."""
    with _lock:
        n = len(all_pics(uid))
        try:
            d = _dir(uid)
            for name in os.listdir(d):
                if re.fullmatch(r"[0-9a-f]{12}\.png|index\.json", name):
                    os.unlink(os.path.join(d, name))
        except OSError:
            pass
    return n


features.OWN[KEY] = (lambda uid: len(all_pics(uid)), clear)


def public(x):
    return {"id": x["id"], "t": x.get("t"), "w": x.get("w"), "h": x.get("h"), "prompt": x.get("prompt", ""),
            "wish": x.get("wish", ""), "format": x.get("format", "quadrat"), "seconds": x.get("seconds"),
            "bytes": x.get("bytes", 0), "src": x.get("src", ""), "job": x.get("job", "")}


# ---------------------------------------------------------------- jobs
def stats():
    _count.today()
    with _lock:
        run = sum(1 for j in _jobs.values() if j["state"] == "run")
        wait = sum(1 for j in _jobs.values() if j["state"] == "wait")
    return {"run": run, "wait": wait, "done": _count["done"], "failed": _count["failed"], "refused": _count["refused"]}


def for_live():
    """Numbers only: pictures running and waiting, done, failed and refused today."""
    try:
        return dict(stats(), on=admin_on())
    except Exception:
        return {"on": False}


def _live(text_):
    try:
        import live
        live.event("Bilder", text_)
    except Exception:
        pass


def job_public(j):
    return {"id": j["id"], "state": j["state"], "error": j.get("error", ""), "error_en": j.get("error_en", ""),
            "pic": public(j["pic"]) if j.get("pic") else None, "prompt": j["prompt"], "t0": int(j["t0"])}


def jobs_of(uid):
    with _lock:
        return [job_public(j) for j in sorted(_jobs.values(), key=lambda j: j["t0"]) if j["uid"] == uid
                and (j["state"] in ("wait", "run") or time.time() - j.get("end", 0) < 600)]


def _sweep(now):
    with _lock:
        for k in [k for k, j in _jobs.items() if j["state"] not in ("wait", "run") and now - j.get("end", 0) > 3600]:
            _jobs.pop(k, None)


def _say(why, prof):
    print(f"bilder: nicht gestartet {why} fuer {profiles.log_name(prof)}", flush=True)


def start(prof, prompt, wish, fmt, src="chat", client="web"):
    """Checks everything with fixed rules and starts a job; raises ValueError((de, en)) with the reason."""
    uid = prof["id"]
    if not features.allowed(KEY, uid):
        _say("aus", prof)
        raise ValueError(("Bilder malen ist für dich nicht freigegeben.", "Painting pictures is not released for you."))
    try:
        notaus.stop("auftrag", uid)
    except notaus.NotausAktiv:
        _say("notaus", prof)
        raise ValueError(REFUSED["notaus"])
    if wartung.paused("bild"):   # Wartungspause (wartung.py): the picture model is being updated, nothing starts
        _say("wartung", prof)
        raise ValueError(REFUSED["wartung"])
    prompt, wish = clean(prompt, MAX_PROMPT), clean(wish, MAX_WISH)
    fmt = fmt if fmt in FORMATS else "quadrat"
    if not prompt:
        _say("leer", prof)
        raise ValueError(("Was soll ich malen?", "What shall I paint?"))
    why = refuse_text(uid, prompt, wish)
    if why:
        _count.bump("refused")
        _say(why, prof)
        raise ValueError(REFUSED[why])
    lim = limits()
    _sweep(time.time())
    with _lock:
        if any(j["uid"] == uid and j["state"] in ("wait", "run") for j in _jobs.values()):
            _say("laeuft", prof)
            raise ValueError(("Ich male schon ein Bild für dich; erst wenn es fertig ist.",
                              "I am already painting a picture for you; once it is done."))
        if sum(1 for j in _jobs.values() if j["state"] in ("wait", "run")) >= WAITING:
            _say("warteschlange", prof)
            raise ValueError(("Gerade warten schon viele Bilder; bitte etwas später noch einmal.",
                              "Many pictures are waiting already; please try again a little later."))
    if today_count(uid) >= lim["day"]:
        _say("tageslimit", prof)
        raise ValueError((f"Heute sind schon {lim['day']} Bilder gemalt; morgen wieder.",
                          f"{lim['day']} pictures were painted today already; tomorrow again."))
    if used_bytes(uid) >= lim["store_mb"] * 1024 * 1024 or len(all_pics(uid)) >= MAX_PICS:
        _say("voll", prof)
        raise ValueError(("Deine Bilder brauchen schon den ganzen Platz; bitte erst alte löschen (Ich → Bilder).",
                          "Your pictures use all their space; please delete old ones first (Me → Pictures)."))
    w, h = size(fmt, lim["max_side"])
    jid = secrets.token_hex(6)
    j = {"id": jid, "uid": uid, "state": "wait", "prompt": prompt, "wish": wish, "format": fmt, "w": w, "h": h,
         "t0": time.time(), "src": src, "client": client, "log": profiles.log_name(prof)}
    with _lock:
        _jobs[jid] = j
    _recent[uid] = time.time()
    _live(f"Bild {w}x{h} angenommen")
    print(f"bilder: auftrag {w}x{h} {fmt} {src} fuer {j['log']}", flush=True)
    if BACKGROUND:
        try:
            t = asyncio.get_running_loop().create_task(_run(j))
            _tasks.add(t)
            t.add_done_callback(_tasks.discard)
        except RuntimeError:
            _fail(j, "dienst")
    return job_public(j)


def _fail(j, why):
    de, en = REFUSED.get(why, REFUSED["dienst"])
    j.update(state="error", error=de, error_en=en, end=time.time())
    _count.bump("refused" if why in ("pruefung", "ohne_pruefung") else "failed")
    _live(f"Bild nicht gemalt: {why}")
    print(f"bilder: nicht gemalt {why} fuer {j['log']}", flush=True)


async def _run(j):
    try:
        await asyncio.wait_for(_work(j), JOB_SECONDS)
    except asyncio.TimeoutError:
        _fail(j, "zeit")
    except Exception as e:   # noqa: BLE001 - every job ends with a state and a journal line
        print("bilder: fehler", type(e).__name__, flush=True)
        _fail(j, "dienst")


def _paint_lock():
    loop = asyncio.get_running_loop()
    if not _paint or _paint[0][0] is not loop:
        _paint[:] = [(loop, asyncio.Lock())]
    return _paint[0][1]


async def call(path, body=None, timeout=JOB_SECONDS):
    """One request to bild_server on the model computer (common.model_url, the panel's API key); returns (status, JSON)."""
    url = model_url("bild", path)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as c:
        if body is None:
            r = await c.get(url, headers=api_headers())
        else:
            r = await c.post(url, json=body, headers=api_headers())
    try:
        d = r.json()
    except ValueError:
        d = {}
    return r.status_code, d if isinstance(d, dict) else {}


async def paint(prompt, w, h):
    """The picture as PNG bytes and its numbers, or raises ValueError(why) with a key of REFUSED."""
    try:
        code, d = await call("/v1/bild", {"prompt": prompt, "width": w, "height": h, "seed": -1})
    except httpx.HTTPError:
        raise ValueError("dienst")
    if code == 503 and d.get("detail") in ("memory", "missing"):
        raise ValueError(d["detail"])
    if code == 504:
        raise ValueError("zeit")
    if code != 200 or not isinstance(d.get("png"), str) or len(d["png"]) > MAX_PNG * 4 // 3 + 4:
        raise ValueError("dienst")
    try:
        png = base64.b64decode(d["png"], validate=True)
    except ValueError:
        raise ValueError("dienst")
    if not png.startswith(PNG_SIG) or len(png) > MAX_PNG:
        raise ValueError("dienst")
    share = d.get("nsfw")
    if share is None or isinstance(share, bool) or not isinstance(share, (int, float)):
        raise ValueError("ohne_pruefung")      # without the check no picture (fail closed)
    if share > NSFW_MAX:
        raise ValueError("pruefung")
    return png, d


async def _work(j):
    import vorrang
    await vorrang.quiet("Bild malen")
    async with _paint_lock():
        await vorrang.quiet("Bild malen")
        if wartung.paused("bild"):
            _fail(j, "wartung")
            return
        j["state"] = "run"
        try:
            png, d = await paint(j["prompt"], j["w"], j["h"])
        except ValueError as e:
            _fail(j, str(e) if str(e) in REFUSED else "dienst")
            return
    row = keep(j["uid"], png, {"w": d.get("w", j["w"]), "h": d.get("h", j["h"]), "prompt": j["prompt"],
                               "wish": j["wish"], "format": j["format"], "seconds": d.get("seconds"), "src": j["src"],
                               "model": str(cfg().get("variant") or "")[:10], "job": j["id"]})
    j.update(state="done", pic=row, end=time.time())
    _count.bump("done")
    import verbrauch   # Verbrauchszähler: one picture and its time (does nothing while the counter is off)
    verbrauch.add("bild", "Bild malen", who=j["uid"], amount=1, ms=int((d.get("seconds") or 0) * 1000))
    _live(f"Bild {row['w']}x{row['h']} gemalt")
    print(f"bilder: gemalt {row['w']}x{row['h']} {d.get('seconds')} s fuer {j['log']}", flush=True)
    try:
        import tagebuch
        tagebuch.note(j["uid"], "bild", "Bild: " + (j["wish"] or j["prompt"])[:70], ref=row["id"])
    except Exception:
        pass
    if j["client"] != "web":
        try:
            import push
            await push.send(j["uid"], "Bild fertig", "Dein Bild liegt unter Ich → Bilder.", tag="bild", why="Bild")
        except Exception as e:   # noqa: BLE001 - the picture is there anyway
            print("bilder: hinweis nicht gesendet", type(e).__name__, flush=True)


# ---------------------------------------------------------------- the assistant
def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    uid = who["id"]
    words = str(ctx.get("text") or "")
    asked = bool(WORDS.search(words))
    recent = time.time() - _recent.get(uid, 0) < FOLLOW_SECONDS
    again = recent and (bool(AGAIN.search(words)) or len(words) <= YES_MAX and bool(YES.search(words)))
    if not asked and not again:
        return None
    if asked:
        _recent[uid] = time.time()   # the wish itself: the assistant may ask back, the answer still paints
    if not features.allowed(KEY, uid):
        return {"tools": [], "hint": off_hint(uid)} if asked else None
    return {"tools": [TOOL], "hint": HINT, "changes": {"bild_malen"}, "keep": {"bild_malen"},
            "filler": {"bild_malen": ("Ich male das Bild.", "Painting the picture.")}}


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    if name != "bild_malen" or not who.get("id"):
        return "Not done: unknown tool."
    args = args if isinstance(args, dict) else {}
    client = ctx.get("client") or "web"
    try:
        j = start(who, args.get("prompt_en"), args.get("wunsch"), args.get("format"), "chat", client)
    except ValueError as e:
        de = e.args[0][0] if e.args and isinstance(e.args[0], tuple) else "Das ging nicht."
        return f"Not done: {de} Sag das so in einem Satz und beschreibe kein Bild."
    if client in ("", "web", "iphone") and ctx.get("out") is not None:   # the panel's chat and the iPhone app show it
        await ctx["out"].put({"type": "bild", "job": j["id"], "prompt": j["prompt"]})
        where = "Es erscheint gleich hier im Chat und unter Ich → Bilder."
    else:
        where = "Es liegt gleich unter Ich → Bilder; der Spark sagt Bescheid."
    return (f"Started: the picture is being painted on the Spark ({j['prompt'][:200]}). Tell the user in one short "
            f"sentence that you are painting it. {where} Do not describe the picture.")


# ---------------------------------------------------------------- routes
def _prof(request, prof):
    if not features.allowed(KEY, prof["id"]):
        raise HTTPException(403, "Bilder malen ist aus (Funktionen → Bilder malen)")
    return prof


@router.get("/api/bilder", dependencies=[Depends(assistant)])
def bilder_list(request: Request, prof=Depends(own_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "bilder", uid)
    lim = limits()
    return {"pics": [public(x) for x in all_pics(uid)], "jobs": jobs_of(uid), "limits": lim,
            "used": used_bytes(uid), "today": today_count(uid),
            "formats": [[k, v[2], v[3]] for k, v in FORMATS.items()]}


@router.post("/api/bilder", dependencies=[Depends(assistant)])
async def bilder_paint(request: Request, prof=Depends(browser_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "bildmalen", uid)
    body = await json_body(request, 8 * 1024, lenient=True)
    wish = clean(body.get("wunsch"), MAX_WISH)
    try:
        return start(prof, wish, wish, str(body.get("format") or ""), "seite", "web")
    except ValueError as e:
        raise HTTPException(409, e.args[0][0] if e.args and isinstance(e.args[0], tuple) else "geht nicht")


@router.get("/api/bilder/job/{jid}", dependencies=[Depends(assistant)])
def bilder_job(jid: str, request: Request, prof=Depends(own_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "bildjob", uid)
    j = _jobs.get(jid)
    if j and j["uid"] == uid:
        return job_public(j)
    # a finished job the panel already forgot (an hour later, after a restart): the kept picture names its job, so
    # an answer in the chat finds its picture again on every device
    p = next((x for x in all_pics(uid) if ID.fullmatch(jid) and x.get("job") == jid), None)
    if not p:
        raise HTTPException(404, "kein solcher Auftrag")
    return {"id": jid, "state": "done", "error": "", "error_en": "", "pic": public(p), "prompt": p.get("prompt", ""),
            "t0": int(p.get("t") or 0)}


@router.get("/api/bilder/{pid}/datei", dependencies=[Depends(assistant)])
def bilder_file(pid: str, request: Request, dl: int = 0, prof=Depends(own_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "bilddatei", uid)
    p = pic_path(uid, pid)
    if not p:
        raise HTTPException(404, "kein solches Bild")
    with open(p, "rb") as f:
        data = f.read(MAX_PNG + 1)
    if len(data) > MAX_PNG or not data.startswith(PNG_SIG):
        raise HTTPException(404, "kein solches Bild")
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'", "Referrer-Policy": "no-referrer"}
    if dl:
        headers["Content-Disposition"] = f'attachment; filename="spark-bild-{pid}.png"'
    return Response(data, media_type="image/png", headers=headers)


@router.delete("/api/bilder/{pid}", dependencies=[Depends(assistant)])
def bilder_delete(pid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    guard.limit(request, "bilder", uid)
    if not ID.fullmatch(pid) or not delete(uid, pid):
        print(f"bilder: nicht geloescht unbekannt fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "kein solches Bild")
    print(f"bilder: geloescht 1 fuer {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


@router.delete("/api/bilder", dependencies=[Depends(assistant)])
def bilder_clear(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "bilder", prof["id"])
    n = clear(prof["id"])
    print(f"bilder: geloescht {n} fuer {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "deleted": n}


# ---------------------------------------------------------------- admin: Bild testen (Stufe 0, measuring)
def _test_file():
    return os.path.join(STATE, "bild-test.json")


def last_test():
    try:
        import json
        with open(_test_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


async def health():
    """The service's state and measurements (load time, memory, seconds per picture), or {"status": "down"}."""
    if not cfg().get("enabled"):
        return {"status": "off_install"}
    try:
        code, d = await call("/health", timeout=5)
    except httpx.HTTPError:
        return {"status": "down"}
    return d if code == 200 else {"status": "down"}


@router.get("/api/admin/bild-test", dependencies=[Depends(auth)])
async def bild_test_get():
    return {"last": last_test(), "health": await health()}


@router.post("/api/admin/bild-test", dependencies=[Depends(auth)])
async def bild_test_run(request: Request):
    guard.limit(request, "bildtest", None, True)
    from common import write_json
    t0 = time.time()
    res = {"t": round(t0), "ok": False, "why": "", "seconds": None}
    if not cfg().get("enabled"):
        res["why"] = "missing"
    else:
        try:
            async with _paint_lock():
                _png, d = await paint(TEST_PROMPT, 512, 512)
            res.update(ok=True, seconds=d.get("seconds"), nsfw=round(float(d["nsfw"]), 3))
        except ValueError as e:
            res["why"] = str(e) if str(e) in REFUSED else "dienst"
    res["total_s"] = round(time.time() - t0, 1)
    res["health"] = await health()
    print("bilder: test", "ok" if res["ok"] else "nicht ok " + res["why"], f"{res['total_s']} s", flush=True)
    try:
        write_json(_test_file(), res)
    except OSError:
        pass
    return {"last": res, "health": res["health"]}
