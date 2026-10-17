"""Das kannst du auch sagen (plan plaene/funktionen-zeigen.md, Dominik 2026-10-16: „können wir vorschläge zurückgeben,
dass der User darauf kommt, er müsste malen sagen“, „1-10 umsetzen“).

"Funktionen vorschlagen" (tipps.py) points out functions that are still off. This module shows functions that are on
for the profile but never used, with a sentence the person can say as it stands:
  1  follow-up sentences under an answer (FOLLOW: after one tool, others that fit it, only tools never used);
  2  „Probier mal“ in an empty chat (start: three examples, other ones each week);
  3  „Meintest du …?“ (NEAR: words the Weiche does not know; never routed, only offered back as a sentence);
  4  „Was kannst du?“ answers with examples per area (AREAS, hilfe.answer_text and the row "kann");
  5  Ich → Was ich kann: the same list to look things up (GET /api/profile/saetze);
  6  „Neu bei dir“: a function the admin released lately and that needs nothing set up, once;
  7  spoken channels (speaker, phone, car, watch): at most one sentence a day at the end of an answer
     (Funktionen → „Tipps beim Sprechen“, each profile can switch it off under Ich → Gespräch);
  8  Telegram as reply keys (only sentences that change nothing), the terminal as a grey line and /tipps;
  9  the weekly hint of tipps.py names a sentence of the week when it has nothing else;
  10 Funktionen → Weiche „Was keiner findet“ (weiche._finden): released functions nobody used for 30 days, shown and
     tapped counts.

The panel decides, never the model: the sentences are fixed (werkzeug_abdeckung.SENTENCES is their one list, FOLLOW
and NEAR here), which ones come are fixed rules over what the panel knows (features.allowed, the tools this turn
called, what the profile used before). A tap only puts the sentence into the field (in Telegram it sends it like a
typed message), so the person's own sending goes through the Weiche and every rule as always. Counted are the tools'
names and numbers, never a word of a question. Off by default (chat.feature_sentences under „Funktionen vorschlagen“),
never for guests, never after outside text, under the Notaus or over MCP.
"""
import hashlib
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import notaus
import onboard
import profiles
import tipps
import werkzeug_abdeckung as wa
from core import assistant, browser_profile

KEY = "tippssaetze"
VOICE_KEY = "tippsstimme"
FRESH = 14 * 86400        # one tool's sentence comes again at the earliest after this
DAY_MAX = 6               # rows under answers per profile and day
VOICE_GAP = 86400         # a spoken sentence at most once a day
UNUSED_DAYS = 30          # Funktionen → Weiche „Was keiner findet“
MAX_ROW = 3
MAX_START = 3
MAX_NEAR_TEXT = 200
KEEP_USED = 120 * 86400   # what a profile used is forgotten after this
SPOKEN = {"speaker", "telefon", "watch", "siri", "car"}
SCREEN = {"panel", "iphone", "android", "tui"}
router = APIRouter()

# the areas of „Was kannst du?“ and Ich → Was ich kann; every tool of SENTENCES in exactly one (test_saetze)
AREAS = (
    ("alltag", "Alltag", "Everyday", ("reminder_set", "reminder_list", "reminder_cancel", "anruf_planen", "weather",
                                      "transit", "tasks_show", "tasks_add", "tasks_change", "parcels", "feeds_news")),
    ("termine", "Kalender und Mail", "Calendar and mail", ("daily_briefing", "calendar_events", "calendar_add",
                                                           "calendar_change", "mail_list", "mail_read",
                                                           "mail_tidy_overview", "contacts_search")),
    ("nachrichten", "Nachrichten", "Messages", ("message_send", "message_read", "message_announce", "iphone_action")),
    ("zuhause", "Zuhause", "Home", ("home_assistant", "home_assistant_states", "home_assistant_history",
                                    "camera_describe")),
    ("wissen", "Wissen und Suche", "Knowledge and search", ("web_search", "wikipedia", "archive_search",
                                                            "document_search", "document_list", "history_search")),
    ("machen", "Bilder, Musik und Dokumente", "Pictures, music and documents", ("bild_malen", "musik_machen", "document_plan")),
    ("gedaechtnis", "Gedächtnis", "Memory", ("memory_save", "memory_forget", "spark_tagebuch")),
    ("auftraege", "Aufträge", "Jobs", ("agent_list", "agent_schedule", "agent_watch", "agent_change")),
    ("spark", "Spark", "Spark", ("spark_hilfe", "spark_vorschlag", "spark_zustand")),
)
AREA_OF = {t: a for a, _, _, ts in AREAS for t in ts}

