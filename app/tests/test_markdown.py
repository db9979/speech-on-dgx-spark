"""Answers as formatted text (Dominik 2026-10-12: "Antworten im Chat mit Markdown anzeigen, aber nicht mit
Markdown aussprechen"): the panel's chat shows the model's Markdown formatted (md.js, never innerHTML from
model text, links only http(s) to public hosts), the voice never says the signs (textnorm.speech_markdown in
both speech services, before the secret rule), devices without formatting get the text without the signs
(textnorm.plain_markdown: Telegram, Siri, reMarkable, watch, speaker displays; the Begleiter gets both, see
test_begleiter)."""
import asyncio
import json
import os
import unittest

from tests import helpers

helpers.start()
import chat  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import textnorm  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})

ANSWER = ("**Auf dem Postfix-Server:**\n1. **SMTP-AUTH:** In der `main.cf` muss `smtpd_sasl_auth_enable = yes` "
          "stehen.\n2. Siehe [Doku](https://www.postfix.org/SASL_README.html).\n## Kurz gesagt\n- *Service-Konto*\n"
          "| A | B |\n|---|---|\n| 1 | 2 |\n```bash\nrm -rf /tmp/x\n```\nFertig: 3 * 4 * 5, snake_case_name.")


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


class Plain(unittest.TestCase):
    def test_plain_text_keeps_words_and_drops_signs(self):
        p = textnorm.plain_markdown(ANSWER)
        for sign in ("**", "`", "## ", "|---", "```", "[Doku]"):
            self.assertNotIn(sign, p)
        for kept in ("Auf dem Postfix-Server:", "1. SMTP-AUTH:", "main.cf", "Doku (https://www.postfix.org/SASL_README.html)",
                     "Kurz gesagt", "• Service-Konto", "A · B", "rm -rf /tmp/x", "3 * 4 * 5", "snake_case_name"):
            self.assertIn(kept, p)

    def test_link_text_and_tables_stay_clean(self):
        self.assertEqual(textnorm.plain_markdown("[**fett**](https://x.de)"), "fett (https://x.de)")
        self.assertEqual(textnorm.plain_markdown("| A | B |\n|---|---|\n| 1 | 2 |"), "A · B\n1 · 2")

    def test_speech_never_says_the_signs_code_or_links(self):
        s = textnorm.speech_markdown(ANSWER)
        for gone in ("**", "`", "#", "•", "rm -rf", "https://", "("):
            self.assertNotIn(gone, s)
        self.assertIn("„main.cf“", s)          # code in quotes: spoken as a word
        self.assertIn("Siehe Doku.", s)
        self.assertIn("3 * 4 * 5", s)          # not italic
        self.assertEqual(textnorm.speech_markdown("ein Teil **fett"), "ein Teil fett")   # a sentence cut in the middle

    def test_secret_in_markdown_is_never_spoken(self):
        for said in ("Das **Passwort** ist `geheim`.", "**WLAN-Passwort:** Sonne123", "Der *Code* lautet `4711`."):
            out = textnorm.hide_secrets(textnorm.speech_markdown(said), "de")
            self.assertIn("nur schriftlich sichtbar", out, said)
            for v in ("geheim", "Sonne123", "4711"):
                self.assertNotIn(v, out, said)

    def test_huge_text_is_left_as_it_is(self):
        big = "**x** " * 20000
        self.assertEqual(textnorm.plain_markdown(big), big)

    def test_code_blocks_over_several_sentences_are_not_spoken(self):
        st = {}
        said = [chat.no_code(x, st) for x in ("So geht es:", "```bash", "rm -rf /tmp/x.", "echo ok.", "```", "Fertig.")]
        self.assertEqual([x for x in said if x], ["So geht es:", "Fertig."])
        self.assertEqual(chat.no_code("Vorher ```x``` nachher.", {}), "Vorher nachher.")


