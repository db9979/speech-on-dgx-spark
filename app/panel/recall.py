"""What a profile talked about before: search in its saved conversations, and facts learned from
them automatically (profiles only; guests keep their conversations in the browser).

    USERS_DIR/<user id>/convos.json    the conversations (see profiles.save_convo)
    USERS_DIR/<user id>/learned.json   {conversation id: [messages already read, its "updated" then]}

Search: every question with its answer is one piece; pieces are ranked with BM25 (same terms as
the document search). Learning: a background loop reads conversations that have been quiet for a
while and asks the LLM for a few lasting facts about the person, which go into the profile's
memory marked "auto".
"""
import datetime
import json
import math
import re
from collections import Counter

import documents
import profiles

IDLE_SECONDS = 10 * 60          # a conversation this quiet is read for facts
MAX_AUTO_FACTS = 3              # per conversation and pass


def _pieces(uid, skip=None, since=None):
    out = []
    for c in profiles.convos(uid):
        if c.get("id") == skip or (since and c.get("updated", 0) < since):
            continue
        msgs = c.get("msgs", [])
        for i, m in enumerate(msgs):
            if m.get("role") != "user":
                continue
            ans = msgs[i + 1]["content"] if i + 1 < len(msgs) and msgs[i + 1].get("role") == "assistant" else ""
            out.append({"convo": c.get("id"), "title": c.get("title", ""), "updated": c.get("updated", 0),
                        "q": m["content"], "a": ans})
    return out


def _day(ms):
    d = datetime.datetime.fromtimestamp(ms / 1000)
    return f"{d:%d.%m.%Y}"


def search(uid, query, days=None, skip=None, k=4):
    """Text for the LLM: the best-matching question/answer pairs of earlier conversations, or
    (without a query) an overview of the recent conversations."""
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp() * 1000 if days else None
    pieces = _pieces(uid, skip, since)
    if not pieces:
        return "No earlier conversations" + (f" in the last {days} days." if days else ".")
    q = set(documents._terms(query or ""))
    if not q:  # "what did we talk about last week?": one line per conversation
        seen, lines = set(), []
        for p in pieces:
            if p["convo"] in seen:
                continue
            seen.add(p["convo"])
            n = sum(1 for x in pieces if x["convo"] == p["convo"])
            lines.append(f"{_day(p['updated'])} ({n} Fragen): {p['title'] or p['q'][:80]}")
            if len(lines) >= 12:
                break
        return "Earlier conversations, newest first:\n" + "\n".join(lines)
    docs = [(p, Counter(t), len(t)) for p in pieces for t in [documents._terms(p["q"] + " " + p["a"])]]
    n = len(docs)
    avg = sum(x[2] for x in docs) / n or 1
    df = {t: sum(1 for x in docs if t in x[1]) for t in q}
    scored = []
    for p, tf, length in docs:
        s = sum(math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) * tf[t] * 2.2
                / (tf[t] + 1.2 * (0.25 + 0.75 * length / avg)) for t in q if tf.get(t))
        if s > 0:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return "Nothing about this in earlier conversations."
    return "\n\n".join(f"[{_day(p['updated'])}, Gespräch „{p['title'][:60]}“]\nFrage: {p['q'][:600]}\n"
                       f"Antwort: {p['a'][:900]}" for _, p in scored[:k])


# ---------------------------------------------------------------- learning facts
LEARN_PROMPT = (
    "Du liest ein Gespräch zwischen {name} und einem Sprachassistenten. Nenne höchstens {n} dauerhafte, "
    "persönliche Fakten über {name}, die in späteren Gesprächen nützlich sind: Familie und Freunde, Vorlieben "
    "und Abneigungen, Arbeit, Wohnort, Haustiere, wichtige Termine oder Pläne (mit Datum, wenn genannt). "
    "Nicht aufnehmen: allgemeines Wissen, Fragen ohne persönlichen Bezug, einmalige Kleinigkeiten, Dinge, die "
    "schon bekannt sind, und Vermutungen. Jeder Fakt ein kurzer Satz in der dritten Person.\n"
    "Schon bekannt:\n{known}\n\nAntworte nur mit JSON: {{\"facts\": [\"...\"]}} (leer, wenn nichts Neues).")


def learned(uid):
    try:
        with open(profiles._path(uid, "learned.json")) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _seen(uid, cid):
    v = learned(uid).get(cid)
    return v if isinstance(v, list) and len(v) == 2 else [0, 0]


def pending(uid, now_ms):
    """Conversations changed since they were last read and quiet for IDLE_SECONDS."""
    return [c for c in profiles.convos(uid) if c.get("msgs") and c.get("updated", 0) > _seen(uid, c["id"])[1]
            and now_ms - c.get("updated", 0) > IDLE_SECONDS * 1000]


def mark(uid, convo):
    with profiles._lock:
        d = learned(uid)
        d[convo["id"]] = [len(convo.get("msgs", [])), convo.get("updated", 0)]
        ids = {c["id"] for c in profiles.convos(uid)}
        profiles._write(profiles._path(uid, "learned.json"), {k: v for k, v in d.items() if k in ids})


def learn_messages(prof, convo):
    """Chat messages for the LLM that extracts facts from the new part of a conversation."""
    msgs = convo.get("msgs", [])
    start = _seen(prof["id"], convo["id"])[0]
    if start >= len(msgs):  # the stored conversation is capped; its newest messages changed
        start = max(0, len(msgs) - 10)
    part = msgs[max(0, start - 2):]           # a little context before the new part
    # answers made from e-mails are other people's words, not facts about this person
    text = "\n".join(("Nutzer: " if m["role"] == "user" else "Assistent: ")
                     + ("(Antwort aus E-Mails, ausgelassen)" if m.get("mail") else m["content"][:1500]) for m in part)
    known = "\n".join("- " + x["text"] for x in profiles.memory(prof["id"])[-60:]) or "(nichts)"
    return [{"role": "system", "content": LEARN_PROMPT.format(name=prof["name"], n=MAX_AUTO_FACTS, known=known)},
            {"role": "user", "content": text[-8000:]}]


def parse_facts(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        facts = json.loads(m.group(0)).get("facts", []) if m else []
    except (ValueError, AttributeError):
        return []
    return [re.sub(r"\s+", " ", str(x)).strip() for x in facts if isinstance(x, str) and 5 <= len(x.strip()) <= 300][:MAX_AUTO_FACTS]
