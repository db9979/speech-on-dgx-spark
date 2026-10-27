"""Das Aufgabenblatt aufs reMarkable (Paket D, Plan /mnt/project-files/remarkable-aufwerten/plan.md, Dominik 2026-10-13
"1a 2b 3a 4a 5"): one living PDF "Aufgaben" with what the profile could do in the app, each point with answers to
tick. The panel fixes what every answer does when it builds the sheet (ITEMS below); the paper only picks one of
them, read back geometrically by rmpapier.check. Nothing written on the sheet is ever a command.

Sources (each by its own switch, only what the profile may do anyway):
  todo     tasks found in the handwriting (rmplus, rm_todo)      Erinnern (tomorrow 9:00) / Weg / Später
  ged      memory entries marked stale or contradicted (gedpruefen) Stimmt / Stimmt nicht / Später
  mich     proposals for the profile's own settings (beratermich)  Übernehmen / Nein
  berater  the Einstellungs-Assistent's proposals: only for an admin profile (role Admin) and never stufe C/U/I/P;
           Dominik 2b: ticked on paper = done directly (each with "Zurücknehmen" under Ich → reMarkable → Papier)
  praxis   Praxistest after an update (idea 1, admin): the new versions' lines from the changelog, Klappt / Klappt nicht;
           "Klappt nicht" becomes a case under Zustand → Verbessern
  notiz    what the person wrote under "Anmerkung" on the sheet (Dominik 2026-10-13 "1"): read as text by the model
           (wissen.read_page, only with "Bilder und Scans lesen"), then a point on the next version: Erinnern / Weg /
           Später, and "Als Auftrag" when the panel's own rule (beobachten.parse) finds a watch sentence in it and
           watches are allowed (agent.watch_on, room under beobachten.MAX_WATCH): then the tick makes a watch under
           Ich → Aufträge (created_by "remarkable"). The text is data: it is shown and acts only after the tick

Parts the person chooses under Ich → reMarkable → Papier (PARTS, Dominik 2026-10-16 "1-5 sollte aber der user steuern
können"; each on unless the profile turns it off, and only while its function is released for the profile):
  termin   today's appointments not over yet (calendars.events): Passt / 30 min vorher erinnern / Auf morgen; only a
           reminder is made, the calendar itself is never changed
  liste    open entries of the task and shopping list (tasks.items): Erledigt ticks it off there (tasks.change)
  mail     unread mails of the last two days (mail.find): Gelesen (off the sheet only, the mailbox stays as it is) /
           Antwort entwerfen (schreib.assist writes it, tidy.make_draft puts it into the drafts folder, never sent;
           only with schreib.draft_ok) / Später
  neu      "Schnell notieren": lines read like the Anmerkung plus one ticked kind (Erinnerung heute, Morgen, Aufgabe,
           Einkauf); the tick is the yes, each line becomes one reminder or list entry
  notiz    the Anmerkung (above)

When it acts: at once when "Fertig – bitte auswerten" is ticked, else after QUIET seconds without a change on the
sheet. Exactly one answer per point; two ticked = unclear, nothing happens and the point comes again. Afterwards a new
version with the receipt ("Erledigt seit Version N"); the old one, with the person's ticks, goes to "Archiv"
(remarkable.place: a sheet with ink is never filled again). Logs: numbers only.

Always a sheet there (Dominik 2026-10-18 "1a 2a 3a 4a"): the first one comes by itself once the function is released
for the profile; ticked "Kann weg" or deleted on the device, the next check puts a new version there ("Kann weg" only
puts that one version away; to have none, the function goes off); a new version every morning from the morning sheet's
time, also when nothing changed. With nothing open the sheet says so: "0 offen" with the time, what the Spark keeps an
eye on, what was done last and what comes next (tomorrow's first appointment, when the next version comes at the
latest), and the writing parts stay.
"""
import asyncio
import datetime
import hashlib
import math
import re
import time

import features
import profiles
import remarkable
import rmpapier

QUIET = 15 * 60             # s without a change on a sheet before its ticks count (without "Fertig")
MAX_ITEMS = 30              # points on one sheet
MAX_CAL = 6                 # appointments of today on one sheet
MAX_LIST = 6                # entries of each list on one sheet
MAX_MAIL = 5                # waiting mails on one sheet
MAIL_DAYS = 2               # unread mails of these last days
MAX_SEEN = 200              # mails ticked "Gelesen" kept off the sheet
NEW_LINES = 3               # ruled lines of "Schnell notieren"
NEW_MAX = 6                 # entries from "Schnell notieren" at most
MAX_UNDO = 30               # acted points kept for "Zurücknehmen"
MAX_PRAXIS = 8              # changelog lines on one sheet
RENEW_GAP = 10 * 60         # s between two new versions at least
NOTE_MIN = 12.0             # mm of ink under "Anmerkung" before it is read
NOTE_CHARS = 200            # characters of one note at most
MAX_NOTES = 6               # notes waiting on the sheet at most
NOTE_WAIT = 180             # s for the model to read the note
NOTE_WATCH = (("ja", "Erinnern"), ("auftrag", "Als Auftrag"), ("nein", "Weg"), ("spaeter", "Später"))
# (part, profile setting, German, English, function it needs): the one list of the sheet's parts
PARTS = (("termine", "rm_tasks_cal", "Termine heute", "Today's appointments", "calendar"),
         ("listen", "rm_tasks_lists", "Aufgaben und Einkauf", "Tasks and shopping", "tasks"),
         ("mails", "rm_tasks_mail", "Wartende Mails", "Waiting mail", "mail"),
         ("neu", "rm_tasks_new", "Schnell notieren", "Quick note", ""),
         ("anmerkung", "rm_tasks_note", "Anmerkung", "Note", ""))
