"""Das Aufgabenblatt aufs reMarkable (Paket D, Plan /mnt/project-files/remarkable-aufwerten/plan.md, Dominik 2026-10-13
"1a 2b 3a 4a 5"): one living PDF "Aufgaben" with what the profile could do in the app, each point with answers to
tick. The panel fixes what every answer does when it builds the sheet (ITEMS below); the paper only picks one of
them, read back geometrically by rmpapier.check. Nothing written on the sheet is ever a command.

Sources (each by its own switch, only what the profile may do anyway):
  todo     tasks found in the handwriting (rmplus, rm_todo)      Erinnern (tomorrow 9:00) / Weg / Später
  ged      memory entries marked stale or contradicted (gedpruefen) Stimmt / Stimmt nicht / Später
  mich     proposals for the profile's own settings (beratermich)  Übernehmen / Nein
  berater  the Einstellungs-Assistent's proposals: only for an admin profile (owner, co-admin) and never stufe C/U/I/P;
           Dominik 2b: ticked on paper = done directly (each with "Zurücknehmen" under Ich → reMarkable → Papier)
  praxis   Praxistest after an update (idea 1, admin): the new versions' lines from the changelog, Klappt / Klappt nicht;
           "Klappt nicht" becomes a case under Zustand → Verbessern

When it acts: at once when "Fertig – bitte auswerten" is ticked, else after QUIET seconds without a change on the
sheet. Exactly one answer per point; two ticked = unclear, nothing happens and the point comes again. Afterwards a new
version with the receipt ("Erledigt seit Version N"); the old one, with the person's ticks, goes to "Archiv"
(remarkable.place: a sheet with ink is never filled again). Logs: numbers only.
"""
import datetime
import re
import time

import features
import profiles
import remarkable
import rmpapier

QUIET = 15 * 60             # s without a change on a sheet before its ticks count (without "Fertig")
MAX_ITEMS = 15              # points on one sheet
MAX_UNDO = 30               # acted points kept for "Zurücknehmen"
MAX_PRAXIS = 8              # changelog lines on one sheet
RENEW_GAP = 10 * 60         # s between two new versions at least
OPTS = {"todo": (("ja", "Erinnern"), ("nein", "Weg"), ("spaeter", "Später")),
        "ged": (("ja", "Stimmt"), ("nein", "Stimmt nicht"), ("spaeter", "Später")),
        "mich": (("ja", "Übernehmen"), ("nein", "Nein")),
        "berater": (("ja", "Übernehmen"), ("nein", "Ablehnen"), ("spaeter", "Später")),
        "praxis": (("ja", "Klappt"), ("nein", "Klappt nicht"))}
SECTION = {"todo": "Aufgaben aus deinen Notizen", "ged": "Stimmt das noch?", "mich": "Vorschläge für dich",
           "berater": "Vorschläge für den Spark (Admin)", "praxis": "Praxistest nach dem Update"}
SAFE = re.compile(r"[0-9A-Za-z_.\-]{1,24}")
RES_DE = {"erledigt": "✓ erledigt", "abgelehnt": "✓ abgelehnt", "spaeter": "später", "unklar": "? unklar",
          "weg": "nicht mehr da", "fehler": "ging nicht", "aus": "ist aus", "angehalten": "Notaus"}


def on(uid):
    return rmpapier.on("rmaufgaben", uid) and rmpapier.paper_on(uid)


def admin(uid):
    """An admin profile: owner or co-admin while the roles are on (coadmin.py)."""
    import coadmin
    return bool(uid) and coadmin.on() and coadmin.role(uid) in ("owner", "coadmin")


def _zone(uid):
    import rmplus
    return rmplus._zone(uid)


