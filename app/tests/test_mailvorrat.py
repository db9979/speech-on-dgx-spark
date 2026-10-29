"""Mail-Vorrat (Dominik 2026-10-20 „ja, so umsetzen“, part of E-Mail lesen, no own switch; mailvorrat.py):

- A listing without words keeps the headers of the mailboxes that answered, the newest HEADS of the last DAYS days;
  an opened (or prefetched) inbox message keeps its plain text, at most TEXTS per profile, TEXT_MAX characters each.
- The file is sealed (AES-GCM, bound to its profile): no subject, sender or text in plain text; without a key nothing
  is written.
- A mailbox that does not answer answers from the supply, with the time it was read, for the assistant and the page;
  a message whose mailbox does not answer comes from the kept text. Without a supply the old error stays.
- After a restart (memory empty) the page gets the listing at once from the file while it is fetched anew.
- Ordering on the page follows (archived gone, read mark); removing a mailbox, all mailboxes or the profile removes
  its part; a supply nobody read for IDLE_DAYS is swept.

Fake mailboxes (no IMAP); times are passed in where it matters.
"""
import datetime
import email
import email.policy
import imaplib
import os
import shutil
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import mail  # noqa: E402
import mailvorrat  # noqa: E402
import profiles  # noqa: E402
import vault  # noqa: E402
import vorrat  # noqa: E402

UID = "u_00000000a1b2"
A1 = {"id": "m00000001", "name": "Privat", "host": "x", "user": "a"}
A2 = {"id": "m00000002", "name": "Arbeit", "host": "y", "user": "b"}
NOW = datetime.datetime.now(datetime.timezone.utc)


def head(i, days=0, unread=True):
    return {"from": f"Anna <anna{i}@example.de>", "subject": f"Rechnung {i}", "date": NOW - datetime.timedelta(days=days, minutes=i),
            "unread": unread, "flagged": False, "attach": False}


def raw(i):
    return email.message_from_bytes(
        (f"From: Anna <anna{i}@example.de>\r\nTo: me@example.de\r\nSubject: Rechnung {i}\r\nMessage-ID: <v{i}@x>\r\n"
         f"Date: Mon, 20 Oct 2026 10:00:00 +0000\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nGeheimer Text {i} bis Freitag.\r\n").encode(),
        policy=email.policy.default)


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (mail._find, mail.get, mail._Session)
        self.accts = [A1, A2]
        mail.get = lambda uid: {"accounts": list(self.accts)}
        self.down = set()
        self.boxes = {A1["id"]: {1: head(1), 2: head(2, unread=False)}, A2["id"]: {7: head(3)}}

        def fake(acct, words, days, unread, limit):
            if acct["id"] in self.down:
                raise OSError("timed out")
            got = [(acct["id"], u, h) for u, h in self.boxes[acct["id"]].items()
                   if (h["unread"] or not unread) and mail.fits(words, h)]
            return sorted(got, key=lambda x: x[2]["date"], reverse=True)[:limit]
        mail._find = fake
        os.makedirs(profiles._path(UID), exist_ok=True)
        self.addCleanup(shutil.rmtree, profiles._path(UID), True)
        self.clear()

    def clear(self, disk=True):
        for d in (mail._cache, mail._bodies, mail._inflight, mail._used, mail._supplied, mail._live):
            d.clear()
        mailvorrat._v.clear()
        if disk:
            try:
                os.remove(mailvorrat._file(UID))
            except OSError:
                pass

    def tearDown(self):
        for ev in list(mail._inflight.values()):
            ev.wait(5)
        mail._find, mail.get, mail._Session = self.saved
        self.clear()