NEW_KINDS = (("heute", "Erinnerung heute"), ("morgen", "Morgen"), ("aufgabe", "Aufgabe"), ("einkauf", "Einkauf"))
LISTS = (("aufgaben", "Aufgabenliste"), ("einkauf", "Einkaufsliste"))
OPTS = {"termin": (("ok", "Passt"), ("erinnern", "30 min vorher erinnern"), ("morgen", "Auf morgen")),
        "liste": (("erledigt", "Erledigt"),),
        "mail": (("gelesen", "Gelesen"), ("entwurf", "Antwort entwerfen"), ("spaeter", "Später")),
        "notiz": (("ja", "Erinnern"), ("nein", "Weg"), ("spaeter", "Später")),
        "todo": (("ja", "Erinnern"), ("nein", "Weg"), ("spaeter", "Später")),
        "ged": (("ja", "Stimmt"), ("nein", "Stimmt nicht"), ("spaeter", "Später")),
        "mich": (("ja", "Übernehmen"), ("nein", "Nein")),
        "berater": (("ja", "Übernehmen"), ("nein", "Ablehnen"), ("spaeter", "Später")),
        "praxis": (("ja", "Klappt"), ("nein", "Klappt nicht"))}
SECTION = {"termin": "Heute im Kalender", "liste": "Aufgaben und Einkauf", "mail": "Wartende Mails",
           "notiz": "Aus deiner Anmerkung", "todo": "Aufgaben aus deinen Notizen", "ged": "Stimmt das noch?", "mich": "Vorschläge für dich",
           "berater": "Vorschläge für den Spark (Admin)", "praxis": "Praxistest nach dem Update"}
SAFE = re.compile(r"[0-9A-Za-z_.\-]{1,24}")
RES_DE = {"erledigt": "✓ erledigt", "abgelehnt": "✓ abgelehnt", "spaeter": "später", "unklar": "? unklar",
          "weg": "nicht mehr da", "notiert": "gelesen", "fehler": "ging nicht", "aus": "ist aus", "angehalten": "Notaus",
          "passt": "✓ passt", "erinnert": "✓ Erinnerung eingetragen", "entwurf": "✓ Entwurf im Postfach",
          "vorbei": "schon vorbei", "neu": "✓ eingetragen"}
DONE = ("erledigt", "abgelehnt", "passt", "erinnert", "entwurf", "neu")
OUTSIDE = ("termin", "liste", "mail")      # points asked from other services (gather): not in due()'s signature
WHY = ("erst", "fehlt", "neu", "morgen", "knopf")   # why a new version came (log)
ORDER = ("termin", "liste", "mail", "notiz", "todo", "ged", "mich", "berater", "praxis")


def on(uid):
    return rmpapier.on("rmaufgaben", uid) and features.allowed("rmpapier", uid)


def admin(uid):
    """An admin profile: the role Admin with its second step on (coadmin.py)."""
    import coadmin
    return bool(uid) and coadmin.acts(uid) == "admin"


def part(uid, p):
    """The profile wants this part on its sheet (its setting) and the function the part needs is released for it.
    "Schnell notieren" also needs "Bilder und Scans lesen" (the lines are read by the model)."""
    row = next(x for x in PARTS if x[0] == p)
    if profiles.settings(uid).get(row[1], profiles.SETTINGS[row[1]][0]) is not True:
        return False
    if p == "neu" and not remarkable._pictures(uid):
        return False
    return not row[4] or features.allowed(row[4], uid)


def _zone(uid):
    import rmplus
    return rmplus._zone(uid)


# ---------------------------------------------------------------- what is open
def items(uid):
    """[{"key", "src", "id", "text", "sub"}] of everything open for this profile, by the sources' own switches."""
    out = []
    t = remarkable.load(uid).get("tasks") or {}
    for n in (t.get("notes") or [])[-MAX_NOTES:] if part(uid, "anmerkung") else ():
        x = {"src": "notiz", "id": n["id"], "text": n["text"], "sub": "von deinem Aufgabenblatt"}
        if watch_of(uid, n["text"]):
            x["opts"] = NOTE_WATCH
        out.append(x)
    import rmplus
    if rmplus.on("rmtodo", uid):
        for t in rmplus.plus(uid).get("todos", [])[-6:]:
            out.append({"src": "todo", "id": t["id"], "text": t["text"], "sub": f"aus {t.get('doc', '')}".strip()})
    import gedaechtnis
    if features.allowed("gedpruefen", uid):
        for f in gedaechtnis.view(uid):
            if f.get("mark") in ("stale", "contra"):
                why = "widerspricht etwas Neuerem" if f["mark"] == "contra" else "vielleicht veraltet"
                out.append({"src": "ged", "id": f["id"], "text": f["text"], "sub": why})
    import berater
    if features.allowed("beratermich", uid):
        for p in berater.profile_props(uid):
            out.append({"src": "mich", "id": p["id"], "text": p["title"][0], "sub": p["why"][0].replace("👎", "Daumen runter")})
    if admin(uid) and features.allowed("berater", uid):
        for p in berater.props(status=("offen",)):
            if p.get("stufe") in ("C", "U", "I", "P"):
                continue          # with a code, outside or a plan: only in the app
            out.append({"src": "berater", "id": p["id"], "text": p["title"][0], "sub": "Einstellungs-Assistent"})
    if admin(uid):
        for e in praxis_lines(uid):
            out.append({"src": "praxis", "id": e["version"], "text": e["text"], "sub": e["version"]})
    return _keyed(out)


