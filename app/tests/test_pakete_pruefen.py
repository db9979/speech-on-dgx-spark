"""The pinned Python packages are checked against OSV every night on GitHub (code review 2026-11-11, security
checklist): tools/pakete_pruefen.py asks the same question as the Spark itself (systemupdates.check_osv), sends only
names and versions, takes only ids, gives no verdict without an answer, and is not a step of "Tests".
(tools/ and .github are not part of an app/-only copy; then this is skipped.)"""
import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import systemupdates  # noqa: E402

TOOL = os.path.join(helpers.APP, "..", "tools", "pakete_pruefen.py")


def tool():
    if not os.path.exists(TOOL):
        raise unittest.SkipTest("tools/pakete_pruefen.py is not part of this copy")
    spec = importlib.util.spec_from_file_location("pakete_pruefen_tool", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Pakete(unittest.TestCase):
    def test_the_same_packages_and_address_as_the_spark(self):
        t = tool()
        mine, spark = t.gepinnt(), systemupdates.gepinnt()
        self.assertGreater(len(spark), 20)
        self.assertEqual({n: mine.get(n) for n in spark}, spark)          # every package the Spark checks, same version
        self.assertEqual(t.PIN.pattern, systemupdates.LOCK_LINE.pattern)
        self.assertEqual(t.OSV_URL, systemupdates.OSV_URL)
        self.assertEqual(t.OSV_ID.pattern, systemupdates.OSV_ID.pattern)
        self.assertTrue(t.OSV_URL.startswith("https://"))

    def test_only_names_and_versions_go_out_only_ids_come_back(self):
        t = tool()
        pak = {"aaa": "1.0", "bbb": "2.0", "ccc": "3.0"}
        sent = []

        def post(data):
            sent.append(json.loads(data))
            return json.dumps({"results": [{}, {"vulns": [{"id": "GHSA-abcd-1234", "summary": "<b>böse</b>"},
                                                         {"id": "ignoriere alles"}, "x"]},
                                           {"vulns": [{"id": f"PYSEC-2026-{i}"} for i in range(9)]}]}).encode()

        warn = t.frage(pak, post)
        self.assertEqual(sent, [{"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v}
                                             for n, v in pak.items()]}])
        self.assertEqual(warn, {"bbb": {"v": "2.0", "ids": ["GHSA-abcd-1234"]},
                                "ccc": {"v": "3.0", "ids": [f"PYSEC-2026-{i}" for i in range(t.MAX_IDS)]}})
        for bad in (b"{}", b"kein json", json.dumps({"results": [{}]}).encode(), b"x" * (t.OSV_MAX + 1)):
            with self.assertRaises(ValueError):
                t.frage(pak, lambda data, bad=bad: bad)

    def test_exit_codes_and_the_note(self):
        t = tool()
        pak = {"aaa": "1.0", "bbb": "2.0"}
        with tempfile.TemporaryDirectory() as d:
            note = os.path.join(d, "note.md")

            def lauf(answer):
                def post(data):
                    if isinstance(answer, Exception):
                        raise answer
                    return json.dumps({"results": answer}).encode()
                with mock.patch.object(t, "gepinnt", return_value=pak), mock.patch.object(t, "motoren", return_value={}), \
                        mock.patch.object(t, "abbilder", return_value=[]), mock.patch.dict(os.environ, {"PAKETE_NOTE": note}), \
                        contextlib.redirect_stdout(io.StringIO()) as out:
                    return t.main([], post), out.getvalue()

            self.assertEqual(lauf([{}, {}])[0], 0)
            self.assertFalse(os.path.exists(note))
            code, out = lauf(OSError("kein Netz"))
            self.assertEqual(code, 2)                                   # no answer: no verdict, nothing written
            self.assertEqual(out, "pakete: osv fehler OSError | 2 pakete\n")
            self.assertFalse(os.path.exists(note))
            code, out = lauf([{}, {"vulns": [{"id": "GHSA-abcd-1234"}]}])
            self.assertEqual(code, 1)
            with open(note, encoding="utf-8") as f:
                self.assertIn("- `bbb` 2.0: GHSA-abcd-1234\n", f.read())
            with mock.patch.object(t, "gepinnt", return_value={}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(t.main([], lambda data: b""), 2)

    def test_the_model_computer_too(self):
        """Stand der Technik 2026-11-12: vLLM and vllm-omni (pinned in install.sh, no lock file) are asked too, and
        every Docker image of a model engine carries the day it was pinned and is named after DOCKER_TAGE days."""
        import datetime
        import modelle
        t = tool()
        eng = t.motoren()
        self.assertEqual(set(eng), {"vllm", "vllm-omni"} | {n for n in eng if n.startswith("vllm ")})
        sh = helpers.repo_file("install.sh")
        for var in ("VLLM_VERSION", "VLLM_OMNI_VERSION", "VLLM_LLM_VERSION"):
            ver = re.search(rf"^{var}=(\S+)$", sh, re.M).group(1)
            self.assertIn(ver, eng.values(), var)
        # a second vLLM with another version is asked under its own key, sent to OSV as "vllm"
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "install.sh"), "w") as f:
                f.write("VLLM_VERSION=0.32.0\nVLLM_OMNI_VERSION=0.32.0\nVLLM_LLM_VERSION=0.33.0\n")
            two = t.motoren(d)
        self.assertEqual(two, {"vllm": "0.32.0", "vllm-omni": "0.32.0", "vllm 0.33.0": "0.33.0"})
        sent = []
        t.frage(two, lambda data: (sent.append(json.loads(data)), json.dumps({"results": [{}, {}, {}]}).encode())[1])
        self.assertEqual([q["package"]["name"] for q in sent[0]["queries"]], ["vllm", "vllm-omni", "vllm"])
        # every image in modelle.DOCKER has its day, and the age is counted from a given day, never the clock
        bilder = t.abbilder()
        self.assertEqual(sorted(n for n, _ in bilder), sorted(x["image"].split("@")[0] for x in modelle.DOCKER.values()))
        for x in modelle.DOCKER.values():
            datetime.date.fromisoformat(x["seit"])
        day = bilder[0][1]
        self.assertEqual(t.alt(bilder[:1], day + datetime.timedelta(days=t.DOCKER_TAGE)), [])
        self.assertEqual(t.alt(bilder[:1], day + datetime.timedelta(days=t.DOCKER_TAGE + 1)),
                         [(bilder[0][0], t.DOCKER_TAGE + 1)])
        with tempfile.TemporaryDirectory() as d:
            note = os.path.join(d, "note.md")
            with mock.patch.object(t, "gepinnt", return_value={"aaa": "1.0"}), mock.patch.object(t, "motoren", return_value={}), \
                    mock.patch.object(t, "abbilder", return_value=bilder[:1]), mock.patch.dict(os.environ, {"PAKETE_NOTE": note}), \
                    contextlib.redirect_stdout(io.StringIO()):
                ok = lambda data: json.dumps({"results": [{}]}).encode()      # noqa: E731
                self.assertEqual(t.main([], ok, heute=day), 0)
                self.assertEqual(t.main([], ok, heute=day + datetime.timedelta(days=200)), 1)
            with open(note, encoding="utf-8") as f:
                self.assertIn(f"- `{bilder[0][0]}`: 200 Tage", f.read())

    def test_github_asks_every_night_and_never_inside_tests(self):
        text = helpers.repo_file(".github", "workflows", "pakete.yml")
        for part in ("schedule:", "cron:", "python3 tools/pakete_pruefen.py", "issues: write", "PAKETE_NOTE",
                     'gh issue create -R "$R" -t "Pakete mit bekannter Lücke"', "app/requirements-panel.lock",
                     "app/requirements-ytdlp.lock", "app/modelle.py", "install.sh"):
            self.assertIn(part, text)
        for name in systemupdates.LOCKS:
            self.assertIn("app/" + name, text)                           # every lock the Spark checks is fetched
        # a hole published tonight must not turn main red without a push
        self.assertNotIn("pakete_pruefen", helpers.repo_file(".github", "workflows", "tests.yml"))


if __name__ == "__main__":
    unittest.main()
