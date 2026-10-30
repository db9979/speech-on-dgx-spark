"""Finden, Stufe E: die Messung (fundmessung.py, plan such-index §8 E).

- 50 000 synthetic mails (sealed like real mail, every fifth with an attachment, the first 1 000 as real MIME
  messages) and 5 000 documents in a throw-away index: the search stays fast (generous limits here, the GitHub runner
  is slower than the Pi and shared; the plan's goal on the Pi is 95 % below 150 ms), reading in per 1000, the size of
  fund.db and the RAM stay within bounds. Numbers only: the journal line, state/fundmessung.json and Live.
- The search reads no longer every id of its sources into a set (fund._Erlaubt asks SQL only for the candidates) and
  looks up only the keys a list brings (fund._ext_ids), the sender filter first in SQL (fund._klar_absender): the same
  hits in the same order with the same scores as the old way, on the big index.
- The command line (sudo speech-spark finden messen) runs in its own folder beside users/, removes it afterwards,
  never touches a profile and never makes the Spark's key.
Fixed data (a seed), a fixed moment for its dates; nothing depends on the clock but the measured times themselves.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from tests import helpers

helpers.start()
import fund  # noqa: E402
import fundmessung  # noqa: E402
import vorrat  # noqa: E402

UID = "fundmessung-test"
# generous limits for the shared GitHub runner; the Pi's own numbers come from sudo speech-spark finden messen
P95_MS = 1500
P50_MS = 600
EINLESEN_1000_S = 90
SCHREIBEN_1000_S = 45
DB_MB = 700
RAM_ZUWACHS_MB = 600
FREI = (("dokument", "nas", "mail", "anhang"), [fundmessung.KONTO], None)


class _AlleIds:
    """The old way (Stufe B to D): every id of the search's conditions read into a set first."""
    def __init__(self, con, where, args, ok_ids):
        self.ids = {r[0] for r in con.execute(f"SELECT id FROM fund_item WHERE {where}", args)}
        if ok_ids is not None:
            self.ids &= ok_ids

    def vorab(self, ids):
        pass

    def __contains__(self, iid):
        return iid in self.ids


