"""Handlungs-Prüfung (Dominik 2026-10-12, plan handlungs-pruefung): what the Spark did in this answer, and whether a
sentence claims a deed that no tool did.

Fixed rules, no model: a tool that changes something has a kind (KIND), its result counts as done only when it does
not start with one of the fixed failure words (failed), and a finished sentence that claims a deed of a kind (claims)
is said only when a tool of that kind worked in this answer (check). Instead the panel says one fixed sentence
(sentence). Only `re` and `time`: chat, answercheck, tagebuch and klaeren import this module, never the other way round.
"""
import re
import time

# tool -> kind of deed; the kinds are the keys of tagebuch.ARTEN (its labels stay there)
KIND = {
    "home_assistant": "geraet", "home_assistant_action": "geraet", "pc_action": "geraet", "iphone_action": "geraet",
    "reminder_set": "erinnerung", "reminder_cancel": "erinnerung",
    "calendar_add": "termin",
    "mail_draft": "mail_entwurf",
    "document_plan": "dokument", "document_change": "dokument", "document_send": "dokument",
    "remarkable_note": "remarkable", "remarkable_attachment": "remarkable", "remarkable_page": "remarkable", "remarkable_sheet": "remarkable",
    "message_send": "nachricht", "message_announce": "nachricht", "pc_send": "nachricht",
    "memory_save": "merken", "memory_forget": "merken",
    "tasks_add": "aufgabe", "tasks_change": "aufgabe",
    "calendar_change": "termin", "speaker_volume": "geraet",
    "agent_change": "aenderung", "home_rule_delete": "aenderung", "proactive_pause": "aenderung", "undo_last": "aenderung",
}
# kind -> the tool that knows what was done earlier (R4 "Nein zu eigenem Tun", thread "Einstellungen optimieren")
STATUS = {"dokument": "document_status", "remarkable": "remarkable_sent", "erinnerung": "reminder_list",
          "aufgabe": "tasks_show", "termin": "calendar_events"}

FAILED = re.compile(r"(?i)\s*(not done|not proposed|unknown tool|unknown action|search failed|invalid|no query|"
                    r"no command|nicht ausgeführt|fehler|error|failed)")


WAIT = re.compile(r"(?i)\s*not (saved|done) yet")   # a proposal the person still has to confirm (chat_tools.py)


def failed(result):
    """True when a tool result says it did not work (the same fixed words as Logs → Anfragen)."""
    return not (isinstance(result, str) and result.strip()) or bool(FAILED.match(result))


def act(name, args, result):
    """The register entry for one tool call that changes something, or None for a reading tool:
    {"art", "ok", "wait", "what"}. wait: only proposed, the person confirms it first (then nothing is said instead)."""
    if name not in KIND:
        return None
    wait = isinstance(result, str) and bool(WAIT.match(result))
    return {"art": KIND[name], "ok": not wait and not failed(result), "wait": wait, "what": what(args)}


