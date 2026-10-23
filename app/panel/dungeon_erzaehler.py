"""Better stories for the KI-Dungeon-Master (plan dungeon-master/plan.md „Bessere Geschichten – Bauplan“, Dominik
2026-10-23 „1-6“): the chapter's fixed truth (people, groups, secrets), the running summary and the open threads, the
world's style examples, fixed checks with one rewrite, the model's sampling, and 👍/👎 per narration.

Everything here is data for the model or numbers for the admin: what the model writes back is checked by fixed rules
(lengths, the tone's words, the taboos, no hero's name as a person) before the panel keeps it, and it never decides a
value. dungeon.py owns the rounds; this module only reads and changes the fields named below:

    rd["wahrheit"]   {"personen": [{name, rolle, ziel, sprache}], "gruppen": [{name, will}], "geheimnisse": [str]}
    rd["kurz"], rd["kurz_zug"]   the running summary of the chapter and the turn it was written at
    rd["faeden"]     [str]   open threads (promises, quests, questions), oldest first
    rd["daumen"]     {zug: {pid: 1|-1}}   the seats' thumbs per narration
    d["daumen_welt"] {"welt|ton": [hoch, runter]}   the thumbs over all rounds (the admin's numbers)
"""
import asyncio
import re

PERSONEN = (3, 6)          # people the model sets at the start of a chapter
PERSONEN_MAX = 12          # people kept (the model's new NPCs join until then)
GRUPPEN_MAX = 3
GEHEIM_MAX = 3
NAME_LEN = 30
TEIL_LEN = 80              # a role, a goal, a way of speaking, a group's will
GEHEIM_LEN = 120
FAEDEN_MAX = 8
FADEN_LEN = 80
FAEDEN_NEU = 2             # threads one narration may open
FAEDEN_ZU = 3              # and close
KURZ_ALLE = 5              # turns between two summaries
KURZ_MAX = 900
KURZ_MIN = 60
KURZ_QUELLE = 12           # narrations the summary is written from
STIL_MAX = 3               # style examples per world
STIL_LEN = 400
WIEDERHOLT = 0.35          # share of word triples already in the last narrations that counts as repeating
WIEDER_ZURUECK = 3         # narrations a new one is compared with
ZU_KURZ = 80               # a narration under this many characters is too short

# the model's sampling per job (llm.complete puts the extra keys into the request): a narration a little freer
# and less repetitive, the checks sober
SAMPLING = {"erzaehlen": {"temperature": 0.85, "top_p": 0.95, "presence_penalty": 0.4, "frequency_penalty": 0.3},
            "prolog": {"temperature": 0.85, "top_p": 0.95, "presence_penalty": 0.4, "frequency_penalty": 0.3},
            "proben": {"temperature": 0.3}, "wahrheit": {"temperature": 0.9, "top_p": 0.95},
            "kurz": {"temperature": 0.3}}
SAMPLING_SONST = {"temperature": 0.8}


def sampling(name):
    return dict(SAMPLING.get(name, SAMPLING_SONST))


# ---------------------------------------------------------------- the chapter's fixed truth
def _strs(n, k):
    return {"type": "string", "maxLength": n + 40} if k is None else {"type": "array", "maxItems": k, "items": {"type": "string", "maxLength": n + 40}}


SCHEMA_WAHRHEIT = {"type": "object", "additionalProperties": False, "required": ["personen"], "properties": {
    "personen": {"type": "array", "maxItems": PERSONEN[1], "items": {"type": "object", "additionalProperties": False,
                 "required": ["name", "rolle"], "properties": {"name": _strs(NAME_LEN, None), "rolle": _strs(TEIL_LEN, None),
                                                               "ziel": _strs(TEIL_LEN, None), "sprache": _strs(TEIL_LEN, None)}}},
    "gruppen": {"type": "array", "maxItems": GRUPPEN_MAX, "items": {"type": "object", "additionalProperties": False,
                "required": ["name"], "properties": {"name": _strs(NAME_LEN, None), "will": _strs(TEIL_LEN, None)}}},
    "geheimnisse": _strs(GEHEIM_LEN, GEHEIM_MAX)}}
