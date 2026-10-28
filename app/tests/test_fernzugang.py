"""Fernzugang (fernzugang.py, anker/spark-anker.py, plan ssh-vermittlung stage 1): one self-test for every protection
rule. Off by default and 404 while off; admins in their browser only (never guests, profiles, the Verwalter, a device
key); a fresh code before pairing and before every session, never without a second step; the one-time code never in
a URL, an argument or a log; the ticket once, short, bound to its login; the WebSocket's own Origin check; the
Notaus closes everything and lets nothing in; a changed host key is no connection; a message cap on both sockets; a
removed system's key gets nothing but „abbauen“; `entfernen` removes every path it made; logs in fixed words only;
no tool and no model ever sees the shell. A real run end to end: the anchor program over TLS, the panel's SSH client
(paramiko) and a small SSH server. No test depends on the time of day."""
import asyncio
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import socket
import ssl
import tempfile
import threading
import time
import types
import unittest
import unittest.mock

from tests import helpers

helpers.start()
import admin  # noqa: E402
import dienstwacht  # noqa: E402
import fernzugang  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import mfa  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import vault  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
OTHER = TestClient(panel.app)          # the same admin in another browser (logged in before the tests ask for a code)
OTHER.post("/api/login", json={"password": "secret-admin"})
OUT = "https://spark.example.org"
CODE = {"x-speech-code": "123456"}


def program():
    spec = importlib.util.spec_from_file_location("spark_anker", fernzugang.PROGRAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def host_key():
    """An ed25519 host key: (paramiko key, OpenSSH public line)."""
    import paramiko
    priv, pub = fernzugang._new_keypair()
    return paramiko.Ed25519Key.from_private_key(io.StringIO(priv)), " ".join(pub.split()[:2])


HOST, HOST_PUB = host_key()


@contextlib.contextmanager
def journal():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def reset():
    fernzugang.CODES.pending.clear()
    fernzugang.TICKETS.clear()
    fernzugang.ANKER.clear()
    fernzugang.SITZUNG.clear()
    with contextlib.suppress(OSError):
        os.remove(fernzugang.FILE)
    for k in [k for k in guard._rate if str(k[0]).startswith("fernzugang")]:
        guard._rate.pop(k, None)
    guard.reset()


class Base(unittest.TestCase):
    def setUp(self):
        self.real = (mfa.enabled, mfa.verify)
        mfa.enabled = lambda who: who == mfa.ADMIN
        mfa.verify = lambda who, code: who == mfa.ADMIN and code == "123456"
        helpers.set_config(fernzugang=True, public=False, deny={})
        reset()

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        helpers.set_config(fernzugang=False)
        if notaus.level():
            notaus.lift(0, "test")
        reset()

    def pair(self, name="vps-1", hostkey=HOST_PUB):
        r = ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": name, "origin": OUT}, headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        code = r.json()["code"]
        r = TestClient(panel.app).post("/api/fernzugang/anker/koppeln", json={"code": code, "hostkey": hostkey,
                                                                              "os": "Debian 13", "version": "1.0.0"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class Off(Base):
    def test_off_by_default_no_profile_switch_and_404_while_off(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["fernzugang"], False)
        import features
        self.assertNotIn("chat.fernzugang", features.DEFAULT_ON)
        self.assertIn("fernzugang", features.SPARK_ONLY)
        self.assertNotIn("fernzugang_on", profiles.SETTINGS)
        helpers.set_config(fernzugang=False)
        c = TestClient(panel.app)
        self.assertEqual(c.get("/fernzugang/anker").status_code, 404)
        self.assertEqual(c.post("/api/fernzugang/anker/koppeln", json={"code": "X"}).status_code, 404)
        self.assertEqual(c.post("/api/fernzugang/anker/abgebaut", json={}).status_code, 404)
        self.assertEqual(ADMIN.get("/api/admin/fernzugang").json()["on"], False)
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "a", "origin": OUT},
                                    headers=CODE).status_code, 404)
        with journal() as j:
            for path in ("/api/fernzugang/anker", "/api/fernzugang/terminal"):
                with self.assertRaises(WebSocketDisconnect):
                    with c.websocket_connect(path, headers={"origin": "http://testserver"}) as ws:
                        ws.receive_text()
        self.assertIn("fernzugang: anker_abgewiesen | aus", j.getvalue())
        self.assertIn("fernzugang: sitzung_abgewiesen | aus", j.getvalue())
        self.assertEqual(fernzugang.probes(), {})
        self.assertEqual(fernzugang.for_live(), {"on": False})

    def test_settings_have_ranges(self):
        self.assertIsNone(fernzugang.check({"fernzugang_sitzungen": 2, "fernzugang_leerlauf_min": 15}))
        self.assertIn("fernzugang_sitzungen", fernzugang.check({"fernzugang_sitzungen": 9}))
        self.assertIn("fernzugang_offline_min", fernzugang.check({"fernzugang_offline_min": True}))
        self.assertEqual(fernzugang.leerlauf_s({"fernzugang_leerlauf_min": 15}), 900)
        self.assertEqual(fernzugang.max_sitzungen({"fernzugang_sitzungen": 99}), fernzugang.SITZUNGEN[0])


