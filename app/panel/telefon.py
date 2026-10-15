"""Telefon: den Spark anrufen (plan plaene/telefon-anruf.md, Stufe T1). The Spark signs in at the home's telephone system
(FRITZ!Box or any SIP PBX) as an IP phone; a handset in the house calls its internal number (FRITZ!Box: **620) and talks
to it like to an own speaker: question, answer, "Stopp" or #, hang up.

Off until the admin switches it on (chat.telefon) and enters the access under Funktionen → Telefon (a wizard with four
steps: pick the PBX from telefonanlagen.json, add the Spark there, enter and check the access, test call and assign the
handsets). Once on, it works for every profile the admin did not block.

Who is calling (fixed rules here, never the model):
    internal number assigned to a profile   that profile; personal things only when the voice is clearly its own
                                            (speakers.verify, as at an own speaker: chat_turn.shared_stranger)
    internal number marked "gemeinsam"      the voice picks the profile for each question (speakers.identify);
                                            no clear voice: questions and answers as a guest
    internal number not assigned            the Spark says so and hangs up (the admin sees the number in step 4);
                                            with chat.telefon_gaeste: questions and answers as a guest
    external number                         refused (T3 brings calls from outside)

The network part, all UDP in the home network only:
    SIP  port SIP_PORT (31060)              REGISTER with digest (MD5, SHA-256), INVITE, ACK, BYE, CANCEL, OPTIONS, INFO;
                                            messages only from the PBX's address, at most MAX_MSG bytes, only these
                                            methods; everything else is dropped and counted
    RTP  ports RTP_PORTS (31062-31068)      G.722 or G.711 (telefon_ton.py), DTMF after RFC 4733; packets only from the
                                            address the PBX named in its SDP, which must be in the home network
The PBX's name has to resolve to an address in the home network (netguard.resolve at HOME and a private address).
Nothing of the sound is stored; the questions and answers go into the profile's history like at a speaker.

    STATE/telefon.json  {"zugang": {"anlage", "host", "port", "user", "pw" (vault)}, "nummern": {number: {"uid", "name"}},
                         "gesehen": [{"nr", "t"}]  (internal numbers that called lately, for step 4)}
"""
import asyncio
import collections
import datetime
import hashlib
import ipaddress
import json
import os
import random
import re
import secrets
import socket
import struct
import threading
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
import telefon_ton
import vault
from common import STATE, DayCounter, load_config, read_json, write_json
from core import admin_code, auth, json_body

router = APIRouter()

