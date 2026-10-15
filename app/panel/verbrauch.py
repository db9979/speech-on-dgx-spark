"""Verbrauchszähler (plan plaene/token-zaehler.md, Dominik 2026-10-14 „1b 2a 3b 4a 5a 6b 7a“).

How much the models of the Spark do, in numbers only: the language model in tokens (read, of them from its cache,
written), Einordnung in questions, speech recognition and speech output in seconds of audio, the meaning search in
texts, re-ranking in pairs, pictures in pieces. Per task ("Gespräch", "Steckbrief", "Verbessern" …, each in one
fixed area of BEREICHE) and per profile ("Gäste" and "Spark selbst" apart). Never a question, an answer or a name of
a document: only numbers, fixed task names and profile ids.

Counting costs nothing in a turn: add() only adds numbers to dicts in memory under a lock. A timer thread writes
state/verbrauch.json at most every SAVE_S seconds (common.write_json, atomic). Kept: KEEP_DAYS days per day,
KEEP_MONTHS months per month, KEEP_HOURS hours per hour and model (for „24 h“). The places that count:
  - the conversation: chat.llm_round, from the last piece of the stream (stream_options include_usage)
  - background work: vorrang.post, from the finished answer ("usage")
  - the few callers of the model outside vorrang (intent, schreib, docmake, images, fixes, health, tidy): response()
  - Einordnung: systemone._note, one question per answer
  - speech: audio() where the panel calls speech recognition or speech output
  - meaning search and re-ranking: docembed and nachsortieren, texts and pairs
An answer without "usage" counts its characters / CHARS_PER_TOKEN, marked as estimated (its own number).

Who: the context variable WHO, set for every API request (panel middleware) and every turn (chat.llm), or the job's
own profile passed as who (vorrang.post); else "Spark selbst". Profiles that no longer exist are folded into "Gelöschte Profile" when the file is written.

Daily quota (Tageskontingent, chat.usage_quota): language model tokens a profile may use per day, for all its own
requests together (chat.usage_quota_k thousand, per profile in state/verbrauch-kontingent.json, 0 = no limit).
Admin profiles are never limited. Reached: the conversation answers with one fixed sentence until midnight;
background work keeps running (nobody asked for it, it would only go stale).

    GET    /api/admin/verbrauch?zeit=24h|30t|12m   Zustand → Verbrauch, the iPhone app's admin part
    POST   /api/admin/verbrauch/leeren             empties every counter (admin protocol)
    PUT    /api/admin/verbrauch/kontingent         {"uid", "k"}: one profile's own daily quota (None: the default)
    GET    /api/profile/verbrauch?zeit=30t|12m      Ich → Verbrauch, own numbers only
    DELETE /api/profile/verbrauch                  own history (today's tokens stay for the quota)
"""
import atexit
import contextvars
import json
import os
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import CONFIG_PATH, STATE, load_config, write_json
from core import assistant, auth, own_profile

router = APIRouter()
FILE = os.path.join(STATE, "verbrauch.json")                    # the counters (statistics, not backed up)
QUOTA_FILE = os.path.join(STATE, "verbrauch-kontingent.json")   # the admin's own quotas per profile (backed up)
SAVE_S = 60                  # written at most this often
KEEP_DAYS, KEEP_MONTHS, KEEP_HOURS = 35, 13, 48
MAX_KEYS = 600               # rows per day or month; more fold into "Sonstige" (a bound for the file)
CHARS_PER_TOKEN = 3.5        # for an answer without "usage"
RATE_S = 60                  # Live: tokens per minute over the last minute
QUOTA_MAX_K = 100000         # 100 million tokens a day: the largest quota the admin may set
GUEST, SPARK, GONE = "g", "s", "x"