class Channels(unittest.TestCase):
    def test_browser_chat_may_use_markdown_other_devices_not(self):
        a = profile("Formatierer")
        helpers.LLM_CALLS.clear()
        a.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]})
        system = helpers.LLM_CALLS[-1]["messages"][0]["content"]
        self.assertIn(chat.WEB_HINT, system)
        self.assertIn(chat.WEB_SPOKEN_HINT, system)     # spoken too: no tables, no code blocks
        a.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "speak": False})
        self.assertIn(chat.WEB_TEXT_HINT, helpers.LLM_CALLS[-1]["messages"][0]["content"])
        for client in ("telegram", "speaker", "watch"):
            a.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "client": client})
            self.assertNotIn(chat.WEB_HINT, helpers.LLM_CALLS[-1]["messages"][0]["content"], client)

    def test_line_breaks_reach_the_chat(self):
        a = profile("Zeilen")
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "SAY | | Zwei Schritte:\n1. **Eins.**\n2. Zwei."}],
                                       "speak": False})
        shown = "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
        self.assertEqual(shown, "Zwei Schritte:\n1. **Eins.**\n2. Zwei.")   # the chat formats it, so it stays

    def test_siri_hears_and_begleiter_reads_plain_text(self):
        a = profile("Siri-Format")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        key = profiles.add_device("iPhone Siri Format", uid)
        g = TestClient(panel.app)
        r = g.post("/api/siri/ask", json={"text": "SAY |x| **Fertig:** siehe `main.cf`."}, headers={"X-Speech-Device": key})
        self.assertEqual(r.json()["answer"], "Fertig: siehe „main.cf“.")
        self.assertIn("**Fertig:**", json.dumps(profiles.convos(uid), ensure_ascii=False))   # the history keeps it


class Briefing(unittest.TestCase):
    def test_daily_briefing_sorted_in_the_history_plain_in_the_push(self):
        """Dominik 2026-10-13: the briefing of 07:45 was one block of text in the chat. The history keeps a version
        with Markdown lists (BRIEF_MD_SYSTEM), the push gets it without the signs; the chat tool may list too."""
        import datetime
        import push
        a = profile("Morgenliste")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        a.put("/api/profile/settings", json={"briefing_at": "07:30", "tz": "Europe/Berlin"})
        text = "Guten Morgen.\n**Termine**\n- 10:00 Webinar\n- 12:00 deBug & Coffee\n**Mails**\n- db9979: Test fehlgeschlagen"
        sent, asked = [], []

        async def fake_brief(u, tz="", markdown=False):
            asked.append(markdown)
            return text

        async def fake_send(u, title, body, tag="", private=True, why=""):
            sent.append(body)
            return 1
        old = chat.morning_briefing, push.send, push.subs
        chat.morning_briefing, push.send = fake_brief, fake_send
        push.subs = lambda u: [{"endpoint": "x"}] if u == uid else []
        try:
            zone = chat.user_zone("Europe/Berlin")
            asyncio.run(chat.due_briefings(datetime.datetime(2026, 10, 13, 7, 45, tzinfo=zone)))
        finally:
            chat.morning_briefing, push.send, push.subs = old
        self.assertEqual(asked, [True])
        self.assertEqual(sent, ["Guten Morgen.\nTermine\n• 10:00 Webinar\n• 12:00 deBug & Coffee\nMails\n• db9979: Test fehlgeschlagen"])
        c = [x for x in profiles.convos(uid) if x["id"] == "brief-20261013"][0]
        self.assertEqual(c["msgs"][-1]["content"], text)
        self.assertIn("Markdown", chat.BRIEF_MD_SYSTEM)
        self.assertIn("ohne Listen, Markdown", chat.BRIEF_SYSTEM)      # the push, reMarkable and Begleiter text stays plain
        self.assertIn("already over", chat.BRIEF_MD_SYSTEM)
        self.assertNotIn("Keine Aufzählungszeichen, keine Links", chat.BRIEFING_HINT)


def _browser():
    try:
        from tests.test_ui_browser import async_playwright, browser_ok, chromium
    except Exception:
        return None
    return (async_playwright, chromium) if browser_ok() else None


