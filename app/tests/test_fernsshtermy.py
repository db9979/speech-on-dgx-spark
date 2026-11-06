"""sshTermy als Jump-Host (fernsshtermy.py, anker `schluessel`; plan sshtermy-vermittler.md, Dominik 2026-11-06): one
self-test per rule. Off by default under the Fernzugang and 503 while off; pairing only by an admin in the browser on
the unlocked page with a fresh code, the code once, at most 10 attempts per address in 10 minutes, at most 5 keys;
the key reaches only its four ways and only as Bearer, a wrong key is 401, a key of another kind never counts; locked
until a fresh code of the key's admin unlocks this one key; the channel's statuses (401/403, 404, 409, 423, 429, 503,
504) before the WebSocket opens; Trennen, Entfernen (also elsewhere) and the Notaus end the channels; the bytes go
through for real (the anchor program over TLS, a fake sshd); the anchor takes only strict public keys, writes exactly
its line without following a link, and „Entfernen“ takes them away; logs carry no key, code or name. No test depends
on the time of day."""
import asyncio
import base64
import contextlib
import io
import json
import os
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
import types
import unittest
import unittest.mock

from tests import helpers
from tests.test_fernzugang import ADMIN, CODE, OUT, Base, _tls_files, fake_session, journal, program  # noqa: F401

import fernsshtermy  # noqa: E402
import fernzugang  # noqa: E402
import guard  # noqa: E402
import mfa  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import stufen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.testclient import WebSocketDenialResponse  # noqa: E402

V1 = fernsshtermy.V1