AUFGABE_WAHRHEIT = {
    "de": f"Aufgabe: Lege die feste Wahrheit dieses Kapitels fest, bevor es beginnt: {PERSONEN[0]} bis {PERSONEN[1]} "
          f"Personen der Welt (name, rolle, ziel, sprache: wie sie redet), bis zu {GRUPPEN_MAX} Gruppen mit dem, was "
          f"sie wollen, und bis zu {GEHEIM_MAX} Geheimnisse, die die Gruppe aufdecken kann. Passend zu Welt, Ort, "
          "Einstieg und Geschichte; keine Figur der Gruppe. Kurz, ohne Werte.",
    "en": f"Task: set the fixed truth of this chapter before it begins: {PERSONEN[0]} to {PERSONEN[1]} people of the "
          f"world (name, rolle: role, ziel: goal, sprache: how they talk), up to {GRUPPEN_MAX} groups with what they "
          f"want, and up to {GEHEIM_MAX} secrets the group can uncover. Fitting world, place, opening and story; no "
          "character of the group. Short, no values."}
WAHRHEIT_LABEL = ("Feste Wahrheit dieses Kapitels (halte dich daran, Geheimnisse nur aufdecken, wenn die Gruppe sie "
                  "verdient):", "Fixed truth of this chapter (keep to it, reveal secrets only when the group earns them):")


def _part(dm, r, rd, x, n):
    t = dm.plain(x, n) if isinstance(x, str) else ""
    return "" if not t or dm.bad_words(r, rd, t) else t


def check_truth(dm, r, rd, obj):
    """The truth by fixed rules: lengths, no refused word, no hero's name as a person, no name twice. None when no
    person is left."""
    if not isinstance(obj, dict):
        return None
    heroes = {p["held"]["name"].lower() for _, p in dm.seated(rd)}
    personen, seen = [], set()
    for p in (obj.get("personen") or [])[:PERSONEN[1]]:
        name = _part(dm, r, rd, (p or {}).get("name"), NAME_LEN) if isinstance(p, dict) else ""
        if len(name) < 2 or name.lower() in heroes or name.lower() in seen:
            continue
        seen.add(name.lower())
        personen.append({"name": name, **{k: _part(dm, r, rd, p.get(k), TEIL_LEN) for k in ("rolle", "ziel", "sprache")}})
    if not personen:
        return None
    gruppen = []
    for g in (obj.get("gruppen") or [])[:GRUPPEN_MAX]:
        name = _part(dm, r, rd, (g or {}).get("name"), NAME_LEN) if isinstance(g, dict) else ""
        if len(name) >= 2:
            gruppen.append({"name": name, "will": _part(dm, r, rd, g.get("will"), TEIL_LEN)})
    geheim = [t for t in (_part(dm, r, rd, x, GEHEIM_LEN) for x in (obj.get("geheimnisse") or [])[:GEHEIM_MAX]) if len(t) >= 10]
    return {"personen": personen, "gruppen": gruppen, "geheimnisse": geheim}


async def make_truth(dm, r, rd):
    """The model sets the chapter's truth once (before the prologue); None when it failed (the game goes on without)."""
    if rd.get("wahrheit"):
        return None
    obj = await dm._ask_json(dm.system_text(r, rd, "wahrheit"), dm.facts(r, rd), SCHEMA_WAHRHEIT, "wahrheit", 700)
    w = check_truth(dm, r, rd, obj)
    print(f"dungeon: wahrheit | {'ok' if w else 'ausfall'} | {len((w or {}).get('personen') or [])} personen", flush=True)
    return w


def learn_people(rd, story):
    """A person the narration lets speak and the truth does not know joins it (no role yet), up to PERSONEN_MAX."""
    w = rd.get("wahrheit")
    if not w or not story:
        return 0
    known = {p["name"].lower() for p in w["personen"]}
    n = 0
    for x in story.get("npc") or []:
        name = str(x.get("name") or "")[:NAME_LEN]
        if len(name) >= 2 and name.lower() not in known and len(w["personen"]) < PERSONEN_MAX:
            w["personen"].append({"name": name, "rolle": "", "ziel": "", "sprache": ""})
            known.add(name.lower())
            n += 1
    return n


