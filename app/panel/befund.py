"""Befund: the cause of a case, worked out before any proposal (plan plaene/vorschlaege-besser.md, V1, V2).

Dominik 2026-10-12, trace e62151: „Wurde ein neues Dokument für den reMarkable erstellt?“ was answered „Nein“ from the
uploaded documents; the 👎 brought only „Temperatur 0.2 → 0.1“. A proposal must fit a cause. The cause comes from fixed
rules on the request's facts (befund.facts: tool names offered, had to be called, called, failed, found nothing, and
whether the answer began with a no), the expectation (the person's chip „Hätte nachsehen sollen in …“, the admin's
„Erwartetes Werkzeug“, the Weiche's „Falsch zugeordnet“, the question's words when it was kept with consent) and the
Werkzeug-Karte below. Never from a model, never from words of an answer.

Werkzeug-Karte (V2): every tool the panel knows sits in a group of the Weiche (intent.GROUPS) or in ALLGEMEIN; a
self-test checks it like rule 23 for settings, so a new tool can not be missing here.
"""
import re

import faelle

# the causes, in the order the proposals follow them: key -> (German, English, what helps). What helps is a whole
# sentence for the Klartext-Karte (klartext.card); its ways become jump links on the page.
KLASSEN = {
    "weiche": ("Weiche hat falsch zugeordnet", "The Weiche sorted it wrongly",
               ("Ein eigenes Wort für die richtige Gruppe und ein Testsatz unter Funktionen → Weiche.",
                "An own word for the right group and a test sentence under Features → Switch.")),
    "nicht_gerufen": ("Richtiges Werkzeug war da, wurde aber nicht gerufen", "The right tool was there but not called",
                      ("Ein Wort, bei dem das Werkzeug Pflicht ist, und ein Testsatz.",
                       "A word that makes the tool a must, and a test sentence.")),
    "fehlt": ("Passendes Werkzeug war nicht angeboten", "No fitting tool was offered",
              ("Prüfen, ob die Funktion aus, gesperrt oder nicht eingerichtet ist; sonst ist es eine Lücke für eine Meldung.",
               "Check whether the function is off, locked or not set up; else it is a gap for a report.")),
    "fehler": ("Werkzeug ist gescheitert", "A tool failed",
               ("Unter Zustand → Dienste den Dienst des Werkzeugs prüfen; kommt es wieder, als Meldung vorbereiten.",
                "Check the tool's service under Status → Services; if it comes back, prepare a report.")),
    "dienst": ("Ein Dienst hat einen Fehler gemeldet", "A service reported an error",
               ("Kommt es wieder, als Meldung vorbereiten; die Anfrage zeigt den genauen Schritt.",
                "If it comes back, prepare a report; the request shows the exact step.")),
    "leer": ("Werkzeug fand nichts", "A tool found nothing",
             ("Dienst und Quelle prüfen: ist dort etwas zu finden?", "Check service and source: is there anything to find?")),
    "widerspruch": ("Antwort sagt Nein, obwohl ein Werkzeug etwas fand", "The answer says no although a tool found "
                    "something", ("Antworten prüfen lassen oder die Temperatur senken.",
                                  "Have answers checked or lower the temperature.")),
    "wissen": ("Ohne Nachschlagen geantwortet", "Answered without looking anything up",
               ("Öfter nachschlagen lassen oder die Websuche zur Pflicht machen.",
                "Look things up more often or make the web search a must.")),
    "erfunden": ("Antwort nennt Angaben, die in keinem Ergebnis stehen", "The answer names details that are in no "
                 "result", ("Antworten prüfen lassen, die Temperatur senken, die Frage in den Qualitätstest.",
                            "Have answers checked, lower the temperature, put the question into the quality test.")),
    "keine_regel": ("Keine Regel der Weiche erkannte die Frage", "No rule of the Weiche recognised the question",
                    ("Ein eigenes Wort für die passende Gruppe unter Funktionen → Weiche.",
                     "An own word for the fitting group under Features → Switch.")),
    "absage": ("Der Spark sagte, dass er das nicht kann", "The Spark said it cannot do that",
               ("Prüfen, ob die Funktion aus oder gesperrt ist; sonst ist es ein Wunsch für eine Meldung.",
                "Check whether the function is off or locked; else it is a wish for a report.")),
    "doppelt": ("Die Person fragte gleich noch einmal", "The person asked again right away",
                ("Die Frage in den Qualitätstest aufnehmen und die erste Antwort ansehen.",
                 "Put the question into the quality test and look at the first answer.")),
    "pruefung": ("Die Antwortprüfung hielt eine Angabe zurück", "The answer check held back a detail",
                 ("Unter Zustand → Logs → Anfragen nachsehen, welche Angabe in keinem Ergebnis stand.",
                  "Look under Status → Logs → Requests which detail was in no result.")),
    "abbruch": ("Die Person hat die Antwort abgebrochen", "The person stopped the answer",
                ("Kam der erste Ton spät, hilft schneller antworten; sonst die Frage in den Qualitätstest.",
                 "If the first sound came late, answering faster helps; else put the question into the quality test.")),
    "aussetzer": ("Die Sprachausgabe kam nicht hinterher", "The speech output could not keep up",
                  ("Mehr Vorlauf vor dem ersten Ton geben; der Vorschlag dazu ist ein Feinwert.",
                   "Give a longer lead before the first sound; the proposal for it is a fine value.")),
    "melder": ("Ein fester Melder schlug an", "A fixed detector went off",
               ("Der Vorschlag setzt bei dem an, was der Melder zählt.", "The proposal starts at what the detector counts.")),
    "richtig": ("Das erwartete Werkzeug lief und fand etwas", "The expected tool ran and found something",
                ("Keine Änderung nötig; „Erklären“ zeigt den Weg der Anfrage.", "No change needed; \"Explain\" shows the "
                 "request's way.")),
    "unklar": ("Ursache noch unklar", "Cause not clear yet",
               ("„Was wäre richtig gewesen?“ beantworten, dann folgt ein passender Vorschlag.",
                "Answer \"What would have been right?\", then a fitting proposal follows.")),
}
# a case of a kind with no cause of its own from the facts: its cause by the kind (fixed, never „unklar“)
BY_KIND = {"unklar": "keine_regel", "absage": "absage", "doppelt": "doppelt", "pruefung": "pruefung",
           "abbruch": "abbruch", "aussetzer": "aussetzer", "melder": "melder"}
