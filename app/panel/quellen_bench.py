"""The source bench (plan such-index/zuverlaessig.md, steps 1 and 3): does a question go to the own data, to the outside
world or to both, and can it reach the right own sources?

Each line: sentence -> expected class and the sources it needs ("+" between them):
    intern   only the person's own data (mail, anhang, dokument, termin, kontakt, chat, liste, wissensbuch)
    extern   only the world outside (web: web search, weather, transit, Wikipedia, archive)
    beides   own data and the world (a timeless knowledge question: the quick look and the web with the own words)

measure() runs every sentence through the decision path, with every switch released for the own profile in the own
browser (Finden with mails, appointments and contacts, „Erst lokal“, the Weiche narrowing, chat.route_model "off"):
    1. intent.classify (the Weiche's groups, the first stage),
    2. intent.narrow over every tool a profile can be offered (ALL_TOOLS),
    3. quellen.klasse (the Quellen-Weiche, the second stage) with a stand-in index for its probe (ATTRAPPE: a few
       entries of a made-up household, never real data), quellen.blick for the quick look's sources,
and counts:
    the class the panel decides   quellen.klasse; "" (an action, small talk) -> "handlung" (never right here)
    the sources it can reach      the tools left after narrowing (TOOL_SOURCES), the quick look's sources for intern
                                  and beides (LOOK_SOURCES), the panel's own web search for beides; a mail tool only
                                  counts while chat.MAIL_HINT does not hold mails back
A sentence is right when the class is the expected one and every expected source is reachable.

tests/test_quellen_bench.py holds the floor (FLOOR, never lowered). Rules may be improved because of a group of misses
here, never by copying one of these sentences into a rule; a sentence that must always land right goes into
intent_bench.BENCH instead. Nothing here reads data, a clock or the model.
"""

