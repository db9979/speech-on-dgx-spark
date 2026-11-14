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
import steckbrief
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
            ("agentbox", "Aufträge", "Jobs"), ("mymcpbox", "Meine MCP-Dienste", "My MCP services"), ("wxbox", "Wetter", "Weather"),
            ("probox", "Von selbst", "By itself"), ("notebox", "Mitteilungen", "Notifications"),
            ("wissbox", "Was ich über dich weiß", "What I know about you"), ("writebox", "Schreibhilfe", "Writing help"),
            ("habox", "Smart Home", "Smart home"), ("roombox", "Raum-Modus", "Room mode"), ("espbox", "Lautsprecher", "Speakers"), ("telbox", "Telefon", "Phone"),
            ("tgbox", "Telegram", "Telegram"), ("appbox", "iPhone-App", "iPhone app"),
            ("andbox", "Android-App", "Android app"), ("deskbox", "Begleiter", "Companion"), ("pebbox", "Pebble-Uhr", "Pebble watch"),
            ("termbox", "Terminal", "Terminal"), ("mcpbox", "Spark als MCP-Server", "Spark as MCP server"), ("llmapibox", "Sprachmodell per API", "Language model by API"), ("secbox", "Sicherheit", "Security"),
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
             ("wbbox", "wbuch", "Wissensbuch", "Knowledge book"), ("fundbox", "finden", "Finden", "Find"),
             ("mpbox", "mappen", "Mappen", "Collections"),
             ("dmbox", "dungeon", "Dungeon-Master", "Dungeon Master"))
# pages of their own without the tab „Einstellungen“: Mappen shows only its list and the open Mappe, the old tab's
# explanation sits in the ⓘ beside the budget (plan mappen-layout 1a, Dominik 2026-11-05); kalender.js OWN_NO_SET
OWN_NO_SETTINGS = frozenset(("mpbox",))
# Ich pages every profile has, whatever is switched on (me.js meAll shows them for every profile too)
ME_ALWAYS = frozenset(("setbox", "factbox", "logbox", "secbox"))
# Ich pages the iPhone app leaves out, each with its reason; every other page can be opened in the app
APP_SKIP = {"overbox": "the app's own start screen shows the overview",
            "gobox": "first steps in the browser after signing up",
            "loginbox": "the app is signed in by its own key",
            "andbox": "the Android app, not for an iPhone"}
# Pages the iPhone app shows itself (plan ios-nativ 5, Dominik 2026-11-14 „1-5“): „Im Panel öffnen“ leads there and
# not into the panel; the word names the app's own view (PanelViews.swift NativePage), a long press still opens the
# panel. A page only partly in the app (Dungeon-Master: new rounds) stays out until the app holds all of it.
APP_NATIVE = {"calbox": "kalender", "mailbox": "post", "taskbox": "listen", "vgbox": "offen", "conbox": "kontakte",
              "wbbox": "wissensbuch", "fundbox": "finden", "mpbox": "mappen",
              "bgbox": "zustand", "factbox": "gedaechtnis", "docbox": "dokumente", "bildbox": "bilder",
              "musikbox": "musik", "wissbox": "ichweiss", "probox": "vonselbst", "agentbox": "vonselbst",
              "wxbox": "vonselbst", "secbox": "sicherheit", "voicebox": "stimme", "notebox": "profil",
              "espbox": "lautsprecher", "setbox": "profil"}
