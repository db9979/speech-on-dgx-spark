#!/usr/bin/env python3
"""spark-tui: the Spark in a terminal (ClockworkPi uConsole, any Linux or Mac terminal, also over SSH).

    spark-tui koppeln 'https://…#tui=CODE[&fp=SHA256]' [--name uConsole]   pair once (Ich → Terminal in the panel)
    spark-tui adresse-dazu https://spark.example.org                        a second address (outside, checked as usual)
    spark-tui                                                                the window (needs Textual)
    spark-tui frage 'Wann fährt der erste Bus?'                              one question, the answer as text
    echo 'Text' | spark-tui frage 'Fasse das zusammen'                       the piped text goes with the question
    spark-tui kalender [--woche N]                                           the appointments of a week (0 = this one)
    spark-tui neu 'Morgen 15 Uhr Zahnarzt' [--ja]                            Schnell eintragen: shows, asks, then saves
    spark-tui mails [--anzahl N]                                             the newest mails by day (sender, subject), up to 200
    spark-tui mail N                                                         mail number N of that list as plain text
    spark-tui status                                                         reachable? what may this terminal do?
    spark-tui update                                                         the newest version from the Spark

Only the Python standard library talks to the Spark: https only; an address from the pairing line at home has its
certificate pinned (SHA-256, checked before anything is sent), any other address is checked against the system's
authorities. The key lives in ~/.config/spark-tui/geraet.json (0600) and reaches only the terminal's paths on the
Spark. What the Spark answers is shown as text, never run. The window needs Textual (python3 -m pip install textual).
"""
import argparse
import hashlib
import hmac
import http.client
import json
import os
import re
import shutil
import socket
import ssl
import sys
import threading
import time
import urllib.parse

VERSION = "1.0.3"
HEADER = "X-Speech-Device"
VENV = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "spark-tui")   # Textual for the window
SETUP = "python3 -m venv ~/.local/share/spark-tui && ~/.local/share/spark-tui/bin/pip install textual"
CONF = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "spark-tui", "geraet.json")
LINE = re.compile(r"(https://[A-Za-z0-9.\-\[\]:]{1,260})/?#tui=([A-Za-z0-9_\-]{20,40})(?:&fp=([0-9a-f]{64}))?")
URL = re.compile(r"https://[A-Za-z0-9.\-]{1,253}(?::\d{1,5})?|https://\[[0-9A-Fa-f:.]{2,45}\](?::\d{1,5})?")
MAX_PIPE = 20000          # characters of piped text that go with a question
HELLO_EVERY = 60          # seconds between two hellos (the Spark counts open terminals for its Live page)


class SparkError(Exception):
    pass


# ---------------------------------------------------------------- the device file
def load():
    try:
        with open(CONF) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("key") and d.get("urls") else None


def save(d):
    os.makedirs(os.path.dirname(CONF), mode=0o700, exist_ok=True)
    tmp = CONF + ".neu"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, CONF)