# ---------------------------------------------------------------- what is open
def items(uid):
    """[{"key", "src", "id", "text", "sub"}] of everything open for this profile, by the sources' own switches."""
    out = []
    import rmplus
    if rmplus.on("rmtodo", uid):
        for t in rmplus.plus(uid).get("todos", [])[-6:]:
            out.append({"src": "todo", "id": t["id"], "text": t["text"], "sub": f"aus {t.get('doc', '')}".strip()})
    import gedaechtnis
    if gedaechtnis.on(uid):
        for f in gedaechtnis.view(uid):
            if f.get("mark") in ("stale", "contra"):
                why = "widerspricht etwas Neuerem" if f["mark"] == "contra" else "vielleicht veraltet"
                out.append({"src": "ged", "id": f["id"], "text": f["text"], "sub": why})
    import berater
    if features.allowed("beratermich", uid):
        for p in berater.profile_props(uid):
            out.append({"src": "mich", "id": p["id"], "text": p["title"][0], "sub": p["why"][0].replace("👎", "Daumen runter")})
    if admin(uid) and features.admin_on("berater"):
        for p in berater.props(status=("offen",)):
            if p.get("stufe") in ("C", "U", "I", "P"):
                continue          # with a code, outside or a plan: only in the app
            out.append({"src": "berater", "id": p["id"], "text": p["title"][0], "sub": "Einstellungs-Assistent"})
    if admin(uid):
        for e in praxis_lines(uid):
            out.append({"src": "praxis", "id": e["version"], "text": e["text"], "sub": e["version"]})
    out = [x for x in out if SAFE.fullmatch(str(x["id"]))]
    for x in out:
        x["key"] = f"{x['src']}:{x['id']}"
        x["text"] = rmpapier.clean(x["text"], 200)
    return out[:MAX_ITEMS]


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


def _sig(its):
    return "|".join(sorted(x["key"] for x in its))


# ---------------------------------------------------------------- the sheet
def build(m, its, version, receipt, day):
    sh = rmpapier.Sheet(m, "Aufgaben", "Deine Aufgaben", f"Version {version} · {day}", rmpapier._code("aufgaben", version, time.time()))
    if receipt:
        sh.section(f"Erledigt seit Version {version - 1}")
        for r in receipt[:12]:
            sh.bullet(f"{RES_DE.get(r['res'], r['res'])}: {r['text']}")
    if not its:
        sh.section("Alles erledigt")
        sh.para("Gerade ist nichts offen. Kommt etwas dazu, liegt hier eine neue Version.", 9.5)
    src_seen = set()
    for x in its:
        if x["src"] not in src_seen:
            src_seen.add(x["src"])
            sh.need(45 * sh.s)        # a heading never stands alone at the bottom of a page
            sh.section(SECTION[x["src"]])
        sh.choice(x["text"], x["key"], OPTS[x["src"]], x.get("sub", ""))
    if its:
        sh.para("Ein Kreuz je Punkt. Falsch? Kästchen ganz ausmalen. Zwei Kreuze in einem Punkt: dann passiert nichts, "
                "und er kommt wieder.", 7.5, "mut")
        sh.check("Fertig – bitte auswerten", "fertig", "fertig", "Sonst wertet der Spark nach 15 Minuten Ruhe aus.")
    return sh.finish()


async def send(uid, now=None):
    """Puts a new version there (also when nothing is open: "Alles erledigt"). Returns the place() result."""
    now = now or time.time()
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    its = items(uid)
    version = int(t.get("v", 0)) + 1
    local = datetime.datetime.fromtimestamp(now, _zone(uid))
    m = rmpapier.model(rmpapier.model_key(uid, d))
    built = build(m, its, version, t.get("receipt") or [], local.strftime("%d.%m.%Y"))
    r = await rmpapier.place(uid, "aufgaben", "Aufgaben", built, "aufgaben", own="aufgaben", auto=True)
    d = remarkable.load(uid)
    pp = d["papers"][r["id"]]
    pp["items"] = {x["key"]: {"src": x["src"], "id": x["id"], "text": x["text"]} for x in its}
    pp["v"] = version
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    t.update(v=version, receipt=[], renew=False, last=int(now), sig=_sig(its), day=local.strftime("%Y-%m-%d"))
    pr = [x["id"] for x in its if x["src"] == "praxis"]
    if pr:
        t["praxis"] = pr[0]
    d["tasks"] = t
    remarkable.save(uid, d)
    print(f"remarkable: task sheet | version {version}, {len(its)} point(s)", flush=True)
    return r


