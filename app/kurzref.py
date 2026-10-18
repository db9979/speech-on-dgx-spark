"""A shorter reference for a cloned voice (tts.ref_max_s, 0 = off).

With the Base model every sentence carries the voice's whole reference recording: the talker reads all of it
before the first sound (in-context cloning), so a long recording makes the first audio late, more so with several
requests at once. When the recording is longer than ref_max_s, the speech output cuts it once at the quietest
moment shortly before ref_max_s, has speech recognition write the piece down again and keeps both in
VOICES_DIR/kurz/. With a transcript of its own the voice keeps that transcript's words (as many as recognition
heard); when they do not match, the full recording stays. The recording itself is never changed.
Fixed rules only, no model decides anything here; the piece goes to the local speech recognition on this machine.
"""
import array
import difflib
import io
import json
import os
import re
import sys
import wave

MIN_S = 3.0          # a reference shorter than this clones the voice badly
SLACK_S = 2.0        # cut only when the recording is this much longer than the limit
WINDOW_S = 0.1       # quietest 100 ms
MATCH = 0.7          # how closely the recognized words must match the voice's own transcript


def read_wav(data):
    """(rate, channels, frames) of a 16-bit PCM WAV, None for anything else."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getsampwidth() != 2 or w.getcomptype() != "NONE" or not 8000 <= w.getframerate() <= 48000:
                return None
            return w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    except (wave.Error, EOFError, OSError):
        return None


def write_wav(rate, channels, frames):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def cut_at(rate, channels, frames, max_s):
    """The number of frames to keep: the quietest WINDOW_S between 0.6 x max_s (at least MIN_S) and max_s,
    cut in its middle. None when the recording is short enough already."""
    total = len(frames) // (2 * channels)
    if total / rate <= max_s + SLACK_S:
        return None
    pcm = array.array("h")
    pcm.frombytes(frames[:int(max_s * rate) * 2 * channels])
    if sys.byteorder == "big":
        pcm.byteswap()
    mono = pcm[::channels]
    win, step = max(1, int(WINDOW_S * rate)), max(1, int(WINDOW_S * rate / 2))
    lo, hi = int(max(MIN_S, 0.6 * max_s) * rate), int(max_s * rate) - win
    best, at = None, hi
    for start in range(lo, hi + 1, step):
        energy = sum(x * x for x in mono[start:start + win])
        if best is None or energy < best:
            best, at = energy, start
    return at + win // 2


def piece(path, max_s):
    """(piece as WAV, whole seconds, kept seconds) of the recording at path; a word why not instead: "format" or
    "schon kurz". Reads and cuts in one go, for a worker thread."""
    with open(path, "rb") as f:
        info = read_wav(f.read())
    if not info:
        return "format"
    rate, channels, frames = info
    keep = cut_at(rate, channels, frames, max_s)
    if keep is None:
        return "schon kurz"
    return write_wav(rate, channels, frames[:keep * 2 * channels]), len(frames) / (2 * channels * rate), keep / rate


def _words(text):
    return re.findall(r"\w+", text.lower())


def keep_words(own, heard):
    """The beginning of the voice's own transcript that recognition heard in the piece, in the transcript's own
    spelling; None when nothing fits closely enough."""
    tokens = own.split()
    plain = [_words(t) for t in tokens]
    got = _words(heard)
    if not got or not tokens:
        return None
    best, upto = 0.0, 0
    for n in range(1, len(tokens) + 1):
        mine = [w for p in plain[:n] for w in p]
        if len(mine) > len(got) + 4:
            break
        ratio = difflib.SequenceMatcher(None, mine, got).ratio()
        if ratio > best:
            best, upto = ratio, n
    return " ".join(tokens[:upto]) if best >= MATCH else None


def short_dir(voices_dir):
    return os.path.join(voices_dir, "kurz")


def cached(voices_dir, name, src_mtime, max_s):
    """(wav bytes, transcript or "") of an earlier cut for this recording and limit, else None."""
    d = short_dir(voices_dir)
    try:
        with open(os.path.join(d, name + ".json")) as f:
            meta = json.load(f)
        if meta.get("src_mtime") != src_mtime or meta.get("max_s") != max_s:
            return None
        with open(os.path.join(d, name + ".wav"), "rb") as f:
            wav = f.read()
        txt = os.path.join(d, name + ".txt")
        return wav, (open(txt).read().strip() if os.path.exists(txt) else "")
    except (OSError, ValueError, AttributeError):
        return None


def store(voices_dir, name, src_mtime, max_s, wav, text, full_s, kept_s):
    d = short_dir(voices_dir)
    os.makedirs(d, mode=0o750, exist_ok=True)
    with open(os.path.join(d, name + ".wav"), "wb") as f:
        f.write(wav)
    txt = os.path.join(d, name + ".txt")
    if text:
        with open(txt, "w") as f:
            f.write(text)
    elif os.path.exists(txt):
        os.remove(txt)
    with open(os.path.join(d, name + ".json"), "w") as f:   # last: a cut counts only once all its files are there
        json.dump({"src_mtime": src_mtime, "max_s": max_s, "full_s": round(full_s, 1), "kept_s": round(kept_s, 1)}, f)