# ---------------------------------------------------------------- talking to the Spark
class Spark:
    """One paired Spark: its addresses (each with its pin or none) and the device key."""

    def __init__(self, conf, timeout=15):
        self.conf, self.timeout = conf, timeout
        self.base = None
        self.more = []   # the panel's sentences under the last answer („Das kannst du auch sagen“)

    def _connect(self, url, fp, timeout):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https":
            raise SparkError("nur https")
        if fp:   # at home: exactly the pinned certificate, checked before anything goes out
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout, context=ctx)
        conn.connect()
        if fp:
            got = hashlib.sha256(conn.sock.getpeercert(binary_form=True) or b"").hexdigest()
            if not hmac.compare_digest(got, fp):
                conn.close()
                raise SparkError("Das Zertifikat passt nicht zur Kopplung. Nichts gesendet.")
        return conn

    def open(self, method, path, body=None, timeout=None, stream=False):
        """The response of the first address that answers (home first, then outside)."""
        last = None
        order = sorted(self.conf["urls"], key=lambda x: x is not self.base)   # the one that worked last goes first
        for item in order:
            try:
                conn = self._connect(item["url"], item.get("fp", ""), timeout or self.timeout)
            except (OSError, ssl.SSLError, SparkError) as e:
                last = e
                if isinstance(e, SparkError):
                    raise
                continue
            self.base = item
            data = json.dumps(body).encode() if body is not None else None
            headers = {HEADER: self.conf["key"], "Accept": "text/event-stream" if stream else "application/json",
                       "User-Agent": "spark-tui/" + VERSION}
            if data is not None:
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            r = conn.getresponse()
            if r.status >= 400:
                raw = r.read(4096)
                conn.close()
                raise SparkError(say_error(r.status, raw))
            return conn, r
        raise SparkError("Der Spark ist nicht erreichbar" + (f" ({type(last).__name__})" if last else "") + ".")

    def call(self, method, path, body=None):
        conn, r = self.open(method, path, body)
        try:
            raw = r.read(4 * 1024 * 1024)
        finally:
            conn.close()
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise SparkError("Unerwartete Antwort vom Spark.")

    def ask(self, messages, convo="", on_text=None, stop=None):
        """Streams one answer; on_text(whole text so far) after every piece. Returns the answer."""
        body = {"messages": messages, "client": "tui", "speak": False, "tz": zone()}
        if convo:
            body["convo"] = convo
        conn, r = self.open("POST", "/api/chat", body, timeout=600, stream=True)
        text = ""
        self.more = []
        try:
            for raw in r:
                if stop and stop.is_set():
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:])
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "text" and isinstance(ev.get("delta"), str):
                    text += ev["delta"]
                elif kind in ("retract", "truncated") and isinstance(ev.get("drop"), int):
                    text = text[:max(0, len(text) - ev["drop"])]
                elif kind == "error":
                    raise SparkError(str(ev.get("message") or "Fehler beim Spark.")[:300])
                elif kind == "more" and isinstance(ev.get("items"), list):   # shown as one grey tip line
                    self.more = [str((x.get("text") or [""])[0])[:200] for x in ev["items"][:3]
                                 if isinstance(x, dict) and isinstance(x.get("text"), list) and x["text"]]
                    continue
                elif kind == "done":
                    break
                else:
                    continue
                if on_text:
                    on_text(text)
        finally:
            conn.close()
        return text.strip()


def say_error(status, raw):
    try:
        detail = json.loads(raw).get("detail")
    except (ValueError, AttributeError):
        detail = None
    if status == 401:
        return "Dieses Terminal ist nicht mehr gekoppelt. Im Panel unter Ich → Terminal neu koppeln."
    if status == 503:
        return "Gerade nicht verfügbar (vom Admin ausgeschaltet oder Notaus)."
    if status == 429:
        return "Zu viele Anfragen. Gleich noch einmal."
    return str(detail)[:300] if isinstance(detail, str) and detail else f"Fehler {status} beim Spark."


def zone():
    try:
        link = os.readlink("/etc/localtime")
        return link.split("zoneinfo/", 1)[1][:64] if "zoneinfo/" in link else ""
    except OSError:
        return os.environ.get("TZ", "")[:64]


def new_convo_id():
    return str(int(time.time() * 1000))


def title_of(text):
    t = " ".join(text.split())
    return t[:60] + ("…" if len(t) > 60 else "")


# ---------------------------------------------------------------- commands
def cmd_pair(args):
    m = LINE.fullmatch(args.line.strip())
    if not m:
        sys.exit("Die Kopplungszeile passt nicht. Im Panel unter Ich → Terminal eine neue holen und ganz kopieren.")
    url, code, fp = m.group(1), m.group(2), m.group(3) or ""
    name = args.name or socket.gethostname()[:40] or "spark-tui"
    sp = Spark({"key": "", "urls": [{"url": url, "fp": fp}]})
    try:
        conn, r = sp.open("POST", "/api/tui/pair", {"code": code, "name": re.sub(r"[^\w .\-]", "", name)[:40]})
        d = json.loads(r.read(65536) or b"{}")
        conn.close()
    except SparkError as e:
        sys.exit("Nicht gekoppelt: " + str(e))
    old = load() or {}
    extra = [x for x in old.get("urls", []) if not x.get("fp") and x.get("url") != url] if old.get("key") == d.get("key") else []
    save({"key": d["key"], "profile": d.get("profile", ""), "urls": [{"url": url, "fp": fp}] + extra})
    print(f"  Spark        {url}")
    print("  Zertifikat   " + (f"SHA-256 {fp[:4]} {fp[4:8]} … {fp[-4:]}  festgepinnt" if fp else "wie im Browser geprüft"))
    print(f"  Profil       {d.get('profile', '')}")
    print(f"  Gespeichert  {CONF}  (Rechte 0600)")
    me = "spark-tui" if shutil.which("spark-tui") else (os.path.abspath(sys.argv[0]) if sys.argv[0].endswith("spark-tui") else "python3 " + sys.argv[0])
    print(f"\n  Fertig. Starten mit:  {me}")


def need():
    conf = load()
    if not conf:
        sys.exit("Noch nicht gekoppelt. Im Panel unter Ich → Terminal eine Kopplungszeile holen.")
    return conf


