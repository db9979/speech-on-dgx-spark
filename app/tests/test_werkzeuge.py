"""Readable tool names (werkzeuge.py, Dominik 2026-10-12: „die Werkzeuge haben komische Namen“).

Every tool the language model, the panel or a program over MCP can run has a name in German and English in
werkzeuge.NAMES, the pages read the same table from static/js/werkzeuge.js (written from it), and every page
that shows a tool uses it. No wall clock dependence; runs in a copy with only app/.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import glob
import os
import re
import unittest

from tests import helpers

helpers.start()
import live  # noqa: E402
import weiche  # noqa: E402
import werkzeuge  # noqa: E402

PANEL = os.path.dirname(werkzeuge.__file__)


def read(*parts):
    with open(os.path.join(PANEL, *parts), encoding="utf-8") as f:
        return f.read()


class ToolNames(unittest.TestCase):
    def test_every_tool_has_a_readable_name(self):
        """A new tool (chat.py, a service, the switch, the live picture) needs its name de/en in werkzeuge.NAMES."""
        names = set()
        for path in glob.glob(os.path.join(PANEL, "*.py")):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            names |= set(re.findall(r'"function":\s*\{\s*"name":\s*"([a-z_]+)"', text))
            names |= set(re.findall(r'"type": "function",\s*"name":\s*"([a-z_]+)"', text))
        import intent
        names |= set(intent.known_tools())
        for tools, _ in intent.GROUPS.values():
            names |= set(tools)
        # live.TOOLS holds every tool and the panel's own steps; the snake_case ones are tool names
        names |= {n for n in live.TOOLS if re.fullmatch(r"[a-z][a-z_]*", n)}
        self.assertTrue({"mail_tidy_overview", "web_search", "get_time", "read_page"} <= names, names)
        self.assertEqual(sorted(names - set(werkzeuge.NAMES)), [],
                         "a new tool: give it a readable name (de, en) in werkzeuge.NAMES, then "
                         "python3 app/panel/werkzeuge.py --js")
        for n, (de, en) in werkzeuge.NAMES.items():
            self.assertTrue(de.strip() and en.strip(), n)
            self.assertNotIn("_", de + en, f"{n}: a readable name, not the internal one")
        self.assertIs(weiche.TOOLS, werkzeuge.NAMES)   # the switch's page reads the same table

    def test_label_and_full(self):
        self.assertEqual(werkzeuge.label("mail_tidy_overview"), "Postfach-Überblick")
        self.assertEqual(werkzeuge.label("mail_tidy_overview", english=True), "Mailbox overview")
        self.assertEqual(werkzeuge.full("mail_tidy_overview"), "Postfach-Überblick (mail_tidy_overview)")
        self.assertEqual(werkzeuge.label("local_search (Panel)"), "Erst in eigenen Quellen (Panel)")
        self.assertEqual(werkzeuge.label("mcpu_a1b2c3_list_notes"), "Dienst: list notes")
        self.assertEqual(werkzeuge.label("mcp_a1b2c3_x", english=True), "Service: x")
        # the panel's own steps already are words: they stay as they are, also in the copy
        self.assertEqual(werkzeuge.full("NAS-Sicherung"), "NAS-Sicherung")
        self.assertEqual(werkzeuge.label(None), "")

    def test_pages_read_the_same_table(self):
        """static/js/werkzeuge.js is written from werkzeuge.NAMES and loaded before every page that shows tools."""
        self.assertEqual(read("static", "js", "werkzeuge.js"), werkzeuge.js(),
                         "werkzeuge.js is out of date: python3 app/panel/werkzeuge.py --js")
        for page, before in (("index.html", "base.js"), ("live.html", "live.js")):
            html = read("static", page)
            self.assertIn("/static/js/werkzeuge.js", html, page)
            self.assertLess(html.index("/static/js/werkzeuge.js"), html.index("/static/js/" + before), page)
        # every place a tool shows uses the readable name: Live (way, returns, copy), Logs → Anfragen, Verbessern
        live_js, logs_js, vb_js = read("static", "js", "live.js"), read("static", "js", "logs.js"), read("static", "js", "verbessern.js")
        self.assertIn("s.k==='tool'?wzName(s.n)", live_js)
        self.assertIn("lvE(wzName(x.tool))", live_js)
        self.assertIn("wzFull(s.n)", live_js)
        self.assertIn("wzName(s.n));b.title=s.n", logs_js)
        self.assertIn("s.k==='tool'?wzName(s.n):s.n}", logs_js)
        self.assertIn("wzName(x.tool)", vb_js)
        self.assertIn("werkzeuge.full(n) for n in bad", read("berater.py"))


if __name__ == "__main__":
    unittest.main()
