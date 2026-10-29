"""Versiegeln im Ruhezustand (plan nutzerwissen, Stufe 4): memory, conversations and what the Spark learned about a
person are read and written only through profiles.read_own / write_own / drop_own, never with open() or
profiles._write on their path, and a file with siegel= in the register (dateien.SIEGEL) lies sealed whole on the disk:
AES-256-GCM with the key of its own purpose, the profile and the name as associated data, a fresh nonce per write. A
file that does not open (other key, other profile, changed) is set aside and never overwritten; the one-time sealing
makes a backup first, checks every file it sealed and touches nothing twice. Times are never read."""
import ast
import contextlib
import io
import json
import os
import stat
import tarfile
import tempfile
import unittest

from tests import helpers

helpers.start()
import backup  # noqa: E402
import dateien  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import siegel  # noqa: E402
import speicher  # noqa: E402
import vault  # noqa: E402
import vorrat  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
HELPERS = {"read_own", "write_own", "drop_own"}
# moved to the helpers ahead of their seal (V01.1.250): siegel= in dateien.py follows in V01.1.252
VORAB = {"interessen.json", "tagebuch.json", "zuordnungen.json", "learned.json", "memory-ask.json"}
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SECRET = "Sgl-Geheimwort-7731"
CRYPTO = unittest.skipUnless(vault.available(), "needs cryptography")


def own_files():
    return set(dateien.SIEGEL) | VORAB


