"""Outbound connections to addresses that people or outside text choose: web pages from search
results, calendars, address books, task lists, mail servers and Home Assistant.

One place decides where such a connection may go (allowed):
- PUBLIC (pages from search results): public internet addresses only.
- USER (CalDAV, CardDAV, webcal, IMAP, SMTP): public addresses; addresses in the home network only when the
  admin allows it (panel.allow_lan, Einstellungen -> Sicherheit, default off).
- HOME (Home Assistant, which lives in the home network): public and home network addresses.
Never: link-local (169.254.x, cloud metadata), multicast, unspecified, and on this machine the ports
of the Spark's own services (30000-31099). While the Notaus is on (notaus.py, stage 1 and up) also no
public internet address at any level; the home network stays reachable as the level allows.

The name is resolved once and the connection goes to exactly the checked address (a second lookup
could answer differently: DNS rebinding); TLS still checks the certificate for the name. Every
redirect is a new connection and checked the same way. Answers are cut at max_bytes, also after
unpacking gzip, so a huge or packed answer cannot fill the memory. Login data (Authorization) only
goes to the site it was entered for (same host or same parent domain, e.g. the caldav servers of
icloud.com), never over plain http when the address was https.

hole_oeffentlich is the one way to fetch a page or file from a public address (search result pages chat.page_text,
the reMarkable's web page rmplus.web_page through it, Links als Dokument doklink.py): the Notaus first, every hop
checked before it is asked (oeffentlich) and at the connection (PUBLIC), at most WEITER redirects, a fixed
User-Agent, the content type from a fixed list, max_bytes and a time limit for all of it; a refusal is AbrufFehler
with a fixed word (WORTE).
"""
import asyncio
import contextvars
import imaplib
import ipaddress
import re
import smtplib
import socket
import zlib
from typing import NamedTuple
from urllib.parse import urlsplit

import httpcore
import httpx

PUBLIC, USER, HOME = "public", "user", "home"
OWN_PORTS = set(range(30000, 31100)) | {31443}   # the services' ports and the panel's https port
_own = {"t": 0.0, "ips": set()}
_model = {"host": "", "t": 0.0, "ips": set()}