# after a tool (left), others that fit it, each with its own sentence for that moment (it must reach the tool's
# Weiche group, test_saetze); only tools the profile never used come (plan 1a)
FOLLOW = {
    "weather": (("reminder_set", "Erinnere mich morgen früh an den Schirm", "Remind me about the umbrella tomorrow morning"),
                ("anruf_planen", "Ruf mich morgen um sieben an", "Call me tomorrow at seven"),
                ("daily_briefing", "Was hab ich morgen vor?", "What am I up to tomorrow?")),
    "calendar_events": (("anruf_planen", "Ruf mich zehn Minuten vorher an", "Call me ten minutes before"),
                        ("reminder_set", "Erinnere mich eine Stunde vorher daran", "Remind me an hour before"),
                        ("transit", "Wann fährt die nächste S-Bahn?", "When does the next S-Bahn leave?"),
                        ("weather", "Wie wird das Wetter morgen?", "What will the weather be like tomorrow?")),
    "mail_list": (("mail_draft", "Schreib Anna eine Antwort auf ihre Mail", "Write Anna a reply to her mail"),
                  ("parcels", "Wann kommt mein Paket?", "When does my parcel arrive?"),
                  ("mail_tidy_overview", "Räum mein Postfach auf", "Tidy up my inbox")),
    "web_search": (("document_plan", "Mach mir dazu eine Präsentation", "Make me a presentation about it"),
                   ("bild_malen", "Mal mir ein Bild dazu", "Paint me a picture of it"),
                   ("memory_save", "Merk dir das", "Remember that")),
    "document_search": (("document_plan", "Mach daraus eine Präsentation", "Make a presentation out of it"),
                        ("reminder_set", "Erinnere mich eine Woche vorher daran", "Remind me a week before")),
    "reminder_set": (("anruf_planen", "Ruf mich morgen um sieben an", "Call me tomorrow at seven"),
                     ("tasks_add", "Setz das auf die Einkaufsliste", "Put that on the shopping list")),
    "tasks_show": (("reminder_set", "Erinnere mich heute Abend an den Einkauf", "Remind me about the shopping tonight"),),
    "home_assistant": (("home_assistant_states", "Ist die Haustür zu?", "Is the front door closed?"),
                       ("camera_describe", "Was sieht die Kamera an der Haustür?", "What does the camera at the front door see?"),
                       ("home_assistant_history", "Wann ist die Waschmaschine fertig?", "When is the washing machine done?")),
    "bild_malen": (("document_plan", "Mach mir dazu eine Präsentation", "Make me a presentation about it"),),
    "contacts_search": (("message_send", "Schick Anna eine Nachricht, dass ich später komme", "Send Anna a message that I will be late"),),
    "message_read": (("message_announce", "Durchsage im Wohnzimmer: Essen ist fertig", "Announcement in the living room: dinner is ready"),),
    "transit": (("reminder_set", "Erinnere mich zehn Minuten vorher an die Bahn", "Remind me about the train ten minutes before"),),
    "memory_save": (("history_search", "Haben wir schon mal darüber gesprochen?", "Did we talk about this before?"),),
}
# the same follow-ups for the tools of the same kind
for _a, _b in (("daily_briefing", "calendar_events"), ("calendar_add", "calendar_events"), ("mail_read", "mail_list"),
               ("mail_search", "mail_list"), ("wikipedia", "web_search"), ("archive_search", "web_search"),
               ("document_list", "document_search"), ("reminder_list", "reminder_set"), ("tasks_add", "tasks_show"),
               ("home_assistant_states", "home_assistant"), ("home_assistant_action", "home_assistant"),
               ("message_send", "message_read")):
    FOLLOW[_a] = FOLLOW[_b]

