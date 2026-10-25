"""KI-Dungeon-Master: Ablage der Runden (dungeon_ablage.py, Punkt 14 of the review of 2026-10-24, Dominik „alles
umsetzten“: „Eine Datei je Runde mit Zwischenspeicher, eine kurze Antwort „nichts neu“ beim Nachfragen, Spiel-Skripte
erst beim Öffnen laden“).

- One file per round; the old file with every round inside is split once; the shared values stay in the old file.
- A read opens only files whose change stamp moved and fixes old rounds once; a write puts only changed rounds and
  removes the files of rounds gone; runde(rid) and rids_von(uid) read without the other rounds.
- The poll answers {"neu": false} while the seat's stand is the same: the round file, who is online, the reading,
  the pictures, who types; while the Dungeon Master answers and every STAND_S seconds the whole view again.
- The page has only dungeonlader.js; it names every other dungeon script.

No wall clock: times are given.
"""
import glob
import json
import os
import re
import unittest
from unittest import mock

from tests import test_dungeon as T
import dungeon  # noqa: E402
import dungeon_ablage as ablage  # noqa: E402

STATIC = os.path.join(os.path.dirname(dungeon.__file__), "static")


class Ablage(T.Base):
    def test_the_old_file_is_split_once(self):
        rd = {"owner": "u1", "plaetze": {"p1": {"uid": "u2"}}, "status": "laeuft", "log": []}
        ablage.vergessen()
        dungeon.write_json(dungeon.FILE, {"runden": {"r0123456789": rd, "kaputt": {}}, "bilder": {"tag": "x"}})
        d = dungeon._read()
        self.assertEqual(d["runden"]["r0123456789"]["owner"], "u1")
        self.assertEqual(d["bilder"], {"tag": "x"})
        self.assertEqual(dungeon.read_json(dungeon.FILE, {}), {"bilder": {"tag": "x"}})      # the old file keeps the rest
        self.assertTrue(os.path.exists(ablage.datei("r0123456789")))
        self.assertEqual(os.listdir(ablage.DIR), ["r0123456789.json"])                       # a bad id never gets a file
        self.assertEqual(ablage.rids_von("u2"), ["r0123456789"])
        self.assertEqual(ablage.rids_von("u1"), ["r0123456789"])
        self.assertEqual(ablage.rids_von("u3"), [])
        self.assertEqual(ablage.runde("r0123456789")["status"], "laeuft")
        self.assertIsNone(ablage.runde("../dungeon-runden"))

    def test_only_changed_files_are_read_and_written(self):
        a, b = self.new_round()["rid"], self.new_round(titel="Zwei")["rid"]
        dungeon._read()
        st = {x: ablage.stand(x) for x in (a, b)}
        fixed, reads = [], []
        real = ablage.read_json

        def count(path, default=None):
            reads.append(os.path.basename(path))
            return real(path, default)
        with mock.patch.object(ablage, "read_json", count), mock.patch.object(dungeon, "_fix", lambda rd: fixed.append(1)):
            d = dungeon._read()
            self.assertEqual((reads, fixed), ([], []))                                       # nothing changed: from the cache
            d["runden"][a]["titel"] = "Neu"
            d["runden"][a]["plaetze"]["x"] = {}                                              # a copy: the cache stays as it was
            self.assertNotIn("x", dungeon._read()["runden"][a]["plaetze"])
            with dungeon._lock:
                d = dungeon._read()
                d["runden"][a]["titel"] = "Neu"
                dungeon._write(d)
            self.assertNotEqual(ablage.stand(a), st[a])
            self.assertEqual(ablage.stand(b), st[b])                                         # the other round is not written
            self.assertEqual(dungeon._read()["runden"][a]["titel"], "Neu")
            self.assertEqual((reads, fixed), ([], [1]))                                      # its own write: fixed once, no read
            other = dungeon.read_json(ablage.datei(b), {})
            other["titel"] = "Von außen"
            dungeon.write_json(ablage.datei(b), other)                                       # changed elsewhere: read once, fixed once
            self.assertEqual(dungeon._read()["runden"][b]["titel"], "Von außen")
            self.assertEqual(dungeon._read()["runden"][b]["titel"], "Von außen")
            self.assertEqual((reads, len(fixed)), ([b + ".json"], 2))
            with dungeon._lock:
                d = dungeon._read()
                d["runden"].pop(b)                                                           # a round gone: its file too
                dungeon._write(d)
        self.assertFalse(os.path.exists(ablage.datei(b)))
        self.assertEqual(set(dungeon._read()["runden"]), {a})

    def test_nothing_new_while_the_stand_holds(self):
        v = self.new_round()
        rid, pid = v["rid"], v["pid"]
        dungeon._running.discard(rid)                                       # the opening is told (spawn is a fake here)
        url = f"/api/profile/dungeon/{rid}"
        s = self.c.get(url).json()["stand"]
        self.assertEqual(self.c.get(url, params={"stand": s}).json(), {"neu": False, "stand": s})
        self.assertEqual(self.c.get(url, params={"stand": "x" * 16}).json()["rid"], rid)        # another stand: the view
        self.assertGreaterEqual(dungeon.for_live()["nichts_neu"], 1)
        self.assertEqual(self.c.post(f"{url}/aktion", json={"text": "Ich lausche an der Tür.", "zug": 1}).status_code, 200)
        v2 = self.c.get(url, params={"stand": s}).json()                                        # the round changed
        self.assertNotEqual(v2["stand"], s)
        self.assertTrue(v2["meine_aktion"])
        dungeon._running.discard(rid)                                       # the turn closed: its narration is a fake here
        t = 1000 * dungeon.STAND_S
        k = dungeon.view_stand(rid, pid, t)
        self.assertEqual(dungeon.view_stand(rid, pid, t + dungeon.STAND_S - 1), k)
        self.assertNotEqual(dungeon.view_stand(rid, pid, t + dungeon.STAND_S), k)                # every STAND_S seconds anew
        self.assertNotEqual(dungeon.view_stand(rid, "p_andere", t), k)                          # per seat
        dungeon._running.add(rid)                                                               # the Dungeon Master answers
        self.addCleanup(dungeon._running.discard, rid)
        self.assertNotEqual(dungeon.view_stand(rid, pid, t), dungeon.view_stand(rid, pid, t + 0.5))
        dungeon._running.discard(rid)
        code, gp = self.guest(rid)
        g = self.v.post("/api/dungeon/lage", json={"code": code}).json()
        self.assertEqual(self.v.post("/api/dungeon/lage", json={"code": code, "stand": g["stand"]}).json(), {"neu": False, "stand": g["stand"]})
        self.assertEqual(self.v.post("/api/dungeon/lage", json={"code": "x" * 32, "stand": g["stand"]}).status_code, 400)   # the code first

    def test_a_poll_with_nothing_due_reads_one_round(self):
        v = self.new_round()
        n = []
        real = dungeon._read
        with mock.patch.object(dungeon, "_read", lambda: n.append(1) or real()):
            self.assertFalse(dungeon.maybe_close(v["rid"]))
            self.assertEqual(dungeon._seat_uid(v["rid"], self.uid), v["pid"])
        self.assertEqual(n, [])
        self.assertRaises(LookupError, dungeon._seat_uid, "r0000000000", self.uid)

    def test_the_page_loads_the_game_on_first_use(self):
        html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        self.assertEqual(re.findall(r'src="/static/js/(dungeon[\w-]*\.js)"', html), ["dungeonlader.js"])
        lader = open(os.path.join(STATIC, "js", "dungeonlader.js"), encoding="utf-8").read()
        names = re.findall(r"'([\w-]+\.js)'", re.search(r"const DM_SKRIPTE=\[([^\]]*)\]", lader).group(1))
        self.assertEqual(names[0], "dungeon.js")                                               # the core first
        have = {os.path.basename(f) for f in glob.glob(os.path.join(STATIC, "js", "dungeon*.js"))} - {"dungeonlader.js"}
        self.assertEqual(set(names), have)                                                     # every game script, once
        self.assertEqual(len(names), len(set(names)))
        for f in ("dmStart", "dmOpen", "dmHash"):                                               # what start.js and base.js call
            self.assertIn(f"window.{f}=", lader)
        self.assertIn("encodeURIComponent(SPARK_VER)", lader)


if __name__ == "__main__":
    unittest.main()
