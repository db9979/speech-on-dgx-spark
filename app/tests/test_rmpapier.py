"""Designed sheets with boxes, folders by kind and tidying up on the reMarkable (rmpapier.py).

Against the fake reMarkable cloud of test_remarkable: the sheets have the size of the device's screen (three models),
the boxes are read back from the strokes geometrically (ticked, filled in = taken back, unclear, empty), a sheet is
only ever read when the Spark made it and recorded its boxes, "Kann weg" puts it into the trash (into "Archiv" when
there is handwriting on it), a reminder's box marks it done and filling it in brings it back, a sheet with marks is
never filled with new text, folders by kind, sorting in and tidying up after 7 / 30 days. All off by default
(admin switch plus profile switch), never guests. No test depends on the clock: times are passed in.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import hashlib
import io
import json
import re
import time
import unittest
import uuid

from tests import helpers
from tests.test_remarkable import CLOUD, Base, profile, run, si  # noqa: F401

import features  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import remarkable  # noqa: E402
import rmpapier  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

if si is not None:
    from rmscene import scene_stream as ss
    from rmscene.crdt_sequence import CrdtSequenceItem
    from rmscene.tagged_block_common import CrdtId, LwwValue


def page_mm(m, lines_mm, size=None, tool=None):
    """A v6 page file with strokes given in mm on the sheet, written in the device's units (and its paper size)."""
    size = size or m["px"]
    k = m["mm"][0] / size[0]
    blocks = list(ss.simple_text_document(" "))
    blocks.insert(2, ss.SceneInfo(current_layer=LwwValue(CrdtId(0, 0), CrdtId(0, 0)), background_visible=LwwValue(CrdtId(0, 0), True),
                                  root_document_visible=LwwValue(CrdtId(0, 0), True), paper_size=tuple(size)))
    for n, ln in enumerate(lines_mm):
        pts = [si.Point(x=(x - m["mm"][0] / 2) / k, y=y / k, speed=1, direction=1, width=3, pressure=90) for x, y in ln]
        line = si.Line(color=si.PenColor.BLACK, tool=tool or si.Pen.BALLPOINT_1, thickness_scale=1.0,
                       starting_length=0.0, points=pts)
        blocks.append(ss.SceneLineItemBlock(parent_id=CrdtId(0, 11), item=CrdtSequenceItem(
            item_id=CrdtId(1, 30 + n), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=line)))
    b = io.BytesIO()
    ss.write_blocks(b, blocks, options={"version": "3.1"})
    return b.getvalue()


def dense(a, b, step=0.3):
    """The points of a straight stroke from a to b (as a pen gives them)."""
    n = max(1, int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 / step))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def tick(f):
    x, y = f["x"], f["y"]
    return [dense((x + 1, y + 3), (x + 2.5, y + 5)) + dense((x + 2.5, y + 5), (x + 5, y + 1))[1:]]


def filled(f):
    x, y, w, h = f["x"], f["y"], f["w"], f["h"]
    out, i = [], 0.0
    while i <= h:
        out.append(dense((x, y + i), (x + w, y + i)))
        i += 0.4
    return out


def nearby(f):
    cy = f["y"] + f["h"] / 2
    return [dense((f["x"] - 5.5, cy), (f["x"] - 2.5, cy))]


def writing(m):
    """Handwriting in the middle of the sheet, far from every box."""
    w, h = m["mm"]
    return [dense((w * 0.2, h * 0.6 + i * 4), (w * 0.7, h * 0.6 + i * 4)) for i in range(3)]


def ink(did, pages):
    """The person writes on the document: page files (and their order) are added, the rest stays."""
    c = CLOUD[0]
    rows = remarkable.parse_index(c.files[c.entries[did][0]])
    keep = [(e["hash"], e["id"], e["size"]) for e in rows if not e["id"].endswith((".rm", ".content"))]
    ids = [str(uuid.UUID(int=900 + i)) for i in range(len(pages))]
    content = {"fileType": "pdf", "formatVersion": 2,
               "cPages": {"pages": [{"id": p, "idx": {"value": f"b{i:03d}"}} for i, p in enumerate(ids)]}}
    files = [(".content", json.dumps(content).encode())] + [(f"/{p}.rm", data) for p, data in zip(ids, pages) if data]
    for suffix, data in files:
        keep.append((c.put(data), did + suffix, len(data)))
    keep.sort(key=lambda r: r[1])
    c.files[hashlib.sha256(b"".join(bytes.fromhex(h) for h, _, _ in keep)).hexdigest()] = \
        ("3\n" + "".join(f"{h}:0:{fid}:0:{s}\n" for h, fid, s in keep)).encode()
    dh = hashlib.sha256(b"".join(bytes.fromhex(h) for h, _, _ in keep)).hexdigest()
    c.entries[did] = (dh, len(keep), sum(s for _, _, s in keep))
    c.commit()


