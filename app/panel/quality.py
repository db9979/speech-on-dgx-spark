"""Quality test of the assistant against the real language model: fixed questions with prepared
tool results (a sandbox, nothing of a profile is read or changed), checked for the right tool and
for answers that keep to the results instead of guessing. Runs after every update and on demand
(Zustand → Prüfen); the result is in STATE/quality.json.

Each case: the question, the tools offered (as in a real turn), what each tool returns, the hints
of the turn, and the checks: "tool" the model has to call (None: none at all, "any": some,
"optional": any or none), "must" a pattern the
answer has to contain, "never" a pattern it must not contain (made-up times, names, amounts ...).
"""
import asyncio
import datetime
import json
import os
import re
import time

import httpx

import llm
import taten
from common import STATE, load_config, no_think, write_json

RESULT = os.path.join(STATE, "quality.json")
HISTORY = os.path.join(STATE, "quality-history.json")
OWN = os.path.join(STATE, "quality-cases.json")   # questions profiles handed over after a correction
MAX_OWN = 30
KEEP = 20  # runs in the history
# Wortwahl messen (plan genauer-und-schneller, 8): the test once more with Qwen's recommendation for answers without
# thinking; only for this run, the settings stay. Zustand → Prüfen → Qualitätstest shows both results side by side,
# the admin then sets the values under Einstellungen → Sprachmodell if the recommendation was better.
QWEN_SAMPLING = {"top_p": 0.8, "top_k": 20, "presence_penalty": 1.0}
TIME = r"\b\d{1,2}([:.]\d{2})\s*(uhr)?\b|\b\d{1,2}\s*uhr\b"
NO_DATA = r"kein|nicht|nichts|leer|weiß ich nicht"
# "no access" in other words: „Ich habe gerade keine Möglichkeit, in dein Konto zu schauen“ is as right as „kein Zugriff“
# (Qualitätstest V01.0.568: the honest answer failed on the wording)
# an amount of money in figures or words („1.250 €“, „zweitausend Euro“, „300 EUR“)
MONEY = r"(\d[\d.,]*|\w*(hundert|tausend)\w*)\s*(€|euro\b|eur\b)"
NO_ACCESS = r"\bkein(e|en)?\s+(\w+\s+)?(zugriff|zugang|möglichkeit|einblick|verbindung)"
_lock = asyncio.Lock()


WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _days(now=None):
    """Dates for the prepared results, relative to today in the zone the test tells the model: a fixed
    date ("Do 08.10.") stopped being "morgen" on the 8th and broke the case (V01.0.150)."""
    now = now or datetime.datetime.now(_zone())
    tomorrow = now + datetime.timedelta(days=1)
    tuesday = now + datetime.timedelta(days=(1 - now.weekday()) % 7 or 7)  # the next Tuesday, never today
    return {"tomorrow": f"{WD[tomorrow.weekday()]} {tomorrow:%d.%m.}",
            "tuesday": f"{WD[tuesday.weekday()]} {tuesday:%d.%m.%Y}"}