# „Meintest du …?“: words the Weiche does not take (test_saetze checks they really do not reach the tool, and the
# sentence offered back does). The person's own short message is turned into the sentence the Weiche knows; nothing
# runs by itself. (pattern on the message, tool, how the sentence is written from the pattern's groups)
NEAR = (
    (re.compile(r"(?i)^\s*klingel?e?\s+mich\s+(.{1,60}?)\s+an\s*[.!]?\s*$"), "anruf_planen",
     lambda m: ("Ruf mich " + m.group(1) + " an", "Call me " + m.group(1))),
    (re.compile(r"(?i)^\s*denke?\s+(.{1,40}?)\s+an\s+(.{1,60}?)\s*[.!]?\s*$"), "reminder_set",
     lambda m: ("Erinnere mich " + m.group(1) + " an " + m.group(2), "Remind me " + m.group(1) + " about " + m.group(2))),
    (re.compile(r"(?i)^\s*notiere?\s+(.{1,60}?)\s+(?:für den einkauf|zum einkaufen|für den einkaufszettel)\s*[.!]?\s*$"),
     "tasks_add", lambda m: ("Setz " + m.group(1) + " auf die Einkaufsliste", "Put " + m.group(1) + " on the shopping list")),
    (re.compile(r"(?i)^\s*(?:bau|mach|schreib|erstell)e?\s+(?:mir\s+)?einen\s+vortrag\s+(über|zu[mr]?)\s+(.{1,80}?)\s*[.!]?\s*$"),
     "document_plan", lambda m: ("Mach eine Präsentation " + m.group(1) + " " + m.group(2),
                                 "Make a presentation about " + m.group(2))),
)

# a tool only some channels can use
ONLY = {"iphone_action": {"iphone"}}
# what a spoken channel can do without a screen (plan 7)
VOICE = {"reminder_set", "reminder_list", "anruf_planen", "weather", "transit", "tasks_show", "tasks_add", "parcels", "feeds_news",
         "daily_briefing", "calendar_events", "calendar_add", "mail_list", "mail_read", "contacts_search",
         "message_send", "message_read", "message_announce", "home_assistant", "home_assistant_states",
         "home_assistant_history", "web_search", "wikipedia", "document_search", "history_search", "memory_save",
         "spark_tagebuch", "spark_zustand", "agent_list"}
# the first example in an empty chat until the profile asked the Spark about itself (start, Grundausstattung)
HELP_START = ("Wo stelle ich die Stimme ein?", "Where do I set the voice?")
# never as a first example in an empty chat: they need something from before (plan 2)
NOT_START = {"reminder_cancel", "tasks_change", "memory_forget", "calendar_change", "agent_change", "spark_vorschlag",
             "spark_hilfe", "iphone_action"}
# set up by the profile itself: the tool works only once it is connected (tipps.py's own checks)
READY = {"calendar_events": "cal", "calendar_add": "cal", "calendar_change": "cal", "daily_briefing": "cal",
         "mail_list": "mail", "mail_read": "mail", "mail_search": "mail", "mail_draft": "mail", "mail_tidy_overview": "mail"}

# tool -> the functions offering it (werkzeug_abdeckung.TOOLS is the one list)
KEYS_OF = {}
for _k, _ts in wa.TOOLS.items():
    for _t in _ts:
        KEYS_OF.setdefault(_t, []).append(_k)


def text_of(tool):
    """The tool's example (de, en): its own sentence, else the first follow-up sentence that names it."""
    if tool in wa.SENTENCES:
        return wa.SENTENCES[tool]
    for rows in FOLLOW.values():
        for t, de, en in rows:
            if t == tool:
                return de, en
    return None


def _ready(uid, tool):
    need = READY.get(tool)
    if need == "cal":
        return tipps._has_calendar(uid)
    if need == "mail":
        return tipps._has_mail(uid)
    return True


def usable(uid, tool, c=None, org="panel"):
    """The profile can use the tool here and now: one of its functions is allowed, set up, and the channel has it."""
    if tool in ONLY and org not in ONLY[tool]:
        return False
    keys = KEYS_OF.get(tool) or ()
    for k in keys:
        if not features.allowed(k, uid, c):
            continue
        own = onboard.own_setup(k, c)
        if own and not onboard.done(own[0], uid):
            continue
        return _ready(uid, tool)
    return False


def channel(turn):
    """Where the answer goes, from what the panel itself knows (hilfe.origin, the terminal's key, the car flag)."""
    body = getattr(turn, "body", None)
    body = body if isinstance(body, dict) else {}
    if body.get("client") == "tui":
        return "tui"
    org = getattr(turn, "hilfe_origin", "panel") or "panel"
    if org == "iphone" and body.get("car") is True:
        return "car"
    return org


# ---------------------------------------------------------------- per profile, kept in tipps.json
def _used(st):
    return st["used"]


def record(uid, tools, now=None):
    """The tools this answer called (names only): a used tool is never suggested to this profile (plan 1a)."""
    now = int(now or time.time())
    names = [t for t in dict.fromkeys(tools) if t in KEYS_OF][:8]
    if not names or not features.allowed(KEY, uid):
        return

    def put(st):
        u = st["used"]
        for t in names:
            u[t] = now
        for t in [t for t, v in u.items() if not isinstance(v, (int, float)) or now - v > KEEP_USED]:
            u.pop(t, None)
    tipps._mut(uid, put)


