"""Spickzettel zum Ausdrucken (plan plaene/spickzettel.md, Dominik 2026-10-20: „Kannst du sowas auch dem User zugänglich
machen in Englisch und Deutsch und auch aktuell halten, sodass er sich das aus dem Portal runterladen kann?“, „1a 2a 3b“).

Ich → Was ich kann opens a page of two A4 sheets: per area of saetze.AREAS the cards of the Weiche, each with sentences
to say, the word the Weiche reacts to marked, its key words and the function behind it. Only what this profile can use
right now (saetze.usable, plan 1a), as a page the browser prints or saves as PDF (2a), part of „Das kannst du auch
sagen“ without a switch of its own (3b).

Never out of date: built on each request from the code. The sentences are werkzeug_abdeckung.SENTENCES plus the few
of KARTEN here, the marked word is what intent.classify really matched (with the admin's own words of Funktionen →
Weiche), the names of the functions come from features.py, the version from app/VERSION. test_spickzettel turns red
when a tool of saetze.AREAS has no card, a sentence or key word does not reach its group, or a mix-up lands elsewhere.

Only fixed texts of the code and the admin's own Weiche words, nothing of the profile's data; the secret code word of
the speakers is never read. Never for guests, the Notaus does not matter (nothing is done), never over MCP.
"""
import html
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

import features
import guard
import intent
import saetze
from core import app_version, assistant, browser_profile

router = APIRouter()
CACHE_S = 600          # one built page per language and set of tools, at most this long
CACHE_MAX = 24
_CACHE = {}

