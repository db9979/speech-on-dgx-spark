"""Home Assistant per profile: each profile connects its own Home Assistant (address and long-lived
access token); only that profile's requests can use it, guests never.

    USERS_DIR/<user id>/homeassistant.json  {"url", "token", "verify", "agent", "language"}

Commands go to Home Assistant's own Assist (POST /api/conversation/process), so Home Assistant
decides what is allowed: only the entities exposed to Assist (Settings → Voice assistants →
Expose) can be switched there, and the token's user rights apply. Devices Assist does not know are
switched by calling their service directly (POST /api/services/<domain>/<service>), only for the
entity's own domain and never for locks, alarm systems or updates. Questions about states read
GET /api/states instead, which sees every entity, zone and person the token's user can see, so
nothing has to be exposed for asking; rooms come from the area registry (POST /api/template, admin
tokens only; without it entities are still found by name). The token never leaves the Spark
again: the panel only learns whether one is stored.

A profile can set a code word: then nothing is switched until the user's own latest message holds
it. The panel checks that itself (the model never decides), and the code word is replaced by
"[Codewort]" before anything reaches the model or the stored conversations. Only a salted hash of
it is kept (and that sealed by vault.py), so it cannot be read back; reading states needs no code.
"""
import asyncio
import functools
import hashlib
import json
import os
import re
import threading
import time

import httpx

import profiles
import vault

_lock = threading.Lock()


def _file(uid):
    return profiles._path(uid, "homeassistant.json")


def _raw(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("url") and d.get("token") else None
    except (OSError, ValueError):
        return None


def get(uid):
    """The connection with the plain token (stored encrypted, see vault.py)."""
    d = _raw(uid)
    if d:
        d["token"] = vault.open_(d["token"])
    return d if d and d["token"] else None


def public(uid):
    d = get(uid)
    return {"url": d["url"], "verify": d.get("verify", True), "agent": d.get("agent", ""),
            "has_token": True, "has_code": bool(d.get("code")),
            "code_old": bool(d.get("code")) and code_state(d).startswith(("old", "unreadable"))} if d \
        else {"url": "", "verify": True, "agent": "", "has_token": False, "has_code": False}


def entry(body, old=None):
    """A checked connection from the panel's form; an empty token keeps the stored one."""
    url = str(body.get("url", "")).strip().rstrip("/")
    if not re.fullmatch(r"https?://[^\s/]{1,200}(/[^\s]{0,200})?", url, re.I):
        raise ValueError("the address must start with http:// or https://, e.g. http://homeassistant.local:8123")
    token = str(body.get("token", "")).strip()
    if not token and old and old.get("url", "").rstrip("/").lower() == url.lower():
        token = old.get("token", "")  # same address: the stored token stays (a new address needs it typed again)
    if not re.fullmatch(r"[\w.\-]{20,1000}", token):
        raise ValueError("a long-lived access token is required (Home Assistant: your profile → Security)")
    agent = str(body.get("agent", "")).strip()
    if agent and not re.fullmatch(r"[\w.\-]{1,100}", agent):
        raise ValueError("invalid agent id")
    return {"url": url, "token": token, "verify": body.get("verify", True) is not False, "agent": agent}


def save(uid, item):
    with _lock:
        old = _raw(uid) or {}
        keep = {"code": old["code"]} if old.get("code") else {}  # a new connection keeps the code word
        profiles._write(_file(uid), dict(item, token=vault.seal(item["token"]), updated=int(time.time()), **keep))
    return public(uid)


# ---- code word for changes ----

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]+|[0-9]+")  # "Apollo13" is two words, like "Apollo 13"


def _tok(word):
    """One word as compared: lower case, umlauts spelled out, numbers as German words, so "Apollo 13"
    and "Apollo dreizehn" are the same code word whichever way speech recognition writes it."""
    if word.isdigit():
        try:
            from textnorm import speak_numbers
            word = speak_numbers(word, "de")
        except ImportError:
            pass
        if word.isdigit():  # without num2words: the small built-in German numbers
            word = _de_number(int(word)) if len(word) <= 6 else word
    return _norm(word).replace(" ", "")


_ONES = "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn " \
        "sechzehn siebzehn achtzehn neunzehn".split()
_TENS = "_ _ zwanzig dreißig vierzig fünfzig sechzig siebzig achtzig neunzig".split()


def _de_number(n):
    """German words for 0..999999 as num2words writes them (so a code word compares the same)."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        one = "ein" if n % 10 == 1 else _ONES[n % 10]
        return (one + "und" if n % 10 else "") + _TENS[n // 10]
    if n < 1000:
        head = "ein" if n // 100 == 1 else _ONES[n // 100]
        return head + "hundert" + (_de_number(n % 100) if n % 100 else "")
    head = "ein" if n // 1000 == 1 else _de_number(n // 1000)
    return head + "tausend" + (_de_number(n % 1000) if n % 1000 else "")


def _words(text):
    return [_tok(m.group(0)) for m in _WORD.finditer(str(text))]


@functools.lru_cache(maxsize=4096)
def _hash(salt, joined):
    return hashlib.pbkdf2_hmac("sha256", joined.encode(), bytes.fromhex(salt), 3000).hex()


def set_code(uid, code):
    """Sets the code word (an empty one removes it); raises ValueError when it is too weak. It is
    stored encrypted (vault.py), never sent back, and compared with some tolerance for how speech
    recognition spells it."""
    words = _words(code)
    joined = "".join(words)
    if joined and (len(joined) < 4 or len(words) > 6):
        raise ValueError("the code word needs at least 4 letters and at most 6 words")
    with _lock:
        d = _raw(uid)
        if not d:
            raise ValueError("connect Home Assistant first")
        d.pop("code", None)
        if joined:
            d["code"] = vault.seal(json.dumps({"v": 2, "code": joined, "words": len(words)}))
        profiles._write(_file(uid), d)
    return public(uid)


def _code(item):
    try:
        c = json.loads(vault.open_(item.get("code") or "") or "null")
        return c if isinstance(c, dict) and (c.get("code") or c.get("hash")) else None
    except ValueError:
        return {"code": "\0unreadable", "words": 1}  # sealed with another key: never matches


def _dist(a, b, limit):
    """Edit distance of a and b, or limit + 1 once it is above limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _fits(code, joined):
    if code.get("code"):  # tolerate a letter or two misheard: Apolo, Appollo, dreizehen
        want = code["code"]
        return _dist(joined, want, 0 if len(want) < 6 else 1 if len(want) < 10 else 2) <= (
            0 if len(want) < 6 else 1 if len(want) < 10 else 2)
    return _hash(code["salt"], joined) == code["hash"]  # older versions kept only a hash: exact