def cmd_add(args):
    conf = need()
    url = args.url.strip().rstrip("/")
    if not URL.fullmatch(url):
        sys.exit("Nur https://name oder https://name:port, ohne Pfad.")
    sp = Spark({"key": conf["key"], "urls": [{"url": url, "fp": ""}]})
    try:
        sp.call("GET", "/api/tui/hello")
    except SparkError as e:
        sys.exit("Über diese Adresse geht es nicht: " + str(e))
    conf["urls"] = [x for x in conf["urls"] if x["url"] != url] + [{"url": url, "fp": ""}]
    save(conf)
    print("Dazu:", url, "(Zertifikat wie im Browser geprüft). Zu Hause bleibt die erste Adresse vorn.")


def cmd_status(args):
    conf = need()
    try:
        d = Spark(conf).call("GET", "/api/tui/hello")
    except SparkError as e:
        sys.exit(str(e))
    agent = {"": "aus", "read": "nur lesen", "act": "auch handeln"}.get(d.get("agent", ""), d.get("agent", ""))
    print(f"Spark {d.get('spark', '')} · erreichbar · Profil {d.get('profile', '')} · Aufträge: {agent} · "
          f"spark-tui {VERSION}" + (f" (auf dem Spark {d['program']}: spark-tui update)" if d.get("program") and d["program"] != VERSION else ""))


def update_file(sp, target):
    """Replaces target with the Spark's spark-tui.py: fetched over the paired (pinned) connection and kept only when
    its SHA-256 matches what the Spark names in hello; written next to it and moved in at once. Returns the new version
    or "" when already current."""
    d = sp.call("GET", "/api/tui/hello")
    want, ver = str(d.get("sha256", "")), str(d.get("program", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", want):
        raise SparkError("Der Spark nennt keine Prüfsumme für das Programm.")
    with open(target, "rb") as f:
        if hmac.compare_digest(hashlib.sha256(f.read()).hexdigest(), want):
            return ""
    conn, r = sp.open("GET", "/tui/spark-tui.py")
    try:
        data = r.read(4 * 1024 * 1024 + 1)
    finally:
        conn.close()
    if len(data) > 4 * 1024 * 1024 or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), want):
        raise SparkError("Die Prüfsumme passt nicht. Nichts geändert.")
    if not data.startswith(b"#!/usr/bin/env python3\n"):
        raise SparkError("Unerwartete Datei vom Spark. Nichts geändert.")
    tmp = target + ".neu"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o755)
    os.replace(tmp, target)
    return ver or "?"


def cmd_update(args):
    conf = need()
    target = os.path.realpath(sys.argv[0])
    try:
        ver = update_file(Spark(conf), target)
    except SparkError as e:
        sys.exit(str(e))
    except OSError as e:
        sys.exit(f"Nicht geschrieben ({type(e).__name__}): {target}")
    print(f"spark-tui {VERSION} ist aktuell." if not ver else f"spark-tui {VERSION} → {ver}, ersetzt: {target}")


def cmd_ask(args):
    conf = need()
    q = " ".join(args.text).strip()
    if not sys.stdin.isatty():
        piped = sys.stdin.read(MAX_PIPE + 1)
        if piped.strip():
            q = (q + "\n\n" if q else "") + piped[:MAX_PIPE]
    if not q:
        sys.exit("Keine Frage.")
    try:
        print(Spark(conf).ask([{"role": "user", "content": q}]))
    except SparkError as e:
        sys.exit(str(e))


DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def week_start(offset=0, now=None):
    """The Monday of this week plus offset weeks, as a date."""
    import datetime
    today = datetime.date.fromtimestamp(now or time.time())
    return today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=offset)


def calendar_lines(d, start):
    """The page Kalender as text, one block per day of the week from start (GET /api/profile/calendar/view).
    Titles and places come from the calendars: plain text, cut to a line."""
    import datetime
    if not d.get("connected"):
        return ["Kein Kalender verbunden (im Panel unter Kalender → Einstellungen)."]
    names = d.get("calendars") or []
    lines = []
    for i in range(7):
        day = start + datetime.timedelta(days=i)
        a = time.mktime(day.timetuple())
        b = a + 86400
        evs = [e for e in d.get("events", []) if e.get("start", 0) < b and max(e.get("end", 0), e.get("start", 0) + 60) > a]
        lines.append(f"{DAYS[day.weekday()]} {day:%d.%m.}")
        for e in evs:
            when = "ganztägig  " if e.get("allday") else time.strftime("%H:%M", time.localtime(e["start"])) + "-" + time.strftime("%H:%M", time.localtime(e["end"])) + " "
            cal = names[e["cal"]] if len(names) > 1 and isinstance(e.get("cal"), int) and e["cal"] < len(names) else ""
            text = str(e.get("title", "")) + (f" · {e['location']}" if e.get("location") else "") + (f" [{cal}]" if cal else "")
            lines.append("  " + when + " " + "".join(c for c in text if c.isprintable())[:60])
        if not evs:
            lines.append("  –")
    lines += [f"Nicht erreicht: {n}" for n in d.get("errors", [])]
    lines += [f"Lädt noch: {n}" for n in d.get("loading", [])]
    return lines


