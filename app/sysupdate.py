"""System-Updates, the part on each computer (Dominik 2026-11-04 „1a 2a 3a 4a“, plan system-updates).

The operating system of both computers (the Pi with the panel, tars with the models) is brought up to date only in a
fixed way, and only on the admin's word. This file is the one place that knows how; it runs in three places:

- as the panel's service user inside the root unit speech-spark-systemupdate (`as_panel_user ../sysupdate.py …` in
  speech-spark.sh): it takes the panel's wish (wunsch_nehmen: one word of WUENSCHE, checked again, then gone), turns
  root's raw apt output into this computer's state file (stand), names the packages root holds back before the run
  (halten) and follows the run line by line (fortschritt, ende). Root itself only runs fixed commands and never parses
  a line: what reaches the state file is a package name and a version in a fixed character set, never other text.
- in the panel (panel/systemupdates.py reads lesen() for this computer and writes wunsch()),
- in the Wärter on tars (tarswart.py, commands `systemupdate` and `systemupdate_tun <wort>`), when the models run
  on another computer.

What is installed, and from where (the rule the root unit follows, docs: Funktionen → System-Updates):
- `apt-get upgrade --with-new-pkgs --no-remove`: only the sources the system already has, never a new one; packages
  only upgraded, a new one only as a dependency of an upgrade (a new kernel of the same series); nothing is ever
  removed (apt stops instead). Not full-upgrade, which may remove packages to solve a conflict: that stays a step by
  hand (Funktionen → Anleitungen → Firmware von Hand).
- Only origins of the system's own family (ERLAUBT: Debian and Raspberry Pi on the Pi, Ubuntu and NVIDIA DGX on tars).
  A package from any other source (Docker, a PPA …) is held back during the run and shown as „fremde Quelle“.
- Firmware and drivers never (VON_HAND: the Pi's EEPROM, NVIDIA driver, CUDA and the kernel the driver is built for
  on tars): held back, shown under „Firmware und Treiber“ with the guide for doing it by hand.
- non-interactive, old configuration files kept (--force-confold), needrestart quiet (it would restart speech).
- never a restart: root writes the marker NEUSTART_MARKE when one is needed; only the admin's „Jetzt neu starten“ (fresh
  code) or „Heute Nacht“ writes the wish neustart, and root restarts only when the marker or /var/run/reboot-required
  is there.

    STATE/system-updates-wunsch.json  {"was": WUENSCHE, "rolle": "panel"|"modelle", "t"}: the panel's (or the Wärter's) wish
    STATE/system-updates-stand.json   {"pruefung": {...}, "lauf": {...}}: this computer's check and run (lesen)
"""
import os
import re
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, load_config, read_json, write_json  # noqa: E402

WUNSCH = os.path.join(STATE, "system-updates-wunsch.json")
STAND = os.path.join(STATE, "system-updates-stand.json")
WUENSCHE = ("pruefen", "einspielen", "neustart")
ROLLEN = ("panel", "modelle")
UNIT = "speech-spark-systemupdate"
WUNSCH_S = 600                  # a wish older than this is not taken
MAX_PAKETE = 300                # packages kept per computer (the count stays exact)
MAX_IDS = 5                     # OSV ids per package
NAME = re.compile(r"[a-z0-9][a-z0-9+.\-]{0,63}")
VER = re.compile(r"[A-Za-z0-9.+~:\-]{1,64}")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{0,31}")
OS_NAME = re.compile(r"[A-Za-z0-9 .,()/_+\-]{1,60}")
# one line of `apt-get -s upgrade`: Inst NAME [OLD] (NEW ORIGIN:VERSION/SUITE[, …] [ARCH])
INST = re.compile(r"^Inst (\S+) (?:\[([^\]]*)\] )?\((\S+) (.*)\)\s*$")
SECTION = re.compile(r"^@@sysup ([a-z\-]{1,20})$")
# the origins a computer of this family takes, by the start of apt's origin label (lower case) -> shown name
HERKUNFT = (("debian", "Debian"), ("raspbian", "Raspberry Pi"), ("raspberry pi", "Raspberry Pi"),
            ("ubuntu", "Ubuntu"), ("nvidia", "NVIDIA DGX"), ("dgx", "NVIDIA DGX"))
