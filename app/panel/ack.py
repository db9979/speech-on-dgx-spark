"""Instant acknowledgement (admin chat.instant_ack under "Gezielte Werkzeugwahl", profile "instant_ack"; both off,
never guests; plan plaene/schnellere-antwort.md "Sofortige Rückmeldung").

Right after the question, before the model has read a word, the Spark says in a short ready-made sentence what it
is doing now ("Ich schau in deinen Kalender."). Never a result, never a yes or no: only what it does next. Which
sentence follows from fixed rules on the person's own words (the Weiche group of intent.py, "Erst lokal", a direct
fetch), never from the model. Small talk gets none (its answer is quick anyway, a "Moment" before it sounds odd).

The sentences are recorded once per voice (same voice, speed, instructions and language as the answer) in a pause
of the TTS (speech first, lowest stage, see record_missing) and kept in STATE/ack/ as raw PCM. Playing them costs no GPU. A sentence that
is not recorded yet is left out this time and recorded afterwards; the generated filler of a tool round
(chat.FILLERS) then speaks as before. When the answer has not started after BRIDGE_S seconds, one second short
sentence bridges the wait (at most once).

Growing the list: every Weiche group needs its sentences (self-test test_ack.Coverage fails for a new group
without any), and Zustand → Prüfen shows which kind of question went without a sentence most often today
(stats), so frequent cases get their sentences too. The log names only the group, never what was asked.
"""
import asyncio
import base64
import hashlib
import json
import os
import random
import re
import threading
import time

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
BRIDGE_S = 6.0          # seconds after the question without any sound of the answer: the second sentence
MAX_CLIPS = 1000        # recordings kept at most (oldest go first); one is ~1-2 s, 50-100 KB
MAX_CLIP_BYTES = 8 * 48000   # 8 s of 16-bit mono PCM at 24 kHz
CHUNK = 9600            # bytes per audio event (0.2 s)
NO_ACK = ("smarthome", "plaudern", "lean")   # a direct command is quick, small talk needs none

