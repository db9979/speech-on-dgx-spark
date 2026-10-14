"""Zustand → Technik, Knoten-Seiten (plan plaene/knoten-seiten.md, Dominik 2026-10-14 „1, A, B und C“): for every box of
the picture one page that says exactly how it works: what it does and why, its way as a picture with numbered steps
(questions with their exits), rules, numbers, where to switch it, where to see it working, its code and its
neighbours. Examples („Durchspielen“) light the way of one case step by step; „heute“ shows today's counts.

The pages stay true with the code (Dominik 2026-10-14: „ebenso aktuell halten wie alles andere“):
- numbers are never typed: {netguard.MAX_BYTES|mb} in a text is read from the code when the page is built;
- lists of callers are searched in the code ({@name}, AUTO below), so a new caller shows up by itself;
- every function, class or constant a page names must exist (tests/test_technik.py);
- „stand“ is a fingerprint of the code a page describes (its "code" list and the constants of its numbers, without
  comments and docstrings). When that code changes, test_technik turns red until the page was checked and its
  fingerprint written again, so a change of a part comes with its page in the same commit.

Only names of modules, functions and settings, never contents, addresses or profiles. Nothing here switches anything.
"""
import ast
import functools
import hashlib
import importlib
import io
import os
import re
import textwrap
import tokenize

from technik_seiten import OFFEN, SEITEN_DATEN, S  # noqa: F401  (S for the pages, re-exported)

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
GITHUB = "https://github.com/db9979/speech-on-dgx-spark/blob/main/"

# labels of a question's exits ("ja" leaves to the side, the way goes on with the other one)
LABELS = {"ja": ("ja", "yes"), "nein": ("nein", "no")}
OTHER = {"ja": "nein", "nein": "ja"}
ARTEN = ("start", "schritt", "frage", "ende")
SEITEN = ("stop", "ok", "zurueck", "info")   # red end, „weiter bei N“, back to an earlier step, a note


# ---------------------------------------------------------------- lists searched in the code
def _callers(*patterns):
    """Modules of app/panel whose code matches one of the patterns (comments left out), sorted."""
    out = set()
    for f in sorted(os.listdir(HERE)):
        if not f.endswith(".py") or f in ("netguard.py", "technik_knoten.py"):
            continue
        try:
            with open(os.path.join(HERE, f), encoding="utf-8") as fh:
                src = re.sub(r"(?m)#.*$", "", fh.read())
        except OSError:
            continue
        if any(re.search(p, src) for p in patterns):
            out.add(f[:-3])
    return sorted(out)


AUTO = {
    "stufe_public": lambda: _callers(r"netguard\.client\(\s*netguard\.PUBLIC"),
    "stufe_user": lambda: _callers(r"netguard\.client\(\s*netguard\.USER", r"netguard\.IMAP4_SSL"),
    "stufe_home": lambda: _callers(r"netguard\.client\(\s*netguard\.HOME"),
    "stufe_wechselnd": lambda: _callers(r"netguard\.(client|resolve)\(\s*(?!netguard\.)(?!seen=)(?!verify=)\w"),
    "netguard_nutzer": lambda: _callers(r"netguard\.(client|resolve|IMAP4_SSL)\b"),
}


# ---------------------------------------------------------------- numbers and names from the code
def wert(path):
    """The value behind "netguard.MAX_BYTES" or "notaus.AUTO.netguard.0" (module, then attributes, keys, indexes). A
    constant is read from the source as it is written (so a test that sets it for itself does not change the page);
    only what is not a plain constant expression is taken from the imported module."""
    parts = path.split(".")
    try:
        obj, rest = _quelle(parts[0], parts[1]), parts[2:]
    except (KeyError, ValueError, TypeError, OSError, SyntaxError):
        obj = importlib.import_module(parts[0])
        rest = parts[1:]
    for p in rest:
        if isinstance(obj, dict):
            obj = obj[p]
        elif isinstance(obj, (list, tuple)):
            obj = obj[int(p)]
        else:
            obj = getattr(obj, p)
    return obj


_OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b, ast.Pow: lambda a, b: a ** b, ast.BitOr: lambda a, b: a | b, ast.Mod: lambda a, b: a % b}
_CALLS = {"set": set, "frozenset": frozenset, "range": range, "tuple": tuple, "list": list, "dict": dict, "int": int}


def _quelle(mod, name):
    """A module-level constant evaluated from its source (numbers, strings, containers, arithmetic, set/range and other
    constants of the same module); KeyError when it is not there, ValueError when it is not such an expression."""
    src, tree = _tree(_file(mod) or "\0")
    for x in tree.body:
        if isinstance(x, ast.Assign):
            for t in x.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return _eval(x.value, mod)
                if isinstance(t, ast.Tuple) and isinstance(x.value, ast.Tuple):
                    for e, v in zip(t.elts, x.value.elts):
                        if isinstance(e, ast.Name) and e.id == name:
                            return _eval(v, mod)
        elif isinstance(x, ast.AnnAssign) and isinstance(x.target, ast.Name) and x.target.id == name and x.value:
            return _eval(x.value, mod)
    raise KeyError(name)


def _eval(n, mod):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, (ast.Tuple, ast.List, ast.Set)):
        items = [_eval(e, mod) for e in n.elts]
        return tuple(items) if isinstance(n, ast.Tuple) else set(items) if isinstance(n, ast.Set) else items
    if isinstance(n, ast.Dict):
        return {_eval(k, mod): _eval(v, mod) for k, v in zip(n.keys, n.values)}
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_eval(n.left, mod), _eval(n.right, mod))
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
        return -_eval(n.operand, mod)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _CALLS and not n.keywords:
        return _CALLS[n.func.id](*[_eval(a, mod) for a in n.args])
    if isinstance(n, ast.Name):
        return _quelle(mod, n.id)
    raise ValueError(ast.dump(n)[:40])


def _bereiche(v):
    nums, out = sorted(int(x) for x in v), []
    for n in nums:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return ", ".join(f"{a}–{b}" if b > a else str(a) for a, b in out)


