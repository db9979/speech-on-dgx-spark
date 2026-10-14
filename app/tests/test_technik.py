"""Zustand → Technik (technik.py, plan technische-doku.md, Dominik 2026-10-13: „immer alles aktuell halten bei jeder
Änderung“): the page and docs/de/architektur.md + docs/en/architecture.md describe the Spark as it is. These tests
turn red when a module, a file under state/ or users/<id>/, a node or a step is missing, or when the generated
parts of the docs were not written again (python3 app/panel/hilfe.py --docs). Admin only, names and paths only.
No test reads the clock; the browser part runs where Playwright and Chromium exist.
"""
import ast
import asyncio
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import backup  # noqa: E402
import profiles  # noqa: E402
import speicher  # noqa: E402
import technik  # noqa: E402
import technik_knoten  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_ui_browser import async_playwright, browser_ok, chromium  # noqa: E402

PANEL = os.path.dirname(technik.__file__)
APP = os.path.dirname(PANEL)


def _sources():
    for base in (PANEL, APP):
        for f in sorted(os.listdir(base)):
            if f.endswith(".py") and f != "selftest.py":
                with open(os.path.join(base, f), encoding="utf-8") as fh:
                    yield f, ast.parse(fh.read())


def _const(n):
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


def written_names(marker):
    """Every name the code writes below a base folder: os.path.join(<…marker…>, …, "name"), and the names passed to a
    small helper of the module that joins the base with its parameter (def _file(name): return join(STATE, name))."""
    def base_of(call):
        if not (isinstance(call, ast.Call) and len(call.args) >= 2):
            return False
        fn = ast.unparse(call.func)
        first = ast.unparse(call.args[0])
        if fn.endswith("path.join"):
            return marker in first and "dirname" not in first
        return marker == "USERS" and fn.endswith("_path")
    found = {}
    for f, tree in _sources():
        helpers_ = {}
        grew = True
        while grew:   # also helpers of helpers: _write(name) -> _file(name) -> join(STATE, name)
            grew = False
            for fd in tree.body:
                if not isinstance(fd, ast.FunctionDef) or fd.name in helpers_:
                    continue
                params = [a.arg for a in fd.args.args]
                for n in ast.walk(fd):
                    if not isinstance(n, ast.Call):
                        continue
                    if base_of(n):
                        arg = n.args[-1]
                    elif isinstance(n.func, ast.Name) and n.func.id in helpers_ and len(n.args) > helpers_[n.func.id]:
                        arg = n.args[helpers_[n.func.id]]
                    else:
                        continue
                    if isinstance(arg, ast.Name) and arg.id in params:
                        helpers_[fd.name] = params.index(arg.id)
                        grew = True
                        break
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = None
            if base_of(n):
                name = _const(n.args[-1])
                if marker == "USERS" and ast.unparse(n.func).endswith("_path") and len(n.args) == 1:
                    name = None   # profiles._path("x"): directly under users/, checked on its own
            elif isinstance(n.func, ast.Name) and n.func.id in helpers_ and len(n.args) > helpers_[n.func.id]:
                name = _const(n.args[helpers_[n.func.id]])
            if name and not name.endswith(".tmp"):
                found.setdefault(name.split("/")[0], set()).add(f)
    return found


class Parts(unittest.TestCase):
    def test_every_module_has_its_group(self):
        files = technik.module_files()
        self.assertEqual(sorted(set(files) - set(technik.MODULE)), [],
                         "new module: give it a group and a German line in technik.MODULE")
        self.assertEqual(sorted(set(technik.MODULE) - set(files)), [], "module gone: take it out of technik.MODULE")
        for name, (group, line) in technik.MODULE.items():
            self.assertIn(group, technik.GRUPPEN, name)
            self.assertTrue(line and len(line) <= 120 and "\n" not in line, name)

    def test_every_group_is_in_the_picture(self):
        self.assertEqual(set(technik.ORT), set(technik.GRUPPEN))
        for k, v in technik.KNOTEN.items():
            self.assertTrue(0 <= v[0] <= 780 and 0 <= v[1] <= 460, k)
            for f in v[8]:
                self.assertTrue(os.path.exists(os.path.join(PANEL, f)) or os.path.exists(os.path.join(APP, f))
                                or os.path.exists(os.path.join(APP, "..", f)) or os.path.exists(os.path.join(PANEL, "static", "js", os.path.basename(f))),
                                f"{k}: {f}")

    def test_edges_and_steps_name_real_nodes(self):
        for a, b in technik.KANTEN:
            self.assertIn(a, technik.KNOTEN)
            self.assertIn(b, technik.KNOTEN)
        edges = {f"{a}>{b}" for a, b in technik.KANTEN}
        self.assertEqual(len(technik.SCHRITTE), 8)
        for s in technik.SCHRITTE:
            for n in s[5]:
                self.assertIn(n, technik.KNOTEN, s[0])
            for e in s[6]:
                a, b = e.split(">")
                self.assertTrue(e in edges or f"{b}>{a}" in edges, f"{s[0]}: {e}")
                self.assertTrue(a in s[5] and b in s[5], f"{s[0]}: {e} lights up both ends")


