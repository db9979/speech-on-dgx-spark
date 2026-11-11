"""Geräte-Bild (geraetebild.py; Dominik 2026-11-11, choice „2 Zeichnung plus eigenes Foto“): each computer's card
shows the panel's own drawing that fits the device, or the admin's own photo. The device name is outside text and
only picks one of the fixed drawings; the photo endpoints need the admin, take only a real JPEG, PNG or WebP of
limited size and store it anew without the file's extra data; nothing is loaded from the internet; the log holds
fixed words and numbers only. No test depends on the clock."""
import base64
import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout

from tests import helpers

helpers.start()
import common  # noqa: E402
import dateien  # noqa: E402
import geraetebild  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

STATIC = os.path.join(os.path.dirname(geraetebild.__file__), "static")


def foto(size=(1200, 900), fmt="JPEG", exif=True):
    im = Image.new("RGB", size, (40, 90, 160))
    out = io.BytesIO()
    kw = {}
    if exif and fmt == "JPEG":
        e = Image.Exif()
        e[0x010F] = "Kamera Geheim"          # Make
        e[0x9003] = "2026:11:11 12:00:00"    # DateTimeOriginal
        kw["exif"] = e
    im.save(out, fmt, **kw)
    return out.getvalue()


def url(data, kind="jpeg"):
    return f"data:image/{kind};base64," + base64.b64encode(data).decode()


class Zeichnung(unittest.TestCase):
    def test_the_device_name_only_picks_a_fixed_drawing(self):
        for name, art in (("Dell Pro Max with GB10 FCM1253", "gb10"), ("NVIDIA DGX Spark", "gb10"),
                          ("Raspberry Pi 5 Model B Rev 1.0", "pi"), ("Raspberry Pi 4 Model B", "pi"),
                          ("ThinkStation P3", "rechner"), ("", "rechner"), (None, "rechner"), (7, "rechner"),
                          ("../../etc/passwd", "rechner"), ("<img src=x onerror=alert(1)>", "rechner"),
                          ("x" * 5000 + " Raspberry Pi", "rechner")):
            self.assertEqual(geraetebild.art(name), art, name)
        self.assertEqual({a for a, _ in geraetebild.ARTEN} | {geraetebild.PLATZ}, set(geraetebild.ZEICHNUNGEN))

    def test_every_drawing_is_there_own_and_loads_nothing(self):
        for name in geraetebild.ZEICHNUNGEN:
            with open(os.path.join(STATIC, "geraete", name + ".svg"), encoding="utf-8") as f:
                svg = f.read()
            self.assertTrue(svg.startswith("<svg "), name)
            self.assertIn("own drawing", svg, name)
            for bad in ("http://", "https://", "<script", "<image", "href", "@import", "url("):
                self.assertNotIn(bad, svg.replace('xmlns="http://www.w3.org/2000/svg"', ""), f"{name}: {bad}")
        self.assertEqual(sorted(os.listdir(os.path.join(STATIC, "geraete"))),
                         sorted(n + ".svg" for n in geraetebild.ZEICHNUNGEN))
        with open(os.path.join(STATIC, "js", "admin.js"), encoding="utf-8") as f:
            js = f.read()
        m = re.search(r"const ZR_BILD=\[([^\]]+)\]", js)
        self.assertEqual(sorted(x.strip("'") for x in m.group(1).split(",")), sorted(geraetebild.ZEICHNUNGEN))
        self.assertIn("h.prepend(zRBild(c))", js)       # in the card's head: no row of its own (cards stand still)

    def test_the_panel_serves_only_these_drawings(self):
        c = TestClient(panel.app)
        for name in geraetebild.ZEICHNUNGEN:
            r = c.get(f"/static/geraete/{name}.svg")
            self.assertEqual((r.status_code, r.headers["content-type"].split(";")[0]), (200, "image/svg+xml"), name)
        for name in ("gb10.png", "andere.svg", "gb10", "..%2Fapp.css", "%2e%2e%2f%2e%2e%2fpanel.py"):
            self.assertEqual(c.get(f"/static/geraete/{name}").status_code, 404, name)

    def test_the_card_names_drawing_and_photo(self):
        import rechnerblick
        with rechnerblick._lock:
            alt = dict(rechnerblick._letzt)
            rechnerblick._letzt["panel"] = {"geraet": "Raspberry Pi 5 Model B Rev 1.0"}
        self.addCleanup(rechnerblick._letzt.update, alt)
        self.addCleanup(geraetebild.weg, "panel")
        geraetebild.weg("panel")
        self.assertEqual(rechnerblick.karte("panel")["bild"], {"art": "pi", "eigen": 0})
        geraetebild.setzen("panel", foto())
        b = rechnerblick.karte("panel")["bild"]
        self.assertEqual(b["art"], "pi")
        self.assertGreater(b["eigen"], 0)


