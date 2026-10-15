"""Notbetrieb mit Parakeet (plan Raspberry-Pi split B5c, Dominik 4b and "Feste Sätze" 2026-10-15).

When the models run on another computer and it has not answered for steuer.GONE seconds, the panel is in Notbetrieb
(wartung.notbetrieb): every question gets the fixed sentence. With the admin switch chat.notbetrieb_asr (Funktionen →
Notbetrieb mit Parakeet, off by default) the panel computer still hears: its own Parakeet (asr_proxy.py with
SPEECH_SPARK_NOTASR=1 on 127.0.0.1:NOTASR_PORT, loaded at the first recording, unloaded after NOTASR_IDLE seconds)
takes the recordings (common.model_url sends "asr" there while hoert() is true), and a few fixed commands work by
fixed rules, without any language model:

    switching in Home Assistant (homeassistant.is_command, the panel's own path)  "Erledigt." / "Das hat nicht geklappt."
    the time ("Wie spät ist es?")                                                 "Es ist 14 Uhr 20."
    the own reminders (intent.DIRECT reminder_list)                               "Du hast 2 Erinnerungen." + the list as text

Everything else keeps the fixed sentence (wartung.NOTBETRIEB). The speech output runs on the model computer too, so a
speaker or Home Assistant hears these answers from files made while it was there (make_clips, in the loop of
wartung.py): whole sentences and building blocks for the time and the count, never a name or a text of a profile.
Browser and apps show the answer as text. Logs: "notbetrieb: …" with fixed words and numbers.
"""
import datetime
import os
import re

import httpx

import common
import features
import steuer
from common import STATE, load_config

CLIPS = os.path.join(STATE, "notbetrieb-saetze")     # 16-bit PCM, 24 kHz, mono, one file per building block
CLIP_DAYS = 7          # made anew once a week (voice or model may have changed)
CLIP_RETRY = 600       # seconds between two tries when the speech output failed
PER_TICK = 40          # files made in one round of the loop (the round has other work too)
RATE = 24000
COUNT_MAX = 9          # "Du hast 9 Erinnerungen."; more is "viele"

# the fixed sentences: key -> (German, English); the time and the count are built from blocks below
SAETZE = {"erledigt": ("Erledigt.", "Done."),
          "fehler": ("Das hat nicht geklappt.", "That did not work."),
          "ha_weg": ("Home Assistant ist gerade nicht erreichbar.", "Home Assistant cannot be reached right now."),
          "keine": ("Du hast keine Erinnerungen.", "You have no reminders."),
          "viele": ("Du hast viele Erinnerungen, sie stehen im Panel.", "You have many reminders, they are in the panel.")}
UHR = re.compile(r"(?i)\W*(hey |hallo )?(spark,? )?(wie spät ist es( jetzt| gerade)?|wie ?viel uhr ist es( jetzt| gerade)?|"
                 r"(sag mir )?(die )?uhrzeit|what time is it( now)?|what's the time)\W*")
_n = {"commands": 0, "fixed": 0}
_clip_try = {"t": 0.0}


def admin_on(c=None):
    return features.admin_on("notbetriebasr", c)


def hoert(cfg=None, now=None):
    """Parakeet on this computer hears: the models run elsewhere, the admin switched it on and they are gone."""
    try:
        cfg = load_config() if cfg is None else cfg
        return steuer.remote(cfg) and admin_on(cfg.get("chat", {})) and steuer.weg(now)
    except Exception:
        return False


common.ASR_UMWEG = hoert   # common.model_url: "asr" goes to this computer's Parakeet while it hears


def _blocks(en):
    """Every block a speaker may need: (file key, text)."""
    i = 1 if en else 0
    out = [(k, v[i]) for k, v in SAETZE.items()]
    out.append(("es_ist", "It is" if en else "Es ist"))
    out += [(f"h{h}", f"{h}" if en else f"{h} Uhr") for h in range(24)]
    out += [(f"m{m}", (f"oh {m}" if m < 10 else f"{m}") if en else f"{m}") for m in range(1, 60)]
    out += [(f"n{k}", (f"You have {k} reminder{'s' if k != 1 else ''}." if en else
                       f"Du hast {k} Erinnerung{'en' if k != 1 else ''}.")) for k in range(1, COUNT_MAX + 1)]
    return out


def uhrzeit(now, en=False):
    """(text, blocks) for the time; `now` is an aware datetime the caller gives (never the clock here)."""
    h, m = now.hour, now.minute
    if en:
        return f"It is {h}:{m:02d}.", ["es_ist", f"h{h}"] + ([f"m{m}"] if m else [])
    return (f"Es ist {h} Uhr {m}." if m else f"Es ist {h} Uhr."), ["es_ist", f"h{h}"] + ([f"m{m}"] if m else [])


def erinnerungen(items, zone, en=False):
    """(text, blocks) for the own reminders: the count to hear, the list only as text."""
    if not items:
        return SAETZE["keine"][1 if en else 0], ["keine"]
    k = len(items)
    head = SAETZE["viele"][1 if en else 0] if k > COUNT_MAX else dict(_blocks(en))[f"n{k}"]
    lines = [datetime.datetime.fromtimestamp(x["due"] / 1000, zone).strftime("%d.%m. %H:%M") + ": " + str(x["text"])[:120]
             for x in items[:20]]
    return head + "\n" + "\n".join(lines), ["viele" if k > COUNT_MAX else f"n{k}"]