FILE = os.path.join(STATE, "telefon.json")
PRESETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "telefonanlagen.json")
SIP_PORT = 31060
RTP_PORTS = (31062, 31064, 31066, 31068)   # even ports (RTCP would take the odd one after, the Spark sends none)
MAX_MSG = 4096                  # bytes of one SIP message
MAX_HEADERS = 60
PER_SECOND = 100                # SIP messages from the PBX per second, more are dropped
REG_EXPIRES = 600               # seconds the registration is asked for; renewed after half
REG_RETRY = 60                  # seconds until a failed registration is tried again
RING = 0.8                      # seconds the caller hears ringing before the Spark answers
MAX_CALL = 15 * 60              # one call ends after this
QUIET_ASK, QUIET_END = 20, 10   # silence: "Noch etwas?" after the first, hang up after the second
MAX_CALLS = 2                   # chat.telefon_max at most
SEEN_MAX = 10
UA = "Speech-on-DGX-Spark"
METHODS = ("INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "INFO", "NOTIFY")
DTMF = "0123456789*#ABCD"
BYE_WORDS = re.compile(r"(?i)^\W*(?:(?:ok|okay|gut|danke)\W+)*(?:tschüss|tschüs|ciao|auf wiederhören|auf wiedersehen|bis dann|"
                       r"bis später|leg auf|auflegen|das war'?s|das wars|ende|bye|goodbye)\W*(?:danke|spark)?\W*$")
_lock = threading.Lock()


# ---------------------------------------------------------------- settings and stored access
def settings(c=None):
    c = c or load_config()
    ch = c.get("chat", {})
    try:
        most = max(1, min(MAX_CALLS, int(ch.get("telefon_max") or 1)))
    except (TypeError, ValueError):
        most = 1
    return {"on": features.admin_on("telefon", c), "ton": "schmal" if ch.get("telefon_ton") == "schmal" else "hd",
            "gaeste": features.admin_on("telefongast", c), "max": most}


def _read():
    return read_json(FILE, {})


def _write(d):
    write_json(FILE, d)


def presets():
    d = read_json(PRESETS, {})
    return [a for a in d.get("anlagen", []) if isinstance(a, dict) and a.get("id")]


def preset(pid):
    return next((a for a in presets() if a["id"] == pid), None) or next(a for a in presets() if a["id"] == "andere")


def zugang():
    """The access to the PBX with the plain password ("" when none is set)."""
    z = dict(_read().get("zugang") or {})
    z["pw"] = vault.open_(z.get("pw", "")) or ""
    return z


def ready(z=None):
    z = z if z is not None else zugang()
    return bool(z.get("host") and z.get("user") and z.get("pw"))


def nummern():
    return dict(_read().get("nummern") or {})


def clean_number(n):
    """Only digits, *, # and + (what a PBX shows as a number), at most 32 characters."""
    return re.sub(r"[^\d*#+]", "", urllib.parse.unquote(str(n or "")))[:32]


def internal(number, anlage=None):
    """Whether this number is an internal one of the PBX (by its preset), e.g. **611 at a FRITZ!Box."""
    if not number:
        return False
    rx = preset(anlage or zugang().get("anlage") or "andere").get("intern") or r"^\d{1,5}$"
    return bool(re.fullmatch(rx, number))


def lan_ip(ip):
    """An address in the home network: private, not this machine's loopback, not link-local."""
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    return a.version == 4 and a.is_private and not a.is_loopback and not a.is_link_local and not a.is_unspecified


def resolve(host, port):
    """The PBX's address: through the Wächter at HOME, and it has to be in the home network (ValueError)."""
    import netguard
    try:
        ip = netguard.resolve(host, port, netguard.HOME)
    except netguard.Blocked:
        raise ValueError("blocked")
    except Exception:
        raise ValueError("name")
    if not lan_ip(ip):
        raise ValueError("lan")
    return ip


# ---------------------------------------------------------------- what the admin page and the log say
SAY = {"ok": ("Angemeldet.", "Signed in."),
       "zugang": ("Benutzername oder Kennwort falsch. Bitte in der Telefonanlage nachsehen und neu eintragen.",
                  "User name or password wrong. Please look them up in the PBX and enter them again."),
       "unbekannt": ("Die Anlage kennt diesen Benutzernamen nicht.", "The PBX does not know this user name."),
       "stumm": ("Die Anlage antwortet nicht. Ist die Adresse richtig und die Anlage an?",
                 "The PBX does not answer. Is the address right and the PBX on?"),
       "verboten": ("Die Anlage lehnt Anmeldungen aus dem Heimnetz ab. In der Anlage das IP-Telefon „Spark“ prüfen.",
                    "The PBX refuses sign-ins from the home network. Check the IP phone \"Spark\" in the PBX."),
       "name": ("Diese Adresse findet der Spark nicht.", "The Spark cannot find this address."),
       "lan": ("Die Telefonanlage muss im Heimnetz stehen (eine Adresse wie 192.168.178.1).",
               "The PBX has to be in the home network (an address like 192.168.178.1)."),
       "blocked": ("Der Wächter erlaubt diese Adresse nicht.", "The Wächter does not allow this address."),
       "abgelehnt": ("Die Anlage lehnt die Anmeldung ab.", "The PBX refuses the sign-in."),
       "port": ("Der Telefon-Port 31060 ist auf diesem Rechner schon belegt.", "The phone port 31060 is already in use on this computer."),
       "aus": ("Ausgeschaltet.", "Switched off."), "fehlt": ("Noch nicht eingerichtet.", "Not set up yet.")}


# ---------------------------------------------------------------- SIP messages
COMPACT = {"v": "via", "f": "from", "t": "to", "i": "call-id", "m": "contact", "l": "content-length", "c": "content-type",
           "k": "supported"}


class Msg:
    __slots__ = ("method", "uri", "code", "reason", "headers", "body")

    def __init__(self):
        self.method, self.uri, self.code, self.reason, self.headers, self.body = "", "", 0, "", {}, ""

    def get(self, name, default=""):
        v = self.headers.get(name)
        return v[0] if v else default

    def all(self, name):
        return list(self.headers.get(name) or [])

    def cseq(self):
        """(number, method) of the CSeq header, (0, "") when broken."""
        m = re.fullmatch(r"\s*(\d{1,9})\s+([A-Z]{3,10})\s*", self.get("cseq"))
        return (int(m.group(1)), m.group(2)) if m else (0, "")


def parse(data):
    """A SIP message from bytes, None for anything that is not one (too large, not UTF-8, broken lines)."""
    if not data or len(data) > MAX_MSG:
        return None
    head, sep, body = data.partition(b"\r\n\r\n")
    if not sep:
        head, sep, body = data.partition(b"\n\n")
    try:
        lines = head.decode("utf-8").replace("\r\n", "\n").split("\n")
        body = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    m = Msg()
    first = lines[0].split(" ", 2)
    if first[0] == "SIP/2.0" and len(first) >= 2 and re.fullmatch(r"[1-6]\d\d", first[1]):
        m.code, m.reason = int(first[1]), (first[2] if len(first) > 2 else "")[:80]
    elif len(first) == 3 and first[2] == "SIP/2.0" and re.fullmatch(r"[A-Z]{3,10}", first[0]) and len(first[1]) <= 256 \
            and re.fullmatch(r"sips?:[^\s<>\"]+", first[1]):
        m.method, m.uri = first[0], first[1]
    else:
        return None
    count = 0
    last = None
    for line in lines[1:]:
        if not line:
            continue
        if line[0] in " \t" and last:       # a folded line continues the header before
            m.headers[last][-1] = (m.headers[last][-1] + " " + line.strip())[:1024]
            continue
        name, colon, value = line.partition(":")
        name = name.strip().lower()
        if not colon or not re.fullmatch(r"[a-z0-9!%*_+`'~.-]{1,40}", name):
            return None
        count += 1
        if count > MAX_HEADERS:
            return None
        name = COMPACT.get(name, name)
        m.headers.setdefault(name, []).append(value.strip()[:1024])
        last = name
    for need in ("call-id", "cseq", "from", "to", "via"):
        if not m.headers.get(need):
            return None
    n = m.get("content-length")
    if n:
        if not n.isdigit() or int(n) > len(body.encode()):
            return None
        body = body.encode()[:int(n)].decode("utf-8", "replace")
    m.body = body
    return m


def tag_of(header):
    m = re.search(r";\s*tag=([^;\s,>]+)", header or "")
    return m.group(1) if m else ""


def uri_of(header):
    """The URI inside <...> of a From, To or Contact header (or the plain one)."""
    m = re.search(r"<([^>]+)>", header or "")
    u = (m.group(1) if m else (header or "").split(";")[0]).strip()
    return u if re.fullmatch(r"sips?:[^\s<>\"]{1,200}", u) else ""


def number_of(msg):
    """The caller's number: what the PBX asserts, else the From header's user part ("" when hidden)."""
    for h in ("p-asserted-identity", "remote-party-id", "from"):
        m = re.search(r"(?:sips?|tel):([^@;>\s]+)", msg.get(h))
        if m:
            n = clean_number(m.group(1))
            if n:
                return n
    return ""


def response(req, code, reason, to_tag="", extra=(), body="", ctype="application/sdp"):
    lines = [f"SIP/2.0 {code} {reason}"]
    lines += ["Via: " + v for v in req.all("via")]
    to = req.get("to")
    if to_tag and not tag_of(to):
        to += ";tag=" + to_tag
    lines += ["From: " + req.get("from"), "To: " + to, "Call-ID: " + req.get("call-id"), "CSeq: " + req.get("cseq")]
    if req.method == "INVITE" and 200 <= code < 300:
        lines += ["Record-Route: " + r for r in req.all("record-route")]
    lines += list(extra) + [f"User-Agent: {UA}"]
    if body:
        lines.append(f"Content-Type: {ctype}")
    lines.append(f"Content-Length: {len(body.encode())}")
    return ("\r\n".join(lines) + "\r\n\r\n" + body).encode()


def request(method, uri, headers, body="", ctype="application/sdp"):
    lines = [f"{method} {uri} SIP/2.0"] + list(headers) + [f"User-Agent: {UA}"]
    if body:
        lines.append(f"Content-Type: {ctype}")
    lines.append(f"Content-Length: {len(body.encode())}")
    return ("\r\n".join(lines) + "\r\n\r\n" + body).encode()


def branch():
    return "z9hG4bK" + secrets.token_hex(8)


# ---------------------------------------------------------------- digest sign-in (RFC 7616: MD5 and SHA-256, qop auth)
def digest(challenge, method, uri, user, pw, nc=1, cnonce=None):
    p = {k.lower(): (q if q or not plain else plain) for k, q, plain in
         re.findall(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s,]+))', challenge or "")}
    algo = (p.get("algorithm") or "MD5").upper()
    if algo not in ("MD5", "SHA-256") or not p.get("nonce"):
        raise ValueError("digest not supported")
    h = (lambda s: hashlib.md5(s.encode()).hexdigest()) if algo == "MD5" else (lambda s: hashlib.sha256(s.encode()).hexdigest())
    realm, nonce = p.get("realm", ""), p["nonce"]
    ha1, ha2 = h(f"{user}:{realm}:{pw}"), h(f"{method}:{uri}")
    qops = [q.strip() for q in p.get("qop", "").split(",") if q.strip()]
    out = f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}", algorithm={algo}'
    if "auth" in qops:
        cnonce = cnonce or secrets.token_hex(8)
        resp = h(f"{ha1}:{nonce}:{nc:08x}:{cnonce}:auth:{ha2}")
        out += f', response="{resp}", qop=auth, nc={nc:08x}, cnonce="{cnonce}"'
    else:
        out += f', response="{h(f"{ha1}:{nonce}:{ha2}")}"'
    if p.get("opaque"):
        out += f', opaque="{p["opaque"]}"'
    return out