def _spans(code, text):
    """Character spans of the code word in a text: windows of about its word count, compared without
    spaces, so speech recognition may split or join its words."""
    toks = list(_WORD.finditer(str(text)))
    norm = [_tok(m.group(0)) for m in toks]
    n = int(code.get("words") or 1)
    found = []
    for k in sorted({max(1, n - 1), n, n + 1}):
        for i in range(len(toks) - k + 1):
            if _fits(code, "".join(norm[i:i + k])):
                found.append((toks[i].start(), toks[i + k - 1].end()))
    return found


def code_state(item):
    """For the journal, never the word itself."""
    c = _code(item) if item else None
    return "none" if not c else "unreadable" if c.get("code") == "\0unreadable" else \
        "old hash (save it again)" if c.get("hash") else f"set, {c.get('words')} word(s)"


def needs_code(item):
    return bool(item and _code(item))


def code_given(item, text):
    c = _code(item)
    return bool(c and _spans(c, text))


def redact(item, text):
    """The text with the code word replaced by [Codewort]."""
    c = _code(item) if item else None
    if not c or not isinstance(text, str):
        return text
    end = len(text) + 1
    for a, b in sorted(_spans(c, text), reverse=True):
        if b <= end:  # windows of different length can overlap; the first one wins
            text, end = text[:a] + "[Codewort]" + text[b:], a
    return text


def seal_stored(uid):
    """Encrypts a token that an older version stored in plain text."""
    d = _raw(uid)
    if d and not str(d["token"]).startswith(vault.PREFIX) and vault.available():
        with _lock:
            profiles._write(_file(uid), dict(d, token=vault.seal(d["token"])))


def remove(uid):
    with _lock:
        try:
            import os
            os.remove(_file(uid))
        except OSError:
            pass
    return public(uid)


def _client(item):
    return httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), verify=item.get("verify", True),
                             headers={"Authorization": f"Bearer {item['token']}"})


async def check(item):
    """Raises ValueError with a readable reason when Home Assistant cannot be used."""
    try:
        async with _client(item) as c:
            r = await c.get(item["url"] + "/api/")
    except httpx.HTTPError as e:
        raise ValueError(f"Home Assistant not reachable: {type(e).__name__}")
    if r.status_code == 401:
        raise ValueError("Home Assistant rejected the token (401)")
    if r.status_code != 200:
        raise ValueError(f"Home Assistant answered HTTP {r.status_code}")
    try:
        r.json()
    except ValueError:
        raise ValueError("this address does not look like Home Assistant (no JSON from /api/)")
    return {"ok": True}


async def command(item, text, language="de"):
    """Hands one spoken command to Home Assistant's Assist; when Assist does not know the device, finds
    it among all states and switches it directly (see fallback). Whatever Assist reports, the states of
    the devices it names are read back afterwards, and only that counts. Returns (ok, answer, targets)."""
    ok, speech, targets, unknown, ids = await _assist(item, text, language)
    if unknown:
        done, more = await fallback(item, text)
        if more:
            return done, more, []
        return False, speech + " (Assist did not find this device or did not understand the sentence; it only " \
            "knows devices exposed to Assist. Look the device up with home_assistant_states and switch it with " \
            "home_assistant_action.)", []
    if not ok:
        return False, "Home Assistant reports: " + speech + " Nothing was switched.", targets
    service = _intent(text)
    if not ids and targets:  # older Home Assistant: only names; find their ids by exact name
        async with _client(item) as c:
            r = await c.get(item["url"] + "/api/states")
            all_states = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
        ids = [x["entity_id"] for x in all_states if isinstance(x, dict)
               and (x.get("attributes") or {}).get("friendly_name") in targets][:10]
    if not ids:
        _log("assist: success without entity ids, cannot verify", repr(text[:80]))
        return False, ("Assist answered '" + speech + "' but named no device, so the result could not be checked. "
                       "Look the device up with home_assistant_states and use home_assistant_action."), targets
    async with _client(item) as c:
        checked = await _verify(c, item, ids, service, {})
    return _report(checked, service, "Assist")[0], _report(checked, service, "Assist")[1], targets


_IMPERATIVE = set("schalte schalt mach mache stell stelle dreh drehe oeffne oeffnen schliess schliesse fahr fahre "
                  "turn switch open close".split())
_ASKING = set("ist sind wie was welche welcher welches wo wann hast hat laeuft brennt warum is are what which "
              "where how".split())
_SUBJECT = set("ich wir du er sie es man das der die mein meine i we it the my".split())
_MODAL = set("kannst koenntest wuerdest bitte can could would please".split())


def clean_command(text):
    """The command without the code word and its lead-in ("Codewort ist ...")."""
    t = str(text).replace("[Codewort]", " ")
    t = re.sub(r"\b[Tt]\.?\s?[Vv]\b\.?", "TV", t)  # speech recognition: "T V", "T.V."
    t = re.sub(r"(?i)\b(und\s+)?(das\s+)?code\s*-?\s*wort(\s+(ist|lautet))?\b[:,]?", " ", t)
    return re.sub(r"\s+", " ", t).strip(" ,.;:-")


def is_command(text):
    """A switching command, by its words: "Schalte den Fernseher aus", "Kannst du bitte das Licht
    einschalten?", "Fernseher aus bitte", "Hey Spark, mach das Licht im Bad an". Questions about a state
    ("Ist das Licht an?", "Wie warm ist es?") and statements ("Ich habe das Licht an gelassen") are not."""
    t = clean_command(text)
    words = [w for w in re.findall(r"\w+", _norm(t)) if w not in ("hey", "hallo", "spark", "ok", "okay")]
    if not words or not _intent(t):
        return False
    if words[0] in _MODAL or any(w in _IMPERATIVE for w in words[:4]):
        return True
    if t.endswith("?") or words[0] in _ASKING or words[0] in _SUBJECT:
        return False
    # short commands: "Fernseher aus", "Licht an im Wohnzimmer", "Bitte den Fernseher ausschalten"
    return len(words) <= 8


