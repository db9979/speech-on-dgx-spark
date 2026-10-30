"""Finden messen (fundmessung.py, plan such-index §8 E; since V01.1.285 the part „fund“ of Wissen messen).

- 50 000 synthetic mails (sealed like real mail, every fifth with an attachment, the first 1 000 as real MIME
  messages) and 5 000 documents in a throw-away index: the search stays fast (generous limits here, the GitHub runner
  is slower than the Pi and shared; the plan's goal on the Pi is 95 % below 150 ms), reading in per 1000, the size of
  fund.db and the RAM stay within bounds; the keys in the form of the other parts (suche_p50_ms …).
- The search reads no longer every id of its sources into a set (fund._Erlaubt asks SQL only for the candidates) and
  looks up only the keys a list brings (fund._ext_ids), the sender filter first in SQL (fund._klar_absender): the same
  hits in the same order with the same scores as the old way, on the big index.
- One way only (Richtlinie Teil 17, eine Quelle): the part runs inside Wissen messen's measuring process, in its run
  folder (never a profile, nothing left), numbers only in the result, the journal and Live; speech stops it between
  two slices; it never makes the Spark's key; there is no command line, unit or state file of its own any more.
Fixed data (a seed), a fixed moment for its dates; nothing depends on the clock but the measured times themselves.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

from tests import helpers

helpers.start()
import fund  # noqa: E402
import fundmessung  # noqa: E402
import profiles  # noqa: E402
import vault  # noqa: E402
import vorrat  # noqa: E402
import wissensmessung as wm  # noqa: E402

UID = "fundmessung-test"
# generous limits for the shared GitHub runner; the Pi's own numbers come from sudo speech-spark wissen messen synth 5000
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
        print("\nfund messung (container):", wm._zeile("fund", r), file=sys.stderr)
        self.assertEqual((r["mails"], r["anhaenge"], r["dokumente"]), (50_000, 10_000, 5_000))
        with fund._Db(UID) as con:
            n = dict(con.execute("SELECT quelle, COUNT(*) FROM fund_item GROUP BY quelle").fetchall())
        self.assertEqual(n, {"mail": 50_000, "anhang": 10_000, "dokument": 200, "nas": 4_800})
        self.assertEqual(r["suche_n"], fundmessung.SUCHEN)
        self.assertGreater(r["mit_treffer"], r["suche_n"] // 2)                # the searches find something
        self.assertLess(r["suche_p50_ms"], P50_MS)
        self.assertLess(r["suche_p95_ms"], P95_MS)
        self.assertLessEqual(r["suche_p50_ms"], r["suche_p95_ms"])
        self.assertLessEqual(r["suche_p95_ms"], r["suche_max_ms"])
        self.assertLess(r["einlesen_1000_s"], EINLESEN_1000_S)
        self.assertLess(r["schreiben_1000_s"], SCHREIBEN_1000_S)
        self.assertLess(r["db_mb"], DB_MB)
        self.assertLess(r["ram_zuwachs_mb"], RAM_ZUWACHS_MB)
        self.assertEqual(r["ziel_ms"], 150)
        self.assertTrue(0 <= r["unter_ziel"] <= 100)
        self.assertEqual(wm._zahlen(r), r)                                     # numbers only, plain keys: kept whole

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

    def test_speech_stops_it_between_two_slices(self):
        class Wm:
            rss_mb, zeiten = staticmethod(wm.rss_mb), staticmethod(wm.zeiten)
            n = 0

            @classmethod
            def ruhe(cls):
                cls.n += 1
                if cls.n > 2:
                    raise wm.Abbruch("sprache")
        with self.assertRaises(wm.Abbruch):
            fundmessung.messen("fundmessung-ruhe", 5_000, 50, wm=Wm)
        self.assertEqual(Wm.n, 3)
        for p in (fund.db_path("fundmessung-ruhe"), fund.db_path("fundmessung-ruhe") + "-wal"):
            if os.path.exists(p):
                os.remove(p)


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


def _kind_state(key=True):
    """The measuring process's own state folder (no other test's speech mark stops it), with the Spark's key."""
    state = tempfile.mkdtemp(prefix="fm-state-")
    if key:
        vorrat.marke("fundmessung-x", "probe")                                  # the test's Spark key exists
        shutil.copy(vault.KEY_FILE, os.path.join(state, "secret.key"))
    return state