# ---------------------------------------------------------------- SDP
def sdp_offer(ip, port, pts, sid):
    lines = ["v=0", f"o=spark {sid} {sid} IN IP4 {ip}", "s=Spark", f"c=IN IP4 {ip}", "t=0 0",
             f"m=audio {port} RTP/AVP {' '.join(str(p) for p in pts)} 101"]
    for pt in pts:
        name, clock = telefon_ton.CODECS[pt][:2]
        lines.append(f"a=rtpmap:{pt} {name}/{clock}")
    lines += ["a=rtpmap:101 telephone-event/8000", "a=fmtp:101 0-16", "a=ptime:20", "a=sendrecv"]
    return "\r\n".join(lines) + "\r\n"


def sdp_parse(body):
    """{"ip", "port", "pts", "dtmf"} of the first audio stream, None when there is none."""
    ip, port, pts, dtmf, names = "", 0, [], None, {}
    in_audio = False
    for line in (body or "").replace("\r\n", "\n").split("\n")[:80]:
        line = line.strip()
        if line.startswith("c=IN IP4 ") and (not ip or in_audio):
            ip = line[9:].split("/")[0].strip()
        elif line.startswith("m="):
            if in_audio:
                break
            parts = line[2:].split()
            if len(parts) >= 4 and parts[0] == "audio" and parts[1].isdigit():
                in_audio, port = True, int(parts[1])
                pts = [int(x) for x in parts[3:] if x.isdigit() and int(x) < 128]
        elif in_audio and line.startswith("a=rtpmap:"):
            m = re.fullmatch(r"a=rtpmap:(\d{1,3}) ([\w.-]+)/(\d+).*", line)
            if m:
                names[int(m.group(1))] = m.group(2).lower()
    if not in_audio or not 0 < port < 65536:
        return None
    dtmf = next((pt for pt, n in names.items() if n == "telephone-event" and pt in pts), None)
    return {"ip": ip, "port": port, "pts": pts, "dtmf": dtmf, "names": names}


def choose(sdp, ton="hd"):
    """The first codec the Spark prefers that the other side offers (by number or name)."""
    want = telefon_ton.PREFER if ton == "hd" else tuple(p for p in telefon_ton.PREFER if p != 9)
    offered = set(sdp["pts"]) | {pt for pt, (n, *_x) in telefon_ton.CODECS.items()
                                 if n.lower() in {sdp["names"].get(x) for x in sdp["pts"]}}
    return next((p for p in want if p in offered), None)


# ---------------------------------------------------------------- numbers of today (Live, admin page)
_today = DayCounter(angenommen=0, abgelehnt=0, besetzt=0, fragen=0, sekunden=0, fremd=0, kaputt=0)
_recent = collections.deque(maxlen=20)   # finished calls: {"t", "art", "nr" (internal only), "who", "s", "fragen"}


def _bump(k, n=1):
    _today.bump(k, n)


def _log_name(uid):
    """A profile in a log line (profiles.log_name: a name only with its consent), "gast" without one."""
    p = profiles.by_id(uid) if uid else None
    return profiles.log_name(p) if p else "gast"


# ---------------------------------------------------------------- the SIP part
class Agent(asyncio.DatagramProtocol):
    """The Spark as an IP phone at the PBX: one UDP socket, the registration and the calls."""

    def __init__(self):
        self.transport = None
        self.pbx = None             # (ip, port)
        self.local = ""             # this machine's address towards the PBX
        self.port = 0
        self.z = {}
        self.reg = {"ok": False, "why": "fehlt", "t": 0.0, "until": 0.0}
        self.cseq = random.randint(1, 1000)
        self.reg_cid = secrets.token_hex(10)
        self.tag = secrets.token_hex(6)
        self.pending = {}           # (call-id, cseq, method) -> Future of the final answer
        self.calls = {}             # call-id -> Call
        self.sec = [0.0, 0]         # the second and the messages in it
        self.closing = False

    # ------------------------------------------------------------ socket
    async def open(self, z, ip):
        self.z, self.pbx = z, (ip, int(z.get("port") or 5060))
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(self.pbx)          # no packet goes out: only asks which address the way out has
            self.local = probe.getsockname()[0]
        finally:
            probe.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", SIP_PORT))
        except OSError:
            sock.close()
            raise
        await asyncio.get_running_loop().create_datagram_endpoint(lambda: self, sock=sock)
        self.port = sock.getsockname()[1]

    def connection_made(self, transport):
        self.transport = transport

    def close(self):
        self.closing = True
        for c in list(self.calls.values()):
            c.end("aus")
            if c.rtp and c.rtp.transport:
                c.rtp.transport.close()
        if self.transport:
            self.transport.close()
        for f in self.pending.values():
            if not f.done():
                f.cancel()

    def send(self, data, addr=None):
        if self.transport and not self.transport.is_closing():
            self.transport.sendto(data, addr or self.pbx)

    def datagram_received(self, data, addr):
        if not self.pbx or addr[0] != self.pbx[0]:
            _bump("fremd")
            return
        now = time.monotonic()
        if now - self.sec[0] >= 1:
            self.sec = [now, 0]
        self.sec[1] += 1
        if self.sec[1] > PER_SECOND:
            return
        msg = parse(data)
        if msg is None:
            _bump("kaputt")
            return
        if msg.code:
            num, meth = msg.cseq()
            f = self.pending.get((msg.get("call-id"), num, meth))
            if f and not f.done() and msg.code >= 200:
                f.set_result(msg)
            return
        try:
            self.on_request(msg, addr)
        except Exception as e:
            print("telefon: anfrage fehler", type(e).__name__, flush=True)

    # ------------------------------------------------------------ our requests (with retransmission)
    async def transact(self, data, key, total=8.0):
        fut = asyncio.get_running_loop().create_future()
        self.pending[key] = fut
        try:
            wait, end = 0.5, time.monotonic() + total
            while True:
                self.send(data)
                try:
                    return await asyncio.wait_for(asyncio.shield(fut), wait)
                except asyncio.TimeoutError:
                    if time.monotonic() >= end:
                        return None
                    wait = min(wait * 2, 4.0)
        finally:
            self.pending.pop(key, None)

    def _domain(self):
        return self.z.get("host") or self.pbx[0]

    async def register(self, expires=REG_EXPIRES):
        """Signs in (or out with expires=0); sets self.reg and returns its "why" ("ok" when signed in)."""
        user, dom = self.z["user"], self._domain()
        uri = f"sip:{dom}"
        auth_line, why, nc = "", "stumm", 0
        for _ in range(3):
            self.cseq += 1
            heads = [f"Via: SIP/2.0/UDP {self.local}:{self.port};branch={branch()};rport", "Max-Forwards: 70",
                     f"From: <sip:{user}@{dom}>;tag={self.tag}", f"To: <sip:{user}@{dom}>", f"Call-ID: {self.reg_cid}",
                     f"CSeq: {self.cseq} REGISTER", f"Contact: <sip:{user}@{self.local}:{self.port}>",
                     f"Expires: {expires}", "Allow: " + ", ".join(METHODS)] + ([auth_line] if auth_line else [])
            r = await self.transact(request("REGISTER", uri, heads), (self.reg_cid, self.cseq, "REGISTER"))
            if r is None:
                why = "stumm"
                break
            if r.code in (401, 407) and not auth_line:
                try:
                    nc += 1
                    head = "Authorization" if r.code == 401 else "Proxy-Authorization"
                    chal = r.get("www-authenticate" if r.code == 401 else "proxy-authenticate")
                    auth_line = f"{head}: " + digest(chal, "REGISTER", uri, user, self.z["pw"], nc)
                    continue
                except ValueError:
                    why = "abgelehnt"
                    break
            why = "ok" if 200 <= r.code < 300 else "zugang" if r.code in (401, 407, 403) and auth_line \
                else "verboten" if r.code == 403 else "unbekannt" if r.code == 404 else "abgelehnt"
            if why == "ok" and expires:
                m = re.search(r";\s*expires=(\d+)", r.get("contact")) or re.fullmatch(r"\s*(\d+)\s*", r.get("expires") or "")
                expires = max(60, min(int(m.group(1)), 3600)) if m else expires
            break
        if expires:
            self.reg = {"ok": why == "ok", "why": why, "t": time.time(), "until": time.time() + (expires if why == "ok" else 0),
                        "code": getattr(r, "code", 0) if why != "ok" else 0}
        return why

    # ------------------------------------------------------------ requests from the PBX
    def on_request(self, msg, addr):
        meth = msg.method
        cid = msg.get("call-id")
        call = self.calls.get(cid)
        if meth == "ACK":
            if call:
                call.acked.set()
            return
        if meth not in METHODS:
            self.send(response(msg, 405, "Method Not Allowed", extra=["Allow: " + ", ".join(METHODS)]), addr)
            return
        if meth == "OPTIONS":
            self.send(response(msg, 200, "OK", extra=["Allow: " + ", ".join(METHODS), "Accept: application/sdp"]), addr)
            return
        if meth == "INVITE":
            if call:
                if msg.cseq() == call.invite.cseq():          # the same INVITE again: the answer again
                    if call.last:
                        self.send(call.last, addr)
                else:                                          # a new offer in the call (hold, other codec): same answer
                    self.send(response(msg, 200, "OK", call.tag, call.contact(), call.sdp), addr)
                return
            if self.closing:
                self.send(response(msg, 480, "Temporarily Unavailable"), addr)
                return
            Call.start(self, msg, addr)
            return
        if meth == "CANCEL":
            self.send(response(msg, 200, "OK"), addr)
            if call and not call.answered:
                call.cancelled = True
                self.send(response(call.invite, 487, "Request Terminated", call.tag), addr)
                call.end("abgebrochen")
            return
        if meth == "BYE":
            self.send(response(msg, 200 if call else 481, "OK" if call else "Call Does Not Exist"), addr)
            if call:
                call.end("aufgelegt", by_peer=True)
            return
        if meth == "INFO":
            self.send(response(msg, 200, "OK"), addr)
            m = re.search(r"(?im)^\s*signal\s*=\s*([0-9*#A-D])", msg.body or "")
            if call and m:
                call.digit(m.group(1))
            return
        self.send(response(msg, 200, "OK"), addr)          # NOTIFY (message summary and the like)


