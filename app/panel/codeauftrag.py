"""Code-Auftrag im Chat (plan opencode-pi, package 3b, Dominik 2026-11-03 „1a“ and „2a“): an admin types in the panel's
or the app's chat what should change in the Spark's code; OpenCode works on it once, as spark-dev on its own branch
opencode/auftrag-<n> of spark-dev's clone, and the card „Code-Auftrag (OpenCode)“ shows what came out.

Fixed rules, the panel decides: the tool code_auftrag is offered only to an admin's own recognized profile, only in
the typed chat of the panel and the apps (never the speakers, the car, Telegram, Siri, the watch, the Begleiter, MCP
or guests), only while the admin switch chat.entwickeln_auftrag is on, and only on the admin's own words (WORDS). The
goal is data for OpenCode with a fixed maximum length (entwickeln.ZIEL_MAX), fenced in a fixed prompt; it is never a
rule. Nothing is installed: the card's „Lokal einspielen“ and „An GitHub geben“ open Zustand → Werkstatt →
Entwickeln, where each asks for a fresh code; „Verwerfen“ deletes the branch. Das Modell schlägt nur vor.

    the wish     STATE/code-auftrag-wunsch: {aktion, id, ziel, von, t} (the service user's file); root's oneshot
                 speech-spark-auftrag takes it (entwickeln.auftrag_lauf) and writes STATE/code-auftraege.json
    the card     vorgaenge art "codeauftrag", key "codeauftrag:<id>": the goal, the state, files and lines, the first
                 lines of the change as text; updated every minute (due_once) from the root's file

Logs only fixed words and numbers (entwickeln: auftrag …), never the goal or the change; Live only counts.
"""
import json
import os
import re
import sys
import threading
import time

import features

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import entwickeln  # noqa: E402

KEY = "entwickelnauftrag"
CARD = "codeauftrag"
WEG = "Zustand → Werkstatt → Entwickeln"
CLIENTS = ("web", "app", "android")       # typed chat of the panel and the apps; every other channel never
PRO_STUNDE = 6                            # orders an admin may start per hour
VORSCHAU = 400                            # characters of the changed paths on the card (the page shows the change)
LAEUFT_S = entwickeln.AUFTRAG_S + 900     # an order that says „läuft“ longer than this counts as gone
WORDS = re.compile(r"(?i)\b(code-?auftrag\w*|opencode|(im|am|den|der) (spark-?)?code\b|"
                   r"programmier\w* (mir |du )?(im|am|in|für den) spark|code order|change the (spark'?s )?code)\b")
TOOL = {"type": "function", "function": {
    "name": "code_auftrag",
    "description": "Starts a code order for the admin: OpenCode changes the Spark's code once, on its own branch on the "
                   "panel computer, and a card shows the change. Nothing is installed; the admin decides on the card. "
                   "Only when the admin asks for a change of the Spark's code.",
    "parameters": {"type": "object", "properties": {
        "ziel": {"type": "string", "description": "what should change, in the admin's words (at most 500 characters)"}},
        "required": ["ziel"]}}}
HINT = ("Will der Admin den Code des Sparks ändern lassen (Code-Auftrag, OpenCode), ruf code_auftrag mit seinem Ziel in "
        "seinen Worten. Sag danach nur, dass der Auftrag läuft und die Karte den Vorschlag zeigt; eingespielt wird nichts.")
STAND = {"laeuft": ("läuft …", "running …"), "fertig": ("Vorschlag fertig", "proposal ready"),
         "leer": ("nichts geändert", "nothing changed"), "abgelehnt": ("nicht gemacht", "not done"),
         "lokal": ("auf lokal übernommen", "taken onto lokal"), "verworfen": ("verworfen", "dropped")}
_lock = threading.Lock()
_starts = {}        # uid -> [t, …] of the last hour
_seen = {}          # id -> the state the card shows (so the card changes only when the order does)


def an(cfg=None):
    return features.admin_on(KEY, cfg)


def is_admin(uid):
    import notaus
    return bool(uid) and uid in notaus.admin_uids()


def offer(ctx):
    """Only an admin's own profile, typed in the panel or an app, the switch on, the own words about the code."""
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") not in CLIENTS:
        return None
    if not WORDS.search(str(ctx.get("text") or "")) or not is_admin(who["id"]) or not features.allowed(KEY, who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "changes": {"code_auftrag"}, "keep": {"code_auftrag"},
            "filler": {"code_auftrag": ("Ich gebe OpenCode den Auftrag.", "Handing the order to OpenCode.")}}


