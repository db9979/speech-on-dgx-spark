"""The values of one computer for Zustand → Überblick → Rechner (Dominik 2026-10-16, both computers when the panel
and the models run apart): CPU, memory, disk, network, temperature, fan, power flags, running time, device and system
name, and how much of the CPU each own service takes (dienste_cpu, Dominik 2026-10-18 "woran gerade gearbeitet wird").
Numbers and fixed words only, never a process, a path, an address or a file name.

The Wärter on the model computer sends messen() with its status (tarswart.status "rechner"); the panel computer
measures itself (panel/rechnerblick.py). The case driver reads temperature, fan and power flags from here too
(panel/gehaeuse.py), with its own reader for the self-tests.
"""
import os
import re
import socket
import time

THERMAL = "/sys/class/thermal"
THROTTLED = "/sys/devices/platform/soc/soc:firmware/get_throttled"   # the Raspberry Pi's firmware flags
MODELL = ("/proc/device-tree/model", "/sys/class/dmi/id/product_name")
OS_RELEASE = "/etc/os-release"
LUEFTER = ("gpio-fan", "pwm-fan")          # the Pironman's fan (gpio-fan overlay) and the Pi 5 active cooler
# interfaces that only mirror others (containers, bridges, tunnels): not counted for the network numbers
VIRTUELL = ("lo", "docker", "veth", "br-", "virbr", "tailscale", "wg", "tun", "tap")
_NAME = re.compile(r"[^A-Za-z0-9 .()+_-]")
_fest = {}
_cpu = {}              # the CPU times of the last measurement (its own, psutil.cpu_percent(None) is shared)
# every service's CPU time in systemd's counters (cgroup v2, always on): own units by their name, the units of
# dgx-spark-qwen38 and Docker's model containers each together; everything else counts as "rest" (computed by the panel)
CGROUP = "/sys/fs/cgroup/system.slice"
_EIGEN = re.compile(r"speech-spark-([a-z][a-z0-9-]{0,23})\.service")
DIENSTE_MAX = 24       # entries at most (more own units do not exist)
_dienst = {}           # the counters of the last measurement: {"t": monotonic, "u": {part: µs}}


def lesen(path):
    with open(path) as f:
        return f.read()


def _sauber(s, n=40):
    return _NAME.sub("", str(s or "").replace("\x00", "")).strip()[:n]