class Storage(unittest.TestCase):
    def test_every_state_file_is_sorted(self):
        """A new file in state/ goes into backup.STATE_FILES (backed up) or backup.STATE_LOCAL (with its reason)."""
        found = written_names("STATE")
        self.assertGreater(len(found), 40)
        known = set(backup.STATE_FILES) | set(backup.STATE_LOCAL)
        missing = sorted(n for n in found if n not in known and not n.startswith("speech-spark-tts-"))
        self.assertEqual(missing, [], "new file under state/: backup.STATE_FILES or backup.STATE_LOCAL")
        self.assertEqual(sorted(set(backup.STATE_FILES) & set(backup.STATE_LOCAL)), [])
        gone = sorted(n for n in known if n not in found and n not in technik.STATE_SONST and n != "speech-spark-tts-*.json")
        self.assertEqual(gone, [], "no code writes these any more: take them out")
        self.assertTrue(all(isinstance(v, str) and v for v in backup.STATE_LOCAL.values()))

    def test_every_profile_file_is_known(self):
        found = written_names("USERS")
        copied = {p.split("/")[0] for _de, _en, files in speicher.AREAS.values() for p in files}
        known = copied | set(speicher.LOCAL) | set(technik.USERS_SONST)
        self.assertEqual(sorted(set(found) - known), [],
                         "new file under users/<id>/: speicher.AREAS, speicher.LOCAL or technik.USERS_SONST")
        for f in technik.USERS_SONST:
            self.assertIn(f, found, f)
            self.assertNotIn(f, speicher.LOCAL, f)

    def test_files_directly_under_users_are_listed(self):
        names = set()
        for f, tree in _sources():
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and ast.unparse(n.func).endswith("_path") and len(n.args) == 1 and _const(n.args[0]):
                    names.add(_const(n.args[0]).split("/")[0])
        names.discard("")
        self.assertEqual(sorted(names - {k.rstrip("/") for k in technik.USERS_GLOBAL} - {"secret"}), [])

    def test_every_place_says_what_it_holds(self):
        rows = technik.speicherorte()
        self.assertGreater(len(rows), 100)
        for r in rows:
            self.assertTrue(r["inhalt"][0] and r["inhalt"][1], r["pfad"])
            self.assertIn(r["sicherung"], ("ja", "nein", "–"), r["pfad"])
        keys = set(technik.INHALT)
        for k in technik.VERSCHLUESSELT:
            self.assertIn(k, keys, k)
        for v in list(speicher.LOCAL.values()) + list(technik.USERS_SONST.values()):
            self.assertIn(v, technik.KAT_EN, v)
        unused = sorted(k for k in keys if not any(r["pfad"].rstrip("/").endswith("/" + k.split("@")[0].rstrip("/"))
                                                    or r["pfad"] == k for r in rows) and k != "firmware")
        self.assertEqual(unused, [], "INHALT names a file no list has")

    def test_what_stays_out_of_a_backup(self):
        rows = {r["pfad"]: r for r in technik.speicherorte()}
        self.assertEqual(rows["users/secret"]["sicherung"], "nein")
        self.assertEqual(rows["state/secret.key"]["sicherung"], "nein")
        self.assertEqual(rows["users/ID/messages-pending.json"]["sicherung"], "nein")
        self.assertEqual(rows["state/offsite.json"]["sicherung"], "ja")
        self.assertEqual(rows["state/panel-password"]["sicherung"], "ja")
        self.assertTrue(rows["users/ID/mail.json"]["schutz"][0])
        self.assertTrue(rows["users/ID/voice.json"]["schutz"][0])    # biometric: sealed (test_stimmabdruck)


