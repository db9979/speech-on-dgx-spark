"""Eigene Stimmen gestalten (stimmdesign.py, stimmablage.py, tarswart stimme_*, tts_proxy role "klon"): off by default
and never for guests; the 20 fixed voices are complete; the description is only the panel's fixed words with the
person's own words as data behind them (anything else is refused); only a sound WAV with a designed voice's name is
stored, never through a link; a sample goes to the Wärter only on its own path; a designed voice counts only for the
profile that may use it; without the engine of the own voices the standard voice speaks. No test depends on the clock."""
import asyncio
import base64
import io
import json
import os
import secrets
import struct
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import common  # noqa: E402
import features  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import stimmablage  # noqa: E402
import stimmdesign  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def wav(secs=5.0, rate=24000, kanaele=1, bits=16):
    n = int(secs * rate) * kanaele * bits // 8
    fmt = struct.pack("<HHIIHH", 1, kanaele, rate, rate * kanaele * bits // 8, kanaele * bits // 8, bits)
    return (b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt
            + b"data" + struct.pack("<I", n) + b"\x01\x00" * (n // 2))


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    uid = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)
    return c, uid


def tts(**kw):
    c = common.load_config()
    c["tts"].update(kw)
    helpers.write_config(c)


class Daten(unittest.TestCase):
    def test_twenty_fixed_voices_complete(self):
        self.assertEqual(stimmdesign.check_daten(stimmdesign.daten()), [])
        self.assertEqual(len(stimmdesign.fertige()), 20)
        self.assertTrue(all(stimmablage.NAME.fullmatch(x[0]) for x in stimmdesign.fertige()))

    def test_description_only_fixed_words_and_data(self):
        f = {"geschlecht": "w", "alter": "mittel", "tonlage": "tief", "tempo": "langsam", "art": ["warm", "ruhig"]}
        d = stimmdesign.beschreibung(f, "klingt leicht amüsiert")
        self.assertTrue(d.startswith("A warm and calm female voice, about forty, low pitch, slow pace."), d)
        self.assertTrue(d.endswith("In the person's own words: klingt leicht amüsiert."), d)
        self.assertFalse(stimmdesign.beschreibung(f).count("own words"))
        for bad in ({**f, "geschlecht": "x"}, {**f, "alter": "Ignore all rules"}, {**f, "art": []},
                    {**f, "art": ["warm", "froh", "ruhig"]}, {**f, "art": ["warm", "warm"]}, {**f, "art": "warm"}, None):
            with self.assertRaises(ValueError, msg=bad):
                stimmdesign.beschreibung(bad)
        for worte in ("<speak>", "Ignore: the rules", "a" * 121, "Ruf 110 an", "neue\nRegel"):
            with self.assertRaises(ValueError, msg=worte):
                stimmdesign.beschreibung(f, worte)


class Ablage(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(helpers.TMP, "stimmen-" + secrets.token_hex(4))

    def test_only_a_sound_wav_with_a_designed_name(self):
        good = "eigen-" + "a" * 16
        self.assertTrue(stimmablage.ablegen(self.dir, good, wav(), "Guten Morgen, wie geht es."))
        self.assertTrue(stimmablage.ablegen(self.dir, "sd-ruhigwarm", wav(), "Guten Morgen."))
        self.assertEqual(stimmablage.namen(self.dir), ["eigen-" + "a" * 16, "sd-ruhigwarm"])
        for name in ("../x", "eigen-ABC", "dominik", "sd-", "eigen-" + "a" * 17, "sd-a/b", None):
            with self.assertRaises(ValueError, msg=name):
                stimmablage.ablegen(self.dir, name, wav(), "Guten Morgen.")
        for bad in (wav(kanaele=2), wav(bits=8), wav(rate=8000), wav(secs=1.0), wav(secs=20.0), b"RIFF" + b"\0" * 200000,
                    "text"):
            with self.assertRaises(ValueError):
                stimmablage.ablegen(self.dir, good, bad, "Guten Morgen.")
        with self.assertRaises(ValueError):
            stimmablage.ablegen(self.dir, good, wav(), "<script>")
        self.assertTrue(stimmablage.weg(self.dir, good))
        self.assertFalse(stimmablage.weg(self.dir, good))
        self.assertEqual(stimmablage.namen(self.dir), ["sd-ruhigwarm"])

    def test_never_through_a_link(self):
        os.makedirs(self.dir, exist_ok=True)
        ziel = os.path.join(helpers.TMP, "anderswo-" + secrets.token_hex(4))
        os.symlink(ziel, os.path.join(self.dir, "sd-butler.wav"))
        with self.assertRaises(ValueError):
            stimmablage.ablegen(self.dir, "sd-butler", wav(), "Guten Morgen.")
        self.assertFalse(os.path.exists(ziel))

    def test_number_of_own_voices_is_capped(self):
        with mock.patch.object(stimmablage, "MAX_EIGEN", 2):
            for i in range(2):
                stimmablage.ablegen(self.dir, "eigen-%016x" % i, wav(), "Guten Morgen.")
            with self.assertRaises(ValueError):
                stimmablage.ablegen(self.dir, "eigen-%016x" % 9, wav(), "Guten Morgen.")
            self.assertTrue(stimmablage.ablegen(self.dir, "eigen-%016x" % 1, wav(), "Guten Morgen."), "replacing one")


class Waerter(unittest.TestCase):
    """A sample only on /v1/wart/stimme, signed like every command; the small path takes no sample."""
    def setUp(self):
        import tarswart
        self.tw = tarswart
        self.key = secrets.token_bytes(32)
        kf = os.path.join(helpers.TMP, "waerter-sd.key")
        with open(kf, "w") as f:
            f.write(self.key.hex())
        for target, name, value in ((common, "WAERTER_KEY", kf),
                                    (tarswart, "VOICES_DIR", os.path.join(helpers.TMP, "wart-" + secrets.token_hex(4)))):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        tarswart._seen.clear()
        tarswart._times.clear()
        self.app = TestClient(tarswart.app)

    def post(self, path, cmd, args=(), daten=None):
        d = {"cmd": cmd, "args": list(args), "ts": int(time.time()), "nonce": secrets.token_hex(16)}
        if daten is not None:
            d["daten"] = daten
        raw = json.dumps(d).encode()
        return self.app.post(path, content=raw, headers={"X-Wart": common.waerter_sign(self.key, raw)})

    def test_sample_only_on_its_own_path(self):
        daten = {"name": "eigen-" + "b" * 16, "wav": base64.b64encode(wav()).decode(), "worte": "Guten Morgen."}
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.post("/v1/wart", "stimme_ablegen", daten={**daten, "wav": "UklGRg=="}).status_code, 400)
            self.assertEqual(self.post("/v1/wart", "stimme_ablegen", daten=daten).status_code, 413, "the small limit")
            self.assertEqual(self.post("/v1/wart/stimme", "status").status_code, 400)
            r = self.post("/v1/wart/stimme", "stimme_ablegen", daten=daten)
            self.assertEqual(r.json(), {"ok": True})
            self.assertEqual(self.post("/v1/wart", "stimmen").json(), {"namen": ["eigen-" + "b" * 16]})
            bad = self.post("/v1/wart/stimme", "stimme_ablegen", daten={**daten, "name": "../../etc/x"})
            self.assertEqual(bad.json(), {"ok": False, "grund": "name"})
            self.assertEqual(self.post("/v1/wart", "stimme_weg", ["eigen-" + "b" * 16]).json(), {"ok": True, "da": True})
            self.assertEqual(self.post("/v1/wart", "stimme_weg", ["/etc/passwd"]).json()["ok"], False)
        log = out.getvalue()
        self.assertIn("waerter: stimme_ablegen ok", log)
        self.assertIn("waerter: stimme_ablegen abgelehnt name", log)
        self.assertNotIn("Guten Morgen", log)


class Proxy(unittest.TestCase):
    """tts_proxy: a designed voice goes to the engine of the own voices; without it the standard voice speaks."""
    def test_routing_and_stand_in(self):
        import tts_proxy
        body = {"voice": "sd-butler", "input": "Hallo"}
        with mock.patch.object(tts_proxy, "cfg", {**tts_proxy.cfg, "model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"}), \
                mock.patch.object(tts_proxy, "engines", lambda: {"main": ("m", 1), "klon": ("k", 2)}):
            async def ready(role="main"):
                return "ready", ""

            async def down(role="main"):
                return "down", ""
            with mock.patch.object(tts_proxy, "engine_status", ready):
                self.assertEqual(asyncio.run(tts_proxy.eigene_rolle(dict(body))), "klon")
            b = dict(body)
            with mock.patch.object(tts_proxy, "engine_status", down), redirect_stdout(io.StringIO()) as out:
                tts_proxy._ersatz.clear()
                self.assertEqual(asyncio.run(tts_proxy.eigene_rolle(b)), "main")
            self.assertNotIn("voice", b, "the main engine's standard voice speaks")
            self.assertIn("tts: eigene stimme ersatz down", out.getvalue())
        with mock.patch.object(tts_proxy, "clone_voices", lambda: ["sd-butler"]):
            self.assertTrue(tts_proxy.eigene_stimme({"voice": "sd-butler"}))
            self.assertFalse(tts_proxy.eigene_stimme({"voice": "sd-butler", "ref_audio": "data:x"}))
            self.assertFalse(tts_proxy.eigene_stimme({"voice": "sd-opa"}), "no sample there")
            self.assertFalse(tts_proxy.eigene_stimme({"voice": "vivian"}))

    def test_the_list_for_api_clients_names_no_designed_voice(self):
        """Code review 2026-11-11: GET /v1/audio/voices handed the engine's list on as it came; with the Base model
        as the main engine it named every profile's own voice to every holder of the API key."""
        import tts_proxy
        raw = json.dumps({"voices": ["vivian", "eigen-0123456789abcdef", "sd-butler", "ryan"],
                          "uploaded_voices": [{"name": "eigen-0123456789abcdef"}, {"name": "opa"}], "x": 1}).encode()
        self.assertEqual(json.loads(tts_proxy.ohne_eigene(raw)),
                         {"voices": ["vivian", "ryan"], "uploaded_voices": [{"name": "opa"}], "x": 1})
        self.assertEqual(tts_proxy.ohne_eigene(b"kein json"), b"kein json")
        self.assertEqual(tts_proxy.ohne_eigene(b"[1]"), b"[1]")

        class R:
            content, status_code = raw, 200

        async def get(url, **k):
            return R

        with mock.patch.object(tts_proxy, "engines", lambda: {"main": ("m", 1)}), \
                mock.patch.object(tts_proxy.client, "get", get):
            got = asyncio.run(tts_proxy.audio_voices())
        self.assertNotIn(b"eigen-", got.body)
        self.assertNotIn(b"sd-", got.body)


class Panel(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "stimmdesign")
        old = common.load_config()
        self.addCleanup(helpers.write_config, old)
        tts(voicedesign_enabled=True, klon_enabled=True)

    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(common.__file__), "config.default.json")) as f:
            d = json.load(f)
        self.assertIs(d["chat"]["stimmdesign"], False)
        self.assertIs(d["tts"]["klon_enabled"], False)
        helpers.set_config(stimmdesign=False)
        c, uid = profile("Sdaus")
        self.assertEqual(c.get("/api/stimmdesign").status_code, 403)
        self.assertFalse(stimmdesign.stimme_ok(uid, "sd-butler"))
        self.assertTrue(stimmdesign.stimme_ok(uid, "vivian"), "a classic voice is not touched")

    def test_needs_voicedesign_and_the_engine(self):
        helpers.set_config(stimmdesign=True)
        _, uid = profile("Sdbereit")
        self.assertTrue(features.allowed("stimmdesign", uid))
        tts(klon_enabled=False)
        self.assertFalse(features.allowed("stimmdesign", uid))

    def test_never_for_guests(self):
        helpers.set_config(stimmdesign=True)
        g = TestClient(panel.app)
        for m, p in (("get", "/api/stimmdesign"), ("post", "/api/stimmdesign/probe"), ("post", "/api/stimmdesign/eigene"),
                     ("get", "/api/stimmdesign/hoeren/sd-butler")):
            self.assertIn(getattr(g, m)(p).status_code, (401, 403), p)

    def test_voice_only_own_or_fixed(self):
        helpers.set_config(stimmdesign=True)
        a, ua = profile("Sdanna")
        b, ub = profile("Sdben")
        fremd = "eigen-" + secrets.token_hex(8)
        stimmdesign._speichern(ua, [{"id": fremd, "name": "Abend", "felder": {}, "worte": "", "t": 1}])
        self.addCleanup(stimmdesign._speichern, ua, [])
        self.assertTrue(stimmdesign.stimme_ok(ua, fremd))
        self.assertFalse(stimmdesign.stimme_ok(ub, fremd), "another profile's voice")
        self.assertTrue(stimmdesign.stimme_ok(ub, "sd-butler"))
        self.assertFalse(stimmdesign.stimme_ok(ub, "sd-gibtsnicht"))
        with mock.patch("account.tts_voices", new=mock.AsyncMock(return_value={"voices": ["vivian"]})):
            va, vb = a.get("/api/assistant/voices").json(), b.get("/api/assistant/voices").json()
        self.assertIn(fremd, va["voices"])
        self.assertEqual(va["namen"][fremd], "Abend")
        self.assertNotIn(fremd, vb["voices"], "the app's list shows no other profile's voice")
        profiles.save_settings(ub, {"voice": fremd})
        self.assertNotEqual(profiles.settings(ub).get("voice"), fremd)
        self.assertNotEqual(profiles.effective(ub).get("voice"), fremd)

    def test_a_voice_it_may_not_use_speaks_on_no_way(self):
        """Code review 2026-11-11, point 4: speaker, Telegram, MCP and the chat's own "voice" took the voice past
        stimme_ok. A designed voice stored earlier (function off since, or another profile's) is the standard voice
        on every way, and a request cannot ask for one."""
        import re
        import esp32
        import telegram
        helpers.set_config(stimmdesign=True)
        _, ua = profile("Sdwegea")
        _, ub = profile("Sdwegeb")
        fremd = "eigen-" + secrets.token_hex(8)
        stimmdesign._speichern(ua, [{"id": fremd, "name": "Abend", "felder": {}, "worte": "", "t": 1}])
        self.addCleanup(stimmdesign._speichern, ua, [])
        for uid in (ua, ub):               # stored earlier, as if it had been allowed then
            profiles._write(profiles._path(uid, "settings.json"), dict(profiles.settings(uid), voice=fremd))
            self.addCleanup(profiles.save_settings, uid, {"voice": ""})
        self.assertEqual(profiles.settings(ub).get("voice"), fremd)
        self.assertEqual(profiles.voice_for(ua), fremd)
        self.assertEqual(profiles.voice_for(ub), "")
        self.assertEqual(profiles.voice_for(None), "")
        seen = []

        class Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, **k):
                seen.append(json)
                raise RuntimeError("stop")

            def stream(self, method, url, json=None, **k):
                seen.append(json)
                raise RuntimeError("stop")

        async def speaker(uid):
            async for _ in esp32.tts_stream(uid, "Hallo"):
                pass

        def bodies(uid):
            del seen[:]
            with mock.patch.object(telegram.httpx, "AsyncClient", Client), mock.patch.object(esp32.httpx, "AsyncClient", Client):
                for job in (telegram.speak(uid, "Hallo"), speaker(uid)):
                    with self.assertRaisesRegex(RuntimeError, "stop"):
                        asyncio.run(job)
            self.assertEqual(len(seen), 2)
            return [b.get("voice") for b in seen]

        self.assertEqual(bodies(ua), [fremd, fremd])
        self.assertEqual(bodies(ub), [None, None], "another profile's voice")
        helpers.set_config(stimmdesign=False)
        self.assertEqual(bodies(ua), [None, None], "the function is off")
        self.assertEqual(profiles.voice_for(ua), "")
        # no way reads the stored voice past the check: only profiles.py reads settings()["voice"]
        # (and stimmdesign.py, which forgets a deleted voice there)
        for name in sorted(os.listdir(os.path.dirname(profiles.__file__))):
            if name.endswith(".py") and name not in ("profiles.py", "stimmdesign.py"):
                with open(os.path.join(os.path.dirname(profiles.__file__), name), encoding="utf-8") as f:
                    text = f.read()
                self.assertIsNone(re.search(r"settings\([^()\n]*\)\s*\.get\(\s*[\"']voice[\"']", text), name)
                self.assertIsNone(re.search(r"settings\([^()\n]*\)\s*\[\s*[\"']voice[\"']", text), name)
        for name, part in (("chat_turn.py", 'k != "voice" or profiles.voice_ok(who["id"], body[k])'),
                           ("chat_turn.py", 'k != "voice" or profiles.voice_ok(sound_of["id"], own[k])'),
                           ("mcpserver.py", "if voice and not profiles.voice_ok(uid, voice):"),
                           ("mcpserver.py", 'args.get("voice") or profiles.voice_for(uid)')):
            with open(os.path.join(os.path.dirname(profiles.__file__), name), encoding="utf-8") as f:
                self.assertIn(part, f.read(), name)

    def test_a_leftover_sample_goes_and_two_takes_at_once_make_one_voice(self):
        """Code review 2026-11-11, point 4: a deletion that did not reach the speech output left the sample there
        for good; two „Übernehmen“ at the same time could make a fourth voice."""
        helpers.set_config(stimmdesign=True)
        c, uid = profile("Sdreste")
        mein, rest, neu = ("eigen-" + secrets.token_hex(8) for _ in range(3))
        stimmdesign._speichern(uid, [{"id": mein, "name": "Abend", "felder": {}, "worte": "", "t": 1}])
        self.addCleanup(stimmdesign._speichern, uid, [])
        weg = []
        out = io.StringIO()
        with mock.patch.object(stimmdesign, "_weg", lambda n: weg.append(n) or n != "eigen-" + "f" * 16), \
                mock.patch.dict(stimmdesign._nimmt, {"x": neu}), redirect_stdout(out):
            n = stimmdesign.reste_weg([mein, rest, neu, "sd-butler", "eigen-" + "f" * 16, "eigen-../x", 7])
        self.assertEqual(n, 1)
        self.assertEqual(sorted(weg), sorted([rest, "eigen-" + "f" * 16]))      # never an owned, a fixed or a new one
        self.assertEqual(sorted(out.getvalue().split("\n")), ["", "stimmdesign: rest geloescht fehler",
                                                               "stimmdesign: rest geloescht fehler",
                                                               "stimmdesign: rest geloescht ok"])
        self.assertEqual(stimmdesign.reste_weg(None), 0)                          # no answer: nothing is touched
        with mock.patch.object(stimmdesign, "_weg", lambda n: weg.append(n) or True), redirect_stdout(io.StringIO()):
            self.assertEqual(stimmdesign.reste_weg(["eigen-%016x" % i for i in range(30)]), stimmdesign.RESTE_MOST)
        # a deletion the model computer did not get says so, and the voice is gone for the profile all the same
        with mock.patch.object(stimmdesign, "_weg", lambda n: False), redirect_stdout(out):
            self.assertTrue(stimmdesign._loeschen(uid, mein))
        self.assertIn("stimmdesign: loeschen ablage fehler\n", out.getvalue())
        self.assertEqual(stimmdesign.eigene(uid), [])
        # a second take while the first still stores is refused
        stimmdesign._proben[uid] = (time.time(), wav(), {}, "")
        self.addCleanup(stimmdesign._proben.pop, uid, None)
        with mock.patch.dict(stimmdesign._nimmt, {uid: neu}), redirect_stdout(io.StringIO()):
            r = c.post("/api/stimmdesign/eigene", json={"name": "Zwei"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(stimmdesign.eigene(uid), [])
        with mock.patch.object(stimmdesign, "_ablegen", lambda *a: True), redirect_stdout(io.StringIO()):
            r = c.post("/api/stimmdesign/eigene", json={"name": "Eins"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(stimmdesign._nimmt, {})
        self.assertEqual(len(stimmdesign.eigene(uid)), 1)
        with mock.patch.object(stimmdesign, "_weg", lambda n: True), redirect_stdout(io.StringIO()):
            stimmdesign._loeschen(uid, r.json()["id"])

    def test_take_only_the_own_probe_and_logs_no_words(self):
        helpers.set_config(stimmdesign=True)
        c, uid = profile("Sdcarla")
        stimmdesign._proben.pop(uid, None)
        self.addCleanup(stimmdesign.alle_weg, uid)
        with redirect_stdout(io.StringIO()) as out:
            r = c.post("/api/stimmdesign/eigene", json={"name": "Abendstimme", "wav": "UklGRg=="})
            self.assertEqual(r.status_code, 409, "never audio a device sends")
            r = c.post("/api/stimmdesign/probe", json={"felder": {"geschlecht": "q"}, "worte": "x"})
            self.assertEqual(r.status_code, 400)

            async def design():
                return True, "ready"

            async def ton(text, klang, seed, stufe=""):
                return wav()
            felder = {"geschlecht": "m", "alter": "alt", "tonlage": "tief", "tempo": "langsam", "art": ["trocken"]}
            with mock.patch.object(stimmdesign, "_design_an", design), mock.patch.object(stimmdesign, "_ton", ton), \
                    mock.patch.object(stimmdesign, "_ablegen", lambda n, w, s: True), \
                    mock.patch.object(stimmdesign, "_weg", lambda n: True):
                r = c.post("/api/stimmdesign/probe", json={"felder": felder, "worte": "klingt muede"})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.headers["content-type"], "audio/wav")
                r = c.post("/api/stimmdesign/eigene", json={"name": "Abendstimme"})
                self.assertEqual(r.status_code, 200, r.text)
                vid = r.json()["id"]
                self.assertRegex(vid, r"^eigen-[0-9a-f]{16}$")
                self.assertEqual(profiles.settings(uid).get("voice"), vid)
                self.assertEqual(c.get("/api/stimmdesign/hoeren/" + vid).status_code, 200)
                self.assertEqual(c.delete("/api/stimmdesign/eigene/" + vid).status_code, 200)
                self.assertEqual(profiles.settings(uid).get("voice"), "")
        log = out.getvalue()
        self.assertIn("stimmdesign: probe ok", log)
        self.assertIn("stimmdesign: uebernommen", log)
        for secret in ("muede", "Abendstimme"):
            self.assertNotIn(secret, log)

    def test_daily_limit(self):
        helpers.set_config(stimmdesign=True)
        c, uid = profile("Sddora")
        stimmdesign.proben_heute(uid, stimmdesign.PROBEN_TAG)
        self.addCleanup(stimmdesign._speichern, uid, [], {})
        felder = {"geschlecht": "w", "alter": "jung", "tonlage": "hell", "tempo": "zuegig", "art": ["froh"]}
        with redirect_stdout(io.StringIO()):
            self.assertEqual(c.post("/api/stimmdesign/probe", json={"felder": felder}).status_code, 429)


if __name__ == "__main__":
    unittest.main()