class Pairing(Base):
    def test_admin_in_the_browser_only(self):
        guest = TestClient(panel.app)
        self.assertIn(guest.get("/api/admin/fernzugang").status_code, (401, 403))
        self.assertIn(guest.post("/api/admin/fernzugang/koppeln", json={"name": "a", "origin": OUT}).status_code, (401, 403))
        r = ADMIN.post("/api/admin/profiles", json={"name": "FernPia", "pin": "1234"})
        self.assertIn(r.status_code, (200, 409))
        pia = TestClient(panel.app)
        self.assertEqual(pia.post("/api/profile/login", json={"name": "FernPia", "pin": "1234"}).status_code, 200)
        self.assertIn(pia.get("/api/admin/fernzugang").status_code, (401, 403))
        # a device key (app, watch, speaker …) is never an admin in the browser, also beside the admin cookie
        req = types.SimpleNamespace(headers={profiles.DEVICE_HEADER: "x"}, cookies={})
        self.assertFalse(fernzugang.is_admin_browser(req))
        # the Verwalter (coadmin role „manager“) never: the role check wants "admin" in its own browser
        import coadmin
        with unittest.mock.patch.object(coadmin, "session", lambda r: {"id": "u", "name": "V", "role": "manager", "via": "b"}), \
                unittest.mock.patch.object(fernzugang.core, "_admin_cookie_age", lambda r: None):
            self.assertFalse(fernzugang.is_admin_browser(types.SimpleNamespace(headers={}, cookies={})))
        with unittest.mock.patch.object(coadmin, "session", lambda r: {"id": "u", "name": "A", "role": "admin", "via": "d1"}), \
                unittest.mock.patch.object(fernzugang.core, "_admin_cookie_age", lambda r: None):
            self.assertFalse(fernzugang.is_admin_browser(types.SimpleNamespace(headers={}, cookies={})))   # the iPhone app: stage 2

    def test_fresh_code_and_a_second_step(self):
        r = ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "vps", "origin": OUT})
        self.assertEqual(r.status_code, 428)      # „Schutz ändern“: asked every time, also of the admin
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "vps", "origin": OUT},
                                    headers={"x-speech-code": "000000"}).status_code, 428)
        mfa.enabled = lambda who: False           # no second step: never a remote shell
        with journal() as j:
            r = ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "vps", "origin": OUT}, headers=CODE)
        self.assertEqual(r.status_code, 403)
        self.assertIn("zweitem Anmeldeschritt", r.json()["detail"])
        self.assertIn("fernzugang: koppeln_code | kein zweiter schritt | 0", j.getvalue())

    def test_pairing_code_once_never_in_url_command_or_log(self):
        with journal() as j:
            r = ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "vps-1", "origin": OUT}, headers=CODE)
            d = r.json()
            code = d["code"]
            self.assertEqual(d["befehl"], f"curl -fsSL {OUT}/fernzugang/anker | sudo python3 - einrichten {OUT}")
            self.assertNotIn(code, d["befehl"])
            self.assertNotIn(code.replace("-", ""), d["befehl"])
            anchor = TestClient(panel.app)
            r = anchor.post("/api/fernzugang/anker/koppeln", json={"code": code, "hostkey": HOST_PUB, "os": "Debian 13"})
            self.assertEqual(r.status_code, 200, r.text)
            got = r.json()
            again = anchor.post("/api/fernzugang/anker/koppeln", json={"code": code, "hostkey": HOST_PUB})
            self.assertEqual(again.status_code, 403)          # once
            self.assertEqual(anchor.post(f"/api/fernzugang/anker/koppeln?code={code}", json={"hostkey": HOST_PUB}).status_code, 403)
        out = j.getvalue()
        for secret in (code, code.replace("-", ""), got["key"]):
            self.assertNotIn(secret, out)
        self.assertIn("fernzugang: koppeln_code | admin | 1", out)
        self.assertIn("fernzugang: koppeln | ok | 1", out)
        self.assertIn("fernzugang: koppeln | falsch | 0", out)
        # what the anchor gets: its key, the Pi's public key with the comment, the user, the program's sum
        self.assertTrue(got["pi_key"].startswith("ssh-ed25519 ") and got["pi_key"].endswith("spark-fernzugang-" + got["id"]))
        self.assertEqual(got["user"], "spark")
        served = TestClient(panel.app).get("/fernzugang/anker")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(hashlib.sha256(served.content).hexdigest(), got["anker_sha256"])
        self.assertEqual(ADMIN.get("/api/admin/fernzugang").json()["anker"]["sha256"], got["anker_sha256"])   # „Prüfen“
        self.assertEqual(served.headers.get("cache-control"), "no-store")
        # on the disk: the device key only as a hash, the Pi's private key sealed, never in plain text
        with open(fernzugang.FILE) as f:
            raw = f.read()
        self.assertNotIn(got["key"], raw)
        self.assertNotIn("PRIVATE KEY", raw)
        x = json.loads(raw)["geraete"][got["id"]]
        self.assertTrue(x["pi_key"].startswith(vault.PREFIX))
        self.assertEqual(x["key_sha"], hashlib.sha256(got["key"].encode()).hexdigest())
        self.assertEqual(x["hostkey"], HOST_PUB)

    def test_expired_and_wrong_codes(self):
        r = ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "alt", "origin": OUT}, headers=CODE)
        code = r.json()["code"]
        for v in fernzugang.CODES.pending.values():
            v["t"] -= fernzugang.CODE_S + 1
        with journal() as j:
            r = TestClient(panel.app).post("/api/fernzugang/anker/koppeln", json={"code": code, "hostkey": HOST_PUB})
        self.assertEqual(r.status_code, 403)
        self.assertIn("fernzugang: koppeln | abgelaufen | 0", j.getvalue())
        r = ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "neu", "origin": OUT}, headers=CODE)
        r = TestClient(panel.app).post("/api/fernzugang/anker/koppeln", json={"code": r.json()["code"], "hostkey": "ssh-rsa AAAA"})
        self.assertEqual(r.status_code, 400)            # ed25519 host keys only

    def test_home_address_pins_the_certificate_and_plain_http_is_refused(self):
        import terminal
        with unittest.mock.patch.object(terminal, "cert_sha256", lambda: "ab" * 32), \
                unittest.mock.patch.object(fernzugang, "_spki_pin", lambda: "sha256//QUJD"):
            pcfg = {"port": 31080, "https_port": 31443}
            with unittest.mock.patch.object(fernzugang, "load_config", lambda part: pcfg):
                d = fernzugang.command("https://tars:31443")
                self.assertEqual(d["befehl"], "curl -fsSLk --pinnedpubkey 'sha256//QUJD' https://tars:31443/fernzugang/anker"
                                              " | sudo python3 - einrichten https://tars:31443 --fp " + "ab" * 32)
                self.assertIsNone(fernzugang.command("http://spark.example.org"))
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "x", "origin": "http://spark.example.org"},
                                    headers=CODE).status_code, 409)

    def test_at_most_max_systems(self):
        with unittest.mock.patch.object(fernzugang, "MAX_ANKER", 1):
            self.pair("eins")
            self.assertEqual(ADMIN.post("/api/admin/fernzugang/koppeln", json={"name": "zwei", "origin": OUT},
                                        headers=CODE).status_code, 409)