# per area of saetze.AREAS (same ids) the cards: (Weiche groups, tools, title de/en, key words de/en, more sentences)
# every tool of saetze.AREAS stands on exactly one card; a key word must hit one of the card's groups, a sentence its
# tool (test_spickzettel). The first sentence of a tool is its werkzeug_abdeckung.SENTENCES line.
KARTEN = {
    "alltag": (
        (("erinnerung",), ("reminder_set", "reminder_list", "reminder_cancel", "anruf_planen"),
         ("Erinnerung, Timer, Weckruf", "Reminders, timers, wake-up call"),
         ("Erinnerung, erinnere mich, Timer, Wecker, weck mich, ruf mich … an",
          "reminder, remind me, timer, call me at"),
         (("reminder_set", "Stell einen Timer auf fünf Minuten", "Set a timer for five minutes"),
          ("reminder_set", "Weck mich morgen um sieben", "Wake me tomorrow at seven"))),
        (("liste",), ("tasks_show", "tasks_add", "tasks_change"),
         ("Einkaufsliste und Aufgaben", "Shopping list and tasks"),
         ("Einkaufsliste, Einkaufszettel, Aufgabenliste, To-do, auf die Liste, abhaken", "shopping list, to-do"),
         (("tasks_add", "Kauf noch Zwiebeln", "Buy onions too"),)),
        (("wetter",), ("weather",), ("Wetter", "Weather"),
         ("Wetter, Regen, Schnee, Gewitter, Frost, Glatteis, Schirm, Regenjacke, draußen",
          "weather, rain, forecast"),
         (("weather", "Brauche ich heute einen Schirm?", "Do I need an umbrella today?"),)),
        (("bahn",), ("transit",), ("Bus und Bahn", "Bus and train"),
         ("Bus, Bahn, S-Bahn, U-Bahn, Zug, Tram, Abfahrt, Verbindung, Fahrplan, ICE, Bahnhof, Gleis",
          "bus, train, tram, departures"),
         (("transit", "Hat mein Zug Verspätung?", "Is my train late?"),)),
        (("paket",), ("parcels",), ("Pakete", "Parcels"),
         ("Paket, Päckchen, Lieferung, Sendung, Bestellung, DHL, Hermes, DPD, GLS", "parcel, package, delivery"),
         (("parcels", "Wo ist meine DHL-Sendung?", "Where is my DHL parcel?"),)),
        (("feeds",), ("feeds_news",), ("Reddit und Feeds", "Reddit and feeds"),
         ("Reddit, Subreddit, r/name, meine Feeds, RSS-Feed", "reddit, subreddit, feeds"),
         (("feeds_news", "Was steht in meinen Feeds?", "What is in my feeds?"),)),
    ),
    "termine": (
        (("kalender",), ("daily_briefing", "calendar_events", "calendar_add", "calendar_change"),
         ("Kalender und Tagesbriefing", "Calendar and daily briefing"),
         ("Termin, Kalender, verabredet, eintragen, Briefing, Morgenbriefing, Meeting, Elternabend, "
          "hab ich … Zeit", "appointment, calendar, meeting, briefing"),
         (("daily_briefing", "Guten Morgen!", "Good morning!"),
          ("calendar_events", "Hab ich am Freitag Zeit?", "Am I free on Friday?"))),
        (("mail",), ("mail_list", "mail_read", "mail_tidy_overview"), ("E-Mail", "Email"),
         ("Mail, E-Mail, Posteingang, Postfach, Newsletter, Spam, Werbemails", "mail, email, inbox"),
         (("mail_list", "Wie viele Newsletter kamen heute?", "How many newsletters came today?"),)),
        (("mail",), ("fuer_dich", "fuer_dich_tun"), ("Für dich aus Mails", "For you from mail"),
         ("was muss ich … erledigen, offene Rechnung, in Für dich", "mail"),
         (("fuer_dich", "Habe ich offene Rechnungen?", "Do I have open bills?"),)),
        (("kontakt",), ("contacts_search",), ("Kontakte", "Contacts"),
         ("Telefonnummer, Handynummer, Adresse von, Anschrift, Geburtstag, wo wohnt", "phone number, contacts"),
         (("contacts_search", "Wann hat Oma Geburtstag?", "When is Grandma's birthday?"),)),
    ),
    "nachrichten": (
        (("nachricht",), ("message_send", "message_read", "message_announce"),
         ("Nachrichten im Haus", "Messages at home"),
         ("Nachricht, Chat, Durchsage, Bescheid, richte … aus", "message, chat"),
         (("message_send", "Richte Tom aus, dass das Essen fertig ist", "Tell Tom that dinner is ready"),)),
        (("iphone",), ("iphone_action",), ("Auf dem iPhone", "On the iPhone"),
         ("ruf … an, anrufen, navigieren, Route nach, bring mich nach, Kurzbefehl, iPhone",
          "iphone, shortcut, call, navigate"),
         (("iphone_action", "Navigiere nach Hause", "Navigate home"),)),
    ),
    "zuhause": (
        (("smarthome",), ("home_assistant", "home_assistant_states", "home_assistant_history", "camera_describe"),
         ("Smart Home", "Smart home"),
         ("Licht, Lampe, Heizung, Thermostat, Temperatur, Rollo, Steckdose, Fernseher, Tür, Fenster, "
          "Waschmaschine, Kamera, Wohnzimmer, Küche, Bad", "lights, heating, doors, windows, smart home"),
         (("home_assistant", "Stell die Heizung auf 21 Grad", "Set the heating to 21 degrees"),)),
    ),
    "wissen": (
        (("websuche",), ("web_search",), ("Websuche", "Web search"),
         ("Nachrichten, Schlagzeilen, Bundesliga, im Internet, google mal, recherchieren, DAX, Aktie, Spritpreis, "
          "Stau, Öffnungszeiten, was kostet", "news, search the web, look it up online"),
         (("web_search", "Hat der Baumarkt heute offen?", "Is the DIY store open today?"),
          ("web_search", "Wie steht der DAX?", "How is the DAX doing?"))),
        (("wikipedia", "archiv"), ("wikipedia", "archive_search"), ("Wikipedia und eigenes Archiv",
                                                                     "Wikipedia and own archive"),
         ("Wikipedia, Wiki, Lexikon, Enzyklopädie, Kiwix, mein Archiv, im Archiv", "wikipedia, wiki, encyclopedia, kiwix"),
         (("wikipedia", "Was sagt das Lexikon über Vulkane?", "What does the encyclopedia say about volcanoes?"),)),
        (("dokument",), ("document_search", "document_list"), ("Eigene Dokumente", "Own documents"),
         ("Dokument, Unterlagen, Vertrag, Rechnung, PDF, Versicherung, Garantie, Anleitung, Bescheid, "
          "Kündigungsfrist, Steuer, Beleg", "documents, pdf"),
         (("document_search", "Wie lange habe ich Garantie auf den Fernseher?",
           "How long is the warranty on the TV?"),)),
        (("finden",), ("fund_suche",), ("Finden in allen Daten", "Find in all data"),
         ("such meine …, finde meine …, wo ist meine Rechnung, such die Bestellung, finde die Buchung, wo ist der Vertrag",
          "find my …, find my invoice, search my contract"),
         (("fund_suche", "Such meine Rechnung von Thomann", "Find my invoice from Thomann"),)),
        (("mappe",), ("mappe_liste", "mappe_stand", "mappe_dazu"), ("Mappen", "Collections"),
         ("welche Mappen, was liegt in der Mappe, leg … in die Mappe", "collections, what is in the collection"),
         (("mappe_stand", "Was liegt in der Mappe Urlaub?", "What is in the collection Holiday?"),
          ("mappe_dazu", "Leg den Mietvertrag in die Mappe Wohnung", "Put the lease into the collection Flat"))),
        (("gedaechtnis",), ("history_search",), ("Frühere Gespräche", "Earlier conversations"),
         ("haben wir darüber gesprochen, letztes Mal, worüber haben wir", "remember"), ()),
    ),
    "machen": (
        (("erstellen",), ("document_plan",), ("Dokument erstellen: schreib, erstell, mach …", "Make a document: write, make …"),
         ("Brief, Präsentation, Folien, Tabelle, Excel, Word, PDF, Bericht, Protokoll, Kündigung",
          "letter, presentation, spreadsheet, report"),
         (("document_plan", "Schreib mir eine Kündigung fürs Fitnessstudio",
           "Write me a letter of termination for the gym"),)),
        (("bild",), ("bild_malen",), ("Bild malen", "Paint a picture"),
         ("male, zeichne, mal mir ein, Bild, Logo, Malvorlage, Ausmalbild", "paint, draw"),
         (("bild_malen", "Zeichne ein Logo für meinen Verein", "Draw a logo for my club"),)),
        (("musik",), ("musik_machen",), ("Musik machen", "Make music"),
         ("komponiere, Lied, Song, Melodie, Schlaflied", "compose, song"),
         (("musik_machen", "Komponier eine ruhige Melodie", "Compose a calm melody"),)),
        (("musik",), ("musik_bearbeiten",), ("Musik bearbeiten", "Edit music"),
         ("verlängere das Lied, kürze das Lied, Lied als Reggae, Remix vom Lied, Tonart vom Lied",
          "extend the song, shorten the song, remix the song"),
         (("musik_bearbeiten", "Mach aus meinem Lied eine Reggae-Version", "Turn my last song into reggae"),)),
    ),
    "gedaechtnis": (
        (("gedaechtnis",), ("memory_save", "memory_forget"), ("Gedächtnis", "Memory"),
         ("merk dir, vergiss, weißt du noch, was weißt du über mich, ich mag keine, ich bin allergisch",
          "remember, forget"),
         (("memory_save", "Ich bin allergisch gegen Nüsse", "I am allergic to nuts"),)),
        (("erstellen",), ("spark_tagebuch",), ("Spark-Tagebuch", "Spark diary"),
         ("was hast du heute gemacht, Spark-Tagebuch", "what did you do"), ()),
    ),
    "auftraege": (
        (("agent",), ("agent_list", "agent_schedule", "agent_watch", "agent_change"), ("Aufträge", "Jobs"),
         ("Agent, Routine, Auftrag, Beobachtung, pass auf ob", "agent, routine"),
         (("agent_schedule", "Schick mir jeden Montag die Schlagzeilen", "Send me the headlines every Monday"),)),
    ),
    "spark": (
        (("spark",), ("spark_hilfe", "spark_vorschlag"), ("Hilfe zum Spark", "Help with the Spark"),
         ("Einstellung, Schalter, Funktion, wie stelle ich, wo schalte ich, was empfiehlst du", "settings"),
         (("spark_hilfe", "Wo finde ich den Schalter für Telegram?", "Where do I find the switch for Telegram?"),)),
        (("zustand",), ("spark_zustand",), ("Zustand des Sparks", "State of the Spark"),
         ("läuft alles, Störung, Ausfall, Sicherung, Backup, Update, welche Version, Notaus, mein Zustand",
          "backup, update, online"),
         (("spark_zustand", "Läuft alles?", "Is everything running?"),)),
    ),
}
AREA_COLOR = {"alltag": "#1f7a5c", "termine": "#2b5fb8", "nachrichten": "#8a4fb0", "zuhause": "#c0612b",
              "wissen": "#15808f", "machen": "#b23a6b", "gedaechtnis": "#6c6a1f", "auftraege": "#4a5568",
              "spark": "#9a6f08"}
