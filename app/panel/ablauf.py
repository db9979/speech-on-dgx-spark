"""Ablauf und Freigabe zeigen (plan plaene/redde-ideen/plan.md, package A, Dominik 2026-10-17 „2a“).

Under an answer the assistant shows which tools it used, each with ok or not and its time (folded:
„3 Werkzeuge benutzt · 2,1 s“), and a proposal this answer left waiting for a plain "Ja" as a card with
Ja and Nein. A tap sends "Ja" or "Nein" like a typed answer from the same device and conversation, so the
module that made the proposal decides with its own fixed rules (calendars.confirms ...); the card itself
carries nothing out and never says more than the kind of the proposal.

Only fixed words: the readable tool name (werkzeuge.NAMES), never its arguments or its result; the kind of a
proposal from KINDS, never its text. Admin switch chat.show_steps (off); never for guests or another voice
(chat_turn steps_on). The same events reach the iPhone app (Assistant.swift); Android shows the panel.
"""
import taten
import werkzeuge

# module of a waiting proposal (chat_turn.waiting_mods) -> what it is about, in fixed words
KINDS = {
    "calendars": ("Termin", "Appointment"),
    "tidy": ("Postfach", "Mailbox"),
    "tasks": ("Liste", "List"),
    "fixes": ("Gedächtnis", "Memory"),
    "agent": ("Auftrag", "Job"),
    "messages": ("Nachricht", "Message"),
    "roomfar": ("Durchsage", "Announcement"),
    "meinmcp": ("Eigener Dienst", "Own service"),
    "hamelden": ("Smart-Home-Meldung", "Smart home alert"),
    "aendern": ("Rückgängig", "Undo"),
    "nasablage": ("NAS-Ablage", "NAS filing"),
}


def step(name, result, seconds):
    """The event for one tool call of this answer (only offered tools reach here): readable name, ok, ms."""
    return {"type": "step", "tool": name, "de": werkzeuge.label(name), "en": werkzeuge.label(name, True),
            "ok": not taten.failed(result) if isinstance(result, str) else True, "ms": max(0, int(seconds * 1000))}


def waiting(uid, mods, since, src):
    """The kinds of the proposals this answer left for a "Ja": made since the start of the turn, from this device
    and conversation (the yes only counts there). Returns [{"type": "confirm", "kind", "de", "en"}]."""
    out = []
    for mod in mods:
        try:
            p = mod.pending(uid)
        except Exception:
            continue
        if not isinstance(p, dict) or p.get("t", 0) < int(since) or p.get("src", src) != src:
            continue
        kind = mod.__name__.rsplit(".", 1)[-1]
        de, en = KINDS.get(kind, ("Vorschlag", "Proposal"))
        out.append({"type": "confirm", "kind": kind, "de": de, "en": en})
    if out:
        print(f"chat: freigabe-karte gezeigt | {len(out)}", flush=True)
    return out[:1]   # one yes confirms one thing (chat_turn): one card