def tapped(uid, tool):
    """The person sent a suggested sentence (the page says which tool it was): counted per tool, nothing else."""
    if not isinstance(tool, str) or tool not in KEYS_OF or not features.allowed(KEY, uid):
        return False

    def put(st):
        z = st["zahl"].setdefault("tap", {})
        z[tool] = min(99999, int(z.get(tool, 0)) + 1)
    tipps._mut(uid, put)
    _event("tap")
    print(f"tipps: Beispielsatz getippt {tool}", flush=True)
    return True


def _fresh(st, tool, now):
    t = st["said"].get(tool)
    return not (isinstance(t, (int, float)) and now - t < FRESH)


def _day_rows(st, now):
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    return int(st["zahl"].get("tag", {}).get(day, 0))


def _shown(uid, tools, now, voice=False):
    def put(st):
        for t in tools:
            st["said"][t] = int(now)
        z = st["zahl"].setdefault("shown", {})
        for t in tools:
            z[t] = min(99999, int(z.get(t, 0)) + 1)
        if voice:
            st["voice"] = int(now)
        else:
            day = time.strftime("%Y-%m-%d", time.localtime(now))
            st["zahl"]["tag"] = {day: _day_rows(st, now) + 1}
        st["said"] = {k: v for k, v in st["said"].items() if isinstance(v, (int, float)) and now - v < FRESH}
    tipps._mut(uid, put)


def _item(tool, de, en, kind="follow"):
    return {"tool": tool, "text": [de, en], "name": _fname(tool), "kind": kind}


def _fname(tool):
    keys = KEYS_OF.get(tool) or ()
    f = features.BY_KEY.get(keys[0]) if keys else None
    return [f.de, f.en] if f else ["", ""]


# ---------------------------------------------------------------- the row under an answer (plan 1, 3, 4, 6)
def _new_items(uid, st, c, now, org):
    """Plan 6: released lately (tipps.NEW_DAYS), nothing to set up, never used: its sentence once."""
    try:
        seen = features._seen(c)
    except Exception:
        return []
    since = st.get("since") or now
    out = []
    for f in features.FEATURES:
        t0 = seen.get(f.key, 0)
        if not (since < t0 and now - t0 < tipps.NEW_DAYS * 86400) or onboard.own_setup(f.key, c):
            continue
        for tool in wa.TOOLS.get(f.key, ()):
            x = text_of(tool)
            if x and tool not in st["used"] and _fresh(st, tool, now) and usable(uid, tool, c, org):
                out.append(dict(_item(tool, *x, kind="new"), name=[f.de, f.en]))
                break
    return out[:1]


def _follow_items(uid, st, called, c, now, org):
    out = []
    for tool in called:
        for t, de, en in FOLLOW.get(tool, ()):
            if t in called or t in st["used"] or not _fresh(st, t, now) or any(x["tool"] == t for x in out):
                continue
            if usable(uid, t, c, org):
                out.append(_item(t, de, en))
    return out[:MAX_ROW]


def near(text, called=()):
    """Plan 3: the person's short message in words the Weiche does not know -> (tool, (de, en)) or None."""
    text = str(text or "")
    if not text or len(text) > MAX_NEAR_TEXT or "\n" in text:
        return None
    for rx, tool, write in NEAR:
        m = rx.match(text)
        if m and tool not in called:
            de, en = write(m)
            return tool, (de[:200], en[:200])
    return None


def kann(uid, c=None, org="panel", lang_li=None):
    """Plan 4 and 5: per area the tools this profile can use here, each with its example; unused and new marked."""
    c = features.chat_cfg() if c is None else c
    st = tipps._st(uid)
    try:
        seen = features._seen(c)
    except Exception:
        seen = {}
    now = time.time()
    out = []
    for aid, de, en, tools in AREAS:
        items = []
        for tool in tools:
            x = text_of(tool)
            if not x or not usable(uid, tool, c, org):
                continue
            keys = KEYS_OF.get(tool) or ()
            new = any(now - seen.get(k, 0) < tipps.NEW_DAYS * 86400 for k in keys)
            items.append(dict(_item(tool, *x, kind="kann"), used=tool in st["used"], new=new))
        if items:
            out.append({"id": aid, "name": [de, en], "items": items})
    return out


