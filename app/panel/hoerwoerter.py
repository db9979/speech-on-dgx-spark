"""Namen fürs Hören (plan genauer-und-schneller, 5): the speech recognition gets the names the profile may use.

Qwen3-ASR takes a short context text and then hears proper names much better. Without it, „Licht im Arbeitszimmer an“
or „Ruf Anke an“ come back misspelled, and the Weiche and Home Assistant miss the device or the person.

With the admin switch chat.hoer_namen (Funktionen → Tempo und Genauigkeit → Namen fürs Hören, off by default) the
panel adds, per recording of a signed-in profile (admin._test_asr):
  - the names of all profiles (who lives here),
  - the profile's contacts (only with Kontakte released for it),
  - the rooms and device names of the profile's own Home Assistant (only with Home Assistant released for it).
Shared speakers and the phone (esp32.transcribe) get only the profile names and the rooms of the house owner's Home
Assistant, never contacts. Guests get nothing.

The names are read in the background (Home Assistant over netguard.HOME, at most every REFRESH seconds) and kept in
memory only, never written to disk or into a log (the log line has counts only). The ASR runs on tars in the LAN.
"""
import asyncio
import re
import time

import features
import profiles

REFRESH = 1800          # seconds: Home Assistant names are read again after this
MAX_WORDS = 100         # names in one context, most useful first
MAX_CHARS = 700         # the ASR context stays short (it costs recognition time)
_cache = {}             # uid -> (time, [names from Home Assistant])
_busy = set()
_NAME = re.compile(r"[^\W\d_][\w .'\-]{0,38}")


def on(cfg):
    return bool((cfg.get("chat") or {}).get("hoer_namen"))


def _clean(names):
    """Unique, plain names (letters first, at most 40 chars), in their order."""
    out, seen = [], set()
    for n in names:
        n = re.sub(r"\s+", " ", str(n or "")).strip()
        if not _NAME.fullmatch(n) or n.lower() in seen:
            continue
        seen.add(n.lower())
        out.append(n)
    return out


def _contacts(uid, cfg):
    if not features.allowed("contacts", uid, cfg.get("chat")):
        return []
    import contacts
    return [x.get("name", "") for x in contacts.cards(uid)][:60]


async def _read_ha(uid):
    """Rooms and device names of the profile's Home Assistant (background)."""
    import homeassistant
    try:
        item = homeassistant.get(uid)
        if not item:
            _cache[uid] = (time.time(), [])
            return
        all_states, areas, names = await homeassistant._switchable(item)
        rooms = sorted(set(areas.values()))
        devs = [names[s["entity_id"]] for s in all_states if s["entity_id"] in names]
        _cache[uid] = (time.time(), _clean(rooms + devs))
        print(f"hoeren: Namen gelesen, {len(rooms)} Räume, {len(devs)} Geräte", flush=True)
    except Exception as e:   # unreachable or refused: tried again after REFRESH, the recognition goes on without
        _cache[uid] = (time.time(), (_cache.get(uid) or (0, []))[1])
        print("hoeren: Home Assistant nicht gelesen,", type(e).__name__, flush=True)
    finally:
        _busy.discard(uid)


def _ha(uid, cfg, now=None):
    """The cached Home Assistant names; starts a background read when they are old (never waits for it)."""
    if not features.allowed("ha", uid, cfg.get("chat")):
        return []
    now = time.time() if now is None else now
    hit = _cache.get(uid)
    if (not hit or now - hit[0] > REFRESH) and uid not in _busy:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop:
            _busy.add(uid)
            loop.create_task(_read_ha(uid))
    return hit[1] if hit else []


def words(cfg, uid=None, shared=False):
    """The names for one recording: profile names, then (own profile) contacts and Home Assistant."""
    if not on(cfg):
        return []
    names = [p["name"] for p in profiles.names()] + [p["call"] for p in profiles.names() if p.get("call")]
    if uid and not shared:
        names += _ha(uid, cfg) + _contacts(uid, cfg)
    elif shared and uid:   # a shared speaker: rooms and devices of its owner, never contacts
        names += _ha(uid, cfg)
    return _clean(names)[:MAX_WORDS]


def prompt(cfg, uid=None, shared=False, extra=""):
    """The ASR context: extra words (wake word), the names, the admin's own context; "" when there is nothing."""
    base = (cfg.get("asr") or {}).get("context") or ""
    names = words(cfg, uid, shared)
    parts = [extra.strip()] if extra.strip() else []
    if names:
        parts.append(", ".join(names) + ".")
    if base:
        parts.append(base)
    return " ".join(parts)[:MAX_CHARS].strip()
