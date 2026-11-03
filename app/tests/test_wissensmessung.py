"""Wissen messen (wissensmessung.py, Wissenskarte Stufe 4): a small synthetic run in its own measuring process brings
every measured field of every part, leaves nothing behind (no run folder, no throwaway profile), keeps numbers only
(result, file, journal lines, Live); a real profile is only read (its database stays byte for byte); speech stops a
run, one run at a time, the throwaway profile is only built in the measuring process inside a run folder; the endpoint
is admin only with the code level, validated, and refuses a second start. No test looks at absolute times or the
clock; runs in a copy with app/ only."""
import contextlib
import fcntl
import hashlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
import wissensmessung as wm  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
# the fields every run must bring per part (the part's dict; the times as _p50_ms, _p95_ms, _max_ms, _n)
FELDER = {"documents": ("dokumente", "stuecke", "vektoren", "matrix_mb", "matrix_ms", "ram_vorher_mb", "ram_matrix_mb", "ram_mb"),
          "wissensbuch": ("seiten", "saetze", "dokumente_eingearbeitet", "seiten_je_dok", "seiten_grenze", "ram_mb"),
          "wissenskarte": ("seiten", "punkte", "knoten", "kanten", "stellen", "kanten_je_dok", "kanten_je_dok_max",
                           "punkte_je_dok", "kanten_grenze", "punkte_grenze", "ram_mb")}
ZEITEN = {"documents": ("suche", "suche_karte"), "wissensbuch": ("liste",),
          "wissenskarte": ("view", "view_um", "rund_um", "weg", "liste")}
WORTE = {"wissen:", "messung", "gestartet", "synth", "profil", "teil", "fertig", "abgebrochen", "engpass", "keiner",
         "s", "ms", "mb", "p95", "ram", "matrix", "dokumente", "stuecke", "seiten", "punkte", "kanten", "|"} | set(wm.STATUS)


def still():
    """The measuring process's own state folder: no other test's speech mark stops it."""
    return {"SPEECH_SPARK_STATE": tempfile.mkdtemp(prefix="wm-state-")}


