"""The voice assistant: /api/chat with its tools (search, memory, documents, reminders, calendar,
Home Assistant, earlier conversations), learning from conversations, and the Pebble watch endpoints."""
import asyncio
import datetime
import json
import os
import re
import html.parser
import secrets
import sys
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from textnorm import guess_language  # noqa: E402
import documents  # noqa: E402
import speakers  # noqa: E402
import calendars  # noqa: E402
import profiles  # noqa: E402
import recall  # noqa: E402
import homeassistant  # noqa: E402
import watch  # noqa: E402
from common import load_config  # noqa: E402
from core import DEFAULTS, api_headers, assistant  # noqa: E402

router = APIRouter()


LEARN_EVERY = 300


async def learn_once():
    """Reads quiet conversations of profiles that allow it and keeps a few lasting facts (marked
    "auto"). Runs only while nobody is chatting, so it never slows down an answer."""
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    if not (ccfg.get("memory", True) and ccfg.get("history", True) and ccfg.get("llm_url")):
        return 0
    adm = profiles.defaults(ccfg.get("defaults"))
    headers = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
    saved = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
        for uid in profiles.user_ids():
            if not dict(adm, **profiles.settings(uid)).get("learn", True):
                continue
            prof = profiles.by_id(uid)
            for convo in recall.pending(uid, time.time() * 1000)[:5]:  # the rest next time
                if time.time() - _last_chat[0] < 60:
                    return saved  # someone is talking: try again later
                payload = {"model": await llm_model(c, ccfg, headers), "temperature": 0.2, "max_tokens": 400,
                           "messages": recall.learn_messages(prof, convo),
                           "chat_template_kwargs": {"enable_thinking": False}}
                r = await c.post(ccfg["llm_url"].rstrip("/") + "/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                known = {x["text"].lower() for x in profiles.memory(uid)}
                for fact in recall.parse_facts(r.json()["choices"][0]["message"].get("content") or ""):
                    if fact.lower() not in known:
                        saved += bool(profiles.remember(uid, fact, auto=True))
                recall.mark(uid, convo)
    return saved


# ---------------------------------------------------------------- voice chat
# The browser records a question, /api/test/asr turns it into text, and /api/chat streams the
# answer: LLM tokens are cut into sentences as they arrive, each sentence goes to the streaming
# TTS while the LLM keeps writing, and text and audio come back as one Server-Sent Events stream.
ABBREV = {"z", "b", "d", "h", "u", "a", "bzw", "ca", "dr", "nr", "usw", "vgl", "etc", "evtl", "ggf", "inkl",
          "max", "min", "mio", "mrd", "str", "tel", "e.g", "i.e", "vs", "mr", "mrs", "st", "prof", "jr", "sr"}
BOUNDARY = re.compile(r"[.!?…]+[\"“”»')\]]*\s+|\n+")


def split_sentences(buf, first):
    """Cut finished sentences off the front of buf. Returns (sentences, rest). A long first
    sentence is also cut at a comma, so the first audio does not wait for the whole sentence."""
    out, start = [], 0
    for m in BOUNDARY.finditer(buf):
        head = buf[start:m.start()]
        word = re.findall(r"[\w.]+$", head)
        last = word[0].lower().rstrip(".") if word else ""
        if m.group(0)[0] == "." and (last in ABBREV or len(last) == 1 or last[-1:].isdigit()):
            continue  # "z. B.", "5. Oktober", "3.5" are no sentence ends
        piece = buf[start:m.end()].strip()
        if piece:
            out.append(piece)
        start = m.end()
    rest = buf[start:]
    if first and not out and len(rest) > 120 and ", " in rest[40:]:
        cut = rest.rindex(", ") + 1
        out, rest = [rest[:cut].strip()], rest[cut:]
    return out, rest


_llm_models = {}


async def llm_model(c, ccfg, headers):
    if ccfg.get("llm_model"):
        return ccfg["llm_model"]
    url = ccfg["llm_url"].rstrip("/")
    if url not in _llm_models:
        r = await c.get(url + "/models", headers=headers, timeout=10)
        r.raise_for_status()
        _llm_models[url] = r.json()["data"][0]["id"]
    return _llm_models[url]


# Web search through the user's own SearXNG instance, offered to the LLM as a tool. SearXNG must
# allow the JSON format (settings.yml: search.formats: [html, json]).
SEARCH_TOOL = {"type": "function", "function": {
    "name": "web_search",
    "description": "Search the web for current or unknown information (news, prices, weather, events, "
                   "facts after your training). Returns result snippets and the text of the top pages.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "search query"}},
                   "required": ["query"]}}}
SEARCH_HINT = ("Du kannst mit dem Werkzeug web_search im Internet suchen. Nutze es, wenn die Frage aktuelle "
               "oder dir unbekannte Informationen braucht, sonst nicht. Fasse das Gefundene in eigenen Worten "
               "kurz zusammen und lies keine Adressen oder Links vor.")


