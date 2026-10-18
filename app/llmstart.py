"""What the own language model is doing while it switches, restarts or loads (Dominik 2026-10-18 „1a 2a 3a 4a 5a“:
„beim wechseln, laden der llm muss irgendwo ersichtlich sein was gerade passiert“).

One source for the steps: speech-spark.sh (switch, „Lange Gespräche“) writes each step with `llmstart.py schritt`,
modelle.rundlauf the test question's parts, `llmstart.py ende` the result. A plain restart of speech-spark-llm (an
update, a crash) has no file: `lesen` sees it from the engine's state file (engine.sh) and its /health. While the new
engine starts, the phase comes from its journal, matched against fixed patterns to a fixed word (never a line of it).
How long a start takes is kept per model (`ZEITEN`) for the next time; before the first one, the measurement's
loading time. Read by the Wärter (tarswart.modelle_daten), the panel (modellseite.lage: Zustand → Modelle, banner,
Live, the sentence in the chat) and the apps; only fixed words and numbers, never text from the engine.

Command line (as the panel's service user): schritt <vorgang> <1-6> [<id>] · teil <wort> · ende ok|zurueck [<wort>]."""
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, read_json, write_json  # noqa: E402

DATEI = os.path.join(STATE, "llm-start.json")          # the running (or last) switch or restart, steps and times
ZEITEN = os.path.join(STATE, "llm-startzeiten.json")   # per model id the seconds its last start took
ENGINE = os.path.join(STATE, "speech-spark-llm.json")  # engine.sh's state of speech-spark-llm (loading, blocked …)
# (word, de, en); a switch goes through all six, „Lange Gespräche“ and a restart start at „anhalten“ or „starten“
SCHRITTE = (("pruefen", "Prüfen: Katalog, fester Stand, Speicher", "Checking: catalog, pinned commit, memory"),
            ("dateien", "Dateien laden und gegen Prüfsummen prüfen", "Fetching files and checking their hashes"),
            ("anhalten", "Altes Modell anhalten", "Stopping the old model"),
            ("starten", "Neues Modell startet", "New model starting"),
            ("probe", "Probefrage", "Test question"),
            ("fertig", "Umgeschaltet", "Switched"))
VORGAENGE = {"wechsel": ("Sprachmodell wechselt", "Language model switching"),
             "platz": ("Sprachmodell startet mit neuem Gesprächsspeicher", "Language model restarting with a new context store"),
             "neustart": ("Sprachmodell startet neu", "Language model restarting")}
# the engine's phases while it starts, in their order: (word, de, en, pattern of a journal line that begins it)
TEILE = (("gewichte", "Gewichte laden", "loading weights", None),
         ("kernel", "Kernel übersetzen", "compiling kernels", re.compile(r"Loading weights took|Model loading took")),
         ("speicher", "Gesprächsspeicher einrichten", "setting up the context store",
          re.compile(r"Available KV cache memory|GPU KV cache size|KV cache size")),
         ("bereit", "bereit", "ready", re.compile(r"Application startup complete")))
# the test question's parts (modelle.rundlauf) and the fixed words a switch ends with
PROBE = ("satz", "werkzeug", "bild", "systemone")
ERGEBNIS = ("ok", "zurueck")
GRUND = re.compile(r"^[a-z][a-z ]{1,23}$")              # a rundlauf word (httperror, nicht bereit, satz …)
START = re.compile(r"Start(ed|ing) speech-spark-llm")     # systemd's line: the journal after it is this start's
ZEIGEN_S = 15 * 60          # the result stays on the page and the banner this long after the end
ALT_S = 3 * 3600            # a file whose step has not moved for this long is stale (a unit that was killed)
ENGINE_ZUSTAND = {"blocked": "speicher", "error": "fehler"}   # engine.sh's state -> the fixed word shown


def _jetzt(now):
    return time.time() if now is None else now


def schritt(vorgang, n, ziel="", now=None, path=DATEI):
    """Step n (1-6) of a switch or restart begins; step 1 or a new vorgang starts the file afresh."""
    if vorgang not in VORGAENGE or not 1 <= int(n) <= len(SCHRITTE) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,47}|", ziel):
        raise ValueError("schritt")
    t = int(_jetzt(now))
    d = read_json(path, {})
    if int(n) == 1 or d.get("vorgang") != vorgang or d.get("ende"):
        d = {"vorgang": vorgang, "ziel": ziel, "seit": {}, "ende": 0, "ergebnis": "", "grund": "", "teil": ""}
    if ziel:
        d["ziel"] = ziel
    d["schritt"] = int(n)
    d["seit"][str(int(n))] = t
    d["teil"] = ""
    write_json(path, d, indent=1)


def teil(wort, path=DATEI):
    """A part of the test question passed (modelle.rundlauf), shown under step 5."""
    d = read_json(path, {})
    if wort not in PROBE or not d or d.get("ende"):
        return
    d["teil"] = wort
    write_json(path, d, indent=1)