def _keyed(out):
    out = [x for x in out if SAFE.fullmatch(str(x["id"]))]
    for x in out:
        x["key"] = f"{x['src']}:{x['id']}"
        x["text"] = rmpapier.clean(x["text"], 200)
        x["sub"] = rmpapier.clean(x.get("sub") or "", 110)
    return sorted(out, key=lambda x: ORDER.index(x["src"]))[:MAX_ITEMS]


def _hid(*parts):
    return hashlib.sha256("|".join(str(x) for x in parts).encode()).hexdigest()[:12]


async def _events(uid, now, days=0):
    """The appointments of today (days=0) or a later day, [] when the calendar does not answer (a line in the log)."""
    import calendars
    zone = _zone(uid)
    start = datetime.datetime.fromtimestamp(now, zone).replace(hour=0, minute=0, second=0, microsecond=0)
    start += datetime.timedelta(days=days)
    try:
        got = await asyncio.wait_for(calendars.events(uid, start, start + datetime.timedelta(days=1), zone), 30)
    except Exception as e:
        got = None
        print("remarkable: task sheet appointments not read:", type(e).__name__, flush=True)
    return got[0] if got else []


async def gather(uid, now):
    """The points of the parts that ask other services (calendar, lists, mailbox), each with what acting needs ("x").
    A service that does not answer leaves its part out of this version (a line in the log); the others still come."""
    out = []
    if part(uid, "termine"):
        for ev in (await _events(uid, now))[:MAX_CAL * 3]:
            if not ev["allday"] and ev["end"].timestamp() <= now:
                continue          # over already
            when = "ganztägig" if ev["allday"] else ev["start"].strftime("%H:%M")
            x = {"src": "termin", "id": _hid(ev["start"].isoformat(), ev["title"]), "text": f"{when} {ev['title']}",
                 "sub": ev["location"], "x": {"start": int(ev["start"].timestamp()), "title": ev["title"][:120]}}
            if ev["allday"]:
                x["opts"] = tuple(o for o in OPTS["termin"] if o[0] != "erinnern")
            out.append(x)
            if sum(1 for y in out if y["src"] == "termin") >= MAX_CAL:
                break
    if part(uid, "listen"):
        import tasks
        for lst, name in LISTS:
            try:
                have = await asyncio.wait_for(tasks.items(uid, lst), 30)
            except Exception as e:
                have = []
                print(f"remarkable: task sheet list {lst} not read:", type(e).__name__, flush=True)
            for e in have[:MAX_LIST]:
                out.append({"src": "liste", "id": _hid(lst, e["id"]), "text": e["text"], "sub": name,
                            "x": {"lst": lst, "ref": e["id"]}})
    if part(uid, "mails"):
        import mail
        seen = set((remarkable.load(uid).get("tasks") or {}).get("mail_seen") or [])
        try:
            found, _, _ = await asyncio.to_thread(mail.find, uid, "", MAIL_DAYS, True, MAX_MAIL + len(seen))
        except Exception as e:
            found = []
            print("remarkable: task sheet mails not read:", type(e).__name__, flush=True)
        reply = await asyncio.to_thread(_draft_ok, uid)
        for aid, u, h in found:
            iid = f"{aid}-{u}"
            if iid in seen:
                continue
            x = {"src": "mail", "id": iid, "text": h.get("subject") or "(ohne Betreff)",
                 "sub": "von " + mail.known(uid, h.get("from", "")), "x": {"ref": f"{aid}:{u}"}}
            if not reply:
                x["opts"] = tuple(o for o in OPTS["mail"] if o[0] != "entwurf")
            out.append(x)
            if sum(1 for y in out if y["src"] == "mail") >= MAX_MAIL:
                break
    return out


def _draft_ok(uid):
    import schreib
    return schreib.draft_ok(uid)


def praxis_lines(uid):
    """The changelog lines of the versions newer than the last Praxistest on paper (the installed one at first)."""
    import update
    log = [e for e in update.changelog() if e.get("version")]
    if not log:
        return []
    seen = (remarkable.load(uid).get("tasks") or {}).get("praxis") or ""
    done = (remarkable.load(uid).get("tasks") or {}).get("praxis_done") or []
    new = []
    for e in log:
        if e["version"] == seen:
            break
        new.append(e)
    if not seen:
        new = log[:1]
    return [e for e in new if e["version"] not in done][:MAX_PRAXIS]