# the models: key -> (name de, name en, unit); the unit says what "amount" counts
MODELS = {"llm": ("Sprachmodell", "Language model", "tok"),
          "systemone": ("Einordnung", "Classification", "fragen"),
          "asr": ("Spracherkennung", "Speech recognition", "sek"),
          "tts": ("Sprachausgabe", "Speech output", "sek"),
          "embed": ("Bedeutungssuche", "Meaning search", "texte"),
          "rerank": ("Nachsortieren", "Re-ranking", "paare"),
          "bild": ("Bilder", "Pictures", "bilder")}
UNITS = {"tok": ("Tokens", "tokens"), "fragen": ("Fragen", "questions"), "sek": ("Sekunden", "seconds"),
         "texte": ("Texte", "texts"), "paare": ("Paare", "pairs"), "bilder": ("Bilder", "pictures")}
BEREICHE = {"gespraech": ("Gespräch", "Conversation"), "weiche": ("Weiche", "Switch"),
            "hintergrund": ("Hintergrund", "Background"), "assistent": ("Assistent und Verbessern", "Assistant and improving"),
            "pruefen": ("Prüfen und Qualität", "Checks and quality"), "agent": ("Agent und MCP", "Agent and MCP"),
            "begleiter": ("Begleiter", "Companion"), "dokumente": ("Dokumente", "Documents"),
            "sonstige": ("Sonstige", "Other")}
# every task that counts: its fixed name (the vorrang job names and the callers' own) -> its area.
# tests/test_verbrauch.py finds every job name in the code and wants it here.
AUFGABEN = {
    # the conversation and what belongs to answering
    "Gespräch": "gespraech", "Bild beschreiben": "gespraech", "Antwort sprechen": "gespraech", "Frage hören": "gespraech",
    "Lautsprecher": "gespraech", "Telegram": "gespraech", "Home Assistant Assist": "gespraech", "Stimme anhören": "gespraech",
    "Beschwerde": "gespraech",
    # the switch
    "Weiche": "weiche", "Werkzeugwahl": "weiche",
    # background work (vorrang)
    "Lernen aus Gesprächen": "hintergrund", "Lernen": "hintergrund", "Korrekturen lernen": "hintergrund",
    "Proaktiver Hinweis": "hintergrund", "Gedächtnis-Themen": "hintergrund", "Gedächtnis aufräumen": "hintergrund",
    "Kamerabild": "hintergrund", "Steckbrief": "hintergrund", "Dokument lesen": "hintergrund",
    "Tagesüberblick": "hintergrund", "Postfach aufräumen": "hintergrund", "Mail sortieren": "hintergrund", "Wichtige Mail": "hintergrund",
    "reMarkable": "hintergrund", "reMarkable: Sprachmodell": "hintergrund", "Suchindex": "hintergrund",
    "Treffer nachsortieren": "hintergrund", "Dokumente suchen": "hintergrund",
    # the settings assistant and Verbessern
    "Verbessern": "assistent", "Einstellungs-Assistent": "assistent",
    # checks
    "Prüffrage": "pruefen", "Qualitätstest": "pruefen", "Prüfen": "pruefen", "Messen": "pruefen",
    "Antwort prüfen": "pruefen", "Einordnung messen": "pruefen", "Dienst prüfen": "pruefen", "Suchprüfung": "pruefen",
    # agent, MCP, companion, documents
    "Agent": "agent", "MCP": "agent", "Schreibhilfe": "begleiter", "Begleiter": "begleiter",
    "Dokument erstellen": "dokumente", "Bild malen": "dokumente",
}

WHO = contextvars.ContextVar("verbrauch_who", default=SPARK)
_lock = threading.Lock()
_days, _months, _hours = {}, {}, {}      # "2026-10-14" / "2026-10" -> {"model|aufgabe|who": [n, in, cached, out, amount, ms, est]}
_today = {"day": "", "who": {}}          # tokens of the language model per who today (the quota, fast)
_rate = deque(maxlen=4000)               # (time, tokens) of the language model, the last RATE_S seconds (Live)
_said = set()                            # (day, uid) whose reached quota was logged already (one line a day)
_unknown = set()                         # task names logged once as unknown
_st = {"loaded": False, "dirty": False, "timer": None, "cfg": (None, None)}
N, IN, CACHED, OUT, AMOUNT, MS, EST = range(7)