def _intent(text):
    words = re.findall(r"\w+", _norm(text))
    return next((svc for svc, verbs in _VERBS if any(w in verbs.split() for w in words)), None)


def _log(*parts):
    print("homeassistant:", *parts, flush=True)


# expected states after a service, by service; None: no fixed state to expect
_EXPECT = {"turn_off": {"off", "standby", "closed", "idle", "not_home"},
           "close_cover": {"closed", "closing"}, "open_cover": {"open", "opening"}}


def _expected(service, before, now):
    if now in ("unavailable", "unknown") and service != "turn_on":
        return None  # some devices drop off when switched off: say what it shows, claim nothing
    if service in ("turn_off", "close_cover", "open_cover"):
        return now in _EXPECT[service]
    if service == "turn_on":
        return now not in ("off", "standby", "unavailable", "unknown")
    if service == "toggle":
        return (now != before) if before is not None else None
    return None


_VERIFY_WAIT = 0.7  # seconds between read-backs; six tries cover devices that take a few seconds


async def _verify(c, item, eids, service, before, tries=6):
    """Reads the states back until they show the service's effect (or the tries are used up).
    Returns [(entity id, name, state, True/False/None)]."""
    result = []
    for i in range(tries):
        result = []
        for eid in eids:
            r = await c.get(f"{item['url']}/api/states/{eid}")
            st = r.json() if r.status_code == 200 else {}
            now = st.get("state", "unknown")
            name = (st.get("attributes") or {}).get("friendly_name") or eid
            result.append((eid, name, now, _expected(service, before.get(eid), now)))
        if all(x[3] is not False for x in result) or i == tries - 1:
            break
        await asyncio.sleep(_VERIFY_WAIT)
    _log("verify", service, [(x[0], x[2], x[3]) for x in result])
    return result


def _report(checked, service, via):
    """Only what Home Assistant's states show, word for word."""
    good = [x for x in checked if x[3]]
    bad = [x for x in checked if x[3] is False]
    open_ = [x for x in checked if x[3] is None]
    lines = ["Checked in Home Assistant afterwards (report only this, do not add anything):"]
    lines += [f"- {n} ({e}) is now '{s}' — done." for e, n, s, _ in good]
    lines += [f"- {n} ({e}) is still '{s}' — NOT done." for e, n, s, _ in bad]
    lines += [f"- {n} ({e}) is now '{s}' ({service or 'command'} sent via {via}; no fixed state to compare)."
              for e, n, s, _ in open_]
    return bool(checked) and not bad, "\n".join(lines)


async def _assist(item, text, language):
    body = {"text": str(text)[:500], "language": language}
    if item.get("agent"):
        body["agent_id"] = item["agent"]
    async with _client(item) as c:
        r = await c.post(item["url"] + "/api/conversation/process", json=body)
    if r.status_code == 401:
        _log("assist: token rejected (401)")
        return False, "Home Assistant rejected the token.", [], False, []
    if r.status_code != 200:
        _log("assist: HTTP", r.status_code, r.text[:200])
    r.raise_for_status()
    res = (r.json() or {}).get("response") or {}
    speech = ((res.get("speech") or {}).get("plain") or {}).get("speech", "")
    data = res.get("data") or {}
    targets = [x.get("name") for x in (data.get("success") or data.get("targets") or []) if x.get("name")]
    failed = [x.get("name") for x in data.get("failed") or [] if x.get("name")]
    ok = res.get("response_type") != "error" and not failed
    if failed:
        speech += " Failed: " + ", ".join(failed)
    # Assist knows only exposed entities and its own sentence patterns
    unknown = res.get("response_type") == "error" and data.get("code") in ("no_valid_targets", "no_intent_match")
    ids = [x["id"] for x in (data.get("success") or []) if x.get("type") == "entity" and "." in str(x.get("id", ""))]
    _log("assist:", repr(str(text)[:80]), "->", res.get("response_type"), data.get("code") or "", ids or targets[:5])
    return ok, speech.strip() or ("Done." if ok else "Home Assistant could not do that."), targets[:10], unknown, ids[:10]


# ---- reading states: every entity the token's user can see, not only those exposed to Assist ----

# words people use for a kind of entity, so "Fenster", "Akku" or "Zone" find it without its name
_KIND = {
    "light": "licht lampe leuchte beleuchtung light lamp", "switch": "schalter steckdose switch plug",
    "climate": "heizung thermostat klima climate heating", "cover": "rollladen rolladen jalousie rollo markise cover blind shutter",
    "lock": "schloss tür tuer lock", "media_player": "fernseher tv musik lautsprecher media speaker",
    "person": "person wo ist anwesend zuhause zu hause who where", "device_tracker": "tracker handy telefon wo ist phone where",
    "zone": "zone zonen ort orte bereich zones place", "sensor": "sensor wert messwert",
    "binary_sensor": "sensor melder", "weather": "wetter weather", "sun": "sonne sonnenaufgang sonnenuntergang sun",
    "fan": "ventilator lüfter luefter fan", "vacuum": "staubsauger saugroboter vacuum", "alarm_control_panel": "alarm alarmanlage",
    "water_heater": "warmwasser boiler", "humidifier": "luftbefeuchter", "camera": "kamera camera",
    "calendar": "kalender", "todo": "liste einkaufsliste todo", "automation": "automation automatisierung",
    "scene": "szene scene", "script": "skript script", "input_boolean": "schalter helfer", "update": "update aktualisierung",
}
_CLASS = {
    "temperature": "temperatur warm kalt grad temperature", "humidity": "luftfeuchte feuchtigkeit humidity",
    "battery": "batterie akku ladung battery", "power": "leistung verbrauch strom watt power",
    "energy": "energie verbrauch strom kwh energy", "window": "fenster offen window", "door": "tür tuer offen door",
    "garage_door": "garage tor", "opening": "offen geöffnet", "motion": "bewegung motion", "occupancy": "anwesenheit belegt",
    "presence": "anwesenheit", "moisture": "wasser leck feucht", "smoke": "rauch rauchmelder", "co2": "co2 luftqualität",
    "carbon_dioxide": "co2 luftqualität", "pm25": "feinstaub", "illuminance": "helligkeit lux", "pressure": "luftdruck",
    "gas": "gas", "tv": "fernseher fernsehen tv glotze", "speaker": "lautsprecher box musik speaker",
    "receiver": "receiver verstaerker anlage", "voltage": "spannung", "current": "strom", "plug": "steckdose", "connectivity": "verbunden online",
}
_STOP = set("der die das den dem des ein eine einen im in ist sind wie was wo welche welcher welches gibt es mir "
            "bitte und oder von vom zum zur auf an aus mit hat haben gerade aktuell jetzt alle alles zeige zeig "
            "sag sage the is are what which where how all any show".split())
