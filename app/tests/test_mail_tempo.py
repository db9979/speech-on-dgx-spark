"""E-Mail schnell (Dominik 2026-10-19 „email muss auch gecached werden“, „die fenster sollten direkt reagieren und im
hintergrund die aktualisierungen machen“):

- All mailboxes of a profile are read at the same time, not one after the other.
- The page shows a listing older than CACHE_SECONDS (up to STALE_SECONDS) at once and fetches it anew behind; without
  one it waits at most VIEW_BUDGET, then answers "loading" while the fetch goes on and lands in the cache.
- One fetch per listing however many ask; a shorter listing without words (the assistant's 7 days, unread) is cut from
  a cached longer one that holds all of it.
- Ordering a message on the page changes the cached listing at once (read mark, archived gone); a fetch started before
  never stores the older state.
- An opened message is kept in memory (BODY_SECONDS); the newest are fetched ahead in the background.
- keep_fresh refreshes the listings of the profiles that read their mail in the last day.

Fake mailboxes (no IMAP); times are passed in where it matters.
"""
import datetime
import email
import email.policy
import threading
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import mail  # noqa: E402
import mailvorrat  # noqa: E402

A1 = {"id": "m00000001", "name": "Privat", "host": "x", "user": "a"}
A2 = {"id": "m00000002", "name": "Arbeit", "host": "y", "user": "b"}
NOW = datetime.datetime.now(datetime.timezone.utc)


def head(i, unread=True, days=0):
    return {"from": f"Anna <anna{i}@example.de>", "subject": f"Betreff {i}", "date": NOW - datetime.timedelta(days=days, minutes=i),
            "unread": unread}


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (mail._find, mail.get, mail._Session, mail.VIEW_BUDGET)
        self.accts = [A1, A2]
        mail.get = lambda uid: {"accounts": list(self.accts)}
        self.calls, self.delay = [], 0.0
        self.boxes = {A1["id"]: {1: head(1), 2: head(2, unread=False)}, A2["id"]: {7: head(3)}}

        def fake(acct, words, days, unread, limit):
            self.calls.append(acct["id"])
            time.sleep(self.delay)
            got = [(acct["id"], u, h) for u, h in self.boxes[acct["id"]].items() if h["unread"] or not unread]
            return sorted(got, key=lambda x: x[2]["date"], reverse=True)[:limit]
        mail._find = fake
        self.clear()

    def clear(self):
        mail._cache.clear()
        mail._bodies.clear()
        mail._inflight.clear()
        mail._used.clear()
        mail._supplied.clear()
        mail._live.clear()
        mailvorrat._v.clear()   # the Mail-Vorrat of earlier tests (memory)

    def tearDown(self):
        for ev in list(mail._inflight.values()):
            ev.wait(5)
        mail._find, mail.get, mail._Session, mail.VIEW_BUDGET = self.saved
        self.clear()


