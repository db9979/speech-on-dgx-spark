"""Modell-Rechner genau (Dominik 2026-11-16 „Alles auf einmal umsetzen“): what the computer with the models does right now,
for the page Zustand → Überblick → Modell-Rechner genau (panel/modellgenau.py). Numbers and fixed words only: never a
prompt, an answer, a voice, a profile, a process, a path or an address.

    messen(einheiten, cfg)   one look at this computer (the Wärter sends it in its status as "betrieb"; on one Spark
                             the panel calls it itself): per service its state (geladen, laedt, entladen, aus, fehler,
                             fehlt), its gate (slots, running, waiting, full), the requests in its gate (kind, stage,
                             seconds, tokens; common.PrioGate.bild), the counters of every vLLM engine from its own
                             /metrics (requests, KV cache, prefix cache, MTP, tokens, latency buckets), the GPU's clock
                             and why it throttles, the memory each service takes, the last finished requests of
                             the language model with their result, and how often the GPU driver refused memory
                             (NVRM lines in the kernel log, counted only, nvrm)

Only this computer's own services on 127.0.0.1 are asked (no address from a setting or from outside), each at most
TIMEOUT_S and all together at most FRIST_S seconds; an engine whose unit does not run is not asked. Counters stay
counters: the panel computes rates and percentiles from two looks in a row. Nothing is logged here (it runs every
few seconds); the panel logs the events it derives ("rechner: ereignis …").
"""
import os
import re
import time

import mandanten
from common import ARTEN, BILD_MAX, ON_DEMAND_UNITS, OWN_LLM_UNITS, UNITS, einheiten_stand, load_config, mem_available_gib, run

TIMEOUT_S = 0.5        # seconds one local service may take to answer
FRIST_S = 2.0          # seconds for the whole look (the Wärter answers its status within steuer.TIMEOUT)
METRIK_MAX = 2_000_000  # bytes of an engine's /metrics text read at most
BUCKETS_MAX = 40       # latency buckets per histogram
CGROUP = "/sys/fs/cgroup/system.slice"
_EIGEN = re.compile(r"speech-spark-([a-z][a-z0-9-]{0,23})\.service")
# the services shown, in this order: id -> (unit id of common's unit lists, config section, engine port key or None,
# service port key or None, runs only on demand)
DIENSTE = {"llm": ("llm", "llm", "engine_port", "port", False), "sehen": ("sehen", "llm", "sehen_port", None, True),
           "helfer": ("helfer", "llm", "helfer_port", None, True),
           "asr": ("asr-engine", "asr", "engine_port", "port", False), "tts": ("tts-engine", "tts", "engine_port", "port", False),
           "tts-design": ("tts-design", "tts", "voicedesign_port", None, True), "tts-klon": ("tts-klon", "tts", "klon_port", None, True),
           "bild": ("bild", "image", None, "port", True), "musik": ("musik", "music", None, "port", True)}
ZUSTAENDE = ("geladen", "laedt", "haengt", "entladen", "aus", "fehler", "fehlt")
ERGEBNISSE = ("fertig", "abgebrochen", "zeit", "fehler")   # llm_tor.ERGEBNISSE
NVRM_S = 60            # the kernel log is counted at most this often
# a refused GPU memory allocation in the kernel log (the driver's own words; the line itself is never kept)
NVRM = re.compile(r"NVRM:.*(NV_ERR_NO_MEMORY|[Oo]ut of memory|failed to allocate)")
_nvrm = {"t": None, "wert": None}
# vLLM's metric names (V1 engine; the older name second) -> key here
ZAEHLER = {"laufen": ("num_requests_running",), "warten": ("num_requests_waiting",),
           "kv": ("kv_cache_usage_perc", "gpu_cache_usage_perc"),
           "prefix_treffer": ("prefix_cache_hits_total",), "prefix_fragen": ("prefix_cache_queries_total",),
           "mtp_an": ("spec_decode_num_accepted_tokens_total",), "mtp_entwurf": ("spec_decode_num_draft_tokens_total",),
           "mtp_schritte": ("spec_decode_num_drafts_total",),
           "tok_rein": ("prompt_tokens_total",), "tok_raus": ("generation_tokens_total",),
           "verdraengt": ("num_preemptions_total",), "fertig": ("request_success_total",)}