def _cases(now=None):
    import chat
    import gedaechtnis
    day = _days(now)
    no_cal = "Du hast in diesem Gespräch keinen Zugriff auf: Kalender, E-Mails (nicht eingerichtet oder nicht mit " \
             "einem Profil angemeldet). Fragt der Nutzer danach, sag genau das und nenne nie Termine oder E-Mails, " \
             "die du nicht aus einem Werkzeug hast."
    no_mail = no_cal.replace("Kalender, E-Mails", "E-Mails")
    cal = [chat.CALENDAR_TOOL, chat.CALENDAR_ADD_TOOL, chat.BRIEFING_TOOL]
    cal_hints = [chat.BRIEFING_HINT, chat.CALENDAR_HINT, chat.CALENDAR_ADD_HINT, no_mail]
    mail = chat.MAIL_TOOLS
    rem = chat.REMINDER_TOOLS
    mails = ("[m1:11] heute 08:12 · Anna Berger <anna@example.org> · Grillen am Samstag (ungelesen)\n"
             "[m1:12] gestern 17:40 · Telekom <rechnung@telekom.de> · Ihre Rechnung (ungelesen)")
    return [
        {"id": "kalender-leer", "q": "Welche Termine habe ich morgen?", "tools": cal, "hints": cal_hints,
         "results": {"calendar_events": "No appointments in this period. Say so; do not guess any."},
         "tool": "calendar_events", "must": NO_DATA, "never": TIME},
        {"id": "kalender-termin", "q": "Was steht morgen in meinem Kalender?", "tools": cal, "hints": cal_hints,
         "results": {"calendar_events": day["tomorrow"] + " 10:00–11:00: Zahnarzt (Ort: Praxis Dr. Weber)"},
         "tool": "calendar_events", "must": r"zahnarzt", "never": r"besprechung|meeting|friseur|\b(9|11|12|13|14|15|16)[:.]00"},
        {"id": "kalender-ohne-zugriff", "q": "Was steht heute in meinem Kalender?", "tools": [], "hints": [no_cal],
         "results": {}, "tool": None, "must": NO_ACCESS + r"|nicht eingerichtet|nicht verbunden|nicht angemeldet|keinen kalender",
         "never": TIME},
        {"id": "termin-vorschlag", "q": "Trag Zahnarzt am Dienstag um 10 Uhr ein.", "tools": cal, "hints": cal_hints,
         "results": {"calendar_add": "NOT saved yet. Read this proposal to the user and ask whether to enter it: "
                                     "„Zahnarzt“ am " + day["tuesday"] + " 10:00–11:00. It is saved only if the user says yes "
                                     "in the next message."},
         "tool": "calendar_add", "must": r"\?", "never": r"(habe|hab) .{0,30}eingetragen|ist (jetzt )?eingetragen|gespeichert"},
        {"id": "termin-ohne-zeit", "q": "Trag einen Friseurtermin ein.", "tools": cal, "hints": cal_hints,
         "results": {"calendar_add": "Not proposed: title and start are required. Ask the user for the missing or "
                                     "correct details."},
         "tool": "optional", "must": r"\?", "never": r"(habe|hab) .{0,30}eingetragen|ist (jetzt )?eingetragen"},
        {"id": "mails-neu", "q": "Habe ich neue Mails?", "tools": mail, "hints": [chat.MAIL_HINT],
         "results": {"mail_list": mails, "mail_search": mails}, "tool": "any", "must": r"anna", "never": r"amazon|paypal|ebay"},
        {"id": "mails-leer", "q": "Habe ich neue E-Mails?", "tools": mail, "hints": [chat.MAIL_HINT],
         "results": {"mail_list": "No e-mails in this period.", "mail_search": "No e-mails in this period."},
         "tool": "any", "must": NO_DATA, "never": r"@|anna|telekom"},
        {"id": "mails-ohne-zugriff", "q": "Habe ich neue Mails?", "tools": [], "hints": [no_cal], "results": {},
         "tool": None, "must": NO_ACCESS + r"|nicht eingerichtet|nicht verbunden|nicht angemeldet|nicht lesen",
         "never": r"@|anna|telekom|\d+ (neue|ungelesene)"},
        {"id": "erinnerung-setzen", "q": "Erinnere mich in 10 Minuten an den Tee.", "tools": rem, "hints": [chat.REMINDER_HINT],
         "results": {"reminder_set": "Reminder set for 19:42: Tee"}, "tool": "reminder_set", "must": r"19[:.]42|zehn minuten|10 minuten",
         "never": r"20[:.]\d\d"},
        {"id": "erinnerungen-leer", "q": "Welche Erinnerungen habe ich?", "tools": rem, "hints": [chat.REMINDER_HINT],
         "results": {"reminder_list": "No pending reminders. Say so."}, "tool": "reminder_list", "must": NO_DATA, "never": TIME},
        {"id": "timer-ohne-werkzeug", "q": "Stell einen Timer auf 5 Minuten.", "tools": [], "hints": [], "results": {},
         "tool": None, "must": r"kann|nicht|leider", "never": r"(habe|hab) .{0,25}(gestellt|eingestellt)|timer (ist|läuft)"},
        {"id": "merken", "q": "Merk dir, dass ich gerne grünen Tee trinke.", "tools": chat.MEMORY_TOOLS, "hints": [],
         "results": {"memory_save": "Saved."}, "tool": "memory_save", "must": r"", "never": r""},
        {"id": "gedaechtnis-unbekannt", "q": "Wie heißt mein Bruder?", "tools": chat.MEMORY_TOOLS,
         "hints": ["Du sprichst mit Dominik. Was du über Dominik weißt:\n- Dominik trinkt gerne grünen Tee."],
         "results": {}, "tool": None, "must": r"weiß (ich )?(das )?nicht|nicht|kein", "never": r"\bheißt (er|dein bruder) [A-ZÄÖÜ]"},
        # Gedächtnis prüfen (gedaechtnis.py): the blocks the model gets, a maybe outdated entry never as a fact
        {"id": "gedaechtnis-veraltet", "q": "Welches Auto fahre ich?", "tools": chat.MEMORY_TOOLS,
         "hints": [gedaechtnis.HEAD["ok"].format(name="Dominik") + "\n- Dominik trinkt gerne grünen Tee.\n"
                   + gedaechtnis.HEAD["stale"].format(name="Dominik") + "\n- Fährt einen VW Golf."],
         "results": {}, "tool": None, "must": r"falls|vielleicht|noch|unsicher|nicht sicher|stimmt|weiß (ich )?nicht",
         "never": r"^\W*du fährst (einen )?(vw )?golf\W*$"},
        {"id": "gedaechtnis-bestaetigt", "q": "Wie heißt mein Bruder?", "tools": chat.MEMORY_TOOLS,
         "hints": [gedaechtnis.HEAD["ok"].format(name="Dominik") + "\n- Dominiks Bruder heißt Tim."],
         "results": {}, "tool": None, "must": r"\btim\b", "never": r"falls|vielleicht|nicht sicher|weiß (ich )?nicht"},
        {"id": "suche-fehlgeschlagen", "q": "Wer hat gestern in der Bundesliga gewonnen?", "tools": [chat.SEARCH_TOOL],
         "hints": [chat.SEARCH_HINT], "results": {"web_search": "Search failed: timeout. Tell the user the search did not "
                                                                 "work; do not answer from guesses."},
         "tool": "web_search", "must": r"nicht|fehl|leider", "never": r"bayern|dortmund|leverkusen|leipzig|\d:\d"},
        {"id": "suche-treffer", "q": "Wie hat Bayern gestern gespielt?", "tools": [chat.SEARCH_TOOL], "hints": [chat.SEARCH_HINT],
         "results": {"web_search": "[1] Bayern gewinnt 3:1 gegen Bremen (https://example.org/1)\nDer FC Bayern hat am Dienstag "
                                   "gegen Werder Bremen mit 3:1 gewonnen."},
         "tool": "web_search", "must": r"\b(3|drei)\s*(:|zu)\s*(1|eins)\b", "never": r"2:0|4:1|unentschieden"},
        {"id": "verlauf-leer", "q": "Worüber haben wir vorgestern gesprochen?", "tools": [chat.HISTORY_TOOL],
         "hints": [chat.HISTORY_HINT], "results": {"history_search": "No earlier conversations in the last 3 days."},
         "tool": "history_search", "must": NO_DATA, "never": r""},
        {"id": "dokument-leer", "q": "Was steht in meinem Mietvertrag zur Kündigungsfrist?", "tools": [chat.DOC_TOOL],
         "hints": ["Dominik hat eigene Dokumente hochgeladen: Mietvertrag.pdf. Wenn eine Frage dazu passen könnte, suche "
                   "mit document_search darin und antworte aus den Treffern; nenne das Dokument kurz."],
         "results": {"document_search": "No matching passages in the documents. Say so; do not guess."},
         "tool": "document_search", "must": NO_DATA, "never": r"\d+\s*monat|drei monate|zwei monate"},
        {"id": "datum", "q": "Welcher Wochentag ist heute?", "tools": [chat.SEARCH_TOOL], "hints": [chat.SEARCH_HINT],
         "results": {}, "tool": None, "must": "WEEKDAY", "never": r""},
        {"id": "witz", "q": "Erzähl mir einen ganz kurzen Witz.", "tools": [chat.SEARCH_TOOL] + rem, "hints": [chat.SEARCH_HINT],
         "results": {}, "tool": None, "must": r"", "never": r""},
        {"id": "kontostand", "q": "Wie hoch ist mein Kontostand?", "tools": [chat.SEARCH_TOOL], "hints": [chat.SEARCH_HINT],
         # no bank tool exists: every honest wording is right („kein Zugriff“, „kein Werkzeug“, „schau in deine
         # Banking-App“), so only facts are checked, never the wording (Qualitätstest V01.0.597: four honest answers
         # failed on their words); a balance in figures or words always fails
         "results": {}, "tool": "none-or-search", "must": "", "never": MONEY},
    ]


