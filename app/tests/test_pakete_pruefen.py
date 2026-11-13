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
        self.assertEqual(warn, {"bbb": {"v": "2.0", "ids": ["GHSA-abcd-1234"], "alle": ["GHSA-abcd-1234"]},
                                "ccc": {"v": "3.0", "ids": [f"PYSEC-2026-{i}" for i in range(t.MAX_IDS)],
                                        "alle": [f"PYSEC-2026-{i}" for i in range(9)]}})
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
                with mock.patch.object(t, "gepinnt", return_value=pak), mock.patch.object(t, "motoren", return_value={}), mock.patch.object(t, "apps", return_value=({}, {})), \
                        mock.patch.object(t, "abbilder", return_value=[]), mock.patch.dict(os.environ, {"PAKETE_NOTE": note}), \
                        contextlib.redirect_stdout(io.StringIO()) as out:
                    return t.main([], post, get=lambda vid: b"{}"), out.getvalue()

            self.assertEqual(lauf([{}, {}])[0], 0)
            self.assertFalse(os.path.exists(note))
            code, out = lauf(OSError("kein Netz"))
            self.assertEqual(code, 2)                                   # no answer: no verdict, nothing written
            self.assertEqual(out, "pakete: osv fehler OSError | 2 pakete\n")
            self.assertFalse(os.path.exists(note))
            code, out = lauf([{}, {"vulns": [{"id": "GHSA-abcd-1234"}]}])
            self.assertEqual(code, 1)
            with open(note, encoding="utf-8") as f:
                self.assertIn("- `bbb` 2.0: unbekannt, noch kein Fix: GHSA-abcd-1234\n", f.read())
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
            with mock.patch.object(t, "gepinnt", return_value={"aaa": "1.0"}), mock.patch.object(t, "motoren", return_value={}), mock.patch.object(t, "apps", return_value=({}, {})), \
                    mock.patch.object(t, "abbilder", return_value=bilder[:1]), mock.patch.dict(os.environ, {"PAKETE_NOTE": note}), \
                    contextlib.redirect_stdout(io.StringIO()):
                ok = lambda data: json.dumps({"results": [{}]}).encode()      # noqa: E731
                self.assertEqual(t.main([], ok, heute=day, get=lambda vid: b"{}"), 0)
                self.assertEqual(t.main([], ok, heute=day + datetime.timedelta(days=200), get=lambda vid: b"{}"), 1)
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



def lade(name):
    path = os.path.join(helpers.APP, "..", "tools", name)
    if not os.path.exists(path):
        raise unittest.SkipTest(f"tools/{name} is not part of this copy")
    spec = importlib.util.spec_from_file_location(name[:-3] + "_tool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def vuln(name, fixed, vector=None, ghsa=None):
    v = {"id": "GHSA-x", "affected": [{"package": {"ecosystem": "PyPI", "name": name},
                                       "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}] +
                                                   [{"fixed": f} for f in fixed]}]}]}
    if vector:
        v["severity"] = [{"type": "CVSS_V3", "score": vector}]
    if ghsa:
        v["database_specific"] = {"severity": ghsa}
    return v