ERLAUBT = {"debian": ("Debian", "Raspberry Pi"), "ubuntu": ("Ubuntu", "NVIDIA DGX")}
# firmware and drivers: never in the run, only by hand (the Pi's EEPROM; on tars driver, CUDA and the kernel the
# driver is built for)
VON_HAND = {"debian": re.compile(r"rpi-eeprom"),
            "ubuntu": re.compile(r"(nvidia|libnvidia|cuda|libcuda|linux-(image|headers|modules|nvidia|signatures)|dgx|nv-)")}
TREIBER_PAKET = re.compile(r"(nvidia-driver|libnvidia-compute)-\d+")
UPSTREAM = re.compile(r"(?:\d+:)?(\d+(?:\.\d+){1,3})")
DGX_VERSION = re.compile(r'^DGX_(?:OTA|SWBUILD|OS)_?VERSION="?(\d+(?:\.\d+){1,3})"?\s*$', re.M)
EEPROM = re.compile(r"^\s*(CURRENT|LATEST):.*\((\d{9,11})\)\s*$", re.M)
FERTIG = re.compile(r"^Setting up (\S+?)(?::\S+)? \(")


def familie(text=None):
    """"debian" (Debian, Raspberry Pi OS) or "ubuntu" (Ubuntu, DGX OS) from /etc/os-release; "" for anything else."""
    if text is None:
        try:
            with open("/etc/os-release") as f:
                text = f.read(8192)
        except OSError:
            return ""
    kv = dict(re.findall(r'^([A-Z_]+)="?([^"\n]*)"?$', text, re.M))
    ids = (kv.get("ID", "") + " " + kv.get("ID_LIKE", "")).lower().split()
    if "ubuntu" in ids:
        return "ubuntu"
    if "debian" in ids or "raspbian" in ids:
        return "debian"
    return ""


def os_name(text=None):
    if text is None:
        try:
            with open("/etc/os-release") as f:
                text = f.read(8192)
        except OSError:
            return ""
    m = re.search(r'^PRETTY_NAME="?([^"\n]*)"?$', text, re.M)
    v = m.group(1).strip() if m else ""
    return v if OS_NAME.fullmatch(v or "-") else ""


def herkunft(label):
    """The shown name of an apt origin label ("Debian-Security:12/stable-security" -> "Debian"), "" when unknown."""
    low = str(label).strip().lower()
    return next((name for start, name in HERKUNFT if low.startswith(start)), "")


def paket_ok(name, ver):
    return bool(NAME.fullmatch(name or "")) and bool(VER.fullmatch(ver or ""))


def plan(text, fam):
    """The packages `apt-get -s upgrade` would install, each {"n", "alt", "neu", "s" (security), "q" (origin name),
    "hand" (firmware/driver), "fremd" (another source)}; a line with another character set is dropped, not cut."""
    out, seen = [], set()
    hand = VON_HAND.get(fam)
    erlaubt = ERLAUBT.get(fam, ())
    for line in str(text).splitlines():
        m = INST.match(line)
        if not m:
            continue
        n, alt, neu, rest = m.group(1), m.group(2) or "", m.group(3), m.group(4)
        n = n.split(":", 1)[0]   # name:arch
        if not paket_ok(n, neu) or (alt and not VER.fullmatch(alt)) or n in seen:
            continue
        seen.add(n)
        teile = [x.strip() for x in re.sub(r"\s*\[[^\]]*\]\s*$", "", rest).split(",") if x.strip()]
        quellen = [herkunft(x) for x in teile]
        q = next((x for x in quellen if x in erlaubt), "")
        out.append({"n": n, "alt": alt, "neu": neu, "s": any("security" in x.lower() for x in teile),
                    "q": q or next((x for x in quellen if x), ""), "hand": bool(hand and hand.match(n)),
                    "fremd": not q})
    return out


