"""Spark-Clients (plan spark-entkoppeln E1, Dominik 2026-11-14 „2a“): other programs use the Spark's services with
a key of their own, with rights, limits and a priority class, only in the home network.

Until now every service (speech recognition, speech output, the LLM-Tor, pictures, music) knew one key, api.key, that
the panel computer got at the pairing. That key stays: it is the built-in client „Assistent“ with every right and the
stages the panel signs (common._stage). Next to it the admin may make clients for other assistants, Open WebUI, Home
Assistant or own scripts, and only while the admin switch api.clients is on (Einstellungen → Spark → Clients,
`speech-spark clients an`); off, nothing but api.key opens a service, exactly as before.

Fixed rules (the Spark decides, never the client):
- a key is made here (KEY_PREFIX + 256 random bits), shown once and kept only as its SHA-256 (STATE/spark-clients.json),
  compared in constant time; a blocked client (gesperrt) or a removed one is refused at once
- rights per service (RECHTE): a request needs the right of its service; "sehen", "helfer" and "systemone" are rights
  of their own inside the LLM-Tor. Managing the Spark (Wärter) is never a right of a key: only the paired panel
  computer, signed with the Wärter key
- the priority class (KLASSEN) decides the stage of every request of the client at the services' gates (PrioGate):
  "sprache" goes first like the panel's speech, "dialog" is normal, "hintergrund" is always last. A client never
  picks its stage with headers (only the panel signs a stage, common._stage)
- limits per client: requests per minute per service (minute), at once at the LLM-Tor (parallel), tokens per day at
  the LLM-Tor (tokens_tag, counted from the engine's usage; the day is the local calendar day). Counts live in each
  service's memory and start new with the service
- the door (tlstor.py, nftables of teilen.py) lets other clients in only from the networks in api.clients_from and only
  while api.clients is on; the panel computer (api.tls_from) as before
- nothing of a request is kept: the journal ("sparkclient: …") holds the client's id, fixed words and numbers

    clients()                      the list without hashes (for the panel, the Wärter and `speech-spark clients`)
    neu(name, rechte, klasse, …)   a new client; returns (entry, key) and the key only this once
    aendern(cid, felder)           rights, class, limits, gesperrt
    weg(cid)                       removes a client
    faehigkeiten(client, cfg)      GET /v1/spark/faehigkeiten (E2): what this Spark offers and what the key may
    finden(authorization, cfg)     the client of a "Bearer …" header, None for no client or api.clients off
    darf(client, recht)            whether the client holds the right
    stufe(client)                  its stage (common.STAGE_*)
    minute_ok(client, dienst, now) one request more within its limit per minute (per service)
    tokens_ok / tokens_zaehlen     the LLM-Tor's tokens per day
"""
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading
import time

from common import CONFIG_PATH, LLM_ALIAS as LLM_NAME, MODEL_ARTS, SPARK_API, SPEECH_MARK, STATE, STAGE_HIGH, STAGE_LOW, STAGE_NORMAL, load_config, model_side, read_json, run, write_json

PATH = os.path.join(STATE, "spark-clients.json")
KEY_PREFIX = "sk-spark-"
MAX_CLIENTS = 20
RECHTE = ("llm", "sehen", "helfer", "systemone", "asr", "tts", "bild", "musik")
KLASSEN = {"sprache": STAGE_HIGH, "dialog": STAGE_NORMAL, "hintergrund": STAGE_LOW}
VORGABE = {"rechte": ["llm"], "klasse": "dialog", "minute": 20, "parallel": 2, "tokens_tag": 300000}
GRENZEN = {"minute": (1, 600), "parallel": (1, 8), "tokens_tag": (1000, 50000000)}
MAX_NETZE = 8
NAME_RE = re.compile(r"[A-Za-zÄÖÜäöüß0-9 ._()-]{1,40}")
ID_RE = re.compile(r"c_[0-9a-f]{10}")
FW_UNIT = "speech-spark-clients-fw"   # root's fixed unit: `speech-spark teilen firewall` reads the config itself
LOG_GAP = 60           # seconds between two journal lines of the same refusal of one client
_lock = threading.Lock()
_cache = {"mtime": None, "d": None}
_minute = {}           # (client id, service) -> [times of the last minute]
_tage = {}             # client id -> (day, tokens)
_offen = {}            # client id -> requests running at the LLM-Tor
_gemeldet = {}         # (client id, why) -> last journal line


