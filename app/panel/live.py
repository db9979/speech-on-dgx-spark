"""Zustand → Live (V01.0.312): what the Spark does right now, for the admin and for a wall monitor.

Running requests with their way through the panel (from tracelog.Rec, also while Logs → Anfragen is off),
what the Wächter (netguard.py) decides for each outgoing connection and why, who came in from the
internet or was turned away (guard.failed, monitor pairing), what the tools gave back, open channels and
the machine's numbers, and how often Einordnung mit Wahrscheinlichkeit (systemone.py) asked the language model
today, per use. Everything lives in memory only and is gone after a restart.

Only fixed words, tool names, numbers and service names: never a question, an answer, tool arguments or
results, mail subjects, URLs with paths or secrets. Web pages from search results show as "Webseite",
not with their address; blocked addresses show (they are the reason). Senders from the internet are
shortened (89.204.x.x). A profile's name shows only with its consent (trace_name, as in Logs → Anfragen);
the monitor shows names only when the admin also allows it (logs.live_names), else "Person".

Off by default: admin switch logs.live (Einstellungen → Spark → Betrieb → Logs). The monitor page /live is
a second switch (logs.live_monitor): a screen in the home network pairs once with a 6-digit code (10 min,
one use) and then keeps a cookie that may only read /api/live/state. Requests from the internet are
refused (the monitor is for the home network). Monitors are kept as hashes in STATE/live-monitors.json,
unused ones expire after 90 days, deleting one cuts it off at once. At most logs.live_screens at a time.
"""
import contextlib
import contextvars
import functools
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import guard
from common import DayCounter, STATE, load_config, write_json
from core import auth

router = APIRouter()
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
FADE = 10                 # a finished request fades out this many seconds after a newer one came
MAX_RUN = 40              # requests watched at once (more: the oldest go)
CODE_S = 600              # a pairing code lasts 10 minutes
MAX_CODES, MAX_MONITORS = 5, 10
KEEP_DAYS = 90            # a monitor nobody used that long must pair again
SEEN_S = 6                # a monitor that asked within this many seconds counts as watching
COOKIE = "speech_spark_live"
NAME = re.compile(r"[A-Za-zÄÖÜäöüß0-9 ._-]{1,30}")
_lock = threading.RLock()

# Where each tool goes: a target of the picture. Every tool of chat.py and the extras must be here
# (tests/test_live.py), so a new tool shows on the monitor too (Dominik 2026-10-10: keep it current).
TOOLS = {
    "calendar_add": "cal", "calendar_events": "cal", "daily_briefing": "cal", "tasks_add": "cal", "tasks_change": "cal", "calendar_change": "cal",
    "agent_change": "mem", "home_rule_delete": "ha", "proactive_pause": "mem", "speaker_volume": "geraete", "undo_last": "mem",
    "tasks_show": "cal", "home_assistant": "ha", "home_assistant_action": "ha", "home_assistant_history": "ha", "camera_describe": "ha", "home_rules_list": "ha",
    "home_assistant_states": "ha", "home_assistant_todo": "ha", "web_search": "web", "read_page": "pages",
    "archive_search": "kiwix", "article_more": "wiki", "wikipedia": "wiki", "mail_draft": "mail", "mail_list": "mail",
    "mail_read": "mail", "mail_search": "mail", "mail_tidy_overview": "mail", "mail_tidy_propose": "mail",
    "fuer_dich": "mail", "fuer_dich_tun": "mail", "offen_zeigen": "cal",   # Offen lives on the Kalender node
    "contacts_search": "contacts", "remarkable_note": "rm", "remarkable_page": "rm", "remarkable_attachment": "rm", "remarkable_sent": "rm", "remarkable_sheet": "rm", "remarkable_library": "rm", "iphone_action": "push", "weather": "weather",
    "parcels": "parcels", "transit": "transit", "feeds_news": "feeds", "document_search": "mem", "document_list": "mem", "history_search": "mem", "local_search": "mem",
    "memory_forget": "mem", "memory_save": "mem", "reminder_cancel": "mem", "reminder_list": "mem", "reminder_set": "mem",
    "message_announce": "mem", "message_read": "mem", "message_send": "mem", "agent_list": "mem",
    "agent_schedule": "mem", "agent_task": "mem", "routine_save": "mem", "agent_watch": "mem",
    # inside a job (auftragsplan.py): plan, question and proposal stay on the Spark
    "job_plan": "mem", "job_propose": "mem", "job_ask": "mem",
    "spark_hilfe": "hilfe", "spark_vorschlag": "hilfe", "spark_tagebuch": "mem", "spark_zustand": "mem", "rechnen": "rechnen", "pc_action": "desk", "pc_send": "desk", "pc_look": "desk",
    # tools only programs use over MCP (mcpserver.py; transcribe/speak/voices show as Hören/Sprechen)
    "today": "cal", "action_status": "mem", "Vorschlag": "mem",
    # notes the Spark sends (push.py) and what it says by itself (proactive.py, live.note)
    "reMarkable": "rm",
    # what the Spark does by itself with services (live.job): update check, backup to the NAS
    "GitHub": "github", "NAS-Sicherung": "nas", "Feeds": "feeds", "Geräte-Updates": "geraete",
    "Speicher-Abgleich": "speicher", "Speicher holen": "speicher", "Wissensordner-Abgleich": "nasquelle",
    "Ablage-Eingang": "nasablage", "Ablegen": "nasablage", "nas_ablegen": "nasablage", "nas_zustand": "naszustand",
    # Docling-Server (doclingdienst.py): a document read a second time in a quiet moment
    "Docling": "docling",
    "Web Push": "webpush", "Apple Push": "push", "Android-App": "android", "Spark-Begleiter": "desk", "Telegram": "tg", "Panel-Seite": "page",
    # steps the panel runs itself (tracelog "… (Panel)")
    "Erst lokal": "mem", "remarkable": "rm", "Ablauf": "mem", "Nachsortieren": "mem",
    # Probleme melden (meldung.py): a draft stays on the Spark, sending goes to GitHub
    "Meldung": "mem", "GitHub-Meldung": "issues",
    # Dokumente erstellen (docmake.py): outline, change and status stay on the Spark; sending goes to its target
    "document_plan": "make", "document_change": "make", "document_status": "make", "document_send": "make",
    # Bilder malen (bilder.py): the picture is painted on the Spark (bild_server.py, 127.0.0.1)
    "bild_malen": "bild", "Bild malen": "bild", "Bild ändern (Panel)": "bild",
    # Musik machen (musik.py): the song is made on the model computer (musik_server.py)
    "musik_machen": "musik", "Musik machen": "musik", "musik_bearbeiten": "musik", "Musik bearbeiten": "musik",
    # Der Spark ruft an (telefon_anruf.py): planned on the Spark, the call goes through the PBX
    "anruf_planen": "telefon", "Anrufen lassen": "telefon",
    # the job itself (docmake._work): every part written by the language model, then the file built
    "document_write": "make", "document_build": "make",
    # before writing: the Kiwix article for the fact check and pictures (folien.py), the own documents
    "document_facts": "kiwix", "document_picture": "kiwix", "document_sources": "mem",
    # a finished document delivered (docmake.send): to the real target
    "Dokument → Begleiter": "desk", "Dokument → reMarkable": "rm", "Dokument → Telegram": "tg", "Dokument → Mail": "mail",
}
# The targets: name, short line, zone (spark = on this machine, lan = home network, net = internet), fixed = always shown
TARGETS = {
    "qwen": ("Sprachmodell qwen38", "LLM · auf dem Spark", "spark", True),
    "ha": ("Home Assistant", "HTTP · Heimnetz", "lan", True),
    "kiwix": ("Kiwix", "Archiv · Heimnetz", "lan", True),
    "mem": ("Spark-Speicher", "Dokumente, Erinnerungen", "spark", False),
    # SearXNG runs in the home network but asks search engines outside: the search words leave the house
    "web": ("Websuche", "SearXNG (Heimnetz) → Internet", "net", True),
    "pages": ("Webseiten", "aus Treffern · Internet", "net", False),
    "cal": ("Kalender", "CalDAV · Internet", "net", True),
    "mail": ("Mail", "IMAP · Internet", "net", True),
    "contacts": ("Kontakte", "CardDAV · Internet", "net", False),
    "wiki": ("Wikipedia", "HTTPS · Internet", "net", False),
    "weather": ("Wetter", "HTTPS · Internet", "net", False),
    "transit": ("Bahn", "HTTPS · Internet", "net", False),
    "parcels": ("Pakete", "HTTPS · Internet", "net", False),
    "feeds": ("Feeds", "Reddit und RSS · Internet", "net", False),
    "rm": ("reMarkable", "Cloud · Internet", "net", True),
    "push": ("Apple Push", "APNs · Internet", "net", True),
    "hilfe": ("Spark-Hilfe", "Anleitungen · auf dem Spark", "spark", False),
    # Rechnen mit festem Werkzeug (rechnen.py): the panel computes, nothing leaves the Spark
    "rechnen": ("Rechnen", "fester Rechner · auf dem Spark", "spark", False),
    "webpush": ("Web Push", "Push-Dienst des Browsers · Internet", "net", False),
    "tg": ("Telegram", "Bot-API · Internet", "net", False),
    "android": ("Android-App", "wartet, bis die App abholt", "spark", False),
    "desk": ("Spark-Begleiter", "wartet, bis PC oder Mac abholt", "spark", False),
    "page": ("Panel-Seite", "beim nächsten Abruf der offenen Seite", "spark", False),
    "github": ("GitHub (Updates)", "neuester Stand und Tests · Internet", "net", False),
    # NAS-Verbindungen (nas.py): shown while they are on, the line with connections and failed checks in numbers;
    # the backup to the NAS (offsite.py) goes here too
    "nas": ("NAS", "Verbindungen und Sicherung · Heimnetz", "lan", False),
    # Eigener Speicher (speicher.py): copies of profiles' data on their NAS, WebDAV service or a folder; counts only
    "speicher": ("Kopie meiner Daten", "an den Speicherorten · verschlüsselt", "lan", False),
    # Wissensordner (nasquelle.py): folders at the places read into the document search; numbers only
    "nasquelle": ("Wissensordner", "Ordner an den Speicherorten · nur lesen", "lan", False),
    # Ablage-Ordner (nasablage.py): spark_ablage at a place in the home network, written only there; numbers only
    "nasablage": ("Ablage-Ordner", "spark_ablage im Heimnetz · schreibt nur dort", "lan", False),
    # Zustand der NAS (naszustand.py): SNMPv3 reading of the own NAS, admin only; numbers only
    "naszustand": ("Zustand der NAS", "SNMPv3 · nur lesen · Heimnetz", "lan", False),
    # Gehäuse (gehaeuse.py): OLED and LEDs of the panel computer's case; numbers and status only
    "gehaeuse": ("Gehäuse", "Pironman 5 · am Panel-Rechner", "spark", False),
    # Steuerzentrale (schirm.py, steuerzentrale.py): the text screen on the panel computer's HDMI output; status only
    "schirm": ("Steuerzentrale", "Bildschirm am Panel-Rechner", "spark", False),
    # Werkstatt (werkstattseite.py): test runs, code measurement, diagnosis and repairs in the sandbox; kinds and counts
    "werkstatt": ("Werkstatt", "Sandbox · auf dem Modell-Rechner", "spark", False),
    # Rundlauf-Wächter (rundlauf.py): speaks, hears and asks the model every few minutes; times and fixed words only
    "rundlauf": ("Rundlauf", "Sprechen → Hören → Sprachmodell", "spark", False),
    # Docling-Server (doclingdienst.py): shown while it is on, the line with waiting and read files in numbers
    "docling": ("Docling-Server", "Dokumente lesen · Heimnetz", "lan", False),
    # the Dienst-Wächter (dienstwacht.py) looks at two fixed public addresses: shown while it is on, with its dot
    "inet": ("Internet", "erreichbar? zwei feste Adressen", "net", False),
    # firmware and apps for the devices (geraeteupdate.py): shown while that function is on, its line with the counts
    "geraete": ("Geräte-Updates", "Firmware und Apps · GitHub · Internet", "net", False),
    # tools of MCP services (mcp_… of the admin, mcpu_… a profile's own, meinmcp.py); the line under Ereignisse names the service
    "mcp": ("MCP-Dienste", "eigene und angebundene Dienste · Netz", "net", False),
    # Probleme melden (meldung.py): only after the person looked at the preview; the line shows counts, never text
    "issues": ("GitHub (Meldungen)", "Issues · Internet", "net", False),
    # Dokumente erstellen (docmake.py): the line shows jobs in numbers, never a title or text
    "make": ("Dokumente erstellen", "Aufträge · auf dem Spark", "spark", False),
    # Bilder malen (bilder.py, bild_server.py): the line shows pictures in numbers, never a wish or a prompt
    "bild": ("Bilder malen", "FLUX.2 klein · auf dem Spark", "spark", False),
    # Musik machen (musik.py, musik_server.py): shown while it is installed or on; songs and the measurement in numbers
    "musik": ("Musik machen", "ACE-Step 1.5 · auf dem Spark", "spark", False),
    # Einstellungs-Assistent (berater.py): shown while it is on, the line with 👍/👎, cases and proposals in numbers
    "verb": ("Verbessern", "Fälle und Vorschläge · auf dem Spark", "spark", False),
    # Gedächtnis prüfen (gedaechtnis.py): shown while it is on, the facts of all profiles by mark, numbers only
    "ged": ("Gedächtnis", "Einträge geprüft · auf dem Spark", "spark", False),
    # Rückfrage statt Raten (klaeren.py): shown while it is on, the line with questions and mappings in numbers
    "klaeren": ("Rückfrage und Merken", "Auswahl und Zuordnungen · auf dem Spark", "spark", False),
    # Chats (chats.py): shown while they are on, the line with chats, groups and today's messages in numbers
    "chats": ("Chats", "Nachrichten zwischen Personen · auf dem Spark", "spark", False),
    # Taten prüfen, Fehlerschleife stoppen (taten.py): shown while one is on, how often they stepped in today
    "taten": ("Taten-Prüfung", "zurückgehalten und gestoppt · auf dem Spark", "spark", False),
    # Suchprüfung (suchpruefung.py): shown while it is on, test questions and the share found in the first five
    "pruef": ("Suchprüfung", "Prüffragen und Trefferquote · auf dem Spark", "spark", False),
    # Wissensbuch (wissensbuch.py): shown while it is on, pages, sentences and documents waiting (numbers only)
    "wbuch": ("Wissensbuch", "Seiten aus den eigenen Dokumenten · auf dem Spark", "spark", False),
    # Wissenskarte (wissenskarte.py): shown while it is on, checked connections, discarded ones and documents waiting (numbers only)
    "wkarte": ("Wissenskarte", "Verbindungen zwischen Wissensbuch-Seiten · auf dem Spark", "spark", False),
    # KI-Dungeon-Master (dungeon.py): shown while it is on, rounds, players, guests, turns, loot and levels today (numbers only)
    "dungeon": ("Dungeon-Master", "Rollenspiel-Runden mit dem eigenen Sprachmodell · auf dem Spark", "spark", False),
    # Teilen mit Profilen (geteilt.py): shown while it is on, single shares and today's changes (numbers only)
    "geteilt": ("Geteilt", "Teilen mit Profilen · auf dem Spark", "spark", False),
    # Den Spark anrufen (telefon.py): the PBX in the home network; signed in, calls now and today in numbers, never a number
    "telefon": ("Telefonanlage", "SIP · Heimnetz", "lan", False),
    # Spark teilen (steuer.py): the DGX with the models while the panel runs on another computer; reachable, counts
    "modell": ("Modell-Rechner", "Sprache, LLM und Bilder · Heimnetz", "lan", False),
    # Spark teilen (rechnerblick.py): the computer the panel runs on, next to the model computer; numbers only
    "panelrechner": ("Panel-Rechner", "Panel und Dienste · Heimnetz", "spark", False),
}
RETURNS = {"cal": "Termine oder Aufgaben", "ha": "Zustände oder Schaltung", "web": "Suchergebnisse", "pages": "Seitentext", "kiwix": "Archiv-Treffer",
           "wiki": "Artikel", "mail": "Mails (nur Anzahl und Größe)", "contacts": "Kontakte", "rm": "Ablage", "push": "Zustellung",
           "weather": "Wetterwerte", "parcels": "Sendungen", "transit": "Verbindungen", "feeds": "Beiträge", "mem": "eigene Daten",
           "hilfe": "Anleitungen oder Vorschlagskarte", "rechnen": "Ergebnis", "webpush": "Zustellung", "tg": "Zustellung",
           "android": "liegt bereit", "desk": "liegt bereit", "page": "liegt bereit",
           "github": "Stand und Testergebnis", "nas": "Ablage bestätigt", "speicher": "Ablage bestätigt oder Datei geholt", "nasquelle": "Ordnerliste und Dateien", "nasablage": "Ablage bestätigt oder Datei geholt", "naszustand": "Belegung und Zustand in Zahlen", "docling": "Text des Dokuments", "mcp": "Antwort des Dienstes",
           "issues": "Nummer der Meldung", "make": "Gliederung, Auftrag oder Zustellung", "bild": "Bild (Größe und Sekunden)",
           "musik": "Lied (Länge und Sekunden)",
           "geraete": "Versionsnummern und geprüfte Dateien", "telefon": "Anruf und Ton"}