# Per Weiche group (intent.GROUPS) and a few panel ways: (German, English) variants. ack.pick takes one at random
# among the recorded ones, never one of the profile's last few (Dominik 2026-10-12: more variety, never monotonous).
PHRASES = {
    "kalender": (("Ich schau in deinen Kalender.", "Let me check your calendar."),
                 ("Moment, ich schau in den Kalender.", "One moment, checking your calendar."),
                 ("Ich werf mal einen Blick in den Kalender.", "Let me have a look at your calendar."),
                 ("Mal sehen, was im Kalender steht.", "Let's see what's in your calendar."),
                 ("Einen Augenblick, ich prüf deine Termine.", "Just a second, checking your appointments."),
                 ("Ich hol mir kurz deine Termine.", "Getting your appointments."),
                 ("Okay, ich schau, was ansteht.", "Okay, let me see what's coming up."),
                 ("Gleich, ich öffne deinen Kalender.", "Hang on, opening your calendar.")),
    "mail": (("Ich schau in deine Mails.", "Let me check your e-mail."),
             ("Moment, ich schau ins Postfach.", "One moment, checking your inbox."),
             ("Ich werf einen Blick in dein Postfach.", "Let me have a look at your inbox."),
             ("Mal sehen, was an Mails da ist.", "Let's see what mail there is."),
             ("Einen Augenblick, ich hol deine Mails.", "Just a second, fetching your mail."),
             ("Okay, ich seh nach, was Neues da ist.", "Okay, let me see what's new."),
             ("Gleich, ich öffne dein Postfach.", "Hang on, opening your inbox.")),
    "websuche": (("Ich suche kurz im Netz.", "Let me search the web."),
                 ("Moment, ich schau im Internet nach.", "One moment, looking it up online."),
                 ("Ich frag mal kurz das Internet.", "Let me ask the internet."),
                 ("Einen Augenblick, ich recherchiere.", "Just a second, researching that."),
                 ("Mal sehen, was das Netz dazu sagt.", "Let's see what the web says."),
                 ("Okay, ich such dir das raus.", "Okay, I'll look that up for you."),
                 ("Gleich, ich schau online nach.", "Hang on, checking online."),
                 ("Gute Frage, ich such kurz.", "Good question, let me search.")),
    "erinnerung": (("Okay, einen Moment.", "Okay, one moment."),
                   ("Moment.", "One moment."),
                   ("Alles klar, Augenblick.", "Alright, just a second."),
                   ("Gut, ich kümmere mich drum.", "Right, I'll see to it."),
                   ("Okay, ich schau mir das an.", "Okay, let me take care of that."),
                   ("Einen Augenblick bitte.", "Just a moment, please."),
                   ("Verstanden, kleinen Moment.", "Got it, one second.")),
    "liste": (("Moment, ich schau auf die Liste.", "One moment, checking the list."),
              ("Ich werf einen Blick auf die Liste.", "Let me look at the list."),
              ("Einen Augenblick, ich hol die Liste.", "Just a second, getting the list."),
              ("Okay, ich kümmere mich um die Liste.", "Okay, I'll see to the list."),
              ("Gleich, ich öffne die Liste.", "Hang on, opening the list."),
              ("Mal sehen, was auf der Liste steht.", "Let's see what's on the list.")),
    "wetter": (("Ich schau nach dem Wetter.", "Let me check the weather."),
               ("Moment, ich hol das Wetter.", "One moment, getting the weather."),
               ("Mal sehen, was das Wetter macht.", "Let's see what the weather's doing."),
               ("Einen Augenblick, ich prüf die Vorhersage.", "Just a second, checking the forecast."),
               ("Ich werf einen Blick auf die Vorhersage.", "Let me look at the forecast."),
               ("Okay, ich schau aus dem digitalen Fenster.", "Okay, peeking out the digital window."),
               ("Gleich, ich hol die Wetterdaten.", "Hang on, fetching the weather.")),
    "bahn": (("Ich schau nach den Verbindungen.", "Let me check the connections."),
             ("Moment, ich prüf den Fahrplan.", "One moment, checking the timetable."),
             ("Einen Augenblick, ich such eine Verbindung.", "Just a second, finding a connection."),
             ("Mal sehen, was fährt.", "Let's see what's running."),
             ("Okay, ich schau, wie du hinkommst.", "Okay, let me see how you get there."),
             ("Gleich, ich frag die Bahn.", "Hang on, asking the railway.")),
    "paket": (("Ich schau nach deinen Paketen.", "Let me check your parcels."),
              ("Moment, ich verfolge die Sendung.", "One moment, tracking the shipment."),
              ("Mal sehen, wo dein Paket steckt.", "Let's see where your parcel is."),
              ("Einen Augenblick, ich prüf die Sendungen.", "Just a second, checking your deliveries."),
              ("Okay, ich schau, was unterwegs ist.", "Okay, let me see what's on its way.")),
    "kontakt": (("Moment, ich schau in die Kontakte.", "One moment, checking your contacts."),
                ("Ich werf einen Blick ins Adressbuch.", "Let me look in your address book."),
                ("Einen Augenblick, ich such den Kontakt.", "Just a second, finding the contact."),
                ("Mal sehen, was im Adressbuch steht.", "Let's see what's in your address book."),
                ("Gleich, ich öffne deine Kontakte.", "Hang on, opening your contacts.")),
    "gedaechtnis": (("Okay, einen Moment.", "Okay, one moment."),
                    ("Alles klar, Augenblick.", "Alright, just a second."),
                    ("Moment, ich überleg kurz.", "One moment, let me think."),
                    ("Verstanden, kleinen Moment.", "Got it, one second."),
                    ("Gut, ich kümmere mich drum.", "Right, I'll see to it.")),
    "dokument": (("Ich schau in deinen Dokumenten nach.", "Let me check your documents."),
                 ("Moment, ich schau in die Dokumente.", "One moment, looking at your documents."),
                 ("Ich blätter kurz durch deine Unterlagen.", "Let me leaf through your papers."),
                 ("Einen Augenblick, ich such das Dokument.", "Just a second, finding the document."),
                 ("Mal sehen, was in deinen Unterlagen steht.", "Let's see what your documents say."),
                 ("Okay, ich durchsuche deine Dokumente.", "Okay, searching your documents."),
                 ("Gleich, ich schau in deine Ablage.", "Hang on, checking your files.")),
    "erstellen": (("Moment, ich kümmere mich um das Dokument.", "One moment, I'll see to the document."),
                  ("Okay, einen Moment, ich bereite das vor.", "Okay, one moment, I'll prepare it."),
                  ("Alles klar, ich setz das auf.", "Alright, I'll draft that."),
                  ("Gut, ich mach mich an die Arbeit.", "Right, getting to work on it."),
                  ("Einen Augenblick, ich schreib das zusammen.", "Just a second, putting it together."),
                  ("Verstanden, ich fang gleich an.", "Got it, starting on it now.")),
    "nachricht": (("Moment.", "One moment."),
                  ("Einen Augenblick.", "Just a second."),
                  ("Alles klar, kleinen Moment.", "Alright, one second."),
                  ("Okay, ich kümmere mich drum.", "Okay, I'll see to it."),
                  ("Verstanden, Augenblick.", "Got it, just a moment.")),
    "agent": (("Moment, ich frag kurz nach.", "One moment, I'll ask."),
              ("Einen Augenblick, ich kläre das.", "Just a second, sorting that out."),
              ("Okay, ich kümmere mich drum.", "Okay, I'll see to it."),
              ("Alles klar, ich frag mal herum.", "Alright, let me ask around."),
              ("Gleich, ich hol mir die Auskunft.", "Hang on, getting the details.")),
    "iphone": (("Einen Moment.", "One moment."),
               ("Augenblick, ich schau aufs Handy.", "Just a second, checking the phone."),
               ("Okay, kleinen Moment.", "Okay, one second."),
               ("Alles klar, ich kümmere mich drum.", "Alright, I'll see to it."),
               ("Gleich, ich frag dein Handy.", "Hang on, asking your phone.")),
    "spark": (("Moment, ich schau in der Anleitung nach.", "One moment, checking the guide."),
              ("Ich blätter kurz in meiner Anleitung.", "Let me flip through my guide."),
              ("Einen Augenblick, ich schau, wie das geht.", "Just a second, let me see how that works."),
              ("Mal sehen, was die Anleitung sagt.", "Let's see what the guide says."),
              ("Gute Frage, ich schau kurz nach.", "Good question, let me check.")),
    "wikipedia": (("Ich schau kurz in der Wikipedia nach.", "Let me check Wikipedia."),
                  ("Moment, ich frag die Wikipedia.", "One moment, asking Wikipedia."),
                  ("Mal sehen, was die Wikipedia weiß.", "Let's see what Wikipedia knows."),
                  ("Einen Augenblick, ich schlag das nach.", "Just a second, looking that up."),
                  ("Gute Frage, ich schlag kurz nach.", "Good question, let me look it up."),
                  ("Okay, ich schau im Lexikon.", "Okay, checking the encyclopedia.")),
    "archiv": (("Ich schau in deinem Archiv nach.", "Let me check your archive."),
               ("Moment, ich schlag im Archiv nach.", "One moment, looking it up in the archive."),
               ("Mal sehen, was das Archiv dazu hat.", "Let's see what the archive has."),
               ("Einen Augenblick, ich durchsuche das Archiv.", "Just a second, searching the archive."),
               ("Gute Frage, ich schau ins Archiv.", "Good question, checking the archive."),
               ("Okay, ich blätter im Archiv.", "Okay, browsing the archive.")),
    # panel ways, not Weiche groups
    "lokal": (("Ich schau kurz nach.", "Let me look that up."),
              ("Moment, ich schau nach.", "One moment, let me check."),
              ("Einen Augenblick, ich such das raus.", "Just a second, digging that out."),
              ("Mal sehen, was ich dazu finde.", "Let's see what I can find."),
              ("Gute Frage, ich schau mal.", "Good question, let me see."),
              ("Okay, ich schau in meine Unterlagen.", "Okay, checking my sources."),
              ("Gleich, ich such kurz.", "Hang on, searching.")),
    "bridge": (("Dauert einen Moment länger.", "This takes a little longer."),
               ("Gleich hab ich's.", "Almost there."),
               ("Ich bin noch dran.", "Still on it."),
               ("Einen kleinen Moment noch.", "Just a little longer."),
               ("Fast fertig, gleich kommt's.", "Nearly ready, coming right up."),
               ("Noch einen Augenblick, bitte.", "One more moment, please."),
               ("Ich sortier das noch kurz.", "Just sorting it out."),
               ("Das braucht etwas länger als gedacht.", "This is taking a bit longer than expected."),
               ("Bleib dran, gleich geht's weiter.", "Stay with me, nearly there."),
               ("Ich hab's fast zusammen.", "I've almost got it together.")),
}