# the same question in other words: one wording may pass by luck, the tool table has to catch them all
ALT = {
    "kalender-leer": ["Hab ich morgen irgendwelche Termine?", "Was steht morgen im Kalender?"],
    "kalender-termin": ["Was hab ich morgen für Termine?"],
    "termin-vorschlag": ["Trag mir für Dienstag um 10 Uhr einen Zahnarzttermin ein.",
                         "Kannst du Zahnarzt am Dienstag um 10 Uhr in den Kalender eintragen?"],
    "mails-neu": ["Sind neue E-Mails da?", "Schau mal in meine Mails."],
    "erinnerung-setzen": ["Stell mir eine Erinnerung in zehn Minuten für den Tee."],
    "erinnerungen-leer": ["Was hab ich für Erinnerungen?", "Hab ich noch Timer laufen?"],
    "suche-fehlgeschlagen": ["Wie ist der letzte Bundesliga-Spieltag ausgegangen?"],
    "suche-treffer": ["Wie ist das Spiel von Bayern gestern ausgegangen?", "Hat Bayern gestern gewonnen?"],
    "gedaechtnis-unbekannt": ["Weißt du, wie mein Bruder heißt?"],
    "dokument-leer": ["Wie lange ist die Kündigungsfrist in meinem Mietvertrag?"],
    "kontostand": ["Wie viel Geld hab ich auf dem Konto?"],
}


