"""Aufnahmen abschreiben (abschrift.py, plan open-notebook Stufe 3a): off by default and never for guests; the content
must be what its ending says (magic), size and length limits before anything is kept; ffmpeg only on the local file
with fixed arguments (no network protocol, no uploaded name in a command); every piece's page is its start second and
wissen.where says "bei 12:30"; the words the overlap heard twice go; only in quiet minutes and in wissen.KETTE after the
page pictures; speech cancels a piece and it goes on at the same piece; the daily limit, long recordings only after
long_ok; without "Originale aufbewahren" the file goes, with it only the sound track stays; "Abbrechen"; the request
to the speech recognition carries the stage "hinten" with the panel's key; logs with fixed words and numbers only.
No test depends on the clock (a fixed moment NOW)."""
import asyncio
import contextlib
import io
import json
import os
import struct
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import abschrift  # noqa: E402
import common  # noqa: E402
import documents  # noqa: E402
import features  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import vorrang  # noqa: E402
import wissen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0          # a fixed moment, never the clock


def run(coro):
    return asyncio.run(coro)


def quiet(buf=None):
    return contextlib.redirect_stdout(buf or io.StringIO())


def wav(secs, rate=16000):
    """A silent mono 16-bit WAV of secs seconds (no ffmpeg needed to make it)."""
    pcm = b"\x00\x00" * int(secs * rate)
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


class Ear:
    """The speech recognition: hands out one text per piece (a function of the call number) and counts its calls."""
    def __init__(self, say=None):
        self.calls, self.say = 0, say or (lambda k: f"Satz Nummer {k} im Vortrag")

    async def __call__(self, wav_bytes, uid=None):
        self.calls += 1
        return self.say(self.calls)


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "doc_audio", "doc_audio_mb", "doc_audio_min", "doc_audio_day_min", "documents",
                          "doc_originals", "doc_semantic", "doc_brief", "doc_auswertung")
        helpers.set_config(doc_audio=True, doc_audio_mb=300, doc_audio_min=180, doc_audio_day_min=240, documents=True,
                           doc_originals=False, doc_semantic=False, doc_brief=False, doc_auswertung=False)
        abschrift._hold["asr"] = 0.0
        abschrift._said.clear()
        abschrift._tries.clear()
        vorrang._local[0] = 0.0
        try:
            os.utime(vorrang.MARK, (0, 0))
        except OSError:
            pass

    def fresh(self, name):
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        return c, uid

    def upload(self, c, name, data):
        return c.post("/api/profile/docs/audio", files={"file": (name, data, "application/octet-stream")})

    def recording(self, c, uid, secs, name="Vortrag Wärmepumpe.wav"):
        """A recording as if uploaded: length from the test, not from ffprobe."""
        with mock.patch.object(abschrift, "laenge", lambda path: float(secs)), quiet():
            r = self.upload(c, name, wav(1))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def step(self, uid, ear, now=NOW, lang=True, cut=lambda path, start, secs: wav(1), buf=None):
        with mock.patch.object(abschrift, "hoeren", ear), mock.patch.object(abschrift, "schneiden", cut), \
                mock.patch.object(wissen, "quiet", lambda: True), mock.patch.object(wissen, "long_ok", lambda now: lang), \
                mock.patch.object(abschrift.profiles, "user_ids", lambda: [uid]), quiet(buf):
            return run(abschrift.due_once(now))

    def doc(self, uid, doc):
        return next(d for d in documents.list_docs(uid) if d["id"] == doc)


