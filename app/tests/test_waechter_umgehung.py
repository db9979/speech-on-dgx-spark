"""Verbindungen am Wächter vorbei (plan knoten-seiten.md, Extra B, Dominik 2026-10-14): a module that opens a connection
itself (httpx client, socket, IMAP, SMTP, websocket, urlopen) instead of netguard.client()/resolve() must be listed in
netguard.DIRECT_OK with its kind and reason. A new direct connection without a line there turns this test red, so an
address from settings or from outside text cannot slip past the Wächter unnoticed; a line whose module no longer
connects directly turns it red too, so the list stays true."""
import ast
import os
import unittest

from tests import helpers

helpers.start()
import netguard  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = {("httpx", n) for n in ("AsyncClient", "Client", "get", "post", "put", "patch", "delete", "head", "stream", "request")} | {
    ("socket", "create_connection"), ("asyncio", "open_connection"), ("imaplib", "IMAP4_SSL"), ("imaplib", "IMAP4"),
    ("smtplib", "SMTP"), ("smtplib", "SMTP_SSL"), ("websockets", "connect"), ("request", "urlopen"), ("urllib", "urlopen"),
    ("aiohttp", "ClientSession"), ("requests", "get"), ("requests", "post"), ("requests", "Session")}
NAMES = {n for _, n in CALLS}
KINDS = {"lokal", "sprachmodell", "suche", "fest", "geprueft"}


def direct(path):
    """The lines of a module that open a connection themselves."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out, imported = [], set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in {m for m, _ in CALLS} | {"urllib"}:
            imported |= {a.asname or a.name for a in n.names if a.name in NAMES}
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, (ast.Name, ast.Attribute)):
            base = f.value.id if isinstance(f.value, ast.Name) else f.value.attr
            if (base, f.attr) in CALLS:
                out.append(n.lineno)
        elif isinstance(f, ast.Name) and f.id in imported:
            out.append(n.lineno)
    return out


def modules():
    out = {}
    for d in (os.path.join(APP, "panel"), APP):
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") and f not in ("netguard.py", "selftest.py"):
                lines = direct(os.path.join(d, f))
                if lines:
                    out[f[:-3]] = lines
    return out


class Umgehung(unittest.TestCase):
    def test_every_direct_connection_has_a_reason(self):
        found = modules()
        missing = {m: v for m, v in found.items() if m not in netguard.DIRECT_OK}
        self.assertEqual(missing, {}, "these modules connect without netguard.client()/resolve(): use netguard.client(level), "
                                      "or, for an own service on localhost or a fixed service, add a line with kind and reason to "
                                      "netguard.DIRECT_OK (lines: %s)" % missing)

    def test_no_stale_lines(self):
        found = modules()
        stale = sorted(m for m in netguard.DIRECT_OK if m not in found)
        self.assertEqual(stale, [], "netguard.DIRECT_OK lists modules that no longer connect directly: remove them")

    def test_kind_and_reason(self):
        for m, (kind, why) in netguard.DIRECT_OK.items():
            self.assertIn(kind, KINDS, m)
            self.assertGreater(len(why), 8, m)

    def test_finds_a_direct_connection(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("import httpx\nfrom socket import create_connection\nasync def a(u):\n    async with httpx.AsyncClient() as c:\n"
                    "        await c.get(u)\n    create_connection((u, 1))\n")
        try:
            self.assertEqual(sorted(direct(f.name)), [4, 6])
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
