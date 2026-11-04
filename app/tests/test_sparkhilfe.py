"""Spontanhilfe S2b, the program SparkHilfe for Windows (spontansteuern.fetch, tools/sparkhilfe/windows, the shared core
tools/begleiter/windows/Sicht.cs; plan spontanhilfe/s2-plan.md): one self-test for every protection rule.

The Spark keeps a program only from GitHub's download addresses of the CI release, only when sparkhilfe.json is signed
(once a key is listed) and size and SHA-256 of every file match; odd names, kinds or sizes keep nothing; an older
release never replaces a newer one; it looks only while the switch is on and the Notaus lets the internet through. The
Dienst-Wächter says whether every program is there with its checksum. The program itself (checked in its source, since
it is built only by CI): it reads host and key only from its file name as /hilfe gives it, connects only there with
wss and normal TLS checks and no Origin, sends the key first and shows the helper's name only after the panel took it,
takes inputs only from the same fixed lists as fernsicht (no Windows key, no Alt+Tab, no Ctrl+Alt+Del) and only after
„Erlauben“ and „Steuern“, sends pictures within MAX_FRAME and FPS; all its texts in German and English. The Begleiter
uses the same core (one source). The workflow pins its actions, publishes only from main in the environment "release"
and signs the manifest only with the key. No test depends on the time of day."""
import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import unittest
import unittest.mock

import httpx

from tests import helpers
from tests.test_spontanhilfe import journal

import dienstwacht as dw  # noqa: E402
import fernsicht  # noqa: E402
import notaus  # noqa: E402
import spontanhilfe as sh  # noqa: E402
import spontansteuern as ss  # noqa: E402

GH = "http://gh.test"
X64 = b"MZ x64 " * 300
ARM = b"MZ arm64 " * 300


def files(x64=X64, arm=ARM):
    return {"SparkHilfe-windows-x64.exe": x64, "SparkHilfe-windows-arm64.exe": arm}