# tools a module offers only on the person's own word (werkzeug_abdeckung.BY_WORD): (tool, de, en)
KURZ = (("speaker_volume", "Mach leiser", "Quieter"),
        ("undo_last", "Mach das rückgängig", "Undo that"),
        ("proactive_pause", "Meld dich heute nicht mehr", "No more notes today"),
        ("remarkable_page", "Schick den Artikel aufs reMarkable", "Send the article to the reMarkable"),
        ("remarkable_library", "Was liegt auf meinem reMarkable?", "What is on my reMarkable?"),
        ("nas_zustand", "Ist die Synology voll?", "Is the Synology full?"),
        ("offen_zeigen", "Was ist noch offen?", "What is still open?"),
        ("rechnen", "Rechne 19 Prozent von 249 Euro aus", "Calculate 19 percent of 249 euros"))
# easily mixed up: (de, en, the Weiche group it lands in or "" for a plain answer, what happens de/en, a tool that
# must be usable for the line to show or "")
VERWECHSELT = (
    ("Ruf mich um acht an", "Call me at eight", "erinnerung", ("der Spark ruft dich an", "the Spark calls you"),
     "anruf_planen"),
    ("Ruf Mama an", "Call Mum", "iphone", ("das iPhone wählt", "the iPhone dials"), "iphone_action"),
    ("Mach mir ein Lied über Katzen", "Make me a song about cats", "musik", ("Musik machen", "make music"),
     "musik_machen"),
    ("Mach mir eine Liste der Hauptstädte als Excel", "Make me a list of capitals as Excel", "erstellen",
     ("ein Dokument, nicht die Einkaufsliste", "a document, not the shopping list"), "document_plan"),
    ("Was heißt Fenster auf Englisch?", "", "", ("Wissen, kein Smart Home", "knowledge, no smart home"), ""),
    ("Was ist der Unterschied zwischen Wetter und Klima?", "", "",
     ("Wissen, keine Vorhersage", "knowledge, no forecast"), ""),
    ("Starte das Terminal", "", "", ("kein Termin", "no appointment"), ""),
)
TIPPS = (
    ("<b>Stichwort deutlich sagen:</b> „im Kalender“, „in meinen Mails“, „im Internet“, „in Wikipedia“.",
     "<b>Name the place:</b> “in my calendar”, “in my mail”, “on the web”, “in Wikipedia”."),
    ("<b>Eine Sache pro Satz.</b> Mehr als zwei Bereiche auf einmal gelten als unklar, dann rät das Modell eher.",
     "<b>One thing per sentence.</b> More than two areas at once count as unclear; the model then guesses more."),
    ("<b>Kurz nachfragen geht:</b> „Und morgen?“ bleibt beim Bereich deiner Frage davor.",
     "<b>Short follow-ups work:</b> “And tomorrow?” stays with the area of your question before."),
    ("<b>Nach Mail, Web oder Dokument</b> fängt eine neue klare Bitte ohne „davon“ oder „dazu“ frisch an.",
     "<b>After mail, web or a document</b> a new clear request without “of it” starts fresh."),
    ("<b>Sagt der Spark, eine Funktion fehlt,</b> ist sie noch nicht freigegeben. Frag deinen Admin.",
     "<b>If the Spark says a function is missing,</b> it is not released yet. Ask your admin."),
    ("<b>Frag „Was kannst du?“</b> oder schau unter Ich → Was ich kann.",
     "<b>Ask “What can you do?”</b> or look under Me → What I can do."),
    ("<b>„Gemerkt: …“ unter der Antwort</b> zeigt, was sich der Spark gerade gemerkt hat; „Rückgängig“ nimmt es zurück.",
     "<b>“Remembered: …” under the answer</b> shows what the Spark just kept; “Undo” takes it back."),
    ("<b>Alle deine Daten</b> als eine ZIP: Ich → Sicherheit → Meine Daten (mit deinem Code).",
     "<b>All your data</b> as one ZIP: Me → Security → My data (with your code)."),
)
EN_NOTE = ("The Spark's fixed word rules are mostly German. An English sentence without one of these words still "
           "works: then the language model picks the tool itself.")


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _marked(text, c):
    """The sentence with the words the Weiche really matched in <mark> (intent.classify, the admin's words too)."""
    try:
        why = intent.classify_cfg(text, c).why
    except Exception:
        why = {}
    out = _esc(text)
    for w in sorted({str(v) for v in why.values() if v}, key=len, reverse=True):
        e = _esc(w)
        if e and e in out and "<mark>" not in out:
            out = out.replace(e, f"<mark>{e}</mark>", 1)
    return out


