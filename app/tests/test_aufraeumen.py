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
- i  no own reader of a request body: core.json_body
- j  the conversation settings' defaults and allowed values only in profiles.SETTINGS and profiles.CHOICES: no copy
     in a script or another module (the browser gets them from /api/profile/settings)
- k  the state folder only from common.STATE; the panel's files only in the register dateien.py (backup, speicher
     and technik take their lists from it)
- l  no one-line wrapper around features.allowed (a function that only returns it): call features.allowed
     directly; the features.admin_on wrappers are the audited places of test_sperre_ueberall.ADMIN_ON_OK

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
    WHAT = "an own call of the language model (chat/completions), use llm.complete"
    ALT = {}   # all through llm.py since the big cleanup step 3
    OWN = {"panel/llm.py": "the one way to the language model",
           "modelle.py": "measures one engine directly on its own port (stage E0), never the panel's language model",
           "llm_tor.py": "is the door in front of the own engine itself (stage E2), the panel reaches it through llm.py"}

    def hits(self):
        return {k: v for k, v in count_by_file(py_files(), lambda name, src: src.count("chat/completions")).items()
                if k not in self.OWN}


class OwnBodyReader(Ratchet, unittest.TestCase):
    WHAT = "an own reader of a request's JSON body, use core.json_body (size limit while reading)"
    ALT = {}   # all on core.json_body since the big cleanup step 4
    OWN = {("panel/chats.py", "_box_media"): "one JSON line, then the sealed file as bytes"}

    def hits(self):
        def count(name, src):
            if name == "panel/core.py":
                return 0
            n = 0
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = ast.unparse(node)
                    if ("request.body()" in body or "request.stream()" in body) and "json.loads(" in body \
                            and (name, node.name) not in self.OWN:
                        n += 1
            return n
        return count_by_file(py_files(), count)


class RawFetch(Ratchet, unittest.TestCase):
    WHAT = "a raw fetch( in a panel script, use api()/apiTry() from base.js"
    ALT = {}   # all through api() or marked /*raw: why*/ since the big cleanup step 5
    OWN = {"base.js": "api() itself", "live.js": "live.html loads without base.js",
           "esptool.js": "the vendored flasher"}

    def hits(self):
        out = {}
        for path in sorted(glob.glob(os.path.join(JS, "*.js"))):
            name = os.path.basename(path)
            if name in self.OWN:
                continue
            with open(path, encoding="utf-8") as f:
                src = f.read()
            # a raw fetch with its reason right before it, /*raw: why*/fetch(, is a decided exception
            n = sum(1 for m in re.finditer(r"(?<![\w.$])fetch\(", src)
                    if not re.search(r"/\*raw: [^*]{3,}\*/\s*$", src[max(0, m.start() - 160):m.start()]))
            if n:
                out[name] = n
        return out