def stufe(wort, grund="", now=None, path=DATEI):
    """modelle.rundlauf's progress: "probe" (the engine answers) moves a running step 4 on to 5, a part of PROBE is
    noted under it, "fehler" keeps rundlauf's word for `ende`. Nothing when no switch runs (a rundlauf of its own,
    `speech-spark modelle llm uebernehmen`)."""
    d = read_json(path, {})
    if not d or d.get("ende") or d.get("vorgang") not in VORGAENGE:
        return
    if wort == "probe" and d.get("schritt") == 4:
        schritt(d["vorgang"], 5, now=now, path=path)
    elif wort in PROBE:
        teil(wort, path)
    elif wort == "fehler":
        d["grund"] = grund if GRUND.match(str(grund)) else "fehler"
        write_json(path, d, indent=1)


def ende(ergebnis, grund="", now=None, path=DATEI, zeiten=ZEITEN):
    """The switch ended: "ok" (switched) or "zurueck" (back to the model before, with rundlauf's word). A start that
    reached the test question keeps its duration for the next time."""
    if ergebnis not in ERGEBNIS:
        raise ValueError("ende")
    grund = grund if not grund or GRUND.match(grund) else "fehler"
    t = int(_jetzt(now))
    d = read_json(path, {})
    if not d or d.get("ende"):
        return
    grund = grund or (d.get("grund", "") if ergebnis == "zurueck" else "")
    if ergebnis == "ok":
        d["schritt"] = len(SCHRITTE)
        d["seit"][str(len(SCHRITTE))] = t
    seit = d.get("seit", {})
    if d.get("ziel") and "4" in seit and "5" in seit:
        z = read_json(zeiten, {})
        z[d["ziel"]] = max(1, int(seit["5"]) - int(seit["4"]))
        write_json(zeiten, z, indent=1)
    d.update(ende=t, ergebnis=ergebnis, grund=grund)
    write_json(path, d, indent=1)


def phase(journal_text):
    """The engine's phase from its journal since the last start: the last fixed word whose line appeared."""
    text = str(journal_text)
    starts = [m.end() for m in START.finditer(text)]
    text = text[starts[-1]:] if starts else text
    word = TEILE[0][0]
    for w, _, _, pat in TEILE[1:]:
        if pat.search(text):
            word = w
    return word


def erwartet(ziel, messung=None, zeiten=ZEITEN):
    """Seconds a start of this model is expected to take: its last start, else the measurement's loading time."""
    s = read_json(zeiten, {}).get(ziel)
    if isinstance(s, int) and s > 0:
        return s
    r = ((messung or {}).get("modelle") or {}).get(ziel) or {}
    return int(r["laden_s"]) if isinstance(r.get("laden_s"), (int, float)) and r["laden_s"] > 0 else 0


def lesen(gesund, journal_text="", messung=None, modell="", now=None, path=DATEI, zeiten=ZEITEN, engine=ENGINE):
    """What the page, the banner and the chat show: None when nothing runs (and no result is still shown), else
    {vorgang, ziel, schritt, n, seit, dauer_s, schritt_s, erwartet_s, teil, ende, ergebnis, grund}. gesund: the
    engine's /health answers; journal_text: its journal lines or a function giving them (only matched against TEILE,
    read only while step 4 runs); modell: the configured id (a plain restart)."""
    t = int(_jetzt(now))
    d = read_json(path, {})
    if d.get("vorgang") in VORGAENGE and isinstance(d.get("seit"), dict) and d["seit"]:
        d["ziel"] = d.get("ziel") or modell
        letzt = max(int(v) for v in d["seit"].values())
        if d.get("ende"):
            # the result for a while; while the engine starts again after it (back to the model before), that start
            if t - int(d["ende"]) <= ZEIGEN_S and (gesund or read_json(engine, {}).get("status") != "loading"):
                return _zeile(d, t, messung, zeiten, "")
            d = {}
        elif t - letzt > ALT_S:
            d = {}
        else:
            return _zeile(d, t, messung, zeiten, phase(_text(journal_text)) if d.get("schritt") == 4 else "")
    else:
        d = {}
    e = read_json(engine, {})
    if gesund or e.get("status") not in ("loading", *ENGINE_ZUSTAND):
        return None
    try:
        seit = int(datetime.fromisoformat(str(e.get("time", ""))).timestamp())
    except ValueError:
        seit = t
    d = {"vorgang": "neustart", "ziel": modell, "schritt": 4, "seit": {"4": seit}, "ende": 0, "ergebnis": "",
         "grund": ENGINE_ZUSTAND.get(e.get("status"), ""), "teil": ""}
    return _zeile(d, t, messung, zeiten, phase(_text(journal_text)) if e.get("status") == "loading" else "")


