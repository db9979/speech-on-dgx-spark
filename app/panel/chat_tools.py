"""The tools of one chat turn: what runs when the model calls web search, Home Assistant, mail,
calendar, reminders ... Each function gets the turn (chat_turn.Turn) as t; only tools the round
offered run (st["offered"]), and locks after mail or outside text are checked here again."""
import asyncio
import datetime
import os
import re
import secrets
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calendars  # noqa: E402
import documents  # noqa: E402
import extras  # noqa: E402
from textnorm import guess_language  # noqa: E402
import homeassistant  # noqa: E402
import kiwix  # noqa: E402
import mail  # noqa: E402
import profiles  # noqa: E402
import recall  # noqa: E402
import tidy  # noqa: E402
import wiki  # noqa: E402
import chat  # noqa: E402  (constants and helpers; imported fully before any call)


async def run(t, name, args, st):
    # the model may only use what this round offered (a tool parser passes any name through)
    if name not in st["offered"]:
        return chat.MAIL_BLOCKED if st["mail"] and name in chat.LOCKED_MAIL else chat.NOT_OFFERED
    todo_change = name == "home_assistant_todo" and str(args.get("action") or "show").strip().lower() not in chat.TODO_READ
    if name in t.locked(st) or (todo_change and (st["mail"] or st["outside"])):
        return chat.MAIL_BLOCKED if st["mail"] else chat.OUTSIDE_BLOCKED
    if name in chat.READS_OUTSIDE:
        st["outside"] = True
    if name == "document_search":
        st["docs"] = True
    if name in t.ex["run"]:
        if name in t.ex["mail"]:
            st["mail"] = True
        elif name in t.ex["outside"]:
            st["outside"] = True
        return await t.ex["run"][name].tool(name, args, {"who": t.who, "own": t.own_browser, "tz": t.body.get("tz"), "src": t.src,
                                                         "private": t.private_ok, "client": t.body.get("client")})
    if name.startswith("mail_tidy_") and t.tidy_on:
        return await tidy_tool(t, name, args, st)
    if name == "mail_draft" and t.drafts_on:
        return await draft_tool(t, args, st)
    if name.startswith("mail_") and t.mailbox:
        return await mail_tool(t, name, args, st)
    if name == "web_search" and t.search:
        query = str(args.get("query", "")).strip()
        if st.get("docs") and t.web_own:
            # "Erst lokal suchen": after the person's documents only their own words go out, never the model's
            # (a document could ask to carry its text away in a query; lokal.py)
            print("lokal: weiter ins Web nach den Unterlagen, mit den eigenen Worten der Frage", flush=True)
            query = t.web_own
        elif t.local_task:
            print("lokal: weiter ins Web (lokal nicht genug)", flush=True)
        if not query:
            return "No query given."
        await t.out.put({"type": "search", "query": query})
        if st["first"]:  # something to hear while the search runs
            st["first"] = False
            en = guess_language(t.messages[-1]["content"]) == "English"
            await t.sentences.put("Let me look that up." if en else "Ich schaue kurz nach.")
        try:
            result, sources = await chat.web_search(t.c, t.ccfg, query)
            await t.out.put({"type": "sources", "items": sources})
            return result
        except Exception as e:
            # the internet or SearXNG is gone: the own Kiwix answers instead, saying so (kiwix.py)
            if t.who and t.own_browser and kiwix.web_fallback(t.who["id"]):
                try:
                    result, sources = await kiwix.web_instead(wiki._query(query))
                    print("chat: web search failed, answered from Kiwix:", type(e).__name__, flush=True)
                    await t.out.put({"type": "sources", "items": sources})
                    return result
                except (httpx.HTTPError, ValueError) as e2:
                    print("kiwix: web search fallback failed", type(e2).__name__, flush=True)
            await t.out.put({"type": "search_error", "message": str(e)})
            return f"Search failed: {e}. Tell the user the search did not work; do not answer from guesses."
    if name == "home_assistant" and t.ha:
        text = str(args.get("command", "")).strip()
        if not text:
            return "No command given."
        if t.ha_code and not t.ha_code_ok:
            print("homeassistant: code word not in the latest message, nothing sent; code word:",
                  homeassistant.code_state(t.ha), flush=True)
            await t.out.put({"type": "home_done", "ok": False, "text": "Codewort fehlt"})
            return chat.CODE_MISSING
        await t.out.put({"type": "home", "command": text})
        try:
            ok, answer, targets = await homeassistant.command(
                t.ha, text, "en" if guess_language(text) == "English" else "de")
        except (httpx.HTTPError, ValueError) as e:
            await t.out.put({"type": "home_done", "ok": False, "text": str(e)[:200]})
            return f"Home Assistant not reachable: {type(e).__name__}"
        await t.out.put({"type": "home_done", "ok": ok, "text": answer, "targets": targets})
        return ("Home Assistant: " if ok else "Home Assistant failed: ") + answer \
            + (f" (devices: {', '.join(targets)})" if targets else "")
    if name == "home_assistant_states" and t.ha:
        query = str(args.get("query", "") or "").strip()
        label = " ".join(x for x in (query, str(args.get("area", "") or ""), str(args.get("domain", "") or "")) if x)
        await t.out.put({"type": "home", "command": "? " + (label or "Übersicht")})
        try:
            n, result = await homeassistant.states(t.ha, query, str(args.get("domain", "") or ""),
                                                   str(args.get("area", "") or ""))
        except (httpx.HTTPError, ValueError) as e:
            await t.out.put({"type": "home_done", "ok": False, "text": str(e)[:200] or type(e).__name__})
            return f"Home Assistant not reachable: {type(e).__name__}"
        await t.out.put({"type": "home_done", "ok": n > 0, "text": f"{n} Treffer"})
        return result
    if name == "home_assistant_history" and t.ha:
        query = str(args.get("query") or args.get("entity_id") or args.get("entity") or "").strip()
        try:
            hours = int(args.get("hours") or 24)
        except (TypeError, ValueError):
            hours = 24
        await t.out.put({"type": "home", "command": f"? {query} ({hours} h)"})
        try:
            n, result = await homeassistant.history(t.ha, query, hours, chat.user_zone(t.body.get("tz")))
        except (httpx.HTTPError, ValueError) as e:
            await t.out.put({"type": "home_done", "ok": False, "text": str(e)[:200] or type(e).__name__})
            return f"Home Assistant not reachable: {type(e).__name__}"
        await t.out.put({"type": "home_done", "ok": n > 0, "text": f"{n} Verläufe"})
        return result
    if name == "home_assistant_todo" and t.ha:
        act = str(args.get("action") or "show").strip().lower()
        if act not in ("show", "list", "read", "get") and t.ha_code and not t.ha_code_ok:
            print("homeassistant: code word not in the latest message, list unchanged; code word:",
                  homeassistant.code_state(t.ha), flush=True)
            await t.out.put({"type": "home_done", "ok": False, "text": "Codewort fehlt"})
            return chat.CODE_MISSING
        await t.out.put({"type": "home", "command": f"{args.get('list') or 'Liste'}: {act} {args.get('item') or ''}".strip()})
        try:
            ok, result = await homeassistant.todo(t.ha, str(args.get("list") or ""), act, str(args.get("item") or ""))
        except (httpx.HTTPError, ValueError) as e:
            await t.out.put({"type": "home_done", "ok": False, "text": str(e)[:200] or type(e).__name__})
            return f"Home Assistant not reachable: {type(e).__name__}"
        await t.out.put({"type": "home_done", "ok": ok, "text": result[:200]})
        return ("Home Assistant: " if ok else "Home Assistant failed: ") + result
    if name == "home_assistant_action" and t.ha:
        # small models name the fields freely: "command", "action", "entity" ...
        eid = str(args.get("entity_id") or args.get("entity") or args.get("device") or args.get("name") or "")
        service = str(args.get("service") or args.get("command") or args.get("action")
                      or args.get("service_name") or "")
        if t.ha_code and not t.ha_code_ok:
            print("homeassistant: code word not in the latest message, nothing sent; code word:",
                  homeassistant.code_state(t.ha), flush=True)
            await t.out.put({"type": "home_done", "ok": False, "text": "Codewort fehlt"})
            return chat.CODE_MISSING
        await t.out.put({"type": "home", "command": f"{eid} {service}".strip()})
        try:
            ok, result = await homeassistant.action(t.ha, eid, service, args.get("data"))
        except (httpx.HTTPError, ValueError) as e:
            await t.out.put({"type": "home_done", "ok": False, "text": str(e)[:200] or type(e).__name__})
            return f"Home Assistant not reachable: {type(e).__name__}"
        await t.out.put({"type": "home_done", "ok": ok, "text": result[:200]})
        return ("Home Assistant: " if ok else "Home Assistant failed: ") + result
    if name == "history_search" and t.past:
        query = str(args.get("query", "")).strip()
        try:
            days = min(3650, max(1, int(args["days"]))) if args.get("days") not in (None, "") else None
        except (TypeError, ValueError):
            days = None
        await t.out.put({"type": "historysearch", "query": query})
        skip = t.body.get("convo") if t.own_browser and isinstance(t.body.get("convo"), str) else None
        return await asyncio.to_thread(recall.search, t.prof["id"], query, days, skip)
    if name == "document_search" and t.docs:
        query = str(args.get("query", "")).strip()
        await t.out.put({"type": "docsearch", "query": query})
        import wissen
        tags = [str(x) for x in args.get("tags") or [] if isinstance(x, (str, int))][:5] if isinstance(args.get("tags"), list) else []
        art = str(args.get("art") or "")[:30]
        if not wissen.on(t.who["id"], "brief"):
            tags, art = [], ""
        hits = await wissen.search(t.who["id"], query, tags=tags or None, art=art or None)
        if not hits and (tags or art):      # nothing in the text: at least which documents fit
            found = wissen.cards(t.who["id"], tags or None, art or None)
            if found:
                return ("No passage matches the words, but these documents fit (their profiles):\n"
                        + "\n".join("- " + wissen.card_line(d) for d in found[:20]))
        if hits:
            refs = list({(h["id"], h["page"]): {"id": h["id"], "name": h["name"], "page": h["page"], "file": h["file"]} for h in hits}.values())
            await t.out.put({"type": "docsources", "items": sorted({h["name"] for h in hits}), "refs": refs[:8]})
        return "\n\n".join(f"[{wissen.where(h)}]\n{h['text']}" for h in hits) or "No matching passages in the documents. Say so; do not guess."
    if name == "iphone_action" and t.phone_act:
        kind = args.get("kind")
        target = re.sub(r"[\x00-\x1f\x7f<>\\]", "", str(args.get("target") or "")).strip()[:120]
        if kind not in ("navigate", "call") or not target:
            return "Not done: give kind 'navigate' or 'call' and a target."
        await t.out.put({"type": "iphone", "kind": kind, "target": target})
        return (f"Sent to the iPhone, which now asks the user before it "
                f"{'opens the route to' if kind == 'navigate' else 'calls'} '{target}'. Say so in one short sentence.")
    if name.startswith("reminder_") and t.timers:
        pending = profiles.reminders(t.who["id"]) if t.who else t.guest_rem
        zone = chat.user_zone(t.body.get("tz"))
        fmt = lambda x: datetime.datetime.fromtimestamp(x["due"] / 1000, zone).strftime("%d.%m. %H:%M")  # noqa: E731
        if name == "reminder_set":
            text = str(args.get("text", "")).strip() or "Timer"
            due = chat.reminder_due(args, t.body.get("tz"))
            if not due:
                return "Invalid time: give minutes from now or a future 'YYYY-MM-DDTHH:MM'."
            item = profiles.add_reminder(t.who["id"], text, due) if t.who else \
                {"id": secrets.token_hex(4), "text": text[:200], "due": due}
            await t.out.put({"type": "reminder", "action": "set", "item": item, "foreign": not t.own_browser})
            return f"Set: '{item['text']}' at {fmt(item)}."
        if name == "reminder_list":
            return "\n".join(f"{fmt(x)}: {x['text']}" for x in pending) or "No pending reminders. Say so."
        if name == "reminder_cancel":
            t = str(args.get("text", "")).strip().lower()
            ids = {x["id"] for x in pending if t in ("alle", "all") or (t and t in x["text"].lower())}
            if t.who and ids:
                profiles.remove_reminders(t.who["id"], ids)
            if ids:
                await t.out.put({"type": "reminder", "action": "cancel", "ids": sorted(ids), "foreign": not t.own_browser})
            return f"Cancelled {len(ids)}."
    if name == "calendar_events" and t.cal["calendars"]:
        zone = chat.user_zone(t.body.get("tz"))
        try:
            day = datetime.date.fromisoformat(str(args.get("date") or "")[:10])
        except ValueError:
            day = datetime.datetime.now(zone).date()
        try:
            days = min(31, max(1, int(args.get("days") or 1)))
        except (TypeError, ValueError):
            days = 1
        await t.out.put({"type": "calendar"})
        start = datetime.datetime.combine(day, datetime.time(), zone)
        try:
            evs, errors = await calendars.events(t.who["id"], start, start + datetime.timedelta(days=days), zone)
        except (ValueError, httpx.HTTPError) as e:
            return f"Calendar not reachable: {e}"
        return ("\n".join(calendars.line(x) for x in evs) or "No appointments in this period. Say so; do not guess any.") \
            + "".join(f"\nCalendar '{n}' could not be read: {e}" for n, e in errors)
    if name == "calendar_add" and t.cal_write:
        try:
            item = chat.appointment(args, t.body.get("tz"))
        except (ValueError, TypeError, OverflowError) as e:
            return f"Not proposed: {e}. Ask the user for the missing or correct details."
        calendars.propose(t.who["id"], item, t.src)
        await t.out.put({"type": "calendar"})
        return ("NOT saved yet. Read this proposal to the user and ask whether to enter it: "
                + calendars.describe(item) + ". It is saved only if the user says yes in the next message.")
    if name == "daily_briefing" and t.briefing:
        return await briefing_text(t, st)
    if name == "memory_save" and t.prof:
        fact = profiles.remember(t.prof["id"], args.get("fact", ""))
        if fact:
            await t.out.put({"type": "memory", "action": "saved", "text": fact})
        return "Saved." if fact else "Nothing to save."
    if name == "memory_forget" and t.prof:
        text = str(args.get("text", "")).strip()
        # never "forget everything": a real word, and only when it names one to three notes
        hits = [x for x in profiles.memory(t.prof["id"]) if text.lower() in x["text"].lower()] \
            if re.search(r"\w{4,}", text) else []
        if len(hits) > 3:
            return (f"Nothing forgotten: '{text}' fits {len(hits)} notes. Ask the user which one exactly, "
                    "or let them delete it under Ich → Gedächtnis.")
        n = profiles.forget(t.prof["id"], text=text) if hits else 0
        if n:
            await t.out.put({"type": "memory", "action": "forgotten", "text": text})
        return f"Forgot {n} fact(s)."
    return f"Unknown tool {name}."


