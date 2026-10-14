"""Aufräumen: eine Quelle (docs/de/richtlinien.md Teil 17, Dominik 2026-10-14 „dass wir keine doppelten
Einstellungseinträge haben, doppelte Datenführung … dass es einfach immer alles sauber ist“).

Every list, default, name and helper lives in one place. These tests stop new duplicates. What was already
doubled on 2026-10-14 (V01.0.526) stands in an Altlastenliste per test: a file may never get more hits than
its entry, and when a file gets fewer, its entry must shrink with it (the list only gets shorter). A new file
starts at zero.

- a  no own "<think>" filter: common.no_think
- b  no key twice in one dict literal (the second silently wins)
- c  no unused import
- d  no own atomic JSON write (json.dump + os.replace): common.write_json
- e  no own call of the language model's chat/completions
- f  no raw fetch( in the panel's scripts: api()/apiTry() in base.js (sign-in, code dialog, Notaus, loading bar)
- g  group and function names the same in features.py and guides.js
- h  every translation in i18n.js and every class in the style sheets is still used

Reads only app/, so it runs in the app/-only copy the Spark tests too. No wall clock dependence.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import ast
import glob
import json
import os
import re
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")
JS = os.path.join(PANEL, "static", "js")


def py_files():
    """Every Python file of the app outside the tests, by its path below app/."""
    out = {}
    for path in sorted(glob.glob(os.path.join(APP, "*.py")) + glob.glob(os.path.join(PANEL, "*.py"))):
        with open(path, encoding="utf-8") as f:
            out[os.path.relpath(path, APP)] = f.read()
    return out


def count_by_file(files, count):
    found = {}
    for name, src in files.items():
        n = count(name, src)
        if n:
            found[name] = n
    return found


class Ratchet:
    """A test of this kind compares today's hits per file with its Altlastenliste ALT."""
    ALT = {}
    WHAT = ""

    def hits(self):
        raise NotImplementedError

    def test_no_new_and_the_list_shrinks(self):
        now = self.hits()
        more = {f: f"{n} > {self.ALT.get(f, 0)}" for f, n in now.items() if n > self.ALT.get(f, 0)}
        self.assertEqual(more, {}, f"new duplicate ({self.WHAT}); use the one shared place instead")
        less = {f: f"{now.get(f, 0)} < {n}" for f, n in self.ALT.items() if now.get(f, 0) < n}
        self.assertEqual(less, {}, f"cleaned up, thank you: lower these entries in {type(self).__name__}.ALT")


THINK = re.compile(r"re\.(?:sub|compile|split)\([^\n]*</?think>")


class OwnThinkFilter(Ratchet, unittest.TestCase):
    WHAT = "an own <think> filter, use common.no_think"
    ALT = {}

    def hits(self):
        return count_by_file(py_files(), lambda name, src: 0 if name == "common.py" else len(THINK.findall(src)))


class DoubleDictKey(Ratchet, unittest.TestCase):
    WHAT = "a key twice in one dict literal, the second one silently wins"
    ALT = {}

    def hits(self):
        def count(name, src):
            n = 0
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Dict):
                    keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                    n += len(keys) - len(set(keys))
            return n
        return count_by_file(py_files(), count)


class UnusedImport(Ratchet, unittest.TestCase):
    WHAT = "an import nothing uses; an import kept for its side effect gets the comment '# noqa: F401'"
    ALT = {}

    @staticmethod
    def unused(src):
        tree = ast.parse(src)
        lines = src.splitlines()
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    continue
                if re.search(r"#\s*noqa(?!:)|#\s*noqa:[^#]*F401", lines[node.lineno - 1]):
                    continue
                for a in node.names:
                    if a.name == "*":
                        continue
                    imported.append((a.asname or a.name).split(".")[0])
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isidentifier():
                used.add(node.value)    # __all__ and getattr(module, "name")
        return [n for n in imported if n not in used]

    def hits(self):
        return count_by_file(py_files(), lambda name, src: len(self.unused(src)))

    def test_the_scan_sees_an_unused_import(self):
        self.assertEqual(self.unused("import os\nimport re\nre.sub('a', 'b', 'c')\n"), ["os"])
        self.assertEqual(self.unused("import os  # noqa: F401\n"), [])
        self.assertEqual(self.unused("import os.path\nos.path.join('a')\n"), [])


class OwnJsonWrite(Ratchet, unittest.TestCase):
    WHAT = "an own atomic JSON write (json.dump + os.replace), use common.write_json"
    ALT = {}   # all on common.write_json since the big cleanup step 2

    def hits(self):
        def count(name, src):
            if name == "common.py":
                return 0
            n = 0
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = ast.unparse(node)
                    inner = sum(1 for sub in ast.walk(node) if sub is not node
                                and isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)))
                    if not inner and "json.dump(" in body and ("os.replace(" in body or "os.rename(" in body):
                        n += 1
            return n
        return count_by_file(py_files(), count)


class OwnModelCall(Ratchet, unittest.TestCase):
    WHAT = "an own call of the language model (chat/completions); planned: one shared llm.complete"
    ALT = {}   # all through llm.py since the big cleanup step 3
    OWN = {"panel/llm.py": "the one way to the language model"}

    def hits(self):
        return {k: v for k, v in count_by_file(py_files(), lambda name, src: src.count("chat/completions")).items()
                if k not in self.OWN}