CLIENT = {"web": "Browser", "speaker": "Lautsprecher", "telefon": "Telefon", "watch": "Uhr", "siri": "Siri", "telegram": "Telegram",
          "app": "iPhone-App", "android": "Android-App", "car": "CarPlay", "mcp": "MCP-Client", "ha": "Home Assistant", "auto": "Von selbst", "desk": "Spark-Begleiter",
          "tui": "Terminal", "other": "Gerät"}
VOICE = ("speaker", "telefon", "watch", "siri", "app", "android", "car", "ha")
LEVEL = {"public": "Öffentlich (Seiten aus Suchergebnissen)", "user": "Nutzer-Dienst", "home": "Heimnetz"}

_run = {}                         # request id -> tracelog.Rec while it runs and FADE seconds after
_events = deque(maxlen=100)       # (t, area, text)
_hits = deque(maxlen=3000)        # (t, node, ok, ms) per finished step: the sheet of a node in the picture
_past = deque(maxlen=400)         # finished requests of the last REWIND seconds: Zurückspulen on the admin page
REWIND = 15 * 60
_guard = deque(maxlen=60)         # Wächter decisions
_door = deque(maxlen=60)          # who came in from the internet or was turned away
_rets = deque(maxlen=40)          # what tools gave back
_count = DayCounter()             # per day: guard_ok, guard_bad, guard_cut, door_in, door_out
_codes = {}                       # hash of a pairing code -> (until, name)
_seen = {}                        # monitor id -> (last time, address)
_saved = [0.0]                    # last time live-monitors.json was written for "last seen"


def _dungeon_regeln(c):
    """The Dungeon-Master's own rules (dungeon_regelseite.counts): numbers only."""
    if not c or not (c.get("eigene") or c.get("aus") or c.get("kandidaten")):
        return ""
    return f" · eigene Regeln {c['eigene']} Einträge, {c['aus']} ausgeblendet" + (f", {c['kandidaten']} neue Bilder zur Wahl" if c.get("kandidaten") else "")


def _gastkonten():
    """„Gäste mit E-Mail“ of the Dungeon-Master (dungeon_gast.counts): numbers only, never an address."""
    import dungeon_gast
    if not dungeon_gast.on():
        return ""
    c = dungeon_gast.counts()
    return (f" · {c['konten']} Gast-Konten ({c['zugmail']} mit Zug-Mail, {c['helden']} Helden), heute {c['codes_heute']} Codes, "
            f"{c['mails_heute']} Mails")


def _pruefstand():
    """The Dungeon-Master's balance bench (dungeon_pruefstand.counts): numbers only."""
    import dungeon_pruefstand
    if not dungeon_pruefstand.on():
        return ""
    c = dungeon_pruefstand.counts()
    return (f" · Prüfstand {c['zellen']} Felder, {c['unter']} unter und {c['ueber']} über dem Ziel" if c["zellen"] else " · Prüfstand noch ohne Lauf") + \
        (" · Prüfstand spielt gerade" if c["laeuft"] else "")


def target(name):
    """The target of a tool: from TOOLS, MCP tools (named per service) by their beginning."""
    if name.startswith(("mcp_", "mcpu_")):
        return "mcp"
    return TOOLS.get(name, "")


def cfg():
    return load_config().get("logs", {}) or {}


def on():
    return cfg().get("live", False) is True


def monitor_on():
    c = cfg()
    return c.get("live", False) is True and c.get("live_monitor", False) is True


def screens():
    try:
        return max(1, min(5, int(cfg().get("live_screens", 3))))
    except (TypeError, ValueError):
        return 3


def _bump(key, now=None):
    _count.bump(key, now=now or time.time())


def counts_today(now=None):
    """Zustand → Technik, Knoten-Seiten („heute“, technik_knoten.heute): today's counts, numbers only."""
    with _lock:
        return _count.counts(now or time.time())


def event(area, text, now=None):
    """One line for "Ereignisse": fixed words and numbers only. Also in the journal (Zustand → Logs → Diagnose,
    filter Ereignisse), whether Live is on or not: what Live shows, the log shows too (Dominik 2026-10-13)."""
    _journal(area, text)
    with _lock:
        _events.append((now or time.time(), area, str(text)[:120]))


def _journal(area, text):
    """The journal line of a Live event: the same fixed words, without line breaks; never raises."""
    try:
        print("ereignis: " + re.sub(r"\s+", " ", f"{area} | {text}")[:160], flush=True)
    except Exception:
        pass


def short_ip(ip):
    """89.204.x.x / 2a02:810::x: enough to tell senders apart, not enough to find a person."""
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return "?"
    if a.version == 4:
        return ".".join(str(a).split(".")[:2]) + ".x.x"
    return ":".join(a.exploded.split(":")[:2]) + "::x"


def sender(request):
    """Who sent it, for the picture only: the address after the trusted reverse proxy; a proxy in the home
    network that is not entered under panel.trusted_proxies still counts by its X-Forwarded-For here (Dominik
    2026-10-12: devices over speech.… belong under "Über das Internet"). Never used for a decision."""
    ip = guard.client_ip(request)
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd and not a.is_global and (a.is_private or a.is_loopback):
            last = fwd.split(",")[-1].strip()[:64]
            if ipaddress.ip_address(last.split("%")[0]).is_global:
                return last
    except (ValueError, AttributeError):
        pass
    return ip


def from_internet(request):
    """The sender (after the trusted reverse proxy) is a public address. For decisions (the monitor is refused):
    an X-Forwarded-For only counts from a listed proxy."""
    try:
        return ipaddress.ip_address(guard.client_ip(request)).is_global
    except ValueError:
        return False


def shown_outside(request):
    """For the picture only: came over the internet, also through a proxy that is not listed (sender())."""
    try:
        return ipaddress.ip_address(str(sender(request)).split("%")[0]).is_global
    except ValueError:
        return False


# ------------------------------------------------------------------ hooks (called by other modules; never raise)
def track(rec):
    """tracelog.Rec was created: watch it while it runs."""
    try:
        with _lock:
            _run[rec.id] = rec
            if len(_run) > MAX_RUN:
                for k in sorted(_run, key=lambda k: _run[k].t0)[:len(_run) - MAX_RUN]:
                    _run.pop(k, None)
    except Exception:
        pass


def came_in(request, rec):
    """A request's sender: from the internet it shows under "Über das Internet" and in the Eingang list."""
    try:
        if not shown_outside(request):
            return
        rec.net = True
        with _lock:
            _bump("door_in")
            _door.append({"t": time.time(), "ok": True, "who": CLIENT.get(rec.client, "Gerät"), "from": short_ip(sender(request)),
                          "why": "Anmeldung gültig, kam über den Proxy",
                          "steps": ["Absender aus X-Forwarded-For des eingetragenen Proxys (panel.trusted_proxies)"
                                    if from_internet(request) else
                                    "Absender aus X-Forwarded-For eines Proxys im Heimnetz, der nicht unter Einstellungen → Sicherheit „Reverse Proxy“ eingetragen ist",
                                    "Anmeldung oder Geräteschlüssel gültig", "Rate-Limit eingehalten"]})
    except Exception:
        pass


def key_call(request, who, why):
    """A device key call outside a chat request (Home Assistant events, hamelden.py): a line under
    "Ereignisse" and, from the internet, an entry in Eingang. Fixed words only."""
    try:
        event(who, why)
        if not shown_outside(request):
            return
        with _lock:
            _bump("door_in")
            _door.append({"t": time.time(), "ok": True, "who": who, "from": short_ip(sender(request)), "why": why,
                          "steps": ["Absender aus X-Forwarded-For des eingetragenen Proxys (panel.trusted_proxies)",
                                    "Geräteschlüssel gültig (Bereich haev)", "Rate-Limit eingehalten"]})
    except Exception:
        pass


def _weiche_today():
    """The Weiche's numbers of today (weiche.py: groups and counts only, never a question)."""
    try:
        import weiche
        return weiche.live_today()
    except Exception:
        return None


def step(rec, s):
    """A step was added to a watched request: tool steps also go to "Was die Dienste zurückgeben"."""
    try:
        x = s.get("x") or {}
        ok = x.get("ok", True) is not False
        node = {"asr": "asr", "weiche": "weiche", "llm": "llm", "tts": "tts", "ack": "tts"}.get(s["k"])
        if s["k"] == "tool":
            node = target(s["n"][:-8] if s["n"].endswith(" (Panel)") else s["n"]) or "tool"
        if node:
            with _lock:
                _hits.append((rec.t0 + (s["a"] + s["d"]) / 1000, node, ok, s["d"]))
                if s["k"] == "tool" and node != "tool":
                    _hits.append((rec.t0 + (s["a"] + s["d"]) / 1000, "tool", ok, s["d"]))
        if s["k"] != "tool":
            return
        name = s["n"][:-8] if s["n"].endswith(" (Panel)") else s["n"]
        tgt = target(name)
        chars = x.get("chars")
        with _lock:
            _rets.append({"t": rec.t0 + (s["a"] + s["d"]) / 1000, "req": rec.id, "tool": name, "to": tgt, "ok": ok,
                          "what": RETURNS.get(tgt, "Antwort"), "size": chars if isinstance(chars, int) else None, "ms": s["d"]})
            _events.append((time.time(), "Werkzeug", f"{rec.id} · {name} → {TARGETS[tgt][0] if tgt else 'Spark'}"
                                                      f"{'' if ok else ' · nicht ok'}"))
    except Exception:
        pass


def ended(rec, now=None):
    try:
        now = now or time.time()
        rec.t_end = now
        with _lock:
            _past.append(rec)
        status = rec.status()
        bad = next((e for e in rec.errors if str(e).startswith("llm_")), "")
        if bad or any(s["k"] == "llm" and s["n"].startswith("Runde") for s in rec.steps):
            llm_seen(not bad, bad, now)
        event("Anfrage", f"{rec.id} fertig in {max(0, now - rec.t0):.1f} s".replace(".", ",")
              + (f" · {rec.intent}" if rec.intent else "") + (" · Fehler" if status == "err" else ""), now)
    except Exception:
        pass


def outgoing(host, port, level, ip, why):
    """netguard.resolve decided about one connection (called in a worker thread)."""
    try:
        if not on():
            return
        try:
            a = ipaddress.ip_address(str(ip).split("%")[0])
        except ValueError:
            a = None
        public = bool(a and a.is_global)
        shown = "Webseite" if (level == "public" and not why) else str(host)[:60]
        if why:
            shown = f"{ip}:{port}"
        steps = [f"Name einmal aufgelöst → {'öffentliche Adresse' if public else 'Heimnetz- oder eigene Adresse'}",
                 f"Stufe {LEVEL.get(level, level)}"]
        if why:
            reason = ("Notaus ist an: keine Verbindung ins Internet" if why.startswith("Notaus")
                      else "eigene Dienste des Spark sind so nicht erreichbar" if "own services" in why
                      else "nur öffentliche Internet-Adressen" if "only public" in why
                      else "Heimnetz-Adressen sind für Nutzer-Dienste aus (Einstellungen → Sicherheit)" if "home network" in why
                      else "diese Adresse ist nie erlaubt (Link-lokal, Multicast, reserviert)")
            steps.append("→ geblockt, die Verbindung kommt nicht zustande")
        else:
            reason = ("öffentliche Adresse" if public else "Heimnetz-Adresse ist auf dieser Stufe erlaubt")
            steps += ["verbunden genau mit der geprüften Adresse (gegen DNS-Rebinding)", "Antwort-Grenze 20 MB"]
        with _lock:
            _bump("guard_bad" if why else "guard_ok")
            _guard.append({"t": time.time(), "ok": not why, "to": shown, "level": LEVEL.get(level, level), "why": reason, "steps": steps})
            if why:
                _events.append((time.time(), "Wächter", f"{shown} geblockt: {reason}"))
    except Exception:
        pass


def cut(host):
    """netguard: an answer was larger than allowed and was stopped."""
    try:
        if on():
            with _lock:
                _bump("guard_cut")
                _guard.append({"t": time.time(), "ok": None, "to": "Webseite", "level": "", "why": "Antwort größer als 20 MB, abgebrochen",
                               "steps": ["Antwort-Grenze 20 MB (auch entpackt)", "→ abgebrochen, nur bis dahin gelesen"]})
    except Exception:
        pass


