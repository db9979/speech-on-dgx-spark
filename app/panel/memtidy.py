"""Weekly memory cleanup per profile: the language model looks at the remembered facts and proposes
which ones to merge (duplicates, the same thing said twice) and which to drop (outdated or
contradicted by a newer fact). Nothing changes until the person accepts the proposal in "Ich" →
Gedächtnis; a proposal is only about that profile's own facts.

    USERS_DIR/<user id>/memory-tidy.json     the open proposal
    USERS_DIR/<user id>/memory-tidy-checked  time of the last check (once a week)
"""
import datetime
import json
import os
import re
import time

import httpx

import profiles
from common import load_config
from core import DEFAULTS

EVERY = 7 * 86400
MIN_FACTS = 6          # fewer facts: nothing worth tidying
MAX_ITEMS = 20         # merges + drops in one proposal

SYSTEM = (
    "Du räumst das Gedächtnis eines Sprachassistenten über eine Person auf. Unten stehen die gemerkten "
    "Fakten, je Zeile: ID, Datum, Text. Finde nur sichere Fälle:\n"
    "- merge: zwei oder mehr Fakten sagen dasselbe oder gehören eng zusammen. Schreibe einen kurzen "
    "Satz, der alles Wichtige daraus enthält und nichts hinzufügt.\n"
    "- drop: ein Fakt ist durch einen neueren widerlegt oder offensichtlich überholt (z. B. ein "
    "vergangener einmaliger Termin). Nenne den Grund kurz.\n"
    "Erfinde nichts, ändere keine Bedeutung, lass im Zweifel alles stehen. Jede ID höchstens einmal. "
    "Antworte nur mit JSON: {\"merge\": [{\"ids\": [\"..\", \"..\"], \"text\": \"..\"}], "
    "\"drop\": [{\"id\": \"..\", \"why\": \"..\"}]}. Nichts zu tun: {\"merge\": [], \"drop\": []}.")


def _file(uid, name):
    return profiles._path(uid, name)


def pending(uid):
    """The open proposal with the facts' texts, or None. A proposal whose facts changed meanwhile
    (deleted, forgotten) is dropped."""
    try:
        with open(_file(uid, "memory-tidy.json")) as f:
            prop = json.load(f)
    except (OSError, ValueError):
        return None
    facts = {x["id"]: x["text"] for x in profiles.memory(uid)}
    ids = [i for m in prop.get("merge", []) for i in m["ids"]] + [d["id"] for d in prop.get("drop", [])]
    if not ids or any(i not in facts for i in ids):
        drop(uid)
        return None
    return {"created": prop.get("created"),
            "merge": [{"ids": m["ids"], "old": [facts[i] for i in m["ids"]], "text": m["text"]} for m in prop["merge"]],
            "drop": [{"id": d["id"], "old": facts[d["id"]], "why": d.get("why", "")} for d in prop["drop"]]}


def drop(uid):
    try:
        os.remove(_file(uid, "memory-tidy.json"))
    except OSError:
        pass


def parse(text, facts):
    """The model's answer checked against the real facts: only known ids, each once, merges of at
    least two facts with a non-empty text. Returns {"merge": [...], "drop": [...]}."""
    text = re.sub(r"(?s)<think>.*?</think>", "", text or "")
    m = re.search(r"(?s)\{.*\}", text)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    known = {x["id"] for x in facts}
    used, merge, drops = set(), [], []
    for item in data.get("merge") or []:
        if not isinstance(item, dict):
            continue
        ids = [str(i) for i in item.get("ids") or [] if str(i) in known]
        ids = list(dict.fromkeys(ids))
        new = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()[:profiles.MAX_FACT_LEN]
        if len(ids) >= 2 and new and not used & set(ids):
            used |= set(ids)
            merge.append({"ids": ids, "text": new})
    for item in data.get("drop") or []:
        if not isinstance(item, dict):
            continue
        i = str(item.get("id") or "")
        if i in known and i not in used:
            used.add(i)
            drops.append({"id": i, "why": re.sub(r"\s+", " ", str(item.get("why") or "")).strip()[:200]})
    return {"merge": merge[:MAX_ITEMS], "drop": drops[:max(0, MAX_ITEMS - len(merge))]}


async def propose(uid):
    """Asks the model for a proposal and keeps it; returns the proposal (None: nothing to do)."""
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    facts = profiles.memory(uid)
    os.makedirs(profiles._path(uid), mode=0o700, exist_ok=True)
    with open(os.open(_file(uid, "memory-tidy-checked"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(str(int(time.time())))   # first, so a failing model does not retry every few minutes
    if len(facts) < 2 or not ccfg.get("llm_url"):
        return None
    from chat import llm_model
    lines = [f"{x['id']} | {datetime.date.fromtimestamp(x.get('created', 0)):%Y-%m-%d} | {x['text']}" for x in facts]
    headers = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=5)) as c:
        payload = {"model": await llm_model(c, ccfg, headers), "temperature": 0.1, "max_tokens": 1500,
                   "messages": [{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": "\n".join(lines)[:24000]}],
                   "chat_template_kwargs": {"enable_thinking": False}}
        r = await c.post(ccfg["llm_url"].rstrip("/") + "/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        prop = parse(r.json()["choices"][0]["message"].get("content") or "", facts)
    if not prop["merge"] and not prop["drop"]:
        drop(uid)
        return None
    prop["created"] = int(time.time())
    profiles._write(_file(uid, "memory-tidy.json"), prop)
    return pending(uid)


def apply(uid):
    """Carries out the open proposal; returns how many facts went (merged ones count as gone)."""
    prop = pending(uid)
    if not prop:
        return 0
    with profiles._lock:
        facts = profiles.memory(uid)
        gone = {d["id"] for d in prop["drop"]}
        for m in prop["merge"]:
            gone |= set(m["ids"])
        keep = [x for x in facts if x["id"] not in gone]
        for m in prop["merge"]:
            item = {"id": os.urandom(4).hex(), "text": m["text"], "created": int(time.time())}
            if all(x.get("auto") for x in facts if x["id"] in m["ids"]):
                item["auto"] = True
            keep.append(item)
        profiles._write(profiles._path(uid, "memory.json"), keep[-profiles.MAX_FACTS:])
    drop(uid)
    return len(facts) - len(keep)


def _checked(uid):
    try:
        return float(open(_file(uid, "memory-tidy-checked")).read().strip())
    except (OSError, ValueError):
        return 0.0


async def due_once():
    """At most one profile per call whose weekly check is due; sends a push note when a proposal is
    ready. Returns the profile id checked, or None."""
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    if not ccfg.get("memory", True):
        return None
    for uid in profiles.user_ids():
        if time.time() - _checked(uid) < EVERY or len(profiles.memory(uid)) < MIN_FACTS:
            continue
        if os.path.exists(_file(uid, "memory-tidy.json")):
            continue   # still waiting for an answer
        prop = await propose(uid)
        if prop:
            import push
            n = len(prop["merge"]) + len(prop["drop"])
            try:
                await push.send(uid, "🧹 Gedächtnis aufräumen",
                                f"{n} Vorschlag{'' if n == 1 else 'e'} zum Aufräumen. Ansehen und bestätigen unter Ich → Gedächtnis.",
                                tag="memtidy")
            except Exception:
                pass
        return uid
    return None
