"""Funktionen → Weiche (plan weiche-sichtbar.md): the switch of intent.py, shown and set up in the panel.

The rules stay fixed code (intent.py); the admin sees every group with its words and tools, tries a sentence and
sees its whole way (question, checks first, group, tools, locks, result), and adds to the rules only in ways that
can never give more than the rights do:

    chat.route_words   own words per group ("smarthome: sauna, kamin"; intent.py, since V01.0.203)
    chat.route_not     „Nicht bei“: a word that takes a group out again ("smarthome: brief")
    chat.route_extra   tools a group keeps as well ("smarthome: weather"), only those the turn offers anyway
    chat.route_off     groups that are recognized but do not narrow (they get every tool, as without the switch)
    chat.route_tests   own test sentences [{"q": "Mach die Sauna an", "want": "smarthome"}] beside intent_bench.BENCH
    chat.tool_words    words that make a tool a must („Werkzeugpflicht“) and find its group (moved here from
                       Einstellungen → Sprachmodell, plan weiche-intelligenter step 0: one place for the Weiche's words)
    chat.route_model   what a question no rule recognizes gets (moved here from Funktionen → Gezielte Werkzeugwahl)
    chat.systemone_min from which probability the classification narrows (moved here from Funktionen → Einordnung
                       mit Wahrscheinlichkeit; the switch itself stays there)

The everyday check (intent_alltag.py) shows how well the rules do on sentences nobody tuned them for („Alltagsquote“).

Every change is checked against all test sentences first; one that would turn out different stops the save until
the admin confirms it. The last versions are kept for „Rückgängig“ (STATE/weiche-history.json). The protection
rules (locks after mail or outside text, Notaus, at most two lookups) are shown, never switched here.

Counting (Statistik, Live): per day and group only how many questions, tools and direct reads, never a word of the
question (STATE/weiche-stats.json, 8 days). Admin only, like the rest of the page.
"""
import asyncio
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import chat
import guard
import intent
import werkzeuge
from common import STATE, load_config, write_json
import core
from core import auth

router = APIRouter()
KEYS = ("route_words", "route_not", "route_extra", "route_off", "route_tests", "tool_words", "route_model", "systemone_min")
MODELS = ("off", "on", "lean", "systemone")
MAX_TESTS = 200
MAX_Q = 200
MAX_BODY = 40000
KEEP_VERSIONS = 20
KEEP_DAYS = 8
FLUSH_S = 60
WANT = re.compile(r"[a-z]{3,12}(\+[a-z]{3,12})?")
WORD = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]{3,39}")
# words that never make a group (asked in every kind of question)
STOP = set("""aber alle allem allen aller alles also auch auf aus bei beim bist bitte dann dass dein deine dem den der
des dich dies diese diesem diesen dieser dieses doch dort durch eine einem einen einer eines etwas euch habe haben
hast hat hatte heute hier ihre immer jetzt kann kannst kein keine mach mache machen mal man mehr mein meine meinem
meinen meiner mich mir mit morgen muss nach nicht noch nur oder ohne schon sehr sein seine sich sie sind soll sollen
über und uns unser unter viel vom von war was weil welche welcher welches wenn wer werden wie wieder wird wir wo wohl
zum zur zwischen schau sag sage zeig zeige gibt gib bin ich du er es ist ein einer""".split())