# Memory per profile. The tools only ever act on the profile of the request (cookie or device
# key); the model cannot name another profile.
MEMORY_TOOLS = [
    {"type": "function", "function": {
        "name": "memory_save",
        "description": "Remember a fact about the user for later conversations (name, preferences, people, "
                       "plans). Use it when the user asks you to remember something or tells you something "
                       "clearly worth keeping. One short fact per call, in the third person.",
        "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}}},
    {"type": "function", "function": {
        "name": "memory_forget",
        "description": "Forget remembered facts that contain the given words, when the user asks you to.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]


HISTORY_TOOL = {"type": "function", "function": {
    "name": "history_search",
    "description": "Search the user's earlier conversations with you (not the current one). Use it when the "
                   "user refers to something talked about before ('last time', 'what did you say about ...', "
                   "'what did we talk about yesterday'). Without a query it lists the recent conversations.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "keywords; empty for an overview"},
        "days": {"type": "integer", "description": "only conversations of the last N days"}}}}}
HISTORY_HINT = ("Mit history_search findest du, worüber ihr in früheren Gesprächen gesprochen habt. Nutze es, "
                "wenn der Nutzer sich auf etwas Früheres bezieht, und erfinde nichts, was dort nicht steht.")


HA_TOOL = {"type": "function", "function": {
    "name": "home_assistant",
    "description": "Control or ask the user's smart home through Home Assistant: switch lights and devices, "
                   "set temperatures, open covers. For reading values, zones or where someone is use "
                   "home_assistant_states. "
                   "Give one short command in the user's language, naming device and room as the user did.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string",
                   "description": "e.g. 'Schalte das Licht im Wohnzimmer an'"}}, "required": ["command"]}}}
HA_STATES_TOOL = {"type": "function", "function": {
    "name": "home_assistant_states",
    "description": "Read the user's smart home: every sensor value, device state, zone and person location "
                   "Home Assistant has, also devices not exposed to its voice assistant. Search with a few "
                   "words (device, room, kind: 'Temperatur Wohnzimmer', 'Fenster offen', 'Akku', 'Zone'); "
                   "without anything you get an overview of rooms, zones and people. An exact entity id "
                   "(e.g. 'sensor.wohnzimmer_temperatur') returns all its attributes.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "words to search for, or one entity id; empty for an overview"},
        "domain": {"type": "string", "description": "optional kind: sensor, binary_sensor, light, switch, climate, "
                                                    "cover, zone, person, device_tracker, media_player, weather ..."},
        "area": {"type": "string", "description": "optional room or area name"}}}}}
HA_ACTION_TOOL = {"type": "function", "function": {
    "name": "home_assistant_action",
    "description": "Switch or set one device directly by its entity id, also devices home_assistant (Assist) "
                   "does not know. Use it when home_assistant did not find the device. Find the id first with "
                   "home_assistant_states. Not for locks, alarm systems or updates.",
    "parameters": {"type": "object", "properties": {
        "entity_id": {"type": "string", "description": "exact id, e.g. light.kueche"},
        "service": {"type": "string", "description": "turn_on, turn_off, toggle, open_cover, close_cover, "
                                                     "set_cover_position, set_temperature, set_hvac_mode, "
                                                     "volume_set, media_pause, press, select_option, set_value ..."},
        "data": {"type": "object", "description": "optional values, e.g. {\"brightness_pct\": 50}, "
                                                  "{\"temperature\": 21}, {\"position\": 30}"}},
        "required": ["entity_id", "service"]}}}
HA_HINT = ("Mit home_assistant steuerst du das Smart Home des Nutzers (Licht, Geräte, Heizung, Rollläden). Gib jeden "
           "Befehl einzeln weiter und sag danach kurz, was passiert ist; behaupte nichts, was Home Assistant nicht "
           "bestätigt hat. Für Fragen nach Werten, Zuständen, Zonen und wo jemand ist nimm home_assistant_states: "
           "es sieht alle Geräte, auch die, die der Sprachassistent von Home Assistant nicht kennt. Findet "
           "home_assistant ein Gerät nicht, such es mit home_assistant_states und schalte es mit "
           "home_assistant_action über seine genaue ID. "
           "Erfinde keine Werte; findest du nichts, such mit anderen Wörtern oder hol dir die Übersicht.")


DOC_TOOL = {"type": "function", "function": {
    "name": "document_search",
    "description": "Search the user's own uploaded documents. Use it when a question may be answered by "
                   "them. Returns the best-matching passages with the document name.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "keywords"}},
                   "required": ["query"]}}}