# (sentence, class, sources): the probe sentences of zuverlaessig.md come first
BENCH = [
    # Probesätze (zuverlaessig.md, Teil 2)
    ("Was hat mir Thomann wegen der Lieferung geschrieben?", "intern", "mail"),
    ("Wann war nochmal der Termin beim Zahnarzt und gab es eine Rechnung?", "intern", "termin+dokument+mail"),
    ("Was weiß ich über Projekt X?", "intern", "dokument+mail+chat+wissensbuch"),
    ("Was ist der Stand bei meiner Steuererklärung?", "intern", "dokument+mail"),
    ("Welche Rechnung von Amazon war die teuerste?", "intern", "mail+anhang"),
    ("Was schreibt die Hausverwaltung zur Nebenkostenabrechnung?", "intern", "mail+dokument"),
    ("Hat sich der Klempner wegen dem Angebot gemeldet?", "intern", "mail"),
    ("Wie hieß nochmal das Hotel in Lissabon?", "intern", "mail"),
    ("Was kostet die Wärmepumpe laut Angebot?", "intern", "dokument+anhang"),
    ("Wie ist die Telefonnummer vom Zahnarzt?", "intern", "kontakt"),
    ("Such die Mail von Thomann", "intern", "mail"),
    ("Wie wird das Wetter?", "extern", "web"),
    ("Was kostet ein iPhone 17?", "extern", "web"),
    ("Wer ist Bundeskanzler?", "extern", "web"),
    ("Wie funktioniert eine Wärmepumpe?", "beides", "web+dokument"),
    # own data, with and without a word of ownership
    ("Hat mir die Versicherung geantwortet?", "intern", "mail"),
    ("Was hat mir Anna geschrieben?", "intern", "mail+chat"),
    ("Was hatte ich bei Thomann bestellt?", "intern", "mail"),
    ("Wie viel habe ich letztes Jahr für Strom bezahlt?", "intern", "dokument+mail"),
    ("Wann hatte ich zuletzt einen Termin beim Friseur?", "intern", "termin"),
    ("Was haben wir neulich über den Urlaub besprochen?", "intern", "chat"),
    ("Steht Milch auf meiner Einkaufsliste?", "intern", "liste"),
    ("Was steht in meinem Wissensbuch über Sauerteig?", "intern", "wissensbuch"),
    ("Wo wohnt Tante Gerda?", "intern", "kontakt"),
    ("Welche Mails kamen heute vom Finanzamt?", "intern", "mail"),
    ("Wann ist die nächste Rate fällig laut Vertrag?", "intern", "dokument"),
    ("Hat sich der Vermieter wegen der Heizung gemeldet?", "intern", "mail"),
    ("Was hat die Werkstatt zum Kostenvoranschlag geschrieben?", "intern", "mail"),
    ("Was steht im Angebot vom Dachdecker?", "intern", "dokument+anhang"),
    ("Wie viel kostet die Reparatur laut Rechnung?", "intern", "dokument"),
    ("Wann läuft meine Kfz-Versicherung ab?", "intern", "dokument"),
    ("Kam schon die Antwort vom Finanzamt?", "intern", "mail"),
    ("Gibt es Neuigkeiten von der Hausverwaltung?", "intern", "mail"),
    ("Was stand in der Mail von der Schule?", "intern", "mail"),
    ("Wann hat Lisa Geburtstag?", "intern", "kontakt"),
    ("What did Thomann write to me?", "intern", "mail"),
    ("Did the plumber get back to me?", "intern", "mail"),
    ("Show me the invoice from Thomann", "intern", "anhang"),
    # the world outside
    ("What's the weather tomorrow?", "extern", "web"),
    ("Who won the Champions League?", "extern", "web"),
    ("Hat der Baumarkt heute offen?", "extern", "web"),
    ("Wann fährt der nächste Zug nach München?", "extern", "web"),
    ("Wie ist der Kurs vom Euro zum Dollar?", "extern", "web"),
    ("Was kostet Strom aktuell pro Kilowattstunde?", "extern", "web"),
    ("Wie hat Bayern gespielt?", "extern", "web"),
    ("Was gibt es Neues in den Nachrichten?", "extern", "web"),
    ("Wie steht der DAX?", "extern", "web"),
    ("Gibt es heute Stau auf der A5?", "extern", "web"),
    ("Regnet es morgen in Hamburg?", "extern", "web"),
    ("Was ist heute politisch los?", "extern", "web"),
    ("What is the price of Bitcoin today?", "extern", "web"),
    ("Wer hat den Nobelpreis für Physik 2025 bekommen?", "extern", "web"),
    # both: timeless knowledge (the quick look, the web as an offer), also with „mein“ that asks about the world
    ("Wie geht mein iPhone in den Flugmodus?", "beides", "web"),
    ("Wie mache ich mein Handy schneller?", "beides", "web"),
    ("Wie lange hält mein Akku beim Fahrrad normalerweise?", "beides", "web"),
    ("Wie stelle ich meine Uhr auf Winterzeit um?", "beides", "web"),
    ("Mein Kühlschrank brummt laut, was kann ich tun?", "beides", "web+dokument"),
    ("Wie entkalke ich meine Kaffeemaschine?", "beides", "web+dokument"),
    ("Wie hoch ist die Zugspitze?", "beides", "web"),
    ("Was ist ein Wärmetauscher?", "beides", "web"),
    ("Wie macht man Sauerteig mit Roggenmehl?", "beides", "web+wissensbuch"),
    ("Wer war Albert Einstein?", "beides", "web"),
    ("Erklär mir Photosynthese", "beides", "web"),
    ("Wie lange ist Hackfleisch im Kühlschrank haltbar?", "beides", "web"),
    ("How does a heat pump work?", "beides", "web"),
    ("What is a quark?", "beides", "web"),
]
CLASSES = ("intern", "extern", "beides")
SOURCES = ("mail", "anhang", "dokument", "termin", "kontakt", "chat", "liste", "wissensbuch", "web")
# the probe's stand-in index: a made-up household's entries as Finden would return them (no real data, no file)
ATTRAPPE = (
    {"quelle": "mail", "titel": "Projekt X: Zeitplan und nächste Schritte", "auszug": "Meilensteine bis Dezember",
     "felder": {"absender": "Team Projekt X"}},
    {"quelle": "mail", "titel": "Buchungsbestätigung Hotel Miradouro Lissabon", "auszug": "Ihre Reservierung für zwei Nächte",
     "felder": {"absender": "Hotel Miradouro"}},
    {"quelle": "mail", "titel": "Nebenkostenabrechnung 2025", "auszug": "Abrechnung für die Wohnung",
     "felder": {"absender": "Hausverwaltung Berger"}},
    {"quelle": "anhang", "titel": "Rechnung 2026-0815", "auszug": "Gitarrensaiten und Kabel",
     "felder": {"absender": "Thomann", "betrag": "48,90 €"}},
)
# which source a tool reaches (fund_suche: Finden with every source released)
TOOL_SOURCES = {
    "fund_suche": {"mail", "anhang", "dokument", "termin", "kontakt", "chat", "liste", "wissensbuch"},
    "document_search": {"dokument"}, "document_list": {"dokument"}, "dokument_auswertung": {"dokument"},
    "mappe_stand": {"dokument"},
    "mail_list": {"mail"}, "mail_search": {"mail"}, "mail_read": {"mail"}, "fuer_dich": {"mail"},
    "calendar_events": {"termin"}, "daily_briefing": {"termin"},
    "contacts_search": {"kontakt"},
    "history_search": {"chat"}, "message_read": {"chat"},
    "tasks_show": {"liste"}, "home_assistant_todo": {"liste"},
    "web_search": {"web"}, "weather": {"web"}, "transit": {"web"}, "wikipedia": {"web"}, "archive_search": {"web"},
    "article_more": {"web"}, "feeds_news": {"web"},
}
# the quick look of „Erst lokal“ (lokal.look) for intern and beides, by the source it asks: Finden over every released
# source (step 4), the documents, the earlier conversations; beides also the panel's web search with the own words
LOOK_SOURCES = {"fund_suche": {"mail", "anhang", "dokument", "termin", "kontakt", "chat", "liste", "wissensbuch"},
                "document_search": {"dokument"}, "history_search": {"chat"}}


