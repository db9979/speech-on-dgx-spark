"""Spontanhilfe S2c, the program SparkHilfe for the Mac (spontansteuern.mac_teile/mac_zip, tools/sparkhilfe/mac, the core
shared with the Begleiter tools/begleiter/mac/Sources/Sicht.swift; plan spontanhilfe/s2-plan.md): one self-test for every
protection rule.

The Spark keeps the Mac zip only from the release „sparkhilfe-mac“ with signature, size and SHA-256 like Windows, and
only when every entry lies below SparkHilfe.app/ (no way out, no symlink, bounded) with the program, its signature and
the stapled notarization ticket inside. Per help it packs the zip anew in memory with the address her page is on and a
new one-time key in the app's name; the key is never in a header, a log or on the disk, modes and contents stay (so
Apple's signature stays valid). The program itself (checked in its source, since it is built only by CI): it reads host
and key only from its own app name, connects only there with wss, normal TLS checks, no cookies and no Origin, asks for
the two permissions before it uses the key, sends the key first and shows the helper's name only after the panel took
it, „Ablehnen“ first and after 60 seconds, takes inputs only from the core's fixed lists (the same as fernsicht) and only
after „Erlauben“ and „Steuern“; all its texts in German and English. The workflow publishes only from main in the
environment "release" and never without Developer ID, notarization and ticket. No test depends on the time of day."""
import asyncio
import hashlib
import io
import json
import os
import re
import stat
import unittest
import unittest.mock
import zipfile

from tests import helpers
from tests import test_spontansteuern as tss
from tests.test_sparkhilfe import _Cache, github
from tests.test_spontanhilfe import ADMIN, PERSON, journal  # noqa: F401

import fernsicht  # noqa: E402
import spontanhilfe as sh  # noqa: E402
import spontansteuern as ss  # noqa: E402

TAG = "sparkhilfe-mac"
EXE = b"\xcf\xfa\xed\xfe universal " * 200


def app_zip(entries=None, extra=(), drop=(), root="SparkHilfe.app/"):
    """A zip like the CI one: the app with its program (mode 755), Info.plist, signature and stapled ticket."""
    files = entries or {root + "Contents/MacOS/SparkHilfe": (EXE, 0o100755),
                        root + "Contents/Info.plist": (b"<plist/>", 0o100644),
                        root + "Contents/_CodeSignature/CodeResources": (b"<sig/>", 0o100644),
                        root + "Contents/CodeResources": (b"ticket", 0o100644)}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d in (root, root + "Contents/", root + "Contents/MacOS/"):
            i = zipfile.ZipInfo(d, date_time=(2026, 11, 4, 8, 0, 0))
            i.create_system, i.external_attr = 3, (0o40755 << 16) | 0x10
            z.writestr(i, b"")
        for name, (data, mode) in list(files.items()) + list(extra):
            if any(name.endswith(x) for x in drop):
                continue
            i = zipfile.ZipInfo(name, date_time=(2026, 11, 4, 8, 0, 0))
            i.create_system, i.external_attr, i.compress_type = 3, mode << 16, zipfile.ZIP_DEFLATED
            z.writestr(i, data)
    return out.getvalue()


def meta_mac(version, data):
    return {"version": version, "files": {"mac": {"name": "SparkHilfe-mac.zip", "size": len(data),
                                                  "sha256": hashlib.sha256(data).hexdigest()}}}


def fetch_mac(version, data=None):
    data = app_zip() if data is None else data
    return asyncio.run(ss.fetch(github(meta_mac(version, data), {"SparkHilfe-mac.zip": data}, tag=TAG), tag=TAG))