REMINDER_TOOLS = [
    {"type": "function", "function": {
        "name": "reminder_set",
        "description": "Set a timer or reminder. Give either minutes from now (timers, 'in 10 minutes') or a "
                       "local date and time 'YYYY-MM-DDTHH:MM' (reminders at a clock time). The device rings "
                       "and speaks the text when it is due.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "what to remind of, short, e.g. 'Ofen ausschalten'"},
            "minutes": {"type": "number"}, "at": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "reminder_list", "description": "List the pending timers and reminders.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "reminder_cancel", "description": "Cancel timers or reminders whose text contains the words "
                                                  "(or all, with text 'alle').",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]
WATCH_HINT = ("Die Frage kommt von einer Smartwatch mit kleinem Display und kleinem Lautsprecher. Antworte "
              "kurz, meist in ein bis drei Sätzen, ohne Listen, Tabellen oder Links.")
REMINDER_HINT = ("Mit reminder_set stellst du Timer und Erinnerungen, mit reminder_list und reminder_cancel "
                 "siehst und löschst du sie. Bestätige kurz, wann es klingelt.")


CALENDAR_TOOL = {"type": "function", "function": {
    "name": "calendar_events",
    "description": "Read the user's calendar: the appointments from a local date for a number of days.",
    "parameters": {"type": "object", "properties": {
        "date": {"type": "string", "description": "first day, 'YYYY-MM-DD' (default today)"},
        "days": {"type": "integer", "description": "number of days, 1-31 (default 1)"}}}}}
BRIEFING_TOOL = {"type": "function", "function": {
    "name": "daily_briefing",
    "description": "Everything for a daily briefing: today's and tomorrow's appointments, today's reminders "
                   "and the latest on the user's chosen topics (news, weather ...).",
    "parameters": {"type": "object", "properties": {}}}}
BRIEFING_HINT = ("Wenn der Nutzer um ein Tagesbriefing bittet, wissen will, was heute ansteht, oder dich am "
                 "Morgen mit „Guten Morgen“ begrüßt, rufe daily_briefing auf. Fasse es gesprochen und natürlich "
                 "zusammen: kurzer Gruß, die heutigen Termine in zeitlicher Reihenfolge mit Uhrzeit, dann die "
                 "Erinnerungen, dann zu jedem Thema ein bis zwei Sätze. Keine Aufzählungszeichen, keine Links.")
CALENDAR_HINT = "Für Fragen zu Terminen an bestimmten Tagen nutze calendar_events."


def user_zone(tz):
    if isinstance(tz, str) and re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}", tz):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(tz)
        except Exception:
            pass
    return datetime.datetime.now().astimezone().tzinfo


def reminder_due(args, tz):
    """Epoch milliseconds when a reminder is due, or None."""
    try:
        if args.get("minutes") not in (None, ""):
            m = float(args["minutes"])
            return int((time.time() + m * 60) * 1000) if 0 < m <= 60 * 24 * 366 else None
        if args.get("at"):
            at = datetime.datetime.fromisoformat(str(args["at"]).strip().replace("Z", ""))
            if at.tzinfo is None:
                at = at.replace(tzinfo=user_zone(tz))
            due = int(at.timestamp() * 1000)
            return due if due > time.time() * 1000 else None
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def docs_hint(prof, docs):
    names = ", ".join(d["name"] for d in docs[:30]) + (" …" if len(docs) > 30 else "")
    return (f"{prof['name']} hat eigene Dokumente hochgeladen: {names}. Wenn eine Frage dazu passen könnte, "
            "suche mit document_search darin und antworte aus den Treffern; nenne das Dokument kurz.")


def memory_hint(prof):
    facts = profiles.memory(prof["id"])
    hint = (f"Du sprichst mit {prof['name']}. Mit memory_save merkst du dir dauerhaft, was {prof['name']} dir "
            "zum Merken sagt oder was für spätere Gespräche nützlich ist, mit memory_forget vergisst du es "
            "auf Wunsch. Sag kurz, dass du es dir gemerkt hast.")
    if facts:
        hint += f"\nWas du über {prof['name']} weißt:\n" + "\n".join("- " + x["text"] for x in facts)
    return hint


class _PageText(html.parser.HTMLParser):
    """Visible text of a web page, without scripts, styles and page furniture."""
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "template"}

    def __init__(self):
        super().__init__()
        self.depth, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth and data.strip():
            self.parts.append(data.strip())


