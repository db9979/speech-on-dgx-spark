"""Ändern per Sprache (plan werkzeug-abdeckung.md, Paket 6; Dominik 2026-10-13 „1-7 umsetzen“): what so far only
had a button on a page.

1. speaker_volume: „Mach den Lautsprecher in der Küche leiser“, „Lautstärke auf 40“. Only the profile's own speakers
   (esp32.py, the same as Ich → Lautsprecher); done at once like switching a device, the old volume kept for undo.
2. proactive_pause: „Melde dich heute nicht mehr“, „Du darfst dich wieder melden“. The same pause as „nicht jetzt“
   after a note (proactive.feedback), here until midnight or for some hours; never more than 24 hours.
3. undo_last: „Mach das rückgängig“. The last deeds of this profile (reminder set, list entry added, fact remembered,
   appointment entered, device switched on or off, speaker volume, pause, scheduled job changed, smart home rule
   deleted) stay in memory for UNDO_KEEP seconds (never a file: a restart forgets them, the person then uses the
   page). The tool only proposes; the person's yes in the next message undoes it (answer). Its own switch
   (features „rueckgaengig“, the admin's, off; it holds for every profile); the others go with their function's switches.

Every change goes through the Notaus (notaus.stop) and is locked after outside text (chat.py, "changes"). Logs carry
fixed words only."""
import collections
import datetime
import re
import time

import features
import notaus
import profiles

UNDO_KEEP = 1800
UNDO_MAX = 5
PENDING_SECONDS = 180
STEP = 15                       # „lauter“ / „leiser“ without a number
MAX_PAUSE_H = 24
_undo = collections.defaultdict(list)   # uid -> [{"kind", "data", "label", "t"}], newest last
_pending = {}                            # uid -> {"entry", "src", "t"}

VOLUME_WORDS = re.compile(r"(?i)\b(lauter|leiser|lautstärke\w*|volume|louder|quieter|softer)\b")
PAUSE_WORDS = re.compile(r"(?i)\bmeld\w* dich\b.{0,40}\bnicht mehr\b|\bkeine meldungen\b.{0,30}\b(mehr|heute)\b|"
                         r"\b(darfst|kannst) dich wieder melden\b|\bmeld\w* dich wieder\b|\bstop (the )?notes\b|"
                         r"\b(no more|resume) notes\b")
UNDO_WORDS = re.compile(r"(?i)\brückgängig\b|\bnimm (das|es) zurück\b|\bmach (das|es) wieder weg\b|\bundo\b")
STOP_WORDS = set("""der die das den dem des ein eine im in am an auf zur zum vom von bei mir mich mein meine meinen
bitte mal etwas bisschen noch ein lautsprecher speaker box auf""".split())

VOLUME_TOOL = {"type": "function", "function": {
    "name": "speaker_volume",
    "description": "Set the volume of one of the user's own speakers: louder, quieter or a value 0-100.",
    "parameters": {"type": "object", "properties": {
        "speaker": {"type": "string", "description": "the speaker's name or room; empty when the user has only one"},
        "change": {"type": "string", "enum": ["louder", "quieter", "set"]},
        "level": {"type": "integer", "description": "0-100, only with change 'set'"}}, "required": ["change"]}}}
PAUSE_TOOL = {"type": "function", "function": {
    "name": "proactive_pause",
    "description": "Pause the notes the Spark sends by itself ('Melde dich heute nicht mehr') or end the pause "
                   "('Du darfst dich wieder melden').",
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["pause", "resume"]},
        "hours": {"type": "integer", "description": "pause for this many hours (1-24); empty: until midnight"}},
        "required": ["action"]}}}
UNDO_TOOL = {"type": "function", "function": {
    "name": "undo_last",
    "description": "Propose to undo what the Spark did last for the user (a reminder, list entry, remembered fact, "
                   "appointment, switched device, speaker volume, pause, changed job or deleted rule). Only proposes: "
                   "the user must say yes in the next message.",
    "parameters": {"type": "object", "properties": {
        "what": {"type": "string", "description": "optional words naming which deed, e.g. 'Erinnerung'"}}}}}
CHANGES = {"speaker_volume", "proactive_pause", "undo_last"}   # all three change something (locked after outside text)
HINT = {"speaker_volume": "speaker_volume stellt die Lautstärke eigener Lautsprecher; sag danach das Ergebnis.",
        "proactive_pause": "proactive_pause pausiert die Meldungen von selbst oder hebt die Pause auf.",
        "undo_last": "undo_last schlägt vor, die letzte Tat rückgängig zu machen; lies den Satz aus dem Ergebnis vor, "
                     "erst das Ja macht es rückgängig."}