# ---------------------------------------------------------------- one call
class Rtp(asyncio.DatagramProtocol):
    def __init__(self, call):
        self.call = call
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.call.rtp_in(data, addr)


def _rtp_port():
    """A free RTP socket from RTP_PORTS (None when all are taken)."""
    for port in RTP_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", port))
            return s
        except OSError:
            s.close()
    return None


class Call:
    """An incoming call: answer, greet, listen, ask the chat, speak, until someone hangs up."""

    def __init__(self, agent, invite, addr, number, uid, shared, sdp, pt, known=True):
        self.agent, self.invite, self.addr = agent, invite, addr
        self.number, self.uid, self.shared, self.known = number, uid, shared, known
        self.cid = invite.get("call-id")
        self.tag = secrets.token_hex(6)
        self.remote = sdp
        self.codec = telefon_ton.Codec(pt)
        self.dtmf_pt = sdp.get("dtmf")
        self.sdp = ""
        self.last = b""
        self.answered = self.cancelled = False
        self.acked = asyncio.Event()
        self.over = asyncio.Event()
        self.why = ""
        self.by_peer = False
        self.t0 = time.time()
        self.inbuf = collections.deque(maxlen=250)      # 5 s of payloads
        self.got = asyncio.Event()
        self.outq = collections.deque()
        self.digits = collections.deque(maxlen=20)
        self.last_dtmf = None
        self.rtp = None
        self.sock = None
        self.history = []
        self.questions = 0
        self.ours = 0                                     # CSeq of our own requests in this dialog
        self.tasks = []
        self.rest = b""

    # ------------------------------------------------------------ start and end
    @staticmethod
    def start(agent, msg, addr):
        s = settings()
        number = number_of(msg)
        if len(agent.calls) >= s["max"]:
            agent.send(response(msg, 486, "Busy Here"), addr)
            _bump("besetzt")
            print("telefon: besetzt", flush=True)
            return
        import notaus
        if notaus.refuse("gespraech"):
            agent.send(response(msg, 480, "Temporarily Unavailable"), addr)
            _bump("abgelehnt")
            print("telefon: anruf abgelehnt, notaus", flush=True)
            return
        if not internal(number, agent.z.get("anlage")):
            # calls from outside come with stage T3; a hidden number is never internal
            agent.send(response(msg, 603, "Decline"), addr)
            _bump("abgelehnt")
            print("telefon: anruf extern abgelehnt", flush=True)
            return
        entry = nummern().get(number)
        if entry and entry.get("uid") and not profiles.by_id(entry["uid"]):
            entry = None                       # its profile is gone: as not assigned
        if not entry:
            seen(number)
        uid, shared = "", False
        if entry:
            shared = not entry.get("uid")
            if entry.get("uid"):
                p = profiles.by_id(entry["uid"])
                if p and features.allowed("telefon", p["id"]):
                    uid = p["id"]
                else:
                    agent.send(response(msg, 403, "Forbidden"), addr)
                    _bump("abgelehnt")
                    print(f"telefon: anruf intern {number} abgelehnt, telefon fuer {_log_name(p['id'])} gesperrt", flush=True)
                    return
        sdp = sdp_parse(msg.body)
        pt = choose(sdp, s["ton"]) if sdp else None
        if not sdp or pt is None or not lan_ip(sdp["ip"]) and sdp["ip"] != agent.pbx[0]:
            agent.send(response(msg, 488, "Not Acceptable Here"), addr)
            _bump("abgelehnt")
            print("telefon: anruf abgelehnt, keine gemeinsame tonart oder adresse nicht im heimnetz", flush=True)
            return
        call = Call(agent, msg, addr, number, uid, shared, sdp, pt, bool(entry))
        agent.calls[call.cid] = call
        call.tasks.append(asyncio.ensure_future(call.run()))

    def contact(self):
        return [f"Contact: <sip:{self.agent.z.get('user', 'spark')}@{self.agent.local}:{self.agent.port}>"]

    def end(self, why, by_peer=False):
        if not self.over.is_set():
            self.why, self.by_peer = why, by_peer
            self.over.set()

    async def _bye(self):
        inv = self.invite
        target = uri_of(inv.get("contact")) or uri_of(inv.get("from"))
        if not target:
            return
        self.ours += 1
        heads = [f"Via: SIP/2.0/UDP {self.agent.local}:{self.agent.port};branch={branch()};rport", "Max-Forwards: 70"]
        heads += ["Route: " + r for r in inv.all("record-route")]
        to = inv.get("to")
        heads += [f"From: {to};tag={self.tag}" if not tag_of(to) else f"From: {to}", "To: " + inv.get("from"),
                  f"Call-ID: {self.cid}", f"CSeq: {self.ours} BYE"]
        await self.agent.transact(request("BYE", target, heads), (self.cid, self.ours, "BYE"), total=4.0)

    async def run(self):
        a = self.agent
        why = "fehler"
        try:
            a.send(response(self.invite, 100, "Trying"), self.addr)
            a.send(response(self.invite, 180, "Ringing", self.tag), self.addr)
            try:
                await asyncio.wait_for(self.over.wait(), RING)
            except asyncio.TimeoutError:
                pass
            if self.over.is_set():
                why = self.why
                return
            self.sock = _rtp_port()
            if not self.sock:
                a.send(response(self.invite, 486, "Busy Here", self.tag), self.addr)
                _bump("besetzt")
                print("telefon: besetzt, kein ton-port frei", flush=True)
                why = "besetzt"
                return
            loop = asyncio.get_running_loop()
            self.rtp = Rtp(self)
            await loop.create_datagram_endpoint(lambda: self.rtp, sock=self.sock)
            port = self.sock.getsockname()[1]
            self.sdp = sdp_offer(a.local, port, [self.codec.pt], random.randint(1000, 10 ** 9))
            self.last = response(self.invite, 200, "OK", self.tag, self.contact(), self.sdp)
            self.answered = True
            wait = 0.5
            for _ in range(7):                      # the 200 again until the ACK comes (RFC 3261 timer G)
                a.send(self.last, self.addr)
                try:
                    await asyncio.wait_for(self.acked.wait(), wait)
                    break
                except asyncio.TimeoutError:
                    wait = min(wait * 2, 4.0)
                if self.over.is_set():
                    break
            if not self.acked.is_set() and not self.over.is_set():
                print("telefon: keine bestaetigung der anlage, aufgelegt", flush=True)
                why = "ohne ack"
                return
            _bump("angenommen")
            print(f"telefon: anruf intern {self.number} als {_log_name(self.uid) if not self.shared else 'gemeinsames telefon'}"
                  + (", nicht zugeordnet" if not self.known else "") + f", ton {self.codec.name}", flush=True)
            self.tasks.append(asyncio.ensure_future(self._sender()))
            talk = asyncio.ensure_future(self.converse())
            done, _ = await asyncio.wait([talk, asyncio.ensure_future(self.over.wait())], timeout=MAX_CALL + 60,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not talk.done():
                talk.cancel()
                try:
                    await talk
                except (asyncio.CancelledError, Exception):
                    pass
            elif talk.exception():
                print("telefon: gespraech", type(talk.exception()).__name__, str(talk.exception())[:120], flush=True)
            why = self.why or "gespraech beendet"
        except Exception as e:
            print("telefon: anruf", type(e).__name__, str(e)[:120], flush=True)
        finally:
            if self.answered and not self.by_peer and not a.closing:
                try:
                    await self._bye()
                except Exception:
                    pass
            for t in self.tasks:
                if not t.done() and t is not asyncio.current_task():
                    t.cancel()
            if self.rtp and self.rtp.transport:
                self.rtp.transport.close()
            elif self.sock:
                self.sock.close()
            a.calls.pop(self.cid, None)
            if self.answered and self.acked.is_set():
                secs = int(time.time() - self.t0)
                _bump("sekunden", secs)
                _recent.append({"t": int(self.t0), "art": "intern", "nr": self.number, "who": self.uid and _log_name(self.uid),
                                "gemeinsam": self.shared, "s": secs, "fragen": self.questions})
                print(f"telefon: aufgelegt nach {secs} s, {self.questions} fragen ({why})", flush=True)
            elif why == "abgebrochen":
                print("telefon: anruf vor dem abheben beendet", flush=True)

    # ------------------------------------------------------------ sound in
    def rtp_in(self, data, addr):
        if addr[0] != self.remote["ip"] or len(data) < 12 or len(data) > 1500:
            return
        b0, b1 = data[0], data[1]
        if b0 >> 6 != 2:
            return
        pt = b1 & 0x7F
        off = 12 + 4 * (b0 & 0x0F)
        if b0 & 0x10:                                  # header extension
            if len(data) < off + 4:
                return
            off += 4 + 4 * struct.unpack("!H", data[off + 2:off + 4])[0]
        end = len(data) - (data[-1] if b0 & 0x20 else 0)
        payload = data[off:end]
        if not payload:
            return
        if pt == self.dtmf_pt and len(payload) >= 4:
            ts = struct.unpack("!I", data[4:8])[0]
            if payload[1] & 0x80 and ts != self.last_dtmf and payload[0] < len(DTMF):
                self.last_dtmf = ts
                self.digit(DTMF[payload[0]])
            return
        if pt == self.codec.pt:
            self.inbuf.append(payload)
            self.got.set()

    def digit(self, d):
        self.digits.append(d)
        self.got.set()

    async def _take(self, wait):
        """The sound that came since the last time, as 16 kHz PCM (waits up to wait seconds for some)."""
        if not self.inbuf:
            self.got.clear()
            try:
                await asyncio.wait_for(self.got.wait(), wait)
            except asyncio.TimeoutError:
                return b""
        parts = list(self.inbuf)
        self.inbuf.clear()
        if not parts:
            return b""
        return await asyncio.to_thread(lambda: b"".join(self.codec.decode(p) for p in parts))

    # ------------------------------------------------------------ sound out
    async def _sender(self):
        """One RTP packet every 20 ms: what is waiting in outq, else silence."""
        loop = asyncio.get_running_loop()
        seq, ts, ssrc = random.randint(0, 0xFFFF), random.randint(0, 0xFFFFFFFF), random.randint(1, 0xFFFFFFFF)
        quiet = telefon_ton.Codec(self.codec.pt).encode(b"\x00\x00" * self.codec.samples_per_frame())
        to = (self.remote["ip"], self.remote["port"])
        nxt, mark = loop.time(), True
        while not self.over.is_set():
            payload = self.outq.popleft() if self.outq else None
            pkt = struct.pack("!BBHII", 0x80, ((1 if mark and payload else 0) << 7) | self.codec.pt, seq, ts, ssrc) + (payload or quiet)
            mark = payload is None
            if self.rtp and self.rtp.transport and not self.rtp.transport.is_closing():
                self.rtp.transport.sendto(pkt, to)
            seq, ts = (seq + 1) & 0xFFFF, (ts + self.codec.clock // 50) & 0xFFFFFFFF
            nxt += 0.02
            delay = nxt - loop.time()
            if delay < -0.2:            # far behind (a busy moment): start the clock anew instead of rushing
                nxt, delay = loop.time(), 0
            await asyncio.sleep(max(0.0, delay))

    def _frames(self, pcm24):
        """24 kHz PCM from the speech output to payloads of 20 ms (in a thread: G.722 is pure Python)."""
        pcm = self.rest + self.codec.out.feed(pcm24)
        size = self.codec.samples_per_frame() * 2
        n = len(pcm) // size
        self.rest = pcm[n * size:]
        return [self.codec.encode(pcm[i * size:(i + 1) * size]) for i in range(n)]

    async def play(self, pcm24):
        for p in await asyncio.to_thread(self._frames, pcm24):
            self.outq.append(p)
        while len(self.outq) > 50 and not self.over.is_set():    # keep at most a second ahead
            await asyncio.sleep(0.05)

    async def drain(self):
        if self.rest:
            size = self.codec.samples_per_frame() * 2
            last = self.rest + b"\x00" * (size - len(self.rest))
            self.rest = b""
            self.outq.append(await asyncio.to_thread(self.codec.encode, last))
        while self.outq and not self.over.is_set():
            await asyncio.sleep(0.02)

    def hush(self):
        self.outq.clear()
        self.rest = b""

    async def say(self, text):
        """A fixed sentence (never the model): in the profile's voice, the Wartungspause sentence when the voice pauses."""
        import esp32
        import wartung
        from textnorm import guess_language
        try:
            if wartung.paused("tts"):
                await self.play(esp32.pause_clip(guess_language(text) == "English", text))
            else:
                async for pcm in esp32.tts_stream(self.uid or None, text):
                    await self.play(pcm)
        except Exception as e:
            print("telefon: sprachausgabe", type(e).__name__, flush=True)
        await self.drain()

    # ------------------------------------------------------------ the conversation
    async def hear(self, wait):
        """("frage", pcm) when someone spoke and paused, ("still", b"") after wait seconds without speech,
        ("ende", b"") when the call is over."""
        import esp32
        ear = esp32.Ear()
        ear.NOTHING = wait
        while True:
            if self.over.is_set() or time.time() - self.t0 > MAX_CALL:
                return "ende", b""
            pcm = await self._take(0.2)
            while self.digits:
                self.digits.popleft()                    # a key while nobody speaks: nothing to stop
            r = ear.feed(pcm) if pcm else None
            if r == "done":
                return "frage", bytes(ear.pcm)
            if r == "nothing" or (not ear.heard and time.time() - ear.started > wait):
                return "still", b""

    async def converse(self):
        name = ""
        if self.uid and not self.shared:
            p = profiles.by_id(self.uid)
            name = (p or {}).get("name", "")
        s = settings()
        if not self.known and not s["gaeste"]:
            await self.say("Hallo, hier ist der Spark. Dieses Telefon ist noch keinem Profil zugeordnet. "
                           "Der Admin ordnet es unter Funktionen, Telefon zu. Tschüss.")
            self.end("nicht zugeordnet")
            return
        await self.say(f"Hallo {name}, hier ist der Spark." if name else "Hallo, hier ist der Spark.")
        asked = False
        while not self.over.is_set():
            if time.time() - self.t0 > MAX_CALL:
                await self.say("Die Gesprächszeit ist um. Tschüss.")
                self.end("zeit um")
                return
            kind, pcm = await self.hear(QUIET_END if asked else QUIET_ASK)
            if kind == "ende":
                return
            if kind == "still":
                if asked:
                    await self.say("Ich lege jetzt auf. Tschüss.")
                    self.end("still")
                    return
                await self.say("Noch etwas?")
                asked = True
                continue
            asked = False
            await self.question(pcm)

    async def question(self, pcm):
        import esp32
        import notaus
        import wartung
        if notaus.blocks("gespraech"):
            self.end("notaus")
            return
        if wartung.paused("asr"):
            print("telefon: wartungspause spracherkennung, fester satz", flush=True)
            await self.say(wartung.sentence())
            return
        vt = self.voice_check(pcm)
        try:
            text = await esp32.transcribe(pcm)
        except Exception as e:
            print("telefon: spracherkennung", type(e).__name__, flush=True)
            text = ""
        if not text:
            if vt:
                vt.cancel()
            return
        if esp32.STOP_WORDS.match(text):
            if vt:
                vt.cancel()
            return
        if BYE_WORDS.match(text):
            if vt:
                vt.cancel()
            await self.say("Tschüss!")
            self.end("verabschiedet")
            return
        uid, voice, why = await self.voice_result(vt)
        self.questions += 1
        _bump("fragen")
        await self.answer(text, uid, voice, why)

    def voice_check(self, pcm):
        """Whose voice this is, while the speech recognition runs: the assigned profile's (speakers.verify) or, at a
        shared phone, any profile's (speakers.identify). None when the speaker recognition is off."""
        import esp32
        import speakers
        cc = load_config().get("chat", {})
        if not cc.get("speaker_id", False):
            return None
        th = speakers.STRICTNESS.get(cc.get("speaker_strictness"), 0.75)
        if self.uid and not self.shared:
            if not speakers.has_voice(self.uid):
                return None
            return asyncio.ensure_future(asyncio.to_thread(speakers.verify, self.uid, esp32.wav16k(pcm), th))
        if self.shared:
            return asyncio.ensure_future(asyncio.to_thread(speakers.identify, esp32.wav16k(pcm), th))
        return None

    async def voice_result(self, vt):
        """(profile id for this question or "", the voice's profile or "", why not): fixed rules, never the model."""
        if self.uid and not self.shared:
            if vt is None:
                return self.uid, "", "speaker ID is off or the profile has not taught its voice"
            try:
                v = await vt
            except Exception:
                return self.uid, "", "voice check failed"
            return self.uid, (self.uid if v.get("ok") else ""), ("" if v.get("ok") else str(v.get("why") or "voice not sure")[:160])
        if self.shared and vt is not None:
            try:
                who, _score = await vt
            except Exception:
                return "", "", "voice check failed"
            if who and features.allowed("telefon", who):
                return who, who, ""
        return "", "", ""

    async def answer(self, text, uid, voice, why):
        """The chat answers (fixed rules decide what it may: chat_turn); "#" or "Stopp" end the answer."""
        import esp32
        talk = asyncio.ensure_future(self._chat(text, uid, voice, why))
        ear, stop = esp32.Ear(), None
        try:
            while not talk.done():
                pcm = await self._take(0.1)
                if "#" in self.digits:
                    self.digits.clear()
                    print("telefon: antwort abgebrochen, taste", flush=True)
                    break
                self.digits.clear()
                if stop and stop.done():
                    heard = stop.result() if not stop.exception() else ""
                    stop = None
                    if heard and esp32.STOP_WORDS.match(heard):
                        print("telefon: antwort abgebrochen, stopp-wort", flush=True)
                        break
                if pcm and stop is None and ear.feed(pcm) == "done":
                    stop, ear = asyncio.ensure_future(esp32.transcribe(bytes(ear.pcm))), esp32.Ear()
        finally:
            if not talk.done():
                talk.cancel()
                self.hush()
            if stop and not stop.done():
                stop.cancel()
            try:
                await talk
            except (asyncio.CancelledError, Exception) as e:
                if not isinstance(e, asyncio.CancelledError):
                    print("telefon: antwort", type(e).__name__, str(e)[:120], flush=True)

    async def _chat(self, text, uid, voice, why):
        import base64
        import chat
        import esp32
        from starlette.requests import Request
        from textnorm import speech_markdown
        body = {"messages": self.history[-8:] + [{"role": "user", "content": text}], "client": "telefon",
                "tz": profiles.settings(uid).get("tz", "") if uid else ""}
        data = json.dumps(body).encode()
        scope = {"type": "http", "method": "POST", "path": "/api/chat", "query_string": b"", "headers": [],
                 "client": (self.agent.pbx[0], 0), "server": ("127.0.0.1", 0), "scheme": "http"}
        if uid:   # set only here, never by a request: the profile and whose voice it was (chat_turn.shared_stranger)
            scope.update({"speech_profile": uid, "speech_channel": "telefon", "speech_voice": voice or "",
                          "speech_voice_why": why})

        async def receive():
            return {"type": "http.request", "body": data, "more_body": False}
        response = await chat.chat(Request(scope, receive))
        answer, sound, from_outside = "", False, False
        try:
            async for chunk in response.body_iterator:
                for line in (chunk.decode() if isinstance(chunk, bytes) else chunk).split("\n"):
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:])
                    except ValueError:
                        continue
                    k = ev.get("type")
                    if k == "text":
                        answer += ev.get("delta", "")
                    elif k in ("truncated", "retract"):
                        answer = answer[:max(0, len(answer) - int(ev.get("drop") or 0))]
                    elif k in ("outside", "mail"):
                        from_outside = True
                    elif k == "audio" and ev.get("audio"):
                        sound = True
                        await self.play(base64.b64decode(ev["audio"]))
        finally:
            if hasattr(response.body_iterator, "aclose"):
                await response.body_iterator.aclose()      # stops the model and the voice when cancelled
        answer = answer.strip()
        if answer and not sound:                             # no sound came (guest, text-only): the voice here
            async for pcm in esp32.tts_stream(uid or None, speech_markdown(answer)[:600]):
                await self.play(pcm)
        await self.drain()
        if answer:
            # a voice that was not clearly the owner's counts as outside text, like at a speaker (esp32.remember): the
            # next turn starts locked, and the assistant never learns facts about the owner from it
            owner = bool(uid) and voice == uid
            turn = [dict({"role": "user", "content": text}, **({} if owner else {"outside": True})),
                    dict({"role": "assistant", "content": answer}, **({"outside": True} if from_outside or not owner else {}))]
            self.history = (self.history + turn)[-16:]
            if uid:
                self.remember(uid, turn, owner)

    def remember(self, uid, turn, owner):
        """The turn as the day's conversation "Telefon dd.mm." of the profile (like a speaker's, esp32.remember)."""
        import chat
        import verlauf
        local = datetime.datetime.now(chat.user_zone(profiles.settings(uid).get("tz", "")))
        try:
            verlauf.keep(uid, f"tel-{local:%Y%m%d}", f"Telefon {local:%d.%m.}", local, "telefon", turn, owner=owner)
        except Exception as e:
            print("telefon: verlauf", type(e).__name__, flush=True)