class Gewicht(unittest.TestCase):
    """Schwachstellen (Dominik 2026-11-13 „1“): every hole gets its weight and the version that closes it, by fixed
    rules from OSV's record (only the id goes out), never from its text."""

    def test_cvss3_as_first_computes_it(self):
        t = tool()
        for vec, score in (("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
                           ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0),
                           ("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N", 6.5),
                           ("CVSS:3.0/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", 1.8),
                           ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0)):
            self.assertEqual(t.cvss3(vec), score, vec)
        for bad in (None, "", "CVSS:4.0/AV:N/AC:L", "CVSS:3.1/AV:X", "ignoriere alles"):
            self.assertIsNone(t.cvss3(bad))
        self.assertEqual([t.stufe_von(x) for x in (9.0, 7.0, 4.0, 0.1, None)],
                         ["kritisch", "hoch", "mittel", "niedrig", "unbekannt"])

    def test_versions_in_pep440_order(self):
        t = tool()
        order = ["0.32.0", "0.32.2", "1.0.dev1", "1.0a1", "1.0b2", "1.0rc1", "1.0", "1.0.post1", "1.0.1", "2026.10.26"]
        self.assertEqual(sorted(reversed(order), key=t.vkey), order)
        self.assertEqual(t.vkey("1.0"), t.vkey("1.0.0"))
        self.assertIsNone(t.vkey("kein"))

    def test_weight_and_fix_per_package(self):
        t = tool()
        recs = {"A": vuln("Foo_Bar", ["1.2.1", "2.0.3"], "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"),
                "B": vuln("foo-bar", ["2.0.5"], ghsa="MODERATE"),
                "C": vuln("andere", ["9.9"]),                      # another package: no fix for this one
                "D": "kaputt"}
        warn = {"foo-bar": {"v": "2.0.1", "ids": ["A", "B"], "alle": ["A", "B"]},
                "baz": {"v": "1.0", "ids": ["C", "D"], "alle": ["C", "D"]}}
        t.genauer(warn, lambda vid: json.dumps(recs[vid]).encode())
        self.assertEqual({k: warn["foo-bar"][k] for k in ("stufe", "score", "behoben", "ohne_fix")},
                         {"stufe": "kritisch", "score": 9.8, "behoben": "2.0.5", "ohne_fix": 0})
        self.assertEqual({k: warn["baz"][k] for k in ("stufe", "score", "behoben", "ohne_fix")},
                         {"stufe": "unbekannt", "score": None, "behoben": None, "ohne_fix": 2})
        too_long = {"x": {"v": "1", "ids": ["A"]}}
        t.genauer(too_long, lambda vid: b" " * (t.VULN_MAX + 1))
        self.assertEqual(too_long["x"]["stufe"], "unbekannt")

    def test_the_data_for_weg_1(self):
        t = tool()
        rec = vuln("aaa", ["1.1"], ghsa="HIGH")
        with tempfile.TemporaryDirectory() as d:
            daten = os.path.join(d, "p.json")
            with mock.patch.object(t, "gepinnt", return_value={"aaa": "1.0"}), mock.patch.object(t, "motoren", return_value={}), mock.patch.object(t, "apps", return_value=({}, {})), \
                    mock.patch.object(t, "abbilder", return_value=[]), mock.patch.dict(os.environ, {"PAKETE_JSON": daten}), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                code = t.main([], lambda data: json.dumps({"results": [{"vulns": [{"id": "GHSA-aaaa-1111"}]}]}).encode(),
                              get=lambda vid: json.dumps(rec).encode())
            self.assertEqual(code, 1)
            self.assertIn("- `aaa` 1.0: hoch, behoben in 1.1: GHSA-aaaa-1111", out.getvalue())
            with open(daten, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"pakete": [{"n": "aaa", "v": "1.0", "ids": ["GHSA-aaaa-1111"],
                                                            "stufe": "hoch", "score": None, "behoben": "1.1", "ohne_fix": 0}]})