# ---------------------------------------------------------------- switches
def _chat():
    """The chat section, read again only when config.json changed (a stat per count, no file read)."""
    try:
        st = os.stat(CONFIG_PATH)
        m = (st.st_mtime_ns, st.st_ino, st.st_size)
    except OSError:
        m = None
    if _st["cfg"][0] != m or m is None:
        _st["cfg"] = (m, load_config().get("chat", {}))
    return _st["cfg"][1]


def on(c=None):
    """The admin counts (Funktionen → Verbrauchszähler, chat.usage_count): Spark-wide, never a right of a profile
    (test_sperre_ueberall.ADMIN_ON_OK)."""
    try:
        return features.admin_on("verbrauch", _chat() if c is None else c)
    except Exception:
        return False


def quota_on(c=None):
    try:
        return features.admin_on("kontingent", _chat() if c is None else c)
    except Exception:
        return False


def who_of(prof):
    return prof["id"] if prof and prof.get("id") else GUEST


# ---------------------------------------------------------------- counting (no file, no network, never raises)
def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _row(table, period, key):
    rows = table.setdefault(period, {})
    if key not in rows and len(rows) >= MAX_KEYS:   # a bound for the file: more rows fold into "Sonstige"
        m, _, w = key.split("|")
        key = f"{m}|Sonstige|{w}"
    return rows.setdefault(key, [0, 0, 0, 0, 0.0, 0, 0])


def add(model, aufgabe, who=None, prompt=0, cached=0, out=0, amount=0.0, ms=0, est=False, now=None):
    """Counts one call. Only numbers; the task is a fixed name of AUFGABEN (another counts as "Sonstige")."""
    try:
        if model not in MODELS or not on():
            return
        if aufgabe not in AUFGABEN:
            if aufgabe not in _unknown and len(_unknown) < 50:
                _unknown.add(aufgabe)
                print("verbrauch: unbekannte Aufgabe, zählt unter Sonstige", flush=True)
            aufgabe = "Sonstige"
        who = who or WHO.get() or SPARK
        now = time.time() if now is None else now
        prompt, cached, out = max(0, int(prompt or 0)), max(0, int(cached or 0)), max(0, int(out or 0))
        amount, ms = max(0.0, float(amount or 0)), max(0, int(ms or 0))
        tok = prompt + out
        _load()
        key, d = f"{model}|{aufgabe}|{who}", _day(now)
        hour, month = time.strftime("%Y-%m-%d %H", time.localtime(now)), d[:7]
        with _lock:
            for table, period, k in ((_days, d, key), (_months, month, key), (_hours, hour, f"{model}|-|-")):
                r = _row(table, period, k)
                r[N] += 1
                r[IN] += prompt
                r[CACHED] += cached
                r[OUT] += out
                r[AMOUNT] += amount
                r[MS] += ms
                r[EST] += 1 if est else 0
            if model == "llm":
                if _today["day"] != d:
                    _today["day"], _today["who"] = d, {}
                _today["who"][who] = _today["who"].get(who, 0) + tok
                _rate.append((now, tok))
            _st["dirty"] = True
            if _st["timer"] is None:
                t = threading.Timer(SAVE_S, _flush_later)
                t.daemon = True
                _st["timer"] = t
                t.start()
    except Exception as e:   # counting never stops an answer
        print("verbrauch: Zählen fehlgeschlagen,", type(e).__name__, flush=True)


def llm(aufgabe, usage, ms=0, chars_in=0, chars_out=0, who=None):
    """The language model's numbers from an OpenAI "usage" (None: estimated from the characters)."""
    u = usage if isinstance(usage, dict) else {}
    if isinstance(u.get("prompt_tokens"), int):
        det = u.get("prompt_tokens_details") if isinstance(u.get("prompt_tokens_details"), dict) else {}
        out = u.get("completion_tokens") if isinstance(u.get("completion_tokens"), int) else 0
        add("llm", aufgabe, who, u["prompt_tokens"], det.get("cached_tokens") or 0, out, ms=ms)
    else:
        add("llm", aufgabe, who, int(chars_in / CHARS_PER_TOKEN), 0, int(chars_out / CHARS_PER_TOKEN), ms=ms, est=True)