_areas_cache = {}  # (url, hash of the token) -> (time, {entity_id: area}): each login sees what it may
# words that say what is asked ("Temperatur", "aktuelle"), never which device: a question about the
# "Whirlpool" must not be answered with another device just because both have a temperature
_GENERIC_ONLY = set("aktuelle aktueller aktuellen aktuelles derzeitige momentane heutige jetzige wert werte "
                    "stand status zustand messwert grad current state value".split())
_GENERIC = _GENERIC_ONLY | set(
    "temperatur temperaturen temperature wassertemperatur grad warm kalt heiss luftfeuchte feuchtigkeit "
    "luftfeuchtigkeit humidity batterie akku ladung battery leistung verbrauch strom watt power energie kwh "
    "energy helligkeit lux luftdruck spannung co2 luftqualitaet feinstaub".split())


def _norm(t):
    t = str(t).lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("_", " "), (".", " ")):
        t = t.replace(a, b)
    return t


async def _areas(c, item):
    key = (item["url"], hashlib.sha256(str(item.get("token", "")).encode()).hexdigest()[:16])
    hit = _areas_cache.get(key)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    tpl = "{% for a in areas() %}{% for e in area_entities(a) %}{{ e }}|{{ area_name(a) }}\n{% endfor %}{% endfor %}"
    found = {}
    try:
        r = await c.post(item["url"] + "/api/template", json={"template": tpl})
        if r.status_code == 200:
            for line in r.text.splitlines():
                e, _, a = line.strip().partition("|")
                if e and a:
                    found.setdefault(e, a)
            _areas_cache[key] = (time.time(), found)  # a failed read is tried again next time
    except httpx.HTTPError:
        pass
    return found


def _line(s, names, area):
    a = s.get("attributes") or {}
    eid = s.get("entity_id", "")
    dom = eid.split(".")[0]
    val = f"{s.get('state', '')}" + (f" {a['unit_of_measurement']}" if a.get("unit_of_measurement") else "")
    extra = []
    if dom == "climate":
        extra += [f"{k}={a[k]}" for k in ("current_temperature", "temperature", "hvac_action", "preset_mode") if a.get(k) is not None]
    elif dom == "cover" and a.get("current_position") is not None:
        extra.append(f"position={a['current_position']}%")
    elif dom == "light" and s.get("state") == "on" and a.get("brightness") is not None:
        extra.append(f"brightness={round(a['brightness'] / 2.55)}%")
    elif dom == "media_player" and a.get("media_title"):
        extra.append(f"playing={a['media_title']}")
    elif dom == "weather":
        extra += [f"{k}={a[k]}" for k in ("temperature", "humidity", "wind_speed") if a.get(k) is not None]
    elif dom == "zone":
        inside = [names.get(p, p) for p in a.get("persons") or []]
        val = f"{s.get('state')} inside" + (f" ({', '.join(inside)})" if inside else "")
        if a.get("radius") is not None:
            extra.append(f"radius={round(a['radius'])} m")
    elif dom in ("person", "device_tracker"):
        val = "zone " + str(s.get("state"))
    if dom not in ("climate", "weather"):  # water heaters, pools, spas: their own temperatures
        extra += [f"{k}={a[k]}" for k in ("current_temperature", "temperature", "target_temp_high")
                  if a.get(k) is not None and not isinstance(a[k], (dict, list))]
    if a.get("device_class") and dom in ("binary_sensor", "cover"):
        extra.append(f"type={a['device_class']}")
    name = a.get("friendly_name") or eid
    return f"{name} ({eid}{', ' + area if area else ''}): {val}" + (f" [{', '.join(extra)}]" if extra else "")


def _hay(s, names, room):
    eid = s["entity_id"]
    dom = eid.split(".")[0]
    a = s.get("attributes") or {}
    dc = a.get("device_class") or ""
    kind = _KIND.get(dom, "")
    if dom == "media_player" and dc:  # a TV is no speaker: the class decides, not the kind
        kind = "media"
    return _norm(" ".join([names[eid], _norm(eid), _norm(room), dom.replace("_", " "), kind, _CLASS.get(dc, ""), dc]))


def _forms(w):
    """A word and its stem without a plural ending: Lichter -> licht, Lampen -> lampe, Rollos -> rollo."""
    out = [w]
    for end in ("ern", "er", "en", "n", "s", "e"):
        if len(w) - len(end) >= 4 and w.endswith(end):
            out.append(w[:-len(end)])
    return out


def _hit(w, hay):
    return any(f in hay for f in _forms(w))


def _correct(words, hays):
    """Words that fit nothing are replaced by the closest word Home Assistant has, when it is close
    (one or two letters off, as speech recognition gets names wrong: "Samsong", "Kelerpumpe")."""
    import difflib
    vocab = None
    out = []
    for w in words:
        if len(w) < 4 or any(_hit(w, h) for h in hays):
            out.append(w)
            continue
        if vocab is None:
            vocab = sorted({t for h in hays for t in h.split() if len(t) >= 4})
        near = [n for n in difflib.get_close_matches(w, vocab, n=3, cutoff=0.8) if abs(len(n) - len(w)) <= 2]
        out.append(near[0] if near else w)  # never a compound to its part ("Pooltemperatur" -> "temperatur")
    return out


def _score(all_states, areas, names, words, domain="", want_area=""):
    """[(words hit, words hit in name or room, state)], best first."""
    pool = []
    for s in all_states:
        eid = s["entity_id"]
        if domain and eid.split(".")[0] != domain:
            continue
        room = areas.get(eid, "")
        if want_area and want_area not in _norm(room) and want_area not in _norm(names[eid]):
            continue
        pool.append((s, room, _hay(s, names, room)))
    words = _correct(words, [h for _, _, h in pool]) if words else words
    scored = []
    for s, room, hay in pool:
        hits = sum(1 for w in words if _hit(w, hay)) if words else 1
        if hits:
            near = sum(1 for w in words if _hit(w, _norm(names[s["entity_id"]])) or _hit(w, _norm(room)))
            scored.append((hits, near, s))
    return sorted(scored, key=lambda x: (-x[0], -x[1], names[x[2]["entity_id"]]))


