"""Zustand per Sprache: the tool spark_zustand (plan werkzeug-abdeckung.md, Paket 4; Dominik 2026-10-13 „1-7 umsetzen“).

„Läuft alles?“, „Ist Home Assistant erreichbar?“, „Wann wurde zuletzt gesichert?“, „Gibt es ein Update?“, „Ist der
Notaus an?“, „Ist mein Postfach verbunden?“ had no tool: the model could only guess, or say all was well. This tool
reads what the panel already knows and answers with fixed words and numbers only:

- every profile: its own Mein Zustand (hintergrund.rows: background jobs, connected services, own devices and device
  updates; names are the ones the person gave), and whether its own Notaus or the Spark's Notaus is on;
- an admin (notaus.admin_uids, only as the own recognized profile, never a voice taken for someone else): the Dienst-
  Wächter (dienstwacht.overview), the newest backup, the installed version and what the last update check found
  (only the panel's memory: this tool never asks GitHub), the Notaus level.

Reading only, nothing is switched. Never a server's error text, address, mail subject or document text. Off by default:
admin switch chat.status_voice (it holds for every profile, no profile switch: Dominik 2026-10-13); never guests, never over MCP. Offered only when the
person's own words ask about the state (WORDS), and the Weiche group „zustand“ has the same words.
"""
import re
import time

import features

WORDS = re.compile(r"(?i)\b(läuft (noch )?alles|laeuft alles|alles in ordnung|erreichbar|ausgefallen|"
                   r"ausfall\w*|störung\w*|stoerung\w*|funktioniert (alles|der|die|das)|geht (alles|der|die|das) (noch|wieder)|"
                   r"zuletzt gesichert|letzte sicherung|sicherung\w*|backup\w*|gesichert|"
                   r"update\w*|aktualisierung\w*|welche version|version läuft|neue version|firmware|"
                   r"notaus|mein(en)? zustand|dienst-?wächter|wie geht es dem spark|"
                   r"verbunden|online|offline|is everything (running|ok)|reachable|backed up|is the emergency stop)\b")
PARTS = ("alles", "dienste", "sicherung", "version", "notaus", "mein")
TOOL = {"type": "function", "function": {
    "name": "spark_zustand",
    "description": "The Spark's own state, read by the panel: services (reachable or not), last backup, installed version "
                   "and whether an update is ready, the emergency stop, and the user's own background jobs, connected "
                   "services and devices. Answer only from this result, never guess that all is well.",
    "parameters": {"type": "object", "properties": {
        "teil": {"type": "string", "enum": list(PARTS), "description": "which part (default alles)"}}}}}
HINT = ("Fragt der Nutzer, ob beim Spark alles läuft, ob ein Dienst erreichbar ist, nach Sicherung, Version, Update, "
        "Notaus oder seinem eigenen Zustand, ruf spark_zustand und antworte nur aus dessen Ergebnis.")
# reads only the panel's own state; names are the ones the person gave its devices and accounts (chat.INSIDE)
INSIDE = {"spark_zustand"}
ST_WORD = {"ok": ("läuft", "running"), "wobble": ("wackelt", "unsteady"), "down": ("ausgefallen", "down"),
           "inet": ("ohne Internet", "no internet"), "new": ("noch nicht geprüft", "not checked yet"),
           "off": ("nicht beobachtet", "not watched")}
ROW_WORD = {"run": ("läuft gerade", "running now"), "wait": ("wartet", "waiting"), "ok": ("in Ordnung", "fine"),
            "bad": ("Problem", "problem"), "idle": ("ruht", "idle")}


def is_admin(uid):
    import notaus
    return bool(uid) and uid in notaus.admin_uids()