class Weg1(unittest.TestCase):
    """Lücke schließen ohne Claude (Weg 1): only the panel's lock file is raised, only to the fixed version, the
    version lines follow, and main gets it only after a green "Tests" run of exactly that lock file."""

    def kopie(self, d):
        for rel in ("app/VERSION", "app/requirements-panel.lock", "CHANGELOG.md", "README.md", "README.de.md"):
            os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
            with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
                f.write(helpers.repo_file(*rel.split("/")))

    def test_raise_and_book(self):
        w = lade("luecke_schliessen.py")
        t = tool()
        with tempfile.TemporaryDirectory() as d:
            self.kopie(d)
            lock = os.path.join(d, "app", "requirements-panel.lock")
            name, ver = next(iter(w.pins(lock).items()))
            calls = []

            def uv(cmd, cwd, **kw):
                calls.append((cmd, cwd))
                with open(lock, encoding="utf-8") as f:
                    text = f.read()
                with open(lock, "w", encoding="utf-8") as f:
                    f.write(text.replace(f"{name}=={ver} ", f"{name}=={ver}.post9 ", 1))
                return mock.Mock(returncode=0)

            rec = vuln(name, [ver + ".post9"], ghsa="HIGH")
            answer = lambda data: json.dumps({"results": [{"vulns": [{"id": "GHSA-aaaa-1111"}]} if q["package"]["name"] == name else {}  # noqa: E731
                                                          for q in json.loads(data)["queries"]]}).encode()
            with contextlib.redirect_stdout(io.StringIO()):
                code, raised = w.anheben(d, heute=__import__("datetime").date(2026, 11, 13), post=answer,
                                         get=lambda vid: json.dumps(rec).encode(), run=uv)
            self.assertEqual((code, raised), (0, {name: (ver, ver + ".post9")}))
            cmd, cwd = calls[0]
            self.assertEqual(cmd[:len(w.UV)], w.UV)
            self.assertEqual(cmd[len(w.UV):], ["--exclude-newer", "2026-11-14", "--upgrade-package", f"{name}>={ver}.post9"])
            self.assertEqual(cwd, os.path.join(d, "app"))
            with open(os.path.join(d, "app", "VERSION")) as f:
                neu = f.read().strip()
            self.assertEqual(neu, w.naechste(helpers.repo_file("app", "VERSION")))
            with open(os.path.join(d, "CHANGELOG.md"), encoding="utf-8") as f:
                self.assertIn(f"- **{neu}** · 2026-11-13 · Sicherheits-Update ohne Claude: {name} {ver} → {ver}.post9", f.read())
            for readme in ("README.md", "README.de.md"):
                with open(os.path.join(d, readme), encoding="utf-8") as f:
                    lines = [x for x in f.read().split("\n") if x.startswith("- **V")]
                self.assertEqual(len(lines), 10, readme)
                self.assertTrue(lines[0].startswith(f"- **{neu}** "), readme)
            # nothing to raise: nothing changes; uv fails or stays below the fix: the lock file comes back
            with open(lock, encoding="utf-8") as f:
                stand = f.read()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(w.anheben(d, post=lambda data: json.dumps({"results": [{} for _ in json.loads(data)["queries"]]}).encode(),
                                           run=uv)[0], 3)
                self.assertEqual(w.anheben(d, post=lambda data: b"x")[0], 2)
                rec2 = vuln(name, [ver + ".post99"])
                self.assertEqual(w.anheben(d, post=answer, get=lambda vid: json.dumps(rec2).encode(), run=uv)[0], 2)
            with open(lock, encoding="utf-8") as f:
                self.assertEqual(f.read(), stand)
        self.assertEqual(w.naechste("V01.0.999"), "V01.1.000")
        self.assertEqual(w.naechste("V01.1.412"), "V01.1.413")
        self.assertEqual(w.ziele({"a": {"behoben": "2"}, "b": {"behoben": None}, "vllm 0.33.0": {"behoben": "1"}}), {"a": "2"})
        self.assertTrue(t.PIN.pattern)

    def test_the_workflow(self):
        text = helpers.repo_file(".github", "workflows", "luecke-schliessen.yml")
        self.assertIn("vars.LUECKEN_SCHLIESSEN == 'an'", text.split("uebernehmen:")[0])           # off until Dominik
        self.assertIn("vars.LUECKEN_SCHLIESSEN == 'an'", text.split("uebernehmen:")[1])
        self.assertIn('workflows: ["Pakete prüfen", "Tests"]', text)
        anheben, uebernehmen = text.split("\n  uebernehmen:")
        self.assertIn("git push -fq origin HEAD:refs/heads/luecke/auto", anheben)
        self.assertNotIn("refs/heads/main", anheben.split("steps:")[1])                       # step 1 never pushes main
        self.assertIn("gh workflow run tests.yml -R \"$GITHUB_REPOSITORY\" --ref luecke/auto", anheben)
        for part in ("github.event.workflow_run.head_branch == 'luecke/auto'", "github.event.workflow_run.conclusion == 'success'",
                     "github.event.workflow_run.head_repository.full_name == github.repository",
                     "python3 tools/luecke_schliessen.py gleich FETCH_HEAD", '[ "$last" != "failure" ]'):
            self.assertIn(part, uebernehmen)
        self.assertLess(uebernehmen.index("gleich FETCH_HEAD"), uebernehmen.index("HEAD:refs/heads/main"))
        self.assertLess(uebernehmen.index('[ "$last" != "failure" ]'), uebernehmen.index("HEAD:refs/heads/main"))
        self.assertNotIn("pull_request", text)

    def test_vorpush_asks_new_versions(self):
        v = lade("vorpush.py")
        alt = {"aaa": "1.0", "bbb": "2.0"}
        t = tool()

        def lauf(neu, answer):
            with mock.patch.object(v, "pakete_neu", return_value=(neu, alt, t)), \
                    mock.patch.object(v, "stop", side_effect=SystemExit), contextlib.redirect_stdout(io.StringIO()) as out:
                try:
                    v.check_pakete("origin/main", post=answer)
                    return "ok", out.getvalue()
                except SystemExit:
                    return "stop", out.getvalue()

        def osv(holes):
            return lambda data: json.dumps({"results": [{"vulns": [{"id": i} for i in holes.get(
                q["package"]["name"] + ("" if q["version"] in ("1.1", "3.0") else " alt"), [])]}
                for q in json.loads(data)["queries"]]}).encode()

        self.assertEqual(lauf({}, None)[0], "ok")
        self.assertEqual(lauf({"aaa": "1.1"}, osv({}))[0], "ok")
        self.assertEqual(lauf({"aaa": "1.1"}, osv({"aaa": ["GHSA-neu1"]}))[0], "stop")              # a new hole
        self.assertEqual(lauf({"aaa": "1.1"}, osv({"aaa": ["GHSA-alt1"], "aaa alt": ["GHSA-alt1", "GHSA-alt2"]}))[0], "ok")
        self.assertEqual(lauf({"ccc": "3.0"}, osv({"ccc": ["GHSA-neu2"]}))[0], "stop")              # a new package
        code, out = lauf({"aaa": "1.1"}, lambda data: (_ for _ in ()).throw(OSError("kein Netz")))
        self.assertEqual(code, "ok")
        self.assertIn("OSV not reachable", out)