async def states(item, text="", domain="", area="", limit=60):
    """Searches every state the token's user may read; returns (count, text for the model).
    Without words, domain or area it gives an overview: areas, zones, people, counts per kind."""
    async with _client(item) as c:
        r = await c.get(item["url"] + "/api/states")
        if r.status_code == 401:
            return 0, "Home Assistant rejected the token."
        r.raise_for_status()
        all_states = [s for s in r.json() or [] if isinstance(s, dict) and s.get("entity_id")]
        areas = await _areas(c, item)
    exact = next((s for s in all_states if s["entity_id"] == str(text).strip().lower()), None)
    if exact:  # one entity by its id: every attribute
        a = {k: v for k, v in (exact.get("attributes") or {}).items() if k not in ("entity_picture", "icon")}
        return 1, (_line(exact, {}, (areas.get(exact["entity_id"], ""))) + "\nattributes: "
                   + json.dumps(a, ensure_ascii=False, default=str)[:3000]
                   + f"\nlast changed: {exact.get('last_changed', '')}")
    names = {s["entity_id"]: (s.get("attributes") or {}).get("friendly_name") or s["entity_id"] for s in all_states}
    domain = _norm(domain).strip().replace(" ", "_")
    want_area = _norm(area).strip()
    words = [w for w in _norm(text).split() if len(w) > 1 and w not in _STOP]
    if not words and not domain and not want_area:
        kinds = {}
        for s in all_states:
            d = s["entity_id"].split(".")[0]
            kinds[d] = kinds.get(d, 0) + 1
        rooms = sorted(set(areas.values()))
        out = [f"{len(all_states)} entities visible. Kinds: " + ", ".join(f"{d} {n}" for d, n in sorted(kinds.items())),
               "Areas: " + (", ".join(rooms) if rooms else "unknown (the area list needs an administrator token)")]
        for d in ("zone", "person"):
            out += [_line(s, names, areas.get(s["entity_id"], "")) for s in all_states if s["entity_id"].startswith(d + ".")]
        return len(all_states), "\n".join(out)
    scored = _score(all_states, areas, names, words, domain, want_area)
    if not scored:
        return 0, ("No entity matches. Try other words, a kind (domain) like sensor, light, zone, person, or "
                   "call without words for an overview.")
    keep = [x[2] for x in scored if x[0] == scored[0][0]]  # the most words; all words when any does
    lines = [_line(s, names, areas.get(s["entity_id"], "")) for s in keep[:limit]]
    _log("states:", repr(str(text)[:60]), domain or "", area or "", "->", len(keep), [x["entity_id"] for x in keep[:5]])
    if len(keep) > limit:
        lines.append(f"... and {len(keep) - limit} more; narrow the search.")
    return len(keep), "\n".join(lines)


# ---- direct actions: devices Assist does not know; never locks, alarm systems or updates ----

BLOCKED = {"lock", "alarm_control_panel", "update"}


# what a spoken command wants, by its words (German and English)
_VERBS = [("turn_off", "aus ausschalten ausmachen abschalten off stop stopp"),
          ("turn_on", "an ein einschalten anmachen anschalten on"),
          ("open_cover", "oeffne oeffnen auf hoch rauf open"), ("close_cover", "schliesse schliessen zu runter close"),
          ("toggle", "umschalten toggle")]
_SWITCHABLE = {"light", "switch", "fan", "cover", "media_player", "climate", "input_boolean", "humidifier",
               "vacuum", "water_heater", "remote", "siren"}
_FILLER = set("schalte schalt mach mache machen stell stelle bitte mal den die das dem im in am beim vom ganz "
              "the please turn switch set".split())


# one device often has several entities (a TV: media_player, remote, switch); the main one is switched
_PRIMARY = {"media_player": 0, "light": 0, "climate": 0, "cover": 0, "fan": 0, "vacuum": 0, "humidifier": 0,
            "water_heater": 0, "switch": 1, "input_boolean": 1, "siren": 1, "remote": 2}


async def _switchable(item):
    async with _client(item) as c:
        r = await c.get(item["url"] + "/api/states")
        r.raise_for_status()
        all_states = [s for s in r.json() or [] if isinstance(s, dict) and s.get("entity_id")
                      and s["entity_id"].split(".")[0] in _SWITCHABLE]
        areas = await _areas(c, item)
    names = {s["entity_id"]: (s.get("attributes") or {}).get("friendly_name") or s["entity_id"] for s in all_states}
    return all_states, areas, names


def _pick(all_states, areas, names, words):
    """(the one device all words fit or None, the candidates). Words that fit no device at all (a room
    when Home Assistant does not tell rooms) are left out; among entities of one device the main one wins."""
    hays = [_hay(x, names, areas.get(x["entity_id"], "")) for x in all_states]
    useful = [w for w in _correct(words, hays) if any(_hit(w, h) for h in hays)]
    if not useful:
        return None, []
    full = [x for x in _score(all_states, areas, names, useful) if x[0] == len(useful)]
    if not full:
        return None, []
    best = max(x[1] for x in full)
    top = [x for x in full if x[1] == best]
    prio = min(_PRIMARY.get(x[2]["entity_id"].split(".")[0], 1) for x in top)
    top = [x for x in top if _PRIMARY.get(x[2]["entity_id"].split(".")[0], 1) == prio]
    return (top[0][2] if len(top) == 1 else None), full


def _name(s):
    return (s.get("attributes") or {}).get("friendly_name") or s["entity_id"]


async def mentions_device(item, text):
    """Whether a word of the text names a switchable device (by name, room or kind), so that
    "Auf Wiedersehen" is no command."""
    words = [w for w in re.findall(r"\w+", _norm(clean_command(text))) if len(w) > 1 and w not in _FILLER
             and w not in _STOP and not any(w in v.split() for _, v in _VERBS)]
    if not words:
        return False
    try:
        all_states, areas, names = await _switchable(item)
    except (httpx.HTTPError, ValueError):
        return True  # Home Assistant will say itself what it cannot do
    hays = [_hay(x, names, areas.get(x["entity_id"], "")) for x in all_states]
    return any(_hit(w, h) for w in _correct(words, hays) for h in hays)


