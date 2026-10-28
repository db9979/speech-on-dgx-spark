"""KI-Dungeon-Master: the narrator bench „Erzähler-Prüfstand“ (dungeon_erzaehlstand.py, Tabletop-Punkt 4 of 2026-10-25,
Dominik „ich hätte gerne alle punkte umgesetzt“).

- Every scene goes through the real steps of a turn (dungeon.ask_checks, dungeon.tell) on a round only in memory:
  nothing of the rounds is written, nothing counts into the day's numbers.
- The fixed rules give the points: 2 for the first try, 1 after a rewrite, 0 refused or repaired; the checks scenes
  2 or 0; a person by name, an English round in English. The model's own Einordnung never gives points.
- Only the admin and only while „Erzähler-Prüfstand“ is on; the button at most every KNOPF_S, one run at a time;
  the result per model name, the live overview with numbers only.

No wall clock: the module's clock is set by the tests; the language model is a fixed fake.
"""
import asyncio
import contextlib
import io
import json
import os
import threading
import unittest
from unittest import mock

from tests.test_dungeon_dingbild import ADMIN, Base
import dungeon  # noqa: E402
import dungeon_erzaehlstand as es  # noqa: E402
import live  # noqa: E402
from tests import helpers  # noqa: E402

P = "/api/admin/dungeon/erzaehlstand"


def model(foe, good=True):
    """A fake model: for the checks a check only on the cliff (good) or always (bad); for the narration a fitting text,
    or (bad) the failed door told as done, blood at the children's table and German in the English round."""
    async def ask(system, user, schema, name, tokens):
        if name == "proben":
            if "Felswand" in user or not good:
                return json.dumps({"proben": [{"wer": "Arvid", "wert": "geschick", "schwer": 14, "wofuer": "die Felswand hinaufklettern"}]})
            return json.dumps({"proben": []})
        if "Holztür" in user:
            t = ("Arvid wirft sich mit aller Kraft gegen die alte Holztür, doch sie hält stand und rührt sich keinen Fingerbreit. "
                 "Staub rieselt von der Decke." if good else
                 "Arvid wirft sich mit aller Kraft gegen die alte Holztür, und die Holztür bricht auf. Staub rieselt von der Decke herab.")
        elif "cellar" in user:
            t = ("Arvid lights the torch and the cellar comes alive: old barrels, cobwebs and a narrow stair that leads down "
                 "into the dark." if good else
                 "Arvid zündet die Fackel an und der Keller ist voller Fässer und Spinnweben, und die Treppe führt nach unten ins Dunkel.")
        elif "Oskar" in user:
            t = "Oskar wischt den Tresen ab und brummt: „Der alte Turm? Hinter dem Moor, zwei Stunden nach Norden.“ Arvid nickt ihm zu."
        elif "Wolf" in user:
            t = ("Arvid stürzt sich auf den Wolf, der erschrocken zurückweicht und mit eingezogenem Schwanz zwischen den Bäumen "
                 "verschwindet." if good else "Arvid stürzt sich auf den Wolf, Blut spritzt über den Waldboden und der Wolf heult laut auf.")
        elif "überlege" in user:              # „Sackgasse“ (Spieler anleiten): two points and a concrete choice, or hollow
            t = ("Arvid sieht sich in der hohen Halle um. Grimma lehnt an einer eisenbeschlagenen Truhe und mustert ihn "
                 "schweigend. Arvid, sprichst du mit Grimma, oder öffnest du die Truhe?" if good else
                 "Arvid steht in der hohen Halle, und die Stille drückt schwer auf seine Schultern, während der Wind heult. Was tut ihr?")
        elif "Spuren" in user:
            t = ("Arvid kniet sich hin und findet frische Spuren im Staub. Bela fragt den Wirt, der nur mit den Schultern zuckt "
                 "und auf die Tür zeigt.")
        else:
            t = (f"Arvid stürmt auf {foe} zu, doch der Hieb geht daneben. {foe} weicht aus und kreischt, der zweite drängt "
                 "von der Seite heran.")
        return json.dumps({"erzaehlung": t, "frage_an": ""})
    return ask