# ---------------------------------------------------------------- running it
_agent = {"a": None, "key": None, "next": 0.0}


def _key(z, s):
    return (z.get("host"), int(z.get("port") or 5060), z.get("user"), hashlib.sha256(z.get("pw", "").encode()).hexdigest()) \
        if s["on"] and ready(z) else None


async def _start(z):
    """A new Agent for this access, signed in; returns it (also when the sign-in failed: it tries again)."""
    a = Agent()
    try:
        ip = await asyncio.to_thread(resolve, z["host"], int(z.get("port") or 5060))
    except ValueError as e:
        a.reg = {"ok": False, "why": str(e), "t": time.time(), "until": 0.0}
        print("telefon: anlage nicht erreichbar,", str(e), flush=True)
        return a
    try:
        await a.open(z, ip)
    except OSError:
        a.reg = {"ok": False, "why": "port", "t": time.time(), "until": 0.0}
        print("telefon: port belegt", flush=True)
        return a
    why = await a.register()
    if why == "ok":
        print("telefon: angemeldet an anlage", str(z.get("anlage") or "andere"), flush=True)
    else:
        print("telefon: anmeldung fehlgeschlagen", why, a.reg.get("code") or "", flush=True)
    return a


async def _stop():
    a = _agent["a"]
    _agent["a"] = None
    if a:
        if a.transport and a.reg.get("ok"):
            try:
                await a.register(0)
            except Exception:
                pass
        a.close()
        print("telefon: abgemeldet", flush=True)