async def calm(uid, now, receipt):
    """What the sheet says when nothing is open: the time, what the Spark keeps an eye on, how much was done since the
    last version, and what comes next (tomorrow's first appointment, the next version at the latest)."""
    import rmplus
    local = datetime.datetime.fromtimestamp(now, _zone(uid))
    watch = [de for p, _, de, _, _ in PARTS if p in ("termine", "listen", "mails") and part(uid, p)]
    watch += [SECTION[s] for s, ok in (("todo", rmplus.on("rmtodo", uid)), ("ged", features.allowed("gedpruefen", uid)),
                                       ("mich", features.allowed("beratermich", uid))) if ok]
    nxt = []
    if part(uid, "termine"):
        evs = await _events(uid, now, 1)
        ev = next((e for e in evs if not e["allday"]), evs[0] if evs else None)
        if ev:
            when = "ganztägig" if ev["allday"] else ev["start"].strftime("%H:%M")
            nxt.append(f"Morgen {when} {rmpapier.clean(ev['title'], 120)}")     # outside text: data, cut and cleaned
    at = profiles.settings(uid).get("rm_morning_at") or "06:30"
    nxt.append(f"Neue Version spätestens morgen um {at}")
    return {"at": local.strftime("%d.%m. %H:%M"), "watch": watch, "next": nxt,
            "done": sum(1 for r in receipt if r.get("res") in DONE)}


# ---------------------------------------------------------------- the sheet
def build(m, its, version, receipt, day, areas=("anmerkung",), kinds=NEW_KINDS, quiet=None):
    """areas: the writing parts on this sheet ("neu" Schnell notieren, "anmerkung"); kinds: the answers of "Schnell
    notieren" (Aufgabe and Einkauf only with the lists); quiet: calm() for a sheet with nothing open."""
    sh = rmpapier.Sheet(m, "Aufgaben", "Deine Aufgaben", f"Version {version} · {day}", rmpapier._code("aufgaben", version, time.time()))
    if not its:
        q = quiet or {}
        sh.section("Alles erledigt")
        if q:
            sh.cards([("0 offen", f"Stand {q['at']}")] + ([(f"{q['done']} erledigt", f"seit Version {version - 1}")] if q["done"] else []))
        seen = f" Der Spark schaut weiter nach: {', '.join(q['watch'])}." if q.get("watch") else ""
        sh.para(f"Gerade ist nichts zu tun.{seen} Kommt etwas dazu, liegt hier von selbst eine neue Version.", 9.5)
    if receipt:
        sh.section("Zuletzt erledigt" if not its else f"Erledigt seit Version {version - 1}")
        for r in receipt[:12]:
            sh.bullet(f"{RES_DE.get(r['res'], r['res'])}: {r['text']}")
    if not its and (quiet or {}).get("next"):
        sh.section("Als Nächstes")
        for n in quiet["next"]:
            sh.bullet(n)
    src_seen = set()
    for x in its:
        if x["src"] not in src_seen:
            src_seen.add(x["src"])
            sh.need(45 * sh.s)        # a heading never stands alone at the bottom of a page
            sh.section(SECTION[x["src"]])
        if x["src"] == "liste":
            sh.check(x["text"], x["key"] + "|erledigt", "wahl", x.get("sub", ""))
        else:
            sh.choice(x["text"], x["key"], x.get("opts") or OPTS[x["src"]], x.get("sub", ""))
    if "neu" in areas:
        sh.need(45 * sh.s + NEW_LINES * 8)
        sh.section("Schnell notieren")
        sh.note_area("neu", "Eine Sache pro Zeile", NEW_LINES)
        sh.choice("Was ist das?", "neu", kinds, "Ein Kreuz: das ist dein Ja. Ohne Kreuz passiert nichts.")
    if "anmerkung" in areas:
        sh.note_area("anmerkung", "Anmerkung")
        sh.para("Was du hier schreibst, liest der Spark und legt es dir auf der nächsten Version zum Ankreuzen vor "
                "(Erinnern, Weg, Später).", 7.5, "mut")
    if its or "neu" in areas:
        sh.para("Ein Kreuz je Punkt. Falsch? Kästchen ganz ausmalen. Zwei Kreuze in einem Punkt: dann passiert nichts, "
                "und er kommt wieder.", 7.5, "mut")
        sh.check("Fertig – bitte auswerten", "fertig", "fertig", "Sonst wertet der Spark nach 15 Minuten Ruhe aus.")
    return sh.finish()


async def send(uid, now=None, why="knopf"):
    """Puts a new version there (also when nothing is open: "Alles erledigt"). why: a word of due() or "knopf".
    Returns the place() result."""
    now = now or time.time()
    if gone(uid):
        d = remarkable.load(uid)
        (d.get("own") or {}).pop("aufgaben", None)     # put away or deleted: a new document, the old one stays where it is
        remarkable.save(uid, d)
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    its = _keyed(await gather(uid, now) + items(uid))
    areas = tuple(p for p in ("neu", "anmerkung") if part(uid, p))
    version = int(t.get("v", 0)) + 1
    local = datetime.datetime.fromtimestamp(now, _zone(uid))
    m = rmpapier.model_of(uid, d)
    kinds = NEW_KINDS if features.allowed("tasks", uid) else NEW_KINDS[:2]
    quiet = None if its else await calm(uid, now, t.get("receipt") or [])
    built = build(m, its, version, t.get("receipt") or [], local.strftime("%d.%m.%Y"), areas, kinds, quiet)
    r = await rmpapier.place(uid, "aufgaben", "Aufgaben", built, "aufgaben", own="aufgaben", auto=True)
    d = remarkable.load(uid)
    pp = d["papers"][r["id"]]
    pp["items"] = {x["key"]: dict({"src": x["src"], "id": x["id"], "text": x["text"]},
                                  **({"o": [k for k, _ in x["opts"]]} if x.get("opts") else {}),
                                  **({"x": x["x"]} if x.get("x") else {})) for x in its}
    pp["v"] = version
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    t.update(v=version, receipt=[], renew=False, last=int(now), day=local.strftime("%Y-%m-%d"))
    t.pop("sig", None)
    pr = [x["id"] for x in its if x["src"] == "praxis"]
    if pr:
        t["praxis"] = pr[0]
    d["tasks"] = t
    remarkable.save(uid, d)
    print(f"remarkable: task sheet | version {version}, {len(its)} point(s), why {why if why in WHY else 'knopf'}", flush=True)
    return r