def get_week(sp, offset):
    start = week_start(offset)
    q = urllib.parse.urlencode({"start": start.isoformat(), "days": 7, "tz": zone()})
    return start, sp.call("GET", "/api/profile/calendar/view?" + q)


def cmd_calendar(args):
    conf = need()
    try:
        start, d = get_week(Spark(conf), args.woche)
    except SparkError as e:
        sys.exit(str(e))
    print("\n".join(calendar_lines(d, start)))


def plain(text, width=None):
    """Text from a calendar or a mail: printable characters only (no terminal escapes), cut to `width`."""
    t = "".join(c for c in str(text or "") if c.isprintable())
    return t[:width] if width else t


def quick_lines(f):
    """What the Spark understood from a line for Schnell eintragen (GET /api/profile/calendar/quick)."""
    when = f.get("start", "") if f.get("allday") else f"{f.get('start', '')} – {str(f.get('end', ''))[-5:]}"
    lines = ["  " + plain(f.get("title"), 80), "  " + ("ganztägig " if f.get("allday") else "") + when.replace("T", " ")]
    if f.get("location"):
        lines.append("  " + plain(f["location"], 80))
    return lines


def cmd_new(args):
    """Schnell eintragen (Dominik 2026-10-19 „a“): the Spark reads the line with fixed rules; only a yes saves."""
    conf = need()
    sp = Spark(conf)
    text = " ".join(args.text).strip()[:200]
    if not text:
        sys.exit("Was soll eingetragen werden? z. B. spark-tui neu 'Morgen 15 Uhr Zahnarzt'")
    try:
        f = sp.call("GET", "/api/profile/calendar/quick?" + urllib.parse.urlencode({"text": text, "tz": zone()}))
        print("\n".join(["Verstanden:"] + quick_lines(f)))
        if not args.ja and input("Eintragen? [j/N] ").strip().lower() not in ("j", "ja", "y", "yes"):
            print("Nicht eingetragen.")
            return
        body = {k: f[k] for k in ("title", "start", "end", "allday", "location") if k in f}
        sp.call("POST", "/api/profile/calendar/event", dict(body, tz=zone()))
    except SparkError as e:
        sys.exit(str(e))
    print("Eingetragen.")


MAIL_MAX = 200   # mails spark-tui lists at most; beyond the first page the older ones are loaded page by page


def mail_items(sp, n):
    """The newest n mails; more than the first page follows the mark „vor“ to the older ones (Ältere nachladen)."""
    n = max(1, min(n, MAIL_MAX))
    r = sp.call("GET", "/api/profile/mail/inbox")
    items, seen = [], set()
    while True:
        for x in r.get("items") or []:
            if x.get("id") not in seen:
                seen.add(x.get("id"))
                items.append(x)
        if len(items) >= n or not r.get("vor"):
            return items[:n]
        r = sp.call("GET", "/api/profile/mail/inbox?" + urllib.parse.urlencode({"vor": r["vor"]}))


def mail_lines(items):
    """The list by day, newest first, numbered for spark-tui mail N; * marks unread."""
    lines, last = [], None
    for i, x in enumerate(items, 1):
        t = time.localtime(x.get("date") or 0)
        day = time.strftime("%d.%m.", t)
        if day != last:
            lines.append(f"{DAYS[t.tm_wday]} {day}")
            last = day
        who = re.sub(r"\s*<[^>]*>$", "", str(x.get("from", ""))) or str(x.get("from", ""))
        lines.append(f"{i:>3} {'*' if x.get('unread') else ' '} {time.strftime('%H:%M', t)}  {plain(who, 24):<24}  {plain(x.get('subject'), 50)}")
    return lines or ["Keine Mail in den letzten 14 Tagen."]


def cmd_mails(args):
    try:
        print("\n".join(mail_lines(mail_items(Spark(need()), args.anzahl))))
    except SparkError as e:
        sys.exit(str(e))