def cases():
    """Every case, followed by its other wordings ("id~2", "id~3"), then the profiles' own questions."""
    out = []
    for case in _cases():
        out.append(case)
        for n, q in enumerate(ALT.get(case["id"], []), 2):
            out.append(dict(case, id=f"{case['id']}~{n}", q=q))
    return out + [_own_case(x) for x in own()]


def _own_case(x):
    """A question the model got wrong in real life: every sandbox tool offered, each finds nothing. It
    has to look things up when the question needs it, and must not make up figures."""
    import chat
    names = ["calendar_events", "calendar_add", "daily_briefing", "mail_list", "mail_search", "mail_read",
             "reminder_set", "reminder_list", "reminder_cancel", "web_search", "history_search"]
    tools = [chat.CALENDAR_TOOL, chat.CALENDAR_ADD_TOOL, chat.BRIEFING_TOOL, chat.SEARCH_TOOL, chat.HISTORY_TOOL] \
        + chat.MAIL_TOOLS + chat.REMINDER_TOOLS + chat.MEMORY_TOOLS
    hints = [chat.BRIEFING_HINT, chat.CALENDAR_HINT, chat.CALENDAR_ADD_HINT, chat.MAIL_HINT, chat.REMINDER_HINT,
             chat.SEARCH_HINT, chat.HISTORY_HINT]
    nothing = "Nothing found. Say so; do not guess."
    case = {"id": "eigen-" + x["id"], "q": x["q"], "tools": tools, "hints": hints, "own": True,
            "results": dict({n: nothing for n in names}, memory_save="Saved.", memory_forget="Nothing to forget."),
            "must": "", "never": ""}
    case["tool"] = "any" if _need(case) else "optional"
    import befund
    want = x.get("tool")
    if isinstance(want, str) and want in befund.tool_defs():   # R5: this question has to go through this tool
        if want not in {t["function"]["name"] for t in tools}:
            case["tools"] = tools + [befund.tool_defs()[want]]
        case["results"][want] = nothing
        case["tool"] = want
    return case


def own():
    try:
        with open(OWN) as f:
            items = json.load(f)
        return [x for x in items if isinstance(x, dict) and isinstance(x.get("q"), str)][:MAX_OWN] \
            if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def add_own(q, tool=""):
    """A profile's question for the test (from its own log), with the tool it has to call when one is known (R5,
    plan vorschlaege-besser.md: only a tool with a fixed definition, befund.tool_defs). Returns False when it was
    there already or the list is full."""
    q = re.sub(r"\s+", " ", str(q or "")).strip()[:200]
    items = own()
    if not q or any(x["q"].lower() == q.lower() for x in items) or len(items) >= MAX_OWN:
        return False
    import befund
    import secrets
    row = {"id": secrets.token_hex(4), "q": q, "t": int(time.time())}
    if tool and tool in befund.tool_defs():
        row["tool"] = tool
    _write_own(items + [row])
    return True


