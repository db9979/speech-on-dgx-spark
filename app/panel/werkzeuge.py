"""The readable name of every tool (Dominik 2026-10-12: „die Werkzeuge haben komische Namen“).

The language model and the logs know a tool by its internal name (mail_tidy_overview); people see
„Postfach-Überblick“ / „Mailbox overview“ instead, everywhere a tool shows: Zustand → Live (Weg der
Anfrage, what the services gave back), Logs → Anfragen, Funktionen → Weiche, Zustand → Verbessern and
„Kopieren für Thread“. Where a thread has to match a trace, the internal name stays beside it, small.

One table for the panel and the pages: static/js/werkzeuge.js is written from it
(python3 app/panel/werkzeuge.py --js); tests/test_werkzeuge.py checks that every tool has a name here
and that the file is current. Tools of MCP services (mcp_…, mcpu_…) are named by the service's own tool.
"""
import json
import os
import re
import sys

# tool -> (de, en)
NAMES = {
    "home_assistant": ("Smart Home", "Smart home"), "home_assistant_action": ("Geräte schalten", "Switch devices"),
    "home_assistant_states": ("Zustände lesen", "Read states"), "home_assistant_history": ("Verlauf", "History"),
    "camera_describe": ("Kamerabild", "Camera picture"), "home_rules_list": ("Smart-Home-Regeln", "Smart home rules"),
    "home_assistant_todo": ("Home-Assistant-Listen", "Home Assistant lists"),
    "calendar_events": ("Termine lesen", "Read appointments"), "calendar_add": ("Termin eintragen", "Add appointment"),
    "daily_briefing": ("Tagesüberblick", "Daily briefing"), "mail_list": ("Mails auflisten", "List mails"),
    "mail_search": ("Mails suchen", "Search mails"), "mail_read": ("Mail lesen", "Read mail"),
    "mail_tidy_overview": ("Postfach-Überblick", "Mailbox overview"), "mail_tidy_propose": ("Postfach aufräumen", "Tidy mailbox"),
    "mail_draft": ("Mail-Entwurf", "Mail draft"), "web_search": ("Websuche", "Web search"),
    "reminder_set": ("Erinnerung stellen", "Set reminder"), "reminder_list": ("Erinnerungen zeigen", "List reminders"),
    "reminder_cancel": ("Erinnerung löschen", "Cancel reminder"), "tasks_show": ("Liste zeigen", "Show list"),
    "tasks_add": ("Auf die Liste", "Add to list"), "tasks_change": ("Liste ändern", "Change list"),
    "calendar_change": ("Termin ändern", "Change appointment"), "agent_change": ("Auftrag ändern", "Change job"),
    "home_rule_delete": ("Regel löschen", "Delete rule"), "proactive_pause": ("Meldungen pausieren", "Pause notes"),
    "speaker_volume": ("Lautstärke", "Volume"), "undo_last": ("Rückgängig", "Undo"),
    "weather": ("Wetter", "Weather"), "transit": ("Bus und Bahn", "Transit"), "parcels": ("Pakete", "Parcels"),
    "feeds_news": ("Reddit und Feeds", "Reddit and feeds"),
    "contacts_search": ("Kontakte", "Contacts"), "memory_save": ("Merken", "Remember"),
    "memory_forget": ("Vergessen", "Forget"), "history_search": ("Frühere Gespräche", "Earlier conversations"),
    "document_search": ("Eigene Dokumente", "Own documents"),
    "document_list": ("Dokumentliste", "Document list"), "message_send": ("Nachricht senden", "Send message"),
    "message_read": ("Nachrichten lesen", "Read messages"), "message_announce": ("Durchsage", "Announcement"),
    "agent_list": ("Agenten zeigen", "List agents"), "agent_task": ("Agent beauftragen", "Agent task"),
    "agent_schedule": ("Agent planen", "Schedule agent"), "agent_watch": ("Beobachten anlegen", "Set up watching"), "routine_save": ("Ablauf speichern", "Save routine"),
    "iphone_action": ("iPhone-Aktion", "iPhone action"), "spark_hilfe": ("Spark-Hilfe", "Spark help"),
    "spark_tagebuch": ("Spark-Tagebuch", "Spark diary"), "spark_zustand": ("Spark-Zustand", "Spark status"),
    "spark_vorschlag": ("Spark-Vorschlag", "Spark suggestion"), "wikipedia": ("Wikipedia", "Wikipedia"),
    "article_more": ("Artikel weiterlesen", "Read on"), "archive_search": ("Eigenes Archiv", "Own archive"),
    "document_plan": ("Dokument planen", "Plan document"), "document_change": ("Dokument ändern", "Change document"),
    "document_status": ("Dokument-Stand", "Document status"), "document_send": ("Dokument senden", "Send document"),
    "bild_malen": ("Bild malen", "Paint picture"),
    "musik_machen": ("Musik machen", "Make music"),
    "anruf_planen": ("Anrufen lassen", "Have the Spark call"),
    "remarkable_sent": ("Aufs reMarkable Gelegtes", "Put on the reMarkable"),
    "remarkable_library": ("reMarkable-Ablage", "reMarkable library"),
    "nas_ablegen": ("Auf der NAS ablegen", "Save to the NAS"),
    "nas_zustand": ("Zustand der NAS", "NAS status"),
    "pc_action": ("Rechner-Aktion", "Computer action"), "pc_send": ("An den Rechner", "Send to computer"),
    # tools outside the switch's groups, the panel's own steps and tools only programs call over MCP
    "get_time": ("Uhrzeit", "Time"), "read_page": ("Webseite lesen", "Read web page"),
    "local_search": ("Erst in eigenen Quellen", "Own sources first"), "remarkable": ("reMarkable", "reMarkable"),
    "remarkable_note": ("Notiz aufs reMarkable", "Note to the reMarkable"),
    "remarkable_page": ("Webseite aufs reMarkable", "Web page to the reMarkable"),
    "remarkable_sheet": ("Blatt aufs reMarkable", "Sheet to the reMarkable"),
    "remarkable_attachment": ("Mail-Anhang aufs reMarkable", "Mail attachment to the reMarkable"),
    "document_write": ("Dokument schreiben", "Write document"), "document_build": ("Datei bauen", "Build file"),
    "document_sources": ("Quellen fürs Dokument", "Sources for the document"),
    "document_facts": ("Fakten aus dem Archiv", "Facts from the archive"), "document_picture": ("Bild aus dem Archiv", "Picture from the archive"),
    "today": ("Heute (Überblick)", "Today (overview)"), "action_status": ("Stand einer Bestätigung", "State of a confirmation"),
}
MCP = re.compile(r"^mcpu?_[0-9a-f]{6}_(.+)$")   # mcp.exposed / meinmcp.exposed
PANEL = " (Panel)"                               # a step the panel ran itself (tracelog)
JS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js", "werkzeuge.js")


