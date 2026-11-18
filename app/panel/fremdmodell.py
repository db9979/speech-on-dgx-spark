"""Fremde Modell-Dienste (plan katalogpaket-und-zwei-modellrechner.md E6, Dominik 2026-11-17 „c“): a language model
that another program in the home network serves through the OpenAI interface (Ollama or LM Studio on a Mac), used
in addition to the own one („Für alle“) or only while the model computer is gone („Ersatz“).

Fixed rules, the panel decides (Richtlinie Teil 2):
- at most MAX services, each with a name, an address http(s)://<IP in the home network>:<port>/v1 (an IP, never a
  name: no name can point elsewhere later; fremdseite and llm.py check it with netguard at every use, which also
  refuses the Spark's own services, netguard.own_service), optionally a key, and the model names the service listed
  itself;
- usable only after the panel's own check (fremdseite.pruefen: the model in /v1/models, a German sentence, a tool
  call) on exactly this address and model: "geprueft" holds their signature, so a change of either needs the check
  again;
- several checked models per service (lanes, at most LANES_MAX; Alzeo serves one model at a time and switches between
  them, Dominik 2026-11-18 „1a“): when the service no longer lists the model in use, the panel takes the first checked
  one it lists now (folgen, from fremdseite's look every minute) and goes back by the same rule; a service that does
  not answer or lists no checked model is left out (ziel) until it does again;
- „Für alle“ (wahl): the panel asks it instead of the own model; „Ersatz“ (ersatz): only while the model computer is
  gone (steuer.weg); the own model's checks (quality test, Probetag), System One and the helper model stay own.

Everything lives in STATE/fremd-modelle.json (0600, never in the configuration, never on a page, never in a log: the
key stays here). Only the standard library and common: llm.py reads it on every call, so it stays below the knot.
"""
import hashlib
import ipaddress
import os
import re
import threading
from urllib.parse import urlsplit

from common import STATE, read_json, write_json

DATEI = os.path.join(STATE, "fremd-modelle.json")
MAX = 3
ID = re.compile(r"^f[1-9]$")
NAME_MAX = 30
MODELL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")     # Ollama "qwen3:30b-a3b", LM Studio "org/model"
KEY = re.compile(r"^[\x21-\x7e]{1,200}$")
LANES_MAX = 8          # checked models per service (Alzeo has about ten text lanes; one runs at a time)
_lock = threading.Lock()
STATUS = {}   # id -> {"ok", "wort", "ms", "tok_s", "t"}: the last look (fremdseite), in memory, never a key or a text


class Fehler(ValueError):
    """A fixed word the page turns into a sentence (fremdseite.GRUND)."""


def basis(url):
    """The service's address as http(s)://<ip>:<port>/v1; an IP in the home network and a port, nothing else."""
    try:
        u = urlsplit(str(url or "").strip())
        port = u.port
        ip = ipaddress.ip_address(u.hostname or "")
    except ValueError:
        raise Fehler("adresse")
    if u.scheme not in ("http", "https") or not port or u.username or u.password or u.query or u.fragment:
        raise Fehler("adresse")
    if u.path.rstrip("/") not in ("", "/v1"):
        raise Fehler("adresse")
    if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        raise Fehler("heimnetz")
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    return f"{u.scheme}://{host}:{port}/v1"


def ziel_ip(d):
    """(ip, port) of a service, for netguard.allowed at every use."""
    u = urlsplit(d["url"])
    return u.hostname, u.port


def sig(d):
    """What the check vouches for: exactly this address and this model."""
    return hashlib.sha256(f"{d.get('url', '')}|{d.get('modell', '')}".encode()).hexdigest()[:16]


def _lanes_gut(v):
    return v is None or (isinstance(v, dict) and len(v) <= LANES_MAX
                         and all(MODELL.match(str(k)) and isinstance(s, str) for k, s in v.items()))


def _gut(d):
    try:
        return (isinstance(d, dict) and ID.match(str(d.get("id", ""))) and 1 <= len(str(d.get("name", ""))) <= NAME_MAX
                and basis(d.get("url")) == d.get("url") and (not d.get("modell") or MODELL.match(str(d["modell"])))
                and (not d.get("key") or KEY.match(str(d["key"]))) and _lanes_gut(d.get("lanes")))
    except Fehler:
        return False


def lanes(x):
    """The checked models of a service in the order they were checked: each signature must fit its address."""
    out = [m for m, s in (x.get("lanes") or {}).items() if s == sig({"url": x.get("url", ""), "modell": m})]
    if nutzbar(x) and x["modell"] not in out:
        out.insert(0, x["modell"])   # a service checked before V01.1.524 has only "modell"
    return out


def stand(path=None):
    """{"dienste": [...], "wahl": id or "", "ersatz": id or ""}; a broken entry is left out."""
    d = read_json(path or DATEI, {})
    d = d if isinstance(d, dict) else {}
    dienste = [x for x in (d.get("dienste") or [])[:MAX] if _gut(x)]
    ids = {x["id"] for x in dienste}
    return {"dienste": dienste, "wahl": d.get("wahl") if d.get("wahl") in ids else "",
            "ersatz": d.get("ersatz") if d.get("ersatz") in ids else ""}


def _schreiben(d, path=None):
    write_json(path or DATEI, d, indent=1)
    try:
        os.chmod(path or DATEI, 0o600)
    except OSError:
        pass


def finde(d, fid):
    return next((x for x in d["dienste"] if x["id"] == fid), None)


def nutzbar(x):
    return bool(x and x.get("modell") and x.get("geprueft") == sig(x))


