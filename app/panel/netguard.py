"""Outbound connections to addresses that people or outside text choose: web pages from search
results, calendars, address books, task lists, mail servers and Home Assistant.

One place decides where such a connection may go (allowed):
- PUBLIC (pages from search results): public internet addresses only.
- USER (CalDAV, CardDAV, webcal, IMAP): public addresses; addresses in the home network only when the
  admin allows it (panel.allow_lan, Einstellungen -> Sicherheit, default off).
- HOME (Home Assistant, which lives in the home network): public and home network addresses.
Never: link-local (169.254.x, cloud metadata), multicast, unspecified, and on this machine the ports
of the Spark's own services (30000-31099).

The name is resolved once and the connection goes to exactly the checked address (a second lookup
could answer differently: DNS rebinding); TLS still checks the certificate for the name. Every
redirect is a new connection and checked the same way. Answers are cut at max_bytes, also after
unpacking gzip, so a huge or packed answer cannot fill the memory. Login data (Authorization) only
goes to the site it was entered for (same host or same parent domain, e.g. the caldav servers of
icloud.com), never over plain http when the address was https.
"""
import asyncio
import imaplib
import ipaddress
import socket
import zlib
from urllib.parse import urlsplit

import httpcore
import httpx

PUBLIC, USER, HOME = "public", "user", "home"
OWN_PORTS = range(30000, 31100)
MAX_BYTES = 20 * 1024 * 1024


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
    if ip.is_loopback and int(port or 0) in OWN_PORTS:
        return "the Spark's own services are not reachable this way"
    if ip.is_global:
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
            raise Blocked(f"{host}: {why}")
    return infos[0][4][0]


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