ORDER = list(KLASSEN)
# tools of no group of their own: offered next to every group (memory, own documents, the computer, help)
ALLGEMEIN = {"memory_save", "memory_forget", "history_search", "document_search", "pc_action", "pc_send",
             "remarkable_note", "remarkable_page", "remarkable_attachment", "remarkable_sheet", "local_search", "spark_hilfe",
             "spark_vorschlag", "article_more", "routine_save",
             # offered when the person's own words name them, kept whatever the Weiche's group (werkzeug_abdeckung.BY_WORD)
             "remarkable_library", "home_rules_list", "home_rule_delete", "speaker_volume", "proactive_pause", "undo_last", "nas_ablegen", "nas_zustand"}
# tool definitions that never reach the chat's model (the health check's own test call, the agent's page reader)
NICHT_IM_CHAT = {"get_time", "read_page"}
TOOL = re.compile(r"[a-z][a-z0-9_]{1,40}")


def facts(s):
    """The facts of one turn for its case example (faelle.add): names and flags only, at most 40 names each."""
    def names(xs):
        return [n for n in dict.fromkeys(xs) if isinstance(n, str) and TOOL.fullmatch(n)][:40]
    return {"g": s.get("group") or "", "o": names(s.get("offered") or []), "n": names(s.get("need") or []),
            "c": names(n for n, _ in s.get("tools") or []), "x": names(n for n, ok in s.get("tools") or [] if not ok),
            "e": names(s.get("empty") or []), "neg": bool(s.get("neg")), "held": int(s.get("held") or 0)}


def karte():
    """{tool: [groups]} for every tool the Weiche knows; ALLGEMEIN as „allgemein“."""
    import intent
    out = {}
    for g, (tools, _) in intent.GROUPS.items():
        for t in tools:
            out.setdefault(t, []).append(g)
    for t in ALLGEMEIN:
        out.setdefault(t, []).append("allgemein")
    return out


# the modules that define tools for the chat (scanned by tool_defs; the agent, MCP and the health check have their own)
TOOL_MODULES = ("chat", "contacts", "docmake", "messages", "parcels", "remarkable", "rmplus", "tasks", "transit",
                "weather", "wiki", "begleiter", "hilfe")
_DEFS = {}


def tool_defs():
    """{name: tool definition} of every fixed tool definition in TOOL_MODULES (for the quality test's own questions
    with an expected tool and for Nachstellen). Tools built per turn are not in it."""
    if not _DEFS:
        import importlib
        for m in TOOL_MODULES:
            try:
                mod = importlib.import_module(m)
            except Exception:
                continue
            for v in vars(mod).values():
                for x in (v if isinstance(v, (list, tuple)) else [v]):
                    if isinstance(x, dict) and x.get("type") == "function" and isinstance(x.get("function"), dict):
                        n = x["function"].get("name")
                        if isinstance(n, str) and TOOL.fullmatch(n):
                            _DEFS.setdefault(n, x)
    return _DEFS


