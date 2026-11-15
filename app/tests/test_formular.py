"""PDF-Formulare ausfüllen (formular.py, Dominik 2026-11-15 „1a 2 ja 3a“): fields read with pypdf, values only by fixed
rules from the profile, the memory's places, the mailbox and the date; signature, IBAN and ID numbers never; someone
else's name never the profile's; scripts and actions out of the written file; the original unchanged; a new document;
the mail answer carries it as an attachment. Off until the admin allows it, never for guests. No test reads the clock."""
import asyncio
import io
import unittest

from tests import helpers
from tests.test_agent import profile
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import documents  # noqa: E402
import formular  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402
from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject,  # noqa: E402
                           StreamObject, TextStringObject)

N = NameObject


def make_form(fields, script=True):
    """A one-page PDF with AcroForm fields [(name, label, kind)], kind tx, btn or sig; with script: actions inside."""
    w = PdfWriter()
    page = w.add_blank_page(595, 842)
    annots, y = ArrayObject(), 780
    for name, label, kind in fields:
        d = DictionaryObject({N("/Type"): N("/Annot"), N("/Subtype"): N("/Widget"), N("/T"): TextStringObject(name),
                              N("/Rect"): ArrayObject([FloatObject(200), FloatObject(y), FloatObject(500), FloatObject(y + 20)]),
                              N("/F"): NumberObject(4), N("/P"): page.indirect_reference})
        if label:
            d[N("/TU")] = TextStringObject(label)
        if kind == "tx":
            d[N("/FT")], d[N("/DA")] = N("/Tx"), TextStringObject("/Helv 10 Tf 0 g")
        elif kind == "btn":
            d[N("/FT")], d[N("/V")] = N("/Btn"), N("/Off")
            d[N("/AP")] = DictionaryObject({N("/N"): DictionaryObject({N("/Yes"): DictionaryObject(), N("/Off"): DictionaryObject()})})
        else:
            d[N("/FT")] = N("/Sig")
        if script:
            d[N("/AA")] = DictionaryObject({N("/K"): DictionaryObject({N("/S"): N("/JavaScript"), N("/JS"): TextStringObject("app.alert(1)")})})
        annots.append(w._add_object(d))
        y -= 40
    page[N("/Annots")] = annots
    font = w._add_object(DictionaryObject({N("/Type"): N("/Font"), N("/Subtype"): N("/Type1"), N("/BaseFont"): N("/Helvetica")}))
    text = StreamObject()       # a text layer: the documents page reads it like any PDF
    text.set_data(b"BT /Helv 14 Tf 50 800 Td (Anmeldung zur Klassenfahrt) Tj ET")
    page[N("/Contents")] = w._add_object(text)
    page[N("/Resources")] = DictionaryObject({N("/Font"): DictionaryObject({N("/Helv"): font})})
    w._root_object[N("/AcroForm")] = DictionaryObject({N("/Fields"): ArrayObject(list(annots)), N("/DA"): TextStringObject("/Helv 10 Tf 0 g"),
                                                       N("/DR"): DictionaryObject({N("/Font"): DictionaryObject({N("/Helv"): font})})})
    if script:
        w._root_object[N("/OpenAction")] = DictionaryObject({N("/S"): N("/JavaScript"), N("/JS"): TextStringObject("app.alert(2)")})
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


FORM = [("vorname", "Vorname", "tx"), ("nachname", "Nachname", "tx"), ("ort_datum", "Ort, Datum", "tx"),
        ("kind", "Name des Kindes", "tx"), ("iban", "IBAN", "tx"), ("geb", "Geburtsdatum", "tx"),
        ("ok", "Teilnahme erlaubt", "btn"), ("sig", "Unterschrift", "sig")]