def cmd_mail(args):
    """One mail as plain text (it stays unread); other people's words, never run or opened."""
    sp = Spark(need())
    try:
        items = mail_items(sp, args.nummer)
        if not 1 <= args.nummer <= len(items):
            sys.exit(f"Nummer 1 bis {len(items)} (siehe spark-tui mails).")
        m = sp.call("GET", "/api/profile/mail/message?" + urllib.parse.urlencode({"id": items[args.nummer - 1]["id"]}))
    except SparkError as e:
        sys.exit(str(e))
    print(f"Von: {plain(m.get('from'), 200)}\nBetreff: {plain(m.get('subject'), 200)}\n")
    print("\n".join(plain(line) for line in str(m.get("text") or "(kein Text)").splitlines()))


# ---------------------------------------------------------------- the window (Textual)
def cmd_window(args):
    conf = need()
    try:
        from textual.app import App
    except ImportError:
        # Debian/Raspberry Pi OS refuse pip outside a venv: Textual lives in spark-tui's own one, used from here
        py = os.path.join(VENV, "bin", "python3")
        if os.path.isfile(py) and os.path.realpath(sys.executable) != os.path.realpath(py):
            os.execv(py, [py, os.path.abspath(sys.argv[0])] + sys.argv[1:])
        sys.exit("Für das Fenster fehlt Textual, einmal einrichten:\n"
                 f"  {SETUP}\n"
                 "Ohne Fenster geht es mit: spark-tui frage '…'")
    run_window(Spark(conf), conf, App)


AG_STATE = {"queued": "○", "running": "◐", "done": "✓", "failed": "✗", "cancelled": "✗"}