def _when(ts, now):
    if not ts:
        return "nie"
    ts = float(ts) / (1000 if ts > 10 ** 11 else 1)
    days = int((now - ts) // 86400)
    clock = time.strftime("%d.%m. %H:%M", time.localtime(ts))
    return f"{clock} (vor {days} Tagen)" if days >= 1 else f"heute {time.strftime('%H:%M', time.localtime(ts))}"


def services(now):
    import dienstwacht
    o = dienstwacht.overview(now)
    if not o["on"]:
        return "Dienst-Wächter: aus (Funktionen → Dienst-Wächter), Erreichbarkeit ist nicht bekannt."
    rows = [r for r in o["services"] if r["st"] != "off"]
    if not rows:
        return "Dienst-Wächter: an, aber kein Dienst eingerichtet."
    bad = [r for r in rows if r["st"] in ("down", "inet", "wobble")]
    parts = []
    for r in rows:
        line = f"{r['name'][0]}: {ST_WORD.get(r['st'], (r['st'],))[0]}"
        if r.get("since"):
            line += f" seit {time.strftime('%H:%M', time.localtime(r['since']))}"
        if r.get("parts") and r["parts"]["bad"]:
            line += f" ({r['parts']['bad']} von {r['parts']['n']} Adressen)"
        parts.append(line)
    head = "Alle beobachteten Dienste laufen." if not bad else f"{len(bad)} von {len(rows)} Diensten haben ein Problem."
    return head + " " + "; ".join(parts) + ("." if o.get("paused") is False else " (Prüfung gerade pausiert).")


def backup(now):
    import backup as bk
    rows = bk.listing()
    if not rows:
        return "Sicherung: noch keine auf dem Spark."
    last = rows[0]
    why = {"daily": "täglich", "manual": "von Hand", "offsite": "außer Haus", "before-restore": "vor dem Wiederherstellen"}.get(last.get("why"), "")
    return (f"Letzte Sicherung: {_when(last['created'], now)}" + (f", {why}" if why else "")
            + f", {len(rows)} Sicherungen auf dem Spark.")


def version():
    import core
    import update
    out = f"Installiert: {core.app_version()}."
    data = update._remote_cache.get("data")
    if not isinstance(data, dict) or not data.get("checked"):
        return out + " Ob es ein Update gibt, wurde seit dem Start noch nicht geprüft (Einstellungen → Update)."
    seen = time.strftime("%H:%M", time.localtime(data["checked"]))
    if data.get("error") and not data.get("latest"):
        return out + f" Die letzte Prüfung um {seen} kam zu keinem Ergebnis."
    behind = data.get("behind")
    if behind == 0:
        return out + f" Das ist die neueste geprüfte Version (Prüfung {seen})."
    newer = data.get("version") if re.fullmatch(r"V[\d.]{1,20}", str(data.get("version") or "")) else ""
    return out + " Ein Update ist bereit" + (f": {newer}" if newer else "") + (
        f", {behind} Änderungen" if isinstance(behind, int) and behind > 0 else "") + f" (Prüfung {seen})."


def emergency(uid, admin):
    import notaus
    lv = notaus.level()
    out = ("Notaus des Spark: aus." if not lv else f"Notaus des Spark: an, Stufe {lv}.") if admin else \
        ("" if not lv else "Der Spark ist im Notaus, manches geht gerade nicht.")
    if notaus.own(uid):
        out += " Dein eigener Notaus ist an."
    elif not admin:
        out += " Dein eigener Notaus ist aus."
    return out.strip()


def mine(uid, now):
    import hintergrund
    if not features.allowed("mystatus", uid):
        return "Mein Zustand: aus (Ich → Mein Zustand), dazu weiß ich nichts."
    rows = hintergrund.rows(uid, now)
    if not rows:
        return "Mein Zustand: nichts eingerichtet."
    out = []
    for r in rows[:30]:
        line = r["name"][0] + (f" „{r['label']}“" if r.get("label") else "") + ": " + ROW_WORD.get(r["state"], (r["state"],))[0]
        if r.get("why_text"):
            line += f" ({r['why_text'][0]})"
        elif r.get("detail") and r["detail"][0]:
            line += f" ({r['detail'][0]})"
        out.append(line)
    s = hintergrund.summary(rows)
    head = f"Mein Zustand: {s['ok']} in Ordnung, {s['wait']} wartend, {s['bad']} mit Problem"
    return head + (f", {s['need']} brauchen dich" if s.get("need") else "") + ". " + "; ".join(out) + "."


def text(uid, part="alles", now=None):
    now = time.time() if now is None else now
    part = part if part in PARTS else "alles"
    admin = is_admin(uid)
    out = []
    if part in ("alles", "dienste"):
        out.append(services(now) if admin else "Dienste des Spark sieht nur ein Admin.")
    if part in ("alles", "sicherung") and admin:
        out.append(backup(now))
    if part in ("alles", "version") and admin:
        out.append(version())
    if part in ("alles", "notaus"):
        out.append(emergency(uid, admin))
    if part in ("alles", "mein", "dienste"):
        out.append(mine(uid, now))
    if part in ("sicherung", "version") and not admin:
        out.append("Sicherung und Version sieht nur ein Admin (Einstellungen → Sicherung, Einstellungen → Update).")
    return " ".join(x for x in out if x)


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp" \
            or not features.allowed("sparkzustand", who["id"]):
        return None
    if not WORDS.search(str(ctx.get("text") or "")):
        return None
    return {"tools": [TOOL], "hint": HINT, "keep": {"spark_zustand"},
            "filler": {"spark_zustand": ("Ich schaue nach.", "Let me check.")}}


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    if name != "spark_zustand" or not features.allowed("sparkzustand", who.get("id")):
        return "Zustand per Sprache ist für dieses Profil aus."
    args = args if isinstance(args, dict) else {}
    out = text(who["id"], str(args.get("teil") or "alles"))
    print(f"zustand: gelesen teil={args.get('teil') if args.get('teil') in PARTS else 'alles'} "
          f"admin={'ja' if is_admin(who['id']) else 'nein'}", flush=True)
    return out
