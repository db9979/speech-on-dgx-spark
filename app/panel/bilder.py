"""Bilder malen (plan plaene/bildgenerierung.md, Dominik 2026-10-14 „1c 2a 3a 4a 5a 6a 7a 8b“): pictures from a
wish, painted on the Spark by FLUX.2 [klein] (bild_server.py on 127.0.0.1, image.port).

Ways in: the tool bild_malen in the conversation (the language model writes the English picture prompt from the
person's words, Dominik 4a, shown under the picture) and Ich → Bilder (the person's own sentence goes as it is).
The panel decides everything else with fixed rules: size from the format and image.max_side, 4 steps, one picture
at a time on the whole Spark and never beside a song (schwer.py: one place for the models on demand, at most
schwer.WAITING heavy jobs waiting), one open job per profile, image.day_limit pictures per
profile in 24 hours, image.store_mb per profile.

Protection (Dominik 5a, fixed rules, no switch): a word list before painting (the wish and the prompt, de and en),
no pictures of people the Spark knows by name (profiles, the profile's contacts), the image check of bild_server
after painting (a fixed threshold NSFW_MAX decides; without the check no picture at all), and every picture
marked as made by an AI (bild_server). Text from outside (mail, web, documents) never starts a picture: bild_malen
is a changing tool, locked after outside text (chat.LOCKED_OUTSIDE via the extras' "changes"), and from Notaus
stage 2 on. Guests never get the tool or the page; a blocked profile only sees „Daten löschen“.

Bilder ändern (plan plaene/bildbearbeitung.md, Dominik 2026-10-16 „Umsetzen“, own admin switch chat.bilder_aendern,
built on Bilder malen): FLUX.2 [klein] changes the person's own picture with it as a reference. The panel decides
which picture and when, never the model (the turn with a photo has no tools anyway): a photo attached in this turn
(images.py) with a wish to change it (EDIT, not a question), a short follow-up within FOLLOW_SECONDS after the last
change (the result of that change), or a picture of Ich → Bilder (painted, changed or uploaded there, „Ändern“).
Pictures from mail, web, documents or someone else are never a source. The wish goes to the model as the person said
it; besides BAD a second fixed list EDIT_BAD refuses forging papers, money and number plates and undressing or
hurting people. The image check and the mark (bild_server: "KI-bearbeitet", IPTC composite) as for painting; the
source stays as it is, the change is a new picture.

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

import coadmin
import features
import guard
import notaus
import profiles
import schwer
import wartung
from common import DayCounter, STATE, load_config, model_url
from core import api_headers, assistant, auth, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "bilder"
EDIT_KEY = "bildaendern"     # Bilder ändern (features.py, chat.bilder_aendern; builds on Bilder malen)
MAX_WISH = 500
MAX_PROMPT = 1000
MAX_PICS = 300              # pictures per profile, whatever the space
NSFW_MAX = 0.5              # the image check's share above which a picture is thrown away (fixed rule)
JOB_SECONDS = 12 * 60       # waiting for a pause, loading the model and painting (plus schwer.WAIT_S in the queue)
FOLLOW_SECONDS = 10 * 60    # after a picture wish, "noch einmal in Blau" or "ja, fiktiv" is understood without the words
MAX_PNG = 40 * 1024 * 1024
MAX_PHOTO = 8 * 1024 * 1024      # an own photo uploaded to Ich → Bilder (as images.MAX_BYTES)
PHOTO_SIDE = 2048                # its longest side once kept
FOLLOW_MAX = 200                 # a follow-up change („heller“) is a short message
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
    r"wallpaper|avatar|karikatur|comic|cartoon|picture|image|drawing|illustration|caricature|coloring page)\b"
    r"|\b(malvorlage|ausmalbild)\b"
    # the noun first, the verb at the end („Kannst du mir ein Bild von … erstellen?“, Dominik 2026-10-15): only a new
    # picture (ein/eine/einen) and only the verbs of making one, so „Was ist auf dem Bild?“ stays with Bilder erkennen
    r"|\b(ein|eine|einen)\s+(?:\w+\s+){0,2}(bild|bildchen|zeichnung|illustration|logo|poster|grafik|"
    r"hintergrundbild|wallpaper|avatar|karikatur|comic|cartoon)\b.{0,120}\b(erstellen|malen|zeichnen|generieren|erzeugen|machen|"
    r"entwerfen|gestalten|anfertigen)\b")
AGAIN = re.compile(r"(?i)\b(nochmal|noch einmal|noch ein|nochmals|anders|andere[nrs]?|aber|statt|lieber|heller|"
                   r"dunkler|bunter|größer|kleiner|again|another|instead|but)\b")
# a short yes to the assistant's question after a wish („Ja, fiktiv“, „Passt“; Dominik 2026-10-14: it searched the
# web instead of painting): only within FOLLOW_SECONDS after the person's own wish, and only a short message
YES = re.compile(r"(?i)^\W*(ja|jo|jep|jawohl|ok|okay|passt|genau|gern|gerne|mach|los|klar|super|fiktiv\w*|"
                 r"yes|yep|yeah|sure|fine|fictional)\b")
YES_MAX = 120
# a wish to change a picture (Bilder ändern), only together with a picture of this turn or right after a change
EDIT = re.compile(
    r"(?i)\b(ändere?n?|aendere?n?|bearbeit\w*|veränder\w*|veraender\w*|verwandl\w*|verwandel\w*|retuschier\w*|"
    r"ersetze?n?|tausche?n?|färbe?n?|faerbe?n?|umfärben|entferne?n?|edit|change|remove|replace|recolou?r|retouch)\b"
    r"|\b(nimm|nehmt?|nehmen)\b.{0,60}\b(weg|raus|heraus)\b|\bfüge?n?\b.{0,60}\bhinzu\b"
    # „Mach den Bart weg“, „Lass den Hut weg“, „Mach ihn ohne Brille“, „Bart weg bitte“ (Dominik 2026-10-16)
    r"|\b(mach\w*|lass\w*)\b.{0,60}\b(weg|raus|ab|ohne)\b|\b(weg|raus)(?:machen|nehmen|lassen|retuschieren)\b"
    r"|^\W*(?:(?:den|die|das|der|dem|seinen|seine|ihren|ihre|meinen|meine)\s+)?\w+\s+(weg|raus)\b(?:\W+bitte)?\W*$"
    r"|\bsetze?n?\b.{0,60}\b(hinein|rein|dazu|ins bild|ins foto)\b"
    r"|\bmach\w*\b.{0,40}\b(heller|dunkler|bunter|farbig\w*|schwarzweiß|schwarz-weiß|blau\w*|rot\w*|grün\w*|gelb\w*|"
    r"wärmer|kälter|schärfer|weicher|freundlicher|sonnig\w*|winterlich\w*|herbstlich\w*|daraus|zu einem|zu einer)\b"
    r"|\b(als|im stil|im stile)\b.{0,20}\b(aquarell\w*|ölgemälde|gemälde|comic\w*|zeichnung|skizze|bleistift\w*|"
    r"pixel\w*|anime|cartoon|pop.?art|mosaik|malvorlage|ausmalbild)\b"
    r"|\b(turn it into|make it)\b")
# a question about the picture stays a question (Bilder erkennen): „Wie entferne ich den Fleck?“ changes nothing
QUESTION = re.compile(r"(?i)^\W*(wie|was|warum|wieso|weshalb|wo|wer|welche\w*|wann|kann man|gibt es|ist das|"
                      r"sind das|erkennst|siehst|what|how|why|where|who|which|when|is (?:it|this|that)|are (?:they|these))\b")
# what is never changed (fixed, besides BAD): forged papers, money and number plates, undressing or hurting people
_CLOTHES = (r"(?:kleid\w*|kleidung|klamotten|hose\w*|hemd\w*|bluse\w*|rock|bh|unterhose\w*|bikini\w*|badeanzug\w*|"
            r"badehose\w*|oberteil\w*|t-?shirt\w*|pulli\w*|pullover\w*|clothes|clothing|dress\w*|shirt\w*|bra|underwear|swimsuit)")
EDIT_BAD = re.compile(
    r"(?i)\b(ausweis\w*|personalausweis\w*|reisepass\w*|pass ?foto\w*|führerschein\w*|fuehrerschein\w*|"
    r"unterschrift\w*|signatur\w*|stempel\w*|siegel\w*|kennzeichen|nummernschild\w*|banknote\w*|geldschein\w*|"
    r"attest\w*|zeugnis\w*|urkunde\w*|passport|driver'?s licen[cs]e|signature|stamp|licen[cs]e plate|"
    r"banknote|id card|"
    r"auszieh\w*|zieh\w* (?:ihr|ihm|ihnen|sie|ihn|die|den|das) .{0,20}aus|entkleid\w*|ohne kleidung|ohne klamotten|"
    r"undress\w*|without clothes|verletz\w*|blutig\w*|blutend\w*|wunden?|injur\w*|bleeding|"
    r"tausch\w* (?:das |die )?gesicht\w*|gesicht\w* (?:tauschen|austauschen|einsetzen)|face ?swap\w*|swap\w* (?:the )?faces?|"
    # clothes taken off a person, in either order („Entferne ihr Kleid“, „das Hemd weg“)
    r"(?:entfern\w*|nimm\w*|weg\w*|remove|take off)\b.{0,40}\b" + _CLOTHES + r"|" + _CLOTHES + r"\b.{0,30}\b(?:weg|aus|ab|entfern\w*|off))\b")

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
_jobs = {}                  # jid -> job
_tasks = set()
_recent = {}                # uid -> time of the last picture or wish, also a refused one (FOLLOW_SECONDS)
_edits = {}                 # uid -> (time, picture id) of the last change (Bilder ändern), for a short follow-up
_count = DayCounter(done=0, edited=0, quick=0, failed=0, refused=0)
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
           "belegt": ("Das Musikmodell gibt den Platz gerade nicht frei; bitte etwas später noch einmal.",
                      "The music model does not free the place right now; please try again a little later."),
           "missing": ("Das Bildmodell ist nicht installiert (Admin: sudo ./install.sh --bild 4b-q8).",
                       "The picture model is not installed (admin: sudo ./install.sh --bild 4b-q8)."),
           "dienst": ("Der Bild-Dienst antwortet gerade nicht.", "The picture service does not answer right now."),
           "zeit": ("Das Bild dauerte zu lange.", "The picture took too long."),
           "notaus": ("Der Notaus hält das gerade an.", "The Notaus holds this off right now."),
           "wartung": ("Bilder malen wird gerade gewartet; bitte etwas später noch einmal.",
                       "Painting pictures is being maintained right now; please try again a little later."),
           "aendern_regel": ("Das ändere ich nicht: Ausweise, Unterschriften, Stempel, Kennzeichen und Geld fälsche ich "
                             "nicht, und Menschen ziehe ich nichts aus und verletze sie nicht.",
                             "I won't change that: I do not forge papers, signatures, stamps, number plates or money, "
                             "and I do not undress or hurt people."),
           "aendern_aus": ("Bilder ändern ist für dich nicht freigegeben.", "Changing pictures is not released for you."),
           "quelle": ("Das Bild ist nicht mehr da; bitte noch einmal anhängen oder unter Ich → Bilder wählen.",
                      "The picture is gone; please attach it again or pick it under Me → Pictures.")}


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
    return sum(1 for x in all_pics(uid) if now - float(x.get("t") or 0) < DAY_S and x.get("src") not in ("foto", "schnell"))


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
            "bytes": x.get("bytes", 0), "src": x.get("src", ""), "job": x.get("job", ""),
            "art": x.get("art", "malen"), "von": x.get("von", "")}


# ---------------------------------------------------------------- jobs
def stats():
    _count.today()
    with _lock:
        run = sum(1 for j in _jobs.values() if j["state"] == "run")
        wait = sum(1 for j in _jobs.values() if j["state"] == "wait")
    return {"run": run, "wait": wait, "done": _count["done"], "edited": _count["edited"], "quick": _count["quick"], "failed": _count["failed"],
            "refused": _count["refused"]}


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
    """The job for its page and card; q: its place among the heavy jobs while it is open (schwer.where)."""
    return {"id": j["id"], "state": j["state"], "error": j.get("error", ""), "error_en": j.get("error_en", ""),
            "pic": public(j["pic"]) if j.get("pic") else None, "prompt": j["prompt"], "t0": int(j["t0"]),
            "art": j.get("art", "malen"), "q": schwer.where(j["id"]) if j["state"] in ("wait", "run") else None}


def jobs_of(uid):
    with _lock:
        return [job_public(j) for j in sorted(_jobs.values(), key=lambda j: j["t0"]) if j["uid"] == uid
                and (j["state"] in ("wait", "run") or time.time() - j.get("end", 0) < 600)]


def _open_jobs():
    """schwer.SOURCES: this module's jobs (no lock: job_public asks schwer while holding _lock)."""
    return list(_jobs.values())


