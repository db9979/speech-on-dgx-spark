"""The assistant's face (chat.face): the admin picks one for everybody, the robot stays the default,
only known faces are accepted, and the browser draws only faces it knows.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
from core import FACES  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
STATIC = os.path.join(os.path.dirname(__file__), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Face(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(face="robot")

    def test_robot_is_the_default(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            self.assertEqual(json.load(f)["chat"]["face"], "robot")
        self.assertEqual(TestClient(panel.app).get("/api/whoami").json()["face"], "robot")

    def test_admin_picks_only_known_faces(self):
        cfg = ADMIN.get("/api/config").json()
        for bad in ("Comic", "../comic", "<svg>", "", 1, None, True):
            new = json.loads(json.dumps(cfg))
            new["chat"]["face"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 400, bad)
        new = json.loads(json.dumps(cfg))
        new["chat"]["face"] = "comic"
        self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 200)
        self.assertEqual(TestClient(panel.app).get("/api/whoami").json()["face"], "comic")

    def test_unknown_face_in_the_file_shows_the_robot(self):
        helpers.set_config(face="<script>")
        self.assertEqual(TestClient(panel.app).get("/api/whoami").json()["face"], "robot")

    def test_choice_lists_exactly_the_known_faces(self):
        html = read("index.html")
        sel = html[html.index('<select id="chat.face">'):]
        sel = sel[:sel.index("</select>")]
        self.assertEqual(tuple(re.findall(r'value="(\w+)"', sel)), FACES)

    def test_browser_draws_only_known_faces(self):
        js = read("js", "face.js")
        self.assertIn("window.setFaceKind=k=>{k=k==='comic'?'comic':'robot';", js)
        self.assertNotIn("innerHTML=k", js)
        self.assertIn("setFaceKind(who.face)", read("js", "start.js"))

    def test_answer_picture_follows_the_face(self):
        # the small picture before each answer (.av) is the robot unless the comic face is chosen
        js, css = read("js", "face.js"), read("app.css")
        self.assertIn("function faceIcon(){document.body.dataset.face=FACE_KIND;", js)
        self.assertIn("mountAll();faceIcon()};", js)
        self.assertIn("body[data-face=comic] .av{background:var(--avface)", css)
        self.assertIn("body[data-face=comic] .av i{display:none}", css)
        # the still is drawn from the face's own fixed drawing, never from outside text
        fn = js[js.index("function comicIcon()"):js.index("function faceIcon()")]
        self.assertIn("comicSvg('I')", fn)
        self.assertIn("encodeURIComponent(", fn)


class FaceLife(unittest.TestCase):
    """"Gesicht zeigt, was es tut" (chat.face_life): admin switch, off by default, only from the panel's own events."""
    def tearDown(self):
        helpers.set_config(face_life=False)

    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["face_life"], False)
        self.assertIs(TestClient(panel.app).get("/api/whoami").json()["face_life"], False)

    def test_admin_switch_takes_only_true_or_false(self):
        cfg = ADMIN.get("/api/config").json()
        for bad in ("true", 1, "yes", None, [True]):
            new = json.loads(json.dumps(cfg))
            new["chat"]["face_life"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 400, bad)
        new = json.loads(json.dumps(cfg))
        new["chat"]["face_life"] = True
        self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 200)
        self.assertIs(TestClient(panel.app).get("/api/whoami").json()["face_life"], True)

    def test_odd_value_in_the_file_stays_off(self):
        helpers.set_config(face_life="on")
        self.assertIs(TestClient(panel.app).get("/api/whoami").json()["face_life"], False)

    def test_switch_sits_next_to_the_face(self):
        html = read("index.html")
        row = html[html.index('id="faceliferow"'):]
        self.assertIn('<input type="checkbox" id="chat.face_life">', row[:row.index("</div></div>") + 200])
        self.assertIn("setFaceLife(who.face_life===true)", read("js", "start.js"))

    def test_face_follows_only_fixed_event_names(self):
        js, chat = read("js", "face.js"), read("js", "chat.js")
        self.assertIn("const ev=JSON.parse(line.slice(5));faceEvent(ev);", chat)
        fn = js[js.index("window.faceEvent="):js.index("function lifeMode(")]
        self.assertIn("if(!FACE_LIFE||!ev)return;", fn)
        # only type, action and ok are read; nothing from the event is drawn or put into the page
        self.assertEqual(set(re.findall(r"ev\.(\w+)", fn)), {"type", "action", "ok"})
        self.assertNotIn("innerHTML", fn)
        self.assertIn("FACE_ACTS[ev.type]", fn)
        self.assertIn("window.setFaceLife=on=>{on=on===true;", js)
        self.assertIn("SLEEP_MS=5*60*1000", js)
