"""Quellenangabe (Dominik 2026-11-13, thread „Quellenangabe bei Antworten einbauen“, „Alles nach Empfehlung
umsetzen“): under every answer that wants to know something, the panel says where it came from, so the person can
check that the right source was asked. Built by fixed rules of the panel from what really ran in this answer, never
by the model, never with a word the model wrote about its sources.

    1a  the line under the answer („Quelle: 2 Mails, Termine lesen, Websuche“, or „nichts nachgeschlagen, nur
        Modellwissen“), in the same "herkunft" event as the Herkunft line of „Erst lokal“ (lokal.herkunft), so the
        panel, the apps, the Begleiter and Telegram show it without a change of their own
    2a  at a speaker, the phone, the watch, Siri or in the car (saetze.SPOKEN) a short sentence at the end
        („Quelle: Websuche.“), a preference of the profile (quelle_sagen, on, Ich → Gespräch)
    3   „Woher weißt du das?“ (FRAGE, the whole message): the panel answers without the model from the record of
        the last answer of this profile on this device (TTL, only in memory): every source with the search words
        and the titles of the pages and hits; only to the person itself, never into a log
    4   a hint when the source does not fit the question: the Quellen-Weiche's class (quellen.klasse, intern /
        extern) against the sources that ran („Achtung: nicht in deinen Daten nachgesehen“)
    5   Logs → Anfragen: the readable tool names and the hint's word on the request (tracelog.Rec.quelle), fixed
        words only

A source is every tool of the answer that reads (not in taten.KIND) and did not fail, named by werkzeuge.label,
and what the quick look of „Erst lokal“ found (kinds and numbers, lokal.ARTEN). Which tools read the own data or
the world comes from the Weiche's groups (quellen.werkzeug_art: intent.GROUPS with quellen.OWN_GROUPS /
WORLD_GROUPS), not from a list of its own. This module is low (only werkzeuge and taten): the flow (chat_modell)
hands in what lies above it, so it never joins the big import cycle (test_schichten).
Who: the admin switch chat.source_note (off), for every profile it releases; never guests, another voice or MCP
(they get no line, no record). Live: today's lines, hints, questions and spoken sentences (numbers only).
"""
import json
import re
import threading
import time

import taten
import werkzeuge

KEY = "quelle"                 # the line, „Woher weißt du das?“, the hint and the column (features.FEATURES)
SAY_KEY = "quellesagen"        # the spoken sentence, a preference (quelle_sagen)
TTL = 1800                     # the record of the last answer holds 30 minutes, for this profile on this device
MAX_KEEP = 500                 # records kept at most (the oldest go first)
MAX_NAMES = 6                  # sources named in the line
MAX_SAID = 3                   # sources named in the spoken sentence
MAX_DETAIL = 5                 # titles or search words per source in the answer to „Woher?“
MODELL = ("nichts nachgeschlagen, nur Modellwissen", "nothing looked up, model knowledge only")
HEAD = ("Quelle: ", "Source: ")
# the hint (4): the class of the question, the sources that ran do not fit it
WARN = {"intern": ("nicht in deinen Daten nachgesehen", "not looked up in your own data"),
        "extern": ("nicht im Internet nachgesehen", "not looked up on the web")}
WARN_HEAD = ("Achtung: ", "Note: ")
# the quick look searched the own sources but found nothing there: still a look in the own data
EIGEN_LEER = ("eigene Daten ohne Treffer", "own data, no hits")
# „Woher weißt du das?“, „Quelle?“, „Where did you get that?“: the whole message, nothing else in it
FRAGE = re.compile(
    r"(?i)^\W*((hey |ok |okay )?spark\W+)?(und\s+)?("
    r"woher (weißt|weisst|hast|kennst) du (das|dies|es)( denn| eigentlich| genau)*|"
    r"woher (stammt|kommt|kommen|stammen) (das|die info\w*|diese info\w*|die angabe\w*|deine info\w*)( denn| eigentlich| genau)*|"
    r"wo (hast|hattest) du (das|dies|es) (denn |eigentlich |genau )*(her|gefunden|gelesen|nachgeschaut|nachgesehen)|"
    r"(was|welche) (ist|war|sind|waren) (denn |eigentlich |genau )*(deine|die) quelle(n)?|"
    r"welche quelle(n)?( hast du (benutzt|genommen|verwendet))?|"
    r"(nenn|sag) (mir )?(bitte )?(deine|die) quelle(n)?( bitte)?|"
    r"quelle(n)?( bitte)?|"
    r"where did you (get|find|read) (that|this|it)( from)?|where does (that|this) come from|"
    r"what('s| is| was| were| are) (your|the) sources?|which sources?( did you use)?|sources?( please)?"
    r")\W*$")