def own_addresses():
    """Every address of this machine (its LAN and VPN addresses too), from /proc, cached for a minute: the
    services' ports are refused there as on loopback (a MCP service "in the home network" could be the Spark)."""
    import time
    if time.time() - _own["t"] < 60:
        return _own["ips"]
    ips = set()
    try:
        with open("/proc/net/fib_trie") as f:
            last = None
            for line in f:
                m = re.search(r"\|--\s+(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    last = m.group(1)
                elif "/32 host LOCAL" in line and last:
                    ips.add(ipaddress.ip_address(last))
    except OSError:
        pass
    try:
        with open("/proc/net/if_inet6") as f:
            for line in f:
                h = line.split()[0]
                ips.add(ipaddress.ip_address(":".join(h[i:i + 4] for i in range(0, 32, 4))))
    except (OSError, ValueError, IndexError):
        pass
    _own.update(t=time.time(), ips=ips)
    return ips


def model_addresses():
    """The addresses of the model computer (models.host, plan Raspberry-Pi split B1) when the models run elsewhere:
    its ports are the Spark's own services too, so a MCP or calendar address can never point at them. Empty on the
    all-in-one install; a name is looked up once a minute, a name that does not resolve gives nothing."""
    import time
    from common import load_config, model_host, model_local
    try:
        cfg = load_config()
    except (OSError, ValueError):
        return set()
    if model_local(cfg):
        return set()
    host = model_host(cfg)
    if _model.get("host") == host and time.time() - _model["t"] < 60:
        return _model["ips"]
    try:
        ips = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            ips = {ipaddress.ip_address(a[4][0].split("%")[0]) for a in socket.getaddrinfo(host, None)}
        except (OSError, ValueError, UnicodeError):
            ips = set()
    _model.update(host=host, t=time.time(), ips=ips)
    return ips
MAX_BYTES = 20 * 1024 * 1024
# set by the Dienst-Wächter (dienstwacht.py) while it looks at its services: those connections are no request, so
# they do not count on the Live page's Wächter list and a refused one does not start the Selbst-Notaus
QUIET = contextvars.ContextVar("netguard_quiet", default=False)


# Modules that open connections without client()/resolve() above, each with its reason (plan knoten-seiten.md, Extra B;
# tests/test_waechter_umgehung.py turns red for a module that connects directly and is not listed here, and for a line
# here whose module no longer does). Kinds: "lokal" = own services on 127.0.0.1; "sprachmodell" = the language model at
# chat.llm_url; "suche" = SearXNG at chat.search_url; "fest" = a fixed public service; "geprueft" = a socket opened only
# after resolve() checked the address. A new address from settings or from outside text never belongs here: it goes
# through client(). Findings about these ways: plaene/waechter-umgehung.md.
DIRECT_OK = {
    "account": ("lokal", "Sprachausgabe auf localhost (Ansagen fürs Gerät)"),
    "ack": ("lokal", "Sprachausgabe auf localhost (fehlende Kurzansagen)"),
    "admin": ("sprachmodell", "Sprachmodell (/models), eigene Sprachdienste und der Suchtest an der eingetragenen SearXNG-Adresse"),
    "agent": ("sprachmodell", "Sprachmodell und SearXNG"),
    "android": ("fest", "App-Release von GitHub, Datei mit SHA-256 geprüft"),
    "apns": ("fest", "Apple-Push (api.push.apple.com); Notaus-Meldungen laufen selbst darüber"),
    "begleiter": ("fest", "Sprachausgabe auf localhost und Begleiter-Release von GitHub (SHA-256 geprüft)"),
    "spontansteuern": ("fest", "SparkHilfe-Release von GitHub (Verzeichnis signiert, sobald es einen Schlüssel gibt; jede Datei mit SHA-256 geprüft)"),
    "berater": ("sprachmodell", "Sprachmodell für den Einstellungs-Assistenten"),
    "chat": ("sprachmodell", "Sprachmodell und SearXNG; Seiten aus Suchergebnissen gehen über client()"),
    "rundlauf": ("sprachmodell", "Probelauf: Sprechen, Hören und Sprachmodell über common.model_url und llm.py, wie die Funktionsprüfung"),
    "abschrift": ("sprachmodell", "Spracherkennung über common.model_url (eigener Dienst) für Aufnahmen in Stücken"),
    "dungeon": ("sprachmodell", "Sprachausgabe und Spracherkennung des Spiels über common.model_url (eigene Dienste)"),
    "dienstwacht": ("sprachmodell", "Probe des Sprachmodells; die anderen Proben gehen über client() und resolve()"),
    "steuerzentrale": ("lokal", "nur das eigene Panel auf 127.0.0.1 (/api/schirm/zustand), mit dem Schlüssel der Steuerzentrale"),
    "gehaeuse": ("lokal", "eigene Ports auf 127.0.0.1 (Dienste-Seite des Displays) und ein UDP-Socket zum Modell-Rechner, der nichts sendet (eigene Adresse)"),
    "docmake": ("sprachmodell", "Sprachmodell beim Erstellen von Dokumenten"),
    "bilder": ("lokal", "eigener Bild-Dienst auf 127.0.0.1 (image.port), malt ohne Netz"),
    "musik": ("lokal", "eigener Musik-Dienst (music.port, beim Teilen über das TLS-Tor), macht Musik ohne Netz"),
    "fernbild": ("lokal", "guacd auf 127.0.0.1:4822 und ein eigener Port auf 127.0.0.1 für genau eine Verbindung von guacd zur Leitung des Ankers"),
    "fernzugang": ("lokal", "nur die Route zur Heimnetz-Adresse eines koppelnden Ankers nachschlagen (UDP connect, es geht kein Paket hinaus)"),
    "bedarf": ("lokal", "die eigene Engine bei Bedarf (sd-server, ace-server) auf 127.0.0.1 (image.engine_port, music.engine_port), nur der Bild- und der Musik-Dienst fragen sie"),
    "llm_tor": ("lokal", "das LLM-Tor fragt nur die eigenen Engines auf 127.0.0.1 (llm.engine_port, llm.sehen_port)"),
    "tlstor": ("lokal", "das TLS-Tor reicht nur an die eigenen Dienste auf 127.0.0.1 weiter (asr, tts, llm, image.port, music.port)"),
    "steuer": ("lokal", "der Wärter des eigenen Modell-Rechners (common.model_url, gepinntes Zertifikat, Wärter-Schlüssel)"),
    "teilen": ("lokal", "die Kopplung mit dem eigenen anderen Rechner (Port 31008, nur von root auf Befehl, Beweis mit dem Code)"),
    "weiche_abstimmen": ("sprachmodell", "Sprachmodell für Wortvorschläge der Weiche-Abstimmung (llm.py, über vorrang)"),
    "entwickeln": ("fest", "nur root (speech-spark lokal zweige): GitHubs Tests eines Zweigs opencode/… bei api.github.com, ohne Schlüssel, wie update.sh"),
    "werkstatt": ("lokal", "die Sandbox fragt nur das eigene LLM-Tor auf 127.0.0.1 (llm.port, ganz hinten); sonst ist ihr jedes Netz gesperrt (IPAddressDeny)"),
    "modelle": ("lokal", "misst die eigene Engine auf 127.0.0.1 (modelle.MESS_PORT) und malt dabei über den Bild-Dienst auf 127.0.0.1"),
    "esp32": ("fest", "eigene Sprachdienste auf localhost, Firmware-Release von GitHub (SHA-256 geprüft), Lautsprecher nach resolve()"),
    "hamelden": ("sprachmodell", "Sprachmodell; Home Assistant geht über client()"),
    "health": ("sprachmodell", "Gesundheitstest: Sprachmodell, eigene Sprachdienste, SearXNG"),
    "images": ("sprachmodell", "Sprachmodell"),
    "intent": ("sprachmodell", "Sprachmodell für unklare Fragen der Weiche"),
    "llm": ("sprachmodell", "Sprachmodell (llm.complete für Hintergrundaufgaben; Adresse aus chat.llm_url)"),
    "llmstart": ("lokal", "/health der eigenen Sprachmodell-Engine auf 127.0.0.1 (Port aus dem Katalog)"),
    "sparkkalender": ("lokal", "kein Netz: der Spark-Kalender antwortet im Panel selbst (httpx.MockTransport), seine Adresse spark.invalid löst nie auf"),
    "loopwacht": ("lokal", "nur die Meldung an systemd über den Unix-Socket aus $NOTIFY_SOCKET (Watchdog), kein Netz"),
    "mcpserver": ("lokal", "eigene Sprachdienste auf localhost"),
    "monitor": ("lokal", "Gesundheitsabfrage der eigenen Dienste auf localhost"),
    "ichweiss": ("suche", "SearXNG für den Netz-Tipp, nur mit dem Wort eines bestätigten Interesses"),
    "proactive": ("sprachmodell", "Sprachmodell und SearXNG"),
    "push": ("fest", "Browser-Push nur an bekannte Push-Dienste (PUSH_HOSTS)"),
    "quality": ("sprachmodell", "Sprachmodell"),
    "angriffsprobe": ("sprachmodell", "Sprachmodell"),
    "rmplus": ("sprachmodell", "Sprachmodell und SearXNG; Webseiten gehen über client()"),
    "room": ("suche", "SearXNG für den Raummodus"),
    "schreib": ("sprachmodell", "Sprachmodell"),
    "speicher": ("geprueft", "SFTP und SMB nach resolve()"),
    "system": ("sprachmodell", "Einrichtung: Test des Sprachmodells an der eingegebenen Adresse (nur Admin)"),
    "systemone": ("sprachmodell", "Sprachmodell"),
    "telegram": ("fest", "Telegram-Bot-API und eigene Sprachdienste auf localhost"),
    "tidy": ("sprachmodell", "Sprachmodell"),
    "transit": ("fest", "Fahrplan-Dienst (chat.transit_url)"),
    "update": ("fest", "Update-Prüfung bei GitHub"),
    "vorrang": ("sprachmodell", "Sprachmodell und eigene Sprachdienste"),
    "weather": ("fest", "Wetter-Dienst (chat.weather_url, chat.geocode_url)"),
    "wiki": ("fest", "Wikipedia-API (chat.wiki_url)"),
    "wyoming": ("lokal", "eigene Sprachdienste auf localhost"),
    "telefon": ("geprueft", "SIP und Ton (UDP) nur mit der Telefonanlage nach resolve() im Heimnetz und der Ton-Adresse aus ihrem SDP"),
    "zertpin": ("geprueft", "Zertifikat lesen nach resolve()"),
    "netproxy": ("geprueft", "der netguard-Proxy für yt-dlp (ytquelle.py): nur CONNECT auf Port 443 zu Hosts der festen Liste, Tunnel erst nach resolve() (PUBLIC, Notaus)"),
    "offline": ("geprueft", "Ohne Internet: eine Uhrzeit-Frage (SNTP, UDP 123) nur an den Zeitserver im Heimnetz nach resolve() (HOME)"),
    "halive": ("geprueft", "WebSocket zum eigenen Home Assistant nach resolve() mit Heimnetz-Regeln (HOME), nur lesen"),
    "asr_proxy": ("lokal", "Spracherkennung: Proxy zur Engine auf localhost"),
    "satzende": ("lokal", "die eigene Spracherkennung (POST /v1/turn, Smart Turn auf dem Modell-Rechner über common.model_url)"),
    "tts_proxy": ("lokal", "Sprachausgabe: Proxy zur Engine auf localhost"),
    "bench": ("lokal", "Messung der eigenen Dienste auf localhost (Kommandozeile)"),
}


class Blocked(ValueError):
    pass


class TooLarge(ValueError):
    pass


def lan_allowed():
    try:
        from common import load_config
        return bool(load_config().get("panel", {}).get("allow_lan", False))
    except Exception:
        return False


def allowed(ip, port, level):
    """None when a connection to ip:port is fine at this level, else the reason."""
    ip = ipaddress.ip_address(str(ip).split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if int(port or 0) in OWN_PORTS and (ip.is_loopback or ip.is_unspecified or ip in own_addresses()
                                     or ip in model_addresses()):
        return "the Spark's own services are not reachable this way"
    if ip.is_global:
        import notaus   # Notaus stage 1 and up: nothing to the internet (notaus.py)
        if notaus.blocks("internet") if QUIET.get() else notaus.refuse("internet"):
            return "Notaus: no connections to the internet"
        return None
    if level == PUBLIC:
        return "only public internet addresses"
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return "this address is not allowed"
    if level == HOME or lan_allowed():
        return None
    return "addresses in the home network are off (Einstellungen -> Sicherheit: Heimnetz-Adressen erlauben)"


def resolve(host, port, level):
    """The address to connect to: every address the name has must be allowed (else Blocked)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise httpx.ConnectError(f"{host}: name not found ({e})")
    if not infos:
        raise httpx.ConnectError(f"{host}: name not found")
    for info in infos:
        why = allowed(info[4][0], port, level)
        if why:
            _live(host, port, level, info[4][0], why)
            if not why.startswith("Notaus") and not QUIET.get():
                try:   # a series of refused targets may start the Selbst-Notaus (notaus.watch, switch off by default)
                    import notaus
                    notaus.watch("netguard")
                except Exception:
                    pass
            raise Blocked(f"{host}: {why}")
    _live(host, port, level, infos[0][4][0], None)
    return infos[0][4][0]


def _live(host, port, level, ip, why):
    """Zustand → Live (live.py): each decision with its reason; never raises."""
    if QUIET.get():
        return
    try:
        import live
        live.outgoing(host, port, level, ip, why)
    except Exception:
        pass


class _Backend(httpcore.AsyncNetworkBackend):
    def __init__(self, level):
        self.level = level
        self.inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        ip = await asyncio.to_thread(resolve, host, port, self.level)
        return await self.inner.connect_tcp(ip, port, timeout=timeout, local_address=local_address,
                                            socket_options=socket_options)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise Blocked("no local sockets")

    async def sleep(self, seconds):
        await self.inner.sleep(seconds)


def same_site(a, b):
    """Same host, or both below the same parent domain (p12-caldav.icloud.com, caldav.icloud.com)."""
    a, b = (a or "").lower().rstrip("."), (b or "").lower().rstrip(".")
    if a == b:
        return True
    try:
        ipaddress.ip_address(a)
        return False
    except ValueError:
        pass
    pa, pb = a.split("."), b.split(".")
    n = 3 if len(pa) > 2 and len(pa[-1]) == 2 and pa[-2] in ("co", "com", "org", "net", "gov", "ac", "edu") else 2
    return len(pa) >= n and len(pb) >= n and pa[-n:] == pb[-n:]


class _Capped(httpx.AsyncByteStream):
    def __init__(self, inner, most, encoding):
        self.inner, self.most = inner, most
        self.dec = None
        if encoding in ("gzip", "x-gzip"):
            self.dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            self.dec = zlib.decompressobj()

    async def __aiter__(self):
        n = 0
        async for chunk in self.inner:
            if self.dec is not None:
                chunk = self.dec.decompress(chunk, self.most + 1 - n)
                if self.dec.unconsumed_tail:
                    raise TooLarge(f"the answer is larger than {self.most // 1048576} MB")
            n += len(chunk)
            if n > self.most:
                raise TooLarge(f"the answer is larger than {self.most // 1048576} MB")
            yield chunk

    async def aclose(self):
        await self.inner.aclose()


class _Transport(httpx.AsyncHTTPTransport):
    def __init__(self, level, origin, most, verify=True, seen=None):
        super().__init__(verify=verify, retries=0)
        self._pool._network_backend = _Backend(level)
        self.origin, self.most, self.seen = origin, most, seen
        self._fine, self._why = False, ""      # for seen: one verdict per client, given when it closes

    async def handle_async_request(self, request):
        if self.origin is not None and "authorization" in request.headers:
            o = self.origin
            if not same_site(request.url.host, o.hostname) or (o.scheme == "https" and request.url.scheme != "https"):
                del request.headers["authorization"]
        request.headers["accept-encoding"] = "gzip, deflate"
        try:
            r = await super().handle_async_request(request)
        except Exception as e:
            self._why = self._why or ("gesperrt" if isinstance(e, Blocked) else "nicht_erreichbar")
            raise
        if r.status_code < 400:
            self._fine = True
        elif r.status_code in (401, 403):
            self._why = "anmeldung"           # a refused login outweighs every other reason
        else:
            self._why = self._why or ("adresse" if r.status_code in (404, 410) else "dienst")
        if int(r.headers.get("content-length") or 0) > self.most:
            try:
                import live
                live.cut(request.url.host)
            except Exception:
                pass
            await r.aclose()
            raise TooLarge(f"the answer is larger than {self.most // 1048576} MB")
        enc = r.headers.get("content-encoding", "identity").lower().strip()
        if enc not in ("identity", "gzip", "x-gzip", "deflate", ""):
            await r.aclose()
            raise ValueError(f"unsupported content encoding {enc}")
        r.stream = _Capped(r.stream, self.most, enc)
        if "content-encoding" in r.headers:
            del r.headers["content-encoding"]
        return r

    def _verdict(self):
        # one look-up asks several addresses (CalDAV): it worked when one answered and none refused the login
        if self.seen and (self._fine or self._why):
            _tell(self.seen, self._fine and self._why != "anmeldung", self._why or "fehler")
        self.seen = None

    async def aclose(self):
        self._verdict()
        await super().aclose()

    async def __aexit__(self, *exc):     # "async with client" ends here, not in aclose
        self._verdict()
        await super().__aexit__(*exc)


def _tell(seen, ok, why):
    """Ich → Mein Zustand (hintergrund.py): whether the service answered, as a fixed word; never raises."""
    if seen:
        try:
            seen(ok, "" if ok else why)
        except Exception:
            pass


def client(level, origin=None, max_bytes=MAX_BYTES, verify=True, seen=None, **kw):
    """An httpx.AsyncClient that keeps the rules above. origin: the address the user entered (login
    data goes only to its site). seen: called with (answered, fixed reason) once the client closes
    (hintergrund.tracker), so a profile sees whether its service works without the page asking it."""
    t = _Transport(level, urlsplit(origin) if origin else None, max_bytes, verify=verify, seen=seen)
    return httpx.AsyncClient(transport=t, trust_env=False, **kw)


class IMAP4_SSL(imaplib.IMAP4_SSL):
    """imaplib's IMAP over TLS, connected to the checked address of the mail server (USER rules)."""

    def _create_socket(self, timeout):
        ip = resolve(self.host, self.port, USER)
        sock = socket.create_connection((ip, self.port), timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


class SMTP(smtplib.SMTP):
    """smtplib's SMTP (then STARTTLS, senden.py requires it) to the checked address of the outgoing server."""

    def _get_socket(self, host, port, timeout):
        ip = resolve(host, port, USER)
        return socket.create_connection((ip, port), timeout, self.source_address)


class SMTP_SSL(smtplib.SMTP_SSL):
    """smtplib's SMTP over TLS (port 465) to the checked address of the outgoing server."""

    def _get_socket(self, host, port, timeout):
        ip = resolve(host, port, USER)
        sock = socket.create_connection((ip, port), timeout, self.source_address)
        return self.context.wrap_socket(sock, server_hostname=host)


# ---------------------------------------------------------------- one fetch from a public address
WEITER = 4                 # redirects followed at most, each one checked again
AGENT = "Mozilla/5.0 (speech-on-dgx-spark)"
HTML = ("text/html", "application/xhtml+xml")
# the fixed words of a refusal (journal lines, Ich → Dokumente): notaus, privat (not a public address, also after a
# redirect or the name lookup), adresse (no http(s), login data in it, no host), groesse, art (content type not
# asked for), status (no 200/304), weiter (too many redirects), zeit, netz
WORTE = ("notaus", "privat", "adresse", "groesse", "art", "status", "weiter", "zeit", "netz")


class AbrufFehler(ValueError):
    def __init__(self, wort):
        super().__init__(wort)
        self.wort = wort if wort in WORTE else "netz"


class Abruf(NamedTuple):
    data: bytes           # empty for 304
    art: str              # the content type without parameters, lower case ("" for 304)
    charset: str
    final_url: str        # after the redirects
    etag: str
    lastmod: str
    status: int           # 200, or 304 for a conditional request that found the page unchanged


def oeffentlich(url):
    """True when the address is http(s) without login data and its host resolves only to public addresses (checked
    before each request: pages never reach the Spark itself, the home network or the router; the connection checks
    the same again, resolve())."""
    try:
        u = urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname or u.username is not None or u.password is not None:
            return False
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
        return bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)
    except (OSError, ValueError, UnicodeError):
        return False


def als_text(got):
    """The fetched bytes as text in their charset (utf-8 when it is missing or unknown)."""
    try:
        return got.data.decode(got.charset or "utf-8", errors="replace")
    except LookupError:
        return got.data.decode("utf-8", errors="replace")


async def hole_oeffentlich(url, max_bytes, sekunden, arten, headers=None, abschneiden=False):
    """GET one public address (Abruf). arten: the content types allowed (HTML, or the kinds a caller reads);
    headers: extra request headers (If-None-Match, If-Modified-Since); abschneiden: an answer longer than max_bytes
    is cut there instead of refused (pages of search results). Raises AbrufFehler with a fixed word."""
    import notaus
    if notaus.refuse("internet"):
        raise AbrufFehler("notaus")
    want = {"User-Agent": AGENT, **{k: v for k, v in (headers or {}).items() if v}}

    async def fetch():
        target = url
        for _ in range(WEITER + 1):
            u = urlsplit(target)
            if u.scheme not in ("http", "https") or not u.hostname or u.username is not None or u.password is not None:
                raise AbrufFehler("adresse")
            if not await asyncio.to_thread(oeffentlich, target):
                raise AbrufFehler("privat")
            async with client(PUBLIC, max_bytes=max_bytes * 2 if abschneiden else max_bytes) as pc, \
                    pc.stream("GET", target, timeout=sekunden, follow_redirects=False, headers=want) as r:
                if r.is_redirect and r.headers.get("location"):
                    target = str(r.url.join(r.headers["location"]))
                    continue
                if r.status_code == 304:
                    return Abruf(b"", "", "", str(r.url), r.headers.get("etag", ""), r.headers.get("last-modified", ""), 304)
                if r.status_code != 200:
                    raise AbrufFehler("status")
                art = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if art not in arten:
                    raise AbrufFehler("art")
                raw = bytearray()
                async for chunk in r.aiter_bytes():
                    raw += chunk
                    if len(raw) > max_bytes:
                        if abschneiden:
                            del raw[max_bytes:]
                            break
                        raise AbrufFehler("groesse")
                return Abruf(bytes(raw), art, r.encoding or "", str(r.url), r.headers.get("etag", "")[:200],
                             r.headers.get("last-modified", "")[:100], 200)
        raise AbrufFehler("weiter")
    try:
        return await asyncio.wait_for(fetch(), sekunden)
    except AbrufFehler:
        raise
    except Blocked as e:
        raise AbrufFehler("notaus" if "Notaus" in str(e) else "privat") from None
    except TooLarge:
        raise AbrufFehler("groesse") from None
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise AbrufFehler("zeit") from None
    except (httpx.HTTPError, OSError, ValueError):
        raise AbrufFehler("netz") from None
