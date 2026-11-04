"""Fernzugang, Dateien als anderer Benutzer (fernals.py, ferndateien, anker `dateien`; plan ssh-vermittlung/
dateien-als-benutzer.md, Dominik 2026-11-03 „1“): one self-test per rule. Both consents are needed (the server's
report and the panel's switch per system with a fresh code), only the users the server named, read only through
`sudo -n -u <user> <sftp-server> -R`, writing its own step with a fresh code every session; the anchor's drop-in names
the one program with exact arguments, is checked with visudo and goes on „aus“ and „Entfernen“; Windows gives exactly
the named folders; logs carry no name."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import threading
import types
import unittest
import unittest.mock

from tests import helpers
from tests.test_fernzugang import ADMIN, CODE, HOST_PUB, Base, _Files, _FilesBase, _Server, journal, program  # noqa: F401

import fernals  # noqa: E402
import fernzugang  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SFTP = "/usr/lib/openssh/sftp-server"


def report(**kw):
    return {"art": "sudo", "benutzer": ["root", "anna"], "schreiben": False, "sftp": SFTP, **kw}


class Panel(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(fernals=True)

    def tearDown(self):
        helpers.set_config(fernals=False)
        super().tearDown()

    def test_off_by_default_its_own_switch_under_fernzugang(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["fernals"], False)
        import features
        f = next(x for x in features.FEATURES if x.key == "fernals")
        self.assertEqual(f.parent, "fernzugang")
        helpers.set_config(fernals=False)
        self.assertFalse(fernals.on())
        with self.assertRaises(Exception) as e:
            fernals.choose({"als": report(), "als_frei": True}, "root", False)
        self.assertEqual(e.exception.status_code, 404)

    def test_the_anchor_report_is_checked_and_switches_the_system_off_again(self):
        for bad in ({}, report(art="x"), report(benutzer=[]), report(benutzer=["spark"]), report(benutzer=["Root!"]),
                    report(benutzer=["root", "root"]), report(benutzer=["u%d" % i for i in range(9)]),
                    report(sftp="/bin/sh"), report(sftp="/usr/lib/../../bin/sftp-server"), report(sftp="sftp-server"),
                    report(schreiben="ja"), {"art": "ordner", "ordner": ["C:/"]}, {"art": "ordner", "ordner": ["C:/a/../Windows"]},
                    {"art": "ordner", "ordner": ["/etc"]}):
            self.assertIsNone(fernals.clean(bad), bad)
        self.assertEqual(fernals.clean({"art": "ordner", "ordner": ["C:/Users/Anna/Dokumente"], "schreiben": True}),
                         {"art": "ordner", "schreiben": True, "ordner": ["C:/Users/Anna/Dokumente"]})
        d = self.pair()
        anchor = TestClient(panel.app)
        h = {"Authorization": "Bearer " + d["key"]}
        self.assertEqual(anchor.post("/api/fernzugang/anker/dateien", json=report()).status_code, 403)   # no key
        with journal() as j:
            self.assertEqual(anchor.post("/api/fernzugang/anker/dateien", json=report(sftp="/bin/sh"), headers=h).status_code, 400)
            fernzugang._update(d["id"], als_frei=True)
            self.assertEqual(anchor.post("/api/fernzugang/anker/dateien", json=report(), headers=h).status_code, 200)
        g = fernzugang._read()["geraete"][d["id"]]
        self.assertEqual((g["als"]["benutzer"], g["als_frei"]), (["root", "anna"], False))   # a new report: switch off
        self.assertIn("fernzugang: dateien_als | gemeldet sudo | 2", j.getvalue())
        self.assertNotIn("anna", j.getvalue())
        row = next(x for x in ADMIN.get("/api/admin/fernzugang").json()["geraete"] if x["id"] == d["id"])
        self.assertEqual((row["als"]["benutzer"], row["als_frei"]), (["root", "anna"], False))
        self.assertEqual(anchor.delete("/api/fernzugang/anker/dateien", headers=h).status_code, 200)
        self.assertIsNone(fernzugang._read()["geraete"][d["id"]]["als"])
        helpers.set_config(fernals=False)                                  # the switch off: the list says nothing
        row = next(x for x in ADMIN.get("/api/admin/fernzugang").json()["geraete"] if x["id"] == d["id"])
        self.assertNotIn("als", row)

    def test_the_switch_per_system_wants_a_fresh_code_and_the_servers_report(self):
        d = self.pair()
        url = f"/api/admin/fernzugang/geraete/{d['id']}/als"
        self.assertIn(TestClient(panel.app).post(url).status_code, (401, 403))
        self.assertNotEqual(ADMIN.post(url).status_code, 200)                 # no fresh code
        self.assertEqual(ADMIN.post(url, headers=CODE).status_code, 409)       # the server said nothing yet
        fernzugang._update(d["id"], als=fernals.clean(report()))
        with journal() as j:
            self.assertEqual(ADMIN.post(url, headers=CODE).json(), {"als_frei": True})
            self.assertEqual(ADMIN.delete(url).json(), {"als_frei": False})
        self.assertIn("fernzugang: dateien_als | an | 1", j.getvalue())
        self.assertIn("fernzugang: dateien_als | aus | 1", j.getvalue())

    def test_choose_only_named_users_only_with_both_and_writing_only_when_allowed(self):
        g = {"als": fernals.clean(report()), "als_frei": False}
        self.assertEqual(fernals.choose(g, "", False), ("", False))
        self.assertEqual(fernals.choose(g, "spark", False), ("", False))
        for user, frei, write, code in (("root", False, False, 403), ("bob", True, False, 403), ("root", True, True, 403)):
            with self.assertRaises(Exception) as e:
                fernals.choose({**g, "als_frei": frei}, user, write)
            self.assertEqual(e.exception.status_code, code, (user, frei, write))
        g["als_frei"] = True
        self.assertEqual(fernals.choose(g, "root", False), (f"sudo -n -u root {SFTP} -R", False))
        g["als"]["schreiben"] = True
        self.assertEqual(fernals.choose(g, "anna", True), (f"sudo -n -u anna {SFTP}", True))
        self.assertEqual(fernals.word("anna"), "anderer")

    def test_opening_as_another_user_is_refused_without_the_switch_and_writing_without_a_fresh_code(self):
        d = self.pair()
        r = ADMIN.post("/api/admin/fernzugang/dateien", json={"geraet": d["id"], "als": "root"})
        self.assertEqual(r.status_code, 403)
        fernzugang._update(d["id"], als=fernals.clean(report(schreiben=True)), als_frei=True)
        called = []

        async def fake(*a, **k):
            called.append(k.get("als"))
            return None, None, "offline"
        with unittest.mock.patch.object(fernzugang, "aufbauen", fake):
            self.assertNotEqual(ADMIN.post("/api/admin/fernzugang/dateien/schreiben", json={"geraet": d["id"], "als": "root"}).status_code, 409)
            self.assertEqual(called, [])                                         # no fresh code: never opened
            ADMIN.post("/api/admin/fernzugang/dateien/schreiben", json={"geraet": d["id"], "als": "root"}, headers=CODE)
            ADMIN.post("/api/admin/fernzugang/dateien", json={"geraet": d["id"], "als": "root", "schreiben": True})   # ignored: read only
            ADMIN.post("/api/admin/fernzugang/dateien/schreiben", json={"geraet": d["id"]}, headers=CODE)              # as spark: no own step
        self.assertEqual(called, [("root", f"sudo -n -u root {SFTP}", True), ("root", f"sudo -n -u root {SFTP} -R", False)])
        self.assertIn(("POST", "/api/admin/fernzugang/dateien/schreiben"), stufen.LIST)


class AsRootEndToEnd(_FilesBase):
    """The whole way: the anchor's pipe, SSH as spark, an exec channel with exactly the sudo command, SFTP on it; read
    only refuses the upload; the counts and the journal without a name."""

    def test_files_as_root_through_sudo(self):
        helpers.set_config(fernals=True)
        self.addCleanup(helpers.set_config, fernals=False)
        d = self.pair(hostkey=HOST_PUB)
        fernzugang._update(d["id"], als=fernals.clean(report()), als_frei=True)
        import paramiko
        files = _Files(self.root).iface
        ran = []

        def run(command, ch):
            ran.append(command)
            if command == f"sudo -n -u root {SFTP} -R":
                srv = paramiko.SFTPServer(ch, "sftp", ch.transport.server_object, files)
                threading.Thread(target=srv.start_subsystem, args=("sftp", ch.transport, ch), daemon=True).start()
            else:
                ch.send_exit_status(1)
                ch.close()
        sshd = _Server(d["pi_key"].split()[1], sftp=files, run=run)
        ws, _ = self.anchor(d["key"], sshd.port)
        with journal() as j:
            r = self.http.post("/api/admin/fernzugang/dateien", json={"geraet": d["id"], "als": "root"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual((r.json()["als"], r.json()["schreiben"]), ("root", False))
            sid = r.json()["id"]
            self.assertEqual(ran, [f"sudo -n -u root {SFTP} -R"])
            c = fernzugang.counts()
            self.assertEqual((c["dateien"], c["dateien_als"]), (1, 1))
            self.assertIn("1 als anderer Benutzer", fernzugang.live_sub(c))
            rows = self.http.post(f"/api/admin/fernzugang/dateien/{sid}/liste", json={"pfad": ""}).json()["eintraege"]
            self.assertIn("notiz.txt", [x["name"] for x in rows])
            up = self.http.post(f"/api/admin/fernzugang/dateien/{sid}/hoch", content=b"x",
                                headers={"x-fz-pfad": "/home/spark", "x-fz-name": "neu.txt"})
            self.assertEqual(up.status_code, 403)
            self.assertFalse(os.path.exists(os.path.join(self.root, "home", "spark", "neu.txt")))
            self.assertEqual(self.http.delete(f"/api/admin/fernzugang/dateien/{sid}").status_code, 200)
        out = j.getvalue()
        self.assertIn("fernzugang: dateien_als | root lesen | 1", out)
        self.assertIn("fernzugang: hoch | nur lesen | 0", out)
        self.assertNotIn("notiz", out)
        ws.close()


class Anchor(unittest.TestCase):
    def ctx(self, system="Linux", visudo=0, users=("root", "anna")):
        p = program()
        root = tempfile.mkdtemp(prefix="anker-als-")
        self.addCleanup(shutil.rmtree, root, True)
        ran = []
        ctx = p.Ctx(system=system, root=root, run=lambda c: ran.append(c) or (visudo if c[:1] == ["visudo"] else 0))
        ctx.euid = lambda: 0
        ctx.ids = lambda n: (0, 0, "/") if n in users else None
        ctx.out = lambda cmd: f"port 22\nsubsystem sftp {SFTP}\n"
        ctx.root_owned = lambda path: path == SFTP
        p.write(ctx.path(ctx.s.conf), json.dumps({"url": "https://s.example.org", "fp": "", "id": "g_1", "key": "fz_k"}), 0o640)
        if system != "Windows":
            p.write(ctx.path(p.SUDOERS), "root ALL=(ALL) ALL\n@includedir /etc/sudoers.d\n", 0o440)
        return p, ctx, ran

    def run_files(self, p, ctx, was, ziele, schreiben=False):
        calls = []
        with unittest.mock.patch.object(p, "http_call", lambda *a, **k: calls.append(a[2:5]) or (200, b"{}")), \
                unittest.mock.patch.object(p.shutil, "which", lambda n: "/usr/bin/" + n), contextlib.redirect_stdout(io.StringIO()):
            rc = p.cmd_files(types.SimpleNamespace(was=was, ziele=ziele, schreiben=schreiben), ctx=ctx)
        return rc, calls

    def test_the_drop_in_names_one_program_with_exact_arguments_checked_with_visudo(self):
        p, ctx, ran = self.ctx()
        rc, calls = self.run_files(p, ctx, "als", ["root,anna"])
        self.assertEqual(rc, 0)
        with open(ctx.path(p.SUDOERS_D)) as f:
            text = f.read()
        self.assertEqual(os.stat(ctx.path(p.SUDOERS_D)).st_mode & 0o777, 0o440)
        rules = [ln for ln in text.splitlines() if ln.startswith("spark ")]
        self.assertEqual(rules, [f"spark ALL=(root,anna) NOPASSWD: {SFTP} -R"])           # read only, nothing else
        self.assertIn(f"Defaults!{SFTP} !requiretty, !use_pty", text)
        self.assertNotIn("ALL=(ALL)", text)
        self.assertTrue(any(c[:2] == ["visudo", "-cf"] for c in ran))
        self.assertEqual(calls[-1], ("POST", "/api/fernzugang/anker/dateien",
                                     {"art": "sudo", "benutzer": ["root", "anna"], "schreiben": False, "sftp": SFTP}))
        rc, _ = self.run_files(p, ctx, "als", ["root"], schreiben=True)
        with open(ctx.path(p.SUDOERS_D)) as f:
            rules = [ln for ln in f.read().splitlines() if ln.startswith("spark ")]
        self.assertEqual(rules, [f"spark ALL=(root) NOPASSWD: {SFTP} -R", f'spark ALL=(root) NOPASSWD: {SFTP} ""'])
        rc, calls = self.run_files(p, ctx, "aus", [])
        self.assertFalse(os.path.exists(ctx.path(p.SUDOERS_D)))
        self.assertEqual(calls[-1][:2], ("DELETE", "/api/fernzugang/anker/dateien"))

    def test_nothing_changes_when_visudo_or_the_system_says_no(self):
        for kind in ("visudo", "include", "user", "spark", "sftp"):
            p, ctx, ran = self.ctx(visudo=1 if kind == "visudo" else 0)
            if kind == "include":                 # read-only (0440) for a runner that is not root: replaced, not opened
                os.remove(ctx.path(p.SUDOERS))
                p.write(ctx.path(p.SUDOERS), "root ALL=(ALL) ALL\n", 0o440)
            if kind == "sftp":
                ctx.root_owned = lambda path: False
            who = {"user": ["bob"], "spark": ["spark"]}.get(kind, ["root"])
            with self.assertRaises(p.Fehler):
                self.run_files(p, ctx, "als", who)
            self.assertFalse(os.path.exists(ctx.path(p.SUDOERS_D)), kind)
            self.assertFalse(os.path.exists(ctx.path(p.SUDOERS_D + ".neu")), kind)

    def test_sudo_rs_gets_the_rule_without_the_defaults_line(self):
        """Ubuntu 25.10 and newer (sudo-rs, Dominik 2026-11-04 on 26.04: „visudo hat die Regel abgelehnt“): its visudo
        rejects the Defaults line, the command lines it takes; still checked with visudo -cf before it counts."""
        p, ctx, ran = self.ctx()
        sshd = ctx.out("x")
        ctx.out = lambda cmd: "sudo-rs 0.2.2\n" if cmd[:2] == ["sudo", "--version"] else sshd
        rc, _ = self.run_files(p, ctx, "als", ["root"], schreiben=True)
        self.assertEqual(rc, 0)
        with open(ctx.path(p.SUDOERS_D)) as f:
            text = f.read()
        self.assertNotIn("Defaults", text)
        self.assertEqual([ln for ln in text.splitlines() if not ln.startswith("#")],
                         [f"spark ALL=(root) NOPASSWD: {SFTP} -R", f'spark ALL=(root) NOPASSWD: {SFTP} ""'])
        self.assertTrue(any(c[:2] == ["visudo", "-cf"] for c in ran))
        self.assertIn("Defaults!", p.sudoers_text(["root"], SFTP, False))          # the classic sudo keeps it
        self.assertNotIn("Defaults", p.sudoers_text(["root"], SFTP, False, rs=True))

    def test_a_sudo_rs_that_does_not_say_so_gets_a_second_try_and_a_refusal_shows_visudos_line(self):
        p, ctx, ran = self.ctx()
        seen = []

        def check(cmd):
            with open(cmd[2]) as f:
                seen.append("Defaults" in f.read())
            return (1, "syntax error: expected configuration option\nvisudo: invalid sudoers file") if seen[-1] else (0, "")
        ctx.check = check
        rc, _ = self.run_files(p, ctx, "als", ["root"])
        self.assertEqual((rc, seen), (0, [True, False]))
        with open(ctx.path(p.SUDOERS_D)) as f:
            self.assertNotIn("Defaults", f.read())
        p, ctx, ran = self.ctx()
        ctx.check = lambda cmd: (1, "\n>>> /etc/sudoers.d/spark-anker.neu: syntax error near line 3 <<<\x1b[0m\n")
        with self.assertRaises(p.Fehler) as e:
            self.run_files(p, ctx, "als", ["root"])
        self.assertIn("visudo hat die Regel abgelehnt („>>> /etc/sudoers.d/spark-anker.neu: syntax error near line 3 <<<", str(e.exception))
        self.assertNotIn("\x1b", str(e.exception))
        self.assertFalse(os.path.exists(ctx.path(p.SUDOERS_D)))
        self.assertFalse(os.path.exists(ctx.path(p.SUDOERS_D + ".neu")))
        self.assertEqual(p.visudo_text(types.SimpleNamespace(check=lambda c: (1, "x" * 500)), "/f"), (1, "x" * 120))

    def test_entfernen_takes_the_drop_in_away(self):
        p, ctx, ran = self.ctx()
        self.run_files(p, ctx, "als", ["root"])
        conf = json.loads(open(ctx.path(ctx.s.conf)).read())
        p.dateien_off(ctx, conf)
        self.assertFalse(os.path.exists(ctx.path(p.SUDOERS_D)))
        import inspect
        self.assertIn("dateien_off(ctx, conf)", inspect.getsource(p.cmd_remove))

    def test_windows_exactly_the_named_folders_never_a_system_folder_and_off_again(self):
        p, ctx, ran = self.ctx(system="Windows")
        os.makedirs(ctx.path("C:/Users/Anna/Dokumente"))
        os.makedirs(ctx.path("C:/Windows/System32"))
        for bad in (["C:/"], ["C:/Windows/System32"], ["C:/Program Files"], ["C:/gibtsnicht"], ["C:/Users/../Windows"]):
            with self.assertRaises(p.Fehler):
                self.run_files(p, ctx, "ordner", bad)
        self.assertFalse(any(c[:1] == ["icacls"] for c in ran))
        rc, calls = self.run_files(p, ctx, "ordner", ["C:\\Users\\Anna\\Dokumente"])
        self.assertEqual(rc, 0)
        grant = [c for c in ran if c[:1] == ["icacls"]][-1]
        self.assertEqual(grant[2:], ["/grant", "spark:(OI)(CI)RX"])
        self.assertEqual(calls[-1][2], {"art": "ordner", "ordner": ["C:/Users/Anna/Dokumente"], "schreiben": False})
        ran.clear()
        self.run_files(p, ctx, "aus", [])
        self.assertEqual([c[2:] for c in ran if c[:1] == ["icacls"]], [["/remove:g", "spark"]])


if __name__ == "__main__":
    unittest.main()