_lock = threading.Lock()
_last = {}                     # (profile id, device "client:convo") -> (monotonic time, record)
_live = {"day": "", "zeile": 0, "warnung": 0, "frage": 0, "gesagt": 0}
ZAEHLER = ("zeile", "warnung", "frage", "gesagt")


def frage(text):
    """The person asks where the last answer came from (the whole message)."""
    return bool(FRAGE.match(str(text or "")[:200]))


def _short(v, n=80):
    """One title or search words as plain words: no markup, no line breaks, cut."""
    return re.sub(r"\s+", " ", re.sub(r"[<>\[\]{}`*_|#\\]", " ", str(v or ""))).strip()[:n]


def _detail(args):
    """The search words of one call (only what the call was given), or ""."""
    if not isinstance(args, dict):
        return ""
    for k in ("query", "q", "text", "topic", "name", "title", "when", "date"):
        if isinstance(args.get(k), str) and args[k].strip():
            return _short(args[k], 60)
    return ""


def teile(calls, art_of, found=None, hit_art=None, arten=None):
    """The sources of one answer, in the order they ran: [{"tool", "de", "en", "art", "n", "mehr": [details]}].
    calls: trace["calls"] of the answer ({"name", "args", "result"}; the panel's own call ends in " (Panel)");
    art_of: tool -> "eigen" | "welt" | "" (quellen.werkzeug_art); found: what the quick look of „Erst lokal“ found
    (lokal.look) or None, with hit_art (lokal.art) and arten (lokal.ARTEN) for its hits."""
    out, by = [], {}
    if found:
        n = {}
        for h in found.get("hits") or []:
            k = hit_art(h)
            if k in arten:
                n.setdefault(k, []).append(_short(h.get("title")))
        for k, titles in n.items():
            c, names = len(titles), arten[k]
            out.append({"tool": "lokal:" + k, "de": f"{c} {names[0 if c == 1 else 1]}",
                        "en": f"{c} {names[2 if c == 1 else 3]}", "art": "welt" if k == "archiv" else "eigen",
                        "n": c, "mehr": [t for t in titles if t][:MAX_DETAIL]})
        if not any(p["art"] == "eigen" for p in out) and any(k in (found.get("n") or {}) for k in ("docs", "history", "fund")):
            out.append({"tool": "lokal:leer", "de": EIGEN_LEER[0], "en": EIGEN_LEER[1], "art": "eigen", "n": 0, "mehr": []})
        if found.get("web"):
            p = {"tool": "web_search", "de": werkzeuge.label("web_search"), "en": werkzeuge.label("web_search", True),
                 "art": "welt", "n": 1, "mehr": []}
            by["web_search"] = p
            out.append(p)
    for c in calls or ():
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").removesuffix(werkzeuge.PANEL)
        if name not in werkzeuge.NAMES or name == "local_search" or name in taten.KIND or taten.failed(c.get("result")):
            continue
        try:
            args = json.loads(c.get("args") or "{}")
        except (TypeError, ValueError):
            args = {}
        d = _detail(args)
        if name in by:
            by[name]["n"] += 1
            if d and d not in by[name]["mehr"] and len(by[name]["mehr"]) < MAX_DETAIL:
                by[name]["mehr"].append(d)
            continue
        by[name] = {"tool": name, "de": werkzeuge.label(name), "en": werkzeuge.label(name, True), "art": art_of(name),
                    "n": 1, "mehr": [d] if d else []}
        out.append(by[name])
    return out


def warnung(kind, parts):
    """The hint's key (4): "intern" when a question about the own data looked in none, "extern" when a question
    about the world looked nowhere outside; else ""."""
    arten = {p["art"] for p in parts}
    if kind == "intern" and "eigen" not in arten:
        return "intern"
    if kind == "extern" and "welt" not in arten:
        return "extern"
    return ""


def zeile(parts, warn="", en=False):
    """The line under the answer, in fixed words only."""
    i = 1 if en else 0
    names = [p["en" if en else "de"] for p in parts][:MAX_NAMES]
    text = HEAD[i] + (", ".join(names) + (" …" if len(parts) > MAX_NAMES else "") if names else MODELL[i])
    return text + (" · " + WARN_HEAD[i] + WARN[warn][i] if warn else "")


def satz(parts, warn="", en=False):
    """The short sentence at the end of a spoken answer (2a)."""
    names = [p["en" if en else "de"] for p in parts][:MAX_SAID]
    if not names:
        out = "I only know that from my model knowledge, I looked nothing up." if en else \
            "Das weiß ich nur aus meinem Modellwissen, nachgeschlagen habe ich nichts."
    else:
        und = " and " if en else " und "
        out = ("Source: " if en else "Quelle: ") + (", ".join(names[:-1]) + und + names[-1] if len(names) > 1 else names[0]) + "."
    if warn == "intern":
        out += " I did not look in your own data." if en else " In deinen Daten habe ich nicht nachgesehen."
    elif warn == "extern":
        out += " I did not look it up on the web." if en else " Im Internet habe ich nicht nachgesehen."
    return out