HISTO = {"ttft": ("time_to_first_token_seconds",), "itl": ("inter_token_latency_seconds", "time_per_output_token_seconds")}
# nvidia-smi's clock event reasons (bit -> fixed word); the field's older name second
DROSSEL = {0x1: "leerlauf", 0x2: "taktgrenze", 0x4: "leistungsgrenze", 0x8: "hw_bremse", 0x10: "sync",
           0x20: "waerme", 0x40: "hw_waerme", 0x80: "netzteil", 0x100: "anzeige"}
GPU_FELDER = ("clocks_event_reasons.active", "clocks_throttle_reasons.active")
_gpu_feld = []         # the field this nvidia-smi knows (found once)


def _zahl(v, hi=1e18):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= hi else None


def metriken(text):
    """The counters of one vLLM engine from its /metrics text (summed over labels), None for a missing one; the
    histograms as [[upper bound, count], …] (the last bound is inf as 1e9)."""
    werte = {}
    for m in re.finditer(r"^vllm:([a-z_]+?)(?:\{([^}]*)\})? ([0-9.eE+\-]+|NaN|\+Inf)$", text, re.M):
        try:
            v = float(m.group(3))
        except ValueError:
            continue
        if v != v:
            continue
        name = m.group(1)
        if name.endswith("_bucket"):
            le = re.search(r'le="([^"]+)"', m.group(2) or "")
            if not le:
                continue
            try:
                grenze = 1e9 if le.group(1) == "+Inf" else float(le.group(1))
            except ValueError:
                continue
            b = werte.setdefault(name, {})
            b[grenze] = b.get(grenze, 0) + v
        else:
            werte[name] = werte.get(name, 0) + v
    out = {}
    for k, namen in ZAEHLER.items():
        v = next((werte[n] for n in namen if n in werte), None)
        out[k] = None if v is None else round(v * 100, 1) if k == "kv" else v
    for k, namen in HISTO.items():
        b = next((werte[n + "_bucket"] for n in namen if isinstance(werte.get(n + "_bucket"), dict)), None)
        out[k] = [[g, b[g]] for g in sorted(b)][:BUCKETS_MAX] if b else None
    z = re.search(r"^vllm:cache_config_info\{([^}]*)\}", text, re.M)   # the context store in tokens (modelle.kv_platz)
    f = dict(re.findall(r'(\w+)="([^"]*)"', z.group(1))) if z else {}
    try:
        out["kv_tokens"] = int(f["num_gpu_blocks"]) * int(f["block_size"])
    except (KeyError, ValueError):
        out["kv_tokens"] = None
    return out


def _holen(c, port, path, key=""):
    """(status code, text) of a local service, (0, "") when it does not answer."""
    try:
        r = c.get(f"http://127.0.0.1:{int(port)}{path}", timeout=TIMEOUT_S,
                  headers={"Authorization": f"Bearer {key}"} if key else None)
        return r.status_code, r.text[:METRIK_MAX]
    except Exception:
        return 0, ""


def _json(text):
    import json
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def zeilen(rows, dienst):
    """A service's requests as data: known keys only, fixed words, numbers in range."""
    out = []
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict) or x.get("z") not in ("laeuft", "wartet"):
            continue
        out.append({"d": dienst, "z": x["z"], "stufe": x.get("stufe") if x.get("stufe") in (0, 1, 2) else 1,
                    "art": x.get("art") if x.get("art") in ARTEN else "", "s": _zahl(x.get("s"), 1e7) or 0,
                    "folge": x.get("folge") is True, "rein": _zahl(x.get("rein"), 1e9), "raus": _zahl(x.get("raus"), 1e9),
                    "kunde": _kunde(x.get("kunde"))})
    return out[:BILD_MAX]


def _kunde(v):
    """The name an admin gave a Spark client (mandanten.NAME_RE), else ""."""
    return v if isinstance(v, str) and mandanten.NAME_RE.fullmatch(v) else ""


def fertige(rows):
    """The language model's last finished requests as data: time, kind, stage, seconds, tokens, client, result."""
    out = []
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict) or x.get("ergebnis") not in ERGEBNISSE or _zahl(x.get("t"), 1e11) is None:
            continue
        out.append({"t": int(x["t"]), "art": x.get("art") if x.get("art") in ARTEN else "",
                    "stufe": x.get("stufe") if x.get("stufe") in (0, 1, 2) else 1, "s": _zahl(x.get("s"), 1e7) or 0,
                    "rein": _zahl(x.get("rein"), 1e9), "raus": _zahl(x.get("raus"), 1e9), "kunde": _kunde(x.get("kunde")),
                    "ergebnis": x["ergebnis"]})
    return out[-BILD_MAX:]


