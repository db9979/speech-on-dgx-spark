#!/usr/bin/env python3
"""spark-tui: the Spark in a terminal (ClockworkPi uConsole, any Linux or Mac terminal, also over SSH).

    spark-tui koppeln 'https://…#tui=CODE[&fp=SHA256]' [--name uConsole]   pair once (Ich → Terminal in the panel)
    spark-tui adresse-dazu https://spark.example.org                        a second address (outside, checked as usual)
    spark-tui                                                                the window (needs Textual)
    spark-tui frage 'Wann fährt der erste Bus?'                              one question, the answer as text
    echo 'Text' | spark-tui frage 'Fasse das zusammen'                       the piped text goes with the question
    spark-tui status                                                         reachable? what may this terminal do?

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
import socket
import ssl
import sys
import threading
import time
import urllib.parse

VERSION = "1.0.0"
HEADER = "X-Speech-Device"
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
    print("\n  Fertig. Starten mit:  spark-tui")


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
          f"spark-tui {VERSION}" + (f" (auf dem Spark {d['program']})" if d.get("program") and d["program"] != VERSION else ""))


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


# ---------------------------------------------------------------- the window (Textual)
def cmd_window(args):
    conf = need()
    try:
        from textual.app import App
    except ImportError:
        sys.exit("Für das Fenster fehlt Textual: python3 -m pip install --user textual\n"
                 "Ohne Fenster geht es mit: spark-tui frage '…'")
    run_window(Spark(conf), conf, App)


AG_STATE = {"queued": "○", "running": "◐", "done": "✓", "failed": "✗", "cancelled": "✗"}


def run_window(sp, conf, App):
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Footer, Input, Label, ListItem, ListView, Markdown, Static

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

    class Ask(ModalScreen):
        BINDINGS = [Binding("escape", "dismiss", "zurück")]

        def __init__(self, head):
            super().__init__()
            self.head = head

        def compose(self):
            with Vertical(id="askbox"):
                yield Label(self.head)
                yield Input(id="askin")

        def on_input_submitted(self, event):
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
        #askbox, #jobbox { width: 90%; height: auto; max-height: 90%; border: round $accent; background: $surface; padding: 1 2; }
        JobView, Ask { align: center middle; }
        """
        BINDINGS = [Binding("f2", "focus_convos", "Gespräche"), Binding("f3", "focus_jobs", "Aufträge"),
                    Binding("f4", "refresh_side", "Heute"), Binding("ctrl+n", "new_convo", "neues Gespräch"),
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
                    yield Input(placeholder="Frag den Spark …  (Enter senden)", id="ask")
            yield Footer()

        def on_mount(self):
            self.query_one("#convos").border_title = "Gespräche  F2"
            self.query_one("#jobs").border_title = "Aufträge  F3  (n neu)"
            self.query_one("#today").border_title = "Heute  F4"
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

        def on_input_submitted(self, event):
            if event.input.id != "ask":
                return
            q = event.value.strip()
            if not q or self.busy:
                return
            event.input.value = ""
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
                    self.call_from_thread(out.update, answer or "_(keine Antwort)_")
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
    sub.add_parser("status", help="erreichbar? was darf dieses Terminal?")
    args = p.parse_args(argv)
    {"koppeln": cmd_pair, "adresse-dazu": cmd_add, "frage": cmd_ask, "status": cmd_status}.get(args.cmd, cmd_window)(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