# the tools of the switch, readable (de, en): one table for every page (werkzeuge.py)
TOOLS = werkzeuge.NAMES
# the fixed rules between groups (intent.classify), said per group
VORRANG = {
    "smarthome": ("Wetter, Liste, Nachricht und „Dokument erstellen“ gehen vor, wenn kein Schaltbefehl dabei ist. "
                  "Ein Schaltwort allein („an“, „aus“) zählt nur, wenn sonst nichts erkannt wird.",
                  "Weather, list, message and “create document” come first when there is no switching command. A "
                  "switching word alone (“on”, “off”) only counts when nothing else is recognized."),
    "nachricht": ("„Habe ich neue Nachrichten?“ ist eine Nachricht für dich, „Was gibt es in den Nachrichten?“ "
                  "die Websuche. „Schreib Anna, dass …“ zählt auch ohne das Wort.",
                  "“Do I have new messages?” is a message for you, “What is in the news?” the web search. “Write "
                  "Anna that …” counts without the word."),
    "websuche": ("Nachrichten für dich gehen vor („Habe ich neue Nachrichten?“).",
                 "Messages for you come first (“Do I have new messages?”)."),
    "paket": ("Geht vor E-Mail: Paketfragen werden aus Mails gelesen, sind aber Paketfragen.",
              "Comes before mail: parcel questions are read from mails but are about parcels."),
    "mail": ("Pakete gehen vor („Wo ist mein Paket?“).", "Parcels come first (“Where is my parcel?”)."),
    "spark": ("Wird vor allen anderen Gruppen geprüft: „Wie verbinde ich Home Assistant?“ ist eine Frage zum Spark.",
              "Checked before every other group: “How do I connect Home Assistant?” is about the Spark."),
    "plaudern": ("Reines Plaudern bekommt keine Werkzeuge.", "Small talk gets no tools."),
}
# the protection rules: shown on the page, never switched there (chat_turn.locked, notaus, chat_tools)
LOCKS = (   # (key, sentence de, sentence en, short de, short en)
    ("mail", "Nach dem Lesen einer Mail: nichts schalten, nichts merken, nicht im Web suchen.",
     "After reading a mail: nothing switched, nothing remembered, no web search.", "nach Mail", "after mail"),
    ("outside", "Nach Text von außen (Web, Kalender, Dokument, Bild): nichts schalten und nichts merken.",
     "After outside text (web, calendar, document, picture): nothing switched, nothing remembered.",
     "nach Text von außen", "after outside text"),
    ("lookups", "Höchstens 2 Nachschlagen pro Frage (Archiv, Wiki, Dokumente, Verlauf, Kontakte, Mails).",
     "At most 2 lookups per question (archive, wiki, documents, history, contacts, mails).", "höchstens 2× nachschlagen",
     "at most 2 lookups"),
    ("notaus", "Notaus hält Werkzeuge zurück, je nach Stufe.", "The emergency stop holds tools back, by stage.", "Notaus",
     "emergency stop"),
)
_lock = threading.Lock()
_stats = {"days": None, "dirty": False, "flushed": 0.0}


# ---------------------------------------------------------------- checking the admin's rules
def parse_tests(value):
    """chat.route_tests -> [{"q", "want"}], or ValueError with a readable reason."""
    if not isinstance(value, list) or len(value) > MAX_TESTS:
        raise ValueError(f"Testsätze: eine Liste mit höchstens {MAX_TESTS}")
    out, seen = [], set()
    for x in value:
        if not isinstance(x, dict) or set(x) - {"q", "want"}:
            raise ValueError("Testsatz: Satz und erwartete Gruppe")
        q, want = x.get("q"), x.get("want", "")
        if not isinstance(q, str) or not q.strip() or len(q) > MAX_Q or not q.isprintable():
            raise ValueError(f"Testsatz: 1 bis {MAX_Q} Zeichen, eine Zeile")
        if not isinstance(want, str) or (want and (not WANT.fullmatch(want)
                                                    or any(n not in intent.GROUPS for n in want.split("+")))):
            raise ValueError(f"„{q[:40]}“: erwartet wird eine Gruppe oder „unklar“")
        if q.strip().lower() in seen:
            continue
        seen.add(q.strip().lower())
        out.append({"q": q.strip(), "want": want})
    return out


def check(ch):
    """Raises ValueError when one of the Weiche's own settings is not valid (admin.validate: save and restore)."""
    try:
        intent.parse_route_words(ch.get("route_not", ""))
    except ValueError as e:
        raise ValueError(f"„Nicht bei“: {e}")
    try:
        intent.parse_route_extra(ch.get("route_extra", ""))
    except ValueError as e:
        raise ValueError(f"zusätzliche Werkzeuge: {e}")
    try:
        intent.parse_route_off(ch.get("route_off", []))
    except ValueError as e:
        raise ValueError(f"Gruppen ohne Eingrenzen: {e}")
    parse_tests(ch.get("route_tests", []))
    try:
        chat.parse_tool_words(ch.get("tool_words", ""))
    except ValueError as e:
        raise ValueError(f"Pflicht-Wörter: {e}")
    if ch.get("route_model", "off") not in MODELS:
        raise ValueError("Fragen, die keine Regel erkennt: " + ", ".join(MODELS))
    import systemone
    v = ch.get("systemone_min", systemone.ROUTE_MIN)
    if isinstance(v, bool) or v not in systemone.ROUTE_STEPS:
        raise ValueError("Schwelle: " + ", ".join(str(x) for x in systemone.ROUTE_STEPS))