def gone(uid):
    """The newest task sheet is gone ("Kann weg" or deleted on the device): the next check puts a new one there."""
    mine = [pp for pp in (remarkable.load(uid).get("papers") or {}).values() if pp.get("k") == "aufgaben"]
    return bool(mine) and bool(max(mine, key=lambda pp: int(pp.get("v", 0))).get("gone"))


def due(uid, now):
    """Why a new version is due (a word of WHY), or "": the first one, the newest gone, after the ticks were acted
    on, or each morning from the morning sheet's time. Never more often than RENEW_GAP (Dominik 2026-10-18: always a
    sheet there)."""
    t = remarkable.load(uid).get("tasks") or {}
    if not t.get("v"):
        return "erst"         # the first one comes by itself once the function is released (3a)
    if now - int(t.get("last", 0)) < RENEW_GAP:
        return ""
    if gone(uid):
        return "fehlt"        # "Kann weg" ticked or deleted on the device: a new one (1a)
    if t.get("renew"):
        return "neu"
    local = datetime.datetime.fromtimestamp(now, _zone(uid))
    at = profiles.settings(uid).get("rm_morning_at") or "06:30"
    if t.get("day") == local.strftime("%Y-%m-%d") or local.strftime("%H:%M") < at:
        return ""
    return "morgen"           # a new one each morning, also when nothing changed: the date and the "Stand" are today's (4a)


# ---------------------------------------------------------------- reading it back (from rmpapier.check)
def note_strokes(pp, mm, name="anmerkung"):
    """The strokes (mm) written in one of the sheet's writing areas ("anmerkung", "neu"): more than half of their
    points inside its lines."""
    f = next((x for x in pp.get("f") or [] if x.get("k") == "notiz" and x.get("n") == name), None)
    if not f:
        return []
    out = []
    for ln in mm.get(f["p"], []):
        inside = sum(1 for pt in ln if rmpapier._inside(pt, f["x"], f["y"], f["w"], f["h"], 2.0))
        if ln and inside * 2 > len(ln):
            out.append(ln)
    return out


def note_lines(text):
    """The model's reading of "Schnell notieren": one entry per written line, without its picture description and
    unreadable marks."""
    out = []
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s or s.lower().startswith("bild:"):
            continue
        s = rmpapier.clean(" ".join(s.replace("[unleserlich]", " ").strip(" -•*#\t").split()), 120).strip()
        if s:
            out.append(s)
    return out[:NEW_MAX]


def _ink(pp, mm, name):
    """(strokes, signature) of a writing area with enough ink, else (None, None)."""
    lines = note_strokes(pp, mm, name)
    if sum(math.dist(a, b) for a, b in rmpapier._segments(lines)) < NOTE_MIN:
        return None, None
    return lines, hashlib.sha256(repr([[(round(x, 1), round(y, 1)) for x, y in ln] for ln in lines]).encode()).hexdigest()[:12]


async def _read_page(lines):
    """The model's reading of the strokes (rendered at a tenth of a millimetre), or raises."""
    import wissen
    jpeg = remarkable.render([([(x * 10, y * 10) for x, y in ln], 8.0) for ln in lines])
    return await asyncio.wait_for(wissen.read_page(jpeg), NOTE_WAIT)


async def read_new(uid, pp, mm):
    """Reads "Schnell notieren" when its ink changed; the lines wait on the sheet (pp["neu"]) for the ticked kind."""
    lines, sig = _ink(pp, mm, "neu")
    if not lines or sig == (pp.get("neu") or {}).get("sig"):
        return None
    if not remarkable._pictures(uid):
        print("remarkable: task sheet quick note not read | reading pictures is off", flush=True)
        return None
    try:
        got = note_lines(await _read_page(lines))
    except Exception as e:             # the model away or slow: read again with the next change of the sheet
        print("remarkable: task sheet quick note not read:", remarkable.why(e), flush=True)
        return None
    pp["neu"] = {"sig": sig, "lines": got}
    print(f"remarkable: task sheet quick note read | {len(got)} line(s)", flush=True)
    return got


def note_text(text):
    """The model's reading as one short line: without its picture description, unreadable marks and list signs."""
    keep = []
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s or s.lower().startswith("bild:"):
            continue
        s = s.replace("[unleserlich]", " ").strip(" -•*#\t")
        if s:
            keep.append(s)
    return rmpapier.clean(" ".join(" ".join(keep).split()), NOTE_CHARS).strip()