@unittest.skipUnless(vault.available(), "needs cryptography for the sealed file")
class Supply(Base):
    def test_kept_sealed_and_bounded(self):
        self.boxes[A1["id"]].update({100 + i: head(100 + i) for i in range(mailvorrat.HEADS + 20)})
        self.boxes[A1["id"]][99] = head(99, days=mailvorrat.DAYS + 2)            # too old
        mail.find(UID, "", mail.DAYS, False, 1000)
        mailvorrat.flush()
        box = mailvorrat._load(UID)["heads"][A1["id"]]
        self.assertEqual(len(box), mailvorrat.HEADS)                               # only the newest
        self.assertNotIn("99", box)
        with open(mailvorrat._file(UID), "rb") as f:
            data = f.read()
        self.assertNotIn(b"Rechnung", data)                                         # sealed, never plain
        self.assertNotIn(b"anna", data)
        self.assertEqual(oct(os.stat(mailvorrat._file(UID)).st_mode & 0o777), "0o600")

    def test_a_search_is_not_kept(self):
        mail.find(UID, "rechnung", 14, False, 50)
        self.assertEqual(mailvorrat._load(UID)["heads"], {})

    def test_answers_from_the_supply_with_its_time(self):
        mail.find(UID, "", 14, False, 50)
        mail._cache.clear()
        self.down.add(A1["id"])
        before = mailvorrat.for_live()["answers"]
        out = mail.listing(UID, "", 7, False, 8)
        self.assertIn("Rechnung 1", out)                                           # from the supply
        self.assertIn("Rechnung 3", out)                                           # the other mailbox live
        self.assertIn("as kept on the Spark at", out)
        self.assertEqual(mailvorrat.for_live()["answers"], before + 1)
        mail.inbox(UID)                                                            # at once (the page), fetched behind
        for ev in list(mail._inflight.values()):
            ev.wait(5)
        page = mail.inbox(UID)
        self.assertEqual(page["errors"], ["Privat"])
        self.assertIn(f"{A1['id']}:1", [x["id"] for x in page["items"]])

    def test_without_a_supply_the_error_stays(self):
        self.down.add(A1["id"])
        out = mail.listing(UID, "", 7, False, 8)
        self.assertIn("could not be read: not readable (OSError)", out)
        self.assertNotIn("Rechnung 1", out)

    def test_after_a_restart_the_page_comes_at_once(self):
        mail.find(UID, "", 14, False, mail.INBOX_MAX)
        mailvorrat.flush()
        self.clear(disk=False)                                                     # a restart: memory empty
        self.down.update({A1["id"], A2["id"]})
        t0 = time.time()
        page = mail.inbox(UID, budget=5)
        self.assertLess(time.time() - t0, 1)
        self.assertEqual(sorted(x["id"] for x in page["items"]), [f"{A1['id']}:1", f"{A1['id']}:2", f"{A2['id']}:7"])

    def test_text_kept_and_read_when_the_mailbox_is_down(self):
        class S:
            def __init__(s, acct, folder="INBOX"):
                pass

            def __enter__(s):
                if A1["id"] in self.down:
                    raise imaplib.IMAP4.error("down")
                return s

            def __exit__(s, *a):
                return False

            def body(s, u):
                return raw(u)
        mail._Session = S
        self.assertIn("Geheimer Text 1", mail.read(UID, f"{A1['id']}:1"))
        mail._bodies.clear()
        self.down.add(A1["id"])
        out = mail.read(UID, f"{A1['id']}:1")
        self.assertIn("Geheimer Text 1", out)
        self.assertIn("Rechnung 1", out)
        with self.assertRaises(imaplib.IMAP4.error):                               # never kept: the error stays
            mail.message(UID, f"{A1['id']}:2")

    def test_texts_bounded_and_plain(self):
        for i in range(mailvorrat.TEXTS + 5):
            m = raw(i)
            mailvorrat.keep_text(UID, f"{A1['id']}:{i}", m, "x" * (mailvorrat.TEXT_MAX + 50), now=1000 + i)
        texts = mailvorrat._load(UID)["texts"]
        self.assertEqual(len(texts), mailvorrat.TEXTS)
        self.assertNotIn(f"{A1['id']}:0", texts)                                   # the oldest used went
        self.assertTrue(all(len(t["text"]) == mailvorrat.TEXT_MAX for t in texts.values()))

    def test_page_changes_follow(self):
        mail.find(UID, "", 14, False, 50)
        mail.changed(UID, f"{A1['id']}:1", "read")
        self.assertFalse(mailvorrat._load(UID)["heads"][A1["id"]]["1"]["unread"])
        mail.changed(UID, f"{A1['id']}:1", "archive")
        self.assertNotIn("1", mailvorrat._load(UID)["heads"][A1["id"]])

    def test_removing_a_mailbox_and_all_and_the_sweep(self):
        mail.find(UID, "", 14, False, 50)
        mailvorrat.flush()
        mailvorrat.drop(UID, A1["id"])
        self.assertNotIn(A1["id"], mailvorrat._load(UID)["heads"])
        self.assertIn(A2["id"], mailvorrat._load(UID)["heads"])
        mailvorrat.forget(UID)
        self.assertFalse(os.path.exists(mailvorrat._file(UID)))
        mail._cache.clear()
        mail.find(UID, "", 14, False, 50)
        mailvorrat.flush()
        old = time.time() - (mailvorrat.IDLE_DAYS + 1) * 86400
        os.utime(mailvorrat._file(UID), (old, old))
        self.assertGreaterEqual(mailvorrat.sweep(), 1)
        self.assertFalse(os.path.exists(mailvorrat._file(UID)))