def own_words(c):
    """The admin's own words per group (Funktionen → Weiche), {group: [words]}; nothing when they cannot be read."""
    try:
        return intent.parse_route_words(c.get("route_words") or "")
    except ValueError:
        return {}


def cards(uid, c, org="panel"):
    """[(area id, name de/en, [card])] with only what this profile can use (plan 1a)."""
    out = []
    for aid, de, en, _tools in saetze.AREAS:
        rows = []
        for groups, tools, title, words, more in KARTEN.get(aid, ()):
            mine = [t for t in tools if saetze.usable(uid, t, c, org)]
            if not mine:
                continue
            said = [saetze.text_of(t) for t in mine if saetze.text_of(t)]
            said += [(sde, sen) for t, sde, sen in more if t in mine]
            names = list(dict.fromkeys(tuple(saetze._fname(t)) for t in mine))
            rows.append({"groups": groups, "title": title, "words": words, "said": said, "names": names})
        if rows:
            out.append((aid, (de, en), rows))
    return out


def kurz(uid, c, org="panel"):
    return [(de, en) for t, de, en in KURZ if saetze.usable(uid, t, c, org)]


def verwechselt(uid, c, org="panel"):
    return [x for x in VERWECHSELT if not x[4] or saetze.usable(uid, x[4], c, org)]


