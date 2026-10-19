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
import begleiter
import contacts
import hamelden
import messages
import parcels
import roomfar
import tasks
import transit
import feeds
import weather
import remarkable
import wiki
import hilfe
import meinmcp
import docmake
import bilder
import musik
import tagebuch
import zustand_wz
import rmliste
import nasablage
import naszustand
import aendern
import telefon_anruf
import rufen
import senden

SERVICES = [roomfar, weather, contacts, parcels, tasks, transit, feeds, wiki, agent, senden, messages, remarkable, hamelden, hilfe, begleiter, meinmcp, docmake, bilder, musik, tagebuch, zustand_wz, rmliste, aendern, nasablage, naszustand, telefon_anruf, rufen]


def offer(ctx):
    """{"tools", "hints", "outside", "mail", "filler", "must", "keep", "own", "run": {name: module}} for this request
    (keep: tools a module offers only because the person's own words named them, intent.narrow keeps them; own:
    tools the person's own words ask for, not locked by outside text read before, still by mail and the Notaus)."""
    res = {"tools": [], "hints": [], "outside": set(), "mail": set(), "changes": set(), "filler": {}, "run": {},
           "must": None, "keep": set(), "own": set()}
    for m in SERVICES:
        try:
            o = m.offer(ctx)
        except Exception as e:
            print(f"extras: {m.__name__}", type(e).__name__, e, flush=True)
            o = None
        if not o:
            continue
        res["tools"] += o.get("tools", [])
        res["hints"].append(o["hint"])
        res["outside"] |= o.get("outside", set())
        res["mail"] |= o.get("mail", set())
        res["changes"] |= o.get("changes", set())
        res["keep"] |= o.get("keep", set())   # offered on the person's own word: the Weiche never drops them
        res["own"] |= o.get("own", set())     # asked for in the person's own words: an answer from outside text before does not lock them
        res["filler"].update(o.get("filler", {}))
        res["must"] = res["must"] or o.get("must")
        res["route"] = res.get("route") or o.get("route")   # (group, why): this turn answers a question about a wish   # a fixed rule of the module: the first round calls this tool
        res["run"].update({t["function"]["name"]: m for t in o["tools"]})
    return res


async def answer(ctx, text):
    """The first module waiting for a yes in this conversation handles the answer: {"call", "system"} or None."""
    for m in SERVICES:
        if hasattr(m, "answer"):
            try:
                res = await m.answer(ctx, text)
            except Exception as e:
                print(f"extras: {m.__name__} answer", type(e).__name__, e, flush=True)
                res = None
            if res:
                return res
    return None


async def briefing(uid, zone=None, private=True):
    """[(service name, text)] for the daily briefing (without private=False only the weather)."""
    out = []
    for m in SERVICES if private else [weather]:
        if not hasattr(m, "briefing"):   # optional, like answer(): roomfar has none (journal "roomfar: briefing AttributeError")
            continue
        try:
            part = await m.briefing(uid, zone)
        except Exception as e:
            print(f"extras: {m.__name__} briefing", type(e).__name__, flush=True)
            part = ""
        if part:
            out.append((m.__name__, part))
    return out


async def due_once():
    await contacts.due_once()
    await feeds.due_once()
