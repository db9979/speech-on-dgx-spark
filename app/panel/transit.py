"""Bus und Bahn: departures from the profile's home stop and connections, from a transport.rest
service (https://v6.db.transport.rest by default, the admin can set another one, e.g. an own
db-rest or a regional *.transport.rest). The panel turns the answer into fixed sentences; the model
only reads them. Off until the admin allows it (chat.transit) and a profile switches it on
(setting transit_on) with its home stop. Guests never.

    USERS_DIR/<uid>/transit.json   {"home": {"id", "name"}, "commute": {"to": {"id", "name"}, "at": "07:30",
                                    "days": [0, 1, 2, 3, 4]}}

Stop names, lines and directions come from outside: they count as outside text (no switching in the
same answer). With a commute set, "Von selbst" can say once a day when that train is late or cancelled.
"""
import datetime
import json
import re
import time

import httpx

import profiles
from common import load_config

DEFAULT_URL = "https://v6.db.transport.rest"
CACHE_SECONDS = 60
LATE = 5 * 60                 # from this many seconds the commute note speaks up
_cache = {}


def admin_on():
    return bool(load_config().get("chat", {}).get("transit", False))


def base():
    return (load_config().get("chat", {}).get("transit_url") or DEFAULT_URL).rstrip("/")


def _file(uid):
    return profiles._path(uid, "transit.json")


