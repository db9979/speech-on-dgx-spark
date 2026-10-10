"""Tasks and the shopping list per profile: "Setz Milch auf die Einkaufsliste", "Was steht auf meiner Liste?".

Off until the admin allows it (chat.tasks) and the profile switches it on (tasks_on). Two lists,
"einkauf" (Einkaufsliste) and "aufgaben" (Aufgaben). Each list lives in one of two places:

    Spark       the panel keeps the list itself. An iPhone shortcut fetches new entries with the
                profile's device key (POST /api/tasks/inbox) and puts them into Apple's Reminders,
                because Apple's Reminders cannot be reached over CalDAV any more (way A).
    CalDAV      a task list (VTODO collection) of one of the profile's calendar accounts:
                Nextcloud, mailbox.org, Radicale ... (way B).

Adding happens at once; ticking off and deleting only after the person's "Ja" in the next message
(the panel does it, not the model). After outside text (web, mail ...) nothing is added.

    USERS_DIR/<uid>/tasks.json   {"items": [{id, list, text, t, sent?}],
                                  "targets": {"einkauf": {"acc", "url", "name"} | absent}}
"""
import datetime
import difflib
import json
import os
import re
import threading
import time
import uuid as uuidlib

import httpx
import icalendar

import calendars
import hintergrund
import netguard
import notaus
import profiles
import features

LISTS = {"einkauf": ("Einkaufsliste", "shopping list"), "aufgaben": ("Aufgaben", "tasks")}
MAX_ITEMS = 200
KEEP_SENT = 14 * 86400      # entries the iPhone took stay hidden this long (so a second fetch sends nothing twice)
PENDING_SECONDS = 15 * 60
_lock = threading.Lock()


def admin_on():
    return features.admin_on("tasks")


def usable(uid):
    return features.allowed("tasks", uid)


def _file(uid):
    return profiles._path(uid, "tasks.json")


def _load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    now = time.time()
    items = [x for x in d.get("items") or [] if isinstance(x, dict) and x.get("list") in LISTS and x.get("text")
             and not (x.get("sent") and now - x["sent"] > KEEP_SENT)]
    targets = {k: v for k, v in (d.get("targets") or {}).items()
               if k in LISTS and isinstance(v, dict) and v.get("url") and v.get("acc")}
    return {"items": items, "targets": targets}


def _save(uid, d):
    profiles._write(_file(uid), {"items": d["items"][-MAX_ITEMS:], "targets": d["targets"]})


