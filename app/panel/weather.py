"""Weather straight from Open-Meteo (no key): the panel turns the numbers into fixed German sentences,
the language model only reads them out. Off until the admin allows it (chat.weather) and a profile
switches it on for itself (setting wx_on) with its place. Guests never.

    USERS_DIR/<user id>/weather.json  {"place", "name", "lat", "lon"}

Only the coordinates (and, when a place is looked up, its name) leave the Spark. The admin can point
both addresses at an own Open-Meteo installation.
"""
import datetime
import json
import os
import re
import time

import httpx

import profiles
from common import load_config

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_SECONDS = 900
_cache = {}

# WMO weather codes as words
CODES = {0: "klar", 1: "meist sonnig", 2: "teils bewölkt", 3: "bedeckt", 45: "Nebel", 48: "Nebel mit Reif",
         51: "leichter Nieselregen", 53: "Nieselregen", 55: "starker Nieselregen", 56: "gefrierender Niesel",
         57: "gefrierender Niesel", 61: "leichter Regen", 63: "Regen", 65: "starker Regen",
         66: "gefrierender Regen", 67: "gefrierender Regen", 71: "leichter Schneefall", 73: "Schneefall",
         75: "starker Schneefall", 77: "Schneegriesel", 80: "Regenschauer", 81: "Regenschauer",
         82: "heftige Regenschauer", 85: "Schneeschauer", 86: "starke Schneeschauer", 95: "Gewitter",
         96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel"}
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def admin_on():
    return bool(load_config().get("chat", {}).get("weather", False))


def urls():
    c = load_config().get("chat", {})
    return (c.get("weather_url") or FORECAST), (c.get("geocode_url") or GEOCODE)


def _file(uid):
    return profiles._path(uid, "weather.json")


def get(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("lat"), (int, float)) else {}
    except (OSError, ValueError):
        return {}


def usable(uid):
    """The profile switched weather on and set its place."""
    return bool(uid and admin_on() and profiles.settings(uid).get("wx_on") and get(uid))


def _clean(s, n=60):
    return re.sub(r"[^\w .,'()/\-]", "", str(s or ""))[:n].strip()


NEAR = ("DE", "AT", "CH")   # the assistant speaks German: "Karlsbad" is the one near Karlsruhe, not Karlovy Vary


def _coords(text):
    """(lat, lon) when the text is just two numbers like "48.87, 8.50" or "48,87 8,50"."""
    nums = re.findall(r"-?\d+(?:[.,]\d+)?", text)
    if len(nums) != 2 or re.search(r"[^\d\s.,;/\-]", text):
        return None
    lat, lon = (float(x.replace(",", ".")) for x in nums)
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 and ("." in text or "," in text) else None


def _hit(x):
    name = ", ".join(_clean(v, 40) for v in (x.get("name"), x.get("admin1")) if v)
    return {"name": name, "lat": float(x["latitude"]), "lon": float(x["longitude"]),
            "country": str(x.get("country_code") or "")[:2], "postcodes": [str(p) for p in (x.get("postcodes") or [])][:20]}


async def candidates(place):
    """Places that fit the text, best first: [{"name", "lat", "lon", "country", "postcodes"}].
    "76307 Karlsbad" is searched as "Karlsbad" in Germany and checked against the postcode; two
    numbers are coordinates."""
    place = _clean(place)
    if len(place) < 2:
        raise ValueError("Ort fehlt")
    xy = _coords(place)
    if xy:
        return [{"name": f"{xy[0]:.3f}, {xy[1]:.3f}", "lat": xy[0], "lon": xy[1], "country": "", "postcodes": []}]
    pc = (re.findall(r"\b\d{4,5}\b", place) or [""])[0]
    name = re.sub(r"\s+", " ", re.sub(r"\b\d{4,5}\b", " ", place)).strip(" ,-/")
    country = "DE" if len(pc) == 5 else ""
    _, geo = urls()
    tries = [(name, country)] if name else []
    tries += [(part.strip(), country) for part in re.split(r"[-/,(]", name) if part.strip() and part.strip() != name]
    tries += [(pc, country)] if pc else []
    tries += [(name, "")] if name and country else []
    found = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as c:
        for q, cc in tries:
            if len(q) < 2:
                continue
            params = {"name": q, "count": 10, "language": "de", "format": "json"}
            if cc:
                params["countryCode"] = cc
            r = await c.get(geo, params=params)
            r.raise_for_status()
            for x in (r.json() or {}).get("results") or []:
                try:
                    h = _hit(x)
                except (KeyError, TypeError, ValueError):
                    continue
                if not any(abs(h["lat"] - f["lat"]) < 0.01 and abs(h["lon"] - f["lon"]) < 0.01 for f in found):
                    found.append(h)
            if found:   # the typed name wins over the postcode (villages often have none of their own)
                break
    if not found:
        raise ValueError(f"Ort „{place}“ nicht gefunden. Versuch den Namen ohne Postleitzahl, den nächsten "
                         "größeren Ort oder Koordinaten wie „48.87, 8.50“.")
    # postcode first, then places in German-speaking countries, otherwise as the service ranked them
    found.sort(key=lambda f: (0 if pc and pc in f["postcodes"] else 1,
                              NEAR.index(f["country"]) if f["country"] in NEAR else len(NEAR)))
    return found[:6]


async def geocode(place):
    """{"name", "lat", "lon"} of the best match, or ValueError."""
    best = (await candidates(place))[0]
    return {"name": best["name"] or _clean(place), "lat": best["lat"], "lon": best["lon"]}


def _store(uid, d):
    profiles._write(_file(uid), d)
    return d


async def set_place(uid, place, pick=None):
    """Sets the profile's place; pick ({"lat", "lon", "name"}) is one of the choices the page showed.
    Returns (place, other choices)."""
    if not str(place or "").strip() and not pick:
        try:
            os.remove(_file(uid))
        except OSError:
            pass
        return {}, []
    if pick:
        try:
            lat, lon = float(pick.get("lat")), float(pick.get("lon"))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Ungültige Koordinaten")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Ungültige Koordinaten")
        name = _clean(pick.get("name"), 80) or f"{lat:.3f}, {lon:.3f}"
        return _store(uid, {"name": name, "lat": lat, "lon": lon, "place": _clean(place) or name}), []
    found = await candidates(place)
    best = found[0]
    d = _store(uid, {"name": best["name"] or _clean(place), "lat": best["lat"], "lon": best["lon"], "place": _clean(place)})
    return d, found if len(found) > 1 else []


