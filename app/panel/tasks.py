"""Lists per profile: the shopping list, the to-do list and own lists („Setz Milch auf die Einkaufsliste“, „Was steht
auf der Baumarkt-Liste?“). The page Listen in the menu (listen.js), the iPhone app (ListenView.swift), the voice.

Off until the admin allows it (chat.tasks, features „tasks“; then for every profile the admin did not block, never
guests). Two lists every profile has, „einkauf“ (Einkauf) and „aufgaben“ (Aufgaben), and up to MAX_LISTS own ones
(Dominik 2026-10-20 „2a“, plan listen-teilen/plan.md Stufe 1), each with a name and a symbol from ICONS.

Every entry keeps who put it on the list, when and from where (SOURCES: the voice, the page, the app, Telegram …);
the page shows it, the journal never. An entry ticked off stays under „Erledigt“ for KEEP_DONE and can be taken back
(„Zurückholen“), then it is gone. „2 Milch“ keeps the amount apart; the same entry again adds the amount up. The
shopping lists are sorted into the shop's departments by a fixed word table (DEPARTMENTS), never by the model.

Each of the two fixed lists can also live elsewhere:
    Spark       the panel keeps the list itself. An iPhone shortcut or the app fetches new entries with the
                profile's device key (POST /api/tasks/inbox) and puts them into Apple's Reminders (way A).
    CalDAV      a task list (VTODO collection) of one of the profile's calendar accounts:
                Nextcloud, mailbox.org, Radicale ... (way B); there the Spark keeps no who and when.

Adding happens at once; by voice ticking off and deleting only after the person's "Ja" in the next message (the
panel does it, not the model); with the own finger on the page at once. After outside text nothing is added.

    USERS_DIR/<uid>/tasks.json   {"items": [{id, list, text, qty?, t, by, src, done?, done_by?, sent?}],
                                  "lists": [{id, name, icon}],
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
from common import DayCounter
import hintergrund
import netguard
import notaus
import profiles
import features

# the two lists every profile has: id -> (name de, name en, symbol); the ids are also what older apps send
LISTS = {"einkauf": ("Einkauf", "Shopping", "🛒"), "aufgaben": ("Aufgaben", "Tasks", "✓")}
# how the assistant names the two fixed lists in a sentence („Auf die Liste Einkaufsliste gesetzt“)
SAID = {"einkauf": "Einkaufsliste", "aufgaben": "Aufgaben"}
# the symbols an own list can have (a fixed choice: nothing from outside lands in the page as a picture)
ICONS = ("📝", "🛒", "🔨", "🧳", "🎁", "🏠", "🌱", "🍳", "💊", "🐾", "🎉", "📚", "🚗", "💼", "⭐")
# lists that are sorted by departments: the shopping list and own lists with the cart
SHOP_ICON = "🛒"
MAX_LISTS = 20
NAME_MAX = 40
MAX_ITEMS = 400
KEEP_SENT = 14 * 86400      # entries the iPhone took stay hidden this long (so a second fetch sends nothing twice)
KEEP_DONE = 14 * 86400      # ticked off entries stay under „Erledigt“ this long
PENDING_SECONDS = 15 * 60
# where an entry came from: fixed words the page and the app translate (never text from the request)
SOURCES = {"panel": ("Panel", "panel"), "app": ("App", "app"), "stimme": ("per Stimme", "by voice"),
           "assistent": ("Assistent", "assistant"), "telegram": ("Telegram", "Telegram"), "telefon": ("Telefon", "phone"),
           "uhr": ("Uhr", "watch"), "terminal": ("Terminal", "terminal"), "begleiter": ("Begleiter", "companion"),
           "siri": ("Siri", "Siri"), "remarkable": ("reMarkable", "reMarkable"), "auftrag": ("Auftrag", "job"),
           "mcp": ("MCP", "MCP"), "erinnerungen": ("iPhone Erinnerungen", "iPhone Reminders")}
# the chat's client (chat_turn body „client“) -> source
CLIENT_SRC = {"speaker": "stimme", "telefon": "telefon", "telegram": "telegram", "watch": "uhr", "mcp": "mcp",
              "tui": "terminal", "android": "app", "iphone": "app", "desk": "begleiter", "siri": "siri"}
# the shop's departments in the order of a walk through the shop: (name de, name en, words); first hit wins
DEPARTMENTS = (
    ("Obst und Gemüse", "Fruit and vegetables", r"apfel|äpfel|banane|birne|orange|zitrone|limette|traube|beere|kiwi|mango|"
     r"ananas|melone|pfirsich|pflaume|tomate|gurke|paprika|salat|zwiebel|knoblauch|kartoffel|karotte|möhre|lauch|"
     r"zucchini|aubergine|brokkoli|blumenkohl|kohl|spinat|pilz|champignon|avocado|ingwer|kräuter|petersilie|"
     r"schnittlauch|basilikum|radieschen|sellerie|obst|gemüse|rucola|spargel|kürbis|mais"),
    ("Brot und Backwaren", "Bread and bakery", r"brot|brötchen|semmel|toast|baguette|croissant|brezel|kuchen|zwieback|knäcke"),
    ("Milch und Kühlregal", "Dairy and chilled", r"milch|joghurt|quark|sahne|butter|käse|frischkäse|mozzarella|feta|"
     r"schmand|eier|\bei\b|margarine|pudding|kefir|buttermilch|wurst|schinken|salami|aufschnitt|tofu|hefe"),
    ("Fleisch und Fisch", "Meat and fish", r"fleisch|hack|hähnchen|huhn|pute|rind|schwein|steak|schnitzel|bratwurst|"
     r"würstchen|speck|lachs|fisch|thunfisch|garnele"),
    ("Vorrat", "Pantry", r"mehl|zucker|salz|pfeffer|reis|nudel|spaghetti|pasta|linsen|bohnen|erbsen|öl|essig|senf|ketchup|"
     r"mayo|brühe|gewürz|haferflocken|müsli|cornflakes|honig|marmelade|nutella|konserve|dose|tomatenmark|soße|sauce|"
     r"backpulver|vanille|nüsse|mandeln"),
    ("Tiefkühl", "Frozen", r"tiefkühl|tk-|pizza|eis\b|eiscreme|pommes|fischstäbchen"),
    ("Süßes und Knabberzeug", "Sweets and snacks", r"schokolade|chips|kekse|keks|gummibär|bonbon|süßigkeit|riegel|cracker|salzstangen|popcorn"),
    ("Getränke", "Drinks", r"wasser|sprudel|saft|limo|cola|bier|wein|sekt|kaffee|tee\b|kakao|getränk|mineral"),
    ("Drogerie und Haushalt", "Household and toiletries", r"spül|tabs|waschmittel|weichspüler|klopapier|toilettenpapier|"
     r"küchenrolle|taschentücher|zahnpasta|zahnbürste|shampoo|duschgel|seife|deo|creme|rasier|windel|müllbeutel|"
     r"alufolie|frischhaltefolie|backpapier|schwamm|putzmittel|reiniger|batterie|glühbirne|lampe"),
)
_DEPT = tuple((de, en, re.compile(r"(?i)(" + rx + ")")) for de, en, rx in DEPARTMENTS)
OTHER_DEPT = ("Sonstiges", "Other")
# „2 Milch“, „2x Milch“, „500 g Mehl“, „Milch 2x“: the amount apart from the entry
_UNITS = r"(?:x|×|stk\.?|stück|g|gr|kg|l|ml|pack\w*|packung\w*|dose\w*|flasche\w*|becher|bund|beutel|glas|gläser|rolle\w*|tüte\w*)"
_QTY_FRONT = re.compile(r"(?i)^(\d{1,4}(?:[.,]\d{1,3})?)\s*(" + _UNITS + r")?\.?\s+(.+)$")
_QTY_BACK = re.compile(r"(?i)^(.+?)\s+(\d{1,4}(?:[.,]\d{1,3})?)\s*(x|×|stk\.?|stück)$")
_lock = threading.Lock()


def admin_on():
    return features.admin_on("tasks")


def _file(uid):
    return profiles._path(uid, "tasks.json")


def _clean_list(x):
    if not isinstance(x, dict) or not re.fullmatch(r"l[0-9a-f]{8}", str(x.get("id", ""))):
        return None
    name = clean_name(x.get("name"))
    return {"id": x["id"], "name": name or "Liste", "icon": x.get("icon") if x.get("icon") in ICONS else ICONS[0]}


def _load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    now = time.time()
    lists = [x for x in (_clean_list(y) for y in d.get("lists") or []) if x][:MAX_LISTS]
    ids = set(LISTS) | {x["id"] for x in lists}
    items = [x for x in d.get("items") or [] if isinstance(x, dict) and x.get("list") in ids and x.get("text")
             and not (x.get("sent") and now - x["sent"] > KEEP_SENT)
             and not (x.get("done") and now - x["done"] > KEEP_DONE)]
    for x in items:   # entries from before who and when were kept: put on by the owner
        x.setdefault("by", uid)
        x.setdefault("src", "panel")
    targets = {k: v for k, v in (d.get("targets") or {}).items()
               if k in LISTS and isinstance(v, dict) and v.get("url") and v.get("acc")}
    return {"items": items, "lists": lists, "targets": targets}


def _save(uid, d):
    items = d["items"]
    if len(items) > MAX_ITEMS:   # the oldest ticked off entries go first, then the oldest open ones
        done = sorted((x for x in items if x.get("done")), key=lambda x: x["done"])
        drop = {id(x) for x in done[:len(items) - MAX_ITEMS]}
        items = [x for x in items if id(x) not in drop][-MAX_ITEMS:]
    profiles._write(_file(uid), {"items": items, "lists": d["lists"], "targets": d["targets"]})


def clean(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip(" .,;:-–")
    return text[:120]


def clean_name(text):
    return re.sub(r"[\x00-\x1f<>\"\\]", "", clean(text))[:NAME_MAX].strip()


def lists_of(uid, d=None):
    """[{"id", "name", "name_en", "icon", "own"}] of the profile's lists: the two fixed ones, then its own."""
    d = d or _load(uid)
    return [{"id": k, "name": de, "name_en": en, "icon": ic, "own": False} for k, (de, en, ic) in LISTS.items()] + \
           [{"id": x["id"], "name": x["name"], "name_en": x["name"], "icon": x["icon"], "own": True} for x in d["lists"]]