class Rules(unittest.TestCase):
    def setUp(self):
        _, self.uid = profile("Formi Muster", "4714")
        profiles.remember(self.uid, "Ich wohne in Musterstadt")

    def test_fields_and_fixed_rules(self):
        fields, pages = formular.fields_of(make_form(FORM))
        self.assertEqual(pages, 1)
        self.assertEqual([f["kind"] for f in fields], ["text"] * 6 + ["check", "sig"])
        got = {f["name"]: f for f in formular.propose(self.uid, fields)}
        self.assertEqual((got["vorname"]["value"], got["vorname"]["src"]), ("Formi", "profil"))
        self.assertEqual(got["nachname"]["value"], "Muster")
        self.assertRegex(got["ort_datum"]["value"], r"^Musterstadt, \d\d\.\d\d\.\d{4}$")
        self.assertEqual(got["kind"]["value"], "")        # someone else's name: never the profile's
        self.assertEqual((got["iban"]["value"], got["iban"]["lock"]), ("", "hand"))
        self.assertEqual(got["geb"]["value"], "")         # a birth date is no „today“
        self.assertEqual((got["ok"]["value"], got["ok"]["src"]), ("", ""))   # a check box is never ticked by the Spark
        self.assertEqual(got["sig"]["lock"], "sig")

    def test_fill_writes_values_and_takes_scripts_out(self):
        data = make_form(FORM)
        fields, _ = formular.fields_of(data)
        out, n = formular.fill(data, fields, {"vorname": "Formi", "ok": "Yes", "sig": "x", "nope": "y",
                                              "nachname": "A" * 900})
        self.assertEqual(n, 3)
        r = PdfReader(io.BytesIO(out))
        v = {k: f.get("/V") for k, f in r.get_fields().items()}
        self.assertEqual((v["vorname"], v["ok"], v["sig"]), ("Formi", "/Yes", None))
        self.assertEqual(len(v["nachname"]), formular.MAX_VALUE)
        self.assertNotIn(b"/JavaScript", out)
        self.assertNotIn(b"/OpenAction", out)
        self.assertNotIn("/AA", str(r.pages[0]["/Annots"][0].get_object()))
        self.assertTrue(formular.preview(out).startswith(b"\x89PNG"))

    def test_no_form_and_no_pdf(self):
        w = PdfWriter()
        w.add_blank_page(100, 100)
        b = io.BytesIO()
        w.write(b)
        self.assertEqual(formular.fields_of(b.getvalue())[0], [])
        with self.assertRaises(ValueError):
            formular.fields_of(b"<html>no pdf</html>")


