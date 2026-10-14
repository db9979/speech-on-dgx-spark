"""Chats mit anderen Sparks (verbund.py, plan plaene/spark-verbund.md): off until the admin, the own address and the
profile switch allow it; only signed requests of allowed Sparks, for the right Spark, in time and once; pairing with a
one-time code; contact requests that let nothing through before "Annehmen" and never tell who exists; the queue with
its second tick, its retries and its "nicht zugestellt"; changes across Sparks only on the own messages; sealed texts
at rest; Live and the journal with numbers only.

The other Spark is played here in Python: its own Ed25519 key, its requests signed like a Spark signs them, and what
this Spark sends it is caught (verbund._post) and checked against this Spark's key."""
import asyncio
import base64
import contextlib
import io
import json
import os
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import chats  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import verbund  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DELIVER = verbund.deliver_once   # the real one; the panel's own loop (a served panel of another test) gets a stub
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
HERE = "spark.beispiel.de"
FAR = "fremd.example.org"


def profile(name, pin="2468", chats=True):
    """A profile; chats=False: the admin blocked Chats for it (Funktionen → Wer darf was), the only way off now."""
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    r = ADMIN.put(f"/api/admin/features/chats/profiles/{uid_of(c)}", json={"on": chats})
    assert r.status_code == 200, r.text
    return c


def uid_of(client):
    return client.get("/api/whoami").json()["profile"]["id"]