def row(turn, calls, outside=False, now=None):
    """The one row under this answer, or None (Panel, apps, Telegram, terminal; never spoken channels)."""
    who = getattr(turn, "who", None)
    uid = who and who.get("id")
    if not uid or not getattr(turn, "own_browser", False) or not features.allowed(KEY, uid):
        return None
    org = channel(turn)
    if org not in SCREEN and org != "telegram":
        return None
    msgs = getattr(turn, "messages", None) or []
    if not msgs or msgs[-1].get("role") != "user" or outside or getattr(turn, "carry", None) \
            or getattr(turn, "pics", None) or notaus.refuse("aktion", uid):
        return None
    now = now or time.time()
    called = [str(x.get("name") or "").removesuffix(" (Panel)") for x in calls or () if isinstance(x, dict)]
    called = [t for t in called if t in KEYS_OF]
    record(uid, called, now)
    c = getattr(turn, "ccfg", None) or features.chat_cfg()
    st = tipps._st(uid)
    ask_text = str(getattr(turn, "ask_text", "") or "")
    route = getattr(turn, "route", None)
    kind, items = None, []
    import hilfe
    if route is not None and route.names == ["spark"] and hilfe.CAN_ASK.search(ask_text):
        kind, items = "kann", [x for a in kann(uid, c, org) for x in a["items"]][:12]
    if not items:
        hit = near(ask_text, called)
        if hit and usable(uid, hit[0], c, org):
            kind, items = "near", [_item(hit[0], *hit[1], kind="near")]
    if not items and _day_rows(st, now) < DAY_MAX:
        items = _new_items(uid, st, c, now, org)
        kind = "new" if items else None
        if not items:
            items = _follow_items(uid, st, called, c, now, org)
            kind = "follow" if items else None
    if org == "telegram":   # a tap sends it at once there: only sentences that change nothing (taten.KIND)
        import taten
        items = [x for x in items if x["tool"] not in taten.KIND]
    if not items:
        return None
    if kind in ("new", "follow"):
        _shown(uid, [x["tool"] for x in items], now)
    _event(kind)
    print(f"tipps: Beispielsätze {kind} {len(items)}", flush=True)
    return {"type": "more", "kind": kind, "items": items}


# ---------------------------------------------------------------- spoken channels (plan 7)
def spoken(turn, calls, en=False, now=None):
    """One sentence at the end of a spoken answer, at most once a day, or ""."""
    who = getattr(turn, "who", None)
    uid = who and who.get("id")
    if not uid or not getattr(turn, "own_browser", False) or channel(turn) not in SPOKEN:
        return ""
    if not features.allowed(VOICE_KEY, uid) or getattr(turn, "carry", None) or notaus.refuse("aktion", uid):
        return ""
    now = now or time.time()
    st = tipps._st(uid)
    if now - (st.get("voice") or 0) < VOICE_GAP:
        return ""
    called = [str(x.get("name") or "").removesuffix(" (Panel)") for x in calls or () if isinstance(x, dict)]
    called = [t for t in called if t in KEYS_OF]
    org = channel(turn)
    c = getattr(turn, "ccfg", None) or features.chat_cfg()
    items = [x for x in _follow_items(uid, st, called, c, now, org) if x["tool"] in VOICE][:1]
    if not items:
        return ""
    _shown(uid, [items[0]["tool"]], now, voice=True)
    _event("voice")
    print(f"tipps: Beispielsatz gesprochen {items[0]['tool']}", flush=True)
    s = items[0]["text"][1 if en else 0]
    return f"By the way: you can also say „{s}“." if en else f"Übrigens: du kannst auch sagen „{s}“."