async def page_text(c, url, limit=3000):
    try:
        async with c.stream("GET", url, timeout=6, follow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 (speech-on-dgx-spark)"}) as r:
            if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                return ""
            raw = b""
            async for chunk in r.aiter_bytes():
                raw += chunk
                if len(raw) > 1_500_000:
                    break
        p = _PageText()
        p.feed(raw.decode(r.encoding or "utf-8", errors="replace"))
        return re.sub(r"\s+", " ", " ".join(p.parts))[:limit]
    except Exception:
        return ""


class _SearxResults(html.parser.HTMLParser):
    """Results from SearXNG's normal HTML page, for instances that do not allow the JSON format:
    <article class="result ..."> with <h3><a href=URL>title</a></h3> and <p class="content">."""

    def __init__(self):
        super().__init__()
        self.results, self.cur, self.field = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "article" and "result" in cls:
            self.cur = {"title": "", "url": "", "content": ""}
            self.results.append(self.cur)
        elif self.cur is not None:
            if tag == "a" and self.field is None and not self.cur["url"] and self._in_h3:
                self.cur["url"], self.field = a.get("href", ""), "title"
            elif tag == "p" and "content" in cls:
                self.field = "content"
        if tag == "h3":
            self._in_h3 = True

    _in_h3 = False

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False
        if (tag == "a" and self.field == "title") or (tag == "p" and self.field == "content"):
            self.field = None
        if tag == "article":
            self.cur, self.field = None, None

    def handle_data(self, data):
        if self.cur is not None and self.field:
            self.cur[self.field] += data


async def web_search(c, ccfg, query):
    """Returns (text for the LLM, [{title, url}])."""
    url = ccfg["search_url"].rstrip("/")
    url = url if url.endswith("/search") else url + "/search"
    r = await c.get(url, params={"q": query, "format": "json"}, timeout=10, follow_redirects=True)
    if r.status_code == 403:  # JSON not enabled on this instance: read the normal results page
        r = await c.get(url, params={"q": query}, timeout=10, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) speech-on-dgx-spark",
            "Accept": "text/html", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
        if r.status_code == 429:
            raise RuntimeError("SearXNG rate limiter blocks the Spark (429): allow its IP in limiter.toml (pass_ip)")
        r.raise_for_status()
        p = _SearxResults()
        p.feed(r.text)
        raw = [{k: v.strip() for k, v in x.items()} for x in p.results]
    else:
        if r.status_code == 429:
            raise RuntimeError("SearXNG rate limiter blocks the Spark (429): allow its IP in limiter.toml (pass_ip)")
        r.raise_for_status()
        raw = r.json().get("results", [])
    results = [x for x in raw if str(x.get("url", "")).startswith(("http://", "https://"))]
    results = results[:int(ccfg.get("search_results") or 5)]
    if not results:
        return "No results.", []
    pages = int(ccfg.get("search_pages") or 0)
    texts = await asyncio.gather(*(page_text(c, x["url"]) for x in results[:pages]))
    lines = [f"Search results for: {query}"]
    for i, x in enumerate(results):
        lines.append(f"[{i + 1}] {x.get('title', '')} ({x['url']})\n{(x.get('content') or '').strip()}")
        if i < len(texts) and texts[i]:
            lines.append(f"Page text: {texts[i]}")
    return "\n\n".join(lines)[:12000], [{"title": x.get("title") or x["url"], "url": x["url"]} for x in results]


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]


def now_line(tz=None):
    """The LLM does not know the date; the browser's time zone is used, else the Spark's."""
    now = None
    if isinstance(tz, str) and re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}", tz):
        try:
            from zoneinfo import ZoneInfo
            now = datetime.datetime.now(ZoneInfo(tz))
        except Exception:
            now = None
    if now is None:
        now, tz = datetime.datetime.now().astimezone(), time.strftime("%Z")
    return (f"Aktuelles Datum und Uhrzeit: {WEEKDAYS[now.weekday()]}, {now.day}. {MONTHS[now.month - 1]} "
            f"{now.year}, {now:%H:%M} Uhr (Zeitzone {tz}). Nutze das nur, wenn es zur Frage passt.")


_last_chat = [0.0]