class Other:
    """The other Spark: its key, its domain, its requests."""

    def __init__(self, dom=FAR):
        self.dom, self.key = dom, Ed25519PrivateKey.generate()
        self.got = []                                   # (type, body) this Spark sent to it

    @property
    def pub(self):
        return base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw,
                                                                   serialization.PublicFormat.Raw)).decode()

    def raw(self, **body):
        b = dict({"v": 1, "t": int(time.time()), "n": os.urandom(16).hex()}, **body)
        return json.dumps(b, separators=(",", ":")).encode()

    def send(self, client=None, dest=HERE, raw=None, sig=None, frm=None, **body):
        raw = self.raw(**body) if raw is None else raw
        sig = sig or base64.b64encode(self.key.sign(b"spark-verbund v1\n" + dest.encode() + b"\n" + raw)).decode()
        return (client or TestClient(panel.app)).post(verbund.INBOX, content=raw, headers={
            "Content-Type": "application/json", "X-Spark-From": frm or self.dom, "X-Spark-Sig": sig})

    async def post(self, dom, raw, sig):
        """What this Spark sends: checked against its own key and the receiving domain, then kept."""
        assert dom == self.dom, dom
        assert verbund.verify(verbund.public_b64(), dom, raw, sig), "not signed by this Spark for that domain"
        b = json.loads(raw)
        self.got.append((b["type"], b))
        return self.status

    status = 200


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(chats=True, chats_verbund=True, verbund_domain=HERE, verbund_mode="pair")
        chats._sent.clear()
        for k in [k for k in guard._rate if k[0] in ("verbundin", "verbund", "verbundadmin", "trust")]:
            guard._rate.pop(k, None)
        verbund._peer_rate.clear()
        verbund._fetches.clear()
        verbund._nonces.clear()
        for name in ("peers.json", "queue.json", "pairs.json"):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(verbund._dir(), name))
        self.other = Other()
        self.keys = {FAR: self.other.pub}
        p1 = mock.patch.object(verbund, "fetch_key", side_effect=self._fetch)
        p2 = mock.patch.object(verbund, "_post", side_effect=self.other.post)
        p3 = mock.patch.object(verbund, "deliver_once", new=mock.AsyncMock(return_value=0))
        for x in (p1, p2, p3):
            x.start()
            self.addCleanup(x.stop)

    async def _fetch(self, dom):
        return self.keys.get(dom, "")

    def tearDown(self):
        helpers.set_config(chats=False, chats_verbund=False, verbund_domain="", verbund_mode="pair")
        chats._subs.clear()

    def paired(self):
        with verbund._lock:
            p = verbund.peers()
            p[FAR] = {"key": self.other.pub, "state": "paired", "t": time.time(), "last": 0, "in": 0, "out": 0}
            verbund._save_peers(p)

    def deliver(self):
        return asyncio.run(DELIVER())

    def contact_with(self, client, frm="vbfremd", name="Fremde Frieda"):
        """The other one asks, the profile accepts: the chat's id."""
        h = verbund.handle(uid_of(client))
        self.assertEqual(self.other.send(type="ask", **{"from": frm, "to": h, "name": name}).status_code, 200)
        rid = verbund.rid_of(f"{frm}@{FAR}")
        r = client.post("/api/verbund/answer", json={"id": rid, "act": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["chat"], rid


class Switches(Base):
    def test_off_until_admin_switch_and_address(self):
        import features
        self.assertEqual(features.BY_KEY["verbund"].parent, "chats")
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            d = json.load(f)["chat"]
        self.assertIs(d["chats_verbund"], False)
        self.assertEqual(d["verbund_domain"], "")
        self.assertEqual(d["verbund_mode"], "pair")
        a = profile("Vbalma")
        self.assertTrue(a.get("/api/chats").json()["verbund"])
        self.assertEqual(TestClient(panel.app).get(verbund.WELL_KNOWN).json()["key"], verbund.public_b64())
        helpers.set_config(verbund_domain="")             # without the own address from outside: off
        self.assertFalse(verbund.admin_on())
        self.assertEqual(TestClient(panel.app).get(verbund.WELL_KNOWN).status_code, 404)
        self.assertEqual(self.other.send(type="ask", **{"from": "x", "to": "y"}).status_code, 404)
        helpers.set_config(verbund_domain=HERE, chats_verbund=False)
        self.assertEqual(TestClient(panel.app).get(verbund.WELL_KNOWN).status_code, 404)
        self.assertEqual(a.get("/api/verbund").status_code, 403)
        helpers.set_config(chats_verbund=True)
        self.assertEqual(a.get("/api/verbund").status_code, 200)   # the admin's switch is enough, no profile switch
        self.assertNotIn("verbund_on", a.get("/api/profile/settings").json())
        g = TestClient(panel.app)                         # guests never
        self.assertIn(g.get("/api/verbund").status_code, (401, 403))
        self.assertIn(g.post("/api/verbund/ask", json={"addr": "a@" + FAR}).status_code, (401, 403))

    def test_admin_address_is_checked_and_needs_the_code(self):
        import admin
        self.assertIn(("chat", "verbund_domain"), admin.SENSITIVE)
        self.assertIn(("chat", "chats_verbund"), admin.SENSITIVE)
        self.assertIn(("chat", "verbund_mode"), admin.SENSITIVE)
        cfg = ADMIN.get("/api/config").json()
        for bad in ("https://spark.beispiel.de", "spark.beispiel.de/pfad", "nur-ein-name", "a b.de"):
            cfg["chat"]["verbund_domain"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, bad)
        cfg["chat"]["verbund_domain"] = HERE
        cfg["chat"]["verbund_mode"] = "jeder"
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)
        import stufen
        self.assertIn(("POST", "/api/admin/verbund/pair"), stufen.LIST)
        self.assertIn(("POST", "/api/admin/verbund/connect"), stufen.LIST)
        self.assertIn(TestClient(panel.app).get("/api/admin/verbund").status_code, (401, 403))


class Inbox(Base):
    def test_only_paired_sparks_in_pair_mode_open_mode_like_mail_blocked_never(self):
        a = profile("Vbcarla")
        h = verbund.handle(uid_of(a))
        ask = {"type": "ask", "from": "vbfremd", "to": h, "name": "Frieda"}
        self.assertEqual(self.other.send(**ask).status_code, 403)          # unknown Spark, pair mode
        self.assertEqual(verbund.listing(uid_of(a)), [])
        helpers.set_config(verbund_mode="open")
        self.assertEqual(self.other.send(**ask).status_code, 200)
        self.assertEqual(verbund.peers()[FAR]["state"], "open")
        self.assertEqual([c["state"] for c in verbund.listing(uid_of(a))], ["in"])
        helpers.set_config(verbund_mode="pair")                            # open ones count only in open mode
        self.assertEqual(self.other.send(**ask).status_code, 403)
        verbund.peer_set(FAR, "block")
        helpers.set_config(verbund_mode="open")
        self.assertEqual(self.other.send(**ask).status_code, 403)          # blocked in every mode
        verbund.peer_set(FAR, "allow")
        self.assertEqual(self.other.send(**ask).status_code, 200)

    def test_signature_receiver_time_and_once(self):
        self.paired()
        a = profile("Vbdora")
        body = {"type": "ask", "from": "vbfremd", "to": verbund.handle(uid_of(a)), "name": "Frieda"}
        stranger = Ed25519PrivateKey.generate()
        raw = self.other.raw(**body)
        bad = base64.b64encode(stranger.sign(b"spark-verbund v1\n" + HERE.encode() + b"\n" + raw)).decode()
        self.assertEqual(self.other.send(raw=raw, sig=bad).status_code, 403)               # someone else's key
        self.assertEqual(self.other.send(dest="dritter.example.net", **body).status_code, 403)  # signed for another Spark
        self.assertEqual(self.other.send(raw=raw, frm="dritter.example.net").status_code, 403)  # claims another sender
        late = json.loads(self.other.raw(**body))
        late["t"] -= 3600
        self.assertEqual(self.other.send(raw=json.dumps(late).encode()).status_code, 400)  # an hour old
        self.assertEqual(self.other.send(raw=raw).status_code, 200)
        self.assertEqual(self.other.send(raw=raw).status_code, 409)                         # the same once more
        self.assertEqual(self.other.send(raw=b"{" + b" " * (verbund.MAX_BODY + 10) + b"}").status_code, 413)
        self.assertEqual(self.other.send(raw=b"[1]").status_code, 400)
        self.assertEqual(self.other.send(type="befehl", **{"from": "x", "to": "y"}).status_code, 400)

    def test_the_same_answer_whether_someone_is_here_or_not(self):
        self.paired()
        a = profile("Vbemil")
        r1 = self.other.send(type="ask", **{"from": "vbfremd", "to": verbund.handle(uid_of(a)), "name": "F"})
        r2 = self.other.send(type="ask", **{"from": "vbfremd", "to": "niemand.hier", "name": "F"})
        b = profile("Vbelse", chats=False)                 # exists, but does not use Chats
        self.addCleanup(ADMIN.put, f"/api/admin/features/chats/profiles/{uid_of(b)}", json={"on": True})
        r3 = self.other.send(type="ask", **{"from": "vbfremd", "to": verbund.handle(uid_of(b)), "name": "F"})
        self.assertEqual((r1.status_code, r1.json()), (r2.status_code, r2.json()))
        self.assertEqual(r2.json(), r3.json())
        self.assertEqual(verbund.listing(uid_of(b)), [])

    def test_every_refusal_writes_a_log_line(self):
        self.paired()
        a = profile("Vblogs")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(a.post("/api/verbund/ask", json={"addr": "x@" + HERE}).status_code, 400)
            self.assertEqual(a.post("/api/verbund/open", json={"id": "r_" + "0" * 12}).status_code, 403)
            with mock.patch.object(verbund, "PEER_PER_MIN", 0):
                self.assertEqual(self.other.send(type="ask", **{"from": "x", "to": "y"}).status_code, 429)
            helpers.set_config(chats_verbund=False)
            self.assertEqual(self.other.send(type="ask", **{"from": "x", "to": "y"}).status_code, 404)
            self.assertEqual(a.get("/api/verbund").status_code, 403)
        helpers.set_config(chats_verbund=True)
        log = out.getvalue()
        for line in ("verbund: ask refused | why ValueError", "verbund: open refused", "verbund: refused rate",
                     "verbund: refused off", "verbund: page refused | why off"):
            self.assertIn(line, log)
        self.assertNotIn(HERE, log)

    def test_too_many_requests_from_one_spark(self):
        self.paired()
        with mock.patch.object(verbund, "PEER_PER_MIN", 3):
            codes = [self.other.send(type="ask", **{"from": "vbf", "to": "nobody"}).status_code for _ in range(5)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3:], [429, 429])


