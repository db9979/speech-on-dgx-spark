"""chat_ton.py: the speech output of an answer, cut out of chat._answer (plan Aufräumen, Richtlinie Teil 17).
Same code, same order; chat._answer hands every value over by name."""
import asyncio
import chat
import echo
import httpx
import json
import latency
import re
import time
import verbrauch
import vorrang
from textnorm import speakable


async def speech_out(*, body, c, device_owner, messages, out, play_clip, request, sentences, t0, tm, tr, tts_body, tts_headers,
                     tts_url, who):
    """The speech output of one answer (was chat._answer's inner tts): takes the finished sentences, asks the speech
    service piece by piece and streams the sound. Every value comes from chat._answer by name; names of chat.py are read
    as chat.NAME at call time, so a test that patches chat still reaches them."""
    first, played_until, ttfa = True, 0.0, 0.5
    mute = body.get("speak") is False  # text only (Siri) or speech output failed: no TTS
    done = False
    said = {"start": None, "pieces": 0, "chars": 0, "behind": 0, "waited": 0, "overtook": 0, "empty": 0,
            "sec": 0.0}   # for Logs → Anfragen and the Verbrauchszähler (seconds of audio)
    waits = list(chat.TTS_WAITS)   # this answer's patience with a speech service that restarts
    try:
        while not done:
            text = await sentences.get()
            if text is None:
                break
            if isinstance(text, tuple):   # a ready-made sentence (ack.py): from its recording, no TTS request
                if not mute and not (text[2] == "bridge" and said["pieces"]):
                    played_until = await play_clip(text[1], text[2], played_until)
                continue
            if mute:
                continue
            # Every TTS request starts its own intonation, so sentence-by-sentence speech
            # wanders in tone. Only the first sentence goes alone (fast first audio); after
            # that, everything the LLM has written meanwhile is spoken as one piece.
            # Waiting for more text is fine while the listener still has buffered audio; the
            # next request starts while enough is left to cover its time to first audio and
            # its second audio block (slower while the LLM shares the GPU), so nothing stalls.
            margin = chat.piece_margin(ttfa, not tm.get("written"), tts_body.get("speed"))
            while not first and len(text) < 300:
                slack = played_until - time.time() - margin
                try:
                    nxt = (sentences.get_nowait() if not sentences.empty() or slack <= 0
                           else await asyncio.wait_for(sentences.get(), slack))
                except (asyncio.QueueEmpty, asyncio.TimeoutError):
                    break
                if nxt is None:
                    done = True
                    break
                if isinstance(nxt, tuple):   # a bridge sentence that came too late: the answer runs already
                    continue
                # a new line only before list items (clean_text strips their markers); plain
                # sentences stay one paragraph, so the voice does not reset at each line
                text += ("\n" if re.match(r"\s*(?:[-*+•]|\d+\.)\s", nxt) else " ") + nxt
            if not speakable(text):   # only "---", an emoji, a link or "Haha!": nothing to say, the TTS would refuse it
                said["empty"] += 1
                continue
            if "language" not in tts_body:  # one language for the whole answer
                lang = chat.guess_language(" ".join([messages[-1]["content"], text]))
                if lang:
                    tts_body["language"] = lang
            req = dict(tts_body, input=text, stream=True, response_format="pcm")
            said["start"] = said["start"] or time.time()
            said["pieces"] += 1
            said["chars"] += len(text)
            await out.put({"type": "tts_request", "chars": len(text)})  # for the stall details in the chat
            # A broken stream (engine restarted, ReadError) costs this piece, never the rest of the
            # answer: a piece that brought no audio yet is tried once more, then the next one goes on.
            # Not reachable or 502/503 (restarting, e.g. ~8 s during an update): tried again after 0.5/1/2/4 s
            # (TTS_WAITS, at most once per answer in all), before the answer goes on as text only.
            attempt = 0
            while True:
                attempt += 1
                sent, got, mine = time.time(), False, None
                try:
                    async with c.stream("POST", tts_url, json=req, headers=tts_headers) as r:
                        for k, h in (("waited", "x-spark-wait-ms"), ("overtook", "x-spark-overtook")):
                            v = r.headers.get(h, "")   # how long it queued in the TTS (common.PrioGate)
                            said[k] += int(v) if v.isdigit() and len(v) < 7 else 0
                        if r.status_code != 200:
                            detail = (await r.aread()).decode(errors='replace')[:300]
                            if r.status_code in (502, 503) and waits:
                                raise chat.TtsAgain(f"HTTP {r.status_code}")
                            why = chat.tts_refusal(r.status_code, detail)
                            if why == "empty":   # nothing left to speak in this piece: the next one goes on
                                print("chat: tts HTTP 400, nothing to speak in this piece - skipped", flush=True)
                                said["empty"] += 1
                                break
                            print(f"chat: tts HTTP {r.status_code} ({why}), this answer stays text only", flush=True)
                            if tr:
                                tr.fail(f"tts_{why}" if why != "other" else f"tts_http_{r.status_code}")
                            await out.put({"type": "error", "code": "tts_loading" if r.status_code == 503 and "loading" in detail
                                           else "tts_down" if r.status_code in (502, 503) else "tts_error",
                                           "message": f"TTS HTTP {r.status_code}: {detail}"})
                            mute = True
                            break
                        async for line in r.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            try:
                                ev = json.loads(line[5:])
                            except ValueError:
                                continue
                            if ev.get("type") == "speech.audio.delta" and ev.get("audio"):
                                now, opening = time.time(), not got
                                if not got:
                                    got, ttfa = True, now - sent
                                    # this piece plays from here on: another device of the house that hears it
                                    # does not take it for a question (echo.py)
                                    mine = echo.said(text, device_owner and device_owner["id"], echo.device_of(request),
                                                     start=max(now, played_until))
                                if first:
                                    first = False
                                    played_until = max(played_until, now)   # (after a ready-made sentence)
                                    tm["audio"] = now
                                    if tr:
                                        tr.mark("sound", now)
                                    await out.put({"type": "timing", "first_audio": round(now - t0, 3)})
                                    try:  # for Zustand → Prüfen: how long people wait (latency.py)
                                        await asyncio.to_thread(latency.add, now - t0, body.get("client") or "web")
                                    except (OSError, ValueError) as e:
                                        print("latency:", type(e).__name__, flush=True)
                                elif now > played_until + 0.3:
                                    # the listener ran out of audio (Zustand → Logs, "chat:"): before a piece it is a
                                    # pause between sentences (the text was not there yet: tool, search, slow LLM),
                                    # inside a piece the speech engine was slower than real time (a real stall)
                                    print(f"chat: tts behind by {now - played_until:.1f} s "
                                          f"{'before the piece' if opening else 'inside the piece'} ({len(text)} chars, "
                                          f"first audio after {ttfa:.1f} s)", flush=True)
                                    if not opening:
                                        vorrang.count("behind")   # Zustand → Prüfen, "Vorrang für Sprache"
                                        said["behind"] += 1
                                # 16-bit mono PCM at 24 kHz: 48000 bytes per second of audio
                                played_until = max(played_until, now) + len(ev["audio"]) * 3 / 4 / 48000
                                said["sec"] += len(ev["audio"]) * 3 / 4 / 48000
                                echo.played(mine, played_until)
                                await out.put({"type": "audio", "audio": ev["audio"]})
                            elif ev.get("type") == "speech.audio.error":
                                await out.put({"type": "error", "message": f"TTS: {ev.get('error')}"})
                    break
                except (chat.TtsAgain, httpx.ConnectError, httpx.ConnectTimeout) as e:
                    if not waits:
                        raise
                    wait = waits.pop(0)
                    print(f"chat: tts not ready ({type(e).__name__} {e}"[:120] + f"), again in {wait} s", flush=True)
                    await asyncio.sleep(wait)
                except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
                    print(f"chat: tts stream broke ({type(e).__name__}, {len(text)} chars, "
                          f"{'with' if got else 'no'} audio, try {attempt})", flush=True)
                    if got or attempt >= 2:
                        if tr:
                            tr.fail("tts_error")
                        await out.put({"type": "error", "code": "tts_error", "message": f"TTS: {type(e).__name__}"})
                        break
                    await asyncio.sleep(0.5)
    except Exception as e:
        code = "tts_down" if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, chat.TtsAgain)) else "tts_error"
        print(f"chat: tts failed ({type(e).__name__}), the rest of this answer stays text only", flush=True)
        if tr:
            tr.fail(code)
        await out.put({"type": "error", "code": code, "message": f"TTS: {type(e).__name__}"})
        while not done and await sentences.get() is not None:  # the text still comes to the end
            pass
    finally:
        verbrauch.audio("tts", "Antwort sprechen", said["sec"],
                        int((time.time() - said["start"]) * 1000) if said["start"] else 0, verbrauch.who_of(who))
        if tr and said["start"]:
            tr.step("tts", "Sprachausgabe", said["start"], time.time(), pieces=said["pieces"], chars=said["chars"],
                    behind=said["behind"] or None, waited_ms=said["waited"] or None, overtook=said["overtook"] or None,
                    empty=said["empty"] or None)
        await out.put(None)