def get(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def usable(uid):
    return bool(uid and admin_on() and profiles.settings(uid).get("transit_on") and (get(uid).get("home") or {}).get("id"))


def _clean(s, n=80):
    return re.sub(r"[^\w .,'()/\-+&]", "", str(s or ""))[:n].strip()


def stop(x):
    """A checked {"id", "name"} picked on the page."""
    if not isinstance(x, dict) or not re.fullmatch(r"[\w:.%\-]{1,60}", str(x.get("id", ""))):
        raise ValueError("Haltestelle ungültig")
    return {"id": str(x["id"]), "name": _clean(x.get("name")) or str(x["id"])}


def save(uid, body):
    d = get(uid)
    if "home" in body:
        if body["home"]:
            d["home"] = stop(body["home"])
        else:
            d.pop("home", None)
    if "commute" in body:
        c = body["commute"]
        if not c:
            d.pop("commute", None)
        else:
            at = str(c.get("at", ""))
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
                raise ValueError("Uhrzeit wie 07:30")
            days = sorted({int(x) for x in c.get("days", []) if str(x).isdigit() and 0 <= int(x) <= 6}) or [0, 1, 2, 3, 4]
            d["commute"] = {"to": stop(c.get("to")), "at": at, "days": days}
    profiles._write(_file(uid), d)
    return d


# ---------------------------------------------------------------- the service
async def _get(path, params):
    key = (path, tuple(sorted(params.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=6), headers={"User-Agent": "speech-on-dgx-spark"}) as c:
        r = await c.get(base() + path, params=params)
    if r.status_code >= 400:
        raise ValueError(f"der Fahrplandienst antwortet {r.status_code}")
    data = r.json()
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.time(), data)
    return data


async def find(query, n=6):
    q = _clean(query, 60)
    if len(q) < 2:
        raise ValueError("Haltestelle fehlt")
    data = await _get("/locations", {"query": q, "results": n, "stops": "true", "addresses": "false", "poi": "false"})
    return [{"id": str(x["id"]), "name": _clean(x.get("name"))} for x in data or []
            if isinstance(x, dict) and x.get("type") in ("stop", "station") and x.get("id")][:n]


async def departures(stop_id, when=None, n=8):
    params = {"duration": 60, "results": n, "remarks": "false"}
    if when:
        params["when"] = when.isoformat()
    data = await _get(f"/stops/{stop_id}/departures", params)
    return data.get("departures", []) if isinstance(data, dict) else data or []


async def journeys(from_id, to_id, when=None, n=3):
    params = {"from": from_id, "to": to_id, "results": n, "stopovers": "false", "remarks": "false"}
    if when:
        params["departure"] = when.isoformat()
    data = await _get("/journeys", params)
    return (data or {}).get("journeys", []) if isinstance(data, dict) else []


# ---------------------------------------------------------------- sentences
def _t(iso, zone):
    if not iso:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(zone) if zone and d.tzinfo else d


def _late(sec):
    m = round((sec or 0) / 60)
    return f" (+{m})" if m >= 1 else ""


def _line(x):
    return _clean((x.get("line") or {}).get("name") or "", 20)


def departure_line(x, zone=None):
    when = _t(x.get("plannedWhen") or x.get("when"), zone)
    if not when:
        return ""
    s = f"{when:%H:%M}{_late(x.get('delay'))} {_line(x)} nach {_clean(x.get('direction'), 50)}".replace("  ", " ")
    plat = x.get("platform") or x.get("plannedPlatform")
    if plat:
        s += f", Gleis {_clean(plat, 6)}"
    if x.get("cancelled"):
        s += ", fällt aus"
    return s


def journey_line(j, zone=None):
    legs = [x for x in j.get("legs") or [] if not x.get("walking")]
    if not legs:
        return ""
    a, b = legs[0], legs[-1]
    dep, arr = _t(a.get("plannedDeparture") or a.get("departure"), zone), _t(b.get("plannedArrival") or b.get("arrival"), zone)
    if not dep or not arr:
        return ""
    lines = " und ".join(dict.fromkeys(_line(x) for x in legs if _line(x)))
    s = f"ab {dep:%H:%M}{_late(a.get('departureDelay'))} mit {lines or 'Fußweg'}, an {arr:%H:%M}{_late(b.get('arrivalDelay'))}"
    s += ", ohne Umstieg" if len(legs) == 1 else f", {len(legs) - 1} Umstieg{'' if len(legs) == 2 else 'e'}"
    if any(x.get("cancelled") for x in legs):
        s += ", fällt aus"
    return s


async def report_departures(stop_, zone=None, when=None):
    deps = [d for d in (departure_line(x, zone) for x in await departures(stop_["id"], when)) if d]
    return (f"Abfahrten ab {stop_['name']}: " + "; ".join(deps[:6]) + ".") if deps else f"Ab {stop_['name']} fährt in der nächsten Stunde nichts."


async def report_journeys(a, b, zone=None, when=None):
    js = [x for x in (journey_line(j, zone) for j in await journeys(a["id"], b["id"], when)) if x]
    return (f"Von {a['name']} nach {b['name']}: " + "; ".join(js) + ".") if js else f"Keine Verbindung von {a['name']} nach {b['name']} gefunden."


async def commute_note(uid, now):
    """The commute train when it is late or cancelled: (sentence, data) or None."""
    d = get(uid)
    c, home = d.get("commute"), d.get("home")
    if not c or not home:
        return None
    hh, mm = map(int, c["at"].split(":"))
    at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    for j in await journeys(home["id"], c["to"]["id"], at - datetime.timedelta(minutes=10), 4):
        legs = [x for x in j.get("legs") or [] if not x.get("walking")]
        dep = _t(legs[0].get("plannedDeparture"), now.tzinfo) if legs else None
        if not dep or dep < at - datetime.timedelta(minutes=10):
            continue
        first = legs[0]
        what = f"Deine Verbindung um {dep:%H:%M} nach {c['to']['name']} ({_line(first) or 'Bahn'})"
        if any(x.get("cancelled") for x in legs):
            return what + " fällt aus.", journey_line(j, now.tzinfo)
        if (first.get("departureDelay") or 0) >= LATE:
            return f"{what} fährt etwa {round(first['departureDelay'] / 60)} Minuten später.", journey_line(j, now.tzinfo)
        return None
    return None


# ---------------------------------------------------------------- the assistant's tool
TOOL = {"type": "function", "function": {
    "name": "transit",
    "description": "Public transport (bus, tram, train): next departures from the user's home stop, or "
                   "connections to a destination, with delays.",
    "parameters": {"type": "object", "properties": {
        "to": {"type": "string", "description": "destination stop or town, only for connections"},
        "from": {"type": "string", "description": "start stop, only if not the user's home stop"},
        "time": {"type": "string", "description": "departure time 'HH:MM' today (default now)"}}}}}
HINT = ("Für Fragen zu Bus und Bahn rufe transit auf und lies die Abfahrten oder Verbindungen aus dem Ergebnis "
        "vor, ohne Zeiten zu ändern. (+3) heißt drei Minuten Verspätung.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or not usable(who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "outside": {"transit"},
            "filler": {"transit": ("Ich schaue in den Fahrplan.", "Let me check the timetable.")}}


async def tool(name, args, ctx):
    import chat
    uid = ctx["who"]["id"]
    zone = chat.user_zone(ctx.get("tz") or profiles.settings(uid).get("tz", ""))
    home = get(uid).get("home")
    when = None
    m = re.fullmatch(r"\s*([01]?\d|2[0-3])[:.]([0-5]\d)\s*", str(args.get("time") or ""))
    if m:
        when = datetime.datetime.now(zone).replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
    try:
        start = home
        if args.get("from"):
            found = await find(args["from"], 1)
            if not found:
                return f"Haltestelle „{_clean(args['from'])}“ nicht gefunden."
            start = found[0]
        if not args.get("to"):
            return await report_departures(start, zone, when)
        found = await find(args["to"], 1)
        if not found:
            return f"Ziel „{_clean(args['to'])}“ nicht gefunden."
        return await report_journeys(start, found[0], zone, when)
    except (httpx.HTTPError, ValueError) as e:
        return f"Der Fahrplan ist gerade nicht erreichbar: {e}"


async def briefing(uid, zone=None):
    return ""


# ---------------------------------------------------------------- API ("Ich" → Bus und Bahn)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from core import assistant, browser_profile, own_profile  # noqa: E402

router = APIRouter()


def _on():
    if not admin_on():
        raise HTTPException(403, "transit is turned off")


@router.get("/api/profile/transit", dependencies=[Depends(assistant)])
def api_get(prof=Depends(own_profile)):
    return dict(get(prof["id"]), on=bool(profiles.settings(prof["id"]).get("transit_on")))


@router.put("/api/profile/transit", dependencies=[Depends(assistant), Depends(_on)])
async def api_put(request: Request, prof=Depends(browser_profile)):
    body = await request.json()
    try:
        return save(prof["id"], body if isinstance(body, dict) else {})
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(400, str(e))


@router.post("/api/profile/transit/find", dependencies=[Depends(assistant), Depends(_on)])
async def api_find(request: Request, prof=Depends(own_profile)):
    try:
        return {"stops": await find((await request.json() or {}).get("q", ""))}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Fahrplandienst nicht erreichbar ({type(e).__name__})")


@router.post("/api/profile/transit/test", dependencies=[Depends(assistant), Depends(_on)])
async def api_test(prof=Depends(own_profile)):
    import chat
    d = get(prof["id"])
    if not d.get("home"):
        raise HTTPException(400, "Keine Haltestelle eingestellt")
    zone = chat.user_zone(profiles.settings(prof["id"]).get("tz", ""))
    try:
        text = await report_departures(d["home"], zone)
        if d.get("commute"):
            text += " " + await report_journeys(d["home"], d["commute"]["to"], zone)
        return {"text": text}
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(400, f"Fahrplandienst: {e}")