# ---------------------------------------------------------------- undo register
def note(uid, kind, data, label):
    """One deed that can be undone (fixed kinds; label: what the person hears, cut short)."""
    if not uid:
        return
    items = [x for x in _undo[uid] if time.time() - x["t"] < UNDO_KEEP]
    items.append({"kind": kind, "data": data, "label": re.sub(r"[\x00-\x1f<>`]", " ", str(label))[:120], "t": time.time()})
    _undo[uid] = items[-UNDO_MAX:]


def note_tool(uid, name, args, result):
    """chat.py, after a tool that worked: the deeds a later „Mach das rückgängig“ can take back."""
    args = args if isinstance(args, dict) else {}
    if name == "reminder_set":
        hit = next((x for x in sorted(profiles.reminders(uid), key=lambda x: -x.get("due", 0))
                    if x["text"] == (str(args.get("text", "")).strip() or "Timer")[:200]), None)
        if hit:
            note(uid, "reminder", {"id": hit["id"]}, f"die Erinnerung „{hit['text']}“ löschen")
    elif name == "memory_save":
        text = re.sub(r"\s+", " ", str(args.get("fact", ""))).strip().lower()
        hit = next((x for x in profiles.memory(uid) if text and x["text"].lower() == text[:profiles.MAX_FACT_LEN]), None)
        if hit:
            note(uid, "memory", {"id": hit["id"]}, f"die Notiz „{hit['text'][:60]}“ vergessen")
    elif name == "tasks_add" and isinstance(result, str) and result.startswith("Auf die Liste"):
        import tasks
        lst = args.get("list") if args.get("list") in tasks.LISTS else tasks.which(args.get("list"))
        items = args.get("items")
        items = [items] if isinstance(items, str) else [str(x) for x in items or []][:20]
        if items:
            note(uid, "tasks", {"list": lst, "items": items}, f"„{', '.join(items)[:60]}“ von der Liste nehmen")
    elif name == "home_assistant_action":
        eid = str(args.get("entity_id") or args.get("entity") or args.get("device") or args.get("name") or "")
        service = str(args.get("service") or args.get("command") or args.get("action") or "").split(".")[-1].lower()
        back = REVERSE.get(service)
        if eid and back:
            dev = eid.split(".")[-1].replace("_", " ")[:40]
            note(uid, "ha", {"eid": eid[:200], "service": back}, f"{dev} wieder {UNDO_SAYS[back]}")


REVERSE = {"turn_on": "turn_off", "turn_off": "turn_on", "open_cover": "close_cover", "close_cover": "open_cover"}
UNDO_SAYS = {"turn_on": "einschalten", "turn_off": "ausschalten", "open_cover": "öffnen", "close_cover": "schließen"}


def last(uid, words=""):
    items = [x for x in _undo.get(uid, []) if time.time() - x["t"] < UNDO_KEEP]
    want = [w for w in re.findall(r"\w{3,}", str(words or "").lower()) if w not in STOP_WORDS][:4]
    if want:
        items = [x for x in items if any(w in x["label"].lower() or w.startswith(KIND_WORD.get(x["kind"], "-"))
                                          for w in want)] or items
    return items[-1] if items else None


KIND_WORD = {"reminder": "erinner", "memory": "notiz", "tasks": "list", "ha": "gerät", "volume": "laut",
             "pause": "meld", "plan": "auftr", "rule": "regel", "calendar": "termin",
             "calendar_ics": "termin"}


# ---------------------------------------------------------------- 1: speaker volume
def my_speakers(uid):
    import esp32
    devs = esp32._devices()
    return [(c["device"], cid, devs[c["device"]].get("name") or "Lautsprecher", c.get("volume"))
            for cid, c in esp32.clients().items() if devs.get(c.get("device"), {}).get("user") == uid]


async def set_volume(uid, did, v):
    import esp32
    notaus.stop("aktion", uid)
    cid, c = esp32.by_device(did)
    if not c or esp32._devices().get(did, {}).get("user") != uid:
        raise ValueError("den Lautsprecher gibt es nicht mehr")
    esp32._update(lambda d: d["clients"][cid].update(volume=v))
    s = esp32._live.get(did)
    if s:
        try:
            await s.set_volume(v)      # connected: at once, else at its next connection
        except Exception:
            pass
    return bool(s)