async def forecast(lat, lon, days=7):
    key = (round(lat, 3), round(lon, 3))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    url, _ = urls()
    params = {"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": max(2, min(14, days)),
              "current": "temperature_2m,weather_code",
              "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                       "precipitation_sum,wind_gusts_10m_max",
              "hourly": "precipitation_probability,temperature_2m"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as c:
        r = await c.get(url, params=params)
    r.raise_for_status()
    d = r.json()
    _cache[key] = (time.time(), d)
    return d


def _n(v):
    return int(round(float(v))) if isinstance(v, (int, float)) else None


def _deg(v):
    v = _n(v)
    return "minus " + str(-v) if v is not None and v < 0 else str(v)


def day_sentence(d, i, name, label):
    """'Morgen in Ulm: Regen, 4 bis 11 Grad, Regenrisiko 80 Prozent (3 Liter), Böen bis 55 km/h.'"""
    dy = d.get("daily") or {}

    def at(k):
        v = dy.get(k) or []
        return v[i] if i < len(v) else None
    code, hi, lo = at("weather_code"), at("temperature_2m_max"), at("temperature_2m_min")
    if hi is None or lo is None:
        return f"{label} in {name}: keine Vorhersage."
    parts = [CODES.get(_n(code), "wechselhaft"), f"{_deg(lo)} bis {_deg(hi)} Grad"]
    p, s = _n(at("precipitation_probability_max")), at("precipitation_sum")
    if p is not None and p >= 20:
        parts.append(f"Regenrisiko {p} Prozent" + (f" (etwa {s:.0f} Liter)" if isinstance(s, (int, float)) and s >= 1 else ""))
    g = _n(at("wind_gusts_10m_max"))
    if g is not None and g >= 40:
        parts.append(f"Böen bis {g} km/h")
    return f"{label} in {name}: " + ", ".join(parts) + "."


def rain_hours(d, now_iso, hours=12):
    """'Regen wahrscheinlich ab 14 Uhr.' for the next hours, or ''."""
    h = d.get("hourly") or {}
    times, probs = h.get("time") or [], h.get("precipitation_probability") or []
    start = next((i for i, x in enumerate(times) if x >= now_iso[:13]), None)
    if start is None:
        return ""
    for i in range(start, min(len(times), start + hours)):
        if i < len(probs) and isinstance(probs[i], (int, float)) and probs[i] >= 60:
            return f"Regen wahrscheinlich ab {int(times[i][11:13])} Uhr."
    return ""


def _label(day, today):
    k = (day - today).days
    return "Heute" if k == 0 else "Morgen" if k == 1 else "Übermorgen" if k == 2 else \
        f"{WEEKDAYS[day.weekday()]}, {day.day}.{day.month}."


async def report(lat, lon, name, first=None, days=1):
    """Fixed sentences for days from `first` (a date in the place's time zone; default today)."""
    d = await forecast(lat, lon, 7)
    dates = [datetime.date.fromisoformat(x) for x in (d.get("daily") or {}).get("time") or []]
    if not dates:
        return f"Für {name} gibt es gerade keine Vorhersage."
    today = dates[0]
    first = first or today
    out = []
    cur = d.get("current") or {}
    if first == today and isinstance(cur.get("temperature_2m"), (int, float)):
        out.append(f"Jetzt in {name}: {_deg(cur['temperature_2m'])} Grad, {CODES.get(_n(cur.get('weather_code')), 'wechselhaft')}.")
        r = rain_hours(d, str(cur.get("time") or ""))
        if r:
            out.append(r)
    found = [first + datetime.timedelta(days=k) for k in range(max(1, min(7, days)))]
    found = [x for x in found if x in dates]
    out += [day_sentence(d, dates.index(x), name, _label(x, today)) for x in found]
    if not found:
        out.append("Für diesen Tag gibt es keine Vorhersage (nur die nächsten 7 Tage).")
    return " ".join(out)


async def notable_tomorrow(uid):
    """(fixed sentence, ["rain", "frost", "heat", "storm"]) when tomorrow's weather is worth a word, else ("", [])."""
    w = get(uid)
    if not w:
        return "", []
    d = await forecast(w["lat"], w["lon"], 3)
    dy = d.get("daily") or {}
    if len(dy.get("time") or []) < 2:
        return "", []

    def at(k):
        v = dy.get(k) or []
        return v[1] if len(v) > 1 else None
    why = []
    if (_n(at("precipitation_probability_max")) or 0) >= 60:
        why.append("rain")
    if _n(at("temperature_2m_min")) is not None and _n(at("temperature_2m_min")) <= 0:
        why.append("frost")
    if (_n(at("temperature_2m_max")) or 0) >= 30:
        why.append("heat")
    if (_n(at("wind_gusts_10m_max")) or 0) >= 60:
        why.append("storm")
    return (day_sentence(d, 1, w["name"], "Morgen"), why) if why else ("", [])


# ---------------------------------------------------------------- assistant tool
TOOL = {"type": "function", "function": {
    "name": "weather",
    "description": "Weather forecast from a weather service: today (with the current temperature and rain in the "
                   "next hours), tomorrow or up to 7 days. Without place it is the user's home place.",
    "parameters": {"type": "object", "properties": {
        "place": {"type": "string", "description": "a town, only if the user named another place"},
        "date": {"type": "string", "description": "first day 'YYYY-MM-DD' (default today)"},
        "days": {"type": "integer", "description": "number of days, 1-7 (default 1)"}}}}}
HINT = ("Für Wetterfragen rufe weather auf und lies die Sätze aus dem Ergebnis vor, ohne Zahlen zu ändern "
        "oder etwas dazuzuerfinden.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not usable(who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "outside": set(), "filler": {"weather": ("Ich schaue nach dem Wetter.", "Let me check the weather.")}}


async def tool(name, args, ctx):
    w = get(ctx["who"]["id"])
    try:
        place = _clean(args.get("place"))
        if place and place.lower() not in (w.get("place", "").lower(), w.get("name", "").lower().split(",")[0]):
            w = await geocode(place)
        first = None
        if args.get("date"):
            try:
                first = datetime.date.fromisoformat(str(args["date"])[:10])
            except ValueError:
                first = None
        try:
            days = max(1, min(7, int(args.get("days") or 1)))
        except (TypeError, ValueError):
            days = 1
        return await report(w["lat"], w["lon"], w["name"], first, days)
    except ValueError as e:
        return f"Keine Vorhersage: {e}."
    except (httpx.HTTPError, KeyError) as e:
        return f"Der Wetterdienst ist gerade nicht erreichbar ({type(e).__name__}). Sag das so."


async def briefing(uid, zone=None):
    if not usable(uid):
        return ""
    w = get(uid)
    try:
        return "Weather (read these sentences as they are):\n" + await report(w["lat"], w["lon"], w["name"], None, 1)
    except (httpx.HTTPError, ValueError, KeyError):
        return "Weather: service not reachable."


# ---------------------------------------------------------------- API ("Ich" → Wetter)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from core import assistant, browser_profile, own_profile  # noqa: E402

router = APIRouter()


def _on():
    if not admin_on():
        raise HTTPException(403, "weather is turned off")


@router.get("/api/profile/weather", dependencies=[Depends(assistant)])
def api_get(prof=Depends(own_profile)):
    return {"place": get(prof["id"]), "on": bool(profiles.settings(prof["id"]).get("wx_on"))}


@router.put("/api/profile/weather", dependencies=[Depends(assistant), Depends(_on)])
async def api_set(request: Request, prof=Depends(browser_profile)):
    try:
        body = await request.json()
    except ValueError:
        body = {}
    try:
        body = body if isinstance(body, dict) else {}
        d, choices = await set_place(prof["id"], body.get("place", ""), body.get("pick") if isinstance(body.get("pick"), dict) else None)
        sample = await report(d["lat"], d["lon"], d["name"]) if d else ""
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Wetterdienst nicht erreichbar ({type(e).__name__})")
    return {"place": d, "sample": sample, "choices": choices}


@router.post("/api/profile/weather/test", dependencies=[Depends(assistant), Depends(_on)])
async def api_test(prof=Depends(own_profile)):
    w = get(prof["id"])
    if not w:
        raise HTTPException(400, "Kein Ort eingestellt")
    try:
        return {"text": await report(w["lat"], w["lon"], w["name"], None, 2)}
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Wetterdienst nicht erreichbar ({type(e).__name__})")
