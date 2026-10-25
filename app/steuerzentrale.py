"""Steuerzentrale am Bildschirm, the screen half (plan Raspberry-Pi split B9, Dominik 2026-10-16).

Runs as the unit speech-spark-schirm on the first console (tty1) of the panel computer: no desktop, no browser, no
sign-in, about 20 MB. Once a second it asks the panel on this machine (GET /api/schirm/zustand on 127.0.0.1, with the
key in KEY that the panel made; panel/schirm.py) and draws one screen with everything: the day in numbers, the flow of
the running requests through the stages on the computer each one runs on, both computers' load, the devices, the
services and the internet behind the Wächter, what needs the admin, the models, the last events, security, maintenance
and the last 20 minutes as curves. Only kinds, places, times and numbers: the panel never sends what was asked or
answered.

The size follows the screen: at the start and whenever the screen changes, the resolution of the console (fb0) picks
a Terminus font so the picture has at least BASIS columns and rows (Full HD 12×24 → 160×45, 4K 16×32 → 240×67);
"kleiner" or "groesser" in the settings take the next font. A missing glyph of the console font is replaced
(ERSATZ), so the picture never shows a box. Outside the admin's times the screen goes dark (the console's own
blanking, the monitor sleeps); the picture moves by a character now and then (Schutz vor Einbrennen).

    python3 steuerzentrale.py            the screen (only on a console)
    python3 steuerzentrale.py --probe    one picture as text to stdout, from a saved state on stdin (self-tests)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, load_config  # noqa: E402

GEDULD = 5                                  # the panel counts as gone after this many failed questions in a row
KEY = os.path.join(STATE, "schirm.key")     # made by the panel (panel/schirm.py), read here
HEADER = "X-Speech-Schirm"
PFAD = "/api/schirm/zustand"
FB = "/sys/class/graphics/fb0/virtual_size"
FONTS = "/usr/share/consolefonts"
SCHRIFTEN = ((8, 16, "Uni3-TerminusBold16"), (10, 20, "Uni3-TerminusBold20x10"), (11, 22, "Uni3-TerminusBold22x11"),
             (12, 24, "Uni3-TerminusBold24x12"), (14, 28, "Uni3-TerminusBold28x14"), (16, 32, "Uni3-TerminusBold32x16"))
BASIS = (160, 45)           # the full picture needs this many columns and rows
KNAPP = (120, 36)           # below this a short list without the flow
FARBEN = ("c", "p", "g", "b")   # one colour per running request
TIOCLINUX, GIO_UNIMAP = 0x541C, 0x4B66
# a glyph the console font lacks: first the stand-in from the old PC set, then plain ASCII
ERSATZ = {"▁": "_", "▂": "▄", "▃": "▄", "▅": "▄", "▆": "█", "▇": "█", "✓": "√", "✖": "x", "▶": "►", "▸": ">", "▾": "v",
          "●": "•", "○": "o", "┄": "-", "┆": "¦", "━": "═", "┃": "║", "┓": "╗", "┗": "╚", "┛": "╝", "┏": "╔", "╌": "-",
          "⚠": "!", "…": "~", "↻": "@", "√": "v", "►": ">", "•": "*", "¦": "|", "═": "=", "║": "|", "╗": "+", "╚": "+",
          "╝": "+", "╔": "+", "▄": "_", "█": "#", "░": ".", "▌": "|", "─": "-", "│": "|", "┌": "+", "┐": "+", "└": "+",
          "┘": "+", "╭": "┌", "╮": "┐", "╰": "└", "╯": "┘", "→": ">", "↓": "v", "·": ".", "°": "o", "Ø": "O", "▲": "^"}
STUFEN = (("asr", "Hören", "Spracherkennung", "modell"), ("weiche", "Weiche", "Absicht", "panel"),
          ("llm", "Sprachmodell", "Antwort", "modell"), ("tool", "Werkzeuge", "Suchen · Schalten · Lesen", "panel"),
          ("tts", "Sprechen", "Sprachausgabe", "modell"))
SCHRITT = {"asr": "asr", "weiche": "weiche", "llm": "llm", "tool": "tool", "tts": "tts", "ack": "tts"}
DIENST = {"ok": "g", "load": "y", "down": "r", "off": "d", "pause": "b"}
STUFE = {"bad": "r", "warn": "y", "info": "m"}
RECHNER = {"modell": "Modell-Rechner", "panel": "Panel-Rechner"}
TEIL = {"asr": "Hören (ASR)", "tts": "Sprechen (TTS)", "llm": "Sprachmodell", "sehen": "Bildverständnis", "helfer": "Hilfsmodell", "bild": "Bilder", "musik": "Musik", "werkstatt": "Werkstatt",
        "waerter": "Wärter", "turn": "TURN", "gehaeuse": "Gehäuse", "notasr": "Notbetrieb-ASR"}
ZUSTAND = {"active": "läuft", "bereit": "bereit", "inactive": "aus", "activating": "startet", "deactivating": "stoppt", "failed": "Fehler"}


# ---------------------------------------------------------------- the picture as a grid of (glyph, colour)
# a box's own surface (Dominik 2026-10-17, draft 1): its colour -> the console colour 1-7 behind its inside
FLAECHE = {"y": 3, "c": 6, "p": 5, "g": 2, "b": 4, "d": 4, "w": 4, "m": 4}


class Raster:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.z = [[(" ", "w")] * w for _ in range(h)]
        self.bg = [[0] * w for _ in range(h)]      # the surface behind each cell (0: the screen's own)

    def put(self, x, y, s, col="w"):
        if 0 <= y < self.h:
            for i, ch in enumerate(str(s)):
                if 0 <= x + i < self.w:
                    self.z[y][x + i] = (ch, col)
        return x + len(str(s))

    def segs(self, x, y, parts, bis=None):
        for s, col in parts:
            if bis is not None:
                s = s[:max(0, bis - x)]
            x = self.put(x, y, s, col)
        return x

    def hl(self, x1, x2, y, col, ch="─"):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.put(x, y, ch, col)

    def vl(self, x, y1, y2, col, ch="│"):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.put(x, y, ch, col)

    def box(self, x, y, w, h, col="d", titel="", tcol="W", voll=False, flaeche=True):
        if w < 2 or h < 2:
            return
        for i in range(1, h - 1) if voll else ():      # covers what was drawn below it
            self.put(x + 1, y + i, " " * (w - 2), "w")
        for yy in range(max(0, y + 1), min(self.h, y + h - 1)):
            for xx in range(max(0, x + 1), min(self.w, x + w - 1)):
                self.bg[yy][xx] = FLAECHE.get(col, 0) if flaeche else 0
        self.put(x, y, "╭" + "─" * (w - 2) + "╮", col)
        self.put(x, y + h - 1, "╰" + "─" * (w - 2) + "╯", col)
        for i in range(1, h - 1):
            self.put(x, y + i, "│", col)
            self.put(x + w - 1, y + i, "│", col)
        if titel:
            self.put(x + 2, y, " " + titel[:max(0, w - 6)] + " ", tcol)

    def text(self):
        return "\n".join("".join(c for c, _ in row).rstrip() for row in self.z)


def kurz(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def zahl(v, nach=0):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "–"
    return (f"{v:.{nach}f}" if nach else str(round(v))).replace(".", ",")


def balken(p, n):
    if not isinstance(p, (int, float)):
        return [("░" * n, "d")]
    f = max(0, min(n, round(p / 100 * n)))
    return [("█" * f, "g" if p < 70 else "y" if p < 90 else "r"), ("░" * (n - f), "d")]


def linie(werte, n, lo=None, hi=None):
    """A curve of n characters from the values (None: a gap), oldest left."""
    v = [x for x in werte or [] if isinstance(x, (int, float))]
    if not v or n <= 0:
        return " " * max(0, n)
    lo = min(v) if lo is None else lo
    hi = max(v) if hi is None else hi
    out = []
    for i in range(n):
        x = (werte or [])[min(len(werte) - 1, i * len(werte) // n)] if werte else None
        out.append(" " if not isinstance(x, (int, float)) else "▁▂▃▄▅▆▇█"[max(0, min(7, int((x - lo) / ((hi - lo) or 1) * 7.99)))])
    return "".join(out)


def uhr(t, sek=True):
    if not isinstance(t, (int, float)):
        return "–"
    return time.strftime("%H:%M:%S" if sek else "%H:%M", time.localtime(t))


# ---------------------------------------------------------------- what the state says
def stufe_von(d):
    lv = {h.get("level") for h in d.get("hinweise") or []}
    return "bad" if "bad" in lv else "warn" if "warn" in lv else "ok"


def laufende(d):
    reqs = [r for r in (d.get("live") or {}).get("reqs") or [] if not r.get("done")]
    return reqs[:len(FARBEN)]


def gezeigt(d):
    """What the flow draws: the running requests, then the finished ones the Live picture still shows (the last one,
    and the others for live.FADE seconds after a newer one came), so an answer does not vanish the moment it is done."""
    reqs = [r for r in (d.get("live") or {}).get("reqs") or [] if isinstance(r, dict)]
    fertig = [r for r in reqs if r.get("done") and (r.get("last") or (r.get("left") or 0) > 0)]
    return (laufende(d) + fertig)[:len(FARBEN)]


def weg(r):
    """The stages a request went through, in order, with the stage it is at now."""
    out = []
    for s in r.get("steps") or []:
        k = SCHRITT.get(s.get("k"))
        if k and (not out or out[-1] != k):
            out.append(k)
    k = SCHRITT.get(r.get("stage"))
    if k and (not out or out[-1] != k):
        out.append(k)
    return out


def rechner_karten(d):
    r = d.get("rechner") or {}
    return {k["id"]: k for k in r.get("liste") or [] if isinstance(k, dict)} if r.get("an") else {}


# ---------------------------------------------------------------- the picture
def kopf(R, d, jetzt):
    live, tag = d.get("live") or {}, d.get("tag") or {}
    st = stufe_von(d)
    R.put(0, 0, " SPARK ", "K")
    R.put(8, 0, "Steuerzentrale", "W")
    n = len(laufende(d))
    teile = [({"ok": "● alles normal", "warn": "● Hinweis offen", "bad": "● Störung"}[st], {"ok": "g", "warn": "y", "bad": "r"}[st]),
             ("   ·   ", "d"), (f"{n} {'Anfrage läuft' if n == 1 else 'Anfragen laufen'}", "y" if n else "m"),
             ("   ·   ", "d"), (f"{len(d.get('hinweise') or [])} {'Hinweis' if len(d.get('hinweise') or []) == 1 else 'Hinweise'}", "g" if st == "ok" else STUFE.get(st, "y")),
             ("   ·   ", "d"), ("Wartungspause" if (live.get("wartung") or {}).get("on") else "keine Wartung", "b" if (live.get("wartung") or {}).get("on") else "m"),
             ("   ·   ", "d"), (str(tag.get("version") or ""), "m")]
    R.segs(24, 0, teile, R.w - 22)
    R.put(R.w - 19, 0, time.strftime("%a %d.%m.  %H:%M:%S", time.localtime(jetzt)).replace("Mon", "Mo").replace("Tue", "Di")
          .replace("Wed", "Mi").replace("Thu", "Do").replace("Fri", "Fr").replace("Sat", "Sa").replace("Sun", "So"), "W")
    g, door = live.get("guard") or {}, live.get("door") or {}
    an, aus = (d.get("zeiten") or [7, 23])[:2]
    ak = live.get("aktiv") or {}     # aktiv.py: people with a request in the last 10 minutes
    R.segs(1, 1, [("Aktiv 10 min ", "m"), (zahl(ak.get("gesamt")), "W"),
                  (f" ({zahl(ak.get('profile'))} Profile · {zahl(ak.get('gaeste'))} Gäste)  ·  ", "m"),
                  ("Heute ", "m"), (zahl(tag.get("answers")), "W"), (" Antworten  ·  erster Ton Ø ", "m"),
                  (zahl(tag.get("first_sound"), 1) + " s", "y" if tag.get("slower") else "W"),
                  ("  ·  Wächter ", "m"), (f"{zahl(g.get('ok'))} erlaubt", "W"), (" · ", "m"), (f"{zahl(g.get('bad'))} geblockt", "y" if g.get("bad") else "g"),
                  ("  ·  Eingang ", "m"), (f"{zahl(door.get('in'))} rein", "W"), (" · ", "m"), (f"{zahl(door.get('out'))} abgewiesen", "y" if door.get("out") else "g"),
                  ("  ·  Sicherung ", "m"), (uhr(tag.get("backup"), False) if tag.get("backup") else "keine", "g" if tag.get("backup") else "y"),
                  ("  ·  Bildschirm ", "m"), ("immer an" if an == aus else f"{an}–{aus} Uhr", "m")], R.w - 1)
    R.hl(0, R.w - 1, 2, "d", "━")


def spitze_text(karte):
    """„▶ <the biggest service> N %“ or „▶ Leerlauf“ (rechnerblick.spitze)."""
    sp = (karte or {}).get("spitze") or {}
    return f"▶ {sp['name']} {zahl(sp.get('pct'))} %" if sp.get("name") else "▶ Leerlauf"


def bahn(R, x, w, top, bot, k, karte, live, feld=0):
    """One computer's frame with its numbers; returns the rows where the stages may go. „feld“: the width of the
    biggest service, the same in both frames, so „Platte“ starts at the same place (Spiegel-Karten 2026-10-20)."""
    name = (karte or {}).get("name") or ("dieser Rechner" if k == "spark" else RECHNER.get(k, ""))
    titel = f"{name} · {RECHNER[k]}" if k in RECHNER else f"{name} · Panel und Modelle"
    weg_ = k == "modell" and karte and not karte.get("ok")
    R.box(x, top, w, bot - top + 1, "r" if weg_ else "b", kurz(titel, w - 6), "r" if weg_ else "b", flaeche=False)   # the frame stays dark
    i, n = x + 2, max(4, (w - 26) // 2)
    if k == "spark":
        s = live.get("sys") or {}
        R.segs(i, top + 1, [("CPU ", "m")] + balken(s.get("cpu"), n) + [(f" {zahl(s.get('cpu'))} %  ", "w"), ("GPU ", "m")]
               + balken(s.get("gpu"), n) + [(f" {zahl(s.get('gpu'))} %", "w")], x + w - 1)
        R.segs(i, top + 2, [("frei ", "m"), (f"{zahl(s.get('free'), 1)} GiB  ", "w"), (f"{zahl(s.get('temp'))} °C", "w")], x + w - 1)
        R.put(i, top + 3, kurz("Strom " + zahl(s.get("power")) + " W", w - 4), "m")
        hist = (s.get("hist") or {}).get("gpu")
    else:
        c = karte or {}
        gpu = (c.get("gpu") or {}).get("util") if k == "modell" else None
        teile = [("CPU ", "m")] + balken(c.get("cpu"), n) + [(f" {zahl(c.get('cpu'))} %  ", "w")]
        # Spiegel-Karten (Dominik 2026-10-20): both frames have the same lines and places, a GPU the Pi lacks is „–“
        teile += ([("GPU ", "m")] + balken(gpu, n) + [(f" {zahl(gpu)} %", "w")]) if k == "modell" else [("GPU ", "m"), ("– keine", "m")]
        R.segs(i, top + 1, teile, x + w - 1)
        tot, frei = c.get("ram_total"), c.get("ram_frei")
        pct = 100 * (tot - frei) / tot if isinstance(tot, (int, float)) and isinstance(frei, (int, float)) and tot else None
        nach = 0 if isinstance(tot, (int, float)) and tot >= 10 else 1
        R.segs(i, top + 2, [("RAM ", "m")] + balken(pct, n) + [(f" {zahl(tot - frei if pct is not None else None, nach)}/{zahl(tot, 0)} GiB ", "w"),
                                                              (f"{zahl(c.get('temp'))} °C", "y" if (c.get("temp") or 0) >= (c.get("temp_warn") or 80) else "w")], x + w - 1)
        strom = c.get("strom") or {}
        lu = {True: "Lüfter an", False: "Lüfter aus"}.get(c.get("luefter"), "")
        hg = c.get("haenger") or {}   # the Hänge-Wächter (loopwacht.py): stalls of the panel in the last 24 hours
        rest = " · ".join(p for p in (f"Platte {zahl(c.get('platte_pct'))} %", lu,
                                      f"Strom {strom.get('spannung')}" if strom else "",
                                      f"hing {hg['n']}-mal" if hg.get("n") else "") if p)
        # „Wer rechnet gerade“ (rechnerblick.spitze): the biggest service first, in a field as wide in both frames
        feld = min(max(feld, len(spitze_text(c))) + 2, w - 4)
        if weg_:
            R.put(i, top + 3, kurz("nicht erreichbar", w - 4), "r")
        else:
            R.segs(i, top + 3, [(kurz(spitze_text(c), feld - 2).ljust(feld), "y" if (c.get("spitze") or {}).get("name") else "m"), (rest, "m")], x + w - 1)
        hist = (c.get("kurven") or {}).get("gpu" if k == "modell" else "cpu")
    R.put(i, top + 4, "20 min ", "m")
    R.put(i + 7, top + 4, linie(hist, w - 11, 0, 100), "g")
    R.hl(x + 1, x + w - 2, top + 5, "d", "┄")
    return top + 6, bot - 3


def werkzeug_teile(lauf):
    """Which tool each shown request uses or used, in its colour: ▶ running, ✓ done, ✗ failed (Dominik 2026-10-16)."""
    teile = []
    for j, r in enumerate(lauf):
        ts = [st for st in r.get("steps") or [] if st.get("k") == "tool" and st.get("n")]
        jetzt = r.get("stage") == "tool" and not r.get("done")
        name = (r.get("tool") if jetzt else "") or (ts[-1].get("n") if ts else "")
        if not name:
            continue
        mark = "▶" if jetzt else "✓" if ts[-1].get("ok", True) is not False else "✗"
        mehr = f" +{len(ts) - 1}" if len(ts) > 1 else ""
        teile += ([(" · ", "m")] if teile else []) + [(f"{mark} {name}{mehr}", FARBEN[j % len(FARBEN)])]
    return teile


def zuletzt_teile(live, zeit=True):
    """While no shown request uses a tool: the last tools that gave something back, newest first, each name once,
    with ✓/✗ and the time (Dominik 2026-10-17: "Suchen · Schalten · Lesen" says nothing)."""
    teile, namen = [], set()
    for x in live.get("rets") or []:
        name = x.get("tool") if isinstance(x, dict) else None
        if not name or name in namen:
            continue
        namen.add(name)
        mark = "✓" if x.get("ok", True) is not False else "✗"
        teile += ([(" · ", "m")] if teile else []) + [(f"{mark} {name}" + (f" {uhr(x.get('t'), False)}" if zeit else ""), "w")]
    return teile


def stufen_zeichnen(R, d, lanes, lauf, stufen):
    """The five stages in the frame of the computer each runs on, the requests' ways between them."""
    live = d.get("live") or {}
    svc = live.get("svc") or {}
    karten = rechner_karten(d)
    y0, y1 = lanes[0][3], lanes[0][4]
    hoch = 4 if y1 - y0 + 1 >= 5 * 4 + 4 else 3
    gap = max(1, (y1 - y0 + 1 - 5 * hoch) // 4)
    pos = {}
    keys = [s[0] for s in stufen]
    for i, (key, name, sub, wo) in enumerate(stufen):
        lx, lw = next(((x, w) for kk, x, w, _, _ in lanes if kk == wo), lanes[0][1:3])
        pos[key] = (lx + (6 if len(lanes) == 1 else 2), y0 + i * (hoch + gap), min(lw - (8 if len(lanes) == 1 else 4), 40))
    # the ways first and the boxes over them: a way that skips a stage never runs across its box (Dominik 2026-10-16);
    # arrow heads and marks come last, they sit on the boxes' edges
    marken = []
    for j, r in enumerate(lauf):
        col, w = FARBEN[j], weg(r)
        for a, b in zip(w, w[1:]):
            ia, ib = keys.index(a), keys.index(b)
            ax, ay, aw = pos[a]
            bx, by, bw = pos[b]
            xa, xb = ax + aw // 2 - 3 + 2 * j, bx + bw // 2 - 3 + 2 * j
            if ib < ia:
                marken.append((bx + bw - 16, by + 1, "↻", col))
                continue
            if ib == ia + 1 or xa != xb or ax == bx and len(lanes) > 1:
                yy = ay + hoch
                if ib == ia + 1:
                    if xa == xb:
                        R.vl(xa, yy, by - 1, col)
                    else:
                        R.put(xa, yy, "└" if xb > xa else "┘", col)
                        R.hl(min(xa, xb) + 1, max(xa, xb) - 1, yy, col)
                        R.put(xb, yy, "┐" if xb > xa else "┌", col)
                        if by - 1 > yy:
                            R.vl(xb, yy + 1, by - 1, col)
                else:
                    R.vl(xa, yy, by - 1, col)
                marken.append((xb, by, "▾", col))
                if ib == ia + 1 and not r.get("done") and SCHRITT.get(r.get("stage")) != a:
                    marken.append((ax + 4 + j, ay + hoch - 1, "✓", "g"))
            else:   # one frame, a stage skipped: round the left side
                lx = ax - 4 + j
                R.put(lx, ay + 1, "┌", col)
                R.hl(lx + 1, ax - 1, ay + 1, col)
                R.vl(lx, ay + 2, by, col)
                R.put(lx, by + 1, "└", col)
                R.hl(lx + 1, bx - 2, by + 1, col)
                R.put(bx - 1, by + 1, "▸", col)
    for key, name, sub, wo in stufen:
        bx, y, bw = pos[key]
        aktiv = [j for j, r in enumerate(lauf) if SCHRITT.get(r.get("stage")) == key]
        teile = werkzeug_teile(lauf) if key == "tool" else []
        vorher = [] if teile or key != "tool" else zuletzt_teile(live, hoch == 4)   # nothing running: what ran last
        R.box(bx, y, bw, hoch, "y" if aktiv else "d", voll=True)
        e = R.put(bx + 2, y + 1, name, "W")
        if aktiv and not teile:             # the tools carry their own ▶
            R.put(e + 1, y + 1, "▶", "y")
        s = svc.get(key) or {}
        if s.get("wait"):
            R.put(bx + bw - 13, y + 1, f"{s['wait']} warten", "y")
        if s.get("st"):
            R.put(bx + bw - 3, y + 1, "●", DIENST.get(s["st"], "m"))
        if key == "llm" and karten.get("modell", {}).get("llm"):
            sub = karten["modell"]["llm"]
        runden = max([sum(1 for st in r.get("steps") or [] if st.get("k") == "llm") for r in lauf] or [0])
        if key == "llm" and runden > 1:
            sub += f" · Runde {runden}"
        zx, zy = (bx + 2, y + 2) if hoch == 4 else (e + (1 if teile or vorher else 3), y + 1)
        if vorher:                           # a low box has no room for the word and the times
            zx, teile = R.put(zx, zy, "zuletzt ", "m") if hoch == 4 else zx, vorher
        if teile:
            bis = bx + bw - (2 if hoch == 4 else 5)
            namen = teile[::2]               # every other part is the dot between two
            for i, (t, col) in enumerate(namen):
                rest = len(namen) - i - 1
                platz = bis - zx - (len(f" +{rest}") if rest else 0)
                if not i and len(t) > platz:   # the first name whole before any count
                    platz = bis - zx
                if i and platz < 5 + 3:      # no room for a readable name: the rest as a number
                    R.put(zx, zy, kurz(f" +{rest + 1}", bis + 3 - zx), "m")
                    break
                zx = R.put(zx, zy, " · ", "m") if i else zx
                zx = R.put(zx, zy, kurz(t, platz - (3 if i else 0)), col)
        else:
            R.put(zx, zy, kurz(sub, bx + bw - 2 - zx - (0 if hoch == 4 else 4)), "m")
    for mx, my, ch, col in marken:
        R.put(mx, my, ch, col)
    return pos, hoch


def geraete(R, d, x, w, top, bot, lauf, pos, hoch, busx):
    live = d.get("live") or {}
    bus = live.get("bus") or {}
    R.vl(busx, top + 1, bot, "d", "┆")
    R.put(max(0, busx - 22), bot, kurz(f"Von selbst · heute {sum(v for v in bus.values() if isinstance(v, int))}", 22), "m")
    R.put(x, top, "GERÄTE", "m")
    y = top + 1
    for j, r in enumerate(lauf):
        col = FARBEN[j]
        sx, sy, _ = pos[(weg(r) or ["weiche"])[0]]
        ziel = sy + 1 + (j % max(1, hoch - 2))
        y = max(y, min(ziel - 1, bot - 4))       # the device next to the stage it came in at
        name = ("Von selbst · " + (r.get("src") or "")) if r.get("auto") else r.get("dev") or "Gerät"
        R.box(x, y, w, 4, col)
        R.put(x + 2, y + 1, kurz(name, w - 4), col)
        R.put(x + 2, y + 2, kurz(f"{r.get('intent') or 'Anfrage'} · {'fertig in ' if r.get('done') else ''}{zahl(r.get('age'), 1)} s", w - 4), "m")
        R.hl(x + w, busx, y + 1, col)
        if ziel != y + 1:
            R.put(busx, y + 1, "┐" if ziel > y + 1 else "┘", col)
            R.vl(busx, min(y + 1, ziel) + 1, max(y + 1, ziel) - 1, col)
            R.put(busx, ziel, "└" if ziel > y + 1 else "┌", col)
        R.hl(busx + 1, sx - 2, ziel, col)
        R.put(sx - 1, ziel, "▸", col)
        y += 5
    conns = [c for c in live.get("conns") or [] if isinstance(c, dict)][:8]
    sp = (d.get("tag") or {}).get("speakers")
    zeilen = ([("Lautsprecher", f"{sp.get('online', 0)} von {sp.get('known', 0)}")] if isinstance(sp, dict) else []) \
        + [(c.get("name") or "", str(c.get("n") or "")) for c in conns if c.get("name") != "Lautsprecher"]
    h = min(len(zeilen) + 2, max(3, bot - y - 8))
    if bot - y >= 12 and zeilen:
        R.box(x, y, w, h, "d", "Verbunden", "w")
        for i, (a, b) in enumerate(zeilen[:h - 2]):
            R.put(x + 2, y + 1 + i, kurz(a, w - 5 - len(b)), "w")
            R.put(x + w - 2 - len(b), y + 1 + i, b, "m")
        y += h + 1
    door = live.get("door") or {}
    if bot - y >= 5:
        R.box(x, y, w, 5, "o", "Von außen ↓", "o")
        R.put(x + 2, y + 1, f"{zahl(door.get('in'))} rein heute", "w")
        R.put(x + 2, y + 2, f"{zahl(door.get('out'))} abgewiesen", "y" if door.get("out") else "g")
        last = next(iter(door.get("items") or []), None)
        R.put(x + 2, y + 3, kurz("zuletzt " + uhr(last.get("t"), False) if isinstance(last, dict) and last.get("t") else "niemand von außen", w - 4), "m")


def dienste(R, d, x, w, top, bot, lauf, pos, hoch):
    live = d.get("live") or {}
    svc, hints = live.get("svc") or {}, {h.get("at"): h for h in live.get("hints") or [] if isinstance(h, dict)}
    targets = [t for t in live.get("targets") or [] if isinstance(t, dict)]
    netz = [t for t in targets if t.get("zone") == "net"]
    heim = [t for t in targets if t.get("zone") != "net"]
    # like the Live picture (Dominik 2026-10-16): quiet targets (live.ruhe) fold into one line per group
    bereit, ruhig = [t for t in heim if t.get("quiet")], [t for t in netz if t.get("quiet")]
    if len(bereit) >= 2:
        heim = [t for t in heim if not t.get("quiet")]
    else:
        bereit = []
    if len(ruhig) >= 2:
        netz = [t for t in netz if not t.get("quiet")]
    else:
        ruhig = []
    R.put(x + 2, top, "DIENSTE UND ZIELE", "m")
    inet = bot - max(4, min(len(netz) + bool(ruhig), 4) + 3)
    reihen = inet - top - 2 - bool(bereit)
    schritt = 2 if len(heim) * 2 <= reihen else 1
    zeile, faerb = {}, {}
    for j, r in enumerate(lauf):
        for t in {r.get("to")} | {s.get("to") for s in r.get("steps") or []}:
            if t and t not in faerb:
                faerb[t] = FARBEN[j]
    zeigen = heim[:max(0, reihen // schritt)]
    rest = len(heim) - len(zeigen)
    if rest:
        zeigen = zeigen[:-1]
        rest += 1
    for i, t in enumerate(zeigen):
        y = top + 1 + i * schritt
        zeile[t.get("id")] = y
        col = faerb.get(t.get("id"))
        R.put(x + 1, y, "▌", col or "d")
        e = R.put(x + 3, y, kurz(t.get("name"), w * 3 // 5), "W" if col else "w")
        R.put(e + 2, y, kurz(t.get("sub"), x + w - 4 - e - 2), "m")
        h, s = hints.get(t.get("id")), svc.get(t.get("id")) or {}
        if h or s.get("st"):
            R.put(x + w - 2, y, "●", STUFE.get(h.get("level"), "y") if h else DIENST.get(s["st"], "m"))
    if rest:
        R.put(x + 3, top + 1 + len(zeigen) * schritt, f"+ {rest} weitere", "m")
    if bereit:
        y = top + 1 + (len(zeigen) + bool(rest)) * schritt
        e = R.put(x + 3, y, f"+ {len(bereit)} bereit", "w")
        R.put(e + 2, y, kurz(" · ".join(str(t.get("name") or "") for t in bereit), x + w - 4 - e - 2), "m")
    for k in range(x + 1, x + w - 1, 2):
        R.put(k, inet, "╌", "o")
    R.put(x + 2, inet, " INTERNET ↓ ", "o")
    g = live.get("guard") or {}
    R.put(x + 2, inet + 1, kurz(f"Wächter · {zahl(g.get('ok'))} erlaubt · {zahl(g.get('bad'))} geblockt · {zahl(g.get('cut'))} getrennt", w - 3),
          "y" if g.get("bad") else "g")
    for i, t in enumerate(netz[:max(0, bot - inet - 1)]):
        y = inet + 2 + i
        zeile[t.get("id")] = y
        col = faerb.get(t.get("id"))
        R.put(x + 1, y, "▌", col or "d")
        e = R.put(x + 3, y, kurz(t.get("name"), w * 3 // 5), "W" if col else "w")
        R.put(e + 2, y, kurz(t.get("sub"), x + w - 4 - e - 2), "m")
    if ruhig and bot - inet - 2 > len(netz):
        y = inet + 2 + len(netz)
        e = R.put(x + 3, y, f"+ {len(ruhig)} ruhig", "w")
        R.put(e + 2, y, kurz(" · ".join(str(t.get("name") or "") for t in ruhig), x + w - 4 - e - 2), "m")
    tx, ty, tw = pos["tool"]
    for j, r in enumerate(lauf):
        t = r.get("to") if r.get("stage") == "tool" else None
        if t not in zeile:
            continue
        col, net = FARBEN[j], next((z.get("zone") == "net" for z in targets if z.get("id") == t), False)
        y0, y1, mx = ty + 1 + j % max(1, hoch - 2), zeile[t], x - 1 - j
        ch, vch = ("━", "┃") if net else ("─", "│")
        R.hl(tx + tw, mx - 1, y0, "o" if net else col, ch)
        if y1 != y0:
            R.put(mx, y0, ("┓" if net else "┐") if y1 > y0 else ("┛" if net else "┘"), "o" if net else col)
            R.vl(mx, min(y0, y1) + 1, max(y0, y1) - 1, "o" if net else col, vch)
            R.put(mx, y1, ("┗" if net else "└") if y1 > y0 else ("┏" if net else "┌"), "o" if net else col)
        R.put(x, y1, "▸", "o" if net else col)


def rechts(R, d, x, w, top, bot):
    live, karten = d.get("live") or {}, rechner_karten(d)
    hin = [h for h in d.get("hinweise") or [] if isinstance(h, dict)]
    y = top
    h = 2 + max(1, min(len(hin), 4))
    R.box(x, y, w, h, STUFE.get(stufe_von(d), "g") if hin else "d", "Braucht dich", "y" if hin else "W")
    if not hin:
        R.put(x + 2, y + 1, "✓ nichts offen", "g")
    for i, a in enumerate(hin[:4]):
        R.put(x + 2, y + 1 + i, kurz(("⚠ " if a.get("level") != "info" else "· ") + str(a.get("text") or ""), w - 4), STUFE.get(a.get("level"), "y"))
    y += h + 1
    svc = live.get("svc") or {}
    mod = [(m.get("id"), m.get("state")) for m in (karten.get("modell") or {}).get("dienste") or []]
    zeilen = [(TEIL.get(k, k), ZUSTAND.get(s, s), "g" if s in ("active", "bereit") else "y" if s == "activating" else "r" if s == "failed" else "d")
              for k, s in mod] \
        or [(TEIL[k], (svc.get(k) or {}).get("word") or "–", DIENST.get((svc.get(k) or {}).get("st"), "d")) for k in ("asr", "llm", "tts")]
    zeilen = zeilen[:6]
    R.box(x, y, w, len(zeilen) + 2, "d", "Modelle und Dienste", "W")
    for i, (k, s, col) in enumerate(zeilen):
        R.put(x + 2, y + 1 + i, kurz(str(k), w // 2 - 2), "w")
        R.put(x + w // 2, y + 1 + i, kurz(str(s), w - w // 2 - 2), col)
    y += len(zeilen) + 3
    unten = bot - 9
    ev = [e for e in live.get("events") or [] if isinstance(e, dict)]
    hz = max(3, unten - y)
    R.box(x, y, w, hz, "d", "Zuletzt", "W")
    for i, e in enumerate(ev[:hz - 2]):
        R.put(x + 2, y + 1 + i, uhr(e.get("t")), "m")
        R.put(x + 11, y + 1 + i, kurz(f"{e.get('area')} · {e.get('text')}", w - 13), "w")
    y = unten + 1
    g, door, na = live.get("guard") or {}, live.get("door") or {}, live.get("notaus") or {}
    R.box(x, y, w, 5, "d", "Sicherheit", "W")
    R.segs(x + 2, y + 1, [("Eingang   ", "w"), (f"{zahl(door.get('in'))} rein · {zahl(door.get('out'))} abgewiesen", "y" if door.get("out") else "g")], x + w - 1)
    R.segs(x + 2, y + 2, [("Wächter   ", "w"), (f"{zahl(g.get('bad'))} geblockt · {zahl(g.get('ok'))} ok", "y" if g.get("bad") else "g")], x + w - 1)
    R.segs(x + 2, y + 3, [("Notaus    ", "w"), (f"Stufe {na.get('level')}" if na.get("level") else "keins", "r" if na.get("level") else "g")], x + w - 1)
    y += 5
    upd, wart, tag = live.get("upd") or {}, live.get("wartung") or {}, d.get("tag") or {}
    R.box(x, y, w, 3, "d", "Wartung", "W")
    R.put(x + 2, y + 1, kurz(" · ".join(p for p in ((f"Update {upd.get('pct')} % · {upd.get('step')}" if isinstance(upd.get("pct"), int) else "Update läuft")
                                                     if upd.get("run") else "",
                                                    "Wartungspause" if wart.get("on") else "",
                                                    "Sicherung " + uhr(tag.get("backup"), False) if tag.get("backup") else "keine Sicherung") if p), w - 4),
          "b" if upd.get("run") or wart.get("on") else "m")


def kurven(R, d, top):
    karten, live, tag = rechner_karten(d), d.get("live") or {}, d.get("tag") or {}
    if karten:
        m, p = karten.get("modell") or {}, karten.get("panel") or {}
        km, kp = m.get("kurven") or {}, p.get("kurven") or {}
        reihen = [(f"{m.get('name') or 'Modell'} GPU", km.get("gpu"), "y", 0, 100, "%"), (f"{m.get('name') or 'Modell'} CPU", km.get("cpu"), "g", 0, 100, "%"),
                  (f"{m.get('name') or 'Modell'} frei", km.get("frei"), "b", 0, m.get("ram_total"), "GiB"), (f"{p.get('name') or 'Panel'} CPU", kp.get("cpu"), "g", 0, 100, "%"),
                  (f"{p.get('name') or 'Panel'} °C", kp.get("temp"), "o", 20, 90, "°C")]
    else:
        h = (live.get("sys") or {}).get("hist") or {}
        reihen = [("GPU", h.get("gpu"), "y", 0, 100, "%"), ("CPU", h.get("cpu"), "g", 0, 100, "%"), ("frei", h.get("avail"), "b", 0, None, "GiB")]
    reihen.append(("Antworten je Stunde", tag.get("hours"), "c", 0, None, ""))
    R.hl(0, R.w - 1, top, "d", "━")
    R.put(0, top + 1, "LETZTE 20 MINUTEN", "m")
    R.put(R.w - 34, top + 1, "Antworten: die letzten 24 Stunden", "m")
    for i, (n, v, col, lo, hi, e) in enumerate(reihen[:R.h - top - 3]):
        y = top + 2 + i
        R.put(0, y, kurz(n, 19), "m")
        R.put(20, y, linie(v, R.w - 34, lo, hi), col)
        last = next((x for x in reversed(v or []) if isinstance(x, (int, float))), None)
        R.put(R.w - 12, y, kurz(f"{zahl(last, 1 if e == 'GiB' else 0)} {e}".strip(), 12), "W")


def bild(d, w, h, jetzt=None):
    """The whole screen for the state d on w×h characters."""
    jetzt = time.time() if jetzt is None else jetzt
    R = Raster(w, h)
    if not d:
        R.put(2, 1, "Steuerzentrale · wartet auf das Panel …", "y")
        return R
    kopf(R, d, jetzt)
    if w < KNAPP[0] or h < KNAPP[1]:
        return knapp(R, d)
    live = d.get("live") or {}
    reihen = 5 + 1
    kt = h - reihen - 4
    main_top, main_bot = 3, kt - 1
    L, Rw, S = max(22, w * 15 // 100), max(30, w * 22 // 100), max(30, w * 23 // 100)
    M = w - L - Rw - S - 4
    mx = L + 2
    karten = rechner_karten(d)
    if karten:
        lw = M // 2
        lanes = [("modell", mx, lw), ("panel", mx + lw, M - lw)]
    else:
        lanes = [("spark", mx, M)]
    ln = []
    feld = max([len(spitze_text(c)) for c in karten.values()] or [0])
    for k, x, lw in lanes:
        a, b = bahn(R, x, lw, main_top, main_bot, k, karten.get(k), live, feld)
        ln.append((k, x, lw, a, b))
    stufen = [(k, n, s, wo if karten else "spark") for k, n, s, wo in STUFEN]
    lauf = gezeigt(d)
    pos, hoch = stufen_zeichnen(R, d, ln, lauf, stufen)
    foot = ("geladen: " + " · ".join(TEIL.get(m.get("id"), m.get("id")) for m in (karten.get("modell") or {}).get("dienste") or [] if m.get("state") == "active")) if karten else ""
    if karten:
        R.put(ln[0][1] + 2, main_bot - 1, kurz(foot, ln[0][2] - 4), "m")
        R.put(ln[1][1] + 2, main_bot - 1, kurz("läuft: " + " · ".join(TEIL.get(x.get("id"), x.get("id")) for x in (karten.get("panel") or {}).get("dienste") or []
                                                                    if x.get("state") == "active"), ln[1][2] - 4), "m")
    geraete(R, d, 0, L - 1, main_top, main_bot, lauf, pos, hoch, L)
    dienste(R, d, mx + M + 1, S, main_top, main_bot, lauf, pos, hoch)
    rechts(R, d, w - Rw, Rw, main_top, main_bot)
    kurven(R, d, kt)
    R.put(0, h - 1, "Nur Art, Ort, Zeit und Zahlen · nie was gefragt oder geantwortet wurde", "m")
    if not d.get("live_an"):
        R.put(74, h - 1, kurz("· Anfragen erscheinen mit Live an: Einstellungen → Spark → Betrieb → Logs", w - 75), "y")
    return R


def knapp(R, d):
    """A small screen: the lines without the flow."""
    y = 3
    for k in rechner_karten(d).values():
        R.put(1, y, kurz(f"{k.get('name')}: CPU {zahl(k.get('cpu'))} % · frei {zahl(k.get('ram_frei'), 1)} GiB · {zahl(k.get('temp'))} °C", R.w - 2), "w")
        y += 1
    for j, r in enumerate(gezeigt(d)):
        R.put(1, y + 1, kurz(f"{r.get('dev')} · {' → '.join(weg(r))} · {zahl(r.get('age'), 1)} s", R.w - 2), FARBEN[j])
        y += 1
    for a in (d.get("hinweise") or [])[:5]:
        R.put(1, y + 2, kurz("⚠ " + str(a.get("text") or ""), R.w - 2), STUFE.get(a.get("level"), "y"))
        y += 1
    for e in ((d.get("live") or {}).get("events") or [])[:max(0, R.h - y - 4)]:
        R.put(1, y + 3, kurz(f"{uhr(e.get('t'))} {e.get('area')} · {e.get('text')}", R.w - 2), "m")
        y += 1
    return R


# ---------------------------------------------------------------- the console
def ersetzen(s, have):
    """The text with every glyph the font lacks replaced (have: the font's characters, None: all there)."""
    if have is None:
        return s
    out = []
    for ch in s:
        while ch not in have and ch in ERSATZ and ord(ch) > 127:
            ch = ERSATZ[ch]
        out.append(ch if ch in have or ord(ch) < 128 else "?")
    return "".join(out)


def schrift(px, wahl="auto", da=os.path.exists):
    """The console font for a screen of px (width, height) pixels: the biggest that still gives BASIS characters."""
    have = [(w, h, n) for w, h, n in SCHRIFTEN if da(os.path.join(FONTS, n + ".psf.gz"))]
    if not have or not px:
        return None
    i = max([k for k, (w, h, _) in enumerate(have) if px[0] // w >= BASIS[0] and px[1] // h >= BASIS[1]] or [0])
    i = max(0, min(len(have) - 1, i + {"kleiner": -1, "groesser": 1}.get(wahl, 0)))
    return os.path.join(FONTS, have[i][2] + ".psf.gz")


def aufloesung():
    try:
        with open(FB) as f:
            w, h = f.read().strip().split(",")
        return int(w), int(h)
    except (OSError, ValueError):
        return None


def zeichen(fd=0):
    """The characters of the console font (GIO_UNIMAP), None when it cannot be read."""
    import ctypes
    import fcntl

    class Paar(ctypes.Structure):
        _fields_ = [("u", ctypes.c_ushort), ("f", ctypes.c_ushort)]

    class Desc(ctypes.Structure):
        _fields_ = [("n", ctypes.c_ushort), ("e", ctypes.POINTER(Paar))]
    buf = (Paar * 4096)()
    desc = Desc(4096, ctypes.cast(buf, ctypes.POINTER(Paar)))
    try:
        fcntl.ioctl(fd, GIO_UNIMAP, desc)
    except OSError:
        return None
    return {chr(buf[i].u) for i in range(min(desc.n, 4096))}


def dunkel(an, fd=0):
    """The console's own blanking: dark and the monitor asleep (VESA powerdown), or back."""
    import fcntl
    try:
        if not an:
            fcntl.ioctl(fd, TIOCLINUX, bytes([10, 3]))
        fcntl.ioctl(fd, TIOCLINUX, bytes([4 if an else 14]))
        return True
    except OSError:
        return False


def holen(port, key, timeout=8):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}{PFAD}", headers={HEADER: key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(4_000_000)), 200
    except urllib.error.HTTPError as e:
        return None, e.code
    except (OSError, ValueError):
        return None, 0


def schluessel():
    try:
        with open(KEY) as f:
            return f.read().strip()
    except OSError:
        return ""


PAARE = {"w": (7, 0), "W": (7, 1), "g": (2, 1), "y": (3, 1), "r": (1, 1), "c": (6, 1), "m": (0, 1), "d": (0, 1),
         "p": (5, 1), "o": (1, 0), "b": (4, 1), "K": (0, 2)}
# the console's 16 colours: 0-7 are the dark surfaces (the only ones a cell's background can take, 1 the orange of
# the Internet), 8-15 the bright writing (bold). Only on the Linux console (ESC ] P), back with ESC ] R at the end.
TAFEL = ("0c1024", "ffa040", "143a22", "3a3214", "22224a", "3a1840", "123844", "c8cce0",
         "8890b0", "ff5f5f", "5cf08c", "ffd84f", "8c8cff", "ff6cff", "5ce0ff", "ffffff")


def farbtafel(an=True):
    """The escape that sets (or resets) the console palette."""
    return "".join(f"\033]P{i:x}{c}" for i, c in enumerate(TAFEL)) if an else "\033]R"


def paar(farben, col, bg):
    """The curses attribute for writing col on the surface bg, a colour pair made the first time it is needed."""
    import curses
    if (col, bg) not in farben:
        fg, art = PAARE[col]
        n = len(farben) + 1
        if bg and n < curses.COLOR_PAIRS and art != 2:
            curses.init_pair(n, fg, bg)
            farben[(col, bg)] = curses.color_pair(n) | (curses.A_BOLD if art == 1 else 0)
        else:                               # no pair left: the colour on the screen's own background
            farben[(col, bg)] = farben[(col, 0)]
    return farben[(col, bg)]


def zeigen(scr, R, have, versatz, farben):
    import curses
    dx, dy = versatz
    for y, row in enumerate(R.z):
        x, bgs = 0, R.bg[y]
        while x < len(row):
            col, bg = row[x][1], bgs[x]
            j = x
            while j < len(row) and row[j][1] == col and bgs[j] == bg:
                j += 1
            try:
                scr.addstr(y + dy, x + dx, ersetzen("".join(c for c, _ in row[x:j]), have), paar(farben, col, bg))
            except curses.error:
                pass
            x = j
    scr.noutrefresh()
    curses.doupdate()


def lauf(scr):
    import curses
    curses.curs_set(0)
    curses.start_color()
    farben = {}
    for i, (k, (fg, art)) in enumerate(PAARE.items(), 1):
        curses.init_pair(i, fg if art != 2 else 7, 0 if art != 2 else 6)    # 2: white on the cyan surface
        farben[(k, 0)] = curses.color_pair(i) | (curses.A_BOLD if art else 0)
    scr.nodelay(True)
    port = (load_config("panel") or {}).get("port", 31080)
    px, wahl0, font, have, an, code0 = None, None, None, None, True, None
    alt, fehl = None, 0
    while True:
        d, code = holen(port, schluessel())
        if d is not None:
            alt, fehl = d, 0
        else:
            fehl += 1
            if fehl < GEDULD and alt is not None:   # one slow answer (the day's numbers on a Pi): keep the last picture
                d, code = alt, code0
        if code != code0:
            print(f"schirm: panel {code or 'weg'}", file=sys.stderr, flush=True)
            code0 = code
        p, wahl = aufloesung(), (d or {}).get("schrift", "auto")
        if p != px or wahl != wahl0 or (font is None and p):     # a new screen or another font size in the settings
            px, wahl0 = p, wahl
            f = schrift(px, wahl)
            if f and f != font:
                import subprocess
                ok = subprocess.run(["setfont", f], stdin=0, capture_output=True, timeout=10).returncode == 0
                print(f"schirm: schrift {os.path.basename(f)} {'ok' if ok else 'fehler'}", file=sys.stderr, flush=True)
                font = f
            have = zeichen()
        groesse = os.get_terminal_size(0)
        if (groesse.lines, groesse.columns) != scr.getmaxyx():   # a new font or a new screen: the picture follows
            curses.resizeterm(groesse.lines, groesse.columns)
        soll = bool(d.get("an", True)) if d else True
        if soll != an:
            dunkel(soll)
            print(f"schirm: bildschirm {'an' if soll else 'aus'}", file=sys.stderr, flush=True)
            an = soll
        if an:
            hh, ww = scr.getmaxyx()
            dx, dy = (d or {}).get("versatz") or (0, 0)
            scr.erase()
            zeigen(scr, bild(d, ww - 1, hh - 2), have, (min(1, dx), min(2, dy)), farben)
        while scr.getch() != -1:
            pass
        time.sleep(1)


def main(argv):
    if argv[:1] == ["--probe"]:
        d = json.load(sys.stdin)
        w, h = (int(x) for x in (argv[1:3] if len(argv) >= 3 else BASIS))
        sys.stdout.write(bild(d, w, h, d.get("t")).text() + "\n")
        return 0
    if not os.isatty(0):
        print("schirm: kein bildschirm", file=sys.stderr, flush=True)
        return 2
    import curses
    import locale
    locale.setlocale(locale.LC_ALL, "")
    print("schirm: start", file=sys.stderr, flush=True)
    tafel = os.environ.get("TERM") == "linux"
    if tafel:
        sys.stdout.write(farbtafel())
        sys.stdout.flush()
    try:
        curses.wrapper(lauf)
    finally:
        if tafel:
            sys.stdout.write(farbtafel(False))
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