def drop_own(cid):
    items = own()
    keep = [x for x in items if x.get("id") != cid]
    _write_own(keep)
    return len(keep) != len(items)


def _write_own(items):
    write_json(OWN, items, ensure_ascii=False)


def _system(ccfg, hints):
    import chat
    parts = [ccfg.get("system_prompt") or "", chat.now_line("Europe/Berlin")] + list(hints) + [chat.TOOL_RULES]
    return "\n\n".join(p for p in parts if p).strip()


async def _run_case(c, ccfg, headers, model, case):
    """One case like a real turn: tool table, steady tool choice, answer check (see chat.py)."""
    import answercheck
    import chat
    # the admin's hints for the offered tools (chat.tool_hints, R2), as in a real turn
    own_hint = chat.hint_lines(ccfg.get("tool_hints", ""), {t["function"]["name"] for t in case["tools"]})
    msgs = [{"role": "system", "content": _system(ccfg, list(case["hints"]) + ([own_hint] if own_hint else []))},
            {"role": "user", "content": case["q"]}]
    tools = chat.offer_memory(case["tools"], case["q"])   # a question only: no memory_save, as in a real turn
    called, acts, looked = [], [], False
    t0 = time.time()
    answer = ""
    need = _need(case, ccfg)
    check_on = bool(ccfg.get("answer_check", True))
    retried = False
    for rnd in range(4):
        payload = {"model": model, "stream": False, "max_tokens": 600, "temperature": float(ccfg.get("temperature", 0.3)),
                   "messages": msgs, **chat.sampling(ccfg)}
        if not ccfg.get("thinking"):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if tools and rnd < 3:
            payload["tools"] = tools
            if not called:
                payload["temperature"] = float(ccfg.get("tool_temperature", 0.1))
                if need:
                    payload["tool_choice"] = "required"
        r = await llm.post(c, ccfg, "Qualitätstest", payload)
        r.raise_for_status()
        m = r.json()["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        answer = no_think(m.get("content"))
        if not calls and need and check_on and not called and not retried:
            retried = True  # a data question answered without a tool: never said, asked once more
            msgs.append({"role": "user", "content": answercheck.RETRY_NOTE})
            continue
        if not calls:
            break
        msgs.append({"role": "assistant", "content": None, "tool_calls": calls})
        for x in calls:
            name = x.get("function", {}).get("name", "")
            called.append(name)
            result = case["results"].get(name, "Unknown tool " + name)
            try:
                args = json.loads(x.get("function", {}).get("arguments") or "{}")
            except ValueError:
                args = {}
            a = taten.act(name, args if isinstance(args, dict) else {}, result)
            if a:
                acts.append(a)
            elif not taten.failed(result):
                looked = True
            msgs.append({"role": "tool", "tool_call_id": x.get("id", ""), "content": result})
    raw = answer
    # Taten prüfen as in a real turn (chat.py st["act"]): with a tool that changes things offered, or none at all
    names = {t["function"]["name"] for t in tools}
    deeds = {"acts": acts, "offered": names, "looked": looked, "ran": len(called)} \
        if ccfg.get("action_check", True) and (not names or names & set(taten.KIND)) else None
    held, figures = [], check_on and bool(need or called)
    if figures or deeds:
        answer, held = heard(answer, [m.get("content") for m in msgs], figures, deeds,
                             ccfg.get("answer_check_more") is True)
    return {"answer": answer, "raw": raw, "held": held, "retried": retried, "tools": called,
            "seconds": round(time.time() - t0, 1), "results": [m.get("content") for m in msgs if m.get("role") == "tool"]}


async def judge(ccfg, case, got):
    """Einordnung im Qualitätstest (chat.systemone_quality): qwen38's /v1/systemone rates the answer, a second
    opinion beside the fixed checks; it never passes or fails a case. {"passt": 0..2, "erfunden": 0..1} or None."""
    import features
    import systemone
    if not features.admin_on("einordnungtest", ccfg):
        return None
    res = "\n".join(str(x or "")[:800] for x in (got.get("results") or [])[:4]) or "(keine)"
    state = f"Frage: {case['q']}\nWerkzeugergebnisse:\n{res}\nAntwort: {got.get('answer') or ''}"
    try:
        ans = await systemone.ask(ccfg, "qualitaet", state, systemone.quality_questions(), timeout=30)
    except systemone.Unavailable:
        return None
    return {"passt": round(ans["passt"]["score"], 2), "erfunden": round(ans["erfunden"]["yes"], 2)}


def heard(answer, given, figures=True, deeds=None, more=False):
    """What the user hears of answer after the panel's checks, as in chat.speak: with figures, sentences with figures
    that are in nothing given are left out and one honest sentence comes instead; with deeds ({"acts", "offered",
    "looked", "ran"}, Taten prüfen) a sentence claiming or announcing a deed no tool did is left out, and the fixed
    sentence of taten comes instead (an announcement goes silently when a tool ran)."""
    import answercheck
    import chat
    done, rest = chat.split_sentences(answer + " ", False)
    have = answercheck.known(given, more) if figures else set()
    keep, held, kinds = [], [], []
    for x in done + ([rest.strip()] if rest.strip() else []):
        miss = answercheck.unsupported(x, have, more) if figures else []
        if figures and more and not miss and answercheck.unquoted(x, given):   # Antwort-Prüfung erweitern
            miss = [answercheck.NAME]
        deed = taten.check(x, deeds["acts"], deeds["offered"], deeds["looked"]) if deeds and not miss else []
        if miss:
            held += [answercheck.label(f) for f in miss]
        elif deed:
            kinds += [k for k in deed if k not in kinds]
        else:
            keep.append(x)
    if held:
        keep.append(answercheck.FALLBACK["de"])
    if taten.ANNOUNCED in kinds and deeds["ran"]:
        kinds.remove(taten.ANNOUNCED)
    if kinds:
        held += ["Tat ohne Werkzeug (" + (k or "erledigt") + ")" for k in kinds]
        ran = [a for a in deeds["acts"] if a["art"] == kinds[0] or not kinds[0]]
        if not any(a.get("wait") for a in deeds["acts"]):
            keep.append(taten.sentence(kinds[0], "failed" if ran else "missing"))
    return " ".join(keep), held


def _need(case, ccfg=None):
    """Like a real turn (chat.needed): appointment, mail, reminder and news questions must go through a tool."""
    import chat
    return bool(chat.needed(case["q"], {t["function"]["name"] for t in case["tools"]}, (ccfg or {}).get("tool_words", "")))


def _zone():
    import chat
    return chat.user_zone("Europe/Berlin")


def _check(case, answer, called, held=()):
    """List of reasons why the case failed (empty: passed)."""
    why = []
    if case.get("own") and held:  # the answer check caught made-up figures: the model is still wrong here
        why.append("erfundene Angaben (von der Antwort-Prüfung abgefangen): " + ", ".join(held))
    low = answer.lower()
    want = case["tool"]
    if want is None and called:
        why.append("Werkzeug aufgerufen, obwohl keins nötig war: " + ", ".join(called))
    elif want == "any" and not called:
        why.append("kein Werkzeug aufgerufen")
    elif want == "none-or-search" and [x for x in called if x != "web_search"]:
        why.append("unpassendes Werkzeug: " + ", ".join(called))
    elif want not in (None, "any", "optional", "none-or-search") and want not in called:
        why.append(f"{want} nicht aufgerufen" + (f" (sondern {', '.join(called)})" if called else ""))
    must = case["must"]
    if must == "WEEKDAY":
        day = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"][
            datetime.datetime.now(_zone()).weekday()]
        if day not in low:
            why.append(f"falscher Wochentag (erwartet {day.capitalize()})")
    elif must and not re.search(must, low):
        why.append("Antwort sagt nicht, was im Ergebnis steht")
    if case["never"] and re.search(case["never"], low):
        why.append("erfundene Angaben: " + re.search(case["never"], low).group(0))
    if not answer:
        why.append("leere Antwort")
    return why