class Listing(Base):
    def test_mailboxes_at_the_same_time(self):
        self.delay = 0.4
        t0 = time.time()
        found, errors, many = mail.find("u1", "", 14, False, 50)
        self.assertLess(time.time() - t0, 0.75)          # both together, not 0.8 s one after the other
        self.assertEqual(sorted(self.calls), [A1["id"], A2["id"]])
        self.assertEqual(len(found), 3)
        self.assertTrue(many)

    def test_page_at_once_from_an_older_listing(self):
        old = time.time() - mail.CACHE_SECONDS - 5
        mail._cache[("u1", "", 14, False, mail.INBOX_MAX)] = (old, ([(A1["id"], 1, head(1))], [], True))
        self.delay = 0.3
        t0 = time.time()
        d = mail.inbox("u1")
        self.assertLess(time.time() - t0, 0.2)
        self.assertEqual([x["id"] for x in d["items"]], [f"{A1['id']}:1"])
        ev = mail._inflight.get(("u1", "", 14, False, mail.INBOX_MAX))
        self.assertIsNotNone(ev)                          # and fetched anew behind
        ev.wait(5)
        self.assertEqual(len(mail.inbox("u1")["items"]), 3)

    def test_without_a_listing_loading_then_there(self):
        self.delay = 0.3
        d = mail.inbox("u1", budget=0.05)
        self.assertTrue(d["loading"])
        self.assertEqual(d["items"], [])
        time.sleep(0.5)
        d = mail.inbox("u1", budget=0.05)
        self.assertFalse(d.get("loading"))
        self.assertEqual(len(d["items"]), 3)
        self.assertEqual(len(self.calls), 2)              # one fetch for the two mailboxes, the second look cached

    def test_one_fetch_for_many_and_the_shorter_one_from_the_cache(self):
        self.delay = 0.2
        res = []
        ts = [threading.Thread(target=lambda: res.append(mail.find("u1", "", 14, False, 50))) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(self.calls), 2)              # three readers, one fetch (two mailboxes)
        found, _, _ = mail.find("u1", "", 7, True, 8)     # the assistant's unread of a week
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(sorted(u for _, u, _ in found), [1, 7])

    def test_ordering_changes_the_listing_at_once(self):
        mail.find("u1", "", 14, False, 50)
        mail.find("u1", "", 14, True, 50)
        mail.changed("u1", f"{A1['id']}:1", "read")
        items = {u: h for _, u, h in mail.find("u1", "", 14, False, 50)[0]}
        self.assertFalse(items[1]["unread"])
        self.assertNotIn(1, [u for _, u, _ in mail.find("u1", "", 14, True, 50)[0]])
        mail.changed("u1", f"{A2['id']}:7", "archive")
        self.assertNotIn(7, [u for _, u, _ in mail.find("u1", "", 14, False, 50)[0]])
        self.assertEqual(len(self.calls), 2)              # the unread one came from the cache, and no new fetch after

    def test_a_change_during_a_fetch_stores_nothing_old(self):
        self.delay = 0.2
        ev = mail._start(("u1", "", 14, False, 50), self.accts, [], 14, False, 50)
        time.sleep(0.05)
        mail._drop("u1")
        ev.wait(5)
        self.assertNotIn(("u1", "", 14, False, 50), mail._cache)


class Bodies(Base):
    def test_opened_once_then_from_memory_and_ahead(self):
        sessions = []
        raw = b"From: anna@example.de\r\nSubject: Hallo\r\n\r\nDer Wagen ist fertig.\r\n"

        class S:
            def __init__(self, acct, folder="INBOX"):   # the signature of mail._Session
                sessions.append(acct["id"])

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def body(self, u, most=0):
                return email.message_from_bytes(raw, policy=email.policy.default)
        mail._Session = S
        m1 = mail.message("u1", f"{A1['id']}:1")
        m2 = mail.message("u1", f"{A1['id']}:1")
        self.assertIs(m1, m2)
        self.assertEqual(sessions, [A1["id"]])
        mail.find("u1", "", 14, False, mail.INBOX_MAX)
        self.assertEqual(mail.prefetch("u1"), 2)           # the other two, one session per mailbox
        self.assertEqual(sorted(sessions), sorted([A1["id"], A1["id"], A2["id"]]))
        # at most BODY_MAX per profile
        for i in range(mail.BODY_MAX + 5):
            mail._keep_body(("u1", f"{A1['id']}:{100 + i}"), m1)
        self.assertEqual(sum(1 for k in mail._bodies if k[0] == "u1"), mail.BODY_MAX)
        # archived on the page: no longer served from memory
        mail.changed("u1", f"{A1['id']}:{100 + mail.BODY_MAX + 4}", "archive")
        self.assertNotIn(("u1", f"{A1['id']}:{100 + mail.BODY_MAX + 4}"), mail._bodies)


class Fresh(Base):
    def test_keep_fresh_only_for_recent_readers(self):
        helpers.set_config(mail=True)
        ahead = []
        saved = mail.prefetch
        mail.prefetch = lambda uid, limit=mail.PREFETCH: ahead.append(uid) or 0
        now = time.time()
        mail._used.update({"u1": now - 60, "u2": now - mail.WARM_SECONDS - 60})
        try:
            people, _ = mail.keep_fresh(now)
            self.assertEqual(people, 1)
            # the page's listing and the Mail-Vorrat's longer one (mailvorrat.HEADS a mailbox, every SUPPLY_EVERY)
            self.assertEqual(sorted(self.calls), [A1["id"], A1["id"], A2["id"], A2["id"]])
            self.assertEqual(ahead, ["u1"])
            self.assertNotIn("u2", mail._used)
            self.calls.clear()
            mail.keep_fresh(now)
            self.assertEqual(self.calls, [])              # fresh now: nothing fetched
        finally:
            mail.prefetch = saved


if __name__ == "__main__":
    unittest.main()
