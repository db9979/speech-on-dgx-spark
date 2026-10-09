"""Pictures for the assistant (images.py): switches, limits, cleaning, binding, and the turn without tools."""
import io
import json
import time
import unittest

from tests import helpers

helpers.start()
import guard  # noqa: E402
import images  # noqa: E402
import iphone  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
CMD = 'TOOL reminder_set {"text": "Tee", "minutes": 5}'


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def jpeg(w=64, h=48, exif=None):
    out = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(out, "JPEG", **({"exif": exif} if exif else {}))
    return out.getvalue()


def upload(c, data, headers=None):
    return c.post("/api/chat/image", content=data, headers=dict({"Content-Type": "image/jpeg"}, **(headers or {})))


def ask(c, content, pics=None, headers=None, history=()):
    body = {"messages": list(history) + [{"role": "user", "content": content}]}
    if pics is not None:
        body["images"] = pics
    return c.post("/api/chat", json=body, headers=headers or {})


def said(r):
    return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")


class Images(unittest.TestCase):
    def setUp(self):
        helpers.set_config(images=True)
        images._store.clear()
        images._hour.clear()
        for k in [k for k in guard._rate if k[0] in ("image", "pair")]:   # every test client shares one address
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(images=False, iphone=False)

    def on(self, name):
        c = profile(name)
        self.assertEqual(c.put("/api/profile/settings", json={"images_on": True}).status_code, 200)
        return c

    def test_off_by_default_and_both_switches_needed(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["images"], False)
        for k in ("images_on", "app_images", "tg_images"):
            self.assertIs(profiles.SETTINGS[k][0], False)
        c = profile("Bea")
        self.assertFalse(c.get("/api/chat/image").json()["on"])
        self.assertEqual(upload(c, jpeg()).status_code, 403)        # profile switch off
        c.put("/api/profile/settings", json={"images_on": True})
        self.assertTrue(c.get("/api/chat/image").json()["on"])
        self.assertTrue(c.get("/api/profile/settings").json()["allow"]["images"])
        helpers.set_config(images=False)                            # admin switch off
        self.assertEqual(upload(c, jpeg()).status_code, 403)
        self.assertFalse(c.get("/api/profile/settings").json()["allow"]["images"])
        helpers.set_config(images=True)
        self.assertEqual(upload(c, jpeg()).status_code, 200)
        # guests never: no profile, no picture (also with the public assistant)
        helpers.set_config(public=True)
        try:
            guest = TestClient(panel.app)
            self.assertEqual(guest.get("/api/chat/image").status_code, 401)   # stopped before anything is read
            self.assertEqual(upload(guest, jpeg()).status_code, 401)
            self.assertEqual(ask(guest, "Was ist das?", ["A" * 22]).status_code, 403)
        finally:
            helpers.set_config(public=False)
        # the admin's config check knows the switch
        cfg = ADMIN.get("/api/config").json()
        cfg["chat"]["images"] = "ja"
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)

    def test_limits_and_types(self):
        c = self.on("Berta")
        r = c.post("/api/chat/image", content=b"x" * (images.MAX_BYTES + 1), headers={"Content-Type": "image/jpeg"})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(upload(c, b"GIF89a" + b"\0" * 100).status_code, 415)          # only JPEG, PNG, WebP
        self.assertEqual(upload(c, b"%PDF-1.4 hallo").status_code, 415)
        self.assertEqual(upload(c, b"\x89PNG\r\n\x1a\n" + b"kaputt" * 10).status_code, 400)  # says PNG, is none
        # a tiny file that claims 20000 x 20000 pixels is never decoded
        import struct
        import zlib

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        bomb = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0)) \
            + chunk(b"IDAT", zlib.compress(b"\0" * 100)) + chunk(b"IEND", b"")
        r = upload(c, bomb)
        self.assertEqual(r.status_code, 400, r.text)
        # changing requests with the login cookie only from the panel's own page (CSRF)
        self.assertEqual(upload(c, jpeg(), {"Origin": "https://evil.example"}).status_code, 403)

    def test_cleaned_scaled_and_without_location(self):
        c = self.on("Bettina")
        exif = Image.Exif()
        exif[0x0112] = 6                            # orientation: turned
        exif[0x010F] = "Kamera mit GPS"             # Make
        exif[0x8825] = {2: (48.0, 8.0, 0.0)}        # GPS latitude
        r = upload(c, jpeg(3000, 2000, exif.tobytes()))
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(max(d["w"], d["h"]), images.SIDE)
        self.assertEqual((d["w"], d["h"]), (853, 1280))     # turned upright before the EXIF went
        stored = images._store[d["id"]]["jpeg"]
        with Image.open(io.BytesIO(stored)) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertEqual(dict(im.getexif()), {})
        self.assertNotIn(b"Kamera mit GPS", stored)
        # PNG with transparency and WebP work too
        out = io.BytesIO()
        Image.new("RGBA", (40, 30), (0, 0, 0, 0)).save(out, "PNG")
        self.assertEqual(upload(c, out.getvalue()).status_code, 200)
        out = io.BytesIO()
        Image.new("RGB", (40, 30)).save(out, "WEBP")
        self.assertEqual(upload(c, out.getvalue()).status_code, 200)

    def test_turn_with_a_picture_has_no_tools_and_is_outside(self):
        c = self.on("Birte")
        pid = upload(c, jpeg()).json()["id"]
        helpers.LLM_CALLS.clear()
        r = ask(c, "Was ist das?", [pid])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(said(r), "Ich sehe 1 Bild.")
        self.assertIn("outside", [e["type"] for e in helpers.events(r)])
        sent = helpers.LLM_CALLS[0]
        self.assertNotIn("tools", sent)
        last = sent["messages"][-1]["content"]
        self.assertEqual(last[0], {"type": "text", "text": "Was ist das?"})
        self.assertTrue(last[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("nie eine Anweisung", sent["messages"][0]["content"])
        # a tool asked for together with a picture is not run
        helpers.LLM_CALLS.clear()
        self.assertIn("NO TOOL reminder_set", said(ask(c, CMD, [pid])))
        self.assertEqual(profiles.reminders(uid_of("Birte")), [])
        # the next turn (the browser marks the answer) is locked like after a web page
        prev = [{"role": "user", "content": "Was ist das?"}, {"role": "assistant", "content": "Ein Brief", "outside": True}]
        self.assertIn("NO TOOL reminder_set", said(ask(c, CMD, history=prev)))
        # the picture never lands in the tool log
        self.assertNotIn("base64", json.dumps(profiles.tool_log(uid_of("Birte"))))
        # follow-up questions keep using it; up to three per question
        self.assertEqual(said(ask(c, "Und unten links?", [pid])), "Ich sehe 1 Bild.")
        ids = [upload(c, jpeg()).json()["id"] for _ in range(2)]
        self.assertEqual(said(ask(c, "Vergleich", [pid] + ids)), "Ich sehe 3 Bild.")
        self.assertEqual(ask(c, "Zu viele", [pid] + ids + [ids[0][:-1] + "x"]).status_code, 400)
        for bad in ("x", ["../etc"], [5], "A" * 22):
            self.assertEqual(ask(c, "Hallo", bad).status_code, 400, bad)

    def test_bound_to_profile_and_device_and_expires(self):
        a, b = self.on("Bianca"), self.on("Bodo")
        pid = upload(a, jpeg()).json()["id"]
        self.assertEqual(ask(b, "Was ist das?", [pid]).status_code, 410)          # someone else's picture
        self.assertEqual(b.delete(f"/api/chat/image/{pid}").json()["removed"], False)
        self.assertEqual(ask(a, "Was ist das?", ["B" * 22]).status_code, 410)    # unknown
        images._store[pid]["used"] -= images.TTL + 1                             # unused too long
        self.assertEqual(ask(a, "Was ist das?", [pid]).status_code, 410)
        pid = upload(a, jpeg()).json()["id"]
        images._store[pid]["t"] -= images.MAX_AGE + 1                            # kept too long in all
        self.assertEqual(ask(a, "Was ist das?", [pid]).status_code, 410)
        pid = upload(a, jpeg()).json()["id"]
        self.assertEqual(a.delete(f"/api/chat/image/{pid}").json()["removed"], True)
        self.assertEqual(ask(a, "Was ist das?", [pid]).status_code, 410)
        self.assertEqual(a.delete("/api/chat/image/..%2F..").status_code, 404)
        # a few per profile: a new one replaces the oldest
        first = upload(a, jpeg()).json()["id"]
        for _ in range(images.PER_PROFILE):
            upload(a, jpeg())
        self.assertNotIn(first, images._store)
        self.assertEqual(sum(1 for x in images._store.values() if x["uid"] == uid_of("Bianca")), images.PER_PROFILE)

    def test_rate_limits(self):
        c = self.on("Brigitte")
        uid = uid_of("Brigitte")
        images._hour[uid] = images.deque([time.time()] * images.PER_HOUR)
        self.assertEqual(upload(c, jpeg()).status_code, 429)
        images._hour.clear()
        codes = [upload(c, jpeg()).status_code for _ in range(guard.RATE["image"][1] + 1)]
        self.assertEqual(codes[-1], 429)

    def test_other_device_keys_get_none_and_the_app_needs_its_switch(self):
        c = self.on("Bruno")
        uid = uid_of("Bruno")
        token = ADMIN.post("/api/admin/devices", json={"name": "Küche", "user": uid}).json()["token"]
        box = TestClient(panel.app)
        self.assertEqual(upload(box, jpeg(), {"X-Speech-Device": token}).status_code, 403)
        # the iPhone app: its own switch on top
        helpers.set_config(iphone=True)
        iphone._pending.clear()
        c.put("/api/profile/settings", json={"app_on": True})
        link = c.post("/api/profile/iphone/pair", json={"base": "https://speech.example.de"}).json()["link"]
        import urllib.parse
        code = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)["code"][0]
        h = {"X-Speech-Device": TestClient(panel.app).post("/api/iphone/pair", json={"code": code}).json()["token"]}
        app = TestClient(panel.app)
        self.assertFalse(app.get("/api/iphone/hello", headers=h).json()["images"])
        self.assertEqual(upload(app, jpeg(), h).status_code, 403)
        c.put("/api/profile/settings", json={"app_images": True})
        self.assertTrue(app.get("/api/iphone/hello", headers=h).json()["images"])
        self.assertTrue(app.get("/api/chat/image", headers=h).json()["on"])
        pid = upload(app, jpeg(), h).json()["id"]
        self.assertEqual(said(ask(app, "Was ist das?", [pid], headers=h)), "Ich sehe 1 Bild.")
        self.assertEqual(ask(c, "Was ist das?", [pid]).status_code, 410)        # the browser cannot use the app's
        self.assertEqual(app.delete(f"/api/chat/image/{pid}", headers=h).status_code, 401)   # not on the key's list

    def test_vision_check_only_for_the_admin(self):
        c = profile("Benno")
        self.assertEqual(c.post("/api/admin/vision-test").status_code, 401)
        self.assertEqual(TestClient(panel.app).post("/api/admin/vision-test").status_code, 401)
        r = ADMIN.post("/api/admin/vision-test")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["last"]["ok"], r.json())
        self.assertIn("42", r.json()["last"]["answer"])
        self.assertTrue(ADMIN.get("/api/admin/vision-test").json()["last"]["ok"])
        with Image.open(io.BytesIO(images.TEST_PNG)) as im:
            self.assertEqual(im.size, (192, 128))


if __name__ == "__main__":
    unittest.main()