def ziel(an, weg, path=None, status=None):
    """The service the panel asks now instead of the own language model, None for the own one. an: the admin switch
    (features.admin_on "fremdmodelle"); weg: the model computer is gone (steuer.weg). „Für alle“ first, then „Ersatz“
    while the model computer is gone; a service whose last look failed (STATUS ok False: no answer, no checked model
    listed) is skipped until a look finds it again."""
    if not an:
        return None
    status = STATUS if status is None else status
    d = stand(path)
    for fid in (d["wahl"], d["ersatz"] if weg else ""):
        x = finde(d, fid) if fid else None
        if nutzbar(x) and (status.get(x["id"]) or {}).get("ok") is not False:
            return x
    return None


def name_ok(name):
    name = str(name or "").strip()
    if not 1 <= len(name) <= NAME_MAX or any(c in name for c in "<>\"'`") or any(ord(c) < 32 for c in name):
        raise Fehler("name")
    return name


def speichern(fid, name, url, key=None, path=None):
    """A new service (fid "") or a changed one; key None keeps the stored one, "" deletes it. Returns its id."""
    name, url = name_ok(name), basis(url)
    if key not in (None, "") and not KEY.match(str(key)):
        raise Fehler("key")
    with _lock:
        d = stand(path)
        if fid:
            x = finde(d, fid)
            if x is None:
                raise Fehler("unbekannt")
        else:
            if len(d["dienste"]) >= MAX:
                raise Fehler("voll")
            fid = next(f"f{i}" for i in range(1, 10) if not finde(d, f"f{i}"))
            x = {"id": fid}
            d["dienste"].append(x)
        if any(y.get("url") == url and y["id"] != fid for y in d["dienste"]):
            raise Fehler("doppelt")
        if x.get("url") != url:
            for k in ("modell", "geprueft", "lanes"):
                x.pop(k, None)
        x.update(name=name, url=url)
        if key is not None:
            x.pop("key", None)
            if key:
                x["key"] = str(key)
        _schreiben(d, path)
    return fid


def geprueft(fid, modell, path=None):
    """After the check passed: this model on this address is usable."""
    if not MODELL.match(str(modell or "")):
        raise Fehler("modell")
    with _lock:
        d = stand(path)
        x = finde(d, fid)
        if x is None:
            raise Fehler("unbekannt")
        lz = {m: sig({"url": x["url"], "modell": m}) for m in lanes(x) if m != modell}
        x["modell"] = modell
        x["geprueft"] = sig(x)
        if len(lz) >= LANES_MAX:
            lz.pop(next(iter(lz)))   # the oldest check goes
        lz[modell] = x["geprueft"]
        x["lanes"] = lz
        _schreiben(d, path)


def folgen(fid, namen, path=None):
    """The service now lists namen (its /v1/models): when the model in use is not among them, take the first checked
    model that is (fixed rule, never the model's own say). Returns the model taken, or None (nothing to change, or no
    checked model listed: then the service waits, ziel skips it)."""
    with _lock:
        d = stand(path)
        x = finde(d, fid)
        if x is None or not x.get("modell") or x["modell"] in namen:
            return None
        neu = next((m for m in lanes(x) if m in namen), None)
        if neu is None:
            return None
        x["modell"] = neu
        x["geprueft"] = sig(x)
        _schreiben(d, path)
    return neu


def nutzung(wahl, ersatz, path=None):
    """„Für alle“ and „Ersatz“: an id of a checked service or ""."""
    with _lock:
        d = stand(path)
        for v in (wahl, ersatz):
            if v and not nutzbar(finde(d, v)):
                raise Fehler("ungeprueft")
        d.update(wahl=wahl or "", ersatz=ersatz or "")
        _schreiben(d, path)


def loeschen(fid, path=None):
    with _lock:
        d = stand(path)
        if finde(d, fid) is None:
            raise Fehler("unbekannt")
        d["dienste"] = [x for x in d["dienste"] if x["id"] != fid]
        d.update(wahl="" if d["wahl"] == fid else d["wahl"], ersatz="" if d["ersatz"] == fid else d["ersatz"])
        _schreiben(d, path)


def fuer_live(an, path=None):
    """Zustand → Live: how many services, checked, in use, reachable; numbers only."""
    d = stand(path)
    return {"on": bool(an) and bool(d["dienste"]), "dienste": len(d["dienste"]),
            "geprueft": sum(nutzbar(x) for x in d["dienste"]), "fuer_alle": bool(d["wahl"]), "ersatz": bool(d["ersatz"]),
            "erreichbar": sum(1 for x in d["dienste"] if (STATUS.get(x["id"]) or {}).get("ok"))}


def live_sub(z, weg=False):
    """The line under the node: numbers and fixed words."""
    return (f"{z['dienste']} Dienste · {z['geprueft']} geprüft · {z['erreichbar']} erreichbar"
            + (" · für alle" if z["fuer_alle"] else "") + (" · Ersatz bereit" if z["ersatz"] and not weg else "")
            + (" · Ersatz antwortet statt des Modell-Rechners" if z["ersatz"] and weg else ""))


def zeigen(d, status=None):
    """For the page: never the key, only whether one is set."""
    status = STATUS if status is None else status
    return [{"id": x["id"], "name": x["name"], "url": x["url"], "https": x["url"].startswith("https:"),
             "schluessel": bool(x.get("key")), "modell": x.get("modell", ""), "geprueft": nutzbar(x),
             "lanes": lanes(x), "status": status.get(x["id"])} for x in d["dienste"]]
