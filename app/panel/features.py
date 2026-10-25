"""One description per function (plan „Vereinheitlichen“, V01.0.267).

Every function the admin can switch is written down here once: its name on every page, its group,
the admin switches it needs (and the functions it builds on), a personal preference where the Spark does
something unasked, and the Ich page it belongs to. The modules ask `admin_on` and `allowed` here instead of
each building their own check, and the panel, the iPhone app and the search read `/api/features` instead of
keeping their own lists.

What the admin releases works at once for every profile (Dominik 2026-10-13, plan plaene/freigabe-vereinfachen.md):
profiles switch nothing on, they only set up their part (an account, a device, a place) and choose preferences.
Only the admin can block a function for one profile (chat.deny). Guests (no profile) never get a function: they
only ask and get answers.

The stored names stay as they are (config.json chat.*, users/<id>/settings.json), so nothing has to
move: this table only knows both. The fixed protection rules (secrets never spoken, voice priority,
the owner's voice at a shared speaker) are not switches and stay where they are.
"""
import hashlib
import json
import os
import re
import time
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import profiles
from common import STATE, load_config, write_json
from core import acting_profile, assistant, auth, json_body

DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.default.json")

# groups as on the Funktionen page (guides.js GGROUPS)
GROUPS = (("talk", "Gespräch", "Conversation"), ("speed", "Tempo und Genauigkeit", "Speed and accuracy"),
          ("data", "Meine Daten", "My data"),
          ("day", "Mein Tag", "My day"), ("post", "Post und Kontakte", "Mail and contacts"),
          ("home", "Zuhause", "Home"), ("go", "Unterwegs und Geräte", "On the go and devices"),
          ("sec", "Zugang", "Access"))


# the pages of Ich, in their order: the one list for the panel (me.js meAll, guides.js ME_NAME) and the apps
# (/api/features "pages"); test_app_gleichstand keeps the copies equal (Richtlinie Teil 1 Zeile 18, Dominik 2026-10-14)
ME_PAGES = (("overbox", "Überblick", "Overview"), ("bgbox", "Mein Zustand", "My status"), ("gobox", "Los geht's", "Let's go"),
            ("kannbox", "Was ich kann", "What I can do"),
            ("setbox", "Gespräch", "Conversation"), ("loginbox", "Anmelden", "Sign in"), ("factbox", "Gedächtnis", "Memory"),
            ("docbox", "Dokumente", "Documents"), ("teilbox", "Geteilt", "Shared"), ("bildbox", "Bilder", "Pictures"), ("musikbox", "Musik", "Music"), ("rmbox", "reMarkable", "reMarkable"), ("storebox", "Speicher", "Storage"),
            ("logbox", "Werkzeug-Verlauf", "Tool history"),
            ("agentbox", "Aufträge", "Jobs"), ("mymcpbox", "Meine MCP-Dienste", "My MCP services"), ("wxbox", "Wetter", "Weather"), ("feedbox", "Reddit und Feeds", "Reddit and feeds"),
            ("probox", "Von selbst", "By itself"), ("notebox", "Mitteilungen", "Notifications"),
            ("wissbox", "Was ich über dich weiß", "What I know about you"), ("writebox", "Schreibhilfe", "Writing help"),
            ("habox", "Smart Home", "Smart home"), ("roombox", "Raum-Modus", "Room mode"), ("espbox", "Lautsprecher", "Speakers"), ("telbox", "Telefon", "Phone"),
            ("trbox", "Bus und Bahn", "Bus and train"), ("tgbox", "Telegram", "Telegram"), ("appbox", "iPhone-App", "iPhone app"),
            ("andbox", "Android-App", "Android app"), ("deskbox", "Begleiter", "Companion"), ("pebbox", "Pebble-Uhr", "Pebble watch"),
            ("termbox", "Terminal", "Terminal"), ("mcpbox", "Spark als MCP-Server", "Spark as MCP server"), ("secbox", "Sicherheit", "Security"),
            ("rpbox", "Probleme melden", "Reporting problems"), ("voicebox", "Sprechererkennung", "Speaker identification"),
            ("usebox", "Verbrauch", "Usage"))
# pages of their own in the menu, outside Ich (Dominik 2026-10-18: „im richtigen Bereich ersichtlich und einstellbar,
# nicht an zu vielen unterschiedlichen Orten … in den alten Bereichen dann raus nehmen“, plan kalender-mail/plan.md 4a):
# each holds everything of its kind, what is set up sits in its tab „Einstellungen“. The id of the box stays the place
# (me=<id>) of every way, card and app; kalender.js OWN_PAGES carries the same (test_app_gleichstand).
# (id, section, name de, name en)
OWN_PAGES = (("calbox", "cal", "Kalender", "Calendar"), ("mailbox", "post", "E-Mail", "E-mail"),
             ("taskbox", "listen", "Listen", "Lists"), ("vgbox", "offen", "Offen", "Open"),
             ("conbox", "kontakte", "Kontakte", "Contacts"),
             ("wbbox", "wbuch", "Wissensbuch", "Knowledge book"),
             ("dmbox", "dungeon", "Dungeon-Master", "Dungeon Master"))
# Ich pages every profile has, whatever is switched on (me.js meAll shows them for every profile too)
ME_ALWAYS = frozenset(("setbox", "factbox", "logbox", "secbox"))
# Ich pages the iPhone app leaves out, each with its reason; every other page can be opened in the app
APP_SKIP = {"overbox": "the app's own start screen shows the overview",
            "gobox": "first steps in the browser after signing up",
            "loginbox": "the app is signed in by its own key",
            "andbox": "the Android app, not for an iPhone"}
# Code-Prüfung D8 (one name per thing): an Ich page carries the name of its function, or a word of it, so "Funktionen →
# Telefon" and "Ich → Telefon" are found as the same thing; these pages are named otherwise, each with its reason
# (test_namen)
ME_NAME_OWN = {"kannbox": "what one can say, of all functions; its one function only adds tips while talking",
               "secbox": "sign-in, sessions and keys of the profile; the second sign-in step is one part of it",
               "habox": "the devices and rules of the home; the function carries the name of the system the admin connects"}


class Feature(NamedTuple):
    key: str
    de: str
    en: str
    group: str
    admin: tuple            # chat.* switches that must all be on
    pref: str = ""          # a preference in settings.json, on unless the profile switched it off: only where the
                            # Spark does something unasked (speaking up, push, sheets at night ...); never a release
    parent: str = ""        # the function it builds on (its switch must be on too)
    me: str = ""            # the Ich page (tab id) where the profile sets it up
    guide: str = ""         # guides.js id