def _text(journal_text):
    return journal_text() if callable(journal_text) else journal_text


def hier(cfg, messung=None):
    """`lesen` on the computer the language model runs on: its /health, its journal only when it is needed."""
    from common import journal
    c = cfg.get("llm", {})
    if not c.get("enabled"):
        return None
    port = c.get("engine_port", 31016)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/health", timeout=2) as r:
            gesund = r.status == 200
    except (OSError, ValueError):
        gesund = False
    return lesen(gesund, lambda: journal("speech-spark-llm", 400), messung, str(c.get("modell") or ""))


def _zeile(d, t, messung, zeiten, phase_wort):
    n = int(d.get("schritt", 1))
    seit = {int(k): int(v) for k, v in d["seit"].items()}
    beginn = min(seit.values())
    ende_t = int(d.get("ende") or 0)
    return {"vorgang": d["vorgang"], "ziel": d.get("ziel", ""), "schritt": SCHRITTE[n - 1][0], "n": n,
            "seit": {SCHRITTE[k - 1][0]: v - beginn for k, v in sorted(seit.items())},
            "dauer_s": (ende_t or t) - beginn, "schritt_s": (ende_t or t) - seit.get(n, beginn),
            "erwartet_s": erwartet(d.get("ziel", ""), messung, zeiten) if d.get("ziel") else 0,
            "teil": d.get("teil") or phase_wort, "ende": bool(ende_t), "ergebnis": d.get("ergebnis", ""),
            "grund": d.get("grund", "")}


def pruefen(x):
    """The panel's check of what the model computer sent (steuer.modelle): the shape `lesen` gives, else None."""
    if x is None:
        return None
    worte = {w for w, *_ in SCHRITTE}
    try:
        ok = (isinstance(x, dict) and x["vorgang"] in VORGAENGE and x["schritt"] in worte
              and isinstance(x["n"], int) and 1 <= x["n"] <= len(SCHRITTE)
              and isinstance(x["seit"], dict) and set(x["seit"]) <= worte
              and all(isinstance(v, int) and 0 <= v < 10**7 for v in x["seit"].values())
              and all(isinstance(x[k], int) and 0 <= x[k] < 10**7 for k in ("dauer_s", "schritt_s", "erwartet_s"))
              and x["teil"] in ("", *PROBE, *(w for w, *_ in TEILE)) and isinstance(x["ende"], bool)
              and x["ergebnis"] in ("", *ERGEBNIS) and (x["grund"] == "" or GRUND.match(x["grund"]))
              and isinstance(x["ziel"], str) and re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,47}|", x["ziel"]))
    except (KeyError, TypeError):
        ok = False
    return {k: x[k] for k in ("vorgang", "ziel", "schritt", "n", "seit", "dauer_s", "schritt_s", "erwartet_s", "teil",
                              "ende", "ergebnis", "grund")} if ok else None


def rest_min(x):
    """Minutes still expected (at least 1), 0 when nothing is known."""
    if not x or x["ende"] or not x["erwartet_s"]:
        return 0
    vor = x["seit"].get("starten")
    lauf = x["dauer_s"] - vor if vor is not None and x["n"] >= 4 else 0
    return max(1, -(-(x["erwartet_s"] - lauf + (60 if x["n"] <= 4 else 30)) // 60))


def satz(x, en=False, misst=False):
    """The sentence the chat says when the language model does not answer while it starts or is measured (Dominik
    „3a“); "" when neither (the chat keeps its own sentence)."""
    if not x or x["ende"]:
        if misst:
            return ("My language model is being measured right now and is back afterwards. Please ask again then." if en
                    else "Mein Sprachmodell wird gerade gemessen und ist danach wieder da. Frag mich dann bitte noch einmal.")
        return ""
    m = rest_min(x)
    if x["grund"] in ("speicher", "fehler"):
        return ("My language model cannot start right now. The admin sees why under Status → Models." if en else
                "Mein Sprachmodell kann gerade nicht starten. Warum, sieht der Admin unter Zustand → Modelle.")
    if en:
        return "My language model is starting right now" + (f", about {m} more minute{'s' if m > 1 else ''}." if m else ".") \
            + " Please ask again then."
    return "Mein Sprachmodell startet gerade neu" + (f", etwa noch {m} Minute{'n' if m > 1 else ''}." if m else ".") \
        + " Frag mich dann bitte noch einmal."


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["schritt"] and len(a) in (3, 4):
            schritt(a[1], int(a[2]), a[3] if len(a) == 4 else "")
        elif a[:1] == ["teil"] and len(a) == 2:
            teil(a[1])
        elif a[:1] == ["ende"] and len(a) in (2, 3):
            ende(a[1], a[2] if len(a) == 3 else "")
        else:
            raise ValueError("befehl")
    except ValueError as e:
        print(f"modelle: llmstart abgelehnt {e}", file=sys.stderr)
        sys.exit(2)