def lib(uid):
    return run(remarkable.refresh_library(uid))


def where(uid, did):
    items = lib(uid)
    return remarkable.path_of(items, items[did]["parent"])


class Paper(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(remarkable_send=True, remarkable_paper=True)

    def tearDown(self):
        super().tearDown()
        helpers.set_config(remarkable_paper=False)

    def on(self, name, model="move", folders=True, tidy=False):
        c, uid = self.paired(name)
        r = c.put("/api/profile/settings", json={"rm_send": True, "rm_paper": True, "rm_folders": folders,
                                                 "rm_tidy": tidy, "rm_model": model})
        self.assertEqual(r.status_code, 200, r.text)
        return c, uid

    def sheet(self, uid, todo=(), art="morgen"):
        m = rmpapier.model(rmpapier.model_key(uid))
        built = rmpapier.build_morning(m, "Morgenblatt Montag", "13. Oktober", "## Wetter\nSonnig.", list(todo))
        r = run(rmpapier.place(uid, art, "Morgenblatt Montag", built, "morgen", auto=False))
        return r["id"], m, remarkable.load(uid)["papers"][r["id"]]


@unittest.skipIf(si is None, "rmscene missing")
class Switches(Paper):
    def test_off_by_default_admin_and_profile_needed_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["remarkable_paper"], False)
        for k in ("rm_paper", "rm_folders", "rm_tidy"):
            self.assertIs(profiles.SETTINGS[k][0], False, k)
        self.assertEqual(profiles.SETTINGS["rm_model"][0], "auto")
        self.assertNotIn("rmpapier", features.DEFAULT_ON)
        self.assertIn("remarkable_send", features.chain_switches("rmpapier"))
        c, uid = self.paired("Ppoff")
        c.put("/api/profile/settings", json={"rm_send": True})
        self.assertFalse(rmpapier.paper_on(uid) or rmpapier.folders_on(uid))
        self.assertEqual(c.post("/api/profile/remarkable/papier/abgleich").status_code, 403)
        self.assertEqual(c.post("/api/profile/remarkable/papier/einsortieren").status_code, 403)
        c.put("/api/profile/settings", json={"rm_paper": True, "rm_folders": True})
        self.assertTrue(rmpapier.paper_on(uid) and rmpapier.folders_on(uid))
        helpers.set_config(remarkable_paper=False)
        self.assertFalse(rmpapier.paper_on(uid))
        self.assertEqual(c.post("/api/profile/remarkable/papier/abgleich").status_code, 403)
        helpers.set_config(remarkable_paper=True, remarkable_send=False)      # builds on "Aufs reMarkable schicken"
        self.assertFalse(rmpapier.paper_on(uid) or rmpapier.folders_on(uid))
        helpers.set_config(remarkable_send=True)
        self.assertFalse(rmpapier.paper_on(""))
        g = TestClient(panel.app)
        for method, path in (("get", "/api/profile/remarkable/papier"), ("post", "/api/profile/remarkable/papier/abgleich"),
                             ("post", "/api/profile/remarkable/papier/einsortieren"),
                             ("post", "/api/profile/remarkable/papier/zurueck"),
                             ("get", f"/api/profile/remarkable/papier/{uuid.UUID(int=5)}/0.png")):
            r = getattr(g, method)(path, **({"json": {}} if method == "post" else {}))
            self.assertIn(r.status_code, (401, 403), path)

    def test_undo_takes_only_known_names(self):
        c, uid = self.on("Ppundo")
        for body in ({}, {"id": "x", "n": "weg"}, {"id": str(uuid.UUID(int=7)), "n": "rm -rf"},
                     {"id": str(uuid.UUID(int=7)), "n": "rem:XYZ"}):
            self.assertEqual(c.post("/api/profile/remarkable/papier/zurueck", json=body).status_code, 400, body)
        self.assertEqual(c.post("/api/profile/remarkable/papier/zurueck",
                                json={"id": str(uuid.UUID(int=7)), "n": "weg"}).status_code, 404)