async def tick(now=None):
    """Keeps the SIP part as the settings say: on with an access → signed in, renewed after half the time."""
    now = now or time.time()
    s, z = settings(), zugang()
    key = _key(z, s)
    if key != _agent["key"]:
        await _stop()
        _agent["key"], _agent["next"] = key, 0.0
        if key:
            _agent["a"] = await _start(z)
            _agent["next"] = now + (REG_EXPIRES / 2 if _agent["a"].reg.get("ok") else REG_RETRY)
        return
    a = _agent["a"]
    if a and now >= _agent["next"]:
        if not a.transport:            # address or port failed: start anew
            _agent["key"] = None
            return
        why = await a.register()
        until = a.reg.get("until") or now
        _agent["next"] = now + (max(30, (until - now) / 2) if why == "ok" else REG_RETRY)
        if why != "ok":
            print("telefon: anmeldung fehlgeschlagen", why, a.reg.get("code") or "", flush=True)


async def loop():
    while True:
        try:
            await tick()
        except Exception as e:
            print("telefon: schleife", type(e).__name__, str(e)[:120], flush=True)
        await asyncio.sleep(5)


def state():
    """Signed in or why not, and the calls running (Live, admin page, Dienst-Wächter)."""
    a = _agent["a"]
    s = settings()
    if not s["on"]:
        reg = {"ok": False, "why": "aus", "t": 0}
    elif not ready():
        reg = {"ok": False, "why": "fehlt", "t": 0}
    else:
        reg = dict(a.reg) if a else {"ok": False, "why": "stumm", "t": 0}
    return {"on": s["on"], "ok": bool(reg.get("ok")), "why": reg.get("why", ""), "since": reg.get("t", 0),
            "calls": len(a.calls) if a else 0}