# ---------------------------------------------------------------- an empty chat (plan 2) and the week (plan 9)
def start(uid, org="panel", now=None, n=MAX_START):
    """Three examples of tools this profile can use and never used; other ones each week (by the profile's id and
    the week's number, no randomness)."""
    if not features.allowed(KEY, uid) or notaus.refuse("aktion", uid):
        return []
    now = now or time.time()
    st = tipps._st(uid)
    c = features.chat_cfg()
    pool = [t for t in wa.SENTENCES if t not in NOT_START and t not in st["used"] and usable(uid, t, c, org)]
    week = int(now // (7 * 86400))
    pool.sort(key=lambda t: hashlib.sha256(f"{uid}|{week}|{t}".encode()).hexdigest())
    items = [_item(t, *wa.SENTENCES[t], kind="start") for t in pool[:n]]
    # Grundausstattung (Dominik 2026-10-17): until the profile has asked the Spark about itself once, the first
    # example says where the settings are found (only with more than one example: never the sentence of the week)
    if n > 1 and "spark_hilfe" not in st["used"] and usable(uid, "spark_hilfe", c, org):
        items = [_item("spark_hilfe", *HELP_START, kind="start")] + items[:n - 1]
    return items


def week_text(uid, now=None):
    """Plan 9: the sentence of the week for tipps.weekly_text, or ""."""
    items = start(uid, "panel", now, 1)
    if not items:
        return ""
    x = items[0]
    return f"Satz der Woche: Sag mal „{x['text'][0]}“ ({x['name'][0]}). Mehr unter Ich → Was ich kann."


# ---------------------------------------------------------------- Funktionen → Weiche „Was keiner findet“ (plan 10)
def admin_view(now=None):
    """Numbers only: functions released on the Spark whose tools nobody used for UNUSED_DAYS, and per tool how often
    a sentence was shown and tapped."""
    c = features.chat_cfg()
    if not features.admin_on(KEY, c):
        return {"on": False}
    now = now or time.time()
    used, shown, tap = {}, {}, {}
    for uid, st in tipps._all().items():
        if not isinstance(st, dict):
            continue
        for t, v in (st.get("used") or {}).items():
            if isinstance(v, (int, float)) and now - v < UNUSED_DAYS * 86400:
                used[t] = used.get(t, 0) + 1
        z = st.get("zahl") if isinstance(st.get("zahl"), dict) else {}
        for src, dst in ((z.get("shown"), shown), (z.get("tap"), tap)):
            for t, n in (src if isinstance(src, dict) else {}).items():
                if t in KEYS_OF and isinstance(n, int):
                    dst[t] = dst.get(t, 0) + n
    unused = []
    for f in features.FEATURES:
        tools = [t for t in wa.TOOLS.get(f.key, ()) if text_of(t)]
        if tools and features.admin_on(f.key, c) and not any(used.get(t) for t in tools):
            unused.append({"key": f.key, "name": [f.de, f.en]})
    rows = [{"tool": t, "name": _fname(t), "shown": shown.get(t, 0), "tap": tap.get(t, 0)}
            for t in sorted(set(shown) | set(tap), key=lambda t: (-tap.get(t, 0), -shown.get(t, 0)))][:20]
    return {"on": True, "days": UNUSED_DAYS, "unused": unused[:30], "rows": rows,
            "shown": sum(shown.values()), "tap": sum(tap.values())}


def _event(what):
    try:
        import live
        live.event("Funktionen vorschlagen", {"follow": "Beispielsätze unter der Antwort", "near": "Meintest du",
                                              "new": "Neu bei dir", "kann": "Was ich kann", "voice": "Beispielsatz gesprochen",
                                              "tap": "Beispielsatz getippt", "start": "Probier mal"}.get(what, what))
    except Exception:
        pass


# ---------------------------------------------------------------- own data (Ich → Was ich kann „Meine Zählung löschen“)
def count(uid):
    st = tipps._st(uid)
    return len(st["used"]) + len(st["said"])


def clear(uid):
    def put(st):
        st["used"], st["said"], st["zahl"] = {}, {}, {}
        st.pop("voice", None)
    tipps._mut(uid, put)
    print("tipps: Beispielsätze gelöscht", flush=True)


features.OWN[KEY] = (count, clear)


@router.get("/api/profile/saetze", dependencies=[Depends(assistant)])
def api_list(request: Request, nur: str = "", prof=Depends(browser_profile)):
    """Ich → Was ich kann (and the terminal's /tipps); ?nur=start only „Probier mal“ for an empty chat."""
    uid = prof["id"]
    guard.limit(request, "tipps", uid)
    if not features.allowed(KEY, uid):
        return {"on": False, "areas": [], "start": []}
    org = "tui" if profiles.key_scope(request) == "tui" else "panel"
    if nur == "start":
        items = start(uid, org)
        if items:
            _event("start")
        return {"on": True, "areas": [], "start": items}
    return {"on": True, "areas": kann(uid, None, org), "start": start(uid, org), "count": count(uid)}


@router.delete("/api/profile/saetze", dependencies=[Depends(assistant)])
def api_clear(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    guard.limit(request, "tipps", uid)
    if not features.allowed(KEY, uid):
        raise HTTPException(403, "Beispielsätze sind aus")
    clear(uid)
    return {"ok": True}