class Messung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.r = fundmessung.messen(UID, fundmessung.MAILS, fundmessung.DOKUMENTE)
        cls.addClassCleanup(lambda: [os.remove(p) for p in (fund.db_path(UID), fund.db_path(UID) + "-wal",
                                                            fund.db_path(UID) + "-shm") if os.path.exists(p)])

    def test_50000_mails_and_5000_documents_stay_fast(self):
        r = self.r
        print("\nfund messung (container):", fundmessung.zeile(r), file=sys.stderr)
        self.assertEqual((r["mails"], r["anhaenge"], r["dokumente"]), (50_000, 10_000, 5_000))
        with fund._Db(UID) as con:
            n = dict(con.execute("SELECT quelle, COUNT(*) FROM fund_item GROUP BY quelle").fetchall())
        self.assertEqual(n, {"mail": 50_000, "anhang": 10_000, "dokument": 200, "nas": 4_800})
        self.assertGreater(r["mit_treffer"], r["suchen"] // 2)                 # the searches find something
        self.assertLess(r["p50_ms"], P50_MS)
        self.assertLess(r["p95_ms"], P95_MS)
        self.assertLessEqual(r["p50_ms"], r["p95_ms"])
        self.assertLessEqual(r["p95_ms"], r["max_ms"])
        self.assertLess(r["einlesen_1000_s"], EINLESEN_1000_S)
        self.assertLess(r["schreiben_1000_s"], SCHREIBEN_1000_S)
        self.assertLess(r["db_mb"], DB_MB)
        self.assertLess(r["ram_zuwachs_mb"], RAM_ZUWACHS_MB)
        self.assertEqual(r["ziel_ms"], 150)

    def test_sealed_like_real_mail(self):
        with open(fund.db_path(UID), "rb") as f:
            raw = f.read()
        for word in (b"Ihre Rechnung", b"Gesamtbetrag", b"service@", b"beleg.txt"):   # only in mails and attachments
            self.assertNotIn(word, raw, word)

    def test_same_hits_as_reading_every_id(self):
        d = fundmessung.Daten(23)
        qs = [d.frage() for _ in range(40)] + [("Rechnung", {"firma": "Thomann"}), ("", {"kategorie": "Rechnung"}),
                                               ("", {"von": "2020-01-01", "bis": "2020-12-31"})]
        new = [fund.suche(UID, w, now=fundmessung.NOW, frei=FREI, **f) for w, f in qs]
        old_class = fund._Erlaubt
        fund._Erlaubt = _AlleIds
        try:
            old = [fund.suche(UID, w, now=fundmessung.NOW, frei=FREI, **f) for w, f in qs]
        finally:
            fund._Erlaubt = old_class
        self.assertTrue(any(new))
        for (w, f), a, b in zip(qs, new, old):
            self.assertEqual([(h["id"], h["score"]) for h in a], [(h["id"], h["score"]) for h in b], (w, f))

    def test_numbers_only_in_the_log_the_file_and_live(self):
        line = fundmessung.zeile(self.r)
        self.assertTrue(line.startswith("fund: messung | "))
        self.assertLessEqual(set(re.findall(r"[^\W\d_]+", line)), {"fund", "messung", "mails", "anhaenge", "dokumente", "p", "ms",
                                                                 "max", "unter", "einlesen", "s", "je", "db", "mb", "ram", "spitze"})
        fundmessung.behalten(dict(self.r, extra="Thomann"))
        with open(fundmessung._file(), encoding="utf-8") as f:
            kept = json.load(f)
        self.assertEqual(set(kept), set(fundmessung.LIVE_KEYS) - {"schreiben_1000_s"} | ({"schreiben_1000_s"}
                         if self.r.get("schreiben_1000_s") is not None else set()))
        self.assertTrue(all(isinstance(v, (int, float)) for v in kept.values()))
        self.assertEqual(fundmessung.letzte(), kept)
        with open(fundmessung._file(), "w", encoding="utf-8") as f:
            json.dump({"p50_ms": "Thomann", "mails": 3, "x": 1}, f)
        self.assertEqual(fundmessung.letzte(), {"mails": 3})                   # only numbers of the fixed keys
        fundmessung.behalten(self.r)
        helpers.keep_chat(self, "fund")
        helpers.set_config(fund=True)
        fund._live.update(at=0.0, d=None)
        self.assertEqual(fund.for_live()["messung"]["mails"], 50_000)
        import live
        snap = json.dumps(live.snapshot(), ensure_ascii=False)
        self.assertIn("Messung 50000 Mails: p50 ", snap)
        self.assertNotIn("Thomann", snap)


class Rules(unittest.TestCase):
    def test_the_sender_filter_first_in_sql_gives_the_same(self):
        uid = "fundmessung-absender"
        fund.leeren(uid, hand=True)
        names = ["Thomann GmbH", "THOMANN  Musik", "Kelvin Bau", "Kelvin Bau", "Müller & Söhne", "Ölwerk Nord",
                 "Anna \"Quote\" Berg", "Back\\slash", "x"]
        with fund._Db(uid) as con:
            for i, n in enumerate(names):
                fund._put(con, uid, fund.BY_NAME["dokument"], {"ext": f"{i:012x}", "titel": "t", "felder": {"absender": n},
                                                               "worte": "t", "tags": []}, 0)
            for w in ("thomann", "Thomann Musik", "kelvin", "KELVIN BAU", "müller", "ölwerk", "quote", "back\\slash", "x",
                      "fehlt", "elvin"):
                naive = {r[0] for r in con.execute("SELECT id, felder FROM fund_item WHERE schutz=0")
                         if fund.norm(w) in fund.norm(json.loads(r[1] or "{}").get("absender", ""))}
                self.assertEqual(fund._klar_absender(con, w), naive, w)
            self.assertEqual(len(fund._klar_absender(con, "kelvin")), 2)          # the Kelvin sign lowers to k
        fund.leeren(uid, hand=True)

    def test_marks_are_remembered_per_profile_and_key(self):
        a = fund._marke("fundmessung-a", "rechnung")
        self.assertEqual(a, vorrat.marke("fundmessung-a", "rechnung"))
        self.assertEqual(fund._marke("fundmessung-a", "rechnung"), a)
        self.assertNotEqual(fund._marke("fundmessung-b", "rechnung"), a)       # never shared between profiles
        self.assertIs(fund._mk["fundmessung-a"][0], vorrat.key("vorrat"))     # bound to the key it was made with
        self.assertIsNone(fund._marke("", "rechnung"))


class Befehl(unittest.TestCase):
    def run_cli(self, state, users, *args):
        env = dict(os.environ, SPEECH_SPARK_STATE=state, SPEECH_SPARK_USERS=users)
        return subprocess.run([sys.executable, os.path.join(helpers.APP, "panel", "fundmessung.py"), "messen", *args],
                              capture_output=True, text=True, timeout=300, env=env, cwd=os.path.join(helpers.APP, "panel"))

    def test_its_own_folder_never_a_profile(self):
        vorrat.marke("fundmessung-x", "probe")                                  # the test's Spark key exists
        base = tempfile.mkdtemp(prefix="speech-spark-fundmessung-")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", base]))
        users = os.path.join(base, "users")
        os.makedirs(users)
        with open(os.path.join(users, "keep.txt"), "w") as f:
            f.write("x")
        state = os.environ["SPEECH_SPARK_STATE"]
        before = sorted(os.listdir(state))
        out = self.run_cli(state, users, "300", "40")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertRegex(out.stdout, r"fund: messung \| 300 mails \| 60 anhaenge \| 40 dokumente \| p50 ")
        self.assertEqual(sorted(os.listdir(users)), ["keep.txt"])               # no profile touched
        self.assertEqual(sorted(os.listdir(base)), ["users"])                   # its own folder is gone again
        self.assertEqual(sorted(set(os.listdir(state)) - set(before)) in ([], ["fundmessung.json"]), True)
        self.assertEqual(fundmessung.letzte()["mails"], 300)
        # whole numbers only, within the limits
        bad = self.run_cli(state, users, "drei")
        self.assertNotEqual(bad.returncode, 0)

    def test_never_makes_the_key(self):
        base = tempfile.mkdtemp(prefix="speech-spark-fundmessung-")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", base]))
        state, users = os.path.join(base, "state"), os.path.join(base, "users")
        os.makedirs(state)
        os.makedirs(users)
        out = self.run_cli(state, users, "10", "1")
        self.assertEqual(out.returncode, 1)
        self.assertIn("fund: messung abgelehnt | kein schluessel", out.stdout)
        self.assertEqual(os.listdir(state), [])
        self.assertEqual(sorted(os.listdir(base)), ["state", "users"])

    def test_wired_into_the_command_line(self):
        sh = helpers.repo_file("app", "speech-spark.sh")
        self.assertIn("finden) shift; cmd_finden", sh)
        body = sh[sh.index("cmd_finden() {"):]
        body = body[:body.index("\n}\n")]
        self.assertIn('need_root finden messen', body)
        self.assertIn('[[ "$mails" =~ ^[0-9]{1,6}$ && "$docs" =~ ^[0-9]{1,5}$ ]]', body)   # only whole numbers reach it
        for prop in ("-p User=\"$svc\"", "-p Nice=10", "-p MemoryMax=", "-p PrivateTmp=yes", "-p LogNamespace=speech-spark"):
            self.assertIn(prop, body)
        head = sh.splitlines()
        rng = int(re.search(r"sed -n '2,(\d+)p'", sh).group(1))
        self.assertIn("speech-spark finden messen", "\n".join(head[1:rng]))
        self.assertTrue(head[rng].startswith("set -euo"))


if __name__ == "__main__":
    unittest.main()