def nvrm(lauf=run, now=None):
    """How often the GPU driver refused memory in the last hour and day: {"h1", "h24"} or None (no kernel log to read).
    Counted from the kernel log at most every NVRM_S seconds; no line is kept."""
    now = time.time() if now is None else now
    if _nvrm["t"] is not None and now - _nvrm["t"] < NVRM_S:
        return _nvrm["wert"]
    rc, out = lauf(["journalctl", "-k", "-q", "--no-pager", "-o", "short-unix", "--since", "-24h"], timeout=5)
    wert = None
    if rc == 0:
        h1 = h24 = 0
        for line in out.splitlines():
            if not NVRM.search(line):
                continue
            try:
                t = float(line.split(" ", 1)[0])
            except ValueError:
                continue
            h24 += 1
            h1 += now - t <= 3600
        wert = {"h1": h1, "h24": h24}
    _nvrm.update(t=now, wert=wert)
    return wert


def tor(q):
    """A gate's view (common.PrioGate.view) as numbers."""
    q = q if isinstance(q, dict) else {}
    return {"plaetze": _zahl(q.get("slots"), 4096), "laufen": _zahl(q.get("running"), 4096), "warten": _zahl(q.get("waiting"), 4096),
            "voll": _zahl(q.get("full")), "wartete_max_ms": _zahl(q.get("waited_max_ms"))}


def gpu_mehr(lauf=run):
    """The GPU's performance state, its highest clock and why it throttles now (fixed words of DROSSEL); {} without."""
    import shutil
    if not shutil.which("nvidia-smi"):
        return {}
    felder = _gpu_feld or list(GPU_FELDER)
    for f in felder:
        code, out = lauf(["nvidia-smi", f"--query-gpu={f},pstate,clocks.max.sm,clocks.mem", "--format=csv,noheader,nounits"])
        if code != 0 or not out:
            continue
        if not _gpu_feld:
            _gpu_feld.append(f)
        teile = [x.strip() for x in out.splitlines()[0].split(",")]
        try:
            bits = int(teile[0], 16)
        except (ValueError, IndexError):
            bits = None
        p = teile[1] if len(teile) > 1 and re.fullmatch(r"P[0-9]{1,2}", teile[1]) else ""

        def num(i):
            try:
                return _zahl(float(teile[i]), 1e5)
            except (ValueError, IndexError):
                return None
        return {"drossel": None if bits is None else [w for b, w in DROSSEL.items() if bits & b], "pstate": p,
                "takt_max": num(2), "takt_speicher": num(3)}
    return {}


def _einheit_von_pid(pid):
    """The own service a process belongs to (its systemd unit), "docker" for a model container, None else."""
    try:
        with open(f"/proc/{int(pid)}/cgroup") as f:
            txt = f.read(4096)
    except (OSError, ValueError):
        return None
    m = _EIGEN.search(txt)
    if m:
        return m.group(1)
    return "docker" if "docker-" in txt else None


def speicher(prozesse, base=CGROUP, lesen=None):
    """GiB each own service holds: the larger of systemd's memory counter (memory.current) and the GPU memory of its
    processes (nvidia-smi); model containers together as "docker". Ids only, never a process or a path."""
    def lies(p):
        with open(p) as f:
            return f.read(64)
    lesen = lesen or lies
    gib, out = 2 ** 30, {}
    try:
        namen = os.listdir(base)
    except OSError:
        namen = []
    for n in namen:
        m = _EIGEN.fullmatch(n)
        teil = m.group(1) if m else "docker" if n.startswith("docker-") and n.endswith(".scope") else None
        if teil is None:
            continue
        try:
            out[teil] = out.get(teil, 0) + int(lesen(f"{base}/{n}/memory.current").strip()) / gib
        except (OSError, ValueError):
            continue
    gpu = {}
    for p in prozesse or []:
        teil = _einheit_von_pid(p.get("pid")) if isinstance(p, dict) else None
        mib = _zahl(p.get("mem_mib")) if isinstance(p, dict) else None
        if teil and mib is not None:
            gpu[teil] = gpu.get(teil, 0) + mib / 1024
    for teil, v in gpu.items():
        out[teil] = max(out.get(teil, 0), v)
    return {k: round(v, 1) for k, v in sorted(out.items(), key=lambda x: -x[1]) if v >= 0.05}