def quellen(policy, fam):
    """The origin names the system's sources carry (apt-cache policy: `release … o=Debian,…`), those of the family
    first; {"eigen": [...], "fremd": n}."""
    eigen, fremd = [], set()
    for o in re.findall(r"\bo=([^,\n]{1,60})", str(policy)):
        name = herkunft(o)
        if name and name in ERLAUBT.get(fam, ()):
            if name not in eigen:
                eigen.append(name)
        else:
            fremd.add(o.strip().lower()[:60])
    return {"eigen": eigen, "fremd": len(fremd)}


def abschnitte(text):
    """Root's raw output in sections (@@sysup <name> lines) -> {name: text}."""
    out, name, buf = {}, None, []
    for line in str(text).splitlines():
        m = SECTION.match(line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    return out


def _datum(epoch):
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(epoch)))
    except (ValueError, OverflowError, OSError):
        return ""


def eeprom(text):
    """rpi-eeprom-update: {"jetzt", "neu"} as dates, "" when unknown or not a Pi."""
    d = dict((k, _datum(v)) for k, v in EEPROM.findall(str(text or "")))
    jetzt, neu = d.get("CURRENT", ""), d.get("LATEST", "")
    return {"jetzt": jetzt, "neu": neu if neu and neu > jetzt else ""}


def _upstream(v):
    m = UPSTREAM.match(str(v or ""))
    return m.group(1) if m else ""


def treiber(smi, pakete):
    """The NVIDIA driver now (nvidia-smi) and the one the sources offer (held back, by hand)."""
    jetzt = str(smi or "").strip().splitlines()[0].strip() if str(smi or "").strip() else ""
    jetzt = jetzt if re.fullmatch(r"\d{2,4}(\.\d{1,4}){1,2}", jetzt) else ""
    neu = next((_upstream(p["neu"]) for p in pakete if TREIBER_PAKET.match(p["n"])), "")
    return {"jetzt": jetzt, "neu": neu if neu and neu != jetzt else ""}


def dgx(release, pakete):
    m = DGX_VERSION.search(str(release or ""))
    jetzt = m.group(1) if m else ""
    neu = next((_upstream(p["neu"]) for p in pakete if p["n"] in ("dgx-release", "dgx-os-release")), "")
    return {"jetzt": jetzt, "neu": neu if neu and neu != jetzt else ""}


def _uptime():
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def _host():
    h = socket.gethostname().split(".")[0]
    return h if HOST.fullmatch(h) else ""


def pruefung(roh, now=None, fam=None, osrel=None):
    """This computer's check from root's raw output (abschnitte): numbers, names and versions only."""
    now = time.time() if now is None else now
    a = abschnitte(roh)
    fam = familie(osrel) if fam is None else fam
    alle = plan(a.get("apt", ""), fam)
    ein = [p for p in alle if not p["hand"] and not p["fremd"]]
    out = {"t": int(now), "familie": fam, "os": os_name(osrel), "host": _host(), "seit": _uptime(),
           "update": "ok" if a.get("apt-update", "").strip() == "ok" else "fehler",
           "anzahl": len(ein), "sicherheit": sum(1 for p in ein if p["s"]),
           "hand": sum(1 for p in alle if p["hand"]), "fremd": sum(1 for p in alle if p["fremd"] and not p["hand"]),
           "pakete": sorted(alle, key=lambda p: (not p["s"], p["hand"] or p["fremd"], p["n"]))[:MAX_PAKETE],
           "quellen": quellen(a.get("policy", ""), fam), "neustart": a.get("neustart", "").strip() == "ja",
           "eeprom": eeprom(a.get("eeprom", "")) if fam == "debian" else {"jetzt": "", "neu": ""},
           "treiber": treiber(a.get("nvidia", ""), alle) if fam == "ubuntu" else {"jetzt": "", "neu": ""},
           "dgx": dgx(a.get("dgx", ""), alle) if fam == "ubuntu" else {"jetzt": "", "neu": ""}}
    if not fam:
        out["update"] = "fehler"
    return out