async def volume(uid, args):
    mine = my_speakers(uid)
    if not mine:
        return "Not done: this profile has no own speaker (Ich → Lautsprecher). Say so."
    words = [w for w in re.findall(r"\w{3,}", str(args.get("speaker") or "").lower()) if w not in STOP_WORDS]
    hits = [m for m in mine if all(w in m[2].lower() for w in words)] if words else mine
    if len(hits) != 1:
        names = ", ".join(f"„{m[2][:40]}“" for m in mine[:8])
        return f"Not done: {'no' if not hits else 'more than one'} speaker fits. The own speakers are {names}. Ask which."
    did, _, name, old = hits[0]
    old = old if isinstance(old, int) else 50
    change = args.get("change")
    if change == "set":
        try:
            v = int(args.get("level"))
        except (TypeError, ValueError):
            return "Not done: give a level 0-100."
    else:
        v = old + (STEP if change == "louder" else -STEP)
    v = max(0, min(100, v))
    try:
        live = await set_volume(uid, did, v)
    except Exception as e:
        return f"Not done: {e}"
    note(uid, "volume", {"device": did, "volume": old}, f"die Lautstärke von „{name[:40]}“ wieder auf {old} stellen")
    print(f"aendern: lautstaerke {old} -> {v} {'sofort' if live else 'beim naechsten verbinden'}", flush=True)
    return (f"Volume of '{name[:40]}' set from {old} to {v}" + ("" if live else " (the speaker is offline; it takes the "
            "volume when it connects again)") + ". Say so in one short sentence.")


# ---------------------------------------------------------------- 2: pause the notes
def pause(uid, args, tz=None):
    import proactive
    notaus.stop("aktion", uid)
    if args.get("action") == "resume":
        before = proactive.state(uid).get("pause_until", 0)
        proactive.feedback(uid, "", "resume")
        if before > time.time():
            note(uid, "pause", {"until": before}, "die Pause der Meldungen wieder einschalten")
        print("aendern: meldungen pause aus", flush=True)
        return "Done: the Spark may speak up by itself again. Say so in one short sentence."
    try:
        hours = int(args.get("hours") or 0)
    except (TypeError, ValueError):
        hours = 0
    if hours > 0:
        until = time.time() + min(hours, MAX_PAUSE_H) * 3600
    else:
        import chat
        zone = chat.user_zone(tz or profiles.settings(uid).get("tz", ""))
        now = datetime.datetime.now(zone)
        until = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    proactive._mut(uid, lambda st: st.update(pause_until=until))
    note(uid, "pause", {"until": 0}, "die Pause der Meldungen aufheben")
    print(f"aendern: meldungen pause {round((until - time.time()) / 3600, 1)} h", flush=True)
    end = datetime.datetime.fromtimestamp(until).strftime("%H:%M")
    return f"Done: no notes by itself until {'midnight' if hours <= 0 else end}. Say so in one short sentence."


# ---------------------------------------------------------------- 3: undo
async def undo(uid, entry, ctx):
    """Carries out the undo after the yes; returns the checked result in German."""
    notaus.stop("aktion", uid)
    k, d = entry["kind"], entry["data"]
    if k == "reminder":
        n = profiles.remove_reminders(uid, {d["id"]})
        return "Erinnerung gelöscht." if n else "Die Erinnerung war schon weg."
    if k == "memory":
        n = profiles.forget(uid, fact_id=d["id"])
        return "Notiz vergessen." if n else "Die Notiz war schon weg."
    if k == "tasks":
        import tasks
        picked = tasks.match(await tasks.items(uid, d["list"]), d["items"])
        n = await tasks.change(uid, d["list"], picked, "delete") if picked else 0
        return f"{n} Einträge von der Liste genommen." if n else "Die Einträge standen nicht mehr auf der Liste."
    if k == "ha":
        if not ctx.get("ha"):
            raise ValueError("Home Assistant ist hier nicht verbunden")
        if ctx.get("ha_code") and not ctx.get("ha_code_ok"):
            raise ValueError("das Codewort fehlt; sag „Ja“ mit dem Codewort")
        import homeassistant
        ok, result = await homeassistant.action(ctx["ha"], d["eid"], d["service"])
        if not ok:
            raise ValueError("Home Assistant: " + str(result)[:120])
        return "Rückgängig gemacht (von Home Assistant bestätigt)."
    if k == "volume":
        await set_volume(uid, d["device"], d["volume"])
        return f"Lautstärke wieder auf {d['volume']}."
    if k == "pause":
        import proactive
        proactive._mut(uid, lambda st: st.update(pause_until=d["until"]))
        return "Meldungen wieder pausiert." if d["until"] > time.time() else "Die Pause ist aufgehoben."
    if k == "plan":
        import agent
        if d.get("restore"):
            agent.mutate(uid, lambda x: x["plans"].append(d["restore"]) if len(x["plans"]) < agent.MAX_PLANS
                         and all(p["id"] != d["restore"]["id"] for p in x["plans"]) else None)
            return "Geplanter Auftrag wiederhergestellt."
        agent.change_plan(uid, d["id"], d["back"])
        return "Geplanter Auftrag wie vorher."
    if k == "rule":
        import proactive
        have = proactive.rules(uid)
        if any(r.get("id") == d["rule"].get("id") for r in have):
            return "Die Regel gibt es schon wieder."
        proactive._save_rules(uid, have + [d["rule"]])
        return "Regel wiederhergestellt."
    if k == "calendar":
        import calendars
        await calendars.delete_href(uid, d["account"], d["href"])
        return "Termin wieder aus dem Kalender gelöscht (vom Kalender-Server bestätigt)."
    if k == "calendar_ics":
        import calendars
        await calendars.put_ics(uid, d["account"], d["href"], d["ics"], new=d.get("deleted"))
        return "Termin wieder wie vorher (vom Kalender-Server bestätigt)."
    raise ValueError("unbekannte Art")