class Fetch(_Cache):
    def test_only_a_complete_app_zip_is_kept(self):
        bad = {
            "a way out": app_zip(extra=[("SparkHilfe.app/../evil", (b"x", 0o100644))]),
            "outside the app": app_zip(extra=[("Other.app/Contents/x", (b"x", 0o100644))]),
            "absolute": app_zip(extra=[("/SparkHilfe.app/x", (b"x", 0o100644))]),
            "a symlink": app_zip(extra=[("SparkHilfe.app/Contents/link", (b"/etc/passwd", 0o120777))]),
            "no ticket": app_zip(drop=("Contents/CodeResources",)),
            "no signature": app_zip(drop=("_CodeSignature/CodeResources",)),
            "too many parts": app_zip(extra=[(f"SparkHilfe.app/Contents/Resources/{n}", (b"", 0o100644))
                                             for n in range(ss.MAC_TEILE)]),
            "no zip": b"PK not a zip",
        }
        for why, data in bad.items():
            with self.assertRaises(ValueError, msg=why):
                fetch_mac("1.1.320", data)
            self.assertIsNone(ss.programm("mac"), why)
            self.assertFalse([n for n in os.listdir(ss.CACHE) if n.endswith(".part")], why)
        self.assertEqual(fetch_mac("1.1.320"), "1.1.320")
        self.assertEqual(ss.angebot(), {"mac": hashlib.sha256(app_zip()).hexdigest()})

    def test_each_release_fills_only_its_own_kinds_and_keeps_the_others(self):
        from tests.test_sparkhilfe import files, meta
        self.assertEqual(asyncio.run(ss.fetch(github(meta("1.1.307"), files()))), "1.1.307")
        self.assertEqual(fetch_mac("1.1.320"), "1.1.320")
        self.assertEqual(sorted(ss.angebot()), ["mac", "windows-arm64", "windows-x64"])   # both releases kept
        odd = meta_mac("1.1.321", app_zip())
        odd["files"]["windows-x64"] = odd["files"].pop("mac")                  # the Mac release cannot fill Windows
        with self.assertRaisesRegex(ValueError, "nennt kein Programm"):
            asyncio.run(ss.fetch(github(odd, {"SparkHilfe-mac.zip": app_zip()}, tag=TAG), tag=TAG))
        exe = meta_mac("1.1.321", EXE)
        exe["files"]["mac"]["name"] = "SparkHilfe-mac.exe"                      # a Mac kind is always a zip
        with self.assertRaises(ValueError):
            asyncio.run(ss.fetch(github(exe, {"SparkHilfe-mac.exe": EXE}, tag=TAG), tag=TAG))
        with self.assertRaisesRegex(ValueError, "Unbekanntes Release"):
            asyncio.run(ss.fetch(github(exe, {}, tag="evil"), tag="evil"))
        self.assertEqual(sorted(ss.angebot()), ["mac", "windows-arm64", "windows-x64"])

    def test_one_look_asks_every_release_with_a_line_each(self):
        seen = []

        async def fake(c=None, tag=None):
            seen.append(tag)
            if tag == TAG:
                import begleiter
                raise begleiter.NotYet("Im Repo gibt es SparkHilfe noch nicht.")
            return "1.1.320"
        with unittest.mock.patch.object(ss, "fetch", fake), journal() as j:
            asyncio.run(ss.check())
        self.assertEqual(seen, list(ss.QUELLEN))
        self.assertEqual(set(ss.QUELLEN), {"sparkhilfe-windows", TAG})
        self.assertIn("spontanhilfe: programm_holen | ok | 1", j.getvalue())
        self.assertIn("spontanhilfe: programm_holen | noch nicht | 0", j.getvalue())
        self.assertTrue(ss._upd["error"])                                       # within the hour again


class Pack(unittest.TestCase):
    def test_the_app_is_renamed_and_nothing_else_changes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "SparkHilfe-mac.zip")
            with open(path, "wb") as f:
                f.write(app_zip())
            key = "A" * 21 + "_"
            out = zipfile.ZipFile(io.BytesIO(ss.mac_zip(path, "spark.example.org_8443", key)))
            src = zipfile.ZipFile(path)
        app = f"SparkHilfe-spark.example.org_8443-{key}.app/"
        self.assertEqual([i.filename for i in out.infolist()], [app + i.filename[len("SparkHilfe.app/"):]
                                                                 for i in src.infolist()])
        for a, b in zip(src.infolist(), out.infolist()):
            self.assertEqual((a.external_attr, a.create_system, a.date_time), (b.external_attr, b.create_system, b.date_time))
            self.assertEqual(src.read(a), out.read(b))
        self.assertTrue(stat.S_IMODE(out.getinfo(app + "Contents/MacOS/SparkHilfe").external_attr >> 16) & 0o111)