def rules_of(ch):
    import systemone
    default = {"route_off": [], "route_tests": [], "route_model": "off", "systemone_min": systemone.ROUTE_MIN}
    return {k: ch.get(k, default.get(k, "")) for k in KEYS}


# ---------------------------------------------------------------- test sentences
def _ok(names, want):
    return set(names) == (set(want.split("+")) if want else set())


def run_tests(ch):
    """Every test sentence (built in, then the admin's own) through the switch with these rules."""
    import intent_bench
    out = []
    for own, rows in ((False, intent_bench.BENCH), (True, [(x["q"], x["want"]) for x in parse_tests_safe(ch)])):
        for q, want in rows:
            r = intent.classify_cfg(q, ch)
            out.append({"q": q, "want": want, "got": "+".join(r.names), "ok": _ok(r.names, want), "own": own})
    return out


def parse_tests_safe(ch):
    try:
        return parse_tests(ch.get("route_tests", []))
    except ValueError:
        return []


def flips(old_ch, new_ch):
    """The sentences that the new rules turn out different from before (a test that held and now fails, or a
    group that changes)."""
    before = {(x["q"], x["own"]): x for x in run_tests(old_ch)}
    out = []
    for x in run_tests(new_ch):
        b = before.get((x["q"], x["own"]))
        if (b and b["ok"] and not x["ok"]) or (not b and not x["ok"]):
            out.append(x)
    return out


# ---------------------------------------------------------------- one sentence, its whole way
def _source(name, text, ch):
    if name == "spark":
        return "hilfe"
    if name == "nachricht" and not intent.MESSAGE_WORDS.search(text):
        return "senden"
    mine = intent.own_route_words(ch.get("route_words", ""))
    if name in mine and mine[name].search(text):
        return "eigen"
    return "eingebaut"


def trace(text, ch, today=None, english=False, before=""):
    """The way of one sentence through the switch, by the same functions a turn uses (no model, nothing stored).
    `today`: the local date for "morgen" (passed in, the rule never reads the clock itself); `before`: the person's
    own question just before, for a follow-up („Und morgen?“)."""
    import ack
    text = str(text or "")[:500]
    try:
        import hilfe
        spark = bool(hilfe.help_question(text))
    except Exception:
        spark = False
    try:
        import messages as inbox
        send = bool(inbox.SEND_ASK.search(text))
    except Exception:
        send = False
    small = bool(chat.SMALLTALK.fullmatch(text))
    route = intent.classify_cfg(text, ch)
    follow = intent.follow_up(text, str(before or "")[:500], ch) if before and not route.names else None
    if follow:
        route = follow
    without = intent.classify(text, ch.get("tool_words", ""), ch.get("route_words", ""))
    removed = [n for n in without.names if n not in route.names and not follow]
    hinted = intent.hint_tools(route)
    off = ch.get("route_off") if isinstance(ch.get("route_off"), list) else []
    extra = intent.own_route_extra(ch.get("route_extra", ""))
    model = ch.get("route_model", "off")
    if route.clear and not any(n in off for n in route.names):
        group = set().union(*(intent.GROUPS[n][0] for n in route.names))
        add = {t for n in route.names for t in extra.get(n, ())} - group
        tools = [{"name": t, "kind": "gruppe"} for t in sorted(group)] \
            + [{"name": t, "kind": "zusatz"} for t in sorted(add)] \
            + [{"name": t, "kind": "immer"} for t in sorted(intent.NARROW_KEEP - group - add)]
        narrowed = "gruppe"
    elif route.clear:
        tools, narrowed = [], "aus"
    elif route.names == ["plaudern"]:
        tools, narrowed = [], "plaudern"
    elif not route.names and model == "lean":
        tools, narrowed = [{"name": t, "kind": "knapp"} for t in sorted(intent.LEAN)] \
            + [{"name": t, "kind": "hinweis"} for t in sorted(hinted - intent.LEAN)], "knapp"
    else:
        tools, narrowed = [], ("modell" if not route.names and model in ("on", "systemone") else "alle")
    names = {t["name"] for t in tools}
    need = chat.needed(text, names, ch.get("tool_words", "")) if names else []
    force = intent.forced(route, need, names) if names else None
    direct = intent.direct(text, names) if names else None
    args = intent.direct_args(text, today) if direct in ("weather", "calendar_events") and today else {}
    group = ack.group_of(route.names, direct)
    sentence = ack.phrase(group, None, english, bump=False) if group else None
    try:
        import notaus
        held = notaus.level()
    except Exception:
        held = 0
    return {
        "text": text,
        "refers": intent.refers_back(text),
        "checks": {"plaudern": small, "spark": spark, "senden": send},
        "names": route.names, "label": route.label(), "clear": route.clear,
        "mixed": len(route.names) > intent.MAX_MIXED,
        "why": [{"group": n, "word": w, "source": "folge" if follow else _source(n, text, ch)} for n, w in route.why.items()],
        "hints": [{"group": n, "word": w} for n, w in route.hints.items()], "follow": bool(follow),
        "removed": removed, "narrow": narrowed, "model": model, "tools": tools,
        "need": need, "force": force, "direct": direct, "date": args.get("date"),
        "ack": sentence, "notaus": held,
    }