FORMATE = {"": str, "mb": lambda v: f"{int(v) // 1048576} MB", "min": lambda v: str(int(v) // 60), "bereiche": _bereiche,
           "anzahl": lambda v: str(len(v))}
PLATZ = re.compile(r"\{(@?[\w.]+)(?:\|(\w+))?\}")


def fill(text):
    """A text with its numbers and lists from the code."""
    def one(m):
        name, fmt = m.group(1), m.group(2) or ""
        if name.startswith("@"):
            found = AUTO[name[1:]]()
            return str(len(found)) if fmt == "anzahl" else ", ".join(found)
        return FORMATE[fmt](wert(name))
    return PLATZ.sub(one, text)


def placeholders(page):
    """Every {…} of a page (for the test)."""
    return sorted(set(m.group(0) for s in _texts(page) for m in PLATZ.finditer(s)))


def _texts(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _texts(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _texts(v)


def _file(mod):
    for base in (HERE, APP):
        p = os.path.join(base, mod + ".py")
        if os.path.exists(p):
            return p
    return ""


@functools.lru_cache(maxsize=64)
def _tree(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return src, ast.parse(src)


def finden(ref):
    """The source of "netguard.allowed" or "netguard._Transport.handle_async_request" (None when it is gone)."""
    mod, *names = ref.split(".")
    path = _file(mod)
    if not path or not names:
        return None
    src, node = _tree(path)
    for n in names:
        body = getattr(node, "body", [])
        hit = None
        for x in body:
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and x.name == n:
                hit = x
            elif isinstance(x, (ast.Assign, ast.AnnAssign)):
                targets = x.targets if isinstance(x, ast.Assign) else [x.target]
                names_ = [t for t in targets if isinstance(t, ast.Name)]
                names_ += [e for t in targets if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name)]
                if any(t.id == n for t in names_):
                    hit = x
        if hit is None:
            return None
        node = hit
    seg = ast.get_source_segment(src, node, padded=True) or ""
    doc = node.body[0] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body and \
        isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant) and \
        isinstance(node.body[0].value.value, str) else None
    if doc is not None:
        seg = seg.replace(ast.get_source_segment(src, doc) or "\0", "pass", 1)
    return seg


def _tokens(seg):
    """The code without comments, blank lines and indentation, so only a change of what it does counts."""
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    try:
        toks = tokenize.generate_tokens(io.StringIO(textwrap.dedent(seg)).readline)
        return " ".join(t.string for t in toks if t.type not in skip)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return " ".join(seg.split())


# lists that nearly every new feature adds a line to: a page names them, but their growth does not change how the box
# works, so they stay out of the fingerprint (else every feature would have to touch these pages)
FLUECHTIG = {"logfilter.AREAS", "werkzeuge.NAMES", "panel.stability"}


def refs(page):
    """What a page's fingerprint covers: its code list and the constants of its numbers (without FLUECHTIG)."""
    out = [r for r, _ in page.get("code", []) if r not in FLUECHTIG]
    out += [z[2] for z in page.get("zahlen", []) if len(z) > 2 and z[2]]
    return sorted(set(out) - FLUECHTIG)


def stand(page):
    """The fingerprint of the code a page describes (10 hex digits)."""
    h = hashlib.sha256()
    for r in refs(page):
        seg = finden(r)
        h.update(r.encode() + b"\0" + _tokens(seg or "").encode() + b"\n")
    return h.hexdigest()[:10]


# ---------------------------------------------------------------- one page for the panel and the docs
def _pick(v, i):
    if isinstance(v, (tuple, list)) and len(v) == 2 and all(isinstance(x, str) for x in v):
        return fill(v[i])
    return fill(v) if isinstance(v, str) else ""


def _label(v, i):
    if isinstance(v, str):
        return LABELS.get(v, (v, v))[i]
    return v[i]


@functools.lru_cache(maxsize=64)
def seite(nid, lang="de"):
    """One box's page in one language (texts filled from the code), or None when the box has no page yet."""
    p = SEITEN_DATEN.get(nid)
    if not p:
        return None
    i = 1 if lang == "en" else 0
    steps = []
    for n, s in enumerate(p["ablauf"], 1):
        side = None
        if s["side"]:
            kind, label, what = s["side"]
            side = {"kind": kind, "label": _label(label, i)}
            if kind in ("ok", "zurueck"):
                to = next(k for k, x in enumerate(p["ablauf"], 1) if x["id"] == what)
                side.update(to=what, n=to)
            else:
                side["text"] = _pick(what, i)
            if s["art"] == "frage" and isinstance(label, str):
                side["main"] = LABELS[OTHER[label]][i]
        steps.append({"id": s["id"], "n": n, "art": s["art"], "name": _pick(s["name"], i), "sub": _pick(s["sub"], i),
                      "text": _pick(s["text"], i), "side": side})
    rules = [[_pick(c, i) if not isinstance(c, str) else fill(c) for c in row] for row in p.get("regeln", [])]
    code = [{"ref": r, "text": _pick(t, i), "file": os.path.relpath(_file(r.split(".")[0]), os.path.dirname(APP))}
            for r, t in p.get("code", [])]
    return {"id": nid, "kurz": _pick(p["kurz"], i), "warum": _pick(p["warum"], i), "steps": steps,
            "examples": [{"name": _pick(b[0], i), "path": b[1], "result": _pick(b[2], i)} for b in p.get("beispiele", [])],
            "rules": rules, "numbers": [{"value": fill(z[0]), "text": _pick(z[1], i)} for z in p.get("zahlen", [])],
            "settings": [_pick(x, i) for x in p.get("einstellen", [])], "see": [_pick(x, i) for x in p.get("sehen", [])],
            "more": [{"title": _pick(t, i), "lines": [_pick(x, i) for x in lines]} for t, lines in p.get("mehr", [])],
            "code": code, "tests": list(p.get("tests", [])), "github": GITHUB,
            "today_keys": [[k, _pick(t, i)] for k, t in p.get("heute", [])]}


def heute(nid):
    """Today's counts of a box (numbers only; empty while Live is off)."""
    p = SEITEN_DATEN.get(nid) or {}
    keys = [k for k, _ in p.get("heute", [])]
    if not keys:
        return {}
    try:
        import live
        c = live.counts_today() if live.on() else None
    except Exception:
        c = None
    if c is None:
        return {"off": True}
    return {k: int(c.get(k, 0)) for k in keys}


# ---------------------------------------------------------------- the docs
def _mm(s):
    return s.replace('"', "'").replace("<", "‹").replace(">", "›")


def mermaid(nid, lang="de"):
    """A page's way as a Mermaid flowchart (top to bottom, exits to the side)."""
    d = seite(nid, lang)
    shape = {"start": ('(["', '"])'), "ende": ('(["', '"])'), "frage": ('{{"', '"}}'), "schritt": ('["', '"]')}
    lines = ["```mermaid", "flowchart TD"]
    for s in d["steps"]:
        a, b = shape[s["art"]]
        lines.append(f'  {s["id"]}{a}{s["n"]}. {_mm(s["name"])}{b}')
    for s, nxt in zip(d["steps"], d["steps"][1:]):
        main = (s["side"] or {}).get("main")
        lines.append(f'  {s["id"]} -->{"|" + main + "|" if main else ""} {nxt["id"]}')
    for s in d["steps"]:
        x = s["side"]
        if not x:
            continue
        if x["kind"] in ("ok", "zurueck"):
            lines.append(f'  {s["id"]} -.->|{_mm(x["label"])}| {x["to"]}')
        else:
            lines.append(f'  {s["id"]}x(["{_mm(x["text"])}"])')
            lines.append(f'  {s["id"]} -->|{_mm(x["label"])}| {s["id"]}x')
    lines.append("```")
    return "\n".join(lines)


TXT = {"de": {"warum": "Warum", "ablauf": "Ablauf", "regeln": "Regeln", "zahlen": "Zahlen (aus dem Code)",
              "einstellen": "Einstellen", "sehen": "Was du siehst", "code": "Im Code", "tests": "Selbsttests",
              "beispiele": "Beispiele", "nein": "nein"},
       "en": {"warum": "Why", "ablauf": "Way", "regeln": "Rules", "zahlen": "Numbers (from the code)",
              "einstellen": "Settings", "sehen": "What you see", "code": "In the code", "tests": "Self-tests",
              "beispiele": "Examples", "nein": "no"}}


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def doc(lang, names):
    """Every page as a section of the architecture doc. names: node id -> its name in this language."""
    x = TXT[lang]
    out = []
    for nid in [k for k in names if k in SEITEN_DATEN]:
        d = seite(nid, lang)
        out += [f"### {names[nid]}", "", d["kurz"], "", f"**{x['warum']}:** {d['warum']}", "", f"#### {x['ablauf']}", "",
                mermaid(nid, lang), ""]
        out += [f"{s['n']}. **{s['name']}**: {s['text']}" for s in d["steps"]]
        if d["examples"]:
            out += ["", f"**{x['beispiele']}:** " + " · ".join(f"{e['name']}: {e['result']}" for e in d["examples"])]
        if d["rules"]:
            head, *rows = d["rules"]
            out += ["", f"#### {x['regeln']}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            out += ["| " + " | ".join(_cell(c) or "–" for c in r) + " |" for r in rows]
        for m in d["more"]:
            out += ["", f"#### {m['title']}", ""] + [f"- {ln}" for ln in m["lines"]]
        if d["numbers"]:
            out += ["", f"#### {x['zahlen']}", ""] + [f"- **{z['value']}** {z['text']}" for z in d["numbers"]]
        if d["settings"]:
            out += ["", f"#### {x['einstellen']}", ""] + [f"- {s}" for s in d["settings"]]
        if d["see"]:
            out += ["", f"#### {x['sehen']}", ""] + [f"- {s}" for s in d["see"]]
        out += ["", f"#### {x['code']}", ""] + [f"- `{c['file']}` `{c['ref'].split('.', 1)[1]}`: {c['text']}" for c in d["code"]]
        if d["tests"]:
            out += ["", f"{x['tests']}: " + ", ".join(f"`{t}`" for t in d["tests"])]
        out.append("")
    return "\n".join(out).rstrip()
