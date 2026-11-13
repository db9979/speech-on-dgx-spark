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

import steckbrief

# tool -> (de, en)
NAMES = {
    # tools outside the switch's groups, the panel's own steps and tools only programs call over MCP
    "get_time": ("Uhrzeit", "Time"), "read_page": ("Webseite lesen", "Read web page"),
    "local_search": ("Erst in eigenen Quellen", "Own sources first"), "remarkable": ("reMarkable", "reMarkable"),
    "document_write": ("Dokument schreiben", "Write document"), "document_build": ("Datei bauen", "Build file"),
    "document_sources": ("Quellen fürs Dokument", "Sources for the document"),
    "document_facts": ("Fakten aus dem Archiv", "Facts from the archive"), "document_picture": ("Bild aus dem Archiv", "Picture from the archive"),
    "job_plan": ("Plan des Auftrags", "Plan of the job"), "job_ask": ("Rückfrage im Auftrag", "Question in a job"),
    "job_propose": ("Vorschlag des Auftrags", "Proposal of the job"),
    "today": ("Heute (Überblick)", "Today (overview)"), "action_status": ("Stand einer Bestätigung", "State of a confirmation"),
    **steckbrief.werkzeug_namen(),   # the functions with a Steckbrief (steckbrief.py)
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
