"""Text schreiben on Ich → Musik (musik.write_lyrics, Dominik 2026-10-20 „musik ohne text sollte auch text generiert
werden können aufgrund vom prompt“): the language model writes the lyrics from the description, nothing is made yet;
artist names never reach the music model (the clause leaves the wish, style words take its place, a fixed rule checks
that no name is left, also after a typo like „im stiel“); the word list and the secrets rule hold; guests and blocked
profiles get nothing; the journal never names the wish or the lyrics. The language model is faked; nothing depends on
the time."""
import asyncio
import contextlib
import io
import json
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import musik  # noqa: E402
from tests.test_musik import block, client, music, profile  # noqa: E402

DOMINIK = "Big Band Song über einen Systemadministrator, der nie Urlaub hat, im stiel fran sinatra, micael bubele"
LYRICS = "[verse]\nDer Server summt die ganze Nacht\n[chorus]\nRoot, root, root, er hat die Macht"


def model(answer):
    """A stand-in for llm.complete: the given answer (a dict as JSON), the asked prompts kept."""
    asked = []

    async def complete(system, user, job, max_tokens, **kw):
        asked.append((system, user, job))
        return answer if isinstance(answer, str) else "Gern: " + json.dumps(answer)
    return complete, asked


def write(prof, wish, answer, seconds=120, lang="de"):
    fake, asked = model(answer)
    out = io.StringIO()
    with mock.patch("llm.complete", fake), contextlib.redirect_stdout(out):
        try:
            res = asyncio.run(musik.write_lyrics(prof, wish, seconds, lang))
        except ValueError as e:
            res = e
    return res, asked, out.getvalue()


class On(unittest.TestCase):
    def setUp(self):
        helpers.set_config(musik=True)
        music(enabled=True)
        self.c, self.prof = profile("Texterin")

    def tearDown(self):
        helpers.set_config(musik=False)
        music(enabled=False)


