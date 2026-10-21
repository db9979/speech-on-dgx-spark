"""Mail formatted like it was sent (mailansicht.py, Apple-Stil Stufe 1, Dominik 2026-10-20 „2a“).

- clean(): the HTML of a mail goes through a fixed allow-list on the Spark: scripts, styles, frames, forms, SVG and
  media go with their content; every on…= handler, every unknown attribute and every dangerous style is left out;
  links never get a working href (data-href, http/https/mailto only); pictures from outside get no src (data-remote)
  and are counted; attached pictures (cid:) only through the Spark; text is escaped anew; broken HTML never breaks it.
- GET /api/profile/mail/view: only an own mail, its own strict CSP (no script, sandbox, nothing from outside), nosniff,
  no referrer, not kept; pictures from outside only with bilder=true and then only as addresses on the Spark.
- GET /api/profile/mail/bild: an attached picture by its number, a picture from outside only when this very mail names
  it (no open proxy); only PNG/JPEG/GIF/WebP by their first bytes, never SVG.
- GET /api/profile/mail/message says whether the page shows the frame (html) and how many pictures wait (remote).
- Guests, another profile, the function off, a folder without Mails ordnen: nothing. Every outcome has a log line
  with fixed words and numbers, never an address, a subject or a text.

Fixed mails, a fake mailbox and a fake picture fetch; no wall clock, no network.
"""
import asyncio
import contextlib
import email
import email.policy
import io
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import mail  # noqa: E402
import mailansicht  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ACCT = {"id": "m0a1b2c3e", "name": "Privat", "host": "imap.example.de", "port": 993, "user": "ich", "password": "pw"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
HTML_MAIL = ("From: Anna Alt <anna@example.de>\r\nTo: ich@example.de\r\nSubject: Geheimer Betreff\r\n"
             "Date: Tue, 10 Mar 2026 09:30:00 +0100\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
             "<p onclick=\"steal()\">Hallo, der Wagen ist <b>fertig</b>.</p><script>alert(1)</script>"
             "<a href=\"https://bank.example/login\">bank.example</a><img src=\"https://tracker.example/x.gif\">\r\n")
TEXT_MAIL = ("From: shop@example.de\r\nTo: ich@example.de\r\nSubject: Rechnung\r\n"
             "Date: Mon, 09 Mar 2026 18:00:00 +0100\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nDanke <b>sehr</b>\r\n")


def related():
    """A mail with an attached picture its HTML shows (cid:) and one SVG that pretends to be a picture."""
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"] = "Bob <bob@example.de>", "ich@example.de", "Foto"
    m.set_content("Foto")
    m.add_alternative('<p>Hier: <img src="cid:foto1@x"> <img src="cid:bild2@x"></p>', subtype="html")
    html = m.get_payload()[1]
    html.add_related(PNG, maintype="image", subtype="png", cid="<foto1@x>", filename="foto.png")
    html.add_related(b'<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>', maintype="image",
                     subtype="png", cid="<bild2@x>", filename="bild.png")
    return email.message_from_bytes(m.as_bytes(), policy=email.policy.default)


RAW = {7: HTML_MAIL, 8: TEXT_MAIL}
OWNERS = {}


class Box:
    def __init__(self, acct, folder="INBOX"):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def body(self, uid, most=0):
        if uid == 9:
            return related()
        return email.message_from_string(RAW[uid], policy=email.policy.default) if uid in RAW else None


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Clean(unittest.TestCase):
    def test_scripts_handlers_and_frames_go(self):
        out, remote, links = mailansicht.clean(
            '<p onclick="x()" onmouseover=y>Hi</p><script>alert(1)</script><style>body{display:none}</style>'
            '<iframe src="https://x.example"></iframe><form action="https://x.example"><input name=a></form>'
            '<svg><script>z</script></svg><object data="x"></object><!-- hidden --><meta http-equiv="refresh" content="0;url=https://x">'
            '<iframe/><b>ok</b>')
        for bad in ("onclick", "onmouseover", "<script", "alert", "<style", "display:none", "<iframe", "<form", "<input",
                    "<svg", "<object", "hidden", "<meta", "refresh"):
            self.assertNotIn(bad, out.lower(), bad)
        self.assertIn("<b>ok</b>", out)
        self.assertEqual((remote, links), (0, 0))

    def test_links_never_work_inside(self):
        out, _, links = mailansicht.clean('<a href="https://bank.example/a?b=1&c=2">Bank</a><a href="javascript:alert(1)">x</a>'
                                          '<a href="mailto:anna@example.de">Anna</a><a href="data:text/html,x">d</a>')
        self.assertNotIn("href=", out.replace("data-href=", ""))
        self.assertIn('data-href="https://bank.example/a?b=1&amp;c=2"', out)
        self.assertIn('data-href="mailto:anna@example.de"', out)
        self.assertNotIn("javascript", out)
        self.assertNotIn("data:text", out)
        self.assertEqual(links, 2)

    def test_pictures_from_outside_get_no_address(self):
        out, remote, _ = mailansicht.clean('<img src="https://tracker.example/p.gif" width=1 height=1><img src="http://x.example/a.png">'
                                           '<img src="//x.example/b.png"><img alt="Logo">')
        self.assertNotIn(" src=", out)
        self.assertEqual(remote, 2)
        self.assertIn("[Logo]", out)
        out, _, _ = mailansicht.clean('<img src="https://t.example/p.gif">', remote_src=lambda u: "/api/profile/mail/bild?u=" + u)
        self.assertIn('src="/api/profile/mail/bild?u=https://t.example/p.gif"', out)

    def test_attached_pictures_only_through_the_spark(self):
        out, remote, _ = mailansicht.clean('<img src="cid:Foto1@x"><img src="cid:other@x">', {"<foto1@x>": 3},
                                           cid_src=lambda n: f"/api/profile/mail/bild?n={n}")
        self.assertIn('src="/api/profile/mail/bild?n=3"', out)
        self.assertEqual(out.count("src="), 1)
        self.assertEqual(remote, 0)

    def test_styles_stay_plain(self):
        out, _, _ = mailansicht.clean('<p style="color:red;background:url(https://t.example/x);position:fixed;z-index:9;'
                                      'width:expression(alert(1));font-weight:bold">x</p>')
        self.assertIn("color:red", out)
        self.assertIn("font-weight:bold", out)
        for bad in ("url(", "position", "z-index", "expression", "t.example"):
            self.assertNotIn(bad, out, bad)

    def test_text_is_escaped_and_broken_html_does_not_break(self):
        out, _, _ = mailansicht.clean('<p>1 &lt; 2 &amp; <b>3</p><td>a<td>b<table><tr><td>c')
        self.assertIn("1 &lt; 2 &amp; ", out)
        out, _, _ = mailansicht.clean("<p " + "a" * 5000)
        self.assertIsInstance(out, str)
        out, _, _ = mailansicht.clean("<b>" * 100000)
        self.assertLessEqual(len(out), mailansicht.OUT_MAX + 1000)

    def test_never_svg_by_the_first_bytes(self):
        self.assertEqual(mailansicht._sniff(PNG), "image/png")
        self.assertEqual(mailansicht._sniff(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertIsNone(mailansicht._sniff(b"<svg xmlns='http://www.w3.org/2000/svg'/>"))
        self.assertIsNone(mailansicht._sniff(b"<html><script>x</script>"))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (mail._Session, mail.get, mail.whole, mailansicht.picture)
        mail._Session = Box
        real = mail.get
        mail.get = lambda uid: {"accounts": OWNERS[uid]} if uid in OWNERS else real(uid)

        def whole(uid, ref, folder="INBOX", **kw):   # like mail.whole: only a mailbox of this profile
            if not any(ref.startswith(a["id"] + ":") for a in mail.get(uid)["accounts"]):
                raise ValueError("unknown message id")
            return related() if ref.endswith(":9") else None
        mail.whole = whole
        cls.fetched = []

        async def picture(url):
            cls.fetched.append(url)
            return ("image/png", PNG) if url.endswith(".gif") else None
        mailansicht.picture = picture
        mail._cache.clear()
        mail._bodies.clear()
        helpers.set_config(mail=True)
        cls.c, cls.uid = profile("Ansicht Anke")
        OWNERS[cls.uid] = [ACCT]

    @classmethod
    def tearDownClass(cls):
        mail._Session, mail.get, mail.whole, mailansicht.picture = cls.saved
        mail._cache.clear()
        mail._bodies.clear()
        helpers.set_config(mail=False)

    def call(self, path, **params):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = self.c.get(path, params=params)
        return r, buf.getvalue()

    def test_view_has_its_own_strict_policy(self):
        before = len(self.fetched)
        r, log = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-security-policy"], mailansicht.FRAME_CSP)
        self.assertIn("sandbox", mailansicht.FRAME_CSP)
        self.assertNotIn("script-src", mailansicht.FRAME_CSP)
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["referrer-policy"], "no-referrer")
        self.assertIn("no-store", r.headers["cache-control"])
        self.assertEqual(r.headers["x-remote-pictures"], "1")
        page = r.text
        self.assertIn("<b>fertig</b>", page)
        for bad in ("<script", "onclick", "alert(", 'src="https://'):
            self.assertNotIn(bad, page, bad)
        self.assertNotRegex(page, r'(?<!data-)href=')
        self.assertIn('data-href="https://bank.example/login"', page)
        self.assertEqual(log.strip(), f"mail: view html | 1 pictures outside | {self.name_in_log()}")
        self.assertEqual(len(self.fetched), before)              # nothing fetched from outside without the click

    def name_in_log(self):
        import profiles
        return profiles.log_name(profiles.by_id(self.uid))

    def test_pictures_from_outside_only_after_the_click_and_only_named_ones(self):
        r, log = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:7", bilder="true")
        self.assertIn('src="/api/profile/mail/bild?', r.text)
        self.assertIn("loaded", log)
        r, log = self.call("/api/profile/mail/bild", id=f"{ACCT['id']}:7", u="https://tracker.example/x.gif")
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "image/png"))
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", r.headers["content-security-policy"])
        self.assertTrue(log.startswith("mail: picture loaded | outside | 1 KB | "), log)
        # no open proxy: an address the mail does not name is never fetched
        before = list(self.fetched)
        r, log = self.call("/api/profile/mail/bild", id=f"{ACCT['id']}:7", u="http://192.168.178.1/admin")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.fetched, before)
        self.assertTrue(log.startswith("mail: picture refused, not in the mail | "), log)
        self.assertNotIn("192.168", log)
        self.assertNotIn("tracker", log)

    def test_attached_pictures_and_never_svg(self):
        r, _ = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:9")
        self.assertIn('src="/api/profile/mail/bild?', r.text)
        self.assertEqual(r.headers["x-remote-pictures"], "0")
        r, log = self.call("/api/profile/mail/bild", id=f"{ACCT['id']}:9", n=0)
        self.assertEqual((r.status_code, r.content), (200, PNG))
        self.assertTrue(log.startswith("mail: picture shown | attached | "), log)
        r, log = self.call("/api/profile/mail/bild", id=f"{ACCT['id']}:9", n=1)   # SVG behind image/png: refused
        self.assertEqual(r.status_code, 404)
        self.assertTrue(log.startswith("mail: picture refused, no picture | "), log)
        self.assertEqual(self.call("/api/profile/mail/bild", id=f"{ACCT['id']}:9", n=7)[0].status_code, 404)

    def test_the_iphone_app_gets_everything_inside(self):
        # app=true: attached pictures as data: addresses, the policy in the page itself (the app loads it from a
        # string), a real href that the app's web view stops and asks about; pictures from outside never
        r, _ = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:9", app="true")
        self.assertIn('src="data:image/png;base64,', r.text)
        self.assertNotIn("/api/profile/mail/bild", r.text)
        self.assertIn(f'<meta http-equiv="Content-Security-Policy" content="{mailansicht.APP_CSP}">', r.text)
        self.assertNotIn("script-src", mailansicht.APP_CSP)
        r, _ = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:7", app="true", bilder="true")
        self.assertIn('<a href="https://bank.example/login">', r.text)
        self.assertNotIn('src="https://', r.text)
        self.assertNotIn("/api/profile/mail/bild", r.text)
        # the page in the browser never gets the policy line (it has the header) and never a live link
        r, _ = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:7")
        self.assertNotIn("http-equiv", r.text)

    def test_a_text_mail_stays_text_and_message_says_which(self):
        r, log = self.call("/api/profile/mail/view", id=f"{ACCT['id']}:8")
        self.assertIn("Danke &lt;b&gt;sehr&lt;/b&gt;", r.text)
        self.assertTrue(log.startswith("mail: view text | 0 pictures outside | "), log)
        m = self.c.get("/api/profile/mail/message", params={"id": f"{ACCT['id']}:7"}).json()
        self.assertEqual((m["html"], m["remote"]), (True, 1))
        m = self.c.get("/api/profile/mail/message", params={"id": f"{ACCT['id']}:8"}).json()
        self.assertEqual((m["html"], m["remote"]), (False, 0))

    def test_logs_never_carry_what_the_mail_says(self):
        logs = "".join(self.call(p, **q)[1] for p, q in (
            ("/api/profile/mail/view", {"id": f"{ACCT['id']}:7"}), ("/api/profile/mail/view", {"id": f"{ACCT['id']}:7", "bilder": "true"}),
            ("/api/profile/mail/bild", {"id": f"{ACCT['id']}:7", "u": "https://tracker.example/x.gif"}),
            ("/api/profile/mail/bild", {"id": f"{ACCT['id']}:7", "u": "https://elsewhere.example/y.gif"})))
        for word in ("anna", "Geheimer", "tracker", "elsewhere", "fertig", "bank"):
            self.assertNotIn(word, logs, word)
        for line in logs.strip().splitlines():
            self.assertTrue(line.startswith("mail: "), line)

    def test_only_own_never_guests_never_off(self):
        other, _ = profile("Ansicht Arno")
        self.assertEqual(other.get("/api/profile/mail/view", params={"id": f"{ACCT['id']}:7"}).status_code, 400)
        self.assertEqual(other.get("/api/profile/mail/bild", params={"id": f"{ACCT['id']}:9", "n": 0}).status_code, 400)
        guest = TestClient(panel.app)
        for path in (f"/api/profile/mail/view?id={ACCT['id']}:7", f"/api/profile/mail/bild?id={ACCT['id']}:9&n=0"):
            self.assertIn(guest.get(path).status_code, (401, 403), path)
        # a folder belongs to Mails ordnen
        self.assertEqual(self.c.get("/api/profile/mail/view", params={"id": f"{ACCT['id']}:7", "folder": "Projekte"}).status_code, 403)
        helpers.set_config(mail=False)
        try:
            for path in (f"/api/profile/mail/view?id={ACCT['id']}:7", f"/api/profile/mail/bild?id={ACCT['id']}:9&n=0"):
                self.assertIn(self.c.get(path).status_code, (403, 503), path)
        finally:
            helpers.set_config(mail=True)


class AppRegeln(unittest.TestCase):
    """The iPhone app's blocking rules for a mail (MailPageView): WebKit compiles no „|“ in a url-filter, and without
    the rules the app shows nothing at all (Dominik 2026-10-21: the mail stayed empty)."""

    def test_every_filter_compiles(self):
        import re
        from tests.test_app_gleichstand import IOS, need, read
        swift = read(need(IOS), "Spark", "KalenderPost.swift")
        m = re.search(r"static let block = (.+)", swift)
        self.assertIsNotNone(m, "MailPageView.block is gone")
        filters = re.findall(r'"(\^[^"]*)"', m.group(1))
        self.assertEqual(sorted(filters), ["^ftp:", "^https?:", "^wss?:"])
        for f in filters:
            self.assertNotRegex(f, r"[|()]", f"{f}: WebKit's content rules know no alternatives")


if __name__ == "__main__":
    unittest.main()