class CheckWrapper(Ratchet, unittest.TestCase):
    WHAT = "a one-line wrapper around features.allowed, call features.allowed directly"
    # kept on purpose (big cleanup step 9): handed over as a gate callback (profiles.*_GATE), or a test patches it.
    # Wrappers of features.admin_on are not counted: they are the audited places of test_sperre_ueberall.ADMIN_ON_OK.
    ALT = {"panel/begleiter.py": 1,       # allowed: profiles.DESK_GATE
           "panel/iphone.py": 1,          # allowed: profiles.APP_GATE
           "panel/kiwix.py": 1,           # usable: test_folien patches it
           "panel/pebblewatch.py": 1,     # allowed: profiles.WATCH_GATE
           "panel/rmliste.py": 1,         # on: test_werkzeug_abdeckung patches it
           "panel/roomlive.py": 1}        # _gate: profiles.ROOM_GATE

    @staticmethod
    def wrappers(src):
        """Names of the module's functions whose body (besides a docstring) is only `return features.allowed(...)`
        with plain names and constants, also behind a `bool(uid) and` guard (features.allowed is False for no uid)."""
        def check(e):
            return (isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and isinstance(e.func.value, ast.Name)
                    and e.func.value.id == "features" and e.func.attr == "allowed" and not e.keywords
                    and all(isinstance(a, (ast.Name, ast.Constant)) for a in e.args))
        out = []
        for node in ast.parse(src).body:
            if not isinstance(node, ast.FunctionDef) or node.decorator_list:
                continue
            body = node.body[1:] if ast.get_docstring(node) is not None else node.body
            if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
                continue
            e = body[0].value
            if isinstance(e, ast.BoolOp) and isinstance(e.op, ast.And) and len(e.values) == 2 \
                    and isinstance(e.values[0], ast.Call) and getattr(e.values[0].func, "id", "") == "bool" \
                    and all(isinstance(a, ast.Name) for a in e.values[0].args):
                e = e.values[1]
            if check(e):
                out.append(node.name)
        return out

    def hits(self):
        return count_by_file(py_files(), lambda name, src: 0 if name == "panel/features.py" else len(self.wrappers(src)))

    def test_the_scan_sees_a_wrapper(self):
        self.assertEqual(self.wrappers('def a(uid):\n    return features.allowed("x", uid)\n'), ["a"])
        self.assertEqual(self.wrappers('def d():\n    return features.admin_on("x")\n'), [])   # ADMIN_ON_OK
        src = 'def b(uid, c=None):\n    """Doc."""\n    return bool(uid) and features.allowed("x", uid, c)\n'
        self.assertEqual(self.wrappers(src), ["b"])
        self.assertEqual(self.wrappers('def c(uid):\n    return features.allowed("x", uid) and has(uid)\n'), [])


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
    DYN = ("ag-", "c-", "st-", "lz-", "vb-c", "kn-", "mdf-")

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


class SettingCopies(unittest.TestCase):
    """profiles.SETTINGS holds the defaults, profiles.CHOICES the allowed values of the conversation settings, once.
    No script keeps an object of defaults (three or more settings with their default) or a list of the allowed values
    (three in a row, or two as [value, label] pairs); no other module a tuple or list equal to one of CHOICES."""
    def setUp(self):
        from tests import helpers
        helpers.start()
        import profiles
        self.settings, self.choices = profiles.SETTINGS, profiles.CHOICES

    @staticmethod
    def lit(v):
        s = str(v)
        return r"['\"]?" + re.escape(s) + r"['\"]?" if s.isdigit() else r"['\"]" + re.escape(s) + r"['\"]"

    def js_defaults(self, src):
        n = 0
        for body in re.findall(r"\{([^{}]*)\}", src):
            same = 0
            for k, v in re.findall(r"(?<![\w.])(\w+)\s*:\s*('[^'\n]*'|true|false|-?\d+(?:\.\d+)?)(?=\s*[,}]|$)", body):
                if k in self.settings:
                    d = self.settings[k][0]
                    js = "true" if d is True else "false" if d is False else f"'{d}'" if isinstance(d, str) else None
                    same += js == v or (js is None and not isinstance(d, (list, dict)) and v == str(d))
            n += same >= 3
        return n

    def js_lists(self, src):
        n = 0
        for vals in self.choices.values():
            if len(vals) >= 3:
                n += len(re.findall(r"\[\s*" + r"\s*,\s*".join(self.lit(v) for v in vals[:3]), src))
            pair = r"\[\s*\[\s*" + self.lit(vals[0]) + r"\s*,[^\]]*\]\s*,\s*\[\s*" + self.lit(vals[1]) + r"\s*,"
            n += len(re.findall(pair, src))
        return n

    def test_no_copy_in_the_scripts(self):
        hits = {}
        for path in sorted(glob.glob(os.path.join(JS, "*.js"))):
            with open(path, encoding="utf-8") as f:
                src = f.read()
            n = self.js_defaults(src) + self.js_lists(src)
            if n:
                hits[os.path.basename(path)] = n
        self.assertEqual(hits, {}, "settings' defaults or allowed values copied into a script: use SDEF and SETC "
                                   "(me.js loadSettings, from profiles.SETTINGS and profiles.CHOICES)")

    def test_no_copy_in_other_modules(self):
        want = {tuple(v) for v in self.choices.values() if len(v) >= 2}
        hits = []
        for name, src in py_files().items():
            if name == os.path.join("panel", "profiles.py"):
                continue
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Constant) for e in node.elts):
                    if tuple(e.value for e in node.elts) in want:
                        hits.append(f"{name}:{node.lineno}")
        self.assertEqual(hits, [], "a copy of a list of profiles.CHOICES: use profiles.CHOICES[key]")

    def test_lists_that_follow_a_module(self):
        """Two lists name what a module has: the reMarkable models (rmpapier.MODELS) and the delivery targets."""
        import docmake
        import rmpapier
        self.assertEqual(self.choices["rm_model"], ("auto",) + tuple(rmpapier.MODELS))
        self.assertEqual(set(docmake.TARGETS), set(docmake.TARGET_NAMES))


