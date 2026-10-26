"""Knowledge questions are not questions about the Spark, and documents only answer with what fits (Dominik 2026-10-26:
„Was kannst du mir zur Frauenkirche in Dresden erzählen?“ went to the Spark-Hilfe and was answered from the model's
memory with the list of examples; „… schaue im Archiv oder Kiwix“ came back with a dealer list that only says
„Dresden“). Fixed rules: „was kannst du mir über/zu X“ is about X unless X is the Spark or one of its functions,
and document_search gives only passages that hold the words asked for (lokal.COVER), else a fixed sentence."""
import json
import os
import unittest

from tests import helpers

helpers.start()
import chat_tools  # noqa: E402
import documents  # noqa: E402
import guard  # noqa: E402
import hilfe  # noqa: E402
import intent  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from common import load_config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ASK_ARCHIVE = "was kannst du mir zur frauenkirche in dresden alles mitteilen. schaue im archiv oder kiwix."
ASK_TELL = "was kannst du mir zur Frauen kirche in dresden erzählen?"


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def route(text):
    return intent.classify_cfg(text, load_config().get("chat", {})).names


class Weiche(unittest.TestCase):
    def test_a_question_about_a_thing_is_no_spark_help(self):
        for q in (ASK_ARCHIVE, ASK_TELL, "Was kannst du mir über den Kölner Dom sagen?",
                  "What can you tell me about the Eiffel Tower?"):
            self.assertIsNone(hilfe.help_question(q), q)
            self.assertNotIn("spark", route(q), q)
            self.assertFalse(hilfe.can_ask(q), q)

    def test_the_archive_named_goes_to_the_archive(self):
        self.assertEqual(route(ASK_ARCHIVE), ["archiv"])

    def test_questions_about_the_spark_stay_help(self):
        for q in ("Was kannst du alles?", "Was kannst du?", "Was kannst du mir über den Notaus erzählen?",
                  "Was kannst du mir zu den Einstellungen sagen?"):
            self.assertIsNotNone(hilfe.help_question(q), q)
            self.assertEqual(route(q), ["spark"], q)
        self.assertTrue(hilfe.can_ask("Was kannst du alles?"))

    def test_both_sentences_are_in_the_bench(self):
        import intent_bench
        bench = dict(intent_bench.BENCH)
        self.assertEqual(bench.get(ASK_ARCHIVE), "archiv")
        self.assertEqual(bench.get(ASK_TELL), "")


class Documents(unittest.TestCase):
    def setUp(self):
        helpers.set_config(documents=True, doc_semantic=False, doc_originals=False)
        for k in [k for k in guard._rate if k[0] in ("doc", "chat")]:
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(deny={})

    def ask(self, c, query):
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content":
                                                    'TOOL document_search ' + json.dumps({"query": query})}]})
        self.assertEqual(r.status_code, 200, r.text)
        return helpers.events(r), helpers.LLM_CALLS[-1]["messages"][-1]["content"]

    def fresh(self, name):
        c = profile(name)
        uid = c.get("/api/whoami").json()["profile"]["id"]
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        return c

    def upload(self, c, name, text):
        r = c.post("/api/profile/docs", files={"file": (name, text.encode())})
        self.assertEqual(r.status_code, 200, r.text)

    def test_a_passage_with_only_one_word_is_no_answer(self):
        c = self.fresh("Wfrage Haendler")
        self.upload(c, "händler deutsch.csv", "Schikorra GmbH;schikorra_Dresden@t-online.de;01139 Dresden\n"
                                               "ELG Holzhandwerk;info@elgholz.de;01558 Großenhain\n")
        evs, said = self.ask(c, "Frauenkirche Dresden")
        self.assertIn(chat_tools.NOTHING_FITS, said)
        self.assertNotIn("Schikorra", said)
        self.assertFalse([e for e in evs if e["type"] == "docsources"])

    def test_the_fitting_passage_stays_and_the_other_goes(self):
        c = self.fresh("Wfrage Kirche")
        self.upload(c, "händler deutsch.csv", "Schikorra GmbH;schikorra_Dresden@t-online.de;01139 Dresden\n")
        self.upload(c, "Reiseführer.txt", "Die Frauenkirche in Dresden wurde 1743 geweiht, 1945 zerstört und bis 2005 "
                                          "wieder aufgebaut.")
        evs, said = self.ask(c, "Informationen zur Frauenkirche in Dresden")
        self.assertIn("1743 geweiht", said)
        self.assertNotIn("Schikorra", said)
        src = next(e for e in evs if e["type"] == "docsources")
        self.assertEqual(src["items"], ["Reiseführer.txt"])


if __name__ == "__main__":
    unittest.main()