def refused(request, what, locked=0):
    """guard.failed: a wrong login or code. Shown in the Eingang list (sender shortened)."""
    try:
        if not on():
            return
        word = {"login": "Anmeldung", "handoff_code": "Übergabe-Code", "live_code": "Monitor-Code", "profile_login": "Profil-Anmeldung",
                "mfa": "zweiter Schritt", "pin": "PIN", "review_code": "Prüf-Code"}.get(what, "Anmeldung")
        steps = [("kam aus dem Internet" if shown_outside(request) else "kam aus dem Heimnetz"), f"{word} falsch"]
        if locked:
            steps.append(f"→ Absender {int(locked) // 60 or 1} min gesperrt, steht im Admin-Protokoll")
        with _lock:
            _bump("door_out")
            _door.append({"t": time.time(), "ok": False, "who": word, "from": short_ip(sender(request)),
                          "why": f"{word} falsch" + (" · gesperrt" if locked else ""), "steps": steps})
            _events.append((time.time(), "Eingang", f"{word} falsch von {short_ip(sender(request))}"))
    except Exception:
        pass


BUS = ("rule", "timer", "job", "note")   # the sources of "Von selbst" on the bus in the picture (Dominik 2026-10-13, B1)


def begin(client, device, t=None, uid=None, auto=False, why="", request=None, src=None):
    """A request that does not go through the chat (Wyoming, MCP tools, rules that speak up): watched like
    one, written to Logs → Anfragen only when that switch is on. With uid it belongs to that profile (its
    name and the device name show only with its consent). auto: the Spark started it itself (no way back
    to a device); why: a fixed word shown like the Weiche's intent; request: where it came from; src: which
    input of the bus an auto request comes from (BUS: HA rules, the Spark's own schedule, jobs, notes). None while
    both are off; never raises."""
    try:
        import tracelog
        kind = "profile" if uid else "spark" if auto else "guest"
        rec = tracelog.start(time.time() if t is None else t, client, uid, kind, device,
                             ort=guard.client_ip(request) if request is not None else "")
        if rec is not None:
            rec.auto, rec.direct = bool(auto), True
            if auto:
                rec.src = src if src in BUS else "rule" if client == "ha" else "job"
                with _lock:
                    _bump("bus_" + rec.src)
            if why:
                rec.intent = str(why)[:40]
            if request is not None:     # from the internet: under "Über das Internet" and in Eingang
                came_in(request, rec)
        return rec
    except Exception:
        return None


def mark(area, text, now=None):
    """One line under "Ereignisse" from anywhere (fixed words and numbers only); nothing while Live is off,
    never raises."""
    try:
        if on():
            event(area, text, now)
        else:
            _journal(area, text)   # Live off: the journal line all the same
    except Exception:
        pass


def job(why, tool, t0, ok=True, uid=None, now=None, code=""):
    """Something the Spark did by itself with a service (update check, NAS backup, reMarkable sheet): a request
    of "Von selbst" with one step to the tool's target, shown like the others. code: a fixed word for why it
    failed (http_401, github_limit, …), shown in the request's line instead of a bare "error". never raises."""
    try:
        rec = begin("auto", "", t=t0, uid=uid, auto=True, why=why, src="job")
        if rec is None or not getattr(rec, "persist", False):   # no "anfrage:" line from Logs → Anfragen: one here
            grund = f" ({code})" if not ok and re.fullmatch(r"[a-z0-9_]{1,30}", str(code or "")) else ""
            _journal("Von selbst", f"{why} · {tool} {'ok' if ok else 'nicht ok'}{grund}")
        if rec is not None:
            rec.step("in", "Von selbst", t0)
            rec.step("tool", tool, t0, now or time.time(), ok=bool(ok))
            end(rec, bool(ok), code)
    except Exception:
        pass


def update_checked(data, t0):
    """update.remote_state asked GitHub (not from its cache): the way and the outcome in fixed words."""
    try:
        if not on():
            return
        err, behind, head = data.get("error"), data.get("behind"), data.get("head_state")
        why = data.get("why") or ""
        job("Update-Prüfung", "GitHub", t0, ok=not err, code=why)
        word = ("keine Version mit bestandenen Tests, nichts wird installiert" if err and data.get("no_green") else
                "GitHub-Grenze von 60 Abfragen pro Stunde erreicht, nichts wird installiert" if err and why == "github_limit" else
                "ohne git installiert, install.sh einmal aus einem git-Klon starten" if err and why == "ohne_git" else
                f"GitHub lehnt ab (HTTP {why[12:]}), nichts wird installiert" if err and why.startswith("github_http_") else
                "GitHub nicht erreichbar, nichts wird installiert" if err else
                "aktuell" if behind == 0 else
                f"neuere getestete Version {data.get('version') or ''}".strip() + (f" ({behind} Änderungen)" if isinstance(behind, int) and behind > 0 else ""))
        try:
            import ghtoken
            word += " · " + ghtoken.used()
        except Exception:
            pass
        if not err and head in ("running", "red"):
            word += " · neuester Stand: " + ("Tests laufen" if head == "running" else "Tests rot oder abgebrochen")
            if data.get("red_since"):
                word += time.strftime(" · rot seit %d.%m. %H:%M", time.localtime(data["red_since"]))
        event("Update", "Prüfung: " + word)
    except Exception:
        pass


_cur = contextvars.ContextVar("live_rec", default=None)


def current():
    """The watched request this code runs for (set with within), or None."""
    return _cur.get()


@contextlib.contextmanager
def within(rec):
    """Steps that code further down adds (a note by push.py) go to this request instead of one of their own."""
    tok = _cur.set(rec)
    try:
        yield rec
    finally:
        _cur.reset(tok)


NOTE = {"web": "Web Push", "app": "Apple Push", "and": "Android-App", "desk": "Spark-Begleiter", "tg": "Telegram",
        "page": "Panel-Seite"}


def note(uid, kind, t0, n, why=""):
    """push.py sent a note ("web", "app", "and", "tg"; "page" when the open page shows it): a step on the
    request that asked for it, else a request of its own from "Von selbst"."""
    try:
        if kind not in NOTE:
            return
        rec, own = current(), None
        if rec is None:
            rec = own = begin("auto", "", t=t0, uid=uid, auto=True, why=why or "Benachrichtigung", src="note")
            if rec is not None:
                rec.step("in", "Von selbst", t0)
        if rec is not None:
            rec.step("tool", NOTE[kind], t0, time.time(), ok=n > 0)
        if own is not None:
            end(own, n > 0)
    except Exception:
        pass


def end(rec, ok=True, code=""):
    try:
        import tracelog
        if rec is not None:
            if not ok:
                rec.fail(code if re.fullmatch(r"[a-z0-9_]{1,30}", str(code or "")) else "error")
            tracelog.finish(rec)
    except Exception:
        pass


def door(who, ip, ok, why, steps):
    """One line in the Eingang list for a way in that is not a login (Wyoming, MCP, devices)."""
    try:
        if not on():
            return
        with _lock:
            _bump("door_in" if ok else "door_out")
            _door.append({"t": time.time(), "ok": ok, "who": str(who)[:40], "from": short_ip(ip), "why": str(why)[:80],
                          "steps": [str(x)[:100] for x in steps][:5]})
            if not ok:
                _events.append((time.time(), "Eingang", f"{str(who)[:40]} abgewiesen von {short_ip(ip)}"))
    except Exception:
        pass


def _door_no(request, why, steps):
    with _lock:
        _bump("door_out")
        _door.append({"t": time.time(), "ok": False, "who": "Monitor", "from": short_ip(sender(request)), "why": why, "steps": steps})


# ------------------------------------------------------------------ the picture
def _now_at(rec, now):
    """Where the request is right now: the step after the last finished one (or the running tool)."""
    if getattr(rec, "t_end", None):
        return "done", ""
    cur = getattr(rec, "cur", None)
    last = rec.steps[-1] if rec.steps else None
    if cur and (not last or cur[2] >= rec.t0 + (last["a"] + last["d"]) / 1000 - 0.01):
        return cur[0], cur[1]
    k = last["k"] if last else "in"
    if getattr(rec, "direct", False):    # no Weiche and no language model unless a step says so
        return k, ""
    if k in ("in", "prep"):
        return "weiche", ""
    if k in ("weiche", "tool", "ack"):   # (the instant sentence plays while the model reads)
        return "llm", ""
    if k in ("llm", "check"):
        return ("tts", "") if "first" in rec.marks else ("llm", "")
    return k, ""


def _who(rec, view):
    """(person, device) as this view may show them."""
    if rec.kind == "admin":
        return "Admin", rec.device if view == "admin" else ""
    if rec.kind == "spark":
        return "Spark", ""
    if rec.kind != "profile" or not rec.who:
        return "Gast", ""
    name, named = _person(rec.who, view)
    if getattr(rec, "peer", ""):    # a call in a chat (anrufe.py): both people, each name only with its own consent
        return name + " ↔ " + _person(rec.peer, view)[0], ""
    return name, rec.device if named else ""


def _person(uid, view):
    """(name, named): a profile's name as this view may show it."""
    import profiles
    p = profiles.by_id(uid)
    if p and profiles.settings(p["id"]).get("trace_name") is True and (view == "admin" or cfg().get("live_names") is True):
        return p["name"], True
    return ("Profil" if view == "admin" else "Person"), False


def _gone_from(rec):
    """When a finished request starts to fade: once a newer request came (Dominik 2026-10-10: the last action
    stays until something new comes), never before it ended. None while it is the newest."""
    end = getattr(rec, "t_end", None)
    if not end:
        return None
    newer = [r.t0 for r in _run.values() if r is not rec and r.t0 > rec.t0]
    return max(end, min(newer)) if newer else None


def _req(rec, view, now):
    stage, tool = _now_at(rec, now)
    person, device = _who(rec, view)
    steps = []
    for s in rec.steps:
        n = s["n"][:-8] if s["n"].endswith(" (Panel)") else s["n"]
        x = s.get("x") or {}
        steps.append({"k": s["k"], "n": n, "a": s["a"], "d": s["d"], "ok": x.get("ok", True) is not False,
                      "to": target(n) if s["k"] == "tool" else ("qwen" if s["k"] == "llm" else "")})
    end, gone = getattr(rec, "t_end", None), _gone_from(rec)
    return {"id": rec.id, "client": rec.client, "dev": getattr(rec, "label", "") or device or CLIENT.get(rec.client, "Gerät"), "who": person,
            "voice": not getattr(rec, "auto", False) and (rec.client in VOICE or any((s.get("x") or {}).get("voice") for s in rec.steps[:1])),
            "auto": bool(getattr(rec, "auto", False)), "src": getattr(rec, "src", "") if getattr(rec, "auto", False) else "", "direct": bool(getattr(rec, "direct", False)),
            "prio": bool(getattr(rec, "prio", False)),
            "call": getattr(rec, "call", ""),   # a question in a phone call (telefon.py): drawn on the call's card
            "quiet": bool(getattr(rec, "quiet", False)),   # text only, no speech (Antworten vorlesen aus)
            "net": bool(getattr(rec, "net", False)), "intent": rec.intent, "stage": stage, "tool": tool,
            "to": target(tool) if stage == "tool" else ("qwen" if stage == "llm" else ""),
            "steps": steps, "marks": dict(rec.marks), "age": round((end or now) - rec.t0, 2),
            "done": bool(end), "left": max(0, int(FADE - (now - gone))) if gone else None, "last": bool(end and not gone),
            "ago": int(now - end) if end else None, "err": bool(rec.errors)}


def _calls(reqs):
    """One card per call (Dominik 2026-10-22: one call showed three phones): each question asked in a phone call is a
    request of its own (chat) with the call's id; the picture draws it on the call's card, the card counts them."""
    by = {r["id"]: r for r in reqs}
    for r in reqs:
        p = by.get(r["call"]) if r["call"] != r["id"] else None
        if p is None or p["call"]:
            r["call"] = ""
        else:
            p["fragen"] = p.get("fragen", 0) + 1