def pending(uid):
    p = _pending.get(uid)
    if p and time.time() - p["t"] > PENDING_SECONDS:
        _pending.pop(uid, None)
        return None
    return p


def drop_pending(uid):
    _pending.pop(uid, None)


async def answer(ctx, latest):
    """The person's yes or no to an undo proposal of this conversation."""
    import calendars
    who = ctx.get("who")
    if not who or not ctx.get("own"):
        return None
    p = pending(who["id"])
    if not p or p.get("src") != ctx.get("src", ""):
        return None
    _pending.pop(who["id"], None)
    label = p["entry"]["label"]
    # „Ja, <Codewort>“ for a device behind the code word: the code word is checked by chat_turn (ha_code_ok)
    coded = p["entry"]["kind"] == "ha" and ctx.get("ha_code_ok") and re.match(r"(?i)^\W*ja\b", str(latest or ""))
    if not calendars.confirms(latest) and not coded:
        return {"call": {"name": "Rückgängig (abgelehnt)", "args": label, "result": "nicht ausgeführt"},
                "system": f"Rückgängig: „{label}“ wurde NICHT ausgeführt, weil der Nutzer nicht zugestimmt hat."}
    try:
        note_ = await undo(who["id"], p["entry"], ctx)
        _undo[who["id"]] = [x for x in _undo[who["id"]] if x is not p["entry"] and x["t"] != p["entry"]["t"]]
        print(f"aendern: rueckgaengig art={p['entry']['kind']} ok", flush=True)
    except Exception as e:
        note_ = f"NICHT rückgängig gemacht: {str(e)[:160]}"
        print(f"aendern: rueckgaengig art={p['entry']['kind']} fehler {type(e).__name__}", flush=True)
    return {"call": {"name": "Rückgängig (bestätigt)", "args": label, "result": note_},
            "system": "Rückgängig: " + note_ + " Sag dem Nutzer genau das in einem kurzen Satz."}


# ---------------------------------------------------------------- offer and run
def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    uid, text = who["id"], str(ctx.get("text") or "")
    tools = []
    if VOLUME_WORDS.search(text) and features.allowed("esp32", uid) and my_speakers(uid):
        tools.append(VOLUME_TOOL)
    if PAUSE_WORDS.search(text) and features.allowed("proactive", uid):
        tools.append(PAUSE_TOOL)
    if UNDO_WORDS.search(text) and features.allowed("rueckgaengig", uid) and last(uid):
        tools.append(UNDO_TOOL)
    if not tools:
        return None
    names = {t["function"]["name"] for t in tools}
    return {"tools": tools, "changes": names & CHANGES, "keep": names, "hint": " ".join(HINT[n] for n in sorted(names)),
            "filler": {n: ("Mach ich.", "On it.") for n in names}}


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    args = args if isinstance(args, dict) else {}
    if not uid:
        return "Not done: only for a profile."
    try:
        if name == "speaker_volume" and features.allowed("esp32", uid):
            return await volume(uid, args)
        if name == "proactive_pause" and features.allowed("proactive", uid):
            return pause(uid, args, ctx.get("tz"))
    except Exception as e:     # the Notaus (notaus.NotausAktiv) or a vanished device
        return f"Not done: {str(e)[:160]}"
    if name == "undo_last" and features.allowed("rueckgaengig", uid):
        entry = last(uid, args.get("what"))
        if not entry:
            return "Nicht vorgeschlagen: es gibt nichts, was sich rückgängig machen lässt. Sag das so."
        _pending[uid] = {"entry": entry, "src": ctx.get("src", ""), "t": time.time()}
        print(f"aendern: rueckgaengig vorgeschlagen art={entry['kind']}", flush=True)
        return (f"Noch NICHT rückgängig gemacht. Frag den Nutzer: „Soll ich {entry['label']}?“ Erst sein Ja in der "
                "nächsten Nachricht macht es rückgängig.")
    return "Not done: this function is off for this profile."


async def briefing(uid, zone=None):
    return ""
