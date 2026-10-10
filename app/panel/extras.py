"""Small services the assistant can use besides the big ones in chat.py (weather, contacts, parcels ...).

Each module offers, per request, its tools with offer(ctx) -> None or {"tools", "hint", "outside",
"mail", "filler"}; "outside" and "mail" name the tools whose results are someone else's words (they
lock switching and changing for the rest of the answer, see chat.py); "changes" names tools that
change something and are locked after such text. tool(name, args, ctx) runs one,
briefing(uid, zone) adds a part to the daily briefing; answer(ctx, text) handles the person's yes or
no to a proposal the module made (optional). ctx: {"who", "own", "tz", "private", "src", "client"}, offer()
also gets "text" (the person's latest message), answer() also "ha", "ha_code", "ha_code_ok" (the smart
home this turn may switch, see chat_turn); "private" is False over Telegram unless the profile allowed it.
"""
import agent
import contacts
import hamelden
import messages
import parcels
import roomfar
import tasks
import transit
import weather
import remarkable
import wiki

SERVICES = [roomfar, weather, contacts, parcels, tasks, transit, wiki, agent, messages, remarkable, hamelden]


def offer(ctx):
    """{"tools", "hints", "outside", "mail", "filler", "run": {name: module}} for this request."""
    res = {"tools": [], "hints": [], "outside": set(), "mail": set(), "changes": set(), "filler": {}, "run": {}}
    for m in SERVICES:
        try:
            o = m.offer(ctx)
        except Exception as e:
            print(f"{m.__name__}:", type(e).__name__, e, flush=True)
            o = None
        if not o:
            continue
        res["tools"] += o.get("tools", [])
        res["hints"].append(o["hint"])
        res["outside"] |= o.get("outside", set())
        res["mail"] |= o.get("mail", set())
        res["changes"] |= o.get("changes", set())
        res["filler"].update(o.get("filler", {}))
        res["run"].update({t["function"]["name"]: m for t in o["tools"]})
    return res


async def answer(ctx, text):
    """The first module waiting for a yes in this conversation handles the answer: {"call", "system"} or None."""
    for m in SERVICES:
        if hasattr(m, "answer"):
            try:
                res = await m.answer(ctx, text)
            except Exception as e:
                print(f"{m.__name__}: answer", type(e).__name__, e, flush=True)
                res = None
            if res:
                return res
    return None


async def briefing(uid, zone=None, private=True):
    """[(service name, text)] for the daily briefing (without private=False only the weather)."""
    out = []
    for m in SERVICES if private else [weather]:
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