# ---------------------------------------------------------------- the state file of this computer
def lesen():
    """This computer's state as the panel and the Wärter show it."""
    return sauber(read_json(STAND, {}))


def fremd(d):
    """The other computer's state as its Wärter sent it (lesen() there), checked again here: data, never orders."""
    d = d if isinstance(d, dict) else {}
    return dict(sauber({"pruefung": d, "lauf": d.get("lauf")}), unit=d.get("unit") is True, opencode=d.get("opencode") is True)


def sauber(d):
    """{"pruefung", "lauf"} with every value checked again (fixed character sets, numbers, known words)."""
    d = d if isinstance(d, dict) else {}
    p = d.get("pruefung") if isinstance(d.get("pruefung"), dict) else {}
    lauf = d.get("lauf") if isinstance(d.get("lauf"), dict) else {}
    pakete = [x for x in p.get("pakete") or [] if isinstance(x, dict) and paket_ok(x.get("n"), x.get("neu"))
              and (not x.get("alt") or VER.fullmatch(str(x["alt"])))][:MAX_PAKETE]

    def zahl(v):
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 10 ** 10 else 0

    def ver2(x):
        x = x if isinstance(x, dict) else {}
        return {k: str(x.get(k) or "") if VER.fullmatch(str(x.get(k) or "-")) else "" for k in ("jetzt", "neu")}
    q = p.get("quellen") if isinstance(p.get("quellen"), dict) else {}
    return {"t": zahl(p.get("t")), "familie": p.get("familie") if p.get("familie") in ERLAUBT else "",
            "os": p.get("os") if OS_NAME.fullmatch(str(p.get("os") or "-")) else "",
            "host": p.get("host") if HOST.fullmatch(str(p.get("host") or "-")) else "",
            "seit": zahl(p.get("seit")) or None, "update": "ok" if p.get("update") == "ok" else ("fehler" if p else ""),
            "anzahl": zahl(p.get("anzahl")), "sicherheit": zahl(p.get("sicherheit")), "hand": zahl(p.get("hand")),
            "fremd": zahl(p.get("fremd")), "neustart": p.get("neustart") is True,
            "pakete": [{"n": x["n"], "alt": str(x.get("alt") or ""), "neu": x["neu"], "s": x.get("s") is True,
                        "q": x.get("q") if x.get("q") in dict(HERKUNFT).values() else "", "hand": x.get("hand") is True,
                        "fremd": x.get("fremd") is True} for x in pakete],
            "quellen": {"eigen": [x for x in q.get("eigen") or [] if x in dict(HERKUNFT).values()][:4], "fremd": zahl(q.get("fremd"))},
            "eeprom": ver2(p.get("eeprom")), "treiber": ver2(p.get("treiber")), "dgx": ver2(p.get("dgx")),
            "lauf": {"laeuft": lauf.get("laeuft") is True, "n": zahl(lauf.get("n")), "m": zahl(lauf.get("m")),
                     "jetzt": lauf.get("jetzt") if NAME.fullmatch(str(lauf.get("jetzt") or "-")) else "",
                     "seit": zahl(lauf.get("seit")), "ende": zahl(lauf.get("ende")),
                     "ok": lauf.get("ok") if lauf.get("ok") in (True, False) else None,
                     "fertig": [x for x in lauf.get("fertig") or [] if NAME.fullmatch(str(x))][-MAX_PAKETE:]}}


def _aendern(fn):
    d = read_json(STAND, {})
    fn(d)
    write_json(STAND, d, mode=0o644)


def stand(roh, now=None):
    p = pruefung(roh, now)
    _aendern(lambda d: d.update(pruefung=p))
    print(f"systemupdate: geprueft {p['anzahl']} updates {p['sicherheit']} sicherheit {p['hand']} von hand "
          f"{p['fremd']} fremd {'neustart' if p['neustart'] else ''}".rstrip(), flush=True)
    return p