class Pairing(Base):
    def test_a_code_works_once_and_a_day(self):
        r = ADMIN.post("/api/admin/verbund/pair", json={})
        self.assertEqual(r.status_code, 200, r.text)
        code = r.json()["code"]
        self.assertTrue(code.startswith(HERE + "#"))
        secret = code.split("#", 1)[1]
        self.assertEqual(self.other.send(type="pair", secret="falsch" * 4).status_code, 403)
        self.assertNotIn(FAR, verbund.peers())
        self.assertEqual(self.other.send(type="pair", secret=secret).status_code, 200)
        self.assertEqual(verbund.peers()[FAR]["state"], "paired")
        self.assertEqual(verbund.peers()[FAR]["key"], self.other.pub)
        verbund.peer_set(FAR, "remove")
        self.assertEqual(self.other.send(type="pair", secret=secret).status_code, 403)      # only once
        code = verbund.pair_new(now=time.time() - verbund.PAIR_SECS - 5)                    # a day old
        self.assertEqual(self.other.send(type="pair", secret=code.split("#", 1)[1]).status_code, 403)
        listed = ADMIN.get("/api/admin/verbund").json()
        self.assertEqual(listed["key"], verbund.fingerprint(verbund.public_b64()))

    def test_using_the_other_admins_code(self):
        self.other.status = 200
        r = ADMIN.post("/api/admin/verbund/connect", json={"code": FAR + "#" + "A" * 24})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["fingerprint"], verbund.fingerprint(self.other.pub))
        self.assertEqual(self.other.got[-1][0], "pair")
        self.assertEqual(self.other.got[-1][1]["secret"], "A" * 24)
        self.assertEqual(verbund.peers()[FAR]["state"], "paired")
        self.keys[FAR] = Other().pub                                   # a new key later: refused
        r = ADMIN.post("/api/admin/verbund/connect", json={"code": FAR + "#" + "B" * 24})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/verbund/connect", json={"code": "kaputt"}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/verbund/connect", json={"code": HERE + "#" + "C" * 24}).status_code, 400)

    def test_a_changed_key_is_refused_until_removed(self):
        self.paired()
        a = profile("Vbfrida")
        imposter = Other()
        r = imposter.send(type="ask", **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        self.assertEqual(r.status_code, 403)                            # same domain, other key: no
        self.assertEqual(verbund.listing(uid_of(a)), [])


class Contacts(Base):
    def test_nothing_gets_through_before_accept_and_accept_says_yes(self):
        self.paired()
        a = profile("Vbgerda")
        uid = uid_of(a)
        h = verbund.handle(uid)
        rid = verbund.rid_of("vbfremd@" + FAR)
        self.assertEqual(self.other.send(type="msg", id="a" * 12, text="Hallo?", **{"from": "vbfremd", "to": h}).status_code, 200)
        self.assertFalse(any(c.get("kind") == "far" for c in chats.mine(uid).values()))    # no contact: dropped
        self.other.send(type="ask", **{"from": "vbfremd", "to": h, "name": "Frieda <b>F</b>"})
        st = a.get("/api/chats").json()
        self.assertEqual(st["far_asks"], 1)
        self.assertEqual(a.get("/api/verbund").json()["contacts"][0]["state"], "in")
        self.other.send(type="msg", id="b" * 12, text="Noch nicht", **{"from": "vbfremd", "to": h})
        self.assertFalse(any(c.get("kind") == "far" for c in chats.mine(uid).values()))    # asked, not accepted
        r = a.post("/api/verbund/answer", json={"id": rid, "act": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["chat"]
        self.assertEqual(self.deliver(), 1)
        kind, body = self.other.got[-1]
        self.assertEqual((kind, body["to"], body["from"]), ("yes", "vbfremd", h))
        self.assertEqual(self.other.send(type="msg", id="c" * 12, text="Jetzt aber", **{"from": "vbfremd", "to": h}).status_code, 200)
        d = a.get("/api/chats/items", params={"id": cid}).json()
        self.assertTrue(d["far"])
        self.assertEqual([x["text"] for x in d["items"]], ["Jetzt aber"])
        self.assertEqual(d["items"][0]["name"], chats.clean_name("Frieda <b>F</b>"))   # a plain name, no markup
        self.assertNotIn("<", d["items"][0]["name"])
        self.assertTrue(d["can_send"])

    def test_decline_block_and_both_asking(self):
        self.paired()
        a = profile("Vbhanna")
        uid = uid_of(a)
        h = verbund.handle(uid)
        rid = verbund.rid_of("vbfremd@" + FAR)
        self.other.send(type="ask", **{"from": "vbfremd", "to": h})
        a.post("/api/verbund/answer", json={"id": rid, "act": "no"})
        self.assertEqual(self.deliver(), 0)                             # declining tells the other Spark nothing
        self.other.send(type="ask", **{"from": "vbfremd", "to": h})
        self.assertEqual(verbund.contact(uid, rid)["state"], "no")      # not heard again for NO_DAYS
        a.post("/api/verbund/answer", json={"id": rid, "act": "block"})
        self.assertEqual([c["state"] for c in a.get("/api/verbund").json()["contacts"]], ["block"])
        a.post("/api/verbund/answer", json={"id": rid, "act": "unblock"})
        self.assertEqual(a.get("/api/verbund").json()["contacts"], [])
        # both ask each other: accepted on both sides at once
        r = a.post("/api/verbund/ask", json={"addr": "Vbzweite@" + FAR.upper()})
        self.assertEqual(r.status_code, 200, r.text)
        rid2 = verbund.rid_of("vbzweite@" + FAR)
        self.other.send(type="ask", **{"from": "vbzweite", "to": h, "name": "Zweite"})
        self.assertEqual(verbund.contact(uid, rid2)["state"], "ok")
        self.deliver()
        self.assertEqual([k for k, b in self.other.got], ["ask", "yes"])

    def test_asking_checks_the_address_and_the_spark(self):
        a = profile("Vbida")
        for bad in ("ohne-at", "a@b", "a@" + HERE, "x y@" + FAR, "a@b@" + FAR):
            self.assertEqual(a.post("/api/verbund/ask", json={"addr": bad}).status_code, 400, bad)
        self.assertEqual(a.post("/api/verbund/ask", json={"addr": "vbx@" + FAR}).status_code, 403)   # not paired
        self.paired()
        self.assertEqual(a.post("/api/verbund/ask", json={"addr": "vbx@" + FAR}).status_code, 200)
        self.deliver()
        kind, body = self.other.got[-1]
        self.assertEqual((kind, body["to"], body["name"]), ("ask", "vbx", "Vbida"))
        self.assertNotIn("u_", json.dumps(body))                         # no profile ids leave the Spark
        self.assertEqual(set(body), {"type", "from", "to", "name", "v", "t", "n"})

    def test_at_most_twenty_waiting_requests(self):
        self.paired()
        a = profile("Vbjana")
        h = verbund.handle(uid_of(a))
        for i in range(verbund.MAX_WAITING + 3):
            self.other.send(type="ask", **{"from": f"vbf{i}", "to": h})
        self.assertEqual(len(verbund.listing(uid_of(a))), verbund.MAX_WAITING)


class Messages(Base):
    def test_send_queue_second_tick_and_read(self):
        self.paired()
        a = profile("Vbkarl")
        cid, rid = self.contact_with(a)
        self.deliver()
        r = a.post("/api/chats/send", json={"id": cid, "text": "Hallo Frieda"})
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["item"]["id"]
        self.assertEqual(r.json()["item"]["tick"], "sent")
        self.assertEqual(self.deliver(), 1)
        kind, body = self.other.got[-1]
        self.assertEqual((kind, body["id"], body["text"]), ("msg", mid, "Hallo Frieda"))
        d = a.get("/api/chats/items", params={"id": cid}).json()
        self.assertEqual(d["items"][-1]["tick"], "got")                 # the other Spark has it
        self.other.send(type="read", id=mid, **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        d = a.get("/api/chats/items", params={"id": cid}).json()
        self.assertEqual(d["items"][-1]["tick"], "read")
        # the profile reads the other's message: "gelesen" goes there once
        self.other.send(type="msg", id="d" * 12, text="Gelesen?", **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        a.post("/api/chats/read", json={"id": cid})
        a.post("/api/chats/read", json={"id": cid})
        self.deliver()
        self.assertEqual([b["id"] for k, b in self.other.got if k == "read"], ["d" * 12])

    def test_away_retry_and_given_up_after_seven_days(self):
        self.paired()
        a = profile("Vblena")
        cid, rid = self.contact_with(a)
        self.deliver()
        self.other.status = 503
        mid = a.post("/api/chats/send", json={"id": cid, "text": "Bist du da?"}).json()["item"]["id"]
        a.post("/api/chats/send", json={"id": cid, "text": "Zweite"})
        n0 = len(self.other.got)
        self.assertEqual(self.deliver(), 0)
        n = len(self.other.got)
        self.assertEqual(n, n0 + 1)                                     # the Spark is away: not the rest of it too
        q = verbund._queue()
        self.assertEqual([x["tries"] for x in q], [1, 0])
        self.assertGreater(q[0]["next"], time.time() + 50)
        self.assertEqual(asyncio.run(DELIVER(now=time.time() + 30)), 0)
        self.assertEqual(len(self.other.got), n)                        # not before its minute
        self.assertEqual(asyncio.run(DELIVER(now=time.time() + verbund.KEEP + 60)), 0)
        self.assertEqual(verbund._queue(), [])
        d = a.get("/api/chats/items", params={"id": cid}).json()
        x = next(x for x in d["items"] if x["id"] == mid)
        self.assertTrue(x.get("fail"))
        self.other.status = 200

    def test_only_text_without_the_files_switch_and_only_while_the_contact_stands(self):
        self.paired()
        helpers.set_config(chats_media=True)
        self.addCleanup(helpers.set_config, chats_media=False)
        a = profile("Vbmara")
        cid, rid = self.contact_with(a)
        r = a.post("/api/chats/media", params={"id": cid, "kind": "file"}, content=b"%PDF-1.4 hallo",
                   headers={"Content-Type": "application/octet-stream", "X-Chat-Name": "a.pdf"})
        self.assertEqual(r.status_code, 403)   # Fotos und Dateien zu anderen Sparks is off (Files below)
        a.post("/api/verbund/remove", json={"id": rid})
        r = a.post("/api/chats/send", json={"id": cid, "text": "Noch da?"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(a.get("/api/chats/items", params={"id": cid}).json()["can_send"])
        n = len(self.other.got)
        self.other.send(type="msg", id="e" * 12, text="Hallo", **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        self.assertEqual(len(a.get("/api/chats/items", params={"id": cid}).json()["items"]), 0)
        self.assertEqual(len(self.other.got), n)

    def test_twice_delivered_is_once_and_changes_only_on_own_messages(self):
        self.paired()
        a = profile("Vbnina")
        cid, rid = self.contact_with(a)
        h = verbund.handle(uid_of(a))
        frm = {"from": "vbfremd", "to": h}
        for _ in range(2):
            self.other.send(type="msg", id="f" * 12, text="Einmal", **frm)
        self.other.send(type="msg", id="0" * 12, text="Antwort", reply="f" * 12, **frm)
        mine = a.post("/api/chats/send", json={"id": cid, "text": "Meins"}).json()["item"]["id"]
        self.other.send(type="edit", id="f" * 12, text="Einmal, geändert", **frm)
        self.other.send(type="edit", id=mine, text="Gefälscht", **frm)              # not its message
        self.other.send(type="back", id=mine, **frm)
        self.other.send(type="react", id=mine, emoji="👍", **frm)
        self.other.send(type="react", id="0" * 12, emoji="💣", **frm)               # not one of the reactions
        d = a.get("/api/chats/items", params={"id": cid}).json()
        by = {x["id"]: x for x in d["items"]}
        self.assertEqual(len(d["items"]), 3)
        self.assertEqual(by["f" * 12]["text"], "Einmal, geändert")
        self.assertEqual(by["0" * 12]["reply"]["id"], "f" * 12)
        self.assertEqual(by[mine]["text"], "Meins")
        self.assertFalse(by[mine].get("gone"))
        self.assertEqual(by[mine]["react"], [{"e": "👍", "n": 1, "me": False}])
        self.assertNotIn("react", by["0" * 12])
        self.other.send(type="back", id="f" * 12, **frm)
        self.assertTrue(next(x for x in a.get("/api/chats/items", params={"id": cid}).json()["items"] if x["id"] == "f" * 12)["gone"])
        # own changes go there too
        a.post("/api/chats/edit", json={"id": cid, "mid": mine, "text": "Meins, neu"})
        a.post("/api/chats/react", json={"id": cid, "mid": "0" * 12, "emoji": "❤️"})
        a.post("/api/chats/back", json={"id": cid, "mid": mine})
        self.deliver()
        kinds = [(k, b.get("id")) for k, b in self.other.got if k in ("edit", "react", "back")]
        self.assertEqual(kinds, [("edit", mine), ("react", "0" * 12), ("back", mine)])

    def test_texts_sealed_at_rest_and_a_deleted_profile_leaves_nothing_behind(self):
        self.paired()
        a = profile("Vbolga")
        uid = uid_of(a)
        cid, rid = self.contact_with(a, name="Geheimname")
        self.other.send(type="msg", id="1" * 12, text="Streng geheimer Satz", **{"from": "vbfremd", "to": verbund.handle(uid)})
        a.post("/api/chats/send", json={"id": cid, "text": "Auch geheim hier"})
        with open(chats._chat_file(cid)) as f:
            raw = f.read()
        self.assertNotIn("Streng geheimer", raw)
        self.assertNotIn("Auch geheim", raw)
        r = ADMIN.delete(f"/api/admin/profiles/{uid}")
        self.assertIn(r.status_code, (200, 204), r.text)
        self.assertNotIn(cid, chats._index())
        self.assertEqual(verbund.contacts_of(uid), {})
        self.assertEqual(verbund.handle(uid, make=False), "")
        self.assertFalse([x for x in verbund._queue() if x["body"].get("text") == "Auch geheim hier"])


class Watch(Base):
    def test_live_and_journal_with_numbers_only(self):
        self.paired()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            a = profile("Vbpaula")
            cid, rid = self.contact_with(a, name="Journalname")
            self.other.send(type="msg", id="2" * 12, text="Kein Text im Journal", **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
            a.post("/api/chats/send", json={"id": cid, "text": "Auch nicht dieser"})
            self.deliver()
            self.other.send(raw=b"kaputt")
        lines = [x for x in out.getvalue().splitlines() if x.startswith(("verbund:", "chats:"))]
        self.assertTrue(any(x.startswith("verbund: sent") for x in lines), lines)
        joined = "\n".join(lines)
        for word in (FAR, "vbfremd", "Journalname", "Vbpaula", "Kein Text", "Auch nicht", verbund.handle(uid_of(a))):
            self.assertNotIn(word, joined)
        v = verbund.for_live()
        self.assertEqual(set(v), {"on", "sparks", "contacts", "in", "out", "waiting", "media", "files_in", "files_out"})
        self.assertTrue(all(isinstance(x, (int, bool)) for x in v.values()))
        live = chats.for_live()
        self.assertTrue(live["far_on"])
        self.assertGreaterEqual(live["far_sparks"], 1)

    def test_watched_by_the_service_watch_and_in_the_backup(self):
        import backup
        import dienstwacht
        import logfilter
        self.assertIn("verbund", dienstwacht.SVC)
        parts = dienstwacht.active()
        self.assertEqual(parts["verbund"]["own"]["url"], "https://" + HERE + verbund.WELL_KNOWN)
        self.assertIn(("verbund", "Chats mit anderen Sparks"), dienstwacht.NEEDS_NET)
        self.assertTrue(verbund._dir().startswith(profiles.USERS_DIR))   # in the backup with users/
        verbund.public_b64()
        backup._forget_cached()
        self.assertIsNone(verbund._pkey)
        self.assertEqual([k for k, rx in logfilter._AREAS if rx.search("verbund: sent | n 1")], ["nachrichten"])

    def test_the_key_comes_from_the_sparks_secret_and_never_leaves(self):
        k1 = verbund.public_b64()
        verbund._pkey = None
        self.assertEqual(verbund.public_b64(), k1)                       # the same key from the same secret
        wk = TestClient(panel.app).get(verbund.WELL_KNOWN).json()
        self.assertEqual(set(wk), {"v", "key", "inbox"})
        for name in os.listdir(verbund._dir()):
            with open(os.path.join(verbund._dir(), name), "rb") as f:
                self.assertNotIn(b"PRIVATE", f.read())


def jpeg(w=600, h=400):
    """A photo as a phone writes it: with a place in its EXIF data."""
    from PIL import Image
    im, out, ex = Image.new("RGB", (w, h), (200, 80, 40)), io.BytesIO(), None
    from PIL import Image as _I
    ex = _I.Exif()
    ex[0x8825] = {1: "N", 2: (48.0, 8.0, 0.0)}
    im.save(out, "JPEG", exif=ex)
    return out.getvalue()


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class Files(Base):
    """Fotos, Dateien und Sprache zu anderen Sparks (V2, chat.verbund_media): the file first, signed, then its message."""

    def setUp(self):
        super().setUp()
        helpers.set_config(chats_media=True, verbund_media=True)
        self.blobs = []
        p = mock.patch.object(verbund, "_post_blob", side_effect=self._blob)
        p.start()
        self.addCleanup(p.stop)
        import shutil
        shutil.rmtree(verbund._blob_dir(), ignore_errors=True)
        verbund._today()["bytes"].clear()

    def tearDown(self):
        helpers.set_config(chats_media=False, verbund_media=False)
        super().tearDown()

    blob_status = 200

    async def _blob(self, dom, sha, data, now):
        self.blobs.append((dom, sha, data))
        return self.blob_status

    def give(self, data, sha=None, size=None, client=None, frm=None, dest=HERE, t=None):
        """The other Spark hands in a file: the signed head in a header, the bytes as the body."""
        import hashlib
        head = json.dumps({"v": 1, "t": int(time.time()) if t is None else t, "n": os.urandom(16).hex(),
                           "sha": sha or hashlib.sha256(data).hexdigest(), "size": len(data) if size is None else size},
                          separators=(",", ":")).encode()
        sig = base64.b64encode(self.other.key.sign(b"spark-verbund v1\n" + dest.encode() + b"\n" + head)).decode()
        return (client or TestClient(panel.app)).post(verbund.BLOB_PATH, content=data, headers={
            "Content-Type": "application/octet-stream", "X-Spark-From": frm or FAR,
            "X-Spark-Blob": base64.urlsafe_b64encode(head).decode(), "X-Spark-Sig": sig})

    def up(self, client, cid, kind, data, name=""):
        from urllib.parse import quote
        head = {"Content-Type": "application/octet-stream"}
        if name:
            head["X-Chat-Name"] = quote(name)
        return client.post("/api/chats/media", params={"id": cid, "kind": kind}, content=data, headers=head)

    def test_off_until_its_own_switch_on_both_sides(self):
        import features
        self.assertEqual(features.BY_KEY["verbundmedia"].parent, "verbund")
        with open(os.path.join(os.path.dirname(verbund.__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["verbund_media"], False)
        self.paired()
        a = profile("Vbmedaria")
        cid, _ = self.contact_with(a, frm="vbmeda")
        helpers.set_config(verbund_media=False)
        self.assertFalse(a.get("/api/chats").json()["far_media"])
        self.assertEqual(self.up(a, cid, "photo", jpeg()).status_code, 403)
        self.assertEqual(self.give(PDF).status_code, 401)          # refused before a byte of the body is read
        helpers.set_config(verbund_media=True)
        self.assertTrue(a.get("/api/chats").json()["far_media"])
        self.assertEqual(self.up(a, cid, "photo", jpeg()).status_code, 200)

    def test_a_photo_goes_out_without_its_place_file_first_then_the_message(self):
        import hashlib
        self.paired()
        a = profile("Vbmedbert")
        cid, _ = self.contact_with(a, frm="vbmedb")
        r = self.up(a, cid, "photo", jpeg())
        self.assertEqual(r.status_code, 200, r.text)
        self.deliver()
        dom, sha, data = self.blobs[-1]
        self.assertEqual((dom, sha), (FAR, hashlib.sha256(data).hexdigest()))
        self.assertTrue(data.startswith(b"\xff\xd8"))
        self.assertNotIn(b"Exif", data[:200])                     # drawn anew here: no place goes out
        msg = [b for t, b in self.other.got if t == "msg"][-1]
        self.assertEqual((msg["media"]["kind"], msg["media"]["sha"], msg["text"]), ("photo", sha, ""))
        # the other Spark takes no files: the message is not delivered, nothing waits for a week
        self.blob_status = 404
        self.up(a, cid, "file", PDF, name="plan.pdf")
        n = len([1 for t, _ in self.other.got if t == "msg"])
        self.deliver()
        self.assertEqual(len([1 for t, _ in self.other.got if t == "msg"]), n)
        self.assertEqual(verbund.waiting_count(), 0)
        self.assertTrue(a.get("/api/chats/items", params={"id": cid}).json()["items"][-1].get("fail"))

    def test_a_file_from_another_spark_is_made_anew_here(self):
        import hashlib
        self.paired()
        b = profile("Vbmedcora")
        cid, _ = self.contact_with(b, frm="vbmedc")
        h = verbund.handle(uid_of(b))
        photo = jpeg()
        self.assertEqual(self.give(photo).status_code, 200)
        r = self.other.send(type="msg", **{"from": "vbmedc", "to": h, "id": "a1b2c3d4e5f6", "text": "",
                                         "media": {"kind": "photo", "sha": hashlib.sha256(photo).hexdigest(), "size": len(photo)}})
        self.assertEqual(r.status_code, 200)
        x = b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]
        self.assertEqual((x["id"], x["kind"]), ("a1b2c3d4e5f6", "photo"))
        got = b.get("/api/chats/media", params={"id": cid, "mid": x["id"], "part": "f"})
        self.assertEqual(got.status_code, 200)
        self.assertTrue(got.content.startswith(b"\xff\xd8"))
        self.assertNotIn(b"Exif", got.content[:200])
        self.assertEqual(os.listdir(verbund._blob_dir()), [])           # taken from where it waited
        # a file with its name; one that is no file of an allowed kind comes not at all
        self.give(PDF)
        self.other.send(type="msg", **{"from": "vbmedc", "to": h, "id": "b1b2c3d4e5f6", "text": "",
                                        "media": {"kind": "file", "sha": hashlib.sha256(PDF).hexdigest(), "size": len(PDF), "name": "plan.pdf"}})
        x = b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]
        self.assertEqual(x["kind"], "file")
        exe = b"MZ\x90\x00" + os.urandom(200)
        self.give(exe)
        self.other.send(type="msg", **{"from": "vbmedc", "to": h, "id": "c1b2c3d4e5f6", "text": "",
                                        "media": {"kind": "file", "sha": hashlib.sha256(exe).hexdigest(), "size": len(exe), "name": "tool.exe"}})
        self.assertNotEqual(b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["id"], "c1b2c3d4e5f6")
        # a message announcing a file that never came: nothing
        self.other.send(type="msg", **{"from": "vbmedc", "to": h, "id": "d1b2c3d4e5f6", "text": "Hallo",
                                        "media": {"kind": "photo", "sha": "0" * 64, "size": 5}})
        self.assertNotEqual(b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["id"], "d1b2c3d4e5f6")

    def test_a_file_needs_a_signed_head_its_exact_bytes_and_stays_within_the_day(self):
        import hashlib
        self.paired()
        self.assertEqual(self.give(PDF, sha="1" * 64).status_code, 400)           # not the bytes the head names
        self.assertEqual(self.give(PDF, size=len(PDF) + 5).status_code, 400)
        self.assertEqual(self.give(PDF, dest="anderer.example.net").status_code, 403)   # signed for another Spark
        self.assertEqual(self.give(PDF, t=int(time.time()) - 3600).status_code, 400)
        self.assertEqual(self.give(PDF, frm="unbekannt.example.net").status_code, 401)  # no known Spark: never read
        big = chats.MAX_FILE + 1
        self.assertIn(self.give(b"x", size=big).status_code, (400, 413))
        with mock.patch.object(verbund, "BLOB_DAY", len(PDF) * 2 + 1):
            self.assertEqual(self.give(PDF).status_code, 200)
            self.assertEqual(self.give(PDF + b"1").status_code, 200)
            self.assertEqual(self.give(PDF + b"22").status_code, 429)
        # one Spark cannot take the file of another: kept per sending Spark
        sha = hashlib.sha256(PDF).hexdigest()
        self.assertTrue(os.path.exists(verbund._blob_file(FAR, sha)))
        self.assertFalse(os.path.exists(verbund._blob_file("anderer.example.net", sha)))
        with open(verbund._blob_file(FAR, sha), "rb") as f:
            self.assertNotIn(b"%PDF", f.read())                                 # sealed while it waits
        os.utime(verbund._blob_file(FAR, sha), (time.time() - verbund.BLOB_KEEP - 5,) * 2)
        self.assertGreaterEqual(verbund.blob_tidy(), 1)
        self.assertFalse(os.path.exists(verbund._blob_file(FAR, sha)))


if __name__ == "__main__":
    unittest.main()


THIRD = "dritte.example.net"


class Groups(Base):
    """Gruppen mit anderen Sparks (V2 Teil 2, chat.verbund_groups): the group belongs to its home Spark."""

    def setUp(self):
        super().setUp()
        helpers.set_config(chats_groups=True, verbund_groups=True)
        self.paired()

    def tearDown(self):
        helpers.set_config(chats_groups=False, verbund_groups=False)
        super().tearDown()

    def sent(self, kind):
        return [b for t, b in self.other.got if t == kind]

    def far_group(self, client, gid="c" + "a1" * 6, name="Ausflug", frm="vbfremd"):
        """The other Spark puts the profile into its group: the chat's id here."""
        me = verbund.address(uid_of(client))
        r = self.other.send(type="gadd", gid=gid, name=name, **{"from": frm, "to": verbund.handle(uid_of(client)), "members": [
            {"addr": f"vbfremd@{FAR}", "name": "Fremde Frieda"}, {"addr": f"drei@{THIRD}", "name": "Dora Dritt"},
            {"addr": me, "name": "egal"}]})
        self.assertEqual(r.status_code, 200)
        import verbundgruppe
        return verbundgruppe.far_cid(FAR, gid)

    def test_off_by_default_and_only_accepted_contacts_go_in(self):
        import admin
        import features
        self.assertEqual(features.BY_KEY["verbundgruppen"].parent, "verbund")
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["verbund_groups"], False)
        self.assertIn(("chat", "verbund_groups"), admin.SENSITIVE)
        a, b = profile("Vggerd"), profile("Vghanna")
        _, rid = self.contact_with(a)
        self.other.send(type="ask", **{"from": "vbfrage", "to": verbund.handle(uid_of(a)), "name": "Nur gefragt"})
        asked = verbund.rid_of(f"vbfrage@{FAR}")
        helpers.set_config(verbund_groups=False)
        self.assertEqual(a.get("/api/chats").json()["far_people"], [])
        r = a.post("/api/chats/group", json={"name": "Aus", "members": [rid]})
        self.assertEqual(r.status_code, 403)                          # nobody left who may come in
        helpers.set_config(verbund_groups=True)
        self.assertEqual([x["id"] for x in a.get("/api/chats").json()["far_people"]], [rid])   # accepted only
        r = a.post("/api/chats/group", json={"name": "Wandern", "members": [uid_of(b), rid, asked]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["left_out"], ["Nur gefragt"])
        cid = r.json()["id"]
        self.assertEqual(set(chats._index()[cid]["members"]), {uid_of(a), uid_of(b), rid})
        self.assertNotIn("verbund_groups", a.get("/api/profile/settings").json())   # the admin's switch only
        r = a.post("/api/chats/members", json={"id": cid, "admin": [rid]})
        self.assertNotIn(rid, chats._index()[cid]["admins"])           # admins only of this Spark
        self.assertEqual(r.status_code, 200)
        g = TestClient(panel.app)                                       # guests never
        self.assertIn(g.post("/api/chats/group", json={"name": "x", "members": [rid]}).status_code, (401, 403))

    def test_the_home_spark_sends_on_and_takes_what_its_members_there_write(self):
        a, b = profile("Vgilse"), profile("Vgjana")
        _, rid = self.contact_with(a)
        cid = a.post("/api/chats/group", json={"name": "Wandern", "members": [uid_of(b), rid]}).json()["id"]
        self.deliver()
        add = self.sent("gadd")
        self.assertEqual(len(add), 1)
        self.assertEqual((add[0]["to"], add[0]["gid"], add[0]["name"]), ("vbfremd", cid, "Wandern"))
        self.assertEqual({m["addr"] for m in add[0]["members"]},
                         {verbund.address(uid_of(a)), verbund.address(uid_of(b)), f"vbfremd@{FAR}"})
        r = a.post("/api/chats/send", json={"id": cid, "text": "Treffpunkt acht Uhr"})
        mid = r.json()["item"]["id"]
        self.deliver()
        msg = self.sent("gmsg")[-1]
        self.assertEqual((msg["id"], msg["text"], msg["by"]), (mid, "Treffpunkt acht Uhr", verbund.address(uid_of(a))))
        for path, body in (("/api/chats/edit", {"id": cid, "mid": mid, "text": "neu"}), ("/api/chats/back", {"id": cid, "mid": mid})):
            self.assertEqual(a.post(path, json=body).status_code, 403, path)   # not across Sparks yet
        n = len(self.sent("gmsg"))
        self.assertEqual(self.other.send(type="gmsg", gid=cid, id="3" * 12, text="Bin dabei", reply=mid,
                                         **{"from": "vbfremd", "to": ""}).status_code, 200)
        items = b.get(f"/api/chats/items?id={cid}").json()["items"]
        x = next(x for x in items if x["id"] == "3" * 12)
        self.assertEqual((x["text"], x["from"]), ("Bin dabei", rid))
        self.other.send(type="gmsg", gid=cid, id="3" * 12, text="Bin dabei", **{"from": "vbfremd", "to": ""})
        self.assertEqual(sum(1 for x in b.get(f"/api/chats/items?id={cid}").json()["items"] if x["id"] == "3" * 12), 1)
        self.deliver()
        self.assertEqual(len(self.sent("gmsg")), n)                    # not back to the Spark it came from
        self.other.send(type="gmsg", gid=cid, id="4" * 12, text="Fremd", **{"from": "vbanders", "to": ""})
        self.assertFalse(any(x["id"] == "4" * 12 for x in b.get(f"/api/chats/items?id={cid}").json()["items"]))
        self.other.send(type="gleave", gid=cid, **{"from": "vbfremd", "to": ""})
        self.assertNotIn(rid, chats._index()[cid]["members"])
        a.post("/api/chats/members", json={"id": cid, "add": [rid]})
        a.post("/api/chats/members", json={"id": cid, "remove": [rid]})
        self.deliver()
        self.assertEqual(self.sent("gremove")[-1]["to"], "vbfremd")

    def test_a_group_of_another_spark_only_from_an_accepted_contact_and_managed_there(self):
        a, b = profile("Vgkarl"), profile("Vglena")
        self.contact_with(a)
        cid = self.far_group(a)
        lst = a.get("/api/chats").json()["chats"]
        self.assertEqual(next(x for x in lst if x["id"] == cid)["title"], "Ausflug")
        d = a.get(f"/api/chats/items?id={cid}").json()
        self.assertTrue(d["far_home"])
        self.assertIn("Dora Dritt", [m["name"] for m in d["members"]])
        self.far_group(b)                                              # b never accepted vbfremd: nothing
        self.assertNotIn(uid_of(b), chats._index()[cid]["members"])
        self.other.send(type="gmsg", gid="c" + "a1" * 6, id="5" * 12, text="Hallo aus Drittland", by=f"drei@{THIRD}",
                        byname="Dora Dritt", **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        x = a.get(f"/api/chats/items?id={cid}").json()["items"][-1]
        self.assertEqual((x["text"], x["from"]), ("Hallo aus Drittland", verbund.rid_of(f"drei@{THIRD}")))
        mine = a.post("/api/chats/send", json={"id": cid, "text": "Ich komme"}).json()["item"]["id"]
        self.deliver()
        up = self.sent("gmsg")[-1]
        self.assertEqual((up["to"], up["gid"], up["id"], up["from"]), ("", "c" + "a1" * 6, mine, verbund.handle(uid_of(a))))
        self.assertEqual(a.post("/api/chats/members", json={"id": cid, "add": [uid_of(b)]}).status_code, 403)
        self.assertEqual(a.post("/api/chats/opts", json={"id": cid, "name": "Meins"}).status_code, 403)
        self.other.send(type="gname", gid="c" + "a1" * 6, name="Ausflug Mai", **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        self.assertEqual(a.get(f"/api/chats/items?id={cid}").json()["title"], "Ausflug Mai")
        self.other.send(type="gmembers", gid="c" + "a1" * 6, members=[{"addr": f"vbfremd@{FAR}", "name": "Fremde Frieda"}],
                        **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        self.assertEqual(chats._index()[cid]["members"], [uid_of(a), verbund.rid_of(f"vbfremd@{FAR}")])
        self.other.send(type="gremove", gid="c" + "a1" * 6, **{"from": "vbfremd", "to": verbund.handle(uid_of(a))})
        self.assertNotIn(cid, chats._index())                          # nobody here left: the chat goes
        helpers.set_config(verbund_groups=False)                       # off: requests of other Sparks are dropped
        self.assertNotIn(self.far_group(a, gid="c" + "b2" * 6), chats._index())

    def test_leaving_a_group_of_another_spark_tells_it_and_logs_and_live_numbers_only(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            a = profile("Vgmona")
            self.contact_with(a)
            cid = self.far_group(a, gid="c" + "c3" * 6, name="Geheimgruppe")
            a.post("/api/chats/send", json={"id": cid, "text": "Kein Journaltext"})
            self.assertEqual(a.post("/api/chats/leave", json={"id": cid}).status_code, 200)
            self.deliver()
        self.assertEqual(self.sent("gleave")[-1]["from"], verbund.handle(uid_of(a)))
        self.assertNotIn(cid, chats._index())
        b = profile("Vgnora")                                          # a deleted profile leaves the group there too
        self.contact_with(b)
        self.far_group(b, gid="c" + "d4" * 6)
        h = verbund.handle(uid_of(b))
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{uid_of(b)}").status_code, 200)
        self.deliver()
        self.assertEqual(self.sent("gleave")[-1]["from"], h)
        joined = "\n".join(x for x in out.getvalue().splitlines() if x.startswith(("verbund:", "chats:")))
        self.assertIn("verbund: group joined there", joined)
        for word in (FAR, THIRD, "Geheimgruppe", "Kein Journaltext", "Vgmona", "Dora"):
            self.assertNotIn(word, joined)
        import verbundgruppe
        v = verbundgruppe.for_live()
        self.assertEqual(set(v), {"on", "home", "there"})
        live = chats.for_live()
        self.assertTrue(live["far_groups"])
        self.assertTrue(all(isinstance(live[k], int) for k in ("far_groups_home", "far_groups_there", "far_group_in")))