_recent = {}            # uid -> the last sentences said to this profile, newest last (RAM only)
RECENT = 6              # never one of the last RECENT sentences while another is recorded
_making = set()         # cache keys being recorded right now
_lock = threading.Lock()
stats = {}              # day -> {"with": n, "without": n, "groups": {group: n}} (RAM only, for Zustand)


def _dir():
    return os.path.join(STATE, "ack")


def lang_of(english):
    return "English" if english else "German"


def key(tts_body, text, lang):
    """The recording's name: the same voice, speed, instructions and language as the answer, and the text."""
    k = {"v": str(tts_body.get("voice") or ""), "s": tts_body.get("speed") or 1.0,
         "i": str(tts_body.get("instructions") or ""), "l": lang, "t": text}
    return hashlib.sha256(json.dumps(k, sort_keys=True).encode()).hexdigest()[:40]


def _path(k):
    return os.path.join(_dir(), k + ".pcm") if re.fullmatch(r"[0-9a-f]{40}", k or "") else None


def clip(k):
    """The recorded PCM (bytes) or None."""
    p = _path(k)
    try:
        with open(p, "rb") as f:
            data = f.read(MAX_CLIP_BYTES + 1)
    except (OSError, TypeError):
        return None
    return data if 0 < len(data) <= MAX_CLIP_BYTES else None