def merke(uid, src, parts, warn, links=(), now=None):
    """Keep the record of this answer for „Woher weißt du das?“ (only in memory, TTL, this profile and device)."""
    if not uid or not src:
        return
    now = time.monotonic() if now is None else now
    rec = {"parts": [dict(p, mehr=list(p["mehr"])) for p in parts], "warn": warn,
           "links": [t for t in (_short(x.get("title") or x.get("url"), 80) for x in links or () if isinstance(x, dict)) if t][:MAX_DETAIL]}
    with _lock:
        _last.pop((uid, src), None)
        if len(_last) >= MAX_KEEP:
            for k in [k for k, v in _last.items() if now - v[0] > TTL] or list(_last)[:MAX_KEEP // 10]:
                _last.pop(k, None)
        _last[(uid, src)] = (now, rec)


def letzte(uid, src, now=None):
    now = time.monotonic() if now is None else now
    with _lock:
        got = _last.get((uid, src))
    return got[1] if got and now - got[0] <= TTL else None


def fremd(uid, src, now=None):
    """The answer to „Woher?“ holds words from outside (titles of pages and hits, search words): the answer is
    marked like any answer from outside text (event "outside"), so the next turn starts locked and the history
    leaves it out later (chat.left_out)."""
    rec = letzte(uid, src, now)
    return bool(rec and (rec["links"] or any(p["mehr"] for p in rec["parts"])))


def antwort(uid, src, en=False, now=None):
    """The panel's answer to „Woher weißt du das?“: (shown, spoken), without the model."""
    rec = letzte(uid, src, now)
    if rec is None:
        s = ("I no longer have a source for that: I keep it for 30 minutes, only on this device." if en else
             "Dazu habe ich keine Quelle mehr: ich merke sie mir 30 Minuten lang und nur auf diesem Gerät.")
        return s, s
    i = 1 if en else 0
    if not rec["parts"]:
        shown = spoken = ("For my last answer I looked nothing up: it came from my model knowledge only." if en else
                          "Für meine letzte Antwort habe ich nichts nachgeschlagen: sie kam nur aus meinem Modellwissen.")
    else:
        lines, said = [], []
        for p in rec["parts"]:
            name = p["en" if en else "de"]
            mehr = "; ".join(p["mehr"])
            lines.append("• " + name + (" (" + str(p["n"]) + "×)" if p["n"] > 1 and not p["tool"].startswith("lokal:") else "")
                         + (": " + mehr if mehr else ""))
            said.append(name + ((" for „" + p["mehr"][0] + "“" if en else " mit „" + p["mehr"][0] + "“")
                                if p["mehr"] and not p["tool"].startswith("lokal:") else ""))
        if rec["links"]:
            lines.append(("• Pages: " if en else "• Seiten: ") + "; ".join(rec["links"]))
        shown = ("For my last answer I used:\n" if en else "Für meine letzte Antwort habe ich benutzt:\n") + "\n".join(lines)
        und = " and " if en else " und "
        spoken = ("For my last answer I used " if en else "Für meine letzte Antwort habe ich ") \
            + (", ".join(said[:-1]) + und + said[-1] if len(said) > 1 else said[0]) + ("." if en else " benutzt.")
        if rec["links"]:
            spoken += (" Pages: " if en else " Seiten: ") + ", ".join(rec["links"][:3]) + "."
    if rec["warn"]:
        shown += "\n\n" + WARN_HEAD[i] + WARN[rec["warn"]][i] + "."
        spoken += " " + WARN_HEAD[i] + WARN[rec["warn"]][i] + "."
    return shown, spoken


def note(k, now=None):
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))
    with _lock:
        if _live["day"] != day:
            _live.update(day=day, **{x: 0 for x in ZAEHLER})
        if k in ZAEHLER:
            _live[k] += 1


def for_live(now=None):
    """{"zeile", "warnung", "frage", "gesagt"} of today (numbers only)."""
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))
    with _lock:
        return {k: (_live[k] if _live["day"] == day else 0) for k in ZAEHLER}


async def links(out, st, items):
    """The "sources" event under the answer (web pages, archive articles: their links as before) and their titles
    kept with the answer for „Woher weißt du das?“ (merke takes the first MAX_DETAIL)."""
    got = st.setdefault("links", [])
    got.extend(x for x in (items or ())[:MAX_DETAIL] if isinstance(x, dict) and len(got) < 4 * MAX_DETAIL)
    await out.put({"type": "sources", "items": items})