# ---------------------------------------------------------------- suggestions from a wrong turn
def suggest(text, want, ch):
    """Words of the sentence that could be the group's own words: whole words of 4 letters and more, not a
    common word, not recognized by any group yet. Fixed rule, at most 5, never from text other than the
    admin's own sentence."""
    out = []
    for w in WORD.findall(str(text or "")[:MAX_Q]):
        low = w.lower()
        if low in STOP or low in out or not chat.TOOL_WORD.fullmatch(low):
            continue
        if intent.classify(low, ch.get("tool_words", ""), ch.get("route_words", "")).names:
            continue
        out.append(low)
    return out[:5] if want else []


def with_word(ch, key, group, word):
    """The rule text of `key` (route_words or route_not) with one more word for the group."""
    rules = intent.parse_route_words(ch.get(key, ""))
    rules[group] = list(dict.fromkeys(rules.get(group, []) + [word]))
    return "\n".join(f"{n}: {', '.join(ws)}" for n, ws in rules.items() if ws)


# ---------------------------------------------------------------- counting (Statistik, Live)
def _file(name):
    return os.path.join(STATE, name)


def _days():
    if _stats["days"] is None:
        try:
            with open(_file("weiche-stats.json")) as f:
                d = json.load(f)
            _stats["days"] = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _stats["days"] = {}
    return _stats["days"]


def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def count(route, offered, of, direct=None, now=None):
    """One turn through the switch: only its group, the number of tools and whether the panel read directly."""
    now = time.time() if now is None else now
    names = route.names if route else []
    key = "unklar" if not names else names[0] if len(names) == 1 else "mehrere"
    model = bool(route and any(v == "Modell" for v in route.why.values()))
    follow = bool(route and any(v == "Folgefrage" for v in route.why.values()))
    hint = bool(route and route.hints)
    with _lock:
        days = _days()
        day = days.setdefault(_day(now), {})
        g = day.setdefault(key, [0] * 7)
        if not isinstance(g, list) or len(g) not in (5, 7):
            g = day[key] = [0] * 7
        g.extend([0] * (7 - len(g)))   # days counted before follow-ups and hints were
        g[0] += 1
        g[1] += int(offered or 0)
        g[2] += int(of or 0)
        g[3] += 1 if direct else 0
        g[4] += 1 if model else 0
        g[5] += 1 if follow else 0
        g[6] += 1 if hint else 0
        oldest = _day(now - KEEP_DAYS * 86400)
        for old in [d for d in days if d <= oldest]:
            days.pop(old, None)
        _stats["dirty"] = True
        if time.monotonic() - _stats["flushed"] >= FLUSH_S:
            _flush()