async def mail_tool(t, name, args, st):
    st["mail"] = True
    await t.out.put({"type": "mail"})

    def num(k, default):
        try:
            return min(mail.DAYS, max(1, int(args.get(k) or default)))
        except (TypeError, ValueError):
            return default
    try:
        if name == "mail_list":
            return await asyncio.to_thread(mail.listing, t.who["id"], "", num("days", 7), bool(args.get("unread")),
                                           8, chat.user_zone(t.body.get("tz")))
        if name == "mail_search":
            query = str(args.get("query", "")).strip()[:200]
            return await asyncio.to_thread(mail.listing, t.who["id"], query, num("days", 30), bool(args.get("unread")),
                                           8, chat.user_zone(t.body.get("tz")))
        if name == "mail_read":
            return await asyncio.to_thread(mail.read, t.who["id"], str(args.get("id", ""))[:40])
    except ValueError as e:
        return f"E-mail not readable: {e}"
    except Exception as e:
        return f"E-mail not readable: {type(e).__name__}"
    return f"Unknown tool {name}."


async def tidy_tool(t, name, args, st):
    st["mail"] = True     # sender names and subjects come from mail
    await t.out.put({"type": "mail"})
    uid = t.who["id"]
    if name == "mail_tidy_overview":
        return await asyncio.to_thread(tidy.overview, uid)
    act = str(args.get("action", "")).strip().lower()
    try:
        if act in ("sort", "keep"):
            folder = "keep" if act == "keep" else str(args.get("folder", "")).strip().lower()
            plan = await asyncio.to_thread(tidy.plan_sort, uid, str(args.get("sender", ""))[:200], folder)
        elif act == "undo":
            run = tidy.last_run(uid)
            if not run:
                return "Nothing to undo: no tidying in the last 30 days."
            n = sum(1 for x in tidy.state(uid)["log"] if x["run"] == run and not x.get("undone"))
            plan = {"kind": "undo", "run": run, "count": n}
        elif act == "cleanup":
            st_ = tidy.state(uid)
            aid = next((x["id"] for x in mail.get(uid)["accounts"]
                        if tidy.acct_state(st_, x["id"])["mode"] != "off"), None)
            summary = await asyncio.to_thread(tidy.backlog_scan, uid, aid)
            if not summary["moves"]:
                return f"Nothing to move in the last {summary['days']} days by the sure rules. Say so."
            plan = {"kind": "backlog", "summary": summary}
        else:
            return "Unknown action: use sort, keep, undo or cleanup."
    except (ValueError, OSError) as e:
        return f"Not proposed: {e}"
    tidy.propose(uid, plan, t.src)
    calendars.drop_pending(uid)      # one proposal at a time: the next yes is for this one
    what = tidy.describe(plan, tidy.state(uid))
    await t.out.put({"type": "proposal", "text": what})
    return ("NOT done yet. Read this proposal to the user and ask whether to do it: " + what
            + ". It is done only if the user says yes in the next message.")