def meta(version, x64=X64, arm=ARM):
    f = lambda n, b: {"name": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    return {"version": version, "files": {"windows-x64": f("SparkHilfe-windows-x64.exe", x64),
                                          "windows-arm64": f("SparkHilfe-windows-arm64.exe", arm)}}


def github(m, assets, tag=ss.TAG, sig=None):
    """A fake GitHub: the release `tag` with sparkhilfe.json (and its .sig) and the files."""
    body = json.dumps(m).encode()
    extra = {ss.MANIFEST: body, **({ss.MANIFEST + ".sig": sig} if sig is not None else {})}
    every = {**assets, **extra}

    def handle(req):
        p = req.url.path
        if p.endswith("/releases/tags/" + tag):
            return httpx.Response(200, json={"tag_name": tag, "assets": [
                {"name": n, "browser_download_url": GH + "/dl/" + n} for n in every]})
        if p.startswith("/dl/") and p[4:] in every:
            return httpx.Response(200, content=every[p[4:]])
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


class _Cache(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "fernzugang", "spontanhilfe", "spontansteuern")
        helpers.set_config(fernzugang=True, spontanhilfe=True, spontansteuern=True)
        shutil.rmtree(ss.CACHE, ignore_errors=True)
        ss._sha.clear()
        ss._upd.update(checked=0.0, error="")
        self.gh = os.environ.get("SPEECH_SPARK_GITHUB_API")
        os.environ["SPEECH_SPARK_GITHUB_API"] = GH

    def tearDown(self):
        shutil.rmtree(ss.CACHE, ignore_errors=True)
        ss._upd.update(checked=0.0, error="")
        if self.gh is None:
            os.environ.pop("SPEECH_SPARK_GITHUB_API", None)
        else:
            os.environ["SPEECH_SPARK_GITHUB_API"] = self.gh

    def fetch(self, m, assets=None, **kw):
        return asyncio.run(ss.fetch(github(m, files() if assets is None else assets, **kw)))


class Fetch(_Cache):
    def test_only_checked_files_are_kept_and_then_offered(self):
        bad = meta("1.1.301")
        bad["files"]["windows-x64"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):                              # a wrong checksum keeps nothing
            self.fetch(bad)
        self.assertEqual(ss.angebot(), {})
        self.assertFalse(os.path.exists(os.path.join(ss.CACHE, "programme.json")))
        for name in ("../evil.exe", "SparkHilfe-x64.bat", "evil.exe"):    # names outside the cache or odd: nothing
            odd = meta("1.1.301")
            odd["files"]["windows-x64"]["name"] = name
            with self.assertRaises(ValueError):
                self.fetch(odd, dict(files(), **{name: X64}))
        for size in (True, 0, -1, 10 ** 12, "300"):                       # sizes that are no size
            odd = meta("1.1.301")
            odd["files"]["windows-x64"]["size"] = size
            with self.assertRaises(ValueError):
                self.fetch(odd)
        missing = meta("1.1.301")                                         # a file the release does not have
        with self.assertRaises(ValueError):
            self.fetch(missing, {"SparkHilfe-windows-x64.exe": X64})
        longer = meta("1.1.301")
        longer["files"]["windows-x64"]["size"] = len(X64) - 1             # more bytes than it says
        with self.assertRaises(ValueError):
            self.fetch(longer)
        with self.assertRaises(ValueError):
            self.fetch(dict(meta("1.1.301"), version="1.1.301; rm"))
        self.assertEqual(ss.angebot(), {})
        unknown = meta("1.1.301")
        unknown["files"]["linux-x64"] = dict(unknown["files"]["windows-x64"])   # a kind the Spark does not offer: skipped
        self.assertEqual(self.fetch(unknown), "1.1.301")
        self.assertEqual(ss.angebot(), {"windows-x64": hashlib.sha256(X64).hexdigest(),
                                        "windows-arm64": hashlib.sha256(ARM).hexdigest()})
        self.assertEqual(sorted(os.listdir(ss.CACHE)), ["SparkHilfe-windows-arm64.exe", "SparkHilfe-windows-x64.exe",
                                                       "programme.json"])

    def test_an_older_release_never_replaces_and_a_missing_file_comes_again(self):
        self.assertEqual(self.fetch(meta("1.1.302")), "1.1.302")
        new = b"MZ newer " * 300
        self.assertEqual(self.fetch(meta("1.1.301", x64=new), files(x64=new)), "1.1.302")
        self.assertEqual(ss.angebot()["windows-x64"], hashlib.sha256(X64).hexdigest())
        os.remove(os.path.join(ss.CACHE, "SparkHilfe-windows-arm64.exe"))   # gone: fetched again at the same version
        self.assertIsNone(ss.programm("windows-arm64"))
        self.assertEqual(self.fetch(meta("1.1.302")), "1.1.302")
        self.assertIsNotNone(ss.programm("windows-arm64"))
        self.assertEqual(self.fetch(meta("1.1.303", x64=new), files(x64=new)), "1.1.303")
        self.assertEqual(ss.angebot()["windows-x64"], hashlib.sha256(new).hexdigest())

    def test_the_manifest_must_be_signed_once_a_key_exists(self):
        import signatur
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                             serialization.PublicFormat.Raw)).decode()
        m = meta("1.1.301")
        body = json.dumps(m).encode()
        with unittest.mock.patch.object(signatur, "KEYS", (pub,)):
            with self.assertRaisesRegex(ValueError, "nicht signiert"):
                self.fetch(m)
            with self.assertRaisesRegex(ValueError, "passt nicht"):
                self.fetch(m, sig=base64.b64encode(other.sign(body)))
            self.assertEqual(ss.angebot(), {})
            self.assertEqual(self.fetch(m, sig=base64.b64encode(key.sign(body))), "1.1.301")
        self.assertEqual(len(ss.angebot()), 2)

    @unittest.mock.patch.dict(os.environ)
    def test_only_github_download_addresses(self):
        os.environ.pop("SPEECH_SPARK_GITHUB_API", None)

        def handle(req):
            if req.url.path.endswith("/releases/tags/" + ss.TAG):
                return httpx.Response(200, json={"assets": [{"name": ss.MANIFEST,
                                                             "browser_download_url": "https://evil.example/sparkhilfe.json"}]})
            return httpx.Response(200, content=b"{}")
        with self.assertRaisesRegex(ValueError, "nicht von GitHub"):
            asyncio.run(ss.fetch(httpx.AsyncClient(transport=httpx.MockTransport(handle))))

    def test_every_result_writes_a_line_with_fixed_words_only(self):
        async def ok(c=None):
            return "1.1.301"

        async def broken(c=None):
            raise ValueError("SparkHilfe-windows-x64.exe: Prüfsumme passt nicht, nichts übernommen.")

        async def nothing(c=None):
            import begleiter
            raise begleiter.NotYet("Im Repo gibt es SparkHilfe noch nicht.")
        for fake, line in ((ok, "spontanhilfe: programm_holen | ok | 1"), (nothing, "spontanhilfe: programm_holen | noch nicht | 0"),
                           (broken, "spontanhilfe: programm_holen | fehler | 0")):
            with unittest.mock.patch.object(ss, "fetch", fake), journal() as j:
                asyncio.run(ss.check())
            self.assertIn(line, j.getvalue())
            self.assertNotIn("Prüfsumme", j.getvalue())
        self.assertTrue(ss._upd["error"])
        self.assertIn("programm_holen", sh.WORDS)

    def test_it_looks_only_while_on_and_the_internet_is_allowed(self):
        self.assertTrue(ss._may_fetch())
        with unittest.mock.patch.object(notaus, "blocks", lambda what: what == "internet"):
            self.assertFalse(ss._may_fetch())
        helpers.set_config(spontansteuern=False)
        self.assertFalse(ss._may_fetch())
        helpers.set_config(spontansteuern=True, spontanhilfe=False)       # the parent off: off too
        self.assertFalse(ss._may_fetch())
        import begleiter
        t = 1_800_000_000.0                                                  # a fixed time, never the clock
        ss._upd.update(checked=0.0, error="")
        self.assertFalse(ss._due(t, t + ss.FIRST - 1))                      # not at once after switching on
        self.assertTrue(ss._due(t, t + ss.FIRST))
        ss._upd.update(checked=t, error="")
        self.assertFalse(ss._due(0.0, t + begleiter.RETRY + 1))             # good: once a day
        self.assertTrue(ss._due(0.0, t + begleiter.FETCH_EVERY + 1))
        ss._upd.update(error="x")
        self.assertTrue(ss._due(0.0, t + begleiter.RETRY + 1))              # after an error: within the hour