def for_live():
    """Zustand → Live: signed in, calls now and today in numbers, never a number or a name."""
    st = state()
    if not st["on"]:
        return {"on": False}
    t = _today.counts()
    return {"on": True, "ok": st["ok"], "calls": st["calls"], "angenommen": t["angenommen"],
            "abgelehnt": t["abgelehnt"] + t["besetzt"], "fragen": t["fragen"], "minuten": t["sekunden"] // 60, "fremd": t["fremd"]}


def probes():
    """For the Dienst-Wächter: one part while the switch is on and the access is set up."""
    if not settings()["on"] or not ready():
        return {}
    return {"telefon": {"sip": True, "host": zugang().get("host", "")}}


def signed_in():
    return state()["ok"]


def seen(number):
    """An internal number that called: kept for step 4 (the admin assigns it)."""
    with _lock:
        d = _read()
        g = [x for x in d.get("gesehen", []) if x.get("nr") != number][-(SEEN_MAX - 1):]
        d["gesehen"] = g + [{"nr": number, "t": int(time.time())}]
        _write(d)


# ---------------------------------------------------------------- discovery (step 1)
DISCOVER = ("fritz.box", "speedport.ip")


def _gateway():
    """The default gateway from /proc/net/route ("" when unknown)."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                p = line.split()
                if len(p) > 2 and p[1] == "00000000":
                    return socket.inet_ntoa(struct.pack("<L", int(p[2], 16)))
    except (OSError, ValueError):
        pass
    return ""


def discover():
    """Where a PBX answers SIP OPTIONS in the home network: [{"host", "ip", "anlage", "name"}] (runs in a thread)."""
    out = []
    for host in DISCOVER + ((_gateway(),) if _gateway() else ()):
        try:
            ip = resolve(host, 5060)
        except ValueError:
            continue
        if any(x["ip"] == ip for x in out):
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(1.0)
            s.connect((ip, 5060))
            me = s.getsockname()
            cid = secrets.token_hex(8)
            s.send(request("OPTIONS", f"sip:{ip}", [f"Via: SIP/2.0/UDP {me[0]}:{me[1]};branch={branch()};rport", "Max-Forwards: 70",
                                                     f"From: <sip:spark@{me[0]}>;tag={secrets.token_hex(4)}", f"To: <sip:{ip}>",
                                                     f"Call-ID: {cid}", "CSeq: 1 OPTIONS", "Accept: application/sdp"]))
            r = parse(s.recv(MAX_MSG))
        except OSError:
            continue
        finally:
            s.close()
        if not r or not r.code:
            continue
        agent = (r.get("server") or r.get("user-agent")).lower()
        pid = "fritzbox" if "fritz" in agent or host == "fritz.box" else "speedport" if "speedport" in agent or host == "speedport.ip" \
            else "asterisk" if "asterisk" in agent or "freepbx" in agent else "3cx" if "3cx" in agent else "andere"
        out.append({"host": host, "ip": ip, "anlage": pid, "name": preset(pid)["name"]})
    return out


# ---------------------------------------------------------------- admin endpoints
def _view():
    d = _read()
    z = d.get("zugang") or {}
    names = {u["id"]: u["name"] for u in profiles._load()["users"]}
    st = state()
    return {"anlagen": [{k: a.get(k) for k in ("id", "name", "host", "port", "steps", "hint")} for a in presets()],
            "zugang": {"anlage": z.get("anlage", ""), "host": z.get("host", ""), "port": z.get("port", 5060), "user": z.get("user", ""),
                       "pw": bool(z.get("pw"))},
            "zustand": dict(st, text=SAY.get(st["why"], SAY["abgelehnt"])),
            "nummern": [{"nr": n, "uid": e.get("uid", ""), "profil": names.get(e.get("uid", ""), ""), "name": e.get("name", "")}
                        for n, e in sorted(nummern().items())],
            "gesehen": [x for x in reversed(d.get("gesehen", [])) if x.get("nr") not in nummern()],
            "profile": [{"id": k, "name": v} for k, v in names.items()],
            "heute": for_live(), "vorschlag": {"user": "spark" + str(secrets.randbelow(9000) + 1000), "pw": secrets.token_urlsafe(15)}}


@router.get("/api/admin/telefon", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "telefon", admin=True)
    return _view()


@router.post("/api/admin/telefon/suchen", dependencies=[Depends(auth)])
async def admin_discover(request: Request):
    guard.limit(request, "telefonsuchen", admin=True)
    found = await asyncio.to_thread(discover)
    print(f"telefon: suche im heimnetz, {len(found)} anlagen gefunden", flush=True)
    return {"gefunden": found}


def _field(b, k, most, rx):
    v = str(b.get(k) or "").strip()
    if len(v) > most or (v and not re.fullmatch(rx, v)):
        raise HTTPException(400, f"{k}: ungültig")
    return v


# the access decides where the Spark signs in with which password: a confirmed code (stufen.py)
@router.put("/api/admin/telefon/zugang", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_access(request: Request):
    guard.limit(request, "telefon", admin=True)
    b = await json_body(request, 2048)
    anlage = _field(b, "anlage", 20, r"[a-z0-9]+")
    host = _field(b, "host", 120, r"[A-Za-z0-9.-]+")
    user = _field(b, "user", 64, r"[A-Za-z0-9._+*#-]+")
    try:
        port = int(b.get("port") or 5060)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        raise HTTPException(400, "port: 1 bis 65535")
    pw = b.get("pw")
    if pw is not None and (not isinstance(pw, str) or len(pw) > 128 or re.search(r"[\x00-\x1f\x7f\"\\]", pw)):
        raise HTTPException(400, "Kennwort: bis 128 Zeichen, ohne Anführungszeichen")
    if host:
        try:
            await asyncio.to_thread(resolve, host, port)
        except ValueError as e:
            raise HTTPException(400, SAY.get(str(e), SAY["name"])[0])
    with _lock:
        d = _read()
        old = d.get("zugang") or {}
        z = {"anlage": anlage or old.get("anlage", ""), "host": host, "port": port, "user": user,
             "pw": vault.seal(pw) if pw else old.get("pw", "") if host == old.get("host") else ""}
        d["zugang"] = z
        _write(d)
    print("telefon: zugang gespeichert" + (", neues kennwort" if pw else ""), flush=True)
    return _view()


@router.post("/api/admin/telefon/pruefen", dependencies=[Depends(auth)])
async def admin_check(request: Request):
    """"Verbindung prüfen": signs in now with the stored access and says the result in plain words."""
    guard.limit(request, "telefonsuchen", admin=True)
    if not ready():
        return {"ok": False, "why": "fehlt", "text": SAY["fehlt"][0]}
    if not settings()["on"]:
        z = zugang()
        a = await _start(z)
        why = a.reg.get("why", "stumm")
        if a.transport:
            if a.reg.get("ok"):
                await a.register(0)
            a.close()
    else:
        _agent["key"] = None
        await tick()
        why = state()["why"] if not state()["ok"] else "ok"
    print(f"telefon: verbindung geprueft, {why}", flush=True)
    return {"ok": why == "ok", "why": why, "text": SAY.get(why, SAY["abgelehnt"])[0]}


@router.put("/api/admin/telefon/nummern", dependencies=[Depends(auth)])
async def admin_numbers(request: Request):
    """{"nr", "uid" (a profile, "" = gemeinsames Telefon), "name"?} assigns an internal number; {"nr", "weg": true} removes it."""
    guard.limit(request, "telefon", admin=True)
    b = await json_body(request, 1024)
    nr = clean_number(b.get("nr"))
    if not nr or not internal(nr):
        raise HTTPException(400, "Nur interne Nummern der Anlage (z. B. **611).")
    uid = str(b.get("uid") or "")
    if uid and not profiles.by_id(uid):
        raise HTTPException(400, "Profil unbekannt")
    name = re.sub(r"[\x00-\x1f<>]", "", str(b.get("name") or ""))[:40]
    with _lock:
        d = _read()
        nn = dict(d.get("nummern") or {})
        if b.get("weg"):
            nn.pop(nr, None)
        else:
            if len(nn) >= 50 and nr not in nn:
                raise HTTPException(400, "Höchstens 50 Nummern")
            nn[nr] = {"uid": uid, "name": name}
        d["nummern"] = nn
        _write(d)
    print(f"telefon: nummer {nr} " + ("entfernt" if b.get("weg") else "zugeordnet " + ("gemeinsam" if not uid else _log_name(uid))), flush=True)
    return _view()


def forget(uid):
    """A profile is deleted: its handsets are no longer assigned (they then count as not assigned)."""
    with _lock:
        d = _read()
        nn = {k: v for k, v in (d.get("nummern") or {}).items() if v.get("uid") != uid}
        if nn != (d.get("nummern") or {}):
            d["nummern"] = nn
            _write(d)