def what(args):
    """A short name of what was acted on, from the tool's own arguments (a device), else ""."""
    args = args if isinstance(args, dict) else {}
    for k in ("name", "device", "entity", "entity_id", "target", "title"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            v = re.sub(r"[^\w .\-äöüÄÖÜß]", "", v.split(".")[-1] if k == "entity_id" else v).replace("_", " ").strip()
            return v[:40]
    return ""


_DONE = r"(?:habe|hab|wurde|ist|sind|wurden|i(?:'| ha)ve|has been|have been|was|is now)"
# a claimed deed: the done form of a verb of that kind (never "soll ich …", "ich kann …", "möchtest du …")
CLAIMS = {
    "geraet": r"\b(?:ist|sind|is|are)\s+(?:jetzt|nun|now)\s+(?:an|aus|eingeschaltet|ausgeschaltet|on|off)\b"
              r"|\b(?:habe|hab|i(?:'| ha)ve)\b[^.!?]{0,60}\b(?:eingeschaltet|ausgeschaltet|angeschaltet|abgeschaltet|"
              r"angemacht|ausgemacht|gestellt|geschaltet|gedimmt|geöffnet|geschlossen|turned (?:on|off)|switched)\b"
              r"|\b(?:der|die|das)\s+\w+\s+(?:ist|sind)\s+(?:jetzt\s+)?(?:aus|an)\s*[.!]",
    "erinnerung": r"\b(?:erinnere dich|erinnerung (?:ist |wurde )?(?:gestellt|eingerichtet|gelöscht)|"
                  r"i(?:'ll| will) remind you|reminder (?:is |has been )?set)\b",
    "termin": r"\b" + _DONE + r"\b[^.!?]{0,60}\b(?:eingetragen|in den kalender|added to (?:your|the) calendar)\b"
              r"|\bsteht (?:jetzt )?(?:in deinem|im) kalender\b",
    "mail_entwurf": r"\b(?:entwurf|draft)\b[^.!?]{0,40}\b(?:erstellt|gespeichert|angelegt|created|saved)\b"
                    r"|\b" + _DONE + r"\b[^.!?]{0,40}\b(?:entwurf|draft)\b[^.!?]{0,20}\b(?:erstellt|geschrieben|angelegt)\b",
    "dokument": r"\b" + _DONE + r"\b[^.!?]{0,60}\b(?:dokument|präsentation|tabelle|brief|datei|document|presentation)"
                r"\b[^.!?]{0,40}\b(?:erstellt|angelegt|geschickt|gesendet|created|sent)\b"
                r"|\b(?:dokument|präsentation|tabelle|brief|document|presentation)\b[^.!?]{0,30}\b(?:habe|hab|ist|wurde|is|was)"
                r"\b[^.!?]{0,30}\b(?:erstellt|angelegt|geschickt|gesendet|fertig|created|sent|ready)\b",
    "remarkable": r"\b(?:liegt|liegen|ist|wurde|habe)\b[^.!?]{0,40}\b(?:auf (?:dem|deinem|dein) remarkable|"
                  r"aufs remarkable|on (?:your|the) remarkable)\b",
    "nachricht": r"\b(?:nachricht|durchsage|message)\b[^.!?]{0,40}\b(?:gesendet|geschickt|verschickt|sent)\b"
                 r"|\b" + _DONE + r"\b[^.!?]{0,60}\b(?:nachricht|durchsage|message)\b[^.!?]{0,30}\b(?:gesendet|geschickt|"
                 r"verschickt|sent)\b|\b(?:habe|hab)\b[^.!?]{0,40}\b(?:ausgerichtet|durchgesagt)\b",
    "merken": r"\b(?:habe ich mir gemerkt|hab ich mir gemerkt|ich merke mir|merk ich mir|habe ich vergessen|"
              r"i(?:'ll| will) remember|i(?:'ve| have) forgotten)\b",
    "aenderung": r"\b" + _DONE + r"\b[^.!?]{0,60}\b(?:pausiert|gelöscht|rückgängig gemacht|wiederhergestellt|"
                 r"fortgesetzt|paused|deleted|undone|restored)\b",
    "aufgabe": r"\b" + _DONE + r"\b[^.!?]{0,60}\b(?:auf die liste|zur liste|auf deine liste|to (?:your|the) list)\b",
}
CLAIMS = {k: re.compile(v, re.I) for k, v in CLAIMS.items()}
DONE_ANY = re.compile(r"^\s*(?:erledigt|fertig|gemacht|done|okay,? erledigt)\s*[.!]?\s*$", re.I)
NOT_CLAIM = re.compile(r"(?i)\b(?:soll ich|möchtest du|willst du|kann ich|könnte ich|shall i|should i|do you want|"
                       r"nicht|kein|keine|not|never|wenn du)\b")


def claims(text):
    """The kinds of deed a finished sentence says were done ("" for a bare "Erledigt.")."""
    if not text or NOT_CLAIM.search(text):
        return set()
    found = {k for k, rx in CLAIMS.items() if rx.search(text)}
    return found or ({""} if DONE_ANY.match(text) else set())


def check(text, acts, offered, looked=False):
    """The kinds a sentence claims without a tool of that kind having worked in this answer: the sentence is held back
    when this is not empty. acts: [{"art", "ok", "what"}] of this answer; offered: names of the tools offered. A bare
    "Erledigt." counts only when something that changes things was offered and nothing worked; looked: a reading tool
    worked in this answer, then "Fertig." may just end a look-up and is said."""
    kinds = claims(text)
    done = {a["art"] for a in acts if a.get("ok")}
    if "" in kinds:
        writes = any(n in KIND for n in offered or ())
        return [""] if writes and not done and not looked else []
    if kinds & done:   # in doubt the sentence is said: one of the deeds it names did work
        return []
    return sorted(kinds)


SENTENCE = {
    "failed": {"de": "Das hat nicht geklappt: {what}.", "en": "That did not work: {what}."},
    "missing": {"de": "Das habe ich nicht ausgeführt.", "en": "I did not do that."},
}
WHAT = {"geraet": ("das Gerät", "the device"), "erinnerung": ("die Erinnerung", "the reminder"),
        "termin": ("der Termin", "the appointment"), "mail_entwurf": ("der Mail-Entwurf", "the mail draft"),
        "dokument": ("das Dokument", "the document"), "remarkable": ("das reMarkable", "the reMarkable"),
        "nachricht": ("die Nachricht", "the message"), "merken": ("das Merken", "remembering it"),
        "aufgabe": ("die Aufgabe", "the task"), "aenderung": ("die Änderung", "the change"), "": ("das", "that")}


def sentence(art, status, en=False, what=""):
    """The one honest sentence instead of held back claims: status "failed" (a tool of that kind ran and failed) or
    "missing" (none ran). what: a short name the panel took from the tool's arguments (a device), else the kind."""
    lang = "en" if en else "de"
    if status == "failed":
        name = (what or WHAT.get(art, WHAT[""])[1 if en else 0])[:60]
        return SENTENCE["failed"][lang].format(what=name)
    return SENTENCE["missing"][lang]


# „Beschwerde erkennen“ (features einordnungklage, plan systemone/einschaetzung.md 6): the deeds of a profile's last
# answer stay in memory for LAST_S (kind, worked, short name; never a file). When the next message of that profile
# says it did not work (the fixed list COMPLAINT, else qwen38's /v1/systemone in chat_turn.py), the panel only
# lets the model look: the tools that change things of that kind are not offered in this answer.
LAST_S = 600
COMPLAINT = re.compile(r"(?i)^\W*(?:nein,?\s*|hm+,?\s*|äh+,?\s*)?(?:(?:das|der|die)\s+\w+\s+|(?:das|es|er|sie)\s+)?(?:"
                       r"geht\s+(?:immer\s+)?(?:noch\s+)?nicht|funktioniert\s+(?:immer\s+)?(?:noch\s+)?nicht|"
                       r"hat\s+(?:aber\s+)?nicht\s+geklappt|klappt\s+(?:immer\s+)?(?:noch\s+)?nicht|"
                       r"(?:ist|sind|bleibt|bleiben)\s+(?:aber\s+)?(?:immer\s+)?noch\s+(?:an|aus|offen|zu)|"
                       r"(?:ist|sind)\s+(?:aber\s+)?(?:gar\s+)?nicht\s+(?:an|aus|offen|zu|angegangen|ausgegangen)|"
                       r"(?:it|that)\s+(?:still\s+)?(?:does\s*n[o']?t|did\s*n[o']?t)\s+work|(?:it'?s|it\s+is)\s+still\s+(?:on|off))"
                       r"\b[^?]{0,60}$")
# the person asks for it again in the same message ("… mach es nochmal aus"): then nothing is locked
RETRY = re.compile(r"(?i)\b(?:nochmal|noch\s+einmal|erneut|wieder|again|try|retry|mach|schalte?|stell|probier\w*|turn)\b")
_last = {}            # uid -> (time, [{"art", "ok", "what"}])


def note_last(uid, acts, now=None):
    """The deeds of the answer just finished (only those done or tried, never proposals); none clears it."""
    if not uid:
        return
    now = time.time() if now is None else now
    keep = [{"art": a["art"], "ok": bool(a.get("ok")), "what": str(a.get("what") or "")[:40]}
            for a in acts or [] if isinstance(a, dict) and a.get("art") in WHAT and not a.get("wait")][:5]
    if keep:
        _last[uid] = (now, keep)
    else:
        _last.pop(uid, None)
    for k in [k for k, (t, _) in _last.items() if now - t > LAST_S]:
        _last.pop(k, None)


def last(uid, now=None):
    """The deeds of the profile's last answer within LAST_S, else []."""
    now = time.time() if now is None else now
    t, acts = _last.get(uid, (0, []))
    return acts if now - t <= LAST_S else []


def complaint(text):
    """The fixed list: the whole (short) message says the last deed did not work ("geht immer noch nicht")."""
    t = str(text or "").strip()
    return 0 < len(t) <= 120 and bool(COMPLAINT.match(t))


def complaint_note(acts, en=False):
    """The fixed note for the model in an answer to a complaint (never the person's words)."""
    a = acts[-1]
    name = (a["what"] or WHAT.get(a["art"], WHAT[""])[1 if en else 0])[:40]
    if en:
        return (f"Complaint: the user says the last deed did not work ({name}; the tool reported "
                f"{'success' if a['ok'] else 'a failure'}). Look up the current state first and say it honestly. Change "
                "something only when the user asks for it in this message; otherwise offer to try again.")
    return (f"Beschwerde: Der Nutzer sagt, das Letzte habe nicht geklappt ({name}; das Werkzeug meldete "
            f"{'Erfolg' if a['ok'] else 'einen Fehler'}). Sieh zuerst nach, wie der Stand ist, und sag ihn ehrlich. "
            "Ändere nur etwas, wenn der Nutzer in dieser Nachricht ausdrücklich darum bittet; sonst biete an, es noch "
            "einmal zu versuchen.")


def locked(acts, text=""):
    """The tools that change things of the kinds of these deeds: not offered in the answer to a complaint, unless the
    message itself asks for it again (RETRY)."""
    if RETRY.search(str(text or "")):
        return set()
    arts = {a["art"] for a in acts}
    return {name for name, art in KIND.items() if art in arts}


# Live page: how often the checks stepped in today (numbers only, never a sentence)
_live = {"day": "", "held": 0, "loop": 0, "klage": 0}


def note_live(what, now=None):
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    if _live["day"] != day:
        _live.update(day=day, held=0, loop=0, klage=0)
    _live[what] = _live.get(what, 0) + 1


def for_live(now=None):
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    return {"held": _live["held"], "loop": _live["loop"], "klage": _live.get("klage", 0)} if _live["day"] == day \
        else {"held": 0, "loop": 0, "klage": 0}