class Off(Base):
    def test_off_by_default_and_everywhere(self):
        self.assertIs(json.loads(helpers.repo_file("app", "config.default.json"))["chat"]["doc_audio"], False)
        self.assertNotIn("docaudio", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["docaudio"].parent, "documents")
        c, uid = self.fresh("Abschriftaus")
        helpers.set_config(doc_audio=False)
        self.assertFalse(abschrift.admin_on())
        with quiet():
            self.assertEqual(self.upload(c, "memo.wav", wav(1)).status_code, 403)
        ear = Ear()
        self.assertIsNone(self.step(uid, ear))
        self.assertEqual(ear.calls, 0)
        self.assertIs(c.get("/api/profile/wissen").json()["audio"]["on"], False)

    def test_never_for_guests(self):
        self.assertEqual(features.reason("docaudio", None), "guest")
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/docs/audio", files={"file": ("m.wav", wav(1))}).status_code, (401, 403))
        self.assertIn(guest.post("/api/profile/wissen/0123456789ab/abschrift/stop").status_code, (401, 403))

    def test_blocked_profile(self):
        c, uid = self.fresh("Abschriftsperre")
        doc = self.recording(c, uid, 40)
        helpers.set_config(deny={"docaudio": [uid]})
        self.addCleanup(helpers.set_config, deny={})
        with quiet():
            self.assertEqual(self.upload(c, "memo.wav", wav(1)).status_code, 403)
        ear = Ear()
        self.assertIsNone(self.step(uid, ear))
        self.assertEqual((ear.calls, self.doc(uid, doc)["state"]), (0, "hoeren"))


