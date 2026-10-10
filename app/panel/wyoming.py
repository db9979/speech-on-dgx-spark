"""Wyoming for Home Assistant Assist: HA (Voice PE, the HA app, ESPHome speakers) uses the Spark's speech
recognition and voice. Home Assistant → Settings → Integrations → "Wyoming Protocol", host of the Spark,
port 31003; then pick "Spark" for speech-to-text and text-to-speech in the voice assistant.

Off until the admin switches it on (chat.wyoming). Wyoming has no password, so the server only answers
the addresses listed in chat.wyoming_allow (single addresses or networks like 192.168.1.0/24); with an
empty list it answers nobody. It is for the whole house, so there is no profile switch: nothing personal
is reachable, only "audio in, text out" and "text in, audio out".

The protocol (github.com/rhasspy/wyoming): each event is one JSON line {"type", "data"?, "data_length"?,
"payload_length"?}, then data_length bytes of JSON data, then payload_length bytes (audio).
"""
import asyncio
import collections
import io
import ipaddress
import json
import socket
import struct
import wave

import httpx

from urllib.parse import urlsplit

from common import load_config
import notaus

MAX_AUDIO = 16000 * 2 * 120      # two minutes of 16 kHz mono 16 bit
CHUNK = 2048                     # bytes of audio per chunk sent to HA
_server = {"srv": None, "key": None}
_knocked = collections.deque(maxlen=5)   # addresses refused lately, shown to the admin as a hint


def settings():
    c = load_config()
    ch = c.get("chat", {})
    return {"on": bool(ch.get("wyoming", False)), "port": int(ch.get("wyoming_port") or 31003),
            "allow": allowed(ch.get("wyoming_allow", "")), "voice": str(ch.get("wyoming_voice") or ""),
            "asr_port": c["asr"]["port"], "tts_port": c["tts"]["port"],
            "language": c["asr"].get("default_language") or "auto",
            "default_voice": c["tts"].get("default_voice") or ""}


def allowed(text):
    """The networks from the admin's list; ValueError for an entry that is no address."""
    nets = []
    for part in str(text or "").replace(";", ",").replace(" ", ",").split(","):
        if part.strip():
            nets.append(ipaddress.ip_network(part.strip(), strict=False))
    return nets


def permitted(ip, nets):
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return any(a in n for n in nets)


def suggest():
    """Addresses for the admin's list: the hosts of the Home Assistant URLs set up in profiles, resolved
    (only addresses in the home network; behind a reverse proxy the public name points at the proxy, not
    at HA), and the addresses that knocked lately and were refused. Runs in a thread (DNS)."""
    import homeassistant
    import profiles
    hosts, out = [], []
    for uid in profiles.user_ids():
        item = homeassistant._raw(uid)
        host = urlsplit(item["url"]).hostname if item else None
        if host and host not in hosts:
            hosts.append(host)
    for host in hosts[:10]:
        try:
            ips = {a[4][0] for a in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        except (OSError, UnicodeError):
            continue
        for ip in sorted(ips):
            try:
                a = ipaddress.ip_address(ip.split("%")[0])
            except ValueError:
                continue
            if a.is_private and not a.is_loopback and not a.is_link_local and ip not in [x["ip"] for x in out]:
                out.append({"ip": ip, "host": host})
    return {"ha": out, "knocked": list(_knocked)}


# ---------------------------------------------------------------- the protocol
async def read_event(reader):
    line = await reader.readline()
    if not line:
        return None
    head = json.loads(line)
    data = head.get("data") or {}
    if head.get("data_length"):
        data = dict(data, **json.loads(await reader.readexactly(int(head["data_length"]))))
    payload = await reader.readexactly(int(head["payload_length"])) if head.get("payload_length") else b""
    return head.get("type", ""), data, payload


async def write_event(writer, kind, data=None, payload=b""):
    body = json.dumps(data or {}, ensure_ascii=False).encode()
    head = {"type": kind, "version": "1.5.4", "data_length": len(body)}
    if payload:
        head["payload_length"] = len(payload)
    writer.write(json.dumps(head).encode() + b"\n" + body + payload)
    await writer.drain()


ATTR = {"name": "Speech on DGX Spark", "url": "https://github.com/db9979/speech-on-dgx-spark"}


def info(s, voices):
    return {"asr": [{"name": "spark", "description": "Spark Spracherkennung", "attribution": ATTR, "installed": True,
                     "version": None, "models": [{"name": "spark-asr", "description": "Spark ASR", "attribution": ATTR,
                                                  "installed": True, "version": None, "languages": ["de", "en"]}]}],
            "tts": [{"name": "spark", "description": "Spark Stimme", "attribution": ATTR, "installed": True,
                     "version": None, "voices": [{"name": v, "description": v, "attribution": ATTR, "installed": True,
                                                  "version": None, "languages": ["de", "en"], "speakers": None}
                                                 for v in voices]}],
            "handle": [], "intent": [], "wake": [], "mic": [], "snd": []}


def wav_of(pcm, rate, width, channels):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def pcm_of(wav):
    """(rate, width, channels, pcm) of a WAV, also of a streamed one whose sizes are unknown."""
    if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("no WAV")
    pos, fmt = 12, None
    while pos + 8 <= len(wav):
        cid, size = wav[pos:pos + 4], struct.unpack("<I", wav[pos + 4:pos + 8])[0]
        if cid == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", wav[pos + 8:pos + 24])
            fmt = (rate, bits // 8, channels)
        elif cid == b"data":
            if not fmt:
                raise ValueError("WAV without format")
            end = len(wav) if size in (0, 0xFFFFFFFF) else min(len(wav), pos + 8 + size)
            return fmt + (wav[pos + 8:end],)
        pos += 8 + size + (size & 1)
    raise ValueError("WAV without audio")


async def transcribe(s, wav, language):
    from core import api_headers
    lang = language or s["language"]
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f"http://127.0.0.1:{s['asr_port']}/v1/audio/transcriptions", files={"file": ("ha.wav", wav)},
                         data={"language": lang or "auto", "response_format": "json"}, headers=api_headers())
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()


async def synthesize(s, text, voice):
    from core import api_headers
    body = {"input": text[:2000], "response_format": "pcm"}
    v = voice or s["voice"] or s["default_voice"]
    if v:
        body["voice"] = v
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f"http://127.0.0.1:{s['tts_port']}/v1/audio/speech", json=body, headers=api_headers())
    r.raise_for_status()
    # raw PCM as the engine makes it (Qwen3-TTS: 24 kHz, 16 bit, mono); a WAV is read as one
    return pcm_of(r.content) if r.content[:4] == b"RIFF" else (24000, 2, 1, r.content)