def openssh(kind):
    """A public key line as ssh-keygen writes it (cryptography): ed25519, ecdsa256, rsa2048, rsa3072."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
    k = {"ed25519": lambda: ed25519.Ed25519PrivateKey.generate(), "ecdsa": lambda: ec.generate_private_key(ec.SECP256R1()),
         "rsa2048": lambda: rsa.generate_private_key(65537, 2048), "rsa3072": lambda: rsa.generate_private_key(65537, 3072)}[kind]()
    return k.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


class StBase(Base):
    """An admin profile (role Admin, second step) logged in in its browser, the Fernzugang unlocked there."""

    def setUp(self):
        super().setUp()
        import coadmin
        self.coadmin = coadmin
        self.mfa_on = {mfa.ADMIN}
        self.real_mark = mfa.mark
        mfa.enabled = lambda who: who in self.mfa_on
        mfa.verify = lambda who, code: who in self.mfa_on and code == "123456"
        mfa.mark = lambda who: f"m-{who}" if who in self.mfa_on else ""
        helpers.set_config(fernzugang=True, fernzugang_sshtermy=True, public=False, deny={})
        r = ADMIN.post("/api/admin/profiles", json={"name": "StermAda", "pin": "1234"})
        self.assertIn(r.status_code, (200, 409), r.text)
        self.uid = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == "StermAda")
        self.mfa_on.add(self.uid)
        coadmin.set_role(self.uid, "admin")
        self.web = TestClient(panel.app)
        self.assertEqual(self.web.post("/api/profile/login", json={"name": "StermAda", "pin": "1234", "code": "123456"}).status_code, 200)
        self.unlock(self.web)
        fernsshtermy.CODES.pending.clear()
        fernsshtermy._versuche.clear()
        for k in [k for k in guard._rate if str(k[0]).startswith("fernzugang")]:
            guard._rate.pop(k, None)

    def tearDown(self):
        for x in fernsshtermy.geraete():
            profiles.delete_device(x["id"])
        mfa.mark = self.real_mark
        with contextlib.suppress(OSError):
            os.remove(self.coadmin.FILE)
        helpers.set_config(fernzugang_sshtermy=False)
        super().tearDown()

    def line(self, client=None, status=200):
        for k in [k for k in guard._rate if k[0] == "fernzugang_code"]:      # several pairings in one test
            guard._rate.pop(k, None)
        r = (client or self.web).post("/api/admin/fernzugang/sshtermy/koppeln", json={"origin": OUT}, headers=CODE)
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def key(self, name="laptop"):
        setup = self.line()["setup"]
        code = setup.split("#termy=")[1].split("&")[0]
        r = TestClient(panel.app).post(V1 + "/koppeln", json={"code": code, "name": name})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["key"]

    def st(self, key):
        c = TestClient(panel.app)
        c.headers["authorization"] = "Bearer " + key
        return c

    def did(self, key):
        return profiles.device_by_token(key)["id"]

    def open_up(self, c):
        r = c.post(V1 + "/entsperren", json={"code": "123456"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def denied(self, c, path):
        with self.assertRaises(WebSocketDenialResponse) as e:
            with c.websocket_connect(path):
                pass
        return e.exception.status_code


class Off(StBase):
    def test_off_by_default_under_the_fernzugang_and_503_while_off(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["fernzugang_sshtermy"], False)
        import features
        f = next(x for x in features.FEATURES if x.key == "fernsshtermy")
        self.assertEqual((f.parent, f.admin), ("fernzugang", ("fernzugang_sshtermy",)))
        self.assertIn("fernsshtermy", features.SPARK_ONLY)
        self.assertNotIn("chat.fernzugang_sshtermy", features.DEFAULT_ON)
        key = self.key()
        c = self.st(key)
        for off in ({"fernzugang_sshtermy": False}, {"fernzugang": False}):
            helpers.set_config(**off)
            self.assertFalse(fernsshtermy.on())
            with journal() as j:
                self.assertEqual(c.get(V1 + "/systeme").status_code, 503)
                self.assertEqual(c.post(V1 + "/entsperren", json={"code": "123456"}).status_code, 503)
                self.assertEqual(TestClient(panel.app).post(V1 + "/koppeln", json={"code": "x" * 24}).status_code, 503)
                self.assertEqual(self.denied(c, V1 + "/kanal?system=g_000000000000"), 503)
            self.assertIn("fernzugang: sshtermy_kanal | aus | 0", j.getvalue())
            self.assertIn(self.web.post("/api/admin/fernzugang/sshtermy/koppeln", json={"origin": OUT}, headers=CODE).status_code, (404, 503))
            helpers.set_config(fernzugang=True, fernzugang_sshtermy=True)
        self.assertIsNotNone(profiles.device_by_token(key))          # off keeps the pairing (test_rechte_sofort)
        helpers.set_config(fernzugang_sshtermy=False)
        self.assertIsNone(ADMIN.get("/api/admin/fernzugang").json()["sshtermy"])      # the page shows no box


class Pairing(StBase):
    def test_only_an_admin_in_the_browser_on_the_unlocked_page_with_a_fresh_code(self):
        url = "/api/admin/fernzugang/sshtermy/koppeln"
        self.assertIn(TestClient(panel.app).post(url, json={"origin": OUT}).status_code, (401, 403))
        self.assertEqual(self.web.post(url, json={"origin": OUT}).status_code, 428)          # a fresh code every time
        fernzugang.ENTSPERRT.clear()
        self.assertEqual(self.web.post(url, json={"origin": OUT}, headers=CODE).status_code, 423)
        self.unlock(self.web)
        self.assertEqual(self.web.post(url, json={"origin": "http://spark.example.org"}, headers=CODE).status_code, 409)
        with journal() as j:
            d = self.line()
        self.assertRegex(d["setup"], r"^https://spark\.example\.org/api/fernzugang/sshtermy#termy=[A-Za-z0-9_\-]{20,40}$")
        self.assertEqual((d["gilt_s"], d["pinned"]), (600, False))
        code = d["setup"].split("#termy=")[1]
        self.assertNotIn(code, j.getvalue())
        self.assertNotIn(code, json.dumps(list(fernsshtermy.CODES.pending)))           # only its hash is kept
        self.assertEqual(stufen.LIST[("POST", url)][0], stufen.PROTECT)
        # the iPhone app never pairs (E3a): the door wants the browser
        with unittest.mock.patch.object(fernzugang, "is_admin_browser", lambda c: False), \
                unittest.mock.patch.object(fernzugang, "is_admin_app", lambda c: True):
            self.assertEqual(self.web.post(url, json={"origin": OUT}, headers=CODE).status_code, 403)

    def test_the_code_once_its_own_key_of_the_admin_profile_and_nothing_in_the_log(self):
        code = self.line()["setup"].split("#termy=")[1]
        prog = TestClient(panel.app)
        with journal() as j:
            r = prog.post(V1 + "/koppeln", json={"code": code, "name": "laptop"})
            self.assertEqual(r.status_code, 200, r.text)
            again = prog.post(V1 + "/koppeln", json={"code": code, "name": "laptop"})
        self.assertEqual(again.status_code, 403)                                             # once
        d = r.json()
        self.assertEqual((d["art"], d["name"]), ("spark", "Spark"))
        dev = profiles.device_by_token(d["key"])
        self.assertEqual((dev["scope"], dev["user"], dev["name"]), ("sshtermy", self.uid, "sshTermy · laptop"))
        out = j.getvalue()
        self.assertIn("fernzugang: sshtermy_koppeln | ok | 1", out)
        self.assertIn("fernzugang: sshtermy_koppeln | falsch | 0", out)
        for secret in (code, d["key"], "laptop", "StermAda"):
            self.assertNotIn(secret, out)

    def test_at_most_five_keys(self):
        for i in range(fernsshtermy.MAX_GERAETE - 1):
            self.key(f"pc{i}")
        spare = self.line()["setup"].split("#termy=")[1]      # made while one place was free
        self.key("pc-last")
        self.assertEqual(fernsshtermy.anzahl(), fernsshtermy.MAX_GERAETE)
        self.line(status=409)
        r = TestClient(panel.app).post(V1 + "/koppeln", json={"code": spare, "name": "zu-viel"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(fernsshtermy.anzahl(), fernsshtermy.MAX_GERAETE)

    def test_at_most_ten_attempts_per_address_in_ten_minutes(self):
        req = types.SimpleNamespace(client=types.SimpleNamespace(host="203.0.113.9"), headers={})
        t0 = 1_000_000.0
        for i in range(fernsshtermy.VERSUCHE):
            fernsshtermy._versuch(req, t0 + i)
        with self.assertRaises(Exception) as e:
            fernsshtermy._versuch(req, t0 + 20)
        self.assertEqual(e.exception.status_code, 429)
        other = types.SimpleNamespace(client=types.SimpleNamespace(host="203.0.113.10"), headers={})
        fernsshtermy._versuch(other, t0 + 20)                                   # per address
        fernsshtermy._versuch(req, t0 + fernsshtermy.VERSUCHE_S + 1)            # the window passed
        self.assertEqual((fernsshtermy.VERSUCHE, fernsshtermy.VERSUCHE_S), (10, 600))
        prog = TestClient(panel.app)                                            # through the door: the 11th is 429
        codes = [prog.post(V1 + "/koppeln", json={"code": "y" * 24}).status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)
        self.assertTrue(all(c in (403, 429) for c in codes))

    def test_a_profile_that_is_no_admin_gets_no_key(self):
        code = self.line()["setup"].split("#termy=")[1]
        self.coadmin.set_role(self.uid, "manager")
        r = TestClient(panel.app).post(V1 + "/koppeln", json={"code": code, "name": "laptop"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(fernsshtermy.anzahl(), 0)


class Key(StBase):
    def test_the_key_reaches_only_its_four_ways_and_only_as_bearer(self):
        key = self.key()
        self.assertEqual(set(profiles.SSHTERMY_PATHS), {r.path for r in fernsshtermy.router.routes if r.path.startswith(V1)})
        dev = TestClient(panel.app)
        dev.headers[profiles.DEVICE_HEADER] = key                    # as a device key: no profile anywhere
        for path in ("/api/profile/today", "/api/profile/convos", "/api/admin/fernzugang", "/api/tui/hello"):
            self.assertIn(dev.get(path).status_code, (401, 403), path)
        self.assertEqual(dev.get(V1 + "/systeme").status_code, 401)      # and not there either: only Bearer
        bearer = self.st(key)
        self.assertIn(bearer.get("/api/profile/today").status_code, (401, 403))
        self.assertEqual(bearer.get(V1 + "/systeme").status_code, 200)

    def test_a_wrong_key_or_another_kind_of_key_is_401(self):
        with journal() as j:
            self.assertEqual(self.st("sd_" + "a" * 32).get(V1 + "/systeme").status_code, 401)
        self.assertIn("fernzugang: sshtermy_systeme | schluessel | 0", j.getvalue())
        other = profiles.add_device("Terminal · x", self.uid, scope="tui")      # a key of another kind
        self.assertEqual(self.st(other).get(V1 + "/systeme").status_code, 401)
        anchor = self.pair()["key"]                                              # the anchor's own key
        self.assertEqual(self.st(anchor).get(V1 + "/systeme").status_code, 401)
        self.assertEqual(self.denied(self.st("sd_" + "b" * 32), V1 + "/kanal?system=g_000000000000"), 401)
        profiles.delete_device(profiles.device_by_token(other)["id"])

    def test_the_role_gone_is_403(self):
        c = self.st(self.key())
        self.coadmin.set_role(self.uid, "manager")
        self.assertEqual(c.get(V1 + "/systeme").status_code, 403)
        self.coadmin.set_role(self.uid, "admin")
        self.mfa_on.discard(self.uid)
        self.assertEqual(c.get(V1 + "/systeme").status_code, 403)


class Unlock(StBase):
    def test_locked_until_a_fresh_code_unlocks_this_key_only(self):
        g = self.pair("vps-1")
        k1, k2 = self.key("a"), self.key("b")
        c1, c2 = self.st(k1), self.st(k2)
        r = c1.get(V1 + "/systeme").json()
        self.assertEqual(r, {"name": "Spark", "art": "spark", "entsperrt_min": 60, "gesperrt": True, "systeme": []})
        self.assertEqual(self.denied(c1, V1 + f"/kanal?system={g['id']}"), 423)
        with journal() as j:
            self.assertEqual(c1.post(V1 + "/entsperren", json={"code": "000000"}).status_code, 403)
            self.assertEqual(c1.post(V1 + "/entsperren", json={}).status_code, 403)
            bis = self.open_up(c1)["bis"]
        self.assertIn("fernzugang: sshtermy_entsperrt | falsch | 0", j.getvalue())
        self.assertIn("fernzugang: sshtermy_entsperrt | ok | 60", j.getvalue())
        self.assertNotIn("123456", j.getvalue())
        self.assertGreater(bis, time.time() + 3500)
        r = c1.get(V1 + "/systeme").json()
        self.assertFalse(r["gesperrt"])
        self.assertEqual(r["systeme"], [{"id": g["id"], "name": "vps-1", "os": "Debian 13", "online": False,
                                         "hostkey": fernzugang._read()["geraete"][g["id"]]["hostkey"], "ordner": "", "benutzer": "spark"}])
        self.assertTrue(c2.get(V1 + "/systeme").json()["gesperrt"])                 # the other key stays locked
        self.assertIn(fernsshtermy.tor(self.did(k1)), fernzugang.ENTSPERRT)
        self.assertEqual(stufen.LIST[("POST", V1 + "/entsperren")][0], stufen.PROTECT)
        with unittest.mock.patch.object(fernzugang, "_herkunft", lambda c: "internet"):   # another kind of place: locked
            self.assertTrue(c1.get(V1 + "/systeme").json()["gesperrt"])

    def test_the_notaus_locks_and_refuses(self):
        c = self.st(self.key())
        self.open_up(c)
        old, _ = notaus.trigger(1, "test", "", "panel")
        asyncio.run(notaus.after_change(old, 1, "test", "panel"))
        self.assertEqual(fernzugang.ENTSPERRT, {})
        self.assertEqual(c.get(V1 + "/systeme").status_code, 503)


class Channel(StBase):
    def online(self, gid, answer=None):
        """An anchor that is there: it answers „auf“ with answer (None: never, a timeout)."""
        sent = []

        class Ws:
            async def send_text(self, t):
                m = json.loads(t)
                sent.append(m)
                if m.get("typ") == "auf" and answer is not None:
                    a = fernzugang.ANKER[gid]
                    a.wait[m["kanal"]].set_result(answer)

            async def send_bytes(self, b):
                sent.append(b)

            async def close(self, code=1000):
                pass
        fernzugang.ANKER[gid] = fernzugang.Anker(Ws(), gid)
        return sent

    def test_the_statuses_of_the_protocol_before_the_websocket_opens(self):
        g = self.pair("vps-1")["id"]
        c = self.st(self.key())
        self.open_up(c)
        with journal() as j:
            self.assertEqual(self.denied(c, V1 + "/kanal?system=g_ffffffffffff"), 404)
            self.assertEqual(self.denied(c, V1 + "/kanal?system=../x"), 404)
            self.assertEqual(self.denied(c, V1 + f"/kanal?system={g}"), 409)              # offline
            self.online(g)
            fernzugang._update(g, erlaubt=False)
            self.assertEqual(self.denied(c, V1 + f"/kanal?system={g}"), 409)              # not allowed
            fernzugang._update(g, erlaubt=True, hostkey_falsch=True)
            self.assertEqual(self.denied(c, V1 + f"/kanal?system={g}"), 409)              # host key wrong
            fernzugang._update(g, hostkey_falsch=False)
            helpers.set_config(fernzugang_sitzungen=1)
            s = fake_session(g)
            self.assertEqual(self.denied(c, V1 + f"/kanal?system={g}"), 429)              # no place
            fernzugang.SITZUNG.pop(s.id, None)
            with unittest.mock.patch.object(fernzugang, "OPEN_S", 0.2):
                self.assertEqual(self.denied(c, V1 + f"/kanal?system={g}"), 504)          # the anchor opened nothing
            self.online(g, answer=False)
            self.assertEqual(self.denied(c, V1 + f"/kanal?system={g}"), 504)              # no sshd over there
        out = j.getvalue()
        for why in ("unbekannt", "offline", "voll", "anker"):
            self.assertIn(f"fernzugang: sshtermy_kanal | {why} | 0", out)
        self.assertEqual(fernzugang.SITZUNG, {})

    def test_bytes_both_ways_and_trennen_ends_it(self):
        g = self.pair("vps-1")["id"]
        key = self.key()
        c = self.st(key)
        self.open_up(c)
        sent = self.online(g, answer=True)
        with journal() as j:
            with c.websocket_connect(V1 + f"/kanal?system={g}") as ws:
                s = next(iter(fernzugang.SITZUNG.values()))
                self.assertEqual((s.art, s.client, s.geraet), ("sshtermy", "sshtermy", self.did(key)))
                ws.send_bytes(b"SSH-2.0-sshTermy\r\n")
                self.assertTrue(helpers.until(lambda: any(isinstance(x, bytes) for x in sent)))
                self.assertEqual([x for x in sent if isinstance(x, bytes)][0], bytes([s.n]) + b"SSH-2.0-sshTermy\r\n")
                off = ADMIN.get("/api/admin/fernzugang").json()
                self.assertEqual([(x["art"], x["client"]) for x in off["offen"]], [("sshtermy", "sshtermy")])
                self.assertEqual(off["sshtermy"]["geraete"][0]["kanaele"], 1)
                self.assertEqual(fernzugang.counts()["sshtermy"], 1)
                self.assertIn("davon 1 sshTermy", fernzugang.live_sub(fernzugang.for_live()))
                self.assertEqual(fernzugang.for_live()["offen"][0]["art"], "sshTermy")
                ws.send_bytes(b"x" * (fernzugang.MAX_MSG + 1))                          # too big: the channel ends
                self.assertTrue(helpers.until(lambda: not fernzugang.SITZUNG))
                # the session leaves SITZUNG first, its last line and the history follow; wait for them while the
                # test client's loop still runs (leaving the block stops that loop, and the end with it)
                self.assertTrue(helpers.until(lambda: "sshtermy_zu" in j.getvalue()))
                self.assertTrue(helpers.until(lambda: fernzugang.verlauf_read()))
        out = j.getvalue()
        self.assertIn("fernzugang: sshtermy_kanal | ok | 1", out)
        self.assertIn("fernzugang: sshtermy_zu | zu_gross | 0", out)
        self.assertEqual([x["typ"] for x in sent if isinstance(x, dict)], ["auf", "zu"])
        self.assertTrue(helpers.until(lambda: fernzugang.verlauf_read()))
        v = fernzugang.verlauf_read()[0]
        self.assertEqual((v["art"], v["client"]), ("sshtermy", "sshtermy"))
        self.assertNotIn(key, out)

    def test_the_anchors_bytes_wait_for_the_websocket_and_count_as_activity(self):
        async def run():
            a = fernzugang.Anker(types.SimpleNamespace(), "g_000000000001")
            s = fernzugang.Sitzung("g_000000000001", a, 1, None, "sshtermy", None, "sshtermy")
            s.zuletzt = 0
            await s.from_anker(b"SSH-2.0-OpenSSH\r\n")
            self.assertEqual(bytes(s.puffer), b"SSH-2.0-OpenSSH\r\n")       # before accept: kept
            self.assertGreater(s.zuletzt, 0)
            got = []

            async def weiter(b):
                got.append(b)
            s.weiter = weiter
            await s.from_anker(b"more")
            self.assertEqual(got, [b"more"])
            said = []
            s.browser = types.SimpleNamespace(send_text=lambda t: said.append(t))
            await s._say({"typ": "bald", "s": 10})
            self.assertEqual(said, [])                                      # sshTermy hears bytes only
            for x in (s.ours, s.theirs):
                x.close()
        asyncio.run(run())
        import inspect
        src = inspect.getsource(fernsshtermy.kanal)
        self.assertIn("s._idle()", src)                                    # E2a: idle without any byte ends it
        self.assertIn("_wache(s", src)                                     # and the 12 hours
        self.assertEqual(fernsshtermy.MAX_KANAL_S, 12 * 3600)


class Ending(StBase):
    def test_trennen_entfernen_and_the_notaus_end_the_channels(self):
        g = self.pair("vps-1")["id"]
        key = self.key()
        did = self.did(key)
        c = self.st(key)
        self.open_up(c)
        s = fake_session(g, art="sshtermy", geraet=did)
        other = fake_session(g)                                                       # a shell stays
        with journal() as j:
            r = self.web.post(f"/api/admin/fernzugang/sshtermy/{did}/trennen")
        self.assertEqual(r.json(), {"n": 1})
        self.assertEqual(s.grund, "getrennt")
        self.assertIn(other.id, fernzugang.SITZUNG)
        self.assertRegex(j.getvalue(), r"fernzugang: sshtermy_trennen \| (StermAda|Profil \w+) \| 1")
        self.assertEqual(self.web.post("/api/admin/fernzugang/sshtermy/d_ffffffffffff/trennen").status_code, 404)
        s = fake_session(g, art="sshtermy", geraet=did)
        self.assertEqual(self.web.delete(f"/api/admin/fernzugang/sshtermy/{did}").status_code, 428)   # fresh code
        r = self.web.delete(f"/api/admin/fernzugang/sshtermy/{did}", headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(s.grund, "entfernt")
        self.assertIsNone(profiles.device_by_token(key))
        self.assertNotIn(fernsshtermy.tor(did), fernzugang.ENTSPERRT)
        self.assertEqual(c.get(V1 + "/systeme").status_code, 401)                      # the key stops at once
        self.assertEqual(stufen.LIST[("DELETE", "/api/admin/fernzugang/sshtermy/{did}")][0], stufen.PROTECT)
        # the Notaus ends every channel
        k2 = self.key("b")
        s = fake_session(g, art="sshtermy", geraet=self.did(k2))
        old, _ = notaus.trigger(1, "test", "", "panel")
        asyncio.run(notaus.after_change(old, 1, "test", "panel"))
        self.assertEqual(s.grund, "notaus")

    def test_a_key_removed_elsewhere_the_role_gone_or_the_hours_end_an_open_channel(self):
        did = self.did(self.key())

        async def run(change, wache_s=0.01, max_s=3600):
            ended = []
            s = types.SimpleNamespace(ende=asyncio.Event())

            async def end(why):
                ended.append(why)
                s.ende.set()
            s.end = end
            change()
            with unittest.mock.patch.object(fernsshtermy, "WACHE_S", wache_s), \
                    unittest.mock.patch.object(fernsshtermy, "MAX_KANAL_S", max_s):
                await asyncio.wait_for(fernsshtermy._wache(s, did), 10)
            return ended
        self.assertEqual(asyncio.run(run(lambda: None, max_s=0)), ["hoechstdauer"])
        self.assertEqual(asyncio.run(run(lambda: self.coadmin.set_role(self.uid, "manager"))), ["aus"])
        self.coadmin.set_role(self.uid, "admin")
        self.assertEqual(asyncio.run(run(lambda: profiles.delete_device(did))), ["entfernt"])   # Personen und Geräte


class AnchorReport(StBase):
    def row(self, gid):
        return next(x for x in ADMIN.get("/api/admin/fernzugang").json()["geraete"] if x["id"] == gid)

    def test_the_report_is_checked_shown_on_the_card_and_never_a_key(self):
        ok = {"fp": "SHA256:" + "A" * 43, "typ": "ssh-ed25519", "kommentar": "sshtermy@laptop", "weiterleiten": False}
        for bad in ({}, {"schluessel": "x"}, {"schluessel": [dict(ok, fp="AAAA")]}, {"schluessel": [dict(ok, typ="ssh-dss")]},
                    {"schluessel": [dict(ok, kommentar="a b")]}, {"schluessel": [dict(ok, weiterleiten="ja")]},
                    {"schluessel": [ok] * 21}):
            self.assertIsNone(fernsshtermy.clean(bad), bad)
        d = self.pair("vps-1")
        anchor = TestClient(panel.app)
        h = {"Authorization": "Bearer " + d["key"]}
        self.assertEqual(self.row(d["id"])["schluessel"], None)
        self.assertEqual(anchor.post("/api/fernzugang/anker/schluessel", json={"schluessel": [ok]}).status_code, 403)
        with journal() as j:
            self.assertEqual(anchor.post("/api/fernzugang/anker/schluessel", json={"schluessel": [ok]}, headers=h).status_code, 200)
            self.assertEqual(anchor.post("/api/fernzugang/anker/schluessel", json={"schluessel": [dict(ok, typ="x")]}, headers=h).status_code, 400)
        self.assertIn("fernzugang: schluessel | gemeldet | 1", j.getvalue())
        self.assertNotIn("laptop", j.getvalue())
        self.assertEqual(self.row(d["id"])["schluessel"], [ok])
        helpers.set_config(fernzugang_sshtermy=False)
        self.assertNotIn("schluessel", self.row(d["id"]))
        self.assertIsNone(ADMIN.get("/api/admin/fernzugang").json()["sshtermy"])

    def test_logs_fixed_words_only(self):
        with open(os.path.join(helpers.APP, "panel", "fernsshtermy.py"), encoding="utf-8") as f:
            src = f.read()
        words = set(re.findall(r'fernzugang\.log\("([a-z_]+)"', src)) | set(re.findall(r'_nein\("([a-z_]+)"', src))
        self.assertTrue(words and words <= set(fernzugang.WORDS), words - set(fernzugang.WORDS))
        self.assertNotRegex(src, r"fernzugang\.log\(f")
        self.assertNotRegex(src, r"print\(")

    def test_the_apps_show_the_box(self):
        swift = os.path.join(helpers.APP, "..", "ios", "Spark", "AdminViews.swift")
        if os.path.exists(swift):      # a copy with only app/ has no app sources
            with open(swift, encoding="utf-8") as f:
                src = f.read()
            for want in ('fz["sshtermy"]', 'd["sshtermy"]', "api/admin/fernzugang/sshtermy/", "/trennen", '"DELETE"'):
                self.assertIn(want, src)
            self.assertNotIn("api/admin/fernzugang/sshtermy/koppeln", src)     # pairing only in the browser (E3a)
        js = ""
        for name in ("js/fernsshtermy.js", "index.html"):     # its own tab; „Koppeln (Code)“ in the page's head (2026-11-06)
            with open(os.path.join(helpers.APP, "panel", "static", *name.split("/")), encoding="utf-8") as f:
                js += f.read()
        for want in ("Koppeln (Code)", "Kopieren", "Trennen", "Entfernen", "Schlüssel für sshTermy", "schluessel dazu"):
            self.assertIn(want, js)


# ---------------------------------------------------------------- the anchor: `schluessel dazu|weg|liste`
class AnchorKeys(unittest.TestCase):
    def ctx(self, system="Linux"):
        p = program()
        root = tempfile.mkdtemp(prefix="anker-st-")
        self.addCleanup(shutil.rmtree, root, True)
        ctx = p.Ctx(system=system, root=root, run=lambda c: 0)
        ctx.euid = lambda: 0
        ctx.ids = lambda n: (os.getuid(), os.getgid(), "/home/spark") if n == "spark" else None
        ctx.chown = lambda *a: None
        p.write(ctx.path(ctx.s.conf), json.dumps({"url": "https://s.example.org", "fp": "", "id": "g_1", "key": "fz_k"}), 0o640)
        return p, ctx

    def keys(self, p, ctx, was, schluessel=(), weiter=False):
        calls = []
        with unittest.mock.patch.object(p, "http_call", lambda *a, **k: calls.append(a[2:5]) or (200, b"{}")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            rc = p.cmd_keys(types.SimpleNamespace(was=was, schluessel=list(schluessel), weiterleiten=weiter), ctx=ctx)
        return rc, calls, out.getvalue()

    def ak(self, ctx):
        return ctx.path("/home/spark/.ssh/authorized_keys")

    def test_only_strict_public_keys(self):
        p = program()
        ed, ec, r3 = openssh("ed25519"), openssh("ecdsa"), openssh("rsa3072")
        for good in (ed + " sshtermy@laptop", ec, r3 + " me@büro"):
            typ, b64, kom = p.schluessel_pruefen(good)
            self.assertEqual(typ, good.split()[0])
        self.assertEqual(p.schluessel_pruefen(r3 + " me@büro")[2], "me@bro")      # only safe letters in the comment
        r2 = openssh("rsa2048")
        b64 = ed.split()[1]
        for bad in (r2, 'command="sh" ' + ed, "restrict " + ed, ed + "\nssh-ed25519 " + b64, ed + "\r", "ssh-dss " + b64,
                    "sk-ssh-ed25519@openssh.com " + b64, "ssh-rsa " + b64, "ssh-ed25519 " + b64[:-8], "ssh-ed25519 !!!!" + b64,
                    "", "ssh-ed25519"):
            with self.assertRaises(p.Fehler, msg=bad[:40]):
                p.schluessel_pruefen(bad)

    def test_dazu_writes_exactly_its_line_weg_and_liste(self):
        p, ctx = self.ctx()
        os.makedirs(os.path.dirname(self.ak(ctx)))
        with open(self.ak(ctx), "w") as f:
            f.write("ssh-ed25519 AAAAown me@laptop\n" + p.key_line("ssh-ed25519 AAAApi spark-fernzugang-g_0123456789ab") + "\n")
        ed = openssh("ed25519")
        rc, calls, out = self.keys(p, ctx, "dazu", [ed + " sshtermy@laptop"])
        self.assertEqual(rc, 0, out)
        with open(self.ak(ctx)) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[:2], ["ssh-ed25519 AAAAown me@laptop", p.key_line("ssh-ed25519 AAAApi spark-fernzugang-g_0123456789ab")])
        self.assertEqual(lines[2], f'from="127.0.0.1,::1",restrict,pty {ed} sshtermy:sshtermy@laptop')
        self.assertEqual(os.stat(self.ak(ctx)).st_mode & 0o777, 0o600)
        fp = p.schluessel_fp(ed.split()[1])
        self.assertEqual(calls[-1], ("POST", "/api/fernzugang/anker/schluessel",
                                     {"schluessel": [{"fp": fp, "typ": "ssh-ed25519", "kommentar": "sshtermy@laptop", "weiterleiten": False}]}))
        self.assertNotIn(ed.split()[1], json.dumps(calls))                               # never the key to the panel
        rc, calls, out = self.keys(p, ctx, "dazu", [ed + " sshtermy@laptop"], weiter=True)    # again: replaced
        with open(self.ak(ctx)) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[2:], [f'from="127.0.0.1,::1",restrict,pty,port-forwarding {ed} sshtermy:sshtermy@laptop'])
        self.assertTrue(calls[-1][2]["schluessel"][0]["weiterleiten"])
        ec = openssh("ecdsa")
        self.keys(p, ctx, "dazu", [ec])
        rc, calls, out = self.keys(p, ctx, "liste")
        self.assertIn("2 Schlüssel für sshTermy", out)
        self.assertEqual(len(calls[-1][2]["schluessel"]), 2)
        rc, calls, out = self.keys(p, ctx, "weg", [fp])
        self.assertEqual(rc, 0)
        rc, calls, out = self.keys(p, ctx, "weg", [ec])
        with open(self.ak(ctx)) as f:
            self.assertEqual(len(f.read().splitlines()), 2)                               # the others stay
        self.assertEqual(calls[-1][2], {"schluessel": []})
        self.assertEqual(self.keys(p, ctx, "weg", [fp])[0], 1)                            # gone already

    def test_root_only_set_up_first_never_through_a_link_and_not_on_windows(self):
        p, ctx = self.ctx()
        ed = openssh("ed25519")
        ctx.euid = lambda: 1000
        self.assertEqual(self.keys(p, ctx, "dazu", [ed])[0], 1)
        ctx.euid = lambda: 0
        os.makedirs(ctx.path("/home/spark/.ssh"))
        outside = os.path.join(ctx.root, "etc-shadow")
        with open(outside, "w") as f:
            f.write("root:x:1\n")
        os.symlink(outside, self.ak(ctx))                       # spark put a link there
        self.assertEqual(self.keys(p, ctx, "dazu", [ed])[0], 0)
        with open(outside) as f:
            self.assertEqual(f.read(), "root:x:1\n")             # never followed
        self.assertFalse(os.path.islink(self.ak(ctx)))
        with open(self.ak(ctx)) as f:
            self.assertEqual(len(f.read().splitlines()), 1)
        p2, ctx2 = self.ctx()
        os.remove(ctx2.path(ctx2.s.conf))
        self.assertEqual(self.keys(p2, ctx2, "dazu", [ed])[0], 1)   # not set up: nothing
        self.assertIsNotNone(p.not_yet("schluessel", "Windows"))
        self.assertIsNone(p.not_yet("schluessel", "Linux"))
        self.assertEqual(p.VERSION, "1.11.0")

    def test_entfernen_takes_every_sshtermy_line_away(self):
        p, ctx = self.ctx()
        os.makedirs(ctx.path("/home/spark/.ssh"))
        with open(self.ak(ctx), "w") as f:
            f.write("ssh-ed25519 AAAAown me@laptop\n" + p.key_line("ssh-ed25519 AAAApi spark-fernzugang-g_0123456789ab") + "\n")
        self.keys(p, ctx, "dazu", [openssh("ed25519") + " a@b"], weiter=True)
        self.keys(p, ctx, "dazu", [openssh("ed25519")])
        self.assertTrue(p.strip_key(self.ak(ctx)))
        with open(self.ak(ctx)) as f:
            self.assertEqual(f.read(), "ssh-ed25519 AAAAown me@laptop\n")
        import inspect
        self.assertIn("strip_key(", inspect.getsource(p.cmd_remove))


# ---------------------------------------------------------------- the whole way: anchor program, panel, a fake sshd
class _Sshd:
    """Not SSH: greets like a server and sends back what comes, upper case (the panel never reads it)."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.one, args=(c,), daemon=True).start()

    def one(self, c):
        with c:
            c.sendall(b"SSH-2.0-OpenSSH_Test\r\n")
            while True:
                data = c.recv(4096)
                if not data:
                    return
                c.sendall(data.upper())