# ---------------------------------------------------------------- open threads and the running summary
SCHEMA_FAEDEN = {"type": "object", "additionalProperties": False, "properties": {"neu": _strs(FADEN_LEN, FAEDEN_NEU),
                                                                               "erledigt": _strs(FADEN_LEN, FAEDEN_ZU)}}
AUFGABE_FAEDEN = {
    "de": f"In faeden.neu trägst du höchstens {FAEDEN_NEU} neue offene Fäden ein (ein Versprechen, ein Auftrag, eine "
          f"offene Frage, je ein kurzer Satz), in faeden.erledigt die offenen Fäden, die diese Erzählung abschließt, "
          "genau so geschrieben wie in der Liste faeden. Greife offene Fäden auf, wenn es passt.",
    "en": f"In faeden.neu put at most {FAEDEN_NEU} new open threads (a promise, a quest, an open question, one short "
          f"sentence each), in faeden.erledigt the open threads this narration closes, written exactly as in the list "
          "faeden. Take up open threads when it fits."}


def check_threads(dm, r, rd, obj):
    """faeden of a narration by fixed rules: short, no refused word; closed only what is open."""
    obj = obj if isinstance(obj, dict) else {}
    neu = [t for t in (_part(dm, r, rd, x, FADEN_LEN) for x in (obj.get("neu") or [])[:FAEDEN_NEU]) if len(t) >= 5]
    offen = {f.lower(): f for f in rd.get("faeden") or []}
    zu = [offen[k] for k in (str(x).strip().lower() for x in (obj.get("erledigt") or [])[:FAEDEN_ZU]) if k in offen]
    return {"neu": neu, "erledigt": zu}


def apply_threads(rd, faeden):
    """The open threads after a narration: closed ones out, new ones in (no twice), the oldest dropped past FAEDEN_MAX."""
    if not faeden:
        return
    cur = [f for f in rd.get("faeden") or [] if f not in faeden.get("erledigt", [])]
    low = {f.lower() for f in cur}
    cur += [f for f in faeden.get("neu", []) if f.lower() not in low]
    rd["faeden"] = cur[-FAEDEN_MAX:]


SCHEMA_KURZ = {"type": "object", "additionalProperties": False, "required": ["kurz"],
               "properties": {"kurz": {"type": "string", "maxLength": KURZ_MAX + 200}}}
AUFGABE_KURZ = {
    "de": f"Aufgabe: Fasse dieses Kapitel bisher zusammen, höchstens {KURZ_MAX} Zeichen, in der Vergangenheit, mit "
          "den Namen der Gruppe, Orten, Personen, Funden und dem, was noch offen ist. Die frühere Zusammenfassung und "
          "die Erzählungen stehen als Spieltext zwischen <<< und >>>.",
    "en": f"Task: summarise this chapter so far, at most {KURZ_MAX} characters, in the past tense, with the group's "
          "names, places, people, finds and what is still open. The earlier summary and the narrations stand as game "
          "text between <<< and >>>."}
KURZ_LABEL = ("Dieses Kapitel bisher (Zusammenfassung):", "This chapter so far (summary):")


def wants_summary(rd):
    """Every KURZ_ALLE turns, once there are narrations to sum up."""
    dm_n = sum(1 for x in rd.get("log") or [] if x["art"] == "dm")
    return dm_n >= 3 and rd.get("zug", 0) - rd.get("kurz_zug", 0) >= KURZ_ALLE