def _norm(s):
    return re.sub(r"[^a-zäöüß0-9]", "", str(s or "").lower().replace("liste", ""))


def which(name, uid=None):
    """The list a word means („Einkaufsliste“, „einkaufen“, „todo“, with uid also „Baumarkt-Liste“ for an own list
    named Baumarkt); the shopping list when nothing fits."""
    n = str(name or "").lower()
    if n in LISTS:
        return n
    if uid:
        want = _norm(n)
        for x in _load(uid)["lists"]:
            if x["id"] == n or want and _norm(x["name"]) == want:
                return x["id"]
    if re.search(r"aufgab|todo|to-do|erledig|task", n):
        return "aufgaben"
    return "einkauf"


def known(uid, lst):
    return lst in LISTS or any(x["id"] == lst for x in _load(uid)["lists"])


def name_of(uid, lst, en=False):
    if lst in LISTS:
        return LISTS[lst][1 if en else 0]
    return next((x["name"] for x in _load(uid)["lists"] if x["id"] == lst), lst)


def shop(uid, lst, d=None):
    """Whether the list is sorted by departments (the shopping list and own lists with the cart)."""
    return lst == "einkauf" or any(x["id"] == lst and x["icon"] == SHOP_ICON for x in (d or _load(uid))["lists"])