async def read_note(uid, did, pp, mm, now):
    """Reads the "Anmerkung" when its ink changed: one note per sheet (a longer one replaces the shorter), a point on
    the next version. Returns the text or None."""
    lines, sig = _ink(pp, mm, "anmerkung")
    if not lines or sig == pp.get("note_sig"):
        return None
    if not remarkable._pictures(uid):
        print("remarkable: task sheet note not read | reading pictures is off", flush=True)
        return None
    try:
        text = note_text(await _read_page(lines))
    except Exception as e:             # the model away or slow: read again with the next change of the sheet
        print("remarkable: task sheet note not read:", remarkable.why(e), flush=True)
        return None
    pp["note_sig"] = sig
    if not text:
        print("remarkable: task sheet note read | nothing legible", flush=True)
        return None
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    notes = [n for n in t.get("notes") or [] if n.get("sheet") != did]
    t["notes"] = (notes + [{"id": sig, "sheet": did, "text": text, "at": int(now)}])[-MAX_NOTES:]
    t["receipt"] = [r for r in t.get("receipt") or [] if r.get("sheet") != did] + [
        {"text": text, "res": "notiert", "sheet": did}]
    d["tasks"] = t
    remarkable.save(uid, d)
    print(f"remarkable: task sheet note read | {len(text)} characters", flush=True)
    rmpapier._live("Anmerkung gelesen")
    return text


def pending(pp, now):
    """A read sheet whose ticks were not acted on yet and that has been quiet long enough."""
    return (pp.get("k") == "aufgaben" and bool(pp.get("r")) and int(pp.get("changed", 0)) > int(pp.get("acted", 0))
            and now - int(pp.get("changed", now)) >= QUIET)


def ready(pp, now):
    """Read and not acted on since: "Fertig" ticked, or quiet long enough."""
    if int(pp.get("changed", 0)) <= int(pp.get("acted", 0)):
        return False
    return (pp.get("r") or {}).get("fertig") == "an" or pending(pp, now)


async def act(uid, pp, now):
    """Does what the ticked answers say, by the table OPTS (never the model). Returns the number acted on."""
    import notaus
    states = pp.get("r") or {}
    results, undo, n = [], [], 0
    stop = None
    try:
        notaus.stop("aktion", uid)
    except notaus.NotausAktiv:
        stop = "angehalten"
    done_keys = pp.setdefault("a_items", [])
    for key, it in (pp.get("items") or {}).items():
        if key in done_keys:
            continue          # acted on already (a later tick on the same sheet does not act twice)
        answers = it.get("o") or [k for k, _ in OPTS.get(it.get("src"), ())]
        ticked = [k for k in answers if states.get(f"{key}|{k}") == "an"]
        if not ticked:
            continue
        if len(ticked) > 1:
            results.append({"text": it["text"], "res": "unklar"})
            continue
        if stop:
            results.append({"text": it["text"], "res": stop})
            continue
        try:
            res, u = await _do_outside(uid, it, ticked[0], now) if it["src"] in OUTSIDE else _do(uid, it, ticked[0], now)
        except Exception as e:         # one point failing never stops the others
            print("remarkable: task point failed:", type(e).__name__, flush=True)
            res, u = "fehler", None
        results.append({"text": it["text"], "res": res})
        if res != "spaeter":
            done_keys.append(key)
        if u:
            undo.append({"i": f"{int(now)}{len(undo)}", "text": it["text"], "src": it["src"], "u": u})
        n += res in DONE
    if "neu" not in done_keys:
        kinds = [k for k, _ in NEW_KINDS if states.get(f"neu|{k}") == "an"]
        got = (pp.get("neu") or {}).get("lines") or []
        if kinds:
            text = "Schnell notieren: " + ", ".join(got)[:120] if got else "Schnell notieren"
            if len(kinds) > 1:
                res, u = "unklar", None
            elif stop:
                res, u = stop, None
            elif not got:
                res, u = "fehler", None     # not read (yet): the next change of the sheet acts again
            else:
                try:
                    res, u = await _do_new(uid, kinds[0], got, now)
                except Exception as e:
                    print("remarkable: task point failed:", type(e).__name__, flush=True)
                    res, u = "fehler", None
                done_keys.append("neu")
            results.append({"text": text, "res": res})
            if u:
                undo.append({"i": f"{int(now)}{len(undo)}", "text": text, "src": "neu", "u": u})
            n += res in DONE
    pp["acted"] = int(now)
    pp["done"] = results
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    t["receipt"] = (t.get("receipt") or []) + results
    t["undo"] = ((t.get("undo") or []) + undo)[-MAX_UNDO:]
    t["renew"] = True
    d["tasks"] = t
    remarkable.save(uid, d)
    print(f"remarkable: task sheet read | {n} done, {sum(r['res'] == 'unklar' for r in results)} unclear", flush=True)
    return n


def watch_of(uid, text):
    """The watch a note asks for, by the panel's own rule (beobachten.parse), when watches are allowed and there is
    room; else None. The model never decides this."""
    try:
        import agent
        import beobachten
    except ImportError:
        return None
    if not agent.watch_on(uid):
        return None
    w = beobachten.parse(text)
    if not w:
        return None
    if sum(1 for p in agent.load(uid).get("plans") or [] if p.get("kind") == "watch") >= beobachten.MAX_WATCH:
        return None
    return w


def _tomorrow_nine(uid, now):
    local = datetime.datetime.fromtimestamp(now, _zone(uid)) + datetime.timedelta(days=1)
    return int(local.replace(hour=9, minute=0, second=0, microsecond=0).timestamp() * 1000)


def _today_evening(uid, now):
    """"Erinnerung heute": at 18:00, or in an hour when it is later than 17:00."""
    local = datetime.datetime.fromtimestamp(now, _zone(uid))
    at = local.replace(hour=18, minute=0, second=0, microsecond=0)
    return int((at.timestamp() if local.hour < 17 else now + 3600) * 1000)