def build(uid, lang, c, admin_words=None, now=None):
    """The whole page (HTML) for this profile in de or en."""
    en = lang == "en"
    i = 1 if en else 0
    c = c or {}
    own = own_words(c) if admin_words is None else admin_words
    parts = []
    shown = cards(uid, c)
    body = []
    for aid, name, rows in shown:
        for r in rows:
            said = "".join(f"<li>{_marked(x[i], c)}</li>" for x in r["said"] if x[i])
            extra = [w for g in r["groups"] for w in own.get(g, ())]
            words = _esc(r["words"][i]) + (f" · <i>{_esc(', '.join(extra))}</i>" if extra else "")
            sw = " · ".join(_esc(n[i]) for n in r["names"] if n[i])
            body.append(f'<article class="card" style="--c:{AREA_COLOR.get(aid, "#4a5568")}">'
                        f'<span class="tag">{_esc(name[i])}</span><h3>{_esc(r["title"][i])}</h3><ul class="say">{said}</ul>'
                        f'<p class="kw"><b>{"Words" if en else "Stichwörter"}:</b> {words}</p>'
                        f'<p class="sw">{sw}</p></article>')
    if body:
        parts.append(f'<div class="cards all">{"".join(body)}</div>')
    k = kurz(uid, c)
    if k:
        items = "".join(f"<li>{_esc(x[i])}</li>" for x in k)
        parts.append(f'<section class="area" style="--c:#4a5568"><h2>{"Short commands" if en else "Kurzbefehle"}</h2>'
                     f'<div class="cards"><article class="card wide"><ul class="say two">{items}</ul></article></div></section>')
    mix = [x for x in verwechselt(uid, c) if x[i]]
    if mix:
        q = ("“", "”") if en else ("„", "“")
        items = "".join(f'<li><span>{q[0]}{_esc(x[i])}{q[1]}</span><span>{_esc(x[3][i])}</span></li>' for x in mix)
        parts.append(f'<section class="area" style="--c:#1b2330"><h2>{"Easily mixed up" if en else "Leicht verwechselt"}'
                     f'</h2><div class="cards"><article class="card wide"><ul class="mix">{items}</ul></article></div></section>')
    tips = "".join(f"<li>{t[i]}</li>" for t in TIPPS)   # fixed texts of this module, with <b>
    parts.append(f'<section class="area" style="--c:#1b2330"><h2>{"Wrong answer? Try this" if en else "Falsche Antwort? So klappt es"}'
                 f'</h2><div class="cards"><article class="card wide"><ol class="tips">{tips}</ol></article></div></section>')
    if not shown:
        parts.insert(0, f'<p class="empty">{"Nothing you can say is released for you right now." if en else "Gerade ist für dich nichts freigegeben, das du sagen kannst."}</p>')
    ver = _esc(app_version()[:20])
    day = time.strftime("%d.%m.%Y", time.localtime(now or time.time()))
    title = "What you say, what the Spark does" if en else "Was du sagst, was der Spark tut"
    sub = ("Cheat sheet: these words fetch the right tool. Marked: the word the Spark reacts to."
           if en else "Spickzettel: diese Wörter holen das passende Werkzeug. Markiert: das Wort, auf das der Spark anspringt.")
    hint = ("Save as PDF: Print (Ctrl P, on the iPhone Share → Print) → Save as PDF."
            if en else "Als PDF sichern: Drucken (Strg P, am iPhone Teilen → Drucken) → Als PDF sichern.")
    note = f'<p class="note">{_esc(EN_NOTE)}</p>' if en else ""
    return (f'<!doctype html><html lang="{"en" if en else "de"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_esc(title)}</title>'
            f'<style>{CSS}</style></head><body><main>'
            f'<header class="top"><h1>{_esc(title)}<small>{_esc(sub)}</small></h1>'
            f'<div class="stamp"><b>{ver}</b>{day}</div></header>'
            f'<p class="screen">{_esc(hint)} <a href="/#me=kannbox">{"Back to the panel" if en else "Zurück zum Panel"}</a></p>{note}{"".join(parts)}'
            f'<footer>{"Made by your Spark from its own rules; it changes with every update." if en else "Von deinem Spark aus seinen eigenen Regeln erzeugt; er ändert sich mit jedem Update."}</footer>'
            '</main></body></html>')