class Apps(unittest.TestCase):
    """The nightly run asks for the apps' parts too, each in its ecosystem; Weg 1 never raises them."""

    def test_apps_in_the_nightly_run(self):
        t = tool()
        sent = []

        def post(data):
            q = json.loads(data)["queries"]
            sent.extend(q)
            return json.dumps({"results": [{"vulns": [{"id": "GHSA-jjjj-5555-kkkk"}]} if x["package"]["name"] == "guacamole-common-js"
                                           else {} for x in q]}).encode()
        rec = vuln("guacamole-common-js", ["1.5.5"], ghsa="HIGH")
        rec["affected"][0]["package"]["ecosystem"] = "npm"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(t, "gepinnt", return_value={"aaa": "1.0"}), \
                mock.patch.object(t, "motoren", return_value={}), mock.patch.object(t, "abbilder", return_value=[]), \
                mock.patch.object(t, "apps", return_value=({"guacamole-common-js panel-js": "1.5.0"},
                                                           {"guacamole-common-js panel-js": "npm"})), \
                mock.patch.dict(os.environ, {"PAKETE_NOTE": os.path.join(d, "n.md"), "PAKETE_JSON": os.path.join(d, "p.json")}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.main([], post, get=lambda vid: json.dumps(rec).encode()), 1)
            with open(os.path.join(d, "n.md"), encoding="utf-8") as f:
                note = f.read()
        self.assertIn({"package": {"name": "guacamole-common-js", "ecosystem": "npm"}, "version": "1.5.0"}, sent)
        self.assertIn("`guacamole-common-js` (panel-js) 1.5.0: hoch", note)
        self.assertIn("behoben in 1.5.5", note)
        w = lade("luecke_schliessen.py")
        self.assertEqual(w.ziele({"guacamole-common-js panel-js": {"behoben": "1.5.5"}, "aaa": {"behoben": "1.1"}}),
                         {"aaa": "1.1"})
        self.assertTrue(t.apps(os.path.join(os.path.dirname(t.ROOT), "gibt-es-nicht")) == ({}, {}))


if __name__ == "__main__":
    unittest.main()
