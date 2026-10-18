"""chat_modell.py: the model side of an answer, cut out of chat._answer (plan Aufräumen, Richtlinie Teil 17).
Same code, same order; chat._answer hands every value over by name."""
import ablauf
import aendern
import answercheck
import asyncio
import calendars
import chat
import fixes
import gedaechtnis
import homeassistant
import httpx
import images
import json
import llm
import notbetrieb
import profiles
import re
import stufe
import taten
import tidy
import time
import verbrauch
import vorab
import wartung


async def llm_start_satz(en):
    """llmstart's sentence while the own language model switches, starts or is measured; "" otherwise or when the
    model computer cannot be asked (the chat keeps its own sentence)."""
    try:
        import llmstart
        import modellseite
        d = await asyncio.to_thread(modellseite.lage)
        return llmstart.satz(d["start"], en, d["misst"])
    except Exception:
        return ""


async def model_turn(*, acked, body, c, came_from, carry, ccfg, cfg, check_on, ex, fix_fix, fix_prev, fixed=None, ha, ha_direct, ha_read, known,
                     lheaders, llm_round, locked, messages, need, out, own_browser, run_tool, said_before, search, sentences,
                     settle, small, speak, src, t0, think_tools, tm, tool_temp, tools, tr, trace, turn, vip, who):
    """The model side of one answer (was chat._answer's inner model_side): asks the language model, runs its tool
    calls and writes the sentences and events. Every value comes from chat._answer by name; names of chat.py are read
    as chat.NAME at call time, so a test that patches chat still reaches them."""
    verbrauch.WHO.set(verbrauch.who_of(who))   # what this answer asks the models counts for this profile
    try:
        if fixed:   # Einfaches sofort beantworten (sofort.py): the panel's fixed sentence, no model
            kind, note = fixed
            print("chat: feste Antwort,", kind, flush=True)
            if tr:
                tr.step("prep", "Feste Antwort (Panel)", time.time(), panel=True)
            trace["calls"].append({"name": "Feste Antwort (Panel)", "args": "", "result": kind})
            await out.put({"type": "text", "delta": note})
            trace["said"] += note
            await sentences.put(note)
            return
        if wartung.paused("llm"):
            # Wartungspause (wartung.py): the fixed sentence at once, never the model's time-out; in Notbetrieb with
            # Parakeet (notbetrieb.py) a few fixed commands first, by fixed rules, still without a model
            en_p = chat.guess_language(messages[-1]["content"]) == "English"
            note = await notbetrieb.antwort(turn, en_p) if notbetrieb.hoert(cfg) else None
            step = "Notbetrieb (Panel)" if note else "Wartungspause (Panel)"
            note = note or await llm_start_satz(en_p) or wartung.sentence(en_p)   # a switch pauses, too
            print("chat: wartungspause, fester satz", flush=True)
            if tr:
                tr.step("prep", step, time.time(), panel=True)
            trace["calls"].append({"name": step, "args": "", "result": "fester Satz"})
            await out.put({"type": "text", "delta": note})
            trace["said"] += note
            await sentences.put(note)
            return
        zeit = verbrauch.over(who["id"]) if who else ""
        if zeit:   # Kontingent used up (verbrauch.py): fixed commands by fixed rules, else one fixed sentence, no model
            note = await notbetrieb.antwort(turn, chat.guess_language(messages[-1]["content"]) == "English", zaehlen=False)
            if not note:
                raise verbrauch.Quota(zeit)
            print("verbrauch: Kontingent voll, fester Befehl ohne Sprachmodell", flush=True)
            if tr:
                tr.step("prep", "Fester Befehl (Panel)", time.time(), panel=True)
            trace["calls"].append({"name": "Fester Befehl (Panel)", "args": "", "result": "Kontingent voll"})
            await out.put({"type": "text", "delta": note})
            trace["said"] += note
            await sentences.put(note)
            return
        model = await llm.model(c, ccfg, lheaders)
        fix_task = asyncio.create_task(fixes.extract(
            ccfg, model, who["name"], messages[-1]["content"], said_before, bool(came_from))) if fix_fix else None
        base = {"model": model, "stream": True, "max_tokens": chat.answer_tokens(ccfg, body, getattr(turn, "car", False)),
                "temperature": float(ccfg.get("temperature", 0.3)), **chat.sampling(ccfg)}
        if not ccfg.get("thinking"):
            base["chat_template_kwargs"] = {"enable_thinking": False}
        # the server says how much it read, from its cache and wrote (Logs, Verbrauchszähler, Zustand → Prüfen per group)
        base["stream_options"] = {"include_usage": True}
        st = {"buf": "", "first": not acked, "think": False, "n": 0, "mail": carry == "mail", "outside": carry == "outside",
              "offered": set(), "saves": 0, "shown": 0, "check": bool(need) and check_on, "hold": None, "dropped": [], "msgs": None,
              "cal": bool(set(need or []) & chat.CAL_READS),
              "seen": set(), "echo": False, "echoed": 0,
              # Handlungs-Prüfung (taten.py): what changed in this answer, sentences claiming a deed nobody did
              # with no tool offered at all as well: every claimed or announced deed is then false (Qualitätstest)
              "act": bool(ccfg.get("action_check", True)) and (not tools or any(t["function"]["name"] in taten.KIND
                                                                                for t in tools)),
              "ran": 0, "acts": [], "held_acts": [], "fails": {}, "stopped": set(), "looked": False,
              "names": {t["function"]["name"] for t in tools or []}}
        if carry:
            await out.put({"type": carry})
        msgs, finish = list(messages), None
        note = chat.panel_note(getattr(turn, "time_note", None), getattr(turn, "turn_notes", None))
        if note and msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1].get("content"), str):
            # time and this turn's notes go with the question (chat.prompt_cache): only to the model, never
            # into the history
            msgs[-1] = dict(msgs[-1], content=msgs[-1]["content"] + note)
        if turn.pics:   # the pictures go to the model only, never into the history or the log
            msgs[-1] = images.with_pictures(msgs[-1], turn.pics)
        st["msgs"] = msgs
        searches, used, retried = 0, False, False
        max_searches = ccfg.get("max_searches", 2)
        max_searches = max_searches if isinstance(max_searches, int) and not isinstance(max_searches, bool) \
            and chat.SEARCH_RANGE[0] <= max_searches <= chat.SEARCH_RANGE[1] else 2
        if ha_direct:
            t_ha = time.time()
            await out.put({"type": "home", "command": ha_direct})
            ha_en = chat.guess_language(ha_direct) == "English"
            ha_step, ha_say, ha_ev = "home_assistant (Panel)", "", None
            try:
                ok, answer, targets, ha_step, ha_say, ha_ev = await chat._ha_panel(turn, ha, ha_direct, ha_en, who, src)
            except homeassistant.notaus.NotausAktiv as e:   # the Notaus holds every action off: its own reason, nothing else
                ok, targets, answer = False, [], f"{e}. Nothing was switched."
            except (httpx.HTTPError, ValueError) as e:  # also a proxy page instead of JSON
                print(f"homeassistant: not reachable ({type(e).__name__})", flush=True)
                ok, targets = False, []   # said out loud: a sentence, never the name of the error (B2)
                answer = "Home Assistant cannot be reached right now." if chat.guess_language(ha_direct) == "English" \
                    else "Home Assistant ist gerade nicht erreichbar."
            # only how many words, never what was said (Richtlinie: logs hold fixed words and numbers; the journal is
            # open to the Verwalter role and goes with traces and reports)
            print("homeassistant: panel ran a command of", len(str(ha_direct).split()), "words ->",
                  "ok" if ok else "not ok", flush=True)
            if tr:
                tr.step("tool", ha_step, t_ha, time.time(), ok=bool(ok), panel=True)
            await out.put({"type": "home_done", "ok": ok, "text": answer[:300], "targets": targets})
            if ha_ev:   # the panel's own question: buttons or the list (klaeren.py)
                await out.put(ha_ev)
            if ha_say and not ok:   # nothing switched yet: the panel asks, the model says the fixed question
                told = (f"Nothing was switched yet. Say exactly this question and nothing else: «{ha_say}» "
                        "Call no tool.")
            elif ha_say:
                told = (f"Home Assistant: {answer} Say this result in one short sentence, then ask exactly: "
                        f"«{ha_say}» Call no tool.")
            else:
                told = (("Home Assistant: " if ok else "Home Assistant failed: ") + answer
                        + " Say only this result, in one or two short sentences."
                        + ("" if ok else " Call no tool for this: nothing more can be switched in this answer."))
            msgs += [{"role": "assistant", "content": None, "tool_calls": [{"id": "ha0", "type": "function",
                      "function": {"name": "home_assistant", "arguments": json.dumps({"command": ha_direct})}}]},
                     {"role": "tool", "tool_call_id": "ha0", "content": told}]
        if ha_read:
            await out.put({"type": "home", "command": "? " + messages[-1]["content"][:80]})
            msgs += [{"role": "assistant", "content": None, "tool_calls": [{"id": "ha1", "type": "function",
                      "function": {"name": "home_assistant_states",
                                   "arguments": json.dumps({"query": messages[-1]["content"][:200]})}}]},
                     {"role": "tool", "tool_call_id": "ha1", "content": chat.wrap_outside(ha_read)}]
            if tr:
                tr.step("tool", "home_assistant_states (Panel)", t0, t0, chars=len(ha_read), panel=True)
            if homeassistant.free_text(ha_read) and not st["outside"]:
                st["outside"] = True
                await out.put({"type": "outside"})
        local_task = getattr(turn, "local_task", None)
        if local_task:   # "Erst lokal suchen" (lokal.py): what the quick look found goes in as data
            import lokal
            t_lk = time.time()
            found = await local_task
            if tr:   # Logs → Anfragen: one step, the numbers only
                tr.step("tool", "Erst lokal (Panel)", t_lk, time.time(), hits=len(found["hits"]), docs=found["n"].get("docs"),
                        archive=found["n"].get("kiwix"), history=found["n"].get("history"), late=len(found["late"]), ms=found["ms"],
                        panel=True)
            trace["calls"].append({"name": "Erst lokal (Panel)", "args": ", ".join(lokal.LABELS[k] for k in found["n"]),
                                   "result": f"{len(found['hits'])} Treffer in {found['ms']} ms"})
            if found["hits"]:
                msgs += [{"role": "assistant", "content": None, "tool_calls": [{"id": "lk0", "type": "function",
                          "function": {"name": "local_search",
                                       "arguments": json.dumps({"query": messages[-1]["content"][:200]})}}]},
                         {"role": "tool", "tool_call_id": "lk0",
                          "content": lokal.HEAD + "\n" + chat.wrap_outside(lokal.block(found["hits"]))}]
                if not st["outside"]:
                    st["outside"] = True
                    await out.put({"type": "outside"})
                if any(h["src"] == "docs" for h in found["hits"]):
                    st["docs"] = True
        direct = getattr(turn, "direct", None)
        if direct and direct not in locked(st):
            # "Eindeutiges direkt abrufen": the panel calls the one tool the question names (intent.DIRECT), the
            # model's first round would only have picked it; its result goes in like any tool result
            t_dr = time.time()
            st["offered"] = {direct}
            filler = chat.FILLERS.get(direct) or ex["filler"].get(direct)
            if filler and st["first"]:
                st["first"] = False
                await sentences.put(filler[1] if chat.guess_language(messages[-1]["content"]) == "English" else filler[0])
            dargs = getattr(turn, "direct_args", None) or {}   # only a date the panel worked out (intent.direct_args)
            result = await run_tool(direct, dict(dargs), st)
            if getattr(turn, "steps_on", False):   # Ablauf zeigen: the tool the panel called itself
                await out.put(ablauf.step(direct, result, time.time() - t_dr))
            pin = getattr(turn, "kl_pin", None)
            if pin and isinstance(result, str):   # the person's choice (klaeren.py): offer to remember it
                import klaeren
                en_kl = chat.guess_language(messages[-1]["content"]) == "English"
                q = klaeren.offer(who["id"], src, pin["area"], pin["said"], pin["cand"], en_kl) if pin.get("used") else ""
                if q:
                    await out.put(klaeren.remember_event(pin["area"], en_kl))
                    result += f"\nAfter saying this result, ask exactly: «{q}» Call no tool."
            if tr:
                tr.step("tool", f"{direct} (Panel)" if not pin else "Auswahl (Panel)", t_dr, time.time(), panel=True)
            trace["calls"].append({"name": direct + " (Panel)", "args": json.dumps(dargs), "result": result})
            msgs += [{"role": "assistant", "content": None, "tool_calls": [{"id": "dr0", "type": "function",
                      "function": {"name": direct, "arguments": json.dumps(dargs)}}]},
                     {"role": "tool", "tool_call_id": "dr0", "content": result}]
            used = True
            st["check"] = check_on   # an answer from a tool result: its figures are checked
        looked, last_noted = {}, False
        loop_stop = bool(ccfg.get("loop_stop", True))
        for rnd in range(5):  # a few tool rounds (at most max_searches searches), then the answer
            payload = dict(base, messages=msgs)
            offer = [t for t in tools if (t is not chat.SEARCH_TOOL or searches < max_searches)
                     and looked.get(t["function"]["name"], 0) < max_searches
                     and t["function"]["name"] not in locked(st) and t["function"]["name"] not in st["stopped"]
                     and not (st["mail"] and t is chat.HA_TODO_TOOL)] if rnd < 4 and not small else []
            st["offered"] = {t["function"]["name"] for t in offer}
            stable = getattr(turn, "tools_stable", None)
            if rnd == 4 and used and not small:
                # the last round: no list at all (with the list and tool_choice "none" qwen38 still writes
                # a call as text, which costs one more round, trace 68bf48), the model hears why
                msgs.append({"role": "user", "content": chat.LAST_NOTE})
                payload, last_noted = dict(base, messages=msgs), True
            elif stable and not offer and used:
                # "Schneller Antwortbeginn": after a tool round the same list as before (the start of this
                # request is the one just read), but no call in this round. A turn without any tool (plaudern,
                # nothing left to offer) gets the short request: the full list only pays off when qwen38
                # really takes it from its cache, and a miss costs every short answer thousands of tokens
                payload["tools"], payload["tool_choice"] = stable, "none"
            if offer:
                payload["tools"] = stable or offer
                if not used:  # choosing the tool: steadier (and, if switched on, with thinking)
                    payload["temperature"] = tool_temp
                    if think_tools:
                        payload["chat_template_kwargs"] = {"enable_thinking": True}
                if not used and need:
                    # the switch (intent.py) named the one tool: the model only fills in its arguments
                    force = getattr(turn, "force", None)
                    payload["tool_choice"] = {"type": "function", "function": {"name": force}} \
                        if force and force in st["offered"] else "required"
            # a data question still without a tool: hold the whole round, it may have to be asked again
            st["hold"] = [] if st["check"] and need and not used and not retried else None
            try:
                try:
                    finish, calls = await llm_round(payload, st)
                except RuntimeError as e:
                    if "tool_choice" not in payload or isinstance(e, chat.ContextFull) or st["n"]:
                        raise
                    print("chat: tool_choice refused, without it:", str(e)[:200], flush=True)
                    payload.pop("tool_choice")
                    if not offer:
                        payload.pop("tools", None)
                    finish, calls = await llm_round(payload, st)
                print(f"chat: {'profile' if who else 'no profile'}, round {rnd}, offered",
                      [t["function"]["name"] for t in offer], "called", [x["name"] for x in calls] or "nothing",
                      flush=True)
                if ha:
                    print("homeassistant: round", rnd, "model called", [x["name"] for x in calls] or "no tool",
                          flush=True)
            except chat.ContextFull:
                # still too long for the model (big documents or results): half the history, once more
                if rnd or st["n"] or len(msgs) < 3:
                    raise
                head = [m for m in msgs if m["role"] == "system"]
                rest = chat.trim_history([m for m in msgs if m["role"] in ("user", "assistant")], chat.history_chars(ccfg) // 4)
                msgs = head + rest
                st["msgs"] = msgs
                finish, calls = await llm_round(dict(payload, messages=msgs), st)
            held, st["hold"] = st["hold"], None
            if held is not None and not calls and finish != "length":
                # answered a data question without looking anything up: never said, asked once more
                print("chat: answer check: no tool for a data question, asked again", flush=True)
                trace["calls"].append({"name": "Antwort-Prüfung", "args": "", "result":
                                       "ohne Werkzeug geantwortet, verworfen: " + " ".join(x for x, _ in held)[:300]})
                retried = True
                if tr:
                    tr.step("check", "Antwort-Prüfung", time.time(), again=True)
                st["buf"], st["first"], st["tail"], st["code"] = "", True, "", False
                msgs.append({"role": "user", "content": answercheck.RETRY_NOTE})
                continue
            for x, gap in held or []:
                await speak(x, st, gap)
            if not calls or finish == "length":
                break
            await settle(st)
            msgs.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": x["id"], "type": "function", "function": {"name": x["name"], "arguments": x["arguments"]}}
                for x in calls]})
            filler = next((chat.FILLERS.get(x["name"]) or ex["filler"][x["name"]] for x in calls
                           if x["name"] in chat.FILLERS or x["name"] in ex["filler"]), None)
            if filler and st["first"] and not trace["said"].strip():
                # something to hear at once while the tool runs
                st["first"] = False
                en = chat.guess_language(messages[-1]["content"]) == "English"
                await sentences.put(filler[1] if en else filler[0])
            for k, x in enumerate(calls):
                if k >= chat.MAX_CALLS:
                    if tr:
                        tr.step("tool", x["name"] if x["name"] in known else "unbekannt", time.time(), ok=False, many=True)
                    msgs.append({"role": "tool", "tool_call_id": x["id"],
                                 "content": f"Not done: at most {chat.MAX_CALLS} tool calls per step."})
                    continue
                try:
                    args = json.loads(x["arguments"] or "{}")
                    args = args if isinstance(args, dict) else {}
                except ValueError:
                    args = {}
                if x["name"] in st["stopped"]:   # "Fehlerschleife stoppen": failed twice, not run a third time
                    msgs.append({"role": "tool", "tool_call_id": x["id"], "content": chat.LOOP_NOTE})
                    continue
                t_tool = time.time()
                if tr:
                    tr.now("tool", x["name"] if x["name"] in known else "unbekannt", t_tool)
                offered = x["name"] in st["offered"]
                result = await run_tool(x["name"], args, st)
                if getattr(turn, "steps_on", False) and offered:   # Ablauf zeigen (ablauf.py): name, ok, time
                    await out.put(ablauf.step(x["name"], result, time.time() - t_tool))
                if not st["ran"] and getattr(turn, "route", None) is not None and not turn.route.names:
                    import weiche   # Lernen: the group of the first tool of an unclear question, never its words
                    weiche.learn(turn.route, x["name"])
                st["ran"] += 1
                a = taten.act(x["name"], args, result)
                if a:
                    st["acts"].append(a)
                    if a["ok"] and who and own_browser:   # „Mach das rückgängig“ (aendern.py)
                        aendern.note_tool(who["id"], x["name"], args, result)
                elif not taten.failed(result):
                    st["looked"] = True
                if tm["rounds"]:
                    tm["rounds"][-1]["tools"].append((x["name"], time.time() - t_tool))
                if tr:
                    tr.step("tool", x["name"] if x["name"] in known else "unbekannt", t_tool, time.time(),
                            **chat.tool_info(x["name"], result, st, ex))
                trace["calls"].append({"name": x["name"], "args": json.dumps(args, ensure_ascii=False), "result": result})
                msgs.append({"role": "tool", "tool_call_id": x["id"], "content": result})
                if loop_stop and isinstance(result, str) and taten.failed(result) and chat.loop_count(st, x["name"], args):
                    st["stopped"].add(x["name"])
                    msgs[-1]["content"] += "\n\n" + chat.LOOP_NOTE
                    print(f"chat: loop stop: tool={x['name'] if x['name'] in known else 'unbekannt'} "
                          f"fails={st['fails'].get(x['name'], 0)}", flush=True)
                    trace["calls"].append({"name": "Schleife gestoppt", "args": x["name"],
                                           "result": "zweimal derselbe Fehler, nicht noch einmal aufgerufen"})
                    if tr:
                        tr.step("check", "Schleife gestoppt", time.time(), tool=x["name"] if x["name"] in known else "unbekannt")
                    taten.note_live("loop")
                if x["name"] == "web_search":
                    searches += 1
                if x["name"] in chat.LOOKUPS:
                    looked[x["name"]] = looked.get(x["name"], 0) + 1
            if search and st["mail"] and not st.get("search_said"):
                # the search just went away (mail was read): the model hears why, so it can say so
                st["search_said"] = True
                msgs[-1]["content"] += "\n\n" + chat.SEARCH_LOCKED_NOTE
            used = True
            st["check"] = check_on  # an answer from tool results: its figures are checked
        if (calls or st["xml"]) and finish != "length" and not last_noted:
            # out of tool rounds while the model still wanted one: one last answer without tools
            await settle(st)
            msgs.append({"role": "user", "content": chat.LAST_NOTE})
            finish, _ = await llm_round(dict(base, messages=msgs), st)
        buf = st["buf"]
        if finish == "length":
            # The answer hit max_tokens mid-sentence: speak up to the last sentence end and
            # tell the browser how much of the shown text to drop.
            ends = [m.end() for m in chat.BOUNDARY.finditer(buf + " ")]
            keep = buf[:min(ends[-1], len(buf))] if ends else ""
            if not (st["check"] or st["echo"] or st["act"]):
                await out.put({"type": "truncated", "drop": len(buf) - len(keep)})
            buf = keep
        if buf.strip():
            lead = st.get("tail", "") + buf[:len(buf) - len(buf.lstrip())]
            await speak(buf.strip(), st, "\n\n" if lead.count("\n") > 1 else "\n" if "\n" in lead else " ")
        if tr and st["check"] and used:
            tr.step("check", "Antwort-Prüfung", time.time(), held=len(st["dropped"]))
        if st["echoed"]:   # Logs → Anfragen: sentences the model wrote a second time, left out
            trace["calls"].append({"name": "Wiederholung weggelassen", "args": "",
                                   "result": f"{st['echoed']} schon gesagte Sätze nicht noch einmal gezeigt oder gesagt"})
        if st["dropped"]:
            # figures that are in no result were not said: one honest sentence instead
            en = chat.guess_language(messages[-1]["content"]) == "English"
            note = answercheck.FALLBACK["en" if en else "de"]
            trace["calls"].append({"name": "Antwort-Prüfung", "args": "",
                                   "result": "nicht gesagt (steht in keinem Ergebnis): "
                                             + ", ".join(answercheck.label(f) for f in st["dropped"])})
            await out.put({"type": "text", "delta": (" " if st["shown"] else "") + note})
            trace["said"] += note
            st["shown"] += len(note) + 1
            await sentences.put(note)
        fix_asked = False
        if taten.ANNOUNCED in st["held_acts"] and st["ran"]:
            # an announcement before a tool call that did come: left out, the tool's answer says the rest
            st["held_acts"].remove(taten.ANNOUNCED)
            print("chat: action check: announcement left out, a tool ran", flush=True)
        worked = {a["art"] for a in st["acts"] if a.get("ok")}
        if any(k and k in worked for k in st["held_acts"]):
            # „Ich mache das Lied.“ before the call that then worked: left out, the tool's answer says the rest
            st["held_acts"] = [k for k in st["held_acts"] if not k or k not in worked]
            print("chat: action check: claim left out, its tool worked later", flush=True)
        if st["held_acts"]:
            # "Taten prüfen": a deed was claimed that no tool did; one fixed sentence instead (never the model's)
            en = chat.guess_language(messages[-1]["content"]) == "English"
            art = st["held_acts"][0]
            ran = [a for a in st["acts"] if a["art"] == art or not art]
            if not any(a.get("wait") for a in st["acts"]):
                note = taten.sentence(art, "failed" if ran else "missing", en, next((a["what"] for a in ran if a["what"]), ""))
                await out.put({"type": "text", "delta": (" " if st["shown"] else "") + note})
                trace["said"] += (" " if trace["said"] else "") + note
                st["shown"] += len(note) + 1
                await sentences.put(note)
            trace["calls"].append({"name": "Taten-Prüfung", "args": "", "result": f"{len(st['held_acts'])} Satz/Sätze "
                                   "nicht gesagt: Tat ohne geklapptes Werkzeug (" + ", ".join(a or "erledigt" for a in st["held_acts"]) + ")"})
            if tr:
                tr.step("check", "Taten-Prüfung", time.time(), held=len(st["held_acts"]), kind=art or "erledigt",
                        why="fehler" if ran else "nicht_gelaufen")
        if who and own_browser:   # „Beschwerde erkennen“: the next message may say this did not work (taten.last)
            taten.note_last(who["id"], st["acts"])
        if fix_task:
            lesson = await fix_task
            busy = any((m.pending(who["id"]) or {}).get("src") == src for m in (calendars, tidy))
            trace["calls"].append({"name": "Korrektur", "args": fix_prev,
                                   "result": lesson or "nichts Dauerhaftes zum Merken"})
            if lesson and not busy and not st["mail"] and not st["outside"]:
                en = chat.guess_language(messages[-1]["content"]) == "English"
                ask_it = fixes.question(lesson, en)
                fixes.propose(who["id"], lesson, src)
                await out.put({"type": "text", "delta": (" " if st["shown"] else "") + ask_it})
                trace["said"] += " " + ask_it
                await sentences.put(ask_it)
                fix_asked = True
        if getattr(turn, "mem_ask_ok", False) and not fix_asked and not st["mail"] and not st["outside"] \
                and trace["said"].strip() and not any((m.pending(who["id"]) or {}).get("src") == src
                                                      for m in (calendars, tidy, fixes)):
            # "Stimmt das noch?" (gedaechtnis.py): the panel picks the fact by fixed rules, never the model
            mf = gedaechtnis.pick(who["id"], messages[-1]["content"], body.get("convo") or "")
            if mf:
                en = chat.guess_language(messages[-1]["content"]) == "English"
                ask_it = gedaechtnis.ask(who["id"], mf, body.get("convo") or "", src, en)
                if tr:
                    tr.step("prep", "Nachfrage (Panel)", time.time(), asked=1)
                trace["calls"].append({"name": "Nachfrage (Panel)", "args": "", "result": "gefragt"})
                await out.put({"type": "text", "delta": (" " if st["shown"] else "") + ask_it})
                trace["said"] += " " + ask_it
                await sentences.put(ask_it)
        if getattr(turn, "rm_after", False) and trace["said"].strip():
            # "... aufs reMarkable": the panel puts the answer there (remarkable.answer_wanted), never the model
            import remarkable
            t_rm = time.time()
            ok, note = await remarkable.send_answer(who["id"], turn.ask_text, trace["said"].strip())
            print("remarkable: answer", "sent" if ok else "not sent", flush=True)
            if tr:
                tr.step("tool", "remarkable (Panel)", t_rm, time.time(), ok=ok, panel=True)
            trace["calls"].append({"name": "remarkable (Panel)", "args": "", "result": note})
            await out.put({"type": "text", "delta": (" " if st["shown"] else "") + note})
            trace["said"] += " " + note
            await sentences.put(note)
        elif who and trace["said"].strip() and not st["mail"] and not st["outside"] and not getattr(turn, "act_held", False) \
                and not any((m.pending(who["id"]) or {}).get("src") == src for m in (calendars, tidy, fixes)):
            # „Soll ich das aufs reMarkable legen?“ (remarkable.offered): the panel keeps the answer as the waiting
            # proposal, so a plain „Ja“ puts it there (chat_turn) instead of meeting a missing tool
            import remarkable
            if remarkable.answer_ok(who, getattr(turn, "own_browser", False), getattr(turn, "private_ok", None)):
                remarkable.propose(who["id"], turn.ask_text, trace["said"].strip(), src)
        # "Vorab holen bei Rückfrage" (vorab.py): the answer asks back, the panel already fetches by fixed rules
        # what the next answer will most likely read, while the question is being spoken
        vorab.after(turn, trace["said"], st, trace["calls"], tr)
        # „Tipps beim Sprechen“ (saetze.py): at a speaker, phone or in the car one fixed sentence a day at the end
        if trace["said"].strip() and not st["mail"] and not st["outside"]:
            import saetze
            tip = saetze.spoken(turn, trace["calls"], chat.guess_language(messages[-1]["content"]) == "English")
            if tip:
                trace["calls"].append({"name": "Beispielsatz (Panel)", "args": "", "result": "gesagt"})
                await out.put({"type": "text", "delta": " " + tip})
                trace["said"] += " " + tip
                await sentences.put(tip)
        zeit = verbrauch.warn(who["id"]) if who else ""
        if zeit:   # Kontingent (verbrauch.py): one fixed sentence under the answer, once per period
            note = verbrauch.warn_text(zeit, chat.guess_language(messages[-1]["content"]) == "English")
            trace["calls"].append({"name": "Kontingent-Vorwarnung (Panel)", "args": "", "result": zeit})
            await out.put({"type": "text", "delta": "\n\n" + note})
            trace["said"] += " " + note
            await sentences.put(note)
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        m = re.match(r"LLM HTTP (\d+)", str(e))
        status = status or (int(m.group(1)) if m else None)
        code = "quota" if isinstance(e, verbrauch.Quota) else chat.llm_error_code(e, status)
        if tr:
            tr.fail(code)
        if (code in chat.LLM_GONE or code == "quota") and not trace["said"].strip():
            # said out loud as well: on a speaker, the watch or in the car nobody reads the error
            en_q = chat.guess_language(messages[-1]["content"]) == "English"
            note = verbrauch.quota_text(e.zeit, en_q) if code == "quota" else chat.LLM_GONE[code]["en" if en_q else "de"]
            if code in chat.LLM_GONE:   # it switches, starts or is measured: say so and for how long (Dominik „3a“)
                note = await llm_start_satz(en_q) or note
            print("chat: language model " + ("not asked: quota" if code == "quota" else "not reachable:"),
                  e.zeit if code == "quota" else code, flush=True)
            await out.put({"type": "text", "delta": note})
            trace["said"] += note
            await sentences.put(note)
        if code != "quota":
            print(f"chat: language model failed ({type(e).__name__}: {str(e)[:300]})", flush=True)
            # to the page only the kind (B2: guests see no addresses or texts from inside), the log keeps the rest
            await out.put({"type": "error", "code": code, "message": f"LLM: {type(e).__name__}"})
    finally:
        stufe.first(vip)
        if who:  # the person can look this up in "Ich" → Protokoll (a few days only)
            try:
                profiles.tool_log_add(who["id"], messages[-1]["content"], trace["calls"], trace["said"])
            except Exception as e:
                print("chat: tool log failed:", type(e).__name__, e, flush=True)
        tm["written"] = True   # the GPU is the speech engine's alone from here on (tts(): less lead)
        await sentences.put(None)