class Bench(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_erzaehlstand", "systemone")
        helpers.set_config(dungeon_erzaehlstand=False, systemone=False)
        self.t = [1_790_000_000]
        p = mock.patch("dungeon_erzaehlstand.clock", lambda: self.t[0])
        p.start()
        self.addCleanup(p.stop)
        es._run.update(laeuft=False, seit=0, task=None)
        self._drop()
        self.addCleanup(self._drop)
        r = dungeon.rules()
        self.foe = es.scene(r, "kampf")[0]["kampf"]["gegner"][0]["name"]

    def _drop(self):
        if os.path.exists(es.FILE):
            os.remove(es.FILE)

    def _rounds(self):
        """The rounds' files with their change times (one file per round, dungeon_ablage)."""
        d = dungeon.ablage.DIR
        return sorted((f, os.path.getmtime(os.path.join(d, f))) for f in os.listdir(d)) if os.path.isdir(d) else []

    def _play(self, good):
        r = dungeon.rules()
        with mock.patch("dungeon.ask_model", model(self.foe, good)):
            return {sid: asyncio.run(es.play(r, sid)) for sid in es.SZENEN}

    def test_every_scene_by_the_fixed_rules(self):
        runden = self._rounds()
        before = dict(dungeon._day)
        good = self._play(True)
        self.assertEqual({k: v["punkte"] for k, v in good.items()}, {k: 2 for k in es.SZENEN}, good)
        self.assertEqual(good["tuer"]["versuche"], 1)
        bad = self._play(False)
        self.assertEqual(bad["tuer"]["punkte"], 0)                       # told as done on every try: only the repair is left
        self.assertEqual(bad["tuer"]["grund"], "probe")
        self.assertEqual((bad["kinder"]["punkte"], bad["kinder"]["grund"]), (0, "abgelehnt"))   # a word of the children's list
        self.assertEqual((bad["englisch"]["punkte"], bad["englisch"]["grund"]), (0, "deutsch"))
        self.assertEqual((bad["ruhe"]["punkte"], bad["ruhe"]["grund"]), (2, "ok"))   # a check for a good morning: the panel drops it (ALLTAG)
        self.assertEqual(bad["probe"]["punkte"], 2)
        self.assertEqual((bad["sackgasse"]["punkte"], bad["sackgasse"]["grund"], bad["sackgasse"]["versuche"]), (0, "vage", 2))
        self.assertEqual(dict(dungeon._day), before)                    # nothing of the bench counts
        self.assertEqual(self._rounds(), runden)                         # no round written
        self.assertNotIn("einordnung", good["zwei"])                    # Einordnung off: none

    def test_everyday_acts_need_no_check(self):
        """Erzähler-Prüfstand 28.10. („Harmlose Aktion ohne Probe“ 0 points): greeting, eating, unpacking are never a
        check by the panel's fixed rule (dungeon.ALLTAG, every part of the action), whatever the model asks; a word of
        RISIKO, a risky food or drink (ALLTAG_NICHT) or any other part keeps the model's check."""
        for t in ("Ich wünsche den anderen einen guten Morgen und packe mein Brot aus.", "Ich grüße den Wirt.", "Ich lächle und nicke.",
                  "Ich esse und trinke.", "I greet the others and unpack my bread."):
            self.assertTrue(dungeon.everyday(t), t)
        for t in ("Ich klettere die Wand hinauf.", "Ich packe mein Brot aus und schleiche mich vorbei.", "Ich trinke den Trank aus der Truhe.",
                  "Ich esse den Pilz und untersuche die Tür.", "Ich trinke aus dem Brunnen.", "Ich greife an.", ""):
            self.assertFalse(dungeon.everyday(t), t)
        r = dungeon.rules()
        rd, _ = es.scene(r, "ruhe")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            got, drop = dungeon.check_proben(r, rd, {"proben": [{"wer": "Arvid", "wert": "geschick", "stufe": "mittel", "wofuer": "Brot auspacken"}]})
        self.assertEqual((got, drop, rd["_ohne"]), ([], 1, [("p0", "alltag")]))
        self.assertIn("dungeon: probe | verworfen | alltag", out.getvalue())
        self.assertIn("alltag", dungeon.OHNE_PROBE)                      # the seat hears why (tell_no_check)

    def test_the_models_own_view_runs_from_0_to_1(self):
        """Erzähler-Prüfstand 28.10. (Dominik's run showed „185/171“ and „200/4“ per cent): systemone's score runs over
        the LEVELS, 0 to 2; the bench keeps 0 to 1, so the page's per cent never pass 100."""
        async def ask(ccfg, use, state, questions, timeout=0):
            return {"lebendig": {"score": 2.0}, "folgt": {"score": 1.0}}
        with mock.patch("systemone.ask", ask), mock.patch.object(es.features, "admin_on", lambda k, c=None: k == "einordnung"):
            e = asyncio.run(es._einordnung(es.scene(dungeon.rules(), "zwei")[0], "Arvid sucht."))
        self.assertEqual(e, {"lebendig": 1.0, "folgt": 0.5})

    def test_a_rewrite_names_its_first_fault(self):
        """Erzähler-Prüfstand 28.10. (Kinderton 1 point, no reason shown): a scene passed only after a rewrite keeps the
        first try's fault as a fixed word (erst), the page shows it."""
        r, n, base = dungeon.rules(), [0], model(self.foe)

        async def ask(system, user, schema, name, tokens):
            if name == "erzaehlen" and "Wolf" in user:
                n[0] += 1
                if n[0] == 1:
                    return json.dumps({"erzaehlung": "Arvid stürzt sich auf den Wolf, Blut spritzt über den Waldboden und der Wolf heult.", "frage_an": ""})
            return await base(system, user, schema, name, tokens)
        with mock.patch("dungeon.ask_model", ask):
            x = asyncio.run(es.play(r, "kinder"))
        self.assertEqual((x["punkte"], x["erst"]), (1, "abgelehnt"))
        self.assertNotIn("erst", self._play(True)["kinder"])

    def test_the_system_text_in_its_fixed_order(self):
        """Review 27.10. E8/T20 (Dominik 2026-10-27 „ok“): the role, the numbered fixed rules, the task, the examples,
        the round's style last under STIL_KOPF and without a second role; an English round the English style
        (Prüfstand 28.10.: the German one made the narration German); the checks step its own short text without the
        style, its facts without the offer and the spell lists; a fight's sentence for each step; the children's
        words named to a German narrator; the examples quote nobody."""
        import dungeon_kampf as kampf
        r = dungeon.rules()
        self.assertNotIn("Du bist", r["prompt"])
        self.assertNotIn("You are", r["prompt_en"])
        rd, _ = es.scene(r, "englisch")
        t = dungeon.system_text(r, rd, "erzaehlen")
        self.assertTrue(t.startswith("You are the narrator"))
        self.assertLess(t.index("Fixed rules:"), t.index("Task:"))
        self.assertLess(t.index(dungeon.KANN_REGEL["en"]), t.index("Task:"))
        self.assertTrue(t.endswith(dungeon.STIL_KOPF["en"] + "\n" + r["prompt_en"]))
        self.assertNotIn(r["prompt"], t)
        self.assertLessEqual(len(es.DEUTSCH.findall(t)), es.ENGLISCH_MAX)
        p = dungeon.system_text(r, rd, "proben")
        self.assertTrue(p.startswith(dungeon.PROBEN_REGELN["en"]))
        self.assertNotIn(r["prompt_en"], p)
        self.assertNotIn(dungeon.STIL_KOPF["en"], p)
        self.assertIn('"angebot"', dungeon.facts(r, rd))
        self.assertNotIn('"angebot"', dungeon.facts(r, rd, proben=True))
        self.assertNotIn('"kann"', dungeon.facts(r, rd, proben=True))
        self.assertIn('"kann"', dungeon.facts(r, rd))
        k, _ = es.scene(r, "kampf")
        e, c = dungeon.system_text(r, k, "erzaehlen"), dungeon.system_text(r, k, "proben")
        self.assertIn(kampf.AUFGABE_KAMPF["de"], e)
        self.assertNotIn(kampf.AUFGABE_ANGRIFF["de"], e)
        self.assertIn(kampf.AUFGABE_ANGRIFF["de"], c)
        self.assertNotIn(kampf.AUFGABE_KAMPF["de"], c)
        self.assertNotIn(kampf.AUFGABE_ANGRIFF["de"], dungeon.system_text(r, rd, "proben"))    # no fight: no attack sentence
        kid, _ = es.scene(r, "kinder")
        kt = dungeon.system_text(r, kid, "erzaehlen")
        self.assertIn(dungeon.NIE_WORTE.format(w="blut, leiche, ").rstrip(". "), kt)
        self.assertNotIn(dungeon.NIE_WORTE.split(":")[0], dungeon.system_text(r, rd, "erzaehlen"))   # English: not the German stems
        for w in r["welten"]:
            for de_en in w.get("stil") or []:
                self.assertFalse(any(q in x for x in de_en for q in "„“\""), w["id"])

    def test_only_the_admin_and_only_while_on(self):
        self.assertIn(self.c.get(P).status_code, (401, 403))
        self.assertIn(self.c.post(P, json={}).status_code, (401, 403))
        d = ADMIN.get(P).json()
        self.assertEqual((d["an"], d["modelle"], len(d["szenen"])), (False, {}, len(es.SZENEN)))
        self.assertEqual(ADMIN.post(P, json={}).status_code, 409)
        self.assertEqual(live._erzaehlstand(), "")

    def test_the_button_the_models_and_the_live_line(self):
        helpers.set_config(dungeon_erzaehlstand=True)
        self.assertIn("noch ohne Lauf", live._erzaehlstand())

        def spawn():                                                    # the run in its own loop, done when the request answers
            th = threading.Thread(target=lambda: asyncio.run(es._go()))
            th.start()
            th.join()
        with mock.patch("dungeon.ask_model", model(self.foe)), mock.patch("dungeon_erzaehlstand._spawn", spawn):
            with mock.patch("llm.known_model", lambda: ""):
                self.assertTrue(ADMIN.post(P, json={}).json()["laeuft"])
            self.assertEqual(ADMIN.post(P, json={}).status_code, 429)    # at most every KNOPF_S
            self.t[0] += es.KNOPF_S
            with mock.patch("llm.known_model", lambda: "qwen36frei"):
                self.assertEqual(ADMIN.post(P, json={}).status_code, 200)
        d = ADMIN.get(P).json()
        self.assertEqual(set(d["modelle"]), {"unbekannt", "qwen36frei"})
        m = d["modelle"]["qwen36frei"]
        self.assertEqual((m["punkte"], m["max"], set(m["szenen"])), (2 * len(es.SZENEN), 2 * len(es.SZENEN), set(es.SZENEN)))
        self.assertNotIn("Holztür", json.dumps(d, ensure_ascii=False))    # points and reasons, never the narration
        n = 2 * len(es.SZENEN)
        self.assertRegex(live._erzaehlstand(), rf"^ · Erzähler-Prüfstand 2 Modelle, bestes {n} von {n} Punkten$")


if __name__ == "__main__":
    unittest.main()
