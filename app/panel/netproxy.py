"""The netguard proxy (plan open-notebook, Stufe 3b): a CONNECT proxy on 127.0.0.1 for one helper program that has its
own network code (yt-dlp, ytquelle.py), so that none of its connections goes around netguard.

- Only for one run: the port is chosen by the system, it lives as long as the run (async with) and answers only a
  request with its one-time key (Proxy-Authorization Basic, secrets, compared in constant time); another program on
  this machine cannot use it.
- Only CONNECT to port 443 (TLS stays end to end, the program checks the certificate for the name) of a host the caller's
  fixed list allows (erlaubt(host) -> bool); never an IP literal, never plain http, never another method.
- The name is resolved by netguard.resolve(host, 443, PUBLIC): every address must be public (never the Spark, the home
  network or the router), the Notaus holds it, Zustand → Live sees the connection; the tunnel goes to exactly that
  checked address (no second lookup: DNS rebinding).
- At most most_bytes from the servers over all tunnels of the run (and UP_MOST to them), at most TUNNEL_MOST tunnels at
  once; beyond the limit every tunnel is closed. A refusal is counted by a fixed word (WORTE), never with the host.
"""
import asyncio
import base64
import hmac
import ipaddress
import re
import secrets
from collections import Counter

import netguard

HEAD_MOST = 8 * 1024       # the request head of one CONNECT
HEAD_S = 10                # seconds for the head
CONNECT_S = 15             # seconds for the connection to the server
UP_MOST = 32 * 1024**2     # bytes sent to the servers over the run (requests are small)
TUNNEL_MOST = 8            # tunnels at once
CHUNK = 64 * 1024
USER = "spark"
HIER = "127.0.0.1"         # where the proxy listens
ZIEL_PORT = 443            # the port a tunnel goes to (tests point it at a local echo server)
# the fixed words of a refusal: methode (no CONNECT), anmeldung (no or a wrong key), port (not 443), host (not on the
# list, an IP literal), privat (an address that is not public), notaus, netz (no answer), viele (too many at once),
# groesse (the run's limit)
WORTE = ("methode", "anmeldung", "port", "host", "privat", "notaus", "netz", "viele", "groesse")
HOST = re.compile(r"[a-z0-9.-]{1,253}")


class Proxy:
    """async with Proxy(erlaubt, most_bytes) as p: p.url for the program's --proxy; afterwards p.abgelehnt (Counter of
    WORTE), p.tunnel (opened), p.unten (bytes from the servers), p.zu_gross."""

    def __init__(self, erlaubt, most_bytes):
        self.erlaubt, self.most = erlaubt, int(most_bytes)
        self.key = secrets.token_urlsafe(24)
        self._auth = b"Basic " + base64.b64encode(f"{USER}:{self.key}".encode())
        self.abgelehnt, self.tunnel, self.unten, self.oben, self.zu_gross = Counter(), 0, 0, 0, False
        self._offen, self._server, self.port, self._kunden = set(), None, 0, 0

    @property
    def url(self):
        # this proxy itself on loopback (no model service: those go through common.model_url)
        return "http://" + f"{USER}:{self.key}@{HIER}:{self.port}"

    async def __aenter__(self):
        self._server = await asyncio.start_server(self._kunde, HIER, 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self._server.close()
        for w in list(self._offen):
            w.close()
        try:
            await asyncio.wait_for(self._server.wait_closed(), 5)
        except (asyncio.TimeoutError, OSError):
            pass

    def _nein(self, writer, code, wort):
        self.abgelehnt[wort] += 1
        try:
            writer.write(f"HTTP/1.1 {code} {'Forbidden' if code == 403 else 'Refused'}\r\nContent-Length: 0\r\n"
                         "Connection: close\r\n\r\n".encode())
        except OSError:
            pass

    def pruefe(self, head):
        """(host, "") for an allowed request head, else (None, fixed word). Nothing is looked up here."""
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3 or parts[0] != "CONNECT" or not parts[2].startswith("HTTP/1."):
            return None, "methode"
        auth = [x.split(":", 1)[1].strip().encode("latin-1") for x in lines[1:]
                if x.lower().startswith("proxy-authorization:")]
        if len(auth) != 1 or not hmac.compare_digest(auth[0], self._auth):
            return None, "anmeldung"
        host, _, port = parts[1].rpartition(":")
        if port != "443":
            return None, "port"
        host = host.lower().rstrip(".")
        try:
            ipaddress.ip_address(host.strip("[]"))
            return None, "host"
        except ValueError:
            pass
        if not HOST.fullmatch(host) or not self.erlaubt(host):
            return None, "host"
        return host, ""

    async def _kunde(self, reader, writer):
        self._offen.add(writer)
        self._kunden += 1
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_S)
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
                return
            if len(head) > HEAD_MOST:
                return self._nein(writer, 400, "methode")
            host, wort = self.pruefe(head)
            if wort:
                return self._nein(writer, 407 if wort == "anmeldung" else 403, wort)
            if self.zu_gross:
                return self._nein(writer, 403, "groesse")
            if self._kunden > TUNNEL_MOST:
                return self._nein(writer, 503, "viele")
            try:
                ip = await asyncio.to_thread(netguard.resolve, host, ZIEL_PORT, netguard.PUBLIC)
            except netguard.Blocked as e:
                return self._nein(writer, 403, "notaus" if "Notaus" in str(e) else "privat")
            except Exception:   # noqa: BLE001  (a name that is not found: httpx.ConnectError)
                return self._nein(writer, 502, "netz")
            try:
                r2, w2 = await asyncio.wait_for(asyncio.open_connection(ip, ZIEL_PORT), CONNECT_S)
            except (asyncio.TimeoutError, OSError):
                return self._nein(writer, 502, "netz")
            self._offen.add(w2)
            self.tunnel += 1
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(self._rohr(reader, w2, False), self._rohr(r2, writer, True), return_exceptions=True)
            self._offen.discard(w2)
            w2.close()
        finally:
            self._kunden -= 1
            self._offen.discard(writer)
            writer.close()

    async def _rohr(self, src, dst, nach_unten):
        """Copies one direction of a tunnel and counts it; the run's limit closes every tunnel."""
        try:
            while True:
                chunk = await src.read(CHUNK)
                if not chunk:
                    break
                if nach_unten:
                    self.unten += len(chunk)
                else:
                    self.oben += len(chunk)
                if self.unten > self.most or self.oben > UP_MOST:
                    if not self.zu_gross:
                        self.zu_gross = True
                        self.abgelehnt["groesse"] += 1
                    for w in list(self._offen):
                        w.close()
                    break
                dst.write(chunk)
                await dst.drain()
        except (OSError, asyncio.CancelledError, ConnectionError):
            pass
        finally:
            try:
                dst.close()
            except OSError:
                pass