def all_tools():
    """Every tool a profile can be offered by the Weiche's groups, the kept and the lean ones, and Finden."""
    import intent
    names = set(intent.NARROW_KEEP) | set(intent.LEAN) | {"fund_suche", "history_search", "message_read"}
    for tools, _ in intent.GROUPS.values():
        names |= set(tools)
    return [{"type": "function", "function": {"name": n}} for n in sorted(names)]


def _wanted(spec):
    return {s for s in str(spec).split("+") if s}


def attrappe(worte):
    """The probe on ATTRAPPE: the entries that share a word with the question's words (like Finden's OR search)."""
    import lokal
    q = set(lokal.terms(worte))
    return [dict(h) for h in ATTRAPPE if q & set(lokal.terms(lokal.fund_text(h)))][:3]


def quellen(kind, tools, look=(), web=False):
    """The sources the turn can reach: the tools left after narrowing, the quick look's sources (look: tool names) and
    the panel's own web search (web)."""
    names = {t["function"]["name"] for t in tools}
    out = set()
    for n in names:
        out |= TOOL_SOURCES.get(n, set())
    if kind in ("intern", "beides"):
        for n in look:
            out |= LOOK_SOURCES.get(n, set())
    if web:
        out.add("web")
    return out


def judge(text, classify=None, narrow=None, probe=None):
    """One sentence through the decision path: {"route", "kind", "klasse", "quellen", "gruende"}."""
    import intent
    import lokal
    import quellen as qw
    classify = classify or intent.classify
    narrow = narrow or intent.narrow
    route = classify(text)
    offered = all_tools()
    tools = narrow(route, offered, {})
    kind, why = qw.klasse(text, "bench", {"route": route, "probe": probe or attrappe})
    if "eigene Quelle" in why:
        tools = [t for t in tools if t["function"]["name"] != "web_search"]
    srcs = qw.blick(kind, why, lokal.sources({t["function"]["name"] for t in offered}), "eigene Quelle" not in why)
    look = {lokal.SOURCES[k] for k in srcs if k in lokal.SOURCES}
    return {"route": route.label(), "kind": kind or "-", "klasse": kind or "handlung", "gruende": why,
            "quellen": quellen(kind, tools, look, "web" in srcs)}


def measure(rows=None, **kw):
    """Every sentence: the share right (class and sources), the share with the right class, per class, and how many
    questions about own mails went out ("mail_extern", the goal is 0); rows: the sentences not right."""
    rows = BENCH if rows is None else rows
    per = {c: {"n": 0, "richtig": 0, "klasse": 0} for c in CLASSES}
    out = {"n": 0, "richtig": 0, "klasse": 0, "mail_extern": 0, "je": per, "rows": []}
    for q, want, spec in rows:
        got = judge(q, **kw)
        need = _wanted(spec)
        fehlt = sorted(need - got["quellen"])
        ok_cls = got["klasse"] == want
        ok = ok_cls and not fehlt
        out["n"] += 1
        per[want]["n"] += 1
        out["klasse"] += ok_cls
        per[want]["klasse"] += ok_cls
        out["richtig"] += ok
        per[want]["richtig"] += ok
        if "mail" in need and want == "intern" and got["klasse"] == "extern":
            out["mail_extern"] += 1
        if not ok:
            out["rows"].append({"q": q, "want": want, "got": got["klasse"], "fehlt": fehlt, "route": got["route"],
                                "gruende": "+".join(got["gruende"])})
    out["quote"] = round(100 * out["richtig"] / out["n"], 1) if out["n"] else 0.0
    out["klasse_quote"] = round(100 * out["klasse"] / out["n"], 1) if out["n"] else 0.0
    return out


def report(m):
    """The measure as lines of text (for a person reading it; never written to the journal)."""
    out = [f"{m['richtig']}/{m['n']} richtig ({m['quote']} %), Klasse {m['klasse']}/{m['n']} ({m['klasse_quote']} %), "
           f"Mail nach extern {m['mail_extern']}"]
    out += [f"{c}: {v['richtig']}/{v['n']} richtig, Klasse {v['klasse']}/{v['n']}" for c, v in m["je"].items()]
    out += [f"- {r['q']} | erwartet {r['want']}, bekommt {r['got']} ({r['route']}, {r['gruende']})"
            + (f", fehlt {'+'.join(r['fehlt'])}" if r["fehlt"] else "") for r in m["rows"]]
    return out