def clean(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip(" .,;:-–")
    return text[:120]


def which(name):
    """The list a word means ("Einkaufsliste", "einkaufen", "todo" ...); default the shopping list."""
    n = str(name or "").lower()
    if re.search(r"aufgab|todo|to-do|erledig|task", n):
        return "aufgaben"
    return "einkauf"


# ---------------------------------------------------------------- CalDAV task lists (way B)
def _account(uid, acc):
    return next((x for x in calendars.get(uid)["calendars"] if x["id"] == acc), None)


def _client(acc):
    auth = (acc["user"], acc.get("password", "")) if acc.get("user") else None
    return netguard.client(netguard.USER, origin=acc["url"], timeout=httpx.Timeout(20, connect=8), auth=auth,
                           follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"},
                           seen=hintergrund.tracker("cal", acc.get("id")) if acc.get("id") else None)


async def collections(uid):
    """[{"acc", "acc_name", "url", "name"}] of task lists in the profile's CalDAV calendar accounts."""
    out, errors = [], []
    for acc in calendars.get(uid)["calendars"]:
        if re.match(r"webcals?://", acc["url"], re.I) or re.search(r"\.ics(\?|$)", acc["url"], re.I):
            continue
        try:
            async with _client(acc) as c:
                for url, name in await calendars._calendars(c, acc["url"], comp="VTODO"):
                    out.append({"acc": acc["id"], "acc_name": acc.get("name", ""), "url": url, "name": name or url})
        except Exception as e:
            errors.append(f"{acc.get('name', '')}: {e}")
    return out, errors


async def _todos(c, url):
    """[(href, etag, Todo)] of the collection's open tasks."""
    q = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
         '<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
         '<c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>')
    r = await c.request("REPORT", url, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    if r.status_code == 401:
        raise ValueError("the server rejects the user name or password (401)")
    if r.status_code != 207:
        raise ValueError(f"the server answered {r.status_code}")
    root = calendars._xml(r.content)
    out = []
    for resp in root.findall("d:response", calendars.NS) if root is not None else []:
        href = calendars._href(url, resp.find("d:href", calendars.NS))
        data = resp.findtext("d:propstat/d:prop/c:calendar-data", "", calendars.NS)
        etag = resp.findtext("d:propstat/d:prop/d:getetag", "", calendars.NS)
        if not href or "BEGIN:VCALENDAR" not in data:
            continue
        try:
            cal = icalendar.Calendar.from_ical(data)
        except ValueError:
            continue
        for todo in cal.walk("VTODO"):
            if str(todo.get("STATUS", "")).upper() in ("COMPLETED", "CANCELLED") or todo.get("COMPLETED"):
                continue
            out.append((href, etag, cal, todo))
    return out


def _ical(text):
    cal = icalendar.Calendar()
    cal.add("prodid", "-//speech-on-dgx-spark//DE")
    cal.add("version", "2.0")
    todo = icalendar.Todo()
    uid_text = f"{uuidlib.uuid4().hex}@speech-spark"
    todo.add("uid", uid_text)
    todo.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
    todo.add("summary", text)
    todo.add("status", "NEEDS-ACTION")
    cal.add_component(todo)
    return uid_text, cal.to_ical()


# ---------------------------------------------------------------- the lists
async def items(uid, lst):
    """[{"id", "text"}] of the list's open entries ("id" is the CalDAV address on way B)."""
    d = _load(uid)
    tgt = d["targets"].get(lst)
    if not tgt:
        return [{"id": x["id"], "text": x["text"]} for x in d["items"] if x["list"] == lst and not x.get("sent")]
    acc = _account(uid, tgt["acc"])
    if not acc:
        raise ValueError("the calendar account of this list was removed")
    async with _client(acc) as c:
        return [{"id": href, "etag": etag, "text": str(todo.get("SUMMARY", "")).strip()}
                for href, etag, _, todo in await _todos(c, tgt["url"]) if str(todo.get("SUMMARY", "")).strip()]


def sent_count(uid, lst):
    return sum(1 for x in _load(uid)["items"] if x["list"] == lst and x.get("sent"))


async def add(uid, lst, texts):
    """Adds the entries; returns the ones added (the same text twice is added once)."""
    notaus.stop("aktion")   # the Notaus holds every action off (notaus.py)
    seen, out = set(), []
    for t in (clean(x) for x in texts):
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    texts = out[:20]
    if not texts:
        return []
    d = _load(uid)
    tgt = d["targets"].get(lst)
    if tgt:
        acc = _account(uid, tgt["acc"])
        if not acc:
            raise ValueError("the calendar account of this list was removed")
        async with _client(acc) as c:
            for t in texts:
                uid_text, body = _ical(t)
                r = await c.put(tgt["url"].rstrip("/") + f"/{uid_text.split('@')[0]}.ics", content=body,
                                headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
                if r.status_code not in (200, 201, 204):
                    raise ValueError(f"the server answered {r.status_code}")
        return texts
    with _lock:
        d = _load(uid)
        have = {x["text"].lower() for x in d["items"] if x["list"] == lst and not x.get("sent")}
        new = [t for t in texts if t.lower() not in have]
        d["items"] += [{"id": os.urandom(5).hex(), "list": lst, "text": t, "t": int(time.time())} for t in new]
        _save(uid, d)
    return texts


async def change(uid, lst, picked, action):
    """Ticks off ("done") or deletes ("delete") the picked entries [{"id", "etag"?, "text"}]; returns how many."""
    notaus.stop("aktion")   # the Notaus holds every action off (notaus.py)
    d = _load(uid)
    tgt = d["targets"].get(lst)
    if not tgt:
        ids = {x["id"] for x in picked}
        with _lock:
            d = _load(uid)
            n = sum(1 for x in d["items"] if x["id"] in ids)
            d["items"] = [x for x in d["items"] if x["id"] not in ids]
            _save(uid, d)
        return n
    acc = _account(uid, tgt["acc"])
    if not acc:
        raise ValueError("the calendar account of this list was removed")
    n = 0
    async with _client(acc) as c:
        now = {x[0]: x for x in await _todos(c, tgt["url"])}
        for p in picked:
            hit = now.get(p["id"])
            if not hit:
                continue
            href, etag, cal, todo = hit
            head = {"If-Match": etag} if etag else {}
            if action == "delete":
                r = await c.delete(href, headers=head)
            else:
                for k in ("STATUS", "COMPLETED", "PERCENT-COMPLETE"):
                    todo.pop(k, None)
                todo.add("status", "COMPLETED")
                todo.add("completed", datetime.datetime.now(datetime.timezone.utc))
                todo.add("percent-complete", 100)
                r = await c.put(href, content=cal.to_ical(),
                                headers=dict(head, **{"Content-Type": "text/calendar; charset=utf-8"}))
            if r.status_code in (200, 201, 204):
                n += 1
            else:
                raise ValueError(f"the server answered {r.status_code}")
    return n


def match(entries, wanted):
    """The entries the words mean: exact, contained or close (never a guess beyond that)."""
    out = []
    for w in wanted:
        w = clean(w).lower()
        if not w:
            continue
        hit = next((e for e in entries if e["text"].lower() == w), None) \
            or next((e for e in entries if w in e["text"].lower() or e["text"].lower() in w), None)
        if not hit:
            close = difflib.get_close_matches(w, [e["text"].lower() for e in entries], n=1, cutoff=0.75)
            hit = next((e for e in entries if close and e["text"].lower() == close[0]), None)
        if hit and hit not in out:
            out.append(hit)
    return out


def inbox(uid, lst, take):
    """Way A: the list's entries not yet handed to the iPhone; take=True marks them handed over."""
    with _lock:
        d = _load(uid)
        out = [x for x in d["items"] if x["list"] == lst and not x.get("sent")]
        if take and out:
            now = int(time.time())
            for x in out:
                x["sent"] = now
            _save(uid, d)
    return [x["text"] for x in out]


# ---------------------------------------------------------------- "Ja" before ticking off or deleting
def _pending_file(uid):
    return profiles._path(uid, "tasks-pending.json")


def pending(uid):
    try:
        with open(_pending_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and time.time() - d.get("t", 0) < PENDING_SECONDS else None
    except (OSError, ValueError):
        return None


def drop_pending(uid):
    try:
        os.remove(_pending_file(uid))
    except OSError:
        pass


def describe(p):
    what = "abhaken" if p["action"] == "done" else "löschen"
    return f"{', '.join('„' + x['text'] + '“' for x in p['items'])} auf der Liste {LISTS[p['list']][0]} {what}"


async def answer(ctx, latest):
    """The person's answer to a proposal from this conversation: {"call", "system"} or None."""
    who = ctx.get("who")
    if not who or not ctx.get("own"):
        return None
    p = pending(who["id"])
    if not p or p.get("src", ctx.get("src")) != ctx.get("src"):
        return None
    drop_pending(who["id"])
    if calendars.confirms(latest):
        try:
            n = await change(who["id"], p["list"], p["items"], p["action"])
            note = (f"Erledigt: {describe(p)} ({n} Eintrag{'' if n == 1 else 'e'}, vom Speicherort bestätigt)." if n
                    else "Nichts geändert: die Einträge stehen nicht mehr auf der Liste.")
        except Exception as e:
            note = f"NICHT geändert, Fehler: {e}"
        return {"call": {"name": "tasks_change (bestätigt)", "args": describe(p), "result": note},
                "system": "Liste: " + note + " Sag dem Nutzer genau das in einem Satz."}
    return {"call": {"name": "tasks_change (abgelehnt)", "args": describe(p), "result": "nicht geändert"},
            "system": f"Liste: {describe(p)} wurde NICHT ausgeführt, weil der Nutzer nicht zugestimmt hat."}


# ---------------------------------------------------------------- the assistant's tools
LIST_PARAM = {"type": "string", "enum": list(LISTS), "description": "einkauf = shopping list, aufgaben = to-do list"}
TOOLS = [
    {"type": "function", "function": {
        "name": "tasks_show", "description": "What is on the user's shopping list or to-do list.",
        "parameters": {"type": "object", "properties": {"list": LIST_PARAM}, "required": ["list"]}}},
    {"type": "function", "function": {
        "name": "tasks_add", "description": "Puts entries on the user's shopping list or to-do list (done at once).",
        "parameters": {"type": "object", "properties": {"list": LIST_PARAM, "items": {
            "type": "array", "items": {"type": "string"}, "description": "short entries, e.g. ['Milch', 'Brot']"}},
            "required": ["list", "items"]}}},
    {"type": "function", "function": {
        "name": "tasks_change", "description": "Ticks off or deletes entries. Only proposes it: the user must "
                                              "say yes in the next message, then the panel does it.",
        "parameters": {"type": "object", "properties": {"list": LIST_PARAM, "items": {
            "type": "array", "items": {"type": "string"}}, "action": {"type": "string", "enum": ["done", "delete"]}},
            "required": ["list", "items", "action"]}}}]
HINT = ("Für die Einkaufsliste und die Aufgabenliste nutzt du tasks_show, tasks_add und tasks_change. Sag nur, "
        "was im Ergebnis steht. Abhaken und Löschen schlägt tasks_change nur vor: frag dann genau mit dem Satz "
        "aus dem Ergebnis nach.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or not usable(who["id"]):
        return None  # a voice recognized at someone else's device reads no lists either
    tools = TOOLS
    outside = {"tasks_show"} if _load(who["id"])["targets"] else set()   # shared CalDAV lists hold others' words
    return {"tools": tools, "hint": HINT, "outside": outside, "changes": {"tasks_add", "tasks_change"},
            "filler": {"tasks_show": ("Ich schaue auf die Liste.", "Let me check the list.")}}


async def tool(name, args, ctx):
    uid = ctx["who"]["id"]
    lst = args.get("list") if args.get("list") in LISTS else which(args.get("list"))
    label = LISTS[lst][0]
    wanted = args.get("items")
    wanted = [wanted] if isinstance(wanted, str) else wanted if isinstance(wanted, list) else []
    try:
        if name == "tasks_show":
            have = await items(uid, lst)
            more = sent_count(uid, lst)
            text = (f"Auf der Liste {label} steht: " + ", ".join(x["text"] for x in have) + "." if have
                    else f"Die Liste {label} ist leer.")
            return text + (f" {more} weitere Einträge hat das iPhone schon in die Erinnerungen übernommen." if more else "")
        if name == "tasks_add":
            done = await add(uid, lst, [str(x) for x in wanted])
            return f"Auf die Liste {label} gesetzt: {', '.join(done)}." if done else "Nichts hinzugefügt: kein Eintrag genannt."
        if name == "tasks_change":
            action = "delete" if args.get("action") == "delete" else "done"
            picked = match(await items(uid, lst), [str(x) for x in wanted])
            if not picked:
                return f"Nicht gefunden auf der Liste {label}: {', '.join(clean(x) for x in wanted) or 'nichts genannt'}."
            p = {"list": lst, "action": action, "items": picked, "t": int(time.time()), "src": ctx.get("src", "")}
            profiles._write(_pending_file(uid), p)
            return (f"Noch NICHT geändert. Frag den Nutzer: „Soll ich {describe(p)}?“ Erst sein Ja in der nächsten "
                    "Nachricht führt es aus.")
    except (httpx.HTTPError, ValueError) as e:
        return f"Die Liste {label} ist gerade nicht erreichbar: {e}"
    return "unknown tool"


async def briefing(uid, zone=None):
    if not usable(uid):
        return ""
    try:
        have = await items(uid, "aufgaben")
    except Exception:
        return ""
    return ("Open tasks: " + ", ".join(x["text"] for x in have[:8])) if have else ""


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402
from fastapi.responses import PlainTextResponse  # noqa: E402

from core import browser_profile, own_profile  # noqa: E402

router = APIRouter()


def _on(prof=Depends(own_profile)):
    if not admin_on():
        raise HTTPException(403, "tasks are turned off")
    return prof


@router.get("/api/profile/tasks")
async def get_lists(prof=Depends(_on)):
    d = _load(prof["id"])
    out = {}
    for k, (de, en) in LISTS.items():
        tgt = d["targets"].get(k)
        try:
            have, err = (await items(prof["id"], k)) if profiles.settings(prof["id"]).get("tasks_on") else [], ""
        except (httpx.HTTPError, ValueError) as e:
            have, err = [], str(e)[:200]
        out[k] = {"name": de, "name_en": en, "items": [{"id": x["id"], "text": x["text"]} for x in have],
                  "sent": sent_count(prof["id"], k), "error": err,
                  "target": {"acc": tgt["acc"], "url": tgt["url"], "name": tgt.get("name", "")} if tgt else None}
    return {"lists": out}


@router.get("/api/profile/tasks/collections")
async def get_collections(prof=Depends(_on)):
    found, errors = await collections(prof["id"])
    return {"collections": found, "errors": errors}


@router.put("/api/profile/tasks/target")
async def set_target(request: Request, prof=Depends(browser_profile)):   # a setting: not with a device key
    if not admin_on():
        raise HTTPException(403, "tasks are turned off")
    body = await request.json()
    lst = body.get("list")
    if lst not in LISTS:
        raise HTTPException(400, "unknown list")
    with _lock:
        d = _load(prof["id"])
        if not body.get("url"):
            d["targets"].pop(lst, None)
        else:
            found, _ = await collections(prof["id"])
            hit = next((x for x in found if x["url"] == body.get("url") and x["acc"] == body.get("acc")), None)
            if not hit:
                raise HTTPException(400, "this task list was not found in your calendar accounts")
            d["targets"][lst] = {"acc": hit["acc"], "url": hit["url"], "name": hit["name"]}
        _save(prof["id"], d)
    return await get_lists(prof)


def _app_ios(request, uid):
    """The iPhone app's key reaches the lists only with the profile's app_ios switch."""
    if profiles.key_scope(request) == "app" and not profiles.settings(uid).get("app_ios"):
        raise HTTPException(403, "Apple Reminders from the app are off (Ich -> iPhone-App)")


@router.post("/api/profile/tasks/{lst}")
async def add_items(lst: str, request: Request, prof=Depends(_on)):
    if lst not in LISTS:
        raise HTTPException(400, "unknown list")
    _app_ios(request, prof["id"])
    import iphone
    text = str((await iphone._json(request, 8192)).get("text", ""))
    try:
        await add(prof["id"], lst, [x for x in re.split(r"[,\n]", text)])
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(502, str(e)[:200])
    return await get_lists(prof)


@router.post("/api/profile/tasks/{lst}/done")
async def done_items(lst: str, request: Request, prof=Depends(_on)):
    """From the page: the person ticks off with their own finger, no extra question."""
    if lst not in LISTS:
        raise HTTPException(400, "unknown list")
    ids = (await request.json() or {}).get("ids") or []
    try:
        have = await items(prof["id"], lst)
        await change(prof["id"], lst, [x for x in have if x["id"] in ids], "done")
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(502, str(e)[:200])
    return await get_lists(prof)


@router.get("/api/tasks/inbox")
def tasks_inbox(request: Request, list: str = "einkauf", take: bool = False, format: str = "text"):
    """Way A, read only: the new entries, one per line. Handing them over changes the list, so that is POST."""
    if take:
        raise HTTPException(405, "take=true needs POST /api/tasks/inbox")
    return _inbox(request, list, False, format)


@router.post("/api/tasks/inbox")
def tasks_inbox_take(request: Request, list: str = "einkauf", format: str = "text"):
    """Way A, for the iPhone shortcut with the device key: the new entries, marked as handed over."""
    return _inbox(request, list, True, format)


def _inbox(request, list, take, format):
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "no profile")
    if not usable(prof["id"]):
        raise HTTPException(403, "tasks are turned off")
    _app_ios(request, prof["id"])
    lst = list if list in LISTS else which(list)
    if _load(prof["id"])["targets"].get(lst):
        raise HTTPException(409, "this list lives in a CalDAV task list, not on the Spark")
    got = inbox(prof["id"], lst, take)
    if format == "json":
        return {"items": got}
    return PlainTextResponse("\n".join(got))