CSS = """
:root{--paper:#fff;--ink:#1b2330;--muted:#5b6676;--line:#d9dee6;--mark:#fff0a8;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.35 "Atkinson Hyperlegible",Verdana,"Segoe UI",system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px max(16px,env(safe-area-inset-right,0px)) 24px max(16px,env(safe-area-inset-left,0px));display:flex;flex-direction:column;gap:12px}
header.top{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;border-bottom:3px solid var(--ink);padding-bottom:8px}
h1{font:800 1.9rem/1.05 "Avenir Next","Segoe UI",system-ui,sans-serif;margin:0;letter-spacing:-.01em}
h1 small{display:block;font-size:.85rem;font-weight:400;color:var(--muted);margin-top:5px;letter-spacing:0}
.stamp{font-size:.8rem;color:var(--muted);text-align:right}.stamp b{display:block;color:var(--ink);font-size:.95rem}
.screen,.note,.empty{margin:0;font-size:.85rem;color:var(--muted)}
.screen a{color:var(--ink)}
.area{display:flex;flex-direction:column}
.area h2{align-self:flex-start;margin:0;background:var(--c);color:#fff;font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;padding:2px 10px;border-radius:4px 4px 0 0}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;border-top:3px solid var(--c);padding-top:7px}
.card{border:1px solid var(--line);border-top:3px solid var(--c,var(--ink));border-radius:6px;padding:6px 8px;display:flex;flex-direction:column;gap:3px;min-width:0;break-inside:avoid}
.card.wide{grid-column:1/-1}
.cards.all{border-top:0;padding-top:0}
.tag{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--c)}
.area h2{break-after:avoid}
.card h3{margin:0;font-size:1rem;color:var(--c)}
.say{list-style:none;margin:0;padding:0}.say li{padding-left:12px;position:relative}
.say li::before{content:"»";position:absolute;left:0;color:var(--c);font-weight:700}
.say.two{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px 12px}
mark{background:var(--mark);color:inherit;font-weight:700;padding:0 2px;border-radius:2px}
.kw,.sw{margin:0;font-size:.8rem;color:var(--muted)}.kw b{color:var(--ink)}
.sw{border-top:1px dotted var(--line);padding-top:2px}
.mix{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 14px;font-size:.85rem}
.mix li{display:flex;justify-content:space-between;gap:8px;border-bottom:1px dotted var(--line)}.mix li span:last-child{color:var(--muted);text-align:right}
.tips{margin:0;padding-left:18px;font-size:.85rem}
footer{font-size:.75rem;color:var(--muted);border-top:1px solid var(--line);padding-top:5px}
@media (max-width:760px){.cards,.say.two,.mix{grid-template-columns:minmax(0,1fr)}}
@page{size:A4 portrait;margin:9mm}
@media print{html{font-size:8pt}body{font-size:1rem;line-height:1.25}main{padding:0;max-width:none;gap:6px}
 *{-webkit-print-color-adjust:exact;print-color-adjust:exact}.screen{display:none}
 .cards{grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;padding-top:4px}.say.two{grid-template-columns:repeat(3,minmax(0,1fr))}
 .mix{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:3px 6px}h1{font-size:2.4rem}}
"""