class Delivery(tss._On):
    def put_mac(self, data=None):
        os.makedirs(ss.CACHE, exist_ok=True)
        data = app_zip() if data is None else data
        with open(os.path.join(ss.CACHE, "SparkHilfe-mac.zip"), "wb") as f:
            f.write(data)
        with open(os.path.join(ss.CACHE, "programme.json"), "w") as f:
            json.dump({"mac": {"datei": "SparkHilfe-mac.zip", "sha256": hashlib.sha256(data).hexdigest()}}, f)

    def load(self, tok, host="testserver", origin=None):
        return PERSON.post("/api/hilfe/programm", headers={"host": host},
                           json={"tok": tok, "art": "mac", "origin": origin or "http://" + host})

    def test_the_zip_carries_address_and_a_new_key_only_in_the_apps_name(self):
        h, tok = self.open_help()
        self.put_mac()
        self.assertEqual(self.load(tok).status_code, 403)                      # not asked yet
        r, sent = self.ask()
        self.assertEqual(sent[0]["programme"], {"mac": hashlib.sha256(app_zip()).hexdigest()})
        with journal() as j:
            r = self.load(tok, host="spark.example.org:8443")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "application/zip")
        self.assertNotIn("x-spark-schluessel", r.headers)                       # the key never in a header
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(r.headers["x-spark-sha256"], hashlib.sha256(r.content).hexdigest())
        names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        m = re.fullmatch(r"SparkHilfe-spark\.example\.org_8443-([A-Za-z0-9_\-]{22})\.app/", names[0])
        self.assertIsNotNone(m, names[0])
        key = m.group(1)
        self.assertTrue(all(n.startswith(names[0]) for n in names))
        self.assertEqual(h.st.key_h, hashlib.sha256(key.encode()).hexdigest())  # only its hash kept, 10 minutes
        self.assertNotIn(key, j.getvalue())
        self.assertIn("spontanhilfe: programm | mac | 1", j.getvalue())
        self.assertFalse([n for n in os.listdir(ss.CACHE) if key in n])          # never on the disk
        again = self.load(tok, host="spark.example.org:8443")
        key2 = zipfile.ZipFile(io.BytesIO(again.content)).namelist()[0][-27:-5]       # …-<22>.app/
        self.assertNotEqual(key2, key)
        self.assertEqual(h.st.key_h, hashlib.sha256(key2.encode()).hexdigest())   # the one before stops

    def test_only_the_address_her_page_is_on_and_only_a_complete_app(self):
        h, tok = self.open_help()
        self.put_mac()
        self.ask()
        before = h.st.key_h
        for host, origin in (("testserver", "https://evil.example"), ("testserver", ""), ("evil_host", None),
                             ("[::1]:8443", None), ("spark.example.org:0", None), ("spark.example.org:99999", None),
                             ("-spark.example.org", None)):
            with journal() as j:
                r = PERSON.post("/api/hilfe/programm", headers={"host": host},
                                json={"tok": tok, "art": "mac", "origin": "http://" + host if origin is None else origin})
            self.assertEqual(r.status_code, 404, host)
            self.assertIn("spontanhilfe: programm | adresse | 0", j.getvalue())
        self.assertEqual(h.st.key_h, before)                                     # no key handed out
        self.put_mac(app_zip(extra=[("SparkHilfe.app/../evil", (b"x", 0o100644))]))   # changed in the cache
        self.assertEqual(self.load(tok).status_code, 404)
        self.assertEqual(h.st.key_h, before)

    def test_the_program_socket_takes_the_key_from_the_name(self):
        """The key in the app's name is the program's key (the same door as Windows and Linux)."""
        h, tok = self.open_help()
        self.put_mac()
        self.ask()
        names = zipfile.ZipFile(io.BytesIO(self.load(tok).content)).namelist()
        key = re.fullmatch(r"SparkHilfe-testserver-([A-Za-z0-9_\-]{22})\.app/", names[0]).group(1)
        self.assertIsNotNone(ss.KEY.fullmatch(key))
        self.assertTrue(h.st.key_bis > 0)
        self.assertEqual(h.st.key_h, sh._h(key))


