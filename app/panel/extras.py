"""Small services the assistant can use besides the big ones in chat.py (weather, contacts, parcels ...).

Each module offers, per request, its tools with offer(ctx) -> None or {"tools", "hint", "outside",
"mail", "filler"}; "outside" and "mail" name the tools whose results are someone else's words (they
lock switching and changing for the rest of the answer, see chat.py). tool(name, args, ctx) runs one,
briefing(uid, zone) adds a part to the daily briefing. ctx: {"who", "own", "tz"}.
"""
import contacts
import parcels
import weather

SERVICES = [weather, contacts, parcels]


def offer(ctx):
    """{"tools", "hints", "outside", "mail", "filler", "run": {name: module}} for this request."""
    res = {"tools": [], "hints": [], "outside": set(), "mail": set(), "filler": {}, "run": {}}
    for m in SERVICES:
        try:
            o = m.offer(ctx)
        except Exception as e:
            print(f"{m.__name__}:", type(e).__name__, e, flush=True)
            o = None
        if not o:
            continue
        res["tools"] += o["tools"]
        res["hints"].append(o["hint"])
        res["outside"] |= o.get("outside", set())
        res["mail"] |= o.get("mail", set())
        res["filler"].update(o.get("filler", {}))
        res["run"].update({t["function"]["name"]: m for t in o["tools"]})
    return res


async def briefing(uid, zone=None):
    """[(service name, text)] for the daily briefing."""
    out = []
    for m in SERVICES:
        try:
            part = await m.briefing(uid, zone)
        except Exception as e:
            print(f"{m.__name__}: briefing", type(e).__name__, flush=True)
            part = ""
        if part:
            out.append((m.__name__, part))
    return out


async def due_once():
    await contacts.due_once()
