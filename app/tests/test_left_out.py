"""An answer made from outside text that is not sent again (V01.0.222). Until V01.0.221 it was replaced
by a German note in the assistant's own turn, and the model copied that note as its answer ("Diese
frühere Antwort beruhte auf Texten von außen ...", Dominik 2026-10-09 with his CV). Now such an answer
leaves the conversation together with its question, the model is told so in the system prompt, and
the note is never shown or spoken, even when the model writes it.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

OLD_NOTE = ("(Diese frühere Antwort beruhte auf Texten von außen, z. B. Web, E-Mail oder Kalender, und wird nicht "
            "erneut mitgegeben. Wenn sie gebraucht wird, das Werkzeug noch einmal benutzen.)")


def ask(messages):
    r = TestClient(panel.app).post("/api/chat", json={"messages": messages})
    assert r.status_code == 200, r.text
    return helpers.events(r)


def streamed():
    return [c for c in helpers.LLM_CALLS if c.get("stream")]


def said(evs):
    return "".join(e.get("delta", "") for e in evs if e.get("type") == "text")


def system_of(call):
    return next((m["content"] for m in call["messages"] if m["role"] == "system"), "")


class LeftOut(unittest.TestCase):
    def setUp(self):
        helpers.set_config(public=True)
        helpers.LLM_CALLS.clear()

    def tearDown(self):
        helpers.set_config(public=False)

    def test_older_outside_answer_leaves_with_its_question(self):
        ask([{"role": "user", "content": "Was steht in meinem Lebenslauf?"},
             {"role": "assistant", "content": "Du hast Code 4711 gelernt.", "outside": True},
             {"role": "user", "content": "Wie heißt du?"},
             {"role": "assistant", "content": "Ich bin Spark."},
             {"role": "user", "content": "Und das Wetter?"},
             {"role": "assistant", "content": "Sonnig.", "outside": True},
             {"role": "user", "content": "Fass mich kurz zusammen."}])
        msgs = streamed()[0]["messages"]
        sent = json.dumps(msgs, ensure_ascii=False)
        self.assertNotIn("4711", sent)
        self.assertNotIn("Lebenslauf", sent)
        self.assertNotIn(chat.DROPPED_HEAD, sent)
        self.assertIn("Sonnig.", sent)                  # the latest one still goes along (and locks)
        self.assertIn(chat.LEFT_OUT_NOTE, system_of(streamed()[0]))
        roles = [m["role"] for m in msgs if m["role"] != "system"]
        self.assertTrue(all(a != b for a, b in zip(roles, roles[1:])), roles)   # still taking turns
        self.assertEqual(roles[-1], "user")

    def test_old_copies_of_the_note_are_left_out(self):
        """Browsers and apps still keep answers that are just the old note (without a mark)."""
        ask([{"role": "user", "content": "Kannst du meine Dokumente lesen?"},
             {"role": "assistant", "content": OLD_NOTE},
             {"role": "user", "content": "Fass mich kurz zusammen."}])
        msgs = streamed()[0]["messages"]
        self.assertNotIn(chat.DROPPED_HEAD, json.dumps(msgs, ensure_ascii=False))
        self.assertEqual([m["role"] for m in msgs if m["role"] != "system"], ["user"])

    def test_nothing_left_out_no_note(self):
        ask([{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Hallo!"},
             {"role": "user", "content": "Wie geht's?"}])
        self.assertNotIn(chat.LEFT_OUT_NOTE, system_of(streamed()[0]))

    def test_note_written_by_the_model_is_never_shown(self):
        for note in (OLD_NOTE, OLD_NOTE[1:]):
            helpers.LLM_CALLS.clear()
            evs = ask([{"role": "user", "content": "SAY |x| " + note}])
            self.assertNotIn("frühere Antwort", said(evs))

    def test_answers_that_only_start_alike_are_kept(self):
        for text in ("(Kurz gesagt) Ja.", "Diese Frage ist gut.", "(", "Diese"):
            helpers.LLM_CALLS.clear()
            evs = ask([{"role": "user", "content": "SAY |x| " + text}])
            self.assertEqual(said(evs).strip(), text)

    def test_left_out_unit(self):
        msgs = [{"role": "assistant", "content": "Notiz", "mark": "outside"},
                {"role": "user", "content": "a"}, {"role": "assistant", "content": "b", "mark": "outside"},
                {"role": "user", "content": "c"}]
        self.assertEqual(chat.left_out(msgs), ([{"role": "user", "content": "c"}], 2))
        self.assertEqual(chat.left_out(msgs, 2), ([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                                                   {"role": "user", "content": "c"}], 1))


if __name__ == "__main__":
    unittest.main()