# Lernen (plan weiche-intelligenter 3/5): a question no rule recognized, for which the model then called a tool of one
# group first. Kept per day beside the counts: the group and the hint word that named it (a fixed word of
# intent.HINTS, one word only), never a word of the question itself. A hint word that leads to its group often is
# offered on Funktionen → Weiche as a word of that group; only the admin takes it over (with the check of all test
# sentences and Rückgängig), the panel never changes a rule by itself.
LEARN_MIN = 3        # times a hint word must have led to its group before it is offered
HINT_WORD = re.compile(r"[a-zäöüß][a-zäöüß-]{2,19}")


def group_of_tool(name):
    """The one Weiche group that owns this tool, or None (several groups, or none)."""
    owners = [g for g, (tools, _) in intent.GROUPS.items() if name in tools and g in intent.INTENT_NAMES]
    return owners[0] if len(owners) == 1 else None


def learn(route, tool, now=None):
    """Called with the first tool the model ran in a turn: counts it only when no rule (and no pick of the model)
    named a group. Returns the group counted, or None."""
    if route is None or route.names:
        return None
    group = group_of_tool(tool)
    if not group:
        return None
    word = str((route.hints or {}).get(group, "")).strip().lower()
    word = word if HINT_WORD.fullmatch(word) else ""
    now = time.time() if now is None else now
    with _lock:
        day = _days().setdefault(_day(now), {})
        box = day.get("lernen")
        if not isinstance(box, dict):
            box = day["lernen"] = {}
        g = box.get(group)
        if not isinstance(g, dict) or not isinstance(g.get("w"), dict):
            g = box[group] = {"n": 0, "w": {}}
        g["n"] = int(g.get("n", 0)) + 1
        if word and (word in g["w"] or len(g["w"]) < 30):
            g["w"][word] = int(g["w"].get(word, 0)) + 1
        _stats["dirty"] = True
        if time.monotonic() - _stats["flushed"] >= FLUSH_S:
            _flush()
    print("weiche: gelernt", group, "| Hinweiswort", "ja" if word else "nein", flush=True)
    return group


def learned(ch, now=None):
    """For the page: per group how often the model took it for an unclear question in the last 7 days, and the
    hint words offered as a word of that group (at least LEARN_MIN times, not yet a word of the group)."""
    now = time.time() if now is None else now
    week = {_day(now - i * 86400) for i in range(7)}
    with _lock:
        days = json.loads(json.dumps(_days()))
    own = intent.parse_route_words(ch.get("route_words", ""))
    groups = {}
    for day, rows in days.items():
        box = rows.get("lernen") if isinstance(rows, dict) and day in week else None
        for group, g in (box or {}).items():
            if group not in intent.GROUPS or not isinstance(g, dict):
                continue
            s = groups.setdefault(group, {"n": 0, "w": {}})
            s["n"] += int(g.get("n", 0) or 0)
            for w, n in (g.get("w") or {}).items():
                if isinstance(w, str) and HINT_WORD.fullmatch(w):
                    s["w"][w] = s["w"].get(w, 0) + int(n or 0)
    rows = []
    for group, s in sorted(groups.items(), key=lambda x: -x[1]["n"]):
        # a word the group already knows (built in or the admin's own) is not offered again
        built = intent.GROUPS[group][1] or (intent.HOME_WORDS if group == "smarthome" else None)
        offer = [{"word": w, "n": n} for w, n in sorted(s["w"].items(), key=lambda x: -x[1])
                 if n >= LEARN_MIN and w not in own.get(group, []) and not (built and built.search(w))]
        rows.append({"group": group, "label": intent.LABELS.get(group, group), "n": s["n"], "offer": offer[:5]})
    return {"rows": rows[:12], "min": LEARN_MIN}


def _flush():
    if not _stats["dirty"]:
        return
    try:
        os.makedirs(STATE, exist_ok=True)
        write_json(_file("weiche-stats.json"), _stats["days"])
        _stats["dirty"] = False
        _stats["flushed"] = time.monotonic()
    except OSError as e:
        print("weiche: Statistik nicht gespeichert", type(e).__name__, flush=True)


