"""Alle meine Daten herunterladen (meinedaten.py, plan nutzerwissen Punkt 5, Dominik 2026-10-29): no switch (right of
access, Richtlinie Teil 3), every time a fresh code or passkey (without a second step the PIN, from the iPhone app only
with the step), JE_STUNDE per hour, GRENZE bytes, a one-time pickup code for the own profile only (ABHOLEN_S
seconds, only its hash kept, never in the access log); what goes in only from the file register (export=), sealed
files opened, no secret, voiceprint or supply of a foreign server, from chats only the own messages; logs and Live
with numbers only; guests nothing. Times are given where a rule depends on them, never read from the clock."""
import contextlib
import io
import json
import logging
import os
import re
import time
import unittest
import zipfile
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chats  # noqa: E402
import core  # noqa: E402
import dateien  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import iphone  # noqa: E402
import logfilter  # noqa: E402
import meinedaten  # noqa: E402
import mfa  # noqa: E402
import profiles  # noqa: E402
import stufen  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PIN = "4826"
T0 = 1_760_000_000
NIE = ("voice.json", "mfa.json", "chatkeys.json", "telefon.json", "speaker-code.json", "mail.json", "homeassistant.json",
       "telegram.json", "mail-vorrat.bin", "wetter-vorrat.bin", "pakete-vorrat.bin", "fuerdich-vorrat.bin",
       "agent-pending.json", "push.json")


