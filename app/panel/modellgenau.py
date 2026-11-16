"""Zustand → Überblick → Modell-Rechner genau (Dominik 2026-11-16 „Alles auf einmal umsetzen“):
what the computer with the models does right now and did lately. With the
models on another computer (Spark teilen) the numbers come from its Wärter (status "betrieb", modellblick.messen);
on one Spark the panel looks itself with the same module, so the page is the same in both.

    probe(gpu)       every 3 s from the panel's sampler: takes one look (checked: data from another computer), keeps
                     the rates (tokens per second, prefix cache, MTP, latency) from two looks in a row, the curves
                     (20 minutes, 24 hours, 7 days) and derives the events
    ansicht(zeit)    /api/admin/modellgenau: now, services, requests (no content, no profile), language model
                     inside, GPU, memory per service, one curve, events, notes
    fuer_live()      Zustand → Live and the Steuerzentrale: requests running and waiting, tokens per second

Numbers and fixed words only, never a prompt, an answer, a voice, a profile, a process or an address: the model
computer's values are data, taken only with known keys, numbers in range and words from fixed lists.
The events follow fixed rules (never a model) and write one log line each ("rechner: ereignis <wort> <dienst>"). The
24-hour and 7-day curves and the events are kept in STATE/modellgenau.json (every SICHERN_S seconds, not in the
backup: they come again).
"""
import os
import sys
import threading
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import modellblick  # noqa: E402
import rechner  # noqa: E402
import steuer  # noqa: E402
from common import BILD_MAX, STATE, gpu_stats, load_config, read_json, write_json  # noqa: E402

DATEI = os.path.join(STATE, "modellgenau.json")
SICHERN_S = 300        # seconds between two saves of the long curves and the events
FENSTER_S = 300        # seconds of the window for prefix cache, MTP, latency and „letzte 5 min“
KURZ, TAG, WOCHE = 400, 1440, 672      # points: every 3 s (20 min), every minute (24 h), every 15 minutes (7 days)
TAG_S, WOCHE_S = 60, 900
EREIGNISSE = 200       # events kept
WARTEN_LANG_S = 5      # a request waiting this long is an event and a note
KV_VOLL = 90           # % KV cache from which it is an event and a note
DROSSEL_SCHLIMM = ("leistungsgrenze", "hw_bremse", "waerme", "hw_waerme", "netzteil")   # reasons worth an event
ZEITEN = ("20m", "24h", "7d")
# the services in the page's order with their names (de, en) and the config's model key
DIENSTE = {"llm": ("Sprachmodell", "Language model", "llm", "modell"),
           "sehen": ("Bildverständnis", "Image understanding", "llm", "sehen_modell"),
           "helfer": ("Hilfsmodell", "Helper model", "llm", "helfer_modell"),
           "asr": ("Spracherkennung", "Speech recognition", "asr", "model"),
           "tts": ("Sprachausgabe", "Speech output", "tts", "model"),
           "tts-design": ("Stimmen gestalten", "Voice design", "tts", "voicedesign_model"),
           "tts-klon": ("Eigene Stimmen", "Own voices", "tts", "klon_model"),
           "bild": ("Bilder malen", "Painting pictures", "image", "variant"),
           "musik": ("Musik machen", "Making music", "music", "variant")}
ARTEN_NAMEN = {"gespraech": ("Gespräch", "Conversation"), "programm": ("Programm", "Program"),
               "entwickler": ("Entwickler", "Developer"), "sehen": ("Bild ansehen", "Looking at a picture"),
               "helfer": ("Hilfsmodell", "Helper model"), "systemone": ("Einordnen (System One)", "Sorting (System One)"),
               "hoeren": ("Hören", "Hearing"), "sprechen": ("Sprechen", "Speaking"),
               "stimme_entwerfen": ("Stimme gestalten", "Designing a voice"), "eigene_stimme": ("Eigene Stimme", "Own voice"),
               "": ("Anfrage", "Request")}
STUFEN = {0: ("hinten", "last"), 1: ("normal", "normal"), 2: ("Vorrang", "priority")}
ZUSTAND_NAMEN = {"geladen": ("geladen", "loaded"), "laedt": ("lädt", "loading"), "entladen": ("entladen", "unloaded"),
                 "aus": ("aus", "off"), "fehler": ("Fehler", "error"), "fehlt": ("nicht eingerichtet", "not set up"),
                 "haengt": ("hängt", "hangs")}