def _zustand(unit, gesund, bedarf, proxy_status=None):
    """One fixed word of ZUSTAENDE from the unit's state, the engine's /health and (pictures, music) the service's own."""
    st = (unit or {}).get("state", "unknown")
    if unit and unit.get("da") is False:
        return "fehlt"
    if st == "failed":
        return "fehler"
    if st in ("activating", "reloading"):
        return "laedt"
    if st != "active":
        return "entladen" if bedarf else "aus"
    if proxy_status is not None:
        return {"ready": "geladen", "busy": "geladen", "starting": "laedt", "error": "fehler", "missing": "fehlt"}.get(
            proxy_status, "entladen")
    return "geladen" if gesund else "laedt"


def messen(einheiten=None, cfg=None, gpu=None, client=None, uhr=time.monotonic):
    """One look (see the module's text). einheiten: the Wärter's unit states ({unit: {"state", "da"}}, asked here
    when None); gpu: common.gpu_stats() (its processes for the memory per service)."""
    import httpx
    cfg = load_config() if cfg is None else cfg
    alle = dict(UNITS, **OWN_LLM_UNITS, **ON_DEMAND_UNITS)
    if einheiten is None:
        einheiten = einheiten_stand(list(alle.values()))
    key = (cfg.get("api") or {}).get("key", "")
    t0 = uhr()
    c = client or httpx.Client()
    dienste, anfragen, vllm, kanarie, fertig, bremse = {}, [], {}, None, [], None
    try:
        for d, (uid, sec, eport, sport, bedarf) in DIENSTE.items():
            s = cfg.get(sec) or {}
            if sec in ("image", "music") and not s.get("enabled"):
                continue
            unit = einheiten.get(alle.get(uid, ""))
            zeit = uhr() - t0 < FRIST_S
            aktiv = (unit or {}).get("state") == "active"
            gesund, h = False, {}
            if eport and aktiv and zeit and _zahl(s.get(eport), 65535):
                code, _ = _holen(c, s[eport], "/health")
                gesund = code == 200
                if gesund and uhr() - t0 < FRIST_S:
                    code, text = _holen(c, s[eport], "/metrics")
                    if code == 200:
                        vllm[d] = metriken(text)
            if sport and zeit and _zahl(s.get(sport), 65535) and (aktiv or d in ("llm", "asr", "tts")):
                code, text = _holen(c, s[sport], "/health", key)
                h = _json(text) if code == 200 else {}
            proxy = h.get("status") if d in ("bild", "musik") and isinstance(h.get("status"), str) else None
            if d in ("bild", "musik") and not h and aktiv:
                proxy = "off"
            zu = _zustand(unit, gesund, bedarf, proxy)
            if d == "llm" and zu == "geladen" and h.get("haengt") is True:
                zu = "haengt"
            row = {"zustand": zu}
            q = h.get("tor") if d == "llm" else h.get("queue")
            if q is not None:
                row.update(tor(q))
            for k in ("requests", "failures", "systemone"):
                if _zahl(h.get(k)) is not None:
                    row[{"requests": "anfragen", "failures": "fehler", "systemone": "systemone"}[k]] = h[k]
            if d in ("bild", "musik") and proxy == "busy":
                row["laufen"] = 1
            dienste[d] = row
            anfragen += zeilen(h.get("anfragen"), "llm" if d == "llm" else d)
            if d == "llm":
                fertig = fertige(h.get("fertig"))
                if h:
                    bremse = {"an": h.get("bremse") is True, "n": _zahl(h.get("bremse_n"), 1e9) or 0}
            if d == "llm" and h:
                st = h.get("status") if h.get("status") in ("ready", "loading", "error", "down") else None
                kanarie = {"status": st, "ms": _zahl(h.get("canary_ms"), 1e7)}
    finally:
        if client is None:
            c.close()
    gpu = gpu if isinstance(gpu, dict) else None
    return {"v": 1, "dienste": dienste, "anfragen": anfragen[:BILD_MAX * 2], "vllm": vllm, "kanarie": kanarie,
            "gpu": gpu_mehr() if gpu is not None else {}, "speicher": speicher((gpu or {}).get("processes")),
            "mem": _mem(), "fertig": fertig, "bremse": bremse, "nvrm": nvrm() if gpu is not None else None, "dauer_ms": int((uhr() - t0) * 1000)}


def _mem():
    """Unified memory of this computer in GiB (free for new work, all), from /proc/meminfo."""
    try:
        return {"frei": round(mem_available_gib(), 1), "gesamt": round(mem_available_gib("MemTotal"), 1)}
    except (OSError, ValueError, IndexError):
        return {"frei": None, "gesamt": None}