def profile(name, pin=PIN):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def journal(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


def raw(uid, name, data):
    path = profiles._path(uid, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())


class Base(unittest.TestCase):
    def setUp(self):
        guard.reset()
        for k in [k for k in guard._rate if str(k[0]).startswith("export")]:
            guard._rate.pop(k, None)
        meinedaten._stunde.clear()
        meinedaten._abholen.clear()
        meinedaten._baut.clear()
        if os.path.isdir(meinedaten.TMP):
            for n in os.listdir(meinedaten.TMP):
                os.remove(os.path.join(meinedaten.TMP, n))

    def export(self, c, **body):
        return c.post("/api/profile/export", json=dict({"pin": PIN}, **body))

    def fetch(self, c, **body):
        r = self.export(c, **body)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        g = c.get(d["url"])
        self.assertEqual(g.status_code, 200, g.text)
        z = zipfile.ZipFile(io.BytesIO(g.content))
        return d, g, z, {n: z.read(n) for n in z.namelist()}


class Register(unittest.TestCase):
    def test_every_profile_file_says_whether_it_goes_out(self):
        for d in dateien.DATEIEN:
            if d.ort != "profil":
                continue
            self.assertTrue(d.export == dateien.JA or (isinstance(d.export, tuple) and len(d.export) == 2
                                                         and all(d.export)), d.name)

    def test_areas_and_sealed_files_go_out(self):
        for d in dateien.DATEIEN:
            if d.ort == "profil" and (d.bereich or d.siegel):
                self.assertEqual(d.export, dateien.JA, d.name)
                self.assertIn(d.name, dateien.EXPORT)

    def test_secrets_voiceprint_queues_and_supplies_never(self):
        for n in NIE:
            self.assertNotIn(n, dateien.EXPORT, n)
            self.assertIn(n, dateien.DRAUSSEN_DATEIEN, n)
            de, en = dateien.DRAUSSEN_DATEIEN[n]
            self.assertTrue(de and en and de != en, n)
        self.assertNotIn("users.json", dateien.EXPORT)
        self.assertEqual(dateien.DRAUSSEN_DATEIEN["voice.json"], dateien.DRAUSSEN["Stimmabdruck"])

    def test_a_file_sealed_its_own_way_has_its_reader(self):
        # a file the register protects (not siegel=) or one outside the profile folder is opened by its module, never raw
        for n, d in dateien.EXPORT.items():
            if (d.schutz and not d.siegel) or d.ort != "profil":
                self.assertIn(n, meinedaten.LESER, n)
        for n in meinedaten.LESER:
            self.assertIn(n, dateien.EXPORT, n)

    def test_one_source_the_register(self):
        c, uid = profile("Medaone")
        profiles.write_own(uid, "memory.json", [{"id": "a1", "text": "Mag Tee.", "created": T0}])
        self.assertIn("memory.json", {x["name"] for x in meinedaten.plan(uid)})
        with mock.patch.object(dateien, "EXPORT", {}):
            self.assertEqual(meinedaten.plan(uid), [])

    def test_no_switch_and_the_level(self):
        self.assertNotIn("meinedaten", features.BY_KEY)
        lvl = stufen.LIST[("POST", "/api/profile/export")]
        self.assertEqual(lvl[0], stufen.PROTECT)
        self.assertEqual(meinedaten.GRENZE, 2 * 1024 ** 3)
        self.assertEqual((meinedaten.JE_STUNDE, meinedaten.ABHOLEN_S, meinedaten.CODE_BYTES), (3, 600, 16))

    def test_the_app_reaches_only_its_paths(self):
        rx = [re.compile(p) for m, p in iphone.AREAS["app_security"] if "GET" in m]
        code = "A" * len(__import__("secrets").token_urlsafe(meinedaten.CODE_BYTES))
        self.assertTrue(any(r.fullmatch("/api/profile/export/" + code) for r in rx))
        self.assertFalse(any(r.fullmatch("/api/profile/export/../settings") for r in rx))
        self.assertFalse(any(r.fullmatch("/api/profile/export/" + code + "x") for r in rx))


class Zip(Base):
    def test_what_is_in_and_what_stays_out(self):
        c, uid = profile("Medatwo")
        profiles.write_own(uid, "memory.json", [{"id": "b1", "text": "Fahre gern Rad.", "created": T0}])
        raw(uid, "voice.json", "STIMMABDRUCK-XYZ")
        raw(uid, "mail-vorrat.bin", "VORRAT-XYZ")
        raw(uid, "telegram.json", json.dumps({"token": "GEHEIM-XYZ"}))
        raw(uid, "weather.json", json.dumps({"ort": "Bonn", "schluessel": "enc1:GEHEIMWERT", "liste": ["g1:x", "ok"]}))
        d, g, z, files = self.fetch(c)
        self.assertEqual(g.headers["cache-control"], "no-store")
        self.assertIn("application/zip", g.headers["content-type"])
        self.assertIn("LIESMICH.txt", files)
        self.assertIn("uebersicht.json", files)
        self.assertEqual(json.loads(files["daten/memory.json"])[0]["text"], "Fahre gern Rad.")
        self.assertEqual(json.loads(files["daten/weather.json"]), {"ort": "Bonn", "liste": ["ok"]})
        blob = b"".join(files.values())
        for bad in (b"STIMMABDRUCK-XYZ", b"VORRAT-XYZ", b"GEHEIM-XYZ", b"enc1:", b"GEHEIMWERT", b"secret-admin"):
            self.assertNotIn(bad, blob, bad)
        self.assertFalse([n for n in files if n.endswith(("voice.json", ".bin", "telegram.json"))])
        readme = files["LIESMICH.txt"].decode()
        self.assertIn("Was draußen bleibt und warum", readme)
        self.assertIn("What stays out and why", readme)
        self.assertIn("voice.json", readme)
        self.assertIn(dateien.DRAUSSEN["Stimmabdruck"][0], readme)
        self.assertIn(dateien.DRAUSSEN["Stimmabdruck"][1], readme)
        self.assertEqual(json.loads(files["uebersicht.json"])["dateien"], d["dateien"])
        self.assertTrue(all(n in ("LIESMICH.txt", "uebersicht.json") or n.startswith("daten/") for n in files))
        self.assertTrue(all(".." not in n and not n.startswith("/") for n in files))

    def test_sealed_on_the_disk_opened_in_the_zip(self):
        c, uid = profile("Medathree")
        profiles.write_own(uid, "memory.json", [{"id": "c1", "text": "Wohnt am See.", "created": T0}])
        with open(profiles._path(uid, "memory.json"), "rb") as f:
            disk = f.read()
        if dateien.EXPORT["memory.json"].siegel and profiles.own_bytes(uid, "memory.json") != disk:
            self.assertNotIn(b"Wohnt am See.", disk)
        _, _, _, files = self.fetch(c)
        self.assertIn("Wohnt am See.", files["daten/memory.json"].decode())

    def test_areas_left_out(self):
        c, uid = profile("Medafour")
        profiles.write_own(uid, "memory.json", [{"id": "d1", "text": "Spielt Cello.", "created": T0}])
        _, _, _, files = self.fetch(c, ohne=["gedaechtnis", "gibt-es-nicht"])
        self.assertNotIn("daten/memory.json", files)
        self.assertEqual(json.loads(files["uebersicht.json"])["abgewaehlt"], ["gedaechtnis"])

    def test_no_link_is_followed(self):
        c, uid = profile("Medafive")
        raw(uid, "voice.json", "STIMME-LINK")
        folder = profiles._path(uid, "erstellt")
        os.makedirs(folder, exist_ok=True)
        link = os.path.join(folder, "bild.txt")
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(profiles._path(uid, "voice.json"), link)
        _, _, _, files = self.fetch(c)
        self.assertNotIn("daten/erstellt/bild.txt", files)
        self.assertNotIn(b"STIMME-LINK", b"".join(files.values()))

    def test_chats_only_the_own_messages(self):
        helpers.set_config(chats=True)
        try:
            a, ua = profile("Medasix")
            b, _ = profile("Medaseven")
            r = a.post("/api/chats/open", json={"to": b.get("/api/whoami").json()["profile"]["id"]})
            self.assertEqual(r.status_code, 200, r.text)
            cid = r.json()["id"]
            self.assertEqual(a.post("/api/chats/send", json={"id": cid, "text": "Von mir selbst"}).status_code, 200)
            self.assertEqual(b.post("/api/chats/send", json={"id": cid, "text": "Vom anderen geheim"}).status_code, 200)
            own = chats.own_messages(ua)
            self.assertEqual([x.get("text") for x in own if x["chat"] == cid], ["Von mir selbst"])
            self.assertTrue(all(set(x) <= {"chat", "art", "t", "text", "medium"} for x in own))
            _, _, _, files = self.fetch(a)
            blob = b"".join(files.values()).decode("utf-8", "replace")
            self.assertIn("Von mir selbst", blob)
            self.assertNotIn("Vom anderen geheim", blob)
            self.assertNotIn("Medaseven", blob)
        finally:
            helpers.set_config(chats=False)


class Rules(Base):
    def test_the_pin_without_a_second_step(self):
        c, _ = profile("Medaeight")
        self.assertEqual(c.post("/api/profile/export", json={}).status_code, 401)
        r, log = journal(c.post, "/api/profile/export", json={"pin": "0000"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("meinedaten: abgelehnt grund=pin", log)
        self.assertEqual(self.export(c).status_code, 200)

    def test_a_fresh_code_every_time(self):
        c, uid = profile("Medanine")
        real = (mfa.enabled, mfa.verify)
        mfa.enabled = lambda who: who == uid
        mfa.verify = lambda who, code: who == uid and code == "123456"
        try:
            self.assertTrue(c.get("/api/profile/export").json()["code"])
            self.assertEqual(c.post("/api/profile/export", json={}).status_code, 428)
            self.assertEqual(c.post("/api/profile/export", json={"pin": PIN}).status_code, 428)   # the PIN is no code
            r, log = journal(c.post, "/api/profile/export", json={}, headers={core.CODE_HEADER: "654321"})
            self.assertEqual(r.status_code, 428)
            self.assertIn("meinedaten: abgelehnt grund=code", log)
            ok = c.post("/api/profile/export", json={}, headers={core.CODE_HEADER: "123456"})
            self.assertEqual(ok.status_code, 200, ok.text)
            # right after it, the next one asks again: no window counts
            self.assertEqual(c.post("/api/profile/export", json={}).status_code, 428)
        finally:
            mfa.enabled, mfa.verify = real

    def test_the_app_only_with_the_second_step(self):
        prof = {"id": "medaapp0001", "name": "Medaapp"}
        req = mock.Mock(scope={"speech_app_area": "app_security"})
        with mock.patch.object(mfa, "enabled", lambda who: False):
            with self.assertRaises(HTTPException) as e:
                journal(meinedaten._bestaetigt, req, prof, {"pin": PIN})
        self.assertEqual(e.exception.status_code, 403)

    def test_three_per_hour(self):
        c, _ = profile("Medaten")
        for _ in range(meinedaten.JE_STUNDE):
            self.assertEqual(self.export(c).status_code, 200)
        r = self.export(c)
        self.assertEqual(r.status_code, 429)
        self.assertIn(str(meinedaten.JE_STUNDE), r.json()["detail"])

    def test_the_hour_by_given_times(self):
        q = meinedaten._stunde["medahour"]
        q.extend([T0, T0 + 10, T0 + 20])
        self.assertFalse(meinedaten._stunde_frei("medahour", T0 + 30))
        self.assertFalse(meinedaten._stunde_frei("medahour", T0 + 3600))
        self.assertTrue(meinedaten._stunde_frei("medahour", T0 + 3601))
        self.assertEqual(len(q), 2)

    def test_one_at_a_time(self):
        c, _ = profile("Medaeleven")
        meinedaten._baut.add("jemand")
        self.assertEqual(self.export(c).status_code, 409)

    def test_too_big(self):
        c, uid = profile("Medatwelve")
        profiles.write_own(uid, "memory.json", [{"id": "e1", "text": "x" * 200, "created": T0}])
        with mock.patch.object(meinedaten, "GRENZE", 10):
            r = self.export(c)
        self.assertEqual(r.status_code, 413)
        self.assertIn("gedaechtnis", json.loads(r.headers["x-speech-export"]))
        self.assertEqual(os.listdir(meinedaten.TMP) if os.path.isdir(meinedaten.TMP) else [], [])

    def test_body_limit(self):
        c, _ = profile("Medathirteen")
        self.assertEqual(c.post("/api/profile/export", json={"pin": PIN, "x": "y" * 2000}).status_code, 413)

    def test_guests_get_nothing(self):
        g = TestClient(panel.app)
        self.assertIn(g.get("/api/profile/export").status_code, (401, 403))
        self.assertIn(g.post("/api/profile/export", json={"pin": PIN}).status_code, (401, 403))
        self.assertIn(g.get("/api/profile/export/" + "A" * 22).status_code, (401, 403))

    def test_a_device_key_gets_nothing(self):
        c, _ = profile("Medafourteen")
        r = c.post("/api/profile/export", json={"pin": PIN}, headers={profiles.DEVICE_HEADER: "x" * 40})
        self.assertIn(r.status_code, (401, 403))


class Pickup(Base):
    def test_once_and_only_for_its_profile(self):
        a, _ = profile("Medafifteen")
        b, _ = profile("Medasixteen")
        d = self.export(a).json()
        self.assertEqual(len(d["code"]), 22)
        self.assertEqual(d["gilt_s"], meinedaten.ABHOLEN_S)
        self.assertNotIn(d["code"], json.dumps(list(meinedaten._abholen)))     # only the hash is kept
        self.assertEqual(b.get(d["url"]).status_code, 404)                     # another profile: nothing, and it stays
        path = next(iter(meinedaten._abholen.values()))["path"]
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
        self.assertEqual(a.get(d["url"]).status_code, 200)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(a.get(d["url"]).status_code, 404)
        self.assertEqual(a.get("/api/profile/export/" + "A" * 22).status_code, 404)

    def test_runs_out(self):
        a, _ = profile("Medaseventeen")
        d = self.export(a).json()
        h, x = next(iter(meinedaten._abholen.items()))
        x["bis"] = time.time() - 1
        self.assertEqual(a.get(d["url"]).status_code, 404)
        self.assertFalse(os.path.exists(x["path"]))

    def test_sweep_by_given_times(self):
        os.makedirs(meinedaten.TMP, exist_ok=True)
        old, kept = os.path.join(meinedaten.TMP, "export-alt.zip"), os.path.join(meinedaten.TMP, "export-neu.zip")
        for p in (old, kept):
            open(p, "wb").close()
        os.utime(old, (T0, T0))
        os.utime(kept, (T0 + 1000, T0 + 1000))
        meinedaten._abholen["h"] = {"uid": "u", "path": kept, "bis": T0 + 2000, "bytes": 0}
        _, log = journal(meinedaten.sweep, T0 + 1500)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(kept))
        _, log = journal(meinedaten.sweep, T0 + 2001)
        self.assertFalse(os.path.exists(kept))
        self.assertEqual(log.strip(), "meinedaten: abgelaufen | dateien=1")

    def test_the_access_log_never_holds_the_code(self):
        rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                ("1.2.3.4:5", "GET", "/api/profile/export/SECRETCODE123456789012", "1.1", 200), None)
        for f in logging.getLogger("uvicorn.access").filters:
            f.filter(rec)
        self.assertNotIn("SECRETCODE", rec.getMessage())
        self.assertIn("/api/profile/export/…", rec.getMessage())
        other = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                  ("1.2.3.4:5", "GET", "/api/profile/export", "1.1", 200), None)
        meinedaten.OhneCode().filter(other)
        self.assertIn('"GET /api/profile/export HTTP', other.getMessage())