class Fehler(ValueError):
    """A wrong value for a client (the word is the reason: name, recht, klasse, wert, voll, unbekannt)."""


def _lesen():
    try:
        mt = os.stat(PATH).st_mtime_ns
    except OSError:
        return {"clients": []}
    if _cache["mtime"] != mt:
        d = read_json(PATH, {"clients": []})
        _cache.update(mtime=mt, d=d if isinstance(d.get("clients"), list) else {"clients": []})
    return _cache["d"]


def _schreiben(d):
    write_json(PATH, d, mode=0o600)
    _cache.update(mtime=None, d=None)


def _sha(key):
    return hashlib.sha256(key.encode()).hexdigest()


def _ohne_hash(c):
    return {k: v for k, v in c.items() if k != "sha"}


def clients():
    return [_ohne_hash(c) for c in _lesen()["clients"] if isinstance(c, dict)]


def _name(name):
    name = str(name or "").strip()
    if not NAME_RE.fullmatch(name):
        raise Fehler("name")
    return name


def _rechte(rechte):
    if not isinstance(rechte, (list, tuple)) or not rechte or any(r not in RECHTE for r in rechte):
        raise Fehler("recht")
    return [r for r in RECHTE if r in rechte]


def _zahl(feld, v):
    lo, hi = GRENZEN[feld]
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise Fehler("wert")
    return v


def _felder(f, alt):
    out = dict(alt)
    if "name" in f:
        out["name"] = _name(f["name"])
    if "rechte" in f:
        out["rechte"] = _rechte(f["rechte"])
    if "klasse" in f:
        if f["klasse"] not in KLASSEN:
            raise Fehler("klasse")
        out["klasse"] = f["klasse"]
    for k in GRENZEN:
        if k in f:
            out[k] = _zahl(k, f[k])
    if "gesperrt" in f:
        if not isinstance(f["gesperrt"], bool):
            raise Fehler("wert")
        out["gesperrt"] = f["gesperrt"]
    return out


def neu(name, rechte=None, klasse=None, now=None, **grenzen):
    """A new client: (entry without hash, key). The key exists only in this answer."""
    f = {"name": name, "rechte": VORGABE["rechte"] if rechte is None else rechte,
         "klasse": VORGABE["klasse"] if klasse is None else klasse}
    f.update({k: grenzen.get(k, VORGABE[k]) for k in GRENZEN})
    with _lock:
        d = _lesen()
        liste = [c for c in d["clients"] if isinstance(c, dict)]
        if len(liste) >= MAX_CLIENTS:
            raise Fehler("voll")
        eintrag = _felder(f, {"gesperrt": False})
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        eintrag.update(id="c_" + secrets.token_hex(5), sha=_sha(key), seit=int(now or time.time()))
        _schreiben({"clients": liste + [eintrag]})
    print(f"sparkclient: neu {eintrag['id']} rechte {len(eintrag['rechte'])}", flush=True)
    return _ohne_hash(eintrag), key


def aendern(cid, felder):
    if not isinstance(felder, dict) or set(felder) - {"name", "rechte", "klasse", "gesperrt", *GRENZEN}:
        raise Fehler("wert")
    with _lock:
        d = _lesen()
        liste = [c for c in d["clients"] if isinstance(c, dict)]
        for i, c in enumerate(liste):
            if c.get("id") == cid:
                liste[i] = _felder(felder, c)
                _schreiben({"clients": liste})
                print(f"sparkclient: geaendert {cid}" + (" gesperrt" if liste[i].get("gesperrt") else ""), flush=True)
                return _ohne_hash(liste[i])
    print("sparkclient: abgelehnt unbekannt", flush=True)
    raise Fehler("unbekannt")