def strings(x, path=""):
    """(key path, value) of every string in a JSON value."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from strings(v, path + "/" + k)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v, path)
    elif isinstance(x, str):
        yield path, x


class Synthetisch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cls.res = wm.lauf("synth", 200, sprache=lambda: False, kind_env=still())
        cls.lines = [x for x in out.getvalue().splitlines() if x.startswith("wissen:")]

    def test_every_field_of_every_part(self):
        self.assertEqual(self.res["status"], "fertig", self.res)
        self.assertEqual(set(self.res["teile"]), set(wm.MESSTEILE))
        for teil, felder in FELDER.items():
            got = self.res["teile"][teil]
            for f in felder:
                self.assertIn(f, got, (teil, f))
            for z in ZEITEN[teil]:
                for end in ("_p50_ms", "_p95_ms", "_max_ms"):
                    self.assertIsInstance(got[z + end], (int, float), (teil, z))
                self.assertGreater(got[z + "_n"], 0, (teil, z))
                self.assertLessEqual(got[z + "_p50_ms"], got[z + "_p95_ms"])
                self.assertLessEqual(got[z + "_p95_ms"], got[z + "_max_ms"])
        d = self.res["teile"]["documents"]
        self.assertEqual(d["dokumente"], 200)
        self.assertEqual(d["vektoren"], d["stuecke"])
        self.assertGreater(d["matrix_mb"], 0)
        for k in ("ram_start_mb", "ram_ende_mb", "dauer_s"):
            self.assertIsInstance(self.res[k], (int, float), k)
        self.assertEqual(set(self.res["engpaesse"]), {"seiten", "kanten", "punkte"})
        for v in self.res["engpaesse"].values():
            self.assertEqual(set(v), {"grenze", "jetzt", "bedarf", "voll"})
            self.assertLessEqual(v["jetzt"], v["grenze"])          # the limits of the real code held while building
            self.assertGreaterEqual(v["bedarf"], v["jetzt"])
        self.assertIn("bedarf_kanten", self.res["aufbau"])

    def test_nothing_is_left(self):
        self.assertEqual([x for x in os.listdir(wm.TMP) if x != ".lock"], [])
        self.assertIsNone(wm._proc)
        self.assertFalse(wm._stand["laeuft"])

    def test_numbers_only(self):
        with open(wm.FILE, encoding="utf-8") as f:
            kept = json.load(f)
        self.assertEqual(kept[0]["id"], self.res["id"])
        for path, s in list(strings(kept)) + list(strings(self.res)):
            key = path.rsplit("/", 1)[-1]
            self.assertIn(key, ("id", "status", "art", "profil", "version", "fehler"), path)
            self.assertRegex(s, r"^[\w.-]{0,40}$", path)
        self.assertEqual(wm.laeufe()[0]["teile"], self.res["teile"])
        self.assertTrue(self.lines)
        allowed = WORTE | set(wm.MESSTEILE) | {z for zs in ZEITEN.values() for z in zs}
        for line in self.lines:
            for tok in line.split():
                self.assertTrue(re.fullmatch(r"[\d.]+", tok) or tok in allowed, (tok, line))
        self.assertEqual(sum(1 for x in self.lines if " teil " in x), len(wm.MESSTEILE))   # one line per part

    def test_live_numbers_only(self):
        v = wm.for_live()
        self.assertTrue(v["on"])
        sub = wm.live_sub(v)
        self.assertIn("Dokumente", sub)
        self.assertIn("wmessen", live.TARGETS)
        self.assertEqual(live.TARGETS["wmessen"][2], "spark")
        self.assertNotRegex(sub, r"[a-z]{3,}[A-Z]")     # no made-up title or name


class Regeln(unittest.TestCase):
    def test_speech_stops_the_run(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            res = wm.lauf("synth", 100, sprache=lambda: True, kind_env=still())
        self.assertEqual(res["status"], "sprache")
        self.assertNotIn("teile", res)
        self.assertIn("wissen: messung abgebrochen | sprache", out.getvalue())
        self.assertEqual([x for x in os.listdir(wm.TMP) if x != ".lock"], [])

    def test_one_run_at_a_time(self):
        os.makedirs(wm.TMP, exist_ok=True)
        fd = os.open(os.path.join(wm.TMP, ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(wm.Abbruch) as e:
                wm.lauf("synth", 100, sprache=lambda: False, kind_env=still())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertEqual(str(e.exception), "laeuft")
        self.assertIn("wissen: messung abgelehnt | laeuft", out.getvalue())

    def test_the_throwaway_profile_only_in_its_process_and_folder(self):
        self.assertFalse(wm._KIND[0])
        with self.assertRaises(RuntimeError):
            wm.teil_documents(tempfile.mkdtemp(prefix="lauf-"), 10)
        with mock.patch.object(wm, "_KIND", [True]), self.assertRaises(RuntimeError):
            wm._im_ordner(os.path.dirname(documents.db_path("x")))     # a profile folder is never one

    def test_parts_keep_numbers_only(self):
        self.assertEqual(wm._zahlen({"a_ms": 1.23456, "name": "Vertrag", "Bad Key": 1, "teil": {"n": 2, "t": "x"},
                                     "ok": True, "nan": float("nan")}),
                         {"a_ms": 1.235, "teil": {"n": 2}, "ok": True})


class Profil(unittest.TestCase):
    def test_a_real_profile_is_only_read(self):
        r = ADMIN.post("/api/admin/profiles", json={"name": "Wmessung", "pin": "2468"})
        self.assertIn(r.status_code, (200, 409), r.text)
        uid = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == "Wmessung")
        for i in range(3):
            documents.add(uid, f"Wmessung Notiz {i}.txt", b"x", text=f"Die Heizung im Keller Nummer {i} braucht im "
                          "Herbst neues Wasser und einen Blick auf den Druck.")
        path = documents.db_path(uid)
        before = hashlib.sha256(open(path, "rb").read()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            res = wm.lauf("profil", 0, uid, sprache=lambda: False, kind_env=still())
        self.assertEqual(res["status"], "fertig", res)
        self.assertEqual(res["teile"]["documents"]["dokumente"], 3)
        self.assertEqual(hashlib.sha256(open(path, "rb").read()).hexdigest(), before)
        text = json.dumps(res, ensure_ascii=False)
        for word in ("Wmessung", "Heizung", "Keller", "Notiz"):
            self.assertNotIn(word, text)
        with contextlib.redirect_stdout(io.StringIO()):
            empty = wm.lauf("profil", 0, "keinprofil", sprache=lambda: False, kind_env=still())
        self.assertEqual(empty["status"], "leer")


class Endpunkt(unittest.TestCase):
    def setUp(self):
        wm._letzter[0] = 0.0
        self.addCleanup(wm._letzter.__setitem__, 0, 0.0)

    def test_admin_only_and_listed_with_its_code_level(self):
        self.assertIn(("POST", "/api/admin/wissensmessung"), stufen.LIST)
        guest = TestClient(panel.app)
        self.assertIn(guest.get("/api/admin/wissensmessung").status_code, (401, 403))
        self.assertIn(guest.post("/api/admin/wissensmessung", json={"art": "synth", "anzahl": 100}).status_code, (401, 403))
        d = ADMIN.get("/api/admin/wissensmessung").json()
        self.assertEqual((d["standard"], d["min"], d["max"]), (wm.ANZAHL, wm.ANZAHL_MIN, wm.ANZAHL_MAX))

    def test_validated_and_one_start(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for bad in ({"art": "synth", "anzahl": 10}, {"art": "synth", "anzahl": "5000"}, {"art": "x"},
                        {"art": "synth", "anzahl": True}, {"art": "profil", "profil": "../x"}):
                self.assertIn(ADMIN.post("/api/admin/wissensmessung", json=bad).status_code, (400, 404), bad)
            self.assertEqual(ADMIN.post("/api/admin/wissensmessung", content=b"{" + b" " * 2000 + b"}",
                                        headers={"Content-Type": "application/json"}).status_code, 413)
            for k in [k for k in guard._rate if k[0] == "wmessen"]:     # the refusals above counted against the limit
                guard._rate.pop(k, None)
            calls = []
            with mock.patch.object(wm, "lauf", lambda *a, **k: calls.append(a)):
                r = ADMIN.post("/api/admin/wissensmessung", json={"art": "synth", "anzahl": 100})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertTrue(helpers.until(lambda: calls), "the run never started")
                self.assertEqual(calls[0][:2], ("synth", 100))
                self.assertTrue(helpers.until(lambda: not wm._stand["laeuft"]), "the run never ended")
                again = ADMIN.post("/api/admin/wissensmessung", json={"art": "synth", "anzahl": 100})
                self.assertEqual(again.status_code, 429)                 # at most every PAUSE_S seconds
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