def response(aufgabe, r, payload=None, who=None):
    """After a finished (not streamed) answer of the language model: its usage, else an estimate. Never raises."""
    try:
        if not on() or r is None or getattr(r, "status_code", 0) != 200:
            return
        try:
            ms = int(r.elapsed.total_seconds() * 1000)
        except Exception:
            ms = 0
        data = r.json()
        usage = data.get("usage") if isinstance(data, dict) else None
        cin = len(json.dumps((payload or {}).get("messages") or "", ensure_ascii=False)) if usage is None else 0
        cout = 0
        if usage is None:
            try:
                cout = len(data["choices"][0]["message"].get("content") or "")
            except (KeyError, IndexError, TypeError, AttributeError):
                cout = 0
        llm(aufgabe, usage, ms, cin, cout, who)
    except Exception as e:
        print("verbrauch: Antwort nicht lesbar,", type(e).__name__, flush=True)


def audio(model, aufgabe, seconds, ms=0, who=None):
    """Seconds of audio heard (asr) or spoken (tts)."""
    if seconds and seconds > 0:
        add(model, aufgabe, who, amount=round(float(seconds), 2), ms=ms)


def heard(aufgabe, r, who=None):
    """After an answer of the speech recognition: the seconds it heard (its "usage" or "duration"). Never raises."""
    try:
        if not on() or getattr(r, "status_code", 0) != 200:
            return
        d = r.json()
        d = d if isinstance(d, dict) else {}
        secs = (d.get("usage") or {}).get("seconds") if isinstance(d.get("usage"), dict) else None
        secs = secs if isinstance(secs, (int, float)) else d.get("duration")
        if isinstance(secs, (int, float)) and not isinstance(secs, bool):
            audio("asr", aufgabe, secs, int(r.elapsed.total_seconds() * 1000), who)
    except Exception as e:
        print("verbrauch: Spracherkennung nicht lesbar,", type(e).__name__, flush=True)


def spoken(aufgabe, pcm_bytes=0, wav=None, who=None, ms=0):
    """Speech output made: 16-bit mono PCM at 24 kHz (48000 bytes a second) or a WAV file."""
    try:
        if wav is not None:
            from admin import wav_seconds
            secs = wav_seconds(bytes(wav)) or 0
        else:
            secs = max(0, int(pcm_bytes or 0)) / 48000
        audio("tts", aufgabe, secs, ms, who)
    except Exception as e:
        print("verbrauch: Sprachausgabe nicht zählbar,", type(e).__name__, flush=True)


# ---------------------------------------------------------------- the file
def _read(path, default):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _load():
    if _st["loaded"]:
        return
    with _lock:
        if _st["loaded"]:
            return
        d = _read(FILE, {})
        for table, k in ((_days, "days"), (_months, "months"), (_hours, "hours")):
            src = d.get(k) if isinstance(d.get(k), dict) else {}
            for period, rows in src.items():
                if isinstance(rows, dict):
                    table[str(period)[:13]] = {str(key)[:200]: [float(x) if i == AMOUNT else int(x) for i, x in enumerate(v[:7])]
                                               for key, v in list(rows.items())[:MAX_KEYS]
                                               if isinstance(v, list) and len(v) >= 7 and all(isinstance(x, (int, float)) for x in v[:7])}
        today = _day(time.time())
        _today["day"], _today["who"] = today, {}
        for key, v in (_days.get(today) or {}).items():
            m, _, w = key.split("|")
            if m == "llm":
                _today["who"][w] = _today["who"].get(w, 0) + v[IN] + v[OUT]
        _st["loaded"] = True