class Api(unittest.TestCase):
    def setUp(self):
        helpers.set_config(documents=True, pdf_forms=True, doc_originals=True)
        self.c, self.uid = profile("Formi Muster", "4714")
        self.data = make_form(FORM)
        import wissen
        self.doc = wissen.add(self.uid, "Klassenfahrt.pdf", self.data)["id"]

    def tearDown(self):
        helpers.set_config(pdf_forms=False)

    def test_read_check_save(self):
        self.assertTrue(documents.original(self.uid, self.doc))      # doc_originals is on in this test
        r = self.c.post("/api/profile/formular/lesen", json={"doc": self.doc})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["name"], "Klassenfahrt.pdf")
        p = self.c.post("/api/profile/formular/vorschau", json={"key": d["key"], "values": {"vorname": "X"}})
        self.assertEqual((p.status_code, p.headers["content-type"]), (200, "image/png"))
        s = self.c.post("/api/profile/formular/speichern", json={"key": d["key"], "values": {"vorname": "Formi"}})
        self.assertEqual(s.status_code, 200, s.text)
        got = s.json()
        self.assertEqual((got["name"], got["filled"]), ("Klassenfahrt (ausgefüllt).pdf", 1))
        path = documents.original(self.uid, got["doc"])[0]
        with open(path, "rb") as fh:
            self.assertEqual(PdfReader(fh).get_fields()["vorname"].get("/V"), "Formi")
        with open(documents.original(self.uid, self.doc)[0], "rb") as fh:
            self.assertEqual(fh.read(), self.data)        # the original stays as it was
        # only a filled form goes along with a mail, never another document
        import senden
        name, ctype, data = senden.ANHAENGE["doc"](self.uid, got["doc"])
        self.assertEqual((name, ctype, data[:5]), ("Klassenfahrt (ausgefüllt).pdf", "application/pdf", b"%PDF-"))
        with self.assertRaises(LookupError):
            senden.ANHAENGE["doc"](self.uid, self.doc)
        x = formular.for_live()
        self.assertGreaterEqual((x["gelesen"], x["gespeichert"]), (1, 1))
        # a key of another profile's draft or an old one is no form
        self.assertEqual(self.c.post("/api/profile/formular/speichern", json={"key": "x" * 24}).status_code, 404)

    def test_off_by_default_and_never_for_guests_or_devices(self):
        helpers.set_config(pdf_forms=False)
        self.assertEqual(self.c.post("/api/profile/formular/lesen", json={"doc": self.doc}).status_code, 403)
        helpers.set_config(pdf_forms=True)
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/formular/lesen", json={"doc": self.doc}).status_code, (401, 403))
        r = self.c.post("/api/profile/formular/lesen", json={"doc": "000000000000"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.c.post("/api/profile/formular/lesen", content=b"x" * 5000,
                                     headers={"Content-Type": "application/json"}).status_code, 413)

    def test_live_counts_numbers_only(self):
        import live
        self.assertIn("formular", live.TEILE)
        x = formular.for_live()
        self.assertTrue(x["on"])
        self.assertTrue(all(isinstance(v, (bool, int)) for v in x.values()))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Sheet(unittest.TestCase):
    """The sheet in the browser: proposals with their source, IBAN and signature open, the picture, saving."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    def setUp(self):
        helpers.set_config(documents=True, pdf_forms=True, doc_originals=True)
        _, self.uid = profile("Formi Blatt", "4715")
        profiles.remember(self.uid, "Ich wohne in Musterstadt")
        import wissen
        self.doc = wissen.add(self.uid, "Anmeldung.pdf", make_form(FORM))["id"]

    def tearDown(self):
        helpers.set_config(pdf_forms=False)

    async def until(self, pg, expr, seconds=20):
        for _ in range(int(seconds * 10)):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass
            await pg.wait_for_timeout(100)
        self.fail("timed out: " + expr)

    def test_sheet(self):
        self.assertTrue(documents.original(self.uid, self.doc))      # doc_originals is on in this test

        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    pg = await (await br.new_context(viewport={"width": 1280, "height": 900}, locale="de-DE")).new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    base = f"http://127.0.0.1:{self.port}"
                    await pg.goto(base + "/")
                    r = await pg.request.post(base + "/api/profile/login", data={"name": "Formi Blatt", "pin": "4715"})
                    self.assertEqual(r.status, 200)
                    await pg.goto(base + "/")
                    await self.until(pg, "typeof PROFILE!=='undefined'&&!!PROFILE&&FM_ON===true")
                    await pg.evaluate(f"fmOpen({{doc:'{self.doc}'}})")
                    await self.until(pg, "!!document.querySelector('#fmsheet [data-fi]')")
                    vals = await pg.evaluate("Object.fromEntries(FM.d.fields.map((f,i)=>[f.name,"
                                             "(document.querySelector(`#fmsheet [data-fi='${i}']`)||{}).value]))")
                    self.assertEqual((vals["vorname"], vals["nachname"], vals["iban"], vals["kind"]), ("Formi", "Blatt", "", ""))
                    text = await pg.inner_text("#fmsheet")
                    self.assertIn("aus deinem Profil", text)
                    self.assertIn("Trägst du selbst ein", text)       # the IBAN
                    self.assertIn("Unterschrift:", text)
                    await self.until(pg, "$('fmimg').naturalWidth>0")
                    await pg.fill("#fmsheet [data-fi='0']", "Formina")
                    await pg.click("#fmsheet [data-fm=save]")
                    await self.until(pg, "/Gespeichert als/.test($('fmmsg').textContent)")
                    self.assertIn("(ausgefüllt).pdf", await pg.inner_text("#fmmsg"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