ERGEBNIS_NAMEN = {"fertig": ("fertig", "done"), "abgebrochen": ("abgebrochen", "cancelled"),
                  "zeit": ("Zeit abgelaufen", "timed out"), "fehler": ("Fehler", "error")}
EREIGNIS_NAMEN = {"geladen": ("geladen", "loaded"), "laedt": ("wird geladen", "is loading"), "entladen": ("entladen", "unloaded"),
                  "aus": ("aus", "off"), "fehler": ("Fehler", "error"), "fehlt": ("nicht eingerichtet", "not set up"),
                  "warteschlange_voll": ("Warteschlange voll, Anfrage abgelehnt", "queue full, request refused"),
                  "wartet_lang": ("eine Anfrage wartet länger als 5 s", "a request waits longer than 5 s"),
                  "kanarie_fehler": ("Probeantwort klappt nicht", "test answer fails"),
                  "kanarie_ok": ("Probeantwort klappt wieder", "test answer works again"),
                  "drosselt": ("GPU drosselt", "GPU throttles"), "kv_voll": ("KV-Cache über 90 %", "KV cache above 90 %"),
                  "verdraengt": ("Anfragen verdrängt (Preemption)", "requests preempted"),
                  "modell": ("anderes Modell", "other model"),
                  "haengt": ("hängt: liest und schreibt keine Tokens", "hangs: reads and writes no tokens"),
                  "ohne_auftrag": ("rechnet an Anfragen, die niemand mehr will", "computes requests nobody waits for"),
                  "gpu_speicher": ("GPU hat Speicher verweigert", "GPU refused memory")}
DROSSEL_NAMEN = {"leerlauf": ("Leerlauf", "idle"), "taktgrenze": ("Taktgrenze", "clock cap"),
                 "leistungsgrenze": ("Leistungsgrenze", "power cap"), "hw_bremse": ("Hardware-Bremse", "hardware slowdown"),
                 "sync": ("Sync-Boost", "sync boost"), "waerme": ("zu warm", "too warm"), "hw_waerme": ("zu warm (Hardware)", "too warm (hardware)"),
                 "netzteil": ("Netzteil", "power supply"), "anzeige": ("Anzeige", "display")}
HINWEISE = {"kv_voll": ("Der KV-Cache ist fast voll: lange Gespräche werden langsamer oder verdrängt.",
                        "The KV cache is nearly full: long conversations slow down or get preempted."),
            "wartet_lang": ("Anfragen warten länger als 5 s: es laufen gerade mehr als Plätze frei sind.",
                            "Requests wait longer than 5 s: more are running than there are free slots."),
            "drosselt": ("Die GPU drosselt wegen Wärme oder Leistung.", "The GPU throttles because of heat or power."),
            "kanarie": ("Das Sprachmodell gibt gerade keine Probeantwort.", "The language model gives no test answer right now."),
            "fehler": ("Ein Dienst meldet einen Fehler.", "A service reports an error."),
            "haengt": ("Das Sprachmodell hängt: Anfragen laufen, aber es kommen keine Tokens.",
                       "The language model hangs: requests run, but no tokens come."),
            "ohne_auftrag": ("Die Engine rechnet mehr Anfragen, als das LLM-Tor kennt: abgebrochene laufen weiter.",
                             "The engine computes more requests than the LLM-Tor knows: cancelled ones keep running."),
            "gpu_speicher": ("Die GPU hat in der letzten Stunde Speicher verweigert.", "The GPU refused memory in the last hour.")}
OHNE_AUFTRAG_N = 3     # looks in a row (3 s each) with more requests in the engine than in the gate
ZUSTAENDE = modellblick.ZUSTAENDE
VLLM_ZAHLEN = tuple(modellblick.ZAEHLER) + ("kv_tokens",)

