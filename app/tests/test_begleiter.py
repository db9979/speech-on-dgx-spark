"""Spark-Begleiter (begleiter.py): switches, pairing, the key's narrow paths, parts per device, notes, Notaus."""
import asyncio
import hashlib
import json
import os
import shutil
import unittest

from tests import helpers

helpers.start()
import begleiter  # noqa: E402
import guard  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import schreib  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
HOME = ("192.168.178.20", 50000)
ASR_TEXT = ["Hallo aus dem Diktat"]


def fake_asr():
    app = FastAPI()

    @app.post("/v1/audio/transcriptions")
    async def tr(req: Request):
        await req.body()
        return {"text": ASR_TEXT[0], "duration": 2.0}
    return app


ASR_PORT = helpers._port()
helpers._serve(fake_asr(), ASR_PORT)
WAV = b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 16 + (16000).to_bytes(4, "little") + b"\0" * 12 + b"\0" * 32000


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app, client=HOME)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def notaus_off():
    for f in (notaus.FILE, notaus.MINE_FILE):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    notaus._cache.update(key=None, state=None)
    notaus._mine_cache.update(key=None, d=None)


def asr_port(port):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    old = c["asr"]["port"]
    c["asr"]["port"] = port
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(c, f)
    return old


class Begleiter(unittest.TestCase):
    def setUp(self):
        helpers.set_config(desk=True, write_help=True)
        for k in [k for k in guard._rate if k[0] in ("desk", "deskask", "pair", "write", "asr", "notausset")]:
            guard._rate.pop(k, None)
        schreib._busy.clear()
        schreib._all[0] = 0
        notaus_off()

    def tearDown(self):
        helpers.set_config(desk=False, write_help=False, write_apps=False)
        notaus_off()

    def on(self, name, write=True):
        c = profile(name)
        self.assertEqual(c.put("/api/profile/settings", json={"desk_on": True, "write_on": write}).status_code, 200)
        return c

    def pair(self, c, kind="windows", name="Laptop"):
        r = c.post("/api/profile/desk/pair", json={"base": "http://192.168.178.171:31080"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertRegex(r.json()["setup"], r"^http://192\.168\.178\.171:31080#begleiter=[A-Z2-9]{4}-[A-Z2-9]{4}$")
        prog = TestClient(panel.app, client=HOME)
        r2 = prog.post("/api/desk/pair", json={"code": r.json()["code"], "name": name, "kind": kind})
        self.assertEqual(r2.status_code, 200, r2.text)
        prog.headers[profiles.DEVICE_HEADER] = r2.json()["key"]
        return r.json()["code"], prog

    def test_off_by_default_both_switches_and_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["desk"], False)
        self.assertIs(profiles.SETTINGS["desk_on"][0], False)
        c = profile("DkAnna")
        self.assertFalse(c.get("/api/profile/desk").json()["on"])
        self.assertEqual(c.post("/api/profile/desk/pair", json={"base": "https://x.de"}).status_code, 403)
        guest = TestClient(panel.app, client=HOME)
        self.assertIn(guest.get("/api/profile/desk").status_code, (401, 403))
        c = self.on("DkAnna")
        code, prog = self.pair(c)
        self.assertEqual(prog.get("/api/desk/config").status_code, 200)
        helpers.set_config(desk=False)                       # the admin switch stops every key at once
        self.assertEqual(prog.get("/api/desk/config").status_code, 401)
        helpers.set_config(desk=True)
        c.put("/api/profile/settings", json={"desk_on": False})   # so does the profile's own
        self.assertEqual(prog.get("/api/desk/poll").status_code, 401)

    def test_pair_once_and_the_key_reaches_only_its_paths(self):
        c = self.on("DkBert")
        code, prog = self.pair(c, "mac", "Büro-Mac")
        bare = TestClient(panel.app, client=HOME)
        self.assertEqual(bare.post("/api/desk/pair", json={"code": code, "kind": "mac"}).status_code, 400)     # once
        self.assertEqual(bare.post("/api/desk/pair", json={"code": "ABCD-EFGH", "kind": "mac"}).status_code, 400)
        # a writing-help code is no Begleiter code and the other way round
        wcode = schreib.new_code(uid_of("DkBert"))
        self.assertEqual(bare.post("/api/desk/pair", json={"code": wcode, "kind": "mac"}).status_code, 400)
        dcode = schreib.new_code(uid_of("DkBert"), what="begleiter")
        helpers.set_config(write_apps=True)
        self.assertEqual(bare.post("/api/write/pair", json={"code": dcode, "kind": "mac"}).status_code, 400)
        cfg = prog.get("/api/desk/config").json()
        self.assertEqual((cfg["profile"], cfg["parts"]["write"], cfg["parts"]["dictate"], cfg["parts"]["notaus"]),
                         ("DkBert", True, False, False))
        r = prog.post("/api/write/assist", json={"text": "Ein Feler."})
        self.assertEqual((r.status_code, r.json()["text"]), (200, "Ein Fehler."), r.text)
        # nothing else with this key
        for path in ("/api/profile/settings", "/api/profile/memory", "/api/profile/desk", "/api/profile/convos"):
            self.assertIn(prog.get(path).status_code, (401, 403, 404), path)
        self.assertEqual(prog.post("/api/chat", json={"messages": [{"role": "user", "content": "x"}]}).status_code, 401)
        self.assertEqual(prog.post("/api/write/draft", json={"to": "a@b.de", "text": "x"}).status_code, 401)
        self.assertEqual(prog.post("/api/write/plain?art=korrigieren", content=b"x").status_code, 401)
        self.assertEqual(prog.post("/api/test/asr", files={"file": ("w.wav", WAV, "audio/wav")}).status_code, 401)
        self.assertEqual(prog.post("/api/notaus/mine", json={}).status_code, 401)
        self.assertEqual(prog.put("/api/profile/desk/devices/x", json={}).status_code, 401)
        devs = c.get("/api/profile/desk").json()["devices"]
        self.assertEqual([d["name"] for d in devs], ["Begleiter Mac · Büro-Mac"])
        # removing it in the panel cuts it off at once
        self.assertEqual(c.delete("/api/profile/desk/devices/" + devs[0]["id"]).status_code, 200)
        self.assertEqual(prog.get("/api/desk/config").status_code, 401)

    def test_parts_are_set_per_device_and_checked_on_every_call(self):
        c = self.on("DkCarla", write=False)
        _, prog = self.pair(c)
        cfg = prog.get("/api/desk/config").json()
        self.assertFalse(cfg["allowed"]["write"])                 # the writing help is off for the profile
        self.assertFalse(cfg["parts"]["write"])
        self.assertEqual(prog.post("/api/write/assist", json={"text": "x"}).status_code, 403)
        self.assertEqual(prog.post("/api/desk/dictate", files={"file": ("w.wav", WAV, "audio/wav")}).status_code, 403)
        did = c.get("/api/profile/desk").json()["devices"][0]["id"]
        rev = prog.get("/api/desk/poll").json()["rev"]
        new = {"parts": {"write": True, "ask": False, "dictate": True, "notes": True, "status": True, "notaus": True},
               "write": {"art": "kuerzer", "sprache": "fr", "wunsch": "mit Du\x07", "arts": ["kuerzer", "nope"], "preview": False},
               "dictate": {"sprache": "xx"}, "autostart": "ja"}
        self.assertEqual(c.put(f"/api/profile/desk/devices/{did}", json={"cfg": new}).status_code, 200)
        self.assertEqual(c.put("/api/profile/desk/devices/d_fremd", json={"cfg": new}).status_code, 404)
        self.assertGreater(prog.get("/api/desk/poll").json()["rev"], rev)    # the program sees the change
        cfg = prog.get("/api/desk/config").json()
        self.assertEqual(cfg["write"], {"art": "kuerzer", "sprache": "fr", "wunsch": "mit Du", "arts": ["kuerzer"],
                                        "preview": False})
        self.assertEqual((cfg["dictate"]["sprache"], cfg["autostart"]), ("auto", True))   # bad values: defaults
        self.assertFalse(cfg["parts"]["write"])                    # on for the device, still off for the profile
        self.assertEqual(prog.post("/api/desk/ask", json={"text": "Hallo?"}).status_code, 403)
        old = asr_port(ASR_PORT)
        try:
            r = prog.post("/api/desk/dictate", files={"file": ("w.wav", WAV, "audio/wav")}, data={"sprache": "de"})
        finally:
            asr_port(old)
        self.assertEqual((r.status_code, r.json()), (200, {"text": "Hallo aus dem Diktat"}), r.text)
        # the switch of the writing help opens the part again
        c.put("/api/profile/settings", json={"write_on": True})
        self.assertTrue(prog.get("/api/desk/config").json()["parts"]["write"])

    def test_ask_answers_as_text(self):
        c = self.on("DkDora")
        _, prog = self.pair(c)
        r = prog.post("/api/desk/ask", json={"text": "Wie spät ist es?"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsInstance(r.json()["answer"], str)
        self.assertTrue(r.json()["answer"])
        self.assertEqual(prog.post("/api/desk/ask", json={"text": ""}).json()["answer"], "Ich habe keine Frage gehört.")

    def test_notes_wait_for_the_program_and_only_with_the_part_on(self):
        c = self.on("DkEmil")
        _, prog = self.pair(c)
        uid = uid_of("DkEmil")
        self.assertFalse(begleiter.reachable(uid))               # not polled yet
        last = prog.get("/api/desk/poll").json()["last"]
        self.assertTrue(begleiter.reachable(uid))
        self.assertEqual(push.pick(uid)[0], "desk")
        import asyncio
        self.assertEqual(asyncio.run(push.send(uid, "Termin", "Zahnarzt um 10", tag="agent")), 1)
        r = prog.get(f"/api/desk/poll?after={last}").json()
        self.assertEqual([(x["title"], x["body"]) for x in r["notes"]], [("Termin", "Zahnarzt um 10")])
        self.assertEqual(prog.get(f"/api/desk/poll?after={r['last']}").json()["notes"], [])
        did = c.get("/api/profile/desk").json()["devices"][0]["id"]
        cfg = prog.get("/api/desk/config").json()
        parts = dict(cfg["parts"], notes=False)
        c.put(f"/api/profile/desk/devices/{did}", json={"cfg": {"parts": parts}})
        begleiter.keep(uid, "Noch was", "x")
        self.assertEqual(prog.get(f"/api/desk/poll?after={r['last']}").json()["notes"], [])
        self.assertFalse(begleiter.reachable(uid))

    def test_notaus_button_only_triggers_and_then_the_key_rests(self):
        c = self.on("DkFritz")
        _, prog = self.pair(c)
        self.assertEqual(prog.post("/api/desk/notaus", json={}).status_code, 403)   # part off by default
        did = c.get("/api/profile/desk").json()["devices"][0]["id"]
        c.put(f"/api/profile/desk/devices/{did}", json={"cfg": {"parts": {"notaus": True}}})
        r = prog.post("/api/desk/notaus", json={})
        self.assertEqual((r.status_code, r.json()), (200, {"on": True}), r.text)
        self.assertTrue(notaus.own(uid_of("DkFritz")))
        r = prog.get("/api/desk/poll")
        self.assertEqual(r.status_code, 503)
        self.assertTrue(r.json()["detail"].startswith("Mein Notaus"))
        self.assertEqual(prog.get("/api/notaus").status_code, 200)       # the state stays readable
        self.assertEqual(prog.post("/api/notaus/mine/off", json={"pin": "1234"}).status_code, 503)   # never lifted by key

    def test_pair_limits(self):
        c = self.on("DkGabi")
        self.assertEqual(c.post("/api/profile/desk/pair", json={"base": "javascript:alert(1)"}).status_code, 400)
        self.assertEqual(c.post("/api/profile/desk/pair", json={"base": "https://x.de/pfad"}).status_code, 400)
        bare = TestClient(panel.app, client=HOME)
        self.assertEqual(bare.post("/api/desk/pair", json={"code": "x", "kind": "toaster"}).status_code, 400)
        self.assertEqual(begleiter.clean({"parts": "x", "write": None}), begleiter.clean({}))


GH = "http://gh.test"
EXE = b"MZ fake exe " * 300


def github(meta, files, tag="begleiter-windows"):
    """A fake GitHub: the release `tag` with begleiter.json and the files."""
    def handle(req):
        p = req.url.path
        if p.endswith("/releases/tags/" + tag):
            return httpx.Response(200, json={"tag_name": tag, "assets": [
                {"name": n, "browser_download_url": GH + "/dl/" + n} for n in ["begleiter.json", *files]]})
        if p == "/dl/begleiter.json":
            return httpx.Response(200, content=json.dumps(meta).encode())
        if p.startswith("/dl/") and p[4:] in files:
            return httpx.Response(200, content=files[p[4:]])
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def win_meta(version, x64=EXE, arm=EXE):
    f = lambda n, b: {"name": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    return {"version": version, "files": {"x64": f("SparkBegleiter-x64.exe", x64), "arm64": f("SparkBegleiter-arm64.exe", arm)}}


class Updates(unittest.TestCase):
    def setUp(self):
        helpers.set_config(desk=True)
        for k in [k for k in guard._rate if k[0] in ("desk", "deskupd", "pair")]:
            guard._rate.pop(k, None)
        shutil.rmtree(begleiter.UPD_DIR, ignore_errors=True)
        self.gh = os.environ.get("SPEECH_SPARK_GITHUB_API")
        os.environ["SPEECH_SPARK_GITHUB_API"] = GH

    def tearDown(self):
        helpers.set_config(desk=False)
        shutil.rmtree(begleiter.UPD_DIR, ignore_errors=True)
        if self.gh is None:
            os.environ.pop("SPEECH_SPARK_GITHUB_API", None)
        else:
            os.environ["SPEECH_SPARK_GITHUB_API"] = self.gh

    def test_only_checked_files_are_kept_and_offered_to_older_programs(self):
        files = {"SparkBegleiter-x64.exe": EXE, "SparkBegleiter-arm64.exe": EXE}
        bad = dict(win_meta("1.0.350"))
        bad["files"] = dict(bad["files"], x64=dict(bad["files"]["x64"], sha256="0" * 64))
        with self.assertRaises(ValueError):                     # a wrong checksum keeps nothing
            asyncio.run(begleiter.fetch("windows", github(bad, files)))
        self.assertIsNone(begleiter.kept("windows"))
        with self.assertRaises(ValueError):                     # names outside the release or odd names: nothing
            asyncio.run(begleiter.fetch("windows", github(dict(win_meta("1.0.350"), files={"x64": {
                "name": "../evil.exe", "size": 3, "sha256": "0" * 64}}), files)))
        self.assertEqual(asyncio.run(begleiter.fetch("windows", github(win_meta("1.0.350"), files))), "1.0.350")
        self.assertEqual(begleiter.kept("windows")["version"], "1.0.350")
        up = begleiter.newer("x64", "1.0.342")
        self.assertEqual((up["version"], up["size"], up["sha256"]), ("1.0.350", len(EXE), hashlib.sha256(EXE).hexdigest()))
        self.assertIsNone(begleiter.newer("x64", "1.0.350"))      # same version
        self.assertIsNone(begleiter.newer("x64", "1.0.9999"))     # newer program
        self.assertIsNone(begleiter.newer("x64", "1.0.0-dev"))    # development build
        self.assertIsNone(begleiter.newer("mac", "1.0.1"))        # nothing kept for the Mac
        # an older release does not replace the kept one
        self.assertEqual(asyncio.run(begleiter.fetch("windows", github(win_meta("1.0.349"), files))), "1.0.350")

    def test_program_sees_and_loads_the_update_only_with_its_key(self):
        files = {"SparkBegleiter-x64.exe": EXE, "SparkBegleiter-arm64.exe": EXE}
        asyncio.run(begleiter.fetch("windows", github(win_meta("1.0.350"), files)))
        c = profile("DkUwe")
        c.put("/api/profile/settings", json={"desk_on": True})
        r = c.post("/api/profile/desk/pair", json={"base": "http://192.168.178.171:31080"})
        prog = TestClient(panel.app, client=HOME)
        key = prog.post("/api/desk/pair", json={"code": r.json()["code"], "kind": "windows", "name": "PC"}).json()["key"]
        prog.headers[profiles.DEVICE_HEADER] = key
        cfg = prog.get("/api/desk/config?version=1.0.342&arch=x64").json()
        self.assertEqual(cfg["update"]["version"], "1.0.350")
        self.assertTrue(cfg["coffee"].startswith("https://buymeacoffee.com/"))
        self.assertEqual(prog.get("/api/desk/poll?version=1.0.342&arch=x64").json()["update"], "1.0.350")
        self.assertIsNone(prog.get("/api/desk/poll?version=1.0.350&arch=x64").json()["update"])
        r = prog.get("/api/desk/update?arch=x64")
        self.assertEqual((r.status_code, hashlib.sha256(r.content).hexdigest()), (200, hashlib.sha256(EXE).hexdigest()))
        self.assertEqual(prog.get("/api/desk/update?arch=mac").status_code, 404)
        self.assertEqual(prog.get("/api/desk/update?arch=../x").status_code, 400)
        self.assertIn(TestClient(panel.app, client=HOME).get("/api/desk/update?arch=x64").status_code, (401, 403))
        self.assertEqual(c.get("/api/profile/desk").json()["devices"][0]["version"], "1.0.350")
        self.assertEqual(begleiter.platforms(), ["windows"])

    def test_only_github_download_addresses(self):
        os.environ.pop("SPEECH_SPARK_GITHUB_API", None)
        self.assertTrue(begleiter._allowed_download("https://github.com/db9979/speech-on-dgx-spark/releases/download/begleiter-windows/begleiter.json"))
        self.assertFalse(begleiter._allowed_download("https://evil.example/releases/download/x"))
        self.assertFalse(begleiter._allowed_download("http://github.com/a/b/releases/download/x"))


if __name__ == "__main__":
    unittest.main()