class Foto(unittest.TestCase):
    def setUp(self):
        guard._rate.clear()
        self.admin = TestClient(panel.app)
        self.assertEqual(self.admin.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        for k in geraetebild.RECHNER:
            geraetebild.weg(k)
            self.addCleanup(geraetebild.weg, k)

    def post(self, k, bild, c=None):
        out = io.StringIO()
        with redirect_stdout(out):
            r = (c or self.admin).post(f"/api/admin/rechner/bild/{k}", json={"bild": bild})
        return r, out.getvalue()

    def test_only_the_admin(self):
        anon = TestClient(panel.app)
        for m, p in (("get", "/api/admin/rechner/bild/panel"), ("post", "/api/admin/rechner/bild/panel"),
                     ("delete", "/api/admin/rechner/bild/panel")):
            self.assertIn(getattr(anon, m)(p).status_code, (401, 403), p)
        r = helpers.TestClient(panel.app) if hasattr(helpers, "TestClient") else TestClient(panel.app)
        r.post("/api/login", json={"password": "falsch"})
        self.assertIn(r.post("/api/admin/rechner/bild/panel", json={"bild": url(foto())}).status_code, (401, 403))
        self.assertEqual(geraetebild.eigen("panel"), (None, 0))

    def test_stored_small_and_without_the_files_extra_data(self):
        self.assertEqual(self.admin.get("/api/admin/rechner/bild/modell").status_code, 404)
        roh = foto()
        self.assertIn(b"Kamera Geheim", roh)
        r, log = self.post("modell", url(roh))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertRegex(log, r"^rechner: bild gespeichert modell \| \d+ kB\n$")
        g = self.admin.get("/api/admin/rechner/bild/modell")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.headers["content-type"], "image/jpeg")
        self.assertEqual(g.headers["x-content-type-options"], "nosniff")
        self.assertNotIn(b"Kamera Geheim", g.content)
        self.assertNotIn(b"2026:11:11", g.content)
        im = Image.open(io.BytesIO(g.content))
        self.assertEqual((im.format, max(im.size)), ("JPEG", geraetebild.MAX_PX))
        self.assertFalse(im.getexif())
        self.assertEqual(geraetebild.eigen("panel"), (None, 0))                 # the other computer keeps its drawing
        with open(os.path.join(common.STATE, "geraetebild.json")) as f:
            self.assertEqual(list(json.load(f)), ["modell"])
        self.assertEqual(os.stat(os.path.join(common.STATE, "geraetebild.json")).st_mode & 0o077, 0)
        for fmt, kind in (("PNG", "png"), ("WEBP", "webp")):
            self.assertEqual(self.post("panel", url(foto((300, 200), fmt), kind))[0].status_code, 200, fmt)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.admin.delete("/api/admin/rechner/bild/modell").json(), {"ok": True, "war": True})
            self.assertEqual(self.admin.delete("/api/admin/rechner/bild/modell").json(), {"ok": True, "war": False})
        self.assertEqual(out.getvalue(), "rechner: bild geloescht modell\nrechner: bild keins modell\n")
        self.assertEqual(self.admin.get("/api/admin/rechner/bild/modell").status_code, 404)

    def test_anything_else_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        gif = io.BytesIO()
        Image.new("RGB", (10, 10)).save(gif, "GIF")
        for bild, why in ((url(svg, "jpeg"), "format"), (url(gif.getvalue(), "png"), "format"), (url(b"kein bild"), "format"),
                          ("data:image/svg+xml;base64," + base64.b64encode(svg).decode(), "format"),
                          ("https://example.org/bild.jpg", "format"), ("", "format"), (7, "format"),
                          (url(foto()[:200]), "format"),
                          (url(b"\xff" * (geraetebild.MAX_BILD + 1)), "gross")):
            r, log = self.post("panel", bild)
            self.assertEqual(r.status_code, 400, str(bild)[:40])
            self.assertEqual(log, f"rechner: bild abgelehnt {why} panel\n")
        self.assertEqual(self.post("drucker", url(foto()))[0].status_code, 404)
        self.assertEqual(self.post("../panel", url(foto()))[0].status_code, 404)
        r = self.admin.post("/api/admin/rechner/bild/panel", content=b"x" * (geraetebild.MAX_BODY + 10),
                            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(geraetebild.eigen("panel"), (None, 0))
        huge = Image.new("L", (7000, 6000))                                      # more pixels than MAX_PIXEL
        buf = io.BytesIO()
        huge.save(buf, "PNG")
        with self.assertRaisesRegex(ValueError, "gross"):
            geraetebild.jpeg(buf.getvalue())

    def test_rate_limit_and_the_file_register(self):
        n = guard.RATE["rechnerbild_tun"][1]
        codes = [self.post("panel", "x")[0].status_code for _ in range(n + 2)]
        self.assertEqual(codes[:n], [400] * n)
        self.assertEqual(codes[-1], 429)
        self.assertIn("geraetebild.json", {d.name for d in dateien.DATEIEN})
        self.assertIn("geraetebild.json", dateien.STATE_FILES)                   # part of a backup


if __name__ == "__main__":
    unittest.main()