async def fallback(item, text):
    """When Assist does not know a device: finds it among all states and switches it when the words
    name one device and a plain on/off/open/close; otherwise lists the candidates. (done, text)."""
    words = [w for w in re.findall(r"\w+", _norm(clean_command(text))) if len(w) > 1]
    service = next((svc for svc, verbs in _VERBS if any(w in verbs.split() for w in words)), None)
    every = any(w in ("alle", "alles", "saemtliche", "all") for w in words)
    words = [w for w in words if w not in _FILLER and w not in _STOP and not any(w in v.split() for _, v in _VERBS)]
    if not words:
        _log("fallback: no device words in", repr(text[:80]))
        return False, ""
    all_states, areas, names = await _switchable(item)
    if every and service:  # "Alle Lichter im Wohnzimmer aus"
        done, res = await _bulk(item, all_states, areas, names, words, service)
        # "all" never falls back to one device that only some of the words fit
        return done, res or "Nothing switched: not every word of the command fits a device in Home Assistant."
    scored = _score(all_states, areas, names, words)
    chosen, full = _pick(all_states, areas, names, words)
    _log("fallback:", repr(text[:80]), "words", words, "service", service, "areas", len(set(areas.values())),
         "candidates", [x[2]["entity_id"] for x in (full or scored)[:8]], "chosen", chosen and chosen["entity_id"])
    if service and chosen:
        dom = chosen["entity_id"].split(".")[0]
        svc = service if dom == "cover" or service not in ("open_cover", "close_cover") else None
        if dom == "cover" and service in ("turn_on", "turn_off"):
            svc = "open_cover" if service == "turn_on" else "close_cover"
        if svc:
            return await action(item, chosen["entity_id"], svc)
    cands = [_line(x[2], names, areas.get(x[2]["entity_id"], "")) for x in (full or scored)[:8]]
    if not cands:
        return False, ""
    return False, ("Nothing switched yet. Candidates (switch the right one with home_assistant_action and its "
                   "exact entity id, or ask the user which one; "
                   + ("rooms unknown: the token is no administrator" if not areas else "rooms known") + "):\n"
                   + "\n".join(cands))


async def _bulk(item, all_states, areas, names, words, service):
    """Switches every device of one kind that all words fit (at most 20), each checked afterwards.
    Only when every word fits some device: a room Home Assistant does not know never widens it to the
    whole home."""
    hays = [_hay(x, names, areas.get(x["entity_id"], "")) for x in all_states]
    fixed = _correct(words, hays)
    if not all(any(_hit(w, h) for h in hays) for w in fixed):
        _log("bulk: not every word fits a device, nothing switched", fixed)
        return False, ""
    full = [x[2] for x in _score(all_states, areas, names, fixed) if x[0] == len(fixed)]
    if not full:
        return False, ""
    prio = min(_PRIMARY.get(x["entity_id"].split(".")[0], 1) for x in full)
    doms = [x["entity_id"].split(".")[0] for x in full if _PRIMARY.get(x["entity_id"].split(".")[0], 1) == prio]
    dom = max(set(doms), key=doms.count)
    targets = [x["entity_id"] for x in full if x["entity_id"].split(".")[0] == dom][:20]
    svc = service
    if dom == "cover" and service in ("turn_on", "turn_off"):
        svc = "open_cover" if service == "turn_on" else "close_cover"
    elif dom != "cover" and service in ("open_cover", "close_cover"):
        return False, ""
    _log("bulk:", dom, svc, targets)
    results = await asyncio.gather(*(action(item, eid, svc) for eid in targets))
    lines = [r[1].split("\n", 1)[1] if "\n" in r[1] else r[1] for r in results]
    head = "Checked in Home Assistant afterwards (report only this, do not add anything):"
    return all(r[0] for r in results), head + "\n" + "\n".join(
        x.split("\n(before")[0] for x in lines)


async def action(item, entity_id, service, data=None):
    """Calls one service of the entity's own domain; returns (ok, text for the model)."""
    eid = str(entity_id or "").strip().lower()
    service = str(service or "").strip().lower().split(".")[-1]  # "media_player.turn_off" is fine too
    if ("_" not in service or not re.fullmatch(r"[a-z0-9_]{1,64}", service)) and _intent(service):
        service = _intent(service)  # words instead of a service: "ausschalten", "turn off", "off"
    if not re.fullmatch(r"[a-z0-9_]{1,64}\.[a-z0-9_]{1,200}", eid):
        # a name instead of the id ("Samsung The Frame"): take the device whose name it is
        all_states, areas, names = await _switchable(item)
        words = [w for w in _norm(entity_id).split() if len(w) > 1 and w not in _STOP]
        chosen, _ = _pick(all_states, areas, names, words) if words else (None, [])
        _log("action: name", repr(str(entity_id)[:80]), "->", chosen and chosen["entity_id"])
        if not chosen:
            return False, ("Nothing switched: give the exact entity id, e.g. light.kueche (look it up with "
                           "home_assistant_states).")
        eid = chosen["entity_id"]
    if not re.fullmatch(r"[a-z0-9_]{1,64}", service):
        _log("action: bad service", repr(service[:80]))
        return False, "Nothing switched. Give the service, e.g. turn_on, turn_off, toggle, set_temperature, set_cover_position."
    domain = eid.split(".")[0]
    if domain in BLOCKED:
        _log("action: blocked domain", eid)
        return False, ("Locks, alarm systems and updates are not switched from here; the user can do it in "
                       "Home Assistant itself.")
    extra = {}
    for k, v in (data if isinstance(data, dict) else {}).items():
        k = str(k)
        if re.fullmatch(r"[a-z0-9_]{1,64}", k) and k not in ("entity_id", "device_id", "area_id", "target") \
                and isinstance(v, (str, int, float, bool)) and len(str(v)) <= 200:
            extra[k] = v
    async with _client(item) as c:
        r = await c.get(f"{item['url']}/api/states/{eid}")
        if r.status_code == 401:
            _log("action: token rejected (401)")
            return False, "Home Assistant rejected the token."
        if r.status_code == 404:
            _log("action: no entity", eid)
            return False, f"There is no entity {eid}; look it up with home_assistant_states."
        r.raise_for_status()
        before = (r.json() or {}).get("state")
        name = ((r.json() or {}).get("attributes") or {}).get("friendly_name") or eid
        r = await c.post(f"{item['url']}/api/services/{domain}/{service}", json=dict(extra, entity_id=eid))
        _log("action:", f"{domain}.{service}", eid, extra or "", "-> HTTP", r.status_code,
             "" if r.status_code == 200 else r.text[:200])
        if r.status_code in (400, 404):
            return False, f"Home Assistant does not accept {domain}.{service} for {name} (HTTP {r.status_code}). Nothing was switched."
        if r.status_code in (401, 403):
            return False, "The Home Assistant user of this token may not do that. Nothing was switched."
        r.raise_for_status()
        checked = await _verify(c, item, [eid], service, {eid: before})
    ok, text = _report(checked, service, "service call")
    return ok, text + f"\n(before: '{before}')"


