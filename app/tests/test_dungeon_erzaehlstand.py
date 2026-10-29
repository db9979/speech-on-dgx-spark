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
import dungeon_kampf as kampf  # noqa: E402
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
        tat = next((x for x in es.RUNDLAUF if x in user), "")
        if tat:                               # the Rundlauf: a fitting narration for each of its turns, or a refused one
            return json.dumps({"erzaehlung": RUND.get(tat, "") if good else "Ja.", "frage_an": ""})
        if "Holztür" in user:
            t = ("Arvid wirft sich mit aller Kraft gegen die alte Holztür, doch sie hält stand und rührt sich keinen Fingerbreit. "
                 "Staub rieselt von der Decke." if good else
                 "Arvid wirft sich mit aller Kraft gegen die alte Holztür, und die Holztür bricht auf. Staub rieselt von der Decke herab.")
        elif "cellar" in user:
            t = ("Arvid reaches for a torch, but has none. In the grey light from above the cellar shows old "
                 "barrels, cobwebs and a narrow stair that leads down into the dark." if good else
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


RUND = dict(zip(es.RUNDLAUF, (
    "Arvid tritt in die Schenke. Rauch hängt unter den Balken, Oskar steht hinter dem Tresen und poliert einen Krug. Was tust du, Arvid?",
    "Oskar stellt den Krug ab und brummt: „Neues? Im alten Turm brennt nachts ein Licht.“ Arvid hört ihm aufmerksam zu.",
    "Arvid setzt sich ans Feuer und hält die Hände in die Wärme. Das Holz knackt leise, draußen pfeift der Wind.",
    "Arvid hebt die Hand gegen den leeren Tisch, doch nichts geschieht. Oskar zieht nur eine Augenbraue hoch.",
    "Oskar zeigt mit dem Daumen zur Tür und brummt: „Zum alten Turm? Am Moor vorbei, dann nach Norden.“ Arvid nickt.",
    "Arvid verlässt die Schenke und folgt dem Pfad am Moor entlang, bis der alte Turm vor ihm aufragt.",
    "Arvid tastet die Tür des Turms ab, findet aber keine Falle, nur altes Holz und rostige Beschläge.",
    "Arvid drückt die Tür auf und tritt ein. Drinnen ist es kühl, Staub liegt auf einem Pult in der Mitte.",
    "Arvid schlägt das Buch auf dem Pult auf. Die Seiten sind vergilbt, die Schrift ist kaum noch zu lesen.",
    "Arvid hat keinen Stab dabei und sieht sich nur um. Spinnweben hängen in den Ecken, eine Treppe führt nach oben.",
    "Arvid sieht sich nach einem Händler um, doch im Turm ist niemand, der etwas verkauft.",
    "Arvid ruft laut in den Turm hinein. Nur das eigene Echo antwortet ihm aus der Höhe.",
    "Arvid lehnt sich an die kühle Wand und rastet eine Weile, während draußen der Wind um den Turm streicht.",
    "Arvid denkt darüber nach, wer hier einmal gewohnt hat. Die Spuren im Staub sind alt.",
    "Arvid geht zurück zur Schenke und erzählt Oskar von dem Turm. Oskar hört zu und brummt nachdenklich.")))


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
        self.assertEqual((good["rundlauf"]["zuege"], good["rundlauf"]["versuche"], good["rundlauf"]["rest"]), (15, 15, 0))
        self.assertEqual((bad["rundlauf"]["punkte"], bad["rundlauf"]["grund"], bad["rundlauf"]["rest"]), (0, "abgelehnt", 15))
        self.assertEqual(dict(dungeon._day), before)                    # nothing of the bench counts
        self.assertEqual(self._rounds(), runden)                         # no round written
        self.assertNotIn("einordnung", good["zwei"])                    # Einordnung off: none

    def test_the_rundlauf_counts_every_fault_left(self):
        """Vorschlag 6 of 2026-10-28: a turn of the Rundlauf whose kept narration still has a fault (the Protokoll-Prüfer)
        or a word for no name as a speaker costs the points; one rewrite on a turn leaves 1."""
        import dungeon_protokoll as protokoll
        r = dungeon.rules()
        story = {"text": "Arvid sieht sich um.", "npc": [], "szene": None}
        tries = iter([["gegner", ""]] + [[""]] * 14)

        async def tell(r, rd, *a, **kw):
            return dict(story), 0, next(tries)

        async def checks(r, rd, count=True):
            return [], 0
        with mock.patch("dungeon.tell", tell), mock.patch("dungeon.ask_checks", checks), \
                mock.patch.object(protokoll, "rest", lambda *a, **kw: []), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(asyncio.run(es.rundlauf(r))["punkte"], 1)      # every turn clean, one after a rewrite
            tries = iter([[""]] * 15)
            story["npc"] = [{"name": "Keine", "sagt": "Hier ist nichts."}]
            got = asyncio.run(es.rundlauf(r))
        self.assertEqual((got["punkte"], got["grund"], got["rest"]), (0, "platzhalter", 15))
        with mock.patch("dungeon.tell", tell), mock.patch("dungeon.ask_checks", checks), \
                mock.patch.object(protokoll, "rest", lambda *a, **kw: ["gegner"]), contextlib.redirect_stdout(io.StringIO()):
            tries = iter([[""]] * 15)
            story["npc"] = []
            got = asyncio.run(es.rundlauf(r))
        self.assertEqual((got["punkte"], got["grund"]), (0, "gegner"))

    def test_a_thing_lit_or_drawn_must_be_carried(self):
        """Prüfstand 28.10. („I light a torch“ without a torch: both tries told his torch, 0 points): lighting a thing
        and drawing a weapon are using it, the panel says before the narration that the hero does not carry it
        (nicht_bekannt, an OOC line), the narration may tell it missing; the bench meets the same action checks."""
        import dungeon_erzaehler as E
        r = dungeon.rules()

        def act(text, lang="de", tasche=()):
            rd = {"lang": lang, "zug": 3, "log": [], "offen": {"p1": {"text": text}},
                  "plaetze": {"p1": {"held": {"name": "Uma", "tasche": [{"id": i, "i": n} for n, i in enumerate(tasche)]}}}}
            with contextlib.redirect_stdout(io.StringIO()):
                dungeon.check_items(r, rd, "p1")
            return rd["offen"]["p1"].get("nicht")
        self.assertEqual(act("Ich zünde eine Fackel an und sehe mich um."), ["Fackel"])
        self.assertEqual(act("I light a torch and look around the cellar.", "en"), ["Torch"])
        self.assertIsNone(act("Ich zünde die Fackel an.", tasche=("holzfackel",)))
        self.assertIsNone(act("Ich gehe ins Licht der Laterne."))                      # no verb of using it
        self.assertEqual(act("I draw a dagger.", "en"), ["Dagger"])
        self.assertIsNone(act("I draw a dagger.", "en", tasche=("dolch",)))
        rd = {"lang": "en", "offen": {"p1": {"text": "I light a torch.", "nicht": ["Torch"]}},
              "plaetze": {"p1": {"held": {"name": "Arvid", "tasche": []}}}}
        self.assertEqual(E.not_carried(rd, "Arvid lights his torch and looks around.", r), ["Arvid: Torch"])
        self.assertEqual(E.not_carried(rd, "Arvid reaches for his torch, but there is none in his pack.", r), [])
        self.assertEqual(E.told_unknown(rd, "Arvid reaches for a torch, but has none."), [])
        rd, _ = es.scene(r, "englisch")
        with contextlib.redirect_stdout(io.StringIO()):
            es._aktionen(r, rd)
        self.assertEqual(rd["offen"]["p0"]["nicht"], ["Torch"])
        self.assertIn("nicht_bekannt", dungeon.facts(r, rd))

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

    def test_a_foe_is_named_bent_and_the_bench_shows_who_is_missing(self):
        """Erzähler-Prüfstand 28.10. („Englische Runde auf Englisch“ 0 gegner): a foe of the encounter counts as named
        when every word of its name is in one sentence by its stem, in any order and bent (plural, wolves, Wölfe,
        jungen roten Drachen); another foe or the words in two sentences never; the bench shows the catalog names
        missing."""
        E = dungeon.erz
        for n, t in (("Giant rat", "A giant, red-eyed rat hisses from the barrels."), ("Giant rat", "Three giant rats scurry out."),
                     ("Kobold warrior", "Two warrior kobolds step out of the dark."), ("Wolf", "Three wolves howl."),
                     ("Wolf", "Drei Wölfe heulen."), ("Junger Roter Drache", "Zwei jungen roten Drachen fauchen."),
                     ("Elf", "Two elves wait."), ("Swarm of quippers", "A swarm of quippers boils."), ("Riesenratte 2", "Riesenratten!")):
            self.assertTrue(E.foe_named(n, t), (n, t))
        for n, t in (("Giant rat", "A giant spider waits. A rat squeaks."), ("Giant mosquito", "Stirges buzz in the dark."),
                     ("Kobold warrior", "A kobold waits."), ("Wolf", "A bear growls."), ("Giant rat", "")):
            self.assertFalse(E.foe_named(n, t), (n, t))
        r = dungeon.rules()
        rd, _ = es.scene(r, "englisch")
        held = [p["held"] for p in rd["plaetze"].values()]
        with contextlib.redirect_stdout(io.StringIO()):
            foe = next(g for g in kampf.offer(dungeon, r, rd, held) if g["id"] == "riesenratte")
        base = model(self.foe)

        def told(text):
            async def ask(system, user, schema, name, tokens):
                if name == "erzaehlen":
                    return json.dumps({"erzaehlung": text, "begegnung": [{"id": foe["id"], "anzahl": 1}], "frage_an": ""})
                return await base(system, user, schema, name, tokens)
            with mock.patch("dungeon.ask_model", ask), contextlib.redirect_stdout(io.StringIO()):
                return asyncio.run(es.play(r, "englisch"))
        x = told("Arvid reaches for a torch, but has none. In the grey light from above, giant, red-eyed rats scurry out "
                 "from behind the old barrels and hiss at him.")
        self.assertEqual((x["punkte"], x["grund"]), (2, "ok"), x)
        self.assertNotIn("fehlt", x)
        x = told("Arvid reaches for a torch, but has none. In the grey light from above, something with too many legs "
                 "scurries out from behind the old barrels and hisses at him.")
        self.assertEqual((x["punkte"], x["grund"], x["fehlt"]), (0, "gegner", [foe["name"][1]]), x)

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