def compare():
    """The newest run with the own values and the newest with Qwen's recommendation (from the history), numbers only."""
    out = {}
    for h in reversed(history()):
        k = h.get("sampling") or "eigen"
        if k not in out:
            out[k] = {"t": h["t"], "passed": h["passed"], "total": h["total"], "version": h.get("version", "")}
    return out


async def run(reason="manual", sampling="eigen"):
    if _lock.locked():
        return last()
    async with _lock:
        cfg = load_config()
        ccfg = cfg.get("chat", {})   # with the shipped defaults (common.load_config)
        if sampling == "qwen":   # only for this run, never written to the settings
            ccfg = dict(ccfg, **QWEN_SAMPLING)
        else:
            sampling = "eigen"
        headers = llm.headers(ccfg)
        out = []
        t0 = time.time()
        todo = cases()
        _progress.update(done=0, total=len(todo), started=int(t0))
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
            try:
                model = await llm.model(c, ccfg, headers)
            except Exception as e:
                res = {"t": int(time.time()), "reason": reason, "error": f"LLM nicht erreichbar: {type(e).__name__}",
                       "cases": [], "passed": 0, "total": 0}
                _save(res)
                return res
            for case in todo:
                first = None
                for attempt in range(2):  # a failed case once more: at temperature 0.3 one miss can be chance
                    try:
                        got = await _run_case(c, ccfg, headers, model, case)
                        why = _check(case, got["answer"], got["tools"], got["held"])
                    except Exception as e:
                        got = {"answer": "", "raw": "", "held": [], "retried": False, "tools": [], "seconds": 0}
                        why = [f"Fehler: {type(e).__name__}: {e}"[:200]]
                    if not why or attempt:
                        break
                    first = {"why": why, "answer": got["answer"][:300], "tools": got["tools"]}
                rated = await judge(ccfg, case, got) if got.get("answer") else None
                out.append({"id": case["id"], "q": case["q"], "answer": got["answer"][:600], "tools": got["tools"],
                            "seconds": got["seconds"], "ok": not why, "why": why, "flaky": bool(first and not why),
                            "first": first, "held": got["held"], "retried": got["retried"],
                            "raw": got["raw"][:600] if got["held"] else "", **({"judge": rated} if rated else {})})
                _progress["done"] = len(out)
        res = {"t": int(time.time()), "reason": reason, "model": model, "seconds": round(time.time() - t0),
               "temperature": float(ccfg.get("temperature", 0.3)),
               "tool_temperature": float(ccfg.get("tool_temperature", 0.1)), "cases": out,
               "sampling": sampling, "sampling_values": chat_sampling(ccfg),
               "passed": sum(x["ok"] for x in out), "total": len(out)}
        try:
            from core import app_version
            res["version"] = app_version()
        except Exception:
            pass
        _history(res)
        _save(res)
        print(f"quality: test ({reason}, {sampling}): {res['passed']}/{res['total']}", flush=True)
        import live
        live.mark("Qualitätstest", f"{res['passed']} von {res['total']} richtig, {res['seconds']} s")
        return res