class AskRule(Base):
    """The assistant (listing): a listing up to ASK_FRESH as it is; an older one waits ASK_WAIT for the fetch, then
    answers with the older one and its time; a fetch back in time gives the new one without a time."""
    def setUp(self):
        super().setUp()
        self.saved_wait = mail.ASK_WAIT
        mail.ASK_WAIT = 0.2
        self.addCleanup(setattr, mail, "ASK_WAIT", self.saved_wait)
        self.key = (UID, "", 7, False, 8)

    def slow(self, seconds):
        fast = mail._find

        def f(*a):
            time.sleep(seconds)
            return fast(*a)
        mail._find = f

    def test_up_to_ten_minutes_as_it_is(self):
        mail._cache[self.key] = (time.time() - mail.ASK_FRESH + 30, ([(A1["id"], 5, head(5))], [], True))
        out = mail.listing(UID, "", 7, False, 8)
        self.assertIn("Rechnung 5", out)
        self.assertNotIn("as of", out)

    def test_older_waits_then_answers_with_its_time(self):
        mail._cache[self.key] = (time.time() - mail.ASK_FRESH - 30, ([(A1["id"], 5, head(5))], [], True))
        self.slow(1.0)
        t0 = time.time()
        out = mail.listing(UID, "", 7, False, 8)
        self.assertLess(time.time() - t0, 0.8)
        self.assertIn("Rechnung 5", out)
        self.assertIn("Listing as of", out)

    def test_older_but_the_fetch_comes_in_time(self):
        mail._cache[self.key] = (time.time() - mail.ASK_FRESH - 30, ([(A1["id"], 5, head(5))], [], True))
        self.slow(0.05)
        out = mail.listing(UID, "", 7, False, 8)
        self.assertIn("Rechnung 1", out)
        self.assertNotIn("Rechnung 5", out)
        self.assertNotIn("as of", out)


class NoKey(Base):
    def test_without_the_key_nothing_is_written(self):
        saved = vorrat.key
        vorrat.key = lambda zweck="vorrat": None
        try:
            mail.find(UID, "", 14, False, 50)
            mailvorrat.flush()
            self.assertFalse(os.path.exists(mailvorrat._file(UID)))
        finally:
            vorrat.key = saved

    @unittest.skipUnless(vault.available(), "needs cryptography")
    def test_a_file_of_another_profile_does_not_open(self):
        mail.find(UID, "", 14, False, 50)
        mailvorrat.flush()
        other = "u_00000000ffff"
        os.makedirs(profiles._path(other), exist_ok=True)
        self.addCleanup(shutil.rmtree, profiles._path(other), True)
        shutil.copy(mailvorrat._file(UID), mailvorrat._file(other))
        self.assertEqual(mailvorrat._load(other)["heads"], {})                    # bound to its profile (AES-GCM)
        mailvorrat._v.clear()
        self.assertIn(A1["id"], mailvorrat._load(UID)["heads"])                   # its own opens again


if __name__ == "__main__":
    unittest.main()