def run_window(sp, conf, App):
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.message import Message
    from textual.widgets import Footer, Label, ListItem, ListView, Markdown, Static, TextArea

    class AskArea(TextArea):
        """Where a question is typed (Dominik 2026-10-19, plan eingabefelder 6a): three lines, grows with the text up to 6,
        then scrolls. Enter sends, Ctrl+J (or Shift+Enter, where the terminal tells it apart) makes a new line."""
        class Submitted(Message):
            def __init__(self, area, value):
                super().__init__()
                self.area, self.value = area, value

        async def _on_key(self, event):
            if event.key == "enter":
                event.prevent_default()
                event.stop()
                self.post_message(self.Submitted(self, self.text))
            elif event.key in ("ctrl+j", "shift+enter"):
                event.prevent_default()
                event.stop()
                self.insert("\n")
            else:
                await super()._on_key(event)

    class Answer(Markdown):
        """One message. The Spark's Markdown is shown formatted; links are never opened from here."""
        def on_markdown_link_clicked(self, event):
            event.prevent_default()

    class JobView(ModalScreen):
        BINDINGS = [Binding("escape", "dismiss", "zurück"), Binding("d", "doc", "als Dokument"),
                    Binding("x", "cancel", "abbrechen"), Binding("delete", "drop", "löschen")]

        def __init__(self, job):
            super().__init__()
            self.job = job

        def compose(self):
            with VerticalScroll(id="jobbox"):
                yield Label(f"{AG_STATE.get(self.job.get('state'), '?')} {self.job.get('title') or self.job.get('task', '')}", id="jobhead")
                yield Answer(self.job.get("report") or "_(noch kein Ergebnis)_")
            yield Footer()

        def _do(self, method, path, note):
            try:
                sp.call(method, path)
                self.app.notify(note)
            except SparkError as e:
                self.app.notify(str(e), severity="error")
            self.app.refresh_side()
            self.dismiss()

        def action_doc(self):
            self._do("POST", f"/api/profile/agent/jobs/{self.job['id']}/doc", "Als Dokument gespeichert.")

        def action_cancel(self):
            self._do("POST", f"/api/profile/agent/jobs/{self.job['id']}/cancel", "Abgebrochen.")

        def action_drop(self):
            self._do("DELETE", f"/api/profile/agent/jobs/{self.job['id']}", "Gelöscht.")

    class Week(ModalScreen):
        """F5: the page Kalender as text, a week at a time (← →)."""
        BINDINGS = [Binding("escape", "dismiss", "zurück"), Binding("left", "move(-1)", "Woche zurück"),
                    Binding("right", "move(1)", "Woche vor"), Binding("t", "move(0)", "heute")]

        def __init__(self):
            super().__init__()
            self.offset = 0

        def compose(self):
            with VerticalScroll(id="jobbox"):
                yield Static("…", id="week")
            yield Footer()

        def on_mount(self):
            self.load()

        def load(self):
            def run():
                try:
                    start, d = get_week(sp, self.offset)
                    text = "\n".join(calendar_lines(d, start))
                except SparkError as e:
                    text = str(e)
                self.app.call_from_thread(self.query_one("#week").update, text)
            threading.Thread(target=run, daemon=True).start()

        def action_move(self, step):
            self.offset = self.offset + step if step else 0
            self.load()

    class Ask(ModalScreen):
        BINDINGS = [Binding("escape", "dismiss", "zurück")]

        def __init__(self, head):
            super().__init__()
            self.head = head

        def compose(self):
            with Vertical(id="askbox"):
                yield Label(self.head)
                yield AskArea(id="askin")

        def on_ask_area_submitted(self, event):
            self.dismiss(event.value.strip())

    class SparkTui(App):
        TITLE = "Spark"
        CSS = """
        #side { width: 40; }
        #side.hidden { display: none; }
        #side ListView { height: 1fr; border: round $primary-darken-2; }
        #side ListView:focus-within { border: round $accent; }
        #today { height: auto; max-height: 12; border: round $primary-darken-2; padding: 0 1; }
        #log { border: round $accent; padding: 0 1; }
        #log Answer { margin: 0 0 1 0; }
        .who { color: $accent; text-style: bold; }
        .me { color: $secondary; text-style: bold; }
        #head { height: 1; background: $boost; padding: 0 1; }
        AskArea { height: auto; min-height: 5; max-height: 8; }
        #askbox, #jobbox { width: 90%; height: auto; max-height: 90%; border: round $accent; background: $surface; padding: 1 2; }
        JobView, Ask { align: center middle; }
        """
        BINDINGS = [Binding("f2", "focus_convos", "Gespräche"), Binding("f3", "focus_jobs", "Aufträge"),
                    Binding("f4", "refresh_side", "Heute"), Binding("f5", "calendar", "Kalender"), Binding("ctrl+n", "new_convo", "neues Gespräch"),
                    Binding("escape", "stop", "abbrechen", show=False), Binding("f10", "quit", "Ende")]

        def __init__(self):
            super().__init__()
            self.convos, self.jobs, self.convo = [], [], None
            self.busy, self.stop = False, threading.Event()

        def compose(self):
            yield Static("Spark · verbinde …", id="head")
            with Horizontal():
                with Vertical(id="side"):
                    yield ListView(id="convos")
                    yield ListView(id="jobs")
                    yield Static("", id="today")
                with Vertical():
                    yield VerticalScroll(id="log")
                    yield AskArea(id="ask")
            yield Footer()

        def on_mount(self):
            self.query_one("#convos").border_title = "Gespräche  F2"
            self.query_one("#jobs").border_title = "Aufträge  F3  (n neu)"
            self.query_one("#today").border_title = "Heute  F4"
            self.query_one("#ask").border_title = "Frag den Spark …  Enter senden · Strg+J neue Zeile"
            self.query_one("#ask").focus()
            self.hello()
            self.refresh_side()
            self.set_interval(HELLO_EVERY, self.hello)
            self.set_interval(HELLO_EVERY, self.refresh_side)

        def on_resize(self, event):
            # 1b on a wide terminal, one window below 100 columns (e.g. over SSH on a phone)
            self.query_one("#side").set_class(event.size.width < 100, "hidden")

        # -------- background calls (never on the screen's thread)
        def bg(self, fn, *a):
            threading.Thread(target=fn, args=a, daemon=True).start()

        def hello(self):
            def run():
                try:
                    d = sp.call("GET", "/api/tui/hello")
                    agent = {"": "Aufträge aus", "read": "Aufträge: nur lesen", "act": "Aufträge: auch handeln"}.get(d.get("agent", ""), "")
                    text = f"✦ Spark {d.get('spark', '')} · {d.get('profile', '')} · ● bereit · {agent}"
                    if d.get("program") and d["program"] != VERSION:
                        text += f" · Neue Version {d['program']}: spark-tui update"
                except SparkError as e:
                    text = f"✦ Spark · ● {e}"
                self.call_from_thread(self.query_one("#head").update, text)
            self.bg(run)

        def refresh_side(self):
            def run():
                out = {}
                for key, path in (("convos", "/api/profile/convos"), ("agent", "/api/profile/agent"),
                                  ("today", "/api/profile/today?tz=" + urllib.parse.quote(zone()))):
                    try:
                        out[key] = sp.call("GET", path)
                    except SparkError as e:
                        out[key] = e
                self.call_from_thread(self.show_side, out)
            self.bg(run)

        def show_side(self, out):
            cv = self.query_one("#convos")
            keep = (cv.index, self.query_one("#jobs").index)   # the 60 s refresh keeps the selection
            if isinstance(out.get("convos"), list):
                self.convos = out["convos"][:50]
                cv.clear()
                for c in self.convos:
                    mark = "● " if self.convo and c.get("id") == self.convo.get("id") else "  "
                    cv.append(ListItem(Label(mark + (c.get("title") or "Gespräch")[:34])))
            jl = self.query_one("#jobs")
            ag = out.get("agent")
            jl.clear()
            self.jobs = []
            if isinstance(ag, dict) and ag.get("on"):
                self.jobs = ag.get("jobs", [])[:20]
                for j in self.jobs:
                    jl.append(ListItem(Label(f"{AG_STATE.get(j.get('state'), '?')} {(j.get('title') or j.get('task', ''))[:34]}")))
                for p in ag.get("plans", [])[:10]:
                    jl.append(ListItem(Label(("‖ " if p.get("paused") else "▶ ") + str(p.get("text", ""))[:34]), disabled=True))
            else:
                jl.append(ListItem(Label(str(ag) if isinstance(ag, SparkError) else "Aufträge sind aus."), disabled=True))
            for lv, i in ((cv, keep[0]), (jl, keep[1])):
                if i is not None and len(lv.children):
                    lv.index = min(i, len(lv.children) - 1)
            td = out.get("today")
            lines = []
            if isinstance(td, dict):
                cards = td.get("cards", {})
                for e in (cards.get("calendar") or {}).get("next", [])[:4]:
                    lines.append(time.strftime("%d.%m. %H:%M", time.localtime(e["start"])) + "  " + str(e.get("title", ""))[:24])
                rem = (cards.get("reminders") or {}).get("next")
                if rem:
                    lines.append(time.strftime("%H:%M", time.localtime(rem["due"])) + "  ⏰ " + str(rem.get("text", ""))[:24])
                if "messages" in cards:
                    lines.append(f"Chats ungelesen  {cards['messages'].get('unread', 0)}")
            self.query_one("#today").update("\n".join(lines) or "Nichts für heute.")

        # -------- chat
        def add_msg(self, who, text, me=False):
            log = self.query_one("#log")
            log.mount(Label(who, classes="me" if me else "who"))
            w = Answer(text)
            log.mount(w)
            log.scroll_end(animate=False)
            return w

        def open_convo(self, c):
            self.convo = c
            log = self.query_one("#log")
            log.remove_children()
            for m in (c or {}).get("msgs", []):
                self.add_msg("Du" if m["role"] == "user" else "Spark", m.get("content", ""), m["role"] == "user")

        def on_list_view_selected(self, event):
            if event.list_view.id == "convos":
                i = event.list_view.index
                if i is not None and i < len(self.convos):
                    self.open_convo(self.convos[i])
                    self.query_one("#ask").focus()
            elif event.list_view.id == "jobs":
                i = event.list_view.index
                if i is not None and i < len(self.jobs):
                    jid = self.jobs[i]["id"]
                    def run():
                        try:
                            job = sp.call("GET", f"/api/profile/agent/jobs/{jid}")
                            self.call_from_thread(self.push_screen, JobView(job))
                        except SparkError as e:
                            self.call_from_thread(self.notify, str(e), severity="error")
                    self.bg(run)

        def on_key(self, event):
            if event.key == "n" and self.focused is self.query_one("#jobs"):
                event.stop()
                self.push_screen(Ask("Neuer Auftrag (der Spark arbeitet ihn im Hintergrund ab):"), self.new_job)

        def new_job(self, task):
            if not task:
                return
            def run():
                try:
                    sp.call("POST", "/api/profile/agent/jobs", {"task": task})
                    self.call_from_thread(self.notify, "Auftrag angelegt.")
                except SparkError as e:
                    self.call_from_thread(self.notify, str(e), severity="error")
                self.call_from_thread(self.refresh_side)
            self.bg(run)

        def on_ask_area_submitted(self, event):
            if event.area.id != "ask":
                return
            q = event.value.strip()
            if not q or self.busy:
                return
            event.area.clear()
            if q.lower() in ("/tipps", "/tips"):   # what this profile can say (Ich → Was ich kann)
                self.show_tips()
                return
            if not self.convo:
                self.convo = {"id": new_convo_id(), "title": title_of(q), "msgs": []}
            msgs = [{"role": m["role"], "content": m["content"]} for m in self.convo["msgs"]][-30:] + [{"role": "user", "content": q}]
            self.add_msg("Du", q, me=True)
            self.add_msg("Spark  schreibt …", "")
            who, out = self.query_one("#log").children[-2:]
            self.busy = True
            self.stop.clear()
            convo = self.convo

            def run():
                shown = [0.0]

                def piece(text):
                    if time.time() - shown[0] > 0.1:   # at most ten redraws a second
                        shown[0] = time.time()
                        self.call_from_thread(out.update, text + " ▍")
                try:
                    answer = sp.ask(msgs, convo["id"], piece, self.stop)
                    tip = ("\n\n_Tipp: " + " · ".join(f"„{s}“" for s in sp.more) + " · /tipps_") if sp.more and answer else ""
                    self.call_from_thread(out.update, (answer or "_(keine Antwort)_") + tip)
                    news = [{"role": "user", "content": q}, {"role": "assistant", "content": answer}] if answer else []
                    if news:
                        convo["msgs"] += news
                        try:
                            sp.call("PUT", "/api/profile/convos", {"id": convo["id"], "title": convo["title"], "add": news})
                        except SparkError:
                            pass
                except (SparkError, OSError) as e:
                    self.call_from_thread(out.update, f"**Nicht geklappt:** {e}")
                finally:
                    self.busy = False
                    self.call_from_thread(who.update, "Spark")
                    self.call_from_thread(self.query_one("#log").scroll_end, animate=False)
                    self.call_from_thread(self.refresh_side)
            self.bg(run)

        def show_tips(self):
            """/tipps: per area the sentences this profile can say, from the panel (GET /api/profile/saetze)."""
            self.add_msg("Du", "/tipps", me=True)
            out = self.add_msg("Spark", "…")

            def run():
                try:
                    d = sp.call("GET", "/api/profile/saetze")
                    if not d.get("on"):
                        text = "_Beispielsätze sind aus (Funktionen → „Das kannst du auch sagen“)._"
                    else:
                        text = "\n\n".join(f"**{a['name'][0]}**\n" + "\n".join(f"- {x['text'][0]}" for x in a["items"])
                                           for a in d.get("areas", [])) or "_Gerade ist nichts freigegeben._"
                except (SparkError, OSError, KeyError, TypeError) as e:
                    text = f"**Nicht geklappt:** {e}"
                self.call_from_thread(out.update, text)
            self.bg(run)

        def action_stop(self):
            self.stop.set()

        def action_new_convo(self):
            self.open_convo(None)
            self.query_one("#ask").focus()

        def focus_list(self, sel):
            lv = self.query_one(sel)
            if lv.index is None and len(lv.children):
                lv.index = 0
            lv.focus()

        def action_focus_convos(self):
            self.focus_list("#convos")

        def action_focus_jobs(self):
            self.focus_list("#jobs")

        def action_refresh_side(self):
            self.refresh_side()

        def action_calendar(self):
            self.push_screen(Week())

    SparkTui().run()