# Begleiter-Gleichstand (Dominik 2026-10-30, Begleiter Paket A): every function is in the Begleiter on purpose or
# left out with its reason. DESK: the function → the Begleiter parts (begleiter.PARTS) that carry it; DESK_SKIP: the
# function → why not. A sub-function follows its parent unless it stands here itself. test_app_gleichstand.Begleiter
# checks that every function is in exactly one of both and every part belongs to a function.
DESK = steckbrief.desk()   # every function's Begleiter parts stand in its Steckbrief (steckbrief.py)
_D_PANEL = "stays in the panel: set up, looked at and deleted there"
_D_LINK = "stays in the panel; the Begleiter's settings (Übersicht) link to its place"
_D_TALK = "works in every answer, Frag Spark included; nothing of its own on the computer, set up in the panel"
_D_SPARK = "a setting of the whole Spark for the admin, stays in the panel"
_D_VOICE = "for speaking in the room (speakers, phone); the Begleiter asks by text, dictation or the wake word"
_D_DEVICE = "another device with its own app or page"
DESK_SKIP = {k: {"talk": _D_TALK, "voice": _D_VOICE, "spark": _D_SPARK, "link": _D_LINK, "device": _D_DEVICE,
                 "panel": _D_PANEL}.get(v, v)   # every function's reason stands in its Steckbrief (steckbrief.py)
             for k, v in steckbrief.begleiter().items()}
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
    F(**steckbrief.feature("search")),
    F(**steckbrief.feature("suchschnell")),
    F(**steckbrief.feature("wiki")),
    F(**steckbrief.feature("kiwix")),
    F(**steckbrief.feature("lokal")),
    F(**steckbrief.feature("quelle")),
    F(**steckbrief.feature("quellesagen")),
    F(**steckbrief.feature("roles")),
    F(**steckbrief.feature("style")),
    F(**steckbrief.feature("follow")),
    F(**steckbrief.feature("selfecho")),
    F(**steckbrief.feature("stimmdesign")),
    F(**steckbrief.feature("anhalten")),
    F(**steckbrief.feature("satzende")),
    F(**steckbrief.feature("fixes")),
    F(**steckbrief.feature("klaeren")),
    F(**steckbrief.feature("klaerenmerken")),
    F(**steckbrief.feature("klaerenweg")),
    F(**steckbrief.feature("ablauf")),
    F(**steckbrief.feature("images")),
    F(**steckbrief.feature("toolthink")),
    F(**steckbrief.feature("routing")),
    F(**steckbrief.feature("direct")),
    F(**steckbrief.feature("hoeren")),
    F(**steckbrief.feature("sofort")),
    F(**steckbrief.feature("rechnen")),   # rechnen.py: name, group, switch and guide in its Steckbrief
    F(**steckbrief.feature("gedkurz")),
    F(**steckbrief.feature("ack")),
    F(**steckbrief.feature("weicheabstimmen")),
    F(**steckbrief.feature("weicheunklar")),
    F(**steckbrief.feature("vorab")),
    F(**steckbrief.feature("hilfe")),
    F(**steckbrief.feature("hilfevorschlag")),
    F(**steckbrief.feature("hilfeseite")),
    F(**steckbrief.feature("tipps")),
    F(**steckbrief.feature("tippspush")),
    F(**steckbrief.feature("tippssaetze")),
    F(**steckbrief.feature("tippsstimme")),
    F(**steckbrief.feature("gespraech")),
    F(**steckbrief.feature("einordnung")),
    F(**steckbrief.feature("einordnungpost")),
    F(**steckbrief.feature("einordnungtest")),
    F(**steckbrief.feature("einordnungrat")),
    F(**steckbrief.feature("einordnungcheck")),
    F(**steckbrief.feature("unbelegt")),
    F(**steckbrief.feature("einordnungklage")),
    F(**steckbrief.feature("helfer")),
    F(**steckbrief.feature("helferangriff")),
    F(**steckbrief.feature("vorrang")),
    # knowledge and memory
    F(**steckbrief.feature("memory")),
    F(**steckbrief.feature("gedpruefen")),
    F(**steckbrief.feature("gedfragen")),
    F(**steckbrief.feature("gedthemen")),
    F(**steckbrief.feature("gedhinweis")),
    F(**steckbrief.feature("history")),
    F(**steckbrief.feature("documents")),
    F(**steckbrief.feature("docpics")),
    F(**steckbrief.feature("docmeaning")),
    F(**steckbrief.feature("docfiles")),
    F(**steckbrief.feature("docnight")),
    F(**steckbrief.feature("docshared")),
    F(**steckbrief.feature("teilen")),
    F(**steckbrief.feature("teilenhinweis")),
    F(**steckbrief.feature("docling")),
    F(**steckbrief.feature("remarkable")),
    F(**steckbrief.feature("rmsend")),
    F(**steckbrief.feature("rmfresh")),
    F(**steckbrief.feature("rmmorning")),
    F(**steckbrief.feature("rmask")),
    F(**steckbrief.feature("rmtodo")),
    F(**steckbrief.feature("rmmeet")),
    F(**steckbrief.feature("rmweek")),
    F(**steckbrief.feature("rmweb")),
    F(**steckbrief.feature("rminbox")),
    F(**steckbrief.feature("rmguide")),
    F(**steckbrief.feature("rmpapier")),
    F(**steckbrief.feature("rmordner")),
    F(**steckbrief.feature("rmaufraeumen")),
    F(**steckbrief.feature("rmaufgaben")),
    F(**steckbrief.feature("erstellen")),
    F(**steckbrief.feature("erstellenvorlagen")),
    F(**steckbrief.feature("erstellenbilder")),
    F(**steckbrief.feature("bilder")),
    F(**steckbrief.feature("bildaendern")),
    F(**steckbrief.feature("musik")),
    F(**steckbrief.feature("musikbearbeiten")),
    F(**steckbrief.feature("dungeon")),
    F(**steckbrief.feature("dungeonbilder")),
    F(**steckbrief.feature("dungeonpruefung")),
    F(**steckbrief.feature("dungeongast")),
    F(**steckbrief.feature("dungeonbuecher")),
    F(**steckbrief.feature("dungeongeschichten")),
    F(**steckbrief.feature("dungeonpruefstand")),
    F(**steckbrief.feature("docbrief")),
    F(**steckbrief.feature("auswertungen")),
    F(**steckbrief.feature("docaudio")),
    F(**steckbrief.feature("doclink")),
    F(**steckbrief.feature("docyoutube")),
    F(**steckbrief.feature("suchpruefung")),
    F(**steckbrief.feature("nachsortieren")),
    F(**steckbrief.feature("wissensbuch")),
    F(**steckbrief.feature("wissenskarte")),
    F(**steckbrief.feature("wissensknoten")),
    F(**steckbrief.feature("kartensuche")),
    F(**steckbrief.feature("mappen")),
    F(**steckbrief.feature("hoerstueck")),
    F(**steckbrief.feature("hoerstueckdisk")),
    F(**steckbrief.feature("fund")),
    F(**steckbrief.feature("fundmail")),
    F(**steckbrief.feature("fundtermine")),
    F(**steckbrief.feature("fundkontakte")),
    F(**steckbrief.feature("fundchats")),
    F(**steckbrief.feature("fundlisten")),
    F(**steckbrief.feature("fundmedien")),
    F(**steckbrief.feature("fundschlagworte")),
    F(**steckbrief.feature("suchfragen")),
    # everyday
    F(**steckbrief.feature("proactive")),
    F(**steckbrief.feature("halive")),
    F(**steckbrief.feature("haloud")),
    F(**steckbrief.feature("haevent")),
    F(**steckbrief.feature("havoice")),
    F(**steckbrief.feature("mailwichtig")),
    F(**steckbrief.feature("hacam")),
    F(**steckbrief.feature("reminders")),
    F(**steckbrief.feature("notedevice")),
    F(**steckbrief.feature("vorgaenge")),
    F(**steckbrief.feature("tasks")),
    F(**steckbrief.feature("listshare")),
    F(**steckbrief.feature("listnote")),
    F(**steckbrief.feature("listdav")),
    F(**steckbrief.feature("listlink")),
    F(**steckbrief.feature("mystatus")),
    F(**steckbrief.feature("agent")),
    F(**steckbrief.feature("beobachten")),
    F(**steckbrief.feature("auftragsplan")),
    F(**steckbrief.feature("mcp")),
    F(**steckbrief.feature("mymcp")),
    F(**steckbrief.feature("mymcpjobs")),
    F(**steckbrief.feature("mymcpoauth")),
    F(**steckbrief.feature("chats")),
    F(**steckbrief.feature("messages_all")),
    F(**steckbrief.feature("chatgroups")),
    F(**steckbrief.feature("chatmedia")),
    F(**steckbrief.feature("chatinvite")),
    F(**steckbrief.feature("chatprivate")),
    F(**steckbrief.feature("verbund")),
    F(**steckbrief.feature("verbundmedia")),
    F(**steckbrief.feature("verbundgruppen")),
    F(**steckbrief.feature("anrufe")),
    F(**steckbrief.feature("anrufeturn")),
    F(**steckbrief.feature("anrufassistent")),
    F(**steckbrief.feature("calendar")),
    F(**steckbrief.feature("calshare")),
    F(**steckbrief.feature("calserver")),
    F(**steckbrief.feature("weather")),
    # mail and contacts
    F(**steckbrief.feature("mail")),
    F(**steckbrief.feature("tidy")),
    F(**steckbrief.feature("mailmanage")),
    F(**steckbrief.feature("mailspaeter")),
    F(**steckbrief.feature("mailsend")),
    F(**steckbrief.feature("maildelete")),
    F(**steckbrief.feature("maillearn")),
    F(**steckbrief.feature("einladungen")),
    F(**steckbrief.feature("mailidle")),
    F(**steckbrief.feature("mailcode")),
    F(**steckbrief.feature("mailstil")),
    F(**steckbrief.feature("parcels")),
    F(**steckbrief.feature("fuerdich")),
    F(**steckbrief.feature("ichweiss")),
    F(**steckbrief.feature("schreib")),
    F(**steckbrief.feature("schreibapps")),
    F(**steckbrief.feature("contacts")),
    F(**steckbrief.feature("kontakteaendern")),
    F(**steckbrief.feature("kontaktserver")),
    # home
    F(**steckbrief.feature("ha")),
    F(**steckbrief.feature("room")),
    F(**steckbrief.feature("roomtv")),
    F(**steckbrief.feature("roomha")),
    F(**steckbrief.feature("esp32")),
    F(**steckbrief.feature("espstopp")),
    F(**steckbrief.feature("roomfar")),
    F(**steckbrief.feature("messages_announce")),
    F(**steckbrief.feature("wyoming")),
    F(**steckbrief.feature("telefon")),
    F(**steckbrief.feature("telefongast")),
    F(**steckbrief.feature("telefonaussen")),
    F(**steckbrief.feature("telefonanrufen")),
    F(**steckbrief.feature("telefonalarm")),
    # on the go and devices
    F(**steckbrief.feature("telegram")),
    F(**steckbrief.feature("android")),
    F(**steckbrief.feature("androidlive")),
    F(**steckbrief.feature("androidupdate")),
    F(**steckbrief.feature("androidassist")),
    F(**steckbrief.feature("androidlock")),
    F(**steckbrief.feature("begleiter")),
    F(**steckbrief.feature("begleitertun")),
    F(**steckbrief.feature("begleitermeeting")),
    F(**steckbrief.feature("begleiterschirm")),
    F(**steckbrief.feature("begleiterbedienen")),
    F(**steckbrief.feature("pebble")),
    F(**steckbrief.feature("pebblegesund")),
    F(**steckbrief.feature("terminal")),
    F(**steckbrief.feature("geraeteupdate")),
    F(**steckbrief.feature("geraetenacht")),
    F(**steckbrief.feature("mcpserver")),
    F(**steckbrief.feature("mcpextern")),
    F(**steckbrief.feature("mcpact")),
    F(**steckbrief.feature("llmapi")),
    F(**steckbrief.feature("llmapiextern")),
    F(**steckbrief.feature("llmapiassist")),
    F(**steckbrief.feature("openwebui")),
    F(**steckbrief.feature("iphone")),
    F(**steckbrief.feature("iphonepush")),
    F(**steckbrief.feature("iphonepanel")),
    F(**steckbrief.feature("appmerken")),
    F(**steckbrief.feature("iphonepruef")),
    F(**steckbrief.feature("iphoneupdate")),
    # security
    F(**steckbrief.feature("speaker")),
    F(**steckbrief.feature("spkcode")),
    F(**steckbrief.feature("mfa")),
    F(**steckbrief.feature("melden")),
    F(**steckbrief.feature("meldenadmin")),
    F(**steckbrief.feature("meldendirekt")),
    F(**steckbrief.feature("meldenerfunden")),
    F(**steckbrief.feature("verbrauch")),
    F(**steckbrief.feature("kontingent")),
    F(**steckbrief.feature("dienstwacht")),
    F(**steckbrief.feature("rundlauf")),
    F(**steckbrief.feature("wachposten")),
    F(**steckbrief.feature("wartung")),
    F(**steckbrief.feature("wartungauto")),
    F(**steckbrief.feature("notbetriebasr")),
    F(**steckbrief.feature("gehaeuse")),
    F(**steckbrief.feature("systemupdates")),
    F(**steckbrief.feature("systemnachtpanel")),
    F(**steckbrief.feature("systemnachtmodelle")),
    F(**steckbrief.feature("schwachstellen")),
    F(**steckbrief.feature("sparkclients")),
    F(**steckbrief.feature("schirm")),
    F(**steckbrief.feature("modellwechsel")),
    F(**steckbrief.feature("modelleeigen")),
    F(**steckbrief.feature("werkstatt")),
    F(**steckbrief.feature("werkstattnacht")),
    F(**steckbrief.feature("entwickeln")),
    F(**steckbrief.feature("entwickelngithub")),
    F(**steckbrief.feature("entwickelnterminal")),
    F(**steckbrief.feature("entwickelnauftrag")),
    F(**steckbrief.feature("fernzugang")),
    F(**steckbrief.feature("fernzugangmeldung")),
    F(**steckbrief.feature("fernzugangalle")),
    F(**steckbrief.feature("spontanhilfe")),
    F(**steckbrief.feature("spontansteuern")),
    F(**steckbrief.feature("fernzuganghilfe")),
    F(**steckbrief.feature("fernbild")),
    F(**steckbrief.feature("fernbildablage")),
    F(**steckbrief.feature("fernnotizen")),
    F(**steckbrief.feature("fernordner")),
    F(**steckbrief.feature("fernals")),
    F(**steckbrief.feature("ferngross")),
    F(**steckbrief.feature("fernweb")),
    F(**steckbrief.feature("fernsshtermy")),
    F(**steckbrief.feature("angriffsprobe")),
    F(**steckbrief.feature("nas")),
    F(**steckbrief.feature("speicher")),
    F(**steckbrief.feature("nasquelle")),
    F(**steckbrief.feature("nashaushalt")),
    F(**steckbrief.feature("nasablage")),
    F(**steckbrief.feature("naszustand")),
    F(**steckbrief.feature("speicherlan")),
    F(**steckbrief.feature("speicherordner")),
    F(**steckbrief.feature("speicherauslagern")),
    F(**steckbrief.feature("dienstnutzer")),
    F(**steckbrief.feature("verlaufsync")),
    F(**steckbrief.feature("eingespraech")),
    F(**steckbrief.feature("offlinelesen")),
    F(**steckbrief.feature("berater")),
    F(**steckbrief.feature("beratererklaeren")),
    F(**steckbrief.feature("beraterchat")),
    F(**steckbrief.feature("beraterhinweis")),
    F(**steckbrief.feature("beraterissue")),
    F(**steckbrief.feature("beraterauto")),
    F(**steckbrief.feature("beraterideen")),
    F(**steckbrief.feature("beraterana")),
    F(**steckbrief.feature("beraterundo")),
    F(**steckbrief.feature("berateru")),
    F(**steckbrief.feature("beratermich")),
    F(**steckbrief.feature("bewerten")),
    F(**steckbrief.feature("beraterwarum")),
    F(**steckbrief.feature("tagebuch")),
    F(**steckbrief.feature("sparkzustand")),
    F(**steckbrief.feature("rueckgaengig")),
    F(**steckbrief.feature("bewertenzurueck")),
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