async def _do_new(uid, kind, lines, now):
    """"Schnell notieren" with its ticked kind: each line one reminder or one list entry."""
    if kind in ("heute", "morgen"):
        due = _today_evening(uid, now) if kind == "heute" else _tomorrow_nine(uid, now)
        return "neu", {"rems": [profiles.add_reminder(uid, x, due)["id"] for x in lines]}
    if not features.allowed("tasks", uid):
        return "aus", None
    import tasks
    lst = "aufgaben" if kind == "aufgabe" else "einkauf"
    added = await tasks.add(uid, lst, lines, src="remarkable")
    return "neu", {"list": lst, "texts": added}


async def _do_outside(uid, it, choice, now):
    """One answer to a point asked from another service (gather): (result, what "Zurücknehmen" needs or None).
    The calendar is never changed, a mail never sent or marked."""
    src, x = it["src"], it.get("x") or {}
    if choice == "spaeter":
        return "spaeter", None
    if src == "termin":
        if not features.allowed("calendar", uid):
            return "aus", None
        if choice == "ok":
            return "passt", None
        start = int(x.get("start", 0))
        when = datetime.datetime.fromtimestamp(start, _zone(uid)).strftime("%H:%M")
        if choice == "erinnern":
            if start <= now:
                return "vorbei", None
            r = profiles.add_reminder(uid, f"Um {when}: {x.get('title', '')}", max(start - 1800, int(now) + 60) * 1000)
        else:
            r = profiles.add_reminder(uid, f"Von gestern verschoben: {x.get('title', '')}", _tomorrow_nine(uid, now))
        return "erinnert", {"rem": r["id"]}
    if src == "liste":
        if not features.allowed("tasks", uid):
            return "aus", None
        import tasks
        hit = next((e for e in await tasks.items(uid, x.get("lst")) if e["id"] == x.get("ref")), None)
        if not hit:
            return "weg", None
        await tasks.change(uid, x["lst"], [hit], "done")
        return "erledigt", {"list": x["lst"], "texts": [hit["text"]]}
    if src == "mail":
        if not features.allowed("mail", uid):
            return "aus", None
        if choice == "entwurf":
            if not await asyncio.to_thread(_draft_ok, uid):
                return "aus", None
            await _draft(uid, x.get("ref", ""))
        _seen(uid, it["id"])
        return ("entwurf", None) if choice == "entwurf" else ("erledigt", {"seen": it["id"]})
    return "weg", None


async def _draft(uid, ref):
    """"Antwort entwerfen": the Schreibhilfe writes the answer to the mail (data for it, never an order), the draft goes
    into the mailbox's drafts folder; nothing is sent."""
    import mail
    import schreib
    import tidy
    msg = await asyncio.to_thread(mail.message, uid, ref)
    if msg is None:
        raise ValueError("the message is gone")
    text, _ = mail.plain(msg)
    head = f"Von: {mail._addr(msg.get('From', ''))}\nBetreff: {mail._hdr(msg.get('Subject', ''))}\n\n"
    out = await schreib.assist(uid, {"art": "antwort", "mail": (head + (text or ""))[:schreib.MAX_MAIL]}, "auto", "reMarkable")
    aid, u = ref.split(":")
    await asyncio.to_thread(tidy.make_draft, uid, aid, "", "", out["text"], int(u))


def _seen(uid, iid):
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    t["mail_seen"] = ([v for v in t.get("mail_seen") or [] if v != iid] + [iid])[-MAX_SEEN:]
    d["tasks"] = t
    remarkable.save(uid, d)


def _keep_note(uid, note):
    """A note whose answer could not be done stays open for the next version."""
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    t["notes"] = ([n for n in t.get("notes") or [] if n["id"] != note["id"]] + [note])[-MAX_NOTES:]
    d["tasks"] = t
    remarkable.save(uid, d)