_lock = threading.Lock()
_stand = {"letzt": None, "t": None, "raten": {}, "fenster": deque(maxlen=FENSTER_S // 3 + 5), "geladen": False,
          "gesichert": 0.0, "zustand": {}, "episode": set(), "kanarie": None, "voll": {}, "verdraengt": None,
          "modell": {}, "tag": None, "woche": None, "ohne": 0, "nvrm": None}
_kurz, _tag, _woche = deque(maxlen=KURZ), deque(maxlen=TAG), deque(maxlen=WOCHE)
_ereignisse = deque(maxlen=EREIGNISSE)


def _zahl(v, hi=1e18):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= hi else None


def _histo(h):
    if not isinstance(h, list):
        return None
    out = []
    for x in h[:modellblick.BUCKETS_MAX]:
        if isinstance(x, list) and len(x) == 2 and _zahl(x[0], 1e9) is not None and _zahl(x[1]) is not None:
            out.append([x[0], x[1]])
    return out or None


def pruefen(b):
    """The look as data (it may come from another computer): known keys, numbers in range, fixed words only."""
    if not isinstance(b, dict):
        return None
    dienste = {}
    for d, x in (b.get("dienste") or {}).items() if isinstance(b.get("dienste"), dict) else []:
        if d not in DIENSTE or not isinstance(x, dict) or x.get("zustand") not in ZUSTAENDE:
            continue
        dienste[d] = {"zustand": x["zustand"], **{k: _zahl(x.get(k), 1e12) for k in
                      ("plaetze", "laufen", "warten", "voll", "wartete_max_ms", "anfragen", "fehler", "systemone")}}
    vllm = {}
    for d, x in (b.get("vllm") or {}).items() if isinstance(b.get("vllm"), dict) else []:
        if d in DIENSTE and isinstance(x, dict):
            vllm[d] = {k: _zahl(x.get(k)) for k in VLLM_ZAHLEN}
            if vllm[d]["kv"] is not None and vllm[d]["kv"] > 100:
                vllm[d]["kv"] = None
            for k in modellblick.HISTO:
                vllm[d][k] = _histo(x.get(k))
    anfragen = []
    for d in DIENSTE:
        anfragen += [dict(x, d=d) for x in modellblick.zeilen([y for y in b.get("anfragen") or [] if isinstance(y, dict)
                                                                 and y.get("d") == d], d)]
    k = b.get("kanarie") if isinstance(b.get("kanarie"), dict) else {}
    g = b.get("gpu") if isinstance(b.get("gpu"), dict) else {}
    dr = g.get("drossel")
    gpu = {"drossel": [w for w in dr if w in modellblick.DROSSEL.values()] if isinstance(dr, list) else None,
           "pstate": g.get("pstate") if isinstance(g.get("pstate"), str) and len(g["pstate"]) <= 3 and g["pstate"][:1] == "P"
           and g["pstate"][1:].isdigit() else "",
           "takt_max": _zahl(g.get("takt_max"), 1e5), "takt_speicher": _zahl(g.get("takt_speicher"), 1e5)}
    sp = b.get("speicher") if isinstance(b.get("speicher"), dict) else {}
    mem = b.get("mem") if isinstance(b.get("mem"), dict) else {}
    speicher = {i: v for i, v in list(sp.items())[:rechner.DIENSTE_MAX]
                if isinstance(i, str) and rechner.DIENST_ID.fullmatch(i) and _zahl(v, 65536) is not None}
    return {"dienste": dienste, "vllm": vllm, "anfragen": anfragen[:BILD_MAX * 2],
            "kanarie": {"status": k.get("status") if k.get("status") in ("ready", "loading", "error", "down") else None,
                        "ms": _zahl(k.get("ms"), 1e7)} if k else None,
            "gpu": gpu, "speicher": speicher, "mem": {k: _zahl(mem.get(k), 65536) for k in ("frei", "gesamt")},
            "fertig": modellblick.fertige(b.get("fertig")), "nvrm": _nvrm(b.get("nvrm"))}


def _nvrm(v):
    """The GPU driver's memory refusals as {"h1", "h24"}, or None when the kernel log could not be read."""
    if not isinstance(v, dict) or _zahl(v.get("h1"), 1e7) is None or _zahl(v.get("h24"), 1e7) is None:
        return None
    return {"h1": int(v["h1"]), "h24": int(v["h24"])}


def _messen(gpu, cfg):
    """One look: the Wärter's last status with the models apart, else this computer itself."""
    if steuer.remote(cfg):
        d = steuer.cached()
        return pruefen((d or {}).get("betrieb")) if d else None
    return pruefen(modellblick.messen(None, cfg, gpu_stats() if gpu is None else gpu))


def _delta(alt, neu, k):
    a, n = (alt or {}).get(k), (neu or {}).get(k)
    return n - a if isinstance(a, (int, float)) and isinstance(n, (int, float)) and n >= a else None


def _quantil(alt, neu, q):
    """The q-quantile in seconds of a histogram between two looks (upper bound of its bucket), None without requests."""
    if not neu:
        return None
    a = {g: n for g, n in (alt or [])}
    d = [(g, n - a.get(g, 0)) for g, n in neu]
    gesamt = d[-1][1] if d else 0
    if gesamt <= 0:
        return None
    for g, n in d:
        if n >= q * gesamt:
            return None if g >= 1e9 else g
    return None


def _ereignis(wort, dienst="", n=None, now=None):
    _ereignisse.append({"t": int(time.time() if now is None else now), "w": wort, "d": dienst, "n": n})
    print(f"rechner: ereignis {wort} {dienst or '-'}" + (f" {n}" if n is not None else ""), flush=True)


def _ereignisse_ableiten(m, now):
    """The fixed rules for events (one log line each), against the look before."""
    st = _stand
    erst = not st["zustand"]
    for d, x in m["dienste"].items():
        war = st["zustand"].get(d)
        if not erst and war is not None and war != x["zustand"]:
            _ereignis(x["zustand"], d, now=now)
        st["zustand"][d] = x["zustand"]
        v, vw = x.get("voll"), st["voll"].get(d)
        if v is not None and vw is not None and v > vw:
            _ereignis("warteschlange_voll", d, int(v - vw), now)
        st["voll"][d] = v
    lang = {x["d"] for x in m["anfragen"] if x["z"] == "wartet" and x["s"] >= WARTEN_LANG_S}
    for d in lang - {e[1] for e in st["episode"] if e[0] == "wartet_lang"}:
        _ereignis("wartet_lang", d, now=now)
    kv = (m["vllm"].get("llm") or {}).get("kv")
    schlimm = [w for w in (m["gpu"].get("drossel") or []) if w in DROSSEL_SCHLIMM]
    neu = {("wartet_lang", d) for d in lang} | ({("kv_voll", "llm")} if kv is not None and kv >= KV_VOLL else set()) \
        | {("drosselt", w) for w in schlimm}
    for e in neu - st["episode"]:
        if e[0] != "wartet_lang":
            _ereignis(e[0], e[1], now=now)
    st["episode"] = neu
    k = (m.get("kanarie") or {}).get("status")
    if k in ("ready", "error") and st["kanarie"] in ("ready", "error") and k != st["kanarie"]:
        _ereignis("kanarie_ok" if k == "ready" else "kanarie_fehler", "llm", now=now)
    if k in ("ready", "error"):
        st["kanarie"] = k
    vd = (m["vllm"].get("llm") or {}).get("verdraengt")
    if vd is not None and st["verdraengt"] is not None and vd > st["verdraengt"]:
        _ereignis("verdraengt", "llm", int(vd - st["verdraengt"]), now)
    st["verdraengt"] = vd
    st["ohne"] = st["ohne"] + 1 if _ohne_auftrag(m) else 0
    if st["ohne"] == OHNE_AUFTRAG_N:
        _ereignis("ohne_auftrag", "llm", now=now)
    nv = (m.get("nvrm") or {}).get("h24")
    if nv is not None and st["nvrm"] is not None and nv > st["nvrm"]:
        _ereignis("gpu_speicher", "", int(nv - st["nvrm"]), now)
    if nv is not None:
        st["nvrm"] = nv


def _ohne_auftrag(m):
    """More requests run in the language model's engine than the LLM-Tor has running (its gate and System One)."""
    engine = (m["vllm"].get("llm") or {}).get("laufen")
    zeilen = sum(1 for x in m["anfragen"] if x["d"] == "llm" and x["z"] == "laeuft")
    tor = max(zeilen, (m["dienste"].get("llm") or {}).get("laufen") or 0)
    return engine is not None and engine > tor


def _raten(alt, neu, dt, fenster):
    """Rates between two looks and over the window: tokens per second, prefix cache, MTP, latency, requests."""
    out = {}
    for d, v in neu["vllm"].items():
        a = (alt or {}).get("vllm", {}).get(d) if alt else None
        f = fenster[0]["vllm"].get(d) if fenster else None
        r = {"raus_s": None, "rein_s": None}
        if a and dt > 0:
            for k, w in (("tok_raus", "raus_s"), ("tok_rein", "rein_s")):
                x = _delta(a, v, k)
                r[w] = round(x / dt, 1) if x is not None else None
        q, t = _delta(f, v, "prefix_fragen"), _delta(f, v, "prefix_treffer")
        r["prefix_pct"] = round(100 * t / q, 1) if q and t is not None else None
        e, an, sch = _delta(f, v, "mtp_entwurf"), _delta(f, v, "mtp_an"), _delta(f, v, "mtp_schritte")
        r["mtp_pct"] = round(100 * an / e, 1) if e and an is not None else None
        r["mtp_je_schritt"] = round(1 + an / sch, 2) if sch and an is not None else None
        for k, q_ in (("ttft", 0.5), ("ttft", 0.95), ("itl", 0.5)):
            r[f"{k}_p{int(q_ * 100)}"] = _quantil((f or {}).get(k), v.get(k), q_)
        r["fertig_5m"] = _delta(f, v, "fertig")
        out[d] = r
    for d, x in neu["dienste"].items():
        a = fenster[0]["dienste"].get(d) if fenster else None
        out.setdefault(d, {})["anfragen_5m"] = _delta(a, x, "anfragen")
    return out


def _punkt(now, m, raten, gpu, rb):
    llm = raten.get("llm") or {}
    return {"t": int(now), "tok": llm.get("raus_s"), "pre": llm.get("rein_s"),
            "gpu": (gpu or {}).get("util"), "w": (gpu or {}).get("power"), "temp": (gpu or {}).get("temp"),
            "takt": (gpu or {}).get("clock"),
            "laufen": sum(x.get("laufen") or 0 for x in m["dienste"].values()),
            "warten": sum(x.get("warten") or 0 for x in m["dienste"].values()),
            "kv": (m["vllm"].get("llm") or {}).get("kv"), "frei": rb}


def _verdichten(punkte, t):
    """One point of many: the mean of each number, the highest of „warten“ (a short queue must not vanish)."""
    out = {"t": int(t)}
    for k in ("tok", "pre", "gpu", "w", "temp", "takt", "laufen", "warten", "kv", "frei"):
        vs = [p[k] for p in punkte if isinstance(p.get(k), (int, float))]
        out[k] = (max(vs) if k == "warten" else round(sum(vs) / len(vs), 1)) if vs else None
    return out


def _laden():
    d = read_json(DATEI, {}) or {}
    for key, q in (("tag", _tag), ("woche", _woche)):
        for p in (d.get(key) or [])[-q.maxlen:] if isinstance(d.get(key), list) else []:
            if isinstance(p, dict) and _zahl(p.get("t"), 1e11):
                q.append({k: (p.get(k) if _zahl(p.get(k), 1e9) is not None else None)
                          for k in ("t", "tok", "pre", "gpu", "w", "temp", "takt", "laufen", "warten", "kv", "frei")})
    for e in (d.get("ereignisse") or [])[-EREIGNISSE:] if isinstance(d.get("ereignisse"), list) else []:
        if isinstance(e, dict) and e.get("w") in EREIGNIS_NAMEN and (e.get("d") in DIENSTE or e.get("d") == ""
                                                                     or e.get("d") in DROSSEL_NAMEN) and _zahl(e.get("t"), 1e11):
            _ereignisse.append({"t": e["t"], "w": e["w"], "d": e["d"], "n": e.get("n") if _zahl(e.get("n"), 1e9) is not None else None})


def sichern():
    with _lock:
        d = {"tag": list(_tag), "woche": list(_woche), "ereignisse": list(_ereignisse)}
    try:
        write_json(DATEI, d)
    except OSError as e:
        print("rechner: verlauf nicht gesichert", type(e).__name__, flush=True)


def probe(gpu=None, cfg=None, now=None, mono=None):
    """One round of the sampler (every 3 s); False without a look (model computer silent)."""
    cfg = load_config() if cfg is None else cfg
    now = time.time() if now is None else now
    mono = time.monotonic() if mono is None else mono
    with _lock:
        if not _stand["geladen"]:
            _stand["geladen"] = True
            _laden()
    try:
        m = _messen(gpu, cfg)
    except Exception as e:
        print("rechner: genau fehler", type(e).__name__, flush=True)
        m = None
    if m is None:
        return False
    frei = m["mem"]["frei"]
    with _lock:
        alt, t_alt = _stand["letzt"], _stand["t"]
        fenster = _stand["fenster"]
        while fenster and mono - fenster[0]["mono"] > FENSTER_S:
            fenster.popleft()
        raten = _raten(alt, m, (mono - t_alt) if t_alt is not None else 0, fenster)
        _ereignisse_ableiten(m, now)
        fenster.append(dict(m, mono=mono))
        _stand.update(letzt=m, t=mono, raten=raten, gpu=gpu if isinstance(gpu, dict) else None)
        p = _punkt(now, m, raten, gpu if isinstance(gpu, dict) else None, frei)
        _kurz.append(p)
        for key, q, schritt in (("tag", _tag, TAG_S), ("woche", _woche, WOCHE_S)):
            fach = int(now // schritt)
            sammel = _stand.get(key)
            if sammel is None or sammel[0] != fach:
                if sammel is not None and sammel[1]:
                    q.append(_verdichten(sammel[1], sammel[0] * schritt))
                _stand[key] = (fach, [p])
            else:
                sammel[1].append(p)
        faellig = mono - _stand["gesichert"] >= SICHERN_S
        if faellig:
            _stand["gesichert"] = mono
    if faellig:
        sichern()
    return True


def _modell(d, cfg):
    """The model's name (de, en) from the catalog, else the last part of its repository; "" when none."""
    _, _, sec, key = DIENSTE[d]
    mid = str((cfg.get(sec) or {}).get(key) or "")
    if not mid:
        return ("", "")
    import modelle
    try:
        kat = modelle.katalog()
    except Exception:
        kat = {}
    e = kat.get(mid) or modelle.zum_repo(mid) if kat else None
    if d in ("bild", "musik"):
        try:
            e = modelle.zur_variante({"bild": "bild", "musik": "musik"}[d], mid)
        except Exception:
            e = None
    n = (e or {}).get("name") if isinstance(e, dict) else None
    if isinstance(n, dict):
        return (str(n.get("de", ""))[:60], str(n.get("en", ""))[:60])
    kurz = mid.split("/")[-1][:60]
    return (kurz, kurz)


def _kontext(cfg):
    import modelle
    try:
        e = modelle.eintrag(str((cfg.get("llm") or {}).get("modell") or ""))
        return _zahl(e.get("kontext"), 1e8)
    except Exception:
        return None


def hinweise(m, raten):
    """The notes on top of the page now (fixed rules), each a key of HINWEISE."""
    if not m:
        return []
    out = []
    if ((m["vllm"].get("llm") or {}).get("kv") or 0) >= KV_VOLL:
        out.append("kv_voll")
    if any(x["z"] == "wartet" and x["s"] >= WARTEN_LANG_S for x in m["anfragen"]):
        out.append("wartet_lang")
    if any(w in DROSSEL_SCHLIMM for w in m["gpu"].get("drossel") or []):
        out.append("drosselt")
    if (m.get("kanarie") or {}).get("status") == "error":
        out.append("kanarie")
    if any(x["zustand"] == "fehler" for x in m["dienste"].values()):
        out.append("fehler")
    if (m["dienste"].get("llm") or {}).get("zustand") == "haengt":
        out.append("haengt")
    if _stand["ohne"] >= OHNE_AUFTRAG_N:
        out.append("ohne_auftrag")
    if (m.get("nvrm") or {}).get("h1"):
        out.append("gpu_speicher")
    return out


def ansicht(zeit="20m", cfg=None):
    """What the page shows (numbers, fixed words and their names; no content)."""
    cfg = load_config() if cfg is None else cfg
    zeit = zeit if zeit in ZEITEN else "20m"
    with _lock:
        m, raten, gpu = _stand["letzt"], dict(_stand["raten"]), _stand.get("gpu")
        kurve = list({"20m": _kurz, "24h": _tag, "7d": _woche}[zeit])
        ereignisse = list(_ereignisse)[-40:][::-1]
    if m is None:
        return {"da": False, "remote": steuer.remote(cfg)}
    dienste = []
    for d, (de, en, _, _) in DIENSTE.items():
        x = m["dienste"].get(d)
        if x is None:
            continue
        md = _modell(d, cfg)
        dienste.append(dict(x, id=d, name=de, en=en, modell=md[0], modell_en=md[1],
                            zustand_name=ZUSTAND_NAMEN[x["zustand"]][0], zustand_en=ZUSTAND_NAMEN[x["zustand"]][1],
                            **{k: v for k, v in (raten.get(d) or {}).items() if k == "anfragen_5m"}))
    anfragen = [dict(x, dienst=DIENSTE[x["d"]][0], dienst_en=DIENSTE[x["d"]][1], art_name=ARTEN_NAMEN.get(x["art"], ARTEN_NAMEN[""])[0],
                     art_en=ARTEN_NAMEN.get(x["art"], ARTEN_NAMEN[""])[1], stufe_name=STUFEN[x["stufe"]][0], stufe_en=STUFEN[x["stufe"]][1],
                     tok_s=round(x["raus"] / x["s"], 1) if x["z"] == "laeuft" and x.get("raus") and x["s"] >= 0.5 else None)
                for x in m["anfragen"]]
    innen = {}
    for d, v in m["vllm"].items():
        innen[d] = dict({k: v.get(k) for k in ("laufen", "warten", "kv", "kv_tokens", "verdraengt")}, **(raten.get(d) or {}),
                        name=DIENSTE[d][0], en=DIENSTE[d][1])
    if "llm" in innen:
        innen["llm"]["kontext"] = _kontext(cfg)
        innen["llm"]["kanarie"] = m.get("kanarie")
    g = dict(m["gpu"], **{k: (gpu or {}).get(k) for k in ("name", "util", "temp", "power", "clock", "grenze")})
    g["drossel_namen"] = [list(DROSSEL_NAMEN[w]) for w in g.get("drossel") or [] if w in DROSSEL_NAMEN]
    g["nvrm"] = m.get("nvrm")
    fertig = [dict(x, art_name=ARTEN_NAMEN.get(x["art"], ARTEN_NAMEN[""])[0], art_en=ARTEN_NAMEN.get(x["art"], ARTEN_NAMEN[""])[1],
                   stufe_name=STUFEN[x["stufe"]][0], stufe_en=STUFEN[x["stufe"]][1],
                   ergebnis_name=ERGEBNIS_NAMEN[x["ergebnis"]][0], ergebnis_en=ERGEBNIS_NAMEN[x["ergebnis"]][1])
              for x in reversed(m.get("fertig") or [])]
    speicher = [{"id": i, "name": rechner.DIENST_NAMEN.get(i, (i, i))[0], "en": rechner.DIENST_NAMEN.get(i, (i, i))[1],
                 "gib": v} for i, v in m["speicher"].items()]
    ev = [dict(e, name=list(EREIGNIS_NAMEN[e["w"]]),
               dienst=list(DIENSTE[e["d"]][:2]) if e["d"] in DIENSTE else list(DROSSEL_NAMEN.get(e["d"], ("", ""))))
          for e in ereignisse]
    hw = hinweise(m, raten)
    return {"da": True, "remote": steuer.remote(cfg), "zeit": zeit, "dienste": dienste, "anfragen": anfragen,
            "innen": innen, "gpu": g, "speicher": speicher,
            "mem": dict(m["mem"]),
            "jetzt": {"laufen": sum(x.get("laufen") or 0 for x in m["dienste"].values()),
                      "plaetze": sum(x.get("plaetze") or 0 for x in m["dienste"].values()),
                      "warten": sum(x.get("warten") or 0 for x in m["dienste"].values()),
                      "warten_max_s": max([x["s"] for x in m["anfragen"] if x["z"] == "wartet"] or [0]),
                      "tok_s": (raten.get("llm") or {}).get("raus_s")},
            "kurve": kurve, "ereignisse": ev, "fertig": fertig, "hinweise": [{"id": h, "text": HINWEISE[h][0], "en": HINWEISE[h][1]} for h in hw]}


def fuer_live(nur_llm=False):
    """Zustand → Live and the Steuerzentrale: requests running and waiting (all services, or only the language
    model's), tokens per second; {} without a look."""
    with _lock:
        m, raten = _stand["letzt"], _stand["raten"]
    if m is None:
        return {}
    d = [x for k, x in m["dienste"].items() if not nur_llm or k == "llm"]
    return {"laufen": sum(x.get("laufen") or 0 for x in d), "warten": sum(x.get("warten") or 0 for x in d),
            "tok_s": (raten.get("llm") or {}).get("raus_s"), "kv": (m["vllm"].get("llm") or {}).get("kv")}
