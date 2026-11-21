#!/usr/bin/env python3
"""Mischbetrieb (plan alzeo-mischbetrieb M2, Dominik 2026-11-18 „1a 2a 3a“): the DGX Spark serves another project
(Alzeo, his Qwen project), and the Spark keeps only Hören and Sprechen there, with the small models, so the other
project has the memory. The assistant on the panel computer goes on: its language model comes from a foreign model
service (fremdmodell.py), Bilder and Musik are off, and what is missing says so (wartung.paused, features.READY).

    sudo speech-spark mischbetrieb an       the own language model (with image understanding, helper, embeddings),
                                            Bilder, Musik, VoiceDesign and the clone engine off, their units stopped
                                            and disabled; Hören and Sprechen switch to the small models (KLEIN)
    sudo speech-spark mischbetrieb aus      everything back exactly as it was before „an“ (STATE/mischbetrieb.json)
    sudo speech-spark mischbetrieb status

Fixed rules (the shell's root part only runs what this module prints, words of fixed lists):
- „an“ remembers the values it changes (AUS) and the catalog ids of Hören and Sprechen before it; „aus“ restores exactly
  those, never anything else. A second „an“ changes nothing.
- While it is on, engine.sh starts none of the GESPERRT roles (also not after an update, a reboot or a wish of the
  console), and modelle.wechsel_pruefen refuses a switch or a measurement of the ARTEN with the word „mischbetrieb“.
- The Wärter's status says „mischbetrieb“ (tarswart.status); the panel computer reads it (steuer.mischbetrieb).
- Speicher-Wache (M3, wache): the other project's engines take 25-40 GB more than they count while they start; on unified
  memory a box without free memory freezes. So every WACHE_S seconds the Wärter looks: while a unit of the other project
  (FREMD_EINHEITEN) starts (activating, or active for less than START_S) or less than FREI_MIN GiB are free, Hören's
  and Sprechen's engines (EIGENE) stop and give their memory back („frei“, the panel computer hears with Parakeet and
  shows the answers as text); once nothing starts and ZURUECK_GIB GiB are free RUHIG_N looks in a row, they start
  again. It only starts what it stopped itself.

Only the standard library and common; one file STATE/mischbetrieb.json (0600). Log lines start with "modelle:" and
hold fixed words and catalog ids only.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_PATH, OWN_LLM_UNITS, ON_DEMAND_UNITS, STATE, UNITS, read_json, write_json  # noqa: E402

DATEI = os.path.join(STATE, "mischbetrieb.json")
# the values „an“ sets to False: section -> keys (the own language model takes its roles with it: modelle.ALLEIN_ARTEN
# and the LLM-Tor answer only with llm.enabled; the image understanding and the helper start only through the LLM-Tor)
AUS = {"llm": ("enabled",), "image": ("enabled",), "music": ("enabled",), "tts": ("voicedesign_enabled", "klon_enabled")}
# Hören and Sprechen in Mischbetrieb (Dominik „3a“: the small ones, about 7 GiB together, more room for the other project)
KLEIN = {"asr": "qwen3-asr-0.6b", "tts": "qwen3-tts-0.6b"}   # entries install.sh offers (field "wahl")
# a Base main voice (own voices cloned from samples, tars since 2026-11) stays a Base one: the built-in voices of the
# CustomVoice model do not know its voice names (V01.1.529: every sentence and speaker file failed with „voice“)
KLEIN_BASE = {"tts": "qwen3-tts-0.6b-base"}


def klein(art, jetzt, kat):
    """The small model of a kind for the model running now: the Base one when a Base one runs."""
    if art in KLEIN_BASE and (kat.get(jetzt) or {}).get("rolle") == "klonen":
        return KLEIN_BASE[art]
    return KLEIN[art]
# engine.sh roles that never start while it is on
GESPERRT = ("llm", "sehen", "helfer", "einbetten", "nachsortieren", "design", "klon")
# kinds of modelle.py that neither switch nor are measured while it is on
ARTEN = ("llm", "sehen", "helfer", "einbetten", "nachsortieren", "bild", "musik")
# Speicher-Wache: the other project's units (Alzeo's systemd units, by the names its lane registry gives them: data only,
# never its code), our engines, the thresholds
FREMD_EINHEITEN = ("qwen38-sglang", "qwen38-flash", "qwen38-image", "qwen38-video", "qwen38-kolibri", "qwen38-nemotron",
                   "qwen38-nemotron-super", "qwen38-flash-local", "qwen38-ornith-122b", "qwen38-flash-unsloth",
                   "qwen38-keepalive")
EIGENE = ("asr-engine", "tts-engine")     # common.UNITS keys; the front ends speech-spark-asr/-tts stay
WACHE_S = 5            # seconds between two looks
FREI_MIN = 6           # GiB available: below, our engines give their memory back
START_S = 900          # a unit of the other project active for less than this many seconds still starts
ZURUECK_GIB = 18       # GiB available before ours load again (about 7 GiB for them and a reserve)
RUHIG_N = 6            # looks in a row with nothing starting and enough free memory
BEWEGT = ("activating", "deactivating", "reloading")
# the units „an“ stops and disables (the language model's Docker container is part of speech-spark-llm)
EINHEITEN = tuple(OWN_LLM_UNITS.values()) + ("speech-spark-llm-docker", ON_DEMAND_UNITS["bild"],
                                            ON_DEMAND_UNITS["musik"], UNITS["tts-design"], UNITS["tts-klon"])


def stand(path=None):
    d = read_json(path or DATEI, {})
    return d if isinstance(d, dict) else {}


def ist_an(path=None):
    return stand(path).get("an") is True


def _roh():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def an(cfg, kat, path=None, roh=None, schreib=None, now=None):
    """Switches it on. Returns the switches Hören and Sprechen still need ([(art, id)]), [] when already on."""
    import modelle
    if ist_an(path):
        print("modelle: mischbetrieb an schon", flush=True)
        return []
    raw = _roh() if roh is None else roh
    vorher = {sec: {k: (raw.get(sec) or {}).get(k) for k in keys} for sec, keys in AUS.items()}
    sprach = {art: modelle.jetzt_id(art, cfg, kat) for art in KLEIN}
    for sec, keys in AUS.items():
        raw[sec] = dict(raw.get(sec) or {}, **{k: False for k in keys})
    write_json(path or DATEI, {"an": True, "seit": int(time.time() if now is None else now), "vorher": vorher,
                               "sprach": sprach}, indent=1, mode=0o600)
    (schreib or modelle._schreib)(raw)
    ziel = {art: klein(art, sprach[art], kat) for art in KLEIN}
    wechsel = [(art, mid) for art, mid in ziel.items() if sprach[art] in kat and mid in kat
               and kat[sprach[art]].get("need_gib", 0) > kat[mid].get("need_gib", 0)]   # never to a bigger one
    print(f"modelle: mischbetrieb an, {len(wechsel)} wechsel", flush=True)
    return wechsel


def aus(cfg, kat, path=None, roh=None, schreib=None):
    """Switches it off: the remembered values back. Returns the switches back ([(art, id)]), [] when it was off."""
    import modelle
    d = stand(path)
    if d.get("an") is not True:
        print("modelle: mischbetrieb aus schon", flush=True)
        return []
    raw = _roh() if roh is None else roh
    for sec, keys in AUS.items():
        alt = (d.get("vorher") or {}).get(sec) or {}
        sek = dict(raw.get(sec) or {})
        for k in keys:
            if isinstance(alt.get(k), bool):
                sek[k] = alt[k]
            else:
                sek.pop(k, None)      # it was not set before: the shipped default counts again
        raw[sec] = sek
    (schreib or modelle._schreib)(raw)
    write_json(path or DATEI, dict(d, an=False, frei=False, bis=int(time.time())), indent=1, mode=0o600)
    sprach = d.get("sprach") or {}
    wechsel = [(art, sprach[art]) for art in KLEIN if sprach.get(art) and sprach[art] in kat
               and modelle.jetzt_id(art, cfg, kat) != sprach[art]]
    print(f"modelle: mischbetrieb aus, {len(wechsel)} wechsel", flush=True)
    return wechsel


def einstellen_merken(daten, path=None):
    """The Wärter's „einstellen“ while it is on (V01.1.528): the panel computer sends its speech settings every minute,
    VoiceDesign and the clone engine with them (tts.voicedesign_enabled, klon_enabled are no model choice), and they
    came back on tars while it was on. Such a key of AUS is kept as the value „aus“ restores (vorher) instead; returns
    the settings without them."""
    d = stand(path)
    if d.get("an") is not True or not isinstance(daten, dict):
        return daten
    vorher, rest, n = dict(d.get("vorher") or {}), {}, 0
    for sec, vals in daten.items():
        keys = AUS.get(sec, ())
        if isinstance(vals, dict):
            for k in keys:
                if isinstance(vals.get(k), bool):
                    vorher[sec] = dict(vorher.get(sec) or {}, **{k: vals[k]})
                    n += 1
            vals = {k: v for k, v in vals.items() if k not in keys}
        rest[sec] = vals
    if n:
        write_json(path or DATEI, dict(d, vorher=vorher), indent=1, mode=0o600)
    return rest


def sicht(cfg, path=None):
    """The configuration as the panel computer counts it while it is on: the keys of AUS with the values „aus“ restores,
    so the hash of the speech settings (common.model_settings_hash) matches the panel's and it stops sending them."""
    d = stand(path)
    if d.get("an") is not True:
        return cfg
    out = json.loads(json.dumps(cfg))
    from common import shipped
    for sec, keys in AUS.items():
        alt = (d.get("vorher") or {}).get(sec) or {}
        for k in keys:
            if sec in out and k in out[sec]:
                v = alt.get(k)
                out[sec][k] = v if isinstance(v, bool) else (shipped().get(sec) or {}).get(k, out[sec][k])
    return out


