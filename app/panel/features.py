"""One description per function (plan „Vereinheitlichen“, V01.0.267).

Every function the admin can switch is written down here once: its name on every page, its group,
the admin switches it needs (and the functions it builds on), the profile's own switch, whether
guests may ever use it and the Ich page it belongs to. The modules ask `admin_on`, `profile_on` and
`allowed` here instead of each building "admin on and profile on" itself, and the panel, the iPhone
app and the search read `/api/features` instead of keeping their own lists.

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
from common import load_config, write_json
from core import assistant, auth

DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.default.json")

# groups as on the Funktionen page (guides.js GGROUPS)
GROUPS = (("talk", "Gespräch", "Conversation"), ("speed", "Tempo und Genauigkeit", "Speed and accuracy"),
          ("data", "Wissen und Gedächtnis", "Knowledge and memory"),
          ("day", "Alltag", "Everyday"), ("post", "Post und Kontakte", "Mail and contacts"),
          ("home", "Zuhause", "Home"), ("go", "Unterwegs und Geräte", "On the go and devices"),
          ("sec", "Sicherheit", "Security"))


class Feature(NamedTuple):
    key: str
    de: str
    en: str
    group: str
    admin: tuple            # chat.* switches that must all be on
    profile: str = ""       # the profile's own switch in settings.json ("" = none: the admin's switch is enough)
    guests: bool = False    # may guests (no profile) ever use it
    parent: str = ""        # the function it builds on (its switch must be on too)
    me: str = ""            # the Ich page (tab id) where the profile sets it up
    guide: str = ""         # guides.js id


F = Feature
FEATURES = (
    # conversation
    F("search", "Websuche", "Web search", "talk", ("search",), guests=True, guide="search"),
    F("wiki", "Wikipedia direkt", "Wikipedia straight away", "talk", ("wiki",), "wiki_on", me="setbox", guide="wiki"),
    F("kiwix", "Eigenes Kiwix-Archiv", "Own Kiwix archive", "talk", ("kiwix",), "kiwix_on", me="setbox", guide="kiwix"),
    F("lokal", "Erst lokal suchen", "Look locally first", "talk", ("local_first",), "local_first", me="setbox", guide="lokal"),
    F("roles", "Rollen per Sprache", "Roles by voice", "talk", ("roles",), "roles_on", me="setbox", guide="roles"),
    F("style", "Eigener Gesprächsstil", "Own conversation style", "talk", ("own_style",), me="setbox", guide="style"),
    F("follow", "Rückfrage ohne Weckwort", "Follow-up without wake word", "talk", ("follow_up",), me="setbox", guide="follow"),
    F("selfecho", "Eigene Stimme überhören", "Ignore my own voice", "talk", ("no_self_echo",), me="setbox", guide="selfecho"),
    F("fixes", "Aus Korrekturen lernen", "Learning from corrections", "talk", ("learn_fixes",), "fix_learn",
      parent="memory", me="setbox", guide="fixes"),
    F("klaeren", "Rückfrage statt Raten", "Ask instead of guessing", "talk", ("klaeren",), "klaeren", me="setbox",
      guide="klaeren"),
    F("klaerenmerken", "Auswahl merken", "Remember the choice", "talk", ("klaeren_merken",), "klaeren_merken",
      parent="klaeren", me="setbox", guide="klaerenmerken"),
    F("images", "Bilder erkennen", "Picture recognition", "talk", ("images",), "images_on", me="setbox", guide="images"),
    F("toolthink", "Bei der Werkzeugwahl nachdenken", "Thinking while choosing tools", "speed", ("tool_thinking",), "tool_think",
      me="setbox", guide="toolthink"),
    F("routing", "Gezielte Werkzeugwahl", "Targeted tool choice", "speed", ("routing",), "route", me="setbox", guide="routing"),
    F("direct", "Eindeutiges direkt abrufen", "Fetch clear questions directly", "speed", ("direct_read",), "direct_read",
      me="setbox", guide="direct"),
    F("ack", "Sofortige Rückmeldung", "Instant acknowledgement", "speed", ("instant_ack",), "instant_ack",
      parent="routing", me="setbox", guide="ack"),
    F("vorab", "Vorab holen bei Rückfrage", "Fetch ahead on a question back", "speed", ("prefetch",), "prefetch",
      parent="routing", me="setbox", guide="vorab"),
    F("hilfe", "Hilfe zum Spark", "Help with the Spark", "talk", ("spark_help",), "spark_help", me="setbox", guide="hilfe"),
    F("hilfevorschlag", "Einstellungen vorschlagen", "Suggesting settings", "talk", ("spark_suggest",), "spark_help",
      parent="hilfe", me="setbox", guide="hilfevorschlag"),
    F("hilfeseite", "Frag Spark auf jeder Seite", "Ask Spark on every page", "talk", ("spark_drawer",), "spark_help",
      parent="hilfe", me="setbox", guide="hilfeseite"),
    # tipps.py: the assistant points out a function that would help and helps setting it up
    F("tipps", "Funktionen vorschlagen", "Suggesting functions", "talk", ("feature_tips",), "tips_on",
      parent="hilfe", me="setbox", guide="tipps"),
    F("tippspush", "Funktionen vorschlagen von selbst", "Suggesting functions by itself", "day",
      ("feature_tips_push", "feature_tips"), "pro_tips", parent="proactive", me="probox", guide="tippspush"),
    # qwen38's /v1/systemone (systemone.py): probabilities instead of words, the panel decides with fixed thresholds
    F("einordnung", "Einordnung mit Wahrscheinlichkeit", "Classification with probabilities", "speed", ("systemone",),
      "systemone_on", me="setbox", guide="einordnung"),
    F("einordnungpost", "Einordnung beim Postfach aufräumen", "Classification when tidying the inbox", "speed",
      ("systemone_tidy", "mail_tidy", "mail"), "systemone_on", parent="einordnung", me="setbox", guide="einordnungpost"),
    F("einordnungtest", "Einordnung im Qualitätstest", "Classification in the quality test", "speed", ("systemone_quality",),
      parent="einordnung", guide="einordnungtest"),
    F("vorrang", "Vorrang für Personen", "Priority for people", "talk", ("person_priority",), guide="vorrang"),
    # knowledge and memory
    F("memory", "Gedächtnis", "Memory", "data", ("memory",), me="factbox", guide="memory"),
    # gedaechtnis.py (plan gedaechtnis-pruefen/plan.md): evidence per fact, fixed rules mark what may be out of date
    F("gedpruefen", "Gedächtnis prüfen", "Memory check", "data", ("memory_check",), "mem_check", parent="memory",
      me="factbox", guide="gedpruefen"),
    F("gedfragen", "Nachfrage zum Gedächtnis", "Memory check-back", "data", ("memory_ask",), "mem_ask",
      parent="gedpruefen", me="setbox", guide="gedfragen"),
    F("gedthemen", "Themen im Gedächtnis", "Memory topics", "data", ("memory_topics",), "mem_topics",
      parent="gedpruefen", me="factbox", guide="gedthemen"),
    F("history", "Frühere Gespräche", "Past conversations", "data", ("history",), me="setbox", guide="history"),
    F("documents", "Eigene Dokumente", "Own documents", "data", ("documents",), me="docbox", guide="documents"),
    F("docpics", "Bilder und Scans lesen", "Read pictures and scans", "data", ("doc_pictures",), "doc_pictures",
      parent="documents", me="docbox", guide="docpics"),
    F("docmeaning", "Bedeutungssuche", "Meaning search", "data", ("doc_semantic",), "doc_semantic",
      parent="documents", me="docbox", guide="docmeaning"),
    F("docfiles", "Originale aufbewahren", "Keep originals", "data", ("doc_originals",), "doc_originals",
      parent="documents", me="docbox", guide="docfiles"),
    F("docnight", "Lange Dokumente nachts lesen", "Read long documents at night", "data", ("doc_night",),
      parent="documents", me="docbox", guide="docnight"),
    F("docshared", "Gemeinsame Dokumente", "Shared documents", "data", ("doc_shared",), "doc_shared",
      parent="documents", me="docbox", guide="docshared"),
    F("remarkable", "reMarkable-Notizen", "reMarkable notes", "data", ("remarkable",), "rm_on",
      parent="docpics", me="rmbox", guide="remarkable"),
    F("rmsend", "Aufs reMarkable schicken", "Sending to the reMarkable", "data", ("remarkable_send",), "rm_send",
      parent="remarkable", me="rmbox", guide="rmsend"),
    F("rmfresh", "Neueste zuerst", "Newest first", "data", ("remarkable_fresh",), "rm_fresh",
      parent="remarkable", me="rmbox", guide="rmfresh"),
    F("rmmorning", "Morgenblatt", "Morning sheet", "data", ("remarkable_plus",), "rm_morning", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmask", "@Spark auf Papier", "@Spark on paper", "data", ("remarkable_plus",), "rm_ask", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmtodo", "Aufgaben vom reMarkable", "Tasks from the reMarkable", "data", ("remarkable_plus",), "rm_todo", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmmeet", "Besprechungen zusammenfassen", "Meeting summaries", "data", ("remarkable_plus",), "rm_meet", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmweek", "Wochenrückblick", "Week in review", "data", ("remarkable_plus",), "rm_week", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmweb", "Webseiten und Anhänge aufs reMarkable", "Web pages and attachments to the reMarkable", "data", ("remarkable_plus",), "rm_web", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rminbox", "Eingang pro Tag", "Daily inbox", "data", ("remarkable_plus",), "rm_inbox", parent="rmsend", me="rmbox", guide="rmplus"),
    F("rmguide", "Spark-Anleitung auf dem reMarkable", "Spark guide on the reMarkable", "data", ("remarkable_plus",), "rm_guide", parent="rmsend", me="rmbox", guide="rmplus"),
    # Dokumente erstellen (docmake.py, plan dokumente-erstellen): letters, presentations, tables ... as files
    F("erstellen", "Dokumente erstellen", "Creating documents", "data", ("doc_make",), "doc_make",
      parent="documents", me="docbox", guide="erstellen"),
    F("erstellenvorlagen", "Eigene Vorlagen", "Own templates", "data", ("doc_make_templates",), "doc_make_templates",
      parent="erstellen", me="docbox", guide="erstellenvorlagen"),
    # pictures for slides from the own Kiwix (docmake.wiki_pictures; Präsentationen professionell, point 5)
    F("erstellenbilder", "Bilder aus dem Kiwix", "Pictures from the Kiwix", "data", ("doc_make_wikipics",), "doc_make_wikipics",
      parent="erstellen", me="docbox", guide="erstellenbilder"),
    F("docbrief", "Steckbrief und Tags", "Document card and tags", "data", ("doc_brief",), "doc_brief",
      parent="documents", me="docbox", guide="docbrief"),
    # everyday
    F("proactive", "Von selbst melden", "Speaking up by itself", "day", ("proactive",), "pro_on", me="probox", guide="proactive"),
    # Home Assistant tells the Spark (hamelden.py): each part below "Von selbst melden"
    F("halive", "Sofort-Meldungen aus Home Assistant", "Instant notes from Home Assistant", "day", ("ha_live", "homeassistant"),
      "pro_ha_live", parent="proactive", me="probox", guide="halive"),
    F("haloud", "Haus-Meldungen über Lautsprecher", "House notes on speakers", "day",
      ("ha_loud", "homeassistant", "messages_announce"), "pro_ha_loud", parent="proactive", me="probox", guide="haloud"),
    F("haevent", "Home Assistant meldet an Spark", "Home Assistant tells the Spark", "day", ("ha_events", "homeassistant"),
      "pro_ha_events", parent="proactive", me="probox", guide="haevent"),
    F("havoice", "Smart-Home-Regel per Sprache", "Smart home rule by voice", "day", ("ha_voice_rules", "homeassistant"),
      "pro_ha_voice", parent="proactive", me="probox", guide="havoice"),
    F("mailwichtig", "Wichtige Mails erkennen", "Recognize important mail", "day", ("systemone_mail", "systemone", "mail"),
      "pro_mail_smart", parent="proactive", me="probox", guide="mailwichtig"),
    F("hacam", "Kamerabild beschreiben", "Describe a camera picture", "day", ("ha_camera", "homeassistant"),
      "pro_ha_cam", parent="proactive", me="probox", guide="hacam"),
    F("reminders", "Timer und Erinnerungen", "Timers and reminders", "day", ("reminders",), guests=True, guide="reminders"),
    F("tasks", "Aufgaben und Einkaufsliste", "Tasks and shopping list", "day", ("tasks",), "tasks_on", me="taskbox", guide="tasks"),
    F("mystatus", "Mein Zustand", "My status", "day", ("my_status",), "my_status", me="bgbox", guide="mystatus"),
    F("agent", "Agent-Funktionen", "Agent functions", "day", ("agent",), "agent_on", me="agentbox", guide="agent"),
    F("mcp", "Dienste per MCP", "Services over MCP", "day", ("agent_mcp",), parent="agent", guide="mcp"),
    # each profile its own MCP services (meinmcp.py); needs no agent level, only the switches
    F("mymcp", "Eigene MCP-Dienste", "Own MCP services", "day", ("mcp_own",), "mymcp_on", parent="mcp", me="mymcpbox",
      guide="mymcp"),
    F("mymcpjobs", "Eigene MCP-Dienste in Aufträgen", "Own MCP services in jobs", "day", ("mcp_own_jobs",), "mymcp_on",
      parent="mymcp", me="mymcpbox", guide="mymcpjobs"),
    F("mymcpoauth", "Eigene MCP-Dienste mit Anmeldung", "Own MCP services with sign-in", "day", ("mcp_own_oauth",), "mymcp_on",
      parent="mymcp", me="mymcpbox", guide="mymcpoauth"),
    F("messages", "Nachrichten an andere", "Messages to others", "day", ("messages",), "msg_on", me="msgbox", guide="messages"),
    F("messages_all", "Nachricht an alle", "Message to everybody", "day", ("messages_all",), parent="messages",
      me="msgbox", guide="messages_all"),
    F("messages_voice", "Sprachnachrichten", "Voice messages", "day", ("messages_voice",), parent="messages",
      me="msgbox", guide="messages_voice"),
    F("calendar", "Kalender", "Calendar", "day", ("calendar",), me="calbox", guide="calendar"),
    F("weather", "Wetter", "Weather", "day", ("weather",), "wx_on", me="wxbox", guide="weather"),
    # mail and contacts
    F("mail", "E-Mail lesen", "Reading e-mail", "post", ("mail",), me="mailbox", guide="mail"),
    F("tidy", "Postfach aufräumen", "Inbox tidying", "post", ("mail_tidy",), parent="mail", me="mailbox", guide="tidy"),
    F("parcels", "Pakete", "Parcels", "post", ("parcels",), "par_on", parent="mail", me="parbox", guide="parcels"),
    F("schreib", "Schreibhilfe", "Writing help", "post", ("write_help",), "write_on", me="writebox", guide="schreib"),
    F("schreibapps", "Schreibhilfe in anderen Programmen", "Writing help in other programs", "post", ("write_apps",),
      "write_apps", parent="schreib", me="writebox", guide="schreibapps"),
    F("contacts", "Kontakte", "Contacts", "post", ("contacts",), "con_on", me="conbox", guide="contacts"),
    # home
    F("ha", "Home Assistant", "Home Assistant", "home", ("homeassistant",), me="habox", guide="ha"),
    F("room", "Raum-Modus", "Room mode", "home", ("room",), me="roombox", guide="room"),
    F("roomtv", "Fernsehstimmen überhören", "Ignore TV voices", "home", ("room_voices",), parent="room", me="roombox", guide="roomtv"),
    F("roomha", "Raum-Modus für Home Assistant", "Room mode for Home Assistant", "home", ("room_ha",), parent="room",
      me="roombox", guide="roomha"),
    F("esp32", "Eigene Lautsprecher (ESP32)", "Own speakers (ESP32)", "home", ("esp32",), "esp_on", me="espbox", guide="esp32"),
    F("roomfar", "Raum-Modus aus der Ferne starten", "Start room mode from afar", "home", ("room_remote", "esp32"), "room_remote",
      parent="room", me="roombox", guide="roomfar"),
    F("messages_announce", "Durchsagen auf Lautsprechern", "Announcements on speakers", "home", ("messages_announce",),
      "msg_announce", parent="messages", me="msgbox", guide="messages_announce"),
    F("wyoming", "Home Assistant Assist (Wyoming)", "Home Assistant Assist (Wyoming)", "home", ("wyoming",), guide="wyoming"),
    # on the go and devices
    F("transit", "Bus und Bahn", "Bus and train", "go", ("transit",), "transit_on", me="trbox", guide="transit"),
    F("telegram", "Telegram", "Telegram", "go", ("telegram",), me="tgbox", guide="telegram"),
    F("android", "Android-App", "Android app", "go", ("android",), "android_on", me="andbox", guide="android"),
    F("begleiter", "Spark-Begleiter am PC und Mac", "Spark companion on PC and Mac", "go", ("desk",), "desk_on",
      me="deskbox", guide="begleiter"),
    F("begleitertun", "Begleiter darf am PC handeln", "Companion may act on the PC", "go", ("desk_act",),
      parent="begleiter", me="deskbox", guide="begleitertun"),
    F("begleitermeeting", "Besprechungen mitschreiben", "Write along in meetings", "go", ("desk_meeting",),
      parent="begleiter", me="deskbox", guide="begleitermeeting"),
    F("pebble", "Pebble-Uhr", "Pebble watch", "go", ("pebble",), "pebble_on", me="pebbox", guide="pebblepair"),
    # new firmware and app versions for the devices (geraeteupdate.py): overview, notes, speakers at night, XiaoZhi
    F("geraeteupdate", "Geräte-Updates", "Device updates", "go", ("dev_updates",), "devup_on", me="setbox", guide="geraeteupdate"),
    F("geraetenacht", "Lautsprecher nachts aktualisieren", "Update speakers at night", "go", ("dev_updates_night", "esp32"),
      "devup_night", parent="geraeteupdate", me="setbox", guide="geraetenacht"),
    F("xiaozhihinweis", "Hinweis auf neue XiaoZhi-Version", "Note on a new XiaoZhi version", "go", ("dev_updates_upstream",),
      parent="geraeteupdate", guide="xiaozhihinweis"),
    F("mcpserver", "Spark als MCP-Server", "Spark as MCP server", "go", ("mcp_server",), "mcps_on", me="mcpbox", guide="mcpserver"),
    F("mcpextern", "MCP-Server von außen (OAuth)", "MCP server from outside (OAuth)", "go", ("mcp_server_extern",),
      parent="mcpserver", me="mcpbox", guide="mcpextern"),
    F("mcpact", "MCP: Handeln mit Bestätigung", "MCP: acting with confirmation", "go", ("mcp_server_act",),
      parent="mcpserver", me="mcpbox", guide="mcpact"),
    F("iphone", "iPhone-App", "iPhone app", "go", ("iphone",), "app_on", me="appbox", guide="iphone"),
    F("iphonepush", "Push an die iPhone-App", "Push to the iPhone app", "go", ("iphone_push",), "app_push", parent="iphone",
      me="appbox", guide="iphonepush"),
    F("iphonepanel", "Panel-Bereiche in der iPhone-App", "Panel areas in the iPhone app", "go", ("iphone_panel",),
      parent="iphone", me="appbox", guide="iphonepanel"),
    F("iphoneupdate", "Spark-Update über die iPhone-App", "Spark update from the iPhone app", "go", ("iphone_update",),
      parent="iphone", guide="iphoneupdate"),
    # security
    F("speaker", "Sprechererkennung", "Speaker recognition", "sec", ("speaker_id",), me="voicebox", guide="speaker"),
    F("spkcode", "Codewort am Lautsprecher", "Code word at a speaker", "sec", ("speaker_code", "esp32"), "spk_code",
      parent="speaker", me="espbox", guide="spkcode"),
    F("mfa", "Zweiter Anmeldeschritt", "Second sign-in step", "sec", ("mfa",), me="secbox", guide="mfa"),
    # reports as GitHub issues with anonymized log lines (meldung.py); what goes out is shown before
    F("melden", "Probleme melden", "Reporting problems", "sec", ("report",), "report_on", me="rpbox", guide="melden"),
    F("meldenadmin", "Admin über Meldungen informieren", "Tell admins about reports", "sec", ("report_notify",),
      parent="melden", me="rpbox", guide="meldenadmin"),
    # dienstwacht.py: the Spark looks at its services and tells the admins when one is gone and when it is back
    F("dienstwacht", "Dienst-Wächter", "Service watch", "sec", ("svc_watch",), "svc_note", me="setbox", guide="dienstwacht"),
    # speicher.py: a copy of the profile's data on its own NAS (WebDAV, SFTP, SMB) or a folder the admin mounted
    F("speicher", "Eigener Speicher", "Own storage", "data", ("storage_own",), "storage_on", me="storebox", guide="speicher"),
    F("speicherlan", "Speicher im Heimnetz", "Storage in the home network", "data", ("storage_lan",), parent="speicher",
      me="storebox", guide="speicherlan"),
    F("speicherordner", "Ordner auf dem Spark", "Folder on the Spark", "data", ("storage_folder",), parent="speicher",
      me="storebox", guide="speicherordner"),
    F("speicherauslagern", "Originale auslagern", "Move originals out", "data", ("storage_offload",), parent="speicher",
      me="storebox", guide="speicherauslagern"),
    F("dienstnutzer", "Hinweis, wenn ein Dienst fehlt", "Note when a service is missing", "talk", ("svc_watch_users",),
      "svc_hint", parent="dienstwacht", me="setbox", guide="dienstnutzer"),
    # verlauf.py (plan plaene/verlauf-sync.md): the history on every device of the profile
    F("verlaufsync", "Verlauf sofort abgleichen", "Instant history sync", "talk", ("history_live",), "sync_live",
      me="setbox", guide="verlaufsync"),
    F("eingespraech", "Ein Gespräch für alle Kanäle", "One conversation for all channels", "talk", ("history_one",), "sync_one",
      me="setbox", guide="eingespraech"),
    F("offlinelesen", "Verlauf offline lesen", "Read history offline", "talk", ("history_offline",), "sync_offline",
      me="setbox", guide="offlinelesen"),
    # Einstellungs-Assistent (faelle.py, berater.py): problems become cases, cases proposals from a fixed catalog
    F("berater", "Einstellungs-Assistent", "Settings assistant", "talk", ("berater",), guide="berater"),
    F("beratererklaeren", "Anfragen erklären", "Explain requests", "talk", ("berater_explain",), parent="berater",
      guide="beratererklaeren"),
    F("beraterchat", "Den Assistenten nach Vorschlägen fragen", "Ask the assistant for proposals", "talk",
      ("berater_chat",), "berater_ask", parent="berater", me="setbox", guide="beraterchat"),
    F("beraterhinweis", "Hinweis bei neuem Vorschlag", "Note on a new proposal", "talk", ("berater_notify",),
      "berater_note", parent="berater", me="setbox", guide="beraterhinweis"),
    F("beraterissue", "Fälle als Meldung vorbereiten", "Prepare cases as reports", "talk", ("berater_issue",),
      parent="berater", guide="beraterissue"),
    F("beraterauto", "Autopilot für kleine Änderungen", "Autopilot for small changes", "talk", ("berater_auto",),
      parent="berater", guide="beraterauto"),
    F("beraterideen", "Ideen außerhalb des Katalogs", "Ideas outside the catalog", "talk", ("berater_ideas",),
      parent="berater", guide="beraterideen"),
    F("berateru", "Schritte für die Umgebung", "Steps for the environment", "talk", ("berater_env",), parent="berater",
      guide="berateru"),
    F("beratermich", "Vorschläge für mein Profil", "Proposals for my profile", "talk", ("berater_me",), "berater_me",
      parent="berater", me="setbox", guide="beratermich"),
    F("bewerten", "👍/👎 unter Antworten", "👍/👎 under answers", "talk", ("bewerten",), "rate_on", parent="berater",
      me="setbox", guide="bewerten"),
    F("bewertenzurueck", "Rückmeldung, wenn es behoben ist", "Feedback when it is fixed", "talk", ("bewerten_back",),
      "rate_back", parent="bewerten", me="setbox", guide="bewertenzurueck"),
)
BY_KEY = {f.key: f for f in FEATURES}
profiles.NO_PRESET.update(f.profile for f in FEATURES if f.profile)

# Spark-wide conditions besides the switches (an address that must be set), registered by the module
# that knows them, so this file imports none of them: key -> function(chat config) -> bool
READY = {"beraterissue": lambda c: admin_on("melden", c)}   # a case as a report needs „Probleme melden“
# extra per-profile conditions given by the admin (the agent level): key -> function(uid) -> bool
GRANTED = {}
# the second step a profile still owes before using a function (join.py, new profiles by invitation):
# function(uid, key) -> bool, set by join.py
DUTY = None

# chat.* switches that are no function a profile uses (how the Spark itself works)
SPARK_ONLY = {"public", "thinking", "prompt_cache", "answer_check", "datetime", "face_life", "esp32_ota_http"}
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
    "chat.datetime": "Grundfunktion: das Modell kennt Datum und Uhrzeit, keine persönlichen Daten",
    "chat.memory": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.history": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.documents": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.reminders": "Grundfunktion von Anfang an, nur eigene Daten, nie Gäste",
    "chat.calendar": "Grundfunktion von Anfang an, braucht trotzdem einen eigenen Kalender des Profils",
    "chat.esp32_ota_http": "Dominik 2026-10-11: Lautsprecher-Updates über http bleiben erlaubt (sonst nur per USB)",
}
# names for the Spark-wide switches that are no function of their own (the app's Funktionen page shows them under "Spark")
SPARK_NAMES = {"public": ("Gastzugang", "Guest access"), "thinking": ("Vorher nachdenken", "Think first"),
               "prompt_cache": ("Schneller Antwortbeginn", "Faster first words"),
               "answer_check": ("Antworten prüfen", "Check answers"), "datetime": ("Datum und Uhrzeit mitgeben", "Pass date and time"),
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


def profile_on(key, uid, s=None):
    """The profile's own switch (True when the function has none). Never from the admin's presets."""
    f = BY_KEY[key]
    if not uid:
        return False
    if f.profile:
        s = profiles.settings(uid) if s is None else s
        if s.get(f.profile) is not True:
            return False
    grant = GRANTED.get(key)
    return bool(grant(uid)) if grant else True


def reason(key, uid, c=None, s=None):
    """Why it cannot be used: "spark" (admin switch), "guest", "profile" (own switch), "mfa" (the second
    step first, join.py) or None."""
    if not admin_on(key, c):
        return "spark"
    if not uid:
        return None if BY_KEY[key].guests else "guest"
    if not profile_on(key, uid, s):
        return "profile"
    return "mfa" if DUTY and DUTY(uid, key) else None


def allowed(key, uid, c=None, s=None):
    return reason(key, uid, c, s) is None


def count(uid, c=None):
    """(on, of) for Personen und Geräte: of the functions with an own switch the Spark allows, how many are on for uid."""
    c = chat_cfg() if c is None else c
    s = profiles.settings(uid)
    mine = [f for f in FEATURES if f.profile and admin_on(f.key, c)]
    return sum(1 for f in mine if s.get(f.profile) is True), len(mine)


def guests(c=None):
    """What guests get: the guest access switch and how many functions they could use with it."""
    c = chat_cfg() if c is None else c
    return {"public": _switch(c, "public"), "features": sum(1 for f in FEATURES if f.guests and admin_on(f.key, c))}


WHY = {"spark": ("Vom Admin ausgeschaltet", "Switched off by the admin"),
       "guest": ("Nur mit Profil", "Only with a profile"),
       "profile": ("Bei dir aus", "Off for you"),
       "mfa": ("Erst den zweiten Anmeldeschritt einrichten (Ich → Sicherheit)", "Set up the second sign-in step first (Me → Security)")}


def state(uid, c=None):
    """Every function with what the Spark, the profile and guests may: for Ich, the app and the search.
    Guests see only the functions guests can use."""
    c = chat_cfg() if c is None else c
    s = profiles.settings(uid) if uid else {}
    out = []
    for f in FEATURES:
        if not uid and not f.guests:
            continue
        why = reason(f.key, uid, c, s)
        out.append({"key": f.key, "name": [f.de, f.en], "group": f.group, "spark": admin_on(f.key, c),
                    "own": f.profile or None, "mine": (s.get(f.profile) is True) if uid and f.profile else None,
                    "can": why is None, "why": why, "guests": f.guests, "parent": f.parent or None,
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
    """Where the profile switches it on: Ich → <page> „<name>“ (way.js marks the row)."""
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
    if uid and f.profile and profiles.settings(uid).get(f.profile) is not True:
        out.append(("Du selbst: " if li == 0 else "You yourself: ") + me_way(key, lang) + (" einschalten." if li == 0 else " on."))
    return " ".join(out)


router = APIRouter()


@router.get("/api/features", dependencies=[Depends(assistant)])
def features_list(request: Request):
    """What may be used here and why not: one list for Ich, the app and the search."""
    prof = profiles.current(request)
    guard.limit(request, "features", prof and prof["id"])
    return {"groups": [{"key": k, "name": [de, en]} for k, de, en in GROUPS],
            "features": state(prof["id"] if prof else None), "why": WHY, "stamp": stamp(prof["id"] if prof else None)}


# ---------------------------------------------------------------- Funktionen → "Wer darf was" (admin)
SEEN = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "features-seen.json")
_UID = re.compile(r"u_[0-9a-f]{12}")


def _seen(c):
    """When each function was first on on this Spark: "Neu, noch nie an" lists the others."""
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


def new_profile(uid):
    """A new profile gets the functions the admin chose for new profiles (chat.new_profile_on)."""
    keys = [k for k in chat_cfg().get("new_profile_on", []) if k in BY_KEY and BY_KEY[k].profile]
    if keys:
        profiles.save_settings(uid, {BY_KEY[k].profile: True for k in keys})
    return keys


def matrix():
    c = chat_cfg()
    seen = _seen(c)
    users = profiles.names()
    s = {u["id"]: profiles.settings(u["id"]) for u in users}
    import admin
    import coadmin
    switchable = set(admin.app_switches())   # what /api/admin/switches may change (not public, mfa, iphone …)
    rows, new = [], set(c.get("new_profile_on", []))
    for f in FEATURES:
        rows.append({"key": f.key, "name": [f.de, f.en], "group": f.group, "switch": f.admin[0], "spark": admin_on(f.key, c),
                     "own": _switch(c, f.admin[0]), "switchable": f.admin[0] in switchable, "parent": f.parent or None, "guests": f.guests, "seen": f.key in seen,
                     "profile": f.profile or None, "guide": f.guide, "new": f.key in new if f.profile else None,
                     "cells": {u["id"]: s[u["id"]].get(f.profile) is True for u in users} if f.profile else None,
                     "chain": chain_switches(f.key), "setup": [admin_way(k) for k in unready(f.key, c)]})
    every = sorted({sw for f in FEATURES for sw in f.admin})
    return {"groups": [{"key": k, "name": [de, en]} for k, de, en in GROUPS], "features": rows,
            "profiles": [{"id": u["id"], "name": u["name"], "role": coadmin.role(u["id"]) if coadmin.on() else ""} for u in users],
            "public": _switch(c, "public"), "why": WHY,
            "states": {sw: _switch(c, sw) for sw in every}, "snames": {sw: list(switch_name(sw)) for sw in every},
            "switchable": sorted(sw for sw in every if sw in switchable)}


@router.get("/api/admin/features", dependencies=[Depends(auth)])
def admin_features(request: Request):
    guard.limit(request, "features", admin=True)
    return matrix()


@router.put("/api/admin/features/{key}/profiles/{uid}", dependencies=[Depends(auth)])
async def admin_feature_profile(key: str, uid: str, request: Request):
    """The admin switches a function for one profile (its own switch, which the profile sees under Ich)."""
    guard.limit(request, "features", admin=True)
    f = BY_KEY.get(key)
    if not f or not f.profile or not _UID.fullmatch(uid) or not profiles.by_id(uid):
        raise HTTPException(404, "no such function or profile")
    raw = await request.body()
    if len(raw) > 256:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    on = body.get("on") if isinstance(body, dict) else None
    if not isinstance(on, bool):
        raise HTTPException(400, "on: true or false")
    import admin
    admin._no_admin_profile(request, uid)
    profiles.save_settings(uid, {f.profile: on})
    elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
    by = "main" if not elev else elev["id"]
    guard.log("feature_profile", uid=uid, by=by,
              detail=f"{f.de} für {profiles.by_id(uid)['name']} {'an' if on else 'aus'}")
    return {"key": key, "uid": uid, "on": on}


@router.put("/api/admin/features/{key}/new", dependencies=[Depends(auth)])
async def admin_feature_new(key: str, request: Request):
    """On for every new profile (chat.new_profile_on); profiles that exist keep their own switch."""
    guard.limit(request, "features", admin=True)
    f = BY_KEY.get(key)
    if not f or not f.profile:
        raise HTTPException(404, "no such function with an own switch")
    raw = await request.body()
    if len(raw) > 256:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    on = body.get("on") if isinstance(body, dict) else None
    if not isinstance(on, bool):
        raise HTTPException(400, "on: true or false")
    import admin
    with admin._save_lock:   # one config write at a time (admin._save)
        new = admin.get_config()
        keys = [k for k in new["chat"].get("new_profile_on", []) if k != key] + ([key] if on else [])
        new["chat"]["new_profile_on"] = [k for k in BY_KEY if k in keys]
        admin.validate(new)
        write_json(admin.CONFIG_PATH, new, indent=2)
    elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
    guard.log("feature_profile", by="main" if not elev else elev["id"], detail=f"{f.de} für neue Profile {'an' if on else 'aus'}")
    return {"key": key, "on": on}


@router.post("/api/admin/features/{key}/enable", dependencies=[Depends(auth)])
async def admin_feature_enable(key: str, request: Request):
    """Switch a function on together with everything it builds on (its chain's Spark switches), optionally also
    for one profile ({"uid": ...}). Switches the app may not change and what still needs setting up come back
    as ways, they are never switched here."""
    guard.limit(request, "features", admin=True)
    f = BY_KEY.get(key)
    if not f:
        raise HTTPException(404, "no such function")
    raw = await request.body()
    if len(raw) > 256:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    uid = body.get("uid") if isinstance(body, dict) else None
    if uid is not None and (not isinstance(uid, str) or not _UID.fullmatch(uid) or not profiles.by_id(uid) or not f.profile):
        raise HTTPException(404, "no such profile or no own switch")
    import admin
    if uid:
        admin._no_admin_profile(request, uid)
    may = set(admin.app_switches())
    todo = missing(key)
    can, manual = [sw for sw in todo if sw in may], [sw for sw in todo if sw not in may]
    if can:
        with admin._save_lock:   # one config write at a time (admin._save)
            new = admin.get_config()
            for sw in can:
                new["chat"][sw] = True
            old = admin.validate(new)
            write_json(admin.CONFIG_PATH, new, indent=2)
        admin.undo.record(old, new, admin._by(request), admin.SENSITIVE)
        guard.log("config_switch", detail=", ".join(f"chat.{sw}=on" for sw in can) + f" (für {f.de})")
    if uid:
        profiles.save_settings(uid, {f.profile: True})
        elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
        guard.log("feature_profile", uid=uid, by="main" if not elev else elev["id"],
                  detail=f"{f.de} für {profiles.by_id(uid)['name']} an")
    c = chat_cfg()
    return {"key": key, "switched": can, "names": [list(switch_name(sw)) for sw in can],
            "manual": [{"switch": sw, "name": list(switch_name(sw)), "way": [switch_way(sw), switch_way(sw, "en")]} for sw in manual],
            "setup": [[admin_way(k), admin_way(k, "en")] for k in unready(key, c)], "spark": admin_on(key, c)}