def summary(now=None):
    """Today and the last 7 days per group: questions, tools on average, of how many, direct reads, model picks."""
    now = time.time() if now is None else now
    today = _day(now)
    week = {_day(now - i * 86400) for i in range(7)}
    with _lock:
        days = json.loads(json.dumps(_days()))
    groups, total = {}, {"n": 0, "rules": 0, "model": 0, "unklar": 0, "direct": 0, "folge": 0, "hinweis": 0,
                           "folge_today": 0, "hinweis_today": 0}
    for day, rows in days.items():
        if day not in week or not isinstance(rows, dict):
            continue
        for key, g in rows.items():
            if not isinstance(g, list) or len(g) not in (5, 7):
                continue
            g = g + [0] * (7 - len(g))
            s = groups.setdefault(key, {"today": 0, "n": 0, "tools": 0, "of": 0, "direct": 0, "model": 0, "folge": 0,
                                        "hinweis": 0})
            s["n"] += g[0]
            s["tools"] += g[1]
            s["of"] += g[2]
            s["direct"] += g[3]
            s["model"] += g[4]
            s["folge"] += g[5]
            s["hinweis"] += g[6]
            total["folge"] += g[5]
            total["hinweis"] += g[6]
            if day == today:
                s["today"] += g[0]
                total["folge_today"] += g[5]
                total["hinweis_today"] += g[6]
            total["n"] += g[0]
            total["direct"] += g[3]
            total["model"] += g[4]
            if key == "unklar":
                total["unklar"] += g[0]
            elif key != "plaudern":
                total["rules"] += g[0] - g[4]
    for s in groups.values():
        s["avg"] = round(s["tools"] / s["n"], 1) if s["n"] else 0
        s["avg_of"] = round(s["of"] / s["n"], 1) if s["n"] else 0
    return {"groups": groups, "total": total}


def live_today(now=None):
    """Zustand → Live, node „Weiche“: today's questions, the share the rules recognized, unclear ones and the three
    groups asked most (group names and numbers only)."""
    try:
        s = summary(now)
    except Exception:
        return None
    rows = sorted(((k, v["today"]) for k, v in s["groups"].items() if v.get("today")), key=lambda x: -x[1])
    n = sum(v for _, v in rows)
    if not n:
        return {"n": 0, "known": 0, "unklar": 0, "top": [], "folge": 0, "hinweis": 0}
    unk = dict(rows).get("unklar", 0)
    return {"n": n, "known": round(100 * (n - unk - dict(rows).get("plaudern", 0)) / n), "unklar": unk,
            "top": [[intent.LABELS.get(k, k), v] for k, v in rows if k not in ("unklar", "plaudern")][:3],
            "folge": s["total"]["folge_today"], "hinweis": s["total"]["hinweis_today"]}


# ---------------------------------------------------------------- versions (Rückgängig)
def _history():
    try:
        with open(_file("weiche-history.json")) as f:
            d = json.load(f)
        return [x for x in d if isinstance(x, dict) and isinstance(x.get("rules"), dict)] if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(rules, by, keep_old=True):
    """Writes the Weiche's rules into the config (same checks and lock as every save, admin.validate) and keeps the
    version before for „Rückgängig“."""
    import admin
    import undo
    with admin._save_lock:   # one config write at a time
        new = admin.get_config()
        before = rules_of(new["chat"])
        new["chat"].update(rules)
        old = admin.validate(new)
        write_json(admin.CONFIG_PATH, new, indent=2)
        if keep_old:
            hist = (_history() + [{"t": int(time.time()), "by": by, "rules": before}])[-KEEP_VERSIONS:]
            os.makedirs(STATE, exist_ok=True)
            write_json(_file("weiche-history.json"), hist)
    undo.record(old, new, by, admin.SENSITIVE)
    guard.log("config_weiche", detail=", ".join(k for k in KEYS if before.get(k) != rules.get(k, before.get(k))))
    return new["chat"]


