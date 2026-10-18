"""Gehäuse (plan Raspberry-Pi split B7, Dominik 2026-10-15 "ok perfekt", own driver instead of SunFounder's software).

The case of a panel computer. The first one is the SunFounder Pironman 5 around a Raspberry Pi 5: an OLED (SSD1306,
128×64, I2C bus 1, address 0x3C or 0x3D), four RGB LEDs (WS2812 on SPI0) and two case fans on GPIO 6. Everything goes
through the Pi's device files, no extra package and no service of its own:

    OLED            pages of fixed words and numbers for the admin, never a name or a text of a profile (the display
                    is seen by everyone in the room): Spark, Dienste und Wartung, Pi, DGX weg oder in Pause, Netz, …,
                    Aktiv 10 min (one big number of people, aktiv.py)
    LEDs            the status as a colour: green ready, yellow Wartungspause or an open hint, red model computer gone
                    or a service down; brightness of its own, off at night
    case fans       the kernel switches them by the CPU temperature (overlay gpio-fan in config.txt, nothing runs for it);
                    the thresholds are the admin's, they count after the next restart

Admin switch Funktionen → Gehäuse (chat.gehaeuse, off), the settings under Einstellungen → System → Gehäuse. "Einrichten"
leaves a wish (WUNSCH) and starts the fixed root unit speech-spark-gehaeuse (speech-spark gehaeuse wunsch-intern), which
takes the wish through `gehaeuse.py wunsch-nehmen` (two whole numbers at most) and writes everything itself, never a
line from the panel: I2C and SPI on and the fan overlay between two marker lines of config.txt, the module i2c-dev, the
service user in the groups i2c, spi and gpio; "Entfernen" takes the block out again. A change there needs a restart of the Pi: root leaves NEUSTART in /run (gone after the restart), and only
then the panel's "Neu starten" restarts the Pi. Logs: "gehaeuse: …" with fixed words and numbers.
"""
import asyncio
import fcntl
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import core  # noqa: E402
import guard  # noqa: E402
import rechner  # noqa: E402
from common import STATE, load_config, read_json, write_json  # noqa: E402
from rechner import THROTTLED  # noqa: E402,F401  (the self-tests fake this file)
from core import admin_code, auth  # noqa: E402

ARTEN = {"keins": ("Keins", "None"), "pironman5": ("SunFounder Pironman 5", "SunFounder Pironman 5")}
I2C_DEV = "/dev/i2c-1"
SPI_DEV = "/dev/spidev0.0"
OLED_ADDRS = (0x3C, 0x3D)
I2C_SLAVE = 0x0703                 # linux/i2c-dev.h
SPI_IOC_WR_MODE = 0x40016B01       # linux/spi/spidev.h: _IOW('k', 1, __u8)
SPI_IOC_WR_MAX_SPEED_HZ = 0x40046B04   # _IOW('k', 4, __u32)
LED_N = 4
LED_HZ = 6_400_000                 # one WS2812 bit = one SPI byte of 1.25 µs
FAN_PIN = 6
W, H = 128, 64
CONFIG_TXT = os.environ.get("SPEECH_SPARK_CONFIG_TXT", "/boot/firmware/config.txt")
BEGIN, END = "# speech-spark gehaeuse begin", "# speech-spark gehaeuse end"
WUNSCH = os.path.join(STATE, "gehaeuse-wunsch.json")
NEUSTART = os.environ.get("SPEECH_SPARK_GEHAEUSE_NEUSTART", "/run/speech-spark-gehaeuse-neustart")
UNIT = "speech-spark-gehaeuse"
WUNSCH_S = 300                     # a wish older than this is not taken
LED_EVERY = 5                      # seconds between two LED colours
RETRY = 60                         # seconds before a device that failed is tried again
# Schutz vor Einbrennen (B7b): the picture moves by a pixel or two every VERSATZ_S seconds, and a picture that did not
# change for GLEICH_S seconds is shown at GLEICH_HELL % at most
VERSATZ = ((0, 0), (1, 1), (0, 2), (1, 0))
VERSATZ_S = 180
GLEICH_S = 600
GLEICH_HELL = 10

# the pages: key -> (German, English); the order is the order on the display unless the admin dragged another one
# (chat.gehaeuse_reihenfolge); 6 to 11 came with B7b (Dominik 2026-10-15 "ergänze diese noch")
SEITEN = (("spark", "Spark", "Spark"), ("dienste", "Dienste und Wartung", "Services and maintenance"),
          ("pi", "Pi", "Pi"), ("dgx", "DGX weg oder in Pause", "DGX gone or paused"), ("netz", "Netz", "Network"),
          ("dgxdetail", "DGX im Detail", "DGX in detail"), ("sicherheit", "Sicherheit", "Security"),
          ("geraete", "Geräte", "Devices"), ("haus", "Haus", "House"), ("strom", "Strom", "Power"),
          ("version", "Version", "Version"), ("aktiv", "Aktiv 10 min", "Active 10 min"),
          ("lastpi", "CPU und RAM Pi", "CPU and RAM Pi"), ("lasttars", "CPU und RAM TARS", "CPU and RAM TARS"))