def _wunsch(w):
    with open(entwickeln.AUFTRAG_WUNSCH, "w") as f:
        json.dump(dict(w, t=int(time.time())), f)


def _starten():
    from core import run
    code, _out = run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", entwickeln.AUFTRAG_UNIT], timeout=20)
    if code != 0:
        try:
            os.remove(entwickeln.AUFTRAG_WUNSCH)
        except OSError:
            pass
    return code == 0


def auftraege():
    """The root's file, every entry checked again (entwickeln.auftrag_eintrag)."""
    try:
        with open(entwickeln.AUFTRAEGE) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    return [x for x in (entwickeln.auftrag_eintrag(y) for y in (raw.get("auftraege") if isinstance(raw, dict) else None) or []) if x]


def laeuft(liste=None, now=None):
    now = time.time() if now is None else now
    return any(x["zustand"] == "laeuft" and now - x["t"] < LAEUFT_S for x in (auftraege() if liste is None else liste))


def start(uid, ziel, now=None):
    """The tool's work: checks, the wish, root's oneshot, the card. Returns (ok, the sentence for the model)."""
    import notaus
    now = time.time() if now is None else now
    if not an() or not features.allowed(KEY, uid) or not is_admin(uid):
        print("entwickeln: auftrag abgelehnt aus", flush=True)
        return False, "Not done: Code-Auftrag ist aus (Funktionen → Entwickeln auf dem Pi → Code-Auftrag im Chat)."
    if notaus.refuse("aussen"):
        print("entwickeln: auftrag abgelehnt notaus", flush=True)
        return False, "Not done: Notaus, kein Code-Auftrag."
    ziel = entwickeln.ziel_pruefen(ziel)
    if not ziel:
        print("entwickeln: auftrag abgelehnt ziel", flush=True)
        return False, "Not done: Es fehlt, was sich ändern soll. Frag den Admin danach."
    with _lock:
        _starts[uid] = [t for t in _starts.get(uid, []) if now - t < 3600]
        if len(_starts[uid]) >= PRO_STUNDE:
            print("entwickeln: auftrag abgelehnt grenze", flush=True)
            return False, f"Not done: höchstens {PRO_STUNDE} Code-Aufträge in der Stunde."
        if laeuft(now=now):
            print("entwickeln: auftrag abgelehnt laeuft", flush=True)
            return False, "Not done: " + entwickeln.AUFTRAG_GRUENDE["laeuft"][0]
        aid = "c" + str(int(now)).rjust(10, "0")[-10:]
        _wunsch({"aktion": "start", "id": aid, "ziel": ziel, "von": uid})
        if not _starten():
            print("entwickeln: auftrag abgelehnt start", flush=True)
            return False, "Not done: Code-Auftrag konnte nicht starten (sudo ./install.sh --entwickeln einmal neu)."
        _starts[uid].append(now)
    karte(uid, {"id": aid, "zustand": "laeuft", "ziel": ziel, "dateien": 0, "plus": 0, "minus": 0, "diff": "", "grund": ""},
          say=True)
    print("entwickeln: auftrag gestartet", flush=True)
    import guard
    guard.log("entwickeln_auftrag", detail="start")
    return True, ("NOT done yet: Der Code-Auftrag läuft (OpenCode als spark-dev auf einem eigenen Zweig). Die Karte "
                  "„Code-Auftrag (OpenCode)“ zeigt den Vorschlag, sobald er fertig ist; einspielen entscheidet der Admin. "
                  "Sag das in einem Satz, ohne Code.")


async def tool(name, args, ctx):
    import asyncio
    who = ctx.get("who") or {}
    if name != "code_auftrag" or ctx.get("client") not in CLIENTS or not is_admin(who.get("id")):
        return "Not done: Code-Auftrag gibt es nur für einen Admin im getippten Chat von Panel und App."
    args = args if isinstance(args, dict) else {}
    _ok, text = await asyncio.to_thread(start, who["id"], args.get("ziel"))
    return text


# ---------------------------------------------------------------- the card (vorgaenge.QUELLEN)
def pfade(diff):
    """The changed paths of a change (its „+++ b/“ lines, „--- a/“ for a deleted file), each once, in order."""
    out, alt = [], ""
    for z in str(diff or "").splitlines():
        if z.startswith("--- "):
            alt = z[6:] if z.startswith("--- a/") else ""
        elif z.startswith("+++ "):
            p = z[6:] if z.startswith("+++ b/") else alt
            if p and p not in out:
                out.append(p)
    return out