class TeilVonWissenMessen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = _kind_state()
        cls.addClassCleanup(shutil.rmtree, cls.state, True)
        os.makedirs(profiles.USERS_DIR, exist_ok=True)
        cls.users_before = sorted(os.listdir(profiles.USERS_DIR))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cls.res = wm.lauf("synth", wm.ANZAHL_MIN, sprache=lambda: False, kind_env={"SPEECH_SPARK_STATE": cls.state})
        cls.lines = [x for x in out.getvalue().splitlines() if x.startswith("wissen:")]

    def test_registered_once_and_measured_in_its_run_folder(self):
        self.assertEqual(list(wm.MESSTEILE).count("fund"), 1)
        self.assertEqual(self.res["status"], "fertig", self.res)
        f = self.res["teile"]["fund"]
        n = wm.ANZAHL_MIN
        self.assertEqual((f["schluessel"], f["dokumente"], f["mails"], f["anhaenge"]),
                         (True, n, n * fundmessung.MAILS_JE_DOKUMENT, n * fundmessung.MAILS_JE_DOKUMENT // fundmessung.ANHANG_JEDE))
        for k in ("suche_p50_ms", "suche_p95_ms", "suche_max_ms", "suche_n", "mit_treffer", "ziel_ms", "unter_ziel",
                  "einlesen_1000_s", "dokumente_1000_s", "db_mb", "kb_je_eintrag", "ram_vorher_mb", "ram_mb",
                  "ram_spitze_mb", "ram_zuwachs_mb"):
            self.assertIn(k, f)
        self.assertLessEqual(f["suche_p50_ms"], f["suche_p95_ms"])
        self.assertEqual(f["suche_n"], fundmessung.SUCHEN)
        # nothing left: no run folder, no throwaway profile among the real ones, no file of its own in state/
        self.assertEqual([x for x in os.listdir(wm.TMP) if x != ".lock"], [])
        self.assertEqual(sorted(os.listdir(profiles.USERS_DIR)), self.users_before)
        self.assertFalse(os.path.exists(fund.db_path(fundmessung.UID)))
        for st in (self.state, os.environ["SPEECH_SPARK_STATE"]):
            self.assertNotIn("fundmessung.json", os.listdir(st))

    def test_numbers_only_in_the_result_the_journal_and_live(self):
        line = next(x for x in self.lines if x.startswith("wissen: messung teil fund | "))
        self.assertRegex(line, r"^wissen: messung teil fund \| dokumente \d+ \| suche p95 \d+ ms \| ram [\d.]+ mb$")
        text = json.dumps(self.res, ensure_ascii=False) + "\n".join(self.lines)
        for word in ("Rechnung", "Thomann", "service@", "beleg", "Gesamtbetrag"):
            self.assertNotIn(word, text)
        self.assertNotIn("messung", fund.for_live())                            # no Live line of its own
        import live
        snap = json.dumps(live.snapshot(), ensure_ascii=False)
        self.assertNotIn("Messung 50000 Mails", snap)
        self.assertNotIn("Thomann", snap)

    def test_never_makes_the_key(self):
        state = _kind_state(key=False)
        self.addCleanup(shutil.rmtree, state, True)
        with contextlib.redirect_stdout(io.StringIO()):
            res = wm.lauf("synth", wm.ANZAHL_MIN, sprache=lambda: False, kind_env={"SPEECH_SPARK_STATE": state})
        self.assertEqual(res["teile"]["fund"], {"schluessel": False})
        self.assertNotIn("secret.key", os.listdir(state))

    def test_only_in_the_measuring_process_and_its_folder(self):
        self.assertFalse(wm._KIND[0])
        with self.assertRaises(RuntimeError):
            wm.teil_fund(tempfile.mkdtemp(prefix="lauf-"), 10)

    def test_one_way_only(self):
        sh = helpers.repo_file("app", "speech-spark.sh")
        for gone in ("cmd_finden", "finden messen", "fundmessung"):
            self.assertNotIn(gone, sh)
        head = sh.splitlines()
        rng = int(re.search(r"sed -n '2,(\d+)p'", sh).group(1))
        self.assertIn("speech-spark wissen messen", "\n".join(head[1:rng]))
        self.assertTrue(head[rng].startswith("set -euo"))
        import dateien
        self.assertNotIn("fundmessung.json", {d.name for d in dateien.DATEIEN})
        for gone in ("main", "behalten", "letzte", "zeile", "LIVE_KEYS"):
            self.assertFalse(hasattr(fundmessung, gone), gone)


if __name__ == "__main__":
    unittest.main()