class StateFolder(unittest.TestCase):
    """The state folder comes from common.STATE (SPEECH_SPARK_STATE), no module reads the variable itself."""
    # file -> how often it may name the variable, with the reason
    ALLOWED = {"common.py": 1,          # STATE itself
               "panel/update.py": 1}    # HOME for git: the state folder, else /tmp (not the state default)

    def test_only_common_reads_it(self):
        hits = count_by_file(py_files(), lambda name, src: src.count("SPEECH_SPARK_STATE"))
        self.assertEqual(hits, self.ALLOWED, "take the state folder from common.STATE")


class FileRegister(unittest.TestCase):
    """Every file the panel keeps has one line in dateien.py; backup, speicher and technik only take their lists from it."""
    LISTS = {"backup": ("STATE_FILES", "STATE_LOCAL"), "speicher": ("AREAS", "LOCAL"),
             "technik": ("INHALT", "VERSCHLUESSELT", "USERS_SONST", "USERS_GLOBAL", "STATE_SONST")}

    def test_no_own_list(self):
        own = []
        for mod, names in self.LISTS.items():
            for node in ast.walk(ast.parse(py_files()[os.path.join("panel", mod + ".py")])):
                if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    continue
                for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    pairs = (zip(t.elts, node.value.elts) if isinstance(t, ast.Tuple) and isinstance(node.value, ast.Tuple)
                             else [(t, node.value)])
                    for target, value in pairs:
                        if isinstance(target, ast.Name) and target.id in names and ast.unparse(value) != "dateien." + target.id:
                            own.append(f"{mod}.{target.id}")
        self.assertEqual(own, [], "a list of files written again: give the file its line in dateien.py")

    def test_the_lists_are_the_register(self):
        from tests import helpers
        helpers.start()
        import importlib
        import dateien
        for mod, names in self.LISTS.items():
            m = importlib.import_module(mod)
            for n in names:
                self.assertIs(getattr(m, n), getattr(dateien, n), f"{mod}.{n}")

    def test_each_file_once(self):
        import sys
        sys.path.insert(0, PANEL)
        import dateien
        seen = [(d.ort, d.name) for d in dateien.DATEIEN]
        self.assertEqual(sorted(k for k in set(seen) if seen.count(k) > 1), [])
        self.assertEqual(len(dateien.INHALT), len(seen))
        for d in dateien.DATEIEN:
            self.assertIn(d.ort, ("state", "profil", "users", "anderswo"), d.name)
            self.assertTrue(d.de and d.en, d.name)
            self.assertTrue(not d.bereich or d.bereich in dateien.BEREICHE, d.name)
            if d.ort == "state":
                self.assertTrue(bool(d.sicherung) != bool(d.lokal), f"{d.name}: in the backup or a reason why not")
            if d.ort == "profil":
                self.assertTrue(bool(d.bereich) != bool(d.art), f"{d.name}: an area of the copy or its kind")


if __name__ == "__main__":
    unittest.main()