def weg(cid):
    with _lock:
        d = _lesen()
        liste = [c for c in d["clients"] if isinstance(c, dict)]
        rest = [c for c in liste if c.get("id") != cid]
        if len(rest) == len(liste):
            print("sparkclient: abgelehnt unbekannt", flush=True)
            raise Fehler("unbekannt")
        _schreiben({"clients": rest})
    for tab in (_minute, _gemeldet):
        for k in [k for k in tab if k[0] == cid]:
            tab.pop(k, None)
    _tage.pop(cid, None)
    print(f"sparkclient: geloescht {cid}", flush=True)
    return True


def an(cfg=None):
    """The admin switch api.clients: only then does a client key open anything."""
    cfg = load_config() if cfg is None else cfg
    return (cfg.get("api") or {}).get("clients") is True


def netz_pruefen(n):
    """A network of the home network (private, not loopback, not everything), as text; Fehler("netz") otherwise."""
    try:
        net = ipaddress.ip_network(str(n), strict=False)
    except ValueError:
        raise Fehler("netz")
    if not net.is_private or net.is_loopback or net.prefixlen < (8 if net.version == 4 else 48):
        raise Fehler("netz")
    return str(net)


def schalten(ein, netze_neu, wer="panel"):
    """The admin switch api.clients and the networks api.clients_from (written into this computer's config); on the
    model computer of a split install root's unit FW_UNIT then builds the door's firewall anew from the config."""
    import json
    if not isinstance(ein, bool) or not isinstance(netze_neu, list) or len(netze_neu) > MAX_NETZE:
        raise Fehler("wert")
    liste = sorted({netz_pruefen(n) for n in netze_neu})
    with _lock:
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
        raw["api"] = dict(raw.get("api") or {}, clients=ein, clients_from=liste)
        write_json(CONFIG_PATH, raw, indent=2)
    print(f"sparkclient: {wer} {'an' if ein else 'aus'} netze {len(liste)}", flush=True)
    if model_side():
        ok = run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", FW_UNIT], timeout=20)[0] == 0
        print(f"sparkclient: firewall {'gestartet' if ok else 'fehler'}", flush=True)
    return uebersicht()


def uebersicht(cfg=None):
    """What Einstellungen → Spark → Clients shows: the switch, the networks, the clients (never a hash or key)."""
    cfg = load_config() if cfg is None else cfg
    api = cfg.get("api") or {}
    return {"an": an(cfg), "netze": [str(n) for n in (api.get("clients_from") or [])][:MAX_NETZE],
            "clients": clients(), "max": MAX_CLIENTS, "rechte": list(RECHTE), "klassen": list(KLASSEN),
            "vorgabe": VORGABE, "grenzen": {k: list(v) for k, v in GRENZEN.items()}}


def im_netz(host, cfg=None):
    """True when a caller that comes straight to a service (not through the TLS-Tor, not from this machine) is in one
    of the networks of api.clients_from."""
    return adresse_in(host, netze(cfg))