@router.post("/api/chat", dependencies=[Depends(assistant)])
async def chat(request: Request):
    _last_chat[0] = time.time()
    body = await request.json()
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    messages = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant") and m.get("content")]
    if not messages:
        raise HTTPException(400, "messages are required")
    system = ccfg.get("system_prompt") or ""
    if ccfg.get("datetime", True):
        system = (system + "\n\n" + now_line(body.get("tz"))).strip()
    search = bool(ccfg.get("search") and ccfg.get("search_url"))
    if search:
        system = (system + "\n\n" + SEARCH_HINT).strip()
    who = profiles.current(request)
    # A voice recognized by the speech recognition (signed token, see speakers.py) picks that
    # profile for this turn; its own settings apply then, not the ones this browser sends.
    heard = speakers.check(body.get("speaker")) if ccfg.get("speaker_id", False) and body.get("speaker") else None
    heard = heard and profiles.by_id(heard)
    own_browser = not heard or (who and who["id"] == heard["id"])
    if heard:
        who = heard
    if not own_browser:
        # someone else's voice at this browser: the browser's conversation is not theirs, so it is
        # not sent along (and the browser keeps this turn out of its own history, see "foreign")
        messages = [m for m in messages[-1:] if m["role"] == "user"]
        if not messages:
            raise HTTPException(400, "a question is required")
    # conversation settings: what the request sends, else the profile's, else the admin's defaults
    # (speakers with a device key send nothing and get their profile's voice, speed and length)
    pset = dict(profiles.defaults(ccfg.get("defaults")), **(profiles.settings(who["id"]) if who else {}))
    for k in (("voice", "speed", "length") if who else ("speed", "length")) if own_browser else ():
        if k in body and profiles.SETTINGS[k][1](body[k]):
            pset[k] = body[k]
    length = {"short": "Antworte besonders knapp, meist in ein bis zwei Sätzen.",
              "long": "Du darfst ausführlicher antworten, wenn die Frage es hergibt."}.get(pset["length"])
    if length:
        system = (system + "\n\n" + length).strip()
    if body.get("client") == "watch":
        system = (system + "\n\n" + WATCH_HINT).strip()
    prof = who if ccfg.get("memory", True) else None
    if prof:  # guests get no memory at all
        system = (system + "\n\n" + memory_hint(prof)).strip()
    past = bool(prof and ccfg.get("history", True))
    if past:
        system = (system + "\n\n" + HISTORY_HINT).strip()
    # Home Assistant only for the profile's own login or device key: a voice recognized at someone
    # else's device does not switch that profile's home
    ha = homeassistant.get(who["id"]) if who and own_browser and ccfg.get("homeassistant", False) else None
    if ha:
        system = (system + "\n\n" + HA_HINT).strip()
    docs = documents.list_docs(who["id"]) if who and ccfg.get("documents", True) else []
    if docs:
        system = (system + "\n\n" + docs_hint(who, docs)).strip()
    timers = bool(ccfg.get("reminders", True))
    if timers:
        system = (system + "\n\n" + REMINDER_HINT).strip()
    # guests keep their reminders in the browser, which sends them along; profiles keep them on the Spark
    guest_rem = [{"id": x["id"][:16], "text": str(x.get("text", ""))[:200], "due": x["due"]}
                 for x in (body.get("reminders") if isinstance(body.get("reminders"), list) else [])
                 if isinstance(x, dict) and isinstance(x.get("id"), str)
                 and isinstance(x.get("due"), (int, float))][:50] if not who else []
    briefing = bool(ccfg.get("calendar", True))
    cal = calendars.get(who["id"]) if who and briefing else {"calendars": [], "topics": []}
    if briefing:
        system = (system + "\n\n" + BRIEFING_HINT + (" " + CALENDAR_HINT if cal["calendars"] else "")).strip()
    tools = ([SEARCH_TOOL] if search else []) + (MEMORY_TOOLS if prof else []) + ([HISTORY_TOOL] if past else []) \
        + ([DOC_TOOL] if docs else []) + ([HA_TOOL, HA_STATES_TOOL, HA_ACTION_TOOL] if ha else []) \
        + (REMINDER_TOOLS if timers else []) + ([BRIEFING_TOOL] if briefing else []) \
        + ([CALENDAR_TOOL] if cal["calendars"] else [])
    if system:
        messages = [{"role": "system", "content": system}] + messages
    lheaders = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
    tts_url = f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech"
    tts_body = {k: body[k] for k in ("language", "instructions") if body.get(k)}
    if pset["voice"]:
        tts_body["voice"] = pset["voice"]
    if pset["speed"] != 1.0:
        tts_body["speed"] = pset["speed"]
    c = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5))
    out = asyncio.Queue()
    if heard:
        out.put_nowait({"type": "speaker", "name": heard["name"], "foreign": not own_browser})
    sentences = asyncio.Queue()
    t0 = time.time()

    async def llm():
        try:
            model = await llm_model(c, ccfg, lheaders)
            base = {"model": model, "stream": True, "max_tokens": int(ccfg.get("max_tokens") or 4096)}
            if not ccfg.get("thinking"):
                base["chat_template_kwargs"] = {"enable_thinking": False}
            st = {"buf": "", "first": True, "think": False, "n": 0}
            msgs, finish = list(messages), None
            searches = 0
            for rnd in range(4):  # a few tool rounds (at most two searches), then the answer
                payload = dict(base, messages=msgs)
                offer = [t for t in tools if t is not SEARCH_TOOL or searches < 2] if rnd < 3 else []
                if offer:
                    payload["tools"] = offer
                finish, calls = await llm_round(payload, st)
                if not calls or finish == "length":
                    break
                msgs.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": x["id"], "type": "function", "function": {"name": x["name"], "arguments": x["arguments"]}}
                    for x in calls]})
                for x in calls:
                    try:
                        args = json.loads(x["arguments"] or "{}")
                        args = args if isinstance(args, dict) else {}
                    except ValueError:
                        args = {}
                    msgs.append({"role": "tool", "tool_call_id": x["id"], "content": await run_tool(x["name"], args, st)})
                    if x["name"] == "web_search":
                        searches += 1
            buf = st["buf"]
            if finish == "length":
                # The answer hit max_tokens mid-sentence: speak up to the last sentence end and
                # tell the browser how much of the shown text to drop.
                ends = [m.end() for m in BOUNDARY.finditer(buf + " ")]
                keep = buf[:min(ends[-1], len(buf))] if ends else ""
                await out.put({"type": "truncated", "drop": len(buf) - len(keep)})
                buf = keep
            if buf.strip():
                await sentences.put(buf.strip())
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (401, 403) or re.match(r"LLM HTTP 40[13]\b", str(e)):
                await out.put({"type": "error", "code": "llm_auth",
                               "message": "LLM: API key rejected (401). Set the qwen38 key under Konfiguration -> Assistent."})
            else:
                await out.put({"type": "error", "message": f"LLM: {type(e).__name__}: {e}"})
        finally:
            await sentences.put(None)

    async def run_tool(name, args, st):
        if name == "web_search" and search:
            query = str(args.get("query", "")).strip()
            if not query:
                return "No query given."
            await out.put({"type": "search", "query": query})
            if st["first"]:  # something to hear while the search runs
                st["first"] = False
                en = guess_language(messages[-1]["content"]) == "English"
                await sentences.put("Let me look that up." if en else "Ich schaue kurz nach.")
            try:
                result, sources = await web_search(c, ccfg, query)
                await out.put({"type": "sources", "items": sources})
                return result
            except Exception as e:
                await out.put({"type": "search_error", "message": str(e)})
                return f"Search failed: {e}"
        if name == "home_assistant" and ha:
            text = str(args.get("command", "")).strip()
            if not text:
                return "No command given."
            await out.put({"type": "home", "command": text})
            try:
                ok, answer, targets = await homeassistant.command(
                    ha, text, "en" if guess_language(text) == "English" else "de")
            except httpx.HTTPError as e:
                await out.put({"type": "home_done", "ok": False, "text": str(e)[:200]})
                return f"Home Assistant not reachable: {type(e).__name__}"
            await out.put({"type": "home_done", "ok": ok, "text": answer, "targets": targets})
            return ("Home Assistant: " if ok else "Home Assistant failed: ") + answer \
                + (f" (devices: {', '.join(targets)})" if targets else "")
        if name == "home_assistant_states" and ha:
            query = str(args.get("query", "") or "").strip()
            label = " ".join(x for x in (query, str(args.get("area", "") or ""), str(args.get("domain", "") or "")) if x)
            await out.put({"type": "home", "command": "? " + (label or "Übersicht")})
            try:
                n, result = await homeassistant.states(ha, query, str(args.get("domain", "") or ""),
                                                       str(args.get("area", "") or ""))
            except (httpx.HTTPError, ValueError) as e:
                await out.put({"type": "home_done", "ok": False, "text": str(e)[:200] or type(e).__name__})
                return f"Home Assistant not reachable: {type(e).__name__}"
            await out.put({"type": "home_done", "ok": n > 0, "text": f"{n} Treffer"})
            return result
        if name == "home_assistant_action" and ha:
            eid, service = str(args.get("entity_id", "")), str(args.get("service", ""))
            await out.put({"type": "home", "command": f"{eid} {service}".strip()})
            try:
                ok, result = await homeassistant.action(ha, eid, service, args.get("data"))
            except (httpx.HTTPError, ValueError) as e:
                await out.put({"type": "home_done", "ok": False, "text": str(e)[:200] or type(e).__name__})
                return f"Home Assistant not reachable: {type(e).__name__}"
            await out.put({"type": "home_done", "ok": ok, "text": result[:200]})
            return ("Home Assistant: " if ok else "Home Assistant failed: ") + result
        if name == "history_search" and past:
            query = str(args.get("query", "")).strip()
            try:
                days = min(3650, max(1, int(args["days"]))) if args.get("days") not in (None, "") else None
            except (TypeError, ValueError):
                days = None
            await out.put({"type": "historysearch", "query": query})
            skip = body.get("convo") if own_browser and isinstance(body.get("convo"), str) else None
            return await asyncio.to_thread(recall.search, prof["id"], query, days, skip)
        if name == "document_search" and docs:
            query = str(args.get("query", "")).strip()
            await out.put({"type": "docsearch", "query": query})
            hits = await asyncio.to_thread(documents.search, who["id"], query)
            if hits:
                await out.put({"type": "docsources", "items": sorted({h["name"] for h in hits})})
            return "\n\n".join(f"[{h['name']}]\n{h['text']}" for h in hits) or "No matching passages."
        if name.startswith("reminder_") and timers:
            pending = profiles.reminders(who["id"]) if who else guest_rem
            zone = user_zone(body.get("tz"))
            fmt = lambda x: datetime.datetime.fromtimestamp(x["due"] / 1000, zone).strftime("%d.%m. %H:%M")  # noqa: E731
            if name == "reminder_set":
                text = str(args.get("text", "")).strip() or "Timer"
                due = reminder_due(args, body.get("tz"))
                if not due:
                    return "Invalid time: give minutes from now or a future 'YYYY-MM-DDTHH:MM'."
                item = profiles.add_reminder(who["id"], text, due) if who else \
                    {"id": secrets.token_hex(4), "text": text[:200], "due": due}
                await out.put({"type": "reminder", "action": "set", "item": item, "foreign": not own_browser})
                return f"Set: '{item['text']}' at {fmt(item)}."
            if name == "reminder_list":
                return "\n".join(f"{fmt(x)}: {x['text']}" for x in pending) or "No pending reminders."
            if name == "reminder_cancel":
                t = str(args.get("text", "")).strip().lower()
                ids = {x["id"] for x in pending if t in ("alle", "all") or (t and t in x["text"].lower())}
                if who and ids:
                    profiles.remove_reminders(who["id"], ids)
                if ids:
                    await out.put({"type": "reminder", "action": "cancel", "ids": sorted(ids), "foreign": not own_browser})
                return f"Cancelled {len(ids)}."
        if name == "calendar_events" and cal["calendars"]:
            zone = user_zone(body.get("tz"))
            try:
                day = datetime.date.fromisoformat(str(args.get("date") or "")[:10])
            except ValueError:
                day = datetime.datetime.now(zone).date()
            try:
                days = min(31, max(1, int(args.get("days") or 1)))
            except (TypeError, ValueError):
                days = 1
            await out.put({"type": "calendar"})
            start = datetime.datetime.combine(day, datetime.time(), zone)
            try:
                evs, errors = await calendars.events(who["id"], start, start + datetime.timedelta(days=days), zone)
            except (ValueError, httpx.HTTPError) as e:
                return f"Calendar not reachable: {e}"
            return ("\n".join(calendars.line(x) for x in evs) or "No appointments in this period.") \
                + "".join(f"\nCalendar '{n}' could not be read: {e}" for n, e in errors)
        if name == "daily_briefing" and briefing:
            return await briefing_text(st)
        if name == "memory_save" and prof:
            fact = profiles.remember(prof["id"], args.get("fact", ""))
            if fact:
                await out.put({"type": "memory", "action": "saved", "text": fact})
            return "Saved." if fact else "Nothing to save."
        if name == "memory_forget" and prof:
            text = str(args.get("text", "")).strip()
            n = profiles.forget(prof["id"], text=text) if len(text) >= 2 else 0  # never "forget everything"
            if n:
                await out.put({"type": "memory", "action": "forgotten", "text": text})
            return f"Forgot {n} fact(s)."
        return f"Unknown tool {name}."

    async def briefing_text(st):
        zone = user_zone(body.get("tz"))
        now = datetime.datetime.now(zone)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        await out.put({"type": "briefing"})
        topics = cal["topics"] if search else []
        jobs = [calendars.events(who["id"], today, today + datetime.timedelta(days=2), zone)
                if cal["calendars"] else asyncio.sleep(0)]
        quick = dict(ccfg, search_pages=0, search_results=3)
        jobs += [web_search(c, quick, q) for q in topics]
        if topics:
            await out.put({"type": "search", "query": " · ".join(topics)})
            if st["first"]:  # something to hear while the searches run
                st["first"] = False
                await sentences.put("Einen Moment, ich stelle alles zusammen.")
        res = await asyncio.gather(*jobs, return_exceptions=True)
        parts = [now_line(body.get("tz")).split(" Nutze")[0]]
        if not cal["calendars"]:
            parts.append("Calendar: none connected" + ("" if who else " (guests have none)") + ".")
        elif isinstance(res[0], Exception):
            parts.append(f"Calendar not reachable: {res[0]}")
        else:
            res[0], errors = res[0]
            parts += [f"Calendar '{n}' could not be read: {e}" for n, e in errors]
            tomorrow = today + datetime.timedelta(days=1)
            for label, a, b in (("Today", today, tomorrow), ("Tomorrow", tomorrow, tomorrow + datetime.timedelta(days=1))):
                evs = [x for x in res[0] if x["start"] < b and (x["end"] > a or x["start"] >= a)]
                parts.append(f"{label}'s appointments:\n" + ("\n".join(
                    calendars.line(x) + (" (already over)" if not x["allday"] and x["end"] <= now else "")
                    for x in evs) or "none"))
        if timers:
            end = (today + datetime.timedelta(days=1)).timestamp() * 1000
            pend = [x for x in (profiles.reminders(who["id"]) if who else guest_rem) if x["due"] < end]
            parts.append("Reminders today:\n" + ("\n".join(
                f"{datetime.datetime.fromtimestamp(x['due'] / 1000, zone):%H:%M} {x['text']}" for x in pend) or "none"))
        srcs = []
        for q, r in zip(topics, res[1:]):
            if isinstance(r, Exception):
                parts.append(f"Topic '{q}': search failed")
            else:
                parts.append(f"Topic '{q}':\n{r[0][:2500]}")
                srcs += r[1][:2]
        if srcs:
            await out.put({"type": "sources", "items": srcs})
        return "\n\n".join(parts)

    async def llm_round(payload, st):
        """Streams one LLM call: text goes to the browser and, sentence by sentence, to TTS.
        Returns (finish_reason, tool calls)."""
        finish, calls = None, {}
        async with c.stream("POST", ccfg["llm_url"].rstrip("/") + "/chat/completions",
                            json=payload, headers=lheaders) as r:
            if r.status_code != 200:
                raise RuntimeError(f"LLM HTTP {r.status_code}: {(await r.aread()).decode(errors='replace')[:300]}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue  # SSE comments and keep-alives
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    choice = json.loads(data)["choices"][0]
                    delta = choice.get("delta") or {}
                except (ValueError, KeyError, IndexError):
                    continue
                finish = choice.get("finish_reason") or finish
                for tc in delta.get("tool_calls") or []:  # arrives in pieces, keyed by index
                    x = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                    x["id"] = tc.get("id") or x["id"]
                    fn = tc.get("function") or {}
                    x["name"] = fn.get("name") or x["name"]
                    x["arguments"] += fn.get("arguments") or ""
                text = delta.get("content") or ""
                if not text:
                    continue
                # models that think inline: drop <think>...</think> from what is spoken
                if "<think>" in text:
                    st["think"], text = True, text.split("<think>")[0]
                if st["think"]:
                    if "</think>" not in text:
                        continue
                    st["think"], text = False, text.split("</think>", 1)[1]
                if st["n"] == 0:
                    await out.put({"type": "timing", "llm_first_token": round(time.time() - t0, 3)})
                st["n"] += 1
                await out.put({"type": "text", "delta": text})
                st["buf"] += text
                done, st["buf"] = split_sentences(st["buf"], st["first"])
                for x in done:
                    st["first"] = False
                    await sentences.put(x)
        out_calls = [dict(v, id=v["id"] or f"call_{i}") for i, v in sorted(calls.items()) if v["name"]]
        return finish, out_calls

    async def tts():
        first, played_until, ttfa = True, 0.0, 0.5
        try:
            done = False
            while not done:
                text = await sentences.get()
                if text is None:
                    break
                # Every TTS request starts its own intonation, so sentence-by-sentence speech
                # wanders in tone. Only the first sentence goes alone (fast first audio); after
                # that, everything the LLM has written meanwhile is spoken as one piece.
                # Waiting for more text is fine while the listener still has buffered audio; the
                # next request starts while enough is left to cover its time to first audio and
                # its second audio block (slower while the LLM shares the GPU), so nothing stalls.
                margin = max(1.8, 2.5 * ttfa + 0.8)
                while not first and len(text) < 300:
                    slack = played_until - time.time() - margin
                    try:
                        nxt = (sentences.get_nowait() if not sentences.empty() or slack <= 0
                               else await asyncio.wait_for(sentences.get(), slack))
                    except (asyncio.QueueEmpty, asyncio.TimeoutError):
                        break
                    if nxt is None:
                        done = True
                        break
                    # a new line only before list items (clean_text strips their markers); plain
                    # sentences stay one paragraph, so the voice does not reset at each line
                    text += ("\n" if re.match(r"\s*(?:[-*+•]|\d+\.)\s", nxt) else " ") + nxt
                if "language" not in tts_body:  # one language for the whole answer
                    lang = guess_language(" ".join([messages[-1]["content"], text]))
                    if lang:
                        tts_body["language"] = lang
                req = dict(tts_body, input=text, stream=True, response_format="pcm")
                await out.put({"type": "tts_request", "chars": len(text)})  # for the stall details in the chat
                sent, got = time.time(), False
                async with c.stream("POST", tts_url, json=req, headers=api_headers()) as r:
                    if r.status_code != 200:
                        await out.put({"type": "error", "message": f"TTS HTTP {r.status_code}: "
                                       f"{(await r.aread()).decode(errors='replace')[:300]}"})
                        continue
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            ev = json.loads(line[5:])
                        except ValueError:
                            continue
                        if ev.get("type") == "speech.audio.delta" and ev.get("audio"):
                            if not got:
                                got, ttfa = True, time.time() - sent
                            if first:
                                first = False
                                played_until = time.time()
                                await out.put({"type": "timing", "first_audio": round(time.time() - t0, 3)})
                            # 16-bit mono PCM at 24 kHz: 48000 bytes per second of audio
                            played_until = max(played_until, time.time()) + len(ev["audio"]) * 3 / 4 / 48000
                            await out.put({"type": "audio", "audio": ev["audio"]})
                        elif ev.get("type") == "speech.audio.error":
                            await out.put({"type": "error", "message": f"TTS: {ev.get('error')}"})
        except Exception as e:
            await out.put({"type": "error", "message": f"TTS: {type(e).__name__}: {e}"})
        finally:
            await out.put(None)

    tasks = [asyncio.create_task(llm()), asyncio.create_task(tts())]

    async def events():
        try:
            while (ev := await out.get()) is not None:
                yield f"data: {json.dumps(ev)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'total': round(time.time() - t0, 3)})}\n\n"
        finally:  # also runs when the browser aborts (barge-in): stop LLM and TTS
            for t in tasks:
                t.cancel()
            await c.aclose()
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/watch/ask", dependencies=[Depends(assistant)])
async def watch_ask(request: Request):
    """Starts an answer for the Pebble app (device key in X-Speech-Device); fetch it with /api/watch/poll."""
    body = await request.json()
    text = str(body.get("text", "")).strip()[:2000]
    if not text:
        raise HTTPException(400, "text is required")
    history = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in body.get("history", [])[-10:]
               if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    inner = {"messages": history + [{"role": "user", "content": text}], "client": "watch"}
    if isinstance(body.get("tz"), str):
        inner["tz"] = body["tz"]
    data = json.dumps(inner).encode()

    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}
    watch.cleanup()
    job = watch.Job(speak=bool(body.get("speak", True)))
    response = await chat(Request(request.scope, receive))
    job.task = asyncio.create_task(watch.run(job, response))
    watch.JOBS[job.id] = job
    return {"id": job.id, "format": "ima-adpcm-8k"}


def _watch_job(job_id):
    job = watch.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown or expired answer")
    return job


@router.get("/api/watch/poll", dependencies=[Depends(assistant)])
async def watch_poll(id: str, t: int = 0, a: int = 0):
    return await watch.poll(_watch_job(id), max(0, t), max(0, a))


@router.delete("/api/watch/{job_id}", dependencies=[Depends(assistant)])
async def watch_cancel(job_id: str):
    job = watch.JOBS.pop(job_id, None)
    if job and job.task:
        job.task.cancel()
    return {"ok": True}