class Rules(On):
    def test_typo_is_an_artist_clause_too(self):
        self.assertEqual(musik.refuse_text("x", DOMINIK), "kuenstler")
        self.assertEqual(musik.refuse_text("x", "Swing im Stil von Frank Sinatra"), "kuenstler")
        self.assertEqual(musik.refuse_text("x", "Big Band, Swing, Crooner-Gesang"), "")

    def test_length_gives_the_parts(self):
        self.assertEqual([musik.text_pairs(s) for s in (10, 30, 90, 180, 600)], [1, 1, 2, 4, 4])

    def test_names_become_style_words(self):
        res, asked, log = write(self.prof, DOMINIK, {"liedtext": LYRICS, "stil": "big band, swing, crooner vocals",
                                                     "namen": ["Frank Sinatra", "Michael Bublé"]})
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res["liedtext"], LYRICS)
        self.assertTrue(res["namen"])
        self.assertNotIn("sinatra", res["wunsch"].lower())
        self.assertNotIn("bubele", res["wunsch"].lower())
        self.assertNotIn("stiel", res["wunsch"].lower())
        self.assertIn("Systemadministrator", res["wunsch"])
        self.assertTrue(res["wunsch"].endswith("Stil: big band, swing, crooner vocals"))
        self.assertEqual(musik.refuse_text("x", res["wunsch"], res["liedtext"]), "")
        # the wish goes as data, in its block; the language and the parts from the panel
        system, user, _job = asked[0]
        self.assertTrue(user.startswith("<<<WUNSCH\n") and user.endswith("\nWUNSCH>>>"))
        self.assertIn("German", system)
        self.assertIn("3 verse", system)
        self.assertEqual(res["teile"], 2)
        self.assertIn("liedtext geschrieben 2 teile stil statt namen", log)

    def test_a_name_left_in_the_lyrics_is_refused(self):
        # the model forgot to list the names: the clause's own names still count (fixed rule, not the model)
        res, _a, log = write(self.prof, DOMINIK, {"liedtext": LYRICS + "\nwie fran sinatra singt", "stil": "swing",
                                                  "namen": []})
        self.assertIsInstance(res, ValueError)
        self.assertEqual(res.args[0], musik.REFUSED["kuenstler"])
        self.assertIn("liedtext nicht geschrieben kuenstler", log)
        res, _a, _l = write(self.prof, "Ein Lied über den Sommer", {"liedtext": LYRICS + "\nim Stil von Elvis",
                                                                     "stil": "", "namen": []})
        self.assertIsInstance(res, ValueError)

    def test_style_words_with_a_clause_are_dropped(self):
        res, _a, _l = write(self.prof, DOMINIK, {"liedtext": LYRICS, "stil": "sounds like Frank Sinatra",
                                                 "namen": ["Frank Sinatra"]})
        self.assertIsInstance(res, dict, res)
        self.assertNotIn("Stil:", res["wunsch"])
        self.assertNotIn("sinatra", res["wunsch"].lower())

    def test_without_names_the_wish_stays(self):
        res, _a, _l = write(self.prof, "Ein fröhliches Lied über Regen", {"liedtext": LYRICS, "stil": "pop", "namen": []},
                            seconds=30, lang="en")
        self.assertEqual(res["wunsch"], "Ein fröhliches Lied über Regen")
        self.assertFalse(res["namen"])

    def test_word_list_and_secrets_before_the_model(self):
        for wish in ("Ein Lied über Nazis", "Lied mit meinem Passwort: geheim123"):
            res, asked, _l = write(self.prof, wish, {"liedtext": LYRICS})
            self.assertIsInstance(res, ValueError)
            self.assertEqual(asked, [])
        res, _a, _l = write(self.prof, "Ein Lied über den Sommer", {"liedtext": "[verse]\nsex sex", "stil": ""})
        self.assertEqual(res.args[0], musik.REFUSED["wortliste"])

    def test_broken_answers_and_empty_wish(self):
        for answer in ("kein json", {"liedtext": "nur Text ohne Teile"}, ["x"]):
            res, _a, log = write(self.prof, "Ein Lied über den Sommer", answer if answer != ["x"] else "[1, 2]")
            self.assertIsInstance(res, ValueError)
            self.assertIn("liedtext nicht geschrieben sprachmodell", log)
        res, asked, log = write(self.prof, "   ", {"liedtext": LYRICS})
        self.assertIsInstance(res, ValueError)
        self.assertEqual(asked, [])
        self.assertIn("liedtext nicht geschrieben leer", log)

    def test_a_long_text_as_template_gives_a_short_music_description(self):
        # Dominik 2026-10-22: a firm's text (about a page) as the template; the music model reads only MAX_CAPTION
        firm = ("Die Muster GmbH baut seit 1950 Fahrräder in Handarbeit. " * 40)[:musik.MAX_WISH]
        self.assertGreater(musik.MAX_WISH, 1500)
        self.assertLessEqual(musik.MAX_WISH, 4000)
        res, asked, _l = write(self.prof, firm, {"liedtext": LYRICS, "stil": "", "namen": [],
                                                 "musik": "upbeat folk pop, acoustic guitar, warm male voice"})
        self.assertIsInstance(res, dict, res)
        self.assertEqual(len(asked[0][1]), len(firm) + len("<<<WUNSCH\n\nWUNSCH>>>"))
        self.assertEqual(res["wunsch"], firm)
        self.assertEqual(res["beschreibung"], "upbeat folk pop, acoustic guitar, warm male voice")
        res, _a, _l = write(self.prof, firm + "x" * 500, {"liedtext": LYRICS, "musik": "x" * 900})
        self.assertEqual(len(res["wunsch"]), musik.MAX_WISH)
        self.assertEqual(len(res["beschreibung"]), musik.MAX_CAPTION)

    def test_a_music_description_with_a_clause_is_dropped(self):
        res, _a, _l = write(self.prof, "Ein Lied über den Sommer", {"liedtext": LYRICS, "musik": "swing that sounds like Frank Sinatra"})
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res["beschreibung"], "")

    def test_journal_never_names_wish_or_lyrics(self):
        _r, _a, log = write(self.prof, DOMINIK, {"liedtext": LYRICS, "stil": "swing", "namen": ["Frank Sinatra"]})
        for word in ("Systemadministrator", "Server", "sinatra", "Texterin"):
            self.assertNotIn(word, log)
        self.assertTrue(all(x.startswith(("musik: ", "ereignis: Musik | ")) for x in log.splitlines()), log)