# ---------------------------------------------------------------- the program (its source; built only by CI)
def mac(*parts):
    return helpers.repo_file("tools", "sparkhilfe", "mac", *parts)


def core():
    return helpers.repo_file("tools", "begleiter", "mac", "Sources", "Sicht.swift")


def block(src, start, end="\n    ]"):
    body = src[src.index(start):]
    return body[:body.index(end)]


class Program(unittest.TestCase):
    def setUp(self):
        self.core = core()
        d = os.path.join(helpers.APP, "..", "tools", "sparkhilfe", "mac", "Sources")
        self.src = {n: mac("Sources", n) for n in sorted(os.listdir(d)) if n.endswith(".swift")}
        self.all = "".join(self.src.values())

    def test_inputs_only_from_the_same_fixed_lists_as_fernsicht(self):
        keys = re.findall(r'"([a-z]+)": \(kVK_', block(self.core, "static let keys:"))
        self.assertEqual(keys, list(fernsicht.KEYS))
        for bad in ("kVK_Command", "kVK_Option", "kVK_Control", "maskAlternate", "maskControl", "kVK_F4"):
            self.assertNotIn(bad, block(self.core, "static let keys:"))
        self.assertEqual(re.findall(r'"([a-z]+)"', re.search(r"static let buttons: Set<String> = \[([^\]]*)\]",
                                                               self.core).group(1)), list(fernsicht.BUTTONS))
        self.assertIn("static let textMax = %d" % fernsicht.TEXT_MAX, self.core)
        self.assertIn("static let maxEvents = %d" % fernsicht.MAX_EVENTS, self.src["Ereignisse.swift"])
        self.assertIn("case \"eingabe\" where mode == \"control\" && steuern:", self.src["Sitzung.swift"])
        self.assertIn("for e in Ereignisse.clean(m) {", self.src["Sitzung.swift"])
        self.assertIn("let an = mode == \"control\" && (m[\"steuern\"] as? Bool) == true", self.src["Sitzung.swift"])
        self.assertEqual(self.all.count("ViewInput.apply("), 1)
        self.assertIn("guard AXIsProcessTrusted() else { return }", self.core)    # never without Accessibility

    def test_pictures_within_the_panels_limits(self):
        e = self.src["Ereignisse.swift"]
        self.assertIn("static let maxFrame = 700 * 1024", e)
        self.assertEqual(700 * 1024, fernsicht.MAX_FRAME)
        self.assertIn("static let maxMessage = 16 * 1024", e)
        self.assertEqual(16 * 1024, sh.MAX_MSG)
        gap = int(re.search(r"static let frameGap: UInt64 = ([\d_]+)", self.core).group(1).replace("_", ""))
        self.assertGreaterEqual(gap, 1_000_000_000 // ss.FPS)
        self.assertIn("a.data.count <= Ereignisse.maxFrame", self.src["Sitzung.swift"])
        self.assertIn("ws.maximumMessageSize = Ereignisse.maxMessage", self.src["Sitzung.swift"])

    def test_only_the_address_in_its_own_name_with_wss_normal_tls_and_no_origin(self):
        z = self.src["Ziel.swift"]
        self.assertIn("aus(Bundle.main.bundleURL.lastPathComponent)", z)
        self.assertIn('c.scheme = "wss"', z)
        self.assertIn('c.path = "/api/hilfe/steuern"', z)
        self.assertIn("var description: String { shown }", z)               # never the key in a text
        name, hostport, label = re.findall(r'pattern: #"(.*?)"#', z)
        self.assertIn(r"([A-Za-z0-9_\-]{22})", name)                          # spontansteuern.KEY
        self.assertEqual(ss.KEY.pattern, r"[A-Za-z0-9_\-]{22}")

        def parse(n):                                                         # Ziel.aus, the same rules in Python
            m = re.fullmatch(name, n)
            h = m and re.fullmatch(hostport, m.group(1).lower())
            if not h or not all(re.fullmatch(label, x) for x in h.group(1).split(".")):
                return None
            port = int(h.group(2)) if h.group(2) else 443
            return (h.group(1), port, m.group(2)) if 0 < port < 65536 else None
        key = "Ab-_" * 5 + "xy"
        for host in ("spark.i234.me", "spark.example.org:8443", "localhost", "a-b.c-d.example", "testserver"):
            self.assertTrue(ss.HOST.fullmatch(host))
            n = f"SparkHilfe-{host.replace(':', '_')}-{key}.app"            # as spontansteuern.mac_zip names it
            self.assertEqual(parse(n), (host.split(":")[0], int(host.split(":")[1]) if ":" in host else 443, key), n)
        for host in ("evil_host", "[::1]:8443", "-spark.me", "spark..me", "spark.me:", "a" * 64 + ".me", "x.me/../y"):
            self.assertIsNone(ss.HOST.fullmatch(host), host)
        for bad in ("URLSessionDelegate", "didReceive challenge", "serverTrust", "setValue(", "addValue(",
                    "allHTTPHeaderFields", "\"Origin\"", "ws://", "http://", "UserDefaults", "CommandLine",
                    "write(to:", "Process("):
            self.assertNotIn(bad, self.all, bad)
        self.assertNotIn("NSAppTransportSecurity", mac("Info.plist"))      # no exception from Apple's TLS rules
        self.assertEqual(self.all.count("webSocketTask(with:"), 1)
        self.assertIn("cfg.httpShouldSetCookies = false", self.src["Sitzung.swift"])
        self.assertIn("URLSession(configuration: cfg)", self.src["Sitzung.swift"])   # no delegate: normal TLS checks

    def test_permissions_first_then_the_key_then_the_helpers_name(self):
        m = self.src["Main.swift"]
        shot, ax, connect = (m.index("if !CGPreflightScreenCaptureAccess() {"), m.index("if !AXIsProcessTrusted() {"),
                             m.index("Sitzung(ziel: ziel, status: status)"))
        self.assertLess(shot, ax)
        self.assertLess(ax, connect)                                          # the key stays unused until both
        self.assertIn('["Privacy_ScreenCapture", "Privacy_Accessibility"].contains(pane)', m)
        s = self.src["Sitzung.swift"]
        hallo = s.index('try await send(["typ": "hallo", "schluessel": ziel.key, "art": "mac"])')
        took = s.index('h["stand"] as? String == "frage"')
        name = s.index('helper = Ereignisse.plain(h["admin"] as? String ?? "", max: Self.helperMax)')
        ask = s.index("ViewAlert.ask(")
        self.assertLess(hallo, took)
        self.assertLess(took, name)
        self.assertLess(name, ask)
        self.assertIn('return Texte.t("neu_laden")', s[hallo:name])
        self.assertIn('buttons: [Texte.t("ablehnen"), Texte.t("ansehen"), Texte.t("erlauben")],\n'
                      '                                  timeout: 60,', s)
        self.assertIn('var answer = r == 2 ? "control" : r == 1 ? "view" : "no"', s)   # timeout and Return: Ablehnen
        self.assertIn('return (0..<buttons.count).contains(i) ? i : 0', self.core)
        self.assertIn('if answer == "control" && !AXIsProcessTrusted() {', s)            # one sentence, view only

    def test_every_text_in_german_and_english(self):
        pairs = re.findall(r'"(\w+)": \("(.*?)",\s*"(.*?)"\),', self.src["Texte.swift"], re.S)
        self.assertGreater(len(pairs), 20)
        used = set(re.findall(r'Texte\.(?:t|raw)\("(\w+)"', self.all))
        self.assertEqual(used - {k for k, _de, _en in pairs}, set())
        for k, de, en in pairs:
            self.assertTrue(de and en, k)
            self.assertEqual(sorted(set(re.findall(r"\{\d\}", de))), sorted(set(re.findall(r"\{\d\}", en))), k)

    def test_the_begleiter_uses_the_same_core(self):
        d = os.path.join(helpers.APP, "..", "tools", "begleiter", "mac", "Sources")
        srcs = {n: helpers.repo_file("tools", "begleiter", "mac", "Sources", n) for n in os.listdir(d) if n.endswith(".swift")}
        for kind in ("enum ViewKeys", "enum ViewShot", "enum ViewInput", "final class ViewMarks", "enum ViewAlert",
                     "enum Keys", "static func type("):
            self.assertEqual([n for n, s in srcs.items() if kind in s], ["Sicht.swift"], kind)
        view = srcs["Fernsicht.swift"]
        for use in ("ViewShot.take()", "ViewInput.apply(e, display: display)", "ViewMarks(display: display,",
                    "ViewAlert.ask(message: message, info: info, buttons: buttons, timeout: ActCenter.timeout)"):
            self.assertIn(use, view)
        build = mac("build.sh")
        self.assertIn('"$core/Sicht.swift"', build)
        self.assertIn("static let (nsBad|nsOnAccent) = NSColor", build)       # the colours only from Theme.swift
        from tests.test_design_tokens import MAC_LITERAL
        for n, s in self.src.items():
            self.assertNotRegex(s, MAC_LITERAL, n)
        self.assertNotIn("NSColor(hex:", self.core)


class Workflow(unittest.TestCase):
    def test_published_only_from_main_and_never_without_developer_id_and_notarization(self):
        wf = helpers.repo_file(".github", "workflows", "sparkhilfe-mac.yml")
        self.assertIn("branches: [main]\n", wf)                               # no test branch left behind
        self.assertNotIn("TEMP", wf)
        build, pub = wf[:wf.index("\n  publish:\n")], wf[wf.index("\n  publish:\n"):]
        self.assertNotIn("contents: write", build)
        self.assertNotIn("secrets.", build)
        self.assertIn("if: github.ref == 'refs/heads/main'", pub)
        self.assertRegex(pub, r"\n    environment: release\b")
        stop = pub.index("No Developer ID, no Mac program")
        self.assertIn("if: env.HAS_DEVID != 'true'", pub[stop:stop + 200])
        self.assertIn("exit 1", pub[stop:pub.index("\n      - name:", stop + 10)])
        for need in ("secrets.MAC_DEVID_P12 != ''", "secrets.MAC_DEVID_P12_PASSWORD != ''", "secrets.ASC_KEY_ID != ''",
                     "secrets.ASC_ISSUER_ID != ''", "secrets.ASC_KEY != ''"):
            self.assertIn(need, pub)
        order = [pub.index(x) for x in ("codesign --force --timestamp --options runtime", "xcrun notarytool submit",
                                        "xcrun stapler staple", "xcrun stapler validate", "spctl --assess",
                                        'test -f "$app/Contents/CodeResources"', "gh release create")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("if: env.HAS_DEVID == 'true'", pub)                 # signing is no optional step here
        self.assertIn("tag=" + TAG, pub)
        self.assertIn("dist/" + ss.MANIFEST, pub)
        self.assertIsNotNone(ss.DATEI.fullmatch("SparkHilfe-mac.zip"))
        for need in ss.MAC_NEEDS:
            self.assertIn(f'"{need}"', pub)                                   # the Spark's check runs before publishing
        self.assertIn("tools/sparkhilfe/mac/build-pruefung/pruefung\n", build)  # the program's self-test
        self.assertIn("grep -qiE '^(origin|cookie):'", build)
        self.assertIn('== *" x86_64 "*', build)                               # universal
        self.assertIn('"SparkHilfe Mac"', helpers.repo_file(".github", "workflows", "releases-aufraeumen.yml"))


if __name__ == "__main__":
    unittest.main()
