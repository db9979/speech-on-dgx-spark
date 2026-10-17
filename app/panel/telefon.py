"""Telefon: den Spark anrufen (plan plaene/telefon-anruf.md, Stufen T1 bis T4; the Spark calling: Call.dial here, the
rules in telefon_anruf.py). The Spark signs in at the home's telephone system
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
    external number waiting for its code    taken only to type that code (Ich → Telefon, telefon_ich.py)
    external, a confirmed own number        with chat.telefon_aussen: that profile, but personal things only with a
                                            sure voice or the Telefon-PIN (a shown number can be forged); no name
                                            in the greeting
    external, unknown or hidden             with chat.telefon_aussen and chat.telefon_gaeste: a guest (at most
                                            GUESTS a day); else refused. A PIN makes no profile out of it.
A Telefon-PIN (telefon_ich.py, digits and #) stands for the voice for the rest of the call: on an assigned handset
for its profile, at a shared phone for the profile whose PIN it is. Wrong ones lock the PIN at that phone.

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
RING_OUT = 30                   # seconds the Spark lets a phone ring when it calls (T4) before it gives up
MAX_CALL = 15 * 60              # one call ends after this
QUIET_ASK, QUIET_END = 20, 10   # silence: "Noch etwas?" after the first, hang up after the second
MAX_CALLS = 2                   # chat.telefon_max at most
SEEN_MAX = 10
GUESTS = 20                     # calls from unknown numbers outside a day at most (chat.telefon_gaeste and _aussen)
UA = "Speech-on-DGX-Spark"
METHODS = ("INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "INFO", "NOTIFY")
DTMF = "0123456789*#ABCD"
BYE_WORDS = re.compile(r"(?i)^\W*(?:(?:ok|okay|gut|danke)\W+)*(?:tschüss|tschüs|ciao|auf wiederhören|auf wiedersehen|bis dann|"
                       r"bis später|leg auf|auflegen|das war'?s|das wars|ende|bye|goodbye)\W*(?:danke|spark)?\W*$")
CALLBACK_WORDS = re.compile(r"(?i)\b(?:ruf|rufe|rufst)\s+(?:mich|du mich)\s+(?:bitte\s+)?(?:gleich\s+)?zurück|\brückruf\b|\bcall me back\b")
_lock = threading.Lock()


# ---------------------------------------------------------------- settings and stored access
def settings(c=None):
    c = c or load_config()
    ch = c.get("chat", {})
    try:
        most = max(1, min(MAX_CALLS, int(ch.get("telefon_max") or 1)))
    except (TypeError, ValueError):
        most = 1
    # features.admin_on takes the chat section, not the whole config
    return {"on": features.admin_on("telefon", ch), "ton": "schmal" if ch.get("telefon_ton") == "schmal" else "hd",
            "gaeste": features.admin_on("telefongast", ch), "aussen": features.admin_on("telefonaussen", ch), "max": most}


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
TEST_SAY = {"angenommen": ("Abgehoben: Der Spark hat den Testsatz gesagt.", "Answered: the Spark said the test sentence."),
            "besetzt": ("Besetzt oder kein Gespräch mehr frei.", "Busy, or no call free."),
            "abgelehnt": ("Die Anlage hat den Anruf abgelehnt. Darf das IP-Telefon „Spark“ anrufen?",
                          "The system refused the call. May the IP phone “Spark” place calls?"),
            "keine antwort": ("Niemand hat abgehoben.", "Nobody answered."),
            "abgemeldet": ("Der Spark ist nicht angemeldet.", "The Spark is not signed in."),
            "fehler": ("Der Anruf ging nicht.", "The call did not work.")}
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
_today = DayCounter(angenommen=0, abgelehnt=0, besetzt=0, fragen=0, sekunden=0, fremd=0, kaputt=0, pin=0, pinfalsch=0,
                    bestaetigt=0, extern=0, gaeste=0, angerufen=0, raus=0, rueckruf=0, alarm=0)


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
        self.nat = ("", 0)          # the address the PBX sees when a router translates in between (Via received, rport)
        self.z = {}
        self.reg = {"ok": False, "why": "fehlt", "t": 0.0, "until": 0.0}
        self.cseq = random.randint(1, 1000)
        self.reg_cid = secrets.token_hex(10)
        self.tag = secrets.token_hex(6)
        self.pending = {}           # (call-id, cseq, method) -> Future of the final answer
        self.watch = {}             # call-id -> function: every answer to an INVITE the Spark sent (Call.dial)
        self.calls = {}             # call-id -> Call
        self.sec = [0.0, 0]         # the second and the messages in it
        self.closing = False

    def me(self):
        """(ip, SIP port) the PBX reaches the Spark at: the router's when one translates in between (NAT; there UDP
        SIP_PORT and RTP_PORTS have to be forwarded to this computer), else this computer's own."""
        return self.nat if self.nat[0] else (self.local, self.port)

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
            w = self.watch.get(msg.get("call-id"))
            if w and meth == "INVITE":
                w(msg)
                return
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
        for _ in range(5):
            self.cseq += 1
            heads = [f"Via: SIP/2.0/UDP {self.local}:{self.port};branch={branch()};rport", "Max-Forwards: 70",
                     f"From: <sip:{user}@{dom}>;tag={self.tag}", f"To: <sip:{user}@{dom}>", f"Call-ID: {self.reg_cid}",
                     f"CSeq: {self.cseq} REGISTER", "Contact: <sip:{}@{}:{}>".format(user, *self.me()),
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
            if why == "ok" and expires and self._learn_nat(r):
                auth_line = ""                             # sign in again with the address the PBX sees (a new challenge)
                continue
            if why == "ok" and expires:
                m = re.search(r";\s*expires=(\d+)", r.get("contact")) or re.fullmatch(r"\s*(\d+)\s*", r.get("expires") or "")
                expires = max(60, min(int(m.group(1)), 3600)) if m else expires
            break
        if expires:
            self.reg = {"ok": why == "ok", "why": why, "t": time.time(), "until": time.time() + (expires if why == "ok" else 0),
                        "code": getattr(r, "code", 0) if why != "ok" else 0}
        return why

    def _learn_nat(self, r):
        """True when the answer shows a router translating between the Spark and the PBX for the first time (Via
        received= differs from this computer's address): from now on Contact and SDP name the router's address."""
        via = r.get("via")
        m = re.search(r";\s*received=([\d.]+)", via)
        ip = m.group(1) if m else ""
        if not ip or ip == self.local or not lan_ip(ip) or self.nat[0] == ip:
            return False
        m = re.search(r";\s*rport=(\d{1,5})", via)
        port = int(m.group(1)) if m and 0 < int(m.group(1)) < 65536 else self.port
        self.nat = (ip, port)
        print(f"telefon: nat zwischen spark und anlage, anlage sieht port {port}", flush=True)
        return True

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
                if not call.out and msg.cseq() == call.invite.cseq():    # the same INVITE again: the answer again
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

    def __init__(self, agent, invite, addr, number, uid, shared, sdp, pt, known=True, mode=""):
        self.agent, self.invite, self.addr = agent, invite, addr
        self.number, self.uid, self.shared, self.known = number, uid, shared, known
        self.mode = mode                                  # "", "extern" (from outside) or "bestaetigen" (a code); the Spark
        #                                                   calling (T4): "weckruf", "erinnerung", "rueckruf", "alarm", "test"
        self.out = None                                   # the Spark called: {"target", "from", "to", "routes"} of the dialog
        self.text = ""                                    # what the Spark called to say (reminder, alarm), never logged
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
        self.digits = collections.deque(maxlen=20)     # "#" alone: stop the answer
        self.keys = ""                                    # digits typed so far (PIN or code), never a word
        self.entered = collections.deque(maxlen=4)       # what was typed and ended with #
        self.pin_uid = ""                                 # the profile a right PIN named, for the rest of the call
        self.voices = set()                               # profiles the voice named at a shared phone
        self.last_dtmf = None
        self.rtp = None
        self.sock = None
        self.history = []
        self.questions = 0
        self.ours = 0                                     # CSeq of our own requests in this dialog
        self.tasks = []
        self.rest = b""
        self.pkts = {"raus": 0, "sprache": 0, "rein": 0}
        self.live = None                                  # the call as one request in Live, Monitoring and Steuerzentrale   # RTP packets sent, of them with speech, received (log at the end)

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
        mode, uid, shared, known = "", "", False, True
        if not internal(number, agent.z.get("anlage")):
            mode, uid = Call.outside(number, s)
            if mode is None:
                agent.send(response(msg, 603, "Decline"), addr)
                _bump("abgelehnt")
                return
            known = bool(uid) or mode == "bestaetigen"
        else:
            entry = nummern().get(number)
            if entry and entry.get("uid") and not profiles.by_id(entry["uid"]):
                entry = None                       # its profile is gone: as not assigned
            if not entry:
                seen(number)
            known = bool(entry)
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
        if mode == "extern":
            _bump("extern")
        call = Call(agent, msg, addr, number, uid, shared, sdp, pt, known, mode=mode)
        agent.calls[call.cid] = call
        call.tasks.append(asyncio.ensure_future(call.run()))

    @staticmethod
    def outside(number, s):
        """A call from outside (fixed rules, never the model; the number is never logged):
            an own number waiting for its code (Ich → Telefon)          ("bestaetigen", that profile)
            a confirmed own number, with "Anrufe von außen" on          ("extern", that profile): personal things
                                                                        only with a sure voice or the Telefon-PIN
            any other or a hidden number, with also "Gäste annehmen"    ("extern", ""): a guest, at most GUESTS a day
            else                                                        (None, "") refused"""
        import telefon_ich
        who = telefon_ich.pending_for(number) if number else ""
        if who and features.allowed("telefon", who):
            return "bestaetigen", who
        if not s["aussen"]:
            print("telefon: anruf extern abgelehnt", flush=True)
            return None, ""
        owner = telefon_ich.owner_of(number) if number else ""
        if owner and features.allowed("telefon", owner):
            print(f"telefon: anruf extern bekannt als {_log_name(owner)}", flush=True)
            return "extern", owner
        if owner:
            print(f"telefon: anruf extern abgelehnt, telefon fuer {_log_name(owner)} gesperrt", flush=True)
            return None, ""
        if not s["gaeste"]:
            print("telefon: anruf extern unbekannt abgelehnt", flush=True)
            return None, ""
        if _today.counts()["gaeste"] >= GUESTS:
            print(f"telefon: anruf extern unbekannt abgelehnt, schon {GUESTS} gaeste heute", flush=True)
            return None, ""
        _bump("gaeste")
        print("telefon: anruf extern unbekannt als gast", flush=True)
        return "extern", ""

    @staticmethod
    async def dial(agent, target, uid, mode, text="", ring=RING_OUT):
        """The Spark calls (T4). target is an internal number or a confirmed own number of uid, never anything else:
        telefon_anruf.target picks it with fixed rules, never from the model, a mail or the conversation. Returns
        "angenommen" (the call runs on as a task), "besetzt", "abgelehnt", "keine antwort" or "fehler"."""
        s = settings()
        if not agent.reg.get("ok") or not agent.transport:
            return "fehler"
        if len(agent.calls) >= s["max"]:
            return "besetzt"
        sock = _rtp_port()
        if not sock:
            return "besetzt"
        cid, tag = secrets.token_hex(12), secrets.token_hex(6)
        user, dom = agent.z["user"], agent._domain()
        uri, me = f"sip:{target}@{dom}", f"<sip:{user}@{dom}>;tag={tag}"
        pts = [p for p in telefon_ton.PREFER if s["ton"] == "hd" or p != 9]
        offer = sdp_offer(agent.me()[0], sock.getsockname()[1], pts, random.randint(1000, 10 ** 9))
        got = asyncio.Queue()
        agent.watch[cid] = got.put_nowait
        cseq, auth, nc, ok, early = random.randint(1, 1000), "", 0, None, {}
        try:
            for _ in range(2):
                via = f"Via: SIP/2.0/UDP {agent.local}:{agent.port};branch={branch()};rport"
                heads = [via, "Max-Forwards: 70", "From: " + me, f"To: <{uri}>", f"Call-ID: {cid}", f"CSeq: {cseq} INVITE",
                         "Contact: <sip:{}@{}:{}>".format(user, *agent.me()), "Allow: " + ", ".join(METHODS)] + ([auth] if auth else [])
                inv = request("INVITE", uri, heads, offer)
                final = await Call._ring(agent, inv, got, cseq, via, uri, me, cid, ring, early)
                if final is None:
                    return "keine antwort"
                if 200 <= final.code < 300:
                    ok = final
                    break
                agent.send(Call._ack_failed(via, uri, me, final, cid, cseq))
                if final.code in (401, 407) and not auth:
                    try:
                        nc += 1
                        head = "Authorization" if final.code == 401 else "Proxy-Authorization"
                        chal = final.get("www-authenticate" if final.code == 401 else "proxy-authenticate")
                        auth = f"{head}: " + digest(chal, "INVITE", uri, user, agent.z["pw"], nc)
                    except ValueError:
                        return "abgelehnt"
                    cseq += 1
                    continue
                print(f"telefon: anruf raus antwort {final.code}", flush=True)     # the code alone, never the number
                return "besetzt" if final.code in (486, 600) else "keine antwort" if final.code in (408, 480, 487) else "abgelehnt"
            if ok is None:
                return "abgelehnt"
            routes = list(reversed(ok.all("record-route")))
            far = uri_of(ok.get("contact")) or uri
            ack_heads = [f"Via: SIP/2.0/UDP {agent.local}:{agent.port};branch={branch()};rport", "Max-Forwards: 70"] \
                + ["Route: " + r for r in routes] + ["From: " + me, "To: " + ok.get("to"), f"Call-ID: {cid}", f"CSeq: {cseq} ACK"]
            ack = request("ACK", far, ack_heads, "")
            agent.send(ack)
            agent.watch[cid] = lambda m: agent.send(ack) if 200 <= m.code < 300 else None   # the 200 again: the ACK again
            sdp = sdp_parse(ok.body or early.get("sdp", ""))     # some PBX answer only in the 183, the 200 comes empty
            pt = choose(sdp, s["ton"]) if sdp else None
            if not sdp or pt is None or not lan_ip(sdp["ip"]) and sdp["ip"] != agent.pbx[0]:
                print("telefon: anruf raus beendet, keine gemeinsame tonart oder adresse nicht im heimnetz", flush=True)
                call = Call(agent, parse(inv), agent.pbx, target, uid, False, {"ip": "", "port": 0, "dtmf": None}, 0, mode=mode)
                call.out, call.tag, call.ours = {"target": far, "from": me, "to": ok.get("to"), "routes": routes}, tag, cseq
                await call._bye()
                return "abgelehnt"
            call = Call(agent, parse(inv), agent.pbx, target, uid, False, sdp, pt, mode=mode)
            call.out, call.tag, call.ours, call.text = {"target": far, "from": me, "to": ok.get("to"), "routes": routes}, tag, cseq, text
            call.sdp = offer                     # a new offer in the call (re-INVITE) gets our own description again
            call.sock, sock = sock, None
            call.answered = True
            call.acked.set()
            agent.calls[cid] = call
            call.tasks.append(asyncio.ensure_future(call.run()))
            return "angenommen"
        except Exception as e:
            print("telefon: anruf raus", type(e).__name__, str(e)[:120], flush=True)
            return "fehler"
        finally:
            if sock:
                sock.close()
            if cid not in agent.calls:
                agent.watch.pop(cid, None)

    @staticmethod
    async def _ring(agent, inv, got, cseq, via, uri, me, cid, ring, early=None):
        """Sends our INVITE (again until the PBX answers at all) and waits for the final answer; after ring seconds a
        CANCEL. The final answer or None when none came. The SDP of a provisional answer (183) goes to early["sdp"]."""
        end, wait, heard = time.monotonic() + ring, 0.5, False
        next_send = time.monotonic()
        while True:
            now = time.monotonic()
            if now >= end:
                break
            if not heard and now >= next_send:
                agent.send(inv)
                next_send, wait = now + wait, min(wait * 2, 4.0)
            try:
                m = await asyncio.wait_for(got.get(), min(0.5, max(0.05, end - now)))
            except asyncio.TimeoutError:
                continue
            if m.cseq()[0] != cseq:
                continue
            if m.code >= 200:
                return m
            if early is not None and m.body.strip():
                early["sdp"] = m.body
            heard = True
        if not heard:
            return None
        cancel = request("CANCEL", uri, [via, "Max-Forwards: 70", "From: " + me, f"To: <{uri}>", f"Call-ID: {cid}",
                                         f"CSeq: {cseq} CANCEL"], "")
        await agent.transact(cancel, (cid, cseq, "CANCEL"), total=4.0)
        until = time.monotonic() + 4.0
        while time.monotonic() < until:
            try:
                m = await asyncio.wait_for(got.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            if m.cseq()[0] == cseq and m.code >= 200:
                if 200 <= m.code < 300:            # answered just then: take the call after all
                    return m
                agent.send(Call._ack_failed(via, uri, me, m, cid, cseq))
                return None
        return None

    @staticmethod
    def _ack_failed(via, uri, me, final, cid, cseq):
        """The ACK for a final answer that is not a 2xx: the same branch as the INVITE (RFC 3261 17.1.1.3)."""
        return request("ACK", uri, [via, "Max-Forwards: 70", "From: " + me, "To: " + final.get("to"), f"Call-ID: {cid}",
                                    f"CSeq: {cseq} ACK"], "")

    def contact(self):
        return ["Contact: <sip:{}@{}:{}>".format(self.agent.z.get("user", "spark"), *self.agent.me())]

    def end(self, why, by_peer=False):
        if not self.over.is_set():
            self.why, self.by_peer = why, by_peer
            self.over.set()

    async def _bye(self):
        self.ours += 1
        heads = [f"Via: SIP/2.0/UDP {self.agent.local}:{self.agent.port};branch={branch()};rport", "Max-Forwards: 70"]
        if self.out:                                    # our own dialog: as in the ACK (Call.dial)
            target = self.out["target"]
            heads += ["Route: " + r for r in self.out["routes"]]
            heads += ["From: " + self.out["from"], "To: " + self.out["to"]]
        else:
            inv = self.invite
            target = uri_of(inv.get("contact")) or uri_of(inv.get("from"))
            heads += ["Route: " + r for r in inv.all("record-route")]
            to = inv.get("to")
            heads += [f"From: {to};tag={self.tag}" if not tag_of(to) else f"From: {to}", "To: " + inv.get("from")]
        if not target:
            return
        heads += [f"Call-ID: {self.cid}", f"CSeq: {self.ours} BYE"]
        await self.agent.transact(request("BYE", target, heads), (self.cid, self.ours, "BYE"), total=4.0)

    async def _pick_up(self):
        """An incoming call: Trying, Ringing, then the 200 with our SDP until the ACK; "" when the call stands, else why not."""
        a = self.agent
        a.send(response(self.invite, 100, "Trying"), self.addr)
        a.send(response(self.invite, 180, "Ringing", self.tag), self.addr)
        try:
            await asyncio.wait_for(self.over.wait(), RING)
        except asyncio.TimeoutError:
            pass
        if self.over.is_set():
            return self.why or "abgebrochen"
        self.sock = _rtp_port()
        if not self.sock:
            a.send(response(self.invite, 486, "Busy Here", self.tag), self.addr)
            _bump("besetzt")
            print("telefon: besetzt, kein ton-port frei", flush=True)
            return "besetzt"
        loop = asyncio.get_running_loop()
        self.rtp = Rtp(self)
        await loop.create_datagram_endpoint(lambda: self.rtp, sock=self.sock)
        port = self.sock.getsockname()[1]
        self.sdp = sdp_offer(a.me()[0], port, [self.codec.pt], random.randint(1000, 10 ** 9))
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
            return "ohne ack"
        return ""

    async def run(self):
        a = self.agent
        why = "fehler"
        try:
            if self.out:                           # we called: the dialog stands, the sound socket waits
                self.rtp = Rtp(self)
                await asyncio.get_running_loop().create_datagram_endpoint(lambda: self.rtp, sock=self.sock)
            else:
                why = await self._pick_up()
                if why:
                    return
            _bump("angerufen" if self.out else "angenommen")
            self._watch()
            if self.out:                        # the Spark called: the kind and the profile, never the number
                print(f"telefon: anruf raus angenommen ({self.mode}) von {_log_name(self.uid)}, ton {self.codec.name}", flush=True)
            elif self.mode == "bestaetigen":      # an external number: never in the log
                print(f"telefon: anruf extern zum bestaetigen einer nummer fuer {_log_name(self.uid)}, ton {self.codec.name}", flush=True)
            elif self.mode == "extern":
                print(f"telefon: anruf extern angenommen als {_log_name(self.uid) if self.uid else 'gast'}, ton {self.codec.name}", flush=True)
            else:
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
            a.watch.pop(self.cid, None)
            if self.live is not None:
                import live
                if self.live.cur:
                    self.live.step(self.live.cur[0], self.live.cur[1], self.live.cur[2], time.time())
                live.end(self.live)
                self.live = None
            if self.answered and self.acked.is_set():
                secs = int(time.time() - self.t0)
                _bump("sekunden", secs)
                self.keep(secs)
                k = self.pkts
                print(f"telefon: aufgelegt nach {secs} s, {self.questions} fragen ({why}), ton raus {k['raus']} pakete, "
                      f"davon {k['sprache']} mit sprache, rein {k['rein']} pakete", flush=True)
            elif why == "abgebrochen":
                print("telefon: anruf vor dem abheben beendet", flush=True)

    def _watch(self):
        """The call as one request from picking up to hanging up (live.begin): the phone stands under the devices of
        Live, Monitoring and the Steuerzentrale while it talks. Device name only of an assigned handset (shown with
        the profile's consent, live._who), never a number; the questions in it are requests of their own (chat)."""
        import live
        name = (nummern().get(self.number) or {}).get("name", "") if self.mode not in ("extern", "bestaetigen") and internal(self.number) else ""
        self.live = live.begin("telefon", str(name)[:30], t=self.t0, uid=self.uid or None,
                               why="Spark ruft an" if self.out else "Anruf")
        if self.live is not None:
            self.live.step("in", "Eingang", self.t0)
            self.live.now("asr", "Gespräch")

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
            self.pkts["rein"] += 1
            self.inbuf.append(payload)
            self.got.set()

    def digit(self, d):
        """A key: digits gather (PIN or code, at most 8), * starts anew, # ends them; # alone stops the answer."""
        if d == "#":
            if self.keys:
                self.entered.append(self.keys)
                self.keys = ""
            else:
                self.digits.append("#")
        elif d == "*":
            self.keys = ""
        elif d.isdigit():
            import telefon_ich
            self.keys = (self.keys + d)[-8:]
            if self.mode == "bestaetigen" and len(self.keys) >= telefon_ich.CODE_LEN:
                self.entered.append(self.keys)
                self.keys = ""
        self.got.set()

    def keep(self, secs):
        """The call under Ich → Telefon → Meine Telefonate of each profile it was for (no number, no words)."""
        import telefon_ich
        art = "spark" if self.out else "bestaetigung" if self.mode == "bestaetigen" else "extern" if self.mode \
            else "gemeinsam" if self.shared else "intern"
        for uid in ({self.uid} if self.uid else set()) | ({self.pin_uid} if self.pin_uid else set()) | self.voices:
            if profiles.by_id(uid):
                try:
                    telefon_ich.keep_call(uid, self.t0, secs, self.questions, art)
                except Exception as e:
                    print("telefon: telefonat nicht gemerkt", type(e).__name__, flush=True)

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
                self.pkts["raus"] += 1
                self.pkts["sprache"] += payload is not None
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
                got = 0
                async for pcm in esp32.tts_stream(self.uid or None, text):
                    got += len(pcm)
                    await self.play(pcm)
                if not got:
                    print("telefon: sprachausgabe leer", flush=True)
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
            if self.entered:
                return "tasten", b""
            r = ear.feed(pcm) if pcm else None
            if r == "done":
                return "frage", bytes(ear.pcm)
            if r == "nothing" or (not ear.heard and time.time() - ear.started > wait):
                return "still", b""

    async def converse(self):
        name = ""
        if self.uid and not self.shared and self.mode != "extern":   # from outside the number may be forged: no name
            p = profiles.by_id(self.uid)
            name = (p or {}).get("name", "")
        s = settings()
        if not self.known and not s["gaeste"]:
            await self.say("Hallo, hier ist der Spark. Dieses Telefon ist noch keinem Profil zugeordnet. "
                           "Der Admin ordnet es unter Funktionen, Telefon zu. Tschüss.")
            self.end("nicht zugeordnet")
            return
        if self.mode == "bestaetigen":
            await self.confirm_number()
            return
        if self.out:
            if not await self.called():
                return
        else:
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
            if kind == "tasten":
                await self.pin(self.entered.popleft())
                asked = False
                continue
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

    async def called(self):
        """The Spark called (T4): says what it called for; True when the conversation goes on afterwards."""
        p = profiles.by_id(self.uid) or {}
        name = p.get("name", "")
        if self.mode == "test":
            await self.say("Hallo, hier ist der Spark. Das ist der Testanruf, das Telefon klappt. Tschüss.")
            self.end("test")
            return False
        if self.mode == "alarm":
            await self.say("Hallo, hier ist der Spark mit einer Meldung für den Admin. " + self.text + " Tschüss.")
            self.end("alarm")
            return False
        if self.mode == "rueckruf":       # the stored, confirmed number answered: that is the proof (plan T3/T4)
            self.pin_uid = self.uid
            await self.say(f"Hallo {name}, hier ist der Spark, wie versprochen. Was möchtest du wissen?")
            return True
        if self.mode == "weckruf":
            import chat
            local = datetime.datetime.now(chat.user_zone(profiles.settings(self.uid).get("tz", "")))
            hello = "Guten Morgen" if local.hour < 11 else "Guten Tag" if local.hour < 18 else "Guten Abend"
            clock = f"{local.hour} Uhr" + (f" {local.minute}" if local.minute else "")
            await self.say(f"{hello}, hier ist der Spark. Es ist {clock}." + (f" {self.text}." if self.text else "")
                           + " Wenn du magst, frag mich etwas.")
            return True
        # a reminder: its words only for the profile itself (the voice, the Telefon-PIN; nothing to check: the own phone)
        if await self.prove(f"Hallo, hier ist der Spark mit einer Erinnerung für {name}." if name
                            else "Hallo, hier ist der Spark mit einer Erinnerung."):
            await self.say("Du wolltest erinnert werden: " + self.text + ". Noch etwas?")
            return True
        await self.say("Ich konnte nicht prüfen, dass du es bist. Die Erinnerung steht in deinen Mitteilungen. Tschüss.")
        print(f"telefon: erinnerung per anruf nicht vorgelesen fuer {_log_name(self.uid)}, nur mitteilung", flush=True)
        try:
            import push
            await push.send(self.uid, "📞 Erinnerung", self.text, tag="telefonanruf", why="Erinnerung")
        except Exception as e:
            print("telefon: erinnerung mitteilung", type(e).__name__, flush=True)
        self.end("nicht geprueft")
        return False

    async def prove(self, hello):
        """Whether the profile itself answered: its voice (speakers.verify) or its Telefon-PIN; True at once when
        neither can be checked (the profile's own phone, nothing to compare with)."""
        import speakers
        import telefon_ich
        cc = load_config().get("chat", {})
        can_voice = bool(cc.get("speaker_id", False)) and speakers.has_voice(self.uid)
        can_pin = telefon_ich.has_pin(self.uid)
        if not can_voice and not can_pin:
            await self.say(hello)
            return True
        ask = "Sag bitte kurz etwas" if can_voice else ""
        ask += ((" oder tippe" if ask else "Tippe bitte") + " deine Telefon-PIN und Raute.") if can_pin else "."
        await self.say(hello + " " + ask)
        for _ in range(2):
            kind, pcm = await self.hear(QUIET_ASK)
            if kind == "tasten":
                await self.pin(self.entered.popleft())
                if self.pin_uid == self.uid:
                    return True
                continue
            if kind == "frage" and can_voice:
                vt = self.voice_check(pcm)
                _uid, voice, _why = await self.voice_result(vt)
                if voice == self.uid:
                    return True
                if can_pin:
                    await self.say("Ich bin mir bei der Stimme nicht sicher. Tippe bitte deine Telefon-PIN und Raute.")
                continue
            break
        return False

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
        if self.mode == "extern" and self.uid and not self.pin_uid and CALLBACK_WORDS.search(text):
            if vt:
                vt.cancel()
            await self.call_back()
            return
        uid, voice, why = await self.voice_result(vt)
        self.questions += 1
        _bump("fragen")
        await self.answer(text, uid, voice, why)

    async def call_back(self):
        """From outside with an unsure voice: the caller asked for a call back. The Spark hangs up and calls the
        profile's confirmed number that matches this call (telefon_anruf.call_back): a forged number never reaches
        the one who forged it."""
        import telefon_anruf
        res = telefon_anruf.call_back(self.uid, self.number)
        if res == "ok":
            _bump("rueckruf")
            await self.say("Gut. Ich lege auf und rufe dich gleich unter deiner Nummer zurück. Tschüss.")
            self.end("rueckruf")
            return
        await self.say(telefon_anruf.NO_CALLBACK.get(res, telefon_anruf.NO_CALLBACK["aus"]))

    async def pin(self, entered):
        """A PIN typed and ended with # (Ich → Telefon): on an assigned handset for its profile, at a shared phone for
        the profile whose PIN it is; right: personal things for the rest of the call. Never spoken, logged or kept."""
        import push
        import telefon_ich
        if self.uid and not self.shared:
            cands = [self.uid]
        elif self.shared:
            cands = [u for u in profiles.user_ids() if features.allowed("telefon", u)]
        else:
            cands = []
        res, who = telefon_ich.pin_attempt(self.number, cands, entered)
        if res == "ok":
            self.pin_uid = who
            _bump("pin")
            print(f"telefon: pin richtig fuer {_log_name(who)}", flush=True)
            p = profiles.by_id(who) or {}
            await self.say(f"Danke, {p.get('name', '')}. Jetzt weiß ich, dass du es bist." if self.shared
                           else "Danke. Jetzt weiß ich, dass du es bist.")
        elif res == "none" and not cands:
            print("telefon: pin getippt, kein profil an diesem telefon", flush=True)
            await self.say("Hier gilt keine Telefon-PIN. Sie geht nur an deinem eigenen Mobilteil oder von deiner bestätigten Nummer.")
        elif res == "none":
            print("telefon: pin getippt, keine pin eingerichtet", flush=True)
            await self.say("Hier ist keine Telefon-PIN eingerichtet. Die PIN legst du unter Ich, Telefon fest.")
        elif res == "wrong":
            _bump("pinfalsch")
            print("telefon: pin falsch", flush=True)
            await self.say("Die PIN stimmt nicht.")
        else:
            _bump("pinfalsch")
            print(f"telefon: pin gesperrt fuer {telefon_ich.LOCK // 60} min nach {telefon_ich.FAILS} falschen", flush=True)
            await self.say("Die PIN stimmt nicht. Eine halbe Stunde lang nehme ich an diesem Telefon keine PIN an.")
            if who == "neu" and self.uid and not self.shared:    # once, when the lock begins
                try:
                    await push.send(self.uid, "🔐 Spark", f"{telefon_ich.FAILS} falsche Telefon-PINs an deinem Mobilteil. "
                                    f"{telefon_ich.LOCK // 60} Minuten lang nimmt der Spark dort keine PIN an.", tag="telefonpin")
                except Exception as e:
                    print("telefon: pin-mitteilung", type(e).__name__, flush=True)

    async def confirm_number(self):
        """A call from an own number waiting for its code (Ich → Telefon): type the code, then hang up."""
        import telefon_ich
        await self.say("Hallo, hier ist der Spark. Bitte tippe jetzt den Code aus Ich, Telefon.")
        for _ in range(telefon_ich.CODE_TRIES):
            got = await self.wait_keys(30)
            if not got:
                print("telefon: bestaetigung ohne code beendet", flush=True)
                await self.say("Ich habe keinen Code bekommen. Tschüss.")
                self.end("kein code")
                return
            res, who = telefon_ich.try_code(self.number, got)
            if res == "ok":
                _bump("bestaetigt")
                print(f"telefon: nummer bestaetigt fuer {_log_name(who)}", flush=True)
                await self.say("Danke, die Nummer ist jetzt bestätigt. Tschüss.")
                self.end("bestaetigt")
                return
            if res == "wrong":
                print("telefon: bestaetigungscode falsch", flush=True)
                await self.say("Der Code stimmt nicht. Bitte noch einmal.")
                continue
            print(f"telefon: bestaetigungscode verfallen ({res})", flush=True)
            break
        await self.say("Der Code stimmt nicht. Hol dir bitte unter Ich, Telefon einen neuen. Tschüss.")
        self.end("code falsch")

    async def wait_keys(self, wait):
        """What was typed next (a code or a PIN), or "" after wait seconds."""
        until = time.time() + wait
        while time.time() < until and not self.over.is_set():
            if self.entered:
                return self.entered.popleft()
            await self._take(0.2)
            self.digits.clear()
        return ""

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
        """(profile id for this question or "", the voice's profile or "", why not): fixed rules, never the model.
        A right PIN in this call stands for the voice."""
        if self.pin_uid:
            if vt is not None:
                vt.cancel()
            return self.pin_uid, self.pin_uid, ""
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
                self.voices.add(who)
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
            if voice != uid and not self.shared:
                import telefon_anruf
                import telefon_ich
                scope["speech_pin_hint"] = telefon_ich.has_pin(uid)   # chat.PHONE_PIN_HINT: the owner may type it
                # chat.PHONE_CALLBACK_HINT: from outside the owner may ask for a call back to the confirmed number
                scope["speech_callback_hint"] = self.mode == "extern" and telefon_anruf.call_back(uid, self.number, dry=True) == "ok"

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
    import telefon_anruf
    while True:
        try:
            await tick()
        except Exception as e:
            print("telefon: schleife", type(e).__name__, str(e)[:120], flush=True)
        try:
            await telefon_anruf.tick()        # the Spark calls (T4): ordered calls, call backs, the alarm
        except Exception as e:
            print("telefon: anrufe raus", type(e).__name__, str(e)[:120], flush=True)
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
            "calls": len(a.calls) if a else 0, "nat": bool(a and a.nat[0] and reg.get("ok"))}


def for_live():
    """Zustand → Live: signed in, calls now and today in numbers, never a number or a name."""
    st = state()
    if not st["on"]:
        return {"on": False}
    t = _today.counts()
    return {"on": True, "ok": st["ok"], "calls": st["calls"], "angenommen": t["angenommen"],
            "abgelehnt": t["abgelehnt"] + t["besetzt"], "fragen": t["fragen"], "minuten": t["sekunden"] // 60, "fremd": t["fremd"],
            "pin": t["pin"], "pinfalsch": t["pinfalsch"], "bestaetigt": t["bestaetigt"], "extern": t["extern"], "gaeste": t["gaeste"],
            "raus": t["raus"], "angerufen": t["angerufen"], "rueckruf": t["rueckruf"], "alarm": t["alarm"],
            "geplant": _planned()}


def _planned():
    """Calls the profiles ordered and still to come (T4), a number only."""
    import telefon_ich
    return sum(len(telefon_ich.planned(u)) for u in profiles.user_ids())


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
        why, nat = a.reg.get("why", "stumm"), bool(a.nat[0])
        if a.transport:
            if a.reg.get("ok"):
                await a.register(0)
            a.close()
    else:
        _agent["key"] = None
        await tick()
        why = state()["why"] if not state()["ok"] else "ok"
        nat = state()["nat"]
    print(f"telefon: verbindung geprueft, {why}" + (", nat dazwischen" if nat else ""), flush=True)
    return {"ok": why == "ok", "why": why, "text": SAY.get(why, SAY["abgelehnt"])[0], "nat": nat and why == "ok"}


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


@router.post("/api/admin/telefon/testanruf", dependencies=[Depends(auth)])
async def admin_test_call(request: Request):
    """"Spark ruft mich an" (step 4): a call to an internal number with a fixed sentence."""
    import telefon_anruf
    guard.limit(request, "telefonsuchen", admin=True)
    b = await json_body(request, 256)
    nr = clean_number(b.get("nr"))
    if not nr or not internal(nr):
        raise HTTPException(400, "Nur interne Nummern der Anlage (z. B. **611).")
    if not settings()["on"] or not signed_in():
        raise HTTPException(409, "Der Spark ist nicht an der Anlage angemeldet (Schritt 3).")
    res = await telefon_anruf.test_call(nr)
    de, en = TEST_SAY.get(res, TEST_SAY["fehler"])
    return {"ok": res == "angenommen", "why": res, "text": de, "text_en": en}


def forget(uid):
    """A profile is deleted: its handsets are no longer assigned (they then count as not assigned)."""
    with _lock:
        d = _read()
        nn = {k: v for k, v in (d.get("nummern") or {}).items() if v.get("uid") != uid}
        if nn != (d.get("nummern") or {}):
            d["nummern"] = nn
            _write(d)