# ---------------------------------------------------------------- the page (admin only)
def _view(ch, english=False):
    words = {r["name"]: r for r in intent.rules(ch.get("route_words", ""))}
    nots = intent.parse_route_words_safe(ch.get("route_not", ""))
    extra = intent.own_route_extra(ch.get("route_extra", ""))
    off = ch.get("route_off") if isinstance(ch.get("route_off"), list) else []
    tests = run_tests(ch)
    stats = summary()
    direct = {name for name, _ in intent.DIRECT + intent.DIRECT_LATER}
    groups = []
    for name, (tools, _) in intent.GROUPS.items():
        w = words[name]
        hint = intent._alternatives(intent.HINTS[name].pattern) if name in intent.HINTS else []
        groups.append({
            "name": name, "label": intent.LABELS.get(name, name), "says": intent.GROUP_SAYS.get(name, ""),
            "words": w["words"], "own": w["own"], "not": nots.get(name, []), "extra": extra.get(name, []), "hints": hint,
            "off": name in off, "tools": sorted(tools), "direct": sorted(tools & direct),
            "vorrang": VORRANG.get(name, ("", ""))[1 if english else 0],
            "tests": [x for x in tests if name in x["want"].split("+") or name in x["got"].split("+")],
            "stats": stats["groups"].get(name, {}),
        })
    return {
        "on": ch.get("routing") is True, "model": ch.get("route_model", "off"), "groups": groups,
        "keep": sorted(intent.NARROW_KEEP), "lean": sorted(intent.LEAN),
        "tools": {k: v[1 if english else 0] for k, v in TOOLS.items()},
        "known": sorted(intent.known_tools()),
        "locks": [{"k": k, "t": en if english else de, "s": sen if english else sde} for k, de, en, sde, sen in LOCKS],
        "tests": {"builtin": sum(1 for x in tests if not x["own"]),
                  "builtin_ok": sum(1 for x in tests if not x["own"] and x["ok"]),
                  "own": [x for x in tests if x["own"]], "wrong": [x for x in tests if not x["ok"]][:50]},
        "unklar": {"stats": stats["groups"].get("unklar", {})},
        "alltag": alltag(ch),
        "systemone": ch.get("systemone") is True,
        "steps": list(_steps()),
        "must_tools": sorted(chat.rule_tools()),
        "stats": stats, "rules": rules_of(ch), "lernen": learned(ch),
        "history": [{"t": x.get("t"), "by": x.get("by")} for x in _history()][-5:][::-1],
        "limits": {"words": intent.MAX_ROUTE_WORDS, "extra": intent.MAX_EXTRA, "tests": MAX_TESTS, "q": MAX_Q,
                   "must": chat.MAX_TOOL_WORDS_CHARS},
    }


def _steps():
    import systemone
    return systemone.ROUTE_STEPS


def alltag(ch):
    """The everyday check with these rules (intent_alltag.py): how many land right, are kept by a hint, stay open
    or land wrong, and the sentences that do not land right (at most 60)."""
    import intent_alltag
    m = intent_alltag.measure(lambda q: intent.classify_cfg(q, ch))
    m["rows"] = m["rows"][:60]
    return m


def _english(request):
    return request.headers.get("accept-language", "")[:2].lower() == "en" or request.query_params.get("lang") == "en"


def _rules_from(body, ch):
    """The rules of a request (any of KEYS), merged onto the saved ones and checked, or 400."""
    rules = body.get("rules")
    if not isinstance(rules, dict) or set(rules) - set(KEYS):
        raise HTTPException(400, "rules: " + ", ".join(KEYS))
    merged = dict(ch, **rules)
    for k in ("route_words", "route_not", "route_extra", "tool_words"):
        if not isinstance(merged.get(k, ""), str):
            raise HTTPException(400, f"{k}: Text")
    try:
        intent.parse_route_words(merged.get("route_words", ""))
        check(merged)
    except ValueError as e:
        raise HTTPException(400, str(e))
    merged["route_tests"] = parse_tests(merged.get("route_tests", []))
    merged["route_off"] = intent.parse_route_off(merged.get("route_off", []))
    return merged


def _who(request):
    import admin
    return admin._by(request)


@router.get("/api/admin/weiche", dependencies=[Depends(auth)])
async def page(request: Request):
    guard.limit(request, "route", None, True)
    return await asyncio.to_thread(_view, load_config().get("chat", {}), _english(request))


@router.post("/api/admin/weiche/test", dependencies=[Depends(auth)])
async def try_sentence(request: Request):
    """One sentence through the switch with the saved rules (or the ones being edited): its whole way."""
    guard.limit(request, "route", None, True)
    body = await core.json_body(request, MAX_BODY)
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > intent.MAX_TEST:
        raise HTTPException(400, f"text: 1 bis {intent.MAX_TEST} Zeichen")
    before = body.get("before", "")
    if not isinstance(before, str) or len(before) > intent.MAX_TEST:
        raise HTTPException(400, f"before: höchstens {intent.MAX_TEST} Zeichen")
    ch = load_config().get("chat", {})
    if "rules" in body:
        ch = _rules_from(body, ch)
    return trace(text, ch, chat.local_now(body.get("tz") if isinstance(body.get("tz"), str) else None).date(),
                 _english(request), before)