class Upload(Base):
    def test_content_must_be_what_the_ending_says(self):
        self.assertEqual(abschrift.family(wav(1)), "wav")
        self.assertEqual(abschrift.family(b"OggS\x00\x02" + b"\x00" * 20), "ogg")
        self.assertEqual(abschrift.family(b"fLaC\x00\x00\x00\x22" + b"\x00" * 8), "flac")
        self.assertEqual(abschrift.family(b"\x1a\x45\xdf\xa3" + b"\x00" * 12), "mkv")
        self.assertEqual(abschrift.family(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 4), "mp4")
        self.assertEqual(abschrift.family(b"ID3\x04\x00" + b"\x00" * 11), "mp3")
        self.assertEqual(abschrift.family(b"\xff\xfb\x90\x00" + b"\x00" * 12), "mp3")
        self.assertEqual(abschrift.family(b"\xff\xf1\x50\x80" + b"\x00" * 12), "aac")
        self.assertIsNone(abschrift.family(b"%PDF-1.7\n" + b"\x00" * 8))
        self.assertTrue(abschrift.fits("a.m4a", b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 4))
        self.assertTrue(abschrift.fits("a.mov", b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 4))
        self.assertTrue(abschrift.fits("a.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 12))
        self.assertFalse(abschrift.fits("a.mp3", wav(1)))            # a WAV called .mp3
        self.assertFalse(abschrift.fits("a.wav", b"<script>alert(1)</script>"))
        self.assertFalse(abschrift.fits("a.exe", wav(1)))            # not an allowed ending at all
        c, uid = self.fresh("Abschrifttyp")
        buf = io.StringIO()
        with quiet(buf):
            r = self.upload(c, "memo.mp3", b"%PDF-1.7\n" + b"\x00" * 200)
        self.assertEqual(r.status_code, 400)
        self.assertIn("abschrift: abgelehnt | typ", buf.getvalue())
        self.assertEqual(os.listdir(documents.audio_dir(uid)) if os.path.isdir(documents.audio_dir(uid)) else [], [])
        self.assertEqual(documents.list_docs(uid), [])

    def test_size_and_length_limits_before_anything_is_kept(self):
        c, uid = self.fresh("Abschriftgross")
        helpers.set_config(doc_audio_mb=10)
        big = wav(1) + b"\x00" * (10 * 1024**2)
        buf = io.StringIO()
        with quiet(buf):
            r = self.upload(c, "lang.wav", big)
        self.assertIn(r.status_code, (400, 413))
        helpers.set_config(doc_audio_mb=300, doc_audio_min=5)
        with mock.patch.object(abschrift, "laenge", lambda path: 5 * 60 + 1.0), quiet(buf):
            r = self.upload(c, "lang.wav", wav(1))
        self.assertEqual(r.status_code, 400)
        self.assertIn("5 Minuten", r.json()["detail"])
        with mock.patch.object(abschrift, "laenge", lambda path: None), quiet(buf):
            self.assertEqual(self.upload(c, "stumm.wav", wav(1)).status_code, 400)
        self.assertIn("abschrift: abgelehnt | laenge", buf.getvalue())
        self.assertIn("abschrift: abgelehnt | keine tonspur", buf.getvalue())
        self.assertEqual(os.listdir(documents.audio_dir(uid)), [])   # nothing kept
        self.assertEqual(documents.list_docs(uid), [])
        # the body limit holds before the login and the reading: its own path, before the documents' one
        lim = next(m for m in panel.app.user_middleware if m.cls is common.BodyLimit).kwargs["limits"]
        paths = [p for p, _ in lim]
        self.assertLess(paths.index("/api/profile/docs/audio"), paths.index("/api/profile/docs"))
        self.assertEqual(dict(lim)["/api/profile/docs/audio"](), abschrift.max_bytes() + 1024**2)

    def test_waits_named_by_its_id_with_0600(self):
        c, uid = self.fresh("Abschriftdatei")
        doc = self.recording(c, uid, 40, name="../../etc/passwd; rm -rf.wav")
        files = os.listdir(documents.audio_dir(uid))
        self.assertEqual(files, [doc + ".wav"])
        self.assertEqual(os.stat(os.path.join(documents.audio_dir(uid), files[0])).st_mode & 0o777, 0o600)
        d = self.doc(uid, doc)
        self.assertEqual((d["kind"], d["source"], d["state"], d["secs"], d["heard"]), ("audio", "audio", "hoeren", 40, 0))
        self.assertNotIn("/", d["name"])

    def test_ffmpeg_only_on_the_local_file_with_fixed_arguments(self):
        seen = []

        def fake(args, **kw):
            seen.append(args)
            return mock.Mock(returncode=0, stdout=b'{"streams": [{"codec_type": "audio"}], "format": {"duration": "61.5"}}')
        with mock.patch.object(abschrift.subprocess, "run", fake):
            self.assertEqual(abschrift.laenge("/x/0123456789ab.wav"), 61.5)
            abschrift.schneiden("/x/0123456789ab.wav", 29, 31)
            abschrift.tonspur("/x/0123456789ab.wav", "/y/0123456789ab.ogg.tmp", 61)
        self.assertEqual(len(seen), 3)
        for args in seen:
            self.assertIn(args[0], ("ffmpeg", "ffprobe"))
            i = args.index("-protocol_whitelist")
            self.assertEqual(args[i + 1], "file,pipe")
            self.assertTrue(all(not str(a).startswith(("http", "rtsp", "tcp", "udp")) for a in args))
            self.assertIn("file:/x/0123456789ab.wav", args)
        self.assertEqual(seen[1][seen[1].index("-t") + 1], "31.000")
        self.assertEqual(seen[1][seen[1].index("-ar") + 1], "16000")

    def test_real_ffmpeg_reads_the_length_and_cuts_a_piece(self):
        c, uid = self.fresh("Abschriftecht")
        buf = io.StringIO()
        with quiet(buf):
            r = self.upload(c, "memo.wav", wav(65))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["secs"], 65)
        path = os.path.join(documents.audio_dir(uid), r.json()["id"] + ".wav")
        piece = abschrift.schneiden(path, 29, 31)
        self.assertEqual(abschrift.family(piece), "wav")
        self.assertAlmostEqual((len(piece) - 44) / 32000, 31, delta=0.2)
        self.assertIn("abschrift: angenommen | 1 min |", buf.getvalue())


class Pieces(Base):
    def test_pages_are_start_seconds_and_where_says_the_time(self):
        self.assertEqual((documents.zeit(0), documents.zeit(750), documents.zeit(3750)), ("00:00", "12:30", "1:02:30"))
        c, uid = self.fresh("Abschriftzeit")
        doc = self.recording(c, uid, 75)
        ear = Ear(lambda k: ["Heute sprechen wir über Apfelbäume", "Dann kommt die Birnenernte", "Zuletzt die Kirschblüte"][k - 1])
        for _ in range(3):
            self.assertEqual(self.step(uid, ear), "abschrift")
        self.assertEqual(ear.calls, 3)
        d = self.doc(uid, doc)
        self.assertEqual((d["state"], d["heard"]), ("ready", 75))
        got = c.get(f"/api/profile/wissen/{doc}/text").json()
        self.assertEqual([p["page"] for p in got["parts"]], [0, 30, 60])
        self.assertEqual([p["at"] for p in got["parts"]], ["bei 00:00", "bei 00:30", "bei 01:00"])
        hits = documents.search(uid, "Birnenernte")
        self.assertEqual(hits[0]["page"], 30)
        self.assertEqual(wissen.where(hits[0]), "Aufnahme: Vortrag Wärmepumpe.wav, bei 00:30")
        r = c.post("/api/profile/wissen/search", json={"q": "Kirschblüte"}).json()["hits"][0]
        self.assertEqual((r["at"], r["audio"]), ("bei 01:00", True))

    def test_the_words_heard_twice_go(self):
        self.assertEqual(abschrift.trim_edge("wir sprechen über die Wärmepumpe", "die Wärmepumpe. Sie spart Strom"),
                         "Sie spart Strom")
        self.assertEqual(abschrift.trim_edge("das Ende.", "Ganz neu beginnt es"), "Ganz neu beginnt es")
        self.assertEqual(abschrift.trim_edge("", "Erstes Stück"), "Erstes Stück")
        c, uid = self.fresh("Abschriftrand")
        doc = self.recording(c, uid, 60)
        cuts = []
        say = {1: "Heute geht es um die Förderung der Wärmepumpe", 2: "der Wärmepumpe und um den Antrag"}
        self.step(uid, Ear(lambda k: say[k]), cut=lambda p, s, n: (cuts.append((s, n)), wav(1))[1])
        self.step(uid, Ear(lambda k: say[k + 1]), cut=lambda p, s, n: (cuts.append((s, n)), wav(1))[1])
        self.assertEqual(cuts, [(0, 30), (29, 31)])      # the second piece starts OVERLAP earlier
        text = " ".join(p["text"] for p in c.get(f"/api/profile/wissen/{doc}/text").json()["parts"])
        self.assertEqual(text, "Heute geht es um die Förderung der Wärmepumpe und um den Antrag")

    def test_only_in_quiet_minutes_and_in_the_chain_after_the_pages(self):
        k = list(wissen.KETTE)
        self.assertEqual(k.index("abschrift.due_once"), k.index("wissen.seiten_due") + 1)
        self.assertLess(k.index("abschrift.due_once"), k.index("wissen.steckbrief_due"))
        c, uid = self.fresh("Abschriftruhe")
        self.recording(c, uid, 40)
        ear = Ear()
        with mock.patch.object(abschrift, "hoeren", ear), mock.patch.object(wissen, "quiet", lambda: False), \
                mock.patch.object(abschrift.profiles, "user_ids", lambda: [uid]), quiet():
            self.assertIsNone(run(abschrift.due_once(NOW)))
        self.assertEqual(ear.calls, 0)

    def test_speech_cancels_a_piece_and_it_goes_on_at_the_same_piece(self):
        c, uid = self.fresh("Abschriftsprache")
        doc = self.recording(c, uid, 60)
        self.addCleanup(lambda: (vorrang._local.__setitem__(0, 0.0), os.utime(vorrang.MARK, (0, 0))))

        async def interrupted(wav_bytes, uid=None):
            vorrang.mark()                 # somebody starts to speak while the piece is being heard
            await asyncio.sleep(30)
            return "nie"
        buf = io.StringIO()
        with mock.patch.object(vorrang, "POLL", 0.01), mock.patch.object(vorrang, "GRACE", 20):
            self.assertEqual(self.step(uid, interrupted, buf=buf), "abschrift")
        self.assertIn("abschrift: abgebrochen | sprache | bei 0 s", buf.getvalue())
        self.assertEqual(self.doc(uid, doc)["heard"], 0)
        vorrang._local[0] = 0.0
        os.utime(vorrang.MARK, (0, 0))
        ear = Ear()
        self.step(uid, ear)
        self.assertEqual((ear.calls, self.doc(uid, doc)["heard"]), (1, 30))   # the same piece, now through

    def test_daily_limit_once_in_the_log_and_long_ones_only_after_long_ok(self):
        c, uid = self.fresh("Abschriftgrenze")
        helpers.set_config(doc_audio_day_min=10)
        self.recording(c, uid, 25 * 60)          # longer than LONG_S
        ear = Ear()
        self.assertIsNone(self.step(uid, ear, lang=False))
        self.assertEqual(ear.calls, 0)
        self.assertEqual(self.step(uid, ear, lang=True), "abschrift")
        self.assertEqual(ear.calls, 1)
        documents.count_today(uid, wissen.today(NOW), add=10 * 60 - 60, key="abschrift")
        buf = io.StringIO()
        self.assertEqual(self.step(uid, ear, buf=buf), "abschrift")          # the last 30 s of today
        self.assertIsNone(self.step(uid, ear, buf=buf))
        self.assertIsNone(self.step(uid, ear, buf=buf))
        self.assertEqual(ear.calls, 2)
        self.assertEqual(buf.getvalue().count("abschrift: grenze | 10 min"), 1)

    def test_missing_speech_recognition_is_not_tried_and_said_once(self):
        c, uid = self.fresh("Abschriftohr")
        self.recording(c, uid, 40)
        ear, buf = Ear(), io.StringIO()
        with mock.patch("dienstwacht.down", lambda sid: sid == "asr"):
            self.assertIsNone(self.step(uid, ear, buf=buf))
            abschrift._hold["asr"] = 0.0
            self.assertIsNone(self.step(uid, ear, buf=buf))
        self.assertEqual(ear.calls, 0)
        self.assertEqual(buf.getvalue().count("abschrift: asr fehlt | dienstwaechter"), 1)

        async def gone(wav_bytes, uid=None):
            import httpx
            raise httpx.ConnectError("refused")
        abschrift._hold["asr"] = 0.0
        self.step(uid, gone, buf=buf)
        self.assertIn("abschrift: asr fehlt | ConnectError | naechster versuch in 300 s", buf.getvalue())
        self.assertIsNone(self.step(uid, ear, now=NOW + 10))       # held, not asked again at once
        self.assertEqual(ear.calls, 0)

    def test_without_originals_the_file_goes_with_them_only_the_sound_track(self):
        c, uid = self.fresh("Abschriftende")
        doc = self.recording(c, uid, 20)
        self.step(uid, Ear())
        self.assertEqual(os.listdir(documents.audio_dir(uid)), [])
        d = self.doc(uid, doc)
        self.assertEqual((d["state"], d["file"]), ("ready", False))
        helpers.set_config(doc_originals=True)
        doc = self.recording(c, uid, 20)

        def track(path, dst, secs):
            with open(dst, "wb") as f:
                f.write(b"OggS" + b"\x00" * 100)
            return True
        with mock.patch.object(abschrift, "tonspur", track):
            self.step(uid, Ear())
        d = self.doc(uid, doc)
        self.assertEqual((d["state"], d["file"]), ("ready", True))
        self.assertEqual(os.listdir(documents.audio_dir(uid)), [])
        r = c.get(f"/api/profile/wissen/{doc}/file?view=1", headers={"Range": "bytes=0-9"})
        self.assertEqual(r.status_code, 206)                        # Safari plays only with ranges
        self.assertEqual(r.headers["content-type"], "audio/ogg")
        self.assertTrue(r.headers["content-disposition"].startswith("inline"))
        self.assertEqual(r.content, b"OggS" + b"\x00" * 6)

    def test_stop_keeps_what_is_written_and_drops_an_empty_one(self):
        c, uid = self.fresh("Abschriftstopp")
        doc = self.recording(c, uid, 90)
        self.step(uid, Ear())
        with quiet(buf := io.StringIO()):
            r = c.post(f"/api/profile/wissen/{doc}/abschrift/stop")
        self.assertEqual(r.json(), {"ok": True, "removed": False})
        d = self.doc(uid, doc)
        self.assertEqual(d["state"], "ready")
        self.assertIn("Abschrift abgebrochen bei 00:30", d["note"])
        self.assertEqual(os.listdir(documents.audio_dir(uid)), [])
        other = self.recording(c, uid, 90)
        with quiet(buf):
            self.assertEqual(c.post(f"/api/profile/wissen/{other}/abschrift/stop").json()["removed"], True)
            self.assertEqual(c.post(f"/api/profile/wissen/{other}/abschrift/stop").status_code, 404)
        self.assertFalse(any(x["id"] == other for x in documents.list_docs(uid)))
        stranger, _ = self.fresh("Abschriftfremd")
        third = self.recording(c, uid, 90)
        with quiet(buf):
            self.assertEqual(stranger.post(f"/api/profile/wissen/{third}/abschrift/stop").status_code, 404)
        self.assertIn("abschrift: stopp | behalten |", buf.getvalue())
        self.assertIn("abschrift: stopp | geloescht |", buf.getvalue())

    def test_deleting_takes_the_waiting_file(self):
        c, uid = self.fresh("Abschriftweg")
        doc = self.recording(c, uid, 90)
        self.assertEqual(c.delete(f"/api/profile/docs/{doc}").json()["removed"], True)
        self.assertEqual(os.listdir(documents.audio_dir(uid)), [])


class Asr(Base):
    def test_the_request_goes_last_with_the_key(self):
        sent = {}

        class Resp:
            status_code = 200
            elapsed = __import__("datetime").timedelta(seconds=1)

            def json(self):
                return {"text": " Hallo Welt ", "usage": {"seconds": 30}}

            def raise_for_status(self):
                pass

        async def post(self, url, **kw):
            sent.update(kw, url=url)
            return Resp()
        import httpx
        with mock.patch.object(httpx.AsyncClient, "post", post):
            self.assertEqual(run(abschrift.hoeren(b"RIFF", "u1")), "Hallo Welt")
        self.assertTrue(sent["url"].endswith("/v1/audio/transcriptions"))
        self.assertEqual(sent["headers"][common.STAGE_HEADER], "0")
        self.assertEqual(sent["headers"][common.STAGE_KEY_HEADER], common.stage_key())

    def test_lines_have_fixed_words_and_live_numbers(self):
        c, uid = self.fresh("Abschriftlog")
        self.recording(c, uid, 40, name="Geheimes Treffen.wav")
        buf = io.StringIO()
        self.step(uid, Ear(lambda k: "Das Passwort ist Zebrafink"), buf=buf)
        self.step(uid, Ear(), buf=buf)
        out = buf.getvalue()
        self.assertIn("abschrift: stueck | 30 s 26 zeichen |", out)
        self.assertIn("abschrift: fertig | 1 min 2 stuecke | tonspur nein |", out)
        for bad in ("Geheimes", "Zebrafink", "Passwort", uid):
            self.assertNotIn(bad, out)
        for line in out.splitlines():
            self.assertTrue(line.startswith("abschrift: ") or line.startswith("vorrang: "), line)
        x = abschrift.for_live()
        self.assertTrue(x["on"])
        self.assertTrue(all(isinstance(v, (int, bool)) for v in x.values()))   # numbers only, never a name
        self.assertIn("abschrift", live.TARGETS)
        import logfilter
        self.assertTrue(any(a == "wissen" and __import__("re").search(rx, "abschrift: stueck") for a, rx in logfilter.AREAS))

    def test_the_waiting_folder_is_registered(self):
        import dateien
        self.assertIn("docs/audio-wait/", [d.name for d in dateien.DATEIEN])
        self.assertEqual(documents.audio_dir("u1"), os.path.join(documents._dir("u1"), "audio-wait"))
