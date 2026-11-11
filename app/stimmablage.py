"""Stimmablage: the stored samples of the designed voices (Eigene Stimmen gestalten, panel stimmdesign.py).

A designed voice is made once with VoiceDesign and kept as a short sample (WAV, the fixed sentence it says); the
speech output's Base engine (tts.klon_*, tts_proxy role "klon") clones it for every answer, so the voice sounds the
same in every sentence and costs no more time than a named one (Dominik 2026-11-11 „1b“, „A“). The samples lie in
the speech output's voices folder (tts_proxy.VOICES_DIR) as <name>.wav with the words in <name>.txt, like the
recorded clone voices. Names are fixed: "sd-<id>" for the 20 presets, "eigen-<16 hex>" for one profile's own voice
(random, so nobody finds another profile's voice by its name). The profile's name never reaches this folder.

The one place both sides use: the panel puts a sample here itself when the speech output runs on its own computer,
else it sends it signed through the Wärter (tarswart.py, command stimme_ablegen); both check it the same way here:
the name, a plain WAV (16-bit mono PCM, 16 000 to 48 000 Hz, at most MAX_S seconds), the words (letters and a few
signs) and the number of voices. What this module writes ends in a log line of its caller, never the words.
"""
import os
import re
import struct

NAME = re.compile(r"(sd-[a-z0-9]{2,24}|eigen-[0-9a-f]{16})")
WORTE = re.compile(r"[A-Za-zÄÖÜäöüß0-9 ,.!?'\-]{3,300}")
MAX_BYTES = 1024 * 1024      # a sample of MAX_S seconds at 24 kHz is about 0.6 MB
MAX_S = 15.0
MIN_S = 3.0
MAX_EIGEN = 300              # own voices of all profiles together (three per profile, stimmdesign.MAX_EIGENE)


def pruefe_wav(wav):
    """The seconds of a plain WAV (16-bit mono PCM, 16 000 to 48 000 Hz), or ValueError with a fixed word."""
    if not isinstance(wav, (bytes, bytearray)) or not MIN_S * 32000 <= len(wav) <= MAX_BYTES \
            or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("wav")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(wav):
        cid, size = wav[pos:pos + 4], struct.unpack("<I", wav[pos + 4:pos + 8])[0]
        if cid == b"fmt " and size >= 16:
            fmt = struct.unpack("<HHIIHH", wav[pos + 8:pos + 24])
        elif cid == b"data":
            data = min(size, len(wav) - pos - 8)
            break
        pos += 8 + size + (size & 1)
    if not fmt or data is None:
        raise ValueError("wav")
    art, kanaele, rate, _, _, bits = fmt
    if art != 1 or kanaele != 1 or bits != 16 or not 16000 <= rate <= 48000:
        raise ValueError("wav")
    s = data / (rate * 2)
    if not MIN_S <= s <= MAX_S:
        raise ValueError("laenge")
    return s


def namen(ordner):
    """The names of the designed voices in the folder (sd-…, eigen-…), sorted."""
    try:
        return sorted(f[:-4] for f in os.listdir(ordner) if f.endswith(".wav") and NAME.fullmatch(f[:-4]))
    except OSError:
        return []


def _schreibe(pfad, data):
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(pfad + ".neu", pfad)


def ablegen(ordner, name, wav, worte):
    """Stores one sample (replaces one of the same name). ValueError with a fixed word when anything is off."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("name")
    if not isinstance(worte, str) or not WORTE.fullmatch(worte.strip()):
        raise ValueError("worte")
    pruefe_wav(wav)
    os.makedirs(ordner, exist_ok=True)
    if name.startswith("eigen-") and name not in namen(ordner) \
            and sum(n.startswith("eigen-") for n in namen(ordner)) >= MAX_EIGEN:
        raise ValueError("voll")
    base = os.path.join(ordner, name)
    for p in (base + ".wav", base + ".txt"):
        if os.path.islink(p):
            raise ValueError("name")
    _schreibe(base + ".txt", worte.strip().encode())
    _schreibe(base + ".wav", bytes(wav))
    return True


def weg(ordner, name):
    """Deletes one sample; False when there was none. ValueError for a name that is not a designed voice."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("name")
    da = False
    for ext in (".wav", ".txt"):
        p = os.path.join(ordner, name + ext)
        if os.path.lexists(p):
            os.remove(p)
            da = True
    import kurzref
    kurz = kurzref.short_dir(ordner)
    try:
        for f in os.listdir(kurz):    # the shorter reference of kurzref.py, when tts.ref_max_s cut it
            if f.split(".")[0] == name:
                os.remove(os.path.join(kurz, f))
    except OSError:
        pass
    return da