@router.post("/api/admin/weiche/check", dependencies=[Depends(auth)])
async def preview(request: Request):
    """What a change would do before it is saved: the test sentences that turn out different."""
    guard.limit(request, "route", None, True)
    body = await core.json_body(request, MAX_BODY)
    ch = load_config().get("chat", {})
    new = _rules_from(body, ch)
    changed = await asyncio.to_thread(flips, ch, new)
    return {"flips": changed[:50], "count": len(changed)}


@router.put("/api/admin/weiche", dependencies=[Depends(auth)])
async def save(request: Request):
    """Saves the rules; a test sentence that would turn out different stops it unless "confirm" is true."""
    guard.limit(request, "weichesave", None, True)
    body = await core.json_body(request, MAX_BODY)
    ch = load_config().get("chat", {})
    new = _rules_from(body, ch)
    changed = await asyncio.to_thread(flips, ch, new)
    if changed and body.get("confirm") is not True:
        raise HTTPException(409, {"flips": changed[:50], "count": len(changed)})
    try:
        saved = await asyncio.to_thread(_save, {k: new[k] for k in KEYS if k in new}, _who(request))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await asyncio.to_thread(_view, saved, _english(request))


@router.post("/api/admin/weiche/undo", dependencies=[Depends(auth)])
async def undo_last(request: Request):
    """Puts back the version before the last change of this page."""
    guard.limit(request, "weichesave", None, True)
    hist = _history()
    if not hist:
        raise HTTPException(404, "Nichts zum Rückgängigmachen.")
    last = hist[-1]
    rules = {k: last["rules"][k] for k in KEYS if k in last["rules"]}
    ch = load_config().get("chat", {})
    try:
        check(dict(ch, **rules))
        intent.parse_route_words(rules.get("route_words", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    saved = await asyncio.to_thread(_save, rules, _who(request), False)
    write_json(_file("weiche-history.json"), hist[:-1])
    return await asyncio.to_thread(_view, saved, _english(request))


@router.post("/api/admin/weiche/suggest", dependencies=[Depends(auth)])
async def wrong_turn(request: Request):
    """„Falsch zugeordnet“: the admin's sentence and the right group -> words that would make it so, each with the
    sentences it would change. Nothing is saved here."""
    guard.limit(request, "route", None, True)
    body = await core.json_body(request, MAX_BODY)
    text, want = body.get("text"), body.get("want")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_Q:
        raise HTTPException(400, f"text: 1 bis {MAX_Q} Zeichen")
    if want not in intent.GROUPS:
        raise HTTPException(400, "want: eine Gruppe")
    ch = load_config().get("chat", {})
    now = intent.classify_cfg(text, ch)
    out = []
    for word in suggest(text, want, ch):
        try:
            new = dict(ch, route_words=with_word(ch, "route_words", want, word))
            check(new)
            intent.parse_route_words(new["route_words"])
        except ValueError:
            continue
        r = intent.classify_cfg(text, new)
        changed = await asyncio.to_thread(flips, ch, new)
        out.append({"word": word, "got": "+".join(r.names), "ok": want in r.names,
                    "flips": changed[:10], "count": len(changed), "route_words": new["route_words"]})
    # a group the sentence must not land in: one of its own words as „Nicht bei“ of that group
    nots = []
    for other in now.names:
        if other == want:
            continue
        w = (now.why.get(other) or "").strip().lower()
        if w and chat.TOOL_WORD.fullmatch(w):
            nots.append({"group": other, "word": w})
    try:   # Einstellungs-Assistent (faelle.py): the admin's „Falsch zugeordnet“ is a case too, with the sentence
        import faelle
        if faelle.wanted():
            await asyncio.to_thread(faelle.add, "weiche", {"group": now.label(), "q": text.strip(), "client": "web"},
                                    want=want, own=True)
    except Exception as e:
        print("weiche: Fall nicht notiert", type(e).__name__, flush=True)
    return {"now": now.label(), "names": now.names, "words": out, "not": nots[:3]}