def page(uid, lang, c):
    """build() kept a while per language, set of usable tools, version and admin words (the Pi builds it rarely)."""
    tools = tuple(t for _a, _d, _e, ts in saetze.AREAS for t in ts if saetze.usable(uid, t, c)) + \
        tuple(t for t, _d, _e in KURZ if saetze.usable(uid, t, c))
    key = (lang, tools, app_version()[:20], c.get("route_words") or "", c.get("route_not") or "", c.get("tool_words") or "")
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < CACHE_S:
        return hit[1], tools
    text = build(uid, lang, c, now=now)
    if len(_CACHE) >= CACHE_MAX:
        _CACHE.pop(min(_CACHE, key=lambda k: _CACHE[k][0]), None)
    _CACHE[key] = (now, text)
    return text, tools


@router.get("/api/profile/spickzettel", dependencies=[Depends(assistant)])
def api_page(request: Request, sprache: str = "de", datei: int = 0, prof=Depends(browser_profile)):
    """Ich → Was ich kann „Spickzettel“: the page to print or save as PDF; ?datei=1 as a file to keep."""
    uid = prof["id"]
    guard.limit(request, "tipps", uid)
    if not features.allowed(saetze.KEY, uid):
        print("tipps: Spickzettel abgelehnt aus", flush=True)
        raise HTTPException(403, "Beispielsätze sind aus")
    lang = "en" if sprache == "en" else "de"
    text, tools = page(uid, lang, features.chat_cfg())
    print(f"tipps: Spickzettel {lang} {len(tools)} Werkzeuge{' Datei' if datei else ''}", flush=True)
    saetze._event("spick")
    headers = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                                          "form-action 'none'; frame-ancestors 'self'",
               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
    if datei:
        headers["Content-Disposition"] = f'attachment; filename="spark-spickzettel-{lang}.html"'
    return HTMLResponse(text, headers=headers)
