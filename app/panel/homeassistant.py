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
"""
import json
import re
import threading
import time

import httpx

import profiles

_lock = threading.Lock()


def _file(uid):
    return profiles._path(uid, "homeassistant.json")


def get(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("url") and d.get("token") else None
    except (OSError, ValueError):
        return None


def public(uid):
    d = get(uid)
    return {"url": d["url"], "verify": d.get("verify", True), "agent": d.get("agent", ""),
            "has_token": True} if d else {"url": "", "verify": True, "agent": "", "has_token": False}


def entry(body, old=None):
    """A checked connection from the panel's form; an empty token keeps the stored one."""
    url = str(body.get("url", "")).strip().rstrip("/")
    if not re.fullmatch(r"https?://[^\s/]{1,200}(/[^\s]{0,200})?", url, re.I):
        raise ValueError("the address must start with http:// or https://, e.g. http://homeassistant.local:8123")
    token = str(body.get("token", "")).strip() or (old or {}).get("token", "")
    if not re.fullmatch(r"[\w.\-]{20,1000}", token):
        raise ValueError("a long-lived access token is required (Home Assistant: your profile → Security)")
    agent = str(body.get("agent", "")).strip()
    if agent and not re.fullmatch(r"[\w.\-]{1,100}", agent):
        raise ValueError("invalid agent id")
    return {"url": url, "token": token, "verify": body.get("verify", True) is not False, "agent": agent}


def save(uid, item):
    with _lock:
        profiles._write(_file(uid), dict(item, updated=int(time.time())))
    return public(uid)


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
    """Hands one spoken command to Home Assistant's Assist; returns (ok, answer, targets)."""
    body = {"text": str(text)[:500], "language": language}
    if item.get("agent"):
        body["agent_id"] = item["agent"]
    async with _client(item) as c:
        r = await c.post(item["url"] + "/api/conversation/process", json=body)
    if r.status_code == 401:
        return False, "Home Assistant rejected the token.", []
    r.raise_for_status()
    res = (r.json() or {}).get("response") or {}
    speech = ((res.get("speech") or {}).get("plain") or {}).get("speech", "")
    data = res.get("data") or {}
    targets = [x.get("name") for x in (data.get("success") or data.get("targets") or []) if x.get("name")]
    failed = [x.get("name") for x in data.get("failed") or [] if x.get("name")]
    ok = res.get("response_type") != "error" and not failed
    if failed:
        speech += " Failed: " + ", ".join(failed)
    if res.get("response_type") == "error" and (res.get("data") or {}).get("code") in (
            "no_valid_targets", "no_intent_match"):
        # Assist knows only exposed entities and its own sentence patterns
        speech += (" (Assist did not find this device or did not understand the sentence; it only knows "
                   "devices exposed to Assist. Look the device up with home_assistant_states and retry "
                   "with its exact name.)")
    return ok, speech.strip() or ("Done." if ok else "Home Assistant could not do that."), targets[:10]


# ---- reading states: every entity the token's user can see, not only those exposed to Assist ----

# words people use for a kind of entity, so "Fenster", "Akku" or "Zone" find it without its name
_KIND = {
    "light": "licht lampe leuchte light lamp", "switch": "schalter steckdose switch plug",
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
    "gas": "gas", "voltage": "spannung", "current": "strom", "plug": "steckdose", "connectivity": "verbunden online",
}
_STOP = set("der die das den dem des ein eine einen im in ist sind wie was wo welche welcher welches gibt es mir "
            "bitte und oder von vom zum zur auf an aus mit hat haben gerade aktuell jetzt alle alles zeige zeig "
            "sag sage the is are what which where how all any show".split())
_areas_cache = {}  # url -> (time, {entity_id: area})


def _norm(t):
    t = str(t).lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("_", " "), (".", " ")):
        t = t.replace(a, b)
    return t


async def _areas(c, item):
    hit = _areas_cache.get(item["url"])
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
    except httpx.HTTPError:
        pass
    _areas_cache[item["url"]] = (time.time(), found)
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
    if a.get("device_class") and dom in ("binary_sensor", "cover"):
        extra.append(f"type={a['device_class']}")
    name = a.get("friendly_name") or eid
    return f"{name} ({eid}{', ' + area if area else ''}): {val}" + (f" [{', '.join(extra)}]" if extra else "")


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
    scored = []
    for s in all_states:
        eid = s["entity_id"]
        dom = eid.split(".")[0]
        if domain and dom != domain:
            continue
        a = s.get("attributes") or {}
        room = areas.get(eid, "")
        if want_area and want_area not in _norm(room) and want_area not in _norm(names[eid]):
            continue
        hay = _norm(" ".join([names[eid], _norm(eid), _norm(room), dom.replace("_", " "), _KIND.get(dom, ""),
                        _CLASS.get(a.get("device_class", ""), ""), a.get("device_class", "")]))
        hits = sum(1 for w in words if w in hay) if words else 1
        if hits:
            # hits in the name or room rank before hits in the kind words
            near = sum(1 for w in words if w in _norm(names[eid]) or w in _norm(room))
            scored.append((hits, near, s))
    if not scored:
        return 0, ("No entity matches. Try other words, a kind (domain) like sensor, light, zone, person, or "
                   "call without words for an overview.")
    best = max(x[0] for x in scored)  # entities matching the most words; all words when any does
    keep = [x[2] for x in sorted((x for x in scored if x[0] == best),
                                 key=lambda x: (-x[1], names[x[2]["entity_id"]]))]
    lines = [_line(s, names, areas.get(s["entity_id"], "")) for s in keep[:limit]]
    if len(keep) > limit:
        lines.append(f"... and {len(keep) - limit} more; narrow the search.")
    return len(keep), "\n".join(lines)


# ---- direct actions: devices Assist does not know; never locks, alarm systems or updates ----

BLOCKED = {"lock", "alarm_control_panel", "update"}


async def action(item, entity_id, service, data=None):
    """Calls one service of the entity's own domain; returns (ok, text for the model)."""
    eid = str(entity_id or "").strip().lower()
    service = str(service or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{1,64}\.[a-z0-9_]{1,200}", eid):
        return False, "Give the exact entity id, e.g. light.kueche (look it up with home_assistant_states)."
    if not re.fullmatch(r"[a-z0-9_]{1,64}", service):
        return False, "Give the service, e.g. turn_on, turn_off, toggle, set_temperature, set_cover_position."
    domain = eid.split(".")[0]
    if domain in BLOCKED:
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
            return False, "Home Assistant rejected the token."
        if r.status_code == 404:
            return False, f"There is no entity {eid}; look it up with home_assistant_states."
        r.raise_for_status()
        name = ((r.json() or {}).get("attributes") or {}).get("friendly_name") or eid
        r = await c.post(f"{item['url']}/api/services/{domain}/{service}", json=dict(extra, entity_id=eid))
        if r.status_code in (400, 404):
            return False, f"Home Assistant does not accept {domain}.{service} for {name} (HTTP {r.status_code})."
        if r.status_code in (401, 403):
            return False, "The Home Assistant user of this token may not do that."
        r.raise_for_status()
        new = next((x for x in (r.json() if isinstance(r.json(), list) else []) if x.get("entity_id") == eid), None)
        if not new:
            r = await c.get(f"{item['url']}/api/states/{eid}")
            new = r.json() if r.status_code == 200 else None
    return True, f"Done: {domain}.{service} for {name}." + (f" Now: {_line(new, {}, '')}" if new else "")