# pages drawn with one big number instead of lines (bild): "Aktiv 10 min" (Dominik 2026-10-17 "1b 2a 3a")
GROSS = ("aktiv",)
# pages drawn with two big numbers, CPU left and RAM right in % (Dominik 2026-10-17 "1a, Namen Pi und TARS");
# "TARS" only while the models run on another computer
ZWEI = ("lastpi", "lasttars")
FARBEN = {"gruen": (0, 255, 0), "gelb": (255, 150, 0), "rot": (255, 0, 0), "aus": (0, 0, 0)}
NACHT = ("aus", "dunkel", "an")
ANZEIGE = ("immer", "probleme")   # "probleme": dark while everything is green
# the settings (chat.*): key -> (default, lowest, highest) for numbers; admin.validate checks them with these
ZAHLEN = {"gehaeuse_wechsel_s": (6, 3, 60), "gehaeuse_hell": (60, 1, 100), "gehaeuse_led_hell": (30, 0, 100),
          "gehaeuse_nacht_von": (22, 0, 23), "gehaeuse_nacht_bis": (7, 0, 23), "gehaeuse_luefter_an": (55, 40, 80),
          "gehaeuse_luefter_aus": (48, 30, 75)}

_lock = threading.Lock()
_st = {"oled": "aus", "led": "aus", "addr": None, "seite": "", "farbe": "aus", "next": 0.0, "i": 0, "led_t": 0.0,
       "fail": {}, "bild": None, "roh": b"", "gleich": 0.0}


# ---------------------------------------------------------------- the device files (tests put a fake here)
class Hw:
    def exists(self, path):
        return os.path.exists(path)

    def i2c_write(self, addr, data):
        fd = os.open(I2C_DEV, os.O_RDWR)
        try:
            fcntl.ioctl(fd, I2C_SLAVE, addr)
            os.write(fd, data)
        finally:
            os.close(fd)

    def spi_write(self, data):
        fd = os.open(SPI_DEV, os.O_WRONLY)
        try:
            fcntl.ioctl(fd, SPI_IOC_WR_MODE, bytes([0]))
            fcntl.ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, LED_HZ.to_bytes(4, "little"))
            os.write(fd, data)
        finally:
            os.close(fd)

    def read(self, path):
        with open(path) as f:
            return f.read()


hw = Hw()


def cfg_chat(c=None):
    import features
    return features.chat_cfg() if c is None else c


def admin_on(c=None):
    import features
    return features.admin_on("gehaeuse", c)


def zahl(c, key):
    d, lo, hi = ZAHLEN[key]
    v = c.get(key, d)
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else d


def check(c):
    """None when the case settings in chat are fine, else the reason (admin.validate)."""
    if c.get("gehaeuse_art", "keins") not in ARTEN:
        return "gehaeuse_art: keins oder pironman5"
    if c.get("gehaeuse_nacht", "aus") not in NACHT:
        return "gehaeuse_nacht: aus, dunkel oder an"
    if c.get("gehaeuse_anzeige", "immer") not in ANZEIGE:
        return "gehaeuse_anzeige: immer oder probleme"
    if c.get("gehaeuse_drehung", 0) not in (0, 180) or isinstance(c.get("gehaeuse_drehung", 0), bool):
        return "gehaeuse_drehung: 0 oder 180"
    for k, (d, lo, hi) in ZAHLEN.items():
        v = c.get(k, d)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return f"{k}: {lo} bis {hi}"
    if zahl(c, "gehaeuse_luefter_aus") >= zahl(c, "gehaeuse_luefter_an"):
        return "gehaeuse_luefter_aus: unter der Grenze zum Einschalten"
    aus = c.get("gehaeuse_seiten_aus", [])
    keys = [k for k, _, _ in SEITEN]
    if not isinstance(aus, list) or len(aus) >= len(keys) or len(set(aus)) != len(aus) or any(x not in keys for x in aus):
        return "gehaeuse_seiten_aus: Seiten des Displays, mindestens eine bleibt an"
    folge = c.get("gehaeuse_reihenfolge", [])
    if not isinstance(folge, list) or len(set(folge)) != len(folge) or any(x not in keys for x in folge):
        return "gehaeuse_reihenfolge: Seiten des Displays, jede höchstens einmal"
    return None


def reihenfolge(c):
    """All pages in the admin's order (chat.gehaeuse_reihenfolge first, the rest in their own order)."""
    keys = [k for k, _, _ in SEITEN]
    folge = [k for k in (c.get("gehaeuse_reihenfolge") or []) if k in keys] if isinstance(c.get("gehaeuse_reihenfolge"), list) else []
    return list(dict.fromkeys(folge)) + [k for k in keys if k not in folge]