def save(k, pcm):
    p = _path(k)
    if not p or not pcm or len(pcm) > MAX_CLIP_BYTES:
        return False
    os.makedirs(_dir(), mode=0o700, exist_ok=True)
    tmp = p + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "wb") as f:
        f.write(pcm)
    os.replace(tmp, p)
    _trim()
    return True


def _trim():
    try:
        files = [os.path.join(_dir(), n) for n in os.listdir(_dir()) if n.endswith(".pcm")]
    except OSError:
        return
    if len(files) <= MAX_CLIPS:
        return
    files.sort(key=lambda p: os.path.getmtime(p))
    for p in files[:len(files) - MAX_CLIPS]:
        try:
            os.remove(p)
        except OSError:
            pass


def chunks(pcm):
    """The recording as base64 pieces for {"type": "audio"} events (the browser plays them like the answer)."""
    for i in range(0, len(pcm), CHUNK):
        yield base64.b64encode(pcm[i:i + CHUNK]).decode()


def group_of(route_names, direct=None, local=False):
    """Which sentences fit this turn (fixed rules): the one Weiche group, else "lokal" for a "Erst lokal" look,
    else None (small talk, a smart home command, several groups at once, nothing recognised)."""
    names = [n for n in (route_names or []) if n not in NO_ACK]
    if direct in ("weather",):
        return "wetter"
    if direct in ("calendar_events",):
        return "kalender"
    if direct in ("mail_list",):
        return "mail"
    if direct in ("parcels",):
        return "paket"
    if direct == "spark_hilfe":
        return "spark"
    if len(names) == 1 and names[0] in PHRASES and not set(route_names or []) & set(NO_ACK):
        return names[0]
    if local and not route_names:
        return "lokal"
    return None


def pick(group, uid, english=False, have=None, bump=True):
    """A sentence of the group for this profile: at random among the recorded ones (have(text) -> bool), never one
    of the profile's last RECENT sentences while another fits (so it does not sound like a recording), else the
    one said longest ago. None when the group has none or none is recorded yet."""
    opts = [v[1 if english else 0] for v in PHRASES.get(group) or ()]
    if have is not None:
        opts = [t for t in opts if have(t)]
    if not opts:
        return None
    with _lock:
        last = _recent.get(uid or "", [])
        fresh = [t for t in opts if t not in last]
        text = random.choice(fresh) if fresh else min(opts, key=last.index)
        if bump:
            _recent[uid or ""] = (last + [text])[-RECENT:]
            if len(_recent) > 500:
                _recent.clear()
    return text