def temp(read=lesen):
    """The CPU temperature in °C (thermal zone 0), None when unknown."""
    try:
        return round(int(read(f"{THERMAL}/thermal_zone0/temp").strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def luefter(read=lesen):
    """Whether the fan turns: True, False, None without a known fan."""
    try:
        for d in sorted(os.listdir(THERMAL)):
            if d.startswith("cooling_device") and read(f"{THERMAL}/{d}/type").strip() in LUEFTER:
                return int(read(f"{THERMAL}/{d}/cur_state").strip()) > 0
    except (OSError, ValueError):
        pass
    return None


def strom_flags(read=lesen):
    """The Raspberry Pi's get_throttled flags as a number, None on other computers."""
    try:
        return int(read(THROTTLED).strip(), 16)
    except (OSError, ValueError):
        return None


def strom_worte(v):
    """The flags in words: (voltage, throttling) with "ok"/"zu niedrig"/"war niedrig" and "nein"/"jetzt"/"war an"."""
    if v is None:
        return "?", "?"
    jetzt = "zu niedrig" if v & 0x1 else "war niedrig" if v & 0x10000 else "ok"
    war = "jetzt" if v & 0x4 else "war an" if v & 0x40000 else "nein"
    return jetzt, war


def cpu_pct():
    """The CPU load in % since this module's last call (None on the first)."""
    import psutil
    t = psutil.cpu_times()
    alt, _cpu["t"] = _cpu.get("t"), t
    if alt is None:
        return None
    busy = lambda x: sum(x) - x.idle - getattr(x, "iowait", 0)   # noqa: E731
    total = sum(t) - sum(alt)
    return round(max(0.0, min(100.0, 100 * (busy(t) - busy(alt)) / total)), 1) if total > 0 else None


def _dienst_von(name):
    """The part a unit of system.slice counts for: own units by their name, qwen38 and Docker together, else None."""
    m = _EIGEN.fullmatch(name)
    if m:
        return m.group(1)
    if name.startswith("qwen38-") and name.endswith(".service"):
        return "qwen38"
    if name.startswith("docker-") and name.endswith(".scope"):   # only model engines run in Docker (modelle.DOCKER)
        return "docker"
    return None


def dienste_cpu(base=CGROUP, read=lesen, now=None, kerne=None):
    """The CPU share in % of the whole computer each service took since the last call ({} on the first, None without
    the counters): usage_usec from the service's cpu.stat. A service that started again in between counts 0."""
    now = time.monotonic() if now is None else now
    kerne = kerne or os.cpu_count() or 1
    try:
        namen = sorted(os.listdir(base))
    except OSError:
        return None
    u = {}
    for n in namen:
        teil = _dienst_von(n)
        if teil is None:
            continue
        try:
            for z in read(f"{base}/{n}/cpu.stat").splitlines():
                k, _, v = z.partition(" ")
                if k == "usage_usec":
                    u[teil] = u.get(teil, 0) + int(v)
                    break
        except (OSError, ValueError):
            continue
    alt = dict(_dienst)
    _dienst.update(t=now, u=u)
    dt = now - alt["t"] if alt else 0
    if dt <= 0:
        return {}
    out = {}
    for teil, v in u.items():
        d = v - alt["u"].get(teil, v)
        pct = round(min(100.0, 100 * d / (dt * 1e6 * kerne)), 1) if d > 0 else 0.0
        if pct >= 0.1:
            out[teil] = pct
    return dict(sorted(out.items(), key=lambda x: -x[1])[:DIENSTE_MAX])


def laeuft_s():
    import psutil
    return max(0, int(time.time() - psutil.boot_time()))


def fest():
    """What does not change while the computer runs: host name, device and system (kept after the first call)."""
    if not _fest:
        geraet = ""
        for p in MODELL:
            try:
                geraet = _sauber(lesen(p))
            except OSError:
                continue
            if geraet:
                break
        system = ""
        try:
            m = re.search(r'^PRETTY_NAME="?([^"\n]*)', lesen(OS_RELEASE), re.M)
            system = _sauber(m.group(1)) if m else ""
        except OSError:
            pass
        _fest.update(name=re.sub(r"[^A-Za-z0-9-]", "", socket.gethostname())[:24], geraet=geraet, system=system)
    return dict(_fest)


def _netz():
    """Bytes received and sent over the real interfaces since the start, and the fastest link in Mbit/s (0 unknown)."""
    import psutil
    rx = tx = 0
    for nic, c in psutil.net_io_counters(pernic=True).items():
        if not nic.startswith(VIRTUELL):
            rx, tx = rx + c.bytes_recv, tx + c.bytes_sent
    mbit = max([s.speed for nic, s in psutil.net_if_stats().items() if s.isup and not nic.startswith(VIRTUELL)] or [0])
    return rx, tx, max(0, int(mbit))


def messen(platte=None, read=lesen):
    """One measurement of this computer (each part None when it cannot be read)."""
    import psutil
    from common import STATE
    gib = 2 ** 30
    out = {"t": round(time.monotonic(), 1), **fest()}
    try:
        out.update(cpu=cpu_pct(), kerne=psutil.cpu_count() or 0, last=round(os.getloadavg()[0], 2))
    except (OSError, AttributeError):
        out.update(cpu=None, kerne=0, last=None)
    try:
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        out.update(ram_total=round(vm.total / gib, 2), ram_frei=round(vm.available / gib, 2),
                   ram_cache=round((getattr(vm, "cached", 0) + getattr(vm, "buffers", 0)) / gib, 2),
                   ram_pct=vm.percent, swap=round(sw.used / gib, 2))
    except OSError:
        out.update(ram_total=None, ram_frei=None, ram_cache=None, ram_pct=None, swap=None)
    try:
        path = platte or (STATE if os.path.isdir(STATE) else "/")
        du = psutil.disk_usage(path)
        out.update(platte_total=round(du.total / 1e9, 1), platte_frei=round(du.free / 1e9, 1), platte_pct=du.percent)
    except OSError:
        out.update(platte_total=None, platte_frei=None, platte_pct=None)
    try:
        out["netz_rx"], out["netz_tx"], out["netz_mbit"] = _netz()
    except (OSError, AttributeError):
        out.update(netz_rx=None, netz_tx=None, netz_mbit=0)
    try:
        out["laeuft_s"] = laeuft_s()
    except OSError:
        out["laeuft_s"] = None
    out.update(temp=temp(read), luefter=luefter(read), strom=strom_flags(read))
    try:
        out["dienste_cpu"] = dienste_cpu()
    except OSError:
        out["dienste_cpu"] = None
    return out