def department(text):
    """(de, en) of the department an entry belongs to, from the fixed word table."""
    for de, en, rx in _DEPT:
        if rx.search(text):
            return de, en
    return OTHER_DEPT


def split_qty(text):
    """(entry, amount) of „2 Milch“, „500 g Mehl“, „Milch 2x“; amount "" when there is none."""
    t = clean(text)
    m = _QTY_FRONT.match(t)
    if m and not re.match(r"(?i)^\d+\s*(uhr|h)\b", t):
        unit = (m.group(2) or "").lower().rstrip(".")
        return clean(m.group(3)), (m.group(1) + ("×" if unit in ("", "x", "×", "stk", "stück") else " " + unit))
    m = _QTY_BACK.match(t)
    if m:
        return clean(m.group(1)), m.group(2) + "×"
    return t, ""


def _sum_qty(a, b):
    """The amounts added up when both are numbers with the same unit, else the newer one."""
    ma, mb = (re.fullmatch(r"(\d{1,4}(?:[.,]\d{1,3})?)(.*)", x or "") for x in (a, b))
    if ma and mb and ma.group(2) == mb.group(2):
        n = float(ma.group(1).replace(",", ".")) + float(mb.group(1).replace(",", "."))
        return (str(int(n)) if n == int(n) else f"{n:g}".replace(".", ",")) + ma.group(2)
    return b or a


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
def show(x):
    """An entry as said and shown: „Milch 2×“, „Mehl 500 g“."""
    return x["text"] + (" " + x["qty"] if x.get("qty") else "")