class Sheets(unittest.TestCase):
    def test_every_model_gets_its_own_page_and_boxes_on_it(self):
        for key, want in (("rm2", (157.8, 210.4)), ("pro", (179.7, 239.6)), ("move", (91.8, 163.2))):
            m = rmpapier.model(key)
            self.assertEqual(tuple(m["mm"]), want, key)
            pdf, fields, pages = rmpapier.build_morning(m, "Morgenblatt", "Montag", "## Wetter\nSonnig.\n- Regenjacke",
                                                       [{"id": f"{i:08x}", "text": f"Punkt {i}", "at": "09:00"} for i in range(5)])
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertGreaterEqual(pages, 2)                                      # a lined page for notes
            box = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", pdf)
            self.assertAlmostEqual(float(box.group(1)) / 72 * 25.4, want[0], delta=0.3)
            self.assertAlmostEqual(float(box.group(2)) / 72 * 25.4, want[1], delta=0.3)
            names = [f["n"] for f in fields]
            self.assertEqual(names[0], "weg")
            self.assertEqual(names[1:], [f"rem:{i:08x}" for i in range(5)])
            weg = fields[0]
            self.assertGreater(weg["x"], want[0] / 2)                              # top right on page 1
            self.assertLess(weg["y"], 30)
            for f in fields:
                self.assertTrue(0 < f["x"] and f["x"] + f["w"] < want[0] and 0 < f["y"] and f["y"] + f["h"] < want[1], (key, f))
            ys = sorted(f["y"] for f in fields if f["k"] == "erledigt")
            self.assertTrue(all(b - a >= rmpapier.BOX + 2 * rmpapier.TOL for a, b in zip(ys, ys[1:])), key)

    def test_detect_and_text_sheet(self):
        self.assertEqual(rmpapier.detect([954, 1696]), "move")
        self.assertEqual(rmpapier.detect((1620, 2160)), "pro")
        self.assertEqual(rmpapier.detect((1404, 1872)), "rm2")
        self.assertIsNone(rmpapier.detect((1000, 1000)))
        self.assertIsNone(rmpapier.detect(None))
        self.assertEqual(rmpapier.model("nonsense")["key"], "rm2")
        pdf, fields, pages = rmpapier.build_text(rmpapier.model("pro"), "Antwort", "Was ist ein Kolibri?",
                                                 "## Kurz\nEin **kleiner** Vogel.\n- schnell\n- bunt\n\n" + "Mehr Text. " * 400)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(pages, 1)
        self.assertEqual([f["n"] for f in fields], ["weg"])

    def test_bold_lines_of_the_briefing_become_headings(self):
        self.assertEqual(rmpapier.heads("**Termine**\n- 9 Uhr\nEin **fettes** Wort"), "## Termine\n- 9 Uhr\nEin **fettes** Wort")
        pdf, fields, pages = rmpapier.build_morning(rmpapier.model("move"), "Morgenblatt", "", "**Termine**\n- 9 Uhr", [])
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_boxes_are_judged_by_their_ink(self):
        f = {"n": "a", "k": "erledigt", "p": 0, "x": 40.0, "y": 60.0, "w": rmpapier.BOX, "h": rmpapier.BOX}
        self.assertEqual(rmpapier.judge([], f), "leer")
        self.assertEqual(rmpapier.judge(tick(f), f), "an")
        x = [dense((f["x"] + 0.5, f["y"] + 0.5), (f["x"] + 5.5, f["y"] + 5.5)),
             dense((f["x"] + 5.5, f["y"] + 0.5), (f["x"] + 0.5, f["y"] + 5.5))]
        self.assertEqual(rmpapier.judge(x, f), "an")                               # a cross counts as ticked
        self.assertEqual(rmpapier.judge(filled(f), f), "zurück")
        self.assertEqual(rmpapier.judge(nearby(f), f), "unklar")                   # beside it: asked, not guessed
        g = dict(f, n="b", y=f["y"] + 12)
        self.assertEqual(rmpapier.judge(tick(f), g), "leer")                       # the box below stays empty
        far = [dense((5, 150), (80, 150))]
        self.assertEqual(rmpapier.judge(far, f), "leer")
        states, other = rmpapier.evaluate([f, g], {0: tick(f) + far})
        self.assertEqual(states, {"a": "an", "b": "leer"})
        self.assertGreater(other, rmpapier.NOTES_MM)

    @unittest.skipIf(si is None, "rmscene missing")
    def test_strokes_land_where_they_were_drawn_on_every_model(self):
        for key in rmpapier.MODELS:
            m = rmpapier.model(key)
            spot = [(30.0, 50.0), (31.0, 52.0)]
            size, lines = rmpapier.strokes(page_mm(m, [spot]))
            self.assertEqual(rmpapier.detect(size), key)
            got = rmpapier.to_mm(lines, size, m)[0]
            for a, b in zip(got, spot):
                self.assertAlmostEqual(a[0], b[0], delta=0.05)
                self.assertAlmostEqual(a[1], b[1], delta=0.05)
        m = rmpapier.model("rm2")
        size, lines = rmpapier.strokes(page_mm(m, [spot], tool=si.Pen.HIGHLIGHTER_1))
        self.assertEqual(lines, [])                                                # highlighter is no answer
        with self.assertRaises(ValueError):
            rmpapier.strokes(b"reMarkable .lines file, version=5          ")

    @unittest.skipIf(si is None, "rmscene missing")
    def test_calibration_from_four_crosses(self):
        m = rmpapier.model("move")
        pdf, fields, pages = rmpapier.build_calibration(m)
        targets = [f for f in fields if f["k"] == "ziel"]
        self.assertEqual(len(targets), 4)
        # this device places strokes 1.5 mm further right and 2 % lower than the plain mapping says
        def cross(f):
            cx, cy = f["x"] + f["w"] / 2, f["y"] + f["h"] / 2
            return [dense((cx - 1.5, cy - 1.5), (cx + 1.5, cy + 1.5)), dense((cx + 1.5, cy - 1.5), (cx - 1.5, cy + 1.5))]
        drawn = [[((x - 1.5), y / 1.02) for x, y in ln] for f in targets for ln in cross(f)]
        size, raw = rmpapier.strokes(page_mm(m, drawn))
        got = rmpapier.fit(fields, {0: raw}, size, m)
        self.assertIsNotNone(got)
        f = targets[3]
        mid = rmpapier.to_mm([[raw[-1][len(raw[-1]) // 2]]], size, m, got)[0][0]
        self.assertAlmostEqual(mid[0], f["x"] + f["w"] / 2, delta=0.6)
        self.assertAlmostEqual(mid[1], f["y"] + f["h"] / 2, delta=0.6)
        size, raw = rmpapier.strokes(page_mm(m, [ln for f in targets[:3] for ln in cross(f)]))
        self.assertIsNone(rmpapier.fit(fields, {0: raw}, size, m))               # a target without a cross: no guess

    def test_control_picture(self):
        paper = {"mm": [91.8, 163.2], "r": {"weg": "an"},
                 "f": [{"n": "weg", "k": "weg", "p": 0, "x": 70, "y": 8, "w": 6, "h": 6, "t": "Kann weg"}]}
        png = rmpapier.picture(paper, 0, [[(70, 9), (75, 13)], [(10, 10)]])
        self.assertTrue(png.startswith(b"\x89PNG"))


@unittest.skipIf(si is None, "rmscene missing")
class Reading(Paper):
    def test_ticked_reminder_is_done_filled_in_brings_it_back(self):
        c, uid = self.on("Ppmorgen")
        item = profiles.add_reminder(uid, "Müll rausstellen", 1_800_000_000)
        did, m, pp = self.sheet(uid, [{"id": item["id"], "text": item["text"], "at": "08:00"}])
        box = next(f for f in pp["f"] if f["n"] == "rem:" + item["id"])
        self.assertEqual(run(rmpapier.check(uid)), 0)                       # nothing written yet
        ink(did, [page_mm(m, tick(box)), None])
        self.assertEqual(run(rmpapier.check(uid)), 1)
        self.assertFalse(any(x["id"] == item["id"] for x in profiles.reminders(uid)))
        self.assertEqual(run(rmpapier.check(uid)), 0)                       # the same sheet is not read twice
        info = c.get("/api/profile/remarkable/papier").json()
        sheet = next(p for p in info["papers"] if p["id"] == did)
        self.assertEqual(next(b for b in sheet["boxes"] if b["n"] == box["n"])["state"], "an")
        self.assertIn(box["n"], sheet["undo"])
        ink(did, [page_mm(m, filled(box)), None])
        run(rmpapier.check(uid))
        self.assertTrue(any(x["text"] == "Müll rausstellen" for x in profiles.reminders(uid)))

    def test_unclear_box_does_nothing(self):
        c, uid = self.on("Ppunklar")
        item = profiles.add_reminder(uid, "Blumen gießen", 1_800_000_000)
        did, m, pp = self.sheet(uid, [{"id": item["id"], "text": item["text"]}])
        box = next(f for f in pp["f"] if f["n"].startswith("rem:"))
        ink(did, [page_mm(m, nearby(box))])
        run(rmpapier.check(uid))
        self.assertTrue(any(x["id"] == item["id"] for x in profiles.reminders(uid)))
        self.assertEqual(remarkable.load(uid)["papers"][did]["r"][box["n"]], "unklar")

    def test_kann_weg_trash_or_archive_and_back(self):
        c, uid = self.on("Ppweg")
        did, m, pp = self.sheet(uid)
        weg = next(f for f in pp["f"] if f["n"] == "weg")
        parent = CLOUD[0].listed()[did]["parent"]
        self.assertEqual(where(uid, did), "Spark/Morgenblatt")
        ink(did, [page_mm(m, tick(weg))])
        run(rmpapier.check(uid))
        self.assertEqual(CLOUD[0].listed()[did]["parent"], "trash")
        r = c.post("/api/profile/remarkable/papier/zurueck", json={"id": did, "n": "weg"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(CLOUD[0].listed()[did]["parent"], parent)
        # with handwriting on it, it goes to "Archiv" instead
        did2, m, pp = self.sheet(uid)
        ink(did2, [page_mm(m, tick(weg) + writing(m))])
        run(rmpapier.check(uid))
        self.assertEqual(where(uid, did2), "Spark/Archiv")
        self.assertEqual(remarkable.load(uid)["papers"][did2]["did"], "archiv")

    def test_only_the_sparks_own_sheets_are_read(self):
        c, uid = self.on("Ppfremd")
        item = profiles.add_reminder(uid, "Steuer", 1_800_000_000)
        did, m, pp = self.sheet(uid, [{"id": item["id"], "text": item["text"]}])
        box = next(f for f in pp["f"] if f["n"].startswith("rem:"))
        copy = str(uuid.UUID(int=555))                     # the same PDF copied on the device: never read
        CLOUD[0].doc(copy, "Morgenblatt Montag (Kopie)", [(str(uuid.UUID(int=556)), page_mm(m, tick(box)))], kind="pdf")
        self.assertEqual(run(rmpapier.check(uid)), 0)
        self.assertTrue(any(x["id"] == item["id"] for x in profiles.reminders(uid)))
        self.assertNotIn(copy, remarkable.load(uid)["papers"])

    def test_calibration_sheet_sets_the_mapping(self):
        c, uid = self.on("Ppkalib")
        r = c.post("/api/profile/remarkable/papier/abgleich")
        self.assertEqual(r.status_code, 200, r.text)
        did = next(p["id"] for p in r.json()["papers"] if p["kind"] == "kalib")
        pp = remarkable.load(uid)["papers"][did]
        m = rmpapier.model("move")
        lines = []
        for f in pp["f"]:
            cx, cy = f["x"] + f["w"] / 2, f["y"] + f["h"] / 2
            lines += [dense((cx - 1.5 + 1, cy - 1.5), (cx + 1.5 + 1, cy + 1.5)), dense((cx + 1.5 + 1, cy - 1.5), (cx - 1.5 + 1, cy + 1.5))]
        ink(did, [page_mm(m, lines)])
        run(rmpapier.check(uid))
        d = remarkable.load(uid)
        self.assertIn("move", d["calib"])
        self.assertAlmostEqual(d["calib"]["move"][1] - m["mm"][0] / 2, -1.0, delta=0.2)
        self.assertEqual(d["paper_size"], [954, 1696])
        self.assertEqual(c.get("/api/profile/remarkable/papier").json()["calibrated"], ["move"])
        png = c.get(f"/api/profile/remarkable/papier/{did}/0.png")
        self.assertEqual(png.status_code, 200)
        self.assertTrue(png.content.startswith(b"\x89PNG"))
        self.assertEqual(c.get(f"/api/profile/remarkable/papier/{did}/7.png").status_code, 404)

    def test_marked_sheet_gets_a_new_version_never_new_text_under_the_ink(self):
        c, uid = self.on("Ppneu")
        m = rmpapier.model("move")
        first = run(rmpapier.place(uid, "eingang", "Eingang Montag", rmpapier.build_text(m, "Eingang", "Eingang Montag", "Eins"),
                                   "text", own="inbox-1", auto=False))
        again = run(rmpapier.place(uid, "eingang", "Eingang Montag", rmpapier.build_text(m, "Eingang", "Eingang Montag", "Zwei"),
                                   "text", own="inbox-1", auto=False))
        self.assertEqual(again["id"], first["id"])                          # no marks yet: the same document, new text
        ink(first["id"], [page_mm(m, writing(m))])
        third = run(rmpapier.place(uid, "eingang", "Eingang Montag", rmpapier.build_text(m, "Eingang", "Eingang Montag", "Drei"),
                                   "text", own="inbox-1", auto=False))
        self.assertNotEqual(third["id"], first["id"])
        self.assertEqual(where(uid, first["id"]), "Spark/Archiv")
        self.assertEqual(where(uid, third["id"]), "Spark/Eingang")

    def test_sync_keeps_what_was_placed_meanwhile(self):
        c, uid = self.on("Ppsync")
        did, m, pp = self.sheet(uid)
        run(remarkable.sync(uid))
        self.assertIn(did, remarkable.load(uid)["papers"])


@unittest.skipIf(si is None, "rmscene missing")
class Folders(Paper):
    def test_without_folders_everything_stays_in_spark(self):
        c, uid = self.on("Ppflach", folders=False)
        did, m, pp = self.sheet(uid)
        self.assertEqual(where(uid, did), "Spark")

    def test_sort_in_moves_only_the_sparks_documents(self):
        c, uid = self.on("Ppsort", folders=False)
        did, m, pp = self.sheet(uid)
        base = lib(uid)[did]["parent"]
        old, mine = str(uuid.UUID(int=601)), str(uuid.UUID(int=602))
        CLOUD[0].doc(old, "Wochenrückblick KW 40", [], parent=base, kind="epub")
        CLOUD[0].doc(mine, "Morgenblatt Notizen", [(str(uuid.UUID(int=603)), page_mm(m, writing(m)))], parent=base)  # a notebook
        c.put("/api/profile/settings", json={"rm_folders": True})
        r = c.post("/api/profile/remarkable/papier/einsortieren")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["moved"], 2)
        self.assertEqual(where(uid, did), "Spark/Morgenblatt")
        self.assertEqual(where(uid, old), "Spark/Wochenrückblick")
        self.assertEqual(lib(uid)[mine]["parent"], base)                           # a notebook is never moved
        remarkable._busy.add(uid)
        try:
            self.assertEqual(c.post("/api/profile/remarkable/papier/einsortieren").status_code, 409)
        finally:
            remarkable._busy.discard(uid)

    def test_tidy_archives_after_7_days_and_trashes_after_30(self):
        c, uid = self.on("Pptidy", tidy=True)
        did, m, pp = self.sheet(uid)
        kept, m, _ = self.sheet(uid)
        ink(kept, [page_mm(m, writing(m))])
        t0 = remarkable.load(uid)["made"][did]["t"]
        self.assertEqual(run(rmpapier.tidy(uid, now=t0 + 6 * 86400)), (0, 0))
        self.assertEqual(run(rmpapier.tidy(uid, now=t0 + 8 * 86400)), (1, 0))
        self.assertEqual(where(uid, did), "Spark/Archiv")
        self.assertEqual(where(uid, kept), "Spark/Morgenblatt")   # handwriting: stays
        self.assertEqual(run(rmpapier.tidy(uid, now=t0 + 20 * 86400)), (0, 0))
        self.assertEqual(run(rmpapier.tidy(uid, now=t0 + 8 * 86400 + 30 * 86400)), (0, 1))
        self.assertEqual(CLOUD[0].listed()[did]["parent"], "trash")
        self.assertNotIn(did, remarkable.load(uid)["made"])
        self.assertIn(kept, remarkable.load(uid)["made"])

    def test_one_cloud_job_at_a_time(self):
        c, uid = self.on("Ppbusy")
        remarkable._busy.add(uid)
        try:
            self.assertEqual(run(rmpapier.tidy(uid, now=1)), 0)
            self.assertEqual(run(rmpapier.check(uid)), 0)
        finally:
            remarkable._busy.discard(uid)


class Guide(unittest.TestCase):
    def test_every_switch_is_in_the_guide_and_the_catalog(self):
        import berater_katalog
        import rmplus
        for k in ("rmpapier", "rmordner", "rmaufraeumen"):
            self.assertIn(k, features.BY_KEY)
            self.assertIn(k, [g[0] for g in rmplus.GUIDE])
        for k in ("rm_paper", "rm_folders", "rm_tidy", "rm_model"):
            self.assertIn(k, berater_katalog.OHNE_PROFIL)


if __name__ == "__main__":
    unittest.main()