def startet(einheiten):
    """True while a unit of the other project starts: {unit: einheiten_stand entry}."""
    return any(isinstance(u, dict) and u.get("da") is not False
               and (u.get("state") in BEWEGT or (u.get("state") == "active" and isinstance(u.get("seit"), (int, float))
                                                  and u["seit"] < START_S))
               for u in (einheiten or {}).values())


def wache(frei_gib, einheiten, frei, ruhig):
    """One look (fixed rule): returns (action, ruhig) with action "freigeben", "zurueck" or None. frei: our engines are
    stopped by the guard now; ruhig: good looks in a row so far. Unknown memory (None) never brings them back."""
    if not frei:
        if startet(einheiten) or (frei_gib is not None and frei_gib < FREI_MIN):
            return "freigeben", 0
        return None, 0
    gut = not startet(einheiten) and frei_gib is not None and frei_gib >= ZURUECK_GIB
    ruhig = ruhig + 1 if gut else 0
    return ("zurueck", 0) if ruhig >= RUHIG_N else (None, ruhig)


def stimme_frei(path=None):
    """The guard has stopped Hören's and Sprechen's engines now (the Wärter's status „mischbetrieb_frei“)."""
    d = stand(path)
    return d.get("an") is True and d.get("frei") is True


def wache_lauf(einheit, stand_holen, mem, stop, path=None, sleep=time.sleep):
    """The Wärter's thread: every WACHE_S seconds one look while Mischbetrieb is on. einheit(action, teil): the Wärter's
    systemctl; stand_holen(units): common.einheiten_stand; mem(): GiB available. Logs one line per action."""
    ruhig = 0
    while not stop.is_set():
        sleep(WACHE_S)
        try:
            d = stand(path)
            if d.get("an") is not True:
                ruhig = 0
                continue
            try:
                frei_gib = mem()
            except OSError:
                frei_gib = None
            aktion, ruhig = wache(frei_gib, stand_holen(list(FREMD_EINHEITEN)), d.get("frei") is True,
                                  ruhig)
            if aktion:
                ok = all((einheit("stop" if aktion == "freigeben" else "start", t) or {}).get("ok") for t in EIGENE)
                write_json(path or DATEI, dict(stand(path), frei=aktion == "freigeben"), indent=1, mode=0o600)
                print(f"modelle: mischbetrieb wache {aktion} {'ok' if ok else 'fehler'} "
                      f"{-1 if frei_gib is None else round(frei_gib)} gib frei", flush=True)
        except Exception as e:   # noqa: BLE001 - the guard goes on
            print("modelle: mischbetrieb wache fehler", type(e).__name__, flush=True)


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "sperrt":            # engine.sh: exit 0 = this role does not start now
        return 0 if len(argv) == 2 and argv[1] in GESPERRT and ist_an() else 1
    if cmd == "einheiten":
        print("\n".join(EINHEITEN))
        return 0
    if cmd == "status":
        d = stand()
        print("Mischbetrieb: " + ("an seit " + time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("seit") or 0))
                                  if d.get("an") is True else "aus"))
        return 0
    if cmd in ("an", "aus"):
        import modelle
        from common import load_config
        cfg, kat = load_config(), modelle.katalog()
        for art, mid in (an if cmd == "an" else aus)(cfg, kat):
            print(f"wechsel {art} {mid}")
        return 0
    print("mischbetrieb.py an|aus|status|sperrt <rolle>|einheiten", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