def label(name, english=False):
    """The readable name of a tool; an unknown name (already a word like „NAS-Sicherung“) stays as it is."""
    name = str(name or "")
    base = name[:-len(PANEL)] if name.endswith(PANEL) else name
    if base in NAMES:
        out = NAMES[base][1 if english else 0]
    else:
        m = MCP.match(base)
        if not m:
            return name
        out = ("Service: " if english else "Dienst: ") + m.group(1).replace("_", " ")
    return out + (PANEL if base != name else "")


def full(name, english=False):
    """The readable name with the internal one beside it, for copies a thread reads: „Postfach-Überblick (mail_tidy_overview)“."""
    lab = label(name, english)
    return lab if lab == str(name or "") else f"{lab} ({name})"


def js():
    """static/js/werkzeuge.js: the same table and the same two functions for the pages."""
    table = json.dumps({k: list(v) for k, v in NAMES.items()}, ensure_ascii=False, separators=(",", ":"))
    return ("// Written by app/panel/werkzeuge.py --js from werkzeuge.NAMES: do not edit here.\n"
            "// The readable name of every tool (de, en); the internal name stays for copies a thread reads.\n"
            f"const WZ={table};\n"
            "function wzName(n){const s=String(n==null?'':n),p=s.endsWith('" + PANEL + "')?s.slice(0,-" + str(len(PANEL)) + "):s,"
            "en=typeof L!=='undefined'&&L==='en',x=Object.prototype.hasOwnProperty.call(WZ,p)?WZ[p]:null;let o;"
            "if(x)o=x[en?1:0];else{const m=p.match(/^mcpu?_[0-9a-f]{6}_(.+)$/);if(!m)return s;"
            "o=(en?'Service: ':'Dienst: ')+m[1].replace(/_/g,' ')}return p===s?o:o+'" + PANEL + "'}\n"
            "function wzFull(n){const l=wzName(n),s=String(n==null?'':n);return l===s?s:l+' ('+s+')'}\n")


if __name__ == "__main__" and "--js" in sys.argv:
    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write(js())
    print("written", JS_FILE)
