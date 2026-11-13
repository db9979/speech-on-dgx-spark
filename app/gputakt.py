"""GPU-Taktgrenze (Dominik 2026-11-13, idea from alzeo v1.47.0): a ceiling on the model computer's GPU clock for less
power and heat at about the same speed. Einstellungen → Betrieb → GPU-Taktgrenze, setting watch.gpu_takt, off by default.

Measured by alzeo on a GB10 (one text model, 4 streams): 2,400 MHz the same tokens per second for about 11 W less on the
GPU; 2,000 MHz 2.4 % fewer tokens per second for half the GPU's watts and about 8 °C less; pictures take about 8 % longer.

How it is set: only root may cap the clock, and root takes no word from the panel. The fixed root unit UNIT runs
`speech-spark gputakt intern`, which reads the one setting from this computer's config itself and knows only the values
of STUFEN: `nvidia-smi -lgc 0,<MHz>` for a cap, `nvidia-smi -rgc` for none (speech-spark.sh, cmd_gputakt). It writes the
outcome as one line "<word> <epoch>" to STAND, never anything else. The unit runs at every start of the model computer
(a cap does not survive a restart) and when the setting changes: on this computer by the panel's save (admin._save),
on a split install by the Wärter after it took the panel's settings (tarswart.einstellen). The panel never runs
nvidia-smi with an argument of its own.

The state reaches the pages through common.gpu_stats ("grenze": what STAND says), so the Wärter's status carries it too.
"""
import os

from common import load_config, run

STUFEN = ("aus", "2400", "2200", "2000")      # the only values; "aus" = no cap (the factory setting)
UNIT = "speech-spark-gpu-takt"
STAND = os.environ.get("SPEECH_SPARK_GPU_TAKT", "/run/speech-spark-gpu-takt/stand")
WOERTER = ("aus", "fehler") + STUFEN[1:]          # what root writes into STAND


def wahl(cfg=None):
    """The chosen value of STUFEN ("aus" for anything else)."""
    cfg = load_config() if cfg is None else cfg
    v = (cfg.get("watch") or {}).get("gpu_takt", "aus")
    return v if isinstance(v, str) and v in STUFEN else "aus"


def stand(read=None):
    """What root last set: {"wort": WOERTER, "t": epoch}, None when it has not run since the start (or no GPU)."""
    try:
        if read is None:
            with open(STAND) as f:
                raw = f.read(64)
        else:
            raw = read(STAND)
        wort, t = raw.split()
        return {"wort": wort, "t": int(t)} if wort in WOERTER and t.isdigit() else None
    except (OSError, ValueError):
        return None


def anwenden(alt, neu, wer="panel"):
    """Starts the root unit when the setting changed between the configs alt and neu; True when nothing was to do or
    the start went through. Only where the GPU is (the model computer); one log line for every outcome."""
    a, n = wahl(alt), wahl(neu)
    if a == n:
        return True
    if not os.path.exists("/usr/bin/nvidia-smi"):
        print(f"gputakt: {wer} {n} ohne gpu", flush=True)
        return True
    ok = run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", UNIT], timeout=20)[0] == 0
    print(f"gputakt: {wer} {n} {'gestartet' if ok else 'fehler'}", flush=True)
    return ok