def phrase(group, uid, english=False, bump=True):
    """pick() without looking at the recordings."""
    return pick(group, uid, english, None, bump)


def all_texts(english=False):
    """Every sentence once, the first variant of each group first (recorded in this order, so every group soon
    has one)."""
    rows = [[v[1 if english else 0] for v in opts] for opts in PHRASES.values()]
    return list(dict.fromkeys(t for i in range(max(map(len, rows))) for r in rows if i < len(r) for t in [r[i]]))


def count(group, ok, now=None):
    """For Zustand → Prüfen: answers with and without a ready sentence today, and the groups that went without."""
    day = time.strftime("%Y-%m-%d", time.localtime(now if now is not None else time.time()))
    with _lock:
        for d in [d for d in stats if d != day]:
            del stats[d]
        s = stats.setdefault(day, {"with": 0, "without": 0, "groups": {}})
        s["with" if ok else "without"] += 1
        if not ok:
            s["groups"][group] = s["groups"].get(group, 0) + 1


def today(now=None):
    day = time.strftime("%Y-%m-%d", time.localtime(now if now is not None else time.time()))
    s = stats.get(day) or {"with": 0, "without": 0, "groups": {}}
    top = sorted(s["groups"].items(), key=lambda x: -x[1])[:3]
    return {"with": s["with"], "without": s["without"], "top": [{"group": g, "n": n} for g, n in top]}


def recorded(tts_body, lang):
    """For pick(): is this sentence recorded in this voice and language?"""
    return lambda t: os.path.exists(_path(key(tts_body, t, lang)))


def missing_ok(tts_body, lang):
    """True when every sentence of this voice and language is recorded."""
    return all(os.path.exists(_path(key(tts_body, t, lang))) for t in all_texts(lang == "English"))


_later = set()


def later(coro):
    """Runs coro in the background (the reference is kept until it ends)."""
    task = asyncio.ensure_future(coro)
    _later.add(task)
    task.add_done_callback(_later.discard)
    return task


async def _record(c, url, headers, body):
    """One sentence through the TTS (stream, PCM): the bytes or None."""
    pcm = b""
    async with c.stream("POST", url, json=dict(body, stream=True, response_format="pcm"), headers=headers) as r:
        if r.status_code != 200:
            return None
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if ev.get("type") == "speech.audio.delta" and ev.get("audio"):
                try:
                    pcm += base64.b64decode(ev["audio"])
                except ValueError:
                    return None
                if len(pcm) > MAX_CLIP_BYTES:
                    return None
    return pcm or None


async def record_missing(url, headers, tts_body, lang, texts=None, sleep=asyncio.sleep):
    """Records every sentence of this voice and language that is missing, in a pause (speech first: it waits until
    nobody spoke for vorrang.GRACE seconds, asks the TTS with the lowest stage so a person's request goes first, and
    stops as soon as an answer streams again; the rest follows after the next answer that misses one)."""
    import httpx
    import stufe
    import vorrang
    texts = texts or all_texts(lang == "English")
    todo = []
    with _lock:
        for t in dict.fromkeys(texts):
            k = key(tts_body, t, lang)
            if k not in _making and clip(k) is None:
                _making.add(k)
                todo.append((k, t))
    if not todo:
        return 0
    made = 0
    body = {x: tts_body[x] for x in ("voice", "speed", "instructions") if tts_body.get(x)}
    hdrs = dict(headers, **stufe.headers("hinten"))
    try:
        await vorrang.quiet("Sätze für die Rückmeldung", sleep)
        start = time.time()
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as c:
            for k, t in todo:
                if vorrang._local[0] > start:   # an answer streams again: the rest in the next pause
                    break
                try:
                    pcm = await _record(c, url, hdrs, dict(body, input=t, language=lang))
                except Exception as e:   # the TTS restarting ...: next time again
                    print(f"ack: recording stopped ({type(e).__name__})", flush=True)
                    break
                if pcm and save(k, pcm):
                    made += 1
    finally:
        with _lock:
            for k, _ in todo:
                _making.discard(k)
    print(f"ack: {made} of {len(todo)} sentence(s) recorded for one voice ({lang})", flush=True)
    return made