def main(argv=None):
    p = argparse.ArgumentParser(prog="spark-tui", description="Der Spark im Terminal.")
    p.add_argument("--version", action="version", version="spark-tui " + VERSION)
    sub = p.add_subparsers(dest="cmd")
    k = sub.add_parser("koppeln", help="mit der Zeile aus Ich → Terminal koppeln")
    k.add_argument("line")
    k.add_argument("--name", default="")
    a = sub.add_parser("adresse-dazu", help="eine weitere https-Adresse (z. B. von außen)")
    a.add_argument("url")
    f = sub.add_parser("frage", help="eine Frage, die Antwort als Text")
    f.add_argument("text", nargs="*")
    c = sub.add_parser("kalender", help="die Termine einer Woche")
    c.add_argument("--woche", type=int, default=0, help="0 diese, 1 nächste, -1 letzte Woche")
    n = sub.add_parser("neu", help="Schnell eintragen: eine Zeile wird ein Termin (fragt vorher)")
    n.add_argument("text", nargs="*")
    n.add_argument("--ja", action="store_true", help="ohne Rückfrage eintragen")
    m = sub.add_parser("mails", help="die neuesten Mails nach Tagen")
    m.add_argument("--anzahl", type=int, default=20, help="bis 200, ältere werden nachgeladen")
    r = sub.add_parser("mail", help="eine Mail aus der Liste als Text")
    r.add_argument("nummer", type=int)
    sub.add_parser("status", help="erreichbar? was darf dieses Terminal?")
    sub.add_parser("update", help="die neueste Version vom Spark holen (Prüfsumme geprüft)")
    args = p.parse_args(argv)
    {"koppeln": cmd_pair, "adresse-dazu": cmd_add, "frage": cmd_ask, "status": cmd_status, "update": cmd_update,
     "kalender": cmd_calendar, "neu": cmd_new, "mails": cmd_mails, "mail": cmd_mail}.get(args.cmd, cmd_window)(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
