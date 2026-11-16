"""The admin's Hugging Face token (Dominik 2026-11-16 „auch die hugginface api eingabe für schnelleren download nicht
vergessen“, „ja“ for models that need an approval): downloads of the model catalog go faster with it, and a model
whose page asks for an approval (gated, e.g. Llama) loads once the admin has accepted its terms on Hugging Face.
Private repositories stay off (modelle.laden_pruefen, eigen_vorschlag).

It lives only on the computer the models run on (STATE/hf-token.json, 0600 like the Wärter's key), never in the
config, never in a log, never in an answer (only whether one is set and since when), never in an engine's or a
Docker measurement's environment (`docker_args`, test_modelle_docker). It goes only to huggingface.co: as
`token=` to snapshot_download (modelle._laden) and as the Authorization header of the metadata question (`kopf`).
A token Hugging Face refuses (401) is marked and the questions go without it, nothing gets worse than without one.
Set and removed by the admin (Zustand → Modelle → „Mehr“, fresh admin code; on another computer through the
Wärter command hf_token, hf_token_weg)."""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, read_json, write_json  # noqa: E402

DATEI = os.path.join(STATE, "hf-token.json")
TOKEN = re.compile(r"hf_[A-Za-z0-9]{30,96}")
HOST = "https://huggingface.co/"


def token(path=DATEI):
    """The token, "" when none is set, it was refused or the file is not this kind."""
    d = read_json(path, {})
    t = d.get("token")
    return t if isinstance(t, str) and TOKEN.fullmatch(t) and not d.get("abgelehnt") else ""


def info(path=DATEI):
    """What a page may see: {gesetzt, seit, abgelehnt}; never the token."""
    d = read_json(path, {})
    t = d.get("token")
    ok = isinstance(t, str) and TOKEN.fullmatch(t) is not None
    seit = d.get("seit")
    return {"gesetzt": ok, "seit": seit if ok and isinstance(seit, int) else None, "abgelehnt": ok and bool(d.get("abgelehnt"))}


def speichern(t, now=None, path=DATEI):
    """Keeps a new token (only the shape of a Hugging Face token); ValueError("token") otherwise."""
    t = str(t or "").strip()
    if not TOKEN.fullmatch(t):
        raise ValueError("token")
    write_json(path, {"token": t, "seit": int(time.time() if now is None else now)}, mode=0o600)


def weg(path=DATEI):
    """Removes the token; True when there was one."""
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def abgelehnt(path=DATEI):
    """Hugging Face refused the token (401): marked, the next questions go without it until a new one is saved."""
    d = read_json(path, {})
    if d.get("token") and not d.get("abgelehnt"):
        d["abgelehnt"] = True
        write_json(path, d, mode=0o600)
        print("modelle: hf-token abgelehnt", flush=True)


def kopf(url, path=DATEI):
    """The Authorization header for a question to huggingface.co with the token, else {} (never to another host)."""
    t = token(path)
    return {"Authorization": f"Bearer {t}"} if t and str(url).startswith(HOST) else {}


API = HOST + "api/models/{repo}/revision/{rev}?blobs=true"     # the one address asked (modelle.HF_API's own)
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
REV = re.compile(r"^[0-9a-f]{40}$")
MAX_BYTES = 4 * 1024 * 1024


def metadaten(repo, rev="", path=DATEI, timeout=20):
    """The metadata of one commit (or the newest) with the token, on the computer that keeps it (the Wärter command
    hf_info for a panel on another one): only this fixed address, at most MAX_BYTES, no redirects. Returns the JSON;
    raises ValueError with a fixed word (repo, zugang, antwort, netz)."""
    import json
    import urllib.error
    import urllib.request
    if not REPO.match(str(repo)) or ".." in repo or not (rev == "" or REV.match(str(rev))):
        raise ValueError("repo")
    url = API.format(repo=repo, rev=rev or "main")

    class Kein(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    req = urllib.request.Request(url, headers=dict(kopf(url, path), **{"User-Agent": "speech-spark"}))
    try:
        with urllib.request.build_opener(Kein).open(req, timeout=timeout) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 401 and token(path):
            abgelehnt(path)
        raise ValueError("zugang" if e.code in (401, 403) else "antwort")
    except (OSError, ValueError):
        raise ValueError("netz")
    if len(raw) > MAX_BYTES:
        raise ValueError("antwort")
    try:
        d = json.loads(raw)
    except ValueError:
        raise ValueError("antwort")
    if not isinstance(d, dict):
        raise ValueError("antwort")
    return d
