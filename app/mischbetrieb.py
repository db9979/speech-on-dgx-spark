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
KLEIN = {"asr": "qwen3-asr-0.6b", "tts": "qwen3-tts-0.6b-base"}
# engine.sh roles that never start while it is on
GESPERRT = ("llm", "sehen", "helfer", "einbetten", "nachsortieren", "design", "klon")
# kinds of modelle.py that neither switch nor are measured while it is on
ARTEN = ("llm", "sehen", "helfer", "einbetten", "nachsortieren", "bild", "musik")
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
    wechsel = [(art, mid) for art, mid in KLEIN.items() if sprach[art] in kat and mid in kat
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
    write_json(path or DATEI, dict(d, an=False, bis=int(time.time())), indent=1, mode=0o600)
    sprach = d.get("sprach") or {}
    wechsel = [(art, sprach[art]) for art in KLEIN if sprach.get(art) and sprach[art] in kat
               and modelle.jetzt_id(art, cfg, kat) != sprach[art]]
    print(f"modelle: mischbetrieb aus, {len(wechsel)} wechsel", flush=True)
    return wechsel


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