def _do(uid, it, choice, now):
    """One answer: (result, what "Zurücknehmen" needs or None)."""
    src, iid = it["src"], it["id"]
    if choice == "spaeter":
        return "spaeter", None
    if src == "notiz":
        d = remarkable.load(uid)
        t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
        note = next((n for n in t.get("notes") or [] if n["id"] == iid), None)
        if not note:
            return "weg", None
        t["notes"] = [n for n in t.get("notes") or [] if n["id"] != iid]
        d["tasks"] = t
        remarkable.save(uid, d)
        if choice == "ja":
            r = profiles.add_reminder(uid, note["text"], _tomorrow_nine(uid, now))
            return "erledigt", {"rem": r["id"], "note": note}
        if choice == "auftrag":
            w = watch_of(uid, note["text"])        # checked again now: switch, rule and room may have changed
            if not w:
                _keep_note(uid, note)
                return "aus", None
            import agent
            import chat
            try:
                plan = agent.parse_plan(dict(w, kind="watch"), chat.user_zone(profiles.settings(uid).get("tz", "")))
                item = agent.add_plan(uid, dict(plan, created_by="remarkable"))
            except ValueError:
                _keep_note(uid, note)
                return "fehler", None
            return "erledigt", {"plan": item["id"], "note": note}
        return "abgelehnt", {"note": note}
    import rmplus
    if src == "todo":
        if not rmplus.on("rmtodo", uid):
            return "aus", None
        todo = next((t for t in rmplus.plus(uid).get("todos", []) if t["id"] == iid), None)
        if not todo:
            return "weg", None
        rmplus._mut(uid, lambda p: p.update(todos=[t for t in p.get("todos", []) if t["id"] != iid]))
        if choice == "ja":
            r = profiles.add_reminder(uid, todo["text"], _tomorrow_nine(uid, now))
            return "erledigt", {"rem": r["id"], "todo": todo}
        return "abgelehnt", {"todo": todo}
    if src == "ged":
        import gedaechtnis
        if not features.allowed("gedpruefen", uid):
            return "aus", None
        fact = next((f for f in gedaechtnis.view(uid) if f["id"] == iid), None)
        if not fact:
            return "weg", None
        if choice == "ja":
            gedaechtnis.confirm(uid, iid)
            return "erledigt", None
        profiles.forget(uid, fact_id=iid)
        return "abgelehnt", {"fact": fact["text"]}
    import berater
    if src == "mich":
        if not features.allowed("beratermich", uid):
            return "aus", None
        p = next((x for x in berater.profile_props(uid) if x["id"] == iid), None)
        if not p:
            return "weg", None
        if choice == "ja":
            if not berater._pruefen_profile(p)["ok"]:
                return "fehler", None
            key = p["change"]["key"]
            old = profiles.settings(uid).get(key, profiles.SETTINGS[key][0])
            profiles.save_settings(uid, {key: p["change"]["new"]})
            return "erledigt", {"set": {key: old}}
        s = profiles.settings(uid)
        skip = [x for x in (s.get("berater_skip") or []) if isinstance(x, str)][-20:]
        profiles.save_settings(uid, {"berater_skip": skip + [iid]})
        return "abgelehnt", None
    if src == "berater":
        # Dominik 2b: an admin's tick is done directly; checked again now (the role may have changed since)
        if not (admin(uid) and features.allowed("berater", uid)):
            return "aus", None
        p = berater.get(iid)
        if not p or p.get("status") != "offen" or p.get("stufe") in ("C", "U", "I", "P"):
            return "weg", None
        if choice == "ja":
            berater.take(iid, uid, now=now)
            return "erledigt", {"berater": iid}
        berater.reject(iid, uid, now)
        return "abgelehnt", None
    if src == "praxis":
        if not admin(uid):
            return "aus", None
        d = remarkable.load(uid)
        t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
        t["praxis_done"] = ((t.get("praxis_done") or []) + [iid])[-50:]
        d["tasks"] = t
        remarkable.save(uid, d)
        if choice == "nein":
            import faelle
            if faelle.wanted():
                faelle.add("schlecht", {"who": [uid]}, title=f"Praxistest {iid}: klappt nicht",
                           note="Praxistest auf Papier: " + it["text"])
        return "erledigt", None
    return "weg", None


async def undo(uid, i):
    """"Zurücknehmen" of one acted point. Returns True when it was taken back."""
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    x = next((u for u in t.get("undo") or [] if u["i"] == i), None)
    if not x:
        return False
    u = x["u"]
    if "rem" in u:
        profiles.remove_reminders(uid, {u["rem"]})
    if "rems" in u:
        profiles.remove_reminders(uid, set(u["rems"]))
    if "list" in u:
        import tasks
        if not features.allowed("tasks", uid):
            return False
        if x["src"] == "neu":          # taken off the list again
            have = await tasks.items(uid, u["list"])
            await tasks.change(uid, u["list"], tasks.match(have, u["texts"]), "delete")
        else:                          # ticked off: back on the list
            await tasks.add(uid, u["list"], u["texts"], src="remarkable")
    if "plan" in u:
        import agent
        agent.mutate(uid, lambda d: d.update(plans=[p for p in d["plans"] if p.get("id") != u["plan"]]))
    if "todo" in u:
        import rmplus
        rmplus._mut(uid, lambda p: p.update(todos=[t for t in p.get("todos", []) if t["id"] != u["todo"]["id"]] + [u["todo"]]))
    if "fact" in u:
        profiles.remember(uid, u["fact"])
    if "set" in u:
        profiles.save_settings(uid, u["set"])
    if "berater" in u:
        import berater
        if not admin(uid):
            return False
        berater.undo(u["berater"], uid)
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    t["undo"] = [v for v in t.get("undo") or [] if v["i"] != i]
    if "seen" in u:
        t["mail_seen"] = [v for v in t.get("mail_seen") or [] if v != u["seen"]]
    if "note" in u:
        t["notes"] = ([n for n in t.get("notes") or [] if n["id"] != u["note"]["id"]] + [u["note"]])[-MAX_NOTES:]
    d["tasks"] = t
    remarkable.save(uid, d)
    print("remarkable: task point taken back", flush=True)
    return True


def public(uid):
    t = remarkable.load(uid).get("tasks") or {}
    return {"on": features.allowed("rmaufgaben", uid), "spark": features.admin_on("rmaufgaben"), "version": t.get("v", 0),
            "open": len(items(uid)) if on(uid) else 0,
            "undo": [{"i": u["i"], "text": u["text"], "src": u["src"]} for u in (t.get("undo") or [])][::-1][:10],
            "parts": [{"k": p, "pref": key, "de": de, "en": en, "ok": not need or features.allowed(need, uid)}
                      for p, key, de, en, need in PARTS]}