class RawFetch(Ratchet, unittest.TestCase):
    WHAT = "a raw fetch( in a panel script, use api()/apiTry() from base.js"
    ALT = {"admin.js": 4, "bewerten.js": 1, "changelog.js": 1, "coadmin.js": 1, "dienste.js": 1, "esp.js": 1,
           "geraete.js": 1, "hilfe.js": 2, "hintergrund.js": 2, "join.js": 1, "laden.js": 2, "me.js": 8,
           "melden.js": 1, "mfa.js": 2, "nas.js": 1, "nasquelle.js": 1, "notaus.js": 2, "proactive.js": 3,
           "room.js": 6, "speicher.js": 1, "start.js": 2, "today.js": 1, "zuordnungen.js": 1}
    OWN = {"base.js": "api() itself", "live.js": "live.html loads without base.js",
           "esptool.js": "the vendored flasher"}

    def hits(self):
        out = {}
        for path in sorted(glob.glob(os.path.join(JS, "*.js"))):
            name = os.path.basename(path)
            if name in self.OWN:
                continue
            with open(path, encoding="utf-8") as f:
                n = len(re.findall(r"(?<![\w.$])fetch\(", f.read()))
            if n:
                out[name] = n
        return out


def panel_text(py=True):
    """Every page, script and (with py) Python module of the panel as one text, whitespace as single spaces."""
    import html
    parts = []
    for path in glob.glob(os.path.join(PANEL, "static", "**", "*"), recursive=True):
        if path.endswith((".html", ".js")) and not path.endswith("i18n.js"):
            with open(path, encoding="utf-8") as f:
                parts.append(f.read())
    if py:
        parts += py_files().values()
    text = re.sub(r"\s+", " ", "\n".join(parts))
    return text + " " + html.unescape(text)


class UnusedText(unittest.TestCase):
    """Every English text in i18n.js belongs to a German text some page, script or module still shows. Texts with
    digits may be built from parts (f-strings) and are left out of the check."""
    def test_every_translation_is_used(self):
        with open(os.path.join(JS, "i18n.js"), encoding="utf-8") as f:
            src = f.read()
        start = src.index("const EN=") + len("const EN=")
        table, _ = json.JSONDecoder().raw_decode(src[start:])
        hay = panel_text()
        dead = [k for k in table if not re.search(r"\d", k) and k not in hay
                and k.replace('"', '\\"') not in hay and k.replace("'", "\\'") not in hay]
        self.assertEqual(dead, [], "a translation nothing shows any more: delete it from i18n.js")


class UnusedCss(unittest.TestCase):
    """Every class in the panel's style sheets is used somewhere. Classes built in code from a prefix stand in DYN."""
    DYN = ("ag-", "c-", "st-", "lz-", "vb-c", "kn-")

    def test_every_class_is_used(self):
        hay = panel_text()
        dead = []
        for path in sorted(glob.glob(os.path.join(PANEL, "static", "*.css"))):
            with open(path, encoding="utf-8") as f:
                css = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
            css = re.sub(r"url\([^)]*\)|\d+\.\d+", "", css)
            for c in sorted(set(re.findall(r"\.(-?[a-zA-Z_][\w-]*)", css))):
                if not c.startswith(self.DYN) and not re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", hay):
                    dead.append(f"{os.path.basename(path)}: .{c}")
        self.assertEqual(dead, [], "a style class nothing uses any more: delete its rule")


class SameNames(unittest.TestCase):
    """features.py is the one source of groups and function names; guides.js keeps a copy for the page."""
    # differences on 2026-10-14; this list only gets shorter
    ALT_GROUPS = set()
    ALT_NAMES = set()

    def setUp(self):
        with open(os.path.join(JS, "guides.js"), encoding="utf-8") as f:
            self.js = f.read()
        with open(os.path.join(PANEL, "features.py"), encoding="utf-8") as f:
            self.py = f.read()

    def py_groups(self):
        block = self.py[self.py.index("GROUPS = ("):]
        block = block[:block.index("\n\n")]
        return {k: (de, en) for k, de, en in re.findall(r'\("(\w+)", "([^"]+)", "([^"]+)"\)', block)}

    def test_group_names(self):
        js = {k: (de, en) for k, de, en in re.findall(
            r"\['(\w+)','([^']+)','([^']+)'\]", self.js[self.js.index("const GGROUPS"):self.js.index("const GSECT")])}
        py = self.py_groups()
        self.assertEqual(sorted(js), sorted(py))
        differ = {k for k in py if py[k] != js[k]}
        self.assertEqual(sorted(differ - self.ALT_GROUPS), [], "group names: take them from features.GROUPS")
        self.assertEqual(sorted(self.ALT_GROUPS - differ), [], "cleaned up, thank you: shrink ALT_GROUPS")

    def test_function_names(self):
        from tests import helpers
        helpers.start()
        import features
        guide = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(
            r"\{id:'(\w+)'[^\n]*?\bt:\['([^']+)','([^']+)'\]", self.js)}
        uses = {}
        for f in features.FEATURES:
            uses.setdefault(f.guide, []).append(f)
        # a guide for one function carries that function's name; a guide for several has its own title
        differ = {f.key for g, fs in uses.items() if len(fs) == 1 and g in guide
                  for f in fs if guide[g] != (f.de, f.en)}
        self.assertEqual(sorted(differ - self.ALT_NAMES), [], "function names: one name in features.py and guides.js")
        self.assertEqual(sorted(self.ALT_NAMES - differ), [], "cleaned up, thank you: shrink ALT_NAMES")


if __name__ == "__main__":
    unittest.main()