class EndToEnd(StBase):
    def setUp(self):
        super().setUp()
        import uvicorn
        from fastapi import FastAPI
        only = FastAPI()
        only.include_router(fernzugang.router)
        only.include_router(fernsshtermy.router)
        self.tmp = tempfile.mkdtemp(prefix="st-tls-")
        cf, kf, self.fp = _tls_files(self.tmp)
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error", ssl_certfile=cf,
                                               ssl_keyfile=kf, timeout_graceful_shutdown=2, ssl_context_factory=panel.tls_context))
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.th = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        self.assertTrue(helpers.until(lambda: server.started))
        self.base = f"https://localhost:{self.port}"
        self.patch = unittest.mock.patch.object(fernzugang, "_herkunft", lambda c: "zuhause")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.server.should_exit = True
        self.th.join(10)
        shutil.rmtree(self.tmp, True)
        super().tearDown()

    def test_the_bytes_go_through_the_real_anchor_untouched(self):
        import websockets.sync.client as wsc
        d = self.pair("vps-1")
        sshd = _Sshd()
        p = program()
        p.SSHD = ("127.0.0.1", sshd.port)
        aws = p.WS.open(self.base, self.fp, "/api/fernzugang/anker", d["key"])
        threading.Thread(target=p.Lauf(aws).run, daemon=True).start()
        self.assertTrue(helpers.until(lambda: d["id"] in fernzugang.ANKER))
        key = self.key()
        self.open_up(self.st(key))
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with journal() as j:
            with wsc.connect(f"wss://localhost:{self.port}{V1}/kanal?system={d['id']}", ssl=ctx,
                             additional_headers={"Authorization": "Bearer " + key}, open_timeout=helpers.WS_OPEN_S) as conn:
                got = b""
                while b"\r\n" not in got:
                    got += conn.recv(timeout=30)
                self.assertEqual(got, b"SSH-2.0-OpenSSH_Test\r\n")                 # the server's banner, as it was
                blob = bytes(range(256)) * 64                                       # every byte value, 16 KB
                conn.send(blob)
                back = b""
                while len(back) < len(blob):
                    back += conn.recv(timeout=30)
                self.assertEqual(back, blob.upper())
                self.assertEqual(fernzugang.counts()["sshtermy"], 1)
            self.assertTrue(helpers.until(lambda: not fernzugang.SITZUNG))
            self.assertTrue(helpers.until(lambda: "sshtermy_zu" in j.getvalue()))
        out = j.getvalue()
        self.assertIn("fernzugang: sshtermy_kanal | ok | 1", out)
        self.assertRegex(out, r"fernzugang: sshtermy_zu \| sshtermy \| 0")
        self.assertNotIn(key, out)
        del aws        # the anchor's thread ends with the server in tearDown


if __name__ == "__main__":
    unittest.main()