def _conns(now):
    out = []
    try:
        import esp32
        n = len(getattr(esp32, "_live", {}) or {})
        if n:
            out.append({"name": "Lautsprecher", "proto": "WebSocket", "dir": "ein", "n": n})
        # "Stopp beim Vorlesen": speakers that speak right now with their microphone on (only the count)
        n = sum(1 for x in list(getattr(esp32, "_live", {}).values())
                if getattr(x, "stop_on", False) and x.answer and not x.answer.done())
        if n:
            out.append({"name": "Lautsprecher hört auf „Stopp“", "proto": "Mikrofon beim Sprechen", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import telefon
        n = telefon.state()["calls"]
        if n:
            out.append({"name": "Telefon", "proto": "SIP und RTP", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        # Anrufe im Chat (anrufe.py, Browser und Apps): talking and ringing now, only the counts
        import anrufe
        a = anrufe.for_live()
        for name, k in (("Anruf im Chat", "talking"), ("Anruf klingelt", "ringing")):
            if a.get(k):
                out.append({"name": name, "proto": "WebRTC", "dir": "ein", "n": int(a[k])})
    except Exception:
        pass
    try:
        import begleiter
        n = sum(1 for t in list(getattr(begleiter, "_seen", {}).values()) if now - t < 3 * getattr(begleiter, "POLL", 30))
        if n:
            out.append({"name": "Spark-Begleiter (PC/Mac)", "proto": "fragt alle 30 s nach", "dir": "ein", "n": n})
        # "Mikrofon zu" at the companion (only the count of online programs with the switch closed)
        seen = getattr(begleiter, "_seen", {})
        n = sum(1 for d in list(getattr(begleiter, "_mic", {})) if now - seen.get(d, -1e12) < 3 * getattr(begleiter, "POLL", 30))
        if n:
            out.append({"name": "Begleiter mit Mikrofon zu", "proto": "Schalter am PC/Mac", "dir": "aus", "n": n})
    except Exception:
        pass
    try:
        # Mitteilung ans genutzte Gerät (zustellung.py): devices in use right now, notes routed and followed up today and
        # notes waiting for their follow-up, only the counts
        import zustellung
        z = zustellung.for_live(now)
        if z["on"] and (z["devices"] or z["aktiv"] or z["handy"] or z["nachgefasst"] or z["warten"]):
            out.append({"name": "Gerade benutzte Geräte", "proto": f"Mitteilungen heute: {z['aktiv']} ans benutzte Gerät, "
                        f"{z['handy']} ans Handy, {z['nachgefasst']} nachgefasst, {z['warten']} warten", "dir": "ein",
                        "n": z["devices"]})
    except Exception:
        pass
    try:
        # Bildschirm zeigen und bedienen (fernsicht.py): running sessions by kind, only the counts
        import fernsicht
        c = fernsicht.counts()
        for name, k in (("Bildschirm ansehen", "view"), ("Bildschirm bedienen", "control"), ("Bildschirm gefragt", "asked"),
                        ("Spark bedient Rechner", "operate"), ("Spark sieht Bildschirm", "look")):
            if c.get(k):
                out.append({"name": name, "proto": "Bilder über das Panel · Begleiter", "dir": "aus", "n": int(c[k])})
    except Exception:
        pass
    try:
        import terminal
        n = terminal.online(now)
        if n:
            out.append({"name": "Terminal-Client", "proto": "HTTPS · meldet sich jede Minute", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import roomlive
        n = len(roomlive.everybody())
        if n:
            out.append({"name": "Raum-Modus hört zu", "proto": "Mikrofon · Gerät im Raum", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import telegram
        if (getattr(telegram, "_poller", {}) or {}).get("on"):
            out.append({"name": "Telegram", "proto": "Long-Poll · Internet", "dir": "aus", "n": 1})
    except Exception:
        pass
    try:
        import mcpserver
        n = sum(1 for v in (getattr(mcpserver, "_busy", {}) or {}).values() if v)
        if n:
            out.append({"name": "MCP-Clients", "proto": "HTTPS", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import hamelden
        n = sum(1 for x in list((getattr(hamelden, "_streams", {}) or {}).values()) if x.synced and not x.error)
        if n:
            out.append({"name": "Home Assistant live", "proto": "WebSocket · Heimnetz", "dir": "aus", "n": n})
    except Exception:
        pass
    try:
        import chats
        n = chats.streams()
        if n:
            out.append({"name": "Chats (sofort)", "proto": "HTTPS · Ereignisse", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import android
        n = android.live_count()
        if n:
            out.append({"name": "Android-App (sofort)", "proto": "HTTPS · wartende Anfrage", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import verlauf
        n = verlauf.streams()
        if n:
            out.append({"name": "Verlauf-Abgleich", "proto": "HTTPS · Ereignisse", "dir": "ein", "n": n})
    except Exception:
        pass
    n = sum(1 for t, _ in _seen.values() if now - t < SEEN_S)
    if n:
        out.append({"name": "Live-Monitore", "proto": "HTTPS · nur lesen", "dir": "ein", "n": n})
    run = [r for r in _run.values() if not getattr(r, "t_end", None)]
    if run:
        out.append({"name": "Laufende Anfragen", "proto": "HTTPS / WebSocket", "dir": "ein", "n": len(run)})
    return out


# ------------------------------------------------------------------ the services' state (Hören, Sprechen, Sprachmodell)
_svc = {}       # "asr" | "tts" | "qwen" -> (state ok|load|down|off, word, time)
_queue = {}     # "asr" | "tts" -> (waiting, running) from the front end's gate (common.Gate.view)
SVC_WORD = {"ok": "läuft", "load": "lädt", "down": "antwortet nicht", "off": "aus"}


def services(health, cfg, now=None):
    """The sampler (panel.py, every 3 s) read the front ends' /health: a dot on Hören and Sprechen."""
    now = time.time() if now is None else now
    for name, h in health.items():
        if name not in ("asr", "tts"):
            continue
        st = "off" if not (cfg.get(name) or {}).get("enabled", True) else "down" if not isinstance(h, dict) \
            else "down" if h.get("status") in ("blocked", "error") else "load" if h.get("status") == "loading" else "ok"
        old = _svc.get(name)
        _svc[name] = (st, SVC_WORD[st], now)
        q = (h or {}).get("queue") if isinstance(h, dict) else None
        num = lambda v: v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10000 else 0  # noqa: E731
        _queue[name] = (num(q.get("waiting")), num(q.get("running"))) if isinstance(q, dict) else (0, 0)
        if (old[0] if old else "ok") != st and on():
            event("Dienste", f"{'Hören' if name == 'asr' else 'Sprechen'}: {SVC_WORD[st]}", now)


# ------------------------------------------------------------------ background work (vorrang.py)
_bg = {}        # job name (fixed words from the code) -> (state wait|run, since)
BG_MAX = 12


def _spitze(sp):
    """Rechner boxes: the service (the panel: its part) that takes the most CPU (rechnerblick.spitze), fixed names."""
    return f" · am meisten {sp['name']} {_n(sp.get('pct'))} %" if isinstance(sp, dict) and sp.get("name") else ""


def bg(job, state, now=None):
    """vorrang.py: a background job waits for a pause (wait), runs (run) or is gone (None)."""
    now = time.time() if now is None else now
    job = str(job)[:40]
    with _lock:
        if state is None:
            _bg.pop(job, None)
        elif state in ("wait", "run"):
            if job in _bg or len(_bg) < BG_MAX:
                _bg[job] = (state, _bg[job][1] if job in _bg and _bg[job][0] == state else now)


def bg_done(job, ok, secs=None, why=""):
    """A background job ended: off the list, a line under "Ereignisse"."""
    job = str(job)[:40]
    with _lock:
        _bg.pop(job, None)
    if on():
        event("Hintergrund", f"{job} " + ("fertig" if ok else why or "nicht fertig")
              + (f" in {secs:.0f} s" if ok and isinstance(secs, (int, float)) else ""))


def _bg_now(now):
    with _lock:
        for k in [k for k, v in _bg.items() if now - v[1] > 6 * 3600]:    # a job that never said it ended
            _bg.pop(k, None)
        out = [{"job": k, "st": v[0], "secs": int(now - v[1])} for k, v in sorted(_bg.items(), key=lambda x: x[1][1])]
    try:   # the meaning search model (docembed.py) while it works on documents or a question
        import docembed
        if docembed._busy():
            out.append({"job": "Bedeutungssuche", "st": "run", "secs": 0})
    except Exception:
        pass
    try:   # the re-ranking model (nachsortieren.py) while it reads question and passages
        import nachsortieren
        if nachsortieren.busy():
            out.append({"job": "Nachsortieren", "st": "run", "secs": 0})
    except Exception:
        pass
    try:   # pictures and songs on the model computer (schwer.py): waiting for a pause, for the one place or for
        import schwer   # memory, or being made; never a wish
        out += schwer.busy(now)
    except Exception:
        pass
    return out


def llm_seen(ok, code="", now=None):
    """A request used the language model (ended): its state as the last answer showed it."""
    now = time.time() if now is None else now
    st = "ok" if ok else "load" if code == "llm_slow" else "down"
    old = _svc.get("qwen")
    _svc["qwen"] = (st, SVC_WORD[st] if ok or code in ("llm_down", "llm_slow") else "Fehler", now)
    if (old[0] if old else "ok") != st:
        event("Dienste", f"Sprachmodell: {_svc['qwen'][1]}", now)
    if st == "down":
        try:   # the Dienst-Wächter looks at it in its next round
            import dienstwacht
            dienstwacht.saw("qwen")
        except Exception:
            pass


def restarted(name, reason, done):
    """The watchdog (health.py) restarted a service, or would have but may not."""
    event("Dienste", f"{name} {'neu gestartet' if done else 'nicht neu gestartet'} · {str(reason)[:60]}")


def _svc_now(now):
    return {k: dict({"st": v[0], "word": v[1], "ago": int(now - v[2])},
                    **({"wait": _queue[k][0], "run": _queue[k][1]} if k in _queue else {}))
            for k, v in _svc.items() if now - v[2] < 3600}


# ------------------------------------------------------------------ the Spark's own warnings (health.alerts)
_hint_cache = [0.0, []]
_hint_seen = set()
LIVECHECK_AT = {"llm": "llm", "tools": "tool", "search": "web", "tts": "tts", "asr": "asr"}


def _num(v):
    return f"{v:g}".replace(".", ",") if isinstance(v, (int, float)) else "?"


# Dominik 2026-10-12: a target that is not set up (its function off, no address, no profile connected) is not shown
# at all, not even in "+ N ruhig"; once a request goes there it shows like any used target
SETUP = {"web": "search", "cal": "calendar", "mail": "mail", "ha": "ha", "kiwix": "kiwix", "rm": "remarkable",
         "push": "iphonepush", "wiki": "wiki", "weather": "weather", "transit": "transit", "parcels": "parcels", "feeds": "feeds", "tg": "telegram"}
SETUP_FILE = {"cal": "calendar.json", "mail": "mail.json", "ha": "homeassistant.json", "rm": "remarkable.json", "feeds": "feeds.json"}
_unset = [0.0, frozenset()]


def unset(now=None):
    """Target ids that are not set up, checked at most every 30 s (each check alone; one that fails counts as set up)."""
    now = now or time.time()
    if now - _unset[0] < 30:
        return _unset[1]
    out = set()
    try:
        import features
        import profiles
        c = features.chat_cfg()
        ids = profiles.user_ids()
    except Exception:
        return _unset[1]
    for t, key in SETUP.items():
        try:
            if not features.admin_on(key, c):
                out.add(t)
            elif t == "web" and not str(c.get("search_url") or "").strip():
                out.add(t)
            elif t == "push":
                import apns
                if not apns.ready():
                    out.add(t)
            elif t in SETUP_FILE and not any(os.path.exists(profiles._path(u, SETUP_FILE[t])) for u in ids):
                out.add(t)
        except Exception:
            pass
    _unset[:] = [now, frozenset(out)]
    return _unset[1]


def hints(now=None):
    """The warnings the admin pages show on top (health.alerts), at the part of the picture they are about
    (Dominik 2026-10-10: "Antworten sind langsamer geworden" belongs to its connection). Fixed words and
    numbers only: the quality test's question or a server's error text never come here."""
    now = time.time() if now is None else now
    if 0 <= now - _hint_cache[0] < 5:
        return _hint_cache[1]
    out = []
    try:
        import health
        m = health.memory_state
        if m.get("low"):
            out.append({"at": "llm", "level": "bad", "word": f"Speicher knapp: {_num(round(m.get('avail') or 0, 1))} GiB frei"})
        for e in [e for e in health.events if now - e.get("t", 0) < 3600][-3:]:
            at = "asr" if str(e.get("unit", "")).upper().startswith("ASR") else "tts"
            out.append({"at": at, "level": "warn" if e.get("done") else "bad",
                        "word": "vom Wächter neu gestartet" if e.get("done") else "hängt, Neustart-Grenze erreicht"})
        lc = health.last_live()
        if lc and not lc.get("ok") and now - lc.get("t", 0) < 86400:
            for st in lc.get("steps", []):
                if st.get("ok") is False and st.get("name") in LIVECHECK_AT:
                    out.append({"at": LIVECHECK_AT[st["name"]], "level": "bad", "word": "Funktionsprüfung fehlgeschlagen"})
        import quality
        res = quality.last()
        if res and res.get("cases") and now - res.get("t", 0) < 7 * 86400:
            n = sum(1 for x in res["cases"] if x.get("new"))
            if n:
                out.append({"at": "llm", "level": "warn", "word": f"Qualitätstest: {n} neu kaputt"})
        import latency
        sm = latency.summary(now)
        if sm.get("warn"):
            out.append({"at": "tts", "level": "warn", "word": f"erster Ton {_num(sm['day']['median'])} s statt "
                                                               f"{_num(sm['week']['median'])} s"})
        import geraeteupdate
        h = geraeteupdate.hint()
        if h:
            out.append(h)
        import telegram
        if telegram.alert():
            out.append({"at": "tg", "level": "warn", "word": "Bot-Token wird woanders auch benutzt"})
        import meldung
        mh = meldung.live_hint(now)
        if mh:
            out.append({"at": "issues", "level": "warn", "word": mh})
    except Exception:
        pass
    for h in out:          # a warning that is new: one line under "Ereignisse"
        key = h["at"] + h["word"].split(":")[0]
        if key not in _hint_seen:
            _hint_seen.add(key)
            event("Hinweis", f"{h['word']}", now)
    for key in list(_hint_seen):
        if not any(h["at"] + h["word"].split(":")[0] == key for h in out):
            _hint_seen.discard(key)
    _hint_cache[:] = [now, out]
    return out


def _upd(now):
    """The Spark's own update (update.py): running with its step and share, the last one's outcome within the
    hour, and whether "Heute Nacht einspielen" is on. Fixed words from the update steps and numbers only."""
    try:
        import update
        p = update.update_progress() or {}
        run = bool(update.update_running())
        out = {"run": run, "night": update.night_on()}
        if run or (p.get("done") and isinstance(p.get("updated"), (int, float)) and 0 <= now - p["updated"] < 3600):
            out.update(pct=int(p.get("percent") or 0), step=str(p.get("text") or "")[:60],
                       ver=str(p.get("version") or "")[:20], ok=p.get("ok") if p.get("done") else None,
                       secs=int(now - p["started"]) if isinstance(p.get("started"), (int, float)) else None)
        g = update.gesamt(now)     # both computers as one bar (Dominik 2026-10-18): TARS first, then this one
        if g and g["run"]:
            out.update(pct=g["pct"], step=(g["teil"] + ": " if g["teil"] else "") + g["step"], teil=g["teil"])
        return out
    except Exception:
        return {"run": False}


def _n(v, nach=0):
    """A number for a box line in German style ("-" when unknown)."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "-"
    return f"{v:.{nach}f}".replace(".", ",")


def _sys():
    try:
        import monitor
        h = list(monitor.history)[-60:]
    except Exception:
        h = []
    last = h[-1] if h else {}
    num = lambda v: round(v, 1) if isinstance(v, (int, float)) else None  # noqa: E731
    out = {"gpu": num(last.get("gpu")), "cpu": num(last.get("cpu")), "free": num(last.get("avail")), "temp": num(last.get("temp")),
           "power": num(last.get("power")), "hist": {k: [num(x.get(k)) for x in h] for k in ("gpu", "cpu", "avail")}}
    try:      # models on another computer: the numbers above are its; the panel computer's CPU next to them
        import rechnerblick
        if rechnerblick.an():
            c = rechnerblick.kurven("panel")["cpu"][-60:]
            out["pi"] = {"cpu": num(c[-1]) if c else None, "hist": [num(x) for x in c]}
    except Exception:
        pass
    return out


def node_stats(now=None):
    """Per node of the picture in the last hour: steps, failures, mean time and the last ten (ok or not).
    Numbers only, for the sheet that opens when the admin clicks a node."""
    now = time.time() if now is None else now
    out = {}
    with _lock:
        hits = [h for h in _hits if now - h[0] < 3600]
    for t, node, ok, ms in hits:
        x = out.setdefault(node, {"n": 0, "bad": 0, "ms": 0, "last": []})
        x["n"] += 1
        x["bad"] += 0 if ok else 1
        x["ms"] += ms
        x["last"] = (x["last"] + [ok])[-10:]
    for x in out.values():
        x["ms"] = int(x["ms"] / x["n"]) if x["n"] else 0
    return out


def past_reqs(view="admin", now=None):
    """Finished requests of the last REWIND seconds for Zurückspulen: the same fixed words and numbers as
    the picture, with their start and end time so the page can play them again."""
    now = time.time() if now is None else now
    with _lock:
        recs = [r for r in _past if now - (getattr(r, "t_end", None) or now) < REWIND]
    out = []
    for r in recs:
        x = _req(r, view, r.t_end)
        x.update(t0=round(r.t0, 2), te=round(r.t_end, 2), left=None, last=False, ago=None)
        out.append(x)
    return out


# the warnings at a node (hints): one sentence what it means and which page helps (goSec name)
EXPLAIN = (("Speicher knapp", "Weniger freier Speicher als die Reserve: Dienste können abstürzen. Läuft qwen38 oder "
            "ein anderer großer Dienst gerade?", "mon"),
           ("vom Wächter neu gestartet", "Der Dienst hat nicht mehr geantwortet, der Wächter hat ihn neu gestartet. "
            "Die Logs zeigen, was davor passierte.", "logs"),
           ("hängt", "Der Dienst antwortet nicht und der Wächter darf ihn diese Stunde nicht mehr neu starten.", "logs"),
           ("Funktionsprüfung", "Die regelmäßige Prüfung von Hören, Weiche, Modell und Sprechen ist hier gescheitert.", "test"),
           ("Qualitätstest", "Fragen, die früher richtig beantwortet wurden, gehen jetzt schief.", "test"),
           ("erster Ton", "Bis zum ersten Ton dauert es heute länger als sonst. Meist läuft qwen38 gerade viel oder "
            "der Speicher ist knapp.", "test"),
           ("Bot-Token", "Ein zweites Programm benutzt denselben Telegram-Bot: Nachrichten gehen verloren.", "apps"),
           ("antwortet nicht seit", "Der Dienst-Wächter erreicht diesen Dienst seit dieser Zeit nicht. Die Admins haben einen "
            "Hinweis bekommen; Zustand → Dienste zeigt den Verlauf.", "mon"),
           ("wegen Internet", "Das Internet ist weg, dieser Dienst liegt dahinter. Er bekommt keinen eigenen Hinweis.", "mon"))


def _explain(h):
    w = h.get("word", "")
    for key, why, go in EXPLAIN:
        if key in w:
            return dict(h, why=why, go=go)
    return dict(h, why=h.get("why") or "", go=h.get("go") or ("prof" if h.get("at") == "geraete" else "feat" if h.get("at") == "issues" else "mon"))


# Dominik 2026-10-16 ("nur aktuell benutzte anzeigen"): the right column shows a box only for a target that works
# right now, was used in the last RECENT seconds or has a warning; the others are "quiet" and fold into "+ N bereit"
# (home and Spark) or "+ N ruhig" (internet). The language model always keeps its box: the LLM stage points at it.
RECENT = 15 * 60
ALWAYS = frozenset({"qwen"})


def ruhe(targets, busy, now=None):
    """Sets "ago" (seconds since the last step there within RECENT, else None) and "quiet" on every target."""
    now = time.time() if now is None else now
    last = {}
    with _lock:
        for t, node, _ok, _ms in _hits:
            if 0 <= now - t < RECENT and t > last.get(node, 0):
                last[node] = t
    for x in targets:
        a = last.get(x["id"])
        x["ago"] = int(now - a) if a else None
        x["quiet"] = not (x["id"] in ALWAYS or x["id"] in busy or a)


def _dungeon_musik(m):
    """The Dungeon-Master's music made ahead (dungeon_musik.for_live): pieces, full fields, making, today, marked annoying (numbers only)."""
    if not m.get("an") and not m.get("stuecke"):
        return ""
    return (f" · Musik {m.get('stuecke', 0)} Stücke ({m.get('mb', 0)} MB), {m.get('voll', 0)} Felder voll"
            + (", macht ein Stück" if m.get("macht") else "") + (f", {m['wartet']} Felder warten" if m.get("wartet") else "")
            + f", heute {m.get('gemacht', 0)} gemacht, {m.get('weg', 0)} nicht gekommen"
            + (f", {m['markiert']} als nervig markiert" if m.get("markiert") else "")
            + (f", {m['alt']} im alten Stil" if m.get("alt") else "")
            + (f", heute {m['nervt']}× Nervt" if m.get("nervt") else ""))


def snapshot(view="admin", now=None):
    now = now or time.time()
    with _lock:
        for k in [k for k, r in _run.items() if (g := _gone_from(r)) and now - g > FADE]:
            _run.pop(k, None)
        reqs = [_req(r, view, now) for r in sorted(_run.values(), key=lambda r: r.t0)]
        _calls(reqs)
        cnt = _count.counts(now)
        guard_items, door_items = list(_guard)[-12:][::-1], list(_door)[-12:][::-1]
        rets, events = list(_rets)[-12:][::-1], list(_events)[-(60 if view == "admin" else 14):][::-1]
    try:
        import vorrang
        speaking = bool(vorrang.speaking(now))
    except Exception:
        speaking = False
    try:
        import notaus
        held = notaus.for_live()
        held["auto"] = notaus.auto_for_live(now)     # Selbst-Notaus: how close each rule is to its threshold
    except Exception:
        held = {"level": 0}
    try:
        import systemone
        sys1 = systemone.for_live(now)
    except Exception:
        sys1 = {"n": 0}
    try:   # the Dienst-Wächter: a dot per service it looks at, and what is gone at its node (fixed words)
        import dienstwacht
        watch_svc, watch_hints = dienstwacht.for_live(now)
    except Exception:
        watch_svc, watch_hints = {}, []
    try:   # the Rundlauf-Wächter: its line, and the step that hakt at its box (fixed words, numbers)
        import rundlauf
        rdl, rdl_hints = rundlauf.for_live(now)
    except Exception:
        rdl, rdl_hints = {"on": False}, []
    hs = [_explain(h) for h in hints(now) + watch_hints + rdl_hints]
    upd = _upd(now)
    used = {h["at"] for h in hs} | {s["to"] for r in reqs for s in r["steps"] if s["to"]} | {r["to"] for r in reqs if r["to"]} | {x["to"] for x in rets if now - x["t"] < 60 and x["to"]}
    try:
        import geraeteupdate
        devup = geraeteupdate.for_live()
    except Exception:
        devup = None
    if devup:
        used.add("geraete")
    try:
        import meldung
        meld = meldung.for_live(now)
    except Exception:
        meld = {"on": False}
    if meld.get("on"):
        used.add("issues")
    try:
        import docmake
        make = docmake.for_live()
    except Exception:
        make = {"on": False}
    if make.get("on"):
        used.add("make")
    try:
        import bilder
        bild = bilder.for_live()
    except Exception:
        bild = {"on": False}
    if bild.get("on"):
        used.add("bild")
    try:
        import musik
        mus = musik.for_live()
    except Exception:
        mus = {"on": False}
    if mus.get("on") or mus.get("installed"):
        used.add("musik")
    try:   # Schwere Aufträge (schwer.py): who has the one place, how many wait (numbers only)
        import schwer
        heavy = schwer.for_live()
    except Exception:
        heavy = {"platz": "", "wait": {}}
    try:
        import berater
        verb = berater.for_live(now)
    except Exception:
        verb = {"on": False}
    if verb.get("on"):
        used.add("verb")
    try:
        import gedaechtnis
        ged = gedaechtnis.for_live(now)
    except Exception:
        ged = {"on": False}
    if ged.get("on"):
        used.add("ged")
    try:
        import klaeren
        import features
        kl = klaeren.for_live() if features.admin_on("klaeren") else None
    except Exception:
        kl = None
    if kl is not None:
        used.add("klaeren")
    try:
        import chats
        cht = chats.for_live(now)
    except Exception:
        cht = {"on": False}
    if cht.get("on"):
        used.add("chats")
    try:
        import suchpruefung
        spr = suchpruefung.for_live()
    except Exception:
        spr = {"on": False}
    if spr.get("on"):
        used.add("pruef")
    try:
        import wissensbuch
        wbk = wissensbuch.for_live()
    except Exception:
        wbk = {"on": False}
    if wbk.get("on"):
        used.add("wbuch")
    try:
        import wissenskarte
        wkk = wissenskarte.for_live()
    except Exception:
        wkk = {"on": False}
    if wkk.get("on"):
        used.add("wkarte")
    try:
        import dungeon
        dgn = dungeon.for_live()
    except Exception:
        dgn = {"on": False}
    try:   # Bilder für Ausrüstung und Zauber (dungeon_dingbild.py): numbers on the game's line
        import dungeon_dingbild
        dgn["ding"] = dungeon_dingbild.for_live() if dgn.get("on") else {"on": False}
    except Exception:
        dgn["ding"] = {"on": False}
    try:   # the admin's rules tab (dungeon_regelseite.py): own entries, hidden ones, pictures to choose
        import dungeon_regelseite
        dgn["regeln"] = dungeon_regelseite.counts() if dgn.get("on") else {}
    except Exception:
        dgn["regeln"] = {}
    try:   # Musik am Tisch (dungeon_musik.py): numbers on the game's line
        import dungeon_musik
        dgn["musik"] = dungeon_musik.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["musik"] = {}
    if dgn.get("on"):
        used.add("dungeon")
    try:
        import geteilt
        tei = geteilt.for_live()
    except Exception:
        tei = {"on": False}
    if tei.get("on"):
        used.add("geteilt")
    try:
        import telefon
        tel = telefon.for_live()
    except Exception:
        tel = {"on": False}
    if tel.get("on"):
        used.add("telefon")
    try:
        import doclingdienst
        dlg = doclingdienst.for_live()
    except Exception:
        dlg = {"on": False}
    if dlg.get("on"):
        used.add("docling")
    try:
        import nas
        nasl = nas.for_live()
    except Exception:
        nasl = {"on": False}
    if nasl.get("on"):
        used.add("nas")
    try:
        import calendars
        kal = calendars.for_live()
        kal_page = calendars.page_today()
        kal_serie, kal_undo = calendars.page_today("serie"), calendars.page_today("undo")
        import postfach
        post_page = postfach.today()
        post_del = postfach.deleted_today()
        import senden
        post_sent = senden.today()
        post_later = senden.later_count()
        import mailregeln
        post_rules = mailregeln.for_live()
        import mail
        post_files = mail.files_today()
        import mailidle
        post_idle = mailidle.for_live()
        import mailcode
        post_code = mailcode.for_live()
        import einordnen
        post_sort = einordnen.for_live()
        import mailvorrat
        post_supply = mailvorrat.for_live()
        post_older = mail.older_today()
        post_threads = mail.threads_today()
        import mailansicht
        post_view = mailansicht.counts()
        import fuerdich
        post_fd = fuerdich.for_live()
    except Exception:
        kal, kal_page, post_page, post_sent, post_files, post_del = {"on": False}, 0, 0, 0, 0, 0
        kal_serie = kal_undo = 0
        post_idle, post_view = {}, {}
        post_rules = {}
        post_supply = {}
        post_older = 0
        post_threads = 0
        post_later = 0
        post_code = {}
        post_sort = {}
        post_fd = {}
    try:
        import vorwaermen
        warm = vorwaermen.for_live()
    except Exception:
        warm = {"profiles": 0}
    try:
        import vorrat
        vsub = functools.partial(vorrat.live_sub, live=vorrat.for_live())
        vround = vorrat.rounds_live()
        vkept = vorrat.supply_live()
        import halive
        halv = halive.for_live()
    except Exception:
        vsub = lambda d: ""   # noqa: E731
        vround, halv, vkept = {}, {}, {}
    try:
        import frisch
        fsub = frisch.live_sub()
    except Exception:
        fsub = ""
    try:
        import antwortvorschlag
        avs = antwortvorschlag.for_live()
    except Exception:
        avs = {"suggested": 0}
    try:
        import kalenderspiegel
        kcopy = kalenderspiegel.for_live()
    except Exception:
        kcopy = {"calendars": 0}
    try:
        import sparkkalender
        kspark = sparkkalender.for_live()
    except Exception:
        kspark = {"calendars": 0}
    try:
        import kalenderserver
        ksrv = kalenderserver.for_live()
    except Exception:
        ksrv = {"on": False}
    try:
        import listendav
        import mitschreiblink
        import tasks
        lst = dict(tasks.for_live(), dav=listendav.for_live(), link=mitschreiblink.for_live())
    except Exception:
        lst = {"on": False}
    try:
        import vorgaenge
        offen = vorgaenge.for_live()
    except Exception:
        offen = {"on": False}
    try:
        import contacts
        import kontaktserver
        kon = dict(contacts.for_live(), srv=kontaktserver.for_live())
    except Exception:
        kon = {}
    try:
        import einladung
        ein = einladung.for_live()
    except Exception:
        ein = {"on": False}
    try:
        import nasquelle
        nql = nasquelle.for_live()
    except Exception:
        nql = {"on": False}
    if nql.get("on"):
        used.add("nasquelle")
    try:
        import nasablage
        nab = nasablage.for_live()
    except Exception:
        nab = {"on": False}
    if nab.get("on"):
        used.add("nasablage")
    try:
        import naszustand
        nzs = naszustand.for_live()
    except Exception:
        nzs = {"on": False}
    if nzs.get("on"):
        used.add("naszustand")
    try:
        import gehaeuse
        geh = gehaeuse.for_live()
    except Exception:
        geh = {"on": False}
    if geh.get("on"):
        used.add("gehaeuse")
    try:
        import schirm
        szr = schirm.for_live(now=now)
    except Exception:
        szr = {"on": False}
    if szr.get("on"):
        used.add("schirm")
    try:
        import werkstattseite
        wks = werkstattseite.for_live(now)
    except Exception:
        wks = {"on": False}
    if wks.get("on"):
        used.add("werkstatt")
    if rdl.get("on"):
        used.add("rundlauf")
    cc = load_config().get("chat", {})
    if cc.get("action_check", True) or cc.get("loop_stop", True):
        import taten
        tat = taten.for_live(now)
        used.add("taten")
    else:
        tat = {}
    try:
        import verbrauch
        vb = verbrauch.for_live(now)
    except Exception:
        vb = {"on": False}
    try:
        import modellseite
        mb = modellseite.for_live()
    except Exception:
        mb = {"on": False}
    try:
        import steuer
        mr = steuer.for_live(now)
    except Exception:
        mr = {"on": False}
    try:
        import notbetrieb
        nbl = notbetrieb.for_live(now) or {}
    except Exception:
        nbl = {}
    if mr.get("on"):
        used.add("modell")
    try:
        import rechnerblick
        rb = rechnerblick.for_live()
    except Exception:
        rb = {"on": False}
    if rb.get("on"):
        used.add("panelrechner")
    used |= set(watch_svc)
    off = unset(now)
    targets = [{"id": k, "name": v[0], "sub": _devup_sub(devup) if k == "geraete" and devup else v[1], "zone": v[2]}
               for k, v in TARGETS.items() if (v[3] and k not in off) or k in used]
    for x in targets:      # Probleme melden: open drafts and sent today, in numbers (no titles, no text)
        if x["id"] == "qwen" and vb.get("on"):   # Verbrauchszähler: tokens of the last minute and today (numbers only)
            x["sub"] = f"{x['sub']} · {vb.get('rate', 0)} Tokens/min · heute {vb.get('today', 0)}"
            if vb.get("full"):   # Kontingent: how many profiles are at a used-up limit
                x["sub"] += f" · {vb['full']} am Kontingent"
        if x["id"] == "qwen" and mb.get("on"):   # Modell-Budget: memory left for models (a number and a fixed word)
            x["sub"] = f"{x['sub']} · frei {mb['frei']:g} GiB" + (" · knapp" if mb["regel"] != "alle" else "")
            if mb.get("eigen"):                  # the own model behind the LLM-Tor (its catalog name, never an address)
                x["name"] = "Sprachmodell " + mb["eigen"]
                x["sub"] = x["sub"].replace("LLM · auf dem Spark", "LLM-Tor · auf dem Spark", 1)
            if mb.get("start"):                  # it switches or starts: step n of 6 first, so the Steuerzentrale's
                import llmstart
                x["sub"] = f"{llmstart.kurz(mb['start'])} · {x['sub']}"   # short line keeps it (never which model)
            elif mb.get("wechsel"):              # stage E4: a model switch runs (that it runs, never which model)
                x["sub"] += " · Modellwechsel läuft"
            if mb.get("messen"):                 # a measurement runs (that it runs, never which model)
                x["sub"] += " · Messung läuft"
        if x["id"] == "nas" and nasl.get("on"):   # NAS: connections and how many failed their last check (no address)
            x["sub"] = (f"{nasl.get('conns', 0)} Verbindungen · {nasl.get('profiles', 0)} Profile"
                        + (f" · {nasl['bad']} mit Fehler" if nasl.get("bad") else "")
                        + (" · Sicherung" if nasl.get("backup") else ""))
        if x["id"] == "cal" and kal.get("on"):   # Kalender teilen: shares in numbers (never a name or an appointment)
            x["sub"] += f" · {kal.get('shares', 0)} geteilt von {kal.get('owners', 0)} Profilen"
        if x["id"] == "mail" and post_page:      # Mails ordnen: messages ordered on the page today (a number)
            x["sub"] += f" · heute {post_page} auf der Seite geordnet" + (f", davon {post_del} gelöscht" if post_del else "")
        if x["id"] == "mail" and post_rules.get("rules"):   # Mail-Regeln: rules and what they took today (numbers only)
            x["sub"] += (f" · {post_rules['rules']} Regeln bei {post_rules['profiles']} Profilen"
                         + (f", heute {post_rules['taken']} Mails einsortiert" if post_rules.get("taken") else ""))
        if x["id"] == "mail" and post_rules.get("hints"):   # Regel-Vorschlag: hints shown today (a number)
            x["sub"] += f" · heute {post_rules['hints']} Regel-Vorschläge"
        if x["id"] == "mail" and post_rules.get("stats"):   # Mail-Statistik: looked at today (a number, never who)
            x["sub"] += f" · heute {post_rules['stats']}× Statistik angesehen"
        if x["id"] == "mail" and post_rules.get("night"):   # Regel-Vorschläge aus dem Ablegen: made last night (a number)
            x["sub"] += f" · {post_rules['night']} Vorschläge aus dem Ablegen"
        if x["id"] == "mail" and post_view.get("html"):   # Apple-Stil „2a“: mails shown formatted, pictures from outside loaded (numbers)
            x["sub"] += f" · heute {post_view['html']} formatiert gezeigt" + (f", {post_view['bilder']} Bilder von außen geladen" if post_view.get("bilder") else "")
        if x["id"] == "mail" and post_files:     # Anhang laden: attachments fetched today (a number, never which)
            x["sub"] += f" · heute {post_files} Anhänge geladen"
        if x["id"] == "mail" and post_idle.get("on"):   # Neue Mails sofort: IDLE connections, new mails today (numbers)
            x["sub"] += f" · sofort: {post_idle['open']} Verbindungen, heute {post_idle['new']} neue Mails"
        if x["id"] == "mail" and post_supply.get("profiles"):   # Mail-Vorrat: profiles with a supply, answers from it (numbers)
            x["sub"] += f" · Vorrat bei {post_supply['profiles']} Profilen" + (f", heute {post_supply['answers']}× daraus geantwortet" if post_supply.get("answers") else "")
        if x["id"] == "mail" and post_older:     # Ältere nachladen: older pages loaded today (a number, never what)
            x["sub"] += f" · heute {post_older} ältere Seiten geladen"
        if x["id"] == "mail" and post_threads:   # Unterhaltung: conversations shown today (a number, never which)
            x["sub"] += f" · heute {post_threads} Unterhaltungen gezeigt"
        if x["id"] == "mail" and post_fd.get("answers"):   # Für dich: mailboxes answered from its kept reading today (a number)
            x["sub"] += f" · Für dich heute {post_fd['answers']}× aus der letzten Lesung"
        if x["id"] == "mail" and post_sent:      # Mails senden: mails sent from the page today (a number, never to whom)
            x["sub"] += f" · heute {post_sent} gesendet"
        if x["id"] == "mail" and post_code.get("on"):   # Bestätigungscodes: notes today (a number, never a code)
            x["sub"] += f" · Codes: heute {post_code['today']} Mitteilungen"
        if x["id"] == "mail" and post_later:     # Später senden: planned mails waiting (a number, never to whom)
            x["sub"] += f" · {post_later} Mails geplant"
        if x["id"] == "mail" and (post_sort.get("going") or post_sort.get("runs")):   # Alle Mails hier einordnen: numbers only
            x["sub"] += f" · Einordnen: {post_sort['going']} läuft, heute {post_sort['runs']} Läufe, {post_sort['moved']} verschoben"
        if x["id"] == "mail" and (avs.get("suggested") or avs.get("rewritten")):   # Antwortvorschläge: numbers only
            x["sub"] += f" · heute {avs['suggested']}× Antwortvorschläge, {avs['rewritten']}× umformuliert"
        if x["id"] == "cal" and kal_page:        # the page Kalender: appointments added, changed, deleted today (a number)
            x["sub"] += f" · heute {kal_page} auf der Seite geändert"
            # Apple-Stil „5a“: of them repeating appointments, and taken back with „Rückgängig“ (numbers only)
            x["sub"] += (f", {kal_serie} davon Serien" if kal_serie else "") + (f", {kal_undo} zurückgenommen" if kal_undo else "")
        if x["id"] == "cal" and kcopy.get("calendars"):   # Spark-Kalender: copies, appointments, last comparison (numbers)
            x["sub"] += (f" · {kcopy['calendars']} Kalender als Kopie, {kcopy['items']} Termine"
                         + (f", abgeglichen vor {kcopy['ago']} min" if kcopy.get("ago") is not None else ""))
        if x["id"] == "cal" and kspark.get("calendars"):   # Spark-Kalender ohne Konto (Stufe 3): numbers only
            x["sub"] += f" · {kspark['calendars']} Spark-Kalender ohne Konto, {kspark['items']} Termine"
        if x["id"] == "cal" and ein.get("on"):   # Einladungen aus Mails: shown, taken, answered today (numbers)
            x["sub"] += f" · Einladungen heute: {ein['shown']} gezeigt, {ein['saved']} eingetragen, {ein['answered']} beantwortet"
        if x["id"] == "cal" and ksrv.get("on"):   # Kalender-Server (Stufe 4): app passwords, requests today (numbers)
            x["sub"] += (f" · Kalender-Apps: {ksrv['profiles']} Profile, heute {ksrv['requests']} Anfragen,"
                         f" {ksrv['saved']} Änderungen, {ksrv['refused']} abgelehnt")
        if x["id"] == "cal" and lst.get("on") and (lst["lists"] or lst["added"] or lst["done"] or lst.get("shares")):   # Listen: numbers only
            x["sub"] += (f" · Listen: {lst['lists']} eigene bei {lst['profiles']} Profilen, heute {lst['added']} eingetragen,"
                         f" {lst['done']} abgehakt" + (f", {lst['shares']}× geteilt" if lst.get("shares") else "")
                         + (f", {lst['dav']['saved']} aus Erinnerungen" if lst["dav"].get("on") else "")
                         + (f", {lst['link']['links']} Mitschreib-Links, {lst['link']['added']} darüber eingetragen,"
                            f" {lst['link']['refused']} abgelehnt" if lst["link"].get("on") else ""))
        if x["id"] == "contacts" and (kon.get("books") or kon.get("spark") or kon.get("today")):   # Seite Kontakte: numbers only, never a name
            x["sub"] += f" · {kon['books']} Adressbücher, {kon['spark']} Karten auf dem Spark, heute {kon['today']} auf der Seite geändert"
        if x["id"] == "contacts" and kon.get("srv", {}).get("on"):   # Kontakte-Server: requests and changes today (numbers)
            x["sub"] += (f" · Kontakte-Apps: heute {kon['srv']['requests']} Anfragen, {kon['srv']['saved']} Änderungen,"
                         f" {kon['srv']['refused']} abgelehnt")
        if x["id"] == "cal" and offen.get("on"):   # Offen (vorgaenge.py): numbers only, never a title
            x["sub"] += (f" · Offen: {offen['braucht']} brauchen jemanden bei {offen['profiles']} Profilen, {offen['spaeter']} später,"
                         f" heute {offen['erledigt']} erledigt, {offen['wieder']} wieder da, {offen['streams']} Seiten verbunden,"
                         f" {offen['warten']} Vorschläge warten auf ein Ja, heute {offen['ja']} per Knopf bestätigt"
                         + ("; offen je Art: " + ", ".join(f"{k} {n}" for k, n in offen["arten"].items()) if offen.get("arten") else ""))
        if x["id"] in ("cal", "mail") and warm.get("profiles"):   # Vorwärmen: how many profiles, how long ago (no name)
            x["sub"] += f" · {warm['profiles']} Profile vorgewärmt, zuletzt vor {warm['ago']} min"
        if x["id"] in ("cal", "mail", "weather", "parcels"):   # Vorrat je Profil: today's share from the store (numbers)
            x["sub"] += vsub({"cal": "calendar"}.get(x["id"], x["id"]))
        if vkept.get(x["id"]):   # Vorrat je Profil 3b: profiles whose last weather/parcels reading is kept sealed
            x["sub"] += f" · versiegelt bei {vkept[x['id']]} Profilen"
        if x["id"] == "cal" and vround.get("rounds"):   # Vorrat je Profil: one round for all services (numbers)
            x["sub"] += f" · Vorrat: heute {vround['rounds']} Runden, {vround['refreshed']} Dienste aufgefrischt"
        if x["id"] == "web":   # Tagesaktuell (frisch.py): searches for a period, old hits dropped, hints (numbers only)
            x["sub"] += fsub
        if x["id"] == "ha" and halv.get("open"):   # Home Assistant live: connections and state changes today (numbers)
            x["sub"] += f" · live: {halv['open']} Verbindungen, heute {halv['changes']} Änderungen"
        if x["id"] == "nasquelle" and nql.get("on"):   # Wissensordner: folders, documents, failing (no path, no name)
            x["sub"] = (f"{nql.get('folders', 0)} Ordner · {nql.get('profiles', 0)} Profile · {nql.get('docs', 0)} Dokumente"
                        + (f" · {nql['bad']} mit Fehler" if nql.get("bad") else "")
                        + (f" · {nql['left_out']} ausgelassen" if nql.get("left_out") else "")
                        + (f" · {nql['taking']} gehen gerade raus" if nql.get("taking") else "")
                        + (f" · Haushalt {nql['haus_folders']} Ordner, {nql.get('haus_docs', 0)} Dokumente" if nql.get("haus_folders") else ""))
        if x["id"] == "nasablage" and nab.get("on"):   # Ablage-Ordner: profiles, files put there and taken in (no path, no name)
            x["sub"] = (f"{nab.get('profiles', 0)} Profile · {nab.get('made', 0)} abgelegt · {nab.get('fetched', 0)} aus dem Eingang"
                        + (f" · {nab['bad']} mit Fehler" if nab.get("bad") else ""))
        if x["id"] == "gehaeuse" and geh.get("on"):   # Gehäuse: display, LEDs, temperature, fan (no page content)
            x["sub"] = (f"Display {geh.get('oled', '-')} · LEDs {geh.get('led', '-')} · {geh.get('temp', '?')} °C"
                        + f" · Lüfter {geh.get('luefter', '?')}" + (" · Neustart nötig" if geh.get("neustart") else ""))
        if x["id"] == "werkstatt" and wks.get("on"):   # Werkstatt: what runs, last night, the measurement (no text, no patch)
            x["sub"] = werkstattseite.live_sub(wks)
        if x["id"] == "rundlauf" and rdl.get("on"):   # Rundlauf: pace, the last run's times, what it waits for
            x["sub"] = rdl["sub"]
        if x["id"] == "schirm" and szr.get("on"):   # Steuerzentrale: shows or not, on or dark by the times (no content)
            x["sub"] = ("zeigt" if szr.get("sieht") else "wartet auf den Bildschirm") + ("" if szr.get("an") else " · dunkel nach Zeitplan")
        if x["id"] == "naszustand" and nzs.get("on"):   # Zustand der NAS: volumes, pools, USB disks, disks, open problems (no address)
            x["sub"] = (f"{nzs.get('vols', 0)} Volumes · {nzs.get('pools', 0)} Pools"
                        + (f" · {nzs['usb']} USB-Platten" if nzs.get("usb") else "") + f" · {nzs.get('disks', 0)} Festplatten"
                        + ("" if nzs.get("ok") else " · antwortet nicht") + (f" · {nzs['warn']} Hinweise" if nzs.get("warn") else ""))
        if x["id"] == "issues":
            x["sub"] = (f"{meld.get('drafts', 0)} Entwürfe · {meld.get('sent_today', 0)} heute gesendet"
                        + ("" if meld.get("token") else " · kein Token"))
        if x["id"] == "verb":   # Einstellungs-Assistent: numbers only (never a question, a title or a word)
            x["sub"] = (f"heute {verb.get('gut', 0)} 👍 · {verb.get('schlecht', 0)} 👎 · {verb.get('faelle', 0)} Fälle · "
                        f"{verb.get('open', 0)} Vorschläge offen" + (f" · {verb['check']} in Nachkontrolle" if verb.get("check") else "")
                        + (f" · {verb['luecken']} Lücken" if verb.get("luecken") else "")
                        + (f" · {verb['regeln']} eigene Regeln" if verb.get("regeln") else ""))
        if x["id"] == "ged":    # Gedächtnis prüfen: how many facts per mark (never a fact)
            x["sub"] = (f"{ged.get('facts', 0)} Einträge · {ged.get('ok', 0)} bestätigt · {ged.get('learned', 0)} gelernt · "
                        f"{ged.get('stale', 0)} veraltet?" + (f" · {ged['contra']} Widerspruch" if ged.get("contra") else "")
                        + (f" · {ged['ask']} Nachfrage offen" if ged.get("ask") else "")
                        + (f" · {ged['untagged']} ohne Thema" if ged.get("untagged") else ""))
        if x["id"] == "klaeren":   # Rückfrage statt Raten: numbers only (never a device, a name or a word)
            x["sub"] = (f"{kl.get('offen', 0)} Fragen offen · heute {kl.get('fragen', 0)} gefragt · {kl.get('auswahl', 0)} gewählt"
                        f" · {kl.get('korrektur', 0)} korrigiert · {kl.get('gemerkt', 0)} gemerkt · {kl.get('genutzt', 0)} genutzt")
        if x["id"] == "chats":  # Chats: numbers only (never a text, a name or a group's name)
            x["sub"] = (f"{cht.get('chats', 0)} Chats · {cht.get('groups', 0)} Gruppen · heute {cht.get('sent', 0)} Nachrichten · "
                        f"{cht.get('pushed', 0)} Mitteilungen" + (f" · {cht['push_failed']} nicht zugestellt" if cht.get("push_failed") else "")
                        + (f" · {cht.get('media', 0)} Fotos/Dateien/Sprache · {cht.get('media_mb', 0)} MB" if cht.get("media_on") else "")
                        + (f" · 🔒 {cht.get('private', 0)} privat, {cht.get('devices', 0)} Geräte, heute {cht.get('private_sent', 0)}" + (f", Verlauf übertragen: {cht['history_waiting']} wartet" if cht.get("history_waiting") else "")
                           if cht.get("private_on") else "")
                        + (f" · Alle: {cht['all']} Personen" if cht.get("all") else "")
                        + (f" · {cht['spoken']} vorgelesen" if cht.get("spoken") else "")
                        + (f" · 🌐 Verbund: {cht.get('far_sparks', 0)} Sparks · {cht.get('far_contacts', 0)} Kontakte · heute "
                           f"{cht.get('far_in', 0)} rein / {cht.get('far_out', 0)} raus" + (f" · {cht['far_waiting']} wartet" if cht.get("far_waiting") else "")
                           + (f" · Dateien heute {cht.get('far_files_in', 0)} rein / {cht.get('far_files_out', 0)} raus" if cht.get("far_media") else "")
                           + (f" · Gruppen: {cht.get('far_groups_home', 0)} von hier, {cht.get('far_groups_there', 0)} von anderen, heute "
                              f"{cht.get('far_group_in', 0)} Nachrichten" if cht.get("far_groups") else "")
                           if cht.get("far_on") else "")
                        + (f" · 📞 Anrufe: {cht.get('call_talking', 0)} laufen, {cht.get('call_ringing', 0)} klingeln, heute "
                           f"{cht.get('call_today', 0)} ({cht.get('call_talked', 0)} angenommen, {cht.get('call_missed', 0)} verpasst, "
                           f"{cht.get('call_minutes', 0)} min, {cht.get('call_iphone', 0)} auf dem iPhone geklingelt)"
                           + (" · Vermittler " + ("läuft" if cht.get("call_turn_ok") else "aus: " + (cht.get("call_turn_why") or "startet"))
                              if cht.get("call_turn") else "")
                           + (f" · per Assistent heute {cht.get('call_assist_asked', 0)} gefragt, {cht.get('call_assist_started', 0)} "
                              f"gestartet, {cht.get('call_assist_sent', 0)} aufs Handy, {cht.get('call_assist_phone', 0)} übers Telefon, "
                              f"{cht.get('call_assist_refused', 0)} abgelehnt" + (f", {cht['call_assist_waiting']} wartet"
                                                                                 if cht.get("call_assist_waiting") else "")
                              if cht.get("call_assist") else "")
                           if cht.get("call_on") else ""))
        if x["id"] == "taten":  # Taten prüfen, Fehlerschleife: counts of today, never a sentence
            x["sub"] = (f"{tat.get('held', 0)} Sätze zurückgehalten · {tat.get('loop', 0)} Schleifen gestoppt heute"
                        + (f" · {tat['klage']} Beschwerden erkannt" if tat.get("klage") else ""))
        if x["id"] == "pruef":     # Suchprüfung: questions and the share found, numbers only (never a question)
            x["sub"] = (f"{spr.get('fragen', 0)} Prüffragen · {spr.get('profile', 0)} Profile"
                        + (f" · {spr['top5']} % unter den ersten 5" if spr.get("top5") is not None else " · noch kein Lauf")
                        + (f" · Sammelfragen {spr['sammel']} % ganz gefunden" if spr.get("sammel") is not None else "")
                        + (" · prüft gerade" if spr.get("running") else ""))
        if x["id"] == "geteilt":   # Teilen mit Profilen: how many single shares, by how many, today (never a title or name)
            x["sub"] = (f"{tei.get('docs', 0)} Dokumente einzeln geteilt von {tei.get('owners', 0)} Profilen"
                        + f" · heute {tei.get('set', 0)} geteilt, {tei.get('back', 0)} zurückgezogen")
        if x["id"] == "wbuch":     # Wissensbuch: pages, sentences, documents waiting, numbers only (never a title)
            x["sub"] = (f"{wbk.get('seiten', 0)} Seiten · {wbk.get('saetze', 0)} Sätze · {wbk.get('warten', 0)} Dokumente warten"
                        + (f" · {wbk['widerspruch']} Widersprüche" if wbk.get("widerspruch") else "")
                        + (f" · {wbk['veraltet']} veraltet?" if wbk.get("veraltet") else "")
                        + (" · arbeitet" if wbk.get("running") else ""))
        if x["id"] == "dungeon":   # Dungeon-Master: rounds, players and guests, turns, loot, levels, campaigns, read aloud and spoken today, stories with acts moved on and proposals, markets, purchases and sales, pictures painted, discarded and on their way, game dates and notes sent, music pieces made ahead, world truths, summaries, rewrites and thumbs, rounds waiting and table talk lines (numbers only, never a name or a text)
            x["sub"] = (f"{dgn.get('runden', 0)} Runden · {dgn.get('spieler', 0)} Spieler, {dgn.get('online', 0)} da, {dgn.get('gaeste', 0)} Gäste"
                        + f" · heute {dgn.get('zuege', 0)} Züge, {dgn.get('beute', 0)} Beute, {dgn.get('stufen', 0)} Stufen"
                        + (f" · {dgn['ausfall']} ohne Erzählung" if dgn.get("ausfall") else "")
                        + (f" · {dgn['verworfen']} Teile verworfen" if dgn.get("verworfen") else "")
                        + (f" · {dgn['abgelehnt']} abgelehnt" if dgn.get("abgelehnt") else "")
                        + (" · erzählt gerade" if dgn.get("denkt") else "")
                        + f" · {dgn.get('kampagnen', 0)} Kampagnen, heute {dgn.get('kapitel', 0)} Kapitel"
                        + f" · heute {dgn.get('vorgelesen', 0)} vorgelesen, {dgn.get('gehoert', 0)} gesprochen"
                        + (f" · Vorlesen läuft ({dgn['liest']})" if dgn.get("liest") else "")
                        + (f" · Vorlesen: {dgn['vorlesen_ersatz']} Teile mit Ersatzstimme" if dgn.get("vorlesen_ersatz") else "")
                        + (f" · Vorlesen: {dgn['vorlesen_fehler']} Fehler" if dgn.get("vorlesen_fehler") else "")
                        + (f" · {dgn['klone']} Klon-Stimmen" + (f", heute {dgn['klone_neu']} neu" if dgn.get("klone_neu") else "") if dgn.get("klone") else "")
                        + (f" · {dgn['am_boden']} am Boden" if dgn.get("am_boden") else "")
                        + (f" · heute {dgn.get('zu_boden', 0)} zu Boden, {dgn.get('aufgestanden', 0)} wieder auf, {dgn.get('geholfen', 0)} Tränke für Freunde, {dgn.get('gefallen', 0)} gefallen, {dgn.get('ohnmacht', 0)} ohnmächtig, {dgn.get('kraft_wirkt', 0)} Kräfte gewirkt"
                           if any(dgn.get(k) for k in ("zu_boden", "gefallen", "ohnmacht", "kraft_wirkt")) else "")
                        + (" · schreibt Bisher geschah" if dgn.get("schreibt") else "")
                        + f" · {dgn.get('geschichten', 0)} Geschichten, heute {dgn.get('akte', 0)} Akte weiter, {dgn.get('vorschlaege', 0)} Vorschläge"
                        + f" · {dgn.get('maerkte_offen', 0)} Märkte offen, heute {dgn.get('maerkte', 0)} Märkte, {dgn.get('kaeufe', 0)} Käufe, {dgn.get('verkaeufe', 0)} Verkäufe"
                        + (f" · heute {dgn['auto']} Schritte im Auto" if dgn.get("auto") else "")
                        + (f" · heute {dgn.get('gemalt', 0)} Bilder gemalt, {dgn.get('bild_weg', 0)} verworfen, {dgn.get('bild_aus', 0)} ausgefallen"
                           if dgn.get("gemalt") or dgn.get("bild_weg") or dgn.get("bild_aus") else "")
                        + (f" · {dgn['bild_wartet']} Bilder unterwegs" if dgn.get("bild_wartet") else "")
                        + (f" · Gegenstandsbilder {dgn['ding']['da']}, Fundstücke {dgn['ding']['funde_da']}, heute {dgn['ding']['gemalt']} gemalt, "
                           f"{dgn['ding']['funde']} Funde, {dgn['ding']['verworfen']} verworfen, {dgn['ding']['ausgefallen']} ausgefallen"
                           + (" · malt Gegenstände" if dgn["ding"]["laeuft"] else "") if dgn.get("ding", {}).get("on") else "")
                        + (f" · {dgn['termine']} Spieltermine" if dgn.get("termine") else "")
                        + (f" · heute {dgn['gemeldet']} Mitteilungen" if dgn.get("gemeldet") else "")
                        + f" · {dgn.get('karten', 0)} Karten, {dgn.get('gewoelbe_drin', 0)} im Gewölbe"
                        + (f", {dgn['ortsbilder']} Ortsbilder" if dgn.get("ortsbilder") else "")
                        + _dungeon_musik(dgn.get("musik") or {})
                        + _dungeon_regeln(dgn.get("regeln") or {})
                        + (f" · heute {dgn.get('wahrheit', 0)} Welt-Wahrheiten, {dgn.get('zusammengefasst', 0)} Zusammenfassungen, {dgn.get('nachgebessert', 0)} nachgebessert"
                           if dgn.get("wahrheit") or dgn.get("zusammengefasst") or dgn.get("nachgebessert") else "")
                        + (f" · {dgn['kaempfe_laufen']} Kämpfe laufen, {dgn['gegner_stehen']} Gegner stehen" if dgn.get("kaempfe_laufen") else "")
                        + (f" · heute {dgn.get('begegnungen', 0)} Begegnungen, {dgn.get('kaempfe', 0)} Kämpfe vorbei, {dgn.get('treffer', 0)} Treffer, "
                           f"{dgn.get('daneben', 0)} daneben, {dgn.get('besiegt', 0)} Gegner besiegt, {dgn.get('geflohen', 0)} geflohen"
                           if dgn.get("begegnungen") or dgn.get("kaempfe") else "")
                        + (f" · {dgn['dinge']} gemerkte Dinge" if dgn.get("dinge") else "")
                        + (f" · heute {dgn['widerspruch']} Widersprüche nachgebessert" if dgn.get("widerspruch") else "")
                        + (f" · heute {dgn.get('daumen_hoch', 0)} 👍, {dgn.get('daumen_runter', 0)} 👎" if dgn.get("daumen_hoch") or dgn.get("daumen_runter") else "")
                        + (f" · {dgn['warten']} Runden warten auf die Erzählung" if dgn.get("warten") else "")
                        + (f" · heute {dgn['tisch']} Zeilen Tischgespräch" if dgn.get("tisch") else "")
                        + (f" · {dgn['verborgen']} Zeilen verborgen" if dgn.get("verborgen") else "")
                        + (f" · {dgn['wortliste']} Spielertexte nach Wortliste abgelehnt" if dgn.get("wortliste") else "")
                        + (f" · {dgn['stumm']} Plätze stumm" if dgn.get("stumm") else "")
                        + (f" · heute {dgn['werkzeug']} Proben mit Werkzeug, {dgn.get('kaputt', 0)} zerbrochen" if dgn.get("werkzeug") else "")
                        + (f" · heute {dgn['geworfen']} Würfe selbst geworfen" if dgn.get("geworfen") else "")
                        + (f" · heute {dgn['kraefte']} Zauber aus Ladungen, {dgn.get('kann_nicht', 0)} unbekannte Kräfte abgewiesen"
                           if dgn.get("kraefte") or dgn.get("kann_nicht") else "")
                        + _gastkonten()
                        + (f" · heute Spielleiter-Regler {dgn.get('regler_hoch', 0)}× schwerer, {dgn.get('regler_runter', 0)}× leichter"
                           if dgn.get("regler_hoch") or dgn.get("regler_runter") else "")
                        + (f" · heute {dgn['heldenmut']}× Heldenmut" if dgn.get("heldenmut") else "")
                        + (f" · heute {dgn['dienste']} Angebote in Siedlungen bezahlt" if dgn.get("dienste") else "")
                        + (f" · heute {dgn['legenden']} legendäre Einzelstücke gefunden" if dgn.get("legenden") else "")
                        + _pruefstand()
                        + (f" · {dgn['npc_stimmen']} NSC-Stimmen" if dgn.get("npc_stimmen") else ""))
        if x["id"] == "wkarte":    # Wissenskarte: connections, discarded, documents waiting, profiles, numbers only (never a title)
            x["sub"] = (f"{wkk.get('verbindungen', 0)} Verbindungen · {wkk.get('punkte', 0)} Punkte · {wkk.get('warten', 0)} Dokumente warten"
                        + f" · {wkk.get('profile', 0)} Profile"
                        + (" · arbeitet" if wkk.get("running") else ""))
        if x["id"] == "modell" and mr.get("on"):   # Modell-Rechner: reachable, units active, version (no address)
            x["sub"] = (("nicht erreichbar" + (" · Notbetrieb" if mr.get("notbetrieb") else "")) if not mr.get("ok") else
                        f"{mr.get('aktiv', 0)} von {mr.get('n', 0)} Diensten aktiv" + (f" · {mr['version']}" if mr.get("version") else "")
                        + (" · Wartungspause" if mr.get("pause") else ""))
            rm = rb.get("modell") or {}   # Rechner: GPU, free memory and CPU of the model computer (numbers only)
            if mr.get("ok") and rm.get("frei") is not None:
                x["sub"] += f" · GPU {_n(rm.get('gpu'))} % · {_n(rm['frei'], 1)} GiB frei · CPU {_n(rm.get('cpu'))} %"
                x["sub"] += _spitze(rm.get("spitze"))
            if nbl.get("on"):   # Notbetrieb mit Parakeet: hearing or not, fixed commands, speaker files (numbers only)
                x["sub"] += ((f" · Parakeet hört · {nbl.get('commands', 0)} Befehle · {nbl.get('fixed', 0)} feste Sätze")
                             if nbl.get("hoert") else f" · Notbetrieb-Sätze {nbl.get('files', 0)} von {nbl.get('need', 0)}")
        if x["id"] == "panelrechner":   # Panel-Rechner: CPU, memory, temperature, disk (numbers only, no name)
            rp = rb.get("panel") or {}
            x["sub"] = (f"CPU {_n(rp.get('cpu'))} % · RAM {_n(rp.get('belegt'), 1)} von {_n(rp.get('total'), 1)} GiB"
                        f" · {_n(rp.get('temp'))} °C · Platte {_n(rp.get('platte'))} %"
                        + (f" · Panel hing {rp['haenger']}-mal in 24 Std." if rp.get("haenger") else "") + _spitze(rp.get("spitze")))
        if x["id"] == "telefon":   # Telefon: signed in, calls in numbers (never a number, a name or a word)
            x["sub"] = (("angemeldet" if tel.get("ok") else "nicht angemeldet") + f" · {tel.get('calls', 0)} Gespräche jetzt · heute "
                        f"{tel.get('angenommen', 0)} angenommen, {tel.get('abgelehnt', 0)} abgelehnt, {tel.get('fragen', 0)} Fragen, "
                        f"{tel.get('minuten', 0)} min" + (f" · {tel['fremd']} fremde Pakete verworfen" if tel.get("fremd") else "")
                        + (f" · PIN {tel.get('pin', 0)} richtig, {tel['pinfalsch']} falsch" if tel.get("pinfalsch") or tel.get("pin") else "")
                        + (f" · {tel['bestaetigt']} Nummern bestätigt" if tel.get("bestaetigt") else "")
                        + (f" · von außen {tel['extern']}, davon {tel.get('gaeste', 0)} Gäste" if tel.get("extern") else "")
                        + (f" · der Spark rief {tel['raus']}-mal an, {tel.get('angerufen', 0)} abgehoben" if tel.get("raus") else "")
                        + (f" · {tel['rueckruf']} Rückrufe" if tel.get("rueckruf") else "")
                        + (f" · {tel['alarm']} Alarm-Anrufe" if tel.get("alarm") else "")
                        + (f" · {tel['geplant']} Anrufe geplant" if tel.get("geplant") else ""))
        if x["id"] == "docling":   # Docling-Server: files in numbers (never a name or a text)
            x["sub"] = (f"{dlg.get('wait', 0)} warten · heute {dlg.get('ok', 0)} gelesen, {dlg.get('pages', 0)} Seiten"
                        + (f" · {dlg['failed']} Fehler" if dlg.get("failed") else "")
                        + (" · liest gerade" if dlg.get("busy") else "") + (" · nicht erreichbar" if dlg.get("down") else ""))
        if x["id"] == "make":   # Dokumente erstellen: jobs in numbers (no titles, no text)
            x["sub"] = (f"{make.get('run', 0)} läuft · {make.get('wait', 0)} wartet · {make.get('done', 0)} heute fertig"
                        + (f" · {make['failed']} Fehler" if make.get("failed") else ""))
        if x["id"] == "bild":   # Bilder malen: pictures in numbers (no wish, no prompt)
            x["sub"] = (f"{bild.get('run', 0)} malt · {bild.get('wait', 0)} wartet · {bild.get('done', 0)} heute gemalt"
                        + (f" · {bild['edited']} geändert" if bild.get("edited") else "")
                        + (f" · {bild['quick']} schnell bearbeitet" if bild.get("quick") else "")
                        + (f" · {bild['refused']} abgelehnt" if bild.get("refused") else "")
                        + (f" · {bild['failed']} Fehler" if bild.get("failed") else "") + _platz(heavy, "bild"))
        if x["id"] == "musik":   # Musik machen: songs and the measurement in numbers (no wish, no lyrics)
            x["sub"] = (f"{mus.get('run', 0)} macht · {mus.get('wait', 0)} wartet · {mus.get('done', 0)} heute gemacht"
                        + (f" · {mus['edited']} bearbeitet" if mus.get("edited") else "")
                        + (f" · {mus['uploaded']} hochgeladen" if mus.get("uploaded") else "")
                        + (f" · {mus['heard']} erkannt" if mus.get("heard") else "")
                        + (f" · {mus['texts']} Liedtexte geschrieben" if mus.get("texts") else "")
                        + (f" · {mus['refused']} abgelehnt" if mus.get("refused") else "")
                        + (f" · {mus['failed']} Fehler" if mus.get("failed") else "")
                        + (" · misst gerade" if mus.get("test_run") else
                           f" · Messung {mus['test_ok']} von {mus['test_total']} gut" if mus.get("test_total") else "")
                        + _platz(heavy, "musik"))
    svc = dict(watch_svc, **{k: v for k, v in _svc_now(now).items() if k not in watch_svc or watch_svc[k]["st"] == "ok"})
    try:   # Wartungspause (wartung.py): the paused parts in blue, "Pause" (never who or why)
        import wartung
        pause = wartung.for_live(now)
        for p in pause.get("parts") or []:
            svc[wartung.PARTS[p][0]] = {"st": "pause", "word": "Wartungspause", "ago": 0}
    except Exception:
        pause = {"on": False}
    work = {"telefon": tel.get("calls"), "docling": dlg.get("busy") or dlg.get("wait") or dlg.get("down"),
            "make": make.get("run") or make.get("wait"), "bild": bild.get("run") or bild.get("wait"), "musik": mus.get("run") or mus.get("wait")}
    ruhe(targets, {k for k, v in work.items() if v} | {h["at"] for h in hs} | {k for k, v in svc.items() if v.get("st") != "ok"}
         | {s["to"] for r in reqs if not r["done"] for s in r["steps"] if s["to"]} | {r["to"] for r in reqs if not r["done"] and r["to"]}, now)
    return {"t": round(now, 1), "view": view, "fade": FADE, "reqs": reqs, "targets": targets, "speaking": speaking,
            "guard": {"ok": cnt.get("guard_ok", 0), "bad": cnt.get("guard_bad", 0), "cut": cnt.get("guard_cut", 0), "items": guard_items},
            "door": {"in": cnt.get("door_in", 0), "out": cnt.get("door_out", 0), "items": door_items},
            "bus": {k: cnt.get("bus_" + k, 0) for k in BUS},
            "rets": rets, "events": [{"t": t, "area": a, "text": x} for t, a, x in events], "conns": _conns(now), "sys": _sys(), "notaus": held,
            "svc": svc, "wartung": pause,
            "bg": _bg_now(now), "weiche": _weiche_today(), "hints": hs, "sys1": sys1, "upd": upd, "devup": devup,
            "meld": {k: meld.get(k) for k in ("on", "drafts", "sent_today", "last", "token")},
            "make": {k: make.get(k) for k in ("on", "run", "wait", "done", "failed", "sent", "planned")},
            "bild": {k: bild.get(k) for k in ("on", "run", "wait", "done", "edited", "quick", "failed", "refused")},
            "musik": {k: mus.get(k) for k in ("on", "installed", "run", "wait", "done", "failed", "refused", "edited", "uploaded", "heard", "texts", "test_run",
                                              "test_ok", "test_total")},
            "schwer": heavy, "stats": node_stats(now), "aktiv": _aktiv(now)}


def _platz(heavy, art):
    """The node line's part for the one place of the heavy jobs (schwer.py): has it, waits for memory, or waits
    behind the other kind; nothing while nobody waits."""
    if heavy.get("platz") == art:
        return " · wartet auf Speicher" if heavy.get("phase") == "speicher" else " · hat den Platz"
    if heavy.get("platz") and (heavy.get("wait") or {}).get(art):
        return " · wartet auf den Platz"
    return ""


def _aktiv(now):
    """Aktiv in den letzten 10 Minuten (aktiv.py): numbers only, also while Live was off before."""
    try:
        import aktiv
        return aktiv.zahlen(now)
    except Exception:
        return {"gesamt": 0, "profile": 0, "gaeste": 0}


def _devup_sub(d):
    """The line under Geräte-Updates: per kind the devices that are current, else the version kept."""
    parts = []
    for k in d["kinds"][:5]:
        parts.append(f"{k['short']} {k['current']}/{k['n']} aktuell" if k["n"] and k["counted"] else f"{k['short']} {k['version'] or '–'}")
    if d["night"]["pending"]:
        parts.append("Neustart läuft")
    return " · ".join(parts)[:90] or TARGETS["geraete"][1]


# ------------------------------------------------------------------ admin view
@router.get("/api/admin/live", dependencies=[Depends(auth)])
def admin_live(request: Request, past: int = 0):
    guard.limit(request, "live", admin=True)
    if not on():
        return {"on": False}   # off: the page says so, without an error in the console of every admin page (B8)
    if past:                   # Zurückspulen: the finished requests of the last 15 minutes (admin only, not the monitor)
        return {"past": past_reqs("admin"), "rewind": REWIND}
    return snapshot("admin")


# ------------------------------------------------------------------ monitors
def _file():
    return os.path.join(STATE, "live-monitors.json")


def _load():
    try:
        with open(_file()) as f:
            items = json.load(f).get("items", [])
        return [m for m in items if isinstance(m, dict) and re.fullmatch(r"m_[0-9a-f]{8}", str(m.get("id")))
                and re.fullmatch(r"[0-9a-f]{64}", str(m.get("hash")))]
    except (OSError, ValueError, AttributeError):
        return []


def _store(items):
    write_json(_file(), {"items": items}, mode=0o600)


def _hash(x):
    return hashlib.sha256(x.encode()).hexdigest()


def _by(request):
    c = request.scope.get("speech_coadmin")
    return "main" if request.scope.get("speech_main_admin") or not c else c.get("id", "coadmin")


@router.get("/api/admin/live/monitors", dependencies=[Depends(auth)])
def monitors(request: Request):
    guard.limit(request, "live", admin=True)
    now = time.time()
    with _lock:
        items = _load()
        return {"on": monitor_on(), "screens": screens(), "codes": sum(1 for u, _ in _codes.values() if u > now),
                "items": [{"id": m["id"], "name": m.get("name", "Monitor"), "created": m.get("created"), "last": max(m.get("last") or 0, _seen.get(m["id"], (0, ""))[0]) or None,
                           "watching": now - _seen.get(m["id"], (0, ""))[0] < SEEN_S, "from": _seen.get(m["id"], (0, m.get("from", "")))[1] or m.get("from", "")} for m in items]}


@router.post("/api/admin/live/monitors", dependencies=[Depends(auth)])
async def monitor_new(request: Request):
    """A one-time 6-digit code for a new monitor (10 minutes); the screen enters it on /live."""
    guard.limit(request, "live", admin=True)
    if not monitor_on():
        raise HTTPException(409, "monitor off")
    try:
        body = await request.json()
    except ValueError:
        body = {}
    name = str((body or {}).get("name") or "Monitor").strip()
    if not NAME.fullmatch(name):
        raise HTTPException(400, "name: 1 to 30 letters, digits, spaces, . _ -")
    now = time.time()
    with _lock:
        for k in [k for k, (u, _) in _codes.items() if u <= now]:
            _codes.pop(k, None)
        if len(_codes) >= MAX_CODES:
            raise HTTPException(429, "too many open codes")
        if len(_load()) >= MAX_MONITORS:
            raise HTTPException(409, f"at most {MAX_MONITORS} monitors")
        while True:
            code = f"{secrets.randbelow(10 ** 6):06d}"
            if _hash(code) not in _codes:
                break
        _codes[_hash(code)] = (now + CODE_S, name)
    guard.log("live_monitor_code", by=_by(request), name=name)
    return {"code": code, "until": int(now + CODE_S), "path": "/live"}


@router.delete("/api/admin/live/monitors/{mid}", dependencies=[Depends(auth)])
def monitor_delete(request: Request, mid: str):
    guard.limit(request, "live", admin=True)
    if not re.fullmatch(r"m_[0-9a-f]{8}", mid):
        raise HTTPException(400, "bad id")
    with _lock:
        items = _load()
        if not any(m["id"] == mid for m in items):
            raise HTTPException(404, "not found")
        _store([m for m in items if m["id"] != mid])
        _seen.pop(mid, None)
    guard.log("live_monitor_deleted", by=_by(request), id=mid)
    return {"ok": True}


def _home_only(request):
    """The monitor is for the home network: a sender from the internet is turned away."""
    if from_internet(request):
        _door_no(request, "Monitor-Zugang gilt nur im Heimnetz", ["kam aus dem Internet", "Live-Monitor: nur Heimnetz", "→ abgewiesen (403)"])
        raise HTTPException(403, "the monitor works in the home network only")


@router.get("/live", include_in_schema=False)
def live_page(request: Request):
    """The monitor page (static, its script /static/js/live.js asks /api/live/state)."""
    if not monitor_on():
        raise HTTPException(404, "not found")
    _home_only(request)
    from core import app_version
    ver = re.sub(r"[^A-Za-z0-9.\-]", "", app_version())[:32] or "0"
    with open(os.path.join(STATIC, "live.html"), encoding="utf-8") as f:
        html = f.read().replace("{{V}}", ver)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.post("/api/live/pair")
async def pair(request: Request):
    """The screen enters the code: it gets its own key as a cookie (read-only, this page only)."""
    if not monitor_on():
        raise HTTPException(404, "not found")
    _home_only(request)
    guard.check(request)
    guard.limit(request, "pair")
    try:
        body = await request.json()
    except ValueError:
        body = {}
    code = re.sub(r"\D", "", str((body or {}).get("code") or ""))[:6]
    now = time.time()
    hit = None
    with _lock:
        for k, (until, name) in list(_codes.items()):
            if until > now and len(code) == 6 and hmac.compare_digest(k, _hash(code)):
                hit = name
                _codes.pop(k, None)
                break
    if not hit:
        guard.failed(request, what="live_code")
        import asyncio
        await asyncio.sleep(1)
        raise HTTPException(401, "wrong or expired code")
    token = "sl_" + secrets.token_urlsafe(32)
    mid = "m_" + secrets.token_hex(4)
    with _lock:
        items = _load()
        items.append({"id": mid, "name": hit, "hash": _hash(token), "created": int(now), "last": int(now),
                      "from": short_ip(sender(request))})
        _store(items[-MAX_MONITORS:])
    guard.succeeded(request)
    guard.log("live_monitor_paired", name=hit, ip=guard.client_ip(request))
    event("Monitor", f"{hit} gekoppelt", now)
    r = JSONResponse({"ok": True, "name": hit})
    r.set_cookie(COOKIE, token, max_age=KEEP_DAYS * 86400, httponly=True, samesite="strict", secure=guard.https(request), path="/")
    return r


def monitor_of(request, now=None):
    """The paired monitor this request's cookie belongs to, or None."""
    token = request.cookies.get(COOKIE, "")
    if not token.startswith("sl_") or len(token) > 80:
        return None
    h, now = _hash(token), now or time.time()
    with _lock:
        for m in _load():
            if hmac.compare_digest(m["hash"], h):
                if now - max(m.get("last") or 0, _seen.get(m["id"], (0, ""))[0]) > KEEP_DAYS * 86400:
                    return None
                return m
    return None


@router.get("/api/live/state")
def state(request: Request):
    """What a paired monitor shows: like the admin view, names only when allowed twice."""
    if not monitor_on():
        raise HTTPException(404, "not found")
    _home_only(request)
    guard.limit(request, "livemon")
    m = monitor_of(request)
    if not m:
        raise HTTPException(401, "pair this screen first")
    now = time.time()
    with _lock:
        watching = [k for k, (t, _) in _seen.items() if now - t < SEEN_S and k != m["id"]]
        if len(watching) >= screens():
            raise HTTPException(429, f"at most {screens()} screens at once")
        _seen[m["id"]] = (now, short_ip(guard.client_ip(request)))
        if now - _saved[0] > 300:     # "last seen" on disk now and then, not every second
            _saved[0] = now
            items = _load()
            for x in items:
                if x["id"] in _seen:
                    x["last"] = int(_seen[x["id"]][0])
            _store(items)
    return dict(snapshot("monitor", now), monitor=m.get("name", "Monitor"))
