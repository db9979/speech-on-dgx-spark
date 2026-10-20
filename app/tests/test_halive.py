"""Home Assistant live (Vorrat je Profil, stage C, halive.py):

- One WebSocket connection per active profile keeps a copy of every state; the states tool, history and switching look
  devices up there instead of GET /api/states. Without a complete copy for exactly this address and token: HTTP.
- Only profiles the admin released Home Assistant for, never while Mein Notaus holds them, at most MAX_OPEN.
- The address goes through netguard (HOME); a refused address opens no socket.
- What Home Assistant sends is data: only results of get_states and state_changed events change the copy, capped.

A small WebSocket server on 127.0.0.1 plays Home Assistant; no wall clock decides a result.
"""
import asyncio
import json
import threading
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import features  # noqa: E402
import halive  # noqa: E402
import homeassistant  # noqa: E402
import netguard  # noqa: E402
import notaus  # noqa: E402
import vorrat  # noqa: E402

LAMP = {"entity_id": "light.flur", "state": "off", "attributes": {"friendly_name": "Flur"}}
WINDOW = {"entity_id": "binary_sensor.fenster", "state": "off", "attributes": {"friendly_name": "Fenster Bad"}}


class Apply(unittest.TestCase):
    def test_states_then_changes(self):
        store = {}
        self.assertEqual(halive.apply(store, {"type": "result", "id": 1, "success": True, "result": [LAMP, WINDOW, "x"]}), "synced")
        self.assertEqual(sorted(store), ["binary_sensor.fenster", "light.flur"])
        ev = {"type": "event", "event": {"data": {"entity_id": "binary_sensor.fenster", "new_state": dict(WINDOW, state="on")}}}
        self.assertEqual(halive.apply(store, ev), "changed")
        self.assertEqual(store["binary_sensor.fenster"]["state"], "on")
        gone = {"type": "event", "event": {"data": {"entity_id": "light.flur", "new_state": None}}}
        self.assertEqual(halive.apply(store, gone), "changed")
        self.assertNotIn("light.flur", store)

    def test_anything_else_is_left_alone(self):
        store = {"light.flur": LAMP}
        for msg in ("text", {"type": "result", "id": 2, "success": True, "result": []}, {"type": "event"},
                    {"type": "event", "event": {"data": {"entity_id": 5}}}, {"type": "auth_ok"}):
            self.assertEqual(halive.apply(store, msg), "")
        self.assertEqual(store, {"light.flur": LAMP})

    def test_capped(self):
        old = halive.MAX_ENTITIES
        halive.MAX_ENTITIES = 2
        try:
            store = {}
            halive.apply(store, {"type": "result", "id": 1, "success": True,
                                 "result": [{"entity_id": f"sensor.s{i}"} for i in range(5)]})
            self.assertEqual(len(store), 2)
            halive.apply(store, {"type": "event", "event": {"data": {"entity_id": "sensor.neu", "new_state": {"entity_id": "sensor.neu"}}}})
            self.assertEqual(len(store), 2)
        finally:
            halive.MAX_ENTITIES = old


class Wanted(unittest.TestCase):
    def setUp(self):
        self.saved = (vorrat.active, features.allowed, homeassistant.get, notaus.blocks, halive.MAX_OPEN)

    def tearDown(self):
        vorrat.active, features.allowed, homeassistant.get, notaus.blocks, halive.MAX_OPEN = self.saved

    def test_only_released_connected_and_not_held(self):
        vorrat.active = lambda now=None: ["a", "b", "c", "d", "e"]
        features.allowed = lambda key, uid, cfg=None: uid != "b"
        homeassistant.get = lambda uid: None if uid == "c" else {"url": "http://ha", "token": "t"}
        notaus.blocks = lambda kind, uid="": uid == "d"
        halive.MAX_OPEN = 4
        self.assertEqual(halive.wanted(), ["a", "e"])
        halive.MAX_OPEN = 1
        self.assertEqual(halive.wanted(), ["a"])


class Netguard(unittest.TestCase):
    def test_a_refused_address_opens_no_socket(self):
        old = netguard.resolve
        asked = []

        def refuse(host, port, level):
            asked.append((host, port, level))
            raise netguard.Blocked("refused")
        netguard.resolve = refuse
        try:
            w = halive._Live("u1", {"url": "https://ha.example:8123", "token": "t"})
            with self.assertRaises(netguard.Blocked):
                w._connect()
        finally:
            netguard.resolve = old
        self.assertEqual(asked, [("ha.example", 8123, netguard.HOME)])


class Session(unittest.TestCase):
    """A fake Home Assistant: auth, get_states, then one change; the copy follows, the tools use it."""

    def setUp(self):
        from websockets.sync.server import serve
        self.got = []

        def handler(ws):
            ws.send(json.dumps({"type": "auth_required"}))
            auth = json.loads(ws.recv())
            if auth.get("access_token") != "geheim":
                ws.send(json.dumps({"type": "auth_invalid"}))
                return
            ws.send(json.dumps({"type": "auth_ok"}))
            for _ in range(2):
                self.got.append(json.loads(ws.recv()).get("type"))
            ws.send(json.dumps({"type": "result", "id": 1, "success": True, "result": [LAMP, WINDOW]}))
            ws.send(json.dumps({"type": "event", "event": {"data": {"entity_id": "binary_sensor.fenster",
                                                                     "new_state": dict(WINDOW, state="on")}}}))
            try:
                ws.recv()
            except Exception:
                pass
        self.server = serve(handler, "127.0.0.1", 0)
        self.port = self.server.socket.getsockname()[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.item = {"url": f"http://127.0.0.1:{self.port}", "token": "geheim", "_uid": "u-live"}

    def tearDown(self):
        with halive._lock:
            w = halive._open.pop("u-live", None)
        if w:
            w.stop()
        self.server.shutdown()

    def wait_for(self, check):
        for _ in range(200):
            if check():
                return True
            threading.Event().wait(0.02)
        return False

    def test_copy_follows_and_the_tools_use_it(self):
        self.assertIsNone(halive.states(self.item))   # no connection yet: HTTP
        w = halive._Live("u-live", self.item)
        with halive._lock:
            halive._open["u-live"] = w
        w.start()
        self.assertTrue(self.wait_for(lambda: (halive.states(self.item) or [{}])[-1].get("state") == "on"
                                      or any(s.get("state") == "on" for s in halive.states(self.item) or [])))
        self.assertEqual(self.got, ["get_states", "subscribe_events"])   # it only reads and listens
        self.assertIsNone(halive.states(dict(self.item, token="other")))  # another token never sees this copy

        class NoHttp:
            async def get(self, *a, **k):
                raise AssertionError("asked over HTTP although the copy is live")
        got = asyncio.run(homeassistant._all(NoHttp(), self.item))
        self.assertEqual(sorted(s["entity_id"] for s in got), ["binary_sensor.fenster", "light.flur"])

    def test_wrong_token_keeps_no_copy(self):
        item = dict(self.item, token="falsch")
        w = halive._Live("u-live", item)
        with halive._lock:
            halive._open["u-live"] = w
        w.start()
        time.sleep(0.3)
        self.assertIsNone(halive.states(item))


if __name__ == "__main__":
    unittest.main()