def _trim(now):
    days = sorted(_days)[:-KEEP_DAYS] if len(_days) > KEEP_DAYS else []
    for k in days:
        _days.pop(k, None)
    for k in (sorted(_months)[:-KEEP_MONTHS] if len(_months) > KEEP_MONTHS else []):
        _months.pop(k, None)
    for k in (sorted(_hours)[:-KEEP_HOURS] if len(_hours) > KEEP_HOURS else []):
        _hours.pop(k, None)


def _fold_gone(have):
    """Rows of profiles that are gone become "Gelöschte Profile" (no id of a deleted profile stays); under _lock."""
    have = set(have) | {GUEST, SPARK, GONE}
    for table in (_days, _months):
        for period, rows in table.items():
            for key in [k for k in rows if k.rsplit("|", 1)[-1] not in have]:
                m, a, _ = key.split("|")
                v = rows.pop(key)
                r = rows.setdefault(f"{m}|{a}|{GONE}", [0, 0, 0, 0, 0.0, 0, 0])
                for i in range(7):
                    r[i] += v[i]


def save(now=None):
    """Writes the counters (atomic); called by the timer, at the end and by tests."""
    _load()
    try:
        have = profiles.user_ids()
    except Exception as e:
        have = None
        print("verbrauch: Profile nicht lesbar,", type(e).__name__, flush=True)
    with _lock:
        if have is not None:
            _fold_gone(have)
        _trim(time.time() if now is None else now)
        data = {"v": 1, "days": _days, "months": _months, "hours": _hours}
        text = json.loads(json.dumps(data))
        _st["dirty"] = False
    try:
        write_json(FILE, text)
    except OSError as e:
        print("verbrauch: Speichern fehlgeschlagen,", type(e).__name__, flush=True)
        return False
    return True


def _flush_later():
    _st["timer"] = None
    if _st["dirty"]:
        save()


@atexit.register
def _at_exit():
    if _st["dirty"]:
        save()


def clear(who=None, keep_today=False):
    """Empties every counter (who None) or one profile's rows (who), today's tokens kept for the quota."""
    _load()
    today = _day(time.time())
    with _lock:
        if who is None:
            for x in (_days, _months, _hours, _rate, _today["who"]):
                x.clear()
        else:
            for table in (_days, _months):
                for period, rows in table.items():
                    for key in [k for k in rows if k.rsplit("|", 1)[-1] == who]:
                        v = rows.pop(key)
                        if keep_today and key.startswith("llm|") and period in (today, today[:7]):
                            # what the quota counts today stays: today's row, and in the month only today's part
                            day = v if period == today else (_days.get(today) or {}).get(key)
                            if day:
                                rows[key] = list(day)
        _st["dirty"] = True
    save()


# ---------------------------------------------------------------- quota
def quotas():
    d = _read(QUOTA_FILE, {})
    own = d.get("own") if isinstance(d.get("own"), dict) else {}
    return {u: int(k) for u, k in own.items() if isinstance(k, int) and not isinstance(k, bool) and 0 <= k <= QUOTA_MAX_K}


def limit(uid, c=None):
    """Tokens a day for this profile (0: no limit). Admin profiles are never limited, nor a profile the admin took
    out of the quota (Funktionen → Wer darf was: „Tageskontingent“ gesperrt heißt, es gilt nicht für dieses Profil)."""
    if not uid or uid in (GUEST, SPARK) or not features.allowed("kontingent", uid, c):
        return 0
    try:
        import coadmin
        if coadmin.acts(uid) == "admin":
            return 0
    except Exception:
        pass
    own = quotas()
    if uid in own:
        return own[uid] * 1000
    c = _chat() if c is None else c
    k = c.get("usage_quota_k", 2000)
    return int(k) * 1000 if isinstance(k, int) and not isinstance(k, bool) and k > 0 else 0


def used_today(who, now=None):
    _load()
    d = _day(time.time() if now is None else now)
    with _lock:
        return _today["who"].get(who, 0) if _today["day"] == d else 0