def adresse_in(host, nets):
    """True for this machine and for an address in one of nets (also the Spark-Konsole's, konsole.erlaubt)."""
    try:
        ip = ipaddress.ip_address(str(host or "").split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or any(ip.version == n.version and ip in n for n in nets)


def netze(cfg=None):
    """The networks other clients may come from (api.clients_from), checked; [] while api.clients is off."""
    cfg = load_config() if cfg is None else cfg
    if not an(cfg):
        return []
    out = []
    for n in ((cfg.get("api") or {}).get("clients_from") or [])[:MAX_NETZE]:
        try:
            net = ipaddress.ip_network(str(n), strict=False)
        except ValueError:
            continue
        if net.is_private and not net.is_loopback:
            out.append(net)
    return out


def finden(authorization, cfg=None):
    """The client whose key is in the Authorization header ("Bearer …"), None otherwise (also while api.clients is
    off, for a blocked client and for api.key, which is no client of this list)."""
    got = authorization.decode("latin-1") if isinstance(authorization, bytes) else str(authorization or "")
    if not got.startswith("Bearer " + KEY_PREFIX) or len(got) > 200 or not an(cfg):
        return None
    sha = _sha(got[7:])
    hit = None
    for c in _lesen()["clients"]:   # every entry compared, so the time does not tell which one matched
        if isinstance(c, dict) and hmac.compare_digest(str(c.get("sha") or ""), sha):
            hit = c
    if hit is None or hit.get("gesperrt"):
        return None
    return hit


def darf(client, recht):
    return isinstance(client, dict) and recht in (client.get("rechte") or ())


def stufe(client):
    return KLASSEN.get(str(client.get("klasse")), STAGE_NORMAL)


def melden(client, warum, dienst, now=None, art="abgelehnt"):
    """One journal line per kind and client every LOG_GAP seconds (a refusal, or "gehalten" while somebody speaks)."""
    now = time.monotonic() if now is None else now
    k = (str(client.get("id")), warum)
    if now - _gemeldet.get(k, -LOG_GAP) >= LOG_GAP:
        _gemeldet[k] = now
        print(f"sparkclient: {art} {warum} {k[0]} {dienst}", flush=True)


# E3, speech first on the Spark for every client: "Hintergrund" never moves up while it waits at a gate (PrioGate fest)
# and, before it even queues, waits while somebody speaks here (the speech mark of ASR and TTS, any client or the
# assistant), at most HALTEN_MAX seconds, then it goes on last in line.
RUHE = 3.0         # seconds after the last speech piece that still count as speaking (like the panel's vorrang.GRACE)
HALTEN_MAX = 60.0
HALTEN_SCHRITT = 0.5


def fest(client):
    return isinstance(client, dict) and client.get("klasse") == "hintergrund"


def sprache_laeuft(now=None, path=None):
    try:
        m = os.stat(path or SPEECH_MARK).st_mtime
    except OSError:
        return False
    return 0 <= (time.time() if now is None else now) - m < RUHE


async def halten(client, dienst, schlafen=None, laeuft=None):
    """Seconds a background client waited for silence (0 for every other caller)."""
    if not fest(client):
        return 0.0
    import asyncio
    schlafen, laeuft = schlafen or asyncio.sleep, laeuft or sprache_laeuft
    t = 0.0
    while t < HALTEN_MAX and laeuft():
        if t == 0:
            melden(client, "sprache", dienst, art="gehalten")
        await schlafen(HALTEN_SCHRITT)
        t += HALTEN_SCHRITT
    return t


def minute_ok(client, dienst, now=None):
    now = time.monotonic() if now is None else now
    with _lock:
        t = [x for x in _minute.get((client["id"], dienst), []) if now - x < 60]
        if len(t) >= int(client.get("minute") or VORGABE["minute"]):
            _minute[(client["id"], dienst)] = t
            return False
        t.append(now)
        _minute[(client["id"], dienst)] = t
    return True


def _tag(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def tokens_ok(client, now=None):
    tag, n = _tage.get(client["id"], ("", 0))
    return tag != _tag(time.time() if now is None else now) or n < int(client.get("tokens_tag") or VORGABE["tokens_tag"])


def tokens_zaehlen(client, n, now=None):
    tag = _tag(time.time() if now is None else now)
    with _lock:
        alt_tag, alt = _tage.get(client["id"], ("", 0))
        _tage[client["id"]] = (tag, (alt if alt_tag == tag else 0) + max(0, int(n or 0)))


def tokens_heute(client, now=None):
    tag, n = _tage.get(client["id"], ("", 0))
    return n if tag == _tag(time.time() if now is None else now) else 0


def herein(client):
    """One request more at the LLM-Tor if the client's parallel limit allows (raus() when it ends)."""
    with _lock:
        n = _offen.get(client["id"], 0)
        if n >= int(client.get("parallel") or VORGABE["parallel"]):
            return False
        _offen[client["id"]] = n + 1
    return True


def raus(client):
    with _lock:
        _offen[client["id"]] = max(0, _offen.get(client["id"], 0) - 1)


def _version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as f:
            v = f.read().strip()
    except OSError:
        return ""
    return v if re.fullmatch(r"V\d{2}\.\d\.\d{3}", v) else ""


def faehigkeiten(client, cfg=None):
    """GET /v1/spark/faehigkeiten (plan spark-entkoppeln E2) on the LLM-Tor, Hören and Sprechen: what this Spark offers
    and what the caller's key may, so a client (another assistant, later the own assistant with other providers, E6)
    goes by the API version SPARK_API instead of the Spark's version. client None = api.key (every right). Only fixed
    words, ports and numbers; never a model's path, never another client."""
    cfg = load_config() if cfg is None else cfg
    llm = cfg.get("llm") or {}
    dienste = {}
    for art, sec in MODEL_ARTS.items():
        c = cfg.get(sec) or {}
        an_ = c.get("enabled", art in ("asr", "tts")) is True and bool(c.get("port"))
        dienste[art] = {"an": an_, "port": int(c.get("port") or 0) if an_ else 0}
    dienste["llm"].update(modell=LLM_NAME, sehen=bool(llm.get("sehen_modell")), helfer=bool(llm.get("helfer_modell")),
                          systemone=True)
    rechte = list(RECHTE) if client is None else [r for r in RECHTE if darf(client, r)]
    out = {"spark_api": SPARK_API, "version": _version(), "dienste": dienste, "rechte": rechte}
    if client is None:
        out["client"] = {"name": "Assistent", "klasse": "sprache"}
    else:
        out["client"] = {"name": client.get("name"), "klasse": client.get("klasse"),
                         **{k: client.get(k) for k in GRENZEN}}
    return out


def faehigkeiten_dep():
    """FastAPI dependency for GET /v1/spark/faehigkeiten: api.key or any Spark-Client (whatever its rights); the
    client (or None for api.key) as its value."""
    from fastapi import Header, HTTPException, Request
    from common import api_key_dependency
    nur_key = api_key_dependency()

    def dep(request: Request, authorization: str = Header(None)):
        c = finden(authorization)
        if c is not None:
            if not im_netz(request.client.host if request.client else ""):
                raise HTTPException(403, "netz")
            if not minute_ok(c, "faehigkeiten"):
                raise HTTPException(429, "limit")
            return c
        nur_key(request, authorization)
        return None
    return dep


def _cli(argv):
    """`speech-spark clients …` on the computer that runs the services (also a Spark without a panel): prints fixed
    words and the entries; a new key once. Exit code 1 with the reason word on a refusal."""
    import json
    cmd = argv[0] if argv else "liste"
    try:
        if cmd == "liste":
            d = uebersicht()
            print(json.dumps({k: d[k] for k in ("an", "netze", "clients")}, ensure_ascii=False, indent=2))
        elif cmd == "an":
            schalten(True, argv[1:] or [str(n) for n in (load_config().get("api") or {}).get("clients_from") or []], "befehl")
        elif cmd == "aus":
            schalten(False, [str(n) for n in (load_config().get("api") or {}).get("clients_from") or []], "befehl")
        elif cmd == "neu" and len(argv) in (3, 4):
            c, key = neu(argv[1], [r for r in argv[2].split(",") if r], argv[3] if len(argv) == 4 else None)
            print(f"{c['id']} {key}")
        elif cmd in ("sperren", "entsperren") and len(argv) == 2:
            aendern(argv[1], {"gesperrt": cmd == "sperren"})
        elif cmd == "weg" and len(argv) == 2:
            weg(argv[1])
        else:
            print("clients [liste] | an [netz …] | aus | neu <name> <recht,recht…> [klasse] | sperren|entsperren|weg <id>")
            return 2
    except Fehler as e:
        print(f"sparkclient: abgelehnt {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