# ---- history: what a device did, read from Home Assistant's recorder ----

async def history(item, text, hours=24, zone=None):
    """The last hours of up to three entities the words fit: numbers as low/high/average/now, other
    states as their last changes with time. Returns (count, text for the model)."""
    import datetime
    hours = min(24 * 30, max(1, int(hours or 24)))
    async with _client(item) as c:
        r = await c.get(item["url"] + "/api/states")
        if r.status_code == 401:
            return 0, "Home Assistant rejected the token."
        r.raise_for_status()
        all_states = [x for x in r.json() or [] if isinstance(x, dict) and x.get("entity_id")]
        areas = await _areas(c, item)
        names = {x["entity_id"]: _name(x) for x in all_states}
        eid = str(text).strip().lower()
        if eid in names:
            picked = [eid]
        else:
            words = [w for w in re.findall(r"\w+", _norm(text)) if len(w) > 1 and w not in _STOP and w not in _FILLER]
            scored = _score(all_states, areas, names, words) if words else []
            picked = [x[2]["entity_id"] for x in scored if x[0] == scored[0][0]][:3] if scored else []
        if not picked:
            return 0, "No entity matches; try other words or look it up with home_assistant_states."
        start = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
        r = await c.get(f"{item['url']}/api/history/period/{start}",
                        params={"filter_entity_id": ",".join(picked), "minimal_response": "",
                                "significant_changes_only": ""})
        r.raise_for_status()
        series = r.json() if isinstance(r.json(), list) else []
    _log("history:", picked, hours, "h,", [len(x) for x in series], "points")
    tz = zone or datetime.datetime.now().astimezone().tzinfo

    def when(t):
        try:
            d = datetime.datetime.fromisoformat(str(t).replace("Z", "+00:00")).astimezone(tz)
            return d.strftime("%d.%m. %H:%M")
        except ValueError:
            return str(t)
    out = [f"History of the last {hours} h (from Home Assistant's recorder; report only this):"]
    for rows in series:
        if not rows:
            continue
        eid = rows[0].get("entity_id") or ""
        unit = ((rows[0].get("attributes") or {}).get("unit_of_measurement")) or ""
        name = names.get(eid, eid)
        nums = []
        for x in rows:
            try:
                nums.append((float(x["state"]), x.get("last_changed")))
            except (KeyError, TypeError, ValueError):
                pass
        if nums and len(nums) >= len(rows) / 2:
            lo, hi = min(nums), max(nums)
            avg = sum(v for v, _ in nums) / len(nums)
            out.append(f"- {name} ({eid}): lowest {lo[0]:g} {unit} ({when(lo[1])}), highest {hi[0]:g} {unit} "
                       f"({when(hi[1])}), average {avg:.1f} {unit}, latest {nums[-1][0]:g} {unit}")
        else:
            changes = [f"{when(x.get('last_changed'))} {x.get('state')}" for x in rows[-10:]]
            out.append(f"- {name} ({eid}): {len(rows)} states; latest changes: " + "; ".join(changes))
    return len(series), "\n".join(out) if len(out) > 1 else "Home Assistant has no history for this time."


# ---- to-do lists (shopping list and others): read, add, tick off ----

async def todo(item, list_name="", act="show", text=""):
    """Returns (ok, text for the model). Changes are read back: an item counts as added or done only
    when the list shows it so afterwards."""
    act = str(act or "show").strip().lower()
    act = {"list": "show", "read": "show", "get": "show", "add_item": "add", "complete": "done",
           "check": "done", "remove_item": "remove", "delete": "remove"}.get(act, act)
    async with _client(item) as c:
        r = await c.get(item["url"] + "/api/states")
        r.raise_for_status()
        lists = [x for x in r.json() or [] if isinstance(x, dict) and str(x.get("entity_id", "")).startswith("todo.")]
        if not lists:
            return False, "Home Assistant has no to-do lists the token's user can see."
        names = {x["entity_id"]: _name(x) for x in lists}
        want = _norm(list_name)
        pick = [x for x in lists if want and (want in _norm(names[x["entity_id"]]) or want in x["entity_id"])] \
            or ([x for x in lists if "einkauf" in _norm(names[x["entity_id"]]) or "shopping" in x["entity_id"]]
                if not want or "einkauf" in want or "shopping" in want else [])
        if not pick:
            return False, "Lists in Home Assistant: " + ", ".join(f"{names[x['entity_id']]} ({x['entity_id']})" for x in lists)
        eid = pick[0]["entity_id"]

        async def items():
            r = await c.post(f"{item['url']}/api/services/todo/get_items?return_response",
                             json={"entity_id": eid})
            if r.status_code != 200:
                _log("todo: get_items HTTP", r.status_code, r.text[:200])
                return None
            resp = (r.json() or {}).get("service_response") or {}
            return [(x.get("summary", ""), x.get("status", "")) for x in (resp.get(eid) or {}).get("items") or []]
        before = await items()
        if before is None:
            return False, "Home Assistant did not return the list (it needs version 2024.1 or newer)."
        thing = str(text or "").strip()[:200]
        if act == "show":
            open_ = [s for s, st in before if st != "completed"]
            return True, f"{names[eid]}: " + (", ".join(open_) if open_ else "empty") + "."
        if not thing:
            return False, "Say which item."
        if act in ("done", "remove"):  # the item as the list writes it
            match = next((s for s, _ in before if _norm(s) == _norm(thing)), None) or next(
                (s for s, _ in before if _norm(thing) in _norm(s)), None)
            if not match:
                return False, f"'{thing}' is not on {names[eid]}. Nothing changed."
            thing = match
        svc, body = {"add": ("add_item", {"item": thing}), "done": ("update_item", {"item": thing, "status": "completed"}),
                     "remove": ("remove_item", {"item": [thing]})}.get(act, (None, None))
        if not svc:
            return False, "Unknown action; use show, add, done or remove."
        r = await c.post(f"{item['url']}/api/services/todo/{svc}", json=dict(body, entity_id=eid))
        _log("todo:", svc, eid, "-> HTTP", r.status_code)
        if r.status_code != 200:
            return False, f"Home Assistant refused it (HTTP {r.status_code}). Nothing changed."
        after = await items() or []
    state = {_norm(s): st for s, st in after}
    ok = {"add": _norm(thing) in state, "done": state.get(_norm(thing)) == "completed",
          "remove": _norm(thing) not in state}[act]
    word = {"add": "added to", "done": "ticked off on", "remove": "removed from"}[act]
    return ok, (f"Checked afterwards: '{thing}' {word} {names[eid]}." if ok
                else f"Checked afterwards: '{thing}' was NOT {word} {names[eid]}.")


