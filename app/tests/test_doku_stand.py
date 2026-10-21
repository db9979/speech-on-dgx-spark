"""The README, its diagram, the docs and the panel's help follow the code (Dominik 2026-10-16: „überprüfe alle
Dokumentationen, Verweise, Schaubilder, README, Hilfen … und merken, dass diese Anpassungen immer automatisch umgesetzt
werden“). After the Spark split and the own language model the README still said the model comes from qwen38 and
every feature is switched per profile; nothing turned red. These tests do:

- worn-out sentences (qwen38 as the only language model, switches per profile) never come back (STALE),
- the README diagram names every public port of config.default.json,
- the ports table of the architecture docs names every port and every speech-spark unit install.sh writes,
- the Technik boxes of the models show the ports from config.default.json,
- every local link and picture in the READMEs exists,
- docs/de and docs/en (and both READMEs) hold the same parts with the same versions (Gleichstand).

The README and docs parts skip in a copy with only app/; the help and Technik parts always run. No clock.
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import anrufe  # noqa: E402
import common  # noqa: E402
import technik  # noqa: E402
import telefon  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
STATIC = os.path.join(APP, "panel", "static")

# sentences that were true once and are not any more; a new stale sentence found later goes here too
STALE = [
    (r"neben \[?dgx-spark-qwen38", "qwen38 is optional since the own language model"),
    (r"next to \[?dgx-spark-qwen38", "qwen38 is optional since the own language model"),
    (r"das das Sprachmodell liefert|which provides the language model", "the own language model exists"),
    (r"LLM von dgx-spark-qwen38|dgx-spark-qwen38 LLM", "the own language model exists"),
    (r"Sprachmodells? \(qwen38\)|language model \(qwen38\)", "own or qwen38"),
    (r"\(qwen38 aus dgx-spark-qwen38, nicht Teil|\(qwen38 from dgx-spark-qwen38, not part", "own or qwen38"),
    (r"Funktion ist pro Profil einzeln schaltbar|feature can be switched on per profile",
     "the admin releases for every profile (Freigabe 2026-10-13)"),
    (r"Funktionen → Wer darf was|Features → Who may do what",
     "the blocks are under Personen und Geräte → Gesperrte Funktionen since V01.0.670"),
    (r"V01\.0\.[A-Z]{3,}", "a version placeholder left in the docs"),
    (r"CarPlay als eigenes Symbol im Auto ist geplant|CarPlay as its own icon in the car is planned",
     "Apple granted CarPlay (V01.0.676)"),
]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def config():
    return json.loads(read(os.path.join(APP, "config.default.json")))


def public_ports(c):
    """The ports apps and devices reach (the engines behind them listen on 127.0.0.1 only)."""
    return {"asr": c["asr"]["port"], "tts": c["tts"]["port"], "image": c["image"]["port"], "music": c["music"]["port"], "llm": c["llm"]["port"],
            "https": c["panel"]["https_port"], "wyoming": c["chat"]["wyoming_port"]}


def all_ports(c):
    found = {}
    for part, values in c.items():
        if isinstance(values, dict):
            for k, v in values.items():
                if (k == "port" or k.endswith("_port")) and isinstance(v, int):
                    found[f"{part}.{k}"] = v
    found.update({"common.WAERTER_PORT": common.WAERTER_PORT, "common.NOTASR_PORT": common.NOTASR_PORT,
                  "telefon.SIP_PORT": telefon.SIP_PORT, "telefon.RTP_PORTS": min(telefon.RTP_PORTS),
                  "anrufe.TURN_PORT": anrufe.TURN_PORT})
    return found


def docs_here():
    return os.path.isfile(os.path.join(ROOT, "README.md")) and os.path.isdir(os.path.join(ROOT, "docs"))


class Stale(unittest.TestCase):
    def files(self):
        out = [os.path.join(STATIC, "index.html"), os.path.join(STATIC, "js", "guides.js"),
               os.path.join(STATIC, "js", "i18n.js")]
        out += [os.path.join(APP, "panel", n) for n in os.listdir(os.path.join(APP, "panel")) if n.startswith("technik")
                and n.endswith(".py")]
        if docs_here():
            out += [os.path.join(ROOT, n) for n in ("README.md", "README.de.md")]
            for lang in ("de", "en"):
                d = os.path.join(ROOT, "docs", lang)
                out += [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".md")]
        return out

    def test_no_stale_sentences(self):
        for path in self.files():
            text = read(path)
            for pattern, why in STALE:
                m = re.search(pattern, text)
                self.assertIsNone(m, f"{os.path.relpath(path, ROOT)}: „{m and m.group(0)}“ is out of date ({why})")


class Technik(unittest.TestCase):
    def test_model_boxes_show_the_configured_ports(self):
        c = config()
        for box, part in (("asr", "asr"), ("tts", "tts"), ("bild", "image"), ("bild", "music"), ("llm", "llm")):
            small = technik.KNOTEN[box][4]
            for key in ("port", "engine_port"):
                self.assertIn(f":{c[part][key]}", small, f"Technik box {box}: {part}.{key}")


@unittest.skipUnless(docs_here(), "README and docs/ not here (app/ alone)")
class Readme(unittest.TestCase):
    def test_diagram_names_every_public_port(self):
        ports = public_ports(config())
        for name in ("README.md", "README.de.md"):
            diagram = re.search(r"```mermaid\n(.*?)```", read(os.path.join(ROOT, name)), re.S)
            self.assertIsNotNone(diagram, name)
            for what, port in ports.items():
                self.assertIn(f":{port}", diagram.group(1), f"{name}: the diagram lacks {what} :{port}")

    def test_local_links_and_pictures_exist(self):
        for name in ("README.md", "README.de.md"):
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", read(os.path.join(ROOT, name))):
                if re.match(r"[a-z]+:", target):
                    continue
                self.assertTrue(os.path.exists(os.path.join(ROOT, target)), f"{name}: {target} is missing")

    def test_ports_table_names_every_port_and_unit(self):
        units = set(re.findall(r"/etc/systemd/system/(speech-spark-[a-z-]+)\.service", read(os.path.join(ROOT, "install.sh"))))
        self.assertIn("speech-spark-panel", units)
        for name, head in (("de/architektur.md", "## Prozesse und Ports"), ("en/architecture.md", "## Processes and ports")):
            text = read(os.path.join(ROOT, "docs", name))
            table = text[text.index(head):]
            table = table[:table.index("\n\n", table.index("|"))]
            for what, port in all_ports(config()).items():
                self.assertIn(str(port), table, f"{name}: the ports table lacks {what} {port}")
            for unit in sorted(units):
                self.assertIn(f"`{unit}`", table, f"{name}: the ports table lacks {unit}")


if __name__ == "__main__":
    unittest.main()


# German and English say the same (Dominik 2026-10-21 „ganze Doku immer aktuell“): every docs/de file has its docs/en
# twin, and README.de.md its README.md; each section holds as many paragraphs, list rows and table rows and names the
# same versions, so a part written only in one language turns this red. The help answers in both languages.
TWINS = (("android-app", "android-app"), ("apis-und-einbinden", "apis-and-integration"), ("app-datenschutz", "app-privacy"),
         ("architektur", "architecture"), ("assistent", "assistant"), ("installation", "installation"),
         ("iphone-app", "iphone-app"), ("iphone-veroeffentlichen", "iphone-publishing"), ("richtlinien", "guidelines"),
         ("sicherheit-und-betrieb", "security-and-operation"), ("sicherheits-checkliste", "security-checklist"),
         ("spark-teilen", "spark-split"), ("technik", "technical"))
UNIT = re.compile(r"\s*(?:[-*] |\d+\. |\||```|<!--|> )")


def sections(text):
    """[(heading, [unit])]: a unit is a paragraph, a list row or a table row; wrapped lines belong to their unit."""
    out, blank, fence = [("", [])], True, False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
        if line.startswith("#") and not fence:
            out.append((line, []))
            blank = True
            continue
        if not line.strip():
            blank = True
            continue
        units = out[-1][1]
        if blank or not units or (UNIT.match(line) and not fence):
            units.append(line)
        else:
            units[-1] += " " + line.strip()
        blank = False
    return out


@unittest.skipUnless(docs_here(), "README and docs/ not here (app/ alone)")
class Gleichstand(unittest.TestCase):
    def test_every_file_has_its_twin(self):
        de = {n[:-3] for n in os.listdir(os.path.join(ROOT, "docs", "de")) if n.endswith(".md")}
        en = {n[:-3] for n in os.listdir(os.path.join(ROOT, "docs", "en")) if n.endswith(".md")}
        self.assertEqual(de, {a for a, _ in TWINS})
        self.assertEqual(en, {b for _, b in TWINS})

    def test_german_and_english_say_the_same(self):
        pairs = [(os.path.join("docs", "de", a + ".md"), os.path.join("docs", "en", b + ".md")) for a, b in TWINS]
        bad = []
        for a, b in pairs + [("README.de.md", "README.md")]:
            sa, sb = sections(read(os.path.join(ROOT, a))), sections(read(os.path.join(ROOT, b)))
            if len(sa) != len(sb):
                bad.append(f"{a}: {len(sa)} sections, {b}: {len(sb)}")
                continue
            for (ha, ua), (hb, ub) in zip(sa, sb):
                va = set(re.findall(r"V01\.0\.\d+", " ".join(ua)))
                vb = set(re.findall(r"V01\.0\.\d+", " ".join(ub)))
                if len(ua) != len(ub) or va != vb:
                    bad.append(f"{a} „{ha[:50]}“ {len(ua)} parts {sorted(va - vb)} / {b} „{hb[:50]}“ {len(ub)} parts {sorted(vb - va)}")
        self.assertEqual(bad, [], "\n".join(bad))