def over(uid, now=None):
    """True when the profile used up its daily quota (the conversation then says QUOTA_TEXT)."""
    try:
        lim = limit(uid)
        if not lim:
            return False
        used = used_today(uid, now)
        if used < lim:
            return False
        day = _day(time.time() if now is None else now)
        if (day, uid) not in _said:
            _said.add((day, uid))
            print(f"verbrauch: Kontingent erreicht | {profiles.log_name(profiles.by_id(uid))} | {used} von {lim} Tokens", flush=True)
        return True
    except Exception as e:
        print("verbrauch: Kontingent nicht prüfbar,", type(e).__name__, flush=True)
        return False


class Quota(RuntimeError):
    """The profile's daily quota is used up (chat.py answers with QUOTA_TEXT)."""


QUOTA_TEXT = ("Für heute ist dein Kontingent beim Sprachmodell aufgebraucht. Ab Mitternacht geht es weiter; "
              "wie viel du verbraucht hast, steht unter Ich → Verbrauch.",
              "Your daily quota for the language model is used up. It goes on after midnight; how much you used is "
              "under Me → Usage.")


# ---------------------------------------------------------------- reading
def _periods(zeit, now):
    """The periods of a view and the table they come from."""
    if zeit == "12m":
        t = time.localtime(now)
        out, y, m = [], t.tm_year, t.tm_mon
        for _ in range(12):
            out.append(f"{y:04d}-{m:02d}")
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        return out[::-1], _months
    if zeit == "24h":
        return [time.strftime("%Y-%m-%d %H", time.localtime(now - 3600 * i)) for i in range(23, -1, -1)], _hours
    return [_day(now - 86400 * i) for i in range(29, -1, -1)], _days


def _split(key):
    m, a, w = key.split("|")
    return m, a, w


def _empty():
    return [0, 0, 0, 0, 0.0, 0, 0]


def _plus(a, b):
    for i in range(7):
        a[i] += b[i]


def _model_row(m, v):
    de, en, unit = MODELS[m]
    return {"id": m, "name": [de, en], "unit": unit, "unit_name": list(UNITS[unit]), "calls": v[N],
            "read": v[IN], "cached": v[CACHED], "written": v[OUT], "amount": round(v[AMOUNT], 1),
            "ms": int(v[MS] / v[N]) if v[N] else 0, "estimated": v[EST]}


def _model_name(m, c):
    if m == "llm":
        name = str(c.get("llm_model") or "").strip()
        return [name[:60], name[:60]] if name else list(MODELS[m][:2])
    return list(MODELS[m][:2])