async def lookup(item, text, limit=12):
    """For a question that names a device or room Home Assistant has ("Wie ist die Pool-Temperatur?",
    "und vom Whirlpool?"): the states of the entities whose name or room carries those words, read by
    the panel itself so the answer never depends on the model calling a tool. None when no word names
    anything in Home Assistant."""
    t = str(text).strip()
    first = (re.findall(r"\w+", _norm(t)) or [""])[0]
    if not (t.endswith("?") or first in _ASKING or first in ("und", "and", "zeig", "sag", "nenn")):
        return None  # only questions and follow-ups ("und vom Whirlpool")
    raw = re.findall(r"\w+", clean_command(text))
    nouns = {_norm(w) for i, w in enumerate(raw) if i and w[:1].isupper()}  # capitalised: names a thing
    words = [w for w in (_norm(x) for x in raw) if len(w) > 2 and w not in _STOP
             and w not in _FILLER and w not in _ASKING and w not in ("und", "vom", "von", "der", "dem", "and")]
    if not words:
        return None
    async with _client(item) as c:
        r = await c.get(item["url"] + "/api/states")
        r.raise_for_status()
        all_states = [x for x in r.json() or [] if isinstance(x, dict) and x.get("entity_id")]
        areas = await _areas(c, item)
    names = {x["entity_id"]: _name(x) for x in all_states}
    labels = [_norm(names[x["entity_id"]] + " " + x["entity_id"].split(".", 1)[1] + " "
                    + areas.get(x["entity_id"], "")) for x in all_states]
    def names_it(w, h):  # whole words; inside compounds ("Pooltemperatur") only for longer words
        return any(f in h.split() for f in _forms(w)) or (len(w) >= 5 and _hit(w, h))
    def known(w):
        return w in _GENERIC or any(names_it(w, h) for h in labels)
    split = []  # "Pooltemperatur" -> "pool" + "temperatur" when both parts are known
    for w in words:
        parts = next(([w[:i], w[i:]] for i in range(3, len(w) - 2) if not known(w)
                      and (known(w[:i]) or w[i:] in _GENERIC) and known(w[i:])), [w])
        split += parts
        if len(parts) > 1 and w in nouns:
            nouns |= set(parts)
    words = _correct(split, labels)
    generic = [w for w in words if w in _GENERIC]  # "Temperatur", "aktuelle": what is asked, not which device
    specific = [w for w in words if w not in _GENERIC and any(names_it(w, h) for h in labels)]
    missing = [w for w in words if w not in _GENERIC and w not in specific and w in nouns]
    low = [_norm(w) for w in raw]
    about_home = any(w in _GENERIC and w not in _GENERIC_ONLY for w in words) or (
        low[:1] == ["und"] and low[1:2] and low[1] in ("vom", "von", "im", "beim", "in", "der", "die", "das", "dem"))
    if missing and about_home:  # "Temperatur vom Gartenteich", "und vom Whirlpool?"  # a thing Home Assistant has no entity for: never answer with another device's values
        near = [x["entity_id"] for x, h in zip(all_states, labels)
                if any(w[i:i + 4] in h for w in missing for i in range(len(w) - 3))]
        _log("lookup:", repr(str(text)[:60]), "nothing named", missing, "- similar:", near[:10])
        return ("Read from Home Assistant just now: no entity, device or room in Home Assistant is called "
                + ", ".join(repr(w) for w in missing) + ". Say exactly that it was not found in Home Assistant; "
                "give no value of any other device instead.")
    if not specific:
        return None
    cands = [x for x, h in zip(all_states, labels) if all(names_it(w, h) for w in specific)]
    if not cands:  # no entity carries all of them: the one with the most
        best = max(sum(names_it(w, h) for w in specific) for h in labels)
        cands = [x for x, h in zip(all_states, labels) if sum(names_it(w, h) for w in specific) == best]
    whole = [x for x, h in zip(all_states, labels) if x in cands
             and all(any(f in h.split() for f in _forms(w)) for w in specific)]
    cands = whole or cands  # "Pool" is the pool, not also the whirlpool
    if generic:  # "Temperatur": narrow down when that leaves something
        hays = {x["entity_id"]: _hay(x, names, areas.get(x["entity_id"], "")) + " " + _norm(_line(x, names, ""))
                for x in cands}
        narrow = [x for x in cands if any(_hit(w, hays[x["entity_id"]]) for w in generic
                                          if w not in _GENERIC_ONLY)]
        cands = narrow or cands
    _log("lookup:", repr(str(text)[:60]), "words", specific, generic, "->", [x["entity_id"] for x in cands[:8]])
    lines = [_line(x, names, areas.get(x["entity_id"], "")) for x in cands[:limit]]
    more = f"\n... and {len(cands) - limit} more" if len(cands) > limit else ""
    return ("Read from Home Assistant just now (answer only from these values; if the asked value is not "
            "among them, say that it is not there):\n" + "\n".join(lines) + more)