@unittest.skipUnless(_browser(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    """md.js in a real browser with the strict CSP: what the model writes never becomes markup or a script,
    links only for public http(s) addresses."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    def test_render_is_safe_and_formatted(self):
        async_playwright, chromium = _browser()

        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                pg = await (await br.new_context(viewport={"width": 320, "height": 700})).new_page()
                base = f"http://127.0.0.1:{self.port}"
                await pg.goto(base + "/")
                await pg.request.post(base + "/api/login", data={"password": "secret-admin"})
                await pg.goto(base + "/")
                # the start shows the chat page only once it has loaded (whoami): before that the section is hidden
                # and a message in it has no width (red on GitHub from V01.0.514 on, when the start took longer)
                ready = False
                for _ in range(200):   # strict CSP: no wait_for_function with a string, so look every 100 ms
                    ready = await pg.evaluate("typeof md==='object'&&typeof chatLog==='function'&&!!document.getElementById('chatlog')"
                                              "&&document.getElementById('chatlog').getBoundingClientRect().width>0")
                    if ready:
                        break
                    await pg.wait_for_timeout(100)
                self.assertTrue(ready, "chat page never shown")
                evil = ANSWER + ("\n<img src=x onerror=\"window.__md=1\"> <script>window.__md=2</script>"
                                 "\n[klick](javascript:window.__md=3) [lan](http://192.168.178.1/reboot) "
                                 "[mail](http://user:pw@example.com/) [gut](https://example.com/a) https://www.kiwix.org/x. [**https://bank.example**](https://evil.example/)"
                                 "\n![bild](https://tracker.example.com/p.gif)\n> **Zitat** mit <b>Tag</b>"
                                 "\n```powershell\nAdd-RecipientPermission -Identity \"Mailbox\" -Trustee \"PostfixServiceAccount\" -AccessRights SendAs\n```"
                                 "\n| Spalte mit sehr langem Inhalt ohne Umbruch | zweite_spalte_mit_noch_viel_mehr_text_darin |\n|---|---|\n| a | b |")
                got = await pg.evaluate("""x=>{showSec('chat');const d=chatLog('assistant',x);const box=d.firstChild;
                  return {tags:[...new Set([...box.querySelectorAll('*')].map(e=>e.tagName.toLowerCase()))].sort(),
                    links:[...box.querySelectorAll('a')].map(a=>[a.textContent,a.getAttribute('href'),a.target,a.rel]),
                    nolink:[...box.querySelectorAll('.md-nolink')].map(e=>e.textContent),
                    host:[...box.querySelectorAll('.md-host')].map(e=>e.textContent),
                    imgs:box.querySelectorAll('img,script,iframe').length,attrs:[...box.querySelectorAll('*')].flatMap(e=>[...e.attributes].map(a=>a.name)),
                    nested:box.querySelectorAll('a a').length,strong:[...box.querySelectorAll('strong')].map(e=>e.textContent),code:[...box.querySelectorAll('code')].map(e=>e.textContent),
                    li:box.querySelectorAll('li').length,th:box.querySelectorAll('th').length,
                    plain:md.plain(x),wide:d.getBoundingClientRect().right>innerWidth+1||document.documentElement.scrollWidth>innerWidth,shown:d.getBoundingClientRect().width>0,flag:window.__md||0}}""",
                                        evil)
                self.assertEqual(got["flag"], 0)
                self.assertEqual(got["imgs"], 0)    # no picture is loaded, no script, no frame
                allowed = {"a", "blockquote", "br", "code", "del", "div", "em", "h3", "h4", "h5", "hr", "li", "ol", "p",
                           "pre", "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "ul"}
                self.assertLessEqual(set(got["tags"]), allowed)
                self.assertLessEqual(set(got["attrs"]), {"class", "href", "target", "rel", "title", "start"})
                hrefs = [x[1] for x in got["links"]]
                self.assertIn("https://example.com/a", hrefs)
                self.assertIn("https://www.postfix.org/SASL_README.html", hrefs)
                self.assertIn("https://www.kiwix.org/x", hrefs)                     # the full stop is not part of it
                self.assertTrue(all(h.startswith("https://") for h in hrefs), hrefs)
                self.assertTrue(all(x[2] == "_blank" and "noopener" in x[3] and "noreferrer" in x[3] for x in got["links"]))
                self.assertTrue(any("javascript:" in x for x in got["nolink"]), got["nolink"])
                self.assertTrue(any("192.168.178.1" in x for x in got["nolink"]), got["nolink"])
                self.assertTrue(any("user:pw@" in x for x in got["nolink"]), got["nolink"])
                self.assertIn(" (example.com)", got["host"])                        # the link text says something else
                self.assertIn(" (evil.example)", got["host"])                       # a link dressed as another address
                self.assertEqual(got["nested"], 0)                                  # never a link inside a link
                self.assertIn("Auf dem Postfix-Server:", got["strong"])
                self.assertIn("Zitat", got["strong"])
                self.assertIn("main.cf", got["code"])
                self.assertIn("rm -rf /tmp/x", got["code"])
                self.assertGreaterEqual(got["li"], 3)
                self.assertEqual(got["th"], 4)
                self.assertTrue(got["shown"])
                self.assertFalse(got["wide"])                                      # 320 px: nothing sticks out
                self.assertNotIn("**", got["plain"])
                self.assertIn("<b>Tag</b>", got["plain"])                           # text stays text
                await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