def _stimmdesign_set_up():
    t = load_config("tts")
    return bool(t.get("voicedesign_enabled")) and (bool(t.get("klon_enabled")) or str(t.get("model", "")).endswith("-Base"))


READY = {"beraterissue": lambda c: admin_on("melden", c),   # a case as a report needs „Probleme melden“
         "docling": _docling_set_up,                          # the Docling server needs its address
         "bilder": lambda c: bool(load_config("image").get("enabled")),   # the picture model installed (install.sh --bild)
         "musik": lambda c: bool(load_config("music").get("enabled")),    # the music model installed (install.sh --musik)
         "naszustand": _naszustand_set_up,                    # the NAS status needs its host and SNMP user
         "stimmdesign": lambda c: _stimmdesign_set_up()}       # VoiceDesign and a Base engine on the speech output
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
SPARK_ONLY = {"public", "thinking", "prompt_cache", "answer_check", "answer_check_more", "action_check", "loop_stop", "datetime", "face_life", "esp32_ota_http"} \
    | steckbrief.nur_spark()   # with the functions that have a Steckbrief (steckbrief.py)
# Everything starts off (Dominik 2026-10-08). The only values shipped on in config.default.json are protection and
# stability rules and the basic functions the Spark had from the start, each with its reason here (Dominik 2026-10-12,
# docs/de/richtlinien.md, part 3). tests/test_richtlinie.py fails for a value shipped on that is not listed.
# chat.defaults are presets of a profile's own manners (hands-free, barge-in …), not functions: they never switch
# a function on (test_features.test_presets_never_switch_a_function_on).
DEFAULT_ON = {
    "chat.fernzugang_meldung": "Schutz (Dominik 2026-10-28): Admins erfahren von jeder Fernsitzung über das Internet oder von einem neuen Ort; wirkt nur, wenn der Fernzugang an ist",
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
    "chat.memory_check": ("Schutz (Plan nutzerwissen, Frage 1): vielleicht Veraltetes wird nie als Tatsache gesagt; "
                          "feste Regeln des Panels, kein Modell, nichts verlässt das Haus, nie Gäste"),
    "chat.memory_note": ("Schutz und Transparenz (Plan nutzerwissen, Frage 5): was der Spark sich merkt, sieht die Person "
                         "sofort und kann es zurücknehmen; feste Regeln des Panels, nichts verlässt das Haus, nie Gäste"),
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
    Ich pages but APP_SKIP with at least one function this profile may use, and the pages of ME_ALWAYS; "app" names
    the app's own view of a page it shows itself (APP_NATIVE).
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
        page = {"id": key, "name": [de, en]}
        if key in APP_NATIVE:
            page["app"] = APP_NATIVE[key]
        out.append(page)
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
