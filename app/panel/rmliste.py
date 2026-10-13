"""„Was liegt auf meinem reMarkable?“ and „Welche Aufgaben hast du dort gefunden?“: the tool remarkable_library
(plan werkzeug-abdeckung.md, Paket 7; Dominik 2026-10-13 „1-7 umsetzen“).

Reading only, from what the panel already keeps: the last listing of the account (remarkable.library, written by
the comparison; this tool never asks the cloud) and the task lines the Spark found on paper (rmplus „Aufgaben vom
reMarkable“, todos). Names of notebooks and handwritten lines are someone's words: outside text (the rest of the
answer is locked, see chat.LOCKED_OUTSIDE), at most MAX lines, cut short. Taking a task over as a reminder stays
a proposal under Ich → reMarkable or a new request in the person's own words.

Same switches as reading notes (features "remarkable", the profile's rm_on), own profile only, never guests or MCP;
offered only when the person's own words name the reMarkable (remarkable.WORDS), and then kept by the Weiche."""
import re
import time

import features

MAX = 40
TOOL = {"type": "function", "function": {
    "name": "remarkable_library",
    "description": "What lies on the user's reMarkable (folders and notebooks, newest first, from the last comparison) "
                   "or, with was='aufgaben', the task lines the Spark found in the handwriting. Reading only.",
    "parameters": {"type": "object", "properties": {
        "was": {"type": "string", "enum": ["ablage", "aufgaben"], "description": "ablage (default) or aufgaben"},
        "ordner": {"type": "string", "description": "optional: only this folder"}}}}}
HINT = ("remarkable_library zeigt, was auf dem reMarkable liegt oder welche Aufgaben der Spark dort gefunden hat; "
        "antworte nur daraus.")


def on(uid):
    return bool(uid) and features.allowed("remarkable", uid)


def _clean(s, n):
    return re.sub(r"\s+", " ", re.sub(r"<<<|>>>|[„“\n\r\t]", "", str(s or ""))).strip()[:n]


def ablage(uid, folder=""):
    import remarkable
    items = remarkable.library(uid)
    if not items:
        return "Vom reMarkable ist noch keine Liste da (Abgleich unter Ich → reMarkable). Sag das so."
    rows = []
    want = _clean(folder, 60).lower()
    for i, it in items.items():
        path = remarkable.path_of(items, i)
        if path is None or it.get("folder"):
            continue
        where = path.rsplit("/", 1)[0] if "/" in path else ""
        if want and want not in where.lower():
            continue
        rows.append((int(it.get("mod") or 0), where, it))
    if not rows:
        return "In diesem Ordner liegt nichts." if want else "Auf dem reMarkable liegt nichts."
    rows.sort(key=lambda r: -r[0])
    kind = {"pdf": "PDF", "epub": "EPUB", "notebook": "Notizbuch"}
    out = [f"„{_clean(it['name'], 60)}“ ({kind.get(it.get('kind'), 'Notizbuch')}"
           + (f", {it['n']} Seiten" if it.get("n") else "") + (f", in {_clean(where, 60)}" if where else "")
           + (f", geändert {time.strftime('%d.%m.', time.localtime(mod))}" if mod else "") + ")"
           for mod, where, it in rows[:MAX]]
    return (f"{len(rows)} Dokumente" + (f", die neuesten {len(out)}" if len(rows) > len(out) else "") + ":\n"
            + "\n".join("- " + x for x in out))


def aufgaben(uid):
    import rmplus
    if not features.allowed("rmtodo", uid):
        return "„Aufgaben vom reMarkable“ ist aus (Ich → reMarkable). Sag das so."
    todos = [t for t in rmplus.plus(uid).get("todos") or [] if isinstance(t, dict)]
    if not todos:
        return "Auf dem reMarkable hat der Spark keine offenen Aufgaben gefunden."
    out = [f"„{_clean(t.get('text'), 120)}“ (aus „{_clean(t.get('doc'), 60)}“)"
           for t in todos[-MAX:]]
    return (f"{len(todos)} Aufgaben vom reMarkable (übernehmen unter Ich → reMarkable):\n" + "\n".join("- " + x for x in out))


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp" or not on(who["id"]):
        return None
    import remarkable
    if not remarkable.WORDS.search(str(ctx.get("text") or "")) or not remarkable.load(who["id"]).get("token"):
        return None
    # the notebooks' names and the handwriting are someone's words: the rest of the answer is locked
    return {"tools": [TOOL], "hint": HINT, "outside": {"remarkable_library"}, "keep": {"remarkable_library"},
            "filler": {"remarkable_library": ("Ich schaue nach.", "Let me check.")}}


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    if name != "remarkable_library" or not on(uid):
        return "reMarkable-Notizen sind für dieses Profil aus."
    args = args if isinstance(args, dict) else {}
    if args.get("was") == "aufgaben":
        return aufgaben(uid)
    return ablage(uid, args.get("ordner") or "")
