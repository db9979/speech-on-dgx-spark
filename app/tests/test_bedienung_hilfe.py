"""Package 5 of the independent review of 11.10.2026 (pruefung/unabhaengige-pruefung-2026-10-11.md, B1–B8):
the English page is English, error messages are sentences, every "?" has its help, old page names are gone,
fields have labels, and small things around the Live page, Ich and the Pebble link. No test reads the clock."""
import html as html_lib
import json
import os
import re
import unittest
from html.parser import HTMLParser

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
from common import load_config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, "..", "panel")
STATIC = os.path.join(PANEL, "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


def en_table():
    s = read("js", "i18n.js")
    start = s.index("const EN=") + len("const EN=")
    return json.loads(s[start:s.index("};", start) + 1])


# words that read the same in English (names, units, technical terms) or are no words at all
SAME_IN_EN = {
    "English", "Strg K", "Update", "CPU", "systemd", "RTF", "Unit", "Status", "PID", "Home Assistant", "Port", "Key ID",
    "Team ID", "Tokens", "Text", "Backend:", "Seed", "Engine (vllm-omni)", "Engine (vLLM)", "bfloat16", "float16", "float32",
    "Base", "wav, mp3, m4a, …", "Reserve", "GiB", "Logs", "MB", "Version", "VoiceDesign", "Open WebUI", ": Server-Sent Events",
    "Hermes Agent", "OpenClaw", "curl", "10 min", "ASR", "TTS", "ASR-Engine", "TTS-Engine",
    "VoiceDesign-Engine", "Panel", "Admin", "iCloud (CalDAV)", "Nextcloud (CalDAV)", "iCloud", "Gmail", "GMX", "web.de",
    "Server", "reMarkable-Notizen",
}
MODEL_NAME = re.compile(r"Qwen/[\w.-]+")


class Texts(HTMLParser):
    """The texts of index.html the way i18n.js translatePage sees them: data-tr elements whole (inner HTML with
    single spaces), every other text node alone, and title / aria-label."""
    VOID = {"input", "br", "img", "meta", "link", "hr", "source", "wbr"}

    def __init__(self, src):
        super().__init__(convert_charrefs=True)
        self.src, self.stack, self.texts, self.attrs, self.whole = src, [], [], [], []
        self.lines = [0]
        for line in src.split("\n"):
            self.lines.append(self.lines[-1] + len(line) + 1)
        self.feed(src)

    def _at(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        for a in ("title", "aria-label"):
            if d.get(a):
                self.attrs.append((self.getpos()[0], html_lib.unescape(d[a])))
        if tag in self.VOID:
            return
        tr = "data-tr" in d
        if tr:
            start = self.src.index(">", self._at()) + 1
            end = self.src.index(f"</{tag}>", start)
            self.whole.append((self.getpos()[0], re.sub(r"\s+", " ", self.src[start:end]).strip()))
        self.stack.append((tag, tr))

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop()[0] != tag:
            pass

    def handle_data(self, d):
        k = html_lib.unescape(d).strip()
        if not k or any(t in ("pre", "code", "script", "style") or tr for t, tr in self.stack):
            return
        if re.search(r"[A-Za-zÄÖÜäöüß]{2}", k):
            self.texts.append((self.getpos()[0], k))


class English(unittest.TestCase):
    """B1: the English page shows no German: texts, tooltips, screen-reader names, sentences with tags inside."""

    def test_translate_page_covers_titles_labels_and_whole_sentences(self):
        js = read("js", "i18n.js")
        body = js[js.index("function translatePage"):js.index("$('langbtn').onclick")]
        self.assertIn("'title','aria-label'", body)
        self.assertIn("[data-tr]", body)
        self.assertLess(body.index("[data-tr]"), body.index("createTreeWalker"))   # whole sentences before their words

    def test_every_text_of_the_page_has_english(self):
        en, page = en_table(), Texts(read("index.html"))
        missing = [x for x in page.texts if x[1] not in en and x[1] not in SAME_IN_EN and not MODEL_NAME.fullmatch(x[1])]
        self.assertEqual(missing, [], "ohne Übersetzung in i18n.js (oder in SAME_IN_EN, wenn es gleich bleibt)")

    def test_every_title_and_aria_label_has_english(self):
        en, page = en_table(), Texts(read("index.html"))
        self.assertGreater(len(page.attrs), 30)
        missing = [x for x in page.attrs if x[1] not in en and x[1] not in SAME_IN_EN]
        self.assertEqual(missing, [], "title/aria-label ohne Übersetzung in i18n.js")

    def test_sentences_with_tags_are_translated_whole(self):
        en, page = en_table(), Texts(read("index.html"))
        self.assertGreaterEqual(len(page.whole), 10)
        missing = [x for x in page.whole if x[1] not in en]
        self.assertEqual(missing, [], "data-tr ohne ganzen Satz in i18n.js")
        for _, k in page.whole:   # the English keeps the ids and links the scripts look for
            for ident in re.findall(r'id="([\w-]+)"', k):
                self.assertIn(f'id="{ident}"', en[k])
        # no sentence with tags inside is left to word-by-word translation
        loose = [x for x in page.texts if x[1] in ("Aktion", "In der App", "anlegen.", "Tagen.")]
        self.assertEqual(loose, [])


class PlainErrors(unittest.TestCase):
    """B2: what the person reads is a sentence in the page's language, never a list, an exception or a path."""

    def test_api_names_the_fields_of_a_422_and_keeps_the_raw_words_apart(self):
        js = read("js", "base.js")
        api = js[js.index("const api=async"):js.index("const apiTry")]
        self.assertIn("errSay(r.status,d,raw)", api)
        self.assertIn("e.detail=", api)
        say = js[js.index("function errSay"):js.index("const errRaw")]
        self.assertIn("Array.isArray(d)", say)          # FastAPI 422: [{loc, msg}] -> the names of the fields
        self.assertIn("EN[d]", say)                      # the panel's German sentences in English
        # callers that look at the panel's own words read them from e.detail, not from the sentence
        for f in ("admin.js", "chat.js", "me.js", "mfa.js", "mcp.js", "mymcp.js", "start.js"):
            self.assertNotRegex(read("js", f), r"/\.test\(e\.message\)|e\.message\.match", f)

    def test_backup_failure_is_a_sentence_without_paths(self):
        import backup
        import errno
        old = backup.create

        def broken(*a, **k):
            raise OSError(errno.ENOSPC, "No space left on device", "/var/lib/speech-spark/backups/x.tar.gz")
        backup.create = broken
        try:
            r = ADMIN.post("/api/backups")
        finally:
            backup.create = old
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("/var/", r.text)
        self.assertIn(r.json()["detail"], en_table())    # a German sentence with its English

    def test_server_sentences_have_english(self):
        en = en_table()
        for f in ("account.py", "system.py"):
            with open(os.path.join(PANEL, f), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(src, r'HTTPException\(\d+, f"[a-z ]+ not reachable: \{type\(e\)', f)
            self.assertNotIn('f"backup failed: {e}"', src)
        for sentence in ("Der Kalender ist nicht erreichbar. Bitte Adresse und Netz prüfen.",
                         "Der Mailserver ist nicht erreichbar. Bitte Server, Port und Netz prüfen.",
                         "Das Sprachmodell ist gerade nicht erreichbar. Bitte später noch einmal.",
                         "Wiederherstellen ging nicht: die Datei ist unvollständig oder nicht lesbar."):
            self.assertIn(sentence, en)

    def test_a_guest_sees_no_address_when_the_model_is_down(self):
        dead = f"http://127.0.0.1:{helpers._port()}/v1"
        c = load_config()["chat"]
        old = {"llm_url": c["llm_url"], "public": c.get("public", False)}
        helpers.set_config(llm_url=dead, public=True)
        try:
            r = TestClient(panel.app).post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "speak": False})
        finally:
            helpers.set_config(**old)
        self.assertEqual(r.status_code, 200, r.text)
        errs = [e for e in helpers.events(r) if e["type"] == "error"]
        self.assertTrue(errs)
        for e in errs:
            self.assertNotIn("127.0.0.1", e.get("message", ""))


class QuestionMarks(unittest.TestCase):
    """B3: a "?" stands only at a row the help has an entry for; the rows the review found have one now."""

    def test_the_rows_of_the_review_have_their_entry(self):
        import hilfe
        ids = set(hilfe.known_ids())
        for k in ("bakfile", "bakpw", "vfile", "coadmnotify", "llmmodelsel", "tts.default_voice", "rptoken",
                  "roomdetect", "roomping", "roomprobe", "roomsum", "roomtext", "roomtone"):
            self.assertIn("sw:" + k, ids, k)
        # fields inside a row's sentence (Von selbst: how long before, from whom, where) get no "?" at all
        js = read("js", "hilfe.js")
        self.assertIn("!x.closest('.lbl')", js[js.index("function hilfeRowId"):])

    def test_every_settings_row_with_a_field_has_an_entry(self):
        import hilfe
        ids = set(hilfe.known_ids())
        rows = [r for r in hilfe.setting_rows() if r["id"] and not r["id"].startswith("set_")]
        self.assertGreater(len(rows), 100)
        self.assertEqual([r["id"] for r in rows if "sw:" + r["id"] not in ids], [])
        self.assertTrue(all(len(r["de"]) < 80 for r in rows), [r["de"] for r in rows if len(r["de"]) >= 80])   # one row each

    def test_a_question_mark_only_where_the_help_knows_the_row(self):
        js = read("js", "hilfe.js")
        self.assertIn("HQIDS.has(id)", js[js.index("function hilfeMarks"):])
        self.assertIn("/api/hilfe/ids", js)

    def test_ids_only_with_the_page_help(self):
        import hilfe
        r = ADMIN.post("/api/admin/profiles", json={"name": "Fragezeichen", "pin": "4321"})
        self.assertIn(r.status_code, (200, 409))
        c = TestClient(panel.app)
        self.assertEqual(c.get("/api/hilfe/ids").status_code, 401)            # guests: nothing
        self.assertEqual(c.post("/api/profile/login", json={"name": "Fragezeichen", "pin": "4321"}).status_code, 200)
        uid = next(u["id"] for u in profiles._load()["users"] if u["name"] == "Fragezeichen")
        helpers.set_config(spark_help=False, spark_drawer=False)
        self.assertEqual(c.get("/api/hilfe/ids").json(), {"ids": []})
        helpers.set_config(spark_help=True, spark_drawer=True)
        profiles.save_settings(uid, {"spark_help": True})
        try:
            self.assertEqual(c.get("/api/hilfe/ids").json()["ids"], hilfe.known_ids())
        finally:
            helpers.set_config(spark_help=False, spark_drawer=False)
            profiles.save_settings(uid, {"spark_help": False})


class Names(unittest.TestCase):
    """B4/B5: the menu's names as they are, the English docs in English."""
    OLD = re.compile(r"(?:unter|Unter|→) \**Profile\b(?![-\w])|Profile →|under \**Profiles|(?<!&amp; )(?<!& )Profiles →"
                     r"|\bunter Einbinden\b|under Integrate\b|Reiter „Einbinden“|\*\*Einbinden\*\*")

    def test_no_old_page_names(self):
        for f in ("index.html", "js/guides.js", "js/extras.js"):
            self.assertIsNone(self.OLD.search(read(*f.split("/"))), f)
        docs = os.path.join(HERE, "..", "..", "docs")
        if not os.path.isdir(docs):
            self.skipTest("docs/ not here (app/ alone)")
        for lang in ("de", "en"):
            for name in os.listdir(os.path.join(docs, lang)):
                with open(os.path.join(docs, lang, name), encoding="utf-8") as fh:
                    self.assertIsNone(self.OLD.search(fh.read()), f"{lang}/{name}")

    def test_english_docs_use_the_english_menu(self):
        docs = os.path.join(HERE, "..", "..", "docs", "en")
        if not os.path.isdir(docs):
            self.skipTest("docs/ not here (app/ alone)")
        for name in os.listdir(docs):
            with open(os.path.join(docs, name), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotRegex(text, r"Ich →|\"Ich\"|\bZustand →|\*Funktionen →|Personen und Geräte →", name)


class Fields(unittest.TestCase):
    """B6/B7: fields have a name for screen readers and the same length limit as the panel."""

    def test_rows_and_the_chat_field_are_labelled(self):
        html = read("index.html")
        self.assertIn('<label for="chattext"', html)
        js = read("js", "base.js")
        self.assertIn("function rowLabels", js)
        self.assertIn("MutationObserver(later)", js)

    def test_tool_words_have_the_panels_limit(self):
        # the must words moved to Funktionen → Weiche (plan weiche-intelligenter step 0): checked there with the
        # panel's own limit (weiche.check → chat.parse_tool_words), the page shows it
        import chat
        import weiche
        self.assertNotIn('id="chat.tool_words"', read("index.html"))
        with self.assertRaises(ValueError):
            weiche.check({"tool_words": "web_search: " + "x" * (chat.MAX_TOOL_WORDS_CHARS + 1)})


class SmallThings(unittest.TestCase):
    """B8: the Live page off is a quiet answer, Ich does not reload everything on each jump, the Pebble link
    follows the page's scheme."""

    def test_live_off_is_quiet(self):
        import live
        old = live.on
        live.on = lambda *a, **k: False
        try:
            r = ADMIN.get("/api/admin/live")
        finally:
            live.on = old
        self.assertEqual((r.status_code, r.json()), (200, {"on": False}))
        self.assertIn("d.on===false", read("js", "live.js"))

    def test_me_boxes_load_once_at_a_time(self):
        js = read("js", "me.js")
        body = js[js.index("async function openMe"):js.index("window.openMe=openMe")]
        self.assertIn("ME_LOAD.p", body)       # a jump while Ich loads waits for that load ...
        self.assertIn("ME_LOAD.next", body)    # ... and at most one more after it, never one per jump
        self.assertNotIn("await showFacts()", body[:body.index("async function meLoad")])

    def test_pebble_link_follows_the_page(self):
        js = read("js", "admin.js")
        part = js[js.index("async function loadInt"):]
        part = part[:part.index("\n}") if "\n}" in part else 3000]
        self.assertIn("$('int-pbw').href=siriBase+", part)
        self.assertNotIn("$('int-pbw').href=panelUrl", part)


class InTheBrowser(unittest.TestCase):
    """B1, B2, B3, B6 in Chromium: the English page, error sentences, the "?" only at known rows, named fields."""

    @classmethod
    def setUpClass(cls):
        from tests import test_ui_browser as ui
        if not ui.browser_ok():
            raise unittest.SkipTest("no Playwright/Chromium here")
        cls.ui = ui
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        r = ADMIN.post("/api/admin/profiles", json={"name": "Bedientest", "pin": "4712"})
        assert r.status_code in (200, 409), r.text
        cls.uid = next(u["id"] for u in profiles._load()["users"] if u["name"] == "Bedientest")

    def test_english_errors_marks_and_names(self):
        import asyncio
        import hilfe
        known = set(hilfe.known_ids())
        helpers.set_config(spark_help=True, spark_drawer=True)
        profiles.save_settings(self.uid, {"spark_help": True})

        async def go():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                exe = self.ui.chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    pg = await (await br.new_context(viewport={"width": 1280, "height": 900}, locale="de-DE")).new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    base = f"http://127.0.0.1:{self.port}"
                    await pg.goto(base + "/")
                    self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
                    self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Bedientest", "pin": "4712"})).status, 200)
                    await pg.evaluate("localStorage.setItem('lang','en')")
                    await pg.goto(base + "/")
                    await pg.wait_for_timeout(800)
                    # B1: tooltip, screen-reader name and a sentence with tags inside are English
                    self.assertEqual(await pg.evaluate("$('updbx').title"), "Later")
                    self.assertEqual(await pg.evaluate("$('chatwake').closest('label').title"),
                                     en_table()["Dauerhaft lauschen, das Wort startet das Gespräch (Bildschirm bleibt an)"])
                    self.assertEqual(await pg.evaluate("$('chattext').labels[0].textContent"), "Question to the assistant")
                    self.assertTrue((await pg.evaluate("$('int-pbw').parentElement.textContent")).startswith("On the phone"))
                    self.assertEqual(await pg.evaluate("$('logdays').textContent"), "7")
                    # B2: sentences, never "[object Object]", never a page of HTML
                    say = await pg.evaluate("[errSay(422,[{loc:['body','name'],msg:'Field required',type:'missing'}],''),"
                                            "errSay(500,'<html><body>Internal</body></html>','<html><body>Internal</body></html>'),"
                                            "errSay(413,'too large',''),errSay(400,'Der Kalender ist nicht erreichbar. Bitte Adresse und Netz prüfen.','')]")
                    self.assertEqual(say[0], "This entry is missing or does not fit: name")
                    self.assertNotIn("<", say[1])
                    self.assertEqual(say[2], "That is too large.")
                    self.assertEqual(say[3], "The calendar cannot be reached. Please check the address and the network.")
                    msg = await pg.evaluate("api('/api/no-such-page-here').then(()=>'',e=>[e.message,e.detail])")
                    self.assertEqual(msg, ["Not found, maybe deleted already. Please reload the page.", "Not Found"])
                    # B3: every "?" on the settings pages and in Ich belongs to a row the help knows
                    marks = set()
                    await pg.evaluate("goSec('cfg')")
                    for _ in range(200):   # strict CSP: no wait_for_function with a string; until every box is loaded
                        if await pg.evaluate("!!window.lzIdle&&lzIdle()"):
                            break
                        await pg.wait_for_timeout(100)
                    else:
                        self.fail("settings never loaded")
                    for p_id in await pg.evaluate("[...document.querySelectorAll('#cfgnav button[data-p]')].map(b=>b.dataset.p)"):
                        await pg.evaluate(f"document.querySelector('#cfgnav button[data-p={p_id}]').click()")
                        await pg.wait_for_timeout(250)
                        marks |= set(await pg.evaluate("[...document.querySelectorAll('.hqbtn')].map(b=>b.dataset.hq)"))
                    await pg.evaluate("openMe('setbox')")
                    await pg.wait_for_selector("#setform .setrow .hqbtn", timeout=5000)
                    marks |= set(await pg.evaluate("[...document.querySelectorAll('.hqbtn')].map(b=>b.dataset.hq)"))
                    self.assertGreater(len(marks), 20)
                    self.assertEqual(marks - known, set())
                    # B6: every field of a settings row has a name
                    await pg.wait_for_timeout(100)
                    nameless = await pg.evaluate("""[...document.querySelectorAll('.setrow')].map(r=>[r,[...r.querySelectorAll('input:not([type=hidden]),select,textarea')].find(x=>!x.closest('.lbl'))])
                        .filter(([r,c])=>c&&r.querySelector(':scope>.lbl>b')&&!c.getAttribute('aria-label')&&!c.getAttribute('aria-labelledby')&&![...(c.labels||[])].some(l=>l.textContent.trim()))
                        .map(([r,c])=>c.id||c.name||r.textContent.slice(0,40))""")
                    self.assertEqual(nameless, [])
                    self.assertEqual(await pg.evaluate("$('chattext').labels.length"), 1)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        try:
            asyncio.run(go())
        finally:
            helpers.set_config(spark_help=False, spark_drawer=False)
            profiles.save_settings(self.uid, {"spark_help": False})