async def summarize(dm, rid):
    """The running summary of the chapter, written in the background after a turn (wants_summary); kept only when it
    passes the fixed rules. Never raises."""
    import textnorm
    try:
        r = dm.rules()
        rd = (await asyncio.to_thread(dm._read))["runden"].get(rid)
        if not rd or rd["status"] != "laeuft" or not wants_summary(rd):
            return
        lang = "en" if rd["lang"] == "en" else "de"
        quelle = [x["text"] for x in rd["log"] if x["art"] == "dm"][-KURZ_QUELLE:]
        user = f"<<<\n{textnorm.defuse(rd.get('kurz') or '')}\n>>>\n<<<\n{textnorm.defuse(chr(10).join(quelle))}\n>>>"
        obj = await dm._ask_json(dm.PANEL_REGELN[lang].format(ton=dm._ton(r, rd)["regel"][1 if lang == "en" else 0])
                                 + "\n\n" + AUFGABE_KURZ[lang], user, SCHEMA_KURZ, "kurz", 600)
        text = _part(dm, r, rd, (obj or {}).get("kurz"), KURZ_MAX)
        if len(text) < KURZ_MIN:
            print("dungeon: kurz | ausfall", flush=True)
            return
        zug = rd["zug"]

        def keep():
            with dm._lock:
                d = dm._read()
                cur = d["runden"].get(rid)
                if cur:
                    cur.update(kurz=text, kurz_zug=zug)
                    dm._write(d)
        await asyncio.to_thread(keep)
        dm._day.bump("zusammengefasst")
        print(f"dungeon: kurz | ok | {len(text)} zeichen", flush=True)
    except Exception as e:   # noqa: BLE001 - a summary that did not come is no error of the game
        print(f"dungeon: kurz | fehler | {type(e).__name__}", flush=True)


def facts_extra(rd, li):
    """What the model gets on top of dungeon.facts: the truth, the summary and the open threads (all as data)."""
    out = {}
    if rd.get("wahrheit"):
        out["wahrheit"] = rd["wahrheit"]
    if rd.get("kurz"):
        out["kurz"] = rd["kurz"]
    if rd.get("faeden"):
        out["faeden"] = list(rd["faeden"])
    return out


# ---------------------------------------------------------------- the world's style
def check_style(r, need):
    """welten[].stil and toene[].stil: up to STIL_MAX pairs [de, en] of STIL_LEN characters (optional)."""
    for kind in ("welten", "toene"):
        for x in r.get(kind) or []:
            s = x.get("stil") if isinstance(x, dict) else None
            if s is None:
                continue
            need(isinstance(s, list) and len(s) <= STIL_MAX and all(
                isinstance(p, list) and len(p) == 2 and all(isinstance(t, str) and 20 <= len(t) <= STIL_LEN for t in p) for p in s),
                f"{kind}[{x.get('id')}].stil: bis {STIL_MAX} Paare [Deutsch, Englisch] mit 20 bis {STIL_LEN} Zeichen")


STIL_LABEL = ("So klingt eine Erzählung hier (nur Beispiele für Ton, Rhythmus und Sinne; übernimm keinen Inhalt):",
              "This is how a narration sounds here (examples of tone, rhythm and senses only; take over no content):")


def style_text(dm, r, rd, lang):
    li = 1 if lang == "en" else 0
    welt = dm._by(r, "welten").get(rd["welt"]) or {}
    beispiele = [p[li] for p in (welt.get("stil") or []) + (dm._ton(r, rd).get("stil") or [])]
    if not beispiele:
        return ""
    return "\n\n" + STIL_LABEL[li] + "\n" + "\n".join(f"- {t}" for t in beispiele)


# ---------------------------------------------------------------- fixed checks with one rewrite
HINWEIS = {
    "wiederholung": ("Hinweis: Deine Erzählung wiederholt zu viel aus den letzten Zügen. Erzähle Neues: eine Wendung, "
                     "ein neues Detail, eine Reaktion der Welt.",
                     "Note: your narration repeats too much of the last turns. Tell something new: a twist, a new "
                     "detail, a reaction of the world."),
    "namen": ("Hinweis: Jede Figur, die gehandelt hat, muss mit ihrem Namen vorkommen und eine Folge ihrer Aktion "
              "erleben: {namen}.",
              "Note: every character that acted must appear by name and meet a consequence of its action: {namen}."),
    "kurz": ("Hinweis: Deine Erzählung ist zu knapp. Beschreibe, was die Figuren sehen, hören und spüren, und wie die "
             "Welt auf sie reagiert.",
             "Note: your narration is too short. Describe what the characters see, hear and feel and how the world "
             "reacts to them.")}