def satz(key, en=False):
    return SAETZE[key][1 if en else 0], [key]


_last = {}   # text -> blocks of the latest fixed answers, so the speaker finds its files (few, newest kept)


def merken(text, blocks):
    _last[text.split("\n")[0]] = blocks
    while len(_last) > 20:
        _last.pop(next(iter(_last)))
    return text


async def antwort(turn, en, now=None, zaehlen=True):
    """The fixed answer for this turn in Notbetrieb, or None (then the fixed sentence). Runs no model: HA through the
    panel's own path (chat._ha_panel), the time, the own reminders. Also for a used-up Kontingent (verbrauch.py, chat.py):
    zaehlen=False keeps it out of the Notbetrieb's own numbers."""
    import chat
    who = turn.who
    text = str(turn.messages[-1].get("content") or "") if turn.messages else ""
    zone = chat.user_zone(turn.body.get("tz"))
    if turn.ha_direct and turn.ha:
        _n["commands"] += 1 if zaehlen else 0
        try:
            ok, _answer, _targets, *_ = await chat._ha_panel(turn, turn.ha, turn.ha_direct, en, who, turn.src)
        except (httpx.HTTPError, ValueError) as e:   # also a proxy page instead of JSON: a fixed sentence, never the error
            print("notbetrieb: befehl fehlgeschlagen", type(e).__name__, flush=True)
            return merken(*satz("ha_weg", en))
        except Exception as e:   # the Notaus holds every action off (homeassistant.notaus.NotausAktiv)
            print("notbetrieb: befehl fehlgeschlagen", type(e).__name__, flush=True)
            return merken(*satz("fehler", en))
        print("notbetrieb: befehl", "ok" if ok else "nicht_ok", flush=True)
        return merken(*satz("erledigt" if ok else "fehler", en))
    if UHR.fullmatch(text):
        _n["commands"] += 1 if zaehlen else 0
        print("notbetrieb: uhrzeit", flush=True)
        return merken(*uhrzeit(now or datetime.datetime.now(zone), en))
    if getattr(turn, "direct", None) == "reminder_list" and who:   # offered only with the profile's own reminders
        import profiles
        items = profiles.reminders(who["id"])
        _n["commands"] += 1 if zaehlen else 0
        print(f"notbetrieb: erinnerungen {len(items)}", flush=True)
        return merken(*erinnerungen(items, zone, en))
    if zaehlen:
        _n["fixed"] += 1
        print("notbetrieb: fester satz", flush=True)
    return None


def ton(text, en=False):
    """The speaker's sound for a fixed answer from the files (make_clips), or None when one block is missing."""
    blocks = _last.get(str(text or "").split("\n")[0])
    if not blocks:
        return None
    pcm = b""
    for b in blocks:
        try:
            with open(_path(b, en), "rb") as f:
                part = f.read(10 * RATE * 2)
        except OSError:
            return None
        pcm += part[:len(part) // 2 * 2] + b"\0\0" * int(RATE * 0.08)
    return pcm or None


def _path(key, en):
    return os.path.join(CLIPS, f"{key}-{'en' if en else 'de'}.pcm")


async def make_clips(now, speak):
    """Makes missing files and those older than CLIP_DAYS, at most PER_TICK in one round of the loop of wartung.py:
    only with the switch on, the models elsewhere and their speech output there. `speak(text)` yields PCM pieces.
    True when it made some."""
    c = load_config()
    if not (steuer.remote(c) and admin_on(c.get("chat", {}))) or now - _clip_try["t"] < CLIP_RETRY:
        return False
    todo = [(k, t, en) for en in (False, True) for k, t in _blocks(en) if not _fresh(_path(k, en), now)][:PER_TICK]
    if not todo:
        return False
    os.makedirs(CLIPS, mode=0o700, exist_ok=True)
    made = 0
    for key, text, en in todo:
        pcm = b""
        try:
            async for piece in speak(text):
                pcm += piece
        except Exception as e:
            _clip_try["t"] = now
            print("notbetrieb: satzdateien fehlgeschlagen", type(e).__name__, made, flush=True)
            return made > 0
        if len(pcm) < RATE // 4:
            _clip_try["t"] = now
            print("notbetrieb: satzdateien fehlgeschlagen zu_kurz", made, flush=True)
            return made > 0
        path = _path(key, en)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(pcm[:10 * RATE * 2])
        os.replace(tmp, path)
        made += 1
    print(f"notbetrieb: satzdateien erneuert {made}", flush=True)
    return True


def _fresh(path, now):
    try:
        return now - os.path.getmtime(path) < CLIP_DAYS * 86400
    except OSError:
        return False


def files_ready(now=None):
    """How many of the speaker's files there are, and how many it needs (Live)."""
    need = [(k, en) for en in (False, True) for k, _ in _blocks(en)]
    return sum(os.path.exists(_path(k, en)) for k, en in need), len(need)


def for_live(now=None):
    """Live: on or off, hearing or not, how many fixed commands and fixed sentences, files ready (only numbers)."""
    c = load_config()
    if not steuer.remote(c):
        return None
    have, need = files_ready()
    return {"on": admin_on(c.get("chat", {})), "hoert": hoert(c, now), "commands": _n["commands"], "fixed": _n["fixed"],
            "files": have, "need": need}