async def items(uid, lst):
    """[{"id", "text", "qty", "t", "by", "src"}] of the list's open entries ("id" is the CalDAV address on way B, where
    the Spark keeps no amount, who or when)."""
    d = _load(uid)
    tgt = d["targets"].get(lst)
    if not tgt:
        return [{k: x.get(k, "") for k in ("id", "text", "qty", "t", "by", "src")}
                for x in d["items"] if x["list"] == lst and not x.get("sent") and not x.get("done")]
    acc = _account(uid, tgt["acc"])
    if not acc:
        raise ValueError("the calendar account of this list was removed")
    async with _client(acc) as c:
        return [{"id": href, "etag": etag, "text": str(todo.get("SUMMARY", "")).strip(), "qty": "", "t": 0, "by": "", "src": ""}
                for href, etag, _, todo in await _todos(c, tgt["url"]) if str(todo.get("SUMMARY", "")).strip()]


def done_items(uid, lst):
    """The entries ticked off in the last KEEP_DONE, newest first (only lists on the Spark keep them)."""
    return sorted(({k: x.get(k, "") for k in ("id", "text", "qty", "t", "by", "src", "done", "done_by")}
                   for x in _load(uid)["items"] if x["list"] == lst and x.get("done")), key=lambda x: -x["done"])


def sent_count(uid, lst):
    return sum(1 for x in _load(uid)["items"] if x["list"] == lst and x.get("sent"))


