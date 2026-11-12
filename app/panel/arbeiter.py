"""Zweiter Prozess für schwere Arbeit (Kritische Prüfung 2026-11-12 point 6): CPU-heavy work that used to run in a
thread of the panel's one process (and so held the GIL beside speech, the phone and every page) runs in a process of
its own, at a lower priority (NICE), with a time limit, and ends with its job.

First job: building a document file (docmake.build → docrender.render; Word, PowerPoint, Excel, PDF, Markdown). More
heavy work follows the same way.

The way, fixed:
- the parent hands over only JSON (the content, the format, the style, the template's path, the page size and the
  pictures already checked by docmake.picture_paths as paths); nothing is unpickled, neither way;
- the child is a fresh `python -I` (no PYTHONPATH, no user site, not the working folder), imports only docrender (the
  bottom layer, no panel module) and writes the file's bytes to stdout, at most MAX_OUT;
- a refusal of docrender (ValueError, its own fixed words) comes back as exit code 2 and is raised again as
  ValueError; anything else as RuntimeError with a fixed word; after TIMEOUT_S the child is killed.
Journal lines start with "arbeiter:", fixed words and numbers only (never the content).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:   # the child runs as `python -I arbeiter.py`: its own folder only, for docrender
    sys.path.insert(0, HERE)
import docrender  # noqa: E402  (the bottom layer: no panel module)

TIMEOUT_S = 120            # a document that takes longer is given up
NICE = 10                  # below the panel: speech and pages go first
MAX_OUT = 64 * 1024 * 1024
MAX_ERR = 300
REFUSED = 2                # exit code: docrender refused (ValueError)


def _bilder(c, pictures):
    """The pictures of this content as JSON: {"pics": {id: path}, "wiki": {id: path}, "cover": path}."""
    out = {"pics": {}, "wiki": {}, "cover": None}
    if not pictures:
        return out

    def walk(x, depth=0):
        if depth > 8:
            return
        if isinstance(x, dict):
            if isinstance(x.get("pictures"), list):
                for pid in x["pictures"][:50]:
                    got = pictures({"pictures": [pid]})
                    if got:
                        out["pics"][str(pid)] = got[0]
            wid = (x.get("wikipic") or {}).get("id") if isinstance(x.get("wikipic"), dict) else None
            if wid and hasattr(pictures, "wiki"):
                out["wiki"][str(wid)] = pictures.wiki(x)
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x:
                walk(v, depth + 1)
    walk(c)
    if hasattr(pictures, "cover"):
        out["cover"] = pictures.cover(c)
    return out


def _resolver(b):
    """docmake.picture_paths' shape again, from the JSON map."""
    def res(s):
        return [b["pics"][str(p)] for p in s.get("pictures") or [] if b["pics"].get(str(p))]
    res.wiki = lambda s: b["wiki"].get(str((s.get("wikipic") or {}).get("id")))
    res.cover = lambda c: b["cover"]
    return res


def _nice():
    try:
        os.nice(NICE)
    except OSError:
        pass


def dokument(c, fmt, style, pictures=None, base=None, page=None):
    """docrender.render(...) in its own process: the file's bytes. Raises ValueError like docrender."""
    job = json.dumps({"c": c, "fmt": fmt, "style": style, "bilder": _bilder(c, pictures), "base": base, "page": page})
    t0 = time.monotonic()
    try:
        r = subprocess.run([sys.executable, "-I", os.path.abspath(__file__)], input=job.encode("utf-8"),
                           capture_output=True, timeout=TIMEOUT_S, cwd=HERE, preexec_fn=_nice)
    except subprocess.TimeoutExpired:
        print("arbeiter: dokument abgebrochen zeit", TIMEOUT_S, "s", flush=True)
        raise ValueError("das Erstellen hat zu lange gedauert")
    ms = int((time.monotonic() - t0) * 1000)
    if r.returncode == REFUSED:
        print("arbeiter: dokument abgelehnt", ms, "ms", flush=True)
        raise ValueError(r.stderr.decode("utf-8", "replace").strip()[-MAX_ERR:] or "abgelehnt")
    if r.returncode or not r.stdout:
        print("arbeiter: dokument fehler code", r.returncode, ms, "ms", flush=True)
        raise RuntimeError("arbeiter: dokument fehler")
    if len(r.stdout) > MAX_OUT:
        print("arbeiter: dokument zu gross", len(r.stdout) // 1024, "KB", flush=True)
        raise ValueError(f"die Datei wäre größer als {MAX_OUT // 1024 ** 2} MB")
    print("arbeiter: dokument fertig", fmt, len(r.stdout) // 1024, "KB", ms, "ms", flush=True)
    return r.stdout


def _main():
    job = json.loads(sys.stdin.buffer.read(MAX_OUT).decode("utf-8"))
    try:
        data = docrender.render(job["c"], job["fmt"], job["style"], _resolver(job["bilder"]), job["base"], job["page"])
    except ValueError as e:
        sys.stderr.write(str(e)[:MAX_ERR])
        sys.exit(REFUSED)
    sys.stdout.buffer.write(data)


if __name__ == "__main__":
    _main()