async def draft_tool(t, args, st):
    try:
        plan = await asyncio.to_thread(tidy.plan_draft, t.who["id"], args.get("id"), args.get("to"),
                                       args.get("subject"), args.get("text"))
    except (ValueError, OSError) as e:
        return f"No draft: {e}"
    tidy.propose(t.who["id"], plan, t.src)
    calendars.drop_pending(t.who["id"])
    what = tidy.describe(plan)
    await t.out.put({"type": "proposal", "text": what})
    return ("NOT saved yet, and it is never sent. Read the draft to the user and ask whether to put it into the "
            "drafts folder: " + what + ". It is saved only if the user says yes in the next message.")


async def briefing_text(t, st):
    zone = chat.user_zone(t.body.get("tz"))
    now = datetime.datetime.now(zone)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await t.out.put({"type": "briefing"})
    topics = t.cal["topics"] if t.search else []
    jobs = [calendars.events(t.who["id"], today, today + datetime.timedelta(days=2), zone)
            if t.cal["calendars"] else asyncio.sleep(0)]
    quick = dict(t.ccfg, search_pages=0, search_results=3)
    jobs += [chat.web_search(t.c, quick, q) for q in topics]
    if t.mailbox:   # last, so the topics above are searched before any mail is read
        st["mail"] = True
        jobs.append(asyncio.to_thread(mail.briefing, t.who["id"]))
    if topics:
        await t.out.put({"type": "search", "query": " · ".join(topics)})
        if st["first"]:  # something to hear while the searches run
            st["first"] = False
            await t.sentences.put("Einen Moment, ich stelle alles zusammen.")
    res = await asyncio.gather(*jobs, return_exceptions=True)
    parts = [chat.now_line(t.body.get("tz")).split(" Nutze")[0]]
    if not t.cal["calendars"]:
        parts.append("Calendar: none connected" + ("" if t.who else " (guests have none)") + ".")
    elif isinstance(res[0], Exception):
        parts.append(f"Calendar not reachable: {res[0]}")
    else:
        res[0], errors = res[0]
        parts += [f"Calendar '{n}' could not be read: {e}" for n, e in errors]
        tomorrow = today + datetime.timedelta(days=1)
        for label, a, b in (("Today", today, tomorrow), ("Tomorrow", tomorrow, tomorrow + datetime.timedelta(days=1))):
            evs = [x for x in res[0] if x["start"] < b and (x["end"] > a or x["start"] >= a)]
            parts.append(f"{label}'s appointments:\n" + ("\n".join(
                calendars.line(x) + (" (already over)" if not x["allday"] and x["end"] <= now else "")
                for x in evs) or "none"))
    if t.timers:
        end = (today + datetime.timedelta(days=1)).timestamp() * 1000
        pend = [x for x in (profiles.reminders(t.who["id"]) if t.who else t.guest_rem) if x["due"] < end]
        parts.append("Reminders today:\n" + ("\n".join(
            f"{datetime.datetime.fromtimestamp(x['due'] / 1000, zone):%H:%M} {x['text']}" for x in pend) or "none"))
    if t.who:   # weather, birthdays, parcels (parcels come from mail: then the answer counts as mail)
        for kind, part in await extras.briefing(t.who["id"], zone, t.private_ok):
            parts.append(part)
            if kind == "parcels":
                st["mail"] = True
    if t.mailbox:
        r = res.pop()
        parts.append(r if isinstance(r, str) else f"E-mail not readable: {r}")
        if t.tidy_on:
            parts.append(tidy.briefing_line(t.who["id"]))
    srcs = []
    for q, r in zip(topics, res[1:]):
        if isinstance(r, Exception):
            parts.append(f"Topic '{q}': search failed")
        else:
            parts.append(f"Topic '{q}':\n{r[0][:2500]}")
            srcs += r[1][:2]
    if srcs:
        await t.out.put({"type": "sources", "items": srcs})
    return "\n\n".join(parts)