async def _add(uid, lst, texts, by, src):
    """Adds the entries; returns the ones added as shown (the same entry again adds its amount up)."""
    notaus.stop("aktion", uid)   # the Notaus (or the profile's own) holds every action off (notaus.py)
    seen, new = set(), []
    for text, qty in (split_qty(x) for x in texts):
        if text and text.lower() not in seen:
            seen.add(text.lower())
            new.append({"text": text, "qty": qty})
    new = new[:20]
    if not new:
        return []
    d = _load(uid)
    if not (lst in LISTS or any(x["id"] == lst for x in d["lists"])):
        raise ValueError("this list does not exist (any more)")
    tgt = d["targets"].get(lst)
    if tgt:
        acc = _account(uid, tgt["acc"])
        if not acc:
            raise ValueError("the calendar account of this list was removed")
        async with _client(acc) as c:
            for x in new:
                uid_text, body = _ical(show(x))
                r = await c.put(tgt["url"].rstrip("/") + f"/{uid_text.split('@')[0]}.ics", content=body,
                                headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
                if r.status_code not in (200, 201, 204):
                    raise ValueError(f"the server answered {r.status_code}")
        return [show(x) for x in new]
    src = src if src in SOURCES else "panel"
    with _lock:
        d = _load(uid)
        have = {x["text"].lower(): x for x in d["items"] if x["list"] == lst and not x.get("sent") and not x.get("done")}
        now = int(time.time())
        for x in new:
            old = have.get(x["text"].lower())
            if old:
                old["qty"] = _sum_qty(old.get("qty", ""), x["qty"])
            else:
                d["items"].append(dict({"id": os.urandom(5).hex(), "list": lst, "text": x["text"], "t": now,
                                        "by": by or uid, "src": src}, **({"qty": x["qty"]} if x["qty"] else {})))
        _save(uid, d)
    return [show(x) for x in new]


async def _change(uid, lst, picked, action, by):
    """Ticks off ("done"), takes back ("undo") or deletes ("delete") the picked entries [{"id", "etag"?, "text"}];
    returns how many. On the Spark a ticked off entry stays under „Erledigt“ (KEEP_DONE)."""
    notaus.stop("aktion", uid)   # the Notaus (or the profile's own) holds every action off (notaus.py)
    d = _load(uid)
    tgt = d["targets"].get(lst)
    if not tgt:
        ids = {x["id"] for x in picked}
        with _lock:
            d = _load(uid)
            hit = [x for x in d["items"] if x["id"] in ids and x["list"] == lst
                   and (bool(x.get("done")) == (action == "undo") or action == "delete")]
            if action == "delete":
                d["items"] = [x for x in d["items"] if x not in hit]
            for x in (hit if action != "delete" else ()):
                if action == "undo":
                    x.pop("done", None)
                    x.pop("done_by", None)
                else:
                    x["done"], x["done_by"] = int(time.time()), by or uid
            _save(uid, d)
        return len(hit)
    if action == "undo":
        return 0   # a CalDAV list keeps what was ticked off itself
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


def _kind(lst):
    """The list in a journal line: its fixed id, an own list only as „own“ (its name is the person's word)."""
    return lst if lst in LISTS else "own"


def _log(what, lst, uid, result):
    """One journal line per change of a list, said or not: fixed words and numbers, never the entries."""
    print(f"tasks: {what} {_kind(lst)} | {result} | {profiles.log_name(profiles.by_id(uid))}", flush=True)


_count = DayCounter()   # per day: "add", "done", "undo", "delete" (entries, never which)


async def _logged(what, lst, uid, run):
    try:
        out = await run
    except notaus.NotausAktiv:
        _log(what, lst, uid, "refused notaus")
        raise
    except Exception as e:
        _log(what, lst, uid, f"failed ({type(e).__name__})")
        raise
    n = len(out) if isinstance(out, list) else out
    _log(what, lst, uid, f"{n} entries")
    if n:
        _count.bump(what, n)
    return out


async def add(uid, lst, texts, by=None, src="panel"):
    """Adds the entries (_add) with a journal line for every outcome. by: the profile that puts them on (the owner
    when left out), src: where they came from (SOURCES)."""
    return await _logged("add", lst, uid, _add(uid, lst, texts, by, src))


async def change(uid, lst, picked, action, by=None):
    """Ticks off, takes back or deletes (_change) with a journal line for every outcome."""
    what = {"delete": "delete", "undo": "undo"}.get(action, "done")
    return await _logged(what, lst, uid, _change(uid, lst, picked, action, by))


def _list_log(what, uid, result):
    print(f"tasks: list {what} | {result} | {profiles.log_name(profiles.by_id(uid))}", flush=True)


def make_list(uid, name, icon):
    """A new own list; returns its id. ValueError for no name, a name taken or too many lists."""
    name = clean_name(name)
    try:
        if not name:
            raise ValueError("the list needs a name")
        with _lock:
            d = _load(uid)
            if len(d["lists"]) >= MAX_LISTS:
                raise ValueError(f"at most {MAX_LISTS} own lists")
            if any(_norm(x["name"]) == _norm(name) for x in lists_of(uid, d)):
                raise ValueError("a list with this name exists already")
            lid = "l" + os.urandom(4).hex()
            d["lists"].append({"id": lid, "name": name, "icon": icon if icon in ICONS else ICONS[0]})
            _save(uid, d)
    except ValueError:
        _list_log("make", uid, "refused")
        raise
    _list_log("make", uid, "ok")
    return lid


def edit_list(uid, lid, name=None, icon=None):
    """Renames an own list or gives it another symbol."""
    with _lock:
        d = _load(uid)
        x = next((y for y in d["lists"] if y["id"] == lid), None)
        if not x:
            _list_log("edit", uid, "refused unknown")
            raise ValueError("this list does not exist (any more)")
        if name is not None:
            name = clean_name(name)
            if not name or any(_norm(y["name"]) == _norm(name) for y in lists_of(uid, d) if y["id"] != lid):
                _list_log("edit", uid, "refused name")
                raise ValueError("the list needs a name of its own")
            x["name"] = name
        if icon in ICONS:
            x["icon"] = icon
        _save(uid, d)
    _list_log("edit", uid, "ok")


def drop_list(uid, lid):
    """Deletes an own list with its entries; returns how many entries went with it."""
    with _lock:
        d = _load(uid)
        if not any(x["id"] == lid for x in d["lists"]):
            _list_log("delete", uid, "refused unknown")
            raise ValueError("this list does not exist (any more)")
        n = sum(1 for x in d["items"] if x["list"] == lid)
        d["lists"] = [x for x in d["lists"] if x["id"] != lid]
        d["items"] = [x for x in d["items"] if x["list"] != lid]
        _save(uid, d)
    _list_log("delete", uid, f"{n} entries")
    return n


def match(entries, wanted):
    """The entries the words mean: exact, contained or close (never a guess beyond that)."""
    out = []
    for w in wanted:
        w = split_qty(w)[0].lower()
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
        out = [x for x in d["items"] if x["list"] == lst and not x.get("sent") and not x.get("done")]
        if take and out:
            now = int(time.time())
            for x in out:
                x["sent"] = now
            _save(uid, d)
    if take and out:
        print(f"tasks: {len(out)} entries handed to the iPhone | {_kind(lst)} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return [show(x) for x in out]


def for_live():
    """Live (Kalender): profiles with own lists, how many own lists, entries added and ticked off today; numbers only."""
    c = _count.counts()
    own = [len(_load(uid)["lists"]) for uid in profiles.user_ids() if os.path.exists(_file(uid))]
    return {"on": admin_on(), "profiles": sum(1 for n in own if n), "lists": sum(own), "added": c.get("add", 0),
            "done": c.get("done", 0)}


def card(uid):
    """Ich → Heute and the app's Heute: the open entries of the lists on the Spark, numbers and the first few only."""
    d = _load(uid)
    open_ = [x for x in d["items"] if not x.get("sent") and not x.get("done") and x["list"] not in d["targets"]]
    shop_ = [x for x in open_ if x["list"] == "einkauf"]
    return {"open": len(open_), "shopping": len(shop_), "first": [show(x)[:40] for x in shop_[-5:]][::-1],
            "lists": len(LISTS) + len(d["lists"])}


def resolve(uid, name):
    """The list a name from the model or a request means, or None for a name that fits no list of the profile
    (then the answer names the lists there are, instead of putting it on the shopping list)."""
    n = str(name or "").strip().lower()
    if not n or n in LISTS:
        return n or "einkauf"
    hit = which(n, uid)
    if hit not in LISTS:
        return hit
    if re.search(r"aufgab|todo|to-do|erledig|task", n):
        return "aufgaben"
    if re.search(r"einkauf|shop|kauf|groceries|besorg", n):
        return "einkauf"
    return None


# ---------------------------------------------------------------- "Ja" before ticking off or deleting
def pending(uid):
    return profiles.pending_get(uid, "tasks", PENDING_SECONDS)


def drop_pending(uid):
    profiles.pending_drop(uid, "tasks")


def describe(p):
    what = "abhaken" if p["action"] == "done" else "löschen"
    return f"{', '.join('„' + x['text'] + '“' for x in p['items'])} auf der Liste {p.get('name') or p['list']} {what}"


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
LIST_PARAM = {"type": "string", "description": "einkauf = shopping list, aufgaben = to-do list, or the name of one of "
                                               "the user's own lists (e.g. Baumarkt)"}
TOOLS = [
    {"type": "function", "function": {
        "name": "tasks_show", "description": "What is on one of the user's lists (shopping, to-do or an own list).",
        "parameters": {"type": "object", "properties": {"list": LIST_PARAM}, "required": ["list"]}}},
    {"type": "function", "function": {
        "name": "tasks_add", "description": "Puts entries on one of the user's lists (done at once).",
        "parameters": {"type": "object", "properties": {"list": LIST_PARAM, "items": {
            "type": "array", "items": {"type": "string"}, "description": "short entries, an amount in front, e.g. ['2 Milch', 'Brot']"}},
            "required": ["list", "items"]}}},
    {"type": "function", "function": {
        "name": "tasks_change", "description": "Ticks off or deletes entries. Only proposes it: the user must "
                                              "say yes in the next message, then the panel does it.",
        "parameters": {"type": "object", "properties": {"list": LIST_PARAM, "items": {
            "type": "array", "items": {"type": "string"}}, "action": {"type": "string", "enum": ["done", "delete"]}},
            "required": ["list", "items", "action"]}}}]
HINT = ("Für die Einkaufsliste, die Aufgabenliste und eigene Listen nutzt du tasks_show, tasks_add und tasks_change. "
        "Sag nur, was im Ergebnis steht. Abhaken und Löschen schlägt tasks_change nur vor: frag dann genau mit dem Satz "
        "aus dem Ergebnis nach.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or not features.allowed("tasks", who["id"]):
        return None  # a voice recognized at someone else's device reads no lists either
    tools = TOOLS
    outside = {"tasks_show"} if _load(who["id"])["targets"] else set()   # shared CalDAV lists hold others' words
    return {"tools": tools, "hint": HINT, "outside": outside, "changes": {"tasks_add", "tasks_change"},
            "filler": {"tasks_show": ("Ich schaue auf die Liste.", "Let me check the list.")}}


def _names(uid):
    return ", ".join(x["name"] for x in lists_of(uid))


async def tool(name, args, ctx):
    uid = ctx["who"]["id"]
    lst = resolve(uid, args.get("list"))
    if lst is None:
        return (f"Nicht geändert: eine Liste „{clean_name(args.get('list'))}“ gibt es nicht. Die Listen des Nutzers: "
                f"{_names(uid)}. Neue Listen legt er auf der Seite Listen an.")
    label = SAID.get(lst) or name_of(uid, lst)
    wanted = args.get("items")
    wanted = [wanted] if isinstance(wanted, str) else wanted if isinstance(wanted, list) else []
    try:
        if name == "tasks_show":
            have = await items(uid, lst)
            more = sent_count(uid, lst)
            text = (f"Auf der Liste {label} steht: " + ", ".join(show(x) for x in have) + "." if have
                    else f"Die Liste {label} ist leer.")
            return text + (f" {more} weitere Einträge hat das iPhone schon in die Erinnerungen übernommen." if more else "")
        if name == "tasks_add":
            done = await add(uid, lst, [str(x) for x in wanted], src=CLIENT_SRC.get(ctx.get("client"), "assistent"))
            return f"Auf die Liste {label} gesetzt: {', '.join(done)}." if done else "Nichts hinzugefügt: kein Eintrag genannt."
        if name == "tasks_change":
            action = "delete" if args.get("action") == "delete" else "done"
            picked = match(await items(uid, lst), [str(x) for x in wanted])
            if not picked:
                return f"Nicht gefunden auf der Liste {label}: {', '.join(clean(x) for x in wanted) or 'nichts genannt'}."
            p = {"list": lst, "name": label, "action": action, "items": [{k: x[k] for k in ("id", "text") if k in x}
                 | ({"etag": x["etag"]} if x.get("etag") else {}) for x in picked], "t": int(time.time()), "src": ctx.get("src", "")}
            profiles._write(profiles.pending_file(uid, "tasks"), p)
            return (f"Noch NICHT geändert. Frag den Nutzer: „Soll ich {describe(p)}?“ Erst sein Ja in der nächsten "
                    "Nachricht führt es aus.")
    except (httpx.HTTPError, ValueError) as e:
        return f"Die Liste {label} ist gerade nicht erreichbar: {e}"
    return "unknown tool"


async def briefing(uid, zone=None):
    if not features.allowed("tasks", uid):
        return ""
    try:
        have = await items(uid, "aufgaben")
    except Exception:
        return ""
    return ("Open tasks: " + ", ".join(show(x) for x in have[:8])) if have else ""


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402
from fastapi.responses import PlainTextResponse  # noqa: E402

import core  # noqa: E402
import guard  # noqa: E402
from core import browser_profile, own_profile  # noqa: E402

router = APIRouter()
BODY = 8192


def _on(request: Request, prof=Depends(own_profile)):
    if not admin_on():
        raise HTTPException(403, "tasks are turned off")
    guard.limit(request, "listen", prof["id"])
    if request.method not in ("GET", "HEAD", "DELETE") and features.blocked("tasks", prof["id"]):   # own data: seen and deleted also while blocked
        raise HTTPException(403, "blocked for this profile by the admin (Personen und Geräte → Gesperrte Funktionen)")
    return prof


def _src(request):
    """Where a change from a page or an app came from: the app's key, else the page."""
    return "app" if profiles.key_scope(request) == "app" else "panel"


def _entry(x, names):
    by = x.get("by") or ""
    if by and by not in names:
        p = profiles.by_id(by)
        names[by] = p["name"] if p else ""
    out = {"id": x["id"], "text": x["text"], "qty": x.get("qty", ""), "t": x.get("t", 0), "src": x.get("src", ""),
           "by_name": names.get(by, "")}
    if x.get("done"):
        db = x.get("done_by") or ""
        if db and db not in names:
            p = profiles.by_id(db)
            names[db] = p["name"] if p else ""
        out.update(done=x["done"], done_name=names.get(db, ""))
    return out


@router.get("/api/profile/tasks")
async def get_lists(prof=Depends(_on)):
    uid = prof["id"]
    d = _load(uid)
    may = features.allowed("tasks", uid)
    out, names = {}, {}
    for li in lists_of(uid, d):
        k = li["id"]
        tgt = d["targets"].get(k)
        try:
            have, err = (await items(uid, k)) if may else [], ""
        except (httpx.HTTPError, ValueError) as e:
            have, err = [], str(e)[:200]
        sorted_ = shop(uid, k, d)
        rows = []
        for x in have:
            e = _entry(x, names)
            if sorted_:
                e["dept"], e["dept_en"] = department(x["text"])
            rows.append(e)
        out[k] = dict(li, items=rows, done=[_entry(x, names) for x in done_items(uid, k)] if not tgt else [],
                      sent=sent_count(uid, k), error=err, shop=sorted_,
                      target={"acc": tgt["acc"], "url": tgt["url"], "name": tgt.get("name", "")} if tgt else None)
    return {"lists": out, "order": [x["id"] for x in lists_of(uid, d)], "icons": list(ICONS),
            "depts": [[de, en] for de, en, _ in DEPARTMENTS] + [list(OTHER_DEPT)],
            "sources": {k: list(v) for k, v in SOURCES.items()}, "max_lists": MAX_LISTS}


@router.get("/api/profile/tasks/collections")
async def get_collections(prof=Depends(_on)):
    found, errors = await collections(prof["id"])
    return {"collections": found, "errors": errors}


@router.put("/api/profile/tasks/target")
async def set_target(request: Request, prof=Depends(browser_profile)):   # a setting: not with a device key
    if not admin_on():
        raise HTTPException(403, "tasks are turned off")
    guard.limit(request, "listen", prof["id"])
    body = await core.json_body(request, BODY)
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


def _known(uid, lst):
    if not known(uid, lst):
        raise HTTPException(404, "this list does not exist (any more)")


@router.post("/api/profile/listen")
async def new_list(request: Request, prof=Depends(_on)):
    """An own list (name, symbol from ICONS)."""
    body = await core.json_body(request, BODY)
    try:
        lid = make_list(prof["id"], body.get("name"), body.get("icon"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return dict(await get_lists(prof), made=lid)


@router.put("/api/profile/listen/{lid}")
async def change_list(lid: str, request: Request, prof=Depends(_on)):
    body = await core.json_body(request, BODY)
    try:
        edit_list(prof["id"], lid, body.get("name") if "name" in body else None, body.get("icon"))
    except ValueError as e:
        raise HTTPException(404 if "exist" in str(e) else 400, str(e))
    return await get_lists(prof)


@router.delete("/api/profile/listen/{lid}")
async def delete_list(lid: str, prof=Depends(_on)):
    try:
        drop_list(prof["id"], lid)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return await get_lists(prof)


@router.post("/api/profile/tasks/{lst}")
async def add_items(lst: str, request: Request, prof=Depends(_on)):
    """The page and the iPhone shortcut (APP_PATHS: the app's key only with the profile's app_ios switch)."""
    _known(prof["id"], lst)
    _app_ios(request, prof["id"])
    return await _add_text(lst, request, prof)


@router.post("/api/profile/tasks/{lst}/add")
async def add_items_app(lst: str, request: Request, prof=Depends(_on)):
    """The iPhone app's Meine Sachen → Listen (iphone.THINGS "tasks"): opens with the admin's release of the lists."""
    _known(prof["id"], lst)
    return await _add_text(lst, request, prof)


async def _add_text(lst, request, prof):
    text = str((await core.json_body(request, BODY, lenient=True)).get("text", ""))
    try:
        await add(prof["id"], lst, [x for x in re.split(r"[,\n]", text)], src=_src(request))
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(502, str(e)[:200])
    return await get_lists(prof)


async def _ids(request):
    ids = (await core.json_body(request, BODY)).get("ids") or []
    return [str(x)[:300] for x in ids[:50]] if isinstance(ids, list) else []


@router.post("/api/profile/tasks/{lst}/done")
async def done_items_route(lst: str, request: Request, prof=Depends(_on)):
    """From the page: the person ticks off with their own finger, no extra question."""
    _known(prof["id"], lst)
    ids = await _ids(request)
    try:
        have = await items(prof["id"], lst)
        await change(prof["id"], lst, [x for x in have if x["id"] in ids], "done")
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(502, str(e)[:200])
    return await get_lists(prof)


@router.post("/api/profile/tasks/{lst}/undo")
async def undo_items(lst: str, request: Request, prof=Depends(_on)):
    """„Zurückholen“: a ticked off entry back on the list (only lists on the Spark keep them)."""
    _known(prof["id"], lst)
    ids = await _ids(request)
    await change(prof["id"], lst, [{"id": x} for x in ids], "undo")
    return await get_lists(prof)


@router.delete("/api/profile/tasks/{lst}/{item}")
async def delete_item(lst: str, item: str, prof=Depends(_on)):
    """Deletes one entry, open or ticked off (own data: also while the admin blocked the profile)."""
    _known(prof["id"], lst)
    try:
        have = await items(prof["id"], lst) + done_items(prof["id"], lst)
        await change(prof["id"], lst, [x for x in have if x["id"] == item], "delete")
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


# A switch that is off stays off for a while: the iPhone app asks again only after this many seconds
# (Retry-After), instead of on every sync (the log on tars showed 84 refused asks a day).
OFF_RETRY = 3600


def _inbox(request, list, take, format):
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "no profile")
    wait = {"Retry-After": str(OFF_RETRY)}
    if not features.allowed("tasks", prof["id"]):
        raise HTTPException(403, "tasks are turned off", headers=wait)
    try:
        _app_ios(request, prof["id"])
    except HTTPException as e:
        raise HTTPException(e.status_code, e.detail, headers=wait) from None
    lst = list if list in LISTS else which(list)
    if _load(prof["id"])["targets"].get(lst):
        raise HTTPException(409, "this list lives in a CalDAV task list, not on the Spark", headers=wait)
    got = inbox(prof["id"], lst, take)
    if format == "json":
        return {"items": got}
    return PlainTextResponse("\n".join(got))