class Chat(On):
    """Anfrage 18adb7 (2026-10-20): musik_machen came back refused twice in a few ms and no song came."""
    def go(self, args):
        async def run():
            return await musik.tool("musik_machen", args, {"who": self.prof, "client": "iphone"})
        with contextlib.redirect_stdout(io.StringIO()):
            return asyncio.run(run())

    def tearDown(self):
        musik._jobs.clear()
        musik._recent.clear()
        super().tearDown()

    def test_a_named_artist_gets_a_clear_way_and_the_wish_loses_its_clause(self):
        musik.clear(self.prof["id"])
        text = self.go({"beschreibung_en": "big band song in the style of Frank Sinatra", "wunsch": DOMINIK})
        self.assertEqual(text, musik.ARTIST_AGAIN)
        self.assertEqual(musik._jobs, {})
        text = self.go({"beschreibung_en": "big band swing, brass section, smooth crooner vocals", "wunsch": DOMINIK})
        self.assertTrue(text.startswith("Started:"), text)
        j = next(iter(musik._jobs.values()))
        self.assertNotIn("sinatra", j["wish"].lower())
        self.assertNotIn("stiel", j["wish"].lower())
        self.assertIn("Systemadministrator", j["wish"])

    def test_everyday_words_in_the_lyrics_are_no_artist(self):
        self.assertEqual(musik.refuse_text("x", "calm pop", lyrics="[verse]\nso wie du lachst, wie von selbst"), "")
        self.assertEqual(musik.refuse_text("x", "ein Lied so wie ein Wiegenlied"), "")
        self.assertEqual(musik.refuse_text("x", "calm pop", lyrics="[verse]\nmein Passwort: abc123"), "geheim")
        self.assertEqual(musik.refuse_text("x", "calm pop", lyrics="[verse]\nnackt"), "wortliste")


class Access(On):
    def test_endpoint(self):
        fake, _asked = model({"liedtext": LYRICS, "stil": "", "namen": []})
        with mock.patch("llm.complete", fake), contextlib.redirect_stdout(io.StringIO()):
            r = self.c.post("/api/musik/liedtext", json={"wunsch": "Ein Lied über den Sommer", "sekunden": 60,
                                                         "sprache": "de"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["liedtext"], LYRICS)
            self.assertIn(client().post("/api/musik/liedtext", json={"wunsch": "x"}).status_code, (401, 403))
            self.assertEqual(self.c.post("/api/musik/liedtext", content=b"x" * (17 * 1024)).status_code, 413)
            block(self.prof["id"])
            try:
                self.assertEqual(self.c.post("/api/musik/liedtext", json={"wunsch": "Sommer"}).status_code, 403)
                with self.assertRaises(ValueError):
                    asyncio.run(musik.write_lyrics(self.prof, "Sommer"))
            finally:
                block(self.prof["id"], False)

    def test_make_takes_the_long_text_and_the_short_description(self):
        firm = ("Die Muster GmbH baut seit 1950 Fahrräder in Handarbeit. " * 40)[:musik.MAX_WISH]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = self.c.post("/api/musik", json={"wunsch": firm, "sekunden": 60, "gesang": True, "sprache": "de",
                                                    "liedtext": LYRICS, "beschreibung": "folk pop, acoustic guitar"})
                self.assertEqual(r.status_code, 200, r.text)
                j = next(iter(musik._jobs.values()))
                self.assertEqual(j["wish"], firm)
                self.assertEqual(j["caption"], "folk pop, acoustic guitar")
                musik._jobs.clear()
                musik._recent.clear()
                # without a description the first MAX_CAPTION characters of the own words go to the music model
                r = self.c.post("/api/musik", json={"wunsch": firm, "sekunden": 60})
                self.assertEqual(r.status_code, 200, r.text)
                j = next(iter(musik._jobs.values()))
                self.assertEqual(j["caption"], firm[:musik.MAX_CAPTION].strip())
                musik._jobs.clear()
                musik._recent.clear()
                # the description is checked like the wish: an artist clause is refused, nothing starts
                r = self.c.post("/api/musik", json={"wunsch": "Sommer", "sekunden": 60, "gesang": True, "liedtext": LYRICS,
                                                    "beschreibung": "swing in the style of Frank Sinatra"})
                self.assertEqual(r.status_code, 409)
                self.assertEqual(musik._jobs, {})
        finally:
            musik._jobs.clear()
            musik._recent.clear()
            musik.clear(self.prof["id"])

    def test_off_without_music(self):
        helpers.set_config(musik=False)
        res, asked, log = write(self.prof, "Sommer", {"liedtext": LYRICS})
        self.assertIsInstance(res, ValueError)
        self.assertEqual(asked, [])
        self.assertIn("liedtext nicht geschrieben aus", log)


if __name__ == "__main__":
    unittest.main()