async def _stop_engine():
    """schwer.STOPS: ends the picture model now; False when the picture service is not installed."""
    if not cfg().get("enabled"):
        return False
    code, _d = await call("/v1/bild/stop", {}, timeout=30)
    if code != 200:
        raise RuntimeError(code)
    return True


schwer.SOURCES["bild"] = _open_jobs
schwer.STOPS["bild"] = _stop_engine


def _sweep(now):
    with _lock:
        for k in [k for k, j in _jobs.items() if j["state"] not in ("wait", "run") and now - j.get("end", 0) > 3600]:
            _jobs.pop(k, None)


def _say(why, prof):
    print(f"bilder: nicht gestartet {why} fuer {profiles.log_name(prof)}", flush=True)


def ref_size(ref, max_side):
    """(width, height) for a change: the source's shape, the long side max_side, both multiples of 16 (None if the
    source is no picture)."""
    from PIL import Image
    import io
    try:
        Image.MAX_IMAGE_PIXELS = 40_000_000
        with Image.open(io.BytesIO(ref)) as im:
            w0, h0 = im.size
    except Exception:
        return None
    if w0 < 1 or h0 < 1:
        return None
    long_ = max(256, min(2048, int(max_side) // 16 * 16))
    short = max(256, min(long_, round(long_ * min(w0, h0) / max(w0, h0) / 16) * 16))
    return (long_, short) if w0 >= h0 else (short, long_)


def start(prof, prompt, wish, fmt, src="chat", client="web", ref=None, von=""):
    """Checks everything with fixed rules and starts a job; raises ValueError((de, en)) with the reason.
    ref: the picture to change (Bilder ändern, bytes of the person's own picture), von: its id in Ich → Bilder."""
    uid = prof["id"]
    if not features.allowed(KEY, uid):
        _say("aus", prof)
        raise ValueError(("Bilder malen ist für dich nicht freigegeben.", "Painting pictures is not released for you."))
    if ref is not None and not features.allowed(EDIT_KEY, uid):
        _say("aendern aus", prof)
        raise ValueError(REFUSED["aendern_aus"])
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
    why = refuse_text(uid, prompt, wish) or ("aendern_regel" if ref is not None and EDIT_BAD.search(prompt + " " + wish) else "")
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
        if schwer.full():
            _say("warteschlange", prof)
            raise ValueError(("Gerade warten schon viele Bilder; bitte etwas später noch einmal.",
                              "Many pictures are waiting already; please try again a little later."))
    if today_count(uid) >= lim["day"] and not coadmin.unbegrenzt(uid):
        _say("tageslimit", prof)
        raise ValueError((f"Heute sind schon {lim['day']} Bilder gemalt; morgen wieder.",
                          f"{lim['day']} pictures were painted today already; tomorrow again."))
    if used_bytes(uid) >= lim["store_mb"] * 1024 * 1024 or len(all_pics(uid)) >= MAX_PICS:
        _say("voll", prof)
        raise ValueError(("Deine Bilder brauchen schon den ganzen Platz; bitte erst alte löschen (Ich → Bilder).",
                          "Your pictures use all their space; please delete old ones first (Me → Pictures)."))
    if ref is not None:
        wh = ref_size(ref, lim["max_side"])
        if not wh:
            _say("quelle", prof)
            raise ValueError(REFUSED["quelle"])
        w, h = wh
    else:
        w, h = size(fmt, lim["max_side"])
    jid = secrets.token_hex(6)
    j = {"id": jid, "uid": uid, "state": "wait", "prompt": prompt, "wish": wish, "format": fmt, "w": w, "h": h,
         "t0": time.time(), "src": src, "client": client, "log": profiles.log_name(prof),
         "art": "aendern" if ref is not None else "malen", "von": von if von == "foto" or ID.fullmatch(str(von or "")) else ""}
    if ref is not None:
        j["ref"] = base64.b64encode(ref).decode()   # only in memory, gone when the job ends
    with _lock:
        _jobs[jid] = j
    if ref is None:
        _recent[uid] = time.time()
    art = "aendern " if ref is not None else ""
    _live(f"Bild {w}x{h} angenommen")
    print(f"bilder: auftrag {art}{w}x{h} {fmt} {src} fuer {j['log']}", flush=True)
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
    j.pop("ref", None)
    j.update(state="error", error=de, error_en=en, end=time.time())
    _count.bump("refused" if why in ("pruefung", "ohne_pruefung") else "failed")
    _live(f"Bild nicht gemalt: {why}")
    print(f"bilder: nicht gemalt {why} fuer {j['log']}", flush=True)


async def _run(j):
    try:
        await asyncio.wait_for(_work(j), JOB_SECONDS + schwer.WAIT_S)
    except asyncio.TimeoutError:
        _fail(j, "zeit")
    except Exception as e:   # noqa: BLE001 - every job ends with a state and a journal line
        print("bilder: fehler", type(e).__name__, flush=True)
        _fail(j, "dienst")


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


async def paint(prompt, w, h, refs=None):
    """The picture as PNG bytes and its numbers, or raises ValueError(why) with a key of REFUSED. refs: base64
    pictures to change (Bilder ändern)."""
    body = {"prompt": prompt, "width": w, "height": h, "seed": -1}
    if refs:
        body["refs"] = list(refs)
    try:
        code, d = await call("/v1/bild", body)
    except httpx.HTTPError:
        raise ValueError("dienst")
    if code == 503 and d.get("detail") in ("memory", "missing", "belegt"):
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

    async def once():   # on the one place of the heavy jobs (schwer.py); again after "memory"
        await vorrang.quiet("Bild malen")
        if wartung.paused("bild"):
            raise ValueError("wartung")
        j["state"] = "run"
        return await paint(j["prompt"], j["w"], j["h"], [j["ref"]] if j.get("ref") else None)
    try:
        png, d = await schwer.run("bild", j.get("id"), j.get("t0"), once)
    except ValueError as e:
        _fail(j, str(e) if str(e) in REFUSED else "dienst")
        return
    j.pop("ref", None)
    edit = j.get("art") == "aendern"
    row = keep(j["uid"], png, {"w": d.get("w", j["w"]), "h": d.get("h", j["h"]), "prompt": j["prompt"],
                               "wish": j["wish"], "format": j["format"], "seconds": d.get("seconds"), "src": j["src"],
                               "model": str(cfg().get("variant") or "")[:10], "job": j["id"],
                               **({"art": "aendern", "von": j.get("von", "")} if edit else {})})
    j.update(state="done", pic=row, end=time.time())
    _count.bump("edited" if edit else "done")
    if edit:
        _edits[j["uid"]] = (time.time(), row["id"])   # a short follow-up changes this result again
    import verbrauch   # Verbrauchszähler: one picture and its time (does nothing while the counter is off)
    verbrauch.add("bild", "Bild ändern" if edit else "Bild malen", who=j["uid"], amount=1,
                  ms=int((d.get("seconds") or 0) * 1000))
    _live(f"Bild {row['w']}x{row['h']} {'geändert' if edit else 'gemalt'}")
    print(f"bilder: {'geaendert' if edit else 'gemalt'} {row['w']}x{row['h']} {d.get('seconds')} s fuer {j['log']}", flush=True)
    try:
        import tagebuch
        tagebuch.note(j["uid"], "bild", ("Bild geändert: " if edit else "Bild: ") + (j["wish"] or j["prompt"])[:70],
                      ref=row["id"])
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
    recent = time.time() - _recent.get(uid, 0) < FOLLOW_SECONDS and _edits.get(uid, (0,))[0] < _recent.get(uid, 0)
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
    wait = schwer.hint(j["id"])
    if wait:   # Dominik 2026-10-18 3a 4a: only when it really waits behind other heavy jobs, a fixed sentence
        return (f"Started, but waiting in the queue: the picture will be painted on the Spark ({j['prompt'][:200]}). "
                f"Say this to the user, in their language and without changing the numbers: „{wait}“ {where} "
                f"Do not describe the picture.")
    return (f"Started: the picture is being painted on the Spark ({j['prompt'][:200]}). Tell the user in one short "
            f"sentence that you are painting it. {where} Do not describe the picture.")


# ---------------------------------------------------------------- Bilder ändern in the conversation
def wants_change(text):
    """A wish to change a picture in the person's own words: a change word, no question about the picture."""
    text = str(text or "")[:2000]
    return bool(EDIT.search(text)) and not QUESTION.search(text)


def _data_url(u):
    """The bytes of a picture of this turn (images.for_turn: "data:image/jpeg;base64,...")."""
    m = re.fullmatch(r"data:image/(?:jpeg|png);base64,([A-Za-z0-9+/=]+)", str(u or ""))
    try:
        return base64.b64decode(m.group(1), validate=True) if m else None
    except ValueError:
        return None


def own_pic(uid, pid):
    """The bytes of one of the profile's own pictures (Ich → Bilder), or None."""
    p = pic_path(uid, pid)
    if not p:
        return None
    with open(p, "rb") as f:
        data = f.read(MAX_PNG + 1)
    return data if len(data) <= MAX_PNG and data.startswith(PNG_SIG) else None


async def from_turn(ctx, text, pics):
    """Bilder ändern by a fixed rule, before the model answers: {"call", "system", "event"?} or None.
    ctx: {"who", "own", "client", "private"}; pics: the pictures of this turn (data URLs, images.for_turn).
    The source is the first picture of this turn, or without one the result of the last change (FOLLOW_SECONDS,
    a short message); never a picture from outside. The model only says that the picture is being changed."""
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    uid = who["id"]
    text = str(text or "")
    if pics:
        if not wants_change(text):
            return None
        ref, von = _data_url(pics[0]), "foto"
    else:
        t, pid = _edits.get(uid, (0, ""))
        if time.time() - t >= FOLLOW_SECONDS or len(text) > FOLLOW_MAX or WORDS.search(text) \
                or QUESTION.search(text) or not (EDIT.search(text) or AGAIN.search(text)):
            return None
        ref, von = own_pic(uid, pid), pid
    if not features.allowed(EDIT_KEY, uid):
        if not pics:
            return None
        print(f"bilder: nicht gestartet aendern aus fuer {profiles.log_name(who)}", flush=True)
        return {"call": {"name": "Bild ändern (Panel)", "args": "", "result": "nicht freigegeben"},
                "system": "Bild ändern: " + features.missing_text(EDIT_KEY, uid, "de")
                + " Sag in einem Satz, dass Bilder ändern gerade nicht geht; beschreibe das Foto nur, wenn danach gefragt."}
    client = ctx.get("client") or "web"
    try:
        if ref is None:
            raise ValueError(REFUSED["quelle"])
        j = start(who, text, text, "", "chat", client, ref=ref, von=von)
    except ValueError as e:
        de = e.args[0][0] if e.args and isinstance(e.args[0], tuple) else "Das ging nicht."
        return {"call": {"name": "Bild ändern (Panel)", "args": "", "result": "nicht gestartet"},
                "system": f"Bild ändern: Nicht gestartet. {de} Sag genau das in einem Satz und beschreibe kein Bild."}
    shown = client in ("", "web", "iphone")
    where = "hier im Chat und unter Ich → Bilder" if shown else "unter Ich → Bilder; der Spark sagt Bescheid"
    wait = schwer.hint(j["id"])
    say = (f"Sag der Person genau diesen Satz (in ihrer Sprache, die Zahlen unverändert): „{wait}“ Danach, dass das "
           f"Bild {where} erscheint." if wait else
           f"Sag in einem kurzen Satz, dass du das Bild änderst und es gleich {where} erscheint.")
    out = {"call": {"name": "Bild ändern (Panel)", "args": "", "result": "gestartet"},
           "system": f"Bild ändern: Das Panel ändert das Bild jetzt nach dem Wunsch der Person auf dem Spark. {say} "
                     f"Beschreibe das Bild nicht und rufe kein Werkzeug auf."}
    if shown:
        out["event"] = {"type": "bild", "job": j["id"], "prompt": j["prompt"], "art": "aendern"}
    return out


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
            "used": used_bytes(uid), "today": today_count(uid), "frei": coadmin.unbegrenzt(uid),
            "formats": [[k, v[2], v[3]] for k, v in FORMATS.items()],
            "quick": [[k, de, en] for k, (de, en) in QUICK.items()] if features.allowed(EDIT_KEY, uid) else []}


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


def _edit_prof(prof):
    if not features.allowed(EDIT_KEY, prof["id"]):
        raise HTTPException(403, "Bilder ändern ist aus (Funktionen → Bilder ändern)")
    return prof


@router.post("/api/bilder/{pid}/aendern", dependencies=[Depends(assistant)])
async def bilder_change(pid: str, request: Request, prof=Depends(browser_profile)):
    """Ich → Bilder „Ändern“: one of the profile's own pictures with the person's own sentence."""
    uid = _edit_prof(_prof(request, prof))["id"]
    guard.limit(request, "bildmalen", uid)
    body = await json_body(request, 8 * 1024, lenient=True)
    wish = clean(body.get("wunsch"), MAX_WISH)
    ref = own_pic(uid, pid) if ID.fullmatch(pid) else None
    if ref is None:
        print(f"bilder: nicht gestartet quelle fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "kein solches Bild")
    try:
        return start(prof, wish, wish, "", "seite", "web", ref=ref, von=pid)
    except ValueError as e:
        raise HTTPException(409, e.args[0][0] if e.args and isinstance(e.args[0], tuple) else "geht nicht")


def photo_png(data, side=PHOTO_SIDE):
    """An own photo for Ich → Bilder: decoded with images.prepare (upright, no metadata, size limits), then kept as
    a plain PNG at most side pixels long. Raises ValueError if it is no picture."""
    import io
    import images
    from PIL import Image
    jpeg, w, h = images.prepare(data, side=side, quality=95)
    im = Image.open(io.BytesIO(jpeg))
    out = io.BytesIO()
    im.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue(), w, h


@router.post("/api/bilder/foto", dependencies=[Depends(assistant)])
async def bilder_photo(request: Request, prof=Depends(browser_profile)):
    """Ich → Bilder „Eigenes Foto hochladen“ (the raw picture as the body): kept to be changed later."""
    uid = _edit_prof(_prof(request, prof))["id"]
    guard.limit(request, "bildfoto", uid)
    import images
    data = await images._read(request, MAX_PHOTO)
    lim = limits()
    if used_bytes(uid) >= lim["store_mb"] * 1024 * 1024 or len(all_pics(uid)) >= MAX_PICS:
        print(f"bilder: foto nicht gespeichert voll fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, "Deine Bilder brauchen schon den ganzen Platz; bitte erst alte löschen (Ich → Bilder).")
    try:
        png, w, h = await asyncio.wait_for(asyncio.to_thread(photo_png, data), 20)
    except (ValueError, asyncio.TimeoutError):
        print(f"bilder: foto nicht gespeichert kein bild fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, "Das ist kein Bild, das ich lesen kann (JPEG, PNG oder WebP).")
    row = keep(uid, png, {"w": w, "h": h, "prompt": "", "wish": "", "format": "", "src": "foto", "art": "foto"})
    print(f"bilder: foto gespeichert {w}x{h} fuer {profiles.log_name(prof)}", flush=True)
    return public(row)


# Schnellknöpfe (Stufe 2b, Dominik 2026-10-16 4a): fixed changes on the panel itself with Pillow, no model, at once.
# key -> (German, English); the result is a new picture, the original stays
QUICK = {"links": ("Nach links drehen", "Rotate left"), "rechts": ("Nach rechts drehen", "Rotate right"),
         "spiegeln": ("Spiegeln", "Mirror"), "heller": ("Heller", "Brighter"), "dunkler": ("Dunkler", "Darker"),
         "kontrast": ("Mehr Kontrast", "More contrast"), "schwarzweiss": ("Schwarzweiß", "Black and white"),
         "quadrat": ("Quadratisch zuschneiden", "Crop to a square"), "kleiner": ("Halb so groß", "Half the size")}


def quick_png(data, was):
    """One fixed change (QUICK) of a PNG -> (PNG, width, height). The source's text chunks stay, so a picture
    marked as made or edited by an AI keeps its marks; an own photo gets none. Raises ValueError otherwise."""
    import io
    from PIL import Image, ImageEnhance, ImageOps, PngImagePlugin
    if was not in QUICK:
        raise ValueError("was")
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise ValueError("bild")
    marks = {k: v for k, v in (im.text or {}).items() if isinstance(v, str) and len(v) <= 4000}
    im = im.convert("RGB")
    if was in ("links", "rechts"):
        im = im.transpose(Image.Transpose.ROTATE_90 if was == "links" else Image.Transpose.ROTATE_270)
    elif was == "spiegeln":
        im = ImageOps.mirror(im)
    elif was in ("heller", "dunkler"):
        im = ImageEnhance.Brightness(im).enhance(1.25 if was == "heller" else 0.8)
    elif was == "kontrast":
        im = ImageEnhance.Contrast(im).enhance(1.3)
    elif was == "schwarzweiss":
        im = ImageOps.grayscale(im).convert("RGB")
    elif was == "quadrat":
        side = min(im.size)
        im = ImageOps.fit(im, (side, side))
    elif was == "kleiner":
        if min(im.size) < 96:     # half of it would be a thumbnail
            raise ValueError("klein")
        im = im.resize((im.width // 2, im.height // 2), Image.Resampling.LANCZOS)
    meta = PngImagePlugin.PngInfo()
    for k, v in marks.items():
        meta.add_itxt(k, v)
    out = io.BytesIO()
    im.save(out, "PNG", pnginfo=meta, optimize=True)
    return out.getvalue(), im.width, im.height


@router.post("/api/bilder/{pid}/schnell", dependencies=[Depends(assistant)])
async def bilder_quick(pid: str, request: Request, prof=Depends(browser_profile)):
    """Ich → Bilder Schnellknöpfe: {was} from QUICK on one of the profile's own pictures, done at once."""
    uid = _edit_prof(_prof(request, prof))["id"]
    guard.limit(request, "bildschnell", uid)
    body = await json_body(request, 1024, lenient=True)
    was = str(body.get("was") or "")
    if was not in QUICK:
        raise HTTPException(400, "unbekannter Knopf")
    src = own_pic(uid, pid) if ID.fullmatch(pid) else None
    if src is None:
        print(f"bilder: schnell nicht gemacht quelle fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "kein solches Bild")
    lim = limits()
    if used_bytes(uid) >= lim["store_mb"] * 1024 * 1024 or len(all_pics(uid)) >= MAX_PICS:
        print(f"bilder: schnell nicht gemacht voll fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, "Deine Bilder brauchen schon den ganzen Platz; bitte erst alte löschen (Ich → Bilder).")
    try:
        png, w, h = await asyncio.wait_for(asyncio.to_thread(quick_png, src, was), 20)
    except (ValueError, asyncio.TimeoutError):
        print(f"bilder: schnell nicht gemacht {was} fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, "Das geht mit diesem Bild nicht.")
    row = keep(uid, png, {"w": w, "h": h, "prompt": "", "wish": QUICK[was][0], "format": "", "src": "schnell",
                          "art": "schnell", "von": pid})
    _count.bump("quick")
    print(f"bilder: schnell {was} {w}x{h} fuer {profiles.log_name(prof)}", flush=True)
    return public(row)


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
            _png, d = await schwer.run("bild", None, None, lambda: paint(TEST_PROMPT, 512, 512))
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