def report(zeit="30t", who=None, now=None):
    """The numbers of a view: per period (bars), per model, per area, per task, per profile (who None) or for one
    profile (who). Numbers and fixed names only."""
    _load()
    now = time.time() if now is None else now
    zeit = zeit if zeit in ("24h", "30t", "12m") else "30t"
    periods, table = _periods(zeit, now)
    c = _chat()
    with _lock:
        snap = {p: {k: list(v) for k, v in (table.get(p) or {}).items()} for p in periods}
        today_rows = {k: list(v) for k, v in (_days.get(_day(now)) or {}).items()}
    bars, models, areas, tasks, people = [], {}, {}, {}, {}
    for p in periods:
        per = {}
        for key, v in snap[p].items():
            m, a, w = _split(key)
            if who is not None and zeit != "24h" and w != who:
                continue
            if zeit != "24h":
                b = AUFGABEN.get(a, "sonstige")
                if m == "llm":
                    per[b] = per.get(b, 0) + v[IN] + v[OUT]
                    _plus(areas.setdefault(b, _empty()), v)
                    _plus(tasks.setdefault(a, _empty()), v)
                _plus(people.setdefault(w, {}).setdefault(m, _empty()), v)
            else:
                per["alle"] = per.get("alle", 0) + (v[IN] + v[OUT] if m == "llm" else 0)
            _plus(models.setdefault(m, _empty()), v)
        bars.append({"p": p, "by": per})
    tday = {}
    for key, v in today_rows.items():
        m, a, w = _split(key)
        if who is not None and w != who:
            continue
        _plus(tday.setdefault(m, _empty()), v)
    out = {"on": on(c), "zeit": zeit, "bars": bars, "bereiche": {k: list(v) for k, v in BEREICHE.items()},
           "models": [dict(_model_row(m, models[m]), name=_model_name(m, c)) for m in MODELS if m in models],
           "today": {m: _model_row(m, v) for m, v in tday.items()},
           "areas": [{"id": b, "name": list(BEREICHE[b]), "read": v[IN], "written": v[OUT], "cached": v[CACHED], "calls": v[N]}
                     for b, v in sorted(areas.items(), key=lambda x: -(x[1][IN] + x[1][OUT]))],
           "tasks": [{"name": a, "area": AUFGABEN.get(a, "sonstige"), "read": v[IN], "written": v[OUT], "calls": v[N],
                      "estimated": v[EST]} for a, v in sorted(tasks.items(), key=lambda x: -(x[1][IN] + x[1][OUT]))[:40]]}
    if who is None:
        names = {u["id"]: u["name"] for u in profiles.names()}
        rows = []
        for w, ms in people.items():
            llm_v = ms.get("llm") or _empty()
            rows.append({"id": w if w in names else "", "kind": "profil" if w in names else {GUEST: "gast", SPARK: "spark"}.get(w, "geloescht"),
                         "name": names.get(w, ""), "tokens": llm_v[IN] + llm_v[OUT],
                         "heard": round((ms.get("asr") or _empty())[AMOUNT], 1), "spoken": round((ms.get("tts") or _empty())[AMOUNT], 1),
                         "pictures": int((ms.get("bild") or _empty())[AMOUNT]),
                         "limit": limit(w) if w in names else 0, "today": used_today(w, now) if w in names else 0})
        out["profiles"] = sorted(rows, key=lambda r: -r["tokens"])
        out["quota"] = {"on": quota_on(c), "k": c.get("usage_quota_k", 2000), "own": {u: k for u, k in quotas().items() if u in names}}
        out["rate"] = rate(now)
    else:
        lim = limit(who)
        out["quota"] = {"on": bool(lim), "limit": lim, "used": used_today(who, now)}
    return out


def rate(now=None):
    """Tokens of the language model in the last minute (Live)."""
    now = time.time() if now is None else now
    with _lock:
        return sum(t for x, t in _rate if now - x < RATE_S)


def heute(now=None):
    """Today's numbers for the Technik pages („Heute“): numbers only, keys vb_*."""
    _load()
    now = time.time() if now is None else now
    with _lock:
        rows = dict(_days.get(_day(now)) or {})
    out = {}
    for key, v in rows.items():
        m = key.split("|", 1)[0]
        for k, val in ((f"vb_{m}_calls", v[N]), (f"vb_{m}_in", v[IN]), (f"vb_{m}_out", v[OUT]), (f"vb_{m}_cached", v[CACHED]),
                       (f"vb_{m}_amount", v[AMOUNT])):
            out[k] = out.get(k, 0) + val
    return {k: int(round(v)) for k, v in out.items()}


def for_live(now=None):
    """Zustand → Live, the box of the language model: tokens per minute and today (numbers only)."""
    if not on():
        return {"on": False}
    h = heute(now)
    return {"on": True, "rate": rate(now), "today": h.get("vb_llm_in", 0) + h.get("vb_llm_out", 0),
            "calls": h.get("vb_llm_calls", 0)}


def for_zustand(now=None):
    """Zustand → Monitoring, the card „Verbrauch heute“ (numbers only)."""
    if not on():
        return {"on": False}
    r = report("30t", now=now)
    t = r["today"]
    llm_v = t.get("llm") or {}
    by = (r["bars"][-1]["by"] if r["bars"] else {})
    total = sum(by.values())
    top = max(by.items(), key=lambda x: x[1]) if by else None
    return {"on": True, "tokens": llm_v.get("read", 0) + llm_v.get("written", 0), "read": llm_v.get("read", 0),
            "cached": llm_v.get("cached", 0), "heard": (t.get("asr") or {}).get("amount", 0),
            "spoken": (t.get("tts") or {}).get("amount", 0), "pictures": (t.get("bild") or {}).get("amount", 0),
            "top": {"id": top[0], "name": list(BEREICHE.get(top[0], BEREICHE["sonstige"])),
                    "pct": round(100 * top[1] / total) if total else 0} if top and total else None}