class Watch(_Cache):
    def test_the_service_watch_says_whether_every_program_is_there_and_right(self):
        from common import load_config
        cfg = load_config()
        self.assertIn("sparkhilfe", dw.active(cfg=cfg))
        self.assertEqual(dw.SVC["sparkhilfe"][4], "spontanhilfe")
        part = ss.probes()["sparkhilfe"]
        probe = lambda: asyncio.run(dw.probe("sparkhilfe", "sparkhilfe", part, cfg)).ok
        self.assertFalse(probe())                                         # nothing fetched yet
        self.fetch(meta("1.1.301"))
        self.assertTrue(probe())
        with open(os.path.join(ss.CACHE, "SparkHilfe-windows-arm64.exe"), "ab") as f:   # changed afterwards
            f.write(b"evil")
        self.assertFalse(probe())
        helpers.set_config(spontansteuern=False)
        self.assertEqual(ss.probes(), {})
        self.assertNotIn("sparkhilfe", dw.active(cfg=load_config()))


# ---------------------------------------------------------------- the program (its source; built only by CI)
def cs(*parts):
    return helpers.repo_file("tools", *parts)


def block(src, start):
    body = src[src.index(start):]
    return body[:body.index("};")]


class Program(unittest.TestCase):
    def setUp(self):
        self.core = cs("begleiter", "windows", "Sicht.cs")
        self.sitzung = cs("sparkhilfe", "windows", "Sitzung.cs")
        self.ziel = cs("sparkhilfe", "windows", "Ziel.cs")
        self.prog = cs("sparkhilfe", "windows", "Program.cs")
        self.texte = cs("sparkhilfe", "windows", "Texte.cs")
        self.all = "".join(cs("sparkhilfe", "windows", n) for n in sorted(os.listdir(os.path.join(
            helpers.APP, "..", "tools", "sparkhilfe", "windows"))) if n.endswith(".cs"))

    def test_inputs_only_from_the_same_fixed_lists_as_fernsicht(self):
        keys = re.findall(r'\["([a-z]+)"\] =', block(self.core, "ViewKeys = new"))
        self.assertEqual(keys, list(fernsicht.KEYS))
        for vk in ("0x5B", "0x5C", "VkMenu", "VK_MENU", "VkF4", "0x73"):     # Windows keys, Alt (Alt+Tab, Alt+F4)
            self.assertNotIn(vk, block(self.core, "ViewKeys = new"))
        self.assertEqual(re.findall(r'"([a-z]+)"', block(self.core, "Buttons = new")), list(fernsicht.BUTTONS))
        self.assertIn("const int TextMax = %d;" % fernsicht.TEXT_MAX, self.core)
        self.assertIn("const int MaxEvents = %d;" % fernsicht.MAX_EVENTS, self.sitzung)
        self.assertIn('case "key" when Sicht.ViewKeys.ContainsKey(', self.sitzung)
        self.assertIn("Sicht.Buttons.Contains(b)", self.sitzung)
        # inputs only after „Erlauben“ and while the admin's toolbar says „Steuern“
        self.assertIn('case "eingabe" when _mode == "control" && _steuern:', self.sitzung)
        self.assertIn('bool an = _mode == "control" &&', self.sitzung)
        self.assertEqual(self.all.count("Sicht.Apply("), 1)

    def test_pictures_within_the_panels_limits(self):
        self.assertIn("const int MaxFrame = 700 * 1024;", self.sitzung)
        self.assertEqual(700 * 1024, fernsicht.MAX_FRAME)
        gap = int(re.search(r"FrameGap = TimeSpan\.FromMilliseconds\((\d+)\)", self.core).group(1))
        self.assertGreaterEqual(gap, 1000 // ss.FPS)
        self.assertIn("jpeg.Length <= MaxFrame ? jpeg : null", self.sitzung)
        self.assertIn("const int MaxMessage = 16 * 1024;", self.sitzung)
        self.assertEqual(16 * 1024, sh.MAX_MSG)

    def test_only_the_address_in_its_own_name_with_wss_and_normal_tls(self):
        page = helpers.repo_file("app", "panel", "static", "js", "spontanhilfe-seite.js")
        self.assertIn("a.download='SparkHilfe-'+location.host.replace(/[^A-Za-z0-9.-]/g,'_')+'-'+key+'.exe'", page)
        rx = re.search(r'Name = new\(\s*@"([^"]+)"', self.ziel).group(1)
        self.assertIn("(?<key>[A-Za-z0-9_\\-]{22})", rx)                   # spontansteuern.KEY
        self.assertEqual(ss.KEY.pattern, r"[A-Za-z0-9_\-]{22}")
        self.assertIn("Path.GetFileName(Environment.ProcessPath)", self.ziel)
        self.assertIn('new UriBuilder("wss", Host, Port, "/api/hilfe/steuern")', self.ziel)
        self.assertIn("private static int Main()", self.prog)              # no arguments, no settings
        for bad in ("ServerCertificateCustomValidationCallback", "RemoteCertificateValidationCallback", "SetRequestHeader",
                    "\"ws\"", "http://", "ws://", "Registry", "File.Write", "Process.Start", "AllowAutoRedirect"):
            self.assertNotIn(bad, self.all, bad)
        self.assertEqual(self.all.count(".ConnectAsync("), 1)
        self.assertIn("_ws.ConnectAsync(_ziel.Socket,", self.sitzung)
        self.assertIn("public override string ToString() => Shown;", self.ziel)   # never the key in a text

    def test_the_key_first_and_the_helpers_name_only_after_the_panel_took_it(self):
        hallo = self.sitzung.index('["typ"] = "hallo", ["schluessel"] = _ziel.Key')
        took = self.sitzung.index('Str(h, "stand") != "frage"')
        name = self.sitzung.index('_helper = Plain(Str(h, "admin"), HelperMax)')
        ask = self.sitzung.index("new ViewAskForm(Question())")
        self.assertLess(hallo, took)
        self.assertLess(took, name)
        self.assertLess(name, ask)
        self.assertIn('return Texte.T("neu_laden");', self.sitzung[hallo:name])

    def test_every_text_in_german_and_english(self):
        pairs = re.findall(r'\["(\w+)"\] = \((".*?"(?:\s*\+\s*".*?")*),\s*(".*?"(?:\s*\+\s*".*?")*)\)', self.texte, re.S)
        self.assertGreater(len(pairs), 15)
        used = set(re.findall(r'Texte\.(?:T|Raw)\("(\w+)"', self.all))
        self.assertEqual(used - {k for k, _de, _en in pairs}, set())
        for k, de, en in pairs:
            self.assertTrue(de.strip('"') and en.strip('"'), k)
            self.assertEqual(sorted(set(re.findall(r"\{\d\}", de))), sorted(set(re.findall(r"\{\d\}", en))), k)

    def test_the_begleiter_uses_the_same_core(self):
        win = os.path.join(helpers.APP, "..", "tools", "begleiter", "windows")
        if not os.path.isdir(win):
            self.skipTest("tools is not part of this copy")
        srcs = {n: cs("begleiter", "windows", n) for n in os.listdir(win) if n.endswith(".cs")}
        for cls in ("class ViewEdge", "class ViewBar", "class ViewAskForm", "record ViewEvent", "static void Chord(",
                    "static void Type(", "ViewKeys = new", "(byte[] Jpeg, int Width, int Height) Capture("):
            self.assertEqual([n for n, s in srcs.items() if cls in s], ["Sicht.cs"], cls)
        view = srcs["ViewSession.cs"]
        for use in ("Sicht.Capture(_screen)", "Sicht.Apply(_screen, e)", "new ViewAskForm(Question(ask))",
                    "Sicht.ShowFrame(_screen, Title, bar)"):
            self.assertIn(use, view)
        proj = cs("sparkhilfe", "windows", "SparkHilfe.csproj")
        self.assertIn(r'<Compile Include="..\..\begleiter\windows\Sicht.cs"', proj)
        self.assertIn(r'<Compile Include="..\..\begleiter\windows\Theme.cs"', proj)   # the Begleiter's colors, nothing own
        self.assertNotRegex(self.all, r"Color\.FromArgb|#[0-9A-Fa-f]{6}\b")


class Workflow(unittest.TestCase):
    def test_built_only_by_ci_and_published_only_from_main(self):
        wf = helpers.repo_file(".github", "workflows", "sparkhilfe-windows.yml")
        self.assertIn("branches: [main]\n", wf)                           # no test branch left behind
        self.assertNotIn("TEMP", wf)
        pub = wf[wf.index("\n  publish:\n"):]
        self.assertIn("if: github.ref == 'refs/heads/main'", pub)
        self.assertRegex(pub, r"\n    environment: release\b")
        self.assertIn("contents: write", pub)
        self.assertNotIn("contents: write", wf[:wf.index("\n  publish:\n")])
        self.assertIn("tag=" + ss.TAG, pub)
        self.assertIn("dist/" + ss.MANIFEST, wf)
        for art in ss.ARTEN:
            self.assertIn("SparkHilfe-" + art + ".exe", pub)
            self.assertIsNotNone(ss.DATEI.fullmatch("SparkHilfe-" + art + ".exe"))
        self.assertIn('"SparkHilfe Windows"', helpers.repo_file(".github", "workflows", "releases-aufraeumen.yml"))


if __name__ == "__main__":
    unittest.main()
