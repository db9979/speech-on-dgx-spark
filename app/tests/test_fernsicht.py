"""Bildschirm zeigen und bedienen (fernsicht.py, Rechner fernsteuern Stufe 2): off by default, only own devices,
asked at the computer, inputs from fixed lists, nothing kept after the end, the counts on Zustand → Live."""
import json
import threading
import time
import unittest

from tests import helpers

helpers.start()
import begleiter  # noqa: E402
import fernsicht  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import profiles  # noqa: E402
from tests import test_begleiter as tb  # noqa: E402 (the module, so its tests do not run twice)

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 200


class Fernsicht(unittest.TestCase):
    on = tb.Begleiter.on
    pair = tb.Begleiter.pair

    def setUp(self):
        tb.Begleiter.setUp(self)
        helpers.set_config(desk_view=True)
        for k in [k for k in guard._rate if k[0] in ("deskframe", "deskviewin", "viewstart", "viewframe", "viewinput",
                                                     "deskact", "deskwait")]:
            guard._rate.pop(k, None)
        self.old = (fernsicht.FRAME_WAIT, fernsicht.INPUT_WAIT, begleiter.ACT_WAIT)
        fernsicht.FRAME_WAIT = fernsicht.INPUT_WAIT = begleiter.ACT_WAIT = 0.3

    def tearDown(self):
        fernsicht.FRAME_WAIT, fernsicht.INPUT_WAIT, begleiter.ACT_WAIT = self.old
        with fernsicht._lock:
            fernsicht._sessions.clear()
        tb.Begleiter.tearDown(self)
        helpers.set_config(desk_view=False)

    def ready(self, name):
        """A profile with a paired computer that has the part "view" on and polled just now."""
        c = self.on(name)
        _, prog = self.pair(c)
        did = c.get("/api/profile/desk").json()["devices"][0]["id"]
        cfg = prog.get("/api/desk/config").json()
        r = c.put(f"/api/profile/desk/devices/{did}", json={"cfg": {"parts": dict(cfg["parts"], view=True)}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(prog.get("/api/desk/poll").status_code, 200)
        return c, prog, did

    def test_off_by_default_and_wired_everywhere(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["desk_view"], False)
        import features
        f = features.BY_KEY["begleiterschirm"]
        self.assertEqual((f.admin, f.parent, f.me, f.guide), (("desk_view",), "begleiter", "deskbox", "begleiterschirm"))
        for p in ("/api/desk/view/answer", "/api/desk/view/frame", "/api/desk/view/input", "/api/desk/view/end",
                  "/api/desk/view/step"):
            self.assertIn(p, profiles.DESK_PATHS)
        self.assertIn("view", begleiter.PARTS)
        self.assertIs(begleiter.DEFAULT["parts"]["view"], False)
        for k in ("deskframe", "deskviewin", "viewstart", "viewframe", "viewinput"):
            self.assertIn(k, guard.RATE)
        helpers.set_config(desk_view=False)
        c, prog, did = self.ready("FsAus")
        self.assertFalse(prog.get("/api/desk/config").json()["parts"]["view"])        # the switch decides
        self.assertEqual(c.post("/api/profile/desk/view", json={"did": did, "want": "view"}).status_code, 403)

    def test_asked_at_the_computer_then_pictures_flow(self):
        c, prog, did = self.ready("FsAnna")
        self.assertTrue(prog.get("/api/desk/config").json()["act"]["wait"])           # the wait runs for "view" too
        r = c.post("/api/profile/desk/view", json={"did": did, "want": "control"})
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()["id"]
        # the request reaches the computer with its wait, once
        self.assertEqual(prog.get("/api/desk/wait").json()["views"], [{"id": sid, "want": "control"}])
        self.assertEqual(prog.get("/api/desk/wait").json()["views"], [])
        # before the answer: no picture is taken, the viewer only hears "asked"
        self.assertEqual(prog.post(f"/api/desk/view/frame?id={sid}&w=10&h=10", content=JPEG).json(), {"state": "asked"})
        self.assertEqual(c.get(f"/api/profile/desk/view/{sid}").json()["state"], "asked")
        self.assertEqual(c.post(f"/api/profile/desk/view/{sid}/input", json={"events": [{"t": "key", "k": "enter"}]})
                         .status_code, 409)
        # "Nur ansehen": looking yes, inputs no
        self.assertEqual(prog.post("/api/desk/view/answer", json={"id": sid, "mode": "view"}).json(), {"state": "view"})
        self.assertEqual(prog.post(f"/api/desk/view/frame?id={sid}&w=1920&h=1080", content=JPEG).json()["state"], "view")
        g = c.get(f"/api/profile/desk/view/{sid}?after=0")
        self.assertEqual((g.headers["content-type"], g.content), ("image/jpeg", JPEG))
        self.assertEqual((g.headers["X-Spark-State"], g.headers["X-Spark-Seq"], g.headers["X-Spark-W"]), ("view", "1", "1920"))
        self.assertEqual(g.headers["Cache-Control"], "no-store")
        self.assertEqual(c.post(f"/api/profile/desk/view/{sid}/input", json={"events": [{"t": "key", "k": "enter"}]})
                         .status_code, 409)
        self.assertEqual(prog.get(f"/api/desk/view/input?id={sid}").json(), {"state": "view", "events": []})
        # the same picture again: the poll waits and then says only the state
        self.assertEqual(c.get(f"/api/profile/desk/view/{sid}?after=1").json()["state"], "view")
        rows = {x["name"]: x["n"] for x in live._conns(time.time())}
        self.assertEqual(rows.get("Bildschirm ansehen"), 1)
        # only JPEG, only up to the limit
        self.assertEqual(prog.post(f"/api/desk/view/frame?id={sid}&w=10&h=10", content=b"GIF89a").status_code, 400)
        self.assertEqual(prog.post(f"/api/desk/view/frame?id={sid}&w=10&h=10",
                                   content=JPEG + b"\0" * fernsicht.MAX_FRAME).status_code, 413)
        self.assertEqual(prog.post(f"/api/desk/view/frame?id={sid}&w=0&h=10", content=JPEG).status_code, 400)
        # ended at the computer: the picture is gone at once
        self.assertEqual(prog.post("/api/desk/view/end", json={"id": sid}).status_code, 200)
        self.assertEqual(fernsicht._sessions[sid]["frame"], b"")
        self.assertEqual(c.get(f"/api/profile/desk/view/{sid}?after=0").json(), {"state": "ended", "seq": 1,
                                                                                 "why": "am Rechner beendet"})

    def test_control_passes_only_checked_inputs(self):
        c, prog, did = self.ready("FsBen")
        sid = c.post("/api/profile/desk/view", json={"did": did, "want": "control"}).json()["id"]
        self.assertEqual(prog.post("/api/desk/view/answer", json={"id": sid, "mode": "control"}).json(), {"state": "control"})
        events = [{"t": "click", "x": 0.5, "y": 0.25, "b": "left"}, {"t": "click", "x": 2, "y": 0.1},
                  {"t": "click", "x": 0.1, "y": 0.1, "b": "middle"}, {"t": "move", "x": "a", "y": 0},
                  {"t": "key", "k": "enter"}, {"t": "key", "k": "win+r"}, {"t": "key", "k": "cmd"},
                  {"t": "scroll", "dy": -99}, {"t": "text", "s": "Hallo\x07 Welt"}, {"t": "shell", "s": "rm"}, "x"]
        r = c.post(f"/api/profile/desk/view/{sid}/input", json={"events": events})
        self.assertEqual(r.json(), {"n": 4})
        self.assertEqual(prog.get(f"/api/desk/view/input?id={sid}").json(),
                         {"state": "control", "events": [{"t": "click", "x": 0.5, "y": 0.25, "b": "left"},
                                                         {"t": "key", "k": "enter"}, {"t": "scroll", "dy": -10},
                                                         {"t": "text", "s": "Hallo Welt"}]})
        # an input that comes while the program waits answers its wait at once
        got = {}

        def wait():
            t0 = time.time()
            got["r"] = prog.get(f"/api/desk/view/input?id={sid}").json()
            got["t"] = time.time() - t0
        fernsicht.INPUT_WAIT = 5
        th = threading.Thread(target=wait)
        th.start()
        time.sleep(0.3)
        c.post(f"/api/profile/desk/view/{sid}/input", json={"events": [{"t": "key", "k": "escape"}]})
        th.join(6)
        self.assertEqual(got["r"]["events"], [{"t": "key", "k": "escape"}])
        self.assertLess(got["t"], 4)
        # "control" only when it was asked for: a view request answered with control stays view
        sid2 = c.post("/api/profile/desk/view", json={"did": did, "want": "view"}).json()["id"]
        self.assertEqual(fernsicht._sessions[sid]["state"], "ended")                     # the older one ended
        self.assertEqual(prog.post("/api/desk/view/answer", json={"id": sid2, "mode": "control"}).json(), {"state": "view"})

    def test_only_own_devices_and_declined_ends(self):
        c, prog, did = self.ready("FsCara")
        other = self.on("FsDora")
        self.assertEqual(other.post("/api/profile/desk/view", json={"did": did, "want": "view"}).status_code, 404)
        sid = c.post("/api/profile/desk/view", json={"did": did, "want": "view"}).json()["id"]
        self.assertEqual(other.get(f"/api/profile/desk/view/{sid}").status_code, 404)
        self.assertEqual(other.delete(f"/api/profile/desk/view/{sid}").status_code, 404)
        # another profile's computer cannot answer or send pictures for it
        _, prog2 = self.pair(other)
        self.assertEqual(prog2.post("/api/desk/view/answer", json={"id": sid, "mode": "view"}).status_code, 403)
        # a device key cannot start a session (browser login only)
        self.assertIn(prog.post("/api/profile/desk/view", json={"did": did, "want": "view"}).status_code, (401, 403))
        self.assertEqual(prog.post("/api/desk/view/answer", json={"id": sid, "mode": "no"}).json(), {"state": "no"})
        self.assertEqual(c.get(f"/api/profile/desk/view/{sid}").json()["state"], "no")
        self.assertEqual(prog.post("/api/desk/view/answer", json={"id": sid, "mode": "view"}).status_code, 409)
        # a computer that does not poll cannot be asked
        begleiter._seen[did] = time.time() - begleiter.ONLINE - 5
        self.assertEqual(c.post("/api/profile/desk/view", json={"did": did, "want": "view"}).status_code, 409)

    def test_sessions_end_by_themselves(self):
        c, prog, did = self.ready("FsEmil")
        uid = tb.uid_of("FsEmil")
        s = fernsicht.start(uid, did, "view")
        fernsicht.sweep(s["t"] + fernsicht.ASK_SECONDS + 1)
        self.assertEqual((s["state"], s["why"]), ("ended", "nicht beantwortet"))
        s = fernsicht.start(uid, did, "view")
        prog.post("/api/desk/view/answer", json={"id": s["id"], "mode": "view"})
        prog.post(f"/api/desk/view/frame?id={s['id']}&w=10&h=10", content=JPEG)
        fernsicht.sweep(time.time() + fernsicht.VIEWER_IDLE + 1)
        self.assertEqual((s["state"], s["why"], s["frame"]), ("ended", "niemand schaut", b""))
        # the part switched off at the device: the computer's next call ends it
        s = fernsicht.start(uid, did, "view")
        prog.post("/api/desk/view/answer", json={"id": s["id"], "mode": "view"})
        cfg = prog.get("/api/desk/config").json()
        c.put(f"/api/profile/desk/devices/{did}", json={"cfg": {"parts": dict(cfg["parts"], view=False)}})
        self.assertEqual(prog.post(f"/api/desk/view/frame?id={s['id']}&w=10&h=10", content=JPEG).status_code, 403)
        self.assertEqual(s["state"], "ended")
        # removing the device ends what runs
        c.put(f"/api/profile/desk/devices/{did}", json={"cfg": {"parts": dict(cfg["parts"], view=True)}})
        s = fernsicht.start(uid, did, "control")
        self.assertEqual(c.delete(f"/api/profile/desk/devices/{did}").status_code, 200)
        self.assertEqual((s["state"], s["why"]), ("ended", "entkoppelt"))

    def test_log_lines_are_fixed_words(self):
        import io
        import contextlib
        c, prog, did = self.ready("FsFrida")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sid = c.post("/api/profile/desk/view", json={"did": did, "want": "view"}).json()["id"]
            prog.post("/api/desk/view/answer", json={"id": sid, "mode": "view"})
            c.delete(f"/api/profile/desk/view/{sid}")
        lines = [x for x in out.getvalue().splitlines() if "bildschirm" in x]
        self.assertEqual(len(lines), 3, out.getvalue())
        for x in lines:
            self.assertRegex(x, r"^begleiter: bildschirm (gefragt|start|ende|abgelehnt)\b")
            self.assertNotIn("FsFrida", x)
            self.assertIn(" | ", x)


if __name__ == "__main__":
    unittest.main()