async def voices(s):
    from core import api_headers
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"http://127.0.0.1:{s['tts_port']}/v1/voices", headers=api_headers())
        got = [v for v in (r.json() or {}).get("voices", []) if isinstance(v, str)]
    except (httpx.HTTPError, ValueError, AttributeError):
        got = []
    first = s["voice"] or s["default_voice"]
    return ([first] if first else []) + [v for v in got if v != first][:40]


async def handle(reader, writer):
    peer = (writer.get_extra_info("peername") or ("?",))[0]
    s = settings()
    if notaus.refuse("gespraech"):   # Notaus stage 3: no speech for Home Assistant either (notaus.py)
        writer.close()
        return
    if not s["on"] or not permitted(peer, s["allow"]):
        print("wyoming: refused", peer, flush=True)
        shown = str(peer).removeprefix("::ffff:")
        if s["on"] and shown not in _knocked:
            _knocked.append(shown)
        writer.close()
        return
    audio, fmt, language = bytearray(), (16000, 2, 1), ""
    try:
        while True:
            ev = await asyncio.wait_for(read_event(reader), timeout=120)
            if ev is None:
                break
            kind, data, payload = ev
            if notaus.blocks("gespraech"):
                break
            if kind == "describe":
                await write_event(writer, "info", info(s, await voices(s)))
            elif kind == "transcribe":
                language = str(data.get("language") or "")[:8]
            elif kind == "audio-start":
                audio.clear()
                fmt = (int(data.get("rate", 16000)), int(data.get("width", 2)), int(data.get("channels", 1)))
            elif kind == "audio-chunk":
                if len(audio) + len(payload) > MAX_AUDIO:
                    raise ValueError("audio too long")
                audio += payload
            elif kind == "audio-stop":
                text = await transcribe(s, wav_of(bytes(audio), *fmt), language) if audio else ""
                print(f"wyoming: transcript for {peer}: {len(text)} chars", flush=True)
                await write_event(writer, "transcript", {"text": text})
                audio.clear()
            elif kind == "synthesize":
                rate, width, channels, pcm = await synthesize(s, str(data.get("text", "")),
                                                              str((data.get("voice") or {}).get("name") or ""))
                fmt_out = {"rate": rate, "width": width, "channels": channels}
                await write_event(writer, "audio-start", fmt_out)
                for i in range(0, len(pcm), CHUNK):
                    await write_event(writer, "audio-chunk", fmt_out, pcm[i:i + CHUNK])
                await write_event(writer, "audio-stop")
                print(f"wyoming: spoke {len(pcm)} bytes for {peer}", flush=True)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
        pass
    except Exception as e:
        print("wyoming:", type(e).__name__, str(e)[:160], flush=True)
        try:
            await write_event(writer, "error", {"text": "Spark: " + type(e).__name__})
        except Exception:
            pass
    finally:
        writer.close()


async def loop():
    """Keeps the server running as the settings say (switched on, port); checks every 5 seconds."""
    while True:
        try:
            s = settings()
            key = s["port"] if s["on"] else None
            if key != _server["key"]:
                if _server["srv"]:
                    _server["srv"].close()
                    _server["srv"] = None
                _server["key"] = key     # set first: a busy port is reported once, not every 5 seconds
                if key:
                    _server["srv"] = await asyncio.start_server(handle, host=None, port=key)
                    print("wyoming: listening on port", key, flush=True)
        except Exception as e:
            print("wyoming: server", type(e).__name__, str(e)[:160], flush=True)
        await asyncio.sleep(5)