# ---------------------------------------------------------------- own data (Ich, features.OWN)
def own_count(uid):
    _load()
    with _lock:
        return sum(1 for table in (_days, _months) for rows in table.values() for k in rows if k.rsplit("|", 1)[-1] == uid)


def _own_clear(uid):
    clear(uid, keep_today=True)
    print(f"verbrauch: eigene Zahlen gelöscht | {profiles.log_name(profiles.by_id(uid))}", flush=True)


features.OWN["verbrauch"] = (own_count, _own_clear)


# ---------------------------------------------------------------- routes
def _zeit(z):
    return z if z in ("24h", "30t", "12m") else "30t"


@router.get("/api/admin/verbrauch", dependencies=[Depends(auth)])
def admin_report(request: Request, zeit: str = "30t"):
    guard.limit(request, "verbrauch", admin=True)
    if not on():
        return {"on": False, "quota": {"on": quota_on()}}
    return report(_zeit(zeit))


@router.get("/api/admin/verbrauch/heute", dependencies=[Depends(auth)])
def admin_today(request: Request):
    guard.limit(request, "verbrauch", admin=True)
    return for_zustand()


@router.post("/api/admin/verbrauch/leeren", dependencies=[Depends(auth)])
def admin_clear(request: Request):
    guard.limit(request, "verbrauchset", admin=True)
    clear()
    print("verbrauch: alle Zähler geleert", flush=True)
    return {"ok": True}


@router.put("/api/admin/verbrauch/kontingent", dependencies=[Depends(auth)])
async def admin_quota(request: Request):
    guard.limit(request, "verbrauchset", admin=True)
    body = await request.json()
    uid, k = (body or {}).get("uid"), (body or {}).get("k")
    if not isinstance(uid, str) or uid not in profiles.user_ids():
        raise HTTPException(404, "Dieses Profil gibt es nicht.")
    if k is not None and (not isinstance(k, int) or isinstance(k, bool) or not 0 <= k <= QUOTA_MAX_K):
        raise HTTPException(400, f"Kontingent: 0 bis {QUOTA_MAX_K} Tausend Tokens oder leer für die Vorgabe.")
    d = _read(QUOTA_FILE, {})
    own = {u: v for u, v in (d.get("own") or {}).items() if u in profiles.user_ids()} if isinstance(d.get("own"), dict) else {}
    if k is None:
        own.pop(uid, None)
    else:
        own[uid] = k
    write_json(QUOTA_FILE, {"own": own})
    print(f"verbrauch: Kontingent gesetzt | {profiles.log_name(profiles.by_id(uid))} | "
          + ("Vorgabe" if k is None else f"{k} Tausend Tokens"), flush=True)
    return {"ok": True}


@router.get("/api/profile/verbrauch", dependencies=[Depends(assistant)])
def profile_report(request: Request, zeit: str = "30t", prof=Depends(own_profile)):
    uid = prof["id"]
    guard.limit(request, "verbrauch", uid)
    if not features.allowed("verbrauch", uid):
        raise HTTPException(403, ("Der Verbrauchszähler geht für dich gerade nicht. " + features.missing_text("verbrauch", uid)).strip())
    z = _zeit(zeit)
    return report("30t" if z == "24h" else z, who=uid)


@router.delete("/api/profile/verbrauch", dependencies=[Depends(assistant)])
def profile_clear(request: Request, prof=Depends(own_profile)):
    guard.limit(request, "verbrauchset", prof["id"])
    _own_clear(prof["id"])
    return {"ok": True}