def _felder(x):
    """Goal, state, numbers, the changed paths and the branch; the change itself only on the page (a diff on one
    line of a card cannot be read)."""
    st = STAND[x["zustand"]][0] + (": " + entwickeln.AUFTRAG_GRUENDE[x["grund"]][0] if x.get("grund") else "")
    out = [("Ziel", x["ziel"]), ("Stand", st)]
    if x["dateien"]:
        out.append(("Dateien", f"{x['dateien']} · +{x['plus']} −{x['minus']}"))
        wo = ", ".join(pfade(x.get("diff")))
        if wo:
            out.append(("Geändert", wo[:VORSCHAU] + (" …" if len(wo) > VORSCHAU else "")))
        out.append(("Zweig", x["zweig"]))
    return out


def karte(uid, x, say=False):
    """The card of one order: the goal and the change only as text (the card is data), the fixed note."""
    import vorgaenge
    zweig = entwickeln.auftrag_zweig(x["id"])
    x = dict(x, zweig=zweig)
    vorgaenge.put(uid, CARD, f"{CARD}:{x['id']}", "Code-Auftrag (OpenCode)",
                  zeile="Das Modell schlägt nur vor. Einspielen entscheidest du. Im Terminal weitermachen: " + WEG + ".",
                  felder=_felder(x), daten={"weg": WEG, "ref": x["id"]}, say=say)
    _seen[x["id"]] = (x["zustand"], x.get("grund", ""), x["dateien"])


async def due_once():
    """Every minute (extras.due_once): an order whose state changed updates its card; a dropped one closes it."""
    import vorgaenge
    if not an():
        return
    for x in auftraege():
        if not x["von"] or _seen.get(x["id"]) == (x["zustand"], x.get("grund", ""), x["dateien"]):
            continue
        karte(x["von"], x)
        if x["zustand"] in ("verworfen", "leer"):
            vorgaenge.done(x["von"], f"{CARD}:{x['id']}", "erledigt")
        print(f"entwickeln: auftrag karte {x['zustand']}", flush=True)


def _eins(x):
    aid = str((x.get("daten") or {}).get("ref") or "")
    return next((y for y in auftraege() if y["id"] == aid), None)


def _card_acts(uid, x):
    """Lokal einspielen and An GitHub geben (they open the page, which asks for the code) and Verwerfen only while
    the proposal is ready; Ansehen always."""
    y = _eins(x)
    if not y or y["zustand"] != "fertig" or not an() or not is_admin(uid):
        return {"oeffnen"}
    import entwickelnseite
    return {"ca_lokal", "ca_weg", "oeffnen"} | ({"ca_github"} if entwickelnseite._github_an() else set())


def _card_run(uid, x, name):
    """Verwerfen: root deletes the order's branch (nothing installed, nothing sent). The others only open the page."""
    import vorgaenge
    if name != "ca_weg":
        return None
    y = _eins(x)
    if not y or y["zustand"] != "fertig" or not an() or not is_admin(uid):
        raise vorgaenge.HTTPException(409, entwickeln.AUFTRAG_GRUENDE["weg"][0])
    _wunsch({"aktion": "weg", "id": y["id"]})
    if not _starten():
        print("entwickeln: auftrag verwerfen abgelehnt start", flush=True)
        raise vorgaenge.HTTPException(500, "Verwerfen konnte nicht starten (sudo ./install.sh --entwickeln einmal neu).")
    print("entwickeln: auftrag verwerfen gestartet", flush=True)
    return {"text": "Wird verworfen: der Zweig " + y["zweig"] + " kommt weg."}


def _register():
    import vorgaenge
    vorgaenge.ARTEN[CARD] = {"de": "Code-Auftrag", "en": "Code order", "sym": "check", "mail": False, "dringend": False,
                             "acts": ("ca_lokal", "ca_github", "ca_weg", "oeffnen")}
    vorgaenge.AKTIONEN.update(ca_lokal={"de": "Lokal einspielen", "en": "Install locally", "stufe": "seite"},
                              ca_github={"de": "An GitHub geben", "en": "Hand to GitHub", "stufe": "seite"},
                              ca_weg={"de": "Verwerfen", "en": "Drop", "stufe": "direkt"})
    vorgaenge.QUELLEN[CARD] = {"acts": _card_acts, "run": _card_run}
    vorgaenge.OFFEN_STUNDEN[CARD] = 7 * 24


_register()
