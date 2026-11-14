"""Lesende Werkzeuge gleichzeitig (idea from OmniBot, Dominik 2026-11-14 „1-2“): when the model asks for several tools in
one round (up to chat.MAX_CALLS) and all of them only read, the panel starts them at the same time instead of one after
the other: „Wetter und Termine morgen?“ waits for the slower of the two, not for both. Admin switch chat.tools_parallel,
off; released for every profile the admin did not block; never guests (guests get no tool at all).

The panel decides with fixed rules, never the model. A round runs at the same time only when
    1. every call that runs is in LESEN (a fixed list of reading tools; nothing that switches, writes, sends or remembers,
       no mail tool, no Home Assistant, no screen: their locks are set only after their result),
    2. no tool comes twice (the Fehlerschleife counts per tool and may stop the second one),
    3. at most one of them goes to the internet (after an internet result the next internet tool may use its words,
       ausleiten.pool_dazu; with one there is nothing to miss).
The locks then come out exactly as one after the other: chat_tools._run sets „outside“ and „docs“ before its first wait
and the tasks start in the model's order. The results go back in the model's order, every step of the answer
(Ablauf, Taten, Fehlerschleife, Anfrage-Verlauf) runs after them as before. A call left over (more than MAX_CALLS,
stopped) is skipped as before.

The bottom layer (test_schichten.GRUND): imports no panel module.
"""

KEY = "gleichzeitig"   # features.py (steckbrief.py)
LESEN = frozenset({
    "web_search", "weather", "wikipedia", "archive_search", "parcels",
    "calendar_events", "contacts_search", "reminder_list", "tasks_show",
    "document_search", "document_list", "history_search", "fund_suche", "get_time",
})


def auswahl(calls, stopped, internet, max_calls):
    """The positions of the calls of this round to start at the same time, () when it runs one after the other.
    calls: [{"name", ...}] in the model's order; stopped: tools the Fehlerschleife stopped; internet: notaus.INTERNET_TOOLS."""
    run = [(k, str(x.get("name") or "")) for k, x in enumerate(calls) if k < max_calls and x.get("name") not in stopped]
    names = [n for _, n in run]
    if len(run) < 2 or any(n not in LESEN for n in names) or len(set(names)) != len(names):
        return ()
    if sum(n in internet for n in names) > 1:
        return ()
    return tuple(k for k, _ in run)