def thrown_away(uid):
    """The newest task sheet is gone from the device ("Kann weg" or deleted there): the Spark stops renewing it."""
    mine = [pp for pp in (remarkable.load(uid).get("papers") or {}).values() if pp.get("k") == "aufgaben"]
    return bool(mine) and bool(max(mine, key=lambda pp: int(pp.get("v", 0))).get("gone"))


def due(uid, now):
    """A new version is due: after the ticks were acted on, or once a day from the morning sheet's time when what
    is open changed. Never more often than RENEW_GAP."""
    t = remarkable.load(uid).get("tasks") or {}
    if not t.get("v"):
        return False          # the first one comes from the person (button or "Leg mir das Aufgabenblatt …")
    if thrown_away(uid):
        return False          # "Kann weg" ticked or deleted on the device: none by itself until the person asks again
    if now - int(t.get("last", 0)) < RENEW_GAP:
        return False
    if t.get("renew"):
        return True
    local = datetime.datetime.fromtimestamp(now, _zone(uid))
    at = profiles.settings(uid).get("rm_morning_at") or "06:30"
    if t.get("day") == local.strftime("%Y-%m-%d") or local.strftime("%H:%M") < at:
        return False
    return _sig(items(uid)) != t.get("sig")


# ---------------------------------------------------------------- reading it back (from rmpapier.check)
def pending(pp, now):
    """A read sheet whose ticks were not acted on yet and that has been quiet long enough."""
    return (pp.get("k") == "aufgaben" and bool(pp.get("r")) and int(pp.get("changed", 0)) > int(pp.get("acted", 0))
            and now - int(pp.get("changed", now)) >= QUIET)


def ready(pp, now):
    """Read and not acted on since: "Fertig" ticked, or quiet long enough."""
    if int(pp.get("changed", 0)) <= int(pp.get("acted", 0)):
        return False
    return (pp.get("r") or {}).get("fertig") == "an" or pending(pp, now)


def act(uid, pp, now):
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
        ticked = [k for k, _ in OPTS.get(it.get("src"), ()) if states.get(f"{key}|{k}") == "an"]
        if not ticked:
            continue
        if len(ticked) > 1:
            results.append({"text": it["text"], "res": "unklar"})
            continue
        if stop:
            results.append({"text": it["text"], "res": stop})
            continue
        try:
            res, u = _do(uid, it, ticked[0], now)
        except Exception as e:         # one point failing never stops the others
            print("remarkable: task point failed:", type(e).__name__, flush=True)
            res, u = "fehler", None
        results.append({"text": it["text"], "res": res})
        if res != "spaeter":
            done_keys.append(key)
        if u:
            undo.append({"i": f"{int(now)}{len(undo)}", "text": it["text"], "src": it["src"], "u": u})
        n += res in ("erledigt", "abgelehnt")
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


def _tomorrow_nine(uid, now):
    local = datetime.datetime.fromtimestamp(now, _zone(uid)) + datetime.timedelta(days=1)
    return int(local.replace(hour=9, minute=0, second=0, microsecond=0).timestamp() * 1000)


def _do(uid, it, choice, now):
    """One answer: (result, what "Zurücknehmen" needs or None)."""
    src, iid = it["src"], it["id"]
    if choice == "spaeter":
        return "spaeter", None
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
        if not gedaechtnis.on(uid):
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
        if not (admin(uid) and features.admin_on("berater")):
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


def undo(uid, i):
    """"Zurücknehmen" of one acted point. Returns True when it was taken back."""
    d = remarkable.load(uid)
    t = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
    x = next((u for u in t.get("undo") or [] if u["i"] == i), None)
    if not x:
        return False
    u = x["u"]
    if "rem" in u:
        profiles.remove_reminders(uid, {u["rem"]})
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
    d["tasks"] = t
    remarkable.save(uid, d)
    print("remarkable: task point taken back", flush=True)
    return True


def public(uid):
    t = remarkable.load(uid).get("tasks") or {}
    return {"on": features.allowed("rmaufgaben", uid), "spark": features.admin_on("rmaufgaben"), "version": t.get("v", 0),
            "open": len(items(uid)) if on(uid) else 0,
            "undo": [{"i": u["i"], "text": u["text"], "src": u["src"]} for u in (t.get("undo") or [])][::-1][:10]}