def expected(case, cfg=None):
    """The tools the case should have gone through, with where that comes from: [(tool, source)]."""
    import chat
    import intent
    ch = (cfg or {}).get("chat", {}) if cfg else {}
    out = []
    soll = case.get("soll") or {}
    if soll:
        top = max(soll, key=lambda k: soll[k])
        out += [(t, "person") for t in faelle.SOLL.get(top, ("", "", ()))[2]]
    for t in case.get("want_tool") or []:
        out.append((t, "admin"))
    if case.get("want") in intent.GROUPS:
        out += [(t, "weiche") for t in sorted(intent.GROUPS[case["want"]][0])]
    qs = [x["q"] for x in case.get("examples", []) if x.get("q") and faelle.CODEWORD not in x["q"]]
    if qs:
        q = qs[-1]
        k = karte()
        need = chat.needed(q, set(k), ch.get("tool_words", ""))
        out += [(t, "frage") for t in need]
        if not need:     # no must-rule: the tools of the groups its words point to
            for g in intent.classify_cfg(q, ch).names:
                out += [(t, "frage") for t in sorted(intent.GROUPS[g][0])]
    for x in case.get("examples", []):
        out += [(t, "pflicht") for t in (x.get("f") or {}).get("n", [])]
    seen, res = set(), []
    for t, src in out:
        if t and t not in seen:
            seen.add(t)
            res.append((t, src))
    return res


def diagnose(case, cfg=None):
    """The causes of a case, most likely first: [{"k", "tools", "group", "src"}]. Fixed rules only."""
    import intent
    ex = [x for x in case.get("examples", []) if isinstance(x.get("f"), dict)]
    f = ex[-1]["f"] if ex else {}
    called, offered = set(f.get("c", [])), set(f.get("o", []))
    exp = expected(case, cfg)
    src = exp[0][1] if exp else ""
    # only the strongest source counts (person or admin before the Weiche, the question, a recorded must-rule):
    # the question's own group tools must not outvote what the person said was right
    want = [t for t, s in exp if s == src]
    out = []

    def add(k, tools=(), group="", code=""):
        if not any(o["k"] == k for o in out):
            out.append({"k": k, "tools": list(tools)[:6], "group": group, "src": src} | ({"code": code} if code else {}))

    if f.get("x"):
        add("fehler", f["x"])
    if case.get("kind") == "erfunden":   # Antworten im Hintergrund prüfen (systemone.check_answer)
        add("erfunden", sorted(called))
    # the Weiche: a wrong group named by the admin, or the question's words point elsewhere
    groups_now = set((f.get("g") or case.get("group") or "").split("+")) - {"", "unklar"}
    if case.get("kind") == "weiche" and case.get("want"):
        add("weiche", group=case["want"])
    qs = [x["q"] for x in case.get("examples", []) if x.get("q") and faelle.CODEWORD not in x["q"]]
    if qs:
        names = intent.classify_cfg(qs[-1], (cfg or {}).get("chat", {}) if cfg else {}).names
        if names and not set(names) & groups_now and case.get("kind") != "weiche":
            add("weiche", group="+".join(names))
    if want and f:
        hit = [t for t in want if t in called]
        if hit:
            if [t for t in hit if t in f.get("e", [])]:
                add("leer", [t for t in hit if t in f.get("e", [])])
            elif f.get("neg"):
                add("widerspruch", hit)
            elif case.get("kind") == "schlecht":
                add("richtig", hit)
        else:
            there = [t for t in want if t in offered]
            if there:
                add("nicht_gerufen", there)
            else:
                add("fehlt", want)
    elif f:
        # without an expectation a „Nein“ after a tool is no proof of a contradiction (e62151: the wrong tool ran);
        # the case stays „unklar“ until someone says what would have been right
        if f.get("e") and set(f["e"]) & called:
            add("leer", sorted(set(f["e"]) & called))
        elif not called and case.get("kind") == "schlecht" and case.get("grund") in ("antwort", ""):
            add("wissen")
    kind = case.get("kind")
    if kind == "fehler" and case.get("code"):    # an error code of the request or an area of Logs → Diagnose
        add("dienst", code=case["code"])
    elif kind == "tool" and case.get("tool") and not out:
        add("fehler", [case["tool"]])
    elif kind in BY_KIND and not out:
        add(BY_KIND[kind])
    if not out:
        add("unklar")
    out.sort(key=lambda o: ORDER.index(o["k"]))
    return out


def text(b, english=False):
    """One line per cause for the page and the chat: „Richtiges Werkzeug war da … (document_status)“."""
    import intent
    import klartext
    import weiche
    i = 1 if english else 0
    rows = []
    for o in b:
        names = ", ".join(weiche.TOOLS.get(t, (t, t))[i] for t in o["tools"])
        group = ", ".join(intent.LABELS.get(g, g) for g in o.get("group", "").split("+") if g)
        rows.append(KLASSEN[o["k"]][i] + (f" ({names})" if names else "") + (f" → {group}" if group else "")
                    + (f": {klartext.code_text(o['code'])[i]}" if o.get("code") else ""))
    return rows