# ---------------------------------------------------------------- OLED (SSD1306)
OLED_INIT = (0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12,
             0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6)


def _cmd(addr, *cmds):
    hw.i2c_write(addr, bytes((0x00,) + cmds))     # control byte 0x00: a stream of commands


def finden():
    """The OLED's address (i2cdetect's quick write: a NOP the display acknowledges), None without one."""
    if not hw.exists(I2C_DEV):
        return None
    for a in OLED_ADDRS:
        try:
            _cmd(a, 0xE3)
            return a
        except OSError:
            continue
    return None


def oled_start(addr):
    _cmd(addr, *OLED_INIT)
    _cmd(addr, 0xAF)


def oled_aus(addr):
    _cmd(addr, 0xAE)


def oled_hell(addr, pct):
    _cmd(addr, 0x81, max(1, min(255, round(pct * 255 / 100))))


def packen(img):
    """A 128×64 picture as the display's 8 pages of 128 bytes (bit 0 is the top row of a page)."""
    px = img.convert("1").load()
    out = bytearray(W * H // 8)
    for page in range(H // 8):
        for x in range(W):
            b = 0
            for bit in range(8):
                if px[x, page * 8 + bit]:
                    b |= 1 << bit
            out[page * W + x] = b
    return bytes(out)


def oled_zeigen(addr, img):
    data = packen(img)
    _cmd(addr, 0x21, 0, W - 1, 0x22, 0, H // 8 - 1)
    for i in range(0, len(data), 32):
        hw.i2c_write(addr, b"\x40" + data[i:i + 32])   # control byte 0x40: display data


# ---------------------------------------------------------------- LEDs (WS2812 over SPI)
def led_bytes(rgb, n=LED_N):
    """n LEDs in one colour as SPI bytes: each bit one byte (0b11110000 for 1, 0b11000000 for 0), GRB order, the
    reset pause before and after."""
    r, g, b = rgb
    bits = bytearray()
    for byte in (g, r, b):
        for i in range(7, -1, -1):
            bits.append(0b11110000 if byte >> i & 1 else 0b11000000)
    return bytes(8) + bytes(bits) * n + bytes(240)


def led_farbe(farbe, pct):
    r, g, b = FARBEN[farbe]
    return tuple(round(x * pct / 100) for x in (r, g, b))


# ---------------------------------------------------------------- what the pages and LEDs show (fixed words, numbers)
def _num(v, d=0):
    return "?" if v is None else (f"{v:.{d}f}".replace(".", ",") if d else str(int(round(v))))


def lage(now=None):
    """The status for the LEDs and the page order: (farbe, Wort)."""
    import steuer
    try:
        if steuer.remote() and steuer.weg(now):
            return "rot", "DGX weg"
    except Exception:
        pass
    start = _llm_start()       # before the pause: a switch pauses the language model while it runs
    if start:
        return "gelb", start
    try:
        if steuer.remote() and ((steuer.cached() or {}).get("pause") or {}).get("on"):
            return "gelb", "DGX in Pause"
    except Exception:
        pass
    down, hints = _hinweise()
    if down:
        return "rot", "Dienst weg"
    if hints:
        return "gelb", "Hinweis offen"
    return "gruen", "bereit"


def _llm_start():
    """While the language model switches or starts: "LLM wechselt (4/6)" (modellseite.for_live, step numbers only)."""
    try:
        import llmstart
        import modellseite
        st = modellseite.for_live().get("start")
        return "LLM " + llmstart.kurz(st) if st else ""
    except Exception:
        return ""


def _hinweise():
    """(services down, other open hints) from the Dienst-Wächter and the admin banner."""
    down = hints = 0
    try:
        import dienstwacht
        if dienstwacht.admin_on():
            down = sum(1 for e in dienstwacht._read()["svc"].values() if e.get("st") == "down")
    except Exception:
        pass
    try:
        import health
        hints = sum(1 for a in health.alerts() if a.get("kind") != "service")
    except Exception:
        pass
    return down, hints


def _pi():
    import psutil
    out = {"temp": rechner.temp(hw.read), "cpu": None, "ram": None, "platte": None, "luefter": rechner.luefter(hw.read)}
    try:
        out["cpu"] = psutil.cpu_percent(None)
        out["ram"] = psutil.virtual_memory().percent
        out["platte"] = psutil.disk_usage("/").percent
    except Exception:
        pass
    return out


def _ip():
    """This computer's address in the home network (a UDP socket towards the model computer sends nothing)."""
    try:
        from common import model_host
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((model_host() if model_host() not in ("127.0.0.1", "localhost") else "192.0.2.1", 9))
            return s.getsockname()[0]
    except (OSError, ValueError):
        return "?"


def _offen(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def zeilen(key, now=None):
    """The lines of one page: a title and up to four lines of fixed words and numbers."""
    import steuer
    now = time.time() if now is None else now
    d = (steuer.cached() or {}) if steuer.remote() else {}
    if key == "spark":
        units = d.get("einheiten") or {}

        def dot(part):
            st = (units.get(f"speech-spark-{part}") or {}).get("state")
            return {"active": "an", None: "-"}.get(st, "aus")
        farbe, wort = lage(now)
        return ["Spark " + time.strftime("%H:%M", time.localtime(now)),
                f"LLM {dot('llm')}  Bild {dot('bild')}", f"Hoeren {dot('asr')}  Sprechen {dot('tts')}", wort]
    if key == "dienste":
        down, hints = _hinweise()
        out = ["Dienste", f"Weg {down}  Hinweise {hints}"]
        try:
            import update
            behind = (update._remote_cache.get("data") or {}).get("behind")
            out.append("Update bereit" if behind else "Update: aktuell" if behind == 0 else "Update: ?")
        except Exception:
            out.append("Update: ?")
        try:
            import backup
            last = (backup.listing() or [{}])[0].get("created")
            out.append(f"Sicherung vor {_num((now - last) / 3600)} h" if last else "Sicherung: keine")
        except Exception:
            out.append("Sicherung: ?")
        return out
    if key == "pi":
        p = _pi()
        return ["Pi " + _ip(), f"CPU {_num(p['temp'])} C  {_num(p['cpu'])} %", f"RAM {_num(p['ram'])} %  SSD {_num(p['platte'])} %",
                "Luefter " + {True: "an", False: "aus", None: "?"}[p["luefter"]]]
    if key == "dgx":
        pause = d.get("pause") or {}
        if steuer.remote() and steuer.weg(now):
            return ["DGX weg", "Notbetrieb", "feste Saetze"]
        if pause.get("on"):
            rest = (pause.get("until") or 0) - now
            return ["DGX in Pause", f"noch {_num(max(0, rest) / 60)} min" if pause.get("until") else "ohne Ende"]
        return ["DGX", "bereit" if steuer.remote() else "auf diesem Rechner"]
    if key == "netz":
        lines = ["Netz", "DGX " + ("weg" if steuer.remote() and steuer.weg(now) else "erreichbar" if d else "-")]
        lines.append("HTTPS 31443 " + ("offen" if _offen(31443) else "zu"))
        lines.append("TURN 3478 " + ("offen" if _offen(3478) else "zu"))
        return lines
    if key == "dgxdetail":
        if not steuer.remote():
            from common import mem_available_gib
            return ["DGX Detail", "auf diesem Rechner", f"Frei {_num(_safe(mem_available_gib))} GiB", "LLM " + _kurz(_llm_lokal())]
        gpu = d.get("gpu") or {}
        llm = ((d.get("modellwahl") or {}).get("llm") or {})
        return ["DGX Detail", f"GPU {_num(gpu.get('temp'))} C", f"Frei {_num(d.get('mem_avail_gib'))} GiB",
                "LLM " + (_kurz(llm.get("modell")) if llm.get("enabled", True) else "aus")]
    if key == "sicherheit":
        n = _zaehler()
        try:
            import notaus
            stufe = str(notaus.level())
        except Exception:
            stufe = "?"
        return ["Sicherheit", f"Anmeldung falsch {n.get('door_out', '-')}", f"Waechter geblockt {n.get('guard_bad', '-')}",
                f"Notaus Stufe {stufe}"]
    if key == "geraete":
        return ["Geraete", f"Lautsprecher {_geraete('esp32')}", f"Apps {_geraete('apps')}", "Verbund " + _dienst("verbund")]
    if key == "haus":
        return ["Haus", f"HA {_dienst('ha')}  NAS {_dienst('naszustand')}", f"Kiwix {_dienst('kiwix')}",
                f"Suche {_dienst('web')}"]
    if key == "strom":
        jetzt, war = _strom()
        return ["Strom", "Spannung " + jetzt, "Drossel " + war, "Pi an " + _dauer(_safe(rechner.laeuft_s))]
    if key == "aktiv":    # aktiv.py: who had a request in the last 10 minutes, numbers only
        import aktiv
        n = aktiv.zahlen(now)
        return ["Aktiv 10 min", str(n["gesamt"]), f"Profile {n['profile']}", f"Gaeste {n['gaeste']}"]
    if key in ZWEI:       # CPU and RAM in %: the Pi measured here, TARS from its last status (rechnerblick.py)
        if key == "lastpi":
            p = _pi()
            return ["Pi", _num(p["cpu"]), _num(p["ram"])]
        if steuer.remote() and steuer.weg(now):
            return ["TARS weg", "-", "-"]
        import rechnerblick
        t = rechnerblick.last("modell")
        return ["TARS", _num(t["cpu"]), _num(t["ram"])]
    if key == "version":
        try:
            import core as _core
            mine = _core.app_version() or "?"
        except Exception:
            mine = "?"
        other = str(d.get("version") or "")[:20] if steuer.remote() else mine
        return ["Version", "Pi " + mine, "DGX " + (other or "-"),
                "gleich" if other == mine else "abweichend" if other else "DGX unbekannt"]
    return []


def _safe(f):
    try:
        return f()
    except Exception:
        return None


def _kurz(name):
    """A model's short name for the display (the last part of its id, 17 characters)."""
    return str(name or "-").rsplit("/", 1)[-1][:17]


def _llm_lokal():
    return (load_config().get("llm") or {}).get("modell")


def _zaehler():
    """Today's counts of Live (live.counts_today): wrong logins and refused devices, connections the Wächter blocked.
    Live counts only while it is on; otherwise empty (the page shows "-")."""
    try:
        import live
        return live.counts_today() if live.on() else {}
    except Exception:
        return {}


def _geraete(was):
    try:
        if was == "esp32":
            import esp32
            return len(getattr(esp32, "_live", {}) or {})
        import android
        import terminal
        return int(terminal.online(time.time())) + int(android.live_count())
    except Exception:
        return "?"


def _dienst(sid):
    """A service of the Dienst-Wächter in one word: ok, weg or - (not watched, not set up, not known yet)."""
    try:
        import dienstwacht
        if not dienstwacht.admin_on():
            return "-"
        e = dienstwacht._read()["svc"].get(sid)
        if not e:
            return "-"
        st = dienstwacht._state(e)
        return "ok" if st in ("ok", "wobble") else "weg" if st in ("down", "inet") else "-"
    except Exception:
        return "?"


def _strom():
    """The Pi's firmware flags (get_throttled): under-voltage now or since the start, throttled now or since the start."""
    return rechner.strom_worte(rechner.strom_flags(hw.read))


def _dauer(s):
    if s is None:
        return "?"
    s = int(s)
    return f"{s // 86400} d {s % 86400 // 3600} h" if s >= 86400 else f"{s // 3600} h {s % 3600 // 60} min"


def seiten(c, now=None):
    """The pages to show, in their order: an open problem brings its page first; "DGX" only while it is gone or paused."""
    aus = set(c.get("gehaeuse_seiten_aus") or [])
    keys = [k for k in reihenfolge(c) if k not in aus]
    farbe, wort = lage(now)
    try:
        import steuer
        dgx = steuer.remote() and (steuer.weg(now) or bool(((steuer.cached() or {}).get("pause") or {}).get("on")))
    except Exception:
        dgx = False
    if not dgx and "dgx" in keys:
        keys.remove("dgx")
    elif dgx and "dgx" in keys:
        keys.remove("dgx")
        keys.insert(0, "dgx")
    try:
        import steuer
        geteilt = steuer.remote()
    except Exception:
        geteilt = False
    if not geteilt and "lasttars" in keys:
        keys.remove("lasttars")
    if farbe != "gruen" and "dienste" in keys and not dgx:
        keys.remove("dienste")
        keys.insert(0, "dienste")
    if wort.startswith("LLM ") and "spark" in keys:   # the language model switches or starts: its step comes first
        keys.remove("spark")
        keys.insert(0, "spark")
    return keys or ["spark"]


def bild(lines, drehen=False, versatz=(0, 0), key=""):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("1", (W, H), 0)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    dx, dy = versatz
    if key in ZWEI and len(lines) >= 3:
        _zwei(draw, font, lines, dx, dy)
        return img.rotate(180) if drehen else img
    if key in GROSS and len(lines) >= 2:
        _gross(draw, font, lines, dx, dy)
        return img.rotate(180) if drehen else img
    for i, line in enumerate(lines[:5]):
        draw.text((dx, dy + i * 12), line[:21], fill=1, font=font)
        if i == 0:
            draw.line((0, dy + 11, W - 1, dy + 11), fill=1)
    return img.rotate(180) if drehen else img


def _gross(draw, font, lines, dx, dy):
    """A page with one big number (GROSS): the title on top, the number left (as large as fits 70 points), up to two
    small lines right of a divider. Pillow's own scalable font, no font file."""
    from PIL import ImageFont
    draw.text((dx, dy), lines[0][:21], fill=1, font=font)
    draw.line((0, dy + 11, W - 1, dy + 11), fill=1)
    zahl_ = lines[1][:4]
    for size in (46, 36, 28, 22):
        big = ImageFont.load_default(size=size)
        x0, y0, x1, y1 = draw.textbbox((0, 0), zahl_, font=big, stroke_width=1)
        if x1 - x0 <= 66:
            break
    draw.text((dx + (70 - (x1 - x0)) // 2 - x0, dy + 15 + (46 - (y1 - y0)) // 2 - y0), zahl_, fill=1, font=big,
              stroke_width=1, stroke_fill=1)
    draw.line((dx + 72, dy + 16, dx + 72, dy + 60), fill=1)
    for i, line in enumerate(lines[2:4]):     # "Profile 3": the word small, its number below it a bit larger
        wort, _, n = line.rpartition(" ")
        draw.text((dx + 77, dy + 13 + i * 25), (wort or n)[:8], fill=1, font=font)
        if wort:
            draw.text((dx + 77, dy + 21 + i * 25), n[:5], fill=1, font=ImageFont.load_default(size=13))


def _zwei(draw, font, lines, dx, dy):
    """A page with two big numbers (ZWEI): the title on top, CPU left and RAM right of a divider, "CPU %" and "RAM %"
    under them; each number as large as fits its half."""
    from PIL import ImageFont
    draw.text((dx, dy), lines[0][:21], fill=1, font=font)
    draw.line((0, dy + 11, W - 1, dy + 11), fill=1)
    draw.line((dx + 63, dy + 14, dx + 63, dy + 62), fill=1)
    for i, (wert, wort) in enumerate(((lines[1], "CPU %"), (lines[2], "RAM %"))):
        x0 = dx + i * 66
        wert = wert[:3]
        for size in (34, 28, 22):
            big = ImageFont.load_default(size=size)
            a, b, c, d = draw.textbbox((0, 0), wert, font=big, stroke_width=1)
            if c - a <= 58:
                break
        draw.text((x0 + (62 - (c - a)) // 2 - a, dy + 15 + (34 - (d - b)) // 2 - b), wert, fill=1, font=big,
                  stroke_width=1, stroke_fill=1)
        w = draw.textlength(wort, font=font)
        draw.text((x0 + (62 - w) // 2, dy + 52), wort, fill=1, font=font)


def versatz(now):
    """Schutz vor Einbrennen: where the picture sits now (a pixel or two, changing every VERSATZ_S seconds)."""
    return VERSATZ[int(now // VERSATZ_S) % len(VERSATZ)]


def bits(img):
    """A picture for the panel's preview: 128×64 points row by row, 16 bytes a row, the leftmost point in the top bit."""
    import base64
    return base64.b64encode(img.convert("1").tobytes()).decode()


def vorschau(c=None, now=None):
    """Funktionen → Gehäuse (B7b): every page as the display would draw it now (upright, without the move against
    burn-in), whether it is on, and the picture the display shows right now. Numbers and fixed words only."""
    c = cfg_chat(c)
    now = time.time() if now is None else now
    aus = set(c.get("gehaeuse_seiten_aus") or [])
    names = {k: (de, en) for k, de, en in SEITEN}
    out = []
    for k in reihenfolge(c):
        try:
            b = bits(bild(zeilen(k, now), key=k))
        except Exception as e:
            print("gehaeuse: vorschau fehler", type(e).__name__, flush=True)
            b = ""
        out.append({"id": k, "name": list(names[k]), "an": k not in aus, "bits": b})
    jetzt = _st["seite"] if _st["oled"] == "an" and _st["seite"] not in ("", "-") else ""
    return {"seiten": out, "jetzt": jetzt, "jetzt_bits": bits(_st["bild"]) if jetzt and _st["bild"] is not None else "",
            "oled": _st["oled"], "dunkel": _st["seite"] == "-", "w": W, "h": H}


def im_fenster(von, bis, now=None):
    """Whether the hour now lies from von to bis o'clock (over midnight when von > bis); also the screen's times (schirm.py)."""
    h = time.localtime(time.time() if now is None else now).tm_hour
    return (von <= h or h < bis) if von > bis else (von <= h < bis)


def nacht(c, now=None):
    return im_fenster(zahl(c, "gehaeuse_nacht_von"), zahl(c, "gehaeuse_nacht_bis"), now)


# ---------------------------------------------------------------- the loop (in the panel, every second)
def _fehler(teil, e, now):
    f = _st["fail"].get(teil)
    if not f:
        print(f"gehaeuse: {teil} fehler {type(e).__name__}", flush=True)
    _st["fail"][teil] = now
    _st[teil] = "fehler"


def _wieder(teil):
    if _st["fail"].pop(teil, None):
        print(f"gehaeuse: {teil} wieder da", flush=True)


def tick(now=None, c=None):
    """One step: the next page when its time came, the LED colour every LED_EVERY seconds. Off (and dark) when the
    switch or the case is off."""
    now = time.time() if now is None else now
    c = cfg_chat(c)
    with _lock:
        if not admin_on(c) or c.get("gehaeuse_art", "keins") == "keins":
            if _st["oled"] == "an" and _st["addr"]:
                try:
                    oled_aus(_st["addr"])
                except OSError:
                    pass
            if _st["led"] == "an":
                try:
                    hw.spi_write(led_bytes(FARBEN["aus"]))
                except OSError:
                    pass
            _st.update(oled="aus", led="aus", seite="", farbe="aus")
            return
        farbe, _ = lage(now)
        dark = nacht(c, now) and c.get("gehaeuse_nacht", "aus") != "an"
        night_off = dark and c.get("gehaeuse_nacht", "aus") == "aus"
        _oled(c, now, farbe, dark, night_off)
        if now - _st["led_t"] >= LED_EVERY:
            _st["led_t"] = now
            _led(c, now, farbe, dark, night_off)


def _oled(c, now, farbe, dark, night_off):
    if _st["fail"].get("oled") and now - _st["fail"]["oled"] < RETRY:
        return
    try:
        if _st["addr"] is None or _st["oled"] in ("aus", "fehler", "fehlt"):
            a = finden()
            if a is None:
                if _st["oled"] != "fehlt":
                    print("gehaeuse: oled fehlt", flush=True)
                _st.update(oled="fehlt", addr=None)
                _st["fail"]["oled"] = now
                return
            oled_start(a)
            _st.update(addr=a, oled="an", next=0.0)
            _wieder("oled")
            print(f"gehaeuse: oled an 0x{a:02x}", flush=True)
        a = _st["addr"]
        quiet = night_off or (c.get("gehaeuse_anzeige") == "probleme" and farbe == "gruen")
        if quiet:
            if _st["seite"] != "-":
                oled_aus(a)
                _st["seite"] = "-"
            return
        if now < _st["next"] and _st["seite"] not in ("", "-"):
            return
        if _st["seite"] == "-":
            _cmd(a, 0xAF)
        keys = seiten(c, now)
        i = _st["i"] % len(keys)
        key = keys[i]
        lines = zeilen(key, now)
        img = bild(lines, c.get("gehaeuse_drehung") == 180, versatz(now), key)
        roh = "\n".join(lines).encode()
        if roh != _st["roh"]:
            _st.update(roh=roh, gleich=now)
        hell = 5 if dark else zahl(c, "gehaeuse_hell")
        if now - _st["gleich"] >= GLEICH_S:
            hell = min(hell, GLEICH_HELL)     # the same picture for 10 minutes: darker against burn-in
        oled_hell(a, hell)
        oled_zeigen(a, img)
        _st.update(seite=key, i=i + 1, next=now + zahl(c, "gehaeuse_wechsel_s"), bild=bild(lines, key=key))
    except OSError as e:
        _fehler("oled", e, now)


def _led(c, now, farbe, dark, night_off):
    if _st["fail"].get("led") and now - _st["fail"]["led"] < RETRY:
        return
    if not hw.exists(SPI_DEV):
        if _st["led"] != "fehlt":
            print("gehaeuse: led fehlt", flush=True)
        _st["led"] = "fehlt"
        return
    pct = 0 if night_off else 5 if dark else zahl(c, "gehaeuse_led_hell")
    try:
        hw.spi_write(led_bytes(led_farbe(farbe, pct)))
        if _st["led"] != "an":
            print("gehaeuse: led an", flush=True)
        _wieder("led")
        _st.update(led="an", farbe=farbe if pct else "aus")
    except OSError as e:
        _fehler("led", e, now)


async def loop():
    import asyncio
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception as e:
            print("gehaeuse: loop", type(e).__name__, flush=True)
        await asyncio.sleep(1)


def for_live(c=None):
    """Zustand → Live, box „Gehäuse“: state words and numbers only, never a page's content."""
    c = cfg_chat(c)
    if not admin_on(c) or c.get("gehaeuse_art", "keins") == "keins":
        return {"on": False}
    p = _pi()
    return {"on": True, "oled": _st["oled"], "led": _st["led"], "temp": _num(p["temp"]),
            "luefter": {True: "an", False: "aus", None: "?"}[p["luefter"]], "neustart": hw.exists(NEUSTART)}


def probes():
    """For the Dienst-Wächter: the display, while the switch is on, a case is chosen and the Pi is set up for it (I2C
    there; before the restart nothing is expected of it)."""
    c = cfg_chat()
    if not admin_on(c) or c.get("gehaeuse_art", "keins") == "keins" or not hw.exists(I2C_DEV):
        return {}
    return {"gehaeuse": {"oled": True}}


def oled_ok():
    return _st["oled"] == "an"


# ---------------------------------------------------------------- set up and take out (root unit)
def zustand():
    """What the settings page shows (no secret, no content)."""
    txt = ""
    try:
        txt = hw.read(CONFIG_TXT)
    except OSError:
        pass
    return {"pi": bool(txt), "eingerichtet": BEGIN in txt, "neustart": hw.exists(NEUSTART),
            "i2c": hw.exists(I2C_DEV), "spi": hw.exists(SPI_DEV), "oled": _st["oled"], "led": _st["led"],
            "addr": f"0x{_st['addr']:02x}" if _st["addr"] else "", "seite": _st["seite"], "farbe": _st["farbe"],
            "wunsch": bool(read_json(WUNSCH, None))}


def wunsch(was, now=None):
    """The panel's wish for the root unit: ein, aus or neustart."""
    if was not in ("ein", "aus", "neustart"):
        raise ValueError(was)
    write_json(WUNSCH, {"was": was, "t": round(time.time() if now is None else now, 1)})


def wunsch_nehmen(now=None):
    """For the root unit (as the service user): the wish, checked again, then gone. A line "ein AN AUS", "aus" or
    "neustart"; None when there is none or it is not right."""
    now = time.time() if now is None else now
    d = read_json(WUNSCH, None)
    try:
        os.remove(WUNSCH)
    except OSError:
        pass
    if not isinstance(d, dict) or d.get("was") not in ("ein", "aus", "neustart") \
            or not isinstance(d.get("t"), (int, float)) or not 0 <= now - d["t"] <= WUNSCH_S:
        return None
    c = load_config().get("chat", {})
    if d["was"] == "ein":
        if not admin_on(c) or c.get("gehaeuse_art") != "pironman5" or check(c):
            return None
        return f"ein {zahl(c, 'gehaeuse_luefter_an')} {zahl(c, 'gehaeuse_luefter_aus')}"
    return d["was"]


# ---------------------------------------------------------------- routes (Einstellungen → System → Gehäuse, admin only)
router = APIRouter()
MAX_BODY = 256


def _starten():
    """The fixed root unit (sudoers allows exactly this command); False when it did not start."""
    import subprocess
    try:
        return subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", UNIT], timeout=20,
                              capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def seite(lang="de"):
    i = 1 if lang == "en" else 0
    return dict(zustand(), an=admin_on(), arten=[{"id": k, "name": v[i]} for k, v in ARTEN.items()],
                seiten=[{"id": k, "name": (de, en)[i]} for k, de, en in SEITEN])


@router.get("/api/admin/gehaeuse", dependencies=[Depends(auth)])
def admin_gehaeuse(request: Request, lang: str = "de"):
    guard.limit(request, "gehaeuse", None, True)
    return seite("en" if lang == "en" else "de")


@router.get("/api/admin/gehaeuse/vorschau", dependencies=[Depends(auth)])
def admin_vorschau(request: Request):
    guard.limit(request, "gehaeuse", None, True)
    return vorschau()


async def _wunsch_starten(request, was):
    guard.limit(request, "gehaeuse_wunsch", None, True)
    await core.json_body(request, MAX_BODY, lenient=True)
    c = cfg_chat()
    if not admin_on(c):
        print(f"gehaeuse: {was} abgelehnt aus", flush=True)
        raise HTTPException(409, "Das Gehäuse ist aus (Funktionen → Gehäuse).")
    if was == "ein" and c.get("gehaeuse_art") != "pironman5":
        print("gehaeuse: ein abgelehnt art", flush=True)
        raise HTTPException(409, "Erst ein Gehäuse auswählen und speichern.")
    if was == "neustart" and not zustand()["neustart"]:
        print("gehaeuse: neustart abgelehnt nicht noetig", flush=True)
        raise HTTPException(409, "Ein Neustart ist gerade nicht nötig.")
    wunsch(was)
    if not await asyncio.to_thread(_starten):   # sudo and systemctl: off the loop (Hänge-Wächter)
        print(f"gehaeuse: {was} start fehler", flush=True)
        raise HTTPException(503, "Ließ sich nicht starten. Auf dem Pi: sudo speech-spark update, dann noch einmal.")
    print(f"gehaeuse: {was} angefragt", flush=True)
    guard.log("gehaeuse", detail={"ein": "Einrichten", "aus": "Entfernen", "neustart": "Neustart"}[was])
    return seite("en" if request.query_params.get("lang") == "en" else "de")


@router.post("/api/admin/gehaeuse/einrichten", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_einrichten(request: Request):
    return await _wunsch_starten(request, "ein")


@router.post("/api/admin/gehaeuse/entfernen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_entfernen(request: Request):
    return await _wunsch_starten(request, "aus")


@router.post("/api/admin/gehaeuse/neustart", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_neustart(request: Request):
    return await _wunsch_starten(request, "neustart")


def main(argv):
    if argv == ["wunsch-nehmen"]:
        w = wunsch_nehmen()
        sys.stdout.write((w or "-") + "\n")
        return 0 if w else 1
    print("gehaeuse.py wunsch-nehmen", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