def direct_uses(names, folder=PANEL):
    """(file, line, name) of every string constant naming one of names outside a call of the helpers."""
    out = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".py") or fn == "dateien.py":
            continue
        with open(os.path.join(folder, fn), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        ok = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and ast.unparse(n.func).split(".")[-1] in HELPERS:
                ok.update(id(a) for a in n.args[1:2])
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
                ok.add(id(n.value))          # a docstring
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and n.value in names and id(n) not in ok:
                out.append((fn, n.lineno, n.value))
    return out


def profile(name, pin="7319"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def raw(uid, name):
    with open(profiles._path(uid, name), "rb") as f:
        return f.read()


def journal(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


@contextlib.contextmanager
def other_key():
    """As on another Spark: the purpose key of the profile data is a different one (profiles forgets what it opened)."""
    saved = dict(vorrat._vkeys)
    vorrat._vkeys["profildaten"] = os.urandom(32)
    profiles._own.clear()
    try:
        yield
    finally:
        vorrat._vkeys.clear()
        vorrat._vkeys.update(saved)
        profiles._own.clear()


class OnlyThroughTheHelpers(unittest.TestCase):
    def test_no_module_opens_an_own_file_itself(self):
        self.assertEqual(direct_uses(own_files()), [],
                         "read or write this file through profiles.read_own / write_own / drop_own (plan nutzerwissen, Stufe 4)")

    def test_the_scan_finds_a_direct_open(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x.py"), "w") as f:
                f.write('"""memory.json in a docstring is fine."""\nimport profiles\n'
                        'a = profiles.read_own(uid, "memory.json", [])\n'
                        'with open(profiles._path(uid, "memory.json")) as f:\n    pass\n')
            self.assertEqual(direct_uses({"memory.json"}, d), [("x.py", 4, "memory.json")])

    def test_the_register_is_the_one_list(self):
        self.assertEqual(dateien.SIEGEL, frozenset({"memory.json", "convos.json", "toollog.json", "room-history.json"}))
        for d in dateien.DATEIEN:
            if d.siegel:
                self.assertEqual(d.ort, "profil", d.name)
                self.assertEqual(d.schutz, dateien.SIEGEL_SCHUTZ, d.name)   # Zustand → Technik says „versiegelt“
        self.assertIn("*.unlesbar", dateien.LOCAL)                          # set aside: never into a copy


class Helpers(unittest.TestCase):
    UID = "u_5e9e1000aa01"

    def setUp(self):
        os.makedirs(profiles._path(self.UID), exist_ok=True)
        for n in ("memory.json", "tagebuch.json"):
            self.addCleanup(profiles.drop_own, self.UID, n)

    def test_round_trip_only_for_the_service_user(self):
        profiles.write_own(self.UID, "memory.json", [{"id": "x1", "text": "Ein Satz mit ä."}])
        self.assertEqual(profiles.read_own(self.UID, "memory.json", []), [{"id": "x1", "text": "Ein Satz mit ä."}])
        self.assertEqual(stat.S_IMODE(os.stat(profiles._path(self.UID, "memory.json")).st_mode), 0o600)

    def test_missing_or_broken_gives_the_default(self):
        self.assertEqual(profiles.read_own(self.UID, "memory.json", []), [])
        with open(profiles._path(self.UID, "memory.json"), "w") as f:
            f.write("[{")
        self.assertEqual(profiles.read_own(self.UID, "memory.json", {"d": 1}), {"d": 1})

    def test_drop(self):
        profiles.write_own(self.UID, "memory.json", [])
        self.assertTrue(profiles.drop_own(self.UID, "memory.json"))
        self.assertFalse(profiles.drop_own(self.UID, "memory.json"))

    def test_plain_files_of_older_versions_still_open(self):
        with open(profiles._path(self.UID, "memory.json"), "w") as f:
            json.dump([{"id": "p1", "text": "Alt und offen."}], f)
        self.assertEqual(profiles.read_own(self.UID, "memory.json", []), [{"id": "p1", "text": "Alt und offen."}])

    def test_a_file_without_siegel_stays_plain(self):
        profiles.write_own(self.UID, "tagebuch.json", {"items": []})
        self.assertEqual(json.loads(raw(self.UID, "tagebuch.json")), {"items": []})


@CRYPTO
class Sealed(unittest.TestCase):
    """What lies on the disk: no plain text, bound to the profile and the name, a fresh nonce for every write."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Sgl Ada")
        cls.c2, cls.uid2 = profile("Sgl Bert")

    def setUp(self):
        for u in (self.uid, self.uid2):
            for n in dateien.SIEGEL:
                profiles.drop_own(u, n)
                for a in profiles.aside_names(u, n):
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(profiles._path(u, a))
        profiles._own_blocked.clear()

    def test_no_plain_text_on_the_disk(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": SECRET}])
        profiles.save_convo(self.uid, {"id": "c1", "title": SECRET, "msgs": [{"role": "user", "content": SECRET}]})
        for n in ("memory.json", "convos.json"):
            b = raw(self.uid, n)
            self.assertNotIn(SECRET.encode(), b, n)
            self.assertTrue(profiles.is_sealed(b) and b.startswith(siegel.HEAD), n)
            self.assertEqual(stat.S_IMODE(os.stat(profiles._path(self.uid, n)).st_mode), 0o600)
        self.assertEqual(profiles.memory(self.uid)[0]["text"], SECRET)
        self.assertEqual(profiles.convos(self.uid)[0]["title"], SECRET)

    def test_a_fresh_nonce_for_every_write(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": "gleich"}])
        a = json.loads(raw(self.uid, "memory.json"))["data"]
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": "gleich"}])
        b = json.loads(raw(self.uid, "memory.json"))["data"]
        self.assertNotEqual(a, b)
        self.assertNotEqual(a[:24], b[:24])          # "G1" + nonce differ

    def test_its_own_key_per_purpose(self):
        self.assertNotEqual(vorrat.key("profildaten"), vorrat.key("vorrat"))
        self.assertIsNone(vorrat.key("unbekannt"))

    def test_copied_into_another_profile_it_does_not_open_and_is_set_aside(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": SECRET}])
        sealed = raw(self.uid, "memory.json")
        with open(profiles._path(self.uid2, "memory.json"), "wb") as f:
            f.write(sealed)
        got, log = journal(profiles.read_own, self.uid2, "memory.json", [])
        self.assertEqual(got, [])
        self.assertFalse(os.path.exists(profiles._path(self.uid2, "memory.json")))
        self.assertEqual(raw(self.uid2, "memory.json.unlesbar"), sealed)          # never overwritten, kept as it was
        self.assertIn("profiles: unlesbar Profil", log)
        self.assertIn("datei=memory.json beiseite=1", log)
        self.assertNotIn(SECRET, log)
        self.assertNotIn(self.uid2, log)

    def test_renamed_inside_the_profile_it_does_not_open(self):
        profiles.write_own(self.uid, "toollog.json", [{"t": 1, "q": SECRET}])
        os.replace(profiles._path(self.uid, "toollog.json"), profiles._path(self.uid, "room-history.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(profiles.read_own(self.uid, "room-history.json", []), [])
        self.assertTrue(os.path.exists(profiles._path(self.uid, "room-history.json.unlesbar")))

    def test_a_changed_file_is_set_aside_not_overwritten(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": SECRET}])
        d = json.loads(raw(self.uid, "memory.json"))
        d["data"] = d["data"][:-8] + ("A" if d["data"][-8] != "A" else "B") + d["data"][-7:]
        with open(profiles._path(self.uid, "memory.json"), "w") as f:
            json.dump(d, f)
        bad = raw(self.uid, "memory.json")
        with contextlib.redirect_stdout(io.StringIO()):
            ok = profiles.write_own(self.uid, "memory.json", [{"id": "f2", "text": "neu"}])
        self.assertTrue(ok)
        self.assertEqual(raw(self.uid, "memory.json.unlesbar"), bad)               # the changed one, untouched
        self.assertEqual(profiles.memory(self.uid), [{"id": "f2", "text": "neu"}])

    def test_with_another_key_nothing_is_lost(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": "vom alten Spark"}])
        old = raw(self.uid, "memory.json")
        with other_key(), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(profiles.memory(self.uid), [])                        # the profile starts empty
            profiles.write_own(self.uid, "memory.json", [{"id": "f2", "text": "auf dem neuen"}])
            self.assertEqual(siegel.view(self.uid), {"aside": 1, "back": 0, "weg": "Einstellungen → Sicherung"})
            self.assertEqual(siegel.einlesen(self.uid), (0, 1))                   # the key is not back: nothing
        self.assertEqual(raw(self.uid, "memory.json.unlesbar"), old)

    def test_the_second_aside_takes_the_next_place_and_a_full_row_blocks_the_write(self):
        for i in range(profiles.ASIDE_MAX):
            with open(profiles._path(self.uid, profiles.aside_names(self.uid, "memory.json")[i]), "w") as f:
                f.write("{}")
        profiles.write_own(self.uid, "memory.json", [{"id": "f1", "text": "x"}])
        before = raw(self.uid, "memory.json")
        with other_key():
            got, log = journal(profiles.write_own, self.uid, "memory.json", [{"id": "f2", "text": "y"}])
            self.assertFalse(got)                                                  # nowhere to put it: no write
        self.assertEqual(raw(self.uid, "memory.json"), before)
        self.assertIn("beiseite=0 grund=voll", log)
        self.assertIn("profiles: nicht geschrieben", log)
        for a in profiles.aside_names(self.uid, "memory.json"):
            os.remove(profiles._path(self.uid, a))


@CRYPTO
class BackAgain(unittest.TestCase):
    """„Wieder einlesen“: the key is back (the move backup), what was set aside is merged in, nothing current goes."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Sgl Cora")

    def test_read_in_again_merges_and_keeps_what_came_since(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "a1", "text": "vom alten Spark", "created": 1}])
        profiles.save_convo(self.uid, {"id": "alt", "title": "Alt", "updated": 1, "msgs": [{"role": "user", "content": "x"}]})
        with other_key(), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(profiles.memory(self.uid), [])
            self.assertEqual(profiles.convos(self.uid), [])
            profiles.write_own(self.uid, "memory.json", [{"id": "n1", "text": "neu dazu", "created": 2}])
            new_key = vorrat._vkeys["profildaten"]
        # the move backup brought the old key back: the new file is now the one that does not open
        profiles._own.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            r = self.c.get("/api/profile/memory").json()["siegel"]
        self.assertEqual((r["aside"], r["back"]), (3, 2))                         # n1 lies aside too, under the other key
        res = self.c.post("/api/profile/memory/einlesen", json={})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual((res.json()["back"], res.json()["left"]), (2, 1))
        self.assertEqual([f["id"] for f in profiles.memory(self.uid)], ["a1"])
        self.assertEqual([c["id"] for c in profiles.convos(self.uid)], ["alt"])
        self.assertEqual(siegel.aside(self.uid), [("memory.json", "memory.json.2.unlesbar")])
        # the copy aside opens later (here: sealed again under this key): merged with what is there, nothing goes
        saved = dict(vorrat._vkeys)
        try:
            vorrat._vkeys["profildaten"] = new_key
            plain = profiles.open_sealed(self.uid, "memory.json", raw(self.uid, "memory.json.2.unlesbar"))
        finally:
            vorrat._vkeys.clear()
            vorrat._vkeys.update(saved)
        sealed = vorrat.seal(plain, f"{self.uid}/memory.json", "profildaten")
        with open(profiles._path(self.uid, "memory.json.2.unlesbar"), "w") as f:
            json.dump({"v": 1, "data": sealed}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(siegel.einlesen(self.uid), (1, 0))
        self.assertEqual(sorted(f["id"] for f in profiles.memory(self.uid)), ["a1", "n1"])
        self.assertEqual(siegel.aside(self.uid), [])

    def test_guests_never(self):
        self.assertIn(TestClient(panel.app).post("/api/profile/memory/einlesen", json={}).status_code, (401, 403))

    def test_the_endpoint_checks_size(self):
        r = self.c.post("/api/profile/memory/einlesen", content=b"{" + b" " * 4096 + b"}",
                        headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)


@CRYPTO
class Migration(unittest.TestCase):
    """The one-time sealing: a backup first, every file opened again and compared, nothing twice."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Sgl Dora")

    def plain(self):
        for n, d in (("memory.json", [{"id": "m1", "text": SECRET}]), ("convos.json", [{"id": "c1", "msgs": [], "updated": 1}])):
            with open(profiles._path(self.uid, n), "w") as f:
                json.dump(d, f)
        profiles._own.clear()

    def test_backup_first_then_sealed_and_compared_then_nothing_twice(self):
        self.plain()
        made = []
        res, log = journal(siegel.migrate, made.append)
        self.assertEqual(made, ["vor-siegel"])
        self.assertGreaterEqual(res["dateien"], 2)
        self.assertEqual(res["fehler"], 0)
        self.assertRegex(log, r"profiles: versiegelt \| profile=\d+ dateien=\d+ fehler=0")
        self.assertNotIn(SECRET, log)
        for n in ("memory.json", "convos.json"):
            self.assertTrue(profiles.is_sealed(raw(self.uid, n)), n)
        self.assertEqual(profiles.memory(self.uid), [{"id": "m1", "text": SECRET}])
        self.assertEqual(siegel.plain_files(self.uid), [])
        made.clear()
        res = siegel.migrate(made.append)                                          # idempotent
        self.assertEqual((made, res["dateien"]), ([], 0))
        self.assertTrue(backup.NAME.fullmatch("speech-spark-20261029-101010-" + siegel.WHY + ".tar.gz"))

    def test_without_the_backup_nothing_changes(self):
        self.plain()

        def fails(why):
            raise OSError("disk full")
        res, log = journal(siegel.migrate, fails)
        self.assertEqual(res["grund"], "sicherung")
        self.assertIn("profiles: versiegeln abgebrochen | grund=sicherung", log)
        self.assertFalse(profiles.is_sealed(raw(self.uid, "memory.json")))
        siegel.migrate(lambda why: None)

    def test_a_file_that_does_not_compare_goes_back_plain(self):
        self.plain()
        real = profiles.own_bytes
        profiles.own_bytes = lambda uid, name: b"[]" if uid == self.uid and name == "memory.json" else real(uid, name)
        try:
            res, _ = journal(siegel.migrate, lambda why: None)
        finally:
            profiles.own_bytes = real
        self.assertGreaterEqual(res["fehler"], 1)
        self.assertEqual(json.loads(raw(self.uid, "memory.json")), [{"id": "m1", "text": SECRET}])   # plain again, whole
        siegel.migrate(lambda why: None)

    def test_without_the_key_nothing_is_sealed(self):
        self.plain()
        saved = vorrat.key
        vorrat.key = lambda zweck="vorrat": None
        try:
            res, log = journal(siegel.migrate, lambda why: self.fail("no backup without a key"))
            profiles.write_own(self.uid, "toollog.json", [{"t": 1}])
        finally:
            vorrat.key = saved
        self.assertEqual(res.get("grund"), "schluessel")
        self.assertIn("profiles: nicht versiegelt | grund=schluessel", log)
        self.assertEqual(json.loads(raw(self.uid, "toollog.json")), [{"t": 1}])     # plain rather than lost
        siegel.migrate(lambda why: None)


@CRYPTO
class Around(unittest.TestCase):
    """Backup on the same Spark, the own storage copy, Live and the hints: numbers only."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Sgl Emil")

    def test_a_backup_opens_on_this_spark_and_aside_elsewhere(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "b1", "text": SECRET}])
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            backup._add_dir(tar, profiles._path(self.uid), "users")
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            packed = tar.extractfile("users/memory.json").read()
        self.assertNotIn(SECRET.encode(), packed)                                  # sealed in the backup
        profiles.drop_own(self.uid, "memory.json")
        with open(profiles._path(self.uid, "memory.json"), "wb") as f:
            f.write(packed)                                                        # restored on this Spark
        self.assertEqual(profiles.memory(self.uid)[0]["text"], SECRET)
        with other_key(), contextlib.redirect_stdout(io.StringIO()):               # restored on another one
            self.assertEqual(profiles.memory(self.uid), [])
        self.assertEqual(raw(self.uid, "memory.json.unlesbar"), packed)
        os.remove(profiles._path(self.uid, "memory.json.unlesbar"))
        vorrat._vkeys["profildaten"] = b"x" * 32
        profiles._own["x"] = ((0, 0, 0), b"[]", 0)
        backup._forget_cached()
        self.assertEqual((vorrat._vkeys, profiles._own), ({}, {}))                 # read again after a restore

    def test_the_own_storage_copy_takes_it_unsealed_and_never_empty(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "s1", "text": SECRET}])
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "plain")
            speicher._snapshot(profiles._path(self.uid, "memory.json"), dst, (self.uid, "memory.json"))
            with open(dst) as f:
                self.assertEqual(json.load(f), [{"id": "s1", "text": SECRET}])
            with other_key(), self.assertRaises(profiles.Unreadable):
                speicher._snapshot(profiles._path(self.uid, "memory.json"), dst, (self.uid, "memory.json"))

    def test_live_and_the_hint_carry_numbers_only(self):
        profiles.write_own(self.uid, "memory.json", [{"id": "l1", "text": SECRET}])
        siegel._live[1] = None
        c = siegel.for_live()
        self.assertGreaterEqual(c["sealed"], 1)
        self.assertNotIn(SECRET, json.dumps(c))
        with open(profiles._path(self.uid, "memory.json.unlesbar"), "w") as f:
            f.write("{}")
        try:
            siegel._live[1] = None
            a = [x for x in siegel.alerts() if x["kind"] == "siegel"]
            self.assertEqual(len(a), 1)
            self.assertEqual(a[0]["go"], "Einstellungen → Sicherung")
            self.assertNotIn(self.uid, a[0]["text"])
            import live
            node = next(x for x in live.snapshot()["targets"] if x["id"] == "ged")
            self.assertIn("unlesbar beiseite", node["sub"])
            self.assertNotIn(SECRET, json.dumps(node))
        finally:
            os.remove(profiles._path(self.uid, "memory.json.unlesbar"))
            siegel._live[1] = None


if __name__ == "__main__":
    unittest.main()