F = Feature
FEATURES = (
    # conversation
    F("search", "Websuche", "Web search", "talk", ("search",), guide="search"),
    # chat.web_search (plan genauer-und-schneller, 7): 3 s per page, the fitting parts, 10 minutes in memory
    F("suchschnell", "Schnellere Websuche", "Faster web search", "talk", ("search_fast",), parent="search",
      guide="suchschnell"),
    F("wiki", "Wikipedia direkt", "Wikipedia straight away", "talk", ("wiki",), me="setbox", guide="wiki"),
    F("kiwix", "Eigenes Kiwix-Archiv", "Own Kiwix archive", "talk", ("kiwix",), me="setbox", guide="kiwix"),
    F("lokal", "Erst lokal suchen", "Look locally first", "talk", ("local_first",), me="setbox", guide="lokal"),
    F("roles", "Rollen per Sprache", "Roles by voice", "talk", ("roles",), me="setbox", guide="roles"),
    F("style", "Eigener Gesprächsstil", "Own conversation style", "talk", ("own_style",), me="setbox", guide="style"),
    F("follow", "Rückfrage ohne Weckwort", "Follow-up without wake word", "talk", ("follow_up",), me="setbox", guide="follow"),
    F("selfecho", "Eigene Stimme überhören", "Ignore my own voice", "talk", ("no_self_echo",), me="setbox", guide="selfecho"),
    # zwischenruf.py (plan ins-wort-fallen): a barge-in only pauses the answer; fixed words decide on, stop or question
    F("anhalten", "Ins Wort fallen: erst anhalten", "Barge-in: pause first", "talk", ("barge_hold",), me="setbox",
      guide="anhalten"),
    # satzende.py, smartturn.py (plan ins-wort-fallen B1): Smart Turn hears at each pause whether you sound done; measures only
    F("satzende", "Satzende am Tonfall", "Turn end by tone", "talk", ("turn_tone",), me="setbox", guide="satzende"),
    F("fixes", "Aus Korrekturen lernen", "Learning from corrections", "talk", ("learn_fixes",),
      parent="memory", me="setbox", guide="fixes"),
    F("klaeren", "Rückfrage statt Raten", "Ask instead of guessing", "talk", ("klaeren",), me="setbox",
      guide="klaeren"),
    F("klaerenmerken", "Auswahl merken", "Remember the choice", "talk", ("klaeren_merken",),
      parent="klaeren", me="setbox", guide="klaerenmerken"),
    # ablauf.py: the tools of an answer under it, a waiting proposal as a card with Ja and Nein
    F("ablauf", "Ablauf und Freigabe zeigen", "Show steps and approvals", "talk", ("show_steps",), guide="ablauf"),
    F("images", "Bilder erkennen", "Picture recognition", "talk", ("images",), me="setbox", guide="images"),
    F("toolthink", "Bei der Werkzeugwahl nachdenken", "Thinking while choosing tools", "speed", ("tool_thinking",),
      me="setbox", guide="toolthink"),
    F("routing", "Gezielte Werkzeugwahl", "Targeted tool choice", "speed", ("routing",), me="setbox", guide="routing"),
    F("direct", "Eindeutiges direkt abrufen", "Fetch clear questions directly", "speed", ("direct_read",),
      me="setbox", guide="direct"),
    # hoerwoerter.py (plan genauer-und-schneller, 5): the speech recognition gets the names of rooms, devices, people
    F("hoeren", "Namen fürs Hören", "Names for listening", "speed", ("hoer_namen",), guide="hoeren"),
    # chat.memory_split (plan genauer-und-schneller, 4): a long memory keeps a fixed core, older facts only when they fit
    # sofort.py (plan genauer-und-schneller, 6): time, date, arithmetic and units as the panel's fixed sentence
    F("sofort", "Einfaches sofort beantworten", "Answer simple things at once", "speed", ("sofort",), guide="sofort"),
    # rechnen.py (Dominik 2026-10-22): the tool rechnen and the check of sums, the panel computes, never the model
    F("rechnen", "Rechnen mit festem Werkzeug", "Exact calculations", "talk", ("rechnen",), guide="rechnen"),
    F("gedkurz", "Großes Gedächtnis kürzen", "Trim a large memory", "speed", ("memory_trim",), guide="gedkurz"),
    F("ack", "Sofortige Rückmeldung", "Instant acknowledgement", "speed", ("instant_ack",),
      parent="routing", me="setbox", guide="ack"),
    # weiche_abstimmen.py (plan opencode-werkstatt, point 1): the model proposes words, fixed rules keep what helps
    F("weicheabstimmen", "Weiche abstimmen", "Tune the switch", "speed", ("route_tune",), parent="routing", guide="weicheabstimmen"),
    # weiche_unklar.py (plan unklare-fragen): unclear questions kept anonymized for the admin to tune the Weiche with;
    # a preference, because the Spark keeps something of the profile's questions without being asked
    F("weicheunklar", "Unklare Fragen anonym merken", "Keep unclear questions anonymously", "speed", ("route_unklar",),
      pref="unklar_anon", parent="routing", me="setbox", guide="weicheunklar"),
    F("vorab", "Vorab holen bei Rückfrage", "Fetch ahead on a question back", "speed", ("prefetch",),
      parent="routing", me="setbox", guide="vorab"),
    F("hilfe", "Hilfe zum Spark", "Help with the Spark", "talk", ("spark_help",), me="setbox", guide="hilfe"),
    F("hilfevorschlag", "Einstellungen vorschlagen", "Suggesting settings", "talk", ("spark_suggest",),
      parent="hilfe", me="setbox", guide="hilfevorschlag"),
    F("hilfeseite", "Frag Spark auf jeder Seite", "Ask Spark on every page", "talk", ("spark_drawer",),
      parent="hilfe", me="setbox", guide="hilfeseite"),
    # tipps.py: the assistant points out a function that would help and helps setting it up
    F("tipps", "Funktionen vorschlagen", "Suggesting functions", "talk", ("feature_tips",),
      parent="hilfe", me="setbox", guide="tipps"),
    F("tippspush", "Funktionen vorschlagen von selbst", "Suggesting functions by itself", "day",
      ("feature_tips_push", "feature_tips"), pref="pro_tips", parent="proactive", me="probox", guide="tippspush"),
    # saetze.py: functions that are on but never used, with a sentence to say (Ich → Was ich kann)
    F("tippssaetze", "Das kannst du auch sagen", "You can also say", "talk", ("feature_sentences",),
      parent="tipps", me="kannbox", guide="tippssaetze"),
    F("tippsstimme", "Tipps beim Sprechen", "Tips while talking", "talk", ("feature_sentences_voice",),
      pref="voice_tips", parent="tippssaetze", me="setbox", guide="tippsstimme"),
    # qwen38's /v1/systemone (systemone.py): probabilities instead of words, the panel decides with fixed thresholds
    F("einordnung", "Einordnung mit Wahrscheinlichkeit", "Classification with probabilities", "speed", ("systemone",), me="setbox", guide="einordnung"),
    F("einordnungpost", "Einordnung beim Postfach aufräumen", "Classification when tidying the inbox", "speed",
      ("systemone_tidy", "mail_tidy", "mail"), parent="einordnung", me="setbox", guide="einordnungpost"),
    F("einordnungtest", "Einordnung im Qualitätstest", "Classification in the quality test", "speed", ("systemone_quality",),
      parent="einordnung", guide="einordnungtest"),
    F("einordnungrat", "Einordnung im Einstellungs-Assistenten", "Classification in the settings assistant", "speed",
      ("systemone_berater", "berater"), parent="einordnung", guide="einordnungrat"),
    F("einordnungcheck", "Antworten im Hintergrund prüfen", "Check answers in the background", "speed",
      ("systemone_check", "berater"), parent="einordnung", me="setbox", guide="einordnungcheck"),
    F("einordnungklage", "Beschwerde erkennen", "Recognize complaints", "speed", ("systemone_klage", "loop_stop"), parent="einordnung", me="setbox", guide="einordnungklage"),
    F("vorrang", "Vorrang für Personen", "Priority for people", "talk", ("person_priority",), guide="vorrang"),
    # knowledge and memory
    F("memory", "Gedächtnis", "Memory", "data", ("memory",), me="factbox", guide="memory"),
    # gedaechtnis.py (plan gedaechtnis-pruefen/plan.md): evidence per fact, fixed rules mark what may be out of date
    F("gedpruefen", "Gedächtnis prüfen", "Memory check", "data", ("memory_check",), parent="memory",
      me="factbox", guide="gedpruefen"),
    F("gedfragen", "Nachfrage zum Gedächtnis", "Memory check-back", "data", ("memory_ask",),
      parent="gedpruefen", me="setbox", guide="gedfragen"),
    F("gedthemen", "Themen im Gedächtnis", "Memory topics", "data", ("memory_topics",),
      parent="gedpruefen", me="factbox", guide="gedthemen"),
    F("history", "Frühere Gespräche", "Past conversations", "data", ("history",), me="setbox", guide="history"),
    F("documents", "Eigene Dokumente", "Own documents", "data", ("documents",), me="docbox", guide="documents"),
    F("docpics", "Bilder und Scans lesen", "Read pictures and scans", "data", ("doc_pictures",),
      parent="documents", me="docbox", guide="docpics"),
    F("docmeaning", "Bedeutungssuche", "Meaning search", "data", ("doc_semantic",),
      parent="documents", me="docbox", guide="docmeaning"),
    F("docfiles", "Originale aufbewahren", "Keep originals", "data", ("doc_originals",),
      parent="documents", me="docbox", guide="docfiles"),
    F("docnight", "Lange Dokumente nachts lesen", "Read long documents at night", "data", ("doc_night",),
      parent="documents", me="docbox", guide="docnight"),
    F("docshared", "Gemeinsame Dokumente", "Shared documents", "data", ("doc_shared",),
      parent="documents", me="docbox", guide="docshared"),
    # geteilt.py (plan teilen-profile, Dominik 2026-10-20 „ok“): one way to share for every kind, Ich → Geteilt; a
    # document to single profiles, calendars and lists listed and taken back there. The note is a preference.
    F("teilen", "Teilen mit Profilen", "Sharing with profiles", "data", ("share",), me="teilbox", guide="teilen"),
    F("teilenhinweis", "Hinweis auf Geteiltes", "Note on shared things", "data", ("share",), pref="share_note",
      parent="teilen", me="teilbox", guide="teilenhinweis"),
    # Docling-Server (doclingdienst.py): for all profiles once the admin sets it up; each may say "not my files"
    # (preference doc_docling, on by default) because the files leave the Spark for the server in the home network
    F("docling", "Docling-Server", "Docling server", "data", ("docling",), pref="doc_docling", parent="documents",
      me="docbox", guide="docling"),
    F("remarkable", "reMarkable-Notizen", "reMarkable notes", "data", ("remarkable",),
      parent="docpics", me="rmbox", guide="remarkable"),
    F("rmsend", "Aufs reMarkable schicken", "Sending to the reMarkable", "data", ("remarkable_send",),
      parent="remarkable", me="rmbox", guide="rmsend"),
    F("rmfresh", "Neueste zuerst", "Newest first", "data", ("remarkable_fresh",),
      parent="remarkable", me="rmbox", guide="rmfresh"),
    F("rmmorning", "Morgenblatt", "Morning sheet", "data", ("remarkable_plus",), pref="rm_morning", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmask", "@Spark auf Papier", "@Spark on paper", "data", ("remarkable_plus",), parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmtodo", "Aufgaben vom reMarkable", "Tasks from the reMarkable", "data", ("remarkable_plus",), parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmmeet", "Besprechungen zusammenfassen", "Meeting summaries", "data", ("remarkable_plus",), parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmweek", "Wochenrückblick", "Week in review", "data", ("remarkable_plus",), pref="rm_week", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmweb", "Webseiten und Anhänge aufs reMarkable", "Web pages and attachments to the reMarkable", "data", ("remarkable_plus",), parent="rmsend", me="rmbox", guide="rmplus"),
    F("rminbox", "Eingang pro Tag", "Daily inbox", "data", ("remarkable_plus",), pref="rm_inbox", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmguide", "Spark-Anleitung auf dem reMarkable", "Spark guide on the reMarkable", "data", ("remarkable_plus",), parent="rmsend", me="rmbox", guide="rmplus"),
    # paper for the reMarkable (rmpapier.py): one admin switch for three functions
    F("rmpapier", "Gestaltete Blätter zum Ankreuzen", "Designed sheets to tick", "data", ("remarkable_paper",),
      parent="rmsend", me="rmbox", guide="rmpapier"),
    F("rmordner", "Ordner nach Art", "Folders by kind", "data", ("remarkable_paper",), parent="rmsend", me="rmbox",
      guide="rmpapier"),
    F("rmaufraeumen", "Selbst aufräumen", "Tidy up by itself", "data", ("remarkable_paper",), pref="rm_tidy", parent="rmordner",
      me="rmbox", guide="rmpapier"),
    F("rmaufgaben", "Aufgabenblatt zum Ankreuzen", "Task sheet to tick", "data", ("remarkable_tasks",), "",
      parent="rmpapier", me="rmbox", guide="rmaufgaben"),
    # Dokumente erstellen (docmake.py, plan dokumente-erstellen): letters, presentations, tables ... as files
    F("erstellen", "Dokumente erstellen", "Creating documents", "data", ("doc_make",),
      parent="documents", me="docbox", guide="erstellen"),
    F("erstellenvorlagen", "Eigene Vorlagen", "Own templates", "data", ("doc_make_templates",),
      parent="erstellen", me="docbox", guide="erstellenvorlagen"),
    # pictures for slides from the own Kiwix (docmake.wiki_pictures; Präsentationen professionell, point 5)
    F("erstellenbilder", "Bilder aus dem Kiwix", "Pictures from the Kiwix", "data", ("doc_make_wikipics",),
      parent="erstellen", me="docbox", guide="erstellenbilder"),
    # Bilder malen (bilder.py, bild_server.py, plan bildgenerierung): FLUX.2 [klein] on the Spark, installed by install.sh --bild
    F("bilder", "Bilder malen", "Painting pictures", "data", ("bilder",), me="bildbox", guide="bilder"),
    # Bilder ändern (bilder.from_turn, plan bildbearbeitung, Stufe 2a): an own photo or picture changed by FLUX.2 [klein];
    # the panel picks the picture by a fixed rule, never the model
    F("bildaendern", "Bilder ändern", "Changing pictures", "data", ("bilder_aendern",), parent="bilder", me="bildbox",
      guide="bildaendern"),
    # Musik machen (musik.py, musik_server.py, plan musik M1): ACE-Step 1.5 on the model computer, install.sh --musik
    F("musik", "Musik machen", "Making music", "data", ("musik",), me="musikbox", guide="musik"),
    # Musik bearbeiten (musik.py, plan musik-experte, Stufe E1): an own song or an own file changed into a new version
    # (Abschnitt neu, Verlängern, Musikrichtung, Remix, Schneiden, Tempo und Tonart); the panel picks the song
    F("musikbearbeiten", "Musik bearbeiten", "Editing music", "data", ("musik_bearbeiten",), parent="musik",
      me="musikbox", guide="musikbearbeiten"),
    # KI-Dungeon-Master (dungeon.py, plan dungeon-master): a role-playing round for up to five players, also without a
    # profile by seat link; the model narrates, the panel rolls and gives loot, experience, levels and trades by fixed rules
    F("dungeon", "KI-Dungeon-Master", "AI Dungeon Master", "data", ("dungeon",), me="dmbox", guide="dungeon"),
    # Bilder für Ausrüstung und Zauber (dungeon_dingbild.py, plan „5i“): one picture per catalog entry and world, painted
    # at night or on the admin's button, and named finds; needs „Bilder malen“ of the Spark too
    F("dungeonbilder", "Bilder für Ausrüstung und Zauber", "Pictures for gear and spells", "data", ("dungeon_bilder",),
      parent="dungeon", me="dmbox", guide="dungeonbilder"),
    # Gäste mit E-Mail (dungeon_gast.py, plan Stufe 3): a guest keeps its heroes in an account after a 6-digit code from
    # the admin's mailbox, and may get „Du bist dran“ by mail; only a hash of the address, the address sealed on wish
    F("dungeongast", "Gäste mit E-Mail", "Guests with e-mail", "data", ("dungeon_gast",), parent="dungeon", me="dmbox",
      guide="dungeongast"),
    # Balance-Prüfstand (dungeon_pruefstand.py, Idee 5 of 2026-10-24): the panel plays fights alone with the real rules,
    # at night or on the admin's button, and shows the wins per level under Regeln; no model, no profile's data
    F("dungeonpruefstand", "Balance-Prüfstand", "Balance bench", "data", ("dungeon_pruefstand",), parent="dungeon",
      me="dmbox", guide="dungeonpruefstand"),
    # Spielleiter-Regler (dungeon_kampf.turn_dial, Idee 6): after every fight the next encounters at most ±25 % by fixed
    # numbers, the host may hold it, the children's table only easier
    F("dungeonregler", "Spielleiter-Regler", "Game master dial", "data", ("dungeon_regler",), parent="dungeon",
      me="dmbox", guide="dungeonregler"),
    # Heldenmut (dungeon_mut.py, Idee 8): once an evening a failed check again or a hit critical, a second charge from
    # the other players' 👍; fixed rules of the panel, never the model
    F("dungeonheldenmut", "Heldenmut", "Heroic courage", "data", ("dungeon_heldenmut",), parent="dungeon",
      me="dmbox", guide="dungeonheldenmut"),
    F("docbrief", "Steckbrief und Tags", "Document card and tags", "data", ("doc_brief",),
      parent="documents", me="docbox", guide="docbrief"),
    # Suchprüfung (suchpruefung.py, plan suche-schaerfen, Stufe 1): test questions measure how often the search
    # finds the right passage; the admin's release is enough (no profile switch, Freigabe rule 2026-10-13)
    F("suchpruefung", "Suchprüfung", "Search check", "data", ("search_check",), parent="documents", me="docbox",
      guide="suchpruefung"),
    F("nachsortieren", "Treffer nachsortieren", "Re-rank hits", "data", ("rerank",), parent="documents", me="docbox",
      guide="nachsortieren"),
    # Wissensbuch (wissensbuch.py, plan wissensbuch after Karpathy's LLM Wiki): own documents worked once into pages
    # with a source per sentence; the panel's fixed rules decide what stays, never the model
    F("wissensbuch", "Wissensbuch", "Knowledge book", "data", ("knowledge_book",), parent="documents", me="wbbox",
      guide="wissensbuch"),
    # Wissenskarte (wissenskarte.py, plan wissensgraph): the pages of the Wissensbuch as a map with checked connections
    F("wissenskarte", "Wissenskarte", "Knowledge map", "data", ("knowledge_map",), parent="wissensbuch", me="wbbox",
      guide="wissenskarte"),
    F("suchfragen", "Prüffragen vom Spark", "Test questions by the Spark", "data", ("search_check_auto",),
      parent="suchpruefung", me="docbox", guide="suchfragen"),
    # everyday
    F("proactive", "Von selbst melden", "Speaking up by itself", "day", ("proactive",), pref="pro_on", me="probox", guide="proactive"),
    # Home Assistant tells the Spark (hamelden.py): each part below "Von selbst melden"
    F("halive", "Sofort-Meldungen aus Home Assistant", "Instant notes from Home Assistant", "day", ("ha_live", "homeassistant"),
      pref="pro_ha_live", parent="proactive", me="probox", guide="halive"),
    F("haloud", "Haus-Meldungen über Lautsprecher", "House notes on speakers", "day",
      ("ha_loud", "homeassistant", "messages_announce", "chats"), pref="pro_ha_loud", parent="proactive", me="probox", guide="haloud"),
    F("haevent", "Home Assistant meldet an Spark", "Home Assistant tells the Spark", "day", ("ha_events", "homeassistant"),
      pref="pro_ha_events", parent="proactive", me="probox", guide="haevent"),
    F("havoice", "Smart-Home-Regel per Sprache", "Smart home rule by voice", "day", ("ha_voice_rules", "homeassistant"), parent="proactive", me="probox", guide="havoice"),
    F("mailwichtig", "Wichtige Mails erkennen", "Recognize important mail", "day", ("systemone_mail", "systemone", "mail"),
      pref="pro_mail_smart", parent="proactive", me="mailbox", guide="mailwichtig"),
    F("hacam", "Kamerabild beschreiben", "Describe a camera picture", "day", ("ha_camera", "homeassistant"),
      pref="pro_ha_cam", parent="proactive", me="probox", guide="hacam"),
    F("reminders", "Timer und Erinnerungen", "Timers and reminders", "day", ("reminders",), guide="reminders"),
    # zustellung.py (plan benachrichtigung-geraet, Dominik 2026-10-20 "ok"): a note goes to the device in use right now,
    # else to the phone app
    F("notedevice", "Mitteilung ans genutzte Gerät", "Notes to the device in use", "day", ("note_device", "reminders"),
      parent="reminders", guide="notedevice"),
    # Alles Offene im Assistenten (vorgaenge.py, plan assistent-zentrale): cards with buttons in the conversation, Später,
    # the page Offen; a child row under Timer und Erinnerungen (the Funktionen page is near its height limit)
    F("vorgaenge", "Alles Offene im Assistenten", "Everything open in the assistant", "day", ("vorgaenge",),
      parent="reminders", me="vgbox", guide="vorgaenge"),
    F("tasks", "Listen für Einkauf und Aufgaben", "Lists for shopping and tasks", "day", ("tasks",), me="taskbox", guide="tasks"),
    # tasks.py (plan listen-teilen Stufe 2, Dominik 2026-10-20 „3a“): share an own list with another profile, see or
    # put on and tick off; a note when others put something on (preference list_note)
    F("listshare", "Listen teilen", "Share lists", "day", ("tasks_share", "tasks"), parent="tasks", me="taskbox",
      guide="listshare"),
    F("listnote", "Hinweis bei neuen Einträgen", "Note on new entries", "day", ("tasks_share", "tasks"), pref="list_note",
      parent="listshare", me="taskbox", guide="listshare"),
    F("listdav", "Listen in Erinnerungen", "Lists in Reminders", "day", ("tasks_dav", "tasks", "calendar_server", "calendar"),
      parent="tasks", me="taskbox", guide="listdav"),
    F("listlink", "Mitschreib-Link", "Write link", "day", ("tasks_link", "tasks"), parent="tasks", me="taskbox",
      guide="listlink"),
    F("mystatus", "Mein Zustand", "My status", "day", ("my_status",), me="bgbox", guide="mystatus"),
    F("agent", "Aufträge", "Jobs", "day", ("agent",), me="agentbox", guide="agent"),
    # watches (beobachten.py): admin release only, every profile with agent functions, never guests
    F("beobachten", "Beobachten", "Watching", "day", ("agent_watch",), parent="agent", me="agentbox", guide="beobachten"),
    # package F of the redde ideas (auftragsplan.py): plan, question, proposal and Nachschieben inside a job
    F("auftragsplan", "Aufträge mit Plan, Rückfrage und Vorschlag", "Jobs with plan, questions and proposals", "day",
      ("agent_plan",), parent="agent", me="agentbox", guide="auftragsplan"),
    F("mcp", "Dienste per MCP", "Services over MCP", "day", ("agent_mcp",), parent="agent", guide="mcp"),
    # each profile its own MCP services (meinmcp.py); needs no agent level, only the switches
    F("mymcp", "Eigene MCP-Dienste", "Own MCP services", "day", ("mcp_own",), parent="mcp", me="mymcpbox",
      guide="mymcp"),
    F("mymcpjobs", "Eigene MCP-Dienste in Aufträgen", "Own MCP services in jobs", "day", ("mcp_own_jobs",),
      parent="mymcp", me="mymcpbox", guide="mymcpjobs"),
    F("mymcpoauth", "Eigene MCP-Dienste mit Anmeldung", "Own MCP services with sign-in", "day", ("mcp_own_oauth",),
      parent="mymcp", me="mymcpbox", guide="mymcpoauth"),
    # chats.py (plan plaene/messenger.md): chats between the people of this Spark, like a messenger; since V01.0.488
    # also what "Nachrichten an andere" did (plan plaene/nachrichten-in-chats.md): "Sag Anna …", "an alle", Durchsagen
    F("chats", "Chats", "Chats", "day", ("chats",), me="setbox", guide="chats"),
    F("messages_all", "Nachricht an alle", "Message to everybody", "day", ("messages_all",), pref="msg_all", parent="chats",
      me="setbox", guide="messages_all"),
    F("chatgroups", "Gruppen-Chats", "Group chats", "day", ("chats_groups",), parent="chats", me="setbox", guide="chatgroups"),
    F("chatmedia", "Fotos, Dateien und Sprache in Chats", "Photos, files and voice in chats", "day", ("chats_media",),
      parent="chats", me="setbox", guide="chatmedia"),
    F("chatinvite", "In einen Chat einladen", "Invite into a chat", "day", ("chats_invite",), parent="chats", me="setbox",
      guide="chatinvite"),
    F("chatprivate", "Private Chats (Ende-zu-Ende)", "Private chats (end-to-end)", "day", ("chats_private",), parent="chats",
      me="setbox", guide="chatprivate"),
    # verbund.py (plan plaene/spark-verbund.md): chats with people on other Sparks; needs the own address from outside
    F("verbund", "Chats mit anderen Sparks", "Chats with other Sparks", "day", ("chats_verbund",), parent="chats",
      guide="verbund"),
    F("verbundmedia", "Fotos und Dateien zu anderen Sparks", "Photos and files to other Sparks", "day", ("verbund_media",),
      parent="verbund", guide="verbundmedia"),
    F("verbundgruppen", "Gruppen mit anderen Sparks", "Groups with other Sparks", "day", ("verbund_groups",),
      parent="verbund", guide="verbundgruppen"),
    # anrufe.py (plan plaene/messenger-d-v2.md): voice and video calls in a chat of two; from outside through the
    # Vermittler (coturn on tars), which needs the address from outside
    F("anrufe", "Anrufe (Sprache und Video)", "Calls (voice and video)", "day", ("chats_calls",), parent="chats",
      guide="anrufe"),
    F("anrufeturn", "Anrufe von unterwegs", "Calls when away", "day", ("calls_turn",), parent="anrufe",
      guide="anrufeturn"),
    # rufen.py (Dominik 2026-10-18): „Ruf Sabine an“ to the assistant, a call after the person's yes; on Android also
    # „übers Telefon“ with the own address book
    F("anrufassistent", "Anrufe per Assistent", "Calls by the assistant", "day", ("calls_assistant",), parent="anrufe",
      guide="anrufassistent"),
    F("calendar", "Kalender", "Calendar", "day", ("calendar",), me="calbox", guide="calendar"),
    # calendars.py (Dominik 2026-10-18 „1a 2a“): share one calendar with another profile, see or see and enter;
    # private appointments only as „belegt“
    F("calshare", "Kalender teilen", "Share calendars", "day", ("calendar_share", "calendar"), parent="calendar",
      me="calbox", guide="calshare"),
    # kalenderserver.py (Dominik 2026-10-19 „1a-5a“, Spark-Kalender Stufe 4): the profile's Spark calendars for the
    # calendar app of the iPhone (CalDAV, an app password per profile)
    F("calserver", "Kalender-Server für Kalender-Apps", "Calendar server for calendar apps", "day",
      ("calendar_server", "calendar"), parent="calendar", me="calbox", guide="calserver"),
    F("weather", "Wetter", "Weather", "day", ("weather",), me="wxbox", guide="weather"),
    # feeds.py (Dominik 2026-10-17, plan reddit/plan.md): own Reddit inbox, subreddits and other feeds, read only
    F("feeds", "Reddit und Feeds", "Reddit and feeds", "day", ("feeds",), me="feedbox", guide="feeds"),
    F("feedsmelden", "Neues aus Feeds melden", "Telling news from feeds", "day", ("feeds", "proactive"),
      pref="pro_feeds", parent="proactive", me="probox", guide="feeds"),
    # mail and contacts
    F("mail", "E-Mail lesen", "Reading e-mail", "post", ("mail",), me="mailbox", guide="mail"),
    F("tidy", "Postfach aufräumen", "Inbox tidying", "post", ("mail_tidy",), parent="mail", me="mailbox", guide="tidy"),
    # postfach.py (plan kalender-mail Stufe 2, Mailclient Stufe A): on the page E-Mail read/unread, flag, archive, move
    # (also several at once), every folder read, own folders made, renamed, removed when empty
    F("mailmanage", "Mails ordnen", "Order mail", "post", ("mail_manage", "mail"), parent="mail", me="mailbox",
      guide="mailmanage"),
    F("mailsend", "Mails senden", "Send mail", "post", ("mail_send", "mail"), parent="mail", me="mailbox",
      guide="mailsend"),
    # mailidle.py (Vorwärmen Stufe C, Dominik 2026-10-19 „6a“): IMAP IDLE for profiles that read mail lately, new mail
    # and its rules within seconds, at most mailidle.MAX_OPEN connections
    # postfach.py „Löschen“ (Dominik 2026-10-20): the person moves a message into the trash and back, or removes one
    # there for good after the page's own question; rules, the model, „Für dich“ and the voice never delete
    F("maildelete", "Mails löschen", "Delete mail", "post", ("mail_delete", "mail_manage", "mail"), parent="mailmanage",
      me="mailbox", guide="maildelete"),
    # einladung.py (Dominik 2026-10-21 „ja alles umsetzen 1-6“, Punkt 3): an invitation (.ics) in a mail into a calendar
    # with one tap, Zusagen/Vielleicht/Absagen to the organiser (with „Mails senden“)
    F("einladungen", "Einladungen aus Mails", "Invitations from mail", "post", ("mail_invites", "mail", "calendar"),
      parent="mail", me="mailbox", guide="einladungen"),
    F("mailidle", "Neue Mails sofort", "New mail at once", "post", ("mail_idle", "mail"), parent="mail", me="mailbox",
      guide="mailidle"),
    # mailcode.py (Dominik 2026-10-21 „5“): a new mail with a confirmation code as a note on the device in use, never
    # Telegram, the code never logged; needs Neue Mails sofort
    F("mailcode", "Bestätigungscodes", "Confirmation codes", "post", ("mail_code", "mail_idle", "mail"), parent="mailidle",
      me="mailbox", guide="mailcode"),
    F("mailstil", "Mailstil lernen", "Learn mail style", "post", ("mail_style",), parent="mail", me="mailbox", guide="mailstil"),
    F("parcels", "Pakete", "Parcels", "post", ("parcels",), parent="mail", me="mailbox", guide="parcels"),
    # fuerdich.py (plan persoenlicher-assistent, Dominik 2026-10-18): bills, contracts, orders, offers, open replies and
    # phishing found in the own mails by fixed rules; tab „Für dich“ on the mail page
    F("fuerdich", "Für dich aus Mails", "For you from mail", "post", ("mail_insight",), parent="mail", me="mailbox",
      guide="fuerdich"),
    # ichweiss.py (stages 3 and 4, „3a 4a 6a 7a“): interests with their evidence (count after „Stimmt“), Wiederkehrendes,
    # the week and the month, one web tip a day; part of the same switch, its own page under Ich
    F("ichweiss", "Was ich über dich weiß", "What I know about you", "post", ("mail_insight",), parent="fuerdich",
      me="wissbox", guide="ichweiss"),
    F("schreib", "Schreibhilfe", "Writing help", "post", ("write_help",), me="writebox", guide="schreib"),
    F("schreibapps", "Schreibhilfe in anderen Programmen", "Writing help in other programs", "post", ("write_apps",), parent="schreib", me="writebox", guide="schreibapps"),
    F("contacts", "Kontakte", "Contacts", "post", ("contacts",), me="conbox", guide="contacts"),
    # contacts.py page Kontakte (Apple-Stil „6a“): a card changed in its own address book (ETag), new ones there or on the Spark
    F("kontakteaendern", "Kontakte ändern", "Edit contacts", "post", ("contacts_edit", "contacts"), parent="contacts",
      me="conbox", guide="kontakteaendern"),
    # kontaktserver.py (Apple-Stil „6a“ Stufe 3b): the address book „Auf dem Spark“ for the iPhone's Kontakte app (CardDAV,
    # the Kalender-Server's app password)
    F("kontaktserver", "Kontakte für Kontakte-Apps", "Contacts for contacts apps", "post",
      ("contacts_server", "contacts", "calendar_server"), parent="contacts", me="conbox", guide="kontaktserver"),
    # home
    F("ha", "Home Assistant", "Home Assistant", "home", ("homeassistant",), me="habox", guide="ha"),
    F("room", "Raum-Modus", "Room mode", "home", ("room",), me="roombox", guide="room"),
    F("roomtv", "Fernsehstimmen überhören", "Ignore TV voices", "home", ("room_voices",), parent="room", me="roombox", guide="roomtv"),
    F("roomha", "Raum-Modus für Home Assistant", "Room mode for Home Assistant", "home", ("room_ha",), parent="room",
      me="roombox", guide="roomha"),
    F("esp32", "Eigene Lautsprecher (ESP32)", "Own speakers (ESP32)", "home", ("esp32",), me="espbox", guide="esp32"),
    F("espstopp", "Stopp beim Vorlesen", "Stop while it speaks", "home", ("esp32_stop", "esp32"),
      parent="esp32", me="espbox", guide="espstopp"),
    F("roomfar", "Raum-Modus aus der Ferne starten", "Start room mode from afar", "home", ("room_remote", "esp32"),
      parent="room", me="roombox", guide="roomfar"),
    F("messages_announce", "Durchsagen auf Lautsprechern", "Announcements on speakers", "home", ("messages_announce",), parent="chats", me="setbox", guide="messages_announce"),
    F("wyoming", "Home Assistant Assist (Wyoming)", "Home Assistant Assist (Wyoming)", "home", ("wyoming",), guide="wyoming"),
    # Den Spark anrufen (telefon.py, plan telefon-anruf.md): the Spark as an IP phone at the home's PBX
    F("telefon", "Telefon", "Phone", "home", ("telefon",), me="telbox", guide="telefon"),
    # handsets nobody assigned get questions and answers as a guest (never a tool); off: a sentence, then hang up
    F("telefongast", "Telefon: Gäste annehmen", "Phone: take guests", "home", ("telefon_gaeste", "telefon"),
      parent="telefon", guide="telefongast"),
    # calls from outside through the PBX: confirmed own numbers (Ich → Telefon) as their profile, with Gäste also unknown ones
    F("telefonaussen", "Telefon: Anrufe von außen", "Phone: calls from outside", "home", ("telefon_aussen", "telefon"),
      parent="telefon", guide="telefonaussen"),
    # the Spark calls (telefon_anruf.py, T4): wake-up calls and reminders the profile ordered, call backs; the
    # preference telefon_anrufbar lets each profile say no
    F("telefonanrufen", "Telefon: der Spark ruft an", "Phone: the Spark calls", "home", ("telefon_anrufen", "telefon"),
      pref="telefon_anrufbar", parent="telefon", me="telbox", guide="telefonanrufen"),
    # a service gone 10 minutes or more: a call to the admin besides the note, never in the quiet hours
    F("telefonalarm", "Telefon: Anruf bei Dienstausfall", "Phone: call on outages", "home",
      ("telefon_alarm", "telefon_anrufen", "telefon", "svc_watch"), parent="telefonanrufen", guide="telefonalarm"),
    # on the go and devices
    F("transit", "Bus und Bahn", "Bus and train", "go", ("transit",), me="trbox", guide="transit"),
    F("telegram", "Telegram", "Telegram", "go", ("telegram",), me="tgbox", guide="telegram"),
    F("android", "Android-App", "Android app", "go", ("android",), me="andbox", guide="android"),
    F("androidlive", "Android: Mitteilungen sofort", "Android: notes at once", "go", ("android_live",), pref="android_live",
      parent="android", me="andbox", guide="androidlive"),
    F("androidupdate", "Android: Update in der App", "Android: update in the app", "go", ("android_update",),
      parent="android", me="andbox", guide="androidupdate"),
    F("androidassist", "Android: Spark als Assistent", "Android: Spark as assistant", "go", ("android_assist",),
      parent="android", me="andbox", guide="androidassist"),
    F("androidlock", "Android: Fingerabdruck für Admins", "Android: fingerprint for admins", "go", ("android_lock",),
      parent="android", me="andbox", guide="androidlock"),
    F("begleiter", "Spark-Begleiter am PC und Mac", "Spark companion on PC and Mac", "go", ("desk",),
      me="deskbox", guide="begleiter"),
    F("begleitertun", "Begleiter darf am PC handeln", "Companion may act on the PC", "go", ("desk_act",),
      parent="begleiter", me="deskbox", guide="begleitertun"),
    F("begleitermeeting", "Besprechungen mitschreiben", "Write along in meetings", "go", ("desk_meeting",),
      parent="begleiter", me="deskbox", guide="begleitermeeting"),
    # Rechner fernsteuern, Stufe 2 (fernsicht.py): look at the own PC or Mac and, when allowed there, operate it
    F("begleiterschirm", "Bildschirm zeigen und bedienen", "Show and operate the screen", "go", ("desk_view",),
      parent="begleiter", me="deskbox", guide="begleiterschirm"),
    # Stufe 3 (bedienen.py): the Spark operates the own computer step by step, every step confirmed there
    F("begleiterbedienen", "Spark bedient den Rechner", "Spark operates the computer", "go", ("desk_operate",),
      parent="begleiter", me="deskbox", guide="begleiterbedienen"),
    F("pebble", "Pebble-Uhr", "Pebble watch", "go", ("pebble",), me="pebbox", guide="pebblepair"),
    # more on the watch (pebblewatch.py, plan pebble-ideen/plan.md): follow-ups to tap, the profile's own fixed commands,
    # its reminders and timers kept on the watch as wake-ups (they ring without the phone)
    F("pebblefolge", "Uhr: Nachfragen zum Antippen", "Watch: follow-ups to tap", "go", ("pebble_follow",),
      parent="pebble", me="pebbox", guide="pebblefolge"),
    F("pebbleschnell", "Uhr: Schnellbefehle", "Watch: quick commands", "go", ("pebble_quick",),
      parent="pebble", me="pebbox", guide="pebbleschnell"),
    F("pebbleerinnern", "Uhr: Erinnerungen und Timer am Handgelenk", "Watch: reminders and timers on the wrist", "go",
      ("pebble_remind", "reminders"), parent="pebble", me="pebbox", guide="pebbleerinnern"),
    # Paket 2: a watchface of its own, the day and the week, outage notes for admins, quick notes (with the place)
    F("pebblezifferblatt", "Spark-Zifferblatt", "Spark watchface", "go", ("pebble_face",),
      parent="pebble", me="pebbox", guide="pebblezifferblatt"),
    F("pebbletag", "Uhr: Mein Tag und meine Woche", "Watch: my day and my week", "go", ("pebble_day",),
      parent="pebble", me="pebbox", guide="pebbletag"),
    F("pebblemeldung", "Uhr: Meldungen für Admins", "Watch: notes for admins", "go", ("pebble_alerts", "svc_watch"),
      parent="pebble", me="pebbox", guide="pebblemeldung"),
    F("pebblemerken", "Uhr: Schnell merken", "Watch: quick notes", "go", ("pebble_note", "memory"),
      parent="pebble", me="pebbox", guide="pebblemerken"),
    F("pebbleort", "Uhr: Ort beim Merken", "Watch: place with a note", "go", ("pebble_place", "pebble_note", "memory"),
      parent="pebble", me="pebbox", guide="pebbleort"),
    # Paket 3: the chats on the watch (with reply suggestions), a remote for picked devices, steps, pulse and sleep
    F("pebblechat", "Uhr: Nachrichten", "Watch: messages", "go", ("pebble_chat", "chats"),
      parent="pebble", me="pebbox", guide="pebblechat"),
    F("pebbleantwort", "Uhr: Antwortvorschläge", "Watch: reply suggestions", "go", ("pebble_reply", "pebble_chat", "chats"),
      parent="pebble", me="pebbox", guide="pebbleantwort"),
    F("pebblefern", "Uhr: Fernbedienung", "Watch: remote", "go", ("pebble_remote",),
      parent="pebble", me="pebbox", guide="pebblefern"),
    F("pebblegesund", "Uhr: Schritte, Puls und Schlaf", "Watch: steps, pulse and sleep", "go", ("pebble_health",),
      parent="pebble", me="pebbox", guide="pebblegesund"),
    # spark-tui in a terminal (terminal.py): chat, conversations, Heute and the agent's jobs, paired by a setup line
    F("terminal", "Terminal-Client", "Terminal client", "go", ("terminal",), me="termbox", guide="terminal"),
    # new firmware and app versions for the devices (geraeteupdate.py): overview, notes, speakers at night, XiaoZhi
    F("geraeteupdate", "Geräte-Updates", "Device updates", "go", ("dev_updates",), me="setbox", guide="geraeteupdate"),
    F("geraetenacht", "Lautsprecher nachts aktualisieren", "Update speakers at night", "go", ("dev_updates_night", "esp32"),
      pref="devup_night", parent="geraeteupdate", me="setbox", guide="geraetenacht"),
    F("xiaozhihinweis", "Hinweis auf neue XiaoZhi-Version", "Note on a new XiaoZhi version", "go", ("dev_updates_upstream",),
      parent="geraeteupdate", guide="xiaozhihinweis"),
    F("mcpserver", "Spark als MCP-Server", "Spark as MCP server", "go", ("mcp_server",), me="mcpbox", guide="mcpserver"),
    F("mcpextern", "MCP-Server von außen (OAuth)", "MCP server from outside (OAuth)", "go", ("mcp_server_extern",),
      parent="mcpserver", me="mcpbox", guide="mcpextern"),
    F("mcpact", "MCP: Handeln mit Bestätigung", "MCP: acting with confirmation", "go", ("mcp_server_act",),
      parent="mcpserver", me="mcpbox", guide="mcpact"),
    F("iphone", "iPhone-App", "iPhone app", "go", ("iphone",), me="appbox", guide="iphone"),
    F("iphonepush", "Push an die iPhone-App", "Push to the iPhone app", "go", ("iphone_push",), pref="app_push", parent="iphone",
      me="appbox", guide="iphonepush"),
    F("iphonepanel", "Panel-Bereiche in der iPhone-App", "Panel areas in the iPhone app", "go", ("iphone_panel",),
      parent="iphone", me="appbox", guide="iphonepanel"),
    # appmerken.py: the iPhone and the Android app keep the last state of their profile on the phone (no files, no keys)
    F("appmerken", "Apps merken sich den letzten Stand", "Apps keep the last state", "go", ("app_cache",), guide="appmerken"),
    # pruefzugang.py: Apple's app review pairs with a typed code instead of the 10-minute link
    F("iphonepruef", "Prüfzugang für die iPhone-App", "Review access for the iPhone app", "go", ("iphone_review",),
      parent="iphone", guide="iphonepruef"),
    F("iphoneupdate", "Spark-Update über die iPhone-App", "Spark update from the iPhone app", "go", ("iphone_update",),
      parent="iphone", guide="iphoneupdate"),
    # security
    F("speaker", "Sprechererkennung", "Speaker recognition", "sec", ("speaker_id",), me="voicebox", guide="speaker"),
    F("spkcode", "Codewort am Lautsprecher", "Code word at a speaker", "sec", ("speaker_code", "esp32"),
      parent="speaker", me="espbox", guide="spkcode"),
    F("mfa", "Zweiter Anmeldeschritt", "Second sign-in step", "sec", ("mfa",), me="secbox", guide="mfa"),
    # reports as GitHub issues with anonymized log lines (meldung.py); what goes out is shown before
    F("melden", "Probleme melden", "Reporting problems", "sec", ("report",), me="rpbox", guide="melden"),
    F("meldenadmin", "Admin über Meldungen informieren", "Tell admins about reports", "sec", ("report_notify",),
      parent="melden", me="rpbox", guide="meldenadmin"),
    # verbrauch.py (plan plaene/token-zaehler.md): how much the models do, numbers only; each profile sees its own
    # under Ich → Verbrauch; the quota limits a profile's language model tokens per day, week and month (admins never)
    F("verbrauch", "Verbrauchszähler", "Usage counter", "sec", ("usage_count",), me="usebox", guide="verbrauch"),
    F("kontingent", "Kontingent", "Quota", "sec", ("usage_quota",), parent="verbrauch", me="usebox",
      guide="kontingent"),
    # dienstwacht.py: the Spark looks at its services and tells the admins when one is gone and when it is back
    F("dienstwacht", "Dienst-Wächter", "Service watch", "sec", ("svc_watch",), pref="svc_note", me="setbox", guide="dienstwacht"),
    # rundlauf.py: every few minutes a real round trip (speak, hear, ask the model); told through the Dienst-Wächter
    F("rundlauf", "Rundlauf prüfen", "Round-trip check", "sec", ("rundlauf",), parent="dienstwacht", guide="rundlauf"),
    # wachposten.py: fixed rules on the change log (lockouts, new ways in, protection changed, log changed, quality
    # worse) notify the admins; the Selbst-Notaus (notaus.AUTO) stays apart
    F("wachposten", "Wachposten", "Sentry", "sec", ("wachposten",), guide="wachposten"),
    # wartung.py: while the language model, ASR or TTS is updated the Spark pauses on purpose (fixed sentence, background waits)
    F("wartung", "Wartungspause", "Maintenance pause", "sec", ("wartung",), guide="wartung"),
    F("wartungauto", "Wartungspause bei Neustart", "Maintenance pause on restart", "sec", ("wartung_auto",), parent="wartung",
      guide="wartungauto"),
    # notbetrieb.py: with the models on another computer, Parakeet on this one hears while they are gone (fixed commands)
    F("notbetriebasr", "Notbetrieb mit Parakeet", "Emergency mode with Parakeet", "sec", ("notbetrieb_asr",), guide="notbetriebasr"),
    # gehaeuse.py: the case of a panel computer (Pironman 5): OLED pages for the admin, status LEDs, fan thresholds
    F("gehaeuse", "Gehäuse", "Case", "sec", ("gehaeuse",), guide="gehaeuse"),
    # schirm.py + steuerzentrale.py (B9): the control centre as text on the panel computer's screen (tty1), no desktop
    F("schirm", "Steuerzentrale am Bildschirm", "Control centre on the screen", "sec", ("schirm",), guide="schirm"),
    # modelle.py stage E4: admins switch the model of one kind under Zustand → Modelle (root unit speech-spark-wechsel)
    F("modellwechsel", "Modelle wechseln", "Switch models", "sec", ("modelle_wechseln",), guide="modellwechsel"),
    # modelle.py stage E5: the admin adds own Hugging Face models (language model, image understanding) under fixed rules
    F("modelleeigen", "Eigene Modelle", "Own models", "sec", ("modelle_eigene",), parent="modellwechsel", guide="modelleeigen"),
    # werkstattseite.py + werkstatt.py (plan opencode-werkstatt): test run, code measurement, diagnosis and repairs in a
    # sandbox on the model computer (OpenCode, no data, no internet, no push); admins only, the patch goes to a person
    F("werkstatt", "Werkstatt", "Workshop", "sec", ("werkstatt",), guide="werkstatt"),
    F("werkstattnacht", "Jede Nacht testen", "Test every night", "sec", ("werkstatt_nacht",), parent="werkstatt", guide="werkstattnacht"),
    # angriffsprobe.py: how often the real model would follow an order in outside text (numbers only, nothing runs)
    F("angriffsprobe", "Angriffsprobe", "Attack probe", "sec", ("angriffsprobe",), parent="werkstatt", guide="angriffsprobe"),
    # nas.py (plan plaene/synology-bauplan.md): the places of a profile (NAS or cloud connected once), Ich → Speicher
    F("nas", "Speicher und NAS", "Storage and NAS", "data", ("nas_on",), me="storebox", guide="nas"),
    # speicher.py: a copy of the profile's data at one of its places (WebDAV, SFTP, SMB) or a folder the admin mounted
    F("speicher", "Kopie meiner Daten", "Copy of my data", "data", ("storage_own",), parent="nas", me="storebox", guide="speicher"),
    # nasquelle.py (S2): folders at a place read into the profile's own document search, only reading
    F("nasquelle", "Wissensordner", "Knowledge folders", "data", ("nas_sources",), parent="nas", me="storebox", guide="nasquelle"),
    # nasquelle.py (S5): an admin profile picks one folder at its place "für alle"; every profile finds what is in it
    F("nashaushalt", "Haushaltsordner", "Household folder", "data", ("nas_shared",), parent="nasquelle", me="storebox",
      guide="nashaushalt"),
    # nasablage.py (S4): spark_ablage at a place in the home network; made documents and, after "Ja", own things go
    # into Erstellt/, files put into Eingang/ come into Dokumente; the only folder the Spark writes to
    F("nasablage", "Ablage-Ordner", "Filing folder", "data", ("nas_drop",), parent="nas", me="storebox", guide="nasablage"),
    # naszustand.py (S6): the main admin lets the Spark read how the NAS is doing (SNMPv3); only admin profiles ask
    F("naszustand", "Zustand der NAS", "NAS status", "data", ("nas_status",), parent="nas", guide="naszustand"),
    F("speicherlan", "Speicher im Heimnetz", "Storage in the home network", "data", ("storage_lan",), parent="speicher",
      me="storebox", guide="speicherlan"),
    F("speicherordner", "Ordner auf dem Spark", "Folder on the Spark", "data", ("storage_folder",), parent="speicher",
      me="storebox", guide="speicherordner"),
    F("speicherauslagern", "Originale auslagern", "Move originals out", "data", ("storage_offload",), parent="speicher",
      me="storebox", guide="speicherauslagern"),
    F("dienstnutzer", "Hinweis, wenn ein Dienst fehlt", "Note when a service is missing", "talk", ("svc_watch_users",), parent="dienstwacht", me="setbox", guide="dienstnutzer"),
    # verlauf.py (plan plaene/verlauf-sync.md): the history on every device of the profile
    F("verlaufsync", "Verlauf sofort abgleichen", "Instant history sync", "talk", ("history_live",),
      me="setbox", guide="verlaufsync"),
    F("eingespraech", "Ein Gespräch für alle Kanäle", "One conversation for all channels", "talk", ("history_one",),
      me="setbox", guide="eingespraech"),
    F("offlinelesen", "Verlauf offline lesen", "Read history offline", "talk", ("history_offline",),
      me="setbox", guide="offlinelesen"),
    # Einstellungs-Assistent (faelle.py, berater.py): problems become cases, cases proposals from a fixed catalog
    F("berater", "Einstellungs-Assistent", "Settings assistant", "talk", ("berater",), guide="berater"),
    F("beratererklaeren", "Anfragen erklären", "Explain requests", "talk", ("berater_explain",), parent="berater",
      guide="beratererklaeren"),
    F("beraterchat", "Den Assistenten nach Vorschlägen fragen", "Ask the assistant for proposals", "talk",
      ("berater_chat",), parent="berater", me="setbox", guide="beraterchat"),
    F("beraterhinweis", "Hinweis bei neuem Vorschlag", "Note on a new proposal", "talk", ("berater_notify",),
      pref="berater_note", parent="berater", me="setbox", guide="beraterhinweis"),
    F("beraterissue", "Fälle als Meldung vorbereiten", "Prepare cases as reports", "talk", ("berater_issue",),
      parent="berater", guide="beraterissue"),
    F("beraterauto", "Autopilot für kleine Änderungen", "Autopilot for small changes", "talk", ("berater_auto",),
      parent="berater", guide="beraterauto"),
    F("beraterideen", "Ideen außerhalb des Katalogs", "Ideas outside the catalog", "talk", ("berater_ideas",),
      parent="berater", guide="beraterideen"),
    F("beraterana", "Fall analysieren", "Analyse a case", "talk", ("berater_analyse",),
      parent="berater", guide="beraterana"),
    F("beraterundo", "Automatisch zurücknehmen", "Undo automatically", "talk", ("berater_auto_undo",),
      parent="berater", guide="beraterundo"),
    F("berateru", "Schritte für die Umgebung", "Steps for the environment", "talk", ("berater_env",), parent="berater",
      guide="berateru"),
    F("beratermich", "Vorschläge für mein Profil", "Proposals for my profile", "talk", ("berater_me",),
      parent="berater", me="setbox", guide="beratermich"),
    F("bewerten", "👍/👎 unter Antworten", "👍/👎 under answers", "talk", ("bewerten",), parent="berater",
      me="setbox", guide="bewerten"),
    F("beraterwarum", "„Warum?“ für alle Profile", "\"Why?\" for every profile", "talk", ("berater_why",),
      me="setbox", guide="beraterwarum", parent="berater"),
    F("tagebuch", "Spark-Tagebuch", "Spark diary", "talk", ("tagebuch",), me="setbox", guide="tagebuch"),
    # Zustand per Sprache (zustand_wz.py, plan werkzeug-abdeckung Paket 4): „Läuft alles?“, „Wann wurde gesichert?“
    F("sparkzustand", "Zustand per Sprache", "Status by voice", "talk", ("status_voice",),
      guide="sparkzustand"),
    # Ändern per Sprache (aendern.py, plan werkzeug-abdeckung Paket 6): „Mach das rückgängig“ nach dem Ja
    F("rueckgaengig", "Rückgängig per Sprache", "Undo by voice", "talk", ("undo_voice",),
      guide="rueckgaengig"),
    F("bewertenzurueck", "Rückmeldung, wenn es behoben ist", "Feedback when it is fixed", "talk", ("bewerten_back",),
      pref="rate_back", parent="bewerten", me="setbox", guide="bewertenzurueck"),
)
BY_KEY = {f.key: f for f in FEATURES}
profiles.NO_PRESET.update(f.pref for f in FEATURES if f.pref)
PREFS = {f.pref for f in FEATURES if f.pref}

# Spark-wide conditions besides the switches (an address that must be set), registered by the module
# that knows them, so this file imports none of them: key -> function(chat config) -> bool
def _naszustand_set_up(c):
    import naszustand
    return naszustand.set_up(c)


def _docling_set_up(c):
    import doclingdienst
    return doclingdienst.set_up(c)


READY = {"beraterissue": lambda c: admin_on("melden", c),   # a case as a report needs „Probleme melden“
         "docling": _docling_set_up,                          # the Docling server needs its address
         "bilder": lambda c: bool(load_config("image").get("enabled")),   # the picture model installed (install.sh --bild)
         "musik": lambda c: bool(load_config("music").get("enabled")),    # the music model installed (install.sh --musik)
         "naszustand": _naszustand_set_up}                    # the NAS status needs its host and SNMP user
# extra per-profile conditions given by the admin (the agent level): key -> function(uid) -> bool
GRANTED = {}
# a profile's own stored data of a function, registered by the module that keeps it: key -> (count(uid) -> int,
# clear(uid) -> None or an awaitable). While the admin blocks the function for the profile, Ich shows only „Daten
# löschen“ in place of its page (account.whoami "locked", DELETE /api/profile/owndata/{key}; Dominik 2026-10-14).
# count is a number of entries, never contents; clear removes exactly what the function's own delete routes remove.
OWN = {}
# the second step a profile still owes before using a function (join.py, new profiles by invitation):
# function(uid, key) -> bool, set by join.py
DUTY = None
# pruefzugang.py: uid -> the functions blocked for a profile with a review access for Apple (features.blocked)
REVIEW = None

# chat.* switches that are no function a profile uses (how the Spark itself works)
SPARK_ONLY = {"wachposten", "public", "thinking", "prompt_cache", "answer_check", "answer_check_more", "action_check", "loop_stop", "datetime", "face_life", "esp32_ota_http", "wartung", "wartungauto", "notbetriebasr", "gehaeuse", "schirm", "rundlauf", "modellwechsel", "modelleeigen", "werkstatt", "werkstattnacht", "angriffsprobe", "weicheabstimmen"}
# Everything starts off (Dominik 2026-10-08). The only values shipped on in config.default.json are protection and
# stability rules and the basic functions the Spark had from the start, each with its reason here (Dominik 2026-10-12,
# docs/de/richtlinien.md, part 3). tests/test_richtlinie.py fails for a value shipped on that is not listed.
# chat.defaults are presets of a profile's own manners (hands-free, barge-in …), not functions: they never switch
# a function on (test_features.test_presets_never_switch_a_function_on).
DEFAULT_ON = {
    "asr.enabled": "Hören ist die Grundaufgabe des Sparks",
    "tts.enabled": "Sprechen ist die Grundaufgabe des Sparks",
    "tts.clean_text": "Qualität: Emojis, Code und Markdown werden nicht vorgelesen",
    "tts.calm": "Qualität: ruhig sprechen ohne Ausrufe",
    "memory.guard": "Stabilität: Speicherwächter vor dem Speicherende von DGX OS",
    "watch.watchdog": "Stabilität: hängende Dienste starten neu",
    "chat.answer_check": "Schutz: erfundene Zahlen und Zeiten werden nicht gesagt",
    "chat.action_check": "Schutz (Dominik 2026-10-12): eine Tat, die kein Werkzeug geschafft hat, wird nicht behauptet",
    "chat.loop_stop": "Schutz (Dominik 2026-10-12): ein Werkzeug mit gleichem Fehler läuft kein drittes Mal",
    "chat.datetime": "Grundfunktion: das Modell kennt Datum und Uhrzeit, keine persönlichen Daten",
    "chat.memory": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.history": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.documents": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.reminders": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.calendar": "Grundfunktion von Anfang an, braucht trotzdem einen eigenen Kalender des Profils",
    "chat.esp32_ota_http": "Dominik 2026-10-11: Lautsprecher-Updates über http bleiben erlaubt (sonst nur per USB)",
}
# Grundausstattung (Dominik 2026-10-17, plan grundeinstellungen/plan.md): what makes a newcomer's chat good from the
# first question. Only what needs no setup, stays in the Spark (no host outside, netguard), loads no extra model and
# concerns only the profile itself (test_grundausstattung); guests still only ask and get answers. A new installation
# starts with it on (config.default.json, each with its reason here instead of DEFAULT_ON); an existing one keeps its
# switches until the admin takes it over on Funktionen („Alle übernehmen“, POST /api/admin/grundausstattung).
GRUNDAUSSTATTUNG = {
    "chat.routing": "Gespräch: feste Regeln zeigen dem Modell nur die passenden Werkzeuge",
    "chat.direct_read": "Gespräch: klare Lesefragen holt das Panel selbst, eine Runde weniger",
    "chat.instant_ack": "Gespräch: ein kurzer Satz sofort statt Stille bis zur Antwort",
    "chat.prefetch": "Gespräch: bei einer Rückfrage liegen die Daten für die nächste Antwort schon bereit",
    "chat.klaeren": "Gespräch: bei mehreren passenden Geräten fragt er statt zu raten",
    "chat.klaeren_merken": "Gespräch: die Auswahl aus einer Rückfrage gilt beim nächsten Mal",
    "chat.follow_up": "Gespräch: „Und morgen?“ geht ohne neues Weckwort",
    "chat.undo_voice": "Gespräch: „Mach das rückgängig“ nimmt die letzte Tat nach einem Ja zurück",
    "chat.learn_fixes": "Gespräch: aus Korrekturen wird ein Gedächtnis-Eintrag, erst nach dem Ja",
    "chat.face_life": "Gespräch: das Gesicht zeigt, was der Spark gerade tut",
    "chat.spark_help": "Finden: Fragen zum Spark beantwortet er aus Anleitung und Schaltern, mit dem Weg",
    "chat.spark_drawer": "Finden: „Frag Spark“ auf jeder Seite",
    "chat.feature_tips": "Finden: er nennt Funktionen, die zur Frage passen",
    "chat.feature_sentences": "Finden: „Probier mal“ und „Das kannst du auch sagen“ mit Sätzen, die bei dir gehen",
    "chat.tasks": "Alltag: Einkaufsliste und Aufgaben auf dem Spark, ohne Konto",
    "chat.history_live": "Alltag: der Verlauf steht sofort auf allen eigenen Geräten",
    "chat.app_cache": "Alltag: die Apps zeigen beim Öffnen gleich den letzten Stand, nur auf dem eigenen Handy",
}
# the part that needs the internet: never shipped on, only by the admin's answer to „Darf der Spark ins Internet?“
# on Funktionen (chat.grund_internet keeps the answer); the web search only once a SearXNG address is stored
GRUND_INTERNET = ("chat.weather", "chat.wiki", "chat.search", "chat.svc_watch")


def grund_state(c=None):
    """The card on Funktionen and the app's Funktionen page: which switches of each part are on, and the answer to
    the internet question. Switch names only, never a value from the settings."""
    c = c if c is not None else chat_cfg()
    on = lambda keys: [k for k in keys if _switch(c, k.split(".", 1)[1])]   # noqa: E731
    return {"basis": {"keys": list(GRUNDAUSSTATTUNG), "on": on(GRUNDAUSSTATTUNG)},
            "internet": {"keys": list(GRUND_INTERNET), "on": on(GRUND_INTERNET),
                         "frage": c.get("grund_internet") if c.get("grund_internet") in ("ja", "nein") else "offen",
                         "search_url": bool(str(c.get("search_url") or "").strip())},
            "names": {k: list(switch_name(k.split(".", 1)[1])) for k in (*GRUNDAUSSTATTUNG, *GRUND_INTERNET)}}
# names for the Spark-wide switches that are no function of their own (the app's Funktionen page shows them under "Spark")
SPARK_NAMES = {"public": ("Gastzugang", "Guest access"), "thinking": ("Vorher nachdenken", "Think first"),
               "prompt_cache": ("Schneller Antwortbeginn", "Faster first words"),
               "answer_check": ("Antworten prüfen", "Check answers"),
               "answer_check_more": ("Antwort-Prüfung erweitern", "Extended answer check"),
               "action_check": ("Taten prüfen", "Check deeds"), "loop_stop": ("Fehlerschleife stoppen", "Stop error loops"), "datetime": ("Datum und Uhrzeit mitgeben", "Pass date and time"),
               "face_life": ("Gesicht zeigt, was es tut", "Face shows what it does")}


def switch_names(keys):
    """For the app (GET /api/admin/switches): a name per admin switch and the groups in menu order, from this
    table, so the app keeps no list of its own. A switch shared by several functions takes the first one's name."""
    names, groups = {}, {g: [] for g, _, _ in GROUPS}
    for f in FEATURES:
        k = f.admin[0]
        if k in keys and k not in names:
            names[k] = [f.de, f.en]
            groups[f.group].append(k)
    for k, (de, en) in SPARK_NAMES.items():
        if k in keys and k not in names:
            names[k] = [de, en]
    return names, [{"key": g, "name": [de, en], "switches": groups[g]} for g, de, en in GROUPS if groups[g]]


def _defaults():
    try:
        with open(DEFAULTS) as f:
            return json.load(f).get("chat", {})
    except (OSError, ValueError):
        return {}


_DEF = _defaults()


def chat_cfg():
    """The chat section; common.load_config fills every missing key with the shipped default."""
    return load_config().get("chat", {})


def _switch(c, k):
    return c.get(k, _DEF.get(k, False)) is True


def admin_on(key, c=None):
    """The Spark allows it: its switches, the ones of the function it builds on, and what must be set up."""
    f = BY_KEY[key]
    c = chat_cfg() if c is None else c
    if not all(_switch(c, k) for k in f.admin):
        return False
    if f.parent and not admin_on(f.parent, c):
        return False
    ready = READY.get(key)
    return bool(ready(c)) if ready else True


def pref_on(key, uid, s=None):
    """The profile's own preference for something the Spark does unasked (True when the function has none, and
    unless the profile switched it off). Never from the admin's presets."""
    f = BY_KEY[key]
    if not f.pref:
        return True
    s = profiles.settings(uid) if s is None else s
    return s.get(f.pref, profiles.SETTINGS[f.pref][0]) is not False


def blocked(key, uid, c=None):
    """The admin blocked the function for this profile (chat.deny, Personen und Geräte → Gesperrte Funktionen): the function or
    one it builds on. A profile can never change this itself, it is not in its settings."""
    c = chat_cfg() if c is None else c
    deny = c.get("deny") if isinstance(c.get("deny"), dict) else {}
    review = REVIEW(uid) if REVIEW else ()
    return any(uid in (deny.get(k) or ()) or k in review for k in chain(key) if k not in NO_BLOCK)


# never blocked for a single profile: a profile must always be able to set up its second step (Dominik 2026-10-13)
NO_BLOCK = {"mfa"}
MAX_DENY = 2000   # blocked profiles per function (Gesperrte Funktionen): the whole household, a bound for the config


def clean_deny(deny):
    """chat.deny without what is gone (a removed function, a deleted profile, doubles): an old entry never blocks
    saving the admin settings."""
    deny = deny if isinstance(deny, dict) else {}
    have = set(profiles.user_ids())
    out = {}
    for k, v in deny.items():
        if k in BY_KEY and k not in NO_BLOCK and isinstance(v, list):
            ids = list(dict.fromkeys(u for u in v if isinstance(u, str) and u in have))[:MAX_DENY]
            if ids:
                out[k] = ids
    return out


def profile_on(key, uid, s=None, c=None):
    """What holds for this profile besides the Spark's switches: not blocked by the admin, its preference (where
    there is one) and what the admin granted it (the agent level)."""
    if not uid or blocked(key, uid, c) or not pref_on(key, uid, s):
        return False
    grant = GRANTED.get(key)
    return bool(grant(uid)) if grant else True


def reason(key, uid, c=None, s=None):
    """Why it cannot be used: "spark" (admin switch), "guest", "blocked" (the admin blocked it for this profile),
    "profile" (the profile switched its preference off), "mfa" (the second step first, join.py) or None."""
    if not admin_on(key, c):
        return "spark"
    if not uid:   # guests only get questions and answers, no function at all (Dominik 2026-10-13)
        return "guest"
    if blocked(key, uid, c):
        return "blocked"
    if not profile_on(key, uid, s, c):
        return "profile"
    return "mfa" if DUTY and DUTY(uid, key) else None


def allowed(key, uid, c=None, s=None):
    return reason(key, uid, c, s) is None


def count(uid, c=None):
    """(on, of) for Personen und Geräte: of the functions the Spark allows, how many this profile may use."""
    c = chat_cfg() if c is None else c
    s = profiles.settings(uid)
    mine = [f for f in FEATURES if admin_on(f.key, c)]
    return sum(1 for f in mine if profile_on(f.key, uid, s, c)), len(mine)


def guests(c=None):
    """What guests get: the guest access switch. With it they only ask and get answers, never a function or a tool
    (Dominik 2026-10-13: "einfach bloß Frage, Antwort")."""
    c = chat_cfg() if c is None else c
    return {"public": _switch(c, "public")}


WHY = {"spark": ("Vom Admin ausgeschaltet", "Switched off by the admin"),
       "guest": ("Nur mit Profil", "Only with a profile"),
       "blocked": ("Vom Admin für dich gesperrt", "Blocked for you by the admin"),
       "profile": ("Von dir ausgeschaltet", "Switched off by you"),
       "mfa": ("Erst den zweiten Anmeldeschritt einrichten (Ich → Sicherheit)", "Set up the second sign-in step first (Me → Security)")}


def state(uid, c=None):
    """Every function with what the Spark and the profile may: for Ich, the app and the search.
    Guests get none: they only ask and get answers."""
    c = chat_cfg() if c is None else c
    s = profiles.settings(uid) if uid else {}
    out = []
    for f in FEATURES:
        if not uid:
            break
        why = reason(f.key, uid, c, s)
        out.append({"key": f.key, "name": [f.de, f.en], "group": f.group, "spark": admin_on(f.key, c),
                    "own": f.pref or None, "mine": pref_on(f.key, uid, s) if f.pref else None,
                    "can": why is None, "why": why, "parent": f.parent or None,
                    "me": f.me or None, "guide": f.guide or None})
    return out


def stamp(uid, c=None):
    """A short fingerprint of what this profile (or a guest) may use right now and of its own switches. The
    pages and apps compare it with the one they started with (/api/whoami, /api/features), so a change under
    Wer darf was or on another device arrives without reloading by hand. Says nothing about the content."""
    st = state(uid, c)
    raw = json.dumps([(x["key"], x["why"], x["mine"]) for x in st], separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- what a function needs (Voraussetzungen)
# Dominik 2026-10-12: "wenn jemand Funktionen einschaltet, die andere voraussetzen, auch mit einschalten". The chain
# of a function is the functions it builds on (parent, the parent's parent ...) and itself; the Spark switches
# of that chain must all be on. The pages ask before switching on what is missing, and say what goes off with it.
def chain(key):
    """The functions key builds on, the first one first, key last."""
    out, k = [], key
    while k and k in BY_KEY and k not in out:
        out.insert(0, k)
        k = BY_KEY[k].parent
    return out


def chain_switches(key):
    """Every Spark switch (chat.*) the function needs, in the order of its chain."""
    out = []
    for k in chain(key):
        for sw in BY_KEY[k].admin:
            if sw not in out:
                out.append(sw)
    return out


def switch_name(sw):
    """(de, en) of a Spark switch: the function it belongs to, else its own name."""
    for f in FEATURES:
        if f.admin[0] == sw:
            return f.de, f.en
    if sw in SPARK_NAMES:
        return SPARK_NAMES[sw]
    names, _ = switch_names({sw})
    n = names.get(sw)
    return (n[0], n[1]) if isinstance(n, (list, tuple)) and len(n) == 2 else (sw, sw)


def missing(key, c=None):
    """The Spark switches of key's chain that are off."""
    c = chat_cfg() if c is None else c
    return [sw for sw in chain_switches(key) if not _switch(c, sw)]


def unready(key, c=None):
    """Functions of the chain whose switches may be on but which still need setting up (an address ...)."""
    c = chat_cfg() if c is None else c
    return [k for k in chain(key) if READY.get(k) and not READY[k](c)]


def affected(sw, c=None):
    """The functions that are on now and go off with the Spark switch sw (not the one sw belongs to itself)."""
    c = chat_cfg() if c is None else c
    return [f.key for f in FEATURES if f.admin[0] != sw and sw in chain_switches(f.key) and admin_on(f.key, c)]


def admin_way(key, lang="de"):
    f = BY_KEY[key]
    return ("Funktionen → " if lang == "de" else "Features → ") + (f.de if lang == "de" else f.en)


def switch_way(sw, lang="de"):
    for f in FEATURES:
        if f.admin[0] == sw:
            return admin_way(f.key, lang)
    return ("Funktionen → " if lang == "de" else "Features → ") + switch_name(sw)[0 if lang == "de" else 1]


def me_way(key, lang="de"):
    """Where the profile sets it up or changes its preference: Ich → <page> „<name>“ (way.js marks the row)."""
    f = BY_KEY[key]
    import hilfe
    head = hilfe.page_name("me/" + (f.me or "setbox"), lang) or hilfe.page_name("me/setbox", lang)
    return f"{head} „{f.de if lang == 'de' else f.en}“"


def missing_text(key, uid, lang="de", c=None):
    """One plain sentence with everything that is missing for uid, each with its way; "" when it can be used."""
    c = chat_cfg() if c is None else c
    li = 0 if lang == "de" else 1
    f = BY_KEY[key]
    out = []
    sws = missing(key, c)
    if sws:
        ways = ", ".join(switch_way(sw, lang) for sw in sws)
        out.append(("Der Admin muss einschalten: " if li == 0 else "The admin has to switch on: ") + ways + ".")
    setup = [k for k in unready(key, c) if not any(sw in missing(k, c) for sw in BY_KEY[k].admin)]
    if setup:
        out.append(("Noch einzurichten: " if li == 0 else "Still to set up: ") + ", ".join(admin_way(k, lang) for k in setup) + ".")
    if uid and blocked(key, uid, c):
        out.append("Der Admin hat es für dich gesperrt (Personen und Geräte → Gesperrte Funktionen)." if li == 0
                   else "The admin blocked it for you (People and devices → Blocked functions).")
    elif uid and f.pref and not pref_on(key, uid):
        out.append(("Du hast es ausgeschaltet: " if li == 0 else "You switched it off: ") + me_way(key, lang) + ".")
    return " ".join(out)


router = APIRouter()


@router.get("/api/features", dependencies=[Depends(assistant)])
def features_list(request: Request):
    """What may be used here and why not: one list for Ich, the app and the search."""
    prof = profiles.current(request)
    guard.limit(request, "features", prof and prof["id"])
    if prof:   # the app opened: its calendars and mail are read ahead in the background (vorwaermen.py)
        import vorwaermen
        vorwaermen.ask(prof["id"])
    return {"groups": [{"key": k, "name": [de, en]} for k, de, en in GROUPS],
            "features": state(prof["id"] if prof else None), "why": WHY, "stamp": stamp(prof["id"] if prof else None),
            "pages": app_pages(prof["id"] if prof else None)}


def app_pages(uid):
    """The pages an app lists for this profile, in the panel's order: the pages of their own (OWN_PAGES) and the
    Ich pages but APP_SKIP with at least one function this profile may use, and the pages of ME_ALWAYS.
    Guests get none: they only ask and get answers."""
    if not uid:
        return []
    c, s = chat_cfg(), profiles.settings(uid)
    out = []
    for key, de, en in tuple((k, de, en) for k, _, de, en in OWN_PAGES) + ME_PAGES:
        if key in APP_SKIP:
            continue
        mine = [f for f in FEATURES if f.me == key]
        if key not in ME_ALWAYS and not any(reason(f.key, uid, c, s) in (None, "profile", "mfa") for f in mine):
            continue
        out.append({"id": key, "name": [de, en]})
    return out


# ---------------------------------------------------------------- Personen und Geräte → Gesperrte Funktionen (admin)
_UID = re.compile(r"u_[0-9a-f]{12}")
SEEN = os.path.join(STATE, "features-seen.json")


def _seen(c):
    """When each function was first on on this Spark: tipps.py shows „neu freigegeben“ for NEW_DAYS after it."""
    try:
        with open(SEEN) as f:
            d = json.load(f)
        d = {k: int(v) for k, v in d.items() if k in BY_KEY and isinstance(v, (int, float))} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    new = {f.key: int(time.time()) for f in FEATURES if f.key not in d and admin_on(f.key, c)}
    if new:
        d.update(new)
        try:
            write_json(SEEN, d)
        except OSError:
            pass
    return d


def matrix():
    """Personen und Geräte → Gesperrte Funktionen (only the blocked ones), „Wer darf es“ in each function, the switch chain on
    Funktionen (needs.js), the tiles under Apps and the iPhone app's profile page."""
    c = chat_cfg()
    users = profiles.names()
    import coadmin
    deny = c.get("deny") if isinstance(c.get("deny"), dict) else {}
    rows = []
    for f in FEATURES:
        rows.append({"key": f.key, "name": [f.de, f.en], "switch": f.admin[0], "spark": admin_on(f.key, c),
                     "blockable": f.key not in NO_BLOCK,
                     # per profile: may it use it (True), blocked here by the admin (False) or through a function it builds on
                     "cells": {u["id"]: u["id"] not in (deny.get(f.key) or ()) for u in users},
                     "inherited": {u["id"]: blocked(f.key, u["id"], c) and u["id"] not in (deny.get(f.key) or ()) for u in users},
                     "chain": chain_switches(f.key)})
    every = sorted({sw for f in FEATURES for sw in f.admin})
    return {"features": rows,
            "profiles": [{"id": u["id"], "name": u["name"], "role": coadmin.role(u["id"])} for u in users],
            "states": {sw: _switch(c, sw) for sw in every}, "snames": {sw: list(switch_name(sw)) for sw in every}}


@router.get("/api/admin/features", dependencies=[Depends(auth)])
def admin_features(request: Request):
    guard.limit(request, "features", admin=True)
    return matrix()


@router.put("/api/admin/features/{key}/profiles/{uid}", dependencies=[Depends(auth)])
async def admin_feature_profile(key: str, uid: str, request: Request):
    """The admin blocks a function for one profile, or lifts the block ({"on": false} blocks, {"on": true} allows
    again). Stored in config.json chat.deny, which only the admin writes: the profile cannot lift it itself. A
    Verwalter only lifts blocks (Dominik 2026-10-14): blocking stays with the admin."""
    guard.limit(request, "features", admin=True)
    f = BY_KEY.get(key)
    if not f or not _UID.fullmatch(uid) or not profiles.by_id(uid):
        raise HTTPException(404, "no such function or profile")
    if key in NO_BLOCK:
        raise HTTPException(400, "not blockable")
    on = (await json_body(request, 256)).get("on")
    if not isinstance(on, bool):
        raise HTTPException(400, "on: true or false")
    import admin
    elev = acting_profile(request)
    if not on and elev and elev.get("role") == "manager":
        guard.log("feature_profile", uid=uid, by=elev["id"], detail=f"{f.de}: Sperren nur durch den Admin, abgelehnt")
        raise HTTPException(403, "only the admin blocks a function for a profile")
    admin._no_admin_profile(request, uid)
    with admin._save_lock:   # one config write at a time (admin._save)
        new = admin.get_config()
        deny = {k: [u for u in v if not (k == key and u == uid)] for k, v in (new["chat"].get("deny") or {}).items()}
        if not on:
            deny[key] = deny.get(key, []) + [uid]
        new["chat"]["deny"] = {k: v for k, v in deny.items() if v}
        old = admin.validate(new)
        write_json(admin.CONFIG_PATH, new, indent=2)
    admin.undo.record(old, new, admin._by(request), admin.SENSITIVE)
    guard.log("feature_profile", uid=uid, by="main" if not elev else elev["id"],
              detail=f"{f.de} für {profiles.by_id(uid)['name']} {'erlaubt' if on else 'gesperrt'}")
    return {"key": key, "uid": uid, "on": on}