def halten():
    """The upgradable packages root holds back during the run: firmware and drivers, and other sources."""
    return [x["n"] for x in lesen()["pakete"] if x["hand"] or x["fremd"]]


def fortschritt(zeilen, now=None):
    """Follows apt's output (stdin of the root unit): n of m packages set up, the one being set up now. Only names
    from the plan count, everything else of the output is dropped."""
    s = lesen()
    plan_n = {x["n"] for x in s["pakete"] if not x["hand"] and not x["fremd"]}
    lauf = {"laeuft": True, "n": 0, "m": len(plan_n), "jetzt": "", "seit": int(time.time() if now is None else now),
            "ende": 0, "ok": None, "fertig": []}
    _aendern(lambda d: d.update(lauf=dict(lauf)))
    fertig = []
    for line in zeilen:
        m = FERTIG.match(line)
        name = m.group(1) if m else ""
        if not m or name not in plan_n or name in fertig:
            continue
        fertig.append(name)
        lauf.update(n=len(fertig), jetzt=name, fertig=fertig[-MAX_PAKETE:])
        _aendern(lambda d: d.update(lauf=dict(lauf)))
    print(f"systemupdate: eingespielt {len(fertig)} von {len(plan_n)}", flush=True)
    return len(fertig)


def ende(rc, now=None):
    ok = str(rc) == "0"

    def fn(d):
        lauf = d.get("lauf") if isinstance(d.get("lauf"), dict) else {}
        lauf.update(laeuft=False, ok=ok, ende=int(time.time() if now is None else now), jetzt="")
        d["lauf"] = lauf
    _aendern(fn)
    print(f"systemupdate: einspielen {'ok' if ok else 'fehler'}", flush=True)


# ---------------------------------------------------------------- the wish
def wunsch(was, rolle, now=None):
    """The wish for this computer's root unit (the panel here, or the Wärter for the panel on the other computer)."""
    if was not in WUENSCHE or rolle not in ROLLEN:
        raise ValueError("wunsch")
    write_json(WUNSCH, {"was": was, "rolle": rolle, "t": round(time.time() if now is None else now, 1)})   # rounded: up to 0.05 s ahead (wunsch_nehmen allows 2 s)


def wunsch_nehmen(now=None, cfg=None):
    """For the root unit (as the service user): the wish, checked again, then gone. One word of WUENSCHE, or None.
    On the panel's computer the switch must still be on; the model computer only takes a wish its Wärter wrote after
    the panel's signed command."""
    now = time.time() if now is None else now
    d = read_json(WUNSCH, None)
    try:
        os.remove(WUNSCH)
    except OSError:
        pass
    if not isinstance(d, dict) or d.get("was") not in WUENSCHE or d.get("rolle") not in ROLLEN \
            or not isinstance(d.get("t"), (int, float)) or not -2 <= now - d["t"] <= WUNSCH_S:
        return None
    if d["rolle"] == "panel":
        c = (load_config() if cfg is None else cfg).get("chat", {})
        if c.get("system_updates") is not True:
            return None
    return d["was"]


def main(argv):
    if argv == ["wunsch-nehmen"]:
        w = wunsch_nehmen()
        sys.stdout.write((w or "-") + "\n")
        if not w:
            print("systemupdate: abgelehnt wunsch", flush=True)
        return 0 if w else 1
    if argv == ["stand"]:
        stand(sys.stdin.read(4_000_000))
        return 0
    if argv == ["halten"]:
        sys.stdout.write("".join(n + "\n" for n in halten()))
        return 0
    if argv == ["fortschritt"]:
        fortschritt(sys.stdin)
        return 0
    if len(argv) == 2 and argv[0] == "ende" and re.fullmatch(r"\d{1,3}", argv[1]):
        ende(argv[1])
        return 0
    print("sysupdate.py wunsch-nehmen|stand|halten|fortschritt|ende RC", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