class LogsAndLive(Base):
    def test_lines_with_numbers_only(self):
        c, uid = profile("Medaeighteen")
        profiles.write_own(uid, "memory.json", [{"id": "f1", "text": "Liest Krimis.", "created": T0}])
        (_, _, _, files), log = journal(self.fetch, c)
        lines = [x for x in log.splitlines() if x.startswith("meinedaten:")]
        self.assertTrue(any(re.fullmatch(r"meinedaten: export Profil \w{4} \| dateien=\d+ mb=\d+ ms=\d+", x) for x in lines),
                        lines)
        self.assertTrue(any(re.fullmatch(r"meinedaten: abgeholt \| mb=\d+ \| Profil \w{4}", x) for x in lines), lines)
        for x in lines:
            self.assertNotIn("Krimis", x)
            self.assertNotIn("Medaeighteen", x)
            self.assertNotIn("memory", x)
            self.assertEqual(next(k for k, rx in logfilter._AREAS if rx.search(x)), "speicher")

    def test_live_numbers_only(self):
        c, _ = profile("Medanineteen")
        self.fetch(c)
        live = meinedaten.for_live()
        self.assertEqual(set(live), {"gebaut", "abgeholt", "abgelehnt", "abgelaufen", "offen", "baut"})
        self.assertTrue(all(isinstance(v, int) for v in live.values()))
        self.assertGreaterEqual(live["gebaut"], 1)
        self.assertEqual(live["baut"], 0)

    def test_the_admins_log_counts_only(self):
        self.assertIn("profile_export", guard.LIVE_WORDS)
        c, _ = profile("Medatwenty")
        with mock.patch.object(guard, "log") as gl:
            self.fetch(c)
        calls = [kw for args, kw in gl.call_args_list if args == ("profile_export",)]
        self.assertEqual(len(calls), 1)
        kw = calls[0]
        self.assertEqual(set(kw), {"user", "files", "mb"})
        self.assertTrue(isinstance(kw["files"], int) and isinstance(kw["mb"], int))


if __name__ == "__main__":
    unittest.main()
