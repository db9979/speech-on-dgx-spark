"""Einordnung mit Wahrscheinlichkeit, the shared rules of a question (System One): the panel's systemone.py builds
questions with them, and the LLM-Tor (llm_tor.py) checks every question it gets with the same rules before it asks the
model. One place for the limits (Richtlinie Teil 17)."""
import re

MAX_STATE = 4000              # characters of the text being judged
MAX_QUESTIONS = 8
MAX_OPTIONS = 40
NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
TYPES = ("choice", "score", "noul")


def clean_state(text):
    """The text being judged: control characters out, at most MAX_STATE characters."""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(text or ""))
    return t[:MAX_STATE]


def check_questions(questions):
    """Raises ValueError (a fixed word) unless questions is {name: {type, instructions, criteria}} within the limits:
    names as NAME, a choice with 2 to MAX_OPTIONS named options, a score with 2 to 10 levels, a yes/no without."""
    if not isinstance(questions, dict) or not 0 < len(questions) <= MAX_QUESTIONS:
        raise ValueError("questions")
    for name, q in questions.items():
        if not NAME.fullmatch(str(name)) or not isinstance(q, dict) or q.get("type") not in TYPES:
            raise ValueError("question " + str(name)[:32])
        if not isinstance(q.get("instructions", ""), str) or len(q.get("instructions", "")) > 2000:
            raise ValueError("instructions " + name)
        crit = q.get("criteria")
        if q["type"] == "choice" and not (isinstance(crit, dict) and 1 < len(crit) <= MAX_OPTIONS
                                           and all(NAME.fullmatch(k) for k in crit)
                                           and all(isinstance(v, str) and len(v) <= 500 for v in crit.values())):
            raise ValueError("choice " + name)
        if q["type"] == "score" and not (isinstance(crit, list) and 1 < len(crit) <= 10
                                          and all(isinstance(v, str) and len(v) <= 500 for v in crit)):
            raise ValueError("score " + name)
    return questions