class Ticket(Base):
    def online(self, gid):
        class Dead:
            async def send_text(self, t):
                raise OSError("gone")

            async def close(self, code=1000):
                pass
        fernzugang.ANKER[gid] = fernzugang.Anker(Dead(), gid)

    def ticket(self, gid, client=ADMIN):
        r = client.post("/api/admin/fernzugang/sitzung", json={"geraet": gid, "cols": 100, "rows": 30}, headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["ticket"]

    def connect(self, client, ticket, origin="http://testserver"):
        head = {"origin": origin} if origin else {}
        with self.assertRaises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/fernzugang/terminal?t={ticket}", headers=head) as ws:
                ws.receive_text()
                ws.receive_text()

    def test_ticket_once_short_bound_to_its_login_and_origin(self):
        gid = self.pair()["id"]
        r = ADMIN.post("/api/admin/fernzugang/sitzung", json={"geraet": gid}, headers=CODE)
        self.assertEqual(r.status_code, 409)                      # offline: no ticket
        self.online(gid)
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/sitzung", json={"geraet": gid}).status_code, 428)   # fresh code
        t = self.ticket(gid)
        self.assertNotIn(t, json.dumps(list(fernzugang.TICKETS)))  # only its hash is kept
        with journal() as j:
            self.connect(ADMIN, t, origin="https://evil.example")   # a foreign page: refused before the ticket is used
            self.connect(ADMIN, t, origin="")                       # no Origin at all
        self.assertEqual(j.getvalue().count("fernzugang: sitzung_abgewiesen | fremde Seite"), 2)
        with journal() as j:
            self.connect(OTHER, t)                                   # another login, same admin: no
        self.assertIn("sitzung_abgewiesen | ticket", j.getvalue())
        t = self.ticket(gid)
        with journal() as j:
            self.connect(ADMIN, t)                                   # right: let in (the dead anchor fails)
            self.connect(ADMIN, t)                                   # the same ticket again: no
        out = j.getvalue()
        self.assertIn("sitzung_abgewiesen | anker", out)
        self.assertIn("sitzung_abgewiesen | ticket", out)
        t = self.ticket(gid)
        for v in fernzugang.TICKETS.values():
            v["until"] -= fernzugang.TICKET_S + 1
        with journal() as j:
            self.connect(ADMIN, t)                                   # too late
        self.assertIn("sitzung_abgewiesen | ticket", j.getvalue())
        with journal() as j:
            self.connect(TestClient(panel.app), "x" * 43)            # no admin login
        self.assertIn("sitzung_abgewiesen | kein Admin", j.getvalue())

    def test_at_most_n_sessions(self):
        gid = self.pair()["id"]
        self.online(gid)
        helpers.set_config(fernzugang=True, fernzugang_sitzungen=1)
        fernzugang.SITZUNG["x"] = types.SimpleNamespace(gid=gid, seit=0)
        r = ADMIN.post("/api/admin/fernzugang/sitzung", json={"geraet": gid}, headers=CODE)
        self.assertEqual(r.status_code, 429)

    def test_notaus_closes_everything_and_lets_nothing_in(self):
        gid = self.pair()["id"]
        self.online(gid)
        ended = []

        class S:
            gid = "g"

            async def end(self, why):
                ended.append(why)
        t = self.ticket(gid)
        fernzugang.SITZUNG["s1"] = S()
        old, _ = notaus.trigger(1, "test", "", "panel")
        asyncio.run(notaus.after_change(old, 1, "test", "panel"))
        self.assertEqual(ended, ["notaus"])
        self.assertEqual(fernzugang.TICKETS, {})                     # open tickets are gone
        self.assertEqual(ADMIN.get("/api/admin/fernzugang").status_code, 503)
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/sitzung", json={"geraet": gid}, headers=CODE).status_code, 503)
        with journal() as j:
            self.connect(ADMIN, t)
            with self.assertRaises(WebSocketDisconnect):
                with TestClient(panel.app).websocket_connect("/api/fernzugang/anker", headers={"authorization": "Bearer fz_x"}) as ws:
                    ws.receive_text()
        self.assertIn("sitzung_abgewiesen | notaus", j.getvalue())
        self.assertIn("anker_abgewiesen | notaus", j.getvalue())


class Anchor(Base):
    def test_unknown_key_and_message_cap(self):
        with journal() as j:
            with self.assertRaises(WebSocketDisconnect):
                with TestClient(panel.app).websocket_connect("/api/fernzugang/anker", headers={"authorization": "Bearer fz_" + "a" * 40}) as ws:
                    ws.receive_text()
        self.assertIn("fernzugang: anker_abgewiesen | schluessel", j.getvalue())
        key = self.pair()["key"]
        with journal() as j:
            with TestClient(panel.app).websocket_connect("/api/fernzugang/anker", headers={"authorization": "Bearer " + key}) as ws:
                ws.send_text(json.dumps({"typ": "hallo", "os": "Debian 13", "version": "1.0.0"}))
                ws.send_bytes(b"\x01" + b"x" * (fernzugang.MAX_MSG + 10))     # too big: the panel closes
                with self.assertRaises(WebSocketDisconnect):
                    ws.receive_text()
        out = j.getvalue()
        self.assertIn("fernzugang: anker_auf | ok | 1", out)
        self.assertIn("fernzugang: anker_zu | zu gross", out)
        self.assertIn("fernzugang: anker_zu | getrennt | 0", out)

    def test_a_removed_system_gets_only_abbauen(self):
        d = self.pair()
        with journal() as j:
            r = ADMIN.delete(f"/api/admin/fernzugang/geraete/{d['id']}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["stand"], "abbau")
        self.assertIn("fernzugang: abbauen | offline", j.getvalue())
        x = fernzugang._read()["geraete"][d["id"]]
        self.assertFalse({"pi_key", "pi_pub", "hostkey"} & set(x))   # the Pi's key and the pin are gone at once
        self.assertEqual(fernzugang.counts()["abbau"], 1)
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/sitzung", json={"geraet": d["id"]}, headers=CODE).status_code, 404)
        with journal() as j:
            with TestClient(panel.app).websocket_connect("/api/fernzugang/anker", headers={"authorization": "Bearer " + d["key"]}) as ws:
                self.assertEqual(json.loads(ws.receive_text()), {"typ": "abbauen"})
                ws.send_text(json.dumps({"typ": "abbau_laeuft"}))
                with self.assertRaises(WebSocketDisconnect):
                    ws.receive_text()                                    # nothing else, then closed
        self.assertIn("fernzugang: abbauen | beim kontakt", j.getvalue())
        self.assertIn("fernzugang: abbauen | laeuft", j.getvalue())
        self.assertNotIn(d["id"], fernzugang.ANKER)
        # the anchor reports that it removed itself: forgotten here too
        r = TestClient(panel.app).post("/api/fernzugang/anker/abgebaut", json={}, headers={"authorization": "Bearer " + d["key"]})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(d["id"], fernzugang._read()["geraete"])
        self.assertEqual(TestClient(panel.app).post("/api/fernzugang/anker/abgebaut", json={},
                                                    headers={"authorization": "Bearer " + d["key"]}).status_code, 403)

    def test_allow_and_cut(self):
        d = self.pair()
        self.assertEqual(ADMIN.put(f"/api/admin/fernzugang/geraete/{d['id']}", json={"erlaubt": False}).json(), {"erlaubt": False})
        with journal() as j:
            with self.assertRaises(WebSocketDisconnect):
                with TestClient(panel.app).websocket_connect("/api/fernzugang/anker", headers={"authorization": "Bearer " + d["key"]}) as ws:
                    ws.receive_text()
        self.assertIn("anker_abgewiesen | nicht erlaubt", j.getvalue())
        self.assertEqual(fernzugang.probes(), {})
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/alle-trennen").json(), {"n": 0})

    def test_host_key_changed_is_no_connection_and_a_warning(self):
        d = self.pair()
        with journal() as j, unittest.mock.patch.object(dienstwacht, "warn") as warned:
            fernzugang.hostkey_wrong(d["id"])
        self.assertIn("fernzugang: hostkey_falsch | keine Verbindung | 1", j.getvalue())
        warned.assert_called_once_with("fernzugang", "Host-Schlüssel geändert", True)
        self.assertFalse(fernzugang.anker_ok(d["id"]))
        self.assertEqual(fernzugang.counts()["hostkey"], 1)
        import wachposten
        self.assertEqual(wachposten.RULE_OF["fernzugang_hostkey"], "schutz")
        self.assertEqual(wachposten.RULE_OF["fernzugang_paired"], "zugang")
        fernzugang.ANKER[d["id"]] = types.SimpleNamespace(seit=0)
        r = ADMIN.post("/api/admin/fernzugang/sitzung", json={"geraet": d["id"]}, headers=CODE)
        self.assertEqual(r.status_code, 409)

    def test_offline_warning_after_its_minutes(self):
        d = self.pair()
        now = fernzugang._read()["geraete"][d["id"]]["seit"]
        helpers.set_config(fernzugang=True, fernzugang_offline_min=30)
        self.assertTrue(fernzugang.anker_ok(d["id"], now=now + 29 * 60))
        self.assertFalse(fernzugang.anker_ok(d["id"], now=now + 31 * 60))
        self.assertIn(d["id"], dienstwacht.active()["fernzugang"])
        self.assertEqual(dienstwacht.SVC["fernzugang"][4], "fernzugang")


class Program(unittest.TestCase):
    """The anchor program itself (no root needed)."""

    def test_code_never_an_argument_and_only_the_own_sshd(self):
        p = program()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            p.main(["einrichten", "https://spark.example.org", "ABCD-EFGH-JKLM"])   # no place for a code
        with open(fernzugang.PROGRAM) as f:
            src = f.read()
        self.assertIn("getpass.getpass(", src)
        self.assertNotIn("environ", src)
        self.assertEqual(p.SSHD, ("127.0.0.1", 22))
        self.assertEqual(p.key_line("ssh-ed25519 AAAA c"), 'from="127.0.0.1,::1",restrict,pty ssh-ed25519 AAAA c')
        for rule in ("User=spark-anker", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes",
                     "CapabilityBoundingSet=\n", "MemoryDenyWriteExecute=yes", "RestrictAddressFamilies=AF_INET AF_INET6"):
            self.assertIn(rule, p.UNIT_RUN)
        self.assertRaises(p.Fehler, p.base_url, "http://spark.example.org")
        self.assertEqual(p.base_url("https://spark.example.org:443/"), "https://spark.example.org")

    def test_entfernen_removes_every_path_it_made(self):
        p = program()
        root = tempfile.mkdtemp(prefix="anker-")
        home = os.path.join(root, "home", "spark")
        files = {p.here(root, x) for x in (*p.UNITS, p.BIN)}
        for path in p.remove_paths(root):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if path in files:
                with open(path, "w") as f:
                    f.write("x")
            else:
                os.makedirs(path, exist_ok=True)
        with open(os.path.join(root, p.CONF.lstrip("/")), "w") as f:
            json.dump({"url": "https://x", "key": "fz_k", "user_neu": True}, f)
        os.makedirs(os.path.join(home, ".ssh"))
        ak = os.path.join(home, ".ssh", "authorized_keys")
        with open(ak, "w") as f:
            f.write("ssh-ed25519 AAAAown me@laptop\n" + p.key_line("ssh-ed25519 AAAApi spark-fernzugang-g_0123456789ab") + "\n")
        ran = []
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(p.cmd_remove(None, root=root, run=lambda c: ran.append(c) or 0, tell=False, home=home), 0)
        self.assertEqual([x for x in p.remove_paths(root) if os.path.lexists(x)], [])
        with open(ak) as f:
            self.assertEqual(f.read(), "ssh-ed25519 AAAAown me@laptop\n")   # someone else's line stays
        self.assertIn(["systemctl", "disable", "--now", "spark-anker.service", "spark-anker-abbau.path"], ran)
        self.assertIn(["userdel", "--remove", "spark"], ran)                # made by the anchor: gone with its home
        self.assertIn(["userdel", "spark-anker"], ran)
        # a user spark that was there before stays; only the panel's line goes (the file with it when empty)
        os.makedirs(os.path.join(root, p.ETC.lstrip("/")))
        with open(os.path.join(root, p.CONF.lstrip("/")), "w") as f:
            json.dump({"url": "https://x", "key": "fz_k", "user_neu": False}, f)
        with open(ak, "w") as f:
            f.write(p.key_line("ssh-ed25519 AAAApi spark-fernzugang-g_0123456789ab") + "\n")
        ran.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            p.cmd_remove(None, root=root, run=lambda c: ran.append(c) or 0, tell=False, home=home)
        self.assertNotIn(["userdel", "--remove", "spark"], ran)
        self.assertFalse(os.path.exists(ak))


class Pieces(Base):
    def test_xterm_pinned_and_served_from_the_panel(self):
        for name, want in fernzugang.XTERM.items():
            with open(os.path.join(fernzugang.XTERM_DIR, name), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), want, name)
        r = TestClient(panel.app).get("/static/xterm/xterm.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(hashlib.sha256(r.content).hexdigest(), fernzugang.XTERM["xterm.js"])
        self.assertEqual(TestClient(panel.app).get("/static/xterm/other.js").status_code, 404)
        with open(os.path.join(fernzugang.XTERM_DIR, "LICENSE")) as f:
            self.assertIn("MIT", f.read())
        with open(os.path.join(helpers.APP, "panel", "static", "js", "fernzugang.js")) as f:
            js = f.read()
        self.assertIn("/static/xterm/xterm.js", js)
        self.assertNotRegex(js, r"https?://")                # nothing from a CDN

    def test_chips_never_press_enter_and_no_model_sees_the_shell(self):
        for c in fernzugang.CHIPS:
            self.assertNotRegex(c, r"[\r\n]")
            self.assertNotRegex(c, r"\b(rm|sudo|reboot|shutdown|dd|mkfs|kill)\b")   # they only read
        import werkzeuge
        self.assertFalse([n for n in getattr(werkzeuge, "NAMES", {}) if "fern" in n])
        panel_dir = os.path.join(helpers.APP, "panel")
        for name in ("chat.py", "chat_turn.py", "agent.py", "werkzeuge.py", "mcpserver.py", "llm.py", "hilfe.py"):   # the model's ways
            path = os.path.join(panel_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    self.assertNotRegex(f.read(), r"\bimport fernzugang\b|from fernzugang import", name)
        with open(os.path.join(helpers.APP, "panel", "static", "js", "fernzugang.js")) as f:
            js = f.read()
        self.assertIn("term.paste(", js)            # a chip goes into the line
        self.assertNotRegex(js, r"paste\([^)]*\\r")  # never with Enter

    def test_logs_fixed_words_and_live_counts_only(self):
        with open(os.path.join(helpers.APP, "panel", "fernzugang.py"), encoding="utf-8") as f:
            src = f.read()
        words = set(re.findall(r'(?<![.\w])log\("([a-z_]+)"', src))
        self.assertTrue(words and words <= set(fernzugang.WORDS), words - set(fernzugang.WORDS))
        self.assertNotRegex(src, r"(?<![.\w])log\(f")      # never a made-up text
        import logfilter
        self.assertTrue(any(k == "fernzugang" and re.match(rx, "fernzugang: koppeln | ok | 1") for k, rx in logfilter.AREAS))
        self.pair("geheimer-server")
        d = fernzugang.for_live()
        self.assertEqual(set(d), {"on", "gekoppelt", "online", "sitzungen", "abbau", "hostkey"})
        self.assertTrue(all(isinstance(v, (bool, int)) for v in d.values()))
        sub = fernzugang.live_sub(d)
        self.assertEqual(sub, "1 gekoppelt · 0 online · 0 Sitzungen")
        self.assertIn("fernzugang", live.TARGETS)
        helpers.set_logs(live=True) if hasattr(helpers, "set_logs") else None
        snap = live.snapshot()
        row = next((x for x in snap["targets"] if x["id"] == "fernzugang"), None)
        self.assertIsNotNone(row)
        self.assertNotIn("geheimer", json.dumps(snap))

    def test_counts_reach_overview_control_centre_oled_and_app(self):
        """Live, Überblick, the Steuerzentrale on the HDMI screen, the OLED page and the iPhone app show the same
        numbers, never a name (standing rule: a change to Live and Monitoring reaches all of them in one commit)."""
        self.pair("geheimer-server")
        st = ADMIN.get("/api/status").json()["fernzugang"]
        self.assertEqual(st, {"on": True, "gekoppelt": 1, "online": 0, "sitzungen": 0, "abbau": 0, "hostkey": 0})
        import steuerzentrale as sz
        from tests.test_steuerzentrale import beispiel
        d = beispiel()
        d["live"]["targets"] = [{"id": "fernzugang", "name": "Fernzugang", "sub": fernzugang.live_sub(st), "zone": "net"}]
        self.assertIn("Fernzugang", sz.bild(d, 240, 67).text())
        import gehaeuse
        lines = gehaeuse.zeilen("sicherheit", time.time())
        self.assertIn("Fern 0/1 Sitz 0", lines)
        self.assertTrue(all(len(x) <= 21 for x in lines))
        swift = os.path.join(helpers.APP, "..", "ios", "Spark", "AdminViews.swift")
        if os.path.exists(swift):      # a copy with only app/ has no app sources; the rest above still runs there
            with open(swift, encoding="utf-8") as f:
                self.assertIn('d["fernzugang"]', f.read())
        with open(os.path.join(helpers.APP, "panel", "static", "js", "admin.js"), encoding="utf-8") as f:
            self.assertIn("zFern(s.fernzugang", f.read())


# ---------------------------------------------------------------- end to end: anchor program, panel, SSH server
class _Server:
    """A small SSH server with one fixed host key: lets in the user spark with the Pi's key, gives a shell that
    greets, echoes what comes and tells the terminal size."""

    def __init__(self, allowed):
        import paramiko
        self.paramiko, self.allowed = paramiko, allowed
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.sizes = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        paramiko = self.paramiko
        outer = self

        class Iface(paramiko.ServerInterface):
            def check_auth_publickey(self, user, key):
                ok = user == "spark" and key.get_base64() == outer.allowed
                return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

            def get_allowed_auths(self, user):
                return "publickey"

            def check_channel_request(self, kind, cid):
                return paramiko.OPEN_SUCCEEDED

            def check_channel_pty_request(self, ch, term, w, h, pw, ph, modes):
                outer.sizes.append((w, h))
                return True

            def check_channel_shell_request(self, ch):
                return True

            def check_channel_window_change_request(self, ch, w, h, pw, ph):
                outer.sizes.append((w, h))
                return True
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            t = paramiko.Transport(conn)
            t.add_server_key(HOST)
            try:
                t.start_server(server=Iface())
            except Exception:
                continue
            ch = t.accept(60)   # generous: a busy test machine is slow, the test waits for the shell anyway
            if ch is None:
                continue

            def shell(ch=ch):
                ch.sendall(b"hallo vom server\r\n")
                while True:
                    data = ch.recv(1024)
                    if not data:
                        return
                    ch.sendall(b"echo:" + data)
            threading.Thread(target=shell, daemon=True).start()


def _tls_files(folder):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import datetime
    k = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "localhost")])
    start = datetime.datetime(2026, 1, 1)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
            .serial_number(1).not_valid_before(start).not_valid_after(start + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False).sign(k, hashes.SHA256()))
    cf, kf = os.path.join(folder, "c.pem"), os.path.join(folder, "k.pem")
    with open(cf, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(kf, "wb") as f:
        f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cf, kf, hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


class EndToEnd(Base):
    """The anchor program (its own WebSocket client, TLS pinned) → the panel's two sockets on one uvicorn → paramiko
    over the pipe → the SSH server; the browser side with the websockets library like a page would."""

    def setUp(self):
        super().setUp()
        try:
            import paramiko  # noqa: F401
            import uvicorn
            import websockets.sync.client  # noqa: F401
        except ImportError as e:   # the panel's lock has all three; a copy without them cannot run this part
            self.fail(f"missing {e.name}")
        from fastapi import FastAPI
        only = FastAPI()
        only.include_router(fernzugang.router)
        self.tmp = tempfile.mkdtemp(prefix="fz-tls-")
        cf, kf, self.fp = _tls_files(self.tmp)
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error",
                                              ssl_certfile=cf, ssl_keyfile=kf, timeout_graceful_shutdown=2))
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.th = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        for _ in range(400):
            if server.started:
                break
            time.sleep(0.05)
        self.base = f"https://localhost:{self.port}"
        # the browser side: the login check and its hash are tested above (Ticket); here the whole way through
        self.patches = [unittest.mock.patch.object(fernzugang, "is_admin_browser", lambda c: True),
                        unittest.mock.patch.object(fernzugang, "_login", lambda c: "L")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.server.should_exit = True
        self.th.join(10)
        super().tearDown()

    def anchor(self, key, sshd_port):
        p = program()
        p.SSHD = ("127.0.0.1", sshd_port)
        ws = p.WS.open(self.base, self.fp, "/api/fernzugang/anker", key)
        run = p.Lauf(ws)
        th = threading.Thread(target=run.run, daemon=True)
        th.start()
        for _ in range(200):
            if fernzugang.ANKER:
                break
            time.sleep(0.05)
        return ws, th

    def browser(self, gid, cols=100, rows=30):
        import websockets.sync.client as wsc
        t = secrets_ticket(gid, cols, rows)
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        return wsc.connect(f"wss://localhost:{self.port}/api/fernzugang/terminal?t={t}", ssl=ctx,
                           additional_headers={"Origin": self.base}, max_size=2 ** 20, open_timeout=10)

    def read_until(self, conn, want, limit=200):
        got, states = b"", []
        for _ in range(limit):
            m = conn.recv(timeout=30)
            if isinstance(m, bytes):
                got += m
                if want in got:
                    return got, states
            else:
                states.append(json.loads(m))
                if states[-1].get("typ") in ("fehler", "zu"):
                    return got, states
        return got, states

    def test_a_whole_session_through_the_anchor(self):
        d = self.pair(hostkey=HOST_PUB)
        pub = d["pi_key"].split()[1]
        sshd = _Server(pub)
        ws, _ = self.anchor(d["key"], sshd.port)
        self.assertIn(d["id"], fernzugang.ANKER)
        with journal() as j:
            conn = self.browser(d["id"], 100, 30)
            got, states = self.read_until(conn, b"hallo vom server")
            self.assertIn(b"hallo vom server", got, states)
            self.assertEqual(states[-1]["typ"], "stand")
            self.assertEqual(states[-1]["fp"], fernzugang.fingerprint(HOST_PUB))
            self.assertEqual(sshd.sizes[0], (100, 30))
            conn.send(b"uptime")
            got, _ = self.read_until(conn, b"echo:uptime")
            self.assertIn(b"echo:uptime", got)
            conn.send(json.dumps({"typ": "groesse", "cols": 120, "rows": 40}))
            for _ in range(100):
                if (120, 40) in sshd.sizes:
                    break
                time.sleep(0.05)
            self.assertIn((120, 40), sshd.sizes)
            self.assertEqual(fernzugang.counts()["sitzungen"], 1)
            conn.send(b"x" * (fernzugang.MAX_MSG + 1))          # too big: the session ends
            got, states = self.read_until(conn, b"\x00never")
            self.assertEqual(states[-1], {"typ": "zu", "grund": "zu_gross"})
            conn.close()
            for _ in range(100):
                if not fernzugang.SITZUNG:
                    break
                time.sleep(0.05)
        out = j.getvalue()
        self.assertIn("fernzugang: sitzung_auf | admin | 1", out)
        self.assertIn("fernzugang: sitzung_zu | zu_gross | 0", out)
        self.assertNotIn("uptime", out)          # never a keystroke or output in the journal
        self.assertNotIn("hallo vom server", out)
        self.assertEqual(fernzugang.SITZUNG, {})
        ws.sock.shutdown(socket.SHUT_RDWR)   # the anchor's loop ends by itself (one thread owns its TLS socket)

    def test_a_changed_host_key_is_no_connection(self):
        _, other = host_key()
        d = self.pair(hostkey=other)               # pinned at pairing: another key than the server shows now
        sshd = _Server(d["pi_key"].split()[1])
        ws, _ = self.anchor(d["key"], sshd.port)
        with journal() as j, unittest.mock.patch.object(dienstwacht, "warn"):
            conn = self.browser(d["id"])
            got, states = self.read_until(conn, b"hallo vom server")
        self.assertNotIn(b"hallo vom server", got)
        self.assertIn({"typ": "fehler", "grund": "hostkey"}, states)
        self.assertIn("fernzugang: hostkey_falsch | keine Verbindung", j.getvalue())
        self.assertTrue(fernzugang._read()["geraete"][d["id"]]["hostkey_falsch"])
        conn.close()
        ws.sock.shutdown(socket.SHUT_RDWR)   # the anchor's loop ends by itself (one thread owns its TLS socket)

    def test_a_pinned_anchor_refuses_another_certificate(self):
        p = program()
        with self.assertRaises(p.Fehler):
            p.tls_connect(self.base, "00" * 32)


def secrets_ticket(gid, cols, rows):
    """A ticket as POST /api/admin/fernzugang/sitzung makes it (the HTTP door is tested in Ticket)."""
    import secrets
    t = secrets.token_urlsafe(32)
    fernzugang.TICKETS[hashlib.sha256(t.encode()).hexdigest()] = {"gid": gid, "login": "L", "until": time.time() + 30,
                                                                   "cols": cols, "rows": rows, "who": "admin", "uid": None}
    return t


if __name__ == "__main__":
    unittest.main()