_WORT = re.compile(r"\w+", re.UNICODE)


def _triples(text):
    w = [x.lower() for x in _WORT.findall(text)]
    return {tuple(w[i:i + 3]) for i in range(len(w) - 2)}


def judge(dm, rd, story):
    """("", []) when the narration passes; else (reason, the names missing) by fixed rules: too short, a hero who acted
    and is missing (one the model answered out of the game, ooc, may be missing), too much repeated from the last
    narrations."""
    text = story["text"]
    if len(text) < ZU_KURZ:
        return "kurz", []
    low, ooc = text.lower(), {x["pid"] for x in story.get("ooc") or []}
    missing = [rd["plaetze"][pid]["held"]["name"] for pid in rd["offen"]
               if pid not in ooc and pid in rd["plaetze"] and rd["plaetze"][pid].get("held")
               and rd["plaetze"][pid]["held"]["name"].lower() not in low]
    if missing:
        return "namen", missing
    t = _triples(text)
    old = set().union(*[_triples(x["text"]) for x in [e for e in rd["log"] if e["art"] == "dm"][-WIEDER_ZURUECK:]] or [set()])
    if t and len(t & old) / len(t) > WIEDERHOLT:
        return "wiederholung", []
    return "", []


def hint(why, missing, lang):
    return "\n\n" + HINWEIS[why][1 if lang == "en" else 0].format(namen=", ".join(missing))


# ---------------------------------------------------------------- 👍/👎 per narration
def thumb(dm, rid, pid, zug, gut):
    """A seat's thumb for the narration of turn zug (one per seat and turn, a new one replaces it); counted per world
    and tone over all rounds for the admin. Returns the seat's thumbs of the round."""
    if not isinstance(zug, int) or isinstance(zug, bool) or not isinstance(gut, bool):
        raise ValueError("daumen")
    with dm._lock:
        d = dm._read()
        rd = dm._round(d, rid)
        if not any(e["art"] == "dm" and e["n"] == zug for e in rd["log"]):
            raise LookupError("erzaehlung")
        votes = rd.setdefault("daumen", {}).setdefault(str(zug), {})
        old, new = votes.get(pid), 1 if gut else -1
        votes[pid] = new
        if len(rd["daumen"]) > dm.LOG_MAX:
            for k in sorted(rd["daumen"], key=int)[:-dm.LOG_MAX]:
                rd["daumen"].pop(k)
        stats = d.setdefault("daumen_welt", {}).setdefault(f"{rd['welt']}|{rd['ton']}", [0, 0])
        if old != new:
            if old:
                stats[0 if old > 0 else 1] -= 1
            stats[0 if new > 0 else 1] += 1
            dm._day.bump("daumen_hoch" if gut else "daumen_runter")
        dm._write(d)
        out = mine(rd, pid)
    print(f"dungeon: daumen | {'hoch' if gut else 'runter'}", flush=True)
    return out


def mine(rd, pid):
    return {k: v[pid] for k, v in (rd.get("daumen") or {}).items() if pid in v}


def stats(dm, r):
    """The thumbs per world and tone for the admin (numbers only, names from the rules)."""
    welten, toene = dm._by(r, "welten"), dm._by(r, "toene")
    out = []
    for k, (hoch, runter) in sorted((dm._read().get("daumen_welt") or {}).items()):
        w, _, t = k.partition("|")
        ton = toene.get(int(t)) if t.isdigit() else None
        out.append({"welt": (welten.get(w) or {}).get("name", [w, w]), "ton": (ton or {}).get("name", [t, t]),
                    "hoch": hoch, "runter": runter})
    return out


# ---------------------------------------------------------------- a chapter's truth goes on in the next one
def keep_chapter(rd):
    return {"wahrheit": rd.get("wahrheit"), "faeden": list(rd.get("faeden") or [])}


def carry(kampagne):
    return {k: kampagne[k] for k in ("wahrheit", "faeden") if kampagne.get(k)}


def view(rd, pid, host):
    out = {"faeden": list(rd.get("faeden") or []), "daumen": mine(rd, pid)}
    if host:
        out["wahrheit"] = rd.get("wahrheit")
    return out