class Docs(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(os.path.join(APP, "..", "docs")), "docs/ only in the full repository")
    def test_docs_are_written_again(self):
        technik.data.cache_clear()
        for lang, path in technik.DOCS.items():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for b in technik.BLOCKS:
                self.assertIn(f"<!-- technik:{b} -->", text, path)
            self.assertEqual(technik.render_doc(text, lang), text, f"{path}: run python3 app/panel/hilfe.py --docs")

    def test_mermaid_shows_the_same_picture(self):
        m = technik.mermaid("de")
        for a, b in technik.KANTEN:
            self.assertIn(f"  {a} --> {b}", m)
        self.assertNotIn("<script", m)

    def test_generated_parts_without_markup_from_data(self):
        for lang in ("de", "en"):
            for b in technik.BLOCKS:
                text = technik.block(b, lang)
                self.assertNotIn("<script", text.lower())
                self.assertNotIn("secret-admin", text)


class Endpoint(unittest.TestCase):
    def test_admin_only(self):
        anon = TestClient(panel.app)
        self.assertIn(anon.get("/api/admin/technik").status_code, (401, 403))
        admin = TestClient(panel.app)
        self.assertEqual(admin.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        r = admin.post("/api/admin/profiles", json={"name": "Technikgast", "pin": "4711"})
        self.assertIn(r.status_code, (200, 409), r.text)
        try:
            prof = TestClient(panel.app)
            self.assertEqual(prof.post("/api/profile/login", json={"name": "Technikgast", "pin": "4711"}).status_code, 200)
            self.assertIn(prof.get("/api/admin/technik").status_code, (401, 403))
        finally:
            for u in profiles._load()["users"]:
                if u.get("name") == "Technikgast":
                    admin.delete("/api/admin/profiles/" + u["id"])

    def test_names_and_paths_only(self):
        admin = TestClient(panel.app)
        self.assertEqual(admin.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        for lang in ("de", "en"):
            r = admin.get("/api/admin/technik" + ("?lang=en" if lang == "en" else ""))
            self.assertEqual(r.status_code, 200)
            d = r.json()
            self.assertEqual(set(d), {"version", "groups", "nodes", "edges", "steps", "storage", "areas"})
            raw = json.dumps(d)
            self.assertNotIn("secret-admin", raw)
            self.assertNotIn("Technikgast", raw)
            self.assertEqual(len(d["steps"]), 8)
            mods = [m for g in d["groups"] for m in g["modules"]]
            self.assertEqual(len(mods), len(technik.MODULE))
            self.assertTrue(all(m["text"] for m in mods), "every module has a line in both languages")
            paths = [r["pfad"] for r in d["storage"]]
            self.assertTrue(all(p.startswith(("/", "users/", "state/", "journald")) for p in paths), "places are paths, not contents")
            if lang == "en":
                self.assertNotIn("Gespräch", json.dumps([g["name"] for g in d["groups"]], ensure_ascii=False))


class Knoten(unittest.TestCase):
    """Knoten-Seiten (technik_knoten.py, Dominik 2026-10-14: „ebenso aktuell halten wie alles andere“)."""

    def test_every_box_has_a_page(self):
        pages, offen = set(technik_knoten.SEITEN_DATEN), technik_knoten.OFFEN
        self.assertEqual(pages | offen, set(technik.KNOTEN), "every box of the picture gets a page (technik_knoten.SEITEN_DATEN)")
        self.assertEqual(pages & offen, set(), "a box with a page is no longer open")

    def test_pages_are_complete(self):
        for nid, p in technik_knoten.SEITEN_DATEN.items():
            ids = [s["id"] for s in p["ablauf"]]
            self.assertGreaterEqual(len(ids), 4, nid)
            self.assertEqual(len(ids), len(set(ids)), nid)
            self.assertEqual(p["ablauf"][0]["art"], "start", nid)
            for s in p["ablauf"]:
                self.assertIn(s["art"], technik_knoten.ARTEN, nid)
                for f in ("name", "sub", "text"):
                    self.assertTrue(all(isinstance(x, str) and x.strip() for x in s[f]) and len(s[f]) == 2, f"{nid}/{s['id']}/{f}")
                if s["side"]:
                    kind, label, what = s["side"]
                    self.assertIn(kind, technik_knoten.SEITEN, nid)
                    if kind in ("ok", "zurueck"):
                        self.assertIn(what, ids, f"{nid}/{s['id']}: exit to a real step")
                    if s["art"] == "frage":
                        self.assertIn(label, technik_knoten.LABELS, f"{nid}/{s['id']}: a question leaves with ja or nein")
            for name, path, result in p.get("beispiele", []):
                for x in path:
                    self.assertIn(x.rstrip("!"), ids, f"{nid}: example {name[0]}")
                    if x.endswith("!"):
                        self.assertTrue(next(s for s in p["ablauf"] if s["id"] == x[:-1])["side"], f"{nid}: {x} has an exit")
            for lang in ("de", "en"):
                d = technik_knoten.seite(nid, lang)
                self.assertTrue(d["kurz"] and d["warum"] and d["code"], f"{nid} {lang}")
                self.assertNotIn("{", json.dumps(d, ensure_ascii=False).replace("{\"", "").replace("{}", ""), f"{nid} {lang}: every placeholder filled")

    def test_names_in_the_code_exist(self):
        for nid, p in technik_knoten.SEITEN_DATEN.items():
            for ref in technik_knoten.refs(p):
                self.assertIsNotNone(technik_knoten.finden(ref), f"{nid}: {ref} is gone from the code, change the page")
            for ph in technik_knoten.placeholders(p):
                technik_knoten.fill(ph)
            for t in p.get("tests", []):
                self.assertTrue(os.path.exists(os.path.join(APP, "tests", t + ".py")), f"{nid}: test {t}")

    def test_page_follows_its_code(self):
        """A changed function, class or constant of a box turns this red until its page was checked (rule 30)."""
        for nid, p in technik_knoten.SEITEN_DATEN.items():
            now = technik_knoten.stand(p)
            self.assertEqual(p["stand"], now, f"the code of the box {nid} changed ({', '.join(technik_knoten.refs(p))}): check "
                                              f"its page in technik_knoten.SEITEN_DATEN (way, rules, numbers, texts), then set "
                                              f"its \"stand\" to \"{now}\" and run python3 app/panel/hilfe.py --docs")

    def test_fingerprint_counts_what_the_code_does(self):
        t = technik_knoten._tokens
        a = "def f(x):\n    return x + 1\n"
        self.assertEqual(t(a), t("def f(x):\n\n    # a comment\n    return x  +  1\n"))
        self.assertNotEqual(t(a), t("def f(x):\n    return x + 2\n"))

    def test_page_endpoint(self):
        anon = TestClient(panel.app)
        self.assertIn(anon.get("/api/admin/technik/knoten/waechter").status_code, (401, 403))
        admin = TestClient(panel.app)
        self.assertEqual(admin.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        self.assertEqual(admin.get("/api/admin/technik/knoten/nichtda").status_code, 404)
        for lang in ("de", "en"):
            d = admin.get("/api/admin/technik/knoten/waechter" + ("?lang=en" if lang == "en" else "")).json()
            self.assertEqual(d["name"], technik.KNOTEN["waechter"][3 if lang == "en" else 2])
            self.assertEqual(len(d["steps"]), len(technik_knoten.SEITEN_DATEN["waechter"]["ablauf"]))
            self.assertIn("aussen", d["neighbours"])
            self.assertTrue(all(isinstance(v, (int, bool)) for v in d["today"].values()), "today: numbers only")
            self.assertNotIn("secret-admin", json.dumps(d))
        data = admin.get("/api/admin/technik").json()
        self.assertEqual({n["id"] for n in data["nodes"] if n["page"]}, set(technik_knoten.SEITEN_DATEN))

    def test_today_numbers_only(self):
        import live
        old = live.on
        live.on = lambda: True
        try:
            live._bump("guard_bad")
            d = technik_knoten.heute("waechter")
            self.assertGreaterEqual(d["guard_bad"], 1)
            self.assertEqual(set(d), {k for k, _ in technik_knoten.SEITEN_DATEN["waechter"]["heute"]})
            live.on = lambda: False
            self.assertEqual(technik_knoten.heute("waechter"), {"off": True})
        finally:
            live.on = old


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    async def _until(self, pg, expr):
        """The strict CSP refuses wait_for_function: poll (20 s, a GitHub runner is slow)."""
        for _ in range(200):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass   # the page is just loading again
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    async def _run(self, w, h):
        async with async_playwright() as p:
            exe = chromium()
            br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
            try:
                ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE")
                pg = await ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text else None)
                base = f"http://127.0.0.1:{self.port}"
                # the first-start wizard would lie over the page: this browser sees the setup as done (nothing is stored)
                await pg.route("**/api/setup", lambda route: route.fulfill(json={"done": True})
                               if route.request.method == "GET" else route.continue_())
                await pg.goto(base + "/")
                self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
                await pg.goto(base + "/")
                await self._until(pg, "typeof ADMIN!=='undefined'&&ADMIN===true")
                await pg.evaluate("goSec('tech')")
                await self._until(pg, "!!window.lzIdle&&lzIdle()")
                await pg.wait_for_selector("#tkview svg .tk-node", timeout=10000)
                wide = "document.documentElement.scrollWidth<=document.documentElement.clientWidth"
                self.assertTrue(await pg.evaluate(wide), f"{w}: Überblick")
                # a box: its detail with its modules
                await pg.evaluate("document.querySelector(\"#tkview [data-tkn='weiche']\").dispatchEvent(new MouseEvent('click',{bubbles:true}))")
                self.assertIn("intent.py", await pg.text_content("#tkview .tk-det"))
                # the way of a request: step 6 lights up the guard, „Weiter“ goes to 7
                await pg.click("#tktabs [data-tkv=fluss]")
                await pg.click("#tkview .ld-chip[data-tkstep='5']")
                self.assertEqual(await pg.evaluate("document.querySelector(\"#tkview [data-tkn='waechter']\").classList.contains('lit')"), True)
                await pg.click("#tkview .tk-det .b.p")
                self.assertIn("7", await pg.text_content("#tkview .tk-kind"))
                self.assertTrue(await pg.evaluate(wide), f"{w}: Datenfluss")
                # Vollbild: over the whole window, zoom makes the picture wider, Escape closes (Dominik 2026-10-13 „2+3+4“)
                await pg.click("#tkview [data-tkfull]")
                self.assertTrue(await pg.evaluate("TK.full&&document.documentElement.classList.contains('tk-lock')"))
                box = await pg.evaluate("(()=>{const r=document.getElementById('tkview').getBoundingClientRect();return[r.left,r.top,r.width,innerWidth]})()")
                self.assertEqual((box[0], box[1]), (0, 0), f"{w}: Vollbild covers the window")
                fit = await pg.evaluate("document.querySelector('#tkview .tk-svg').getBoundingClientRect().width")
                await pg.click("#tkview [data-tkzoom='+']")
                self.assertGreater(await pg.evaluate("document.querySelector('#tkview .tk-svg').getBoundingClientRect().width"), fit * 1.3)
                self.assertIn("150", await pg.text_content("#tkview .tk-zl"))
                await pg.click("#tkview [data-tkzoom='0']")
                self.assertEqual(await pg.evaluate("TK.zoom"), 1)
                self.assertIn("7", await pg.text_content("#tkview .tk-kind"))     # the step stays
                await pg.keyboard.press("Escape")
                self.assertFalse(await pg.evaluate("TK.full||document.documentElement.classList.contains('tk-lock')"))
                self.assertTrue(await pg.evaluate(wide), f"{w}: after Vollbild")
                # storage places: filter, a row, its detail (a page of its own on phones), back
                await pg.click("#tktabs [data-tkv=speicher]")
                await pg.click("#tkview .ld-chip[data-tkfilt='profil']")
                n = await pg.evaluate("document.querySelectorAll('#tkview .ld-row').length")
                self.assertEqual(n, sum(1 for r in technik.speicherorte() if r["ort"] == "profil"))
                await pg.click("#tkview [data-tkrow='users/ID/voice.json']")
                self.assertIn("Stimmabdruck", await pg.text_content("#tkview .ld-detail"))
                self.assertTrue(await pg.evaluate(wide), f"{w}: Speicherorte")
                if w < 660:
                    self.assertFalse(await pg.is_visible("#tktabs"))
                    await pg.click("#tkview [data-tkback]")
                    self.assertTrue(await pg.is_visible("#tktabs"))
                await pg.fill("#tkq", "wissen.db")
                self.assertEqual(await pg.evaluate("document.querySelectorAll('#tkview .ld-row').length"), 1)
                # Knoten-Seite: from the box's detail, its way drawn from the steps, an example plays, Vollbild, back
                await pg.click("#tktabs [data-tkv=bild]")
                await pg.evaluate("document.querySelector(\"#tkview [data-tkn='waechter']\").dispatchEvent(new MouseEvent('click',{bubbles:true}))")
                await pg.click("#tkview .tk-det [data-tkpage='waechter']")
                await self._until(pg, "TK.view==='knoten'&&!!document.querySelector('#tkview .kn-svg')")
                steps = technik_knoten.SEITEN_DATEN["waechter"]["ablauf"]
                self.assertEqual(await pg.evaluate("document.querySelectorAll('#tkview .kn-svg .kn-st').length"), len(steps))
                self.assertEqual(await pg.evaluate("document.querySelectorAll('#tkview .kn-steps li').length"), len(steps))
                self.assertTrue(await pg.evaluate(wide), f"{w}: Knoten-Seite")
                await pg.click("#tkview [data-tkplay='4']")       # Notaus an: blocked at step 4
                ex = technik_knoten.seite("waechter")["examples"][4]
                await self._until(pg, "document.getElementById('kncap').textContent.includes(%s)" % json.dumps(ex["result"]))
                self.assertTrue(await pg.evaluate("document.querySelector(\"#tkview .kn-side[data-kns='s4!']\").classList.contains('lit')"))
                self.assertTrue(await pg.evaluate("document.querySelector(\"#tkview .kn-st[data-kns='s9']\").classList.contains('dim')"))
                await pg.click("#kn-ablauf [data-tkfull]")
                box = await pg.evaluate("(()=>{const r=document.getElementById('tkview').getBoundingClientRect();return[r.left,r.top]})()")
                self.assertEqual(tuple(box), (0, 0), f"{w}: Vollbild of the way")
                self.assertTrue(await pg.evaluate("!!document.querySelector('#tkview .kn-svg')&&!document.querySelector('#tkview #kn-code')"))
                await pg.keyboard.press("Escape")
                self.assertTrue(await pg.evaluate("!TK.full&&!!document.querySelector('#tkview #kn-code')"))
                if 380 < w < 400:   # every page fits a phone
                    for nid in technik_knoten.SEITEN_DATEN:
                        await pg.evaluate(f"knOpen('{nid}')")
                        await self._until(pg, f"TK.page==='{nid}'&&!!document.querySelector('#tkview .kn-svg')")
                        self.assertTrue(await pg.evaluate(wide), f"{w}: page {nid}")
                    await pg.evaluate("knOpen('waechter')")
                    await self._until(pg, "TK.page==='waechter'&&!!document.querySelector('#tkview .kn-head')")
                await pg.click("#tkview .kn-head [data-tkv=bild]")
                self.assertEqual(await pg.evaluate("TK.view+':'+TK.sel"), "bild:waechter")
                await pg.click("#tktabs [data-tkv=module]")
                self.assertIn("technik.py", await pg.text_content("#tkview"))
                self.assertTrue(await pg.evaluate(wide), f"{w}: Bausteine")
                self.assertEqual(errors, [])
            finally:
                await br.close()

    def test_page_on_computer_and_phones(self):
        for w, h in ((1280, 900), (390, 844), (320, 700)):
            asyncio.run(self._run(w, h))


class Integration(unittest.TestCase):
    def test_wired_into_the_panel(self):
        static = os.path.join(PANEL, "static")
        html = open(os.path.join(static, "index.html"), encoding="utf-8").read()
        base = open(os.path.join(static, "js", "base.js"), encoding="utf-8").read()
        coadm = open(os.path.join(static, "js", "coadmin.js"), encoding="utf-8").read()
        i18n = open(os.path.join(static, "js", "i18n.js"), encoding="utf-8").read()
        js = open(os.path.join(static, "js", "technik.js"), encoding="utf-8").read()
        self.assertIn('<section id="tech">', html)
        self.assertIn('<script src="/static/js/technik.js"></script>', html)
        self.assertIn("['tech',t('Technik','Architecture')]", base)
        self.assertIn("lzb($('tkview'),loadTechnik)", base)
        self.assertIn("x[0]!=='tech'", coadm)          # a Verwalter does not see it
        self.assertIn('"Technik": "Architecture"', i18n)
        self.assertNotIn("onclick=", js)
        self.assertNotIn("fetch(", js)                   # only through api() (laden.js)
        import hilfe
        self.assertIn("tech", hilfe.SECTIONS)
        self.assertTrue({"architektur", "architecture"} <= hilfe.TECH_DOCS)

    def test_rule_in_the_guideline(self):
        root = os.path.join(APP, "..", "docs")
        if not os.path.isdir(root):
            self.skipTest("docs/ only in the full repository")
        de = open(os.path.join(root, "de", "richtlinien.md"), encoding="utf-8").read()
        en = open(os.path.join(root, "en", "guidelines.md"), encoding="utf-8").read()
        self.assertIn("**Technik-Doku**", de)
        self.assertIn("**Architecture docs**", en)
        self.assertIn("test_technik", de)


if __name__ == "__main__":
    unittest.main()