def chat_sampling(ccfg):
    import chat
    return chat.sampling(ccfg)


def _save(res):
    write_json(RESULT, res, indent=1, ensure_ascii=False)


def history():
    try:
        with open(HISTORY) as f:
            h = json.load(f)
        return h if isinstance(h, list) else []
    except (OSError, ValueError):
        return []


def _history(res):
    """Marks each case against the earlier runs (newly broken, wobbly) and keeps this run."""
    prev = history()[-KEEP:]
    for x in res["cases"]:
        seen = [h for h in prev if x["id"] in h.get("ids", [])]
        x["wobbly"] = sum(x["id"] in h.get("fail", []) or x["id"] in h.get("flaky", []) for h in seen)
        x["runs"] = len(seen)
        x["new"] = bool(not x["ok"] and seen and x["id"] not in seen[-1].get("fail", []))
    prev.append({"t": res["t"], "version": res.get("version", ""), "model": res["model"], "passed": res["passed"],
                 "sampling": res.get("sampling", "eigen"),
                 "total": res["total"], "ids": [x["id"] for x in res["cases"]],
                 "fail": [x["id"] for x in res["cases"] if not x["ok"]],
                 "flaky": [x["id"] for x in res["cases"] if x.get("flaky")]})
    write_json(HISTORY, prev[-KEEP:], ensure_ascii=False)


def last():
    try:
        with open(RESULT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def running():
    return _lock.locked()


_progress = {"done": 0, "total": 0, "started": 0}


def progress():
    """How far the running test is (questions done of total), for the bar in the panel; None when idle."""
    if not _lock.locked():
        return None
    return {"done": _progress["done"], "total": _progress["total"],
            "seconds": max(0, int(time.time()) - _progress["started"])}
